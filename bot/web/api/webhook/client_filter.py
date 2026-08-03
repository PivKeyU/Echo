from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
from datetime import datetime
from hashlib import sha256
from typing import Any, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bot import LOGGER, bot, config
from bot.func_helper import redis_cache
from bot.func_helper.emby import emby
from bot.sql_helper.sql_emby import Emby, sql_get_emby, sql_update_emby

router = APIRouter()

DEFAULT_BLOCKED_CLIENTS = [
    r".*curl.*", r".*wget.*", r".*python.*", r".*spider.*", r".*crawler.*",
    r".*scraper.*", r".*downloader.*", r".*aria2.*", r".*youtube-dl.*",
    r".*yt-dlp.*", r".*ffmpeg.*", r".*vlc.*",
]


class _WebhookSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Id: str = Field(..., min_length=1, max_length=128)
    Client: str = Field(..., min_length=1, max_length=256)


class _WebhookUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Id: str = Field(..., min_length=1, max_length=128)
    Name: str = Field(default="", max_length=256)


class _WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Event: str = Field(..., min_length=1, max_length=128)
    Session: _WebhookSession
    User: _WebhookUser


_WEBHOOK_MAX_BODY_BYTES = max(
    1024,
    min(int(os.getenv("PIVKEYU_WEBHOOK_MAX_BODY_BYTES", "1048576") or 1048576), 16 * 1024 * 1024),
)
_REPLAY_LOCK = threading.Lock()
_RECENT_SIGNATURES: dict[str, float] = {}
_LISTEN_EVENTS = {
    "user.authenticated",
    "user.authenticationfailed",
    "playback.start",
    "playback.progress",
    "playback.stop",
    "session.start",
}


def _webhook_secret() -> str:
    configured = getattr(config, "webhook_secret", None)
    if not configured and getattr(config, "api", None) is not None:
        configured = getattr(config.api, "webhook_secret", None)
    return str(configured or os.getenv("PIVKEYU_WEBHOOK_SECRET", "")).strip()


def _replay_window() -> int:
    configured = getattr(getattr(config, "api", None), "webhook_replay_window", None)
    raw = configured or os.getenv("PIVKEYU_WEBHOOK_REPLAY_WINDOW", "300")
    try:
        return max(1, min(int(raw), 86400))
    except (TypeError, ValueError):
        return 300


def _verify_webhook_signature(request: Request, body: bytes) -> None:
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret 未配置")

    timestamp = (
        request.headers.get("x-echo-webhook-timestamp")
        or request.headers.get("x-pivkeyu-webhook-timestamp")  # 旧版兼容
        or request.headers.get("x-webhook-timestamp")
        or request.headers.get("x-emby-timestamp")
    )
    signature = (
        request.headers.get("x-echo-webhook-signature")
        or request.headers.get("x-pivkeyu-webhook-signature")  # 旧版兼容
        or request.headers.get("x-webhook-signature")
        or request.headers.get("x-emby-signature")
    )
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Webhook 签名缺失")
    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Webhook 时间戳无效") from None
    now = int(time.time())
    replay_window = _replay_window()
    if abs(now - timestamp_int) > replay_window:
        raise HTTPException(status_code=401, detail="Webhook 已过期")

    # The canonical signing input is deliberately unambiguous: decimal
    # timestamp, a dot, then the exact raw request body.
    try:
        signed = timestamp.encode("ascii", "strict") + b"." + body
    except UnicodeEncodeError:
        raise HTTPException(status_code=400, detail="Webhook 时间戳无效") from None
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    supplied = signature.strip().lower()
    if supplied.startswith("sha256="):
        supplied = supplied[7:]
    # compare_digest only accepts ASCII str; non-ASCII header values (ASGI
    # decodes headers as latin-1) must be rejected as invalid, not crash.
    try:
        valid = hmac.compare_digest(
            supplied.encode("ascii", "strict"), expected.encode("ascii", "strict")
        )
    except UnicodeEncodeError:
        valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="Webhook 签名无效")

    replay_key = sha256(f"{timestamp}:{supplied}".encode("ascii", "strict")).hexdigest()
    redis_client = redis_cache.get_client() if redis_cache.redis_enabled() else None
    if redis_client is not None:
        try:
            accepted = redis_client.set(
                redis_cache.build_key("webhook", "replay", replay_key),
                "1",
                nx=True,
                ex=replay_window,
            )
            if not accepted:
                raise HTTPException(status_code=409, detail="Webhook 请求已处理")
            return
        except HTTPException:
            raise
        except Exception as exc:
            LOGGER.warning(f"Webhook Redis 重放保护不可用，回退进程内保护: {exc}")

    # Redis is optional.  The local fallback protects a single worker and is
    # still preferable to accepting the same signed event repeatedly.
    cutoff = float(now - replay_window)
    with _REPLAY_LOCK:
        for key, seen_at in list(_RECENT_SIGNATURES.items()):
            if seen_at < cutoff:
                _RECENT_SIGNATURES.pop(key, None)
        if replay_key in _RECENT_SIGNATURES:
            raise HTTPException(status_code=409, detail="Webhook 请求已处理")
        _RECENT_SIGNATURES[replay_key] = float(now)


