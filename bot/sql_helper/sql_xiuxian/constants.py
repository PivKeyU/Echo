"""修仙插件 ORM 模型与数据库读写封装。

定义表结构、序列化器，以及后台和玩法层会直接调用的增删改查函数。
"""

from __future__ import annotations

import copy
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import event
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    or_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from bot.plugins.xiuxian_game import cache as xiuxian_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby


REALM_ORDER = [
    "炼气",
    "筑基",
    "金丹",
    "元婴",
    "化神",
    "炼虚",
    "合体",
    "大乘",
    "渡劫",
    "人仙",
    "地仙",
    "天仙",
    "金仙",
    "大罗金仙",
    "仙君",
    "仙王",
    "仙尊",
    "仙帝",
]
FIRST_REALM_STAGE = REALM_ORDER[0]
LEGACY_REALM_ORDER = ["凡人", "炼气", "筑基", "结丹", "元婴", "化神", "须弥", "芥子", "混元一体", "炼虚", "合体", "渡劫", "真仙"]
REALM_LAYER_LIMIT = 9
DEFAULT_TECHNIQUE_CAPACITY = 2
MAX_TECHNIQUE_CAPACITY = 2
LEGACY_REALM_ALIASES = {
    "练气": "炼气",
    "浑元一体": "混元一体",
}
LEGACY_TO_NEW_REALM_STAGE = {
    "凡人": "炼气",
    "炼气": "炼气",
    "筑基": "筑基",
    "结丹": "金丹",
    "元婴": "元婴",
    "化神": "化神",
    "须弥": "炼虚",
    "芥子": "合体",
    "混元一体": "大乘",
    "炼虚": "炼虚",
    "合体": "合体",
    "渡劫": "渡劫",
    "真仙": "人仙",
}
REALM_STAGE_RULE_ROWS = [
    ("炼气", 180, 36, 8, 16, 2, 4, 24, 90),
    ("筑基", 420, 72, 10, 20, 2, 5, 34, 84),
    ("金丹", 900, 140, 14, 26, 3, 6, 48, 78),
    ("元婴", 1800, 260, 18, 34, 4, 8, 68, 72),
    ("化神", 3400, 420, 24, 44, 5, 10, 96, 66),
    ("炼虚", 6200, 680, 30, 56, 6, 12, 136, 60),
    ("合体", 10800, 1080, 38, 70, 8, 14, 190, 54),
    ("大乘", 18000, 1680, 48, 86, 10, 16, 260, 48),
    ("渡劫", 29400, 2580, 60, 104, 12, 18, 350, 42),
    ("人仙", 46800, 3900, 76, 126, 14, 22, 470, 36),
    ("地仙", 73200, 5820, 94, 152, 16, 26, 620, 32),
    ("天仙", 112000, 8520, 116, 182, 18, 30, 810, 28),
    ("金仙", 168000, 12300, 140, 216, 20, 34, 1040, 24),
    ("大罗金仙", 248000, 17400, 168, 256, 22, 38, 1320, 20),
    ("仙君", 360000, 24600, 198, 302, 24, 42, 1660, 16),
    ("仙王", 516000, 34200, 230, 354, 26, 48, 2060, 12),
    ("仙尊", 730000, 47000, 264, 414, 28, 54, 2520, 8),
    ("仙帝", 1024000, 64000, 300, 480, 32, 60, 3060, 0),
]
REALM_STAGE_RULES = {
    stage: {
        "threshold_base": threshold_base,
        "threshold_step": threshold_step,
        "practice_gain_min": practice_gain_min,
        "practice_gain_max": practice_gain_max,
        "practice_stone_min": practice_stone_min,
        "practice_stone_max": practice_stone_max,
        "retreat_hourly_base": retreat_hourly_base,
        "breakthrough_base_rate": breakthrough_base_rate,
    }
    for (
        stage,
        threshold_base,
        threshold_step,
        practice_gain_min,
        practice_gain_max,
        practice_stone_min,
        practice_stone_max,
        retreat_hourly_base,
        breakthrough_base_rate,
    ) in REALM_STAGE_RULE_ROWS
}
REALM_LAYER_THRESHOLD_GROWTH_RATE = 0.05
FIVE_ELEMENTS = ["金", "木", "水", "火", "土"]
ELEMENT_GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
ELEMENT_CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
ITEM_KIND_LABELS = {
    "artifact": "法宝",
    "pill": "丹药",
    "talisman": "符箓",
    "material": "材料",
    "technique": "功法",
    "recipe": "配方",
}
STARTER_ARTIFACT_NAME = "凡铁剑"
STARTER_ARTIFACT_GRANTED_ACTION = "starter_artifact_grant"
STARTER_ARTIFACT_RELEASED_ACTION = "starter_artifact_release"
DUEL_MODE_LABELS = {
    "standard": "普通斗法",
    "master": "炉鼎对决",
    "death": "生死斗",
}
ARTIFACT_TYPE_LABELS = {
    "battle": "战斗法宝",
    "support": "辅助法宝",
}
ARTIFACT_ROLE_LABELS = {
    "battle": "攻伐",
    "support": "辅修",
    "guardian": "护身",
    "movement": "身法",
}
ARTIFACT_SLOT_LABELS = {
    "weapon": "武器",
    "helmet": "头冠",
    "clothes": "衣服",
    "boots": "鞋",
    "shield": "盾",
    "accessory": "饰品",
    # Legacy slot keys kept readable for older rows and imports.
    "chest": "衣服",
    "legs": "衣服",
    "robe": "衣服",
    "armor": "衣服",
    "necklace": "饰品",
    "ring": "饰品",
    "bracelet": "饰品",
}
ARTIFACT_EQUIP_SLOTS = ("weapon", "helmet", "clothes", "boots", "shield", "accessory")
ARTIFACT_SLOT_ALIASES = {
    "weapon": "weapon",
    "sword": "weapon",
    "blade": "weapon",
    "helmet": "helmet",
    "head": "helmet",
    "crown": "helmet",
    "chest": "clothes",
    "legs": "clothes",
    "robe": "clothes",
    "armor": "clothes",
    "clothes": "clothes",
    "boots": "boots",
    "boot": "boots",
    "shoes": "boots",
    "shoe": "boots",
    "shield": "shield",
    "necklace": "accessory",
    "ring": "accessory",
    "bracelet": "accessory",
    "accessory": "accessory",
    "amulet": "accessory",
}
ARTIFACT_EQUIP_CATEGORY_LABELS = {
    "weapon": "武器",
    "armor": "防具",
    "shield": "盾",
    "accessory": "饰品",
    "other": "其他装备",
}
ARTIFACT_SLOT_CATEGORY_MAP = {
    "weapon": "weapon",
    "chest": "armor",
    "legs": "armor",
    "boots": "armor",
    "helmet": "armor",
    "clothes": "armor",
    "robe": "armor",
    "armor": "armor",
    "shield": "shield",
    "bracelet": "accessory",
    "necklace": "accessory",
    "ring": "accessory",
    "accessory": "accessory",
}


