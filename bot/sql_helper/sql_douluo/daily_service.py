"""每日任务、宗门学院与俸禄(领域玩法)。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bot.plugins.douluo_game.core import DAILY_TASK_CATALOG, task_by_key, sect_by_key, SECT_CATALOG
from bot.sql_helper import Session
from bot.sql_helper.sql_douluo.models import DouluoDailyTask, DouluoProfile, DouluoSectMember, utcnow
from bot.sql_helper.sql_douluo.service import (
    _apply_daily_income_caps,
    _check_daily_action_limit,
    _check_daily_action_points,
    _consume_daily_action_points,
    _economy_day_key,
    _increment_daily_action_counter,
    _load_profile,
    _serialize_profile_row,
    _action_point_cost,
    get_settings,
)

POSITION_MULTIPLIER: dict[str, float] = {
    "弟子": 1.0,
    "执事": 1.2,
    "长老": 1.5,
    "副宗主": 1.8,
    "宗主": 2.2,
}


def _get_or_create_task_session(
    session,
    tg: int,
    day_key: str,
    task_key: str,
    *,
    for_update: bool = False,
) -> DouluoDailyTask:
    query = session.query(DouluoDailyTask).filter(
        DouluoDailyTask.tg == int(tg),
        DouluoDailyTask.day_key == str(day_key),
        DouluoDailyTask.task_key == str(task_key),
    )
    if for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        row = DouluoDailyTask(tg=int(tg), day_key=str(day_key), task_key=str(task_key), progress=0, claimed=False)
        session.add(row)
        session.flush()
    return row


def _serialize_task(row: DouluoDailyTask, definition: dict[str, Any]) -> dict[str, Any]:
    target = int(definition.get("target") or 1)
    return {
        "task_key": row.task_key,
        "name": definition.get("name", row.task_key),
        "description": definition.get("description", ""),
        "metric": definition.get("metric", ""),
        "progress": int(row.progress or 0),
        "target": target,
        "completed": int(row.progress or 0) >= target,
        "claimed": bool(row.claimed),
        "claimable": int(row.progress or 0) >= target and not bool(row.claimed),
        "rewards": definition.get("rewards", {}),
    }


def list_daily_tasks(tg: int) -> dict[str, Any]:
    tg = int(tg)
    day_key = _economy_day_key()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        tasks = []
        for definition in DAILY_TASK_CATALOG:
            row = _get_or_create_task_session(
                session,
                tg,
                day_key,
                str(definition.get("key") or ""),
                for_update=True,
            )
            tasks.append(_serialize_task(row, definition))
        session.commit()
    sect = sect_by_key(str(profile.sect_key or "")) if profile and profile.sect_key else None
    return {
        "day_key": day_key,
        "tasks": tasks,
        "sect": sect,
        "sect_contribution": int(profile.sect_contribution or 0) if profile else 0,
        "sect_position": profile.sect_position if profile else None,
    }


def report_task_progress(tg: int, metric: str, amount: int = 1) -> None:
    tg = int(tg)
    day_key = _economy_day_key()
    metric = str(metric or "")
    amount = max(int(amount or 1), 1)
    if not metric:
        return
    with Session() as session:
        # 与领取流程使用相同锁顺序，避免并发上报丢失进度。
        _load_profile(session, tg, for_update=True)
        matched = [t for t in DAILY_TASK_CATALOG if t.get("metric") == metric]
        for definition in matched:
            row = _get_or_create_task_session(
                session,
                tg,
                day_key,
                str(definition.get("key") or ""),
                for_update=True,
            )
            target = int(definition.get("target") or 1)
            if int(row.progress or 0) < target:
                row.progress = min(int(row.progress or 0) + amount, target)
                row.updated_at = utcnow()
        session.commit()


def claim_daily_task(tg: int, task_key: str) -> dict[str, Any]:
    tg = int(tg)
    day_key = _economy_day_key()
    definition = task_by_key(task_key)
    if definition is None:
        raise ValueError("任务不存在")
    with Session() as session:
        # 先锁玩家，再读取并锁任务行。相同玩家的并发领取会在读取 claimed 前串行化。
        profile = _load_profile(session, tg, for_update=True)
        row = _get_or_create_task_session(session, tg, day_key, task_key, for_update=True)
        if bool(row.claimed):
            raise ValueError("该任务奖励已领取")
        if int(row.progress or 0) < int(definition.get("target") or 1):
            raise ValueError("任务尚未完成")
        rewards = definition.get("rewards", {})
        coin = max(int(rewards.get("coin") or 0), 0)
        soul_power = max(int(rewards.get("soul_power") or 0), 0)
        gained = _apply_daily_income_caps(
            session, tg, day_key, get_settings(), coin=coin, soul_power=soul_power
        )
        profile.coin = int(profile.coin or 0) + gained["coin"]
        profile.soul_power = int(profile.soul_power or 0) + gained["soul_power"]
        profile.updated_at = utcnow()
        row.claimed = True
        row.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
    return {
        "task_key": task_key,
        "name": definition.get("name", task_key),
        "coin_gained": gained["coin"],
        "soul_power_gained": gained["soul_power"],
        "coin": int(profile.coin or 0),
        "soul_power": int(profile.soul_power or 0),
    }


# ---------------------------------------------------------------------------
# 宗门
# ---------------------------------------------------------------------------
def list_sect_options() -> list[dict[str, Any]]:
    return SECT_CATALOG


def join_sect(tg: int, sect_key: str) -> dict[str, Any]:
    tg = int(tg)
    sect = sect_by_key(sect_key)
    if sect is None:
        raise ValueError("宗门不存在")
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if profile.sect_key:
            raise ValueError(f"你已加入 {profile.sect_key},当前版本暂不开放转宗")
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先觉醒武魂再入宗")
        entry_coin = max(int(sect.get("entry_coin") or 0), 0)
        if int(profile.coin or 0) < entry_coin:
            raise ValueError(f"加入该宗门需要 {entry_coin} 金魂币,当前不足")
        if entry_coin > 0:
            profile.coin = int(profile.coin or 0) - entry_coin
        profile.sect_key = sect["key"]
        profile.sect_position = "弟子"
        profile.sect_contribution = 0
        profile.updated_at = utcnow()
        member = session.query(DouluoSectMember).filter(DouluoSectMember.tg == tg).first()
        if member is None:
            member = DouluoSectMember(tg=tg, sect_key=sect["key"], position="弟子", contribution=0, total_contribution=0)
            session.add(member)
        else:
            member.sect_key = sect["key"]
            member.position = "弟子"
            member.contribution = 0
            member.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
    return {"tg": tg, "sect": sect, "profile": _serialize_profile_row(profile)}


def leave_sect(tg: int) -> dict[str, Any]:
    tg = int(tg)
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.sect_key:
            raise ValueError("你尚未加入任何宗门")
        sect_key = profile.sect_key
        profile.sect_key = None
        profile.sect_position = None
        profile.sect_contribution = 0
        profile.updated_at = utcnow()
        member = session.query(DouluoSectMember).filter(DouluoSectMember.tg == tg).first()
        if member is not None:
            session.delete(member)
        session.commit()
        session.refresh(profile)
    return {"tg": tg, "left_sect": sect_key, "profile": _serialize_profile_row(profile)}


def add_sect_contribution(tg: int, amount: int) -> dict[str, Any]:
    tg = int(tg)
    amount = max(int(amount or 0), 0)
    if amount <= 0:
        return {}
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.sect_key:
            return {}
        profile.sect_contribution = int(profile.sect_contribution or 0) + amount
        profile.updated_at = utcnow()
        member = session.query(DouluoSectMember).filter(DouluoSectMember.tg == tg).first()
        if member is not None:
            member.contribution = int(member.contribution or 0) + amount
            member.total_contribution = int(member.total_contribution or 0) + amount
            member.updated_at = utcnow()
        # 按贡献晋升职位
        sect = sect_by_key(str(profile.sect_key or ""))
        if sect is not None:
            positions = sect.get("positions", [])
            best = "弟子"
            for pos in positions:
                if int(profile.sect_contribution or 0) >= int(pos.get("required_contribution") or 0):
                    best = str(pos.get("name") or best)
                else:
                    break
            profile.sect_position = best
            if member is not None:
                member.position = best
        session.commit()
    return {"tg": tg, "contribution": int(profile.sect_contribution or 0), "position": profile.sect_position}


def claim_salary(tg: int) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.sect_key:
            raise ValueError("尚未加入宗门,无法领取俸禄")
        sect = sect_by_key(str(profile.sect_key or ""))
        if sect is None:
            raise ValueError("宗门不存在")
        action_counter, _, _ = _check_daily_action_points(session, tg, "salary", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "salary", settings, now)
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "salary"))
        _increment_daily_action_counter(daily_counter)

        base = max(int(sect.get("salary_coin") or 0), 0)
        mult = POSITION_MULTIPLIER.get(str(profile.sect_position or "弟子"), 1.0)
        coin_raw = int(base * mult)
        gained = _apply_daily_income_caps(session, tg, _economy_day_key(now), settings, coin=coin_raw)
        profile.coin = int(profile.coin or 0) + gained["coin"]
        profile.last_salary_at = now
        profile.updated_at = utcnow()
        member = session.query(DouluoSectMember).filter(DouluoSectMember.tg == tg).first()
        if member is not None:
            member.last_salary_at = now
            member.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
    try:
        from bot.sql_helper.sql_douluo.daily_service import report_task_progress

        report_task_progress(tg, "sect_duty", 1)
    except Exception:
        pass
    return {
        "tg": tg,
        "sect_name": sect.get("name"),
        "position": profile.sect_position,
        "coin_gained": gained["coin"],
        "coin": int(profile.coin or 0),
        "profile": _serialize_profile_row(profile),
    }
