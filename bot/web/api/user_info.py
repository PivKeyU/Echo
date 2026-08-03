#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
get_user_info -
Author:susu
Date:2024/8/27
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bot import LOGGER, group, bot
from bot.func_helper.emby import emby
from bot.sql_helper.sql_emby import Emby, sql_adjust_emby_iv, sql_get_emby, sql_update_emby

from . import verify_admin_token, verify_token

route = APIRouter()


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateCreditPayload(_Payload):
    tg: str = Field(min_length=1, max_length=64)
    credit: int


class BanPayload(_Payload):
    query: str = Field(min_length=1, max_length=128)


async def _read_payload(request: Request, model: type[BaseModel]) -> BaseModel:
    """Read JSON or the legacy form ``data`` field, returning a validated model."""
    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type:
            data: Any = await request.json()
            if isinstance(data, str):
                data = json.loads(data)
        else:
            form_data = await request.form()
            raw_data = form_data.get("data")
            data = json.loads(raw_data) if raw_data is not None else {}
    except (json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无效的JSON格式") from None
    try:
        return model.model_validate(data)
    except ValidationError:
        raise HTTPException(status_code=400, detail="参数错误") from None


@route.get("/user_info", dependencies=[Depends(verify_token)])
async def user_info(tg: str = Query(..., min_length=1, max_length=64)):
    user = sql_get_emby(tg)
    if not user:
        return {"code": 404, "message": "用户不存在"}
    return {
        "code": 200,
        "data": {
            "tg": user.tg,
            "iv": user.iv,
            "name": user.name,
            "embyid": user.embyid,
            "lv": user.lv,
            "cr": user.cr,
            "ex": user.ex,
        },
    }


@route.post("/update_credit", dependencies=[Depends(verify_admin_token)])
async def update_credit(request: Request):
    try:
        payload = await _read_payload(request, UpdateCreditPayload)
        tg, credit = payload.tg, payload.credit
        user = sql_get_emby(tg)
        if not user:
            return {"code": 404, "message": "用户不存在"}

        new_iv = sql_adjust_emby_iv(tg, credit)
        if new_iv is None:
            # Distinguish a missing row from an insufficient balance without
            # exposing database details through the API.
            latest = sql_get_emby(tg)
            if latest is None:
                return {"code": 404, "message": "用户不存在"}
            if credit < 0 and int(latest.iv or 0) + credit < 0:
                return {"code": 400, "message": "积分不足"}
            return {"code": 500, "message": "更新失败"}
        return {"code": 200, "data": {"tg": user.tg, "iv": new_iv, "changed": credit}}
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.error(f"更新用户积分失败: {exc}")
        return {"code": 500, "message": "服务器错误"}


@route.post("/ban", dependencies=[Depends(verify_admin_token)])
async def ban_user(request: Request):
    try:
        payload = await _read_payload(request, BanPayload)
        query = payload.query
        user = sql_get_emby(tg=query)
        if not user or not user.embyid:
            return {"code": 404, "message": "用户不存在"}

        disable_emby = await emby.emby_change_policy(emby_id=user.embyid, disable=True)
        if disable_emby:
            user.lv = "c"
            sql_update_emby(Emby.tg == user.tg, lv="c")
            send_notification = f"#BAN通告\n用户 {user.name} (TG: #{user.tg}, EmbyID: {user.embyid}) 已被封禁。"
            LOGGER.info(send_notification)
            await bot.send_message(chat_id=group[0], text=send_notification)
            return {
                "code": 200,
                "data": {"tg": user.tg, "embyid": user.embyid, "name": user.name, "lv": user.lv},
            }
        return {"code": 500, "message": "封禁失败"}
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.error(f"封禁用户失败: {exc}")
        return {"code": 500, "message": "服务器错误"}
