const storageKey = "echo-admin-token";
const DEFAULT_BACK_PATH = "/miniapp";

const LEVEL_META = {
  a: {
    code: "a",
    text: "白名单用户",
    shortText: "白名单",
    description: "主人亲自盖章的小宝贝，享有更稳定线路与更完整的观影体验。",
    tone: "vip"
  },
  b: {
    code: "b",
    text: "正常用户",
    shortText: "正常",
    description: "已领取观影资格的小可爱，可以正常解锁日常观影体验。",
    tone: "normal"
  },
  c: {
    code: "c",
    text: "已封禁用户",
    shortText: "已封禁",
    description: "当前已被禁用，需要主人处理后才能恢复。",
    tone: "danger"
  },
  d: {
    code: "d",
    text: "未注册用户",
    shortText: "未注册",
    description: "仅录入了账号信息，还没有有效的 Emby 账号。",
    tone: "pending"
  }
};

const UNKNOWN_LEVEL = {
  code: "?",
  text: "未知状态",
  shortText: "未知",
  description: "系统无法识别这个等级，请检查数据。",
  tone: "unknown"
};

const tgApp = window.Telegram?.WebApp || null;
const tgBackButton = tgApp?.BackButton || null;
const backState = {
  fallbackPath: DEFAULT_BACK_PATH,
  returnTo: "",
  referrerPath: ""
};

const state = {
  page: 1,
  pageSize: 20,
  query: "",
  summary: null,
  selectedTg: null,
  selectedUser: null,
  codesPage: 1,
  codesPageSize: 20,
  codeStatus: "all",
  visibleCodes: [],
  selectedCodes: new Set(),
  inviteBundle: null,
  selectedInviteCredits: new Set(),
  selectedInviteOpenCredits: new Set(),
  inviteSearchQuery: "",
  inviteGroupPage: 1,
  inviteOpenPage: 1,
  invitePageSize: 20,
  visibleUsers: [],
  moderationChats: [],
  selectedModerationChatId: null,
  moderationMembers: [],
  selectedModerationTarget: null,
  moderationWarnings: [],
  moderationSearchQuery: "",
  botAccessBlocks: [],
  userBatchPreview: null,
  token: localStorage.getItem(storageKey) || "",
  authMode: null,
  telegramInitData: tgApp?.initData || "",
  telegramUser: tgApp?.initDataUnsafe?.user || null
};

const refs = {
  adminStatus: document.querySelector("#admin-status"),
  authTitle: document.querySelector("#auth-title"),
  authStatus: document.querySelector("#auth-status"),
  authModePill: document.querySelector("#auth-mode-pill"),
  selectedUserPill: document.querySelector("#selected-user-pill"),
  jumpEditorButton: document.querySelector("#jump-editor-button"),
  pageBackButton: document.querySelector("#page-back-button"),
  tokenPanel: document.querySelector("#token-panel"),
  tokenForm: document.querySelector("#token-form"),
  tokenInput: document.querySelector("#admin-token"),
  editorStatus: document.querySelector("#editor-status"),
  pageLabel: document.querySelector("#page-label"),
  userList: document.querySelector("#user-list"),
  codeList: document.querySelector("#code-list"),
  codeResult: document.querySelector("#code-create-result"),
  codeResultTitle: document.querySelector("#code-create-result-title"),
  codeResultMeta: document.querySelector("#code-create-result-meta"),
  codeOutput: document.querySelector("#code-create-output"),
  codeCreateForm: document.querySelector("#code-create-form"),
  codeCreateSubmit: document.querySelector("#code-create-submit"),
  codeCreateCopy: document.querySelector("#code-create-copy"),
  codeCreateSuffixMode: document.querySelector("#code-create-suffix-mode"),
  codeCreateSuffixText: document.querySelector("#code-create-suffix-text"),
  codeStatusButtons: [...document.querySelectorAll("[data-code-status]")],
  codeSelectPage: document.querySelector("#codes-select-page"),
  codeClearSelection: document.querySelector("#codes-clear-selection"),
  codeDeleteSelected: document.querySelector("#codes-delete-selected"),
  codePrevPage: document.querySelector("#codes-prev-page"),
  codeNextPage: document.querySelector("#codes-next-page"),
  codePageLabel: document.querySelector("#codes-page-label"),
  inviteSettingsForm: document.querySelector("#invite-settings-form"),
  inviteEnabled: document.querySelector("#invite-enabled"),
  inviteTargetChatId: document.querySelector("#invite-target-chat-id"),
  inviteExpireHours: document.querySelector("#invite-expire-hours"),
  inviteAccountOpenDays: document.querySelector("#invite-account-open-days"),
  inviteGroupVerificationEnabled: document.querySelector("#invite-group-verification-enabled"),
  inviteChannelVerificationEnabled: document.querySelector("#invite-channel-verification-enabled"),
  inviteSettingsSave: document.querySelector("#invite-settings-save"),
  inviteSettingsStatus: document.querySelector("#invite-settings-status"),
  inviteSearchForm: document.querySelector("#invite-search-form"),
  inviteSearchInput: document.querySelector("#invite-search-input"),
  inviteSearchSubmit: document.querySelector("#invite-search-submit"),
  inviteQualificationForm: document.querySelector("#invite-qualification-form"),
  inviteQualificationOwner: document.querySelector("#invite-qualification-owner"),
  inviteQualificationType: document.querySelector("#invite-qualification-type"),
  inviteQualificationEnabled: document.querySelector("#invite-qualification-enabled"),
  inviteQualificationReason: document.querySelector("#invite-qualification-reason"),
  inviteQualificationSubmit: document.querySelector("#invite-qualification-submit"),
  inviteOpenGrantForm: document.querySelector("#invite-open-grant-form"),
  inviteOpenGrantTg: document.querySelector("#invite-open-grant-tg"),
  inviteOpenGrantDays: document.querySelector("#invite-open-grant-days"),
  inviteOpenGrantNote: document.querySelector("#invite-open-grant-note"),
  inviteOpenGrantUseSelected: document.querySelector("#invite-open-grant-use-selected"),
  inviteOpenGrantSubmit: document.querySelector("#invite-open-grant-submit"),
  inviteOpenGrantStatus: document.querySelector("#invite-open-grant-status"),
  inviteOpenCreateForm: document.querySelector("#invite-open-create-form"),
  inviteOpenCreateInviter: document.querySelector("#invite-open-create-inviter"),
  inviteOpenCreateInvitee: document.querySelector("#invite-open-create-invitee"),
  inviteOpenCreateNote: document.querySelector("#invite-open-create-note"),
  inviteOpenCreateSubmit: document.querySelector("#invite-open-create-submit"),
  inviteOpenCreditList: document.querySelector("#invite-open-credit-list"),
  inviteOpenRecordList: document.querySelector("#invite-open-record-list"),
  inviteOpenCreditSelectPage: document.querySelector("#invite-open-credit-select-page"),
  inviteOpenCreditClearSelection: document.querySelector("#invite-open-credit-clear-selection"),
  inviteOpenCreditDeleteSelected: document.querySelector("#invite-open-credit-delete-selected"),
  inviteOpenPrevPage: document.querySelector("#invite-open-prev-page"),
  inviteOpenNextPage: document.querySelector("#invite-open-next-page"),
  inviteOpenPageLabel: document.querySelector("#invite-open-page-label"),
  inviteGrantForm: document.querySelector("#invite-grant-form"),
  inviteGrantTg: document.querySelector("#invite-grant-tg"),
  inviteGrantCount: document.querySelector("#invite-grant-count"),
  inviteGrantNote: document.querySelector("#invite-grant-note"),
  inviteGrantUseSelected: document.querySelector("#invite-grant-use-selected"),
  inviteGrantSubmit: document.querySelector("#invite-grant-submit"),
  inviteGrantStatus: document.querySelector("#invite-grant-status"),
  inviteCreditList: document.querySelector("#invite-credit-list"),
  inviteRecordList: document.querySelector("#invite-record-list"),
  inviteCreditSelectPage: document.querySelector("#invite-credit-select-page"),
  inviteCreditClearSelection: document.querySelector("#invite-credit-clear-selection"),
  inviteCreditDeleteSelected: document.querySelector("#invite-credit-delete-selected"),
  inviteRefresh: document.querySelector("#invite-refresh"),
  inviteGroupPrevPage: document.querySelector("#invite-group-prev-page"),
  inviteGroupNextPage: document.querySelector("#invite-group-next-page"),
  inviteGroupPageLabel: document.querySelector("#invite-group-page-label"),
  autoUpdateForm: document.querySelector("#auto-update-form"),
  autoUpdateSave: document.querySelector("#auto-update-save"),
  autoUpdateStatus: document.querySelector("#auto-update-status"),
  autoUpdateGitRepo: document.querySelector("#auto-update-git-repo"),
  autoUpdateDockerImage: document.querySelector("#auto-update-docker-image"),
  autoUpdateComposeService: document.querySelector("#auto-update-compose-service"),
  autoUpdateContainerName: document.querySelector("#auto-update-container-name"),
  autoUpdateInterval: document.querySelector("#auto-update-interval"),
  autoUpdateEnabledText: document.querySelector("#update-enabled-text"),
  autoUpdateLastChecked: document.querySelector("#update-last-checked"),
  autoUpdateLastStatus: document.querySelector("#update-last-status"),
  autoUpdateCommitSha: document.querySelector("#update-commit-sha"),
  autoUpdateNote: document.querySelector("#update-note"),
  migrationExportButton: document.querySelector("#migration-export-button"),
  migrationImportForm: document.querySelector("#migration-import-form"),
  migrationImportFile: document.querySelector("#migration-import-file"),
  migrationRestoreConfig: document.querySelector("#migration-restore-config"),
  migrationRestartAfterImport: document.querySelector("#migration-restart-after-import"),
  migrationImportSubmit: document.querySelector("#migration-import-submit"),
  migrationNote: document.querySelector("#migration-note"),
  pluginList: document.querySelector("#plugin-list"),
  pluginImportForm: document.querySelector("#plugin-import-form"),
  pluginImportFile: document.querySelector("#plugin-import-file"),
  pluginImportEnabled: document.querySelector("#plugin-import-enabled"),
  pluginImportReplace: document.querySelector("#plugin-import-replace"),
  pluginImportSubmit: document.querySelector("#plugin-import-submit"),
  botBlockForm: document.querySelector("#bot-block-form"),
  botBlockTg: document.querySelector("#bot-block-tg"),
  botBlockUsername: document.querySelector("#bot-block-username"),
  botBlockNote: document.querySelector("#bot-block-note"),
  botBlockUseSelected: document.querySelector("#bot-block-use-selected"),
  botBlockSubmit: document.querySelector("#bot-block-submit"),
  botBlockStatus: document.querySelector("#bot-block-status"),
  botBlockList: document.querySelector("#bot-block-list"),
  moderationStatus: document.querySelector("#moderation-status"),
  moderationChatForm: document.querySelector("#moderation-chat-form"),
  moderationChatSelect: document.querySelector("#moderation-chat-select"),
  moderationRefresh: document.querySelector("#moderation-refresh"),
  moderationSearchForm: document.querySelector("#moderation-search-form"),
  moderationSearchInput: document.querySelector("#moderation-search-input"),
  moderationSearchSubmit: document.querySelector("#moderation-search-submit"),
  moderationMemberList: document.querySelector("#moderation-member-list"),
  moderationTargetStatus: document.querySelector("#moderation-target-status"),
  moderationTargetDisplay: document.querySelector("#moderation-target-display"),
  moderationMuteMinutes: document.querySelector("#moderation-mute-minutes"),
  moderationTitle: document.querySelector("#moderation-title"),
  moderationMessageId: document.querySelector("#moderation-message-id"),
  moderationReason: document.querySelector("#moderation-reason"),
  moderationMuteButton: document.querySelector("#moderation-mute-button"),
  moderationUnmuteButton: document.querySelector("#moderation-unmute-button"),
  moderationKickButton: document.querySelector("#moderation-kick-button"),
  moderationWarnButton: document.querySelector("#moderation-warn-button"),
  moderationClearWarnButton: document.querySelector("#moderation-clear-warn-button"),
  moderationTitleButton: document.querySelector("#moderation-title-button"),
  moderationPinButton: document.querySelector("#moderation-pin-button"),
  moderationUnpinButton: document.querySelector("#moderation-unpin-button"),
  moderationSettingsForm: document.querySelector("#moderation-settings-form"),
  moderationSettingsStatus: document.querySelector("#moderation-settings-status"),
  moderationWarnThreshold: document.querySelector("#moderation-warn-threshold"),
  moderationWarnAction: document.querySelector("#moderation-warn-action"),
  moderationWarnMuteMinutes: document.querySelector("#moderation-warn-mute-minutes"),
  moderationSettingsSave: document.querySelector("#moderation-settings-save"),
  moderationWarningRefresh: document.querySelector("#moderation-warning-refresh"),
  moderationWarningList: document.querySelector("#moderation-warning-list"),
  whitelistRevokeAll: document.querySelector("#revoke-all-whitelist"),
  whitelistRevokeStatus: document.querySelector("#whitelist-revoke-status"),
  userBatchForm: document.querySelector("#user-batch-form"),
  userBatchScope: document.querySelector("#user-batch-scope"),
  userBatchSourceLevel: document.querySelector("#user-batch-source-level"),
  userBatchAction: document.querySelector("#user-batch-action"),
  userBatchTargetLevel: document.querySelector("#user-batch-target-level"),
  userBatchPreview: document.querySelector("#user-batch-preview"),
  userBatchPreviewButton: document.querySelector("#user-batch-preview-button"),
  userBatchApplyButton: document.querySelector("#user-batch-apply-button"),
  userBatchStatus: document.querySelector("#user-batch-status"),
  embyServiceBadge: document.querySelector("#emby-service-badge"),
  embyServiceToggle: document.querySelector("#emby-service-toggle"),
  embyServiceStatus: document.querySelector("#emby-service-status"),
  levelLegend: document.querySelector("#level-legend"),
  prevPage: document.querySelector("#prev-page"),
  nextPage: document.querySelector("#next-page"),
  revokeAllWhitelist: document.querySelector("#revoke-all-whitelist"),
  saveUser: document.querySelector("#save-user"),
  navButtons: [...document.querySelectorAll("[data-section-target]")]
};

refs.tokenInput.value = state.token;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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
  if (!safePath) {
    return "";
  }

  const url = new URL(safePath, window.location.origin);
  const safeReturnTo = toSameOriginPath(returnTo, "");
  if (safeReturnTo) {
    url.searchParams.set("return_to", safeReturnTo);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

function getLevelMeta(levelCode) {
  return LEVEL_META[(levelCode || "").toLowerCase()] || UNKNOWN_LEVEL;
}

function isNarrowScreen() {
  return window.matchMedia("(max-width: 1039px)").matches;
}

function normalizeError(error, fallback = "操作失败，请稍后再试。") {
  const message = String(error?.message || fallback || "").trim();
  if (!message) return fallback;
  if (message === "Failed to fetch" || message === "Load failed" || message === "NetworkError when attempting to fetch resource.") {
    return "网络请求失败，请稍后重试。";
  }
  if (message.startsWith("Unexpected token")) {
    return "服务返回了异常数据，请稍后重试。";
  }
  if (message === "Internal Server Error") {
    return "服务暂时不可用，请稍后重试。";
  }
  return message;
}

function isLikelyFetchDisconnect(error) {
  const message = String(error?.message || "").trim();
  return [
    "Failed to fetch",
    "Load failed",
    "NetworkError when attempting to fetch resource."
  ].includes(message);
}

function touchFeedback(tone = "success") {
  if (!tgApp?.HapticFeedback) return;
  if (tone === "error") {
    tgApp.HapticFeedback.notificationOccurred("error");
    return;
  }
  if (tone === "warning") {
    tgApp.HapticFeedback.notificationOccurred("warning");
    return;
  }
  tgApp.HapticFeedback.notificationOccurred("success");
}

function toneTitle(tone = "info") {
  if (tone === "error") return "操作失败";
  if (tone === "warning") return "请注意";
  if (tone === "success") return "操作成功";
  return "系统提示";
}

function toneMessage(tone = "info") {
  if (tone === "error") return "处理过程中出现异常，请稍后重试。";
  if (tone === "warning") return "请确认当前操作后继续。";
  if (tone === "success") return "操作已经完成。";
  return "正在同步当前状态。";
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
  }, 2600);
}

let popupResolver = null;

function closeInlinePopup() {
  const layer = document.querySelector("#modal-layer");
  if (layer) {
    layer.classList.add("hidden");
    layer.setAttribute("aria-hidden", "true");
  }
  document.body.classList.remove("is-modal-open");
  if (popupResolver) {
    const resolve = popupResolver;
    popupResolver = null;
    resolve();
  }
}

function handleBackNavigation() {
  const modalLayer = document.querySelector("#modal-layer");
  if (modalLayer && !modalLayer.classList.contains("hidden")) {
    closeInlinePopup();
    return;
  }

  const currentPath = currentRelativePath();
  if (backState.returnTo && backState.returnTo !== currentPath) {
    window.location.href = backState.returnTo;
    return;
  }

  if (backState.referrerPath && backState.referrerPath !== currentPath) {
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    window.location.href = backState.referrerPath;
    return;
  }

  window.location.href = backState.fallbackPath;
}

