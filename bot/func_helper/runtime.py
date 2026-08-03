from __future__ import annotations

import logging
import os


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning("环境变量 %s=%r 不是有效整数，回退到默认值 %s", name, raw, default)
        return default


def configure_runtime_limits(desired_nofile: int | None = None) -> None:
    logger = logging.getLogger(__name__)

    if os.name != "posix":
        return

    if desired_nofile is None:
        desired_nofile = _env_int("PIVKEYU_NOFILE_SOFT", 65535)

    try:
        import resource
    except ImportError:
        return

    try:
        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        target_hard = hard_limit
        target_soft = desired_nofile

        if hard_limit != resource.RLIM_INFINITY:
            target_soft = min(target_soft, hard_limit)

        if soft_limit >= target_soft:
            return

        resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, target_hard))
        logger.info("已将 RLIMIT_NOFILE 从 %s 提升到 %s", soft_limit, target_soft)
    except Exception as exc:
        logger.warning("提升 RLIMIT_NOFILE 失败：%s", exc)


def get_or_create_event_loop():
    """获取当前事件循环；不存在时创建并注册，兼容 Python 3.10~3.13。

    Python 3.12+ 中 ``asyncio.get_event_loop()`` 在无运行中循环且未设置
    事件循环策略时会抛 RuntimeError（3.10/3.11 则自动创建）。本项目在模块
    导入期（bot.run() 之前）多次调用 get_event_loop() 创建任务（web 服务、
    watchdog、调度器），需要统一入口保证跨版本行为一致。
    """
    import asyncio

    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
