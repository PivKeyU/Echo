from __future__ import annotations

import asyncio
import os
import shutil
import threading
import time
from datetime import datetime
from time import monotonic
from sys import argv, executable
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from starlette.background import BackgroundTask

from bot import LOGGER, bot, chanel, config, save_config
from bot.func_helper.moderation import (
    ModerationServiceError,
    clear_chat_member_warning,
    get_chat_member_brief,
    kick_chat_member,
    list_managed_chats,
    mute_chat_member,
    pin_chat_message,
    search_chat_members,
    set_chat_member_title,
    unpin_chat_message,
    update_warning_config,
    warn_chat_member,
    warning_map_for_targets,
)
from bot.func_helper.utils import cr_link_one, rn_link_one
from bot.plugins import PluginImportError, import_plugin_archive, list_plugins, sync_plugin_runtime_state
from bot.scheduler.auto_update import serialize_auto_update_state, update_auto_update_settings
from bot.sql_helper import Session
from bot.sql_helper.sql_bot_access import (
    BotAccessBlock,
    find_bot_access_block,
    find_existing_bot_access_block,
    invalidate_bot_access_cache,
    normalize_bot_access_username,
    serialize_bot_access_block,
)
from bot.sql_helper.sql_code import Code, CodeRedeem
from bot.sql_helper.sql_emby import Emby, sql_invalidate_emby_namespace
from bot.sql_helper.sql_emby2 import Emby2
from bot.sql_helper.sql_invite import (
    INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
    INVITE_CREDIT_TYPE_GROUP,
    approve_account_open_invite_record,
    create_account_open_invite_record,
    decline_account_open_invite_record,
    get_invite_record,
    get_invite_settings,
    invite_credit_summary,
    invite_qualification_status,
    list_invite_credits,
    list_invite_records,
    normalize_invite_credit_type,
    revoke_account_open_invite_record,
    revoke_invite_credit,
    revoke_invite_record,
    set_invite_qualification,
    set_invite_settings,
    update_invite_credit,
)
from bot.sql_helper.sql_moderation import get_group_moderation_setting, list_group_moderation_warnings
from bot.web.migration_bundle import MigrationBundleError, create_migration_bundle, restore_migration_bundle
from bot.web.presenters import get_level_meta, serialize_emby_user

router = APIRouter()

_TELEGRAM_IDENTITY_CACHE_TTL = 300.0
_telegram_identity_cache: dict[int, tuple[float, dict[str, str]]] = {}


def _env_upload_limit(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, str(default)) or default), 1024 * 1024)
    except (TypeError, ValueError):
        return default


_PLUGIN_ARCHIVE_MAX_BYTES = _env_upload_limit("PIVKEYU_PLUGIN_MAX_ARCHIVE_BYTES", 128 * 1024 * 1024)


async def _read_upload_limited(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"上传文件不能超过 {limit // (1024 * 1024)}MB")
        chunks.append(chunk)
    return b"".join(chunks)


class AdminUserPatch(BaseModel):
    model_config = {"extra": "forbid"}

    embyid: str | None = None
    name: str | None = None
    # Credentials are intentionally not editable through the general user
    # patch endpoint.  Password reset/change flows use Emby-specific actions.
    lv: str | None = Field(default=None, pattern="^[abcd]$")
    cr: datetime | None = None
    ex: datetime | None = None
    us: int | None = None
    iv: int | None = None
    ch: datetime | None = None


class AdminUserBatchPayload(BaseModel):
    action: str = Field(default="set_level")
    scope: str = Field(default="all")
    source_level: str | None = Field(default=None, pattern="^[abcd]$")
    target_level: str | None = Field(default=None, pattern="^[abcd]$")


class AdminPluginPatch(BaseModel):
    enabled: bool | None = None
    bottom_nav_visible: bool | None = None


class AdminAutoUpdatePatch(BaseModel):
    status: bool | None = None
    git_repo: str | None = None
    docker_image: str | None = None
    container_name: str | None = None
    compose_service: str | None = None
    check_interval_minutes: int | None = Field(default=None, ge=5, le=1440)


class AdminCodeCreatePayload(BaseModel):
    days: int = Field(..., gt=0, le=3650)
    count: int = Field(..., gt=0, le=500)
    method: str = Field(default="code")
    type: str = Field(default="F")
    usage_limit: int = Field(default=1, gt=0, le=100)
    suffix_mode: str = Field(default="random")
    suffix_text: str | None = None


class AdminCodeDeletePayload(BaseModel):
    codes: list[str] = Field(default_factory=list)


class AdminBotAccessBlockCreatePayload(BaseModel):
    tg: int | None = Field(default=None, ge=1)
    username: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)


class AdminInviteSettingsPatch(BaseModel):
    enabled: bool | None = None
    target_chat_id: int | None = None
    expire_hours: int | None = Field(default=None, ge=1, le=168)
    strict_target: bool | None = None
    group_verification_enabled: bool | None = None
    channel_verification_enabled: bool | None = None
    account_open_days: int | None = Field(default=None, ge=1, le=3650)


class AdminInviteGrantPayload(BaseModel):
    owner_tg: int = Field(..., ge=1)
    count: int = Field(default=1, ge=1, le=500)
    credit_type: str = Field(default=INVITE_CREDIT_TYPE_GROUP)
    invite_days: int | None = Field(default=None, ge=1, le=3650)
    note: str | None = Field(default=None, max_length=255)


class AdminInviteCreditDeletePayload(BaseModel):
    credit_ids: list[int] = Field(default_factory=list)
    reason: str | None = Field(default=None, max_length=255)


class AdminInviteCreditPatchPayload(BaseModel):
    owner_tg: int | None = Field(default=None, ge=1)
    invite_days: int | None = Field(default=None, ge=1, le=3650)
    note: str | None = Field(default=None, max_length=255)


class AdminInviteQualificationPatchPayload(BaseModel):
    owner_tg: int = Field(..., ge=1)
    credit_type: str = Field(default=INVITE_CREDIT_TYPE_GROUP)
    enabled: bool = True
    reason: str | None = Field(default=None, max_length=255)


class AdminAccountOpenInviteCreatePayload(BaseModel):
    inviter_tg: int = Field(..., ge=1)
    invitee_tg: int = Field(..., ge=1)
    note: str | None = Field(default=None, max_length=255)


class AdminAccountOpenInviteReviewPayload(BaseModel):
    action: str = Field(default="approve")
    invite_days: int | None = Field(default=None, ge=1, le=3650)
    note: str | None = Field(default=None, max_length=255)


class AdminModerationSettingsPatch(BaseModel):
    warn_threshold: int = Field(..., ge=1, le=100)
    warn_action: str = Field(default="mute")
    mute_minutes: int = Field(default=60, ge=1, le=10080)


class AdminModerationMutePayload(BaseModel):
    chat_id: int
    tg: int
    minutes: int = Field(..., ge=0, le=10080)


class AdminModerationKickPayload(BaseModel):
    chat_id: int
    tg: int


class AdminModerationTitlePayload(BaseModel):
    chat_id: int
    tg: int
    title: str = Field(..., min_length=1, max_length=16)


class AdminModerationWarnPayload(BaseModel):
    chat_id: int
    tg: int
    reason: str | None = Field(default=None, max_length=255)


class AdminModerationPinPayload(BaseModel):
    chat_id: int
    message_id: int = Field(..., gt=0)
    disable_notification: bool = True


class AdminModerationUnpinPayload(BaseModel):
    chat_id: int
    message_id: int | None = Field(default=None, gt=0)


def _telegram_identity_payload(user: Any) -> dict[str, str]:
    first_name = str(getattr(user, "first_name", "") or "").strip()
    last_name = str(getattr(user, "last_name", "") or "").strip()
    username = str(getattr(user, "username", "") or "").strip().lstrip("@")
    display_name = " ".join(part for part in [first_name, last_name] if part).strip()
    payload: dict[str, str] = {}
    if display_name:
        payload["display_name"] = display_name
    if username:
        payload["username"] = username
    return payload


def _telegram_display_label(tg: int, identity: dict[str, str] | None) -> str:
    identity = identity or {}
    if identity.get("display_name"):
        return identity["display_name"]
    if identity.get("username"):
        return f"@{identity['username']}"
    return f"TG {tg}"


async def _telegram_actor_label(tg: int | None) -> str:
    if tg is None:
        return "后台"
    try:
        identity = (await _fetch_telegram_identity_map([int(tg)])).get(int(tg)) or {}
    except Exception:
        identity = {}
    return _telegram_display_label(int(tg), identity)


