from __future__ import annotations

from typing import Any


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def set_gender_for_user(tg: int, gender: str) -> dict[str, Any]:
    return _legacy_service().set_gender_for_user(tg, gender)


def create_marriage_request_for_user(tg: int, target_tg: int, message: str = "") -> dict[str, Any]:
    return _legacy_service().create_marriage_request_for_user(tg, target_tg, message=message)


def respond_marriage_request_for_user(tg: int, request_id: int, action: str) -> dict[str, Any]:
    return _legacy_service().respond_marriage_request_for_user(tg, request_id, action)


def dual_cultivate_with_spouse(tg: int) -> dict[str, Any]:
    return _legacy_service().dual_cultivate_with_spouse(tg)


def divorce_with_spouse(tg: int) -> dict[str, Any]:
    return _legacy_service().divorce_with_spouse(tg)
