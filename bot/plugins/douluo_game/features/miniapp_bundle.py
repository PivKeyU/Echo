from __future__ import annotations

from typing import Any

from bot.plugins.sdk import build_plugin_url
from bot.sql_helper.sql_douluo import (
    build_douluo_leaderboard,
    get_craftsman_info,
    get_daily_action_usage,
    get_economy_snapshot,
    get_sequel_catalog,
    get_settings,
    list_auction_listings,
    list_bosses,
    list_daily_tasks,
    list_hunt_regions,
    list_item_definitions,
    list_player_inventory_grouped,
    list_recent_journals,
    list_sect_options,
    serialize_profile,
)
from bot.web.api.miniapp import is_admin_user_id


def _build_user_capabilities(tg: int) -> dict[str, Any]:
    is_admin = is_admin_user_id(int(tg))
    return {
        "is_admin": is_admin,
        "admin_panel_url": (
            build_plugin_url("/plugins/douluo/admin") or "/plugins/douluo/admin"
        ) if is_admin else None,
    }


def build_profile_bundle(tg: int) -> dict[str, Any]:
    tg = int(tg)
    payload = serialize_profile(tg, include_rings=True, include_equipment=True, include_actions=True)
    usage = get_daily_action_usage(tg)
    payload["action_points"] = usage.get("action_points", {})
    payload["action_usage"] = usage.get("items", {})
    payload["economy"] = get_economy_snapshot(tg)
    return payload


def build_user_bootstrap_bundle(tg: int) -> dict[str, Any]:
    tg = int(tg)
    profile_bundle = build_profile_bundle(tg)
    settings = get_settings()
    return {
        **profile_bundle,
        "capabilities": _build_user_capabilities(tg),
        "settings": {
            "daily_action_points": settings.get("daily_action_points"),
            "event_chance_percent": settings.get("event_chance_percent"),
            "duel_min_stake": settings.get("duel_min_stake"),
            "duel_max_stake": settings.get("duel_max_stake"),
            "wuhun_reforge_coin": settings.get("wuhun_reforge_coin"),
            "wuhun_reforge_cd_hours": settings.get("wuhun_reforge_cd_hours"),
            "hunt_absorb_fee": settings.get("hunt_absorb_fee"),
            "auction_fee_percent": settings.get("auction_fee_percent"),
            "auction_duration_hours": settings.get("auction_duration_hours"),
            "broadcast_enabled": settings.get("broadcast_enabled"),
            "exchange_enabled": settings.get("exchange_enabled"),
            "bloodline_awaken_coin": settings.get("bloodline_awaken_coin"),
            "bloodline_enhance_coin": settings.get("bloodline_enhance_coin"),
            "bloodline_enhance_soul_power": settings.get("bloodline_enhance_soul_power"),
            "prospect_coin_cost": settings.get("prospect_coin_cost"),
            "condense_coin_cost": settings.get("condense_coin_cost"),
            "condense_soul_power_cost": settings.get("condense_soul_power_cost"),
            "armor_upgrade_coin": settings.get("armor_upgrade_coin"),
        },
        "craftsman": get_craftsman_info(tg),
        "sequel": get_sequel_catalog(),
        "inventory": list_player_inventory_grouped(tg),
        "item_definitions": list_item_definitions(),
        "daily_tasks": list_daily_tasks(tg),
        "sects": list_sect_options(),
        "hunt_regions": list_hunt_regions(),
        "bosses": list_bosses(),
        "journals": list_recent_journals(tg, limit=15),
        "auction_listings": _list_open_auctions(tg),
        "leaderboard": {
            "power": build_douluo_leaderboard("power", 10),
            "rings": build_douluo_leaderboard("rings", 10),
            "coin": build_douluo_leaderboard("coin", 10),
        },
    }


def _list_open_auctions(tg: int) -> list[dict[str, Any]]:
    return list_auction_listings(int(tg), status="open")


def build_action_result_bundle(tg: int, result: dict[str, Any]) -> dict[str, Any]:
    tg = int(tg)
    payload = build_profile_bundle(tg)
    payload["result"] = result
    return payload


def build_exchange_result_bundle(tg: int, result: dict[str, Any]) -> dict[str, Any]:
    tg = int(tg)
    payload = build_profile_bundle(tg)
    payload["result"] = result
    return payload
