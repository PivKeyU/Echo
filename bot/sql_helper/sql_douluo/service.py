"""斗罗大陆文字游戏核心服务层(设置/档案/行动力/武魂/修炼/装备/兑换/斗魂/排行)。

领域玩法(猎杀魂环、拍卖、每日任务、后台管理)分别在:
  - soulbeast_service.py  猎杀魂兽、魂环吸收/替换
  - auction_service.py    拍卖会
  - daily_service.py      每日任务、宗门、俸禄
  - admin_service.py      后台玩家编辑、内容目录
"""

from __future__ import annotations

import copy
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from bot.func_helper.emby_currency import get_emby_balance
from bot.plugins.douluo_game.core import (
    ACTION_TYPE_LABELS,
    BATTLE_ARMOR_ITEM_KEY,
    BATTLE_ARMOR_TIERS,
    BLOODLINE_AWAKEN_REALM,
    BLOODLINE_MAX_LEVEL,
    BREAKTHROUGH_RULES,
    CRAFTSMAN_RANK_EXP,
    DEFAULT_ACTION_POINT_COSTS,
    DEFAULT_DAILY_ACTION_LIMITS,
    DEFAULT_REALM_THRESHOLDS,
    EQUIP_SLOT_BATTLE_ARMOR,
    EQUIP_SLOT_SOUL_CORE,
    MATERIAL_CATALOG,
    MATERIAL_WEIGHT_BY_RARITY,
    PROSPECT_REGIONS,
    REALM_BASE_POWER,
    RING_SLOT_CAP,
    SLOT_SOUL_JET,
    SLOT_SOUL_SHIELD,
    SLOT_SOUL_WEAPON,
    SOUL_BONE_PARTS,
    SOUL_CORE_TIERS,
    SOUL_DEVICE_CATALOG,
    TITLED_DOULUO_TITLES,
    WUHUN_QUALITY_POWER,
    WUHUN_SYSTEM_POWER,
    material_by_key,
    max_allowed_ring_tier,
    realm_index,
    realm_stages,
    total_soul_power_needed,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_douluo.models import (
    DouluoDailyActionCounter,
    DouluoInventoryItem,
    DouluoItemDefinition,
    DouluoJournal,
    DouluoProfile,
    DouluoSetting,
    DouluoSoulRing,
    utcnow,
)
from bot.sql_helper.sql_emby import Emby, sql_invalidate_emby_cache

# ---------------------------------------------------------------------------
# 设置默认值
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS: dict[str, Any] = {
    "exchange_rate": 100,  # 100 碎片 = 1 魂币
    "min_coin_to_exchange": 1,
    "coin_min_to_buy": 1,
    "daily_coin_soft_cap": 650,
    "daily_coin_hard_cap": 1000,
    "daily_coin_overflow_percent": 20,
    "daily_action_points": 12,
    "daily_soul_power_soft_cap": 400,
    "daily_soul_power_hard_cap": 700,
    "soul_power_overflow_percent": 20,
    "train_coin_min": 20,
    "train_coin_max": 45,
    "train_soul_power_min": 30,
    "train_soul_power_max": 60,
    "wuhun_awaken_coin": 0,
    "wuhun_reforge_coin": 500,
    "wuhun_reforge_cd_hours": 24,
    "hunt_absorb_fee": 200,
    "duel_min_stake": 0,
    "duel_max_stake": 500,
    "duel_prepare_seconds": 8,
    "exchange_enabled": True,
    "broadcast_enabled": True,
    "message_auto_delete_seconds": 180,
    "event_chance_percent": 25,
    "auction_fee_percent": 5,
    "auction_duration_hours": 12,
    # 后续作品玩法
    "bloodline_awaken_coin": 2000,
    "bloodline_enhance_coin": 800,
    "bloodline_enhance_soul_power": 2000,
    "prospect_coin_cost": 100,
    "condense_coin_cost": 2000,
    "condense_soul_power_cost": 3000,
    "armor_upgrade_coin": 1500,
}

_SETTINGS_CACHE: tuple[float, dict[str, Any]] | None = None
_SETTINGS_CACHE_LOCK = threading.RLock()
_SETTINGS_CACHE_TTL = 30.0

_ACTION_POINTS_COUNTER_KEY = "__action_points__"
_COIN_INCOME_COUNTER_KEY = "__coin_income__"
_SOUL_POWER_INCOME_COUNTER_KEY = "__soul_power_income__"

_CATEGORY_LABELS: dict[str, str] = {
    "soulbone": "魂骨",
    "ambush": "暗器",
    "pill": "丹药",
    "material": "材料",
    "contract": "契约",
    "ticket": "凭证",
    "craft_material": "锻造材料",
    "soul_device": "魂导器",
    "battle_armor": "斗铠",
    "soul_core": "魂核",
}

_INVENTORY_CATEGORIES = [
    {"key": "soulbone", "label": "魂骨", "equip": True},
    {"key": "ambush", "label": "暗器", "equip": True},
    {"key": "pill", "label": "丹药", "equip": False},
    {"key": "material", "label": "材料", "equip": False},
    {"key": "contract", "label": "契约", "equip": False},
    {"key": "ticket", "label": "凭证", "equip": False},
    {"key": "craft_material", "label": "锻造材料", "equip": False},
    {"key": "soul_device", "label": "魂导器", "equip": True},
    {"key": "battle_armor", "label": "斗铠", "equip": True},
    {"key": "soul_core", "label": "魂核", "equip": True},
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _roll_range(config: dict[str, Any], min_key: str, max_key: str, default_min: int, default_max: int) -> int:
    low = _coerce_int(config.get(min_key), default_min)
    high = _coerce_int(config.get(max_key), default_max)
    if high < low:
        high = low
    return random.randint(low, high)


def _economy_day_key(now: datetime | None = None) -> str:
    return (now or datetime.utcnow()).strftime("%Y%m%d")


def _profile_display_name(display_name: str | None, username: str | None, tg: int) -> str:
    return str(display_name or username or f"魂师{tg}")


# 触发群播报的关键突破境界
BROADCAST_MILESTONE_REALMS = {"魂王", "魂帝", "魂圣", "魂斗罗", "封号斗罗", "神", "神王"}


def _build_douluo_broadcast_event(profile, result: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    """根据动作结果构造群播报事件;未达播报条件或关闭播报时返回 None。

    覆盖:关键突破、高阶魂环(万年及以上)、魂兽讨伐胜利(含稀有魂骨掉落)。
    """
    if not bool(settings.get("broadcast_enabled", True)):
        return None
    display = _profile_display_name(profile.display_name, profile.username, int(profile.tg))
    # 关键突破
    if result.get("success") and str(result.get("next_stage") or "") in BROADCAST_MILESTONE_REALMS:
        next_stage = result.get("next_stage")
        return {
            "kind": "breakthrough",
            "title": "斗罗突破播报",
            "text": (
                f"⚡ {display} 魂力贯通,冲破瓶颈,成功晋升【{next_stage}】!\n"
                "🌟 群中魂师,无不侧目。"
            ),
        }
    # 高阶魂环:猎杀吸收/替换万年及以上魂环
    ring = result.get("ring") or {}
    if str(ring.get("action") or "") in ("absorb", "replace") and int(result.get("years") or 0) >= 10000:
        region = result.get("region") or {}
        beast = result.get("beast") or {}
        color = str(result.get("color") or "")
        return {
            "kind": "high_ring",
            "title": "斗罗猎魂播报",
            "text": (
                f"🐾 {display} 于【{region.get('name')}】猎杀 {beast.get('name')},\n"
                f"💍 夺得 {result.get('years')}年高阶魂环!{color}色魂光冲天而起,群中魂师尽皆瞩目。"
            ),
        }
    # 血脉觉醒(珍品/神品)
    bloodline = result.get("bloodline") or {}
    if result.get("awakened") and str(bloodline.get("rarity") or "") in ("珍品", "神品"):
        return {
            "kind": "bloodline",
            "title": "斗罗血脉播报",
            "text": (
                f"🧬 {display} 觉醒稀有血脉【{bloodline.get('name')}】({bloodline.get('rarity')})!\n"
                f"🌀 {bloodline.get('system') or ''} 体系血脉流转周身,群中魂师尽皆动容。"
            ),
        }
    # 魂兽讨伐胜利(含稀有魂骨掉落)
    if result.get("win"):
        boss = result.get("boss") or {}
        rewards = result.get("rewards") or {}
        lines = [f"⚔️ {display} 讨伐成功,击败【{boss.get('name')}】!"]
        bone = (rewards or {}).get("soulbone") or {}
        if bone.get("name"):
            lines.append(f"🦴 稀有魂骨掉落:【{bone.get('name')}】({bone.get('rarity') or '未知'})")
        armor = (rewards or {}).get("armor") or {}
        if armor.get("name"):
            lines.append(f"🛡️ 天降斗铠:【{armor.get('name')}】")
        score = int(rewards.get("score") or 0)
        if score:
            lines.append(f"📈 讨伐战绩 +{score}")
        return {
            "kind": "boss",
            "title": "斗罗讨伐播报",
            "text": "\n".join(lines),
        }
    return None


# ---------------------------------------------------------------------------
# 设置
# ---------------------------------------------------------------------------
def get_settings() -> dict[str, Any]:
    global _SETTINGS_CACHE
    now = time.monotonic()
    with _SETTINGS_CACHE_LOCK:
        cached = _SETTINGS_CACHE
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1])
        with Session() as session:
            rows = session.query(DouluoSetting).all()
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        for row in rows:
            merged[str(row.setting_key)] = row.setting_value
        merged["exchange_rate"] = max(_coerce_int(merged.get("exchange_rate"), 100), 1)
        merged["min_coin_to_exchange"] = max(_coerce_int(merged.get("min_coin_to_exchange"), 1), 1)
        merged["coin_min_to_buy"] = max(_coerce_int(merged.get("coin_min_to_buy"), 1), 1)
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
        merged["daily_coin_soft_cap"] = max(_coerce_int(merged.get("daily_coin_soft_cap"), 650), 0)
        merged["daily_coin_hard_cap"] = max(_coerce_int(merged.get("daily_coin_hard_cap"), 1000), 0)
        if 0 < merged["daily_coin_hard_cap"] < merged["daily_coin_soft_cap"]:
            merged["daily_coin_hard_cap"] = merged["daily_coin_soft_cap"]
        merged["daily_coin_overflow_percent"] = min(
            max(_coerce_int(merged.get("daily_coin_overflow_percent"), 20), 0), 100
        )
        merged["daily_soul_power_soft_cap"] = max(_coerce_int(merged.get("daily_soul_power_soft_cap"), 400), 0)
        merged["daily_soul_power_hard_cap"] = max(_coerce_int(merged.get("daily_soul_power_hard_cap"), 700), 0)
        if 0 < merged["daily_soul_power_hard_cap"] < merged["daily_soul_power_soft_cap"]:
            merged["daily_soul_power_hard_cap"] = merged["daily_soul_power_soft_cap"]
        merged["soul_power_overflow_percent"] = min(
            max(_coerce_int(merged.get("soul_power_overflow_percent"), 20), 0), 100
        )
        merged["wuhun_reforge_coin"] = max(_coerce_int(merged.get("wuhun_reforge_coin"), 500), 0)
        merged["wuhun_reforge_cd_hours"] = max(_coerce_int(merged.get("wuhun_reforge_cd_hours"), 24), 0)
        merged["hunt_absorb_fee"] = max(_coerce_int(merged.get("hunt_absorb_fee"), 200), 0)
        merged["duel_min_stake"] = max(_coerce_int(merged.get("duel_min_stake"), 0), 0)
        merged["duel_max_stake"] = max(_coerce_int(merged.get("duel_max_stake"), 500), merged["duel_min_stake"])
        merged["duel_prepare_seconds"] = min(max(_coerce_int(merged.get("duel_prepare_seconds"), 8), 0), 600)
        merged["event_chance_percent"] = min(max(_coerce_int(merged.get("event_chance_percent"), 25), 0), 100)
        merged["auction_fee_percent"] = min(max(_coerce_int(merged.get("auction_fee_percent"), 5), 0), 50)
        merged["auction_duration_hours"] = max(_coerce_int(merged.get("auction_duration_hours"), 12), 1)
        merged["exchange_enabled"] = bool(merged.get("exchange_enabled", True))
        merged["broadcast_enabled"] = bool(merged.get("broadcast_enabled", True))
        merged["bloodline_awaken_coin"] = max(_coerce_int(merged.get("bloodline_awaken_coin"), 2000), 0)
        merged["bloodline_enhance_coin"] = max(_coerce_int(merged.get("bloodline_enhance_coin"), 800), 0)
        merged["bloodline_enhance_soul_power"] = max(_coerce_int(merged.get("bloodline_enhance_soul_power"), 2000), 0)
        merged["prospect_coin_cost"] = max(_coerce_int(merged.get("prospect_coin_cost"), 100), 0)
        merged["condense_coin_cost"] = max(_coerce_int(merged.get("condense_coin_cost"), 2000), 0)
        merged["condense_soul_power_cost"] = max(_coerce_int(merged.get("condense_soul_power_cost"), 3000), 0)
        merged["armor_upgrade_coin"] = max(_coerce_int(merged.get("armor_upgrade_coin"), 1500), 0)
        if not isinstance(merged.get("realm_thresholds"), list) or not merged.get("realm_thresholds"):
            merged["realm_thresholds"] = copy.deepcopy(DEFAULT_REALM_THRESHOLDS)
        _SETTINGS_CACHE = (now + _SETTINGS_CACHE_TTL, copy.deepcopy(merged))
        return merged


def set_settings(patch: dict[str, Any]) -> dict[str, Any]:
    global _SETTINGS_CACHE
    with _SETTINGS_CACHE_LOCK:
        with Session() as session:
            for key, value in patch.items():
                row = session.query(DouluoSetting).filter(DouluoSetting.setting_key == str(key)).first()
                if row is None:
                    row = DouluoSetting(setting_key=str(key), setting_value=value)
                    session.add(row)
                else:
                    row.setting_value = value
                    row.updated_at = utcnow()
            session.commit()
        _SETTINGS_CACHE = None
    return get_settings()


# ---------------------------------------------------------------------------
# 档案
# ---------------------------------------------------------------------------
def _new_profile(tg: int, *, display_name: str | None = None, username: str | None = None) -> DouluoProfile:
    return DouluoProfile(
        tg=int(tg),
        display_name=display_name,
        username=username,
        realm_stage="魂士",
        realm_stars=1,
        soul_power=0,
        coin=0,
        spirit_power=0,
    )


def upsert_profile_identity(tg: int, *, display_name: str | None = None, username: str | None = None) -> dict[str, Any]:
    tg = int(tg)
    with Session() as session:
        profile = session.query(DouluoProfile).filter(DouluoProfile.tg == tg).first()
        if profile is None:
            profile = _new_profile(tg, display_name=display_name, username=username)
            session.add(profile)
        else:
            changed = False
            if display_name is not None and str(display_name).strip() and str(profile.display_name or "") != str(display_name).strip():
                profile.display_name = str(display_name).strip()
                changed = True
            if username is not None and str(username).strip() and str(profile.username or "") != str(username).strip():
                profile.username = str(username).strip()
                changed = True
            if changed:
                profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
    return {"tg": tg, "display_name": profile.display_name, "username": profile.username}


def get_or_create_profile(tg: int) -> dict[str, Any]:
    tg = int(tg)
    with Session() as session:
        profile = session.query(DouluoProfile).filter(DouluoProfile.tg == tg).first()
        if profile is None:
            profile = _new_profile(tg)
            session.add(profile)
            session.commit()
            session.refresh(profile)
        payload = _serialize_profile_row(profile, session=session)
    return payload


def _serialize_profile_row(profile: DouluoProfile, *, session=None) -> dict[str, Any]:
    return {
        "tg": int(profile.tg),
        "display_name": profile.display_name,
        "username": profile.username,
        "realm_stage": profile.realm_stage,
        "realm_stars": int(profile.realm_stars),
        "soul_power": int(profile.soul_power),
        "coin": int(profile.coin),
        "spirit_power": int(profile.spirit_power),
        "innate_soul_power": int(profile.innate_soul_power),
        "wuhun": {
            "key": profile.wuhun_key,
            "name": profile.wuhun_name,
            "system": profile.wuhun_system,
            "quality": profile.wuhun_quality,
        },
        "breakthrough_failures": int(profile.breakthrough_failures),
        "sect_key": profile.sect_key,
        "sect_contribution": int(profile.sect_contribution),
        "sect_position": profile.sect_position,
        "boss_score": int(profile.boss_score),
        "arena_wins": int(profile.arena_wins),
        "arena_losses": int(profile.arena_losses),
        "total_hunts": int(profile.total_hunts),
        "last_train_at": profile.last_train_at,
        "last_breakthrough_at": profile.last_breakthrough_at,
        "bloodline": _bloodline_payload(profile),
        "craftsman": {
            "rank": max(int(profile.craftsman_rank or 1), 1),
            "exp": max(int(profile.craftsman_exp or 0), 0),
        },
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def _bloodline_payload(profile: DouluoProfile) -> dict[str, Any] | None:
    """档案序列化的血脉字段。"""
    if not profile.bloodline_key:
        return None
    from bot.plugins.douluo_game.core.bloodline import bloodline_power_per_level, get_bloodline

    bl = get_bloodline(profile.bloodline_key)
    level = max(int(profile.bloodline_level or 0), 0)
    if bl is None:
        return {"key": profile.bloodline_key, "name": profile.bloodline_key, "level": level}
    base = REALM_BASE_POWER.get(str(profile.realm_stage or "魂士"), 1000)
    per_level = bloodline_power_per_level(bl, base)
    return {
        "key": bl["key"],
        "name": bl["name"],
        "system": bl.get("system"),
        "rarity": bl.get("rarity"),
        "skill": bl.get("skill"),
        "description": bl.get("description"),
        "level": level,
        "power_per_level": per_level,
        "power": int(per_level * level),
    }


def _load_profile(session, tg: int, *, for_update: bool = False) -> DouluoProfile:
    query = session.query(DouluoProfile)
    if for_update:
        query = query.with_for_update()
    profile = query.filter(DouluoProfile.tg == int(tg)).first()
    if profile is None:
        profile = _new_profile(int(tg))
        session.add(profile)
        session.flush()
    return profile


def serialize_profile(
    tg: int,
    *,
    include_rings: bool = False,
    include_equipment: bool = False,
    include_actions: bool = False,
) -> dict[str, Any]:
    with Session() as session:
        profile = session.query(DouluoProfile).filter(DouluoProfile.tg == int(tg)).first()
        if profile is None:
            profile = _new_profile(int(tg))
            session.add(profile)
            session.flush()
        payload = _serialize_profile_row(profile, session=session)
        payload["battle_power"] = _compute_battle_power_session(session, profile)
        if include_rings:
            payload["rings"] = _rings_payload_session(session, profile.tg)
        if include_equipment:
            payload["equipment"] = _equipment_summary_session(session, profile.tg)
        if include_actions:
            payload["actions"] = _build_action_usage_session(session, profile.tg)
    return payload


# ---------------------------------------------------------------------------
# 武魂
# ---------------------------------------------------------------------------
def _roll_wuhun(profile: DouluoProfile) -> dict[str, Any]:
    from bot.plugins.douluo_game.core.wuhun import random_wuhun

    wuhun = random_wuhun()
    profile.wuhun_key = wuhun["key"]
    profile.wuhun_name = wuhun["name"]
    profile.wuhun_system = wuhun["system"]
    profile.wuhun_quality = wuhun["quality"]
    profile.innate_soul_power = random.randint(
        int(wuhun["innate_soul_power_min"]), int(wuhun["innate_soul_power_max"])
    )
    profile.updated_at = utcnow()
    return wuhun


def awaken_wuhun(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if profile.wuhun_key:
            raise ValueError("武魂已经觉醒,无法重复觉醒")
        cost = _coerce_int(settings.get("wuhun_awaken_coin"), 0)
        if int(profile.coin or 0) < cost:
            raise ValueError(f"觉醒武魂需要 {cost} 金魂币,当前不足")
        if cost > 0:
            profile.coin = int(profile.coin or 0) - cost
        wuhun = _roll_wuhun(profile)
        session.commit()
        session.refresh(profile)
    return {
        "tg": tg,
        "wuhun": wuhun,
        "innate_soul_power": profile.innate_soul_power,
        "coin": int(profile.coin or 0),
    }


def reforge_wuhun(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    cost = _coerce_int(settings.get("wuhun_reforge_coin"), 500)
    cd_hours = _coerce_int(settings.get("wuhun_reforge_cd_hours"), 24)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,无法重铸")
        if profile.reforge_at is not None:
            remaining = (profile.reforge_at - now).total_seconds()
            if remaining > 0:
                raise ValueError(f"武魂重铸冷却中,剩余 {int(remaining // 3600)} 小时")
        if int(profile.coin or 0) < cost:
            raise ValueError(f"重铸武魂需要 {cost} 金魂币,当前不足")
        profile.coin = int(profile.coin or 0) - cost
        profile.reforge_at = now + timedelta(hours=cd_hours)
        wuhun = _roll_wuhun(profile)
        session.commit()
        session.refresh(profile)
    return {
        "tg": tg,
        "wuhun": wuhun,
        "innate_soul_power": profile.innate_soul_power,
        "coin": int(profile.coin or 0),
        "reforge_at": profile.reforge_at,
    }


def get_wuhun_payload(tg: int) -> dict[str, Any]:
    from bot.plugins.douluo_game.core.wuhun import wuhun_by_key

    with Session() as session:
        profile = session.query(DouluoProfile).filter(DouluoProfile.tg == int(tg)).first()
        if profile is None or not profile.wuhun_key:
            return {}
        definition = wuhun_by_key(profile.wuhun_key) or {}
        rings = _rings_payload_session(session, int(tg))
        return {
            "key": profile.wuhun_key,
            "name": profile.wuhun_name,
            "system": profile.wuhun_system,
            "quality": profile.wuhun_quality,
            "description": definition.get("description", ""),
            "stats": definition.get("stats", {}),
            "innate_soul_power": int(profile.innate_soul_power),
            "unlocked_skills": [ring["skill_name"] for ring in rings if ring.get("skill_name")],
        }


# ---------------------------------------------------------------------------
# 行动力 / 每日限额
# ---------------------------------------------------------------------------
def _get_or_create_daily_counter_session(session, tg: int, day_key: str, action_type: str) -> DouluoDailyActionCounter:
    counter = (
        session.query(DouluoDailyActionCounter)
        .filter(
            DouluoDailyActionCounter.tg == int(tg),
            DouluoDailyActionCounter.day_key == str(day_key),
            DouluoDailyActionCounter.action_type == str(action_type),
        )
        .first()
    )
    if counter is None:
        counter = DouluoDailyActionCounter(
            tg=int(tg), day_key=str(day_key), action_type=str(action_type), used_count=0
        )
        session.add(counter)
        session.flush()
    return counter


def _action_point_cost(settings: dict[str, Any], action_type: str) -> int:
    raw_costs = settings.get("action_point_costs")
    if not isinstance(raw_costs, dict):
        raw_costs = DEFAULT_ACTION_POINT_COSTS
    return max(_coerce_int(raw_costs.get(str(action_type or "")), 1), 0)


def _daily_limit_for_action_type(settings: dict[str, Any], action_type: str) -> int:
    raw_limits = settings.get("daily_action_limits")
    if not isinstance(raw_limits, dict):
        raw_limits = DEFAULT_DAILY_ACTION_LIMITS
    return max(_coerce_int(raw_limits.get(str(action_type or "")), 0), 0)


def _check_daily_action_points(
    session,
    tg: int,
    action_type: str,
    settings: dict[str, Any],
    now: datetime,
) -> tuple[DouluoDailyActionCounter, int, int]:
    counter = _get_or_create_daily_counter_session(
        session, int(tg), _economy_day_key(now), _ACTION_POINTS_COUNTER_KEY
    )
    limit = max(_coerce_int(settings.get("daily_action_points"), 12), 0)
    cost = _action_point_cost(settings, action_type)
    if limit > 0 and int(counter.used_count or 0) + cost > limit:
        remaining = max(limit - int(counter.used_count or 0), 0)
        raise ValueError(f"今日行动力不足,需要 {cost} 点,当前剩余 {remaining} 点")
    return counter, limit, cost


def _consume_daily_action_points(counter: DouluoDailyActionCounter | None, cost: int) -> None:
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
) -> tuple[DouluoDailyActionCounter, int]:
    counter = _get_or_create_daily_counter_session(session, int(tg), _economy_day_key(now), str(action_type or ""))
    limit = _daily_limit_for_action_type(settings, action_type)
    if limit > 0 and int(counter.used_count or 0) >= limit:
        raise ValueError(f"今日{ACTION_TYPE_LABELS.get(action_type, action_type)}次数已用完（{counter.used_count}/{limit}）")
    return counter, limit


def _increment_daily_action_counter(counter: DouluoDailyActionCounter | None) -> None:
    if counter is None:
        return
    counter.used_count = int(counter.used_count or 0) + 1
    counter.updated_at = utcnow()


def _apply_daily_income_caps(
    session,
    tg: int,
    day_key: str,
    settings: dict[str, Any],
    *,
    coin: int = 0,
    soul_power: int = 0,
) -> dict[str, int]:
    """对金魂币/魂力施加每日软硬上限,超额按溢出比例折算,返回实际获得量。"""
    now = utcnow()
    coin_counter = None
    sp_counter = None
    if coin > 0:
        coin_counter = _get_or_create_daily_counter_session(session, int(tg), day_key, _COIN_INCOME_COUNTER_KEY)
    if soul_power > 0:
        sp_counter = _get_or_create_daily_counter_session(session, int(tg), day_key, _SOUL_POWER_INCOME_COUNTER_KEY)

    def apply_cap(counter, amount: int, soft_key: str, hard_key: str, overflow_key: str) -> int:
        soft = max(_coerce_int(settings.get(soft_key), 0), 0)
        hard = max(_coerce_int(settings.get(hard_key), 0), 0)
        overflow = min(max(_coerce_int(settings.get(overflow_key), 20), 0), 100)
        if amount <= 0:
            return 0
        earned = int(counter.used_count or 0)
        if hard > 0 and earned >= hard:
            return 0
        if hard > 0:
            amount = min(amount, hard - earned)
        if soft > 0 and earned < soft:
            inside = min(amount, soft - earned)
            outside = amount - inside
            if outside > 0 and overflow < 100:
                outside = int(outside * overflow / 100)
            amount = inside + outside
        counter.used_count = int(counter.used_count or 0) + amount
        counter.updated_at = utcnow()
        return amount

    gained_coin = apply_cap(coin_counter, coin, "daily_coin_soft_cap", "daily_coin_hard_cap", "daily_coin_overflow_percent") if coin_counter else coin
    gained_sp = apply_cap(sp_counter, soul_power, "daily_soul_power_soft_cap", "daily_soul_power_hard_cap", "soul_power_overflow_percent") if sp_counter else soul_power
    return {"coin": gained_coin, "soul_power": gained_sp}


def get_daily_action_usage(tg: int, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    day_key = _economy_day_key()
    with Session() as session:
        rows = (
            session.query(DouluoDailyActionCounter)
            .filter(DouluoDailyActionCounter.tg == int(tg), DouluoDailyActionCounter.day_key == day_key)
            .all()
        )
    usage: dict[str, dict[str, Any]] = {}
    for action_type, label in ACTION_TYPE_LABELS.items():
        limit = _daily_limit_for_action_type(settings, action_type)
        usage[action_type] = {
            "action_type": action_type,
            "label": label,
            "used": 0,
            "limit": limit,
            "remaining": max(limit, 0) if limit > 0 else None,
        }
    action_points_used = 0
    coin_income = 0
    sp_income = 0
    for row in rows:
        action_type = str(row.action_type or "")
        if action_type == _ACTION_POINTS_COUNTER_KEY:
            action_points_used = max(int(row.used_count or 0), 0)
            continue
        if action_type == _COIN_INCOME_COUNTER_KEY:
            coin_income = max(int(row.used_count or 0), 0)
            continue
        if action_type == _SOUL_POWER_INCOME_COUNTER_KEY:
            sp_income = max(int(row.used_count or 0), 0)
            continue
        bucket = usage.setdefault(
            action_type,
            {"action_type": action_type, "label": action_type, "used": 0, "limit": 0, "remaining": None},
        )
        bucket["used"] = int(row.used_count or 0)
        limit = int(bucket.get("limit") or 0)
        bucket["remaining"] = max(limit - bucket["used"], 0) if limit > 0 else None
    action_points_limit = max(_coerce_int(settings.get("daily_action_points"), 12), 0)
    return {
        "day_key": day_key,
        "items": usage,
        "action_points": {
            "used": action_points_used,
            "limit": action_points_limit,
            "remaining": max(action_points_limit - action_points_used, 0) if action_points_limit > 0 else None,
        },
        "coin_income": {
            "earned": coin_income,
            "soft_cap": max(_coerce_int(settings.get("daily_coin_soft_cap"), 0), 0),
            "hard_cap": max(_coerce_int(settings.get("daily_coin_hard_cap"), 0), 0),
        },
        "soul_power_income": {
            "earned": sp_income,
            "soft_cap": max(_coerce_int(settings.get("daily_soul_power_soft_cap"), 0), 0),
            "hard_cap": max(_coerce_int(settings.get("daily_soul_power_hard_cap"), 0), 0),
        },
    }


def _build_action_usage_session(session, tg: int) -> dict[str, Any]:
    day_key = _economy_day_key()
    rows = (
        session.query(DouluoDailyActionCounter)
        .filter(DouluoDailyActionCounter.tg == int(tg), DouluoDailyActionCounter.day_key == day_key)
        .all()
    )
    used: dict[str, int] = {}
    for row in rows:
        used[str(row.action_type or "")] = int(row.used_count or 0)
    return {"day_key": day_key, "used": used}


# ---------------------------------------------------------------------------
# 战力计算
# ---------------------------------------------------------------------------
def _rings_payload_session(session, tg: int) -> list[dict[str, Any]]:
    rows = (
        session.query(DouluoSoulRing)
        .filter(DouluoSoulRing.tg == int(tg))
        .order_by(DouluoSoulRing.slot.asc())
        .all()
    )
    return [
        {
            "slot": int(row.slot),
            "years": int(row.years),
            "tier": row.tier,
            "color": row.color,
            "source_name": row.source_name or "",
            "skill_name": row.skill_name,
            "attack": int(row.attack),
            "defense": int(row.defense),
            "speed": int(row.speed),
            "spirit": int(row.spirit),
        }
        for row in rows
    ]


def _equipment_summary_session(session, tg: int) -> dict[str, Any]:
    rows = (
        session.query(DouluoInventoryItem)
        .filter(DouluoInventoryItem.tg == int(tg), DouluoInventoryItem.equipped_slot.isnot(None))
        .all()
    )
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        slot = str(row.equipped_slot or "")
        summary[slot] = {
            "item_key": row.item_key,
            "name": row.name,
            "category": row.category,
            "rarity": row.rarity,
            "slot": slot,
            "attack": int((row.item_meta or {}).get("attack", 0)),
            "defense": int((row.item_meta or {}).get("defense", 0)),
            "speed": int((row.item_meta or {}).get("speed", 0)),
            "spirit": int((row.item_meta or {}).get("spirit", 0)),
            "trigger_chance": (row.item_meta or {}).get("trigger_chance"),
            "skill": (row.item_meta or {}).get("skill"),
            "tier": (row.item_meta or {}).get("tier"),
        }
    return summary


def _compute_battle_power_session(session, profile: DouluoProfile) -> int:
    realm_stage = str(profile.realm_stage or "魂士")
    realm_stars = max(int(profile.realm_stars or 1), 1)
    base = REALM_BASE_POWER.get(realm_stage, 1000)
    power = base + base * (realm_stars - 1) * 0.12

    if profile.wuhun_key and profile.wuhun_quality:
        quality_mult = WUHUN_QUALITY_POWER.get(str(profile.wuhun_quality), 1.0)
        system_mult = WUHUN_SYSTEM_POWER.get(str(profile.wuhun_system), 1.0)
        power += max(int(profile.innate_soul_power or 0), 0) * 140 * quality_mult * system_mult

    rings = _rings_payload_session(session, int(profile.tg))
    for ring in rings:
        power += int(ring["attack"]) * 8 + int(ring["defense"]) * 6 + int(ring["speed"]) * 10 + int(ring["spirit"]) * 12

    equipment = _equipment_summary_session(session, int(profile.tg))
    for slot, item in equipment.items():
        power += int(item.get("attack") or 0) * 6
        power += int(item.get("defense") or 0) * 6
        power += int(item.get("speed") or 0) * 8

    power += max(int(profile.spirit_power or 0), 0) * 3
    power += int(profile.sect_contribution or 0) // 10
    bloodline = _bloodline_payload(profile)
    if bloodline:
        power += int(bloodline.get("power") or 0)
    return int(power)


def compute_battle_power(tg: int) -> int:
    with Session() as session:
        profile = _load_profile(session, int(tg))
        power = _compute_battle_power_session(session, profile)
    return power


def _rank_by_threshold(value: int, rows: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    current = rows[0] if rows else {}
    for row in rows:
        if int(value) >= int(row.get(value_key) or 0):
            current = row
        else:
            break
    return current


# ---------------------------------------------------------------------------
# 修炼 / 突破
# ---------------------------------------------------------------------------
def train_soul_power(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先使用 /dl_wuhun 觉醒武魂再修炼")
        action_counter, _, _ = _check_daily_action_points(session, tg, "train", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "train", settings, now)
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "train"))
        _increment_daily_action_counter(daily_counter)

        soul_power_raw = _roll_range(settings, "train_soul_power_min", "train_soul_power_max", 30, 60)
        coin_raw = _roll_range(settings, "train_coin_min", "train_coin_max", 20, 45)
        gained = _apply_daily_income_caps(
            session, tg, _economy_day_key(now), settings, coin=coin_raw, soul_power=soul_power_raw
        )
        profile.soul_power = int(profile.soul_power or 0) + gained["soul_power"]
        profile.coin = int(profile.coin or 0) + gained["coin"]
        profile.last_train_at = now
        profile.updated_at = utcnow()

        event = _maybe_trigger_event(session, profile, "train", settings)

        usage = _build_action_usage_session(session, tg)
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    try:
        from bot.sql_helper.sql_douluo.daily_service import report_task_progress

        report_task_progress(tg, "train", 1)
    except Exception:
        pass
    return {
        "tg": tg,
        "soul_power_gained": gained["soul_power"],
        "coin_gained": gained["coin"],
        "event": event,
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
        "usage": usage,
    }


def _maybe_trigger_event(session, profile: DouluoProfile, trigger: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    chance = min(max(_coerce_int(settings.get("event_chance_percent"), 25), 0), 100)
    if random.randint(1, 100) > chance:
        return None
    from bot.plugins.douluo_game.core.events import roll_event

    event = roll_event(trigger)
    if event is None:
        return None
    # 应用奇遇结果
    gained_coin = 0
    gained_sp = 0
    text = event.get("text", "")
    for outcome in event.get("outcomes", []):
        out_type = str(outcome.get("type") or "")
        out_min = _coerce_int(outcome.get("min"), 0)
        out_max = _coerce_int(outcome.get("max"), 0)
        if out_type in ("coin", "loss_coin"):
            amount = random.randint(out_min, out_max) if out_max >= out_min else 0
            if out_type == "coin":
                gained_coin += amount
            else:
                profile.coin = max(int(profile.coin or 0) - amount, 0)
        elif out_type in ("soul_power", "loss_soul_power"):
            amount = random.randint(out_min, out_max) if out_max >= out_min else 0
            if out_type == "soul_power":
                gained_sp += amount
            else:
                profile.soul_power = max(int(profile.soul_power or 0) - amount, 0)
        elif out_type == "soulbone":
            from bot.plugins.douluo_game.core.soulbone import random_soulbone_by_rarity

            bone = random_soulbone_by_rarity("千年")
            if bone:
                granted = _grant_inventory_item_session(session, int(profile.tg), bone["key"], 1)
                if granted:
                    text = f"{text}\n获得魂骨【{bone['name']}】"
        elif out_type == "item":
            item_key = str(outcome.get("item_key") or "").strip()
            if item_key:
                granted = _grant_inventory_item_session(session, int(profile.tg), item_key, 1)
                if granted:
                    text = f"{text}\n获得道具 {item_key}"
    if gained_coin > 0:
        profile.coin = int(profile.coin or 0) + gained_coin
    if gained_sp > 0:
        profile.soul_power = int(profile.soul_power or 0) + gained_sp
    profile.updated_at = utcnow()
    return {
        "key": event.get("key"),
        "title": event.get("title", ""),
        "text": text,
        "coin": gained_coin,
        "soul_power": gained_sp,
    }


def breakthrough(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先觉醒武魂再尝试突破")
        stage = str(profile.realm_stage or "魂士")
        rule = BREAKTHROUGH_RULES.get(stage)
        if rule is None:
            raise ValueError("已达最高境界")
        current_realm = next((r for r in settings.get("realm_thresholds", []) if r.get("stage") == stage), None)
        star_cap = int(current_realm["star_cap"]) if current_realm else 9
        if int(profile.realm_stars or 0) < star_cap:
            raise ValueError(f"当前 {stage} 未满星({profile.realm_stars}/{star_cap}),无法突破")
        action_counter, _, _ = _check_daily_action_points(session, tg, "breakthrough", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "breakthrough", settings, now)
        cost = _coerce_int(rule.get("coin_cost"), 100)
        if int(profile.coin or 0) < cost:
            raise ValueError(f"突破需要 {cost} 金魂币,当前不足")
        profile.coin = int(profile.coin or 0) - cost
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "breakthrough"))
        _increment_daily_action_counter(daily_counter)

        pity_after = max(_coerce_int(rule.get("pity_after"), 3), 1)
        success_percent = int(_coerce_int(rule.get("success_percent"), 60))
        fail_count = int(profile.breakthrough_failures or 0)
        if fail_count >= pity_after:
            success_percent = 100
        success = random.randint(1, 100) <= success_percent
        next_stage: str | None = None
        if success:
            idx = realm_index(stage)
            stages = realm_stages()
            if idx + 1 < len(stages):
                next_stage = stages[idx + 1]
                profile.realm_stage = next_stage
                profile.realm_stars = 1
                profile.breakthrough_failures = 0
                if next_stage == "封号斗罗":
                    profile.display_name = None
                title_note = ""
                if next_stage == "封号斗罗":
                    title_note = f"\n获得封号:【{random.choice(TITLED_DOULUO_TITLES)}斗罗】"
                result_text = f"突破成功,晋升【{next_stage}】!{title_note}"
            else:
                result_text = "已至巅峰,无法继续突破"
        else:
            profile.breakthrough_failures = fail_count + 1
            loss = max(int(profile.soul_power or 0) // 20, 1)
            profile.soul_power = max(int(profile.soul_power or 0) - loss, 0)
            result_text = f"突破失败,损失 {loss} 魂力(保底 {profile.breakthrough_failures}/{pity_after} 次)"
        profile.last_breakthrough_at = now
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "success": success,
        "next_stage": next_stage,
        "result_text": result_text,
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


# ---------------------------------------------------------------------------
# 物品目录 / 背包 / 装备
# ---------------------------------------------------------------------------
def _serialize_item_definition_row(row: DouluoItemDefinition) -> dict[str, Any]:
    return {
        "item_key": row.item_key,
        "name": row.name,
        "category": row.category,
        "rarity": row.rarity,
        "description": row.description,
        "icon": row.icon,
        "equipment_slot": row.equipment_slot,
        "attack": int(row.attack or 0),
        "defense": int(row.defense or 0),
        "speed": int(row.speed or 0),
        "spirit": int(row.spirit or 0),
        "trigger_chance": row.trigger_chance,
        "skill": row.skill,
        "recipe_config": row.recipe_config,
        "drop_sources": row.drop_sources,
        "version": int(row.version or 1),
        "enabled": bool(row.enabled),
        "is_builtin": bool(row.is_builtin),
    }


def _builtin_item_definitions() -> list[dict[str, Any]]:
    from bot.plugins.douluo_game.core.soulbone import SOULBONE_CATALOG
    from bot.plugins.douluo_game.core.ambush import AMBUSH_CATALOG

    definitions: list[dict[str, Any]] = []
    for bone in SOULBONE_CATALOG:
        stats = bone.get("stats", {})
        definitions.append(
            {
                "item_key": bone["key"],
                "name": bone["name"],
                "category": "soulbone",
                "rarity": bone.get("rarity", "十年"),
                "description": bone.get("description", ""),
                "equipment_slot": bone.get("part"),
                "attack": int(stats.get("attack", 0)),
                "defense": int(stats.get("defense", 0)),
                "speed": int(stats.get("speed", 0)),
                "skill": bone.get("skill"),
                "is_builtin": True,
            }
        )
    for weapon in AMBUSH_CATALOG:
        definitions.append(
            {
                "item_key": weapon["key"],
                "name": weapon["name"],
                "category": "ambush",
                "rarity": weapon.get("rarity", "凡品"),
                "description": weapon.get("description", ""),
                "equipment_slot": "weapon",
                "attack": int(weapon.get("attack", 0)),
                "defense": 0,
                "speed": 0,
                "trigger_chance": float(weapon.get("trigger_chance") or 0),
                "is_builtin": True,
            }
        )
    # 锻造材料
    for material in MATERIAL_CATALOG:
        definitions.append(
            {
                "item_key": material["key"],
                "name": material["name"],
                "category": "craft_material",
                "rarity": material.get("rarity", "凡品"),
                "description": material.get("description", ""),
                "is_builtin": True,
            }
        )
    # 魂导器(含锻造配方)
    for device in SOUL_DEVICE_CATALOG:
        definitions.append(
            {
                "item_key": device["key"],
                "name": device["name"],
                "category": "soul_device",
                "rarity": device.get("rarity", "良品"),
                "description": device.get("description", ""),
                "equipment_slot": device.get("equipment_slot"),
                "attack": int(device.get("attack", 0)),
                "defense": int(device.get("defense", 0)),
                "speed": int(device.get("speed", 0)),
                "spirit": int(device.get("spirit", 0)),
                "trigger_chance": device.get("trigger_chance"),
                "skill": device.get("skill"),
                "recipe_config": {
                    "materials": dict(device.get("recipe") or {}),
                    "coin": int(device.get("craft_coin") or 0),
                    "craftsman_rank": max(int(device.get("craftsman_rank") or 1), 1),
                },
                "is_builtin": True,
            }
        )
    # 斗铠(基础一字斗铠;升级在 item_meta.tier 上推进)
    armor_base = BATTLE_ARMOR_TIERS[0] if BATTLE_ARMOR_TIERS else {}
    definitions.append(
        {
            "item_key": BATTLE_ARMOR_ITEM_KEY,
            "name": armor_base.get("name", "一字斗铠"),
            "category": "battle_armor",
            "rarity": armor_base.get("rarity", "凡品"),
            "description": armor_base.get("description", ""),
            "equipment_slot": EQUIP_SLOT_BATTLE_ARMOR,
            "attack": int(armor_base.get("attack", 0)),
            "defense": int(armor_base.get("defense", 0)),
            "speed": int(armor_base.get("speed", 0)),
            "spirit": int(armor_base.get("spirit", 0)),
            "trigger_chance": armor_base.get("trigger_chance"),
            "skill": armor_base.get("skill"),
            "is_builtin": True,
        }
    )
    # 魂核
    for core in SOUL_CORE_TIERS:
        definitions.append(
            {
                "item_key": core["item_key"],
                "name": core["name"],
                "category": "soul_core",
                "rarity": core.get("rarity", "凡品"),
                "description": core.get("description", ""),
                "equipment_slot": EQUIP_SLOT_SOUL_CORE,
                "attack": int(core.get("attack", 0)),
                "defense": int(core.get("defense", 0)),
                "speed": int(core.get("speed", 0)),
                "spirit": int(core.get("spirit", 0)),
                "trigger_chance": core.get("trigger_chance"),
                "skill": core.get("skill"),
                "is_builtin": True,
            }
        )
    return definitions


def _sync_builtin_item_definitions(session) -> None:
    existing = {row.item_key for row in session.query(DouluoItemDefinition).all()}
    for definition in _builtin_item_definitions():
        if definition["item_key"] in existing:
            continue
        session.add(
            DouluoItemDefinition(
                item_key=definition["item_key"],
                name=definition["name"],
                category=definition["category"],
                rarity=definition["rarity"],
                description=definition.get("description"),
                equipment_slot=definition.get("equipment_slot"),
                attack=definition.get("attack", 0),
                defense=definition.get("defense", 0),
                speed=definition.get("speed", 0),
                spirit=definition.get("spirit", 0),
                trigger_chance=definition.get("trigger_chance"),
                skill=definition.get("skill"),
                recipe_config=definition.get("recipe_config"),
                version=1,
                enabled=True,
                is_builtin=True,
            )
        )


def _item_definition_snapshot(row: DouluoItemDefinition | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return _serialize_item_definition_row(row)


def list_item_definitions(*, include_disabled: bool = True) -> list[dict[str, Any]]:
    with Session() as session:
        _sync_builtin_item_definitions(session)
        session.commit()
        query = session.query(DouluoItemDefinition).order_by(DouluoItemDefinition.category.asc())
        if not include_disabled:
            query = query.filter(DouluoItemDefinition.enabled.is_(True))
        rows = query.all()
    return [_serialize_item_definition_row(row) for row in rows]


def get_item_definition(item_key: str) -> dict[str, Any] | None:
    item_key = str(item_key or "").strip()
    with Session() as session:
        _sync_builtin_item_definitions(session)
        session.commit()
        row = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == item_key).first()
    return _item_definition_snapshot(row)


def _serialize_inventory_row(row: DouluoInventoryItem) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "tg": int(row.tg),
        "item_key": row.item_key,
        "category": row.category,
        "name": row.name,
        "rarity": row.rarity,
        "quantity": int(row.quantity or 0),
        "equipped_slot": row.equipped_slot,
        "item_meta": row.item_meta or {},
    }


def _grant_inventory_item_session(
    session,
    tg: int,
    item_key: str,
    quantity: int = 1,
    *,
    meta: dict[str, Any] | None = None,
    allow_disabled: bool = False,
) -> dict[str, Any] | None:
    definition = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == str(item_key)).first()
    if definition is None or (not definition.enabled and not allow_disabled):
        _sync_builtin_item_definitions(session)
        session.flush()
        definition = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == str(item_key)).first()
        if definition is None or (not definition.enabled and not allow_disabled):
            return None
    row = (
        session.query(DouluoInventoryItem)
        .filter(DouluoInventoryItem.tg == int(tg), DouluoInventoryItem.item_key == str(item_key))
        .with_for_update()
        .first()
    )
    quantity = max(int(quantity or 1), 1)
    if row is None:
        row = DouluoInventoryItem(
            tg=int(tg),
            item_key=item_key,
            category=definition.category,
            name=definition.name,
            rarity=definition.rarity,
            quantity=quantity,
            item_meta=meta or {},
        )
        session.add(row)
    else:
        row.quantity = int(row.quantity or 0) + quantity
        if meta:
            merged = dict(row.item_meta or {})
            merged.update(meta)
            row.item_meta = merged
        row.updated_at = utcnow()
    session.flush()
    return _serialize_inventory_row(row)


def _consume_inventory_item_session(session, tg: int, item_key: str, quantity: int) -> dict[str, Any] | None:
    row = (
        session.query(DouluoInventoryItem)
        .filter(DouluoInventoryItem.tg == int(tg), DouluoInventoryItem.item_key == str(item_key))
        .with_for_update()
        .first()
    )
    if row is None or int(row.quantity or 0) < quantity:
        return None
    row.quantity = int(row.quantity or 0) - int(quantity)
    if int(row.quantity or 0) <= 0:
        if row.equipped_slot:
            row.equipped_slot = None
            row.quantity = 0
        else:
            session.delete(row)
    else:
        row.updated_at = utcnow()
    session.flush()
    return _serialize_inventory_row(row)


def grant_inventory_item(tg: int, item_key: str, quantity: int = 1) -> dict[str, Any] | None:
    with Session() as session:
        result = _grant_inventory_item_session(session, int(tg), str(item_key), quantity)
        session.commit()
    return result


def consume_inventory_item(tg: int, item_key: str, quantity: int = 1) -> dict[str, Any] | None:
    with Session() as session:
        result = _consume_inventory_item_session(session, int(tg), str(item_key), quantity)
        session.commit()
    return result


def list_player_inventory_grouped(tg: int) -> dict[str, Any]:
    with Session() as session:
        rows = (
            session.query(DouluoInventoryItem)
            .filter(DouluoInventoryItem.tg == int(tg))
            .order_by(DouluoInventoryItem.category.asc(), DouluoInventoryItem.item_key.asc())
            .all()
        )
        items = [_serialize_inventory_row(row) for row in rows]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item["category"]), []).append(item)
    return {"tg": int(tg), "categories": grouped, "items": items}


