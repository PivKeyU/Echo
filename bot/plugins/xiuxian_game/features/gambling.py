from __future__ import annotations

from typing import Any


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def build_gambling_bundle(tg: int, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    return _legacy_service().build_gambling_bundle(tg, bundle=bundle)


def exchange_immortal_stones(tg: int, count: int) -> dict[str, Any]:
    return _legacy_service().exchange_immortal_stones(tg, count)


def open_immortal_stones(tg: int, count: int) -> dict[str, Any]:
    return _legacy_service().open_immortal_stones(tg, count)