def normalize_artifact_slot(slot: str | None) -> str:
    raw = str(slot or "").strip().lower()
    if not raw:
        return "weapon"
    return ARTIFACT_SLOT_ALIASES.get(raw, raw if raw in ARTIFACT_EQUIP_SLOTS else "accessory")


def artifact_slot_label(slot: str | None) -> str:
    normalized = normalize_artifact_slot(slot)
    return ARTIFACT_SLOT_LABELS.get(normalized, str(slot or "").strip() or "饰品")
SECT_CAMP_LABELS = {
    "orthodox": "正道",
    "heterodox": "邪道",
}
PILL_TYPE_LABELS = {
    "foundation": "突破加成",
    "clear_poison": "解毒",
    "cultivation": "提升修为",
    "bone": "提升根骨",
    "comprehension": "提升悟性",
    "divine_sense": "提升神识",
    "fortune": "提升机缘",
    "willpower": "提升心志",
    "charisma": "提升魅力",
    "karma": "提升因果",
    "qi_blood": "提升气血",
    "true_yuan": "提升真元",
    "body_movement": "提升身法",
    "attack": "提升攻击",
    "defense": "提升防御",
    "root_refine": "淬炼灵根",
    "root_remold": "重塑灵根",
    "root_single": "洗成单灵根",
    "root_double": "洗成双灵根",
    "root_earth": "洗成地灵根",
    "root_heaven": "洗成天灵根",
    "root_variant": "洗成变异灵根",
}
SECT_ROLE_PRESETS = [
    ("leader", "掌门", 1),
    ("elder", "长老", 2),
    ("core", "真传弟子", 3),
    ("inner_deacon", "内门执事", 4),
    ("outer_deacon", "外门执事", 5),
    ("inner_disciple", "内门弟子", 6),
    ("outer_disciple", "外门弟子", 7),
]
SECT_ROLE_LABELS = {key: label for key, label, _ in SECT_ROLE_PRESETS}
TASK_SCOPE_LABELS = {
    "official": "官方任务",
    "sect": "宗门任务",
    "personal": "个人悬赏",
}
TASK_TYPE_LABELS = {
    "quiz": "答题任务",
    "custom": "自定义任务",
    "metric": "计数任务",
}
TECHNIQUE_TYPE_LABELS = {
    "balanced": "均衡功法",
    "cultivation": "吐纳功法",
    "combat": "斗战功法",
    "attack": "攻伐功法",
    "movement": "身法秘术",
    "defense": "护体功法",
    "divine": "神识秘法",
    "support": "辅修功法",
}
RECIPE_KIND_LABELS = {
    "artifact": "炼制法宝",
    "pill": "炼制丹药",
    "talisman": "炼制符箓",
}
ENVELOPE_MODE_LABELS = {
    "normal": "普通红包",
    "lucky": "拼手气红包",
    "exclusive": "专属红包",
}
DEFAULT_ROOT_QUALITY_VALUE_RULES = {
    "废灵根": {"cultivation_rate": 0.72, "breakthrough_bonus": -8, "combat_factor": 0.97},
    "下品灵根": {"cultivation_rate": 0.88, "breakthrough_bonus": -3, "combat_factor": 0.985},
    "中品灵根": {"cultivation_rate": 1.0, "breakthrough_bonus": 0, "combat_factor": 1.0},
    "上品灵根": {"cultivation_rate": 1.12, "breakthrough_bonus": 3, "combat_factor": 1.015},
    "极品灵根": {"cultivation_rate": 1.24, "breakthrough_bonus": 6, "combat_factor": 1.03},
    "天灵根": {"cultivation_rate": 1.38, "breakthrough_bonus": 12, "combat_factor": 1.045},
    "变异灵根": {"cultivation_rate": 1.3, "breakthrough_bonus": 9, "combat_factor": 1.04},
}
DEFAULT_EXPLORATION_DROP_WEIGHT_RULES = {
    "material_divine_sense_divisor": 7,
    "high_quality_threshold": 4,
    "high_quality_fortune_divisor": 8,
    "high_quality_root_level_start": 4,
}
DEFAULT_ITEM_QUALITY_VALUE_RULES = {
    "凡品": {"artifact_multiplier": 0.70, "pill_multiplier": 0.70, "talisman_multiplier": 0.65, "recipe_multiplier": 0.70},
    "下品": {"artifact_multiplier": 0.90, "pill_multiplier": 0.90, "talisman_multiplier": 0.85, "recipe_multiplier": 0.90},
    "中品": {"artifact_multiplier": 1.20, "pill_multiplier": 1.20, "talisman_multiplier": 1.15, "recipe_multiplier": 1.20},
    "上品": {"artifact_multiplier": 1.60, "pill_multiplier": 1.60, "talisman_multiplier": 1.55, "recipe_multiplier": 1.60},
    "极品": {"artifact_multiplier": 2.20, "pill_multiplier": 2.20, "talisman_multiplier": 2.10, "recipe_multiplier": 2.20},
    "仙品": {"artifact_multiplier": 3.10, "pill_multiplier": 3.10, "talisman_multiplier": 2.95, "recipe_multiplier": 3.10},
    "先天至宝": {"artifact_multiplier": 4.50, "pill_multiplier": 4.50, "talisman_multiplier": 4.25, "recipe_multiplier": 4.50},
}
DEFAULT_ACTIVITY_STAT_GROWTH_RULES = {
    "practice": {"chance_percent": 16, "gain_min": 1, "gain_max": 2, "attribute_count": 1},
    "commission": {"chance_percent": 18, "gain_min": 1, "gain_max": 2, "attribute_count": 1},
    "exploration": {"chance_percent": 26, "gain_min": 1, "gain_max": 3, "attribute_count": 1},
    "duel": {"chance_percent": 20, "gain_min": 1, "gain_max": 2, "attribute_count": 2},
}
DEFAULT_GAMBLING_QUALITY_WEIGHT_RULES = {
    "凡品": {"weight_multiplier": 1.0},
    "下品": {"weight_multiplier": 0.55},
    "中品": {"weight_multiplier": 0.28},
    "上品": {"weight_multiplier": 0.12},
    "极品": {"weight_multiplier": 0.045},
    "仙品": {"weight_multiplier": 0.014},
    "先天至宝": {"weight_multiplier": 0.004},
}
DEFAULT_FISHING_QUALITY_WEIGHT_RULES = {
    "凡品": {"weight_multiplier": 1.0},
    "下品": {"weight_multiplier": 0.42},
    "中品": {"weight_multiplier": 0.18},
    "上品": {"weight_multiplier": 0.065},
    "极品": {"weight_multiplier": 0.020},
    "仙品": {"weight_multiplier": 0.0055},
    "先天至宝": {"weight_multiplier": 0.0012},
}


