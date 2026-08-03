from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint, func

from bot.sql_helper import Base, Session

DEFAULT_WARN_THRESHOLD = max(int(os.getenv("PIVKEYU_WARN_THRESHOLD", "3") or 3), 1)
DEFAULT_WARN_ACTION = str(os.getenv("PIVKEYU_WARN_ACTION", "mute") or "mute").strip().lower()
DEFAULT_WARN_MUTE_MINUTES = max(int(os.getenv("PIVKEYU_WARN_MUTE_MINUTES", "60") or 60), 1)
MAX_REASON_LENGTH = 255
ALLOWED_WARN_ACTIONS = {"mute", "kick"}


def normalize_warn_action(value: str | None) -> str:
    normalized = str(value or DEFAULT_WARN_ACTION or "mute").strip().lower()
    return normalized if normalized in ALLOWED_WARN_ACTIONS else "mute"


def _normalize_reason(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:MAX_REASON_LENGTH]


class GroupModerationSetting(Base):
    __tablename__ = "group_moderation_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False, unique=True)
    warn_threshold = Column(Integer, nullable=False, default=DEFAULT_WARN_THRESHOLD)
    warn_action = Column(String(16), nullable=False, default=normalize_warn_action(DEFAULT_WARN_ACTION))
    mute_minutes = Column(Integer, nullable=False, default=DEFAULT_WARN_MUTE_MINUTES)
    updated_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GroupModerationWarning(Base):
    __tablename__ = "group_moderation_warnings"
    __table_args__ = (
        UniqueConstraint("chat_id", "tg", name="uq_group_moderation_warning_chat_tg"),
        Index("ix_group_moderation_warning_chat_id", "chat_id"),
        Index("ix_group_moderation_warning_tg", "tg"),
        Index("ix_group_moderation_warning_count", "warn_count"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False)
    tg = Column(BigInteger, nullable=False)
    warn_count = Column(Integer, nullable=False, default=0)
    last_reason = Column(String(MAX_REASON_LENGTH), nullable=True)
    last_warned_by = Column(BigInteger, nullable=True)
    last_warned_at = Column(DateTime, nullable=False, server_default=func.now())
    last_action = Column(String(16), nullable=True)
    last_action_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


def serialize_group_moderation_setting(row: GroupModerationSetting | None) -> dict[str, Any]:
    row = row or GroupModerationSetting()
    return {
        "chat_id": int(row.chat_id) if row.chat_id is not None else None,
        "warn_threshold": max(int(row.warn_threshold or DEFAULT_WARN_THRESHOLD), 1),
        "warn_action": normalize_warn_action(row.warn_action),
        "mute_minutes": max(int(row.mute_minutes or DEFAULT_WARN_MUTE_MINUTES), 1),
        "updated_by": int(row.updated_by) if row.updated_by is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def serialize_group_moderation_warning(row: GroupModerationWarning | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row.id),
        "chat_id": int(row.chat_id),
        "tg": int(row.tg),
        "warn_count": max(int(row.warn_count or 0), 0),
        "last_reason": row.last_reason,
        "last_warned_by": int(row.last_warned_by) if row.last_warned_by is not None else None,
        "last_warned_at": row.last_warned_at.isoformat() if row.last_warned_at else None,
        "last_action": row.last_action,
        "last_action_at": row.last_action_at.isoformat() if row.last_action_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_group_moderation_setting(chat_id: int | str) -> dict[str, Any]:
    chat_id = int(chat_id)
    with Session() as session:
        row = (
            session.query(GroupModerationSetting)
            .filter(GroupModerationSetting.chat_id == chat_id)
            .first()
        )
        if row is None:
            row = GroupModerationSetting(
                chat_id=chat_id,
                warn_threshold=DEFAULT_WARN_THRESHOLD,
                warn_action=normalize_warn_action(DEFAULT_WARN_ACTION),
                mute_minutes=DEFAULT_WARN_MUTE_MINUTES,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        return serialize_group_moderation_setting(row)


def update_group_moderation_setting(
    chat_id: int | str,
    *,
    warn_threshold: int | None = None,
    warn_action: str | None = None,
    mute_minutes: int | None = None,
    updated_by: int | None = None,
) -> dict[str, Any]:
    chat_id = int(chat_id)
    normalized_threshold = max(int(warn_threshold or DEFAULT_WARN_THRESHOLD), 1)
    normalized_action = normalize_warn_action(warn_action)
    normalized_mute_minutes = max(int(mute_minutes or DEFAULT_WARN_MUTE_MINUTES), 1)
    actor_id = int(updated_by) if updated_by is not None else None

    with Session() as session:
        row = (
            session.query(GroupModerationSetting)
            .filter(GroupModerationSetting.chat_id == chat_id)
            .with_for_update()
            .first()
        )
        if row is None:
            row = GroupModerationSetting(chat_id=chat_id)
            session.add(row)

        row.warn_threshold = normalized_threshold
        row.warn_action = normalized_action
        row.mute_minutes = normalized_mute_minutes
        row.updated_by = actor_id
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        return serialize_group_moderation_setting(row)


def get_group_moderation_warning(chat_id: int | str, tg: int | str) -> dict[str, Any] | None:
    chat_id = int(chat_id)
    tg = int(tg)
    with Session() as session:
        row = (
            session.query(GroupModerationWarning)
            .filter(
                GroupModerationWarning.chat_id == chat_id,
                GroupModerationWarning.tg == tg,
            )
            .first()
        )
        return serialize_group_moderation_warning(row)


def get_group_warning_map(chat_id: int | str, tg_ids: list[int] | set[int] | tuple[int, ...]) -> dict[int, dict[str, Any]]:
    normalized_ids = sorted({int(value) for value in tg_ids if value is not None})
    if not normalized_ids:
        return {}

    with Session() as session:
        rows = (
            session.query(GroupModerationWarning)
            .filter(
                GroupModerationWarning.chat_id == int(chat_id),
                GroupModerationWarning.tg.in_(normalized_ids),
                GroupModerationWarning.warn_count > 0,
            )
            .all()
        )
        return {int(row.tg): serialize_group_moderation_warning(row) for row in rows}


def list_group_moderation_warnings(chat_id: int | str, *, limit: int = 100) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(GroupModerationWarning)
            .filter(
                GroupModerationWarning.chat_id == int(chat_id),
                GroupModerationWarning.warn_count > 0,
            )
            .order_by(
                GroupModerationWarning.warn_count.desc(),
                GroupModerationWarning.last_warned_at.desc(),
                GroupModerationWarning.id.desc(),
            )
            .limit(max(int(limit), 1))
            .all()
        )
        return [serialize_group_moderation_warning(row) for row in rows]


def increment_group_moderation_warning(
    chat_id: int | str,
    tg: int | str,
    *,
    actor_tg: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    normalized_reason = _normalize_reason(reason)
    actor_id = int(actor_tg) if actor_tg is not None else None

    with Session() as session:
        row = (
            session.query(GroupModerationWarning)
            .filter(
                GroupModerationWarning.chat_id == chat_id,
                GroupModerationWarning.tg == tg,
            )
            .with_for_update()
            .first()
        )
        if row is None:
            row = GroupModerationWarning(chat_id=chat_id, tg=tg, warn_count=0)
            session.add(row)

        previous_count = max(int(row.warn_count or 0), 0)
        row.warn_count = previous_count + 1
        row.last_reason = normalized_reason
        row.last_warned_by = actor_id
        row.last_warned_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        return {
            "previous_count": previous_count,
            "item": serialize_group_moderation_warning(row),
        }


def mark_group_warning_action(chat_id: int | str, tg: int | str, action: str | None) -> dict[str, Any] | None:
    normalized_action = normalize_warn_action(action)
    with Session() as session:
        row = (
            session.query(GroupModerationWarning)
            .filter(
                GroupModerationWarning.chat_id == int(chat_id),
                GroupModerationWarning.tg == int(tg),
            )
            .with_for_update()
            .first()
        )
        if row is None:
            return None
        row.last_action = normalized_action
        row.last_action_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        return serialize_group_moderation_warning(row)


def clear_group_moderation_warning(chat_id: int | str, tg: int | str) -> dict[str, Any]:
    with Session() as session:
        row = (
            session.query(GroupModerationWarning)
            .filter(
                GroupModerationWarning.chat_id == int(chat_id),
                GroupModerationWarning.tg == int(tg),
            )
            .with_for_update()
            .first()
        )
        if row is None:
            return {"removed": False, "item": None}

        payload = serialize_group_moderation_warning(row)
        session.delete(row)
        session.commit()
        return {"removed": True, "item": payload}
