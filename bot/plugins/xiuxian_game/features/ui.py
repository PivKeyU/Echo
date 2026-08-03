from __future__ import annotations

from bot.plugins.sdk import build_plugin_url as sdk_build_plugin_url


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def build_plugin_url(path: str) -> str | None:
    return sdk_build_plugin_url(path)


def xiuxian_confirm_keyboard():
    return _legacy_service().xiuxian_confirm_keyboard()


def xiuxian_profile_keyboard():
    return _legacy_service().xiuxian_profile_keyboard()


def leaderboard_keyboard(kind: str, page: int, total_pages: int):
    return _legacy_service().leaderboard_keyboard(kind, page, total_pages)


def duel_keyboard(challenger_tg: int, defender_tg: int, stake: int, bet_seconds: int, **kwargs):
    return _legacy_service().duel_keyboard(challenger_tg, defender_tg, stake, bet_seconds, **kwargs)