def get_equipment_summary(tg: int) -> dict[str, Any]:
    with Session() as session:
        summary = _equipment_summary_session(session, int(tg))
    return {"tg": int(tg), "equipment": summary}


def equip_inventory_item(tg: int, item_key: str) -> dict[str, Any]:
    item_key = str(item_key or "").strip()
    with Session() as session:
        row = (
            session.query(DouluoInventoryItem)
            .filter(DouluoInventoryItem.tg == int(tg), DouluoInventoryItem.item_key == item_key)
            .first()
        )
        if row is None or int(row.quantity or 0) <= 0:
            raise ValueError("背包中没有该物品")
        definition = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == item_key).first()
        if definition is None:
            raise ValueError("物品不存在")
        target_slot = str(definition.equipment_slot or "").strip()
        if not target_slot:
            raise ValueError("该物品无法装备")
        # 卸下同槽位旧装备
        old_rows = (
            session.query(DouluoInventoryItem)
            .filter(DouluoInventoryItem.tg == int(tg), DouluoInventoryItem.equipped_slot == target_slot)
            .all()
        )
        for old in old_rows:
            old.equipped_slot = None
            old.updated_at = utcnow()
        row.equipped_slot = target_slot
        row.updated_at = utcnow()
        meta = dict(row.item_meta or {})
        meta.update(
            {
                "attack": int(definition.attack or 0),
                "defense": int(definition.defense or 0),
                "speed": int(definition.speed or 0),
                "spirit": int(definition.spirit or 0),
                "trigger_chance": definition.trigger_chance,
                "skill": definition.skill,
            }
        )
        row.item_meta = meta
        session.commit()
        session.refresh(row)
        summary = _equipment_summary_session(session, int(tg))
    return {"tg": int(tg), "item_key": item_key, "slot": target_slot, "equipment": summary}


