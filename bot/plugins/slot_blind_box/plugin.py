from __future__ import annotations

import json
import math
import os
import random
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pyrogram import enums
from sqlalchemy import or_

from bot import LOGGER, api as api_config, bot, config, group, pivkeyu
from bot.plugins.sdk import (
    AdminBootstrapPayload,
    InitDataPayload,
    build_bottom_nav,
    verify_admin_credential,
    verify_telegram_user,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_emby import Emby, _invalidate_emby_payload, _serialize_emby_row, sql_get_emby, sql_invalidate_emby_cache
from bot.sql_helper.sql_invite import grant_slot_group_invite_credit, normalize_invite_days
from bot.web.api.miniapp import is_admin_user_id
from bot.web.presenters import get_level_meta, serialize_emby_user


PLUGIN_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PLUGIN_ROOT / "static"
PROJECT_ROOT = PLUGIN_ROOT.parents[2]
PLUGIN_MANIFEST = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
SHANGHAI_TZ = timezone(timedelta(hours=8))
MAX_WEIGHT = 1_000_000.0
MAX_STOCK = 2_147_483_647
MAX_SPIN_COST = 9_007_199_254_740_991
LEVEL_CODES = ("a", "b", "c", "d")
REWARD_TYPE_MANUAL = "manual"
REWARD_TYPE_FREE_SPIN_TICKET = "free_spin_ticket"
REWARD_TYPE_GROUP_INVITE = "group_invite_credit"
REWARD_TYPE_ACCOUNT_OPEN = "account_open_credit"
REWARD_TYPE_EMBY_CURRENCY = "emby_currency"
REWARD_TYPES = {
    REWARD_TYPE_MANUAL,
    REWARD_TYPE_FREE_SPIN_TICKET,
    REWARD_TYPE_GROUP_INVITE,
    REWARD_TYPE_ACCOUNT_OPEN,
    REWARD_TYPE_EMBY_CURRENCY,
}
LIMITED_REWARD_TYPES = (REWARD_TYPE_GROUP_INVITE, REWARD_TYPE_ACCOUNT_OPEN)
LIMITED_REWARD_MAX_RATE = 1.0
LIMITED_REWARD_DEFAULT_WEIGHTS = {
    REWARD_TYPE_GROUP_INVITE: 0.2,
    REWARD_TYPE_ACCOUNT_OPEN: 0.1,
}
LEGACY_DEFAULT_LIMITED_PRIZES = {
    "group-invite-credit": (REWARD_TYPE_GROUP_INVITE, 2.0),
    "account-open-credit": (REWARD_TYPE_ACCOUNT_OPEN, 1.0),
}
BACKPACK_ITEM_TYPES = {REWARD_TYPE_FREE_SPIN_TICKET, REWARD_TYPE_GROUP_INVITE, REWARD_TYPE_ACCOUNT_OPEN}
BACKPACK_ITEM_META = {
    REWARD_TYPE_FREE_SPIN_TICKET: {"label": "抽奖券", "icon": "🎟️"},
    REWARD_TYPE_GROUP_INVITE: {"label": "邀请资格", "icon": "📨"},
    REWARD_TYPE_ACCOUNT_OPEN: {"label": "开号资格", "icon": "🪪"},
}
STATE_LOCK = RLock()
RNG = random.SystemRandom()
STATE_PATH = PROJECT_ROOT / "data" / "plugin_state" / "slot-blind-box" / "state.json"
STATE_MEMORY_CACHE: dict[str, Any] = {"mtime": 0.0, "payload": None}
TELEGRAM_IDENTITY_CACHE_TTL = 300.0
TELEGRAM_IDENTITY_CACHE: dict[int, tuple[float, dict[str, str]]] = {}


DEFAULT_SETTINGS = {
    "enabled": True,
    "title": "幸运老虎机盲盒",
    "notice": "奖池已开放。",
    "blank_enabled": True,
    "blank_label": "轮空",
    "blank_icon": "🍀",
    "blank_weight": 50,
    "pity_enabled": True,
    "pity_after": 10,
    "daily_limit": 0,
    "spin_cost_iv": 10,
    "currency_name": pivkeyu,
    "daily_limit_by_level": {"a": 0, "b": 0, "c": 0, "d": 0},
    "daily_gift_by_level": {"a": 3, "b": 1, "c": 0, "d": 0},
    "cooldown_seconds": 0,
    "record_limit": 300,
}


DEFAULT_PRIZES = [
    {
        "id": "starter-ticket",
        "name": "体验券",
        "icon": "🎫",
        "description": "默认示例奖品，可在后台修改或删除。",
        "delivery_text": "请联系管理员兑换体验券。",
        "reward_type": REWARD_TYPE_MANUAL,
        "free_spin_quantity": 0,
        "weight": 20,
        "stock": -1,
        "enabled": True,
        "guarantee_eligible": True,
        "guarantee_after": 0,
        "broadcast_enabled": False,
        "broadcast_image_url": "",
    },
    {
        "id": "bonus-points",
        "name": "积分礼包",
        "icon": "💰",
        "description": "中奖后自动到账的 Emby 货币奖励。",
        "delivery_text": "Emby 货币已自动发放到账户。",
        "reward_type": REWARD_TYPE_EMBY_CURRENCY,
        "free_spin_quantity": 50,
        "weight": 10,
        "stock": -1,
        "enabled": True,
        "guarantee_eligible": True,
        "guarantee_after": 0,
        "broadcast_enabled": False,
        "broadcast_image_url": "",
    },
    {
        "id": "rare-box",
        "name": "稀有盲盒",
        "icon": "🎁",
        "description": "低概率奖品示例。",
        "delivery_text": "请联系管理员确认稀有盲盒发放方式。",
        "reward_type": REWARD_TYPE_MANUAL,
        "free_spin_quantity": 0,
        "weight": 3,
        "stock": 20,
        "enabled": True,
        "guarantee_eligible": True,
        "guarantee_after": 0,
        "broadcast_enabled": True,
        "broadcast_image_url": "",
    },
    {
        "id": "free-spin-ticket",
        "name": "抽奖券",
        "icon": "🎟️",
        "description": "中奖后可免费再抽一次。",
        "delivery_text": "已自动发放 1 张免费抽奖券。",
        "reward_type": REWARD_TYPE_FREE_SPIN_TICKET,
        "free_spin_quantity": 1,
        "weight": 8,
        "stock": -1,
        "enabled": True,
        "guarantee_eligible": True,
        "guarantee_after": 0,
        "broadcast_enabled": False,
        "broadcast_image_url": "",
    },
    {
        "id": "group-invite-credit",
        "name": "邀请资格",
        "icon": "📨",
        "description": "可在背包中转赠，交易请前往 Emby 商店处理的入群邀请资格。",
        "delivery_text": "已放入背包：邀请资格 1 个。",
        "reward_type": REWARD_TYPE_GROUP_INVITE,
        "free_spin_quantity": 0,
        "weight": 0.2,
        "stock": -1,
        "enabled": True,
        "guarantee_eligible": False,
        "guarantee_after": 0,
        "broadcast_enabled": True,
        "broadcast_image_url": "",
    },
    {
        "id": "account-open-credit",
        "name": "开号资格",
        "icon": "🪪",
        "description": "可在背包中转赠，交易请前往 Emby 商店处理的 Emby 开号资格。",
        "delivery_text": "已放入背包：开号资格 1 个。",
        "reward_type": REWARD_TYPE_ACCOUNT_OPEN,
        "free_spin_quantity": 0,
        "weight": 0.1,
        "stock": -1,
        "enabled": True,
        "guarantee_eligible": False,
        "guarantee_after": 0,
        "broadcast_enabled": True,
        "broadcast_image_url": "",
    },
]


class RedeemCodePayload(InitDataPayload):
    code: str


class UseBackpackItemPayload(InitDataPayload):
    item_type: str


class TransferItemPayload(InitDataPayload):
    item_type: str
    target_tg: int
    quantity: int = 1


class TransferTargetSearchPayload(InitDataPayload):
    query: str


class ListingPayload(InitDataPayload):
    item_type: str
    quantity: int = 1
    price_iv: int = 0


class ListingPurchasePayload(InitDataPayload):
    listing_id: str


class ListingCancelPayload(InitDataPayload):
    listing_id: str


class AdminUserSearchPayload(BaseModel):
    query: str = ""
    limit: int = 20


class AdminUserStatsPayload(BaseModel):
    total_spins: int = 0
    reset_spin_stats: bool = False


class AdminResetAllStatsPayload(BaseModel):
    clear_records: bool = True


class RedeemCodeAdminPayload(BaseModel):
    code: str | None = None
    title: str = ""
    max_uses: int = 1
    per_user_limit: int = 1
    enabled: bool = True
    grants: dict[str, int] | None = None


class RedeemCodeAdminPatchPayload(BaseModel):
    title: str | None = None
    max_uses: int | None = None
    per_user_limit: int | None = None
    enabled: bool | None = None
    grants: dict[str, int] | None = None


class SettingsPatchPayload(BaseModel):
    enabled: bool | None = None
    title: str | None = None
    notice: str | None = None
    blank_enabled: bool | None = None
    blank_label: str | None = None
    blank_icon: str | None = None
    blank_weight: float | None = None
    pity_enabled: bool | None = None
    pity_after: int | None = None
    daily_limit: int | None = None
    spin_cost_iv: int | None = None
    currency_name: str | None = None
    daily_limit_by_level: dict[str, int] | None = None
    daily_gift_by_level: dict[str, int] | None = None
    cooldown_seconds: int | None = None
    record_limit: int | None = None


class PrizePayload(BaseModel):
    name: str
    icon: str = "🎁"
    description: str = ""
    delivery_text: str = ""
    reward_type: str = REWARD_TYPE_MANUAL
    free_spin_quantity: int = 0
    weight: float = 10
    stock: int = -1
    enabled: bool = True
    guarantee_eligible: bool = True
    guarantee_after: int = 0
    broadcast_enabled: bool = False
    broadcast_image_url: str = ""


class PrizePatchPayload(BaseModel):
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    delivery_text: str | None = None
    reward_type: str | None = None
    free_spin_quantity: int | None = None
    weight: float | None = None
    stock: int | None = None
    enabled: bool | None = None
    guarantee_eligible: bool | None = None
    guarantee_after: int | None = None
    broadcast_enabled: bool | None = None
    broadcast_image_url: str | None = None


def _configure_state_path(context: Any | None = None) -> None:
    global STATE_PATH
    if context is not None and getattr(context, "data_dir", None):
        STATE_PATH = Path(context.data_dir) / "state.json"
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().astimezone(SHANGHAI_TZ).isoformat(timespec="seconds")


def _today_key() -> str:
    return _now().astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d")


def _clean_text(value: Any, *, default: str = "", max_length: int = 512) -> str:
    text = str(value if value is not None else default).strip()
    if not text:
        text = default
    return text[:max_length]


def _clean_bool(value: Any) -> bool:
    return bool(value)


def _clean_int(value: Any, *, default: int, minimum: int, maximum: int, field_name: str) -> int:
    if value is None or value == "":
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须是整数") from None
    if normalized < minimum:
        raise ValueError(f"{field_name}不能小于 {minimum}")
    if normalized > maximum:
        raise ValueError(f"{field_name}不能超过 {maximum}")
    return normalized


def _clean_float(value: Any, *, default: float, minimum: float, maximum: float, field_name: str) -> float:
    if value is None or value == "":
        return float(default)
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须是数字") from None
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name}必须是有效数字")
    if normalized < minimum:
        raise ValueError(f"{field_name}不能小于 {minimum:g}")
    if normalized > maximum:
        raise ValueError(f"{field_name}不能超过 {maximum:g}")
    return round(normalized, 6)


