from __future__ import annotations

import aiohttp
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from pyrogram import enums
from pyrogram.types import ChatPermissions

from bot import LOGGER, bot, bot_token, group
from bot.sql_helper.sql_moderation import (
    get_group_moderation_setting,
    get_group_moderation_warning,
    get_group_warning_map,
    increment_group_moderation_warning,
    list_group_moderation_warnings,
    mark_group_warning_action,
    clear_group_moderation_warning,
    update_group_moderation_setting,
)


STATUS_TEXT_MAP = {
    "owner": "群主",
    "creator": "群主",
    "administrator": "管理员",
    "member": "普通成员",
    "restricted": "受限成员",
    "left": "已离开",
    "banned": "已封禁",
}


class ModerationServiceError(RuntimeError):
    pass


class ModerationLookupError(ModerationServiceError):
    pass


class ModerationAmbiguousError(ModerationServiceError):
    def __init__(self, matches: list[dict[str, Any]]):
        self.matches = matches
        super().__init__("匹配到多个群成员，请改用更精确的 TGID 或 @username。")


def iter_managed_chat_ids() -> list[int]:
    chat_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in group:
        try:
            chat_id = int(raw_value)
        except (TypeError, ValueError):
            continue
        if chat_id == 0 or chat_id in seen:
            continue
        seen.add(chat_id)
        chat_ids.append(chat_id)
    return chat_ids


def _status_value(status: Any) -> str:
    raw = getattr(status, "value", status)
    return str(raw or "").strip().lower()


def _user_identity_payload(user: Any) -> dict[str, Any]:
    first_name = str(getattr(user, "first_name", "") or "").strip()
    last_name = str(getattr(user, "last_name", "") or "").strip()
    username = str(getattr(user, "username", "") or "").strip().lstrip("@")
    display_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return {
        "tg": int(getattr(user, "id", 0) or 0),
        "display_name": display_name or None,
        "username": username or None,
        "is_bot": bool(getattr(user, "is_bot", False)),
    }


def _display_label(identity: dict[str, Any]) -> str:
    if identity.get("display_name"):
        return str(identity["display_name"])
    if identity.get("username"):
        return f"@{identity['username']}"
    return f"TG {identity.get('tg')}"


def _serialize_member(member: Any = None, *, user: Any = None, chat_id: int | None = None) -> dict[str, Any]:
    member_user = user or getattr(member, "user", None)
    if member_user is None:
        raise ModerationLookupError("未找到对应的 Telegram 用户。")

    identity = _user_identity_payload(member_user)
    status = _status_value(getattr(member, "status", None))
    is_admin = status in {"owner", "creator", "administrator"}
    return {
        "chat_id": int(chat_id) if chat_id is not None else None,
        "tg": int(identity["tg"]),
        "display_name": identity.get("display_name"),
        "username": identity.get("username"),
        "display_label": _display_label(identity),
        "status": status or None,
        "status_text": STATUS_TEXT_MAP.get(status or "", "未知状态"),
        "is_admin": is_admin,
        "is_bot": bool(identity.get("is_bot")),
        "is_member": member is not None,
    }


def _member_matches(payload: dict[str, Any], keyword: str) -> bool:
    normalized = str(keyword or "").strip().lower().lstrip("@")
    if not normalized:
        return False
    return any(
        normalized in str(payload.get(field) or "").strip().lower().lstrip("@")
        for field in ("display_name", "username", "tg")
    )


def _exact_member_match(payload: dict[str, Any], keyword: str) -> bool:
    normalized = str(keyword or "").strip().lower().lstrip("@")
    if not normalized:
        return False

    display_name = str(payload.get("display_name") or "").strip().lower()
    username = str(payload.get("username") or "").strip().lower()
    tg_text = str(payload.get("tg") or "").strip()
    return normalized in {display_name, username, tg_text}


async def _telegram_bot_api_post(method: str, payload: dict[str, Any]) -> Any:
    endpoint = f"https://api.telegram.org/bot{bot_token}/{method}"
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, json=payload) as response:
                data = await response.json(content_type=None)
    except Exception as exc:
        raise ModerationServiceError(f"调用 Telegram Bot API {method} 失败：{exc}") from exc

    if not isinstance(data, dict) or not data.get("ok"):
        description = str((data or {}).get("description") or f"Telegram Bot API {method} 失败。").strip()
        raise ModerationServiceError(description)
    return data.get("result")


