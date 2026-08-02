"""猎杀魂兽、魂环吸收与替换(领域玩法)。"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from bot.plugins.douluo_game.core import (
    ACTION_TYPE_LABELS,
    RING_SLOT_CAP,
    HUNT_REGIONS,
    REALM_MAX_RING_TIER,
    max_allowed_ring_tier,
    region_by_key,
    regions_for_stage,
    ring_stats_for_year,
    ring_tier_of_year,
    tier_by_name,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_douluo.models import DouluoJournal, DouluoProfile, DouluoSoulRing, utcnow
from bot.sql_helper.sql_douluo.service import (
    _apply_daily_income_caps,
    _build_action_usage_session,
    _build_douluo_broadcast_event,
    _check_daily_action_limit,
    _check_daily_action_points,
    _compute_battle_power_session,
    _consume_daily_action_points,
    _economy_day_key,
    _increment_daily_action_counter,
    _load_profile,
    _maybe_trigger_event,
    _serialize_profile_row,
    _action_point_cost,
    create_journal,
    get_settings,
)


def _year_cap_for_realm(stage: str, region: dict[str, Any]) -> int:
    realm_tier = max_allowed_ring_tier(stage)
    region_tier = tier_by_name(str(region.get("max_year_tier") or ""))
    caps: list[int] = []
    if realm_tier is not None:
        caps.append(int(realm_tier["year_max"]))
    if region_tier is not None:
        caps.append(int(region_tier["year_max"]))
    return max(caps, default=10_000_000)


def list_hunt_regions() -> list[dict[str, Any]]:
    return HUNT_REGIONS


def list_soul_rings(tg: int) -> list[dict[str, Any]]:
    from bot.sql_helper.sql_douluo.service import _rings_payload_session

    with Session() as session:
        return _rings_payload_session(session, int(tg))


def _roll_beast(region: dict[str, Any]) -> dict[str, Any]:
    beasts = region.get("beasts", [])
    if not beasts:
        raise ValueError("该区域暂无魂兽")
    total = sum(max(int(b.get("weight") or 1), 1) for b in beasts)
    roll = random.randint(1, total)
    acc = 0
    for beast in beasts:
        acc += max(int(beast.get("weight") or 1), 1)
        if roll <= acc:
            return beast
    return beasts[-1]


def hunt_soul_beast(tg: int, region_key: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先使用 /dl_wuhun 觉醒武魂再猎杀魂兽")
        stage = str(profile.realm_stage or "魂士")

        region: dict[str, Any] | None = None
        if region_key:
            region = region_by_key(region_key)
            if region is None:
                raise ValueError("猎杀区域不存在")
            accessible = [r for r in regions_for_stage(stage) if r["key"] == region["key"]]
            if not accessible:
                raise ValueError(f"当前境界无法进入该猎杀区域")
        else:
            region = regions_for_stage(stage)
            if not region:
                raise ValueError("当前境界还没有开放的猎杀区域")
            region = region[0]

        action_counter, _, _ = _check_daily_action_points(session, tg, "hunt", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "hunt", settings, now)
        entry_coin = max(int(region.get("entry_coin") or 0), 0)
        if int(profile.coin or 0) < entry_coin:
            raise ValueError(f"进入该区域需要 {entry_coin} 金魂币,当前不足")
        if entry_coin > 0:
            profile.coin = int(profile.coin or 0) - entry_coin
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "hunt"))
        _increment_daily_action_counter(daily_counter)

        beast = _roll_beast(region)
        cap = _year_cap_for_realm(stage, region)
        low = max(int(beast.get("year_min") or 10), 10)
        high = max(low, int(beast.get("year_max") or low))
        high = min(high, cap)
        if high < low:
            high = low
        years = random.randint(low, high)
        stats = ring_stats_for_year(years)
        tier_info = ring_tier_of_year(years) or {"tier": "十年", "color": "白"}

        # 奖励
        coin_raw = random.randint(int(beast.get("coin_min") or 0), int(beast.get("coin_max") or 0))
        sp_raw = random.randint(int(beast.get("soul_power_min") or 0), int(beast.get("soul_power_max") or 0))
        gained = _apply_daily_income_caps(
            session, tg, _economy_day_key(now), settings, coin=coin_raw, soul_power=sp_raw
        )
        profile.coin = int(profile.coin or 0) + gained["coin"]
        profile.soul_power = int(profile.soul_power or 0) + gained["soul_power"]

        # 魂环吸收
        existing = (
            session.query(DouluoSoulRing).filter(DouluoSoulRing.tg == tg).order_by(DouluoSoulRing.slot.asc()).all()
        )
        from bot.plugins.douluo_game.core.wuhun import wuhun_by_key

        wuhun_def = wuhun_by_key(profile.wuhun_key) or {}
        skills = wuhun_def.get("skills", [])
        absorb_fee = max(int(settings.get("hunt_absorb_fee") or 0), 0)
        ring_result: dict[str, Any] | None = None
        if len(existing) < RING_SLOT_CAP:
            slot = len(existing) + 1
            skill_name = skills[slot - 1] if slot - 1 < len(skills) else f"第{slot}魂技"
            ring = DouluoSoulRing(
                tg=tg,
                slot=slot,
                years=years,
                tier=str(tier_info["tier"]),
                color=str(tier_info["color"]),
                source_name=beast["name"],
                skill_name=skill_name,
                attack=stats["attack"],
                defense=stats["defense"],
                speed=stats["speed"],
                spirit=stats["spirit"],
            )
            session.add(ring)
            profile.total_hunts = int(profile.total_hunts or 0) + 1
            ring_result = {
                "action": "absorb",
                "slot": slot,
                "years": years,
                "tier": str(tier_info["tier"]),
                "color": str(tier_info["color"]),
                "source_name": beast["name"],
                "skill_name": skill_name,
                "absorb_fee": 0,
                "replaced": False,
            }
        else:
            # 9 环已满:仅当新环年限更高才替换最弱环
            weakest = min(existing, key=lambda r: int(r.years or 0))
            profile.total_hunts = int(profile.total_hunts or 0) + 1
            if int(years) > int(weakest.years or 0):
                if int(profile.coin or 0) < absorb_fee:
                    raise ValueError(f"替换魂环需要 {absorb_fee} 金魂币,当前不足")
                profile.coin = int(profile.coin or 0) - absorb_fee
                old_skill = weakest.skill_name
                weakest.years = years
                weakest.tier = str(tier_info["tier"])
                weakest.color = str(tier_info["color"])
                weakest.source_name = beast["name"]
                weakest.attack = stats["attack"]
                weakest.defense = stats["defense"]
                weakest.speed = stats["speed"]
                weakest.spirit = stats["spirit"]
                weakest.updated_at = utcnow()
                ring_result = {
                    "action": "replace",
                    "slot": int(weakest.slot),
                    "years": years,
                    "tier": str(tier_info["tier"]),
                    "color": str(tier_info["color"]),
                    "source_name": beast["name"],
                    "skill_name": weakest.skill_name,
                    "replaced_skill": old_skill,
                    "absorb_fee": absorb_fee,
                    "replaced": True,
                }
            else:
                ring_result = {
                    "action": "give_up",
                    "slot": None,
                    "years": years,
                    "tier": str(tier_info["tier"]),
                    "color": str(tier_info["color"]),
                    "source_name": beast["name"],
                    "absorb_fee": 0,
                    "replaced": False,
                    "reason": f"新魂环年限低于你已吸收的最弱魂环({weakest.years}年),放弃吸收",
                }

        event = _maybe_trigger_event(session, profile, "hunt", settings)
        profile.updated_at = utcnow()
        usage = _build_action_usage_session(session, tg)
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
        rings = _rings_payload_session(session, tg)

    # 记录日志
    try:
        create_journal(
            tg,
            "hunt",
            "猎杀魂兽",
            f"在【{region.get('name')}】猎杀 {beast.get('name')},年限 {years} 年,"
            f"获得魂力 {gained['soul_power']}、金魂币 {gained['coin']}。",
        )
    except Exception:
        pass
    try:
        from bot.sql_helper.sql_douluo.daily_service import report_task_progress

        report_task_progress(tg, "hunt", 1)
    except Exception:
        pass
    result = {
        "tg": tg,
        "region": {"key": region["key"], "name": region["name"]},
        "beast": {"key": beast["key"], "name": beast["name"]},
        "years": years,
        "tier": str(tier_info["tier"]),
        "color": str(tier_info["color"]),
        "ring": ring_result,
        "soul_power_gained": gained["soul_power"],
        "coin_gained": gained["coin"],
        "entry_coin": entry_coin,
        "event": event,
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
        "rings": rings,
        "usage": usage,
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result