function setupBackNavigation(defaultPath = DEFAULT_BACK_PATH) {
  backState.fallbackPath = toSameOriginPath(defaultPath, DEFAULT_BACK_PATH) || DEFAULT_BACK_PATH;
  backState.returnTo = toSameOriginPath(new URLSearchParams(window.location.search).get("return_to"), "");
  backState.referrerPath = toSameOriginPath(document.referrer, "");

  const currentPath = currentRelativePath();
  const hasPrevious = (backState.returnTo && backState.returnTo !== currentPath)
    || (backState.referrerPath && backState.referrerPath !== currentPath);

  if (refs.pageBackButton) {
    refs.pageBackButton.textContent = hasPrevious ? "返回上一级" : "返回首页";
    refs.pageBackButton.addEventListener("click", handleBackNavigation);
  }

  if (tgBackButton) {
    tgBackButton.offClick?.(handleBackNavigation);
    tgBackButton.hide?.();
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
window.addEventListener("beforeunload", () => {
  tgBackButton?.offClick?.(handleBackNavigation);
});

async function popup(title, message, tone = "success") {
  touchFeedback(tone);
  const layer = document.querySelector("#modal-layer");
  const label = document.querySelector("#modal-label");
  const titleNode = document.querySelector("#modal-title");
  const messageNode = document.querySelector("#modal-message");

  if (!layer || !label || !titleNode || !messageNode) {
    window.alert(`${title}\n\n${message}`);
    return;
  }

  if (popupResolver) {
    closeInlinePopup();
  }

  label.textContent = toneTitle(tone);
  titleNode.textContent = title || toneTitle(tone);
  messageNode.textContent = message || toneMessage(tone);
  layer.classList.remove("hidden");
  layer.setAttribute("aria-hidden", "false");
  document.body.classList.add("is-modal-open");

  return new Promise((resolve) => {
    popupResolver = resolve;
  });
}

function setAdminStatus(text, tone = "info") {
  refs.adminStatus.textContent = text;
  refs.adminStatus.dataset.tone = tone;
}

function setAuthMode(mode = null) {
  const meta = {
    telegram: { text: "主人直登", tone: "normal" },
    token: { text: "令牌登录", tone: "vip" },
    none: { text: "待认证", tone: "pending" }
  }[mode || "none"];

  refs.authModePill.className = `badge badge--${meta.tone}`;
  refs.authModePill.textContent = meta.text;
}

function setSelectedUserPill(text = "未选中用户") {
  refs.selectedUserPill.textContent = text;
}

function syncEditorShortcut() {
  if (!refs.jumpEditorButton) return;
  const hasSelection = Boolean(state.selectedTg);
  refs.jumpEditorButton.disabled = !hasSelection;
  refs.jumpEditorButton.textContent = hasSelection ? "回到当前编辑" : "跳到用户编辑";
}

function pulseTarget(node) {
  if (!node) return;
  node.classList.remove("jump-highlight");
  void node.offsetWidth;
  node.classList.add("jump-highlight");
  window.setTimeout(() => {
    node.classList.remove("jump-highlight");
  }, 1500);
}

function setAuthCopy(title, status) {
  refs.authTitle.textContent = title;
  refs.authStatus.textContent = status;
}

function setActiveNav(sectionId) {
  refs.navButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.sectionTarget === sectionId);
  });
}

function focusSection(sectionId, smooth = true) {
  const section = document.getElementById(sectionId);
  if (!section) return;
  section.open = true;
  setActiveNav(sectionId);
  section.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  pulseTarget(section);
}

function toggleSections(open) {
  document.querySelectorAll(".fold-card").forEach((card) => {
    card.open = open;
  });
}

function authHeaders() {
  if (state.authMode === "telegram" && state.telegramInitData) {
    return { "X-Telegram-Init-Data": state.telegramInitData };
  }

  if (state.token) {
    return { "X-Admin-Token": state.token };
  }

  return {};
}

async function readPayload(response) {
  const raw = await response.text();
  if (!raw) {
    return { code: response.ok ? 200 : response.status, data: null };
  }
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(raw.trim() || `请求失败（HTTP ${response.status}）`);
  }
}

async function api(path, options = {}) {
  const headers = {
    ...authHeaders(),
    ...(options.headers || {})
  };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const response = await fetch(path, {
    ...options,
    headers
  });
  const payload = await readPayload(response);

  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.detail || payload.message || `请求失败（HTTP ${response.status}）`);
  }

  return payload;
}

