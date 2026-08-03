const tg = window.Telegram?.WebApp || null;
const storageKey = "emby-shop-admin-token";

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
    setStatus("浏览器阻止了本地保存，仍会使用本次输入的令牌验证。", "warning");
  }
}

const state = {
  token: readLocalStorage(storageKey),
  initData: tg?.initData || "",
  authMode: null,
  payload: null
};

const refs = {
  status: document.querySelector("#admin-status"),
  authMode: document.querySelector("#admin-auth-mode"),
  tokenInput: document.querySelector("#admin-token"),
  tokenForm: document.querySelector("#token-form"),
  itemCount: document.querySelector("#admin-item-count"),
  orderCount: document.querySelector("#admin-order-count"),
  userListingState: document.querySelector("#admin-user-listing-state"),
  settingsForm: document.querySelector("#settings-form"),
  settingsSubmit: document.querySelector("#settings-submit"),
  itemForm: document.querySelector("#item-form"),
  itemSubmit: document.querySelector("#item-submit"),
  itemUpload: document.querySelector("#item-upload"),
  productList: document.querySelector("#admin-product-list"),
  orderList: document.querySelector("#admin-order-list")
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

async function request(method, url, payload, isForm = false) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: isForm ? authHeaders() : { ...authHeaders(), "Content-Type": "application/json" },
      body: payload ? (isForm ? payload : JSON.stringify(payload)) : undefined
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

async function uploadImage(file) {
  const body = new FormData();
  body.append("folder", "admin");
  body.append("file", file);
  return request("POST", "/plugins/shop/admin-api/upload-image", body, true);
}

function renderOrders(orders = []) {
  if (!orders.length) {
    refs.orderList.innerHTML = `<div class="empty">暂时还没有成交记录。</div>`;
    return;
  }
  refs.orderList.innerHTML = orders.map((order) => `
    <article class="stack-item">
      <div class="order-line">
        <strong>#${escapeHtml(order.id)} · ${escapeHtml(order.item_title)}</strong>
        <span class="tag">${escapeHtml(order.total_price_iv)}</span>
      </div>
      <p class="muted">买家 TG ${escapeHtml(order.buyer_tg)} · 卖家 ${escapeHtml(order.seller_tg || "官方")}</p>
      <p class="muted">${inviteItemLabel(order.item_type, order.invite_credit_quantity)}</p>
      <p class="muted">${escapeHtml(order.created_at || "")}</p>
    </article>
  `).join("");
}

function inviteItemLabel(itemType, quantity = 0) {
  if (itemType === "invite_credit" || itemType === "group_invite_credit") {
    return `入群资格 ${escapeHtml(quantity || 1)} 次/份`;
  }
  if (itemType === "account_open_credit") {
    return `注册资格 ${escapeHtml(quantity || 1)} 次/份`;
  }
  return "普通数字商品";
}

function renderItems(items = []) {
  if (!items.length) {
    refs.productList.innerHTML = `<div class="empty">当前还没有任何商品。</div>`;
    return;
  }
  refs.productList.innerHTML = items.map((item) => `
    <article class="stack-item">
      <div class="card-head">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="tag">${item.enabled ? "已上架" : "已下架"}</span>
      </div>
      <p class="muted">${escapeHtml(item.description || "暂无描述")}</p>
      <div class="product-meta">
        <span class="tag">价格 ${escapeHtml(item.price_iv)}</span>
        <span class="tag">库存 ${escapeHtml(item.stock)}</span>
        <span class="tag">${inviteItemLabel(item.item_type, item.invite_credit_quantity)}</span>
        <span class="tag">${item.official ? "官方商品" : "用户商品"}</span>
        ${item.notify_group ? `<span class="tag">群通知开启</span>` : ""}
      </div>
      <div class="form-actions">
        <button type="button" class="secondary" data-edit="${escapeHtml(item.id)}">编辑</button>
        <button type="button" class="secondary" data-toggle="${escapeHtml(item.id)}">${item.enabled ? "下架" : "上架"}</button>
        <button type="button" class="secondary" data-delete="${escapeHtml(item.id)}">删除</button>
      </div>
    </article>
  `).join("");

  refs.productList.querySelectorAll("[data-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = Number(button.dataset.toggle);
      const item = items.find((row) => Number(row.id) === itemId);
      if (!item) return;
      try {
        const payload = await request("PATCH", `/plugins/shop/admin-api/item/${itemId}`, {
          enabled: !item.enabled
        });
        applyPayload({ ...state.payload, items: payload.items || [] });
        setStatus("商品状态已更新。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });

  refs.productList.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = Number(button.dataset.edit);
      const item = items.find((row) => Number(row.id) === itemId);
      if (!item) return;
      const patch = promptItemPatch(item);
      if (!patch) return;
      try {
        button.disabled = true;
        button.textContent = "保存中...";
        const payload = await request("PATCH", `/plugins/shop/admin-api/item/${itemId}`, patch);
        applyPayload({ ...state.payload, items: payload.items || [] });
        setStatus("商品信息已更新。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      } finally {
        button.disabled = false;
        button.textContent = "编辑";
      }
    });
  });

  refs.productList.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = Number(button.dataset.delete);
      const confirmed = window.confirm("确认删除这个商品吗？");
      if (!confirmed) return;
      try {
        const payload = await request("DELETE", `/plugins/shop/admin-api/item/${itemId}`);
        applyPayload({ ...state.payload, items: payload.items || [] });
        setStatus("商品已经删除。", "success");
      } catch (error) {
        setStatus(String(error.message || error), "error");
      }
    });
  });
}

