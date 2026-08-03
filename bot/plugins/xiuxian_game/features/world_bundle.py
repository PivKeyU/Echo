from __future__ import annotations

from typing import Any

from bot.plugins.xiuxian_game.features.farm import append_farm_source_labels, build_farm_bundle
from bot.plugins.xiuxian_game.features.fishing import build_fishing_bundle


def _legacy_world_service():
    from bot.plugins.xiuxian_game import world_service as legacy_world_service

    return legacy_world_service


def build_world_bundle(tg: int) -> dict[str, Any]:
    legacy = _legacy_world_service()
    bundle = legacy.build_world_bundle(tg)
    bundle["recipes"] = legacy.attach_recipe_search_indexes(append_farm_source_labels(bundle.get("recipes") or []))
    bundle["farm"] = build_farm_bundle(tg)
    bundle["fishing"] = build_fishing_bundle(tg)
    return bundle
