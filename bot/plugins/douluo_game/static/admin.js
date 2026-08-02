"use strict";

/* ============ 斗罗大陆 管理后台 ============ */

const state = {
  token: localStorage.getItem("douluo_admin_token") || "",
  initData: "",
  telegramInitData: "",
  data: null,
  playerPage: 1,
  playerPageSize: 10,
  playerQuery: "",
};

const SETTINGS_FIELDS = [
  ["exchange_enabled", "兑换开启", "bool"],
  ["exchange_rate", "兑换汇率(碎片/魂币)", "num"],
  ["min_coin_to_exchange", "最低兑换碎片", "num"],
  ["daily_action_points", "每日行动力", "num"],
  ["daily_coin_soft_cap", "魂币软上限", "num"],
  ["daily_coin_hard_cap", "魂币硬上限", "num"],
  ["daily_coin_overflow_percent", "魂币溢出%(%)", "num"],
  ["daily_soul_power_soft_cap", "魂力软上限", "num"],
  ["daily_soul_power_hard_cap", "魂力硬上限", "num"],
  ["soul_power_overflow_percent", "魂力溢出%(%)", "num"],
  ["event_chance_percent", "奇遇概率%(%)", "num"],
  ["wuhun_awaken_coin", "觉醒武魂魂币", "num"],
  ["wuhun_reforge_coin", "重铸武魂魂币", "num"],
  ["wuhun_reforge_cd_hours", "重铸冷却(小时)", "num"],
  ["hunt_absorb_fee", "换环手续费", "num"],
  ["auction_fee_percent", "拍卖手续费%(%)", "num"],
  ["auction_duration_hours", "拍卖时长(小时)", "num"],
  ["duel_min_stake", "斗魂最低押注", "num"],
  ["duel_max_stake", "斗魂最高押注", "num"],
  ["duel_prepare_seconds", "斗魂准备(秒)", "num"],
  ["broadcast_enabled", "群内播报", "bool"],
  ["message_auto_delete_seconds", "消息自动删除(秒)", "num"],
  ["bloodline_awaken_coin", "血脉觉醒魂币", "num"],
  ["bloodline_enhance_coin", "血脉淬炼魂币", "num"],
  ["bloodline_enhance_soul_power", "血脉淬炼魂力", "num"],
  ["prospect_coin_cost", "勘探消耗魂币", "num"],
  ["condense_coin_cost", "魂核凝聚魂币", "num"],
  ["condense_soul_power_cost", "魂核凝聚魂力", "num"],
  ["armor_upgrade_coin", "斗铠升级魂币", "num"],
];

function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return [...document.querySelectorAll(sel)]; }
function setText(sel, value) { const n = qs(sel); if (n) n.textContent = String(value ?? ""); }
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function el(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}
function toast(message, kind = "") {
  const stack = qs("#toast-stack");
  const node = el(`<div class="toast ${kind ? "toast--" + kind : ""}">${esc(message)}</div>`);
  stack.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

function init() {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try { tg.ready(); tg.expand(); } catch (e) { /* ignore */ }
    state.telegramInitData = tg.initData || "";
  }
  const webSession = localStorage.getItem("douluo_web_session_token") || "";
  state.initData = state.telegramInitData || (webSession ? "web_session:" + webSession : "");
  wireEvents();
  bootstrap();
}

function headers() {
  const h = { "Content-Type": "application/json" };
  if (state.token) h["x-admin-token"] = state.token;
  if (state.initData) h["x-telegram-init-data"] = state.initData;
  return h;
}

async function apiPost(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  const raw = await response.text();
  let payload = { code: response.status, data: null };
  try { payload = raw ? JSON.parse(raw) : payload; } catch { /* ignore */ }
  if (!response.ok || payload.code !== 200) {
    const error = new Error(payload.detail || payload.message || "请求失败");
    error.status = response.status;
    throw error;
  }
  return payload.data;
}