def _serialize_admin_user(user: Emby, identity: dict[str, str] | None = None) -> dict[str, Any]:
    payload = serialize_emby_user(user)
    identity = identity or {}
    matched_block = find_bot_access_block(tg=int(user.tg), username=identity.get("username"))
    payload["tg_display_name"] = identity.get("display_name")
    payload["tg_username"] = identity.get("username")
    payload["tg_display_label"] = _telegram_display_label(int(user.tg), identity)
    payload["bot_access_blocked"] = matched_block is not None
    payload["bot_access_block"] = matched_block
    return payload


def _serialize_moderation_member(
    member: dict[str, Any],
    warning_map: dict[int, dict[str, Any]] | None = None,
    emby_map: dict[int, Emby] | None = None,
) -> dict[str, Any]:
    payload = dict(member or {})
    tg = int(payload.get("tg") or 0)
    display_name = str(payload.get("display_name") or "").strip()
    username = str(payload.get("username") or "").strip().lstrip("@")
    if display_name:
        payload["display_label"] = display_name
    elif username:
        payload["display_label"] = f"@{username}"
    else:
        payload["display_label"] = f"TG {tg}"
    warning = (warning_map or {}).get(tg)
    emby_user = (emby_map or {}).get(tg)
    level_meta = get_level_meta(getattr(emby_user, "lv", None)) if emby_user is not None else None
    payload["warning"] = warning
    payload["warn_count"] = int((warning or {}).get("warn_count") or 0)
    payload["emby_name"] = getattr(emby_user, "name", None)
    payload["embyid"] = getattr(emby_user, "embyid", None)
    payload["lv"] = getattr(emby_user, "lv", None)
    payload["lv_text"] = level_meta["text"] if level_meta else None
    payload["lv_tone"] = level_meta["tone"] if level_meta else None
    return payload


def _serialize_moderation_warning_item(
    warning: dict[str, Any],
    identity: dict[str, str] | None = None,
    emby_user: Emby | None = None,
) -> dict[str, Any]:
    payload = dict(warning or {})
    tg = int(payload.get("tg") or 0)
    identity = identity or {}
    level_meta = get_level_meta(getattr(emby_user, "lv", None)) if emby_user is not None else None
    payload["tg_display_name"] = identity.get("display_name")
    payload["tg_username"] = identity.get("username")
    payload["tg_display_label"] = _telegram_display_label(tg, identity)
    payload["emby_name"] = getattr(emby_user, "name", None)
    payload["embyid"] = getattr(emby_user, "embyid", None)
    payload["lv"] = getattr(emby_user, "lv", None)
    payload["lv_text"] = level_meta["text"] if level_meta else None
    payload["lv_tone"] = level_meta["tone"] if level_meta else None
    return payload


def _cached_telegram_identity(tg: int) -> dict[str, str] | None:
    cached = _telegram_identity_cache.get(int(tg))
    if not cached:
        return None
    cached_at, payload = cached
    if monotonic() - cached_at > _TELEGRAM_IDENTITY_CACHE_TTL:
        _telegram_identity_cache.pop(int(tg), None)
        return None
    return dict(payload)


def _store_telegram_identity(tg: int, identity: dict[str, str]) -> None:
    _telegram_identity_cache[int(tg)] = (monotonic(), dict(identity))


def _chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


async def _fetch_telegram_identity_map(tgs: list[int]) -> dict[int, dict[str, str]]:
    identities: dict[int, dict[str, str]] = {}
    missing: list[int] = []

    for tg in {int(value) for value in tgs if value is not None}:
        cached = _cached_telegram_identity(tg)
        if cached is None:
            missing.append(tg)
        else:
            identities[tg] = cached

    for chunk in _chunked(missing, 100):
        try:
            response = await bot.get_users(chunk if len(chunk) > 1 else chunk[0])
            users = response if isinstance(response, list) else [response]
            found: set[int] = set()
            for user in users:
                tg = int(user.id)
                identity = _telegram_identity_payload(user)
                _store_telegram_identity(tg, identity)
                identities[tg] = identity
                found.add(tg)
            for tg in chunk:
                if tg not in found:
                    _store_telegram_identity(tg, {})
                    identities[tg] = {}
        except Exception as exc:
            LOGGER.warning(f"admin telegram batch lookup failed: {exc}")
            for tg in chunk:
                try:
                    user = await bot.get_users(int(tg))
                    identity = _telegram_identity_payload(user)
                except Exception as inner_exc:
                    LOGGER.warning(f"admin telegram lookup failed for {tg}: {inner_exc}")
                    identity = {}
                _store_telegram_identity(tg, identity)
                identities[tg] = identity

    return identities


def _telegram_identity_matches(identity: dict[str, str] | None, keyword: str) -> bool:
    if not keyword:
        return False
    identity = identity or {}
    normalized = keyword.strip().lower()
    username = identity.get("username", "").lower()
    display_name = identity.get("display_name", "").lower()
    return (
        normalized in display_name
        or normalized in username
        or normalized.lstrip("@") in username
    )


def _apply_admin_user_keyword_filter(query, keyword: str):
    normalized = str(keyword or "").strip()
    if not normalized:
        return query
    conditions = [
        Emby.name.ilike(f"%{normalized}%"),
        Emby.embyid.ilike(f"%{normalized}%"),
    ]
    if normalized.isdigit():
        conditions.append(Emby.tg == int(normalized))
    return query.filter(or_(*conditions))


async def _search_admin_users_by_telegram_identity(keyword: str, page: int, page_size: int) -> tuple[list[Emby], int]:
    with Session() as session:
        all_users = session.query(Emby).order_by(Emby.tg.desc()).all()
    identity_map = await _fetch_telegram_identity_map([user.tg for user in all_users])
    matched_users = [user for user in all_users if _telegram_identity_matches(identity_map.get(int(user.tg)), keyword)]
    start = max(page - 1, 0) * page_size
    return matched_users[start:start + page_size], len(matched_users)


def _resolve_admin_actor_id(request: Request) -> int | None:
    admin_user = getattr(request.state, "admin_user", None) or {}
    admin_id = admin_user.get("id")
    try:
        return int(admin_id) if admin_id is not None else None
    except (TypeError, ValueError):
        return None


async def _safe_get_moderation_target(chat_id: int, tg: int) -> dict[str, Any]:
    try:
        return await get_chat_member_brief(chat_id, tg)
    except Exception as exc:
        LOGGER.warning(f"admin moderation get target failed chat={chat_id} tg={tg}: {exc}")
        return {
            "chat_id": int(chat_id),
            "tg": int(tg),
            "display_label": f"TG {tg}",
            "display_name": None,
            "username": None,
            "status": None,
            "status_text": "未知状态",
            "is_admin": False,
            "is_bot": False,
            "is_member": False,
        }


def _restart_current_process() -> None:
    service_name = os.getenv("PIVKEYU_RESTART_SERVICE", "").strip()
    if service_name and os.path.exists("/bin/systemctl"):
        os.execl("/bin/systemctl", "systemctl", "restart", service_name)
    os.execl(executable, executable, *argv)


def _restart_after_delay(seconds: float = 1.0) -> None:
    time.sleep(max(float(seconds), 0.1))
    _restart_current_process()


def _schedule_restart_after_delay(seconds: float = 4.0) -> None:
    # 让导入响应先完整返回，避免移动端/WebView把正常导入误判成网络失败。
    worker = threading.Thread(target=_restart_after_delay, args=(seconds,), daemon=True)
    worker.start()


def _serialize_code_actor(
    tg: int | None,
    identity_map: dict[int, dict[str, str]],
    emby_map: dict[int, Emby],
) -> dict[str, Any] | None:
    if tg is None:
        return None

    tg = int(tg)
    identity = identity_map.get(tg) or {}
    emby_user = emby_map.get(tg)
    level_meta = get_level_meta(getattr(emby_user, "lv", None)) if emby_user is not None else None
    return {
        "tg": tg,
        "tg_display_name": identity.get("display_name"),
        "tg_username": identity.get("username"),
        "tg_display_label": _telegram_display_label(tg, identity),
        "emby_name": getattr(emby_user, "name", None),
        "embyid": getattr(emby_user, "embyid", None),
        "lv": getattr(emby_user, "lv", None),
        "lv_text": level_meta["text"] if level_meta else None,
        "lv_tone": level_meta["tone"] if level_meta else None,
        "iv": getattr(emby_user, "iv", None),
        "us": getattr(emby_user, "us", None),
        "ex": emby_user.ex.isoformat() if emby_user and emby_user.ex else None,
    }


def _code_kind(code_value: str) -> str:
    if "Renew_" in str(code_value or ""):
        return "renew"
    if "Register_" in str(code_value or ""):
        return "register"
    return "unknown"


def _code_kind_text(kind: str) -> str:
    return {
        "register": "注册码",
        "renew": "续期码",
    }.get(kind, "未知类型")