def _weight_value(value: Any) -> float:
    try:
        weight = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return weight if math.isfinite(weight) and weight > 0 else 0.0


def _clean_level_int_map(value: Any, *, default: dict[str, int], field_name: str, maximum: int = 100_000) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    normalized: dict[str, int] = {}
    for level in LEVEL_CODES:
        normalized[level] = _clean_int(
            raw.get(level, default.get(level, 0)),
            default=int(default.get(level, 0) or 0),
            minimum=0,
            maximum=maximum,
            field_name=f"{field_name}{level.upper()}",
        )
    return normalized


def _normalize_reward_type(value: Any) -> str:
    normalized = str(value or REWARD_TYPE_MANUAL).strip().lower()
    return normalized if normalized in REWARD_TYPES else REWARD_TYPE_MANUAL


def _normalize_backpack_item_type(value: Any) -> str:
    normalized = _normalize_reward_type(value)
    if normalized not in BACKPACK_ITEM_TYPES:
        raise ValueError("背包物品类型不正确")
    return normalized


def _clean_grants(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    return {
        item_type: _clean_int(
            raw.get(item_type),
            default=0,
            minimum=0,
            maximum=100_000,
            field_name=BACKPACK_ITEM_META[item_type]["label"],
        )
        for item_type in BACKPACK_ITEM_TYPES
    }


def _normalize_redeem_code(value: Any | None = None) -> str:
    raw = str(value or uuid4().hex[:10]).strip().upper()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:40] or uuid4().hex[:10].upper()


