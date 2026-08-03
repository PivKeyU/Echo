from __future__ import annotations

import asyncio
import hmac
import json
import os
from datetime import datetime, timedelta
from hashlib import sha256
from time import time
from urllib.parse import parse_qsl
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from bot import LOGGER, admins, api as api_config, bot, bot_token, chanel, config, owner, pivkeyu, ranks
from bot.plugins import list_miniapp_plugins
from bot.sql_helper.sql_bot_access import find_bot_access_block
from bot.sql_helper.sql_emby import sql_get_emby
from bot.sql_helper.sql_invite import (
    INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
    INVITE_CREDIT_TYPE_GROUP,
    available_invite_credit_count,
    cancel_pending_invite_record,
    create_account_open_invite_record,
    create_invite_record,
    get_invite_settings,
    has_viewing_access,
    invite_qualification_status,
    list_invite_records,
    user_has_account_open_history,
    user_has_group_invite_history,
)
from bot.web.presenters import serialize_emby_user

router = APIRouter(prefix="/miniapp-api", tags=["小程序"])


class MiniAppInitRequest(BaseModel):
    init_data: str


class MiniAppInviteCreateRequest(MiniAppInitRequest):
    invitee_tg: int
    note: str | None = None


def _public_invite_record(record: dict | None, *, include_link: bool = False) -> dict | None:
    if record is None:
        return None
    payload = dict(record)
    if not include_link:
        payload.pop("invite_link", None)
    return payload


def _public_invite_bundle(user_id: int, account=None) -> dict:
    account = account if account is not None else sql_get_emby(user_id)
    settings = get_invite_settings()
    has_access = has_viewing_access(account)
    group_count = available_invite_credit_count(user_id, credit_type=INVITE_CREDIT_TYPE_GROUP)
    group_records = [
        _public_invite_record(item)
        for item in list_invite_records(inviter_tg=user_id, credit_type=INVITE_CREDIT_TYPE_GROUP, limit=20)
    ]
    account_open_records = [
        _public_invite_record(item)
        for item in list_invite_records(inviter_tg=user_id, credit_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN, limit=20)
    ]
    account_open_history = user_has_account_open_history(user_id) if has_access else False
    qualification = invite_qualification_status(user_id)
    account_open_count = 1 if qualification.get("account_open", {}).get("available") else 0
    return {
        "settings": {
            "enabled": bool(settings.get("enabled")),
            "target_chat_id": settings.get("target_chat_id"),
            "expire_hours": int(settings.get("expire_hours") or 24),
            "strict_target": bool(settings.get("strict_target", True)),
            "group_verification_enabled": bool(settings.get("group_verification_enabled", settings.get("strict_target", True))),
            "channel_verification_enabled": bool(settings.get("channel_verification_enabled", False)),
            "account_open_days": int(settings.get("account_open_days") or 30),
        },
        "permissions": {
            "has_viewing_access": bool(has_access),
            "can_create": bool(settings.get("enabled") and (has_access or group_count > 0)),
            "has_invite_qualification": bool(settings.get("enabled") and group_count > 0),
            "has_account_open_application_qualification": bool(
                settings.get("enabled") and qualification.get("account_open", {}).get("available")
            ),
            "group_verification_enabled": bool(settings.get("group_verification_enabled", settings.get("strict_target", True))),
            "channel_verification_enabled": bool(settings.get("channel_verification_enabled", False)),
            "group_invite_used": bool(user_has_group_invite_history(user_id)) if has_access or group_count > 0 else False,
            "account_open_application_used": bool(account_open_history),
            "group_invite_revoked": bool(qualification.get("group_join", {}).get("revoked")),
            "account_open_application_revoked": bool(qualification.get("account_open", {}).get("revoked")),
        },
        "available_credits": group_count,
        "records": group_records,
        "group_join": {
            "available_credits": group_count,
            "records": group_records,
        },
        "account_open": {
            "available_credits": account_open_count,
            "records": account_open_records,
        },
    }


def _invite_link_value(invite_link_obj) -> str:
    for field in ("invite_link", "link"):
        value = getattr(invite_link_obj, field, None)
        if value:
            return str(value)
    return str(invite_link_obj or "").strip()