def unequip_inventory_item(tg: int, slot: str) -> dict[str, Any]:
    slot = str(slot or "").strip()
    with Session() as session:
        row = (
            session.query(DouluoInventoryItem)
            .filter(DouluoInventoryItem.tg == int(tg), DouluoInventoryItem.equipped_slot == slot)
            .first()
        )
        if row is None:
            raise ValueError("该槽位未装备物品")
        row.equipped_slot = None
        row.updated_at = utcnow()
        session.commit()
        summary = _equipment_summary_session(session, int(tg))
    return {"tg": int(tg), "slot": slot, "equipment": summary}


def soulbone_equipment_bonus(tg: int) -> dict[str, int]:
    with Session() as session:
        summary = _equipment_summary_session(session, int(tg))
    attack = defense = speed = 0
    for item in summary.values():
        if str(item.get("category")) == "ambush":
            attack += int(item.get("attack") or 0)
        else:
            attack += int(item.get("attack") or 0)
            defense += int(item.get("defense") or 0)
            speed += int(item.get("speed") or 0)
    return {"attack": attack, "defense": defense, "speed": speed}


# ---------------------------------------------------------------------------
# 兑换(金魂币 <-> Emby 碎片)
# ---------------------------------------------------------------------------
def _preview_exchange(direction: str, amount: int, settings: dict[str, Any]) -> dict[str, Any]:
    rate = max(_coerce_int(settings.get("exchange_rate"), 100), 1)
    if direction == "coin_to_fragment":
        gross_fragment = max(int(amount or 0), 0) * rate
        return {"received_fragment": gross_fragment}
    if direction == "fragment_to_coin":
        requested = max(int(amount or 0), 0)
        gross_coin = requested // rate
        spent_fragment = gross_coin * rate
        return {"received_coin": gross_coin, "spent_fragment": spent_fragment, "remainder": requested - spent_fragment}
    raise ValueError("Unsupported exchange direction")


