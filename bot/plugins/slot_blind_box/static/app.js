const tg = window.Telegram?.WebApp || null;

const state = {
  initData: tg?.initData || "",
  payload: null,
  symbols: ["🎁", "🍒", "🍋", "🔔", "7️⃣", "💰", "🎟️", "⭐"],
  spinning: false,
  reelTimers: [],
  recordPage: 1,
  recordPageSize: 10,
  recordFilter: "all",
  records: [],
  transferTarget: null,
  transferSearchTimer: null,
  transferSearchSeq: 0,
  transferSearchResults: []
};

const refs = {
  title: document.querySelector("#slot-title"),
  notice: document.querySelector("#slot-notice"),
  status: document.querySelector("#app-status"),
  adminEntry: document.querySelector("#slot-admin-entry"),
  spinButton: document.querySelector("#spin-button"),
  refreshButton: document.querySelector("#refresh-button"),
  resultPanel: document.querySelector("#result-panel"),
  reels: Array.from(document.querySelectorAll(".reel")),
  pityMeter: document.querySelector("#pity-meter"),
  limitMeter: document.querySelector("#limit-meter"),
  balanceCount: document.querySelector("#balance-count"),
  spinCost: document.querySelector("#spin-cost"),
  dailyGiftCount: document.querySelector("#daily-gift-count"),
  ticketCount: document.querySelector("#ticket-count"),
  spinCount: document.querySelector("#spin-count"),
  winCount: document.querySelector("#win-count"),
  blankCount: document.querySelector("#blank-count"),
  prizeCount: document.querySelector("#prize-count"),
  blankRate: document.querySelector("#blank-rate"),
  myStreak: document.querySelector("#my-streak"),
  prizeList: document.querySelector("#prize-list"),
  recordList: document.querySelector("#record-list"),
  recordFilter: document.querySelector("#record-filter"),
  recordPrev: document.querySelector("#record-prev"),
  recordNext: document.querySelector("#record-next"),
  recordPageInfo: document.querySelector("#record-page-info"),
  backpackList: document.querySelector("#backpack-list"),
  redeemForm: document.querySelector("#redeem-form"),
  redeemSubmit: document.querySelector("#redeem-submit"),
  transferForm: document.querySelector("#transfer-form"),
  transferSubmit: document.querySelector("#transfer-submit"),
  transferTargetQuery: document.querySelector("#transfer-target-query"),
  transferTargetInput: document.querySelector("#transfer-target"),
  transferTargetResults: document.querySelector("#transfer-target-results"),
  transferTargetSelected: document.querySelector("#transfer-target-selected"),
  shopAdminLink: document.querySelector("#shop-admin-link"),
  bottomNav: document.querySelector("#bottom-nav"),
  machineBand: document.querySelector(".machine-band")
};

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

async function request(url, payload) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
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

function randomSymbol() {
  const symbols = state.symbols.length ? state.symbols : ["🎁", "🍒", "🔔", "7️⃣", "⭐"];
  return symbols[Math.floor(Math.random() * symbols.length)] || "🍒";
}

function randomSymbolExcept(excludedSymbols = []) {
  const excluded = new Set(excludedSymbols.map((symbol) => String(symbol || "").trim()).filter(Boolean));
  const candidates = (state.symbols.length ? state.symbols : ["🎁", "🍒", "🔔", "7️⃣", "⭐"])
    .map((symbol) => String(symbol || "").trim())
    .filter((symbol) => symbol && !excluded.has(symbol));
  const symbols = candidates.length ? candidates : ["🍒", "🍋", "🔔", "⭐"].filter((symbol) => !excluded.has(symbol));
  return symbols[Math.floor(Math.random() * symbols.length)] || "🍒";
}

function reelStripHtml(centerSymbol, { locked = false } = {}) {
  const center = centerSymbol || randomSymbol();
  const top = locked ? randomSymbolExcept([center]) : randomSymbol();
  const bottom = locked ? randomSymbolExcept([center, top]) : randomSymbol();
  return `<span class="reel-strip"><span>${escapeHtml(top)}</span><span class="payline-symbol">${escapeHtml(center)}</span><span>${escapeHtml(bottom)}</span></span>`;
}

