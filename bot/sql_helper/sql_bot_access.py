from __future__ import annotations

import os
import threading
from time import monotonic

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func, or_

from bot.sql_helper import Base, Session

BOT_ACCESS_CACHE_TTL = max(int(os.getenv("PIVKEYU_BOT_ACCESS_CACHE_TTL", "60") or 60), 1)


class BotAccessBlock(Base):
    __tablename__ = "bot_access_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg = Column(BigInteger, nullable=True, unique=True)
    username = Column(String(255), nullable=True, unique=True)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


_cache_lock = threading.Lock()
_cache_payload: dict[str, object] = {
    "loaded_at": 0.0,
    "items": [],
    "tg_map": {},
    "username_map": {},
}


def normalize_bot_access_username(value: str | None) -> str | None:
    text = str(value or "").strip().lstrip("@").lower()
    return text or None


def serialize_bot_access_block(row: BotAccessBlock) -> dict[str, object | None]:
    username = normalize_bot_access_username(row.username)
    parts = []
    if row.tg is not None:
        parts.append(f"TG {int(row.tg)}")
    if username:
        parts.append(f"@{username}")

    return {
        "id": int(row.id),
        "tg": int(row.tg) if row.tg is not None else None,
        "username": username,
        "username_display": f"@{username}" if username else None,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "target_text": " / ".join(parts) if parts else "未指定目标",
        "match_scope_text": "TGID 与用户名" if row.tg is not None and username else ("TGID" if row.tg is not None else "用户名"),
    }


def invalidate_bot_access_cache() -> None:
    with _cache_lock:
        _cache_payload["loaded_at"] = 0.0
        _cache_payload["items"] = []
        _cache_payload["tg_map"] = {}
        _cache_payload["username_map"] = {}


def _load_bot_access_snapshot() -> dict[str, object]:
    with Session() as session:
        rows = (
            session.query(BotAccessBlock)
            .order_by(BotAccessBlock.created_at.desc(), BotAccessBlock.id.desc())
            .all()
        )

    items = [serialize_bot_access_block(row) for row in rows]
    tg_map = {int(item["tg"]): item for item in items if item.get("tg") is not None}
    username_map = {
        normalize_bot_access_username(item.get("username")): item
        for item in items
        if normalize_bot_access_username(item.get("username")) is not None
    }

    snapshot = {
        "loaded_at": monotonic(),
        "items": items,
        "tg_map": tg_map,
        "username_map": username_map,
    }
    with _cache_lock:
        _cache_payload.update(snapshot)
        return dict(_cache_payload)


def get_bot_access_snapshot(force: bool = False) -> dict[str, object]:
    with _cache_lock:
        loaded_at = float(_cache_payload.get("loaded_at") or 0.0)
        if not force and loaded_at and monotonic() - loaded_at <= BOT_ACCESS_CACHE_TTL:
            return dict(_cache_payload)
    return _load_bot_access_snapshot()


def find_bot_access_block(
    tg: int | str | None = None,
    username: str | None = None,
    snapshot: dict[str, object] | None = None,
) -> dict[str, object | None] | None:
    current = snapshot or get_bot_access_snapshot()

    if tg is not None:
        try:
            match = current.get("tg_map", {}).get(int(tg))
        except (TypeError, ValueError):
            match = None
        if match:
            return {**match, "match_type": "tg"}

    normalized_username = normalize_bot_access_username(username)
    if normalized_username:
        match = current.get("username_map", {}).get(normalized_username)
        if match:
            return {**match, "match_type": "username"}

    return None


def find_existing_bot_access_block(
    tg: int | None = None,
    username: str | None = None,
) -> BotAccessBlock | None:
    conditions = []
    if tg is not None:
        conditions.append(BotAccessBlock.tg == int(tg))
    normalized_username = normalize_bot_access_username(username)
    if normalized_username:
        conditions.append(BotAccessBlock.username == normalized_username)

    if not conditions:
        return None

    with Session() as session:
        return (
            session.query(BotAccessBlock)
            .filter(or_(*conditions))
            .order_by(BotAccessBlock.created_at.desc(), BotAccessBlock.id.desc())
            .first()
        )