async function patchPlugin(pluginId, payload) {
  return api(`/admin-api/plugins/${encodeURIComponent(pluginId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

async function importPluginArchive(file, options = {}) {
  const body = new FormData();
  body.append("file", file);
  body.append("enabled", String(Boolean(options.enabled)));
  body.append("replace_existing", String(Boolean(options.replaceExisting)));
  return api("/admin-api/plugins/import", {
    method: "POST",
    body
  });
}

function resolveDownloadFilename(contentDisposition, fallback = "echo-migration.zip") {
  if (!contentDisposition) {
    return fallback;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const plainMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  return plainMatch?.[1] || fallback;
}

async function downloadMigrationBundle() {
  const response = await fetch("/admin-api/system/migration/export", {
    headers: authHeaders()
  });

  if (!response.ok) {
    const payload = await readPayload(response);
    throw new Error(payload.detail || payload.message || `请求失败（HTTP ${response.status}）`);
  }

  const blob = await response.blob();
  const filename = resolveDownloadFilename(
    response.headers.get("content-disposition"),
    `echo-migration-${Date.now()}.zip`
  );
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function importMigrationArchive(file, options = {}) {
  const body = new FormData();
  body.append("file", file);
  body.append("restore_config_file", String(Boolean(options.restoreConfig)));
  body.append("restart_after_import", String(Boolean(options.restartAfterImport)));
  return api("/admin-api/system/migration/import", {
    method: "POST",
    body
  });
}

function toLocalValue(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromLocalValue(value) {
  return value ? new Date(value).toISOString() : null;
}

function fmtDateTime(value) {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未设置";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatCount(value) {
  return Number(value ?? 0).toLocaleString("zh-CN");
}

function actorPrimaryLabel(actor) {
  if (!actor) return "暂无信息";
  if (actor.tg_display_name) return actor.tg_display_name;
  if (actor.tg_username) return `@${actor.tg_username}`;
  if (actor.tg_display_label && !String(actor.tg_display_label).startsWith("TG ")) {
    return actor.tg_display_label;
  }
  return actor.tg ? `TG ${actor.tg}` : "暂无信息";
}

function fmtActor(actor) {
  if (!actor) return "暂无信息";
  const parts = [
    actorPrimaryLabel(actor),
    actor.emby_name ? `Emby ${actor.emby_name}` : "",
    actor.lv_text || ""
  ].filter(Boolean);
  return parts.join(" · ");
}

function actorLikeLabel(item) {
  if (!item) return "暂无信息";
  return actorPrimaryLabel({
    tg: item.tg,
    tg_display_name: item.tg_display_name || item.display_name,
    tg_username: item.tg_username || item.username,
    tg_display_label: item.tg_display_label || item.display_label
  });
}

function targetDisplayLabel(target) {
  if (!target) return "暂无信息";
  return actorLikeLabel(target);
}

function fmtBotBlockTarget(item) {
  if (!item) return "未指定目标";
  const parts = [];
  if (item.tg) {
    parts.push(`TG ${item.tg}`);
  }
  if (item.username) {
    parts.push(`@${item.username}`);
  }
  return parts.join(" / ") || "未指定目标";
}

function fmtModerationMember(item) {
  if (!item) return "未选择成员";
  const parts = [
    actorLikeLabel(item),
    item.tg ? `TG ${item.tg}` : "",
    item.username ? `@${item.username}` : "",
    item.status_text || "",
    item.warn_count ? `警告 ${item.warn_count}` : ""
  ].filter(Boolean);
  return parts.join(" · ");
}

function setModerationStatus(text, tone = "info") {
  if (!refs.moderationStatus) return;
  refs.moderationStatus.textContent = text;
  refs.moderationStatus.dataset.tone = tone;
}

function setModerationSettings(data = {}) {
  if (refs.moderationWarnThreshold) {
    refs.moderationWarnThreshold.value = Number(data.warn_threshold || 3);
  }
  if (refs.moderationWarnAction) {
    refs.moderationWarnAction.value = data.warn_action || "mute";
  }
  if (refs.moderationWarnMuteMinutes) {
    refs.moderationWarnMuteMinutes.value = Number(data.mute_minutes || 60);
    refs.moderationWarnMuteMinutes.disabled = (data.warn_action || "mute") !== "mute";
  }
  if (refs.moderationSettingsStatus) {
    const actionText = (data.warn_action || "mute") === "kick"
      ? "达到阈值后自动踢出"
      : `达到阈值后自动禁言 ${formatCount(data.mute_minutes || 60)} 分钟`;
    refs.moderationSettingsStatus.textContent = `当前阈值 ${formatCount(data.warn_threshold || 3)} 次，${actionText}。`;
    refs.moderationSettingsStatus.dataset.tone = "info";
  }
}

function fillModerationTarget(item) {
  state.selectedModerationTarget = item ? { ...item, chat_id: item.chat_id || state.selectedModerationChatId } : null;
  if (!refs.moderationTargetDisplay || !refs.moderationTargetStatus) return;
  if (!item) {
    refs.moderationTargetDisplay.value = "";
    refs.moderationTargetStatus.textContent = "先在上方搜索并选择一个群成员。";
    refs.moderationTargetStatus.dataset.tone = "info";
    return;
  }
  refs.moderationTargetDisplay.value = fmtModerationMember(item);
  refs.moderationTargetStatus.textContent = item.warn_count
    ? `当前选中 ${actorLikeLabel(item)}，已有 ${item.warn_count} 次警告。`
    : `当前选中 ${actorLikeLabel(item)}，暂时没有警告记录。`;
  refs.moderationTargetStatus.dataset.tone = item.warn_count ? "warning" : "info";
}

function renderModerationMembers(items) {
  if (!refs.moderationMemberList) return;
  refs.moderationMemberList.innerHTML = "";

  if (!items.length) {
    refs.moderationMemberList.innerHTML = `
      <article class="user-card">
        <div class="user-name">当前没有匹配成员</div>
        <p class="user-meta stack-empty">可以更换关键词，或先切换到正确的群组后再搜索。</p>
      </article>
    `;
    return;
  }

  for (const item of items) {
    const badges = [
      `<span class="badge badge--${item.is_admin ? "vip" : "normal"}">${escapeHtml(item.status_text || "成员")}</span>`
    ];
    if (item.warn_count) {
      badges.push(`<span class="badge badge--danger">警告 ${escapeHtml(item.warn_count)}</span>`);
    }
    if (item.lv_text) {
      badges.push(`<span class="badge badge--${escapeHtml(item.lv_tone || "pending")}">${escapeHtml(item.lv_text)}</span>`);
    }

    const card = document.createElement("button");
    card.type = "button";
    card.className = `user-card${state.selectedModerationTarget?.tg === item.tg ? " is-selected" : ""}`;
    card.innerHTML = `
      <div class="user-card-top">
        <div>
          <div class="user-name">${escapeHtml(actorLikeLabel(item))}</div>
          <div class="user-subline">TG ${escapeHtml(item.tg)}${item.username ? ` · @${escapeHtml(item.username)}` : ""}</div>
        </div>
        <div class="code-card-badges">${badges.join("")}</div>
      </div>
      <div class="user-meta">
        <div>${escapeHtml(item.emby_name || "未绑定 Emby 账号")}${item.embyid ? ` · ID ${escapeHtml(item.embyid)}` : ""}</div>
        <div>当前群身份：${escapeHtml(item.status_text || "未知状态")}</div>
      </div>
    `;
    card.addEventListener("click", () => {
      fillModerationTarget(item);
      renderModerationMembers(state.moderationMembers);
      focusSection("moderation-section", false);
    });
    refs.moderationMemberList.appendChild(card);
  }
}

function renderModerationWarnings(items) {
  if (!refs.moderationWarningList) return;
  refs.moderationWarningList.innerHTML = "";

  if (!items.length) {
    refs.moderationWarningList.innerHTML = `
      <article class="plugin-card">
        <div class="plugin-name">当前群没有有效警告</div>
        <p class="plugin-meta stack-empty">当你在这里执行“警告”后，列表会自动展示累计中的成员。</p>
      </article>
    `;
    return;
  }

  for (const item of items) {
    const actionText = item.last_action
      ? `最近自动处罚：${item.last_action}${item.last_action_at ? ` · ${fmtDateTime(item.last_action_at)}` : ""}`
      : "最近还没有触发自动处罚。";
    const card = document.createElement("article");
    card.className = "plugin-card";
    card.innerHTML = `
      <div class="plugin-card-top">
        <div class="plugin-name">${escapeHtml(actorLikeLabel(item))}</div>
        <span class="badge badge--danger">警告 ${escapeHtml(item.warn_count)}</span>
      </div>
      <div class="plugin-meta">TG ${escapeHtml(item.tg)}${item.tg_username ? ` · @${escapeHtml(item.tg_username)}` : ""}${item.emby_name ? ` · Emby ${escapeHtml(item.emby_name)}` : ""}</div>
      <div class="plugin-meta">最近原因：${escapeHtml(item.last_reason || "未填写")}</div>
      <div class="plugin-meta">最近警告时间：${escapeHtml(fmtDateTime(item.last_warned_at))}</div>
      <div class="plugin-meta">${escapeHtml(actionText)}</div>
      <div class="plugin-actions">
        <button type="button" class="secondary" data-warning-pick="${escapeHtml(item.tg)}">选中成员</button>
      </div>
    `;
    refs.moderationWarningList.appendChild(card);
  }
}

function setCodeSummary(summary = {}) {
  document.querySelector("#codes-total").textContent = formatCount(summary.all);
  document.querySelector("#codes-unused").textContent = formatCount(summary.unused);
  document.querySelector("#codes-used").textContent = formatCount(summary.used);
  document.querySelector("#codes-exhausted").textContent = formatCount(summary.exhausted);

  refs.codeStatusButtons.forEach((button) => {
    const status = button.dataset.codeStatus;
    const count = summary[status];
    const labelMap = {
      all: "全部",
      unused: "未使用",
      used: "已使用"
    };
    button.textContent = typeof count === "number" ? `${labelMap[status]} (${formatCount(count)})` : labelMap[status];
    button.classList.toggle("is-active", status === state.codeStatus);
  });
}

function syncCodeSelectionActions() {
  const visibleCodes = state.visibleCodes.map((item) => item.code);
  const allVisibleSelected = visibleCodes.length > 0 && visibleCodes.every((code) => state.selectedCodes.has(code));
  refs.codeSelectPage.textContent = allVisibleSelected ? "取消本页" : "全选本页";
  refs.codeDeleteSelected.disabled = state.selectedCodes.size === 0;
  refs.codeDeleteSelected.textContent = state.selectedCodes.size ? `删除已选 (${state.selectedCodes.size})` : "删除已选";
  refs.codeClearSelection.disabled = state.selectedCodes.size === 0;
}

function renderCodeCreateResult(payload) {
  refs.codeResult.classList.remove("hidden");
  refs.codeResultTitle.textContent = `${payload.type_text}生成完成`;
  refs.codeResultMeta.textContent = `${payload.days} 天 · ${payload.count} 个 · ${payload.method} 模式 · 每码 ${payload.usage_limit} 次`;
  refs.codeOutput.value = (payload.items || []).map((item) => item.display || item.code || "").filter(Boolean).join("\n");
}

async function runButtonAction(button, pendingText, handler) {
  if (!button) {
    return handler();
  }

  const previous = button.textContent;
  button.disabled = true;
  button.textContent = pendingText;
  try {
    return await handler();
  } finally {
    button.disabled = false;
    button.textContent = previous;
  }
}

function renderLevelLegend() {
  refs.levelLegend.innerHTML = "";

  Object.values(LEVEL_META).forEach((meta) => {
    const item = document.createElement("article");
    item.className = "level-chip";
    item.innerHTML = `
      <div class="level-chip-head">
        <strong>${escapeHtml(meta.text)} (${escapeHtml(meta.code.toUpperCase())})</strong>
        <span class="badge badge--${escapeHtml(meta.tone)}">${escapeHtml(meta.shortText)}</span>
      </div>
      <p>${escapeHtml(meta.description)}</p>
    `;
    refs.levelLegend.appendChild(item);
  });
}

function setSummary(data) {
  state.summary = data || null;
  document.querySelector("#summary-total").textContent = formatCount(data.total_users);
  document.querySelector("#summary-active").textContent = formatCount(data.active_accounts);
  document.querySelector("#summary-whitelist").textContent = formatCount(data.whitelist_users);
  document.querySelector("#summary-banned").textContent = formatCount(data.banned_users);
  document.querySelector("#summary-currency").textContent = formatCount(data.total_currency);
  syncUserBatchControls();
  syncEmbyServiceUI(Boolean(data.emby_service_suspended));
}

function currentUserBatchPayload() {
  const action = refs.userBatchAction?.value || "set_level";
  return {
    action,
    scope: refs.userBatchScope?.value || "exclude_whitelist",
    source_level: refs.userBatchSourceLevel?.value || "b",
    target_level: action === "set_level" ? (refs.userBatchTargetLevel?.value || "b") : null
  };
}

function userBatchPayloadKey(payload = currentUserBatchPayload()) {
  return JSON.stringify(payload);
}

function syncUserBatchControls() {
  const scope = refs.userBatchScope?.value || "exclude_whitelist";
  const action = refs.userBatchAction?.value || "set_level";
  if (refs.userBatchSourceLevel) {
    refs.userBatchSourceLevel.disabled = scope !== "level";
  }
  if (refs.userBatchTargetLevel) {
    refs.userBatchTargetLevel.disabled = action !== "set_level";
  }
  if (refs.userBatchApplyButton) {
    const previewMatches = state.userBatchPreview?.payloadKey === userBatchPayloadKey();
    refs.userBatchApplyButton.disabled = !previewMatches || Number(state.userBatchPreview?.affected_count || 0) <= 0;
  }
}

function invalidateUserBatchPreview(message = "批量条件已变更，请重新预览影响账号。") {
  state.userBatchPreview = null;
  if (refs.userBatchPreview) {
    refs.userBatchPreview.classList.add("hidden");
    refs.userBatchPreview.innerHTML = "";
  }
  if (refs.userBatchStatus) {
    refs.userBatchStatus.textContent = message;
    refs.userBatchStatus.dataset.tone = "info";
  }
  syncUserBatchControls();
}

function renderUserBatchPreview(data = {}, payload = currentUserBatchPayload()) {
  state.userBatchPreview = {
    ...data,
    payload,
    payloadKey: userBatchPayloadKey(payload)
  };
  const levelCounts = data.level_counts || {};
  const samples = Array.isArray(data.samples) ? data.samples : [];
  const sampleText = samples.length
    ? samples.map((item) => {
        const level = getLevelMeta(item.lv);
        return `<li>${escapeHtml(actorLikeLabel(item))} · TG ${escapeHtml(item.tg)} · ${escapeHtml(item.lv_text || level.text)}${item.name ? ` · Emby ${escapeHtml(item.name)}` : ""}</li>`;
      }).join("")
    : "<li>暂无样例账号。</li>";

  if (refs.userBatchPreview) {
    refs.userBatchPreview.classList.remove("hidden");
    refs.userBatchPreview.innerHTML = `
      <div class="code-result-head">
        <strong>${escapeHtml(data.scope_text || "批量范围")} · ${escapeHtml(data.action_text || "批量操作")}</strong>
        <span class="badge badge--${Number(data.affected_count || 0) > 0 ? "warning" : "pending"}">影响 ${escapeHtml(formatCount(data.affected_count || 0))}</span>
      </div>
      <div class="code-info-grid">
        <section class="code-info-block">
          <h4>账号数量</h4>
          <p>总计 ${escapeHtml(formatCount(data.affected_count || 0))} 个，含有效 Emby 账号 ${escapeHtml(formatCount(data.active_account_count || 0))} 个。</p>
        </section>
        <section class="code-info-block">
          <h4>当前等级分布</h4>
          <p>白名单 ${escapeHtml(formatCount(levelCounts.a || 0))} · 正常 ${escapeHtml(formatCount(levelCounts.b || 0))} · 封禁 ${escapeHtml(formatCount(levelCounts.c || 0))} · 未注册 ${escapeHtml(formatCount(levelCounts.d || 0))}</p>
        </section>
      </div>
      <section class="code-info-block">
        <h4>样例账号</h4>
        <ul class="batch-sample-list">${sampleText}</ul>
      </section>
    `;
  }

  if (refs.userBatchStatus) {
    refs.userBatchStatus.textContent = Number(data.affected_count || 0) > 0
      ? `预览完成：${data.scope_text} 将执行“${data.action_text}”，影响 ${formatCount(data.affected_count)} 个账号。`
      : "预览完成：当前条件没有匹配账号。";
    refs.userBatchStatus.dataset.tone = Number(data.affected_count || 0) > 0 ? "warning" : "info";
  }
  syncUserBatchControls();
}

function syncEmbyServiceUI(suspended) {
  if (refs.embyServiceBadge) {
    refs.embyServiceBadge.className = `badge badge--${suspended ? "danger" : "normal"}`;
    refs.embyServiceBadge.textContent = suspended ? "服务已暂停" : "服务正常";
  }
  if (refs.embyServiceToggle) {
    refs.embyServiceToggle.textContent = suspended ? "恢复 Emby 服务" : "暂停 Emby 服务";
  }
  if (refs.embyServiceStatus) {
    refs.embyServiceStatus.textContent = suspended
      ? "当前 Emby 服务已全局暂停，所有用户的 Emby 账号在服务器端已被禁用。点击下方按钮恢复服务。"
      : "开启后，所有用户的 Emby 账号将在服务器端被禁用，即使手机已保存线路也无法播放。关闭后，有账号的用户自动恢复。";
  }
}

function setAutoUpdate(data = {}) {
  refs.autoUpdateEnabledText.textContent = data.status ? "已启用" : "已关闭";
  refs.autoUpdateLastChecked.textContent = fmtDateTime(data.last_checked_at);
  refs.autoUpdateLastStatus.textContent = data.last_status || "未运行";
  refs.autoUpdateCommitSha.textContent = data.commit_sha ? String(data.commit_sha).slice(0, 7) : "未记录";
  refs.autoUpdateStatus.checked = Boolean(data.status);
  refs.autoUpdateGitRepo.value = data.git_repo || "";
  refs.autoUpdateDockerImage.value = data.docker_image || "";
  refs.autoUpdateComposeService.value = data.compose_service || "";
  refs.autoUpdateContainerName.value = data.container_name || "";
  refs.autoUpdateInterval.value = Number(data.check_interval_minutes || 30);
  refs.autoUpdateNote.textContent = data.up_description || data.last_error || "保存后会按设定间隔检查 GitHub 与 Docker 镜像。";
  refs.autoUpdateNote.dataset.tone = data.last_error ? "error" : "info";
}

function renderUsers(items) {
  refs.userList.innerHTML = "";

  if (!items.length) {
    refs.userList.innerHTML = `
      <article class="user-card">
        <div class="user-name">没有查到记录</div>
        <p class="user-meta stack-empty">可以更换关键词，或者翻页继续查看。</p>
      </article>
    `;
    return;
  }

  for (const item of items) {
    const level = getLevelMeta(item.lv);
    const primaryName = actorLikeLabel(item);
    const secondaryBits = [
      `账号 ID ${escapeHtml(item.tg)}`,
      item.embyid ? `Emby ID ${escapeHtml(item.embyid)}` : "",
      item.name ? `Emby 名称 ${escapeHtml(item.name)}` : ""
    ].filter(Boolean);
    const secondary = secondaryBits.join(" · ");
    const badges = [
      `<span class="badge badge--${escapeHtml(item.lv_tone || level.tone)}">${escapeHtml(item.lv_text || level.text)}</span>`
    ];
    if (item.bot_access_blocked) {
      badges.push(`<span class="badge badge--danger">Bot 已屏蔽</span>`);
    }
    const card = document.createElement("button");
    card.type = "button";
    card.className = `user-card${state.selectedTg === item.tg ? " is-selected" : ""}`;
    card.innerHTML = `
      <div class="user-card-top">
        <div>
          <div class="user-name">${escapeHtml(primaryName)}</div>
          <div class="user-subline">${secondary}</div>
        </div>
        <div class="code-card-badges">${badges.join("")}</div>
      </div>
      <div class="user-meta">
        <div>账户余额：${escapeHtml(item.iv ?? 0)} · 注册/续期天数：${escapeHtml(item.us ?? 0)}</div>
        <div>到期时间：${escapeHtml(fmtDateTime(item.ex))}</div>
      </div>
    `;
    card.addEventListener("click", () => loadUser(item.tg));
    refs.userList.appendChild(card);
  }
}

function renderCodes(items) {
  refs.codeList.innerHTML = "";

  if (!items.length) {
    refs.codeList.innerHTML = `
      <article class="user-card">
        <div class="user-name">当前分类没有注册码</div>
        <p class="user-meta stack-empty">可以切换到其他分类，或先批量生成一批新的注册码。</p>
      </article>
    `;
    syncCodeSelectionActions();
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "code-card";
    const redeemerHtml = item.redeemers?.length
      ? item.redeemers.map((redeemer) => `
          <div class="code-actor-line">
            <strong>第 ${escapeHtml(redeemer.use_index)} 次</strong>
            <span>${escapeHtml(fmtActor(redeemer.actor))}</span>
            <span>${escapeHtml(fmtDateTime(redeemer.redeemed_at))}</span>
          </div>
        `).join("")
      : `<p class="plugin-meta stack-empty">还没有使用记录。</p>`;

    card.innerHTML = `
      <div class="code-card-top">
        <label class="code-check">
          <input type="checkbox" data-code-select="${escapeHtml(item.code)}" ${state.selectedCodes.has(item.code) ? "checked" : ""}>
          <span>选择</span>
        </label>
        <div class="code-card-badges">
          <span class="badge badge--${item.kind === "renew" ? "vip" : "normal"}">${escapeHtml(item.kind_text)}</span>
          <span class="badge badge--${item.status === "unused" ? "pending" : "normal"}">${escapeHtml(item.status_text)}</span>
          ${item.is_exhausted ? `<span class="badge badge--danger">已用尽</span>` : ""}
        </div>
      </div>
      <div class="user-name code-value">${escapeHtml(item.code)}</div>
      <div class="user-subline">天数 ${escapeHtml(item.days)} · 使用进度 ${escapeHtml(item.use_count)}/${escapeHtml(item.use_limit)} · 剩余 ${escapeHtml(item.remaining_uses)}</div>
      <div class="code-info-grid">
        <section class="code-info-block">
          <h4>邀请人 / 创建人</h4>
          <p>${escapeHtml(fmtActor(item.creator))}</p>
        </section>
        <section class="code-info-block">
          <h4>最近使用者</h4>
          <p>${escapeHtml(fmtActor(item.latest_redeemer))}</p>
          <p class="plugin-meta">最近时间：${escapeHtml(fmtDateTime(item.usedtime))}</p>
        </section>
      </div>
      <section class="code-info-block">
        <h4>被邀请人 / 使用者详情</h4>
        <div class="code-redeemer-list">${redeemerHtml}</div>
      </section>
    `;
    refs.codeList.appendChild(card);
  }

  syncCodeSelectionActions();
}

function setInviteSummary(summary = {}) {
  document.querySelector("#invite-total").textContent = formatCount(summary.total);
  document.querySelector("#invite-available").textContent = "按观影用户派发";
  document.querySelector("#invite-used").textContent = formatCount(summary.used);
  document.querySelector("#invite-revoked").textContent = formatCount(summary.revoked);
}

function setInviteOpenSummary(summary = {}) {
  document.querySelector("#invite-open-total").textContent = formatCount(summary.total);
  document.querySelector("#invite-open-available").textContent = formatCount(summary.available);
  document.querySelector("#invite-open-used").textContent = formatCount(summary.used);
  document.querySelector("#invite-open-revoked").textContent = formatCount(summary.revoked);
}

function applyInviteSettings(settings = {}) {
  if (refs.inviteEnabled) refs.inviteEnabled.checked = Boolean(settings.enabled);
  if (refs.inviteTargetChatId) refs.inviteTargetChatId.value = settings.target_chat_id || "";
  if (refs.inviteExpireHours) refs.inviteExpireHours.value = Number(settings.expire_hours || 24);
  if (refs.inviteAccountOpenDays) refs.inviteAccountOpenDays.value = Number(settings.account_open_days || 30);
  if (refs.inviteOpenGrantDays && !Number(refs.inviteOpenGrantDays.value || 0)) {
    refs.inviteOpenGrantDays.value = Number(settings.account_open_days || 30);
  }
  const groupVerificationEnabled = settings.group_verification_enabled ?? settings.strict_target ?? true;
  const channelVerificationEnabled = settings.channel_verification_enabled ?? false;
  if (refs.inviteGroupVerificationEnabled) refs.inviteGroupVerificationEnabled.checked = Boolean(groupVerificationEnabled);
  if (refs.inviteChannelVerificationEnabled) refs.inviteChannelVerificationEnabled.checked = Boolean(channelVerificationEnabled);
  if (refs.inviteSettingsStatus) {
    refs.inviteSettingsStatus.textContent = settings.enabled
      ? `邀请模块已开启：观影用户可生成一次入群邀请，也可提交一次账号开通申请；目标群组 ${settings.target_chat_id || "未配置"}，群组验证 ${groupVerificationEnabled ? "开启" : "关闭"}，频道验证 ${channelVerificationEnabled ? "开启" : "关闭"}，入群链接有效期 ${formatCount(settings.expire_hours || 24)} 小时，注册天数 ${formatCount(settings.account_open_days || 30)} 天。`
      : "邀请模块当前关闭，用户界面的入群邀请和账号开通申请都会隐藏。";
    refs.inviteSettingsStatus.dataset.tone = settings.enabled ? "success" : "warning";
  }
}

function inviteSection(type) {
  return type === "account_open" ? (state.inviteBundle?.account_open || {}) : (state.inviteBundle?.group_join || state.inviteBundle || {});
}

function inviteSelectedSet(type) {
  return type === "account_open" ? state.selectedInviteOpenCredits : state.selectedInviteCredits;
}

function syncInviteCreditSelectionActions(type = "group_join") {
  const section = inviteSection(type);
  const credits = section.credits || [];
  const selected = inviteSelectedSet(type);
  const availableIds = credits.filter((item) => item.available).map((item) => Number(item.id));
  const allSelected = availableIds.length > 0 && availableIds.every((id) => selected.has(id));
  const selectButton = type === "account_open" ? refs.inviteOpenCreditSelectPage : refs.inviteCreditSelectPage;
  const deleteButton = type === "account_open" ? refs.inviteOpenCreditDeleteSelected : refs.inviteCreditDeleteSelected;
  const clearButton = type === "account_open" ? refs.inviteOpenCreditClearSelection : refs.inviteCreditClearSelection;
  if (selectButton) selectButton.textContent = allSelected ? "取消可删" : "全选可删";
  if (deleteButton) {
    deleteButton.disabled = selected.size === 0;
    deleteButton.textContent = selected.size ? `删除已选 (${selected.size})` : "删除已选";
  }
  if (clearButton) clearButton.disabled = selected.size === 0;
}

function renderInviteCredits(items = [], type = "group_join") {
  const root = type === "account_open" ? refs.inviteOpenCreditList : refs.inviteCreditList;
  const selected = inviteSelectedSet(type);
  const qualification = inviteSection(type).searched_qualification;
  if (!root) return;
  root.innerHTML = "";
  if (qualification) {
    const info = type === "account_open" ? qualification.account_open : qualification.group_join;
    const label = type === "account_open" ? "开通申请资格" : "入群邀请资格";
    const article = document.createElement("article");
    article.className = "code-card";
    article.innerHTML = `
      <div class="code-card-top">
        <div class="code-card-badges">
          <span class="badge badge--${info.available ? "normal" : "danger"}">${info.available ? "可用" : "不可用"}</span>
          <span class="badge badge--vip">${escapeHtml(label)}</span>
        </div>
      </div>
      <div class="user-name">${escapeHtml(label)} · ${escapeHtml(fmtActor(qualification.owner))}</div>
      <div class="plugin-meta">观影资格：${qualification.has_viewing_access ? "有" : "无"} · 已使用：${info.used ? "是" : "否"} · 已撤销：${info.revoked ? "是" : "否"}</div>
      <div class="plugin-actions">
        <button type="button" class="secondary" data-invite-qualification-owner="${escapeHtml(qualification.owner_tg)}" data-invite-qualification-type="${escapeHtml(type)}" data-invite-qualification-enabled="${info.revoked ? "true" : "false"}">${info.revoked ? "恢复资格" : "撤销资格"}</button>
      </div>
    `;
    root.appendChild(article);
  }
  if (!items.length) {
    root.insertAdjacentHTML("beforeend", `
      <article class="user-card">
        <div class="user-name">当前还没有${type === "account_open" ? "注册资格" : "入群资格"}</div>
        <p class="user-meta stack-empty">${type === "account_open" ? "注册资格已改为申请制，优先处理下方开通申请。" : "入群资格由观影用户自动拥有一次。"}</p>
      </article>
    `);
    syncInviteCreditSelectionActions(type);
    return;
  }

  for (const item of items) {
    const selectable = Boolean(item.available);
    const typeLabel = item.credit_type_text || (type === "account_open" ? "注册资格" : "入群资格");
    const card = document.createElement("article");
    card.className = "code-card";
    card.innerHTML = `
      <div class="code-card-top">
        <label class="code-check">
          <input type="checkbox" data-invite-credit-select="${escapeHtml(item.id)}" data-invite-credit-type="${escapeHtml(type)}" ${selected.has(Number(item.id)) ? "checked" : ""} ${selectable ? "" : "disabled"}>
          <span>选择</span>
        </label>
        <div class="code-card-badges">
          <span class="badge badge--${item.available ? "normal" : item.status === "used" ? "pending" : "danger"}">${escapeHtml(item.status_text)}</span>
          <span class="badge badge--vip">${escapeHtml(typeLabel)}</span>
          <span class="badge badge--normal">${escapeHtml(item.source || "admin")}</span>
        </div>
      </div>
      <div class="user-name">${escapeHtml(typeLabel)} #${escapeHtml(item.id)} · ${escapeHtml(fmtActor(item.owner))}</div>
      <div class="user-subline">发放时间：${escapeHtml(fmtDateTime(item.granted_at))} · 来源：${escapeHtml(item.source_ref || item.source || "后台")}${item.invite_days ? ` · 注册 ${escapeHtml(item.invite_days)} 天` : ""}</div>
      <div class="plugin-meta">发放人：${escapeHtml(fmtActor(item.granted_by))}</div>
      <div class="plugin-meta">备注：${escapeHtml(item.note || item.revoke_reason || "无")}</div>
      ${item.available ? `<div class="plugin-actions"><button type="button" class="secondary" data-invite-credit-edit="${escapeHtml(item.id)}" data-invite-credit-type="${escapeHtml(type)}">编辑资格</button></div>` : ""}
    `;
    root.appendChild(card);
  }
  syncInviteCreditSelectionActions(type);
}

function renderInviteRecords(items = [], type = "group_join") {
  const root = type === "account_open" ? refs.inviteOpenRecordList : refs.inviteRecordList;
  if (!root) return;
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = `
      <article class="user-card">
        <div class="user-name">当前还没有邀请关系</div>
        <p class="user-meta stack-empty">发放邀请后，这里会展示邀请人和被邀请人。</p>
      </article>
    `;
    return;
  }

  for (const item of items) {
    const pending = item.status === "pending";
    const isAccountOpen = type === "account_open";
    const reviewerLine = isAccountOpen
      ? `<div class="plugin-meta">审核人：${escapeHtml(fmtActor(item.reviewer))} · 审核时间：${escapeHtml(fmtDateTime(item.reviewed_at))}</div>`
      : "";
    const accountActions = isAccountOpen
      ? `<div class="plugin-actions">
          ${pending ? `<button type="button" data-invite-open-review="${escapeHtml(item.id)}" data-invite-open-action="approve">通过</button><button type="button" class="secondary" data-invite-open-review="${escapeHtml(item.id)}" data-invite-open-action="decline">拒绝</button>` : ""}
          ${["pending", "approved", "granted"].includes(item.status) ? `<button type="button" class="secondary" data-invite-open-review="${escapeHtml(item.id)}" data-invite-open-action="revoke">撤销</button>` : ""}
        </div>`
      : "";
    const card = document.createElement("article");
    card.className = "code-card";
    card.innerHTML = `
      <div class="code-card-top">
        <div class="code-card-badges">
          <span class="badge badge--${pending ? "pending" : item.status === "approved" ? "normal" : "danger"}">${escapeHtml(item.status_text)}</span>
          <span class="badge badge--normal">${isAccountOpen ? `注册 ${escapeHtml(item.invite_days || 0)} 天` : `群 ${escapeHtml(item.target_chat_id)}`}</span>
        </div>
      </div>
      <div class="user-name">${isAccountOpen ? "开通申请" : "入群邀请"} #${escapeHtml(item.id)} · ${escapeHtml(fmtActor(item.inviter))} -> ${escapeHtml(fmtActor(item.invitee))}</div>
      <div class="user-subline">创建：${escapeHtml(fmtDateTime(item.created_at))} · 过期：${escapeHtml(fmtDateTime(item.expires_at))}</div>
      <div class="plugin-meta">${isAccountOpen ? "申请人" : "邀请人"}：${escapeHtml(fmtActor(item.inviter))} · ${isAccountOpen ? "被申请人" : "被邀请人"}：${escapeHtml(fmtActor(item.invitee))}</div>
      <div class="plugin-meta">最近请求：${escapeHtml(fmtActor(item.last_requester))} · 使用时间：${escapeHtml(fmtDateTime(item.used_at))}</div>
      ${reviewerLine}
      ${isAccountOpen ? `<div class="plugin-meta">申请备注：${escapeHtml(item.note || "无")} · 审核备注：${escapeHtml(item.review_note || "无")}</div>` : `<div class="plugin-meta">邀请链接：${escapeHtml(item.invite_link || "已隐藏或不可用")}</div>`}
      ${isAccountOpen ? accountActions : pending ? `<div class="plugin-actions"><button type="button" data-invite-record-revoke="${escapeHtml(item.id)}">撤销邀请</button></div>` : ""}
    `;
    root.appendChild(card);
  }
}

function syncInvitePagers(groupPagination = {}, accountPagination = {}) {
  const groupPage = Number(groupPagination.page || state.inviteGroupPage || 1);
  const groupTotal = Number(groupPagination.total_pages || 1);
  const openPage = Number(accountPagination.page || state.inviteOpenPage || 1);
  const openTotal = Number(accountPagination.total_pages || 1);
  state.inviteGroupPage = groupPage;
  state.inviteOpenPage = openPage;
  if (refs.inviteGroupPageLabel) refs.inviteGroupPageLabel.textContent = `第 ${groupPage} 页 / 共 ${groupTotal} 页`;
  if (refs.inviteGroupPrevPage) refs.inviteGroupPrevPage.disabled = !groupPagination.has_prev;
  if (refs.inviteGroupNextPage) refs.inviteGroupNextPage.disabled = !groupPagination.has_next;
  if (refs.inviteOpenPageLabel) refs.inviteOpenPageLabel.textContent = `第 ${openPage} 页 / 共 ${openTotal} 页`;
  if (refs.inviteOpenPrevPage) refs.inviteOpenPrevPage.disabled = !accountPagination.has_prev;
  if (refs.inviteOpenNextPage) refs.inviteOpenNextPage.disabled = !accountPagination.has_next;
}

function applyInviteBundle(bundle = {}) {
  state.inviteBundle = bundle || {};
  const groupSection = bundle.group_join || bundle || {};
  const accountSection = bundle.account_open || {};
  setInviteSummary(groupSection.summary || bundle.summary || {});
  setInviteOpenSummary(accountSection.summary || {});
  applyInviteSettings(bundle.settings || {});
  renderInviteCredits(groupSection.credits || bundle.credits || [], "group_join");
  renderInviteRecords(groupSection.records || bundle.records || [], "group_join");
  renderInviteCredits(accountSection.credits || [], "account_open");
  renderInviteRecords(accountSection.records || [], "account_open");
  syncInvitePagers(groupSection.records_pagination || {}, accountSection.records_pagination || {});
}

function renderPlugins(items) {
  refs.pluginList.innerHTML = "";

  if (!items.length) {
    refs.pluginList.innerHTML = `
      <article class="plugin-card">
        <div class="plugin-name">暂无插件</div>
        <p class="plugin-meta stack-empty">当前没有发现可展示的扩展玩法。</p>
      </article>
    `;
    return;
  }

  for (const item of items) {
    const hasError = Boolean(item.error);
    const disablePending = Boolean(item.runtime_disable_pending);
    const migration = item.migration_summary || {};
    const installScopeText = item.install_scope === "runtime" ? "运行时插件" : "内置插件";
    const pluginTypeText = item.plugin_type === "core"
      ? "核心扩展"
      : item.plugin_type === "builtin"
        ? "内建插件"
        : "运行时玩法";
    const permissionsText = item.permissions?.length ? item.permissions.join("、") : "未声明";
    let stateText = "未启用";
    let tone = "unknown";
    if (hasError) {
      stateText = "启动异常";
      tone = "danger";
    } else if (item.requires_container_rebuild && !item.loaded) {
      stateText = "待重建";
      tone = "pending";
    } else if (disablePending) {
      stateText = "停用待重启";
      tone = "pending";
    } else if (item.loaded) {
      stateText = "已加载";
      tone = "normal";
    } else if (item.enabled) {
      stateText = "待命";
      tone = "pending";
    }
    const card = document.createElement("article");
    card.className = "plugin-card";

    const actions = [];
    actions.push(
      `<button type="button" class="ghost-button" data-plugin-enable="${escapeHtml(item.id)}" data-plugin-enabled="${item.enabled ? "1" : "0"}">
        ${item.enabled ? "禁用插件" : "启用插件"}
      </button>`
    );
    if (item.admin_path) {
      actions.push(`<a class="ghost-button" href="${escapeHtml(withReturnTo(item.admin_path))}">打开插件后台</a>`);
    }
    if (item.miniapp_path && item.enabled) {
      actions.push(`<a class="ghost-button" href="${escapeHtml(item.miniapp_path)}">打开插件页面</a>`);
      actions.push(
        `<button type="button" class="ghost-button" data-plugin-toggle="${escapeHtml(item.id)}" data-plugin-visible="${item.bottom_nav_visible ? "1" : "0"}">
          ${item.bottom_nav_visible ? "从首页底栏隐藏" : "显示到首页底栏"}
        </button>`
      );
    }

    card.innerHTML = `
      <div class="plugin-card-top">
        <div class="plugin-name">${escapeHtml(item.name)}</div>
        <span class="badge badge--${escapeHtml(tone)}">${escapeHtml(stateText)}</span>
      </div>
      <p class="plugin-meta">${escapeHtml(item.description || "暂无描述")}</p>
      <div class="plugin-meta">插件标识：${escapeHtml(item.id)} · 版本 ${escapeHtml(item.version)}</div>
      <div class="plugin-meta">来源：${escapeHtml(installScopeText)} · 类型：${escapeHtml(pluginTypeText)}</div>
      <div class="plugin-meta">默认状态：${item.manifest_enabled ? "启用" : "禁用"} · 当前状态：${item.enabled ? "启用" : "禁用"}</div>
      <div class="plugin-meta">权限声明：${escapeHtml(permissionsText)}</div>
      ${item.miniapp_path ? `<div class="plugin-meta">首页入口：${escapeHtml(item.miniapp_label || item.name)} · 底栏${item.bottom_nav_visible ? "已显示" : "已隐藏"}</div>` : ""}
      ${migration.supported ? `<div class="plugin-meta">插件迁移：已执行 ${escapeHtml(migration.applied ?? 0)} / ${escapeHtml(migration.total ?? 0)}${migration.pending ? ` · 待执行 ${escapeHtml(migration.pending)}` : ""}</div>` : ""}
      ${item.requires_restart ? `<div class="plugin-meta">说明：该插件声明本次安装或更新后需要重启才能完全生效。</div>` : ""}
      ${item.requires_container_rebuild ? `<div class="plugin-meta">说明：该插件需要重建 Docker 容器或补齐依赖后才能完全启用。</div>` : ""}
      ${item.permission_review_required ? `<div class="plugin-meta">权限审查：存在未登记权限 ${escapeHtml((item.unknown_permissions || []).join("、") || "未说明")}，建议先人工确认。</div>` : ""}
      ${item.missing_python_dependencies?.length ? `<div class="plugin-meta">缺少依赖：${escapeHtml(item.missing_python_dependencies.join("、"))}</div>` : ""}
      ${item.overrides_builtin ? `<div class="plugin-meta">说明：当前运行时插件已覆盖同名内置插件。</div>` : ""}
      ${disablePending ? `<div class="plugin-meta">说明：当前进程仍保留该插件，重启本女仆后会完全停用。</div>` : ""}
      ${item.error ? `<div class="plugin-meta">错误信息：${escapeHtml(item.error)}</div>` : ""}
      ${actions.length ? `<div class="plugin-actions">${actions.join("")}</div>` : ""}
    `;
    refs.pluginList.appendChild(card);
  }
}

function renderBotAccessBlocks(items) {
  refs.botBlockList.innerHTML = "";

  if (!items.length) {
    refs.botBlockList.innerHTML = `
      <article class="plugin-card">
        <div class="plugin-name">当前没有黑名单规则</div>
        <p class="plugin-meta stack-empty">加入黑名单后，Bot 会直接忽略该用户的消息、回调按钮和内联查询，Mini App 会返回 404。</p>
      </article>
    `;
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "plugin-card";
    card.innerHTML = `
      <div class="plugin-card-top">
        <div class="plugin-name">${escapeHtml(fmtBotBlockTarget(item))}</div>
        <span class="badge badge--danger">已禁止</span>
      </div>
      <div class="plugin-meta">规则 ID：${escapeHtml(item.id)} · 匹配方式：${escapeHtml(item.match_scope_text || "未知")}</div>
      <div class="plugin-meta">创建时间：${escapeHtml(fmtDateTime(item.created_at))}</div>
      <div class="plugin-meta">备注：${escapeHtml(item.note || "无")}</div>
      <div class="plugin-actions">
        <button type="button" data-bot-block-delete="${escapeHtml(item.id)}">移除限制</button>
      </div>
    `;
    refs.botBlockList.appendChild(card);
  }
}

function fillEditor(item) {
  const level = getLevelMeta(item.lv);
  state.selectedUser = item;

  document.querySelector("#field-tg").value = item.tg ?? "";
  document.querySelector("#field-lv").value = item.lv ?? "d";
  document.querySelector("#field-name").value = item.name ?? "";
  document.querySelector("#field-embyid").value = item.embyid ?? "";
  document.querySelector("#field-iv").value = item.iv ?? 0;
  document.querySelector("#field-us").value = item.us ?? 0;
  document.querySelector("#field-cr").value = toLocalValue(item.cr);
  document.querySelector("#field-ex").value = toLocalValue(item.ex);
  document.querySelector("#field-ch").value = toLocalValue(item.ch);

  refs.editorStatus.textContent = item.bot_access_blocked
    ? `当前正在编辑账号 ${item.tg} · ${item.lv_text || level.text} · 已加入 Bot 黑名单`
    : `当前正在编辑账号 ${item.tg} · ${item.lv_text || level.text}`;
  setSelectedUserPill(`正在编辑 ${actorLikeLabel(item)}`);
  syncEditorShortcut();
}

async function loadSummary() {
  const result = await api("/admin-api/summary");
  setSummary(result.data);
  setAutoUpdate(result.data.auto_update || {});
}

async function previewUserBatch(event) {
  event?.preventDefault?.();
  const payload = currentUserBatchPayload();
  try {
    const result = await runButtonAction(refs.userBatchPreviewButton, "预览中...", () => api("/admin-api/users/batch/preview", {
      method: "POST",
      body: JSON.stringify(payload)
    }));
    renderUserBatchPreview(result.data || {}, payload);
    setAdminStatus("批量账号操作预览已生成。", "warning");
  } catch (error) {
    const message = normalizeError(error, "批量操作预览失败。");
    invalidateUserBatchPreview(`预览失败：${message}`);
    if (refs.userBatchStatus) {
      refs.userBatchStatus.dataset.tone = "error";
    }
    setAdminStatus(`批量操作预览失败：${message}`, "error");
    showToast(`预览失败：${message}`, "error");
    await popup("预览失败", message, "error");
  }
}

async function applyUserBatch() {
  const preview = state.userBatchPreview;
  const payload = currentUserBatchPayload();
  if (!preview || preview.payloadKey !== userBatchPayloadKey(payload)) {
    const message = "当前批量条件已经变更，请先重新预览。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    await popup("需要重新预览", message, "warning");
    return;
  }

  const affectedCount = Number(preview.affected_count || 0);
  if (affectedCount <= 0) {
    const message = "当前条件没有匹配账号，无需执行。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    await popup("无需处理", message, "warning");
    return;
  }

  const dangerText = payload.action === "delete"
    ? "删除资格会删除这些用户的 Emby 服务账号，并把后台记录恢复为未注册状态。"
    : payload.action === "ban"
      ? "封禁账号会同步禁用这些用户的 Emby 服务账号。"
      : payload.target_level === "c"
        ? "设置为已封禁会同步禁用这些用户的 Emby 服务账号。"
        : "设置为白名单或正常用户会尝试恢复这些用户的 Emby 服务账号。";
  const confirmed = window.confirm(`确认对 ${affectedCount} 个账号执行“${preview.action_text}”吗？\n\n范围：${preview.scope_text}\n${dangerText}`);
  if (!confirmed) {
    return;
  }

  try {
    const result = await runButtonAction(refs.userBatchApplyButton, "执行中...", () => api("/admin-api/users/batch/apply", {
      method: "POST",
      body: JSON.stringify(payload)
    }));
    const data = result.data || {};
    const policy = data.policy_sync || {};
    const actionCount = payload.action === "delete"
      ? Number(data.deleted_count || data.updated_count || 0)
      : Number(data.updated_count || 0);
    let message = `批量操作完成：已处理 ${formatCount(actionCount)} 个账号。`;
    if (Number(policy.total || 0) > 0) {
      message += ` Emby 服务同步成功 ${formatCount(policy.success_count || 0)}/${formatCount(policy.total || 0)}${Number(policy.fail_count || 0) > 0 ? `，失败 ${formatCount(policy.fail_count)}` : ""}。`;
    }
    state.userBatchPreview = null;
    if (refs.userBatchPreview) {
      refs.userBatchPreview.classList.add("hidden");
      refs.userBatchPreview.innerHTML = "";
    }
    if (refs.userBatchStatus) {
      refs.userBatchStatus.textContent = message;
      refs.userBatchStatus.dataset.tone = Number(policy.fail_count || 0) > 0 ? "warning" : "success";
    }
    await Promise.all([loadSummary(), loadUsers(), refreshSelectedUser().catch(() => null)]);
    setAdminStatus(message, Number(policy.fail_count || 0) > 0 ? "warning" : "success");
    showToast("批量账号操作完成。", Number(policy.fail_count || 0) > 0 ? "warning" : "success");
    await popup("批量操作完成", message, Number(policy.fail_count || 0) > 0 ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, "批量操作执行失败。");
    if (refs.userBatchStatus) {
      refs.userBatchStatus.textContent = `执行失败：${message}`;
      refs.userBatchStatus.dataset.tone = "error";
    }
    setAdminStatus(`批量操作执行失败：${message}`, "error");
    showToast(`执行失败：${message}`, "error");
    await popup("执行失败", message, "error");
  } finally {
    syncUserBatchControls();
  }
}

async function revokeAllWhitelistUsers() {
  const whitelistCount = Number(state.summary?.whitelist_users || 0);
  if (whitelistCount <= 0) {
    const message = "当前没有白名单账号，无需批量取消。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    await popup("无需处理", message, "warning");
    return;
  }

  const confirmed = window.confirm(`确认取消全部 ${whitelistCount} 个白名单账号的权限吗？\n\n这些账号会从 a 级降为 b 级正常用户。`);
  if (!confirmed) {
    return;
  }

  try {
    const result = await runButtonAction(refs.whitelistRevokeAll, "处理中...", () => api("/admin-api/users/whitelist/revoke-all", {
      method: "POST"
    }));
    const updatedCount = Number(result.data?.updated_count || 0);
    await Promise.all([loadSummary(), loadUsers(), refreshSelectedUser().catch(() => null)]);
    const message = updatedCount > 0
      ? `已批量取消 ${updatedCount} 个白名单账号，全部恢复为 b 级正常用户。`
      : "当前没有白名单账号，无需批量取消。";
    if (refs.whitelistRevokeStatus) {
      refs.whitelistRevokeStatus.textContent = message;
    }
    setAdminStatus(message, updatedCount > 0 ? "success" : "warning");
    showToast(message, updatedCount > 0 ? "success" : "warning");
    await popup(updatedCount > 0 ? "处理完成" : "无需处理", message, updatedCount > 0 ? "success" : "warning");
  } catch (error) {
    const message = normalizeError(error, "批量取消白名单失败。");
    if (refs.whitelistRevokeStatus) {
      refs.whitelistRevokeStatus.textContent = `处理失败：${message}`;
    }
    setAdminStatus(`批量取消白名单失败：${message}`, "error");
    showToast(`批量取消白名单失败：${message}`, "error");
    await popup("处理失败", message, "error");
  }
}

async function toggleEmbyService() {
  const isSuspended = Boolean(state.summary?.emby_service_suspended);
  const action = isSuspended ? "恢复" : "暂停";
  const activeCount = Number(state.summary?.active_accounts || 0);
  const confirmMsg = isSuspended
    ? `确认恢复 Emby 服务吗？\n\n恢复后，所有 ${activeCount} 个有效账号将重新可用。`
    : `⚠️ 确认暂停 Emby 服务吗？\n\n这将在 Emby 服务器端禁用全部 ${activeCount} 个账号，所有用户都将无法播放，即使手机已保存线路也不行。`;

  if (!window.confirm(confirmMsg)) {
    return;
  }

  try {
    const result = await runButtonAction(refs.embyServiceToggle, "处理中...", () => api("/admin-api/emby-service/toggle", {
      method: "POST"
    }));
    const d = result.data || {};
    syncEmbyServiceUI(d.emby_service_suspended);
    if (state.summary) {
      state.summary.emby_service_suspended = d.emby_service_suspended;
    }
    const message = `已${d.action} Emby 服务，成功 ${d.success_count}/${d.total_accounts}${d.fail_count > 0 ? `，失败 ${d.fail_count}` : ""}。`;
    setAdminStatus(message, d.fail_count > 0 ? "warning" : "success");
    showToast(message, d.fail_count > 0 ? "warning" : "success");
    await popup(d.action + "完成", message, d.fail_count > 0 ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, `${action} Emby 服务失败。`);
    setAdminStatus(`${action}失败：${message}`, "error");
    showToast(`${action}失败：${message}`, "error");
    await popup("操作失败", message, "error");
  }
}

async function loadAutoUpdate() {
  const result = await api("/admin-api/system/auto-update");
  setAutoUpdate(result.data || {});
}

async function loadPlugins() {
  const result = await api("/admin-api/plugins");
  renderPlugins(result.data);
}

async function loadBotAccessBlocks() {
  const result = await api("/admin-api/bot-access-blocks");
  state.botAccessBlocks = result.data || [];
  renderBotAccessBlocks(state.botAccessBlocks);
}

function currentModerationChat() {
  return state.moderationChats.find((item) => Number(item.chat_id) === Number(state.selectedModerationChatId)) || null;
}

function requireModerationChat() {
  const chat = currentModerationChat();
  if (chat) {
    return chat;
  }
  const message = "请先选择一个可管理的群组。";
  setModerationStatus(message, "warning");
  setAdminStatus(message, "warning");
  showToast(message, "warning");
  return null;
}

function requireModerationTarget() {
  if (state.selectedModerationTarget) {
    return state.selectedModerationTarget;
  }
  const message = "请先搜索并选择一个群成员。";
  if (refs.moderationTargetStatus) {
    refs.moderationTargetStatus.textContent = message;
    refs.moderationTargetStatus.dataset.tone = "warning";
  }
  setAdminStatus(message, "warning");
  showToast(message, "warning");
  return null;
}

async function loadModerationWarnings() {
  const chat = requireModerationChat();
  if (!chat) {
    state.moderationWarnings = [];
    renderModerationWarnings([]);
    return;
  }

  const params = new URLSearchParams({
    chat_id: String(chat.chat_id),
    limit: "100"
  });
  const result = await api(`/admin-api/moderation/warnings?${params.toString()}`);
  state.moderationWarnings = result.data?.items || [];
  setModerationSettings(result.data?.settings || chat.settings || {});
  renderModerationWarnings(state.moderationWarnings);
}

async function loadModerationChats() {
  const result = await api("/admin-api/moderation/chats");
  state.moderationChats = result.data || [];

  if (refs.moderationChatSelect) {
    refs.moderationChatSelect.innerHTML = "";
  }

  if (!state.moderationChats.length) {
    state.selectedModerationChatId = null;
    state.moderationMembers = [];
    state.moderationWarnings = [];
    fillModerationTarget(null);
    renderModerationMembers([]);
    renderModerationWarnings([]);
    setModerationStatus("当前没有可管理群组，请先在配置中填写 `group` 群列表。", "warning");
    return;
  }

  const selectedExists = state.moderationChats.some((item) => Number(item.chat_id) === Number(state.selectedModerationChatId));
  if (!selectedExists) {
    state.selectedModerationChatId = Number(state.moderationChats[0].chat_id);
    fillModerationTarget(null);
  }

  state.moderationChats.forEach((item) => {
    const option = document.createElement("option");
    option.value = String(item.chat_id);
    option.textContent = item.username
      ? `${item.title} (${item.username.startsWith("@") ? item.username : `@${item.username}`})`
      : `${item.title} (${item.chat_id})`;
    refs.moderationChatSelect?.appendChild(option);
  });
  if (refs.moderationChatSelect) {
    refs.moderationChatSelect.value = String(state.selectedModerationChatId);
  }

  const chat = currentModerationChat();
  setModerationSettings(chat?.settings || {});
  setModerationStatus(
    chat
      ? `当前正在管理 ${chat.title}，活跃警告 ${formatCount(chat.active_warning_count || 0)} 条。`
      : "请选择一个群组开始管理。",
    "info"
  );
  await loadModerationWarnings();
}

async function searchModerationMembers() {
  const chat = requireModerationChat();
  if (!chat) {
    return;
  }

  const keyword = refs.moderationSearchInput?.value.trim() || "";
  state.moderationSearchQuery = keyword;
  if (!keyword) {
    state.moderationMembers = [];
    renderModerationMembers([]);
    setModerationStatus("请输入 TG 昵称、@username 或 TGID 后再搜索。", "warning");
    return;
  }

  const params = new URLSearchParams({
    chat_id: String(chat.chat_id),
    q: keyword,
    limit: "20"
  });
  const result = await api(`/admin-api/moderation/members/search?${params.toString()}`);
  state.moderationMembers = result.data?.items || [];
  setModerationSettings(result.data?.settings || chat.settings || {});
  renderModerationMembers(state.moderationMembers);
  setModerationStatus(
    state.moderationMembers.length
      ? `已在 ${chat.title} 中找到 ${formatCount(state.moderationMembers.length)} 个匹配成员。`
      : `在 ${chat.title} 中没有找到“${keyword}”的匹配成员。`,
    state.moderationMembers.length ? "success" : "warning"
  );
}

async function refreshModerationAfterAction(options = {}) {
  const { reloadMembers = true } = options;
  await loadModerationChats();
  if (reloadMembers && state.moderationSearchQuery) {
    await searchModerationMembers();
  }
  if (state.selectedModerationTarget) {
    const targetTg = Number(state.selectedModerationTarget.tg);
    const refreshed = state.moderationMembers.find((item) => Number(item.tg) === targetTg)
      || state.moderationWarnings.find((item) => Number(item.tg) === targetTg);
    if (refreshed) {
      fillModerationTarget(refreshed);
      renderModerationMembers(state.moderationMembers);
    }
  }
}

async function loadUsers() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize)
  });

  if (state.query) {
    params.set("q", state.query);
  }

  const result = await api(`/admin-api/users?${params.toString()}`);
  const { items, page, page_size, total } = result.data;
  state.visibleUsers = items;
  renderUsers(items);

  const totalPages = Math.max(1, Math.ceil(total / page_size));
  refs.pageLabel.textContent = `第 ${page} 页 / 共 ${totalPages} 页`;
  refs.prevPage.disabled = page <= 1;
  refs.nextPage.disabled = page >= totalPages;
}

async function loadCodes() {
  const params = new URLSearchParams({
    status: state.codeStatus,
    page: String(state.codesPage),
    page_size: String(state.codesPageSize)
  });

  const result = await api(`/admin-api/codes?${params.toString()}`);
  const { items, page, page_size, total, summary } = result.data;
  state.visibleCodes = items;
  setCodeSummary(summary);
  renderCodes(items);

  const totalPages = Math.max(1, Math.ceil(total / page_size));
  refs.codePageLabel.textContent = `第 ${page} 页 / 共 ${totalPages} 页`;
  refs.codePrevPage.disabled = page <= 1;
  refs.codeNextPage.disabled = page >= totalPages;
}

async function loadInvites() {
  const params = new URLSearchParams({
    q: state.inviteSearchQuery || "",
    account_page: String(state.inviteOpenPage || 1),
    group_page: String(state.inviteGroupPage || 1),
    page_size: String(state.invitePageSize || 20)
  });
  const result = await api(`/admin-api/invites?${params.toString()}`);
  applyInviteBundle(result.data || {});
}

async function loadUser(tg) {
  try {
    const result = await api(`/admin-api/users/${tg}`);
    state.selectedTg = tg;
    fillEditor(result.data);
    renderUsers(state.visibleUsers);
    setAdminStatus(`已载入账号 ${tg} 的资料，可以开始编辑。`);
    focusSection("editor-section");
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`载入用户资料失败：${message}`, "error");
    showToast(`载入用户资料失败：${message}`, "error");
    await popup("载入失败", message, "error");
  }
}

async function refreshSelectedUser() {
  if (!state.selectedTg) {
    return;
  }

  const result = await api(`/admin-api/users/${state.selectedTg}`);
  fillEditor(result.data);
}

async function refreshDashboard() {
  await Promise.all([loadSummary(), loadAutoUpdate(), loadPlugins(), loadBotAccessBlocks(), loadModerationChats(), loadUsers(), loadCodes(), loadInvites()]);
}

async function tryTelegramAuth() {
  if (!state.telegramInitData) {
    return false;
  }

  state.authMode = "telegram";
  setAuthMode("telegram");

  const name = state.telegramUser?.first_name || "主人";
  setAuthCopy("主人直登", `正在以主人身份验证，当前账号：${name}`);
  setAdminStatus("正在通过主人直登加载后台数据。");

  try {
    await refreshDashboard();
    refs.tokenPanel.open = false;
    setAuthCopy("主人直登", `已通过主人身份登录，当前账号：${name}`);
    setAdminStatus("主人身份验证通过，后台数据已同步。", "success");
    return true;
  } catch (error) {
    const message = normalizeError(error);
    state.authMode = null;
    setAuthMode(null);
    setAuthCopy("主人登录", `自动登录失败：${message}`);
    setAdminStatus("自动登录失败，可改用后台令牌继续访问。", "warning");
    refs.tokenPanel.open = true;
    return false;
  }
}

async function tryTokenAuth(options = {}) {
  const { notify = false } = options;
  if (!state.token) {
    return false;
  }

  state.authMode = "token";
  setAuthMode("token");
  setAuthCopy("令牌登录", "正在验证后台令牌...");
  setAdminStatus("正在验证后台令牌并加载管理数据。");

  try {
    await refreshDashboard();
    setAuthCopy("令牌登录", "后台令牌验证通过，当前页面已连接管理接口。");
    setAdminStatus("后台令牌验证通过，数据已加载。", "success");
    if (notify) {
      showToast("后台令牌验证通过。", "success");
      await popup("验证通过", "后台令牌验证通过，当前页面已连接管理接口。", "success");
    }
    return true;
  } catch (error) {
    const message = normalizeError(error);
    state.authMode = null;
    setAuthMode(null);
    setAuthCopy("主人登录", `令牌登录失败：${message}`);
    setAdminStatus("后台令牌验证失败，请检查后重试。", "error");
    refs.tokenPanel.open = true;
    if (notify) {
      showToast(`令牌登录失败：${message}`, "error");
      await popup("验证失败", message, "error");
    }
    return false;
  }
}

async function saveUser(event) {
  event.preventDefault();

  if (!state.selectedTg) {
    refs.editorStatus.textContent = "请先从用户列表选择一个账号，再保存修改。";
    showToast("请先从用户列表选择一个账号。", "warning");
    await popup("无法保存", "请先从用户列表选择一个账号，再保存修改。", "warning");
    return;
  }

  const payload = {
    lv: document.querySelector("#field-lv").value,
    name: document.querySelector("#field-name").value || null,
    embyid: document.querySelector("#field-embyid").value || null,
    iv: Number(document.querySelector("#field-iv").value || 0),
    us: Number(document.querySelector("#field-us").value || 0),
    cr: fromLocalValue(document.querySelector("#field-cr").value),
    ex: fromLocalValue(document.querySelector("#field-ex").value),
    ch: fromLocalValue(document.querySelector("#field-ch").value)
  };

  try {
    const result = await runButtonAction(refs.saveUser, "正在保存...", () => api(`/admin-api/users/${state.selectedTg}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }));
    fillEditor(result.data);
    if (Array.isArray(state.visibleUsers) && result.data) {
      const savedTg = Number(result.data.tg ?? state.selectedTg);
      state.visibleUsers = state.visibleUsers.map((item) =>
        Number(item.tg) === savedTg ? { ...item, ...result.data } : item
      );
      renderUsers(state.visibleUsers);
    }
    loadSummary().catch(() => null);
    refs.editorStatus.textContent = `账号 ${state.selectedTg} 的资料已保存。`;
    setAdminStatus(`账号 ${state.selectedTg} 的资料已更新。`, "success");
    showToast(`账号 ${state.selectedTg} 已保存。`, "success");
    await popup("保存成功", `账号 ${state.selectedTg} 的资料已更新。`, "success");
  } catch (error) {
    const message = normalizeError(error);
    refs.editorStatus.textContent = `保存失败：${message}`;
    setAdminStatus(`保存失败：${message}`, "error");
    showToast(`保存失败：${message}`, "error");
    await popup("保存失败", message, "error");
  }
}

