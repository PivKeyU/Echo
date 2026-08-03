from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

from bot.func_helper import redis_cache
from bot.plugins.sdk.memory_cache import get_memory_cache


SETTINGS_TTL = max(int(os.getenv("PIVKEYU_REDIS_XIUXIAN_SETTINGS_TTL", "300") or 300), 1)
CATALOG_TTL = max(int(os.getenv("PIVKEYU_REDIS_XIUXIAN_CATALOG_TTL", "300") or 300), 1)
USER_VIEW_TTL = max(int(os.getenv("PIVKEYU_REDIS_XIUXIAN_USER_VIEW_TTL", "45") or 45), 1)
MEMORY_CACHE = get_memory_cache()
_LOCAL_VERSION_LOCK = threading.RLock()
_LOCAL_VERSIONS: dict[tuple[str, ...], int] = {}


def _normalize_parts(parts: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(str(part).strip() for part in parts if part is not None and str(part).strip())


def _version_key(*parts: Any) -> str:
    return redis_cache.build_key("xiuxian", "version", *_normalize_parts(parts))


def _cache_key(*parts: Any) -> str:
    return redis_cache.build_key("xiuxian", "cache", *_normalize_parts(parts))


def _local_version(parts: tuple[str, ...]) -> int:
    with _LOCAL_VERSION_LOCK:
        return max(int(_LOCAL_VERSIONS.get(parts, 1) or 1), 1)


def _bump_version(*parts: Any) -> int:
    normalized = _normalize_parts(parts)
    if not normalized:
        return 0
    with _LOCAL_VERSION_LOCK:
        local_value = max(int(_LOCAL_VERSIONS.get(normalized, 1) or 1), 1) + 1
        _LOCAL_VERSIONS[normalized] = local_value

    if not redis_cache.redis_enabled():
        return local_value
    remote_value = redis_cache.increment(_version_key(*normalized))
    # Missing Redis keys read as version 1. A first INCR also returns 1, so
    # advance once more to guarantee that other processes see a new token.
    if remote_value == 1:
        remote_value = redis_cache.increment(_version_key(*normalized))
    return remote_value if remote_value > 0 else local_value


def _version_tokens(part_groups: tuple[tuple[Any, ...], ...]) -> list[str]:
    normalized_groups = [_normalize_parts(parts) for parts in part_groups]
    normalized_groups = [parts for parts in normalized_groups if parts]
    if not normalized_groups:
        return ["1"]

    local_tokens = [_local_version(parts) for parts in normalized_groups]
    if not redis_cache.redis_enabled():
        return [str(value) for value in local_tokens]

    keys = [_version_key(*parts) for parts in normalized_groups]
    remote_tokens = redis_cache.mget_int(keys, default=1)
    return [f"{remote}.{local}" for remote, local in zip(remote_tokens, local_tokens)]


def _memory_cache_get(cache_key: str) -> Any | None:
    return MEMORY_CACHE.get(f"xiuxian:{cache_key}")


def _memory_cache_set(cache_key: str, payload: Any, ttl: int) -> None:
    MEMORY_CACHE.set(f"xiuxian:{cache_key}", payload, ttl)


def _memory_cache_ttl(ttl: int) -> int:
    return min(max(int(ttl), 15), 120)


def load_versioned_json(
    *,
    version_parts: tuple[Any, ...],
    cache_parts: tuple[Any, ...],
    ttl: int,
    loader: Callable[[], Any],
) -> Any:
    token = _version_tokens((version_parts,))[0]
    cache_key = _cache_key(*cache_parts, f"v{token}")

    cached = _memory_cache_get(cache_key)
    if cached is not None:
        return cached

    if redis_cache.redis_enabled():
        hit, payload = redis_cache.get_json(cache_key)
        if hit:
            _memory_cache_set(cache_key, payload, _memory_cache_ttl(ttl))
            return payload

    payload = loader()
    _memory_cache_set(cache_key, payload, _memory_cache_ttl(ttl))
    if redis_cache.redis_enabled():
        redis_cache.set_json(cache_key, payload, ttl)
    return payload


def load_multi_versioned_json(
    *,
    version_part_groups: tuple[tuple[Any, ...], ...],
    cache_parts: tuple[Any, ...],
    ttl: int,
    loader: Callable[[], Any],
) -> Any:
    normalized_groups = tuple(
        parts
        for parts in (_normalize_parts(group) for group in version_part_groups)
        if parts
    )
    tokens = _version_tokens(normalized_groups)
    resolved_cache_parts = list(cache_parts)
    for parts, token in zip(normalized_groups, tokens):
        resolved_cache_parts.extend(("ver", *parts, f"v{token}"))

    cache_key = _cache_key(*resolved_cache_parts)
    cached = _memory_cache_get(cache_key)
    if cached is not None:
        return cached

    if redis_cache.redis_enabled():
        hit, payload = redis_cache.get_json(cache_key)
        if hit:
            _memory_cache_set(cache_key, payload, _memory_cache_ttl(ttl))
            return payload

    payload = loader()
    _memory_cache_set(cache_key, payload, _memory_cache_ttl(ttl))
    if redis_cache.redis_enabled():
        redis_cache.set_json(cache_key, payload, ttl)
    return payload


def bump_settings_version() -> int:
    return _bump_version("settings")


def bump_catalog_versions(*names: str) -> int:
    bumped = 0
    seen: set[str] = set()
    for name in names:
        normalized = str(name or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        _bump_version("catalog", normalized)
        bumped += 1
    if bumped:
        _bump_version("catalog", "aggregate")
    return bumped


def bump_profile_versions(*tgs: int) -> int:
    bumped = 0
    seen: set[int] = set()
    for tg in tgs:
        value = int(tg or 0)
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        _bump_version("profile", value)
        bumped += 1
    return bumped


def bump_user_view_versions(*tgs: int) -> int:
    bumped = 0
    seen: set[int] = set()
    for tg in tgs:
        value = int(tg or 0)
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        _bump_version("user-view", value)
        bumped += 1
    return bumped


def version_generation(*part_groups: tuple[Any, ...]) -> str:
    return ".".join(_version_tokens(part_groups))


def catalog_version_groups(*, include_all_catalog: bool = True) -> tuple[tuple[Any, ...], ...]:
    """合并 catalog 版本组，减少 Redis 往返与缓存键数量。"""
    groups: list[tuple[Any, ...]] = [
        ("settings",),
        ("catalog", "aggregate"),
    ]
    if include_all_catalog:
        groups.extend(
            [
                ("catalog", "artifact-sets"),
                ("catalog", "artifacts"),
                ("catalog", "materials"),
                ("catalog", "pills"),
                ("catalog", "recipes"),
                ("catalog", "scenes"),
                ("catalog", "sects"),
                ("catalog", "shop-items"),
                ("catalog", "talismans"),
                ("catalog", "techniques"),
                ("catalog", "titles"),
            ]
        )
    return tuple(groups)
