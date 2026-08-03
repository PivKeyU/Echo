const tg = window.Telegram?.WebApp || null;
const storageKey = "slot-blind-box-admin-token";

function readLocalStorage(key) {
  try {
    return window.localStorage.getItem(key) || "";
  } catch (error) {
    return "";
  }
}

function writeLocalStorage(key, value) {
  try {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch (error) {
    setStatus("浏览器阻止了本地保存，本次仍会使用输入的令牌验证。", "warning");
  }
}

const state = {
  token: readLocalStorage(storageKey),
  initData: tg?.initData || "",
  authMode: null,
  payload: null,
  recordPage: 1,
  recordPageSize: 10,
  recordFilter: "all",
  records: [],
  pityUsers: []
};

const limitedRewardTypes = new Set(["group_invite_credit", "account_open_credit"]);

const refs = {
  status: document.querySelector("#admin-status"),
  authMode: document.querySelector("#admin-auth-mode"),
  tokenInput: document.querySelector("#admin-token"),
  tokenForm: document.querySelector("#token-form"),
  tokenSubmit: document.querySelector("#token-submit"),
  settingsForm: document.querySelector("#settings-form"),
  settingsSubmit: document.querySelector("#settings-submit"),
  prizeForm: document.querySelector("#prize-form"),
  prizeSubmit: document.querySelector("#prize-submit"),
  redeemCodeForm: document.querySelector("#redeem-code-form"),
  redeemCodeSubmit: document.querySelector("#redeem-code-submit"),
  userPitySearchForm: document.querySelector("#user-pity-search-form"),
  userPitySearchSubmit: document.querySelector("#user-pity-search-submit"),
  userPityQuery: document.querySelector("#user-pity-query"),
  userPityList: document.querySelector("#user-pity-list"),
  userStatsResetAll: document.querySelector("#user-stats-reset-all"),
  prizeList: document.querySelector("#admin-prize-list"),
  redeemCodeList: document.querySelector("#admin-redeem-code-list"),
  recordList: document.querySelector("#admin-record-list"),
  recordFilter: document.querySelector("#admin-record-filter"),
  recordPrev: document.querySelector("#admin-record-prev"),
  recordNext: document.querySelector("#admin-record-next"),
  recordPageInfo: document.querySelector("#admin-record-page-info"),
  prizeCount: document.querySelector("#admin-prize-count"),
  activeCount: document.querySelector("#admin-active-count"),
  spinCount: document.querySelector("#admin-spin-count"),
  userCount: document.querySelector("#admin-user-count"),
  blankRate: document.querySelector("#admin-blank-rate"),
  totalWeight: document.querySelector("#admin-total-weight")
};

if (refs.tokenInput) {
  refs.tokenInput.value = state.token;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(text, tone = "info") {
  if (!refs.status) return;
  refs.status.textContent = text;
  refs.status.dataset.tone = tone;
}

function authHeaders() {
  if (state.authMode === "telegram" && state.initData) {
    return { "X-Telegram-Init-Data": state.initData };
  }
  if (state.token) {
    return { "X-Admin-Token": state.token };
  }
  return {};
}

async function request(method, url, payload) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: payload ? JSON.stringify(payload) : undefined
    });
  } catch (error) {
    throw new Error("网络请求失败，请确认后台服务正在运行。");
  }
  const raw = await response.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch (error) {
    throw new Error(raw || `请求失败（HTTP ${response.status}）`);
  }
  if (!response.ok || data.code !== 200) {
    throw new Error(data.detail || data.message || `请求失败（HTTP ${response.status}）`);
  }
  return data.data;
}

function field(selector) {
  return document.querySelector(selector);
}