def calculate_arena_cultivation_cap(stage: str | None) -> int:
    normalized = str(stage or "").strip()
    if normalized not in REALM_STAGE_RULES:
        normalized = FIRST_REALM_STAGE
    threshold_base = int((REALM_STAGE_RULES.get(normalized) or REALM_STAGE_RULES[FIRST_REALM_STAGE])["threshold_base"])
    return max(int(round(threshold_base * 0.05)), 15)


def _default_arena_stage_rule(stage: str, index: int) -> dict[str, Any]:
    duration_minutes = 60 if index < 2 else 90 if index < 5 else 120 if index < 9 else 180
    return {
        "realm_stage": stage,
        "duration_minutes": duration_minutes,
        "reward_cultivation": calculate_arena_cultivation_cap(stage),
    }


DEFAULT_ARENA_STAGE_RULES = [_default_arena_stage_rule(stage, index) for index, stage in enumerate(REALM_ORDER)]


def _shared_reward_pool_entry(
    item_kind: str,
    item_name: str,
    quantity_min: int,
    quantity_max: int,
    base_weight: float,
    *,
    enabled: bool = True,
    fishing_weight: float | None = None,
    gambling_weight: float | None = None,
    fishing_enabled: bool | None = None,
    gambling_enabled: bool | None = None,
) -> dict[str, Any]:
    resolved_gambling_weight = float(base_weight if gambling_weight is None else gambling_weight)
    resolved_fishing_weight = float(base_weight if fishing_weight is None else fishing_weight)
    resolved_enabled = bool(enabled)
    return {
        "item_kind": item_kind,
        "item_name": item_name,
        "quantity_min": quantity_min,
        "quantity_max": quantity_max,
        "base_weight": resolved_gambling_weight,
        "enabled": resolved_enabled,
        "gambling_weight": resolved_gambling_weight,
        "fishing_weight": resolved_fishing_weight,
        "gambling_enabled": resolved_enabled if gambling_enabled is None else bool(gambling_enabled),
        "fishing_enabled": resolved_enabled if fishing_enabled is None else bool(fishing_enabled),
    }


