const tg = window.Telegram?.WebApp;
const webSessionToken = localStorage.getItem("doupo_web_session_token") || "";
const state = {
  token: localStorage.getItem("doupo_admin_token") || "",
  initData: tg?.initData || (webSessionToken ? `web_session:${webSessionToken}` : ""),
  bootstrap: null,
};

function toSameOriginPath(path, fallback = "") {
  if (!path) return fallback;
  try {
    const url = new URL(path, window.location.origin);
    if (url.origin !== window.location.origin) return fallback;
    return `${url.pathname}${url.search}${url.hash}` || fallback;
  } catch {
    return fallback;
  }
}

function setupBackNavigation() {
  const fallbackPath = "/plugins/doupo/app";
  const returnTo = toSameOriginPath(new URLSearchParams(window.location.search).get("return_to"), "");
  const target = returnTo || fallbackPath;
  const link = document.querySelector("#page-back-link");
  if (link) link.href = target;
  if (tg?.BackButton) {
    const goBack = () => { window.location.href = target; };
    tg.BackButton.offClick?.(goBack);
    tg.BackButton.onClick(goBack);
    tg.BackButton.show();
  }
}

function setStatus(text) {
  const node = document.querySelector("#admin-status");
  if (node) node.textContent = String(text || "");
}

function headers(withJson = true) {
  const h = {};
  if (withJson) h["Content-Type"] = "application/json";
  if (state.token) h["x-admin-token"] = state.token;
  if (state.initData) h["x-telegram-init-data"] = state.initData;
  return h;
}

async function request(method, path, body = null) {
  const response = await fetch(path, {
    method,
    headers: headers(body !== null),
    body: body === null ? undefined : JSON.stringify(body),
  });
  const raw = await response.text();
  const payload = raw ? JSON.parse(raw) : { code: response.status, data: null };
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || "请求失败");
  }
  return payload.data;
}

function safeJson(text, fallback = {}) {
  try {
    const data = JSON.parse(String(text || "").trim() || "{}");
    if (data && typeof data === "object") return data;
  } catch {}
  return fallback;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function itemIconHtml(icon, name = "物品") {
  const value = String(icon || "").trim();
  if (!value) return "";
  if (/^https:\/\//i.test(value)) {
    return `<img class="item-icon" src="${escapeHtml(value)}" alt="" title="${escapeHtml(name)}" loading="lazy" referrerpolicy="no-referrer" />`;
  }
  return `<span class="item-icon-text" aria-hidden="true">${escapeHtml(value)}</span>`;
}

document.addEventListener("error", (event) => {
  const image = event.target;
  if (!(image instanceof HTMLImageElement) || !image.classList.contains("item-icon")) return;
  const fallback = document.createElement("span");
  fallback.className = "item-icon-text";
  fallback.setAttribute("aria-hidden", "true");
  fallback.textContent = "物";
  image.replaceWith(fallback);
}, true);

function fillActionForm(item = {}) {
  document.querySelector("#action-key").value = item.action_key || "";
  document.querySelector("#action-name").value = item.name || "";
  document.querySelector("#action-type").value = item.action_type || "train";
  document.querySelector("#action-cooldown").value = Number(item.cooldown_seconds || 0);
  document.querySelector("#action-desc").value = item.description || "";
  document.querySelector("#action-reward").value = JSON.stringify(item.reward_config || {}, null, 2);
  document.querySelector("#action-requirement").value = JSON.stringify(item.requirement_config || {}, null, 2);
  document.querySelector("#action-enabled").checked = Boolean(item.enabled ?? true);
  document.querySelector("#action-sort").value = Number(item.sort_order || 0);
  setStatus(`已载入行动：${item.name || item.action_key || ""}`);
}

function itemCostSummary(reward = {}) {
  const costs = [];
  const itemCosts = reward.item_costs || {};
  if (Array.isArray(itemCosts)) {
    itemCosts.forEach((item) => {
      const key = item.item_key || item.key;
      const qty = Number(item.quantity || item.qty || 0);
      if (key && qty > 0) costs.push(`${key} x${qty}`);
    });
  } else if (itemCosts && typeof itemCosts === "object") {
    Object.entries(itemCosts).forEach(([key, qty]) => {
      if (Number(qty || 0) > 0) costs.push(`${key} x${Number(qty || 0)}`);
    });
  }
  if (reward.gold_cost) costs.push(`gold x${Number(reward.gold_cost)}`);
  if (reward.core_cost) costs.push(`core x${Number(reward.core_cost)}`);
  return costs.join(" + ");
}

function renderActionList(data = {}) {
  const list = document.querySelector("#action-list");
  if (!list) return;
  const rows = Array.isArray(data.actions) ? data.actions : [];
  list.innerHTML = rows.map((item) => {
    const req = item.requirement_config || {};
    const requirement = item.action_type === "breakthrough" ? "九星圆满 / 动态丹药与金币" : [
      req.realm_stage_min ? `境界 ${req.realm_stage_min}` : "",
      req.realm_stars_min ? `${Number(req.realm_stars_min)} 星` : "",
      req.gold_min ? `金币 ${Number(req.gold_min)}` : "",
      req.core_min ? `魔核 ${Number(req.core_min)}` : "",
      req.alchemy_min ? `炼药 ${Number(req.alchemy_min)}` : "",
      req.fire_min ? `火候 ${Number(req.fire_min)}` : "",
      req.sect_contribution_min ? `贡献 ${Number(req.sect_contribution_min)}` : "",
      req.pill_min ? `丹药 ${Number(req.pill_min)}` : "",
      req.technique_level_min ? `斗技 ${Number(req.technique_level_min)}` : "",
      req.fire_progress_min ? `线索 ${Number(req.fire_progress_min)}` : "",
      req.boss_score_min ? `Boss ${Number(req.boss_score_min)}` : "",
      req.tower_floor_min ? `塔层 ${Number(req.tower_floor_min)}` : "",
      req.auction_credit_min ? `拍卖 ${Number(req.auction_credit_min)}` : "",
    ].filter(Boolean).join(" / ") || "无门槛";
    const recipe = ["alchemy", "craft"].includes(item.action_type) ? itemCostSummary(item.reward_config || {}) : "";
    return `
      <li>
        <span>${escapeHtml(item.action_key)} - ${escapeHtml(item.name)} (${escapeHtml(item.action_type_label || item.action_type)}) · ${escapeHtml(requirement)}${recipe ? ` · 配方 ${escapeHtml(recipe)}` : ""}</span>
        <button type="button" class="ghost mini" data-edit-action="${escapeHtml(item.action_key)}">编辑</button>
      </li>
    `;
  }).join("") || "<li>暂无行动</li>";
  list.querySelectorAll("[data-edit-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-edit-action");
      const item = rows.find((row) => row.action_key === key);
      if (item) fillActionForm(item);
    });
  });
}

