"""魂核目录(绝世唐门)。

魂斗罗及以上境界凝聚魂核,穿戴到专属槽位 soul_core,提供巨额精神力与攻防。
凝聚结果随机,高阶境界可凝聚更高品阶魂核。
"""

from __future__ import annotations

from typing import Any

EQUIP_SLOT_SOUL_CORE = "soul_core"

SOUL_CORE_TIERS: list[dict[str, Any]] = [
    {
        "tier": 1,
        "item_key": "soul_core_1",
        "name": "基础魂核",
        "rarity": "凡品",
        "realm_required": "魂斗罗",
        "attack": 400,
        "defense": 400,
        "speed": 160,
        "spirit": 700,
        "trigger_chance": 0.05,
        "skill": "魂力共振",
        "description": "凝聚初成的魂核,蕴含澎湃魂力。",
    },
    {
        "tier": 2,
        "item_key": "soul_core_2",
        "name": "稳固魂核",
        "rarity": "良品",
        "realm_required": "封号斗罗",
        "attack": 900,
        "defense": 900,
        "speed": 350,
        "spirit": 1600,
        "trigger_chance": 0.08,
        "skill": "魂力泉涌",
        "description": "魂核稳固,魂力恢复大幅提升。",
    },
    {
        "tier": 3,
        "item_key": "soul_core_3",
        "name": "圆满魂核",
        "rarity": "精品",
        "realm_required": "封号斗罗",
        "attack": 1900,
        "defense": 1900,
        "speed": 720,
        "spirit": 3400,
        "trigger_chance": 0.12,
        "skill": "圆满无漏",
        "description": "圆融无缺的魂核,攻守兼备。",
    },
    {
        "tier": 4,
        "item_key": "soul_core_4",
        "name": "天阶魂核",
        "rarity": "珍品",
        "realm_required": "神",
        "attack": 4000,
        "defense": 4000,
        "speed": 1500,
        "spirit": 7200,
        "trigger_chance": 0.16,
        "skill": "天阶共鸣",
        "description": "沟通天地的天阶魂核,精神无边。",
    },
    {
        "tier": 5,
        "item_key": "soul_core_5",
        "name": "神阶魂核",
        "rarity": "神品",
        "realm_required": "神王",
        "attack": 9000,
        "defense": 9000,
        "speed": 3300,
        "spirit": 16000,
        "trigger_chance": 0.22,
        "skill": "神核不朽",
        "description": "蕴含神性的至强魂核,几乎不朽。",
    },
]


def soul_core_tier_by_index(index: int) -> dict[str, Any] | None:
    for item in SOUL_CORE_TIERS:
        if int(item["tier"]) == int(index):
            return dict(item)
    return None
