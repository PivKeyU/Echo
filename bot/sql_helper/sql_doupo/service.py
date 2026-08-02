from __future__ import annotations

import copy
import hashlib
import logging
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("doupo.service")

from bot.func_helper.emby_currency import get_emby_balance
from bot.plugins.doupo_game.core import (
    ACTION_TYPE_LABELS,
    ALCHEMY_RANKS,
    BREAKTHROUGH_RULES,
    DEFAULT_ACTION_POINT_COSTS,
    DEFAULT_ACTIONS,
    DEFAULT_DAILY_ACTION_LIMITS,
    DEFAULT_SETTINGS,
    EXPEDITION_EVENTS,
    EXPEDITION_REGIONS,
    HEAVENLY_FIRES,
    INVENTORY_CATEGORIES,
    ITEM_CATALOG,
    SECT_OPTIONS,
    SECT_RANKS,
    TECHNIQUES,
    clamp_int,
    realm_rank,
    resolve_stage_index,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_doupo.models import (
    DoupoAction,
    DoupoDailyActionCounter,
    DoupoDuelHistory,
    DoupoEconomyLedger,
    DoupoExpedition,
    DoupoInventoryItem,
    DoupoItemDefinition,
    DoupoItemDefinitionVersion,
    DoupoJournal,
    DoupoProfile,
    DoupoSetting,
    utcnow,
)
from bot.sql_helper.sql_emby import Emby, sql_invalidate_emby_cache


_CATEGORY_LOOKUP = {str(item["key"]): item for item in INVENTORY_CATEGORIES}
_FIRE_ITEM_BY_NAME = {
    "青莲地心火": "qinglian_fire_seed",
    "海心焰": "sea_heart_flame_seed",
    "陨落心炎": "fallen_heart_flame_seed",
    "骨灵冷火": "bone_spirit_cold_fire_seed",
    "三千焱炎火": "three_thousand_flame_seed",
}
_SECT_LOOKUP = {str(item["key"]): item for item in SECT_OPTIONS}
_SECT_NAME_LOOKUP = {str(item["name"]): item for item in SECT_OPTIONS}
_RARITY_WEIGHT = {
    "凡品": 1,
    "一品": 2,
    "二品": 3,
    "三品": 4,
    "玄阶": 4,
    "四品": 5,
    "五品": 6,
    "地阶": 6,
    "六品": 7,
    "七品": 8,
    "八品": 9,
    "九品": 10,
    "天阶": 8,
    "异火": 9,
}
_SETTINGS_CACHE_LOCK = threading.RLock()
_SETTINGS_CACHE_TTL = max(float(os.getenv("PIVKEYU_DOUPO_SETTINGS_CACHE_TTL", "15") or 15), 1.0)
_SETTINGS_CACHE: tuple[float, dict[str, Any]] | None = None
_DEFAULT_ACTIONS_LOCK = threading.Lock()
_DEFAULT_ACTIONS_READY = False
_ACTION_POINTS_COUNTER_KEY = "__action_points__"
_DOUQI_INCOME_COUNTER_KEY = "__douqi_income__"
ITEM_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
EQUIPMENT_SLOTS: dict[str, str] = {
    "weapon": "武器",
    "armor": "护甲",
    "boots": "靴履",
    "accessory": "饰品",
    "ring": "纳戒",
    "cauldron": "药鼎",
}
EQUIPMENT_STAT_LABELS: dict[str, str] = {
    "attack": "攻击",
    "defense": "防御",
    "agility": "身法",
    "fire_bonus": "异火",
    "alchemy_bonus": "炼药",
}
EQUIPMENT_STAT_WEIGHTS: dict[str, int] = {
    "attack": 12,
    "defense": 10,
    "agility": 8,
    "fire_bonus": 15,
    "alchemy_bonus": 6,
}
_ITEM_DEFINITION_CACHE_LOCK = threading.RLock()
_ITEM_DEFINITION_CACHE_TTL = max(float(os.getenv("PIVKEYU_DOUPO_ITEM_CACHE_TTL", "15") or 15), 1.0)
_ITEM_DEFINITION_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None

# 32 位 Integer 列上限（DoupoProfile.gold 等），防管理端/兑换溢出。
_INT32_MAX = 2_147_483_647
# 首次建号并发保护：进程内锁 + 已初始化 tg 集合，避免无锁 SELECT+INSERT 竞态。
_PROFILE_INIT_LOCK = threading.Lock()
_INITIALIZED_PROFILES: set[int] = set()


def _coerce_int(value: Any, default: int) -> int:
    return clamp_int(value, default)


def _roll_range(config: dict[str, Any], min_key: str, max_key: str, default_min: int, default_max: int) -> int:
    low = _coerce_int(config.get(min_key), default_min)
    high = _coerce_int(config.get(max_key), default_max)
    return random.randint(min(low, high), max(low, high))


def _roll_optional_range(config: dict[str, Any], min_key: str, max_key: str) -> int:
    if min_key not in config and max_key not in config:
        return 0
    return _roll_range(config, min_key, max_key, 0, 0)


def get_settings() -> dict[str, Any]:
    global _SETTINGS_CACHE

    now = time.monotonic()
    with _SETTINGS_CACHE_LOCK:
        cached = _SETTINGS_CACHE
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1])

        with Session() as session:
            rows = session.query(DoupoSetting).all()
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        for row in rows:
            merged[str(row.setting_key)] = row.setting_value
        merged["exchange_rate"] = max(_coerce_int(merged.get("exchange_rate"), 100), 1)
        merged["min_gold_to_exchange"] = max(_coerce_int(merged.get("min_gold_to_exchange"), 100), 1)
        merged["gold_min_to_buy"] = max(_coerce_int(merged.get("gold_min_to_buy"), 1), 1)
        merged["daily_gold_action_cap"] = max(_coerce_int(merged.get("daily_gold_action_cap"), 650), 0)
        merged["daily_train_limit"] = max(_coerce_int(merged.get("daily_train_limit"), 5), 0)
        merged["daily_expedition_limit"] = max(_coerce_int(merged.get("daily_expedition_limit"), 3), 0)
        merged["daily_action_points"] = max(_coerce_int(merged.get("daily_action_points"), 12), 0)
        daily_limits = copy.deepcopy(DEFAULT_DAILY_ACTION_LIMITS)
        if isinstance(merged.get("daily_action_limits"), dict):
            daily_limits.update(merged["daily_action_limits"])
        merged["daily_action_limits"] = {
            str(key): max(_coerce_int(value, DEFAULT_DAILY_ACTION_LIMITS.get(str(key), 0)), 0)
            for key, value in daily_limits.items()
        }
        point_costs = copy.deepcopy(DEFAULT_ACTION_POINT_COSTS)
        if isinstance(merged.get("action_point_costs"), dict):
            point_costs.update(merged["action_point_costs"])
        merged["action_point_costs"] = {
            str(key): max(_coerce_int(value, DEFAULT_ACTION_POINT_COSTS.get(str(key), 1)), 0)
            for key, value in point_costs.items()
        }
        merged["daily_douqi_soft_cap"] = max(_coerce_int(merged.get("daily_douqi_soft_cap"), 250), 0)
        merged["daily_douqi_hard_cap"] = max(_coerce_int(merged.get("daily_douqi_hard_cap"), 400), 0)
        if 0 < merged["daily_douqi_hard_cap"] < merged["daily_douqi_soft_cap"]:
            merged["daily_douqi_hard_cap"] = merged["daily_douqi_soft_cap"]
        merged["daily_douqi_overflow_percent"] = min(
            max(_coerce_int(merged.get("daily_douqi_overflow_percent"), 20), 0),
            100,
        )
        merged["breakthrough_failure_douqi_loss_percent"] = min(
            max(_coerce_int(merged.get("breakthrough_failure_douqi_loss_percent"), 10), 0),
            100,
        )
        merged["duel_min_stake"] = max(_coerce_int(merged.get("duel_min_stake"), 0), 0)
        merged["duel_max_stake"] = max(_coerce_int(merged.get("duel_max_stake"), 500), merged["duel_min_stake"])
        merged["duel_prepare_seconds"] = min(max(_coerce_int(merged.get("duel_prepare_seconds"), 8), 0), 600)
        merged["exchange_enabled"] = bool(merged.get("exchange_enabled", True))
        merged["broadcast_enabled"] = bool(merged.get("broadcast_enabled", True))
        merged["message_auto_delete_seconds"] = max(_coerce_int(merged.get("message_auto_delete_seconds"), 180), 0)
        if not isinstance(merged.get("realm_thresholds"), list) or not merged.get("realm_thresholds"):
            merged["realm_thresholds"] = copy.deepcopy(DEFAULT_SETTINGS["realm_thresholds"])
        _SETTINGS_CACHE = (now + _SETTINGS_CACHE_TTL, copy.deepcopy(merged))
        return merged


def set_settings(patch: dict[str, Any]) -> dict[str, Any]:
    global _SETTINGS_CACHE

    with _SETTINGS_CACHE_LOCK:
        with Session() as session:
            for key, value in patch.items():
                row = session.query(DoupoSetting).filter(DoupoSetting.setting_key == str(key)).first()
                if row is None:
                    row = DoupoSetting(setting_key=str(key), setting_value=value)
                    session.add(row)
                else:
                    row.setting_value = value
                    row.updated_at = utcnow()
            session.commit()
        _SETTINGS_CACHE = None
    return get_settings()


def _profile_display_name(display_name: str | None, username: str | None, tg: int) -> str:
    if display_name:
        return str(display_name).strip()[:80]
    if username:
        username = str(username).strip().lstrip("@")
        if username:
            return f"@{username}"[:80]
    return f"TG {tg}"


def _new_profile(tg: int, *, display_name: str | None = None, username: str | None = None) -> DoupoProfile:
    return DoupoProfile(
        tg=int(tg),
        display_name=display_name,
        username=username,
        realm_stage="斗之气",
        realm_stars=1,
        douqi=0,
        gold=0,
        fire_seed=0,
        alchemy_exp=0,
        beast_core=0,
        sect_name=None,
        sect_contribution=0,
        pill_stock=0,
        technique_key=None,
        technique_level=0,
        method_level=0,
        fire_name=None,
        fire_progress=0,
        fire_rank=0,
        academy_fire_energy=0,
        faction_reputation=0,
        black_corner_infamy=0,
        pet_key=None,
        pet_level=0,
        boss_score=0,
        tower_floor=0,
        auction_credit=0,
        breakthrough_failures=0,
    )


def upsert_profile_identity(tg: int, *, display_name: str | None = None, username: str | None = None) -> dict[str, Any]:
    actor_tg = int(tg or 0)
    if actor_tg <= 0:
        return {}
    get_or_create_profile(actor_tg)
    with Session() as session:
        row = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        if row is None:
            row = _new_profile(actor_tg, display_name=display_name, username=username)
            session.add(row)
        else:
            if display_name:
                row.display_name = display_name
            if username:
                row.username = username
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_profile(row)


def get_or_create_profile(tg: int) -> dict[str, Any]:
    actor_tg = int(tg or 0)
    if actor_tg <= 0:
        raise ValueError("非法用户")
    if actor_tg not in _INITIALIZED_PROFILES:
        with _PROFILE_INIT_LOCK:
            if actor_tg not in _INITIALIZED_PROFILES:
                with Session() as session:
                    row = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).first()
                    if row is None:
                        try:
                            row = _new_profile(actor_tg)
                            session.add(row)
                            session.commit()
                            session.refresh(row)
                        except IntegrityError:
                            # 并发首建：另一进程/线程已插入，回滚后重查。
                            session.rollback()
                            row = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).first()
                _INITIALIZED_PROFILES.add(actor_tg)
    with Session() as session:
        row = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).first()
        return serialize_profile(row)


def _battle_power(
    row: DoupoProfile,
    settings: dict[str, Any] | None = None,
    equipment_summary: dict[str, Any] | None = None,
) -> int:
    thresholds = (settings or get_settings()).get("realm_thresholds") or []
    equipment = equipment_summary if equipment_summary is not None else get_equipment_summary(int(row.tg))
    return (
        realm_rank(row.realm_stage, thresholds) * 10000
        + max(int(row.realm_stars or 1), 1) * 850
        + max(int(row.douqi or 0), 0)
        + max(int(row.fire_seed or 0), 0) * 18
        + max(int(row.alchemy_exp or 0), 0) * 8
        + max(int(row.beast_core or 0), 0) * 55
        + max(int(row.sect_contribution or 0), 0) * 3
        + max(int(row.technique_level or 0), 0) * 650
        + max(int(getattr(row, "method_level", 0) or 0), 0) * 900
        + max(int(getattr(row, "fire_rank", 0) or 0), 0) * 1300
        + max(int(getattr(row, "pet_level", 0) or 0), 0) * 520
        + max(int(row.boss_score or 0), 0) * 12
        + max(int(row.tower_floor or 0), 0) * 320
        + max(int(equipment.get("battle_power_bonus") or 0), 0)
    )


