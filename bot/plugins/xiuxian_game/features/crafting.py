from __future__ import annotations

from typing import Any

from bot.plugins.xiuxian_game.features.farm import append_farm_source_labels


def _legacy_world_service():
    from bot.plugins.xiuxian_game import world_service as legacy_world_service

    return legacy_world_service


def create_recipe_with_ingredients(**kwargs) -> dict[str, Any]:
    return _legacy_world_service().create_recipe_with_ingredients(**kwargs)


def patch_recipe_with_ingredients(recipe_id: int, **kwargs) -> dict[str, Any]:
    return _legacy_world_service().patch_recipe_with_ingredients(recipe_id, **kwargs)


def build_recipe_catalog(tg: int | None = None) -> list[dict[str, Any]]:
    legacy = _legacy_world_service()
    recipes = append_farm_source_labels(legacy.build_recipe_catalog(tg))
    return legacy.attach_recipe_search_indexes(recipes)


def build_recipe_fragment_synthesis_catalog(tg: int) -> list[dict[str, Any]]:
    return _legacy_world_service().build_recipe_fragment_synthesis_catalog(tg)


def craft_recipe_for_user(tg: int, recipe_id: int, quantity: int = 1) -> dict[str, Any]:
    return _legacy_world_service().craft_recipe_for_user(tg, recipe_id, quantity)


def synthesize_recipe_fragment_for_user(tg: int, recipe_id: int) -> dict[str, Any]:
    return _legacy_world_service().synthesize_recipe_fragment_for_user(tg, recipe_id)