async function createBotAccessBlock(event) {
  event.preventDefault();

  const payload = {
    tg: refs.botBlockTg.value ? Number(refs.botBlockTg.value) : null,
    username: refs.botBlockUsername.value.trim() || null,
    note: refs.botBlockNote.value.trim() || null
  };

  if (!payload.tg && !payload.username) {
    const message = "TGID 和 TG 用户名至少需要填写一项。";
    refs.botBlockStatus.textContent = message;
    refs.botBlockStatus.dataset.tone = "error";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    await popup("无法加入黑名单", message, "warning");
    return;
  }

  try {
    const result = await runButtonAction(refs.botBlockSubmit, "提交中...", () => api("/admin-api/bot-access-blocks", {
      method: "POST",
      body: JSON.stringify(payload)
    }));
    refs.botBlockForm.reset();
    refs.botBlockStatus.textContent = `已加入黑名单：${fmtBotBlockTarget(result.data)}`;
    refs.botBlockStatus.dataset.tone = "info";
    await Promise.all([loadBotAccessBlocks(), loadUsers(), refreshSelectedUser().catch(() => null)]);
    setAdminStatus(`已禁止 ${fmtBotBlockTarget(result.data)} 使用 Bot。`, "success");
    showToast(`已禁止 ${fmtBotBlockTarget(result.data)} 使用 Bot。`, "success");
    await popup("已加入黑名单", `规则已生效：${fmtBotBlockTarget(result.data)}。Bot 将不再响应该用户的消息、按钮和内联查询，Mini App 会返回 404。`, "success");
  } catch (error) {
    const message = normalizeError(error);
    refs.botBlockStatus.textContent = `加入黑名单失败：${message}`;
    refs.botBlockStatus.dataset.tone = "error";
    setAdminStatus(`加入 Bot 黑名单失败：${message}`, "error");
    showToast(`加入黑名单失败：${message}`, "error");
    await popup("加入失败", message, "error");
  }
}