function promptItemPatch(item) {
  const title = window.prompt("商品标题：", item.title || "");
  if (title === null) return null;
  const itemType = window.prompt("商品类型（digital / group_invite_credit / account_open_credit）：", item.item_type || "digital");
  if (itemType === null) return null;
  const inviteQuantity = window.prompt("每份资格数量：", item.invite_credit_quantity ?? 0);
  if (inviteQuantity === null) return null;
  const priceIv = window.prompt("价格（Emby 货币）：", item.price_iv ?? 0);
  if (priceIv === null) return null;
  const stock = window.prompt("库存：", item.stock ?? 0);
  if (stock === null) return null;
  const imageUrl = window.prompt("图片地址：", item.image_url || "");
  if (imageUrl === null) return null;
  const description = window.prompt("商品描述：", item.description || "");
  if (description === null) return null;
  const deliveryText = window.prompt("自动发货内容：", item.delivery_text || "");
  if (deliveryText === null) return null;
  const notifyGroup = parseBooleanPrompt("是否通知群组（true/false）", item.notify_group);
  if (notifyGroup === null) return null;
  const official = parseBooleanPrompt("是否标记为官方商品（true/false）", item.official);
  if (official === null) return null;
  const enabled = parseBooleanPrompt("是否立即上架（true/false）", item.enabled);
  if (enabled === null) return null;
  return {
    title: title.trim(),
    item_type: itemType.trim(),
    invite_credit_quantity: Number(inviteQuantity || 0),
    price_iv: Number(priceIv || 0),
    stock: Number(stock || 0),
    image_url: imageUrl.trim(),
    description: description.trim(),
    delivery_text: deliveryText.trim(),
    notify_group: notifyGroup,
    official,
    enabled
  };
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

function applyPayload(payload = {}) {
  state.payload = payload;
  const settings = payload.settings || {};
  const items = payload.items || [];
  const orders = payload.orders || [];
  document.querySelector("#setting-title").value = settings.shop_title || "";
  document.querySelector("#setting-currency").value = settings.currency_name || "";
  document.querySelector("#setting-notice").value = settings.shop_notice || "";
  document.querySelector("#setting-allow-user-listing").checked = Boolean(settings.allow_user_listing);
  refs.itemCount.textContent = String(items.length);
  refs.orderCount.textContent = String(orders.length);
  refs.userListingState.textContent = settings.allow_user_listing ? "已开放" : "已关闭";
  renderItems(items);
  renderOrders(orders);
}

async function bootstrap(forceToken = false) {
  if (state.initData && !forceToken) {
    state.authMode = "telegram";
    refs.authMode.textContent = "主人直登";
    const payload = await request("POST", "/plugins/shop/admin-api/bootstrap", {
      init_data: state.initData
    });
    applyPayload(payload);
    setStatus("已通过 Telegram 主人身份进入商店后台。", "success");
    return;
  }

  if (!state.token) {
    throw new Error("缺少后台令牌");
  }
  state.authMode = "token";
  refs.authMode.textContent = "令牌登录";
  const payload = await request("POST", "/plugins/shop/admin-api/bootstrap", {
    token: state.token
  });
  applyPayload(payload);
  setStatus("后台令牌验证通过。", "success");
}

refs.tokenForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = document.querySelector("#token-submit");
  const previousText = submitButton?.textContent || "保存并验证";
  state.token = refs.tokenInput?.value.trim() || "";
  writeLocalStorage(storageKey, state.token);
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "验证中...";
  }
  setStatus("正在验证后台令牌...", "info");
  try {
    await bootstrap(true);
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = previousText;
    }
  }
});

