const RESOURCE_LABELS = {
  douqi: "斗气",
  gold: "金币",
  fire_seed: "异火火候",
  alchemy_exp: "炼药经验",
  beast_core: "魔核",
  sect_contribution: "宗门贡献",
  pill_stock: "丹药",
  technique_level: "斗技等级",
  fire_progress: "异火线索",
  boss_score: "Boss战绩",
  tower_floor: "塔层",
  auction_credit: "拍卖声望",
};

const ITEM_LABELS = {
  qi_gathering_powder: "聚气散",
  recovery_pill: "回气丹",
  three_pattern_qingling_pill: "三纹青灵丹",
  breaking_zong_pill: "破宗丹",
  healing_powder: "疗伤散",
  fire_guard_pill: "护火丹",
  lotus_body_pill: "血莲丹",
  douling_pill: "斗灵丹",
  ice_spirit_flame_grass: "冰灵焰草",
  blood_lotus_essence: "血莲精",
  seven_leaf_lotus: "七叶青莲",
  snake_shed_grass: "蛇蜕草",
  earth_core_fire_mushroom: "地心火芝",
  dragon_beard_ice_fire_fruit: "龙须冰火果",
  purple_spirit_crystal: "紫灵晶",
  soul_warming_lotus: "温魂莲",
  bone_washing_flower: "洗骨花",
  black_iron_ore: "黑铁矿",
  flame_pattern_steel: "火纹钢",
  monster_core_low: "一二阶魔核",
  monster_core_mid: "三四阶魔核",
  monster_core_high: "五阶以上魔核",
  qinglian_fire_map: "青莲地心火线索",
  fallen_heart_flame_trace: "陨落心炎残焰",
  qinglian_fire_seed: "青莲地心火",
  sea_heart_flame_seed: "海心焰",
  baji_beng_scroll: "八极崩卷轴",
  flame_divide_scroll: "焰分噬浪尺卷轴",
  thunder_steps_scroll: "三千雷动残卷",
  flame_method_fragment: "火属性功法残篇",
  xuan_heavy_ruler: "玄重尺",
  black_iron_sword: "黑铁剑",
  cloud_step_boots: "踏云靴",
  scale_guard_armor: "蛇鳞护甲",
  purple_cloud_wings: "紫云翼",
  flame_guard_bracer: "炎纹护腕",
  low_grade_storage_ring: "低阶纳戒",
  mitel_auction_token: "米特尔拍卖牌",
  inner_academy_badge: "内院火能牌",
  sea_heart_flame_trace: "海心焰线索",
  bone_spirit_cold_fire_trace: "骨灵冷火线索",
  three_thousand_flame_trace: "三千焱炎火残图",
  fallen_heart_flame_seed: "陨落心炎",
  bone_spirit_cold_fire_seed: "骨灵冷火",
  three_thousand_flame_seed: "三千焱炎火",
  buddha_lotus_scroll: "佛怒火莲残卷",
  burning_method_fragment: "焚诀残篇",
  fire_energy_crystal: "火能晶",
  black_corner_black_card: "黑角域黑卡",
  danta_exam_token: "丹塔考核令",
  yunlan_token: "云岚令",
  snake_people_token: "蛇人族信物",
  starfall_token: "星陨令",
  soul_palace_token: "魂殿密令",
  alchemist_badge_1: "一品炼药师徽章",
  alchemist_badge_2: "二品炼药师徽章",
  alchemist_badge_3: "三品炼药师徽章",
  alchemist_badge_4: "四品炼药师徽章",
  alchemist_badge_5: "五品炼药师徽章",
  alchemist_badge_6: "六品炼药师徽章",
  alchemist_badge_7: "七品炼药师徽章",
  alchemist_badge_8: "八品炼药师徽章",
  alchemist_badge_9: "九品炼药师徽章",
  star_mist_grass: "星雾草",
  dragon_blood_branch: "龙血枝",
  void_spirit_leaf: "虚灵叶",
  bodhi_seed: "菩提子",
  amethyst_lion_cub: "小紫晶翼狮",
  phoenix_plume: "天妖凰翎",
  taixu_dragon_scale: "太虚古龙鳞",
  clotting_grass: "凝血草",
  bone_growth_flower: "生骨花",
  purple_blue_leaf: "紫蓝叶",
  fire_spirit_root: "火灵根",
  cold_marrow_grass: "寒髓草",
  jade_bone_fruit: "玉骨果",
  earth_core_body_milk: "地心淬体乳",
  emperor_flow_serum: "帝流浆",
  nine_leaf_reincarnation_grass: "九叶轮回草",
  ancient_dragon_saliva: "古龙涎",
  green_rock_ore: "青岩矿",
  cold_iron_ore: "寒铁矿",
  meteorite_iron: "陨星铁",
  thunder_pattern_ore: "雷纹矿",
  space_stone: "空间石",
  beast_bone_shard: "魔兽骨片",
  beast_hide: "魔兽皮革",
  flame_crystal_core: "火晶核",
  spirit_pattern_wood: "灵纹木",
  ice_crystal_marrow: "冰晶髓",
  hemostasis_powder: "凝血散",
  bone_growth_pill: "生骨丹",
  qi_boost_pill: "增气丹",
  ice_heart_pill: "冰心丹",
  marrow_cleansing_pill: "洗髓丹",
  purple_heart_barrier_pill: "紫心破障丹",
  emperor_extreme_pill: "皇极丹",
  bodhi_pill: "菩提丹",
  soul_restoring_pill: "复魂丹",
  yin_yang_life_soul_pill: "阴阳命魂丹",
  bronze_cauldron: "青铜药鼎",
  black_demon_cauldron_replica: "黑魔鼎仿品",
  mercenary_leather_armor: "佣兵皮甲",
  cold_iron_blade: "寒铁刀",
  fire_spirit_talisman: "火灵护符",
  mid_grade_storage_ring: "中阶纳戒",
  thunder_pattern_boots: "雷纹靴",
  alchemist_robe: "炼药师袍",
  meteorite_heavy_ruler: "陨星重尺",
  spirit_wood_heart_mirror: "灵木护心镜",
};

const ACTION_ORDER = ["all", "train", "adventure", "alchemy", "craft", "pill", "fire", "sect", "technique", "tower", "auction", "faction", "pet", "black_corner", "boss", "breakthrough"];
const ACTION_LABELS = {
  all: "全部",
  train: "修炼",
  adventure: "历练",
  alchemy: "炼药",
  craft: "炼器",
  pill: "丹药",
  fire: "异火",
  sect: "宗门",
  technique: "斗技",
  tower: "塔修",
  auction: "拍卖",
  faction: "阵营",
  pet: "伙伴",
  black_corner: "黑角域",
  boss: "Boss",
  breakthrough: "突破",
};

const ACTION_GROUPS = [
  { key: "train", types: ["train"] },
  { key: "adventure", types: ["adventure"] },
  { key: "growth", types: ["alchemy", "pill", "breakthrough"] },
  { key: "craft", types: ["craft"] },
  { key: "sect", types: ["sect", "technique"] },
  { key: "fire", types: ["fire", "tower"] },
  { key: "market", types: ["auction", "boss"] },
];

const state = {
  initData: "",
  user: null,
  data: null,
  actionFilter: "all",
  actionLocks: {},
  sessionToken: localStorage.getItem("doupo_web_session_token") || "",
  authAccount: null,
  authMode: "login",
  expeditionChoiceKey: "",
  sectPanel: null,
  telegramInitData: "",
};

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return [...document.querySelectorAll(selector)];
}

function setText(selector, value) {
  const node = qs(selector);
  if (node) node.textContent = value ?? "-";
}