function numberValue(selector, fallback = 0) {
  const value = Number(field(selector)?.value ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function checked(selector) {
  return Boolean(field(selector)?.checked);
}

function levelMap(prefix) {
  return {
    a: numberValue(`#${prefix}-a`, 0),
    b: numberValue(`#${prefix}-b`, 0),
    c: numberValue(`#${prefix}-c`, 0),
    d: numberValue(`#${prefix}-d`, 0)
  };
}

function rewardTypeLabel(type, quantity = 0) {
  if (type === "free_spin_ticket") return `抽奖券 ${quantity || 1} 张`;
  if (type === "group_invite_credit") return "邀请资格";
  if (type === "account_open_credit") return `开号资格 x${quantity || 1}`;
  if (type === "emby_currency") return `Emby 货币 ${quantity || 0}`;
  return "普通奖品";
}

function prizeGuaranteeLabel(prize = {}) {
  if (!prize.guarantee_eligible) return "不参与保底";
  const after = coerceNumber(prize.guarantee_after, 0);
  return after > 0 ? `单独保底 ${after} 次` : "跟随全局保底";
}

function grantsPayload(prefix = "redeem-grant") {
  return {
    free_spin_ticket: numberValue(`#${prefix}-ticket`, 0),
    group_invite_credit: numberValue(`#${prefix}-group`, 0),
    account_open_credit: numberValue(`#${prefix}-account`, 0)
  };
}

function grantsLabel(grants = {}) {
  const parts = [];
  if (Number(grants.free_spin_ticket || 0) > 0) parts.push(`抽奖券 x${grants.free_spin_ticket}`);
  if (Number(grants.group_invite_credit || 0) > 0) parts.push(`邀请资格 x${grants.group_invite_credit}`);
  if (Number(grants.account_open_credit || 0) > 0) parts.push(`开号资格 x${grants.account_open_credit}`);
  return parts.join(" · ") || "无发放内容";
}

function coerceNumber(value, fallback = 0) {
  const number = Number(value ?? fallback);
  return Number.isFinite(number) ? number : fallback;
}

function formatRate(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return "0";
  if (number < 0.0001) return "<0.0001";
  const digits = number < 1 ? 4 : number < 10 ? 3 : 2;
  return number.toFixed(digits).replace(/\.?0+$/, "");
}

function formatWeight(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return number.toFixed(6).replace(/\.?0+$/, "");
}

function selectedAttribute(value, current) {
  return value === current ? "selected" : "";
}

function checkedAttribute(value) {
  return value ? "checked" : "";
}

function disabledAttribute(value) {
  return value ? "disabled" : "";
}

function reelStripText(reels = []) {
  const symbols = Array.isArray(reels) ? reels.slice(0, 3) : [];
  while (symbols.length < 3) symbols.push("◇");
  return symbols.join(" ");
}

function isUnlimitedStock(stock) {
  return coerceNumber(stock, -1) < 0;
}

function stockInputValue(stock) {
  return isUnlimitedStock(stock) ? -1 : Math.max(coerceNumber(stock, 0), 0);
}

function stockValueFromForm(form) {
  if (form.elements.stock_unlimited?.checked) return -1;
  return Math.max(coerceNumber(form.elements.stock?.value, 0), 0);
}

function syncStockUnlimitedControl(form) {
  const stockInput = form?.elements?.stock || form?.querySelector("[data-stock-input], #prize-stock");
  const unlimitedInput = form?.elements?.stock_unlimited || form?.querySelector("[data-stock-unlimited], #prize-stock-unlimited");
  if (!stockInput || !unlimitedInput) return;
  const unlimited = Boolean(unlimitedInput.checked);
  stockInput.disabled = unlimited;
  if (unlimited) {
    stockInput.value = -1;
    return;
  }
  if (!stockInput.value || coerceNumber(stockInput.value, 0) < 0) {
    stockInput.value = 0;
  }
}

function syncCreatePrizeStockUnlimited() {
  syncStockUnlimitedControl(refs.prizeForm);
}

function syncGuaranteeControl(form) {
  const rewardInput = form?.elements?.reward_type || form?.querySelector("#prize-reward-type");
  const guaranteeInput = form?.elements?.guarantee_eligible || form?.querySelector("#prize-guarantee");
  const guaranteeAfterInput = form?.elements?.guarantee_after || form?.querySelector("#prize-guarantee-after");
  if (!rewardInput || !guaranteeInput) return;
  const limited = limitedRewardTypes.has(String(rewardInput.value || "").trim());
  guaranteeInput.checked = limited ? false : Boolean(guaranteeInput.checked);
  guaranteeInput.disabled = limited;
  if (guaranteeAfterInput) {
    guaranteeAfterInput.disabled = limited;
    if (limited) guaranteeAfterInput.value = 0;
  }
}

function syncCreatePrizeControls() {
  syncCreatePrizeStockUnlimited();
  syncGuaranteeControl(refs.prizeForm);
}

function stockLabel(stock) {
  const value = coerceNumber(stock, -1);
  if (value < 0) return "不限";
  if (value === 0) return "已售罄";
  return String(value);
}

function activePrizeWeight(prize = {}, overrides = {}) {
  const weight = Math.max(coerceNumber(overrides.weight ?? prize.weight, 0), 0);
  const stock = coerceNumber(overrides.stock ?? prize.stock, -1);
  const enabled = overrides.enabled ?? Boolean(prize.enabled);
  return enabled && stock !== 0 && weight > 0 ? weight : 0;
}

function prizeProbabilityPreview(prize = {}, overrides = {}) {
  const probabilities = state.payload?.probabilities || {};
  const currentTotal = Math.max(coerceNumber(probabilities.total_weight, 0), 0);
  const currentWeight = activePrizeWeight(prize);
  const nextWeight = activePrizeWeight(prize, overrides);
  const nextTotal = Math.max(currentTotal - currentWeight + nextWeight, 0);
  const rate = nextTotal > 0 && nextWeight > 0 ? (nextWeight / nextTotal) * 100 : 0;
  return { rate, totalWeight: nextTotal, activeWeight: nextWeight };
}

function limitedRewardTypeRatePreview(prize = {}, overrides = {}, preview = null) {
  const type = String(overrides.reward_type ?? prize.reward_type ?? "").trim();
  if (!limitedRewardTypes.has(type)) return 0;
  const nextPreview = preview || prizeProbabilityPreview(prize, overrides);
  const total = coerceNumber(nextPreview.totalWeight, 0);
  if (total <= 0) return 0;
  const currentPrizeId = String(prize.id || "");
  const sameTypeWeight = (state.payload?.prizes || [])
    .filter((item) => String(item.id || "") !== currentPrizeId)
    .filter((item) => String(item.reward_type || "").trim() === type)
    .reduce((sum, item) => sum + activePrizeWeight(item), 0);
  return ((sameTypeWeight + coerceNumber(nextPreview.activeWeight, 0)) / total) * 100;
}

function rateFormulaText(preview = {}) {
  const weight = coerceNumber(preview.activeWeight, 0);
  const total = coerceNumber(preview.totalWeight, 0);
  if (weight <= 0) return "未参与抽奖池";
  if (total <= 0) return "奖池总权重 0";
  return `权重 ${formatWeight(weight)} / 奖池总权重 ${formatWeight(total)}`;
}

function limitedRewardTypeRate(type) {
  const rates = state.payload?.probabilities?.reward_type_rates || {};
  return coerceNumber(rates[type], 0);
}

function limitedRewardRateWarning(prize = {}, rate = 0) {
  const type = String(prize.reward_type || "").trim();
  if (!limitedRewardTypes.has(type)) return "";
  return Number(rate || 0) >= 1 ? " · 同类型必须低于 1%，请降低小数权重" : " · 同类型低于 1%";
}

function limitedRewardTypeRateText(type, rate = null) {
  if (!limitedRewardTypes.has(String(type || "").trim())) return "";
  const nextRate = rate === null ? limitedRewardTypeRate(type) : coerceNumber(rate, 0);
  return `同类型总概率 ${formatRate(nextRate)}%`;
}

function limitedRewardStatusText(rate = 0) {
  return coerceNumber(rate, 0) >= 1 ? "超过 1%，需降低" : "低于 1%";
}

function limitedRewardTypeSummary() {
  const groupRate = limitedRewardTypeRate("group_invite_credit");
  const accountRate = limitedRewardTypeRate("account_open_credit");
  return `邀请资格 ${formatRate(groupRate)}% · 开号资格 ${formatRate(accountRate)}%`;
}

function updatePrizeRatePreview(form, prize) {
  const patch = prizePatchFromForm(form);
  const preview = prizeProbabilityPreview(prize, {
    weight: patch.weight,
    stock: patch.stock,
    enabled: patch.enabled
  });
  const typeRate = limitedRewardTypeRatePreview(prize, patch, preview);
  const previewNode = form.querySelector("[data-rate-preview]");
  const formulaNode = form.querySelector("[data-rate-formula]");
  if (previewNode) previewNode.textContent = `${formatRate(preview.rate)}%`;
  if (formulaNode) {
    const typeText = limitedRewardTypeRateText(patch.reward_type, typeRate);
    const warning = limitedRewardRateWarning(patch, typeRate);
    formulaNode.textContent = `${rateFormulaText(preview)}${typeText ? ` · ${typeText}` : ""}${warning}`;
  }
}

function prizePatchFromForm(form) {
  return {
    name: String(form.elements.name?.value || "").trim(),
    icon: String(form.elements.icon?.value || "🎁").trim(),
    weight: coerceNumber(form.elements.weight?.value, 0),
    stock: stockValueFromForm(form),
    reward_type: String(form.elements.reward_type?.value || "manual").trim(),
    free_spin_quantity: coerceNumber(form.elements.free_spin_quantity?.value, 0),
    description: String(form.elements.description?.value || "").trim(),
    delivery_text: String(form.elements.delivery_text?.value || "").trim(),
    broadcast_image_url: String(form.elements.broadcast_image_url?.value || "").trim(),
    enabled: Boolean(form.elements.enabled?.checked),
    guarantee_eligible: Boolean(form.elements.guarantee_eligible?.checked),
    guarantee_after: coerceNumber(form.elements.guarantee_after?.value, 0),
    broadcast_enabled: Boolean(form.elements.broadcast_enabled?.checked)
  };
}

function normalizedRecordType(record = {}) {
  const type = String(record.reward_type || "").trim();
  if (type) return type;
  return record.outcome === "blank" ? "blank" : "manual";
}

function recordTypeLabel(record = {}) {
  const type = normalizedRecordType(record);
  if (type === "emby_currency") return `💰 ${record.reward_quantity || 0} ${record.reward_label || "货币"}`;
  if (type === "free_spin_ticket") return `🎟️ 抽奖券 x${record.reward_quantity || 1}`;
  if (type === "group_invite_credit") return `📨 邀请资格 x${record.reward_quantity || 1}`;
  if (type === "account_open_credit") return `🪪 开号资格 x${record.reward_quantity || 1}`;
  if (type === "blank" || record.outcome === "blank") return "🍀 轮空";
  return "🎁 普通奖品";
}

function recordMatchesFilter(record = {}, filter = "all") {
  if (filter === "all") return true;
  if (filter === "win") return record.outcome === "win";
  return normalizedRecordType(record) === filter;
}

function renderRecords(records = state.records) {
  state.records = Array.isArray(records) ? records : [];
  const filtered = state.records.filter((record) => recordMatchesFilter(record, state.recordFilter));
  const totalPages = Math.max(Math.ceil(filtered.length / state.recordPageSize), 1);
  state.recordPage = Math.min(Math.max(state.recordPage, 1), totalPages);
  const start = (state.recordPage - 1) * state.recordPageSize;
  const pageItems = filtered.slice(start, start + state.recordPageSize);
  if (!pageItems.length) {
    refs.recordList.innerHTML = `<div class="empty">暂无匹配记录。</div>`;
  } else {
    refs.recordList.innerHTML = pageItems.map((record) => `
      <article class="record-item" data-outcome="${escapeHtml(record.outcome)}">
        <div class="record-line">
          <strong>${escapeHtml(record.prize_icon || "🍀")} ${escapeHtml(record.prize_name || "轮空")}</strong>
          <span class="status-pill">${escapeHtml(recordTypeLabel(record))}</span>
        </div>
        <div class="record-reels" aria-label="转轮结果">${escapeHtml(reelStripText(record.reels))}</div>
        <p class="muted">${escapeHtml(record.user_display || record.user_id || "未知用户")} · ${escapeHtml(record.created_at || "")}${record.pity_triggered ? " · 保底" : ""}</p>
      </article>
    `).join("");
  }
  if (refs.recordPageInfo) refs.recordPageInfo.textContent = `${state.recordPage}/${totalPages} · ${filtered.length} 条`;
  if (refs.recordPrev) refs.recordPrev.disabled = state.recordPage <= 1;
  if (refs.recordNext) refs.recordNext.disabled = state.recordPage >= totalPages;
}

function userMetaLine(user = {}) {
  const parts = [];
  if (user.username) parts.push(`@${user.username}`);
  if (user.emby_name) parts.push(`Emby ${user.emby_name}`);
  if (user.embyid) parts.push(user.embyid);
  if (user.level) parts.push(`等级 ${user.level}`);
  parts.push(`TG ${user.tg}`);
  return parts.filter(Boolean).join(" · ");
}

function renderUserPityList(users = state.pityUsers) {
  state.pityUsers = Array.isArray(users) ? users : [];
  if (!refs.userPityList) return;
  if (!state.pityUsers.length) {
    refs.userPityList.innerHTML = `<div class="empty">搜索用户后可管理总抽奖次数，并可清零测试统计。</div>`;
    return;
  }
  refs.userPityList.innerHTML = state.pityUsers.map((user) => `
    <article class="admin-prize user-pity-card" data-user-tg="${escapeHtml(user.tg)}">
      <div class="admin-prize-head">
        <div class="admin-prize-title">
          <h3>${escapeHtml(user.display_label || `TG ${user.tg}`)}</h3>
          <p class="muted">${escapeHtml(userMetaLine(user))}</p>
        </div>
        <div class="admin-prize-rate">
          <strong>${escapeHtml(user.total_spins ?? 0)}</strong>
          <span>总抽奖次数</span>
        </div>
      </div>
      <div class="admin-prize-meta">
        <span class="status-pill">中奖 ${escapeHtml(user.win_count ?? 0)}</span>
        <span class="status-pill">轮空 ${escapeHtml(user.blank_count ?? 0)}</span>
        <span class="status-pill">保底累计 ${escapeHtml(user.miss_streak ?? 0)}</span>
      </div>
      <div class="admin-prize-actions user-pity-actions">
        <input type="number" min="0" max="1000000" value="${escapeHtml(user.total_spins ?? 0)}" data-spin-input="${escapeHtml(user.tg)}" aria-label="总抽奖次数">
        <button type="button" data-spin-save="${escapeHtml(user.tg)}">保存总抽</button>
        <button type="button" class="secondary" data-spin-clear="${escapeHtml(user.tg)}">清零统计</button>
      </div>
    </article>
  `).join("");

  refs.userPityList.querySelectorAll("[data-spin-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const tg = Number(button.dataset.spinSave || 0);
      const input = button.closest("[data-user-tg]")?.querySelector("[data-spin-input]");
      await updateUserStats(tg, Number(input?.value || 0), false, button);
    });
  });
  refs.userPityList.querySelectorAll("[data-spin-clear]").forEach((button) => {
    button.addEventListener("click", async () => {
      const tg = Number(button.dataset.spinClear || 0);
      await updateUserStats(tg, 0, true, button);
    });
  });
}

