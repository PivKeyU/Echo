from __future__ import annotations

import os
from typing import Any

from bot.plugins.xiuxian_game.cache import USER_VIEW_TTL, load_multi_versioned_json, version_generation
FULL_BUNDLE_TTL = max(int(os.getenv("PIVKEYU_XIUXIAN_FULL_BUNDLE_TTL", "45") or 45), 5)


def bootstrap_version_groups(tg: int) -> tuple[tuple[Any, ...], ...]:
    return (
        ("profile", tg),
        ("user-view", tg),
        ("settings",),
        ("catalog", "aggregate"),
        ("catalog", "artifact-sets"),
        ("catalog", "artifacts"),
    )


def bootstrap_cache_generation(tg: int) -> str:
    return version_generation(*bootstrap_version_groups(tg))


def load_cached_bootstrap_core_bundle(tg: int, **flags: Any) -> dict[str, Any]:
    """带 Redis / 进程内缓存的 bootstrap core，供 section 与 deferred 复用。"""
    from bot.plugins.xiuxian_game.features.miniapp_bundle import build_bootstrap_core_bundle

    return load_multi_versioned_json(
        version_part_groups=bootstrap_version_groups(tg),
        cache_parts=("bootstrap", tg),
        ttl=min(USER_VIEW_TTL, FULL_BUNDLE_TTL),
        loader=lambda: build_bootstrap_core_bundle(tg, **flags),
    )