def _clean_redeem_code(raw: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    created_at = existing.get("created_at") or raw.get("created_at") or _iso_now()
    used_by = existing.get("used_by") or raw.get("used_by") or {}
    if not isinstance(used_by, dict):
        used_by = {}
    return {
        "code": _normalize_redeem_code(existing.get("code") or raw.get("code")),
        "title": _clean_text(raw.get("title", existing.get("title")), default="兑换码", max_length=80),
        "max_uses": _clean_int(
            raw.get("max_uses", existing.get("max_uses")),
            default=1,
            minimum=0,
            maximum=1_000_000,
            field_name="总使用次数",
        ),
        "per_user_limit": _clean_int(
            raw.get("per_user_limit", existing.get("per_user_limit")),
            default=1,
            minimum=1,
            maximum=10_000,
            field_name="单人使用次数",
        ),
        "enabled": _clean_bool(raw.get("enabled", existing.get("enabled", True))),
        "grants": _clean_grants(raw.get("grants", existing.get("grants"))),
        "used_count": _clean_int(
            raw.get("used_count", existing.get("used_count")),
            default=0,
            minimum=0,
            maximum=1_000_000,
            field_name="已使用次数",
        ),
        "used_by": {str(key): int(value or 0) for key, value in used_by.items()},
        "created_at": created_at,
        "updated_at": _iso_now() if existing else raw.get("updated_at") or created_at,
    }


def _clean_listing(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        item_type = _normalize_backpack_item_type(raw.get("item_type"))
    except ValueError:
        return None
    quantity = _clean_int(raw.get("quantity"), default=1, minimum=1, maximum=1_000_000, field_name="上架数量")
    price_iv = _clean_int(raw.get("price_iv"), default=0, minimum=0, maximum=MAX_SPIN_COST, field_name="上架价格")
    seller_tg = raw.get("seller_tg")
    try:
        seller_tg = int(seller_tg)
    except (TypeError, ValueError):
        return None
    return {
        "id": _clean_prize_id(raw.get("id")),
        "seller_tg": seller_tg,
        "seller_display": _clean_text(raw.get("seller_display"), default=str(seller_tg), max_length=80),
        "item_type": item_type,
        "quantity": quantity,
        "price_iv": price_iv,
        "status": str(raw.get("status") or "active").strip().lower(),
        "created_at": raw.get("created_at") or _iso_now(),
        "updated_at": raw.get("updated_at") or raw.get("created_at") or _iso_now(),
    }


def _clean_prize_id(value: Any | None = None) -> str:
    raw = str(value or uuid4().hex[:12]).strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-_")
    return cleaned[:48] or uuid4().hex[:12]


def _clean_prize(raw: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    created_at = existing.get("created_at") or raw.get("created_at") or _iso_now()
    reward_type = _normalize_reward_type(raw.get("reward_type", existing.get("reward_type")))
    quantity_max = MAX_SPIN_COST if reward_type == REWARD_TYPE_EMBY_CURRENCY else 1000
    quantity_default = 1 if reward_type in {REWARD_TYPE_FREE_SPIN_TICKET, REWARD_TYPE_GROUP_INVITE, REWARD_TYPE_ACCOUNT_OPEN} else 0
    guarantee_default = reward_type not in LIMITED_REWARD_TYPES
    return {
        "id": _clean_prize_id(existing.get("id") or raw.get("id")),
        "name": _clean_text(raw.get("name", existing.get("name")), default="未命名奖品", max_length=80),
        "icon": _clean_text(raw.get("icon", existing.get("icon")), default="🎁", max_length=16),
        "description": _clean_text(raw.get("description", existing.get("description")), max_length=500),
        "delivery_text": _clean_text(raw.get("delivery_text", existing.get("delivery_text")), max_length=1000),
        "reward_type": reward_type,
        "free_spin_quantity": _clean_int(
            raw.get("free_spin_quantity", existing.get("free_spin_quantity")),
            default=quantity_default,
            minimum=0,
            maximum=quantity_max,
            field_name="奖励数量",
        ),
        "weight": _clean_float(
            raw.get("weight", existing.get("weight")),
            default=10.0,
            minimum=0.0,
            maximum=MAX_WEIGHT,
            field_name="中奖率权重",
        ),
        "stock": _clean_int(
            raw.get("stock", existing.get("stock")),
            default=-1,
            minimum=-1,
            maximum=MAX_STOCK,
            field_name="库存",
        ),
        "enabled": _clean_bool(raw.get("enabled", existing.get("enabled", True))),
        "guarantee_eligible": False
        if reward_type in LIMITED_REWARD_TYPES
        else _clean_bool(raw.get("guarantee_eligible", existing.get("guarantee_eligible", guarantee_default))),
        "guarantee_after": 0
        if reward_type in LIMITED_REWARD_TYPES
        else _clean_int(
            raw.get("guarantee_after", existing.get("guarantee_after")),
            default=0,
            minimum=0,
            maximum=10_000,
            field_name="奖品单独保底次数",
        ),
        "broadcast_enabled": _clean_bool(raw.get("broadcast_enabled", existing.get("broadcast_enabled", False))),
        "broadcast_image_url": _clean_text(
            raw.get("broadcast_image_url", existing.get("broadcast_image_url")), max_length=1000
        ),
        "created_at": created_at,
        "updated_at": _iso_now() if existing else raw.get("updated_at") or created_at,
    }


def _migrate_legacy_limited_prize(prize: dict[str, Any], raw_prize: dict[str, Any]) -> dict[str, Any]:
    legacy = LEGACY_DEFAULT_LIMITED_PRIZES.get(str(prize.get("id") or ""))
    reward_type = _normalize_reward_type(prize.get("reward_type"))
    if not legacy or legacy[0] != reward_type:
        return prize
    try:
        raw_weight = float(raw_prize.get("weight"))
    except (TypeError, ValueError):
        return prize
    if not math.isfinite(raw_weight) or round(raw_weight, 6) != legacy[1]:
        return prize
    prize["weight"] = LIMITED_REWARD_DEFAULT_WEIGHTS[reward_type]
    prize["updated_at"] = _iso_now()
    return prize


def _fresh_state() -> dict[str, Any]:
    timestamp = _iso_now()
    prizes = []
    for prize in DEFAULT_PRIZES:
        clean = _clean_prize({**prize, "created_at": timestamp, "updated_at": timestamp})
        prizes.append(clean)
    return {
        "schema_version": 3,
        "settings": deepcopy(DEFAULT_SETTINGS),
        "prizes": prizes,
        "users": {},
        "records": [],
        "redeem_codes": [],
        "market_listings": [],
        "telegram_identities": {},
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _normalize_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    settings = deepcopy(DEFAULT_SETTINGS)
    settings.update(raw)
    settings["enabled"] = bool(settings.get("enabled", True))
    settings["title"] = _clean_text(settings.get("title"), default=DEFAULT_SETTINGS["title"], max_length=80)
    settings["notice"] = _clean_text(settings.get("notice"), max_length=240)
    settings["blank_enabled"] = bool(settings.get("blank_enabled", True))
    settings["blank_label"] = _clean_text(settings.get("blank_label"), default="轮空", max_length=24)
    settings["blank_icon"] = _clean_text(settings.get("blank_icon"), default="🍀", max_length=16)
    settings["blank_weight"] = _clean_float(
        settings.get("blank_weight"), default=50.0, minimum=0.0, maximum=MAX_WEIGHT, field_name="轮空权重"
    )
    settings["pity_enabled"] = bool(settings.get("pity_enabled", True))
    settings["pity_after"] = _clean_int(
        settings.get("pity_after"), default=10, minimum=1, maximum=10_000, field_name="保底次数"
    )
    settings["daily_limit"] = _clean_int(
        settings.get("daily_limit"), default=0, minimum=0, maximum=100_000, field_name="每日次数"
    )
    settings["spin_cost_iv"] = _clean_int(
        settings.get("spin_cost_iv"), default=10, minimum=0, maximum=MAX_SPIN_COST, field_name="单抽价格"
    )
    settings["currency_name"] = _clean_text(settings.get("currency_name"), default=pivkeyu, max_length=32)
    settings["daily_limit_by_level"] = _clean_level_int_map(
        settings.get("daily_limit_by_level"),
        default=DEFAULT_SETTINGS["daily_limit_by_level"],
        field_name="等级每日上限",
    )
    settings["daily_gift_by_level"] = _clean_level_int_map(
        settings.get("daily_gift_by_level"),
        default=DEFAULT_SETTINGS["daily_gift_by_level"],
        field_name="等级每日赠送次数",
    )
    settings["cooldown_seconds"] = _clean_int(
        settings.get("cooldown_seconds"), default=0, minimum=0, maximum=86_400, field_name="冷却秒数"
    )
    settings["record_limit"] = _clean_int(
        settings.get("record_limit"), default=300, minimum=50, maximum=5000, field_name="记录保留数"
    )
    return settings


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(state or {})
    raw_schema_version = int(normalized.get("schema_version") or 1)
    normalized["schema_version"] = 3
    normalized["settings"] = _normalize_settings(normalized.get("settings"))

    prizes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_prize in normalized.get("prizes") or []:
        if not isinstance(raw_prize, dict):
            continue
        prize = _clean_prize(raw_prize)
        prize = _migrate_legacy_limited_prize(prize, raw_prize)
        original_id = prize["id"]
        while prize["id"] in seen_ids:
            prize["id"] = _clean_prize_id(f"{original_id}-{uuid4().hex[:4]}")
        seen_ids.add(prize["id"])
        prizes.append(prize)
    if raw_schema_version < 2 and "free-spin-ticket" not in seen_ids:
        prize = _clean_prize({**DEFAULT_PRIZES[3], "created_at": _iso_now(), "updated_at": _iso_now()})
        prizes.append(prize)
        seen_ids.add(prize["id"])
    if raw_schema_version < 3:
        for default_prize in DEFAULT_PRIZES[4:]:
            if default_prize["id"] in seen_ids:
                continue
            prize = _clean_prize({**default_prize, "created_at": _iso_now(), "updated_at": _iso_now()})
            prizes.append(prize)
            seen_ids.add(prize["id"])
    normalized["prizes"] = prizes
    normalized["users"] = normalized.get("users") if isinstance(normalized.get("users"), dict) else {}
    normalized["records"] = normalized.get("records") if isinstance(normalized.get("records"), list) else []
    redeem_codes = []
    seen_codes: set[str] = set()
    for raw_code in normalized.get("redeem_codes") or []:
        if not isinstance(raw_code, dict):
            continue
        code = _clean_redeem_code(raw_code)
        if code["code"] in seen_codes:
            continue
        seen_codes.add(code["code"])
        redeem_codes.append(code)
    normalized["redeem_codes"] = redeem_codes
    listings = []
    seen_listing_ids: set[str] = set()
    for raw_listing in normalized.get("market_listings") or []:
        if not isinstance(raw_listing, dict):
            continue
        listing = _clean_listing(raw_listing)
        if not listing or listing["id"] in seen_listing_ids:
            continue
        seen_listing_ids.add(listing["id"])
        listings.append(listing)
    normalized["market_listings"] = listings
    identities: dict[str, dict[str, str]] = {}
    raw_identities = normalized.get("telegram_identities") if isinstance(normalized.get("telegram_identities"), dict) else {}
    for raw_tg, raw_identity in raw_identities.items():
        if not isinstance(raw_identity, dict):
            continue
        try:
            tg = int(raw_tg)
        except (TypeError, ValueError):
            continue
        identity = _clean_stored_telegram_identity(raw_identity)
        if not identity:
            continue
        identities[str(tg)] = identity
        _store_telegram_identity(tg, identity)
    normalized["telegram_identities"] = identities
    normalized.setdefault("created_at", _iso_now())
    normalized["updated_at"] = normalized.get("updated_at") or normalized["created_at"]
    return normalized


def _load_state_unlocked() -> dict[str, Any]:
    _configure_state_path()
    if not STATE_PATH.exists():
        state = _fresh_state()
        _save_state_unlocked(state)
        return state
    mtime = STATE_PATH.stat().st_mtime
    cached = STATE_MEMORY_CACHE
    if cached["payload"] is not None and cached["mtime"] == mtime:
        return deepcopy(cached["payload"])
    with STATE_PATH.open("r", encoding="utf-8") as state_file:
        state = json.load(state_file)
    state = _normalize_state(state)
    cached["mtime"] = mtime
    cached["payload"] = deepcopy(state)
    return state


def _save_state_unlocked(state: dict[str, Any]) -> None:
    _configure_state_path()
    state["updated_at"] = _iso_now()
    temp_path = STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, STATE_PATH)
    STATE_MEMORY_CACHE["mtime"] = STATE_PATH.stat().st_mtime
    STATE_MEMORY_CACHE["payload"] = deepcopy(state)


def _verify_user_from_init_data(init_data: str) -> dict[str, Any]:
    return verify_telegram_user(init_data, on_verified=_remember_telegram_identity)


def _telegram_user_label(user: dict[str, Any]) -> str:
    display_name = " ".join(
        part for part in [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()] if part
    ).strip()
    if display_name:
        return display_name[:80]
    username = str(user.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"[:80]
    return str(user.get("id") or "未知用户")[:80]


def _telegram_identity_payload(user: Any) -> dict[str, str]:
    if isinstance(user, dict):
        first_name = str(user.get("first_name", "") or "").strip()
        last_name = str(user.get("last_name", "") or "").strip()
        username = str(user.get("username", "") or "").strip().lstrip("@")
    else:
        first_name = str(getattr(user, "first_name", "") or "").strip()
        last_name = str(getattr(user, "last_name", "") or "").strip()
        username = str(getattr(user, "username", "") or "").strip().lstrip("@")
    display_name = " ".join(part for part in [first_name, last_name] if part).strip()
    payload: dict[str, str] = {}
    if display_name:
        payload["display_name"] = display_name
    if username:
        payload["username"] = username
    return payload


def _telegram_display_label(tg: int, identity: dict[str, str] | None = None) -> str:
    identity = identity or {}
    display_name = str(identity.get("display_name") or "").strip()
    username = str(identity.get("username") or "").strip().lstrip("@")
    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return f"TG {int(tg)}"


def _cached_telegram_identity(tg: int) -> dict[str, str] | None:
    cached = TELEGRAM_IDENTITY_CACHE.get(int(tg))
    if not cached:
        return None
    cached_at, payload = cached
    if time.monotonic() - cached_at > TELEGRAM_IDENTITY_CACHE_TTL:
        TELEGRAM_IDENTITY_CACHE.pop(int(tg), None)
        return None
    return dict(payload)


def _store_telegram_identity(tg: int, identity: dict[str, str]) -> None:
    TELEGRAM_IDENTITY_CACHE[int(tg)] = (time.monotonic(), dict(identity))


def _clean_stored_telegram_identity(raw: dict[str, Any]) -> dict[str, str]:
    display_name = _clean_text(raw.get("display_name"), max_length=80)
    username = _clean_text(raw.get("username"), max_length=64).lstrip("@")
    updated_at = _clean_text(raw.get("updated_at"), max_length=40)
    payload: dict[str, str] = {}
    if display_name:
        payload["display_name"] = display_name
    if username:
        payload["username"] = username
    if updated_at:
        payload["updated_at"] = updated_at
    return payload


def _remember_telegram_identity(user: dict[str, Any]) -> None:
    try:
        tg = int(user.get("id"))
    except (TypeError, ValueError):
        return
    identity = _telegram_identity_payload(user)
    _store_telegram_identity(tg, identity)
    if not identity:
        return
    stored = _clean_stored_telegram_identity({**identity, "updated_at": _iso_now()})
    with STATE_LOCK:
        state = _load_state_unlocked()
        identities = state.setdefault("telegram_identities", {})
        current = identities.get(str(tg)) if isinstance(identities, dict) else None
        current_display = "" if not isinstance(current, dict) else str(current.get("display_name") or "")
        current_username = "" if not isinstance(current, dict) else str(current.get("username") or "")
        if current_display == stored.get("display_name", "") and current_username == stored.get("username", ""):
            return
        identities[str(tg)] = stored
        _save_state_unlocked(state)


def _stored_transfer_target_tgs(query: str, *, limit: int = 120) -> list[int]:
    matches: list[int] = []
    with STATE_LOCK:
        state = _load_state_unlocked()
        identities = state.get("telegram_identities") if isinstance(state.get("telegram_identities"), dict) else {}
        for raw_tg, identity in identities.items():
            try:
                tg = int(raw_tg)
            except (TypeError, ValueError):
                continue
            if _identity_matches_query(tg, identity, query):
                _store_telegram_identity(tg, identity)
                matches.append(tg)
            if len(matches) >= limit:
                break
    return matches


def _identity_matches_query(tg: int, identity: dict[str, str] | None, query: str) -> bool:
    normalized = str(query or "").strip().lower().lstrip("@")
    if not normalized:
        return False
    identity = identity or {}
    fields = [
        str(tg),
        str(identity.get("display_name") or ""),
        str(identity.get("username") or ""),
    ]
    return any(normalized in field.lower().lstrip("@") for field in fields if field)


def _cached_transfer_target_tgs(query: str, *, limit: int = 80) -> list[int]:
    matches: list[int] = []
    for tg, cached in list(TELEGRAM_IDENTITY_CACHE.items()):
        cached_at, identity = cached
        if time.monotonic() - cached_at > TELEGRAM_IDENTITY_CACHE_TTL:
            TELEGRAM_IDENTITY_CACHE.pop(int(tg), None)
            continue
        if _identity_matches_query(int(tg), identity, query):
            matches.append(int(tg))
        if len(matches) >= limit:
            break
    return matches


async def _resolve_transfer_target_username(query: str) -> tuple[int | None, dict[str, str]]:
    lookup = str(query or "").strip().lstrip("@")
    if len(lookup) < 5 or lookup.lstrip("-").isdigit():
        return None, {}
    if not all(ch.isalnum() or ch == "_" for ch in lookup):
        return None, {}
    try:
        user = await bot.get_users(lookup)
    except Exception:
        return None, {}
    tg = int(user.id)
    identity = _telegram_identity_payload(user)
    _store_telegram_identity(tg, identity)
    return tg, identity


async def _fetch_transfer_target_identities(tgs: list[int]) -> dict[int, dict[str, str]]:
    identities: dict[int, dict[str, str]] = {}
    missing: list[int] = []
    for tg in {int(value) for value in tgs if value is not None}:
        cached = _cached_telegram_identity(tg)
        if cached is None:
            missing.append(tg)
        else:
            identities[tg] = cached
    for start in range(0, len(missing), 100):
        chunk = missing[start:start + 100]
        try:
            response = await bot.get_users(chunk if len(chunk) > 1 else chunk[0])
            users = response if isinstance(response, list) else [response]
            found: set[int] = set()
            for user in users:
                tg = int(user.id)
                identity = _telegram_identity_payload(user)
                _store_telegram_identity(tg, identity)
                identities[tg] = identity
                found.add(tg)
            for tg in chunk:
                if tg not in found:
                    _store_telegram_identity(tg, {})
                    identities[tg] = {}
        except Exception as exc:
            LOGGER.warning(f"slot box transfer target lookup failed: {exc}")
            for tg in chunk:
                identities[tg] = _cached_telegram_identity(tg) or {}
    return identities


async def _search_transfer_targets(query: str, current_tg: int, *, limit: int = 8) -> list[dict[str, Any]]:
    normalized = str(query or "").strip()
    if len(normalized) < 2 and not normalized.lstrip("@-").isdigit():
        return []
    normalized_text = normalized.lstrip("@").lower()
    resolved_tg: int | None = None
    resolved_identity: dict[str, str] = {}
    if normalized.startswith("@"):
        resolved_tg, resolved_identity = await _resolve_transfer_target_username(normalized)
    candidates: dict[int, Emby] = {}
    identity_tgs: list[int] = []
    with Session() as session:
        filters = [Emby.name.ilike(f"%{normalized}%"), Emby.embyid.ilike(f"%{normalized}%")]
        if normalized.lstrip("-").isdigit():
            filters.append(Emby.tg == int(normalized))
        if resolved_tg is not None:
            filters.append(Emby.tg == int(resolved_tg))
        for row in session.query(Emby).filter(or_(*filters)).order_by(Emby.tg.desc()).limit(40).all():
            candidates[int(row.tg)] = row
        stored_tgs = [tg for tg in _stored_transfer_target_tgs(normalized) if tg not in candidates]
        cached_tgs = [
            tg for tg in _cached_transfer_target_tgs(normalized)
            if tg not in candidates and tg not in stored_tgs
        ]
        identity_tgs = (stored_tgs + cached_tgs)[:120]
        if identity_tgs:
            for row in session.query(Emby).filter(Emby.tg.in_(identity_tgs)).limit(120).all():
                candidates.setdefault(int(row.tg), row)
    extra_tgs: list[int] = []
    if normalized.lstrip("-").isdigit():
        direct_tg = int(normalized)
        if direct_tg > 0:
            extra_tgs.append(direct_tg)
    if resolved_tg is not None:
        extra_tgs.append(int(resolved_tg))
    extra_tgs.extend(identity_tgs)

    identities = await _fetch_transfer_target_identities(list(candidates) + extra_tgs)
    if resolved_tg is not None and resolved_identity:
        identities[int(resolved_tg)] = resolved_identity
    rows: list[dict[str, Any]] = []
    for tg, row in candidates.items():
        identity = identities.get(tg) or {}
        emby_name = str(getattr(row, "name", "") or "")
        embyid = str(getattr(row, "embyid", "") or "")
        matched = (
            normalized_text in str(tg)
            or normalized_text in emby_name.lower()
            or normalized_text in embyid.lower()
            or _identity_matches_query(tg, identity, normalized)
        )
        if not matched:
            continue
        rows.append(
            {
                "tg": tg,
                "display_label": _telegram_display_label(tg, identity),
                "display_name": identity.get("display_name") or "",
                "username": identity.get("username") or "",
                "emby_name": emby_name,
                "embyid": embyid,
                "is_self": tg == int(current_tg),
            }
        )
    seen_tgs = {int(item["tg"]) for item in rows}
    for tg in extra_tgs:
        tg = int(tg)
        if tg in seen_tgs:
            continue
        identity = identities.get(tg) or {}
        if not _identity_matches_query(tg, identity, normalized) and normalized_text not in str(tg):
            continue
        rows.append(
            {
                "tg": tg,
                "display_label": _telegram_display_label(tg, identity),
                "display_name": identity.get("display_name") or "",
                "username": identity.get("username") or "",
                "emby_name": "",
                "embyid": "",
                "is_self": tg == int(current_tg),
            }
        )
        seen_tgs.add(tg)
    rows.sort(key=lambda item: (item["is_self"], item["display_label"].lower(), item["tg"]))
    return rows[:limit]


def _main_group_chat_id() -> int | None:
    for value in group:
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


_MD_ESCAPE_PATTERN = re.compile(r"([_*\[`])")
# 群播报卡片分隔线(与斗罗/斗破/修仙播报同款样式)
_MD_BROADCAST_DIVIDER = "━" * 18


def _md_escape(value: Any) -> str:
    """转义 legacy Markdown 特殊字符,防止动态内容破坏排版。"""
    return _MD_ESCAPE_PATTERN.sub(r"\\\1", str(value or ""))


def _format_broadcast_card(title: str, *, emoji: str, lines: list[str], footer: str | None = None) -> str:
    """带分隔线边框的群播报卡片:图标标题 + 分隔线 + 正文 + 分隔线。"""
    rows = [f"{emoji} **{_md_escape(title)}** {emoji}", _MD_BROADCAST_DIVIDER]
    rows.extend(str(line).strip() for line in lines if str(line or "").strip())
    if footer:
        rows.extend([_MD_BROADCAST_DIVIDER, str(footer).strip()])
    else:
        rows.append(_MD_BROADCAST_DIVIDER)
    return "\n".join(rows)


def _broadcast_text(*, user_label: str, prize: dict[str, Any], probabilities: dict[str, Any], pity_triggered: bool) -> str:
    rate = (probabilities.get("prize_rates") or {}).get(prize.get("id"), 0)
    stock = int(prize.get("stock") or 0)
    stock_text = "不限" if stock < 0 else str(stock)
    pity_text = "，这次还是保底触发的，算、算你坚持得不错啦" if pity_triggered else ""
    return _format_broadcast_card(
        "盲盒大奖播报",
        emoji="🎰",
        lines=[
            f"🎉 **{_md_escape(user_label)}** 刚刚抽中了 {prize.get('icon') or '🎁'} **{_md_escape(prize.get('name'))}**！",
            f"📊 当前概率约 `{rate}%`{pity_text}。",
            f"📦 剩余库存：`{_md_escape(stock_text)}`",
        ],
        footer="🎀 哼，本女仆才不是特意给你们报喜呢！既然中了大奖，就勉强恭喜一下吧。下次可别得意忘形哦。",
    )


async def _send_group_broadcast(payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    chat_id = _main_group_chat_id()
    if not chat_id:
        return
    image_url = str(payload.get("image_url") or "").strip()
    text = str(payload.get("text") or "").strip()
    if not text:
        return
    try:
        if image_url:
            try:
                await bot.send_photo(chat_id=chat_id, photo=image_url, caption=text, parse_mode=enums.ParseMode.MARKDOWN)
                return
            except Exception as exc:
                LOGGER.warning(f"slot blind box broadcast image failed chat={chat_id}: {exc}")
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as exc:
        LOGGER.warning(f"slot blind box broadcast failed chat={chat_id}: {exc}")


def _telegram_member_is_active(member: Any) -> bool:
    status = str(getattr(getattr(member, "status", None), "value", getattr(member, "status", "")) or "").lower()
    if status in {"creator", "owner", "administrator", "member"}:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", True))
    return False


async def _ensure_account_open_receiver_in_group(
    target_tg: int,
    item_type: str,
    *,
    missing_group_detail: str = "主群未配置，无法接收开号资格",
    inactive_detail: str = "接收方不在主群内，不能接收开号资格",
) -> None:
    if _normalize_backpack_item_type(item_type) != REWARD_TYPE_ACCOUNT_OPEN:
        return
    chat_id = _main_group_chat_id()
    if not chat_id:
        raise HTTPException(status_code=400, detail=missing_group_detail)
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=int(target_tg))
    except Exception as exc:
        LOGGER.warning(f"slot box account open receiver group check failed chat={chat_id} tg={target_tg}: {exc}")
        raise HTTPException(status_code=400, detail=inactive_detail) from exc
    if not _telegram_member_is_active(member):
        raise HTTPException(status_code=400, detail=inactive_detail)


async def _account_open_receiver_in_group(target_tg: int) -> bool:
    try:
        await _ensure_account_open_receiver_in_group(target_tg, REWARD_TYPE_ACCOUNT_OPEN)
        return True
    except HTTPException:
        return False


def _available_prizes(
    state: dict[str, Any],
    *,
    guarantee_only: bool = False,
    account_open_receiver_ok: bool = True,
) -> list[dict[str, Any]]:
    prizes = []
    for prize in state.get("prizes") or []:
        if not prize.get("enabled") or _weight_value(prize.get("weight")) <= 0:
            continue
        if int(prize.get("stock") or 0) == 0:
            continue
        if not account_open_receiver_ok and _normalize_reward_type(prize.get("reward_type")) == REWARD_TYPE_ACCOUNT_OPEN:
            continue
        if guarantee_only and not prize.get("guarantee_eligible"):
            continue
        prizes.append(prize)
    return prizes


def _pick_weighted(entries: list[tuple[str, dict[str, Any] | None, float]]) -> tuple[str, dict[str, Any] | None]:
    total = sum(_weight_value(weight) for _, _, weight in entries)
    if total <= 0:
        raise ValueError("抽奖池为空")
    ticket = RNG.random() * total
    cursor = 0.0
    for kind, prize, weight in entries:
        cursor += _weight_value(weight)
        if ticket <= cursor:
            return kind, prize
    kind, prize, _ = entries[-1]
    return kind, prize


def _prize_guarantee_after(prize: dict[str, Any], settings: dict[str, Any]) -> int:
    value = int(prize.get("guarantee_after") or 0)
    if value > 0:
        return value
    return int(settings.get("pity_after") or 0)


def _guarantee_ready_prizes(
    prizes: list[dict[str, Any]],
    settings: dict[str, Any],
    user_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    miss_streak = _global_miss_streak(user_stats)
    ready = []
    for prize in prizes:
        threshold = _prize_guarantee_after(prize, settings)
        if threshold > 0 and miss_streak + 1 >= threshold:
            ready.append(prize)
    return ready


def _probability_summary(state: dict[str, Any], *, account_open_receiver_ok: bool = True) -> dict[str, Any]:
    settings = state.get("settings") or {}
    prizes = _available_prizes(state, account_open_receiver_ok=account_open_receiver_ok)
    blank_weight = _weight_value(settings.get("blank_weight")) if settings.get("blank_enabled") else 0.0
    total_weight = sum(_weight_value(prize.get("weight")) for prize in prizes) + blank_weight
    prize_rates: dict[str, float] = {}
    reward_type_rates = {reward_type: 0.0 for reward_type in REWARD_TYPES}
    for prize in state.get("prizes") or []:
        active = prize in prizes
        rate = (_weight_value(prize.get("weight")) / total_weight * 100) if active and total_weight else 0
        prize_rates[prize["id"]] = round(rate, 4)
        reward_type = _normalize_reward_type(prize.get("reward_type"))
        reward_type_rates[reward_type] = reward_type_rates.get(reward_type, 0.0) + rate
    blank_rate = (blank_weight / total_weight * 100) if total_weight else 0
    return {
        "total_weight": total_weight,
        "blank_rate": round(blank_rate, 4),
        "prize_rates": prize_rates,
        "reward_type_rates": {key: round(value, 4) for key, value in reward_type_rates.items()},
    }


def _reward_display_payload(prize: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, str | int]:
    reward_type = _normalize_reward_type(prize.get("reward_type"))
    quantity = int(prize.get("free_spin_quantity") or 0)
    currency_name = (settings or {}).get("currency_name") or pivkeyu
    if reward_type == REWARD_TYPE_FREE_SPIN_TICKET:
        return {"label": f"抽奖券 x{max(quantity, 1)}", "icon": "🎟️", "quantity": max(quantity, 1)}
    if reward_type == REWARD_TYPE_GROUP_INVITE:
        return {"label": f"邀请资格 x{max(quantity, 1)}", "icon": "📨", "quantity": max(quantity, 1)}
    if reward_type == REWARD_TYPE_ACCOUNT_OPEN:
        return {"label": f"开号资格 x{max(quantity, 1)}", "icon": "🪪", "quantity": max(quantity, 1)}
    if reward_type == REWARD_TYPE_EMBY_CURRENCY and quantity > 0:
        return {"label": f"{currency_name} x{quantity}", "icon": "💰", "quantity": quantity}
    return {"label": "普通奖品", "icon": str(prize.get("icon") or "🎁"), "quantity": 0}


def _public_prize(prize: dict[str, Any], probabilities: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(prize)
    reward_display = _reward_display_payload(prize, settings)
    payload["computed_rate"] = (probabilities.get("prize_rates") or {}).get(prize.get("id"), 0)
    payload["reward_label"] = reward_display["label"]
    payload["reward_icon"] = reward_display["icon"]
    return payload


def _global_stats(state: dict[str, Any]) -> dict[str, int]:
    user_rows = [row for row in (state.get("users") or {}).values() if isinstance(row, dict)]
    spin_count = sum(int(row.get("total_spins") or 0) for row in user_rows)
    win_count = sum(int(row.get("win_count") or 0) for row in user_rows)
    blank_count = sum(int(row.get("blank_count") or 0) for row in user_rows)
    if spin_count <= 0:
        records = state.get("records") or []
        spin_count = len(records)
        win_count = sum(1 for record in records if record.get("outcome") == "win")
        blank_count = max(spin_count - win_count, 0)
    return {
        "prize_count": len(state.get("prizes") or []),
        "active_prize_count": len(_available_prizes(state)),
        "spin_count": spin_count,
        "win_count": win_count,
        "blank_count": blank_count,
        "user_count": len(state.get("users") or {}),
    }


def _get_user_stats(state: dict[str, Any], user_id: int) -> dict[str, Any]:
    users = state.setdefault("users", {})
    key = str(int(user_id))
    user_stats = users.setdefault(
        key,
        {
            "total_spins": 0,
            "win_count": 0,
            "blank_count": 0,
            "miss_streak": 0,
            "last_spin_at": 0,
            "free_spin_tickets": 0,
            "daily_free_used": 0,
            "daily_key": _today_key(),
            "daily_count": 0,
        },
    )
    if user_stats.get("daily_key") != _today_key():
        user_stats["daily_key"] = _today_key()
        user_stats["daily_count"] = 0
        user_stats["daily_free_used"] = 0
    user_stats.setdefault("total_spins", 0)
    user_stats.setdefault("win_count", 0)
    user_stats.setdefault("blank_count", 0)
    user_stats.setdefault("miss_streak", 0)
    _prize_pity_map(user_stats)
    user_stats.setdefault("last_spin_at", 0)
    user_stats.setdefault("free_spin_tickets", 0)
    user_stats.setdefault("daily_free_used", 0)
    backpack = user_stats.setdefault("backpack", {})
    if not isinstance(backpack, dict):
        backpack = {}
        user_stats["backpack"] = backpack
    for item_type in BACKPACK_ITEM_TYPES:
        backpack[item_type] = max(int(backpack.get(item_type) or 0), 0)
    backpack[REWARD_TYPE_FREE_SPIN_TICKET] = max(
        int(backpack.get(REWARD_TYPE_FREE_SPIN_TICKET) or 0),
        int(user_stats.get("free_spin_tickets") or 0),
    )
    user_stats["free_spin_tickets"] = int(backpack.get(REWARD_TYPE_FREE_SPIN_TICKET) or 0)
    return user_stats


def _prize_pity_map(user_stats: dict[str, Any]) -> dict[str, int]:
    raw = user_stats.get("prize_miss_streaks")
    if not isinstance(raw, dict):
        raw = {}
    cleaned: dict[str, int] = {}
    for raw_prize_id, raw_count in raw.items():
        prize_id = str(raw_prize_id or "").strip()
        if not prize_id:
            continue
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            count = 0
        cleaned[prize_id[:48]] = max(min(count, 1_000_000), 0)
    user_stats["prize_miss_streaks"] = cleaned
    return cleaned


def _global_miss_streak(user_stats: dict[str, Any]) -> int:
    try:
        return max(int(user_stats.get("miss_streak") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _backpack(user_stats: dict[str, Any]) -> dict[str, int]:
    backpack = user_stats.setdefault("backpack", {})
    if not isinstance(backpack, dict):
        backpack = {}
        user_stats["backpack"] = backpack
    for item_type in BACKPACK_ITEM_TYPES:
        backpack[item_type] = max(int(backpack.get(item_type) or 0), 0)
    user_stats["free_spin_tickets"] = int(backpack.get(REWARD_TYPE_FREE_SPIN_TICKET) or 0)
    return backpack


def _backpack_summary(user_stats: dict[str, Any]) -> list[dict[str, Any]]:
    backpack = _backpack(user_stats)
    return [
        {
            "type": item_type,
            "label": BACKPACK_ITEM_META[item_type]["label"],
            "icon": BACKPACK_ITEM_META[item_type]["icon"],
            "quantity": int(backpack.get(item_type) or 0),
        }
        for item_type in BACKPACK_ITEM_TYPES
    ]


def _add_backpack_item(user_stats: dict[str, Any], item_type: str, quantity: int) -> dict[str, Any] | None:
    normalized_type = _normalize_backpack_item_type(item_type)
    qty = max(int(quantity or 0), 0)
    if qty <= 0:
        return None
    backpack = _backpack(user_stats)
    backpack[normalized_type] = int(backpack.get(normalized_type) or 0) + qty
    if normalized_type == REWARD_TYPE_FREE_SPIN_TICKET:
        user_stats["free_spin_tickets"] = int(backpack[normalized_type])
    return {
        "type": normalized_type,
        "label": BACKPACK_ITEM_META[normalized_type]["label"],
        "quantity": qty,
        "quantity_after": int(backpack.get(normalized_type) or 0),
    }


def _remove_backpack_item(user_stats: dict[str, Any], item_type: str, quantity: int) -> dict[str, Any]:
    normalized_type = _normalize_backpack_item_type(item_type)
    qty = max(int(quantity or 0), 1)
    backpack = _backpack(user_stats)
    current = int(backpack.get(normalized_type) or 0)
    if current < qty:
        raise ValueError(f"{BACKPACK_ITEM_META[normalized_type]['label']}数量不足")
    backpack[normalized_type] = current - qty
    if normalized_type == REWARD_TYPE_FREE_SPIN_TICKET:
        user_stats["free_spin_tickets"] = int(backpack[normalized_type])
    return {
        "type": normalized_type,
        "label": BACKPACK_ITEM_META[normalized_type]["label"],
        "quantity": qty,
        "quantity_after": int(backpack.get(normalized_type) or 0),
    }


def _account_level(account: Emby | None) -> str:
    level = str(getattr(account, "lv", "") or "d").strip().lower()
    return level if level in LEVEL_CODES else "d"


def _effective_daily_limit(settings: dict[str, Any], level: str) -> int:
    level_limit = int((settings.get("daily_limit_by_level") or {}).get(level, 0) or 0)
    return level_limit if level_limit > 0 else int(settings.get("daily_limit") or 0)


def _daily_gift_total(settings: dict[str, Any], level: str) -> int:
    return int((settings.get("daily_gift_by_level") or {}).get(level, 0) or 0)


def _consume_spin_payment(user_stats: dict[str, Any], settings: dict[str, Any], account: Emby) -> dict[str, Any]:
    level = _account_level(account)
    gift_total = _daily_gift_total(settings, level)
    daily_free_used = int(user_stats.get("daily_free_used") or 0)
    if daily_free_used < gift_total:
        user_stats["daily_free_used"] = daily_free_used + 1
        return {
            "method": "daily_gift",
            "cost_iv": 0,
            "balance_after": int(account.iv or 0),
            "free_spin_tickets_after": int(user_stats.get("free_spin_tickets") or 0),
            "daily_free_remaining": max(gift_total - int(user_stats.get("daily_free_used") or 0), 0),
        }

    backpack = _backpack(user_stats)
    free_tickets = int(backpack.get(REWARD_TYPE_FREE_SPIN_TICKET) or 0)
    if free_tickets > 0:
        _remove_backpack_item(user_stats, REWARD_TYPE_FREE_SPIN_TICKET, 1)
        return {
            "method": "ticket",
            "cost_iv": 0,
            "balance_after": int(account.iv or 0),
            "free_spin_tickets_after": int(user_stats.get("free_spin_tickets") or 0),
            "daily_free_remaining": 0,
        }

    spin_cost = int(settings.get("spin_cost_iv") or 0)
    balance = int(account.iv or 0)
    if balance < spin_cost:
        raise HTTPException(status_code=400, detail=f"{settings.get('currency_name') or pivkeyu}不足")
    account.iv = balance - spin_cost
    return {
        "method": "currency",
        "cost_iv": spin_cost,
        "balance_after": int(account.iv or 0),
        "free_spin_tickets_after": int(user_stats.get("free_spin_tickets") or 0),
        "daily_free_remaining": 0,
    }


def _payment_label(payment: dict[str, Any], settings: dict[str, Any]) -> str:
    method = payment.get("method")
    if method == "daily_gift":
        return "每日赠送次数"
    if method == "ticket":
        return "抽奖券"
    return f"{int(payment.get('cost_iv') or 0)} {settings.get('currency_name') or pivkeyu}"


def _apply_prize_reward(
    user_stats: dict[str, Any],
    prize: dict[str, Any],
    *,
    account: Emby | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    reward_type = _normalize_reward_type(prize.get("reward_type"))
    quantity = max(int(prize.get("free_spin_quantity") or 0), 0)
    if reward_type == REWARD_TYPE_EMBY_CURRENCY:
        if account is None or quantity <= 0:
            return None
        account.iv = int(account.iv or 0) + quantity
        return {
            "type": reward_type,
            "label": (settings or {}).get("currency_name") or pivkeyu,
            "quantity": quantity,
            "balance_after": int(account.iv or 0),
        }
    if reward_type not in BACKPACK_ITEM_TYPES:
        return None
    quantity = max(quantity, 1)
    grant = _add_backpack_item(user_stats, reward_type, quantity)
    if grant is None:
        return None
    return {
        "type": reward_type,
        "label": BACKPACK_ITEM_META[reward_type]["label"],
        "quantity": quantity,
        "quantity_after": grant["quantity_after"],
        "free_spin_tickets_after": int(user_stats.get("free_spin_tickets") or 0),
    }


def _symbol_pool(state: dict[str, Any]) -> list[str]:
    symbols = [str(prize.get("icon") or "🎁") for prize in state.get("prizes") or [] if prize.get("enabled")]
    blank_icon = str((state.get("settings") or {}).get("blank_icon") or "🍀")
    symbols.append(blank_icon)
    symbols.extend(["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣", "⭐", "💰", "🎟️"])
    unique = []
    for symbol in symbols:
        if symbol and symbol not in unique:
            unique.append(symbol[:16])
    return unique[:24] or ["🎁", "🍀", "⭐"]


def _blank_reels(state: dict[str, Any]) -> list[str]:
    pool = _symbol_pool(state)
    if len(pool) == 1:
        return [pool[0], "🍒", "🔔"]
    reels = [RNG.choice(pool) for _ in range(3)]
    if reels[0] == reels[1] == reels[2]:
        alternatives = [symbol for symbol in pool if symbol != reels[0]] or ["🍋"]
        reels[2] = RNG.choice(alternatives)
    return reels


def _winning_reels(icon: Any) -> list[str]:
    symbol = str(icon or "🎁")[:16] or "🎁"
    return [symbol, symbol, symbol]


def _record_reels(record: dict[str, Any]) -> list[str]:
    raw_reels = record.get("reels")
    if isinstance(raw_reels, list) and len(raw_reels) >= 3:
        reels = [str(item or "")[:16] or "◇" for item in raw_reels[:3]]
    elif record.get("outcome") == "win":
        reels = _winning_reels(record.get("prize_icon"))
    else:
        icon = str(record.get("prize_icon") or "🍀")[:16] or "🍀"
        reels = [icon, "🍒", "🔔"]
    if record.get("outcome") == "win":
        return _winning_reels(record.get("prize_icon") or reels[0])
    if reels[0] == reels[1] == reels[2]:
        reels[2] = "🔔" if reels[0] != "🔔" else "🍒"
    return reels


def _next_guarantee_status(state: dict[str, Any], user_stats: dict[str, Any]) -> dict[str, Any] | None:
    settings = state.get("settings") or {}
    if not settings.get("pity_enabled"):
        return None
    candidates: list[dict[str, Any]] = []
    for prize in _available_prizes(state, guarantee_only=True):
        threshold = _prize_guarantee_after(prize, settings)
        if threshold <= 0:
            continue
        current = _global_miss_streak(user_stats)
        candidates.append(
            {
                "prize_id": prize.get("id"),
                "prize_name": prize.get("name"),
                "prize_icon": prize.get("icon"),
                "current": min(current, threshold),
                "threshold": threshold,
                "remaining": max(threshold - current, 1),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (int(item.get("remaining") or 0), int(item.get("threshold") or 0)))
    return candidates[0]


def _public_records(records: list[dict[str, Any]], *, user_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    filtered = records
    if user_id is not None:
        filtered = [record for record in records if int(record.get("user_id") or 0) == int(user_id)]
    rows = []
    for record in filtered[: max(int(limit or 20), 1)]:
        payload = dict(record)
        payload["reels"] = _record_reels(payload)
        rows.append(payload)
    return rows


def _active_market_listings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in state.get("market_listings") or [] if item.get("status") == "active"]
    rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    for item in rows:
        meta = BACKPACK_ITEM_META.get(item.get("item_type"), {})
        item["item_label"] = meta.get("label", item.get("item_type"))
        item["item_icon"] = meta.get("icon", "◇")
    return rows


def _public_redeem_codes(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for code in state.get("redeem_codes") or []:
        payload = dict(code)
        payload["used_by_count"] = len(payload.get("used_by") or {})
        rows.append(payload)
    rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return rows[:200]


def _public_slot_user(
    state: dict[str, Any],
    user_id: int,
    *,
    account: Emby | None = None,
    identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    stats = _get_user_stats(state, int(user_id))
    if account is None:
        account = sql_get_emby(int(user_id))
    identity = identity if identity is not None else _cached_telegram_identity(int(user_id))
    return {
        "tg": int(user_id),
        "display_label": _telegram_display_label(int(user_id), identity),
        "display_name": (identity or {}).get("display_name") or "",
        "username": (identity or {}).get("username") or "",
        "emby_name": str(getattr(account, "name", "") or ""),
        "embyid": str(getattr(account, "embyid", "") or ""),
        "level": str(getattr(account, "lv", "") or ""),
        "miss_streak": int(stats.get("miss_streak") or 0),
        "total_spins": int(stats.get("total_spins") or 0),
        "win_count": int(stats.get("win_count") or 0),
        "blank_count": int(stats.get("blank_count") or 0),
        "last_spin_at": int(stats.get("last_spin_at") or 0),
    }


def _serialize_bundle(
    state: dict[str, Any],
    *,
    user_id: int | None = None,
    include_admin: bool = False,
    account: Emby | None = None,
) -> dict[str, Any]:
    settings = dict(state.get("settings") or {})
    probabilities = _probability_summary(state)
    prizes = [_public_prize(prize, probabilities, settings) for prize in state.get("prizes") or []]
    bundle = {
        "meta": {
            "plugin_name": PLUGIN_MANIFEST.get("name"),
            "version": PLUGIN_MANIFEST.get("version"),
            "symbols": _symbol_pool(state),
            "bottom_nav": build_bottom_nav(),
        },
        "settings": settings,
        "probabilities": probabilities,
        "prizes": prizes if include_admin else [prize for prize in prizes if prize.get("enabled")],
        "stats": _global_stats(state),
        "records": _public_records(
            state.get("records") or [],
            user_id=None if include_admin else user_id,
            limit=min(int(settings.get("record_limit") or 300), 500 if include_admin else 200),
        ),
        "market_listings": _active_market_listings(state),
        "redeem_codes": _public_redeem_codes(state) if include_admin else [],
        "permissions": {
            "is_admin": bool(user_id is not None and is_admin_user_id(int(user_id))),
            "admin_url": "/plugins/slot-box/admin" if user_id is not None and is_admin_user_id(int(user_id)) else None,
        },
    }
    account_payload = None
    if user_id is not None:
        if account is None:
            account = sql_get_emby(user_id)
        if account is not None:
            account_payload = serialize_emby_user(account)

    bundle["account"] = account_payload

    if user_id is not None:
        user_stats = deepcopy(_get_user_stats(state, int(user_id)))
        level = _account_level(account)
        now_ts = int(time.time())
        cooldown = int(settings.get("cooldown_seconds") or 0)
        wait_seconds = max(cooldown - (now_ts - int(user_stats.get("last_spin_at") or 0)), 0) if cooldown else 0
        daily_limit = _effective_daily_limit(settings, level)
        daily_gift_total = _daily_gift_total(settings, level)
        daily_free_used = int(user_stats.get("daily_free_used") or 0)
        next_guarantee = _next_guarantee_status(state, user_stats)
        bundle["user_stats"] = user_stats
        bundle["backpack"] = _backpack_summary(user_stats)
        bundle["limits"] = {
            "daily_limit": daily_limit,
            "daily_remaining": None if daily_limit <= 0 else max(daily_limit - int(user_stats.get("daily_count") or 0), 0),
            "daily_gift_total": daily_gift_total,
            "daily_free_remaining": max(daily_gift_total - daily_free_used, 0),
            "cooldown_seconds": cooldown,
            "wait_seconds": wait_seconds,
            "spin_cost_iv": int(settings.get("spin_cost_iv") or 0),
            "currency_name": settings.get("currency_name") or pivkeyu,
            "free_spin_tickets": int(user_stats.get("free_spin_tickets") or 0),
            "user_level": level,
            "user_level_text": get_level_meta(level)["short_text"],
            "next_guarantee_after": None if next_guarantee is None else next_guarantee.get("threshold"),
            "next_guarantee": next_guarantee,
        }
    return bundle


def _update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_SETTINGS)
    sanitized = {key: value for key, value in patch.items() if key in allowed and value is not None}
    with STATE_LOCK:
        state = _load_state_unlocked()
        settings = dict(state.get("settings") or {})
        settings.update(sanitized)
        state["settings"] = _normalize_settings(settings)
        _validate_limited_reward_rates(state)
        _save_state_unlocked(state)
        return _serialize_bundle(state, include_admin=True)


def _create_prize(payload: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        prize = _clean_prize(payload)
        existing_ids = {item["id"] for item in state.get("prizes") or []}
        original_id = prize["id"]
        while prize["id"] in existing_ids:
            prize["id"] = _clean_prize_id(f"{original_id}-{uuid4().hex[:4]}")
        state.setdefault("prizes", []).append(prize)
        _validate_limited_reward_rates(state)
        _save_state_unlocked(state)
        return _serialize_bundle(state, include_admin=True)


def _patch_prize(prize_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        for index, prize in enumerate(state.get("prizes") or []):
            if prize.get("id") != prize_id:
                continue
            merged = dict(prize)
            merged.update({key: value for key, value in patch.items() if value is not None})
            state["prizes"][index] = _clean_prize(merged, existing=prize)
            _validate_limited_reward_rates(state)
            _save_state_unlocked(state)
            return _serialize_bundle(state, include_admin=True)
    raise HTTPException(status_code=404, detail="奖品不存在")


def _delete_prize(prize_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        before_count = len(state.get("prizes") or [])
        state["prizes"] = [prize for prize in state.get("prizes") or [] if prize.get("id") != prize_id]
        if len(state["prizes"]) == before_count:
            raise HTTPException(status_code=404, detail="奖品不存在")
        _validate_limited_reward_rates(state)
        _save_state_unlocked(state)
        return _serialize_bundle(state, include_admin=True)


def _validate_limited_reward_rates(state: dict[str, Any]) -> None:
    probabilities = _probability_summary(state)
    reward_type_rates = probabilities.get("reward_type_rates") or {}
    for reward_type in LIMITED_REWARD_TYPES:
        rate = float(reward_type_rates.get(reward_type, 0) or 0)
        if rate < LIMITED_REWARD_MAX_RATE:
            continue
        label = "邀请资格" if reward_type == REWARD_TYPE_GROUP_INVITE else "开号资格"
        raise ValueError(f"{label}总中奖概率必须低于 1%，当前约 {round(rate, 4)}%，请降低小数权重")


def _create_redeem_code(payload: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        code = _clean_redeem_code(payload)
        existing_codes = {item.get("code") for item in state.get("redeem_codes") or []}
        original_code = code["code"]
        suffix = 1
        while code["code"] in existing_codes:
            suffix += 1
            code["code"] = _normalize_redeem_code(f"{original_code}-{suffix}")
        state.setdefault("redeem_codes", []).append(code)
        _save_state_unlocked(state)
        return _serialize_bundle(state, include_admin=True)


def _patch_redeem_code(code_value: str, patch: dict[str, Any]) -> dict[str, Any]:
    normalized_code = _normalize_redeem_code(code_value)
    with STATE_LOCK:
        state = _load_state_unlocked()
        for index, code in enumerate(state.get("redeem_codes") or []):
            if code.get("code") != normalized_code:
                continue
            merged = dict(code)
            merged.update({key: value for key, value in patch.items() if value is not None})
            state["redeem_codes"][index] = _clean_redeem_code(merged, existing=code)
            _save_state_unlocked(state)
            return _serialize_bundle(state, include_admin=True)
    raise HTTPException(status_code=404, detail="兑换码不存在")


def _delete_redeem_code(code_value: str) -> dict[str, Any]:
    normalized_code = _normalize_redeem_code(code_value)
    with STATE_LOCK:
        state = _load_state_unlocked()
        before_count = len(state.get("redeem_codes") or [])
        state["redeem_codes"] = [code for code in state.get("redeem_codes") or [] if code.get("code") != normalized_code]
        if len(state["redeem_codes"]) == before_count:
            raise HTTPException(status_code=404, detail="兑换码不存在")
        _save_state_unlocked(state)
        return _serialize_bundle(state, include_admin=True)


def _admin_search_users(query: str, limit: int = 20) -> dict[str, Any]:
    normalized = str(query or "").strip()
    normalized_text = normalized.lower().lstrip("@")
    max_rows = min(max(int(limit or 20), 1), 80)
    with STATE_LOCK:
        state = _load_state_unlocked()
        user_ids = {
            int(raw_tg)
            for raw_tg in (state.get("users") or {})
            if str(raw_tg).lstrip("-").isdigit()
        }
        if normalized.lstrip("-").isdigit():
            direct_tg = int(normalized)
            if direct_tg > 0:
                user_ids.add(direct_tg)
        identities = state.get("telegram_identities") if isinstance(state.get("telegram_identities"), dict) else {}
        for raw_tg, identity in identities.items():
            try:
                tg = int(raw_tg)
            except (TypeError, ValueError):
                continue
            if not normalized or _identity_matches_query(tg, identity, normalized):
                user_ids.add(tg)
        with Session() as session:
            filters = []
            if normalized:
                filters.extend([Emby.name.ilike(f"%{normalized}%"), Emby.embyid.ilike(f"%{normalized}%")])
                if normalized.lstrip("-").isdigit():
                    filters.append(Emby.tg == int(normalized))
            query_obj = session.query(Emby)
            if filters:
                query_obj = query_obj.filter(or_(*filters))
            else:
                query_obj = query_obj.filter(Emby.tg.in_(list(user_ids) or [0]))
            accounts = {int(row.tg): row for row in query_obj.order_by(Emby.tg.desc()).limit(120).all()}
            user_ids.update(accounts.keys())

            rows = []
            for tg in sorted(user_ids, reverse=True):
                identity = identities.get(str(tg)) if isinstance(identities.get(str(tg)), dict) else _cached_telegram_identity(tg)
                account = accounts.get(tg)
                if account is None:
                    account = session.query(Emby).filter(Emby.tg == tg).first()
                if normalized:
                    fields = [
                        str(tg),
                        str((identity or {}).get("display_name") or ""),
                        str((identity or {}).get("username") or ""),
                        str(getattr(account, "name", "") or ""),
                        str(getattr(account, "embyid", "") or ""),
                    ]
                    if not any(normalized_text in field.lower().lstrip("@") for field in fields if field):
                        continue
                rows.append(_public_slot_user(state, tg, account=account, identity=identity or {}))
                if len(rows) >= max_rows:
                    break
    return {"items": rows}


def _reset_user_stats_dict(stats: dict[str, Any]) -> None:
    stats["total_spins"] = 0
    stats["win_count"] = 0
    stats["blank_count"] = 0
    stats["miss_streak"] = 0
    stats["daily_count"] = 0
    stats["daily_free_used"] = 0
    stats["last_spin_at"] = 0
    stats["prize_miss_streaks"] = {}


def _admin_set_user_stats(user_id: int, total_spins: int, *, reset_spin_stats: bool = False) -> dict[str, Any]:
    value = _clean_int(
        total_spins,
        default=0,
        minimum=0,
        maximum=1_000_000,
        field_name="总抽奖次数",
    )
    with STATE_LOCK:
        state = _load_state_unlocked()
        user_stats = _get_user_stats(state, int(user_id))
        if reset_spin_stats:
            _reset_user_stats_dict(user_stats)
            state["records"] = [
                record
                for record in state.get("records") or []
                if int(record.get("user_id") or 0) != int(user_id)
            ]
        else:
            user_stats["total_spins"] = value
        _save_state_unlocked(state)
        return {"user": _public_slot_user(state, int(user_id)), **_serialize_bundle(state, include_admin=True)}


def _admin_reset_all_user_stats(*, clear_records: bool = True) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        users = state.get("users") or {}
        affected = 0
        for stats in users.values():
            if not isinstance(stats, dict):
                continue
            _reset_user_stats_dict(stats)
            affected += 1
        if clear_records:
            state["records"] = []
        _save_state_unlocked(state)
        bundle = _serialize_bundle(state, include_admin=True)
        bundle["reset_user_count"] = affected
        return bundle


def _redeem_code_for_user(user_id: int, code_value: str) -> dict[str, Any]:
    normalized_code = _normalize_redeem_code(code_value)
    with STATE_LOCK:
        state = _load_state_unlocked()
        account = sql_get_emby(user_id)
        for code in state.get("redeem_codes") or []:
            if code.get("code") != normalized_code:
                continue
            if not code.get("enabled"):
                raise HTTPException(status_code=400, detail="兑换码已停用")
            max_uses = int(code.get("max_uses") or 0)
            if max_uses > 0 and int(code.get("used_count") or 0) >= max_uses:
                raise HTTPException(status_code=400, detail="兑换码使用次数已满")
            used_by = code.setdefault("used_by", {})
            user_key = str(int(user_id))
            per_user_limit = int(code.get("per_user_limit") or 1)
            if int(used_by.get(user_key) or 0) >= per_user_limit:
                raise HTTPException(status_code=400, detail="你已经使用过这个兑换码")
            user_stats = _get_user_stats(state, int(user_id))
            grants = _clean_grants(code.get("grants"))
            granted = []
            for item_type, quantity in grants.items():
                grant = _add_backpack_item(user_stats, item_type, quantity)
                if grant:
                    granted.append(grant)
            if not granted:
                raise HTTPException(status_code=400, detail="兑换码没有可发放内容")
            code["used_count"] = int(code.get("used_count") or 0) + 1
            used_by[user_key] = int(used_by.get(user_key) or 0) + 1
            code["updated_at"] = _iso_now()
            _save_state_unlocked(state)
            bundle = _serialize_bundle(state, user_id=user_id, account=account)
            return {"granted": granted, **bundle}
    raise HTTPException(status_code=404, detail="兑换码不存在")


def _grant_slot_registration_credit(user_id: int) -> dict[str, Any]:
    days = normalize_invite_days(30)
    with Session() as session:
        account = session.query(Emby).filter(Emby.tg == int(user_id)).with_for_update().first()
        if account is None:
            account = Emby(tg=int(user_id), lv="d", us=0, iv=0)
            session.add(account)
            session.flush()
        if account.embyid:
            raise ValueError("你当前已经有 Emby 账号，这里只能使用注册资格")
        if int(account.us or 0) > 0:
            raise ValueError("你已经有注册资格，请先使用“创建账号”")
        account_before = _serialize_emby_row(account)
        account.us = int(account.us or 0) + int(days)
        session.commit()
        session.refresh(account)
        account_after = _serialize_emby_row(account)
    _invalidate_emby_payload(account_before)
    _invalidate_emby_payload(account_after)
    sql_invalidate_emby_cache(user_id)
    return {"days": int(days), "account": account_after}


def _use_backpack_item(user_id: int, item_type: str) -> dict[str, Any]:
    normalized_type = _normalize_backpack_item_type(item_type)
    if normalized_type == REWARD_TYPE_FREE_SPIN_TICKET:
        raise ValueError("抽奖券会在抽奖时自动抵扣，不需要手动使用")

    with STATE_LOCK:
        state = _load_state_unlocked()
        user_stats = _get_user_stats(state, int(user_id))
        backpack = _backpack(user_stats)
        if int(backpack.get(normalized_type) or 0) <= 0:
            raise ValueError(f"{BACKPACK_ITEM_META[normalized_type]['label']}数量不足")

        grant: dict[str, Any]
        if normalized_type == REWARD_TYPE_GROUP_INVITE:
            grant = grant_slot_group_invite_credit(
                owner_tg=int(user_id),
                granted_by_tg=int(user_id),
                source_ref=f"slot-backpack:{int(user_id)}:{int(time.time())}",
                note="老虎机背包使用邀请资格",
            )
            message = "已拥有邀请资格，可前往 MiniApp 主页的入群资格邀请模块发送邀请链接。"
        elif normalized_type == REWARD_TYPE_ACCOUNT_OPEN:
            grant = _grant_slot_registration_credit(int(user_id))
            days = int(grant.get("days") or 30)
            message = f"已获得 {days} 天 Emby 注册资格，请回到 Bot 用户面板继续创建账号。"
        else:
            raise ValueError("该背包物品暂不支持手动使用")

        used_item = _remove_backpack_item(user_stats, normalized_type, 1)
        _save_state_unlocked(state)
        account = sql_get_emby(user_id)
        bundle = _serialize_bundle(state, user_id=int(user_id), account=account)
        return {"used_item": used_item, "grant": grant, "message": message, **bundle}


def _transfer_item(sender_tg: int, target_tg: int, item_type: str, quantity: int) -> dict[str, Any]:
    normalized_type = _normalize_backpack_item_type(item_type)
    qty = max(int(quantity or 1), 1)
    if int(sender_tg) == int(target_tg):
        raise HTTPException(status_code=400, detail="不能转赠给自己")
    with STATE_LOCK:
        state = _load_state_unlocked()
        sender_stats = _get_user_stats(state, int(sender_tg))
        target_stats = _get_user_stats(state, int(target_tg))
        _remove_backpack_item(sender_stats, normalized_type, qty)
        _add_backpack_item(target_stats, normalized_type, qty)
        _save_state_unlocked(state)
        return _serialize_bundle(state, user_id=int(sender_tg))


def _create_listing(user: dict[str, Any], item_type: str, quantity: int, price_iv: int) -> dict[str, Any]:
    seller_tg = int(user["id"])
    normalized_type = _normalize_backpack_item_type(item_type)
    qty = _clean_int(quantity, default=1, minimum=1, maximum=1_000_000, field_name="上架数量")
    price = _clean_int(price_iv, default=0, minimum=0, maximum=MAX_SPIN_COST, field_name="上架价格")
    with STATE_LOCK:
        state = _load_state_unlocked()
        seller_stats = _get_user_stats(state, seller_tg)
        _remove_backpack_item(seller_stats, normalized_type, qty)
        listing = {
            "id": uuid4().hex[:12],
            "seller_tg": seller_tg,
            "seller_display": _telegram_user_label(user),
            "item_type": normalized_type,
            "quantity": qty,
            "price_iv": price,
            "status": "active",
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
        }
        state.setdefault("market_listings", []).insert(0, listing)
        _save_state_unlocked(state)
        return _serialize_bundle(state, user_id=seller_tg)


def _cancel_listing(user_id: int, listing_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        for listing in state.get("market_listings") or []:
            if listing.get("id") != listing_id or listing.get("status") != "active":
                continue
            if int(listing.get("seller_tg") or 0) != int(user_id) and not is_admin_user_id(int(user_id)):
                raise HTTPException(status_code=403, detail="不能取消别人的上架")
            seller_stats = _get_user_stats(state, int(listing.get("seller_tg")))
            _add_backpack_item(seller_stats, listing.get("item_type"), int(listing.get("quantity") or 0))
            listing["status"] = "cancelled"
            listing["updated_at"] = _iso_now()
            _save_state_unlocked(state)
            return _serialize_bundle(state, user_id=int(user_id))
    raise HTTPException(status_code=404, detail="上架商品不存在")


def _purchase_listing(user_id: int, listing_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        state_before_purchase = deepcopy(state)
        listing = next(
            (item for item in state.get("market_listings") or [] if item.get("id") == listing_id and item.get("status") == "active"),
            None,
        )
        if listing is None:
            raise HTTPException(status_code=404, detail="上架商品不存在或已售出")
        seller_tg = int(listing.get("seller_tg") or 0)
        if seller_tg == int(user_id):
            raise HTTPException(status_code=400, detail="不能购买自己上架的物品")
        with Session() as session:
            buyer = session.query(Emby).filter(Emby.tg == int(user_id)).with_for_update().first()
            if buyer is None:
                raise HTTPException(status_code=403, detail="未找到你的 Emby 账户")
            seller = session.query(Emby).filter(Emby.tg == seller_tg).with_for_update().first()
            if seller is None:
                raise HTTPException(status_code=400, detail="卖家 Emby 账户不存在")
            price = int(listing.get("price_iv") or 0)
            if int(buyer.iv or 0) < price:
                raise HTTPException(status_code=400, detail=f"{pivkeyu}不足")
            buyer_before = _serialize_emby_row(buyer)
            seller_before = _serialize_emby_row(seller)
            buyer.iv = int(buyer.iv or 0) - price
            seller.iv = int(seller.iv or 0) + price
            buyer_stats = _get_user_stats(state, int(user_id))
            _add_backpack_item(buyer_stats, listing.get("item_type"), int(listing.get("quantity") or 0))
            listing["status"] = "sold"
            listing["buyer_tg"] = int(user_id)
            listing["sold_at"] = _iso_now()
            listing["updated_at"] = _iso_now()
            try:
                session.commit()
            except Exception:
                session.rollback()
                _save_state_unlocked(state_before_purchase)
                raise
            session.refresh(buyer)
            session.refresh(seller)
            _invalidate_emby_payload(buyer_before)
            _invalidate_emby_payload(_serialize_emby_row(buyer))
            _invalidate_emby_payload(seller_before)
            _invalidate_emby_payload(_serialize_emby_row(seller))
            _save_state_unlocked(state)
            return _serialize_bundle(state, user_id=int(user_id), account=buyer)
    raise HTTPException(status_code=404, detail="上架商品不存在或已售出")


def _spin_for_user(user: dict[str, Any], *, account_open_receiver_ok: bool = True) -> dict[str, Any]:
    user_id = int(user["id"])
    user_label = _telegram_user_label(user)
    with STATE_LOCK:
        state = _load_state_unlocked()
        state_before_spin = deepcopy(state)
        settings = state.get("settings") or {}
        if not settings.get("enabled", True):
            raise HTTPException(status_code=403, detail="盲盒当前未开放")
        _validate_limited_reward_rates(state)

        with Session() as session:
            account = session.query(Emby).filter(Emby.tg == user_id).with_for_update().first()
            if account is None:
                raise HTTPException(status_code=403, detail="未找到你的 Emby 账户，不能参与抽奖")
            account_before_payload = _serialize_emby_row(account)

            user_stats = _get_user_stats(state, user_id)
            level = _account_level(account)
            now_ts = int(time.time())
            cooldown = int(settings.get("cooldown_seconds") or 0)
            if cooldown and now_ts - int(user_stats.get("last_spin_at") or 0) < cooldown:
                wait_seconds = cooldown - (now_ts - int(user_stats.get("last_spin_at") or 0))
                raise HTTPException(status_code=429, detail=f"抽取冷却中，还需等待 {wait_seconds} 秒")

            daily_limit = _effective_daily_limit(settings, level)
            if daily_limit and int(user_stats.get("daily_count") or 0) >= daily_limit:
                raise HTTPException(status_code=429, detail="今日抽取次数已用完")

            prize_pool = _available_prizes(state, account_open_receiver_ok=account_open_receiver_ok)
            guarantee_pool = _available_prizes(
                state,
                guarantee_only=True,
                account_open_receiver_ok=account_open_receiver_ok,
            )
            blank_weight = _weight_value(settings.get("blank_weight")) if settings.get("blank_enabled") else 0.0
            if not prize_pool and blank_weight <= 0:
                raise HTTPException(status_code=400, detail="抽奖池为空，请先在后台配置奖品或轮空权重")

            payment = _consume_spin_payment(user_stats, settings, account)
            payment_label = _payment_label(payment, settings)

            ready_guarantee_pool = (
                _guarantee_ready_prizes(guarantee_pool, settings, user_stats)
                if settings.get("pity_enabled")
                else []
            )
            pity_triggered = bool(ready_guarantee_pool)

            if pity_triggered:
                entries = [("prize", prize, _weight_value(prize.get("weight"))) for prize in ready_guarantee_pool]
                outcome, prize = _pick_weighted(entries)
            else:
                entries = [("prize", prize, _weight_value(prize.get("weight"))) for prize in prize_pool]
                if blank_weight > 0:
                    entries.append(("blank", None, blank_weight))
                outcome, prize = _pick_weighted(entries)

            draw_probabilities = _probability_summary(state, account_open_receiver_ok=account_open_receiver_ok)

            user_stats["total_spins"] = int(user_stats.get("total_spins") or 0) + 1
            user_stats["daily_count"] = int(user_stats.get("daily_count") or 0) + 1
            user_stats["last_spin_at"] = now_ts

            record: dict[str, Any]
            broadcast_payload: dict[str, Any] | None = None
            reward_grant: dict[str, Any] | None = None
            if outcome == "prize" and prize is not None:
                if int(prize.get("stock") or 0) > 0:
                    prize["stock"] = int(prize.get("stock") or 0) - 1
                    prize["updated_at"] = _iso_now()
                reward_grant = _apply_prize_reward(user_stats, prize, account=account, settings=settings)
                user_stats["win_count"] = int(user_stats.get("win_count") or 0) + 1
                user_stats["miss_streak"] = 0
                user_stats["prize_miss_streaks"] = {}
                reels = _winning_reels(prize.get("icon"))
                message = prize.get("delivery_text") or prize.get("description") or "请联系管理员处理奖励发放。"
                if reward_grant:
                    if reward_grant.get("type") == REWARD_TYPE_EMBY_CURRENCY:
                        message = (
                            f"{message}\n已到账：{int(reward_grant.get('quantity') or 0)} "
                            f"{reward_grant.get('label')}，当前余额 {int(reward_grant.get('balance_after') or 0)}。"
                        )
                    else:
                        message = (
                            f"{message}\n已放入背包：{reward_grant.get('label')} "
                            f"x{int(reward_grant.get('quantity') or 0)}。"
                        )
                result = {
                    "outcome": "win",
                    "title": f"抽中 {prize.get('name')}",
                    "message": message,
                    "prize": dict(prize),
                    "reels": reels,
                    "pity_triggered": pity_triggered,
                    "payment": payment,
                    "payment_label": payment_label,
                    "reward_grant": reward_grant,
                }
                record = {
                    "id": uuid4().hex[:12],
                    "user_id": user_id,
                    "user_display": user_label,
                    "outcome": "win",
                    "prize_id": prize.get("id"),
                    "prize_name": prize.get("name"),
                    "prize_icon": prize.get("icon"),
                    "payment_method": payment.get("method"),
                    "cost_iv": payment.get("cost_iv", 0),
                    "reward_type": prize.get("reward_type"),
                    "reward_quantity": 0 if not reward_grant else reward_grant.get("quantity", 0),
                    "reward_label": "" if not reward_grant else reward_grant.get("label", ""),
                    "reels": reels,
                    "pity_triggered": pity_triggered,
                    "created_at": _iso_now(),
                }
                if prize.get("broadcast_enabled"):
                    broadcast_payload = {
                        "text": _broadcast_text(
                            user_label=user_label,
                            prize=prize,
                            probabilities=draw_probabilities,
                            pity_triggered=pity_triggered,
                        ),
                        "image_url": prize.get("broadcast_image_url") or "",
                    }
            else:
                user_stats["blank_count"] = int(user_stats.get("blank_count") or 0) + 1
                user_stats["miss_streak"] = int(user_stats.get("miss_streak") or 0) + 1
                reels = _blank_reels(state)
                result = {
                    "outcome": "blank",
                    "title": settings.get("blank_label") or "轮空",
                    "message": "本次没有抽中奖品。",
                    "prize": None,
                    "reels": reels,
                    "pity_triggered": False,
                    "payment": payment,
                    "payment_label": payment_label,
                    "reward_grant": None,
                }
                record = {
                    "id": uuid4().hex[:12],
                    "user_id": user_id,
                    "user_display": user_label,
                    "outcome": "blank",
                    "prize_id": None,
                    "prize_name": settings.get("blank_label") or "轮空",
                    "prize_icon": settings.get("blank_icon") or "🍀",
                    "payment_method": payment.get("method"),
                    "cost_iv": payment.get("cost_iv", 0),
                    "reward_type": "blank",
                    "reward_quantity": 0,
                    "reward_label": "",
                    "reels": reels,
                    "pity_triggered": False,
                    "created_at": _iso_now(),
                }

            state.setdefault("records", []).insert(0, record)
            record_limit = int(settings.get("record_limit") or 300)
            state["records"] = state["records"][:record_limit]
            _save_state_unlocked(state)

            try:
                session.commit()
            except Exception:
                session.rollback()
                _save_state_unlocked(state_before_spin)
                raise
            session.refresh(account)
            _invalidate_emby_payload(account_before_payload)
            _invalidate_emby_payload(_serialize_emby_row(account))

            bundle = _serialize_bundle(state, user_id=user_id, account=account)
            return {"result": result, "broadcast": broadcast_payload, **bundle}


def _bootstrap_user_bundle(user_id: int) -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        return _serialize_bundle(state, user_id=user_id)


def _bootstrap_admin_bundle() -> dict[str, Any]:
    with STATE_LOCK:
        state = _load_state_unlocked()
        return _serialize_bundle(state, include_admin=True)


def _raise_value_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="老虎机盲盒数据写入失败")


def register_web(app, context=None) -> None:
    _configure_state_path(context)
    user_router = APIRouter(prefix="/plugins/slot-box", tags=["slot-box-user"])
    admin_router = APIRouter(prefix="/plugins/slot-box/admin-api", tags=["slot-box-admin"])

    if STATIC_DIR.exists():
        app.mount("/plugins/slot-box/static", StaticFiles(directory=STATIC_DIR), name="slot-box-static")

    @user_router.get("/app")
    def slot_app_page():
        return FileResponse(STATIC_DIR / "app.html")

    @user_router.get("/admin")
    def slot_admin_page():
        return FileResponse(STATIC_DIR / "admin.html")

    @user_router.post("/api/bootstrap")
    async def slot_bootstrap(payload: InitDataPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        await run_in_threadpool(_remember_telegram_identity, user)
        bundle = await run_in_threadpool(_bootstrap_user_bundle, int(user["id"]))
        return {"code": 200, "data": bundle}

    @user_router.post("/api/spin")
    async def slot_spin(payload: InitDataPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        account_open_receiver_ok = await _account_open_receiver_in_group(int(user["id"]))
        try:
            bundle = await run_in_threadpool(_spin_for_user, user, account_open_receiver_ok=account_open_receiver_ok)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        await _send_group_broadcast(bundle.pop("broadcast", None))
        return {"code": 200, "data": bundle}

    @user_router.post("/api/redeem")
    async def slot_redeem(payload: RedeemCodePayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        with STATE_LOCK:
            state = _load_state_unlocked()
            code = next((item for item in state.get("redeem_codes") or [] if item.get("code") == _normalize_redeem_code(payload.code)), None)
            grants = _clean_grants(code.get("grants") if code else {})
        if grants.get(REWARD_TYPE_ACCOUNT_OPEN, 0) > 0:
            await _ensure_account_open_receiver_in_group(int(user["id"]), REWARD_TYPE_ACCOUNT_OPEN)
        try:
            bundle = await run_in_threadpool(_redeem_code_for_user, int(user["id"]), payload.code)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @user_router.post("/api/backpack/use")
    async def slot_use_backpack_item(payload: UseBackpackItemPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        try:
            normalized_type = _normalize_backpack_item_type(payload.item_type)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        if normalized_type == REWARD_TYPE_ACCOUNT_OPEN:
            await _ensure_account_open_receiver_in_group(
                int(user["id"]),
                normalized_type,
                missing_group_detail="主群未配置，无法使用开号资格",
                inactive_detail="你不在主群内，不能使用开号资格",
            )
        try:
            bundle = await run_in_threadpool(_use_backpack_item, int(user["id"]), normalized_type)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @user_router.post("/api/transfer")
    async def slot_transfer(payload: TransferItemPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        await _ensure_account_open_receiver_in_group(int(payload.target_tg), payload.item_type)
        try:
            bundle = await run_in_threadpool(
                _transfer_item,
                int(user["id"]),
                int(payload.target_tg),
                payload.item_type,
                payload.quantity,
            )
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @user_router.post("/api/transfer-targets")
    async def slot_transfer_targets(payload: TransferTargetSearchPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        rows = await _search_transfer_targets(payload.query, int(user["id"]))
        return {"code": 200, "data": {"items": rows}}

    @user_router.post("/api/listing")
    async def slot_create_listing(payload: ListingPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        try:
            bundle = await run_in_threadpool(
                _create_listing,
                user,
                payload.item_type,
                payload.quantity,
                payload.price_iv,
            )
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @user_router.post("/api/listing/purchase")
    async def slot_purchase_listing(payload: ListingPurchasePayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        with STATE_LOCK:
            state = _load_state_unlocked()
            listing = next(
                (item for item in state.get("market_listings") or [] if item.get("id") == payload.listing_id and item.get("status") == "active"),
                None,
            )
            listing_type = None if listing is None else listing.get("item_type")
        if listing_type:
            await _ensure_account_open_receiver_in_group(int(user["id"]), listing_type)
        try:
            bundle = await run_in_threadpool(_purchase_listing, int(user["id"]), payload.listing_id)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @user_router.post("/api/listing/cancel")
    async def slot_cancel_listing(payload: ListingCancelPayload):
        user = await run_in_threadpool(_verify_user_from_init_data, payload.init_data)
        try:
            bundle = await run_in_threadpool(_cancel_listing, int(user["id"]), payload.listing_id)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.post("/bootstrap")
    async def slot_admin_bootstrap(payload: AdminBootstrapPayload):
        admin_user = await run_in_threadpool(verify_admin_credential, payload.token, payload.init_data)
        bundle = await run_in_threadpool(_bootstrap_admin_bundle)
        return {"code": 200, "data": {"admin_user": admin_user, **bundle}}

    @admin_router.post("/settings")
    async def slot_settings_api(payload: SettingsPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_update_settings, payload.model_dump(exclude_unset=True))
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.post("/users/search")
    async def slot_admin_user_search_api(payload: AdminUserSearchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_admin_search_users, payload.query, payload.limit)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.patch("/users/{user_id}/stats")
    async def slot_admin_user_stats_api(user_id: int, payload: AdminUserStatsPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(
                _admin_set_user_stats,
                int(user_id),
                payload.total_spins,
                reset_spin_stats=payload.reset_spin_stats,
            )
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.post("/users/reset-all")
    async def slot_admin_user_reset_all_api(payload: AdminResetAllStatsPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(
                _admin_reset_all_user_stats,
                clear_records=payload.clear_records,
            )
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.post("/prize")
    async def slot_prize_api(payload: PrizePayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_create_prize, payload.model_dump())
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.patch("/prize/{prize_id}")
    async def slot_prize_patch_api(prize_id: str, payload: PrizePatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_patch_prize, prize_id, payload.model_dump(exclude_unset=True))
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.delete("/prize/{prize_id}")
    async def slot_prize_delete_api(prize_id: str, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_delete_prize, prize_id)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.post("/redeem-code")
    async def slot_redeem_code_create_api(payload: RedeemCodeAdminPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_create_redeem_code, payload.model_dump())
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.patch("/redeem-code/{code_value}")
    async def slot_redeem_code_patch_api(code_value: str, payload: RedeemCodeAdminPatchPayload, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_patch_redeem_code, code_value, payload.model_dump(exclude_unset=True))
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    @admin_router.delete("/redeem-code/{code_value}")
    async def slot_redeem_code_delete_api(code_value: str, request: Request):
        token = request.headers.get("x-admin-token")
        init_data = request.headers.get("x-telegram-init-data")
        await run_in_threadpool(verify_admin_credential, token, init_data)
        try:
            bundle = await run_in_threadpool(_delete_redeem_code, code_value)
        except Exception as exc:
            raise _raise_value_error(exc) from exc
        return {"code": 200, "data": bundle}

    app.include_router(user_router)
    app.include_router(admin_router)


def register_bot(_bot, context=None) -> None:
    _configure_state_path(context)
    return None
