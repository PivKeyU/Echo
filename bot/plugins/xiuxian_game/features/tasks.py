from __future__ import annotations

from typing import Any


def _legacy_world_service():
    from bot.plugins.xiuxian_game import world_service as legacy_world_service

    return legacy_world_service


def create_bounty_task(**kwargs) -> dict[str, Any]:
    return _legacy_world_service().create_bounty_task(**kwargs)


def list_tasks_for_user(tg: int) -> list[dict[str, Any]]:
    return _legacy_world_service().list_tasks_for_user(tg)


def claim_task_for_user(tg: int, task_id: int) -> dict[str, Any]:
    return _legacy_world_service().claim_task_for_user(tg, task_id)


def cancel_task_for_user(tg: int, task_id: int) -> dict[str, Any]:
    return _legacy_world_service().cancel_task_for_user(tg, task_id)


def resolve_quiz_answer(chat_id: int, tg: int, answer_text: str) -> dict[str, Any] | None:
    return _legacy_world_service().resolve_quiz_answer(chat_id, tg, answer_text)


def mark_task_group_message(task_id: int, chat_id: int, message_id: int) -> dict[str, Any]:
    return _legacy_world_service().mark_task_group_message(task_id, chat_id, message_id)