function setReelSymbol(reel, symbol) {
  reel.innerHTML = reelStripHtml(symbol, { locked: true });
}

function normalizeFinalReels(result = {}) {
  const raw = Array.isArray(result.reels)
    ? result.reels.slice(0, 3).map((symbol) => String(symbol || "").trim()).filter(Boolean)
    : [];
  if (result.outcome === "win") {
    const symbol = String(result.prize?.icon || raw[0] || "🎁").trim() || "🎁";
    return [symbol, symbol, symbol];
  }
  while (raw.length < 3) raw.push(randomSymbol());
  return raw.slice(0, 3);
}

function setMachineState(className, enabled) {
  if (!refs.machineBand) return;
  refs.machineBand.classList.toggle(className, Boolean(enabled));
}

function clearReelMotionClasses(reel) {
  reel.classList.remove("spinning", "is-settled");
}

function startReels() {
  stopReels();
  state.spinning = true;
  setMachineState("is-winning", false);
  setMachineState("is-spinning", true);
  refs.reels.forEach((reel, index) => {
    clearReelMotionClasses(reel);
    reel.classList.add("spinning");
    state.reelTimers[index] = window.setInterval(() => {
      reel.innerHTML = reelStripHtml(randomSymbol());
    }, 58 + index * 18);
  });
}

function stopReels(finalReels = []) {
  state.reelTimers.forEach((timer) => window.clearInterval(timer));
  state.reelTimers = [];
  refs.reels.forEach((reel, index) => {
    clearReelMotionClasses(reel);
    setReelSymbol(reel, finalReels[index] || randomSymbol());
  });
  setMachineState("is-spinning", false);
  state.spinning = false;
}

async function settleReels(finalReels) {
  state.reelTimers.forEach((timer) => window.clearInterval(timer));
  state.reelTimers = [];
  for (let index = 0; index < refs.reels.length; index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 190 + index * 110));
    const reel = refs.reels[index];
    reel.classList.remove("spinning");
    setReelSymbol(reel, finalReels[index] || randomSymbol());
    reel.classList.remove("is-settled");
    void reel.offsetWidth;
    reel.classList.add("is-settled");
  }
  setMachineState("is-spinning", false);
  state.spinning = false;
}

function firePrizeBurst(outcome = "blank") {
  if (!refs.machineBand || outcome !== "win") return;
  const colors = ["#facc15", "#38bdf8", "#fb7185", "#a78bfa", "#22c55e"];
  const count = 22;
  for (let index = 0; index < count; index += 1) {
    const particle = document.createElement("span");
    particle.className = "burst-particle";
    particle.style.setProperty("--x", `${42 + Math.random() * 16}%`);
    particle.style.setProperty("--y", `${52 + Math.random() * 12}%`);
    particle.style.setProperty("--dx", `${Math.round((Math.random() - 0.5) * 180)}px`);
    particle.style.setProperty("--c", colors[index % colors.length]);
    particle.style.animationDelay = `${index * 22}ms`;
    refs.machineBand.appendChild(particle);
    window.setTimeout(() => particle.remove(), 1200);
  }
}

function renderBottomNav(items = []) {
  if (!refs.bottomNav) return;
  if (!items.length) {
    refs.bottomNav.classList.add("hidden");
    return;
  }
  refs.bottomNav.classList.remove("hidden");
  const currentPath = window.location.pathname;
  refs.bottomNav.innerHTML = items.map((item) => {
    const active = item.path === currentPath ? "is-active" : "";
    return `
      <a class="${active}" href="${escapeHtml(item.path)}">
        <span class="nav-icon">${escapeHtml(item.icon || "◇")}</span>
        <span>${escapeHtml(item.label || item.id || "入口")}</span>
      </a>
    `;
  }).join("");
}

