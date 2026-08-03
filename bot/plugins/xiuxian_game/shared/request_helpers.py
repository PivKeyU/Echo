from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from typing import Any

from fastapi import HTTPException, Request, UploadFile

from bot.plugins.sdk import public_url_root, verify_admin_credential, verify_telegram_user
from bot.sql_helper.sql_xiuxian import (
    authenticate_xiuxian_web_session,
    get_xiuxian_settings,
    has_image_upload_permission,
    upsert_profile,
)
from bot.web.api.miniapp import is_admin_user_id

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PLUGIN_ROOT.parent.parent.parent / "data"
UPLOAD_DIR = DATA_DIR / "xiuxian_uploads"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _upsert_xiuxian_profile_identity(user: dict[str, Any]) -> None:
    display_name = " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part).strip()
    upsert_fields = {}
    if display_name:
        upsert_fields["display_name"] = display_name
    if user.get("username"):
        upsert_fields["username"] = str(user["username"]).lstrip("@")
    if upsert_fields:
        upsert_profile(int(user["id"]), **upsert_fields)


def _web_session_token_from_init_data(init_data: str | None) -> str | None:
    raw = str(init_data or "").strip()
    if not raw.startswith("web_session:"):
        return None
    token = raw.removeprefix("web_session:").strip()
    return token or None


def _telegram_user_from_web_session(init_data: str | None) -> dict[str, Any] | None:
    token = _web_session_token_from_init_data(init_data)
    if not token:
        return None
    try:
        account = authenticate_xiuxian_web_session(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    tg = int(account.get("tg") or 0)
    if tg <= 0:
        raise HTTPException(status_code=403, detail="网页账号尚未绑定 Telegram，请先完成绑定")
    username = str(account.get("telegram_username") or "").strip().lstrip("@")
    display_name = str(account.get("telegram_display_name") or account.get("display_name") or "").strip()
    return {
        "id": tg,
        "username": username,
        "first_name": display_name or str(account.get("display_name") or "").strip() or username or str(tg),
        "last_name": "",
        "auth": "web_session",
        "web_account_id": account.get("id"),
    }


def verify_user_from_init_data(init_data: str) -> dict[str, Any]:
    web_user = _telegram_user_from_web_session(init_data)
    if web_user is None:
        raise HTTPException(status_code=401, detail="请先注册或登录游戏账号，并完成 Telegram 绑定")
    _upsert_xiuxian_profile_identity(web_user)
    return web_user


def verify_admin_from_credential(token: str | None, init_data: str | None) -> dict[str, Any]:
    return verify_admin_credential(token, init_data)


def extract_init_data_from_body_bytes(content_type: str, body: bytes) -> str | None:
    if not body:
        return None
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        return str(payload.get("init_data") or "").strip() or None
    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
        values = parsed.get("init_data")
        if values:
            return str(values[0] or "").strip() or None
    return None


def actor_from_request(request: Request) -> dict[str, Any]:
    scope = "admin" if "/admin-api/" in str(request.url.path or "") else "user"
    init_data = getattr(request.state, "xiuxian_init_data", None)
    if not init_data:
        init_data = request.headers.get("x-telegram-init-data")
    if not init_data:
        return {"scope": scope}
    try:
        user = verify_user_from_init_data(init_data)
    except Exception:
        return {"scope": scope}
    return {
        "scope": scope,
        "tg": int(user.get("id") or 0) or None,
        "username": str(user.get("username") or "").strip() or None,
        "display_name": str(user.get("first_name") or user.get("last_name") or "").strip() or None,
    }


def can_user_upload_images(user_id: int) -> tuple[bool, str]:
    if is_admin_user_id(user_id):
        return True, ""
    settings = get_xiuxian_settings()
    if bool(settings.get("allow_non_admin_image_upload", False)):
        return True, ""
    if has_image_upload_permission(user_id):
        return True, ""
    return False, "当前未开放普通用户上传图片，请联系主人开启总开关或单独授权。"


def sanitize_upload_folder(folder: str | None) -> str:
    raw = (folder or "misc").strip().replace("\\", "/")
    parts = []
    for part in raw.split("/"):
        cleaned = "".join(ch for ch in part.lower() if ch.isalnum() or ch in {"-", "_"})
        if cleaned:
            parts.append(cleaned)
    return "/".join(parts[:3]) or "misc"


def public_url_root_from(base_url: str | None = None) -> str:
    return public_url_root(base_url)


def resolve_group_image_source(image_url: str | None) -> str | Path | None:
    if not image_url:
        return None
    image_url = str(image_url).strip()
    if not image_url:
        return None
    upload_path = image_url
    if image_url.startswith("http://") or image_url.startswith("https://"):
        parsed = urlsplit(image_url)
        upload_path = parsed.path or image_url
        if not upload_path.startswith("/plugins/xiuxian/uploads/"):
            return image_url
    if upload_path.startswith("/plugins/xiuxian/uploads/"):
        relative_path = upload_path.removeprefix("/plugins/xiuxian/uploads/").strip("/")
        local_path = UPLOAD_DIR.joinpath(*[part for part in relative_path.split("/") if part])
        if local_path.exists():
            return str(local_path)
        public_root = public_url_root_from()
        if public_root:
            return f"{public_root}{upload_path}"
    return image_url


async def save_uploaded_image(file: UploadFile, folder: str, base_url: str | None = None) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 jpg、png、webp、gif 图片格式")

    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        suffix = mapping.get(content_type, ".jpg")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="上传的图片不能为空")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="图片大小不能超过 8MB")

    subdir = sanitize_upload_folder(folder)
    target_dir = UPLOAD_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    target = target_dir / filename
    target.write_bytes(payload)
    relative = Path(subdir) / filename
    relative_url = f"/plugins/xiuxian/uploads/{relative.as_posix()}"
    public_url = public_url_root_from(base_url)
    return {
        "name": filename,
        "size": len(payload),
        "url": f"{public_url}{relative_url}" if public_url else relative_url,
        "relative_url": relative_url,
    }