def exchange_currency(tg: int, direction: str, amount: int) -> dict[str, Any]:
    amount = max(int(amount or 0), 0)
    if amount <= 0:
        raise ValueError("兑换数量必须大于 0")
    settings = get_settings()
    if not bool(settings.get("exchange_enabled", True)):
        raise ValueError("兑换功能当前未开启")
    tg = int(tg)
    preview = _preview_exchange(direction, amount, settings)
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        account = session.query(Emby).filter(Emby.tg == tg).with_for_update().first()
        if account is None:
            raise ValueError("Emby 账号不存在")
        if direction == "coin_to_fragment":
            received = int(preview["received_fragment"])
            if received <= 0:
                raise ValueError("当前比例下可兑换碎片不足 1")
            if int(profile.coin or 0) < amount:
                raise ValueError("金魂币不足")
            profile.coin = int(profile.coin or 0) - amount
            account.iv = int(account.iv or 0) + received
            title = "魂币兑换碎片"
            detail = f"消耗金魂币 {amount},获得碎片 {received}"
        elif direction == "fragment_to_coin":
            minimum = max(_coerce_int(settings.get("min_coin_to_exchange"), 1), 1)
            if amount < minimum:
                raise ValueError(f"最低需 {minimum} 碎片")
            received_coin = int(preview["received_coin"])
            spent_fragment = int(preview["spent_fragment"])
            if received_coin <= 0 or spent_fragment <= 0:
                raise ValueError("当前比例下可兑换魂币不足 1")
            if int(account.iv or 0) < spent_fragment:
                raise ValueError("Emby 碎片不足")
            account.iv = int(account.iv or 0) - spent_fragment
            profile.coin = int(profile.coin or 0) + received_coin
            title = "碎片兑换魂币"
            detail = f"消耗碎片 {spent_fragment},获得金魂币 {received_coin}"
        else:
            raise ValueError("Unsupported exchange direction")
        profile.updated_at = utcnow()
        session.add(DouluoJournal(tg=tg, action_type="exchange", title=title, detail=detail))
        session.commit()
        session.refresh(profile)
        session.refresh(account)
        balance = int(account.iv or 0)
    return {
        "direction": direction,
        "coin": int(profile.coin or 0),
        "emby_fragment": balance,
        "title": title,
        "detail": detail,
    }


