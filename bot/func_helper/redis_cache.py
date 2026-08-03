from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from bot.func_helper.logger_config import logu

LOGGER = logu(__name__)

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - runtime dependency guard
    Redis = None

    class RedisError(Exception):
        pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


REDIS_ENABLED = _env_bool("PIVKEYU_REDIS_ENABLED", False)
REDIS_HOST = os.getenv("PIVKEYU_REDIS_HOST", "127.0.0.1").strip() or "127.0.0.1"
REDIS_PORT = _env_int("PIVKEYU_REDIS_PORT", 6379, 1)
REDIS_DB = _env_int("PIVKEYU_REDIS_DB", 0, 0)
REDIS_PASSWORD = os.getenv("PIVKEYU_REDIS_PASSWORD", "") or None
REDIS_PREFIX = (os.getenv("PIVKEYU_REDIS_PREFIX", "pivkeyu_emby") or "pivkeyu_emby").strip().rstrip(":")
REDIS_CONNECT_TIMEOUT = max(float(os.getenv("PIVKEYU_REDIS_CONNECT_TIMEOUT", "1.5") or 1.5), 0.1)
REDIS_SOCKET_TIMEOUT = max(float(os.getenv("PIVKEYU_REDIS_SOCKET_TIMEOUT", "1.5") or 1.5), 0.1)
REDIS_RETRY_COOLDOWN = max(float(os.getenv("PIVKEYU_REDIS_RETRY_COOLDOWN", "15") or 15), 1.0)

_client: Redis | None = None
_client_lock = threading.Lock()
_last_connect_failure_at = 0.0
_missing_dependency_reported = False
_connect_success_reported = False


def _report_missing_dependency_once() -> None:
    global _missing_dependency_reported
    if _missing_dependency_reported:
        return
    LOGGER.error("Redis 已启用，但未安装 redis Python 依赖，请执行 pip install -r requirements.txt")
    _missing_dependency_reported = True


def redis_enabled() -> bool:
    return REDIS_ENABLED


def build_key(*parts: Any) -> str:
    normalized_parts = [REDIS_PREFIX] if REDIS_PREFIX else []
    normalized_parts.extend(str(part).strip() for part in parts if part is not None and str(part).strip())
    return ":".join(normalized_parts)


def get_client() -> Redis | None:
    global _client, _last_connect_failure_at, _connect_success_reported

    if not REDIS_ENABLED:
        return None

    if Redis is None:
        _report_missing_dependency_once()
        return None

    if _client is not None:
        return _client

    now = time.monotonic()
    if now - _last_connect_failure_at < REDIS_RETRY_COOLDOWN:
        return None

    with _client_lock:
        if _client is not None:
            return _client

        now = time.monotonic()
        if now - _last_connect_failure_at < REDIS_RETRY_COOLDOWN:
            return None

        try:
            client = Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
                health_check_interval=30,
            )
            client.ping()
            _client = client
            if not _connect_success_reported:
                LOGGER.info(f"Redis 缓存已启用 {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
                _connect_success_reported = True
            return _client
        except Exception as exc:
            _last_connect_failure_at = now
            LOGGER.warning(f"Redis 连接失败，暂时回退到本地数据库直连: {exc}")
            return None


def get_json(key: str) -> tuple[bool, Any]:
    client = get_client()
    if client is None:
        return False, None

    try:
        raw = client.get(key)
        if raw is None:
            return False, None
        return True, json.loads(raw)
    except (RedisError, TypeError, ValueError) as exc:
        LOGGER.warning(f"Redis 读取缓存失败 key={key}: {exc}")
        return False, None


def set_json(key: str, payload: Any, ttl: int) -> bool:
    client = get_client()
    if client is None:
        return False

    try:
        ttl = max(int(ttl or 0), 1)
        client.setex(key, ttl, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return True
    except (RedisError, TypeError, ValueError) as exc:
        LOGGER.warning(f"Redis 写入缓存失败 key={key}: {exc}")
        return False


def get_int(key: str, default: int = 0) -> int:
    client = get_client()
    if client is None:
        return int(default)

    try:
        raw = client.get(key)
        if raw is None:
            return int(default)
        return int(raw)
    except (RedisError, TypeError, ValueError) as exc:
        LOGGER.warning(f"Redis 读取整数失败 key={key}: {exc}")
        return int(default)


def mget_int(keys: list[str], *, default: int = 1) -> list[int]:
    client = get_client()
    normalized = [str(key).strip() for key in keys if key and str(key).strip()]
    if client is None or not normalized:
        return [int(default)] * len(normalized)

    try:
        values = client.mget(normalized)
    except RedisError as exc:
        LOGGER.warning(f"Redis 批量读取整数失败 keys={normalized}: {exc}")
        return [int(default)] * len(normalized)

    resolved: list[int] = []
    for raw in values:
        if raw is None:
            resolved.append(int(default))
            continue
        try:
            resolved.append(max(int(raw), 1))
        except (TypeError, ValueError):
            resolved.append(int(default))
    return resolved


def increment(key: str, amount: int = 1) -> int:
    client = get_client()
    if client is None:
        return 0

    try:
        return int(client.incrby(key, int(amount or 1)))
    except (RedisError, TypeError, ValueError) as exc:
        LOGGER.warning(f"Redis 自增失败 key={key}: {exc}")
        return 0


def delete_keys(*keys: str) -> int:
    client = get_client()
    normalized = [str(key).strip() for key in keys if key and str(key).strip()]
    if client is None or not normalized:
        return 0

    try:
        return int(client.delete(*normalized) or 0)
    except RedisError as exc:
        LOGGER.warning(f"Redis 删除缓存失败 keys={normalized}: {exc}")
        return 0


def delete_pattern(*patterns: str, max_scan: int = 10000) -> int:
    client = get_client()
    normalized = [str(pattern).strip() for pattern in patterns if pattern and str(pattern).strip()]
    if client is None or not normalized:
        return 0

    deleted = 0
    try:
        for pattern in normalized:
            batch: list[str] = []
            scanned = 0
            for key in client.scan_iter(match=pattern, count=200):
                scanned += 1
                if scanned > max_scan:
                    LOGGER.warning(f"Redis scan 超过上限 {max_scan} pattern={pattern}，提前终止")
                    break
                batch.append(key)
                if len(batch) >= 200:
                    deleted += int(client.delete(*batch) or 0)
                    batch.clear()
            if batch:
                deleted += int(client.delete(*batch) or 0)
        return deleted
    except RedisError as exc:
        LOGGER.warning(f"Redis 按模式删除缓存失败 patterns={normalized}: {exc}")
        return deleted


def get_status() -> dict[str, Any]:
    if not REDIS_ENABLED:
        return {
            "enabled": False,
            "available": False,
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": REDIS_DB,
        }

    client = get_client()
    available = client is not None
    return {
        "enabled": True,
        "available": available,
        "host": REDIS_HOST,
        "port": REDIS_PORT,
        "db": REDIS_DB,
    }