DEFAULT_GAMBLING_REWARD_POOL = [
    _shared_reward_pool_entry("material", "灵露滴", 2, 5, 120),
    _shared_reward_pool_entry("artifact", "凡铁剑", 1, 1, 90),
    _shared_reward_pool_entry("material", "霜凌草", 1, 3, 84),
    _shared_reward_pool_entry("pill", "聚气丹", 1, 2, 72),
    _shared_reward_pool_entry("pill", "轻灵丹", 1, 2, 68),
    _shared_reward_pool_entry("talisman", "御风符", 1, 1, 36),
    _shared_reward_pool_entry("talisman", "护心符", 1, 1, 30),
    _shared_reward_pool_entry("material", "冰魄珠", 1, 2, 54),
    _shared_reward_pool_entry("material", "星河砂", 1, 2, 42),
    _shared_reward_pool_entry("artifact", "青罡剑", 1, 1, 38),
    _shared_reward_pool_entry("artifact", "逐云履", 1, 1, 34),
    _shared_reward_pool_entry("pill", "回春丹", 1, 2, 36),
    _shared_reward_pool_entry("pill", "聚宝含光丹", 1, 2, 28),
    _shared_reward_pool_entry("artifact", "玄龟盾", 1, 1, 26),
    _shared_reward_pool_entry("pill", "龙髓丹", 1, 1, 24),
    _shared_reward_pool_entry("material", "地脉玉髓", 1, 1, 20),
    _shared_reward_pool_entry("material", "玄冰精髓", 1, 1, 18),
    _shared_reward_pool_entry("talisman", "镇岳符", 1, 1, 8),
    _shared_reward_pool_entry("artifact", "定海镇心佩", 1, 1, 8),
    _shared_reward_pool_entry("material", "九幽寒莲", 1, 1, 8),
    _shared_reward_pool_entry("talisman", "化毒符", 1, 1, 4),
    _shared_reward_pool_entry("artifact", "流霞问心簪", 1, 1, 6),
    _shared_reward_pool_entry("talisman", "摄魂符", 1, 1, 3.5),
    _shared_reward_pool_entry("pill", "太和解厄丹", 1, 1, 5),
    _shared_reward_pool_entry("material", "天道精华", 1, 1, 4),
    _shared_reward_pool_entry("material", "鸿蒙紫莲", 1, 1, 3),
    _shared_reward_pool_entry("material", "命运之种", 1, 1, 2),
    _shared_reward_pool_entry("talisman", "裂空符", 1, 1, 1.2),
    _shared_reward_pool_entry("material", "本源雷种", 1, 1, 1.5),
    _shared_reward_pool_entry("material", "开天神石", 1, 1, 1),
]