async function apiGet(path) {
  const response = await fetch(path, { method: "GET", headers: headers() });
  const raw = await response.text();
  let payload = { code: response.status, data: null };
  try { payload = raw ? JSON.parse(raw) : payload; } catch { /* ignore */ }
  if (!response.ok || payload.code !== 200) {
    const error = new Error(payload.detail || payload.message || "请求失败");
    error.status = response.status;
    throw error;
  }
  return payload.data;
}

async function bootstrap() {
  setText("#admin-status", "正在加载后台数据...");
  try {
    state.data = await apiPost("/plugins/douluo/admin-api/bootstrap", {
      player_page: state.playerPage,
      player_page_size: state.playerPageSize,
      player_query: state.playerQuery || null,
    });
    document.body.classList.remove("auth-locked");
    setText("#admin-status", "身份已验证 · " + new Date().toLocaleString());
    renderOverview(state.data.overview);
    renderPlayers(state.data.players);
    renderSettings(state.data.settings);
    renderItems(state.data.item_definitions);
    loadAccounts().catch((e) => toast(e.message, "error"));
  } catch (e) {
    if (e.status === 401 || e.status === 403) {
      setText("#admin-status", "需要管理员鉴权：" + e.message);
      qs("#admin-token-toggle").classList.remove("hidden");
    } else {
      setText("#admin-status", "加载失败：" + e.message);
    }
    toast(e.message, "error");
  }
}

function renderOverview(overview = {}) {
  const items = [
    ["玩家", overview.player_count || 0],
    ["魂环", overview.ring_count || 0],
    ["在拍", overview.open_listings || 0],
    ["物品定义", overview.item_defs || 0],
  ];
  qs("#admin-overview").replaceChildren(...items.map(([label, value]) =>
    el(`<article><span>${label}</span><strong>${value}</strong></article>`)
  ));
}

function renderPlayers(players = {}) {
  const rows = players.items || [];
  setText("#player-page", `第 ${state.playerPage} 页（共 ${players.total || 0} 人）`);
  const tbody = qs("#player-table tbody");
  tbody.replaceChildren(...rows.map((player) => {
    const actions = `
      <button type="button" class="mini" data-player-edit="${player.tg}">编辑</button>
      <button type="button" class="mini ghost" data-player-grant="${player.tg}">发物</button>
      <button type="button" class="mini ghost" data-player-reset="${player.tg}">重置</button>`;
    return el(`<tr>
      <td>${player.tg}</td>
      <td>${esc(player.display_name || player.username || "")}</td>
      <td>${esc(player.realm_stage || "魂士")}${player.realm_stars || 1}星</td>
      <td>${fmt(player.soul_power)}</td>
      <td>${fmt(player.coin)}</td>
      <td>${fmt(player.battle_power)}</td>
      <td style="white-space:nowrap">${actions}</td>
    </tr>`);
  }).concat(rows.length ? [] : [el('<tr><td colspan="7">无匹配玩家。</td></tr>')]));
}

function fmt(value) {
  const n = Number(value ?? 0);
  return n >= 10000 ? (n / 10000).toFixed(1) + "万" : String(n);
}

function renderSettings(settings = {}) {
  const form = qs("#settings-form");
  form.replaceChildren(...SETTINGS_FIELDS.map(([key, label, type]) => {
    const input = type === "bool"
      ? `<input type="checkbox" data-setting="${key}" ${settings[key] ? "checked" : ""}>`
      : `<input type="number" data-setting="${key}" value="${Number(settings[key] ?? 0)}">`;
    return el(`<label class="field-row">${esc(label)} ${input}</label>`);
  }));
}

function collectSettings() {
  const patch = {};
  qsa("[data-setting]").forEach((input) => {
    const key = input.dataset.setting;
    if (input.type === "checkbox") patch[key] = input.checked;
    else {
      const value = Number(input.value);
      patch[key] = Number.isFinite(value) ? value : 0;
    }
  });
  return patch;
}

