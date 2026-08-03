from __future__ import annotations

from typing import Any


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def build_leaderboard(kind: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    return _legacy_service().build_leaderboard(kind, page=page, page_size=page_size)


def format_leaderboard_text(result: dict[str, Any]) -> str:
    return _legacy_service().format_leaderboard_text(result)


def compute_duel_odds(challenger_tg: int, defender_tg: int, **kwargs: Any) -> dict[str, Any]:
    return _legacy_service().compute_duel_odds(challenger_tg, defender_tg, **kwargs)


def assert_duel_stake_affordable(challenger_profile: dict[str, Any], defender_profile: dict[str, Any], stake: int) -> None:
    return _legacy_service().assert_duel_stake_affordable(challenger_profile, defender_profile, stake)


def resolve_duel(challenger_tg: int, defender_tg: int, stake: int = 0, **kwargs: Any) -> dict[str, Any]:
    return _legacy_service().resolve_duel(challenger_tg, defender_tg, stake=stake, **kwargs)


def format_duel_settlement_text(result: dict[str, Any], bet_settlement: dict[str, Any] | None = None, page: int = 1, page_size: int = 10) -> str:
    return _legacy_service().format_duel_settlement_text(result, bet_settlement=bet_settlement, page=page, page_size=page_size)


def generate_duel_preview_text(duel: dict[str, Any], stake: int = 0, **kwargs: Any) -> str:
    return _legacy_service().generate_duel_preview_text(duel, stake=stake, **kwargs)


def list_group_arenas(**kwargs: Any) -> list[dict[str, Any]]:
    return _legacy_service().list_group_arenas(**kwargs)


def get_group_arena(arena_id: int) -> dict[str, Any] | None:
    return _legacy_service().get_group_arena(arena_id)


def get_active_group_arena(group_chat_id: int, realm_stage: str | None = None) -> dict[str, Any] | None:
    return _legacy_service().get_active_group_arena(group_chat_id, realm_stage=realm_stage)


def patch_group_arena(arena_id: int, **kwargs: Any) -> dict[str, Any] | None:
    return _legacy_service().patch_group_arena(arena_id, **kwargs)


def open_group_arena_for_user(tg: int, **kwargs: Any) -> dict[str, Any]:
    return _legacy_service().open_group_arena_for_user(tg, **kwargs)


def challenge_group_arena_for_user(arena_id: int, challenger_tg: int, **kwargs: Any) -> dict[str, Any]:
    return _legacy_service().challenge_group_arena_for_user(arena_id, challenger_tg, **kwargs)


def finalize_group_arena(arena_id: int, *, force: bool = False) -> dict[str, Any] | None:
    return _legacy_service().finalize_group_arena(arena_id, force=force)


def cancel_group_arena(arena_id: int, **kwargs: Any) -> dict[str, Any] | None:
    return _legacy_service().cancel_group_arena(arena_id, **kwargs)