function renderPrizes(prizes = []) {
  if (!prizes.length) {
    refs.prizeList.innerHTML = `<div class="empty">当前奖池为空。</div>`;
    return;
  }
  refs.prizeList.innerHTML = prizes.map((prize, index) => `
    <article class="prize-card" style="--i:${index}">
      <div class="prize-card-head">
        <span class="prize-icon">${escapeHtml(prize.icon || "🎁")}</span>
        <span class="rate-text">${escapeHtml(prize.computed_rate ?? 0)}%</span>
      </div>
      <h3>${escapeHtml(prize.name)}</h3>
      <p class="muted">${escapeHtml(prize.description || "")}</p>
      <p class="muted">${escapeHtml(prize.reward_label || "普通奖品")}</p>
      <p class="muted">${prize.guarantee_eligible ? `保底 ${Number(prize.guarantee_after || 0) > 0 ? `${escapeHtml(prize.guarantee_after)} 次` : "跟随全局"}` : "不参与保底"}</p>
      <p class="muted">库存 ${Number(prize.stock) < 0 ? "不限" : escapeHtml(prize.stock)}</p>
    </article>
  `).join("");
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

function reelStripText(reels = []) {
  const symbols = Array.isArray(reels) ? reels.slice(0, 3) : [];
  while (symbols.length < 3) symbols.push("◇");
  return symbols.join(" ");
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
    refs.recordList.innerHTML = pageItems.map((record, index) => `
      <article class="record-item" style="--i:${index}" data-outcome="${escapeHtml(record.outcome)}">
        <div class="record-line">
          <strong>${escapeHtml(record.prize_icon || "🍀")} ${escapeHtml(record.prize_name || "轮空")}</strong>
          <span class="status-pill">${escapeHtml(recordTypeLabel(record))}</span>
        </div>
        <div class="record-reels" aria-label="转轮结果">${escapeHtml(reelStripText(record.reels))}</div>
        <p class="muted">${escapeHtml(record.created_at || "")}${record.pity_triggered ? " · 保底" : ""}</p>
      </article>
    `).join("");
  }
  if (refs.recordPageInfo) refs.recordPageInfo.textContent = `${state.recordPage}/${totalPages} · ${filtered.length} 条`;
  if (refs.recordPrev) refs.recordPrev.disabled = state.recordPage <= 1;
  if (refs.recordNext) refs.recordNext.disabled = state.recordPage >= totalPages;
}

function backpackItemHint(type) {
  if (type === "group_invite_credit") return "使用后会添加到账号下，可在 MiniApp 主页发送入群邀请。";
  if (type === "account_open_credit") return "使用前会校验你是否在主群内，通过后获得 30 天注册资格。";
  if (type === "free_spin_ticket") return "抽奖时自动抵扣，无需手动使用。";
  return "可转赠；交易请前往 Emby 商店。";
}

function canUseBackpackItem(item = {}) {
  return ["group_invite_credit", "account_open_credit"].includes(item.type) && Number(item.quantity || 0) > 0;
}

function renderBackpack(items = []) {
  if (!refs.backpackList) return;
  if (!items.length) {
    refs.backpackList.innerHTML = `<div class="empty">背包为空。</div>`;
    return;
  }
  refs.backpackList.innerHTML = items.map((item, index) => `
    <article class="prize-card backpack-card" style="--i:${index}">
      <div class="prize-card-head">
        <span class="prize-icon">${escapeHtml(item.icon || "◇")}</span>
        <span class="rate-text">x${escapeHtml(item.quantity ?? 0)}</span>
      </div>
      <h3>${escapeHtml(item.label || item.type)}</h3>
      <p class="muted">${escapeHtml(backpackItemHint(item.type))}</p>
      ${canUseBackpackItem(item) ? `
        <div class="backpack-actions">
          <button type="button" class="secondary use-backpack-item" data-item-type="${escapeHtml(item.type)}">
            <span class="button-icon">${item.type === "account_open_credit" ? "🪪" : "📨"}</span><span>使用</span>
          </button>
        </div>
      ` : ""}
    </article>
  `).join("");
}

function targetMetaLine(item = {}) {
  const parts = [];
  if (item.username) parts.push(`@${item.username}`);
  if (item.emby_name) parts.push(`Emby ${item.emby_name}`);
  if (item.embyid) parts.push(item.embyid);
  parts.push(`TG ${item.tg}`);
  return parts.filter(Boolean).join(" · ");
}