function renderItems(defs = []) {
  const tbody = qs("#item-table tbody");
  tbody.replaceChildren(...defs.map((item) => {
    const edit = `<button type="button" class="mini ghost" data-item-edit="${esc(item.item_key)}">编辑</button>`;
    const toggle = item.enabled
      ? `<button type="button" class="mini ghost" data-item-toggle="${esc(item.item_key)}">禁用</button>`
      : `<button type="button" class="mini" data-item-toggle="${esc(item.item_key)}">启用</button>`;
    return el(`<tr>
      <td>${esc(item.item_key)}</td>
      <td>${esc(item.name)}</td>
      <td>${esc(item.category)}</td>
      <td>${esc(item.rarity || "")}</td>
      <td>${item.enabled ? "✅" : "🚫"}</td>
      <td style="white-space:nowrap">${edit} ${toggle}</td>
    </tr>`);
  }).concat(defs.length ? [] : [el('<tr><td colspan="6">暂无物品定义。</td></tr>')]));
}

function accountMetricSummary(summary = {}) {
  const root = qs("#account-summary");
  if (!root) return;
  root.replaceChildren(...[
    ["账号总数", Number(summary.total || 0)],
    ["已绑定", Number(summary.bound || 0)],
    ["待绑定", Number(summary.unbound || 0)],
    ["已停用", Number(summary.disabled || 0)],
  ].map(([label, value]) => el(`<article><span>${label}</span><strong>${value}</strong></article>`)));
}

function renderAccounts(data = {}) {
  accountMetricSummary(data.summary || {});
  const root = qs("#account-list");
  if (!root) return;
  const rows = Array.isArray(data.items) ? data.items : [];
  root.replaceChildren(...rows.map((account) => {
    const tag = account.enabled === false ? "已停用" : account.bound ? "已绑定" : "待绑定";
    const actions = `
      <button type="button" class="ghost mini" data-account-action="state" data-account-id="${account.id}" data-enabled="${account.enabled === false ? "true" : "false"}">${account.enabled === false ? "启用" : "停用"}</button>
      <button type="button" class="ghost mini" data-account-action="revoke" data-account-id="${account.id}">强制下线</button>
      ${account.bound ? `<button type="button" class="ghost mini danger-button" data-account-action="unbind" data-account-id="${account.id}">解绑 TG</button>` : ""}`;
    return el(`<article class="admin-list-item ${account.enabled === false ? "is-disabled" : ""}">
      <div>
        <div class="admin-item-title">
          <strong>${esc(account.display_name || account.username)}</strong>
          <span class="tag">${tag}</span>
        </div>
        <p class="section-copy" style="margin:2px 0 0">账号 ${esc(account.username)} · ${esc(account.telegram_label || "未绑定 Telegram")}${account.tg ? ` · TG ${esc(account.tg)}` : ""}</p>
      </div>
      <div class="admin-item-actions">${actions}</div>
    </article>`);
  }).concat(rows.length ? [] : [el('<article class="admin-empty">没有符合条件的游戏账号</article>')]));
}

async function loadAccounts() {
  const params = new URLSearchParams({
    q: qs("#account-search-q")?.value || "",
    bound: qs("#account-bound-filter")?.value || "",
    enabled: qs("#account-enabled-filter")?.value || "",
    page: "1",
    page_size: "30",
  });
  const data = await apiGet(`/plugins/douluo/admin-api/accounts?${params}`);
  renderAccounts(data);
  return data;
}

async function handleAccountAction(button) {
  const accountId = Number(button.dataset.accountId || 0);
  const action = button.dataset.accountAction || "";
  if (!accountId) return;
  try {
    if (action === "state") {
      const enabled = button.dataset.enabled === "true";
      if (!window.confirm(`确认${enabled ? "启用" : "停用"}这个游戏账号？`)) return;
      await apiPost(`/plugins/douluo/admin-api/accounts/${accountId}/state`, { enabled });
    } else if (action === "unbind") {
      if (!window.confirm("确认解绑 Telegram？该账号会被强制下线，需要重新绑定后才能游戏。")) return;
      await apiPost(`/plugins/douluo/admin-api/accounts/${accountId}/unbind`, {});
    } else if (action === "revoke") {
      if (!window.confirm("确认让该账号的所有网页登录会话立即失效？")) return;
      await apiPost(`/plugins/douluo/admin-api/accounts/${accountId}/sessions/revoke`, {});
    }
    await loadAccounts();
    toast("账号操作已完成", "good");
  } catch (e) { toast(e.message, "error"); }
}

