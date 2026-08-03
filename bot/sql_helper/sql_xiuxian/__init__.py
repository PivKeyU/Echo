"""修仙插件 ORM 模型与数据库读写封装 - 子包。

按领域拆分: constants, models, serializers, profile, items, shop, social, activities, combat。
__init__.py 重导出所有公共符号，保持外部 import 兼容。
"""

from __future__ import annotations

from .constants import *  # noqa: F401 F403
from .models import *  # noqa: F401 F403
from .serializers import *  # noqa: F401 F403
from .profile import *  # noqa: F401 F403
from .items import *  # noqa: F401 F403
from .shop import *  # noqa: F401 F403
from .social import *  # noqa: F401 F403
from .activities import *  # noqa: F401 F403
from .combat import *  # noqa: F401 F403
from .web_auth import *  # noqa: F401 F403


def cultivation_threshold(stage: str, layer: int) -> int:
    return calculate_realm_threshold(stage, layer)


__all__ = [name for name in globals() if not name.startswith("__")]
