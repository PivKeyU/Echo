const tg = window.Telegram?.WebApp;

const state = {
  initData: tg?.initData || "",
  webSessionToken: "",
  authAccount: null,
  profileBundle: null,
  pendingBundleCandidate: null,
  bundleRefreshPromise: null,
  bundleRenderToken: 0,
  wikiBundle: null,
  wikiBundleLoading: false,
  wikiBundlePromise: null,
  wikiBundleRequested: false,
  deferredBundleLoading: false,
  deferredBundleLoaded: false,
  deferredBundlePromise: null,
  deferredSectionsLoaded: new Set(),
  deferredSectionPromises: new Map(),
  deferredSectionQueue: Promise.resolve(),
  externalSectionRefreshAt: {},
  actionLocks: new Set(),
  officialRecycleSelections: {},
  deferredBootstrapTimer: null,
  retreatTimingTimer: null,
  wikiFilter: "all",
  wikiSearchQuery: "",
  leaderboard: { kind: "stone", page: 1, totalPages: 1, loaded: false },
  shopNameEditing: false,
  giftTarget: null,
  giftSearchQuery: "",
  giftSearchResults: [],
  giftSearchTimer: null,
  mentorshipTarget: null,
  mentorshipSearchQuery: "",
  mentorshipSearchResults: [],
  mentorshipSearchTimer: null,
  marriageTarget: null,
  marriageSearchQuery: "",
  marriageSearchResults: [],
  marriageSearchTimer: null,
  foldStates: {},
  foldStatesLoaded: false,
};

const WIKI_BUNDLE_CACHE_KEY = "xiuxian_wiki_bundle_v3";
const BOOTSTRAP_CACHE_KEY_PREFIX = "xiuxian_bootstrap_core_v2";
const BOOTSTRAP_CACHE_MAX_AGE_MS = 6 * 60 * 60 * 1000;
const FOLD_STATE_CACHE_KEY_PREFIX = "xiuxian_fold_states_v1";
const WEB_AUTH_TOKEN_KEY = "xiuxian_web_session_token_v1";
const WEB_AUTH_ACCOUNT_KEY = "xiuxian_web_account_v1";
const DEFAULT_REQUEST_TIMEOUT_MS = 30000;
const DEFERRED_SECTION_REQUEST_TIMEOUT_MS = 18000;
const WIKI_REQUEST_TIMEOUT_MS = 20000;
const ACTION_REQUEST_TIMEOUT_MS = 45000;
const NETWORK_ERROR_MESSAGES = new Set([
  "Failed to fetch",
  "Load failed",
  "NetworkError when attempting to fetch resource.",
  "The Internet connection appears to be offline.",
  "The network connection was lost.",
]);
const UPSTREAM_UNAVAILABLE_MESSAGES = new Set([
  "Bad Gateway",
  "Gateway Timeout",
  "Service Unavailable",
]);
const REALM_ORDER = ["炼气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫", "人仙", "地仙", "天仙", "金仙", "大罗金仙", "仙君", "仙王", "仙尊", "仙帝"];

function applyTelegramTheme() {
  const root = document.documentElement;
  const scheme = String(tg?.colorScheme || "").toLowerCase();
  if (scheme === "light" || scheme === "dark") {
    root.dataset.colorScheme = scheme;
  }
  const params = tg?.themeParams || {};
  const map = {
    bg_color: "--bg-top",
    secondary_bg_color: "--surface",
    text_color: "--ink",
    hint_color: "--muted",
    button_color: "--accent-strong",
    button_text_color: "--tg-button-text",
    link_color: "--accent",
  };
  for (const [key, cssVar] of Object.entries(map)) {
    const value = params[key];
    if (typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value)) {
      root.style.setProperty(cssVar, value);
    }
  }
}

applyTelegramTheme();
tg?.onEvent?.("themeChanged", applyTelegramTheme);

function requestTimeoutMessage(timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS) {
  const seconds = Math.max(Math.round(Number(timeoutMs || DEFAULT_REQUEST_TIMEOUT_MS) / 1000), 1);
  return `请求超过 ${seconds} 秒仍未完成，请稍后重试。`;
}

function timeoutSignal(timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS) {
  if (typeof AbortController !== "function") return { signal: undefined, cleanup: () => {} };
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), Math.max(Number(timeoutMs || DEFAULT_REQUEST_TIMEOUT_MS), 1000));
  return {
    signal: controller.signal,
    cleanup: () => window.clearTimeout(timer),
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeHexColor(value) {
  const raw = String(value || "").trim();
  if (/^#[0-9a-f]{3}$/i.test(raw)) {
    const [, r, g, b] = raw;
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
  }
  if (/^#[0-9a-f]{6}$/i.test(raw)) return raw.toLowerCase();
  if (/^#[0-9a-f]{8}$/i.test(raw)) return `#${raw.slice(1, 7)}`.toLowerCase();
  return "";
}

function hexWithAlpha(value, alpha) {
  const hex = normalizeHexColor(value);
  return hex ? `${hex}${alpha}` : "";
}

function isGradientDecorColor(value) {
  return /gradient\s*\(/i.test(String(value || ""));
}

function normalizeDecorColor(value, fallback = "") {
  const raw = String(value || "").trim();
  if (!raw) return fallback;
  if (raw.length > 255) return fallback;
  if (!/^[#(),.%/+\-\sa-zA-Z0-9]+$/.test(raw)) return fallback;
  const lower = raw.toLowerCase();
  if (lower.includes("url(") || lower.includes("expression(") || lower.includes("javascript:") || lower.includes("var(")) {
    return fallback;
  }
  if (/^#[0-9a-f]{3,8}$/i.test(raw)) return raw;
  if (/^(rgb|rgba|hsl|hsla)\([#0-9a-z.,%/+\-\s]+\)$/i.test(raw)) return raw;
  if (/^(linear|radial|conic)-gradient\([#0-9a-z.,%/+\-\s]+\)$/i.test(raw)) return raw;
  return fallback;
}

function buildDecorBadgeStyle(color, fallback = "#9ca3af") {
  const safeColor = normalizeDecorColor(color, fallback) || fallback;
  if (isGradientDecorColor(safeColor)) {
    return `background:${safeColor};color:#fff;box-shadow:inset 0 0 0 1px rgba(255,255,255,.28);`;
  }
  const hex = normalizeHexColor(safeColor);
  if (hex) {
    return `background:${hexWithAlpha(hex, "22")};color:${hex};box-shadow:inset 0 0 0 1px ${hexWithAlpha(hex, "33")};`;
  }
  return `background:rgba(148,163,184,.14);color:${safeColor};box-shadow:inset 0 0 0 1px rgba(148,163,184,.24);`;
}

function buildDecorTextStyle(color) {
  const safeColor = normalizeDecorColor(color, "");
  if (!safeColor) return "";
  if (isGradientDecorColor(safeColor)) {
    return `display:inline-block;background:${safeColor};background-size:100% 100%;background-clip:text;-webkit-background-clip:text;color:transparent;-webkit-text-fill-color:transparent;`;
  }
  return `color:${safeColor};`;
}

function titleColoredNameHtml(label, color) {
  const safeLabel = escapeHtml(label || "未命名称号");
  const style = escapeHtml(buildDecorTextStyle(color));
  return `<span class="title-colored-name"${style ? ` style="${style}"` : ""}>${safeLabel}</span>`;
}

function grantedItemName(payload) {
  if (!payload || typeof payload !== "object") return "";
  if (payload.duplicate_converted) {
    return `重复${payload.item_kind_label || "物品"}折灵石 +${Number(payload.stone_compensation || 0)}`;
  }
  return payload.artifact?.name
    || payload.pill?.name
    || payload.talisman?.name
    || payload.material?.name
    || payload.technique?.name
    || payload.recipe?.name
    || payload.item_name
    || "";
}

function setStatus(text, tone = "info") {
  document.querySelector("#status-text").textContent = text;
  const chip = document.querySelector("#feedback-chip");
  chip.textContent = text;
  chip.className = `feedback-chip ${tone === "error" ? "error" : tone === "success" ? "success" : tone === "warning" ? "warning" : ""}`;
  chip.classList.remove("hidden");
}

function touchFeedback(tone = "success") {
  if (!tg?.HapticFeedback) return;
  if (tone === "error") {
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }
  if (tone === "warning") {
    tg.HapticFeedback.notificationOccurred("warning");
    return;
  }
  tg.HapticFeedback.notificationOccurred("success");
}

const TOUCH_CONTEXTMENU_GUARD_MS = 900;
let lastTouchContextTarget = null;
let lastTouchContextAt = 0;

function isEditableTouchTarget(target) {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest(
    "textarea, [contenteditable=''], [contenteditable='true'], [contenteditable='plaintext-only'], "
      + "input:not([type='button']):not([type='checkbox']):not([type='file']):not([type='image']):not([type='radio']):not([type='range']):not([type='reset']):not([type='submit'])"
  ));
}

function rememberTouchContextTarget(target) {
  if (!(target instanceof Element)) return;
  lastTouchContextTarget = target;
  lastTouchContextAt = Date.now();
}

function markTouchPointerInteraction(event) {
  if (String(event.pointerType || "").toLowerCase() !== "touch") return;
  rememberTouchContextTarget(event.target);
}

function markTouchStartInteraction(event) {
  if (!event.touches?.length) return;
  rememberTouchContextTarget(event.target);
}

function shouldSuppressTouchContextMenu(event) {
  const pointerType = String(event.pointerType || "").toLowerCase();
  if (pointerType === "mouse") return false;
  const target = event.target instanceof Element ? event.target : null;
  if (!target || isEditableTouchTarget(target)) return false;
  if (pointerType === "touch") return true;
  const recentTouch = Date.now() - lastTouchContextAt <= TOUCH_CONTEXTMENU_GUARD_MS;
  if (!recentTouch || !(lastTouchContextTarget instanceof Element)) return false;
  return target === lastTouchContextTarget
    || target.contains(lastTouchContextTarget)
    || lastTouchContextTarget.contains(target);
}

function installTouchContextMenuGuard() {
  if (document.documentElement.dataset.touchContextMenuGuardBound) return;
  document.documentElement.dataset.touchContextMenuGuardBound = "1";
  document.addEventListener("pointerdown", markTouchPointerInteraction, { passive: true, capture: true });
  document.addEventListener("touchstart", markTouchStartInteraction, { passive: true, capture: true });
  document.addEventListener("contextmenu", (event) => {
    if (!shouldSuppressTouchContextMenu(event)) return;
    event.preventDefault();
  }, { capture: true });
}

function normalizeErrorLegacy(error, fallback) {
  const message = String(error?.message || fallback || "操作失败，请稍后再试").trim();
  if (!message || /^[?？.\s]+$/.test(message)) {
    return fallback || "操作失败，请稍后再试";
  }
  return message;
}

const TG_POPUP_TITLE_LIMIT = 64;
const TG_POPUP_MESSAGE_LIMIT = 256;
const TG_POPUP_FALLBACK_MESSAGE = {
  success: "操作已完成。",
  warning: "操作已完成，请留意页面提示。",
  error: "操作失败，请稍后再试。",
};

function safeTelegramPopupText(value, limit, fallback = "") {
  const text = String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  const normalized = text || fallback;
  if (!normalized) return "";
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, Math.max(limit - 1, 1)).trimEnd()}…`;
}

async function popupLegacy(title, message, tone = "success") {
  touchFeedback(tone);
  if (tg?.showPopup) {
    try {
      await tg.showPopup({
        title: safeTelegramPopupText(title, TG_POPUP_TITLE_LIMIT, "提示"),
        message: safeTelegramPopupText(
          message,
          TG_POPUP_MESSAGE_LIMIT,
          TG_POPUP_FALLBACK_MESSAGE[tone] || TG_POPUP_FALLBACK_MESSAGE.success,
        ),
        buttons: [{ type: "close", text: "知道了" }]
      });
      return;
    } catch (error) {
      console.warn("Telegram popup failed, fallback to alert", error);
    }
  }
  window.alert(`${title}\n\n${message}`);
}

async function postJsonLegacy(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: authInitData(), ...body })
  });
  const payload = await response.json();
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || "请求失败");
  }
  return payload.data;
}

async function uploadImageLegacy(path, file, folder) {
  if (!file) {
    throw new Error("请先选择一张图片");
  }
  const formData = new FormData();
  formData.append("init_data", authInitData());
  formData.append("folder", folder);
  formData.append("file", file);
  const headers = state.webSessionToken ? { Authorization: `Bearer ${state.webSessionToken}` } : undefined;
  const response = await fetch(path, {
    method: "POST",
    body: formData,
    headers,
  });
  const payload = await response.json();
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || "上传失败");
  }
  return payload.data;
}

function defaultMessage(fallback = "操作失败，请稍后再试") {
  return fallback || "操作失败，请稍后再试";
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

function normalizeError(error, fallback) {
  const message = String(error?.message || fallback || defaultMessage()).trim();
  if (!message || /^[??\s]+$/.test(message)) {
    return defaultMessage(fallback);
  }
  if (NETWORK_ERROR_MESSAGES.has(message)) {
    return "网络请求失败，请稍后重试。";
  }
  if (UPSTREAM_UNAVAILABLE_MESSAGES.has(message)) {
    return "服务正在重启或暂时不可用，请稍后重试。";
  }
  if (error?.name === "AbortError" || message === "AbortError" || message === "The operation was aborted.") {
    return "请求处理时间过长，已自动停止等待，请稍后重试。";
  }
  if (message.includes("仍未完成")) {
    return message;
  }
  if (message.startsWith("Unexpected token") || message === "Internal Server Error") {
    return defaultMessage(fallback);
  }
  return message;
}

async function popup(title, message, tone = "success") {
  touchFeedback(tone);
  if (tg?.showPopup) {
    try {
      await tg.showPopup({
        title: safeTelegramPopupText(title, TG_POPUP_TITLE_LIMIT, "提示"),
        message: safeTelegramPopupText(
          message,
          TG_POPUP_MESSAGE_LIMIT,
          TG_POPUP_FALLBACK_MESSAGE[tone] || TG_POPUP_FALLBACK_MESSAGE.success,
        ),
        buttons: [{ type: "close", text: "知道了" }]
      });
      return;
    } catch (error) {
      console.warn("Telegram popup failed, fallback to alert", error);
    }
  }
  window.alert(`${title}\n\n${message}`);
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

async function postJson(path, body = {}, options = {}) {
  const timeoutMs = Number(options.timeoutMs || DEFAULT_REQUEST_TIMEOUT_MS);
  const { signal, cleanup } = timeoutSignal(timeoutMs);
  const includeAuth = options.includeAuth !== false;
  const headers = { "Content-Type": "application/json" };
  if (includeAuth && state.webSessionToken) {
    headers.Authorization = `Bearer ${state.webSessionToken}`;
  }
  const requestBody = includeAuth ? { init_data: authInitData(), ...body } : { ...body };
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers,
      body: JSON.stringify(requestBody),
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(requestTimeoutMessage(timeoutMs));
    }
    throw error;
  } finally {
    cleanup();
  }
  let payload;
  try {
    payload = await readResponsePayload(response);
  } catch (error) {
    if (response.status === 504) {
      throw new Error("服务处理超时，请稍后重试。");
    }
    throw error;
  }
  if (!response.ok || payload.code !== 200) {
    const message = payload.detail || payload.message || "请求失败";
    if (response.status === 429) {
      throw new Error("当前修仙请求较多，请稍后再试。");
    }
    const error = new Error(message);
    error.status = response.status;
    error.code = payload.code;
    error.payload = payload;
    throw error;
  }
  rememberBundleCandidate(payload.data);
  return payload.data;
}

function nextUiFrame() {
  return new Promise((resolve) => {
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => resolve());
      return;
    }
    window.setTimeout(resolve, 16);
  });
}

async function waitForUiFrames(count = 2) {
  for (let index = 0; index < count; index += 1) {
    await nextUiFrame();
  }
}

async function uploadImage(path, file, folder) {
  if (!file) {
    throw new Error("请先选择一张图片");
  }
  const formData = new FormData();
  formData.append("init_data", authInitData());
  formData.append("folder", folder);
  formData.append("file", file);
  const headers = state.webSessionToken ? { Authorization: `Bearer ${state.webSessionToken}` } : undefined;
  const response = await fetch(path, {
    method: "POST",
    body: formData,
    headers,
  });
  const payload = await readResponsePayload(response);
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || "上传失败");
  }
  return payload.data;
}

function authPanelElements() {
  return {
    card: document.querySelector("#auth-card"),
    status: document.querySelector("#auth-status"),
    loginForm: document.querySelector("#auth-login-form"),
    registerForm: document.querySelector("#auth-register-form"),
    bindPanel: document.querySelector("#auth-bind-panel"),
    tabs: document.querySelector(".auth-tabs"),
    loginTab: document.querySelector("[data-auth-mode='login']"),
    registerTab: document.querySelector("[data-auth-mode='register']"),
    bindButton: document.querySelector("#auth-bind-telegram"),
    logoutButton: document.querySelector("#auth-logout"),
    closeButton: document.querySelector("#auth-close"),
    accountName: document.querySelector("#auth-account-name"),
    bindHint: document.querySelector("#auth-bind-hint"),
    bindState: document.querySelector("#auth-bind-state"),
  };
}

function authStatusText() {
  if (state.authAccount?.bound) {
    const label = state.authAccount.display_name || state.authAccount.username || "网页账号";
    return `${label} 已绑定 TG ${state.authAccount.tg}`;
  }
  if (state.webSessionToken) {
    return "账号已登录，完成 Telegram 绑定后即可进入修仙。";
  }
  if (hasTelegramInitData()) {
    return "当前在 Telegram 内，可直接绑定新账号。";
  }
  return "登录后可在浏览器打开修仙面板。";
}

function renderAuthPanel(mode = "") {
  const elements = authPanelElements();
  if (!elements.card) return;
  const hasSession = Boolean(state.webSessionToken);
  const isBound = Boolean(state.authAccount?.bound);
  const requestedMode = String(mode || "").trim();
  const shouldShow = Boolean(requestedMode) || !hasSession || !isBound;
  let activeMode = requestedMode || state.authMode || "login";
  if (hasSession && !isBound) activeMode = "bind";
  if (hasSession && isBound && activeMode === "bind") activeMode = "account";
  if (!hasSession && ["bind", "account"].includes(activeMode)) activeMode = "login";
  if (hasSession && isBound && !requestedMode) activeMode = "account";
  state.authMode = activeMode;

  elements.card.classList.toggle("hidden", !shouldShow);
  elements.card.setAttribute("aria-hidden", shouldShow ? "false" : "true");
  elements.card.inert = !shouldShow;
  elements.loginForm?.classList.toggle("hidden", activeMode !== "login");
  elements.registerForm?.classList.toggle("hidden", activeMode !== "register");
  elements.bindPanel?.classList.toggle("hidden", !["bind", "account"].includes(activeMode));
  elements.tabs?.classList.toggle("hidden", hasSession);
  elements.loginTab?.classList.toggle("is-active", activeMode === "login");
  elements.registerTab?.classList.toggle("is-active", activeMode === "register");
  if (elements.status) elements.status.textContent = authStatusText();
  if (elements.accountName) {
    elements.accountName.textContent = state.authAccount?.display_name || state.authAccount?.username || "未登录";
  }
  if (elements.bindHint) {
    elements.bindHint.textContent = isBound
      ? `${state.authAccount?.telegram_label || `TG ${state.authAccount?.tg || ""}`} 已绑定，可在修仙与斗破中使用。`
      : hasTelegramInitData()
        ? "点击绑定后会使用当前 Telegram 身份完成验证。"
        : "请从 Telegram Mini App 打开此页完成绑定。";
  }
  if (elements.bindButton) {
    elements.bindButton.disabled = !hasTelegramInitData();
    elements.bindButton.classList.toggle("hidden", isBound);
  }
  elements.closeButton?.classList.toggle("hidden", !(isBound && activeMode === "account"));
  if (elements.bindState) {
    elements.bindState.textContent = isBound ? "已绑定" : "待绑定";
    elements.bindState.classList.toggle("badge--normal", isBound);
  }
}

function setGameLocked(locked) {
  document.body.classList.toggle("auth-locked", Boolean(locked));
}

function resetAuthenticatedView() {
  setGameLocked(true);
  state.profileBundle = null;
  state.pendingBundleCandidate = null;
  state.deferredBundleLoaded = false;
  state.deferredBundlePromise = null;
  clearDeferredSectionState();
  document.querySelectorAll(".fold-card, #fold-toolbar").forEach((element) => {
    element.classList.add("hidden");
    if ("open" in element) element.open = false;
  });
  renderBottomNav([]);
}

function isBindRequiredError(error) {
  return Number(error?.status || 0) === 403 && String(error?.message || "").includes("绑定");
}

function isWebSessionError(error) {
  return Boolean(state.webSessionToken) && Number(error?.status || 0) === 401;
}

async function resumeAfterAuth() {
  renderAuthPanel();
  if (state.authAccount?.bound) {
    await bootstrap();
  }
}

function handleAuthResult(payload) {
  const sessionToken = String(payload?.session_token || state.webSessionToken || "").trim();
  const account = normalizeAuthAccount(payload?.account);
  storeWebAuth(sessionToken, account);
  if (payload?.telegram_user) {
    rememberTelegramIdentity(payload.telegram_user);
  }
  renderAuthPanel(account?.bound ? "" : "bind");
  return account;
}

function setupAuthPanel() {
  const elements = authPanelElements();
  if (!elements.card || elements.card.dataset.authBound) return;
  elements.card.dataset.authBound = "1";
  elements.loginTab?.addEventListener("click", () => renderAuthPanel("login"));
  elements.registerTab?.addEventListener("click", () => renderAuthPanel("register"));

  elements.loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type='submit']");
    try {
      const account = await runButtonAction(button, "登录中…", async () => {
        const data = await postJson(
          "/plugins/xiuxian/api/auth/login",
          {
            username: document.querySelector("#auth-login-username")?.value || "",
            password: document.querySelector("#auth-login-password")?.value || "",
            init_data: state.initData,
          },
          { includeAuth: false, timeoutMs: 20000 },
        );
        return handleAuthResult(data);
      });
      setStatus(account?.bound ? "登录成功，正在同步修仙状态。" : "登录成功，请完成 Telegram 绑定。", account?.bound ? "success" : "warning");
      await resumeAfterAuth();
    } catch (error) {
      const message = normalizeError(error, "登录失败。");
      setStatus(message, "error");
      await popup("登录失败", message, "error");
    }
  });

  elements.registerForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = String(document.querySelector("#auth-register-password")?.value || "");
    const confirm = String(document.querySelector("#auth-register-confirm")?.value || "");
    if (password !== confirm) {
      setStatus("两次输入的密码不一致。", "error");
      return;
    }
    const button = event.currentTarget.querySelector("button[type='submit']");
    try {
      const account = await runButtonAction(button, "注册中…", async () => {
        const data = await postJson(
          "/plugins/xiuxian/api/auth/register",
          {
            username: document.querySelector("#auth-register-username")?.value || "",
            display_name: document.querySelector("#auth-register-display")?.value || "",
            password,
            init_data: state.initData,
          },
          { includeAuth: false, timeoutMs: 25000 },
        );
        return handleAuthResult(data);
      });
      setStatus(account?.bound ? "注册成功，正在同步修仙状态。" : "注册成功，请完成 Telegram 绑定。", account?.bound ? "success" : "warning");
      await resumeAfterAuth();
    } catch (error) {
      const message = normalizeError(error, "注册失败。");
      setStatus(message, "error");
      await popup("注册失败", message, "error");
    }
  });

  elements.bindButton?.addEventListener("click", async (event) => {
    if (!hasTelegramInitData()) {
      setStatus("请从 Telegram Mini App 打开此页完成绑定。", "warning");
      return;
    }
    const button = event.currentTarget;
    try {
      const account = await runButtonAction(button, "绑定中…", async () => {
        const data = await postJson(
          "/plugins/xiuxian/api/auth/bind-telegram",
          {
            session_token: state.webSessionToken,
            init_data: state.initData,
          },
          { includeAuth: false, timeoutMs: 20000 },
        );
        storeWebAuth(state.webSessionToken, data.account);
        rememberTelegramIdentity(data.telegram_user);
        renderAuthPanel();
        return normalizeAuthAccount(data.account);
      });
      setStatus(`已绑定 TG ${account?.tg || ""}，正在同步修仙状态。`, "success");
      await resumeAfterAuth();
    } catch (error) {
      const message = normalizeError(error, "绑定失败。");
      setStatus(message, "error");
      await popup("绑定失败", message, "error");
    }
  });

  elements.logoutButton?.addEventListener("click", async () => {
    const token = state.webSessionToken;
    if (token) {
      await postJson("/plugins/xiuxian/api/auth/logout", { session_token: token }, { includeAuth: false }).catch(() => null);
    }
    clearWebAuth();
    resetAuthenticatedView();
    renderAuthPanel("login");
    setStatus("已退出网页账号。", "warning");
  });
  elements.closeButton?.addEventListener("click", () => renderAuthPanel(""));
  document.querySelector("#open-account-center")?.addEventListener("click", () => {
    renderAuthPanel("account");
    document.querySelector("#auth-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

async function runButtonAction(button, pendingText, handler, { lockKey = "" } = {}) {
  const normalizedLockKey = String(lockKey || "").trim();
  if (normalizedLockKey && state.actionLocks.has(normalizedLockKey)) {
    throw new Error("上一次操作仍在处理中，请稍后再试。");
  }
  const previous = button.textContent;
  button.disabled = true;
  button.textContent = pendingText;
  if (normalizedLockKey) state.actionLocks.add(normalizedLockKey);
  try {
    await nextUiFrame();
    return await handler();
  } finally {
    if (normalizedLockKey) state.actionLocks.delete(normalizedLockKey);
    button.disabled = false;
    button.textContent = previous;
  }
}

function setDisabled(button, disabled, reason = "") {
  if (!button) return;
  button.disabled = Boolean(disabled);
  button.title = disabled ? reason : "";
}

function applyBreakthroughActionState(bundle, fallbackReason = "当前无法尝试突破") {
  const canBreakthrough = Boolean(bundle?.capabilities?.can_breakthrough);
  const requiredPillName = String(bundle?.capabilities?.required_breakthrough_pill_name || "").trim();
  const requiredSceneName = String(bundle?.capabilities?.required_breakthrough_scene_name || "").trim();
  const breakButton = document.querySelector("#break-btn");
  const breakPillButton = document.querySelector("#break-pill-btn");
  if (breakPillButton) {
    breakPillButton.textContent = requiredPillName ? `服用${requiredPillName}突破` : "服用破境丹突破";
  }
  if (breakButton) {
    if (requiredPillName) {
      const reason = requiredSceneName
        ? `当前版本突破必须服用【${requiredPillName}】；丹方与材料可在【${requiredSceneName}】获取。`
        : `当前版本突破必须服用【${requiredPillName}】。`;
      setDisabled(breakButton, true, reason);
    } else {
      setDisabled(breakButton, !canBreakthrough, fallbackReason);
    }
  }
  setDisabled(
    breakPillButton,
    !canBreakthrough,
    !canBreakthrough ? (bundle?.capabilities?.breakthrough_reason || fallbackReason) : "",
  );
}

function parseShanghaiDate(value) {
  if (!value) return null;
  const normalized = typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value}+00:00`
    : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value) {
  if (!value) return "未开始";
  const date = parseShanghaiDate(value);
  return date ? date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "未知";
}

function retreatRemainingSeconds(profile = {}) {
  const endAt = parseShanghaiDate(profile?.retreat_end_at);
  if (!endAt) return 0;
  return Math.max(Math.ceil((endAt.getTime() - Date.now()) / 1000), 0);
}

function retreatTimingText(bundle = state.profileBundle) {
  const profile = bundle?.profile || {};
  const retreating = Boolean(bundle?.capabilities?.is_in_retreat);
  if (!retreating || !profile.retreat_started_at || !profile.retreat_end_at) {
    return "开始闭关后，这里会显示本次闭关开始时间、预计出关时间和剩余时长。";
  }
  const startText = formatDate(profile.retreat_started_at);
  const endText = formatDate(profile.retreat_end_at);
  const remainingSeconds = retreatRemainingSeconds(profile);
  if (remainingSeconds <= 0) {
    return `本次闭关开始于 ${startText}，原定 ${endText} 出关，现在可以直接出关结算。`;
  }
  return `本次闭关开始于 ${startText}，预计 ${endText} 出关，剩余 ${formatCountdownSeconds(remainingSeconds)}。`;
}

function renderRetreatTimingHint(bundle = state.profileBundle) {
  const hint = document.querySelector("#retreat-time-hint");
  if (!hint) return;
  hint.textContent = retreatTimingText(bundle);
}

function syncRetreatTimingTicker(bundle = state.profileBundle) {
  if (state.retreatTimingTimer) {
    window.clearInterval(state.retreatTimingTimer);
    state.retreatTimingTimer = null;
  }
  renderRetreatTimingHint(bundle);
  if (!bundle?.capabilities?.is_in_retreat) return;
  state.retreatTimingTimer = window.setInterval(() => {
    renderRetreatTimingHint(state.profileBundle);
  }, 30000);
}

function normalizeWikiSearchQuery(value) {
  return String(value || "").trim().toLowerCase();
}

function wikiSearchTokens(value) {
  const query = normalizeWikiSearchQuery(value);
  if (!query) return [];
  return query.split(/\s+/).filter(Boolean);
}

function wikiHaystack(entry) {
  return [
    entry?.title,
    entry?.subtitle,
    entry?.description,
    ...(Array.isArray(entry?.tags) ? entry.tags : []),
    ...(Array.isArray(entry?.keywords) ? entry.keywords : []),
    ...(Array.isArray(entry?.body_lines) ? entry.body_lines : []),
  ].join(" ").toLowerCase();
}

function wikiEntryScore(entry, query) {
  const normalizedQuery = normalizeWikiSearchQuery(query);
  if (!normalizedQuery) return 0;
  const tokens = wikiSearchTokens(normalizedQuery);
  const haystack = wikiHaystack(entry);
  if (!tokens.every((token) => haystack.includes(token))) return -1;
  const title = String(entry?.title || "").toLowerCase();
  const subtitle = String(entry?.subtitle || "").toLowerCase();
  const keywords = Array.isArray(entry?.keywords) ? entry.keywords.join(" ").toLowerCase() : "";
  const body = Array.isArray(entry?.body_lines) ? entry.body_lines.join(" ").toLowerCase() : "";
  let score = 0;
  if (title === normalizedQuery) score += 120;
  if (title.includes(normalizedQuery)) score += 80;
  if (subtitle.includes(normalizedQuery)) score += 32;
  if (keywords.includes(normalizedQuery)) score += 24;
  if (body.includes(normalizedQuery)) score += 12;
  score += Math.max(12 - title.length, 0);
  return score;
}

function wikiFilterMatches(entry, filter) {
  if (!filter || filter === "all") return true;
  const keys = Array.isArray(entry?.filter_keys) ? entry.filter_keys.map((item) => String(item || "")) : [String(entry?.group || "")];
  return keys.includes(String(filter || ""));
}

const WIKI_FILTER_LABELS = {
  tutorial: "玩法",
  attribute: "属性",
  starter: "入门",
  explore: "探索",
  crafting: "炼制",
  combat: "战斗",
  task: "任务",
  social: "社交",
  sect: "宗门",
  activity: "活动",
  scene: "秘境",
  encounter: "奇遇",
  boss: "Boss",
  farm: "灵田",
  fishing: "垂钓",
  gambling: "赌坊",
  material: "材料",
  artifact: "法宝",
  pill: "丹药",
  talisman: "符箓",
  technique: "功法",
  title: "称号",
  recipe: "配方",
  achievement: "成就",
};

function normalizeWikiDisplayText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function wikiCardTitle(entry) {
  const title = normalizeWikiDisplayText(entry?.title);
  const subtitle = normalizeWikiDisplayText(entry?.subtitle);
  if (!title) return "";
  if (String(entry?.group || "") === "tutorial" && subtitle && title.startsWith(`${subtitle} · `)) {
    return title.slice(subtitle.length + 3).trim();
  }
  return title;
}

function wikiCardSubtitle(entry) {
  const title = normalizeWikiDisplayText(entry?.title);
  const subtitle = normalizeWikiDisplayText(entry?.subtitle);
  if (!subtitle || title === subtitle) return "";
  return subtitle;
}

function wikiCardTags(entry) {
  if (String(entry?.group || "") === "tutorial") {
    const filterKeys = Array.isArray(entry?.filter_keys) ? entry.filter_keys : [];
    return filterKeys
      .filter((key) => key && key !== "tutorial")
      .map((key) => WIKI_FILTER_LABELS[String(key)] || "")
      .filter(Boolean)
      .slice(0, 3);
  }
  return (Array.isArray(entry?.tags) ? entry.tags : []).filter(Boolean).slice(0, 4);
}

function wikiCardLines(entry) {
  const lines = Array.isArray(entry?.body_lines) ? entry.body_lines : [];
  const seen = new Set();
  const skipValues = [
    entry?.title,
    entry?.subtitle,
    entry?.description,
  ].map((value) => normalizeWikiDisplayText(value).toLowerCase()).filter(Boolean);
  skipValues.forEach((value) => seen.add(value));
  const visible = [];
  for (const line of lines) {
    const text = normalizeWikiDisplayText(line);
    if (!text) continue;
    const normalized = text.toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    visible.push(text);
  }
  return visible.slice(0, String(entry?.group || "") === "tutorial" ? 1 : 2);
}

function wikiPopupLines(entry) {
  const rows = [];
  const subtitle = wikiCardSubtitle(entry);
  if (subtitle) rows.push(subtitle);
  for (const value of [entry?.description, ...(Array.isArray(entry?.body_lines) ? entry.body_lines : [])]) {
    const text = normalizeWikiDisplayText(value);
    if (!text) continue;
    const normalized = text.toLowerCase();
    if (rows.some((item) => normalizeWikiDisplayText(item).toLowerCase() === normalized)) continue;
    rows.push(text);
  }
  return rows;
}

function renderWikiCards(root, entries, { emptyTitle, emptyText } = {}) {
  if (!root) return;
  if (!Array.isArray(entries) || !entries.length) {
    root.innerHTML = `<article class="stack-item"><strong>${escapeHtml(emptyTitle || "暂无内容")}</strong><p>${escapeHtml(emptyText || "请稍后再试。")}</p></article>`;
    return;
  }
  root.innerHTML = entries.map((entry) => {
    const tags = wikiCardTags(entry);
    const lines = wikiCardLines(entry);
    const title = wikiCardTitle(entry);
    const subtitle = wikiCardSubtitle(entry);
    const description = normalizeWikiDisplayText(entry?.description);
    return `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(title || entry?.title || "未命名词条")}</strong>
          <button type="button" class="ghost" data-wiki-entry="${escapeHtml(entry?.id || "")}">查看全文</button>
        </div>
        <div class="wiki-meta-line">
          <span>${escapeHtml(entry?.kind_label || "词条")}</span>
          ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ""}
        </div>
        ${description ? `<p>${escapeHtml(description)}</p>` : ""}
        ${tags.length ? `<div class="item-tags">${tags.map((tag) => `<span class="badge badge--normal">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
        ${lines.length ? `<div class="wiki-body-lines">${lines.map((line) => `<p class="section-copy">${escapeHtml(line)}</p>`).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
}

function readSessionStorage(key) {
  try {
    return window.sessionStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function writeSessionStorage(key, value) {
  try {
    if (value == null) {
      window.sessionStorage.removeItem(key);
      return;
    }
    window.sessionStorage.setItem(key, value);
  } catch (error) {
    // 忽略存储配额不足或不可用等错误。
  }
}

function readLocalStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
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
  } catch (error) {
    // 忽略存储配额不足或不可用等错误。
  }
}

function normalizeAuthAccount(account) {
  if (!account || typeof account !== "object") return null;
  const id = Number(account.id || 0);
  const tgId = Number(account.tg || 0);
  const username = String(account.username || "").trim();
  return {
    id: id > 0 ? id : null,
    username,
    display_name: String(account.display_name || username || "").trim(),
    tg: tgId > 0 ? tgId : null,
    bound: tgId > 0 || Boolean(account.bound),
    telegram_username: String(account.telegram_username || "").trim(),
    telegram_display_name: String(account.telegram_display_name || "").trim(),
    telegram_label: String(account.telegram_label || "").trim(),
    enabled: account.enabled !== false,
  };
}

function loadStoredWebAuth() {
  state.webSessionToken = String(readLocalStorage(WEB_AUTH_TOKEN_KEY) || "").trim();
  try {
    state.authAccount = normalizeAuthAccount(JSON.parse(readLocalStorage(WEB_AUTH_ACCOUNT_KEY) || "null"));
  } catch (error) {
    state.authAccount = null;
    writeLocalStorage(WEB_AUTH_ACCOUNT_KEY, null);
  }
}

function storeWebAuth(sessionToken, account) {
  const token = String(sessionToken || state.webSessionToken || "").trim();
  const normalizedAccount = normalizeAuthAccount(account);
  state.webSessionToken = token;
  state.authAccount = normalizedAccount;
  writeLocalStorage(WEB_AUTH_TOKEN_KEY, token || null);
  writeLocalStorage(WEB_AUTH_ACCOUNT_KEY, normalizedAccount ? JSON.stringify(normalizedAccount) : null);
}

function clearWebAuth() {
  state.webSessionToken = "";
  state.authAccount = null;
  writeLocalStorage(WEB_AUTH_TOKEN_KEY, null);
  writeLocalStorage(WEB_AUTH_ACCOUNT_KEY, null);
}

function hasTelegramInitData() {
  return Boolean(String(state.initData || "").trim());
}

function authInitData() {
  if (state.webSessionToken) return `web_session:${state.webSessionToken}`;
  if (hasTelegramInitData()) return String(state.initData || "").trim();
  return "";
}

function authIdentityKey() {
  const telegramUserId = Number(tg?.initDataUnsafe?.user?.id || 0);
  if (telegramUserId > 0) return String(telegramUserId);
  const accountTg = Number(state.authAccount?.tg || 0);
  if (accountTg > 0) return String(accountTg);
  if (state.webSessionToken) return `web:${state.webSessionToken.slice(0, 12)}`;
  return "anon";
}

function rememberTelegramIdentity(telegramUser) {
  const tgId = Number(telegramUser?.id || 0);
  if (tgId <= 0 || !state.webSessionToken) return;
  const displayName = [telegramUser?.first_name, telegramUser?.last_name].filter(Boolean).join(" ").trim();
  storeWebAuth(state.webSessionToken, {
    ...(state.authAccount || {}),
    username: state.authAccount?.username || String(telegramUser?.username || "").trim(),
    display_name: state.authAccount?.display_name || displayName,
    tg: tgId,
    bound: true,
  });
}

function bootstrapCacheKey() {
  return `${BOOTSTRAP_CACHE_KEY_PREFIX}:${authIdentityKey()}`;
}

function foldStateCacheKey() {
  return `${FOLD_STATE_CACHE_KEY_PREFIX}:${authIdentityKey()}`;
}

function hydrateFoldStates() {
  const raw = readLocalStorage(foldStateCacheKey());
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      writeLocalStorage(foldStateCacheKey(), null);
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).filter(([key, value]) => typeof key === "string" && typeof value === "boolean")
    );
  } catch (error) {
    writeLocalStorage(foldStateCacheKey(), null);
    return {};
  }
}

function ensureFoldStatesLoaded() {
  if (state.foldStatesLoaded) return;
  state.foldStates = hydrateFoldStates();
  state.foldStatesLoaded = true;
}

function persistFoldStates() {
  ensureFoldStatesLoaded();
  writeLocalStorage(foldStateCacheKey(), JSON.stringify(state.foldStates || {}));
}

function foldStateKey(...parts) {
  return parts
    .map((part) => String(part ?? "").trim())
    .filter(Boolean)
    .join(":");
}

function readFoldState(key, defaultOpen = false) {
  ensureFoldStatesLoaded();
  if (!key) return Boolean(defaultOpen);
  if (!Object.prototype.hasOwnProperty.call(state.foldStates, key)) {
    return Boolean(defaultOpen);
  }
  return Boolean(state.foldStates[key]);
}

function writeFoldState(key, open) {
  const normalizedKey = String(key || "").trim();
  if (!normalizedKey) return;
  ensureFoldStatesLoaded();
  state.foldStates[normalizedKey] = Boolean(open);
  persistFoldStates();
}

function bindPersistentFoldState(details, key, { defaultOpen = false } = {}) {
  if (!details) return details;
  const normalizedKey = String(key || "").trim();
  details.open = readFoldState(normalizedKey, defaultOpen);
  if (!normalizedKey) return details;
  details.dataset.foldKey = normalizedKey;
  details.addEventListener("toggle", () => {
    writeFoldState(normalizedKey, details.open);
  });
  return details;
}

function hydrateBootstrapCache() {
  const raw = readLocalStorage(bootstrapCacheKey());
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.profile_bundle || typeof parsed.profile_bundle !== "object") {
      writeLocalStorage(bootstrapCacheKey(), null);
      return null;
    }
    const savedAt = Number(parsed.saved_at || 0);
    if (savedAt > 0 && Date.now() - savedAt > BOOTSTRAP_CACHE_MAX_AGE_MS) {
      writeLocalStorage(bootstrapCacheKey(), null);
      return null;
    }
    return parsed;
  } catch (error) {
    writeLocalStorage(bootstrapCacheKey(), null);
    return null;
  }
}

function storeBootstrapCache(payload) {
  if (!payload || typeof payload !== "object" || !payload.profile_bundle || typeof payload.profile_bundle !== "object") {
    return;
  }
  writeLocalStorage(bootstrapCacheKey(), JSON.stringify({
    profile_bundle: payload.profile_bundle,
    bottom_nav: Array.isArray(payload.bottom_nav) ? payload.bottom_nav : [],
    cache_generation: String(payload.cache_generation || "").trim(),
    saved_at: Date.now(),
  }));
}

function bootstrapCacheGeneration(payload) {
  return String(payload?.cache_generation || "").trim();
}

function applyBootstrapPayload(payload, { skipIfSameGeneration = false, cachedGeneration = "" } = {}) {
  rememberTelegramIdentity(payload?.telegram_user);
  const generation = bootstrapCacheGeneration(payload);
  const sameGeneration = Boolean(
    skipIfSameGeneration
    && generation
    && cachedGeneration
    && generation === cachedGeneration
  );
  storeBootstrapCache(payload);
  if (!sameGeneration) {
    renderBottomNav(payload.bottom_nav || []);
    applyProfileBundle(payload.profile_bundle);
  }
  return sameGeneration;
}

function hydrateWikiBundleFromCache() {
  if (state.wikiBundle) return state.wikiBundle;
  const raw = readSessionStorage(WIKI_BUNDLE_CACHE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      writeSessionStorage(WIKI_BUNDLE_CACHE_KEY, null);
      return null;
    }
    state.wikiBundle = parsed;
    return parsed;
  } catch (error) {
    writeSessionStorage(WIKI_BUNDLE_CACHE_KEY, null);
    return null;
  }
}

function currentWikiEntries() {
  const bundle = state.wikiBundle;
  const filter = state.wikiFilter || "all";
  const query = state.wikiSearchQuery || "";
  const rows = Array.isArray(bundle?.search_index) ? bundle.search_index.slice() : [];
  const filtered = rows.filter((entry) => wikiFilterMatches(entry, filter));
  if (!query) {
    const defaults = filter === "all"
      ? filtered.filter((entry) => entry.group !== "tutorial")
      : filtered;
    return defaults.slice(0, 12);
  }
  return filtered
    .map((entry) => ({ entry, score: wikiEntryScore(entry, query) }))
    .filter((row) => row.score >= 0)
    .sort((left, right) => right.score - left.score || String(left.entry?.title || "").localeCompare(String(right.entry?.title || ""), "zh-CN"))
    .slice(0, 20)
    .map((row) => row.entry);
}

function renderWikiArea() {
  const countsNode = document.querySelector("#wiki-counts");
  const hintNode = document.querySelector("#wiki-search-hint");
  const featuredRoot = document.querySelector("#wiki-featured-list");
  const resultRoot = document.querySelector("#wiki-result-list");
  const filterButtons = Array.from(document.querySelectorAll("[data-wiki-filter]"));
  const wikiCard = document.querySelector("#wiki-card");

  if (wikiCard && !wikiCard.open && !state.wikiSearchQuery) {
    if (countsNode) countsNode.textContent = state.wikiBundle ? "已缓存，展开后检索" : "展开后加载";
    if (hintNode) hintNode.textContent = "展开后可检索玩法教程、材料来源、法宝、丹药、符箓、功法、称号、成就与配方。";
    if (featuredRoot) featuredRoot.innerHTML = "";
    if (resultRoot) resultRoot.innerHTML = "";
    return;
  }
  const bundle = state.wikiBundle || hydrateWikiBundleFromCache();

  filterButtons.forEach((button) => {
    button.classList.toggle("is-active", (button.dataset.wikiFilter || "all") === (state.wikiFilter || "all"));
  });

  if (!bundle) {
    if (state.wikiBundleLoading) {
      if (countsNode) countsNode.textContent = "正在整理词条...";
      if (hintNode) hintNode.textContent = "首次打开时才会拉取 Wiki 词条，当前正在加载属性说明、玩法教程与掉落来源。";
      renderWikiCards(featuredRoot, [], { emptyTitle: "Wiki 加载中", emptyText: "正在整理属性说明、新手手册与掉落词条，请稍候。" });
      renderWikiCards(resultRoot, [], { emptyTitle: "等待检索", emptyText: "Wiki 正在加载，完成后可立即搜索玩法和物品来源。" });
      return;
    }
    if (countsNode) countsNode.textContent = "展开或搜索后加载";
    if (hintNode) hintNode.textContent = "可搜索属性说明、玩法教程、秘境、奇遇、Boss、灵田、垂钓、赌坊、材料来源与配方获取方式。为减少首页加载时间，Wiki 改为按需加载。";
    renderWikiCards(featuredRoot, [], { emptyTitle: "按需加载 Wiki", emptyText: "展开本模块或输入关键词后，再拉取玩法手册与掉落词条。" });
    renderWikiCards(resultRoot, [], { emptyTitle: "等待检索", emptyText: "输入关键词后，可快速定位玩法和物品来源。" });
    return;
  }

  const counts = bundle.counts || {};
  const examples = Array.isArray(bundle.search_examples) ? bundle.search_examples.filter(Boolean) : [];
  if (countsNode) {
    countsNode.textContent = `教程 ${Number(counts.tutorial || 0)} · 属性 ${Number(counts.attribute || 0)} · 活动 ${Number(counts.activity || 0)} · 材料 ${Number(counts.material || 0)} · 法宝 ${Number(counts.artifact || 0)} · 丹药 ${Number(counts.pill || 0)} · 符箓 ${Number(counts.talisman || 0)} · 功法 ${Number(counts.technique || 0)} · 称号 ${Number(counts.title || 0)} · 配方 ${Number(counts.recipe || 0)} · 成就 ${Number(counts.achievement || 0)}`;
  }
  if (hintNode) {
    hintNode.textContent = examples.length
      ? `试试这些关键词：${examples.join("、")}`
      : "可搜索属性说明、玩法教程、秘境、奇遇、Boss、灵田、垂钓、赌坊、材料来源与配方获取方式，也可按入门、探索、炼制、战斗、任务、社交、宗门筛选。";
  }

  renderWikiCards(featuredRoot, bundle.featured_tutorials || [], {
    emptyTitle: "暂无推荐教程",
    emptyText: "主人还没有补充玩法手册。",
  });

  const query = state.wikiSearchQuery || "";
  const entries = currentWikiEntries();
  renderWikiCards(resultRoot, entries, {
    emptyTitle: query ? "没有找到对应词条" : "暂无检索词条",
    emptyText: query
      ? "可换个关键词，或先搜玩法名、材料名、法宝名、丹药名、符箿名、功法名、成就名、配方名。"
      : "输入关键词后，可查看对应的玩法与来源说明。",
  });
}

async function openWikiEntry(entryId) {
  const rows = Array.isArray(state.wikiBundle?.search_index) ? state.wikiBundle.search_index : [];
  const entry = rows.find((item) => String(item?.id || "") === String(entryId || ""));
  if (!entry) return;
  const lines = wikiPopupLines(entry);
  await popup(
    wikiCardTitle(entry) || entry.title || "修仙 Wiki",
    lines.join("\n\n"),
    "success",
    { autoCloseMs: 0 },
  );
}

async function refreshWikiBundle({ force = false } = {}) {
  if (!force && state.wikiBundle) {
    renderWikiArea();
    return state.wikiBundle;
  }
  if (state.wikiBundlePromise) {
    return state.wikiBundlePromise;
  }
  state.wikiBundleLoading = true;
  renderWikiArea();
  state.wikiBundlePromise = postJson("/plugins/xiuxian/api/wiki", {}, { timeoutMs: WIKI_REQUEST_TIMEOUT_MS })
    .then((bundle) => {
      state.wikiBundle = bundle;
      writeSessionStorage(WIKI_BUNDLE_CACHE_KEY, JSON.stringify(bundle));
      return bundle;
    })
    .finally(() => {
      state.wikiBundleLoading = false;
      state.wikiBundlePromise = null;
      renderWikiArea();
    });
  return state.wikiBundlePromise;
}

function ensureWikiBundle() {
  hydrateWikiBundleFromCache();
  if (state.wikiBundleRequested && (state.wikiBundle || state.wikiBundlePromise)) {
    return state.wikiBundlePromise || Promise.resolve(state.wikiBundle);
  }
  state.wikiBundleRequested = true;
  return refreshWikiBundle({ force: true });
}

function formatRemainingDuration(totalSeconds) {
  const safeSeconds = Math.max(Number(totalSeconds || 0), 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = Math.floor(safeSeconds % 60);
  if (hours > 0) return `${hours} 小时 ${minutes} 分`;
  if (minutes > 0) return `${minutes} 分 ${seconds} 秒`;
  return `${seconds} 秒`;
}

function officialShopName(bundle = state.profileBundle) {
  const raw = bundle?.settings?.official_shop_name;
  return String(raw || "").trim() || "官方商店";
}

function officialRecycleName(bundle = state.profileBundle) {
  const raw = bundle?.official_recycle?.shop_name;
  return String(raw || "").trim() || "万宝归炉";
}

function currentDuelLockReason(bundle = state.profileBundle) {
  const reason = bundle?.capabilities?.duel_lock_reason;
  return String(reason || "").trim();
}

function currentSocialInteractionLockReason(bundle = state.profileBundle) {
  const reason = bundle?.capabilities?.social_interaction_lock_reason;
  return String(reason || "").trim();
}

function currentSocialMode(bundle = state.profileBundle) {
  return String(bundle?.profile?.social_mode || "worldly").trim() || "worldly";
}

function attributeGrowthText(changes = [], prefix = "小幅成长") {
  const rows = (changes || [])
    .map((item) => {
      const label = String(item?.label || item?.key || "属性").trim();
      const value = Number(item?.value || 0);
      return value > 0 ? `${label}+${value}` : "";
    })
    .filter(Boolean);
  return rows.length ? `${prefix}：${rows.join("、")}` : "";
}

function setSelectOptions(select, options = [], selectedValue = "") {
  if (!select) return;
  const normalizedSelected = String(selectedValue ?? "");
  select.innerHTML = options.map((item) => `
    <option value="${escapeHtml(item.value)}" ${String(item.value) === normalizedSelected ? "selected" : ""}>${escapeHtml(item.label)}</option>
  `).join("");
}

function currentGiftTarget() {
  return state.giftTarget && Number(state.giftTarget.tg || 0) > 0 ? state.giftTarget : null;
}

function looksLikeProfileBundle(value) {
  return Boolean(
    value
    && typeof value === "object"
    && !Array.isArray(value)
    && value.profile
    && value.settings
    && value.capabilities
  );
}

function extractBundleCandidate(payload) {
  if (looksLikeProfileBundle(payload)) return payload;
  if (looksLikeProfileBundle(payload?.bundle)) return payload.bundle;
  if (looksLikeProfileBundle(payload?.profile)) return payload.profile;
  return null;
}

function rememberBundleCandidate(payload) {
  const candidate = extractBundleCandidate(payload);
  if (candidate) {
    state.pendingBundleCandidate = candidate;
  }
  return candidate;
}

function takePendingBundleCandidate() {
  const candidate = state.pendingBundleCandidate;
  state.pendingBundleCandidate = null;
  return candidate;
}

function deferUiWork(callback) {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(callback, { timeout: 900 });
    return;
  }
  window.setTimeout(callback, 16);
}

const DEFERRED_SECTION_IDS = new Set([
  "inventory-card",
  "technique-card",
  "official-shop-card",
  "official-recycle-card",
  "market-card",
  "auction-card",
  "sect-card",
  "task-card",
  "craft-card",
  "explore-card",
  "journal-card",
  "gift-card",
  "title-card",
  "furnace-card",
  "mentorship-card",
  "commission-card",
  "farm-card",
  "marriage-card",
  "fishing-card",
  "gambling-card",
]);

const DEFERRED_CARD_SECTIONS = {
  "inventory-card": "inventory",
  "technique-card": "technique",
  "official-shop-card": "official_shop",
  "official-recycle-card": "official_recycle",
  "market-card": "market",
  "auction-card": "auction",
  "sect-card": "sect",
  "task-card": "task",
  "craft-card": "craft",
  "explore-card": "explore",
  "journal-card": "journal",
  "gift-card": "gift",
  "title-card": "title",
  "furnace-card": "furnace",
  "mentorship-card": "mentorship",
  "commission-card": "commission",
  "farm-card": "farm",
  "marriage-card": "marriage",
  "fishing-card": "fishing",
  "gambling-card": "gambling",
};

const EXTERNAL_REFRESH_SECTION_IDS = new Set([
  "inventory-card",
  "market-card",
  "auction-card",
  "gift-card",
  "craft-card",
]);
const EXTERNAL_REFRESH_INTERVAL_MS = 15000;

const LAZY_SECTION_IDS = [
  ...DEFERRED_SECTION_IDS,
  "boss-card",
  "leaderboard-card",
];

function renderGiftTargetSelection() {
  const root = document.querySelector("#gift-target-selected");
  const hidden = document.querySelector("#gift-target");
  const target = currentGiftTarget();
  if (!root || !hidden) return;
  hidden.value = target ? String(target.tg) : "";
  if (!target) {
    root.innerHTML = "";
    return;
  }
  const hint = target.username ? `@${target.username}` : `TG ${target.tg}`;
  root.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>已选目标：${escapeHtml(target.display_label || hint)}</strong>
        <button type="button" class="ghost" data-clear-gift-target>重新选择</button>
      </div>
      <p>当前仅展示公开昵称与用户名：${escapeHtml(hint)}。</p>
    </article>
  `;
}

function renderGiftSearchResults(items = state.giftSearchResults) {
  const root = document.querySelector("#gift-player-search-results");
  if (!root) return;
  const keyword = String(state.giftSearchQuery || "").trim();
  if (!keyword) {
    root.innerHTML = "";
    return;
  }
  if (!(items || []).length) {
    root.innerHTML = `<article class="stack-item"><strong>未找到匹配道友</strong><p>试试输入 @用户名、TG ID 或昵称。</p></article>`;
    return;
  }
  root.innerHTML = (items || []).map((item) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(item.display_label || `TG ${item.tg}`)}</strong>
        <button
          type="button"
          class="ghost"
          data-gift-target-tg="${escapeHtml(item.tg)}"
          data-gift-target-label="${escapeHtml(item.display_label || `TG ${item.tg}`)}"
          data-gift-target-username="${escapeHtml(item.username || "")}"
        >选择</button>
      </div>
      <p>${escapeHtml(item.username ? `@${item.username}` : `TG ${item.tg}`)}</p>
    </article>
  `).join("");
}

function setGiftTarget(target) {
  const tgValue = Number(target?.tg || 0);
  state.giftTarget = tgValue > 0
    ? {
      tg: tgValue,
      display_label: String(target?.display_label || target?.label || `TG ${tgValue}`).trim(),
      username: String(target?.username || "").trim().replace(/^@/, ""),
    }
    : null;
  renderGiftTargetSelection();
  syncGiftPanelState(state.profileBundle);
}

function currentMentorshipTarget() {
  return state.mentorshipTarget && Number(state.mentorshipTarget.tg || 0) > 0 ? state.mentorshipTarget : null;
}

function renderMentorshipTargetSelection() {
  const root = document.querySelector("#mentorship-target-selected");
  const target = currentMentorshipTarget();
  if (!root) return;
  if (!target) {
    root.innerHTML = "";
    return;
  }
  const hint = target.username ? `@${target.username}` : `TG ${target.tg}`;
  root.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>已选目标：${escapeHtml(target.display_label || hint)}</strong>
        <button type="button" class="ghost" data-clear-mentorship-target>重新选择</button>
      </div>
      <p>当前仅展示公开昵称与用户名：${escapeHtml(hint)}。</p>
    </article>
  `;
}

function renderMentorshipSearchResults(items = state.mentorshipSearchResults) {
  const root = document.querySelector("#mentorship-player-search-results");
  if (!root) return;
  const keyword = String(state.mentorshipSearchQuery || "").trim();
  if (!keyword) {
    root.innerHTML = "";
    return;
  }
  if (!(items || []).length) {
    root.innerHTML = `<article class="stack-item"><strong>未找到匹配道友</strong><p>试试输入 @用户名、TG ID 或昵称。</p></article>`;
    return;
  }
  root.innerHTML = (items || []).map((item) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(item.display_label || `TG ${item.tg}`)}</strong>
        <button
          type="button"
          class="ghost"
          data-mentorship-target-tg="${escapeHtml(item.tg)}"
          data-mentorship-target-label="${escapeHtml(item.display_label || `TG ${item.tg}`)}"
          data-mentorship-target-username="${escapeHtml(item.username || "")}"
        >选择</button>
      </div>
      <p>${escapeHtml(item.username ? `@${item.username}` : `TG ${item.tg}`)}</p>
    </article>
  `).join("");
}

function setMentorshipTarget(target) {
  const tgValue = Number(target?.tg || 0);
  state.mentorshipTarget = tgValue > 0
    ? {
      tg: tgValue,
      display_label: String(target?.display_label || target?.label || `TG ${tgValue}`).trim(),
      username: String(target?.username || "").trim().replace(/^@/, ""),
    }
    : null;
  renderMentorshipTargetSelection();
  syncMentorshipRequestComposer(state.profileBundle);
}

async function searchMentorshipPlayers(query, page = 1) {
  const keyword = String(query || "").trim();
  state.mentorshipSearchQuery = keyword;
  if (!keyword) {
    state.mentorshipSearchResults = [];
    renderMentorshipSearchResults([]);
    return { items: [], page: 1, page_size: 0, total: 0 };
  }
  const requestKeyword = keyword;
  const payload = await postJson("/plugins/xiuxian/api/player/search", {
    query: keyword,
    page,
    page_size: 8,
  });
  if (state.mentorshipSearchQuery !== requestKeyword) {
    return payload;
  }
  state.mentorshipSearchResults = payload.items || [];
  renderMentorshipSearchResults(state.mentorshipSearchResults);
  return payload;
}

function mentorshipRequestRoleLabel(role) {
  return String(role || "").trim() === "mentor" ? "收徒邀请" : "拜师申请";
}

function syncMentorshipRequestComposer(bundle = state.profileBundle) {
  renderMentorshipTargetSelection();
  renderMentorshipSearchResults();
  const mentorship = bundle?.mentorship || {};
  const target = currentMentorshipTarget();
  const role = document.querySelector("#mentorship-request-role")?.value || "disciple";
  const socialLockReason = currentSocialInteractionLockReason(bundle);
  let roleLockReason = "";
  if (role === "mentor" && !mentorship.can_take_disciple) {
    roleLockReason = mentorship.request_hint || "当前不可继续收徒。";
  }
  if (role === "disciple" && !mentorship.can_seek_mentor) {
    roleLockReason = mentorship.request_hint || "当前不可再拜师。";
  }
  const inputLockReason = socialLockReason || "";
  const submitLockReason = socialLockReason || roleLockReason || (target ? "" : "先选择目标道友。");
  ["#mentorship-player-query", "#mentorship-player-search", "#mentorship-request-role", "#mentorship-request-message"]
    .forEach((selector) => setDisabled(document.querySelector(selector), Boolean(inputLockReason), inputLockReason));
  setDisabled(document.querySelector("#mentorship-request-form button[type='submit']"), Boolean(submitLockReason), submitLockReason);
  const hint = document.querySelector("#mentorship-request-hint");
  if (hint) {
    const roleText = mentorshipRequestRoleLabel(role);
    hint.textContent = socialLockReason
      ? socialLockReason
      : roleLockReason
        ? roleLockReason
        : target
          ? `${mentorship.request_hint || "可继续结识同道。"} 当前准备发送：${roleText} -> ${target.display_label || `TG ${target.tg}`}。`
          : (mentorship.request_hint || "完成搜索并选中目标后，才可递上拜帖。");
  }
}

function currentMarriageTarget() {
  return state.marriageTarget && Number(state.marriageTarget.tg || 0) > 0 ? state.marriageTarget : null;
}

function renderMarriageTargetSelection() {
  const root = document.querySelector("#marriage-target-selected");
  const target = currentMarriageTarget();
  if (!root) return;
  if (!target) {
    root.innerHTML = "";
    return;
  }
  const hint = target.username ? `@${target.username}` : `TG ${target.tg}`;
  root.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>已选目标：${escapeHtml(target.display_label || hint)}</strong>
        <button type="button" class="ghost" data-clear-marriage-target>重新选择</button>
      </div>
      <p>当前仅展示公开昵称与用户名：${escapeHtml(hint)}。</p>
    </article>
  `;
}

function renderMarriageSearchResults(items = state.marriageSearchResults) {
  const root = document.querySelector("#marriage-player-search-results");
  if (!root) return;
  const keyword = String(state.marriageSearchQuery || "").trim();
  if (!keyword) {
    root.innerHTML = "";
    return;
  }
  if (!(items || []).length) {
    root.innerHTML = `<article class="stack-item"><strong>未找到匹配道友</strong><p>试试输入 @用户名、TG ID 或昵称。</p></article>`;
    return;
  }
  root.innerHTML = (items || []).map((item) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(item.display_label || `TG ${item.tg}`)}</strong>
        <button
          type="button"
          class="ghost"
          data-marriage-target-tg="${escapeHtml(item.tg)}"
          data-marriage-target-label="${escapeHtml(item.display_label || `TG ${item.tg}`)}"
          data-marriage-target-username="${escapeHtml(item.username || "")}"
        >选择</button>
      </div>
      <p>${escapeHtml(item.username ? `@${item.username}` : `TG ${item.tg}`)}</p>
    </article>
  `).join("");
}

function setMarriageTarget(target) {
  const tgValue = Number(target?.tg || 0);
  state.marriageTarget = tgValue > 0
    ? {
      tg: tgValue,
      display_label: String(target?.display_label || target?.label || `TG ${tgValue}`).trim(),
      username: String(target?.username || "").trim().replace(/^@/, ""),
    }
    : null;
  renderMarriageTargetSelection();
  syncMarriageRequestComposer(state.profileBundle);
}

async function searchMarriagePlayers(query, page = 1) {
  const keyword = String(query || "").trim();
  state.marriageSearchQuery = keyword;
  if (!keyword) {
    state.marriageSearchResults = [];
    renderMarriageSearchResults([]);
    return { items: [], page: 1, page_size: 0, total: 0 };
  }
  const requestKeyword = keyword;
  const payload = await postJson("/plugins/xiuxian/api/player/search", {
    query: keyword,
    page,
    page_size: 8,
  });
  if (state.marriageSearchQuery !== requestKeyword) {
    return payload;
  }
  state.marriageSearchResults = payload.items || [];
  renderMarriageSearchResults(state.marriageSearchResults);
  return payload;
}

function syncGenderComposer(bundle = state.profileBundle) {
  const marriage = bundle?.marriage || {};
  const select = document.querySelector("#gender-select");
  const submit = document.querySelector("#gender-set-form button[type='submit']");
  const hint = document.querySelector("#gender-set-hint");
  const lockReason = marriage.can_set_gender ? "" : (marriage.gender_change_reason || "");
  if (select) {
    select.value = String(marriage.gender || bundle?.profile?.gender || "male");
  }
  setDisabled(select, Boolean(lockReason), lockReason);
  setDisabled(submit, Boolean(lockReason), lockReason);
  if (hint) {
    hint.textContent = lockReason
      ? lockReason
      : marriage.gender_set
        ? `当前已设置为${marriage.gender_label || "已设置"}。未结为道侣前可重新调整。`
        : "未设置性别前，其他修仙玩法会被锁定。";
  }
}

function syncMarriageRequestComposer(bundle = state.profileBundle) {
  renderMarriageTargetSelection();
  renderMarriageSearchResults();
  const marriage = bundle?.marriage || {};
  const target = currentMarriageTarget();
  const socialLockReason = currentSocialInteractionLockReason(bundle);
  const inputLockReason = socialLockReason || (!marriage.can_request_marriage ? (marriage.request_hint || "当前不可发起姻缘请求。") : "");
  const submitLockReason = inputLockReason || (target ? "" : "先选择目标道友。");
  ["#marriage-player-query", "#marriage-player-search", "#marriage-request-message"]
    .forEach((selector) => setDisabled(document.querySelector(selector), Boolean(inputLockReason), inputLockReason));
  setDisabled(document.querySelector("#marriage-request-form button[type='submit']"), Boolean(submitLockReason), submitLockReason);
  const hint = document.querySelector("#marriage-request-hint");
  if (hint) {
    hint.textContent = submitLockReason
      ? submitLockReason
      : `${marriage.request_hint || "可递上结缘信物。"} 当前准备发送给 ${target?.display_label || `TG ${target?.tg || 0}`}。`;
  }
}

function inventoryGiftRows(kind, bundle = state.profileBundle) {
  const profileBundle = bundle || {};
  if (kind === "artifact") {
    return (profileBundle.artifacts || [])
      .map((row) => {
        const quantity = Number(row.unbound_quantity ?? Math.max(Number(row.quantity || 0) - Number(row.bound_quantity || 0), 0));
        return {
          value: Number(row.artifact?.id || 0),
          label: `${row.artifact?.name || "未命名法宝"} · 可赠 ${quantity}`,
          quantity,
        };
      })
      .filter((item) => item.value > 0 && item.quantity > 0);
  }
  if (kind === "talisman") {
    return (profileBundle.talismans || [])
      .map((row) => {
        const quantity = Number(row.unbound_quantity ?? Math.max(Number(row.quantity || 0) - Number(row.bound_quantity || 0), 0));
        return {
          value: Number(row.talisman?.id || 0),
          label: `${row.talisman?.name || "未命名符箓"} · 可赠 ${quantity}`,
          quantity,
        };
      })
      .filter((item) => item.value > 0 && item.quantity > 0);
  }
  if (kind === "pill") {
    return (profileBundle.pills || [])
      .map((row) => ({
        value: Number(row.pill?.id || 0),
        label: `${row.pill?.name || "未命名丹药"} · 持有 ${Number(row.quantity || 0)}`,
        quantity: Number(row.quantity || 0),
      }))
      .filter((item) => item.value > 0 && item.quantity > 0);
  }
  return (profileBundle.materials || [])
    .map((row) => ({
      value: Number(row.material?.id || 0),
      label: `${row.material?.name || "未命名材料"} · 持有 ${Number(row.quantity || 0)}`,
      quantity: Number(row.quantity || 0),
    }))
    .filter((item) => item.value > 0 && item.quantity > 0);
}

function renderItemGiftInventorySelect(bundle = state.profileBundle) {
  const kind = document.querySelector("#item-gift-kind")?.value || "artifact";
  const select = document.querySelector("#item-gift-ref");
  const quantityInput = document.querySelector("#item-gift-quantity");
  const hint = document.querySelector("#item-gift-hint");
  const previousValue = select?.value || "";
  const rows = inventoryGiftRows(kind, bundle);
  if (!select) return;
  if (!rows.length) {
    setSelectOptions(select, [{ value: "", label: "当前类型暂无可赠送物品" }], "");
    if (quantityInput) quantityInput.value = "1";
    if (hint && !currentGiftTarget()) {
      hint.textContent = "先搜索并选中一位道友，再赠送背包物品。";
    } else if (hint) {
      hint.textContent = "当前类型没有可赠送的未绑定物品，切换类型后再试。";
    }
    return;
  }
  const selectedRow = rows.find((item) => String(item.value) === String(previousValue)) || rows[0];
  setSelectOptions(select, rows, String(selectedRow.value));
  if (quantityInput) {
    const maxQuantity = Math.max(Number(selectedRow.quantity || 1), 1);
    quantityInput.max = String(maxQuantity);
    quantityInput.value = String(Math.min(Number(quantityInput.value || 1), maxQuantity));
  }
  if (hint) {
    const target = currentGiftTarget();
    hint.textContent = target
      ? `当前赠送目标：${target.display_label || (target.username ? `@${target.username}` : `TG ${target.tg}`)}。不会展示对方面板信息。`
      : "先搜索并选中一位道友，再赠送背包物品。";
  }
}

function syncGiftPanelState(bundle = state.profileBundle) {
  renderGiftTargetSelection();
  renderGiftSearchResults();
  renderItemGiftInventorySelect(bundle);
  const duelLockReason = currentDuelLockReason(bundle);
  const socialLockReason = currentSocialInteractionLockReason(bundle);
  const target = currentGiftTarget();
  const interactionLockReason = duelLockReason || socialLockReason;
  const giftBlockedReason = interactionLockReason || (target ? "" : "先选择赠送对象。");
  ["#gift-player-query", "#gift-player-search", "#item-gift-kind", "#item-gift-ref", "#item-gift-quantity"]
    .forEach((selector) => setDisabled(document.querySelector(selector), Boolean(interactionLockReason), interactionLockReason));
  setDisabled(document.querySelector("#gift-form button[type='submit']"), Boolean(giftBlockedReason), giftBlockedReason);
  setDisabled(document.querySelector("#item-gift-form button[type='submit']"), Boolean(giftBlockedReason), giftBlockedReason);
}

async function searchGiftPlayers(query, page = 1) {
  const keyword = String(query || "").trim();
  state.giftSearchQuery = keyword;
  if (!keyword) {
    state.giftSearchResults = [];
    renderGiftSearchResults([]);
    return { items: [], page: 1, page_size: 0, total: 0 };
  }
  const requestKeyword = keyword;
  const payload = await postJson("/plugins/xiuxian/api/player/search", {
    query: keyword,
    page,
    page_size: 8,
  });
  if (state.giftSearchQuery !== requestKeyword) {
    return payload;
  }
  state.giftSearchResults = payload.items || [];
  renderGiftSearchResults(state.giftSearchResults);
  return payload;
}

function profileRootText(profile) {
  if (!profile.root_type) return "尚未踏入仙途";
  if (profile.root_type === "双灵根") {
    return `${profile.root_type} · ${profile.root_primary}/${profile.root_secondary} · ${profile.root_relation}`;
  }
  return `${profile.root_type} · ${profile.root_primary || "无属性"} · ${profile.root_relation || "待定"}`;
}

let bottomNavResizeObserver = null;

function syncBottomNavLayout() {
  const nav = document.querySelector("#bottom-nav");
  const height = nav && !nav.classList.contains("hidden") && nav.childElementCount
    ? Math.ceil(nav.getBoundingClientRect().height)
    : 0;
  document.documentElement.style.setProperty("--bottom-nav-height", `${height}px`);
}

function setupBottomNavLayout() {
  const nav = document.querySelector("#bottom-nav");
  if (!nav) return;
  if ("ResizeObserver" in window && !bottomNavResizeObserver) {
    bottomNavResizeObserver = new ResizeObserver(() => syncBottomNavLayout());
    bottomNavResizeObserver.observe(nav);
  }
  window.addEventListener("resize", syncBottomNavLayout, { passive: true });
  window.addEventListener("orientationchange", syncBottomNavLayout, { passive: true });
  syncBottomNavLayout();
}

function renderBottomNav(items = []) {
  const nav = document.querySelector("#bottom-nav");
  if (!nav) return;
  const currentPath = window.location.pathname;
  nav.innerHTML = "";
  nav.classList.toggle("hidden", !(items || []).length);
  for (const item of items || []) {
    const link = document.createElement("a");
    link.href = item.path;
    link.title = item.label || "";
    const icon = document.createElement("span");
    icon.className = "bottom-nav-icon";
    icon.textContent = String(item.icon || "").trim();
    const label = document.createElement("span");
    label.className = "bottom-nav-label";
    label.textContent = item.label || "未命名";
    if (icon.textContent) {
      link.appendChild(icon);
    }
    link.appendChild(label);
    if (item.path === currentPath) {
      link.classList.add("is-active");
    }
    nav.appendChild(link);
  }
  syncBottomNavLayout();
}

function visibleFoldCards() {
  return [...document.querySelectorAll(".fold-card")].filter((card) => !card.classList.contains("hidden"));
}

function foldCardLabel(card) {
  return card?.querySelector(".fold-summary h2")?.textContent?.trim() || "未命名模块";
}

function foldToolbarScrollOffset() {
  const toolbar = document.querySelector("#fold-toolbar");
  if (!toolbar || toolbar.classList.contains("hidden")) return 12;
  const top = Number.parseFloat(window.getComputedStyle(toolbar).top || "0");
  return Math.ceil((Number.isFinite(top) ? top : 0) + toolbar.getBoundingClientRect().height + 12);
}

function scrollFoldCardIntoView(card, { behavior = "smooth" } = {}) {
  if (!card) return;
  card.style.scrollMarginTop = `${foldToolbarScrollOffset()}px`;
  card.scrollIntoView({ behavior, block: "start", inline: "nearest" });
}

async function jumpToFoldCard(cardId) {
  const card = document.getElementById(cardId);
  if (!card || card.classList.contains("hidden")) return;
  card.open = true;
  syncFoldToolbar();
  refreshExternallyMutableSection(card.id);
  renderLazyFoldCard(card.id, { force: true });
  await waitForUiFrames(2);
  scrollFoldCardIntoView(card);
  window.setTimeout(() => {
    if (!card.isConnected || card.classList.contains("hidden")) return;
    scrollFoldCardIntoView(card, { behavior: "auto" });
  }, 180);
}

function candidatePageScrollTargets() {
  const targets = [];
  const pushTarget = (target) => {
    if (!target || targets.includes(target)) return;
    targets.push(target);
  };
  pushTarget(document.scrollingElement);
  pushTarget(document.documentElement);
  pushTarget(document.body);
  pushTarget(document.querySelector(".app-shell"));
  return targets;
}

function effectivePageScrollTargets() {
  return candidatePageScrollTargets().filter((target) => {
    if (!target) return false;
    if (target === document.body || target === document.documentElement || target === document.scrollingElement) {
      const scrollHeight = Math.max(
        Number(document.documentElement?.scrollHeight || 0),
        Number(document.body?.scrollHeight || 0),
        Number(target.scrollHeight || 0)
      );
      const clientHeight = Math.max(
        Number(window.innerHeight || 0),
        Number(document.documentElement?.clientHeight || 0),
        Number(target.clientHeight || 0)
      );
      return scrollHeight > clientHeight;
    }
    return Number(target.scrollHeight || 0) > Number(target.clientHeight || 0);
  });
}

function currentPageScrollTop() {
  const tops = candidatePageScrollTargets().map((target) => Number(target?.scrollTop || 0));
  tops.push(Number(window.scrollY || 0));
  return Math.max(...tops, 0);
}

function scrollPageToTop({ behavior = "smooth" } = {}) {
  const resolvedBehavior = behavior === "instant" ? "auto" : behavior;
  window.scrollTo({ top: 0, behavior: resolvedBehavior });
  effectivePageScrollTargets().forEach((target) => {
    if (!target) return;
    if (typeof target.scrollTo === "function") {
      target.scrollTo({ top: 0, behavior: resolvedBehavior });
      return;
    }
    target.scrollTop = 0;
  });
  if (behavior === "instant") {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }
}

function watchPageScroll(listener) {
  const seen = new Set();
  [window, ...candidatePageScrollTargets()].forEach((target) => {
    if (!target || seen.has(target) || typeof target.addEventListener !== "function") return;
    seen.add(target);
    target.addEventListener("scroll", listener, { passive: true });
  });
}

function lazyCardCanRender(cardId, { force = false } = {}) {
  const card = document.getElementById(cardId);
  if (!card || card.classList.contains("hidden")) return false;
  return force || card.open;
}

function setLazyCardLoading(cardId, message = "正在加载该模块...") {
  const card = document.getElementById(cardId);
  const root = card?.querySelector(".fold-body .stack-list");
  if (!root || root.children.length) return;
  root.innerHTML = `<article class="stack-item"><strong>${escapeHtml(message)}</strong><p>请稍候。</p></article>`;
}

function lazyRenderMetrics(bundle = state.profileBundle) {
  const retreating = Boolean(bundle?.capabilities?.is_in_retreat);
  const equippedArtifacts = bundle?.equipped_artifacts || [];
  const equipLimit = bundle?.settings?.artifact_equip_limit || bundle?.capabilities?.artifact_equip_limit || 1;
  return { retreating, equippedArtifacts, equipLimit };
}

function ensureLeaderboardLoaded() {
  if (state.leaderboard.loaded) return Promise.resolve(state.leaderboard);
  setLazyCardLoading("leaderboard-card", "正在加载排行榜...");
  return refreshLeaderboard(state.leaderboard.kind || "stone", state.leaderboard.page || 1).catch((error) => {
    const message = normalizeError(error, "加载排行榜失败。");
    setStatus(message, "error");
    throw error;
  });
}

function renderLazyFoldCard(cardId, { force = false } = {}) {
  if (!lazyCardCanRender(cardId, { force })) return false;
  if (cardId === "leaderboard-card") {
    ensureLeaderboardLoaded().catch(() => null);
    return true;
  }
  if (DEFERRED_SECTION_IDS.has(cardId)) {
    const section = DEFERRED_CARD_SECTIONS[cardId];
    if (section && !state.deferredBundleLoaded && !state.deferredSectionsLoaded.has(section)) {
      setLazyCardLoading(cardId);
      loadDeferredSection(section, { silent: true })
        .then(() => renderLazyFoldCard(cardId, { force: true }))
        .catch(() => null);
      return true;
    }
  }
  const bundle = state.profileBundle;
  if (!bundle) return false;
  const { retreating, equippedArtifacts, equipLimit } = lazyRenderMetrics(bundle);
  switch (cardId) {
    case "inventory-card":
      renderArtifactList(bundle.artifacts || [], retreating, equipLimit, equippedArtifacts.length);
      renderTalismanList(bundle.talismans || [], retreating);
      renderPillList(bundle.pills || [], retreating);
      renderMaterialInventoryList(bundle.materials || []);
      return true;
    case "technique-card":
      renderTechniqueArea(bundle);
      return true;
    case "official-shop-card":
      renderOfficialShop(bundle.official_shop || [], retreating);
      return true;
    case "official-recycle-card":
      renderOfficialRecyclePanel(bundle, retreating);
      return true;
    case "market-card":
      renderPersonalShop(bundle.personal_shop || []);
      renderCommunityShop(bundle.community_shop || [], retreating);
      renderInventorySelect();
      return true;
    case "auction-card":
      renderAuctionInventorySelect();
      renderPersonalAuctions(bundle.personal_auctions || []);
      renderCommunityAuctions(bundle.community_auctions || []);
      return true;
    case "sect-card":
      renderSectArea(bundle);
      return true;
    case "task-card":
      renderTaskArea(bundle);
      return true;
    case "craft-card":
      renderCraftArea(bundle);
      return true;
    case "explore-card":
      renderExploreArea(bundle);
      return true;
    case "journal-card":
      renderJournalArea(bundle);
      return true;
    case "title-card":
      renderTitleAchievementArea(bundle);
      return true;
    case "furnace-card":
      renderFurnaceArea(bundle);
      return true;
    case "mentorship-card":
      renderMentorshipArea(bundle);
      return true;
    case "commission-card":
      renderCommissionArea(bundle);
      return true;
    case "farm-card":
      renderFarmArea(bundle);
      return true;
    case "marriage-card":
      renderMarriageArea(bundle);
      return true;
    case "fishing-card":
      renderFishingArea(bundle);
      return true;
    case "boss-card":
      renderBossArea(bundle);
      return true;
    case "gambling-card": {
      renderGamblingArea(bundle);
      const gambling = bundle?.gambling || {};
      const duelLockReason = currentDuelLockReason(bundle);
      const poolBlockedReason = Number(gambling.pool_size || 0) > 0 ? "" : "当前赌坊奖池尚未配置。";
      const disabledReason = duelLockReason || poolBlockedReason;
      ["#gambling-exchange-count", "#gambling-open-count"].forEach((selector) => {
        setDisabled(document.querySelector(selector), Boolean(disabledReason), disabledReason);
      });
      setDisabled(document.querySelector("#gambling-exchange-form button[type='submit']"), Boolean(disabledReason), disabledReason);
      setDisabled(document.querySelector("#gambling-open-form button[type='submit']"), Boolean(disabledReason), disabledReason);
      return true;
    }
    case "gift-card":
      renderItemGiftInventorySelect(bundle);
      syncGiftPanelState(bundle);
      return true;
    default:
      return false;
  }
}

function refreshExternallyMutableSection(cardId) {
  if (!EXTERNAL_REFRESH_SECTION_IDS.has(cardId)) return;
  const now = Date.now();
  const lastRefresh = Number(state.externalSectionRefreshAt?.[cardId] || 0);
  if (now - lastRefresh < EXTERNAL_REFRESH_INTERVAL_MS) return;
  state.externalSectionRefreshAt = state.externalSectionRefreshAt || {};
  state.externalSectionRefreshAt[cardId] = now;
  const section = DEFERRED_CARD_SECTIONS[cardId];
  if (!section) return;
  state.deferredSectionsLoaded?.delete?.(section);
  if (state.deferredBundleLoaded) {
    state.deferredBundleLoaded = false;
    state.deferredBundlePromise = null;
  }
  loadDeferredSection(section, { silent: true }).catch(() => null);
}

function renderOpenLazyFoldCards() {
  LAZY_SECTION_IDS.forEach((cardId) => renderLazyFoldCard(cardId));
}

function queueOpenLazyFoldCards() {
  deferUiWork(renderOpenLazyFoldCards);
}

function keepShortcutVisible(shortcuts, button) {
  if (!shortcuts || !button) return;
  if (shortcuts.scrollWidth <= shortcuts.clientWidth + 4) return;

  const padding = 12;
  const visibleLeft = Number(shortcuts.scrollLeft || 0);
  const visibleRight = visibleLeft + Number(shortcuts.clientWidth || 0);
  const buttonLeft = Number(button.offsetLeft || 0) - padding;
  const buttonRight = Number(button.offsetLeft || 0) + Number(button.offsetWidth || 0) + padding;

  if (buttonLeft >= visibleLeft && buttonRight <= visibleRight) {
    return;
  }

  const centeredLeft = Math.max(
    0,
    Number(button.offsetLeft || 0) - Math.max((Number(shortcuts.clientWidth || 0) - Number(button.offsetWidth || 0)) / 2, padding)
  );
  shortcuts.scrollTo({
    left: centeredLeft,
    behavior: "smooth",
  });
}

function syncFoldToolbar() {
  const toolbar = document.querySelector("#fold-toolbar");
  if (!toolbar) return;

  const cards = visibleFoldCards();
  toolbar.classList.toggle("hidden", cards.length < 2);

  const count = document.querySelector("#fold-count");
  if (count) {
    count.textContent = `(${cards.length})`;
  }

  const openAllButton = document.querySelector("[data-fold-open-all]");
  const closeAllButton = document.querySelector("[data-fold-close-all]");
  if (openAllButton) {
    openAllButton.disabled = !cards.some((card) => !card.open);
  }
  if (closeAllButton) {
    closeAllButton.disabled = !cards.some((card) => card.open);
  }

  const shortcuts = document.querySelector("#fold-shortcuts");
  if (shortcuts) {
    shortcuts.innerHTML = "";
    for (const card of cards) {
      if (!card.id) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `ghost fold-shortcut${card.open ? " is-active" : ""}`;
      button.textContent = foldCardLabel(card);
      button.dataset.foldTarget = card.id;
      shortcuts.appendChild(button);
    }
    keepShortcutVisible(shortcuts, shortcuts.querySelector(".is-active"));
  }
}

function toggleFoldCards(open) {
  visibleFoldCards().forEach((card) => {
    card.open = open;
  });
  syncFoldToolbar();
}

function isNarrowViewport() {
  const matchMedia = window.matchMedia?.bind(window);
  const isNarrow = matchMedia?.("(max-width: 720px)")?.matches ?? window.innerWidth <= 720;
  const isShortLandscape = matchMedia?.("(orientation: landscape) and (max-height: 520px)")?.matches
    ?? (window.innerWidth > window.innerHeight && window.innerHeight <= 520);
  const hasTouchPointer = matchMedia?.("(pointer: coarse)")?.matches ?? navigator.maxTouchPoints > 0;
  return isNarrow || (hasTouchPointer && isShortLandscape);
}

function scrollElementIntoComfortableView(element, options = {}) {
  if (!element || !isNarrowViewport()) return;
  window.setTimeout(() => {
    element.scrollIntoView({
      behavior: options.behavior || "smooth",
      block: options.block || "start",
      inline: "nearest",
    });
  }, options.delay ?? 80);
}

function setupFoldToolbar() {
  const openAllButton = document.querySelector("[data-fold-open-all]");
  if (openAllButton && !openAllButton.dataset.foldToolbarBound) {
    openAllButton.dataset.foldToolbarBound = "1";
    openAllButton.addEventListener("click", () => toggleFoldCards(true));
  }
  const closeAllButton = document.querySelector("[data-fold-close-all]");
  if (closeAllButton && !closeAllButton.dataset.foldToolbarBound) {
    closeAllButton.dataset.foldToolbarBound = "1";
    closeAllButton.addEventListener("click", () => toggleFoldCards(false));
  }
  const shortcuts = document.querySelector("#fold-shortcuts");
  if (shortcuts && !shortcuts.dataset.foldToolbarBound) {
    shortcuts.dataset.foldToolbarBound = "1";
    shortcuts.addEventListener("click", (event) => {
      const button = event.target.closest("[data-fold-target]");
      if (!button) return;
      jumpToFoldCard(button.dataset.foldTarget);
    });
  }

  document.querySelectorAll(".fold-card").forEach((card) => {
    if (card.dataset.foldToolbarBound) return;
    card.dataset.foldToolbarBound = "1";
    card.addEventListener("toggle", () => {
      syncFoldToolbar();
      if (card.open) {
        refreshExternallyMutableSection(card.id);
        renderLazyFoldCard(card.id, { force: true });
      }
    });
  });
  syncFoldToolbar();
}

function setupMobileInteractionPolish() {
  installTouchContextMenuGuard();

  document.addEventListener("focusin", (event) => {
    const field = event.target?.closest?.("input, textarea, select");
    if (!field || field.closest(".modal-card")) return;
    if (field.matches("input[type='number']")) field.setAttribute("inputmode", "numeric");
    if (field.matches("input[type='search']")) field.setAttribute("enterkeyhint", "search");
    if (field.matches("input[type='url']")) field.setAttribute("inputmode", "url");
    scrollElementIntoComfortableView(field, { block: "center", delay: 220 });
  });

  document.querySelectorAll("input[type='number']").forEach((input) => {
    input.setAttribute("inputmode", "numeric");
  });
  document.querySelectorAll("input[type='search']").forEach((input) => {
    input.setAttribute("enterkeyhint", "search");
  });
  document.querySelectorAll("input[type='url']").forEach((input) => {
    input.setAttribute("inputmode", "url");
  });
}

function ensureSectionState(selector, visible, openWhenVisible = false) {
  const section = document.querySelector(selector);
  if (!section) return;
  section.classList.toggle("hidden", !visible);
  if (!visible) {
    section.open = false;
  } else if (openWhenVisible) {
    section.open = true;
  }
  syncFoldToolbar();
}

function inventoryRowsByKind(kind, bundle = state.profileBundle) {
  const source = bundle || {};
  if (kind === "artifact") return source.artifacts || [];
  if (kind === "pill") return source.pills || [];
  if (kind === "talisman") return source.talismans || [];
  if (kind === "material") return source.materials || [];
  if (kind === "technique") return source.techniques || [];
  return [];
}

function tradeableInventoryRows(kind, bundle = state.profileBundle) {
  return inventoryRowsByKind(kind, bundle).filter((row) => Number(row.tradeable_quantity ?? row.quantity ?? (kind === "technique" ? 1 : 0)) > 0);
}

function populateTradeableInventorySelect(select, kind, emptyText) {
  if (!select) return;
  const previousValue = select.value;
  const rows = tradeableInventoryRows(kind);
  select.innerHTML = "";
  if (!rows.length) {
    select.innerHTML = `<option value="">${emptyText}</option>`;
    return;
  }

  rows.forEach((row) => {
    const item = kind === "technique" ? (row.technique || row) : row[kind];
    const quantity = Number(row.tradeable_quantity ?? row.quantity ?? 1);
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = `${item.name} · 可交易 ${quantity}`;
    select.appendChild(option);
  });

  if ([...select.options].some((option) => String(option.value) === String(previousValue))) {
    select.value = previousValue;
  }
}

function syncAuctionQuantityState() {
  const kind = document.querySelector("#auction-item-kind")?.value || "artifact";
  const quantityInput = document.querySelector("#auction-quantity");
  if (!quantityInput) return;
  if (kind === "technique") {
    quantityInput.value = "1";
    quantityInput.min = "1";
    quantityInput.max = "1";
    quantityInput.readOnly = true;
    quantityInput.title = "功法拍卖数量固定为 1。";
    return;
  }
  quantityInput.min = "1";
  quantityInput.removeAttribute("max");
  quantityInput.readOnly = false;
  if (!quantityInput.disabled) {
    quantityInput.title = "";
  }
}

function renderInventorySelect() {
  const select = document.querySelector("#shop-item-ref");
  const kind = document.querySelector("#shop-item-kind")?.value || "artifact";
  populateTradeableInventorySelect(select, kind, "暂无可上架物品");
}

function renderAuctionInventorySelect() {
  const select = document.querySelector("#auction-item-ref");
  const kind = document.querySelector("#auction-item-kind")?.value || "artifact";
  populateTradeableInventorySelect(select, kind, "暂无可拍卖物品");
  syncAuctionQuantityState();
}

function officialRecycleItems(bundle = state.profileBundle) {
  return Array.isArray(bundle?.official_recycle?.items) ? bundle.official_recycle.items : [];
}

function findOfficialRecycleQuote(kind, itemRefId, bundle = state.profileBundle) {
  return officialRecycleItems(bundle).find(
    (row) => String(row.item_kind || "") === String(kind || "") && String(row.item_ref_id || "") === String(itemRefId || "")
  ) || null;
}

const OFFICIAL_RECYCLE_KIND_ORDER = ["artifact", "talisman", "pill", "material", "technique", "recipe"];

function officialRecycleKindRank(kind) {
  const index = OFFICIAL_RECYCLE_KIND_ORDER.indexOf(String(kind || ""));
  return index >= 0 ? index : OFFICIAL_RECYCLE_KIND_ORDER.length;
}

function officialRecycleSearchText(quote = {}) {
  return [
    quote.item_name,
    quote.item_kind_label,
    quote.item_kind,
    quote.quality_label,
    quote.quote_note,
    quote.unit_price_stone,
  ].map((value) => String(value || "").toLowerCase()).join(" ");
}

function officialRecycleVisibleQuotes(bundle = state.profileBundle) {
  const quotes = officialRecycleItems(bundle);
  const query = String(document.querySelector("#official-recycle-search")?.value || "").trim().toLowerCase();
  return query
    ? quotes.filter((quote) => officialRecycleSearchText(quote).includes(query))
    : quotes;
}

function officialRecycleSelectionKey(kind, itemRefId) {
  return `${String(kind || "")}:${String(itemRefId || "")}`;
}

function findOfficialRecycleQuoteBySelectionKey(selectionKey, bundle = state.profileBundle) {
  const [kind, itemRefId] = String(selectionKey || "").split(":");
  return findOfficialRecycleQuote(kind, itemRefId, bundle);
}

function officialRecycleIsFixedQuantityKind(kind) {
  return kind === "technique" || kind === "recipe";
}

function officialRecycleMaxQuantity(quote = {}) {
  if (officialRecycleIsFixedQuantityKind(String(quote.item_kind || ""))) {
    return 1;
  }
  return Math.max(Number(quote.available_quantity || 0), 0);
}

function defaultOfficialRecycleSelectionQuantity(quote = {}) {
  return Math.max(officialRecycleMaxQuantity(quote), 1);
}

function officialRecycleSelectedQuantity(kind, itemRefId) {
  const key = officialRecycleSelectionKey(kind, itemRefId);
  return Math.max(Number(state.officialRecycleSelections?.[key] || 0), 0);
}

function sanitizeOfficialRecycleSelections(bundle = state.profileBundle) {
  const nextSelections = {};
  const quotesByKey = new Map(
    officialRecycleItems(bundle).map((quote) => [
      officialRecycleSelectionKey(quote.item_kind, quote.item_ref_id),
      quote,
    ]),
  );
  for (const [key, rawQuantity] of Object.entries(state.officialRecycleSelections || {})) {
    const quote = quotesByKey.get(key);
    if (!quote) continue;
    const maxQuantity = officialRecycleMaxQuantity(quote);
    if (maxQuantity <= 0) continue;
    const normalizedQuantity = Math.min(Math.max(Number(rawQuantity || 0), 1), maxQuantity);
    nextSelections[key] = normalizedQuantity;
  }
  state.officialRecycleSelections = nextSelections;
}

function setOfficialRecycleSelection(quote, quantity) {
  if (!quote) return;
  const key = officialRecycleSelectionKey(quote.item_kind, quote.item_ref_id);
  const maxQuantity = officialRecycleMaxQuantity(quote);
  if (maxQuantity <= 0) {
    delete state.officialRecycleSelections[key];
    return;
  }
  const normalizedQuantity = Math.min(Math.max(Number(quantity || 0), 1), maxQuantity);
  state.officialRecycleSelections[key] = normalizedQuantity;
}

function clearOfficialRecycleSelection(kind, itemRefId) {
  const key = officialRecycleSelectionKey(kind, itemRefId);
  delete state.officialRecycleSelections[key];
}

function selectedOfficialRecycleEntries(bundle = state.profileBundle) {
  sanitizeOfficialRecycleSelections(bundle);
  return officialRecycleItems(bundle)
    .map((quote) => {
      const quantity = officialRecycleSelectedQuantity(quote.item_kind, quote.item_ref_id);
      if (quantity <= 0) return null;
      return { quote, quantity };
    })
    .filter(Boolean);
}

function updateOfficialRecycleBatchPreview(bundle = state.profileBundle) {
  const preview = document.querySelector("#official-recycle-batch-preview");
  const button = document.querySelector("#official-recycle-batch-submit");
  if (!preview) return;
  const blockedReason = currentDuelLockReason(bundle);
  const selectedEntries = selectedOfficialRecycleEntries(bundle);
  const totalKinds = selectedEntries.length;
  const totalQuantity = selectedEntries.reduce((sum, entry) => sum + Math.max(Number(entry.quantity || 0), 0), 0);
  const totalStone = selectedEntries.reduce(
    (sum, entry) => sum + Math.max(Number(entry.quote?.unit_price_stone || 0), 0) * Math.max(Number(entry.quantity || 0), 0),
    0,
  );
  preview.value = totalKinds
    ? `已勾选 ${totalKinds} 项，共 ${totalQuantity} 件，预计到账 ${totalStone} 灵石`
    : "未勾选归炉物品";
  if (button) {
    button.disabled = Boolean(blockedReason) || totalKinds <= 0;
    button.title = blockedReason || "";
  }
}

function officialRecycleQuoteCardHtml(quote, blockedReason) {
  const selectedQuantity = officialRecycleSelectedQuantity(quote.item_kind, quote.item_ref_id);
  const isChecked = selectedQuantity > 0;
  const maxQuantity = Math.max(officialRecycleMaxQuantity(quote), 1);
  const selectionEnabled = !blockedReason && maxQuantity > 0;
  const quantityValue = isChecked ? selectedQuantity : defaultOfficialRecycleSelectionQuantity(quote);
  const fixedQuantity = officialRecycleIsFixedQuantityKind(String(quote.item_kind || ""));
  const selectionKey = officialRecycleSelectionKey(quote.item_kind, quote.item_ref_id);
  return `
    <div class="stack-item-head">
      <strong>${escapeHtml(quote.item_name)}</strong>
      <span class="badge badge--normal">${escapeHtml(quote.unit_price_stone)} 灵石/件</span>
    </div>
    <div class="item-tags">
      ${qualityBadgeHtml(quote.quality_label || "凡品", quote.quality_color, "tag")}
      <span class="tag">${escapeHtml(quote.item_kind_label || quote.item_kind)}</span>
      <span class="tag">可归炉 ${escapeHtml(quote.available_quantity || 0)}</span>
    </div>
    <p>当前整包归炉最多到账 ${escapeHtml(quote.max_total_price_stone || 0)} 灵石。</p>
    <p class="muted">${escapeHtml(quote.quote_note || "")}</p>
    <div class="inline-actions recycle-selection-row">
      <label class="inline-check recycle-selection-check">
        <input type="checkbox" data-recycle-select="${escapeHtml(selectionKey)}" ${isChecked ? "checked" : ""} ${selectionEnabled ? "" : "disabled"}>
        <span>勾选本项</span>
      </label>
      <label class="recycle-selection-qty">
        <span>${fixedQuantity ? "数量固定 1" : "归炉数量"}</span>
        <input
          type="number"
          min="1"
          max="${escapeHtml(maxQuantity)}"
          value="${escapeHtml(quantityValue)}"
          data-recycle-quantity="${escapeHtml(selectionKey)}"
          ${!isChecked || !selectionEnabled ? "disabled" : ""}
          ${fixedQuantity ? "readonly" : ""}
        >
      </label>
    </div>
    ${blockedReason ? `<p class="reason-text">${escapeHtml(blockedReason)}</p>` : ""}
  `;
}

function populateOfficialRecycleInventorySelect() {
  const select = document.querySelector("#official-recycle-item-ref");
  if (!select) return;
  const previousValue = select.value;
  const kind = document.querySelector("#official-recycle-kind")?.value || "artifact";
  const rows = officialRecycleItems().filter((row) => String(row.item_kind || "") === String(kind) && Number(row.available_quantity || 0) > 0);
  select.innerHTML = "";
  if (!rows.length) {
    select.innerHTML = `<option value="">暂无可归炉物品</option>`;
    return;
  }
  rows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.item_ref_id;
    option.textContent = `${row.item_name} · ${row.quality_label || "凡品"} · 可归炉 ${row.available_quantity} · ${row.unit_price_stone} 灵石/件`;
    select.appendChild(option);
  });
  if ([...select.options].some((option) => String(option.value) === String(previousValue))) {
    select.value = previousValue;
  }
}

function updateOfficialRecycleQuotePreview(bundle = state.profileBundle) {
  const preview = document.querySelector("#official-recycle-preview");
  const quantityInput = document.querySelector("#official-recycle-quantity");
  const hint = document.querySelector("#official-recycle-hint");
  const kind = document.querySelector("#official-recycle-kind")?.value || "artifact";
  const itemRefId = Number(document.querySelector("#official-recycle-item-ref")?.value || 0);
  const quote = findOfficialRecycleQuote(kind, itemRefId, bundle);
  if (!preview || !quantityInput) return;
  if (!quote) {
    quantityInput.max = "1";
    if (Number(quantityInput.value || 0) < 1) quantityInput.value = "1";
    preview.value = officialRecycleItems(bundle).length ? "请选择可归炉物品" : "暂无可归炉物品";
    if (hint) {
      hint.textContent = String(bundle?.official_recycle?.description || "万宝归炉会按物品品阶与属性自动折价。");
    }
    return;
  }
  const availableQuantity = Math.max(Number(quote.available_quantity || 0), 0);
  let quantity = Math.max(Number(quantityInput.value || 1), 1);
  if (availableQuantity > 0) {
    quantity = Math.min(quantity, availableQuantity);
  }
  quantityInput.max = String(Math.max(availableQuantity, 1));
  quantityInput.value = String(quantity);
  const totalPrice = Math.max(Number(quote.unit_price_stone || 0), 0) * quantity;
  preview.value = `${quote.quality_label || "凡品"} · 单价 ${quote.unit_price_stone || 0} 灵石，当前可归炉 ${availableQuantity} 件，本次到账 ${totalPrice} 灵石`;
  if (hint) {
    hint.textContent = String(quote.quote_note || bundle?.official_recycle?.description || "万宝归炉会按物品品阶与属性自动折价。");
  }
}

function selectVisibleOfficialRecycleQuotes(bundle = state.profileBundle) {
  officialRecycleVisibleQuotes(bundle).forEach((quote) => {
    setOfficialRecycleSelection(quote, defaultOfficialRecycleSelectionQuantity(quote));
  });
}

function clearAllOfficialRecycleSelections() {
  state.officialRecycleSelections = {};
}

function buildOfficialRecycleBatchPayload(bundle = state.profileBundle) {
  return selectedOfficialRecycleEntries(bundle).map(({ quote, quantity }) => ({
    item_kind: quote.item_kind,
    item_ref_id: Number(quote.item_ref_id || 0),
    quantity: Number(quantity || 0),
  }));
}

function taskRequirementRows(kind) {
  const bundle = state.profileBundle || {};
  if (kind === "artifact") {
    return (bundle.artifacts || [])
      .filter((row) => Number(row.consumable_quantity ?? row.quantity ?? 0) > 0)
      .map((row) => ({ value: row.artifact.id, label: `${row.artifact.name} · 可提交 ${row.consumable_quantity ?? row.quantity}` }));
  }
  if (kind === "pill") {
    return (bundle.pills || [])
      .filter((row) => Number(row.quantity || 0) > 0)
      .map((row) => ({ value: row.pill.id, label: `${row.pill.name} · 库存 ${row.quantity}` }));
  }
  if (kind === "talisman") {
    return (bundle.talismans || [])
      .filter((row) => Number(row.consumable_quantity ?? row.quantity ?? 0) > 0)
      .map((row) => ({ value: row.talisman.id, label: `${row.talisman.name} · 可提交 ${row.consumable_quantity ?? row.quantity}` }));
  }
  if (kind === "material") {
    return (bundle.materials || [])
      .filter((row) => Number(row.quantity || 0) > 0)
      .map((row) => ({ value: row.material.id, label: `${row.material.name} · 库存 ${row.quantity}` }));
  }
  return [];
}

function renderTaskRequirementSelect() {
  const kind = document.querySelector("#task-required-kind")?.value || "";
  const select = document.querySelector("#task-required-ref");
  if (!select) return;
  const previousValue = select.value;
  const rows = taskRequirementRows(kind);
  select.innerHTML = "";
  select.disabled = !kind;
  if (!rows.length) {
    select.innerHTML = `<option value="">${kind ? "暂无可提交物品" : "无"}</option>`;
    select.value = "";
    return;
  }
  rows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.value;
    option.textContent = row.label;
    select.appendChild(option);
  });
  select.disabled = false;
  if (rows.some((row) => String(row.value) === String(previousValue))) {
    select.value = previousValue;
  }
}

function taskRewardRows(kind) {
  const bundle = state.profileBundle || {};
  if (kind === "artifact") {
    return (bundle.artifacts || [])
      .map((row) => ({
        value: row.artifact?.id,
        label: `${row.artifact?.name || "未命名法宝"} · 可扣押 ${Number(row.consumable_quantity ?? row.quantity ?? 0)}`,
        quantity: Number(row.consumable_quantity ?? row.quantity ?? 0),
      }))
      .filter((row) => Number(row.value || 0) > 0 && row.quantity > 0);
  }
  if (kind === "pill") {
    return (bundle.pills || [])
      .map((row) => ({
        value: row.pill?.id,
        label: `${row.pill?.name || "未命名丹药"} · 库存 ${Number(row.quantity || 0)}`,
        quantity: Number(row.quantity || 0),
      }))
      .filter((row) => Number(row.value || 0) > 0 && row.quantity > 0);
  }
  if (kind === "talisman") {
    return (bundle.talismans || [])
      .map((row) => ({
        value: row.talisman?.id,
        label: `${row.talisman?.name || "未命名符箓"} · 可扣押 ${Number(row.consumable_quantity ?? row.quantity ?? 0)}`,
        quantity: Number(row.consumable_quantity ?? row.quantity ?? 0),
      }))
      .filter((row) => Number(row.value || 0) > 0 && row.quantity > 0);
  }
  if (kind === "material") {
    return (bundle.materials || [])
      .map((row) => ({
        value: row.material?.id,
        label: `${row.material?.name || "未命名材料"} · 库存 ${Number(row.quantity || 0)}`,
        quantity: Number(row.quantity || 0),
      }))
      .filter((row) => Number(row.value || 0) > 0 && row.quantity > 0);
  }
  if (kind === "recipe") {
    return (bundle.recipes || [])
      .map((row) => {
        const recipe = row.recipe || row;
        return { value: recipe?.id || row.recipe_id, label: `${recipe?.name || "未命名配方"} · 可扣押 1`, quantity: 1, uniqueReward: true };
      })
      .filter((row) => Number(row.value || 0) > 0);
  }
  if (kind === "technique") {
    return (bundle.techniques || [])
      .map((row) => {
        const technique = row.technique || row;
        return { value: technique?.id || row.technique_id, label: `${technique?.name || "未命名功法"} · 可扣押 1`, quantity: 1, uniqueReward: true };
      })
      .filter((row) => Number(row.value || 0) > 0);
  }
  return [];
}

function selectedTaskRewardRow() {
  const kind = document.querySelector("#task-reward-kind")?.value || "";
  const refId = document.querySelector("#task-reward-ref")?.value || "";
  return taskRewardRows(kind).find((row) => String(row.value) === String(refId)) || null;
}

function taskRewardEscrowMultiplier() {
  const taskType = document.querySelector("#task-type")?.value || "custom";
  if (taskType === "quiz") return 1;
  return Math.max(Number(document.querySelector("#task-max-claimants")?.value || 1), 1);
}

function taskRewardStoneEscrowAmount() {
  const rewardStone = Math.max(Number(document.querySelector("#task-reward-stone")?.value || 0), 0);
  return rewardStone * taskRewardEscrowMultiplier();
}

function taskPublishStoneCostBreakdown(bundle = state.profileBundle) {
  const settings = bundle?.settings || {};
  const publishCost = Math.max(Number(settings.task_publish_cost || 0), 0);
  const escrowRewardStone = taskRewardStoneEscrowAmount();
  return {
    publishCost,
    escrowRewardStone,
    totalCost: publishCost + escrowRewardStone
  };
}

function taskPublishStoneCostText(breakdown) {
  const publishCost = Number(breakdown?.publishCost || 0);
  const escrowRewardStone = Number(breakdown?.escrowRewardStone || 0);
  const totalCost = Number(breakdown?.totalCost || 0);
  if (totalCost <= 0) return "发布不额外消耗灵石";
  if (publishCost > 0 && escrowRewardStone > 0) {
    return `发布会预扣 ${totalCost} 灵石（发布费 ${publishCost}，奖励押金 ${escrowRewardStone}）`;
  }
  if (escrowRewardStone > 0) return `发布会预扣 ${escrowRewardStone} 灵石作为奖励押金`;
  return `发布一次任务需要消耗 ${publishCost} 灵石`;
}

function renderTaskRewardSelect() {
  const kind = document.querySelector("#task-reward-kind")?.value || "";
  const select = document.querySelector("#task-reward-ref");
  const quantityInput = document.querySelector("#task-reward-quantity");
  if (!select) return;
  const previousValue = select.value;
  const rows = taskRewardRows(kind);
  select.innerHTML = "";
  select.disabled = !kind;
  if (kind === "recipe" || kind === "technique") {
    const quantityInput = document.querySelector("#task-reward-quantity");
    if (quantityInput) quantityInput.value = "1";
  }
  if (!rows.length) {
    select.innerHTML = `<option value="">${kind ? "暂无可作为奖励的物品" : "无"}</option>`;
    select.value = "";
    if (quantityInput) {
      quantityInput.value = "0";
      quantityInput.max = "0";
      quantityInput.disabled = !kind;
      quantityInput.readOnly = kind === "recipe" || kind === "technique";
    }
    return;
  }
  rows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.value;
    option.textContent = row.label;
    select.appendChild(option);
  });
  select.disabled = false;
  if (rows.some((row) => String(row.value) === String(previousValue))) {
    select.value = previousValue;
  } else {
    select.value = String(rows[0].value);
  }
  const selected = selectedTaskRewardRow() || rows[0];
  if (quantityInput) {
    const maxQuantity = Math.max(Number(selected?.quantity || 1), 1);
    quantityInput.min = kind ? "1" : "0";
    quantityInput.max = String(maxQuantity);
    quantityInput.value = kind === "recipe" || kind === "technique"
      ? "1"
      : String(Math.min(Math.max(Number(quantityInput.value || 1), 1), maxQuantity));
    quantityInput.disabled = !kind;
    quantityInput.readOnly = kind === "recipe" || kind === "technique";
  }
}

function applyShopNameState(shopName) {
  const input = document.querySelector("#shop-name");
  const button = document.querySelector("#shop-name-toggle");
  if (!input) return;
  input.value = shopName || "游仙小铺";
  input.readOnly = !state.shopNameEditing;
  if (button) {
    button.textContent = state.shopNameEditing ? "锁定铺名" : "修改铺名";
  }
}

function currentShopNameValue() {
  return document.querySelector("#shop-name")?.value?.trim()
    || state.profileBundle?.profile?.shop_name
    || "游仙小铺";
}

function focusShopNameInput(selectAll = false) {
  const input = document.querySelector("#shop-name");
  if (!input || input.disabled) return;
  input.focus({ preventScroll: true });
  if (selectAll) {
    input.select?.();
    return;
  }
  const end = input.value.length;
  input.setSelectionRange?.(end, end);
}

function openShopNameEditor(selectAll = true) {
  state.shopNameEditing = true;
  applyShopNameState(currentShopNameValue());
  focusShopNameInput(selectAll);
}

function artifactTypeLabel(type) {
  return type === "support" ? "辅助法宝" : "战斗法宝";
}

function artifactEquipCategoryLabel(item = {}) {
  if (item?.equip_category_label) return item.equip_category_label;
  switch (item?.equip_slot) {
    case "weapon":
      return "武器";
    case "shield":
      return "盾";
    case "accessory":
      return "饰品";
    case "clothes":
    case "chest":
    case "legs":
    case "boots":
    case "helmet":
      return "防具";
    case "bracelet":
    case "necklace":
    case "ring":
      return "饰品";
    default:
      return "装备";
  }
}

function fallbackReason(reason, fallback) {
  const message = String(reason || "").trim();
  return !message || /^[?？.\s]+$/.test(message) ? fallback : message;
}

function disabledReason(disabled, reason = "", fallback = "") {
  if (!disabled) return "";
  const message = String(reason || "").trim();
  if (!message) return String(fallback || "").trim();
  return /^[?？.\s]+$/.test(message) ? String(fallback || "").trim() : message;
}

function meaningfulTextLength(value) {
  return String(value ?? "").replace(/\s+/g, "").length;
}

function taskPublishBlockReason(bundle = state.profileBundle) {
  const settings = bundle?.settings || {};
  const publishAllowed = settings.allow_user_task_publish ?? true;
  const dailyLimit = Number(settings.user_task_daily_limit || 0);
  const publishedToday = Number(settings.user_task_published_today || 0);
  const currentStone = Number(bundle?.profile?.spiritual_stone || 0);
  const duelLockReason = currentDuelLockReason(bundle);
  const costBreakdown = taskPublishStoneCostBreakdown(bundle);

  if (!publishAllowed) {
    return "当前未开放玩家发布任务。";
  }
  if (duelLockReason) {
    return duelLockReason;
  }
  if (dailyLimit > 0 && publishedToday >= dailyLimit) {
    return `今日已发布 ${publishedToday}/${dailyLimit} 次悬赏，已达到上限。`;
  }
  if (currentStone < costBreakdown.totalCost) {
    return `${taskPublishStoneCostText(costBreakdown)}，当前灵石不足。`;
  }
  return "";
}

function syncTaskPublishState(bundle = state.profileBundle) {
  const publishNote = document.querySelector("#task-compose-note");
  const publishButton = document.querySelector("#task-form button[type='submit']");
  const settings = bundle?.settings || {};
  const dailyLimit = Number(settings.user_task_daily_limit || 0);
  const publishedToday = Number(settings.user_task_published_today || 0);
  const publishReason = taskPublishBlockReason(bundle);
  applyInteractiveBlockState(publishButton, Boolean(publishReason), publishReason);
  if (publishNote) {
    const limitText = dailyLimit > 0 ? `今日已发布 ${publishedToday}/${dailyLimit} 次。` : "今日发布次数不限。";
    const costText = taskPublishStoneCostText(taskPublishStoneCostBreakdown(bundle));
    publishNote.textContent = publishReason || `${costText}，灵石奖励会在发布时全额扣押，撤销未完成任务会退还剩余奖励押金，物品奖励会从背包扣押。${limitText}`;
  }
}

function applyInteractiveBlockState(button, blocked, reason = "") {
  if (!button) return;
  const message = blocked ? String(reason || "").trim() : "";
  button.classList.toggle("is-blocked", Boolean(message));
  button.title = message;
  button.setAttribute("aria-disabled", message ? "true" : "false");
  if (message) {
    button.dataset.blockedReason = message;
  } else {
    delete button.dataset.blockedReason;
  }
}

function renderProfile(bundle) {
  state.profileBundle = bundle;
  const profile = bundle.profile;

  if (!profile.consented) {
    ensureSectionState("#enter-card", true);
    [
      "#profile-card",
      "#action-card",
      "#exchange-card",
      "#inventory-card",
      "#technique-card",
      "#official-shop-card",
      "#market-card",
      "#auction-card",
      "#leaderboard-card",
      "#sect-card",
      "#task-card",
      "#craft-card",
      "#explore-card",
      "#red-envelope-card",
      "#journal-card",
      "#gift-card"
    ].forEach((selector) => ensureSectionState(selector, false));
    setStatus("你还没有踏入仙途，确认后会立即抽取灵根并创建修仙档案。", "warning");
    return;
  }

  ensureSectionState("#enter-card", false);
  ensureSectionState("#profile-card", true, true);
  ensureSectionState("#action-card", true, true);
  ensureSectionState("#exchange-card", true);
  ensureSectionState("#inventory-card", true);
  ensureSectionState("#technique-card", true);
  ensureSectionState("#official-shop-card", true);
  ensureSectionState("#market-card", true);
  ensureSectionState("#auction-card", true);
  ensureSectionState("#leaderboard-card", true);
  ensureSectionState("#sect-card", true);
  ensureSectionState("#task-card", true);
  ensureSectionState("#craft-card", true);
  ensureSectionState("#explore-card", true);
  ensureSectionState("#red-envelope-card", true);
  ensureSectionState("#journal-card", true);
  ensureSectionState("#gift-card", true);

  const progress = bundle.progress || {};
  const retreating = bundle.capabilities?.is_in_retreat;
  const equippedArtifacts = bundle.equipped_artifacts || [];
  const artifactNames = equippedArtifacts.length ? equippedArtifacts.map((item) => item.name).join("、") : "暂无";
  const equipLimit = bundle.settings?.artifact_equip_limit || bundle.capabilities?.artifact_equip_limit || 1;
  const talismanName = bundle.active_talisman?.name || "暂无";
  const retreatStatus = retreating ? `闭关中，预计结束 ${formatDate(profile.retreat_end_at)}` : "未在闭关";
  const sharedStone = bundle.capabilities?.shared_spiritual_stone_total ?? profile.spiritual_stone ?? 0;
  const combatPower = bundle.combat_power ?? 0;

  document.querySelector("#realm-badge").textContent = `${profile.realm_stage}${profile.realm_layer}层`;
  document.querySelector("#root-text").textContent = `灵根：${profileRootText(profile)} · 斗法修正 ${profile.root_bonus >= 0 ? "+" : ""}${profile.root_bonus}%`;
  document.querySelector("#profile-grid").innerHTML = `
    <article class="profile-item"><span>境界</span><strong>${escapeHtml(profile.realm_stage)}${escapeHtml(profile.realm_layer)}层</strong></article>
    <article class="profile-item"><span>当前修为</span><strong>${escapeHtml(progress.current ?? profile.cultivation)} / ${escapeHtml(progress.threshold ?? 0)}</strong></article>
    <article class="profile-item"><span>距离下层</span><strong>${escapeHtml(progress.remaining ?? 0)}</strong></article>
    <article class="profile-item"><span>灵石</span><strong>${escapeHtml(profile.spiritual_stone)}</strong></article>
    <article class="profile-item"><span>共享灵石</span><strong>${escapeHtml(sharedStone)}</strong></article>
    <article class="profile-item"><span>片刻碎片</span><strong>${escapeHtml(bundle.emby_balance)}</strong></article>
    <article class="profile-item"><span>综合战力</span><strong>${escapeHtml(combatPower)}</strong></article>
    <article class="profile-item"><span>丹毒</span><strong>${escapeHtml(profile.dan_poison)}/100</strong></article>
    <article class="profile-item"><span>已装备法宝</span><strong>${escapeHtml(artifactNames)}</strong></article>
    <article class="profile-item"><span>装备数量</span><strong>${escapeHtml(equippedArtifacts.length)} / ${escapeHtml(equipLimit)}</strong></article>
    <article class="profile-item"><span>生效符箓</span><strong>${escapeHtml(talismanName)}</strong></article>
    <article class="profile-item"><span>闭关状态</span><strong>${escapeHtml(retreatStatus)}</strong></article>
  `;

  const hints = [];
  if (retreating) {
    hints.push("闭关中，无法使用其他修仙功能");
  } else {
    if (!bundle.capabilities?.can_train) hints.push("今日吐纳次数已用完");
    if (!bundle.capabilities?.can_breakthrough) hints.push("当前尚未达到可突破条件");
  }
  document.querySelector("#action-hint").textContent = hints.join(" · ") || "当前状态良好，可以继续修炼、突破或闭关。";

  const exchangeEnabled = bundle.settings?.coin_stone_exchange_enabled ?? true;
  document.querySelector("#exchange-hint").textContent =
    exchangeEnabled
      ? exchangeHintText(bundle.settings || {})
      : "灵石互兑功能当前已关闭，可联系管理员在后台重新开启。";

  setDisabled(document.querySelector("#train-btn"), !bundle.capabilities?.can_train, "当前无法吐纳修炼");
  applyBreakthroughActionState(bundle, "当前无法尝试突破");
  setDisabled(document.querySelector("#retreat-start-btn"), !bundle.capabilities?.can_retreat, "当前无法开始闭关");
  setDisabled(document.querySelector("#retreat-finish-btn"), !retreating, "当前没有进行中的闭关");

  renderArtifactList(bundle.artifacts, retreating, equipLimit, equippedArtifacts.length);
  renderTalismanList(bundle.talismans, retreating);
  renderPillList(bundle.pills, retreating);
  renderMaterialInventoryList(bundle.materials || []);
  renderOfficialShop(bundle.official_shop, retreating);
  renderPersonalShop(bundle.personal_shop);
  renderCommunityShop(bundle.community_shop, retreating);
  renderInventorySelect();

  const shopDisabledReason = retreating ? "闭关期间无法经营店铺" : "";
  ["#shop-item-kind", "#shop-item-ref", "#shop-quantity", "#shop-price", "#shop-name", "#shop-broadcast"]
    .forEach((selector) => setDisabled(document.querySelector(selector), retreating, shopDisabledReason));
  setDisabled(document.querySelector("#personal-shop-form button[type='submit']"), retreating, shopDisabledReason);
}

function renderProfile(bundle) {
  state.profileBundle = bundle;
  const profile = bundle.profile || {};
  const consented = Boolean(profile.consented);

  ensureSectionState("#enter-card", !consented);
  [
    "#profile-card",
    "#action-card",
    "#exchange-card",
    "#inventory-card",
    "#technique-card",
    "#official-shop-card",
    "#official-recycle-card",
    "#market-card",
    "#auction-card",
    "#leaderboard-card",
    "#sect-card",
    "#task-card",
    "#craft-card",
    "#explore-card",
    "#red-envelope-card",
    "#journal-card",
    "#gift-card",
  ].forEach((selector) => ensureSectionState(selector, consented));

  if (!consented) {
    setStatus("你还没有踏入仙途，确认后就会抽取灵根并建立修仙档案。", "warning");
    return;
  }

  const progress = bundle.progress || {};
  const settings = bundle.settings || {};
  const retreating = Boolean(bundle.capabilities?.is_in_retreat);
  const equippedArtifacts = bundle.equipped_artifacts || [];
  const equipLimit = settings.artifact_equip_limit || bundle.capabilities?.artifact_equip_limit || 1;
  const artifactNames = equippedArtifacts.length ? equippedArtifacts.map((item) => item.name).join("、") : "暂无";
  const talismanName = bundle.active_talisman?.name || "暂无";
  const retreatStatus = retreating ? `闭关中，预计结束 ${formatDate(profile.retreat_end_at)}` : "未在闭关";
  const sharedStone = bundle.capabilities?.shared_spiritual_stone_total ?? profile.spiritual_stone ?? 0;
  const combatPower = bundle.combat_power ?? 0;
  const profileGrid = document.querySelector("#profile-grid");
  const rootText = document.querySelector("#root-text");
  const realmBadge = document.querySelector("#realm-badge");

  if (realmBadge) {
    realmBadge.textContent = `${profile.realm_stage || "炼气"}${profile.realm_layer || 0}层`;
  }
  if (rootText) {
    rootText.textContent = `灵根：${profileRootText(profile)} · 斗法修正 ${profile.root_bonus >= 0 ? "+" : ""}${profile.root_bonus || 0}%`;
  }
  if (profileGrid) {
    profileGrid.innerHTML = `
      <article class="profile-item"><span>境界</span><strong>${escapeHtml(profile.realm_stage || "炼气")}${escapeHtml(profile.realm_layer || 0)}层</strong></article>
      <article class="profile-item"><span>当前修为</span><strong>${escapeHtml(progress.current ?? profile.cultivation ?? 0)} / ${escapeHtml(progress.threshold ?? 0)}</strong></article>
      <article class="profile-item"><span>距离下一层</span><strong>${escapeHtml(progress.remaining ?? 0)}</strong></article>
      <article class="profile-item"><span>灵石</span><strong>${escapeHtml(profile.spiritual_stone ?? 0)}</strong></article>
      <article class="profile-item"><span>共享灵石</span><strong>${escapeHtml(sharedStone)}</strong></article>
      <article class="profile-item"><span>片刻碎片</span><strong>${escapeHtml(bundle.emby_balance ?? 0)}</strong></article>
      <article class="profile-item"><span>综合战力</span><strong>${escapeHtml(combatPower)}</strong></article>
      <article class="profile-item"><span>丹毒</span><strong>${escapeHtml(profile.dan_poison ?? 0)} / 100</strong></article>
      <article class="profile-item"><span>法宝</span><strong>${escapeHtml(artifactNames)}</strong></article>
      <article class="profile-item"><span>装备数量</span><strong>${escapeHtml(equippedArtifacts.length)} / ${escapeHtml(equipLimit)}</strong></article>
      <article class="profile-item"><span>生效符箓</span><strong>${escapeHtml(talismanName)}</strong></article>
      <article class="profile-item"><span>闭关状态</span><strong>${escapeHtml(retreatStatus)}</strong></article>
      <article class="profile-item"><span>宗门贡献</span><strong>${escapeHtml(profile.sect_contribution ?? 0)}</strong></article>
      <article class="profile-item"><span>魅力</span><strong>${escapeHtml(bundle.effective_stats?.charisma ?? profile.charisma ?? 0)}</strong></article>
      <article class="profile-item"><span>机缘</span><strong>${escapeHtml(bundle.effective_stats?.fortune ?? profile.fortune ?? 0)}</strong></article>
    `;
  }

  const hints = [];
  if (retreating) {
    hints.push("闭关期间无法使用大部分修仙功能。");
  } else {
    if (!bundle.capabilities?.can_train) hints.push("今日吐纳次数已经用完。");
    if (!bundle.capabilities?.can_breakthrough) hints.push("达到当前大境界九层满修为后才可突破。");
  }
  const actionHint = document.querySelector("#action-hint");
  if (actionHint) {
    actionHint.textContent = hints.join(" ") || "状态平稳，可以继续吐纳、突破、经营坊市或探索。";
  }

  const exchangeEnabled = settings.coin_stone_exchange_enabled ?? true;
  const exchangeHint = document.querySelector("#exchange-hint");
  if (exchangeHint) {
    exchangeHint.textContent = exchangeEnabled
      ? exchangeHintText(settings)
      : "灵石互兑功能当前已关闭，可联系管理员在后台重新开启。";
  }
  const officialShopTitle = document.querySelector("#official-shop-title");
  if (officialShopTitle) {
    officialShopTitle.textContent = officialShopName(bundle);
  }

  setDisabled(document.querySelector("#train-btn"), !bundle.capabilities?.can_train, "当前无法吐纳修炼");
  applyBreakthroughActionState(bundle, "当前无法尝试突破");
  setDisabled(document.querySelector("#retreat-start-btn"), !bundle.capabilities?.can_retreat, "当前无法开始闭关");
  setDisabled(document.querySelector("#retreat-finish-btn"), !retreating, "当前没有进行中的闭关");
  const exchangeDisabledReason = !exchangeEnabled
    ? "灵石互兑功能当前已关闭。"
    : (retreating ? "闭关期间无法兑换灵石和片刻碎片。" : "");
  ["#coin-to-stone-amount", "#stone-to-coin-amount"]
    .forEach((selector) => setDisabled(document.querySelector(selector), retreating || !exchangeEnabled, exchangeDisabledReason));
  setDisabled(document.querySelector("#coin-to-stone-form button[type='submit']"), retreating || !exchangeEnabled, exchangeDisabledReason);
  setDisabled(document.querySelector("#stone-to-coin-form button[type='submit']"), retreating || !exchangeEnabled, exchangeDisabledReason);

  const shopDisabledReason = retreating ? "闭关期间无法经营店铺。" : "";
  ["#shop-item-kind", "#shop-item-ref", "#shop-quantity", "#shop-price", "#shop-name", "#shop-broadcast"]
    .forEach((selector) => setDisabled(document.querySelector(selector), retreating, shopDisabledReason));
  setDisabled(document.querySelector("#personal-shop-form button[type='submit']"), retreating, shopDisabledReason);
}

function renderArtifactList(items, retreating, equipLimit, equippedCount) {
  const root = document.querySelector("#artifact-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>暂无法宝</strong><p>管理后台发放或在${escapeHtml(officialShopName())}购买后会出现在这里。</p></article>`;
    return;
  }

  for (const row of items) {
    const item = row.artifact;
    const effects = item.resolved_effects || {};
    const disabled = !item.usable || retreating;
    const fallback = retreating
      ? "闭关期间无法切换法宝"
      : item.equipped
        ? "当前法宝已装备"
        : equippedCount >= equipLimit
          ? `当前最多只能装备 ${equipLimit} 件法宝`
          : "当前条件不满足，暂时无法装备";
    const reason = retreating || !item.equipped ? fallbackReason(item.unusable_reason, fallback) : "";

    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "artifact")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(artifactEquipCategoryLabel(item))}</span>
        <span class="tag">${escapeHtml(item.equip_slot_label || item.equip_slot || "槽位未定")}</span>
        <span class="tag ${item.artifact_type === "support" ? "support" : ""}">${escapeHtml(item.artifact_type_label || artifactTypeLabel(item.artifact_type))}</span>
        ${item.unique_item ? `<span class="tag">唯一</span>` : ""}
        <span class="tag">攻击 ${escapeHtml(effects.attack_bonus ?? item.attack_bonus)}</span>
        <span class="tag">防御 ${escapeHtml(effects.defense_bonus ?? item.defense_bonus)}</span>
        <span class="tag">斗法 +${escapeHtml(effects.duel_rate_bonus ?? item.duel_rate_bonus)}%</span>
        <span class="tag">修炼 +${escapeHtml(effects.cultivation_bonus ?? item.cultivation_bonus)}</span>
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-equip-id="${item.id}" ${disabled ? "disabled" : ""}>${escapeHtml(item.action_label || (item.equipped ? "卸下法宝" : "装备法宝"))}</button>
    `;
    root.appendChild(card);
  }
}

function renderPillList(items, retreating) {
  const root = document.querySelector("#pill-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>暂无丹药</strong><p>${escapeHtml(officialShopName())}购买或主人发放后会出现在这里。</p></article>`;
    return;
  }

  for (const row of items) {
    const item = row.pill;
    const effects = item.resolved_effects || {};
    const disabled = !item.usable;
    const reason = item.usable ? "" : fallbackReason(item.unusable_reason, "当前条件不满足，暂时无法服用");

    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--pending">x${escapeHtml(row.quantity)}</span>
      </div>
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(item.pill_type_label)}</span>
        <span class="tag">${escapeHtml(item.effect_value_label || "效果值")} ${escapeHtml(effects.effect_value ?? item.effect_value)}</span>
        <span class="tag">丹毒 +${escapeHtml(effects.poison_delta ?? item.poison_delta)}</span>
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-pill-id="${item.id}" ${disabled ? "disabled" : ""}>服用丹药</button>
    `;
    root.appendChild(card);
  }
}

function renderTalismanList(items, retreating) {
  const root = document.querySelector("#talisman-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>暂无符箓</strong><p>符箓启用后会持续护持探索与垂钓；斗法、Boss、炼制、吐纳或闭关后仍会消耗，后台发放或商店购买后会出现在这里。</p></article>`;
    return;
  }

  for (const row of items) {
    const item = row.talisman;
    const effects = item.resolved_effects || {};
    const disabled = item.active || !item.usable || retreating;
    const reason = item.active
      ? "当前已生效"
      : fallbackReason(item.unusable_reason, retreating ? "闭关期间无法启用符箓" : "当前条件不满足，暂时无法启用");

    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--vip">x${escapeHtml(row.quantity)}</span>
      </div>
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(item.rarity)}</span>
        <span class="tag">攻击 ${escapeHtml(effects.attack_bonus ?? item.attack_bonus)}</span>
        <span class="tag">斗法 +${escapeHtml(effects.duel_rate_bonus ?? item.duel_rate_bonus)}%</span>
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-talisman-id="${item.id}" ${disabled ? "disabled" : ""}>${item.active ? "已生效" : "启用符箓"}</button>
    `;
    root.appendChild(card);
  }
}

function renderOfficialShop(items, retreating) {
  const root = document.querySelector("#official-shop-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>${escapeHtml(officialShopName())}暂无商品</strong><p>等主人上架后，这里会自动显示。</p></article>`;
    return;
  }

  const duelLockReason = currentDuelLockReason();
  const blockedReason = retreating ? "闭关期间无法交易。" : duelLockReason;
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "stack-item official-shop-item";
    card.innerHTML = `
      <div class="official-shop-item-top">
        <div class="official-shop-copy">
          <strong class="official-shop-name">${escapeHtml(item.item_name)}</strong>
          <p class="official-shop-meta">${escapeHtml(item.item_kind_label)} · ${escapeHtml(item.shop_name)}</p>
        </div>
        <div class="official-shop-price" aria-label="售价 ${escapeHtml(item.price_stone)} 灵石一件">
          <span class="official-shop-price-label">售价</span>
          <strong class="official-shop-price-value">${escapeHtml(item.price_stone)}</strong>
          <span class="official-shop-price-unit">灵石 / 件</span>
        </div>
      </div>
      <div class="item-tags official-shop-tags">
        <span class="tag official-shop-tag">官方供给</span>
        <span class="tag">库存 ${escapeHtml(item.quantity)}</span>
        <span class="tag">${escapeHtml(item.item_kind_label)}</span>
      </div>
      ${blockedReason ? `<p class="reason-text">${escapeHtml(blockedReason)}</p>` : ""}
      ${shopPurchaseControlsHtml(item, retreating || duelLockReason)}
    `;
    root.appendChild(card);
  }
}

function isPillShopItem(item) {
  return String(item?.item_kind || "").trim() === "pill";
}

function shopPurchaseControlsHtml(item, disabled) {
  if (!isPillShopItem(item)) {
    return `<button type="button" data-buy-id="${item.id}" ${disabled ? "disabled" : ""}>购买 1 件</button>`;
  }
  const maxQuantity = Math.max(Number(item?.quantity || 1), 1);
  const quantityLabel = `${item?.item_name || "丹药"}购买数量`;
  return `
    <div class="inline-actions">
      <input
        type="number"
        min="1"
        max="${escapeHtml(maxQuantity)}"
        step="1"
        inputmode="numeric"
        value="1"
        data-buy-quantity-for="${item.id}"
        aria-label="${escapeHtml(quantityLabel)}"
        ${disabled ? "disabled" : ""}
      >
      <button type="button" data-buy-id="${item.id}" ${disabled ? "disabled" : ""}>按数量购买</button>
    </div>
  `;
}

function renderOfficialRecyclePanel(bundle, retreating) {
  const root = document.querySelector("#official-recycle-list");
  const preview = document.querySelector("#official-recycle-preview");
  const hint = document.querySelector("#official-recycle-hint");
  if (!root) return;
  const quotes = officialRecycleItems(bundle);
  root.innerHTML = "";
  const duelLockReason = currentDuelLockReason(bundle);
  const blockedReason = duelLockReason;
  if (!quotes.length) {
    root.innerHTML = `<article class="stack-item"><strong>${escapeHtml(officialRecycleName(bundle))}暂无可归炉物品</strong><p>未绑定且可交易的法宝、符箓、丹药、材料，以及已掌握的功法和配方会显示在这里。</p></article>`;
    if (preview) preview.value = "暂无可归炉物品";
    if (hint) {
      hint.textContent = String(bundle?.official_recycle?.description || "万宝归炉会按物品品阶与属性自动折价。");
    }
    populateOfficialRecycleInventorySelect();
    updateOfficialRecycleQuotePreview(bundle);
    updateOfficialRecycleBatchPreview(bundle);
    return;
  }

  const visibleQuotes = officialRecycleVisibleQuotes(bundle);
  if (!visibleQuotes.length) {
    root.innerHTML = `<article class="stack-item"><strong>没有匹配的归炉报价</strong><p>可按物品名称、类型、品阶或报价说明搜索。</p></article>`;
    populateOfficialRecycleInventorySelect();
    updateOfficialRecycleQuotePreview(bundle);
    updateOfficialRecycleBatchPreview(bundle);
    return;
  }

  const groups = new Map();
  for (const quote of visibleQuotes) {
    const key = String(quote.item_kind || "unknown");
    if (!groups.has(key)) {
      groups.set(key, {
        label: quote.item_kind_label || quote.item_kind || "物品",
        items: [],
      });
    }
    groups.get(key).items.push(quote);
  }

  [...groups.entries()]
    .sort(([kindA, groupA], [kindB, groupB]) => {
      const rankDelta = officialRecycleKindRank(kindA) - officialRecycleKindRank(kindB);
      return rankDelta || String(groupA.label || "").localeCompare(String(groupB.label || ""), "zh-Hans-CN");
    })
    .forEach(([kind, group]) => {
      const section = document.createElement("details");
      section.className = "mini-fold recycle-quote-group";
      section.open = true;
      section.innerHTML = `
        <summary class="mini-fold-summary">
          <h3>${escapeHtml(group.label || kind)}</h3>
          <span class="summary-tip">${escapeHtml(group.items.length)} 项报价</span>
        </summary>
        <div class="mini-fold-body recycle-quote-group-body"></div>
      `;
      const body = section.querySelector(".recycle-quote-group-body");
      group.items.forEach((quote) => {
        const card = document.createElement("article");
        card.className = "stack-item";
        card.innerHTML = officialRecycleQuoteCardHtml(quote, blockedReason);
        body.appendChild(card);
      });
      root.appendChild(section);
    });

  if (hint) {
    hint.textContent = String(bundle?.official_recycle?.description || "万宝归炉会按物品品阶与属性自动折价。");
  }

  populateOfficialRecycleInventorySelect();
  updateOfficialRecycleQuotePreview(bundle);
  updateOfficialRecycleBatchPreview(bundle);
}

function renderPersonalShop(items) {
  const root = document.querySelector("#personal-shop-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>你的店铺暂时空空如也</strong><p>可以从背包里选择法宝、符箓、丹药或材料上架。</p></article>`;
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.item_name)}</strong>
        <span class="badge badge--normal">${escapeHtml(item.price_stone)} 灵石</span>
      </div>
      <p>${escapeHtml(item.item_kind_label)} · 库存 ${escapeHtml(item.quantity)} · ${escapeHtml(item.shop_name)}</p>
    `;
    root.appendChild(card);
  }
}

function renderCommunityShop(items, retreating) {
  const root = document.querySelector("#community-shop-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>群修市集暂无商品</strong><p>等有道友上架后，这里会热闹起来。</p></article>`;
    return;
  }

  const duelLockReason = currentDuelLockReason();
  const blockedReason = retreating ? "闭关期间无法交易。" : duelLockReason;
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.item_name)}</strong>
        <span class="badge badge--normal">${escapeHtml(item.price_stone)} 灵石</span>
      </div>
      <p>${escapeHtml(item.item_kind_label)} · 库存 ${escapeHtml(item.quantity)} · ${escapeHtml(item.shop_name)}</p>
      ${blockedReason ? `<p class="reason-text">${escapeHtml(blockedReason)}</p>` : ""}
      ${shopPurchaseControlsHtml(item, retreating || duelLockReason)}
    `;
    root.appendChild(card);
  }
}

function auctionStatusText(item) {
  return String(item?.status_label || item?.status || "未知状态");
}

function auctionBuyoutText(item) {
  const price = Number(item?.buyout_price_stone || 0);
  return price > 0 ? `${price} 灵石` : "未设置";
}

function auctionLeaderText(item) {
  return String(item?.highest_bidder_display_name || "").trim()
    || (item?.highest_bidder_tg ? `TG ${item.highest_bidder_tg}` : "暂无");
}

function renderPersonalAuctions(items = []) {
  const root = document.querySelector("#personal-auction-list");
  if (!root) return;
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>你还没有发起拍卖</strong><p>从背包中挑选可交易物品后，可以直接推送到群里开拍。</p></article>`;
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "stack-item";
    let extraText = `当前价 ${item.current_display_price_stone} 灵石 · 下次出价 ${item.next_bid_price_stone} 灵石`;
    if (item.status === "sold") {
      extraText = `成交 ${item.final_price_stone} 灵石 · 入账 ${item.seller_income_stone} 灵石 · 手续费 ${item.fee_amount_stone} 灵石`;
    } else if (item.status === "expired") {
      extraText = "无人出价，拍品已经退回背包。";
    } else if (item.status === "cancelled") {
      extraText = "拍卖已取消，拍品与竞价灵石均已退回。";
    }
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.item_name)} × ${escapeHtml(item.quantity)}</strong>
        <span class="badge badge--normal">${escapeHtml(auctionStatusText(item))}</span>
      </div>
      <p>${escapeHtml(item.item_kind_label || item.item_kind)} · 结束 ${escapeHtml(formatDate(item.end_at))}</p>
      <p>加价 ${escapeHtml(item.bid_increment_stone)} 灵石 · 一口价 ${escapeHtml(auctionBuyoutText(item))}</p>
      <p>领先者：${escapeHtml(auctionLeaderText(item))} · 出价 ${escapeHtml(item.bid_count || 0)} 次</p>
      <p>${escapeHtml(extraText)}</p>
      ${item.group_message_id ? `<p class="section-copy">群消息已推送${item.status === "active" ? "并置顶" : ""}，竞拍请在群里点击按钮完成。</p>` : ""}
    `;
    root.appendChild(card);
  });
}

function renderCommunityAuctions(items = []) {
  const root = document.querySelector("#community-auction-list");
  if (!root) return;
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>群内暂时没有进行中的拍卖</strong><p>等其他道友开拍后，这里会显示当前竞拍情况。</p></article>`;
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.item_name)} × ${escapeHtml(item.quantity)}</strong>
        <span class="badge badge--vip">${escapeHtml(item.current_display_price_stone)} 灵石</span>
      </div>
      <p>${escapeHtml(item.item_kind_label || item.item_kind)} · 卖家 ${escapeHtml(item.owner_display_name || `TG ${item.owner_tg || 0}`)}</p>
      <p>下次出价 ${escapeHtml(item.next_bid_price_stone)} 灵石 · 每次加价 ${escapeHtml(item.bid_increment_stone)} 灵石</p>
      <p>一口价 ${escapeHtml(auctionBuyoutText(item))} · 结束 ${escapeHtml(formatDate(item.end_at))}</p>
      <p>当前领先：${escapeHtml(auctionLeaderText(item))} · 出价 ${escapeHtml(item.bid_count || 0)} 次</p>
      <p class="section-copy">请前往群里的置顶拍卖消息点击按钮竞拍，群消息会随出价自动刷新。</p>
    `;
    root.appendChild(card);
  });
}

function taskRewardText(task) {
  const parts = [];
  const rewardStone = Number((task.reward_stone_preview ?? task.reward_stone) || 0);
  const rewardCultivation = Number((task.reward_cultivation_preview ?? task.reward_cultivation) || 0);
  if (rewardStone > 0) parts.push(`${rewardStone} 灵石`);
  if (rewardCultivation > 0) parts.push(`${rewardCultivation} 修为`);
  if (task.reward_item_kind && task.reward_item_quantity) {
    parts.push(`${task.reward_item_quantity} ${task.reward_item?.name || task.reward_item_kind_label || task.reward_item_kind}`);
  }
  const text = parts.join(" · ") || "无奖励";
  return task.reward_scale_mode === "realm" ? `${text}（按当前境界折算）` : text;
}

function taskMetricRequirementText(task) {
  if (task.task_type !== "metric") return "";
  const metricLabel = task.metric_label || task.requirement_metric_key || "计数指标";
  const metricTarget = Number((task.metric_target ?? task.requirement_metric_target) || 0);
  if (metricTarget <= 0) return "";
  return `${metricLabel} 达到 ${metricTarget} 次`;
}

function taskMetricProgressText(task) {
  if (task.task_type !== "metric") return "";
  const progress = Number(task.metric_progress_value || 0);
  const target = Number((task.metric_target ?? task.requirement_metric_target) || 0);
  if (target <= 0) return "";
  return `当前进度 ${progress}/${target}`;
}

function taskResultRewardText(reward, task = {}) {
  const parts = [];
  if (Number(reward?.reward_stone || 0) > 0) parts.push(`${Number(reward.reward_stone)} 灵石`);
  if (Number(reward?.reward_cultivation || 0) > 0) parts.push(`${Number(reward.reward_cultivation)} 修为`);
  if (reward?.reward_item) {
    if (reward.reward_item.duplicate_converted) {
      parts.push(`重复${reward.reward_item.item_kind_label || "物品"}折灵石 ${Number(reward.reward_item.stone_compensation || 0)}`);
      return parts.join(" · ");
    }
    const item = reward.reward_item.artifact
      || reward.reward_item.pill
      || reward.reward_item.talisman
      || reward.reward_item.material
      || reward.reward_item.technique
      || reward.reward_item.recipe
      || {};
    parts.push(`${Number(reward.reward_item.quantity || 1)} ${item.name || "物品"}`);
  }
  return parts.join(" · ") || taskRewardText(task);
}

function renderUserTaskMetricKeyOptions(bundle = state.profileBundle) {
  const select = document.querySelector("#task-metric-key");
  if (!select) return;
  const previousValue = select.value;
  const rows = Array.isArray(bundle?.achievement_metric_presets) ? bundle.achievement_metric_presets : [];
  select.innerHTML = "";
  if (!rows.length) {
    select.innerHTML = `<option value="">暂无可用指标</option>`;
    return;
  }
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "请选择计数指标";
  select.appendChild(placeholder);
  rows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.key;
    option.textContent = row.label || row.key;
    select.appendChild(option);
  });
  if (rows.some((row) => String(row.key) === String(previousValue))) {
    select.value = previousValue;
  }
}

function sectDonationRows(kind, bundle = state.profileBundle) {
  if (kind === "artifact") {
    return (bundle?.artifacts || [])
      .filter((row) => Number(row.consumable_quantity ?? row.tradeable_quantity ?? 0) > 0)
      .map((row) => ({ value: row.artifact.id, label: `${row.artifact.name} · 可提交 ${row.consumable_quantity ?? row.tradeable_quantity ?? row.quantity ?? 0}` }));
  }
  if (kind === "pill") {
    return (bundle?.pills || [])
      .filter((row) => Number(row.quantity || 0) > 0)
      .map((row) => ({ value: row.pill.id, label: `${row.pill.name} · 库存 ${row.quantity}` }));
  }
  if (kind === "talisman") {
    return (bundle?.talismans || [])
      .filter((row) => Number(row.consumable_quantity ?? row.tradeable_quantity ?? 0) > 0)
      .map((row) => ({ value: row.talisman.id, label: `${row.talisman.name} · 可提交 ${row.consumable_quantity ?? row.tradeable_quantity ?? row.quantity ?? 0}` }));
  }
  if (kind === "material") {
    return (bundle?.materials || [])
      .filter((row) => Number(row.quantity || 0) > 0)
      .map((row) => ({ value: row.material.id, label: `${row.material.name} · 库存 ${row.quantity}` }));
  }
  return [];
}

function renderSectDonationSelect(bundle = state.profileBundle) {
  const kind = document.querySelector("#sect-donate-kind")?.value || "material";
  const select = document.querySelector("#sect-donate-ref");
  if (!select) return;
  const previousValue = select.value;
  const rows = sectDonationRows(kind, bundle);
  select.innerHTML = "";
  if (!rows.length) {
    select.innerHTML = `<option value="">暂无可提交物品</option>`;
    select.disabled = true;
    return;
  }
  rows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.value;
    option.textContent = row.label;
    select.appendChild(option);
  });
  select.disabled = false;
  if (rows.some((row) => String(row.value) === String(previousValue))) {
    select.value = previousValue;
  }
}

function renderSectArea(bundle) {
  const currentRoot = document.querySelector("#sect-current");
  const listRoot = document.querySelector("#sect-list");
  const salaryButton = document.querySelector("#sect-salary-btn");
  if (!currentRoot || !listRoot || !salaryButton) return;

  const current = bundle.current_sect;
  currentRoot.innerHTML = "";
  if (current) {
    const role = current.current_role?.role_name || "门下弟子";
    currentRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(current.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(role)}</span>
        </div>
        <p>${escapeHtml(current.description || "暂无宗门简介")}</p>
      </article>
    `;
    salaryButton.disabled = false;
  } else {
    currentRoot.innerHTML = `<article class="stack-item"><strong>暂未加入宗门</strong><p>可在下方选择满足条件的宗门加入。</p></article>`;
    salaryButton.disabled = true;
  }

  listRoot.innerHTML = "";
  const sects = [...(bundle.sects || [])].sort((left, right) => {
    if (Boolean(left.joinable) !== Boolean(right.joinable)) return left.joinable ? -1 : 1;
    const realmCompare = compareRealmRequirement(left.min_realm_stage, left.min_realm_layer, right.min_realm_stage, right.min_realm_layer);
    if (realmCompare !== 0) return realmCompare;
    return String(left.name || "").localeCompare(String(right.name || ""), "zh-Hans-CN");
  });
  if (!sects.length) {
    listRoot.innerHTML = `<article class="stack-item"><strong>暂无可加入宗门</strong></article>`;
    return;
  }
  for (const sect of sects) {
    const card = document.createElement("article");
    card.className = "stack-item";
    const disabled = current?.id === sect.id || !sect.joinable;
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(sect.name)}</strong>
        <span class="badge badge--normal">${escapeHtml((sect.roles || []).length)} 个职位</span>
      </div>
      <p>${escapeHtml(sect.description || "暂无简介")}</p>
      <p>条件：${escapeHtml(sect.min_realm_stage || "无")} ${escapeHtml(sect.min_realm_layer || 1)} 层 / 灵石 ${escapeHtml(sect.min_stone || 0)}</p>
      <button type="button" data-sect-id="${sect.id}" ${disabled ? "disabled" : ""}>${current?.id === sect.id ? "已加入" : "加入宗门"}</button>
      ${disabled && sect.join_reason ? `<p class="muted compact-copy">${escapeHtml(sect.join_reason)}</p>` : ""}
    `;
    listRoot.appendChild(card);
  }
}

function renderTaskArea(bundle) {
  const root = document.querySelector("#task-list");
  if (!root) return;
  root.innerHTML = "";
  const uploadAllowed = Boolean(bundle.capabilities?.can_upload_images);
  const uploadReason = fallbackReason(bundle.capabilities?.upload_image_reason, "当前无法上传图片");
  const uploadButton = document.querySelector("#task-image-upload");
  const uploadInput = document.querySelector("#task-image-file");
  const uploadHelp = document.querySelector("#task-upload-help");
  setDisabled(uploadButton, !uploadAllowed, uploadReason);
  setDisabled(uploadInput, !uploadAllowed, uploadReason);
  if (uploadHelp) {
    uploadHelp.textContent = uploadAllowed
      ? "如需带图答题，可先上传图片再发布任务。"
      : uploadReason;
  }
  syncTaskPublishState(bundle);
  renderUserTaskMetricKeyOptions(bundle);
  renderTaskRequirementSelect();
  renderTaskRewardSelect();
  const tasks = bundle.tasks || [];
  if (!tasks.length) {
    root.innerHTML = `<article class="stack-item"><strong>暂无任务</strong><p>主人、宗门或玩家发布悬赏后会出现在这里。</p></article>`;
    return;
  }
  for (const task of tasks) {
    const claimStatus = task.claim?.status || "";
    const alreadyCompleted = Boolean(task.winner_tg) || claimStatus === "completed";
    const alreadyAccepted = Boolean(task.claimed) && !alreadyCompleted;
    const isMetric = task.task_type === "metric";
    const metricClaimable = Boolean(task.metric_claimable);
    const requiresItem = Boolean(task.required_item_kind && Number(task.required_item_quantity || 0) > 0);
    const claimBlockReason = String(task.claim_block_reason || "").trim();
    const disabled = Boolean(claimBlockReason)
      || alreadyCompleted
      || task.task_type === "quiz"
      || (alreadyAccepted && (!isMetric || !metricClaimable));
    const requiredItemName = task.required_item?.name || task.required_item_kind_label || task.required_item_kind || "物品";
    const actionLabel = alreadyCompleted
      ? "已完成"
      : alreadyAccepted
        ? (isMetric ? (metricClaimable ? "提交进度并领奖" : `进行中 ${task.metric_progress_value || 0}/${task.metric_target || task.requirement_metric_target || 0}`) : "已接取")
        : task.task_type === "quiz"
          ? "请到群内作答"
          : isMetric
            ? "接取计数任务"
          : requiresItem
            ? "提交物品并完成"
            : "接取任务";
    const canCancel = Boolean(task.can_cancel);
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(task.title)}</strong>
        <span class="badge badge--normal">${escapeHtml(task.task_scope_label || task.task_scope)}</span>
      </div>
      <p>${escapeHtml(task.description || "暂无描述")}</p>
      <p>类型：${escapeHtml(task.task_type_label || task.task_type)} · 奖励：${escapeHtml(taskRewardText(task))}</p>
      ${requiresItem ? `<p>提交需求：${escapeHtml(requiredItemName)} × ${escapeHtml(task.required_item_quantity)}</p>` : ""}
      ${isMetric ? `<p>任务要求：${escapeHtml(taskMetricRequirementText(task))} · ${escapeHtml(taskMetricProgressText(task))}</p>` : ""}
      ${task.question_text ? `<p>题目：${escapeHtml(task.question_text)}</p>` : ""}
      <div class="inline-actions">
        <button type="button" data-task-id="${task.id}" data-task-action="claim" ${disabled ? "disabled" : ""} ${claimBlockReason ? `title="${escapeHtml(claimBlockReason)}"` : ""}>${claimBlockReason ? "已暂停领取" : actionLabel}</button>
        ${canCancel ? `<button type="button" class="ghost" data-task-id="${task.id}" data-task-action="cancel">撤销任务</button>` : ""}
      </div>
    `;
    root.appendChild(card);
  }
}

function renderTechniqueArea(bundle) {
  const currentRoot = document.querySelector("#technique-current");
  const listRoot = document.querySelector("#technique-list");
  if (!currentRoot || !listRoot) return;

  const current = bundle.current_technique;
  currentRoot.innerHTML = current
    ? `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(current.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(current.technique_type_label || current.technique_type || "功法")}</span>
        </div>
        <p>${escapeHtml(current.description || "暂无描述")}</p>
        <div class="item-tags">
          ${qualityBadgeHtml(current.rarity || "凡品", current.quality_color, "tag")}
          ${itemAffixTags(current, current.resolved_effects || {})}
        </div>
      </article>
    `
    : `<article class="stack-item"><strong>当前未参悟功法</strong><p>可从下方功法目录中切换一门适合你的修行路线。</p></article>`;

  const techniques = bundle.techniques || [];
  listRoot.innerHTML = "";
  if (!techniques.length) {
    listRoot.innerHTML = `<article class="stack-item"><strong>暂无可用功法</strong></article>`;
    return;
  }
  techniques.forEach((item) => {
    const effects = item.resolved_effects || {};
    const disabled = item.active || !item.usable;
    const reason = disabledReason(
      disabled,
      item.active ? "当前已启用这门功法" : item.unusable_reason,
      "当前无法切换到这门功法"
    );
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">${escapeHtml(item.technique_type_label || item.technique_type || "功法")}</span>
      </div>
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color, "tag")}
        ${itemAffixTags(item, effects)}
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-technique-id="${item.id}" ${disabled ? "disabled" : ""}>${escapeHtml(item.action_label || (item.active ? "当前功法" : "切换功法"))}</button>
    `;
    listRoot.appendChild(card);
  });
}

function renderCraftArea(bundle) {
  const materialRoot = document.querySelector("#material-list");
  const recipeRoot = document.querySelector("#recipe-list");
  if (!materialRoot || !recipeRoot) return;

  const materials = bundle.materials || [];
  materialRoot.innerHTML = materials.length
    ? materials.map((row) => `<article class="stack-item"><strong>${escapeHtml(row.material.name)}</strong><p>品质 ${escapeHtml(row.material.quality_label || row.material.quality_level)} · 数量 ${escapeHtml(row.quantity)}</p><p class="muted">${escapeHtml(row.material.quality_feature || "")}</p></article>`).join("")
    : `<article class="stack-item"><strong>暂无炼制材料</strong><p>可通过探索、任务或主人发放获得。</p></article>`;

  const recipes = sortRecipesByResultQuality(bundle.recipes || []);
  recipeRoot.innerHTML = "";
  if (!recipes.length) {
    recipeRoot.innerHTML = `<article class="stack-item"><strong>暂无配方</strong></article>`;
    return;
  }
  for (const recipe of recipes) {
    const ingredients = (recipe.ingredients || []).map((item) => `${item.material?.name || "材料"}×${item.quantity}`).join("，");
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(recipe.name)}</strong>
        <span class="badge badge--normal">${escapeHtml(recipe.recipe_kind_label || recipe.recipe_kind)}</span>
      </div>
      <p>产出：${escapeHtml(recipe.result_item?.name || "成品")} × ${escapeHtml(recipe.result_quantity)}</p>
      <p>材料：${escapeHtml(ingredients || "未配置")}</p>
      <p>当前成功率：${escapeHtml(formatPercentText(recipe.current_success_rate, String(recipe.base_success_rate || 0)))}%</p>
      <button type="button" data-recipe-id="${recipe.id}">开始炼制</button>
    `;
    recipeRoot.appendChild(card);
  }
}

function compareRealmRequirement(leftStage, leftLayer, rightStage, rightLayer) {
  const leftIndex = REALM_ORDER.indexOf(leftStage || "");
  const rightIndex = REALM_ORDER.indexOf(rightStage || "");
  if (leftIndex !== rightIndex) return leftIndex - rightIndex;
  return Number(leftLayer || 1) - Number(rightLayer || 1);
}

function cleanSceneCopy(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .replace(/[，、]{2,}/g, "，")
    .replace(/[。！？]{2,}/g, "。")
    .trim()
    .replace(/^[，。！？；、,.!?;]+|[，。！？；、,.!?;]+$/g, "");
}

function sceneRiskBadgeClass(level) {
  if (level === "stable" || level === "light") return "badge--normal";
  if (level === "medium") return "badge--pending";
  return "badge--danger";
}

function sceneEventProbabilityMeta(scene = {}) {
  const events = Array.isArray(scene.event_pool) ? scene.event_pool.filter((event) => event && typeof event === "object") : [];
  const weights = { good: 0, bad: 0, neutral: 0, total: 0 };
  events.forEach((event) => {
    const weight = Math.max(Number(event.weight || 0), 1);
    const eventType = String(event.event_type || "").trim();
    const stoneLossMax = Math.max(Number(event.stone_loss_max || event.stone_loss_min || 0), 0);
    const stoneBonusMax = Math.max(Number(event.stone_bonus_max || event.stone_bonus_min || 0), 0);
    const hasBonusReward = Boolean(String(event.bonus_reward_kind || "").trim() && Number(event.bonus_reward_ref_id || 0) > 0);
    weights.total += weight;
    if (eventType === "danger" || stoneLossMax > 0) weights.bad += weight;
    else if (["fortune", "recipe", "oddity"].includes(eventType) || stoneBonusMax > 0 || hasBonusReward) weights.good += weight;
    else weights.neutral += weight;
  });
  const percent = (value) => weights.total > 0 ? Math.round(value / weights.total * 100) : 0;
  const goodPercent = Number(scene.requirement_state?.event_good_percent ?? percent(weights.good));
  const badPercent = Number(scene.requirement_state?.event_bad_percent ?? percent(weights.bad));
  const neutralPercent = Number(scene.requirement_state?.event_neutral_percent ?? Math.max(100 - goodPercent - badPercent, 0));
  return {
    goodPercent,
    badPercent,
    neutralPercent,
    summary: `好运 ${goodPercent}% · 不幸 ${badPercent}%${neutralPercent > 0 ? ` · 普通 ${neutralPercent}%` : ""}`,
  };
}

function sceneDisplayMeta(scene, currentStage, currentLayer, currentPower) {
  const state = scene.requirement_state || {};
  const eventProbability = sceneEventProbabilityMeta(scene);
  const minStage = scene.min_realm_stage || "";
  const minLayer = Number(scene.min_realm_layer || 1);
  const minPower = Number(scene.min_combat_power || 0);
  const currentStageIndex = REALM_ORDER.indexOf(currentStage || "");
  const minStageIndex = REALM_ORDER.indexOf(minStage || "");
  const realmQualified = !minStage || minStageIndex < 0 || currentStageIndex > minStageIndex || (currentStageIndex === minStageIndex && currentLayer >= minLayer);
  const powerQualified = minPower <= 0 || currentPower >= minPower;
  const warnings = [];
  if (Array.isArray(state.risk_reasons) && state.risk_reasons.length) {
    warnings.push(...state.risk_reasons.map((item) => cleanSceneCopy(item)).filter(Boolean));
  } else {
    if (minPower > 0 && !powerQualified) warnings.push("当前战力偏低，翻车概率会明显提高");
    if (minStage && !realmQualified) warnings.push("当前境界不足，翻车概率会明显提高");
  }
  if (state.item_loss_warning) warnings.push(cleanSceneCopy(state.item_loss_warning));
  const entryRiskLevel = String(state.entry_risk_level || state.risk_level || (realmQualified && powerQualified ? "stable" : "high"));
  const entryRiskLabel = String(state.entry_risk_label || state.risk_label || (realmQualified && powerQualified ? "稳妥" : "高危"));
  const entryRiskPercent = Number(state.entry_risk_percent ?? state.risk_percent ?? state.death_chance ?? 0);
  const eventRiskLevel = String(state.event_risk_level || (entryRiskPercent > 0 ? entryRiskLevel : "stable"));
  const eventRiskLabel = String(state.event_risk_label || (entryRiskPercent > 0 ? entryRiskLabel : "平稳"));
  const eventRiskPercent = Number(state.event_risk_percent || 0);
  const useEventBadge = eventRiskPercent > entryRiskPercent;
  const riskLevel = useEventBadge ? eventRiskLevel : entryRiskLevel;
  const riskLabel = useEventBadge ? eventRiskLabel : entryRiskLabel;
  const itemLossRisk = Number(state.item_loss_risk || 0);
  return {
    minStage,
    minLayer,
    minPower,
    realmQualified,
    powerQualified,
    qualified: realmQualified && powerQualified,
    warnings,
    riskLevel,
    riskLabel,
    riskPercent: Math.max(entryRiskPercent, eventRiskPercent),
    entryRiskPercent,
    eventRiskPercent,
    eventGoodPercent: eventProbability.goodPercent,
    eventBadPercent: eventProbability.badPercent,
    eventNeutralPercent: eventProbability.neutralPercent,
    eventProbabilityText: eventProbability.summary,
    itemLossRisk,
    requirementSummary: cleanSceneCopy(state.requirement_summary),
    realmStatusText: cleanSceneCopy(state.realm_status_text),
    powerStatusText: cleanSceneCopy(state.power_status_text),
    eventRiskNote: cleanSceneCopy(state.event_risk_note),
    safeNote: cleanSceneCopy(state.safe_note),
  };
}

function buildSceneSearchText(scene = {}) {
  return [
    scene.name,
    scene.description,
    (scene.drops || []).map((drop) => drop.reward_name || drop.reward_ref_id_name || drop.reward_kind_label || drop.reward_kind),
    (scene.event_pool || []).map((event) => [event.name, event.description, event.bonus_reward_name, event.bonus_reward_kind_label || event.bonus_reward_kind]),
  ];
}

function sceneDropName(drop = {}) {
  return String(
    drop.reward_name
    || drop.reward_ref_id_name
    || drop.reward_kind_label
    || drop.reward_kind
    || "未知掉落"
  ).trim() || "未知掉落";
}

function sceneDropQuantityText(drop = {}) {
  const quantityMin = Math.max(Number(drop.quantity_min || 1), 1);
  const quantityMax = Math.max(Number(drop.quantity_max || quantityMin), quantityMin);
  const unit = String(drop.reward_kind || "").trim() === "material" ? "份" : "件";
  return quantityMin === quantityMax ? `${quantityMin} ${unit}` : `${quantityMin}~${quantityMax} ${unit}`;
}

function summarizeSceneDrops(drops = []) {
  const grouped = new Map();
  (drops || []).forEach((drop) => {
    if (!drop || typeof drop !== "object") return;
    const rewardKind = String(drop.reward_kind || "").trim();
    const rewardRefId = Number(drop.reward_ref_id || 0);
    const name = sceneDropName(drop);
    const key = `${rewardKind}:${rewardRefId || name}`;
    const quantityMin = Math.max(Number(drop.quantity_min || 1), 1);
    const quantityMax = Math.max(Number(drop.quantity_max || quantityMin), quantityMin);
    const existing = grouped.get(key);
    if (existing) {
      existing.quantity_min = Math.min(existing.quantity_min, quantityMin);
      existing.quantity_max = Math.max(existing.quantity_max, quantityMax);
      return;
    }
    grouped.set(key, {
      reward_kind: rewardKind,
      reward_kind_label: String(drop.reward_kind_label || rewardKind || "掉落"),
      reward_ref_id: rewardRefId,
      reward_name: name,
      quantity_min: quantityMin,
      quantity_max: quantityMax,
    });
  });
  return [...grouped.values()];
}

function materialSourceScenes(materialName, bundle = state.profileBundle) {
  const targetName = String(materialName || "").trim();
  if (!targetName) return [];
  const seen = new Set();
  return (bundle?.scenes || []).filter((scene) => {
    const sceneId = Number(scene?.id || 0);
    if (sceneId > 0 && seen.has(sceneId)) return false;
    const matched = (scene?.drops || []).some((drop) => (
      String(drop?.reward_kind || "").trim() === "material"
      && sceneDropName(drop) === targetName
    ));
    if (matched && sceneId > 0) seen.add(sceneId);
    return matched;
  });
}

function materialSourceSceneNames(materialName, bundle = state.profileBundle) {
  return materialSourceScenes(materialName, bundle)
    .map((scene) => String(scene?.name || "").trim())
    .filter(Boolean);
}

function materialSceneJumpButtonHtml(materialName, bundle = state.profileBundle) {
  const targetName = String(materialName || "").trim();
  const sceneNames = materialSourceSceneNames(targetName, bundle);
  const disabled = !targetName || !sceneNames.length;
  const label = disabled
    ? "暂无地图"
    : sceneNames.length > 1
      ? `去地图 ×${sceneNames.length}`
      : "去地图";
  const title = disabled
    ? "当前未找到该材料对应的探索地图"
    : `前往 ${sceneNames.join("、")}`;
  return `<button type="button" class="ghost mini material-jump-button" data-material-scene-query="${escapeHtml(targetName)}" title="${escapeHtml(title)}" ${disabled ? "disabled" : ""}>${escapeHtml(label)}</button>`;
}

function jumpToMaterialSourceScenes(materialName) {
  const targetName = String(materialName || "").trim();
  if (!targetName) return;
  const searchInput = document.querySelector("#scene-search");
  if (searchInput) {
    searchInput.value = targetName;
  }
  document.querySelectorAll("#explore-card .mini-fold").forEach((fold) => {
    fold.open = true;
  });
  renderExploreArea(state.profileBundle);
  jumpToFoldCard("explore-card");
  setStatus(`已定位 ${targetName} 的获取地图。`, "info");
}

function renderExploreArea(bundle) {
  const sceneRoot = document.querySelector("#scene-list");
  const activeRoot = document.querySelector("#exploration-active");
  if (!sceneRoot || !activeRoot) return;
  const currentStage = bundle.profile?.realm_stage || "炼气";
  const currentLayer = Number(bundle.profile?.realm_layer || 1);
  const currentPower = Number(bundle.combat_power || 0);
  const sceneQuery = inventorySearchValue("#scene-search");

  const active = bundle.active_exploration;
  activeRoot.innerHTML = "";
  if (active && !active.claimed) {
    const endAt = parseShanghaiDate(active.end_at);
    const canClaim = endAt ? endAt.getTime() <= Date.now() : false;
    const claimReason = canClaim ? "" : "探索尚未结束，暂时不能领取奖励。";
    activeRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>探索进行中</strong>
          <span class="badge badge--normal">${escapeHtml(active.reward_kind_label || active.reward_kind || "奖励")}</span>
        </div>
        <p>${escapeHtml(cleanSceneCopy(active.event_text) || "未知遭遇")}</p>
        <p>结束时间：${escapeHtml(formatDate(active.end_at))}</p>
        ${claimReason ? `<p class="reason-text">${escapeHtml(claimReason)}</p>` : ""}
        <button type="button" data-explore-claim="${active.id}" ${canClaim ? "" : "disabled"}>${canClaim ? "领取奖励" : "尚未结束"}</button>
      </article>
    `;
  } else {
    activeRoot.innerHTML = `<article class="stack-item"><strong>当前没有待领取探索</strong></article>`;
  }

  const buildDurationOptions = (maxMinutesRaw) => {
    const maxMinutes = Math.max(Number(maxMinutesRaw) || 1, 1);
    const candidates = maxMinutes <= 10
      ? [maxMinutes]
      : maxMinutes <= 20
        ? [10, maxMinutes]
        : maxMinutes <= 30
          ? [10, 20, maxMinutes]
          : [10, 20, 30, Math.min(45, maxMinutes), maxMinutes];
    return [...new Set(candidates.filter((value) => value > 0 && value <= maxMinutes))]
      .sort((left, right) => left - right)
      .map((value) => `<option value="${value}">${value} 分钟</option>`)
      .join("");
  };

  sceneRoot.innerHTML = "";
  const sourceScenes = bundle.scenes || [];
  const scenes = sourceScenes
    .filter((scene) => textQueryMatches(sceneQuery, buildSceneSearchText(scene)))
    .map((scene) => ({ scene, meta: sceneDisplayMeta(scene, currentStage, currentLayer, currentPower) }))
    .sort((left, right) => {
      if (left.meta.qualified !== right.meta.qualified) return left.meta.qualified ? -1 : 1;
      if (left.meta.powerQualified !== right.meta.powerQualified) return left.meta.powerQualified ? -1 : 1;
      if (left.meta.minPower !== right.meta.minPower) return left.meta.minPower - right.meta.minPower;
      const realmCompare = compareRealmRequirement(left.meta.minStage, left.meta.minLayer, right.meta.minStage, right.meta.minLayer);
      if (realmCompare !== 0) return realmCompare;
      return String(left.scene.name || "").localeCompare(String(right.scene.name || ""), "zh-Hans-CN");
    });
  if (!scenes.length) {
    sceneRoot.innerHTML = sourceScenes.length
      ? `<article class="stack-item"><strong>未找到匹配秘境</strong><p>可按秘境名、掉落、功法或材料关键词继续搜索。</p></article>`
      : `<article class="stack-item"><strong>暂无探索场景</strong></article>`;
    return;
  }
  for (const { scene, meta } of scenes) {
    const explorationCount = Number(scene.user_exploration_count || 0);
    const entryDisabled = !meta.qualified;
    const entryLabel = !meta.realmQualified && !meta.powerQualified
      ? "条件不足"
      : !meta.realmQualified
        ? "境界不足"
        : !meta.powerQualified
          ? "战力不足"
          : meta.riskLevel === "high" || meta.riskLevel === "extreme"
            ? "冒险进入"
            : "开始探索";
    const summarizedDrops = summarizeSceneDrops(scene.drops || []);
    const materialDrops = summarizedDrops.filter((drop) => drop.reward_kind === "material");
    const otherDrops = summarizedDrops.filter((drop) => drop.reward_kind !== "material");
    const materialCards = materialDrops.map((drop) => `
      <article class="scene-material-item">
        <div class="scene-material-head">
          <strong>${escapeHtml(drop.reward_name || "未知材料")}</strong>
          <span class="badge badge--normal">${escapeHtml(sceneDropQuantityText(drop))}</span>
        </div>
        <div class="item-tags">
          <span class="tag">材料</span>
          <span class="tag">秘境掉落</span>
        </div>
      </article>
    `).join("");
    const otherRewardCards = otherDrops.map((drop) => `
      <article class="scene-drop-item">
        <div class="scene-drop-head">
          <strong>${escapeHtml(drop.reward_name || "未知掉落")}</strong>
          <span class="badge badge--normal">${escapeHtml(sceneDropQuantityText(drop))}</span>
        </div>
        <p>${escapeHtml(drop.reward_kind_label || "其他掉落")}</p>
      </article>
    `).join("");
    const rewardSections = [
      materialDrops.length
        ? `
          <section class="scene-section">
            <div class="scene-section-head">
              <h4>可获取材料</h4>
              <span class="summary-tip">共 ${escapeHtml(materialDrops.length)} 种</span>
            </div>
            <div class="scene-material-list">${materialCards}</div>
          </section>
        `
        : "",
      otherDrops.length
        ? `
          <section class="scene-section">
            <div class="scene-section-head">
              <h4>其他掉落</h4>
              <span class="summary-tip">功法、配方或特殊奖励</span>
            </div>
            <div class="scene-drop-list">${otherRewardCards}</div>
          </section>
        `
        : "",
    ].filter(Boolean).join("");
    const warningText = meta.warnings.join(" · ");
    const safeText = meta.safeNote || "当前实力已基本覆盖此处风险，可优先刷取所需材料与功法。";
    const riskText = [
      `门槛压力 ${meta.entryRiskPercent}%`,
      meta.eventProbabilityText,
      meta.itemLossRisk > 0 ? `掉宝 ${meta.itemLossRisk}%` : "",
    ].filter(Boolean).join(" · ");
    const card = document.createElement("article");
    card.className = `stack-item scene-card ${meta.qualified ? "is-qualified" : "is-risky"}`;
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(scene.name)}</strong>
        <span class="badge ${sceneRiskBadgeClass(meta.riskLevel)}">${escapeHtml(meta.riskLabel)}</span>
      </div>
      ${itemArtworkHtml(scene, "scene", "scene-art")}
      <p>${escapeHtml(cleanSceneCopy(scene.description) || "暂无场景描述")}</p>
      <div class="info-grid">
        <article class="info-chip">
          <span>战力门槛</span>
          <strong>${escapeHtml(meta.minPower > 0 ? `${meta.minPower}` : "无限制")}</strong>
        </article>
        <article class="info-chip">
          <span>当前战力</span>
          <strong>${escapeHtml(currentPower)}</strong>
        </article>
        <article class="info-chip">
          <span>境界门槛</span>
          <strong>${escapeHtml(meta.minStage ? `${meta.minStage}${meta.minLayer}层` : "无限制")}</strong>
        </article>
        <article class="info-chip">
          <span>历练记录</span>
          <strong>已探索 ${escapeHtml(explorationCount)} 次</strong>
        </article>
        <article class="info-chip">
          <span>风险评估</span>
          <strong>${escapeHtml(riskText)}</strong>
        </article>
      </div>
      ${meta.requirementSummary ? `<p class="muted">${escapeHtml(`进入要求：${meta.requirementSummary}`)}</p>` : ""}
      ${meta.realmStatusText ? `<p class="muted">${escapeHtml(meta.realmStatusText)}</p>` : ""}
      ${meta.powerStatusText ? `<p class="muted">${escapeHtml(meta.powerStatusText)}</p>` : ""}
      ${meta.eventRiskNote ? `<p class="muted">${escapeHtml(meta.eventRiskNote)}</p>` : ""}
      ${warningText ? `<p class="reason-text">${escapeHtml(warningText)}</p>` : `<p>${escapeHtml(safeText)}</p>`}
      ${rewardSections || `<div class="scene-drop-list"><article class="scene-drop-item"><div class="scene-drop-head"><strong>掉落待补充</strong></div><p>当前秘境尚未配置可展示的奖励。</p></article></div>`}
      <label>探索时长
        <select data-scene-minutes="${scene.id}" ${entryDisabled ? "disabled" : ""}>
          ${buildDurationOptions(scene.max_minutes)}
        </select>
      </label>
      <button type="button" data-scene-id="${scene.id}" ${entryDisabled ? "disabled" : ""}>${escapeHtml(entryLabel)}</button>
    `;
    sceneRoot.appendChild(card);
  }
}

function renderLeaderboard(result) {
  state.leaderboard = {
    kind: result.kind,
    page: result.page,
    totalPages: result.total_pages,
    loaded: true
  };

  document.querySelectorAll(".rank-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.kind === result.kind);
  });

  const list = document.querySelector("#leaderboard-list");
  list.innerHTML = "";
  if (!result.items.length) {
    list.innerHTML = `<article class="stack-item"><strong>暂无排行榜数据</strong><p>等更多道友入道后，这里会热闹起来。</p></article>`;
    return;
  }

  for (const item of result.items) {
    const desc = result.kind === "stone"
      ? `${item.spiritual_stone} 灵石`
      : result.kind === "realm"
        ? `${item.realm_stage}${item.realm_layer}层`
        : (item.artifact_name || "暂无法宝");

    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${item.rank}. ${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">${escapeHtml(desc)}</span>
      </div>
      <p>TG ${escapeHtml(item.tg)}</p>
    `;
    list.appendChild(card);
  }

  document.querySelector("#rank-page").textContent = `第 ${result.page} 页 / 共 ${result.total_pages} 页`;
  document.querySelector("#rank-prev").disabled = result.page <= 1;
  document.querySelector("#rank-next").disabled = result.page >= result.total_pages;
}

function renderArtifactList(items, retreating, equipLimit, equippedCount) {
  const root = document.querySelector("#artifact-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>暂无法宝</strong><p>去${escapeHtml(officialShopName())}挑几件趁手的宝贝，再来装配吧。</p></article>`;
    return;
  }

  for (const row of items) {
    const item = row.artifact;
    const effects = item.resolved_effects || {};
    const limitReached = !item.equipped && equippedCount >= equipLimit;
    const disabled = retreating || (!item.equipped && (!item.usable || limitReached));
    let reason = "";
    if (disabled) {
      if (retreating) {
        reason = "闭关期间不能切换法宝。";
      } else if (limitReached) {
        reason = `当前最多只能装备 ${equipLimit} 件法宝。`;
      } else {
        reason = item.unusable_reason || "当前条件不满足，暂时无法装备。";
      }
    }

    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "artifact")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(artifactEquipCategoryLabel(item))}</span>
        <span class="tag">${escapeHtml(item.equip_slot_label || item.equip_slot || "槽位未定")}</span>
        <span class="tag ${item.artifact_type === "support" ? "support" : ""}">${escapeHtml(item.artifact_type_label || artifactTypeLabel(item.artifact_type))}</span>
        <span class="tag">攻击 ${escapeHtml(effects.attack_bonus ?? item.attack_bonus)}</span>
        <span class="tag">防御 ${escapeHtml(effects.defense_bonus ?? item.defense_bonus)}</span>
        <span class="tag">斗法 +${escapeHtml(effects.duel_rate_bonus ?? item.duel_rate_bonus)}%</span>
        <span class="tag">修炼 +${escapeHtml(effects.cultivation_bonus ?? item.cultivation_bonus)}</span>
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-equip-id="${item.id}" ${disabled ? "disabled" : ""}>${escapeHtml(item.action_label || (item.equipped ? "卸下法宝" : "装备法宝"))}</button>
    `;
    root.appendChild(card);
  }
}

function renderPersonalShop(items) {
  const root = document.querySelector("#personal-shop-list");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `<article class="stack-item"><strong>游仙小铺暂时空空如也</strong><p>从背包里挑一件物品上架后，这里就会热闹起来。</p></article>`;
    return;
  }

  const duelLockReason = currentDuelLockReason();
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.item_name)}</strong>
        <span class="badge badge--normal">${escapeHtml(item.price_stone)} 灵石</span>
      </div>
      <p>${escapeHtml(item.item_kind_label)} · 库存 ${escapeHtml(item.quantity)} · 游仙小铺</p>
      <div class="inline-action-buttons">
        <button type="button" data-cancel-id="${item.id}" class="ghost" ${duelLockReason ? "disabled" : ""}>取消上架</button>
      </div>
    `;
    root.appendChild(card);
  }
}

function renderSectArea(bundle) {
  const currentRoot = document.querySelector("#sect-current");
  const listRoot = document.querySelector("#sect-list");
  const salaryButton = document.querySelector("#sect-salary-btn");
  const leaveButton = document.querySelector("#sect-leave-btn");
  if (!currentRoot || !listRoot || !salaryButton || !leaveButton) return;

  const current = bundle.current_sect;
  currentRoot.innerHTML = "";
  if (current) {
    const role = current.current_role?.role_name || "门下弟子";
    const contribution = bundle.profile?.sect_contribution ?? 0;
    currentRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(current.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(role)}</span>
        </div>
        <p>${escapeHtml(current.description || "暂无宗门简介")}</p>
        <div class="item-tags">
          <span class="tag">成员 ${escapeHtml((current.roster || []).length)}</span>
          <span class="tag">贡献 ${escapeHtml(contribution)}</span>
          <span class="tag">月俸 ${escapeHtml(current.current_role?.monthly_salary ?? 0)} 灵石</span>
        </div>
      </article>
    `;
    salaryButton.disabled = false;
    leaveButton.disabled = false;
  } else {
    currentRoot.innerHTML = `<article class="stack-item"><strong>暂未加入宗门</strong><p>满足条件后，就可以在下方挑选心仪宗门了。</p></article>`;
    salaryButton.disabled = true;
    leaveButton.disabled = true;
  }

  listRoot.innerHTML = "";
  const sects = bundle.sects || [];
  if (!sects.length) {
    listRoot.innerHTML = `<article class="stack-item"><strong>暂无可加入宗门</strong></article>`;
    return;
  }

  for (const sect of sects) {
    const disabled = current?.id === sect.id || !sect.joinable;
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(sect.name)}</strong>
        <span class="badge badge--normal">${escapeHtml((sect.roles || []).length)} 个职位</span>
      </div>
      <p>${escapeHtml(sect.description || "暂无简介")}</p>
      <div class="item-tags">
        <span class="tag">境界 ${escapeHtml(sect.min_realm_stage || "无")}${escapeHtml(sect.min_realm_layer || 1)}层</span>
        <span class="tag">灵石 ${escapeHtml(sect.min_stone || 0)}</span>
      </div>
      ${disabled && sect.join_reason ? `<p class="reason-text">${escapeHtml(sect.join_reason)}</p>` : ""}
      <button type="button" data-sect-id="${sect.id}" ${disabled ? "disabled" : ""}>${current?.id === sect.id ? "已加入" : "加入宗门"}</button>
    `;
    listRoot.appendChild(card);
  }
}

function renderRedEnvelopeClaims(claims = []) {
  const root = document.querySelector("#red-envelope-claim-list");
  if (!root) return;
  if (!claims.length) {
    root.innerHTML = `<article class="stack-item"><strong>最近没有新的领取记录</strong><p>发红包或领取红包后，记录会更新在这里。</p></article>`;
    return;
  }
  root.innerHTML = claims.slice(-8).reverse().map((row) => `
    <article class="stack-item">
      <strong>${escapeHtml(row.name || `TG ${row.tg}`)}</strong>
      <p>领取了 ${escapeHtml(row.amount)} 灵石 · ${escapeHtml(formatDate(row.created_at))}</p>
    </article>
  `).join("");
}

function renderJournalArea(bundle) {
  const root = document.querySelector("#journal-list");
  if (!root) return;
  const rows = (bundle.journal || []).filter((row) => row.title !== "主人修改");
  if (!rows.length) {
    root.innerHTML = `<article class="stack-item"><strong>最近 24 小时还没有新记录</strong><p>修炼、交易、任务、红包和宗门往来都会记在这里。</p></article>`;
    return;
  }
  root.innerHTML = rows.map((row) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(row.title)}</strong>
        <span class="badge badge--normal">${escapeHtml(formatDate(row.created_at))}</span>
      </div>
      <p>${escapeHtml(row.detail || row.action_type || "暂无详情")}</p>
    </article>
  `).join("");
}

function renderLeaderboard(result) {
  state.leaderboard = {
    kind: result.kind,
    page: result.page,
    totalPages: result.total_pages,
    loaded: true
  };

  document.querySelectorAll(".rank-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.kind === result.kind);
  });

  const list = document.querySelector("#leaderboard-list");
  list.innerHTML = "";
  if (!result.items.length) {
    list.innerHTML = `<article class="stack-item"><strong>暂无排行榜数据</strong><p>等更多道友踏入仙途后，这里自然会热闹起来。</p></article>`;
    return;
  }

  for (const item of result.items) {
    const desc = result.kind === "stone"
      ? `${item.spiritual_stone} 灵石`
      : result.kind === "realm"
        ? `${item.realm_stage}${item.realm_layer}层`
        : (item.artifact_name || "暂无已装备法宝");

    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${item.rank}. ${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">${escapeHtml(desc)}</span>
      </div>
    `;
    list.appendChild(card);
  }

  document.querySelector("#rank-page").textContent = `第 ${result.page} 页 / 共 ${result.total_pages} 页`;
  document.querySelector("#rank-prev").disabled = result.page <= 1;
  document.querySelector("#rank-next").disabled = result.page >= result.total_pages;
}

function applyProfileBundle(bundle, { deferSecondary = true } = {}) {
  if (!bundle) return;
  state.profileBundle = bundle;
  sanitizeOfficialRecycleSelections(bundle);
  state.pendingBundleCandidate = null;
  const renderToken = (state.bundleRenderToken || 0) + 1;
  state.bundleRenderToken = renderToken;
  renderWikiArea();
  renderProfile(bundle);
  syncRetreatTimingTicker(bundle);
  syncGiftPanelState(bundle);
  renderRedEnvelopeClaims(state.lastRedEnvelopeClaims || []);
  syncAdminEntry(bundle);

  const renderSecondary = () => {
    if (state.bundleRenderToken !== renderToken || state.profileBundle !== bundle) {
      return;
    }
    renderOpenLazyFoldCards();
  };

  if (deferSecondary) {
    deferUiWork(renderSecondary);
  } else {
    renderSecondary();
  }

  state.shopNameEditing = false;
  applyShopNameState(bundle?.profile?.shop_name || "游仙小铺");

  const settings = bundle?.settings || {};
  const exchangeEnabled = settings.coin_stone_exchange_enabled ?? true;
  const exchangeHint = document.querySelector("#exchange-hint");
  if (exchangeHint) {
    exchangeHint.textContent = exchangeEnabled
      ? exchangeHintText(settings)
      : "灵石互兑功能当前已关闭，可联系管理员在后台重新开启。";
  }

  ensureSectionState("#journal-card", Boolean(bundle?.profile?.consented));
  ensureSectionState("#technique-card", Boolean(bundle?.profile?.consented));
  ensureSectionState("#auction-card", Boolean(bundle?.profile?.consented));
  ensureSectionState("#gift-card", Boolean(bundle?.profile?.consented));
}

function exchangeHintText(settings = {}) {
  const rate = settings.rate ?? settings.coin_exchange_rate ?? 100;
  return `当前比例：1 片刻碎片 = ${rate} 灵石；${rate} 灵石 = 1 片刻碎片。兑换不收手续费，灵石兑换碎片按整份结算，不足 ${rate} 灵石的零头会保留。`;
}

function mergeBundleData(baseBundle, patchBundle) {
  const merged = { ...(baseBundle || {}) };
  for (const [key, value] of Object.entries(patchBundle || {})) {
    if (value && typeof value === "object" && !Array.isArray(value) && merged[key] && typeof merged[key] === "object" && !Array.isArray(merged[key])) {
      merged[key] = { ...merged[key], ...value };
      continue;
    }
    merged[key] = value;
  }
  return merged;
}

function clearDeferredSectionState() {
  state.deferredSectionsLoaded?.clear?.();
  state.deferredSectionPromises?.clear?.();
}

async function loadDeferredSection(section, { silent = false } = {}) {
  const normalized = String(section || "").trim();
  if (!normalized) return state.profileBundle;
  if (state.deferredBundleLoaded || state.deferredSectionsLoaded.has(normalized)) {
    return state.profileBundle;
  }
  if (state.deferredSectionPromises.has(normalized)) {
    return state.deferredSectionPromises.get(normalized);
  }
  const request = state.deferredSectionQueue.catch(() => null).then(async () => {
    if (state.deferredBundleLoaded || state.deferredSectionsLoaded.has(normalized)) {
      return state.profileBundle;
    }
    const deferred = await postJson(
      `/plugins/xiuxian/api/bootstrap/section/${encodeURIComponent(normalized)}`,
      {},
      { timeoutMs: DEFERRED_SECTION_REQUEST_TIMEOUT_MS },
    );
    state.profileBundle = mergeBundleData(state.profileBundle, deferred);
    state.deferredSectionsLoaded.add(normalized);
    applyProfileBundle(state.profileBundle);
    return state.profileBundle;
  })
    .catch((error) => {
      if (!silent) throw error;
      return state.profileBundle;
    })
    .finally(() => {
      state.deferredSectionPromises.delete(normalized);
    });
  state.deferredSectionQueue = request.catch(() => null);
  state.deferredSectionPromises.set(normalized, request);
  return request;
}

async function loadDeferredBundle({ silent = false } = {}) {
  if (state.deferredBundleLoaded) return state.profileBundle;
  if (state.deferredBundlePromise) return state.deferredBundlePromise;
  if (state.deferredBootstrapTimer) {
    window.clearTimeout(state.deferredBootstrapTimer);
    state.deferredBootstrapTimer = null;
  }
  state.deferredBundleLoading = true;
  state.deferredBundlePromise = (async () => {
    const deferred = await postJson("/plugins/xiuxian/api/bootstrap/deferred", {}, { timeoutMs: DEFERRED_SECTION_REQUEST_TIMEOUT_MS });
    state.profileBundle = mergeBundleData(state.profileBundle, deferred);
    state.deferredBundleLoaded = true;
    clearDeferredSectionState();
    applyProfileBundle(state.profileBundle);
    return state.profileBundle;
  })()
    .catch((error) => {
      if (!silent) throw error;
      return state.profileBundle;
    })
    .finally(() => {
      state.deferredBundleLoading = false;
      state.deferredBundlePromise = null;
    });
  return state.deferredBundlePromise;
}

function scheduleDeferredBootstrapWork() {
  const prefetchSections = ["inventory", "explore", "official_shop", "sect", "task"];
  const runner = () => {
    prefetchSections.forEach((section) => {
      loadDeferredSection(section, { silent: true }).catch(() => null);
    });
  };
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(runner, { timeout: 2500 });
  } else {
    window.setTimeout(runner, 600);
  }
}

function warmDeferredBundleForInteraction() {
  scheduleDeferredBootstrapWork();
}

async function refreshBundle({ background = false } = {}) {
  const pendingBundle = takePendingBundleCandidate();
  if (pendingBundle) {
    state.deferredBundleLoaded = true;
    clearDeferredSectionState();
    applyProfileBundle(pendingBundle);
    return pendingBundle;
  }
  if (state.bundleRefreshPromise) {
    return state.bundleRefreshPromise;
  }
  const runner = async () => {
    if (!state.profileBundle) {
      state.deferredBundleLoaded = false;
      state.deferredBundlePromise = null;
      clearDeferredSectionState();
      const payload = await postJson("/plugins/xiuxian/api/bootstrap", {}, { timeoutMs: 20000 });
      applyBootstrapPayload(payload);
      return state.profileBundle;
    }
    state.deferredBundleLoaded = false;
    state.deferredBundlePromise = null;
    clearDeferredSectionState();
    const payload = await postJson("/plugins/xiuxian/api/bootstrap", {}, { timeoutMs: 20000 });
    storeBootstrapCache(payload);
    renderBottomNav(payload.bottom_nav || []);
    applyProfileBundle(mergeBundleData(state.profileBundle, payload.profile_bundle));
    return state.profileBundle;
  };
  state.bundleRefreshPromise = runner().finally(() => {
    state.bundleRefreshPromise = null;
  });
  if (background) {
    state.bundleRefreshPromise.catch(() => null);
  }
  return state.bundleRefreshPromise;
}

function applyReturnedBundle(payload, { backgroundFallback = true } = {}) {
  if (payload?.bundle_patch) {
    const patchSection = String(payload.bundle_patch.bundle_section || "").trim();
    if (patchSection) {
      state.deferredSectionsLoaded.add(patchSection);
    }
    const mergedBundle = mergeBundleData(state.profileBundle, payload.bundle_patch);
    applyProfileBundle(mergedBundle);
    return Promise.resolve(mergedBundle);
  }

  const bundle = extractBundleCandidate(payload);
  if (bundle) {
    if (payload?.bundle_mode === "core") {
      const mergedBundle = state.profileBundle ? mergeBundleData(state.profileBundle, bundle) : bundle;
      state.deferredBundleLoaded = false;
      state.deferredBundlePromise = null;
      clearDeferredSectionState();
      applyProfileBundle(mergedBundle);
      return Promise.resolve(mergedBundle);
    }
    state.deferredBundleLoaded = true;
    clearDeferredSectionState();
    applyProfileBundle(bundle);
    return Promise.resolve(bundle);
  }

  const refreshTask = refreshBundle({ background: backgroundFallback });
  if (backgroundFallback) {
    refreshTask.catch((error) => console.warn("xiuxian bundle refresh failed", error));
    return Promise.resolve(null);
  }
  return refreshTask;
}

function syncActionBundle(payload, { backgroundFallback = true } = {}) {
  return applyReturnedBundle(payload, { backgroundFallback });
}

function refreshLeaderboardInBackground(kind = state.leaderboard.kind, page = state.leaderboard.page) {
  refreshLeaderboard(kind, page).catch((error) => console.warn("xiuxian leaderboard refresh failed", error));
}

async function refreshLeaderboard(kind = state.leaderboard.kind, page = state.leaderboard.page) {
  const result = await postJson("/plugins/xiuxian/api/leaderboard", { kind, page });
  renderLeaderboard(result);
}

async function bootstrap() {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#eef4ff");
    tg.setBackgroundColor("#eef4ff");
  }

  renderAuthPanel();
  if (!state.webSessionToken) {
    resetAuthenticatedView();
    renderAuthPanel("login");
    setStatus("请先登录统一游戏账号，并绑定 Telegram。", "warning");
    return;
  }

  setGameLocked(false);
  renderAuthPanel();

  renderWikiArea();
  state.deferredBundleLoaded = false;
  state.deferredBundlePromise = null;
  clearDeferredSectionState();
  const cachedPayload = hydrateBootstrapCache();
  const cachedGeneration = bootstrapCacheGeneration(cachedPayload);
  if (cachedPayload?.profile_bundle) {
    renderBottomNav(cachedPayload.bottom_nav || []);
    applyProfileBundle(cachedPayload.profile_bundle);
  }
  try {
    const payload = await postJson("/plugins/xiuxian/api/bootstrap", {}, { timeoutMs: 20000 });
    setGameLocked(false);
    rememberTelegramIdentity(payload?.telegram_user);
    renderAuthPanel();
    applyBootstrapPayload(payload, {
      skipIfSameGeneration: true,
      cachedGeneration,
    });
    if (payload.initial_leaderboard) {
      renderLeaderboard(payload.initial_leaderboard);
    }
    scheduleDeferredBootstrapWork();
  } catch (error) {
    if (isWebSessionError(error)) {
      clearWebAuth();
      resetAuthenticatedView();
      renderAuthPanel("login");
      setStatus("登录已失效，请重新登录。", "warning");
      return;
    }
    if (isBindRequiredError(error)) {
      resetAuthenticatedView();
      renderAuthPanel("bind");
      setStatus("完成 Telegram 绑定后即可进入修仙。", "warning");
      return;
    }
    if (!cachedPayload?.profile_bundle) {
      throw error;
    }
    setStatus("已显示上次缓存，最新数据同步失败。", "warning");
  }
}

document.querySelector("#enter-path").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "入道中…", () => postJson("/plugins/xiuxian/api/enter"));
    setStatus(`仙途已开，你的灵根是：${profileRootText(payload.profile)}`, "success");
    syncActionBundle(payload);
    refreshLeaderboardInBackground("realm", 1);
    await popup("踏入仙途", `灵根抽取完成：${profileRootText(payload.profile)}`);
  } catch (error) {
    const message = normalizeError(error, "踏入仙途失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#train-btn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "吐纳中…", () => postJson("/plugins/xiuxian/api/train"));
    const growthText = attributeGrowthText(payload.attribute_growth || []);
    const curseText = curseEventText(payload.curse_event);
    const efficiencyText = Number(payload.cultivation_efficiency_percent || 100) < 100
      ? `\n避世修为效率：${payload.cultivation_efficiency_percent}%（原始 ${payload.gain_raw || payload.gain}）`
      : "";
    setStatus(`本次修炼获得修为 ${payload.gain}、灵石 ${payload.stone_gain}${growthText ? `，${growthText}` : ""}。${curseText ? ` ${curseText}` : ""}`, "success");
    syncActionBundle(payload);
    refreshLeaderboardInBackground(state.leaderboard.kind, state.leaderboard.page);
    await popup("吐纳成功", `修为 +${payload.gain}\n灵石 +${payload.stone_gain}${growthText ? `\n${growthText}` : ""}${efficiencyText}${curseText ? `\n☠️ ${curseText}` : ""}`);
  } catch (error) {
    const message = normalizeError(error, "吐纳修炼失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#break-btn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "突破中…", () => postJson("/plugins/xiuxian/api/breakthrough", { use_pill: false }));
    const tone = payload.success ? "success" : "warning";
    const message = `点数 ${payload.roll} / 成功率 ${payload.success_rate}%`;
    setStatus(`突破判定完成：${message}`, tone);
    syncActionBundle(payload);
    refreshLeaderboardInBackground("realm", 1);
    await popup(payload.success ? "突破成功" : "突破失败", message, tone);
  } catch (error) {
    const message = normalizeError(error, "突破失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#break-pill-btn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "服丹突破中…", () => postJson("/plugins/xiuxian/api/breakthrough", { use_pill: true }));
    const tone = payload.success ? "success" : "warning";
    const detail = `点数 ${payload.roll} / 成功率 ${payload.success_rate}%`;
    setStatus(`服用破境丹后已完成突破判定：${detail}`, tone);
    syncActionBundle(payload);
    refreshLeaderboardInBackground("realm", 1);
    await popup(payload.success ? "突破成功" : "突破失败", detail, tone);
  } catch (error) {
    const message = normalizeError(error, "服用破境丹突破失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#retreat-start-btn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "闭关中…", () => postJson("/plugins/xiuxian/api/retreat/start", {
      hours: Number(document.querySelector("#retreat-hours").value || 1)
    }));
    const retreatProfile = payload.profile?.profile || {};
    const lines = [
      `预计获得 ${payload.estimated_gain} 修为`,
      `预计消耗 ${payload.estimated_cost} 灵石`,
    ];
    if (retreatProfile.retreat_started_at) {
      lines.push(`开始时间：${formatDate(retreatProfile.retreat_started_at)}`);
    }
    if (retreatProfile.retreat_end_at) {
      lines.push(`预计出关：${formatDate(retreatProfile.retreat_end_at)}`);
    }
    if (Number(payload.cultivation_efficiency_percent || 100) < 100) {
      lines.push(`当前避世效率 ${payload.cultivation_efficiency_percent}%（原始 ${payload.estimated_gain_raw || payload.estimated_gain}）`);
    }
    const message = lines.join("\n");
    setStatus(`闭关已开始，预计 ${retreatProfile.retreat_end_at ? formatDate(retreatProfile.retreat_end_at) : "稍后"} 出关。`, "success");
    syncActionBundle(payload);
    await popup("闭关开始", message);
  } catch (error) {
    const message = normalizeError(error, "开始闭关失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#retreat-finish-btn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "出关中…", () => postJson("/plugins/xiuxian/api/retreat/finish"));
    const settled = payload.settled || { gain: 0, cost: 0 };
    const efficiencyText = Number(settled.cultivation_efficiency_percent || 100) < 100
      ? ` 避世效率 ${settled.cultivation_efficiency_percent}%（原始 ${settled.gain_raw || settled.gain}）。`
      : "";
    const baseMessage = `本次闭关获得修为 ${settled.gain}，消耗灵石 ${settled.cost}。${efficiencyText}`;
    const message = settled.insufficient_stone
      ? `${baseMessage}由于中途灵石不足，剩余闭关进度未继续结算。`
      : baseMessage;
    setStatus(message, settled.insufficient_stone ? "warning" : "success");
    syncActionBundle(payload);
    refreshLeaderboardInBackground("realm", 1);
    await popup("闭关结算完成", message, settled.insufficient_stone ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, "出关结算失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#social-mode-btn")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const nextMode = currentSocialMode() === "secluded" ? "worldly" : "secluded";
  const nextLabel = nextMode === "secluded" ? "避世" : "入世";
  try {
    const payload = await runButtonAction(button, "切换中…", () => postJson("/plugins/xiuxian/api/social-mode", { social_mode: nextMode }));
    setStatus(`当前状态已切换为${nextLabel}。`, "success");
    syncActionBundle(payload);
    await popup("状态已切换", `当前已切换为${nextLabel}。`, "success");
  } catch (error) {
    const message = normalizeError(error, "切换状态失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#coin-to-stone-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "兑换中…", () => postJson("/plugins/xiuxian/api/exchange", {
      direction: "coin_to_stone",
      amount: Number(document.querySelector("#coin-to-stone-amount").value || 0)
    }));
    const message = `消耗 ${payload.spent_coin} 片刻碎片，获得 ${payload.received_stone} 灵石。`;
    setStatus(`兑换成功：${message}`, "success");
    syncActionBundle(payload);
    await popup("兑换成功", message);
  } catch (error) {
    const message = normalizeError(error, "兑换灵石失败。");
    setStatus(message, "error");
    await popup("兑换失败", message, "error");
  }
});

document.querySelector("#stone-to-coin-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "兑换中…", () => postJson("/plugins/xiuxian/api/exchange", {
      direction: "stone_to_coin",
      amount: Number(document.querySelector("#stone-to-coin-amount").value || 0)
    }));
    const message = `消耗 ${payload.spent_stone} 灵石，获得 ${payload.received_coin} 片刻碎片。`;
    setStatus(`兑换成功：${message}`, "success");
    syncActionBundle(payload);
    await popup("兑换成功", message);
  } catch (error) {
    const message = normalizeError(error, "兑换碎片失败。");
    setStatus(message, "error");
    await popup("兑换失败", message, "error");
  }
});

document.querySelector("#gambling-exchange-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(
      button,
      "兑换中…",
      () => postJson("/plugins/xiuxian/api/gambling/exchange", {
        count: Number(document.querySelector("#gambling-exchange-count")?.value || 0),
      }, { timeoutMs: ACTION_REQUEST_TIMEOUT_MS }),
      { lockKey: "gambling:exchange" },
    );
    const result = payload.result || {};
    const message = `消耗 ${Number(result.total_cost_stone || 0)} 灵石，兑换 ${Number(result.exchange_count || 0)} 枚仙界奇石，当前持有 ${Number(result.immortal_stone_quantity || 0)} 枚。`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("兑换成功", message);
  } catch (error) {
    const message = normalizeError(error, "兑换仙界奇石失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#gambling-open-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(
      button,
      "开启中…",
      () => postJson("/plugins/xiuxian/api/gambling/open", {
        count: Number(document.querySelector("#gambling-open-count")?.value || 0),
      }, { timeoutMs: ACTION_REQUEST_TIMEOUT_MS }),
      { lockKey: "gambling:open" },
    );
    const result = payload.result || {};
    const rareRows = (result.summary || []).filter((item) => item.broadcasted);
    const lines = [
      `开启数量：${Number(result.opened_count || 0)} 枚`,
      `获得：${result.summary_text || "未知奖励"}`,
      `剩余奇石：${Number(result.remaining_immortal_stone || 0)} 枚`,
    ];
    if (result.fortune_hint) {
      lines.push(result.fortune_hint);
    }
    if (rareRows.length) {
      lines.push(`已触发群播：${rareRows.map((item) => item.duplicate_converted ? `重复${item.quality_label || "高品"} ${item.item_name || "未知物品"}折灵石 +${Number(item.stone_compensation || 0)}` : `${item.quality_label || "高品"} ${item.item_name || "未知物品"} x${Number(item.quantity || 0)}`).join("、")}`);
    }
    setStatus(`奇石开启完成：${result.summary_text || "奖励已发放。"}。`, "success");
    syncActionBundle(payload);
    await popup("奇石开启完成", lines.join("\n"));
  } catch (error) {
    const message = normalizeError(error, "开启仙界奇石失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#shop-item-kind").addEventListener("change", renderInventorySelect);
document.querySelector("#auction-item-kind")?.addEventListener("change", renderAuctionInventorySelect);
document.querySelector("#official-recycle-kind")?.addEventListener("change", () => {
  populateOfficialRecycleInventorySelect();
  updateOfficialRecycleQuotePreview();
  updateOfficialRecycleBatchPreview();
});
document.querySelector("#official-recycle-item-ref")?.addEventListener("change", () => updateOfficialRecycleQuotePreview());
document.querySelector("#official-recycle-quantity")?.addEventListener("input", () => updateOfficialRecycleQuotePreview());
document.querySelector("#official-recycle-search")?.addEventListener("input", () => {
  renderOfficialRecyclePanel(state.profileBundle, false);
});
document.querySelector("#official-recycle-list")?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-recycle-select]");
  if (checkbox) {
    const quote = findOfficialRecycleQuoteBySelectionKey(checkbox.dataset.recycleSelect);
    if (!quote) return;
    if (checkbox.checked) {
      const quantityInput = checkbox.closest(".stack-item")?.querySelector("[data-recycle-quantity]");
      const quantity = Number(quantityInput?.value || defaultOfficialRecycleSelectionQuantity(quote));
      setOfficialRecycleSelection(quote, quantity);
    } else {
      clearOfficialRecycleSelection(quote.item_kind, quote.item_ref_id);
    }
    renderOfficialRecyclePanel(state.profileBundle, false);
    return;
  }
  const quantityInput = event.target.closest("[data-recycle-quantity]");
  if (!quantityInput) return;
  const quote = findOfficialRecycleQuoteBySelectionKey(quantityInput.dataset.recycleQuantity);
  if (!quote) return;
  const maxQuantity = Math.max(officialRecycleMaxQuantity(quote), 1);
  const normalizedQuantity = Math.min(Math.max(Number(quantityInput.value || 0), 1), maxQuantity);
  quantityInput.value = String(normalizedQuantity);
  if (officialRecycleSelectedQuantity(quote.item_kind, quote.item_ref_id) > 0) {
    setOfficialRecycleSelection(quote, normalizedQuantity);
    updateOfficialRecycleBatchPreview();
  }
});
document.querySelector("#official-recycle-list")?.addEventListener("input", (event) => {
  const quantityInput = event.target.closest("[data-recycle-quantity]");
  if (!quantityInput) return;
  const quote = findOfficialRecycleQuoteBySelectionKey(quantityInput.dataset.recycleQuantity);
  if (!quote) return;
  const maxQuantity = Math.max(officialRecycleMaxQuantity(quote), 1);
  const normalizedQuantity = Math.min(Math.max(Number(quantityInput.value || 0), 1), maxQuantity);
  quantityInput.value = String(normalizedQuantity);
  if (officialRecycleSelectedQuantity(quote.item_kind, quote.item_ref_id) > 0) {
    setOfficialRecycleSelection(quote, normalizedQuantity);
    updateOfficialRecycleBatchPreview();
  }
});
document.querySelector("#official-recycle-select-visible")?.addEventListener("click", () => {
  selectVisibleOfficialRecycleQuotes(state.profileBundle);
  renderOfficialRecyclePanel(state.profileBundle, false);
});
document.querySelector("#official-recycle-clear-selection")?.addEventListener("click", () => {
  clearAllOfficialRecycleSelections();
  renderOfficialRecyclePanel(state.profileBundle, false);
});
["#official-recycle-jump-from-shop", "#official-recycle-jump-from-market"].forEach((selector) => {
  document.querySelector(selector)?.addEventListener("click", () => jumpToFoldCard("official-recycle-card"));
});

document.querySelector("#shop-name-toggle")?.addEventListener("click", () => {
  state.shopNameEditing = !state.shopNameEditing;
  applyShopNameState(currentShopNameValue());
  if (state.shopNameEditing) {
    focusShopNameInput(true);
  }
});

document.querySelector("#shop-name")?.addEventListener("pointerdown", () => {
  const input = document.querySelector("#shop-name");
  if (!input || input.disabled || state.shopNameEditing) return;
  state.shopNameEditing = true;
  applyShopNameState(currentShopNameValue());
});

document.querySelector("#shop-name")?.addEventListener("click", () => {
  const input = document.querySelector("#shop-name");
  if (!input || input.disabled || state.shopNameEditing) return;
  openShopNameEditor(false);
});

document.querySelector("#shop-name")?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  state.shopNameEditing = false;
  applyShopNameState(currentShopNameValue());
  document.querySelector("#shop-name-toggle")?.focus({ preventScroll: true });
});

document.querySelector("#personal-shop-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "上架中…", () => postJson("/plugins/xiuxian/api/shop/personal", {
      shop_name: document.querySelector("#shop-name").value.trim(),
      item_kind: document.querySelector("#shop-item-kind").value,
      item_ref_id: Number(document.querySelector("#shop-item-ref").value || 0),
      quantity: Number(document.querySelector("#shop-quantity").value || 1),
      price_stone: Number(document.querySelector("#shop-price").value || 0),
      broadcast: document.querySelector("#shop-broadcast").checked
    }));
    const discountText = payload.broadcast_discount ? `，魅力减免 ${payload.broadcast_discount} 灵石播报费` : "";
    const noticeText = payload.push_warning
      ? ` ${payload.push_warning}`
      : (document.querySelector("#shop-broadcast").checked ? " 商品通知已推送到群里。" : "");
    const message = `已上架 ${payload.listing.item_name}，售价 ${payload.listing.price_stone} 灵石${discountText}。${noticeText}`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("上架成功", message);
  } catch (error) {
    const message = normalizeError(error, "上架个人店铺失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#official-recycle-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "归炉中…", () => postJson("/plugins/xiuxian/api/recycle/official", {
      item_kind: document.querySelector("#official-recycle-kind")?.value || "artifact",
      item_ref_id: Number(document.querySelector("#official-recycle-item-ref")?.value || 0),
      quantity: Number(document.querySelector("#official-recycle-quantity")?.value || 1),
    }));
    const result = payload?.result || {};
    const receivedStone = Number(result.net_stone_gain ?? result.total_price_stone ?? 0);
    const quotedStone = Number(result.total_price_stone || 0);
    const quoteSuffix = receivedStone !== quotedStone ? `（报价 ${quotedStone} 灵石）` : "";
    const message = `已归炉 ${result.item_name || "物品"} x${Number(result.quantity || 0)}，到账 ${receivedStone} 灵石${quoteSuffix}。`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("归炉成功", message);
  } catch (error) {
    const message = normalizeError(error, "提交万宝归炉失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#official-recycle-batch-submit")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const items = buildOfficialRecycleBatchPayload(state.profileBundle);
  if (!items.length) {
    const message = "请先勾选至少一项要归炉的物品。";
    setStatus(message, "warning");
    await popup("尚未勾选", message, "warning");
    return;
  }
  try {
    const payload = await runButtonAction(button, "批量归炉中…", () => postJson("/plugins/xiuxian/api/recycle/official/batch", {
      items,
    }, { timeoutMs: ACTION_REQUEST_TIMEOUT_MS }));
    const result = payload?.result || {};
    const lines = [
      `归炉项数：${Number(result.recycled_line_count || 0)} 项`,
      `归炉数量：${Number(result.total_quantity || 0)} 件`,
      `到账灵石：${Number(result.net_stone_gain ?? result.total_price_stone ?? 0)}`,
    ];
    const detailRows = Array.isArray(result.items) ? result.items : [];
    if (detailRows.length) {
      lines.push(`明细：${detailRows.slice(0, 6).map((item) => `${item.item_name || "未知物品"} x${Number(item.quantity || 0)} +${Number(item.net_stone_gain ?? item.total_price_stone ?? 0)}`).join("、")}`);
      if (detailRows.length > 6) {
        lines.push(`其余 ${detailRows.length - 6} 项已一并归炉。`);
      }
    }
    if (result.partial_success) {
      lines.push(`中断原因：${result.error_message || "批量归炉中断。"}。`);
    }
    if (!result.partial_success) {
      clearAllOfficialRecycleSelections();
    }
    syncActionBundle(payload);
    const message = String(result.summary_text || "批量归炉已完成。");
    setStatus(message, result.partial_success ? "warning" : "success");
    await popup(result.partial_success ? "部分归炉完成" : "批量归炉完成", lines.join("\n"), result.partial_success ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, "批量归炉失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#personal-auction-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "发起中…", () => postJson("/plugins/xiuxian/api/auction/personal", {
      item_kind: document.querySelector("#auction-item-kind").value,
      item_ref_id: Number(document.querySelector("#auction-item-ref").value || 0),
      quantity: Number(document.querySelector("#auction-quantity").value || 1),
      opening_price_stone: Number(document.querySelector("#auction-opening-price").value || 0),
      bid_increment_stone: Number(document.querySelector("#auction-bid-increment").value || 1),
      buyout_price_stone: Number(document.querySelector("#auction-buyout-price").value || 0) || null,
    }));
    const itemName = payload.auction?.item_name || "拍品";
    const buyoutPrice = Number(payload.auction?.buyout_price_stone || 0);
    const pushWarning = String(payload.push_warning || "").trim();
    const message = `${itemName} 已发起群拍，起拍价 ${payload.auction?.opening_price_stone || 0} 灵石，单次加价 ${payload.auction?.bid_increment_stone || 1} 灵石${buyoutPrice > 0 ? `，一口价 ${buyoutPrice} 灵石` : ""}。${pushWarning || "群消息已推送并置顶。"}`
      .trim();
    syncActionBundle(payload);
    setStatus(message, pushWarning ? "warning" : "success");
    await popup(pushWarning ? "拍卖已创建，但置顶失败" : "拍卖已发起", message, pushWarning ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, "发起拍卖失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#personal-shop-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-cancel-id]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "取消中…", () => postJson("/plugins/xiuxian/api/shop/cancel", {
      item_id: Number(button.dataset.cancelId)
    }));
    const message = payload?.result?.item_name
      ? `已取消 ${payload.result.item_name} 的上架。`
      : "已取消该商品的上架。";
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("取消成功", message);
  } catch (error) {
    const message = normalizeError(error, "取消上架失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#artifact-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-equip-id], [data-artifact-bind-id], [data-artifact-unbind-id]");
  if (!button || button.disabled) return;
  try {
    let payload;
    let message = "";
    if (button.dataset.artifactBindId) {
      payload = await runButtonAction(button, "绑定中…", () => postJson("/plugins/xiuxian/api/artifact/bind", {
        artifact_id: Number(button.dataset.artifactBindId)
      }));
      message = `已绑定 ${payload.artifact.name} 1 件。`;
    } else if (button.dataset.artifactUnbindId) {
      payload = await runButtonAction(button, "解绑中…", () => postJson("/plugins/xiuxian/api/artifact/unbind", {
        artifact_id: Number(button.dataset.artifactUnbindId)
      }));
      message = `已解绑 ${payload.artifact.name} 1 件${payload.cost ? `，消耗 ${payload.cost} 灵石` : ""}。`;
    } else {
      payload = await runButtonAction(button, "处理中…", () => postJson("/plugins/xiuxian/api/artifact/equip", {
        artifact_id: Number(button.dataset.equipId)
      }));
      const actionText = payload.action === "unequipped" ? "已卸下法宝" : "已装备法宝";
      message = `${actionText}：${payload.artifact_name}`;
      refreshLeaderboardInBackground(state.leaderboard.kind, state.leaderboard.page);
    }
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("操作成功", message);
  } catch (error) {
    const message = normalizeError(error, "法宝操作失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#pill-list").addEventListener("click", async (event) => {
  const singleButton = event.target.closest("[data-pill-id]");
  const batchButton = event.target.closest("[data-pill-batch-id]");
  const button = batchButton || singleButton;
  if (!button || button.disabled) return;
  try {
    const pillId = Number(batchButton ? button.dataset.pillBatchId : button.dataset.pillId);
    let quantity = 1;
    if (batchButton) {
      const quantityInput = button.closest(".stack-item")?.querySelector(`[data-pill-quantity-for="${pillId}"]`);
      quantity = Math.max(Number(quantityInput?.value || 1), 1);
    }
    const payload = await runButtonAction(button, batchButton ? "批量服用中…" : "服用中…", () => postJson("/plugins/xiuxian/api/pill/use", {
      pill_id: pillId,
      quantity
    }));
    const usedQuantity = Math.max(Number(payload.used_quantity || quantity || 1), 1);
    const statusMessage = usedQuantity > 1
      ? `已批量服用 ${payload.pill.name} x${usedQuantity}。`
      : `已服用 ${payload.pill.name}。`;
    const message = payload.summary ? `${statusMessage}\n${payload.summary}` : statusMessage;
    setStatus(statusMessage, "success");
    syncActionBundle(payload);
    await popup(usedQuantity > 1 ? "批量服用成功" : "服用成功", message);
  } catch (error) {
    const message = normalizeError(error, "服用丹药失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#talisman-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-talisman-id], [data-talisman-bind-id], [data-talisman-unbind-id]");
  if (!button || button.disabled) return;
  try {
    let payload;
    let message = "";
    let title = "操作成功";
    if (button.dataset.talismanBindId) {
      payload = await runButtonAction(button, "绑定中…", () => postJson("/plugins/xiuxian/api/talisman/bind", {
        talisman_id: Number(button.dataset.talismanBindId)
      }));
      message = `已绑定 ${payload.talisman.name} 1 张。`;
    } else if (button.dataset.talismanUnbindId) {
      payload = await runButtonAction(button, "解绑中…", () => postJson("/plugins/xiuxian/api/talisman/unbind", {
        talisman_id: Number(button.dataset.talismanUnbindId)
      }));
      message = `已解绑 ${payload.talisman.name} 1 张${payload.cost ? `，消耗 ${payload.cost} 灵石` : ""}。`;
    } else {
      payload = await runButtonAction(button, "激活中…", () => postJson("/plugins/xiuxian/api/talisman/activate", {
        talisman_id: Number(button.dataset.talismanId)
      }));
      message = `已启用 ${payload.talisman.name}，会持续护持探索与垂钓；斗法、Boss、炼制、吐纳或闭关后会消耗。`;
      if (payload.replaced_talisman_id) {
        message += " 原生效符箓已被覆盖。";
      }
      title = "激活成功";
    }
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup(title, message);
  } catch (error) {
    const message = normalizeError(error, "激活符箓失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

function readShopPurchaseQuantity(button) {
  const itemId = Number(button?.dataset.buyId || 0);
  if (!itemId) return 1;
  const input = button.closest(".stack-item")?.querySelector(`[data-buy-quantity-for="${itemId}"]`);
  if (!input) return 1;
  const min = Math.max(Number.parseInt(input.min || "1", 10) || 1, 1);
  const parsedMax = Number.parseInt(input.max || "", 10);
  const max = Number.isFinite(parsedMax) && parsedMax > 0 ? parsedMax : null;
  let quantity = Math.max(Number.parseInt(input.value || String(min), 10) || min, min);
  if (max !== null) quantity = Math.min(quantity, max);
  input.value = String(quantity);
  return quantity;
}

async function purchaseItem(button) {
  try {
    const requestedQuantity = readShopPurchaseQuantity(button);
    const payload = await runButtonAction(button, "购买中…", () => postJson("/plugins/xiuxian/api/shop/purchase", {
      item_id: Number(button.dataset.buyId),
      quantity: requestedQuantity
    }));
    const itemName = payload.item?.item_name || "商品";
    const purchasedQuantity = Math.max(Number(payload.purchased_quantity || requestedQuantity || 1), 1);
    const quantityText = purchasedQuantity > 1 ? ` x${purchasedQuantity}` : "";
    const discountText = payload.discount_amount ? `，魅力减免 ${payload.discount_amount} 灵石` : "";
    const message = `购买 ${itemName}${quantityText} 成功，共消耗 ${payload.total_cost} 灵石${discountText}。`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("购买成功", message);
  } catch (error) {
    const message = normalizeError(error, "购买商品失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
}

document.querySelector("#official-shop-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-buy-id]");
  if (!button || button.disabled) return;
  await purchaseItem(button);
});

document.querySelector("#community-shop-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-buy-id]");
  if (!button || button.disabled) return;
  await purchaseItem(button);
});

document.querySelector("#sect-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-sect-id]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "加入中…", () => postJson("/plugins/xiuxian/api/sect/join", {
      sect_id: Number(button.dataset.sectId)
    }));
    setStatus("宗门加入成功。", "success");
    syncActionBundle(payload);
    await popup("加入成功", "宗门关系已建立。");
  } catch (error) {
    const message = normalizeError(error, "加入宗门失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#sect-salary-btn")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "领取中…", () => postJson("/plugins/xiuxian/api/sect/salary"));
    setStatus(`已领取宗门俸禄 ${payload.salary} 灵石。`, "success");
    syncActionBundle(payload);
    await popup("领取成功", `已领取宗门俸禄 ${payload.salary} 灵石。`);
  } catch (error) {
    const message = normalizeError(error, "领取俸禄失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#sect-leave-btn")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "叛出中…", () => postJson("/plugins/xiuxian/api/sect/leave"));
    const sectName = payload?.sect?.previous_sect?.name || "当前宗门";
    const betrayal = payload?.sect?.betrayal || {};
    const penalty = Number(betrayal.stone_penalty || 0);
    const contribution = Number(betrayal.contribution_cleared || 0);
    const cooldownUntil = betrayal.cooldown_until ? formatDate(betrayal.cooldown_until) : "";
    const lines = [`你已经叛出 ${sectName}。`];
    if (penalty > 0) lines.push(`宗门收回供奉灵石 ${penalty}。`);
    if (contribution > 0) lines.push(`宗门贡献清零 ${contribution}。`);
    if (cooldownUntil) lines.push(`叛宗余罚将持续到 ${cooldownUntil}。`);
    const message = lines.join("\n");
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("叛出成功", message);
  } catch (error) {
    const message = normalizeError(error, "叛出宗门失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#sect-teach-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  try {
    const amount = Number(document.querySelector("#sect-teach-amount")?.value || 0);
    if (amount < 1000) {
      await popup("表单未完成", "传功至少需要投入 1000 修为。", "error");
      return;
    }
    const payload = await runButtonAction(button, "传功中…", () => postJson("/plugins/xiuxian/api/sect/teach", {
      cultivation_amount: amount
    }));
    const result = payload.result || {};
    const promotionText = result.promotion?.role?.role_name ? `\n职位晋升：${result.promotion.role.role_name}` : "";
    const message = `已向宗门传功 ${amount} 修为，获得 ${Number(result.contribution_gain || 0)} 点宗门贡献。${promotionText}`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("传功成功", message);
  } catch (error) {
    const message = normalizeError(error, "宗门传功失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#sect-attendance-btn")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    const payload = await runButtonAction(button, "签到中…", () => postJson("/plugins/xiuxian/api/sect/attendance", {}));
    const result = payload.result || {};
    const promotionText = result.promotion?.role?.role_name ? `\n职位晋升：${result.promotion.role.role_name}` : "";
    const message = `已完成今日宗门点卯签到，获得 ${Number(result.contribution_gain || 0)} 点宗门贡献。${promotionText}`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("签到成功", message);
  } catch (error) {
    const message = normalizeError(error, "宗门点卯失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#sect-donate-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  try {
    const itemKind = document.querySelector("#sect-donate-kind")?.value || "";
    const itemRefId = Number(document.querySelector("#sect-donate-ref")?.value || 0);
    const quantity = Number(document.querySelector("#sect-donate-quantity")?.value || 0);
    if (!itemKind || !itemRefId || quantity <= 0) {
      await popup("表单未完成", "请选择要捐入宗门宝库的物品与数量。", "error");
      return;
    }
    const payload = await runButtonAction(button, "捐赠中…", () => postJson("/plugins/xiuxian/api/sect/donate", {
      item_kind: itemKind,
      item_ref_id: itemRefId,
      quantity
    }));
    const result = payload.result || {};
    const itemName = result.item?.name || "物品";
    const promotionText = result.promotion?.role?.role_name ? `\n职位晋升：${result.promotion.role.role_name}` : "";
    const message = `已向宗门宝库提交 ${itemName} × ${quantity}，获得 ${Number(result.contribution_gain || 0)} 点宗门贡献。${promotionText}`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("捐赠成功", message);
  } catch (error) {
    const message = normalizeError(error, "捐赠宗门宝库失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#task-image-upload")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const fileInput = document.querySelector("#task-image-file");
  const targetInput = document.querySelector("#task-image");
  const file = fileInput?.files?.[0];
  try {
    const payload = await runButtonAction(button, "上传中…", () =>
      uploadImage("/plugins/xiuxian/api/upload-image", file, "tasks")
    );
    targetInput.value = payload.url;
    if (fileInput) {
      fileInput.value = "";
    }
    setStatus("题图上传成功，已自动回填地址。", "success");
    await popup("上传成功", "题图已上传并写入当前任务表单。");
  } catch (error) {
    const message = normalizeError(error, "题图上传失败。");
    setStatus(message, "error");
    await popup("上传失败", message, "error");
  }
});

document.querySelector("#red-image-upload")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const fileInput = document.querySelector("#red-image-file");
  const targetInput = document.querySelector("#red-image");
  const file = fileInput?.files?.[0];
  try {
    const payload = await runButtonAction(button, "上传中…", () =>
      uploadImage("/plugins/xiuxian/api/upload-image", file, "red-envelopes")
    );
    targetInput.value = payload.url;
    if (fileInput) {
      fileInput.value = "";
    }
    setStatus("红包封面上传成功，已自动回填地址。", "success");
    await popup("上传成功", "红包封面图已上传并写入当前表单。");
  } catch (error) {
    const message = normalizeError(error, "红包封面上传失败。");
    setStatus(message, "error");
    await popup("上传失败", message, "error");
  }
});

document.querySelector("#task-form-legacy")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "发布中…", () => postJson("/plugins/xiuxian/api/task/create", {
      title: document.querySelector("#task-title").value.trim(),
      description: document.querySelector("#task-description").value.trim(),
      task_scope: document.querySelector("#task-scope").value,
      task_type: document.querySelector("#task-type").value,
      question_text: document.querySelector("#task-question").value.trim(),
      answer_text: document.querySelector("#task-answer").value.trim(),
      image_url: document.querySelector("#task-image").value.trim(),
      reward_stone: Number(document.querySelector("#task-reward-stone").value || 0),
      max_claimants: Number(document.querySelector("#task-max-claimants").value || 1),
      active_in_group: document.querySelector("#task-push-group").checked
    }));
    setStatus("悬赏任务已发布。", "success");
    form?.reset?.();
    syncActionBundle(payload);
    await popup("发布成功", `任务【${payload.task.title}】已发布。`);
  } catch (error) {
    const message = normalizeError(error, "发布任务失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#task-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-task-id][data-task-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.taskAction || "claim";
  try {
    let payload = null;
    if (action === "cancel") {
      payload = await runButtonAction(button, "撤销中…", () => postJson("/plugins/xiuxian/api/task/cancel", {
        task_id: Number(button.dataset.taskId)
      }));
      const taskTitle = payload.result?.task?.title || "该任务";
      const message = `任务《${taskTitle}》已撤销。`;
      setStatus(message, "success");
    } else {
      payload = await runButtonAction(button, "领取中…", () => postJson("/plugins/xiuxian/api/task/claim", {
        task_id: Number(button.dataset.taskId)
      }));
      const submitted = payload.result?.submitted_item;
      const resultTask = payload.result?.task || {};
      const reward = payload.result?.reward || null;
      if (submitted?.item) {
        const itemName = submitted.item.name || "任务物品";
        const quantity = submitted.quantity || 0;
        const rewardText = taskResultRewardText(reward, resultTask);
        const message = `已提交 ${itemName} × ${quantity}，任务已直接完成。奖励：${rewardText}`;
        setStatus(message, "success");
        syncActionBundle(payload);
        await popup("提交完成", message);
        return;
      } else if (resultTask.task_type === "metric" && reward) {
        const rewardText = taskResultRewardText(reward, resultTask);
        const message = `计数任务《${resultTask.title || "未命名任务"}》已完成。奖励：${rewardText}`;
        setStatus(message, "success");
        syncActionBundle(payload);
        await popup("结算成功", message);
        return;
      } else if (resultTask.task_type === "metric") {
        const message = "计数任务已接取，后续只统计你接取之后新增的完成进度。";
        setStatus(message, "success");
        syncActionBundle(payload);
        await popup("接取成功", message);
        return;
      } else {
        const message = "任务已接取，请按要求完成后再领取奖励。";
        setStatus(message, "success");
        syncActionBundle(payload);
        await popup("接取成功", message);
        return;
      }
    }
    syncActionBundle(payload);
    await popup("撤销成功", `任务《${payload?.result?.task?.title || "该任务"}》已撤销。`);
  } catch (error) {
    const fallback = action === "cancel" ? "撤销任务失败。" : "领取任务失败。";
    const message = normalizeError(error, fallback);
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#technique-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-technique-id]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "切换中…", () => postJson("/plugins/xiuxian/api/technique/activate", {
      technique_id: Number(button.dataset.techniqueId)
    }));
    const techniqueName = payload.technique?.name || "功法";
    const message = `已切换为 ${techniqueName}。`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("切换成功", message);
  } catch (error) {
    const message = normalizeError(error, "切换功法失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#material-list")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-material-scene-query]");
  if (!button || button.disabled) return;
  jumpToMaterialSourceScenes(button.dataset.materialSceneQuery);
});

document.querySelector("#recipe-list")?.addEventListener("click", async (event) => {
  const jumpButton = event.target.closest("[data-material-scene-query]");
  if (jumpButton && !jumpButton.disabled) {
    jumpToMaterialSourceScenes(jumpButton.dataset.materialSceneQuery);
    return;
  }
  const button = event.target.closest("[data-recipe-id]");
  if (!button || button.disabled) return;
  try {
    const quantityInput = document.querySelector(`[data-recipe-quantity-for="${button.dataset.recipeId}"]`);
    const quantity = Math.max(Number.parseInt(quantityInput?.value || "1", 10) || 1, 1);
    const payload = await runButtonAction(button, "炼制中…", () => postJson("/plugins/xiuxian/api/recipe/craft", {
      recipe_id: Number(button.dataset.recipeId),
      quantity,
    }));
    const result = payload.result;
    const tone = result.partial_success ? "warning" : result.success ? "success" : "warning";
    const title = result.partial_success ? "部分炼制成功" : result.success ? "炼制成功" : "炼制失败";
    const message = result.summary_text || (result.success ? "炼制成功，成品已发放。" : "炼制失败，材料已消耗。");
    setStatus(message, tone);
    const detailRows = [`${message}`, `当前成功率 ${result.success_rate}%`];
    if (Number(result.crafted_times || 1) > 1) {
      detailRows.push(`本次开炉 ${result.crafted_times} 次：成功 ${result.success_count || 0}，失败 ${result.failure_count || 0}`);
    }
    if (result.result_item?.name) detailRows.push(`目标成品：${result.result_item.name}`);
    if (Number(result.total_reward_quantity || 0) > 0) detailRows.push(`总产出：${result.total_reward_quantity}`);
    if (result.reward) detailRows.push(`获得：${grantedItemName(result.reward) || "成品已入库"}`);
    syncActionBundle(payload);
    await popup(title, detailRows.join("\n"), tone);
  } catch (error) {
    const message = normalizeError(error, "炼制失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#recipe-list")?.addEventListener("input", (event) => {
  const input = event.target.closest("[data-recipe-quantity-for]");
  if (!input) return;
  updateRecipeQuantityHint(input);
});

document.querySelector("#recipe-fragment-synthesis-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-recipe-synthesis-id]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "参悟中…", () => postJson("/plugins/xiuxian/api/recipe/synthesize", {
      recipe_id: Number(button.dataset.recipeSynthesisId)
    }));
    const result = payload.result || {};
    const recipeName = result.recipe?.name || "配方";
    const materialName = result.fragment_material?.name || "残页";
    const requiredQuantity = Number(result.required_quantity || 1);
    const itemName = result.result_item?.name || result.recipe?.result_item?.name || "成品";
    const message = `已消耗 ${materialName} × ${requiredQuantity}，成功参悟 ${recipeName}。`;
    setStatus(message, "success");
    syncActionBundle(payload);
    await popup("参悟成功", [message, `对应成品：${itemName}`].join("\n"));
  } catch (error) {
    const message = normalizeError(error, "参悟配方失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#scene-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-scene-id]");
  if (!button || button.disabled) return;
  const sceneId = Number(button.dataset.sceneId);
  const minutes = Number(document.querySelector(`[data-scene-minutes='${sceneId}']`)?.value || 10);
  try {
    const payload = await runButtonAction(button, "派遣中…", () => postJson("/plugins/xiuxian/api/explore/start", {
      scene_id: sceneId,
      minutes
    }));
    setStatus("探索已开始。", "success");
    syncActionBundle(payload);
    await popup("探索开始", `已派出角色探索，预计 ${minutes} 分钟后可领取。`, "success", { autoCloseMs: 3800 });
  } catch (error) {
    const message = normalizeError(error, "开始探索失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#exploration-active")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-explore-claim]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "领取中…", () => postJson("/plugins/xiuxian/api/explore/claim", {
      exploration_id: Number(button.dataset.exploreClaim)
    }));
    const result = payload.result || {};
    const death = result.death || {};
    setStatus(death.died ? "探索已结算，秘境中遭逢重创。" : "探索奖励已领取。", death.died ? "warning" : "success");
    const lines = [];
    if (result.exploration?.event_text) lines.push(`📜 遭遇：${result.exploration.event_text}`);
    if (result.exploration?.outcome_payload?.risk_note) lines.push(`⚠️ 风险：${result.exploration.outcome_payload.risk_note}`);
    if (death.died) {
      if (Array.isArray(death.reasons) && death.reasons.length) lines.push(`💥 阵亡原因：${death.reasons.join("；")}`);
      if (typeof death.stone_loss === "number") lines.push(`💸 灵石损失 -${death.stone_loss}`);
      if (typeof death.cultivation_loss === "number") lines.push(`🌀 修为损失 -${death.cultivation_loss}`);
      if (Array.isArray(death.artifact_losses) && death.artifact_losses.length) {
        lines.push(`🧿 遗失装备：${death.artifact_losses.map((item) => item.artifact?.name || "未命名法宝").join("、")}`);
      }
    } else {
      if (typeof result.stone_delta === "number") lines.push(`💰 灵石变化 ${result.stone_delta >= 0 ? "+" : ""}${result.stone_delta}`);
      if (result.reward_item) lines.push(`🎁 基础掉落：${grantedItemName(result.reward_item) || "已发放"}`);
      if (result.bonus_reward) lines.push(`✨ 奇遇额外：${grantedItemName(result.bonus_reward) || "已发放"}`);
      const growthText = attributeGrowthText(result.attribute_growth || []);
      if (growthText) lines.push(`📈 ${growthText}`);
    }
    const curseText = curseEventText(result.curse_event);
    if (curseText) lines.push(`☠️ ${curseText}`);
    syncActionBundle(payload);
    await popup(
      death.died ? "探索失败" : "领取成功",
      lines.join("\n") || "探索奖励已发放到你的背包与档案。",
      death.died ? "warning" : "success",
      { autoCloseMs: death.died ? 6800 : 5600 },
    );
  } catch (error) {
    const message = normalizeError(error, "领取探索奖励失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#red-envelope-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  try {
    const payload = await runButtonAction(button, "发送中…", () => postJson("/plugins/xiuxian/api/red-envelope/create", {
      cover_text: document.querySelector("#red-cover").value.trim(),
      image_url: document.querySelector("#red-image").value.trim(),
      mode: document.querySelector("#red-mode").value,
      amount_total: Number(document.querySelector("#red-amount").value || 0),
      count_total: Number(document.querySelector("#red-count").value || 1),
      target_tg: document.querySelector("#red-target").value ? Number(document.querySelector("#red-target").value) : null
    }));
    setStatus("灵石红包已发往群内。", "success");
    form?.reset?.();
    syncActionBundle(payload);
    await popup("发送成功", `红包【${payload.result.envelope.cover_text}】已发出。`);
  } catch (error) {
    const message = normalizeError(error, "发送红包失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#gift-target-search-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#gift-player-search");
  const query = document.querySelector("#gift-player-query")?.value || "";
  try {
    await runButtonAction(button, "搜索中…", () => searchGiftPlayers(query));
    if (!state.giftSearchResults.length) {
      setStatus("没有找到匹配的道友。", "warning");
    }
  } catch (error) {
    const message = normalizeError(error, "搜索道友失败。");
    setStatus(message, "error");
    await popup("搜索失败", message, "error");
  }
});

document.querySelector("#gift-player-query")?.addEventListener("input", (event) => {
  const keyword = event.currentTarget?.value || "";
  if (state.giftSearchTimer) window.clearTimeout(state.giftSearchTimer);
  if (!String(keyword).trim()) {
    state.giftSearchQuery = "";
    state.giftSearchResults = [];
    renderGiftSearchResults([]);
    return;
  }
  state.giftSearchTimer = window.setTimeout(() => {
    searchGiftPlayers(keyword).catch((error) => {
      const message = normalizeError(error, "搜索道友失败。");
      setStatus(message, "error");
    });
  }, 240);
});

document.querySelector("#gift-player-search-results")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-gift-target-tg]");
  if (!button) return;
  setGiftTarget({
    tg: Number(button.dataset.giftTargetTg || 0),
    display_label: button.dataset.giftTargetLabel || "",
    username: button.dataset.giftTargetUsername || "",
  });
  state.giftSearchQuery = "";
  state.giftSearchResults = [];
  const queryInput = document.querySelector("#gift-player-query");
  if (queryInput) queryInput.value = "";
  renderGiftSearchResults([]);
  setStatus(`已选中 ${button.dataset.giftTargetLabel || `TG ${button.dataset.giftTargetTg || ""}`}。`, "success");
});

document.querySelector("#gift-target-selected")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-clear-gift-target]");
  if (!button) return;
  setGiftTarget(null);
  setStatus("已清除赠送目标。", "warning");
});

document.querySelector("#gender-set-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  const gender = document.querySelector("#gender-select")?.value || "male";
  try {
    const payload = await runButtonAction(button, "设置中…", () => postJson("/plugins/xiuxian/api/gender/set", {
      gender,
    }));
    applyReturnedBundle(payload);
    const result = payload.result || {};
    setStatus(result.message || "性别设置已更新。", "success");
    await popup("设置成功", result.message || "性别设置已更新。");
  } catch (error) {
    const message = normalizeError(error, "设置性别失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#marriage-search-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#marriage-player-search");
  const query = document.querySelector("#marriage-player-query")?.value || "";
  try {
    await runButtonAction(button, "搜索中…", () => searchMarriagePlayers(query));
    if (!state.marriageSearchResults.length) {
      setStatus("没有找到匹配的道友。", "warning");
    }
  } catch (error) {
    const message = normalizeError(error, "搜索道友失败。");
    setStatus(message, "error");
    await popup("搜索失败", message, "error");
  }
});

document.querySelector("#marriage-player-query")?.addEventListener("input", (event) => {
  const keyword = event.currentTarget?.value || "";
  if (state.marriageSearchTimer) window.clearTimeout(state.marriageSearchTimer);
  if (!String(keyword).trim()) {
    state.marriageSearchQuery = "";
    state.marriageSearchResults = [];
    renderMarriageSearchResults([]);
    return;
  }
  state.marriageSearchTimer = window.setTimeout(() => {
    searchMarriagePlayers(keyword).catch((error) => {
      const message = normalizeError(error, "搜索道友失败。");
      setStatus(message, "error");
    });
  }, 240);
});

document.querySelector("#marriage-player-search-results")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-marriage-target-tg]");
  if (!button) return;
  setMarriageTarget({
    tg: Number(button.dataset.marriageTargetTg || 0),
    display_label: button.dataset.marriageTargetLabel || "",
    username: button.dataset.marriageTargetUsername || "",
  });
  state.marriageSearchQuery = "";
  state.marriageSearchResults = [];
  const queryInput = document.querySelector("#marriage-player-query");
  if (queryInput) queryInput.value = "";
  renderMarriageSearchResults([]);
  setStatus(`已选中 ${button.dataset.marriageTargetLabel || `TG ${button.dataset.marriageTargetTg || ""}`}。`, "success");
});

document.querySelector("#marriage-target-selected")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-clear-marriage-target]");
  if (!button) return;
  setMarriageTarget(null);
  setStatus("已清除姻缘目标。", "warning");
});

document.querySelector("#marriage-request-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  const target = currentMarriageTarget();
  if (!target) {
    const message = "请先搜索并选中一位道友。";
    setStatus(message, "warning");
    await popup("无法递交", message, "warning");
    return;
  }
  try {
    const payload = await runButtonAction(button, "递交中…", () => postJson("/plugins/xiuxian/api/marriage/request", {
      target_tg: target.tg,
      message: document.querySelector("#marriage-request-message")?.value?.trim?.() || "",
    }));
    applyReturnedBundle(payload);
    const result = payload.result || {};
    setMarriageTarget(null);
    const messageInput = document.querySelector("#marriage-request-message");
    if (messageInput) messageInput.value = "";
    setStatus(result.message || "结缘信物已送出。", "success");
    await popup("信物已送出", result.message || "结缘信物已送出。");
  } catch (error) {
    const message = normalizeError(error, "递交结缘信物失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#mentorship-search-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#mentorship-player-search");
  const query = document.querySelector("#mentorship-player-query")?.value || "";
  try {
    await runButtonAction(button, "搜索中…", () => searchMentorshipPlayers(query));
    if (!state.mentorshipSearchResults.length) {
      setStatus("没有找到匹配的道友。", "warning");
    }
  } catch (error) {
    const message = normalizeError(error, "搜索道友失败。");
    setStatus(message, "error");
    await popup("搜索失败", message, "error");
  }
});

document.querySelector("#mentorship-player-query")?.addEventListener("input", (event) => {
  const keyword = event.currentTarget?.value || "";
  if (state.mentorshipSearchTimer) window.clearTimeout(state.mentorshipSearchTimer);
  if (!String(keyword).trim()) {
    state.mentorshipSearchQuery = "";
    state.mentorshipSearchResults = [];
    renderMentorshipSearchResults([]);
    return;
  }
  state.mentorshipSearchTimer = window.setTimeout(() => {
    searchMentorshipPlayers(keyword).catch((error) => {
      const message = normalizeError(error, "搜索道友失败。");
      setStatus(message, "error");
    });
  }, 240);
});

document.querySelector("#mentorship-player-search-results")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-mentorship-target-tg]");
  if (!button) return;
  setMentorshipTarget({
    tg: Number(button.dataset.mentorshipTargetTg || 0),
    display_label: button.dataset.mentorshipTargetLabel || "",
    username: button.dataset.mentorshipTargetUsername || "",
  });
  state.mentorshipSearchQuery = "";
  state.mentorshipSearchResults = [];
  const queryInput = document.querySelector("#mentorship-player-query");
  if (queryInput) queryInput.value = "";
  renderMentorshipSearchResults([]);
  setStatus(`已选中 ${button.dataset.mentorshipTargetLabel || `TG ${button.dataset.mentorshipTargetTg || ""}`}。`, "success");
});

document.querySelector("#mentorship-target-selected")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-clear-mentorship-target]");
  if (!button) return;
  setMentorshipTarget(null);
  setStatus("已清除师徒目标。", "warning");
});

document.querySelector("#mentorship-request-role")?.addEventListener("change", () => {
  syncMentorshipRequestComposer(state.profileBundle);
});

document.querySelector("#mentorship-request-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  const target = currentMentorshipTarget();
  if (!target) {
    const message = "请先搜索并选择目标道友。";
    setStatus(message, "warning");
    return await popup("缺少目标", message, "warning");
  }
  const sponsorRole = document.querySelector("#mentorship-request-role")?.value || "disciple";
  try {
    const payload = await runButtonAction(button, "递交中…", () => postJson("/plugins/xiuxian/api/mentorship/request", {
      target_tg: Number(target.tg || 0),
      sponsor_role: sponsorRole,
      message: document.querySelector("#mentorship-request-message")?.value?.trim?.() || "",
    }));
    applyReturnedBundle(payload);
    setMentorshipTarget(null);
    const requestText = payload.result?.request?.sponsor_role_label || mentorshipRequestRoleLabel(sponsorRole);
    setStatus(`已向 ${target.display_label || `TG ${target.tg}`} 递出${requestText}。`, "success");
    await popup("拜帖已送达", payload.result?.message || "对方稍后可在师徒传承页处理你的拜帖。");
    form?.reset?.();
    document.querySelector("#mentorship-request-role").value = "disciple";
    syncMentorshipRequestComposer(state.profileBundle);
  } catch (error) {
    const message = normalizeError(error, "递交师徒拜帖失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#gift-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  const target = currentGiftTarget();
  if (!target) {
    const message = "请先搜索并选择收礼道友。";
    setStatus(message, "warning");
    return await popup("缺少目标", message, "warning");
  }
  try {
    const payload = await runButtonAction(button, "赠送中…", () => postJson("/plugins/xiuxian/api/gift", {
      target_tg: Number(target.tg || 0),
      amount: Number(document.querySelector("#gift-amount").value || 0)
    }));
    const targetName = payload.result?.receiver?.display_label || target.display_label || `TG ${target.tg}`;
    const amount = payload.result?.amount || 0;
    const message = `已向 ${targetName} 赠送 ${amount} 灵石。`;
    setStatus(message, "success");
    document.querySelector("#gift-amount").value = "100";
    syncActionBundle(payload);
    await popup("赠送成功", message);
  } catch (error) {
    const message = normalizeError(error, "灵石赠送失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#item-gift-kind")?.addEventListener("change", () => {
  renderItemGiftInventorySelect(state.profileBundle);
});

document.querySelector("#item-gift-ref")?.addEventListener("change", () => {
  renderItemGiftInventorySelect(state.profileBundle);
});

document.querySelector("#item-gift-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  const target = currentGiftTarget();
  if (!target) {
    const message = "请先搜索并选择收礼道友。";
    setStatus(message, "warning");
    return await popup("缺少目标", message, "warning");
  }
  try {
    const giftQuantity = Number(document.querySelector("#item-gift-quantity").value || 1);
    const payload = await runButtonAction(button, "赠送中…", () => postJson("/plugins/xiuxian/api/gift/item", {
      target_tg: Number(target.tg || 0),
      item_kind: document.querySelector("#item-gift-kind").value,
      item_ref_id: Number(document.querySelector("#item-gift-ref").value || 0),
      quantity: giftQuantity,
    }));
    const result = payload.result || {};
    const itemName = result.item?.artifact?.name
      || result.item?.pill?.name
      || result.item?.talisman?.name
      || result.item?.material?.name
      || "物品";
    const targetName = target.display_label || (target.username ? `@${target.username}` : `TG ${target.tg}`);
    const message = `已向 ${targetName} 赠送 ${itemName} × ${giftQuantity}。`;
    setStatus(message, "success");
    document.querySelector("#item-gift-quantity").value = "1";
    syncActionBundle(payload);
    await popup("物品赠送成功", message);
  } catch (error) {
    const message = normalizeError(error, "物品赠送失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelectorAll(".rank-tab").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await refreshLeaderboard(button.dataset.kind, 1);
    } catch (error) {
      const message = normalizeError(error, "加载排行榜失败。");
      setStatus(message, "error");
    }
  });
});

document.querySelector("#rank-prev").addEventListener("click", async () => {
  if (state.leaderboard.page <= 1) return;
  await refreshLeaderboard(state.leaderboard.kind, state.leaderboard.page - 1);
});

document.querySelector("#rank-next").addEventListener("click", async () => {
  if (state.leaderboard.page >= state.leaderboard.totalPages) return;
  await refreshLeaderboard(state.leaderboard.kind, state.leaderboard.page + 1);
});

function itemAffixTags(item, effects = {}) {
  const rows = [];
  const values = {
    attack: effects.attack_bonus ?? item.attack_bonus,
    defense: effects.defense_bonus ?? item.defense_bonus,
    bone: effects.bone_bonus ?? item.bone_bonus,
    comprehension: effects.comprehension_bonus ?? item.comprehension_bonus,
    divineSense: effects.divine_sense_bonus ?? item.divine_sense_bonus,
    fortune: effects.fortune_bonus ?? item.fortune_bonus,
    qiBlood: effects.qi_blood_bonus ?? item.qi_blood_bonus,
    trueYuan: effects.true_yuan_bonus ?? item.true_yuan_bonus,
    bodyMovement: effects.body_movement_bonus ?? item.body_movement_bonus,
    duel: effects.duel_rate_bonus ?? item.duel_rate_bonus,
    cultivation: effects.cultivation_bonus ?? item.cultivation_bonus,
    breakthrough: effects.breakthrough_bonus ?? item.breakthrough_bonus,
  };
  if (Number(values.attack || 0)) rows.push(`<span class="tag">攻击 ${escapeHtml(values.attack)}</span>`);
  if (Number(values.defense || 0)) rows.push(`<span class="tag">防御 ${escapeHtml(values.defense)}</span>`);
  if (Number(values.bone || 0)) rows.push(`<span class="tag">根骨 ${escapeHtml(values.bone)}</span>`);
  if (Number(values.comprehension || 0)) rows.push(`<span class="tag">悟性 ${escapeHtml(values.comprehension)}</span>`);
  if (Number(values.divineSense || 0)) rows.push(`<span class="tag">神识 ${escapeHtml(values.divineSense)}</span>`);
  if (Number(values.fortune || 0)) rows.push(`<span class="tag">机缘 ${escapeHtml(values.fortune)}</span>`);
  if (Number(values.qiBlood || 0)) rows.push(`<span class="tag">气血 ${escapeHtml(values.qiBlood)}</span>`);
  if (Number(values.trueYuan || 0)) rows.push(`<span class="tag">真元 ${escapeHtml(values.trueYuan)}</span>`);
  if (Number(values.bodyMovement || 0)) rows.push(`<span class="tag">身法 ${escapeHtml(values.bodyMovement)}</span>`);
  if (Number(values.duel || 0)) rows.push(`<span class="tag">斗法 +${escapeHtml(values.duel)}%</span>`);
  if (Number(values.cultivation || 0)) rows.push(`<span class="tag">修炼 +${escapeHtml(values.cultivation)}</span>`);
  if (Number(values.breakthrough || 0)) rows.push(`<span class="tag">突破 +${escapeHtml(values.breakthrough)}</span>`);
  if (item?.curse_summary) rows.push(`<span class="tag">诅咒物</span>`);
  return rows.join("");
}

function curseEventText(event) {
  const text = event && typeof event.message === "string" ? event.message.trim() : "";
  return text || "";
}

function itemAffixText(item, effects = {}) {
  const html = itemAffixTags(item || {}, effects || {});
  if (!html) return "暂无加成";
  const wrapper = document.createElement("div");
  wrapper.innerHTML = html;
  return [...wrapper.querySelectorAll(".tag")]
    .map((node) => (node.textContent || "").trim())
    .filter(Boolean)
    .join(" · ") || "暂无加成";
}

function artifactSetSummaryText(artifactSet = {}) {
  const countText = `${Number(artifactSet.equipped_count || 0)}/${Number(artifactSet.required_count || 2)}`;
  const effectSource = artifactSet.active ? (artifactSet.resolved_effects || artifactSet) : artifactSet;
  return `${artifactSet.name || "未命名套装"} ${countText} · ${itemAffixText(artifactSet, effectSource)}`;
}

function itemArtworkHtml(item, kind = "item", className = "item-art") {
  const url = String(item?.image_url || "").trim();
  if (!url) return "";
  const label = item?.name || kind || "图片";
  return `
    <figure class="${className}">
      <img src="${escapeHtml(url)}" alt="${escapeHtml(label)}" loading="lazy" decoding="async">
    </figure>
  `;
}

function talismanActiveEffectTags(item) {
  const summary = Array.isArray(item?.active_effect_summary) ? item.active_effect_summary : [];
  if (!summary.length) return "";
  return summary
    .slice(0, 5)
    .map((text) => `<span class="tag">${escapeHtml(text)}</span>`)
    .join("");
}

const _legacyRenderArtifactList = renderArtifactList;
const _legacyRenderTalismanList = renderTalismanList;
const _legacyRenderPillList = renderPillList;
const _legacyRenderProfile = renderProfile;

renderArtifactList = function renderArtifactList(items, retreating, equipLimit, equippedCount) {
  const root = document.querySelector("#artifact-list");
  if (!root || !items.length) return _legacyRenderArtifactList(items, retreating, equipLimit, equippedCount);
  root.innerHTML = "";
  for (const row of items) {
    const item = row.artifact;
    const effects = item.resolved_effects || {};
    const disabled = !item.usable || retreating;
    const reason = item.equipped ? "" : fallbackReason(item.unusable_reason, "当前不满足装备条件");
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "artifact")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(artifactEquipCategoryLabel(item))}</span>
        <span class="tag">${escapeHtml(item.equip_slot_label || item.equip_slot || "槽位未定")}</span>
        <span class="tag ${item.artifact_type === "support" ? "support" : ""}">${escapeHtml(item.artifact_type_label || artifactTypeLabel(item.artifact_type))}</span>
        <span class="tag">${escapeHtml(item.rarity || "凡品")}</span>
        ${itemAffixTags(item, effects)}
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-equip-id="${item.id}" ${disabled ? "disabled" : ""}>${escapeHtml(item.action_label || (item.equipped ? "卸下法宝" : "装备法宝"))}</button>
    `;
    root.appendChild(card);
  }
};

renderTalismanList = function renderTalismanList(items, retreating) {
  const root = document.querySelector("#talisman-list");
  if (!root || !items.length) return _legacyRenderTalismanList(items, retreating);
  root.innerHTML = "";
  for (const row of items) {
    const item = row.talisman;
    const effects = item.resolved_effects || {};
    const disabled = item.active || !item.usable || retreating;
    const reason = item.active ? "当前已生效" : fallbackReason(item.unusable_reason, "当前无法启用该符箓");
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "talisman")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(item.rarity || "凡品")}</span>
        ${itemAffixTags(item, effects)}
        ${talismanActiveEffectTags(item)}
      </div>
      <p>启用后持续护持探索与垂钓；斗法、Boss、炼制、吐纳或闭关后会消耗。</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-talisman-id="${item.id}" ${disabled ? "disabled" : ""}>${item.active ? "已生效" : "启用符箓"}</button>
    `;
    root.appendChild(card);
  }
};

renderPillList = function renderPillList(items, retreating) {
  const root = document.querySelector("#pill-list");
  if (!root || !items.length) return _legacyRenderPillList(items, retreating);
  root.innerHTML = "";
  for (const row of items) {
    const item = row.pill;
    const effects = item.resolved_effects || {};
    const disabled = !item.usable;
    const reason = fallbackReason(item.unusable_reason, "当前无法使用该丹药");
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "pill")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(item.rarity || "凡品")}</span>
        <span class="tag">${escapeHtml(item.pill_type_label || item.pill_type)}</span>
        <span class="tag">主效果 ${escapeHtml(item.effect_value)}</span>
        <span class="tag">丹毒 ${escapeHtml(item.poison_delta)}</span>
        ${itemAffixTags(item, effects)}
      </div>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <button type="button" data-pill-id="${item.id}" ${disabled ? "disabled" : ""}>服用丹药</button>
    `;
    root.appendChild(card);
  }
};

renderProfile = function renderProfile(bundle) {
  _legacyRenderProfile(bundle);
  const profile = bundle.profile || {};
  const stats = bundle.effective_stats || {};
  const currentTechnique = bundle.current_technique;
  const settings = bundle.settings || {};
  const grid = document.querySelector("#profile-grid");
  const rootText = document.querySelector("#root-text");
  const actionHint = document.querySelector("#action-hint");
  const socialSummary = document.querySelector("#social-mode-summary");
  const socialButton = document.querySelector("#social-mode-btn");
  const socialMode = currentSocialMode(bundle);
  const socialLabel = profile.social_mode_label || (socialMode === "secluded" ? "避世" : "入世");
  const socialLockReason = currentSocialInteractionLockReason(bundle);
  const duelLockReason = currentDuelLockReason(bundle);
  const seclusionEfficiency = Number(settings.seclusion_cultivation_efficiency_percent || 60);
  if (rootText) {
    rootText.textContent = `灵根：${profile.root_text || profileRootText(profile)} · 品质 ${profile.root_quality || "中品灵根"} · 五行修正 ${(profile.root_bonus ?? 0) >= 0 ? "+" : ""}${profile.root_bonus ?? 0}%`;
  }
  if (grid) {
    grid.innerHTML += `
      <article class="profile-item"><span>根骨</span><strong>${escapeHtml(stats.bone ?? profile.bone ?? 0)}</strong></article>
      <article class="profile-item"><span>悟性</span><strong>${escapeHtml(stats.comprehension ?? profile.comprehension ?? 0)}</strong></article>
      <article class="profile-item"><span>神识</span><strong>${escapeHtml(stats.divine_sense ?? profile.divine_sense ?? 0)}</strong></article>
      <article class="profile-item"><span>机缘</span><strong>${escapeHtml(stats.fortune ?? profile.fortune ?? 0)}</strong></article>
      <article class="profile-item"><span>气血</span><strong>${escapeHtml(stats.qi_blood ?? profile.qi_blood ?? 0)}</strong></article>
      <article class="profile-item"><span>真元</span><strong>${escapeHtml(stats.true_yuan ?? profile.true_yuan ?? 0)}</strong></article>
      <article class="profile-item"><span>身法</span><strong>${escapeHtml(stats.body_movement ?? profile.body_movement ?? 0)}</strong></article>
      <article class="profile-item"><span>攻击</span><strong>${escapeHtml(stats.attack_power ?? profile.attack_power ?? 0)}</strong></article>
      <article class="profile-item"><span>防御</span><strong>${escapeHtml(stats.defense_power ?? profile.defense_power ?? 0)}</strong></article>
      <article class="profile-item"><span>综合战力</span><strong>${escapeHtml(bundle.combat_power ?? 0)}</strong></article>
      <article class="profile-item"><span>当前功法</span><strong>${escapeHtml(currentTechnique?.name || "暂无")}</strong></article>
      <article class="profile-item"><span>当前状态</span><strong>${escapeHtml(socialLabel)}</strong></article>
    `;
  }
  if (actionHint && socialLockReason && !actionHint.textContent.includes(socialLockReason)) {
    actionHint.textContent = `${actionHint.textContent} ${socialLockReason}`.trim();
  }
  if (socialSummary) {
    socialSummary.textContent = socialMode === "secluded"
      ? `当前处于避世状态，斗法、抢劫与互赠已关闭，修为收益按 ${seclusionEfficiency}% 结算。`
      : "当前处于入世状态，可与其他道友正常互动。";
  }
  if (socialButton) {
    socialButton.textContent = socialMode === "secluded" ? "切换为入世" : "切换为避世";
    setDisabled(
      socialButton,
      !bundle?.capabilities?.can_toggle_social_mode,
      bundle?.capabilities?.social_mode_toggle_reason || "当前无法切换状态",
    );
  }
  const giftInteractionReason = duelLockReason || socialLockReason;
  setDisabled(document.querySelector("#gift-form button[type='submit']"), Boolean(giftInteractionReason), giftInteractionReason);
  setDisabled(document.querySelector("#item-gift-form button[type='submit']"), Boolean(giftInteractionReason), giftInteractionReason || "先选择赠送对象。");
  syncGiftPanelState(bundle);
};

const _enhancedRenderProfile = renderProfile;
renderProfile = function renderProfileWithAdminEntry(bundle) {
  _enhancedRenderProfile(bundle);
  ensureSectionState("#technique-card", Boolean(bundle?.profile?.consented));
  syncAdminEntry(bundle);
  syncUserTaskComposer();
};

function qualityBadgeHtml(label, color, className = "tag") {
  const safeLabel = escapeHtml(label || "凡品");
  const style = buildDecorBadgeStyle(color, "#9ca3af");
  return `<span class="${className}" style="${style}">${safeLabel}</span>`;
}

function inventorySearchValue(selector) {
  return String(document.querySelector(selector)?.value || "").trim().toLowerCase();
}

function searchQueryTokens(query) {
  return String(query || "")
    .trim()
    .toLowerCase()
    .split(/[\s,，、;；:：/|｜]+/)
    .filter(Boolean);
}

function collectSearchText(value, output = []) {
  if (value === null || value === undefined || value === false) return output;
  if (Array.isArray(value)) {
    value.forEach((item) => collectSearchText(item, output));
    return output;
  }
  if (typeof value === "object") {
    Object.values(value).forEach((item) => {
      if (item === null || item === undefined || typeof item === "object") return;
      collectSearchText(item, output);
    });
    return output;
  }
  const text = String(value).trim().toLowerCase();
  if (text) output.push(text);
  return output;
}

function buildSearchHaystack(values = []) {
  return collectSearchText(values).join(" ");
}

function formatPercentText(value, fallback = "0") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return numeric % 1 === 0 ? String(numeric) : numeric.toFixed(2).replace(/\.?0+$/, "");
}

function textQueryMatches(query, values = []) {
  if (!query) return true;
  const tokens = searchQueryTokens(query);
  if (!tokens.length) return true;
  const haystack = buildSearchHaystack(values);
  return tokens.every((token) => haystack.includes(token));
}

function inventoryMatches(item, query, extraFields = []) {
  if (!query) return true;
  const haystack = [
    item?.name,
    item?.description,
    item?.rarity,
    item?.quality_label,
    item?.artifact_type_label,
    item?.artifact_role_label,
    item?.equip_category_label,
    item?.equip_slot_label,
    item?.pill_type_label,
    item?.quality_feature,
    item?.quality_description,
    ...extraFields.map((key) => item?.[key]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function sortInventoryRowsByQuality(rows, pickItem, qualityKey = "rarity_level") {
  return [...(rows || [])].sort((left, right) => {
    const leftItem = pickItem(left) || {};
    const rightItem = pickItem(right) || {};
    const leftQuality = Number(leftItem?.[qualityKey] || 0);
    const rightQuality = Number(rightItem?.[qualityKey] || 0);
    if (leftQuality !== rightQuality) return rightQuality - leftQuality;
    return String(leftItem?.name || "").localeCompare(String(rightItem?.name || ""), "zh-Hans-CN");
  });
}

function recipeResultQuality(recipe) {
  return Number(recipe?.result_quality || recipe?.result_item?.rarity_level || recipe?.result_item?.quality_level || 0);
}

function sortRecipesByResultQuality(recipes) {
  return [...(recipes || [])].sort((left, right) => (
    recipeResultQuality(right) - recipeResultQuality(left)
    || String(left?.name || "").localeCompare(String(right?.name || ""), "zh-Hans-CN")
  ));
}

function rerenderInventoryLists() {
  const bundle = state.profileBundle;
  if (!bundle?.profile?.consented) return;
  const retreating = Boolean(bundle.capabilities?.is_in_retreat);
  const equippedArtifacts = bundle.equipped_artifacts || [];
  const equipLimit = Number(bundle.settings?.artifact_equip_limit || bundle.capabilities?.artifact_equip_limit || 1);
  renderArtifactList(bundle.artifacts || [], retreating, equipLimit, equippedArtifacts.length);
  renderTalismanList(bundle.talismans || [], retreating);
  renderPillList(bundle.pills || [], retreating);
  renderMaterialInventoryList(bundle.materials || []);
  renderCraftArea(bundle);
}

function recipeCraftableCount(recipe, bundle) {
  const backendCount = Number(recipe?.material_check?.max_craft_quantity);
  if (Number.isFinite(backendCount) && backendCount >= 0) {
    return Math.floor(backendCount);
  }
  const inventory = new Map(
    (bundle?.materials || []).map((row) => [Number(row?.material?.id || 0), Math.max(Number(row?.quantity || 0), 0)])
  );
  const ingredients = Array.isArray(recipe?.ingredients) ? recipe.ingredients : [];
  if (!ingredients.length) return 0;
  let maxCount = Infinity;
  for (const ingredient of ingredients) {
    const materialId = Number(ingredient?.material_id || ingredient?.material?.id || 0);
    const required = Math.max(Number(ingredient?.quantity || 0), 1);
    const owned = inventory.get(materialId) || 0;
    maxCount = Math.min(maxCount, Math.floor(owned / required));
  }
  return Number.isFinite(maxCount) ? Math.max(maxCount, 0) : 0;
}

function recipeMaterialCheckRow(recipe, ingredient) {
  const materialId = Number(ingredient?.material_id || ingredient?.material?.id || 0);
  return (recipe?.material_check?.materials || []).find((row) => Number(row?.material_id || 0) === materialId) || {};
}

function recipeMissingText(recipe) {
  const rows = recipe?.material_check?.missing_materials || [];
  if (!rows.length) return "";
  return rows
    .map((row) => `${row.material_name || "材料"} 缺 ${Number(row.missing_quantity || 0)}`)
    .join("、");
}

function recipeMissingTextForQuantity(recipe, quantity = 1) {
  const amount = Math.max(Number.parseInt(quantity, 10) || 1, 1);
  const rows = recipe?.material_check?.materials || [];
  const missingRows = rows
    .map((row) => {
      const required = Math.max(Number(row.required_quantity || 0), 0) * amount;
      const owned = Math.max(Number(row.owned_quantity || 0), 0);
      return {
        material_name: row.material_name || "材料",
        required,
        owned,
        missing: Math.max(required - owned, 0),
      };
    })
    .filter((row) => row.missing > 0);
  if (!missingRows.length) return "";
  return missingRows
    .map((row) => `${row.material_name} 缺 ${row.missing}（需 ${row.required}，持有 ${row.owned}）`)
    .join("、");
}

function findRecipeQuantityHint(recipeId) {
  return [...document.querySelectorAll("[data-recipe-quantity-hint-for]")]
    .find((item) => String(item.dataset.recipeQuantityHintFor || "") === String(recipeId));
}

function updateRecipeQuantityHint(input) {
  if (!input) return;
  const recipeId = String(input.dataset.recipeQuantityFor || "");
  const bundle = state.profileBundle || {};
  const recipe = (bundle.recipes || []).find((item) => String(item.id) === recipeId);
  if (!recipe) return;
  const craftableCount = recipeCraftableCount(recipe, bundle);
  const quantity = Math.max(Number.parseInt(input.value || "1", 10) || 1, 1);
  const hint = findRecipeQuantityHint(recipeId);
  if (!hint) return;
  const missingText = recipeMissingTextForQuantity(recipe, quantity);
  hint.textContent = missingText || `当前材料最多可炼 ${craftableCount} 炉`;
  hint.classList.toggle("reason-text", Boolean(missingText));
}

function recipeResultPreviewTags(recipe, item) {
  if (!item) return "";
  const tags = [];
  const kind = recipe?.result_kind || recipe?.recipe_kind || "";
  const qualityLabel = item.rarity || item.quality_label || "凡品";
  tags.push(qualityBadgeHtml(qualityLabel, item.quality_color, "tag"));
  if (kind === "artifact") {
    tags.push(`<span class="tag">${escapeHtml(artifactEquipCategoryLabel(item))}</span>`);
    tags.push(`<span class="tag ${item.artifact_type === "support" ? "support" : ""}">${escapeHtml(item.artifact_type_label || artifactTypeLabel(item.artifact_type))}</span>`);
    tags.push(`<span class="tag">${escapeHtml(item.equip_slot_label || item.equip_slot || "槽位未定")}</span>`);
    tags.push(`<span class="tag">${escapeHtml(item.artifact_role_label || item.artifact_role || "定位未定")}</span>`);
  } else if (kind === "pill") {
    tags.push(`<span class="tag">${escapeHtml(item.pill_type_label || item.pill_type || "丹药")}</span>`);
    tags.push(`<span class="tag">${escapeHtml(item.effect_value_label || "主效果")} ${escapeHtml(item.effect_value ?? 0)}</span>`);
    tags.push(`<span class="tag">丹毒 ${escapeHtml(item.poison_delta ?? 0)}</span>`);
  } else if (kind === "talisman") {
    tags.push(`<span class="tag">显化 ${escapeHtml(item.effect_uses || 1)} 次</span>`);
    const activeEffectTags = talismanActiveEffectTags(item);
    if (activeEffectTags) tags.push(activeEffectTags);
  } else if (kind === "material" && item.quality_feature) {
    tags.push(`<span class="tag">${escapeHtml(item.quality_feature)}</span>`);
  }
  const affixTags = itemAffixTags(item, item.resolved_effects || {});
  if (affixTags) tags.push(affixTags);
  return tags.join("");
}

function recipeResultRequirementText(recipe, item) {
  if (!item) return "";
  const kind = recipe?.result_kind || recipe?.recipe_kind || "";
  if (kind === "artifact" || kind === "pill" || kind === "talisman") {
    return item.min_realm_stage ? `境界要求：${item.min_realm_stage}${item.min_realm_layer || 1}层` : "境界要求：无限制";
  }
  return "";
}

function recipeSearchValues(recipe) {
  return [
    recipe?.search_index,
    recipe?.search_tokens,
    recipe?.id ? `配方id${recipe.id} recipe:${recipe.id}` : "",
    recipe?.name,
    recipe?.recipe_kind,
    recipe?.recipe_kind_label,
    recipe?.result_kind,
    recipe?.result_kind_label,
    recipe?.source,
    recipe?.obtained_note,
    recipe?.source_text,
    recipe?.source_labels,
    recipe?.result_item,
    (recipe?.ingredients || []).map((item) => [
      item?.material,
      item?.material?.name,
      item?.source_text,
      item?.sources,
    ]),
    (recipe?.material_check?.materials || []).map((item) => [
      item?.material_name,
      item?.source_text,
      item?.sources,
    ]),
  ];
}

function recipeSearchScore(recipe, query) {
  const tokens = searchQueryTokens(query);
  if (!tokens.length) return 0;
  const haystack = buildSearchHaystack(recipeSearchValues(recipe));
  if (!tokens.every((token) => haystack.includes(token))) return -1;
  const normalizedQuery = tokens.join(" ");
  const name = String(recipe?.name || "").toLowerCase();
  const resultName = String(recipe?.result_item?.name || "").toLowerCase();
  const recipeKind = String(recipe?.recipe_kind_label || recipe?.recipe_kind || "").toLowerCase();
  const sourceText = String(recipe?.source_text || "").toLowerCase();
  let score = 0;
  if (name === normalizedQuery) score += 120;
  if (name.includes(normalizedQuery)) score += 80;
  if (resultName.includes(normalizedQuery)) score += 48;
  if (recipeKind.includes(normalizedQuery)) score += 24;
  if (sourceText.includes(normalizedQuery)) score += 16;
  for (const token of tokens) {
    if (name.includes(token)) score += 16;
    if (resultName.includes(token)) score += 10;
    if (recipeKind.includes(token)) score += 6;
    if (sourceText.includes(token)) score += 4;
  }
  return score;
}

const RECIPE_KIND_GROUP_META = {
  artifact: { label: "法宝", order: 10 },
  talisman: { label: "符箓", order: 20 },
  pill: { label: "丹药", order: 30 },
};

function normalizedRecipeKind(recipe) {
  const recipeKind = String(recipe?.recipe_kind || "").trim();
  const resultKind = String(recipe?.result_kind || "").trim();
  if (RECIPE_KIND_GROUP_META[recipeKind]) return recipeKind;
  if (RECIPE_KIND_GROUP_META[resultKind]) return resultKind;
  return recipeKind || resultKind || "other";
}

function recipeKindGroupLabel(recipe, kind) {
  if (RECIPE_KIND_GROUP_META[kind]) return RECIPE_KIND_GROUP_META[kind].label;
  return String(recipe?.recipe_kind_label || recipe?.result_kind_label || kind || "其他").trim() || "其他";
}

function recipePillGroupLabel(recipe) {
  const item = recipe?.result_item || {};
  return String(item.pill_type_label || item.pill_type || "其他丹药").trim() || "其他丹药";
}

function buildRecipeGroupDetails(className, title, tip, cards, { foldKey = "", defaultOpen = false } = {}) {
  const details = document.createElement("details");
  details.className = className;
  bindPersistentFoldState(details, foldKey, { defaultOpen });
  details.innerHTML = `
    <summary class="mini-fold-summary">
      <h3>${escapeHtml(title)}</h3>
      <span class="summary-tip">${escapeHtml(tip)}</span>
    </summary>
  `;
  const body = document.createElement("div");
  body.className = "mini-fold-body stack-list";
  cards.forEach((card) => body.appendChild(card));
  details.appendChild(body);
  return details;
}

function appendPillRecipeSubgroups(body, rows) {
  const groups = new Map();
  const sortedRows = [...(rows || [])].sort((left, right) => (
    recipeResultQuality(right.recipe) - recipeResultQuality(left.recipe)
    || String(left.recipe?.name || "").localeCompare(String(right.recipe?.name || ""), "zh-Hans-CN")
  ));
  sortedRows.forEach(({ card, recipe }) => {
    const label = recipePillGroupLabel(recipe);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(card);
  });
  if (groups.size <= 1) {
    sortedRows.forEach(({ card }) => body.appendChild(card));
    return;
  }
  groups.forEach((cards, label) => {
    body.appendChild(buildRecipeGroupDetails(
      "mini-fold recipe-pill-subgroup",
      `${label} (${cards.length})`,
      "丹药小类",
      cards,
      { foldKey: foldStateKey("craft", "recipe-pill-subgroup", label) }
    ));
  });
}

function appendRecipeCardsByKind(root, rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const kind = normalizedRecipeKind(row.recipe);
    if (!groups.has(kind)) {
      groups.set(kind, {
        kind,
        label: recipeKindGroupLabel(row.recipe, kind),
        order: RECIPE_KIND_GROUP_META[kind]?.order ?? 90,
        rows: [],
      });
    }
    groups.get(kind).rows.push(row);
  });
  [...groups.values()]
    .sort((left, right) => left.order - right.order || String(left.label).localeCompare(String(right.label), "zh-Hans-CN"))
    .forEach((group) => {
      const details = document.createElement("details");
      details.className = "mini-fold recipe-kind-group";
      bindPersistentFoldState(details, foldStateKey("craft", "recipe-kind", group.kind));
      details.innerHTML = `
        <summary class="mini-fold-summary">
          <h3>${escapeHtml(group.label)} (${escapeHtml(group.rows.length)})</h3>
          <span class="summary-tip">${escapeHtml(group.rows.length)} 张配方</span>
        </summary>
      `;
      const body = document.createElement("div");
      body.className = "mini-fold-body stack-list";
      group.rows.sort((left, right) => (
        recipeResultQuality(right.recipe) - recipeResultQuality(left.recipe)
        || String(left.recipe?.name || "").localeCompare(String(right.recipe?.name || ""), "zh-Hans-CN")
      ));
      if (group.kind === "pill") {
        appendPillRecipeSubgroups(body, group.rows);
      } else {
        group.rows.forEach(({ card }) => body.appendChild(card));
      }
      details.appendChild(body);
      root.appendChild(details);
    });
}

renderCraftArea = function renderCraftArea(bundle) {
  const materialRoot = document.querySelector("#material-list");
  const recipeRoot = document.querySelector("#recipe-list");
  if (!materialRoot || !recipeRoot) return;

  const sourceMaterials = bundle.materials || [];
  const materialQuery = inventorySearchValue("#material-search");
  const materials = sortInventoryRowsByQuality(
    sourceMaterials.filter((row) => inventoryMatches(row.material || {}, materialQuery, ["quality_feature", "quality_description"])),
    (row) => row.material || {},
    "quality_level"
  );
  materialRoot.innerHTML = materials.length
    ? materials.map((row) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <div class="material-item-head">
            <strong>${escapeHtml(row.material.name)}</strong>
            ${materialSceneJumpButtonHtml(row.material.name, bundle)}
          </div>
          ${qualityBadgeHtml(row.material.quality_label || row.material.quality_level, row.material.quality_color, "badge badge--normal")}
        </div>
        ${itemArtworkHtml(row.material, "material", "item-art item-art--compact")}
        <p>数量 ${escapeHtml(row.quantity)}</p>
        <p class="muted">${escapeHtml(row.material.quality_feature || row.material.quality_description || "")}</p>
      </article>
    `).join("")
    : sourceMaterials.length
      ? `<article class="stack-item"><strong>未找到匹配材料</strong><p>换个名称、品质或用途关键词再试。</p></article>`
      : `<article class="stack-item"><strong>暂无炼制材料</strong><p>可通过探索、任务或主人发放获得。</p></article>`;

  const recipes = sortRecipesByResultQuality(bundle.recipes || []);
  const recipeQuery = inventorySearchValue("#recipe-search");
  const filteredRecipes = recipeQuery
    ? recipes
      .map((recipe) => ({ recipe, score: recipeSearchScore(recipe, recipeQuery) }))
      .filter((row) => row.score >= 0)
      .sort((left, right) => right.score - left.score || String(left.recipe?.name || "").localeCompare(String(right.recipe?.name || ""), "zh-CN"))
      .map((row) => row.recipe)
    : recipes;
  recipeRoot.innerHTML = "";
  if (!filteredRecipes.length) {
    recipeRoot.innerHTML = recipes.length
      ? `<article class="stack-item"><strong>未找到匹配配方</strong><p>可按配方名、成品、材料或获取途径继续搜索。</p></article>`
      : `<article class="stack-item"><strong>暂无配方</strong></article>`;
    return;
  }
  const recipeCards = [];
  for (const recipe of filteredRecipes) {
    const resultItem = recipe.result_item || {};
    const resultName = resultItem.name || "成品";
    const craftableCount = recipeCraftableCount(recipe, bundle);
    const canCraft = craftableCount > 0;
    const recipeKind = recipe.recipe_kind || recipe.result_kind || "";
    const batchMax = Math.max(Math.min(craftableCount || 1, 99), 1);
    const batchDefault = Math.min(batchMax, craftableCount > 0 ? 10 : 1);
    const previewTags = recipeResultPreviewTags(recipe, resultItem);
    const previewDescription = resultItem.description || resultItem.quality_description || resultItem.quality_feature || "暂无详细描述";
    const requirementText = recipeResultRequirementText(recipe, resultItem);
    const ingredientTags = (recipe.ingredients || [])
      .map((item) => {
        const materialName = item.material?.name || "材料";
        const check = recipeMaterialCheckRow(recipe, item);
        const ownedQuantity = Number(check.owned_quantity ?? item.owned_quantity ?? 0);
        const requiredQuantity = Number(check.required_quantity ?? item.quantity ?? 1);
        const enough = Boolean(check.enough ?? item.enough);
        const missingQuantity = Math.max(Number(check.missing_quantity ?? item.missing_quantity ?? Math.max(requiredQuantity - ownedQuantity, 0)), 0);
        const statusText = enough ? `持有 ${ownedQuantity}/${requiredQuantity}` : `缺 ${missingQuantity}，持有 ${ownedQuantity}/${requiredQuantity}`;
        return `<span class="tag ${enough ? "material-enough" : "material-missing"}">${escapeHtml(materialName)} × ${escapeHtml(requiredQuantity)} · ${escapeHtml(statusText)}</span>`;
      })
      .join("");
    const sourceCards = (recipe.ingredients || [])
      .map((item) => {
        const materialName = item.material?.name || "材料";
        const check = recipeMaterialCheckRow(recipe, item);
        const ownedQuantity = Number(check.owned_quantity ?? item.owned_quantity ?? 0);
        const requiredQuantity = Number(check.required_quantity ?? item.quantity ?? 1);
        const missingQuantity = Math.max(Number(check.missing_quantity ?? item.missing_quantity ?? Math.max(requiredQuantity - ownedQuantity, 0)), 0);
        const enough = Boolean(check.enough ?? item.enough);
        const sceneNames = materialSourceSceneNames(materialName, bundle);
        const sourceText = sceneNames.length
          ? `地图：${sceneNames.join("、")}`
          : (item.source_text || (item.sources || []).join("、") || "暂未补充获取路径");
        return `
        <article class="recipe-source-item ${enough ? "is-enough" : "is-missing"}">
          <div class="recipe-source-head">
            <strong>${escapeHtml(materialName)} × ${escapeHtml(requiredQuantity)}</strong>
            ${materialSceneJumpButtonHtml(materialName, bundle)}
          </div>
          <p class="${enough ? "material-enough-text" : "reason-text"}">${escapeHtml(enough ? `材料足够：持有 ${ownedQuantity}` : `材料不足：持有 ${ownedQuantity}，还缺 ${missingQuantity}`)}</p>
          <p>${escapeHtml(sourceText)}</p>
        </article>
      `;
      })
      .join("");
    const previewCard = `
      <article class="recipe-result-preview">
        <div class="stack-item-head">
          <strong>成品属性预览</strong>
          ${qualityBadgeHtml(resultItem.rarity || resultItem.quality_label || "凡品", resultItem.quality_color, "badge badge--normal")}
        </div>
        ${itemArtworkHtml(resultItem, recipe.result_kind || recipe.recipe_kind || "item", "item-art item-art--compact")}
        <p>${escapeHtml(previewDescription)}</p>
        <div class="item-tags">${previewTags || `<span class="tag">暂无额外词条</span>`}</div>
        ${requirementText ? `<p>${escapeHtml(requirementText)}</p>` : ""}
      </article>
    `;
    const actionArea = recipeKind === "pill"
      ? `
        <div class="recipe-craft-controls">
          <label class="recipe-quantity-field">
            <span>炼药炉数</span>
            <input type="number" min="1" max="${escapeHtml(batchMax)}" value="${escapeHtml(batchDefault)}" data-recipe-quantity-for="${recipe.id}" ${canCraft ? "" : "disabled"}>
            <small data-recipe-quantity-hint-for="${escapeHtml(recipe.id)}">${escapeHtml(canCraft ? `当前材料最多可炼 ${craftableCount} 炉` : "当前材料不足 1 炉")}</small>
          </label>
          ${canCraft ? "" : `<p class="reason-text">${escapeHtml(recipeMissingText(recipe) || "当前材料不足 1 炉")}</p>`}
          <button type="button" data-recipe-id="${recipe.id}" ${canCraft ? "" : "disabled"}>${escapeHtml(craftableCount > 1 ? "批量炼药" : "开始炼药")}</button>
        </div>
      `
      : `
        ${canCraft ? "" : `<p class="reason-text">${escapeHtml(recipeMissingText(recipe) || "当前材料不足 1 炉")}</p>`}
        <button type="button" data-recipe-id="${recipe.id}" ${canCraft ? "" : "disabled"}>开始炼制</button>
      `;
    const card = document.createElement("article");
    card.className = "stack-item";
    const recipeRouteText = recipe.source_text
      ? `掉落途径：${recipe.source_text}`
      : "";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(recipe.name)}</strong>
        <span class="badge badge--normal">${escapeHtml(recipe.recipe_kind_label || recipe.recipe_kind)}</span>
      </div>
      <p>${escapeHtml(recipe.source ? `来源：${recipe.source}${recipe.obtained_note ? ` · ${recipe.obtained_note}` : ""}` : "已掌握配方，可随时开炉。")}</p>
      ${recipeRouteText ? `<p>${escapeHtml(recipeRouteText)}</p>` : ""}
      <div class="info-grid">
        <article class="info-chip">
          <span>炼成目标</span>
          <strong>${escapeHtml(resultName)} × ${escapeHtml(recipe.result_quantity)}</strong>
        </article>
        <article class="info-chip">
          <span>当前成功率</span>
          <strong>${escapeHtml(formatPercentText(recipe.current_success_rate, String(recipe.base_success_rate || 0)))}%</strong>
        </article>
        <article class="info-chip">
          <span>所需材料数</span>
          <strong>${escapeHtml((recipe.ingredients || []).length)}</strong>
        </article>
        <article class="info-chip">
          <span>${escapeHtml(recipeKind === "pill" ? "最多可炼" : "当前可炼")}</span>
          <strong>${escapeHtml(canCraft ? `${craftableCount} 炉` : "材料不足")}</strong>
        </article>
      </div>
      ${previewCard}
      <div class="item-tags">${ingredientTags || `<span class="tag">未配置材料</span>`}</div>
      <div class="recipe-source-list">${sourceCards || `<article class="recipe-source-item"><strong>获取路径待补充</strong><p>当前配方没有记录材料来源。</p></article>`}</div>
      ${actionArea}
    `;
    recipeCards.push({ card, recipe });
  }
  appendRecipeCardsByKind(recipeRoot, recipeCards);
};

renderArtifactList = function renderArtifactList(items, retreating, equipLimit, equippedCount) {
  const root = document.querySelector("#artifact-list");
  if (!root) return;
  root.innerHTML = "";
  const artifactQuery = inventorySearchValue("#artifact-search");
  const rows = sortInventoryRowsByQuality(
    (items || []).filter((row) => inventoryMatches(row.artifact || {}, artifactQuery, ["artifact_set_name", "min_realm_stage"])),
    (row) => row.artifact || {},
    "rarity_level"
  );
  if (!rows.length) {
    root.innerHTML = (items || []).length
      ? `<article class="stack-item"><strong>未找到匹配法宝</strong><p>可按名称、品质、分类、槽位或套装继续检索。</p></article>`
      : `<article class="stack-item"><strong>暂无法宝</strong><p>管理后台发放或在${escapeHtml(officialShopName())}购买后会出现在这里。</p></article>`;
    return;
  }
  const cardsArray = [];
  for (const row of rows) {
    const item = row.artifact;
    const effects = item.resolved_effects || {};
    const disabled = !item.usable || retreating;
    const bindableQuantity = Number(row.unbound_quantity ?? row.quantity ?? 0);
    const unbindableQuantity = Number(row.bound_quantity ?? 0);
    const canBind = bindableQuantity > 0;
    const canUnbind = unbindableQuantity > 0;
    const unbindCost = Number(state.profileBundle?.settings?.equipment_unbind_cost || 0);
    const reason = item.equipped
      ? ""
      : fallbackReason(
          item.unusable_reason,
          retreating
            ? "闭关期间无法切换法宝"
            : equippedCount >= equipLimit
              ? `当前最多只能装备 ${equipLimit} 件法宝`
              : "当前不满足装备条件"
        );
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "artifact")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(artifactEquipCategoryLabel(item))}</span>
        <span class="tag">${escapeHtml(item.equip_slot_label || item.equip_slot || "槽位未定")}</span>
        <span class="tag ${item.artifact_type === "support" ? "support" : ""}">${escapeHtml(item.artifact_type_label || artifactTypeLabel(item.artifact_type))}</span>
        ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color, "tag")}
        ${unbindableQuantity > 0 ? `<span class="tag">已绑定 ${escapeHtml(unbindableQuantity)}</span>` : ""}
        ${bindableQuantity > 0 ? `<span class="tag">未绑定 ${escapeHtml(bindableQuantity)}</span>` : ""}
        ${itemAffixTags(item, effects)}
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      <p>可交易：${escapeHtml(row.tradeable_quantity ?? 0)} ｜ 可提交：${escapeHtml(row.consumable_quantity ?? 0)}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <div class="inline-action-buttons">
        <button type="button" data-equip-id="${item.id}" ${disabled ? "disabled" : ""}>${escapeHtml(item.action_label || (item.equipped ? "卸下法宝" : "装备法宝"))}</button>
        <button type="button" class="ghost" data-artifact-bind-id="${item.id}" ${canBind ? "" : "disabled"}>绑定1件</button>
        <button type="button" class="ghost" data-artifact-unbind-id="${item.id}" ${canUnbind ? "" : "disabled"}>解绑1件${unbindCost > 0 ? `（${escapeHtml(unbindCost)}灵石）` : ""}</button>
      </div>
    `;
    cardsArray.push({ card, item });
  }
  renderGroupedCards(root, cardsArray, item => item.rarity || "凡品", { foldNamespace: "inventory:artifact" });
};

renderTalismanList = function renderTalismanList(items, retreating) {
  const root = document.querySelector("#talisman-list");
  if (!root) return;
  root.innerHTML = "";
  const talismanQuery = inventorySearchValue("#talisman-search");
  const rows = sortInventoryRowsByQuality(
    (items || []).filter((row) => inventoryMatches(row.talisman || {}, talismanQuery, ["min_realm_stage"])),
    (row) => row.talisman || {},
    "rarity_level"
  );
  if (!rows.length) {
    root.innerHTML = (items || []).length
      ? `<article class="stack-item"><strong>未找到匹配符箓</strong><p>可以按名称、效果或境界要求搜索。</p></article>`
      : `<article class="stack-item"><strong>暂无符箓</strong><p>符箓启用后会持续护持探索与垂钓；斗法、Boss、炼制、吐纳或闭关后仍会消耗，后续可通过商店、掉落或发放获得。</p></article>`;
    return;
  }
  const cardsArray = [];
  for (const row of rows) {
    const item = row.talisman;
    const effects = item.resolved_effects || {};
    const disabled = item.active || !item.usable || retreating;
    const bindableQuantity = Number(row.unbound_quantity ?? row.quantity ?? 0);
    const unbindableQuantity = Number(row.bound_quantity ?? 0);
    const canBind = bindableQuantity > 0;
    const canUnbind = unbindableQuantity > 0;
    const unbindCost = Number(state.profileBundle?.settings?.equipment_unbind_cost || 0);
    const reason = disabledReason(
      disabled,
      item.active ? "当前已生效" : item.unusable_reason,
      retreating ? "闭关期间无法启用符箓" : "当前不满足启用条件"
    );
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "talisman")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color, "tag")}
        ${unbindableQuantity > 0 ? `<span class="tag">已绑定 ${escapeHtml(unbindableQuantity)}</span>` : ""}
        ${bindableQuantity > 0 ? `<span class="tag">未绑定 ${escapeHtml(bindableQuantity)}</span>` : ""}
        ${itemAffixTags(item, effects)}
        ${talismanActiveEffectTags(item)}
      </div>
      <p>启用后持续护持探索与垂钓；斗法、Boss、炼制、吐纳或闭关后会消耗，斗法内最多显化 ${escapeHtml(item.effect_uses || 1)} 次。</p>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      <p>可交易：${escapeHtml(row.tradeable_quantity ?? 0)} ｜ 可提交：${escapeHtml(row.consumable_quantity ?? 0)}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <div class="inline-action-buttons">
        <button type="button" data-talisman-id="${item.id}" ${disabled ? "disabled" : ""}>${item.active ? "已生效" : "启用符箓"}</button>
        <button type="button" class="ghost" data-talisman-bind-id="${item.id}" ${canBind ? "" : "disabled"}>绑定1件</button>
        <button type="button" class="ghost" data-talisman-unbind-id="${item.id}" ${canUnbind ? "" : "disabled"}>解绑1件${unbindCost > 0 ? `（${escapeHtml(unbindCost)}灵石）` : ""}</button>
      </div>
    `;
    cardsArray.push({ card, item });
  }
  renderGroupedCards(root, cardsArray, item => item.rarity || "凡品", { foldNamespace: "inventory:talisman" });
};

renderPillList = function renderPillList(items, retreating) {
  const root = document.querySelector("#pill-list");
  if (!root) return;
  root.innerHTML = "";
  const pillQuery = inventorySearchValue("#pill-search");
  const rows = sortInventoryRowsByQuality(
    (items || []).filter((row) => inventoryMatches(row.pill || {}, pillQuery, ["pill_type_label", "min_realm_stage"])),
    (row) => row.pill || {},
    "rarity_level"
  );
  if (!rows.length) {
    root.innerHTML = (items || []).length
      ? `<article class="stack-item"><strong>未找到匹配丹药</strong><p>可以按名称、丹类或效果关键词搜索。</p></article>`
      : `<article class="stack-item"><strong>暂无丹药</strong><p>${escapeHtml(officialShopName())}购买或主人发放后会出现在这里。</p></article>`;
    return;
  }
  const cardsArray = [];
  for (const row of rows) {
    const item = row.pill;
    const effects = item.resolved_effects || {};
    const disabled = !item.usable;
    const batchUsable = Boolean(item.batch_usable) && Number(row.quantity || 0) > 1;
    const batchMax = Math.max(Number(item.batch_use_max || row.quantity || 1), 1);
    const batchNote = Number(row.quantity || 0) > 1 ? String(item.batch_use_note || "").trim() : "";
    const reason = disabledReason(disabled, item.unusable_reason, "当前无法使用该丹药");
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity)}</span>
      </div>
      ${itemArtworkHtml(item, "pill")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color, "tag")}
        <span class="tag">${escapeHtml(item.pill_type_label || item.pill_type)}</span>
        <span class="tag">${escapeHtml(item.effect_value_label || "主效果")} ${escapeHtml(effects.effect_value ?? item.effect_value)}</span>
        <span class="tag">丹毒 ${escapeHtml(effects.poison_delta ?? item.poison_delta)}</span>
        ${itemAffixTags(item, effects)}
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${batchNote ? `<p class="muted">${escapeHtml(batchNote)}</p>` : ""}
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <div class="inline-actions">
        <button type="button" data-pill-id="${item.id}" ${disabled ? "disabled" : ""}>服用丹药</button>
        ${batchUsable ? `<input type="number" min="1" max="${escapeHtml(batchMax)}" value="${escapeHtml(Math.min(batchMax, 10))}" data-pill-quantity-for="${item.id}" ${disabled ? "disabled" : ""}>` : ""}
        ${batchUsable ? `<button type="button" class="ghost" data-pill-batch-id="${item.id}" ${disabled ? "disabled" : ""}>批量服用</button>` : ""}
      </div>
    `;
    cardsArray.push({ card, item });
  }
  renderGroupedCards(root, cardsArray, item => item.pill_type_label || item.pill_type || "其他", { foldNamespace: "inventory:pill" });
};

function renderMaterialInventoryList(items = []) {
  const root = document.querySelector("#material-inventory-list");
  if (!root) return;
  root.innerHTML = "";
  const query = inventorySearchValue("#material-inventory-search");
  const rows = sortInventoryRowsByQuality(
    (items || []).filter((row) => inventoryMatches(row.material || {}, query, ["quality_feature", "quality_description"])),
    (row) => row.material || {},
    "quality_level"
  );
  if (!rows.length) {
    root.innerHTML = (items || []).length
      ? `<article class="stack-item"><strong>未找到匹配材料</strong><p>换个名称、品质或用途关键词再试。</p></article>`
      : `<article class="stack-item"><strong>暂无材料</strong><p>探索、垂钓、任务、灵田收获或拍卖流拍返还后会出现在这里。</p></article>`;
    return;
  }
  const cardsArray = rows.map((row) => {
    const item = row.material || {};
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name || "未命名材料")}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity || 0)}</span>
      </div>
      ${itemArtworkHtml(item, "material")}
      <p>${escapeHtml(item.description || item.quality_description || item.quality_feature || "暂无描述")}</p>
      <div class="item-tags">
        ${qualityBadgeHtml(item.quality_label || item.rarity || "凡品", item.quality_color, "tag")}
        ${item.quality_feature ? `<span class="tag">${escapeHtml(item.quality_feature)}</span>` : ""}
        <span class="tag">可交易 ${escapeHtml(row.tradeable_quantity ?? row.quantity ?? 0)}</span>
        <span class="tag">可提交 ${escapeHtml(row.consumable_quantity ?? row.quantity ?? 0)}</span>
      </div>
    `;
    return { card, item };
  });
  renderGroupedCards(root, cardsArray, item => item.quality_label || item.rarity || "材料", { foldNamespace: "inventory:material" });
}

["#artifact-search", "#talisman-search", "#pill-search", "#material-search", "#material-inventory-search"].forEach((selector) => {
  document.querySelector(selector)?.addEventListener("input", () => {
    rerenderInventoryLists();
  });
});

["#recipe-search", "#scene-search"].forEach((selector) => {
  document.querySelector(selector)?.addEventListener("input", () => {
    if (!state.profileBundle?.profile?.consented) return;
    renderCraftArea(state.profileBundle);
    renderExploreArea(state.profileBundle);
  });
});

function syncAdminEntry(bundle = state.profileBundle) {
  const root = document.querySelector("#hero-admin-entry");
  const button = document.querySelector("#open-admin-panel");
  const adminUrl = bundle?.capabilities?.admin_panel_url;
  const visible = Boolean(bundle?.capabilities?.is_admin && adminUrl);
  if (root) {
    root.classList.toggle("hidden", !visible);
  }
  if (button) {
    button.disabled = !visible;
    button.dataset.adminUrl = visible ? adminUrl : "";
  }
}

function syncUserTaskComposer() {
  const taskType = document.querySelector("#task-type")?.value || "custom";
  const isQuiz = taskType === "quiz";
  const isMetric = taskType === "metric";
  const title = document.querySelector("#task-title");
  const description = document.querySelector("#task-description");
  const pushGroup = document.querySelector("#task-push-group");
  const maxClaimants = document.querySelector("#task-max-claimants");
  const question = document.querySelector("#task-question");
  const answer = document.querySelector("#task-answer");
  const requiredKind = document.querySelector("#task-required-kind");
  const requiredRef = document.querySelector("#task-required-ref");
  const requiredQuantity = document.querySelector("#task-required-quantity");
  const metricKey = document.querySelector("#task-metric-key");
  const metricTarget = document.querySelector("#task-metric-target");
  const rewardKind = document.querySelector("#task-reward-kind");
  const rewardRef = document.querySelector("#task-reward-ref");
  const rewardQuantity = document.querySelector("#task-reward-quantity");
  const rewardStone = document.querySelector("#task-reward-stone");
  const rewardScaleMode = document.querySelector("#task-reward-scale-mode");
  renderUserTaskMetricKeyOptions();
  if (pushGroup) {
    if (isQuiz) pushGroup.checked = true;
    pushGroup.disabled = isQuiz;
  }
  if (maxClaimants) {
    if (isQuiz) maxClaimants.value = "1";
    maxClaimants.disabled = isQuiz;
  }
  if (title) title.required = true;
  if (description) description.required = !isQuiz;
  if (question) question.required = isQuiz;
  if (answer) answer.required = isQuiz;
  if (requiredKind) {
    if (isQuiz || isMetric) requiredKind.value = "";
    requiredKind.disabled = isQuiz || isMetric;
  }
  if (requiredQuantity) {
    if (isQuiz || isMetric) requiredQuantity.value = "0";
    requiredQuantity.disabled = isQuiz || isMetric;
  }
  if (requiredRef) {
    requiredRef.disabled = isQuiz || isMetric;
  }
  if (metricKey) {
    if (!isMetric) metricKey.value = "";
    metricKey.disabled = !isMetric;
  }
  if (metricTarget) {
    if (!isMetric) metricTarget.value = "0";
    metricTarget.disabled = !isMetric;
  }
  if (rewardKind && !rewardKind.value) {
    if (rewardRef) rewardRef.value = "";
    if (rewardQuantity) rewardQuantity.value = "0";
  }
  if (rewardScaleMode) {
    const hasStoneReward = Math.max(Number(rewardStone?.value || 0), 0) > 0;
    if (hasStoneReward) rewardScaleMode.value = "fixed";
    rewardScaleMode.disabled = hasStoneReward;
    rewardScaleMode.title = hasStoneReward ? "玩家发布灵石奖励任务时必须使用固定奖励，奖励灵石会按领取上限预扣。" : "";
  }
  renderTaskRequirementSelect();
  renderTaskRewardSelect();
  syncTaskPublishState();
}

function validateUserTaskComposer() {
  const publishButton = document.querySelector("#task-form button[type='submit']");
  const blockedReason = String(publishButton?.dataset.blockedReason || "").trim();
  if (blockedReason) {
    return { title: "当前无法发布", message: blockedReason, tone: "warning" };
  }

  const title = document.querySelector("#task-title")?.value || "";
  const description = document.querySelector("#task-description")?.value || "";
  const taskType = document.querySelector("#task-type")?.value || "custom";
  const question = document.querySelector("#task-question")?.value || "";
  const answer = document.querySelector("#task-answer")?.value || "";
  const requiredKind = document.querySelector("#task-required-kind")?.value || "";
  const requiredRef = Number(document.querySelector("#task-required-ref")?.value || 0);
  const requiredQuantity = Number(document.querySelector("#task-required-quantity")?.value || 0);
  const rewardStone = Number(document.querySelector("#task-reward-stone")?.value || 0);
  const rewardCultivation = Number(document.querySelector("#task-reward-cultivation")?.value || 0);
  const rewardKind = document.querySelector("#task-reward-kind")?.value || "";
  const rewardRef = Number(document.querySelector("#task-reward-ref")?.value || 0);
  const rewardQuantity = Number(document.querySelector("#task-reward-quantity")?.value || 0);
  const rewardScaleMode = document.querySelector("#task-reward-scale-mode")?.value || "fixed";
  const metricKey = document.querySelector("#task-metric-key")?.value || "";
  const metricTarget = Number(document.querySelector("#task-metric-target")?.value || 0);

  if (meaningfulTextLength(title) < 2) {
    return { title: "表单未完成", message: "任务标题至少填写 2 个字。", tone: "error" };
  }

  if (taskType === "quiz") {
    if (meaningfulTextLength(question) < 4) {
      return { title: "表单未完成", message: "答题任务必须填写清晰的题目内容。", tone: "error" };
    }
    if (!String(answer || "").trim()) {
      return { title: "表单未完成", message: "答题任务必须填写标准答案。", tone: "error" };
    }
  } else if (taskType === "metric") {
    if (meaningfulTextLength(description) < 6) {
      return { title: "表单未完成", message: "计数任务必须填写至少 6 个字的任务说明。", tone: "error" };
    }
    if (!metricKey) {
      return { title: "表单未完成", message: "请选择计数任务指标。", tone: "error" };
    }
    if (metricTarget <= 0) {
      return { title: "表单未完成", message: "计数任务目标次数必须大于 0。", tone: "error" };
    }
  } else if (meaningfulTextLength(description) < 6) {
    return { title: "表单未完成", message: "普通任务必须填写至少 6 个字的任务说明。", tone: "error" };
  }

  if (requiredKind) {
    if (!requiredRef) {
      const requiredSelect = document.querySelector("#task-required-ref");
      const message = requiredSelect?.disabled
        ? "当前没有可选择的提交物，请先切换提交物类型或取消提交需求。"
        : "请选择任务需要提交的物品。";
      return { title: "表单未完成", message, tone: "error" };
    }
    if (requiredQuantity <= 0) {
      return { title: "表单未完成", message: "任务提交物数量必须大于 0。", tone: "error" };
    }
  }

  if (rewardStone > 0 && rewardScaleMode === "realm") {
    return { title: "奖励缩放受限", message: "玩家发布含灵石奖励的任务必须使用固定奖励，奖励灵石会按领取上限预先扣押。", tone: "error" };
  }

  const costBreakdown = taskPublishStoneCostBreakdown();
  const currentStone = Number(state.profileBundle?.profile?.spiritual_stone || 0);
  if (currentStone < costBreakdown.totalCost) {
    return { title: "灵石不足", message: `${taskPublishStoneCostText(costBreakdown)}，当前只有 ${currentStone} 灵石。`, tone: "error" };
  }

  if (rewardKind) {
    if (!rewardRef) {
      const rewardSelect = document.querySelector("#task-reward-ref");
      const message = rewardSelect?.disabled
        ? "当前没有可作为奖励的物品，请先切换奖励物类型或取消物品奖励。"
        : "请选择任务完成后要发放的奖励物。";
      return { title: "表单未完成", message, tone: "error" };
    }
    if (rewardQuantity <= 0) {
      return { title: "表单未完成", message: "奖励物数量必须大于 0。", tone: "error" };
    }
    const selectedReward = selectedTaskRewardRow();
    const escrowMultiplier = taskRewardEscrowMultiplier();
    if (selectedReward?.uniqueReward && escrowMultiplier > 1) {
      return { title: "奖励不支持多人", message: "配方和功法奖励只能发布单人委托。", tone: "error" };
    }
    const requiredRewardQuantity = rewardQuantity * escrowMultiplier;
    if (selectedReward && requiredRewardQuantity > Number(selectedReward.quantity || 0)) {
      return { title: "库存不足", message: `奖励物库存不足，当前需要扣押 ${requiredRewardQuantity} 个，最多可提供 ${Number(selectedReward.quantity || 0)} 个。`, tone: "error" };
    }
  }

  if (rewardStone <= 0 && rewardCultivation <= 0 && !rewardKind) {
    return { title: "表单未完成", message: "悬赏任务至少需要设置灵石、修为或物品奖励。", tone: "error" };
  }

  return null;
}

document.querySelector("#task-type")?.addEventListener("change", syncUserTaskComposer);
document.querySelector("#task-max-claimants")?.addEventListener("input", syncUserTaskComposer);
document.querySelector("#task-reward-stone")?.addEventListener("input", syncUserTaskComposer);
document.querySelector("#task-reward-scale-mode")?.addEventListener("change", syncUserTaskComposer);
document.querySelector("#task-required-kind")?.addEventListener("change", renderTaskRequirementSelect);
document.querySelector("#task-reward-kind")?.addEventListener("change", renderTaskRewardSelect);
document.querySelector("#task-reward-ref")?.addEventListener("change", renderTaskRewardSelect);
document.querySelector("#sect-donate-kind")?.addEventListener("change", () => renderSectDonationSelect(state.profileBundle));

document.querySelector("#open-admin-panel")?.addEventListener("click", () => {
  const button = document.querySelector("#open-admin-panel");
  const adminUrl = button?.dataset.adminUrl || state.profileBundle?.capabilities?.admin_panel_url;
  if (adminUrl) {
    window.location.href = withReturnTo(adminUrl) || adminUrl;
  }
});

const userTaskForm = document.querySelector("#task-form");
if (userTaskForm) {
  userTaskForm.noValidate = true;
}

userTaskForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  event.stopImmediatePropagation();
  const form = event.currentTarget;
  const button = form?.querySelector("button[type='submit']");
  try {
    const validation = validateUserTaskComposer();
    if (validation) {
      setStatus(validation.message, validation.tone);
      await popup(validation.title, validation.message, validation.tone);
      return;
    }
    const payload = await runButtonAction(button, "发布中...", () => postJson("/plugins/xiuxian/api/task/create", {
      title: document.querySelector("#task-title").value.trim(),
      description: document.querySelector("#task-description").value.trim(),
      task_scope: document.querySelector("#task-scope").value,
      task_type: document.querySelector("#task-type").value,
      question_text: document.querySelector("#task-question").value.trim(),
      answer_text: document.querySelector("#task-answer").value.trim(),
      image_url: document.querySelector("#task-image").value.trim(),
      required_item_kind: document.querySelector("#task-required-kind").value || null,
      required_item_ref_id: Number(document.querySelector("#task-required-ref").value || 0) || null,
      required_item_quantity: Number(document.querySelector("#task-required-quantity").value || 0),
      reward_stone: Number(document.querySelector("#task-reward-stone").value || 0),
      reward_cultivation: Number(document.querySelector("#task-reward-cultivation").value || 0),
      reward_item_kind: document.querySelector("#task-reward-kind")?.value || null,
      reward_item_ref_id: Number(document.querySelector("#task-reward-ref")?.value || 0) || null,
      reward_item_quantity: Number(document.querySelector("#task-reward-quantity")?.value || 0),
      reward_scale_mode: document.querySelector("#task-reward-scale-mode").value,
      requirement_metric_key: document.querySelector("#task-metric-key").value || null,
      requirement_metric_target: Number(document.querySelector("#task-metric-target").value || 0),
      max_claimants: Number(document.querySelector("#task-max-claimants").value || 1),
      active_in_group: document.querySelector("#task-push-group").checked
    }));
    const pushWarning = payload.push_warning;
    const publishCost = Number(payload.task?.publish_cost ?? state.profileBundle?.settings?.task_publish_cost ?? 0);
    const escrowedRewardStone = Number(payload.task?.escrowed_reward_stone || 0);
    const totalStoneCost = Number(payload.task?.total_spiritual_stone_cost ?? (publishCost + escrowedRewardStone));
    const costText = totalStoneCost > 0
      ? (escrowedRewardStone > 0
        ? `，预扣 ${totalStoneCost} 灵石（发布费 ${publishCost}，奖励押金 ${escrowedRewardStone}）`
        : `，消耗 ${publishCost} 灵石`)
      : "";
    const message = pushWarning
      ? `任务《${payload.task.title}》已创建${costText}，但群内推送失败。\n${pushWarning}`
      : `任务《${payload.task.title}》已发布${costText}。`;
    setStatus(message, pushWarning ? "warning" : "success");
    form?.reset?.();
    const rewardStoneInput = document.querySelector("#task-reward-stone");
    if (rewardStoneInput) rewardStoneInput.value = "10";
    const rewardCultivationInput = document.querySelector("#task-reward-cultivation");
    if (rewardCultivationInput) rewardCultivationInput.value = "0";
    const rewardKindInput = document.querySelector("#task-reward-kind");
    if (rewardKindInput) rewardKindInput.value = "";
    const rewardQuantityInput = document.querySelector("#task-reward-quantity");
    if (rewardQuantityInput) rewardQuantityInput.value = "0";
    const rewardScaleMode = document.querySelector("#task-reward-scale-mode");
    if (rewardScaleMode) rewardScaleMode.value = "fixed";
    const metricTargetInput = document.querySelector("#task-metric-target");
    if (metricTargetInput) metricTargetInput.value = "0";
    syncUserTaskComposer();
    syncActionBundle(payload);
    await popup(pushWarning ? "创建已完成，但推送失败" : "发布成功", message, pushWarning ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, "发布任务失败，请稍后重试");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
}, true);

function looksCorruptedText(value) {
  const text = String(value ?? "").trim();
  if (!text) return true;
  const markers = ["鍙", "鎿", "銆", "鏈", "璇", "闂", "鍒", "鐏", "淇", "寮", "缁", "锛"];
  let hits = 0;
  for (const marker of markers) {
    if (text.includes(marker)) hits += 1;
  }
  return hits >= 2;
}

function toneTitle(tone = "info") {
  if (tone === "error") return "操作失败";
  if (tone === "warning") return "需要注意";
  if (tone === "success") return "操作完成";
  return "状态更新";
}

function toneMessage(tone = "info") {
  if (tone === "error") return "操作没有成功，请稍后重试。";
  if (tone === "warning") return "当前操作已完成，但有额外信息需要留意。";
  if (tone === "success") return "操作已经完成。";
  return "正在同步当前状态。";
}

function readableUiText(value, tone = "info", fallback = "") {
  const text = String(value ?? "").trim();
  if (!text || looksCorruptedText(text)) {
    return fallback || toneMessage(tone);
  }
  return text;
}

function showToast(text, tone = "info") {
  const stack = document.querySelector("#toast-stack");
  if (!stack || !text) return;
  const node = document.createElement("article");
  node.className = `toast ${tone}`;
  node.textContent = text;
  stack.appendChild(node);
  setTimeout(() => {
    node.remove();
  }, 3200);
}

let popupResolver = null;
let popupAutoCloseTimer = null;

function closeInlinePopup() {
  const layer = document.querySelector("#modal-layer");
  if (layer) {
    layer.classList.add("hidden");
    layer.setAttribute("aria-hidden", "true");
  }
  if (popupAutoCloseTimer) {
    window.clearTimeout(popupAutoCloseTimer);
    popupAutoCloseTimer = null;
  }
  document.body.classList.remove("is-modal-open");
  if (popupResolver) {
    const resolve = popupResolver;
    popupResolver = null;
    resolve();
  }
}

document.querySelector("#modal-close")?.addEventListener("click", closeInlinePopup);
document.querySelector("#modal-confirm")?.addEventListener("click", closeInlinePopup);
document.querySelector("[data-modal-close]")?.addEventListener("click", closeInlinePopup);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeInlinePopup();
  }
});

setStatus = function setStatusRefined(text, tone = "info") {
  const safeText = readableUiText(text, tone, toneMessage(tone));
  const statusText = document.querySelector("#status-text");
  const chip = document.querySelector("#feedback-chip");
  if (statusText) statusText.textContent = safeText;
  if (chip) {
    chip.textContent = safeText;
    chip.className = `feedback-chip ${tone === "error" ? "error" : tone === "success" ? "success" : tone === "warning" ? "warning" : ""}`;
    chip.classList.remove("hidden");
  }
  if (tone !== "info") {
    showToast(safeText, tone);
  }
};

popup = async function popupRefined(title, message, tone = "success", options = {}) {
  touchFeedback(tone);
  const layer = document.querySelector("#modal-layer");
  const label = document.querySelector("#modal-label");
  const titleNode = document.querySelector("#modal-title");
  const messageNode = document.querySelector("#modal-message");
  if (!layer || !label || !titleNode || !messageNode) {
    return;
  }
  if (popupResolver) {
    closeInlinePopup();
  }
  label.textContent = toneTitle(tone);
  titleNode.textContent = readableUiText(title, tone, toneTitle(tone));
  messageNode.textContent = readableUiText(message, tone, toneMessage(tone));
  layer.classList.remove("hidden");
  layer.setAttribute("aria-hidden", "false");
  document.body.classList.add("is-modal-open");
  layer.scrollTop = 0;
  messageNode.scrollTop = 0;
  if (popupAutoCloseTimer) {
    window.clearTimeout(popupAutoCloseTimer);
  }
  const autoCloseMs = Number.isFinite(Number(options?.autoCloseMs))
    ? Math.max(Number(options.autoCloseMs), 0)
    : (tone === "error" ? 4600 : tone === "warning" ? 4200 : 3600);
  popupAutoCloseTimer = autoCloseMs > 0 ? window.setTimeout(closeInlinePopup, autoCloseMs) : null;
  if (!options?.waitForClose) {
    popupResolver = null;
    return;
  }
  return new Promise((resolve) => {
    popupResolver = resolve;
  });
};

renderProfile = function renderProfileRedesigned(bundle) {
  state.profileBundle = bundle;
  const profile = bundle.profile || {};
  const consented = Boolean(profile.consented);

  ensureSectionState("#enter-card", !consented);
  [
    "#profile-card",
    "#action-card",
    "#exchange-card",
    "#inventory-card",
    "#technique-card",
    "#official-shop-card",
    "#official-recycle-card",
    "#market-card",
    "#auction-card",
    "#leaderboard-card",
    "#sect-card",
    "#task-card",
    "#craft-card",
    "#explore-card",
    "#red-envelope-card",
    "#journal-card",
    "#gift-card",
  ].forEach((selector) => ensureSectionState(selector, consented));

  const realmBadge = document.querySelector("#realm-badge");
  const rootText = document.querySelector("#root-text");
  const heroRootPill = document.querySelector("#hero-root-pill");
  const profileGrid = document.querySelector("#profile-grid");
  const officialShopTitle = document.querySelector("#official-shop-title");

  if (!consented) {
    const deathAt = profile.death_at ? formatDate(profile.death_at) : "";
    const rebirthCount = Number(profile.rebirth_count || 0);
    const rebirthLocked = Boolean(profile.rebirth_locked || bundle?.capabilities?.rebirth_locked);
    const rebirthAvailableAt = profile.rebirth_available_at ? formatDate(profile.rebirth_available_at) : "";
    const rebirthRemaining = Number(profile.rebirth_cooldown_remaining_seconds || 0);
    const rebirthCooldownHours = Number(profile.rebirth_cooldown_hours || 0);
    const rebirthReason = String(profile.rebirth_cooldown_reason || bundle?.capabilities?.enter_reason || "").trim();
    const rebirthLockedText = rebirthLocked
      ? `转世重修冷却中，还需等待 ${formatRemainingDuration(rebirthRemaining)}${rebirthAvailableAt ? `，预计 ${rebirthAvailableAt} 后可重新踏入仙途。` : "。"}`
      : "";
    const enterButton = document.querySelector("#enter-path");
    setDisabled(enterButton, rebirthLocked, rebirthLockedText || rebirthReason || "当前无法踏入仙途");
    if (realmBadge) realmBadge.textContent = "未入道";
    if (heroRootPill) {
      heroRootPill.textContent = profile.death_at
        ? (rebirthLocked ? "残魂冷却中" : "残魂待续")
        : "等待踏入仙途";
    }
    if (rootText) {
      rootText.textContent = profile.death_at
        ? (
          rebirthLocked
            ? `上一世已于 ${deathAt || "未知时刻"} 陨落，当前转世次数 ${rebirthCount}。${rebirthLockedText}`
            : `上一世已于 ${deathAt || "未知时刻"} 陨落，当前转世次数 ${rebirthCount}。${rebirthCooldownHours > 0 ? `本次重修冷却 ${rebirthCooldownHours} 小时已结束，` : ""}可重新踏入仙途，重新入道后将重开道途。`
        )
        : "确认入道后将抽取灵根、开启境界与背包系统。";
    }
    setStatus(
      profile.death_at
        ? (rebirthLocked
          ? rebirthLockedText
          : `你已身死道消，当前可重新踏入仙途。${rebirthAvailableAt ? ` 本次冷却结束时间：${rebirthAvailableAt}` : ""}`)
        : "你还没有踏入仙途，确认后将建立修仙档案。",
      profile.death_at ? (rebirthLocked ? "error" : "warning") : "warning",
    );
    syncAdminEntry(bundle);
    syncUserTaskComposer();
    return;
  }

  const progress = bundle.progress || {};
  const settings = bundle.settings || {};
  const retreating = Boolean(bundle.capabilities?.is_in_retreat);
  const duelLockReason = currentDuelLockReason(bundle);
  const equippedArtifacts = bundle.equipped_artifacts || [];
  const equipLimit = settings.artifact_equip_limit || bundle.capabilities?.artifact_equip_limit || 1;
  const artifactNames = equippedArtifacts.length ? equippedArtifacts.map((item) => item.name).join("、") : "未装备";
  const talismanName = bundle.active_talisman?.name || "暂无";
  const retreatStatus = retreating ? `闭关中，预计 ${formatDate(profile.retreat_end_at)} 出关` : "当前未闭关";
  const rootLabel = profile.root_text || profileRootText(profile);
  const rootQuality = profile.root_quality || "灵根未定";
  const rootBonus = Number(profile.root_bonus || 0);
  const stats = bundle.effective_stats || {};
  const slaveNames = Array.isArray(profile.slave_names) ? profile.slave_names : [];
  const servitudeText = profile.master_name
    ? `炉鼎于 ${profile.master_name} 名下`
    : (slaveNames.length ? `名下 ${slaveNames.length} 名炉鼎` : "无炉鼎因果");
  const servitudeCooldownText = profile.master_name
    ? (profile.servitude_challenge_available_at ? formatDate(profile.servitude_challenge_available_at) : "可随时发起脱离挑战")
    : "无";

  if (realmBadge) {
    realmBadge.textContent = `${profile.realm_stage || "炼气"}${profile.realm_layer || 0}层`;
  }
  if (heroRootPill) {
    heroRootPill.textContent = `${rootQuality} · ${rootLabel}`;
  }
  if (rootText) {
    rootText.textContent = `灵根：${rootLabel}，五行修正 ${rootBonus >= 0 ? "+" : ""}${rootBonus}%`;
  }
  if (officialShopTitle) {
    officialShopTitle.textContent = officialShopName(bundle);
  }
  if (profileGrid) {
    profileGrid.innerHTML = `
      <article class="profile-item"><span>当前修为</span><strong>${escapeHtml(progress.current ?? profile.cultivation ?? 0)}</strong></article>
      <article class="profile-item"><span>下一层门槛</span><strong>${escapeHtml(progress.threshold ?? 0)}</strong></article>
      <article class="profile-item"><span>距离突破</span><strong>${escapeHtml(progress.remaining ?? 0)}</strong></article>
      <article class="profile-item"><span>灵石</span><strong>${escapeHtml(profile.spiritual_stone ?? 0)}</strong></article>
      <article class="profile-item"><span>根骨</span><strong>${escapeHtml(stats.bone ?? profile.bone ?? 0)}</strong></article>
      <article class="profile-item"><span>悟性</span><strong>${escapeHtml(stats.comprehension ?? profile.comprehension ?? 0)}</strong></article>
      <article class="profile-item"><span>神识</span><strong>${escapeHtml(stats.divine_sense ?? profile.divine_sense ?? 0)}</strong></article>
      <article class="profile-item"><span>机缘</span><strong>${escapeHtml(stats.fortune ?? profile.fortune ?? 0)}</strong></article>
      <article class="profile-item"><span>心志</span><strong>${escapeHtml(stats.willpower ?? profile.willpower ?? 0)}</strong></article>
      <article class="profile-item"><span>魅力</span><strong>${escapeHtml(stats.charisma ?? profile.charisma ?? 0)}</strong></article>
      <article class="profile-item"><span>因果</span><strong>${escapeHtml(stats.karma ?? profile.karma ?? 0)}</strong></article>
      <article class="profile-item"><span>丹毒</span><strong>${escapeHtml(profile.dan_poison ?? 0)} / 100</strong></article>
      <article class="profile-item"><span>法宝位</span><strong>${escapeHtml(equippedArtifacts.length)} / ${escapeHtml(equipLimit)}</strong></article>
      <article class="profile-item"><span>已装法宝</span><strong>${escapeHtml(artifactNames)}</strong></article>
      <article class="profile-item"><span>生效符箓</span><strong>${escapeHtml(talismanName)}</strong></article>
      <article class="profile-item"><span>当前功法</span><strong>${escapeHtml(bundle.current_technique?.name || "暂无")}</strong></article>
      <article class="profile-item"><span>炉鼎关系</span><strong>${escapeHtml(servitudeText)}</strong></article>
      <article class="profile-item"><span>脱离冷却</span><strong>${escapeHtml(servitudeCooldownText)}</strong></article>
      <article class="profile-item"><span>闭关状态</span><strong>${escapeHtml(retreatStatus)}</strong></article>
      <article class="profile-item"><span>宗门贡献</span><strong>${escapeHtml(profile.sect_contribution ?? 0)}</strong></article>
      <article class="profile-item"><span>转世次数</span><strong>${escapeHtml(profile.rebirth_count ?? 0)}</strong></article>
      <article class="profile-item"><span>综合战力</span><strong>${escapeHtml(bundle.combat_power ?? stats.attack_power ?? 0)}</strong></article>
    `;
  }

  const hints = [];
  if (duelLockReason) {
    hints.push(duelLockReason);
  }
  if (retreating) {
    hints.push("闭关期间可继续回收、服丹、钓鱼与奇石操作；若要突破、经营店铺或参与多数交易，请先出关。");
  } else {
    if (!bundle.capabilities?.can_train) hints.push("今日吐纳次数已用完。");
    if (!bundle.capabilities?.can_breakthrough) hints.push("当前还未满足突破条件。");
  }
  const actionHint = document.querySelector("#action-hint");
  if (actionHint) {
    actionHint.textContent = hints.join(" ") || "状态稳定，可以继续修炼、交易、探索或发布任务。";
  }

  const exchangeEnabled = settings.coin_stone_exchange_enabled ?? true;
  const exchangeHint = document.querySelector("#exchange-hint");
  if (exchangeHint) {
    exchangeHint.textContent = exchangeEnabled
      ? `${exchangeHintText(settings)}${duelLockReason ? ` 当前状态：${duelLockReason}` : ""}`
      : `灵石互兑功能当前已关闭。${duelLockReason ? ` 当前状态：${duelLockReason}` : ""}`;
  }

  setDisabled(document.querySelector("#train-btn"), !bundle.capabilities?.can_train, "当前无法吐纳修炼");
  applyBreakthroughActionState(bundle, "当前无法尝试突破");
  setDisabled(document.querySelector("#retreat-start-btn"), !bundle.capabilities?.can_retreat, "当前无法开始闭关");
  setDisabled(document.querySelector("#retreat-finish-btn"), !retreating, "当前没有进行中的闭关");
  const exchangeActionDisabled = Boolean(duelLockReason) || !exchangeEnabled;
  const exchangeActionReason = !exchangeEnabled ? "灵石互兑功能当前已关闭。" : duelLockReason;
  ["#coin-to-stone-amount", "#stone-to-coin-amount"]
    .forEach((selector) => setDisabled(document.querySelector(selector), retreating || exchangeActionDisabled, exchangeActionReason));
  setDisabled(document.querySelector("#coin-to-stone-form button[type='submit']"), retreating || exchangeActionDisabled, exchangeActionReason);
  setDisabled(document.querySelector("#stone-to-coin-form button[type='submit']"), retreating || exchangeActionDisabled, exchangeActionReason);

  const shopDisabledReason = retreating ? "闭关期间无法经营店铺。" : duelLockReason;
  ["#shop-item-kind", "#shop-item-ref", "#shop-quantity", "#shop-price", "#shop-name", "#shop-broadcast"]
    .forEach((selector) => setDisabled(document.querySelector(selector), retreating || Boolean(duelLockReason), shopDisabledReason));
  setDisabled(document.querySelector("#shop-name-toggle"), retreating || Boolean(duelLockReason), shopDisabledReason);
  setDisabled(document.querySelector("#personal-shop-form button[type='submit']"), retreating || Boolean(duelLockReason), shopDisabledReason);
  const officialRecycleDisabledReason = duelLockReason;
  ["#official-recycle-kind", "#official-recycle-item-ref", "#official-recycle-quantity"]
    .forEach((selector) => setDisabled(document.querySelector(selector), Boolean(duelLockReason), officialRecycleDisabledReason));
  setDisabled(document.querySelector("#official-recycle-form button[type='submit']"), Boolean(duelLockReason), officialRecycleDisabledReason);
  const auctionDisabledReason = retreating ? "闭关期间无法发起拍卖。" : duelLockReason;
  ["#auction-item-kind", "#auction-item-ref", "#auction-quantity", "#auction-opening-price", "#auction-bid-increment", "#auction-buyout-price"]
    .forEach((selector) => setDisabled(document.querySelector(selector), retreating || Boolean(duelLockReason), auctionDisabledReason));
  setDisabled(document.querySelector("#personal-auction-form button[type='submit']"), retreating || Boolean(duelLockReason), auctionDisabledReason);
  setDisabled(document.querySelector("#gift-form button[type='submit']"), Boolean(duelLockReason), duelLockReason);
  setDisabled(document.querySelector("#red-envelope-form button[type='submit']"), Boolean(duelLockReason), duelLockReason);

  renderMaterialInventoryList(bundle.materials || []);

  const auctionFeeDisplay = document.querySelector("#auction-fee-display");
  if (auctionFeeDisplay) {
    auctionFeeDisplay.value = `${Number(settings.auction_fee_percent || 0)}%（后台设定）`;
  }
  const auctionDurationDisplay = document.querySelector("#auction-duration-display");
  if (auctionDurationDisplay) {
    auctionDurationDisplay.value = `${Number(settings.auction_duration_minutes || 60)} 分钟`;
  }

  queueOpenLazyFoldCards();
  syncAdminEntry(bundle);
  syncUserTaskComposer();
};

function titleEffectSummary(effects = {}) {
  const rows = [];
  if (Number(effects.attack_bonus || 0)) rows.push(`攻击 ${effects.attack_bonus}`);
  if (Number(effects.defense_bonus || 0)) rows.push(`防御 ${effects.defense_bonus}`);
  if (Number(effects.bone_bonus || 0)) rows.push(`根骨 ${effects.bone_bonus}`);
  if (Number(effects.comprehension_bonus || 0)) rows.push(`悟性 ${effects.comprehension_bonus}`);
  if (Number(effects.divine_sense_bonus || 0)) rows.push(`神识 ${effects.divine_sense_bonus}`);
  if (Number(effects.fortune_bonus || 0)) rows.push(`机缘 ${effects.fortune_bonus}`);
  if (Number(effects.qi_blood_bonus || 0)) rows.push(`气血 ${effects.qi_blood_bonus}`);
  if (Number(effects.true_yuan_bonus || 0)) rows.push(`真元 ${effects.true_yuan_bonus}`);
  if (Number(effects.body_movement_bonus || 0)) rows.push(`身法 ${effects.body_movement_bonus}`);
  if (Number(effects.duel_rate_bonus || 0)) rows.push(`斗法 ${effects.duel_rate_bonus}%`);
  if (Number(effects.cultivation_bonus || 0)) rows.push(`修炼 ${effects.cultivation_bonus}`);
  if (Number(effects.breakthrough_bonus || 0)) rows.push(`突破 ${effects.breakthrough_bonus}`);
  return rows.join(" · ") || "暂无额外效果";
}

function renderTitleAchievementArea(bundle) {
  const currentRoot = document.querySelector("#current-title-summary");
  const titleRoot = document.querySelector("#title-list");
  const achievementRoot = document.querySelector("#achievement-list");
  if (!currentRoot || !titleRoot || !achievementRoot) return;

  const currentTitle = bundle.current_title || null;
  const effectiveStats = bundle.effective_stats || {};
  const charisma = Number(effectiveStats.charisma ?? bundle.profile?.charisma ?? 0);
  const karma = Number(effectiveStats.karma ?? bundle.profile?.karma ?? 0);
  const destinyHint = "魅力会压低官坊成交价与坊市播报成本，因果会抬高突破把握、委托收益与秘境趋吉避凶。";
  currentRoot.innerHTML = currentTitle ? `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${titleColoredNameHtml(currentTitle.name, currentTitle.color)}</strong>
        <span class="badge badge--normal">已佩戴</span>
      </div>
      <p>${escapeHtml(currentTitle.description || "这道名帖已经烙印在你的修仙名帖上。")}</p>
      <p>${escapeHtml(titleEffectSummary(currentTitle.resolved_effects || currentTitle))}</p>
      <p>名帖气运：魅力 ${escapeHtml(charisma)} · 因果 ${escapeHtml(karma)}</p>
      <p class="muted">${escapeHtml(destinyHint)}</p>
      <div class="inline-action-buttons">
        <button type="button" class="ghost" data-title-clear="1">暂不佩戴</button>
      </div>
    </article>
  ` : `<article class="stack-item"><strong>当前未佩戴称号</strong><p>获得称号后可在这里切换展示与效果。</p><p>名帖气运：魅力 ${escapeHtml(charisma)} · 因果 ${escapeHtml(karma)}</p><p class="muted">${escapeHtml(destinyHint)}</p></article>`;

  const titles = bundle.titles || [];
  if (!titles.length) {
    titleRoot.innerHTML = `<article class="stack-item"><strong>尚未获得称号</strong><p>后续可通过管理员发放或成就奖励获得新称号。</p></article>`;
  } else {
    titleRoot.innerHTML = titles.map((row) => {
      const title = row.title || {};
      return `
        <article class="stack-item">
          <div class="stack-item-head">
            <strong>${titleColoredNameHtml(title.name || "未命名称号", title.color)}</strong>
            <span class="badge badge--normal">${title.equipped ? "佩戴中" : "已拥有"}</span>
          </div>
          <p>${escapeHtml(title.description || "暂无称号描述")}</p>
          <p>${escapeHtml(titleEffectSummary(title.resolved_effects || title))}</p>
          <div class="inline-action-buttons">
            <button type="button" data-title-equip="${title.id}" ${title.equipped ? "disabled" : ""}>${title.equipped ? "当前佩戴" : "佩戴称号"}</button>
          </div>
        </article>
      `;
    }).join("");
  }

  const achievements = bundle.achievements || [];
  if (!achievements.length) {
    achievementRoot.innerHTML = `<article class="stack-item"><strong>当前没有已配置成就</strong><p>管理员在后台创建成就后，这里会展示你的进度。</p></article>`;
    return;
  }
  achievementRoot.innerHTML = achievements.map((row) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(row.name || "未命名成就")}</strong>
        <span class="badge badge--normal">${row.unlocked ? "已达成" : `${escapeHtml(row.current_value || 0)} / ${escapeHtml(row.target_value || 0)}`}</span>
      </div>
      <p>${escapeHtml(row.description || (row.metric_label ? `追踪 ${row.metric_label}` : "暂无成就描述"))}</p>
      <p>条件：${escapeHtml(row.metric_label || row.metric_key)} 达到 ${escapeHtml(row.target_value || 0)}，当前进度 ${escapeHtml(row.current_value || 0)}。</p>
      <p>奖励：${escapeHtml(row.reward_summary || "无额外奖励")}</p>
    </article>
  `).join("");
}

function renderMentorshipArea(bundle) {
  const selfRoot = document.querySelector("#mentorship-self-summary");
  const mentorRoot = document.querySelector("#mentorship-mentor-current");
  const discipleRoot = document.querySelector("#mentorship-disciple-list");
  const incomingRoot = document.querySelector("#mentorship-incoming-list");
  const outgoingRoot = document.querySelector("#mentorship-outgoing-list");
  if (!selfRoot || !mentorRoot || !discipleRoot || !incomingRoot || !outgoingRoot) return;

  const mentorship = bundle?.mentorship || {};
  const selfProfile = mentorship.self_profile || {};
  const mentorRelation = mentorship.mentor_relation || null;
  const discipleRelations = mentorship.disciple_relations || [];
  const incomingRequests = mentorship.incoming_requests || [];
  const outgoingRequests = mentorship.outgoing_requests || [];

  selfRoot.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(selfProfile.display_name_with_title || selfProfile.display_label || bundle?.profile?.display_label || "当前角色")}</strong>
        <span class="badge badge--normal">可收徒 ${escapeHtml(mentorship.used_slots || 0)} / ${escapeHtml(mentorship.mentor_capacity || 0)}</span>
      </div>
      <p>${escapeHtml(mentorship.request_hint || "当前可处理师徒相关事务。")}</p>
      <div class="item-tags">
        <span class="tag">当前师尊 ${escapeHtml(mentorRelation?.mentor_profile?.display_label || "暂无")}</span>
        <span class="tag">门下弟子 ${escapeHtml(discipleRelations.length)}</span>
        <span class="tag">剩余名额 ${escapeHtml(mentorship.available_slots || 0)}</span>
      </div>
    </article>
  `;

  if (!mentorRelation) {
    mentorRoot.innerHTML = `<article class="stack-item"><strong>当前没有师尊</strong><p>可在下方搜索高境界道友，递上拜师申请。</p></article>`;
  } else {
    const mentorProfile = mentorRelation.mentor_profile || {};
    mentorRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>师尊：${escapeHtml(mentorProfile.display_name_with_title || mentorProfile.display_label || "未具名师尊")}</strong>
          <span class="badge badge--normal">${escapeHtml(mentorRelation.bond_label || "初结师缘")}</span>
        </div>
        <p>境界 ${escapeHtml(mentorProfile.realm_text || "未知")} · 战力 ${escapeHtml(mentorProfile.combat_power || 0)}</p>
        <p>师徒缘 ${escapeHtml(mentorRelation.bond_value || 0)} ｜ 传道 ${escapeHtml(mentorRelation.teach_count || 0)} 次 ｜ 问道 ${escapeHtml(mentorRelation.consult_count || 0)} 次</p>
        <p>${escapeHtml(mentorRelation.graduation_hint || "完成传道、问道与境界成长后，可申请出师。")}</p>
        ${mentorRelation.consult_reason ? `<p class="reason-text">${escapeHtml(mentorRelation.consult_reason)}</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" data-mentorship-consult="1" ${mentorRelation.can_consult_today ? "" : "disabled"}>今日问道</button>
          <button type="button" class="ghost" data-mentorship-graduate-target="${escapeHtml(mentorProfile.tg || 0)}" ${mentorRelation.graduation_ready ? "" : "disabled"}>申请出师</button>
          <button type="button" class="ghost" data-mentorship-dissolve-target="${escapeHtml(mentorProfile.tg || 0)}">离开师门</button>
        </div>
      </article>
    `;
  }

  if (!discipleRelations.length) {
    discipleRoot.innerHTML = `<article class="stack-item"><strong>当前没有门下弟子</strong><p>可搜索后发出收徒邀请，建立自己的传承。</p></article>`;
  } else {
    discipleRoot.innerHTML = discipleRelations.map((relation) => {
      const discipleProfile = relation.disciple_profile || {};
      return `
        <article class="stack-item">
          <div class="stack-item-head">
            <strong>弟子：${escapeHtml(discipleProfile.display_name_with_title || discipleProfile.display_label || "未具名弟子")}</strong>
            <span class="badge badge--normal">${escapeHtml(relation.bond_label || "初结师缘")}</span>
          </div>
          <p>境界 ${escapeHtml(discipleProfile.realm_text || "未知")} · 战力 ${escapeHtml(discipleProfile.combat_power || 0)}</p>
          <p>师徒缘 ${escapeHtml(relation.bond_value || 0)} ｜ 传道 ${escapeHtml(relation.teach_count || 0)} 次 ｜ 问道 ${escapeHtml(relation.consult_count || 0)} 次</p>
          <p>${escapeHtml(relation.graduation_hint || "继续传道与历练，等待出师。")}</p>
          ${relation.teach_reason ? `<p class="reason-text">${escapeHtml(relation.teach_reason)}</p>` : ""}
          <div class="inline-action-buttons">
            <button type="button" data-mentorship-teach="${escapeHtml(discipleProfile.tg || 0)}" ${relation.can_teach_today ? "" : "disabled"}>今日传道</button>
            <button type="button" class="ghost" data-mentorship-graduate-target="${escapeHtml(discipleProfile.tg || 0)}" ${relation.graduation_ready ? "" : "disabled"}>准许出师</button>
            <button type="button" class="ghost" data-mentorship-dissolve-target="${escapeHtml(discipleProfile.tg || 0)}">解除关系</button>
          </div>
        </article>
      `;
    }).join("");
  }

  if (!incomingRequests.length) {
    incomingRoot.innerHTML = `<article class="stack-item"><strong>没有待处理名帖</strong><p>别人发来的拜师申请或收徒邀请会显示在这里。</p></article>`;
  } else {
    incomingRoot.innerHTML = incomingRequests.map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.sponsor_profile?.display_label || "匿名道友")}</strong>
          <span class="badge badge--normal">${escapeHtml(item.sponsor_role_label || "师徒拜帖")}</span>
        </div>
        <p>拟定关系：师尊 ${escapeHtml(item.mentor_profile?.display_label || "未知")} ｜ 徒弟 ${escapeHtml(item.disciple_profile?.display_label || "未知")}</p>
        <p>到期：${escapeHtml(formatDate(item.expires_at))}</p>
        ${item.message ? `<p>${escapeHtml(item.message)}</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" data-mentorship-request-action="accept" data-mentorship-request-id="${escapeHtml(item.id)}">同意</button>
          <button type="button" class="ghost" data-mentorship-request-action="reject" data-mentorship-request-id="${escapeHtml(item.id)}">婉拒</button>
        </div>
      </article>
    `).join("");
  }

  if (!outgoingRequests.length) {
    outgoingRoot.innerHTML = `<article class="stack-item"><strong>没有你发出的待处理名帖</strong><p>你递出的拜帖，在对方处理前会暂存这里。</p></article>`;
  } else {
    outgoingRoot.innerHTML = outgoingRequests.map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.counterpart_profile?.display_label || "匿名道友")}</strong>
          <span class="badge badge--normal">${escapeHtml(item.sponsor_role_label || "师徒拜帖")}</span>
        </div>
        <p>到期：${escapeHtml(formatDate(item.expires_at))}</p>
        ${item.message ? `<p>${escapeHtml(item.message)}</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" class="ghost" data-mentorship-request-action="cancel" data-mentorship-request-id="${escapeHtml(item.id)}">撤回拜帖</button>
        </div>
      </article>
    `).join("");
  }

  syncMentorshipRequestComposer(bundle);
}

function marriageDisplayName(profile = {}, fallback = "未具名道友") {
  return profile.display_name_with_title || profile.display_label || fallback;
}

function renderMarriageArea(bundle) {
  const selfRoot = document.querySelector("#marriage-self-summary");
  const currentRoot = document.querySelector("#marriage-current-summary");
  const incomingRoot = document.querySelector("#marriage-incoming-list");
  const outgoingRoot = document.querySelector("#marriage-outgoing-list");
  if (!selfRoot || !currentRoot || !incomingRoot || !outgoingRoot) return;

  const marriage = bundle?.marriage || {};
  const selfProfile = marriage.self_profile || bundle?.profile || {};
  const currentMarriage = marriage.current_marriage || null;
  const incomingRequests = marriage.incoming_requests || [];
  const outgoingRequests = marriage.outgoing_requests || [];

  selfRoot.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(marriageDisplayName(selfProfile, "当前角色"))}</strong>
        <span class="badge badge--normal">${escapeHtml(marriage.gender_label || "未设性别")}</span>
      </div>
      <p>${escapeHtml(marriage.request_hint || "当前可处理姻缘事务。")}</p>
      <div class="item-tags">
        <span class="tag">性别 ${escapeHtml(marriage.gender_label || "未设置")}</span>
        <span class="tag">道侣 ${escapeHtml(currentMarriage?.spouse_profile?.display_label || "暂无")}</span>
        <span class="tag">共享灵石 ${escapeHtml(currentMarriage?.shared_spiritual_stone_total ?? bundle?.profile?.spiritual_stone ?? 0)}</span>
      </div>
    </article>
  `;

  if (!currentMarriage) {
    currentRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>当前暂无道侣</strong>
          <span class="badge badge--normal">待结缘</span>
        </div>
        <p>${escapeHtml(marriage.shared_assets_hint || "结为道侣后，灵石与背包会自动共享。")}</p>
      </article>
    `;
  } else {
    const spouseProfile = currentMarriage.spouse_profile || {};
    currentRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>道侣：${escapeHtml(marriageDisplayName(spouseProfile, "未具名道侣"))}</strong>
          <span class="badge badge--normal">${escapeHtml(currentMarriage.bond_label || "新缔良缘")}</span>
        </div>
        <p>境界 ${escapeHtml(spouseProfile.realm_text || "未知")} · 战力 ${escapeHtml(spouseProfile.combat_power || 0)}</p>
        <p>缘分 ${escapeHtml(currentMarriage.bond_value || 0)} ｜ 双修 ${escapeHtml(currentMarriage.dual_cultivation_count || 0)} 次</p>
        <p>${escapeHtml(marriage.shared_assets_hint || "婚后灵石与背包已共享。")}</p>
        ${currentMarriage.dual_cultivate_reason ? `<p class="reason-text">${escapeHtml(currentMarriage.dual_cultivate_reason)}</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" data-marriage-dual-cultivate="1" ${currentMarriage.can_dual_cultivate_today ? "" : "disabled"}>今日双修</button>
          <button type="button" class="ghost" data-marriage-divorce="1">和离分家</button>
        </div>
      </article>
    `;
  }

  if (!incomingRequests.length) {
    incomingRoot.innerHTML = `<article class="stack-item"><strong>没有待处理结缘信物</strong><p>别人发来的道侣请求会显示在这里。</p></article>`;
  } else {
    incomingRoot.innerHTML = incomingRequests.map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.sponsor_profile?.display_label || "匿名道友")}</strong>
          <span class="badge badge--normal">待你回应</span>
        </div>
        <p>对方性别：${escapeHtml(item.sponsor_profile?.gender_label || "未设置")} ｜ 到期：${escapeHtml(formatDate(item.expires_at))}</p>
        ${item.message ? `<p>${escapeHtml(item.message)}</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" data-marriage-request-action="accept" data-marriage-request-id="${escapeHtml(item.id)}">同意</button>
          <button type="button" class="ghost" data-marriage-request-action="reject" data-marriage-request-id="${escapeHtml(item.id)}">婉拒</button>
        </div>
      </article>
    `).join("");
  }

  if (!outgoingRequests.length) {
    outgoingRoot.innerHTML = `<article class="stack-item"><strong>没有你送出的结缘信物</strong><p>你发出的道侣请求，在对方处理前会保存在这里。</p></article>`;
  } else {
    outgoingRoot.innerHTML = outgoingRequests.map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.counterpart_profile?.display_label || "匿名道友")}</strong>
          <span class="badge badge--normal">待对方回应</span>
        </div>
        <p>对方性别：${escapeHtml(item.counterpart_profile?.gender_label || "未设置")} ｜ 到期：${escapeHtml(formatDate(item.expires_at))}</p>
        ${item.message ? `<p>${escapeHtml(item.message)}</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" class="ghost" data-marriage-request-action="cancel" data-marriage-request-id="${escapeHtml(item.id)}">撤回信物</button>
        </div>
      </article>
    `).join("");
  }

  syncGenderComposer(bundle);
  syncMarriageRequestComposer(bundle);
}

function furnaceDisplayName(profile = {}, fallback = "未具名道友") {
  return profile.display_name_with_title || profile.display_label || profile.master_name || fallback;
}

function renderFurnaceArea(bundle) {
  const selfRoot = document.querySelector("#furnace-self-summary");
  const rosterRoot = document.querySelector("#furnace-roster-list");
  if (!selfRoot || !rosterRoot) return;

  const profile = bundle?.profile || {};
  const masterProfile = bundle?.master_profile || null;
  const furnaceRows = Array.isArray(bundle?.slave_profiles) ? bundle.slave_profiles : [];
  const harvestPercent = Number(bundle?.settings?.furnace_harvest_cultivation_percent ?? 10);
  const challengeTime = profile.servitude_challenge_available_at
    ? formatDate(profile.servitude_challenge_available_at)
    : "可随时发起脱离挑战";

  if (profile.master_name) {
    selfRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(furnaceDisplayName(profile, "当前角色"))}</strong>
          <span class="badge badge--normal">炉鼎</span>
        </div>
        <p>你当前归于 ${escapeHtml(profile.master_name)} 名下，主人每天可对你采补一次。</p>
        <div class="item-tags">
          <span class="tag">当前境界 ${escapeHtml(profile.realm_stage || "炼气")}${escapeHtml(profile.realm_layer || 0)}层</span>
          <span class="tag">脱离冷却 ${escapeHtml(challengeTime)}</span>
          <span class="tag">采补比例 ${escapeHtml(harvestPercent)}%</span>
        </div>
        <p class="muted">采补会按你当前境界的修为门槛折算给主人修为，不是简单等额转移。</p>
      </article>
    `;
    rosterRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>主人：${escapeHtml(furnaceDisplayName(masterProfile || {}, profile.master_name || "未具名主人"))}</strong>
          <span class="badge badge--normal">归属中</span>
        </div>
        <p>境界 ${escapeHtml(masterProfile?.realm_stage || "未知")}${escapeHtml(masterProfile?.realm_layer || "-")}层</p>
        <p>若想解除当前归属，需要通过炉鼎对决向主人发起脱离挑战。</p>
      </article>
    `;
    return;
  }

  if (furnaceRows.length) {
    selfRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(furnaceDisplayName(profile, "当前角色"))}</strong>
          <span class="badge badge--normal">主人</span>
        </div>
        <p>你名下共有 ${escapeHtml(furnaceRows.length)} 名炉鼎，每天可对每名炉鼎采补一次。</p>
        <div class="item-tags">
          <span class="tag">采补比例 ${escapeHtml(harvestPercent)}%</span>
          <span class="tag">炉鼎数量 ${escapeHtml(furnaceRows.length)}</span>
          <span class="tag">今日可操作 ${escapeHtml(furnaceRows.filter((item) => item.can_harvest_today).length)}</span>
        </div>
        <p class="muted">采补收益会按主人与炉鼎各自当前境界门槛折算。</p>
      </article>
    `;
    rosterRoot.innerHTML = furnaceRows.map((item) => {
      const available = Boolean(item.can_harvest_today);
      const gain = Number(item.estimated_harvest_gain || 0);
      const loss = Number(item.estimated_harvest_loss || 0);
      const reason = available ? "" : fallbackReason(item.harvest_reason, "当前暂不可采补。");
      return `
        <article class="stack-item">
          <div class="stack-item-head">
            <strong>${escapeHtml(furnaceDisplayName(item, item.display_label || `TG ${item.tg || 0}`))}</strong>
            <span class="badge badge--normal">${available ? "今日可采补" : "暂不可采补"}</span>
          </div>
          <p>境界 ${escapeHtml(item.realm_text || `${item.realm_stage || "炼气"}${item.realm_layer || 0}层`)} · 当前修为 ${escapeHtml(item.cultivation ?? 0)}</p>
          <div class="item-tags">
            <span class="tag">抽取比例 ${escapeHtml(item.harvest_percent ?? harvestPercent)}%</span>
            <span class="tag">预计主人 +${escapeHtml(gain)}</span>
            <span class="tag">预计炉鼎 -${escapeHtml(loss)}</span>
          </div>
          ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : `<p>本次可抽取其当前修为 ${escapeHtml(loss)} 点，折算为你 ${escapeHtml(gain)} 点修为。</p>`}
          <div class="inline-action-buttons">
            <button type="button" data-furnace-harvest-target="${escapeHtml(item.tg || 0)}" ${available ? "" : "disabled"}>${available ? "今日采补" : "今日不可采补"}</button>
          </div>
        </article>
      `;
    }).join("");
    return;
  }

  selfRoot.innerHTML = `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(furnaceDisplayName(profile, "当前角色"))}</strong>
        <span class="badge badge--normal">自由身</span>
      </div>
      <p>当前未与任何人形成炉鼎因果，也没有名下炉鼎。</p>
      <div class="item-tags">
        <span class="tag">采补比例 ${escapeHtml(harvestPercent)}%</span>
        <span class="tag">当前状态 自由</span>
      </div>
    </article>
  `;
  rosterRoot.innerHTML = `<article class="stack-item"><strong>暂无可采补对象</strong><p>只有通过炉鼎对决建立关系后，主人才可每天进行一次采补。</p></article>`;
}

const baseRenderProfileWithTitles = renderProfile;
renderProfile = function renderProfileWithTitles(bundle) {
  baseRenderProfileWithTitles(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  ensureSectionState("#title-card", consented);
  if (!consented) {
    syncFoldToolbar();
    return;
  }
  const currentTitleName = bundle.current_title?.name || "未佩戴称号";
  const currentTitleColor = bundle.current_title?.color || "";
  const heroRootPill = document.querySelector("#hero-root-pill");
  if (heroRootPill) {
    heroRootPill.innerHTML = `称号 · ${titleColoredNameHtml(currentTitleName, currentTitleColor)}`;
  }
  const rootText = document.querySelector("#root-text");
  if (rootText) {
    const profile = bundle.profile || {};
    const rootLabel = profile.root_text || profileRootText(profile);
    const rootBonus = Number(profile.root_bonus || 0);
    rootText.innerHTML = `称号：${titleColoredNameHtml(currentTitleName, currentTitleColor)} · 灵根：${escapeHtml(rootLabel)}，五行修正 ${rootBonus >= 0 ? "+" : ""}${escapeHtml(rootBonus)}%`;
  }
  const profileGrid = document.querySelector("#profile-grid");
  if (profileGrid) {
    profileGrid.insertAdjacentHTML(
      "beforeend",
      `<article class="profile-item"><span>当前称号</span><strong>${titleColoredNameHtml(currentTitleName, currentTitleColor)}</strong></article>`
      + `<article class="profile-item"><span>成就解锁</span><strong>${escapeHtml(bundle.achievement_unlocked_count || 0)} / ${escapeHtml(bundle.achievement_total_count || 0)}</strong></article>`
    );
  }
  renderLazyFoldCard("title-card");
  syncFoldToolbar();
};

document.addEventListener("click", async (event) => {
  const equipButton = event.target.closest("[data-title-equip]");
  const clearButton = event.target.closest("[data-title-clear]");
  if (!equipButton && !clearButton) return;
  const button = equipButton || clearButton;
  try {
    await runButtonAction(button, clearButton ? "卸下中..." : "佩戴中...", async () => {
      const titleId = clearButton ? null : Number(equipButton.dataset.titleEquip || 0) || null;
      const payload = await postJson("/plugins/xiuxian/api/title/equip", { title_id: titleId });
      syncActionBundle(payload);
      await popup("称号已更新", clearButton ? "你已经暂时卸下当前称号。" : "修仙名帖上的称号已经切换。");
    });
  } catch (error) {
    await popup("操作失败", normalizeError(error, "称号切换失败。"), "error");
  }
});

const renderTitleAchievementAreaBase = renderTitleAchievementArea;
renderTitleAchievementArea = function renderTitleAchievementAreaEnhanced(bundle) {
  renderTitleAchievementAreaBase(bundle);
  const syncButton = document.querySelector("#title-group-sync-btn");
  const syncHint = document.querySelector("#title-sync-hint");
  const currentTitleName = bundle.current_title?.name || "";
  if (syncHint) {
    syncHint.textContent = currentTitleName
      ? `当前佩戴「${currentTitleName}」，可同步到群成员标签；无需你自己成为管理员。`
      : "请先佩戴称号，再同步到群成员标签。";
  }
  if (syncButton) {
    setDisabled(syncButton, !currentTitleName, currentTitleName ? "" : "当前未佩戴称号");
  }
};

const renderTechniqueAreaBase = renderTechniqueArea;
renderTechniqueArea = function renderTechniqueAreaEnhanced(bundle) {
  renderTechniqueAreaBase(bundle);
  const hint = document.querySelector("#technique-discovery-hint");
  if (!hint) return;
  const owned = Number(bundle.technique_owned_count ?? (bundle.techniques || []).length ?? 0);
  const total = Number(bundle.technique_total_count ?? 0);
  const capacity = Number(bundle.profile?.technique_capacity ?? 0);
  hint.textContent = `已掌握 ${owned}${total ? ` / ${total}` : ""} 门功法，当前最多可启用 ${capacity} 门功法位。功法需要先探索获得，是否切换由你自行决定。`;
};

const renderCraftAreaBase = renderCraftArea;
renderCraftArea = function renderCraftAreaEnhanced(bundle) {
  renderCraftAreaBase(bundle);
  const hint = document.querySelector("#recipe-discovery-hint");
  const synthesisRoot = document.querySelector("#recipe-fragment-synthesis-list");
  const discovered = Number(bundle.recipe_discovered_count ?? (bundle.recipes || []).length ?? 0);
  const total = Number(bundle.recipe_total_count ?? 0);
  if (hint) {
    hint.textContent = `已发现 ${discovered}${total ? ` / ${total}` : ""} 张配方。残页可先参悟成完整配方，再进行炼制。`;
  }
  if (!synthesisRoot) return;
  const syntheses = bundle.recipe_fragment_syntheses || [];
  synthesisRoot.innerHTML = "";
  if (!syntheses.length) {
    synthesisRoot.innerHTML = `<article class="stack-item"><strong>暂无可参悟配方</strong><p>尚未持有对应残页，或相关配方都已掌握。</p></article>`;
    return;
  }
  for (const item of syntheses) {
    const disabled = !item.can_synthesize;
    const reason = disabled ? `缺少 ${item.required_material_name || "残页"}，当前仅有 ${item.owned_quantity || 0} / ${item.required_quantity || 1}。` : "";
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.recipe_name || "未知配方")}</strong>
        <span class="badge badge--normal">${escapeHtml(item.recipe_kind_label || item.recipe_kind || "配方")}</span>
      </div>
      <p>参悟后解锁：${escapeHtml(item.result_item_name || item.result_item?.name || "成品")}</p>
      <div class="info-grid">
        <article class="info-chip">
          <span>所需残页</span>
          <strong>${escapeHtml(item.required_material_name || "残页")} × ${escapeHtml(item.required_quantity || 1)}</strong>
        </article>
        <article class="info-chip">
          <span>当前持有</span>
          <strong>${escapeHtml(item.owned_quantity || 0)}</strong>
        </article>
      </div>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : `<p>残页足够后可直接参悟为完整配方。</p>`}
      <button type="button" data-recipe-synthesis-id="${item.recipe_id}" ${disabled ? "disabled" : ""}>${escapeHtml(disabled ? "残页不足" : "参悟配方")}</button>
    `;
    synthesisRoot.appendChild(card);
  }
};

const renderProfileWithDiscoveriesBase = renderProfile;
renderProfile = function renderProfileWithDiscoveries(bundle) {
  renderProfileWithDiscoveriesBase(bundle);
  if (!bundle?.profile?.consented) return;
  const statusText = document.querySelector("#status-text");
  if (statusText) {
    const name = bundle.profile?.display_name_with_title || bundle.profile?.display_label || "道友";
    statusText.textContent = `${name} 当前已踏入仙途，可展开下方模块继续修炼、探索与经营。`;
  }
  const profileGrid = document.querySelector("#profile-grid");
  if (profileGrid) {
    const activeSets = (bundle.active_artifact_sets || []).filter((item) => item.active);
    const activeSetText = activeSets.length
      ? activeSets.map((item) => artifactSetSummaryText(item)).join("、")
      : "暂无激活";
    const techniqueCount = Number(bundle.technique_owned_count ?? (bundle.techniques || []).length ?? 0);
    profileGrid.insertAdjacentHTML(
      "beforeend",
      `<article class="profile-item"><span>已掌握功法</span><strong>${escapeHtml(techniqueCount)}</strong></article>`
      + `<article class="profile-item"><span>法宝套装</span><strong>${escapeHtml(activeSetText)}</strong></article>`
    );
  }
};

document.querySelector("#title-group-sync-btn")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    await runButtonAction(button, "同步中...", async () => {
      const payload = await postJson("/plugins/xiuxian/api/title/group-sync", {});
      syncActionBundle(payload);
      await popup("同步成功", "当前佩戴称号已同步到群成员标签。若群内未生效，请确认 bot 拥有管理成员标签权限。");
    });
  } catch (error) {
    await popup("同步失败", normalizeError(error, "群成员标签同步失败。"), "error");
  }
});

const renderArtifactListBase = renderArtifactList;
renderArtifactList = function renderArtifactListEnhanced(items, retreating, equipLimit, equippedCount) {
  renderArtifactListBase(items, retreating, equipLimit, equippedCount);
  const root = document.querySelector("#artifact-list");
  if (!root) return;
  root.innerHTML = "";
  const artifactQuery = inventorySearchValue("#artifact-search");
  const rows = sortInventoryRowsByQuality(
    (items || []).filter((row) => inventoryMatches(row.artifact || {}, artifactQuery, ["artifact_set_name", "min_realm_stage"])),
    (row) => row.artifact || {},
    "rarity_level"
  );
  if (!rows.length) {
    root.innerHTML = (items || []).length
      ? `<article class="stack-item"><strong>未找到匹配法宝</strong><p>可按名称、品质、分类、槽位或套装继续检索。</p></article>`
      : `<article class="stack-item"><strong>暂无法宝</strong><p>管理后台发放或在${escapeHtml(officialShopName())}购买后会出现在这里。</p></article>`;
    return;
  }
  for (const row of rows) {
    const item = row.artifact || {};
    const effects = item.resolved_effects || {};
    const disabled = !item.usable || retreating;
    const bindableQuantity = Number(row.unbound_quantity ?? row.quantity ?? 0);
    const unbindableQuantity = Number(row.bound_quantity ?? 0);
    const canBind = bindableQuantity > 0;
    const canUnbind = unbindableQuantity > 0;
    const unbindCost = Number(state.profileBundle?.settings?.equipment_unbind_cost || 0);
    const reason = disabledReason(
      disabled,
      item.unusable_reason,
      retreating ? "闭关期间无法切换法宝" : "当前不满足装备条件"
    );
    const activeSet = item.artifact_set ? artifactSetSummaryText(item.artifact_set) : "无套装";
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(item.name || "未命名法宝")}</strong>
        <span class="badge badge--normal">x${escapeHtml(row.quantity ?? 0)}</span>
      </div>
      ${itemArtworkHtml(item, "artifact")}
      <p>${escapeHtml(item.description || "暂无描述")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(artifactEquipCategoryLabel(item))}</span>
        <span class="tag ${item.artifact_type === "support" ? "support" : ""}">${escapeHtml(item.artifact_type_label || artifactTypeLabel(item.artifact_type))}</span>
        <span class="tag">${escapeHtml(item.equip_slot_label || item.equip_slot || "槽位未定")}</span>
        <span class="tag">${escapeHtml(item.artifact_role_label || item.artifact_role || "定位未定")}</span>
        <span class="tag">${escapeHtml(activeSet)}</span>
        ${qualityBadgeHtml(item.rarity || "凡品", item.quality_color, "tag")}
        ${unbindableQuantity > 0 ? `<span class="tag">已绑定 ${escapeHtml(unbindableQuantity)}</span>` : ""}
        ${bindableQuantity > 0 ? `<span class="tag">未绑定 ${escapeHtml(bindableQuantity)}</span>` : ""}
        ${itemAffixTags(item, effects)}
      </div>
      <p>境界要求：${escapeHtml(item.min_realm_stage ? `${item.min_realm_stage}${item.min_realm_layer}层` : "无限制")}</p>
      ${item.artifact_set ? `<p>套装加成：${escapeHtml(activeSet)}</p>` : ""}
      <p>可交易：${escapeHtml(row.tradeable_quantity ?? 0)} ｜ 可提交：${escapeHtml(row.consumable_quantity ?? 0)}</p>
      ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
      <div class="inline-action-buttons">
        <button type="button" data-equip-id="${item.id}" ${disabled ? "disabled" : ""}>${escapeHtml(item.action_label || (item.equipped ? "卸下法宝" : "装备法宝"))}</button>
        <button type="button" class="ghost" data-artifact-bind-id="${item.id}" ${canBind ? "" : "disabled"}>绑定1件</button>
        <button type="button" class="ghost" data-artifact-unbind-id="${item.id}" ${canUnbind ? "" : "disabled"}>解绑1件${unbindCost > 0 ? `（${escapeHtml(unbindCost)}灵石）` : ""}</button>
      </div>
    `;
    root.appendChild(card);
  }
};

function sectRequirementSummary(sect = {}) {
  const rows = [];
  if (sect.min_realm_stage) rows.push(`境界 ${sect.min_realm_stage}${sect.min_realm_layer || 1}层`);
  if (Number(sect.min_bone || 0) > 0) rows.push(`根骨 ${sect.min_bone}`);
  if (Number(sect.min_comprehension || 0) > 0) rows.push(`悟性 ${sect.min_comprehension}`);
  if (Number(sect.min_divine_sense || 0) > 0) rows.push(`神识 ${sect.min_divine_sense}`);
  if (Number(sect.min_fortune || 0) > 0) rows.push(`机缘 ${sect.min_fortune}`);
  if (Number(sect.min_charisma || 0) > 0) rows.push(`魅力 ${sect.min_charisma}`);
  if (Number(sect.min_willpower || 0) > 0) rows.push(`心志 ${sect.min_willpower}`);
  if (Number(sect.min_karma || 0) > 0) rows.push(`因果 ${sect.min_karma}`);
  if (Number(sect.min_body_movement || 0) > 0) rows.push(`身法 ${sect.min_body_movement}`);
  if (Number(sect.min_stone || 0) > 0) rows.push(`灵石 ${sect.min_stone}`);
  return rows.join(" · ") || "几乎无门槛";
}

function sectBonusSummary(sect = {}, role = null) {
  const rows = [];
  const attack = Number(sect.attack_bonus || 0) + Number(role?.attack_bonus || 0);
  const defense = Number(sect.defense_bonus || 0) + Number(role?.defense_bonus || 0);
  const duel = Number(sect.duel_rate_bonus || 0) + Number(role?.duel_rate_bonus || 0);
  const cultivation = Number(sect.cultivation_bonus || 0) + Number(role?.cultivation_bonus || 0);
  const fortune = Number(sect.fortune_bonus || 0);
  const movement = Number(sect.body_movement_bonus || 0);
  if (attack) rows.push(`攻击 ${attack > 0 ? "+" : ""}${attack}`);
  if (defense) rows.push(`防御 ${defense > 0 ? "+" : ""}${defense}`);
  if (duel) rows.push(`斗法 ${duel > 0 ? "+" : ""}${duel}%`);
  if (cultivation) rows.push(`修炼 ${cultivation > 0 ? "+" : ""}${cultivation}`);
  if (fortune) rows.push(`机缘 ${fortune > 0 ? "+" : ""}${fortune}`);
  if (movement) rows.push(`身法 ${movement > 0 ? "+" : ""}${movement}`);
  return rows.join(" · ") || "暂无额外加成";
}

renderSectArea = function renderSectAreaEnhanced(bundle) {
  const currentRoot = document.querySelector("#sect-current");
  const listRoot = document.querySelector("#sect-list");
  const treasuryRoot = document.querySelector("#sect-treasury");
  const attendanceNote = document.querySelector("#sect-attendance-note");
  const attendanceButton = document.querySelector("#sect-attendance-btn");
  const salaryButton = document.querySelector("#sect-salary-btn");
  const leaveButton = document.querySelector("#sect-leave-btn");
  const teachButton = document.querySelector("#sect-teach-btn");
  const donateButton = document.querySelector("#sect-donate-btn");
  const teachInput = document.querySelector("#sect-teach-amount");
  const donateKind = document.querySelector("#sect-donate-kind");
  const donateRef = document.querySelector("#sect-donate-ref");
  const donateQuantity = document.querySelector("#sect-donate-quantity");
  if (!currentRoot || !listRoot || !treasuryRoot || !attendanceNote || !attendanceButton || !salaryButton || !leaveButton) return;

  const current = bundle.current_sect;
  const duelLockReason = currentDuelLockReason(bundle);
  leaveButton.textContent = "叛出宗门";
  currentRoot.innerHTML = "";
  treasuryRoot.innerHTML = "";
  renderSectDonationSelect(bundle);

  if (current) {
    const role = current.current_role || null;
    const contribution = Number(bundle.profile?.sect_contribution ?? 0);
    const attendance = current.attendance || {};
    const promotionPreview = current.promotion_preview || null;
    const attendanceText = attendance.done_today
      ? "今日已完成宗门点卯签到。"
      : "今日尚未点卯，可先完成一次宗门签到。";
    const promotionText = promotionPreview
      ? `再获 ${promotionPreview.remaining_contribution || 0} 点贡献可晋升为 ${promotionPreview.next_role_name || promotionPreview.next_role_key || "下一职位"}。`
      : "当前职位已达到自动晋升上限。";
    currentRoot.innerHTML = `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(current.name)}</strong>
          <span class="badge badge--normal">${escapeHtml(current.camp_label || current.camp || "宗门")}</span>
        </div>
        <p>${escapeHtml(current.description || "暂无宗门简介")}</p>
        <div class="item-tags">
          <span class="tag">职位 ${escapeHtml(role?.role_name || "门下弟子")}</span>
          <span class="tag">成员 ${escapeHtml((current.roster || []).length)}</span>
          <span class="tag">贡献 ${escapeHtml(contribution)}</span>
          <span class="tag">月俸 ${escapeHtml(role?.monthly_salary ?? 0)} 灵石</span>
          <span class="tag">${escapeHtml(attendance.done_today ? "今日已签到" : "今日未签到")}</span>
          ${current.entry_technique_name ? `<span class="tag">入门功法 ${escapeHtml(current.entry_technique_name)}</span>` : ""}
        </div>
        <p>宗门加成：${escapeHtml(sectBonusSummary(current, role))}</p>
        <p>${escapeHtml(promotionText)}</p>
        ${current.entry_hint ? `<p>${escapeHtml(current.entry_hint)}</p>` : ""}
      </article>
    `;
    attendanceNote.textContent = `${attendanceText}${attendance.last_at ? ` 上次点卯：${formatDate(attendance.last_at)}。` : ""}`;
    const attendanceBlockedReason = attendance.done_today
      ? "今日已完成宗门签到。"
      : (duelLockReason || "");
    const sectActionBlockedReason = duelLockReason || "";
    setDisabled(salaryButton, Boolean(duelLockReason), duelLockReason);
    setDisabled(leaveButton, Boolean(duelLockReason), duelLockReason);
    setDisabled(attendanceButton, Boolean(attendanceBlockedReason), attendanceBlockedReason);
    [teachButton, teachInput, donateButton, donateKind, donateRef, donateQuantity]
      .forEach((element) => setDisabled(element, Boolean(sectActionBlockedReason), sectActionBlockedReason));
    const availableDonationRows = sectDonationRows(donateKind?.value || "material", bundle);
    if (!sectActionBlockedReason && !availableDonationRows.length) {
      setDisabled(donateRef, true, "当前背包没有可提交物品");
      setDisabled(donateButton, true, "当前背包没有可提交物品");
    }

    const treasuryItems = current.treasury_items || [];
    treasuryRoot.innerHTML = treasuryItems.length
      ? treasuryItems.map((row) => `
        <article class="stack-item">
          <div class="stack-item-head">
            <strong>${escapeHtml(row.item_name || row.item?.name || row.item_kind_label || row.item_kind || "物品")}</strong>
            <span class="badge badge--normal">x${escapeHtml(row.quantity || 0)}</span>
          </div>
          <p>${escapeHtml(row.item_kind_label || row.item_kind || "物品")} · ${escapeHtml(row.item?.quality_label || row.item?.rarity || row.item?.quality_feature || "常规物资")}</p>
        </article>
      `).join("")
      : `<article class="stack-item"><strong>宗门宝库暂无物资</strong><p>成员捐入宗门宝库的物资会展示在这里。</p></article>`;
  } else {
    currentRoot.innerHTML = `<article class="stack-item"><strong>暂未加入宗门</strong><p>满足门槛后，即可在下方挑选正邪宗门与入门路线。</p></article>`;
    treasuryRoot.innerHTML = `<article class="stack-item"><strong>宗门宝库未开启</strong><p>加入宗门后才能查看并捐赠宝库物资。</p></article>`;
    attendanceNote.textContent = "尚未加入宗门，当前无法进行宗门点卯签到。";
    [attendanceButton, salaryButton, leaveButton, teachButton, teachInput, donateButton, donateKind, donateRef, donateQuantity]
      .forEach((element) => setDisabled(element, true, "尚未加入宗门"));
  }

  listRoot.innerHTML = "";
  const sects = bundle.sects || [];
  if (!sects.length) {
    listRoot.innerHTML = `<article class="stack-item"><strong>暂无可加入宗门</strong></article>`;
    return;
  }

  for (const sect of sects) {
    const disabled = current?.id === sect.id || !sect.joinable;
    const card = document.createElement("article");
    card.className = "stack-item";
    card.innerHTML = `
      <div class="stack-item-head">
        <strong>${escapeHtml(sect.name)}</strong>
        <span class="badge badge--normal">${escapeHtml(sect.camp_label || sect.camp || "宗门")}</span>
      </div>
      <p>${escapeHtml(sect.description || "暂无简介")}</p>
      <div class="item-tags">
        <span class="tag">${escapeHtml(sectRequirementSummary(sect))}</span>
        <span class="tag">成员 ${escapeHtml(sect.member_count ?? 0)}</span>
        ${sect.entry_technique_name ? `<span class="tag">入门赠 ${escapeHtml(sect.entry_technique_name)}</span>` : ""}
      </div>
      <p>宗门加成：${escapeHtml(sectBonusSummary(sect))}</p>
      ${sect.entry_hint ? `<p>${escapeHtml(sect.entry_hint)}</p>` : ""}
      ${disabled && sect.join_reason ? `<p class="reason-text">${escapeHtml(sect.join_reason)}</p>` : ""}
      <button type="button" data-sect-id="${sect.id}" ${disabled ? "disabled" : ""}>${current?.id === sect.id ? "已加入" : "加入宗门"}</button>
    `;
    listRoot.appendChild(card);
  }
};

function commissionRequirementText(item = {}) {
  if (item.requirement_summary) return item.requirement_summary;
  if (!item.min_realm_stage) return "无门槛";
  return `${item.min_realm_stage}${item.min_realm_layer || 1}层`;
}

function renderCommissionArea(bundle) {
  const root = document.querySelector("#commission-list");
  if (!root) return;
  const commissions = Array.isArray(bundle?.commissions) ? bundle.commissions : [];
  if (!commissions.length) {
    root.innerHTML = `<article class="stack-item"><strong>暂无可承接的坊市委托</strong><p>踏入仙途后，坊市会根据你的境界开放灵石差事。</p></article>`;
    return;
  }

  root.innerHTML = commissions.map((item) => {
    const requirement = commissionRequirementText(item);
    const rewardText = `灵石 ${item.reward_stone_min || 0}-${item.reward_stone_max || 0} · 修为 ${item.reward_cultivation_min || 0}-${item.reward_cultivation_max || 0}`;
    const cooldownText = `${item.cooldown_hours || 0} 小时`;
    const disabled = !item.available;
    const reason = item.available ? "" : fallbackReason(item.reason, "当前暂不可承接该委托。");
    const timeText = item.next_available_at
      ? `下次可接：${formatDate(item.next_available_at)}`
      : (item.last_claimed_at ? `上次完成：${formatDate(item.last_claimed_at)}` : "首次承接无冷却");
    return `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name || "未命名委托")}</strong>
          <span class="badge badge--normal">${disabled ? "冷却/未解锁" : "可接取"}</span>
        </div>
        <p>${escapeHtml(item.summary || item.description || "暂无说明")}</p>
        <div class="item-tags">
          <span class="tag">门槛 ${escapeHtml(requirement)}</span>
          <span class="tag">冷却 ${escapeHtml(cooldownText)}</span>
          <span class="tag">${escapeHtml(rewardText)}</span>
        </div>
        ${item.description ? `<p>${escapeHtml(item.description)}</p>` : ""}
        <p>${escapeHtml(timeText)}</p>
        ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
        <button type="button" data-commission-key="${escapeHtml(item.key || "")}" ${disabled ? "disabled" : ""}>${disabled ? "暂不可接" : "承接委托"}</button>
      </article>
    `;
  }).join("");
}

const renderProfileWithCommissionBoardBase = renderProfile;
renderProfile = function renderProfileWithCommissionBoard(bundle) {
  renderProfileWithCommissionBoardBase(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  ensureSectionState("#furnace-card", consented);
  ensureSectionState("#mentorship-card", consented);
  ensureSectionState("#commission-card", consented);
  if (!consented) {
    syncFoldToolbar();
    return;
  }
  renderLazyFoldCard("furnace-card");
  renderLazyFoldCard("mentorship-card");
  renderLazyFoldCard("commission-card");
  syncFoldToolbar();
};

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-furnace-harvest-target]");
  if (!button || button.disabled) return;

  try {
    const targetTg = Number(button.dataset.furnaceHarvestTarget || 0);
    const payload = await runButtonAction(button, "采补中…", () => postJson("/plugins/xiuxian/api/furnace/harvest", {
      target_tg: targetTg,
    }));
    applyReturnedBundle(payload);
    const result = payload.result || {};
    const lines = [String(result.message || "本次采补已完成。").trim()];
    lines.push(`主人修为 +${Number(result.master_gain || 0)}`);
    lines.push(`炉鼎当前修为 -${Number(result.furnace_loss || 0)}`);
    if (Array.isArray(result.upgraded_layers) && result.upgraded_layers.length) {
      lines.push(`层数提升：${result.upgraded_layers.map((layer) => `${layer}层`).join("、")}`);
    }
    setStatus(result.message || "采补完成。", "success");
    await popup("采补完成", lines.join("\n"));
  } catch (error) {
    const message = normalizeError(error, "采补炉鼎失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

function farmStatusBadgeClass(status) {
  if (status === "ready") return "badge badge--normal";
  if (status === "overdue") return "badge badge--danger";
  if (status === "growing") return "badge badge--pending";
  return "badge badge--unknown";
}

function formatCountdownSeconds(seconds) {
  const totalSeconds = Math.max(Number(seconds || 0), 0);
  if (totalSeconds < 60) return "不到 1 分钟";
  const totalMinutes = Math.ceil(totalSeconds / 60);
  if (totalMinutes < 60) return `${totalMinutes} 分钟`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours < 24) return `${hours} 小时${minutes ? `${minutes} 分钟` : ""}`;
  const days = Math.floor(hours / 24);
  const remainHours = hours % 24;
  return `${days} 天${remainHours ? `${remainHours} 小时` : ""}`;
}

function farmTimingText(plot = {}) {
  if (!plot.unlocked) {
    return plot.locked_reason || plot.unlock_requirement_text || "满足条件后可开垦该地块。";
  }
  if (!plot.occupied) {
    return "当前空置，可在上方选择灵种后播种。";
  }
  if (plot.status === "growing") {
    return `距离成熟约 ${formatCountdownSeconds(plot.seconds_until_mature)}。`;
  }
  if (plot.status === "ready") {
    return `已成熟，建议在 ${formatDate(plot.harvest_deadline_at)} 前收获。`;
  }
  if (plot.status === "overdue") {
    return `已错过最佳采收期，继续拖延会持续减产。`;
  }
  return "灵药状态稳定，可继续观察。";
}

function renderFarmArea(bundle) {
  const summaryRoot = document.querySelector("#farm-summary");
  const catalogRoot = document.querySelector("#farm-material-catalog");
  const plotRoot = document.querySelector("#farm-plot-list");
  const slotSelect = document.querySelector("#farm-slot-select");
  const materialSelect = document.querySelector("#farm-material-select");
  const hint = document.querySelector("#farm-plant-hint");
  if (!summaryRoot || !catalogRoot || !plotRoot || !slotSelect || !materialSelect || !hint) return;

  summaryRoot.classList.add("farm-summary-grid");
  const farm = bundle?.farm || {};
  const plots = Array.isArray(farm.plots) ? farm.plots : [];
  const materials = Array.isArray(farm.plantable_materials) ? farm.plantable_materials : [];
  const selectedSlot = String(slotSelect.value || (farm.empty_slots || [])[0] || "");
  const selectedMaterial = String(materialSelect.value || (materials.find((item) => item.plantable_now)?.id || ""));

  summaryRoot.innerHTML = `
    <article class="info-chip">
      <span>已开垦地块</span>
      <strong>${escapeHtml(farm.unlocked_count || 0)} / ${escapeHtml(farm.slot_count || plots.length || 0)}</strong>
    </article>
    <article class="info-chip">
      <span>空闲地块</span>
      <strong>${escapeHtml(farm.empty_count || 0)} 块</strong>
    </article>
    <article class="info-chip">
      <span>可收获</span>
      <strong>${escapeHtml(farm.ready_count || 0)} 块</strong>
    </article>
    <article class="info-chip">
      <span>下一株成熟</span>
      <strong>${escapeHtml(farm.next_mature_at ? formatDate(farm.next_mature_at) : "暂无")}</strong>
    </article>
  `;
  summaryRoot.insertAdjacentHTML(
    "beforeend",
    `<article class="info-chip farm-auto-harvest-chip">
      <span>批量操作</span>
      <button type="button" data-farm-auto-harvest ${Number(farm.ready_count || 0) > 0 ? "" : "disabled"}>
        自动收获${Number(farm.ready_count || 0) > 0 ? ` ${escapeHtml(farm.ready_count || 0)} 块` : ""}
      </button>
    </article>`
  );

  const emptySlots = plots
    .filter((plot) => plot.unlocked && !plot.occupied)
    .map((plot) => ({ value: String(plot.slot_index), label: `${plot.slot_index} 号灵田` }));
  const availableMaterials = materials
    .filter((item) => item.plantable_now)
    .map((item) => ({
      value: String(item.id),
      label: `${item.name} · ${item.seed_price_stone || 0} 灵石 · ${item.growth_label || `${item.growth_minutes || 0} 分钟`}`,
    }));

  setSelectOptions(
    slotSelect,
    emptySlots.length ? emptySlots : [{ value: "", label: "暂无空闲地块" }],
    selectedSlot,
  );
  slotSelect.disabled = !emptySlots.length;
  setSelectOptions(
    materialSelect,
    availableMaterials.length ? availableMaterials : [{ value: "", label: "当前无可播种灵种" }],
    selectedMaterial,
  );
  materialSelect.disabled = !emptySlots.length || !availableMaterials.length;

  if (!plots.length) {
    plotRoot.innerHTML = `<article class="stack-item"><strong>灵田尚未开启</strong><p>踏入仙途后会自动获得基础药圃。</p></article>`;
  } else {
    plotRoot.innerHTML = plots.map((plot) => {
      const plotClass = [
        "stack-item",
        "farm-plot-card",
        plot.status === "ready" ? "is-ready" : "",
        plot.status === "overdue" ? "is-overdue" : "",
        !plot.unlocked ? "is-locked" : "",
      ].filter(Boolean).join(" ");
      const progressBar = plot.occupied ? `
        <div class="farm-progress">
          <span class="farm-progress-bar" style="width:${escapeHtml(Math.max(Math.min(Number(plot.progress_percent || 0), 100), 0))}%"></span>
        </div>
      ` : "";
      const actionButtons = !plot.unlocked ? `
        <div class="inline-action-buttons">
          <button type="button" data-farm-action="unlock" data-farm-slot="${escapeHtml(plot.slot_index)}" ${plot.can_unlock ? "" : "disabled"}>
            解锁地块${plot.unlock_cost_stone ? `（${escapeHtml(plot.unlock_cost_stone)} 灵石）` : ""}
          </button>
        </div>
      ` : plot.occupied ? `
        <div class="inline-action-buttons">
          <button type="button" class="ghost" data-farm-action="water" data-farm-slot="${escapeHtml(plot.slot_index)}" ${plot.can_water ? "" : "disabled"}>浇灌</button>
          <button type="button" class="ghost" data-farm-action="fertilize" data-farm-slot="${escapeHtml(plot.slot_index)}" ${plot.can_fertilize ? "" : "disabled"}>
            施肥${plot.fertilize_cost_stone ? `（${escapeHtml(plot.fertilize_cost_stone)} 灵石）` : ""}
          </button>
          <button type="button" class="ghost" data-farm-action="clear_pest" data-farm-slot="${escapeHtml(plot.slot_index)}" ${plot.can_clear_pest ? "" : "disabled"}>除虫</button>
          <button type="button" data-farm-action="harvest" data-farm-slot="${escapeHtml(plot.slot_index)}" ${plot.can_harvest ? "" : "disabled"}>收获</button>
        </div>
      ` : `<p class="muted">上方选择灵种后，可播种到这块空置灵田。</p>`;
      const tags = [
        plot.occupied ? `基础产量 ${plot.base_yield || 0}` : "空置地块",
        plot.occupied ? `当前预估 ${plot.yield_preview || 0}` : "等待播种",
        ...(plot.care_tags || []),
      ];
      return `
        <article class="${plotClass}">
          <div class="stack-item-head">
            <strong>${escapeHtml(plot.slot_index)} 号灵田${plot.material?.name ? ` · ${escapeHtml(plot.material.name)}` : ""}</strong>
            <span class="${farmStatusBadgeClass(plot.status)}">${escapeHtml(plot.status_label || "状态未知")}</span>
          </div>
          <p>${escapeHtml(farmTimingText(plot))}</p>
          ${plot.occupied ? `<p>可用于：${escapeHtml(plot.recipe_summary || "丹方材料")}</p>` : ""}
          <div class="item-tags">
            ${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
            ${!plot.unlocked && plot.unlock_requirement_text ? `<span class="tag">${escapeHtml(plot.unlock_requirement_text)}</span>` : ""}
          </div>
          ${plot.occupied ? `<p>成熟时间：${escapeHtml(formatDate(plot.mature_at))}</p>` : ""}
          ${plot.occupied ? `<p>最佳采收截止：${escapeHtml(formatDate(plot.harvest_deadline_at))}</p>` : ""}
          ${progressBar}
          ${plot.locked_reason && !plot.unlocked ? `<p class="reason-text">${escapeHtml(plot.locked_reason)}</p>` : ""}
          ${actionButtons}
        </article>
      `;
    }).join("");
  }

  const materialQuery = inventorySearchValue("#farm-material-search");
  const filteredMaterials = materials.filter((item) => textQueryMatches(materialQuery, [
    item.name,
    item.quality_label,
    item.unlock_requirement_text,
    item.recipe_summary,
    item.recipe_names || [],
  ]));

  if (!filteredMaterials.length) {
    catalogRoot.innerHTML = materials.length
      ? `<article class="stack-item"><strong>未找到匹配灵种</strong><p>可按材料名、丹方名或境界要求继续搜索。</p></article>`
      : `<article class="stack-item"><strong>当前没有可种植药材</strong><p>只有真正用于丹药炼制的材料，才会出现在灵田目录里。</p></article>`;
  } else {
    catalogRoot.innerHTML = filteredMaterials.map((item) => `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(item.name)}</strong>
          ${qualityBadgeHtml(item.quality_label || item.quality_level, item.quality_color, "badge badge--normal")}
        </div>
        <p>适用丹方：${escapeHtml(item.recipe_summary || (item.recipe_names || []).join("、") || "暂无")}</p>
        <div class="item-tags">
          <span class="tag">种子 ${escapeHtml(item.seed_price_stone || 0)} 灵石</span>
          <span class="tag">成长 ${escapeHtml(item.growth_label || `${item.growth_minutes || 0} 分钟`)}</span>
          <span class="tag">产量 ${escapeHtml(item.yield_label || `${item.yield_min || 0}-${item.yield_max || 0}`)}</span>
          <span class="tag">${escapeHtml(item.unlock_requirement_text || "入道后即可种植")}</span>
        </div>
        ${item.plantable_now ? "" : `<p class="reason-text">当前境界不足，尚不能种植这味灵药。</p>`}
        ${item.plantable_now && !item.seed_affordable ? `<p class="reason-text">当前灵石不足，播种至少需要 ${escapeHtml(item.seed_price_stone || 0)} 灵石。</p>` : ""}
        <div class="inline-action-buttons">
          <button type="button" class="ghost" data-farm-pick-material="${escapeHtml(item.id)}" ${item.plantable_now && emptySlots.length ? "" : "disabled"}>选作灵种</button>
        </div>
      </article>
    `).join("");
  }

  if (!emptySlots.length) {
    hint.textContent = "当前没有空闲灵田，可先收获成熟作物或开垦新的地块。";
  } else if (!availableMaterials.length) {
    hint.textContent = "你当前境界下暂无可播种灵种，先提升修为或查看下方药材目录。";
  } else {
    hint.textContent = `当前有 ${emptySlots.length} 块空闲灵田，可播种 ${availableMaterials.length} 种丹方材料。`;
  }
}

const renderProfileWithFarmBase = renderProfile;
renderProfile = function renderProfileWithFarm(bundle) {
  renderProfileWithFarmBase(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  ensureSectionState("#farm-card", consented);
  if (!consented) {
    syncFoldToolbar();
    return;
  }
  renderLazyFoldCard("farm-card");
  syncFoldToolbar();
};

const renderProfileWithMarriageBase = renderProfile;
renderProfile = function renderProfileWithMarriage(bundle) {
  renderProfileWithMarriageBase(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  const genderLocked = Boolean(bundle?.capabilities?.gender_required);
  const genderLockReason = String(bundle?.capabilities?.gender_lock_reason || "").trim();
  ensureSectionState("#marriage-card", consented, genderLocked);
  if (!consented) {
    syncFoldToolbar();
    return;
  }

  renderLazyFoldCard("marriage-card");
  const profileGrid = document.querySelector("#profile-grid");
  if (profileGrid) {
    profileGrid.insertAdjacentHTML(
      "beforeend",
      `<article class="profile-item"><span>性别</span><strong>${escapeHtml(bundle?.marriage?.gender_label || "未设置")}</strong></article>`
      + `<article class="profile-item"><span>道侣</span><strong>${escapeHtml(bundle?.marriage?.current_marriage?.spouse_profile?.display_label || "暂无")}</strong></article>`
    );
  }

  if (genderLocked) {
    [
      "#action-card",
      "#exchange-card",
      "#inventory-card",
      "#technique-card",
      "#official-shop-card",
      "#official-recycle-card",
      "#market-card",
      "#auction-card",
      "#leaderboard-card",
      "#sect-card",
      "#task-card",
      "#craft-card",
      "#explore-card",
      "#red-envelope-card",
      "#gift-card",
      "#title-card",
      "#furnace-card",
      "#mentorship-card",
      "#commission-card",
      "#farm-card",
      "#fishing-card",
    ].forEach((selector) => ensureSectionState(selector, false));
    if (genderLockReason) {
      setStatus(genderLockReason, "warning");
    }
  }
  syncFoldToolbar();
};

document.querySelector("#farm-material-search")?.addEventListener("input", () => {
  if (!state.profileBundle?.profile?.consented) return;
  renderFarmArea(state.profileBundle);
});

document.querySelector("#farm-summary")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-farm-auto-harvest]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "收获中…", () => postJson("/plugins/xiuxian/api/farm/auto-harvest", {}));
    applyReturnedBundle(payload);
    const result = payload.result || {};
    const lines = [result.message || "成熟灵田已自动收获。"];
    if (Number(result.total_quantity || 0) > 0) {
      lines.push(`收获总数 ${Number(result.total_quantity || 0)}`);
    }
    if (Number(result.withered_count || 0) > 0) {
      lines.push(`失收地块 ${Number(result.withered_count || 0)}`);
    }
    setStatus(result.message || "自动收获完成。", "success");
    await popup("自动收获完成", lines.join("\n"));
  } catch (error) {
    const message = normalizeError(error, "自动收获失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#farm-material-catalog")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-farm-pick-material]");
  if (!button) return;
  const materialSelect = document.querySelector("#farm-material-select");
  if (!materialSelect) return;
  materialSelect.value = button.dataset.farmPickMaterial || "";
  document.querySelector("#farm-plant-form")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

document.querySelector("#farm-plant-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget?.querySelector("button[type='submit']");
  const slotIndex = Number(document.querySelector("#farm-slot-select")?.value || 0);
  const materialId = Number(document.querySelector("#farm-material-select")?.value || 0);
  if (!button || slotIndex <= 0 || materialId <= 0) {
    const message = "请选择空闲地块和要播种的灵药。";
    setStatus(message, "warning");
    await popup("无法播种", message, "warning");
    return;
  }
  try {
    const payload = await runButtonAction(button, "播种中…", () => postJson("/plugins/xiuxian/api/farm/plant", {
      slot_index: slotIndex,
      material_id: materialId,
    }));
    applyReturnedBundle(payload);
    const result = payload.result || {};
    const lines = [result.message || "灵药已经播入灵田。"];
    if (Number(result.seed_cost_stone || 0) > 0) {
      lines.push(`消耗灵石 ${result.seed_cost_stone}`);
    }
    if (result.mature_at) {
      lines.push(`预计成熟：${formatDate(result.mature_at)}`);
    }
    setStatus(result.message || "播种完成。", "success");
    await popup("播种完成", lines.join("\n"));
  } catch (error) {
    const message = normalizeError(error, "播种灵药失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#farm-plot-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-farm-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.farmAction || "";
  const slotIndex = Number(button.dataset.farmSlot || 0);
  if (slotIndex <= 0) return;

  let path = "";
  let body = { slot_index: slotIndex };
  let title = "灵田操作";
  let pendingText = "处理中…";
  if (action === "unlock") {
    path = "/plugins/xiuxian/api/farm/unlock";
    title = "开垦完成";
    pendingText = "开垦中…";
  } else if (action === "harvest") {
    path = "/plugins/xiuxian/api/farm/harvest";
    title = "收获完成";
    pendingText = "收获中…";
  } else {
    path = "/plugins/xiuxian/api/farm/care";
    body = { ...body, action };
    title = action === "water" ? "浇灌完成" : action === "fertilize" ? "施肥完成" : "除虫完成";
    pendingText = action === "water" ? "浇灌中…" : action === "fertilize" ? "施肥中…" : "除虫中…";
  }

  try {
    const payload = await runButtonAction(button, pendingText, () => postJson(path, body));
    applyReturnedBundle(payload);
    const result = payload.result || {};
    const lines = [result.message || "灵田操作已完成。"];
    if (Number(result.quantity || 0) > 0) {
      lines.push(`收获数量 ${result.quantity}`);
    }
    if (Number(result.stone_cost || 0) > 0) {
      lines.push(`消耗灵石 ${result.stone_cost}`);
    }
    if (Number(result.unlock_cost_stone || 0) > 0) {
      lines.push(`消耗灵石 ${result.unlock_cost_stone}`);
    }
    if (result.mature_at) {
      lines.push(`新的成熟时间：${formatDate(result.mature_at)}`);
    }
    setStatus(result.message || "灵田操作已完成。", "success");
    await popup(title, lines.join("\n"));
  } catch (error) {
    const message = normalizeError(error, "灵田操作失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

function renderFishingArea(bundle) {
  const summaryRoot = document.querySelector("#fishing-summary");
  const listRoot = document.querySelector("#fishing-spot-list");
  const noteRoot = document.querySelector("#fishing-note");
  if (!summaryRoot || !listRoot || !noteRoot) return;

  const fishing = bundle?.fishing || {};
  const spots = Array.isArray(fishing.spots) ? fishing.spots : [];
  noteRoot.textContent = fishing.note || "高品阶物品基础概率更低，机缘会抬升高品掉率。";
  summaryRoot.innerHTML = `
    <article class="info-chip">
      <span>当前机缘</span>
      <strong>${escapeHtml(fishing.effective_fortune || fishing.current_fortune || bundle?.effective_stats?.fortune || bundle?.profile?.fortune || 0)}</strong>
    </article>
    <article class="info-chip">
      <span>可用钓场</span>
      <strong>${escapeHtml(fishing.available_spot_count || 0)} 处</strong>
    </article>
    <article class="info-chip">
      <span>玩法提示</span>
      <strong>高品更稀有</strong>
    </article>
    <article class="info-chip">
      <span>概率关联</span>
      <strong>机缘越高越容易出高品</strong>
    </article>
  `;

  if (!spots.length) {
    listRoot.innerHTML = `<article class="stack-item"><strong>暂无钓场</strong><p>踏入仙途后会开放可用水域。</p></article>`;
    return;
  }

  listRoot.innerHTML = spots.map((spot) => {
    const oddsTags = (spot.odds_preview || []).map((item) => `${item.label} ${item.chance_percent}%`);
    const rewardCards = (spot.reward_preview || []).map((item) => `
      <article class="recipe-source-item">
        <strong>${escapeHtml(item.name || "未知物品")}</strong>
        <p>${escapeHtml(item.kind_label || item.kind || "物品")} · ${escapeHtml(item.quality_label || "凡品")}</p>
      </article>
    `).join("");
    const statusClass = spot.available ? "badge badge--normal" : "badge badge--unknown";
    const reason = spot.available ? "" : (spot.available_reason || "当前还不能在此抛竿。");
    return `
      <article class="stack-item">
        <div class="stack-item-head">
          <strong>${escapeHtml(spot.name || "未命名钓场")}</strong>
          <span class="${statusClass}">${spot.available ? "可抛竿" : "暂不可用"}</span>
        </div>
        <p>${escapeHtml(spot.description || "暂无说明")}</p>
        <div class="item-tags">
          <span class="tag">耗费 ${escapeHtml(spot.cast_cost_stone || 0)} 灵石</span>
          <span class="tag">门槛 ${escapeHtml(spot.requirement_text || "入道后即可")}</span>
          <span class="tag">品阶带 ${escapeHtml(spot.quality_band_label || "未标注")}</span>
          <span class="tag">产出 ${escapeHtml((spot.kind_labels || []).join(" / ") || "物品")}</span>
        </div>
        ${(oddsTags || []).length ? `<div class="item-tags">${oddsTags.map((text) => `<span class="tag">${escapeHtml(text)}</span>`).join("")}</div>` : ""}
        <div class="recipe-source-list">${rewardCards || `<article class="recipe-source-item"><strong>暂无预览</strong><p>此钓场的样本奖励尚未生成。</p></article>`}</div>
        ${reason ? `<p class="reason-text">${escapeHtml(reason)}</p>` : ""}
        <button type="button" data-fishing-spot="${escapeHtml(spot.key || "")}" ${spot.available ? "" : "disabled"}>前往抛竿</button>
      </article>
    `;
  }).join("");
}

const renderProfileWithFishingBase = renderProfile;
renderProfile = function renderProfileWithFishing(bundle) {
  renderProfileWithFishingBase(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  ensureSectionState("#fishing-card", consented);
  if (!consented) {
    syncFoldToolbar();
    return;
  }
  renderLazyFoldCard("fishing-card");
  syncFoldToolbar();
};

document.querySelector("#fishing-spot-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-fishing-spot]");
  if (!button || button.disabled) return;
  const spotKey = button.dataset.fishingSpot || "";
  try {
    const payload = await runButtonAction(
      button,
      "抛竿中…",
      () => postJson("/plugins/xiuxian/api/fishing/cast", { spot_key: spotKey }, { timeoutMs: ACTION_REQUEST_TIMEOUT_MS }),
      { lockKey: "fishing:cast" },
    );
    applyReturnedBundle(payload);
    refreshExternallyMutableSection("inventory-card");
    const result = payload.result || {};
    const rewardName = grantedItemName(result.reward_item) || result.reward_item?.name || "未知物品";
    const lines = [result.message || "你已经顺利完成本次垂钓。"];
    lines.push(`${result.duplicate_converted ? "折算" : "获得"}：${rewardName}${!result.duplicate_converted && Number(result.quantity || 0) > 1 ? ` ×${Number(result.quantity || 0)}` : ""}`);
    lines.push(`类型：${result.reward_kind_label || result.reward_kind || "物品"}`);
    lines.push(`品阶：${result.quality_label || "凡品"}`);
    if (Number(result.cast_cost_stone || 0) > 0) {
      lines.push(`耗费灵石：${Number(result.cast_cost_stone || 0)}`);
    }
    if (Number(result.fortune_used || 0) > 0) {
      lines.push(`本次结算机缘：${Number(result.fortune_used || 0)}`);
    }
    setStatus(result.message || "垂钓完成。", "success");
    await popup("垂钓完成", lines.join("\n"));
  } catch (error) {
    const message = normalizeError(error, "本次抛竿失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

function formatChancePercent(value) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount <= 0) return "0%";
  if (amount < 0.001) return "<0.001%";
  if (amount < 0.01) return `${amount.toFixed(4).replace(/\.?0+$/, "")}%`;
  return `${amount.toFixed(amount >= 10 ? 2 : 3).replace(/\.?0+$/, "")}%`;
}

function gamblingQuantityText(entry = {}) {
  const min = Math.max(Number(entry.quantity_min || 1), 1);
  const max = Math.max(Number(entry.quantity_max || min), min);
  return min === max ? `x${min}` : `x${min}-${max}`;
}

function renderGamblingArea(bundle) {
  const summaryRoot = document.querySelector("#gambling-summary");
  const noteRoot = document.querySelector("#gambling-note");
  const listRoot = document.querySelector("#gambling-pool-list");
  const exchangeInput = document.querySelector("#gambling-exchange-count");
  const openInput = document.querySelector("#gambling-open-count");
  if (!summaryRoot || !noteRoot || !listRoot) return;

  const gambling = bundle?.gambling || {};
  const preview = Array.isArray(gambling.pool_preview) ? gambling.pool_preview : [];
  const exchangeMax = Math.max(Number(gambling.exchange_max_count || 1), 1);
  const openMax = Math.max(Number(gambling.open_max_count || 1), 1);
  if (exchangeInput) {
    exchangeInput.max = String(exchangeMax);
    if (!exchangeInput.value || Number(exchangeInput.value || 0) > exchangeMax) {
      exchangeInput.value = "1";
    }
  }
  if (openInput) {
    openInput.max = String(openMax);
    if (!openInput.value || Number(openInput.value || 0) > openMax) {
      openInput.value = "1";
    }
  }

  summaryRoot.innerHTML = `
    <article class="info-chip">
      <span>持有奇石</span>
      <strong>${escapeHtml(gambling.owned_count || 0)} 枚</strong>
    </article>
    <article class="info-chip">
      <span>兑换价格</span>
      <strong>${escapeHtml(gambling.exchange_cost_stone || 0)} 灵石 / 枚</strong>
    </article>
    <article class="info-chip">
      <span>单次上限</span>
      <strong>兑 ${escapeHtml(exchangeMax)} / 开 ${escapeHtml(openMax)}</strong>
    </article>
    <article class="info-chip">
      <span>当前机缘</span>
      <strong>${escapeHtml(gambling.fortune_value || bundle?.effective_stats?.fortune || bundle?.profile?.fortune || 0)}</strong>
    </article>
  `;
  noteRoot.textContent = `${gambling.fortune_hint || "当前机缘未触发额外稀有加成。"} ${Number(gambling.broadcast_quality_level || 0) > 0 ? `抽到${gambling.broadcast_quality_level}阶及以上奖励时会自动群播。` : ""}`.trim();

  if (!preview.length) {
    listRoot.innerHTML = `<article class="stack-item"><strong>当前赌坊奖池未配置</strong><p>请等待主人在后台配置奖励后再来开启仙界奇石。</p></article>`;
    return;
  }

  listRoot.innerHTML = preview.map((entry) => `
    <article class="stack-item">
      <div class="stack-item-head">
        <strong>${escapeHtml(entry.item_name || "未知物品")}</strong>
        ${qualityBadgeHtml(entry.quality_label || "凡品", entry.quality_color, "badge badge--normal")}
      </div>
      <p>${escapeHtml(entry.item_kind_label || entry.item_kind || "物品")} · 当前概率 ${escapeHtml(formatChancePercent(entry.chance_percent || 0))}</p>
      ${entry.source_summary ? `<p class="muted">掉落途径：${escapeHtml(entry.source_summary)}</p>` : ""}
      <div class="item-tags">
        <span class="tag">掉落数量 ${escapeHtml(gamblingQuantityText(entry))}</span>
        <span class="tag">奇石权重 ${escapeHtml(entry.gambling_weight ?? entry.base_weight ?? 0)}</span>
        <span class="tag">修正权重 ${escapeHtml(Number(entry.effective_weight || 0).toFixed(3).replace(/\.?0+$/, ""))}</span>
      </div>
    </article>
  `).join("");
}

// ---- 个人 Boss 讨伐 ----
const BOSS_DATA_CACHE_TTL_MS = 15000;
let _bossDataCache = null;
let _bossDataPromise = null;

function bossActionResult(payload = {}) {
  if (payload?.result && typeof payload.result === "object") {
    return payload.result;
  }
  return payload && typeof payload === "object" ? payload : {};
}

function fallbackBossData() {
  return { personal: { bosses: [] }, world: { active: false }, ts: 0 };
}

async function fetchBossData({ force = false } = {}) {
  const now = Date.now();
  if (!force && _bossDataCache && now - Number(_bossDataCache.ts || 0) < BOSS_DATA_CACHE_TTL_MS) {
    return _bossDataCache;
  }
  if (_bossDataPromise) return _bossDataPromise;
  _bossDataPromise = (async () => {
    const [personalResult, worldResult] = await Promise.allSettled([
      postJson("/plugins/xiuxian/api/boss/list", {}),
      postJson("/plugins/xiuxian/api/boss/world/status", {}),
    ]);
    const allFailed = personalResult.status === "rejected" && worldResult.status === "rejected";
    if (allFailed && _bossDataCache) return _bossDataCache;
    _bossDataCache = {
      personal: personalResult.status === "fulfilled" ? personalResult.value : (_bossDataCache?.personal || { bosses: [] }),
      world: worldResult.status === "fulfilled" ? worldResult.value : (_bossDataCache?.world || { active: false }),
      ts: Date.now(),
    };
    return _bossDataCache;
  })()
    .catch(() => _bossDataCache || fallbackBossData())
    .finally(() => {
      _bossDataPromise = null;
    });
  return _bossDataPromise;
}

function renderBossData(data) {
  renderBossSummary(data);
  renderBossPersonalTab(data);
  renderBossWorldTab(data);
}

function renderBossLoadingState() {
  const summaryRoot = document.querySelector("#boss-summary");
  const personalNote = document.querySelector("#boss-personal-note");
  const personalList = document.querySelector("#boss-personal-list");
  const worldNote = document.querySelector("#boss-world-note");
  const worldStatus = document.querySelector("#boss-world-status");
  const worldRankings = document.querySelector("#boss-world-rankings");
  if (summaryRoot) {
    summaryRoot.innerHTML = `
      <article class="boss-metric"><span>Boss 数据</span><strong>同步中</strong><small>首次打开时加载</small></article>
      <article class="boss-metric"><span>世界 Boss</span><strong>检测中</strong><small>独立接口刷新</small></article>
    `;
  }
  if (personalNote) personalNote.textContent = "正在读取个人 Boss 列表。";
  if (personalList) personalList.innerHTML = `<article class="stack-item boss-empty-card"><strong>加载中</strong><p>正在同步可挑战目标。</p></article>`;
  if (worldNote) worldNote.textContent = "正在检测世界 Boss 状态。";
  if (worldStatus) worldStatus.innerHTML = `<article class="stack-item boss-empty-card"><strong>加载中</strong><p>正在查看当前是否有世界 Boss 降临。</p></article>`;
  if (worldRankings) worldRankings.innerHTML = "";
}

function bossNumber(value) {
  const number = Number(value || 0);
  if (number >= 100000000) return `${(number / 100000000).toFixed(1).replace(/\.0$/, "")}亿`;
  if (number >= 10000) return `${(number / 10000).toFixed(1).replace(/\.0$/, "")}万`;
  return String(Math.round(number));
}

function bossHpPercent(current, max) {
  const maximum = Math.max(Number(max || 0), 1);
  return Math.max(Math.min(Math.round(Number(current || 0) / maximum * 100), 100), 0);
}

function bossLootCount(boss = {}) {
  return [
    boss.loot_pills_json,
    boss.loot_materials_json,
    boss.loot_artifacts_json,
    boss.loot_talismans_json,
    boss.loot_recipes_json,
    boss.loot_techniques_json,
  ].reduce((total, rows) => total + (Array.isArray(rows) ? rows.length : 0), 0);
}

function bossRewardText(boss = {}) {
  const parts = [];
  const stoneMax = Number(boss.stone_reward_max || 0);
  if (stoneMax > 0) parts.push(`灵石 ${bossNumber(boss.stone_reward_min)}-${bossNumber(stoneMax)}`);
  if (Number(boss.cultivation_reward || 0) > 0) parts.push(`修为 +${bossNumber(boss.cultivation_reward)}`);
  const lootCount = bossLootCount(boss);
  if (lootCount > 0) parts.push(`掉落 ${lootCount} 项`);
  return parts.join(" · ") || "暂无额外奖励";
}

function bossAttemptsUnlimited(boss = {}) {
  return Boolean(boss.daily_attempts_unlimited) || Number(boss.daily_attempt_limit || 0) <= 0;
}

function bossRemainingAttempts(boss = {}) {
  return Math.max(Number(boss.daily_attempts_remaining || 0), 0);
}

function bossAttemptText(boss = {}) {
  if (bossAttemptsUnlimited(boss)) return "不限";
  return `${bossRemainingAttempts(boss)}/${Number(boss.daily_attempt_limit || 0)}`;
}

function renderBossSummary(bossData) {
  const root = document.querySelector("#boss-summary");
  if (!root) return;
  const personal = bossData?.personal || {};
  const world = bossData?.world || {};
  const bosses = Array.isArray(personal.bosses) ? personal.bosses : [];
  const beatenCount = bosses.filter((b) => b.beaten).length;
  const unlockedCount = bosses.filter((b) => b.unlocked).length;
  const hasUnlimitedAttempts = bosses.some((boss) => bossAttemptsUnlimited(boss));
  const remainingAttempts = bosses.reduce((total, boss) => total + bossRemainingAttempts(boss), 0);
  const remainingAttemptText = hasUnlimitedAttempts ? "今日不限次数" : `今日剩余 ${remainingAttempts} 次`;
  root.innerHTML = `
    <article class="boss-metric">
      <span>个人进度</span>
      <strong>${escapeHtml(beatenCount)} / ${escapeHtml(bosses.length)}</strong>
      <small>已征服 Boss</small>
    </article>
    <article class="boss-metric">
      <span>可挑战</span>
      <strong>${escapeHtml(unlockedCount)}</strong>
      <small>${escapeHtml(remainingAttemptText)}</small>
    </article>
    <article class="boss-metric ${world.active ? "is-hot" : ""}">
      <span>世界 Boss</span>
      <strong>${world.active ? "降临中" : "未降临"}</strong>
      <small>${world.active ? "切到世界页参战" : "等待下一次刷新"}</small>
    </article>
  `;
}

function renderBossPersonalTab(bossData) {
  const noteRoot = document.querySelector("#boss-personal-note");
  const listRoot = document.querySelector("#boss-personal-list");
  if (!noteRoot || !listRoot) return;
  const bosses = Array.isArray(bossData?.personal?.bosses) ? bossData.personal.bosses : [];
  noteRoot.textContent = bosses.length ? "选择已解锁 Boss 发起挑战。移动端卡片已压缩关键属性、门票、次数与奖励，减少来回滚动。" : "暂无个人 Boss 数据。";
  if (!bosses.length) {
    listRoot.innerHTML = `<article class="stack-item boss-empty-card"><strong>暂无 Boss</strong><p>天地一片安宁。</p></article>`;
    return;
  }
  listRoot.innerHTML = bosses.map((boss) => {
    const statusLabel = !boss.unlocked ? "境界未至" : boss.beaten ? "已击败" : "可挑战";
    const statusClass = !boss.unlocked ? "badge badge--unknown" : boss.beaten ? "badge badge--safe" : "badge badge--warn";
    const canChallenge = boss.unlocked && (bossAttemptsUnlimited(boss) || bossRemainingAttempts(boss) > 0);
    const disabledReason = !boss.unlocked ? `需达到 ${escapeHtml(boss.realm_stage || "未知境界")}` : !canChallenge ? "今日次数已尽" : "";
    const firstChar = String(boss.name || "Boss").trim().slice(0, 1) || "B";
    const bossEmblem = boss.image_url
      ? itemArtworkHtml(boss, "boss", "boss-art")
      : `<div class="boss-emblem">${escapeHtml(firstChar)}</div>`;
    return `
      <article class="stack-item boss-personal-card ${canChallenge ? "is-ready" : ""}">
        <div class="boss-card-top">
          ${bossEmblem}
          <div class="boss-title-block">
            <strong>${escapeHtml(boss.name || "未命名 Boss")}</strong>
            <span>${escapeHtml(boss.realm_stage || "未知境界")} · 门票 ${escapeHtml(boss.ticket_cost_stone || 0)} 灵石</span>
          </div>
          <span class="${statusClass}">${statusLabel}</span>
        </div>
        <p class="boss-desc">${escapeHtml(boss.description || "暂无描述")}</p>
        <div class="boss-stat-grid">
          <span><small>气血</small><strong>${escapeHtml(bossNumber(boss.qi_blood || boss.hp))}</strong></span>
          <span><small>攻击</small><strong>${escapeHtml(boss.attack_power || 0)}</strong></span>
          <span><small>防御</small><strong>${escapeHtml(boss.defense_power || 0)}</strong></span>
          <span><small>今日</small><strong>${escapeHtml(bossAttemptText(boss))}</strong></span>
        </div>
        <div class="boss-reward-row">
          <span>${escapeHtml(bossRewardText(boss))}</span>
          ${boss.skill_name ? `<span>技能 ${escapeHtml(boss.skill_name)}</span>` : ""}
        </div>
        <button class="boss-action-btn" type="button" data-boss-challenge="${escapeHtml(boss.id || 0)}" ${canChallenge ? "" : "disabled"}>${canChallenge ? "发起挑战" : (boss.unlocked ? "次数已尽" : "境界未至")}</button>
        ${disabledReason ? `<p class="reason-text">${escapeHtml(disabledReason)}</p>` : ""}
      </article>
    `;
  }).join("");
}

function renderBossWorldTab(bossData) {
  const noteRoot = document.querySelector("#boss-world-note");
  const statusRoot = document.querySelector("#boss-world-status");
  const rankingRoot = document.querySelector("#boss-world-rankings");
  if (!noteRoot || !statusRoot || !rankingRoot) return;
  const world = bossData?.world || {};
  if (!world.active) {
    noteRoot.textContent = "当前没有活跃的世界Boss，请静待下次降临。";
    statusRoot.innerHTML = `<article class="stack-item boss-empty-card"><strong>暂无世界 Boss</strong><p>世界 Boss 每 6 小时尝试刷新，降临后会在群内公告。</p></article>`;
    rankingRoot.innerHTML = "";
    return;
  }
  const instance = world.instance || {};
  const boss = world.boss || {};
  const player = world.player_damage || {};
  const cooldown = Number(world.cooldown_seconds_remaining || 0);
  const ranking = Array.isArray(world.ranking) ? world.ranking : [];
  const hpPercent = bossHpPercent(instance.current_hp, instance.max_hp);
  const hpBarColor = hpPercent > 50 ? "var(--success)" : hpPercent > 20 ? "var(--warning)" : "var(--danger)";
  const canAttack = cooldown <= 0 && (instance.status === "active");
  const statusText = instance.status === "settled" ? "已结算" : instance.status === "defeated" ? "已击败" : instance.status === "escaped" ? "已遁走" : "活跃中";

  noteRoot.textContent = `${boss.name || "未知 Boss"} · 状态：${statusText} · 结束时间 ${formatDate(instance.expires_at)}`;
  statusRoot.innerHTML = `
    <article class="stack-item boss-world-card">
      <div class="boss-world-head">
        ${itemArtworkHtml(boss, "boss", "boss-art boss-art--world")}
        <div>
          <strong>${escapeHtml(boss.name || "世界 Boss")}</strong>
          <p>${escapeHtml(boss.description || "全服共伐目标。")}</p>
        </div>
        <span class="badge ${instance.status === "active" ? "badge--warn" : "badge--unknown"}">${statusText}</span>
      </div>
      <div class="hp-bar-wrap boss-hp-bar">
        <div class="hp-bar" style="width:${hpPercent}%; background:${hpBarColor};"></div>
        <span class="hp-bar-text">${escapeHtml(bossNumber(instance.current_hp))} / ${escapeHtml(bossNumber(instance.max_hp))} (${hpPercent}%)</span>
      </div>
      <div class="boss-stat-grid boss-world-stats">
        <span><small>我的伤害</small><strong>${escapeHtml(bossNumber(player.total_damage))}</strong></span>
        <span><small>攻击次数</small><strong>${escapeHtml(player.attack_count || 0)}</strong></span>
        <span><small>冷却</small><strong>${cooldown > 0 ? `${cooldown}秒` : "就绪"}</strong></span>
        <span><small>防御</small><strong>${escapeHtml(boss.defense_power || 0)}</strong></span>
      </div>
      ${instance.status === "active" ? `
      <button class="boss-action-btn" type="button" data-boss-world-attack ${canAttack ? "" : "disabled"}>${canAttack ? "攻击世界 Boss" : (cooldown > 0 ? `冷却中 (${cooldown}秒)` : "不可攻击")}</button>
      ` : ""}
    </article>
  `;

  if (ranking.length) {
    rankingRoot.innerHTML = `
      <article class="stack-item boss-ranking-card">
        <div class="boss-ranking-head">
          <strong>伤害排名</strong>
          <span class="summary-tip">前 10 名</span>
        </div>
        <div class="boss-ranking-list">
          ${ranking.map((r) => {
      const tierBadge = r.tier === "mvp" ? "MVP" : r.tier === "top3" ? "前三" : r.tier === "top10" ? "前十" : "参与";
      return `
            <div class="boss-rank-row">
              <span><strong>#${escapeHtml(r.rank)} ${escapeHtml(tierBadge)}</strong>${escapeHtml(r.display_name || "?")}</span>
              <b>${escapeHtml(bossNumber(r.total_damage))}</b>
            </div>
      `;
    }).join("")}
        </div>
      </article>
    `;
  } else {
    rankingRoot.innerHTML = `<article class="stack-item boss-ranking-card"><strong>暂无伤害记录</strong><p>成为第一个出手的道友。</p></article>`;
  }
}

function renderBossArea(bundle) {
  const consented = Boolean(bundle?.profile?.consented);
  if (!consented) return;
  if (_bossDataCache) renderBossData(_bossDataCache);
  else renderBossLoadingState();
  fetchBossData().then(renderBossData);
}

// Boss action event handlers
document.querySelector("#boss-personal-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-boss-challenge]");
  if (!button || button.disabled) return;
  const bossId = Number(button.dataset.bossChallenge || 0);
  if (!bossId) return;
  try {
    const payload = await runButtonAction(button, "挑战中…", () => postJson("/plugins/xiuxian/api/boss/challenge", { boss_id: bossId }));
    applyReturnedBundle(payload);
    const result = bossActionResult(payload);
    const won = Boolean(result.won);
    const bossName = result.boss?.name || "Boss";
    const lines = [won ? `成功击败【${bossName}】！` : `挑战【${bossName}】失败…`];
    if (result.rewards) {
      if (Number(result.rewards.stone || 0) > 0) lines.push(`获得灵石：${result.rewards.stone}`);
      if (Number(result.rewards.cultivation || 0) > 0) lines.push(`获得修为：${result.rewards.cultivation}`);
      const items = Array.isArray(result.rewards.items) ? result.rewards.items : [];
      items.forEach((item) => {
        const name = item.item?.name || `${item.kind}#${item.ref_id}`;
        lines.push(`获得：${name}${Number(item.quantity || 0) > 1 ? ` ×${item.quantity}` : ""}`);
      });
    }
    const curseText = curseEventText(result.curse_event);
    if (curseText) lines.push(`☠️ ${curseText}`);
    if (result.summary) lines.push("", result.summary);
    setStatus(won ? `击败${bossName}！` : `挑战${bossName}失败`, won ? "success" : "warn");
    await popup(won ? "讨伐胜利" : "讨伐失败", lines.join("\n"));
    fetchBossData({ force: true }).then(renderBossData);
  } catch (error) {
    const message = normalizeError(error, "挑战失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#boss-world-status")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-boss-world-attack]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "攻击中…", () => postJson("/plugins/xiuxian/api/boss/world/attack", {}));
    applyReturnedBundle(payload);
    const result = bossActionResult(payload);
    const lines = [
      `对【${result.boss?.name || "Boss"}】造成 ${result.damage_dealt || 0} 点伤害${result.crit ? "（暴击！）" : ""}`,
      `累计伤害：${result.player_total_damage || 0} · 攻击次数：${result.player_attack_count || 0}`,
    ];
    if (result.boss_defeated) {
      lines.push("", "Boss已被击败！奖励已按伤害排名结算。");
    }
    const curseText = curseEventText(result.curse_event);
    if (curseText) lines.push(`☠️ ${curseText}`);
    setStatus(`造成 ${result.damage_dealt || 0} 点伤害`, "success");
    await popup("攻击世界Boss", lines.join("\n"));
    fetchBossData({ force: true }).then(renderBossData);
  } catch (error) {
    const message = normalizeError(error, "攻击失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

// 标签页切换
document.querySelector("#boss-tabs")?.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-boss-tab]");
  if (!tab) return;
  const tabName = tab.dataset.bossTab || "personal";
  document.querySelectorAll("#boss-tabs .tab-btn").forEach((btn) => btn.classList.toggle("is-active", btn === tab));
  const personalPanel = document.querySelector("#boss-personal-panel");
  const worldPanel = document.querySelector("#boss-world-panel");
  if (personalPanel) personalPanel.classList.toggle("hidden", tabName !== "personal");
  if (worldPanel) worldPanel.classList.toggle("hidden", tabName !== "world");
  if (tabName === "world") {
    fetchBossData({ force: true }).then((data) => {
      renderBossSummary(data);
      renderBossWorldTab(data);
    });
  }
});

// 世界 Boss 血量自动刷新（世界标签页可见时每 10 秒更新一次）
let _bossWorldPollTimer = null;
function startBossWorldPolling() {
  stopBossWorldPolling();
  _bossWorldPollTimer = setInterval(() => {
    const bossCard = document.querySelector("#boss-card");
    const worldPanel = document.querySelector("#boss-world-panel");
    if (!bossCard?.open || !worldPanel || worldPanel.classList.contains("hidden")) return;
    fetchBossData({ force: true }).then((data) => {
      renderBossSummary(data);
      renderBossWorldTab(data);
    });
  }, 10000);
}
function stopBossWorldPolling() {
  if (_bossWorldPollTimer) { clearInterval(_bossWorldPollTimer); _bossWorldPollTimer = null; }
}
document.querySelector("#boss-tabs")?.addEventListener("click", () => {
  const worldTab = document.querySelector("[data-boss-tab='world']");
  if (worldTab && worldTab.classList.contains("is-active")) startBossWorldPolling();
  else stopBossWorldPolling();
});

document.querySelector("#boss-card")?.addEventListener("toggle", (event) => {
  if (!event.currentTarget?.open) {
    stopBossWorldPolling();
    return;
  }
  const worldTab = document.querySelector("[data-boss-tab='world']");
  if (worldTab && worldTab.classList.contains("is-active")) startBossWorldPolling();
});

const renderProfileWithBossBase = renderProfile;
renderProfile = function renderProfileWithBoss(bundle) {
  renderProfileWithBossBase(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  const genderLocked = Boolean(bundle?.capabilities?.gender_required);
  const visible = consented && !genderLocked;
  ensureSectionState("#boss-card", visible);
  if (!visible) {
    syncFoldToolbar();
    return;
  }
  renderLazyFoldCard("boss-card");
  syncFoldToolbar();
};

const renderProfileWithGamblingBase = renderProfile;
renderProfile = function renderProfileWithGambling(bundle) {
  renderProfileWithGamblingBase(bundle);
  const consented = Boolean(bundle?.profile?.consented);
  const genderLocked = Boolean(bundle?.capabilities?.gender_required);
  const visible = consented && !genderLocked;
  ensureSectionState("#gambling-card", visible);
  if (!visible) {
    syncFoldToolbar();
    return;
  }

  renderLazyFoldCard("gambling-card");
  syncFoldToolbar();
};

document.querySelector("#commission-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-commission-key]");
  if (!button || button.disabled) return;
  try {
    const payload = await runButtonAction(button, "承接中...", () => postJson("/plugins/xiuxian/api/commission/claim", {
      commission_key: button.dataset.commissionKey || "",
    }));
    const result = payload.commission || {};
    const title = result.name || "坊市委托";
    const stoneGain = Number(result.stone_gain || 0);
    const cultivationGain = Number(result.cultivation_gain || 0);
    const detail = result.detail || "委托已经顺利完成。";
    const growthText = attributeGrowthText(result.attribute_growth || []);
    const curseText = curseEventText(payload.curse_event);
    const message = `${title} 完成，灵石 +${stoneGain}，修为 +${cultivationGain}${growthText ? `，${growthText}` : ""}。${curseText ? ` ${curseText}` : ""}`;
    syncActionBundle(payload);
    setStatus(message, "success");
    await popup("委托完成", `${detail}\n灵石 +${stoneGain}\n修为 +${cultivationGain}${growthText ? `\n${growthText}` : ""}${curseText ? `\n☠️ ${curseText}` : ""}`);
    refreshLeaderboardInBackground(state.leaderboard.kind, state.leaderboard.page);
  } catch (error) {
    const message = normalizeError(error, "承接灵石委托失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.addEventListener("click", async (event) => {
  const requestButton = event.target.closest("[data-marriage-request-action]");
  const dualButton = event.target.closest("[data-marriage-dual-cultivate]");
  const divorceButton = event.target.closest("[data-marriage-divorce]");
  if (!requestButton && !dualButton && !divorceButton) return;

  try {
    if (requestButton) {
      const action = requestButton.dataset.marriageRequestAction || "accept";
      const requestId = Number(requestButton.dataset.marriageRequestId || 0);
      const pendingText = action === "accept" ? "处理中…" : action === "reject" ? "婉拒中…" : "撤回中…";
      const payload = await runButtonAction(requestButton, pendingText, () => postJson("/plugins/xiuxian/api/marriage/request/respond", {
        request_id: requestId,
        action,
      }));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const title = action === "accept" ? "已结为道侣" : action === "reject" ? "已婉拒" : "已撤回";
      setStatus(result.message || title, action === "accept" ? "success" : "warning");
      await popup(title, result.message || "操作已完成。", action === "accept" ? "success" : "warning");
      return;
    }

    if (dualButton) {
      const payload = await runButtonAction(dualButton, "双修中…", () => postJson("/plugins/xiuxian/api/marriage/dual-cultivate", {}));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const lines = [result.message || "本次双修已完成。"];
      lines.push(`你获得修为 +${Number(result.actor_gain || 0)}`);
      lines.push(`道侣获得修为 +${Number(result.spouse_gain || 0)}`);
      lines.push(`缘分 +${Number(result.bond_gain || 0)}`);
      setStatus(result.message || "道侣双修完成。", "success");
      await popup("双修完成", lines.join("\n"));
      return;
    }

    if (divorceButton) {
      const payload = await runButtonAction(divorceButton, "分家中…", () => postJson("/plugins/xiuxian/api/marriage/divorce", {}));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const lines = [result.message || "双方已经和离。"];
      lines.push(`${result.husband_name || "男方"} 灵石 ${Number(result.husband_stone || 0)}`);
      lines.push(`${result.wife_name || "女方"} 灵石 ${Number(result.wife_stone || 0)}`);
      setStatus(result.message || "和离分家已完成。", "warning");
      await popup("和离分家", lines.join("\n"), "warning");
    }
  } catch (error) {
    const message = normalizeError(error, "姻缘操作失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.addEventListener("click", async (event) => {
  const requestButton = event.target.closest("[data-mentorship-request-action]");
  const teachButton = event.target.closest("[data-mentorship-teach]");
  const consultButton = event.target.closest("[data-mentorship-consult]");
  const graduateButton = event.target.closest("[data-mentorship-graduate-target]");
  const dissolveButton = event.target.closest("[data-mentorship-dissolve-target]");
  if (!requestButton && !teachButton && !consultButton && !graduateButton && !dissolveButton) return;

  try {
    if (requestButton) {
      const action = requestButton.dataset.mentorshipRequestAction || "accept";
      const requestId = Number(requestButton.dataset.mentorshipRequestId || 0);
      const pendingText = action === "accept" ? "处理中…" : action === "reject" ? "婉拒中…" : "撤回中…";
      const payload = await runButtonAction(requestButton, pendingText, () => postJson("/plugins/xiuxian/api/mentorship/request/respond", {
        request_id: requestId,
        action,
      }));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const title = action === "accept" ? "师徒已结成" : action === "reject" ? "已婉拒" : "已撤回";
      setStatus(result.message || title, action === "accept" ? "success" : "warning");
      await popup(title, result.message || "操作已完成。", action === "accept" ? "success" : "warning");
      return;
    }

    if (teachButton) {
      const discipleTg = Number(teachButton.dataset.mentorshipTeach || 0);
      const payload = await runButtonAction(teachButton, "传道中…", () => postJson("/plugins/xiuxian/api/mentorship/teach", {
        disciple_tg: discipleTg,
      }));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const growthText = attributeGrowthText(result.attribute_growth || [], "额外感悟");
      const message = result.message || `本次传道已完成，弟子修为 +${result.disciple_gain || 0}。`;
      setStatus(message, "success");
      await popup(
        "传道完成",
        `${message}\n师徒缘 +${result.bond_gain || 0}${growthText ? `\n${growthText}` : ""}`,
      );
      return;
    }

    if (consultButton) {
      const payload = await runButtonAction(consultButton, "问道中…", () => postJson("/plugins/xiuxian/api/mentorship/consult", {}));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const growthText = attributeGrowthText(result.attribute_growth || [], "额外领悟");
      const message = result.message || `本次问道已完成，修为 +${result.disciple_gain || 0}。`;
      setStatus(message, "success");
      await popup(
        "问道完成",
        `${message}\n师徒缘 +${result.bond_gain || 0}${growthText ? `\n${growthText}` : ""}`,
      );
      return;
    }

    if (graduateButton) {
      const targetTg = Number(graduateButton.dataset.mentorshipGraduateTarget || 0);
      const payload = await runButtonAction(graduateButton, "出师中…", () => postJson("/plugins/xiuxian/api/mentorship/graduate", {
        target_tg: targetTg,
      }));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      const titleRewards = (result.title_rewards || [])
        .map((item) => item?.title?.name)
        .filter(Boolean)
        .join("、");
      const message = result.message || "本段师徒传承已正式完成。";
      setStatus(message, "success");
      await popup(
        "正式出师",
        `${message}\n师尊修为 +${result.mentor_gain || 0}\n弟子修为 +${result.disciple_gain || 0}${titleRewards ? `\n称号：${titleRewards}` : ""}`,
      );
      return;
    }

    if (dissolveButton) {
      const targetTg = Number(dissolveButton.dataset.mentorshipDissolveTarget || 0);
      const payload = await runButtonAction(dissolveButton, "处理中…", () => postJson("/plugins/xiuxian/api/mentorship/dissolve", {
        target_tg: targetTg,
      }));
      applyReturnedBundle(payload);
      const result = payload.result || {};
      setStatus(result.message || "师徒关系已解除。", "warning");
      await popup("关系已解除", result.message || "师徒关系已解除。", "warning");
    }
  } catch (error) {
    const message = normalizeError(error, "师徒操作失败。");
    setStatus(message, "error");
    await popup("操作失败", message, "error");
  }
});

document.querySelector("#wiki-card")?.addEventListener("toggle", (event) => {
  if (!event.currentTarget?.open) return;
  ensureWikiBundle()
    .then(() => renderWikiArea())
    .catch(() => null);
});

document.querySelector("#wiki-search")?.addEventListener("input", (event) => {
  state.wikiSearchQuery = String(event.target?.value || "").trim();
  ensureWikiBundle().catch(() => null);
  renderWikiArea();
});

document.querySelector("#wiki-filter-row")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-wiki-filter]");
  if (!button) return;
  state.wikiFilter = button.dataset.wikiFilter || "all";
  ensureWikiBundle().catch(() => null);
  renderWikiArea();
});

document.querySelector("#wiki-featured-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-wiki-entry]");
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  event.stopPropagation();
  button.blur?.();
  await openWikiEntry(button.dataset.wikiEntry || "");
});

document.querySelector("#wiki-result-list")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-wiki-entry]");
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  event.stopPropagation();
  button.blur?.();
  await openWikiEntry(button.dataset.wikiEntry || "");
});

loadStoredWebAuth();
setupAuthPanel();
setupFoldToolbar();
setupMobileInteractionPolish();
setupBottomNavLayout();

bootstrap().catch(async (error) => {
  const message = normalizeError(error, "修仙面板初始化失败。");
  setStatus(message, "error");
  await popup("初始化失败", message, "error");
});

// --- 卡片排序按钮 ---
const boardGrid = document.querySelector(".board-grid");
if (boardGrid) {
  const cards = Array.from(boardGrid.querySelectorAll(".fold-card"));
  cards.forEach(card => {
    const summary = card.querySelector(".fold-summary");
    if (summary) {
      const controls = document.createElement("div");
      controls.className = "card-sort-controls";
      
      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "ghost card-up";
      upBtn.innerHTML = "↑上移";
      upBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); moveCard(card, -1); };

      const downBtn = document.createElement("button");
      downBtn.type = "button";
      downBtn.className = "ghost card-down";
      downBtn.innerHTML = "↓下移";
      downBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); moveCard(card, 1); };

      controls.appendChild(upBtn);
      controls.appendChild(downBtn);
      
      const titleDiv = summary.querySelector("div");
      if (titleDiv) {
        titleDiv.appendChild(controls);
      }
    }
  });

  const savedOrder = localStorage.getItem("xiuxian_layout_order");
  if (savedOrder) {
    try {
      const orderIds = JSON.parse(savedOrder);
      const cardMap = new Map();
      cards.forEach(card => cardMap.set(card.id, card));
      
      orderIds.forEach(id => {
        if (cardMap.has(id)) {
          boardGrid.appendChild(cardMap.get(id));
          cardMap.delete(id);
        }
      });
      cardMap.forEach(card => boardGrid.appendChild(card));
    } catch (e) {
      console.error("Failed to restore layout order", e);
    }
  }

  window.moveCard = (card, direction) => {
    const index = Array.from(boardGrid.children).indexOf(card);
    if (direction === -1 && index > 0) {
      boardGrid.insertBefore(card, boardGrid.children[index - 1]);
    } else if (direction === 1 && index < boardGrid.children.length - 1) {
      boardGrid.insertBefore(card, boardGrid.children[index + 2]);
    }
    
    const newOrder = Array.from(boardGrid.querySelectorAll(".fold-card"))
      .map(c => c.id).filter(Boolean);
    localStorage.setItem("xiuxian_layout_order", JSON.stringify(newOrder));
    setupFoldToolbar();
  };
}

// --- 悬浮操作按钮（管理入口） ---
const fabAdmin = document.getElementById("fab-admin");

if (fabAdmin) {
  const observer = new MutationObserver(() => {
    const heroAdmin = document.getElementById("hero-admin-entry");
    if (heroAdmin && !heroAdmin.classList.contains("hidden")) {
      fabAdmin.classList.remove("hidden");
    } else {
      fabAdmin.classList.add("hidden");
    }
  });
  const heroAdmin = document.getElementById("hero-admin-entry");
  if (heroAdmin) {
    observer.observe(heroAdmin, { attributes: true, attributeFilter: ["class"] });
    if (!heroAdmin.classList.contains("hidden")) {
      fabAdmin.classList.remove("hidden");
    }
  }

  fabAdmin.addEventListener("click", () => {
    const adminBtn = document.getElementById("open-admin-panel");
    if (adminBtn) adminBtn.click();
  });
}

function renderGroupedCards(root, cardsHtmlArray, groupingFn, { foldNamespace = "", defaultOpen = false } = {}) {
  if (cardsHtmlArray.length <= 5) {
    cardsHtmlArray.forEach(({card}) => root.appendChild(card));
    return;
  }
  const groups = new Map();
  cardsHtmlArray.forEach(({card, item}) => {
    const key = groupingFn(item) || "其他";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(card);
  });
  
  if (groups.size === 1) {
    cardsHtmlArray.forEach(({card}) => root.appendChild(card));
    return;
  }
  
  groups.forEach((cards, key) => {
    const details = document.createElement("details");
    details.className = "mini-fold";
    bindPersistentFoldState(details, foldStateKey(foldNamespace || root?.id || "group", key), { defaultOpen });
    details.innerHTML = `<summary class="mini-fold-summary"><h3>${escapeHtml(key)} (${cards.length})</h3><span class="summary-tip">折叠分组</span></summary>`;
    const body = document.createElement("div");
    body.className = "mini-fold-body stack-list";
    cards.forEach(c => body.appendChild(c));
    details.appendChild(body);
    root.appendChild(details);
  });
}

// --- 回到顶部悬浮按钮 ---
const fabToTop = document.querySelector("#fab-totop");
if (fabToTop) {
  const syncFabToTop = () => {
    if (currentPageScrollTop() > 300) {
      fabToTop.classList.remove("hidden");
    } else {
      fabToTop.classList.add("hidden");
    }
  };
  watchPageScroll(syncFabToTop);
  syncFabToTop();
  fabToTop.addEventListener("click", () => {
    scrollPageToTop({ behavior: "smooth" });
  });
}
