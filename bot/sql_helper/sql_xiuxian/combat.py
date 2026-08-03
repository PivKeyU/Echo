from __future__ import annotations

import copy
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import event
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    or_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from bot.plugins.xiuxian_game import cache as xiuxian_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby
from .constants import *  # noqa: F401 F403
from .constants import _default_arena_stage_rule
from .models import *  # noqa: F401 F403
from .serializers import *  # noqa: F401 F403
from .profile import *  # noqa: F401 F403

def _arena_stage_rule_key(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    stage = normalize_realm_stage(entry.get("realm_stage"))
    return stage if stage in REALM_ORDER else None


def _merge_default_arena_stage_rules(raw: Any) -> list[dict[str, Any]]:
    current_rows = [copy.deepcopy(entry) for entry in raw] if isinstance(raw, list) else []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in current_rows:
        stage = _arena_stage_rule_key(entry)
        if stage is None or stage in seen:
            continue
        default_rule = _default_arena_stage_rule(stage, REALM_ORDER.index(stage))
        legacy_reward = int(get_realm_stage_rule(stage)["threshold_base"])
        reward_cultivation = max(int(entry.get("reward_cultivation", default_rule["reward_cultivation"]) or 0), 0)
        if reward_cultivation == legacy_reward:
            reward_cultivation = int(default_rule["reward_cultivation"])
        normalized.append(
            {
                "realm_stage": stage,
                "duration_minutes": max(int(entry.get("duration_minutes", default_rule["duration_minutes"]) or default_rule["duration_minutes"]), 1),
                "reward_cultivation": reward_cultivation,
            }
        )
        seen.add(stage)
    for index, stage in enumerate(REALM_ORDER):
        if stage in seen:
            continue
        normalized.append(copy.deepcopy(_default_arena_stage_rule(stage, index)))
    normalized.sort(key=lambda item: REALM_ORDER.index(item["realm_stage"]))
    return normalized


STALE_DUEL_LOCK_GRACE_SECONDS = 120


def _active_duel_pool_row(
    session: Session,
    tg: int,
    *,
    for_update: bool = False,
) -> XiuxianDuelBetPool | None:
    stale_cutoff = utcnow() - timedelta(seconds=STALE_DUEL_LOCK_GRACE_SECONDS)
    query = session.query(XiuxianDuelBetPool).filter(
        XiuxianDuelBetPool.resolved.is_(False),
        XiuxianDuelBetPool.bets_close_at > stale_cutoff,
        or_(XiuxianDuelBetPool.challenger_tg == tg, XiuxianDuelBetPool.defender_tg == tg),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianDuelBetPool.id.desc()).first()


def _cleanup_stale_duel_locks(
    session: Session,
    tg: int,
    *,
    for_update: bool = False,
) -> list[int]:
    stale_cutoff = utcnow() - timedelta(seconds=STALE_DUEL_LOCK_GRACE_SECONDS)
    query = session.query(XiuxianDuelBetPool).filter(
        XiuxianDuelBetPool.resolved.is_(False),
        XiuxianDuelBetPool.bets_close_at <= stale_cutoff,
        or_(XiuxianDuelBetPool.challenger_tg == tg, XiuxianDuelBetPool.defender_tg == tg),
    )
    if for_update:
        query = query.with_for_update()
    stale_pools = query.order_by(XiuxianDuelBetPool.id.asc()).all()
    cleaned_ids: list[int] = []

    for pool in stale_pools:
        bets = session.query(XiuxianDuelBet).filter(XiuxianDuelBet.pool_id == pool.id).all()
        for bet in bets:
            refund_amount = max(int(bet.amount or 0), 0)
            if refund_amount <= 0:
                continue
            profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(bet.tg)).with_for_update().first()
            if profile is None:
                continue
            apply_spiritual_stone_delta(
                session,
                int(bet.tg),
                refund_amount,
                action_text="退还过期斗法押注",
                allow_dead=True,
                apply_tribute=True,
            )
        pool.resolved = True
        pool.winner_tg = None
        pool.updated_at = utcnow()
        cleaned_ids.append(int(pool.id))

    if cleaned_ids:
        session.flush()
    return cleaned_ids


def get_active_duel_lock(tg: int) -> dict[str, Any] | None:
    with Session() as session:
        cleaned_ids = _cleanup_stale_duel_locks(session, tg, for_update=False)
        if cleaned_ids:
            session.commit()
        row = _active_duel_pool_row(session, tg, for_update=False)
        if row is None:
            return None
        return {
            "pool_id": int(row.id),
            "duel_mode": str(row.duel_mode or "standard"),
            "duel_mode_label": DUEL_MODE_LABELS.get(str(row.duel_mode or "standard"), str(row.duel_mode or "standard")),
            "challenger_tg": int(row.challenger_tg),
            "defender_tg": int(row.defender_tg),
            "bets_close_at": serialize_datetime(row.bets_close_at),
        }



def _fallback_duel_bet_amount_options(minimum: int, maximum: int) -> list[int]:
    if maximum <= minimum:
        return [minimum]
    midpoint = (minimum + maximum) // 2
    values = [minimum]
    if midpoint not in {minimum, maximum}:
        values.append(midpoint)
    values.append(maximum)
    return sorted(set(values))



