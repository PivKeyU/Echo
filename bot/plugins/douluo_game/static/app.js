"use strict";

/* ============ 斗罗大陆 Mini App ============ */

const RING_COLOR_EMOJI = { "白": "⚪", "黄": "🟡", "紫": "🟣", "黑": "⚫", "红": "🔴", "蓝金": "💎" };
const CATEGORY_LABELS = { soulbone: "魂骨", ambush: "暗器", pill: "丹药", material: "材料", contract: "契约", ticket: "凭证", craft_material: "锻造材料", soul_device: "魂导器", battle_armor: "斗铠", soul_core: "魂核" };

const state = {
  initData: "",
  telegramInitData: "",
  user: null,
  data: null,
  sessionToken: localStorage.getItem("douluo_web_session_token") || "",
  authAccount: null,
  authMode: "login",
  busy: false,
  selectedRegion: "",
  selectedProspectRegion: "",
  rankKind: "power",
};

/* ---------- tiny DOM helpers ---------- */
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
function fmtNum(value) {
  const n = Number(value ?? 0);
  if (n >= 10000) return (n / 10000).toFixed(n % 10000 ? 1 : 0) + "万";
  return String(n);
}
function toast(message, kind = "") {
  const stack = qs("#toast-stack");
  const node = el(`<div class="toast ${kind ? "toast--" + kind : ""}">${esc(message)}</div>`);
  stack.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

/* ---------- API client ---------- */
async function readPayload(response) {
  const raw = await response.text();
  if (!raw) return { code: response.ok ? 200 : response.status, data: null };
  try { return JSON.parse(raw); }
  catch { throw new Error(raw.trim() || "请求失败"); }
}

async function postJson(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: state.initData, session_token: state.sessionToken, ...body }),
  });
  const payload = await readPayload(response);
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || "请求失败");
  }
  return payload.data;
}

async function authPostJson(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await readPayload(response);
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || "请求失败");
  }
  return payload.data;
}

/* ---------- Telegram init ---------- */
function initTelegram() {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try { tg.ready(); tg.expand(); } catch (e) { /* ignore */ }
    state.telegramInitData = tg.initData || "";
    state.user = tg.initDataUnsafe?.user || null;
    if (tg.colorScheme === "dark" || window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
      document.body.classList.add("dark");
    }
  }
  state.initData = state.telegramInitData;
}

/* ---------- Auth ---------- */
function renderAuthPanel(mode = "login") {
  state.authMode = mode;
  const isLogin = mode === "login";
  qs("#auth-login-form").classList.toggle("hidden", !isLogin);
  qs("#auth-register-form").classList.toggle("hidden", isLogin);
  qsa("[data-auth-mode]").forEach((btn) => btn.classList.toggle("active", btn.dataset.authMode === mode));
  const authCard = qs("#auth-card");
  authCard.classList.remove("hidden");
  document.body.classList.add("auth-locked");
}

function hideAuthPanel() {
  qs("#auth-card").classList.add("hidden");
  document.body.classList.remove("auth-locked");
}

function setSessionToken(token) {
  state.sessionToken = token || "";
  if (state.sessionToken) localStorage.setItem("douluo_web_session_token", state.sessionToken);
  else localStorage.removeItem("douluo_web_session_token");
}

async function checkSession() {
  if (!state.sessionToken) return false;
  try {
    const payload = await authPostJson("/plugins/douluo/api/auth/me", { session_token: state.sessionToken });
    if (payload?.account?.tg) {
      state.authAccount = payload.account;
      return true;
    }
    return false;
  } catch (e) {
    setSessionToken("");
    return false;
  }
}

async function onLogin(event) {
  event.preventDefault();
  const username = qs("#auth-login-username").value.trim();
  const password = qs("#auth-login-password").value;
  if (!username || !password) return;
  const btn = qs("#auth-login-submit");
  btn.disabled = true;
  try {
    const payload = await authPostJson("/plugins/douluo/api/auth/login", { username, password, init_data: state.telegramInitData });
    state.authAccount = payload.account;
    setSessionToken(payload.session_token);
    if (payload.account?.tg) { await enterGame(); }
    else { renderBindPanel(payload.account); }
  } catch (e) { toast(e.message, "error"); }
  finally { btn.disabled = false; }
}

async function onRegister(event) {
  event.preventDefault();
  const username = qs("#auth-register-username").value.trim();
  const password = qs("#auth-register-password").value;
  const confirm = qs("#auth-register-confirm").value;
  const displayName = qs("#auth-register-display").value.trim();
  if (password !== confirm) { toast("两次输入的密码不一致", "error"); return; }
  const btn = qs("#auth-register-submit");
  btn.disabled = true;
  try {
    const payload = await authPostJson("/plugins/douluo/api/auth/register", {
      username, password, display_name: displayName, init_data: state.telegramInitData,
    });
    state.authAccount = payload.account;
    setSessionToken(payload.session_token);
    if (payload.account?.tg) { await enterGame(); }
    else { renderBindPanel(payload.account); }
  } catch (e) { toast(e.message, "error"); }
  finally { btn.disabled = false; }
}

