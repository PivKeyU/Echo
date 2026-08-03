from __future__ import annotations

from typing import Any

from bot.func_helper.emby_currency import get_emby_balance
from bot.plugins.doupo_game.core import ACTION_TYPE_LABELS, GAMEPLAY_MODULES
from bot.plugins.sdk import build_bottom_nav, build_plugin_url
from bot.sql_helper.sql_doupo import (
    build_feature_overview,
    build_growth_snapshot,
    get_daily_action_usage,
    get_economy_snapshot,
    get_expedition_overview,
    get_or_create_profile,
    get_sect_panel,
    get_settings,
    list_sect_options,
    list_player_inventory_grouped,
    list_player_actions,
    list_recent_journals,
)
from bot.web.api.miniapp import is_admin_user_id


def _build_user_capabilities(tg: int) -> dict[str, Any]:
    is_admin = is_admin_user_id(int(tg))
    return {
        "is_admin": is_admin,
        "admin_panel_url": (
            build_plugin_url("/plugins/doupo/admin") or "/plugins/doupo/admin"
        ) if is_admin else None,
    }


def _decorate_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for action in actions:
        row = dict(action)
        row["action_type_label"] = ACTION_TYPE_LABELS.get(str(row.get("action_type") or ""), str(row.get("action_type") or "行动"))
        decorated.append(row)
    return decorated


def build_user_bootstrap_bundle(tg: int) -> dict[str, Any]:
    actor_tg = int(tg)
    profile = get_or_create_profile(actor_tg)
    settings = get_settings()
    return {
        "profile": profile,
        "growth": build_growth_snapshot(profile, settings),
        "features": build_feature_overview(profile),
        "inventory": list_player_inventory_grouped(actor_tg),
        "economy": get_economy_snapshot(actor_tg, settings),
        "expedition": get_expedition_overview(actor_tg),
        "daily_usage": get_daily_action_usage(actor_tg, settings),
        "emby_balance": get_emby_balance(actor_tg),
        "settings": settings,
        "sects": list_sect_options(),
        "sect_panel": get_sect_panel(actor_tg, settings),
        "actions": _decorate_actions(list_player_actions(actor_tg, enabled_only=True)),
        "journals": list_recent_journals(actor_tg, limit=20),
        "bottom_nav": build_bottom_nav(),
        "playbook": GAMEPLAY_MODULES,
        "capabilities": _build_user_capabilities(actor_tg),
    }


def build_action_result_bundle(tg: int, result: dict[str, Any]) -> dict[str, Any]:
    actor_tg = int(tg)
    profile = result.get("profile") or get_or_create_profile(actor_tg)
    settings = get_settings()
    return {
        **result,
        "growth": build_growth_snapshot(profile, settings),
        "features": build_feature_overview(profile),
        "inventory": result.get("inventory") or list_player_inventory_grouped(actor_tg),
        "economy": result.get("economy") or get_economy_snapshot(actor_tg, settings),
        "expedition": get_expedition_overview(actor_tg),
        "daily_usage": get_daily_action_usage(actor_tg, settings),
        "emby_balance": get_emby_balance(actor_tg),
        "settings": settings,
        "sects": list_sect_options(),
        "actions": _decorate_actions(list_player_actions(actor_tg, enabled_only=True)),
        "journals": list_recent_journals(actor_tg, limit=20),
        "bottom_nav": build_bottom_nav(),
        "playbook": GAMEPLAY_MODULES,
        "capabilities": _build_user_capabilities(actor_tg),
    }


def build_exchange_result_bundle(tg: int, result: dict[str, Any]) -> dict[str, Any]:
    return build_action_result_bundle(tg, result)