DEFAULT_SETTINGS = {
    "coin_stone_exchange_enabled": True,
    "coin_exchange_rate": 100,
    "exchange_fee_percent": 1,
    "min_coin_exchange": 1,
    "message_auto_delete_seconds": 180,
    "equipment_unbind_cost": 100,
    "artifact_plunder_chance": 20,
    "shop_broadcast_cost": 20,
    "shop_notice_group_id": 0,
    "official_shop_name": "官方商店",
    "auction_fee_percent": 5,
    "auction_duration_minutes": 60,
    "auction_notice_group_id": 0,
    "allow_user_task_publish": True,
    "task_publish_cost": 20,
    "user_task_daily_limit": 3,
    "artifact_equip_limit": 6,
    "duel_bet_enabled": True,
    "duel_bet_seconds": 120,
    "duel_bet_min_amount": 10,
    "duel_bet_max_amount": 100,
    "duel_bet_amount_options": [10, 50, 100],
    "duel_winner_steal_percent": 25,
    "duel_invite_timeout_seconds": 90,
    "arena_open_fee_stone": 0,
    "arena_challenge_fee_stone": 0,
    "arena_notice_group_id": 0,
    "arena_stage_rules": DEFAULT_ARENA_STAGE_RULES,
    "event_summary_interval_minutes": 10,
    "allow_non_admin_image_upload": False,
    "chat_cultivation_chance": 6,
    "chat_cultivation_min_gain": 1,
    "chat_cultivation_max_gain": 2,
    "robbery_daily_limit": 3,
    "robbery_max_steal": 180,
    "exploration_daily_limit": 10,
    "fishing_daily_limit": 30,
    "encounter_claim_daily_limit": 5,
    "high_quality_broadcast_level": 6,
    "gambling_exchange_cost_stone": 120,
    "gambling_exchange_max_count": 20,
    "gambling_open_max_count": 100,
    "gambling_broadcast_quality_level": 6,
    "gambling_fortune_divisor": 6,
    "gambling_fortune_bonus_per_quality_percent": 8,
    "gambling_quality_weight_rules": DEFAULT_GAMBLING_QUALITY_WEIGHT_RULES,
    "fishing_quality_weight_rules": DEFAULT_FISHING_QUALITY_WEIGHT_RULES,
    "gambling_reward_pool": DEFAULT_GAMBLING_REWARD_POOL,
    "root_quality_value_rules": DEFAULT_ROOT_QUALITY_VALUE_RULES,
    "exploration_drop_weight_rules": DEFAULT_EXPLORATION_DROP_WEIGHT_RULES,
    "item_quality_value_rules": DEFAULT_ITEM_QUALITY_VALUE_RULES,
    "activity_stat_growth_rules": DEFAULT_ACTIVITY_STAT_GROWTH_RULES,
    "immortal_touch_infusion_layers": 1,
    "encounter_auto_dispatch_enabled": True,
    "encounter_auto_dispatch_hour": 12,
    "encounter_auto_dispatch_minute": 0,
    "encounter_auto_dispatch_last_dates": {},
    "encounter_spawn_chance": 5,
    "encounter_group_cooldown_minutes": 12,
    "encounter_active_seconds": 90,
    "slave_tribute_percent": 20,
    "slave_challenge_cooldown_hours": 24,
    "rebirth_cooldown_enabled": False,
    "rebirth_cooldown_base_hours": 12,
    "rebirth_cooldown_increment_hours": 6,
    "furnace_harvest_cultivation_percent": 10,
    "sect_salary_min_stay_days": 30,
    "sect_betrayal_cooldown_days": 7,
    "marriage_divorce_cooldown_days": 7,
    "sect_betrayal_stone_percent": 10,
    "sect_betrayal_stone_min": 20,
    "sect_betrayal_stone_max": 300,
    "error_log_retention_count": 500,
    "seclusion_cultivation_efficiency_percent": 60,
}
DEFAULT_SETTINGS["duel_bet_minutes"] = 2

