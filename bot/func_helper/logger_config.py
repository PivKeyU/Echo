"""
logger_config -

Author:susu
Date:2023/12/12
"""
from __future__ import annotations

import datetime
import logging
import sys
import warnings

import pytz
from loguru import logger


class InterceptHandler(logging.Handler):
    """将标准 logging 的输出转发到 loguru，避免 warning/error 丢失。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        bound_logger = logger.bind(logger_name=record.name)
        bound_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _configure_standard_logging() -> None:
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    warnings.simplefilter("default")
    logging.captureWarnings(True)


# 转换为亚洲上海时区
shanghai_tz = pytz.timezone("Asia/Shanghai")
Now = datetime.datetime.now(shanghai_tz)
log_filename = f"log/log_{Now.strftime('%Y%m%d')}.txt"
log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS ZZ} | {extra[logger_name]} | {level} | {message}"

logger.remove()
logger.add(
    sys.stdout,
    format=log_format,
    level="INFO",
    enqueue=True,
    backtrace=True,
    diagnose=False,
)
logger.add(
    log_filename,
    format=log_format,
    level="INFO",
    rotation="00:00",
    retention="30 days",
    enqueue=True,
    backtrace=True,
    diagnose=False,
)
_configure_standard_logging()
logger = logger.bind(logger_name="app")


def logu(name):
    """返回一个绑定名称的日志实例"""
    return logger.bind(logger_name=name)
