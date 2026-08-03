from __future__ import annotations

from pyrogram import filters

from bot import LOGGER, bot
from bot.sql_helper.sql_bot_access import find_bot_access_block


def _maybe_stop_blocked_update(update, update_type: str) -> bool:
    user = getattr(update, "from_user", None)
    if user is None:
        return False

    tg = getattr(user, "id", None)
    username = getattr(user, "username", None)
    matched = find_bot_access_block(tg=tg, username=username)
    if matched is None:
        return False

    LOGGER.info(
        "bot access blocked update: "
        f"type={update_type} user={tg} username={username!r} "
        f"rule={matched.get('id')} match={matched.get('match_type')}"
    )
    stop_propagation = getattr(update, "stop_propagation", None)
    if callable(stop_propagation):
        stop_propagation()
    return True


@bot.on_message(filters.all, group=-2000)
async def guard_blocked_message(_, message):
    _maybe_stop_blocked_update(message, "message")


@bot.on_callback_query(filters.all, group=-2000)
async def guard_blocked_callback(_, callback_query):
    _maybe_stop_blocked_update(callback_query, "callback_query")


@bot.on_inline_query(filters.all, group=-2000)
async def guard_blocked_inline_query(_, inline_query):
    _maybe_stop_blocked_update(inline_query, "inline_query")