def normalize_telegram_member_badge_text(value: str | None) -> str:
    text = str(value or "").strip()
    rows: list[str] = []
    for char in text:
        codepoint = ord(char)
        if codepoint in {0x200D, 0xFE0E, 0xFE0F}:
            continue
        if (
            0x1F000 <= codepoint <= 0x1FAFF
            or 0x2600 <= codepoint <= 0x27BF
            or unicodedata.category(char) == "So"
        ):
            continue
        rows.append(char)
    return "".join(rows).strip()[:16]


async def get_chat_member_details(chat_id: int | str, tg: int | str) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    result = await _telegram_bot_api_post("getChatMember", {"chat_id": chat_id, "user_id": tg})
    if not isinstance(result, dict):
        raise ModerationServiceError("未能获取群成员状态。")
    return result


async def list_managed_chats() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for chat_id in iter_managed_chat_ids():
        title = str(chat_id)
        username = None
        try:
            chat = await bot.get_chat(chat_id)
            title = str(getattr(chat, "title", None) or getattr(chat, "first_name", None) or chat_id)
            username = str(getattr(chat, "username", "") or "").strip().lstrip("@") or None
        except Exception as exc:
            LOGGER.warning(f"moderation get_chat failed chat_id={chat_id}: {exc}")

        items.append(
            {
                "chat_id": int(chat_id),
                "title": title,
                "username": username,
                "settings": get_group_moderation_setting(chat_id),
                "active_warning_count": len(list_group_moderation_warnings(chat_id, limit=500)),
            }
        )
    return items


async def _search_members_via_query(chat_id: int, keyword: str, limit: int) -> list[dict[str, Any]]:
    normalized_query = str(keyword or "").strip().lstrip("@")
    if not normalized_query:
        return []

    items: list[dict[str, Any]] = []
    seen: set[int] = set()
    search_filter = getattr(getattr(enums, "ChatMembersFilter", None), "SEARCH", None)
    query_options = [
        {"query": normalized_query, "limit": max(limit * 2, 20)},
        {"query": normalized_query, "filter": search_filter, "limit": max(limit * 2, 20)} if search_filter is not None else None,
    ]

    for options in [option for option in query_options if option]:
        try:
            async for member in bot.get_chat_members(chat_id, **options):
                payload = _serialize_member(member, chat_id=chat_id)
                if payload["tg"] in seen or not _member_matches(payload, normalized_query):
                    continue
                seen.add(payload["tg"])
                items.append(payload)
                if len(items) >= limit:
                    return items
            if items:
                return items
        except TypeError:
            continue
        except Exception as exc:
            LOGGER.warning(f"moderation query search failed chat_id={chat_id} keyword={keyword!r}: {exc}")
            break

    return items


async def search_chat_members(chat_id: int | str, keyword: str, *, limit: int = 20, scan_limit: int = 800) -> list[dict[str, Any]]:
    chat_id = int(chat_id)
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return []

    if normalized_keyword.lstrip("-").isdigit():
        try:
            return [await get_chat_member_brief(chat_id, int(normalized_keyword))]
        except ModerationLookupError:
            return []

    queried = await _search_members_via_query(chat_id, normalized_keyword, limit)
    if queried:
        return queried

    matches: list[dict[str, Any]] = []
    seen: set[int] = set()
    scanned = 0
    try:
        async for member in bot.get_chat_members(chat_id):
            scanned += 1
            payload = _serialize_member(member, chat_id=chat_id)
            if payload["tg"] in seen or not _member_matches(payload, normalized_keyword):
                if scanned >= scan_limit:
                    break
                continue
            seen.add(payload["tg"])
            matches.append(payload)
            if len(matches) >= limit or scanned >= scan_limit:
                break
    except Exception as exc:
        LOGGER.warning(f"moderation fallback search failed chat_id={chat_id} keyword={keyword!r}: {exc}")

    return matches