function metricItem(label, value, note = "") {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${note ? `<small>${escapeHtml(note)}</small>` : ""}</article>`;
}

function renderAdminMetrics(data = {}) {
  const accountSummary = data.game_accounts?.summary || {};
  const playerSearch = data.player_search || {};
  const root = document.querySelector("#admin-metrics");
  if (root) {
    root.innerHTML = [
      metricItem("斗破玩家", Number(playerSearch.total || 0), "独立角色档案"),
      metricItem("统一账号", Number(accountSummary.total || 0), `${Number(accountSummary.bound || 0)} 个已绑定 TG`),
      metricItem("可用行动", (data.actions || []).filter((item) => item.enabled).length, `共 ${(data.actions || []).length} 项`),
      metricItem("账号异常", Number(accountSummary.disabled || 0), `${Number(accountSummary.unbound || 0)} 个待绑定`),
    ].join("");
  }
}

function requirementSummary(requirement = {}) {
  return [
    requirement.realm_stage_min ? `境界 ${requirement.realm_stage_min}` : "",
    requirement.gold_min ? `金币 ${Number(requirement.gold_min)}` : "",
    requirement.alchemy_min ? `炼药经验 ${Number(requirement.alchemy_min)}` : "",
    requirement.fire_min ? `火候 ${Number(requirement.fire_min)}` : "",
    requirement.auction_credit_min ? `拍卖声望 ${Number(requirement.auction_credit_min)}` : "",
  ].filter(Boolean).join(" · ") || "无额外门槛";
}

function emptyItemDefinition() {
  return {
    item_key: "", name: "", category: "token", rarity: "凡品", description: "", icon: "",
    tradable: false, stack_limit: 9999, equipment_slot: "", attack: 0, defense: 0, agility: 0,
    fire_bonus: 0, alchemy_bonus: 0, recipe_config: {}, drop_sources: [], enabled: true, version: 0,
  };
}

function builderItemOptions(selected = "") {
  const rows = state.bootstrap?.content_catalog?.items || [];
  return `<option value="">选择材料</option>${rows.filter((item) => item.enabled !== false).map((item) => `<option value="${escapeHtml(item.key)}" ${item.key === selected ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.key)}</option>`).join("")}`;
}

function builderActionOptions(selected = "") {
  const rows = state.bootstrap?.actions || [];
  return `<option value="">选择行动</option>${rows.map((action) => `<option value="${escapeHtml(action.action_key)}" ${action.action_key === selected ? "selected" : ""}>${escapeHtml(action.name)} · ${escapeHtml(action.action_key)}</option>`).join("")}`;
}

function addRecipeMaterialRow(itemKey = "", quantity = 1) {
  const root = document.querySelector("#item-recipe-materials");
  root.insertAdjacentHTML("beforeend", `<div class="builder-row" data-recipe-material>
    <select data-builder-item-key>${builderItemOptions(itemKey)}</select>
    <input data-builder-quantity type="number" min="1" value="${Number(quantity || 1)}" aria-label="材料数量" />
    <button type="button" class="ghost mini" data-remove-builder-row>移除</button>
  </div>`);
  root.lastElementChild.querySelector("[data-remove-builder-row]").addEventListener("click", (event) => event.currentTarget.closest(".builder-row")?.remove());
}

function addDropSourceRow(source = {}) {
  const root = document.querySelector("#item-drop-sources");
  root.insertAdjacentHTML("beforeend", `<div class="builder-row builder-row--drop" data-drop-source>
    <select data-source-action>${builderActionOptions(source.action_key || "")}</select>
    <label><span>概率%</span><input data-source-chance type="number" min="0" max="100" value="${Number(source.chance ?? 10)}" /></label>
    <label><span>最少</span><input data-source-min type="number" min="1" value="${Number(source.min || 1)}" /></label>
    <label><span>最多</span><input data-source-max type="number" min="1" value="${Number(source.max || source.min || 1)}" /></label>
    <button type="button" class="ghost mini" data-remove-builder-row>移除</button>
  </div>`);
  root.lastElementChild.querySelector("[data-remove-builder-row]").addEventListener("click", (event) => event.currentTarget.closest(".builder-row")?.remove());
}

function fillItemEditor(item = {}) {
  const value = { ...emptyItemDefinition(), ...item };
  document.querySelector("#item-key").value = value.item_key || value.key || "";
  document.querySelector("#item-key").readOnly = Boolean(value.version);
  document.querySelector("#item-name").value = value.name || "";
  document.querySelector("#item-category").value = value.category || "token";
  document.querySelector("#item-rarity").value = value.rarity || "凡品";
  document.querySelector("#item-description").value = value.description || "";
  document.querySelector("#item-icon").value = value.icon || "";
  document.querySelector("#item-tradable").checked = Boolean(value.tradable);
  document.querySelector("#item-stack-limit").value = Number(value.stack_limit || 1);
  document.querySelector("#item-equipment-slot").value = value.equipment_slot || "";
  ["attack", "defense", "agility", "fire_bonus", "alchemy_bonus"].forEach((key) => {
    document.querySelector(`#item-${key.replaceAll("_", "-")}`).value = Number(value[key] || value.equipment?.[key] || 0);
  });
  const recipe = value.recipe_config || {};
  document.querySelector("#item-recipe-enabled").checked = Boolean(recipe.enabled);
  document.querySelector("#item-recipe-type").value = recipe.action_type || (value.category === "gear" ? "craft" : "alchemy");
  document.querySelector("#item-recipe-action-key").value = recipe.action_key || "";
  document.querySelector("#item-recipe-name").value = recipe.name || "";
  document.querySelector("#item-recipe-cooldown").value = Number(recipe.cooldown_seconds || 60);
  document.querySelector("#item-recipe-gold").value = Number(recipe.gold_cost || 0);
  document.querySelector("#item-recipe-output").value = Number(recipe.output_quantity || 1);
  document.querySelector("#item-recipe-sort").value = Number(recipe.sort_order || 75);
  document.querySelector("#item-recipe-requirements").value = JSON.stringify(recipe.requirement_config || {}, null, 2);
  document.querySelector("#item-recipe-materials").innerHTML = "";
  Object.entries(recipe.item_costs || {}).forEach(([key, quantity]) => addRecipeMaterialRow(key, quantity));
  document.querySelector("#item-drop-sources").innerHTML = "";
  (value.drop_sources || []).forEach(addDropSourceRow);
  document.querySelector("#item-enabled").checked = Boolean(value.enabled ?? true);
  document.querySelector("#item-change-note").value = "";
  document.querySelector("#item-editor-title").textContent = value.version ? `编辑：${value.name}` : "新建物品";
  document.querySelector("#item-version-badge").textContent = value.version ? `v${Number(value.version)}` : "未保存";
  document.querySelector("#item-version-list").classList.add("hidden");
  document.querySelector("#equipment-editor-fold").open = value.category === "gear";
  syncEquipmentEditor();
  document.querySelector("#item-editor")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function syncEquipmentEditor() {
  const isGear = document.querySelector("#item-category")?.value === "gear";
  document.querySelector("#equipment-editor-fold")?.classList.toggle("is-disabled", !isGear);
  document.querySelectorAll("#equipment-editor-fold select, #equipment-editor-fold input").forEach((input) => { input.disabled = !isGear; });
  if (!isGear) document.querySelector("#item-equipment-slot").value = "";
}