async function deleteBotAccessBlock(blockId) {
  if (!blockId) {
    return;
  }

  const target = state.botAccessBlocks.find((item) => String(item.id) === String(blockId));
  const confirmed = window.confirm(`确认移除这条 Bot 黑名单规则吗？\n\n${fmtBotBlockTarget(target)}`);
  if (!confirmed) {
    return;
  }

  try {
    const result = await api(`/admin-api/bot-access-blocks/${encodeURIComponent(blockId)}`, {
      method: "DELETE"
    });
    refs.botBlockStatus.textContent = `已移除黑名单：${fmtBotBlockTarget(result.data?.item)}`;
    refs.botBlockStatus.dataset.tone = "info";
    await Promise.all([loadBotAccessBlocks(), loadUsers(), refreshSelectedUser().catch(() => null)]);
    setAdminStatus(`已解除 ${fmtBotBlockTarget(result.data?.item)} 的 Bot 限制。`, "success");
    showToast(`已解除 ${fmtBotBlockTarget(result.data?.item)} 的 Bot 限制。`, "success");
    await popup("已移除黑名单", `规则已删除：${fmtBotBlockTarget(result.data?.item)}。`, "success");
  } catch (error) {
    const message = normalizeError(error);
    refs.botBlockStatus.textContent = `移除黑名单失败：${message}`;
    refs.botBlockStatus.dataset.tone = "error";
    setAdminStatus(`移除 Bot 黑名单失败：${message}`, "error");
    showToast(`移除黑名单失败：${message}`, "error");
    await popup("移除失败", message, "error");
  }
}

