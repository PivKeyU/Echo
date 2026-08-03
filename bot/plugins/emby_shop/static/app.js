const tg = window.Telegram?.WebApp || null;
const state = {
  initData: tg?.initData || "",
  bundle: null
};

const refs = {
  title: document.querySelector("#shop-title"),
  notice: document.querySelector("#shop-notice"),
  role: document.querySelector("#user-role"),
  balance: document.querySelector("#balance-amount"),
  itemCount: document.querySelector("#item-count"),
  myItemCount: document.querySelector("#my-item-count"),
  version: document.querySelector("#shop-version"),
  status: document.querySelector("#app-status"),
  refresh: document.querySelector("#refresh-button"),
  productList: document.querySelector("#product-list"),
  listingSection: document.querySelector("#listing-section"),
  myProductList: document.querySelector("#my-product-list"),
  listingForm: document.querySelector("#listing-form"),
  listingSubmit: document.querySelector("#listing-submit"),
  listingUpload: document.querySelector("#listing-upload"),
  adminEntry: document.querySelector("#shop-admin-entry")
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
  refs.status.textContent = text;
  refs.status.dataset.tone = tone;
}

async function request(method, url, payload) {
  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json"
    },
    body: payload ? JSON.stringify(payload) : undefined
  });
  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!response.ok || data.code !== 200) {
    throw new Error(data.detail || data.message || `请求失败（HTTP ${response.status}）`);
  }
  return data.data;
}

async function uploadImage(file) {
  const body = new FormData();
  body.append("folder", "user");
  body.append("file", file);
  const response = await fetch("/plugins/shop/api/upload-image", {
    method: "POST",
    headers: {
      "X-Telegram-Init-Data": state.initData
    },
    body
  });
  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!response.ok || data.code !== 200) {
    throw new Error(data.detail || data.message || "上传失败");
  }
  return data.data;
}

function renderMyItems(items = []) {
  if (!items.length) {
    refs.myProductList.innerHTML = `<div class="empty">你还没有发布商品。</div>`;
    return;
  }
  refs.myProductList.innerHTML = items.map((item) => `
    <article class="stack-item">
      <div class="card-head">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="tag">${item.enabled ? "已上架" : "已下架"}</span>
      </div>
      <p class="muted">${escapeHtml(item.description || "暂无描述")}</p>
      <div class="product-meta">
        <span class="tag">价格 ${escapeHtml(item.price_iv)}</span>
        <span class="tag">库存 ${escapeHtml(item.stock)}</span>
        <span class="tag">销量 ${escapeHtml(item.sold_count)}</span>
      </div>
    </article>
  `).join("");
}

function inviteItemType(itemType) {
  if (itemType === "invite_credit" || itemType === "group_invite_credit") return "group";
  if (itemType === "account_open_credit") return "account";
  return "";
}

function inviteItemLabel(item) {
  const type = inviteItemType(item?.item_type);
  if (type === "group") return "入群资格";
  if (type === "account") return "注册资格";
  return item?.official ? "官方" : "个人";
}

function renderProducts(items = []) {
  if (!items.length) {
    refs.productList.innerHTML = `<div class="empty">当前还没有可购买的商品。</div>`;
    return;
  }
  refs.productList.innerHTML = items.map((item) => {
    const inviteType = inviteItemType(item.item_type);
    const isInviteCredit = Boolean(inviteType);
    return `
    <article class="product-card">
      ${item.image_url ? `<img class="product-media" src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title)}">` : `<div class="product-media"></div>`}
      <div class="card-head">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="tag">${escapeHtml(inviteItemLabel(item))}</span>
      </div>
      <p class="muted">${escapeHtml(item.description || "暂无描述")}</p>
      <div class="product-meta">
        <span class="tag">库存 ${escapeHtml(item.stock)}</span>
        <span class="tag">销量 ${escapeHtml(item.sold_count)}</span>
        ${isInviteCredit ? `<span class="tag">每份 ${escapeHtml(item.invite_credit_quantity || 1)} 次</span>` : ""}
        ${item.owner_display_name ? `<span class="tag">卖家 ${escapeHtml(item.owner_display_name)}</span>` : ""}
      </div>
      <div class="card-head">
        <div class="product-price">${escapeHtml(item.price_iv)}</div>
        <button type="button" data-purchase="${escapeHtml(item.id)}">立即购买</button>
      </div>
    </article>
  `;
  }).join("");

  refs.productList.querySelectorAll("[data-purchase]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = Number(button.dataset.purchase);
      const item = items.find((row) => Number(row.id) === itemId);
      if (!item) return;
      const inviteType = inviteItemType(item.item_type);
      const deliveryHint = inviteType
        ? `购买后将获得 ${item.invite_credit_quantity || 1} 次${inviteItemLabel(item)}。`
        : "机器人会通过私聊自动发货。";
      const confirmed = window.confirm(`确认花费 ${item.price_iv} 购买《${item.title}》吗？${deliveryHint}`);
      if (!confirmed) return;
      const previous = button.textContent;
      button.disabled = true;
      button.textContent = "购买中...";
      try {
        const payload = await request("POST", "/plugins/shop/api/purchase", {
          init_data: state.initData,
          item_id: itemId,
          quantity: 1
        });
        applyBundle(payload);
        const inviteCount = payload.granted_invites?.length || 0;
        setStatus(
          inviteCount
            ? `已购买《${item.title}》，获得 ${inviteCount} 次${inviteItemLabel(item)}。`
            : `已购买《${item.title}》，机器人会把发货内容私聊给你。`,
          "success"
        );
        window.alert(`购买成功，订单号 #${payload.last_order?.id || "-"}`);
      } catch (error) {
        setStatus(String(error.message || error), "error");
        window.alert(String(error.message || error));
      } finally {
        button.disabled = false;
        button.textContent = previous;
      }
    });
  });
}

