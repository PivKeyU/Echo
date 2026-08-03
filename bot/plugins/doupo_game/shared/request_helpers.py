from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

from fastapi import HTTPException, Request

from bot.plugins.sdk import verify_admin_credential, verify_telegram_user
from bot.sql_helper.sql_doupo import upsert_profile_identity
from bot.sql_helper.sql_xiuxian.web_auth import authenticate_xiuxian_web_session
from bot.web.api.miniapp import is_admin_user_id


def _upsert_doupo_profile_identity(user: dict[str, Any]) -> None:
    display_name = " ".join(
        part for part in [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()] if part
    ).strip()
    username = str(user.get("username") or "").strip().lstrip("@")
    upsert_profile_identity(int(user.get("id") or 0), display_name=display_name or None, username=username or None)


def verify_user_from_init_data(init_data: str) -> dict[str, Any]:
    return verify_telegram_user(init_data, on_verified=_upsert_doupo_profile_identity)


def verify_user_from_auth(init_data: str = "", session_token: str = "") -> dict[str, Any]:
    raw_init = str(init_data or "").strip()
    raw_session = str(session_token or "").strip()
    if raw_init.startswith("web_session:"):
        raw_session = raw_init.removeprefix("web_session:").strip()
        raw_init = ""
    if not raw_session:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="请先注册或登录游戏账号，并完成 Telegram 绑定")
    try:
        account = authenticate_xiuxian_web_session(raw_session)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail=str(exc)) from exc
    tg = int(account.get("tg") or 0)
    if tg <= 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="完成 Telegram 绑定后即可进入斗破。")
    if raw_init:
        telegram_user = verify_user_from_init_data(raw_init)
        if int(telegram_user.get("id") or 0) != tg:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="当前 Telegram 与游戏账号绑定身份不一致")
        return telegram_user
    user = {
        "id": tg,
        "username": str(account.get("telegram_username") or "").strip().lstrip("@"),
        "first_name": str(
            account.get("telegram_display_name")
            or account.get("display_name")
            or account.get("username")
            or "游戏账号"
        ).strip(),
        "last_name": "",
        "auth": "web_session",
    }
    _upsert_doupo_profile_identity(user)
    return user


def verify_admin_from_credential(token: str | None, init_data: str | None) -> dict[str, Any]:
    raw_init_data = str(init_data or "").strip()
    if not raw_init_data.startswith("web_session:"):
        return verify_admin_credential(token, init_data)

    if token:
        try:
            return verify_admin_credential(token, None)
        except HTTPException:
            pass

    session_token = raw_init_data.removeprefix("web_session:").strip()
    try:
        account = authenticate_xiuxian_web_session(session_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    tg = int(account.get("tg") or 0)
    if tg <= 0:
        raise HTTPException(status_code=403, detail="游戏账号尚未绑定 Telegram")
    if not is_admin_user_id(tg):
        raise HTTPException(status_code=403, detail="当前绑定的 Telegram 账号没有后台权限")
    return {
        "id": tg,
        "username": str(account.get("telegram_username") or "").strip().lstrip("@"),
        "first_name": str(
            account.get("telegram_display_name")
            or account.get("display_name")
            or account.get("username")
            or "管理员"
        ).strip(),
        "last_name": "",
        "auth": "web_session",
    }


def extract_init_data_from_body_bytes(content_type: str, body: bytes) -> str | None:
    if not body:
        return None
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        value = str(payload.get("init_data") or "").strip()
        return value or None
    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
        values = parsed.get("init_data") or []
        if values:
            value = str(values[0] or "").strip()
            return value or None
    return None


def actor_from_request(request: Request) -> dict[str, Any]:
    scope = "admin" if "/admin-api/" in str(request.url.path or "") else "user"
    init_data = getattr(request.state, "doupo_init_data", None) or request.headers.get("x-telegram-init-data")
    if not init_data:
        return {"scope": scope}
    try:
        user = verify_telegram_user(init_data)
    except Exception:
        return {"scope": scope}
    return {
        "scope": scope,
        "tg": int(user.get("id") or 0) or None,
        "username": str(user.get("username") or "").strip() or None,
        "display_name": " ".join(
            part for part in [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()] if part
        ).strip()
        or None,
    }