def get_economy_snapshot(tg: int, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    tg = int(tg)
    with Session() as session:
        profile = session.query(DouluoProfile).filter(DouluoProfile.tg == tg).first()
    rate = max(_coerce_int(settings.get("exchange_rate"), 100), 1)
    return {
        "coin": int(profile.coin or 0) if profile else 0,
        "emby_fragment": get_emby_balance(tg),
        "exchange_rate": rate,
        "exchange_enabled": bool(settings.get("exchange_enabled", True)),
        "min_coin_to_exchange": max(_coerce_int(settings.get("min_coin_to_exchange"), 1), 1),
    }


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
def create_journal(tg: int, action_type: str, title: str, detail: str = "") -> dict[str, Any]:
    tg = int(tg)
    with Session() as session:
        row = DouluoJournal(tg=tg, action_type=str(action_type), title=str(title), detail=str(detail))
        session.add(row)
        session.commit()
        session.refresh(row)
    return {"id": int(row.id), "tg": tg, "action_type": row.action_type, "title": row.title, "detail": row.detail}


def list_recent_journals(tg: int, limit: int = 20) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(DouluoJournal)
            .filter(DouluoJournal.tg == int(tg))
            .order_by(DouluoJournal.created_at.desc())
            .limit(max(int(limit), 1))
            .all()
        )
    return [
        {"id": int(row.id), "action_type": row.action_type, "title": row.title, "detail": row.detail, "created_at": row.created_at}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 排行榜
# ---------------------------------------------------------------------------
def build_douluo_leaderboard(kind: str, limit: int = 10) -> dict[str, Any]:
    kind = str(kind or "power").strip().lower()
    limit = min(max(int(limit or 10), 1), 50)
    with Session() as session:
        if kind in ("ring", "rings", "hunt"):
            rows = (
                session.query(DouluoProfile, DouluoSoulRing)
                .join(DouluoSoulRing, DouluoSoulRing.tg == DouluoProfile.tg)
                .all()
            )
            total_years: dict[int, int] = {}
            for profile, ring in rows:
                total_years[int(profile.tg)] = total_years.get(int(profile.tg), 0) + int(ring.years or 0)
            profiles = session.query(DouluoProfile).all()
            ranking = []
            for profile in profiles:
                ranking.append(
                    {
                        "tg": int(profile.tg),
                        "display_name": _profile_display_name(profile.display_name, profile.username, profile.tg),
                        "value": total_years.get(int(profile.tg), 0),
                        "sub": f"{profile.realm_stage}{profile.realm_stars}星",
                    }
                )
            ranking.sort(key=lambda item: item["value"], reverse=True)
            return {"kind": kind, "label": "魂环年限", "items": ranking[:limit]}
        if kind in ("coin", "coins"):
            rows = session.query(DouluoProfile).order_by(DouluoProfile.coin.desc()).limit(limit).all()
            ranking = [
                {
                    "tg": int(profile.tg),
                    "display_name": _profile_display_name(profile.display_name, profile.username, profile.tg),
                    "value": int(profile.coin or 0),
                    "sub": f"{profile.realm_stage}{profile.realm_stars}星",
                }
                for profile in rows
            ]
            return {"kind": kind, "label": "金魂币", "items": ranking}
        # 默认:战力
        profiles = session.query(DouluoProfile).all()
        ranking = []
        for profile in profiles:
            ranking.append(
                {
                    "tg": int(profile.tg),
                    "display_name": _profile_display_name(profile.display_name, profile.username, profile.tg),
                    "value": _compute_battle_power_session(session, profile),
                    "sub": f"{profile.realm_stage}{profile.realm_stars}星",
                }
            )
        ranking.sort(key=lambda item: item["value"], reverse=True)
        return {"kind": kind, "label": "综合战力", "items": ranking[:limit]}


# ---------------------------------------------------------------------------
# 斗魂
# ---------------------------------------------------------------------------
def compute_duel_preview(challenger_tg: int, defender_tg: int, stake: int) -> dict[str, Any]:
    settings = get_settings()
    challenger_tg = int(challenger_tg)
    defender_tg = int(defender_tg)
    with Session() as session:
        challenger = _load_profile(session, challenger_tg)
        defender = _load_profile(session, defender_tg)
        challenger_power = _compute_battle_power_session(session, challenger)
        defender_power = _compute_battle_power_session(session, defender)
        challenger_coin = int(challenger.coin or 0)
        defender_coin = int(defender.coin or 0)
    stake = max(int(stake or 0), 0)
    max_stake = max(_coerce_int(settings.get("duel_max_stake"), 500), _coerce_int(settings.get("duel_min_stake"), 0))
    if stake > max_stake:
        raise ValueError(f"押注超过上限 {max_stake}")
    diff = challenger_power - defender_power
    return {
        "challenger_tg": challenger_tg,
        "defender_tg": defender_tg,
        "challenger_name": _profile_display_name(challenger.display_name, challenger.username, challenger_tg),
        "defender_name": _profile_display_name(defender.display_name, defender.username, defender_tg),
        "challenger_power": challenger_power,
        "defender_power": defender_power,
        "challenger_coin": challenger_coin,
        "defender_coin": defender_coin,
        "power_diff": diff,
        "stake": stake,
        "challenger_win_chance": round(min(max(0.5 + diff / 200000.0, 0.05), 0.95), 4),
    }


def resolve_duel(challenger_tg: int, defender_tg: int, stake: int) -> dict[str, Any]:
    settings = get_settings()
    challenger_tg = int(challenger_tg)
    defender_tg = int(defender_tg)
    if challenger_tg == defender_tg:
        raise ValueError("不能向自己发起斗魂")
    stake = max(int(stake or 0), 0)
    min_stake = max(_coerce_int(settings.get("duel_min_stake"), 0), 0)
    max_stake = max(_coerce_int(settings.get("duel_max_stake"), 500), min_stake)
    if stake < min_stake:
        raise ValueError(f"押注不能低于 {min_stake}")
    if stake > max_stake:
        raise ValueError(f"押注不能超过 {max_stake}")
    with Session() as session:
        # 按固定 TG 顺序加锁，避免 A→B 与 B→A 同时结算时形成反向锁死。
        locked = {
            tg_value: _load_profile(session, tg_value, for_update=True)
            for tg_value in sorted((challenger_tg, defender_tg))
        }
        challenger = locked[challenger_tg]
        defender = locked[defender_tg]
        challenger_power = _compute_battle_power_session(session, challenger)
        defender_power = _compute_battle_power_session(session, defender)
        if stake > 0:
            if int(challenger.coin or 0) < stake:
                raise ValueError("挑战方金魂币不足")
            if int(defender.coin or 0) < stake:
                raise ValueError("被挑战方金魂币不足")
        variance = max(int((challenger_power + defender_power) * 0.08), 100)
        roll = random.randint(1, 10000)
        challenger_win = roll <= int(5000 + (challenger_power - defender_power) / (variance / 2) * 500)
        challenger_win = challenger_win or challenger_power > defender_power and roll <= 7500
        if challenger_win:
            winner, loser = challenger, defender
            winner_tg, loser_tg = challenger_tg, defender_tg
        else:
            winner, loser = defender, challenger
            winner_tg, loser_tg = defender_tg, challenger_tg
        if stake > 0:
            winner.coin = int(winner.coin or 0) + stake
            loser.coin = max(int(loser.coin or 0) - stake, 0)
        challenger.arena_wins = int(challenger.arena_wins or 0) + (1 if challenger_win else 0)
        challenger.arena_losses = int(challenger.arena_losses or 0) + (0 if challenger_win else 1)
        defender.arena_wins = int(defender.arena_wins or 0) + (1 if not challenger_win else 0)
        defender.arena_losses = int(defender.arena_losses or 0) + (0 if not challenger_win else 1)
        winner.updated_at = utcnow()
        loser.updated_at = utcnow()
        session.add(
            DouluoJournal(
                tg=challenger_tg,
                action_type="duel",
                title="斗魂结算",
                detail=f"挑战方 {_profile_display_name(challenger.display_name, challenger.username, challenger_tg)} "
                f"{'胜' if challenger_win else '负'} 于 "
                f"{_profile_display_name(defender.display_name, defender.username, defender_tg)}",
            )
        )
        session.commit()
        session.refresh(challenger)
        session.refresh(defender)
    return {
        "challenger_tg": challenger_tg,
        "defender_tg": defender_tg,
        "challenger_win": challenger_win,
        "stake": stake,
        "challenger_power": challenger_power,
        "defender_power": defender_power,
        "challenger_coin": int(challenger.coin or 0),
        "defender_coin": int(defender.coin or 0),
        "winner_tg": winner_tg,
    }


# ---------------------------------------------------------------------------
# 猎杀魂兽(委托 soulbeast_service)
# ---------------------------------------------------------------------------
def hunt_soul_beast(tg: int, region_key: str | None = None) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.soulbeast_service import hunt_soul_beast as _hunt

    return _hunt(int(tg), region_key)


def list_hunt_regions() -> list[dict[str, Any]]:
    from bot.sql_helper.sql_douluo.soulbeast_service import list_hunt_regions as _list

    return _list()


# ---------------------------------------------------------------------------
# 每日任务 / 宗门(委托 daily_service)
# ---------------------------------------------------------------------------
def list_daily_tasks(tg: int) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.daily_service import list_daily_tasks as _list

    return _list(int(tg))


def report_task_progress(tg: int, metric: str, amount: int = 1) -> None:
    from bot.sql_helper.sql_douluo.daily_service import report_task_progress as _report

    return _report(int(tg), metric, amount)


def claim_daily_task(tg: int, task_key: str) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.daily_service import claim_daily_task as _claim

    return _claim(int(tg), task_key)


def list_sect_options() -> list[dict[str, Any]]:
    from bot.plugins.douluo_game.core.sects import SECT_CATALOG

    return SECT_CATALOG


def join_sect(tg: int, sect_key: str) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.daily_service import join_sect as _join

    return _join(int(tg), sect_key)


def claim_salary(tg: int) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.daily_service import claim_salary as _claim

    return _claim(int(tg))


# ---------------------------------------------------------------------------
# 拍卖会(委托 auction_service)
# ---------------------------------------------------------------------------
def list_auction_listings(tg: int | None = None, *, status: str = "open") -> list[dict[str, Any]]:
    from bot.sql_helper.sql_douluo.auction_service import list_auction_listings as _list

    return _list(tg, status=status)


def place_auction_listing(tg: int, item_key: str, price: int, duration_hours: int | None = None) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.auction_service import place_auction_listing as _place

    return _place(int(tg), item_key, price, duration_hours)


def place_auction_bid(tg: int, listing_id: int, price: int) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.auction_service import place_auction_bid as _bid

    return _bid(int(tg), listing_id, price)


def settle_expired_auctions() -> int:
    from bot.sql_helper.sql_douluo.auction_service import settle_expired_auctions as _settle

    return _settle()


# ---------------------------------------------------------------------------
# 魂兽 Boss(service 直接实现)
# ---------------------------------------------------------------------------
def list_bosses() -> list[dict[str, Any]]:
    from bot.plugins.douluo_game.core.bosses import BOSS_CATALOG

    return BOSS_CATALOG


def challenge_boss(tg: int, boss_key: str | None = None) -> dict[str, Any]:
    from bot.sql_helper.sql_douluo.boss_service import challenge_boss as _challenge

    return _challenge(int(tg), boss_key)


# ---------------------------------------------------------------------------
# 斗罗后续作品玩法:血脉 / 魂导器 / 斗铠 / 魂核
# ---------------------------------------------------------------------------
def get_bloodline_payload(tg: int) -> dict[str, Any] | None:
    with Session() as session:
        profile = _load_profile(session, int(tg))
        return _bloodline_payload(profile)


def awaken_bloodline(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if profile.bloodline_key:
            raise ValueError("血脉已经觉醒,无法重复觉醒")
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先觉醒武魂再觉醒血脉")
        if realm_index(str(profile.realm_stage or "魂士")) < realm_index(BLOODLINE_AWAKEN_REALM):
            raise ValueError(f"至少达到 {BLOODLINE_AWAKEN_REALM} 才能觉醒血脉")
        action_counter, _, _ = _check_daily_action_points(session, tg, "bloodline", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "bloodline", settings, now)
        cost = _coerce_int(settings.get("bloodline_awaken_coin"), 2000)
        if int(profile.coin or 0) < cost:
            raise ValueError(f"觉醒血脉需要 {cost} 金魂币,当前不足")
        profile.coin = int(profile.coin or 0) - cost
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "bloodline"))
        _increment_daily_action_counter(daily_counter)
        from bot.plugins.douluo_game.core.bloodline import random_bloodline

        bloodline = random_bloodline()
        profile.bloodline_key = bloodline["key"]
        profile.bloodline_level = 1
        profile.bloodline_at = now
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "success": True,
        "awakened": True,
        "result_text": f"血脉觉醒!获得【{bloodline['name']}】({bloodline['rarity']})\n"
        f"血脉特性:{bloodline.get('skill')}",
        "bloodline": _bloodline_payload(profile),
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