function useSelectedUserForBotBlock() {
  const item = state.selectedUser;
  if (!item) {
    const message = "请先从用户列表选择一个账号，再带入黑名单表单。";
    refs.botBlockStatus.textContent = message;
    refs.botBlockStatus.dataset.tone = "error";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }

  refs.botBlockTg.value = item.tg ?? "";
  refs.botBlockUsername.value = item.tg_username ? `@${item.tg_username}` : "";
  refs.botBlockStatus.textContent = `已带入当前选中账号：${fmtBotBlockTarget({ tg: item.tg, username: item.tg_username })}`;
  refs.botBlockStatus.dataset.tone = "info";
  focusSection("bot-block-section");
  showToast("已带入当前选中账号。", "success");
}

async function createCodes(event) {
  event.preventDefault();

  const payload = {
    days: Number(document.querySelector("#code-create-days").value || 0),
    count: Number(document.querySelector("#code-create-count").value || 0),
    method: document.querySelector("#code-create-method").value,
    type: document.querySelector("#code-create-type").value,
    usage_limit: Number(document.querySelector("#code-create-usage-limit").value || 1),
    suffix_mode: refs.codeCreateSuffixMode.value,
    suffix_text: refs.codeCreateSuffixText.value.trim() || null
  };

  try {
    const result = await runButtonAction(refs.codeCreateSubmit, "生成中...", () => api("/admin-api/codes", {
      method: "POST",
      body: JSON.stringify(payload)
    }));
    renderCodeCreateResult(result.data);
    state.selectedCodes.clear();
    await loadCodes();
    setAdminStatus(`${result.data.type_text}已生成 ${result.data.count} 个。`, "success");
    showToast(`${result.data.type_text}已生成 ${result.data.count} 个。`, "success");
    focusSection("codes-section", false);
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`生成注册码失败：${message}`, "error");
    showToast(`生成失败：${message}`, "error");
    await popup("生成失败", message, "error");
  }
}

async function saveAutoUpdate(event) {
  event.preventDefault();

  const payload = {
    status: refs.autoUpdateStatus.checked,
    git_repo: refs.autoUpdateGitRepo.value.trim() || null,
    docker_image: refs.autoUpdateDockerImage.value.trim() || null,
    compose_service: refs.autoUpdateComposeService.value.trim() || null,
    container_name: refs.autoUpdateContainerName.value.trim() || null,
    check_interval_minutes: Number(refs.autoUpdateInterval.value || 30)
  };

  try {
    const result = await runButtonAction(refs.autoUpdateSave, "保存中...", () => api("/admin-api/system/auto-update", {
      method: "PATCH",
      body: JSON.stringify(payload)
    }));
    setAutoUpdate(result.data || {});
    setAdminStatus("自动更新配置已保存。", "success");
    showToast("自动更新配置已保存。", "success");
    await popup("保存成功", "自动更新配置已保存，新的定时规则已经生效。", "success");
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`保存自动更新配置失败：${message}`, "error");
    showToast(`保存失败：${message}`, "error");
    await popup("保存失败", message, "error");
  }
}

