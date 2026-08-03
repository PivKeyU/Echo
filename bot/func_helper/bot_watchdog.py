from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp

from bot.func_helper.logger_config import logu

LOGGER = logu(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = max(minimum, int(raw))
        if maximum is not None:
            value = min(value, maximum)
        return value
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


async def _probe_pyrogram(client: Any, timeout: int) -> tuple[bool, str]:
    try:
        await asyncio.wait_for(client.get_me(), timeout=timeout)
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def _probe_bot_api(bot_token: str, timeout: int) -> tuple[bool, str]:
    token = str(bot_token or "").strip()
    if not token:
        return False, "bot token is empty"

    url = f"https://api.telegram.org/bot{token}/getMe"
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return False, f"HTTP {response.status}"
                data = await response.json(content_type=None)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if not data.get("ok"):
        return False, str(data.get("description") or data)
    return True, ""


async def run_bot_watchdog(client: Any, bot_token: str) -> None:
    startup_grace = _env_int("PIVKEYU_BOT_WATCHDOG_STARTUP_GRACE", 180, minimum=15, maximum=3600)
    interval = _env_int("PIVKEYU_BOT_WATCHDOG_INTERVAL", 60, minimum=15, maximum=3600)
    timeout = _env_int("PIVKEYU_BOT_WATCHDOG_TIMEOUT", 8, minimum=2, maximum=60)
    max_failures = _env_int("PIVKEYU_BOT_WATCHDOG_FAILURES", 3, minimum=1, maximum=20)
    exit_code = _env_int("PIVKEYU_BOT_WATCHDOG_EXIT_CODE", 75, minimum=1, maximum=255)
    compare_bot_api = _env_bool("PIVKEYU_BOT_WATCHDOG_COMPARE_BOT_API", True)
    restart_on_network_failure = _env_bool("PIVKEYU_BOT_WATCHDOG_RESTART_ON_NETWORK_FAILURE", False)

    LOGGER.info(
        f"Bot 自愈看门狗已启用 interval={interval}s timeout={timeout}s "
        f"failures={max_failures} startup_grace={startup_grace}s"
    )
    await asyncio.sleep(startup_grace)

    consecutive_failures = 0
    while True:
        pyrogram_ok, pyrogram_detail = await _probe_pyrogram(client, timeout)
        if pyrogram_ok:
            if consecutive_failures:
                LOGGER.info("Bot 自愈看门狗检测到 Pyrogram 已恢复")
            consecutive_failures = 0
            await asyncio.sleep(interval)
            continue

        bot_api_ok = True
        bot_api_detail = "skipped"
        if compare_bot_api:
            bot_api_ok, bot_api_detail = await _probe_bot_api(bot_token, timeout)

        if bot_api_ok or restart_on_network_failure:
            consecutive_failures += 1
            LOGGER.warning(
                f"Bot 自愈看门狗检测失败 {consecutive_failures}/{max_failures}: "
                f"pyrogram={pyrogram_detail}; bot_api_ok={bot_api_ok}; bot_api={bot_api_detail}"
            )
        else:
            LOGGER.warning(
                f"Bot 自愈看门狗检测到 Telegram 侧连通性异常，暂不重启: "
                f"pyrogram={pyrogram_detail}; bot_api={bot_api_detail}"
            )
            consecutive_failures = 0

        if consecutive_failures >= max_failures:
            LOGGER.error("Bot 自愈看门狗判定 Pyrogram 已假死，即将退出进程交给 Docker 自动重启")
            await asyncio.sleep(1)
            os._exit(exit_code)

        await asyncio.sleep(interval)


def schedule_bot_watchdog(client: Any, bot_token: str) -> asyncio.Task | None:
    if not _env_bool("PIVKEYU_BOT_WATCHDOG_ENABLED", True):
        LOGGER.info("Bot 自愈看门狗未启用")
        return None

    from bot.func_helper.runtime import get_or_create_event_loop

    loop = get_or_create_event_loop()
    return loop.create_task(run_bot_watchdog(client, bot_token), name="bot-watchdog")
