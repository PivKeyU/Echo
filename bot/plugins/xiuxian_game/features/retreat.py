from __future__ import annotations

from datetime import timedelta
from math import ceil
from typing import Any

from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    XiuxianProfile,
    apply_spiritual_stone_delta,
    assert_currency_operation_allowed,
    get_current_title,
    get_profile,
    get_shared_spiritual_stone_total,
    serialize_profile,
    upsert_profile,
    utcnow,
    _queue_profile_cache_invalidation,
    _queue_user_view_cache_invalidation,
)


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def is_retreating(profile) -> bool:
    if isinstance(profile, dict):
        return bool(
            profile
            and profile.get("retreat_started_at")
            and profile.get("retreat_end_at")
            and int(profile.get("retreat_minutes_total") or 0) > int(profile.get("retreat_minutes_resolved") or 0)
        )
    return bool(
        profile
        and profile.retreat_started_at
        and profile.retreat_end_at
        and int(profile.retreat_minutes_total or 0) > int(profile.retreat_minutes_resolved or 0)
    )


def _compute_retreat_plan(profile) -> dict[str, int]:
    from bot.plugins.xiuxian_game.world_service import get_sect_effects

    legacy_service = _legacy_service()
    profile_data = serialize_profile(profile)
    artifact_effects = legacy_service.merge_artifact_effects(
        profile_data,
        legacy_service.collect_equipped_artifacts(profile.tg),
    )
    sect_effects = get_sect_effects(profile_data)
    technique_effects = legacy_service.resolve_technique_effects(
        profile_data,
        legacy_service._current_technique_payload(profile_data),
    )
    active_talisman = legacy_service.serialize_talisman(legacy_service.get_talisman(int(profile_data.get("active_talisman_id") or 0))) if profile_data.get("active_talisman_id") else None
    talisman_active_effects = legacy_service.resolve_talisman_active_effects(profile_data, active_talisman) if active_talisman else {}
    title_effects = legacy_service.resolve_title_effects(
        profile_data,
        get_current_title(profile.tg),
    )
    artifact_bonus = (
        int(artifact_effects.get("cultivation_bonus", 0))
        + int(sect_effects.get("cultivation_bonus", 0))
        + int(technique_effects.get("cultivation_bonus", 0))
        + int(title_effects.get("cultivation_bonus", 0))
        + int(round(float(talisman_active_effects.get("cultivation_bonus") or 0)))
        + int(profile_data.get("insight_bonus", 0) or 0)
    )
    stage = legacy_service.normalize_realm_stage(profile.realm_stage or legacy_service.FIRST_REALM_STAGE)
    stage_rule = legacy_service._realm_stage_rule(stage)
    poison_penalty = min(int(profile.dan_poison or 0) // 4, 25)
    gain_per_hour = max(
        int(stage_rule["retreat_hourly_base"])
        + int(profile.realm_layer or 1) * 18
        + legacy_service.realm_index(stage) * 48
        + artifact_bonus * 3
        - poison_penalty * 4,
        60,
    )
    cost_per_hour = max(ceil(gain_per_hour / 10), 12)
    return {
        "gain_per_minute": max(gain_per_hour // 60, 1),
        "cost_per_hour": cost_per_hour,
        # The DB column is legacy-named as per-minute, but new retreats store an hourly rate here.
        "cost_per_minute": cost_per_hour,
    }


def _retreat_cost_for_minutes(cost_per_hour: int, minutes: int) -> int:
    settled_minutes = max(int(minutes or 0), 0)
    hourly_cost = max(int(cost_per_hour or 0), 0)
    if settled_minutes <= 0 or hourly_cost <= 0:
        return 0
    return max(int(ceil(hourly_cost * settled_minutes / 60.0)), 1)


def _stored_retreat_rate_is_legacy_per_minute(stored_rate: int, gain_per_minute: int) -> bool:
    rate = max(int(stored_rate or 0), 0)
    gain_rate = max(int(gain_per_minute or 0), 1)
    if rate <= 0:
        return False
    return rate <= max(int(ceil(gain_rate / 2.0)), 3)


def _retreat_cost_from_stored_rate(stored_rate: int, minutes: int, *, gain_per_minute: int = 0) -> int:
    rate = max(int(stored_rate or 0), 0)
    settled_minutes = max(int(minutes or 0), 0)
    if settled_minutes <= 0 or rate <= 0:
        return 0
    if _stored_retreat_rate_is_legacy_per_minute(rate, gain_per_minute):
        return rate * settled_minutes
    return _retreat_cost_for_minutes(rate, settled_minutes)


def _retreat_affordable_minutes(available_stone: int, target_minutes: int, stored_rate: int, *, gain_per_minute: int = 0) -> int:
    available = max(int(available_stone or 0), 0)
    target = max(int(target_minutes or 0), 0)
    rate = max(int(stored_rate or 0), 0)
    if target <= 0:
        return 0
    if rate <= 0:
        return target
    if available <= 0:
        return 0
    if _retreat_cost_from_stored_rate(rate, target, gain_per_minute=gain_per_minute) <= available:
        return target
    low = 0
    high = target
    while low < high:
        mid = (low + high + 1) // 2
        if _retreat_cost_from_stored_rate(rate, mid, gain_per_minute=gain_per_minute) <= available:
            low = mid
        else:
            high = mid - 1
    return low


def settle_retreat_progress(tg: int) -> dict[str, Any] | None:
    legacy_service = _legacy_service()
    profile = legacy_service._repair_profile_realm_state(tg) or get_profile(tg, create=False)
    if profile is None or not is_retreating(profile):
        return None

    now = utcnow()
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if updated is None or not is_retreating(updated):
            return None

        end_at = updated.retreat_end_at or now
        started_at = updated.retreat_started_at or now
        total_minutes = max(int(updated.retreat_minutes_total or 0), 0)
        resolved_minutes = max(int(updated.retreat_minutes_resolved or 0), 0)
        elapsed_minutes = int(max(min(now, end_at) - started_at, timedelta()).total_seconds() // 60)
        target_minutes = min(max(elapsed_minutes, 0), total_minutes)
        delta_minutes = max(target_minutes - resolved_minutes, 0)

        if delta_minutes <= 0:
            if now >= end_at and resolved_minutes >= total_minutes:
                updated.active_talisman_id = None
                updated.retreat_started_at = None
                updated.retreat_end_at = None
                updated.retreat_gain_per_minute = 0
                updated.retreat_cost_per_minute = 0
                updated.retreat_minutes_total = 0
                updated.retreat_minutes_resolved = 0
                updated.updated_at = now
                _queue_profile_cache_invalidation(session, tg)
                _queue_user_view_cache_invalidation(session, tg)
                session.commit()
            return None

        gain_per_minute = max(int(updated.retreat_gain_per_minute or 0), 0)
        stored_cost_rate = max(int(updated.retreat_cost_per_minute or 0), 0)
        affordable_minutes = delta_minutes
        insufficient_stone = False
        if stored_cost_rate > 0:
            available_stone = max(int(get_shared_spiritual_stone_total(tg, session=session, for_update=True) or 0), 0)
            affordable_minutes = _retreat_affordable_minutes(
                available_stone,
                delta_minutes,
                stored_cost_rate,
                gain_per_minute=gain_per_minute,
            )
            insufficient_stone = affordable_minutes < delta_minutes

        if affordable_minutes <= 0:
            if insufficient_stone or now >= end_at:
                updated.active_talisman_id = None
                updated.retreat_started_at = None
                updated.retreat_end_at = None
                updated.retreat_gain_per_minute = 0
                updated.retreat_cost_per_minute = 0
                updated.retreat_minutes_total = 0
                updated.retreat_minutes_resolved = 0
                updated.updated_at = now
                _queue_profile_cache_invalidation(session, tg)
                _queue_user_view_cache_invalidation(session, tg)
                session.commit()
                profile_payload = serialize_profile(updated)
                return {
                    "gain": 0,
                    "gain_raw": 0,
                    "cultivation_efficiency_percent": 100,
                    "cost": 0,
                    "upgraded_layers": [],
                    "remaining": 0,
                    "finished": True,
                    "insufficient_stone": True,
                    "profile": profile_payload,
                }
            return None

        raw_gain = affordable_minutes * gain_per_minute
        gain, gain_meta = legacy_service.adjust_cultivation_gain_for_social_mode(updated, raw_gain)
        cost = _retreat_cost_from_stored_rate(stored_cost_rate, affordable_minutes, gain_per_minute=gain_per_minute)
        layer, cultivation, upgraded_layers, remaining = legacy_service.apply_cultivation_gain(
            legacy_service.normalize_realm_stage(updated.realm_stage or legacy_service.FIRST_REALM_STAGE),
            int(updated.realm_layer or 1),
            int(updated.cultivation or 0),
            gain,
        )

        settled_minutes = min(resolved_minutes + affordable_minutes, total_minutes)
        finished = insufficient_stone or settled_minutes >= total_minutes or now >= end_at
        if cost > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -cost,
                action_text="闭关消耗灵石",
                enforce_currency_lock=True,
                allow_dead=False,
                apply_tribute=False,
            )
        updated.cultivation = cultivation
        updated.realm_layer = layer
        # Passive dan_poison decay during retreat: ~5 + bone//50 per in-game day (480 min)
        in_game_days = max(affordable_minutes, 0) / 480.0
        daily_decay = 5 + max(int(updated.bone or 0), 0) // 50
        poison_decay = max(int(round(in_game_days * daily_decay)), 0)
        if poison_decay > 0:
            updated.dan_poison = max(int(updated.dan_poison or 0) - poison_decay, 0)
        updated.active_talisman_id = None if finished else updated.active_talisman_id
        updated.retreat_minutes_resolved = 0 if finished else settled_minutes
        updated.retreat_started_at = None if finished else updated.retreat_started_at
        updated.retreat_end_at = None if finished else updated.retreat_end_at
        updated.retreat_gain_per_minute = 0 if finished else int(updated.retreat_gain_per_minute or 0)
        updated.retreat_cost_per_minute = 0 if finished else int(updated.retreat_cost_per_minute or 0)
        updated.retreat_minutes_total = 0 if finished else total_minutes
        updated.updated_at = now
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        profile_payload = serialize_profile(updated)

    return {
        "gain": gain,
        "gain_raw": raw_gain,
        "cultivation_efficiency_percent": int(gain_meta.get("efficiency_percent") or 100),
        "cost": cost,
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "finished": finished,
        "insufficient_stone": insufficient_stone,
        "profile": profile_payload,
    }


def ensure_not_in_retreat(tg: int) -> None:
    legacy_service = _legacy_service()
    settle_retreat_progress(tg)
    profile = get_profile(tg, create=False)
    if profile is not None:
        legacy_service._assert_gender_ready(profile, "执行当前操作")
    if profile is not None and is_retreating(profile):
        raise ValueError("你正在闭关中，当前不能执行这个操作。")


def start_retreat_for_user(tg: int, hours: int) -> dict[str, Any]:
    legacy_service = _legacy_service()
    settle_retreat_progress(tg)
    profile = legacy_service._require_alive_profile_obj(tg, "开始闭关")
    assert_currency_operation_allowed(tg, "开始闭关", profile=profile)
    if is_retreating(profile):
        raise ValueError("你已入定闭关，心神内守，莫再扰动。")

    retreat_hours = max(min(int(hours or 0), 4), 1)
    plan = _compute_retreat_plan(profile)
    total_minutes = retreat_hours * 60
    estimated_gain_raw = plan["gain_per_minute"] * total_minutes
    estimated_gain, gain_meta = legacy_service.adjust_cultivation_gain_for_social_mode(profile, estimated_gain_raw)
    total_cost = _retreat_cost_for_minutes(plan["cost_per_hour"], total_minutes)
    if max(int(get_shared_spiritual_stone_total(tg) or 0), 0) < total_cost:
        raise ValueError(f"灵石不足，闭关 {retreat_hours} 小时预计需要 {total_cost} 灵石。")

    now = utcnow()
    upsert_profile(
        tg,
        retreat_started_at=now,
        retreat_end_at=now + timedelta(hours=retreat_hours),
        retreat_gain_per_minute=plan["gain_per_minute"],
        retreat_cost_per_minute=plan["cost_per_minute"],
        retreat_minutes_total=total_minutes,
        retreat_minutes_resolved=0,
    )
    return {
        "hours": retreat_hours,
        "estimated_gain": estimated_gain,
        "estimated_gain_raw": estimated_gain_raw,
        "cultivation_efficiency_percent": int(gain_meta.get("efficiency_percent") or 100),
        "estimated_cost": total_cost,
        "profile": legacy_service.serialize_full_profile(tg),
    }


def finish_retreat_for_user(tg: int) -> dict[str, Any]:
    legacy_service = _legacy_service()
    profile = legacy_service._require_alive_profile_obj(tg, "结束闭关")
    assert_currency_operation_allowed(tg, "结束闭关", profile=profile)
    result = settle_retreat_progress(tg)
    if result is None and not is_retreating(profile):
        raise ValueError("你此刻并未处于闭关之中，何来出关之说？")

    upsert_profile(
        tg,
        active_talisman_id=None,
        retreat_started_at=None,
        retreat_end_at=None,
        retreat_gain_per_minute=0,
        retreat_cost_per_minute=0,
        retreat_minutes_total=0,
        retreat_minutes_resolved=0,
    )
    return {
        "settled": result
        or {
            "gain": 0,
            "gain_raw": 0,
            "cultivation_efficiency_percent": 100,
            "cost": 0,
            "upgraded_layers": [],
            "finished": True,
        },
        "profile": legacy_service.serialize_full_profile(tg),
    }