async function saveModerationSettings(event) {
  event.preventDefault();
  const chat = requireModerationChat();
  if (!chat) {
    return;
  }

  const payload = {
    warn_threshold: Number(refs.moderationWarnThreshold?.value || 3),
    warn_action: refs.moderationWarnAction?.value || "mute",
    mute_minutes: Number(refs.moderationWarnMuteMinutes?.value || 60)
  };

  try {
    const result = await runButtonAction(refs.moderationSettingsSave, "保存中...", () => api(`/admin-api/moderation/settings/${encodeURIComponent(chat.chat_id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }));
    setModerationSettings(result.data || {});
    await loadModerationChats();
    setAdminStatus(`群组 ${chat.title} 的警告配置已更新。`, "success");
    setModerationStatus(`群组 ${chat.title} 的警告配置已更新。`, "success");
    showToast("警告配置已保存。", "success");
    await popup("保存成功", `群组 ${chat.title} 的警告配置已更新。`, "success");
  } catch (error) {
    const message = normalizeError(error, "保存群组警告配置失败。");
    setAdminStatus(`保存群组警告配置失败：${message}`, "error");
    setModerationStatus(`保存失败：${message}`, "error");
    showToast(`保存失败：${message}`, "error");
    await popup("保存失败", message, "error");
  }
}

async function moderationMuteAction(minutes) {
  const chat = requireModerationChat();
  const target = requireModerationTarget();
  if (!chat || !target) {
    return;
  }

  try {
    const result = await runButtonAction(minutes > 0 ? refs.moderationMuteButton : refs.moderationUnmuteButton, minutes > 0 ? "处理中..." : "解除中...", () => api("/admin-api/moderation/actions/mute", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        tg: target.tg,
        minutes
      })
    }));
    fillModerationTarget({ ...target, ...(result.data?.target || {}) });
    await refreshModerationAfterAction();
    const message = `${targetDisplayLabel(result.data?.target || target)} ${result.data?.result?.message || "操作已完成。"}`
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
    showToast(message, "success");
    await popup(minutes > 0 ? "禁言成功" : "解除禁言成功", message, "success");
  } catch (error) {
    const message = normalizeError(error, minutes > 0 ? "禁言失败。" : "解除禁言失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup(minutes > 0 ? "禁言失败" : "解除禁言失败", message, "error");
  }
}

async function moderationKickAction() {
  const chat = requireModerationChat();
  const target = requireModerationTarget();
  if (!chat || !target) {
    return;
  }

  const confirmed = window.confirm(`确认将 ${targetDisplayLabel(target)} 踢出当前群吗？`);
  if (!confirmed) {
    return;
  }

  try {
    const result = await runButtonAction(refs.moderationKickButton, "踢出中...", () => api("/admin-api/moderation/actions/kick", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        tg: target.tg
      })
    }));
    await refreshModerationAfterAction();
    const message = `${targetDisplayLabel(result.data?.target || target)} ${result.data?.result?.message || "已踢出群组。"}`
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
    showToast(message, "success");
    await popup("踢出成功", message, "success");
  } catch (error) {
    const message = normalizeError(error, "踢出失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("踢出失败", message, "error");
  }
}

async function moderationWarnAction() {
  const chat = requireModerationChat();
  const target = requireModerationTarget();
  if (!chat || !target) {
    return;
  }

  try {
    const result = await runButtonAction(refs.moderationWarnButton, "警告中...", () => api("/admin-api/moderation/actions/warn", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        tg: target.tg,
        reason: refs.moderationReason?.value.trim() || null
      })
    }));
    fillModerationTarget({ ...target, ...(result.data?.target || {}), warn_count: result.data?.warning?.warn_count || target.warn_count || 0 });
    await refreshModerationAfterAction();
    const warning = result.data?.warning || {};
    let message = `${targetDisplayLabel(result.data?.target || target)} 当前警告 ${warning.warn_count || 0} / ${result.data?.settings?.warn_threshold || 0}。`;
    if (result.data?.action_triggered && result.data?.action_result?.message) {
      message += ` 已自动执行：${result.data.action_result.message}`;
    } else if (result.data?.action_error) {
      message += ` 自动处罚失败：${result.data.action_error}`;
    }
    setAdminStatus(message, result.data?.action_error ? "warning" : "success");
    setModerationStatus(message, result.data?.action_error ? "warning" : "success");
    showToast(message, result.data?.action_error ? "warning" : "success");
    await popup("警告已记录", message, result.data?.action_error ? "warning" : "success");
  } catch (error) {
    const message = normalizeError(error, "警告失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("警告失败", message, "error");
  }
}

async function moderationClearWarnAction() {
  const chat = requireModerationChat();
  const target = requireModerationTarget();
  if (!chat || !target) {
    return;
  }

  try {
    const result = await runButtonAction(refs.moderationClearWarnButton, "清空中...", () => api("/admin-api/moderation/actions/clear-warn", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        tg: target.tg
      })
    }));
    fillModerationTarget({ ...target, ...(result.data?.target || {}), warn_count: 0 });
    await refreshModerationAfterAction();
    const removed = Boolean(result.data?.result?.removed);
    const message = removed
      ? `${targetDisplayLabel(result.data?.target || target)} 的警告已清空。`
      : `${targetDisplayLabel(result.data?.target || target)} 当前没有警告记录。`;
    setAdminStatus(message, removed ? "success" : "warning");
    setModerationStatus(message, removed ? "success" : "warning");
    showToast(message, removed ? "success" : "warning");
    await popup(removed ? "已清空警告" : "无需处理", message, removed ? "success" : "warning");
  } catch (error) {
    const message = normalizeError(error, "清空警告失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("清空失败", message, "error");
  }
}

async function moderationTitleAction() {
  const chat = requireModerationChat();
  const target = requireModerationTarget();
  if (!chat || !target) {
    return;
  }

  const title = refs.moderationTitle?.value.trim() || "";
  if (!title) {
    const message = "请先填写管理员头衔。";
    setModerationStatus(message, "warning");
    showToast(message, "warning");
    await popup("缺少头衔", message, "warning");
    return;
  }

  try {
    const result = await runButtonAction(refs.moderationTitleButton, "设置中...", () => api("/admin-api/moderation/actions/title", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        tg: target.tg,
        title
      })
    }));
    fillModerationTarget({ ...target, ...(result.data?.target || {}) });
    const message = `${targetDisplayLabel(result.data?.target || target)} ${result.data?.result?.message || "头衔已更新。"}`
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
    showToast(message, "success");
    await popup("设置成功", message, "success");
  } catch (error) {
    const message = normalizeError(error, "设置头衔失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("设置失败", message, "error");
  }
}

async function moderationPinAction() {
  const chat = requireModerationChat();
  if (!chat) {
    return;
  }

  const messageId = Number(refs.moderationMessageId?.value || 0);
  if (!messageId) {
    const message = "请先填写需要置顶的消息 ID。";
    setModerationStatus(message, "warning");
    showToast(message, "warning");
    await popup("缺少消息 ID", message, "warning");
    return;
  }

  try {
    const result = await runButtonAction(refs.moderationPinButton, "置顶中...", () => api("/admin-api/moderation/actions/pin", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        message_id: messageId,
        disable_notification: true
      })
    }));
    const message = result.data?.message || `消息 ${messageId} 已置顶。`;
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
    showToast(message, "success");
    await popup("置顶成功", message, "success");
  } catch (error) {
    const message = normalizeError(error, "置顶消息失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("置顶失败", message, "error");
  }
}

async function moderationUnpinAction() {
  const chat = requireModerationChat();
  if (!chat) {
    return;
  }

  const messageId = Number(refs.moderationMessageId?.value || 0) || null;
  try {
    const result = await runButtonAction(refs.moderationUnpinButton, "取消中...", () => api("/admin-api/moderation/actions/unpin", {
      method: "POST",
      body: JSON.stringify({
        chat_id: chat.chat_id,
        message_id: messageId
      })
    }));
    const message = result.data?.message || "已取消置顶。";
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
    showToast(message, "success");
    await popup("已取消置顶", message, "success");
  } catch (error) {
    const message = normalizeError(error, "取消置顶失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("取消失败", message, "error");
  }
}

async function deleteSelectedCodes() {
  const codes = [...state.selectedCodes];
  if (!codes.length) {
    setAdminStatus("请先勾选需要删除的注册码。", "warning");
    showToast("请先勾选需要删除的注册码。", "warning");
    return;
  }

  const confirmed = window.confirm(`确认删除选中的 ${codes.length} 个注册码吗？已使用记录也会一并删除。`);
  if (!confirmed) {
    return;
  }

  try {
    const result = await runButtonAction(refs.codeDeleteSelected, "删除中...", () => api("/admin-api/codes/delete", {
      method: "POST",
      body: JSON.stringify({ codes })
    }));
    state.selectedCodes.clear();
    await loadCodes();
    setAdminStatus(`已删除 ${result.data.deleted} 个注册码。`, "success");
    showToast(`已删除 ${result.data.deleted} 个注册码。`, "success");
    await popup("删除完成", `已删除 ${result.data.deleted} 个注册码，对应使用记录删除 ${result.data.redeem_deleted} 条。`, "success");
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`删除注册码失败：${message}`, "error");
    showToast(`删除失败：${message}`, "error");
    await popup("删除失败", message, "error");
  }
}

async function saveInviteSettings(event) {
  event.preventDefault();
  try {
    const result = await runButtonAction(refs.inviteSettingsSave, "保存中...", () => api("/admin-api/invites/settings", {
      method: "PATCH",
      body: JSON.stringify({
        enabled: Boolean(refs.inviteEnabled?.checked),
        target_chat_id: Number(refs.inviteTargetChatId?.value || 0) || null,
        expire_hours: Number(refs.inviteExpireHours?.value || 24),
        account_open_days: Number(refs.inviteAccountOpenDays?.value || 30),
        strict_target: Boolean(refs.inviteGroupVerificationEnabled?.checked),
        group_verification_enabled: Boolean(refs.inviteGroupVerificationEnabled?.checked),
        channel_verification_enabled: Boolean(refs.inviteChannelVerificationEnabled?.checked)
      })
    }));
    applyInviteBundle(result.data || {});
    setAdminStatus("邀请功能设置已保存。", "success");
    showToast("邀请设置已保存。", "success");
  } catch (error) {
    const message = normalizeError(error, "保存邀请设置失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("保存失败", message, "error");
  }
}

async function grantInviteCredits(event) {
  event.preventDefault();
  const message = "入群资格已改为观影用户自动拥有一次，不再需要后台发放。";
  if (refs.inviteGrantStatus) refs.inviteGrantStatus.textContent = message;
  setAdminStatus(message, "warning");
  showToast(message, "warning");
  return;
  const ownerTg = Number(refs.inviteGrantTg?.value || 0);
  if (!ownerTg) {
    const message = "请先填写需要赠送的用户 TGID。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }
  try {
    const result = await runButtonAction(refs.inviteGrantSubmit, "发放中...", () => api("/admin-api/invites/credits", {
      method: "POST",
      body: JSON.stringify({
        owner_tg: ownerTg,
        count: Number(refs.inviteGrantCount?.value || 1),
        credit_type: "group_join",
        note: refs.inviteGrantNote?.value?.trim() || ""
      })
    }));
    applyInviteBundle(result.data || {});
    const count = result.data?.last_granted?.length || 0;
    const message = `已向 TG ${ownerTg} 发放 ${formatCount(count)} 个入群资格。`;
    if (refs.inviteGrantStatus) refs.inviteGrantStatus.textContent = message;
    setAdminStatus(message, "success");
    showToast(message, "success");
  } catch (error) {
    const message = normalizeError(error, "赠送入群资格失败。");
    if (refs.inviteGrantStatus) refs.inviteGrantStatus.textContent = message;
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("赠送失败", message, "error");
  }
}

function useSelectedUserForInviteGrant() {
  if (!state.selectedUser?.tg) {
    const message = "请先在用户检索中选中一个用户。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }
  refs.inviteGrantTg.value = state.selectedUser.tg;
  focusSection("invites-section");
}

function useSelectedUserForInviteOpenGrant() {
  if (!state.selectedUser?.tg) {
    const message = "请先在用户检索中选中一个用户。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }
  refs.inviteOpenCreateInviter.value = state.selectedUser.tg;
  focusSection("invites-section");
}

async function grantInviteOpenCredits(event) {
  event.preventDefault();
  const message = "注册资格已改为申请制，请在下方开通申请关系中审核，或使用管理员代发。";
  if (refs.inviteOpenGrantStatus) refs.inviteOpenGrantStatus.textContent = message;
  setAdminStatus(message, "warning");
  showToast(message, "warning");
  return;
  const ownerTg = Number(refs.inviteOpenGrantTg?.value || 0);
  if (!ownerTg) {
    const message = "请先填写需要赠送注册资格的用户 TGID。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }
  try {
    const result = await runButtonAction(refs.inviteOpenGrantSubmit, "发放中...", () => api("/admin-api/invites/credits", {
      method: "POST",
      body: JSON.stringify({
        owner_tg: ownerTg,
        count: 1,
        credit_type: "account_open",
        invite_days: Number(refs.inviteOpenGrantDays?.value || refs.inviteAccountOpenDays?.value || 30),
        note: refs.inviteOpenGrantNote?.value?.trim() || ""
      })
    }));
    applyInviteBundle(result.data || {});
    const message = `已向 TG ${ownerTg} 发放 1 个注册资格。`;
    if (refs.inviteOpenGrantStatus) refs.inviteOpenGrantStatus.textContent = message;
    setAdminStatus(message, "success");
    showToast(message, "success");
  } catch (error) {
    const message = normalizeError(error, "赠送注册资格失败。");
    if (refs.inviteOpenGrantStatus) refs.inviteOpenGrantStatus.textContent = message;
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("赠送失败", message, "error");
  }
}

async function createAccountOpenInviteFromAdmin(event) {
  event.preventDefault();
  const inviterTg = Number(refs.inviteOpenCreateInviter?.value || 0);
  const inviteeTg = Number(refs.inviteOpenCreateInvitee?.value || 0);
  if (!inviterTg || !inviteeTg) {
    const message = "请填写邀请人 TGID 和被邀请人 TGID。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }
  try {
    const result = await runButtonAction(refs.inviteOpenCreateSubmit, "发放中...", () => api("/admin-api/invites/account-open/create", {
      method: "POST",
      body: JSON.stringify({
        inviter_tg: inviterTg,
        invitee_tg: inviteeTg,
        note: refs.inviteOpenCreateNote?.value?.trim() || ""
      })
    }));
    applyInviteBundle(result.data || {});
    const message = `已由 TG ${inviterTg} 向 TG ${inviteeTg} 发放注册资格。`;
    setAdminStatus(message, "success");
    showToast(message, "success");
  } catch (error) {
    const message = normalizeError(error, "代发注册资格失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("代发失败", message, "error");
  }
}

async function updateInviteQualification(eventOrOptions = {}) {
  if (eventOrOptions?.preventDefault) {
    eventOrOptions.preventDefault();
  }
  const ownerTg = Number(eventOrOptions.owner_tg || refs.inviteQualificationOwner?.value || 0);
  const creditType = eventOrOptions.credit_type || refs.inviteQualificationType?.value || "group_join";
  const enabled = eventOrOptions.enabled !== undefined
    ? Boolean(eventOrOptions.enabled)
    : refs.inviteQualificationEnabled?.value === "true";
  const reason = eventOrOptions.reason ?? refs.inviteQualificationReason?.value?.trim() ?? "";
  if (!ownerTg) {
    const message = "请先填写需要更改资格的用户 TGID。";
    setAdminStatus(message, "warning");
    showToast(message, "warning");
    return;
  }
  try {
    const result = await runButtonAction(refs.inviteQualificationSubmit, "更新中...", () => api("/admin-api/invites/qualification", {
      method: "PATCH",
      body: JSON.stringify({
        owner_tg: ownerTg,
        credit_type: creditType,
        enabled,
        reason
      })
    }));
    state.inviteSearchQuery = String(ownerTg);
    if (refs.inviteSearchInput) refs.inviteSearchInput.value = state.inviteSearchQuery;
    applyInviteBundle(result.data || {});
    const label = creditType === "account_open" ? "开通申请资格" : "入群资格";
    const message = `已${enabled ? "恢复" : "撤销"} TG ${ownerTg} 的${label}。`;
    setAdminStatus(message, "success");
    showToast(message, "success");
  } catch (error) {
    const message = normalizeError(error, "更新邀请资格失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("更新失败", message, "error");
  }
}

async function reviewAccountOpenInvite(recordId, action) {
  const section = inviteSection("account_open");
  const item = (section.records || []).find((row) => Number(row.id) === Number(recordId));
  let inviteDays = item?.invite_days || refs.inviteAccountOpenDays?.value || 30;
  let note = "";
  if (action === "approve") {
    const daysValue = window.prompt("通过申请并发放注册天数：", inviteDays);
    if (daysValue === null) return;
    inviteDays = Number(daysValue || inviteDays || 30);
    note = window.prompt("审核备注：", "审核通过") || "";
  } else if (action === "decline") {
    const confirmed = window.confirm(`确认拒绝开通申请 #${recordId} 吗？`);
    if (!confirmed) return;
    note = window.prompt("拒绝原因：", "后台拒绝") || "";
  } else if (action === "revoke") {
    const confirmed = window.confirm(`确认撤销开通申请 #${recordId} 吗？已发放但未注册的资格会扣回。`);
    if (!confirmed) return;
    note = window.prompt("撤销原因：", "后台撤销") || "";
  }
  try {
    const result = await api(`/admin-api/invites/account-open/records/${encodeURIComponent(recordId)}/review`, {
      method: "POST",
      body: JSON.stringify({
        action,
        invite_days: action === "approve" ? inviteDays : null,
        note
      })
    });
    applyInviteBundle(result.data || {});
    setAdminStatus(`开通申请 #${recordId} 已处理。`, "success");
    showToast("开通申请已处理。", "success");
  } catch (error) {
    const message = normalizeError(error, "处理开通申请失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("处理失败", message, "error");
  }
}

async function editInviteCredit(creditId, type = "group_join") {
  const section = inviteSection(type);
  const item = (section.credits || []).find((row) => Number(row.id) === Number(creditId));
  if (!item) return;
  const ownerValue = window.prompt("修改拥有人 TGID：", item.owner_tg || "");
  if (ownerValue === null) return;
  const noteValue = window.prompt("修改备注：", item.note || "");
  if (noteValue === null) return;
  const payload = {
    owner_tg: Number(ownerValue || item.owner_tg),
    note: noteValue
  };
  if (type === "account_open") {
    const daysValue = window.prompt("修改注册天数：", item.invite_days || refs.inviteAccountOpenDays?.value || 30);
    if (daysValue === null) return;
    payload.invite_days = Number(daysValue || item.invite_days || 30);
  }
  try {
    const result = await api(`/admin-api/invites/credits/${encodeURIComponent(creditId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
    applyInviteBundle(result.data || {});
    setAdminStatus(`邀请资格 #${creditId} 已更新。`, "success");
    showToast("邀请资格已更新。", "success");
  } catch (error) {
    const message = normalizeError(error, "编辑邀请资格失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("编辑失败", message, "error");
  }
}

async function deleteSelectedInviteCredits(type = "group_join") {
  const selected = inviteSelectedSet(type);
  const creditIds = [...selected];
  if (!creditIds.length) {
    setAdminStatus("请先选择需要删除的邀请资格。", "warning");
    showToast("请先选择需要删除的邀请资格。", "warning");
    return;
  }
  if (!window.confirm(`确认删除选中的 ${creditIds.length} 个未使用邀请资格吗？`)) {
    return;
  }
  try {
    const button = type === "account_open" ? refs.inviteOpenCreditDeleteSelected : refs.inviteCreditDeleteSelected;
    const result = await runButtonAction(button, "删除中...", () => api("/admin-api/invites/credits/delete", {
      method: "POST",
      body: JSON.stringify({ credit_ids: creditIds, reason: "后台删除" })
    }));
    selected.clear();
    applyInviteBundle(result.data || {});
    const payload = result.data?.delete_result || {};
    const message = `已删除 ${formatCount(payload.deleted || 0)} 个邀请资格${payload.skipped ? `，跳过 ${formatCount(payload.skipped)} 个已使用项` : ""}。`;
    setAdminStatus(message, "success");
    showToast(message, "success");
  } catch (error) {
    const message = normalizeError(error, "删除邀请资格失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("删除失败", message, "error");
  }
}

async function revokeInviteRecord(recordId) {
  if (!window.confirm("确认撤销这条邀请链接吗？")) {
    return;
  }
  try {
    const result = await api(`/admin-api/invites/records/${encodeURIComponent(recordId)}/revoke`, {
      method: "POST"
    });
    applyInviteBundle(result.data || {});
    setAdminStatus(`邀请 #${recordId} 已撤销。`, "success");
    showToast("邀请已撤销。", "success");
  } catch (error) {
    const message = normalizeError(error, "撤销邀请失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
    await popup("撤销失败", message, "error");
  }
}

function bindNavigation() {
  refs.navButtons.forEach((button) => {
    button.addEventListener("click", () => {
      focusSection(button.dataset.sectionTarget);
    });
  });

  document.querySelector("[data-open-all]")?.addEventListener("click", () => {
    toggleSections(true);
  });

  document.querySelector("[data-close-all]")?.addEventListener("click", () => {
    toggleSections(false);
  });
}

function syncSuffixField() {
  const fixed = refs.codeCreateSuffixMode.value === "fixed";
  refs.codeCreateSuffixText.disabled = !fixed;
  if (!fixed) {
    refs.codeCreateSuffixText.value = "";
  }
}

refs.codeCreateForm?.addEventListener("submit", createCodes);
refs.inviteSettingsForm?.addEventListener("submit", saveInviteSettings);
refs.inviteSearchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.inviteSearchQuery = refs.inviteSearchInput?.value?.trim() || "";
  state.inviteOpenPage = 1;
  state.inviteGroupPage = 1;
  try {
    await runButtonAction(refs.inviteSearchSubmit, "搜索中...", loadInvites);
    setAdminStatus("邀请关系搜索已完成。", "success");
  } catch (error) {
    const message = normalizeError(error, "搜索邀请关系失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
  }
});
refs.inviteQualificationForm?.addEventListener("submit", updateInviteQualification);
refs.inviteOpenGrantForm?.addEventListener("submit", grantInviteOpenCredits);
refs.inviteOpenGrantUseSelected?.addEventListener("click", useSelectedUserForInviteOpenGrant);
refs.inviteOpenCreateForm?.addEventListener("submit", createAccountOpenInviteFromAdmin);
refs.inviteGrantForm?.addEventListener("submit", grantInviteCredits);
refs.inviteGrantUseSelected?.addEventListener("click", useSelectedUserForInviteGrant);
refs.autoUpdateForm?.addEventListener("submit", saveAutoUpdate);
refs.moderationSettingsForm?.addEventListener("submit", saveModerationSettings);
refs.botBlockForm?.addEventListener("submit", createBotAccessBlock);
refs.botBlockUseSelected?.addEventListener("click", useSelectedUserForBotBlock);
refs.codeCreateSuffixMode?.addEventListener("change", syncSuffixField);
refs.moderationSearchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await runButtonAction(refs.moderationSearchSubmit, "搜索中...", searchModerationMembers);
    focusSection("moderation-section", false);
  } catch (error) {
    const message = normalizeError(error, "搜索群成员失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
    await popup("搜索失败", message, "error");
  }
});
refs.moderationRefresh?.addEventListener("click", async () => {
  try {
    await runButtonAction(refs.moderationRefresh, "刷新中...", async () => {
      await loadModerationChats();
      if (state.moderationSearchQuery) {
        await searchModerationMembers();
      }
    });
    const chat = currentModerationChat();
    const message = chat ? `群组 ${chat.title} 的管理数据已刷新。` : "群管理数据已刷新。";
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
    showToast(message, "success");
  } catch (error) {
    const message = normalizeError(error, "刷新群管理数据失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
  }
});
refs.moderationChatSelect?.addEventListener("change", async (event) => {
  state.selectedModerationChatId = Number(event.target.value || 0) || null;
  state.moderationMembers = [];
  fillModerationTarget(null);
  renderModerationMembers([]);
  try {
    await loadModerationWarnings();
    const chat = currentModerationChat();
    if (chat) {
      setModerationSettings(chat.settings || {});
      setModerationStatus(`已切换到 ${chat.title}。`, "success");
      setAdminStatus(`已切换到群组 ${chat.title} 的管理视图。`, "success");
    }
  } catch (error) {
    const message = normalizeError(error, "切换群组失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
  }
});
refs.moderationWarnAction?.addEventListener("change", () => {
  const isMute = (refs.moderationWarnAction?.value || "mute") === "mute";
  if (refs.moderationWarnMuteMinutes) {
    refs.moderationWarnMuteMinutes.disabled = !isMute;
  }
  if (refs.moderationSettingsStatus) {
    refs.moderationSettingsStatus.textContent = isMute
      ? `达到阈值后会自动禁言 ${formatCount(refs.moderationWarnMuteMinutes?.value || 60)} 分钟。`
      : "达到阈值后会自动踢出。";
  }
});
refs.moderationMuteButton?.addEventListener("click", () => moderationMuteAction(Number(refs.moderationMuteMinutes?.value || 0) || 0));
refs.moderationUnmuteButton?.addEventListener("click", () => moderationMuteAction(0));
refs.moderationKickButton?.addEventListener("click", moderationKickAction);
refs.moderationWarnButton?.addEventListener("click", moderationWarnAction);
refs.moderationClearWarnButton?.addEventListener("click", moderationClearWarnAction);
refs.moderationTitleButton?.addEventListener("click", moderationTitleAction);
refs.moderationPinButton?.addEventListener("click", moderationPinAction);
refs.moderationUnpinButton?.addEventListener("click", moderationUnpinAction);
refs.moderationWarningRefresh?.addEventListener("click", async () => {
  try {
    await runButtonAction(refs.moderationWarningRefresh, "刷新中...", loadModerationWarnings);
    const chat = currentModerationChat();
    const message = chat ? `${chat.title} 的警告列表已刷新。` : "警告列表已刷新。";
    setAdminStatus(message, "success");
    setModerationStatus(message, "success");
  } catch (error) {
    const message = normalizeError(error, "刷新警告列表失败。");
    setAdminStatus(message, "error");
    setModerationStatus(message, "error");
    showToast(message, "error");
  }
});
refs.moderationWarningList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-warning-pick]");
  if (!button) {
    return;
  }
  const tg = Number(button.dataset.warningPick || 0);
  const item = state.moderationWarnings.find((row) => Number(row.tg) === tg);
  if (!item) {
    return;
  }
  fillModerationTarget({
    chat_id: state.selectedModerationChatId,
    tg: item.tg,
    display_label: actorLikeLabel(item),
    display_name: item.tg_display_name,
    username: item.tg_username,
    status_text: "警告成员",
    warn_count: item.warn_count
  });
  renderModerationMembers(state.moderationMembers);
  focusSection("moderation-section", false);
});
refs.jumpEditorButton?.addEventListener("click", () => {
  if (!state.selectedTg) return;
  focusSection("editor-section");
});
refs.codeCreateCopy?.addEventListener("click", async () => {
  const value = refs.codeOutput.value.trim();
  if (!value) {
    return;
  }

  try {
    await navigator.clipboard.writeText(value);
    showToast("生成结果已复制。", "success");
  } catch (error) {
    showToast("复制失败，请手动选择内容。", "warning");
  }
});

refs.codeStatusButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    state.codeStatus = button.dataset.codeStatus || "all";
    state.codesPage = 1;
    try {
      await loadCodes();
      setActiveNav("codes-section");
      setAdminStatus(`注册码列表已切换到“${button.textContent}”。`);
    } catch (error) {
      const message = normalizeError(error);
      setAdminStatus(`加载注册码失败：${message}`, "error");
      showToast(`加载失败：${message}`, "error");
    }
  });
});

refs.codePrevPage?.addEventListener("click", async () => {
  if (state.codesPage <= 1) {
    return;
  }

  state.codesPage -= 1;
  try {
    await loadCodes();
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`注册码翻页失败：${message}`, "error");
    showToast(`翻页失败：${message}`, "error");
  }
});

refs.codeNextPage?.addEventListener("click", async () => {
  state.codesPage += 1;
  try {
    await loadCodes();
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`注册码翻页失败：${message}`, "error");
    showToast(`翻页失败：${message}`, "error");
  }
});

refs.codeSelectPage?.addEventListener("click", () => {
  const visibleCodes = state.visibleCodes.map((item) => item.code);
  const allVisibleSelected = visibleCodes.length > 0 && visibleCodes.every((code) => state.selectedCodes.has(code));

  visibleCodes.forEach((code) => {
    if (allVisibleSelected) {
      state.selectedCodes.delete(code);
    } else {
      state.selectedCodes.add(code);
    }
  });

  renderCodes(state.visibleCodes);
});

refs.codeClearSelection?.addEventListener("click", () => {
  state.selectedCodes.clear();
  renderCodes(state.visibleCodes);
});