function itemEditorPayload() {
  const category = document.querySelector("#item-category").value;
  const itemCosts = {};
  document.querySelectorAll("[data-recipe-material]").forEach((row) => {
    const key = row.querySelector("[data-builder-item-key]").value;
    const quantity = Number(row.querySelector("[data-builder-quantity]").value || 0);
    if (key && quantity > 0) itemCosts[key] = quantity;
  });
  const recipeEnabled = document.querySelector("#item-recipe-enabled").checked;
  const dropSources = [...document.querySelectorAll("[data-drop-source]")].map((row) => ({
    action_key: row.querySelector("[data-source-action]").value,
    chance: Number(row.querySelector("[data-source-chance]").value || 0),
    min: Number(row.querySelector("[data-source-min]").value || 1),
    max: Number(row.querySelector("[data-source-max]").value || 1),
  })).filter((source) => source.action_key);
  return {
    item_key: document.querySelector("#item-key").value.trim(),
    name: document.querySelector("#item-name").value.trim(),
    category,
    rarity: document.querySelector("#item-rarity").value.trim() || "凡品",
    description: document.querySelector("#item-description").value.trim(),
    icon: document.querySelector("#item-icon").value.trim(),
    tradable: document.querySelector("#item-tradable").checked,
    stack_limit: Number(document.querySelector("#item-stack-limit").value || 1),
    equipment_slot: category === "gear" ? (document.querySelector("#item-equipment-slot").value || null) : null,
    attack: category === "gear" ? Number(document.querySelector("#item-attack").value || 0) : 0,
    defense: category === "gear" ? Number(document.querySelector("#item-defense").value || 0) : 0,
    agility: category === "gear" ? Number(document.querySelector("#item-agility").value || 0) : 0,
    fire_bonus: category === "gear" ? Number(document.querySelector("#item-fire-bonus").value || 0) : 0,
    alchemy_bonus: category === "gear" ? Number(document.querySelector("#item-alchemy-bonus").value || 0) : 0,
    recipe_config: recipeEnabled ? {
      enabled: true,
      action_type: document.querySelector("#item-recipe-type").value,
      action_key: document.querySelector("#item-recipe-action-key").value.trim(),
      name: document.querySelector("#item-recipe-name").value.trim(),
      cooldown_seconds: Number(document.querySelector("#item-recipe-cooldown").value || 0),
      gold_cost: Number(document.querySelector("#item-recipe-gold").value || 0),
      output_quantity: Number(document.querySelector("#item-recipe-output").value || 1),
      sort_order: Number(document.querySelector("#item-recipe-sort").value || 75),
      item_costs: itemCosts,
      requirement_config: safeJson(document.querySelector("#item-recipe-requirements").value, {}),
      enabled_action: true,
    } : {},
    drop_sources: dropSources,
    enabled: document.querySelector("#item-enabled").checked,
    change_note: document.querySelector("#item-change-note").value.trim(),
  };
}

