"use strict";

(() => {
  const ARTIFACT_ROLE_OPTIONS = [
    { value: "battle", label: "攻伐" },
    { value: "support", label: "辅修" },
    { value: "guardian", label: "护身" },
    { value: "movement", label: "身法" },
  ];
  const ARTIFACT_SLOT_OPTIONS = [
    { value: "weapon", label: "武器" },
    { value: "helmet", label: "头冠" },
    { value: "clothes", label: "衣服" },
    { value: "boots", label: "鞋" },
    { value: "shield", label: "盾" },
    { value: "accessory", label: "饰品" },
  ];
  const SECT_CAMP_OPTIONS = [
    { value: "orthodox", label: "正道" },
    { value: "heterodox", label: "邪道" },
  ];
  const ITEM_KIND_OPTIONS = [
    { value: "artifact", label: "法宝" },
    { value: "pill", label: "丹药" },
    { value: "talisman", label: "符箓" },
    { value: "material", label: "材料" },
    { value: "recipe", label: "配方" },
    { value: "technique", label: "功法" },
  ];
  const COMBAT_KIND_OPTIONS = [
    { value: "extra_damage", label: "额外伤害" },
    { value: "burn", label: "灼烧" },
    { value: "shield", label: "护盾" },
    { value: "guard", label: "格挡" },
    { value: "dodge", label: "闪避" },
    { value: "heal", label: "回复" },
    { value: "armor_break", label: "破甲" },
  ];
  const FORM_INFO = {
    "artifact-form": { idField: "artifact-id", label: "法宝" },
    "artifact-set-form": { idField: "artifact-set-id", label: "法宝套装" },
    "talisman-form": { idField: "talisman-id", label: "符箓" },
    "pill-form": { idField: "pill-id", label: "丹药" },
    "sect-form": { idField: "sect-id", label: "宗门" },
    "technique-form": { idField: "technique-id", label: "功法" },
    "title-form": { idField: "title-id", label: "称号" },
    "achievement-form": { idField: "achievement-id", label: "成就" },
    "material-form": { idField: "material-id", label: "材料" },
    "recipe-form": { idField: "recipe-id", label: "配方" },
    "scene-form": { idField: "scene-id", label: "场景" },
    "encounter-form": { idField: "encounter-id", label: "奇遇" },
  };

  ADMIN_SECTION_LABELS["artifact-sets"] = "套装";
  if (Array.isArray(PLAYER_EDIT_FIELDS) && !PLAYER_EDIT_FIELDS.includes("technique_capacity")) {
    PLAYER_EDIT_FIELDS.push("technique_capacity");
  }

  function safeRows(key) {
    const rows = state.bundle?.[key];
    return Array.isArray(rows) ? rows : [];
  }

  function findById(rows, id) {
    return (Array.isArray(rows) ? rows : []).find((item) => Number(item?.id || 0) === Number(id || 0)) || null;
  }

  function itemRowsExtended(kind) {
    if (kind === "artifact") return safeRows("artifacts").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
    if (kind === "pill") return safeRows("pills").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
    if (kind === "talisman") return safeRows("talismans").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
    if (kind === "material") return safeRows("materials").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
    if (kind === "technique") return safeRows("techniques").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
    if (kind === "recipe") return safeRows("recipes").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
    return [];
  }

  itemRows = function advancedItemRows(kind) {
    const rows = itemRowsExtended(kind);
    if (rows.length) return rows;
    return [];
  };

  const _baseAdminSectionCount = adminSectionCount;
  adminSectionCount = function advancedAdminSectionCount(key) {
    if (key === "artifact-sets") return safeRows("artifact_sets").length;
    return _baseAdminSectionCount(key);
  };

  function artifactSetRows() {
    return safeRows("artifact_sets").map((item) => ({ value: item.id, label: `${item.id} · ${item.name}` }));
  }

  function editButton(kind, id) {
    return `<button type="button" class="secondary" data-edit-kind="${escapeHtml(kind)}" data-id="${escapeHtml(id)}">编辑</button>`;
  }

  function encounterDispatchButton(id) {
    return `<button type="button" class="secondary" data-encounter-dispatch="${escapeHtml(id)}">投放到群</button>`;
  }

  function focusForm(formId) {
    const form = $(formId);
    if (!form) return;
    const card = form.closest(".fold-card");
    if (card) card.open = true;
    if (typeof window.scrollAdminTargetIntoView === "function") {
      window.scrollAdminTargetIntoView(form);
    } else {
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    pulseTarget(form);
  }

  function formMeta(formId) {
    return FORM_INFO[formId] || null;
  }

  function getFormEditId(formId) {
    const meta = formMeta(formId);
    return meta ? Number($(meta.idField)?.value || 0) : 0;
  }

  function ensureFormBanner(formId) {
    const form = $(formId);
    const meta = formMeta(formId);
    if (!form || !meta || form.querySelector(".form-edit-banner")) return;
    const submitButton = form.querySelector(".form-actions button[type=\"submit\"], .form-actions button:not([type])");
    if (submitButton) {
      submitButton.dataset.defaultText = submitButton.textContent || "";
    }
    const banner = document.createElement("div");
    banner.className = "form-edit-banner hidden wide-field";
    banner.innerHTML = `
      <div>
        <strong data-edit-title>当前为新增模式</strong>
        <p class="muted" data-edit-subtitle>点击下方列表中的“编辑”后，表单会自动回填。</p>
      </div>
      <div class="mini-actions">
        <button type="button" class="secondary" data-reset-form="${formId}">退出编辑</button>
      </div>
    `;
    const firstLabel = [...form.children].find((node) => node.tagName === "LABEL" || node.classList?.contains("wide-field"));
    if (firstLabel) form.insertBefore(banner, firstLabel);
    else form.appendChild(banner);
  }

  function setFormEditMode(formId, row) {
    ensureFormBanner(formId);
    const form = $(formId);
    const meta = formMeta(formId);
    if (!form || !meta) return;
    const banner = form.querySelector(".form-edit-banner");
    const submitButton = form.querySelector(".form-actions button[type=\"submit\"], .form-actions button:not([type])");
    $(meta.idField).value = row?.id || "";
    if (banner) {
      banner.classList.remove("hidden");
      banner.querySelector("[data-edit-title]").textContent = `正在编辑${meta.label}：${row?.name || row?.title || "未命名条目"}`;
      banner.querySelector("[data-edit-subtitle]").textContent = "保存后将直接覆盖当前条目，不会新建重复配置。";
    }
    if (submitButton) {
      submitButton.textContent = `保存${meta.label}`;
    }
    window.__xiuxianAdvancedForm = formId;
  }

  function clearFormEditMode(formId, reset = false) {
    const form = $(formId);
    const meta = formMeta(formId);
    if (!form || !meta) return;
    ensureFormBanner(formId);
    const banner = form.querySelector(".form-edit-banner");
    const submitButton = form.querySelector(".form-actions button[type=\"submit\"], .form-actions button:not([type])");
    if ($(meta.idField)) $(meta.idField).value = "";
    if (banner) {
      banner.classList.add("hidden");
      banner.querySelector("[data-edit-title]").textContent = "当前为新增模式";
      banner.querySelector("[data-edit-subtitle]").textContent = "点击下方列表中的“编辑”后，表单会自动回填。";
    }
    if (submitButton) {
      submitButton.textContent = submitButton.dataset.defaultText || submitButton.textContent;
    }
    if (reset) form.reset();
  }

  function createAdvancedBuilderRow(content) {
    const wrapper = document.createElement("div");
    wrapper.className = "builder-row";
    wrapper.innerHTML = `${content}<div class="builder-row-actions"><button type="button" class="ghost" data-remove-row>删除</button></div>`;
    wrapper.querySelector("[data-remove-row]")?.addEventListener("click", () => wrapper.remove());
    return wrapper;
  }

  function ensureCombatBuilder(prefix, title) {
    const raw = $(`${prefix}-combat-config`);
    if (!raw || raw.dataset.builderReady === "1") return;
    const hostLabel = raw.closest("label");
    raw.classList.add("raw-json-hidden");
    const wrapper = document.createElement("div");
    wrapper.className = "wide-field builder-section";
    wrapper.innerHTML = `
      <div class="builder-head">
        <strong>${escapeHtml(title)}</strong>
        <button type="button" class="secondary" data-combat-add="${prefix}">新增法术</button>
      </div>
      <label class="wide-field">
        起手文案
        <input id="${prefix}-combat-opening" type="text" placeholder="例如：灵气鼓荡，先手起势。">
      </label>
      <p class="field-note">主动 / 被动、伤害、护盾、闪避、破甲、持续回合与真元消耗都在这里配置。</p>
      <div id="${prefix}-combat-rows" class="builder-list"></div>
    `;
    hostLabel?.insertAdjacentElement("afterend", wrapper);
    hostLabel?.classList.add("hidden");
    wrapper.querySelector(`[data-combat-add="${prefix}"]`)?.addEventListener("click", () => {
      addCombatRow(prefix);
      syncCombatConfig(prefix);
    });
    wrapper.addEventListener("input", () => syncCombatConfig(prefix));
    wrapper.addEventListener("change", () => syncCombatConfig(prefix));
    raw.dataset.builderReady = "1";
  }

  function addCombatRow(prefix, data = {}) {
    const rows = $(`${prefix}-combat-rows`);
    if (!rows) return;
    const wrapper = createAdvancedBuilderRow(`
      <div class="builder-grid builder-grid--wide">
        <label>分类
          <select data-combat-group>
            <option value="skills" ${(data.group || "skills") === "skills" ? "selected" : ""}>主动</option>
            <option value="passives" ${(data.group || "") === "passives" ? "selected" : ""}>被动</option>
          </select>
        </label>
        <label>名称
          <input data-combat-name type="text" value="${escapeHtml(data.name || "")}" placeholder="例如：离火斩">
        </label>
        <label>效果类型
          <select data-combat-kind>${COMBAT_KIND_OPTIONS.map((item) => `<option value="${item.value}" ${(data.kind || "extra_damage") === item.value ? "selected" : ""}>${item.label}</option>`).join("")}</select>
        </label>
        <label>触发率（%）
          <input data-combat-chance type="number" min="0" max="100" value="${escapeHtml(data.chance ?? 20)}">
        </label>
        <label>固定伤害
          <input data-combat-flat-damage type="number" value="${escapeHtml(data.flat_damage ?? 0)}">
        </label>
        <label>倍率（%）
          <input data-combat-ratio type="number" value="${escapeHtml(data.ratio_percent ?? 0)}">
        </label>
        <label>护盾
          <input data-combat-shield type="number" value="${escapeHtml(data.flat_shield ?? 0)}">
        </label>
        <label>治疗
          <input data-combat-heal type="number" value="${escapeHtml(data.flat_heal ?? 0)}">
        </label>
        <label>闪避
          <input data-combat-dodge type="number" value="${escapeHtml(data.dodge_bonus ?? 0)}">
        </label>
        <label>破甲 / 减防（%）
          <input data-combat-defense-ratio type="number" value="${escapeHtml(data.defense_ratio_percent ?? 0)}">
        </label>
        <label>持续回合
          <input data-combat-duration type="number" min="0" value="${escapeHtml(data.duration ?? 0)}">
        </label>
        <label>真元消耗
          <input data-combat-cost type="number" min="0" value="${escapeHtml(data.cost_true_yuan ?? 0)}">
        </label>
      </div>
      <label class="wide-field">战斗文案
        <textarea data-combat-text rows="2" placeholder="技能触发时显示的文字">${escapeHtml(data.text || "")}</textarea>
      </label>
    `);
    rows.appendChild(wrapper);
  }

  function collectCombatConfig(prefix) {
    const opening = $(`${prefix}-combat-opening`)?.value?.trim() || "";
    const result = {};
    const skills = [];
    const passives = [];
    document.querySelectorAll(`#${prefix}-combat-rows .builder-row`).forEach((row) => {
      const payload = {
        name: row.querySelector("[data-combat-name]")?.value?.trim() || "",
        kind: row.querySelector("[data-combat-kind]")?.value || "extra_damage",
        chance: Number(row.querySelector("[data-combat-chance]")?.value || 0),
        flat_damage: Number(row.querySelector("[data-combat-flat-damage]")?.value || 0),
        ratio_percent: Number(row.querySelector("[data-combat-ratio]")?.value || 0),
        flat_shield: Number(row.querySelector("[data-combat-shield]")?.value || 0),
        flat_heal: Number(row.querySelector("[data-combat-heal]")?.value || 0),
        dodge_bonus: Number(row.querySelector("[data-combat-dodge]")?.value || 0),
        defense_ratio_percent: Number(row.querySelector("[data-combat-defense-ratio]")?.value || 0),
        duration: Number(row.querySelector("[data-combat-duration]")?.value || 0),
        cost_true_yuan: Number(row.querySelector("[data-combat-cost]")?.value || 0),
        text: row.querySelector("[data-combat-text]")?.value?.trim() || "",
      };
      const normalized = Object.fromEntries(Object.entries(payload).filter(([key, value]) => {
        if (key === "name" || key === "kind") return Boolean(value);
        if (key === "text") return Boolean(value);
        return Number(value || 0) !== 0;
      }));
      if (!normalized.name && !normalized.text) return;
      if ((row.querySelector("[data-combat-group]")?.value || "skills") === "passives") passives.push(normalized);
      else skills.push(normalized);
    });
    if (opening) result.opening_text = opening;
    if (skills.length) result.skills = skills;
    if (passives.length) result.passives = passives;
    return result;
  }

  function syncCombatConfig(prefix) {
    const raw = $(`${prefix}-combat-config`);
    if (!raw) return;
    raw.value = JSON.stringify(collectCombatConfig(prefix), null, 2);
  }

  function applyCombatConfig(prefix, config = {}) {
    ensureCombatBuilder(prefix, "");
    const rows = $(`${prefix}-combat-rows`);
    if (!rows) return;
    rows.innerHTML = "";
    $(`${prefix}-combat-opening`).value = config?.opening_text || "";
    (Array.isArray(config?.skills) ? config.skills : []).forEach((item) => addCombatRow(prefix, { ...item, group: "skills" }));
    (Array.isArray(config?.passives) ? config.passives : []).forEach((item) => addCombatRow(prefix, { ...item, group: "passives" }));
    syncCombatConfig(prefix);
  }

  function resetCombatConfig(prefix) {
    const rows = $(`${prefix}-combat-rows`);
    if (rows) rows.innerHTML = "";
    if ($(`${prefix}-combat-opening`)) $(`${prefix}-combat-opening`).value = "";
    syncCombatConfig(prefix);
  }

  function ensureAchievementRewardBuilder() {
    const raw = $("achievement-reward-config");
    if (!raw || raw.dataset.builderReady === "1") return;
    const hostLabel = raw.closest("label");
    raw.classList.add("raw-json-hidden");
    const wrapper = document.createElement("div");
    wrapper.className = "wide-field builder-section";
    wrapper.innerHTML = `
      <div class="builder-head">
        <strong>奖励配置</strong>
        <div class="mini-actions">
          <button type="button" class="secondary" id="achievement-title-reward-add">新增称号奖励</button>
          <button type="button" class="secondary" id="achievement-item-reward-add">新增物品奖励</button>
        </div>
      </div>
      <div class="builder-grid builder-grid--wide">
        <label>奖励灵石
          <input id="achievement-reward-stone" type="number" min="0" value="0">
        </label>
        <label>奖励修为
          <input id="achievement-reward-cultivation" type="number" min="0" value="0">
        </label>
      </div>
      <label class="wide-field">附加提示
        <textarea id="achievement-reward-message" rows="2" placeholder="例如：你自此名动群雄。"></textarea>
      </label>
      <div class="builder-section">
        <div class="builder-head">
          <strong>称号奖励</strong>
          <span class="field-note">支持发放多个称号，达到成就后统一解锁。</span>
        </div>
        <div id="achievement-reward-title-rows" class="builder-list"></div>
      </div>
      <div class="builder-section">
        <div class="builder-head">
          <strong>物品奖励</strong>
          <span class="field-note">法宝、丹药、符箓、材料、配方、功法都能直接配置。</span>
        </div>
        <div id="achievement-reward-item-rows" class="builder-list"></div>
      </div>
    `;
    hostLabel?.insertAdjacentElement("afterend", wrapper);
    hostLabel?.classList.add("hidden");
    $("achievement-title-reward-add")?.addEventListener("click", () => {
      addAchievementTitleRewardRow();
      syncAchievementRewardConfig();
    });
    $("achievement-item-reward-add")?.addEventListener("click", () => {
      addAchievementItemRewardRow();
      syncAchievementRewardConfig();
    });
    wrapper.addEventListener("input", syncAchievementRewardConfig);
    wrapper.addEventListener("change", syncAchievementRewardConfig);
    raw.dataset.builderReady = "1";
  }

  function addAchievementTitleRewardRow(titleId = "") {
    const rows = $("achievement-reward-title-rows");
    if (!rows) return;
    rows.appendChild(createAdvancedBuilderRow(`
      <label>奖励称号
        <select data-achievement-title-id></select>
      </label>
    `));
    const target = rows.lastElementChild?.querySelector("[data-achievement-title-id]");
    setOptions(target, titleRows(), titleId, "请选择称号");
  }

  function addAchievementItemRewardRow(data = {}) {
    const rows = $("achievement-reward-item-rows");
    if (!rows) return;
    const wrapper = createAdvancedBuilderRow(`
      <div class="builder-grid builder-grid--wide">
        <label>奖励类型
          <select data-achievement-item-kind>${ITEM_KIND_OPTIONS.map((item) => `<option value="${item.value}" ${(data.kind || "pill") === item.value ? "selected" : ""}>${item.label}</option>`).join("")}</select>
        </label>
        <label>奖励物品
          <select data-achievement-item-ref></select>
        </label>
        <label>数量
          <input data-achievement-item-quantity type="number" min="1" value="${escapeHtml(data.quantity || 1)}">
        </label>
      </div>
    `);
    rows.appendChild(wrapper);
    const kindNode = wrapper.querySelector("[data-achievement-item-kind]");
    const refNode = wrapper.querySelector("[data-achievement-item-ref]");
    const sync = () => setOptions(refNode, itemRows(kindNode.value || "pill"), data.ref_id || data.item_ref_id || "", "请选择物品");
    kindNode.addEventListener("change", sync);
    sync();
  }

  function collectAchievementRewardConfig() {
    const reward = {};
    const stone = Number($("achievement-reward-stone")?.value || 0);
    const cultivation = Number($("achievement-reward-cultivation")?.value || 0);
    const message = $("achievement-reward-message")?.value?.trim() || "";
    const titles = [...document.querySelectorAll("#achievement-reward-title-rows [data-achievement-title-id]")]
      .map((node) => Number(node.value || 0))
      .filter((value) => value > 0);
    const items = [...document.querySelectorAll("#achievement-reward-item-rows .builder-row")].map((row) => ({
      kind: row.querySelector("[data-achievement-item-kind]")?.value || "pill",
      ref_id: Number(row.querySelector("[data-achievement-item-ref]")?.value || 0),
      quantity: Number(row.querySelector("[data-achievement-item-quantity]")?.value || 1),
    })).filter((item) => item.ref_id > 0 && item.quantity > 0);
    if (stone > 0) reward.spiritual_stone = stone;
    if (cultivation > 0) reward.cultivation = cultivation;
    if (message) reward.message = message;
    if (titles.length) reward.titles = titles;
    if (items.length) reward.items = items;
    return reward;
  }

  function syncAchievementRewardConfig() {
    const raw = $("achievement-reward-config");
    if (!raw) return;
    raw.value = JSON.stringify(collectAchievementRewardConfig(), null, 2);
  }

  function applyAchievementRewardConfig(config = {}) {
    ensureAchievementRewardBuilder();
    $("achievement-reward-stone").value = Number(config?.spiritual_stone || 0);
    $("achievement-reward-cultivation").value = Number(config?.cultivation || 0);
    $("achievement-reward-message").value = config?.message || "";
    $("achievement-reward-title-rows").innerHTML = "";
    $("achievement-reward-item-rows").innerHTML = "";
    (Array.isArray(config?.titles) ? config.titles : []).forEach((id) => addAchievementTitleRewardRow(id));
    (Array.isArray(config?.items) ? config.items : []).forEach((item) => addAchievementItemRewardRow(item));
    syncAchievementRewardConfig();
  }

  function resetAchievementRewardConfig() {
    ensureAchievementRewardBuilder();
    $("achievement-reward-stone").value = "0";
    $("achievement-reward-cultivation").value = "0";
    $("achievement-reward-message").value = "";
    $("achievement-reward-title-rows").innerHTML = "";
    $("achievement-reward-item-rows").innerHTML = "";
    syncAchievementRewardConfig();
  }

  addSceneEventRow = function advancedAddSceneEventRow(data = {}) {
    const rows = $("scene-event-rows");
    if (!rows) return;
    const typeOptions = SCENE_EVENT_TYPES.map(([value, label]) => `<option value="${value}" ${(data.event_type || "encounter") === value ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
    const wrapper = createAdvancedBuilderRow(`
      <div class="builder-grid builder-grid--wide">
        <label>事件名称
          <input data-scene-event-name type="text" value="${escapeHtml(data.name || "")}" placeholder="例如：残碑拓影">
        </label>
        <label>事件类型
          <select data-scene-event-type>${typeOptions}</select>
        </label>
        <label>权重
          <input data-scene-event-weight type="number" min="1" value="${escapeHtml(data.weight || 1)}">
        </label>
        <label>灵石奖励最小值
          <input data-scene-stone-bonus-min type="number" min="0" value="${escapeHtml(data.stone_bonus_min || 0)}">
        </label>
        <label>灵石奖励最大值
          <input data-scene-stone-bonus-max type="number" min="0" value="${escapeHtml(data.stone_bonus_max || 0)}">
        </label>
        <label>灵石损失最小值
          <input data-scene-stone-loss-min type="number" min="0" value="${escapeHtml(data.stone_loss_min || 0)}">
        </label>
        <label>灵石损失最大值
          <input data-scene-stone-loss-max type="number" min="0" value="${escapeHtml(data.stone_loss_max || 0)}">
        </label>
        <label>额外奖励类型
          <select data-scene-bonus-kind>
            <option value="" ${(data.bonus_reward_kind || "") === "" ? "selected" : ""}>无</option>
            ${ITEM_KIND_OPTIONS.map((item) => `<option value="${item.value}" ${(data.bonus_reward_kind || "") === item.value ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </label>
        <label>额外奖励
          <select data-scene-bonus-ref></select>
        </label>
        <label>额外奖励最小数量
          <input data-scene-bonus-min type="number" min="1" value="${escapeHtml(data.bonus_quantity_min || 1)}">
        </label>
        <label>额外奖励最大数量
          <input data-scene-bonus-max type="number" min="1" value="${escapeHtml(data.bonus_quantity_max || 1)}">
        </label>
        <label>额外奖励触发率（%）
          <input data-scene-bonus-chance type="number" min="0" max="100" value="${escapeHtml(data.bonus_chance || 0)}">
        </label>
      </div>
      <label class="wide-field">事件描述
        <textarea data-scene-event-description rows="2" placeholder="例如：石壁上浮现旧日符纹，你急忙拓下一页残纸。">${escapeHtml(data.description || "")}</textarea>
      </label>
    `);
    rows.appendChild(wrapper);
    const kindNode = wrapper.querySelector("[data-scene-bonus-kind]");
    const refNode = wrapper.querySelector("[data-scene-bonus-ref]");
    const sync = () => setOptions(refNode, itemRows(kindNode.value || "material"), data.bonus_reward_ref_id || "", "无");
    kindNode.addEventListener("change", sync);
    sync();
  };

  addSceneDropRow = function advancedAddSceneDropRow(data = {}) {
    const rows = $("scene-drop-rows");
    if (!rows) return;
    const rewardKind = data.reward_kind || "material";
    const wrapper = createAdvancedBuilderRow(`
      <div class="builder-grid builder-grid--wide">
        <label>掉落类型
          <select data-drop-kind>${ITEM_KIND_OPTIONS.map((item) => `<option value="${item.value}" ${rewardKind === item.value ? "selected" : ""}>${item.label}</option>`).join("")}</select>
        </label>
        <label>对应物品
          <select data-drop-ref></select>
        </label>
        <label>最小数量
          <input data-drop-min type="number" min="1" value="${escapeHtml(data.quantity_min || 1)}">
        </label>
        <label>最大数量
          <input data-drop-max type="number" min="1" value="${escapeHtml(data.quantity_max || 1)}">
        </label>
        <label>权重
          <input data-drop-weight type="number" min="1" value="${escapeHtml(data.weight || 1)}">
        </label>
        <label>额外灵石
          <input data-drop-stone type="number" min="0" value="${escapeHtml(data.stone_reward || 0)}">
        </label>
      </div>
      <label class="wide-field">触发文本
        <input data-drop-event type="text" value="${escapeHtml(data.event_text || "")}" placeholder="例如：你在废墟深处捡到一块玄铁。">
      </label>
    `);
    rows.appendChild(wrapper);
    const kindNode = wrapper.querySelector("[data-drop-kind]");
    const refNode = wrapper.querySelector("[data-drop-ref]");
    const sync = () => setOptions(refNode, itemRows(kindNode.value || "material"), data.reward_ref_id || "", "无");
    kindNode.addEventListener("change", sync);
    sync();
  };

  function resetSceneBuilders() {
    if ($("scene-event-rows")) $("scene-event-rows").innerHTML = "";
    if ($("scene-drop-rows")) $("scene-drop-rows").innerHTML = "";
    addSceneEventRow();
    addSceneDropRow();
  }

  function resetSectRoles() {
    if ($("sect-role-rows")) $("sect-role-rows").innerHTML = "";
    ROLE_PRESETS.forEach(([role_key, role_name]) => addSectRoleRow({ role_key, role_name }));
  }

  const _baseSyncSelects = syncSelects;
  syncSelects = function advancedSyncSelects() {
    _baseSyncSelects();
    setOptions($("artifact-role"), ARTIFACT_ROLE_OPTIONS, $("artifact-role")?.value || "battle", null);
    setOptions($("artifact-slot"), ARTIFACT_SLOT_OPTIONS, $("artifact-slot")?.value || "weapon", null);
    setOptions($("artifact-set-id"), [{ value: "", label: "无套装" }, ...artifactSetRows()], $("artifact-set-id")?.value || "");
    setOptions($("sect-camp"), SECT_CAMP_OPTIONS, $("sect-camp")?.value || "orthodox", null);
    document.querySelectorAll("#scene-event-rows .builder-row").forEach((row) => {
      const kindNode = row.querySelector("[data-scene-bonus-kind]");
      const refNode = row.querySelector("[data-scene-bonus-ref]");
      if (kindNode && refNode) {
        setOptions(refNode, itemRows(kindNode.value || "material"), refNode.value, "无");
      }
    });
    document.querySelectorAll("#scene-drop-rows .builder-row").forEach((row) => {
      const kindNode = row.querySelector("[data-drop-kind]");
      const refNode = row.querySelector("[data-drop-ref]");
      if (kindNode && refNode) {
        setOptions(refNode, itemRows(kindNode.value || "material"), refNode.value, "无");
      }
    });
    document.querySelectorAll("#achievement-reward-title-rows [data-achievement-title-id]").forEach((node) => {
      setOptions(node, titleRows(), node.value, "请选择称号");
    });
    document.querySelectorAll("#achievement-reward-item-rows .builder-row").forEach((row) => {
      const kindNode = row.querySelector("[data-achievement-item-kind]");
      const refNode = row.querySelector("[data-achievement-item-ref]");
      if (kindNode && refNode) {
        setOptions(refNode, itemRows(kindNode.value || "pill"), refNode.value, "请选择物品");
      }
    });
    syncCombatConfig("artifact");
    syncCombatConfig("talisman");
    syncCombatConfig("technique");
    syncAchievementRewardConfig();
  };

  function enrichArtifactBody(body) {
    return {
      ...body,
      artifact_role: $("artifact-role")?.value || "battle",
      equip_slot: $("artifact-slot")?.value || "weapon",
      artifact_set_id: Number($("artifact-set-id")?.value || 0) || null,
      enabled: $("artifact-enabled")?.checked ?? true,
      combat_config: collectCombatConfig("artifact"),
    };
  }

  function enrichTalismanBody(body) {
    return {
      ...body,
      effect_uses: Number($("talisman-effect-uses")?.value || 1),
      enabled: $("talisman-enabled")?.checked ?? true,
      combat_config: collectCombatConfig("talisman"),
    };
  }

  function enrichPillBody(body) {
    return {
      ...body,
      rarity: $("pill-rarity")?.value || body?.rarity || "凡品",
      enabled: $("pill-enabled")?.checked ?? true,
    };
  }

  function enrichTechniqueBody(body) {
    return {
      ...body,
      enabled: $("technique-enabled")?.checked ?? true,
      combat_config: collectCombatConfig("technique"),
    };
  }

  function enrichSectBody(body) {
    return {
      ...body,
      camp: $("sect-camp")?.value || "orthodox",
      min_bone: Number($("sect-bone")?.value || 0),
      min_comprehension: Number($("sect-comprehension")?.value || 0),
      min_divine_sense: Number($("sect-divine-sense")?.value || 0),
      min_fortune: Number($("sect-fortune")?.value || 0),
      min_willpower: Number($("sect-willpower")?.value || 0),
      min_charisma: Number($("sect-charisma")?.value || 0),
      min_karma: Number($("sect-karma")?.value || 0),
      min_body_movement: Number($("sect-min-body-movement")?.value || 0),
      min_combat_power: Number($("sect-min-combat-power")?.value || 0),
      attack_bonus: Number($("sect-attack")?.value || 0),
      defense_bonus: Number($("sect-defense")?.value || 0),
      duel_rate_bonus: Number($("sect-duel")?.value || 0),
      cultivation_bonus: Number($("sect-cultivation")?.value || 0),
      fortune_bonus: Number($("sect-fortune-bonus")?.value || 0),
      body_movement_bonus: Number($("sect-body-movement")?.value || 0),
      salary_min_stay_days: Number($("sect-salary-stay-days")?.value || 30),
      entry_hint: $("sect-entry-hint")?.value?.trim() || "",
      roles: collectSectRoles(),
    };
  }

  function enrichMaterialBody(body) {
    return {
      ...body,
      enabled: $("material-enabled")?.checked ?? true,
    };
  }

  function enrichAchievementBody(body) {
    return {
      ...body,
      reward_config: collectAchievementRewardConfig(),
    };
  }

  function routeByEditId(path, formId) {
    const id = getFormEditId(formId);
    if (!id) return { method: "POST", path };
    const suffix = path.split("/").pop();
    if (suffix === "title") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/title/${id}` };
    if (suffix === "achievement") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/achievement/${id}` };
    if (suffix === "artifact") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/artifact/${id}` };
    if (suffix === "pill") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/pill/${id}` };
    if (suffix === "talisman") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/talisman/${id}` };
    if (suffix === "technique") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/technique/${id}` };
    if (suffix === "sect") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/sect/${id}` };
    if (suffix === "material") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/material/${id}` };
    if (suffix === "recipe") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/recipe/${id}` };
    if (suffix === "scene") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/scene/${id}` };
    if (suffix === "encounter") return { method: "PATCH", path: `/plugins/xiuxian/admin-api/encounter/${id}` };
    return { method: "POST", path };
  }

  const _baseRequest = request;
  request = async function advancedRequest(method, path, body = null) {
    let nextMethod = method;
    let nextPath = path;
    let nextBody = body ? { ...body } : body;
    if (path === "/plugins/xiuxian/admin-api/artifact" && body) {
      window.__xiuxianAdvancedForm = "artifact-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "artifact-form"));
      nextBody = enrichArtifactBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/talisman" && body) {
      window.__xiuxianAdvancedForm = "talisman-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "talisman-form"));
      nextBody = enrichTalismanBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/pill" && body) {
      window.__xiuxianAdvancedForm = "pill-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "pill-form"));
      nextBody = enrichPillBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/technique" && body) {
      window.__xiuxianAdvancedForm = "technique-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "technique-form"));
      nextBody = enrichTechniqueBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/sect" && body) {
      window.__xiuxianAdvancedForm = "sect-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "sect-form"));
      nextBody = enrichSectBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/material" && body) {
      window.__xiuxianAdvancedForm = "material-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "material-form"));
      nextBody = enrichMaterialBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/title" && body) {
      window.__xiuxianAdvancedForm = "title-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "title-form"));
    } else if (path === "/plugins/xiuxian/admin-api/achievement" && body) {
      window.__xiuxianAdvancedForm = "achievement-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "achievement-form"));
      nextBody = enrichAchievementBody(nextBody);
    } else if (path === "/plugins/xiuxian/admin-api/recipe" && body) {
      window.__xiuxianAdvancedForm = "recipe-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "recipe-form"));
    } else if (path === "/plugins/xiuxian/admin-api/scene" && body) {
      window.__xiuxianAdvancedForm = "scene-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "scene-form"));
    } else if (path === "/plugins/xiuxian/admin-api/encounter" && body) {
      window.__xiuxianAdvancedForm = "encounter-form";
      ({ method: nextMethod, path: nextPath } = routeByEditId(path, "encounter-form"));
    }
    return _baseRequest(nextMethod, nextPath, nextBody);
  };

  function resetArtifactForm() {
    $("artifact-form")?.reset();
    clearFormEditMode("artifact-form");
    $("artifact-enabled").checked = true;
    syncSelects();
    resetCombatConfig("artifact");
  }

  function resetArtifactSetForm() {
    $("artifact-set-form")?.reset();
    clearFormEditMode("artifact-set-form");
    $("artifact-set-enabled").checked = true;
    syncSelects();
  }

  function resetTalismanForm() {
    $("talisman-form")?.reset();
    clearFormEditMode("talisman-form");
    $("talisman-enabled").checked = true;
    syncSelects();
    resetCombatConfig("talisman");
  }

  function resetPillForm() {
    $("pill-form")?.reset();
    clearFormEditMode("pill-form");
    $("pill-enabled").checked = true;
    syncSelects();
    updatePillEffectLabel();
  }

  function resetSectForm() {
    $("sect-form")?.reset();
    clearFormEditMode("sect-form");
    if ($("sect-salary-stay-days")) {
      $("sect-salary-stay-days").value = state.bundle?.settings?.sect_salary_min_stay_days ?? 30;
    }
    syncSelects();
    resetSectRoles();
  }

  function resetTechniqueForm() {
    $("technique-form")?.reset();
    clearFormEditMode("technique-form");
    $("technique-enabled").checked = true;
    syncSelects();
    resetCombatConfig("technique");
  }

  function resetTitleForm() {
    $("title-form")?.reset();
    clearFormEditMode("title-form");
    $("title-enabled").checked = true;
    window.refreshTitleColorEditor?.("solid");
  }

  function resetAchievementForm() {
    $("achievement-form")?.reset();
    clearFormEditMode("achievement-form");
    $("achievement-notify-group").checked = true;
    $("achievement-notify-private").checked = true;
    $("achievement-enabled").checked = true;
    resetAchievementRewardConfig();
  }

  function resetMaterialForm() {
    $("material-form")?.reset();
    clearFormEditMode("material-form");
    $("material-enabled").checked = true;
    syncSelects();
  }

  function resetRecipeForm() {
    $("recipe-form")?.reset();
    clearFormEditMode("recipe-form");
    syncSelects();
    if ($("recipe-ingredient-rows")) $("recipe-ingredient-rows").innerHTML = "";
    addRecipeIngredientRow();
  }

  function resetSceneForm() {
    $("scene-form")?.reset();
    clearFormEditMode("scene-form");
    syncSelects();
    resetSceneBuilders();
  }

  function resetEncounterForm() {
    $("encounter-form")?.reset();
    clearFormEditMode("encounter-form");
    if ($("encounter-enabled")) $("encounter-enabled").checked = true;
    if ($("encounter-button-text")) $("encounter-button-text").value = "争抢机缘";
    syncSelects();
  }

  const FORM_RESETTERS = {
    "artifact-form": resetArtifactForm,
    "artifact-set-form": resetArtifactSetForm,
    "talisman-form": resetTalismanForm,
    "pill-form": resetPillForm,
    "sect-form": resetSectForm,
    "technique-form": resetTechniqueForm,
    "title-form": resetTitleForm,
    "achievement-form": resetAchievementForm,
    "material-form": resetMaterialForm,
    "recipe-form": resetRecipeForm,
    "scene-form": resetSceneForm,
    "encounter-form": resetEncounterForm,
  };

  const _baseSubmitAndRefresh = submitAndRefresh;
  submitAndRefresh = async function advancedSubmitAndRefresh(handler, successTitle, successMessage) {
    const formId = window.__xiuxianAdvancedForm || "";
    const meta = formMeta(formId);
    const editing = meta ? getFormEditId(formId) > 0 : false;
    const shouldRewriteCopy = editing && /创建|发布|上架/.test(String(successTitle || ""));
    const finalTitle = shouldRewriteCopy ? "保存成功" : successTitle;
    const finalMessage = shouldRewriteCopy && meta ? `${meta.label}已更新。` : successMessage;
    await _baseSubmitAndRefresh(handler, finalTitle, finalMessage);
    if (shouldRewriteCopy && formId && FORM_RESETTERS[formId]) {
      FORM_RESETTERS[formId]();
    }
    window.__xiuxianAdvancedForm = "";
  };

  function renderArtifactSets() {
    renderStack("artifact-set-list", safeRows("artifact_sets").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(item.required_count || 2)} 件生效</span>
        </div>
        <p>${escapeHtml(item.description || "暂无套装说明")}</p>
        <p>套装加成：${escapeHtml(affixSummary(item))}</p>
        <div class="inline-action-buttons">${editButton("artifact-set", item.id)}${deleteButton("artifact-set", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无套装</strong></article>`);
  }

  function sectRequirementSummary(item = {}) {
    const rows = [];
    if (item.min_realm_stage) rows.push(`${item.min_realm_stage}${item.min_realm_layer || 1}层`);
    if (Number(item.min_stone || 0)) rows.push(`灵石 ${item.min_stone}`);
    if (Number(item.min_bone || 0)) rows.push(`根骨 ${item.min_bone}`);
    if (Number(item.min_comprehension || 0)) rows.push(`悟性 ${item.min_comprehension}`);
    if (Number(item.min_divine_sense || 0)) rows.push(`神识 ${item.min_divine_sense}`);
    if (Number(item.min_fortune || 0)) rows.push(`机缘 ${item.min_fortune}`);
    if (Number(item.min_willpower || 0)) rows.push(`心志 ${item.min_willpower}`);
    if (Number(item.min_charisma || 0)) rows.push(`魅力 ${item.min_charisma}`);
    if (Number(item.min_karma || 0)) rows.push(`因果 ${item.min_karma}`);
    if (Number(item.min_body_movement || 0)) rows.push(`身法 ${item.min_body_movement}`);
    if (Number(item.min_combat_power || 0)) rows.push(`战力 ${item.min_combat_power}`);
    return rows.join(" · ") || "无门槛";
  }

  function sectBonusSummary(item = {}) {
    const rows = [];
    if (Number(item.attack_bonus || 0)) rows.push(`攻击 ${item.attack_bonus}`);
    if (Number(item.defense_bonus || 0)) rows.push(`防御 ${item.defense_bonus}`);
    if (Number(item.duel_rate_bonus || 0)) rows.push(`斗法 ${item.duel_rate_bonus}%`);
    if (Number(item.cultivation_bonus || 0)) rows.push(`修炼 ${item.cultivation_bonus}`);
    if (Number(item.fortune_bonus || 0)) rows.push(`机缘 ${item.fortune_bonus}`);
    if (Number(item.body_movement_bonus || 0)) rows.push(`身法 ${item.body_movement_bonus}`);
    return rows.join(" · ") || "暂无宗门加成";
  }

  const _baseRenderWorld = renderWorld;
  renderWorld = function advancedRenderWorld() {
    _baseRenderWorld();
    const bundle = state.bundle;
    if (!bundle) return;

    renderStack("artifact-list", safeRows("artifacts").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(item.equip_category_label || item.equip_slot_label || item.equip_slot || "武器")}</span>
        </div>
        <p class="quality-line">${qualityBadgeHtml(item.rarity || "凡品", item.quality_color)}<span class="builder-chip">${escapeHtml(item.equip_slot_label || item.equip_slot || "未知槽位")}</span><span class="builder-chip">${escapeHtml(item.artifact_role_label || item.artifact_role || "攻伐")}</span>${item.artifact_set?.name ? `<span class="builder-chip">${escapeHtml(item.artifact_set.name)}</span>` : ""}</p>
        <p>${escapeHtml(affixSummary(item))}</p>
        <p>${escapeHtml(combatConfigSummary(item.combat_config || {}))}</p>
        <div class="inline-action-buttons">${editButton("artifact", item.id)}${deleteButton("artifact", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无法宝</strong></article>`);

    renderArtifactSets();

    renderStack("talisman-list", safeRows("talismans").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color)}
        </div>
        <p>${escapeHtml(affixSummary(item))}</p>
        <p>斗法内最多显化 ${escapeHtml(item.effect_uses || 1)} 次</p>
        <p>${escapeHtml(combatConfigSummary(item.combat_config || {}))}</p>
        <div class="inline-action-buttons">${editButton("talisman", item.id)}${deleteButton("talisman", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无符箓</strong></article>`);

    renderStack("pill-list", safeRows("pills").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color)}
        </div>
        <p>${escapeHtml(item.pill_type_label || item.pill_type)} · ${escapeHtml(item.effect_value_label || "效果值")} ${escapeHtml(item.effect_value)} · 丹毒 ${escapeHtml(item.poison_delta)}</p>
        <p>${escapeHtml(affixSummary(item))}</p>
        <div class="inline-action-buttons">${editButton("pill", item.id)}${deleteButton("pill", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无丹药</strong></article>`);

    renderStack("technique-list", safeRows("techniques").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color)}
        </div>
        <p>${escapeHtml(item.technique_type_label || item.technique_type)} · ${escapeHtml(affixSummary(item))}</p>
        <p>${escapeHtml(combatConfigSummary(item.combat_config || {}))}</p>
        <div class="inline-action-buttons">${editButton("technique", item.id)}${deleteButton("technique", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无功法</strong></article>`);

    renderStack("sect-list", safeRows("sects").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(item.camp_label || item.camp || "正道")}</span>
        </div>
        <p>${escapeHtml(item.description || "暂无宗门简介")}</p>
        <p>门槛：${escapeHtml(sectRequirementSummary(item))}</p>
        <p>加成：${escapeHtml(sectBonusSummary(item))}</p>
        ${item.entry_hint ? `<p>入门提示：${escapeHtml(item.entry_hint)}</p>` : ""}
        <div class="inline-action-buttons">${editButton("sect", item.id)}${deleteButton("sect", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无宗门</strong></article>`);

    renderStack("title-list", safeRows("titles").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${titleColoredNameHtml(item.name, item.color)}</strong>
          <span class="badge badge--normal">${item.enabled ? "启用中" : "已停用"}</span>
        </div>
        <p>${escapeHtml(item.description || "暂无称号描述")}</p>
        <p>${escapeHtml(adminTitleEffectSummary(item))}</p>
        <p class="quality-line">${titleColorBadgeHtml(item.color ? "称号预览" : "默认配色", item.color || "")}<span class="field-note">颜色 ${escapeHtml(summarizeDecorColor(item.color))} · ID ${escapeHtml(item.id)}</span></p>
        <div class="inline-action-buttons">${editButton("title", item.id)}${deleteButton("title", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无称号</strong></article>`);

    renderStack("achievement-list", safeRows("achievements").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">${item.enabled ? "启用中" : "已停用"}</span>
        </div>
        <p>统计项 ${escapeHtml(item.metric_key)} · 目标 ${escapeHtml(item.target_value)} · Key ${escapeHtml(item.achievement_key || "auto")}</p>
        <p>${escapeHtml(item.description || "暂无成就描述")}</p>
        <p>奖励：${escapeHtml(adminRewardSummary(item.reward_config || {}))}</p>
        <div class="inline-action-buttons">${editButton("achievement", item.id)}${deleteButton("achievement", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无成就</strong></article>`);

    renderStack("material-list", safeRows("materials").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          ${qualityBadgeHtml(item.quality_label || item.quality_level, item.quality_color)}
        </div>
        <p>${escapeHtml(item.quality_feature || item.description || "暂无描述")}</p>
        <div class="inline-action-buttons">${editButton("material", item.id)}${deleteButton("material", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无材料</strong></article>`);

    renderStack("recipe-list", safeRows("recipes").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(item.recipe_kind_label || item.recipe_kind)}</span>
        </div>
        <p>产出：${escapeHtml(item.result_item?.name || item.result_kind_label || item.result_kind)} × ${escapeHtml(item.result_quantity)} · 成功率 ${escapeHtml(item.base_success_rate)}%</p>
        <p>材料：${escapeHtml((item.ingredients || []).map((row) => `${row.material?.name || row.material_id}×${row.quantity}`).join("、") || "未配置")}</p>
        <div class="inline-action-buttons">${editButton("recipe", item.id)}${deleteButton("recipe", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无配方</strong></article>`);

    renderStack("scene-list", safeRows("scenes").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">最多 ${escapeHtml(item.max_minutes)} 分钟</span>
        </div>
        <p>${escapeHtml(item.description || "暂无描述")}</p>
        <p>掉落 ${(item.drops || []).length} 项 · 事件 ${(item.event_pool || []).length} 条 · ${escapeHtml(sceneEventOddsSummary(item))}</p>
        <div class="inline-action-buttons">${editButton("scene", item.id)}${deleteButton("scene", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无场景</strong></article>`);

    renderStack("encounter-list", safeRows("encounters").map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(item.weight || 1)} 权重</span>
        </div>
        <p>${escapeHtml(item.description || "暂无描述")}</p>
        <p>奖励：灵石 ${escapeHtml(item.reward_stone_min || 0)}-${escapeHtml(item.reward_stone_max || 0)} · 修为 ${escapeHtml(item.reward_cultivation_min || 0)}-${escapeHtml(item.reward_cultivation_max || 0)}</p>
        <div class="inline-action-buttons">${editButton("encounter", item.id)}${encounterDispatchButton(item.id)}${deleteButton("encounter", item.id)}</div>
      </article>
    `).join("") || `<article class="stack-item"><strong>暂无奇遇</strong></article>`);
  };

  function loadArtifactEdit(id) {
    const item = findById(safeRows("artifacts"), id);
    if (!item) return;
    $("artifact-name").value = item.name || "";
    $("artifact-rarity").value = item.rarity || "凡品";
    $("artifact-type").value = item.artifact_type || "battle";
    $("artifact-role").value = item.artifact_role || "battle";
    $("artifact-slot").value = item.equip_slot || "weapon";
    $("artifact-set-id").value = String(item.artifact_set_id || "");
    window.setAdminInputValue?.("artifact-image", item.image_url || "");
    $("artifact-description").value = item.description || "";
    $("artifact-duel").value = item.duel_rate_bonus || 0;
    $("artifact-cultivation").value = item.cultivation_bonus || 0;
    $("artifact-stage").value = item.min_realm_stage || "";
    $("artifact-layer").value = item.min_realm_layer || 1;
    $("artifact-enabled").checked = item.enabled !== false;
    for (const [key] of ITEM_AFFIX_FIELDS) {
      const payloadKey = `${key.replaceAll("-", "_")}_bonus`;
      if ($(`artifact-${key}`)) $(`artifact-${key}`).value = item[payloadKey] || 0;
    }
    applyCombatConfig("artifact", item.combat_config || {});
    setFormEditMode("artifact-form", item);
    focusForm("artifact-form");
  }

  function loadArtifactSetEdit(id) {
    const item = findById(safeRows("artifact_sets"), id);
    if (!item) return;
    $("artifact-set-name").value = item.name || "";
    $("artifact-set-required-count").value = item.required_count || 2;
    $("artifact-set-description").value = item.description || "";
    $("artifact-set-attack").value = item.attack_bonus || 0;
    $("artifact-set-defense").value = item.defense_bonus || 0;
    $("artifact-set-bone").value = item.bone_bonus || 0;
    $("artifact-set-comprehension").value = item.comprehension_bonus || 0;
    $("artifact-set-divine-sense").value = item.divine_sense_bonus || 0;
    $("artifact-set-fortune").value = item.fortune_bonus || 0;
    $("artifact-set-qi-blood").value = item.qi_blood_bonus || 0;
    $("artifact-set-true-yuan").value = item.true_yuan_bonus || 0;
    $("artifact-set-body-movement").value = item.body_movement_bonus || 0;
    $("artifact-set-duel").value = item.duel_rate_bonus || 0;
    $("artifact-set-cultivation").value = item.cultivation_bonus || 0;
    $("artifact-set-breakthrough").value = item.breakthrough_bonus || 0;
    $("artifact-set-enabled").checked = item.enabled !== false;
    setFormEditMode("artifact-set-form", item);
    focusForm("artifact-set-form");
  }

  function loadTalismanEdit(id) {
    const item = findById(safeRows("talismans"), id);
    if (!item) return;
    $("talisman-name").value = item.name || "";
    $("talisman-rarity").value = item.rarity || "凡品";
    window.setAdminInputValue?.("talisman-image", item.image_url || "");
    $("talisman-description").value = item.description || "";
    $("talisman-duel").value = item.duel_rate_bonus || 0;
    $("talisman-effect-uses").value = item.effect_uses || 1;
    $("talisman-stage").value = item.min_realm_stage || "";
    $("talisman-layer").value = item.min_realm_layer || 1;
    $("talisman-enabled").checked = item.enabled !== false;
    for (const [key] of ITEM_AFFIX_FIELDS) {
      const payloadKey = `${key.replaceAll("-", "_")}_bonus`;
      if ($(`talisman-${key}`)) $(`talisman-${key}`).value = item[payloadKey] || 0;
    }
    applyCombatConfig("talisman", item.combat_config || {});
    setFormEditMode("talisman-form", item);
    focusForm("talisman-form");
  }

  function loadPillEdit(id) {
    const item = findById(safeRows("pills"), id);
    if (!item) return;
    $("pill-name").value = item.name || "";
    $("pill-rarity").value = item.rarity || "凡品";
    $("pill-type").value = item.pill_type || "foundation";
    window.setAdminInputValue?.("pill-image", item.image_url || "");
    $("pill-description").value = item.description || "";
    $("pill-effect").value = item.effect_value || 0;
    $("pill-poison").value = item.poison_delta || 0;
    $("pill-stage").value = item.min_realm_stage || "";
    $("pill-layer").value = item.min_realm_layer || 1;
    $("pill-enabled").checked = item.enabled !== false;
    for (const [key] of ITEM_AFFIX_FIELDS) {
      const payloadKey = `${key.replaceAll("-", "_")}_bonus`;
      if ($(`pill-${key}`)) $(`pill-${key}`).value = item[payloadKey] || 0;
    }
    updatePillEffectLabel();
    setFormEditMode("pill-form", item);
    focusForm("pill-form");
  }

  function loadTechniqueEdit(id) {
    const item = findById(safeRows("techniques"), id);
    if (!item) return;
    $("technique-name").value = item.name || "";
    $("technique-rarity").value = item.rarity || "凡品";
    $("technique-type").value = item.technique_type || "balanced";
    window.setAdminInputValue?.("technique-image", item.image_url || "");
    $("technique-description").value = item.description || "";
    $("technique-duel").value = item.duel_rate_bonus || 0;
    $("technique-cultivation").value = item.cultivation_bonus || 0;
    $("technique-breakthrough").value = item.breakthrough_bonus || 0;
    $("technique-stage").value = item.min_realm_stage || "";
    $("technique-layer").value = item.min_realm_layer || 1;
    $("technique-enabled").checked = item.enabled !== false;
    for (const [key] of ITEM_AFFIX_FIELDS) {
      const payloadKey = `${key.replaceAll("-", "_")}_bonus`;
      if ($(`technique-${key}`)) $(`technique-${key}`).value = item[payloadKey] || 0;
    }
    applyCombatConfig("technique", item.combat_config || {});
    setFormEditMode("technique-form", item);
    focusForm("technique-form");
  }

  function loadSectEdit(id) {
    const item = findById(safeRows("sects"), id);
    if (!item) return;
    $("sect-name").value = item.name || "";
    $("sect-camp").value = item.camp || "orthodox";
    $("sect-stage").value = item.min_realm_stage || "";
    $("sect-layer").value = item.min_realm_layer || 1;
    $("sect-stone").value = item.min_stone || 0;
    $("sect-bone").value = item.min_bone || 0;
    $("sect-comprehension").value = item.min_comprehension || 0;
    $("sect-divine-sense").value = item.min_divine_sense || 0;
    $("sect-fortune").value = item.min_fortune || 0;
    $("sect-willpower").value = item.min_willpower || 0;
    $("sect-charisma").value = item.min_charisma || 0;
    $("sect-karma").value = item.min_karma || 0;
    $("sect-min-body-movement").value = item.min_body_movement || 0;
    $("sect-min-combat-power").value = item.min_combat_power || 0;
    window.setAdminInputValue?.("sect-image", item.image_url || "");
    $("sect-description").value = item.description || "";
    $("sect-attack").value = item.attack_bonus || 0;
    $("sect-defense").value = item.defense_bonus || 0;
    $("sect-duel").value = item.duel_rate_bonus || 0;
    $("sect-cultivation").value = item.cultivation_bonus || 0;
    $("sect-fortune-bonus").value = item.fortune_bonus || 0;
    $("sect-body-movement").value = item.body_movement_bonus || 0;
    $("sect-salary-stay-days").value = item.salary_min_stay_days || (state.bundle?.settings?.sect_salary_min_stay_days ?? 30);
    $("sect-entry-hint").value = item.entry_hint || "";
    $("sect-role-rows").innerHTML = "";
    (item.roles || []).forEach((role) => addSectRoleRow(role));
    setFormEditMode("sect-form", item);
    focusForm("sect-form");
  }

  function loadTitleEdit(id) {
    const item = findById(safeRows("titles"), id);
    if (!item) return;
    $("title-name").value = item.name || "";
    $("title-color").value = item.color || "";
    window.setAdminInputValue?.("title-image", item.image_url || "");
    $("title-enabled").checked = item.enabled !== false;
    $("title-description").value = item.description || "";
    $("title-attack").value = item.attack_bonus || 0;
    $("title-defense").value = item.defense_bonus || 0;
    $("title-bone").value = item.bone_bonus || 0;
    $("title-comprehension").value = item.comprehension_bonus || 0;
    $("title-divine-sense").value = item.divine_sense_bonus || 0;
    $("title-fortune").value = item.fortune_bonus || 0;
    $("title-qi-blood").value = item.qi_blood_bonus || 0;
    $("title-true-yuan").value = item.true_yuan_bonus || 0;
    $("title-body-movement").value = item.body_movement_bonus || 0;
    $("title-duel").value = item.duel_rate_bonus || 0;
    $("title-cultivation").value = item.cultivation_bonus || 0;
    $("title-breakthrough").value = item.breakthrough_bonus || 0;
    window.refreshTitleColorEditor?.();
    setFormEditMode("title-form", item);
    focusForm("title-form");
  }

  function loadAchievementEdit(id) {
    const item = findById(safeRows("achievements"), id);
    if (!item) return;
    $("achievement-key").value = item.achievement_key || "";
    $("achievement-name").value = item.name || "";
    $("achievement-metric-key").value = item.metric_key || "";
    $("achievement-target").value = item.target_value || 1;
    $("achievement-sort").value = item.sort_order || 0;
    $("achievement-notify-group").checked = item.notify_group !== false;
    $("achievement-notify-private").checked = item.notify_private !== false;
    $("achievement-enabled").checked = item.enabled !== false;
    $("achievement-description").value = item.description || "";
    applyAchievementRewardConfig(item.reward_config || {});
    setFormEditMode("achievement-form", item);
    focusForm("achievement-form");
  }

  function loadMaterialEdit(id) {
    const item = findById(safeRows("materials"), id);
    if (!item) return;
    $("material-name").value = item.name || "";
    $("material-quality").value = item.quality_label || item.quality_level || "凡品";
    window.setAdminInputValue?.("material-image", item.image_url || "");
    $("material-description").value = item.description || "";
    $("material-enabled").checked = item.enabled !== false;
    setFormEditMode("material-form", item);
    focusForm("material-form");
  }

  function loadRecipeEdit(id) {
    const item = findById(safeRows("recipes"), id);
    if (!item) return;
    $("recipe-name").value = item.name || "";
    $("recipe-kind").value = item.recipe_kind || "artifact";
    $("recipe-result-kind").value = item.result_kind || "artifact";
    syncSelects();
    $("recipe-result-id").value = item.result_ref_id || "";
    $("recipe-result-quantity").value = item.result_quantity || 1;
    $("recipe-success").value = item.base_success_rate || 60;
    $("recipe-broadcast").checked = item.broadcast_on_success === true;
    $("recipe-ingredient-rows").innerHTML = "";
    (item.ingredients || []).forEach((ingredient) => {
      addRecipeIngredientRow({
        material_id: ingredient.material_id || ingredient.material?.id || 0,
        quantity: ingredient.quantity || 1,
      });
    });
    if (!(item.ingredients || []).length) addRecipeIngredientRow();
    setFormEditMode("recipe-form", item);
    focusForm("recipe-form");
  }

  function loadSceneEdit(id) {
    const item = findById(safeRows("scenes"), id);
    if (!item) return;
    $("scene-name").value = item.name || "";
    $("scene-max-minutes").value = item.max_minutes || 60;
    window.setAdminInputValue?.("scene-image", item.image_url || "");
    $("scene-description").value = item.description || "";
    $("scene-event-rows").innerHTML = "";
    $("scene-drop-rows").innerHTML = "";
    (item.event_pool || []).forEach((event) => addSceneEventRow(event));
    (item.drops || []).forEach((drop) => addSceneDropRow(drop));
    if (!(item.event_pool || []).length) addSceneEventRow();
    if (!(item.drops || []).length) addSceneDropRow();
    setFormEditMode("scene-form", item);
    focusForm("scene-form");
  }

  function loadEncounterEdit(id) {
    const item = findById(safeRows("encounters"), id);
    if (!item) return;
    $("encounter-name").value = item.name || "";
    $("encounter-description").value = item.description || "";
    window.setAdminInputValue?.("encounter-image", item.image_url || "");
    $("encounter-button-text").value = item.button_text || "争抢机缘";
    $("encounter-success-text").value = item.success_text || "";
    $("encounter-broadcast-text").value = item.broadcast_text || "";
    $("encounter-weight").value = item.weight || 1;
    $("encounter-active-seconds").value = item.active_seconds || 90;
    $("encounter-stage").value = item.min_realm_stage || "";
    $("encounter-layer").value = item.min_realm_layer || 1;
    $("encounter-power").value = item.min_combat_power || 0;
    $("encounter-stone-min").value = item.reward_stone_min || 0;
    $("encounter-stone-max").value = item.reward_stone_max || 0;
    $("encounter-cultivation-min").value = item.reward_cultivation_min || 0;
    $("encounter-cultivation-max").value = item.reward_cultivation_max || 0;
    $("encounter-item-kind").value = item.reward_item_kind || "";
    syncSelects();
    $("encounter-item-id").value = item.reward_item_ref_id || "";
    $("encounter-item-quantity-min").value = item.reward_item_quantity_min || 1;
    $("encounter-item-quantity-max").value = item.reward_item_quantity_max || 1;
    $("encounter-enabled").checked = item.enabled !== false;
    setFormEditMode("encounter-form", item);
    focusForm("encounter-form");
  }

  const EDIT_LOADERS = {
    artifact: loadArtifactEdit,
    "artifact-set": loadArtifactSetEdit,
    talisman: loadTalismanEdit,
    pill: loadPillEdit,
    technique: loadTechniqueEdit,
    sect: loadSectEdit,
    title: loadTitleEdit,
    achievement: loadAchievementEdit,
    material: loadMaterialEdit,
    recipe: loadRecipeEdit,
    scene: loadSceneEdit,
    encounter: loadEncounterEdit,
  };

  function bindArtifactSetSubmit() {
    $("artifact-set-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      window.__xiuxianAdvancedForm = "artifact-set-form";
      const id = getFormEditId("artifact-set-form");
      const payload = {
        name: $("artifact-set-name").value.trim(),
        description: $("artifact-set-description").value.trim(),
        required_count: Number($("artifact-set-required-count").value || 2),
        attack_bonus: Number($("artifact-set-attack").value || 0),
        defense_bonus: Number($("artifact-set-defense").value || 0),
        bone_bonus: Number($("artifact-set-bone").value || 0),
        comprehension_bonus: Number($("artifact-set-comprehension").value || 0),
        divine_sense_bonus: Number($("artifact-set-divine-sense").value || 0),
        fortune_bonus: Number($("artifact-set-fortune").value || 0),
        qi_blood_bonus: Number($("artifact-set-qi-blood").value || 0),
        true_yuan_bonus: Number($("artifact-set-true-yuan").value || 0),
        body_movement_bonus: Number($("artifact-set-body-movement").value || 0),
        duel_rate_bonus: Number($("artifact-set-duel").value || 0),
        cultivation_bonus: Number($("artifact-set-cultivation").value || 0),
        breakthrough_bonus: Number($("artifact-set-breakthrough").value || 0),
        enabled: $("artifact-set-enabled").checked,
      };
      try {
        await submitAndRefresh(
          () => _baseRequest(
            id ? "PATCH" : "POST",
            id ? `/plugins/xiuxian/admin-api/artifact-set/${id}` : "/plugins/xiuxian/admin-api/artifact-set",
            payload,
          ),
          id ? "保存成功" : "创建成功",
          id ? "套装已更新。" : "套装已保存。",
        );
      } catch (error) {
        await popup("提交失败", String(error.message || error), "error");
      }
    });
  }

  function installAdvancedUi() {
    Object.keys(FORM_INFO).forEach((formId) => ensureFormBanner(formId));
    ensureCombatBuilder("artifact", "法宝战斗配置");
    ensureCombatBuilder("talisman", "符箓战斗配置");
    ensureCombatBuilder("technique", "功法法术配置");
    ensureAchievementRewardBuilder();
    resetSceneBuilders();
    resetSectRoles();
    syncSelects();
    renderWorld();
  }

  document.body.addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-kind]");
    if (edit) {
      const handler = EDIT_LOADERS[edit.dataset.editKind || ""];
      if (handler) {
        handler(Number(edit.dataset.id || 0));
      }
      return;
    }
    const reset = event.target.closest("[data-reset-form]");
    if (reset) {
      const formId = reset.dataset.resetForm || "";
      const resetter = FORM_RESETTERS[formId];
      if (resetter) resetter();
    }
  });

  document.body.addEventListener("focusin", (event) => {
    const form = event.target.closest("form");
    if (form?.id) {
      window.__xiuxianAdvancedForm = form.id;
    }
  });

  bindArtifactSetSubmit();
  installAdvancedUi();
  bootstrapAdmin().catch(() => {});
})();