refs.codeDeleteSelected?.addEventListener("click", deleteSelectedCodes);
refs.botBlockList?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-bot-block-delete]");
  if (!button) {
    return;
  }
  await deleteBotAccessBlock(button.dataset.botBlockDelete);
});

refs.migrationExportButton?.addEventListener("click", async () => {
  try {
    await runButtonAction(refs.migrationExportButton, "打包中...", downloadMigrationBundle);
    const message = "迁移压缩包已开始下载，包含数据库快照、插件信息和当前运行时数据。";
    setAdminStatus(message, "success");
    refs.migrationNote.textContent = message;
    refs.migrationNote.dataset.tone = "info";
    showToast("迁移压缩包已开始下载。", "success");
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`导出迁移压缩包失败：${message}`, "error");
    refs.migrationNote.textContent = `导出失败：${message}`;
    refs.migrationNote.dataset.tone = "error";
    showToast(`导出失败：${message}`, "error");
    await popup("导出失败", message, "error");
  }
});

refs.migrationImportForm?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = refs.migrationImportFile?.files?.[0];
  if (!file) {
    setAdminStatus("请先选择迁移 ZIP 压缩包。", "warning");
    refs.migrationNote.textContent = "请先选择迁移 ZIP 压缩包，再执行导入。";
    refs.migrationNote.dataset.tone = "info";
    showToast("请先选择迁移 ZIP。", "warning");
    await popup("缺少文件", "请先选择迁移 ZIP 压缩包，再执行导入。", "warning");
    return;
  }

  const confirmed = window.confirm("导入迁移压缩包会覆盖压缩包内包含的数据库和插件数据；如果勾选了配置恢复，还会覆盖 data/config.json。是否继续？");
  if (!confirmed) {
    return;
  }

  try {
    const result = await runButtonAction(event.submitter || refs.migrationImportSubmit, "导入中...", () => importMigrationArchive(file, {
      restoreConfig: refs.migrationRestoreConfig?.checked,
      restartAfterImport: refs.migrationRestartAfterImport?.checked
    }));
    const payload = result.data || {};
    const restoredTableCount = payload.database?.restored_tables?.length || 0;
    const restoredDataCount = payload.data?.count || 0;
    const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
    const restartScheduled = Boolean(payload.restart_scheduled);
    let message = `迁移压缩包已导入，已恢复 ${restoredTableCount} 张数据表和 ${restoredDataCount} 项运行时数据。`;
    if (payload.config?.restored) {
      message += " 已同步恢复配置文件。";
    }

    if (restartScheduled) {
      message += " Bot 将在数秒后自动重启，请稍后重新进入后台。";
    } else {
      message += " 请尽快手动重启 Bot，以加载新的配置和插件状态。";
    }
    if (warnings.length) {
      message += ` 注意：${warnings.join("；")}`;
    }

    refs.migrationImportForm.reset();
    refs.migrationNote.textContent = message;
    refs.migrationNote.dataset.tone = warnings.length ? "error" : "info";
    setAdminStatus(message, restartScheduled ? "warning" : "success");
    showToast(restartScheduled ? "迁移数据已导入，Bot 即将重启。" : "迁移数据已导入。", restartScheduled ? "warning" : "success");
    await popup(restartScheduled ? "导入成功，即将重启" : "导入成功", message, restartScheduled ? "warning" : "success");
  } catch (error) {
    if (refs.migrationRestartAfterImport?.checked && isLikelyFetchDisconnect(error)) {
      const message = "连接在导入请求结束前后中断了；如果你勾选了自动重启，Bot 很可能已经开始重启。请等待 10 到 20 秒后刷新后台，并核对导入后的数据。";
      setAdminStatus(message, "warning");
      refs.migrationNote.textContent = message;
      refs.migrationNote.dataset.tone = "warning";
      showToast("连接已中断，Bot 可能正在重启。", "warning");
      await popup("连接已中断", message, "warning");
      return;
    }
    const message = normalizeError(error);
    setAdminStatus(`导入迁移压缩包失败：${message}`, "error");
    refs.migrationNote.textContent = `导入失败：${message}`;
    refs.migrationNote.dataset.tone = "error";
    showToast(`导入失败：${message}`, "error");
    await popup("导入失败", message, "error");
  }
});

refs.codeList?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-code-select]");
  if (!checkbox) {
    return;
  }

  const code = checkbox.dataset.codeSelect;
  if (!code) {
    return;
  }

  if (checkbox.checked) {
    state.selectedCodes.add(code);
  } else {
    state.selectedCodes.delete(code);
  }
  syncCodeSelectionActions();
});

refs.inviteCreditList?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-invite-credit-select]");
  if (!checkbox) return;
  const creditId = Number(checkbox.dataset.inviteCreditSelect || 0);
  if (!creditId) return;
  const selected = inviteSelectedSet(checkbox.dataset.inviteCreditType || "group_join");
  if (checkbox.checked) {
    selected.add(creditId);
  } else {
    selected.delete(creditId);
  }
  syncInviteCreditSelectionActions(checkbox.dataset.inviteCreditType || "group_join");
});

refs.inviteCreditSelectPage?.addEventListener("click", () => {
  const credits = inviteSection("group_join").credits || [];
  const selected = inviteSelectedSet("group_join");
  const availableIds = credits.filter((item) => item.available).map((item) => Number(item.id));
  const allSelected = availableIds.length > 0 && availableIds.every((id) => selected.has(id));
  availableIds.forEach((id) => {
    if (allSelected) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
  });
  renderInviteCredits(credits, "group_join");
});

refs.inviteCreditClearSelection?.addEventListener("click", () => {
  state.selectedInviteCredits.clear();
  renderInviteCredits(inviteSection("group_join").credits || [], "group_join");
});

refs.inviteCreditDeleteSelected?.addEventListener("click", () => deleteSelectedInviteCredits("group_join"));

refs.inviteCreditList?.addEventListener("click", async (event) => {
  const qualificationButton = event.target.closest("[data-invite-qualification-owner]");
  if (qualificationButton) {
    await updateInviteQualification({
      owner_tg: qualificationButton.dataset.inviteQualificationOwner,
      credit_type: qualificationButton.dataset.inviteQualificationType || "group_join",
      enabled: qualificationButton.dataset.inviteQualificationEnabled === "true",
      reason: "后台列表操作"
    });
    return;
  }
  const button = event.target.closest("[data-invite-credit-edit]");
  if (!button) return;
  await editInviteCredit(button.dataset.inviteCreditEdit, button.dataset.inviteCreditType || "group_join");
});

refs.inviteOpenCreditList?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-invite-credit-select]");
  if (!checkbox) return;
  const creditId = Number(checkbox.dataset.inviteCreditSelect || 0);
  if (!creditId) return;
  const selected = inviteSelectedSet("account_open");
  if (checkbox.checked) {
    selected.add(creditId);
  } else {
    selected.delete(creditId);
  }
  syncInviteCreditSelectionActions("account_open");
});

refs.inviteOpenCreditSelectPage?.addEventListener("click", () => {
  const credits = inviteSection("account_open").credits || [];
  const selected = inviteSelectedSet("account_open");
  const availableIds = credits.filter((item) => item.available).map((item) => Number(item.id));
  const allSelected = availableIds.length > 0 && availableIds.every((id) => selected.has(id));
  availableIds.forEach((id) => {
    if (allSelected) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
  });
  renderInviteCredits(credits, "account_open");
});

refs.inviteOpenCreditClearSelection?.addEventListener("click", () => {
  state.selectedInviteOpenCredits.clear();
  renderInviteCredits(inviteSection("account_open").credits || [], "account_open");
});

refs.inviteOpenCreditDeleteSelected?.addEventListener("click", () => deleteSelectedInviteCredits("account_open"));

refs.inviteOpenCreditList?.addEventListener("click", async (event) => {
  const qualificationButton = event.target.closest("[data-invite-qualification-owner]");
  if (qualificationButton) {
    await updateInviteQualification({
      owner_tg: qualificationButton.dataset.inviteQualificationOwner,
      credit_type: qualificationButton.dataset.inviteQualificationType || "account_open",
      enabled: qualificationButton.dataset.inviteQualificationEnabled === "true",
      reason: "后台列表操作"
    });
    return;
  }
  const button = event.target.closest("[data-invite-credit-edit]");
  if (!button) return;
  await editInviteCredit(button.dataset.inviteCreditEdit, "account_open");
});

refs.inviteOpenRecordList?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-invite-open-review]");
  if (!button) return;
  await reviewAccountOpenInvite(button.dataset.inviteOpenReview, button.dataset.inviteOpenAction || "approve");
});

refs.inviteRecordList?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-invite-record-revoke]");
  if (!button) return;
  await revokeInviteRecord(button.dataset.inviteRecordRevoke);
});

refs.inviteRefresh?.addEventListener("click", async () => {
  try {
    await runButtonAction(refs.inviteRefresh, "刷新中...", loadInvites);
    setAdminStatus("邀请数据已刷新。", "success");
    showToast("邀请数据已刷新。", "success");
  } catch (error) {
    const message = normalizeError(error, "刷新邀请数据失败。");
    setAdminStatus(message, "error");
    showToast(message, "error");
  }
});

refs.inviteGroupPrevPage?.addEventListener("click", async () => {
  if (state.inviteGroupPage <= 1) return;
  state.inviteGroupPage -= 1;
  await loadInvites();
});

refs.inviteGroupNextPage?.addEventListener("click", async () => {
  state.inviteGroupPage += 1;
  await loadInvites();
});

refs.inviteOpenPrevPage?.addEventListener("click", async () => {
  if (state.inviteOpenPage <= 1) return;
  state.inviteOpenPage -= 1;
  await loadInvites();
});

refs.inviteOpenNextPage?.addEventListener("click", async () => {
  state.inviteOpenPage += 1;
  await loadInvites();
});

refs.userBatchForm?.addEventListener("submit", previewUserBatch);
refs.userBatchApplyButton?.addEventListener("click", applyUserBatch);
[
  refs.userBatchScope,
  refs.userBatchSourceLevel,
  refs.userBatchAction,
  refs.userBatchTargetLevel
].forEach((node) => {
  node?.addEventListener("change", () => {
    invalidateUserBatchPreview();
  });
});

refs.tokenForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = refs.tokenInput.value.trim();
  localStorage.setItem(storageKey, state.token);
  await runButtonAction(event.submitter, "正在验证...", () => tryTokenAuth({ notify: true }));
});

document.querySelector("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.page = 1;
  state.query = document.querySelector("#search-input").value.trim();
  try {
    await runButtonAction(event.submitter, "搜索中...", loadUsers);
    setAdminStatus(state.query ? `已完成搜索，关键词“${state.query}”的结果已更新。` : "已刷新全部用户列表。");
    setActiveNav("users-section");
    showToast(state.query ? `搜索完成：${state.query}` : "用户列表已刷新。", "success");
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`搜索失败：${message}`, "error");
    showToast(`搜索失败：${message}`, "error");
  }
});

refs.revokeAllWhitelist?.addEventListener("click", revokeAllWhitelistUsers);

refs.prevPage.addEventListener("click", async () => {
  if (state.page <= 1) {
    return;
  }

  state.page -= 1;
  try {
    await loadUsers();
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`翻页失败：${message}`, "error");
    showToast(`翻页失败：${message}`, "error");
  }
});

refs.nextPage.addEventListener("click", async () => {
  state.page += 1;
  try {
    await loadUsers();
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`翻页失败：${message}`, "error");
    showToast(`翻页失败：${message}`, "error");
  }
});

refs.whitelistRevokeAll?.addEventListener("click", revokeAllWhitelistUsers);
refs.embyServiceToggle?.addEventListener("click", toggleEmbyService);

document.querySelector("#editor-form").addEventListener("submit", saveUser);

refs.pluginImportForm?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = refs.pluginImportFile?.files?.[0];
  if (!file) {
    setAdminStatus("请先选择一个插件 ZIP 压缩包。", "warning");
    showToast("请先选择插件 ZIP。", "warning");
    await popup("缺少文件", "请先选择一个插件 ZIP 压缩包，再执行导入。", "warning");
    return;
  }

  try {
    const result = await runButtonAction(event.submitter || refs.pluginImportSubmit, "导入中...", () => importPluginArchive(file, {
      enabled: refs.pluginImportEnabled?.checked,
      replaceExisting: refs.pluginImportReplace?.checked
    }));
    await loadPlugins();
    refs.pluginImportForm.reset();

    const plugin = result.data || {};
    const pendingRestart = Boolean(plugin.restart_required);
    const pendingRebuild = Boolean(plugin.container_rebuild_required);
    const hasError = Boolean(plugin.error);
    let tone = "success";
    let message = `插件 ${plugin.id || file.name} 已导入。`;

    if (pendingRebuild) {
      tone = "warning";
      message = `插件 ${plugin.id || file.name} 已导入，但需要重建 Docker 容器后才能完全启用。建议切换到本地构建模式后执行：docker compose up -d --build echo`;
    } else if (hasError) {
      tone = "warning";
      message = `插件 ${plugin.id || file.name} 已导入，但加载时报错：${plugin.error}`;
    } else if (!plugin.enabled) {
      tone = "success";
      message = `插件 ${plugin.id || file.name} 已导入，当前保持禁用状态。`;
    } else if (pendingRestart) {
      tone = "warning";
      message = `插件 ${plugin.id || file.name} 已导入，但变更需要重启后才能完全生效。`;
    } else if (plugin.replaced) {
      message = `插件 ${plugin.id || file.name} 已覆盖导入并完成同步。`;
    } else {
      message = `插件 ${plugin.id || file.name} 已导入并完成同步。`;
    }

    if (plugin.replaced && plugin.backup_path) {
      message += ` 旧版本已备份到 ${plugin.backup_path}。`;
    }
    if (plugin.permission_review_required && plugin.unknown_permissions?.length) {
      message += ` 请确认新增权限：${plugin.unknown_permissions.join("、")}。`;
    }

    setAdminStatus(message, tone);
    showToast(message, tone);
    await popup(hasError ? "导入完成，但存在异常" : "导入成功", message, tone);
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`导入插件失败：${message}`, "error");
    showToast(`导入失败：${message}`, "error");
    await popup("导入失败", message, "error");
  }
});

refs.pluginList.addEventListener("click", async (event) => {
  const enableButton = event.target.closest("[data-plugin-enable]");
  if (enableButton) {
    const pluginId = enableButton.dataset.pluginEnable;
    const nextEnabled = enableButton.dataset.pluginEnabled !== "1";

    try {
      const result = await runButtonAction(enableButton, "更新中...", () => patchPlugin(pluginId, { enabled: nextEnabled }));
      await loadPlugins();
      const pendingRestart = Boolean(result?.data?.restart_required);
      const message = nextEnabled
        ? `插件 ${pluginId} 已启用。`
        : pendingRestart
          ? `插件 ${pluginId} 已设为禁用，重启本女仆后会完全停用。`
          : `插件 ${pluginId} 已禁用。`;
      setAdminStatus(message, pendingRestart ? "warning" : "success");
      showToast(message, pendingRestart ? "warning" : "success");
      await popup(pendingRestart ? "已更新，等待重启" : "更新成功", message, pendingRestart ? "warning" : "success");
    } catch (error) {
      const message = normalizeError(error);
      setAdminStatus(`更新插件启用状态失败：${message}`, "error");
      showToast(`更新失败：${message}`, "error");
      await popup("更新失败", message, "error");
    }
    return;
  }

  const navButton = event.target.closest("[data-plugin-toggle]");
  if (!navButton) {
    return;
  }

  const pluginId = navButton.dataset.pluginToggle;
  const nextVisible = navButton.dataset.pluginVisible !== "1";

  try {
    await runButtonAction(navButton, "更新中...", () => patchPlugin(pluginId, { bottom_nav_visible: nextVisible }));
    await loadPlugins();
    setAdminStatus(`插件 ${pluginId} 的首页底栏显示状态已更新。`, "success");
    showToast(`插件 ${pluginId} 的显示状态已更新。`, "success");
    await popup("更新成功", `插件 ${pluginId} 的首页底栏显示状态已更新。`, "success");
  } catch (error) {
    const message = normalizeError(error);
    setAdminStatus(`更新插件显示状态失败：${message}`, "error");
    showToast(`更新失败：${message}`, "error");
    await popup("更新失败", message, "error");
  }
});

(async () => {
  renderLevelLegend();
  bindNavigation();
  setAuthMode(null);
  setSelectedUserPill();
  syncEditorShortcut();
  syncSuffixField();
  syncCodeSelectionActions();
  syncInviteCreditSelectionActions();
  syncUserBatchControls();

  if (tgApp) {
    tgApp.ready();
    tgApp.expand();
    tgApp.setHeaderColor("#f8f9fa");
    tgApp.setBackgroundColor("#f8f9fa");
  }

  setupBackNavigation();

  const telegramOk = await tryTelegramAuth();
  if (telegramOk) {
    return;
  }

  const tokenOk = await tryTokenAuth();
  if (tokenOk) {
    return;
  }

  setAuthCopy("主人登录", "当前未通过主人身份认证。你仍然可以在浏览器中手动输入后台令牌。");
  setAdminStatus("等待主人完成身份验证后再加载后台数据。", "warning");
  refs.tokenPanel.open = true;
})();