function applyBundle(bundle) {
  state.bundle = bundle || {};
  const settings = bundle.settings || {};
  const permissions = bundle.permissions || {};
  const account = bundle.account || {};
  refs.title.textContent = settings.shop_title || "Emby 光影商店";
  refs.notice.textContent = settings.shop_notice || "欢迎使用积分购买数字商品。";
  refs.balance.textContent = `${account.iv ?? 0} ${settings.currency_name || ""}`.trim();
  refs.itemCount.textContent = String((bundle.items || []).length);
  refs.myItemCount.textContent = String((bundle.my_items || []).length);
  refs.version.textContent = `v${bundle.meta?.version || "-"}`;
  refs.role.textContent = permissions.is_admin ? "管理员" : permissions.can_publish ? "卖家" : "普通用户";
  refs.adminEntry?.classList.toggle("hidden", !permissions.is_admin);
  if (refs.adminEntry && permissions.admin_url) {
    refs.adminEntry.href = permissions.admin_url;
  }
  refs.listingSection.classList.toggle("hidden", !permissions.can_publish);
  renderProducts(bundle.items || []);
  renderMyItems(bundle.my_items || []);
  renderBottomNav();
}

function renderBottomNav() {
  const nav = document.querySelector("#bottom-nav");
  if (!nav) return;
  const configuredItems = Array.isArray(state.bundle?.meta?.bottom_nav) ? state.bundle.meta.bottom_nav : [];
  const items = configuredItems.length ? configuredItems : [
    { label: "主页", path: "/miniapp", icon: "🏠" },
    { label: "商店", path: "/plugins/shop/app", icon: "🛒" }
  ];
  const currentPath = window.location.pathname;
  nav.innerHTML = "";
  for (const item of items) {
    const link = document.createElement("a");
    link.href = item.path;
    link.textContent = `${item.icon || ""} ${item.label || item.id || "入口"}`.trim();
    if (item.path === currentPath) {
      link.classList.add("is-active");
    }
    nav.appendChild(link);
  }
}

async function bootstrap() {
  setStatus("正在同步商店数据...");
  const data = await request("POST", "/plugins/shop/api/bootstrap", { init_data: state.initData });
  applyBundle(data);
  setStatus("商店数据已同步。", "success");
}

refs.refresh?.addEventListener("click", () => {
  bootstrap().catch((error) => {
    setStatus(String(error.message || error), "error");
  });
});

refs.listingUpload?.addEventListener("click", async () => {
  const file = document.querySelector("#listing-image-file")?.files?.[0];
  if (!file) {
    window.alert("请先选择一张图片。");
    return;
  }
  const previous = refs.listingUpload.textContent;
  refs.listingUpload.disabled = true;
  refs.listingUpload.textContent = "上传中...";
  try {
    const payload = await uploadImage(file);
    document.querySelector("#listing-image").value = payload.url || payload.relative_url || "";
    setStatus("图片上传成功。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
    window.alert(String(error.message || error));
  } finally {
    refs.listingUpload.disabled = false;
    refs.listingUpload.textContent = previous;
  }
});

refs.listingForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const previous = refs.listingSubmit.textContent;
  refs.listingSubmit.disabled = true;
  refs.listingSubmit.textContent = "发布中...";
  try {
    const payload = await request("POST", "/plugins/shop/api/listing", {
      init_data: state.initData,
      title: document.querySelector("#listing-title").value.trim(),
      description: document.querySelector("#listing-description").value.trim(),
      image_url: document.querySelector("#listing-image").value.trim(),
      delivery_text: document.querySelector("#listing-delivery").value.trim(),
      price_iv: Number(document.querySelector("#listing-price").value || 0),
      stock: Number(document.querySelector("#listing-stock").value || 1),
      notify_group: document.querySelector("#listing-notify").checked
    });
    applyBundle(payload);
    refs.listingForm.reset();
    setStatus("商品发布成功。", "success");
  } catch (error) {
    setStatus(String(error.message || error), "error");
    window.alert(String(error.message || error));
  } finally {
    refs.listingSubmit.disabled = false;
    refs.listingSubmit.textContent = previous;
  }
});

(async () => {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#101010");
    tg.setBackgroundColor("#101010");
    tg.BackButton.show();
    tg.BackButton.onClick(() => {
      window.location.href = "/miniapp";
    });
  }
  try {
    await bootstrap();
  } catch (error) {
    setStatus(String(error.message || error), "error");
  }
})();