(() => {
  function accountMetric(label, value) {
    return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
  }

  function renderGameAccountSummary(summary = {}) {
    const root = $("game-account-summary");
    if (!root) return;
    root.innerHTML = [
      accountMetric("账号总数", Number(summary.total || 0)),
      accountMetric("已绑定 TG", Number(summary.bound || 0)),
      accountMetric("待绑定", Number(summary.unbound || 0)),
      accountMetric("已停用", Number(summary.disabled || 0)),
    ].join("");
  }

  function renderGameAccounts(data = {}) {
    renderGameAccountSummary(data.summary || {});
    const root = $("game-account-list");
    if (!root) return;
    const rows = Array.isArray(data.items) ? data.items : [];
    root.innerHTML = rows.map((account) => `
      <article class="stack-item game-account-item ${account.enabled === false ? "is-disabled" : ""}">
        <div class="stack-item-head">
          <div>
            <strong>${escapeHtml(account.display_name || account.username)}</strong>
            <p>账号 ${escapeHtml(account.username)} · ${escapeHtml(account.telegram_label || "未绑定 Telegram")}${account.tg ? ` · TG ${escapeHtml(account.tg)}` : ""}</p>
          </div>
          <span class="tag">${account.enabled === false ? "已停用" : account.bound ? "已绑定" : "待绑定"}</span>
        </div>
        <div class="inline-action-buttons">
          <button type="button" class="secondary" data-game-account-action="state" data-account-id="${account.id}" data-enabled="${account.enabled === false ? "true" : "false"}">${account.enabled === false ? "启用账号" : "停用账号"}</button>
          <button type="button" class="secondary" data-game-account-action="revoke" data-account-id="${account.id}">强制下线</button>
          ${account.bound ? `<button type="button" class="secondary danger-account-action" data-game-account-action="unbind" data-account-id="${account.id}">解绑 TG</button>` : ""}
        </div>
      </article>
    `).join("") || `<article class="stack-item"><strong>没有符合条件的游戏账号</strong></article>`;
    root.querySelectorAll("[data-game-account-action]").forEach((button) => {
      button.addEventListener("click", () => handleGameAccountAction(button));
    });
  }

  async function loadGameAccounts() {
    const params = new URLSearchParams({
      q: $("game-account-search-q")?.value || "",
      bound: $("game-account-bound-filter")?.value || "",
      enabled: $("game-account-enabled-filter")?.value || "",
      page: "1",
      page_size: "30",
    });
    const data = await request("GET", `/plugins/xiuxian/admin-api/accounts?${params}`);
    renderGameAccounts(data);
    return data;
  }

  async function handleGameAccountAction(button) {
    const accountId = Number(button?.dataset.accountId || 0);
    const action = String(button?.dataset.gameAccountAction || "");
    if (!accountId || !action) return;
    try {
      if (action === "state") {
        const enabled = button.dataset.enabled === "true";
        if (!window.confirm(`确认${enabled ? "启用" : "停用"}这个统一游戏账号？`)) return;
        await request("POST", `/plugins/xiuxian/admin-api/accounts/${accountId}/state`, { enabled });
      } else if (action === "unbind") {
        if (!window.confirm("确认解绑 Telegram？账号会被强制下线，重新绑定后才能进入游戏。")) return;
        await request("POST", `/plugins/xiuxian/admin-api/accounts/${accountId}/unbind`, {});
      } else if (action === "revoke") {
        if (!window.confirm("确认让该账号的所有网页登录会话立即失效？")) return;
        await request("POST", `/plugins/xiuxian/admin-api/accounts/${accountId}/sessions/revoke`, {});
      }
      await loadGameAccounts();
      await popup("账号操作完成", "统一游戏账号状态已更新。", "success");
    } catch (error) {
      await popup("账号操作失败", String(error.message || error), "error");
    }
  }

  $("game-account-search-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadGameAccounts().catch((error) => popup("查询失败", String(error.message || error), "error"));
  });
  $("token-form")?.addEventListener("submit", () => {
    window.setTimeout(() => loadGameAccounts().catch(() => {}), 500);
  });
  loadGameAccounts().catch(() => {});
})();
