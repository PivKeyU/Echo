"""魂导器目录(绝世唐门 · 魂导师锻造产物)。

魂导师(魂师修炼到一定境界后专精锻造)消耗材料锻造魂导器,装备到专属槽位
(soul_weapon / soul_shield / soul_jet)。锻造消耗行动力,并为魂导师积累经验提升等阶。
"""

from __future__ import annotations

from typing import Any

# 魂导师等阶所需的累计经验阈值:升到第 N 阶所需总经验
CRAFTSMAN_RANK_EXP: list[int] = [0, 80, 200, 380, 620, 940, 1360, 1880, 2520, 3300]

# 装备槽位
SLOT_SOUL_WEAPON = "soul_weapon"
SLOT_SOUL_SHIELD = "soul_shield"
SLOT_SOUL_JET = "soul_jet"

SOUL_DEVICE_CATALOG: list[dict[str, Any]] = [
    # ---------------- 魂导武器(soul_weapon) ----------------
    {
        "key": "tiezhuazhao",
        "name": "魂导爪·铁爪",
        "rarity": "凡品",
        "equipment_slot": SLOT_SOUL_WEAPON,
        "attack": 140,
        "defense": 0,
        "speed": 20,
        "spirit": 0,
        "trigger_chance": 0.06,
        "skill": "裂甲",
        "craftsman_rank": 1,
        "recipe": {"tiejing": 4, "miyin": 2},
        "craft_coin": 300,
        "description": "魂导师入门的试制魂导爪。",
    },
    {
        "key": "zhuihun_pao",
        "name": "魂导炮·追魂",
        "rarity": "良品",
        "equipment_slot": SLOT_SOUL_WEAPON,
        "attack": 320,
        "defense": 0,
        "speed": 40,
        "spirit": 0,
        "trigger_chance": 0.08,
        "skill": "爆裂弹",
        "craftsman_rank": 2,
        "recipe": {"tiejing": 8, "miyin": 4, "xuantie": 2},
        "craft_coin": 800,
        "description": "追魂炮可锁敌轰击,射程极远。",
    },
    {
        "key": "yinyue_ren",
        "name": "魂导刃·银月",
        "rarity": "精品",
        "equipment_slot": SLOT_SOUL_WEAPON,
        "attack": 620,
        "defense": 0,
        "speed": 90,
        "spirit": 0,
        "trigger_chance": 0.12,
        "skill": "月牙斩",
        "craftsman_rank": 4,
        "recipe": {"xuantie": 6, "xingchengang": 4, "tianwaitie": 2, "huolingshi": 2},
        "craft_coin": 2400,
        "description": "灌注火元力的近战魂导刃,削铁如泥。",
    },
    {
        "key": "chenmo_pao",
        "name": "魂导炮·尘魔",
        "rarity": "珍品",
        "equipment_slot": SLOT_SOUL_WEAPON,
        "attack": 1150,
        "defense": 0,
        "speed": 60,
        "spirit": 0,
        "trigger_chance": 0.15,
        "skill": "轰天炮",
        "craftsman_rank": 6,
        "recipe": {"tianwaitie": 6, "shenhaiyinyin": 4, "hunshoujingxue": 3, "bingsui": 2},
        "craft_coin": 6200,
        "description": "以魂兽精血驱动的重型魂导炮。",
    },
    {
        "key": "juexian_ji",
        "name": "魂导刃·绝线",
        "rarity": "神品",
        "equipment_slot": SLOT_SOUL_WEAPON,
        "attack": 2100,
        "defense": 0,
        "speed": 160,
        "spirit": 0,
        "trigger_chance": 0.2,
        "skill": "虚空斩",
        "craftsman_rank": 9,
        "recipe": {"shenqijijin": 4, "shenhaiyinyin": 6, "hunshoujingxue": 5, "bingsui": 4},
        "craft_coin": 16000,
        "description": "近乎神器的魂导利刃,可斩开空间。",
    },
    # ---------------- 魂导护盾(soul_shield) ----------------
    {
        "key": "xutie_dun",
        "name": "魂导盾·虚铁",
        "rarity": "良品",
        "equipment_slot": SLOT_SOUL_SHIELD,
        "attack": 0,
        "defense": 260,
        "speed": 0,
        "spirit": 40,
        "trigger_chance": 0.1,
        "skill": "铁壁",
        "craftsman_rank": 2,
        "recipe": {"tiejing": 10, "miyin": 3, "xuantie": 2},
        "craft_coin": 700,
        "description": "基础的魂导护盾,可展开能量屏障。",
    },
    {
        "key": "mancang_ju",
        "name": "魂导护具·蛮苍",
        "rarity": "精品",
        "equipment_slot": SLOT_SOUL_SHIELD,
        "attack": 0,
        "defense": 520,
        "speed": 0,
        "spirit": 90,
        "trigger_chance": 0.13,
        "skill": "苍御",
        "craftsman_rank": 4,
        "recipe": {"xuantie": 8, "xingchengang": 5, "shenhaiyinyin": 2},
        "craft_coin": 2200,
        "description": "以深海沉银加固的护盾,坚固异常。",
    },
    {
        "key": "dongpo_dun",
        "name": "魂导盾·冻魄",
        "rarity": "珍品",
        "equipment_slot": SLOT_SOUL_SHIELD,
        "attack": 0,
        "defense": 980,
        "speed": 0,
        "spirit": 200,
        "trigger_chance": 0.16,
        "skill": "极冻壁垒",
        "craftsman_rank": 6,
        "recipe": {"bingsui": 6, "shenhaiyinyin": 4, "tianwaitie": 4, "hunshoujingxue": 2},
        "craft_coin": 5800,
        "description": "冰髓之力凝成的护盾,可冰封近敌。",
    },
    # ---------------- 魂导推进器(soul_jet) ----------------
    {
        "key": "xunfeng_tui",
        "name": "魂导推进器·迅风",
        "rarity": "良品",
        "equipment_slot": SLOT_SOUL_JET,
        "attack": 0,
        "defense": 0,
        "speed": 220,
        "spirit": 40,
        "trigger_chance": 0.1,
        "skill": "疾风",
        "craftsman_rank": 3,
        "recipe": {"tiejing": 6, "xingchengang": 3, "miyin": 4},
        "craft_coin": 900,
        "description": "喷气式推进器,大幅提升机动性。",
    },
    {
        "key": "leiyan_tui",
        "name": "魂导推进器·雷焰",
        "rarity": "精品",
        "equipment_slot": SLOT_SOUL_JET,
        "attack": 0,
        "defense": 0,
        "speed": 480,
        "spirit": 120,
        "trigger_chance": 0.13,
        "skill": "雷闪",
        "craftsman_rank": 5,
        "recipe": {"huolingshi": 5, "xingchengang": 5, "tianwaitie": 3},
        "craft_coin": 2600,
        "description": "雷火双驱推进,速度冠绝同级。",
    },
    {
        "key": "tianhe_chi",
        "name": "魂导翼·天河",
        "rarity": "神品",
        "equipment_slot": SLOT_SOUL_JET,
        "attack": 0,
        "defense": 0,
        "speed": 1100,
        "spirit": 260,
        "trigger_chance": 0.18,
        "skill": "天河穿梭",
        "craftsman_rank": 9,
        "recipe": {"shenqijijin": 3, "hunshoujingxue": 6, "shenhaiyinyin": 6, "xingchengang": 6},
        "craft_coin": 15000,
        "description": "可短暂穿梭空间的传奇魂导翼。",
    },
]


def soul_device_by_key(key: str) -> dict[str, Any] | None:
    for item in SOUL_DEVICE_CATALOG:
        if item.get("key") == str(key or ""):
            return dict(item)
    return None


def craftsman_rank_from_exp(exp: int) -> tuple[int, int, int]:
    """根据经验返回 (当前阶, 本阶下限经验, 下一阶所需经验)。"""
    exp = max(int(exp or 0), 0)
    rank = 1
    lower = 0
    upper = CRAFTSMAN_RANK_EXP[1] if len(CRAFTSMAN_RANK_EXP) > 1 else exp
    for index in range(1, len(CRAFTSMAN_RANK_EXP)):
        if exp >= CRAFTSMAN_RANK_EXP[index]:
            rank = index + 1
            lower = CRAFTSMAN_RANK_EXP[index]
            upper = CRAFTSMAN_RANK_EXP[index + 1] if index + 1 < len(CRAFTSMAN_RANK_EXP) else exp
    if rank >= len(CRAFTSMAN_RANK_EXP):
        upper = lower
    return rank, lower, upper
