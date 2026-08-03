from __future__ import annotations

from typing import Any


def _legacy_world_service():
    from bot.plugins.xiuxian_game import world_service as legacy_world_service

    return legacy_world_service


def create_sect_with_roles(**kwargs) -> dict[str, Any]:
    return _legacy_world_service().create_sect_with_roles(**kwargs)


def sync_sect_with_roles_by_name(**kwargs) -> dict[str, Any]:
    return _legacy_world_service().sync_sect_with_roles_by_name(**kwargs)


def join_sect_for_user(tg: int, sect_id: int) -> dict[str, Any]:
    return _legacy_world_service().join_sect_for_user(tg, sect_id)


def leave_sect_for_user(tg: int) -> dict[str, Any]:
    return _legacy_world_service().leave_sect_for_user(tg)


def set_user_sect_role(tg: int, sect_id: int, role_key: str) -> dict[str, Any]:
    return _legacy_world_service().set_user_sect_role(tg, sect_id, role_key)


def claim_sect_salary_for_user(tg: int) -> dict[str, Any]:
    return _legacy_world_service().claim_sect_salary_for_user(tg)


def perform_sect_attendance(tg: int) -> dict[str, Any]:
    return _legacy_world_service().perform_sect_attendance(tg)


def perform_sect_teach(tg: int, cultivation_amount: int) -> dict[str, Any]:
    return _legacy_world_service().perform_sect_teach(tg, cultivation_amount)


def donate_item_to_sect_treasury(tg: int, item_kind: str, item_ref_id: int, quantity: int) -> dict[str, Any]:
    return _legacy_world_service().donate_item_to_sect_treasury(tg, item_kind, item_ref_id, quantity)
