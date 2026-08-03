const LEVEL_META = {
  a: {
    text: "白名单用户",
    shortText: "白名单",
    description: "最高权限，畅享全部内容。",
    tone: "vip"
  },
  b: {
    text: "普通用户",
    shortText: "普通",
    description: "已绑定账号，畅享观影。",
    tone: "normal"
  },
  c: {
    text: "已封禁",
    shortText: "封禁",
    description: "账号已被封禁，如有疑问请联系管理员。",
    tone: "danger"
  },
  d: {
    text: "未注册",
    shortText: "未注册",
    description: "还没绑定账号，用注册码开通或联系管理员。",
    tone: "pending"
  }
};

const MINIAPP_BOOTSTRAP_CACHE_PREFIX = "miniapp_bootstrap";
const LOCAL_TEST_DEFAULT_ID = 1001001;

let currentInviteBundle = null;
let currentMiniAppUserId = "default";
let currentRuntime = null;
let currentBootstrapData = null;
let currentPlugins = [];
let pluginFilter = "all";
let pluginSearch = "";

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return [...document.querySelectorAll(selector)];
}

function setText(selector, value) {
  const node = qs(selector);
  if (node) {
    node.textContent = value ?? "-";
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getLevelMeta(code) {
  return LEVEL_META[(code || "").toLowerCase()] || {
    text: "未知",
    shortText: "未知",
    description: "暂时无法获取账号状态。",
    tone: "unknown"
  };
}

function normalizeError(error) {
  const message = String(error?.message || "").trim();
  if (
    !message
    || message === "Failed to fetch"
    || message.startsWith("Unexpected token")
    || message.includes("Unexpected end of JSON input")
  ) {
    return "网络连接失败，请稍后重试。";
  }
  if (message === "Internal Server Error") {
    return "服务器繁忙，请稍后再试。";
  }
  return message;
}

async function readResponsePayload(response) {
  const raw = await response.text();
  if (!raw) {
    return { code: response.ok ? 200 : response.status, data: null };
  }
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(raw.trim() || "Internal Server Error");
  }
}

function formatDate(value, fallback = "") {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? fallback : date.toLocaleString("zh-CN");
}

function currentRelativePath() {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

function toSameOriginPath(path, fallback = "") {
  if (!path) return fallback;
  try {
    const url = new URL(path, window.location.origin);
    if (url.origin !== window.location.origin) {
      return fallback;
    }
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
  if (safeReturnTo) {
    url.searchParams.set("return_to", safeReturnTo);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

function readLocalStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocalStorage(key, value) {
  try {
    if (value == null) {
      window.localStorage.removeItem(key);
      return;
    }
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be disabled in some embedded browsers.
  }
}

function miniAppBootstrapCacheKey(userId) {
  return `${MINIAPP_BOOTSTRAP_CACHE_PREFIX}:${userId || "anon"}`;
}

function hydrateMiniAppBootstrapCache(userId) {
  const raw = readLocalStorage(miniAppBootstrapCacheKey(userId));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.telegram_user || !parsed.meta) {
      writeLocalStorage(miniAppBootstrapCacheKey(userId), null);
      return null;
    }
    return parsed;
  } catch {
    writeLocalStorage(miniAppBootstrapCacheKey(userId), null);
    return null;
  }
}

function storeMiniAppBootstrapCache(userId, payload) {
  if (!payload || typeof payload !== "object") return;
  writeLocalStorage(miniAppBootstrapCacheKey(userId), JSON.stringify({ ...payload, cached_at: new Date().toISOString() }));
}

function showToast(message, type = "info") {
  const stack = qs("#toast-stack");
  if (!stack) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  stack.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 3600);
}

function setSyncState(text, tone = "neutral") {
  const node = qs("#sync-state");
  if (!node) return;
  node.textContent = text;
  node.className = "soft-pill";
  if (tone === "success") node.classList.add("badge--normal");
  if (tone === "warning") node.classList.add("badge--vip");
  if (tone === "error") node.classList.add("badge--danger");
}

function setButtonBusy(button, busy, busyText = "处理中...") {
  if (!button) return "";
  const previous = button.dataset.previousText || button.textContent || "";
  if (busy) {
    button.dataset.previousText = previous;
    button.disabled = true;
    button.textContent = busyText;
    return previous;
  }
  button.disabled = false;
  button.textContent = previous;
  delete button.dataset.previousText;
  return previous;
}

function resolveDisplayName(user) {
  return user?.first_name || user?.last_name || user?.username || "未知用户";
}

function isLocalHost() {
  return ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
}

function getMiniAppRuntime() {
  const tg = window.Telegram?.WebApp;
  if (tg?.initData) {
    return {
      initData: tg.initData,
      user: tg.initDataUnsafe?.user || {},
      ready: () => tg.ready?.(),
      expand: () => tg.expand?.(),
      hideBackButton: () => tg.BackButton?.hide?.(),
      localTest: false
    };
  }

  if (isLocalHost()) {
    const params = new URLSearchParams(window.location.search);
    const userId = Number(params.get("test_user") || LOCAL_TEST_DEFAULT_ID);
    const safeUserId = Number.isFinite(userId) && userId > 0 ? Math.trunc(userId) : LOCAL_TEST_DEFAULT_ID;
    const username = params.get("test_name") || "miniapp_tester";
    const firstName = params.get("test_display") || "本地测试用户";
    return {
      initData: `local_test:${safeUserId}:${username}:${firstName}`,
      user: {
        id: safeUserId,
        username,
        first_name: firstName
      },
      ready: () => {},
      expand: () => {},
      hideBackButton: () => {},
      localTest: true
    };
  }

  return null;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function resolveMiniAppRuntime() {
  const immediate = getMiniAppRuntime();
  if (immediate || isLocalHost()) {
    return immediate;
  }

  const deadline = Date.now() + 1600;
  while (Date.now() < deadline) {
    await sleep(80);
    const runtime = getMiniAppRuntime();
    if (runtime) {
      return runtime;
    }
  }
  return null;
}

function updateBottomNavHeight() {
  const nav = qs("#bottom-nav");
  const height = nav && !nav.classList.contains("hidden") ? Math.ceil(nav.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty("--bottom-nav-height", `${height}px`);
}

function renderBottomNav(items) {
  const nav = qs("#bottom-nav");
  if (!nav) return;
  const currentPath = window.location.pathname;
  nav.innerHTML = "";
  nav.classList.toggle("hidden", !(items || []).length);

  for (const item of items || []) {
    const link = document.createElement("a");
    link.href = item.path;
    link.textContent = `${item.icon || ""} ${item.label}`.trim();
    if (item.path === currentPath) {
      link.classList.add("is-active");
    }
    nav.appendChild(link);
  }
  requestAnimationFrame(updateBottomNavHeight);
}

function sortPluginsForUser(plugins, userId) {
  const sorted = [...plugins];
  const savedOrderStr = readLocalStorage(`miniapp_order_${userId}`);
  if (!savedOrderStr) return sorted;

  try {
    const savedOrder = JSON.parse(savedOrderStr);
    sorted.sort((a, b) => {
      const nameA = a.miniapp_label || a.name || "";
      const nameB = b.miniapp_label || b.name || "";
      let indexA = savedOrder.indexOf(nameA);
      let indexB = savedOrder.indexOf(nameB);
      if (indexA === -1) indexA = 9999;
      if (indexB === -1) indexB = 9999;
      return indexA - indexB || nameA.localeCompare(nameB, "zh-Hans-CN");
    });
  } catch {
    writeLocalStorage(`miniapp_order_${userId}`, null);
  }
  return sorted;
}

function filteredPlugins() {
  const keyword = pluginSearch.trim().toLowerCase();
  return currentPlugins.filter((plugin) => {
    const hasError = Boolean(plugin.error);
    if (pluginFilter === "running" && (!plugin.loaded || hasError)) return false;
    if (pluginFilter === "issue" && !hasError) return false;
    if (!keyword) return true;
    const haystack = [
      plugin.id,
      plugin.name,
      plugin.miniapp_label,
      plugin.description,
      plugin.version
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(keyword);
  });
}

function renderPlugins() {
  const pluginGrid = qs("#plugin-grid");
  if (!pluginGrid) return;
  const items = filteredPlugins();
  pluginGrid.innerHTML = "";

  if (!items.length) {
    pluginGrid.innerHTML = `
      <article class="empty-state">
        <strong>没有匹配的功能</strong>
        <p>换个关键词或切回全部筛选。</p>
      </article>
    `;
    return;
  }

  for (const plugin of items) {
    const item = document.createElement("article");
    const hasError = Boolean(plugin.error);
    const stateClass = hasError ? "is-error" : plugin.loaded ? "is-on" : "is-off";
    const stateText = hasError ? "异常" : plugin.loaded ? "运行中" : "未启用";
    const mark = escapeHtml(String(plugin.miniapp_icon || plugin.icon || plugin.name?.slice?.(0, 1) || "功").trim().slice(0, 2));
    const description = escapeHtml(plugin.description || "暂无描述信息。");
    const name = escapeHtml(plugin.miniapp_label || plugin.name || "未命名功能");
    const version = escapeHtml(plugin.version || "v0.0");
    const errorText = hasError ? `<p class="plugin-warning">${escapeHtml(plugin.error)}</p>` : "";

    item.className = "plugin-item";
    item.dataset.openPath = plugin.miniapp_path || "";
    item.innerHTML = `
      <div class="plugin-mark">${mark}</div>
      <div class="plugin-main">
        <div class="plugin-head">
          <strong class="plugin-title">${name}</strong>
          <span class="plugin-state ${stateClass}">${stateText}</span>
        </div>
        <p class="plugin-copy">${description}</p>
        ${errorText}
        <div class="plugin-foot">
          <span class="plugin-meta">${version}</span>
          <button class="plugin-open" type="button">进入</button>
        </div>
      </div>
    `;
    pluginGrid.appendChild(item);
  }
}

function firstAvailablePlugin() {
  return currentPlugins.find((plugin) => plugin.loaded && !plugin.error && plugin.miniapp_path)
    || currentPlugins.find((plugin) => plugin.miniapp_path)
    || null;
}

function renderPrimaryAction(account, permissions) {
  const plugin = firstAvailablePlugin();
  const primaryButton = qs("#primary-plugin-button");
  const nextButton = qs("#next-action-button");
  const inviteButton = qs("#invite-shortcut-button");

  if (primaryButton) {
    primaryButton.disabled = !plugin;
    primaryButton.textContent = plugin ? `进入${plugin.miniapp_label || plugin.name || "功能"}` : "暂无功能";
    primaryButton.onclick = plugin ? () => { window.location.href = plugin.miniapp_path; } : null;
  }

  if (inviteButton) {
    inviteButton.onclick = () => qs("#invite-shell")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (!account) {
    setText("#next-action-title", "开通账号");
    setText("#next-action-tag", "待绑定");
    setText("#next-action-text", "当前 Telegram 账号还没有绑定 Emby 用户。");
    if (nextButton) {
      nextButton.textContent = "查看账户";
      nextButton.onclick = () => qs("#account-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }

  const invite = currentInviteBundle || {};
  const permissionsInvite = invite.permissions || {};
  if (permissionsInvite.has_invite_qualification || permissionsInvite.has_account_open_application_qualification) {
    setText("#next-action-title", "处理邀请");
    setText("#next-action-tag", "可操作");
    setText("#next-action-text", "你当前有可用邀请或开通申请资格。");
    if (nextButton) {
      nextButton.textContent = "进入邀请中心";
      nextButton.onclick = () => qs("#invite-shell")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }

  if (permissions?.is_admin) {
    setText("#next-action-title", "管理后台");
    setText("#next-action-tag", "管理员");
    setText("#next-action-text", "当前账号拥有后台管理权限。");
    if (nextButton) {
      nextButton.textContent = "进入后台";
      nextButton.onclick = () => {
        const adminUrl = withReturnTo(permissions.admin_url || "/admin");
        if (adminUrl) window.location.href = adminUrl;
      };
    }
    return;
  }

  setText("#next-action-title", plugin ? "继续使用" : "账户正常");
  setText("#next-action-tag", plugin ? "推荐" : "完成");
  setText("#next-action-text", plugin ? `可以直接进入 ${plugin.miniapp_label || plugin.name || "常用功能"}。` : "你的账户状态正常。");
  if (nextButton) {
    nextButton.textContent = plugin ? "进入功能" : "刷新状态";
    nextButton.onclick = plugin ? () => { window.location.href = plugin.miniapp_path; } : () => bootstrapMiniApp({ force: true });
  }
}

function renderInviteRecords(records = [], type = "group_join") {
  const root = qs(type === "account_open" ? "#invite-open-records" : "#invite-records");
  if (!root) return;
  if (!records.length) {
    root.innerHTML = `
      <article class="empty-state">
        <strong>暂无记录</strong>
        <p>${type === "account_open" ? "开通申请提交后会显示在这里。" : "邀请链接发送后会显示在这里。"}</p>
      </article>
    `;
    return;
  }
  root.innerHTML = records.map((item) => {
    const status = escapeHtml(item.status_text || item.status || "待处理");
    const title = type === "account_open" ? `申请 TG ${escapeHtml(item.invitee_tg)}` : `邀请 TG ${escapeHtml(item.invitee_tg)}`;
    const mainMeta = type === "account_open"
      ? `申请天数：${escapeHtml(item.invite_days || 0)} 天`
      : `目标群：${escapeHtml(item.target_chat_id || "-")}`;
    const secondMeta = type === "account_open"
      ? `审核：${escapeHtml(formatDate(item.reviewed_at, "待审核"))}`
      : `过期：${escapeHtml(formatDate(item.expires_at, "未设置"))}`;
    return `
      <article class="record-item">
        <div class="record-head">
          <strong>${title}</strong>
          <span class="record-status">${status}</span>
        </div>
        <p>${mainMeta} · 创建：${escapeHtml(formatDate(item.created_at, "未知"))}</p>
        <p>${secondMeta}</p>
      </article>
    `;
  }).join("");
}

function renderInviteBundle(invite = {}) {
  currentInviteBundle = invite || {};
  const shell = qs("#invite-shell");
  const settings = invite.settings || {};
  const permissions = invite.permissions || {};
  const groupJoin = invite.group_join || invite || {};
  const accountOpen = invite.account_open || {};
  const enabled = Boolean(settings.enabled);

  shell?.classList.toggle("hidden", !enabled);
  if (!enabled) {
    renderPrimaryAction(currentBootstrapData?.account, currentBootstrapData?.permissions);
    return;
  }

  const groupCount = Number(groupJoin.available_credits || invite.available_credits || 0);
  const accountCount = Number(accountOpen.available_credits || 0);
  const availableTotal = groupCount + accountCount;
  const canCreateGroup = Boolean(permissions.can_create && groupCount > 0);
  const canCreateOpen = Boolean(permissions.can_create && permissions.has_account_open_application_qualification);

  setText("#invite-total-pill", `${availableTotal} 项可用`);
  setText("#invite-credit-count", String(groupCount));
  setText("#invite-expire-hours", `${settings.expire_hours || 24} 小时`);
  setText("#invite-open-credit-count", String(accountCount));
  setText("#invite-open-days", `${settings.account_open_days || 30} 天`);

  if (!permissions.has_viewing_access && groupCount <= 0) {
    setText("#invite-status", "当前账号没有 Emby 观影资格，暂时不能获取入群资格。");
  } else if (permissions.group_invite_revoked) {
    setText("#invite-status", "你的入群邀请资格已被撤销。");
  } else if (groupCount <= 0) {
    setText("#invite-status", permissions.group_invite_used ? "你已经使用过本次入群邀请资格。" : "当前没有可用的入群邀请资格。");
  } else {
    setText("#invite-status", "填写被邀请人的 TGID 后，机器人会私聊发送专属链接。");
  }

  if (!permissions.has_viewing_access) {
    setText("#invite-open-status", "当前账号没有 Emby 观影资格，暂时不能提交开通申请。");
  } else if (permissions.account_open_application_revoked) {
    setText("#invite-open-status", "你的开通申请资格已被撤销。");
  } else if (permissions.account_open_application_used) {
    setText("#invite-open-status", "你已经提交或完成过开通申请，不能重复申请。");
  } else if (accountCount <= 0) {
    setText("#invite-open-status", "当前没有可用的账号开通申请资格。");
  } else {
    setText("#invite-open-status", "填写未开通用户的 TGID 后，提交给管理员审核。");
  }

  const groupSubmit = qs("#invite-submit");
  if (groupSubmit && !groupSubmit.dataset.previousText) {
    groupSubmit.disabled = !canCreateGroup;
    groupSubmit.textContent = canCreateGroup ? "发送邀请链接" : "暂无可用入群资格";
  }

  const openSubmit = qs("#invite-open-submit");
  if (openSubmit && !openSubmit.dataset.previousText) {
    openSubmit.disabled = !canCreateOpen;
    openSubmit.textContent = canCreateOpen ? "提交开通申请" : "暂无申请资格";
  }

  renderInviteRecords(groupJoin.records || invite.records || [], "group_join");
  renderInviteRecords(accountOpen.records || [], "account_open");
  renderPrimaryAction(currentBootstrapData?.account, currentBootstrapData?.permissions);
}

function renderMiniAppNotFound(userId) {
  writeLocalStorage(miniAppBootstrapCacheKey(userId), null);
  currentInviteBundle = null;
  currentPlugins = [];
  currentBootstrapData = null;
  document.title = "404";

  setText("#app-title", "404");
  setText("#welcome-text", "404");
  setText("#hero-title", "Not Found");
  setText("#hero-note", "当前账号不可访问。");
  setText("#account-level-desc", "Not Found");
  setText("#plugin-count", "0 个可用");
  setText("#plugin-count-pill", "0 个功能");
  setText("#role-pill", "不可访问");
  setSyncState("不可访问", "error");

  const badge = qs("#account-level-badge");
  if (badge) {
    badge.className = "badge badge--danger";
    badge.textContent = "404";
  }

  qs("#admin-entry-button")?.classList.add("hidden");
  qs("#invite-shell")?.classList.add("hidden");
  renderPlugins();
  renderBottomNav([]);
}

function applyMiniAppBootstrapData(data, userId, { fromCache = false } = {}) {
  const { telegram_user, account, meta, permissions } = data;
  const visiblePlugins = (meta.plugins || []).filter((item) => item.miniapp_path);
  currentBootstrapData = data;
  currentPlugins = sortPluginsForUser(visiblePlugins, userId);
  currentInviteBundle = data.invite || {};

  const loadedCount = currentPlugins.filter((item) => item.loaded && !item.error).length;
  const errorCount = currentPlugins.filter((item) => item.error).length;
  const levelMeta = getLevelMeta(account?.lv || (account ? "" : "d"));
  const displayName = resolveDisplayName(telegram_user);
  const accountTone = account?.lv_tone || levelMeta.tone;
  const appTitle = meta.brand || "Echo 面板";

  document.title = appTitle;
  setText("#app-title", appTitle);
  setText("#hero-title", appTitle);
  setText("#welcome-text", `欢迎回来，${displayName}`);
  setText("#role-pill", permissions?.is_admin ? "管理员" : "普通用户");
  setText("#plugin-count", `${loadedCount} / ${currentPlugins.length} 个可用`);
  setText("#plugin-count-pill", `${currentPlugins.length} 个功能`);
  setText("#brand-name", meta.brand || "Emby");
  setText("#currency-name", meta.currency || "积分");
  setText("#hero-name", displayName);
  setText("#hero-id", telegram_user.id || "-");

  setText("#tg-id", telegram_user.id || "-");
  setText("#tg-name", displayName);
  setText("#account-iv", account?.iv ?? 0);
  setText("#account-name", account?.name || "未绑定");
  setText("#account-ex", formatDate(account?.ex, "永久"));
  setText("#account-us", account?.us ?? 0);
  setText("#account-level-desc", account?.lv_description || levelMeta.description);
  setText("#account-state-pill", account?.name ? "已绑定" : "未绑定");

  const badge = qs("#account-level-badge");
  if (badge) {
    badge.className = `badge badge--${accountTone}`;
    badge.textContent = account?.lv_short_text || account?.lv_text || levelMeta.shortText || levelMeta.text;
  }

  const expiryText = account?.lv === "a" ? "无限期" : formatDate(account?.ex, "永久");
  setText(
    "#hero-note",
    account?.name
      ? `已绑定 ${account.name}，到期时间 ${expiryText}。${errorCount ? `有 ${errorCount} 个功能异常。` : ""}`
      : "当前 Telegram 账号还没有绑定 Emby 用户。"
  );

  const adminButton = qs("#admin-entry-button");
  if (permissions?.is_admin && permissions?.admin_url) {
    adminButton?.classList.remove("hidden");
    if (adminButton) {
      adminButton.onclick = () => {
        const adminUrl = withReturnTo(permissions.admin_url);
        if (adminUrl) window.location.href = adminUrl;
      };
    }
  } else {
    adminButton?.classList.add("hidden");
    if (adminButton) adminButton.onclick = null;
  }

  renderPlugins();
  renderBottomNav(meta.bottom_nav || []);
  renderInviteBundle(data.invite || {});
  setSyncState(fromCache ? "缓存数据" : "已同步", fromCache ? "warning" : "success");
}

function validateTargetTg(inputSelector) {
  const input = qs(inputSelector);
  const value = Number(input?.value || 0);
  if (!Number.isFinite(value) || value <= 0) {
    input?.focus();
    return { ok: false, message: "请填写有效的 Telegram ID。" };
  }
  if (String(Math.trunc(value)).length < 5) {
    input?.focus();
    return { ok: false, message: "Telegram ID 看起来不完整。" };
  }
  if (currentRuntime?.user?.id && Number(currentRuntime.user.id) === Math.trunc(value)) {
    input?.focus();
    return { ok: false, message: "不能把资格发送给自己。" };
  }
  return { ok: true, value: Math.trunc(value) };
}

async function createInviteFromMiniApp(event) {
  event.preventDefault();
  if (!currentRuntime) return;
  const validation = validateTargetTg("#invitee-tg");
  if (!validation.ok) {
    showToast(validation.message, "warning");
    return;
  }
  const note = qs("#invite-note")?.value?.trim() || "";
  const button = qs("#invite-submit");
  setButtonBusy(button, true, "发送中...");
  try {
    const response = await fetch("/miniapp-api/invites/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        init_data: currentRuntime.initData,
        invitee_tg: validation.value,
        note
      })
    });
    const result = await readResponsePayload(response);
    if (!response.ok || result.code !== 200) {
      throw new Error(result.detail || result.message || "邀请发送失败。");
    }
    renderInviteBundle(result.data?.invite || {});
    qs("#invite-form")?.reset();
    showToast("邀请链接已发送。", "success");
  } catch (error) {
    renderInviteBundle(currentInviteBundle || {});
    showToast(normalizeError(error), "error");
  } finally {
    setButtonBusy(button, false);
    renderInviteBundle(currentInviteBundle || {});
    storeMiniAppBootstrapCache(currentMiniAppUserId, {
      ...(hydrateMiniAppBootstrapCache(currentMiniAppUserId) || {}),
      invite: currentInviteBundle
    });
  }
}

async function createAccountOpenInviteFromMiniApp(event) {
  event.preventDefault();
  if (!currentRuntime) return;
  const validation = validateTargetTg("#invite-open-invitee-tg");
  if (!validation.ok) {
    showToast(validation.message, "warning");
    return;
  }
  const note = qs("#invite-open-note")?.value?.trim() || "";
  const button = qs("#invite-open-submit");
  setButtonBusy(button, true, "提交中...");
  try {
    const response = await fetch("/miniapp-api/invites/account-open/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        init_data: currentRuntime.initData,
        invitee_tg: validation.value,
        note
      })
    });
    const result = await readResponsePayload(response);
    if (!response.ok || result.code !== 200) {
      throw new Error(result.detail || result.message || "开通申请提交失败。");
    }
    renderInviteBundle(result.data?.invite || {});
    qs("#invite-open-form")?.reset();
    showToast("开通申请已提交。", "success");
  } catch (error) {
    renderInviteBundle(currentInviteBundle || {});
    showToast(normalizeError(error), "error");
  } finally {
    setButtonBusy(button, false);
    renderInviteBundle(currentInviteBundle || {});
    storeMiniAppBootstrapCache(currentMiniAppUserId, {
      ...(hydrateMiniAppBootstrapCache(currentMiniAppUserId) || {}),
      invite: currentInviteBundle
    });
  }
}

async function bootstrapMiniApp({ force = false } = {}) {
  const runtime = await resolveMiniAppRuntime();
  currentRuntime = runtime;

  if (!runtime) {
    setText("#welcome-text", "请在 Telegram 中打开此页面。");
    setText("#hero-title", "无法连接");
    setText("#hero-note", "当前环境没有 Telegram Mini App 数据。");
    setSyncState("未连接", "error");
    return;
  }

  runtime.ready();
  runtime.expand();
  runtime.hideBackButton();
  currentMiniAppUserId = runtime.user?.id || "default";
  const cachedData = hydrateMiniAppBootstrapCache(currentMiniAppUserId);

  if (cachedData && !force) {
    applyMiniAppBootstrapData(cachedData, currentMiniAppUserId, { fromCache: true });
  }

  setSyncState(force ? "刷新中" : "同步中");
  const refreshButton = qs("#refresh-button");
  setButtonBusy(refreshButton, true, "同步中");

  try {
    const response = await fetch("/miniapp-api/bootstrap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: runtime.initData })
    });
    const result = await readResponsePayload(response);

    if (!response.ok || result.code !== 200) {
      if (response.status === 404 || result.code === 404) {
        renderMiniAppNotFound(currentMiniAppUserId);
        return;
      }
      throw new Error(result.detail || result.message || "服务器连接失败。");
    }

    storeMiniAppBootstrapCache(currentMiniAppUserId, result.data);
    applyMiniAppBootstrapData(result.data, currentMiniAppUserId);
    if (runtime.localTest) {
      showToast("本地测试模式已连接。", "success");
    }
  } catch (error) {
    const message = normalizeError(error);
    if (!cachedData) {
      setText("#welcome-text", `连接失败：${message}`);
      setText("#hero-title", "同步失败");
      setText("#hero-note", "请检查网络后重试，或联系管理员。");
      setText("#account-level-desc", "账号状态未知。");
      setSyncState("失败", "error");
      currentPlugins = [];
      renderPlugins();
      renderBottomNav([]);
      showToast(message, "error");
      return;
    }
    applyMiniAppBootstrapData(cachedData, currentMiniAppUserId, { fromCache: true });
    setText("#hero-note", `已展示本地缓存，最新数据同步失败：${message}`);
    showToast(message, "warning");
  } finally {
    setButtonBusy(refreshButton, false);
  }
}

function setupInviteTabs() {
  qsa("[data-invite-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.inviteTab;
      qsa("[data-invite-tab]").forEach((item) => item.classList.toggle("is-active", item === button));
      qsa("[data-invite-panel]").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.invitePanel !== target);
      });
    });
  });
}

function setupPluginControls() {
  qs("#plugin-search")?.addEventListener("input", (event) => {
    pluginSearch = event.target.value || "";
    renderPlugins();
  });

  qsa("[data-plugin-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      pluginFilter = button.dataset.pluginFilter || "all";
      qsa("[data-plugin-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      renderPlugins();
    });
  });

  qs("#plugin-grid")?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-open-path]");
    if (!card) return;
    const path = card.dataset.openPath;
    if (path) {
      window.location.href = path;
    }
  });
}

function setupGlobalActions() {
  qs("#refresh-button")?.addEventListener("click", () => bootstrapMiniApp({ force: true }));
  qs("#invite-form")?.addEventListener("submit", createInviteFromMiniApp);
  qs("#invite-open-form")?.addEventListener("submit", createAccountOpenInviteFromMiniApp);
  window.addEventListener("resize", updateBottomNavHeight);
}

setupInviteTabs();
setupPluginControls();
setupGlobalActions();
bootstrapMiniApp();
