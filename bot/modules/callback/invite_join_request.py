from __future__ import annotations

from bot import LOGGER, bot
from bot.sql_helper.sql_invite import (
    find_pending_invite_by_link,
    get_invite_settings,
    mark_invite_record_request,
)


def _invite_link_value(invite_link_obj) -> str:
    if not invite_link_obj:
        return ""
    for field in ("invite_link", "link"):
        value = getattr(invite_link_obj, field, None)
        if value:
            return str(value)
    return str(invite_link_obj or "").strip()


async def _safe_decline(client, chat_id: int, user_id: int) -> None:
    try:
        await client.decline_chat_join_request(chat_id=chat_id, user_id=user_id)
    except Exception as exc:
        LOGGER.warning(f"decline invite join request failed chat={chat_id} user={user_id}: {exc}")


async def _safe_revoke(client, chat_id: int, invite_link: str) -> None:
    if not invite_link:
        return
    try:
        await client.revoke_chat_invite_link(chat_id=chat_id, invite_link=invite_link)
    except Exception as exc:
        LOGGER.warning(f"revoke consumed invite link failed chat={chat_id}: {exc}")


@bot.on_chat_join_request()
async def invite_join_request_guard(client, request):
    settings = get_invite_settings()
    if not settings.get("enabled"):
        return

    chat_id = int(getattr(getattr(request, "chat", None), "id", 0) or 0)
    user_id = int(getattr(getattr(request, "from_user", None), "id", 0) or 0)
    invite_link = _invite_link_value(getattr(request, "invite_link", None))
    if not chat_id or not user_id or not invite_link:
        return

    record = find_pending_invite_by_link(chat_id, invite_link)
    if not record:
        return

    expected_user_id = int(record.get("invitee_tg") or 0)
    if settings.get("strict_target", True) and user_id != expected_user_id:
        mark_invite_record_request(record["id"], user_id, status="declined")
        await _safe_revoke(client, chat_id, invite_link)
        await _safe_decline(client, chat_id, user_id)
        LOGGER.info(
            f"invite join request declined and revoked record={record['id']} expected={expected_user_id} actual={user_id}"
        )
        return

    try:
        await client.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
        mark_invite_record_request(record["id"], user_id, status="approved")
        await _safe_revoke(client, chat_id, invite_link)
        LOGGER.info(f"invite join request approved record={record['id']} user={user_id} chat={chat_id}")
    except Exception as exc:
        LOGGER.warning(f"approve invite join request failed record={record['id']} user={user_id}: {exc}")
        mark_invite_record_request(record["id"], user_id, status="declined")
        await _safe_revoke(client, chat_id, invite_link)
        await _safe_decline(client, chat_id, user_id)