def _telegram_user_label(user: dict | None) -> str:
    user = user or {}
    display_name = " ".join(
        str(part or "").strip()
        for part in [user.get("first_name"), user.get("last_name")]
        if str(part or "").strip()
    ).strip()
    if display_name:
        return display_name
    username = str(user.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    return str(user.get("id") or "未知用户")


async def _create_targeted_invite_link(chat_id: int, invitee_tg: int, expire_hours: int) -> tuple[str, datetime, str]:
    expires_at = datetime.utcnow() + timedelta(hours=max(int(expire_hours or 24), 1))
    link_name = f"emby-invite-{invitee_tg}-{int(time())}"
    try:
        invite_link_obj = await bot.create_chat_invite_link(
            chat_id=int(chat_id),
            name=link_name,
            expire_date=expires_at,
            creates_join_request=True,
        )
    except TypeError as exc:
        raise RuntimeError("呜...当前 Pyrogram 版本太旧了，不支持这个功能，快催主人升级啦~") from exc
    invite_link = _invite_link_value(invite_link_obj)
    if not invite_link:
        raise RuntimeError("Telegram 没给本女仆邀请链接...可能是被限制了啦")
    return invite_link, expires_at, link_name


async def _safe_revoke_invite_link(chat_id: int, invite_link: str) -> None:
    if not invite_link:
        return
    try:
        await bot.revoke_chat_invite_link(chat_id=int(chat_id), invite_link=invite_link)
    except Exception as exc:
        LOGGER.warning(f"miniapp revoke invite link failed chat={chat_id}: {exc}")


async def _send_invite_link_to_invitee(invitee_tg: int, inviter_name: str, invite_link: str, expire_hours: int) -> None:
    text = (
        f"你收到来自 {inviter_name} 的 Emby 群组邀请。\n\n"
        f"邀请链接：{invite_link}\n\n"
        f"该链接仅供当前 Telegram 账号使用，约 {expire_hours} 小时内有效，入群后会自动失效。"
    )
    await bot.send_message(chat_id=int(invitee_tg), text=text)


async def _send_account_open_notice(invitee_tg: int, inviter_name: str, days: int) -> None:
    text = (
        f"你收到来自 {inviter_name} 的 Emby 注册资格。\n\n"
        f"注册天数：{int(days)} 天\n\n"
        "请私聊机器人发送 /start，然后点击“注册”完成开通。"
    )
    await bot.send_message(chat_id=int(invitee_tg), text=text)


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


async def _ensure_target_user_in_group(invitee_tg: int, settings: dict) -> None:
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
                f"check invite target {label.lower()} member failed chat={normalized_chat_id} tg={invitee_tg}: {exc}"
            )
            raise HTTPException(status_code=400, detail=f"被申请人不在目标{label}里呢，不能提交开通申请啦~") from exc
        if not _telegram_member_is_active(member):
            raise HTTPException(status_code=400, detail=f"被申请人不在目标{label}里呢，不能提交开通申请啦~")


def is_admin_user_id(user_id: int) -> bool:
    normalized_admins = set()
    for item in admins:
        try:
            normalized_admins.add(int(item))
        except (TypeError, ValueError):
            continue

    try:
        return int(user_id) == int(owner) or int(user_id) in normalized_admins
    except (TypeError, ValueError):
        return False