function renderTransferTargets(items = []) {
  state.transferSearchResults = Array.isArray(items) ? items : [];
  if (!refs.transferTargetResults) return;
  if (!state.transferSearchResults.length) {
    refs.transferTargetResults.classList.remove("hidden");
    refs.transferTargetResults.innerHTML = `<div class="empty compact-empty">没有找到匹配用户。</div>`;
    return;
  }
  refs.transferTargetResults.classList.remove("hidden");
  refs.transferTargetResults.innerHTML = state.transferSearchResults.map((item) => `
    <button type="button" class="target-result" data-target-tg="${escapeHtml(item.tg)}" ${item.is_self ? "disabled" : ""}>
      <span class="target-avatar">${escapeHtml((item.display_label || "TG").slice(0, 1).toUpperCase())}</span>
      <span class="target-main">
        <strong>${escapeHtml(item.display_label || `TG ${item.tg}`)}</strong>
        <small>${escapeHtml(targetMetaLine(item))}${item.is_self ? " · 不能转赠给自己" : ""}</small>
      </span>
    </button>
  `).join("");
}

function clearTransferTarget() {
  state.transferTarget = null;
  if (refs.transferTargetInput) refs.transferTargetInput.value = "";
  if (refs.transferTargetSelected) refs.transferTargetSelected.textContent = "尚未选择接收方。";
}

function selectTransferTarget(item = {}) {
  state.transferTarget = item;
  if (refs.transferTargetInput) refs.transferTargetInput.value = String(item.tg || "");
  if (refs.transferTargetQuery) refs.transferTargetQuery.value = item.display_label || `TG ${item.tg}`;
  if (refs.transferTargetSelected) {
    refs.transferTargetSelected.textContent = `已选择：${item.display_label || `TG ${item.tg}`}（TG ${item.tg}）`;
  }
  refs.transferTargetResults?.classList.add("hidden");
}

async function searchTransferTargets(query) {
  const normalized = String(query || "").trim();
  clearTransferTarget();
  if (!normalized || (normalized.length < 2 && !/^@?\d+$/.test(normalized))) {
    state.transferSearchResults = [];
    refs.transferTargetResults?.classList.add("hidden");
    return;
  }
  const seq = ++state.transferSearchSeq;
  refs.transferTargetResults?.classList.remove("hidden");
  if (refs.transferTargetResults) {
    refs.transferTargetResults.innerHTML = `<div class="empty compact-empty">正在搜索...</div>`;
  }
  try {
    const payload = await request("/plugins/slot-box/api/transfer-targets", {
      init_data: state.initData,
      query: normalized
    });
    if (seq !== state.transferSearchSeq) return;
    renderTransferTargets(payload.items || []);
  } catch (error) {
    if (seq !== state.transferSearchSeq) return;
    if (refs.transferTargetResults) {
      refs.transferTargetResults.innerHTML = `<div class="empty compact-empty">${escapeHtml(error.message || "搜索失败")}</div>`;
    }
  }
}

function renderResult(result) {
  if (!result) return;
  refs.resultPanel.classList.remove("hidden");
  refs.resultPanel.dataset.outcome = result.outcome || "blank";
  const prize = result.prize || {};
  const icon = prize.icon || (result.outcome === "win" ? "🎁" : "🍀");
  refs.resultPanel.innerHTML = `
    <div class="result-hero">
      <span class="result-icon">${escapeHtml(icon)}</span>
      <div>
        <div class="record-line">
          <h3>${escapeHtml(result.title || "结果")}</h3>
          <span class="status-pill">${result.pity_triggered ? "保底触发" : result.outcome === "win" ? "中奖" : "轮空"}</span>
        </div>
        <p class="muted">${escapeHtml(result.message || "")}</p>
      </div>
    </div>
    <div class="result-detail">
      <p class="muted">本次消耗：${escapeHtml(result.payment_label || "-")}</p>
      ${prize.name ? `<p class="muted">奖品：${escapeHtml(prize.name)}</p>` : ""}
    </div>
  `;
}