function renderBindPanel(account) {
  setText("#auth-account-name", account?.username || "网页账号");
  const bound = Boolean(account?.tg);
  setText("#auth-bind-state", bound ? "已绑定" : "待绑定");
  setText("#auth-bind-hint", bound
    ? "已绑定 Telegram，可以返回游戏。"
    : "请从 Telegram Mini App 内点击下方按钮完成绑定。");
  qs("#auth-bind-telegram").classList.toggle("hidden", bound);
  qs("#auth-close").classList.toggle("hidden", !bound);
  qs("#auth-bind-panel").classList.remove("hidden");
  qs("#auth-login-form").classList.add("hidden");
  qs("#auth-register-form").classList.add("hidden");
}

async function onBindTelegram() {
  if (!state.telegramInitData) { toast("请在 Telegram Mini App 内绑定", "error"); return; }
  try {
    const payload = await authPostJson("/plugins/douluo/api/auth/bind-telegram", {
      session_token: state.sessionToken,
      init_data: state.telegramInitData,
    });
    state.authAccount = payload.account;
    renderBindPanel(payload.account);
    await enterGame();
  } catch (e) { toast(e.message, "error"); }
}

async function onLogout() {
  try { await authPostJson("/plugins/douluo/api/auth/logout", { session_token: state.sessionToken }); } catch (e) { /* ignore */ }
  setSessionToken("");
  state.authAccount = null;
  renderAuthPanel("login");
}

/* ---------- Data & render ---------- */
async function bootstrap() {
  const payload = await postJson("/plugins/douluo/api/bootstrap", {});
  state.user = payload.telegram_user || state.user;
  state.data = payload;
  renderAll();
  document.body.classList.remove("auth-locked");
}

async function enterGame() {
  await bootstrap();
  window.history.replaceState(null, "", window.location.pathname);
}

async function reload() {
  const payload = await postJson("/plugins/douluo/api/bootstrap", {});
  state.data = payload;
  renderAll();
}

function profile() { return state.data; }
function profileRow() { return state.data || {}; }

function renderAll() {
  const d = state.data;
  if (!d) return;
  renderHero(d);
  renderWuhun(d);
  renderTrain(d);
  renderHunt(d);
  renderBreakthrough(d);
  renderSequel(d);
  renderCraft(d);
  renderArmor(d);
  renderInventory(d);
  renderSect(d);
  renderTasks(d);
  renderAuction(d);
  renderBoss(d);
  renderExchange(d);
  renderRank(d);
  renderJournals(d);
  qsa(".fold-card").forEach((card) => card.open = card.hasAttribute("open"));
  renderAdminEntry(d);
  renderBottomNav();
}

function renderHero(d) {
  const realm = d.realm_stage || "魂士";
  const stars = Number(d.realm_stars || 1);
  const starText = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"][stars] || stars + "星";
  setText("#realm-badge", realm);
  setText("#star-pill", starText + "星");
  setText("#battle-pill", "战力 " + fmtNum(d.battle_power || 0));
  setText("#hero-soul-power", fmtNum(d.soul_power || 0));
  setText("#hero-coin", fmtNum(d.coin || 0));
  setText("#hero-spirit-power", fmtNum(d.spirit_power || 0));
  setText("#hero-fragment", fmtNum(d.economy?.emby_fragment || 0));
  setText("#status-text", `${d.display_name || "魂师"} · 魂师名帖`);
  const ap = d.action_points || {};
  const apText = ap.limit ? `行动力 ${ap.remaining}/${ap.limit}` : "行动力 ∞";
  setText("#hero-note", `${apText} ｜ 今日修炼、猎杀、讨伐与拍卖都会消耗行动力。`);
}

function ringText(ring) {
  const emoji = RING_COLOR_EMOJI[ring.color] || "⚪";
  const years = Number(ring.years || 0);
  const yearsText = years >= 10000 && years % 10000 === 0 ? (years / 10000) + "万" : String(years);
  const source = ring.source_name ? `【${esc(ring.source_name)}】` : "";
  return `${emoji}${source}第${ring.slot}环·${ring.tier}(${yearsText}年)${ring.skill_name ? " " + esc(ring.skill_name) : ""}`;
}

function renderWuhun(d) {
  const box = qs("#wuhun-status");
  const actions = qs("#wuhun-actions");
  const wuhun = d.wuhun || {};
  const lines = [];
  if (wuhun.name) {
    lines.push(el(`<div class="entry"><div class="row"><span><strong>${esc(wuhun.name)}</strong>（${esc(wuhun.system)}系 · ${esc(wuhun.quality)}）</span><span class="muted">先天魂力 ${d.innate_soul_power || 0}</span></div></div>`));
  } else {
    lines.push(el('<div class="entry">尚未觉醒武魂。觉醒武魂后才能修炼、猎杀与突破。</div>'));
  }
  const rings = d.rings || [];
  if (rings.length) {
    lines.push(el(`<div class="entry"><div class="row"><span>魂环</span><span style="display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end">${rings.map((r) => `<span class="ring-chip">${ringText(r)}</span>`).join("")}</span></div></div>`));
  } else if (wuhun.name) {
    lines.push(el('<div class="entry">还没有魂环，去猎杀魂兽获取第 1 魂环吧。</div>'));
  }
  const equipment = d.equipment || {};
  const bones = Object.values(equipment).filter((item) => item.category === "soulbone");
  const ambush = Object.values(equipment).find((item) => item.category === "ambush");
  lines.push(el(`<div class="entry"><div class="row"><span>魂骨 ${bones.length}/6</span><span class="muted">暗器 ${ambush ? esc(ambush.name) : "未装备"}</span></div></div>`));
  box.replaceChildren(...lines);

  const buttons = [];
  if (!wuhun.name) {
    buttons.push(el('<button type="button" data-action="wuhun-awaken">🧬 觉醒武魂</button>'));
  } else {
    buttons.push(el(`<button type="button" data-action="wuhun-reforge" class="ghost">🔁 重铸武魂</button>`));
  }
  actions.replaceChildren(...buttons);
}