async function saveItemDefinition() {
  const payload = itemEditorPayload();
  if (!payload.item_key || !payload.name) throw new Error("物品 key 和名称不能为空");
  const item = await request("POST", "/plugins/doupo/admin-api/items", payload);
  await bootstrapAdmin();
  fillItemEditor(item);
  setStatus(`物品已保存为 v${Number(item.version || 1)}`);
}

async function loadItemVersions() {
  const key = document.querySelector("#item-key").value.trim();
  if (!key) throw new Error("请先选择已保存物品");
  const data = await request("GET", `/plugins/doupo/admin-api/items/${encodeURIComponent(key)}/versions`);
  const root = document.querySelector("#item-version-list");
  root.classList.remove("hidden");
  root.innerHTML = (data.items || []).map((version) => `
    <article class="version-item">
      <div><strong>v${Number(version.version)}</strong><p>${escapeHtml(version.change_note || "未填写说明")}</p><small>${escapeHtml(version.created_at || "")}</small></div>
      <button type="button" class="ghost mini" data-item-rollback="${Number(version.version)}">回滚到此版本</button>
    </article>
  `).join("") || `<article class="admin-empty">暂无版本历史</article>`;
  root.querySelectorAll("[data-item-rollback]").forEach((button) => {
    button.addEventListener("click", async () => {
      const version = Number(button.dataset.itemRollback || 0);
      if (!window.confirm(`确认以 v${version} 内容创建一个新的回滚版本？`)) return;
      const item = await request("POST", `/plugins/doupo/admin-api/items/${encodeURIComponent(key)}/rollback`, { version });
      await bootstrapAdmin();
      fillItemEditor(item);
      setStatus(`已回滚并生成 v${Number(item.version)}`);
    });
  });
}

async function archiveItemDefinition() {
  const key = document.querySelector("#item-key").value.trim();
  if (!key) throw new Error("请先选择已保存物品");
  if (!window.confirm("停用后不能继续掉落、制作、发放或穿戴，已拥有物品仍会保留。确认继续？")) return;
  const item = await request("POST", `/plugins/doupo/admin-api/items/${encodeURIComponent(key)}/archive`, {});
  await bootstrapAdmin();
  fillItemEditor(item);
  setStatus("物品已停用并生成新版本");
}

