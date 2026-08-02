#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
__init__.py -
Author:susu
Date:2024/8/27
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from secrets import compare_digest

from bot import LOGGER, api as config_api, owner

from .admin import router as admin_router
from .ban_playlist import route as ban_playlist_route
from .login import router as login_router
from .miniapp import is_admin_user_id, router as miniapp_router, verify_init_data
from .user_info import route as user_info_route
from .webhook.client_filter import router as client_filter_router

emby_api_route = APIRouter(prefix="/emby", tags=["对接 Emby 的接口"])
user_api_route = APIRouter(prefix="/user", tags=["对接用户信息的接口"])
auth_api_route = APIRouter(prefix="/auth", tags=["用户认证接口"])
admin_api_route = APIRouter(prefix="/admin-api", tags=["后台管理"])
miniapp_api_route = APIRouter(tags=["小程序"])


def _resolve_token(request: Request) -> str | None:
    token = (
        request.headers.get("x-api-token")
        or request.headers.get("x-admin-token")
    )
    if token:
        return token

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _resolve_telegram_init_data(request: Request) -> str | None:
    return request.headers.get("x-telegram-init-data")


async def verify_token(request: Request):
    try:
        expected_token = str(config_api.access_token or "").strip()
        if not expected_token:
            LOGGER.error("api.access_token 未配置，已拒绝通用 API 请求")
            raise HTTPException(status_code=503, detail="API 访问令牌尚未配置。")
        token = _resolve_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="本女仆没看到访问令牌呢...")
        if not compare_digest(str(token), expected_token):
            LOGGER.warning("Invalid token attempt")
            raise HTTPException(status_code=403, detail="这个令牌不对啦，本女仆不认识！")
        return True
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.error(f"Token verification error: {exc}")
        raise HTTPException(status_code=500, detail="令牌校验出错了...才不是本女仆的问题！")


async def verify_admin_token(request: Request):
    token = _resolve_token(request)
    expected_token = str(config_api.admin_token or "").strip()
    init_data = _resolve_telegram_init_data(request)

    if token and expected_token and compare_digest(str(token), expected_token):
        request.state.admin_auth = "token"
        request.state.admin_user = {"id": owner}
        return True

    if init_data:
        verified = verify_init_data(init_data)
        telegram_user = verified["user"]
        if is_admin_user_id(telegram_user["id"]):
            request.state.admin_auth = "telegram"
            request.state.admin_user = telegram_user
            return True

        LOGGER.warning(f"Telegram user {telegram_user['id']} tried to access admin API without admin rights")
        raise HTTPException(status_code=403, detail="哼，你这个账号没有后台权限啦！")

    if token:
        LOGGER.warning("Invalid admin token attempt")
        raise HTTPException(status_code=403, detail="后台令牌无效呢...才不给你进！")

    raise HTTPException(status_code=401, detail="本女仆没收到后台认证信息哦~")


emby_api_route.include_router(
    ban_playlist_route,
    dependencies=[Depends(verify_token)],
)
emby_api_route.include_router(
    client_filter_router,
    dependencies=[Depends(verify_token)]
)
user_api_route.include_router(
    user_info_route,
    dependencies=[Depends(verify_token)]
)
auth_api_route.include_router(
    login_router,
    dependencies=[Depends(verify_token)]
)
admin_api_route.include_router(
    admin_router,
    dependencies=[Depends(verify_admin_token)]
)
miniapp_api_route.include_router(
    miniapp_router,
)