function renderTrain(d) {
  const box = qs("#actions-train");
  const ap = d.action_points || {};
  const usage = (d.action_usage || {}).train || {};
  const remain = usage.remaining;
  const info = el(`<div class="entry"><div class="row"><span>⚔️ 静室修炼</span><span class="muted">${remain === null ? "不限次数" : "今日剩余 " + remain + " 次"}</span></div><div class="meta muted" style="font-size:12px">产出魂力与金魂币，有概率触发奇遇。</div></div>`);
  const btn = el('<button type="button" data-action="train">修炼</button>');
  const box2 = document.createElement("div");
  box2.className = "action-section-grid";
  box2.appendChild(btn);
  box.replaceChildren(info, box2);
}

function renderHunt(d) {
  const regions = d.hunt_regions || [];
  const grid = qs("#hunt-regions");
  grid.replaceChildren(...regions.map((region) => {
    const node = el(`<div class="module-item" data-region="${esc(region.key)}">
      <div class="name">${esc(region.name)}</div>
      <div class="meta">入场 ${fmtNum(region.entry_coin || 0)} 魂币</div>
    </div>`);
    if (region.key === state.selectedRegion) node.classList.add("selected");
    return node;
  }));
  const actions = qs("#actions-hunt");
  const btn = el(`<button type="button" data-action="hunt">🎯 进入猎杀${state.selectedRegion ? "（当前区域）" : ""}</button>`);
  actions.replaceChildren(btn);
}

function renderBreakthrough(d) {
  const box = qs("#actions-breakthrough");
  const btn = el('<button type="button" data-action="breakthrough">🚀 尝试突破</button>');
  const info = el(`<div class="entry"><div class="row"><span>当前 ${esc(d.realm_stage || "魂士")} ${d.realm_stars || 1} 星</span><span class="muted">${d.breakthrough_failures ? "失败保底 " + d.breakthrough_failures + " 次" : "突破失败将损失魂力"}</span></div></div>`);
  box.replaceChildren(info, btn);
}

function renderSequel(d) {
  const box = qs("#bloodline-status");
  const actions = qs("#bloodline-actions");
  const bl = d.bloodline || null;
  const settings = d.settings || {};
  const lines = [];
  if (bl) {
    lines.push(el(`<div class="entry"><div class="row"><span><strong>${esc(bl.name)}</strong>（${esc(bl.rarity)}）Lv.${bl.level}</span><span class="muted">血脉加成战力 ${fmtNum(bl.power || 0)}</span></div></div>`));
    lines.push(el(`<div class="entry"><div class="row"><span>🌀 ${esc(bl.system || "")}</span><span class="muted">📜 ${esc(bl.skill || "无")}</span></div></div>`));
  } else {
    lines.push(el(`<div class="entry">血脉未觉醒。达到 <strong>魂尊</strong> 且已觉醒武魂后，可消耗 <strong>${fmtNum(settings.bloodline_awaken_coin || 2000)}</strong> 魂币觉醒血脉（龙王传说 / 终极斗罗）。</div>`));
  }
  box.replaceChildren(...lines);
  const buttons = [];
  if (!bl) {
    buttons.push(el('<button type="button" data-action="bloodline-awaken">🩸 觉醒血脉</button>'));
  } else if (bl.level < 50) {
    buttons.push(el(`<button type="button" data-action="bloodline-enhance" class="ghost">⬆️ 淬炼血脉（${fmtNum(settings.bloodline_enhance_coin || 800)} 魂币 + ${fmtNum(settings.bloodline_enhance_soul_power || 2000)} 魂力）</button>`));
  } else {
    buttons.push(el('<div class="entry muted" style="font-size:12px">血脉已淬炼至圆满。</div>'));
  }
  actions.replaceChildren(...buttons);

  const cm = d.craftsman || {};
  const cmBox = qs("#craftsman-status");
  const cmExp = cm.exp || 0;
  const cmNext = cm.next_exp;
  cmBox.innerHTML = `<div class="row"><span>🔧 魂导师 ${cm.rank || 1} 阶</span><span class="muted">熟练度 ${cmNext ? cmExp + "/" + cmNext : cmExp + "（已满级）"}</span></div>`;
}

