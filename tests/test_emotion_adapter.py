#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
emotion_adapter tests — 用本地 mock HTTP 服务验证 Emotion 服务端适配器：
- 认证头：所有请求携带 Bearer credential 与 X-Request-ID
- 写请求携带 Idempotency-Key
- 401/403/404 错误映射
- 事件领取/确认/释放的 lease 语义
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import types
import unittest
from pathlib import Path
from typing import Dict, List, Optional

# 隔离测试：bot 包依赖 loguru/pyrogram 等重量级库，这里注入一个最小桩模块，
# 使 emotion 适配器可以在无完整运行时依赖的环境下单独测试。
stub_bot = types.ModuleType("bot")
stub_bot.LOGGER = logging.getLogger("bot-stub")

class _Cfg:
    status = True
    url = "http://127.0.0.1:1"
    credential = "emo_int_test_token"
    timeout = 5
    max_retries = 1
    event_poll_interval = 60
    event_claim_limit = 50
    notify_on_new_episode = True

stub_bot.emotion_cfg = _Cfg()
sys.modules["bot"] = stub_bot
sys.modules["bot.func_helper"] = types.ModuleType("bot.func_helper")
sys.modules["bot.func_helper"].__path__ = []

# 直接从文件加载 emotion 模块并挂到 bot.func_helper 命名空间下。
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_emotion_path = Path(__file__).resolve().parents[1] / "bot" / "func_helper" / "emotion.py"
_spec = importlib.util.spec_from_file_location("bot.func_helper.emotion", _emotion_path)
_emotion_mod = importlib.util.module_from_spec(_spec)
sys.modules["bot.func_helper.emotion"] = _emotion_mod
_spec.loader.exec_module(_emotion_mod)
EmotionApiResult = _emotion_mod.EmotionApiResult
EmotionService = _emotion_mod.EmotionService


class _FakeEmotionServer:
    """极简 async mock：记录请求并可按路径返回预置响应。"""

    def __init__(self):
        self.requests: List[dict] = []
        self.responses: Dict[str, dict] = {}
        self.default_status = 200
        self.default_body: dict = {}

    def handle(self, method: str, path: str, headers: dict, body: Optional[dict]):
        self.requests.append({"method": method, "path": path, "headers": headers, "body": body})
        key = f"{method} {path}"
        preset = self.responses.get(key)
        if preset is None:
            # 按路径前缀匹配（如 /integration/v1/users/123）
            for k, v in self.responses.items():
                if k.endswith("*") and path.startswith(k[:-1]):
                    preset = v
                    break
        if preset is None:
            return self.default_status, self.default_body
        return preset.get("status", self.default_status), preset.get("body", self.default_body)


async def _serve(handler, request):
    body = None
    if request.method in ("POST", "PATCH", "PUT"):
        try:
            body = await request.json()
        except Exception:
            body = None
    status, payload = handler.handle(
        request.method, request.path, dict(request.headers), body
    )
    return web.json_response(payload, status=status)


import aiohttp
import aiohttp.web as web
from aiohttp.test_utils import TestServer, TestClient


class EmotionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = _FakeEmotionServer()
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", lambda req: _serve(self.fake, req))
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        sock = self.site._server.sockets[0]
        port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        self.service = EmotionService(
            url=self.base, credential="emo_int_test_token", timeout=5, max_retries=0
        )
        self.fake.default_body = {"ok": True}

    async def asyncTearDown(self):
        await self.service.close()
        await self.runner.cleanup()

    async def test_health_sends_bearer_and_request_id(self):
        result = await self.service.health()
        self.assertTrue(result.success)
        req = self.fake.requests[-1]
        self.assertEqual(req["method"], "GET")
        self.assertEqual(req["path"], "/integration/v1/health")
        self.assertEqual(req["headers"].get("Authorization"), "Bearer emo_int_test_token")
        self.assertTrue(req["headers"].get("X-Request-ID", "").startswith("emo_"))

    async def test_mutating_requests_carry_idempotency_key(self):
        self.fake.responses["POST /integration/v1/users"] = {
            "status": 201,
            "body": {"id": 7, "username": "alice"},
        }
        result = await self.service.create_user(name="alice", telegram_user_id=123456)
        self.assertTrue(result.success)
        self.assertEqual(result.data["id"], 7)
        req = self.fake.requests[-1]
        self.assertEqual(req["method"], "POST")
        self.assertTrue(req["headers"].get("Idempotency-Key"))
        self.assertEqual(req["body"]["name"], "alice")
        self.assertEqual(req["body"]["telegram_user_id"], 123456)

    async def test_401_maps_to_credential_error(self):
        self.fake.responses["GET /integration/v1/users"] = {"status": 401, "body": {}}
        result = await self.service.users()
        self.assertFalse(result.success)
        self.assertEqual(result.status, 401)
        self.assertIn("credential", result.error)

    async def test_403_maps_to_scope_error(self):
        self.fake.responses["GET /integration/v1/users"] = {"status": 403, "body": {}}
        result = await self.service.users()
        self.assertFalse(result.success)
        self.assertEqual(result.status, 403)
        self.assertIn("scope", result.error)

    async def test_404_maps_to_not_found(self):
        self.fake.responses["GET /integration/v1/users/999"] = {"status": 404, "body": {}}
        result = await self.service.user_by_id(999)
        self.assertFalse(result.success)
        self.assertEqual(result.status, 404)
        self.assertIn("不存在", result.error)

    async def test_409_maps_to_conflict(self):
        self.fake.responses["POST /integration/v1/users"] = {"status": 409, "body": {}}
        result = await self.service.create_user(name="dup")
        self.assertFalse(result.success)
        self.assertEqual(result.status, 409)

    async def test_delete_user_idempotency(self):
        self.fake.responses["DELETE /integration/v1/users/5"] = {"status": 204, "body": {}}
        result = await self.service.delete_user(5)
        self.assertTrue(result.success)
        req = self.fake.requests[-1]
        self.assertEqual(req["method"], "DELETE")
        self.assertTrue(req["headers"].get("Idempotency-Key"))

    async def test_claim_ack_release_lease_contract(self):
        # claim 返回 lease_token + events
        self.fake.responses["POST /integration/v1/events/claim"] = {
            "status": 200,
            "body": {
                "lease_token": "lease-abc",
                "events": [
                    {"id": 1, "user_id": 10, "video_list_id": 100, "video_episode_id": 200},
                ],
                "count": 1,
            },
        }
        claim = await self.service.claim_events(limit=10)
        self.assertTrue(claim.success)
        self.assertEqual(claim.data["lease_token"], "lease-abc")
        self.assertEqual(claim.data["events"][0]["id"], 1)

        # ack 幂等键与 lease 绑定
        self.fake.responses["POST /integration/v1/events/ack"] = {
            "status": 200,
            "body": {"acked": 1},
        }
        ack = await self.service.ack_events("lease-abc", [1])
        self.assertTrue(ack.success)
        req = self.fake.requests[-1]
        self.assertEqual(req["body"]["lease_token"], "lease-abc")
        self.assertEqual(req["body"]["ids"], [1])
        self.assertTrue(req["headers"].get("Idempotency-Key"))

        # release 记录错误信息
        self.fake.responses["POST /integration/v1/events/release"] = {
            "status": 200,
            "body": {"released": 1},
        }
        rel = await self.service.release_events("lease-abc", [1], error="tg send failed")
        self.assertTrue(rel.success)
        req = self.fake.requests[-1]
        self.assertEqual(req["body"]["error"], "tg send failed")

    async def test_unconfigured_service_returns_error(self):
        svc = EmotionService(url="", credential="")
        result = await svc.health()
        self.assertFalse(result.success)
        self.assertIn("未配置", result.error)

    async def test_retry_on_5xx_then_success(self):
        calls = {"n": 0}

        class _Counting:
            def __init__(self, fake):
                self.fake = fake

            def handle(self, method, path, headers, body):
                calls["n"] += 1
                if calls["n"] == 1:
                    return 503, {}
                return 200, {"ok": True}

        counting = _Counting(self.fake)
        old_handle = self.fake.handle
        self.fake.handle = counting.handle
        try:
            svc = EmotionService(url=self.base, credential="tok", timeout=5, max_retries=2)
            result = await svc.health()
            self.assertTrue(result.success)
            self.assertGreaterEqual(calls["n"], 2)
            await svc.close()
        finally:
            self.fake.handle = old_handle


if __name__ == "__main__":
    unittest.main()