function fillItemEditor(item = {}) {
  qs("#item-editor").classList.remove("hidden");
  qs("#item-key").value = item.item_key || "";
  qs("#item-key").readOnly = Boolean(item.version);
  qs("#item-name").value = item.name || "";
  qs("#item-category").value = item.category || "material";
  qs("#item-rarity").value = item.rarity || "凡品";
  qs("#item-description").value = item.description || "";
  qs("#item-icon").value = item.icon || "";
  qs("#item-equipment-slot").value = item.equipment_slot || "";
  qs("#item-attack").value = Number(item.attack || 0);
  qs("#item-defense").value = Number(item.defense || 0);
  qs("#item-speed").value = Number(item.speed || 0);
  qs("#item-spirit").value = Number(item.spirit || 0);
  qs("#item-trigger-chance").value = item.trigger_chance == null ? 0 : Math.round(Number(item.trigger_chance) * 100);
  qs("#item-skill").value = item.skill || "";
  qs("#item-enabled").checked = Boolean(item.enabled ?? true);
  qs("#item-editor-title").textContent = item.version ? `编辑：${item.name}` : "新建物品";
  qs("#item-version-badge").textContent = item.version ? `v${Number(item.version)}` : "未保存";
  qs("#item-editor").scrollIntoView({ behavior: "smooth", block: "start" });
}

function collectItemForm() {
  const trigger = qs("#item-trigger-chance").value.trim();
  return {
    item_key: qs("#item-key").value.trim(),
    name: qs("#item-name").value.trim(),
    category: qs("#item-category").value,
    rarity: qs("#item-rarity").value.trim() || "凡品",
    description: qs("#item-description").value.trim(),
    icon: qs("#item-icon").value.trim(),
    equipment_slot: qs("#item-equipment-slot").value || null,
    attack: Number(qs("#item-attack").value || 0),
    defense: Number(qs("#item-defense").value || 0),
    speed: Number(qs("#item-speed").value || 0),
    spirit: Number(qs("#item-spirit").value || 0),
    trigger_chance: trigger === "" ? null : Math.min(Math.max(Number(trigger) / 100, 0), 1),
    skill: qs("#item-skill").value.trim() || null,
    enabled: qs("#item-enabled").checked,
  };
}

async function saveItem() {
  const payload = collectItemForm();
  if (!payload.item_key || !payload.name) { toast("物品 key 和名称不能为空", "error"); return; }
  try {
    await apiPost("/plugins/douluo/admin-api/items", payload);
    toast("物品已保存", "good");
    await bootstrap();
  } catch (e) { toast(e.message, "error"); }
}

function newItem() { fillItemEditor(); }