function renderCraft(d) {
  const settings = d.settings || {};
  const regions = d.sequel?.prospect_regions || [];
  const grid = qs("#prospect-regions");
  grid.replaceChildren(...regions.map((region) => {
    const node = el(`<div class="module-item" data-prospect-region="${esc(region.key)}">
      <div class="name">${esc(region.name)}</div>
      <div class="meta">入场 ${fmtNum(region.entry_coin || 0)} 魂币</div>
    </div>`);
    if (region.key === state.selectedProspectRegion) node.classList.add("selected");
    return node;
  }));

  const actions = qs("#actions-prospect");
  const usage = (d.action_usage || {}).prospect || {};
  const remain = usage.remaining;
  actions.replaceChildren(
    el(`<div class="entry"><div class="row"><span>⛏️ 勘探矿脉</span><span class="muted">${remain === null ? "不限次数" : "今日剩余 " + remain + " 次"} · 消耗 ${fmtNum(settings.prospect_coin_cost || 100)} 魂币</span></div></div>`),
    el(`<button type="button" data-action="prospect">⛏️ 勘探${state.selectedProspectRegion ? "（当前区域）" : ""}</button>`)
  );

  const defs = d.item_definitions || [];
  const defMap = {};
  defs.forEach((def) => { defMap[def.item_key] = def; });
  const held = {};
  (d.inventory?.categories?.craft_material || []).forEach((item) => { held[item.item_key] = item.quantity; });
  const devices = defs.filter((x) => x.category === "soul_device");
  const cmRank = d.craftsman?.rank || 1;
  const nodes = devices.map((def) => {
    const recipe = (def.recipe_config || {}).materials || {};
    const coin = (def.recipe_config || {}).coin || 0;
    const needRank = (def.recipe_config || {}).craftsman_rank || 1;
    const matText = Object.entries(recipe).map(([key, qty]) => {
      const m = defMap[key];
      const have = held[key] || 0;
      const ok = have >= qty;
      return `<span class="${ok ? "" : "lack"}">${esc(m ? m.name : key)} ${have}/${qty}</span>`;
    }).join(" ");
    const locked = cmRank < needRank;
    const btn = locked
      ? `<span class="muted" style="font-size:12px">需魂导师 ${needRank} 阶</span>`
      : `<button type="button" class="mini" data-action="craft" data-item="${esc(def.item_key)}" ${def.enabled === false ? "disabled" : ""}>锻造</button>`;
    return el(`<div class="entry">
      <div class="row"><span><strong>${esc(def.name)}</strong> <span class="muted">${esc(def.rarity || "")}</span></span>${btn}</div>
      <div class="meta muted" style="font-size:12px">攻 ${def.attack || 0} 防 ${def.defense || 0} 速 ${def.speed || 0} 精 ${def.spirit || 0} ｜ 魂币 ${fmtNum(coin)}</div>
      <div class="meta" style="font-size:12px">${matText}</div>
    </div>`);
  });
  const craftBox = qs("#craft-devices");
  craftBox.replaceChildren(...nodes.length ? nodes : [el('<div class="entry">暂无魂导器配方。</div>')]);
}

function renderArmor(d) {
  const settings = d.settings || {};
  const box = qs("#armor-status");
  const actions = qs("#actions-armor");
  const armor = d.equipment?.battle_armor || null;
  const tiers = d.sequel?.battle_armor_tiers || [];
  const lines = [];
  if (armor) {
    lines.push(el(`<div class="entry"><div class="row"><span><strong>${esc(armor.name)}</strong>（${esc(armor.rarity || "")}）</span><span class="muted">攻 ${armor.attack || 0} 防 ${armor.defense || 0} 速 ${armor.speed || 0}</span></div></div>`));
    const nextTier = tiers.find((t) => Number(t.tier) === Number(armor.tier || 0) + 1);
    if (nextTier) {
      const matText = Object.entries(nextTier.recipe || {}).map(([key, qty]) => key + "×" + qty).join(" ");
      lines.push(el(`<div class="entry"><div class="row"><span>下一阶</span><span class="muted">${esc(nextTier.name)}（需 ${esc(nextTier.realm_required)}）</span></div><div class="meta muted" style="font-size:12px">${matText} ｜ 魂币 ${fmtNum(nextTier.coin)}</div></div>`));
    } else {
      lines.push(el('<div class="entry"><div class="row"><span class="muted">斗铠已至最高阶。</span></div></div>'));
    }
  } else {
    const first = tiers[0];
    lines.push(el(`<div class="entry">未穿戴斗铠。${first ? "达到 <strong>" + esc(first.realm_required) + "</strong> 并集齐材料后可锻造，锻造后在背包中装备。" : ""}</div>`));
  }
  box.replaceChildren(...lines);
  const buttons = [];
  const nextTier = armor ? tiers.find((t) => Number(t.tier) === Number(armor.tier || 0) + 1) : null;
  if (nextTier) {
    buttons.push(el(`<button type="button" data-action="armor-upgrade">⬆️ 升级斗铠（${fmtNum(settings.armor_upgrade_coin || 1500)} 魂币）</button>`));
  }
  if (armor) {
    buttons.push(el(`<button type="button" data-action="unequip" data-slot="battle_armor" class="ghost">卸下斗铠</button>`));
  }
  actions.replaceChildren(...buttons);

  const core = d.equipment?.soul_core || null;
  const coreBox = qs("#soul-core-status");
  coreBox.innerHTML = core
    ? `<div class="row"><span>💎 <strong>${esc(core.name)}</strong>（${esc(core.rarity || "")}）</span><span class="muted">精 ${fmtNum(core.spirit || 0)} ｜ 攻 ${fmtNum(core.attack || 0)} 防 ${fmtNum(core.defense || 0)}</span></div>`
    : `<div class="row"><span>💎 魂核未凝聚</span><span class="muted">魂斗罗及以上可凝聚（${fmtNum(settings.condense_coin_cost || 2000)} 魂币 + ${fmtNum(settings.condense_soul_power_cost || 3000)} 魂力）</span></div>`;
  const condenseBtn = el('<button type="button" data-action="soul-core-condense" class="ghost">💎 凝聚魂核</button>');
  actions.appendChild(condenseBtn);
}