def _normalize_bot_access_payload(payload: AdminBotAccessBlockCreatePayload) -> dict[str, Any]:
    tg = int(payload.tg) if payload.tg is not None else None
    username = normalize_bot_access_username(payload.username)
    note = str(payload.note or "").strip() or None

    if tg is None and username is None:
        raise HTTPException(status_code=400, detail="TGID 和 TG 用户名至少填一项啦，本女仆没法猜呢...")

    return {
        "tg": tg,
        "username": username,
        "note": note,
    }


def _serialize_code_record(
    row: Code,
    redeem_rows: list[CodeRedeem],
    identity_map: dict[int, dict[str, str]],
    emby_map: dict[int, Emby],
) -> dict[str, Any]:
    use_limit = max(int(row.use_limit or 1), 1)
    use_count = max(int(row.use_count or 0), 0)
    remaining = max(use_limit - use_count, 0)
    kind = _code_kind(row.code)

    redeemers = [
        {
            "code": redeem.code,
            "use_index": redeem.use_index,
            "redeemed_at": redeem.redeemed_at.isoformat() if redeem.redeemed_at else None,
            "actor": _serialize_code_actor(redeem.user_id, identity_map, emby_map),
        }
        for redeem in redeem_rows
    ]

    return {
        "code": row.code,
        "kind": kind,
        "kind_text": _code_kind_text(kind),
        "days": int(row.us or 0),
        "use_limit": use_limit,
        "use_count": use_count,
        "remaining_uses": remaining,
        "is_exhausted": remaining <= 0,
        "status": "unused" if use_count == 0 else "used",
        "status_text": "未使用" if use_count == 0 else "已使用",
        "usedtime": row.usedtime.isoformat() if row.usedtime else None,
        "latest_redeemer": _serialize_code_actor(row.used, identity_map, emby_map),
        "creator": _serialize_code_actor(row.tg, identity_map, emby_map),
        "redeemers": redeemers,
        "redeemer_count": len(redeemers),
    }


def _serialize_invite_credit_admin(
    item: dict[str, Any],
    identity_map: dict[int, dict[str, str]],
    emby_map: dict[int, Emby],
) -> dict[str, Any]:
    payload = dict(item or {})
    payload["owner"] = _serialize_code_actor(payload.get("owner_tg"), identity_map, emby_map)
    payload["granted_by"] = _serialize_code_actor(payload.get("granted_by_tg"), identity_map, emby_map)
    payload["revoked_by"] = _serialize_code_actor(payload.get("revoked_by_tg"), identity_map, emby_map)
    return payload


def _serialize_invite_record_admin(
    item: dict[str, Any],
    identity_map: dict[int, dict[str, str]],
    emby_map: dict[int, Emby],
) -> dict[str, Any]:
    payload = dict(item or {})
    payload["inviter"] = _serialize_code_actor(payload.get("inviter_tg"), identity_map, emby_map)
    payload["invitee"] = _serialize_code_actor(payload.get("invitee_tg"), identity_map, emby_map)
    payload["created_by"] = _serialize_code_actor(payload.get("created_by_tg"), identity_map, emby_map)
    payload["last_requester"] = _serialize_code_actor(payload.get("last_request_tg"), identity_map, emby_map)
    payload["reviewer"] = _serialize_code_actor(payload.get("reviewed_by_tg"), identity_map, emby_map)
    return payload


def _serialize_invite_qualification_admin(
    owner_tg: int,
    identity_map: dict[int, dict[str, str]],
    emby_map: dict[int, Emby],
) -> dict[str, Any]:
    payload = invite_qualification_status(owner_tg)
    payload["owner"] = _serialize_code_actor(owner_tg, identity_map, emby_map)
    return payload


def _actor_search_text(tg: int | None, identity_map: dict[int, dict[str, str]], emby_map: dict[int, Emby]) -> str:
    if tg is None:
        return ""
    tg = int(tg)
    identity = identity_map.get(tg) or {}
    emby_user = emby_map.get(tg)
    return " ".join(
        str(part or "")
        for part in [
            tg,
            identity.get("display_name"),
            identity.get("username"),
            getattr(emby_user, "name", None),
            getattr(emby_user, "embyid", None),
        ]
    ).lower()


def _invite_record_matches_keyword(
    item: dict[str, Any],
    keyword: str,
    identity_map: dict[int, dict[str, str]],
    emby_map: dict[int, Emby],
) -> bool:
    normalized = str(keyword or "").strip().lower().lstrip("@")
    if not normalized:
        return True
    for key in ("inviter_tg", "invitee_tg", "created_by_tg", "last_request_tg", "reviewed_by_tg"):
        if normalized in _actor_search_text(item.get(key), identity_map, emby_map):
            return True
    return False


