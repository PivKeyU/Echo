#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
emotion.py - Emotion 服务端适配器（服务端凭据管理 Emotion）

凭据（integration credential）只由本服务持有，通过 HTTPS/私网 + Bearer 调用
Emotion 的 /integration/v1 控制面。设计约束：

- 不把 bot_token / admin_token / Emotion credential 返回给浏览器、Mini App 或
  普通 Telegram 请求；本模块只在 FastAPI 服务端和机器人后端内部使用。
- 所有写操作携带 X-Request-ID 与 Idempotency-Key，便于 Emotion 侧幂等与审计。
- 超时、重试、错误映射（401/403/404/409/429）统一收敛，调用方只看到
  EmotionApiResult(success, data, error)。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from bot import LOGGER, emotion_cfg


class EmotionApiResult:
    """Emotion integration API 统一结果封装。"""

    __slots__ = ("success", "data", "error", "status")

    def __init__(self, success: bool, data: Any = None, error: str = None, status: int = 0):
        self.success = success
        self.data = data
        self.error = error
        self.status = status

    def __bool__(self):
        return self.success


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 2**31 - 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, min(maximum, int(raw)))
    except (TypeError, ValueError):
        return default


def _credential() -> str:
    return str(emotion_cfg.credential or "").strip()


def emotion_enabled() -> bool:
    """Emotion 联动是否可用：开关开启且凭据与地址均已配置。"""
    if not getattr(emotion_cfg, "status", False):
        return False
    if not _credential():
        return False
    url = str(getattr(emotion_cfg, "url", "") or "").strip()
    return bool(url and (url.startswith("http://") or url.startswith("https://")))