def enhance_bloodline(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.bloodline_key:
            raise ValueError("尚未觉醒血脉,先觉醒血脉再淬炼")
        level = max(int(profile.bloodline_level or 0), 0)
        if level >= BLOODLINE_MAX_LEVEL:
            raise ValueError(f"血脉已淬炼至 {BLOODLINE_MAX_LEVEL} 级,已达圆满")
        action_counter, _, _ = _check_daily_action_points(session, tg, "bloodline", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "bloodline", settings, now)
        coin_cost = _coerce_int(settings.get("bloodline_enhance_coin"), 800)
        sp_cost = _coerce_int(settings.get("bloodline_enhance_soul_power"), 2000)
        if int(profile.coin or 0) < coin_cost:
            raise ValueError(f"淬炼血脉需要 {coin_cost} 金魂币,当前不足")
        if int(profile.soul_power or 0) < sp_cost:
            raise ValueError(f"淬炼血脉需要消耗 {sp_cost} 魂力,当前不足")
        profile.coin = int(profile.coin or 0) - coin_cost
        profile.soul_power = max(int(profile.soul_power or 0) - sp_cost, 0)
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "bloodline"))
        _increment_daily_action_counter(daily_counter)
        success_percent = max(100 - level, 10)
        success = random.randint(1, 100) <= success_percent
        if success:
            profile.bloodline_level = level + 1
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "success": success,
        "result_text": (
            f"血脉淬炼成功,升至 {profile.bloodline_level} 级!"
            if success
            else f"血脉淬炼失败,流失部分魂力(成功率 {success_percent}%)"
        ),
        "bloodline": _bloodline_payload(profile),
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


