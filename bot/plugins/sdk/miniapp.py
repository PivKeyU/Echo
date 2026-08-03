from __future__ import annotations

import hashlib
import os
from secrets import compare_digest
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from bot import api as api_config, config, owner
from bot.plugins.sdk.memory_cache import get_memory_cache

_BOTTOM_NAV_TTL = max(int(os.getenv("PIVKEYU_BOTTOM_NAV_CACHE_TTL", "45") or 45), 15)
_BOTTOM_NAV_MEMORY_CACHE = get_memory_cache()


def public_url_root(base_url: str | None = None) -> str:
    if api_config.public_url:
        return str(api_config.public_url).rstrip("/")
    return str(base_url or "").rstrip("/")


def build_plugin_url(path: str) -> str | None:
    public_url = public_url_root()
    if not public_url:
        return None
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{public_url}{normalized}"


def _bottom_nav_fingerprint() -> str:
    from bot.plugins import list_miniapp_plugins

    plugin_nav = getattr(config, "plugin_nav", {}) or {}
    parts = ["home:/miniapp"]
    for plugin in list_miniapp_plugins():
        if not plugin.get("enabled") or not plugin.get("loaded") or not plugin.get("web_registered"):
            continue
        plugin_id = str(plugin.get("id") or "").strip()
        miniapp_path = str(plugin.get("miniapp_path") or "").strip()
        if not plugin_id or not miniapp_path:
            continue
        plugin_visible = bool(plugin_nav.get(plugin_id, plugin.get("bottom_nav_default", False)))
        parts.append(
            f"{plugin_id}:{miniapp_path}:{int(plugin_visible)}:"
            f"{plugin.get('miniapp_label') or plugin.get('name') or ''}:{plugin.get('miniapp_icon') or ''}"
        )
    digest = hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()
    return digest[:16]


def build_bottom_nav() -> list[dict[str, str]]:
    from bot.plugins import list_miniapp_plugins

    cache_key = f"bottom_nav:{_bottom_nav_fingerprint()}"
    cached = _BOTTOM_NAV_MEMORY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    items = [
        {
            "id": "home",
            "label": "主页",
            "path": "/miniapp",
            "icon": "🏠",
        }
    ]
    plugin_nav = getattr(config, "plugin_nav", {}) or {}
    for plugin in list_miniapp_plugins():
        if not plugin.get("enabled") or not plugin.get("loaded") or not plugin.get("web_registered"):
            continue
        plugin_visible = bool(plugin_nav.get(plugin["id"], plugin.get("bottom_nav_default", False)))
        if not plugin.get("miniapp_path") or not plugin_visible:
            continue
        items.append(
            {
                "id": plugin["id"],
                "label": plugin.get("miniapp_label") or plugin["name"],
                "path": plugin["miniapp_path"],
                "icon": plugin.get("miniapp_icon") or "◇",
            }
        )
    _BOTTOM_NAV_MEMORY_CACHE.set(cache_key, items, _BOTTOM_NAV_TTL)
    return items


def telegram_display_name(user: dict[str, Any]) -> str:
    display_name = " ".join(
        part
        for part in [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()]
        if part
    ).strip()
    if display_name:
        return display_name[:80]
    username = str(user.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"[:80]
    return str(user.get("id") or "未知用户")[:80]


def _local_test_telegram_user(init_data: str) -> dict[str, Any] | None:
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


def verify_telegram_user(
    init_data: str,
    *,
    on_verified: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from bot.web.api.miniapp import verify_init_data

    local_test_user = _local_test_telegram_user(init_data)
    if local_test_user is not None:
        if on_verified is not None:
            on_verified(local_test_user)
        return local_test_user

    verified = verify_init_data(init_data)
    user = verified["user"]
    if on_verified is not None:
        on_verified(user)
    return user


def verify_admin_credential(token: str | None, init_data: str | None) -> dict[str, Any]:
    from bot.web.api.miniapp import is_admin_user_id

    expected_token = api_config.admin_token or ""
    if token and expected_token and compare_digest(str(token), str(expected_token)):
        return {"id": owner, "auth": "token"}

    if init_data:
        telegram_user = verify_telegram_user(init_data)
        if is_admin_user_id(int(telegram_user["id"])):
            telegram_user["auth"] = "telegram"
            return telegram_user
        raise HTTPException(status_code=403, detail="当前 Telegram 账号没有后台权限")

    raise HTTPException(status_code=401, detail="缺少后台登录凭证")
