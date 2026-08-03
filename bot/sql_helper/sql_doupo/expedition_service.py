from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from bot.plugins.doupo_game.core import (
    EXPEDITION_BOSSES,
    EXPEDITION_EVENTS,
    EXPEDITION_HIDDEN_EVENTS,
    EXPEDITION_REGIONS,
    expedition_boss_for_region,
    expedition_event_for_key,
    expedition_region,
    realm_rank,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_doupo.models import DoupoEconomyLedger, DoupoExpedition, DoupoJournal, DoupoProfile, utcnow
from bot.sql_helper.sql_doupo.service import (
    _apply_gold_delta_with_economy,
    _apply_douqi_delta_with_balance,
    _apply_realm_progress,
    _battle_power,
    _catalog_item,
    _check_daily_action_limit,
    _check_daily_action_points,
    _economy_day_key,
    _get_or_create_economy_ledger_session,
    _grant_inventory_item_session,
    _increment_daily_action_counter,
    _consume_daily_action_points,
    get_daily_action_usage,
    get_or_create_profile,
    get_settings,
    serialize_profile,
)


def _active_expedition(session, tg: int, *, lock: bool = False) -> DoupoExpedition | None:
    query = session.query(DoupoExpedition).filter(
        DoupoExpedition.tg == int(tg),
        DoupoExpedition.status == "active",
    )
    if lock:
        query = query.with_for_update()
    return query.order_by(DoupoExpedition.id.desc()).first()


_STALE_EXPEDITION_HOURS = 24


def _expedition_is_stale(row: DoupoExpedition, hours: int = _STALE_EXPEDITION_HOURS) -> bool:
    """超过 24 小时未推进的游历视为超时，避免 0 步游历软锁永久占位。"""
    if row is None or not row.updated_at:
        return False
    return utcnow() - row.updated_at > timedelta(hours=max(int(hours or 0), 1))


def _roll_pair(value: Any, default: tuple[int, int] = (0, 0)) -> int:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        low, high = default
    else:
        low, high = int(value[0] or 0), int(value[1] or 0)
    return random.randint(min(low, high), max(low, high))


def _focus_profile(score: int) -> tuple[int, int, str]:
    """Return bounded chance/damage modifiers and a player-facing focus grade."""
    value = min(max(int(score or 0), 0), 100)
    if value >= 90:
        return 7, -2, "完美"
    if value >= 75:
        return 4, -1, "稳定"
    if value >= 55:
        return 1, 0, "聚气"
    if value >= 35:
        return -1, 1, "分神"
    return -4, 2, "失衡"


def _region_available(profile: DoupoProfile, region: dict[str, Any], settings: dict[str, Any]) -> tuple[bool, str]:
    thresholds = settings.get("realm_thresholds") or []
    required = str(region.get("realm_stage_min") or "斗之气")
    if realm_rank(str(profile.realm_stage or "斗之气"), thresholds) < realm_rank(required, thresholds):
        return False, f"需要达到{required}"
    entry_gold = max(int(region.get("entry_gold") or 0), 0)
    if int(profile.gold or 0) < entry_gold:
        return False, f"需要 🪙 {entry_gold} 金币作为补给"
    return True, ""


def _success_chance(
    profile: DoupoProfile,
    region: dict[str, Any],
    choice: dict[str, Any],
    danger: int,
    settings: dict[str, Any] | None = None,
    *,
    power_override: int | None = None,
) -> int:
    base = int(choice.get("base_chance") or 100)
    if base >= 100:
        return 100
    recommended = power_override if power_override else max(int(region.get("recommended_power") or 1), 1)
    power = _battle_power(profile, settings)
    power_adjustment = round(((power / recommended) - 1.0) * 18)
    power_adjustment = min(max(power_adjustment, -18), 18)
    technique_bonus = min(max(int(profile.technique_level or 0), 0), 8)
    fire_bonus = min(max(int(getattr(profile, "fire_rank", 0) or 0), 0) * 2, 8)
    return min(max(base + power_adjustment + technique_bonus + fire_bonus - max(int(danger or 0), 0) * 2, 20), 95)


def _coerce_chance(value: Any, default: int) -> int:
    if value is None or value == "":
        return min(max(int(default), 0), 100)
    try:
        return min(max(int(value), 0), 100)
    except (TypeError, ValueError):
        return min(max(int(default), 0), 100)


def _pick_next_event(
    row: DoupoExpedition,
    region: dict[str, Any],
    profile: DoupoProfile | None = None,
    settings: dict[str, Any] | None = None,
) -> str:
    """Pick the next event key.

    优先级：隐藏事件（低概率、境界达标）→ 区域首领（``boss:<region_key>``，每步小概率）→
    常规事件。Boss 与隐藏事件不会紧接同一种连续出现。
    """
    settings = settings or {}
    hidden_chance = _coerce_chance(settings.get("expedition_hidden_event_chance"), 8)
    boss_chance = _coerce_chance(settings.get("expedition_boss_chance"), 14)
    history = list(row.history or [])
    previous = str((history[-1] if history else {}).get("event_key") or row.current_event_key or "")
    if profile is not None and hidden_chance > 0 and random.randint(1, 100) <= hidden_chance:
        thresholds = settings.get("realm_thresholds") or []
        player_realm = str(profile.realm_stage or "斗之气")
        hidden_pool = [
            hk
            for hk, hv in EXPEDITION_HIDDEN_EVENTS.items()
            if realm_rank(player_realm, thresholds) >= realm_rank(str(hv.get("realm_stage_min") or "斗之气"), thresholds)
        ]
        non_repeat = [hk for hk in hidden_pool if hk != previous] or hidden_pool
        if non_repeat:
            return random.choice(non_repeat)
    if boss_chance > 0 and random.randint(1, 100) <= boss_chance:
        boss = expedition_boss_for_region(str(region.get("key") or ""))
        if boss is not None:
            boss_key = f"boss:{region['key']}"
            if boss_key != previous:
                return boss_key
    event_keys = [key for key in region.get("event_keys") or [] if key in EXPEDITION_EVENTS]
    if not event_keys:
        raise ValueError("该区域暂未配置游历事件")
    choices = [key for key in event_keys if key != previous] or event_keys
    return random.choice(choices)


def _loot_payload(raw: Any) -> dict[str, Any]:
    loot = dict(raw or {})
    items = {str(key): max(int(value or 0), 0) for key, value in dict(loot.get("items") or {}).items() if int(value or 0) > 0}
    return {
        "douqi": max(int(loot.get("douqi") or 0), 0),
        "gold": max(int(loot.get("gold") or 0), 0),
        "items": items,
    }


def _item_rows(items: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, quantity in items.items():
        catalog = _catalog_item(key)
        rows.append({
            "item_key": key,
            "name": str(catalog.get("name") or key),
            "rarity": str(catalog.get("rarity") or "凡品"),
            "quantity": int(quantity),
        })
    return rows


def _serialize_current_event(
    row: DoupoExpedition,
    profile: DoupoProfile,
    region: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    event = expedition_event_for_key(str(row.current_event_key or ""))
    if not event:
        return None
    kind = str(event.get("kind") or "normal")
    boss_power = max(int(event.get("boss_power") or 0), 1) if kind == "boss" else None
    options = []
    for choice in event.get("choices") or []:
        item = dict(choice)
        options.append({
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or "继续"),
            "description": str(item.get("description") or ""),
            "risk": str(item.get("risk") or "未知"),
            "success_chance": _success_chance(
                profile,
                region,
                item,
                int(row.danger or 0),
                settings,
                power_override=boss_power if (kind == "boss" and bool(item.get("boss_fight"))) else None,
            ),
        })
    serialized = {
        "key": str(row.current_event_key),
        "kind": kind,
        "title": str(event.get("title") or "未知事件"),
        "story": str(event.get("story") or ""),
        "choices": options,
    }
    if kind == "boss":
        serialized["boss_key"] = str(event.get("boss_key") or "")
        serialized["boss_name"] = str(event.get("boss_name") or "区域首领")
        serialized["boss_power"] = boss_power
    return serialized


def _serialize_run(row: DoupoExpedition, profile: DoupoProfile, settings: dict[str, Any]) -> dict[str, Any]:
    region = expedition_region(str(row.region_key)) or {"key": row.region_key, "name": row.region_key}
    loot = _loot_payload(row.loot)
    settlement = dict(row.settlement or {})
    if settlement.get("items") and not settlement.get("item_rows"):
        settlement["item_rows"] = _item_rows(dict(settlement.get("items") or {}))
    return {
        "id": int(row.id),
        "status": str(row.status or "active"),
        "region_key": str(row.region_key),
        "region_name": str(region.get("name") or row.region_key),
        "step": int(row.step or 0),
        "max_steps": max(int(row.max_steps or 1), 1),
        "vitality": max(int(row.vitality or 0), 0),
        "max_vitality": max(int(row.max_vitality or 100), 1),
        "danger": max(int(row.danger or 0), 0),
        "loot": {**loot, "item_rows": _item_rows(loot["items"])},
        "current_event": _serialize_current_event(row, profile, region, settings) if row.status == "active" else None,
        "history": list(row.history or [])[-6:],
        "settlement": settlement,
        "can_retreat": row.status == "active" and int(row.step or 0) > 0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def get_expedition_overview(tg: int) -> dict[str, Any]:
    actor_tg = int(tg)
    get_or_create_profile(actor_tg)
    settings = get_settings()
    usage_snapshot = get_daily_action_usage(actor_tg, settings)
    daily_usage = dict((usage_snapshot.get("items") or {}).get("expedition") or {})
    action_points = dict(usage_snapshot.get("action_points") or {})
    point_cost = max(int((settings.get("action_point_costs") or {}).get("expedition") or 0), 0)
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).first()
        active = _active_expedition(session, actor_tg)
        if active is not None and _expedition_is_stale(active):
            # 超时游历自动按失败结算，释放占位，玩家可重新开始。
            _settle_expedition(session, active, profile, settings, "failed")
            session.commit()
            active = None
        latest = (
            session.query(DoupoExpedition)
            .filter(DoupoExpedition.tg == actor_tg, DoupoExpedition.status != "active")
            .order_by(DoupoExpedition.id.desc())
            .first()
        )
        regions = []
        for source in EXPEDITION_REGIONS:
            region = dict(source)
            available, reason = _region_available(profile, region, settings)
            if daily_usage.get("remaining") == 0:
                available, reason = False, "今日游历次数已用完"
            if action_points.get("remaining") is not None and int(action_points["remaining"]) < point_cost:
                available, reason = False, f"今日行动力不足，需要 {point_cost} 点"
            boss = expedition_boss_for_region(region["key"])
            regions.append({
                "key": region["key"],
                "name": region["name"],
                "description": region["description"],
                "realm_stage_min": region["realm_stage_min"],
                "recommended_power": int(region["recommended_power"]),
                "entry_gold": int(region["entry_gold"]),
                "max_steps": int(region["max_steps"]),
                "available": available and active is None,
                "disabled_reason": "已有一段游历正在进行" if active is not None else reason,
                "boss": {
                    "key": str(boss["key"]),
                    "name": str(boss["name"]),
                    "realm_stage_min": str(boss.get("realm_stage_min") or "斗之气"),
                    "power": int(boss.get("power") or 0),
                } if boss else None,
            })
        return {
            "daily_usage": daily_usage,
            "action_points": {**action_points, "cost": point_cost},
            "regions": regions,
            "active": _serialize_run(active, profile, settings) if active else None,
            "last_run": _serialize_run(latest, profile, settings) if latest else None,
        }


def start_expedition(tg: int, region_key: str) -> dict[str, Any]:
    actor_tg = int(tg)
    get_or_create_profile(actor_tg)
    settings = get_settings()
    region = expedition_region(region_key)
    if not region:
        raise ValueError("未知游历区域")
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        stale = _active_expedition(session, actor_tg, lock=True)
        if stale is not None and _expedition_is_stale(stale):
            # 超时游历先按失败结算，再允许新开，避免永久占位。
            _settle_expedition(session, stale, profile, settings, "failed")
            stale = None
        if stale:
            raise ValueError("你已有一段游历正在进行")
        available, reason = _region_available(profile, region, settings)
        if not available:
            raise ValueError(reason)
        now = utcnow()
        daily_counter, _daily_limit = _check_daily_action_limit(session, actor_tg, "expedition", settings, now)
        point_counter, _point_limit, point_cost = _check_daily_action_points(
            session,
            actor_tg,
            "expedition",
            settings,
            now,
        )
        _increment_daily_action_counter(daily_counter)
        _consume_daily_action_points(point_counter, point_cost)
        entry_gold = max(int(region.get("entry_gold") or 0), 0)
        ledger: DoupoEconomyLedger | None = None
        if entry_gold:
            profile.gold = int(profile.gold or 0) - entry_gold
            ledger = _get_or_create_economy_ledger_session(session, actor_tg, _economy_day_key())
            ledger.gold_sink = int(ledger.gold_sink or 0) + entry_gold
            ledger.updated_at = utcnow()
        row = DoupoExpedition(
            tg=actor_tg,
            region_key=str(region["key"]),
            status="active",
            step=0,
            max_steps=int(region["max_steps"]),
            vitality=100,
            max_vitality=100,
            danger=0,
            loot={"douqi": 0, "gold": 0, "items": {}},
            history=[],
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        row.current_event_key = _pick_next_event(row, region, profile, settings)
        session.commit()
        session.refresh(row)
        return {
            "profile": serialize_profile(profile, settings),
            "detail": f"🗺️ 已进入{region['name']}，第一段事件已出现。",
            "expedition_result": _serialize_run(row, profile, settings),
        }


def _add_completion_bonus(row: DoupoExpedition, region: dict[str, Any]) -> None:
    loot = _loot_payload(row.loot)
    bonus = dict(region.get("completion_bonus") or {})
    loot["douqi"] += max(int(bonus.get("douqi") or 0), 0)
    loot["gold"] += max(int(bonus.get("gold") or 0), 0)
    for key, quantity in dict(bonus.get("items") or {}).items():
        loot["items"][str(key)] = int(loot["items"].get(str(key)) or 0) + max(int(quantity or 0), 0)
    row.loot = loot


def _settle_expedition(
    session,
    row: DoupoExpedition,
    profile: DoupoProfile,
    settings: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    retention = {"completed": 100, "retreated": 70, "failed": 30}.get(status, 0)
    loot = _loot_payload(row.loot)
    kept_douqi = loot["douqi"] * retention // 100
    kept_gold = loot["gold"] * retention // 100
    # 单件物品至少保留 1 件（30% 时 1*30//100=0 的边界修复）。
    kept_items = {key: max(quantity * retention // 100, 1) for key, quantity in loot["items"].items()}
    result = {
        "gold_capped_delta": 0,
        "economy_capped": False,
        "douqi_capped_delta": 0,
        "douqi_bottleneck_delta": 0,
        "douqi_soft_capped": False,
        "douqi_hard_capped": False,
    }
    douqi_actual = _apply_douqi_delta_with_balance(session, profile, kept_douqi, settings, result)
    ledger = _get_or_create_economy_ledger_session(session, int(profile.tg), _economy_day_key())
    gold_actual = _apply_gold_delta_with_economy(profile, kept_gold, ledger, settings, result)
    granted_items: dict[str, int] = {}
    for key, quantity in kept_items.items():
        granted = _grant_inventory_item_session(session, int(profile.tg), key, quantity)
        if granted:
            granted_items[key] = int(granted["quantity"])
    _apply_realm_progress(profile, settings)
    row.status = status
    row.current_event_key = None
    row.completed_at = utcnow()
    row.updated_at = row.completed_at
    row.settlement = {
        "retention_percent": retention,
        "douqi": douqi_actual,
        "douqi_capped": int(result["douqi_capped_delta"]),
        "douqi_bottleneck": int(result["douqi_bottleneck_delta"]),
        "gold": gold_actual,
        "gold_capped": int(result["gold_capped_delta"]),
        "items": granted_items,
    }
    status_label = {"completed": "完成游历", "retreated": "安全撤离", "failed": "重伤撤回"}[status]
    detail = f"🗺️ {status_label}，带回 🌀 斗气 {douqi_actual}、🪙 金币 {gold_actual}"
    if granted_items:
        detail += "、💍 " + "、".join(f"{_catalog_item(key).get('name', key)} x{qty}" for key, qty in granted_items.items())
    if result["gold_capped_delta"]:
        detail += f"；🪙 另有 {result['gold_capped_delta']} 金币触及今日上限"
    if result["douqi_capped_delta"]:
        detail += f"；🌀 另有 {result['douqi_capped_delta']} 斗气受今日衰减影响"
    if result["douqi_bottleneck_delta"]:
        detail += f"；🌀 另有 {result['douqi_bottleneck_delta']} 斗气因境界瓶颈未吸收"
    session.add(DoupoJournal(tg=int(profile.tg), action_type="expedition", title=f"游历：{status_label}", detail=detail))
    return {"detail": detail, "status": status, "settlement": dict(row.settlement or {})}


def choose_expedition_event(tg: int, choice_key: str, focus_score: int = 50) -> dict[str, Any]:
    actor_tg = int(tg)
    settings = get_settings()
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        if profile is None:
            raise ValueError("请先初始化斗破角色")
        row = _active_expedition(session, actor_tg, lock=True)
        if row is None:
            raise ValueError("当前没有进行中的游历")
        if _expedition_is_stale(row):
            # 超时游历自动按失败结算，玩家需重新开始。
            _settle_expedition(session, row, profile, settings, "failed")
            session.commit()
            raise ValueError("上一段游历已超时结算，请重新开始游历")
        region = expedition_region(str(row.region_key))
        event = expedition_event_for_key(str(row.current_event_key or ""))
        if not region or not event:
            raise ValueError("当前游历事件配置已失效，请联系管理员")
        choice = next((dict(item) for item in event.get("choices") or [] if str(item.get("key")) == str(choice_key)), None)
        if not choice:
            raise ValueError("无效的事件选择")
        kind = str(event.get("kind") or "normal")
        boss = expedition_boss_for_region(str(row.region_key)) if kind == "boss" else None
        boss_rewards = dict((boss or {}).get("rewards") or {})
        is_boss_fight = kind == "boss" and bool(choice.get("boss_fight"))
        power_override = max(int(event.get("boss_power") or boss.get("power") or 0), 1) if is_boss_fight else None
        bounded_focus = min(max(int(focus_score or 0), 0), 100)
        focus_chance, focus_damage, focus_grade = _focus_profile(bounded_focus)
        chance = min(
            max(
                _success_chance(profile, region, choice, int(row.danger or 0), settings, power_override=power_override)
                + focus_chance,
                10,
            ),
            98,
        )
        if int(choice.get("base_chance") or 100) >= 100:
            chance = 100
        roll = random.randint(1, 100)
        success = roll <= chance
        effect = dict(choice.get("success" if success else "failure") or choice.get("success") or {})
        damage = max(_roll_pair(effect.get("damage")) + focus_damage, 0)
        douqi_gain = max(_roll_pair(effect.get("douqi")), 0)
        gold_gain = max(_roll_pair(effect.get("gold")), 0)
        loot = _loot_payload(row.loot)
        loot["douqi"] += douqi_gain
        loot["gold"] += gold_gain
        dropped: list[dict[str, Any]] = []
        if success:
            for key, drop_chance in dict(effect.get("drops") or {}).items():
                if not bool(_catalog_item(str(key)).get("enabled", True)):
                    continue
                if random.randint(1, 100) <= max(min(int(drop_chance or 0), 100), 0):
                    loot["items"][str(key)] = int(loot["items"].get(str(key)) or 0) + 1
                    dropped.extend(_item_rows({str(key): 1}))
        row.loot = loot
        row.vitality = max(int(row.vitality or 0) - damage, 0)
        row.danger = min(max(int(row.danger or 0) + int(effect.get("danger") or 0), 0), 10)
        row.step = int(row.step or 0) + 1
        outcome = "成功" if success else "失手"
        summary = f"{'✅ 成功' if success else '💥 失手'}，{focus_grade}聚气，❤️ 体力 -{damage}，暂存 🌀 斗气 +{douqi_gain}、🪙 金币 +{gold_gain}"
        boss_defeated = None
        boss_score_gained = 0
        if is_boss_fight and success:
            boss_defeated = str(event.get("boss_name") or "区域首领")
            boss_score_gained = max(int(boss_rewards.get("boss_score") or 0), 0)
            if boss_score_gained:
                profile.boss_score = int(profile.boss_score or 0) + boss_score_gained
            journal = DoupoJournal(
                tg=int(profile.tg),
                action_type="expedition",
                title=f"讨伐 {boss_defeated}",
                detail=f"👹 在「{region.get('name')}」讨伐区域首领 {boss_defeated} 成功，获得首领积分 +{boss_score_gained}。",
            )
            session.add(journal)
            summary += f"，👹 讨伐首领 {boss_defeated} 成功（首领积分 +{boss_score_gained}）"
        if dropped:
            summary += "，获得 💍 " + "、".join(f"{item['name']} x{item['quantity']}" for item in dropped)
        history = list(row.history or [])
        history.append({
            "event_key": str(row.current_event_key),
            "event_title": str(event.get("title") or "游历事件"),
            "choice_key": str(choice.get("key") or ""),
            "choice_label": str(choice.get("label") or "继续"),
            "success": success,
            "chance": chance,
            "roll": roll,
            "focus_score": bounded_focus,
            "focus_grade": focus_grade,
            "summary": summary,
        })
        row.history = history[-20:]
        row.updated_at = utcnow()
        settlement = None
        # 结算优先级：走满且体力 > 0 → 完成；否则体力耗尽 → 失败（修"最后一步死亡覆盖完成"）。
        if row.step >= row.max_steps and row.vitality > 0:
            _add_completion_bonus(row, region)
            settlement = _settle_expedition(session, row, profile, settings, "completed")
        elif row.vitality <= 0:
            settlement = _settle_expedition(session, row, profile, settings, "failed")
        else:
            row.current_event_key = _pick_next_event(row, region, profile, settings)
        session.commit()
        session.refresh(row)
        detail = settlement["detail"] if settlement else summary
        result: dict[str, Any] = {
            "profile": serialize_profile(profile, settings),
            "detail": detail,
            "expedition_result": _serialize_run(row, profile, settings),
        }
        if boss_defeated:
            result["boss_defeated"] = boss_defeated
            result["boss_score_gained"] = boss_score_gained
        return result


def retreat_expedition(tg: int) -> dict[str, Any]:
    actor_tg = int(tg)
    settings = get_settings()
    with Session() as session:
        profile = session.query(DoupoProfile).filter(DoupoProfile.tg == actor_tg).with_for_update().first()
        row = _active_expedition(session, actor_tg, lock=True)
        if profile is None or row is None:
            raise ValueError("当前没有进行中的游历")
        if int(row.step or 0) <= 0:
            # 0 步游历（未完成任何事件）允许结束，按失败结算，避免软锁。
            settlement = _settle_expedition(session, row, profile, settings, "failed")
            settlement["detail"] = "🗺️ 未完成任何事件，游历已结束"
        else:
            settlement = _settle_expedition(session, row, profile, settings, "retreated")
        session.commit()
        session.refresh(row)
        return {
            "profile": serialize_profile(profile, settings),
            "detail": settlement["detail"],
            "expedition_result": _serialize_run(row, profile, settings),
        }