class EmotionService:
    """
    服务端 Emotion 控制面客户端。

    - 认证：Authorization: Bearer <integration credential>
    - 幂等/审计：所有写请求带 X-Request-ID；写请求可带 Idempotency-Key
    - 错误映射：401=凭据无效、403=scope 不足、404=资源不存在、409=冲突/重复、
      429/5xx 可重试
    """

    def __init__(
        self,
        url: str = "",
        credential: str = "",
        timeout: int = 10,
        max_retries: int = 1,
    ):
        self.url = str(url or "").rstrip("/")
        self.credential = str(credential or "")
        self.timeout = aiohttp.ClientTimeout(total=max(1, int(timeout)), connect=min(max(1, int(timeout)), 10))
        self.max_retries = max(0, int(max_retries))
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self._session_idle = asyncio.Event()
        self._session_idle.set()
        self._session_users = 0
        self._closing = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    if self._closing:
                        raise RuntimeError("Emotion 服务正在关闭")
                    self._session_idle.clear()
                    self._session = aiohttp.ClientSession(
                        timeout=self.timeout,
                        headers={
                            "accept": "application/json",
                            "content-type": "application/json",
                            "Authorization": f"Bearer {self.credential}",
                            "User-Agent": "Echo emotion-adapter/1.0",
                        },
                    )
                    self._session_idle.set()
        return self._session

    async def close(self) -> None:
        # Take the lock so a concurrent _get_session() cannot create a fresh
        # session after shutdown has begun (which would leak it).
        async with self._session_lock:
            self._closing = True
            session = self._session
            idle = self._session_users == 0
        if not idle:
            # 等待在途请求完成（与 Embyservice.shutdown 同一模式），
            # 避免关闭会话导致在途请求被中断。
            try:
                await asyncio.wait_for(self._session_idle.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
        if session is not None and not session.closed:
            try:
                await session.close()
            except Exception:
                pass
        async with self._session_lock:
            self._closing = False
    async def shutdown(self) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        idempotency_key: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> EmotionApiResult:
        if not self.url or not self.credential:
            return EmotionApiResult(False, error="Emotion adapter 未配置 url/credential")

        # 与 Embyservice 相同：永远不要把凭据放进 URL。
        endpoint_parts = urlsplit(endpoint)
        endpoint_query = [
            (k, v) for k, v in parse_qsl(endpoint_parts.query, keep_blank_values=True) if k.lower() != "api_key"
        ]
        endpoint = urlunsplit(
            (endpoint_parts.scheme, endpoint_parts.netloc, endpoint_parts.path, urlencode(endpoint_query), endpoint_parts.fragment)
        )
        if params:
            params = {k: v for k, v in params.items() if str(k).lower() != "api_key"}

        url = f"{self.url}{endpoint}"
        safe_url = f"{self.url}{endpoint}"
        sensitive = "/password" in endpoint.lower()

        headers: Dict[str, str] = {}
        rid = request_id or ("emo_" + uuid.uuid4().hex[:16])
        headers["X-Request-ID"] = rid
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            if idempotency_key:
                headers["Idempotency-Key"] = str(idempotency_key)[:255]

        attempts = self.max_retries + 1
        retry_statuses = {429, 500, 502, 503, 504}
        backoff_cap = 30.0
        for attempt in range(attempts):
            try:
                session = await self._get_session()
                async with self._session_lock:
                    self._session_users += 1
                    self._session_idle.clear()
                try:
                    async with session.request(
                        method,
                        url,
                        params=params,
                        json=json_body,
                        headers=headers,
                    ) as response:
                        if response.status in (200, 201, 202, 204):
                            if response.status == 204 or response.content_type != "application/json":
                                await response.read()
                                return EmotionApiResult(True, None, status=response.status)
                            data = await response.json()
                            return EmotionApiResult(True, data, status=response.status)

                        error_msg = self._map_error(response.status)
                        if not sensitive:
                            try:
                                text = await response.text()
                                if text and len(text) <= 512:
                                    error_msg = f"{error_msg}: {text}"
                            except Exception:
                                pass

                        if response.status in retry_statuses and attempt < attempts - 1:
                            delay = min(backoff_cap, 1.0 * (2 ** min(attempt, 5)))
                            LOGGER.warning(f"Emotion 请求失败将重试: {method} {safe_url} - {error_msg}; delay={delay:.1f}s")
                            await asyncio.sleep(delay)
                            continue

                        LOGGER.warning(f"Emotion 请求失败: {method} {safe_url} - {error_msg}")
                        return EmotionApiResult(False, error=error_msg, status=response.status)
                finally:
                    async with self._session_lock:
                        self._session_users = max(0, self._session_users - 1)
                        if self._session_users == 0:
                            self._session_idle.set()
            except asyncio.TimeoutError:
                LOGGER.warning(f"Emotion 请求超时 (尝试 {attempt + 1}/{attempts}): {safe_url}")
                if attempt >= attempts - 1:
                    return EmotionApiResult(False, error="请求超时", status=0)
                await asyncio.sleep(min(backoff_cap, 1.0 * (2 ** min(attempt, 5))))
            except aiohttp.ClientError as exc:
                LOGGER.warning(f"Emotion 网络异常 (尝试 {attempt + 1}/{attempts}): {safe_url} - {exc}")
                if attempt >= attempts - 1:
                    return EmotionApiResult(False, error=f"网络请求失败: {exc}", status=0)
                await asyncio.sleep(min(backoff_cap, 1.0 * (2 ** min(attempt, 5))))
            except Exception as exc:
                LOGGER.error(f"Emotion 未知异常: {safe_url} - {exc}")
                return EmotionApiResult(False, error=f"未知错误: {exc}", status=0)

        return EmotionApiResult(False, error="达到最大重试次数", status=0)

    @staticmethod
    def _map_error(status: int) -> str:
        if status == 401:
            return "认证失败：Emotion credential 无效或已撤销"
        if status == 403:
            return "权限不足：credential 缺少所需 scope"
        if status == 404:
            return "资源不存在"
        if status == 409:
            return "冲突：资源已存在或 Idempotency-Key 已用于其他请求"
        if status == 429:
            return "请求过于频繁"
        if status >= 500:
            return f"Emotion 服务端错误 (HTTP {status})"
        return f"HTTP {status}"

    @staticmethod
    def _stable_key(*parts: str) -> str:
        digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
        return digest[:40]

    # ---------------------------------------------------------------- 健康
    async def health(self) -> EmotionApiResult:
        return await self._request("GET", "/integration/v1/health")

    # ---------------------------------------------------------------- 用户
    async def users(
        self, q: str = "", limit: int = 50, offset: int = 0
    ) -> EmotionApiResult:
        params: Dict[str, Any] = {"limit": max(1, min(int(limit), 200)), "offset": max(0, int(offset))}
        if q:
            params["q"] = str(q)
        return await self._request("GET", "/integration/v1/users", params=params)

    async def user_by_id(self, user_id: int) -> EmotionApiResult:
        return await self._request("GET", f"/integration/v1/users/{int(user_id)}")

    async def user_by_telegram(self, telegram_id: int) -> EmotionApiResult:
        return await self._request("GET", f"/integration/v1/users/telegram/{int(telegram_id)}")

    async def create_user(
        self,
        name: str,
        username: str = "",
        password: str = "",
        telegram_user_id: int = 0,
        telegram_username: str = "",
    ) -> EmotionApiResult:
        body = {
            "name": str(name or username),
            "username": str(username or name),
        }
        if password:
            body["password"] = str(password)
        if int(telegram_user_id or 0) > 0:
            body["telegram_user_id"] = int(telegram_user_id)
            body["telegram_username"] = str(telegram_username or "").lstrip("@")
        return await self._request(
            "POST",
            "/integration/v1/users",
            json_body=body,
            idempotency_key=self._stable_key("create_user", str(name), str(telegram_user_id or 0)),
        )

    async def delete_user(self, user_id: int) -> EmotionApiResult:
        return await self._request(
            "DELETE",
            f"/integration/v1/users/{int(user_id)}",
            idempotency_key=self._stable_key("delete_user", str(user_id)),
        )

    # ---------------------------------------------------------------- 策略/密码
    async def set_policy(self, user_id: int, *, admin: Optional[bool] = None, disable: Optional[bool] = None) -> EmotionApiResult:
        body: Dict[str, Any] = {}
        if admin is not None:
            body["IsAdministrator"] = bool(admin)
        if disable is not None:
            body["IsDisabled"] = bool(disable)
        return await self._request(
            "PATCH",
            f"/integration/v1/users/{int(user_id)}/policy",
            json_body=body,
            idempotency_key=self._stable_key("policy", str(user_id), str(admin), str(disable)),
        )

    async def set_password(self, user_id: int, password: str) -> EmotionApiResult:
        return await self._request(
            "POST",
            f"/integration/v1/users/{int(user_id)}/password",
            json_body={"password": str(password)},
            idempotency_key=self._stable_key("password", str(user_id)),
        )

    # ---------------------------------------------------------------- Telegram 绑定
    async def bind_telegram(self, user_id: int, telegram_user_id: int, telegram_username: str = "") -> EmotionApiResult:
        return await self._request(
            "POST",
            f"/integration/v1/users/{int(user_id)}/telegram",
            json_body={
                "telegram_user_id": int(telegram_user_id),
                "telegram_username": str(telegram_username or "").lstrip("@"),
            },
            idempotency_key=self._stable_key("bind_tg", str(user_id), str(telegram_user_id)),
        )

    async def unbind_telegram(self, user_id: int) -> EmotionApiResult:
        return await self._request(
            "DELETE",
            f"/integration/v1/users/{int(user_id)}/telegram",
            idempotency_key=self._stable_key("unbind_tg", str(user_id)),
        )

    # ---------------------------------------------------------------- 会话
    async def sessions(self) -> EmotionApiResult:
        return await self._request("GET", "/integration/v1/sessions")

    async def stop_session(self, session_id: str) -> EmotionApiResult:
        return await self._request(
            "POST",
            f"/integration/v1/sessions/{str(session_id)}/stop",
            idempotency_key=self._stable_key("stop_session", str(session_id)),
        )

    # ---------------------------------------------------------------- 媒体库/扫描
    async def libraries(self) -> EmotionApiResult:
        return await self._request("GET", "/integration/v1/libraries")

    async def scan_start(self) -> EmotionApiResult:
        return await self._request("POST", "/integration/v1/scans", json_body={}, idempotency_key=self._stable_key("scan_start"))

    async def scan_job(self, job_id: int) -> EmotionApiResult:
        return await self._request("GET", f"/integration/v1/scans/{int(job_id)}")

    # ---------------------------------------------------------------- 安全审计
    async def security_summary(self, hours: int = 24) -> EmotionApiResult:
        hours = max(1, min(int(hours or 24), 24 * 30))
        return await self._request("GET", "/integration/v1/security/summary", params={"hours": hours})

    async def security_events(self, hours: int = 24) -> EmotionApiResult:
        hours = max(1, min(int(hours or 24), 24 * 30))
        return await self._request("GET", "/integration/v1/security/events", params={"hours": hours})

    # ---------------------------------------------------------------- 订阅
    async def subscriptions(self, user_id: int) -> EmotionApiResult:
        return await self._request("GET", f"/integration/v1/users/{int(user_id)}/subscriptions")

    async def subscribe(self, user_id: int, video_id: int) -> EmotionApiResult:
        return await self._request(
            "POST",
            f"/integration/v1/users/{int(user_id)}/subscriptions/{int(video_id)}",
            json_body={},
            idempotency_key=self._stable_key("subscribe", str(user_id), str(video_id)),
        )

    async def unsubscribe(self, user_id: int, video_id: int) -> EmotionApiResult:
        return await self._request(
            "DELETE",
            f"/integration/v1/users/{int(user_id)}/subscriptions/{int(video_id)}",
            idempotency_key=self._stable_key("unsubscribe", str(user_id), str(video_id)),
        )

    # ---------------------------------------------------------------- 追更事件队列
    async def claim_events(self, limit: Optional[int] = None) -> EmotionApiResult:
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = max(1, min(int(limit), 100))
        return await self._request("POST", "/integration/v1/events/claim", params=params, json_body={})

    async def ack_events(self, lease_token: str, ids: List[int]) -> EmotionApiResult:
        if not lease_token or not ids:
            return EmotionApiResult(True, {"acked": 0})
        return await self._request(
            "POST",
            "/integration/v1/events/ack",
            json_body={"lease_token": lease_token, "ids": [int(i) for i in ids]},
            idempotency_key=self._stable_key("ack", lease_token, ",".join(str(i) for i in ids)),
        )

    async def release_events(self, lease_token: str, ids: List[int], error: str = "") -> EmotionApiResult:
        if not lease_token or not ids:
            return EmotionApiResult(True, {"released": 0})
        return await self._request(
            "POST",
            "/integration/v1/events/release",
            json_body={"lease_token": lease_token, "ids": [int(i) for i in ids], "error": str(error)[:2000]},
            idempotency_key=self._stable_key("release", lease_token, ",".join(str(i) for i in ids)),
        )


class EmotionEventPoller:
    """
    追更事件轮询：从 Emotion 领取订阅新集事件，通知对应 TG 用户后确认/释放。
    只在 Emotion 联动启用时运行；事件 ID 稳定，重复领取/确认幂等。
    """

    def __init__(self, service: EmotionService):
        self.service = service
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _poll_once(self) -> int:
        limit = int(getattr(emotion_cfg, "event_claim_limit", 50) or 50)
        result = await self.service.claim_events(limit=limit)
        if not result.success:
            return 0
        payload = result.data or {}
        events = payload.get("events") or []
        if not events:
            return 0
        lease_token = str(payload.get("lease_token") or "")
        ids = [int(e.get("id")) for e in events if e.get("id") is not None]

        ok_ids: List[int] = []
        for event in events:
            try:
                if await self._notify(event):
                    ok_ids.append(int(event["id"]))
            except Exception as exc:
                LOGGER.warning(f"Emotion 事件通知失败 id={event.get('id')}: {exc}")

        if ok_ids:
            await self.service.ack_events(lease_token, ok_ids)
        failed = [i for i in ids if i not in ok_ids]
        if failed:
            await self.service.release_events(lease_token, failed, error="TG 通知失败")
        return len(events)

    async def _notify(self, event: Dict[str, Any]) -> bool:
        if not getattr(emotion_cfg, "notify_on_new_episode", True):
            return True  # 通知关闭时视为处理成功
        telegram_id = int(event.get("telegram_user_id") or 0)
        if telegram_id <= 0:
            return True
        from bot import bot

        video_list_id = int(event.get("video_list_id") or 0)
        episode_id = int(event.get("video_episode_id") or 0)
        title = str(event.get("title") or "")
        episode = str(event.get("episode_name") or "")
        if not title or not episode:
            await self._enrich_titles(event, video_list_id, episode_id, telegram_id, title, episode)
            title = str(event.get("title") or "")
            episode = str(event.get("episode_name") or "")
            if not title:
                title = f"媒体 #{video_list_id}" if video_list_id else "新内容"
        if not episode:
            episode = f"第 {episode_id} 集" if episode_id else "新集已上线"
        text = (
            "🔔 **追更提醒**\n\n"
            f"📺 {title}\n"
            f"🎞️ {episode}\n\n"
            "已经更新，快去观看吧！"
        )
        await bot.send_message(chat_id=telegram_id, text=text)
        return True

    async def _enrich_titles(self, event: Dict[str, Any], video_list_id: int, episode_id: int, telegram_id: int, title: str, episode: str) -> None:
        # 尽力而为：通过 Emby 兼容接口补全剧名/集名，失败不阻断通知。
        try:
            from bot.func_helper.emby import emby
            emby_id = ""
            from bot.sql_helper.sql_emby import sql_get_emby
            row = sql_get_emby(tg=telegram_id)
            if row is not None and getattr(row, "embyid", None):
                emby_id = str(row.embyid)
            if not emby_id:
                return
            if video_list_id and not title:
                got = await emby.item_id_name(emby_id, str(video_list_id))
                if got:
                    event["title"] = got
            if episode_id and not episode:
                got = await emby.item_id_name(emby_id, str(episode_id))
                if got:
                    event["episode_name"] = got
        except Exception as exc:
            LOGGER.debug(f"Emotion 事件标题补全失败: {exc}")

    async def _loop(self) -> None:
        interval = int(getattr(emotion_cfg, "event_poll_interval", 60) or 60)
        while not self._stop.is_set():
            try:
                await self._poll_once()
            except Exception as exc:
                LOGGER.error(f"Emotion 事件轮询异常: {exc}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # main.py 在 bot.run() 之前（模块导入期）调用 start()，此时没有运行中的
            # 事件循环；get_or_create_event_loop() 返回的循环与 bot.run() 使用同一个。
            from bot.func_helper.runtime import get_or_create_event_loop

            loop = get_or_create_event_loop()
        self._task = loop.create_task(self._loop(), name="emotion-event-poller")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()


_service: Optional[EmotionService] = None
_poller: Optional[EmotionEventPoller] = None


def get_emotion_service() -> EmotionService:
    """返回进程内单例 Emotion 适配器（懒加载，未启用时返回禁用实例）。"""
    global _service
    if _service is None:
        _service = EmotionService(
            url=str(getattr(emotion_cfg, "url", "") or "").strip(),
            credential=_credential(),
            timeout=int(getattr(emotion_cfg, "timeout", 10) or 10),
            max_retries=int(getattr(emotion_cfg, "max_retries", 1) or 1),
        )
    return _service


def get_emotion_poller() -> EmotionEventPoller:
    global _poller
    if _poller is None:
        _poller = EmotionEventPoller(get_emotion_service())
    return _poller


async def shutdown_emotion_adapter() -> None:
    if _poller is not None:
        await _poller.stop()
    if _service is not None:
        await _service.close()