function currentRelativePath() {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

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

function withReturnTo(path, returnTo = currentRelativePath()) {
  const safePath = toSameOriginPath(path, "");
  if (!safePath) return "";
  const url = new URL(safePath, window.location.origin);
  const safeReturnTo = toSameOriginPath(returnTo, "");
  if (safeReturnTo) url.searchParams.set("return_to", safeReturnTo);
  return `${url.pathname}${url.search}${url.hash}`;
}

function localTestInitData() {
  const params = new URLSearchParams(window.location.search || "");
  const rawId = Number(params.get("test_user") || 1001001);
  const userId = Number.isFinite(rawId) && rawId > 0 ? Math.floor(rawId) : 1001001;
  const username = params.get("test_name") || "doupo_tester";
  const display = params.get("test_display") || "斗破测试者";
  return `local_test:${userId}:${username}:${display}`;
}

function isLocalHost() {
  return ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
}

function getRuntime() {
  const tg = window.Telegram?.WebApp;
  if (tg?.initData) {
    return {
      initData: tg.initData,
      user: tg.initDataUnsafe?.user || {},
      ready: () => tg.ready?.(),
      expand: () => tg.expand?.(),
      hideBackButton: () => tg.BackButton?.hide?.(),
    };
  }
  if (isLocalHost()) {
    return {
      initData: localTestInitData(),
      user: {},
      ready: () => {},
      expand: () => {},
      hideBackButton: () => {},
    };
  }
  return null;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function resolveRuntime() {
  const immediate = getRuntime();
  if (immediate || isLocalHost()) return immediate;
  const deadline = Date.now() + 1600;
  while (Date.now() < deadline) {
    await sleep(80);
    const runtime = getRuntime();
    if (runtime) return runtime;
  }
  return null;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function number(value) {
  return Number(value || 0);
}

function itemLabel(item = {}) {
  const key = item.item_key || item.key;
  const name = item.name || item.item_name || ITEM_LABELS[key] || key || "物品";
  const quantity = Number(item.quantity ?? item.qty ?? 0);
  if (!quantity) return name;
  return `${name} ${quantity > 0 ? "+" : ""}${quantity}`;
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

function percent(current, total) {
  const c = number(current);
  const t = Math.max(number(total), 1);
  return Math.max(0, Math.min(100, Math.round((c / t) * 100)));
}

function inventoryCategoryTotal(bundle = {}, categoryKey = "") {
  const categories = bundle.inventory?.categories;
  if (!Array.isArray(categories)) return 0;
  const category = categories.find((item) => item.key === categoryKey);
  return number(category?.total_quantity);
}

function actionLockRemaining(actionKey) {
  const until = Number(state.actionLocks?.[actionKey] || 0);
  if (!until || until <= Date.now()) {
    delete state.actionLocks[actionKey];
    return 0;
  }
  return Math.ceil((until - Date.now()) / 1000);
}

function lockAction(actionKey, seconds) {
  const duration = Math.max(Number(seconds || 0), 3);
  state.actionLocks[actionKey] = Date.now() + duration * 1000;
  window.setTimeout(() => {
    if (actionLockRemaining(actionKey) <= 0) renderActions(state.data || {});
  }, duration * 1000 + 120);
}

function showToast(message, type = "success") {
  const root = qs("#toast-stack");
  if (!root) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = String(message || "");
  root.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3200);
}

function setStatus(text, type = "normal") {
  setText("#status-text", text || "");
  const chip = qs("#feedback-chip");
  if (!chip) return;
  chip.textContent = String(text || "");
  chip.classList.toggle("hidden", !text);
  chip.classList.toggle("badge--danger", type === "error");
}

function setButtonBusy(button, busy, text = "处理中...") {
  if (!button) return;
  if (busy) {
    button.dataset.previousText = button.textContent || "";
    button.disabled = true;
    button.textContent = text;
    return;
  }
  button.disabled = false;
  if (button.dataset.previousText) button.textContent = button.dataset.previousText;
  delete button.dataset.previousText;
}

async function readPayload(response) {
  const raw = await response.text();
  if (!raw) return { code: response.ok ? 200 : response.status, data: null };
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(raw.trim() || "请求失败");
  }
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
    const error = new Error(payload.detail || payload.message || "请求失败");
    error.status = response.status;
    throw error;
  }
  return payload.data;
}

function describeDelta(action = {}) {
  const reward = action.reward_config || {};
  const chunks = [];
  [
    ["douqi", "douqi_min", "douqi_max"],
    ["gold", "gold_min", "gold_max"],
    ["fire_seed", "fire_min", "fire_max"],
    ["alchemy_exp", "alchemy_min", "alchemy_max"],
    ["beast_core", "core_min", "core_max"],
    ["sect_contribution", "sect_min", "sect_max"],
    ["pill_stock", "pill_min", "pill_max"],
    ["technique_level", "technique_min", "technique_max"],
    ["fire_progress", "fire_progress_min", "fire_progress_max"],
    ["boss_score", "boss_min", "boss_max"],
    ["tower_floor", "tower_min", "tower_max"],
    ["auction_credit", "auction_min", "auction_max"],
  ].forEach(([resource, minKey, maxKey]) => {
    const min = reward[minKey];
    const max = reward[maxKey];
    if (min === undefined && max === undefined) return;
    chunks.push(`${RESOURCE_LABELS[resource]} ${Number(min || 0)}-${Number(max ?? min ?? 0)}`);
  });
  if (reward.gold_cost) chunks.push(`消耗金币 ${Number(reward.gold_cost)}`);
  if (reward.core_cost) chunks.push(`消耗魔核 ${Number(reward.core_cost)}`);
  if (reward.pill_cost) chunks.push(`消耗丹药 ${Number(reward.pill_cost)}`);
  if (reward.contribution_cost) chunks.push(`消耗贡献 ${Number(reward.contribution_cost)}`);
  if (reward.auction_cost) chunks.push(`消耗声望 ${Number(reward.auction_cost)}`);
  if (reward.item_costs && typeof reward.item_costs === "object") {
    const costs = Array.isArray(reward.item_costs)
      ? reward.item_costs.map((item) => `${ITEM_LABELS[item.item_key || item.key] || item.name || item.item_key || item.key} x${Number(item.quantity || item.qty || 0)}`)
      : Object.entries(reward.item_costs).map(([key, value]) => `${ITEM_LABELS[key] || key} x${Number(value || 0)}`);
    if (costs.length) chunks.push(`消耗物品 ${costs.join("、")}`);
  }
  if (Array.isArray(reward.item_drops)) {
    const drops = reward.item_drops.map((item) => {
      const min = Number(item.min ?? item.quantity_min ?? 1);
      const max = Number(item.max ?? item.quantity_max ?? min);
      const chance = Number(item.chance ?? 100);
      const name = ITEM_LABELS[item.item_key || item.key] || item.name || item.item_key || item.key;
      return `${name} ${min}-${max}${chance < 100 ? ` / ${chance}%` : ""}`;
    });
    if (drops.length) chunks.push(`掉落 ${drops.join("、")}`);
  }
  if (reward.success_percent) chunks.push(`成功率 ${Number(reward.success_percent)}%`);
  return chunks.join(" · ");
}

function normalizeItemCostText(value) {
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        const key = item.item_key || item.key;
        const qty = Number(item.quantity || item.qty || 0);
        if (!key || qty <= 0) return "";
        return `${ITEM_LABELS[key] || item.name || key} x${qty}`;
      })
      .filter(Boolean);
  }
  return Object.entries(value)
    .map(([key, qty]) => Number(qty || 0) > 0 ? `${ITEM_LABELS[key] || key} x${Number(qty || 0)}` : "")
    .filter(Boolean);
}

function describeAlchemyRecipe(action = {}) {
  const reward = action.reward_config || {};
  const costs = normalizeItemCostText(reward.item_costs);
  if (reward.gold_cost) costs.push(`金币 x${Number(reward.gold_cost)}`);
  if (reward.core_cost) costs.push(`魔核 x${Number(reward.core_cost)}`);
  const products = Array.isArray(reward.item_drops)
    ? reward.item_drops.map((item) => {
        const key = item.item_key || item.key;
        const min = Number(item.min ?? item.quantity_min ?? 1);
        const max = Number(item.max ?? item.quantity_max ?? min);
        const chance = Number(item.chance ?? 100);
        const qty = min === max ? `${min}` : `${min}-${max}`;
        return `${ITEM_LABELS[key] || item.name || key} x${qty}${chance < 100 ? ` / ${chance}%` : ""}`;
      }).filter(Boolean)
    : [];
  if (!costs.length && !products.length) return "";
  return `${costs.join(" + ") || "无材料"} -> ${products.join("、") || "成品待配置"}`;
}

function describeRequirement(action = {}) {
  const req = action.requirement_config || {};
  const chunks = [];
  if (req.realm_stage_min) chunks.push(`境界 ${req.realm_stage_min}`);
  if (req.realm_stars_min) chunks.push(`${Number(req.realm_stars_min)} 星`);
  if (req.gold_min) chunks.push(`金币 ${Number(req.gold_min)}`);
  if (req.core_min) chunks.push(`魔核 ${Number(req.core_min)}`);
  if (req.alchemy_min) chunks.push(`炼药 ${Number(req.alchemy_min)}`);
  if (req.fire_min) chunks.push(`火候 ${Number(req.fire_min)}`);
  if (req.sect_contribution_min) chunks.push(`贡献 ${Number(req.sect_contribution_min)}`);
  if (req.pill_min) chunks.push(`丹药 ${Number(req.pill_min)}`);
  if (req.technique_level_min) chunks.push(`斗技 ${Number(req.technique_level_min)}`);
  if (req.fire_progress_min) chunks.push(`线索 ${Number(req.fire_progress_min)}`);
  if (req.boss_score_min) chunks.push(`Boss ${Number(req.boss_score_min)}`);
  if (req.tower_floor_min) chunks.push(`塔层 ${Number(req.tower_floor_min)}`);
  if (req.auction_credit_min) chunks.push(`拍卖 ${Number(req.auction_credit_min)}`);
  return chunks.length ? chunks.join(" · ") : "无门槛";
}

function statItem(label, value, note = "") {
  return `
    <article class="profile-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </article>
  `;
}

