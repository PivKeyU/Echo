from __future__ import annotations

from typing import Any


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def create_mentorship_request_for_user(tg: int, target_tg: int, sponsor_role: str, message: str = "") -> dict[str, Any]:
    return _legacy_service().create_mentorship_request_for_user(tg, target_tg, sponsor_role, message=message)


def respond_mentorship_request_for_user(tg: int, request_id: int, action: str) -> dict[str, Any]:
    return _legacy_service().respond_mentorship_request_for_user(tg, request_id, action)


def mentor_teach_for_user(tg: int, disciple_tg: int) -> dict[str, Any]:
    return _legacy_service().mentor_teach_for_user(tg, disciple_tg)


def consult_mentor_for_user(tg: int) -> dict[str, Any]:
    return _legacy_service().consult_mentor_for_user(tg)


def graduate_mentorship_for_user(tg: int, target_tg: int) -> dict[str, Any]:
    return _legacy_service().graduate_mentorship_for_user(tg, target_tg)


def dissolve_mentorship_for_user(tg: int, target_tg: int) -> dict[str, Any]:
    return _legacy_service().dissolve_mentorship_for_user(tg, target_tg)