def _paginate_invite_records(items: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    safe_page_size = min(max(int(page_size or 20), 1), 20)
    total = len(items)
    total_pages = max((total + safe_page_size - 1) // safe_page_size, 1)
    safe_page = min(max(int(page or 1), 1), total_pages)
    start = (safe_page - 1) * safe_page_size
    return items[start:start + safe_page_size], {
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": safe_page > 1,
        "has_next": safe_page < total_pages,
    }


async def _invite_admin_bundle(
    *,
    search_query: str = "",
    account_page: int = 1,
    group_page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    settings = get_invite_settings()
    account_credits = list_invite_credits(limit=200, credit_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN)
    group_credits = list_invite_credits(limit=200, credit_type=INVITE_CREDIT_TYPE_GROUP)
    account_records = list_invite_records(limit=500, credit_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN)
    group_records = list_invite_records(limit=500, credit_type=INVITE_CREDIT_TYPE_GROUP)
    tg_ids: set[int] = set()

    for item in [*account_credits, *group_credits]:
        for key in ("owner_tg", "granted_by_tg", "revoked_by_tg"):
            if item.get(key) is not None:
                tg_ids.add(int(item[key]))
    for item in [*account_records, *group_records]:
        for key in ("inviter_tg", "invitee_tg", "created_by_tg", "last_request_tg", "reviewed_by_tg"):
            if item.get(key) is not None:
                tg_ids.add(int(item[key]))
    if str(search_query or "").strip().isdigit():
        tg_ids.add(int(str(search_query).strip()))

    with Session() as session:
        emby_rows = session.query(Emby).filter(Emby.tg.in_(tg_ids)).all() if tg_ids else []
    emby_map = {int(row.tg): row for row in emby_rows}
    identity_map = await _fetch_telegram_identity_map(list(tg_ids))

    account_filtered = [
        item for item in account_records if _invite_record_matches_keyword(item, search_query, identity_map, emby_map)
    ]
    group_filtered = [
        item for item in group_records if _invite_record_matches_keyword(item, search_query, identity_map, emby_map)
    ]
    account_page_records, account_pagination = _paginate_invite_records(account_filtered, account_page, page_size)
    group_page_records, group_pagination = _paginate_invite_records(group_filtered, group_page, page_size)

    account_open = {
        "summary": invite_credit_summary(credit_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN),
        "credits": [_serialize_invite_credit_admin(item, identity_map, emby_map) for item in account_credits],
        "records": [_serialize_invite_record_admin(item, identity_map, emby_map) for item in account_page_records],
        "records_pagination": account_pagination,
        "searched_qualification": (
            _serialize_invite_qualification_admin(int(search_query), identity_map, emby_map)
            if str(search_query or "").strip().isdigit()
            else None
        ),
    }
    group_join = {
        "summary": invite_credit_summary(credit_type=INVITE_CREDIT_TYPE_GROUP),
        "credits": [_serialize_invite_credit_admin(item, identity_map, emby_map) for item in group_credits],
        "records": [_serialize_invite_record_admin(item, identity_map, emby_map) for item in group_page_records],
        "records_pagination": group_pagination,
        "searched_qualification": (
            _serialize_invite_qualification_admin(int(search_query), identity_map, emby_map)
            if str(search_query or "").strip().isdigit()
            else None
        ),
    }

    return {
        "settings": settings,
        "search": {
            "query": search_query,
            "page_size": min(max(int(page_size or 20), 1), 20),
        },
        "account_open": account_open,
        "group_join": group_join,
        "summary": group_join["summary"],
        "credits": group_join["credits"],
        "records": group_join["records"],
    }


async def _safe_revoke_invite_link(chat_id: int, invite_link: str) -> None:
    if not chat_id or not invite_link:
        return
    try:
        await bot.revoke_chat_invite_link(chat_id=int(chat_id), invite_link=invite_link)
    except Exception as exc:
        LOGGER.warning(f"admin revoke invite link failed chat={chat_id}: {exc}")


async def _safe_send_account_open_review_notice(record: dict[str, Any] | None, action: str) -> None:
    if not record:
        return
    invitee_tg = record.get("invitee_tg")
    if not invitee_tg:
        return
    action_text = {
        "approve": f"已审核通过，获得 {int(record.get('invite_days') or 0)} 天注册资格。",
        "decline": "已被拒绝。",
        "reject": "已被拒绝。",
        "revoke": "已被撤销。",
    }.get(action, "已处理。")
    inviter_label, invitee_label, reviewer_label = await asyncio.gather(
        _telegram_actor_label(record.get("inviter_tg")),
        _telegram_actor_label(record.get("invitee_tg")),
        _telegram_actor_label(record.get("reviewed_by_tg")),
    )
    text = (
        f"你的 Emby 开通申请{action_text}\n\n"
        f"申请人：{inviter_label}\n"
        f"被申请人：{invitee_label}\n"
        f"审核人：{reviewer_label}"
    )
    try:
        await bot.send_message(chat_id=int(invitee_tg), text=text)
    except Exception as exc:
        LOGGER.warning(f"admin account-open review notice failed tg={invitee_tg}: {exc}")


def _normalize_invite_chat_reference(raw_target: Any) -> int | str | None:
    if raw_target is None:
        return None
    text = str(raw_target).strip()
    if text.startswith("https://t.me/") or text.startswith("http://t.me/"):
        text = text.rsplit("/", 1)[-1].strip()
    normalized = text.lstrip("@").lower()
    if (
        not text
        or normalized in {"0", "none", "null", "your_channel_username", "your_main_group_username"}
        or "replace_with" in normalized
    ):
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return text if text.startswith("@") else f"@{text}"


def _telegram_member_is_active(member) -> bool:
    status = str(getattr(getattr(member, "status", None), "value", getattr(member, "status", "")) or "").lower()
    if status in {"creator", "owner", "administrator", "member"}:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", True))
    return False


async def _ensure_target_user_in_invite_group(invitee_tg: int) -> None:
    settings = get_invite_settings()
    verification_checks: list[tuple[str, int | str | None]] = []
    if settings.get("group_verification_enabled", settings.get("strict_target", True)):
        verification_checks.append(("群组", settings.get("target_chat_id")))
    if settings.get("channel_verification_enabled"):
        verification_checks.append(("频道", chanel))

    for label, target_chat_id in verification_checks:
        normalized_chat_id = _normalize_invite_chat_reference(target_chat_id)
        if normalized_chat_id is None:
            raise HTTPException(status_code=400, detail=f"主人还没配置{label}地址呢，不能开启{label}验证哦")
        try:
            member = await bot.get_chat_member(chat_id=normalized_chat_id, user_id=int(invitee_tg))
        except Exception as exc:
            LOGGER.warning(
                f"admin check account-open target {label.lower()} member failed chat={normalized_chat_id} tg={invitee_tg}: {exc}"
            )
            raise HTTPException(status_code=400, detail=f"被申请人不在目标{label}里呢，不能通过开通申请啦~") from exc
        if not _telegram_member_is_active(member):
            raise HTTPException(status_code=400, detail=f"被申请人不在目标{label}里呢，不能通过开通申请啦~")


def _normalize_code_create_payload(payload: AdminCodeCreatePayload) -> dict[str, Any]:
    method = str(payload.method or "").strip().lower()
    code_type = str(payload.type or "").strip().upper()
    suffix_mode = str(payload.suffix_mode or "").strip().lower()
    suffix_text = payload.suffix_text.strip() if payload.suffix_text else None

    if method not in {"code", "link"}:
        raise HTTPException(status_code=400, detail="模式只能是 code 或 link 啦~")
    if code_type not in {"F", "T"}:
        raise HTTPException(status_code=400, detail="类型只能是 F 或 T 啦~")
    if suffix_mode not in {"random", "fixed"}:
        raise HTTPException(status_code=400, detail="后缀模式只能是 random 或 fixed 啦~")
    if suffix_mode == "fixed" and not suffix_text:
        raise HTTPException(status_code=400, detail="固定后缀模式必须提供后缀文本啦~")

    return {
        "days": int(payload.days),
        "count": int(payload.count),
        "method": method,
        "type": code_type,
        "usage_limit": int(payload.usage_limit),
        "suffix_mode": suffix_mode,
        "suffix_text": suffix_text,
    }


def _iter_generated_output_lines(raw_output: Any) -> list[str]:
    if raw_output is None:
        return []
    if isinstance(raw_output, (list, tuple, set)):
        lines: list[str] = []
        for item in raw_output:
            lines.extend(_iter_generated_output_lines(item))
        return lines
    return str(raw_output).splitlines()


def _parse_generated_items(raw_output: Any, method: str) -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    for line in _iter_generated_output_lines(raw_output):
        value = line.strip()
        if not value:
            continue

        if method == "link":
            code = value.split("start=", 1)[1] if "start=" in value else value
            items.append({"code": code, "display": value, "link": value})
        else:
            code = value.strip("`")
            items.append({"code": code, "display": code, "link": None})
    return items


_USER_BATCH_ACTIONS = {"set_level", "ban", "delete"}
_USER_BATCH_SCOPES = {"all", "level", "exclude_whitelist", "whitelist"}


def _level_label(level: str | None) -> str:
    return get_level_meta(level).get("text") or f"{level or '未知'} 级"


def _normalize_user_batch_payload(payload: AdminUserBatchPayload) -> dict[str, str | None]:
    action = str(payload.action or "").strip().lower()
    scope = str(payload.scope or "").strip().lower()
    source_level = (payload.source_level or "").strip().lower() or None
    target_level = (payload.target_level or "").strip().lower() or None

    if action not in _USER_BATCH_ACTIONS:
        raise HTTPException(status_code=400, detail="批量动作只能是删除、封禁或设置等级。")
    if scope not in _USER_BATCH_SCOPES:
        raise HTTPException(status_code=400, detail="批量范围不正确。")
    if scope == "level" and not source_level:
        raise HTTPException(status_code=400, detail="按等级筛选时必须选择来源等级。")

    if action == "set_level":
        if target_level is None:
            raise HTTPException(status_code=400, detail="设置等级时必须选择目标等级。")
    elif action == "ban":
        target_level = "c"
    elif action == "delete":
        target_level = "d"

    return {
        "action": action,
        "scope": scope,
        "source_level": source_level,
        "target_level": target_level,
    }


def _apply_user_batch_scope(query, scope: str, source_level: str | None):
    if scope == "level":
        return query.filter(Emby.lv == source_level)
    if scope == "exclude_whitelist":
        return query.filter(or_(Emby.lv.is_(None), Emby.lv != "a"))
    if scope == "whitelist":
        return query.filter(Emby.lv == "a")
    return query


def _user_batch_scope_text(scope: str, source_level: str | None) -> str:
    if scope == "level":
        return f"所有{_level_label(source_level)}"
    if scope == "exclude_whitelist":
        return "除白名单以外的所有账号"
    if scope == "whitelist":
        return "所有白名单账号"
    return "所有账号"


def _user_batch_action_text(action: str, target_level: str | None) -> str:
    if action == "delete":
        return "删除资格"
    if action == "ban":
        return "封禁账号"
    return f"设置为{_level_label(target_level)}"


def _user_batch_preview_from_rows(
    rows: list[Emby],
    action: str,
    scope: str,
    source_level: str | None,
    target_level: str | None,
    identity_map: dict[int, dict[str, str]] | None = None,
) -> dict[str, Any]:
    level_counts = {code: 0 for code in ("a", "b", "c", "d")}
    active_count = 0
    sample_rows: list[Emby] = []
    for row in rows:
        level = (row.lv or "d").lower()
        level_counts[level] = level_counts.get(level, 0) + 1
        if row.embyid:
            active_count += 1
        if len(sample_rows) < 8:
            sample_rows.append(row)

    return {
        "action": action,
        "action_text": _user_batch_action_text(action, target_level),
        "scope": scope,
        "scope_text": _user_batch_scope_text(scope, source_level),
        "source_level": source_level,
        "source_level_text": _level_label(source_level) if source_level else None,
        "target_level": target_level,
        "target_level_text": _level_label(target_level) if target_level else None,
        "affected_count": len(rows),
        "active_account_count": active_count,
        "level_counts": level_counts,
        "samples": [
            _serialize_admin_user(row, identity_map.get(int(row.tg))) if identity_map is not None else serialize_emby_user(row)
            for row in sample_rows
        ],
    }


def _load_user_batch_rows(session, normalized: dict[str, str | None]) -> list[Emby]:
    query = session.query(Emby)
    scoped = _apply_user_batch_scope(query, normalized["scope"], normalized["source_level"])
    return scoped.order_by(Emby.tg.desc()).all()


async def _sync_user_batch_emby_policy(rows: list[Emby], disable: bool) -> dict[str, int]:
    emby_ids = [str(row.embyid) for row in rows if row.embyid]
    if not emby_ids:
        return {"success_count": 0, "fail_count": 0, "total": 0}

    from bot.func_helper.emby import emby as emby_service

    semaphore = asyncio.Semaphore(16)

    async def _change_one(emby_id: str) -> bool:
        async with semaphore:
            try:
                return bool(await emby_service.emby_change_policy(emby_id=emby_id, admin=False, disable=disable))
            except Exception as exc:
                LOGGER.warning(f"admin user batch policy sync failed emby_id={emby_id}: {exc}")
                return False

    results = await asyncio.gather(*[_change_one(emby_id) for emby_id in emby_ids])
    success_count = sum(1 for item in results if item)
    return {
        "success_count": success_count,
        "fail_count": len(results) - success_count,
        "total": len(results),
    }


async def _delete_user_batch_emby_accounts(rows: list[Emby]) -> dict[str, int]:
    targets = [(str(row.embyid), str(row.name or ""), int(row.tg)) for row in rows if row.embyid]
    no_account_tgs = [int(row.tg) for row in rows if not row.embyid]

    from bot.func_helper.emby import emby as emby_service

    semaphore = asyncio.Semaphore(8)

    async def _delete_one(target: tuple[str, str, int]) -> tuple[str, str, int, bool]:
        emby_id, name, tg = target
        async with semaphore:
            try:
                ok = bool(await emby_service.emby_del(emby_id=emby_id))
            except Exception as exc:
                LOGGER.warning(f"admin user batch delete emby account failed emby_id={emby_id}: {exc}")
                ok = False
            return emby_id, name, tg, ok

    results = await asyncio.gather(*[_delete_one(target) for target in targets]) if targets else []
    deleted = [(emby_id, name, tg) for emby_id, name, tg, ok in results if ok]
    deleted_emby_ids = {emby_id for emby_id, _, _ in deleted if emby_id}
    deleted_names = {name for _, name, _ in deleted if name}
    clear_tgs = [tg for _, _, tg in deleted] + no_account_tgs

    if deleted_emby_ids or deleted_names or clear_tgs:
        with Session() as session:
            if deleted_emby_ids:
                session.query(Emby2).filter(Emby2.embyid.in_(list(deleted_emby_ids))).delete(synchronize_session=False)
            if deleted_names:
                session.query(Emby2).filter(Emby2.name.in_(list(deleted_names))).delete(synchronize_session=False)

            if clear_tgs:
                session.query(Emby).filter(Emby.tg.in_(clear_tgs)).update(
                    {
                        Emby.embyid: None,
                        Emby.name: None,
                        Emby.pwd: None,
                        Emby.pwd2: None,
                        Emby.lv: "d",
                        Emby.cr: None,
                        Emby.ex: None,
                    },
                    synchronize_session=False,
                )
            session.commit()

    return {
        "success_count": len(deleted) + len(no_account_tgs),
        "fail_count": len(results) - len(deleted),
        "total": len(rows),
    }


@router.get("/summary")
async def summary():
    def _collect_summary():
        with Session() as session:
            row = session.query(
                func.count(Emby.tg),
                func.sum(case((Emby.embyid.isnot(None), 1), else_=0)),
                func.sum(case((Emby.lv == "a", 1), else_=0)),
                func.sum(case((Emby.lv == "c", 1), else_=0)),
                func.coalesce(func.sum(Emby.iv), 0),
            ).one()
            total_users, active_accounts, whitelist_users, banned_users, total_currency = row
            return {
                "total_users": int(total_users or 0),
                "active_accounts": int(active_accounts or 0),
                "whitelist_users": int(whitelist_users or 0),
                "banned_users": int(banned_users or 0),
                "total_currency": int(total_currency or 0),
            }

    counts = await run_in_threadpool(_collect_summary)
    return {
        "code": 200,
        "data": {
            **counts,
            "auto_update": serialize_auto_update_state(),
            "emby_service_suspended": bool(config.emby_service_suspended),
        },
    }


@router.get("/system/auto-update")
async def get_auto_update():
    return {"code": 200, "data": serialize_auto_update_state()}


@router.patch("/system/auto-update")
async def patch_auto_update(payload: AdminAutoUpdatePatch):
    data = update_auto_update_settings(payload.model_dump(exclude_unset=True))
    return {"code": 200, "data": data}


@router.get("/system/migration/export")
async def export_migration_bundle():
    exported = await run_in_threadpool(create_migration_bundle)
    return FileResponse(
        exported["archive_path"],
        media_type="application/zip",
        filename=exported["filename"],
        background=BackgroundTask(shutil.rmtree, exported["temp_root"], ignore_errors=True),
    )


@router.post("/system/migration/import")
async def import_migration_bundle_api(
    file: UploadFile = File(...),
    restore_config_file: bool = Form(False),
    restart_after_import: bool = Form(True),
):
    try:
        await file.seek(0)
        imported = await run_in_threadpool(
            restore_migration_bundle,
            file.file,
            restore_config_file=restore_config_file,
        )
    except MigrationBundleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        LOGGER.exception("migration bundle import failed")
        raise HTTPException(status_code=500, detail="压缩包导入失败了...本女仆也不知道为什么，主人快看看日志啦~") from exc
    finally:
        await file.close()

    if restart_after_import:
        _schedule_restart_after_delay(4.0)

    return {
        "code": 200,
        "data": {
            **imported,
            "restart_scheduled": bool(restart_after_import),
            "source_filename": file.filename or "migration.zip",
        },
    }


@router.get("/users")
async def list_users(
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    keyword = (q or "").strip()
    start = (page - 1) * page_size

    def _load_user_page():
        with Session() as session:
            query = session.query(Emby)
            if keyword:
                filtered_query = _apply_admin_user_keyword_filter(query, keyword)
                local_total = int(filtered_query.count() or 0)
                local_page_users = (
                    filtered_query
                    .order_by(Emby.tg.desc())
                    .offset(start)
                    .limit(page_size)
                    .all()
                )
            else:
                local_total = int(query.count() or 0)
                local_page_users = (
                    query
                    .order_by(Emby.tg.desc())
                    .offset(start)
                    .limit(page_size)
                    .all()
                )
            return local_page_users, local_total

    page_users, total = await run_in_threadpool(_load_user_page)

    if keyword and total == 0:
        page_users, total = await _search_admin_users_by_telegram_identity(keyword, page, page_size)

    identity_map = await _fetch_telegram_identity_map([user.tg for user in page_users])

    return {
        "code": 200,
        "data": {
            "items": [_serialize_admin_user(user, identity_map.get(int(user.tg))) for user in page_users],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }


@router.get("/users/{tg}")
async def get_user(tg: int):
    with Session() as session:
        user = session.query(Emby).filter(Emby.tg == tg).first()
        if user is None:
            raise HTTPException(status_code=404, detail="哼，本女仆找不到这个用户啦~")
    identity_map = await _fetch_telegram_identity_map([tg])
    return {"code": 200, "data": _serialize_admin_user(user, identity_map.get(int(tg)))}


@router.patch("/users/{tg}")
async def update_user(tg: int, payload: AdminUserPatch):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return {"code": 200, "data": {"updated": False, "reason": "no_changes"}}

    with Session() as session:
        user = session.query(Emby).filter(Emby.tg == tg).first()
        if user is None:
            raise HTTPException(status_code=404, detail="哼，本女仆找不到这个用户啦~")

        for key, value in changes.items():
            setattr(user, key, value)

        session.commit()
        session.refresh(user)
    identity_map = await _fetch_telegram_identity_map([tg])
    return {"code": 200, "data": _serialize_admin_user(user, identity_map.get(int(tg)))}


@router.post("/users/batch/preview")
async def preview_user_batch(payload: AdminUserBatchPayload):
    normalized = _normalize_user_batch_payload(payload)
    with Session() as session:
        rows = _load_user_batch_rows(session, normalized)

    sample_tgs = [int(row.tg) for row in rows[:8]]
    identity_map = await _fetch_telegram_identity_map(sample_tgs)
    preview = _user_batch_preview_from_rows(rows, **normalized, identity_map=identity_map)
    return {"code": 200, "data": preview}


@router.post("/users/batch/apply")
async def apply_user_batch(payload: AdminUserBatchPayload, request: Request):
    normalized = _normalize_user_batch_payload(payload)
    actor_tg = _resolve_admin_actor_id(request)

    with Session() as session:
        rows = _load_user_batch_rows(session, normalized)
    sample_tgs = [int(row.tg) for row in rows[:8]]
    identity_map = await _fetch_telegram_identity_map(sample_tgs)
    preview = _user_batch_preview_from_rows(rows, **normalized, identity_map=identity_map)

    if not rows:
        return {
            "code": 200,
            "data": {
                **preview,
                "updated_count": 0,
                "deleted_count": 0,
                "policy_sync": {"success_count": 0, "fail_count": 0, "total": 0},
            },
        }

    action = normalized["action"]
    target_level = normalized["target_level"]
    policy_sync = {"success_count": 0, "fail_count": 0, "total": 0}
    updated_count = 0
    deleted_count = 0

    if action == "delete":
        policy_sync = await _delete_user_batch_emby_accounts(rows)
        deleted_count = int(policy_sync["success_count"])
        updated_count = deleted_count
    else:
        if action == "ban" or target_level == "c":
            policy_sync = await _sync_user_batch_emby_policy(rows, disable=True)
        elif target_level in {"a", "b"} and not config.emby_service_suspended:
            policy_sync = await _sync_user_batch_emby_policy(rows, disable=False)

        tgs = [int(row.tg) for row in rows]
        with Session() as session:
            updated_count = int(
                session.query(Emby)
                .filter(Emby.tg.in_(tgs))
                .update({Emby.lv: target_level}, synchronize_session=False)
                or 0
            )
            session.commit()

    sql_invalidate_emby_namespace()
    LOGGER.info(
        "admin user batch actor=%s action=%s scope=%s source=%s target=%s affected=%s updated=%s policy=%s",
        actor_tg,
        action,
        normalized["scope"],
        normalized["source_level"],
        target_level,
        preview["affected_count"],
        updated_count,
        policy_sync,
    )
    return {
        "code": 200,
        "data": {
            **preview,
            "updated_count": updated_count,
            "deleted_count": deleted_count,
            "policy_sync": policy_sync,
        },
    }


@router.post("/users/whitelist/revoke-all")
async def revoke_all_whitelist_users(request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    with Session() as session:
        affected = int(session.query(func.count(Emby.tg)).filter(Emby.lv == "a").scalar() or 0)
        if affected > 0:
            session.query(Emby).filter(Emby.lv == "a").update({Emby.lv: "b"}, synchronize_session=False)
            session.commit()
        else:
            session.rollback()
    sql_invalidate_emby_namespace()
    LOGGER.info(f"admin whitelist revoke-all actor={actor_tg} affected={affected}")
    return {
        "code": 200,
        "data": {
            "updated_count": affected,
            "target_level": "b",
        },
    }


@router.post("/emby-service/toggle")
async def toggle_emby_service(request: Request):
    """一键暂停/恢复所有用户的 Emby 服务（通过 Emby API 设置 IsDisabled）"""
    from bot.func_helper.emby import Embyservice
    from bot import emby_url, emby_api as emby_api_key

    actor_tg = _resolve_admin_actor_id(request)
    new_state = not config.emby_service_suspended

    with Session() as session:
        users_with_emby = session.query(Emby).filter(Emby.embyid.isnot(None)).all()
        emby_ids = [str(row.embyid) for row in users_with_emby if row.embyid]

    emby = Embyservice(emby_url, emby_api_key)
    semaphore = asyncio.Semaphore(16)

    async def _toggle_one(emby_id: str) -> bool:
        async with semaphore:
            try:
                result = await emby.emby_change_policy(emby_id, admin=False, disable=new_state)
                return bool(result)
            except Exception as exc:
                LOGGER.warning(f"emby service toggle failed for {emby_id}: {exc}")
                return False

    try:
        results = await asyncio.gather(*[_toggle_one(eid) for eid in emby_ids]) if emby_ids else []
    finally:
        await emby.close()
    success_count = sum(1 for r in results if r)
    fail_count = len(results) - success_count

    config.emby_service_suspended = new_state
    save_config()

    action = "暂停" if new_state else "恢复"
    LOGGER.info(
        f"admin emby-service toggle actor={actor_tg} action={action} "
        f"success={success_count} fail={fail_count} total={len(emby_ids)}"
    )

    return {
        "code": 200,
        "data": {
            "emby_service_suspended": new_state,
            "action": action,
            "success_count": success_count,
            "fail_count": fail_count,
            "total_accounts": len(emby_ids),
        },
    }


@router.get("/moderation/chats")
async def list_moderation_chats():
    return {"code": 200, "data": await list_managed_chats()}


@router.get("/moderation/settings/{chat_id}")
async def get_moderation_settings(chat_id: int):
    return {"code": 200, "data": get_group_moderation_setting(chat_id)}


@router.patch("/moderation/settings/{chat_id}")
async def patch_moderation_settings(chat_id: int, payload: AdminModerationSettingsPatch, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        data = await update_warning_config(
            chat_id,
            warn_threshold=payload.warn_threshold,
            warn_action=payload.warn_action,
            mute_minutes=payload.mute_minutes,
            updated_by=actor_tg,
        )
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    LOGGER.info(f"admin moderation settings actor={actor_tg} chat={chat_id} data={data}")
    return {"code": 200, "data": data}


@router.get("/moderation/members/search")
async def moderation_search_members(
    chat_id: int = Query(...),
    q: str = Query(...),
    limit: int = Query(default=20, ge=1, le=50),
):
    keyword = str(q or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空啦，本女仆怎么找嘛...")

    items = await search_chat_members(chat_id, keyword, limit=limit)
    tg_ids = [int(item["tg"]) for item in items if item.get("tg") is not None]
    warning_map = warning_map_for_targets(chat_id, tg_ids)

    with Session() as session:
        emby_rows = session.query(Emby).filter(Emby.tg.in_(tg_ids)).all() if tg_ids else []

    emby_map = {int(row.tg): row for row in emby_rows}
    return {
        "code": 200,
        "data": {
            "items": [_serialize_moderation_member(item, warning_map, emby_map) for item in items],
            "settings": get_group_moderation_setting(chat_id),
        },
    }


@router.get("/moderation/warnings")
async def moderation_list_warnings(
    chat_id: int = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
):
    items = list_group_moderation_warnings(chat_id, limit=limit)
    tg_ids = [int(item["tg"]) for item in items if item.get("tg") is not None]
    identity_map = await _fetch_telegram_identity_map(tg_ids)

    with Session() as session:
        emby_rows = session.query(Emby).filter(Emby.tg.in_(tg_ids)).all() if tg_ids else []

    emby_map = {int(row.tg): row for row in emby_rows}
    return {
        "code": 200,
        "data": {
            "settings": get_group_moderation_setting(chat_id),
            "items": [
                _serialize_moderation_warning_item(item, identity_map.get(int(item["tg"])), emby_map.get(int(item["tg"])))
                for item in items
            ],
        },
    }


@router.post("/moderation/actions/mute")
async def moderation_mute(payload: AdminModerationMutePayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        result = await mute_chat_member(payload.chat_id, payload.tg, payload.minutes)
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target = await _safe_get_moderation_target(payload.chat_id, payload.tg)
    LOGGER.info(f"admin moderation mute actor={actor_tg} chat={payload.chat_id} target={payload.tg} minutes={payload.minutes}")
    return {"code": 200, "data": {"target": target, "result": result}}


@router.post("/moderation/actions/kick")
async def moderation_kick(payload: AdminModerationKickPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        result = await kick_chat_member(payload.chat_id, payload.tg)
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target = await _safe_get_moderation_target(payload.chat_id, payload.tg)
    LOGGER.info(f"admin moderation kick actor={actor_tg} chat={payload.chat_id} target={payload.tg}")
    return {"code": 200, "data": {"target": target, "result": result}}


@router.post("/moderation/actions/title")
async def moderation_title(payload: AdminModerationTitlePayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        result = await set_chat_member_title(payload.chat_id, payload.tg, payload.title)
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target = await _safe_get_moderation_target(payload.chat_id, payload.tg)
    LOGGER.info(f"admin moderation title actor={actor_tg} chat={payload.chat_id} target={payload.tg} title={payload.title}")
    return {"code": 200, "data": {"target": target, "result": result}}


@router.post("/moderation/actions/pin")
async def moderation_pin(payload: AdminModerationPinPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        result = await pin_chat_message(
            payload.chat_id,
            payload.message_id,
            disable_notification=bool(payload.disable_notification),
        )
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    LOGGER.info(f"admin moderation pin actor={actor_tg} chat={payload.chat_id} message_id={payload.message_id}")
    return {"code": 200, "data": result}


@router.post("/moderation/actions/unpin")
async def moderation_unpin(payload: AdminModerationUnpinPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        result = await unpin_chat_message(payload.chat_id, payload.message_id)
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    LOGGER.info(f"admin moderation unpin actor={actor_tg} chat={payload.chat_id} message_id={payload.message_id}")
    return {"code": 200, "data": result}


@router.post("/moderation/actions/warn")
async def moderation_warn(payload: AdminModerationWarnPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        result = await warn_chat_member(
            payload.chat_id,
            payload.tg,
            actor_tg=actor_tg,
            reason=payload.reason,
        )
    except ModerationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target = await _safe_get_moderation_target(payload.chat_id, payload.tg)
    LOGGER.info(f"admin moderation warn actor={actor_tg} chat={payload.chat_id} target={payload.tg} reason={payload.reason!r}")
    return {"code": 200, "data": {"target": target, **result}}


@router.post("/moderation/actions/clear-warn")
async def moderation_clear_warn(payload: AdminModerationKickPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    result = clear_chat_member_warning(payload.chat_id, payload.tg)
    target = await _safe_get_moderation_target(payload.chat_id, payload.tg)
    LOGGER.info(f"admin moderation clear-warn actor={actor_tg} chat={payload.chat_id} target={payload.tg} removed={result.get('removed')}")
    return {
        "code": 200,
        "data": {
            "target": target,
            "result": result,
            "settings": get_group_moderation_setting(payload.chat_id),
        },
    }


@router.get("/bot-access-blocks")
async def list_bot_access_blocks():
    with Session() as session:
        rows = (
            session.query(BotAccessBlock)
            .order_by(BotAccessBlock.created_at.desc(), BotAccessBlock.id.desc())
            .all()
        )

    return {
        "code": 200,
        "data": [serialize_bot_access_block(row) for row in rows],
    }


@router.post("/bot-access-blocks")
async def create_bot_access_block(payload: AdminBotAccessBlockCreatePayload):
    normalized = _normalize_bot_access_payload(payload)
    existing = find_existing_bot_access_block(tg=normalized["tg"], username=normalized["username"])
    if existing is not None:
        target = serialize_bot_access_block(existing).get("target_text") or f"规则 {existing.id}"
        raise HTTPException(status_code=409, detail=f"{target} 已经在黑名单里了啦~")

    with Session() as session:
        try:
            row = BotAccessBlock(
                tg=normalized["tg"],
                username=normalized["username"],
                note=normalized["note"],
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        except Exception as exc:
            session.rollback()
            LOGGER.warning(f"create bot access block failed: {exc}")
            raise HTTPException(status_code=500, detail="黑名单规则创建失败了...才不是本女仆的错！") from exc

    invalidate_bot_access_cache()
    return {"code": 200, "data": serialize_bot_access_block(row)}


@router.delete("/bot-access-blocks/{block_id}")
async def delete_bot_access_block(block_id: int):
    with Session() as session:
        row = session.query(BotAccessBlock).filter(BotAccessBlock.id == block_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="哼，本女仆找不到这条黑名单规则啦~")

        payload = serialize_bot_access_block(row)
        try:
            session.delete(row)
            session.commit()
        except Exception as exc:
            session.rollback()
            LOGGER.warning(f"delete bot access block failed: {exc}")
            raise HTTPException(status_code=500, detail="黑名单规则删除失败了...才不是本女仆的错！") from exc

    invalidate_bot_access_cache()
    return {"code": 200, "data": {"deleted": True, "item": payload}}


@router.get("/codes")
async def list_codes(
    status: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    normalized_status = str(status or "all").strip().lower()
    if normalized_status not in {"all", "unused", "used"}:
        raise HTTPException(status_code=400, detail="status 只能是 all、unused 或 used 啦~")

    with Session() as session:
        all_total = session.query(func.count(Code.code)).scalar() or 0
        unused_total = (
            session.query(func.count(Code.code))
            .filter(func.coalesce(Code.use_count, 0) == 0)
            .scalar()
            or 0
        )
        used_total = (
            session.query(func.count(Code.code))
            .filter(func.coalesce(Code.use_count, 0) > 0)
            .scalar()
            or 0
        )
        exhausted_total = (
            session.query(func.count(Code.code))
            .filter(func.coalesce(Code.use_count, 0) >= func.coalesce(Code.use_limit, 1))
            .scalar()
            or 0
        )

        query = session.query(Code)
        if normalized_status == "unused":
            query = query.filter(func.coalesce(Code.use_count, 0) == 0)
        elif normalized_status == "used":
            query = query.filter(func.coalesce(Code.use_count, 0) > 0)

        total = query.count()
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        page_rows = (
            query.order_by(Code.usedtime.desc(), Code.code.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        codes = [row.code for row in page_rows]
        redeem_rows = []
        if codes:
            redeem_rows = (
                session.query(CodeRedeem)
                .filter(CodeRedeem.code.in_(codes))
                .order_by(CodeRedeem.redeemed_at.desc(), CodeRedeem.id.desc())
                .all()
            )

        tg_ids = {
            int(value)
            for value in [*(row.tg for row in page_rows), *(row.used for row in page_rows)]
            if value is not None
        }
        for redeem in redeem_rows:
            if redeem.user_id is not None:
                tg_ids.add(int(redeem.user_id))

        emby_rows = session.query(Emby).filter(Emby.tg.in_(tg_ids)).all() if tg_ids else []

    redeem_map: dict[str, list[CodeRedeem]] = {}
    for redeem in redeem_rows:
        redeem_map.setdefault(redeem.code, []).append(redeem)

    emby_map = {int(row.tg): row for row in emby_rows}
    identity_map = await _fetch_telegram_identity_map(list(tg_ids))
    items = [
        _serialize_code_record(row, redeem_map.get(row.code, []), identity_map, emby_map)
        for row in page_rows
    ]

    return {
        "code": 200,
        "data": {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "summary": {
                "all": int(all_total),
                "unused": int(unused_total),
                "used": int(used_total),
                "exhausted": int(exhausted_total),
            },
        },
    }


@router.post("/codes")
async def create_codes(payload: AdminCodeCreatePayload, request: Request):
    normalized = _normalize_code_create_payload(payload)
    admin_id = _resolve_admin_actor_id(request)
    if admin_id is None:
        raise HTTPException(status_code=400, detail="本女仆无法识别当前管理员身份...你是谁呀？")

    generator = cr_link_one if normalized["type"] == "F" else rn_link_one
    generated_output = await generator(
        admin_id,
        str(normalized["days"]),
        normalized["count"],
        normalized["days"],
        normalized["method"],
        usage_limit=normalized["usage_limit"],
        suffix_mode=normalized["suffix_mode"],
        suffix_text=normalized["suffix_text"],
    )
    if generated_output is None:
        raise HTTPException(status_code=500, detail="数据库写入失败了...才不是本女仆的错！请稍后重试啦~")

    items = _parse_generated_items(generated_output, normalized["method"])
    return {
        "code": 200,
        "data": {
            "count": normalized["count"],
            "days": normalized["days"],
            "method": normalized["method"],
            "type": normalized["type"],
            "type_text": "注册码" if normalized["type"] == "F" else "续期码",
            "usage_limit": normalized["usage_limit"],
            "suffix_mode": normalized["suffix_mode"],
            "suffix_text": normalized["suffix_text"],
            "items": items,
            "output": generated_output,
        },
    }


@router.post("/codes/delete")
async def delete_codes(payload: AdminCodeDeletePayload):
    codes = [str(code).strip() for code in payload.codes if str(code).strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="至少需要提供一个注册码啦~")
    if len(codes) > 1000:
        raise HTTPException(status_code=400, detail="单次最多删除 1000 个注册码啦，太多了本女仆处理不过来~")

    unique_codes = list(dict.fromkeys(codes))
    with Session() as session:
        try:
            redeem_deleted = (
                session.query(CodeRedeem)
                .filter(CodeRedeem.code.in_(unique_codes))
                .delete(synchronize_session=False)
            )
            code_deleted = (
                session.query(Code)
                .filter(Code.code.in_(unique_codes))
                .delete(synchronize_session=False)
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            LOGGER.warning(f"admin code batch delete failed: {exc}")
            raise HTTPException(status_code=500, detail="批量删除注册码失败了...才不是本女仆的错！") from exc

    return {
        "code": 200,
        "data": {
            "requested": len(unique_codes),
            "deleted": int(code_deleted),
            "redeem_deleted": int(redeem_deleted),
        },
    }


@router.get("/invites")
async def admin_invites(
    q: str = Query(default=""),
    account_page: int = Query(default=1, ge=1),
    group_page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=20),
):
    return {
        "code": 200,
        "data": await _invite_admin_bundle(
            search_query=q,
            account_page=account_page,
            group_page=group_page,
            page_size=page_size,
        ),
    }


@router.patch("/invites/settings")
async def patch_invite_settings(payload: AdminInviteSettingsPatch, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    settings = set_invite_settings(payload.model_dump(exclude_unset=True))
    LOGGER.info(f"admin invite settings actor={actor_tg} settings={settings}")
    return {"code": 200, "data": await _invite_admin_bundle()}


@router.post("/invites/credits")
async def grant_invite_credit_api(payload: AdminInviteGrantPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        credit_type = normalize_invite_credit_type(payload.credit_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = (
        "注册资格已改为申请制，请在后台处理开通申请或使用管理员代发。"
        if credit_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN
        else "入群资格已改为观影用户自动拥有一次，不支持手动发放。"
    )
    LOGGER.info(
        f"admin legacy invite credits grant rejected actor={actor_tg} owner={payload.owner_tg} "
        f"type={credit_type} count={payload.count}"
    )
    raise HTTPException(status_code=410, detail=detail)


@router.patch("/invites/credits/{credit_id}")
async def patch_invite_credit_api(credit_id: int, payload: AdminInviteCreditPatchPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        updated = update_invite_credit(credit_id, **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="哼，本女仆找不到这条邀请资格啦~")
    LOGGER.info(f"admin invite credit edit actor={actor_tg} credit={credit_id}")
    bundle = await _invite_admin_bundle()
    bundle["updated_credit"] = updated
    return {"code": 200, "data": bundle}


@router.patch("/invites/qualification")
async def patch_invite_qualification_api(payload: AdminInviteQualificationPatchPayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    try:
        credit_type = normalize_invite_credit_type(payload.credit_type)
        qualification = set_invite_qualification(
            owner_tg=payload.owner_tg,
            credit_type=credit_type,
            enabled=payload.enabled,
            actor_tg=actor_tg,
            reason=payload.reason or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.info(
        f"admin invite qualification edit actor={actor_tg} owner={payload.owner_tg} "
        f"type={credit_type} enabled={payload.enabled}"
    )
    bundle = await _invite_admin_bundle(search_query=str(payload.owner_tg))
    bundle["updated_qualification"] = qualification
    return {"code": 200, "data": bundle}


@router.post("/invites/account-open/create")
async def create_account_open_invite_api(payload: AdminAccountOpenInviteCreatePayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    await _ensure_target_user_in_invite_group(payload.invitee_tg)
    try:
        record = create_account_open_invite_record(
            inviter_tg=payload.inviter_tg,
            invitee_tg=payload.invitee_tg,
            created_by_tg=actor_tg,
            note=payload.note or "",
            auto_approve=True,
            reviewed_by_tg=actor_tg,
            review_note="后台代发通过",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.info(
        f"admin account open invite create actor={actor_tg} "
        f"inviter={payload.inviter_tg} invitee={payload.invitee_tg}"
    )
    bundle = await _invite_admin_bundle()
    bundle["created_record"] = record
    return {"code": 200, "data": bundle}


@router.post("/invites/account-open/records/{record_id}/review")
async def review_account_open_invite_api(
    record_id: int,
    payload: AdminAccountOpenInviteReviewPayload,
    request: Request,
):
    actor_tg = _resolve_admin_actor_id(request)
    action = str(payload.action or "approve").strip().lower()
    try:
        if action == "approve":
            pending_record = get_invite_record(record_id)
            if pending_record is None:
                raise HTTPException(status_code=404, detail="哼，本女仆找不到这条开通申请啦~")
            await _ensure_target_user_in_invite_group(int(pending_record.get("invitee_tg") or 0))
        if action == "approve":
            record = approve_account_open_invite_record(
                record_id,
                reviewer_tg=actor_tg,
                invite_days=payload.invite_days,
                review_note=payload.note or "",
            )
        elif action in {"decline", "reject"}:
            record = decline_account_open_invite_record(
                record_id,
                reviewer_tg=actor_tg,
                review_note=payload.note or "",
            )
        elif action == "revoke":
            record = revoke_account_open_invite_record(
                record_id,
                reviewer_tg=actor_tg,
                review_note=payload.note or "后台撤销",
            )
        else:
            raise HTTPException(status_code=400, detail="审核动作不正确啦，只能是 approve/decline/reject/revoke 哦~")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="哼，本女仆找不到这条开通申请啦~")
    await _safe_send_account_open_review_notice(record, action)
    LOGGER.info(f"admin account open invite review actor={actor_tg} record={record_id} action={action}")
    bundle = await _invite_admin_bundle()
    bundle["reviewed_record"] = record
    return {"code": 200, "data": bundle}


@router.post("/invites/credits/delete")
async def delete_invite_credits_api(payload: AdminInviteCreditDeletePayload, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    unique_ids = [int(item) for item in dict.fromkeys(payload.credit_ids) if int(item) > 0]
    if not unique_ids:
        raise HTTPException(status_code=400, detail="至少需要选择一个邀请资格啦~")
    deleted = 0
    skipped = 0
    for credit_id in unique_ids:
        item = revoke_invite_credit(credit_id, revoked_by_tg=actor_tg, reason=payload.reason or "后台删除")
        if item and item.get("status") == "revoked":
            deleted += 1
        else:
            skipped += 1
    LOGGER.info(f"admin invite credits delete actor={actor_tg} deleted={deleted} skipped={skipped}")
    bundle = await _invite_admin_bundle()
    bundle["delete_result"] = {"requested": len(unique_ids), "deleted": deleted, "skipped": skipped}
    return {"code": 200, "data": bundle}


@router.post("/invites/records/{record_id}/revoke")
async def revoke_invite_record_api(record_id: int, request: Request):
    actor_tg = _resolve_admin_actor_id(request)
    record = get_invite_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="哼，本女仆找不到这条邀请记录啦~")
    if record.get("status") == "pending":
        await _safe_revoke_invite_link(record.get("target_chat_id"), record.get("invite_link") or "")
    try:
        updated = revoke_invite_record(record_id, requester_tg=actor_tg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.info(f"admin invite record revoke actor={actor_tg} record={record_id}")
    bundle = await _invite_admin_bundle()
    bundle["revoked_record"] = updated
    return {"code": 200, "data": bundle}


@router.get("/plugins")
async def plugins():
    # Discovery includes filesystem and migration-summary reads; keep it out
    # of the FastAPI event loop just like plugin mutations below.
    discovered = await run_in_threadpool(list_plugins)
    items = []
    for plugin in discovered:
        visible = bool(config.plugin_nav.get(plugin["id"], plugin.get("bottom_nav_default", False)))
        items.append(
            {
                **plugin,
                "bottom_nav_visible": visible,
            }
        )
    return {"code": 200, "data": items}


@router.patch("/plugins/{plugin_id}")
async def patch_plugin(plugin_id: str, payload: AdminPluginPatch, request: Request):
    discovered = await run_in_threadpool(list_plugins)
    plugins = {plugin["id"]: plugin for plugin in discovered}
    if plugin_id not in plugins:
        raise HTTPException(status_code=404, detail="哼，本女仆找不到这个插件啦~")
    if payload.enabled is None and payload.bottom_nav_visible is None:
        raise HTTPException(status_code=400, detail="至少需要提供 enabled 或 bottom_nav_visible 之一啦~")

    plugin = plugins[plugin_id]
    if payload.enabled is not None:
        if payload.enabled == plugin.get("manifest_enabled", True):
            config.plugin_enabled.pop(plugin_id, None)
        else:
            config.plugin_enabled[plugin_id] = payload.enabled
        if payload.enabled is False and payload.bottom_nav_visible is None:
            config.plugin_nav[plugin_id] = False

    if payload.bottom_nav_visible is not None:
        config.plugin_nav[plugin_id] = payload.bottom_nav_visible

    save_config()
    runtime_plugin = await run_in_threadpool(sync_plugin_runtime_state, plugin_id, request.app)
    visible = bool(config.plugin_nav.get(plugin_id, runtime_plugin.get("bottom_nav_default", False)))
    return {
        "code": 409 if runtime_plugin.get("runtime_action") == "failed" else 200,
        "data": {
            **runtime_plugin,
            "bottom_nav_visible": visible,
            "status": runtime_plugin.get("runtime_action", "updated"),
        },
    }


@router.post("/plugins/import")
async def import_plugin(
    request: Request,
    file: UploadFile = File(...),
    enabled: bool = Form(True),
    replace_existing: bool = Form(False),
):
    try:
        archive_bytes = await _read_upload_limited(file, _PLUGIN_ARCHIVE_MAX_BYTES)
        imported = await run_in_threadpool(
            import_plugin_archive,
            archive_bytes,
            file.filename or "plugin.zip",
            replace_existing=replace_existing,
        )
    except PluginImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

    plugin_id = imported["plugin_id"]
    if imported.get("permission_review_required") or imported.get("unknown_permissions"):
        enabled = False
    if enabled == imported.get("manifest_enabled", True):
        config.plugin_enabled.pop(plugin_id, None)
    else:
        config.plugin_enabled[plugin_id] = enabled
    if not enabled:
        config.plugin_nav[plugin_id] = False

    save_config()
    runtime_plugin = await run_in_threadpool(sync_plugin_runtime_state, plugin_id, request.app)
    visible = bool(config.plugin_nav.get(plugin_id, runtime_plugin.get("bottom_nav_default", False)))
    return {
        "code": 409 if runtime_plugin.get("runtime_action") == "failed" else 200,
        "data": {
            **runtime_plugin,
            "bottom_nav_visible": visible,
            "imported": True,
            "replaced": imported["replaced"],
            "backup_path": imported["backup_path"],
            "directory": imported["directory"],
            "source_filename": imported["source_filename"],
            "status": runtime_plugin.get("runtime_action", "imported"),
        },
    }