def _rank_by_threshold(value: int, rows: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    resolved = rows[0]
    for row in rows:
        if int(value) >= int(row.get(value_key) or 0):
            resolved = row
    return resolved


def _technique_payload(level: int, key: str | None = None) -> dict[str, Any]:
    current_level = max(int(level or 0), 0)
    if current_level <= 0:
        return {"key": None, "name": "未习得", "level": 0, "next": TECHNIQUES[0]}
    current = TECHNIQUES[0]
    for row in TECHNIQUES:
        if current_level >= int(row.get("level") or 1):
            current = row
    if key:
        current = {**current, "key": key}
    next_row = next((row for row in TECHNIQUES if int(row.get("level") or 0) > current_level), None)
    return {"key": current.get("key"), "name": current.get("name"), "level": current_level, "next": next_row}


def _heavenly_fire_payload(progress: int, fire_name: str | None = None) -> dict[str, Any]:
    current_progress = max(int(progress or 0), 0)
    captured = None
    for row in HEAVENLY_FIRES:
        if current_progress >= int(row.get("progress") or 0):
            captured = row
    next_row = next((row for row in HEAVENLY_FIRES if int(row.get("progress") or 0) > current_progress), None)
    name = fire_name or (captured or {}).get("name")
    return {
        "name": name,
        "progress": current_progress,
        "captured": bool(name),
        "next": next_row,
    }


def serialize_profile(
    row: DoupoProfile,
    settings: dict[str, Any] | None = None,
    equipment_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    equipment = equipment_summary if equipment_summary is not None else get_equipment_summary(int(row.tg))
    alchemy_rank = _rank_by_threshold(int(row.alchemy_exp or 0), ALCHEMY_RANKS, "exp")
    sect_rank = _rank_by_threshold(int(row.sect_contribution or 0), SECT_RANKS, "contribution")
    technique = _technique_payload(int(row.technique_level or 0), row.technique_key)
    heavenly_fire = _heavenly_fire_payload(int(row.fire_progress or 0), row.fire_name)
    return {
        "tg": int(row.tg),
        "display_name": _profile_display_name(row.display_name, row.username, int(row.tg)),
        "username": row.username,
        "realm_stage": str(row.realm_stage or "斗之气"),
        "realm_stars": int(row.realm_stars or 1),
        "douqi": int(row.douqi or 0),
        "gold": int(row.gold or 0),
        "fire_seed": int(row.fire_seed or 0),
        "alchemy_exp": int(row.alchemy_exp or 0),
        "beast_core": int(row.beast_core or 0),
        "sect_name": row.sect_name,
        "sect_joined": bool(row.sect_name),
        "sect_contribution": int(row.sect_contribution or 0),
        "sect_rank": sect_rank.get("name") if row.sect_name else None,
        "pill_stock": int(row.pill_stock or 0),
        "technique_key": technique.get("key"),
        "technique_name": technique.get("name"),
        "technique_level": int(row.technique_level or 0),
        "method_level": int(getattr(row, "method_level", 0) or 0),
        "fire_name": heavenly_fire.get("name"),
        "fire_progress": int(row.fire_progress or 0),
        "fire_rank": int(getattr(row, "fire_rank", 0) or 0),
        "academy_fire_energy": int(getattr(row, "academy_fire_energy", 0) or 0),
        "faction_reputation": int(getattr(row, "faction_reputation", 0) or 0),
        "black_corner_infamy": int(getattr(row, "black_corner_infamy", 0) or 0),
        "pet_key": getattr(row, "pet_key", None),
        "pet_level": int(getattr(row, "pet_level", 0) or 0),
        "boss_score": int(row.boss_score or 0),
        "tower_floor": int(row.tower_floor or 0),
        "auction_credit": int(row.auction_credit or 0),
        "breakthrough_failures": int(getattr(row, "breakthrough_failures", 0) or 0),
        "alchemy_rank": alchemy_rank.get("name"),
        "heavenly_fire": heavenly_fire,
        "technique": technique,
        "battle_power": _battle_power(row, settings, equipment),
        "equipment": equipment,
        "last_train_at": row.last_train_at.isoformat() if row.last_train_at else None,
        "last_breakthrough_at": row.last_breakthrough_at.isoformat() if row.last_breakthrough_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_journal(tg: int, action_type: str, title: str, detail: str = "") -> dict[str, Any]:
    with Session() as session:
        row = DoupoJournal(
            tg=int(tg),
            action_type=str(action_type or "system")[:32],
            title=str(title or "系统操作")[:128],
            detail=str(detail or "")[:2000],
        )
        session.add(row)
        session.commit()
        return {
            "id": int(row.id),
            "tg": int(row.tg),
            "action_type": row.action_type,
            "title": row.title,
            "detail": row.detail,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


def list_recent_journals(tg: int, limit: int = 20) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(DoupoJournal)
            .filter(DoupoJournal.tg == int(tg))
            .order_by(DoupoJournal.id.desc())
            .limit(max(int(limit or 20), 1))
            .all()
        )
    return [
        {
            "id": int(row.id),
            "action_type": row.action_type,
            "title": row.title,
            "detail": row.detail,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _economy_day_key(now: datetime | None = None) -> str:
    # The project runs in Asia/Shanghai; keep the daily cap aligned with player-facing days.
    source = now or utcnow()
    return (source + timedelta(hours=8)).date().isoformat()


def _normalize_item_definition_payload(item_key: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    key = str(item_key or "").strip()
    item = dict(source or {})
    category = str(item.get("category") or "token")
    equipment = dict(item.get("equipment") or {})
    equipment_slot = str(item.get("equipment_slot") or equipment.get("slot") or "").strip() or None
    if equipment_slot not in EQUIPMENT_SLOTS:
        equipment_slot = None
    stats = {
        stat: max(_coerce_int(item.get(stat, equipment.get(stat)), 0), 0)
        for stat in EQUIPMENT_STAT_LABELS
    }
    stack_default = 1 if category == "gear" else 9999
    return {
        "key": key,
        "item_key": key,
        "name": str(item.get("name") or key or "未知物品"),
        "category": category,
        "category_name": str((_CATEGORY_LOOKUP.get(category) or {}).get("name") or category),
        "rarity": str(item.get("rarity") or "凡品"),
        "description": str(item.get("description") or ""),
        "icon": str(item.get("icon") or ""),
        "tradable": bool(item.get("tradable", False)),
        "stack_limit": max(_coerce_int(item.get("stack_limit"), stack_default), 1),
        "equipment_slot": equipment_slot,
        "equipment_slot_name": EQUIPMENT_SLOTS.get(str(equipment_slot or "")),
        "equipment": {"slot": equipment_slot, **stats},
        **stats,
        "recipe_config": dict(item.get("recipe_config") or {}),
        "drop_sources": list(item.get("drop_sources") or []),
        "version": max(_coerce_int(item.get("version"), 1), 1),
        "enabled": bool(item.get("enabled", True)),
        "is_builtin": bool(item.get("is_builtin", key in ITEM_CATALOG)),
        "is_custom": not bool(item.get("is_builtin", key in ITEM_CATALOG)),
        "defined": bool(item.get("defined", key in ITEM_CATALOG or bool(source))),
    }


def _serialize_item_definition_row(row: DoupoItemDefinition) -> dict[str, Any]:
    return _normalize_item_definition_payload(
        str(row.item_key),
        {
            "name": row.name,
            "category": row.category,
            "rarity": row.rarity,
            "description": row.description,
            "icon": row.icon,
            "tradable": row.tradable,
            "stack_limit": row.stack_limit,
            "equipment_slot": row.equipment_slot,
            "attack": row.attack,
            "defense": row.defense,
            "agility": row.agility,
            "fire_bonus": row.fire_bonus,
            "alchemy_bonus": row.alchemy_bonus,
            "recipe_config": row.recipe_config,
            "drop_sources": row.drop_sources,
            "version": row.version,
            "enabled": row.enabled,
            "is_builtin": row.is_builtin,
        },
    )


def _invalidate_item_definition_cache() -> None:
    global _ITEM_DEFINITION_CACHE
    with _ITEM_DEFINITION_CACHE_LOCK:
        _ITEM_DEFINITION_CACHE = None


def _item_definition_overrides(*, force: bool = False) -> dict[str, dict[str, Any]]:
    global _ITEM_DEFINITION_CACHE
    now = time.monotonic()
    with _ITEM_DEFINITION_CACHE_LOCK:
        if not force and _ITEM_DEFINITION_CACHE is not None and _ITEM_DEFINITION_CACHE[0] > now:
            return copy.deepcopy(_ITEM_DEFINITION_CACHE[1])
        try:
            with Session() as session:
                rows = session.query(DoupoItemDefinition).all()
                resolved = {str(row.item_key): _serialize_item_definition_row(row) for row in rows}
        except Exception:
            # Plugin imports can occur before its migrations are applied. Retry on the next cache window.
            resolved = {}
        _ITEM_DEFINITION_CACHE = (now + _ITEM_DEFINITION_CACHE_TTL, resolved)
        return copy.deepcopy(resolved)


def _catalog_item(item_key: str) -> dict[str, Any]:
    key = str(item_key or "").strip()
    builtin = _normalize_item_definition_payload(
        key,
        {**dict(ITEM_CATALOG.get(key) or {}), "is_builtin": key in ITEM_CATALOG, "defined": key in ITEM_CATALOG},
    )
    override = _item_definition_overrides().get(key)
    if not override:
        return builtin
    merged = {**builtin, **override}
    merged["equipment"] = dict(override.get("equipment") or builtin.get("equipment") or {})
    return _normalize_item_definition_payload(key, merged)


def list_item_definitions(*, include_disabled: bool = True) -> list[dict[str, Any]]:
    overrides = _item_definition_overrides()
    keys = list(ITEM_CATALOG)
    keys.extend(key for key in overrides if key not in ITEM_CATALOG)
    items = [_catalog_item(key) for key in keys]
    if not include_disabled:
        items = [item for item in items if item.get("enabled", True)]
    return sorted(items, key=lambda item: (str(item.get("category") or ""), str(item.get("name") or ""), str(item.get("key") or "")))


def get_item_definition(item_key: str) -> dict[str, Any]:
    key = str(item_key or "").strip()
    if key not in ITEM_CATALOG and key not in _item_definition_overrides():
        raise ValueError("物品不存在")
    return _catalog_item(key)


def _item_definition_snapshot(row: DoupoItemDefinition) -> dict[str, Any]:
    payload = _serialize_item_definition_row(row)
    return {
        key: payload[key]
        for key in (
            "item_key",
            "name",
            "category",
            "rarity",
            "description",
            "icon",
            "tradable",
            "stack_limit",
            "equipment_slot",
            "attack",
            "defense",
            "agility",
            "fire_bonus",
            "alchemy_bonus",
            "recipe_config",
            "drop_sources",
            "version",
            "enabled",
            "is_builtin",
        )
    }


def _normalize_recipe_config(value: dict[str, Any] | None, item: dict[str, Any]) -> dict[str, Any]:
    source = dict(value or {})
    if not source or not bool(source.get("enabled", True)):
        return {}
    action_type = str(source.get("action_type") or ("craft" if item.get("category") == "gear" else "alchemy"))
    if action_type not in {"alchemy", "craft"}:
        raise ValueError("物品配方仅支持炼药或炼器类型")
    costs = {key: quantity for key, quantity in _normalize_item_costs(source.get("item_costs"))}
    if not costs:
        raise ValueError("启用配方时至少需要一种物品材料")
    for cost_key in costs:
        if not _catalog_item(cost_key).get("defined"):
            raise ValueError(f"配方材料未定义：{cost_key}")
    generated_key = f"custom_{action_type}_{item['item_key']}"
    if len(generated_key) > 64:
        digest = hashlib.sha1(str(item["item_key"]).encode("utf-8")).hexdigest()[:16]
        generated_key = f"custom_{action_type}_{digest}"
    action_key = str(source.get("action_key") or generated_key).strip()
    if not ITEM_KEY_PATTERN.fullmatch(action_key):
        raise ValueError("配方行动 key 只能使用小写字母、数字和下划线")
    return {
        "enabled": True,
        "action_key": action_key,
        "name": str(source.get("name") or f"制作{item['name']}")[:64],
        "description": str(source.get("description") or f"使用指定材料制作{item['name']}。")[:255],
        "action_type": action_type,
        "cooldown_seconds": max(_coerce_int(source.get("cooldown_seconds"), 60), 0),
        "gold_cost": max(_coerce_int(source.get("gold_cost"), 0), 0),
        "output_quantity": max(_coerce_int(source.get("output_quantity"), 1), 1),
        "item_costs": costs,
        "requirement_config": dict(source.get("requirement_config") or {}),
        "enabled_action": bool(source.get("enabled_action", True)),
        "sort_order": _coerce_int(source.get("sort_order"), 75),
    }


def _normalize_drop_sources(value: list[dict[str, Any]] | None, item_key: str) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in list(value or []):
        if not isinstance(raw, dict):
            continue
        action_key = str(raw.get("action_key") or "").strip()
        if not action_key or action_key in seen:
            continue
        if not ITEM_KEY_PATTERN.fullmatch(action_key):
            raise ValueError(f"掉落行动 key 格式错误：{action_key}")
        minimum = max(_coerce_int(raw.get("min"), 1), 1)
        maximum = max(_coerce_int(raw.get("max"), minimum), minimum)
        resolved.append(
            {
                "action_key": action_key,
                "chance": min(max(_coerce_int(raw.get("chance"), 10), 0), 100),
                "min": minimum,
                "max": maximum,
                "item_key": item_key,
            }
        )
        seen.add(action_key)
    return resolved


def _remove_managed_item_drop(reward: dict[str, Any], item_key: str) -> dict[str, Any]:
    patched = dict(reward or {})
    patched["item_drops"] = [
        dict(item)
        for item in list(patched.get("item_drops") or [])
        if str((item or {}).get("item_key") or (item or {}).get("key") or "") != item_key
    ]
    return patched


def _sync_item_content_session(
    session,
    item_key: str,
    previous_recipe: dict[str, Any] | None,
    previous_sources: list[dict[str, Any]] | None,
    recipe: dict[str, Any],
    drop_sources: list[dict[str, Any]],
) -> None:
    previous_action_keys = {
        str(item.get("action_key") or "")
        for item in list(previous_sources or [])
        if isinstance(item, dict)
    }
    previous_recipe_key = str((previous_recipe or {}).get("action_key") or "")
    if previous_recipe_key:
        previous_action_keys.add(previous_recipe_key)
    next_action_keys = {str(item.get("action_key") or "") for item in drop_sources}
    if recipe:
        next_action_keys.add(str(recipe.get("action_key") or ""))
    touched_keys = {key for key in previous_action_keys | next_action_keys if key}
    rows = {
        str(row.action_key): row
        for row in session.query(DoupoAction).filter(DoupoAction.action_key.in_(touched_keys)).with_for_update().all()
    } if touched_keys else {}

    for action_key in previous_action_keys:
        row = rows.get(action_key)
        if row is None:
            continue
        row.reward_config = _remove_managed_item_drop(dict(row.reward_config or {}), item_key)
        if action_key == previous_recipe_key and action_key != str(recipe.get("action_key") or ""):
            row.enabled = False
        row.updated_at = utcnow()

    if recipe:
        action_key = str(recipe["action_key"])
        row = rows.get(action_key)
        if row is not None:
            managed_item_key = str((row.reward_config or {}).get("managed_item_key") or "")
            if managed_item_key != item_key:
                raise ValueError(f"配方行动 key 已被其他行动占用：{action_key}")
        if row is None:
            row = DoupoAction(action_key=action_key, created_at=utcnow())
            session.add(row)
            rows[action_key] = row
        row.name = str(recipe["name"])
        row.description = str(recipe["description"])
        row.action_type = str(recipe["action_type"])
        row.cooldown_seconds = int(recipe["cooldown_seconds"])
        row.reward_config = {
            "recipe_version": max(_coerce_int((row.reward_config or {}).get("recipe_version"), 0) + 1, 1),
            "managed_item_key": item_key,
            "gold_cost": int(recipe["gold_cost"]),
            "item_costs": dict(recipe["item_costs"]),
            "item_drops": [{"item_key": item_key, "min": int(recipe["output_quantity"]), "max": int(recipe["output_quantity"]), "chance": 100}],
        }
        row.requirement_config = dict(recipe["requirement_config"])
        row.enabled = bool(recipe["enabled_action"])
        row.sort_order = int(recipe["sort_order"])
        row.updated_at = utcnow()

    for source in drop_sources:
        action_key = str(source["action_key"])
        row = rows.get(action_key)
        if row is None:
            raise ValueError(f"掉落来源行动不存在：{action_key}")
        reward = _remove_managed_item_drop(dict(row.reward_config or {}), item_key)
        drops = list(reward.get("item_drops") or [])
        drops.append(
            {
                "item_key": item_key,
                "min": int(source["min"]),
                "max": int(source["max"]),
                "chance": int(source["chance"]),
            }
        )
        reward["item_drops"] = drops
        reward["drop_table_version"] = max(_coerce_int(reward.get("drop_table_version"), 0) + 1, 1)
        row.reward_config = reward
        row.updated_at = utcnow()


def admin_upsert_item_definition(
    item_key: str,
    *,
    name: str,
    category: str,
    rarity: str,
    description: str = "",
    icon: str = "",
    tradable: bool = False,
    stack_limit: int = 9999,
    equipment_slot: str | None = None,
    attack: int = 0,
    defense: int = 0,
    agility: int = 0,
    fire_bonus: int = 0,
    alchemy_bonus: int = 0,
    recipe_config: dict[str, Any] | None = None,
    drop_sources: list[dict[str, Any]] | None = None,
    enabled: bool = True,
    change_note: str = "",
    created_by: int | None = None,
) -> dict[str, Any]:
    key = str(item_key or "").strip()
    if not ITEM_KEY_PATTERN.fullmatch(key):
        raise ValueError("物品 key 必须以小写字母开头，只能包含小写字母、数字和下划线，长度 2-64")
    category_keys = {str(item.get("key") or "") for item in INVENTORY_CATEGORIES}
    if category not in category_keys:
        raise ValueError("不支持的物品分类")
    slot = str(equipment_slot or "").strip() or None
    if category == "gear" and slot not in EQUIPMENT_SLOTS:
        raise ValueError("装备必须选择有效槽位")
    if category != "gear":
        slot = None
        attack = defense = agility = fire_bonus = alchemy_bonus = 0
    icon_value = str(icon or "").strip()[:512]
    if "://" in icon_value and not icon_value.lower().startswith("https://"):
        raise ValueError("图片图标仅支持 HTTPS 地址")
    max_integer = 2_000_000_000
    base = {
        "item_key": key,
        "name": str(name or key).strip()[:128],
        "category": category,
        "rarity": str(rarity or "凡品").strip()[:32],
        "description": str(description or "").strip()[:4000],
        "icon": icon_value,
        "tradable": bool(tradable),
        "stack_limit": min(max(int(stack_limit or 1), 1), max_integer),
        "equipment_slot": slot,
        "attack": min(max(int(attack or 0), 0), max_integer),
        "defense": min(max(int(defense or 0), 0), max_integer),
        "agility": min(max(int(agility or 0), 0), max_integer),
        "fire_bonus": min(max(int(fire_bonus or 0), 0), max_integer),
        "alchemy_bonus": min(max(int(alchemy_bonus or 0), 0), max_integer),
        "enabled": bool(enabled),
        "is_builtin": key in ITEM_CATALOG,
    }
    normalized = _normalize_item_definition_payload(key, base)
    normalized_recipe = _normalize_recipe_config(recipe_config, normalized)
    normalized_sources = _normalize_drop_sources(drop_sources, key)
    with Session() as session:
        row = session.query(DoupoItemDefinition).filter(DoupoItemDefinition.item_key == key).with_for_update().first()
        previous_recipe = dict(row.recipe_config or {}) if row is not None else {}
        previous_sources = list(row.drop_sources or []) if row is not None else []
        version = max(int(row.version or 0), 0) + 1 if row is not None else 1
        if row is None:
            row = DoupoItemDefinition(item_key=key, created_at=utcnow())
            session.add(row)
        for field in ("name", "category", "rarity", "description", "icon", "tradable", "stack_limit", "equipment_slot", "attack", "defense", "agility", "fire_bonus", "alchemy_bonus", "enabled", "is_builtin"):
            setattr(row, field, base[field])
        row.recipe_config = normalized_recipe
        row.drop_sources = normalized_sources
        row.version = version
        row.updated_at = utcnow()
        _sync_item_content_session(session, key, previous_recipe, previous_sources, normalized_recipe, normalized_sources)
        session.flush()
        snapshot = _item_definition_snapshot(row)
        session.add(
            DoupoItemDefinitionVersion(
                item_key=key,
                version=version,
                snapshot=snapshot,
                change_note=str(change_note or "保存物品定义")[:255],
                created_by=int(created_by) if created_by else None,
                created_at=utcnow(),
            )
        )
        session.query(DoupoInventoryItem).filter(DoupoInventoryItem.item_key == key).update(
            {
                DoupoInventoryItem.category: base["category"],
                DoupoInventoryItem.name: base["name"],
                DoupoInventoryItem.rarity: base["rarity"],
            },
            synchronize_session=False,
        )
        inventory_query = session.query(DoupoInventoryItem).filter(DoupoInventoryItem.item_key == key)
        if not slot or not enabled:
            inventory_query.update({DoupoInventoryItem.equipped_slot: None}, synchronize_session=False)
        else:
            equipped_rows = inventory_query.filter(DoupoInventoryItem.equipped_slot.isnot(None)).all()
            for inventory_row in equipped_rows:
                session.query(DoupoInventoryItem).filter(
                    DoupoInventoryItem.tg == int(inventory_row.tg),
                    DoupoInventoryItem.equipped_slot == slot,
                    DoupoInventoryItem.id != int(inventory_row.id),
                ).update({DoupoInventoryItem.equipped_slot: None}, synchronize_session=False)
                inventory_row.equipped_slot = slot
                inventory_row.updated_at = utcnow()
        session.commit()
    _invalidate_item_definition_cache()
    return get_item_definition(key)


def list_item_definition_versions(item_key: str) -> list[dict[str, Any]]:
    key = str(item_key or "").strip()
    with Session() as session:
        rows = (
            session.query(DoupoItemDefinitionVersion)
            .filter(DoupoItemDefinitionVersion.item_key == key)
            .order_by(DoupoItemDefinitionVersion.version.desc())
            .limit(100)
            .all()
        )
    return [
        {
            "id": int(row.id),
            "item_key": row.item_key,
            "version": int(row.version),
            "snapshot": dict(row.snapshot or {}),
            "change_note": row.change_note,
            "created_by": int(row.created_by) if row.created_by else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def admin_rollback_item_definition(item_key: str, version: int, *, created_by: int | None = None) -> dict[str, Any]:
    key = str(item_key or "").strip()
    with Session() as session:
        history = (
            session.query(DoupoItemDefinitionVersion)
            .filter(DoupoItemDefinitionVersion.item_key == key, DoupoItemDefinitionVersion.version == int(version))
            .first()
        )
        if history is None:
            raise ValueError("指定物品版本不存在")
        snapshot = dict(history.snapshot or {})
    return admin_upsert_item_definition(
        key,
        name=str(snapshot.get("name") or key),
        category=str(snapshot.get("category") or "token"),
        rarity=str(snapshot.get("rarity") or "凡品"),
        description=str(snapshot.get("description") or ""),
        icon=str(snapshot.get("icon") or ""),
        tradable=bool(snapshot.get("tradable", False)),
        stack_limit=max(_coerce_int(snapshot.get("stack_limit"), 9999), 1),
        equipment_slot=snapshot.get("equipment_slot"),
        attack=_coerce_int(snapshot.get("attack"), 0),
        defense=_coerce_int(snapshot.get("defense"), 0),
        agility=_coerce_int(snapshot.get("agility"), 0),
        fire_bonus=_coerce_int(snapshot.get("fire_bonus"), 0),
        alchemy_bonus=_coerce_int(snapshot.get("alchemy_bonus"), 0),
        recipe_config=dict(snapshot.get("recipe_config") or {}),
        drop_sources=list(snapshot.get("drop_sources") or []),
        enabled=bool(snapshot.get("enabled", True)),
        change_note=f"回滚到版本 v{int(version)}",
        created_by=created_by,
    )


def admin_archive_item_definition(item_key: str, *, created_by: int | None = None) -> dict[str, Any]:
    item = get_item_definition(item_key)
    return admin_upsert_item_definition(
        str(item["item_key"]),
        name=str(item["name"]),
        category=str(item["category"]),
        rarity=str(item["rarity"]),
        description=str(item.get("description") or ""),
        icon=str(item.get("icon") or ""),
        tradable=bool(item.get("tradable", False)),
        stack_limit=max(_coerce_int(item.get("stack_limit"), 9999), 1),
        equipment_slot=item.get("equipment_slot"),
        attack=_coerce_int(item.get("attack"), 0),
        defense=_coerce_int(item.get("defense"), 0),
        agility=_coerce_int(item.get("agility"), 0),
        fire_bonus=_coerce_int(item.get("fire_bonus"), 0),
        alchemy_bonus=_coerce_int(item.get("alchemy_bonus"), 0),
        recipe_config={},
        drop_sources=[],
        enabled=False,
        change_note="停用物品定义",
        created_by=created_by,
    )


def admin_grant_item(tg: int, item_key: str, quantity: int, *, created_by: int | None = None) -> dict[str, Any]:
    actor_tg = int(tg)
    amount = max(int(quantity or 0), 0)
    if amount <= 0:
        raise ValueError("发放数量必须大于 0")
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        if profile is None:
            raise ValueError("玩家尚未初始化斗破角色")
        granted = _grant_inventory_item_session(
            session,
            actor_tg,
            item_key,
            amount,
            item_meta={"last_granted_by": int(created_by) if created_by else None},
            strict_stack_limit=True,
        )
        session.add(
            DoupoJournal(
                tg=actor_tg,
                action_type="admin",
                title="后台发放物品",
                detail=f"{granted['name']} x{amount}",
            )
        )
        session.commit()
    return admin_get_player_bundle(actor_tg)


def _serialize_inventory_row(row: DoupoInventoryItem) -> dict[str, Any]:
    catalog = _catalog_item(str(row.item_key))
    category_key = str(catalog.get("category") or row.category or "token")
    category = _CATEGORY_LOOKUP.get(category_key) or _CATEGORY_LOOKUP.get("token") or {}
    return {
        "id": int(row.id),
        "tg": int(row.tg),
        "item_key": str(row.item_key),
        "category": category_key,
        "category_name": str(category.get("name") or category_key or "其他"),
        "name": str(catalog.get("name") or row.name or row.item_key),
        "rarity": str(catalog.get("rarity") or row.rarity or "凡品"),
        "quantity": int(row.quantity or 0),
        "description": str(catalog.get("description") or ""),
        "icon": str(catalog.get("icon") or ""),
        "tradable": bool(catalog.get("tradable", False)),
        "stack_limit": max(_coerce_int(catalog.get("stack_limit"), 9999), 1),
        "equipment": dict(catalog.get("equipment") or {}),
        "equipped": bool(row.equipped_slot),
        "equipped_slot": str(row.equipped_slot or "") or None,
        "equipped_slot_name": EQUIPMENT_SLOTS.get(str(row.equipped_slot or "")),
        "item_version": max(_coerce_int(catalog.get("version"), 1), 1),
        "enabled": bool(catalog.get("enabled", True)),
        "meta": dict(row.item_meta or {}),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _grant_inventory_item_session(
    session,
    tg: int,
    item_key: str,
    quantity: int,
    *,
    item_meta: dict[str, Any] | None = None,
    strict_stack_limit: bool = False,
) -> dict[str, Any] | None:
    qty = max(int(quantity or 0), 0)
    if qty <= 0:
        return None
    catalog = _catalog_item(item_key)
    if not bool(catalog.get("defined")):
        raise ValueError(f"未定义物品：{catalog['key']}")
    if not bool(catalog.get("enabled", True)):
        if strict_stack_limit:
            raise ValueError(f"{catalog['name']}当前已停用，无法继续发放")
        return None
    row = (
        session.query(DoupoInventoryItem)
        .filter(DoupoInventoryItem.tg == int(tg), DoupoInventoryItem.item_key == catalog["key"])
        .with_for_update()
        .first()
    )
    now = utcnow()
    if row is None:
        row = DoupoInventoryItem(
            tg=int(tg),
            item_key=catalog["key"],
            category=catalog["category"],
            name=catalog["name"],
            rarity=catalog["rarity"],
            quantity=0,
            item_meta=dict(item_meta or {}),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
    row.category = catalog["category"]
    row.name = catalog["name"]
    row.rarity = catalog["rarity"]
    current_quantity = max(int(row.quantity or 0), 0)
    stack_limit = max(_coerce_int(catalog.get("stack_limit"), 9999), 1)
    if current_quantity + qty > stack_limit:
        if strict_stack_limit:
            raise ValueError(f"{catalog['name']}堆叠上限为 {stack_limit}，当前已有 {current_quantity}")
        qty = max(stack_limit - current_quantity, 0)
        if qty <= 0:
            return None
    row.quantity = current_quantity + qty
    if item_meta:
        merged = dict(row.item_meta or {})
        merged.update(item_meta)
        row.item_meta = merged
    row.updated_at = now
    return {
        "item_key": catalog["key"],
        "name": catalog["name"],
        "category": catalog["category"],
        "category_name": str((_CATEGORY_LOOKUP.get(catalog["category"]) or {}).get("name") or catalog["category"]),
        "rarity": catalog["rarity"],
        "quantity": qty,
    }


def _consume_inventory_item_session(session, tg: int, item_key: str, quantity: int) -> dict[str, Any] | None:
    qty = max(int(quantity or 0), 0)
    if qty <= 0:
        return None
    catalog = _catalog_item(item_key)
    row = (
        session.query(DoupoInventoryItem)
        .filter(DoupoInventoryItem.tg == int(tg), DoupoInventoryItem.item_key == catalog["key"])
        .with_for_update()
        .first()
    )
    if row is None or int(row.quantity or 0) < qty:
        current = 0 if row is None else int(row.quantity or 0)
        raise ValueError(f"{catalog['name']}不足，需要 {qty}，当前 {current}")
    row.quantity = int(row.quantity or 0) - qty
    if int(row.quantity or 0) <= 0:
        row.equipped_slot = None
    row.updated_at = utcnow()
    return {
        "item_key": catalog["key"],
        "name": catalog["name"],
        "category": catalog["category"],
        "category_name": str((_CATEGORY_LOOKUP.get(catalog["category"]) or {}).get("name") or catalog["category"]),
        "rarity": catalog["rarity"],
        "quantity": -qty,
    }


def _inventory_item_quantity_session(session, tg: int, item_key: str) -> int:
    catalog = _catalog_item(item_key)
    row = (
        session.query(DoupoInventoryItem.quantity)
        .filter(DoupoInventoryItem.tg == int(tg), DoupoInventoryItem.item_key == catalog["key"])
        .first()
    )
    return max(int(row[0] or 0), 0) if row else 0


def grant_inventory_item(tg: int, item_key: str, quantity: int = 1) -> dict[str, Any] | None:
    with Session() as session:
        result = _grant_inventory_item_session(session, int(tg), item_key, quantity)
        session.commit()
        return result


def consume_inventory_item(tg: int, item_key: str, quantity: int = 1) -> dict[str, Any] | None:
    with Session() as session:
        result = _consume_inventory_item_session(session, int(tg), item_key, quantity)
        session.commit()
        return result


def list_player_inventory_grouped(tg: int) -> dict[str, Any]:
    with Session() as session:
        rows = (
            session.query(DoupoInventoryItem)
            .filter(DoupoInventoryItem.tg == int(tg), DoupoInventoryItem.quantity > 0)
            .order_by(DoupoInventoryItem.category.asc(), DoupoInventoryItem.updated_at.desc())
            .all()
        )
    equipment = _equipment_summary_from_rows(rows)
    grouped: dict[str, dict[str, Any]] = {}
    for category in INVENTORY_CATEGORIES:
        key = str(category.get("key") or "")
        grouped[key] = {
            "key": key,
            "name": str(category.get("name") or key),
            "description": str(category.get("description") or ""),
            "total_quantity": 0,
            "items": [],
        }
    for row in rows:
        item = _serialize_inventory_row(row)
        bucket = grouped.setdefault(
            item["category"],
            {
                "key": item["category"],
                "name": item["category_name"],
                "description": "",
                "total_quantity": 0,
                "items": [],
            },
        )
        bucket["items"].append(item)
        bucket["total_quantity"] += int(item["quantity"] or 0)
    categories = list(grouped.values())
    return {
        "categories": categories,
        "total_unique": sum(len(category["items"]) for category in categories),
        "total_quantity": sum(int(category["total_quantity"] or 0) for category in categories),
        "equipped_count": int(equipment.get("equipped_count") or 0),
        "equipment": equipment,
    }


def _equipment_summary_from_rows(rows: list[DoupoInventoryItem]) -> dict[str, Any]:
    equipped_rows = [row for row in rows if str(getattr(row, "equipped_slot", "") or "")]
    stats = {key: 0 for key in EQUIPMENT_STAT_LABELS}
    slots: dict[str, dict[str, Any] | None] = {key: None for key in EQUIPMENT_SLOTS}
    items: list[dict[str, Any]] = []
    for row in equipped_rows:
        slot = str(row.equipped_slot or "")
        catalog = _catalog_item(str(row.item_key))
        if slot not in EQUIPMENT_SLOTS or catalog.get("equipment_slot") != slot or int(row.quantity or 0) <= 0:
            continue
        item = _serialize_inventory_row(row)
        items.append(item)
        slots[slot] = item
        equipment = dict(catalog.get("equipment") or {})
        for key in stats:
            stats[key] += max(_coerce_int(equipment.get(key), 0), 0)
    battle_power_bonus = sum(int(stats[key]) * int(EQUIPMENT_STAT_WEIGHTS[key]) for key in stats)
    return {
        "slots": slots,
        "slot_labels": dict(EQUIPMENT_SLOTS),
        "items": items,
        "equipped_count": len(items),
        "stats": stats,
        "stat_labels": dict(EQUIPMENT_STAT_LABELS),
        "battle_power_bonus": battle_power_bonus,
    }


def get_equipment_summary(tg: int) -> dict[str, Any]:
    try:
        with Session() as session:
            rows = (
                session.query(DoupoInventoryItem)
                .filter(DoupoInventoryItem.tg == int(tg), DoupoInventoryItem.equipped_slot.isnot(None))
                .order_by(DoupoInventoryItem.equipped_slot.asc())
                .all()
            )
    except Exception:
        rows = []
    return _equipment_summary_from_rows(rows)


def equip_inventory_item(tg: int, item_key: str) -> dict[str, Any]:
    actor_tg = int(tg)
    key = str(item_key or "").strip()
    catalog = get_item_definition(key)
    if not bool(catalog.get("enabled", True)):
        raise ValueError("该物品已停用，无法穿戴")
    slot = str(catalog.get("equipment_slot") or "")
    if str(catalog.get("category") or "") != "gear" or slot not in EQUIPMENT_SLOTS:
        raise ValueError("该物品不是可穿戴装备")
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        if profile is None:
            raise ValueError("请先初始化斗破角色")
        row = (
            session.query(DoupoInventoryItem)
            .filter(DoupoInventoryItem.tg == actor_tg, DoupoInventoryItem.item_key == key)
            .with_for_update()
            .first()
        )
        if row is None or int(row.quantity or 0) <= 0:
            raise ValueError(f"背包中没有{catalog['name']}")
        session.query(DoupoInventoryItem).filter(
            DoupoInventoryItem.tg == actor_tg,
            DoupoInventoryItem.equipped_slot == slot,
            DoupoInventoryItem.id != int(row.id),
        ).update({DoupoInventoryItem.equipped_slot: None}, synchronize_session=False)
        row.equipped_slot = slot
        row.updated_at = utcnow()
        session.add(
            DoupoJournal(
                tg=actor_tg,
                action_type="equipment",
                title="穿戴装备",
                detail=f"{EQUIPMENT_SLOTS[slot]}：{catalog['name']}，战力加成 {_equipment_power_for_catalog(catalog)}",
            )
        )
        session.commit()
    profile = get_or_create_profile(actor_tg)
    return {
        "profile": profile,
        "inventory": list_player_inventory_grouped(actor_tg),
        "detail": f"⚔️ 已穿戴{catalog['name']}。",
    }


def unequip_inventory_item(tg: int, item_key: str) -> dict[str, Any]:
    actor_tg = int(tg)
    key = str(item_key or "").strip()
    with Session() as session:
        row = (
            session.query(DoupoInventoryItem)
            .filter(DoupoInventoryItem.tg == actor_tg, DoupoInventoryItem.item_key == key)
            .with_for_update()
            .first()
        )
        if row is None or not row.equipped_slot:
            raise ValueError("该物品当前未穿戴")
        catalog = _catalog_item(key)
        row.equipped_slot = None
        row.updated_at = utcnow()
        session.add(DoupoJournal(tg=actor_tg, action_type="equipment", title="卸下装备", detail=f"卸下{catalog['name']}"))
        session.commit()
    profile = get_or_create_profile(actor_tg)
    return {
        "profile": profile,
        "inventory": list_player_inventory_grouped(actor_tg),
        "detail": f"⚔️ 已卸下{catalog['name']}。",
    }


def _equipment_power_for_catalog(catalog: dict[str, Any]) -> int:
    equipment = dict(catalog.get("equipment") or {})
    return sum(max(_coerce_int(equipment.get(key), 0), 0) * weight for key, weight in EQUIPMENT_STAT_WEIGHTS.items())


def _get_or_create_economy_ledger_session(session, tg: int, day_key: str) -> DoupoEconomyLedger:
    row = (
        session.query(DoupoEconomyLedger)
        .filter(DoupoEconomyLedger.tg == int(tg), DoupoEconomyLedger.day_key == str(day_key))
        .with_for_update()
        .first()
    )
    if row is None:
        now = utcnow()
        row = DoupoEconomyLedger(
            tg=int(tg),
            day_key=str(day_key),
            gold_income=0,
            gold_sink=0,
            action_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError:
            # 并发首建：仅回滚保存点（不丢调用方同一事务的待提交改动），重查既有行。
            row = (
                session.query(DoupoEconomyLedger)
                .filter(DoupoEconomyLedger.tg == int(tg), DoupoEconomyLedger.day_key == str(day_key))
                .with_for_update()
                .first()
            )
    return row


def _serialize_economy_ledger(row: DoupoEconomyLedger | None, settings: dict[str, Any]) -> dict[str, Any]:
    cap = max(_coerce_int(settings.get("daily_gold_action_cap"), 650), 0)
    income = max(int(getattr(row, "gold_income", 0) or 0), 0)
    sink = max(int(getattr(row, "gold_sink", 0) or 0), 0)
    return {
        "day_key": str(getattr(row, "day_key", None) or _economy_day_key()),
        "daily_gold_action_cap": cap,
        "gold_income": income,
        "gold_sink": sink,
        "remaining_gold_income": max(cap - income, 0) if cap > 0 else None,
        "action_count": max(int(getattr(row, "action_count", 0) or 0), 0),
    }


def get_economy_snapshot(tg: int, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    day_key = _economy_day_key()
    with Session() as session:
        row = (
            session.query(DoupoEconomyLedger)
            .filter(DoupoEconomyLedger.tg == int(tg), DoupoEconomyLedger.day_key == day_key)
            .first()
        )
        return _serialize_economy_ledger(row, settings)


def _get_or_create_daily_counter_session(session, tg: int, day_key: str, action_type: str) -> DoupoDailyActionCounter:
    row = (
        session.query(DoupoDailyActionCounter)
        .filter(
            DoupoDailyActionCounter.tg == int(tg),
            DoupoDailyActionCounter.day_key == str(day_key),
            DoupoDailyActionCounter.action_type == str(action_type),
        )
        .with_for_update()
        .first()
    )
    if row is None:
        now = utcnow()
        row = DoupoDailyActionCounter(
            tg=int(tg),
            day_key=str(day_key),
            action_type=str(action_type),
            used_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError:
            # 并发首建：仅回滚保存点，重查既有计数行。
            row = (
                session.query(DoupoDailyActionCounter)
                .filter(
                    DoupoDailyActionCounter.tg == int(tg),
                    DoupoDailyActionCounter.day_key == str(day_key),
                    DoupoDailyActionCounter.action_type == str(action_type),
                )
                .with_for_update()
                .first()
            )
    return row


def _daily_limit_for_action_type(settings: dict[str, Any], action_type: str) -> int:
    if str(action_type or "") == "train":
        return max(_coerce_int(settings.get("daily_train_limit"), 5), 0)
    if str(action_type or "") == "expedition":
        return max(_coerce_int(settings.get("daily_expedition_limit"), 3), 0)
    raw_limits = settings.get("daily_action_limits")
    if isinstance(raw_limits, dict):
        return max(_coerce_int(raw_limits.get(str(action_type or "")), 0), 0)
    return 0


def _action_point_cost(settings: dict[str, Any], action_type: str) -> int:
    raw_costs = settings.get("action_point_costs")
    if not isinstance(raw_costs, dict):
        raw_costs = DEFAULT_ACTION_POINT_COSTS
    return max(_coerce_int(raw_costs.get(str(action_type or "")), 1), 0)


def _check_daily_action_points(
    session,
    tg: int,
    action_type: str,
    settings: dict[str, Any],
    now: datetime,
) -> tuple[DoupoDailyActionCounter, int, int]:
    counter = _get_or_create_daily_counter_session(
        session,
        int(tg),
        _economy_day_key(now),
        _ACTION_POINTS_COUNTER_KEY,
    )
    limit = max(_coerce_int(settings.get("daily_action_points"), 12), 0)
    cost = _action_point_cost(settings, action_type)
    if limit > 0 and int(counter.used_count or 0) + cost > limit:
        remaining = max(limit - int(counter.used_count or 0), 0)
        raise ValueError(f"今日行动力不足，需要 {cost} 点，当前剩余 {remaining} 点")
    return counter, limit, cost


def _consume_daily_action_points(counter: DoupoDailyActionCounter | None, cost: int) -> None:
    if counter is None or int(cost or 0) <= 0:
        return
    counter.used_count = int(counter.used_count or 0) + int(cost)
    counter.updated_at = utcnow()


def _check_daily_action_limit(
    session,
    tg: int,
    action_type: str,
    settings: dict[str, Any],
    now: datetime,
) -> tuple[DoupoDailyActionCounter, int]:
    counter = _get_or_create_daily_counter_session(session, int(tg), _economy_day_key(now), str(action_type or ""))
    limit = _daily_limit_for_action_type(settings, action_type)
    if limit > 0 and int(counter.used_count or 0) >= limit:
        raise ValueError(f"今日{ACTION_TYPE_LABELS.get(action_type, action_type)}次数已用完（{counter.used_count}/{limit}）")
    return counter, limit


def _increment_daily_action_counter(counter: DoupoDailyActionCounter | None) -> None:
    if counter is None:
        return
    counter.used_count = int(counter.used_count or 0) + 1
    counter.updated_at = utcnow()


def get_daily_action_usage(tg: int, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    day_key = _economy_day_key()
    with Session() as session:
        rows = (
            session.query(DoupoDailyActionCounter)
            .filter(DoupoDailyActionCounter.tg == int(tg), DoupoDailyActionCounter.day_key == day_key)
            .all()
        )
    usage: dict[str, dict[str, Any]] = {}
    for action_type in ACTION_TYPE_LABELS:
        limit = _daily_limit_for_action_type(settings, action_type)
        usage[action_type] = {
            "action_type": action_type,
            "label": ACTION_TYPE_LABELS.get(action_type, action_type),
            "used": 0,
            "limit": limit,
            "remaining": max(limit, 0) if limit > 0 else None,
        }
    action_points_used = 0
    douqi_income = 0
    for row in rows:
        action_type = str(row.action_type or "")
        if action_type == _ACTION_POINTS_COUNTER_KEY:
            action_points_used = max(int(row.used_count or 0), 0)
            continue
        if action_type == _DOUQI_INCOME_COUNTER_KEY:
            douqi_income = max(int(row.used_count or 0), 0)
            continue
        bucket = usage.setdefault(
            action_type,
            {
                "action_type": action_type,
                "label": ACTION_TYPE_LABELS.get(action_type, action_type),
                "used": 0,
                "limit": 0,
                "remaining": None,
            },
        )
        bucket["used"] = int(row.used_count or 0)
        limit = int(bucket.get("limit") or 0)
        bucket["remaining"] = max(limit - bucket["used"], 0) if limit > 0 else None
    action_points_limit = max(_coerce_int(settings.get("daily_action_points"), 12), 0)
    soft_cap = max(_coerce_int(settings.get("daily_douqi_soft_cap"), 250), 0)
    hard_cap = max(_coerce_int(settings.get("daily_douqi_hard_cap"), 400), 0)
    return {
        "day_key": day_key,
        "items": usage,
        "action_points": {
            "used": action_points_used,
            "limit": action_points_limit,
            "remaining": max(action_points_limit - action_points_used, 0) if action_points_limit > 0 else None,
        },
        "douqi_income": {
            "earned": douqi_income,
            "soft_cap": soft_cap,
            "hard_cap": hard_cap,
            "overflow_percent": min(max(_coerce_int(settings.get("daily_douqi_overflow_percent"), 20), 0), 100),
            "remaining_to_soft_cap": max(soft_cap - douqi_income, 0) if soft_cap > 0 else None,
            "remaining_to_hard_cap": max(hard_cap - douqi_income, 0) if hard_cap > 0 else None,
            "soft_capped": soft_cap > 0 and douqi_income >= soft_cap,
            "hard_capped": hard_cap > 0 and douqi_income >= hard_cap,
        },
    }


def list_sect_options() -> list[dict[str, Any]]:
    return [dict(item) for item in SECT_OPTIONS]


def _sect_option_by_name_or_key(value: str | None) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return _SECT_LOOKUP.get(raw) or _SECT_NAME_LOOKUP.get(raw)


def join_sect(tg: int, sect_key: str) -> dict[str, Any]:
    settings = get_settings()
    option = _SECT_LOOKUP.get(str(sect_key or "").strip())
    if option is None:
        raise ValueError("宗门不存在")
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == int(tg)).with_for_update().first()
        if profile is None:
            profile = _new_profile(int(tg))
            session.add(profile)
            session.flush()
        if profile.sect_name:
            raise ValueError(f"你已加入 {profile.sect_name}，如需更换请使用转宗（冷却与贡献保留受设置约束）。")
        stage_min = str(option.get("realm_stage_min") or "").strip()
        if stage_min and realm_rank(profile.realm_stage, settings.get("realm_thresholds") or []) < realm_rank(stage_min, settings.get("realm_thresholds") or []):
            raise ValueError(f"加入 {option['name']} 至少需要达到 {stage_min}")
        profile.sect_name = str(option["name"])
        profile.sect_contribution = max(int(profile.sect_contribution or 0), 10)
        profile.updated_at = utcnow()
        session.add(
            DoupoJournal(
                tg=int(tg),
                action_type="sect",
                title="加入宗门",
                detail=f"⛩️ 加入 {option['name']}，获得入门贡献 +10",
            )
        )
        session.commit()
        session.refresh(profile)
        profile_payload = serialize_profile(profile, settings)
    # 函数级延迟导入，避免与 sect_service 的模块级循环依赖。
    from bot.sql_helper.sql_doupo.sect_service import get_sect_panel  # noqa: PLC0415
    return {
        "profile": profile_payload,
        "sect": dict(option),
        "sect_panel": get_sect_panel(int(tg), settings, profile_payload),
        "growth": build_growth_snapshot(profile_payload, settings),
        "features": build_feature_overview(profile_payload),
        "inventory": list_player_inventory_grouped(int(tg)),
        "economy": get_economy_snapshot(int(tg), settings),
        "daily_usage": get_daily_action_usage(int(tg), settings),
        "journals": list_recent_journals(int(tg), limit=20),
    }


def ensure_default_actions() -> None:
    global _DEFAULT_ACTIONS_READY

    if _DEFAULT_ACTIONS_READY:
        return
    with _DEFAULT_ACTIONS_LOCK:
        if _DEFAULT_ACTIONS_READY:
            return
        with Session() as session:
            exists = {str(item.action_key): item for item in session.query(DoupoAction).all()}
            changed = False
            for item in DEFAULT_ACTIONS:
                key = str(item["action_key"])
                row = exists.get(key)
                if row is None:
                    session.add(DoupoAction(**item))
                    changed = True
                    continue
                if not row.name:
                    row.name = item["name"]
                    changed = True
                if not row.description:
                    row.description = item.get("description") or ""
                    changed = True
                if row.reward_config is None:
                    row.reward_config = item.get("reward_config") or {}
                    changed = True
                if row.requirement_config is None:
                    row.requirement_config = item.get("requirement_config") or {}
                    changed = True
                default_reward = dict(item.get("reward_config") or {})
                current_reward = dict(row.reward_config or {})
                default_version = max(
                    _coerce_int(default_reward.get("recipe_version"), 0),
                    _coerce_int(default_reward.get("drop_table_version"), 0),
                    _coerce_int(default_reward.get("balance_version"), 0),
                )
                current_version = max(
                    _coerce_int(current_reward.get("recipe_version"), 0),
                    _coerce_int(current_reward.get("drop_table_version"), 0),
                    _coerce_int(current_reward.get("balance_version"), 0),
                )
                if current_reward.get("managed_item_key"):
                    continue
                if default_version > 0 and current_version < default_version:
                    row.name = item["name"]
                    row.description = item.get("description") or ""
                    row.action_type = item.get("action_type") or row.action_type
                    row.cooldown_seconds = item.get("cooldown_seconds") or row.cooldown_seconds
                    row.reward_config = default_reward
                    row.requirement_config = item.get("requirement_config") or {}
                    row.sort_order = item.get("sort_order") or row.sort_order
                    changed = True
                    continue
                for merge_key in ("item_drops", "item_costs"):
                    if merge_key in default_reward and merge_key not in current_reward:
                        current_reward[merge_key] = default_reward[merge_key]
                        row.reward_config = current_reward
                        changed = True
            # 检测重复 sort_order：自动 +1 偏移直到唯一，避免行动排序错乱。
            rows_by_order: dict[int, list[DoupoAction]] = {}
            for row in session.query(DoupoAction).order_by(DoupoAction.sort_order.asc(), DoupoAction.id.asc()).all():
                rows_by_order.setdefault(int(row.sort_order or 0), []).append(row)
            used_orders: set[int] = set()
            for order, same_order_rows in rows_by_order.items():
                if order not in used_orders:
                    used_orders.add(order)
                for row in same_order_rows[1:]:
                    new_order = order + 1
                    while new_order in used_orders:
                        new_order += 1
                    row.sort_order = new_order
                    used_orders.add(new_order)
                    changed = True
                    logger.warning(
                        f"doupo ensure_default_actions: 修复重复 sort_order {order} → {new_order}（{row.action_key}）"
                    )
            if changed:
                session.commit()
        _DEFAULT_ACTIONS_READY = True
    _log_undefined_action_references()


def _log_undefined_action_references() -> None:
    """启动时校验全部 DEFAULT_ACTIONS 的物品引用，未定义/停用的列出告警（不抛错）。"""
    problems: list[str] = []
    for item in DEFAULT_ACTIONS:
        key = str(item.get("action_key") or "?")
        reward = dict(item.get("reward_config") or {})
        for drop in reward.get("item_drops") or []:
            if not isinstance(drop, dict):
                continue
            drop_key = str(drop.get("item_key") or drop.get("key") or "").strip()
            if not drop_key:
                continue
            catalog = _catalog_item(drop_key)
            if not bool(catalog.get("defined")):
                problems.append(f"[{key}] 掉落物品未定义：{drop_key}")
            elif not bool(catalog.get("enabled", True)):
                problems.append(f"[{key}] 掉落物品已停用：{drop_key}")
        for cost_key in _normalize_item_costs(reward.get("item_costs")):
            catalog = _catalog_item(cost_key)
            if not bool(catalog.get("defined")):
                problems.append(f"[{key}] 消耗物品未定义：{cost_key}")
    if problems:
        for problem in problems:
            logger.warning(f"doupo default action reference: {problem}")


def list_actions(*, enabled_only: bool = True) -> list[dict[str, Any]]:
    ensure_default_actions()
    with Session() as session:
        query = session.query(DoupoAction)
        if enabled_only:
            query = query.filter(DoupoAction.enabled.is_(True))
        rows = query.order_by(DoupoAction.sort_order.asc(), DoupoAction.id.asc()).all()
    return [serialize_action(row) for row in rows]


def serialize_action(row: DoupoAction) -> dict[str, Any]:
    action_type = str(row.action_type or "train")
    return {
        "id": int(row.id),
        "action_key": str(row.action_key),
        "name": str(row.name),
        "description": str(row.description or ""),
        "action_type": action_type,
        "action_type_label": ACTION_TYPE_LABELS.get(action_type, action_type),
        "cooldown_seconds": int(row.cooldown_seconds or 0),
        "reward_config": dict(row.reward_config or {}),
        "requirement_config": dict(row.requirement_config or {}),
        "enabled": bool(row.enabled),
        "sort_order": int(row.sort_order or 0),
    }


def _decorate_player_action_state(
    session,
    profile: DoupoProfile,
    action: DoupoAction,
    settings: dict[str, Any],
    usage: dict[str, Any],
    inventory_quantities: dict[str, int],
) -> dict[str, Any]:
    item = serialize_action(action)
    reasons: list[str] = []
    ok, reason = _check_action_requirement(session, profile, action, settings, inventory_quantities)
    if not ok and reason:
        reasons.append(reason)
    cooldown_ok, cooldown_remain = _check_action_cooldown(profile, action)
    if not cooldown_ok:
        reasons.append(f"冷却中，请等待 {cooldown_remain} 秒")
    action_type = str(action.action_type or "train")
    usage_items = usage.get("items") if isinstance(usage.get("items"), dict) else usage
    usage_row = dict((usage_items or {}).get(action_type) or {})
    limit = max(_coerce_int(usage_row.get("limit"), 0), 0)
    used = max(_coerce_int(usage_row.get("used"), 0), 0)
    if limit > 0 and used >= limit:
        reasons.append(f"今日{ACTION_TYPE_LABELS.get(action_type, action_type)}次数已用完（{used}/{limit}）")
    point_usage = dict(usage.get("action_points") or {})
    point_cost = _action_point_cost(settings, action_type)
    point_remaining = point_usage.get("remaining")
    if point_remaining is not None and int(point_remaining) < point_cost:
        reasons.append(f"今日行动力不足，需要 {point_cost} 点，当前剩余 {int(point_remaining)} 点")
    breakthrough = None
    if action_type == "breakthrough":
        breakthrough = _breakthrough_state(session, profile, settings, inventory_quantities)
        item["reward_config"] = {
            **dict(item.get("reward_config") or {}),
            "gold_cost": int(breakthrough["gold_cost"]),
            "success_percent": int(breakthrough["success_percent"]),
            "item_costs": dict(breakthrough["item_costs"]),
        }
        item["requirement_summary"] = (
            f"{breakthrough['stage']} {breakthrough['star_cap']} 星且斗气圆满"
        )
    item.update(
        {
            "available": not reasons,
            "disabled_reason": reasons[0] if reasons else "",
            "disabled_reasons": reasons,
            "cooldown_remaining": int(cooldown_remain or 0),
            "daily_used": used,
            "daily_limit": limit,
            "action_point_cost": point_cost,
            "action_points_remaining": point_remaining,
            "breakthrough": breakthrough,
        }
    )
    return item


def list_player_actions(tg: int, *, enabled_only: bool = True) -> list[dict[str, Any]]:
    ensure_default_actions()
    actor_tg = int(tg)
    settings = get_settings()
    daily_usage = get_daily_action_usage(actor_tg, settings)
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).first()
        profile_created = profile is None
        if profile is None:
            profile = _new_profile(actor_tg)
            session.add(profile)
            session.flush()
        query = session.query(DoupoAction)
        if enabled_only:
            query = query.filter(DoupoAction.enabled.is_(True))
        rows = query.order_by(DoupoAction.sort_order.asc(), DoupoAction.id.asc()).all()
        cost_keys = {
            item_key
            for row in rows
            for item_key, _quantity in _normalize_item_costs(dict(row.reward_config or {}).get("item_costs"))
        }
        cost_keys.update(
            item_key
            for row in rows
            if str(row.action_type or "") in {"alchemy", "craft"}
            for item_key in _guaranteed_item_outputs(dict(row.reward_config or {}))
        )
        cost_keys.update(
            item_key
            for item_key, _quantity in _normalize_item_costs(_breakthrough_rule(profile, settings).get("item_costs"))
        )
        inventory_quantities: dict[str, int] = {}
        if cost_keys:
            inventory_quantities = {
                str(item_key): max(int(quantity or 0), 0)
                for item_key, quantity in (
                    session.query(DoupoInventoryItem.item_key, DoupoInventoryItem.quantity)
                    .filter(DoupoInventoryItem.tg == actor_tg, DoupoInventoryItem.item_key.in_(cost_keys))
                    .all()
                )
            }
        actions = [
            _decorate_player_action_state(session, profile, row, settings, daily_usage, inventory_quantities)
            for row in rows
        ]
        if profile_created:
            session.commit()
    return actions


def _apply_realm_progress(profile: DoupoProfile, settings: dict[str, Any]) -> None:
    thresholds = settings.get("realm_thresholds") or []
    if not isinstance(thresholds, list) or not thresholds:
        return
    current_stage = str(profile.realm_stage or "斗之气")
    current_star = max(int(profile.realm_stars or 1), 1)
    current_douqi = max(int(profile.douqi or 0), 0)
    stage_idx = resolve_stage_index(current_stage, thresholds)
    star_cap = max(_coerce_int(thresholds[stage_idx].get("star_cap"), 9), 1)
    douqi_per_star = max(_coerce_int(thresholds[stage_idx].get("douqi_per_star"), 100), 1)

    current_star = min(current_star, star_cap)
    while current_star < star_cap and current_douqi >= douqi_per_star:
        current_douqi -= douqi_per_star
        current_star += 1
    if current_star >= star_cap:
        # 终境也允许修满到 douqi_per_star（斗帝圆满），不再钳到 per_star-1。
        max_douqi = douqi_per_star
        current_douqi = min(current_douqi, max(max_douqi, 0))
    profile.realm_stage = current_stage
    profile.realm_stars = current_star
    profile.douqi = current_douqi


def _settle_realm_change(profile: DoupoProfile, old_stage: str) -> None:
    """境界变更统一收口：仅在境界名真正改变时清零突破失败计数。

    旧逻辑在突破成功与后台改境界的各路径手工归零，容易遗漏；这里集中处理。
    """
    if str(profile.realm_stage or "") != str(old_stage or ""):
        profile.breakthrough_failures = 0


def _breakthrough_rule(profile: DoupoProfile, settings: dict[str, Any]) -> dict[str, Any]:
    thresholds = settings.get("realm_thresholds") or []
    stage = str(profile.realm_stage or "斗之气")
    stage_idx = resolve_stage_index(stage, thresholds)
    row = thresholds[stage_idx] if thresholds else {}
    next_row = thresholds[stage_idx + 1] if thresholds and stage_idx + 1 < len(thresholds) else None
    configured = dict(BREAKTHROUGH_RULES.get(stage) or BREAKTHROUGH_RULES.get(str(stage).split("·")[0]) or {})
    return {
        "stage": stage,
        "next_stage": None if next_row is None else str(next_row.get("stage") or ""),
        "star_cap": max(_coerce_int(row.get("star_cap"), 9), 1),
        "douqi_required": max(_coerce_int(row.get("douqi_per_star"), 100), 1),
        "gold_cost": max(_coerce_int(configured.get("gold_cost"), 0), 0),
        "success_percent": min(max(_coerce_int(configured.get("success_percent"), 50), 1), 95),
        "pity_after": max(_coerce_int(configured.get("pity_after"), 4), 1),
        "item_costs": dict(configured.get("item_costs") or {}),
    }


def _breakthrough_state(
    session,
    profile: DoupoProfile,
    settings: dict[str, Any],
    inventory_quantities: dict[str, int] | None = None,
) -> dict[str, Any]:
    rule = _breakthrough_rule(profile, settings)
    failures = max(int(getattr(profile, "breakthrough_failures", 0) or 0), 0)
    reasons: list[str] = []
    if not rule["next_stage"]:
        reasons.append("当前已到达开放境界上限")
    if int(profile.realm_stars or 1) < int(rule["star_cap"]):
        reasons.append(f"需要达到 {rule['stage']} {rule['star_cap']} 星")
    if int(profile.douqi or 0) < int(rule["douqi_required"]):
        reasons.append(f"斗气尚未圆满，还需 {max(int(rule['douqi_required']) - int(profile.douqi or 0), 0)}")
    if int(profile.gold or 0) < int(rule["gold_cost"]):
        reasons.append(f"金币不足，需要 {rule['gold_cost']}")

    costs = _normalize_item_costs(rule["item_costs"])
    quantities = inventory_quantities
    if quantities is None:
        keys = [item_key for item_key, _quantity in costs]
        quantities = {
            str(item_key): max(int(quantity or 0), 0)
            for item_key, quantity in (
                session.query(DoupoInventoryItem.item_key, DoupoInventoryItem.quantity)
                .filter(DoupoInventoryItem.tg == int(profile.tg), DoupoInventoryItem.item_key.in_(keys))
                .all()
            )
        } if keys else {}
    for item_key, quantity in costs:
        current = max(int((quantities or {}).get(item_key) or 0), 0)
        if current < quantity:
            catalog = _catalog_item(item_key)
            reasons.append(f"{catalog['name']}不足，需要 {quantity}，当前 {current}")

    base_success = int(rule["success_percent"])
    growth_bonus = min(
        int(profile.fire_seed or 0) // 240
        + int(profile.alchemy_exp or 0) // 480
        + int(getattr(profile, "fire_rank", 0) or 0) * 2,
        15,
    )
    # 帝流丹：临时 +5% 成功率（一次性，仅在成功突破时消耗）；定境丹：失败斗气损失减半（失败时消耗）。
    has_emperor_pill = int((quantities or {}).get("emperor_flow_pill") or 0) > 0
    has_stabilizing_pill = int((quantities or {}).get("realm_stabilizing_pill") or 0) > 0
    pill_bonus = 5 if has_emperor_pill else 0
    success_percent = min(base_success + growth_bonus + pill_bonus, 95)
    pity_ready = failures + 1 >= int(rule["pity_after"])
    return {
        **rule,
        "failures": failures,
        "success_percent": 100 if pity_ready else success_percent,
        "base_success_percent": base_success,
        "pity_ready": pity_ready,
        "remaining_attempts_to_pity": max(int(rule["pity_after"]) - failures, 0),
        "available": not reasons,
        "disabled_reason": reasons[0] if reasons else "",
        "disabled_reasons": reasons,
        # 加成丹状态（P1）：仅供前端展示与结果播报，实际消耗在突破结算分支处理。
        "pill_bonus": pill_bonus,
        "has_emperor_pill": has_emperor_pill,
        "has_stabilizing_pill": has_stabilizing_pill,
    }


def _check_action_requirement(
    session,
    profile: DoupoProfile,
    action: DoupoAction,
    settings: dict[str, Any],
    inventory_quantities: dict[str, int] | None = None,
) -> tuple[bool, str]:
    req = dict(action.requirement_config or {})
    reward = dict(action.reward_config or {})
    thresholds = settings.get("realm_thresholds") or []
    action_type = str(action.action_type or "")
    if action_type == "breakthrough":
        state = _breakthrough_state(session, profile, settings, inventory_quantities)
        return bool(state["available"]), str(state["disabled_reason"] or "")
    if action_type in {"sect", "technique"} and not profile.sect_name:
        return False, "请先选择加入宗门"
    if bool(req.get("sect_required")) and not profile.sect_name:
        return False, "请先选择加入宗门"
    sect_name = str(req.get("sect_name") or "").strip()
    if sect_name and str(profile.sect_name or "") != sect_name:
        return False, f"需要加入 {sect_name}"
    stage_min = str(req.get("realm_stage_min") or "").strip()
    if stage_min and realm_rank(profile.realm_stage, thresholds) < realm_rank(stage_min, thresholds):
        return False, f"至少需要达到 {stage_min}"
    stars_min = max(_coerce_int(req.get("realm_stars_min"), 0), 0)
    if stars_min > 0 and int(profile.realm_stars or 1) < stars_min:
        return False, f"至少需要 {stars_min} 星才能执行"
    checks = {
        "gold_min": ("金币", int(profile.gold or 0)),
        "alchemy_min": ("炼药经验", int(profile.alchemy_exp or 0)),
        "fire_min": ("异火火候", int(profile.fire_seed or 0)),
        "core_min": ("魔核", int(profile.beast_core or 0)),
        "sect_contribution_min": ("宗门贡献", int(profile.sect_contribution or 0)),
        "pill_min": ("丹药", int(profile.pill_stock or 0)),
        "technique_level_min": ("斗技等级", int(profile.technique_level or 0)),
        "fire_progress_min": ("异火线索", int(profile.fire_progress or 0)),
        "method_level_min": ("焚诀等级", int(getattr(profile, "method_level", 0) or 0)),
        "fire_rank_min": ("异火掌控", int(getattr(profile, "fire_rank", 0) or 0)),
        "academy_fire_energy_min": ("火能", int(getattr(profile, "academy_fire_energy", 0) or 0)),
        "faction_reputation_min": ("阵营声望", int(getattr(profile, "faction_reputation", 0) or 0)),
        "black_corner_infamy_min": ("黑角域恶名", int(getattr(profile, "black_corner_infamy", 0) or 0)),
        "pet_level_min": ("伙伴等级", int(getattr(profile, "pet_level", 0) or 0)),
        "boss_score_min": ("Boss 战绩", int(profile.boss_score or 0)),
        "tower_floor_min": ("塔层", int(profile.tower_floor or 0)),
        "auction_credit_min": ("拍卖声望", int(profile.auction_credit or 0)),
    }
    for key, (label, current) in checks.items():
        required = max(_coerce_int(req.get(key), 0), 0)
        if required > 0 and current < required:
            return False, f"需要{label} >= {required}"
    for item_key, quantity in _normalize_item_costs(reward.get("item_costs")):
        if inventory_quantities is None:
            current = _inventory_item_quantity_session(session, int(profile.tg), item_key)
        else:
            current = max(int(inventory_quantities.get(str(item_key), 0) or 0), 0)
        if current >= quantity:
            continue
        catalog = _catalog_item(item_key)
        if action_type == "alchemy":
            return False, f"丹方材料不足：{catalog['name']} {current}/{quantity}。请先外出历练获取材料。"
        return False, f"{catalog['name']}不足，需要 {quantity}，当前 {current}"
    if action_type in {"alchemy", "craft"}:
        item_costs: dict[str, int] = {}
        for cost_key, cost_quantity in _normalize_item_costs(reward.get("item_costs")):
            item_costs[cost_key] = item_costs.get(cost_key, 0) + cost_quantity
        # 校验全部掉落引用（含非 100% 概率），避免炸事务/产出死物品
        all_drops = reward.get("item_drops")
        if isinstance(all_drops, list):
            for drop in all_drops:
                if not isinstance(drop, dict):
                    continue
                drop_key = str(drop.get("item_key") or drop.get("key") or "").strip()
                if not drop_key:
                    continue
                drop_catalog = _catalog_item(drop_key)
                if not bool(drop_catalog.get("defined")):
                    return False, f"掉落物品未定义：{drop_key}"
                if not bool(drop_catalog.get("enabled", True)):
                    return False, f"掉落物品 {drop_catalog['name']} 已停用"
        for item_key, quantity in _guaranteed_item_outputs(reward).items():
            catalog = _catalog_item(item_key)
            if not bool(catalog.get("defined")):
                return False, f"制作产物未定义：{item_key}"
            if not bool(catalog.get("enabled", True)):
                return False, f"制作产物 {catalog['name']} 已停用"
            if inventory_quantities is None:
                current = _inventory_item_quantity_session(session, int(profile.tg), item_key)
            else:
                current = max(int(inventory_quantities.get(item_key, 0) or 0), 0)
            quantity_after_cost = max(current - max(int(item_costs.get(item_key, 0)), 0), 0)
            stack_limit = max(_coerce_int(catalog.get("stack_limit"), 9999), 1)
            if quantity_after_cost + quantity > stack_limit:
                available = max(stack_limit - quantity_after_cost, 0)
                return False, f"{catalog['name']}空间不足，最多还能制作 {available} 个"
    return True, ""


def _set_action_cooldown(profile: DoupoProfile, action_key: str, now: datetime) -> None:
    """按 action_key 写入逐行动冷却时间戳（JSON 列需整体赋值才能被 SQLAlchemy 捕获变更）。"""
    cooldown_map = dict(profile.cooldown_map or {})
    cooldown_map[str(action_key)] = now.isoformat()
    profile.cooldown_map = cooldown_map


def _check_action_cooldown(profile: DoupoProfile, action: DoupoAction) -> tuple[bool, int]:
    cooldown = max(int(action.cooldown_seconds or 0), 0)
    if cooldown <= 0:
        return True, 0
    now = utcnow()
    stored = (profile.cooldown_map or {}).get(str(action.action_key))
    if not stored:
        return True, 0
    try:
        base_time = datetime.fromisoformat(str(stored))
    except (TypeError, ValueError):
        return True, 0
    remain = int((base_time + timedelta(seconds=cooldown) - now).total_seconds())
    return remain <= 0, max(remain, 0)


def _apply_resource_delta(profile: DoupoProfile, field: str, delta: int) -> int:
    current = int(getattr(profile, field) or 0)
    updated = min(max(current + int(delta or 0), 0), _INT32_MAX)
    setattr(profile, field, updated)
    return updated - current


def _apply_douqi_delta_with_balance(
    session,
    profile: DoupoProfile,
    delta: int,
    settings: dict[str, Any],
    result: dict[str, Any] | None = None,
) -> int:
    amount = int(delta or 0)
    if amount <= 0:
        return _apply_resource_delta(profile, "douqi", amount)

    counter = _get_or_create_daily_counter_session(
        session,
        int(profile.tg),
        _economy_day_key(),
        _DOUQI_INCOME_COUNTER_KEY,
    )
    earned = max(int(counter.used_count or 0), 0)
    soft_cap = max(_coerce_int(settings.get("daily_douqi_soft_cap"), 250), 0)
    hard_cap = max(_coerce_int(settings.get("daily_douqi_hard_cap"), 400), 0)
    overflow_percent = min(max(_coerce_int(settings.get("daily_douqi_overflow_percent"), 20), 0), 100)

    full_rate_amount = amount
    overflow_amount = 0
    if soft_cap > 0:
        full_rate_amount = min(amount, max(soft_cap - earned, 0))
        overflow_amount = max(amount - full_rate_amount, 0)
    reduced_overflow = overflow_amount * overflow_percent // 100
    balanced_amount = full_rate_amount + reduced_overflow
    if hard_cap > 0:
        balanced_amount = min(balanced_amount, max(hard_cap - earned, 0))

    bottleneck_reduced = 0
    perfected_discarded = 0
    thresholds = settings.get("realm_thresholds") or []
    if thresholds:
        stage_idx = realm_rank(str(profile.realm_stage or "斗之气"), thresholds)
        row = thresholds[stage_idx]
        star_cap = max(_coerce_int(row.get("star_cap"), 9), 1)
        per_star = max(_coerce_int(row.get("douqi_per_star"), 100), 1)
        current_star = min(max(int(profile.realm_stars or 1), 1), star_cap)
        current_douqi = max(int(profile.douqi or 0), 0)
        has_next_stage = stage_idx + 1 < len(thresholds)
        final_bar_capacity = per_star  # 允许终境修满到 per_star（斗帝圆满），消除 11999 死资源
        useful_capacity = max((star_cap - current_star) * per_star + final_bar_capacity - current_douqi, 0)
        before_bottleneck = balanced_amount
        balanced_amount = min(balanced_amount, useful_capacity)
        bottleneck_reduced = max(before_bottleneck - balanced_amount, 0)
        if result is not None and not has_next_stage:
            will_reach = current_douqi + balanced_amount >= per_star
            result["realm_perfected"] = will_reach
            if will_reach:
                # 斗帝圆满：满 12000 后多余斗气直接丢弃并播报「帝位圆满」，不再计入「境界瓶颈未吸收」。
                perfected_discarded = bottleneck_reduced
                bottleneck_reduced = 0

    actual = _apply_resource_delta(profile, "douqi", balanced_amount)
    if actual > 0:
        counter.used_count = earned + actual
        counter.updated_at = utcnow()
    if result is not None:
        reduced = max(amount - max(actual, 0) - bottleneck_reduced - perfected_discarded, 0)
        result["douqi_capped_delta"] = int(result.get("douqi_capped_delta") or 0) + reduced
        result["douqi_bottleneck_delta"] = int(result.get("douqi_bottleneck_delta") or 0) + bottleneck_reduced
        result["realm_perfected_discarded"] = int(result.get("realm_perfected_discarded") or 0) + perfected_discarded
        result["douqi_soft_capped"] = bool(soft_cap > 0 and earned + max(actual, 0) >= soft_cap)
        result["douqi_hard_capped"] = bool(hard_cap > 0 and earned + max(actual, 0) >= hard_cap)
        result["daily_douqi_income"] = earned + max(actual, 0)
    return actual


def _normalize_item_costs(value: Any) -> list[tuple[str, int]]:
    if not value:
        return []
    rows: list[tuple[str, int]] = []
    if isinstance(value, dict):
        iterable = value.items()
        for item_key, quantity in iterable:
            qty = max(_coerce_int(quantity, 0), 0)
            if item_key and qty > 0:
                rows.append((str(item_key), qty))
        return rows
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            item_key = str(item.get("item_key") or item.get("key") or "").strip()
            qty = max(_coerce_int(item.get("quantity") or item.get("qty"), 0), 0)
            if item_key and qty > 0:
                rows.append((item_key, qty))
    return rows


def _guaranteed_item_outputs(reward: dict[str, Any]) -> dict[str, int]:
    outputs: dict[str, int] = {}
    drops = reward.get("item_drops")
    if not isinstance(drops, list):
        return outputs
    for drop in drops:
        if not isinstance(drop, dict):
            continue
        item_key = str(drop.get("item_key") or drop.get("key") or "").strip()
        chance = min(max(_coerce_int(drop.get("chance"), 100), 0), 100)
        if not item_key or chance < 100:
            continue
        minimum = max(_coerce_int(drop.get("min", drop.get("quantity_min", 1)), 1), 0)
        maximum = max(_coerce_int(drop.get("max", drop.get("quantity_max", minimum)), minimum), minimum)
        if maximum > 0:
            outputs[item_key] = outputs.get(item_key, 0) + maximum
    return outputs


def _spend_inventory_costs(session, profile: DoupoProfile, reward: dict[str, Any], result: dict[str, Any]) -> None:
    for item_key, quantity in _normalize_item_costs(reward.get("item_costs")):
        consumed = _consume_inventory_item_session(session, int(profile.tg), item_key, quantity)
        if consumed:
            result["items_delta"].append(consumed)


def _apply_gold_delta_with_economy(
    profile: DoupoProfile,
    delta: int,
    ledger: DoupoEconomyLedger | None,
    settings: dict[str, Any],
    result: dict[str, Any],
) -> int:
    amount = int(delta or 0)
    if amount == 0:
        return 0
    if amount > 0:
        cap = max(_coerce_int(settings.get("daily_gold_action_cap"), 650), 0)
        allowed = amount
        if ledger is not None and cap > 0:
            remaining = max(cap - int(ledger.gold_income or 0), 0)
            allowed = min(amount, remaining)
        actual = _apply_resource_delta(profile, "gold", allowed)
        if ledger is not None and actual > 0:
            ledger.gold_income = int(ledger.gold_income or 0) + actual
            ledger.updated_at = utcnow()
        capped = max(amount - max(actual, 0), 0)
        if capped:
            result["gold_capped_delta"] += capped
            result["economy_capped"] = True
        return actual
    actual = _apply_resource_delta(profile, "gold", amount)
    if ledger is not None and actual < 0:
        ledger.gold_sink = int(ledger.gold_sink or 0) + abs(actual)
        ledger.updated_at = utcnow()
    return actual


def _spend_action_costs(
    session,
    profile: DoupoProfile,
    reward: dict[str, Any],
    result: dict[str, Any],
    ledger: DoupoEconomyLedger | None,
    settings: dict[str, Any],
) -> None:
    _spend_inventory_costs(session, profile, reward, result)
    costs = {
        "gold_cost": ("gold", "gold_delta", "金币"),
        "core_cost": ("beast_core", "core_delta", "魔核"),
        "pill_cost": ("pill_stock", "pill_delta", "丹药"),
        "contribution_cost": ("sect_contribution", "sect_delta", "宗门贡献"),
        "auction_cost": ("auction_credit", "auction_delta", "拍卖声望"),
        "fire_energy_cost": ("academy_fire_energy", "fire_energy_delta", "火能"),
        "faction_cost": ("faction_reputation", "faction_delta", "阵营声望"),
        "infamy_cost": ("black_corner_infamy", "infamy_delta", "黑角域恶名"),
    }
    for key, (field, result_key, label) in costs.items():
        cost = max(_coerce_int(reward.get(key), 0), 0)
        if cost <= 0:
            continue
        if int(getattr(profile, field) or 0) < cost:
            raise ValueError(f"{label}不足，需要 {cost}")
        if field == "gold":
            result[result_key] += _apply_gold_delta_with_economy(profile, -cost, ledger, settings, result)
        else:
            result[result_key] += _apply_resource_delta(profile, field, -cost)


def _apply_feature_side_effects(profile: DoupoProfile, action_type: str, result: dict[str, Any]) -> None:
    if action_type == "technique" and int(profile.technique_level or 0) > 0 and not profile.technique_key:
        profile.technique_key = "octane_burst"
    if action_type == "fire":
        # 按 HEAVENLY_FIRES 进度阈值取当前可达的最高火种，已达更高火种即升级收服（不再只收第一次）。
        progress = int(profile.fire_progress or 0)
        target = None
        for row in HEAVENLY_FIRES:
            if progress >= int(row.get("progress") or 0):
                target = row
        target_name = str((target or {}).get("name") or "").strip()
        current_name = str(profile.fire_name or "").strip()
        if target_name and target_name != current_name:
            profile.fire_name = target_name
            result["captured_fire"] = target_name
            result["fire_delta"] += _apply_resource_delta(profile, "fire_seed", 20)
    if action_type == "tower":
        raw_floor = int(profile.tower_floor or 0)
        capped_floor = min(max(raw_floor, 0), 99)
        if capped_floor != raw_floor:
            profile.tower_floor = capped_floor
            lost = max(raw_floor - capped_floor, 0)
            if lost:
                # 封顶损失量单独记录供展示「塔层已至 99」，并修正 tower_delta 为真实进账。
                result["tower_capped_delta"] = lost
                prior_delta = max(int(result.get("tower_delta", 0) or 0), 0)
                result["tower_delta"] = max(prior_delta - lost, 0)
    if int(getattr(profile, "method_level", 0) or 0) > 0 and not profile.technique_key:
        # 焚诀进阶但未学任何斗技时，补目录内斗技（TECHNIQUES[0]），不再写入目录外 key。
        profile.technique_key = str(TECHNIQUES[0]["key"])


def _roll_item_drop_quantity(drop: dict[str, Any]) -> int:
    low = max(_coerce_int(drop.get("min") if "min" in drop else drop.get("quantity_min"), 1), 0)
    high = max(_coerce_int(drop.get("max") if "max" in drop else drop.get("quantity_max"), low), 0)
    if high <= 0:
        return 0
    return random.randint(min(low, high), max(low, high))


def _douqi_training_bonus(profile: DoupoProfile, action_type: str, base: int) -> int:
    amount = int(base or 0)
    if amount <= 0 or action_type not in {"train", "tower", "fire"}:
        return amount
    method_level = max(int(getattr(profile, "method_level", 0) or 0), 0)
    fire_rank = max(int(getattr(profile, "fire_rank", 0) or 0), 0)
    fire_seed = max(int(profile.fire_seed or 0), 0)
    equipment = get_equipment_summary(int(profile.tg)).get("stats") or {}
    fire_equipment_bonus = max(_coerce_int(equipment.get("fire_bonus"), 0), 0)
    bonus_percent = min(method_level * 4 + fire_rank * 6 + fire_seed // 160 + fire_equipment_bonus, 100)
    return amount + (amount * bonus_percent // 100)


def _apply_configured_item_drops(session, profile: DoupoProfile, reward: dict[str, Any], result: dict[str, Any]) -> None:
    drops = reward.get("item_drops")
    if not isinstance(drops, list):
        return
    for drop in drops:
        if not isinstance(drop, dict):
            continue
        item_key = str(drop.get("item_key") or drop.get("key") or "").strip()
        if not item_key:
            continue
        catalog = _catalog_item(item_key)
        # 防御式：未定义/已停用的物品直接跳过，避免中途炸整个行动事务。
        if not bool(catalog.get("defined")) or not bool(catalog.get("enabled", True)):
            continue
        chance = min(max(_coerce_int(drop.get("chance"), 100), 0), 100)
        if chance < 100 and random.randint(1, 100) > chance:
            continue
        quantity = _roll_item_drop_quantity(drop)
        granted = _grant_inventory_item_session(session, int(profile.tg), item_key, quantity)
        if granted:
            result["items_delta"].append(granted)


def _refund_consumed_items_session(session, profile: DoupoProfile, result: dict[str, Any], refund_percent: int) -> None:
    percent = min(max(_coerce_int(refund_percent, 0), 0), 100)
    if percent <= 0:
        return
    consumed = [item for item in list(result.get("items_delta") or []) if int(item.get("quantity") or 0) < 0]
    for item in consumed:
        quantity = max((abs(int(item.get("quantity") or 0)) * percent) // 100, 0)
        if quantity <= 0:
            continue
        refunded = _grant_inventory_item_session(session, int(profile.tg), str(item.get("item_key") or ""), quantity)
        if refunded:
            result["items_delta"].append(refunded)


def _apply_legacy_inventory_mirrors(session, profile: DoupoProfile, result: dict[str, Any]) -> None:
    """旧版双轨物品镜像（降级保留，不重构）。

    canonical 源：物品已有独立掉落/合成/装备路径（monster_core_low、qi_gathering_powder、
    qinglian_fire_map、baji_beng_scroll、flame_divide_scroll、各火种）。
    这里仅在玩家背包尚无对应物品时补发一份种子，避免与 canonical 掉落叠加导致无限膨胀。
    """

    def _seed_if_absent(item_key: str, quantity: int) -> None:
        if quantity <= 0 or not item_key:
            return
        if _inventory_item_quantity_session(session, int(profile.tg), item_key) > 0:
            return
        granted = _grant_inventory_item_session(session, int(profile.tg), item_key, quantity)
        if granted:
            result["items_delta"].append(granted)

    for result_key, item_key, ratio in [
        ("core_delta", "monster_core_low", 1),
        ("pill_delta", "qi_gathering_powder", 1),
    ]:
        value = int(result.get(result_key) or 0)
        if value <= 0:
            continue
        _seed_if_absent(item_key, max(value // max(ratio, 1), 1))

    fire_progress = int(result.get("fire_progress_delta") or 0)
    if fire_progress > 0:
        _seed_if_absent("qinglian_fire_map", max(fire_progress // 30, 1))

    technique_delta = int(result.get("technique_delta") or 0)
    if technique_delta > 0:
        item_key = "baji_beng_scroll" if int(profile.technique_level or 0) <= 2 else "flame_divide_scroll"
        _seed_if_absent(item_key, max(technique_delta, 1))

    captured_fire = str(result.get("captured_fire") or "").strip()
    fire_item_key = _FIRE_ITEM_BY_NAME.get(captured_fire)
    if fire_item_key:
        _seed_if_absent(fire_item_key, 1)


def _mark_rare_item_events(result: dict[str, Any]) -> None:
    rare_items = []
    for item in result.get("items_delta") or []:
        if int(item.get("quantity") or 0) <= 0:
            continue
        rarity = str(item.get("rarity") or "凡品")
        if _RARITY_WEIGHT.get(rarity, 0) >= 6:
            rare_items.append(item)
    result["rare_items"] = rare_items


def _apply_action_rewards(
    session,
    profile: DoupoProfile,
    action: DoupoAction,
    reward: dict[str, Any],
    result: dict[str, Any],
    ledger: DoupoEconomyLedger | None,
    settings: dict[str, Any],
) -> None:
    action_type = str(action.action_type or "train")
    if action_type == "breakthrough":
        state = _breakthrough_state(session, profile, settings)
        if not state["available"]:
            raise ValueError(str(state["disabled_reason"] or "当前无法突破"))
        effective_costs = {
            "gold_cost": int(state["gold_cost"]),
            "item_costs": dict(state["item_costs"]),
        }
        _spend_action_costs(session, profile, effective_costs, result, ledger, settings)
        success_percent = int(state["success_percent"])
        roll = random.randint(1, 100)
        result["roll"] = roll
        result["success_percent"] = success_percent
        result["breakthrough_pity"] = bool(state["pity_ready"])
        result["breakthrough_pity_after"] = int(state["pity_after"])
        result["breakthrough_stage_from"] = str(state["stage"])
        if roll <= success_percent:
            required_douqi = int(state["douqi_required"])
            consumed_douqi = min(int(profile.douqi or 0), required_douqi)
            profile.douqi = max(int(profile.douqi or 0) - consumed_douqi, 0)
            result["douqi_delta"] -= consumed_douqi
            profile.realm_stage = str(state["next_stage"])
            profile.realm_stars = 1
            _settle_realm_change(profile, str(state["stage"]))
            result["breakthrough_success"] = True
            result["breakthrough_stage_to"] = str(state["next_stage"])
            result["breakthrough_failures"] = 0
            # 帝流丹仅在突破成功时消耗（一次性加成已计入 success_percent）。
            if state["has_emperor_pill"]:
                consumed = _consume_inventory_item_session(session, int(profile.tg), "emperor_flow_pill", 1)
                if consumed:
                    result["items_delta"].append(consumed)
                    result["bonus_pill_used"] = "帝流丹"
        else:
            failure_loss_percent = min(
                max(_coerce_int(settings.get("breakthrough_failure_douqi_loss_percent"), 10), 0),
                100,
            )
            loss = int(state["douqi_required"]) * failure_loss_percent // 100
            if failure_loss_percent > 0:
                loss = max(loss, 1)
            # 定境丹：突破失败时斗气损失减半（一次性），消耗在本次失败结算。
            if state["has_stabilizing_pill"]:
                loss = max(loss // 2, 0)
                consumed = _consume_inventory_item_session(session, int(profile.tg), "realm_stabilizing_pill", 1)
                if consumed:
                    result["items_delta"].append(consumed)
                    result["stabilizing_pill_used"] = True
            result["douqi_delta"] += _apply_resource_delta(profile, "douqi", -loss)
            result["breakthrough_failure_douqi_loss"] = loss
            profile.breakthrough_failures = int(state["failures"]) + 1
            result["breakthrough_failures"] = int(profile.breakthrough_failures)
        return

    costs_spent = False
    if action_type == "alchemy":
        _spend_action_costs(session, profile, reward, result, ledger, settings)
        costs_spent = True
        base_success = min(max(_coerce_int(reward.get("success_percent"), 82), 1), 100)
        equipment = get_equipment_summary(int(profile.tg)).get("stats") or {}
        success_percent = min(
            base_success
            + int(profile.alchemy_exp or 0) // 90
            + int(profile.fire_seed or 0) // 180
            + int(getattr(profile, "fire_rank", 0) or 0) * 3
            + int(getattr(profile, "method_level", 0) or 0) * 2
            + max(_coerce_int(equipment.get("alchemy_bonus"), 0), 0),
            98,
        )
        roll = random.randint(1, 100)
        result["alchemy_success_percent"] = success_percent
        result["roll"] = roll
        if roll > success_percent:
            result["alchemy_success"] = False
            result["success"] = False
            result["alchemy_delta"] += _apply_resource_delta(
                profile,
                "alchemy_exp",
                max(_roll_optional_range(reward, "alchemy_min", "alchemy_max") // 2, 1),
            )
            _refund_consumed_items_session(session, profile, result, _coerce_int(reward.get("refund_percent"), 30))
            _mark_rare_item_events(result)
            return
        result["alchemy_success"] = True
        # 炼药成功稳定产出丹药库存：全库唯一消耗 pill_stock 的口是塔修/Boss，此为其稳定来源。
        # 若自定义炼药行动自带了 pill_min/max，则交给下方通用分支发放，避免重复。
        if "pill_max" not in reward:
            result["pill_delta"] += _apply_resource_delta(
                profile,
                "pill_stock",
                max(_roll_optional_range(reward, "pill_min", "pill_max") // 2, 1),
            )

    if not costs_spent:
        _spend_action_costs(session, profile, reward, result, ledger, settings)
    douqi_gain = _roll_optional_range(reward, "douqi_min", "douqi_max")
    result["douqi_delta"] += _apply_douqi_delta_with_balance(
        session,
        profile,
        _douqi_training_bonus(profile, action_type, douqi_gain),
        settings,
        result,
    )
    result["gold_delta"] += _apply_gold_delta_with_economy(
        profile,
        _roll_optional_range(reward, "gold_min", "gold_max"),
        ledger,
        settings,
        result,
    )
    result["fire_delta"] += _apply_resource_delta(profile, "fire_seed", _roll_optional_range(reward, "fire_min", "fire_max"))
    result["alchemy_delta"] += _apply_resource_delta(profile, "alchemy_exp", _roll_optional_range(reward, "alchemy_min", "alchemy_max"))
    result["core_delta"] += _apply_resource_delta(profile, "beast_core", _roll_optional_range(reward, "core_min", "core_max"))
    result["sect_delta"] += _apply_resource_delta(profile, "sect_contribution", _roll_optional_range(reward, "sect_min", "sect_max"))
    result["pill_delta"] += _apply_resource_delta(profile, "pill_stock", _roll_optional_range(reward, "pill_min", "pill_max"))
    result["technique_delta"] += _apply_resource_delta(profile, "technique_level", _roll_optional_range(reward, "technique_min", "technique_max"))
    result["method_delta"] += _apply_resource_delta(profile, "method_level", _roll_optional_range(reward, "method_min", "method_max"))
    result["fire_rank_delta"] += _apply_resource_delta(profile, "fire_rank", _roll_optional_range(reward, "fire_rank_min", "fire_rank_max"))
    result["fire_energy_delta"] += _apply_resource_delta(profile, "academy_fire_energy", _roll_optional_range(reward, "fire_energy_min", "fire_energy_max"))
    result["faction_delta"] += _apply_resource_delta(profile, "faction_reputation", _roll_optional_range(reward, "faction_min", "faction_max"))
    result["infamy_delta"] += _apply_resource_delta(profile, "black_corner_infamy", _roll_optional_range(reward, "infamy_min", "infamy_max"))
    result["pet_delta"] += _apply_resource_delta(profile, "pet_level", _roll_optional_range(reward, "pet_min", "pet_max"))
    pet_key = str(reward.get("pet_key") or "").strip()
    if pet_key and not getattr(profile, "pet_key", None):
        profile.pet_key = pet_key
    result["boss_delta"] += _apply_resource_delta(profile, "boss_score", _roll_optional_range(reward, "boss_min", "boss_max"))
    result["tower_delta"] += _apply_resource_delta(profile, "tower_floor", _roll_optional_range(reward, "tower_min", "tower_max"))
    result["auction_delta"] += _apply_resource_delta(profile, "auction_credit", _roll_optional_range(reward, "auction_min", "auction_max"))
    result["fire_progress_delta"] += _apply_resource_delta(
        profile,
        "fire_progress",
        _roll_optional_range(reward, "fire_progress_min", "fire_progress_max"),
    )
    _apply_feature_side_effects(profile, action_type, result)
    _apply_configured_item_drops(session, profile, reward, result)
    _apply_legacy_inventory_mirrors(session, profile, result)
    _mark_rare_item_events(result)
    backlash = _apply_action_backlash(session, profile, reward, result, ledger, settings)
    if backlash:
        result["backlash_detail"] = backlash


def _apply_action_backlash(
    session,
    profile: DoupoProfile,
    reward: dict[str, Any],
    result: dict[str, Any],
    ledger: DoupoEconomyLedger | None,
    settings: dict[str, Any],
) -> str | None:
    """高风险行动反噬：命中 risk_percent 时按 backlash_* 键施加负向资源，返回可读详情。

    此前的 risk_percent/backlash_* 是死配置（全库无读取），这里首次消费。
    """
    risk_percent = min(max(_coerce_int(reward.get("risk_percent"), 0), 0), 100)
    if risk_percent <= 0 or random.randint(1, 100) > risk_percent:
        return None
    detail: list[str] = []
    douqi_loss = max(_coerce_int(reward.get("backlash_douqi_loss"), 0), 0)
    if douqi_loss:
        applied = _apply_douqi_delta_with_balance(session, profile, -douqi_loss, settings, result)
        if applied:
            result["douqi_delta"] += applied
            detail.append(f"斗气 {applied:+d}")
    gold_loss = max(_coerce_int(reward.get("backlash_gold_loss"), 0), 0)
    if gold_loss:
        applied = _apply_gold_delta_with_economy(profile, -gold_loss, ledger, settings, result)
        if applied:
            result["gold_delta"] += applied
            detail.append(f"金币 {applied:+d}")
    fire_loss = max(_coerce_int(reward.get("backlash_fire_loss"), 0), 0)
    if fire_loss:
        applied = _apply_resource_delta(profile, "fire_progress", -fire_loss)
        if applied:
            result["fire_progress_delta"] += applied
            detail.append(f"火候 {applied:+d}")
    return "，".join(detail) if detail else None


def _action_detail(result: dict[str, Any]) -> str:
    parts = [
        f"🌀 斗气 {int(result.get('douqi_delta') or 0):+d}",
        f"🪙 金币 {int(result.get('gold_delta') or 0):+d}",
    ]
    for key, label in (
        ("core_delta", "💎 魔核"),
        ("alchemy_delta", "⚗️ 炼药"),
        ("fire_delta", "🔥 火候"),
        ("fire_progress_delta", "🔥 异火线索"),
        ("sect_delta", "🏅 贡献"),
        ("pill_delta", "💊 丹药"),
        ("technique_delta", "📜 斗技"),
        ("method_delta", "📖 焚诀"),
        ("fire_rank_delta", "🔥 异火掌控"),
        ("fire_energy_delta", "🔥 火能"),
        ("faction_delta", "🛡️ 阵营声望"),
        ("infamy_delta", "💀 黑角域恶名"),
        ("pet_delta", "🐾 伙伴"),
        ("boss_delta", "👹 Boss战绩"),
        ("tower_delta", "🏯 塔层"),
        ("auction_delta", "🏛️ 拍卖声望"),
    ):
        value = int(result.get(key) or 0)
        if value:
            parts.append(f"{label} {value:+d}")
    if result.get("captured_fire"):
        parts.append(f"🔥 收服 {result['captured_fire']}")
    item_parts = []
    for item in result.get("items_delta") or []:
        quantity = int(item.get("quantity") or 0)
        if quantity == 0:
            continue
        item_parts.append(f"{item.get('name') or item.get('item_key')} {quantity:+d}")
    if item_parts:
        parts.append("💍 纳戒 " + "、".join(item_parts[:6]))
    capped = int(result.get("gold_capped_delta") or 0)
    if capped > 0:
        parts.append(f"🪙 今日金币上限截断 {capped}")
    douqi_capped = int(result.get("douqi_capped_delta") or 0)
    if douqi_capped > 0:
        parts.append(f"🌀 今日斗气衰减 {douqi_capped}")
    bottleneck_reduced = int(result.get("douqi_bottleneck_delta") or 0)
    if bottleneck_reduced > 0:
        parts.append(f"🌀 境界瓶颈未吸收斗气 {bottleneck_reduced}")
    perfected_discarded = int(result.get("realm_perfected_discarded") or 0)
    if perfected_discarded > 0:
        parts.append(f"👑 帝位圆满，多余斗气已消散 {perfected_discarded}")
    elif result.get("realm_perfected"):
        parts.append("👑 帝位圆满")
    if result.get("breakthrough_success"):
        pity_text = "（🎯 保底）" if result.get("breakthrough_pity") else ""
        parts.append(
            f"⚡ 突破成功{pity_text}：{result.get('breakthrough_stage_from') or ''} → "
            f"{result.get('breakthrough_stage_to') or ''}"
        )
    elif result.get("action_type") == "breakthrough":
        failures = int(result.get("breakthrough_failures") or 0)
        pity_after = int(result.get("breakthrough_pity_after") or 0)
        parts.append(f"💥 突破未成，保底进度 {failures}/{pity_after}")
    if result.get("action_type") == "alchemy":
        if result.get("alchemy_success") is False:
            parts.append(f"⚗️ 炼药失败（成功率 {int(result.get('alchemy_success_percent') or 0)}%）")
        elif result.get("alchemy_success") is True:
            parts.append(f"⚗️ 炼药成功（成功率 {int(result.get('alchemy_success_percent') or 0)}%）")
    return "，".join(parts)


def _build_broadcast_event(profile: DoupoProfile, result: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(settings.get("broadcast_enabled", True)):
        return None
    display_name = _profile_display_name(profile.display_name, profile.username, int(profile.tg))
    realm_text = f"{profile.realm_stage} {int(profile.realm_stars or 1)}星"
    if result.get("breakthrough_success"):
        return {
            "kind": "breakthrough",
            "title": "⚡ 斗破突破播报",
            "text": f"⚡ {display_name} 冲破瓶颈，当前境界：{realm_text}。",
        }
    if result.get("captured_fire"):
        return {
            "kind": "fire",
            "title": "🔥 异火收服播报",
            "text": f"🔥 {display_name} 成功收服 {result['captured_fire']}，火候大涨。",
        }
    rare_items = result.get("rare_items") or []
    if rare_items:
        names = "、".join(str(item.get("name") or item.get("item_key")) for item in rare_items[:3])
        return {
            "kind": "rare_item",
            "title": "💎 纳戒稀有掉落",
            "text": f"💎 {display_name} 在 {result.get('action_name') or '行动'} 中获得稀有物品：{names}。",
        }
    if str(result.get("action_type") or "") == "boss" and int(result.get("boss_delta") or 0) >= 60:
        return {
            "kind": "boss",
            "title": "👹 魔兽讨伐播报",
            "text": f"👹 {display_name} 完成高战绩讨伐，Boss 战绩 +{int(result.get('boss_delta') or 0)}。",
        }
    return None


def run_action(tg: int, action_key: str) -> dict[str, Any]:
    ensure_default_actions()
    settings = get_settings()
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == int(tg)).with_for_update().first()
        if profile is None:
            profile = _new_profile(int(tg))
            session.add(profile)
            session.flush()
        action = (
            session.query(DoupoAction)
            .filter(DoupoAction.action_key == str(action_key), DoupoAction.enabled.is_(True))
            .first()
        )
        if action is None:
            raise ValueError("该行动不存在或已停用")
        ok, reason = _check_action_requirement(session, profile, action, settings)
        if not ok:
            raise ValueError(reason)
        cooldown_ok, cooldown_remain = _check_action_cooldown(profile, action)
        if not cooldown_ok:
            raise ValueError(f"冷却中，请等待 {cooldown_remain} 秒")

        action_type = str(action.action_type or "train")
        result: dict[str, Any] = {
            "action_key": str(action.action_key),
            "action_name": str(action.name),
            "action_type": action_type,
            "action_type_label": ACTION_TYPE_LABELS.get(action_type, action_type),
            "success": True,
            "gold_delta": 0,
            "douqi_delta": 0,
            "fire_delta": 0,
            "alchemy_delta": 0,
            "core_delta": 0,
            "sect_delta": 0,
            "pill_delta": 0,
            "technique_delta": 0,
            "method_delta": 0,
            "fire_rank_delta": 0,
            "fire_energy_delta": 0,
            "faction_delta": 0,
            "infamy_delta": 0,
            "pet_delta": 0,
            "boss_delta": 0,
            "tower_delta": 0,
            "auction_delta": 0,
            "fire_progress_delta": 0,
            "captured_fire": None,
            "breakthrough_success": False,
            "alchemy_success": None,
            "alchemy_success_percent": None,
            "gold_capped_delta": 0,
            "economy_capped": False,
            "douqi_capped_delta": 0,
            "douqi_bottleneck_delta": 0,
            "douqi_soft_capped": False,
            "douqi_hard_capped": False,
            "daily_douqi_income": 0,
            "items_delta": [],
            "rare_items": [],
            "broadcast": None,
        }
        now = utcnow()
        ledger = _get_or_create_economy_ledger_session(session, int(tg), _economy_day_key(now))
        daily_counter, daily_limit = _check_daily_action_limit(session, int(tg), action_type, settings, now)
        point_counter, point_limit, point_cost = _check_daily_action_points(
            session,
            int(tg),
            action_type,
            settings,
            now,
        )
        _apply_action_rewards(session, profile, action, dict(action.reward_config or {}), result, ledger, settings)
        _apply_realm_progress(profile, settings)
        ledger.action_count = int(ledger.action_count or 0) + 1
        ledger.updated_at = now
        _increment_daily_action_counter(daily_counter)
        _consume_daily_action_points(point_counter, point_cost)
        profile.last_breakthrough_at = now if action_type == "breakthrough" else profile.last_breakthrough_at
        profile.last_train_at = now if action_type != "breakthrough" else profile.last_train_at
        _set_action_cooldown(profile, action.action_key, now)
        profile.updated_at = now
        detail = _action_detail(result)
        session.add(
            DoupoJournal(
                tg=int(tg),
                action_type=action_type,
                title=f"{ACTION_TYPE_LABELS.get(action_type, '行动')}：{action.name}",
                detail=detail,
            )
        )
        session.commit()
        session.refresh(profile)
        result["detail"] = detail
        result["profile"] = serialize_profile(profile, settings)
        result["inventory"] = list_player_inventory_grouped(int(tg))
        result["economy"] = _serialize_economy_ledger(ledger, settings)
        result["daily_usage"] = {
            "action_type": action_type,
            "label": ACTION_TYPE_LABELS.get(action_type, action_type),
            "used": int(daily_counter.used_count or 0),
            "limit": int(daily_limit or 0),
            "remaining": max(int(daily_limit or 0) - int(daily_counter.used_count or 0), 0) if int(daily_limit or 0) > 0 else None,
            "action_point_cost": int(point_cost),
            "action_points_used": int(point_counter.used_count or 0),
            "action_points_limit": int(point_limit or 0),
            "action_points_remaining": max(int(point_limit or 0) - int(point_counter.used_count or 0), 0) if int(point_limit or 0) > 0 else None,
        }
        result["broadcast"] = _build_broadcast_event(profile, result, settings)
    return result


def _preview_exchange(direction: str, amount: int, settings: dict[str, Any]) -> dict[str, Any]:
    rate = max(_coerce_int(settings.get("exchange_rate"), 100), 1)
    if direction == "coin_to_gold":
        return {"spent_coin": int(amount), "received_gold": int(amount) * rate, "rate": rate}
    coin = int(amount) // rate
    spent_gold = coin * rate
    return {
        "spent_gold": spent_gold,
        "received_coin": coin,
        "remainder_gold": int(amount) - spent_gold,
        "rate": rate,
    }


def exchange_currency(tg: int, direction: str, amount: int) -> dict[str, Any]:
    amount = max(int(amount or 0), 0)
    if amount <= 0:
        raise ValueError("兑换数量必须大于 0")
    settings = get_settings()
    if not bool(settings.get("exchange_enabled", True)):
        raise ValueError("兑换功能当前未开启")
    actor_tg = int(tg)
    preview = _preview_exchange(direction, amount, settings)
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        if profile is None:
            profile = _new_profile(actor_tg)
            session.add(profile)
            session.flush()
        account = session.query(Emby).filter(Emby.tg == actor_tg).with_for_update().first()
        if account is None:
            raise ValueError("Emby 账号不存在")

        if direction == "coin_to_gold":
            rate = max(_coerce_int(settings.get("exchange_rate"), 100), 1)
            room = max(_INT32_MAX - int(profile.gold or 0), 0)
            max_coin = room // rate
            if amount > max_coin:
                raise ValueError(f"金币已接近上限，最多还能兑换 {max_coin} 碎片")
            if int(account.iv or 0) < amount:
                raise ValueError("Emby 碎片不足")
            received = int(amount) * rate
            account.iv = int(account.iv or 0) - amount
            profile.gold = int(profile.gold or 0) + received
            title = "碎片兑换金币"
            detail = f"🪙 消耗碎片 {amount}，获得金币 {received}"
        elif direction == "gold_to_coin":
            minimum = max(_coerce_int(settings.get("min_gold_to_exchange"), 100), 1)
            if amount < minimum:
                raise ValueError(f"最低需 {minimum} 金币")
            spent_gold = int(preview["spent_gold"])
            received_coin = int(preview["received_coin"])
            if spent_gold <= 0 or received_coin <= 0:
                raise ValueError("当前比例下可兑换碎片不足 1")
            if int(profile.gold or 0) < spent_gold:
                raise ValueError("金币不足")
            profile.gold = int(profile.gold or 0) - spent_gold
            account.iv = int(account.iv or 0) + received_coin
            title = "金币兑换碎片"
            detail = f"🪙 消耗金币 {spent_gold}，获得碎片 {received_coin}"
        else:
            raise ValueError("Unsupported exchange direction")

        profile.updated_at = utcnow()
        session.add(DoupoJournal(tg=actor_tg, action_type="exchange", title=title, detail=detail))
        session.commit()
        session.refresh(profile)
        session.refresh(account)
        balance = int(account.iv or 0)

    sql_invalidate_emby_cache(actor_tg)
    return {
        "direction": direction,
        **preview,
        "emby_balance": balance,
        "profile": serialize_profile(profile),
    }


def build_growth_snapshot(profile: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    stage = str(profile.get("realm_stage") or "斗之气")
    star = max(int(profile.get("realm_stars") or 1), 1)
    douqi = max(int(profile.get("douqi") or 0), 0)
    thresholds = settings.get("realm_thresholds") or []
    stage_index = realm_rank(stage, thresholds)
    row = thresholds[stage_index] if thresholds else None
    next_row = thresholds[stage_index + 1] if thresholds and stage_index + 1 < len(thresholds) else None
    per_star = max(_coerce_int((row or {}).get("douqi_per_star"), 100), 1)
    star_cap = max(_coerce_int((row or {}).get("star_cap"), 9), 1)
    at_stage_cap = star >= star_cap
    bar_full = douqi >= per_star
    realm_perfected = bool(next_row is None and bar_full)
    breakthrough_rule = dict(BREAKTHROUGH_RULES.get(stage) or {})
    failures = max(int(profile.get("breakthrough_failures") or 0), 0)
    pity_after = max(_coerce_int(breakthrough_rule.get("pity_after"), 4), 1)
    return {
        "realm_stage": stage,
        "realm_stars": star,
        "realm_index": stage_index,
        "next_realm_stage": None if next_row is None else str(next_row.get("stage") or ""),
        "star_cap": star_cap,
        "douqi_current": douqi,
        "douqi_to_next_star": max(per_star - douqi, 0),
        "douqi_per_star": per_star,
        "at_stage_cap": at_stage_cap,
        "bar_full": bar_full,
        "realm_perfected": realm_perfected,
        "requires_breakthrough": bool(next_row is not None and at_stage_cap),
        "breakthrough_ready": bool(next_row is not None and at_stage_cap and bar_full),
        "breakthrough": {
            "failures": failures,
            "pity_after": pity_after,
            "remaining_attempts_to_pity": max(pity_after - failures, 0),
            "gold_cost": max(_coerce_int(breakthrough_rule.get("gold_cost"), 0), 0),
            "item_costs": dict(breakthrough_rule.get("item_costs") or {}),
        },
        "battle_power": int(profile.get("battle_power") or 0),
        "alchemy_exp": int(profile.get("alchemy_exp") or 0),
        "fire_seed": int(profile.get("fire_seed") or 0),
        "beast_core": int(profile.get("beast_core") or 0),
    }


def build_feature_overview(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "sect": {
            "name": profile.get("sect_name"),
            "joined": bool(profile.get("sect_name")),
            "rank": profile.get("sect_rank") if profile.get("sect_name") else "未入宗门",
            "contribution": int(profile.get("sect_contribution") or 0),
            "next": next(
                (row for row in SECT_RANKS if int(row.get("contribution") or 0) > int(profile.get("sect_contribution") or 0)),
                None,
            ),
        },
        "alchemy": {
            "rank": profile.get("alchemy_rank") or "未入品",
            "exp": int(profile.get("alchemy_exp") or 0),
            "pill_stock": int(profile.get("pill_stock") or 0),
            "next": next(
                (row for row in ALCHEMY_RANKS if int(row.get("exp") or 0) > int(profile.get("alchemy_exp") or 0)),
                None,
            ),
        },
        "heavenly_fire": profile.get("heavenly_fire") or {},
        "burning_method": {
            "level": int(profile.get("method_level") or 0),
            "title": "黄阶低级" if int(profile.get("method_level") or 0) <= 0 else f"焚诀 {int(profile.get('method_level') or 0)} 转",
            "bonus": int(profile.get("method_level") or 0) * 4,
        },
        "technique": profile.get("technique") or {},
        "academy": {
            "fire_energy": int(profile.get("academy_fire_energy") or 0),
            "title": "外院新生" if int(profile.get("academy_fire_energy") or 0) < 100 else "内院强榜候选",
        },
        "faction": {
            "reputation": int(profile.get("faction_reputation") or 0),
            "title": "无名散修" if int(profile.get("faction_reputation") or 0) < 100 else "势力客卿",
        },
        "pet": {
            "key": profile.get("pet_key"),
            "level": int(profile.get("pet_level") or 0),
            "title": profile.get("pet_key") or "暂无伙伴",
        },
        "black_corner": {
            "infamy": int(profile.get("black_corner_infamy") or 0),
            "title": "黑角域新人" if int(profile.get("black_corner_infamy") or 0) < 100 else "黑榜留名",
        },
        "auction": {
            "credit": int(profile.get("auction_credit") or 0),
            "title": "拍卖熟客" if int(profile.get("auction_credit") or 0) >= 300 else "初入拍场",
        },
        "boss": {
            "score": int(profile.get("boss_score") or 0),
            "title": "魔兽猎手" if int(profile.get("boss_score") or 0) >= 300 else "试炼者",
        },
        "tower": {
            "floor": int(profile.get("tower_floor") or 0),
            "title": "塔中常客" if int(profile.get("tower_floor") or 0) >= 12 else "初入塔修",
        },
    }


def build_doupo_leaderboard(kind: str = "power", limit: int = 10) -> dict[str, Any]:
    normalized = str(kind or "power").strip().lower()
    kind_aliases = {
        "战力": "power",
        "power": "power",
        "realm": "realm",
        "境界": "realm",
        "alchemy": "alchemy",
        "炼药": "alchemy",
        "gold": "gold",
        "金币": "gold",
        "boss": "boss",
        "讨伐": "boss",
    }
    resolved_kind = kind_aliases.get(normalized, "power")
    settings = get_settings()
    with Session() as session:
        rows = session.query(DoupoProfile).all()
        # 批量取全部玩家的已装备物品，内存组装 equipment_summary，避免逐玩家查询 N+1。
        tg_list = [int(row.tg) for row in rows]
        equipment_map: dict[int, dict[str, Any]] = {}
        if tg_list:
            equipped_rows = (
                session.query(DoupoInventoryItem)
                .filter(
                    DoupoInventoryItem.tg.in_(tg_list),
                    DoupoInventoryItem.equipped_slot.isnot(None),
                )
                .order_by(DoupoInventoryItem.equipped_slot.asc())
                .all()
            )
            by_tg: dict[int, list[DoupoInventoryItem]] = {}
            for equip_row in equipped_rows:
                by_tg.setdefault(int(equip_row.tg), []).append(equip_row)
            for tg_value, item_rows in by_tg.items():
                equipment_map[tg_value] = _equipment_summary_from_rows(item_rows)
        profiles = [serialize_profile(row, settings, equipment_map.get(int(row.tg))) for row in rows]
    if resolved_kind == "realm":
        profiles.sort(
            key=lambda item: (
                int(item.get("battle_power") or 0),
                int(item.get("realm_stars") or 0),
                int(item.get("douqi") or 0),
            ),
            reverse=True,
        )
        label = "境界榜"
    elif resolved_kind == "alchemy":
        profiles.sort(key=lambda item: (int(item.get("alchemy_exp") or 0), int(item.get("battle_power") or 0)), reverse=True)
        label = "炼药榜"
    elif resolved_kind == "gold":
        profiles.sort(key=lambda item: (int(item.get("gold") or 0), int(item.get("battle_power") or 0)), reverse=True)
        label = "金币榜"
    elif resolved_kind == "boss":
        profiles.sort(key=lambda item: (int(item.get("boss_score") or 0), int(item.get("battle_power") or 0)), reverse=True)
        label = "讨伐榜"
    else:
        profiles.sort(key=lambda item: int(item.get("battle_power") or 0), reverse=True)
        label = "战力榜"
    max_limit = max(min(int(limit or 10), 30), 1)
    return {
        "kind": resolved_kind,
        "label": label,
        "items": profiles[:max_limit],
        "total": len(profiles),
    }


def _duel_stake_bounds(settings: dict[str, Any]) -> tuple[int, int]:
    minimum = max(_coerce_int(settings.get("duel_min_stake"), 0), 0)
    maximum = max(_coerce_int(settings.get("duel_max_stake"), 500), minimum)
    return minimum, maximum


def _duel_win_rate(challenger_power: int, defender_power: int) -> int:
    left = max(int(challenger_power or 0), 1)
    right = max(int(defender_power or 0), 1)
    raw = round((left / (left + right)) * 100)
    return min(max(raw, 12), 88)


def _duel_profile_payload(row: DoupoProfile, settings: dict[str, Any]) -> dict[str, Any]:
    profile = serialize_profile(row, settings)
    return {
        "tg": int(profile["tg"]),
        "display_name": profile.get("display_name"),
        "realm": f"{profile.get('realm_stage')} {int(profile.get('realm_stars') or 1)}星",
        "battle_power": int(profile.get("battle_power") or 0),
        "gold": int(profile.get("gold") or 0),
        "sect_name": profile.get("sect_name"),
        "technique_name": profile.get("technique_name"),
        "fire_name": profile.get("fire_name"),
        "method_level": int(profile.get("method_level") or 0),
        "fire_rank": int(profile.get("fire_rank") or 0),
        "duel_burst": int(profile.get("method_level") or 0) * 3 + int(profile.get("fire_rank") or 0) * 5,
    }


def compute_doupo_duel_preview(challenger_tg: int, defender_tg: int, stake: int = 0) -> dict[str, Any]:
    challenger_tg = int(challenger_tg)
    defender_tg = int(defender_tg)
    if challenger_tg <= 0 or defender_tg <= 0:
        raise ValueError("斗战双方身份无效")
    if challenger_tg == defender_tg:
        raise ValueError("不能向自己发起斗战")
    settings = get_settings()
    minimum, maximum = _duel_stake_bounds(settings)
    stake = max(int(stake or 0), 0)
    if stake < minimum:
        raise ValueError(f"斗战赌注至少需要 {minimum} 金币")
    if stake > maximum:
        raise ValueError(f"斗战赌注最多只能设置为 {maximum} 金币")
    with Session() as session:
        rows = {
            int(row.tg): row
            for row in session.query(DoupoProfile)
            .filter(DoupoProfile.tg.in_([challenger_tg, defender_tg]))
            .all()
        }
        challenger = rows.get(challenger_tg)
        defender = rows.get(defender_tg)
        if challenger is None:
            challenger = _new_profile(challenger_tg)
            session.add(challenger)
            session.flush()
        if defender is None:
            defender = _new_profile(defender_tg)
            session.add(defender)
            session.flush()
        if stake > 0 and (int(challenger.gold or 0) < stake or int(defender.gold or 0) < stake):
            raise ValueError("双方金币不足，无法发起该赌注斗战")
        challenger_payload = _duel_profile_payload(challenger, settings)
        defender_payload = _duel_profile_payload(defender, settings)
        session.commit()
    rate = _duel_win_rate(challenger_payload["battle_power"], defender_payload["battle_power"])
    return {
        "challenger": challenger_payload,
        "defender": defender_payload,
        "stake_gold": stake,
        "challenger_win_rate": rate,
        "defender_win_rate": 100 - rate,
        "stake_min": minimum,
        "stake_max": maximum,
    }


def _duel_log_lines(challenger: dict[str, Any], defender: dict[str, Any], winner: dict[str, Any], roll: int, rate: int) -> list[str]:
    lines = [
        f"{challenger['display_name']} 以 {challenger['technique_name'] or '基础斗技'} 起手。",
        f"{defender['display_name']} 以 {defender['fire_name'] or '斗气护体'} 应对。",
    ]
    if int(challenger.get("duel_burst") or 0) > 0:
        lines.append(f"{challenger['display_name']} 运转焚诀，异火爆发值 {int(challenger.get('duel_burst') or 0)}。")
    if int(defender.get("duel_burst") or 0) > 0:
        lines.append(f"{defender['display_name']} 借异火护身，爆发值 {int(defender.get('duel_burst') or 0)}。")
    if roll <= rate:
        lines.append(f"判定 {roll}/{rate}，{challenger['display_name']} 抓住破绽压制对手。")
    else:
        lines.append(f"判定 {roll}/{rate}，{defender['display_name']} 反手破招。")
    lines.append(f"胜者：{winner['display_name']}。")
    return lines


def resolve_doupo_duel(challenger_tg: int, defender_tg: int, stake: int = 0) -> dict[str, Any]:
    challenger_tg = int(challenger_tg)
    defender_tg = int(defender_tg)
    if challenger_tg == defender_tg:
        raise ValueError("不能挑战自己")
    settings = get_settings()
    minimum, maximum = _duel_stake_bounds(settings)
    stake = max(int(stake or 0), 0)
    if stake < minimum:
        raise ValueError(f"斗战赌注至少需要 {minimum} 金币")
    if stake > maximum:
        raise ValueError(f"斗战赌注最多只能设置为 {maximum} 金币")
    with Session() as session:
        rows = {
            int(row.tg): row
            for row in session.query(DoupoProfile)
            .filter(DoupoProfile.tg.in_([challenger_tg, defender_tg]))
            .with_for_update()
            .all()
        }
        challenger = rows.get(challenger_tg)
        defender = rows.get(defender_tg)
        if challenger is None or defender is None:
            raise ValueError("斗战双方需要先初始化斗破角色")
        if stake > 0 and (int(challenger.gold or 0) < stake or int(defender.gold or 0) < stake):
            raise ValueError("双方金币不足，斗战已取消")
        challenger_payload = _duel_profile_payload(challenger, settings)
        defender_payload = _duel_profile_payload(defender, settings)
        rate = _duel_win_rate(challenger_payload["battle_power"], defender_payload["battle_power"])
        roll = random.randint(1, 100)
        challenger_wins = roll <= rate
        winner_row = challenger if challenger_wins else defender
        loser_row = defender if challenger_wins else challenger
        winner_payload = challenger_payload if challenger_wins else defender_payload
        loser_payload = defender_payload if challenger_wins else challenger_payload
        if stake > 0:
            loser_row.gold = max(int(loser_row.gold or 0) - stake, 0)
            winner_row.gold = int(winner_row.gold or 0) + stake
        battle_log = _duel_log_lines(challenger_payload, defender_payload, winner_payload, roll, rate)
        row = DoupoDuelHistory(
            challenger_tg=challenger_tg,
            defender_tg=defender_tg,
            winner_tg=int(winner_row.tg),
            loser_tg=int(loser_row.tg),
            stake_gold=stake,
            challenger_power=challenger_payload["battle_power"],
            defender_power=defender_payload["battle_power"],
            challenger_win_rate=rate,
            roll=roll,
            battle_log=battle_log,
        )
        session.add(row)
        session.add(DoupoJournal(tg=challenger_tg, action_type="duel", title="斗战结算", detail=f"⚔️ 对战 {defender_payload['display_name']}，{'🏆 胜' if challenger_wins else '💔 负'}，🪙 赌注 {stake}"))
        session.add(DoupoJournal(tg=defender_tg, action_type="duel", title="斗战结算", detail=f"⚔️ 对战 {challenger_payload['display_name']}，{'🏆 胜' if not challenger_wins else '💔 负'}，🪙 赌注 {stake}"))
        session.commit()
        session.refresh(row)
    return {
        "id": int(row.id),
        "challenger": challenger_payload,
        "defender": defender_payload,
        "winner": winner_payload,
        "loser": loser_payload,
        "stake_gold": stake,
        "challenger_win_rate": rate,
        "defender_win_rate": 100 - rate,
        "roll": roll,
        "battle_log": battle_log,
    }


def list_duel_history(tg: int, limit: int = 20) -> list[dict[str, Any]]:
    """读取某玩家的决斗历史（DoupoDuelHistory 此前只写不读）。"""
    actor_tg = int(tg)
    limit = max(min(int(limit or 20), 50), 1)
    with Session() as session:
        rows = (
            session.query(DoupoDuelHistory)
            .filter((DoupoDuelHistory.challenger_tg == actor_tg) | (DoupoDuelHistory.defender_tg == actor_tg))
            .order_by(DoupoDuelHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        involved = {actor_tg}
        for row in rows:
            involved.add(int(row.challenger_tg))
            involved.add(int(row.defender_tg))
        names = {
            int(profile.tg): (profile.display_name or profile.username or str(profile.tg))
            for profile in session.query(DoupoProfile).filter(DoupoProfile.tg.in_(list(involved))).all()
        }
        items = []
        for row in rows:
            challenger_tg = int(row.challenger_tg)
            defender_tg = int(row.defender_tg)
            winner_tg = int(row.winner_tg)
            items.append(
                {
                    "id": int(row.id),
                    "challenger_tg": challenger_tg,
                    "challenger_name": names.get(challenger_tg, str(challenger_tg)),
                    "defender_tg": defender_tg,
                    "defender_name": names.get(defender_tg, str(defender_tg)),
                    "winner_tg": winner_tg,
                    "loser_tg": int(row.loser_tg),
                    "winner_name": names.get(winner_tg, str(winner_tg)),
                    "stake_gold": int(row.stake_gold or 0),
                    "challenger_win_rate": int(row.challenger_win_rate or 0),
                    "roll": int(row.roll or 0),
                    "player_won": winner_tg == actor_tg,
                    "battle_log": list(row.battle_log or []),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return items


def build_duel_standings(tg: int) -> dict[str, Any]:
    """聚合玩家决斗胜负与赌注收支。"""
    actor_tg = int(tg)
    with Session() as session:
        history = (
            session.query(DoupoDuelHistory)
            .filter((DoupoDuelHistory.challenger_tg == actor_tg) | (DoupoDuelHistory.defender_tg == actor_tg))
            .all()
        )
        wins = 0
        losses = 0
        stake_won = 0
        stake_lost = 0
        for row in history:
            if int(row.winner_tg) == actor_tg:
                wins += 1
                stake_won += int(row.stake_gold or 0)
            else:
                losses += 1
                stake_lost += int(row.stake_gold or 0)
        total = wins + losses
        return {
            "wins": wins,
            "losses": losses,
            "total": total,
            "win_rate_percent": round(wins * 100 / total, 1) if total else 0,
            "stake_won": stake_won,
            "stake_lost": stake_lost,
            "net_stake": stake_won - stake_lost,
        }


def _admin_content_catalog(actions: list[dict[str, Any]]) -> dict[str, Any]:
    definitions = list_item_definitions(include_disabled=True)
    source_lookup: dict[str, set[str]] = {str(item["item_key"]): set() for item in definitions}
    recipes: list[dict[str, Any]] = []

    for action in actions:
        reward = dict(action.get("reward_config") or {})
        drops = reward.get("item_drops") if isinstance(reward.get("item_drops"), list) else []
        for drop in drops:
            if not isinstance(drop, dict):
                continue
            item_key = str(drop.get("item_key") or drop.get("key") or "").strip()
            if item_key in source_lookup:
                source_lookup[item_key].add(f"行动 · {action.get('name') or action.get('action_key')}")

        costs = _normalize_item_costs(reward.get("item_costs"))
        if not costs or not drops:
            continue
        recipe_outputs = []
        for drop in drops:
            if not isinstance(drop, dict):
                continue
            item_key = str(drop.get("item_key") or drop.get("key") or "").strip()
            catalog = _catalog_item(item_key)
            minimum = max(_coerce_int(drop.get("min", drop.get("quantity_min", 1)), 1), 0)
            maximum = max(_coerce_int(drop.get("max", drop.get("quantity_max", minimum)), minimum), minimum)
            recipe_outputs.append(
                {
                    "item_key": item_key,
                    "name": catalog["name"],
                    "min": minimum,
                    "max": maximum,
                    "chance": min(max(_coerce_int(drop.get("chance"), 100), 0), 100),
                }
            )
        if recipe_outputs:
            recipes.append(
                {
                    "action_key": str(action.get("action_key") or ""),
                    "name": str(action.get("name") or action.get("action_key") or ""),
                    "action_type": str(action.get("action_type") or ""),
                    "action_type_label": str(action.get("action_type_label") or action.get("action_type") or ""),
                    "enabled": bool(action.get("enabled", True)),
                    "gold_cost": max(_coerce_int(reward.get("gold_cost"), 0), 0),
                    "inputs": [
                        {
                            "item_key": item_key,
                            "name": _catalog_item(item_key)["name"],
                            "quantity": quantity,
                        }
                        for item_key, quantity in costs
                    ],
                    "outputs": recipe_outputs,
                    "requirement_config": dict(action.get("requirement_config") or {}),
                }
            )

    region_rows: list[dict[str, Any]] = []
    for region in EXPEDITION_REGIONS:
        region_name = str(region.get("name") or region.get("key") or "游历区域")
        event_names: list[str] = []
        completion = dict(region.get("completion_bonus") or {})
        for item_key in dict(completion.get("items") or {}):
            if str(item_key) in source_lookup:
                source_lookup[str(item_key)].add(f"游历 · {region_name}结算")
        for event_key in list(region.get("event_keys") or []):
            event = dict(EXPEDITION_EVENTS.get(str(event_key)) or {})
            event_name = str(event.get("title") or event_key)
            event_names.append(event_name)
            for choice in list(event.get("choices") or []):
                for outcome_key in ("success", "failure"):
                    outcome = choice.get(outcome_key) if isinstance(choice, dict) else None
                    for item_key in dict((outcome or {}).get("drops") or {}):
                        if str(item_key) in source_lookup:
                            source_lookup[str(item_key)].add(f"游历 · {region_name} / {event_name}")
        region_rows.append(
            {
                "key": str(region.get("key") or ""),
                "name": region_name,
                "description": str(region.get("description") or ""),
                "realm_stage_min": str(region.get("realm_stage_min") or "斗之气"),
                "recommended_power": max(_coerce_int(region.get("recommended_power"), 0), 0),
                "entry_gold": max(_coerce_int(region.get("entry_gold"), 0), 0),
                "max_steps": max(_coerce_int(region.get("max_steps"), 0), 0),
                "events": event_names,
            }
        )

    items = [
        {
            **dict(item),
            "key": str(item["item_key"]),
            "sources": sorted(source_lookup.get(str(item["item_key"])) or []),
        }
        for item in definitions
    ]
    for item in items:
        configured_sources = [
            f"行动 · {source.get('action_key')}（{int(source.get('chance') or 0)}%）"
            for source in list(item.get("drop_sources") or [])
            if isinstance(source, dict) and source.get("action_key")
        ]
        item["sources"] = sorted(set(item.get("sources") or []) | set(configured_sources))
    category_rows = []
    for category in INVENTORY_CATEGORIES:
        key = str(category.get("key") or "")
        category_rows.append(
            {
                **dict(category),
                "item_count": sum(1 for item in items if item["category"] == key),
            }
        )
    return {
        "summary": {
            "items": len(items),
            "materials": sum(1 for item in items if item["category"] in {"herb", "ore", "core"}),
            "pills": sum(1 for item in items if item["category"] == "pill"),
            "gear": sum(1 for item in items if item["category"] == "gear"),
            "recipes": len(recipes),
            "regions": len(region_rows),
            "events": len(EXPEDITION_EVENTS),
        },
        "categories": category_rows,
        "items": items,
        "recipes": recipes,
        "regions": region_rows,
    }


def admin_bootstrap_payload(player_query: str | None = None, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 10), 100), 1)
    with Session() as session:
        query = session.query(DoupoProfile)
        keyword = str(player_query or "").strip()
        if keyword:
            if keyword.lstrip("-").isdigit():
                query = query.filter(DoupoProfile.tg == int(keyword))
            else:
                like = f"%{keyword}%"
                query = query.filter((DoupoProfile.display_name.ilike(like)) | (DoupoProfile.username.ilike(like)))
        total = query.count()
        rows = (
            query.order_by(DoupoProfile.updated_at.desc(), DoupoProfile.tg.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        players = [serialize_profile(row) for row in rows]
    actions = list_actions(enabled_only=False)
    return {
        "settings": get_settings(),
        "actions": actions,
        "action_type_labels": ACTION_TYPE_LABELS,
        "content_catalog": _admin_content_catalog(actions),
        "player_search": {
            "query": str(player_query or ""),
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "items": players,
        },
    }


def admin_get_player_bundle(tg: int) -> dict[str, Any]:
    actor_tg = int(tg)
    profile = get_or_create_profile(actor_tg)
    settings = get_settings()
    return {
        "profile": profile,
        "growth": build_growth_snapshot(profile, settings),
        "features": build_feature_overview(profile),
        "inventory": list_player_inventory_grouped(actor_tg),
        "economy": get_economy_snapshot(actor_tg, settings),
        "daily_usage": get_daily_action_usage(actor_tg, settings),
        "sects": list_sect_options(),
        "journals": list_recent_journals(actor_tg, limit=30),
        "emby_balance": get_emby_balance(actor_tg),
    }


def admin_grant_resource(tg: int, resource: str, amount: int) -> dict[str, Any]:
    actor_tg = int(tg)
    raw_amount = int(amount or 0)
    resource_fields = {
        "gold": "gold",
        "douqi": "douqi",
        "fire_seed": "fire_seed",
        "alchemy_exp": "alchemy_exp",
        "beast_core": "beast_core",
        "sect_contribution": "sect_contribution",
        "pill_stock": "pill_stock",
        "technique_level": "technique_level",
        "method_level": "method_level",
        "fire_rank": "fire_rank",
        "pet_level": "pet_level",
        "academy_fire_energy": "academy_fire_energy",
        "faction_reputation": "faction_reputation",
        "black_corner_infamy": "black_corner_infamy",
        "fire_progress": "fire_progress",
        "boss_score": "boss_score",
        "tower_floor": "tower_floor",
        "auction_credit": "auction_credit",
        "realm_stage": "realm_stage",
        "realm_stars": "realm_stars",
        "fire_name": "fire_name",
    }
    field = resource_fields.get(str(resource or ""))
    if field is None:
        raise ValueError("不支持的资源类型")
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        if profile is None:
            profile = _new_profile(actor_tg)
            session.add(profile)
            session.flush()
        if field == "realm_stage":
            # amount 作为境界阈值下标（0 = 斗之气），设置后统一收口失败数。
            thresholds = get_settings().get("realm_thresholds") or []
            if raw_amount < 0 or raw_amount >= len(thresholds):
                raise ValueError("境界序号越界")
            old_stage = str(profile.realm_stage or "斗之气")
            profile.realm_stage = str(thresholds[raw_amount].get("stage") or "")
            profile.realm_stars = max(int(profile.realm_stars or 1), 1)
            _settle_realm_change(profile, old_stage)
        elif field == "realm_stars":
            if raw_amount < 1:
                raise ValueError("星级至少为 1")
            profile.realm_stars = raw_amount
        elif field == "fire_name":
            # amount 作为 HEAVENLY_FIRES 下标（0 = 青莲地心火）。
            if raw_amount < 0 or raw_amount >= len(HEAVENLY_FIRES):
                raise ValueError("异火序号越界")
            profile.fire_name = str(HEAVENLY_FIRES[raw_amount].get("name") or "")
        else:
            if raw_amount == 0:
                raise ValueError("数量不能为 0")
            _apply_resource_delta(profile, field, raw_amount)
        if field == "douqi":
            _apply_realm_progress(profile, get_settings())
        profile.updated_at = utcnow()
        session.add(
            DoupoJournal(
                tg=actor_tg,
                action_type="admin",
                title="后台资源调整",
                detail=f"{resource} {delta:+d}",
            )
        )
        session.commit()
    return admin_get_player_bundle(actor_tg)


def admin_reset_all_player_data() -> dict[str, Any]:
    with Session() as session:
        deleted_journals = session.query(DoupoJournal).delete()
        deleted_inventory = session.query(DoupoInventoryItem).delete()
        deleted_economy = session.query(DoupoEconomyLedger).delete()
        deleted_counters = session.query(DoupoDailyActionCounter).delete()
        deleted_expeditions = session.query(DoupoExpedition).delete()
        deleted_duels = session.query(DoupoDuelHistory).delete()
        deleted_profiles = session.query(DoupoProfile).delete()
        session.commit()
    return {
        "deleted_profiles": int(deleted_profiles),
        "deleted_journals": int(deleted_journals),
        "deleted_inventory": int(deleted_inventory),
        "deleted_economy": int(deleted_economy),
        "deleted_counters": int(deleted_counters),
        "deleted_expeditions": int(deleted_expeditions),
        "deleted_duels": int(deleted_duels),
    }


def admin_upsert_action(
    action_key: str,
    *,
    name: str,
    description: str = "",
    action_type: str = "train",
    cooldown_seconds: int = 0,
    reward_config: dict[str, Any] | None = None,
    requirement_config: dict[str, Any] | None = None,
    enabled: bool = True,
    sort_order: int = 0,
) -> dict[str, Any]:
    key = str(action_key or "").strip()
    if not key:
        raise ValueError("action_key 不能为空")
    if action_type not in ACTION_TYPE_LABELS:
        raise ValueError("不支持的行动类型")
    with Session() as session:
        row = session.query(DoupoAction).filter(DoupoAction.action_key == key).first()
        if row is None:
            row = DoupoAction(action_key=key)
            session.add(row)
        row.name = str(name or key)[:64]
        row.description = str(description or "")[:255]
        row.action_type = str(action_type or "train")[:32]
        row.cooldown_seconds = max(int(cooldown_seconds or 0), 0)
        row.reward_config = dict(reward_config or {})
        row.requirement_config = dict(requirement_config or {})
        row.enabled = bool(enabled)
        row.sort_order = int(sort_order or 0)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_action(row)