function renderInventory(d) {
  const equipment = d.equipment || {};
  const eqBox = qs("#equipment-summary");
  const eqChips = Object.entries(equipment).map(([slot, item]) =>
    `<span class="equip-chip">${esc(item.name)} <button type="button" class="mini ghost" data-action="unequip" data-slot="${esc(slot)}">卸下</button></span>`
  );
  eqBox.innerHTML = eqChips.length ? `<div class="row" style="gap:6px;display:flex;flex-wrap:wrap">${eqChips.join("")}</div>`
    : '<div class="entry" style="font-size:12px;color:var(--muted)">暂无已装备物品。</div>';

  const defs = d.item_definitions || [];
  const defMap = {};
  defs.forEach((def) => { defMap[def.item_key] = def; });

  const groups = d.inventory?.categories || {};
  const container = qs("#inventory-groups");
  const boxes = Object.entries(groups).map(([category, items]) => {
    const itemNodes = items.map((item) => {
      const def = defMap[item.item_key] || {};
      const canEquip = Boolean(def.equipment_slot);
      const isEquipped = Boolean(item.equipped_slot);
      const action = isEquipped
        ? `<button type="button" class="mini ghost" data-action="unequip" data-slot="${esc(item.equipped_slot)}">卸下</button>`
        : canEquip
          ? `<button type="button" class="mini" data-action="equip" data-item="${esc(item.item_key)}">装备</button>`
          : "";
      return `<span class="inv-item">${esc(item.name)} <span class="qty">×${item.quantity}</span>${isEquipped ? ' <span class="equipped">✅</span>' : ""} ${action}</span>`;
    });
    return el(`<div class="inv-group"><div class="group-head">${CATEGORY_LABELS[category] || category}</div><div class="inv-items">${itemNodes.join("")}</div></div>`);
  });
  container.replaceChildren(...boxes.length ? boxes : [el('<div class="entry" style="font-size:12px;color:var(--muted)">背包空空如也。</div>')]);
}

function renderSect(d) {
  const box = qs("#sect-choice");
  const sects = d.sects || [];
  const current = d.sect_key;
  if (!current) {
    box.replaceChildren(...sects.map((sect) => {
      const btn = sect.key === (state.selectedSect || sects[0]?.key)
        ? sect.key
        : sect.key;
      return el(`<div class="sect-item" data-sect="${esc(sect.key)}">
        <div class="name">${esc(sect.name)}</div>
        <div class="meta">入宗 ${fmtNum(sect.entry_coin || 0)} 魂币</div>
        <button type="button" class="mini" data-action="join-sect" data-sect="${esc(sect.key)}">加入</button>
      </div>`);
    }));
  } else {
    box.replaceChildren(el(`<div class="entry"><div class="row"><span><strong>${esc(d.sect_key)}</strong> · ${esc(d.sect_position || "弟子")}</span><span class="muted">贡献 ${fmtNum(d.sect_contribution || 0)}</span></div></div>`));
  }
  const actions = qs("#actions-sect");
  actions.replaceChildren(el('<button type="button" data-action="sect-salary">💰 领取俸禄</button>'));
}

function renderTasks(d) {
  const taskData = d.daily_tasks || {};
  const tasks = taskData.tasks || [];
  const box = qs("#task-list");
  const nodes = tasks.map((task) => {
    const pct = task.target ? Math.min(100, Math.round((task.progress / task.target) * 100)) : 0;
    const rewardText = Object.entries(task.rewards || {})
      .map(([key, val]) => ({ coin: "魂币", soul_power: "魂力" }[key] ? ({ coin: "魂币", soul_power: "魂力" })[key] + " +" + val : key + " " + val))
      .join(" · ");
    const claimBtn = task.claimable
      ? `<button type="button" class="mini" data-action="claim-task" data-task="${esc(task.task_key)}">领取</button>`
      : task.claimed ? '<span class="muted">已领</span>' : "";
    return el(`<div class="entry">
      <div class="row"><span><strong>${esc(task.name)}</strong></span>${claimBtn ? `<span>${claimBtn}</span>` : ""}</div>
      <div class="progress-meta"><span>${task.progress}/${task.target}</span><span class="muted">${rewardText || ""}</span></div>
      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
    </div>`);
  });
  box.replaceChildren(...nodes.length ? nodes : [el('<div class="entry">今日暂无任务。</div>')]);
}

