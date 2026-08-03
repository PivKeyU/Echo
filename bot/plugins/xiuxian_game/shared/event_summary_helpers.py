from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from bot.sql_helper.sql_xiuxian import DEFAULT_SETTINGS, get_xiuxian_settings

SHANGHAI_TZ = timezone(timedelta(hours=8))


def _event_summary_interval_minutes(settings: dict[str, Any] | None = None) -> int:
    source = settings if isinstance(settings, dict) else get_xiuxian_settings()
    try:
        value = int(source.get("event_summary_interval_minutes", DEFAULT_SETTINGS.get("event_summary_interval_minutes", 10)) or 0)
    except (TypeError, ValueError):
        value = int(DEFAULT_SETTINGS.get("event_summary_interval_minutes", 10))
    return max(value, 0)


def _parse_shanghai_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(SHANGHAI_TZ)


def _summary_remaining_text(end_at: str | None) -> str:
    target = _parse_shanghai_datetime(end_at)
    if target is None:
        return "剩余未知"
    remaining = max(int((target - datetime.now(SHANGHAI_TZ)).total_seconds()), 0)
    if remaining <= 0:
        return "已到时"
    hours, rem = divmod(remaining, 3600)
    minutes = max(rem // 60, 0)
    if hours > 0:
        return f"剩 {hours}时{minutes}分"
    return f"剩 {max(minutes, 1)}分"


def _message_text_content(message: Any) -> str:
    return str(getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


def _message_id_value(message: Any) -> int:
    return int(getattr(message, "id", None) or getattr(message, "message_id", None) or 0)


def _is_message_not_modified_error(exc: Exception) -> bool:
    detail = str(exc or "").strip().lower()
    return "message is not modified" in detail or "message_not_modified" in detail


__all__ = [
    "_event_summary_interval_minutes",
    "_summary_remaining_text",
    "_message_text_content",
    "_message_id_value",
    "_is_message_not_modified_error",
]
