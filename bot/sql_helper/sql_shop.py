from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from bot import pivkeyu
from bot.func_helper import redis_cache
from bot.plugins.sdk.memory_cache import get_memory_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby


UTC_TZ = timezone.utc
SHANGHAI_TZ = timezone(timedelta(hours=8))
# 商店金额需要覆盖大额上架场景，同时保持前端 Number / JSON 可精确表达。
MAX_SHOP_PRICE_IV = 9_007_199_254_740_991
MAX_SQL_INTEGER = 2_147_483_647
DEFAULT_SHOP_SETTINGS = {
    "allow_user_listing": False,
    # 商店默认沿用全局配置中的货币名称。
    "currency_name": pivkeyu,
    "shop_title": "Emby 光影商店",
    "shop_notice": "欢迎使用 Emby 货币购买数字商品。",
}

SHOP_CACHE_TTL = 120
_SHOP_MEMORY_CACHE = get_memory_cache()


def _shop_version_key(scope: str) -> str:
    return redis_cache.build_key("shop", "version", scope)


def _bump_shop_cache(*scopes: str) -> None:
    bumped = False
    for scope in scopes:
        if scope:
            redis_cache.increment(_shop_version_key(scope))
            bumped = True
    if bumped:
        _SHOP_MEMORY_CACHE.delete_prefix("shop:")


def _load_shop_cached(cache_key: str, version_scope: str, loader):
    version = str(max(redis_cache.get_int(_shop_version_key(version_scope), 1), 1))
    memory_key = f"shop:{cache_key}:v{version}"
    cached = _SHOP_MEMORY_CACHE.get(memory_key)
    if cached is not None:
        return cached

    redis_key = redis_cache.build_key("shop", "cache", memory_key)
    if redis_cache.redis_enabled():
        hit, payload = redis_cache.get_json(redis_key)
        if hit:
            _SHOP_MEMORY_CACHE.set(memory_key, payload, SHOP_CACHE_TTL)
            return payload

    payload = loader()
    _SHOP_MEMORY_CACHE.set(memory_key, payload, SHOP_CACHE_TTL)
    if redis_cache.redis_enabled():
        redis_cache.set_json(redis_key, payload, SHOP_CACHE_TTL)
    return payload

SHOP_ITEM_TYPE_DIGITAL = "digital"
SHOP_ITEM_TYPE_GROUP_INVITE = "group_invite_credit"
SHOP_ITEM_TYPE_ACCOUNT_OPEN = "account_open_credit"
LEGACY_SHOP_ITEM_TYPE_INVITE = "invite_credit"
SHOP_ITEM_TYPES = {
    SHOP_ITEM_TYPE_DIGITAL,
    SHOP_ITEM_TYPE_GROUP_INVITE,
    SHOP_ITEM_TYPE_ACCOUNT_OPEN,
    LEGACY_SHOP_ITEM_TYPE_INVITE,
}


def utcnow() -> datetime:
    return datetime.utcnow()


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TZ)
    return value.astimezone(SHANGHAI_TZ).isoformat()


def _normalize_non_negative_int(value: Any, *, field_name: str, max_value: int | None = None) -> int:
    try:
        normalized = int(value or 0)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须是整数") from None
    if normalized < 0:
        raise ValueError(f"{field_name}不能小于 0")
    if max_value is not None and normalized > max_value:
        raise ValueError(f"{field_name}不能超过 {max_value}")
    return normalized


def _normalize_shop_price(value: Any) -> int:
    return _normalize_non_negative_int(value, field_name="商品价格", max_value=MAX_SHOP_PRICE_IV)


