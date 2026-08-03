from __future__ import annotations

from typing import Any


def _legacy_world_service():
    from bot.plugins.xiuxian_game import world_service as legacy_world_service

    return legacy_world_service


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def create_red_envelope_for_user(**kwargs) -> dict[str, Any]:
    return _legacy_world_service().create_red_envelope_for_user(**kwargs)


def claim_red_envelope_for_user(envelope_id: int, tg: int) -> dict[str, Any]:
    return _legacy_world_service().claim_red_envelope_for_user(envelope_id, tg)


def rob_player(attacker_tg: int, defender_tg: int, success_hint: float = 0.5) -> dict[str, Any]:
    return _legacy_world_service().rob_player(attacker_tg, defender_tg, success_hint=success_hint)


def create_duel_bet_pool_for_duel(**kwargs) -> dict[str, Any]:
    return _legacy_world_service().create_duel_bet_pool_for_duel(**kwargs)


def place_duel_bet(pool_id: int, tg: int, side: str, amount: int) -> dict[str, Any]:
    return _legacy_world_service().place_duel_bet(pool_id, tg, side, amount)


def settle_duel_bet_pool(pool_id: int, winner_tg: int) -> dict[str, Any]:
    return _legacy_world_service().settle_duel_bet_pool(pool_id, winner_tg)


def cancel_duel_bet_pool(pool_id: int, reason: str = "") -> dict[str, Any]:
    return _legacy_world_service().cancel_duel_bet_pool(pool_id, reason=reason)


def format_duel_bet_board(pool_id: int) -> str:
    return _legacy_world_service().format_duel_bet_board(pool_id)


def update_duel_bet_pool_message(pool_id: int, bet_message_id: int) -> None:
    return _legacy_world_service().update_duel_bet_pool_message(pool_id, bet_message_id)


def switch_social_mode_for_user(tg: int, social_mode: str) -> dict[str, Any]:
    return _legacy_service().switch_social_mode_for_user(tg, social_mode)


def harvest_furnace_for_user(tg: int, furnace_tg: int) -> dict[str, Any]:
    return _legacy_service().harvest_furnace_for_user(tg, furnace_tg)
