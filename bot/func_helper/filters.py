#!/usr/bin/python3

import asyncio
import os
import time
from typing import Any

import aiohttp
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import BadRequest
from pyrogram.filters import create

from bot import LOGGER, admins, bot_token, chanel, group, owner

_LOGGED_INVALID_GROUP_IDS = set()
_LOGGED_INVALID_CHAT_REFS = set()
_BOT_API_ALLOWED_STATUSES = {"creator", "administrator", "member"}
_PYROGRAM_ALLOWED_STATUSES = {
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.OWNER,
}
_MEMBERSHIP_CACHE: dict[tuple[str, int], tuple[float, bool | None]] = {}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


MEMBERSHIP_CHECK_TIMEOUT = _env_int("PIVKEYU_MEMBERSHIP_CHECK_TIMEOUT", 4, 1)
MEMBERSHIP_CACHE_TTL = _env_int("PIVKEYU_MEMBERSHIP_CACHE_TTL", 300, 1)
MEMBERSHIP_NEGATIVE_CACHE_TTL = _env_int("PIVKEYU_MEMBERSHIP_NEGATIVE_CACHE_TTL", 30, 1)
MEMBERSHIP_ERROR_CACHE_TTL = _env_int("PIVKEYU_MEMBERSHIP_ERROR_CACHE_TTL", 10, 1)


def _iter_valid_group_ids():
    for raw_group_id in group:
        try:
            group_id = int(raw_group_id)
        except (TypeError, ValueError):
            if raw_group_id not in _LOGGED_INVALID_GROUP_IDS:
                LOGGER.error(
                    f"Invalid group id in config.json: {raw_group_id}. "
                    f"Please check the group list."
                )
                _LOGGED_INVALID_GROUP_IDS.add(raw_group_id)
            continue

        if group_id == 0:
            if raw_group_id not in _LOGGED_INVALID_GROUP_IDS:
                LOGGER.error("Invalid group id in config.json: 0. Please check the group list.")
                _LOGGED_INVALID_GROUP_IDS.add(raw_group_id)
            continue

        yield group_id


def _valid_group_ids() -> list[int]:
    return list(_iter_valid_group_ids())


def _is_placeholder_chat_reference(value: Any) -> bool:
    normalized = str(value or "").strip()
    if normalized.startswith("https://t.me/") or normalized.startswith("http://t.me/"):
        normalized = normalized.rsplit("/", 1)[-1]
    normalized = normalized.strip().lstrip("@").lower()
    return not normalized or normalized in {
        "0",
        "none",
        "null",
        "false",
        "your_channel_username",
        "your_main_group_username",
        "replace_with_channel_username",
    } or "replace_with" in normalized


def _normalize_chat_reference(value: Any, *, label: str) -> int | str | None:
    if _is_placeholder_chat_reference(value):
        return None
    text = str(value).strip()
    if text.startswith("https://t.me/") or text.startswith("http://t.me/"):
        text = text.rsplit("/", 1)[-1].strip()
    elif text.startswith("t.me/") or text.startswith("telegram.me/"):
        text = text.rsplit("/", 1)[-1].strip()
    text = text.split("?", 1)[0].strip()
    if not text or text.startswith("+"):
        if value not in _LOGGED_INVALID_CHAT_REFS:
            LOGGER.warning(f"{label}配置无法用于成员验证: {value!r}")
            _LOGGED_INVALID_CHAT_REFS.add(value)
        return None
    try:
        chat_id = int(text)
        return chat_id if chat_id != 0 else None
    except (TypeError, ValueError):
        return text if text.startswith("@") else f"@{text}"


def _configured_channel_reference() -> int | str | None:
    return _normalize_chat_reference(chanel, label="频道")


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status) or "").lower()


def _member_is_active(member: Any) -> bool:
    status = getattr(member, "status", None)
    if status in _PYROGRAM_ALLOWED_STATUSES:
        return True
    status_text = _status_value(status)
    if status_text in _BOT_API_ALLOWED_STATUSES:
        return True
    if status_text == "restricted":
        return bool(getattr(member, "is_member", True))
    return False


def _extract_user(update):
    return getattr(update, "from_user", None) or getattr(update, "sender_chat", None)


def _extract_chat_id(update) -> int | None:
    chat = getattr(update, "chat", None)
    if chat is None:
        message = getattr(update, "message", None)
        chat = getattr(message, "chat", None)
    try:
        return int(getattr(chat, "id", 0) or 0) or None
    except (TypeError, ValueError):
        return None


def _is_privileged_user_id(uid: int) -> bool:
    try:
        normalized_uid = int(uid)
    except (TypeError, ValueError):
        return False
    normalized_admins = set()
    for item in admins:
        try:
            normalized_admins.add(int(item))
        except (TypeError, ValueError):
            continue
    return normalized_uid == int(owner) or normalized_uid in normalized_admins


async def _check_member_via_bot_api(chat_id: int | str, user_id: int):
    url = f"https://api.telegram.org/bot{bot_token}/getChatMember"
    payload = {"chat_id": chat_id, "user_id": user_id}
    timeout = aiohttp.ClientTimeout(total=MEMBERSHIP_CHECK_TIMEOUT)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=payload) as response:
                data = await response.json(content_type=None)
    except Exception as exc:
        LOGGER.warning(f"Bot API getChatMember failed chat={chat_id} user={user_id}: {exc}")
        return None

    if not data.get("ok"):
        description = data.get("description", "unknown error")
        if "user not found" in description.lower() or "participant_id_invalid" in description.lower():
            return False
        if "member not found" in description.lower() or "user not participant" in description.lower():
            return False
        LOGGER.error(f"Bot API getChatMember rejected chat={chat_id} user={user_id}: {description}")
        return None

    result = data.get("result") or {}
    status = str(result.get("status") or "").lower()
    return status in _BOT_API_ALLOWED_STATUSES or (status == "restricted" and bool(result.get("is_member", True)))


