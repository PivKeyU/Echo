"""修仙游戏常量 — 从 service.py 和 sql_xiuxian.py 提取，无外部依赖。"""

# 灵根常量
ROOT_SPECIAL_BONUS = {
    "天灵根": 15,
    "地灵根": 10,
}
ROOT_COMMON_QUALITY_ORDER = ["废灵根", "下品灵根", "中品灵根", "上品灵根", "极品灵根"]
ROOT_SPECIAL_QUALITIES = {"天灵根", "变异灵根"}
ROOT_TRANSFORM_PILL_TYPES = {"root_single", "root_double", "root_earth", "root_heaven", "root_variant"}

# 丹药批量使用类型 — clear_poison 刻意排除，防止无限堆属性破坏数值体系
PILL_BATCH_USE_TYPES = {
    "attack",
    "body_movement",
    "bone",
    "charisma",
    "comprehension",
    "cultivation",
    "defense",
    "divine_sense",
    "fortune",
    "karma",
    "qi_blood",
    "true_yuan",
    "willpower",
}
# clear_poison 刻意不加入批量使用，防止丹毒循环叠加：
# 1. 批量服用属性丹药 → 丹毒 >= 100
# 2. 批量服用清毒丹 → 丹毒归零
# 3. 循环往复 → 唯一限制只剩背包数量
# 排除后，清毒只能单次手动使用，数值体系不会被无限放大。

ROOT_COMBAT_BASELINE_QUALITY = "中品灵根"
ROOT_COMBAT_FACTOR_MIN = 0.97
ROOT_COMBAT_FACTOR_MAX = 1.06
ROOT_ELEMENT_FACTOR_WEIGHT = 0.35
ROOT_VARIANT_FACTOR_BONUS = 0.01

# 商店名称
PERSONAL_SHOP_NAME = "游仙小铺"
OFFICIAL_RECYCLE_NAME = "万宝归炉"
IMMORTAL_STONE_NAME = "仙界奇石"

# 物品类型
GAMBLING_SUPPORTED_ITEM_KINDS = {"artifact", "pill", "talisman", "material", "recipe", "technique"}
RECYCLABLE_ITEM_KINDS = {"artifact", "pill", "talisman", "material", "technique", "recipe"}

# 开局赠送
STARTER_TECHNIQUE_NAME = "长青诀"
STARTER_TITLE_NAME = "初入仙途"
STARTER_FOUNDATION_PILL_NAME = "筑基丹"

# 境界
FIRST_REALM_STAGE = "炼气"