async def get_chat_member_brief(chat_id: int | str, tg: int | str) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=tg)
        return _serialize_member(member, chat_id=chat_id)
    except Exception as exc:
        LOGGER.warning(f"moderation get_chat_member failed chat_id={chat_id} tg={tg}: {exc}")

    try:
        user = await bot.get_users(tg)
        return _serialize_member(user=user, chat_id=chat_id)
    except Exception as exc:
        raise ModerationLookupError(f"未找到 TG {tg} 对应的用户。") from exc


async def resolve_chat_member(
    chat_id: int | str,
    target: str | int | None = None,
    *,
    reply_user: Any = None,
) -> dict[str, Any]:
    chat_id = int(chat_id)

    if reply_user is not None:
        return await get_chat_member_brief(chat_id, int(reply_user.id))

    raw_target = str(target or "").strip()
    if not raw_target:
        raise ModerationLookupError("请回复目标用户，或提供 TGID / @username / 昵称关键词。")

    if raw_target.lstrip("-").isdigit():
        return await get_chat_member_brief(chat_id, int(raw_target))

    matches = await search_chat_members(chat_id, raw_target, limit=10)
    if not matches:
        raise ModerationLookupError(f"未在当前群中找到 {raw_target}。")

    exact_matches = [item for item in matches if _exact_member_match(item, raw_target)]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(matches) == 1:
        return matches[0]
    raise ModerationAmbiguousError(matches[:5])


def get_chat_warning_state(chat_id: int | str, tg: int | str) -> dict[str, Any]:
    return {
        "settings": get_group_moderation_setting(chat_id),
        "warning": get_group_moderation_warning(chat_id, tg),
    }


async def update_warning_config(
    chat_id: int | str,
    *,
    warn_threshold: int,
    warn_action: str,
    mute_minutes: int,
    updated_by: int | None = None,
) -> dict[str, Any]:
    return update_group_moderation_setting(
        chat_id,
        warn_threshold=warn_threshold,
        warn_action=warn_action,
        mute_minutes=mute_minutes,
        updated_by=updated_by,
    )


def warning_map_for_targets(chat_id: int | str, tg_ids: list[int] | set[int] | tuple[int, ...]) -> dict[int, dict[str, Any]]:
    return get_group_warning_map(chat_id, tg_ids)


async def mute_chat_member(chat_id: int | str, tg: int | str, minutes: int) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    normalized_minutes = int(minutes or 0)

    if normalized_minutes <= 0:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_send_polls=True,
            can_invite_users=True,
        )
        try:
            await bot.restrict_chat_member(chat_id=chat_id, user_id=tg, permissions=permissions)
        except Exception as exc:
            raise ModerationServiceError(f"解除禁言失败：{exc}") from exc
        return {
            "chat_id": chat_id,
            "tg": tg,
            "minutes": 0,
            "action": "unmute",
            "message": "已解除禁言。",
        }

    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_send_polls=False,
    )
    until_date = datetime.utcnow() + timedelta(minutes=normalized_minutes)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=tg,
            permissions=permissions,
            until_date=until_date,
        )
    except Exception as exc:
        raise ModerationServiceError(f"禁言失败：{exc}") from exc

    return {
        "chat_id": chat_id,
        "tg": tg,
        "minutes": normalized_minutes,
        "until_date": until_date.isoformat(),
        "action": "mute",
        "message": f"已禁言 {normalized_minutes} 分钟。",
    }


async def kick_chat_member(chat_id: int | str, tg: int | str) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=tg)
        try:
            await bot.unban_chat_member(chat_id=chat_id, user_id=tg, only_if_banned=True)
        except TypeError:
            await bot.unban_chat_member(chat_id=chat_id, user_id=tg)
    except Exception as exc:
        raise ModerationServiceError(f"踢出失败：{exc}") from exc

    return {
        "chat_id": chat_id,
        "tg": tg,
        "action": "kick",
        "message": "已踢出群组。",
    }


