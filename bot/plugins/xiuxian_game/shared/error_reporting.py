from __future__ import annotations

import traceback
from typing import Any

from fastapi import Request

from bot.sql_helper.sql_xiuxian import create_error_log

from .request_helpers import actor_from_request


def operation_name_from_request(request: Request) -> str:
    path = str(request.url.path or "").strip()
    if not path:
        return "未知操作"
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[-1].isdigit():
        parts = parts[:-1]
    if not parts:
        return path
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1]


def record_request_error(
    request: Request,
    exc: Exception,
    *,
    status_code: int,
    level: str,
) -> None:
    try:
        actor = actor_from_request(request)
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:12000]
        create_error_log(
            tg=actor.get("tg"),
            username=actor.get("username"),
            display_name=actor.get("display_name"),
            scope=actor.get("scope") or "user",
            level=level,
            operation=operation_name_from_request(request),
            method=request.method,
            path=str(request.url.path or "")[:255] or None,
            status_code=status_code,
            message=str(exc) or exc.__class__.__name__,
            detail=detail,
        )
    except Exception:
        # 不要让错误落库再次触发二次异常导致接口返回失败。
        pass


__all__ = ["operation_name_from_request", "record_request_error"]