class ShopSetting(Base):
    __tablename__ = "shop_settings"

    setting_key = Column(String(64), primary_key=True)
    setting_value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ShopItem(Base):
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_tg = Column(BigInteger, nullable=True)
    owner_display_name = Column(String(128), nullable=True)
    owner_username = Column(String(64), nullable=True)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    delivery_text = Column(Text, nullable=True)
    item_type = Column(String(32), default="digital", nullable=False)
    invite_credit_quantity = Column(Integer, default=0, nullable=False)
    price_iv = Column(BigInteger, default=0, nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    sold_count = Column(Integer, default=0, nullable=False)
    notify_group = Column(Boolean, default=False, nullable=False)
    official = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    buyer_tg = Column(BigInteger, nullable=False)
    seller_tg = Column(BigInteger, nullable=True)
    item_title = Column(String(128), nullable=False)
    image_url = Column(String(512), nullable=True)
    delivery_text = Column(Text, nullable=True)
    item_type = Column(String(32), default="digital", nullable=False)
    invite_credit_quantity = Column(Integer, default=0, nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price_iv = Column(BigInteger, default=0, nullable=False)
    total_price_iv = Column(BigInteger, default=0, nullable=False)
    status = Column(String(32), default="delivered", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


def serialize_shop_item(item: ShopItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.id,
        "owner_tg": item.owner_tg,
        "owner_display_name": item.owner_display_name,
        "owner_username": item.owner_username,
        "title": item.title,
        "description": item.description or "",
        "image_url": item.image_url or "",
        "delivery_text": item.delivery_text or "",
        "item_type": item.item_type or SHOP_ITEM_TYPE_DIGITAL,
        "invite_credit_quantity": int(item.invite_credit_quantity or 0),
        "price_iv": int(item.price_iv or 0),
        "stock": int(item.stock or 0),
        "sold_count": int(item.sold_count or 0),
        "notify_group": bool(item.notify_group),
        "official": bool(item.official),
        "enabled": bool(item.enabled),
        "created_at": serialize_datetime(item.created_at),
        "updated_at": serialize_datetime(item.updated_at),
    }


def serialize_shop_order(order: ShopOrder | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "id": order.id,
        "item_id": order.item_id,
        "buyer_tg": order.buyer_tg,
        "seller_tg": order.seller_tg,
        "item_title": order.item_title,
        "image_url": order.image_url or "",
        "delivery_text": order.delivery_text or "",
        "item_type": order.item_type or SHOP_ITEM_TYPE_DIGITAL,
        "invite_credit_quantity": int(order.invite_credit_quantity or 0),
        "quantity": int(order.quantity or 0),
        "unit_price_iv": int(order.unit_price_iv or 0),
        "total_price_iv": int(order.total_price_iv or 0),
        "status": order.status,
        "created_at": serialize_datetime(order.created_at),
    }


def get_shop_settings() -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        with Session() as session:
            rows = session.query(ShopSetting).all()
            data = {row.setting_key: row.setting_value for row in rows}
        merged = dict(DEFAULT_SHOP_SETTINGS)
        merged.update(data)
        merged["allow_user_listing"] = bool(merged.get("allow_user_listing", False))
        merged["currency_name"] = str(merged.get("currency_name") or pivkeyu)
        shop_title = str(merged.get("shop_title") or DEFAULT_SHOP_SETTINGS["shop_title"])
        if shop_title == "仙舟小铺":
            shop_title = DEFAULT_SHOP_SETTINGS["shop_title"]
        merged["shop_title"] = shop_title
        merged["shop_notice"] = str(merged.get("shop_notice") or DEFAULT_SHOP_SETTINGS["shop_notice"])
        return merged

    return _load_shop_cached("settings", "settings", _load)


def set_shop_settings(patch: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(patch)
    if "allow_user_listing" in sanitized:
        sanitized["allow_user_listing"] = bool(sanitized["allow_user_listing"])
    if "currency_name" in sanitized and sanitized["currency_name"] is not None:
        sanitized["currency_name"] = str(sanitized["currency_name"]).strip() or pivkeyu
    if "shop_title" in sanitized and sanitized["shop_title"] is not None:
        sanitized["shop_title"] = str(sanitized["shop_title"]).strip() or DEFAULT_SHOP_SETTINGS["shop_title"]
    if "shop_notice" in sanitized and sanitized["shop_notice"] is not None:
        sanitized["shop_notice"] = str(sanitized["shop_notice"]).strip() or DEFAULT_SHOP_SETTINGS["shop_notice"]

    with Session() as session:
        for key, value in sanitized.items():
            row = session.query(ShopSetting).filter(ShopSetting.setting_key == key).first()
            if row is None:
                row = ShopSetting(setting_key=key, setting_value=value)
                session.add(row)
            else:
                row.setting_value = value
        session.commit()
    _bump_shop_cache("settings")
    return get_shop_settings()


def list_shop_items(*, enabled_only: bool = True, owner_tg: int | None = None) -> list[dict[str, Any]]:
    scope = f"items:{'enabled' if enabled_only else 'all'}:{owner_tg if owner_tg is not None else 'all'}"

    def _load() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(ShopItem)
            if enabled_only:
                query = query.filter(ShopItem.enabled.is_(True))
            if owner_tg is not None:
                query = query.filter(ShopItem.owner_tg == int(owner_tg))
            rows = query.order_by(ShopItem.official.desc(), ShopItem.id.desc()).all()
            return [serialize_shop_item(row) for row in rows]

    return _load_shop_cached(scope, "items", _load)


def list_shop_orders(*, limit: int = 50) -> list[dict[str, Any]]:
    normalized_limit = max(int(limit or 50), 1)
    scope = f"orders:{normalized_limit}"

    def _load() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(ShopOrder)
                .order_by(ShopOrder.id.desc())
                .limit(normalized_limit)
                .all()
            )
            return [serialize_shop_order(row) for row in rows]

    return _load_shop_cached(scope, "orders", _load)


def get_shop_item(item_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(ShopItem).filter(ShopItem.id == int(item_id)).first()
        return serialize_shop_item(row)


def create_shop_item(
    *,
    owner_tg: int | None,
    owner_display_name: str = "",
    owner_username: str = "",
    title: str,
    description: str = "",
    image_url: str = "",
    delivery_text: str = "",
    item_type: str = "digital",
    invite_credit_quantity: int = 0,
    price_iv: int,
    stock: int,
    notify_group: bool = False,
    official: bool = False,
    enabled: bool = True,
) -> dict[str, Any]:
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("商品标题不能为空")
    clean_price_iv = _normalize_shop_price(price_iv)
    clean_stock = _normalize_non_negative_int(stock, field_name="商品库存", max_value=MAX_SQL_INTEGER)
    clean_item_type = str(item_type or SHOP_ITEM_TYPE_DIGITAL).strip().lower()
    if clean_item_type not in SHOP_ITEM_TYPES:
        raise ValueError("商品类型不正确")
    clean_invite_credit_quantity = _normalize_non_negative_int(
        invite_credit_quantity,
        field_name="每份资格数量",
        max_value=MAX_SQL_INTEGER,
    )
    if clean_item_type in {LEGACY_SHOP_ITEM_TYPE_INVITE, SHOP_ITEM_TYPE_GROUP_INVITE, SHOP_ITEM_TYPE_ACCOUNT_OPEN} and clean_invite_credit_quantity <= 0:
        clean_invite_credit_quantity = 1
    if clean_item_type == SHOP_ITEM_TYPE_ACCOUNT_OPEN:
        clean_invite_credit_quantity = 1
    if clean_item_type == SHOP_ITEM_TYPE_DIGITAL:
        clean_invite_credit_quantity = 0

    with Session() as session:
        item = ShopItem(
            owner_tg=int(owner_tg) if owner_tg is not None else None,
            owner_display_name=str(owner_display_name or "").strip(),
            owner_username=str(owner_username or "").strip().lstrip("@"),
            title=clean_title,
            description=str(description or "").strip(),
            image_url=str(image_url or "").strip(),
            delivery_text=str(delivery_text or "").strip(),
            item_type=clean_item_type,
            invite_credit_quantity=clean_invite_credit_quantity,
            price_iv=clean_price_iv,
            stock=clean_stock,
            notify_group=bool(notify_group),
            official=bool(official),
            enabled=bool(enabled),
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        _bump_shop_cache("items")
        return serialize_shop_item(item)


def update_shop_item(item_id: int, **fields) -> dict[str, Any] | None:
    with Session() as session:
        item = session.query(ShopItem).filter(ShopItem.id == int(item_id)).first()
        if item is None:
            return None
        integer_field_names = {
            "price_iv": "商品价格",
            "stock": "商品库存",
            "sold_count": "已售数量",
            "invite_credit_quantity": "每份资格数量",
        }
        for key, value in fields.items():
            if not hasattr(item, key):
                continue
            if key in {"title", "description", "image_url", "delivery_text", "owner_display_name", "owner_username", "item_type"} and value is not None:
                value = str(value).strip()
                if key == "item_type":
                    value = value.lower()
                    if value not in SHOP_ITEM_TYPES:
                        continue
            if key == "price_iv" and value is not None:
                value = _normalize_shop_price(value)
            if key in {"stock", "sold_count", "invite_credit_quantity"} and value is not None:
                value = _normalize_non_negative_int(
                    value,
                    field_name=integer_field_names.get(key, key),
                    max_value=MAX_SQL_INTEGER,
                )
            if key in {"notify_group", "official", "enabled"} and value is not None:
                value = bool(value)
            if key == "owner_username" and value is not None:
                value = str(value).lstrip("@")
            setattr(item, key, value)
        if (item.item_type or SHOP_ITEM_TYPE_DIGITAL) in {
            LEGACY_SHOP_ITEM_TYPE_INVITE,
            SHOP_ITEM_TYPE_GROUP_INVITE,
            SHOP_ITEM_TYPE_ACCOUNT_OPEN,
        } and int(item.invite_credit_quantity or 0) <= 0:
            item.invite_credit_quantity = 1
        if (item.item_type or SHOP_ITEM_TYPE_DIGITAL) == SHOP_ITEM_TYPE_ACCOUNT_OPEN:
            item.invite_credit_quantity = 1
        if (item.item_type or SHOP_ITEM_TYPE_DIGITAL) == SHOP_ITEM_TYPE_DIGITAL:
            item.invite_credit_quantity = 0
        session.commit()
        session.refresh(item)
        _bump_shop_cache("items")
        return serialize_shop_item(item)


def delete_shop_item(item_id: int) -> bool:
    with Session() as session:
        item = session.query(ShopItem).filter(ShopItem.id == int(item_id)).first()
        if item is None:
            return False
        session.delete(item)
        session.commit()
        _bump_shop_cache("items")
        return True


def purchase_shop_item(*, buyer_tg: int, item_id: int, quantity: int = 1) -> dict[str, Any]:
    qty = max(_normalize_non_negative_int(quantity, field_name="购买数量", max_value=MAX_SQL_INTEGER), 1)
    with Session() as session:
        item = session.query(ShopItem).filter(ShopItem.id == int(item_id)).with_for_update().first()
        if item is None or not item.enabled:
            raise ValueError("商品不存在或已下架")
        if int(item.stock or 0) < qty:
            raise ValueError("商品库存不足")
        if item.owner_tg and int(item.owner_tg) == int(buyer_tg):
            raise ValueError("不能购买自己上架的商品")

        buyer = session.query(Emby).filter(Emby.tg == int(buyer_tg)).with_for_update().first()
        if buyer is None:
            raise ValueError("未找到你的 Emby 账户")

        unit_price = _normalize_shop_price(item.price_iv)
        total_price = unit_price * qty
        if total_price > MAX_SHOP_PRICE_IV:
            raise ValueError("订单金额过大，请降低购买数量后重试")
        buyer_balance = int(buyer.iv or 0)
        if buyer_balance < total_price:
            raise ValueError("余额不足")

        seller = None
        if item.owner_tg is not None:
            seller = session.query(Emby).filter(Emby.tg == int(item.owner_tg)).with_for_update().first()

        buyer.iv = buyer_balance - total_price
        if seller is not None and int(seller.tg) != int(buyer_tg):
            seller.iv = int(seller.iv or 0) + total_price

        item.stock = int(item.stock or 0) - qty
        item.sold_count = int(item.sold_count or 0) + qty

        order = ShopOrder(
            item_id=item.id,
            buyer_tg=int(buyer_tg),
            seller_tg=int(item.owner_tg) if item.owner_tg is not None else None,
            item_title=item.title,
            image_url=item.image_url,
            delivery_text=item.delivery_text,
            item_type=item.item_type or "digital",
            invite_credit_quantity=int(item.invite_credit_quantity or 0),
            quantity=qty,
            unit_price_iv=unit_price,
            total_price_iv=total_price,
            status="delivered",
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        session.refresh(item)
        session.refresh(buyer)
        if seller is not None:
            session.refresh(seller)
        _bump_shop_cache("items", "orders")
        return {
            "order": serialize_shop_order(order),
            "item": serialize_shop_item(item),
            "buyer_balance": int(buyer.iv or 0),
            "seller_balance": None if seller is None else int(seller.iv or 0),
        }