function renderContentCatalog(data = {}) {
  const catalog = data.content_catalog || {};
  const summary = catalog.summary || {};
  const summaryRoot = document.querySelector("#content-summary");
  if (summaryRoot) {
    summaryRoot.innerHTML = [
      metricItem("收录物品", Number(summary.items || 0), `${Number(summary.materials || 0)} 种采集材料`),
      metricItem("制作配方", Number(summary.recipes || 0), `${Number(summary.pills || 0)} 种丹药 · ${Number(summary.gear || 0)} 种装备`),
      metricItem("游历区域", Number(summary.regions || 0), `${Number(summary.events || 0)} 类随机事件`),
      metricItem("管理方式", "行动编辑器", "配方、门槛、掉率与冷却均可调整"),
    ].join("");
  }

  const categorySelect = document.querySelector("#content-category");
  const currentCategory = categorySelect?.value || "";
  if (categorySelect) {
    categorySelect.innerHTML = `<option value="">全部分类</option>${(catalog.categories || []).map((category) => `
      <option value="${escapeHtml(category.key)}">${escapeHtml(category.name)}（${Number(category.item_count || 0)}）</option>
    `).join("")}`;
    categorySelect.value = currentCategory;
  }

  const keyword = String(document.querySelector("#content-search")?.value || "").trim().toLowerCase();
  const category = categorySelect?.value || "";
  const items = (catalog.items || []).filter((item) => {
    if (category && item.category !== category) return false;
    if (!keyword) return true;
    return [item.key, item.name, item.rarity, item.description, ...(item.sources || [])]
      .join(" ")
      .toLowerCase()
      .includes(keyword);
  });
  const itemRoot = document.querySelector("#content-catalog");
  if (itemRoot) {
    itemRoot.innerHTML = items.map((item) => {
      const sources = Array.isArray(item.sources) ? item.sources : [];
      const sourceText = sources.length
        ? `${sources.slice(0, 3).join("；")}${sources.length > 3 ? `；另 ${sources.length - 3} 处` : ""}`
        : "当前仅由后台发放或预留玩法产出";
      return `
        <article class="content-item ${item.enabled === false ? "is-disabled" : ""}">
          <div class="admin-item-title">
            <strong>${itemIconHtml(item.icon, item.name)} ${escapeHtml(item.name)}</strong>
            <span class="tag">${item.enabled === false ? "已停用" : escapeHtml(item.rarity || "凡品")}</span>
          </div>
          <code>${escapeHtml(item.key)}</code>
          <p>${escapeHtml(item.description || "暂无描述")}</p>
          ${item.equipment_slot ? `<small>${escapeHtml(item.equipment_slot_name || item.equipment_slot)} · 攻 ${Number(item.attack || 0)} / 防 ${Number(item.defense || 0)} / 身法 ${Number(item.agility || 0)} / 异火 ${Number(item.fire_bonus || 0)} / 炼药 ${Number(item.alchemy_bonus || 0)}</small>` : ""}
          <small>来源：${escapeHtml(sourceText)}</small>
          <button type="button" class="ghost mini" data-edit-item="${escapeHtml(item.key)}">编辑物品</button>
        </article>
      `;
    }).join("") || `<article class="admin-empty">没有符合筛选条件的物品</article>`;
    itemRoot.querySelectorAll("[data-edit-item]").forEach((button) => {
      button.addEventListener("click", () => {
        const item = (catalog.items || []).find((entry) => entry.key === button.dataset.editItem);
        if (item) fillItemEditor(item);
      });
    });
  }

  const grantSelect = document.querySelector("#grant-item-key");
  if (grantSelect) {
    const selected = grantSelect.value || "";
    grantSelect.innerHTML = `<option value="">选择要发放的物品</option>${(catalog.items || []).filter((item) => item.enabled !== false).map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.name)} · ${escapeHtml(item.rarity)}</option>`).join("")}`;
    grantSelect.value = selected;
  }

  const recipeRoot = document.querySelector("#recipe-catalog");
  if (recipeRoot) {
    recipeRoot.innerHTML = (catalog.recipes || []).map((recipe) => {
      const inputs = (recipe.inputs || []).map((item) => `${item.name} x${Number(item.quantity || 0)}`);
      if (Number(recipe.gold_cost || 0) > 0) inputs.push(`金币 x${Number(recipe.gold_cost)}`);
      const outputs = (recipe.outputs || []).map((item) => {
        const range = Number(item.min || 0) === Number(item.max || 0) ? Number(item.min || 0) : `${Number(item.min || 0)}-${Number(item.max || 0)}`;
        return `${item.name} x${range}${Number(item.chance ?? 100) < 100 ? ` / ${Number(item.chance)}%` : ""}`;
      });
      return `
        <article class="recipe-item ${recipe.enabled === false ? "is-disabled" : ""}">
          <div>
            <div class="admin-item-title"><strong>${escapeHtml(recipe.name)}</strong><span class="tag">${escapeHtml(recipe.action_type_label || recipe.action_type)}</span></div>
            <p>${escapeHtml(inputs.join(" + ") || "无材料")} → ${escapeHtml(outputs.join("、") || "未配置产物")}</p>
            <small>${escapeHtml(requirementSummary(recipe.requirement_config || {}))}</small>
          </div>
          <button type="button" class="ghost mini" data-catalog-edit-action="${escapeHtml(recipe.action_key)}">编辑配方</button>
        </article>
      `;
    }).join("") || `<article class="admin-empty">暂无制作配方</article>`;
    recipeRoot.querySelectorAll("[data-catalog-edit-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = (data.actions || []).find((item) => item.action_key === button.dataset.catalogEditAction);
        if (!action) return;
        fillActionForm(action);
        document.querySelector("#actions")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  const regionRoot = document.querySelector("#region-catalog");
  if (regionRoot) {
    regionRoot.innerHTML = (catalog.regions || []).map((region) => `
      <article class="region-item">
        <div class="admin-item-title"><strong>${escapeHtml(region.name)}</strong><span class="tag">${escapeHtml(region.realm_stage_min)}起</span></div>
        <p>${escapeHtml(region.description || "")}</p>
        <small>推荐战力 ${Number(region.recommended_power || 0)} · 入场 ${Number(region.entry_gold || 0)} 金币 · ${Number(region.max_steps || 0)} 步</small>
        <small>事件：${escapeHtml((region.events || []).join("、"))}</small>
      </article>
    `).join("") || `<article class="admin-empty">暂无游历区域</article>`;
  }
}

function renderPlayerSearch(data = {}) {
  const root = document.querySelector("#player-search-list");
  if (!root) return;
  const search = data.player_search || {};
  const rows = Array.isArray(search.items) ? search.items : [];
  root.innerHTML = rows.map((profile) => `
    <article class="admin-list-item">
      <div>
        <strong>${escapeHtml(profile.display_name || (profile.username ? `@${profile.username}` : `TG ${profile.tg}`))}</strong>
        <p class="section-copy">TG ${escapeHtml(profile.tg)} · ${escapeHtml(profile.realm_stage || "斗之气")} ${Number(profile.realm_stars || 1)} 星 · 战力 ${Number(profile.battle_power || 0)}</p>
      </div>
      <button type="button" class="ghost mini" data-select-player="${escapeHtml(profile.tg)}">选择</button>
    </article>
  `).join("") || `<article class="admin-empty">未找到匹配玩家</article>`;
  root.querySelectorAll("[data-select-player]").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelector("#player-tg").value = button.dataset.selectPlayer || "";
      await loadPlayer();
    });
  });
}

function accountMetricSummary(summary = {}) {
  const root = document.querySelector("#account-summary");
  if (!root) return;
  root.innerHTML = [
    metricItem("账号总数", Number(summary.total || 0)),
    metricItem("已绑定", Number(summary.bound || 0)),
    metricItem("待绑定", Number(summary.unbound || 0)),
    metricItem("已停用", Number(summary.disabled || 0)),
  ].join("");
}

function renderAccounts(data = {}) {
  accountMetricSummary(data.summary || {});
  const root = document.querySelector("#account-list");
  if (!root) return;
  const rows = Array.isArray(data.items) ? data.items : [];
  root.innerHTML = rows.map((account) => `
    <article class="admin-list-item ${account.enabled === false ? "is-disabled" : ""}">
      <div>
        <div class="admin-item-title">
          <strong>${escapeHtml(account.display_name || account.username)}</strong>
          <span class="tag">${account.enabled === false ? "已停用" : account.bound ? "已绑定" : "待绑定"}</span>
        </div>
        <p class="section-copy">账号 ${escapeHtml(account.username)} · ${escapeHtml(account.telegram_label || "未绑定 Telegram")}${account.tg ? ` · TG ${escapeHtml(account.tg)}` : ""}</p>
      </div>
      <div class="admin-item-actions">
        <button type="button" class="ghost mini" data-account-action="state" data-account-id="${account.id}" data-enabled="${account.enabled === false ? "true" : "false"}">${account.enabled === false ? "启用" : "停用"}</button>
        <button type="button" class="ghost mini" data-account-action="revoke" data-account-id="${account.id}">强制下线</button>
        ${account.bound ? `<button type="button" class="ghost mini danger-button" data-account-action="unbind" data-account-id="${account.id}">解绑 TG</button>` : ""}
      </div>
    </article>
  `).join("") || `<article class="admin-empty">没有符合条件的游戏账号</article>`;
  root.querySelectorAll("[data-account-action]").forEach((button) => {
    button.addEventListener("click", () => handleAccountAction(button).catch((error) => setStatus(error.message || String(error))));
  });
}

async function loadAccounts() {
  const params = new URLSearchParams({
    q: document.querySelector("#account-search-q")?.value || "",
    bound: document.querySelector("#account-bound-filter")?.value || "",
    enabled: document.querySelector("#account-enabled-filter")?.value || "",
    page: "1",
    page_size: "30",
  });
  const data = await request("GET", `/plugins/doupo/admin-api/accounts?${params}`);
  renderAccounts(data);
  return data;
}

async function handleAccountAction(button) {
  const accountId = Number(button.dataset.accountId || 0);
  const action = button.dataset.accountAction || "";
  if (!accountId) return;
  if (action === "state") {
    const enabled = button.dataset.enabled === "true";
    if (!window.confirm(`确认${enabled ? "启用" : "停用"}这个游戏账号？`)) return;
    await request("POST", `/plugins/doupo/admin-api/accounts/${accountId}/state`, { enabled });
  } else if (action === "unbind") {
    if (!window.confirm("确认解绑 Telegram？该账号会被强制下线，需要重新绑定后才能游戏。")) return;
    await request("POST", `/plugins/doupo/admin-api/accounts/${accountId}/unbind`, {});
  } else if (action === "revoke") {
    if (!window.confirm("确认让该账号的所有网页登录会话立即失效？")) return;
    await request("POST", `/plugins/doupo/admin-api/accounts/${accountId}/sessions/revoke`, {});
  }
  await loadAccounts();
  setStatus("账号操作已完成");
}

async function bootstrapAdmin(forceToken = false) {
  const previousItemKey = document.querySelector("#item-key")?.value || "";
  const payload = {
    player_query: document.querySelector("#player-search-q")?.value || "",
    player_page: 1,
    player_page_size: 20,
  };
  if (!forceToken && state.initData) payload.init_data = state.initData;
  else if (state.token) payload.token = state.token;
  const data = await request("POST", "/plugins/doupo/admin-api/bootstrap", payload);
  state.bootstrap = data;
  document.querySelector("#setting-enabled").checked = Boolean(data.settings?.exchange_enabled ?? true);
  document.querySelector("#setting-rate").value = Number(data.settings?.exchange_rate || 100);
  document.querySelector("#setting-min-gold").value = Number(data.settings?.min_gold_to_exchange || 100);
  document.querySelector("#setting-daily-gold-cap").value = Number(data.settings?.daily_gold_action_cap ?? 650);
  document.querySelector("#setting-daily-train-limit").value = Number(data.settings?.daily_train_limit ?? 5);
  document.querySelector("#setting-daily-expedition-limit").value = Number(data.settings?.daily_expedition_limit ?? 3);
  document.querySelector("#setting-daily-action-points").value = Number(data.settings?.daily_action_points ?? 12);
  document.querySelector("#setting-daily-douqi-soft-cap").value = Number(data.settings?.daily_douqi_soft_cap ?? 250);
  document.querySelector("#setting-daily-douqi-hard-cap").value = Number(data.settings?.daily_douqi_hard_cap ?? 400);
  document.querySelector("#setting-daily-douqi-overflow").value = Number(data.settings?.daily_douqi_overflow_percent ?? 20);
  document.querySelector("#setting-breakthrough-loss").value = Number(data.settings?.breakthrough_failure_douqi_loss_percent ?? 10);
  document.querySelectorAll("[data-action-limit]").forEach((input) => {
    const key = input.dataset.actionLimit || "";
    input.value = Number(data.settings?.daily_action_limits?.[key] ?? input.value ?? 0);
  });
  document.querySelectorAll("[data-action-point-cost]").forEach((input) => {
    const key = input.dataset.actionPointCost || "";
    input.value = Number(data.settings?.action_point_costs?.[key] ?? input.value ?? 0);
  });
  document.querySelector("#setting-duel-min-stake").value = Number(data.settings?.duel_min_stake || 0);
  document.querySelector("#setting-duel-max-stake").value = Number(data.settings?.duel_max_stake || 500);
  document.querySelector("#setting-duel-prepare-seconds").value = Number(data.settings?.duel_prepare_seconds || 8);
  document.querySelector("#setting-broadcast-enabled").checked = Boolean(data.settings?.broadcast_enabled ?? true);
  document.querySelector("#setting-message-auto-delete").value = Number(data.settings?.message_auto_delete_seconds ?? 180);
  document.querySelector("#setting-expedition-boss-chance").value = Number(data.settings?.expedition_boss_chance ?? 14);
  document.querySelector("#setting-expedition-hidden-chance").value = Number(data.settings?.expedition_hidden_event_chance ?? 8);
  document.querySelector("#setting-sect-transfer-cooldown").value = Number(data.settings?.sect_transfer_cooldown_days ?? 7);
  document.querySelector("#setting-sect-transfer-cost").value = Number(data.settings?.sect_transfer_cost ?? 1500);
  document.querySelector("#setting-sect-transfer-retain").value = Number(data.settings?.sect_transfer_contribution_retain ?? 50);
  document.querySelector("#setting-sect-leave-cost").value = Number(data.settings?.sect_leave_gold_cost ?? 0);
  renderActionList(data);
  renderAdminMetrics(data);
  renderContentCatalog(data);
  renderPlayerSearch(data);
  renderAccounts(data.game_accounts || {});
  if (previousItemKey) {
    const currentItem = data.content_catalog?.items?.find((item) => item.key === previousItemKey);
    if (currentItem) fillItemEditor(currentItem);
  }
  setStatus("后台数据已加载");
}

async function saveSettings() {
  const dailyActionLimits = {};
  document.querySelectorAll("[data-action-limit]").forEach((input) => {
    dailyActionLimits[input.dataset.actionLimit || ""] = Number(input.value || 0);
  });
  const actionPointCosts = {};
  document.querySelectorAll("[data-action-point-cost]").forEach((input) => {
    actionPointCosts[input.dataset.actionPointCost || ""] = Number(input.value || 0);
  });
  const payload = {
    exchange_enabled: document.querySelector("#setting-enabled").checked,
    exchange_rate: Number(document.querySelector("#setting-rate").value || 100),
    min_gold_to_exchange: Number(document.querySelector("#setting-min-gold").value || 100),
    daily_gold_action_cap: Number(document.querySelector("#setting-daily-gold-cap").value || 650),
    daily_train_limit: Number(document.querySelector("#setting-daily-train-limit").value || 5),
    daily_expedition_limit: Number(document.querySelector("#setting-daily-expedition-limit").value || 0),
    daily_action_points: Number(document.querySelector("#setting-daily-action-points").value || 0),
    daily_action_limits: dailyActionLimits,
    action_point_costs: actionPointCosts,
    daily_douqi_soft_cap: Number(document.querySelector("#setting-daily-douqi-soft-cap").value || 0),
    daily_douqi_hard_cap: Number(document.querySelector("#setting-daily-douqi-hard-cap").value || 0),
    daily_douqi_overflow_percent: Number(document.querySelector("#setting-daily-douqi-overflow").value || 0),
    breakthrough_failure_douqi_loss_percent: Number(document.querySelector("#setting-breakthrough-loss").value || 0),
    duel_min_stake: Number(document.querySelector("#setting-duel-min-stake").value || 0),
    duel_max_stake: Number(document.querySelector("#setting-duel-max-stake").value || 500),
    duel_prepare_seconds: Number(document.querySelector("#setting-duel-prepare-seconds").value || 8),
    broadcast_enabled: document.querySelector("#setting-broadcast-enabled").checked,
    message_auto_delete_seconds: Number(document.querySelector("#setting-message-auto-delete").value || 180),
    expedition_boss_chance: Number(document.querySelector("#setting-expedition-boss-chance").value || 0),
    expedition_hidden_event_chance: Number(document.querySelector("#setting-expedition-hidden-chance").value || 0),
    sect_transfer_cooldown_days: Number(document.querySelector("#setting-sect-transfer-cooldown").value || 0),
    sect_transfer_cost: Number(document.querySelector("#setting-sect-transfer-cost").value || 0),
    sect_transfer_contribution_retain: Number(document.querySelector("#setting-sect-transfer-retain").value || 0),
    sect_leave_gold_cost: Number(document.querySelector("#setting-sect-leave-cost").value || 0),
  };
  await request("POST", "/plugins/doupo/admin-api/settings", payload);
  setStatus("设置已保存");
}

async function saveAction() {
  const payload = {
    action_key: document.querySelector("#action-key").value.trim(),
    name: document.querySelector("#action-name").value.trim(),
    action_type: document.querySelector("#action-type").value,
    cooldown_seconds: Number(document.querySelector("#action-cooldown").value || 0),
    description: document.querySelector("#action-desc").value.trim(),
    reward_config: safeJson(document.querySelector("#action-reward").value, {}),
    requirement_config: safeJson(document.querySelector("#action-requirement").value, {}),
    enabled: document.querySelector("#action-enabled").checked,
    sort_order: Number(document.querySelector("#action-sort").value || 0),
  };
  await request("POST", "/plugins/doupo/admin-api/actions", payload);
  await bootstrapAdmin();
  setStatus("行动已保存");
}

async function loadPlayer() {
  const tg = Number(document.querySelector("#player-tg").value || 0);
  if (tg <= 0) throw new Error("请填写正确 TG");
  const detail = await request("GET", `/plugins/doupo/admin-api/players/${tg}`);
  const profile = detail.profile || {};
  const actionPoints = detail.daily_usage?.action_points || {};
  const douqiIncome = detail.daily_usage?.douqi_income || {};
  const equipment = detail.inventory?.equipment || profile.equipment || {};
  const equipmentStats = equipment.stats || {};
  document.querySelector("#player-detail").innerHTML = `
    <div class="admin-detail-grid">
      ${metricItem("玩家", profile.display_name || `TG ${profile.tg || tg}`)}
      ${metricItem("境界", `${profile.realm_stage || "斗之气"} ${Number(profile.realm_stars || 1)} 星`)}
      ${metricItem("斗气", Number(profile.douqi || 0))}
      ${metricItem("金币", Number(profile.gold || 0))}
      ${metricItem("战力", Number(profile.battle_power || 0))}
      ${metricItem("宗门", profile.sect_name || "未加入")}
      ${metricItem("今日行动力", `${Number(actionPoints.used || 0)} / ${Number(actionPoints.limit || 0) || "不限"}`)}
      ${metricItem("今日成长斗气", `${Number(douqiIncome.earned || 0)} / ${Number(douqiIncome.hard_cap || 0) || "不限"}`, `软上限 ${Number(douqiIncome.soft_cap || 0)}`)}
      ${metricItem("已穿戴装备", Number(equipment.equipped_count || 0), `装备战力 +${Number(equipment.battle_power_bonus || 0)}`)}
    </div>
    <div class="admin-equipment-line">攻击 ${Number(equipmentStats.attack || 0)} · 防御 ${Number(equipmentStats.defense || 0)} · 身法 ${Number(equipmentStats.agility || 0)} · 异火 ${Number(equipmentStats.fire_bonus || 0)} · 炼药 ${Number(equipmentStats.alchemy_bonus || 0)}</div>`;
}

async function grantResource() {
  const tg = Number(document.querySelector("#player-tg").value || 0);
  const payload = {
    resource: document.querySelector("#grant-resource").value,
    amount: Number(document.querySelector("#grant-amount").value || 0),
  };
  await request("POST", `/plugins/doupo/admin-api/players/${tg}/resource/grant`, payload);
  await loadPlayer();
  setStatus("资源调整完成");
}

async function grantItem() {
  const tg = Number(document.querySelector("#player-tg").value || 0);
  const itemKey = document.querySelector("#grant-item-key").value;
  const quantity = Number(document.querySelector("#grant-item-amount").value || 0);
  if (tg <= 0) throw new Error("请先选择玩家");
  if (!itemKey || quantity <= 0) throw new Error("请选择物品并填写正确数量");
  await request("POST", `/plugins/doupo/admin-api/players/${tg}/items/grant`, { item_key: itemKey, quantity });
  await loadPlayer();
  setStatus("物品发放完成");
}

async function resetAll() {
  if (!window.confirm("确认清空全部斗破玩家数据？此操作不可撤销，统一游戏账号不会被删除。")) return;
  await request("POST", "/plugins/doupo/admin-api/system/reset-player-data");
  setStatus("已重置全部斗破玩家数据");
}

document.querySelector("#admin-token").value = state.token;
document.querySelector("#admin-login-btn")?.addEventListener("click", async () => {
  state.token = document.querySelector("#admin-token").value.trim();
  localStorage.setItem("doupo_admin_token", state.token);
  await bootstrapAdmin(true);
});
document.querySelector("#save-settings-btn")?.addEventListener("click", () => saveSettings().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#save-action-btn")?.addEventListener("click", () => saveAction().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#load-player-btn")?.addEventListener("click", () => loadPlayer().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#grant-btn")?.addEventListener("click", () => grantResource().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#grant-item-btn")?.addEventListener("click", () => grantItem().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#new-item-btn")?.addEventListener("click", () => fillItemEditor());
document.querySelector("#save-item-btn")?.addEventListener("click", () => saveItemDefinition().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#item-versions-btn")?.addEventListener("click", () => loadItemVersions().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#archive-item-btn")?.addEventListener("click", () => archiveItemDefinition().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#item-category")?.addEventListener("change", syncEquipmentEditor);
document.querySelector("#add-recipe-material-btn")?.addEventListener("click", () => addRecipeMaterialRow());
document.querySelector("#add-drop-source-btn")?.addEventListener("click", () => addDropSourceRow());
document.querySelector("#reset-all-btn")?.addEventListener("click", () => resetAll().catch((e) => setStatus(e.message || String(e))));
document.querySelector("#player-search-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  bootstrapAdmin().catch((error) => setStatus(error.message || String(error)));
});
document.querySelector("#account-search-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  loadAccounts().catch((error) => setStatus(error.message || String(error)));
});
document.querySelector("#content-search")?.addEventListener("input", () => renderContentCatalog(state.bootstrap || {}));
document.querySelector("#content-category")?.addEventListener("change", () => renderContentCatalog(state.bootstrap || {}));
document.querySelectorAll(".admin-nav a").forEach((link) => {
  link.addEventListener("click", (event) => {
    const target = document.querySelector(link.getAttribute("href") || "");
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

if (tg) {
  tg.ready();
  tg.expand();
}
setupBackNavigation();
bootstrapAdmin().catch((e) => setStatus(e.message || String(e)));