def _local_test_telegram_user(init_data: str) -> dict | None:
    if str(os.getenv("PIVKEYU_LOCAL_TEST_AUTH", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    raw = str(init_data or "").strip()
    if not raw.startswith("local_test:"):
        return None

    parts = raw.split(":", 3)
    try:
        user_id = int(parts[1])
    except (IndexError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="本地测试用户格式无效") from None

    if user_id <= 0:
        raise HTTPException(status_code=401, detail="本地测试用户 ID 无效")

    username = str(parts[2] if len(parts) > 2 else "local_test").strip().lstrip("@") or "local_test"
    first_name = str(parts[3] if len(parts) > 3 else "本地测试用户").strip() or "本地测试用户"
    return {
        "id": user_id,
        "username": username[:64],
        "first_name": first_name[:80],
        "last_name": "",
        "auth": "local_test",
    }


def verify_init_data(init_data: str) -> dict:
    local_test_user = _local_test_telegram_user(init_data)
    if local_test_user is not None:
        matched_block = find_bot_access_block(
            tg=local_test_user.get("id"),
            username=local_test_user.get("username"),
        )
        if matched_block is not None:
            raise HTTPException(status_code=404, detail="Not Found")
        return {"user": local_test_user, "auth": "local_test"}

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    their_hash = parsed.pop("hash", None)

    if not their_hash:
        raise HTTPException(status_code=400, detail="本女仆没收到小程序签名参数哦~")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), sha256).digest()
    our_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), sha256).hexdigest()

    if not hmac.compare_digest(our_hash, their_hash):
        raise HTTPException(status_code=403, detail="小程序数据校验失败了...才不是本女仆的问题！")

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="小程序认证时间格式无效。") from exc
    now = int(time())
    if auth_date <= 0:
        raise HTTPException(status_code=400, detail="小程序认证数据缺少有效时间。")
    if auth_date > now + 60:
        raise HTTPException(status_code=401, detail="小程序认证时间异常，请重新进入页面。")
    if now - auth_date > api_config.webapp_auth_max_age:
        raise HTTPException(status_code=401, detail="小程序数据过期了啦，重新进入页面吧~")

    user_data = parsed.get("user")
    if not user_data:
        raise HTTPException(status_code=400, detail="本女仆没收到小程序用户信息呢...")

    parsed["user"] = json.loads(user_data)
    matched_block = find_bot_access_block(
        tg=parsed["user"].get("id"),
        username=parsed["user"].get("username"),
    )
    if matched_block is not None:
        raise HTTPException(status_code=404, detail="Not Found")
    return parsed


@router.post("/bootstrap")
async def bootstrap(payload: MiniAppInitRequest):
    verified = await run_in_threadpool(verify_init_data, payload.init_data)
    telegram_user = verified["user"]
    account, plugins = await asyncio.gather(
        run_in_threadpool(sql_get_emby, telegram_user["id"]),
        run_in_threadpool(list_miniapp_plugins),
    )
    invite_bundle = await run_in_threadpool(_public_invite_bundle, int(telegram_user["id"]), account)
    is_admin = is_admin_user_id(telegram_user["id"])
    plugins = [
        plugin
        for plugin in plugins
        if plugin.get("enabled") and plugin.get("loaded") and plugin.get("web_registered")
    ]
    bottom_nav = [
        {
            "id": "home",
            "label": "主页",
            "path": "/miniapp",
            "icon": "🏠",
        }
    ]

    for plugin in plugins:
        plugin_visible = bool(config.plugin_nav.get(plugin["id"], plugin.get("bottom_nav_default", False)))
        if plugin.get("miniapp_path") and plugin_visible:
            bottom_nav.append(
                {
                    "id": plugin["id"],
                    "label": plugin.get("miniapp_label") or plugin["name"],
                    "path": plugin["miniapp_path"],
                    "icon": plugin.get("miniapp_icon") or "✨",
                }
            )

    return {
        "code": 200,
        "data": {
            "telegram_user": telegram_user,
            "account": None if account is None else serialize_emby_user(account),
            "invite": invite_bundle,
            "permissions": {
                "is_admin": is_admin,
                "admin_url": "/admin" if is_admin else None,
            },
            "meta": {
                "brand": ranks.logo,
                "currency": pivkeyu,
                "plugins": plugins,
                "bottom_nav": bottom_nav,
            },
        },
    }


