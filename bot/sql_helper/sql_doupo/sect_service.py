"""P3 宗门社交领域服务：转宗、离开、成员榜、每日委托。

对齐 expedition_service.py 的领域拆分模式，将宗门社交逻辑从 service.py
单体中抽出；join_sect 仍留在 service.py（P4 迁移）。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from bot.plugins.doupo_game.core import SECT_RANKS, realm_rank
from bot.sql_helper import Session
from bot.sql_helper.sql_doupo.models import DoupoInventoryItem, DoupoJournal, DoupoProfile, utcnow
from bot.sql_helper.sql_doupo.service import (
    _SECT_LOOKUP,
    _SECT_NAME_LOOKUP,
    _apply_douqi_delta_with_balance,
    _apply_gold_delta_with_economy,
    _coerce_int,
    _economy_day_key,
    _equipment_summary_from_rows,
    _get_or_create_economy_ledger_session,
    _grant_inventory_item_session,
    _rank_by_threshold,
    build_feature_overview,
    build_growth_snapshot,
    get_daily_action_usage,
    get_economy_snapshot,
    get_settings,
    list_player_inventory_grouped,
    list_recent_journals,
    serialize_profile,
)


def _sect_option(value: str | None) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return _SECT_LOOKUP.get(raw) or _SECT_NAME_LOOKUP.get(raw)


def _sect_position_multiplier(contribution: int) -> float:
    rank = _rank_by_threshold(max(int(contribution or 0), 0), SECT_RANKS, "contribution")
    return max(float(rank.get("multiplier") or 1.0), 1.0)


def _today_key(now) -> str:
    # 项目统一使用 Asia/Shanghai 日界，与 _economy_day_key 对齐。
    return (now + timedelta(hours=8)).date().isoformat()


def _transfer_remaining_days(changed_at, now, cooldown_days: int) -> int:
    if not changed_at or cooldown_days <= 0:
        return 0
    elapsed_days = (now - changed_at).total_seconds() / 86400
    return max(int(cooldown_days - elapsed_days + 0.999), 0)


def transfer_sect(tg: int, sect_key: str) -> dict[str, Any]:
    """转宗：扣除转宗费，贡献按比例保留，并进入转宗冷却。

    需要已入宗门、目标宗门不同、境界达标、金币充足，且不在冷却期。
    """
    settings = get_settings()
    target = _sect_option(sect_key)
    if target is None:
        raise ValueError("宗门不存在")
    cost = max(_coerce_int(settings.get("sect_transfer_cost"), 1500), 0)
    cooldown_days = max(_coerce_int(settings.get("sect_transfer_cooldown_days"), 7), 0)
    retain_pct = min(max(_coerce_int(settings.get("sect_transfer_contribution_retain"), 50), 0), 100)
    thresholds = settings.get("realm_thresholds") or []
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.sect_name:
            raise ValueError("请先加入宗门")
        if str(profile.sect_name) == str(target["name"]):
            raise ValueError("你已在该宗门")
        now = utcnow()
        remaining = _transfer_remaining_days(profile.sect_changed_at, now, cooldown_days)
        if remaining > 0:
            raise ValueError(f"转宗冷却中，还需 {remaining} 天才能转宗")
        stage_min = str(target.get("realm_stage_min") or "").strip()
        if stage_min and realm_rank(profile.realm_stage, thresholds) < realm_rank(stage_min, thresholds):
            raise ValueError(f"转入 {target['name']} 至少需要达到 {stage_min}")
        if cost > 0 and int(profile.gold or 0) < cost:
            raise ValueError(f"转宗需要 {cost} 金币")
        result: dict[str, Any] = {"gold_delta": 0}
        if cost > 0:
            ledger = _get_or_create_economy_ledger_session(session, int(tg), _economy_day_key())
            result["gold_delta"] = _apply_gold_delta_with_economy(profile, -cost, ledger, settings, result)
        old_name = str(profile.sect_name)
        kept = max(int(profile.sect_contribution or 0) * retain_pct // 100, 0)
        profile.sect_name = str(target["name"])
        profile.sect_contribution = kept
        profile.sect_changed_at = now
        profile.updated_at = now
        session.add(
            DoupoJournal(
                tg=int(tg),
                action_type="sect",
                title="转宗",
                detail=f"🌀 从 {old_name} 转投 {target['name']}，宗门贡献保留 {kept}",
            )
        )
        session.commit()
        session.refresh(profile)
        profile_payload = serialize_profile(profile, settings)
    return _sect_bundle(
        int(tg),
        profile_payload,
        settings,
        dict(target),
        f"已转投 {target['name']}，宗门贡献保留 {kept}",
    )


def leave_sect(tg: int) -> dict[str, Any]:
    """离开宗门：清零贡献并进入转宗冷却，可按配置收取费用。"""
    settings = get_settings()
    cost = max(_coerce_int(settings.get("sect_leave_gold_cost"), 0), 0)
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.sect_name:
            raise ValueError("你未加入任何宗门")
        if cost > 0 and int(profile.gold or 0) < cost:
            raise ValueError(f"离开宗门需要 {cost} 金币")
        result: dict[str, Any] = {"gold_delta": 0}
        if cost > 0:
            ledger = _get_or_create_economy_ledger_session(session, int(tg), _economy_day_key())
            result["gold_delta"] = _apply_gold_delta_with_economy(profile, -cost, ledger, settings, result)
        old_name = str(profile.sect_name)
        now = utcnow()
        profile.sect_name = None
        profile.sect_contribution = 0
        profile.sect_changed_at = now
        profile.updated_at = now
        session.add(
            DoupoJournal(
                tg=int(tg),
                action_type="sect",
                title="离开宗门",
                detail=f"🚪 离开 {old_name}，宗门贡献已清零",
            )
        )
        session.commit()
        session.refresh(profile)
        profile_payload = serialize_profile(profile, settings)
    return _sect_bundle(int(tg), profile_payload, settings, None, f"已离开 {old_name}")


def list_sect_members(sect_name: str, limit: int = 50) -> dict[str, Any]:
    """宗门成员榜：按宗门贡献排序，附战力与境界（批量取装备，避免 N+1）。"""
    settings = get_settings()
    name = str(sect_name or "").strip()
    with Session() as session:
        query = session.query(DoupoProfile).filter(DoupoProfile.sect_name == name)
        rows = (
            query.order_by(DoupoProfile.sect_contribution.desc(), DoupoProfile.battle_power.desc())
            .limit(max(min(int(limit or 50), 100), 1))
            .all()
        )
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
        members: list[dict[str, Any]] = []
        for row in rows:
            payload = serialize_profile(row, settings, equipment_map.get(int(row.tg)))
            members.append({
                "tg": int(payload["tg"]),
                "display_name": str(payload.get("display_name") or f"玩家{row.tg}"),
                "username": payload.get("username"),
                "realm_stage": str(payload.get("realm_stage") or "斗之气"),
                "realm_stars": int(payload.get("realm_stars") or 1),
                "sect_rank": str(payload.get("sect_rank") or "外门弟子"),
                "sect_contribution": int(payload.get("sect_contribution") or 0),
                "battle_power": int(payload.get("battle_power") or 0),
            })
    return {"sect_name": name, "members": members, "total": len(members)}


def get_sect_panel(
    tg: int,
    settings: dict[str, Any] | None = None,
    profile_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """前端宗门面板聚合：入宗状态 + 每日委托 + 成员榜 + 转宗/离宗成本与冷却。

    单次会话读取角色行；profile_payload 仅作冗余优化，不承担数据来源。
    """
    settings = settings or get_settings()
    cooldown_days = max(_coerce_int(settings.get("sect_transfer_cooldown_days"), 7), 0)
    transfer_cost = max(_coerce_int(settings.get("sect_transfer_cost"), 1500), 0)
    leave_cost = max(_coerce_int(settings.get("sect_leave_gold_cost"), 0), 0)
    with Session() as session:
        row = session.query(DoupoProfile).filter(DoupoProfile.tg == int(tg)).first()
    if row is None or not row.sect_name:
        return {
            "joined": False,
            "sect_name": None,
            "sect_option": None,
            "quest": None,
            "members": [],
            "transfer": {"cost": transfer_cost, "cooldown_days": cooldown_days, "remaining_days": 0},
            "leave_cost": leave_cost,
        }
    option = _sect_option(str(row.sect_name))
    now = utcnow()
    remaining = _transfer_remaining_days(row.sect_changed_at, now, cooldown_days)
    contribution = int(row.sect_contribution or 0)
    rank = _rank_by_threshold(contribution, SECT_RANKS, "contribution")
    rewards = dict((option or {}).get("quest_rewards") or {})
    claimed = bool(row.last_sect_quest_at and _today_key(row.last_sect_quest_at) == _today_key(now))
    quest = {
        "rewards": rewards,
        "multiplier": _sect_position_multiplier(contribution),
        "claimed": claimed,
        "rank": str(rank.get("name") or "外门弟子"),
    }
    members = list_sect_members(str(row.sect_name)).get("members", [])
    return {
        "joined": True,
        "sect_name": str(row.sect_name),
        "sect_option": dict(option) if option else None,
        "quest": quest,
        "members": members,
        "transfer": {"cost": transfer_cost, "cooldown_days": cooldown_days, "remaining_days": remaining},
        "leave_cost": leave_cost,
    }


def claim_sect_quest(tg: int) -> dict[str, Any]:
    """每日宗门委托：按宗门位阶倍率发放贡献、金币、斗气与宗门信物。"""
    settings = get_settings()
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.sect_name:
            raise ValueError("请先加入宗门")
        option = _sect_option(str(profile.sect_name))
        if option is None:
            raise ValueError("当前宗门配置已失效")
        now = utcnow()
        if profile.last_sect_quest_at and _today_key(profile.last_sect_quest_at) == _today_key(now):
            raise ValueError("今日宗门委托已领取，明日再来")
        base = dict(option.get("quest_rewards") or {})
        multiplier = _sect_position_multiplier(int(profile.sect_contribution or 0))
        contribution = round(max(_coerce_int(base.get("contribution"), 40), 0) * multiplier)
        gold = round(max(_coerce_int(base.get("gold"), 240), 0) * multiplier)
        douqi = round(max(_coerce_int(base.get("douqi"), 320), 0) * multiplier)
        profile.sect_contribution = int(profile.sect_contribution or 0) + contribution
        profile.last_sect_quest_at = now
        profile.updated_at = now
        result: dict[str, Any] = {"gold_delta": 0}
        ledger = _get_or_create_economy_ledger_session(session, int(tg), _economy_day_key())
        gold_actual = _apply_gold_delta_with_economy(profile, gold, ledger, settings, result)
        _apply_douqi_delta_with_balance(session, profile, douqi, settings, result)
        granted_items: list[dict[str, Any]] = []
        for item_key, quantity in dict(base.get("items") or {}).items():
            granted = _grant_inventory_item_session(session, int(tg), str(item_key), max(int(quantity or 0), 1))
            if granted:
                granted_items.append(granted)
        session.add(
            DoupoJournal(
                tg=int(tg),
                action_type="sect",
                title="宗门委托",
                detail=(
                    f"📋 {profile.sect_name} 每日委托完成：🏅 贡献 +{contribution}、🪙 金币 +{gold_actual}、🌀 斗气 +{douqi}"
                    + ("、" + "、".join(g["name"] for g in granted_items) if granted_items else "")
                ),
            )
        )
        session.commit()
        session.refresh(profile)
        profile_payload = serialize_profile(profile, settings)
    return _sect_bundle(
        int(tg),
        profile_payload,
        settings,
        dict(option),
        f"📋 宗门委托完成：🏅 贡献 +{contribution}、🪙 金币 +{gold_actual}、🌀 斗气 +{douqi}",
    )


def _sect_bundle(
    tg: int,
    profile_payload: dict[str, Any],
    settings: dict[str, Any],
    sect_detail: dict[str, Any] | None,
    detail: str,
) -> dict[str, Any]:
    return {
        "profile": profile_payload,
        "sect": sect_detail,
        "sect_panel": get_sect_panel(tg, settings, profile_payload),
        "growth": build_growth_snapshot(profile_payload, settings),
        "features": build_feature_overview(profile_payload),
        "inventory": list_player_inventory_grouped(int(tg)),
        "economy": get_economy_snapshot(int(tg), settings),
        "daily_usage": get_daily_action_usage(int(tg), settings),
        "journals": list_recent_journals(int(tg), limit=20),
        "detail": detail,
    }