def _roll_materials(region: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    """按区域产出品质与材料表加权随机 material。"""
    tier_rarities = list(region.get("rarity_tiers") or ["凡品", "良品"])
    allowed_keys = set(region.get("materials") or [m["key"] for m in MATERIAL_CATALOG])
    pool: list[dict[str, Any]] = []
    for material in MATERIAL_CATALOG:
        if material["key"] not in allowed_keys:
            continue
        rarity = str(material.get("rarity") or "凡品")
        rarity_weight = MATERIAL_WEIGHT_BY_RARITY.get(rarity, 10)
        tier_weight = 4 if rarity in tier_rarities else 1
        pool.extend([material] * (rarity_weight * tier_weight))
    if not pool:
        pool = [MATERIAL_CATALOG[-1]]
    return [dict(random.choice(pool)) for _ in range(max(int(count or 3), 1))]


def prospect_materials(tg: int, region_key: str | None = None) -> dict[str, Any]:
    from bot.plugins.douluo_game.core.material import prospect_region_by_key, prospects_for_stage

    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先觉醒武魂再勘探矿脉")
        stage = str(profile.realm_stage or "魂士")
        accessible = prospects_for_stage(stage)
        region: dict[str, Any] | None = None
        if region_key:
            candidate = prospect_region_by_key(region_key)
            if candidate is None:
                raise ValueError("勘探区域不存在")
            if candidate["key"] not in [r["key"] for r in accessible]:
                raise ValueError("当前境界无法进入该勘探区域")
            region = candidate
        else:
            region = accessible[-1] if accessible else None
        if region is None:
            raise ValueError("当前境界还没有开放的勘探区域")
        entry_coin = max(_coerce_int(region.get("entry_coin"), 0), 0)
        if int(profile.coin or 0) < entry_coin:
            raise ValueError(f"进入【{region['name']}】需要 {entry_coin} 金魂币")
        action_counter, _, _ = _check_daily_action_points(session, tg, "prospect", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "prospect", settings, now)
        coin_cost = max(_coerce_int(settings.get("prospect_coin_cost"), 100), 0)
        total_cost = entry_coin + coin_cost
        if int(profile.coin or 0) < total_cost:
            raise ValueError(f"勘探需要 {total_cost} 金魂币(入场 {entry_coin} + 消耗 {coin_cost})")
        profile.coin = int(profile.coin or 0) - total_cost
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "prospect"))
        _increment_daily_action_counter(daily_counter)
        materials = _roll_materials(region, count=random.randint(2, 3))
        for material in materials:
            _grant_inventory_item_session(session, tg, material["key"], 1)
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "region": region,
        "materials": materials,
        "result_text": (
            f"在【{region['name']}】勘探,收获:\n"
            + "\n".join(f"· {m['name']}({m['rarity']})" for m in materials)
        ),
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