def resolve_duel_bet_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    source = settings if isinstance(settings, dict) else {}
    default_options = list(DEFAULT_SETTINGS.get("duel_bet_amount_options") or [10, 50, 100])
    default_minimum = max(_coerce_int(DEFAULT_SETTINGS.get("duel_bet_min_amount"), min(default_options or [10])), 1)
    default_maximum = max(
        _coerce_int(DEFAULT_SETTINGS.get("duel_bet_max_amount"), max(default_options or [100])),
        default_minimum,
    )
    legacy_minutes = max(_coerce_int(source.get("duel_bet_minutes"), DEFAULT_SETTINGS.get("duel_bet_minutes", 2)), 1)
    raw_seconds = source.get("duel_bet_seconds")
    if raw_seconds is None:
        raw_seconds = legacy_minutes * 60
    seconds = min(max(_coerce_int(raw_seconds, DEFAULT_SETTINGS.get("duel_bet_seconds", 120)), 10), 3600)
    enabled = _coerce_bool(source.get("duel_bet_enabled"), _coerce_bool(DEFAULT_SETTINGS.get("duel_bet_enabled"), True))
    minimum = min(max(_coerce_int(source.get("duel_bet_min_amount"), default_minimum), 1), 1_000_000)
    maximum = min(max(_coerce_int(source.get("duel_bet_max_amount"), default_maximum), minimum), 1_000_000)
    options = _normalize_duel_bet_amount_options(
        source.get("duel_bet_amount_options"),
        minimum=minimum,
        maximum=maximum,
    )
    if not options:
        options = _fallback_duel_bet_amount_options(minimum, maximum)
    return {
        "duel_bet_enabled": enabled,
        "duel_bet_seconds": seconds,
        "duel_bet_min_amount": minimum,
        "duel_bet_max_amount": maximum,
        "duel_bet_amount_options": options,
    }



def create_duel_record(
    challenger_tg: int,
    defender_tg: int,
    winner_tg: int,
    loser_tg: int,
    challenger_rate: int,
    defender_rate: int,
    summary: str,
    duel_mode: str = "standard",
    battle_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with Session() as session:
        record = XiuxianDuelRecord(
            challenger_tg=challenger_tg,
            defender_tg=defender_tg,
            winner_tg=winner_tg,
            loser_tg=loser_tg,
            duel_mode=str(duel_mode or "standard"),
            challenger_rate=challenger_rate,
            defender_rate=defender_rate,
            summary=summary,
            battle_log=_sanitize_json_value(battle_log) if battle_log else [],
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return {
            "id": record.id,
            "challenger_tg": record.challenger_tg,
            "defender_tg": record.defender_tg,
            "winner_tg": record.winner_tg,
            "loser_tg": record.loser_tg,
            "duel_mode": record.duel_mode,
            "challenger_rate": record.challenger_rate,
            "defender_rate": record.defender_rate,
            "summary": record.summary,
            "battle_log": _sanitize_json_value(record.battle_log) or [],
            "created_at": serialize_datetime(record.created_at),
        }



def create_red_envelope(**fields) -> dict[str, Any]:
    with Session() as session:
        envelope = XiuxianRedEnvelope(**fields)
        session.add(envelope)
        session.commit()
        session.refresh(envelope)
        return serialize_red_envelope(envelope)


def get_red_envelope(envelope_id: int) -> XiuxianRedEnvelope | None:
    with Session() as session:
        return session.query(XiuxianRedEnvelope).filter(XiuxianRedEnvelope.id == envelope_id).first()


def list_red_envelope_claims(envelope_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianRedEnvelopeClaim)
            .filter(XiuxianRedEnvelopeClaim.envelope_id == envelope_id)
            .order_by(XiuxianRedEnvelopeClaim.id.asc())
            .all()
        )
        payload = [
            {
                "id": row.id,
                "envelope_id": row.envelope_id,
                "tg": row.tg,
                "amount": row.amount,
                "created_at": serialize_datetime(row.created_at),
            }
            for row in rows
        ]
    name_map = get_emby_name_map([int(item["tg"]) for item in payload])
    for item in payload:
        item["name"] = name_map.get(int(item["tg"]), f"TG {item['tg']}")
    return payload



def create_duel_bet_pool(**fields) -> dict[str, Any]:
    with Session() as session:
        pool = XiuxianDuelBetPool(**fields)
        session.add(pool)
        session.commit()
        session.refresh(pool)
        return {
            "id": pool.id,
            "challenger_tg": pool.challenger_tg,
            "defender_tg": pool.defender_tg,
            "stake": pool.stake,
            "group_chat_id": pool.group_chat_id,
            "duel_message_id": pool.duel_message_id,
            "bet_message_id": pool.bet_message_id,
            "bets_close_at": serialize_datetime(pool.bets_close_at),
            "resolved": pool.resolved,
            "winner_tg": pool.winner_tg,
        }


def get_duel_bet_pool(pool_id: int) -> XiuxianDuelBetPool | None:
    with Session() as session:
        return session.query(XiuxianDuelBetPool).filter(XiuxianDuelBetPool.id == pool_id).first()


__all__ = [name for name in globals() if not name.startswith("__")]