async def _check_chat_membership_uncached(client, chat_id: int | str, user_id: int):
    try:
        member = await asyncio.wait_for(
            client.get_chat_member(chat_id=chat_id, user_id=user_id),
            timeout=MEMBERSHIP_CHECK_TIMEOUT,
        )
        return _member_is_active(member)
    except BadRequest as exc:
        if exc.ID in {"USER_NOT_PARTICIPANT", "PARTICIPANT_ID_INVALID", "USER_NOT_FOUND"}:
            return False
        if exc.ID == "CHAT_ADMIN_REQUIRED":
            LOGGER.error(
                f"Bot cannot read members in chat {chat_id}. "
                f"Check whether the bot is in the group/channel and has enough permissions."
            )
            return False
        LOGGER.warning(f"Pyrogram get_chat_member failed chat={chat_id} user={user_id}: {exc}")
    except asyncio.TimeoutError:
        LOGGER.warning(f"Pyrogram get_chat_member timeout chat={chat_id} user={user_id}")
    except (KeyError, ValueError) as exc:
        LOGGER.warning(
            f"Pyrogram peer cache miss for chat={chat_id} user={user_id}, "
            f"falling back to Bot API: {exc}"
        )
    except Exception as exc:
        LOGGER.warning(f"Unexpected get_chat_member failure chat={chat_id} user={user_id}: {exc}")

    return await _check_member_via_bot_api(chat_id, user_id)


async def _check_chat_membership(client, chat_id: int | str, user_id: int):
    key = (str(chat_id), int(user_id))
    now = time.monotonic()
    cached = _MEMBERSHIP_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    result = await _check_chat_membership_uncached(client, chat_id, user_id)
    if result is True:
        ttl = MEMBERSHIP_CACHE_TTL
    elif result is False:
        ttl = MEMBERSHIP_NEGATIVE_CACHE_TTL
    else:
        ttl = MEMBERSHIP_ERROR_CACHE_TTL
    _MEMBERSHIP_CACHE[key] = (time.monotonic() + ttl, result)
    return result


async def _check_group_membership(client, group_id: int, user_id: int):
    return await _check_chat_membership(client, group_id, user_id)


async def check_initial_access(client, update) -> dict[str, Any]:
    user = _extract_user(update)
    try:
        uid = int(getattr(user, "id", 0) or 0)
    except (TypeError, ValueError):
        uid = 0

    valid_group_ids = _valid_group_ids()
    channel_ref = _configured_channel_reference()
    result = {
        "ok": False,
        "user_id": uid,
        "group_required": bool(valid_group_ids),
        "channel_required": channel_ref is not None,
        "group_ok": False,
        "channel_ok": channel_ref is None,
        "missing": [],
    }

    if uid <= 0:
        result["missing"] = ["用户身份"]
        return result

    if _is_privileged_user_id(uid):
        result.update({"ok": True, "group_ok": True, "channel_ok": True, "missing": []})
        return result

    if not valid_group_ids:
        LOGGER.error("No valid group ids were found in config.json.")
    elif uid in valid_group_ids or _extract_chat_id(update) in valid_group_ids:
        result["group_ok"] = True
    else:
        checks = [
            _check_group_membership(client, group_id, uid)
            for group_id in valid_group_ids
        ]
        group_results = await asyncio.gather(*checks, return_exceptions=True)
        result["group_ok"] = any(item is True for item in group_results)

    if channel_ref is not None:
        result["channel_ok"] = bool(await _check_chat_membership(client, channel_ref, uid))

    missing = []
    if not result["group_ok"]:
        missing.append("群组")
    if not result["channel_ok"]:
        missing.append("频道")
    result["missing"] = missing
    result["ok"] = not missing
    return result


def initial_access_denied_text(access: dict[str, Any] | None = None) -> str:
    missing = list((access or {}).get("missing") or [])
    if not missing:
        missing = ["群组", "频道"]
    if "群组" in missing and "频道" in missing:
        target = "加入授权群组并关注频道"
    elif "群组" in missing:
        target = "加入授权群组"
    elif "频道" in missing:
        target = "关注频道"
    else:
        target = "完成使用前验证"
    return f"🚫 请先{target}，再回到这里发送 /start 或点击面板按钮继续。"


async def admins_on_filter(filt, client, update) -> bool:
    user = _extract_user(update)
    if user is None:
        return False
    uid = user.id
    return bool(_is_privileged_user_id(uid) or uid in _valid_group_ids())


async def admins_filter(update):
    user = _extract_user(update)
    if user is None:
        return False
    uid = user.id
    return bool(_is_privileged_user_id(uid))


async def user_in_group_filter(client, update):
    return bool((await check_initial_access(client, update)).get("ok"))


async def user_in_group_on_filter(filt, client, update):
    return bool((await check_initial_access(client, update)).get("ok"))


admins_on_filter = create(admins_on_filter)
admins_filter = create(admins_filter)
user_in_group_f = create(user_in_group_filter)
user_in_group_on_filter = create(user_in_group_on_filter)