function renderProfile(bundle = {}) {
  const profile = bundle.profile || {};
  const growth = bundle.growth || {};
  const economy = bundle.economy || {};
  const pillInventoryTotal = inventoryCategoryTotal(bundle, "pill");
  const heavenlyFire = profile.heavenly_fire || {};
  const technique = profile.technique || {};
  const current = number(growth.douqi_current);
  const cap = number(growth.douqi_per_star);
  const pct = percent(current, cap);

  setText("#realm-badge", profile.realm_stage || "斗之气");
  setText("#star-pill", `${number(profile.realm_stars || 1)} 星`);
  setText("#battle-pill", `战力 ${number(profile.battle_power)}`);
  setText("#hero-douqi", `${current} / ${cap}`);
  setText("#hero-gold", number(profile.gold));
  setText("#hero-fire", heavenlyFire.name || profile.fire_name || "未收服");
  setText("#hero-coin", number(bundle.emby_balance));
  setText("#hero-note", `${profile.display_name || `TG ${profile.tg || "-"}`} · ${profile.sect_name || "未入宗门"} · ${profile.sect_name ? (profile.sect_rank || "外门弟子") : "未入宗门"}`);
  setText("#growth-title", `${growth.realm_stage || profile.realm_stage || "斗之气"} ${number(profile.realm_stars || 1)} 星`);
  setText("#growth-percent", `${pct}%`);
  let growthNote = "当前已到达开放境界上限。";
  if (growth.next_realm_stage && growth.breakthrough_ready) {
    const pity = growth.breakthrough || {};
    growthNote = `斗气已经圆满，可冲击 ${growth.next_realm_stage}；突破保底 ${number(pity.failures)} / ${number(pity.pity_after)}。`;
  } else if (growth.next_realm_stage && growth.requires_breakthrough) {
    growthNote = `已到当前境界瓶颈，还需 ${number(growth.douqi_to_next_star)} 斗气圆满后冲击 ${growth.next_realm_stage}。`;
  } else if (growth.next_realm_stage) {
    growthNote = `距下一星还需 ${number(growth.douqi_to_next_star)} 斗气；升至 ${number(growth.star_cap)} 星并圆满后方可冲击 ${growth.next_realm_stage}。`;
  }
  setText("#growth-note", growthNote);

  const bar = qs("#growth-bar");
  if (bar) bar.style.width = `${pct}%`;

  const profileGrid = qs("#profile-grid");
  if (profileGrid) {
    profileGrid.innerHTML = [
      statItem("角色", profile.display_name || `TG ${profile.tg || "-"}`),
      statItem("境界", `${profile.realm_stage || "-"} · ${number(profile.realm_stars || 1)} 星`),
      statItem("战力", number(profile.battle_power)),
      statItem("宗门", profile.sect_name ? `${profile.sect_name} · ${profile.sect_rank || "外门弟子"}` : "未入宗门"),
      statItem("斗技", `${technique.name || profile.technique_name || "未习得"} · ${number(technique.level || profile.technique_level)} 级`),
      statItem("异火", heavenlyFire.name || profile.fire_name || "未收服"),
    ].join("");
  }

  const resourceGrid = qs("#resource-grid");
  if (resourceGrid) {
    const cap = number(economy.daily_gold_action_cap);
    const incomeText = cap > 0 ? `${number(economy.gold_income)} / ${cap}` : number(economy.gold_income);
    const trainUsage = bundle.daily_usage?.items?.train || {};
    const trainText = number(trainUsage.limit) > 0 ? `${number(trainUsage.used)} / ${number(trainUsage.limit)}` : `${number(trainUsage.used)} / 不限`;
    const actionPoints = bundle.daily_usage?.action_points || {};
    const pointText = number(actionPoints.limit) > 0 ? `${number(actionPoints.used)} / ${number(actionPoints.limit)}` : `${number(actionPoints.used)} / 不限`;
    const douqiIncome = bundle.daily_usage?.douqi_income || {};
    const douqiText = number(douqiIncome.hard_cap) > 0
      ? `${number(douqiIncome.earned)} / ${number(douqiIncome.hard_cap)}`
      : number(douqiIncome.earned);
    resourceGrid.innerHTML = [
      statItem("金币", number(profile.gold)),
      statItem("今日行动力", pointText),
      statItem("今日成长斗气", douqiText, `软上限 ${number(douqiIncome.soft_cap)}，超额 ${number(douqiIncome.overflow_percent)}%`),
      statItem("今日行动金币", incomeText),
      statItem("今日修炼次数", trainText),
      statItem("今日金币回收", number(economy.gold_sink)),
      statItem("魔核", number(profile.beast_core)),
      statItem("背包丹药", pillInventoryTotal),
      statItem("宗门贡献", number(profile.sect_contribution)),
      statItem("炼药经验", number(profile.alchemy_exp)),
      statItem("异火火候", number(profile.fire_seed)),
      statItem("异火线索", number(profile.fire_progress)),
      statItem("Boss战绩", number(profile.boss_score)),
      statItem("塔层", number(profile.tower_floor)),
    ].join("");
  }
}

function renderInventory(bundle = {}) {
  const equipmentRoot = qs("#equipment-summary");
  const summary = qs("#inventory-summary");
  const root = qs("#inventory-groups");
  if (!root) return;
  const inventory = bundle.inventory || {};
  const categories = Array.isArray(inventory.categories) ? inventory.categories : [];
  const equipment = inventory.equipment || bundle.profile?.equipment || {};
  const equipmentStats = equipment.stats || {};
  if (equipmentRoot) {
    const slots = equipment.slots || {};
    const labels = equipment.slot_labels || {};
    equipmentRoot.innerHTML = `
      <div class="equipment-head">
        <div><p class="eyebrow">当前装备</p><h3>六槽装备栏</h3></div>
        <span class="tag">战力 +${number(equipment.battle_power_bonus)}</span>
      </div>
      <div class="equipment-slots">
        ${Object.entries(labels).map(([slot, label]) => {
          const item = slots[slot];
          return `<article class="equipment-slot ${item ? "is-filled" : ""}">
            <span>${escapeHtml(label)}</span>
            <strong>${item ? `${itemIconHtml(item.icon, item.name)} ${escapeHtml(item.name)}` : "未装备"}</strong>
            ${item ? `<button type="button" class="ghost mini" data-unequip-item="${escapeHtml(item.item_key)}">卸下</button>` : ""}
          </article>`;
        }).join("")}
      </div>
      <div class="equipment-stats">
        ${[["攻击", "attack"], ["防御", "defense"], ["身法", "agility"], ["异火", "fire_bonus"], ["炼药", "alchemy_bonus"]].map(([label, key]) => `<span>${label} <strong>${number(equipmentStats[key])}</strong></span>`).join("")}
      </div>`;
  }
  if (summary) {
    summary.innerHTML = `
      <article class="inventory-stat">
        <span>物品种类</span>
        <strong>${number(inventory.total_unique)}</strong>
      </article>
      <article class="inventory-stat">
        <span>物品总量</span>
        <strong>${number(inventory.total_quantity)}</strong>
      </article>
      <article class="inventory-stat">
        <span>分类数量</span>
        <strong>${categories.length}</strong>
      </article>
    `;
  }
  root.innerHTML = categories.map((category) => {
    const items = Array.isArray(category.items) ? category.items : [];
    const itemHtml = items.map((item) => {
      const stats = item.equipment || {};
      const statText = [["攻", "attack"], ["防", "defense"], ["身法", "agility"], ["异火", "fire_bonus"], ["炼药", "alchemy_bonus"]]
        .filter(([, key]) => number(stats[key]) > 0)
        .map(([label, key]) => `${label} +${number(stats[key])}`)
        .join(" · ");
      return `
      <article class="inventory-item">
        <div>
          <strong>${itemIconHtml(item.icon, item.name)} ${escapeHtml(item.name || ITEM_LABELS[item.item_key] || item.item_key)}</strong>
          <span>${escapeHtml(item.rarity || "凡品")}${statText ? ` · ${escapeHtml(statText)}` : ""}</span>
        </div>
        <div class="inventory-item-actions">
          <b>x${number(item.quantity)}</b>
          ${item.equipment?.slot ? `<button type="button" class="ghost mini" data-${item.equipped ? "unequip" : "equip"}-item="${escapeHtml(item.item_key)}">${item.equipped ? "卸下" : "穿戴"}</button>` : ""}
        </div>
      </article>
    `; }).join("");
    return `
      <section class="inventory-category ${items.length ? "" : "is-empty"}">
        <div class="inventory-category-head">
          <div>
            <strong>${escapeHtml(category.name || category.key)}</strong>
            <p>${escapeHtml(category.description || "")}</p>
          </div>
          <span class="tag">总量 ${number(category.total_quantity)}</span>
        </div>
        <div class="inventory-items">
          ${itemHtml || `<article class="inventory-empty">暂无物品</article>`}
        </div>
      </section>
    `;
  }).join("");
  root.querySelectorAll("[data-equip-item]").forEach((button) => button.addEventListener("click", () => changeEquipment("equip", button.dataset.equipItem, button)));
  document.querySelectorAll("[data-unequip-item]").forEach((button) => button.addEventListener("click", () => changeEquipment("unequip", button.dataset.unequipItem, button)));
}