function renderAuction(d) {
  const defs = d.item_definitions || [];
  const groups = d.inventory?.categories || {};
  const tradable = [];
  ["soulbone", "ambush", "material"].forEach((cat) => {
    (groups[cat] || []).forEach((item) => {
      if (item.equipped_slot) return;
      const def = defs.find((x) => x.item_key === item.item_key);
      if (def && !def.equipment_slot) return; // 仅允许可装备类(魂骨/暗器)上架
      tradable.push(item);
    });
  });
  const place = qs("#auction-place");
  if (!tradable.length) {
    place.replaceChildren(el('<div class="entry" style="font-size:12px;color:var(--muted)">背包中暂无可以上架的魂骨或暗器。</div>'));
  } else {
    const options = tradable.map((item) => `<option value="${esc(item.item_key)}">${esc(item.name)} ×${item.quantity}</option>`).join("");
    place.replaceChildren(el(`<form id="auction-place-form" class="mini-form">
      <label>上架物品
        <select id="auction-item">${options}</select>
      </label>
      <label>起拍价(魂币)
        <input id="auction-price" type="number" min="1" value="100">
      </label>
      <button type="submit">上架拍卖</button>
    </form>`));
  }

  const listBox = qs("#auction-list");
  const listings = d.auctionListings || [];
  listBox.replaceChildren(...listings.map((item) => {
    const isMine = item.is_mine;
    const action = isMine
      ? '<span class="muted">我的拍卖</span>'
      : `<button type="button" class="mini" data-action="bid" data-listing="${item.id}">竞价 ${fmtNum(item.current_bid)}</button>`;
    return el(`<div class="auction-item">
      <div class="name">${esc(item.item_name)} <span class="muted">${item.rarity || ""}</span></div>
      <div class="meta">当前 ${fmtNum(item.current_bid)} ｜ 出价 ${item.bid_count} 次</div>
      <div class="row" style="justify-content:space-between;align-items:center">${action}</div>
    </div>`);
  }).concat(listings.length ? [] : [el('<div class="entry" style="font-size:12px;color:var(--muted)">暂无在拍商品。</div>')]));
}

function renderBoss(d) {
  const bosses = d.bosses || [];
  const box = qs("#boss-list");
  box.replaceChildren(...bosses.map((boss) => {
    const btn = `<button type="button" class="mini" data-action="boss" data-boss="${esc(boss.key)}">讨伐</button>`;
    return el(`<div class="boss-item">
      <div class="name">${esc(boss.name)}</div>
      <div class="meta">推荐战力 ${fmtNum(boss.recommended_power || 0)} ｜ 入场 ${fmtNum(boss.entry_coin || 0)}</div>
      <div class="row" style="justify-content:space-between;align-items:center"><span class="muted" style="font-size:12px">${esc(boss.realm_stage_min || "魂士")} 可讨伐</span>${btn}</div>
    </div>`);
  }).concat(bosses.length ? [] : [el('<div class="entry" style="font-size:12px;color:var(--muted)">暂无可讨伐的 Boss。</div>')]));
  const record = qs("#boss-record");
  record.replaceChildren(el(`<div class="entry"><div class="row"><span>Boss 战绩分</span><span><strong>${fmtNum(d.boss_score || 0)}</strong></span></div><div class="row"><span>猎杀记录</span><span class="muted">${fmtNum(d.total_hunts || 0)} 次</span></div></div>`));
}

function renderExchange(d) {
  const eco = d.economy || {};
  const rate = eco.exchange_rate || 100;
  const hint = `当前汇率：${rate} 碎片 = 1 魂币${eco.exchange_enabled ? "" : "（兑换功能未开启）"}`;
  setText("#exchange-hint", hint);
  qs("#exchange-form").classList.toggle("hidden", !eco.exchange_enabled);
}

function renderRank(d) {
  const kind = state.rankKind;
  const data = (d.leaderboard || {})[kind] || { items: [], label: "" };
  const box = qs("#rank-list");
  const medals = ["🥇", "🥈", "🥉"];
  const nodes = (data.items || []).map((item, index) => el(`<div class="entry rank-row">
    <span class="rank-medal">${medals[index] || index + 1 + "."}</span>
    <span style="flex:1">${esc(item.display_name)} <span class="muted" style="font-size:12px">${esc(item.sub || "")}</span></span>
    <span class="rank-value">${fmtNum(item.value)}</span>
  </div>`));
  box.replaceChildren(...nodes.length ? nodes : [el('<div class="entry">暂无排行数据。</div>')]);
  qsa("[data-rank-kind]").forEach((btn) => btn.classList.toggle("active", btn.dataset.rankKind === kind));
}

function renderJournals(d) {
  const items = d.journals || [];
  const box = qs("#journal-list");
  const nodes = items.map((item) => el(`<div class="entry"><div class="row"><span><strong>${esc(item.title)}</strong></span><span class="muted" style="font-size:12px">${(item.created_at || "").replace("T", " ").slice(0, 16)}</span></div>${item.detail ? `<div class="meta muted" style="font-size:12px">${esc(item.detail)}</div>` : ""}</div>`));
  box.replaceChildren(...nodes.length ? nodes : [el('<div class="entry">暂无记录。</div>')]);
}

function renderAdminEntry(d) {
  const caps = d.capabilities || {};
  const visible = Boolean(caps.is_admin && caps.admin_panel_url);
  const fab = qs("#fab-admin");
  const heroEntry = qs("#hero-admin-entry");
  fab.classList.toggle("hidden", !visible);
  heroEntry.classList.toggle("hidden", !visible);
  if (visible) {
    const button = qs("#open-admin-panel");
    if (button) button.dataset.adminUrl = caps.admin_panel_url;
    fab.dataset.adminUrl = caps.admin_panel_url;
  }
}