refs.settingsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.settingsSubmit.textContent;
  refs.settingsSubmit.disabled = true;
  refs.settingsSubmit.textContent = "保存中...";
  try {
    const settings = await request("POST", "/plugins/shop/admin-api/settings", {
      shop_title: document.querySelector("#setting-title").value.trim(),
      currency_name: document.querySelector("#setting-currency").value.trim(),
      shop_notice: document.querySelector("#setting-notice").value.trim(),
      allow_user_listing: document.querySelector("#setting-allow-user-listing").checked
    });
    applyPayload({ ...state.payload, settings });
    setStatus("商店设置已保存。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.settingsSubmit.disabled = false;
    refs.settingsSubmit.textContent = previous;
  }
});

refs.itemUpload?.addEventListener("click", async () => {
  const file = document.querySelector("#item-image-file")?.files?.[0];
  if (!file) {
    window.alert("请先选择图片。");
    return;
  }
  const previous = refs.itemUpload.textContent;
  refs.itemUpload.disabled = true;
  refs.itemUpload.textContent = "上传中...";
  try {
    const payload = await uploadImage(file);
    document.querySelector("#item-image").value = payload.url || payload.relative_url || "";
    setStatus("商品图片上传成功。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.itemUpload.disabled = false;
    refs.itemUpload.textContent = previous;
  }
});

refs.itemForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.itemSubmit.textContent;
  refs.itemSubmit.disabled = true;
  refs.itemSubmit.textContent = "创建中...";
  try {
    const payload = await request("POST", "/plugins/shop/admin-api/item", {
      title: document.querySelector("#item-title").value.trim(),
      description: document.querySelector("#item-description").value.trim(),
      image_url: document.querySelector("#item-image").value.trim(),
      delivery_text: document.querySelector("#item-delivery").value.trim(),
      item_type: document.querySelector("#item-type").value,
      invite_credit_quantity: Number(document.querySelector("#item-invite-quantity").value || 0),
      price_iv: Number(document.querySelector("#item-price").value || 0),
      stock: Number(document.querySelector("#item-stock").value || 1),
      notify_group: document.querySelector("#item-notify").checked,
      official: document.querySelector("#item-official").checked,
      enabled: document.querySelector("#item-enabled").checked
    });
    applyPayload({ ...state.payload, items: payload.items || [], orders: payload.orders || state.payload.orders });
    refs.itemForm.reset();
    document.querySelector("#item-official").checked = true;
    document.querySelector("#item-enabled").checked = true;
    setStatus("商品已经创建成功。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
  } finally {
    refs.itemSubmit.disabled = false;
    refs.itemSubmit.textContent = previous;
  }
});

(async () => {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#f5efe5");
    tg.setBackgroundColor("#f5efe5");
  }
  try {
    await bootstrap();
  } catch (error) {
    refs.authMode.textContent = "待认证";
    setStatus(String(error.message || error), "error");
  }
})();