SHANGHAI_TZ = timezone(timedelta(hours=8))
UTC_TZ = timezone.utc

QUALITY_LEVEL_LABELS = {
    1: "凡品",
    2: "下品",
    3: "中品",
    4: "上品",
    5: "极品",
    6: "仙品",
    7: "先天至宝",
}
QUALITY_LABEL_LEVELS = {label: level for level, label in QUALITY_LEVEL_LABELS.items()}
QUALITY_LEVEL_COLORS = {
    1: "#9ca3af",
    2: "#22c55e",
    3: "#3b82f6",
    4: "#8b5cf6",
    5: "#f59e0b",
    6: "#ef4444",
    7: "linear-gradient(135deg, #fb7185 0%, #f59e0b 18%, #fde047 36%, #34d399 54%, #60a5fa 72%, #a78bfa 88%, #f472b6 100%)",
}
QUALITY_LEVEL_DESCRIPTIONS = {
    1: "凡铁凡草，灵韵初生。多为刚入道途者随手可得的寻常之物，胜在稳妥。",
    2: "略有打磨，已蕴一丝灵气。散修行走江湖时最常依仗的品阶，不求惊艳但求踏实。",
    3: "锻火初成，器纹浮现。此阶宝物已能隐约引动天地灵气，入手便觉与凡物截然不同。",
    4: "地脉滋养，百炼成器。或藏前辈心血，或吸一方灵气，已能隐约改变斗法走势。",
    5: "天工开物，宝光自生。材取天地至纯，火候十年方成，持之如携一小天地在身。",
    6: "见之如见传说。古籍里零星留下名字，能得一件便是气运加身，坊间数年未必现世一次。",
    7: "先天之宝，道痕自生。混沌初开时便已存在，或从劫灭中幸存，天下仅此一件。",
}
QUALITY_LEVEL_FEATURES = {
    1: "灵纹未显，胜在质朴稳妥",
    2: "仅凝一道灵纹，妙用虽浅却实在可靠",
    3: "灵纹渐明，偶有微末异象相随",
    4: "灵纹交织，已能引动小范围灵潮变动",
    5: "灵纹自成小周天，特效不卑不亢",
    6: "宝纹通玄，御敌之时如臂使指，斗法节奏为之一变",
    7: "混沌道纹，天地间仅此一缕，可逆转乾坤",
}

