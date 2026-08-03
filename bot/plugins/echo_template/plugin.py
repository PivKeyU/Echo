from __future__ import annotations

from fastapi import APIRouter
from pyrogram import filters

from bot import prefixes


def register_bot(bot) -> None:
    # Minimal bot-side probe for plugin activation checks.
    @bot.on_message(filters.command("plugin_ping", prefixes))
    async def plugin_ping(_, msg):
        await msg.reply_text("echo-template plugin is active")


def register_web(app) -> None:
    # Minimal web-side probe for plugin activation checks.
    router = APIRouter(prefix="/plugins/template", tags=["Template Plugin"])

    @router.get("/ping")
    async def ping():
        return {"ok": True, "plugin": "echo-template"}

    app.include_router(router)
