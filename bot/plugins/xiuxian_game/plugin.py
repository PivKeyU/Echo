from __future__ import annotations

# Entry point for the xiuxian_game plugin.
# Lazy-import heavy modules to speed up process startup and plugin discovery.


def register_bot(bot, context=None) -> None:
    from .plugin_bot_handlers import register_bot as _register_bot

    _register_bot(bot)


def register_web(app, context=None) -> None:
    from .plugin_web_routes import register_web as _register_web

    _register_web(app)


__all__ = ["register_bot", "register_web"]
