"""斗铠目录(龙王传说)。

六字斗铠,穿戴到专属槽位 battle_armor。斗铠以基础形态(一字)获得后,
消耗锻造材料与魂币逐级淬炼升级。每阶有境界门槛。
"""

from __future__ import annotations

from typing import Any

EQUIP_SLOT_BATTLE_ARMOR = "battle_armor"

BATTLE_ARMOR_ITEM_KEY = "battle_armor"

BATTLE_ARMOR_TIERS: list[dict[str, Any]] = [
    {
        "tier": 1,
        "name": "一字斗铠",
        "rarity": "凡品",
        "realm_required": "魂王",
        "attack": 300,
        "defense": 800,
        "speed": 120,
        "spirit": 200,
        "trigger_chance": 0.05,
        "skill": "斗铠初成",
        "recipe": {"tiejing": 18, "miyin": 8, "xuantie": 4},
        "coin": 2000,
        "description": "以稀有金属锻成的基础斗铠,贴合身形增幅魂力。",
    },
    {
        "tier": 2,
        "name": "二字斗铠",
        "rarity": "良品",
        "realm_required": "魂帝",
        "attack": 700,
        "defense": 1800,
        "speed": 260,
        "spirit": 450,
        "trigger_chance": 0.08,
        "skill": "斗铠护魂",
        "recipe": {"xuantie": 10, "xingchengang": 6, "tianwaitie": 3},
        "coin": 4200,
        "description": "融入星辰钢,防御与魂力增幅显著提升。",
    },
    {
        "tier": 3,
        "name": "三字斗铠",
        "rarity": "精品",
        "realm_required": "魂圣",
        "attack": 1500,
        "defense": 3600,
        "speed": 500,
        "spirit": 900,
        "trigger_chance": 0.11,
        "skill": "斗铠领域",
        "recipe": {"tianwaitie": 8, "xingchengang": 8, "huolingshi": 4, "bingsui": 3},
        "coin": 8000,
        "description": "可展开小型领域,压制对手魂力运转。",
    },
    {
        "tier": 4,
        "name": "四字斗铠",
        "rarity": "珍品",
        "realm_required": "魂斗罗",
        "attack": 3200,
        "defense": 7200,
        "speed": 950,
        "spirit": 1800,
        "trigger_chance": 0.14,
        "skill": "斗铠进化",
        "recipe": {"shenhaiyinyin": 8, "hunshoujingxue": 5, "bingsui": 5, "tianwaitie": 6},
        "coin": 15000,
        "description": "以魂兽精血淬炼,铠内自成小天地。",
    },
    {
        "tier": 5,
        "name": "五字斗铠",
        "rarity": "神品",
        "realm_required": "封号斗罗",
        "attack": 6800,
        "defense": 15000,
        "speed": 1900,
        "spirit": 3600,
        "trigger_chance": 0.18,
        "skill": "斗铠神化",
        "recipe": {"hunshoujingxue": 10, "shenqijijin": 4, "shenhaiyinyin": 10, "huolingshi": 6},
        "coin": 30000,
        "description": "接近神器的存在,可引动天地之力。",
    },
    {
        "tier": 6,
        "name": "六字斗铠",
        "rarity": "神品",
        "realm_required": "神王",
        "attack": 15000,
        "defense": 36000,
        "speed": 4200,
        "spirit": 8000,
        "trigger_chance": 0.25,
        "skill": "斗铠神王",
        "recipe": {"shenqijijin": 10, "hunshoujingxue": 14, "shenhaiyinyin": 16, "bingsui": 10},
        "coin": 80000,
        "description": "传说中神王才能驾驭的至强斗铠,威压天地。",
    },
]


def battle_armor_tier_by_index(index: int) -> dict[str, Any] | None:
    for item in BATTLE_ARMOR_TIERS:
        if int(item["tier"]) == int(index):
            return dict(item)
    return None