function renderBottomNav() {
  const sections = [
    ["#wuhun-card", "武魂"],
    ["#hunt-card", "猎杀"],
    ["#bloodline-card", "血脉"],
    ["#craft-card", "魂导"],
    ["#inventory-card", "背包"],
    ["#task-card", "任务"],
    ["#auction-card", "拍卖"],
    ["#rank-card", "排行"],
  ];
  const nav = qs("#bottom-nav");
  nav.replaceChildren(...sections.map(([selector, label]) => {
    const btn = el(`<button type="button" data-scroll="${selector}">${label}</button>`);
    return btn;
  }));
}

/* ---------- Action runner ---------- */
async function runAction(label, fn) {
  if (state.busy) { toast("操作进行中，请稍候", "error"); return; }
  state.busy = true;
  try {
    await fn();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    state.busy = false;
  }
}

function showResult(result) {
  if (!result) return;
  let box = qs("#result-box");
  if (!box) {
    box = el('<div id="result-box" class="result-box"></div>');
    const firstCard = qs(".fold-card");
    firstCard.parentNode.insertBefore(box, firstCard);
  }
  const text = result.result_text || result.detail || result.title || "";
  box.textContent = text;
  box.classList.remove("hidden");
}

/* ---------- Event wiring ---------- */
function wireEvents() {
  qsa("[data-auth-mode]").forEach((btn) => {
    btn.addEventListener("click", () => renderAuthPanel(btn.dataset.authMode));
  });
  qs("#auth-login-form").addEventListener("submit", onLogin);
  qs("#auth-register-form").addEventListener("submit", onRegister);
  qs("#auth-bind-telegram").addEventListener("click", onBindTelegram);
  qs("#auth-logout").addEventListener("click", onLogout);
  qs("#auth-close").addEventListener("click", () => { hideAuthPanel(); reload(); });
  qs("#focus-train").addEventListener("click", () => qs("#train-card").scrollIntoView({ behavior: "smooth" }));
  qs("#focus-hunt").addEventListener("click", () => qs("#hunt-card").scrollIntoView({ behavior: "smooth" }));
  qs("#open-account-center").addEventListener("click", () => renderBindPanel(state.authAccount));
  qs("#open-admin-panel").addEventListener("click", () => openAdminPanel());
  qs("#fab-admin").addEventListener("click", () => openAdminPanel());

  document.addEventListener("click", (event) => {
    const elTarget = event.target.closest("[data-action]");
    if (elTarget) handleAction(elTarget);
    const region = event.target.closest("[data-region]");
    if (region) {
      state.selectedRegion = region.dataset.region;
      qsa("[data-region]").forEach((n) => n.classList.toggle("selected", n.dataset.region === state.selectedRegion));
    }
    const prospectRegion = event.target.closest("[data-prospect-region]");
    if (prospectRegion) {
      state.selectedProspectRegion = prospectRegion.dataset.prospectRegion;
      qsa("[data-prospect-region]").forEach((n) => n.classList.toggle("selected", n.dataset.prospectRegion === state.selectedProspectRegion));
    }
    const rankBtn = event.target.closest("[data-rank-kind]");
    if (rankBtn) {
      state.rankKind = rankBtn.dataset.rankKind;
      renderRank(state.data);
    }
    const scrollBtn = event.target.closest("[data-scroll]");
    if (scrollBtn) qs(scrollBtn.dataset.scroll).scrollIntoView({ behavior: "smooth" });
  });

  qs("#auction-place").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (event.target.id !== "auction-place-form") return;
    const itemKey = qs("#auction-item").value;
    const price = Number(qs("#auction-price").value || 0);
    await runAction("上架拍卖", async () => {
      const payload = await postJson("/plugins/douluo/api/auction/place", { item_key: itemKey, price });
      showResult(payload.result);
      await reload();
    });
  });

  qs("#exchange-form").addEventListener("submit", (event) => event.preventDefault());
  qs("#fragment-to-coin-btn").addEventListener("click", () => doExchange("fragment_to_coin"));
  qs("#coin-to-fragment-btn").addEventListener("click", () => doExchange("coin_to_fragment"));
}

async function openAdminPanel() {
  const url = qs("#open-admin-panel")?.dataset.adminUrl
    || qs("#fab-admin")?.dataset.adminUrl
    || state.data?.capabilities?.admin_panel_url;
  if (!url) return;
  window.open(url, "_blank");
}

async function doExchange(direction) {
  const amount = Number(qs("#exchange-amount").value || 0);
  if (amount <= 0) { toast("请输入有效数量", "error"); return; }
  await runAction("兑换", async () => {
    const payload = await postJson("/plugins/douluo/api/exchange", { direction, amount });
    showResult({ detail: payload.result.detail });
    await reload();
  });
}

