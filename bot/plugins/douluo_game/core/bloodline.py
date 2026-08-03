"""血脉目录(龙王传说 / 终极斗罗)。

血脉是后续作品的核心战力来源:觉醒后逐级淬炼,每级按境界基础战力比例提供战力加成,
是魂斗罗之后的成长主线和战力大头。
"""

from __future__ import annotations

from typing import Any

# 血脉品质对应的每级战力系数(占当前境界基础战力的比例)
BLOODLINE_POWER_PERCENT: dict[str, float] = {
    "凡品": 0.006,
    "良品": 0.008,
    "精品": 0.011,
    "珍品": 0.016,
    "神品": 0.024,
}

# 觉醒所需境界(索引为境界最低要求)
BLOODLINE_AWAKEN_REALM = "魂尊"

# 淬炼成功率:随等级下降,公式见 service。此处为最高等级
BLOODLINE_MAX_LEVEL = 50

BLOODLINE_CATALOG: list[dict[str, Any]] = [
    {
        "key": "jinlongwang",
        "name": "金龙王血脉",
        "system": "龙",
        "rarity": "神品",
        "weight": 1,
        "skill": "金龙霸体",
        "description": "继承金龙王之力,肉身与魂力共鸣,爆发时金龙虚影护体。",
    },
    {
        "key": "yinlongwang",
        "name": "银龙王血脉",
        "system": "龙",
        "rarity": "神品",
        "weight": 1,
        "skill": "银龙之瞳",
        "description": "掌控元素本源,可窥破对手破绽,精神力深不可测。",
    },
    {
        "key": "xiuwo",
        "name": "修罗神血脉",
        "system": "神",
        "rarity": "神品",
        "weight": 1,
        "skill": "修罗血怒",
        "description": "神界修罗之力,越战越勇,杀意凝为实质。",
    },
    {
        "key": "shiguange",
        "name": "时光鳄血脉",
        "system": "兽",
        "rarity": "珍品",
        "weight": 2,
        "skill": "时间流速",
        "description": "掌控一缕时光之力,战斗中令对手招式迟滞。",
    },
    {
        "key": "bingbihuangxie",
        "name": "冰碧帝皇蝎血脉",
        "system": "兽",
        "rarity": "珍品",
        "weight": 2,
        "skill": "冰极无双",
        "description": "极致之冰血脉,寒冰凝甲,坚不可摧。",
    },
    {
        "key": "tianmengbingcan",
        "name": "天梦冰蚕血脉",
        "system": "兽",
        "rarity": "珍品",
        "weight": 2,
        "skill": "精神风暴",
        "description": "蕴含海量精神之力的上古血脉,精神力暴涨。",
    },
    {
        "key": "renyu",
        "name": "人鱼血脉",
        "system": "人",
        "rarity": "精品",
        "weight": 3,
        "skill": "碧波之澜",
        "description": "万年前的古老血脉,感知与亲和力极强。",
    },
    {
        "key": "taitanjuanyuan",
        "name": "泰坦巨猿血脉",
        "system": "兽",
        "rarity": "精品",
        "weight": 3,
        "skill": "泰坦巨力",
        "description": "力大无穷的蛮荒血脉,肉身力量惊人。",
    },
    {
        "key": "anmodongxiehu",
        "name": "暗魔邪神虎血脉",
        "system": "兽",
        "rarity": "精品",
        "weight": 3,
        "skill": "邪神噬魂",
        "description": "亦正亦邪的暗系血脉,攻防兼备。",
    },
    {
        "key": "zijinzhitong",
        "name": "紫金之瞳血脉",
        "system": "元素",
        "rarity": "良品",
        "weight": 4,
        "skill": "紫金瞳术",
        "description": "瞳术类血脉,可洞察魂力流动。",
    },
    {
        "key": "guangmingshenglong",
        "name": "光明圣龙血脉",
        "system": "龙",
        "rarity": "良品",
        "weight": 4,
        "skill": "圣光龙息",
        "description": "蕴含光明之力的龙族血脉,克制邪祟。",
    },
    {
        "key": "huofenghuang",
        "name": "火凤凰血脉",
        "system": "兽",
        "rarity": "良品",
        "weight": 4,
        "skill": "涅槃真火",
        "description": "浴火重生的凤凰血脉,生命顽强。",
    },
    {
        "key": "shanshui",
        "name": "山水血脉",
        "system": "元素",
        "rarity": "凡品",
        "weight": 5,
        "skill": "山河印",
        "description": "普通却沉稳的血脉,坚韧持久。",
    },
    {
        "key": "jingtong",
        "name": "金瞳血脉",
        "system": "人",
        "rarity": "凡品",
        "weight": 5,
        "skill": "洞察金瞳",
        "description": "较常见的上古血脉,聊胜于无。",
    },
]

# 品质 -> 权重区间,用于随机觉醒
BLOODLINE_WEIGHT_BY_RARITY: dict[str, int] = {
    "凡品": 20,
    "良品": 26,
    "精品": 26,
    "珍品": 18,
    "神品": 10,
}


def random_bloodline() -> dict[str, Any]:
    """按品质权重随机一条血脉。"""
    import random

    pool: list[dict[str, Any]] = []
    for item in BLOODLINE_CATALOG:
        rarity = str(item.get("rarity") or "凡品")
        weight = int(item.get("weight") or 1) * int(BLOODLINE_WEIGHT_BY_RARITY.get(rarity, 10))
        pool.extend([item] * weight)
    return dict(random.choice(pool))


def get_bloodline(key: str) -> dict[str, Any] | None:
    for item in BLOODLINE_CATALOG:
        if item.get("key") == str(key or ""):
            return dict(item)
    return None


def bloodline_power_per_level(bloodline: dict[str, Any], realm_base: int) -> int:
    """该血脉每级提供的战力(按境界基础战力比例)。"""
    rarity = str(bloodline.get("rarity") or "凡品")
    percent = BLOODLINE_POWER_PERCENT.get(rarity, BLOODLINE_POWER_PERCENT["凡品"])
    return max(int(int(realm_base) * percent), 1)
