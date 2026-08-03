from __future__ import annotations

import threading
import time
from typing import Any


class TTLMemoryCache:
    """轻量进程内 TTL 缓存，Redis 不可用时的二级缓存。"""

    def __init__(self, *, max_entries: int = 512) -> None:
        self._max_entries = max(32, int(max_entries))
        self._lock = threading.RLock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                return None
            expires_at, payload = item
            if expires_at <= now:
                self._entries.pop(key, None)
                return None
            return payload

    def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.monotonic() + max(int(ttl or 1), 1)
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max_entries:
                oldest_key = min(self._entries, key=lambda item: self._entries[item][0])
                self._entries.pop(oldest_key, None)
            self._entries[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        normalized = str(prefix or "")
        if not normalized:
            return 0
        with self._lock:
            keys = [key for key in self._entries if key.startswith(normalized)]
            for key in keys:
                self._entries.pop(key, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_GLOBAL_MEMORY_CACHE = TTLMemoryCache()


def get_memory_cache() -> TTLMemoryCache:
    return _GLOBAL_MEMORY_CACHE