async function handleAction(node) {
  const action = node.dataset.action;
  const tgId = state.user?.id;
  await runAction(action, async () => {
    let payload;
    switch (action) {
      case "train":
        payload = await postJson("/plugins/douluo/api/train", {});
        showResult({ detail: `魂力 +${payload.result.soul_power_gained}，魂币 +${payload.result.coin_gained}${payload.result.event ? "，触发奇遇：" + payload.result.event.title : ""}` });
        break;
      case "hunt":
        payload = await postJson("/plugins/douluo/api/hunt", { region_key: state.selectedRegion || "" });
        showResult({ detail: describeHunt(payload.result) });
        break;
      case "breakthrough":
        payload = await postJson("/plugins/douluo/api/breakthrough", {});
        showResult(payload.result);
        break;
      case "wuhun-awaken":
        payload = await postJson("/plugins/douluo/api/wuhun/awaken", {});
        showResult({ detail: `觉醒武魂【${payload.result.wuhun?.name}】（${payload.result.wuhun?.system}系·${payload.result.wuhun?.quality}），先天魂力 ${payload.result.innate_soul_power}` });
        break;
      case "wuhun-reforge":
        payload = await postJson("/plugins/douluo/api/wuhun/reforge", {});
        showResult({ detail: `重铸武魂【${payload.result.wuhun?.name}】（${payload.result.wuhun?.system}系·${payload.result.wuhun?.quality}），先天魂力 ${payload.result.innate_soul_power}` });
        break;
      case "equip":
        payload = await postJson("/plugins/douluo/api/inventory/equip", { item_key: node.dataset.item });
        showResult({ detail: "装备完成" });
        break;
      case "unequip":
        payload = await postJson("/plugins/douluo/api/inventory/unequip", { slot: node.dataset.slot });
        showResult({ detail: "已卸下" });
        break;
      case "claim-task":
        payload = await postJson("/plugins/douluo/api/tasks/claim", { task_key: node.dataset.task });
        showResult({ detail: `领取成功：魂币 +${payload.result.coin_gained}，魂力 +${payload.result.soul_power_gained}` });
        break;
      case "join-sect":
        payload = await postJson("/plugins/douluo/api/sect/join", { sect_key: node.dataset.sect });
        showResult({ detail: `已加入【${payload.result.sect?.name}】` });
        break;
      case "sect-salary":
        payload = await postJson("/plugins/douluo/api/sect/salary", {});
        showResult(payload.result);
        break;
      case "bid":
        payload = await promptBid(node.dataset.listing);
        if (payload) showResult({ detail: "竞价成功" });
        break;
      case "boss":
        payload = await postJson("/plugins/douluo/api/boss/challenge", { boss_key: node.dataset.boss });
        showResult({ detail: describeBoss(payload.result) });
        break;
      case "bloodline-awaken":
        payload = await postJson("/plugins/douluo/api/bloodline/awaken", {});
        showResult(payload.result);
        break;
      case "bloodline-enhance":
        payload = await postJson("/plugins/douluo/api/bloodline/enhance", {});
        showResult(payload.result);
        break;
      case "prospect":
        payload = await postJson("/plugins/douluo/api/prospect", { region_key: state.selectedProspectRegion || "" });
        showResult(payload.result);
        break;
      case "craft":
        payload = await postJson("/plugins/douluo/api/craft", { item_key: node.dataset.item });
        showResult(payload.result);
        break;
      case "armor-upgrade":
        payload = await postJson("/plugins/douluo/api/armor/upgrade", {});
        showResult(payload.result);
        break;
      case "soul-core-condense":
        payload = await postJson("/plugins/douluo/api/soul-core/condense", {});
        showResult({ detail: `凝聚【${payload.result.core?.name || "魂核"}】！可在背包中装备` });
        break;
      default:
        return;
    }
    await reload();
  });
}

async function promptBid(listingId) {
  const price = window.prompt("请输入竞价金额（魂币）：", "100");
  if (!price) return null;
  const value = Number(price);
  if (value <= 0) { toast("请输入有效金额", "error"); return null; }
  return await postJson("/plugins/douluo/api/auction/bid", { listing_id: Number(listingId), price: value });
}

function describeHunt(result) {
  const ring = result.ring || {};
  const src = ring.source_name ? `【${ring.source_name}】` : "";
  let text = `在【${result.region?.name}】猎杀 ${result.beast?.name}，魂力 +${result.soul_power_gained}，魂币 +${result.coin_gained}。`;
  if (ring.action === "absorb") text += `\n吸收${src}第${ring.slot}魂环·${ring.tier}(${ring.years}年)，解锁魂技【${ring.skill_name}】！`;
  else if (ring.action === "replace") text += `\n以${src}${ring.tier}魂环(${ring.years}年)替换第${ring.slot}魂环！`;
  else if (ring.action === "give_up") text += `\n斩获${src}${ring.tier}魂环(${ring.years}年)，但${ring.reason}。`;
  if (result.event) text += `\n✨ 奇遇：${result.event.title}`;
  return text;
}

function describeBoss(result) {
  let text = result.win
    ? `讨伐【${result.boss?.name}】胜利！魂币 +${result.rewards?.coin}，魂力 +${result.rewards?.soul_power}，战绩分 +${result.rewards?.score}`
    : `讨伐【${result.boss?.name}】失败...`;
  if (result.rewards?.soulbone) text += `\n获得魂骨【${result.rewards.soulbone.name}】！`;
  if (result.rewards?.armor) text += `\n🛡️ 获得斗铠【${result.rewards.armor.name}】，在背包中装备后可在斗铠页升级！`;
  return text;
}

/* ---------- Init ---------- */
async function init() {
  initTelegram();
  wireEvents();

  if (await checkSession()) {
    try {
      await enterGame();
      return;
    } catch (e) {
      setSessionToken("");
    }
  }
  renderAuthPanel("login");
}

document.addEventListener("DOMContentLoaded", init);