def get_craftsman_info(tg: int) -> dict[str, Any]:
    with Session() as session:
        profile = _load_profile(session, int(tg))
        exp = max(int(profile.craftsman_exp or 0), 0)
        from bot.plugins.douluo_game.core.soul_device import craftsman_rank_from_exp

        rank, lower, upper = craftsman_rank_from_exp(exp)
        return {
            "rank": max(int(profile.craftsman_rank or rank), rank),
            "exp": exp,
            "next_exp": upper if rank < len(CRAFTSMAN_RANK_EXP) else None,
        }


def craft_soul_device(tg: int, item_key: str) -> dict[str, Any]:
    from bot.plugins.douluo_game.core.soul_device import craftsman_rank_from_exp

    settings = get_settings()
    tg = int(tg)
    item_key = str(item_key or "").strip()
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        definition = (
            session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == item_key).first()
        )
        if definition is None or str(definition.category) != "soul_device":
            raise ValueError("魂导器不存在")
        if not definition.enabled:
            raise ValueError("该魂导器配方已停用")
        recipe = dict((definition.recipe_config or {}) if isinstance(definition.recipe_config, dict) else {})
        materials = recipe.get("materials") or {}
        craft_coin = max(_coerce_int(recipe.get("coin"), 0), 0)
        required_rank = max(_coerce_int(recipe.get("craftsman_rank"), 1), 1)
        current_rank = max(int(profile.craftsman_rank or 1), 1)
        if current_rank < required_rank:
            raise ValueError(f"锻造该魂导器需要 {required_rank} 阶魂导师,当前 {current_rank} 阶")
        if int(profile.coin or 0) < craft_coin:
            raise ValueError(f"锻造需要 {craft_coin} 金魂币")
        for material_key, quantity in materials.items():
            row = (
                session.query(DouluoInventoryItem)
                .filter(
                    DouluoInventoryItem.tg == tg,
                    DouluoInventoryItem.item_key == str(material_key),
                )
                .first()
            )
            have = int(row.quantity or 0) if row else 0
            if have < int(quantity):
                name = material_by_key(str(material_key)) or {"name": material_key}
                raise ValueError(f"锻造材料不足:缺少 {name['name']} ×{int(quantity)}(现有 {have})")
        action_counter, _, _ = _check_daily_action_points(session, tg, "craft", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "craft", settings, now)
        for material_key, quantity in materials.items():
            _consume_inventory_item_session(session, tg, str(material_key), int(quantity))
        profile.coin = int(profile.coin or 0) - craft_coin
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "craft"))
        _increment_daily_action_counter(daily_counter)
        exp_gain = 40 + (required_rank - 1) * 25
        new_exp = max(int(profile.craftsman_exp or 0), 0) + exp_gain
        new_rank, _, _ = craftsman_rank_from_exp(new_exp)
        profile.craftsman_exp = new_exp
        profile.craftsman_rank = new_rank
        _grant_inventory_item_session(session, tg, item_key, 1, allow_disabled=False)
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "item_key": item_key,
        "craftsman_exp_gained": exp_gain,
        "result_text": (
            f"锻造成功!获得【{definition.name}】\n魂导师经验 +{exp_gain},当前 {new_rank} 阶"
        ),
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


def _battle_armor_row(session, tg: int):
    return (
        session.query(DouluoInventoryItem)
        .filter(
            DouluoInventoryItem.tg == int(tg),
            DouluoInventoryItem.item_key == BATTLE_ARMOR_ITEM_KEY,
        )
        .order_by(DouluoInventoryItem.equipped_slot.desc())
        .first()
    )


def upgrade_battle_armor(tg: int) -> dict[str, Any]:
    from bot.plugins.douluo_game.core.battle_armor import battle_armor_tier_by_index

    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        row = _battle_armor_row(session, tg)
        if row is None or int(row.quantity or 0) <= 0:
            raise ValueError("背包中没有斗铠,先锻造或获得一具斗铠")
        current_tier = int((row.item_meta or {}).get("tier") or 1)
        next_tier = battle_armor_tier_by_index(current_tier + 1)
        if next_tier is None:
            raise ValueError("斗铠已达最高等阶(六字斗铠)")
        stage = str(profile.realm_stage or "魂士")
        if realm_index(stage) < realm_index(str(next_tier.get("realm_required") or "魂王")):
            raise ValueError(f"淬炼【{next_tier['name']}】需要达到 {next_tier['realm_required']}")
        materials = dict(next_tier.get("recipe") or {})
        coin_cost = max(_coerce_int(settings.get("armor_upgrade_coin"), 1500), 0) + int(next_tier.get("coin") or 0)
        if int(profile.coin or 0) < coin_cost:
            raise ValueError(f"淬炼斗铠需要 {coin_cost} 金魂币")
        for material_key, quantity in materials.items():
            have_row = (
                session.query(DouluoInventoryItem)
                .filter(
                    DouluoInventoryItem.tg == tg,
                    DouluoInventoryItem.item_key == str(material_key),
                )
                .first()
            )
            have = int(have_row.quantity or 0) if have_row else 0
            if have < int(quantity):
                name = material_by_key(str(material_key)) or {"name": material_key}
                raise ValueError(f"淬炼材料不足:缺少 {name['name']} ×{int(quantity)}(现有 {have})")
        action_counter, _, _ = _check_daily_action_points(session, tg, "armor", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "armor", settings, now)
        for material_key, quantity in materials.items():
            _consume_inventory_item_session(session, tg, str(material_key), int(quantity))
        profile.coin = int(profile.coin or 0) - coin_cost
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "armor"))
        _increment_daily_action_counter(daily_counter)
        meta = dict(row.item_meta or {})
        meta.update(
            {
                "tier": int(next_tier["tier"]),
                "attack": int(next_tier.get("attack") or 0),
                "defense": int(next_tier.get("defense") or 0),
                "speed": int(next_tier.get("speed") or 0),
                "spirit": int(next_tier.get("spirit") or 0),
                "trigger_chance": next_tier.get("trigger_chance"),
                "skill": next_tier.get("skill"),
            }
        )
        row.item_meta = meta
        row.name = str(next_tier["name"])
        row.rarity = str(next_tier.get("rarity") or row.rarity)
        row.updated_at = now
        profile.updated_at = now
        session.commit()
        session.refresh(row)
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "tier": int(next_tier["tier"]),
        "result_text": f"斗铠淬炼成功!晋升为【{next_tier['name']}】",
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


def _condense_tier_pool(stage: str) -> list[int]:
    if stage == "神王":
        return [3, 4, 5, 5]
    if stage == "神":
        return [2, 3, 4, 4]
    if stage == "封号斗罗":
        return [1, 2, 3, 3]
    return [1, 2]


def condense_soul_core(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        stage = str(profile.realm_stage or "魂士")
        if realm_index(stage) < realm_index("魂斗罗"):
            raise ValueError("至少达到魂斗罗才能凝聚魂核")
        action_counter, _, _ = _check_daily_action_points(session, tg, "condense", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "condense", settings, now)
        coin_cost = _coerce_int(settings.get("condense_coin_cost"), 2000)
        sp_cost = _coerce_int(settings.get("condense_soul_power_cost"), 3000)
        if int(profile.coin or 0) < coin_cost:
            raise ValueError(f"凝聚魂核需要 {coin_cost} 金魂币")
        if int(profile.soul_power or 0) < sp_cost:
            raise ValueError(f"凝聚魂核需要消耗 {sp_cost} 魂力")
        profile.coin = int(profile.coin or 0) - coin_cost
        profile.soul_power = max(int(profile.soul_power or 0) - sp_cost, 0)
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "condense"))
        _increment_daily_action_counter(daily_counter)
        pool = _condense_tier_pool(stage)
        tier_index = random.choice(pool)
        from bot.plugins.douluo_game.core.soul_core import soul_core_tier_by_index

        core = soul_core_tier_by_index(tier_index)
        item_key = str(core["item_key"])
        _grant_inventory_item_session(session, tg, item_key, 1)
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    result = {
        "tg": tg,
        "item_key": item_key,
        "core": core,
        "result_text": f"魂力凝聚成功!获得【{core['name']}】({core['rarity']})\n精神力 +{core.get('spirit')}",
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result


# ---------------------------------------------------------------------------
# 后续作品内容目录(listers 供 bundle / bot 展示)
# ---------------------------------------------------------------------------
def list_bloodline_catalog() -> list[dict[str, Any]]:
    from bot.plugins.douluo_game.core.bloodline import BLOODLINE_CATALOG

    return BLOODLINE_CATALOG


def list_material_catalog() -> list[dict[str, Any]]:
    return MATERIAL_CATALOG


def list_prospect_regions() -> list[dict[str, Any]]:
    return PROSPECT_REGIONS


def list_soul_device_catalog() -> list[dict[str, Any]]:
    return SOUL_DEVICE_CATALOG


def list_battle_armor_tiers() -> list[dict[str, Any]]:
    return BATTLE_ARMOR_TIERS


def list_soul_core_tiers() -> list[dict[str, Any]]:
    return SOUL_CORE_TIERS


def get_sequel_catalog() -> dict[str, Any]:
    """静态目录:供 Mini App 渲染锻造/斗铠/魂核界面。"""
    return {
        "bloodlines": list_bloodline_catalog(),
        "materials": list_material_catalog(),
        "prospect_regions": list_prospect_regions(),
        "soul_devices": list_soul_device_catalog(),
        "battle_armor_tiers": list_battle_armor_tiers(),
        "soul_core_tiers": list_soul_core_tiers(),
        "craftsman_rank_exp": CRAFTSMAN_RANK_EXP,
    }
