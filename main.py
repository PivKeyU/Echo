#! /usr/bin/python3
# -*- coding: utf-8 -*-

import asyncio

from bot import bot, bot_token
from bot.func_helper.bot_watchdog import schedule_bot_watchdog

# 面板
from bot.modules.panel import *
# 命令
from bot.modules.commands import *
# 其他
from bot.modules.extra import *
from bot.modules.callback import *
from bot.plugins import load_plugins
from bot.web import *
from bot.web import check
from bot.func_helper.emby import emby
from bot.func_helper.moviepilot import close_moviepilot_session
from bot import LOGGER

try:
    load_plugins()
except Exception as exc:
    LOGGER.error(f"插件加载失败: {exc}")

schedule_bot_watchdog(bot, bot_token)

# Emotion 服务端适配器：联动启用时启动追更事件轮询。
try:
    from bot.func_helper.emotion import emotion_enabled, get_emotion_poller
    if emotion_enabled():
        get_emotion_poller().start()
        LOGGER.info("Emotion 服务端适配器已启用，追更事件轮询启动")
    else:
        LOGGER.info("Emotion 服务端适配器未启用（emotion.status=false 或未配置凭据）")
except Exception as exc:
    LOGGER.error(f"Emotion 适配器启动失败: {exc}")

try:
    bot.run()
finally:
    # Pyrogram's run() owns the current event loop but does not know about
    # auxiliary Uvicorn/aiohttp resources created by this application.
    # Always stop them on normal shutdown, SIGINT, or a bot startup error.
    try:
        from bot.func_helper.runtime import get_or_create_event_loop

        loop = get_or_create_event_loop()
        if not loop.is_closed():
            loop.run_until_complete(check.stop())
            loop.run_until_complete(emby.shutdown())
            loop.run_until_complete(close_moviepilot_session())
            try:
                from bot.func_helper.emotion import shutdown_emotion_adapter
                loop.run_until_complete(shutdown_emotion_adapter())
            except Exception as exc:
                LOGGER.error(f"Emotion 适配器关闭失败: {exc}")
    except Exception as exc:
        LOGGER.error(f"后台服务关闭失败: {exc}")
