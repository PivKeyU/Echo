"""修仙游戏核心模块 — 纯函数和常量，无数据库依赖。

所有 feature 文件都可以安全地从这里导入，不会产生循环依赖。
"""

from bot.plugins.xiuxian_game.core.constants import (
    FIRST_REALM_STAGE,
    GAMBLING_SUPPORTED_ITEM_KINDS,
    IMMORTAL_STONE_NAME,
    OFFICIAL_RECYCLE_NAME,
    PERSONAL_SHOP_NAME,
    PILL_BATCH_USE_TYPES,
    RECYCLABLE_ITEM_KINDS,
    ROOT_COMBAT_BASELINE_QUALITY,
    ROOT_COMBAT_FACTOR_MAX,
    ROOT_COMBAT_FACTOR_MIN,
    ROOT_COMMON_QUALITY_ORDER,
    ROOT_ELEMENT_FACTOR_WEIGHT,
    ROOT_SPECIAL_BONUS,
    ROOT_SPECIAL_QUALITIES,
    ROOT_TRANSFORM_PILL_TYPES,
    ROOT_VARIANT_FACTOR_BONUS,
    STARTER_FOUNDATION_PILL_NAME,
    STARTER_TECHNIQUE_NAME,
    STARTER_TITLE_NAME,
)

from bot.plugins.xiuxian_game.core.realm import (
    apply_cultivation_gain,
    realm_index,
    seclusion_cultivation_efficiency_percent,
)

__all__ = [
    # constants
    "FIRST_REALM_STAGE",
    "GAMBLING_SUPPORTED_ITEM_KINDS",
    "IMMORTAL_STONE_NAME",
    "OFFICIAL_RECYCLE_NAME",
    "PERSONAL_SHOP_NAME",
    "PILL_BATCH_USE_TYPES",
    "RECYCLABLE_ITEM_KINDS",
    "ROOT_COMBAT_BASELINE_QUALITY",
    "ROOT_COMBAT_FACTOR_MAX",
    "ROOT_COMBAT_FACTOR_MIN",
    "ROOT_COMMON_QUALITY_ORDER",
    "ROOT_ELEMENT_FACTOR_WEIGHT",
    "ROOT_SPECIAL_BONUS",
    "ROOT_SPECIAL_QUALITIES",
    "ROOT_TRANSFORM_PILL_TYPES",
    "ROOT_VARIANT_FACTOR_BONUS",
    "STARTER_FOUNDATION_PILL_NAME",
    "STARTER_TECHNIQUE_NAME",
    "STARTER_TITLE_NAME",
    # realm
    "apply_cultivation_gain",
    "realm_index",
    "seclusion_cultivation_efficiency_percent",
]
