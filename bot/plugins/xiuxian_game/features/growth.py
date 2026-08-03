from __future__ import annotations

from typing import Any


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def ensure_seed_data(force: bool = False) -> None:
    return _legacy_service().ensure_seed_data(force=force)


def create_foundation_pill_for_user_if_missing(tg: int) -> None:
    return _legacy_service().create_foundation_pill_for_user_if_missing(tg)


def maybe_gain_cultivation_from_chat(tg: int) -> dict[str, Any] | None:
    return _legacy_service().maybe_gain_cultivation_from_chat(tg)


def immortal_touch_infuse_cultivation(actor_tg: int, target_tg: int) -> dict[str, Any]:
    return _legacy_service().immortal_touch_infuse_cultivation(actor_tg, target_tg)


def format_root(payload: dict[str, Any]) -> str:
    return _legacy_service().format_root(payload)


def init_path_for_user(tg: int) -> dict[str, Any]:
    return _legacy_service().init_path_for_user(tg)


def practice_for_user(tg: int) -> dict[str, Any]:
    return _legacy_service().practice_for_user(tg)


def breakthrough_for_user(tg: int, use_pill: bool = False) -> dict[str, Any]:
    return _legacy_service().breakthrough_for_user(tg, use_pill=use_pill)


def build_spirit_stone_commissions(tg: int) -> list[dict[str, Any]]:
    return _legacy_service().build_spirit_stone_commissions(tg)


def claim_spirit_stone_commission(
    tg: int,
    commission_key: str,
    *,
    include_profile: bool = True,
) -> dict[str, Any]:
    return _legacy_service().claim_spirit_stone_commission(
        tg,
        commission_key,
        include_profile=include_profile,
    )


def serialize_full_profile(tg: int) -> dict[str, Any]:
    return _legacy_service().serialize_full_profile(tg)