function applyPayload(payload = {}) {
  state.payload = payload;
  state.symbols = payload.meta?.symbols || state.symbols;
  const settings = payload.settings || {};
  const stats = payload.stats || {};
  const userStats = payload.user_stats || {};
  const probabilities = payload.probabilities || {};
  const limits = payload.limits || {};
  const account = payload.account || null;
  refs.title.textContent = settings.title || "老虎机盲盒";
  refs.notice.textContent = settings.notice || "";
  refs.spinButton.disabled = !settings.enabled || state.spinning || Boolean(payload.limits?.wait_seconds);
  refs.balanceCount.textContent = account ? String(account.iv ?? 0) : "无账号";
  refs.spinCost.textContent = `${limits.spin_cost_iv ?? settings.spin_cost_iv ?? 0}`;
  refs.dailyGiftCount.textContent = `${limits.daily_free_remaining ?? 0}/${limits.daily_gift_total ?? 0}`;
  refs.ticketCount.textContent = String(limits.free_spin_tickets ?? userStats.free_spin_tickets ?? 0);
  refs.spinCount.textContent = String(userStats.total_spins ?? 0);
  refs.winCount.textContent = String(userStats.win_count ?? 0);
  refs.blankCount.textContent = String(userStats.blank_count ?? 0);
  refs.prizeCount.textContent = String(stats.active_prize_count ?? 0);
  refs.blankRate.textContent = `轮空 ${probabilities.blank_rate ?? 0}%`;
  refs.myStreak.textContent = `连续未中 ${userStats.miss_streak ?? 0}`;

  if (settings.pity_enabled) {
    const nextGuarantee = limits.next_guarantee || null;
    if (nextGuarantee) {
      refs.pityMeter.textContent = `${nextGuarantee.prize_name || "保底"} ${nextGuarantee.current}/${nextGuarantee.threshold}`;
    } else {
      refs.pityMeter.textContent = "无保底奖品";
    }
  } else {
    refs.pityMeter.textContent = "保底关闭";
  }

  const dailyRemaining = payload.limits?.daily_remaining;
  const waitSeconds = Number(payload.limits?.wait_seconds || 0);
  refs.limitMeter.dataset.hot = "false";
  if (waitSeconds > 0) {
    refs.limitMeter.textContent = `冷却 ${waitSeconds}s`;
  } else if (dailyRemaining === null || dailyRemaining === undefined) {
    refs.limitMeter.textContent = "次数不限";
    refs.limitMeter.dataset.hot = "true";
  } else {
    refs.limitMeter.textContent = `剩余 ${dailyRemaining} · ${limits.user_level_text || "未知"}`;
    refs.limitMeter.dataset.hot = Number(dailyRemaining) > 0 ? "true" : "false";
    if (Number(dailyRemaining) <= 0) refs.spinButton.disabled = true;
  }

  if (payload.permissions?.admin_url) {
    refs.adminEntry.href = payload.permissions.admin_url;
    refs.adminEntry.classList.remove("hidden");
  } else {
    refs.adminEntry.classList.add("hidden");
  }

  if (refs.shopAdminLink) {
    refs.shopAdminLink.classList.toggle("hidden", !payload.permissions?.is_admin);
  }

  renderPrizes(payload.prizes || []);
  state.recordPage = 1;
  renderRecords(payload.records || []);
  renderBackpack(payload.backpack || []);
  renderBottomNav(payload.meta?.bottom_nav || []);
}