async def set_chat_member_title(chat_id: int | str, tg: int | str, title: str) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise ModerationServiceError("头衔不能为空。")

    safe_title = normalize_telegram_member_badge_text(normalized_title)
    if not safe_title:
        raise ModerationServiceError("头衔不能只包含 emoji 或特殊符号。")
    try:
        await _telegram_bot_api_post(
            "setChatAdministratorCustomTitle",
            {"chat_id": chat_id, "user_id": tg, "custom_title": safe_title},
        )
    except Exception as exc:
        raise ModerationServiceError("设置头衔失败，请确认目标已是管理员且 Bot 拥有修改头衔权限。") from exc

    return {
        "chat_id": chat_id,
        "tg": tg,
        "title": safe_title,
        "action": "title",
        "message": f"已设置头衔：{safe_title}",
    }


async def set_chat_member_tag(chat_id: int | str, tg: int | str, tag: str | None) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    normalized_tag = normalize_telegram_member_badge_text(tag)
    try:
        await _telegram_bot_api_post(
            "setChatMemberTag",
            {"chat_id": chat_id, "user_id": tg, "tag": normalized_tag},
        )
    except ModerationServiceError as exc:
        message = str(exc)
        lowered = message.lower()
        if any(keyword in lowered for keyword in ("not enough rights", "administrator", "manage tags", "can_manage_tags")):
            raise ModerationServiceError("设置群成员标签失败，请确认 Bot 已是群管理员并开启管理标签权限（can_manage_tags）。") from exc
        if any(keyword in lowered for keyword in ("user not found", "member not found", "user not participant", "not participant")):
            raise ModerationServiceError("被操作用户不在目标群组里。") from exc
        raise

    return {
        "chat_id": chat_id,
        "tg": tg,
        "tag": normalized_tag,
        "action": "tag",
        "message": "已设置群成员标签。" if normalized_tag else "已清除群成员标签。",
    }


async def pin_chat_message(chat_id: int | str, message_id: int | str, *, disable_notification: bool = True) -> dict[str, Any]:
    chat_id = int(chat_id)
    message_id = int(message_id)
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=disable_notification)
    except Exception as exc:
        raise ModerationServiceError(f"置顶失败：{exc}") from exc

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "action": "pin",
        "message": f"已置顶消息 {message_id}。",
    }


async def unpin_chat_message(chat_id: int | str, message_id: int | str | None = None) -> dict[str, Any]:
    chat_id = int(chat_id)
    try:
        if message_id is None:
            await bot.unpin_chat_message(chat_id=chat_id)
        else:
            await bot.unpin_chat_message(chat_id=chat_id, message_id=int(message_id))
    except Exception as exc:
        raise ModerationServiceError(f"取消置顶失败：{exc}") from exc

    return {
        "chat_id": chat_id,
        "message_id": int(message_id) if message_id is not None else None,
        "action": "unpin",
        "message": "已取消置顶。",
    }


async def warn_chat_member(
    chat_id: int | str,
    tg: int | str,
    *,
    actor_tg: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    chat_id = int(chat_id)
    tg = int(tg)
    settings = get_group_moderation_setting(chat_id)
    warning_result = increment_group_moderation_warning(chat_id, tg, actor_tg=actor_tg, reason=reason)
    warning_item = warning_result["item"]
    previous_count = int(warning_result["previous_count"])
    current_count = int(warning_item["warn_count"])
    threshold = max(int(settings["warn_threshold"]), 1)
    should_trigger = previous_count < threshold <= current_count

    action_result = None
    action_error = None
    if should_trigger:
        try:
            if settings["warn_action"] == "kick":
                action_result = await kick_chat_member(chat_id, tg)
            else:
                action_result = await mute_chat_member(chat_id, tg, int(settings["mute_minutes"]))
            mark_group_warning_action(chat_id, tg, settings["warn_action"])
            warning_item = get_group_moderation_warning(chat_id, tg) or warning_item
        except ModerationServiceError as exc:
            action_error = str(exc)

    return {
        "settings": settings,
        "warning": warning_item,
        "action_triggered": should_trigger,
        "action_result": action_result,
        "action_error": action_error,
    }


def clear_chat_member_warning(chat_id: int | str, tg: int | str) -> dict[str, Any]:
    return clear_group_moderation_warning(chat_id, tg)