async def get_blocked_clients() -> List[str]:
    try:
        blocked_agents = getattr(config, "blocked_clients", DEFAULT_BLOCKED_CLIENTS)
        return blocked_agents if blocked_agents else DEFAULT_BLOCKED_CLIENTS
    except Exception as exc:
        LOGGER.error(f"获取被拦截客户端列表失败: {exc}")
        return DEFAULT_BLOCKED_CLIENTS


async def is_client_blocked(client: str) -> bool:
    if not client:
        return False
    for pattern in await get_blocked_clients():
        try:
            if re.search(pattern, client, flags=re.IGNORECASE):
                return True
        except re.error as exc:
            LOGGER.error(f"正则表达式错误: {pattern} - {exc}")
    return False


async def log_blocked_request(
    user_id: str = None, user_name: str = None, session_id: str = None,
    client_name: str = None, tg_id: int = None, block_success: bool = False,
):
    try:
        block_action = "封禁用户" if block_success else "不封禁用户"
        log_message = (
            f"🚫 拦截可疑请求\n用户ID: {user_id or 'Unknown'}\n"
            f"用户名称: {user_name or 'Unknown'}\n会话ID: {session_id or 'Unknown'}\n"
            f"客户端: {client_name or 'Unknown'}\nTG ID: {tg_id or 'Unknown'}\n"
            f"是否封禁用户: {block_action}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        LOGGER.warning(log_message)
        if getattr(config, "group", None):
            try:
                await bot.send_message(chat_id=config.group[0], text=log_message)
            except Exception as exc:
                LOGGER.error(f"发送拦截通知失败: {exc}")
    except Exception as exc:
        LOGGER.error(f"记录拦截请求失败: {exc}")


async def terminate_blocked_session(session_id: str, client_name: str) -> bool:
    if not session_id:
        return False
    try:
        success = await emby.terminate_session(session_id, f"检测到可疑客户端: {client_name}")
        if success:
            LOGGER.info(f"成功终止可疑会话 {session_id}")
        else:
            LOGGER.error(f"终止会话失败 {session_id}")
        return bool(success)
    except Exception as exc:
        LOGGER.error(f"终止会话异常 {session_id}: {exc}")
        return False


def _safe_user_details(user: Emby | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "tg": user.tg,
        "embyid": user.embyid,
        "name": user.name,
        "lv": user.lv,
    }


@router.post("/webhook/client-filter")
async def handle_client_filter_webhook(request: Request):
    """处理 Emby 用户代理拦截 webhook。"""
    content_length = request.headers.get("content-length")
    try:
        if content_length is not None and int(content_length) > _WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook 请求体过大")
    except ValueError:
        raise HTTPException(status_code=400, detail="Content-Length 无效") from None

    body = await request.body()
    if len(body) > _WEBHOOK_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook 请求体过大")
    _verify_webhook_signature(request, body)
    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type:
            raw_data: Any = json.loads(body.decode("utf-8"))
        else:
            form_data = await request.form()
            raw_data = json.loads(str(form_data.get("data", "")))
        webhook_data = _WebhookPayload.model_validate(raw_data)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, ValidationError):
        raise HTTPException(status_code=400, detail="无效的JSON格式或请求字段") from None

    event = webhook_data.Event
    if event not in _LISTEN_EVENTS:
        return {"status": "ignored", "message": "Not listen event", "event": event}

    session_info = webhook_data.Session
    user_info = webhook_data.User
    user_name = user_info.Name
    emby_id = user_info.Id
    session_id = session_info.Id
    client_name = session_info.Client
    if not client_name:
        return {"status": "ignored", "message": "No Client info found"}

    if not await is_client_blocked(client_name):
        return {
            "status": "allowed", "message": "Client allowed",
            "data": {"client": client_name, "user_id": emby_id, "event": event},
        }

    user_details = sql_get_emby(emby_id)
    action_success = True
    terminate_enabled = bool(getattr(config, "client_filter_terminate_session", True))
    ban_enabled = bool(getattr(config, "client_filter_block_user", False))
    if terminate_enabled:
        action_success = await terminate_blocked_session(session_id, client_name) and action_success

    ban_success = False
    if ban_enabled:
        try:
            ban_success = bool(await emby.emby_change_policy(emby_id=emby_id, disable=True))
        except Exception as exc:
            LOGGER.error(f"封禁 Emby 用户失败 {emby_id}: {exc}")
            ban_success = False
        action_success = ban_success and action_success
        if ban_success and user_details:
            sql_update_emby(Emby.tg == user_details.tg, lv="c")
            user_details.lv = "c"

    await log_blocked_request(
        user_id=emby_id, user_name=user_name, session_id=session_id,
        client_name=client_name, tg_id=user_details.tg if user_details else None,
        block_success=ban_success,
    )
    if not action_success:
        return {
            "status": "error", "message": "Client detected but configured action failed",
            "data": {"user_id": emby_id, "user_name": user_name, "session_id": session_id,
                     "client_name": client_name, "event": event},
        }
    return {
        "status": "blocked", "message": "Client blocked",
        "data": {"user_id": emby_id, "user_name": user_name, "session_id": session_id,
                 "client_name": client_name, "user_details": _safe_user_details(user_details),
                 "event": event, "timestamp": datetime.now().isoformat()},
    }