async function mutateWithButton(button, pendingText, url, payload, successText) {
  const previous = button.innerHTML;
  button.disabled = true;
  button.textContent = pendingText;
  try {
    const nextPayload = await request(url, payload);
    applyPayload(nextPayload);
    setStatus(successText, "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    button.disabled = false;
    button.innerHTML = previous;
  }
}

async function useBackpackItem(button) {
  const itemType = button?.dataset?.itemType || "";
  if (!itemType) return;
  const previous = button.innerHTML;
  button.disabled = true;
  button.textContent = "使用中";
  try {
    const nextPayload = await request("/plugins/slot-box/api/backpack/use", {
      init_data: state.initData,
      item_type: itemType
    });
    applyPayload(nextPayload);
    setStatus(nextPayload.message || "已使用。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    button.disabled = false;
    button.innerHTML = previous;
  }
}

async function bootstrap() {
  if (!state.initData) {
    throw new Error("请从 Telegram 小程序入口打开。");
  }
  const payload = await request("/plugins/slot-box/api/bootstrap", { init_data: state.initData });
  applyPayload(payload);
  setStatus("奖池已同步。", "success");
}

async function spin() {
  if (state.spinning) return;
  if (!state.initData) {
    setStatus("请从 Telegram 小程序入口打开。", "error");
    return;
  }
  refs.spinButton.disabled = true;
  refs.refreshButton.disabled = true;
  refs.resultPanel.classList.add("hidden");
  setStatus("转轮启动。", "info");
  startReels();
  const startedAt = Date.now();
  try {
    const payload = await request("/plugins/slot-box/api/spin", { init_data: state.initData });
    const delay = Math.max(900 - (Date.now() - startedAt), 0);
    if (delay) await new Promise((resolve) => window.setTimeout(resolve, delay));
    const finalReels = normalizeFinalReels(payload.result || {});
    if (payload.result) payload.result.reels = finalReels;
    await settleReels(finalReels);
    const won = payload.result?.outcome === "win";
    setMachineState("is-winning", won);
    firePrizeBurst(payload.result?.outcome);
    applyPayload(payload);
    renderResult(payload.result);
    setStatus(won ? "已中奖。" : "本次轮空。", won ? "success" : "info");
    if (won) window.setTimeout(() => setMachineState("is-winning", false), 2400);
  } catch (error) {
    stopReels();
    setMachineState("is-winning", false);
    setStatus(String(error.message || error), "error");
  } finally {
    refs.refreshButton.disabled = false;
    const waitSeconds = Number(state.payload?.limits?.wait_seconds || 0);
    const dailyRemaining = state.payload?.limits?.daily_remaining;
    const dailyLimitReached = dailyRemaining !== null && dailyRemaining !== undefined && Number(dailyRemaining) <= 0;
    refs.spinButton.disabled = !state.payload?.settings?.enabled || waitSeconds > 0 || dailyLimitReached;
  }
}

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

refs.spinButton?.addEventListener("click", spin);
refs.refreshButton?.addEventListener("click", async () => {
  refs.refreshButton.disabled = true;
  setStatus("正在刷新。", "info");
  try {
    await bootstrap();
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.refreshButton.disabled = false;
  }
});

refs.redeemForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = document.querySelector("#redeem-code")?.value.trim() || "";
  if (!code) return;
  await mutateWithButton(refs.redeemSubmit, "兑换中", "/plugins/slot-box/api/redeem", {
    init_data: state.initData,
    code
  }, "兑换成功。");
});

refs.backpackList?.addEventListener("click", async (event) => {
  const button = event.target.closest(".use-backpack-item");
  if (!button) return;
  await useBackpackItem(button);
});

refs.transferForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const targetTg = Number(refs.transferTargetInput?.value || 0);
  if (!targetTg) {
    setStatus("请先搜索并选择接收方。", "error");
    refs.transferTargetQuery?.focus();
    return;
  }
  await mutateWithButton(refs.transferSubmit, "转赠中", "/plugins/slot-box/api/transfer", {
    init_data: state.initData,
    item_type: document.querySelector("#transfer-type")?.value,
    quantity: Number(document.querySelector("#transfer-quantity")?.value || 1),
    target_tg: targetTg
  }, "转赠完成。");
});

refs.transferTargetQuery?.addEventListener("input", (event) => {
  window.clearTimeout(state.transferSearchTimer);
  const query = event.target.value || "";
  state.transferSearchTimer = window.setTimeout(() => searchTransferTargets(query), 260);
});

refs.transferTargetResults?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-target-tg]");
  if (!button || button.disabled) return;
  const targetTg = Number(button.dataset.targetTg || 0);
  const selected = state.transferSearchResults.find((item) => Number(item.tg) === targetTg) || {
    tg: targetTg,
    display_label: `TG ${targetTg}`
  };
  selectTransferTarget(selected);
});

(async () => {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#0b1020");
    tg.setBackgroundColor("#0b1020");
    tg.BackButton?.hide?.();
  }
  try {
    await bootstrap();
  } catch (error) {
    setStatus(String(error.message || error), "error");
  }
})();
