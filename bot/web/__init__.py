#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
__init__.py -
Author:susu
Date:2024/8/27
"""
import asyncio
import errno
import os
from time import perf_counter
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from bot import LOGGER, api as config_api
from bot.func_helper.emby import emby
from bot.func_helper.moviepilot import close_moviepilot_session
from bot.func_helper.redis_cache import get_status as get_redis_status
from bot.func_helper.runtime import get_or_create_event_loop
from bot.func_helper.telegram_webapp import configure_chat_menu_button
from bot.plugins import has_loaded_plugins, load_plugins, register_web_plugins

from .api import admin_api_route, auth_api_route, emby_api_route, miniapp_api_route, user_api_route

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


class Web:
    def __init__(self):
        self.app: FastAPI = FastAPI(title="Echo Web API")
        self.web_api = None
        self.start_api = None
        self._serve_finished: asyncio.Event | None = None
        self._start_task: asyncio.Task | None = None
        self._api_initialized = False
        self._shutdown_registered = False
        self._stop_requested = False

    async def _configure_runtime_limits(self) -> None:
        tokens = _env_int("PIVKEYU_WEB_THREADPOOL_TOKENS", 96, minimum=24, maximum=512)
        try:
            import anyio

            limiter = anyio.to_thread.current_default_thread_limiter()
            if int(limiter.total_tokens) != tokens:
                limiter.total_tokens = tokens
                LOGGER.info(f"【API服务】Web线程池并发调整为 {tokens}")
        except Exception as exc:
            LOGGER.warning(f"【API服务】Web线程池并发调整失败: {exc}")

    def init_api(self):
        if self._api_initialized:
            return
        self._api_initialized = True
        slow_request_ms = _env_int("PIVKEYU_WEB_SLOW_REQUEST_MS", 2000, minimum=200, maximum=120000)

        @self.app.middleware("http")
        async def slow_request_logger(request, call_next):
            started_at = perf_counter()
            try:
                return await call_next(request)
            finally:
                elapsed_ms = int((perf_counter() - started_at) * 1000)
                path = str(request.url.path or "")
                if elapsed_ms >= slow_request_ms and (
                    path.startswith("/miniapp")
                    or path.startswith("/miniapp-api")
                    or path.startswith("/plugins/")
                ):
                    LOGGER.warning(
                        f"【API慢请求】{request.method} {path} 耗时 {elapsed_ms}ms"
                    )

        self.app.include_router(emby_api_route)
        self.app.include_router(user_api_route)
        self.app.include_router(auth_api_route)
        self.app.include_router(admin_api_route)
        self.app.include_router(miniapp_api_route)

        if STATIC_DIR.exists():
            self.app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

            @self.app.get("/", include_in_schema=False)
            async def root():
                return {
                    "ok": True,
                    "admin": "/admin",
                    "miniapp": "/miniapp",
                    "health": "/health",
                }

            @self.app.get("/health", include_in_schema=False)
            async def health():
                redis_status = get_redis_status()
                return {
                    "ok": True,
                    "redis": {
                        "enabled": bool(redis_status.get("enabled")),
                        "available": bool(redis_status.get("available")),
                    },
                }

            @self.app.get("/admin", include_in_schema=False)
            async def admin_page():
                return FileResponse(STATIC_DIR / "admin.html")

            @self.app.get("/miniapp", include_in_schema=False)
            async def miniapp_page():
                return FileResponse(STATIC_DIR / "miniapp.html")

        allowed_origins = [str(origin) for origin in (config_api.allow_origins or []) if str(origin).strip()]
        if "*" in allowed_origins:
            parsed_public_url = urlsplit(str(config_api.public_url or "").strip())
            public_origin = (
                f"{parsed_public_url.scheme}://{parsed_public_url.netloc}"
                if parsed_public_url.scheme and parsed_public_url.netloc
                else None
            )
            allowed_origins = [public_origin] if public_origin else []
            LOGGER.warning("【API服务】allow_origins 不再接受通配符，已收紧为 public_url 同源访问")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        if not self._shutdown_registered:
            self._shutdown_registered = True

            @self.app.on_event("shutdown")
            async def close_external_clients():
                await emby.shutdown()
                await close_moviepilot_session()

    async def start(self):
        if not config_api.status:
            LOGGER.info("【API服务】未配置，跳过")
            return
        LOGGER.info("【API服务】检测到配置，开始启动")
        if self._stop_requested:
            LOGGER.info("【API服务】在启动前收到停止请求，跳过启动")
            return
        import uvicorn

        await self._configure_runtime_limits()
        self.init_api()
        redis_status = get_redis_status()
        if redis_status.get("enabled"):
            if redis_status.get("available"):
                LOGGER.info("【API服务】Redis 缓存已连接")
            else:
                LOGGER.warning("【API服务】Redis 已启用但未连接，热数据将回退进程内缓存/数据库直连")
        # Bot 侧插件在 main.py 启动时已加载；此处仅注册 Web 路由。
        if not has_loaded_plugins():
            LOGGER.warning("【API服务】未检测到已加载插件，补执行 load_plugins()")
            load_plugins()
        register_web_plugins(self.app)
        if self._stop_requested:
            LOGGER.info("【API服务】注册路由后收到停止请求，跳过启动")
            return
        self.web_api = uvicorn.Server(
            config=uvicorn.Config(
                self.app,
                host=config_api.http_url,
                port=config_api.http_port,
                access_log=False,
                # Bound the graceful drain: without a timeout, a stuck
                # connection blocks Server.shutdown() (and therefore stop())
                # forever instead of letting lifespan shutdown proceed.
                timeout_graceful_shutdown=30,
            )
        )
        self._serve_finished = asyncio.Event()
        LOGGER.info("【API服务】启动成功，进入持续服务状态")
        try:
            # Server.serve() owns the complete lifespan: startup, request loop,
            # and shutdown.  This is intentionally awaited by the task created
            # below, rather than during module import.
            await self.web_api.serve()
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                LOGGER.error(f"【API服务】端口 {config_api.http_port} 已被占用，请修改配置文件")
            LOGGER.error("【API服务】启动失败")
            raise
        finally:
            if self._serve_finished is not None:
                self._serve_finished.set()
            LOGGER.info("API 服务已停止")

    async def stop(self):
        """Request and await uvicorn's graceful shutdown."""
        self._stop_requested = True
        task = self._start_task
        if self.web_api is None:
            if task is not None and not task.done():
                # start() checks _stop_requested before binding the socket, so
                # waiting here cannot accidentally start a new server.  Consume
                # startup failures (e.g. EADDRINUSE) so they do not escape into
                # the caller and abort later shutdown cleanup.
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    LOGGER.error(f"【API服务】后台任务结束时发生异常: {exc}")
            elif task is not None:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    LOGGER.error(f"【API服务】后台任务结束时发生异常: {exc}")
            return
        LOGGER.info("正在停止 API 服务...")
        self.web_api.should_exit = True
        if self._serve_finished is not None:
            await self._serve_finished.wait()
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                LOGGER.error(f"【API服务】后台任务结束时发生异常: {exc}")
        elif task is not None:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                LOGGER.error(f"【API服务】后台任务结束时发生异常: {exc}")



check = Web()

loop = get_or_create_event_loop()
check._start_task = loop.create_task(check.start(), name="web-api-start")


def _report_web_task(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    try:
        task.result()
    except Exception as exc:
        LOGGER.error(f"【API服务】后台服务任务异常退出: {exc}")


check._start_task.add_done_callback(_report_web_task)
if str(os.getenv("PIVKEYU_WEB_ONLY", "")).strip().lower() not in {"1", "true", "yes", "on"}:
    loop.create_task(configure_chat_menu_button())