SOCIAL_MODE_LABELS = {
    "worldly": "入世",
    "secluded": "避世",
}
GENDER_LABELS = {
    "male": "男",
    "female": "女",
}
MENTORSHIP_REQUEST_ROLE_LABELS = {
    "mentor": "收徒邀请",
    "disciple": "拜师申请",
}
MENTORSHIP_STATUS_LABELS = {
    "active": "师徒在籍",
    "graduated": "已出师",
    "dissolved": "已解除",
}
MENTORSHIP_REQUEST_STATUS_LABELS = {
    "pending": "待处理",
    "accepted": "已接受",
    "rejected": "已婉拒",
    "cancelled": "已撤回",
    "expired": "已过期",
}
MARRIAGE_STATUS_LABELS = {
    "active": "已结为道侣",
    "divorced": "已和离",
}
MARRIAGE_REQUEST_STATUS_LABELS = {
    "pending": "待处理",
    "accepted": "已接受",
    "rejected": "已婉拒",
    "cancelled": "已撤回",
    "expired": "已过期",
}
MATERIAL_QUALITY_NOTES = {
    1: "常见基础灵材，适合入门炼制、任务收集与日常积累。",
    2: "灵性稳定的常备材料，足以支撑前中期常规配方。",
    3: "已具明显灵韵，可作为中阶丹器符配方的主辅材料。",
    4: "材质精纯、灵息凝实，常用于高阶炼制与精修。",
    5: "珍稀核心灵材，往往决定成品的上限与方向。",
    6: "传说层次的异材，多见于险地奇遇、榜单奖励或古修遗藏。",
    7: "天材地宝级重宝，足以左右顶级炼制与机缘布局。",
}
REMOVED_PILL_TYPES = {"stone"}
PILL_EFFECT_VALUE_LABELS = {
    "foundation": "突破增幅",
    "clear_poison": "解毒值",
    "cultivation": "修为增量",
    "bone": "根骨增量",
    "comprehension": "悟性增量",
    "divine_sense": "神识增量",
    "fortune": "机缘增量",
    "willpower": "心志增量",
    "charisma": "魅力增量",
    "karma": "因果增量",
    "qi_blood": "气血增量",
    "true_yuan": "真元增量",
    "body_movement": "身法增量",
    "attack": "攻击增量",
    "defense": "防御增量",
    "root_refine": "淬灵阶数",
    "root_remold": "保底品阶",
    "root_single": "保底品阶",
    "root_double": "保底品阶",
    "root_earth": "效果值未用",
    "root_heaven": "效果值未用",
    "root_variant": "效果值未用",
}