@router.post("/invites/create")
async def create_user_invite(payload: MiniAppInviteCreateRequest):
    verified = await run_in_threadpool(verify_init_data, payload.init_data)
    telegram_user = verified["user"]
    user_id = int(telegram_user["id"])
    invitee_tg = int(payload.invitee_tg)

    def _prepare_invite_request():
        account = sql_get_emby(user_id)
        settings = get_invite_settings()
        if not settings.get("enabled"):
            raise HTTPException(status_code=403, detail="主人还没开启邀请功能呢~")
        group_count = available_invite_credit_count(user_id, credit_type=INVITE_CREDIT_TYPE_GROUP)
        if not has_viewing_access(account) and group_count <= 0:
            raise HTTPException(status_code=403, detail="哼，只有拥有 Emby 观影资格或可用入群资格的人才能发送邀请啦~")
        if group_count <= 0:
            raise HTTPException(status_code=400, detail="你当前没有可用的入群资格呢...想邀请别人？先看看自己够不够格啦~")
        target_chat_id = settings.get("target_chat_id")
        if not target_chat_id:
            raise HTTPException(status_code=400, detail="主人还没配置邀请目标群组呢...催催主人吧")
        return account, settings, int(target_chat_id)

    account, settings, target_chat_id = await run_in_threadpool(_prepare_invite_request)

    invite_link = ""
    record = None
    try:
        invite_link, expires_at, link_name = await _create_targeted_invite_link(
            int(target_chat_id),
            invitee_tg,
            int(settings.get("expire_hours") or 24),
        )
        record = await run_in_threadpool(
            create_invite_record,
            inviter_tg=user_id,
            invitee_tg=invitee_tg,
            target_chat_id=target_chat_id,
            invite_link=invite_link,
            link_name=link_name,
            expires_at=expires_at,
            created_by_tg=user_id,
            note=payload.note or "",
        )
        inviter_name = _telegram_user_label(telegram_user)
        await _send_invite_link_to_invitee(
            invitee_tg,
            inviter_name,
            invite_link,
            int(settings.get("expire_hours") or 24),
        )
    except ValueError as exc:
        await _safe_revoke_invite_link(target_chat_id, invite_link)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        await _safe_revoke_invite_link(target_chat_id, invite_link)
        if record:
            await run_in_threadpool(cancel_pending_invite_record, record["id"], reason=str(exc))
        LOGGER.warning(f"create user invite failed inviter={user_id} invitee={invitee_tg}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        await _safe_revoke_invite_link(target_chat_id, invite_link)
        if record:
            await run_in_threadpool(cancel_pending_invite_record, record["id"], reason="私聊发送邀请链接失败，已自动撤销")
        LOGGER.warning(f"create user invite failed inviter={user_id} invitee={invitee_tg}: {exc}")
        raise HTTPException(status_code=500, detail="邀请链接生成或发送失败了...让对方先私聊启动本女仆啦！") from exc

    return {
        "code": 200,
        "data": {
            "record": _public_invite_record(record),
            "invite": await run_in_threadpool(_public_invite_bundle, user_id, account),
        },
    }


@router.post("/invites/account-open/create")
async def create_account_open_invite(payload: MiniAppInviteCreateRequest):
    verified = await run_in_threadpool(verify_init_data, payload.init_data)
    telegram_user = verified["user"]
    user_id = int(telegram_user["id"])
    invitee_tg = int(payload.invitee_tg)

    def _prepare_account_open_request():
        account = sql_get_emby(user_id)
        settings = get_invite_settings()
        if not settings.get("enabled"):
            raise HTTPException(status_code=403, detail="主人还没开启邀请功能呢~")
        if not has_viewing_access(account):
            raise HTTPException(status_code=403, detail="哼，只有拥有 Emby 观影资格的人才能提交开通申请啦~")
        return account, settings

    account, settings = await run_in_threadpool(_prepare_account_open_request)
    await _ensure_target_user_in_group(invitee_tg, settings)
    try:
        record = await run_in_threadpool(
            create_account_open_invite_record,
            inviter_tg=user_id,
            invitee_tg=invitee_tg,
            created_by_tg=user_id,
            note=payload.note or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        LOGGER.warning(f"create account open invite failed inviter={user_id} invitee={invitee_tg}: {exc}")
        raise HTTPException(status_code=500, detail="开通申请提交失败了...才不是本女仆的错！稍后重试啦~") from exc

    return {
        "code": 200,
        "data": {
            "record": _public_invite_record(record),
            "invite": await run_in_threadpool(_public_invite_bundle, user_id, account),
        },
    }