function renderPrizes(prizes = []) {
  if (!prizes.length) {
    refs.prizeList.innerHTML = `<div class="empty">当前还没有奖品。</div>`;
    return;
  }
  refs.prizeList.innerHTML = prizes.map((prize) => {
    const currentPreview = prizeProbabilityPreview(prize);
    const currentRate = formatRate(prize.computed_rate ?? currentPreview.rate);
    const currentTypeRate = limitedRewardTypeRate(prize.reward_type);
    const currentTypeText = limitedRewardTypeRateText(prize.reward_type, currentTypeRate);
    const currentFormula = `${rateFormulaText(currentPreview)}${currentTypeText ? ` · ${currentTypeText}` : ""}`;
    const rewardType = prize.reward_type || "manual";
    return `
      <article class="admin-prize" data-prize-id="${escapeHtml(prize.id)}">
        <div class="admin-prize-head">
          <div class="admin-prize-title">
            <h3>${escapeHtml(prize.icon || "🎁")} ${escapeHtml(prize.name)}</h3>
            <p class="muted">${escapeHtml(prize.description || "")}</p>
          </div>
          <div class="admin-prize-rate">
            <strong>${escapeHtml(currentRate)}%</strong>
            <span>实际中奖概率</span>
          </div>
        </div>
        <div class="admin-prize-meta">
          <span class="status-pill">${prize.enabled ? "启用" : "停用"}</span>
          <span class="status-pill">权重 ${escapeHtml(formatWeight(prize.weight))}</span>
          ${limitedRewardTypes.has(rewardType) ? `<span class="status-pill">同类型 ${escapeHtml(formatRate(currentTypeRate))}% / ${escapeHtml(limitedRewardStatusText(currentTypeRate))}</span>` : ""}
          <span class="status-pill">库存 ${escapeHtml(stockLabel(prize.stock))}</span>
          <span class="status-pill">${escapeHtml(currentFormula)}</span>
          <span class="status-pill">${escapeHtml(prize.reward_label || rewardTypeLabel(prize.reward_type, prize.free_spin_quantity))}</span>
          <span class="status-pill">${escapeHtml(prizeGuaranteeLabel(prize))}</span>
          <span class="status-pill">${prize.broadcast_enabled ? "中奖播报" : "不播报"}</span>
          ${prize.broadcast_image_url ? `<span class="status-pill">有播报图</span>` : ""}
        </div>
        <div class="admin-prize-actions">
          <button type="button" class="secondary" data-edit="${escapeHtml(prize.id)}">编辑参数</button>
          <button type="button" class="secondary" data-toggle="${escapeHtml(prize.id)}">${prize.enabled ? "停用" : "启用"}</button>
          <button type="button" class="secondary" data-delete="${escapeHtml(prize.id)}">删除</button>
        </div>
        <form class="prize-edit-form hidden" data-prize-edit-form="${escapeHtml(prize.id)}">
          <div class="grid-form compact-form admin-prize-edit-grid">
            <label>
              奖品名称
              <input name="name" type="text" maxlength="80" value="${escapeHtml(prize.name || "")}" required>
            </label>
            <label>
              图标
              <input name="icon" type="text" maxlength="16" value="${escapeHtml(prize.icon || "🎁")}">
            </label>
            <label>
              中奖权重（决定概率）
              <input name="weight" type="number" min="0" max="1000000" step="0.000001" value="${escapeHtml(formatWeight(prize.weight ?? 0))}" data-rate-affects>
              <small class="field-hint">资格类可填 0.1、0.01 等小数；同类型总概率必须低于 1%。</small>
            </label>
            <label>
              库存
              <input name="stock" type="number" min="0" max="2147483647" value="${escapeHtml(stockInputValue(prize.stock))}" ${disabledAttribute(isUnlimitedStock(prize.stock))} data-stock-input data-rate-affects>
            </label>
            <label class="stock-unlimited-toggle">
              <input name="stock_unlimited" type="checkbox" ${checkedAttribute(isUnlimitedStock(prize.stock))} data-stock-unlimited data-rate-affects>
              无限库存
            </label>
            <label>
              奖品类型
              <select name="reward_type">
                <option value="manual" ${selectedAttribute("manual", rewardType)}>普通奖品</option>
                <option value="free_spin_ticket" ${selectedAttribute("free_spin_ticket", rewardType)}>抽奖券</option>
                <option value="group_invite_credit" ${selectedAttribute("group_invite_credit", rewardType)}>邀请资格</option>
                <option value="account_open_credit" ${selectedAttribute("account_open_credit", rewardType)}>开号资格</option>
                <option value="emby_currency" ${selectedAttribute("emby_currency", rewardType)}>Emby 货币</option>
              </select>
            </label>
            <label>
              奖励数量
              <input name="free_spin_quantity" type="number" min="0" max="9007199254740991" value="${escapeHtml(prize.free_spin_quantity ?? 0)}">
            </label>
            <label>
              单独保底次数
              <input name="guarantee_after" type="number" min="0" max="10000" value="${escapeHtml(prize.guarantee_after ?? 0)}">
              <small class="field-hint">0 表示跟随全局保底；大于 0 时按连续轮空次数触发该奖品。</small>
            </label>
            <label class="wide">
              奖品描述
              <textarea name="description" maxlength="500">${escapeHtml(prize.description || "")}</textarea>
            </label>
            <label class="wide">
              发奖说明
              <textarea name="delivery_text" maxlength="1000">${escapeHtml(prize.delivery_text || "")}</textarea>
            </label>
            <label class="wide">
              播报图片地址
              <input name="broadcast_image_url" type="text" maxlength="1000" value="${escapeHtml(prize.broadcast_image_url || "")}" placeholder="https://... 可留空">
            </label>
            <label>
              <input name="enabled" type="checkbox" ${checkedAttribute(prize.enabled)} data-rate-affects>
              启用奖品
            </label>
            <label>
              <input name="guarantee_eligible" type="checkbox" ${checkedAttribute(prize.guarantee_eligible)}>
              参与保底
              <small class="field-hint">资格类固定不参与保底，避免实际概率被保底放大。</small>
            </label>
            <label>
              <input name="broadcast_enabled" type="checkbox" ${checkedAttribute(prize.broadcast_enabled)}>
              中奖群播报
            </label>
          </div>
          <div class="admin-rate-preview">
            <span>保存后预估概率</span>
            <strong data-rate-preview>${escapeHtml(currentRate)}%</strong>
            <small data-rate-formula>${escapeHtml(currentFormula)}</small>
          </div>
          <div class="admin-prize-actions">
            <button type="submit" data-save-prize>保存修改</button>
            <button type="button" class="secondary" data-cancel-edit>收起</button>
          </div>
        </form>
      </article>
    `;
  }).join("");

  refs.prizeList.querySelectorAll("[data-prize-edit-form]").forEach((form) => {
    const prize = prizes.find((item) => item.id === form.dataset.prizeEditForm);
    if (!prize) return;
    syncStockUnlimitedControl(form);
    syncGuaranteeControl(form);
    form.addEventListener("input", () => updatePrizeRatePreview(form, prize));
    form.addEventListener("change", (event) => {
      if (event.target?.name === "stock_unlimited") syncStockUnlimitedControl(form);
      if (event.target?.name === "reward_type") syncGuaranteeControl(form);
      updatePrizeRatePreview(form, prize);
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = form.querySelector("[data-save-prize]");
      const previous = submitButton?.innerHTML || "保存修改";
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "保存中";
      }
      try {
        const payload = await request("PATCH", `/plugins/slot-box/admin-api/prize/${encodeURIComponent(prize.id)}`, prizePatchFromForm(form));
        applyPayload(payload);
        setStatus("奖品参数已更新。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.innerHTML = previous;
        }
      }
    });
    updatePrizeRatePreview(form, prize);
  });

  refs.prizeList.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".admin-prize");
      const form = card?.querySelector("[data-prize-edit-form]");
      if (!form) return;
      const willOpen = form.classList.contains("hidden");
      form.classList.toggle("hidden", !willOpen);
      button.textContent = willOpen ? "收起编辑" : "编辑参数";
      const prize = prizes.find((item) => item.id === button.dataset.edit);
      if (willOpen && prize) updatePrizeRatePreview(form, prize);
    });
  });

  refs.prizeList.querySelectorAll("[data-cancel-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".admin-prize");
      const form = card?.querySelector("[data-prize-edit-form]");
      const editButton = card?.querySelector("[data-edit]");
      if (!form) return;
      form.reset();
      syncStockUnlimitedControl(form);
      syncGuaranteeControl(form);
      const prize = prizes.find((item) => item.id === form.dataset.prizeEditForm);
      if (prize) updatePrizeRatePreview(form, prize);
      form.classList.add("hidden");
      if (editButton) editButton.textContent = "编辑参数";
    });
  });

  refs.prizeList.querySelectorAll("[data-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      const prize = prizes.find((item) => item.id === button.dataset.toggle);
      if (!prize) return;
      try {
        const payload = await request("PATCH", `/plugins/slot-box/admin-api/prize/${encodeURIComponent(prize.id)}`, {
          enabled: !prize.enabled
        });
        applyPayload(payload);
        setStatus("奖品状态已更新。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });

  refs.prizeList.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const prize = prizes.find((item) => item.id === button.dataset.delete);
      if (!prize || !window.confirm(`确认删除奖品「${prize.name}」吗？`)) return;
      try {
        const payload = await request("DELETE", `/plugins/slot-box/admin-api/prize/${encodeURIComponent(prize.id)}`);
        applyPayload(payload);
        setStatus("奖品已删除。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });
}

function renderRedeemCodes(codes = []) {
  if (!refs.redeemCodeList) return;
  if (!codes.length) {
    refs.redeemCodeList.innerHTML = `<div class="empty">还没有兑换码。</div>`;
    return;
  }
  refs.redeemCodeList.innerHTML = codes.map((code) => `
    <article class="admin-prize">
      <div class="admin-prize-head">
        <div>
          <h3>${escapeHtml(code.code)}</h3>
          <p class="muted">${escapeHtml(code.title || "兑换码")}</p>
        </div>
        <span class="status-pill">${code.enabled ? "启用" : "停用"}</span>
      </div>
      <div class="admin-prize-meta">
        <span class="status-pill">已用 ${escapeHtml(code.used_count || 0)}/${escapeHtml(code.max_uses || 0)}</span>
        <span class="status-pill">单人 ${escapeHtml(code.per_user_limit || 1)}</span>
        <span class="status-pill">${escapeHtml(grantsLabel(code.grants || {}))}</span>
      </div>
      <div class="admin-prize-actions">
        <button type="button" class="secondary" data-edit-code="${escapeHtml(code.code)}">编辑</button>
        <button type="button" class="secondary" data-toggle-code="${escapeHtml(code.code)}">${code.enabled ? "停用" : "启用"}</button>
        <button type="button" class="secondary" data-delete-code="${escapeHtml(code.code)}">删除</button>
      </div>
    </article>
  `).join("");

  refs.redeemCodeList.querySelectorAll("[data-toggle-code]").forEach((button) => {
    button.addEventListener("click", async () => {
      const code = codes.find((item) => item.code === button.dataset.toggleCode);
      if (!code) return;
      try {
        const payload = await request("PATCH", `/plugins/slot-box/admin-api/redeem-code/${encodeURIComponent(code.code)}`, {
          enabled: !code.enabled
        });
        applyPayload(payload);
        setStatus("兑换码状态已更新。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });

  refs.redeemCodeList.querySelectorAll("[data-edit-code]").forEach((button) => {
    button.addEventListener("click", async () => {
      const code = codes.find((item) => item.code === button.dataset.editCode);
      if (!code) return;
      const patch = promptRedeemCodePatch(code);
      if (!patch) return;
      try {
        const payload = await request("PATCH", `/plugins/slot-box/admin-api/redeem-code/${encodeURIComponent(code.code)}`, patch);
        applyPayload(payload);
        setStatus("兑换码已更新。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });

  refs.redeemCodeList.querySelectorAll("[data-delete-code]").forEach((button) => {
    button.addEventListener("click", async () => {
      const codeValue = button.dataset.deleteCode;
      if (!window.confirm(`确认删除兑换码 ${codeValue} 吗？`)) return;
      try {
        const payload = await request("DELETE", `/plugins/slot-box/admin-api/redeem-code/${encodeURIComponent(codeValue)}`);
        applyPayload(payload);
        setStatus("兑换码已删除。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });
}

async function searchUserPity() {
  const query = refs.userPityQuery?.value.trim() || "";
  const payload = await request("POST", "/plugins/slot-box/admin-api/users/search", {
    query,
    limit: 40
  });
  renderUserPityList(payload.items || []);
  setStatus(`已找到 ${(payload.items || []).length} 个用户。`, "success");
}

async function updateUserStats(tg, totalSpins, resetStats, button) {
  if (!tg) {
    setStatus("用户 TGID 不正确。", "error");
    return;
  }
  const previous = button?.innerHTML || "";
  if (button) {
    button.disabled = true;
    button.textContent = resetStats ? "清零中" : "保存中";
  }
  try {
    const payload = await request("PATCH", `/plugins/slot-box/admin-api/users/${encodeURIComponent(tg)}/stats`, {
      total_spins: Math.max(coerceNumber(totalSpins, 0), 0),
      reset_spin_stats: Boolean(resetStats)
    });
    applyPayload(payload);
    const nextUser = payload.user;
    state.pityUsers = state.pityUsers.map((user) => Number(user.tg) === Number(tg) ? nextUser : user);
    if (!state.pityUsers.some((user) => Number(user.tg) === Number(tg))) {
      state.pityUsers.unshift(nextUser);
    }
    renderUserPityList(state.pityUsers);
    setStatus(resetStats ? "用户抽奖统计已清零。" : "用户总抽奖次数已更新。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
    if (button) {
      button.disabled = false;
      button.innerHTML = previous;
    }
  }
}

function parseBooleanPrompt(message, currentValue) {
  const raw = window.prompt(message, currentValue ? "true" : "false");
  if (raw === null) return null;
  const normalized = raw.trim().toLowerCase();
  if (["true", "1", "yes", "y", "是", "开", "开启"].includes(normalized)) return true;
  if (["false", "0", "no", "n", "否", "关", "关闭"].includes(normalized)) return false;
  window.alert("请输入 true 或 false。");
  return parseBooleanPrompt(message, currentValue);
}


function promptRedeemCodePatch(code) {
  const title = window.prompt("兑换码名称：", code.title || "兑换码");
  if (title === null) return null;
  const maxUses = window.prompt("总使用次数（0 表示不限）：", code.max_uses ?? 1);
  if (maxUses === null) return null;
  const perUserLimit = window.prompt("单人使用次数：", code.per_user_limit ?? 1);
  if (perUserLimit === null) return null;
  const ticket = window.prompt("发放抽奖券数量：", code.grants?.free_spin_ticket ?? 0);
  if (ticket === null) return null;
  const group = window.prompt("发放邀请资格数量：", code.grants?.group_invite_credit ?? 0);
  if (group === null) return null;
  const account = window.prompt("发放开号资格数量：", code.grants?.account_open_credit ?? 0);
  if (account === null) return null;
  const enabled = parseBooleanPrompt("是否启用（true/false）：", code.enabled);
  if (enabled === null) return null;
  return {
    title: title.trim(),
    max_uses: Number(maxUses || 0),
    per_user_limit: Number(perUserLimit || 1),
    enabled,
    grants: {
      free_spin_ticket: Number(ticket || 0),
      group_invite_credit: Number(group || 0),
      account_open_credit: Number(account || 0)
    }
  };
}

function applyPayload(payload = {}) {
  state.payload = payload;
  const settings = payload.settings || {};
  const stats = payload.stats || {};
  const probabilities = payload.probabilities || {};

  field("#setting-title").value = settings.title || "";
  field("#setting-notice").value = settings.notice || "";
  field("#setting-blank-label").value = settings.blank_label || "";
  field("#setting-blank-icon").value = settings.blank_icon || "";
  field("#setting-blank-weight").value = settings.blank_weight ?? 0;
  field("#setting-pity-after").value = settings.pity_after ?? 1;
  field("#setting-daily-limit").value = settings.daily_limit ?? 0;
  field("#setting-spin-cost").value = settings.spin_cost_iv ?? 0;
  field("#setting-currency").value = settings.currency_name || "";
  field("#setting-cooldown").value = settings.cooldown_seconds ?? 0;
  field("#setting-record-limit").value = settings.record_limit ?? 300;
  ["a", "b", "c", "d"].forEach((level) => {
    field(`#setting-limit-${level}`).value = settings.daily_limit_by_level?.[level] ?? 0;
    field(`#setting-gift-${level}`).value = settings.daily_gift_by_level?.[level] ?? 0;
  });
  field("#setting-enabled").checked = Boolean(settings.enabled);
  field("#setting-blank-enabled").checked = Boolean(settings.blank_enabled);
  field("#setting-pity-enabled").checked = Boolean(settings.pity_enabled);

  refs.prizeCount.textContent = String(stats.prize_count ?? 0);
  refs.activeCount.textContent = String(stats.active_prize_count ?? 0);
  refs.spinCount.textContent = String(stats.spin_count ?? 0);
  refs.userCount.textContent = String(stats.user_count ?? 0);
  refs.blankRate.textContent = `轮空 ${probabilities.blank_rate ?? 0}%`;
  refs.totalWeight.textContent = `奖池总权重 ${formatWeight(probabilities.total_weight ?? 0)} · 轮空 ${formatRate(probabilities.blank_rate ?? 0)}% · ${limitedRewardTypeSummary()}`;

  renderPrizes(payload.prizes || []);
  renderRedeemCodes(payload.redeem_codes || []);
  state.recordPage = 1;
  renderRecords(payload.records || []);
  renderUserPityList(state.pityUsers);
}

async function bootstrap(forceToken = false) {
  if (state.initData && !forceToken) {
    state.authMode = "telegram";
    refs.authMode.textContent = "主人直登";
    const payload = await request("POST", "/plugins/slot-box/admin-api/bootstrap", {
      init_data: state.initData
    });
    applyPayload(payload);
    setStatus("已通过 Telegram 主人身份进入后台。", "success");
    return;
  }

  if (!state.token) {
    throw new Error("缺少后台令牌");
  }
  state.authMode = "token";
  refs.authMode.textContent = "令牌登录";
  const payload = await request("POST", "/plugins/slot-box/admin-api/bootstrap", {
    token: state.token
  });
  applyPayload(payload);
  setStatus("后台令牌验证通过。", "success");
}

refs.tokenForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.tokenSubmit.textContent;
  state.token = refs.tokenInput?.value.trim() || "";
  writeLocalStorage(storageKey, state.token);
  refs.tokenSubmit.disabled = true;
  refs.tokenSubmit.textContent = "验证中";
  setStatus("正在验证后台令牌。", "info");
  try {
    await bootstrap(true);
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.tokenSubmit.disabled = false;
    refs.tokenSubmit.textContent = previous;
  }
});

refs.settingsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.settingsSubmit.textContent;
  refs.settingsSubmit.disabled = true;
  refs.settingsSubmit.textContent = "保存中";
  try {
    const payload = await request("POST", "/plugins/slot-box/admin-api/settings", {
      enabled: checked("#setting-enabled"),
      title: field("#setting-title").value.trim(),
      notice: field("#setting-notice").value.trim(),
      blank_enabled: checked("#setting-blank-enabled"),
      blank_label: field("#setting-blank-label").value.trim(),
      blank_icon: field("#setting-blank-icon").value.trim(),
      blank_weight: numberValue("#setting-blank-weight", 0),
      pity_enabled: checked("#setting-pity-enabled"),
      pity_after: numberValue("#setting-pity-after", 1),
      daily_limit: numberValue("#setting-daily-limit", 0),
      spin_cost_iv: numberValue("#setting-spin-cost", 0),
      currency_name: field("#setting-currency").value.trim(),
      daily_limit_by_level: levelMap("setting-limit"),
      daily_gift_by_level: levelMap("setting-gift"),
      cooldown_seconds: numberValue("#setting-cooldown", 0),
      record_limit: numberValue("#setting-record-limit", 300)
    });
    applyPayload(payload);
    setStatus("玩法设置已保存。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.settingsSubmit.disabled = false;
    refs.settingsSubmit.textContent = previous;
  }
});

refs.userPitySearchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.userPitySearchSubmit?.innerHTML || "搜索用户";
  if (refs.userPitySearchSubmit) {
    refs.userPitySearchSubmit.disabled = true;
    refs.userPitySearchSubmit.textContent = "搜索中";
  }
  try {
    await searchUserPity();
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    if (refs.userPitySearchSubmit) {
      refs.userPitySearchSubmit.disabled = false;
      refs.userPitySearchSubmit.innerHTML = previous;
    }
  }
});

refs.userStatsResetAll?.addEventListener("click", async () => {
  const confirmed = window.confirm("确认清零所有用户的抽奖统计与抽奖记录？此操作不可撤销。");
  if (!confirmed) return;
  const button = refs.userStatsResetAll;
  const previous = button.innerHTML;
  button.disabled = true;
  button.textContent = "清零中";
  try {
    const payload = await request("POST", "/plugins/slot-box/admin-api/users/reset-all", {
      clear_records: true
    });
    applyPayload(payload);
    if (state.pityUsers.length) {
      try {
        await searchUserPity();
      } catch (error) {
        state.pityUsers = [];
        renderUserPityList(state.pityUsers);
      }
    } else {
      renderUserPityList(state.pityUsers);
    }
    const affected = Number(payload.reset_user_count || 0);
    setStatus(`已清零 ${affected} 名用户的抽奖统计。`, "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    button.disabled = false;
    button.innerHTML = previous;
  }
});

field("#prize-stock-unlimited")?.addEventListener("change", syncCreatePrizeControls);
field("#prize-reward-type")?.addEventListener("change", syncCreatePrizeControls);
syncCreatePrizeControls();

refs.prizeForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.prizeSubmit.textContent;
  refs.prizeSubmit.disabled = true;
  refs.prizeSubmit.textContent = "创建中";
  try {
    const payload = await request("POST", "/plugins/slot-box/admin-api/prize", {
      name: field("#prize-name").value.trim(),
      icon: field("#prize-icon").value.trim(),
      description: field("#prize-description").value.trim(),
      delivery_text: field("#prize-delivery").value.trim(),
      reward_type: field("#prize-reward-type").value,
      free_spin_quantity: numberValue("#prize-free-spin-quantity", 0),
      broadcast_image_url: field("#prize-broadcast-image").value.trim(),
      weight: numberValue("#prize-weight", 10),
      stock: checked("#prize-stock-unlimited") ? -1 : Math.max(numberValue("#prize-stock", 0), 0),
      enabled: checked("#prize-enabled"),
      guarantee_eligible: checked("#prize-guarantee"),
      guarantee_after: numberValue("#prize-guarantee-after", 0),
      broadcast_enabled: checked("#prize-broadcast")
    });
    applyPayload(payload);
    refs.prizeForm.reset();
    field("#prize-icon").value = "🎁";
    field("#prize-weight").value = 10;
    field("#prize-stock").value = -1;
    field("#prize-stock-unlimited").checked = true;
    field("#prize-reward-type").value = "manual";
    field("#prize-free-spin-quantity").value = 0;
    field("#prize-guarantee-after").value = 0;
    field("#prize-enabled").checked = true;
    field("#prize-guarantee").checked = true;
    field("#prize-broadcast").checked = false;
    syncCreatePrizeControls();
    setStatus("奖品已创建。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.prizeSubmit.disabled = false;
    refs.prizeSubmit.textContent = previous;
  }
});


refs.recordFilter?.addEventListener("change", (event) => {
  state.recordFilter = event.target.value || "all";
  state.recordPage = 1;
  renderRecords();
});

refs.recordPrev?.addEventListener("click", () => {
  state.recordPage -= 1;
  renderRecords();
});

refs.recordNext?.addEventListener("click", () => {
  state.recordPage += 1;
  renderRecords();
});

refs.redeemCodeForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.redeemCodeSubmit.textContent;
  refs.redeemCodeSubmit.disabled = true;
  refs.redeemCodeSubmit.textContent = "生成中";
  try {
    const payload = await request("POST", "/plugins/slot-box/admin-api/redeem-code", {
      code: field("#redeem-code-value").value.trim(),
      title: field("#redeem-code-title").value.trim(),
      max_uses: numberValue("#redeem-code-max-uses", 1),
      per_user_limit: numberValue("#redeem-code-per-user", 1),
      enabled: checked("#redeem-code-enabled"),
      grants: grantsPayload()
    });
    applyPayload(payload);
    refs.redeemCodeForm.reset();
    field("#redeem-code-title").value = "兑换码";
    field("#redeem-code-max-uses").value = 1;
    field("#redeem-code-per-user").value = 1;
    field("#redeem-code-enabled").checked = true;
    setStatus("兑换码已生成。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.redeemCodeSubmit.disabled = false;
    refs.redeemCodeSubmit.textContent = previous;
  }
});

(async () => {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#17120f");
    tg.setBackgroundColor("#111111");
    tg.BackButton?.hide?.();
  }
  try {
    await bootstrap();
  } catch (error) {
    refs.authMode.textContent = "待认证";
    setStatus(String(error.message || error), "error");
  }
})();