function wireEvents() {
  qs("#admin-refresh").addEventListener("click", bootstrap);
  qs("#admin-token-toggle").addEventListener("click", () => qs("#admin-token-panel").classList.toggle("hidden"));
  qs("#admin-token-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.token = qs("#admin-token-input").value.trim();
    localStorage.setItem("douluo_admin_token", state.token);
    await bootstrap();
  });
  qs("#player-search").addEventListener("click", () => {
    state.playerQuery = qs("#player-query").value.trim();
    state.playerPage = 1;
    bootstrap();
  });
  qs("#player-prev").addEventListener("click", () => {
    if (state.playerPage <= 1) return;
    state.playerPage -= 1;
    bootstrap();
  });
  qs("#player-next").addEventListener("click", () => {
    state.playerPage += 1;
    bootstrap();
  });
  qs("#settings-save").addEventListener("click", async () => {
    try {
      await apiPost("/plugins/douluo/admin-api/settings", collectSettings());
      toast("设置已保存", "good");
      await bootstrap();
    } catch (e) { toast(e.message, "error"); }
  });
  qs("#account-search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadAccounts().catch((e) => toast(e.message, "error"));
  });
  qs("#new-item-btn").addEventListener("click", newItem);
  qs("#save-item-btn").addEventListener("click", saveItem);
  qs("#item-editor-cancel").addEventListener("click", () => qs("#item-editor").classList.add("hidden"));

  document.addEventListener("click", (event) => {
    const editBtn = event.target.closest("[data-player-edit]");
    if (editBtn) { promptPatchPlayer(Number(editBtn.dataset.playerEdit)); return; }
    const grantBtn = event.target.closest("[data-player-grant]");
    if (grantBtn) { promptGrantItem(Number(grantBtn.dataset.playerGrant)); return; }
    const resetBtn = event.target.closest("[data-player-reset]");
    if (resetBtn) { resetPlayer(Number(resetBtn.dataset.playerReset)); return; }
    const toggleBtn = event.target.closest("[data-item-toggle]");
    if (toggleBtn) { toggleItem(toggleBtn.dataset.itemToggle, toggleBtn.textContent.includes("启用")); return; }
    const editItemBtn = event.target.closest("[data-item-edit]");
    if (editItemBtn) {
      const item = (state.data?.item_definitions || []).find((i) => i.item_key === editItemBtn.dataset.itemEdit);
      fillItemEditor(item || { item_key: editItemBtn.dataset.itemEdit });
      return;
    }
    const accountActionBtn = event.target.closest("[data-account-action]");
    if (accountActionBtn) { handleAccountAction(accountActionBtn); return; }
  });
}

async function promptPatchPlayer(tg) {
  const current = (state.data.players.items || []).find((p) => Number(p.tg) === tg);
  const soulPower = window.prompt(`修改 ${tg} 的魂力（当前 ${current?.soul_power || 0}）：`, String(current?.soul_power ?? 0));
  if (soulPower === null) return;
  const coin = window.prompt("修改金魂币：", String(current?.coin ?? 0));
  if (coin === null) return;
  const patch = {};
  const sp = Number(soulPower);
  const c = Number(coin);
  if (Number.isFinite(sp) && sp >= 0) patch.soul_power = sp;
  if (Number.isFinite(c) && c >= 0) patch.coin = c;
  if (!Object.keys(patch).length) { toast("未输入有效数值", "error"); return; }
  try {
    await apiPost(`/plugins/douluo/admin-api/players/${tg}/patch`, patch);
    toast("玩家属性已更新", "good");
    await bootstrap();
  } catch (e) { toast(e.message, "error"); }
}

async function promptGrantItem(tg) {
  const itemKey = window.prompt(`给 ${tg} 发放物品（item_key）：`);
  if (!itemKey) return;
  const quantity = Number(window.prompt("数量：", "1") || 1);
  try {
    await apiPost(`/plugins/douluo/admin-api/players/${tg}/items/grant`, { item_key: itemKey.trim(), quantity });
    toast("物品已发放", "good");
    await bootstrap();
  } catch (e) { toast(e.message, "error"); }
}

async function resetPlayer(tg) {
  if (!window.confirm(`确定重置 ${tg} 的全部斗罗数据吗？此操作不可撤销。`)) return;
  try {
    await apiPost(`/plugins/douluo/admin-api/players/${tg}/reset`, {});
    toast("玩家已重置", "good");
    await bootstrap();
  } catch (e) { toast(e.message, "error"); }
}

async function toggleItem(itemKey, enabled) {
  try {
    await apiPost(`/plugins/douluo/admin-api/items/${encodeURIComponent(itemKey)}/toggle`, { enabled });
    toast("物品状态已更新", "good");
    await bootstrap();
  } catch (e) { toast(e.message, "error"); }
}

document.addEventListener("DOMContentLoaded", init);
