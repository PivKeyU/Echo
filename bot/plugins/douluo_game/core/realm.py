"""魂师境界、行动力与魂环年限等核心数值定义(数据驱动)。"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 魂师境界:魂士 -> 魂师 -> 大魂师 -> 魂尊 -> 魂宗 -> 魂王 -> 魂帝 -> 魂圣
#            -> 魂斗罗 -> 封号斗罗 -> 神
# ---------------------------------------------------------------------------
DEFAULT_REALM_THRESHOLDS: list[dict[str, Any]] = [
    {"stage": "魂士", "star_cap": 9, "soul_power_per_star": 100},
    {"stage": "魂师", "star_cap": 9, "soul_power_per_star": 220},
    {"stage": "大魂师", "star_cap": 9, "soul_power_per_star": 380},
    {"stage": "魂尊", "star_cap": 9, "soul_power_per_star": 620},
    {"stage": "魂宗", "star_cap": 9, "soul_power_per_star": 920},
    {"stage": "魂王", "star_cap": 9, "soul_power_per_star": 1320},
    {"stage": "魂帝", "star_cap": 9, "soul_power_per_star": 1850},
    {"stage": "魂圣", "star_cap": 9, "soul_power_per_star": 2550},
    {"stage": "魂斗罗", "star_cap": 9, "soul_power_per_star": 3400},
    {"stage": "封号斗罗", "star_cap": 9, "soul_power_per_star": 5200},
    {"stage": "神", "star_cap": 1, "soul_power_per_star": 12000},
]

# 境界对应的基础战力量级(用于战力公式与斗魂结算)
REALM_BASE_POWER: dict[str, int] = {
    "魂士": 1000,
    "魂师": 5000,
    "大魂师": 12000,
    "魂尊": 25000,
    "魂宗": 45000,
    "魂王": 80000,
    "魂帝": 140000,
    "魂圣": 230000,
    "魂斗罗": 360000,
    "封号斗罗": 550000,
    "神": 900000,
}

# 武魂品质系数(战力加成)
WUHUN_QUALITY_POWER: dict[str, float] = {
    "凡品": 1.0,
    "良品": 1.25,
    "精品": 1.6,
    "珍品": 2.1,
    "神品": 2.8,
}

# 武魂系别系数(同品质下的系别差异)
WUHUN_SYSTEM_POWER: dict[str, float] = {
    "强攻": 1.2,
    "敏攻": 1.05,
    "防御": 1.0,
    "辅助": 0.9,
    "控制": 1.1,
}

# 封号斗罗突破时随机分配的封号
TITLED_DOULUO_TITLES: list[str] = [
    "昊天", "千手", "冰碧", "剑", "骨", "蓝电", "啸天", "柔骨",
    "毒", "天使", "海神", "修罗", "破魂", "星罗", "圣龙",
]

# ---------------------------------------------------------------------------
# 每日行动次数限制
# ---------------------------------------------------------------------------
DEFAULT_DAILY_ACTION_LIMITS: dict[str, int] = {
    "train": 5,
    "hunt": 3,
    "duel": 3,
    "auction": 3,
    "boss": 2,
    "exchange": 3,
    "wuhun": 1,
    "sect": 3,
    "salary": 1,
    "breakthrough": 3,
}

# 各行动消耗的行动力
DEFAULT_ACTION_POINT_COSTS: dict[str, int] = {
    "train": 1,
    "hunt": 2,
    "duel": 2,
    "auction": 1,
    "boss": 3,
    "exchange": 1,
    "wuhun": 1,
    "sect": 1,
    "salary": 1,
    "breakthrough": 2,
}

ACTION_TYPE_LABELS: dict[str, str] = {
    "train": "魂力修炼",
    "hunt": "猎杀魂兽",
    "duel": "斗魂",
    "auction": "拍卖",
    "boss": "讨伐",
    "exchange": "兑换",
    "wuhun": "武魂觉醒",
    "sect": "宗门",
    "salary": "俸禄",
    "breakthrough": "突破",
}

# ---------------------------------------------------------------------------
# 突破规则(满星突破到下一境界)
# ---------------------------------------------------------------------------
BREAKTHROUGH_RULES: dict[str, dict[str, Any]] = {
    "魂士": {"coin_cost": 80, "success_percent": 80, "pity_after": 2},
    "魂师": {"coin_cost": 120, "success_percent": 72, "pity_after": 3},
    "大魂师": {"coin_cost": 220, "success_percent": 65, "pity_after": 3},
    "魂尊": {"coin_cost": 420, "success_percent": 60, "pity_after": 4},
    "魂宗": {"coin_cost": 800, "success_percent": 55, "pity_after": 4},
    "魂王": {"coin_cost": 1500, "success_percent": 50, "pity_after": 5},
    "魂帝": {"coin_cost": 2600, "success_percent": 45, "pity_after": 5},
    "魂圣": {"coin_cost": 4200, "success_percent": 42, "pity_after": 5},
    "魂斗罗": {"coin_cost": 7000, "success_percent": 40, "pity_after": 6},
    "封号斗罗": {"coin_cost": 12000, "success_percent": 38, "pity_after": 6},
    "神": {"coin_cost": 50000, "success_percent": 35, "pity_after": 8},
}

# ---------------------------------------------------------------------------
# 魂环年限档位(十年 -> 百万年)
# ---------------------------------------------------------------------------
RING_TIERS: list[dict[str, Any]] = [
    {"tier": "十年", "color": "白", "year_min": 10, "year_max": 99, "stat_mult": 1.0},
    {"tier": "百年", "color": "黄", "year_min": 100, "year_max": 999, "stat_mult": 1.5},
    {"tier": "千年", "color": "紫", "year_min": 1000, "year_max": 9999, "stat_mult": 2.5},
    {"tier": "万年", "color": "黑", "year_min": 10000, "year_max": 99999, "stat_mult": 4.0},
    {"tier": "十万年", "color": "红", "year_min": 100000, "year_max": 999999, "stat_mult": 6.0},
    {"tier": "百万年", "color": "蓝金", "year_min": 1000000, "year_max": 9999999, "stat_mult": 9.0},
]

RING_SLOT_CAP = 9

# 每个境界可吸收的魂环最高年限档位(索引对应 RING_TIERS)
REALM_MAX_RING_TIER: dict[str, str] = {
    "魂士": "百年",
    "魂师": "百年",
    "大魂师": "千年",
    "魂尊": "千年",
    "魂宗": "千年",
    "魂王": "万年",
    "魂帝": "万年",
    "魂圣": "万年",
    "魂斗罗": "十万年",
    "封号斗罗": "十万年",
    "神": "百万年",
}

# 魂环基础属性:每档年限的基础攻击/防御/速度/精神
RING_TIER_BASE_STATS: dict[str, dict[str, int]] = {
    "十年": {"attack": 10, "defense": 10, "speed": 4, "spirit": 4},
    "百年": {"attack": 30, "defense": 30, "speed": 12, "spirit": 12},
    "千年": {"attack": 90, "defense": 90, "speed": 36, "spirit": 36},
    "万年": {"attack": 240, "defense": 240, "speed": 96, "spirit": 96},
    "十万年": {"attack": 600, "defense": 600, "speed": 240, "spirit": 240},
    "百万年": {"attack": 1500, "defense": 1500, "speed": 600, "spirit": 600},
}

# ---------------------------------------------------------------------------
# 魂骨部位
# ---------------------------------------------------------------------------
SOUL_BONE_PARTS: list[str] = ["头骨", "左臂骨", "右臂骨", "左腿骨", "右腿骨", "躯干骨"]

SOUL_BONE_RARITY_POWER: dict[str, float] = {
    "十年": 1.0,
    "百年": 1.6,
    "千年": 2.6,
    "万年": 4.0,
    "十万年": 6.0,
    "神级": 9.0,
}

# 装备槽位常量
EQUIP_SLOT_WEAPON = "weapon"


def ring_tier_of_year(year: int) -> dict[str, Any] | None:
    for tier in RING_TIERS:
        if int(year) >= tier["year_min"] and int(year) <= tier["year_max"]:
            return tier
    return None


def tier_by_name(name: str) -> dict[str, Any] | None:
    for tier in RING_TIERS:
        if tier["tier"] == str(name or ""):
            return tier
    return None


def ring_stats_for_year(year: int) -> dict[str, int]:
    tier = ring_tier_of_year(int(year))
    if tier is None:
        tier = RING_TIERS[-1]
    base = RING_TIER_BASE_STATS.get(tier["tier"], RING_TIER_BASE_STATS["十年"])
    mult = float(tier["stat_mult"])
    progress = 1.0
    span = max(int(tier["year_max"]) - int(tier["year_min"]), 1)
    if int(year) > int(tier["year_min"]):
        progress = 1.0 + 0.5 * (int(year) - int(tier["year_min"])) / span
    return {
        "attack": max(int(base["attack"] * mult * progress), 1),
        "defense": max(int(base["defense"] * mult * progress), 1),
        "speed": max(int(base["speed"] * mult * progress), 1),
        "spirit": max(int(base["spirit"] * mult * progress), 1),
    }


def max_allowed_ring_tier(stage: str) -> dict[str, Any] | None:
    tier_name = REALM_MAX_RING_TIER.get(str(stage or ""))
    if tier_name is None:
        return None
    return tier_by_name(tier_name)


def realm_index(stage: str) -> int:
    for index, row in enumerate(DEFAULT_REALM_THRESHOLDS):
        if row["stage"] == str(stage or ""):
            return index
    return 0


def realm_stages() -> list[str]:
    return [row["stage"] for row in DEFAULT_REALM_THRESHOLDS]


def total_soul_power_needed(stage: str, stars: int) -> int:
    """累计魂力需求:达到该境界星级所需的总魂力。"""
    idx = realm_index(stage)
    total = 0
    for row in DEFAULT_REALM_THRESHOLDS[: idx + 1]:
        stage_cap = int(row["star_cap"])
        fill = stage_cap if row["stage"] != stage else max(int(stars) - 1, 0)
        total += int(row["soul_power_per_star"]) * fill
    return total