async function changeEquipment(operation, itemKey, button) {
  if (!itemKey) return;
  setButtonBusy(button, true, operation === "equip" ? "穿戴中..." : "卸下中...");
  try {
    const result = await postJson(`/plugins/doupo/api/inventory/${operation}`, { item_key: itemKey });
    state.data = result;
    renderAll(result);
    setStatus(result.detail || (operation === "equip" ? "装备已穿戴" : "装备已卸下"));
    showToast(result.detail || "装备状态已更新");
  } catch (error) {
    const message = String(error.message || error);
    setStatus(message, "error");
    showToast(message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function featureProgress(current, target) {
  if (!target || number(target) <= 0) return "";
  const pct = percent(current, target);
  return `
    <div class="module-progress">
      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
    </div>
  `;
}

function renderFeatureOverview(bundle = {}) {
  const root = qs("#feature-overview");
  if (!root) return;
  const features = bundle.features || {};
  const pillInventoryTotal = inventoryCategoryTotal(bundle, "pill");
  const heavenlyFire = features.heavenly_fire || {};
  const technique = features.technique || {};
  const rows = [
    {
      label: "宗门",
      value: features.sect?.joined ? `${features.sect?.name || "宗门"} · ${features.sect?.rank || "外门弟子"}` : "未入宗门",
      meta: `贡献 ${number(features.sect?.contribution)} / ${number(features.sect?.next?.contribution) || "-"}`,
      current: features.sect?.contribution,
      target: features.sect?.next?.contribution,
    },
    {
      label: "炼药",
      value: `${features.alchemy?.rank || "未入品"} · 背包丹药 ${pillInventoryTotal}`,
      meta: `经验 ${number(features.alchemy?.exp)} / ${number(features.alchemy?.next?.exp) || "-"}`,
      current: features.alchemy?.exp,
      target: features.alchemy?.next?.exp,
    },
    {
      label: "异火",
      value: heavenlyFire.name || `线索：${heavenlyFire.next?.name || "青莲地心火"}`,
      meta: `进度 ${number(heavenlyFire.progress)} / ${number(heavenlyFire.next?.progress) || 100}`,
      current: heavenlyFire.progress,
      target: heavenlyFire.next?.progress || 100,
    },
    {
      label: "斗技",
      value: `${technique.name || "未习得"} · ${number(technique.level)} 级`,
      meta: technique.next?.name ? `下阶段 ${technique.next.name}` : "斗技已同步",
    },
    { label: "拍卖", value: features.auction?.title || "初入拍场", meta: `声望 ${number(features.auction?.credit)}` },
    { label: "Boss", value: features.boss?.title || "试炼者", meta: `战绩 ${number(features.boss?.score)}` },
    { label: "塔修", value: features.tower?.title || "初入塔修", meta: `第 ${number(features.tower?.floor)} 层` },
  ];

  root.innerHTML = rows.map((item) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(item.label)}</strong>
        <span class="tag">${escapeHtml(item.value)}</span>
      </div>
      <p>${escapeHtml(item.meta)}</p>
      ${featureProgress(item.current, item.target)}
    </article>
  `).join("");
}

function renderSectChoice(bundle = {}) {
  const root = qs("#sect-choice");
  if (!root) return;
  const profile = bundle.profile || {};
  const sects = Array.isArray(bundle.sects) ? bundle.sects : [];
  const panel = bundle.sect_panel || state.sectPanel || null;
  if (bundle.sect_panel) state.sectPanel = bundle.sect_panel;
  if (profile.sect_name && panel) {
    renderSectPanel(root, profile, panel);
    return;
  }
  if (profile.sect_name) {
    root.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(profile.sect_name)}</strong>
          <span class="tag">${escapeHtml(profile.sect_rank || "外门弟子")}</span>
        </div>
        <p>你已加入当前宗门，宗门任务、贡献和斗技阁会按该势力推进。</p>
      </article>
    `;
    return;
  }
  root.innerHTML = sects.map((sect) => `
    <article class="sect-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(sect.name)}</strong>
        <span class="tag">${escapeHtml(sect.realm_stage_min || "斗之气")}</span>
      </div>
      <p>${escapeHtml(sect.description || "")}</p>
      <p class="meta-line">${escapeHtml(sect.bonus || "")}</p>
      <button type="button" data-sect-key="${escapeHtml(sect.key)}">加入</button>
    </article>
  `).join("") || `<article class="stack-item"><strong>暂无宗门</strong><p>宗门配置暂未开放。</p></article>`;
  root.querySelectorAll("[data-sect-key]").forEach((button) => {
    button.addEventListener("click", async () => {
      const sectKey = button.getAttribute("data-sect-key");
      if (!sectKey) return;
      setButtonBusy(button, true, "加入中...");
      try {
        const result = await postJson("/plugins/doupo/api/sect/join", { sect_key: sectKey });
        state.data = result;
        renderAll(result);
        setStatus(`已加入：${result.profile?.sect_name || "宗门"}`);
        showToast(`已加入：${result.profile?.sect_name || "宗门"}`);
      } catch (error) {
        const message = String(error.message || error);
        setStatus(message, "error");
        showToast(message, "error");
      } finally {
        setButtonBusy(button, false);
      }
    });
  });
}

function renderSectPanel(root, profile, panel) {
  const quest = panel.quest || {};
  const members = Array.isArray(panel.members) ? panel.members : [];
  const transfer = panel.transfer || {};
  const rewards = quest.rewards || {};
  const multiplier = Number(quest.multiplier || 1);
  const rewardText = [
    `贡献 +${number(Math.round((Number(rewards.contribution) || 0) * multiplier))}`,
    `金币 +${number(Math.round((Number(rewards.gold) || 0) * multiplier))}`,
    `斗气 +${number(Math.round((Number(rewards.douqi) || 0) * multiplier))}`,
  ].join("、");
  root.innerHTML = `
    <article class="stack-item sect-panel">
      <div class="stack-item-head">
        <div>
          <p class="eyebrow">宗门面板</p>
          <strong>${escapeHtml(profile.sect_name)}</strong>
        </div>
        <span class="tag">${escapeHtml(quest.rank || profile.sect_rank || "外门弟子")}</span>
      </div>
      <p class="meta-line">贡献 ${number(profile.sect_contribution)} · 委托倍率 x${number(multiplier)}</p>
      <div class="sect-quest">
        <div>
          <strong>每日宗门委托</strong>
          <p>${escapeHtml(rewardText)}</p>
        </div>
        <button type="button" data-sect-quest ${quest.claimed ? "disabled" : ""}>${quest.claimed ? "今日已领取" : "领取委托"}</button>
      </div>
      <div class="sect-actions">
        <button type="button" data-sect-transfer>转宗</button>
        <button type="button" data-sect-leave>离开宗门</button>
      </div>
      <p class="meta-line">转宗费 ${number(transfer.cost || 0)}${transfer.remaining_days > 0 ? ` · 冷却 ${number(transfer.remaining_days)} 天` : ""} · 离宗费 ${number(panel.leave_cost || 0)}</p>
      ${members.length ? `
        <div class="sect-members">
          <strong>同门 · ${number(members.length)}</strong>
          ${members.map((member) => `
            <div class="sect-member">
              <span class="sect-member-name">${escapeHtml(member.display_name)}</span>
              <span class="tag">${escapeHtml(member.sect_rank)}</span>
              <span class="sect-member-meta">${escapeHtml(member.realm_stage)} ${number(member.realm_stars)}星 · 贡献 ${number(member.sect_contribution)} · 战力 ${number(member.battle_power)}</span>
            </div>
          `).join("")}
        </div>
      ` : ""}
    </article>
  `;
  root.querySelector("[data-sect-quest]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setButtonBusy(button, true, "领取中...");
    try {
      const result = await postJson("/plugins/doupo/api/sect/quest/claim", {});
      state.data = result;
      renderAll(result);
      const detail = result.detail || "委托完成";
      setStatus(detail);
      showToast(detail);
    } catch (error) {
      const message = String(error.message || error);
      setStatus(message, "error");
      showToast(message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  });
  root.querySelector("[data-sect-transfer]")?.addEventListener("click", () => renderSectTransfer(root));
  root.querySelector("[data-sect-leave]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    if (!window.confirm("确认离开当前宗门？宗门贡献将清零，且进入转宗冷却。")) return;
    setButtonBusy(button, true, "处理中...");
    try {
      const result = await postJson("/plugins/doupo/api/sect/leave", {});
      state.data = result;
      state.sectPanel = null;
      renderAll(result);
      const detail = result.detail || "已离开宗门";
      setStatus(detail);
      showToast(detail);
    } catch (error) {
      const message = String(error.message || error);
      setStatus(message, "error");
      showToast(message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  });
}

function renderSectTransfer(root) {
  const profile = state.data?.profile || {};
  const sects = Array.isArray(state.data?.sects) ? state.data.sects : [];
  const currentName = profile.sect_name;
  const targets = sects.filter((sect) => sect.name !== currentName);
  root.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>选择转宗目标</strong>
        <span class="tag">当前 ${escapeHtml(currentName || "无")}</span>
      </div>
      ${targets.map((sect) => `
        <div class="sect-item">
          <div class="stack-item-head">
            <strong>${escapeHtml(sect.name)}</strong>
            <span class="tag">${escapeHtml(sect.realm_stage_min || "斗之气")}</span>
          </div>
          <p>${escapeHtml(sect.description || "")}</p>
          <p class="meta-line">${escapeHtml(sect.bonus || "")}</p>
          <button type="button" data-sect-transfer-key="${escapeHtml(sect.key)}">转入此宗</button>
        </div>
      `).join("")}
      <button type="button" data-sect-back class="sect-back-button">返回面板</button>
    </article>
  `;
  root.querySelectorAll("[data-sect-transfer-key]").forEach((button) => {
    button.addEventListener("click", async () => {
      const sectKey = button.getAttribute("data-sect-transfer-key");
      if (!sectKey) return;
      setButtonBusy(button, true, "转宗中...");
      try {
        const result = await postJson("/plugins/doupo/api/sect/transfer", { sect_key: sectKey });
        state.data = result;
        renderAll(result);
        const detail = result.detail || "转宗成功";
        setStatus(detail);
        showToast(detail);
      } catch (error) {
        const message = String(error.message || error);
        setStatus(message, "error");
        showToast(message, "error");
      } finally {
        setButtonBusy(button, false);
      }
    });
  });
  root.querySelector("[data-sect-back]")?.addEventListener("click", () => renderAll(state.data || {}));
}

function actionTypes(actions) {
  const available = new Set(actions.map((item) => item.action_type).filter(Boolean));
  return ACTION_ORDER.filter((key) => key === "all" || available.has(key));
}

function renderActionTabs(actions) {
  const root = qs("#action-type-tabs");
  if (!root) return;
  const types = actionTypes(actions);
  if (!types.includes(state.actionFilter)) state.actionFilter = "all";
  root.innerHTML = types.map((type) => `
    <button type="button" class="${type === state.actionFilter ? "is-active" : ""}" data-action-filter="${escapeHtml(type)}">
      ${escapeHtml(ACTION_LABELS[type] || type)}
    </button>
  `).join("");
  root.querySelectorAll("[data-action-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.actionFilter = button.getAttribute("data-action-filter") || "all";
      renderActions(state.data || {});
    });
  });
}

function renderActions(bundle = {}) {
  const allActions = Array.isArray(bundle.actions) ? bundle.actions : [];
  renderActionTabs(allActions);
  const actions = state.actionFilter === "all"
    ? allActions
    : allActions.filter((action) => action.action_type === state.actionFilter);
  const usage = bundle.daily_usage?.items || {};
  const actionCard = (action) => {
    const delta = describeDelta(action);
    const isCraftRecipe = ["alchemy", "craft"].includes(action.action_type);
    const recipe = isCraftRecipe ? describeAlchemyRecipe(action) : "";
    const lockRemaining = actionLockRemaining(action.action_key);
    const serverDisabled = action.available === false;
    const disabledReason = lockRemaining > 0
      ? `冷却中，请等待 ${lockRemaining} 秒`
      : String(action.disabled_reason || "");
    const disabled = lockRemaining > 0 || serverDisabled;
    const buttonText = lockRemaining > 0 ? `冷却 ${lockRemaining}s` : (disabled ? "暂不可用" : "执行");
    const typeUsage = usage[action.action_type] || {};
    const limitText = number(typeUsage.limit) > 0
      ? `今日 ${number(typeUsage.used)} / ${number(typeUsage.limit)}`
      : "今日不限次";
    return `
      <article class="action-item">
        <div class="action-head">
          <strong>${escapeHtml(action.name || action.action_key)}</strong>
          <span class="action-type">${escapeHtml(action.action_type_label || action.action_type || "行动")}</span>
        </div>
        <p class="action-copy">${escapeHtml(action.description || "")}</p>
        <div class="meta-line">行动力 ${number(action.action_point_cost)} · 冷却 ${number(action.cooldown_seconds)} 秒 · ${escapeHtml(limitText)} · 门槛 ${escapeHtml(action.requirement_summary || describeRequirement(action))}</div>
        ${recipe ? `<div class="meta-line action-recipe">${action.action_type === "craft" ? "器方" : "丹方"} ${escapeHtml(recipe)}</div>` : ""}
        <div class="meta-line ${delta.includes("消耗") ? "action-cost" : "action-reward"}">${escapeHtml(delta || "无固定收益")}</div>
        ${disabledReason ? `<div class="meta-line action-disabled-reason">${escapeHtml(disabledReason)}</div>` : ""}
        <button data-action-key="${escapeHtml(action.action_key)}" data-cooldown="${number(action.cooldown_seconds)}" type="button" ${disabled ? "disabled" : ""}>${escapeHtml(buttonText)}</button>
      </article>
    `;
  };
  const bindRunButtons = (root) => {
    root?.querySelectorAll("button[data-action-key]").forEach((button) => {
      button.addEventListener("click", async () => {
        const key = button.getAttribute("data-action-key");
        if (!key) return;
        setButtonBusy(button, true, "执行中...");
        try {
          const result = await postJson("/plugins/doupo/api/action/run", { action_key: key });
          lockAction(key, Number(button.getAttribute("data-cooldown") || 0));
          state.data = result;
          renderAll(result);
          setStatus(`执行完成：${result.action_name || "行动"}`);
          showToast(result.detail || `执行完成：${result.action_name || "行动"}`);
        } catch (error) {
          const message = String(error.message || error);
          setStatus(message, "error");
          showToast(message, "error");
        } finally {
          setButtonBusy(button, false);
        }
      });
    });
  };

  ACTION_GROUPS.forEach((group) => {
    const card = qs(`#action-card-${group.key}`);
    const root = qs(`#actions-${group.key}`);
    if (!card || !root) return;
    const visible = actions.filter((action) => group.types.includes(action.action_type));
    card.classList.toggle("hidden", !visible.length);
    root.innerHTML = visible.map(actionCard).join("") || `<article class="stack-item"><strong>暂无行动</strong><p>当前模块暂未开放行动。</p></article>`;
    bindRunButtons(root);
  });

  const leftovers = actions.filter((action) => !ACTION_GROUPS.some((group) => group.types.includes(action.action_type)));
  const otherCard = qs("#action-card-other");
  const otherRoot = qs("#actions-other");
  otherCard?.classList.toggle("hidden", !leftovers.length);
  if (otherRoot) {
    otherRoot.innerHTML = leftovers.map(actionCard).join("");
    bindRunButtons(otherRoot);
  }

  const legacyRoot = qs("#actions");
  if (!legacyRoot) return;
  const sections = [];
  if (leftovers.length) {
    sections.push(`
      <section class="action-section">
        <div class="action-section-head">
          <div>
            <h3>其他行动</h3>
            <p>后台新增但尚未归类的拓展行动。</p>
          </div>
          <span class="tag">${leftovers.length}项</span>
        </div>
        <div class="action-section-grid">
          ${leftovers.map(actionCard).join("")}
        </div>
      </section>
    `);
  }
  legacyRoot.innerHTML = sections.join("") || `<article class="stack-item"><strong>暂无行动</strong><p>当前没有可执行行动。</p></article>`;
  bindRunButtons(legacyRoot);
}

function expeditionItemText(rows = []) {
  if (!Array.isArray(rows) || !rows.length) return "暂无物品";
  return rows.map((item) => `${item.name || ITEM_LABELS[item.item_key] || item.item_key} x${number(item.quantity)}`).join("、");
}

function expeditionStatusLabel(status) {
  return {
    completed: "完成游历",
    retreated: "安全撤离",
    failed: "重伤撤回",
  }[status] || "游历结束";
}

async function runExpeditionRequest(path, body, button, busyText) {
  setButtonBusy(button, true, busyText);
  try {
    const result = await postJson(path, body);
    state.expeditionChoiceKey = "";
    state.data = result;
    renderAll(result);
    setStatus(result.detail || "游历状态已更新");
    showToast(result.detail || "游历状态已更新");
  } catch (error) {
    const message = String(error.message || error);
    setStatus(message, "error");
    showToast(message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function renderExpedition(bundle = {}) {
  const root = qs("#expedition-root");
  if (!root) return;
  const overview = bundle.expedition || {};
  const active = overview.active;
  if (!active) {
    const latest = overview.last_run;
    const latestHtml = latest ? `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>上次：${escapeHtml(latest.region_name || "游历")}</strong>
          <span class="tag">${escapeHtml(expeditionStatusLabel(latest.status))}</span>
        </div>
        <p>带回斗气 ${number(latest.settlement?.douqi)}、金币 ${number(latest.settlement?.gold)}${latest.settlement?.gold_capped ? `，${number(latest.settlement.gold_capped)} 金币触及上限` : ""}${latest.settlement?.douqi_capped ? `，${number(latest.settlement.douqi_capped)} 斗气受衰减` : ""}${latest.settlement?.douqi_bottleneck ? `，${number(latest.settlement.douqi_bottleneck)} 斗气受瓶颈限制` : ""}</p>
        <p>${escapeHtml(expeditionItemText(latest.settlement?.item_rows || []))}</p>
      </article>
    ` : "";
    const regions = Array.isArray(overview.regions) ? overview.regions : [];
    const daily = overview.daily_usage || {};
    const expeditionPoints = overview.action_points || {};
    const dailyText = number(daily.limit) > 0 ? `今日游历 ${number(daily.used)} / ${number(daily.limit)}` : "今日游历不限次";
    root.innerHTML = `
      <div class="stack-item-head"><strong>${escapeHtml(dailyText)}</strong><span class="tag">行动力 ${number(expeditionPoints.cost)} · 剩余 ${expeditionPoints.remaining == null ? "不限" : number(expeditionPoints.remaining)}</span></div>
      ${latestHtml}
      <div class="expedition-regions">
        ${regions.map((region) => `
          <article class="expedition-region">
            <div class="stack-item-head">
              <strong>${escapeHtml(region.name)}</strong>
              <span class="tag">${number(region.max_steps)} 段</span>
            </div>
            <p>${escapeHtml(region.description || "")}</p>
            <p class="meta-line">门槛 ${escapeHtml(region.realm_stage_min)} · 建议战力 ${number(region.recommended_power)} · 补给 ${number(region.entry_gold)} 金币</p>
            ${region.boss ? `<p class="meta-line expedition-boss-hint">首领 ${escapeHtml(region.boss.name)} · 战力 ${number(region.boss.power)} · 需 ${escapeHtml(region.boss.realm_stage_min)}</p>` : ""}
            ${region.disabled_reason ? `<p class="action-disabled-reason">${escapeHtml(region.disabled_reason)}</p>` : ""}
            <button type="button" data-expedition-start="${escapeHtml(region.key)}" ${region.available ? "" : "disabled"}>进入区域</button>
          </article>
        `).join("")}
      </div>
    `;
    root.querySelectorAll("[data-expedition-start]").forEach((button) => {
      button.addEventListener("click", () => runExpeditionRequest(
        "/plugins/doupo/api/expedition/start",
        { region_key: button.getAttribute("data-expedition-start") },
        button,
        "整备中...",
      ));
    });
    return;
  }

  const vitalityPercent = percent(active.vitality, active.max_vitality);
  const loot = active.loot || {};
  const event = active.current_event || {};
  const eventKind = event.kind || "normal";
  const kindBadge = eventKind === "boss"
    ? '<span class="tag expedition-tag-boss">首领讨伐</span>'
    : eventKind === "hidden"
      ? '<span class="tag expedition-tag-hidden">隐藏机缘</span>'
      : "";
  const bossPowerLine = eventKind === "boss" && event.boss_power
    ? `<p class="eyebrow">${escapeHtml(event.boss_name || "区域首领")} · 战力 ${number(event.boss_power)}</p>`
    : "";
  const choices = Array.isArray(event.choices) ? event.choices : [];
  const selectedChoice = choices.some((choice) => choice.key === state.expeditionChoiceKey)
    ? state.expeditionChoiceKey
    : (choices[0]?.key || "");
  state.expeditionChoiceKey = selectedChoice;
  const history = Array.isArray(active.history) ? [...active.history].reverse().slice(0, 4) : [];
  const trail = Array.from({ length: number(active.max_steps) }, (_, index) => {
    const step = index + 1;
    const status = step <= number(active.step) ? "is-complete" : step === number(active.step) + 1 ? "is-active" : "";
    return `<span class="expedition-trail-node ${status}"><b>${step}</b></span>`;
  }).join('<i class="expedition-trail-line"></i>');
  root.innerHTML = `
    <div class="expedition-layout">
      <article class="expedition-event">
        <div class="stack-item-head">
          <div>
            <p class="eyebrow">${escapeHtml(active.region_name)}</p>
            ${bossPowerLine}
            <strong>${escapeHtml(event.title || "前路未明")}</strong>
          </div>
          <div class="expedition-head-tags">
            ${kindBadge}
            <span class="tag">第 ${number(active.step) + 1} / ${number(active.max_steps)} 段</span>
          </div>
        </div>
        <div class="expedition-trail" aria-label="游历进度">${trail}</div>
        <p class="expedition-event-story">${escapeHtml(event.story || "前方的气息仍在变化。")}</p>
        <div class="expedition-choices" data-expedition-carousel tabindex="0">
          ${choices.map((choice) => `
            <button type="button" class="expedition-choice ${choice.key === selectedChoice ? "is-selected" : ""}" data-expedition-choice="${escapeHtml(choice.key)}">
              <div>
                <strong>${escapeHtml(choice.label)}</strong>
                <p>${escapeHtml(choice.description || "")}</p>
                <span class="expedition-choice-meta">${escapeHtml(choice.risk)} · 成功率 ${number(choice.success_chance)}%</span>
              </div>
              <span class="expedition-choice-mark" aria-hidden="true">${choice.key === selectedChoice ? "◆" : "◇"}</span>
            </button>
          `).join("")}
        </div>
        <div class="expedition-focus">
          <div class="expedition-focus-head">
            <div>
              <p class="eyebrow">斗气操控</p>
              <strong id="expedition-focus-state">${selectedChoice ? "准备凝聚" : "先选择路线"}</strong>
            </div>
            <span class="tag">${selectedChoice ? "待机" : "锁定"}</span>
          </div>
          <div class="expedition-focus-track" aria-hidden="true">
            <span class="expedition-focus-target"></span>
            <span class="expedition-focus-cursor"></span>
          </div>
          <button type="button" class="expedition-channel" data-expedition-channel ${selectedChoice ? "" : "disabled"}>按住凝聚斗气</button>
        </div>
      </article>
      <aside class="expedition-sidebar">
        <div class="expedition-stats">
          <div class="expedition-stat"><span>体力</span><strong>${number(active.vitality)} / ${number(active.max_vitality)}</strong></div>
          <div class="expedition-stat"><span>路程</span><strong>${number(active.step)} / ${number(active.max_steps)}</strong></div>
          <div class="expedition-stat"><span>危险</span><strong>${number(active.danger)} / 10</strong></div>
        </div>
        <div class="expedition-vitality">
          <div class="progress-track"><div class="progress-fill" style="width:${vitalityPercent}%"></div></div>
        </div>
        <div class="expedition-loot">
          <div><span>暂存斗气</span><strong>${number(loot.douqi)}</strong></div>
          <div><span>暂存金币</span><strong>${number(loot.gold)}</strong></div>
          <div style="grid-column:1/-1"><span>暂存物品</span><strong>${escapeHtml(expeditionItemText(loot.item_rows || []))}</strong></div>
        </div>
        ${history.length ? `
          <div class="expedition-history">
            ${history.map((item) => `
              <article class="expedition-history-item ${item.success ? "" : "is-failure"}">
                <strong>${escapeHtml(item.event_title)} · ${escapeHtml(item.choice_label)}</strong>
                <p>${escapeHtml(item.summary || "")}</p>
              </article>
            `).join("")}
          </div>
        ` : ""}
        <button type="button" class="ghost expedition-retreat" data-expedition-retreat ${active.can_retreat ? "" : "disabled"}>携带 70% 收获撤离</button>
      </aside>
    </div>
  `;
  const choiceCards = [...root.querySelectorAll("[data-expedition-choice]")];
  const choiceList = root.querySelector("[data-expedition-carousel]");
  const channel = root.querySelector("[data-expedition-channel]");
  const focusState = root.querySelector("#expedition-focus-state");
  const cursor = root.querySelector(".expedition-focus-cursor");
  const chooseIndex = (index, focus = true) => {
    if (!choiceCards.length) return;
    const safeIndex = (index + choiceCards.length) % choiceCards.length;
    state.expeditionChoiceKey = choiceCards[safeIndex].getAttribute("data-expedition-choice") || "";
    choiceCards.forEach((card, cardIndex) => {
      const activeCard = cardIndex === safeIndex;
      card.classList.toggle("is-selected", activeCard);
      const mark = card.querySelector(".expedition-choice-mark");
      if (mark) mark.textContent = activeCard ? "◆" : "◇";
    });
    if (channel) channel.disabled = false;
    if (focusState) focusState.textContent = "准备凝聚";
    if (focus) choiceCards[safeIndex].focus();
  };
  choiceCards.forEach((card, index) => card.addEventListener("click", () => chooseIndex(index)));
  let touchStartX = null;
  choiceList?.addEventListener("touchstart", (event) => {
    touchStartX = event.touches?.[0]?.clientX ?? null;
  }, { passive: true });
  choiceList?.addEventListener("touchend", (event) => {
    if (touchStartX == null) return;
    const endX = event.changedTouches?.[0]?.clientX ?? touchStartX;
    const delta = endX - touchStartX;
    touchStartX = null;
    if (Math.abs(delta) < 36) return;
    const currentIndex = Math.max(choiceCards.findIndex((card) => card.classList.contains("is-selected")), 0);
    chooseIndex(currentIndex + (delta < 0 ? 1 : -1));
  }, { passive: true });
  choiceList?.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = Math.max(choiceCards.findIndex((card) => card.classList.contains("is-selected")), 0);
    chooseIndex(currentIndex + (event.key === "ArrowRight" ? 1 : -1));
  });
  let charging = false;
  let chargeStartedAt = 0;
  let chargeFrame = 0;
  let chargeValue = 50;
  const updateCharge = (now) => {
    if (!charging) return;
    const cycle = ((now - chargeStartedAt) % 1500) / 1500;
    chargeValue = cycle <= 0.5 ? cycle * 200 : (1 - cycle) * 200;
    if (cursor) cursor.style.left = `${chargeValue}%`;
    chargeFrame = window.requestAnimationFrame(updateCharge);
  };
  const submitChoice = (score) => {
    if (charging) charging = false;
    if (chargeFrame) window.cancelAnimationFrame(chargeFrame);
    const choiceKey = state.expeditionChoiceKey;
    if (!choiceKey || !channel || channel.disabled) return;
    channel.disabled = true;
    if (focusState) focusState.textContent = score >= 90 ? "完美释放" : score >= 75 ? "稳定释放" : score >= 55 ? "斗气成形" : "气息紊乱";
    runExpeditionRequest(
      "/plugins/doupo/api/expedition/choose",
      { choice_key: choiceKey, focus_score: Math.round(score) },
      channel,
      "斗气碰撞...",
    );
  };
  const startCharge = (event) => {
    if (!channel || channel.disabled || charging) return;
    event.preventDefault();
    charging = true;
    chargeStartedAt = window.performance.now();
    if (channel.setPointerCapture && event.pointerId != null) channel.setPointerCapture(event.pointerId);
    if (focusState) focusState.textContent = "引导火劲...";
    chargeFrame = window.requestAnimationFrame(updateCharge);
  };
  const finishCharge = (event) => {
    if (!charging) return;
    event?.preventDefault?.();
    const now = window.performance.now();
    updateCharge(now);
    const focusScore = Math.max(0, 100 - Math.abs(chargeValue - 75) * 4);
    submitChoice(focusScore);
  };
  channel?.addEventListener("pointerdown", startCharge);
  channel?.addEventListener("pointerup", finishCharge);
  channel?.addEventListener("pointercancel", finishCharge);
  channel?.addEventListener("click", () => {
    if (!charging && channel && !channel.disabled) submitChoice(50);
  });
  channel?.addEventListener("keydown", (event) => {
    if (event.key !== " ") return;
    event.preventDefault();
    if (!charging) startCharge(event);
  });
  channel?.addEventListener("keyup", (event) => {
    if (event.key !== " ") return;
    event.preventDefault();
    finishCharge(event);
  });
  const retreat = root.querySelector("[data-expedition-retreat]");
  retreat?.addEventListener("click", () => {
    if (!window.confirm("现在撤离只能带回 70% 暂存收获，确定撤离？")) return;
    runExpeditionRequest("/plugins/doupo/api/expedition/retreat", {}, retreat, "撤离中...");
  });
}

function renderJournals(bundle = {}) {
  const root = qs("#journal-list");
  if (!root) return;
  const rows = Array.isArray(bundle.journals) ? bundle.journals : [];
  root.innerHTML = rows.map((item) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(item.title || "")}</strong>
        <span class="tag">${escapeHtml((item.created_at || "").slice(0, 16).replace("T", " "))}</span>
      </div>
      <p>${escapeHtml(item.detail || "")}</p>
    </article>
  `).join("") || `<article class="stack-item"><strong>暂无记录</strong><p>完成行动或兑换后会显示在这里。</p></article>`;
}

function renderExchangeHint(bundle = {}) {
  const settings = bundle.settings || {};
  const enabled = Boolean(settings.exchange_enabled);
  setText("#exchange-hint", enabled
    ? `当前汇率：1 碎片 = ${number(settings.exchange_rate || 100)} 金币；金币换碎片最低 ${number(settings.min_gold_to_exchange || 100)} 金币。`
    : "兑换功能当前关闭。");
  qs("#coin-to-gold-btn").disabled = !enabled;
  qs("#gold-to-coin-btn").disabled = !enabled;
}

function renderPlaybook(bundle = {}) {
  const root = qs("#playbook");
  if (!root) return;
  const modules = Array.isArray(bundle.playbook) ? bundle.playbook : [];
  root.innerHTML = modules.map((item) => `
    <article class="module-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="tag">${escapeHtml(item.status)}</span>
      </div>
      <p class="module-copy">${escapeHtml(item.description)}</p>
    </article>
  `).join("");
}

function renderBottomNav(items = []) {
  const nav = qs("#bottom-nav");
  if (!nav) return;
  const currentPath = window.location.pathname;
  nav.innerHTML = "";
  nav.classList.toggle("hidden", !items.length);
  for (const item of items) {
    const link = document.createElement("a");
    link.href = item.path;
    link.textContent = `${item.icon || ""} ${item.label}`.trim();
    if (item.path === currentPath) link.classList.add("is-active");
    nav.appendChild(link);
  }
  requestAnimationFrame(updateBottomNavHeight);
}

function visibleFoldCards() {
  return qsa(".fold-card").filter((card) => !card.classList.contains("hidden"));
}

function syncFoldToolbar() {
  const cards = visibleFoldCards();
  const toolbar = qs("#fold-toolbar");
  toolbar?.classList.toggle("hidden", cards.length < 2);
  setText("#fold-count", `(${cards.length})`);
  const shortcuts = qs("#fold-shortcuts");
  if (shortcuts) {
    shortcuts.innerHTML = cards.map((card) => {
      const title = card.querySelector("h2")?.textContent || card.id || "模块";
      return `<button type="button" data-target="${escapeHtml(card.id)}">${escapeHtml(title)}</button>`;
    }).join("");
    shortcuts.querySelectorAll("[data-target]").forEach((button) => {
      button.addEventListener("click", () => {
        const card = qs(`#${button.getAttribute("data-target")}`);
        if (!card) return;
        card.open = true;
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }
  const openAll = qs("[data-fold-open-all]");
  const closeAll = qs("[data-fold-close-all]");
  if (openAll) openAll.disabled = !cards.some((card) => !card.open);
  if (closeAll) closeAll.disabled = !cards.some((card) => card.open);
}

function toggleFoldCards(open) {
  visibleFoldCards().forEach((card) => {
    card.open = open;
  });
  syncFoldToolbar();
}

function updateBottomNavHeight() {
  const nav = qs("#bottom-nav");
  const height = nav && !nav.classList.contains("hidden") ? Math.ceil(nav.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty("--bottom-nav-height", `${height}px`);
}

function hasTelegramInitData() {
  return Boolean(window.Telegram?.WebApp?.initData);
}

function setAuthSession(payload = {}) {
  const token = String(payload.session_token || state.sessionToken || "").trim();
  if (token) {
    state.sessionToken = token;
    localStorage.setItem("doupo_web_session_token", token);
  }
  state.authAccount = payload.account || null;
}

function clearAuthSession() {
  state.sessionToken = "";
  state.authAccount = null;
  localStorage.removeItem("doupo_web_session_token");
}

function renderAuthPanel(mode = "") {
  const card = qs("#auth-card");
  if (!card) return;
  const account = state.authAccount;
  const hasSession = Boolean(state.sessionToken && account);
  const isBound = Boolean(account?.bound);
  const requestedMode = String(mode || "").trim();
  let activeMode = requestedMode || state.authMode || "login";
  if (hasSession && !isBound) activeMode = "bind";
  if (hasSession && isBound && activeMode === "bind") activeMode = "account";
  if (!hasSession && ["bind", "account"].includes(activeMode)) activeMode = "login";
  if (hasSession && isBound && !requestedMode) activeMode = "account";
  state.authMode = activeMode;
  const shouldShow = Boolean(requestedMode) || !hasSession || !isBound;
  card.classList.toggle("hidden", !shouldShow);
  card.setAttribute("aria-hidden", shouldShow ? "false" : "true");
  card.inert = !shouldShow;
  qs("#auth-login-form")?.classList.toggle("hidden", activeMode !== "login");
  qs("#auth-register-form")?.classList.toggle("hidden", activeMode !== "register");
  qs("#auth-bind-panel")?.classList.toggle("hidden", !["bind", "account"].includes(activeMode));
  qs(".tab-row")?.classList.toggle("hidden", hasSession);
  qsa("[data-auth-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.getAttribute("data-auth-mode") === activeMode);
  });
  setText("#auth-account-name", account?.display_name || account?.username || "网页账号");
  const bindButton = qs("#auth-bind-telegram");
  if (bindButton) {
    bindButton.disabled = !hasTelegramInitData();
    bindButton.classList.toggle("hidden", isBound);
  }
  qs("#auth-close")?.classList.toggle("hidden", !(isBound && activeMode === "account"));
  setText("#auth-bind-state", isBound ? "已绑定" : "待绑定");
  setText("#auth-status", isBound
    ? `${account?.telegram_label || `TG ${account?.tg || ""}`} 已绑定，可进入修仙与斗破。`
    : hasSession
      ? "账号已登录，完成 Telegram 绑定后才可进入游戏。"
      : "修仙与斗破共用账号，完成 TG 绑定后才可进入游戏。"
  );
  setText(
    "#auth-bind-hint",
    isBound
      ? `${account?.telegram_label || `TG ${account?.tg || ""}`} 已绑定。`
      : hasTelegramInitData()
        ? "点击绑定后会使用当前 Telegram 身份完成验证。"
        : "账号已登录，请从 Telegram Mini App 打开一次完成绑定。"
  );
}

function setGameLocked(locked) {
  document.body.classList.toggle("auth-locked", Boolean(locked));
}

function syncAdminEntry(bundle = state.data || {}) {
  const capabilities = bundle?.capabilities || {};
  const adminUrl = capabilities.admin_panel_url;
  const visible = Boolean(capabilities.is_admin && adminUrl);
  const root = qs("#hero-admin-entry");
  const button = qs("#open-admin-panel");
  const fab = qs("#fab-admin");
  root?.classList.toggle("hidden", !visible);
  fab?.classList.toggle("hidden", !visible);
  if (button) {
    button.disabled = !visible;
    button.dataset.adminUrl = visible ? adminUrl : "";
  }
  if (fab) fab.dataset.adminUrl = visible ? adminUrl : "";
}

function openAdminPanel() {
  const adminUrl = qs("#open-admin-panel")?.dataset.adminUrl
    || qs("#fab-admin")?.dataset.adminUrl
    || state.data?.capabilities?.admin_panel_url;
  if (!adminUrl) return;
  window.location.href = withReturnTo(adminUrl) || adminUrl;
}

async function restoreWebSession() {
  if (!state.sessionToken) {
    renderAuthPanel("login");
    return false;
  }
  try {
    const payload = await authPostJson("/plugins/doupo/api/auth/me", { session_token: state.sessionToken });
    state.authAccount = payload.account || null;
    if (!state.authAccount) {
      clearAuthSession();
      renderAuthPanel("login");
      return false;
    }
    if (!state.authAccount.bound) {
      setGameLocked(true);
      renderAuthPanel("bind");
      setStatus("完成 Telegram 绑定后即可进入斗破。", "error");
      return false;
    }
    state.initData = state.telegramInitData || `web_session:${state.sessionToken}`;
    renderAuthPanel("");
    return true;
  } catch (error) {
    clearAuthSession();
    renderAuthPanel("login");
    setStatus(String(error.message || error), "error");
    return false;
  }
}

function renderAll(bundle = {}) {
  renderProfile(bundle);
  renderInventory(bundle);
  renderActions(bundle);
  renderExpedition(bundle);
  renderJournals(bundle);
  renderExchangeHint(bundle);
  renderFeatureOverview(bundle);
  renderSectChoice(bundle);
  renderPlaybook(bundle);
  renderBottomNav(bundle.bottom_nav || []);
  syncAdminEntry(bundle);
  syncFoldToolbar();
}

async function bootstrap() {
  const runtime = await resolveRuntime();
  if (runtime) {
    runtime.ready();
    runtime.expand();
    runtime.hideBackButton();
    state.telegramInitData = runtime.initData;
    state.user = runtime.user;
  }
  const authenticated = await restoreWebSession();
  if (!authenticated) return;
  setGameLocked(false);
  renderAuthPanel("");
  const bundle = await postJson("/plugins/doupo/api/bootstrap");
  state.data = bundle;
  setGameLocked(false);
  setStatus("斗破修炼已连接");
  renderAll(bundle);
}

async function runExchange(direction) {
  const amount = Number(qs("#exchange-amount")?.value || 0);
  if (!Number.isFinite(amount) || amount <= 0) {
    showToast("请输入有效数量。", "error");
    qs("#exchange-amount")?.focus();
    return;
  }
  const button = qs(direction === "coin_to_gold" ? "#coin-to-gold-btn" : "#gold-to-coin-btn");
  setButtonBusy(button, true, "兑换中...");
  try {
    const result = await postJson("/plugins/doupo/api/exchange", { direction, amount: Math.floor(amount) });
    state.data = result;
    setStatus(direction === "coin_to_gold" ? "碎片已兑换金币" : "金币已兑换碎片");
    showToast(direction === "coin_to_gold" ? "碎片已兑换金币" : "金币已兑换碎片");
    renderAll(result);
  } catch (error) {
    const message = String(error.message || error);
    setStatus(message, "error");
    showToast(message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function setupPage() {
  qsa("[data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => renderAuthPanel(button.getAttribute("data-auth-mode") || "login"));
  });
  qs("#auth-login-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = qs("#auth-login-submit");
    setButtonBusy(button, true, "登录中...");
    try {
      const payload = await authPostJson("/plugins/doupo/api/auth/login", {
        username: qs("#auth-login-username")?.value || "",
        password: qs("#auth-login-password")?.value || "",
        init_data: hasTelegramInitData() ? window.Telegram.WebApp.initData : "",
      });
      setAuthSession(payload);
      setStatus(payload.account?.bound ? "登录成功，正在同步斗破状态。" : "登录成功，请完成 Telegram 绑定。");
      if (payload.account?.bound) {
        state.initData = state.telegramInitData || `web_session:${state.sessionToken}`;
        await bootstrap();
      } else {
        renderAuthPanel("bind");
      }
    } catch (error) {
      const message = String(error.message || error);
      setStatus(message, "error");
      showToast(message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  });
  qs("#auth-register-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = String(qs("#auth-register-password")?.value || "");
    const confirm = String(qs("#auth-register-confirm")?.value || "");
    if (password !== confirm) {
      showToast("两次密码不一致。", "error");
      return;
    }
    const button = qs("#auth-register-submit");
    setButtonBusy(button, true, "注册中...");
    try {
      const payload = await authPostJson("/plugins/doupo/api/auth/register", {
        username: qs("#auth-register-username")?.value || "",
        display_name: qs("#auth-register-display")?.value || "",
        password,
        init_data: hasTelegramInitData() ? window.Telegram.WebApp.initData : "",
      });
      setAuthSession(payload);
      setStatus(payload.account?.bound ? "注册成功，正在同步斗破状态。" : "注册成功，请完成 Telegram 绑定。");
      if (payload.account?.bound) {
        state.initData = state.telegramInitData || `web_session:${state.sessionToken}`;
        await bootstrap();
      } else {
        renderAuthPanel("bind");
      }
    } catch (error) {
      const message = String(error.message || error);
      setStatus(message, "error");
      showToast(message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  });
  qs("#auth-bind-telegram")?.addEventListener("click", async () => {
    if (!hasTelegramInitData()) {
      showToast("请从 Telegram Mini App 打开此页完成绑定。", "error");
      return;
    }
    const button = qs("#auth-bind-telegram");
    setButtonBusy(button, true, "绑定中...");
    try {
      const payload = await authPostJson("/plugins/doupo/api/auth/bind-telegram", {
        session_token: state.sessionToken,
        init_data: window.Telegram.WebApp.initData,
      });
      state.authAccount = payload.account || null;
      state.initData = state.telegramInitData || `web_session:${state.sessionToken}`;
      showToast("绑定成功");
      await bootstrap();
    } catch (error) {
      const message = String(error.message || error);
      setStatus(message, "error");
      showToast(message, "error");
    } finally {
      setButtonBusy(button, false);
    }
  });
  qs("#auth-logout")?.addEventListener("click", async () => {
    const token = state.sessionToken;
    clearAuthSession();
    state.initData = "";
    setGameLocked(true);
    if (token) {
      try {
        await authPostJson("/plugins/doupo/api/auth/logout", { session_token: token });
      } catch {}
    }
    renderAuthPanel("login");
    setStatus("已退出网页账号。");
  });
  qs("#open-account-center")?.addEventListener("click", () => {
    renderAuthPanel("account");
    qs("#auth-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  qs("#open-admin-panel")?.addEventListener("click", openAdminPanel);
  qs("#fab-admin")?.addEventListener("click", openAdminPanel);
  qs("#auth-close")?.addEventListener("click", () => renderAuthPanel(""));
  qs("#coin-to-gold-btn")?.addEventListener("click", () => runExchange("coin_to_gold"));
  qs("#gold-to-coin-btn")?.addEventListener("click", () => runExchange("gold_to_coin"));
  qs("#focus-actions")?.addEventListener("click", () => {
    const card = qs("#action-card-train");
    if (card) {
      card.open = true;
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  qs("#focus-exchange")?.addEventListener("click", () => {
    const card = qs("#exchange-card");
    if (card) {
      card.open = true;
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  qs("[data-fold-open-all]")?.addEventListener("click", () => toggleFoldCards(true));
  qs("[data-fold-close-all]")?.addEventListener("click", () => toggleFoldCards(false));
  qsa(".fold-card").forEach((card) => card.addEventListener("toggle", syncFoldToolbar));
  window.addEventListener("resize", updateBottomNavHeight);
  syncFoldToolbar();
}

setupPage();
if (!state.sessionToken) renderAuthPanel("login");
bootstrap().catch((error) => {
  const message = String(error.message || error);
  setStatus(message, "error");
  showToast(message, "error");
});
