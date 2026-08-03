"""锻造材料目录(绝世唐门 · 魂导师)。

勘探(prospect)产出的材料,用于魂导器锻造与斗铠淬炼。
"""

from __future__ import annotations

from typing import Any

MATERIAL_CATALOG: list[dict[str, Any]] = [
    {"key": "tiejing", "name": "铁精", "rarity": "凡品", "weight": 30, "description": "精炼铁矿,魂导器的基础材料。"},
    {"key": "miyin", "name": "秘银", "rarity": "良品", "weight": 22, "description": "导魂性极佳的银白金属。"},
    {"key": "xuantie", "name": "玄铁", "rarity": "良品", "weight": 20, "description": "密度惊人的重铁,锻造核心。"},
    {"key": "xingchengang", "name": "星辰钢", "rarity": "精品", "weight": 14, "description": "陨落星辰淬炼的合金。"},
    {"key": "tianwaitie", "name": "天外陨铁", "rarity": "精品", "weight": 12, "description": "天外坠落的奇铁,蕴含奇异能量。"},
    {"key": "bingsui", "name": "冰髓", "rarity": "珍品", "weight": 8, "description": "极寒之地亿年冰晶,内藏冰之本源。"},
    {"key": "huolingshi", "name": "火灵石", "rarity": "珍品", "weight": 7, "description": "地脉火元凝聚的灵石。"},
    {"key": "shenhaiyinyin", "name": "深海沉银", "rarity": "珍品", "weight": 6, "description": "深海高压下形成的稀有银矿。"},
    {"key": "hunshoujingxue", "name": "魂兽精血", "rarity": "珍品", "weight": 5, "description": "高阶魂兽的精血,激活装备潜能。"},
    {"key": "shenqijijin", "name": "神赐奇金", "rarity": "神品", "weight": 2, "description": "蕴含神性力量的奇金,极其稀有。"},
]

# 品质 -> 权重(勘探骰)
MATERIAL_WEIGHT_BY_RARITY: dict[str, int] = {
    "凡品": 34,
    "良品": 28,
    "精品": 20,
    "珍品": 14,
    "神品": 6,
}

# 勘探区域:按境界解锁,产出材料品质随区域提升
PROSPECT_REGIONS: list[dict[str, Any]] = [
    {
        "key": "chengwai",
        "name": "城外荒矿",
        "realm_stage_min": "魂师",
        "entry_coin": 0,
        "rarity_tiers": ["凡品", "良品"],
        "materials": ["tiejing", "miyin", "xuantie"],
    },
    {
        "key": "riyue",
        "name": "日月皇家矿场",
        "realm_stage_min": "魂宗",
        "entry_coin": 200,
        "rarity_tiers": ["良品", "精品"],
        "materials": ["miyin", "xuantie", "xingchengang", "tianwaitie"],
    },
    {
        "key": "mingdu",
        "name": "明都地下矿脉",
        "realm_stage_min": "魂圣",
        "entry_coin": 600,
        "rarity_tiers": ["精品", "珍品"],
        "materials": ["xingchengang", "tianwaitie", "bingsui", "huolingshi", "shenhaiyinyin"],
    },
    {
        "key": "shenzang",
        "name": "神禁矿藏",
        "realm_stage_min": "封号斗罗",
        "entry_coin": 1500,
        "rarity_tiers": ["珍品", "神品"],
        "materials": ["bingsui", "huolingshi", "shenhaiyinyin", "hunshoujingxue", "shenqijijin"],
    },
]


def material_by_key(key: str) -> dict[str, Any] | None:
    for item in MATERIAL_CATALOG:
        if item.get("key") == str(key or ""):
            return dict(item)
    return None


def prospects_for_stage(stage: str) -> list[dict[str, Any]]:
    from bot.plugins.douluo_game.core.realm import realm_index

    idx = realm_index(str(stage or "魂士"))
    accessible = []
    for region in PROSPECT_REGIONS:
        if realm_index(str(region.get("realm_stage_min") or "魂士")) <= idx:
            accessible.append(region)
    return accessible


def prospect_region_by_key(key: str) -> dict[str, Any] | None:
    for region in PROSPECT_REGIONS:
        if region.get("key") == str(key or ""):
            return dict(region)
    return None
