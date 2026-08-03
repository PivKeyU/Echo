"""修仙核心数值与成长服务。

这里保留历史兼容出口。
后续新增或维护优先落到 `features/` 下的对应领域文件，再由这里兼容导出。
"""

from __future__ import annotations

import random
import re
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from math import ceil, exp
from typing import Any

from pykeyboard import InlineButton, InlineKeyboard
from pyromod.helpers import ikb
from sqlalchemy import text

from bot import api as api_config
from bot.sql_helper import DB_BACKEND, Session, engine
from bot.func_helper.emby_currency import (
    convert_coin_to_stone,
    convert_stone_to_coin,
    get_emby_balance,
    get_exchange_settings,
)
from bot.sql_helper.sql_xiuxian import (
    ATTRIBUTE_LABELS,
    ATTRIBUTE_EFFECT_HINTS,
    DEFAULT_SETTINGS,
    DUEL_MODE_LABELS,
    ELEMENT_CONTROLS,
    ELEMENT_GENERATES,
    FIVE_ELEMENTS,
    ITEM_KIND_LABELS,
    PILL_TYPE_LABELS,
    REALM_ORDER,
    REALM_STAGE_RULES,
    ROOT_QUALITY_COLORS,
    ROOT_QUALITY_LEVELS,
    ROOT_VARIANT_ELEMENTS,
    SOCIAL_MODE_LABELS,
    STARTER_ARTIFACT_NAME,
    _grant_artifact_inventory_in_session,
    apply_spiritual_stone_delta,
    admin_patch_profile,
    assert_currency_operation_allowed,
    assert_profile_alive,
    bind_user_artifact,
    bind_user_talisman,
    calculate_arena_cultivation_cap,
    calculate_realm_threshold,
    clear_all_xiuxian_user_data,
    cancel_auction_item,
    cancel_personal_shop_item as sql_cancel_personal_shop_item,
    create_journal,
    create_auction_item,
    create_boss_config,
    create_artifact,
    create_duel_record,
    create_pill,
    create_shop_item,
    create_technique,
    create_talisman,
    get_artifact,
    get_current_title,
    get_emby_name_map,
    get_material,
    get_pill,
    get_profile,
    get_recipe,
    get_technique,
    get_talisman,
    get_xiuxian_settings,
    invalidate_xiuxian_user_view_cache,
    grant_duplicate_knowledge_compensation_in_session,
    grant_artifact_to_user,
    grant_starter_artifact_once,
    grant_material_to_user,
    grant_pill_to_user,
    grant_recipe_to_user,
    grant_talisman_to_user,
    grant_technique_to_user,
    grant_title_to_user,
    list_artifacts,
    list_artifact_sets,
    list_auction_items,
    list_boss_configs,
    list_slave_profiles,
    list_equipped_artifacts,
    list_materials,
    list_pills,
    list_profiles,
    list_recipe_ingredients,
    list_recipes,
    list_shop_items,
    list_techniques,
    list_talismans,
    list_titles,
    list_user_titles,
    list_user_artifacts,
    list_user_materials,
    list_user_pills,
    list_user_recipes,
    list_user_techniques,
    list_user_talismans,
    migrate_legacy_realm_state,
    normalize_mentorship_request_role,
    normalize_mentorship_request_status,
    normalize_mentorship_status,
    normalize_gender,
    normalize_marriage_request_status,
    normalize_marriage_status,
    normalize_artifact_slot,
    normalize_realm_stage,
    normalize_social_mode,
    finalize_auction_item as sql_finalize_auction_item,
    place_auction_bid as sql_place_auction_bid,
    patch_boss_config,
    purchase_shop_item as sql_purchase_shop_item,
    plunder_random_artifact_to_user,
    realm_index,
    resolve_duel_bet_settings,
    search_profiles,
    serialize_artifact,
    serialize_datetime,
    serialize_material,
    serialize_marriage,
    serialize_marriage_request,
    serialize_mentorship,
    serialize_mentorship_request,
    serialize_arena,
    serialize_pill,
    serialize_profile,
    serialize_recipe,
    serialize_technique,
    serialize_talisman,
    purge_removed_pill_types,
    starter_artifact_protection_active,
    get_quality_meta,
    get_active_duel_lock,
    set_current_technique,
    set_current_title,
    set_active_talisman,
    set_equipped_artifact,
    set_xiuxian_settings,
    sync_achievement_by_key,
    sync_official_shop_name,
    sync_artifact_by_name,
    sync_artifact_set_by_name,
    sync_encounter_template_by_name,
    sync_material_by_name,
    sync_pill_by_name,
    sync_talisman_by_name,
    sync_technique_by_name,
    sync_title_by_name,
    admin_set_user_artifact_inventory,
    admin_set_user_material_inventory,
    admin_set_user_pill_inventory,
    admin_set_user_talisman_inventory,
    revoke_recipe_from_user,
    revoke_technique_from_user,
    revoke_title_from_user,
    unbind_user_artifact,
    unbind_user_talisman,
    update_shop_item,
    update_auction_item,
    upsert_profile,
    XiuxianArtifact,
    XiuxianProfile,
    XiuxianArtifactInventory,
    XiuxianEquippedArtifact,
    XiuxianExploration,
    XiuxianJournal,
    XiuxianMarriage,
    XiuxianMarriageRequest,
    XiuxianMaterialInventory,
    XiuxianMentorship,
    XiuxianMentorshipRequest,
    XiuxianArena,
    XiuxianPillInventory,
    XiuxianTalismanInventory,
    XiuxianTaskClaim,
    XiuxianSetting,
    XiuxianUserRecipe,
    XiuxianUserTechnique,
    _queue_catalog_cache_invalidation,
    _queue_profile_cache_invalidation,
    _queue_user_view_cache_invalidation,
    use_user_artifact_listing_stock,
    use_user_material_listing_stock,
    use_user_pill_listing_stock,
    use_user_talisman_listing_stock,
    consume_user_pill,
    consume_user_talisman,
    get_shared_spiritual_stone_total,
    utcnow,
    _ordered_owner_rows,
)
from bot.plugins.xiuxian_game.achievement_service import (
    build_user_achievement_overview,
    record_achievement_progress,
    record_arena_metrics,
    record_duel_metrics,
)
from bot.plugins.xiuxian_game.probability import (
    FORTUNE_BASELINE,
    adjust_probability_rate,
    roll_probability_percent,
)
from bot.plugins.xiuxian_game.world_service import (
    _get_item_payload,
    get_item_source_catalog,
    get_sect_effects,
    sync_recipe_with_ingredients_by_name,
    sync_scene_with_drops_by_name,
    sync_sect_with_roles_by_name,
)
from bot.plugins.xiuxian_game.features.content_catalog import (
    ALL_EXTRA_MATERIALS,
    DEFAULT_ENCOUNTER_TEMPLATES,
    EXTRA_ARTIFACTS,
    EXTRA_PILLS,
    EXTRA_RECIPES,
    EXTRA_SCENES,
    EXTRA_TALISMANS,
    apply_farmable_material_overrides,
)


ROOT_SPECIAL_BONUS = {
    "天灵根": 15,
    "地灵根": 10,
}
ROOT_COMMON_QUALITY_ORDER = ["废灵根", "下品灵根", "中品灵根", "上品灵根", "极品灵根"]
ROOT_SPECIAL_QUALITIES = {"天灵根", "变异灵根"}
ROOT_TRANSFORM_PILL_TYPES = {"root_single", "root_double", "root_earth", "root_heaven", "root_variant"}
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
FORTUNE_PILL_CAP_BASE = 60
FORTUNE_PILL_CAP_STEP = 20
FORTUNE_PILL_CAP_MAX = 240


def _profile_field(profile: XiuxianProfile | dict[str, Any] | None, field: str, default: Any = None) -> Any:
    if profile is None:
        return default
    if isinstance(profile, dict):
        return profile.get(field, default)
    return getattr(profile, field, default)


def _fortune_pill_cap_for_profile(profile: XiuxianProfile | dict[str, Any] | None) -> int:
    stage = normalize_realm_stage(_profile_field(profile, "realm_stage", FIRST_REALM_STAGE) or FIRST_REALM_STAGE)
    stage_index = max(realm_index(stage), 0)
    return min(FORTUNE_PILL_CAP_BASE + stage_index * FORTUNE_PILL_CAP_STEP, FORTUNE_PILL_CAP_MAX)


def _fortune_pill_current_value(profile: XiuxianProfile | dict[str, Any] | None) -> int:
    try:
        return max(int(_profile_field(profile, "fortune", 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


def _fortune_pill_gain_per_use(profile_data: dict[str, Any], pill: dict[str, Any] | None) -> int:
    if str((pill or {}).get("pill_type") or "").strip() != "fortune":
        return 0
    effects = resolve_pill_effects(profile_data, pill)
    return max(int(round(float(effects.get("fortune_bonus", 0) or 0))), 0)


def _fortune_pill_remaining_uses(
    profile_data: dict[str, Any],
    pill: dict[str, Any] | None,
    owned_quantity: int | None = None,
) -> int:
    if str((pill or {}).get("pill_type") or "").strip() != "fortune":
        return 0
    cap = _fortune_pill_cap_for_profile(profile_data)
    current = _fortune_pill_current_value(profile_data)
    if current >= cap:
        return 0
    gain = _fortune_pill_gain_per_use(profile_data, pill)
    if gain <= 0:
        return 0
    remaining = int(ceil((cap - current) / gain))
    if owned_quantity is not None:
        remaining = min(remaining, max(int(owned_quantity or 0), 0))
    return max(remaining, 0)


def _fortune_pill_usage_reason(profile_data: dict[str, Any], pill: dict[str, Any] | None) -> str:
    if str((pill or {}).get("pill_type") or "").strip() != "fortune":
        return ""
    cap = _fortune_pill_cap_for_profile(profile_data)
    current = _fortune_pill_current_value(profile_data)
    if current >= cap:
        return f"机缘已达当前境界丹药可提升上限（{current}/{cap}），继续服用不会生效。"
    if _fortune_pill_gain_per_use(profile_data, pill) <= 0:
        return "这枚机缘丹没有可生效的机缘。"
    return ""


def _pill_batch_use_max(profile_data: dict[str, Any], pill: dict[str, Any] | None, quantity: int | None) -> int:
    if not _pill_supports_batch_use(pill):
        return 1
    try:
        owned_quantity = max(int(quantity or 0), 0)
    except (TypeError, ValueError):
        owned_quantity = 0
    if str((pill or {}).get("pill_type") or "").strip() == "fortune":
        return _fortune_pill_remaining_uses(profile_data, pill, owned_quantity)
    return owned_quantity


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

PERSONAL_SHOP_NAME = "游仙小铺"
OFFICIAL_RECYCLE_NAME = "万宝归炉"
IMMORTAL_STONE_NAME = "仙界奇石"
GAMBLING_SUPPORTED_ITEM_KINDS = {"artifact", "pill", "talisman", "material", "recipe", "technique"}
RECYCLABLE_ITEM_KINDS = {"artifact", "pill", "talisman", "material", "technique", "recipe"}
STARTER_TECHNIQUE_NAME = "长青诀"
STARTER_TITLE_NAME = "初入仙途"
STARTER_FOUNDATION_PILL_NAME = "筑基丹"

DEFAULT_ARTIFACTS = [
    {
        "name": "凡铁剑",
        "rarity": "凡品",
        "artifact_type": "battle",
        "artifact_role": "battle",
        "equip_slot": "weapon",
        "description": "最基础的入门法宝，适合刚踏入仙途的道友防身。",
        "attack_bonus": 12,
        "defense_bonus": 6,
        "duel_rate_bonus": 2,
        "cultivation_bonus": 0,
        "combat_config": {
            "passives": [
                {
                    "name": "铁锋一击",
                    "kind": "extra_damage",
                    "chance": 18,
                    "flat_damage": 8,
                    "text": "凡铁剑劈出一线寒芒，逼得对手仓促后撤。",
                }
            ]
        },
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "青罡剑",
        "rarity": "下品",
        "artifact_type": "battle",
        "artifact_role": "battle",
        "equip_slot": "weapon",
        "description": "以寒铁与赤炎晶砂淬成，剑势凌厉，最适合初入筑基的剑修。",
        "attack_bonus": 18,
        "defense_bonus": 5,
        "body_movement_bonus": 4,
        "duel_rate_bonus": 4,
        "combat_config": {
            "opening_text": "青罡剑鸣，剑气先至。",
            "passives": [
                {
                    "name": "剑罡斩",
                    "kind": "extra_damage",
                    "chance": 26,
                    "flat_damage": 14,
                    "ratio_percent": 20,
                    "text": "青罡剑卷起一道剑罡，直取对手要害。",
                }
            ],
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "玄龟盾",
        "rarity": "下品",
        "artifact_type": "support",
        "artifact_role": "guardian",
        "equip_slot": "shield",
        "description": "以玄龟甲片和地脉岩芯炼成，擅长化劲护体。",
        "attack_bonus": 4,
        "defense_bonus": 18,
        "qi_blood_bonus": 40,
        "duel_rate_bonus": 3,
        "combat_config": {
            "passives": [
                {
                    "name": "玄甲护身",
                    "kind": "shield",
                    "chance": 28,
                    "flat_shield": 22,
                    "ratio_percent": 24,
                    "duration": 1,
                    "text": "玄龟盾沉沉一震，垒起一层灵甲护住周身。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 7,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "逐云履",
        "rarity": "中品",
        "artifact_type": "support",
        "artifact_role": "movement",
        "equip_slot": "boots",
        "description": "以云纹丝炼成的轻灵法履，步踏如风，专克笨重攻势。",
        "attack_bonus": 8,
        "defense_bonus": 8,
        "body_movement_bonus": 16,
        "duel_rate_bonus": 6,
        "combat_config": {
            "passives": [
                {
                    "name": "踏云错影",
                    "kind": "dodge",
                    "chance": 24,
                    "dodge_bonus": 16,
                    "duration": 1,
                    "text": "逐云履轻轻一点，身形已借雾气挪开半尺。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "赤焰珠",
        "rarity": "中品",
        "artifact_type": "battle",
        "artifact_role": "support",
        "equip_slot": "accessory",
        "description": "珠内封着一缕离火，攻势不算厚重，但善于不断灼烧对手。",
        "attack_bonus": 16,
        "true_yuan_bonus": 50,
        "duel_rate_bonus": 5,
        "combat_config": {
            "passives": [
                {
                    "name": "离火灼心",
                    "kind": "burn",
                    "chance": 22,
                    "flat_damage": 10,
                    "duration": 2,
                    "text": "赤焰珠吐出离火细线，附在护体灵气上缓缓灼烧。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 3,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "残修青罡古剑",
        "rarity": "上品",
        "artifact_type": "battle",
        "artifact_role": "battle",
        "equip_slot": "weapon",
        "description": "自秘境残剑中修复而来，剑身尚有裂纹，却也藏着不俗杀意。",
        "attack_bonus": 28,
        "defense_bonus": 10,
        "body_movement_bonus": 6,
        "duel_rate_bonus": 8,
        "combat_config": {
            "opening_text": "古剑微震，似有旧日战魂苏醒。",
            "skills": [
                {
                    "name": "裂空古剑式",
                    "kind": "extra_damage",
                    "chance": 32,
                    "flat_damage": 22,
                    "ratio_percent": 28,
                    "cost_true_yuan": 20,
                    "text": "残修青罡古剑带着破空之声悍然斩下。",
                }
            ],
            "passives": [
                {
                    "name": "残锋噬血",
                    "kind": "bleed",
                    "chance": 18,
                    "flat_damage": 12,
                    "duration": 2,
                    "text": "旧伤被古剑撕开，鲜血顺着灵力痕迹一并溃散。",
                }
            ],
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 6,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "残修玄龟古盾",
        "rarity": "上品",
        "artifact_type": "support",
        "artifact_role": "guardian",
        "equip_slot": "shield",
        "description": "由古盾残片重新归铸，盾势厚重，最适合久战磨敌。",
        "attack_bonus": 6,
        "defense_bonus": 28,
        "qi_blood_bonus": 80,
        "duel_rate_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "镇岳灵壁",
                    "kind": "guard",
                    "chance": 34,
                    "defense_ratio_percent": 30,
                    "flat_shield": 28,
                    "cost_true_yuan": 16,
                    "duration": 1,
                    "text": "古盾轰然立起，如一座小山压住来势汹汹的劲力。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 6,
        "image_url": "",
        "enabled": True,
    },
]

DEFAULT_PILLS = [
    {
        "name": "筑基丹",
        "pill_type": "foundation",
        "description": "丹成之时金光满室，服用后可夯实道基，大幅提升筑基突破之成功率。传闻唯有以此丹为引，方能叩开长生第一扇门。",
        "effect_value": 50,
        "poison_delta": 12,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "清心丹",
        "rarity": "凡品",
        "pill_type": "clear_poison",
        "description": "以九种清心草药炼制，入口如饮甘露。丹丸入腹化作一缕清凉之气，缓缓涤荡经脉，将沉积已久的丹毒杂质尽数净化。",
        "effect_value": 12,
        "poison_delta": 0,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "洗髓丹",
        "rarity": "下品",
        "pill_type": "bone",
        "description": "丹体晶莹如雪，蕴含淬体之力。服后浑身骨髓如被天地灵泉冲刷洗涤，浊垢尽去，筋骨愈发坚韧如铁，根基亦随之稳固。",
        "effect_value": 4,
        "poison_delta": 6,
        "image_url": "",
        "min_realm_stage": "炼气",
        "min_realm_layer": 3,
        "enabled": True,
    },
    {
        "name": "悟道丹",
        "rarity": "下品",
        "pill_type": "comprehension",
        "description": "丹成时似有道音低鸣，服后灵台一片澄明。原本晦涩的功法经义豁然贯通，悟道之路由此平坦几分，修仙百艺皆可触类旁通。",
        "effect_value": 4,
        "poison_delta": 8,
        "image_url": "",
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "凝神丹",
        "rarity": "下品",
        "pill_type": "divine_sense",
        "description": "丹丸泛着淡淡幽蓝光泽，入口化为一缕清灵之气直冲识海。服后神识如经春雨润泽，渐渐凝聚成形，感知万物之能亦随之大增。",
        "effect_value": 4,
        "poison_delta": 6,
        "image_url": "",
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "enabled": True,
    },
    {
        "name": "天运丹",
        "rarity": "中品",
        "pill_type": "fortune",
        "description": "丹中似有星辰流转，蕴含天道福祉之精粹。服后冥冥中似有天助，奇遇机缘不请自来，福运绵长且深厚。",
        "effect_value": 3,
        "poison_delta": 5,
        "image_url": "",
        "min_realm_stage": "筑基",
        "min_realm_layer": 1,
        "enabled": True,
    },
    {
        "name": "血魄丹",
        "rarity": "下品",
        "pill_type": "qi_blood",
        "description": "丹成赤红如血，散发灼热气息。入口如吞焰火，热流瞬间融入血脉，激发气血本源之力，令体魄更加强健有力。",
        "effect_value": 60,
        "poison_delta": 10,
        "image_url": "",
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "enabled": True,
    },
    {
        "name": "蕴元丹",
        "rarity": "下品",
        "pill_type": "true_yuan",
        "description": "丹体莹润如珠玉，内蕴天地灵气精华。服后温养丹田气海，令真元如涓涓细流汇聚成河，绵延不绝，持久绵长。",
        "effect_value": 50,
        "poison_delta": 9,
        "image_url": "",
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "enabled": True,
    },
    {
        "name": "轻灵丹",
        "rarity": "下品",
        "pill_type": "body_movement",
        "description": "丹丸轻盈如羽，入口即有一股清风之气流转四肢百骸。服后身轻如燕，踏雪无痕，腾挪闪跃之间愈发灵动自如。",
        "effect_value": 4,
        "poison_delta": 6,
        "image_url": "",
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "enabled": True,
    },
    {
        "name": "补天丹",
        "rarity": "极品",
        "pill_type": "root_refine",
        "description": "乃上古遗方所炼，丹成时天花乱舞、地涌金莲。服后可淬炼灵根、升华资质，将低品灵根一阶阶淬炼提升，直至极品之境。",
        "effect_value": 1,
        "poison_delta": 14,
        "image_url": "",
        "min_realm_stage": "筑基",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "洗灵丹",
        "rarity": "极品",
        "pill_type": "root_remold",
        "description": "传说中可重塑根基的逆天丹药，丹成时有异象横生。服后灵根如被天地重新造化，洗尽前尘种种，结果至少为中品灵根。",
        "effect_value": 3,
        "poison_delta": 18,
        "image_url": "",
        "min_realm_stage": "筑基",
        "min_realm_layer": 9,
        "enabled": True,
    },
    {
        "name": "聚气丹",
        "rarity": "下品",
        "pill_type": "cultivation",
        "description": "丹成时有灵气氤氲，入口化为一股澎湃灵气如潮水般涌入经脉。炼气后期修士服之，可迅速补足修为缺口，冲关破境更有底气。",
        "effect_value": 120,
        "poison_delta": 8,
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "回春丹",
        "rarity": "下品",
        "pill_type": "qi_blood",
        "description": "丹色嫩绿如春芽初生，散发盎然生机。入口如春风拂面，药力温和地修复亏损，将气血的源头重新滋养，战后亏空亦能稳住。",
        "effect_value": 90,
        "poison_delta": 8,
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "enabled": True,
    },
    {
        "name": "凝元丹",
        "rarity": "下品",
        "pill_type": "true_yuan",
        "description": "丹体浑圆如珠，内蕴凝练真元之精华。专为本元不足、频繁催动功法者所制，服后可令丹田真元愈发凝实，消耗后恢复更快。",
        "effect_value": 80,
        "poison_delta": 8,
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "锐金丹",
        "rarity": "中品",
        "pill_type": "attack",
        "description": "丹成时隐有金芒闪烁，入口即有一股锐利金气穿透经脉直抵丹田。服后攻伐之力大增，出手愈发凌厉，难撄其锋。",
        "effect_value": 6,
        "poison_delta": 10,
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "enabled": True,
    },
    {
        "name": "护脉丹",
        "rarity": "中品",
        "pill_type": "defense",
        "description": "丹体温润如暖玉，入口化作一道柔和灵光包裹经脉。专为主修防御或频繁斗法者所备，服后经脉愈发坚韧，护体真元亦更加浑厚。",
        "effect_value": 6,
        "poison_delta": 9,
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "enabled": True,
    },
]

DEFAULT_TALISMANS = [
    {
        "name": "疾风符",
        "rarity": "凡品",
        "description": "以疾风鸟羽为引、灵力为墨绘就。符成时有风啸之声隐而不发，贴于身上可借风之力，令身法如风般飘忽不定，先发制人。",
        "attack_bonus": 6,
        "duel_rate_bonus": 4,
        "body_movement_bonus": 6,
        "combat_config": {
            "passives": [
                {
                    "name": "疾风借位",
                    "kind": "dodge",
                    "chance": 20,
                    "dodge_bonus": 12,
                    "duration": 1,
                    "text": "疾风符风起云涌，身形化作一缕青烟，在锋芒即将触及的刹那已飘然远引。",
                }
            ]
        },
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "雷火符",
        "rarity": "下品",
        "description": "取雷击木配合火鸾残羽绘制，符成时隐隐有风雷涌动。引动之际雷火交加，灼热与麻痹并重，令敌人在火焰中颤抖难逃。",
        "attack_bonus": 10,
        "duel_rate_bonus": 5,
        "combat_config": {
            "skills": [
                {
                    "name": "雷火骤落",
                    "kind": "burn",
                    "chance": 34,
                    "flat_damage": 12,
                    "duration": 2,
                    "text": "雷火符凌空炸裂，赤色雷芒携着火星如暴雨般倾泻而下，对手衣袍瞬间被灼热点燃，麻痹之感从四肢蔓延开来。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 7,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "金钟符",
        "rarity": "下品",
        "description": "以金精混合玄铁粉末书就，符成时隐有钟鸣之音。引动后化作金钟虚影笼罩周身，将一切攻击隔绝于钟壁之外。",
        "defense_bonus": 12,
        "duel_rate_bonus": 3,
        "combat_config": {
            "skills": [
                {
                    "name": "金钟护体",
                    "kind": "shield",
                    "chance": 40,
                    "flat_shield": 26,
                    "ratio_percent": 18,
                    "duration": 1,
                    "text": "金钟符激发瞬间，一道古朴厚重的金色钟影拔地而起，将修士牢牢护于钟壁之内，钟身上刻满密密麻麻的防护真纹。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 7,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "轻身符",
        "rarity": "下品",
        "description": "以风脉灵木为基、辅以轻灵草汁描绘。符成时似有清风徐来，贴于身上可令体重如鸿毛，腾挪闪躲皆在谈笑之间。",
        "body_movement_bonus": 12,
        "duel_rate_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "轻烟借步",
                    "kind": "dodge",
                    "chance": 30,
                    "dodge_bonus": 20,
                    "duration": 1,
                    "text": "轻身符化为一缕青烟环绕周身，下一刻人已如惊鸿掠影般闪至三丈之外，只留下一道渐散的残影。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "image_url": "",
        "enabled": True,
    },
    {
        "name": "破甲符",
        "rarity": "中品",
        "description": "取破甲虫外壳配合锐金石粉炼就，符成时锋芒内敛却锐气逼人。引动后可破开对手层层护体灵光，直击其薄弱要害。",
        "attack_bonus": 8,
        "duel_rate_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "裂甲真纹",
                    "kind": "armor_break",
                    "chance": 28,
                    "defense_ratio_percent": 18,
                    "duration": 2,
                    "text": "破甲符贴身即碎，锋锐的真纹如灵蛇钻隙，顺着护体灵气的缝隙一路穿透，破开重重防御直抵本体。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "image_url": "",
        "enabled": True,
    },
]

DEFAULT_TECHNIQUES = [
    {
        "name": "长青诀",
        "rarity": "凡品",
        "technique_type": "cultivation",
        "description": "循序吐纳、温养经脉的入门功法，适合刚踏入仙途的修士稳扎稳打。",
        "comprehension_bonus": 2,
        "true_yuan_bonus": 18,
        "cultivation_bonus": 10,
        "breakthrough_bonus": 5,
        "defense_bonus": 2,
        "combat_config": {
            "passives": [
                {
                    "name": "长青回气",
                    "kind": "heal",
                    "chance": 18,
                    "flat_heal": 10,
                    "ratio_percent": 8,
                    "text": "长青诀运转片刻，经脉中回涌出一缕温润生机。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 1,
        "enabled": True,
    },
    {
        "name": "金刚伏魔功",
        "rarity": "下品",
        "technique_type": "combat",
        "description": "以气血催动筋骨，重攻重势，适合偏战斗路线的修士。",
        "attack_bonus": 12,
        "defense_bonus": 8,
        "qi_blood_bonus": 42,
        "duel_rate_bonus": 6,
        "combat_config": {
            "skills": [
                {
                    "name": "伏魔重拳",
                    "kind": "extra_damage",
                    "chance": 26,
                    "flat_damage": 16,
                    "ratio_percent": 20,
                    "cost_true_yuan": 14,
                    "text": "金刚伏魔功鼓荡气血，一拳打得空气轰然作响。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 1,
        "enabled": True,
    },
    {
        "name": "太虚凝神篇",
        "rarity": "下品",
        "technique_type": "balanced",
        "description": "偏重神识与悟性，可兼顾突破与斗法，是中前期泛用功法。",
        "comprehension_bonus": 5,
        "divine_sense_bonus": 6,
        "attack_bonus": 5,
        "defense_bonus": 5,
        "breakthrough_bonus": 8,
        "combat_config": {
            "skills": [
                {
                    "name": "凝神刺魄",
                    "kind": "extra_damage",
                    "chance": 24,
                    "flat_damage": 12,
                    "ratio_percent": 18,
                    "cost_true_yuan": 12,
                    "text": "太虚凝神篇化神识为细芒，猛然点向对手灵台。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 3,
        "enabled": True,
    },
    {
        "name": "焚天离火诀",
        "rarity": "中品",
        "technique_type": "attack",
        "description": "将离火之气压入经脉，出手霸道，善于叠加灼伤。",
        "attack_bonus": 18,
        "true_yuan_bonus": 30,
        "duel_rate_bonus": 7,
        "combat_config": {
            "opening_text": "离火自掌心涌起，四周空气都被烤得扭曲。",
            "skills": [
                {
                    "name": "离火斩",
                    "kind": "burn",
                    "chance": 34,
                    "flat_damage": 14,
                    "ratio_percent": 20,
                    "duration": 2,
                    "cost_true_yuan": 18,
                    "text": "焚天离火诀催出一道火芒，紧贴护体罡气一路烧进去。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "enabled": True,
    },
    {
        "name": "游龙踏云步",
        "rarity": "中品",
        "technique_type": "movement",
        "description": "以身法见长，讲究腾挪借势，最擅把对手的重击引空。",
        "defense_bonus": 6,
        "body_movement_bonus": 22,
        "duel_rate_bonus": 8,
        "combat_config": {
            "skills": [
                {
                    "name": "云间错影",
                    "kind": "dodge",
                    "chance": 32,
                    "dodge_bonus": 22,
                    "duration": 1,
                    "cost_true_yuan": 12,
                    "text": "游龙踏云步连踏数步，残影在半空拖出一串水波般的弧线。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "enabled": True,
    },
    {
        "name": "玄龟镇岳经",
        "rarity": "中品",
        "technique_type": "defense",
        "description": "护体厚重如山，真元越稳，挨打时反而越显难缠。",
        "defense_bonus": 20,
        "qi_blood_bonus": 72,
        "duel_rate_bonus": 5,
        "combat_config": {
            "skills": [
                {
                    "name": "镇岳灵壁",
                    "kind": "guard",
                    "chance": 36,
                    "defense_ratio_percent": 26,
                    "flat_shield": 20,
                    "duration": 1,
                    "cost_true_yuan": 14,
                    "text": "玄龟镇岳经一沉，护体灵壁如山根般稳稳立住。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "enabled": True,
    },
    {
        "name": "太虚摄魂篇",
        "rarity": "中品",
        "technique_type": "divine",
        "description": "重神识与悟性，擅长看穿破绽，以小代价打出致命空隙。",
        "comprehension_bonus": 6,
        "divine_sense_bonus": 10,
        "attack_bonus": 7,
        "duel_rate_bonus": 6,
        "breakthrough_bonus": 5,
        "combat_config": {
            "skills": [
                {
                    "name": "摄魂灵刺",
                    "kind": "armor_break",
                    "chance": 30,
                    "defense_ratio_percent": 16,
                    "duration": 2,
                    "cost_true_yuan": 16,
                    "text": "太虚摄魂篇聚起一缕神识尖刺，直扎对方灵台与护体交界。",
                }
            ]
        },
        "min_realm_stage": "筑基",
        "min_realm_layer": 4,
        "enabled": True,
    },
    {
        "name": "太玄剑经",
        "rarity": "中品",
        "technique_type": "attack",
        "description": "剑意正大开阖，兼顾身法与攻势，是太玄剑宗的入门真传。",
        "attack_bonus": 12,
        "body_movement_bonus": 8,
        "duel_rate_bonus": 5,
        "comprehension_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "太玄斩岳",
                    "kind": "extra_damage",
                    "chance": 28,
                    "flat_damage": 16,
                    "ratio_percent": 22,
                    "cost_true_yuan": 16,
                    "text": "太玄剑经剑意一振，剑光如山势压落。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "enabled": True,
    },
    {
        "name": "青木长生诀",
        "rarity": "中品",
        "technique_type": "cultivation",
        "description": "药息与木灵相生，擅长养元续航与稳步破关。",
        "cultivation_bonus": 12,
        "true_yuan_bonus": 36,
        "defense_bonus": 6,
        "breakthrough_bonus": 5,
        "fortune_bonus": 4,
        "combat_config": {
            "passives": [
                {
                    "name": "木息回春",
                    "kind": "heal",
                    "chance": 24,
                    "flat_heal": 12,
                    "ratio_percent": 10,
                    "text": "青木药息在经脉间回转，带起一阵温润生机。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 3,
        "enabled": True,
    },
    {
        "name": "天机观星术",
        "rarity": "上品",
        "technique_type": "divine",
        "description": "以星轨推演斗法节奏，兼顾神识、机缘与突破。",
        "comprehension_bonus": 8,
        "divine_sense_bonus": 12,
        "fortune_bonus": 6,
        "breakthrough_bonus": 6,
        "duel_rate_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "观星破隙",
                    "kind": "armor_break",
                    "chance": 30,
                    "defense_ratio_percent": 18,
                    "duration": 2,
                    "cost_true_yuan": 16,
                    "text": "星盘倒映敌手破绽，一线灵机直取护体薄处。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "enabled": True,
    },
    {
        "name": "血煞战典",
        "rarity": "上品",
        "technique_type": "combat",
        "description": "以战养煞，攻势凌厉，越是短兵相接越能打出压迫感。",
        "attack_bonus": 16,
        "qi_blood_bonus": 48,
        "duel_rate_bonus": 6,
        "body_movement_bonus": 6,
        "combat_config": {
            "skills": [
                {
                    "name": "血煞追击",
                    "kind": "extra_damage",
                    "chance": 32,
                    "flat_damage": 20,
                    "ratio_percent": 24,
                    "cost_true_yuan": 18,
                    "text": "血煞战典催得煞气翻涌，趁对手失衡再补上一击。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "幽冥夜行录",
        "rarity": "上品",
        "technique_type": "movement",
        "description": "身入夜色，步法与神识相辅相成，极擅游走切后。",
        "body_movement_bonus": 16,
        "divine_sense_bonus": 8,
        "duel_rate_bonus": 6,
        "defense_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "夜行借影",
                    "kind": "dodge",
                    "chance": 30,
                    "dodge_bonus": 24,
                    "duration": 1,
                    "cost_true_yuan": 14,
                    "text": "幽冥夜行录一转，整个人像被夜色拢进阴影里。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "enabled": True,
    },
    {
        "name": "万毒归元经",
        "rarity": "上品",
        "technique_type": "balanced",
        "description": "将毒息驯作己用，守中有攻，擅长拖长战线后反制。",
        "defense_bonus": 10,
        "fortune_bonus": 5,
        "true_yuan_bonus": 24,
        "attack_bonus": 6,
        "combat_config": {
            "skills": [
                {
                    "name": "毒息侵骨",
                    "kind": "burn",
                    "chance": 28,
                    "flat_damage": 12,
                    "ratio_percent": 16,
                    "duration": 2,
                    "cost_true_yuan": 14,
                    "text": "万毒归元经放出一缕缠骨毒息，缓缓侵蚀对手护体。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "星罗潮生诀",
        "rarity": "上品",
        "technique_type": "balanced",
        "description": "引星潮入体，擅长在攻守之间平顺切换。",
        "attack_bonus": 8,
        "defense_bonus": 8,
        "fortune_bonus": 5,
        "true_yuan_bonus": 24,
        "duel_rate_bonus": 4,
        "combat_config": {
            "skills": [
                {
                    "name": "潮生回浪",
                    "kind": "guard",
                    "chance": 26,
                    "defense_ratio_percent": 18,
                    "flat_shield": 20,
                    "duration": 1,
                    "cost_true_yuan": 14,
                    "text": "潮声回卷，一层层浪纹护在周身，将来势卸去大半。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
    {
        "name": "灵傀百炼篇",
        "rarity": "上品",
        "technique_type": "defense",
        "description": "擅借器意稳固自身，真元与悟性并重，适合长线经营成长。",
        "defense_bonus": 12,
        "comprehension_bonus": 6,
        "true_yuan_bonus": 30,
        "cultivation_bonus": 6,
        "combat_config": {
            "skills": [
                {
                    "name": "傀丝护身",
                    "kind": "guard",
                    "chance": 28,
                    "defense_ratio_percent": 22,
                    "flat_shield": 18,
                    "duration": 1,
                    "cost_true_yuan": 12,
                    "text": "灵傀丝线瞬间交错成网，将冲击层层卸开。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "enabled": True,
    },
    {
        "name": "栖凰离火录",
        "rarity": "上品",
        "technique_type": "attack",
        "description": "火意灵动，不只重爆发，也能提升修炼时的气机运转。",
        "attack_bonus": 14,
        "true_yuan_bonus": 34,
        "cultivation_bonus": 8,
        "duel_rate_bonus": 5,
        "combat_config": {
            "skills": [
                {
                    "name": "凰羽焚风",
                    "kind": "burn",
                    "chance": 30,
                    "flat_damage": 16,
                    "ratio_percent": 22,
                    "duration": 2,
                    "cost_true_yuan": 16,
                    "text": "离火化作凰羽掠过战场，余焰紧贴护体灵光燃烧。",
                }
            ]
        },
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "enabled": True,
    },
]

DEFAULT_TITLES = [
    {"name": "初入仙途", "description": "才刚踏上问道之路，衣袍犹带凡尘风，却已真正推开仙门。", "color": "#94a3b8", "fortune_bonus": 1},
    {"name": "红尘初行者", "description": "踏入仙途后的第一段旅程仍算平凡，却已不再是凡人。", "color": "#94a3b8", "fortune_bonus": 1},
    {"name": "斗法常客", "description": "常在斗法台露面，出手已不再生涩。", "color": "#ef4444", "attack_bonus": 2, "defense_bonus": 2, "duel_rate_bonus": 2},
    {"name": "秘境行者", "description": "熟悉山川遗府与古道残阵，遇事更懂趋吉避凶。", "color": "#0f766e", "divine_sense_bonus": 3, "fortune_bonus": 3},
    {"name": "百折不挠", "description": "屡败不乱，道心未折。", "color": "#2563eb", "qi_blood_bonus": 36, "defense_bonus": 4},
    {"name": "小有机缘", "description": "命数微盛，时常能从险地捡到别人错过的机缘。", "color": "#f59e0b", "fortune_bonus": 4, "true_yuan_bonus": 24},
    {"name": "炼器熟手", "description": "已经懂得分辨火候与材质，不再轻易炸炉。", "color": "#92400e", "comprehension_bonus": 4, "defense_bonus": 2},
    {"name": "丹心妙手", "description": "丹火温润，识药识性，对药力流转颇有心得。", "color": "#059669", "comprehension_bonus": 4, "true_yuan_bonus": 30},
    {"name": "夺宝老手", "description": "见财知势，动手之前总能先找准最值钱的那一件。", "color": "#7c3aed", "attack_bonus": 4, "fortune_bonus": 2, "duel_rate_bonus": 3},
    {"name": "杏坛初开", "description": "第一次收徒立下传承，自此开始教人问道。", "color": "#0ea5e9", "comprehension_bonus": 3, "fortune_bonus": 2},
    {"name": "传道授业", "description": "讲道不倦，已能把门下弟子一路带到出师。", "color": "#2563eb", "comprehension_bonus": 5, "true_yuan_bonus": 36, "cultivation_bonus": 4},
    {"name": "门下高徒", "description": "承其衣钵，终于凭本事独当一面。", "color": "#16a34a", "comprehension_bonus": 3, "attack_bonus": 2, "defense_bonus": 2},
    {"name": "桃李满门", "description": "门下弟子各有成材之姿，传承已成气候。", "color": "#9333ea", "comprehension_bonus": 6, "fortune_bonus": 4, "cultivation_bonus": 6},
]

DEFAULT_MATERIALS = apply_farmable_material_overrides([
    {"name": IMMORTAL_STONE_NAME, "quality_level": 5, "description": "赌坊流出的封灵奇石，石中自藏一缕仙机，可在赌坊中开启随机宝物。"},
    {"name": "寒铁矿", "quality_level": 1, "description": "常见矿料，适合炼制剑胚与基础法器。"},
    {"name": "灵木芯", "quality_level": 1, "description": "灵木深处凝出的芯材，可稳固器物中的灵纹。"},
    {"name": "云纹丝", "quality_level": 1, "description": "轻若无物的灵丝，常用于鞋履与轻甲。"},
    {"name": "归元草", "quality_level": 1, "description": "常用于温养气血与中和药性的低阶灵草。"},
    {"name": "赤炎晶砂", "quality_level": 2, "description": "带火性的细砂，适合攻伐类法器与符箓。"},
    {"name": "凝露花", "quality_level": 2, "description": "夜半凝露而生，适合炼制回春与凝元类丹药。"},
    {"name": "玄龟甲片", "quality_level": 2, "description": "来自妖龟遗骸的厚重甲片，护体效果极好。"},
    {"name": "雷击木", "quality_level": 2, "description": "遭天雷劈过的灵木，最适合承载雷火符纹。"},
    {"name": "青罡剑谱残页", "quality_level": 2, "description": "残缺的剑谱拓本，能补足青罡剑的炼制脉络。"},
    {"name": "回春丹谱残页", "quality_level": 2, "description": "记着几味关键药引顺序的丹谱残页。"},
    {"name": "雷火符谱残页", "quality_level": 2, "description": "隐约还看得清雷火二纹的落笔顺序。"},
    {"name": "金钟符谱残页", "quality_level": 2, "description": "记录了金钟护体符纹的几笔转折。"},
    {"name": "星辉砂", "quality_level": 3, "description": "夜间会微微发亮的细砂，常用于修复古器灵性。"},
    {"name": "地脉岩芯", "quality_level": 3, "description": "深埋地脉的凝实核心，能稳住法宝结构。"},
    {"name": "破损青罡剑胚", "quality_level": 3, "description": "从残剑崖捡回的残损剑胚，尚有修复价值。"},
    {"name": "破损玄龟盾片", "quality_level": 3, "description": "古盾脱落的一角残片，内里灵纹还未彻底断绝。"},
])

DEFAULT_RECIPES = [
    {"name": "青罡剑炼制图", "recipe_kind": "artifact", "result_kind": "artifact", "result_name": "青罡剑", "result_quantity": 1, "base_success_rate": 58, "broadcast_on_success": False, "ingredients": [{"material_name": "寒铁矿", "quantity": 3}, {"material_name": "赤炎晶砂", "quantity": 1}, {"material_name": "青罡剑谱残页", "quantity": 1}]},
    {"name": "玄龟盾炼制图", "recipe_kind": "artifact", "result_kind": "artifact", "result_name": "玄龟盾", "result_quantity": 1, "base_success_rate": 56, "broadcast_on_success": False, "ingredients": [{"material_name": "玄龟甲片", "quantity": 2}, {"material_name": "地脉岩芯", "quantity": 1}, {"material_name": "灵木芯", "quantity": 1}]},
    {"name": "逐云履炼制图", "recipe_kind": "artifact", "result_kind": "artifact", "result_name": "逐云履", "result_quantity": 1, "base_success_rate": 50, "broadcast_on_success": False, "ingredients": [{"material_name": "云纹丝", "quantity": 3}, {"material_name": "雷击木", "quantity": 1}, {"material_name": "星辉砂", "quantity": 1}]},
    {"name": "回春丹丹谱", "recipe_kind": "pill", "result_kind": "pill", "result_name": "回春丹", "result_quantity": 1, "base_success_rate": 66, "broadcast_on_success": False, "ingredients": [{"material_name": "归元草", "quantity": 2}, {"material_name": "凝露花", "quantity": 1}, {"material_name": "回春丹谱残页", "quantity": 1}]},
    {"name": "聚气丹丹谱", "recipe_kind": "pill", "result_kind": "pill", "result_name": "聚气丹", "result_quantity": 1, "base_success_rate": 72, "broadcast_on_success": False, "ingredients": [{"material_name": "归元草", "quantity": 2}, {"material_name": "灵木芯", "quantity": 1}]},
    {"name": "雷火符符谱", "recipe_kind": "talisman", "result_kind": "talisman", "result_name": "雷火符", "result_quantity": 2, "base_success_rate": 60, "broadcast_on_success": False, "ingredients": [{"material_name": "雷击木", "quantity": 2}, {"material_name": "赤炎晶砂", "quantity": 1}, {"material_name": "雷火符谱残页", "quantity": 1}]},
    {"name": "金钟符符谱", "recipe_kind": "talisman", "result_kind": "talisman", "result_name": "金钟符", "result_quantity": 2, "base_success_rate": 60, "broadcast_on_success": False, "ingredients": [{"material_name": "玄龟甲片", "quantity": 1}, {"material_name": "地脉岩芯", "quantity": 1}, {"material_name": "金钟符谱残页", "quantity": 1}]},
    {"name": "古剑残纹修复法", "recipe_kind": "artifact", "result_kind": "artifact", "result_name": "残修青罡古剑", "result_quantity": 1, "base_success_rate": 16, "broadcast_on_success": True, "ingredients": [{"material_name": "破损青罡剑胚", "quantity": 1}, {"material_name": "星辉砂", "quantity": 2}, {"material_name": "地脉岩芯", "quantity": 1}]},
    {"name": "古盾归铸法", "recipe_kind": "artifact", "result_kind": "artifact", "result_name": "残修玄龟古盾", "result_quantity": 1, "base_success_rate": 18, "broadcast_on_success": True, "ingredients": [{"material_name": "破损玄龟盾片", "quantity": 1}, {"material_name": "地脉岩芯", "quantity": 2}, {"material_name": "凝露花", "quantity": 1}]},
]

DEFAULT_SCENES = [
    {
        "name": "黑风山谷",
        "description": "黑风终年呜咽如兽，谷底碎石间埋着散修遗落的家当，正是新手磨砺胆气的好去处。",
        "max_minutes": 30,
        "min_combat_power": 0,
        "event_pool": [
            {"name": "山风异响", "description": "黑风卷石而来，你躲开乱石后在石缝里摸到几块灵石。", "event_type": "danger", "weight": 3, "stone_bonus_min": 8, "stone_bonus_max": 18, "stone_loss_min": 3, "stone_loss_max": 10},
            {"name": "旧修行囊", "description": "山道边有遗落多时的旧行囊，里头还剩下一页模糊图录。", "event_type": "recipe", "weight": 2, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "青罡剑谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 35},
            {"name": "灵风拂面", "description": "一阵带着药香的山风扫过，脚下多了几株被掩住的灵草。", "event_type": "fortune", "weight": 3},
        ],
        "drops": [
            {"reward_kind": "material", "reward_ref_id_name": "寒铁矿", "quantity_min": 1, "quantity_max": 3, "weight": 6, "stone_reward": 4, "event_text": "你在碎石间刨出几块寒铁矿。"},
            {"reward_kind": "material", "reward_ref_id_name": "灵木芯", "quantity_min": 1, "quantity_max": 2, "weight": 5, "stone_reward": 3, "event_text": "山谷古木中藏着尚未腐坏的灵木芯。"},
            {"reward_kind": "material", "reward_ref_id_name": "归元草", "quantity_min": 1, "quantity_max": 3, "weight": 6, "stone_reward": 3, "event_text": "山谷背阴处长着一片归元草。"},
        ],
    },
    {
        "name": "断剑崖",
        "description": "万剑折戟之处，残兵断刃堆积如丘。夜深时可闻旧主剑意低鸣，若有缘，或可唤回一缕剑魂认你为主。",
        "max_minutes": 45,
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "min_combat_power": 850,
        "event_pool": [
            {"name": "剑煞回潮", "description": "残剑煞气忽然倒卷，你虽被震退，却也在裂缝里捡到灵石碎袋。", "event_type": "danger", "weight": 3, "stone_bonus_min": 12, "stone_bonus_max": 28, "stone_loss_min": 6, "stone_loss_max": 16},
            {"name": "残碑拓影", "description": "你在半截石碑上拓出一页残谱。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "青罡剑谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 46},
            {"name": "旧器遗骸", "description": "乱石间压着一截带着余温的破损剑胚。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "破损青罡剑胚", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 18},
        ],
        "drops": [
            {"reward_kind": "material", "reward_ref_id_name": "寒铁矿", "quantity_min": 2, "quantity_max": 4, "weight": 5, "stone_reward": 6, "event_text": "残剑堆下埋着质地不错的寒铁矿。"},
            {"reward_kind": "material", "reward_ref_id_name": "赤炎晶砂", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 8, "event_text": "剑痕摩擦地火，凝出了细碎的赤炎晶砂。"},
            {"reward_kind": "material", "reward_ref_id_name": "星辉砂", "quantity_min": 1, "quantity_max": 2, "weight": 2, "stone_reward": 12, "event_text": "夜色落入崖底，你拾到了闪烁的星辉砂。"},
        ],
    },
    {
        "name": "迷雾药园",
        "description": "不知哪位丹道前辈遗下的药圃，雾中灵草自生自灭百余年，药性虽柔但年份极足。",
        "max_minutes": 40,
        "min_realm_stage": "炼气",
        "min_realm_layer": 3,
        "min_combat_power": 720,
        "event_pool": [
            {"name": "药灵惊走", "description": "药园深处有药灵窜过，追逐间踩断了几根枯藤，也抖落一些灵石。", "event_type": "danger", "weight": 2, "stone_bonus_min": 10, "stone_bonus_max": 22, "stone_loss_min": 2, "stone_loss_max": 8},
            {"name": "丹谱旧页", "description": "药架夹层里竟压着一张回春丹残页。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "回春丹谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 48},
            {"name": "露华未散", "description": "清晨雾气还未散尽，草叶上挂着可入丹的灵露。", "event_type": "fortune", "weight": 3},
        ],
        "drops": [
            {"reward_kind": "material", "reward_ref_id_name": "归元草", "quantity_min": 2, "quantity_max": 4, "weight": 6, "stone_reward": 5, "event_text": "你在药园边角采到几株完整的归元草。"},
            {"reward_kind": "material", "reward_ref_id_name": "凝露花", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 8, "event_text": "花圃中央还活着几朵凝露花。"},
            {"reward_kind": "material", "reward_ref_id_name": "灵木芯", "quantity_min": 1, "quantity_max": 2, "weight": 3, "stone_reward": 5, "event_text": "旧药架中剥出了仍有药香的灵木芯。"},
        ],
    },
    {
        "name": "雷火符窟",
        "description": "天然雷火交加之穴，石壁上残留上古符师刻下的试符痕迹——寻材虽易，雷火却不通人情，稍有不慎便会反噬。",
        "max_minutes": 50,
        "min_realm_stage": "筑基",
        "min_realm_layer": 1,
        "min_combat_power": 1500,
        "event_pool": [
            {"name": "符火反噬", "description": "残符忽然炸裂，火星烫穿袖口，好在地上散落了些灵石。", "event_type": "danger", "weight": 3, "stone_bonus_min": 14, "stone_bonus_max": 30, "stone_loss_min": 6, "stone_loss_max": 18},
            {"name": "符谱显痕", "description": "石壁上显出一段旧符纹，你赶紧拓下一页残纸。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "雷火符谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 42},
            {"name": "钟纹残迹", "description": "窟深处的石壁还有半面金钟纹路。", "event_type": "recipe", "weight": 2, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "金钟符谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 34},
        ],
        "drops": [
            {"reward_kind": "material", "reward_ref_id_name": "雷击木", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 8, "event_text": "窟顶断木带着焦痕，是上好的雷击木。"},
            {"reward_kind": "material", "reward_ref_id_name": "赤炎晶砂", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 7, "event_text": "石缝里凝着一层赤红晶砂。"},
            {"reward_kind": "material", "reward_ref_id_name": "星辉砂", "quantity_min": 1, "quantity_max": 1, "weight": 2, "stone_reward": 10, "event_text": "雷火碰撞后，窟底留下了一抹星辉砂。"},
        ],
    },
    {
        "name": "玄龟古潭",
        "description": "潭深不见底，传有千年玄龟沉眠其中。每逢月圆，潭底便会浮起被水压碾碎的古盾残片与丝丝地脉灵息。",
        "max_minutes": 50,
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "min_combat_power": 1800,
        "event_pool": [
            {"name": "水压暗涌", "description": "古潭忽起暗流，你被逼得连退几步，腰间灵石也被卷走少许。", "event_type": "danger", "weight": 3, "stone_bonus_min": 16, "stone_bonus_max": 28, "stone_loss_min": 8, "stone_loss_max": 20},
            {"name": "古盾残片", "description": "潭底泥沙里埋着一块仍有灵纹的盾片。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "破损玄龟盾片", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 16},
            {"name": "地脉回响", "description": "潭底有地脉回响，石缝间的岩芯纹理越发清晰。", "event_type": "fortune", "weight": 3},
        ],
        "drops": [
            {"reward_kind": "material", "reward_ref_id_name": "玄龟甲片", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 8, "event_text": "你自潭边剥下几块保存完好的玄龟甲片。"},
            {"reward_kind": "material", "reward_ref_id_name": "地脉岩芯", "quantity_min": 1, "quantity_max": 2, "weight": 3, "stone_reward": 12, "event_text": "潭底石缝里藏着沉重的地脉岩芯。"},
            {"reward_kind": "material", "reward_ref_id_name": "凝露花", "quantity_min": 1, "quantity_max": 2, "weight": 3, "stone_reward": 6, "event_text": "古潭边缘竟生着耐寒的凝露花。"},
        ],
    },
]

DEFAULT_ACHIEVEMENTS = [
    {"achievement_key": "envelope_novice", "name": "福泽初现", "description": "累计发放 1 次灵石红包。", "metric_key": "red_envelope_sent_count", "target_value": 1, "sort_order": 10, "reward_config": {"spiritual_stone": 20}},
    {"achievement_key": "envelope_generous", "name": "散财有道", "description": "累计通过红包发出 500 灵石。", "metric_key": "red_envelope_sent_stone", "target_value": 500, "sort_order": 11, "reward_config": {"cultivation": 80, "reward_title_names": ["红尘初行者"]}},
    {"achievement_key": "envelope_rainfall", "name": "灵雨满楼", "description": "累计发放 12 次灵石红包。", "metric_key": "red_envelope_sent_count", "target_value": 12, "sort_order": 12, "reward_config": {"spiritual_stone": 88, "cultivation": 88}},
    {"achievement_key": "envelope_bless_all", "name": "福泽八方", "description": "累计通过红包发出 5000 灵石。", "metric_key": "red_envelope_sent_stone", "target_value": 5000, "sort_order": 13, "reward_config": {"cultivation": 260, "reward_title_names": ["福缘广施"]}},
    {"achievement_key": "duel_rookie", "name": "试锋一战", "description": "累计发起 1 场斗法。", "metric_key": "duel_initiated_count", "target_value": 1, "sort_order": 20, "reward_config": {"spiritual_stone": 18}},
    {"achievement_key": "duel_veteran", "name": "斗法常客", "description": "累计发起 20 场斗法。", "metric_key": "duel_initiated_count", "target_value": 20, "sort_order": 21, "reward_config": {"cultivation": 160, "reward_title_names": ["斗法常客"]}},
    {"achievement_key": "duel_first_win", "name": "首战告捷", "description": "累计赢下 1 场斗法。", "metric_key": "duel_win_count", "target_value": 1, "sort_order": 22, "reward_config": {"spiritual_stone": 30}},
    {"achievement_key": "duel_ten_wins", "name": "胜势渐成", "description": "累计赢下 10 场斗法。", "metric_key": "duel_win_count", "target_value": 10, "sort_order": 23, "reward_config": {"cultivation": 180, "reward_title_names": ["小有机缘"]}},
    {"achievement_key": "duel_hardened", "name": "百折不挠", "description": "累计经历 10 场斗法失利。", "metric_key": "duel_loss_count", "target_value": 10, "sort_order": 24, "reward_config": {"spiritual_stone": 66, "reward_title_names": ["百折不挠"]}},
    {"achievement_key": "duel_many_battles", "name": "鏖战不息", "description": "累计参与 50 场斗法。", "metric_key": "duel_total_count", "target_value": 50, "sort_order": 25, "reward_config": {"spiritual_stone": 120, "cultivation": 120}},
    {"achievement_key": "duel_hundred_battles", "name": "百战称雄", "description": "累计参与 150 场斗法。", "metric_key": "duel_total_count", "target_value": 150, "sort_order": 26, "reward_config": {"cultivation": 280, "reward_title_names": ["百战无双"]}},
    {"achievement_key": "duel_fifty_wins", "name": "连胜成势", "description": "累计赢下 50 场斗法。", "metric_key": "duel_win_count", "target_value": 50, "sort_order": 27, "reward_config": {"spiritual_stone": 188, "cultivation": 260, "reward_title_names": ["斗战宗师"]}},
    {"achievement_key": "rob_novice", "name": "顺手牵机缘", "description": "累计尝试偷窃 1 次。", "metric_key": "rob_attempt_count", "target_value": 1, "sort_order": 30, "reward_config": {"spiritual_stone": 16}},
    {"achievement_key": "rob_success", "name": "夺宝老手", "description": "累计偷窃成功 10 次。", "metric_key": "rob_success_count", "target_value": 10, "sort_order": 31, "reward_config": {"cultivation": 180, "reward_title_names": ["夺宝老手"]}},
    {"achievement_key": "rob_fail_twenty", "name": "失手亦修行", "description": "累计偷窃失败 20 次。", "metric_key": "rob_fail_count", "target_value": 20, "sort_order": 32, "reward_config": {"spiritual_stone": 96, "cultivation": 96}},
    {"achievement_key": "rob_stone_hunter", "name": "黑夜敛财", "description": "累计通过偷窃获得 800 灵石。", "metric_key": "rob_stone_total", "target_value": 800, "sort_order": 33, "reward_config": {"spiritual_stone": 128, "cultivation": 128}},
    {"achievement_key": "rob_shadow_hand", "name": "劫运无声", "description": "累计通过偷窃获得 3000 灵石。", "metric_key": "rob_stone_total", "target_value": 3000, "sort_order": 34, "reward_config": {"cultivation": 240, "reward_title_names": ["劫运之手"]}},
    {"achievement_key": "gift_kindness", "name": "同道相助", "description": "累计赠送 300 灵石。", "metric_key": "gift_sent_stone", "target_value": 300, "sort_order": 40, "reward_config": {"cultivation": 100}},
    {"achievement_key": "gift_often", "name": "同道有情", "description": "累计赠送灵石 10 次。", "metric_key": "gift_sent_count", "target_value": 10, "sort_order": 41, "reward_config": {"spiritual_stone": 96, "cultivation": 96}},
    {"achievement_key": "gift_grand_benefactor", "name": "义贯仙途", "description": "累计赠送 2000 灵石。", "metric_key": "gift_sent_stone", "target_value": 2000, "sort_order": 42, "reward_config": {"cultivation": 220, "reward_title_names": ["义薄云天"]}},
    {"achievement_key": "mentor_first", "name": "杏坛开讲", "description": "累计成功收下 1 名徒弟。", "metric_key": "mentor_accept_count", "target_value": 1, "sort_order": 45, "reward_config": {"spiritual_stone": 48, "reward_title_names": ["杏坛初开"]}},
    {"achievement_key": "mentor_teach_many", "name": "言传身教", "description": "累计完成 10 次传道。", "metric_key": "mentor_teach_count", "target_value": 10, "sort_order": 46, "reward_config": {"cultivation": 140}},
    {"achievement_key": "mentor_graduate", "name": "桃李成行", "description": "累计带出 3 名出师弟子。", "metric_key": "mentor_graduate_count", "target_value": 3, "sort_order": 47, "reward_config": {"cultivation": 220, "reward_title_names": ["桃李满门"]}},
    {"achievement_key": "disciple_seek", "name": "勤学不辍", "description": "累计完成 8 次问道。", "metric_key": "disciple_consult_count", "target_value": 8, "sort_order": 48, "reward_config": {"spiritual_stone": 80}},
    {"achievement_key": "disciple_graduate", "name": "承道出山", "description": "累计成功出师 1 次。", "metric_key": "disciple_graduate_count", "target_value": 1, "sort_order": 49, "reward_config": {"cultivation": 180, "reward_title_names": ["门下高徒"]}},
    {"achievement_key": "mentor_teach_master", "name": "传道不倦", "description": "累计完成 30 次传道。", "metric_key": "mentor_teach_count", "target_value": 30, "sort_order": 46, "reward_config": {"cultivation": 200, "reward_title_names": ["传道名宿"]}},
    {"achievement_key": "mentor_lineage_master", "name": "一门桃李", "description": "累计带出 8 名出师弟子。", "metric_key": "mentor_graduate_count", "target_value": 8, "sort_order": 47, "reward_config": {"cultivation": 320, "reward_title_names": ["桃李宗师"]}},
    {"achievement_key": "craft_first_success", "name": "炉火初明", "description": "累计成功炼制 1 次。", "metric_key": "craft_success_count", "target_value": 1, "sort_order": 50, "reward_config": {"spiritual_stone": 28}},
    {"achievement_key": "craft_ten_success", "name": "炼器熟手", "description": "累计成功炼制 10 次。", "metric_key": "craft_success_count", "target_value": 10, "sort_order": 51, "reward_config": {"cultivation": 180, "reward_title_names": ["炼器熟手"]}},
    {"achievement_key": "repair_master", "name": "残器归真", "description": "累计成功修复 1 件破损法宝。", "metric_key": "repair_success_count", "target_value": 1, "sort_order": 52, "reward_config": {"spiritual_stone": 120, "titles": []}},
    {"achievement_key": "craft_attempt_thirty", "name": "百炼不殆", "description": "累计尝试炼制 30 次。", "metric_key": "craft_attempt_count", "target_value": 30, "sort_order": 50, "reward_config": {"spiritual_stone": 108, "cultivation": 108}},
    {"achievement_key": "craft_grandmaster", "name": "炉火归一", "description": "累计成功炼制 40 次。", "metric_key": "craft_success_count", "target_value": 40, "sort_order": 51, "reward_config": {"cultivation": 260, "reward_title_names": ["万炉归一"]}},
    {"achievement_key": "repair_five_master", "name": "天工回春", "description": "累计成功修复 5 件破损法宝。", "metric_key": "repair_success_count", "target_value": 5, "sort_order": 52, "reward_config": {"spiritual_stone": 188, "cultivation": 188, "reward_title_names": ["天工妙手"]}},
    {"achievement_key": "explore_ten", "name": "秘境行者", "description": "累计完成 10 次秘境探索。", "metric_key": "exploration_count", "target_value": 10, "sort_order": 60, "reward_config": {"cultivation": 120, "reward_title_names": ["秘境行者"]}},
    {"achievement_key": "explore_recipe", "name": "残页搜罗者", "description": "累计获得 5 次配方残页。", "metric_key": "exploration_recipe_drop_count", "target_value": 5, "sort_order": 61, "reward_config": {"spiritual_stone": 88}},
    {"achievement_key": "explore_danger_survivor", "name": "险中求活", "description": "累计在秘境中遭遇危险事件 15 次并活着归来。", "metric_key": "exploration_danger_count", "target_value": 15, "sort_order": 62, "reward_config": {"spiritual_stone": 150, "reward_title_names": ["险境还生"]}},
    {"achievement_key": "explore_treasure_hunter", "name": "洞天搜珍", "description": "累计完成 40 次秘境探索。", "metric_key": "exploration_count", "target_value": 40, "sort_order": 63, "reward_config": {"cultivation": 240, "reward_title_names": ["洞天寻珍客"]}},
    {"achievement_key": "arena_founder", "name": "开坛立擂", "description": "累计开启 1 次群擂台。", "metric_key": "arena_open_count", "target_value": 1, "sort_order": 70, "reward_config": {"spiritual_stone": 36}},
    {"achievement_key": "arena_crowned", "name": "初登擂主", "description": "累计成为 1 次擂主。", "metric_key": "arena_crowned_count", "target_value": 1, "sort_order": 71, "reward_config": {"cultivation": 96}},
    {"achievement_key": "arena_defender", "name": "擂上留名", "description": "累计守擂成功 3 次。", "metric_key": "arena_defend_win_count", "target_value": 3, "sort_order": 72, "reward_config": {"spiritual_stone": 120, "cultivation": 120}},
    {"achievement_key": "arena_final_winner", "name": "擂台终主", "description": "累计以最终擂主身份完成 1 次擂台结算。", "metric_key": "arena_final_win_count", "target_value": 1, "sort_order": 73, "reward_config": {"spiritual_stone": 188, "cultivation": 188}},
    {"achievement_key": "arena_defend_ten", "name": "擂台铁壁", "description": "累计守擂成功 10 次。", "metric_key": "arena_defend_win_count", "target_value": 10, "sort_order": 72, "reward_config": {"spiritual_stone": 220, "cultivation": 180}},
    {"achievement_key": "arena_final_five", "name": "擂主镇场", "description": "累计以最终擂主身份完成 5 次擂台结算。", "metric_key": "arena_final_win_count", "target_value": 5, "sort_order": 73, "reward_config": {"spiritual_stone": 300, "cultivation": 300, "reward_title_names": ["擂台霸主"]}},
]

SEED_QUALITY_LEVELS = {
    "凡品": 1,
    "下品": 2,
    "中品": 3,
    "上品": 4,
    "极品": 5,
    "仙品": 6,
    "先天至宝": 7,
}

SEED_MATERIAL_BLUEPRINTS = {
    "下品": [
        "青霜铁", "灵桑皮", "暖玉粉", "风鹤羽", "赤流砂",
        "寒水露", "厚土晶", "玄松脂", "离火絮", "断岳石",
    ],
    "中品": [
        "星河砂", "玄龟骨晶", "云母银丝", "赤霄铜髓", "灵雾草心",
        "霜华露珠", "金乌羽粉", "沧浪冰魄", "太乙木心", "断雷砂",
    ],
    "上品": [
        "太虚陨铁", "九曲灵丝", "地脉玉髓", "龙鳞铁片", "天游羽晶",
        "幻月晶核", "紫焰琉砂", "天游莲芯", "玄冰胆", "星陨木根",
    ],
    "极品": [
        "玄天乌金", "九霄凤羽", "太阴寒髓", "炽阳赤晶", "镇岳龙骨",
        "无垢净沙", "璇玑星砂", "幽冥墨玉", "太华灵液", "万象青金",
    ],
    "仙品": [
        "仙凰真羽", "苍穹雷髓", "九转金液", "造化玉露", "混元息壤",
        "玄冥冰魄", "太清星尘", "赤霄凤血", "长生灵藤心", "太初光砂",
        "玄苍龟晶", "太虚雷纹钢", "云阙天蚕丝",
    ],
    "先天至宝": [
        "先天混沌石", "太初紫气晶", "鸿蒙天髓", "造化青莲瓣", "周天星核",
        "玄黄母气", "大罗神铁", "无相天露", "太始龙骨", "元始真砂",
        "混元界壳", "劫寂玄纱", "太易风痕晶",
    ],
}

ARTIFACT_SET_BLUEPRINTS = [
    {
        "name": "青霄巡天套",
        "description": "轻灵迅捷的正道剑修套装，重攻伐与腾挪。",
        "required_count": 2,
        "attack_bonus": 10,
        "body_movement_bonus": 12,
        "duel_rate_bonus": 4,
        "items": [
            {
                "name": "青霄巡天剑",
                "rarity": "下品",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 24,
                "body_movement_bonus": 6,
                "duel_rate_bonus": 4,
                "description": "剑锋轻颤如燕掠青云，专为快攻而生。",
                "combat_config": {"passives": [{"name": "青霄掠影", "kind": "extra_damage", "chance": 24, "flat_damage": 14, "ratio_percent": 18, "text": "青霄巡天剑借身法加速，一剑斜斩而下。"}]},
                "materials": [("青霜铁", 3), ("风鹤羽", 2), ("赤流砂", 1)],
                "success": 64,
            },
            {
                "name": "青霄巡天甲",
                "rarity": "下品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 18,
                "qi_blood_bonus": 38,
                "body_movement_bonus": 4,
                "description": "以灵桑皮与暖玉粉熬炼而成，轻而不薄。",
                "combat_config": {"passives": [{"name": "巡天气罩", "kind": "shield", "chance": 20, "flat_shield": 18, "ratio_percent": 14, "text": "青霄巡天甲化出一层薄薄气罩，将余波卸去。"}]},
                "materials": [("灵桑皮", 3), ("暖玉粉", 1), ("厚土晶", 1)],
                "success": 62,
            },
            {
                "name": "青霄踏云靴",
                "rarity": "下品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "defense_bonus": 8,
                "body_movement_bonus": 18,
                "duel_rate_bonus": 3,
                "description": "落地无尘，最擅错步改位。",
                "combat_config": {"passives": [{"name": "踏云错位", "kind": "dodge", "chance": 24, "dodge_bonus": 18, "duration": 1, "text": "青霄踏云靴轻轻一点，人已错开半步。"}]},
                "materials": [("风鹤羽", 2), ("离火絮", 2), ("寒水露", 1)],
                "success": 63,
            },
        ],
    },
    {
        "name": "玄岳镇海套",
        "description": "以守为攻的厚重战套，适合护体与反打路线。",
        "required_count": 2,
        "defense_bonus": 14,
        "qi_blood_bonus": 66,
        "duel_rate_bonus": 3,
        "items": [
            {
                "name": "玄岳镇海枪",
                "rarity": "中品",
                "artifact_type": "battle",
                "artifact_role": "guardian",
                "equip_slot": "weapon",
                "attack_bonus": 30,
                "defense_bonus": 10,
                "description": "枪势沉稳如山岳压潮，破招时极具压迫。",
                "combat_config": {"passives": [{"name": "岳势横扫", "kind": "extra_damage", "chance": 28, "flat_damage": 20, "ratio_percent": 20, "text": "玄岳镇海枪横扫一轮，枪势压得对手难以喘息。"}]},
                "materials": [("星河砂", 2), ("玄龟骨晶", 2), ("断雷砂", 1)],
                "success": 58,
            },
            {
                "name": "玄岳护腿",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "legs",
                "defense_bonus": 22,
                "qi_blood_bonus": 56,
                "body_movement_bonus": 4,
                "description": "腿部沉稳若磐石，硬撼重击而不乱。",
                "combat_config": {"passives": [{"name": "镇岳稳身", "kind": "guard", "chance": 26, "defense_ratio_percent": 20, "duration": 1, "text": "玄岳护腿灌入地脉之力，硬生生立稳脚步。"}]},
                "materials": [("玄龟骨晶", 2), ("太乙木心", 1), ("云母银丝", 2)],
                "success": 56,
            },
            {
                "name": "玄岳镇心佩",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "necklace",
                "defense_bonus": 12,
                "true_yuan_bonus": 42,
                "cultivation_bonus": 8,
                "description": "佩玉厚润，能稳住真元与心神。",
                "combat_config": {"passives": [{"name": "镇海归元", "kind": "heal", "chance": 20, "flat_heal": 18, "ratio_percent": 12, "text": "玄岳镇心佩泛起清光，缓缓抚平受创经脉。"}]},
                "materials": [("霜华露珠", 2), ("沧浪冰魄", 1), ("云母银丝", 2)],
                "success": 57,
            },
        ],
    },
    {
        "name": "夜魇逐命套",
        "description": "邪道奇袭套装，强调爆发、闪避与蚕食真元。",
        "required_count": 2,
        "attack_bonus": 16,
        "duel_rate_bonus": 6,
        "body_movement_bonus": 10,
        "items": [
            {
                "name": "夜魇夺命刃",
                "rarity": "上品",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 42,
                "fortune_bonus": 6,
                "duel_rate_bonus": 7,
                "description": "刀身细窄，最擅在死角递出夺命一击。",
                "combat_config": {"passives": [{"name": "夜魇追魂", "kind": "armor_break", "chance": 32, "defense_ratio_percent": 20, "duration": 2, "text": "夜魇夺命刃贴着护体缝隙一抹而过，灵罡顿时虚浮。"}]},
                "materials": [("太虚陨铁", 2), ("紫焰琉砂", 2), ("幻月晶核", 1)],
                "success": 52,
            },
            {
                "name": "夜魇潜影履",
                "rarity": "上品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "defense_bonus": 12,
                "body_movement_bonus": 28,
                "duel_rate_bonus": 6,
                "description": "步落无声，残影却能扰乱神识。",
                "combat_config": {"passives": [{"name": "潜影迷踪", "kind": "dodge", "chance": 30, "dodge_bonus": 24, "duration": 1, "text": "夜魇潜影履轻点地面，身形已隐入一缕暗影。"}]},
                "materials": [("九曲灵丝", 2), ("天游羽晶", 2), ("幻月晶核", 1)],
                "success": 53,
            },
            {
                "name": "夜魇摄魂链",
                "rarity": "上品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "necklace",
                "attack_bonus": 16,
                "divine_sense_bonus": 18,
                "true_yuan_bonus": 36,
                "description": "细链如蛇，能牵动对手神魂起伏。",
                "combat_config": {"passives": [{"name": "摄魂乱念", "kind": "burn", "chance": 24, "flat_damage": 18, "ratio_percent": 14, "duration": 2, "text": "夜魇摄魂链忽然一紧，对手神魂如被细火炙烤。"}]},
                "materials": [("龙鳞铁片", 1), ("玄冰胆", 1), ("紫焰琉砂", 2)],
                "success": 50,
            },
        ],
    },
    {
        "name": "星河归元套",
        "description": "偏悟性与修炼的高阶法套，适合稳健积累。",
        "required_count": 3,
        "cultivation_bonus": 18,
        "comprehension_bonus": 12,
        "true_yuan_bonus": 88,
        "items": [
            {
                "name": "星河归元冠",
                "rarity": "极品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "helmet",
                "comprehension_bonus": 18,
                "divine_sense_bonus": 18,
                "cultivation_bonus": 10,
                "description": "戴冠观星，神识更易沉入周天运转。",
                "combat_config": {"passives": [{"name": "星河静神", "kind": "heal", "chance": 22, "flat_heal": 24, "ratio_percent": 18, "text": "星河归元冠垂下细碎星芒，令心神与经脉同时平稳。"}]},
                "materials": [("玄天乌金", 1), ("璇玑星砂", 2), ("太华灵液", 1)],
                "success": 46,
            },
            {
                "name": "星河归元袍",
                "rarity": "极品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 28,
                "qi_blood_bonus": 88,
                "cultivation_bonus": 8,
                "description": "法袍绣满周天星纹，守势圆融。",
                "combat_config": {"passives": [{"name": "周天回环", "kind": "shield", "chance": 24, "flat_shield": 30, "ratio_percent": 20, "text": "星河归元袍星纹齐亮，护体之力连成一圈。"}]},
                "materials": [("九霄凤羽", 1), ("太阴寒髓", 1), ("万象青金", 2)],
                "success": 45,
            },
            {
                "name": "星河归元环",
                "rarity": "极品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "ring",
                "true_yuan_bonus": 96,
                "fortune_bonus": 10,
                "cultivation_bonus": 12,
                "description": "环内刻着归元纹，最适合久战回气。",
                "combat_config": {"passives": [{"name": "归元回潮", "kind": "heal", "chance": 18, "flat_heal": 26, "ratio_percent": 20, "text": "星河归元环轻震一声，真元回潮般涌回丹田。"}]},
                "materials": [("无垢净沙", 2), ("璇玑星砂", 2), ("幽冥墨玉", 1)],
                "success": 44,
            },
        ],
    },
    {
        "name": "紫宸天阙套",
        "description": "仙品天庭遗套，兼顾攻伐、护体与裂空机动。",
        "required_count": 3,
        "attack_bonus": 22,
        "defense_bonus": 18,
        "duel_rate_bonus": 8,
        "items": [
            {
                "name": "紫宸天刀",
                "rarity": "仙品",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 58,
                "true_yuan_bonus": 66,
                "duel_rate_bonus": 8,
                "description": "刀势可撕开灵压，斩出一道短暂裂缝。",
                "combat_config": {"passives": [{"name": "裂空斩", "kind": "extra_damage", "chance": 34, "flat_damage": 30, "ratio_percent": 26, "text": "紫宸天刀凌空一斩，竟将灵气生生切开一道缝隙。"}]},
                "materials": [("仙凰真羽", 1), ("苍穹雷髓", 1), ("赤霄凤血", 1), ("太初光砂", 1)],
                "success": 36,
                "broadcast": True,
            },
            {
                "name": "紫宸战铠",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 42,
                "qi_blood_bonus": 132,
                "body_movement_bonus": 10,
                "description": "战铠内藏天阙旧阵，能缓冲重创。",
                "combat_config": {"passives": [{"name": "阙门护身", "kind": "shield", "chance": 28, "flat_shield": 42, "ratio_percent": 24, "text": "紫宸战铠外层阵纹迸亮，将巨力一层层削去。"}]},
                "materials": [("混元息壤", 1), ("玄冥冰魄", 1), ("九转金液", 1), ("长生灵藤心", 1)],
                "success": 35,
                "broadcast": True,
            },
            {
                "name": "紫宸飞履",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "defense_bonus": 18,
                "body_movement_bonus": 36,
                "duel_rate_bonus": 8,
                "description": "一念踏空，落点可在数丈之外。",
                "combat_config": {"passives": [{"name": "飞履瞬空", "kind": "dodge", "chance": 32, "dodge_bonus": 32, "duration": 1, "text": "紫宸飞履一踏而空，身形似乎在原地消失了一瞬。"}]},
                "materials": [("造化玉露", 1), ("太清星尘", 1), ("仙凰真羽", 1), ("苍穹雷髓", 1)],
                "success": 38,
                "broadcast": True,
            },
        ],
    },
    {
        "name": "太初大道套",
        "description": "先天至宝级大道遗装，兼具大道护持与绝巅杀伐。",
        "required_count": 3,
        "attack_bonus": 30,
        "defense_bonus": 26,
        "breakthrough_bonus": 18,
        "items": [
            {
                "name": "太初道剑",
                "rarity": "先天至宝",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 72,
                "comprehension_bonus": 24,
                "duel_rate_bonus": 10,
                "description": "剑出无声，却像天地本身在轻轻校正一切偏差。",
                "combat_config": {"passives": [{"name": "大道裁断", "kind": "armor_break", "chance": 36, "defense_ratio_percent": 28, "duration": 2, "text": "太初道剑轻轻一点，对手护体就像被天地法则直接削去一层。"}]},
                "materials": [("先天混沌石", 1), ("太初紫气晶", 1), ("大罗神铁", 1), ("元始真砂", 1)],
                "success": 24,
                "broadcast": True,
            },
            {
                "name": "太初道甲",
                "rarity": "先天至宝",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 58,
                "qi_blood_bonus": 188,
                "breakthrough_bonus": 10,
                "description": "道纹如水流淌，护体之时仿佛立于大道中央。",
                "combat_config": {"passives": [{"name": "大道垂护", "kind": "shield", "chance": 30, "flat_shield": 56, "ratio_percent": 28, "text": "太初道甲上的古老道纹同时亮起，护体光幕层层叠起。"}]},
                "materials": [("鸿蒙天髓", 1), ("造化青莲瓣", 1), ("玄黄母气", 1), ("太始龙骨", 1)],
                "success": 22,
                "broadcast": True,
            },
            {
                "name": "太初道环",
                "rarity": "先天至宝",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "ring",
                "true_yuan_bonus": 168,
                "fortune_bonus": 24,
                "cultivation_bonus": 18,
                "description": "一环在指，周天万象都像慢了半拍。",
                "combat_config": {"passives": [{"name": "一炁回环", "kind": "heal", "chance": 24, "flat_heal": 46, "ratio_percent": 28, "text": "太初道环轻轻一震，体内一炁周流不绝。"}]},
                "materials": [("周天星核", 1), ("无相天露", 1), ("先天混沌石", 1), ("鸿蒙天髓", 1)],
                "success": 23,
                "broadcast": True,
            },
        ],
    },
    {
        "name": "玄穹镇劫套",
        "description": "仙品重甲御守套装，补足高阶盾、甲、靴位，偏护体、卸力与反震。",
        "required_count": 3,
        "defense_bonus": 24,
        "qi_blood_bonus": 140,
        "duel_rate_bonus": 6,
        "items": [
            {
                "name": "玄穹镇劫戟",
                "rarity": "仙品",
                "artifact_type": "battle",
                "artifact_role": "guardian",
                "equip_slot": "weapon",
                "attack_bonus": 56,
                "defense_bonus": 18,
                "true_yuan_bonus": 42,
                "duel_rate_bonus": 7,
                "description": "戟锋沉如潮门，既能横断来势，也能借反震之力回击。",
                "combat_config": {"passives": [{"name": "镇劫回潮", "kind": "extra_damage", "chance": 30, "flat_damage": 28, "ratio_percent": 22, "text": "玄穹镇劫戟借对方余势一拧，反震之力顺着戟锋轰然回卷。"}]},
                "materials": [("太虚雷纹钢", 1), ("玄苍龟晶", 1), ("混元息壤", 1), ("太清星尘", 1)],
                "success": 34,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 2,
            },
            {
                "name": "玄穹镇劫盾",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "shield",
                "defense_bonus": 52,
                "qi_blood_bonus": 156,
                "duel_rate_bonus": 6,
                "description": "盾面铭着龟天古纹，受击时会像潮汐一般层层卸力。",
                "combat_config": {"passives": [{"name": "镇劫玄幕", "kind": "shield", "chance": 30, "flat_shield": 46, "ratio_percent": 26, "text": "玄穹镇劫盾亮起深青古纹，护体光幕一层接一层展开。"}]},
                "materials": [("玄苍龟晶", 1), ("混元息壤", 1), ("九转金液", 1), ("太虚雷纹钢", 1)],
                "success": 32,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 3,
            },
            {
                "name": "玄穹覆海甲",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 48,
                "qi_blood_bonus": 172,
                "true_yuan_bonus": 30,
                "description": "甲片相扣如重潮叠浪，最擅把巨力拆成绵长余波。",
                "combat_config": {"passives": [{"name": "覆海卸潮", "kind": "guard", "chance": 28, "defense_ratio_percent": 26, "duration": 1, "text": "玄穹覆海甲甲片层层错开，将正面巨力拆成细密潮劲。"}]},
                "materials": [("玄苍龟晶", 1), ("长生灵藤心", 1), ("九转金液", 1), ("云阙天蚕丝", 1)],
                "success": 31,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 4,
            },
            {
                "name": "玄穹踏界靴",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "defense_bonus": 20,
                "body_movement_bonus": 34,
                "duel_rate_bonus": 7,
                "description": "靴底古纹与潮门共鸣，退可踏潮卸势，进可一步越界。",
                "combat_config": {"passives": [{"name": "踏界避潮", "kind": "dodge", "chance": 30, "dodge_bonus": 28, "duration": 1, "text": "玄穹踏界靴在脚下荡开一圈暗潮，人影已错到攻势之外。"}]},
                "materials": [("云阙天蚕丝", 1), ("太清星尘", 1), ("造化玉露", 1), ("太虚雷纹钢", 1)],
                "success": 33,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 3,
            },
        ],
    },
    {
        "name": "云阙巡霄套",
        "description": "仙品轻甲巡天套装，补足高阶甲、盾、靴的机动路线，强调裂空追击。",
        "required_count": 3,
        "attack_bonus": 20,
        "body_movement_bonus": 26,
        "true_yuan_bonus": 72,
        "items": [
            {
                "name": "云阙裂穹刃",
                "rarity": "仙品",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 60,
                "body_movement_bonus": 18,
                "duel_rate_bonus": 8,
                "description": "刃身细长如天缝，最擅在高速错位中递出追命一斩。",
                "combat_config": {"passives": [{"name": "裂穹逐影", "kind": "extra_damage", "chance": 32, "flat_damage": 30, "ratio_percent": 24, "text": "云阙裂穹刃借身法拉出一道细长天痕，追着退势再补一斩。"}]},
                "materials": [("云阙天蚕丝", 1), ("赤霄凤血", 1), ("苍穹雷髓", 1), ("太初光砂", 1)],
                "success": 35,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 5,
            },
            {
                "name": "云阙流光甲",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 38,
                "qi_blood_bonus": 126,
                "body_movement_bonus": 12,
                "description": "甲如流霞铺身，既轻且韧，能在高速突进中维持护体完整。",
                "combat_config": {"passives": [{"name": "流光护身", "kind": "shield", "chance": 26, "flat_shield": 38, "ratio_percent": 20, "text": "云阙流光甲亮起大片霞纹，把逼近身侧的杀机瞬间弹开。"}]},
                "materials": [("云阙天蚕丝", 1), ("造化玉露", 1), ("长生灵藤心", 1), ("太清星尘", 1)],
                "success": 34,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 5,
            },
            {
                "name": "云阙逐电靴",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "defense_bonus": 16,
                "body_movement_bonus": 40,
                "duel_rate_bonus": 9,
                "description": "靴跟蓄着雷光，一念借势，身法便比电芒更快半拍。",
                "combat_config": {"passives": [{"name": "逐电瞬闪", "kind": "dodge", "chance": 34, "dodge_bonus": 34, "duration": 1, "text": "云阙逐电靴雷纹炸亮，原地只余一抹被拉长的残像。"}]},
                "materials": [("云阙天蚕丝", 1), ("苍穹雷髓", 1), ("赤霄凤血", 1), ("太虚雷纹钢", 1)],
                "success": 36,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 6,
            },
            {
                "name": "云阙回风盾",
                "rarity": "仙品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "shield",
                "defense_bonus": 42,
                "true_yuan_bonus": 54,
                "body_movement_bonus": 14,
                "duel_rate_bonus": 6,
                "description": "盾缘似风轮缓缓转动，可在格挡时顺势导开正面灵压。",
                "combat_config": {"passives": [{"name": "回风导压", "kind": "guard", "chance": 28, "defense_ratio_percent": 22, "duration": 1, "text": "云阙回风盾卷起一圈回风，把迎面冲力生生偏转了出去。"}]},
                "materials": [("玄苍龟晶", 1), ("云阙天蚕丝", 1), ("太清星尘", 1), ("造化玉露", 1)],
                "success": 34,
                "broadcast": True,
                "min_realm_stage": "炼虚",
                "min_realm_layer": 6,
            },
        ],
    },
    {
        "name": "混元御极套",
        "description": "先天至宝级镇界套装，集断界、护道、踏虚于一体，整体偏全能生存。",
        "required_count": 4,
        "attack_bonus": 32,
        "defense_bonus": 34,
        "body_movement_bonus": 18,
        "breakthrough_bonus": 16,
        "items": [
            {
                "name": "混元断界戈",
                "rarity": "先天至宝",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 74,
                "defense_bonus": 24,
                "comprehension_bonus": 16,
                "duel_rate_bonus": 10,
                "description": "戈锋仿佛贴着界壁打磨而成，一挥就像要把前方天地直接切开。",
                "combat_config": {"passives": [{"name": "断界裁痕", "kind": "armor_break", "chance": 36, "defense_ratio_percent": 30, "duration": 2, "text": "混元断界戈横扫而过，对手护体像被界壁裂缝生生扯开。"}]},
                "materials": [("大罗神铁", 1), ("混元界壳", 1), ("太初紫气晶", 1), ("元始真砂", 1)],
                "success": 24,
                "broadcast": True,
                "min_realm_stage": "大乘",
                "min_realm_layer": 6,
            },
            {
                "name": "混元玄界盾",
                "rarity": "先天至宝",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "shield",
                "defense_bonus": 62,
                "qi_blood_bonus": 210,
                "true_yuan_bonus": 48,
                "description": "盾心宛如一枚完整界壳，护体时像将自己暂时藏进另一重天地。",
                "combat_config": {"passives": [{"name": "玄界垂幕", "kind": "shield", "chance": 32, "flat_shield": 60, "ratio_percent": 30, "text": "混元玄界盾放出厚重界幕，把整个人连同气机都一并收拢进去。"}]},
                "materials": [("混元界壳", 1), ("玄黄母气", 1), ("鸿蒙天髓", 1), ("劫寂玄纱", 1)],
                "success": 22,
                "broadcast": True,
                "min_realm_stage": "大乘",
                "min_realm_layer": 7,
            },
            {
                "name": "混元无漏甲",
                "rarity": "先天至宝",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "chest",
                "defense_bonus": 58,
                "qi_blood_bonus": 198,
                "breakthrough_bonus": 10,
                "description": "甲胄浑然一体，气机流转近乎无漏，越是死战越显稳固。",
                "combat_config": {"passives": [{"name": "无漏守中", "kind": "guard", "chance": 30, "defense_ratio_percent": 30, "duration": 1, "text": "混元无漏甲收束周身气机，正面轰击竟被生生磨去大半。"}]},
                "materials": [("劫寂玄纱", 1), ("玄黄母气", 1), ("太始龙骨", 1), ("周天星核", 1)],
                "success": 21,
                "broadcast": True,
                "min_realm_stage": "大乘",
                "min_realm_layer": 7,
            },
            {
                "name": "混元踏虚履",
                "rarity": "先天至宝",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "defense_bonus": 24,
                "body_movement_bonus": 42,
                "duel_rate_bonus": 10,
                "description": "履底留着太易风痕，一步踏出，落点常比心念更早到达。",
                "combat_config": {"passives": [{"name": "踏虚遁迹", "kind": "dodge", "chance": 36, "dodge_bonus": 36, "duration": 1, "text": "混元踏虚履在原地留下一道淡淡风痕，真身已借虚空滑开。"}]},
                "materials": [("太易风痕晶", 1), ("无相天露", 1), ("周天星核", 1), ("劫寂玄纱", 1)],
                "success": 23,
                "broadcast": True,
                "min_realm_stage": "大乘",
                "min_realm_layer": 7,
            },
        ],
    },
    {
        "name": "云岚初行套",
        "description": "适合前期成型的六部位轻装，补足武器、头冠、衣服、鞋、盾与饰品的基础配置。",
        "required_count": 3,
        "attack_bonus": 8,
        "defense_bonus": 8,
        "body_movement_bonus": 8,
        "items": [
            {
                "name": "云岚轻灵剑",
                "rarity": "凡品",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 14,
                "body_movement_bonus": 3,
                "description": "剑身轻薄，适合初入仙途者熟悉御器节奏。",
                "combat_config": {"passives": [{"name": "轻灵斩", "kind": "extra_damage", "chance": 20, "flat_damage": 10, "ratio_percent": 12, "text": "云岚轻灵剑顺势一挑，剑光贴着灵压掠过。"}]},
                "materials": [("寒铁矿", 2), ("云纹丝", 1)],
                "success": 72,
            },
            {
                "name": "云岚束发冠",
                "rarity": "凡品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "helmet",
                "comprehension_bonus": 3,
                "divine_sense_bonus": 3,
                "description": "冠中嵌一缕清风玉纹，可令灵台稍定。",
                "materials": [("灵木芯", 2), ("凝露花", 1)],
                "success": 74,
            },
            {
                "name": "云岚护身衣",
                "rarity": "凡品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "clothes",
                "defense_bonus": 10,
                "qi_blood_bonus": 24,
                "description": "衣纹朴素，却能分散入门斗法中的余劲。",
                "combat_config": {"passives": [{"name": "云纹护体", "kind": "shield", "chance": 18, "flat_shield": 14, "ratio_percent": 10, "text": "云岚护身衣浮起细纹，卸去一截冲击。"}]},
                "materials": [("云纹丝", 2), ("归元草", 1)],
                "success": 72,
            },
            {
                "name": "云岚踏风鞋",
                "rarity": "凡品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "body_movement_bonus": 10,
                "defense_bonus": 2,
                "description": "鞋底缝有轻风纹，闪转腾挪更稳。",
                "materials": [("云纹丝", 2), ("雷击木", 1)],
                "success": 72,
            },
            {
                "name": "云岚小圆盾",
                "rarity": "凡品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "shield",
                "defense_bonus": 12,
                "qi_blood_bonus": 18,
                "description": "盾面不大，胜在顺手，能护住破绽。",
                "combat_config": {"passives": [{"name": "圆盾格挡", "kind": "guard", "chance": 18, "defense_ratio_percent": 14, "duration": 1, "text": "云岚小圆盾横在身前，硬接一记余势。"}]},
                "materials": [("玄龟甲片", 1), ("灵木芯", 1)],
                "success": 70,
            },
            {
                "name": "云岚清心坠",
                "rarity": "凡品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "accessory",
                "true_yuan_bonus": 22,
                "fortune_bonus": 2,
                "cultivation_bonus": 3,
                "description": "坠子中存一滴清露，可稳住初学者的真元流转。",
                "materials": [("凝露花", 1), ("归元草", 2)],
                "success": 72,
            },
        ],
    },
    {
        "name": "赤炉炼战套",
        "description": "炼器修士偏爱的中阶六部位战装，攻守平衡，适合日常斗法与炼制成长。",
        "required_count": 4,
        "attack_bonus": 18,
        "defense_bonus": 14,
        "cultivation_bonus": 8,
        "items": [
            {
                "name": "赤炉断金斧",
                "rarity": "中品",
                "artifact_type": "battle",
                "artifact_role": "battle",
                "equip_slot": "weapon",
                "attack_bonus": 34,
                "duel_rate_bonus": 4,
                "description": "斧刃带赤炉余温，重劈时能震散护体灵光。",
                "combat_config": {"passives": [{"name": "断金重劈", "kind": "armor_break", "chance": 26, "defense_ratio_percent": 16, "duration": 2, "text": "赤炉断金斧轰然劈下，护体灵光被砸出裂纹。"}]},
                "materials": [("赤霄铜髓", 2), ("断雷砂", 1), ("星河砂", 1)],
                "success": 56,
            },
            {
                "name": "赤炉护额冠",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "helmet",
                "comprehension_bonus": 8,
                "divine_sense_bonus": 8,
                "description": "护额温润，可让炼火躁意不扰灵台。",
                "materials": [("金乌羽粉", 1), ("霜华露珠", 2), ("云母银丝", 1)],
                "success": 58,
            },
            {
                "name": "赤炉百炼衣",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "clothes",
                "defense_bonus": 24,
                "qi_blood_bonus": 62,
                "description": "衣内嵌入百炼铜丝，可承受炼火反震。",
                "combat_config": {"passives": [{"name": "百炼护劲", "kind": "shield", "chance": 24, "flat_shield": 24, "ratio_percent": 16, "text": "赤炉百炼衣火纹一亮，护住经脉要害。"}]},
                "materials": [("赤霄铜髓", 2), ("云母银丝", 2), ("厚土晶", 1)],
                "success": 55,
            },
            {
                "name": "赤炉行火鞋",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "movement",
                "equip_slot": "boots",
                "body_movement_bonus": 22,
                "duel_rate_bonus": 4,
                "description": "鞋底火纹一闪，可借地火反推身形。",
                "combat_config": {"passives": [{"name": "行火错步", "kind": "dodge", "chance": 24, "dodge_bonus": 20, "duration": 1, "text": "赤炉行火鞋踏出火星，人影已偏开一线。"}]},
                "materials": [("离火絮", 2), ("金乌羽粉", 1), ("云母银丝", 1)],
                "success": 56,
            },
            {
                "name": "赤炉熔铁盾",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "guardian",
                "equip_slot": "shield",
                "defense_bonus": 28,
                "qi_blood_bonus": 40,
                "description": "盾缘常有暗红余烬，攻来之力会被层层熔解。",
                "combat_config": {"passives": [{"name": "熔铁回护", "kind": "guard", "chance": 26, "defense_ratio_percent": 20, "duration": 1, "text": "赤炉熔铁盾沉声挡下攻势，火纹顺势反卷。"}]},
                "materials": [("玄龟骨晶", 2), ("赤霄铜髓", 1), ("断雷砂", 1)],
                "success": 54,
            },
            {
                "name": "赤炉温玉佩",
                "rarity": "中品",
                "artifact_type": "support",
                "artifact_role": "support",
                "equip_slot": "accessory",
                "true_yuan_bonus": 48,
                "cultivation_bonus": 8,
                "fortune_bonus": 4,
                "description": "温玉藏火，可在修炼时缓缓调匀真元。",
                "materials": [("暖玉粉", 2), ("灵雾草心", 1), ("霜华露珠", 1)],
                "success": 57,
            },
        ],
    },
]

PILL_BLUEPRINTS = [
    {"name": "养元凝魄丹", "rarity": "下品", "pill_type": "cultivation", "effect_value": 160, "poison_delta": 2, "description": "丹成时灵气内敛，入口化作涓涓细流温养魂魄。专治炼气末期灵气涣散之症，服后根基愈发稳固，冲关更有成算。", "materials": [("青霜铁", 1), ("寒水露", 2), ("暖玉粉", 1)], "success": 76},
    {"name": "踏云轻身丹", "rarity": "中品", "pill_type": "body_movement", "effect_value": 18, "poison_delta": 3, "description": "丹体轻盈如云絮，入口即有一股御风之气贯穿四肢。服后身轻如燕、足底生云，纵是悬崖峭壁亦能如履平川。", "materials": [("云母银丝", 1), ("霜华露珠", 2), ("灵雾草心", 1)], "success": 68},
    {"name": "玄火锻骨丹", "rarity": "中品", "pill_type": "bone", "effect_value": 16, "poison_delta": 4, "description": "丹成时隐有火焰纹路流转，药性刚猛如熔岩炼狱。服后骨髓如被烈火淬炼，骨骼愈发坚硬如金铁，寻常攻击难伤分毫。", "materials": [("赤霄铜髓", 2), ("金乌羽粉", 1), ("断雷砂", 1)], "success": 62},
    {"name": "天机明神丹", "rarity": "上品", "pill_type": "divine_sense", "effect_value": 22, "poison_delta": 4, "description": "丹成之际似有天机流转、神思涌动。入口化为一缕清凉之气直入识海深处，令神识瞬间澄澈万千，感知天地万物之能骤增。", "materials": [("幻月晶核", 1), ("玄冰胆", 1), ("天游莲芯", 1)], "success": 54},
    {"name": "九霄御气丹", "rarity": "极品", "pill_type": "true_yuan", "effect_value": 88, "poison_delta": 5, "description": "丹成时似有九天真气萦绕，入口化为一股磅礴灵气灌入丹田。专为持久斗法所备，服后真元如九霄长风绵延不绝，取之不尽用之不竭。", "materials": [("九霄凤羽", 1), ("太华灵液", 1), ("璇玑星砂", 1)], "success": 46},
    {"name": "福缘问心丹", "rarity": "极品", "pill_type": "fortune", "effect_value": 12, "poison_delta": 5, "description": "丹中似有命运之线隐现，玄妙至极难以言表。服后冥冥中自有天佑，奇珍异宝不请自来，绝境之中亦能逢凶化吉、遇难呈祥。", "materials": [("无垢净沙", 1), ("幽冥墨玉", 1), ("太阴寒髓", 1)], "success": 45},
    {"name": "长生回命丹", "rarity": "仙品", "pill_type": "qi_blood", "effect_value": 168, "poison_delta": 6, "description": "乃仙人手制，丹成时满室异香、气血翻涌。入口可同时点燃命火、激活气血本源，将生机与活力同时催发至巅峰，生死关头亦能逆转乾坤。", "materials": [("长生灵藤心", 1), ("造化玉露", 1), ("九转金液", 1)], "success": 38},
    {"name": "混元开天丹", "rarity": "先天至宝", "pill_type": "foundation", "effect_value": 22, "poison_delta": 8, "description": "传说为混沌初开时所炼之丹，丹成时天降异象、地涌金莲。入口可沟通天地初开之混元之气，对突破大境界有着不可思议之增幅，令修士脱胎换骨、返璞归真。", "materials": [("太初紫气晶", 1), ("玄黄母气", 1), ("无相天露", 1)], "success": 24},
]

TALISMAN_BLUEPRINTS = [
    {"name": "御风符", "rarity": "下品", "attack_bonus": 8, "body_movement_bonus": 10, "duel_rate_bonus": 2, "description": "以风鹤羽为引、寒水露调和，符成时有风卷残云之象。引动后身轻如羽、进退自如，令敌难以捕捉轨迹。", "combat_config": {"skills": [{"name": "风行一瞬", "kind": "dodge", "chance": 30, "dodge_bonus": 16, "duration": 1, "text": "御风符引动瞬间，一阵清风托起全身，身形如落叶般随风飘舞，在电光火石间已移至敌侧。"}]}, "materials": [("风鹤羽", 2), ("寒水露", 1), ("离火絮", 1)], "success": 74},
    {"name": "护心符", "rarity": "中品", "defense_bonus": 14, "true_yuan_bonus": 18, "duel_rate_bonus": 2, "description": "取玄龟骨晶配合沧浪冰魄绘制，符成时似有海浪拍岸之声。引动后可稳固心脉、凝聚灵罩，抵挡一切外邪入侵。", "combat_config": {"skills": [{"name": "护心灵罩", "kind": "shield", "chance": 34, "flat_shield": 18, "ratio_percent": 16, "text": "护心符化作淡蓝色灵罩贴合胸口，如海浪般将周身牢牢包裹，将迎面而来的攻势尽数卸去。"}]}, "materials": [("玄龟骨晶", 1), ("沧浪冰魄", 1), ("太乙木心", 1)], "success": 66},
    {"name": "镇岳符", "rarity": "上品", "defense_bonus": 20, "qi_blood_bonus": 32, "duel_rate_bonus": 3, "description": "以地脉玉髓为墨、龙鳞铁片为基，符成时隐有山岳镇压之势。引动后可化出巍峨灵壁，任凭敌人攻势如潮亦岿然不动。", "combat_config": {"skills": [{"name": "镇岳符壁", "kind": "guard", "chance": 30, "defense_ratio_percent": 22, "duration": 1, "text": "镇岳符引动瞬间，一座厚重如山的灵壁拔地而起，巍峨崔嵬似能镇岳压顶，将一切冲击尽数挡下。"}]}, "materials": [("地脉玉髓", 1), ("龙鳞铁片", 1), ("太虚陨铁", 1)], "success": 56},
    {"name": "摄魂符", "rarity": "极品", "attack_bonus": 22, "divine_sense_bonus": 22, "duel_rate_bonus": 4, "description": "取璇玑星砂配合幽冥墨玉炼就，符成时幽光闪烁如鬼火飘忽。专攻神魂破绽，可令对手灵台失守、神魂震荡。", "combat_config": {"skills": [{"name": "摄魂钉", "kind": "armor_break", "chance": 32, "defense_ratio_percent": 18, "duration": 2, "text": "摄魂符幽光一闪，神识化作森寒钉芒穿透虚空，直接刺入对手灵台深处，令其神魂剧痛难当。"}]}, "materials": [("璇玑星砂", 1), ("幽冥墨玉", 1), ("玄天乌金", 1)], "success": 44},
    {"name": "裂空符", "rarity": "仙品", "attack_bonus": 28, "body_movement_bonus": 24, "duel_rate_bonus": 6, "description": "以苍穹雷髓配合仙凰真羽绘就，符成时似有凤鸣九天、裂帛之音。引动时可短暂撕裂空间，令身形如鬼魅般穿梭于战场之间。", "combat_config": {"skills": [{"name": "裂空步", "kind": "extra_damage", "chance": 34, "flat_damage": 26, "ratio_percent": 24, "text": "裂空符燃成一道漆黑裂隙，下一瞬已从对手身后的虚空中闪出，攻势如影随形般贴脸而至。"}]}, "materials": [("苍穹雷髓", 1), ("太清星尘", 1), ("仙凰真羽", 1)], "success": 34},
    {"name": "化毒符", "rarity": "仙品", "defense_bonus": 18, "fortune_bonus": 10, "duel_rate_bonus": 4, "description": "以造化玉露配合长生灵藤心炼就，符成时散发淡淡青芒。专克天下万毒，可将体内浊毒尽数化解，令修士百毒不侵。", "combat_config": {"skills": [{"name": "清晦灵洗", "kind": "heal", "chance": 24, "flat_heal": 30, "ratio_percent": 20, "text": "化毒符散出柔和青芒，如春风化雨般涤荡全身，浊毒在青芒中逐渐消融，经脉重归清明。"}]}, "materials": [("造化玉露", 1), ("长生灵藤心", 1), ("玄冥冰魄", 1)], "success": 33},
    {"name": "玄穹镇劫符", "rarity": "仙品", "defense_bonus": 20, "qi_blood_bonus": 88, "duel_rate_bonus": 4, "description": "以玄苍龟晶、混元息壤与太虚雷纹钢绘就，符成时会自然浮现一圈镇潮古纹。引动之后护体如城，最擅顶住正面重击。", "combat_config": {"skills": [{"name": "镇劫灵幕", "kind": "shield", "chance": 30, "flat_shield": 34, "ratio_percent": 22, "text": "玄穹镇劫符沉沉一震，深青灵幕像堤坝一样拦在身前。"}]}, "materials": [("玄苍龟晶", 1), ("混元息壤", 1), ("太虚雷纹钢", 1)], "success": 32},
    {"name": "云阙裂界符", "rarity": "仙品", "attack_bonus": 26, "body_movement_bonus": 22, "duel_rate_bonus": 6, "description": "以云阙天蚕丝、苍穹雷髓与赤霄凤血并绘，符面隐约可见一道细长裂纹。引动时身法与斩势会同时被拔高。", "combat_config": {"skills": [{"name": "裂界追光", "kind": "extra_damage", "chance": 32, "flat_damage": 24, "ratio_percent": 22, "text": "云阙裂界符化出一道极细裂痕，攻势沿着那道裂痕瞬间追到面前。"}]}, "materials": [("云阙天蚕丝", 1), ("苍穹雷髓", 1), ("赤霄凤血", 1)], "success": 31},
    {"name": "混元定界符", "rarity": "先天至宝", "defense_bonus": 24, "true_yuan_bonus": 60, "duel_rate_bonus": 6, "description": "以混元界壳、劫寂玄纱与玄黄母气为引绘成，一经催动便如将周身临时固定在另一重界面。", "combat_config": {"skills": [{"name": "定界镇压", "kind": "guard", "chance": 34, "defense_ratio_percent": 28, "duration": 1, "text": "混元定界符压下一重无形界壁，正面冲击像撞在了另一方天地上。"}]}, "materials": [("混元界壳", 1), ("劫寂玄纱", 1), ("玄黄母气", 1)], "success": 20},
    {"name": "太易遁空符", "rarity": "先天至宝", "body_movement_bonus": 34, "divine_sense_bonus": 20, "duel_rate_bonus": 8, "description": "以太易风痕晶、无相天露与周天星核炼成，符成时像有一缕风已经先一步消失在原地。", "combat_config": {"skills": [{"name": "太易空遁", "kind": "dodge", "chance": 36, "dodge_bonus": 36, "duration": 1, "text": "太易遁空符刚一亮起，真身便像顺着风痕提前遁入了空隙之中。"}]}, "materials": [("太易风痕晶", 1), ("无相天露", 1), ("周天星核", 1)], "success": 18},
    {"name": "太初神雷符", "rarity": "先天至宝", "attack_bonus": 36, "divine_sense_bonus": 24, "duel_rate_bonus": 8, "description": "以先天紫气配合大罗神铁绘制，符成时天降异象、雷声滚滚。引动可召唤太初神雷，令天地失色、鬼神辟易，是为绝杀之术。", "combat_config": {"skills": [{"name": "太初雷殛", "kind": "extra_damage", "chance": 36, "flat_damage": 36, "ratio_percent": 30, "text": "太初神雷符撕裂苍穹，一道蕴含先天之威的雷芒从天而降，雷声震百里，令天地万物尽皆失色。"}]}, "materials": [("太初紫气晶", 1), ("大罗神铁", 1), ("周天星核", 1)], "success": 22},
]

DEFAULT_BOSS_CONFIGS = [
    # ========== 个人Boss ==========
    {
        "name": "噬灵鼠王",
        "boss_type": "personal",
        "realm_stage": "炼气",
        "description": "盘踞于灵脉矿洞深处的鼠妖之王，体型如牛犊般大小，双目赤红如血，浑身毛发坚硬如铁。它以灵脉矿石为食，修行百年已通灵智，可驱使鼠群淹没来犯之敌。",
        "hp": 400,
        "attack_power": 22,
        "defense_power": 12,
        "body_movement": 8,
        "divine_sense": 8,
        "qi_blood": 400,
        "true_yuan": 150,
        "skill_name": "鼠群啮咬",
        "skill_ratio_percent": 24,
        "skill_hit_bonus": 0,
        "passive_name": "铁毛护体",
        "passive_effect_kind": "guard",
        "passive_ratio_percent": 14,
        "passive_chance": 22,
        "loot_pills_json": [{"name": "聚气丹", "chance": 60, "quantity_min": 1, "quantity_max": 2},
                            {"name": "培元丹", "chance": 25, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "灵脉碎晶", "chance": 70, "quantity_min": 1, "quantity_max": 3},
                                {"name": "凡铁锭", "chance": 40, "quantity_min": 1, "quantity_max": 2}],
        "stone_reward_min": 30,
        "stone_reward_max": 80,
        "cultivation_reward": 30,
        "daily_attempt_limit": 5,
        "ticket_cost_stone": 30,
        "flavor_text": "鼠王临死前发出凄厉尖啸，千万鼠群随之四散溃逃。",
        "sort_order": 1,
    },
    {
        "name": "黑水玄蛇",
        "boss_type": "personal",
        "realm_stage": "筑基",
        "description": "潜伏在黑水潭底千年的玄鳞巨蛇，身长十丈有余，鳞甲黝黑发亮似玄铁铸成。口中喷吐的毒雾可销金蚀骨，寻常修士沾之即亡。",
        "hp": 800,
        "attack_power": 38,
        "defense_power": 22,
        "body_movement": 14,
        "divine_sense": 14,
        "qi_blood": 800,
        "true_yuan": 300,
        "skill_name": "毒雾噬体",
        "skill_ratio_percent": 26,
        "skill_hit_bonus": 4,
        "passive_name": "玄鳞甲",
        "passive_effect_kind": "guard",
        "passive_ratio_percent": 16,
        "passive_chance": 24,
        "loot_pills_json": [{"name": "培元丹", "chance": 55, "quantity_min": 1, "quantity_max": 2},
                            {"name": "筑基丹", "chance": 20, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "玄蛇毒囊", "chance": 75, "quantity_min": 1, "quantity_max": 2},
                                {"name": "黑水玄鳞", "chance": 50, "quantity_min": 1, "quantity_max": 2}],
        "stone_reward_min": 60,
        "stone_reward_max": 150,
        "cultivation_reward": 60,
        "daily_attempt_limit": 4,
        "ticket_cost_stone": 60,
        "flavor_text": "玄蛇轰然倒下，黑水潭掀起滔天巨浪，千年毒雾缓缓散去。",
        "sort_order": 2,
    },
    {
        "name": "九幽魔蛛",
        "boss_type": "personal",
        "realm_stage": "金丹",
        "description": "栖息于九幽秘境深处的巨型魔蛛，八足展开似一座小山，背上生有诡异的人面花纹。蛛丝坚韧胜似法宝，利爪可撕碎护体灵光，更擅以幻术扰乱神魂。",
        "hp": 1500,
        "attack_power": 58,
        "defense_power": 35,
        "body_movement": 22,
        "divine_sense": 22,
        "qi_blood": 1500,
        "true_yuan": 500,
        "skill_name": "魔蛛噬魂",
        "skill_ratio_percent": 30,
        "skill_hit_bonus": 6,
        "passive_name": "蛛丝陷阱",
        "passive_effect_kind": "armor_break",
        "passive_ratio_percent": 16,
        "passive_chance": 26,
        "loot_pills_json": [{"name": "培元丹", "chance": 50, "quantity_min": 1, "quantity_max": 3},
                            {"name": "金丹", "chance": 15, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "九幽蛛丝", "chance": 70, "quantity_min": 1, "quantity_max": 3},
                                {"name": "人面蛛壳", "chance": 45, "quantity_min": 1, "quantity_max": 1}],
        "loot_artifacts_json": [{"name": "玄铁重剑", "chance": 15, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 120,
        "stone_reward_max": 280,
        "cultivation_reward": 120,
        "daily_attempt_limit": 3,
        "ticket_cost_stone": 100,
        "flavor_text": "魔蛛八足抽搐、人面花纹渐渐褪去，九幽深处传来凄厉的回声。",
        "sort_order": 3,
    },
    {
        "name": "焚天妖鹏",
        "boss_type": "personal",
        "realm_stage": "元婴",
        "description": "翱翔于九天罡风层中的远古妖鹏，双翼展开遮天蔽日，浑身燃着不灭的妖火。翎羽如利刃般锋利，振翅可掀起烈焰风暴，所过之处化为焦土。",
        "hp": 2800,
        "attack_power": 85,
        "defense_power": 52,
        "body_movement": 32,
        "divine_sense": 32,
        "qi_blood": 2800,
        "true_yuan": 800,
        "skill_name": "焚天妖火",
        "skill_ratio_percent": 32,
        "skill_hit_bonus": 10,
        "passive_name": "涅槃余烬",
        "passive_effect_kind": "heal",
        "passive_ratio_percent": 18,
        "passive_chance": 20,
        "loot_pills_json": [{"name": "培元丹", "chance": 45, "quantity_min": 2, "quantity_max": 4},
                            {"name": "元婴丹", "chance": 18, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "妖鹏火羽", "chance": 70, "quantity_min": 1, "quantity_max": 3},
                                {"name": "焚天妖火种", "chance": 35, "quantity_min": 1, "quantity_max": 1}],
        "loot_artifacts_json": [{"name": "青霜剑", "chance": 15, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 200,
        "stone_reward_max": 500,
        "cultivation_reward": 200,
        "daily_attempt_limit": 3,
        "ticket_cost_stone": 160,
        "flavor_text": "妖鹏发出最后一声哀鸣，从九天坠落，漫天妖火渐渐熄灭。",
        "sort_order": 4,
    },
    {
        "name": "万载玄龟",
        "boss_type": "personal",
        "realm_stage": "化神",
        "description": "沉睡于北海冰渊万载的上古玄龟，背甲如山岳般巍峨，其上铭刻着先天八卦纹路。行动虽缓，但防御力冠绝同阶，口中喷吐的玄冥寒气可冻结万物。",
        "hp": 5000,
        "attack_power": 120,
        "defense_power": 80,
        "body_movement": 18,
        "divine_sense": 45,
        "qi_blood": 5000,
        "true_yuan": 1200,
        "skill_name": "玄冥吐息",
        "skill_ratio_percent": 34,
        "skill_hit_bonus": 12,
        "passive_name": "八卦龟甲",
        "passive_effect_kind": "guard",
        "passive_ratio_percent": 24,
        "passive_chance": 32,
        "loot_pills_json": [{"name": "培元丹", "chance": 40, "quantity_min": 3, "quantity_max": 5},
                            {"name": "化神丹", "chance": 15, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "玄龟甲片", "chance": 75, "quantity_min": 1, "quantity_max": 3},
                                {"name": "万载冰晶", "chance": 40, "quantity_min": 1, "quantity_max": 2}],
        "loot_artifacts_json": [{"name": "玄冥护甲", "chance": 14, "quantity_min": 1, "quantity_max": 1}],
        "loot_recipes_json": [{"name": "九转还魂丹方", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 350,
        "stone_reward_max": 800,
        "cultivation_reward": 350,
        "daily_attempt_limit": 3,
        "ticket_cost_stone": 250,
        "flavor_text": "玄龟背上的八卦纹路寸寸碎裂，庞大的身躯缓缓沉入冰渊之中。",
        "sort_order": 5,
    },
    {
        "name": "太阴幽狼",
        "boss_type": "personal",
        "realm_stage": "炼虚",
        "description": "游走于阴阳两界缝隙中的太阴狼王，身披月华银毫，双瞳一阴一阳。它无声无息穿行于虚实之间，利爪可撕裂法则，嚎叫能勾魂夺魄。",
        "hp": 8500,
        "attack_power": 170,
        "defense_power": 115,
        "body_movement": 62,
        "divine_sense": 62,
        "qi_blood": 8500,
        "true_yuan": 1800,
        "skill_name": "太阴裂虚",
        "skill_ratio_percent": 36,
        "skill_hit_bonus": 16,
        "passive_name": "虚实穿梭",
        "passive_effect_kind": "dodge",
        "passive_ratio_percent": 20,
        "passive_chance": 28,
        "loot_pills_json": [{"name": "培元丹", "chance": 35, "quantity_min": 3, "quantity_max": 6},
                            {"name": "炼虚丹", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "太阴月华", "chance": 70, "quantity_min": 1, "quantity_max": 3},
                                {"name": "幽狼银毫", "chance": 45, "quantity_min": 1, "quantity_max": 2}],
        "loot_artifacts_json": [{"name": "太阴破虚刃", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "loot_recipes_json": [{"name": "太清玉液丹方", "chance": 10, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 550,
        "stone_reward_max": 1200,
        "cultivation_reward": 550,
        "daily_attempt_limit": 3,
        "ticket_cost_stone": 350,
        "flavor_text": "幽狼的虚影渐渐消散，月光洒落之处只余一缕银毫随风飘逝。",
        "sort_order": 6,
    },
    {
        "name": "九首妖龙",
        "boss_type": "personal",
        "realm_stage": "合体",
        "description": "自上古封魔之地破印而出的九首妖龙，每个头颅各掌一种元素之力——风火雷电冰毒光暗血，九龙齐出毁天灭地。龙威之下，万物俯首。",
        "hp": 14000,
        "attack_power": 240,
        "defense_power": 165,
        "body_movement": 85,
        "divine_sense": 85,
        "qi_blood": 14000,
        "true_yuan": 2600,
        "skill_name": "九龙灭世",
        "skill_ratio_percent": 40,
        "skill_hit_bonus": 20,
        "passive_name": "龙威压迫",
        "passive_effect_kind": "armor_break",
        "passive_ratio_percent": 22,
        "passive_chance": 30,
        "loot_pills_json": [{"name": "培元丹", "chance": 30, "quantity_min": 4, "quantity_max": 8},
                            {"name": "合体丹", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "妖龙逆鳞", "chance": 65, "quantity_min": 1, "quantity_max": 3},
                                {"name": "九龙精血", "chance": 35, "quantity_min": 1, "quantity_max": 2}],
        "loot_artifacts_json": [{"name": "龙魂战甲", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "loot_techniques_json": [{"name": "九龙驭天诀", "chance": 8, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 800,
        "stone_reward_max": 1800,
        "cultivation_reward": 800,
        "daily_attempt_limit": 2,
        "ticket_cost_stone": 500,
        "flavor_text": "九颗龙头逐一爆开，妖龙庞大身躯化为漫天血雨洒落封魔之地。",
        "sort_order": 7,
    },
    {
        "name": "混元天魔",
        "boss_type": "personal",
        "realm_stage": "大乘",
        "description": "域外天魔中的混元级存在，无形无相却又无处不在，唯有神识可捕捉其踪迹。它吞噬修士道心为食，能幻化出对手最深层的恐惧，令大乘修士亦闻之色变。",
        "hp": 22000,
        "attack_power": 330,
        "defense_power": 230,
        "body_movement": 115,
        "divine_sense": 115,
        "qi_blood": 22000,
        "true_yuan": 3600,
        "skill_name": "心魔噬道",
        "skill_ratio_percent": 44,
        "skill_hit_bonus": 24,
        "passive_name": "无形天魔",
        "passive_effect_kind": "dodge",
        "passive_ratio_percent": 24,
        "passive_chance": 32,
        "loot_pills_json": [{"name": "培元丹", "chance": 25, "quantity_min": 5, "quantity_max": 10},
                            {"name": "大乘丹", "chance": 10, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "天魔残魂", "chance": 60, "quantity_min": 1, "quantity_max": 3},
                                {"name": "混元魔晶", "chance": 30, "quantity_min": 1, "quantity_max": 2}],
        "loot_artifacts_json": [{"name": "破魔仙剑", "chance": 10, "quantity_min": 1, "quantity_max": 1}],
        "loot_techniques_json": [{"name": "混元镇魔经", "chance": 8, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 1200,
        "stone_reward_max": 2500,
        "cultivation_reward": 1200,
        "daily_attempt_limit": 2,
        "ticket_cost_stone": 700,
        "flavor_text": "天魔发出刺耳的尖啸，无形身躯寸寸崩解，散为漫天黑雾渐渐消弭。",
        "sort_order": 8,
    },
    # ========== 世界Boss ==========
    {
        "name": "噬日魔鲲",
        "boss_type": "world",
        "realm_stage": "金丹",
        "description": "自北冥深渊苏醒的上古魔鲲，体型之大堪比一座浮岛，张口可吞日月精华。传说其体内自成一方洞天世界，无数修士陨落后遗留的宝物尽在其中。",
        "hp": 20000,
        "attack_power": 65,
        "defense_power": 40,
        "body_movement": 20,
        "divine_sense": 20,
        "qi_blood": 20000,
        "true_yuan": 800,
        "skill_name": "吞天噬日",
        "skill_ratio_percent": 28,
        "skill_hit_bonus": 8,
        "passive_name": "北冥寒气",
        "passive_effect_kind": "guard",
        "passive_ratio_percent": 16,
        "passive_chance": 24,
        "loot_pills_json": [{"name": "聚气丹", "chance": 82, "quantity_min": 1, "quantity_max": 3},
                            {"name": "凝元丹", "chance": 48, "quantity_min": 1, "quantity_max": 2},
                            {"name": "筑基丹", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "寒水露", "chance": 86, "quantity_min": 1, "quantity_max": 3},
                                {"name": "沧浪冰魄", "chance": 58, "quantity_min": 1, "quantity_max": 2},
                                {"name": "星河砂", "chance": 36, "quantity_min": 1, "quantity_max": 2},
                                {"name": "太虚陨铁", "chance": 18, "quantity_min": 1, "quantity_max": 1}],
        "loot_artifacts_json": [{"name": "玄岳镇心佩", "chance": 4, "quantity_min": 1, "quantity_max": 1}],
        "loot_talismans_json": [{"name": "护心符", "chance": 18, "quantity_min": 1, "quantity_max": 1},
                                {"name": "御风符", "chance": 24, "quantity_min": 1, "quantity_max": 2}],
        "loot_recipes_json": [{"name": "玄岳镇海枪炼制图", "chance": 5, "quantity_min": 1, "quantity_max": 1}],
        "loot_techniques_json": [{"name": "玄岳不动经", "chance": 3, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 100,
        "stone_reward_max": 300,
        "cultivation_reward": 150,
        "daily_attempt_limit": 10,
        "ticket_cost_stone": 0,
        "flavor_text": "魔鲲发出震天动地的哀鸣，庞大身躯缓缓沉入北冥深渊，激起万丈狂澜。",
        "sort_order": 100,
    },
    {
        "name": "万劫不朽真魔",
        "boss_type": "world",
        "realm_stage": "化神",
        "description": "渡万劫而不灭的古老真魔，曾以一己之力屠灭数个仙门。他身披不朽魔甲、手持灭世战戟，每一次现身都令天地变色、日月无光。唯有全服修士联手，方有一线生机。",
        "hp": 50000,
        "attack_power": 130,
        "defense_power": 75,
        "body_movement": 50,
        "divine_sense": 50,
        "qi_blood": 50000,
        "true_yuan": 2000,
        "skill_name": "万劫魔威",
        "skill_ratio_percent": 38,
        "skill_hit_bonus": 16,
        "passive_name": "不朽魔甲",
        "passive_effect_kind": "guard",
        "passive_ratio_percent": 20,
        "passive_chance": 30,
        "loot_pills_json": [{"name": "九霄御气丹", "chance": 58, "quantity_min": 1, "quantity_max": 2},
                            {"name": "长生回命丹", "chance": 32, "quantity_min": 1, "quantity_max": 1},
                            {"name": "福缘问心丹", "chance": 10, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "玄天乌金", "chance": 76, "quantity_min": 1, "quantity_max": 3},
                                {"name": "幽冥墨玉", "chance": 54, "quantity_min": 1, "quantity_max": 2},
                                {"name": "仙凰真羽", "chance": 28, "quantity_min": 1, "quantity_max": 1},
                                {"name": "太初紫气晶", "chance": 7, "quantity_min": 1, "quantity_max": 1}],
        "loot_artifacts_json": [{"name": "夜魇夺命刃", "chance": 5, "quantity_min": 1, "quantity_max": 1},
                                {"name": "紫宸天刀", "chance": 2, "quantity_min": 1, "quantity_max": 1}],
        "loot_talismans_json": [{"name": "摄魂符", "chance": 20, "quantity_min": 1, "quantity_max": 1},
                                {"name": "裂空符", "chance": 8, "quantity_min": 1, "quantity_max": 1},
                                {"name": "太初神雷符", "chance": 2, "quantity_min": 1, "quantity_max": 1}],
        "loot_recipes_json": [{"name": "紫宸天刀炼制图", "chance": 4, "quantity_min": 1, "quantity_max": 1},
                              {"name": "太初神雷符符谱", "chance": 2, "quantity_min": 1, "quantity_max": 1}],
        "loot_techniques_json": [{"name": "星罗潮生诀", "chance": 5, "quantity_min": 1, "quantity_max": 1},
                                 {"name": "紫宸裂空经", "chance": 2, "quantity_min": 1, "quantity_max": 1}],
        "stone_reward_min": 250,
        "stone_reward_max": 600,
        "cultivation_reward": 300,
        "daily_attempt_limit": 10,
        "ticket_cost_stone": 0,
        "flavor_text": "真魔发出不甘的怒吼，不朽魔甲寸寸崩碎，万年魔威终告消散。天地间回荡着他最后的诅咒。",
        "sort_order": 101,
    },
]

LEGACY_WORLD_BOSS_LOOT_CONFIGS = {
    "噬日魔鲲": {
        "name": "噬日魔鲲",
        "loot_pills_json": [{"name": "培元丹", "chance": 60, "quantity_min": 1, "quantity_max": 3},
                            {"name": "金丹", "chance": 20, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "魔鲲鳞甲", "chance": 75, "quantity_min": 1, "quantity_max": 3},
                                {"name": "北冥冰晶", "chance": 50, "quantity_min": 1, "quantity_max": 2}],
        "loot_artifacts_json": [{"name": "鲲骨法杖", "chance": 15, "quantity_min": 1, "quantity_max": 1}],
    },
    "万劫不朽真魔": {
        "name": "万劫不朽真魔",
        "loot_pills_json": [{"name": "培元丹", "chance": 50, "quantity_min": 2, "quantity_max": 5},
                            {"name": "化神丹", "chance": 18, "quantity_min": 1, "quantity_max": 1}],
        "loot_materials_json": [{"name": "不朽魔晶", "chance": 70, "quantity_min": 1, "quantity_max": 3},
                                {"name": "真魔残甲", "chance": 40, "quantity_min": 1, "quantity_max": 2}],
        "loot_artifacts_json": [{"name": "灭世战戟", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
        "loot_recipes_json": [{"name": "九转还魂丹方", "chance": 12, "quantity_min": 1, "quantity_max": 1}],
    },
}

TECHNIQUE_BLUEPRINTS = [
    {"name": "青霄御风诀", "rarity": "下品", "technique_type": "movement", "description": "正道轻灵身法，讲究剑步合一。", "body_movement_bonus": 16, "duel_rate_bonus": 4, "combat_config": {"skills": [{"name": "御风借势", "kind": "dodge", "chance": 24, "dodge_bonus": 18, "duration": 1, "cost_true_yuan": 10, "text": "青霄御风诀顺势带起一阵清风，整个人贴着灵压边缘滑开。"}]}, "min_realm_stage": "炼气", "min_realm_layer": 7},
    {"name": "玄岳不动经", "rarity": "中品", "technique_type": "defense", "description": "以地脉沉息淬体，最适合硬接重手。", "defense_bonus": 18, "qi_blood_bonus": 52, "breakthrough_bonus": 4, "combat_config": {"skills": [{"name": "不动如岳", "kind": "guard", "chance": 28, "defense_ratio_percent": 24, "duration": 1, "cost_true_yuan": 14, "text": "玄岳不动经一沉，周身气机瞬间稳如山岳。"}]}, "min_realm_stage": "筑基", "min_realm_layer": 2},
    {"name": "夜魇夺魂录", "rarity": "上品", "technique_type": "attack", "description": "邪道追魂秘卷，强调神识压迫与破甲斩杀。", "attack_bonus": 20, "divine_sense_bonus": 14, "duel_rate_bonus": 6, "combat_config": {"skills": [{"name": "夺魂追斩", "kind": "armor_break", "chance": 30, "defense_ratio_percent": 18, "duration": 2, "cost_true_yuan": 18, "text": "夜魇夺魂录牵出一缕阴影，顺着护体缝隙猛然钻入。"}]}, "min_realm_stage": "结丹", "min_realm_layer": 1},
    {"name": "星河归元章", "rarity": "极品", "technique_type": "cultivation", "description": "以周天星河温养经脉，久修者真元最厚。", "comprehension_bonus": 12, "true_yuan_bonus": 68, "cultivation_bonus": 16, "breakthrough_bonus": 8, "combat_config": {"passives": [{"name": "归元长潮", "kind": "heal", "chance": 18, "flat_heal": 24, "ratio_percent": 18, "text": "星河归元章缓缓运转，真元与气血像潮水一样回涨。"}]}, "min_realm_stage": "元婴", "min_realm_layer": 2},
    {"name": "紫宸裂空经", "rarity": "仙品", "technique_type": "combat", "description": "天阙遗经，擅裂空突进与高压连斩。", "attack_bonus": 26, "body_movement_bonus": 22, "duel_rate_bonus": 8, "combat_config": {"skills": [{"name": "裂空天步", "kind": "extra_damage", "chance": 32, "flat_damage": 28, "ratio_percent": 26, "cost_true_yuan": 24, "text": "紫宸裂空经踏出一记短促破空步，下一瞬攻势已贴脸而来。"}]}, "min_realm_stage": "化神", "min_realm_layer": 2},
    {"name": "玄穹镇劫典", "rarity": "仙品", "technique_type": "defense", "description": "以镇海、卸力和稳身为核心的重守秘典，越是硬吃正面越能体现价值。", "defense_bonus": 24, "qi_blood_bonus": 96, "true_yuan_bonus": 40, "breakthrough_bonus": 6, "combat_config": {"skills": [{"name": "镇劫沉壁", "kind": "guard", "chance": 30, "defense_ratio_percent": 26, "duration": 1, "cost_true_yuan": 22, "text": "玄穹镇劫典一沉，周身气机像铸成了一整面厚重潮壁。"}]}, "min_realm_stage": "炼虚", "min_realm_layer": 2},
    {"name": "云阙巡霄诀", "rarity": "仙品", "technique_type": "movement", "description": "专讲裂空借势与高速换位，适合追击、脱战与抢先手。", "attack_bonus": 18, "body_movement_bonus": 28, "duel_rate_bonus": 8, "combat_config": {"skills": [{"name": "巡霄错影", "kind": "dodge", "chance": 32, "dodge_bonus": 28, "duration": 1, "cost_true_yuan": 20, "text": "云阙巡霄诀顺着高空乱流一折，整个人像被抹成了一道掠影。"}]}, "min_realm_stage": "炼虚", "min_realm_layer": 5},
    {"name": "混元御极经", "rarity": "先天至宝", "technique_type": "balanced", "description": "讲究以界护身、以风走位、以本源真元维持全程稳定的先天总纲。", "attack_bonus": 16, "defense_bonus": 24, "true_yuan_bonus": 96, "body_movement_bonus": 18, "breakthrough_bonus": 14, "combat_config": {"passives": [{"name": "御极界衣", "kind": "shield", "chance": 26, "flat_shield": 36, "ratio_percent": 24, "text": "混元御极经将本源真元织成一层薄界衣，硬生生护住了周身要害。"}]}, "min_realm_stage": "大乘", "min_realm_layer": 7},
    {"name": "太初一炁经", "rarity": "先天至宝", "technique_type": "balanced", "description": "先天一炁归于本源，攻守修炼俱强。", "attack_bonus": 18, "defense_bonus": 18, "comprehension_bonus": 18, "true_yuan_bonus": 88, "cultivation_bonus": 20, "breakthrough_bonus": 12, "combat_config": {"passives": [{"name": "一炁周流", "kind": "heal", "chance": 24, "flat_heal": 34, "ratio_percent": 24, "text": "太初一炁经周流全身，一切损耗都被缓缓抚平。"}]}, "min_realm_stage": "须弥", "min_realm_layer": 1},
]

DEFAULT_ARTIFACT_SETS = [
    {key: value for key, value in blueprint.items() if key != "items"}
    for blueprint in ARTIFACT_SET_BLUEPRINTS
]

for quality_label, material_names in SEED_MATERIAL_BLUEPRINTS.items():
    DEFAULT_MATERIALS.extend(
        {
            "name": material_name,
            "quality_level": SEED_QUALITY_LEVELS[quality_label],
            "description": f"{quality_label}灵材【{material_name}】，多见于对应层级秘境，是炼器、炼丹、制符的常备核心素材。",
        }
        for material_name in material_names
    )

for blueprint in ARTIFACT_SET_BLUEPRINTS:
    for item in blueprint["items"]:
        DEFAULT_ARTIFACTS.append(
            {
                "name": item["name"],
                "rarity": item["rarity"],
                "artifact_type": item["artifact_type"],
                "artifact_role": item["artifact_role"],
                "equip_slot": item["equip_slot"],
                "artifact_set_name": blueprint["name"],
                "description": item["description"],
                "attack_bonus": item.get("attack_bonus", 0),
                "defense_bonus": item.get("defense_bonus", 0),
                "bone_bonus": item.get("bone_bonus", 0),
                "comprehension_bonus": item.get("comprehension_bonus", 0),
                "divine_sense_bonus": item.get("divine_sense_bonus", 0),
                "fortune_bonus": item.get("fortune_bonus", 0),
                "qi_blood_bonus": item.get("qi_blood_bonus", 0),
                "true_yuan_bonus": item.get("true_yuan_bonus", 0),
                "body_movement_bonus": item.get("body_movement_bonus", 0),
                "duel_rate_bonus": item.get("duel_rate_bonus", 0),
                "cultivation_bonus": item.get("cultivation_bonus", 0),
                "combat_config": item.get("combat_config", {}),
                "min_realm_stage": item.get("min_realm_stage"),
                "min_realm_layer": item.get("min_realm_layer", 1),
                "enabled": True,
            }
        )
        DEFAULT_RECIPES.append(
            {
                "name": f"{item['name']}炼制图",
                "recipe_kind": "artifact",
                "result_kind": "artifact",
                "result_name": item["name"],
                "result_quantity": 1,
                "base_success_rate": int(item.get("success", 60)),
                "broadcast_on_success": bool(item.get("broadcast", False)),
                "ingredients": [
                    {"material_name": material_name, "quantity": quantity}
                    for material_name, quantity in item.get("materials", [])
                ],
            }
        )

for pill in PILL_BLUEPRINTS:
    DEFAULT_PILLS.append(
        {
            "name": pill["name"],
            "rarity": pill["rarity"],
            "pill_type": pill["pill_type"],
            "description": pill["description"],
            "effect_value": pill["effect_value"],
            "poison_delta": pill["poison_delta"],
            "enabled": True,
        }
    )
    DEFAULT_RECIPES.append(
        {
            "name": f"{pill['name']}丹谱",
            "recipe_kind": "pill",
            "result_kind": "pill",
            "result_name": pill["name"],
            "result_quantity": 1,
            "base_success_rate": int(pill.get("success", 60)),
            "broadcast_on_success": False,
            "ingredients": [
                {"material_name": material_name, "quantity": quantity}
                for material_name, quantity in pill.get("materials", [])
            ],
        }
    )

for talisman in TALISMAN_BLUEPRINTS:
    DEFAULT_TALISMANS.append(
        {
            "name": talisman["name"],
            "rarity": talisman["rarity"],
            "description": talisman["description"],
            "attack_bonus": talisman.get("attack_bonus", 0),
            "defense_bonus": talisman.get("defense_bonus", 0),
            "bone_bonus": talisman.get("bone_bonus", 0),
            "comprehension_bonus": talisman.get("comprehension_bonus", 0),
            "divine_sense_bonus": talisman.get("divine_sense_bonus", 0),
            "fortune_bonus": talisman.get("fortune_bonus", 0),
            "qi_blood_bonus": talisman.get("qi_blood_bonus", 0),
            "true_yuan_bonus": talisman.get("true_yuan_bonus", 0),
            "body_movement_bonus": talisman.get("body_movement_bonus", 0),
            "duel_rate_bonus": talisman.get("duel_rate_bonus", 0),
            "effect_uses": talisman.get("effect_uses", 1),
            "combat_config": talisman.get("combat_config", {}),
            "enabled": True,
        }
    )
    DEFAULT_RECIPES.append(
        {
            "name": f"{talisman['name']}符谱",
            "recipe_kind": "talisman",
            "result_kind": "talisman",
            "result_name": talisman["name"],
            "result_quantity": 2,
            "base_success_rate": int(talisman.get("success", 60)),
            "broadcast_on_success": False,
            "ingredients": [
                {"material_name": material_name, "quantity": quantity}
                for material_name, quantity in talisman.get("materials", [])
            ],
        }
    )

DEFAULT_TECHNIQUES.extend(TECHNIQUE_BLUEPRINTS)
DEFAULT_TITLES.extend(
    [
        {"name": "剑宗真传", "description": "经剑宗长老首肯，已有真传气象。", "color": "#2563eb", "attack_bonus": 6, "body_movement_bonus": 4, "duel_rate_bonus": 3},
        {"name": "药王门生", "description": "对草木药性极熟，气机平和绵长。", "color": "#16a34a", "comprehension_bonus": 6, "true_yuan_bonus": 42, "cultivation_bonus": 4},
        {"name": "天机上客", "description": "常与天机阁论道，心神澄明。", "color": "#0f766e", "comprehension_bonus": 8, "divine_sense_bonus": 8},
        {"name": "魔宫行者", "description": "能在血煞中保持清醒，杀意更利。", "color": "#b91c1c", "attack_bonus": 8, "duel_rate_bonus": 4},
        {"name": "鬼府夜游", "description": "行走于阴影之间，出手总在死角。", "color": "#4c1d95", "body_movement_bonus": 8, "divine_sense_bonus": 4, "fortune_bonus": 4},
        {"name": "万毒不侵", "description": "毒息难侵，体内百脉更显稳固。", "color": "#15803d", "defense_bonus": 6, "qi_blood_bonus": 72, "fortune_bonus": 3},
        {"name": "福缘广施", "description": "灵石散去，善缘却汇成更大的机运，所行之处总有人念你一分好。", "color": "#f59e0b", "fortune_bonus": 6, "true_yuan_bonus": 24, "cultivation_bonus": 4},
        {"name": "百战无双", "description": "历经百战仍能稳住锋芒，越是强敌临身，越能逼出你体内的战意。", "color": "#dc2626", "attack_bonus": 8, "defense_bonus": 6, "qi_blood_bonus": 48, "duel_rate_bonus": 4},
        {"name": "斗战宗师", "description": "斗法节奏已入骨髓，举手投足皆是攻守转换的最佳时机。", "color": "#b91c1c", "attack_bonus": 10, "defense_bonus": 8, "body_movement_bonus": 6, "duel_rate_bonus": 5},
        {"name": "劫运之手", "description": "总能在最乱的局势里截住最值钱的一缕气运，出手悄无声息。", "color": "#7c3aed", "attack_bonus": 6, "divine_sense_bonus": 4, "fortune_bonus": 5, "body_movement_bonus": 8},
        {"name": "义薄云天", "description": "出手相助从不吝啬，久而久之，同道也愿在你最难时回敬一份真心。", "color": "#0284c7", "fortune_bonus": 5, "qi_blood_bonus": 84, "true_yuan_bonus": 30},
        {"name": "传道名宿", "description": "所讲之道已成体系，一言一行都能让后来者少走许多弯路。", "color": "#2563eb", "comprehension_bonus": 8, "true_yuan_bonus": 42, "cultivation_bonus": 6},
        {"name": "桃李宗师", "description": "弟子成材如林，传承由此生根发芽，最终自成一脉气象。", "color": "#7c3aed", "comprehension_bonus": 10, "fortune_bonus": 4, "cultivation_bonus": 8},
        {"name": "万炉归一", "description": "丹火、器火、符火皆在掌中归于一炉，火候再难也能被你稳稳压住。", "color": "#a16207", "comprehension_bonus": 10, "true_yuan_bonus": 54, "cultivation_bonus": 6, "breakthrough_bonus": 2},
        {"name": "天工妙手", "description": "残缺之物到了你手里，总能重新焕出生机，仿佛从未破败过。", "color": "#0f766e", "comprehension_bonus": 8, "divine_sense_bonus": 6, "defense_bonus": 4},
        {"name": "险境还生", "description": "在绝境里活过太多次，肉身与道心都学会了怎样从死地里拽回自己。", "color": "#16a34a", "defense_bonus": 8, "fortune_bonus": 2, "qi_blood_bonus": 96},
        {"name": "洞天寻珍客", "description": "秘境于你不只是险地，更像一座早已熟门熟路的藏宝楼。", "color": "#0891b2", "divine_sense_bonus": 8, "fortune_bonus": 8, "body_movement_bonus": 6},
        {"name": "擂台霸主", "description": "一旦登擂，气势便会压住全场，让后来挑战者先弱三分。", "color": "#ef4444", "attack_bonus": 10, "defense_bonus": 10, "qi_blood_bonus": 60, "duel_rate_bonus": 6},
    ]
)

DEFAULT_SECTS = [
    {
        "name": "太玄剑宗",
        "camp": "orthodox",
        "description": "剑不出鞘则已，出鞘必断因果。太玄宗训：剑心不正者不传，不敢正面迎敌者不收。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "min_bone": 22,
        "min_comprehension": 18,
        "min_willpower": 16,
        "min_combat_power": 0,
        "attack_bonus": 8,
        "body_movement_bonus": 6,
        "duel_rate_bonus": 3,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 0,
        "craft_success_rate": 0,
        "death_penalty_reduce": 0.0,
        "entry_hint": "授《太玄剑经》一卷。入宗试炼：以剑意劈开山门前的试剑石——心不正则剑锋自折。",
        "roles": [
            {"role_key": "leader", "role_name": "剑主", "attack_bonus": 14, "defense_bonus": 8, "duel_rate_bonus": 6, "cultivation_bonus": 5, "monthly_salary": 360, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "镇峰长老", "attack_bonus": 10, "defense_bonus": 7, "duel_rate_bonus": 4, "cultivation_bonus": 4, "monthly_salary": 250, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "剑脉真传", "attack_bonus": 7, "defense_bonus": 5, "duel_rate_bonus": 3, "cultivation_bonus": 3, "monthly_salary": 180, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "巡山执事", "attack_bonus": 5, "defense_bonus": 5, "duel_rate_bonus": 2, "cultivation_bonus": 2, "monthly_salary": 136, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "护山执事", "attack_bonus": 4, "defense_bonus": 4, "duel_rate_bonus": 1, "cultivation_bonus": 2, "monthly_salary": 102, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "内门剑修", "attack_bonus": 3, "defense_bonus": 2, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 64, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "外门弟子", "attack_bonus": 2, "defense_bonus": 2, "duel_rate_bonus": 0, "cultivation_bonus": 1, "monthly_salary": 32, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "药王谷",
        "camp": "orthodox",
        "description": "一丹一世界，百草即苍生。谷中只传稳中求进之道——不求一朝破境惊天下，但求百年丹火暖仙途。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 3,
        "min_comprehension": 20,
        "min_fortune": 16,
        "min_charisma": 12,
        "min_combat_power": 0,
        "defense_bonus": 7,
        "cultivation_bonus": 12,
        "fortune_bonus": 6,
        "pill_poison_resist": 0.25,
        "pill_poison_cap_bonus": 30,
        "farm_growth_speed": 0.20,
        "explore_drop_rate": 0,
        "craft_success_rate": 0,
        "death_penalty_reduce": 0.0,
        "entry_hint": "授《青木长生诀》一卷。入谷考验：以掌心灵息催开枯木上的嫩芽——催不活者请回。",
        "roles": [
            {"role_key": "leader", "role_name": "谷主", "attack_bonus": 5, "defense_bonus": 12, "duel_rate_bonus": 2, "cultivation_bonus": 9, "monthly_salary": 340, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "丹堂长老", "attack_bonus": 4, "defense_bonus": 9, "duel_rate_bonus": 1, "cultivation_bonus": 7, "monthly_salary": 240, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "药炉真传", "attack_bonus": 3, "defense_bonus": 7, "duel_rate_bonus": 1, "cultivation_bonus": 5, "monthly_salary": 176, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "百草执事", "attack_bonus": 2, "defense_bonus": 5, "duel_rate_bonus": 1, "cultivation_bonus": 4, "monthly_salary": 132, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "药圃执事", "attack_bonus": 1, "defense_bonus": 4, "duel_rate_bonus": 0, "cultivation_bonus": 3, "monthly_salary": 98, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "内门药修", "attack_bonus": 1, "defense_bonus": 3, "duel_rate_bonus": 0, "cultivation_bonus": 2, "monthly_salary": 58, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "试药弟子", "attack_bonus": 0, "defense_bonus": 2, "duel_rate_bonus": 0, "cultivation_bonus": 1, "monthly_salary": 30, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "天机阁",
        "camp": "orthodox",
        "description": "观星可知兴替，推演可避死劫。阁中弟子未必最能打，但一定最懂什么时候该做什么事。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "min_comprehension": 26,
        "min_divine_sense": 24,
        "min_fortune": 18,
        "min_combat_power": 0,
        "defense_bonus": 4,
        "cultivation_bonus": 9,
        "fortune_bonus": 8,
        "body_movement_bonus": 4,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 10,
        "craft_success_rate": 4,
        "death_penalty_reduce": 0.0,
        "entry_hint": "授《天机观星术》一卷。入阁资格：读懂门前星壁上第一幅推演图——迷惘者连图上第一颗星都看不见。",
        "roles": [
            {"role_key": "leader", "role_name": "阁主", "attack_bonus": 8, "defense_bonus": 8, "duel_rate_bonus": 6, "cultivation_bonus": 8, "monthly_salary": 380, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "星盘长老", "attack_bonus": 6, "defense_bonus": 6, "duel_rate_bonus": 5, "cultivation_bonus": 6, "monthly_salary": 260, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "天机真传", "attack_bonus": 4, "defense_bonus": 4, "duel_rate_bonus": 4, "cultivation_bonus": 5, "monthly_salary": 190, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "观星执事", "attack_bonus": 3, "defense_bonus": 3, "duel_rate_bonus": 2, "cultivation_bonus": 4, "monthly_salary": 136, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "录图执事", "attack_bonus": 2, "defense_bonus": 2, "duel_rate_bonus": 1, "cultivation_bonus": 3, "monthly_salary": 102, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "内门卜修", "attack_bonus": 1, "defense_bonus": 1, "duel_rate_bonus": 1, "cultivation_bonus": 2, "monthly_salary": 62, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "引星弟子", "attack_bonus": 0, "defense_bonus": 1, "duel_rate_bonus": 0, "cultivation_bonus": 1, "monthly_salary": 32, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "血煞魔宫",
        "camp": "heterodox",
        "description": "煞气即道行，血光即修行。敢在众目睽睽之下踏血而行之人，方能参透魔宫第一页战典。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "min_bone": 22,
        "min_willpower": 18,
        "min_fortune": 12,
        "min_combat_power": 0,
        "attack_bonus": 12,
        "duel_rate_bonus": 5,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 0,
        "craft_success_rate": 0,
        "death_penalty_reduce": 0.20,
        "entry_hint": "授《血煞战典》一卷。入宫考验：从血雾中走到殿前——脚步不停者即为我辈中人。",
        "roles": [
            {"role_key": "leader", "role_name": "宫主", "attack_bonus": 16, "defense_bonus": 7, "duel_rate_bonus": 8, "cultivation_bonus": 4, "monthly_salary": 370, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "血煞长老", "attack_bonus": 12, "defense_bonus": 5, "duel_rate_bonus": 6, "cultivation_bonus": 3, "monthly_salary": 250, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "魔宫真种", "attack_bonus": 9, "defense_bonus": 4, "duel_rate_bonus": 5, "cultivation_bonus": 3, "monthly_salary": 180, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "血卫执事", "attack_bonus": 7, "defense_bonus": 3, "duel_rate_bonus": 3, "cultivation_bonus": 2, "monthly_salary": 132, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "煞堂执事", "attack_bonus": 5, "defense_bonus": 3, "duel_rate_bonus": 2, "cultivation_bonus": 1, "monthly_salary": 100, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "内宫凶徒", "attack_bonus": 4, "defense_bonus": 2, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 62, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "试煞者", "attack_bonus": 2, "defense_bonus": 1, "duel_rate_bonus": 1, "cultivation_bonus": 0, "monthly_salary": 32, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "幽冥鬼府",
        "camp": "heterodox",
        "description": "暗处之刃最为致命。鬼府弟子行走于阴阳之间，看不见的敌人比看得见的可怕百倍。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 6,
        "min_divine_sense": 22,
        "min_fortune": 20,
        "min_body_movement": 20,
        "min_combat_power": 0,
        "body_movement_bonus": 10,
        "duel_rate_bonus": 5,
        "fortune_bonus": 4,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 6,
        "craft_success_rate": 0,
        "death_penalty_reduce": 0.15,
        "entry_hint": "授《幽冥夜行录》一卷。入府资格：能在无月之夜看出自己身后多了几道影子——看不透之人连府门都摸不到。",
        "roles": [
            {"role_key": "leader", "role_name": "府君", "attack_bonus": 13, "defense_bonus": 8, "duel_rate_bonus": 8, "cultivation_bonus": 5, "monthly_salary": 360, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "夜巡长老", "attack_bonus": 10, "defense_bonus": 6, "duel_rate_bonus": 6, "cultivation_bonus": 4, "monthly_salary": 246, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "摄魂真传", "attack_bonus": 7, "defense_bonus": 4, "duel_rate_bonus": 5, "cultivation_bonus": 3, "monthly_salary": 180, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "引魂执事", "attack_bonus": 5, "defense_bonus": 3, "duel_rate_bonus": 3, "cultivation_bonus": 2, "monthly_salary": 130, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "巡夜执事", "attack_bonus": 4, "defense_bonus": 2, "duel_rate_bonus": 2, "cultivation_bonus": 2, "monthly_salary": 96, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "夜行弟子", "attack_bonus": 3, "defense_bonus": 2, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 58, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "幽门杂徒", "attack_bonus": 1, "defense_bonus": 1, "duel_rate_bonus": 1, "cultivation_bonus": 0, "monthly_salary": 30, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "万毒崖",
        "camp": "heterodox",
        "description": "毒道之妙在于后发制人。你若能在第一波瘴雾中睁开眼，崖顶的万毒经便会为你翻开下一章。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "min_comprehension": 18,
        "min_fortune": 20,
        "min_willpower": 16,
        "min_combat_power": 0,
        "defense_bonus": 7,
        "fortune_bonus": 8,
        "pill_poison_resist": 0.40,
        "pill_poison_cap_bonus": 50,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 0,
        "craft_success_rate": 0,
        "death_penalty_reduce": 0.0,
        "entry_hint": "授《万毒归元经》一卷。入崖试炼：穿过崖脚第一道毒瘴而不运功相抗——熬不住的请原路折返。",
        "roles": [
            {"role_key": "leader", "role_name": "崖主", "attack_bonus": 7, "defense_bonus": 12, "duel_rate_bonus": 5, "cultivation_bonus": 5, "monthly_salary": 350, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "毒师长老", "attack_bonus": 5, "defense_bonus": 9, "duel_rate_bonus": 4, "cultivation_bonus": 4, "monthly_salary": 240, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "百毒真传", "attack_bonus": 4, "defense_bonus": 7, "duel_rate_bonus": 3, "cultivation_bonus": 3, "monthly_salary": 170, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "试毒执事", "attack_bonus": 3, "defense_bonus": 5, "duel_rate_bonus": 2, "cultivation_bonus": 2, "monthly_salary": 128, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "药毒执事", "attack_bonus": 2, "defense_bonus": 4, "duel_rate_bonus": 1, "cultivation_bonus": 2, "monthly_salary": 96, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "内门毒修", "attack_bonus": 2, "defense_bonus": 3, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 56, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "试毒弟子", "attack_bonus": 1, "defense_bonus": 2, "duel_rate_bonus": 0, "cultivation_bonus": 1, "monthly_salary": 28, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "星罗海阁",
        "camp": "orthodox",
        "description": "临海观潮、夜观群星，潮声与星轨交织成最古老的道韵——海阁弟子以平衡之道立于天地之间。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "min_comprehension": 22,
        "min_fortune": 20,
        "min_charisma": 16,
        "min_combat_power": 0,
        "attack_bonus": 6,
        "defense_bonus": 6,
        "fortune_bonus": 6,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 5,
        "craft_success_rate": 6,
        "death_penalty_reduce": 0.0,
        "entry_hint": "授《星罗潮生诀》一卷。入阁试炼：在潮声轰鸣中端坐观星一刻而不动心神——心浮者浪涛自会劝退。",
        "roles": [
            {"role_key": "leader", "role_name": "海阁之主", "attack_bonus": 10, "defense_bonus": 10, "duel_rate_bonus": 5, "cultivation_bonus": 6, "monthly_salary": 350, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "观潮长老", "attack_bonus": 8, "defense_bonus": 8, "duel_rate_bonus": 4, "cultivation_bonus": 5, "monthly_salary": 238, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "星潮真传", "attack_bonus": 6, "defense_bonus": 6, "duel_rate_bonus": 3, "cultivation_bonus": 4, "monthly_salary": 170, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "巡潮执事", "attack_bonus": 4, "defense_bonus": 4, "duel_rate_bonus": 2, "cultivation_bonus": 3, "monthly_salary": 126, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "望海执事", "attack_bonus": 3, "defense_bonus": 3, "duel_rate_bonus": 1, "cultivation_bonus": 2, "monthly_salary": 96, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "潮汐弟子", "attack_bonus": 2, "defense_bonus": 2, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 58, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "海阁外门", "attack_bonus": 1, "defense_bonus": 1, "duel_rate_bonus": 0, "cultivation_bonus": 1, "monthly_salary": 30, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "灵傀山",
        "camp": "orthodox",
        "description": "擅制灵傀与机关，每一根傀丝都是心神的延伸——重耐心、重悟性，更重真元的细腻运转。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "min_comprehension": 22,
        "min_willpower": 18,
        "min_bone": 18,
        "min_combat_power": 0,
        "defense_bonus": 8,
        "cultivation_bonus": 8,
        "body_movement_bonus": 4,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.12,
        "explore_drop_rate": 0,
        "craft_success_rate": 12,
        "death_penalty_reduce": 0.0,
        "entry_hint": "授《灵傀百炼篇》一卷。入山考验：以心神牵起桌上最短的那根傀丝——手抖半分则丝断不收。",
        "roles": [
            {"role_key": "leader", "role_name": "山主", "attack_bonus": 8, "defense_bonus": 12, "duel_rate_bonus": 4, "cultivation_bonus": 7, "monthly_salary": 346, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "百炼长老", "attack_bonus": 6, "defense_bonus": 10, "duel_rate_bonus": 3, "cultivation_bonus": 5, "monthly_salary": 236, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "灵傀真传", "attack_bonus": 4, "defense_bonus": 8, "duel_rate_bonus": 2, "cultivation_bonus": 4, "monthly_salary": 168, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "机巧执事", "attack_bonus": 3, "defense_bonus": 6, "duel_rate_bonus": 2, "cultivation_bonus": 3, "monthly_salary": 124, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "傀坊执事", "attack_bonus": 2, "defense_bonus": 4, "duel_rate_bonus": 1, "cultivation_bonus": 2, "monthly_salary": 94, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "内门傀修", "attack_bonus": 1, "defense_bonus": 3, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 56, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "试线弟子", "attack_bonus": 1, "defense_bonus": 2, "duel_rate_bonus": 0, "cultivation_bonus": 1, "monthly_salary": 28, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
    {
        "name": "栖凰山",
        "camp": "orthodox",
        "description": "山中离火终年不熄，温烈并济方为上乘——栖凰之道不在爆发，在将烈意养成风骨。",
        "min_realm_stage": "炼气",
        "min_realm_layer": 5,
        "min_comprehension": 20,
        "min_charisma": 18,
        "min_fortune": 18,
        "min_combat_power": 0,
        "attack_bonus": 10,
        "cultivation_bonus": 6,
        "fortune_bonus": 4,
        "pill_poison_resist": 0.0,
        "pill_poison_cap_bonus": 0,
        "farm_growth_speed": 0.0,
        "explore_drop_rate": 0,
        "craft_success_rate": 0,
        "death_penalty_reduce": 0.30,
        "entry_hint": "授《栖凰离火录》一卷。入门试炼：将掌心离火维持一炷香而不灭——火脉不只看爆发，更看重持恒。",
        "roles": [
            {"role_key": "leader", "role_name": "凰主", "attack_bonus": 14, "defense_bonus": 6, "duel_rate_bonus": 6, "cultivation_bonus": 5, "monthly_salary": 352, "can_publish_tasks": True, "sort_order": 1},
            {"role_key": "elder", "role_name": "焰羽长老", "attack_bonus": 11, "defense_bonus": 5, "duel_rate_bonus": 5, "cultivation_bonus": 4, "monthly_salary": 240, "can_publish_tasks": True, "sort_order": 2},
            {"role_key": "core", "role_name": "离火真传", "attack_bonus": 8, "defense_bonus": 4, "duel_rate_bonus": 4, "cultivation_bonus": 3, "monthly_salary": 174, "can_publish_tasks": False, "sort_order": 3},
            {"role_key": "inner_deacon", "role_name": "焚霞执事", "attack_bonus": 6, "defense_bonus": 3, "duel_rate_bonus": 3, "cultivation_bonus": 2, "monthly_salary": 128, "can_publish_tasks": True, "sort_order": 4},
            {"role_key": "outer_deacon", "role_name": "栖焰执事", "attack_bonus": 4, "defense_bonus": 3, "duel_rate_bonus": 2, "cultivation_bonus": 2, "monthly_salary": 98, "can_publish_tasks": True, "sort_order": 5},
            {"role_key": "inner_disciple", "role_name": "焰羽弟子", "attack_bonus": 3, "defense_bonus": 2, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 58, "can_publish_tasks": False, "sort_order": 6},
            {"role_key": "outer_disciple", "role_name": "山门弟子", "attack_bonus": 1, "defense_bonus": 1, "duel_rate_bonus": 1, "cultivation_bonus": 1, "monthly_salary": 30, "can_publish_tasks": False, "sort_order": 7},
        ],
    },
]

DEFAULT_SCENES.extend(
    [
        {
            "name": "青木秘林",
            "description": "林间灵风自有轨迹，轻灵草木随风摇曳。传说曾有一株青木在此化形离去，留下满林木息供后人采撷。",
            "max_minutes": 36,
            "event_pool": [
                {"name": "旧剑匣遗痕", "description": "林间旧剑匣里压着一卷残旧炼图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "青霄巡天剑炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 42},
                {"name": "风痕身法", "description": "古树年轮里藏着一段步法心得。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "青霄御风诀", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 28},
                {"name": "枝影乱石", "description": "林中灵风卷石而起，险些打乱你的步伐。", "event_type": "danger", "weight": 3, "stone_bonus_min": 10, "stone_bonus_max": 24, "stone_loss_min": 4, "stone_loss_max": 10},
            ],
            "drops": [{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (10 - index), "stone_reward": 4, "event_text": f"你在青木秘林中采得一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["下品"], start=1)],
        },
        {
            "name": "玄潮古窟",
            "description": "中品矿窟深处有潮鸣回响，壁间矿脉层层叠叠，随手一凿都可能挖出上好护身材料。",
            "max_minutes": 42,
            "event_pool": [
                {"name": "枪胚残图", "description": "矿壁夹层里卡着一张沉重枪图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "玄岳镇海枪炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 38},
                {"name": "地息经文", "description": "地缝渗出的灵息里竟带着一段防御经文。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "玄岳不动经", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 24},
                {"name": "暗潮回卷", "description": "暗潮裹着碎石回卷而来，你只来得及护住要害。", "event_type": "danger", "weight": 3, "stone_bonus_min": 14, "stone_bonus_max": 30, "stone_loss_min": 6, "stone_loss_max": 14},
            ],
            "drops": [{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (10 - index), "stone_reward": 6, "event_text": f"你在玄潮古窟中挖到一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["中品"], start=1)],
        },
        {
            "name": "魇月裂谷",
            "description": "上品裂谷终年被一轮幻月笼罩，月光照不到的地方藏着暗袭与神魂类天材，唯胆大心细者方可取之。",
            "max_minutes": 48,
            "event_pool": [
                {"name": "夜刃图卷", "description": "裂谷深处漂着一页诡异刀图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "夜魇夺命刃炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 34},
                {"name": "阴影秘页", "description": "你在断壁背面看到一段追魂秘法。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "夜魇夺魂录", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 22},
                {"name": "魇月侵神", "description": "裂谷阴月忽明忽暗，让你的神识一阵刺痛。", "event_type": "danger", "weight": 3, "stone_bonus_min": 20, "stone_bonus_max": 40, "stone_loss_min": 10, "stone_loss_max": 20},
            ],
            "drops": [{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (10 - index), "stone_reward": 8, "event_text": f"你从魇月裂谷中截获一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["上品"], start=1)],
        },
        {
            "name": "星阙残庭",
            "description": "极品层级的残破仙庭废墟，断柱残垣间散落着周天与归元类天材，仿佛天道崩塌时遗落的私藏。",
            "max_minutes": 54,
            "event_pool": [
                {"name": "星袍织图", "description": "残庭石座上压着一页法袍织图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "星河归元袍炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 30},
                {"name": "归元篇章", "description": "夜半星影错位间，竟显出一页归元经文。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "星河归元章", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 20},
                {"name": "庭阵失衡", "description": "残庭阵纹突然逆卷，将你逼退数丈。", "event_type": "danger", "weight": 3, "stone_bonus_min": 26, "stone_bonus_max": 50, "stone_loss_min": 12, "stone_loss_max": 24},
            ],
            "drops": [{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (10 - index), "stone_reward": 10, "event_text": f"你在星阙残庭拾得一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["极品"], start=1)],
        },
        {
            "name": "紫宸天遗",
            "description": "上古仙庭崩塌后的一角废墟，苍穹时有裂痕如蛛网蔓延，散落的天阙旧材历经万劫而不朽。",
            "max_minutes": 58,
            "min_realm_stage": "炼虚",
            "min_realm_layer": 7,
            "min_combat_power": 1500,
            "event_pool": [
                {"name": "天刀遗图", "description": "一截断碑后压着完整的仙刀炼图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "紫宸天刀炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 16},
                {"name": "裂空真传", "description": "遗迹穹顶忽现一段天阙步法。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "紫宸裂空经", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 12},
                {"name": "天阙坠雷", "description": "残破禁制坠下一缕神雷，震得经脉发麻。", "event_type": "danger", "weight": 3, "stone_bonus_min": 36, "stone_bonus_max": 66, "stone_loss_min": 18, "stone_loss_max": 32},
            ],
            "drops": [
                *[{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (10 - index), "stone_reward": 14, "event_text": f"你在紫宸天遗中截获一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["仙品"], start=1)],
                {"reward_kind": "material", "reward_ref_id_name": "玄冥冰魄", "quantity_min": 1, "quantity_max": 1, "weight": 2, "stone_reward": 22, "event_text": "紫宸天遗阴影深处寒意凝结，你凿下一枚玄冥冰魄。"},
                {"reward_kind": "material", "reward_ref_id_name": "长生灵藤心", "quantity_min": 1, "quantity_max": 1, "weight": 2, "stone_reward": 22, "event_text": "残阙裂缝里仍有古藤不死，你取下其中一截长生灵藤心。"},
                {"reward_kind": "material", "reward_ref_id_name": "太清星尘", "quantity_min": 1, "quantity_max": 1, "weight": 2, "stone_reward": 22, "event_text": "碎裂天穹落下点点清辉，你收拢一捧太清星尘。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "紫宸战铠炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 80, "event_text": "紫宸天遗残阙之下，一副战铠阵纹仍在缓缓亮灭，你拓下完整炼图。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "紫宸飞履炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 80, "event_text": "裂空旧阶上留有飞履步纹，你循着残痕悟出紫宸飞履炼制图。"},
            ],
        },
        {
            "name": "鸿蒙源海",
            "description": "混沌未分之地，大道法则尚呈液态流转。有缘者仅凭一息感应便能踏足，无缘者穷尽一生也寻不到入口。",
            "max_minutes": 60,
            "min_realm_stage": "大乘",
            "min_realm_layer": 5,
            "min_combat_power": 1800,
            "event_pool": [
                {"name": "大道剑图", "description": "源海之上浮起一卷大道剑图，转瞬又要散去。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "太初道剑炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 10},
                {"name": "一炁残章", "description": "海面涟漪化成一段古老经文，须在一息之间记住。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "太初一炁经", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 8},
                {"name": "源海逆浪", "description": "鸿蒙源海掀起一片逆浪，几乎将你的神识整个淹没。", "event_type": "danger", "weight": 3, "stone_bonus_min": 48, "stone_bonus_max": 88, "stone_loss_min": 24, "stone_loss_max": 40},
            ],
            "drops": [{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (10 - index), "stone_reward": 18, "event_text": f"你从鸿蒙源海中捞到一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["先天至宝"], start=1)],
        },
        {
            "name": "玄穹潮墟",
            "description": "坍塌的古潮关口仍在缓缓吞吐海雾，残盾与甲片半埋于碎石之间，是高阶守御器修最常踏足的险地。",
            "max_minutes": 59,
            "min_realm_stage": "炼虚",
            "min_realm_layer": 3,
            "min_combat_power": 1620,
            "event_pool": [
                {"name": "古盾劫图", "description": "半塌潮门之后，还压着一整面古盾阵图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "玄穹镇劫盾炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 16},
                {"name": "镇劫残章", "description": "断碑缝里留着一段专讲卸力与稳身的古经。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "玄穹镇劫典", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 12},
                {"name": "潮墟反灌", "description": "塌陷潮门忽然倒卷，碎甲与寒潮一同拍来。", "event_type": "danger", "weight": 3, "stone_bonus_min": 38, "stone_bonus_max": 70, "stone_loss_min": 16, "stone_loss_max": 30},
            ],
            "drops": [
                *[{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (len(SEED_MATERIAL_BLUEPRINTS["仙品"]) - index), "stone_reward": 14, "event_text": f"你在玄穹潮墟中收下一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["仙品"], start=1)],
                {"reward_kind": "material", "reward_ref_id_name": "玄苍龟晶", "quantity_min": 1, "quantity_max": 1, "weight": 3, "stone_reward": 24, "event_text": "断流海眼里滚出一枚沉重的玄苍龟晶。"},
                {"reward_kind": "material", "reward_ref_id_name": "太虚雷纹钢", "quantity_min": 1, "quantity_max": 1, "weight": 3, "stone_reward": 24, "event_text": "你从断裂潮门的雷痕里凿下了一块太虚雷纹钢。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "玄穹镇劫戟炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 82, "event_text": "废关兵架上仍立着一柄残戟，你据其纹路补全了炼图。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "玄穹覆海甲炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 82, "event_text": "坍塌关墙后挂着一副破碎重甲，你拓下了完整覆海阵纹。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "玄穹踏界靴炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 80, "event_text": "碎石堆里留着一串踏界步印，你顺着步印悟出靴纹炼图。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "玄穹镇劫符符谱", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 74, "event_text": "一张残破符纸吸满海雾后显出完整镇劫符纹。"},
            ],
        },
        {
            "name": "云阙天径",
            "description": "悬在高空裂风中的仙路遗段，脚下皆是罡风与碎光，唯有真正擅长腾挪的人才能在这里带走完整器图。",
            "max_minutes": 59,
            "min_realm_stage": "炼虚",
            "min_realm_layer": 6,
            "min_combat_power": 1720,
            "event_pool": [
                {"name": "裂穹刃图", "description": "裂风深处悬着一卷几乎被撕碎的仙刃图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "云阙裂穹刃炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 14},
                {"name": "巡霄步痕", "description": "断桥上残留的步痕竟是一整门裂空身法。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "云阙巡霄诀", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 10},
                {"name": "天径崩风", "description": "高空罡风忽然折返，几乎将你连人带护体一并削开。", "event_type": "danger", "weight": 3, "stone_bonus_min": 42, "stone_bonus_max": 76, "stone_loss_min": 18, "stone_loss_max": 32},
            ],
            "drops": [
                *[{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (len(SEED_MATERIAL_BLUEPRINTS["仙品"]) - index), "stone_reward": 15, "event_text": f"你在云阙天径上截到一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["仙品"], start=1)],
                {"reward_kind": "material", "reward_ref_id_name": "云阙天蚕丝", "quantity_min": 1, "quantity_max": 1, "weight": 3, "stone_reward": 24, "event_text": "裂风深处挂着一缕完好的云阙天蚕丝，被你险险收了下来。"},
                {"reward_kind": "material", "reward_ref_id_name": "太虚雷纹钢", "quantity_min": 1, "quantity_max": 1, "weight": 2, "stone_reward": 24, "event_text": "断桥雷痕里嵌着一块太虚雷纹钢，仍在噼啪作响。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "云阙流光甲炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 82, "event_text": "你在残阶边缘抖开一页流光甲图，整页竟未被罡风撕碎。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "云阙逐电靴炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 82, "event_text": "断桥尽头留着一串雷痕步印，你顺着步印补齐了逐电靴图。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "云阙回风盾炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 80, "event_text": "一面碎盾在罡风里仍缓缓旋转，你临摹下了完整回风阵纹。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "云阙裂界符符谱", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 74, "event_text": "被风刃切开的符纸突然自行拼回，露出裂界符的全谱。"},
            ],
        },
        {
            "name": "混元界渊",
            "description": "界渊深处时有两重天地互相碾压，古修士在这里留下的每一件重器都带着镇界之意，非大修无法承受其威压。",
            "max_minutes": 60,
            "min_realm_stage": "大乘",
            "min_realm_layer": 6,
            "min_combat_power": 2050,
            "event_pool": [
                {"name": "断界古戈", "description": "界渊崖壁里斜插着半截古戈，戈身上还留着完整器图。", "event_type": "recipe", "weight": 3, "bonus_reward_kind": "recipe", "bonus_reward_ref_id_name": "混元断界戈炼制图", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 10},
                {"name": "御极总纲", "description": "两重界壁互相摩擦时，竟震出一段先天御极总纲。", "event_type": "oddity", "weight": 2, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "混元御极经", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 8},
                {"name": "界渊倒压", "description": "界渊忽然反向挤压，你的护体几乎被两重天地当场碾碎。", "event_type": "danger", "weight": 3, "stone_bonus_min": 50, "stone_bonus_max": 90, "stone_loss_min": 22, "stone_loss_max": 40},
            ],
            "drops": [
                *[{"reward_kind": "material", "reward_ref_id_name": name, "quantity_min": 1, "quantity_max": 2, "weight": 4 + (len(SEED_MATERIAL_BLUEPRINTS["先天至宝"]) - index), "stone_reward": 18, "event_text": f"你从混元界渊中摄出一份【{name}】。"} for index, name in enumerate(SEED_MATERIAL_BLUEPRINTS["先天至宝"], start=1)],
                {"reward_kind": "material", "reward_ref_id_name": "混元界壳", "quantity_min": 1, "quantity_max": 1, "weight": 3, "stone_reward": 28, "event_text": "界壁碎裂后露出一片完整混元界壳，被你迅速收走。"},
                {"reward_kind": "material", "reward_ref_id_name": "劫寂玄纱", "quantity_min": 1, "quantity_max": 1, "weight": 3, "stone_reward": 28, "event_text": "你在无声劫痕之间扯下一缕劫寂玄纱，入手竟轻若无物。"},
                {"reward_kind": "material", "reward_ref_id_name": "太易风痕晶", "quantity_min": 1, "quantity_max": 1, "weight": 3, "stone_reward": 28, "event_text": "界渊边缘留着一抹永不散去的风痕，被你凝成了太易风痕晶。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "混元玄界盾炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 90, "event_text": "界渊底部有一面几乎完好的古盾，你拓下了它全部镇界纹路。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "混元无漏甲炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 90, "event_text": "一副无漏古甲在界压中仍不曾开裂，你收下了完整炼图。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "混元踏虚履炼制图", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 88, "event_text": "崖边残留的虚空步痕竟能自行演化，你将其拓成了一卷履图。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "混元定界符符谱", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 82, "event_text": "界渊震落的一页古符残纸上，正写着完整定界符骨。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "太易遁空符符谱", "quantity_min": 1, "quantity_max": 1, "weight": 1, "stone_reward": 82, "event_text": "一道太易风痕在你面前凝成符纹，转瞬便被你封入谱页。"},
            ],
        },
    ]
)

DEFAULT_MATERIALS.extend(ALL_EXTRA_MATERIALS)
DEFAULT_ARTIFACTS.extend(EXTRA_ARTIFACTS)
DEFAULT_PILLS.extend(
    {
        "name": pill["name"],
        "rarity": pill["rarity"],
        "pill_type": pill["pill_type"],
        "description": pill["description"],
        "effect_value": pill["effect_value"],
        "poison_delta": pill["poison_delta"],
        "enabled": True,
    }
    for pill in EXTRA_PILLS
)
DEFAULT_TALISMANS.extend(
    {
        "name": talisman["name"],
        "rarity": talisman["rarity"],
        "description": talisman["description"],
        "attack_bonus": talisman.get("attack_bonus", 0),
        "defense_bonus": talisman.get("defense_bonus", 0),
        "bone_bonus": talisman.get("bone_bonus", 0),
        "comprehension_bonus": talisman.get("comprehension_bonus", 0),
        "divine_sense_bonus": talisman.get("divine_sense_bonus", 0),
        "fortune_bonus": talisman.get("fortune_bonus", 0),
        "qi_blood_bonus": talisman.get("qi_blood_bonus", 0),
        "true_yuan_bonus": talisman.get("true_yuan_bonus", 0),
        "body_movement_bonus": talisman.get("body_movement_bonus", 0),
        "duel_rate_bonus": talisman.get("duel_rate_bonus", 0),
        "effect_uses": talisman.get("effect_uses", 1),
        "combat_config": talisman.get("combat_config", {}),
        "enabled": True,
    }
    for talisman in EXTRA_TALISMANS
)
_extra_pill_success_map = {
    str(pill["name"]): int(pill.get("success", 60))
    for pill in EXTRA_PILLS
    if str(pill.get("name") or "").strip()
}
DEFAULT_RECIPES.extend(
    {
        **recipe,
        "base_success_rate": _extra_pill_success_map.get(
            str(recipe.get("result_name") or ""),
            int(recipe.get("base_success_rate", 60)),
        )
        if str(recipe.get("result_kind") or "") == "pill"
        else int(recipe.get("base_success_rate", 60)),
    }
    for recipe in EXTRA_RECIPES
)
DEFAULT_SCENES.extend(EXTRA_SCENES)
DEFAULT_SCENES.extend(
    [
        {
            "name": "太玄剑冢",
            "description": "旧剑意未散的山门剑冢，残剑虽朽，余势犹存——最适合炼气剑修磨砺锋芒、参悟剑势。",
            "max_minutes": 38,
            "min_realm_stage": "炼气",
            "min_realm_layer": 4,
            "min_combat_power": 620,
            "event_pool": [
                {"name": "剑纹回响", "description": "残剑共鸣间，有一段太玄剑意在石壁上浮现。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "太玄剑经", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 24},
                {"name": "剑碑残拓", "description": "你从半断石碑上拓下几笔清晰剑痕。", "event_type": "recipe", "weight": 2, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "青罡剑谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 42},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "寒铁矿", "quantity_min": 2, "quantity_max": 4, "weight": 5, "stone_reward": 6, "event_text": "剑冢裂隙中埋着锋芒未失的寒铁矿。"},
                {"reward_kind": "material", "reward_ref_id_name": "青霜铁", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 8, "event_text": "你在古剑堆下翻出一块泛着霜光的青霜铁。"},
            ],
        },
        {
            "name": "百草灵圃",
            "description": "药王谷废弃的旧药圃，灵雾终年不散，草木自行繁衍百代——遍地是年份扎实的药料与养元心得。",
            "max_minutes": 38,
            "min_realm_stage": "炼气",
            "min_realm_layer": 3,
            "min_combat_power": 560,
            "event_pool": [
                {"name": "木息丹纹", "description": "藤蔓缠绕的药案上留着一段温养真元的口诀。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "青木长生诀", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 26},
                {"name": "药谱旧页", "description": "你在废弃药柜深处翻到一张残页。", "event_type": "recipe", "weight": 2, "bonus_reward_kind": "material", "bonus_reward_ref_id_name": "回春丹谱残页", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 46},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "归元草", "quantity_min": 2, "quantity_max": 4, "weight": 6, "stone_reward": 5, "event_text": "灵圃药垄中长着一片养元用的归元草。"},
                {"reward_kind": "material", "reward_ref_id_name": "灵雾草心", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 8, "event_text": "你在薄雾中央采到一份灵雾草心。"},
            ],
        },
        {
            "name": "观星残台",
            "description": "天机阁废弃观星台虽已残破，石壁上仍残留大半星图——悟性高者或能在残图中看出几分天机流转。",
            "max_minutes": 42,
            "min_realm_stage": "炼气",
            "min_realm_layer": 6,
            "min_combat_power": 980,
            "event_pool": [
                {"name": "星图映照", "description": "残台上方忽然显出一角运转中的星图。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "天机观星术", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 22},
                {"name": "流星碎辉", "description": "一缕陨辉落入盘中，化成几粒星砂。", "event_type": "fortune", "weight": 3},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "星辉砂", "quantity_min": 1, "quantity_max": 2, "weight": 5, "stone_reward": 10, "event_text": "观星盘边缘滚落出几粒星辉砂。"},
                {"reward_kind": "material", "reward_ref_id_name": "星河砂", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 12, "event_text": "你在残台缝隙里刮下一份星河砂。"},
                {"reward_kind": "recipe", "reward_ref_id_name": "聚宝含光丹丹谱", "quantity_min": 1, "quantity_max": 1, "weight": 2, "stone_reward": 16, "event_text": "残台星轨忽然归于一线，你在观星盘底座暗格中抽出一页记着聚宝含光丹的旧丹谱。"},
            ],
        },
        {
            "name": "血煞试炼场",
            "description": "魔宫外门旧试炼场血气未散，遍地是打斗残痕——专为好战修士磨砺胆魄、以战养煞。",
            "max_minutes": 42,
            "min_realm_stage": "炼气",
            "min_realm_layer": 5,
            "min_combat_power": 920,
            "event_pool": [
                {"name": "煞纹战书", "description": "血色石柱上刻着一段魔宫战典。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "血煞战典", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 22},
                {"name": "杀伐回音", "description": "旧战场杀意回卷，让你的护体灵光狠狠一震。", "event_type": "danger", "weight": 3, "stone_bonus_min": 14, "stone_bonus_max": 28, "stone_loss_min": 8, "stone_loss_max": 16},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "赤炎晶砂", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 8, "event_text": "旧兵刃与地火摩擦，炼出一撮赤炎晶砂。"},
                {"reward_kind": "material", "reward_ref_id_name": "赤流砂", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 10, "event_text": "你在兵坑里翻出一份杀意未散的赤流砂。"},
            ],
        },
        {
            "name": "夜影回廊",
            "description": "幽冥鬼府外的回廊层层叠影，每走一步都似被人暗中盯着——身法稍慢就会被黑影反扑，鬼修最爱在此练身法。",
            "max_minutes": 44,
            "min_realm_stage": "炼气",
            "min_realm_layer": 6,
            "min_combat_power": 1080,
            "event_pool": [
                {"name": "夜行残页", "description": "你在阴影交叠处看到一篇完整夜行法门。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "幽冥夜行录", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 20},
                {"name": "影门错位", "description": "回廊中的影门忽然换位，险些把你困在原地。", "event_type": "danger", "weight": 3, "stone_bonus_min": 16, "stone_bonus_max": 30, "stone_loss_min": 8, "stone_loss_max": 16},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "云纹丝", "quantity_min": 2, "quantity_max": 4, "weight": 5, "stone_reward": 7, "event_text": "夜风卷来几束柔韧的云纹丝。"},
                {"reward_kind": "material", "reward_ref_id_name": "风鹤羽", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 10, "event_text": "影廊尽头飘着一片极轻的风鹤羽。"},
            ],
        },
        {
            "name": "毒瘴古泽",
            "description": "古泽瘴气层叠如纱，毒雾深处藏有旁人不敢采的奇材——耐性不够者走不过三步，但撑住了就是遍地机缘。",
            "max_minutes": 44,
            "min_realm_stage": "炼气",
            "min_realm_layer": 5,
            "min_combat_power": 960,
            "event_pool": [
                {"name": "毒经浮字", "description": "瘴云散开一瞬，露出一段收毒归元的古经。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "万毒归元经", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 22},
                {"name": "瘴浪逼身", "description": "毒雾突然翻卷，逼得你以真元硬抗。", "event_type": "danger", "weight": 3, "stone_bonus_min": 15, "stone_bonus_max": 28, "stone_loss_min": 8, "stone_loss_max": 15},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "凝露花", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 7, "event_text": "古泽边缘竟开着几朵耐毒的凝露花。"},
                {"reward_kind": "material", "reward_ref_id_name": "玄松脂", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 10, "event_text": "毒瘴深处的古松渗出一份玄松脂。"},
            ],
        },
        {
            "name": "潮音洞天",
            "description": "洞天潮声日夜不绝，如天地呼吸——最适合参悟潮汐转换、攻守交替的自然道韵。",
            "max_minutes": 46,
            "min_realm_stage": "炼气",
            "min_realm_layer": 5,
            "min_combat_power": 1020,
            "event_pool": [
                {"name": "潮生心法", "description": "潮声鼓荡之间，你听出了一段完整心法。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "星罗潮生诀", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 20},
                {"name": "海潮倒卷", "description": "洞中潮势忽快忽慢，险些把你拍进石壁。", "event_type": "danger", "weight": 3, "stone_bonus_min": 18, "stone_bonus_max": 32, "stone_loss_min": 8, "stone_loss_max": 18},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "寒水露", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 8, "event_text": "潮音石壁上凝出了几滴寒水露。"},
                {"reward_kind": "material", "reward_ref_id_name": "云母银丝", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 11, "event_text": "洞天潮眼里卷出一缕云母银丝。"},
            ],
        },
        {
            "name": "傀丝遗坊",
            "description": "遗坊遍布断线机关与旧灵傀残件，满地都是前人留下的半成品——考验耐心与细致操控，傀修复原的绝佳试场。",
            "max_minutes": 46,
            "min_realm_stage": "炼气",
            "min_realm_layer": 4,
            "min_combat_power": 880,
            "event_pool": [
                {"name": "百炼傀谱", "description": "旧工坊正厅里悬着一页傀术总纲。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "灵傀百炼篇", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 24},
                {"name": "乱线回弹", "description": "一根断裂傀丝突然回弹，在你手臂上割出一道血线。", "event_type": "danger", "weight": 3, "stone_bonus_min": 14, "stone_bonus_max": 26, "stone_loss_min": 6, "stone_loss_max": 14},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "灵木芯", "quantity_min": 1, "quantity_max": 3, "weight": 5, "stone_reward": 6, "event_text": "遗坊残架中还留着几枚灵木芯。"},
                {"reward_kind": "material", "reward_ref_id_name": "九曲灵丝", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 11, "event_text": "你顺着遗坊地槽抽出一缕九曲灵丝。"},
            ],
        },
        {
            "name": "栖凰焰谷",
            "description": "焰谷火意灵动不暴戾，讲究节奏与火势回转——正如栖凰山一脉的修行之道，温烈并济方为上乘。",
            "max_minutes": 48,
            "min_realm_stage": "炼气",
            "min_realm_layer": 5,
            "min_combat_power": 1100,
            "event_pool": [
                {"name": "凰羽离火", "description": "山谷深处落下一片离火凰羽，内里藏着完整真意。", "event_type": "oddity", "weight": 3, "bonus_reward_kind": "technique", "bonus_reward_ref_id_name": "栖凰离火录", "bonus_quantity_min": 1, "bonus_quantity_max": 1, "bonus_chance": 20},
                {"name": "焰流暴走", "description": "谷底火流骤然暴走，只能以真元强行压住。", "event_type": "danger", "weight": 3, "stone_bonus_min": 20, "stone_bonus_max": 34, "stone_loss_min": 10, "stone_loss_max": 18},
            ],
            "drops": [
                {"reward_kind": "material", "reward_ref_id_name": "赤炎晶砂", "quantity_min": 2, "quantity_max": 3, "weight": 5, "stone_reward": 8, "event_text": "焰谷风口卷出一簇赤炎晶砂。"},
                {"reward_kind": "material", "reward_ref_id_name": "紫焰琉砂", "quantity_min": 1, "quantity_max": 2, "weight": 4, "stone_reward": 12, "event_text": "你在火脉交汇处采到一份紫焰琉砂。"},
            ],
        },
    ]
)

FIRST_REALM_STAGE = REALM_ORDER[0]
BREAKTHROUGH_BASE_RATE = {
    stage: int(rule.get("breakthrough_base_rate", 0))
    for stage, rule in REALM_STAGE_RULES.items()
}
BREAKTHROUGH_PILL_NAME_OVERRIDES = {
    "炼气": "筑基丹",
    "渡劫": "天罚破境丹",
}
BREAKTHROUGH_QUALITY_LABELS = ["下品", "中品", "上品", "极品", "仙品", "先天至宝"]
BREAKTHROUGH_SCENE_NAME_SUFFIX = "破境秘境"


def _breakthrough_target_stage(stage: str) -> str | None:
    index = realm_index(stage)
    if index < 0 or index >= len(REALM_ORDER) - 1:
        return None
    return REALM_ORDER[index + 1]


def _breakthrough_requirement(stage: str | None) -> dict[str, Any] | None:
    current_stage = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    target_stage = _breakthrough_target_stage(current_stage)
    if target_stage is None:
        return None
    source_index = max(realm_index(current_stage), 0)
    quality_index = min((source_index * len(BREAKTHROUGH_QUALITY_LABELS)) // max(len(REALM_ORDER) - 1, 1), len(BREAKTHROUGH_QUALITY_LABELS) - 1)
    quality_label = BREAKTHROUGH_QUALITY_LABELS[quality_index]
    pool = SEED_MATERIAL_BLUEPRINTS[quality_label]
    offset = source_index % len(pool)
    material_names = [pool[(offset + step * 3) % len(pool)] for step in range(3)]
    pill_name = BREAKTHROUGH_PILL_NAME_OVERRIDES.get(current_stage, f"{target_stage}破境丹")
    recipe_name = f"{pill_name}丹谱"
    scene_name = f"{target_stage}{BREAKTHROUGH_SCENE_NAME_SUFFIX}"
    success_floor = min(58 + source_index * 2, 88)
    min_power = 180 + source_index * 320
    return {
        "source_stage": current_stage,
        "target_stage": target_stage,
        "pill_name": pill_name,
        "recipe_name": recipe_name,
        "scene_name": scene_name,
        "quality_label": quality_label,
        "material_names": material_names,
        "success_floor": success_floor,
        "min_power": min_power,
    }


def _build_breakthrough_seed_payloads() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    pills: list[dict[str, Any]] = []
    recipes: list[dict[str, Any]] = []
    scenes: list[dict[str, Any]] = []
    for stage in REALM_ORDER[:-1]:
        requirement = _breakthrough_requirement(stage)
        if requirement is None:
            continue
        source_index = max(realm_index(requirement["source_stage"]), 0)
        target_stage = requirement["target_stage"]
        pill_name = requirement["pill_name"]
        recipe_name = requirement["recipe_name"]
        scene_name = requirement["scene_name"]
        material_names = requirement["material_names"]
        rarity = requirement["quality_label"]
        effect_value = 48 + source_index * 4
        poison_delta = 6 + min(source_index, 8)
        pills.append(
            {
                "name": pill_name,
                "rarity": rarity,
                "pill_type": "foundation",
                "description": f"专为 {target_stage} 大境界突破炼制的破境丹，药力会在冲关一刻稳住灵台与经脉，适合 {requirement['source_stage']} 圆满修士服用。",
                "effect_value": effect_value,
                "poison_delta": poison_delta,
                "min_realm_stage": requirement["source_stage"],
                "min_realm_layer": 9,
                "enabled": True,
            }
        )
        recipes.append(
            {
                "name": recipe_name,
                "recipe_kind": "pill",
                "result_kind": "pill",
                "result_name": pill_name,
                "result_quantity": 1,
                "base_success_rate": max(72 - source_index * 2, 28),
                "broadcast_on_success": False,
                "ingredients": [{"material_name": item_name, "quantity": 1} for item_name in material_names],
            }
        )
        scenes.append(
            {
                "name": scene_name,
                "description": f"为 {requirement['source_stage']} 修士准备的破境试炼地，产出 {pill_name} 所需主材，也有机会直接找到丹谱。",
                "max_minutes": min(32 + source_index * 2, 60),
                "min_realm_stage": requirement["source_stage"],
                "min_realm_layer": 8,
                "min_combat_power": requirement["min_power"],
                "event_pool": [
                    {
                        "name": "破境残诀",
                        "description": f"残阵之中残留着前辈冲击 {target_stage} 的心得，你顺势找到了关键丹谱。",
                        "event_type": "recipe",
                        "weight": 3,
                        "bonus_reward_kind": "recipe",
                        "bonus_reward_ref_id_name": recipe_name,
                        "bonus_quantity_min": 1,
                        "bonus_quantity_max": 1,
                        "bonus_chance": min(34 + source_index, 68),
                    }
                ],
                "drops": [
                    {
                        "reward_kind": "material",
                        "reward_ref_id_name": item_name,
                        "quantity_min": 1,
                        "quantity_max": 2 if index == 0 else 1,
                        "weight": max(6 - index, 2),
                        "stone_reward": 4 + source_index * 2,
                        "event_text": f"你在 {scene_name} 中觅得一份【{item_name}】。",
                    }
                    for index, item_name in enumerate(material_names)
                ]
                + [
                    {
                        "reward_kind": "recipe",
                        "reward_ref_id_name": recipe_name,
                        "quantity_min": 1,
                        "quantity_max": 1,
                        "weight": 1,
                        "stone_reward": 6 + source_index * 2,
                        "event_text": f"你在 {scene_name} 的核心残阵中找到一页【{recipe_name}】。",
                    }
                ],
            }
        )
    return pills, recipes, scenes


BREAKTHROUGH_PILLS, BREAKTHROUGH_RECIPES, BREAKTHROUGH_SCENES = _build_breakthrough_seed_payloads()
DEFAULT_PILLS.extend(BREAKTHROUGH_PILLS)
DEFAULT_RECIPES.extend(BREAKTHROUGH_RECIPES)
DEFAULT_SCENES.extend(BREAKTHROUGH_SCENES)
DEFAULT_MATERIALS = apply_farmable_material_overrides(DEFAULT_MATERIALS, DEFAULT_RECIPES)

SPIRIT_STONE_COMMISSION_ACTION = "commission"
SPIRIT_STONE_COMMISSIONS = {
    "work": {
        "key": "work",
        "name": "仙坊打工",
        "description": "在坊市轮值、搬运灵材与整理柜台，风险最低，但也得有足够心志和脚力才不会手忙脚乱。",
        "summary": "入门稳定差事，适合刚踏入仙途的修士慢慢攒第一桶灵石。",
        "cooldown_hours": 4,
        "min_realm_stage": FIRST_REALM_STAGE,
        "min_realm_layer": 1,
        "stone_range": (12, 24),
        "cultivation_range": (8, 16),
        "stone_bonus_cap": 8,
        "cultivation_bonus_cap": 6,
        "attribute_requirements": {"willpower": 10, "body_movement": 8},
        "stone_bonus_divisors": {"fortune": 4, "body_movement": 6, "charisma": 8},
        "cultivation_bonus_divisors": {"comprehension": 4, "willpower": 6},
        "result_texts": [
            "在仙坊忙完一班，账房按时结了工钱。",
            "替商会整理完灵材库后，顺手领到了今日酬劳。",
        ],
    },
    "spirit_field": {
        "key": "spirit_field",
        "name": "照料灵田",
        "description": "替药圃巡查灵田、调理地脉和分拣草木精华，讲究悟性、机缘和真元续航。",
        "summary": "低风险技术活，基础奖励略低，但稳定且吃悟性。",
        "cooldown_hours": 4,
        "min_realm_stage": "炼气",
        "min_realm_layer": 4,
        "stone_range": (18, 32),
        "cultivation_range": (10, 22),
        "stone_bonus_cap": 10,
        "cultivation_bonus_cap": 8,
        "attribute_requirements": {"comprehension": 16, "fortune": 12, "true_yuan": 520},
        "stone_bonus_divisors": {"fortune": 4, "charisma": 7, "true_yuan": 42},
        "cultivation_bonus_divisors": {"comprehension": 4, "divine_sense": 7},
        "result_texts": [
            "你把灵田地脉梳理得井井有条，药圃管事满意地结算了工钱。",
            "灵露与草木精气被你调配得分毫不差，药农额外添了一份酬谢。",
        ],
    },
    "ore_sorting": {
        "key": "ore_sorting",
        "name": "巡拣矿脉",
        "description": "替矿坊分辨矿脉、搬运矿料并守住坍塌口，既吃体魄，也考验防御底子。",
        "summary": "炼气后期开放，偏重根骨、气血与防御，回报比灵田略高。",
        "cooldown_hours": 4,
        "min_realm_stage": "炼气",
        "min_realm_layer": 7,
        "stone_range": (22, 40),
        "cultivation_range": (12, 26),
        "stone_bonus_cap": 12,
        "cultivation_bonus_cap": 8,
        "attribute_requirements": {"bone": 16, "defense_power": 20, "qi_blood": 720},
        "stone_bonus_divisors": {"bone": 4, "defense_power": 5, "qi_blood": 90},
        "cultivation_bonus_divisors": {"bone": 4, "willpower": 6},
        "result_texts": [
            "你顺着地脉把几处杂矿分拣清楚，矿坊按件结算了酬劳。",
            "塌方点被你稳稳守住，矿监满意地补发了一笔灵石。",
        ],
    },
    "beast_hunt": {
        "key": "beast_hunt",
        "name": "代捕灵兽",
        "description": "替洞府雇主追索走失灵兽，讲究胆气、身手与追踪机缘。",
        "summary": "筑基后可接的实战差事，偏重攻击、身法与机缘。",
        "cooldown_hours": 6,
        "min_realm_stage": "筑基",
        "min_realm_layer": 3,
        "stone_range": (34, 60),
        "cultivation_range": (20, 40),
        "stone_bonus_cap": 18,
        "cultivation_bonus_cap": 12,
        "attribute_requirements": {"attack_power": 32, "body_movement": 16, "fortune": 14},
        "stone_bonus_divisors": {"attack_power": 3, "fortune": 4, "qi_blood": 40},
        "cultivation_bonus_divisors": {"bone": 3, "willpower": 4, "karma": 5},
        "result_texts": [
            "你循着兽痕擒回暴走灵兽，雇主爽快付清了悬红。",
            "几番腾挪后终于将灵兽困入封灵笼，拿到了不菲酬劳。",
        ],
    },
    "caravan_guard": {
        "key": "caravan_guard",
        "name": "护送灵材商队",
        "description": "替跨境商队压阵护镖、驱散沿途妖匪，既看战力也看身法和眼力。",
        "summary": "筑基中后期高强度差事，收益更稳，但更吃攻防底子。",
        "cooldown_hours": 6,
        "min_realm_stage": "筑基",
        "min_realm_layer": 7,
        "stone_range": (46, 78),
        "cultivation_range": (28, 50),
        "stone_bonus_cap": 22,
        "cultivation_bonus_cap": 14,
        "attribute_requirements": {"attack_power": 38, "defense_power": 36, "body_movement": 22},
        "stone_bonus_divisors": {"attack_power": 3, "defense_power": 4, "body_movement": 3},
        "cultivation_bonus_divisors": {"willpower": 3, "body_movement": 5, "karma": 5},
        "result_texts": [
            "你护着商队穿过险路，压住了几波劫匪，镖头当场加了价。",
            "一路压阵到最后一站，商会按高风险档位发下了整笔酬金。",
        ],
    },
    "fire_watch": {
        "key": "fire_watch",
        "name": "值守地火室",
        "description": "替炼丹房和炼器铺值守地火，既要扛得住火压，也得有足够真元维持火候稳定。",
        "summary": "金丹期开放的耐力差事，偏重心志、防御与真元。",
        "cooldown_hours": 6,
        "min_realm_stage": "金丹",
        "min_realm_layer": 1,
        "stone_range": (56, 92),
        "cultivation_range": (32, 60),
        "stone_bonus_cap": 24,
        "cultivation_bonus_cap": 16,
        "attribute_requirements": {"willpower": 22, "defense_power": 44, "true_yuan": 820},
        "stone_bonus_divisors": {"willpower": 4, "defense_power": 5, "true_yuan": 70},
        "cultivation_bonus_divisors": {"willpower": 4, "true_yuan": 60},
        "result_texts": [
            "你把地火火势稳稳压在最佳区间，丹房按值守档给了工钱。",
            "几炉灵材都顺利出炉，掌柜满意地加发了一笔酬劳。",
        ],
    },
    "formation_maintenance": {
        "key": "formation_maintenance",
        "name": "检修护山阵",
        "description": "替洞府和坊市修补阵纹、校准灵枢，要求悟性、神识与真元足够扎实。",
        "summary": "偏技术路线的金丹差事，门槛更明确，基础回报比旧版更收敛。",
        "cooldown_hours": 8,
        "min_realm_stage": "金丹",
        "min_realm_layer": 3,
        "stone_range": (66, 108),
        "cultivation_range": (38, 70),
        "stone_bonus_cap": 26,
        "cultivation_bonus_cap": 18,
        "attribute_requirements": {"comprehension": 24, "divine_sense": 22, "true_yuan": 860},
        "stone_bonus_divisors": {"comprehension": 3, "divine_sense": 4, "true_yuan": 28},
        "cultivation_bonus_divisors": {"comprehension": 3, "divine_sense": 4, "fortune": 6},
        "result_texts": [
            "你把护山阵断裂的灵纹补得严丝合缝，阵主爽快结清了报酬。",
            "灵枢重启后阵光再起，对方依照高阶阵修的价码付给了酬劳。",
        ],
    },
    "sword_repair": {
        "key": "sword_repair",
        "name": "修补灵剑",
        "description": "替剑修温养剑胚、补全剑纹与禁制，最吃悟性与神识。",
        "summary": "高阶技术差事，重悟性、神识与真元，收益高但不再离谱。",
        "cooldown_hours": 8,
        "min_realm_stage": "金丹",
        "min_realm_layer": 5,
        "stone_range": (76, 124),
        "cultivation_range": (44, 80),
        "stone_bonus_cap": 28,
        "cultivation_bonus_cap": 20,
        "attribute_requirements": {"comprehension": 28, "divine_sense": 24, "true_yuan": 920, "charisma": 18},
        "stone_bonus_divisors": {"comprehension": 3, "divine_sense": 4, "true_yuan": 35, "charisma": 10},
        "cultivation_bonus_divisors": {"comprehension": 3, "divine_sense": 5, "karma": 4},
        "result_texts": [
            "你补齐了灵剑缺失的剑纹，对方当场付了修剑酬金。",
            "一番祭炼后剑鸣再起，主人满意地结清了报酬。",
        ],
    },
    "cloud_escort": {
        "key": "cloud_escort",
        "name": "云舟押阵",
        "description": "替跨州云舟压阵护航，要在高空乱流和突袭之间稳住全船阵脚。",
        "summary": "元婴初期开放，偏重攻防、身法与气血，是新版中高阶主力委托。",
        "cooldown_hours": 10,
        "min_realm_stage": "元婴",
        "min_realm_layer": 1,
        "stone_range": (90, 148),
        "cultivation_range": (52, 96),
        "stone_bonus_cap": 32,
        "cultivation_bonus_cap": 22,
        "attribute_requirements": {"attack_power": 56, "defense_power": 50, "body_movement": 30, "qi_blood": 1200},
        "stone_bonus_divisors": {"attack_power": 3, "defense_power": 4, "qi_blood": 55},
        "cultivation_bonus_divisors": {"willpower": 3, "body_movement": 5, "karma": 4},
        "result_texts": [
            "你压住了云舟沿途几波袭扰，船主按高阶护航价结算了酬金。",
            "乱流与妖匪都被你稳稳挡下，整船平安抵达后拿到了厚实报酬。",
        ],
    },
    "rift_patrol": {
        "key": "rift_patrol",
        "name": "镇守裂隙前哨",
        "description": "前往高危裂隙前哨清剿异兽、稳住阵脚，是当前最凶险也最赚钱的长期差事。",
        "summary": "当前最高阶日常委托，回报仍高，但基础值已比旧版收紧。",
        "cooldown_hours": 10,
        "min_realm_stage": "元婴",
        "min_realm_layer": 4,
        "stone_range": (108, 176),
        "cultivation_range": (64, 118),
        "stone_bonus_cap": 36,
        "cultivation_bonus_cap": 24,
        "attribute_requirements": {"attack_power": 68, "defense_power": 60, "willpower": 30, "qi_blood": 1450},
        "stone_bonus_divisors": {"attack_power": 2, "defense_power": 3, "qi_blood": 24, "willpower": 4},
        "cultivation_bonus_divisors": {"bone": 3, "willpower": 3, "karma": 4, "true_yuan": 36},
        "result_texts": [
            "你顶住裂隙前哨的连续冲击，统领按最高风险档位发放了整笔军饷。",
            "前哨危局被你稳住，阵营库房依规补发了一份厚重的灵石与修为奖励。",
        ],
    },
}
DAILY_PRACTICE_CULTIVATION_FACTOR = 0.88
DAILY_PRACTICE_STONE_FACTOR = 0.84
ROOT_QUALITY_ROLLS = [
    ("天灵根", 1),
    ("变异灵根", 1),
    ("极品灵根", 10),
    ("上品灵根", 20),
    ("中品灵根", 32),
    ("下品灵根", 28),
    ("废灵根", 8),
]
ITEM_STAT_FIELDS = (
    "attack_bonus",
    "defense_bonus",
    "bone_bonus",
    "comprehension_bonus",
    "divine_sense_bonus",
    "fortune_bonus",
    "qi_blood_bonus",
    "true_yuan_bonus",
    "body_movement_bonus",
    "duel_rate_bonus",
    "cultivation_bonus",
)

TALISMAN_ACTIVE_EFFECT_FIELDS = (
    "cultivation_bonus",
    "craft_success_bonus",
    "exploration_drop_bonus",
    "exploration_quantity_bonus",
    "exploration_stone_bonus",
    "exploration_risk_reduce",
    "fishing_luck_bonus",
    "fishing_empty_reduce",
    "fishing_quantity_bonus",
    "exploration_repeat_count",
    "boss_damage_bonus",
    "boss_crit_bonus",
    "practice_stone_bonus",
)
TALISMAN_UTILITY_KEYWORDS = (
    ("化毒", "exploration_risk_reduce"),
    ("护", "exploration_risk_reduce"),
    ("镇", "exploration_risk_reduce"),
    ("金钟", "exploration_risk_reduce"),
    ("涅槃", "exploration_risk_reduce"),
    ("风", "fishing_empty_reduce"),
    ("浪", "fishing_empty_reduce"),
    ("潮", "fishing_empty_reduce"),
    ("影", "fishing_empty_reduce"),
    ("裂空", "fishing_empty_reduce"),
    ("醒神", "craft_success_bonus"),
    ("天师", "craft_success_bonus"),
    ("建木", "cultivation_bonus"),
    ("鸿蒙", "cultivation_bonus"),
    ("开天", "cultivation_bonus"),
    ("冰", "exploration_drop_bonus"),
    ("寒", "exploration_drop_bonus"),
    ("魄", "exploration_drop_bonus"),
    ("摄魂", "exploration_drop_bonus"),
    ("魂", "exploration_drop_bonus"),
    ("命", "exploration_drop_bonus"),
    ("雷", "boss_damage_bonus"),
    ("火", "boss_damage_bonus"),
    ("焰", "boss_damage_bonus"),
    ("破", "boss_damage_bonus"),
    ("罚", "boss_damage_bonus"),
    ("白虎", "boss_damage_bonus"),
)
CURSE_TRIGGER_ACTION_LABELS = {
    "practice": "吐纳",
    "commission": "委托",
    "exploration": "探索",
    "fishing": "垂钓",
    "personal_boss": "个人Boss",
    "world_boss": "世界Boss",
}
CURSE_DAN_POISON_CAP = 100


def _repair_profile_realm_state(tg: int) -> XiuxianProfile | None:
    profile = get_profile(tg, create=False)
    if profile is None:
        return None
    repair = migrate_legacy_realm_state(profile.realm_stage, profile.realm_layer, profile.cultivation)
    target_stage = repair["target_stage"]
    target_layer = int(repair["target_layer"])
    target_cultivation = int(repair["target_cultivation"])
    changed = bool(repair.get("changed"))

    target_stage = normalize_realm_stage(target_stage or FIRST_REALM_STAGE)
    settled_layer, settled_cultivation, _, _ = apply_cultivation_gain(
        target_stage,
        target_layer,
        target_cultivation,
        0,
    )
    if settled_layer != target_layer or settled_cultivation != target_cultivation:
        changed = True
        target_layer = settled_layer
        target_cultivation = settled_cultivation

    if not changed:
        return profile
    return upsert_profile(
        tg,
        realm_stage=target_stage,
        realm_layer=target_layer,
        cultivation=target_cultivation,
    )


def _realm_stage_rule(stage: str | None) -> dict[str, int]:
    normalized = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    return REALM_STAGE_RULES.get(normalized, REALM_STAGE_RULES[FIRST_REALM_STAGE])


def _commission_latest_entry(session: Session, tg: int, title: str) -> XiuxianJournal | None:
    return (
        session.query(XiuxianJournal)
        .filter(
            XiuxianJournal.tg == int(tg),
            XiuxianJournal.action_type == SPIRIT_STONE_COMMISSION_ACTION,
            XiuxianJournal.title == title,
        )
        .order_by(XiuxianJournal.created_at.desc(), XiuxianJournal.id.desc())
        .first()
    )


def _format_countdown(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {seconds} 秒"
    return f"{seconds} 秒"


def _attribute_display_label(attribute_key: str) -> str:
    key = str(attribute_key or "").strip()
    return {
        "attack_power": "攻击",
        "defense_power": "防御",
    }.get(key, ATTRIBUTE_LABELS.get(f"{key}_bonus", key))


def _commission_effective_stats(tg: int, profile_data: dict[str, Any]) -> dict[str, float]:
    equipped_artifacts = collect_equipped_artifacts(tg)
    artifact_effects = merge_artifact_effects(profile_data, equipped_artifacts)
    active_talisman = serialize_talisman(get_talisman(profile_data.get("active_talisman_id"))) if profile_data.get("active_talisman_id") else None
    current_technique = _current_technique_payload(profile_data)
    current_title = get_current_title(tg)
    talisman_effects = resolve_talisman_effects(profile_data, active_talisman) if active_talisman else None
    technique_effects = resolve_technique_effects(profile_data, current_technique) if current_technique else None
    title_effects = resolve_title_effects(profile_data, current_title) if current_title else None
    return _effective_stats(
        profile_data,
        artifact_effects,
        talisman_effects,
        get_sect_effects(profile_data),
        technique_effects,
        title_effects,
    )


def _commission_attribute_requirements(config: dict[str, Any]) -> dict[str, int]:
    requirements: dict[str, int] = {}
    for key, value in (config.get("attribute_requirements") or {}).items():
        amount = max(int(value or 0), 0)
        if amount > 0:
            requirements[str(key)] = amount
    return requirements


def _commission_attribute_requirement_rows(stats: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, required in _commission_attribute_requirements(config).items():
        current = max(int(stats.get(key, 0) or 0), 0)
        rows.append(
            {
                "key": key,
                "label": _attribute_display_label(key),
                "required": required,
                "current": current,
                "met": current >= required,
            }
        )
    return rows


def _commission_requirement_summary(config: dict[str, Any]) -> str:
    parts: list[str] = []
    if config.get("min_realm_stage"):
        parts.append(format_realm_requirement(config.get("min_realm_stage"), config.get("min_realm_layer")))
    parts.extend(
        f"{_attribute_display_label(key)}≥{required}"
        for key, required in _commission_attribute_requirements(config).items()
    )
    return " · ".join(parts) if parts else "无门槛"


def _commission_missing_requirement_text(stats: dict[str, Any], config: dict[str, Any]) -> str:
    missing = [
        f"{row['label']} {row['current']}/{row['required']}"
        for row in _commission_attribute_requirement_rows(stats, config)
        if not row.get("met")
    ]
    return "、".join(missing)


def _commission_reward_bonus(
    stats: dict[str, Any],
    divisors: dict[str, int],
    *,
    cap: int | None = None,
) -> int:
    total = 0
    for key, divisor in (divisors or {}).items():
        safe_divisor = max(int(divisor or 1), 1)
        total += max(int(stats.get(key, 0) or 0), 0) // safe_divisor
    if cap is not None:
        total = min(total, max(int(cap or 0), 0))
    return total


def build_spirit_stone_commissions(tg: int) -> list[dict[str, Any]]:
    _settle_retreat_progress(tg)
    profile = _repair_profile_realm_state(tg)
    if profile is None or not profile.consented:
        return []
    profile_data = serialize_profile(profile) or {}
    effective_stats = _commission_effective_stats(tg, profile_data)
    retreating = _is_retreating(profile)
    duel_lock = get_active_duel_lock(tg)
    now = utcnow()
    rows: list[dict[str, Any]] = []
    with Session() as session:
        for key, config in SPIRIT_STONE_COMMISSIONS.items():
            last_entry = _commission_latest_entry(session, tg, config["name"])
            next_available_at = None
            if last_entry is not None:
                next_available_at = last_entry.created_at + timedelta(hours=int(config["cooldown_hours"]))

            unlocked = realm_requirement_met(
                profile_data,
                config.get("min_realm_stage"),
                config.get("min_realm_layer"),
            )
            attribute_requirements = _commission_attribute_requirement_rows(effective_stats, config)
            unmet_attribute_text = _commission_missing_requirement_text(effective_stats, config)
            available = bool(
                not profile_data.get("is_dead")
                and not retreating
                and not duel_lock
                and unlocked
                and not unmet_attribute_text
                and (next_available_at is None or next_available_at <= now)
            )
            reason = ""
            if profile_data.get("is_dead"):
                reason = "角色已死亡，只能重新踏出仙途。"
            elif retreating:
                reason = "闭关之中，无暇承接凡尘委托，待出关后再议。"
            elif duel_lock:
                reason = duel_lock.get("duel_mode_label", "斗法") + "结算前，禁止灵石操作"
            elif not unlocked:
                reason = f"需要达到 {format_realm_requirement(config.get('min_realm_stage'), config.get('min_realm_layer'))}"
            elif unmet_attribute_text:
                reason = f"属性未达标：{unmet_attribute_text}"
            elif next_available_at is not None and next_available_at > now:
                reason = f"冷却中，还需 {_format_countdown(next_available_at - now)}"
            rows.append(
                {
                    "key": key,
                    "name": config["name"],
                    "description": config["description"],
                    "summary": config["summary"],
                    "cooldown_hours": int(config["cooldown_hours"]),
                    "min_realm_stage": config.get("min_realm_stage"),
                    "min_realm_layer": int(config.get("min_realm_layer") or 1),
                    "reward_stone_min": int(config["stone_range"][0]),
                    "reward_stone_max": int(config["stone_range"][1]),
                    "reward_cultivation_min": int(config["cultivation_range"][0]),
                    "reward_cultivation_max": int(config["cultivation_range"][1]),
                    "attribute_requirements": attribute_requirements,
                    "requirement_summary": _commission_requirement_summary(config),
                    "available": available,
                    "reason": reason,
                    "last_claimed_at": serialize_datetime(last_entry.created_at) if last_entry else None,
                    "next_available_at": serialize_datetime(next_available_at) if next_available_at else None,
                }
            )
    return rows


def claim_spirit_stone_commission(tg: int, commission_key: str, *, include_profile: bool = True) -> dict[str, Any]:
    config = SPIRIT_STONE_COMMISSIONS.get(str(commission_key or "").strip())
    if config is None:
        raise ValueError("未寻得此委托，或已被他人先行接下。")

    _settle_retreat_progress(tg)
    profile = _require_alive_profile_obj(tg, f"处理{config['name']}")
    if _is_retreating(profile):
        raise ValueError("闭关之中，无暇承接凡尘委托，待出关后再议。")

    profile_data = serialize_profile(profile) or {}
    if not realm_requirement_met(profile_data, config.get("min_realm_stage"), config.get("min_realm_layer")):
        raise ValueError(f"需要达到 {format_realm_requirement(config.get('min_realm_stage'), config.get('min_realm_layer'))} 才能承接该委托。")
    equipped_artifacts = collect_equipped_artifacts(tg)
    stats = _commission_effective_stats(tg, profile_data)
    missing_requirement_text = _commission_missing_requirement_text(stats, config)
    if missing_requirement_text:
        raise ValueError(f"当前属性未达标：{missing_requirement_text}。")

    stone_bonus_cap = max(int(config.get("stone_bonus_cap") or config["stone_range"][1] or 0), 0)
    cultivation_bonus_cap = max(int(config.get("cultivation_bonus_cap") or config["cultivation_range"][1] or 0), 0)
    stone_gain = random.randint(*config["stone_range"]) + _commission_reward_bonus(
        stats,
        config.get("stone_bonus_divisors", {}),
        cap=stone_bonus_cap,
    )
    cultivation_gain = random.randint(*config["cultivation_range"]) + _commission_reward_bonus(
        stats,
        config.get("cultivation_bonus_divisors", {}),
        cap=cultivation_bonus_cap,
    )
    stone_gain = max(int(stone_gain), int(config["stone_range"][0]))
    cultivation_gain = max(int(cultivation_gain), int(config["cultivation_range"][0]))
    raw_cultivation_gain = cultivation_gain
    activity_growth = {"triggered": False, "changes": [], "patch": {}, "chance": 0, "roll": None}
    curse_event = None

    cooldown_until = None
    detail_text = random.choice(config["result_texts"])
    with Session() as session:
        row = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if row is None or not row.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        assert_profile_alive(row, config["name"])
        if _is_retreating(row):
            raise ValueError("闭关之中，无暇承接凡尘委托，待出关后再议。")
        last_entry = _commission_latest_entry(session, tg, config["name"])
        now = utcnow()
        if last_entry is not None:
            cooldown_until = last_entry.created_at + timedelta(hours=int(config["cooldown_hours"]))
            if cooldown_until > now:
                raise ValueError(f"{config['name']}仍在冷却中，还需 {_format_countdown(cooldown_until - now)}。")
        cultivation_gain, cultivation_meta = adjust_cultivation_gain_for_social_mode(row, raw_cultivation_gain)
        stage = normalize_realm_stage(row.realm_stage or FIRST_REALM_STAGE)
        layer, cultivation, upgraded_layers, remaining = apply_cultivation_gain(
            stage,
            int(row.realm_layer or 1),
            int(row.cultivation or 0),
            cultivation_gain,
        )
        apply_spiritual_stone_delta(
            session,
            tg,
            stone_gain,
            action_text=f"完成委托【{config['name']}】",
            enforce_currency_lock=True,
            allow_dead=False,
            apply_tribute=True,
        )
        row.realm_layer = layer
        row.cultivation = cultivation
        activity_growth = _apply_activity_stat_growth_to_profile_row(row, "commission", stats)
        curse_event = _apply_artifact_curse_backlash(
            tg,
            "commission",
            equipped_artifacts=equipped_artifacts,
            session=session,
            profile_row=row,
        )
        row.updated_at = utcnow()
        session.commit()

    growth_text = ""
    if activity_growth.get("triggered"):
        growth_text = " 属性成长：" + "、".join(
            f"{item['label']} +{item['value']}"
            for item in activity_growth.get("changes") or []
        ) + "。"
    create_journal(
        tg,
        SPIRIT_STONE_COMMISSION_ACTION,
        config["name"],
        (
            f"{detail_text} 获得 {stone_gain} 灵石，修为 +{cultivation_gain}"
            + (
                f"（避世效率 {cultivation_meta['efficiency_percent']}%，原始 {raw_cultivation_gain}）"
                if cultivation_meta.get("reduced")
                else ""
            )
            + f"。{growth_text}"
        ),
    )
    _record_artifact_curse_event(tg, curse_event)
    result = {
        "commission": {
            "key": config["key"],
            "name": config["name"],
            "stone_gain": stone_gain,
            "cultivation_gain": cultivation_gain,
            "cultivation_gain_raw": raw_cultivation_gain,
            "cultivation_efficiency_percent": int(cultivation_meta.get("efficiency_percent") or 100),
            "detail": detail_text,
            "attribute_growth": activity_growth.get("changes") or [],
        },
        "curse_event": curse_event,
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
    }
    if include_profile:
        result["profile"] = serialize_full_profile(tg)
    return result


def _coerce_float(value: Any, default: float, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    if minimum is not None:
        result = max(result, minimum)
    return round(result, 4)


def _coerce_int(value: Any, default: int, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    if minimum is not None:
        result = max(result, minimum)
    return result


ACTIVITY_STAT_GROWTH_POOLS = {
    "practice": ("bone", "comprehension", "divine_sense", "willpower", "true_yuan"),
    "commission": ("fortune", "charisma", "karma", "body_movement", "attack_power", "defense_power", "qi_blood"),
    "exploration": ("fortune", "divine_sense", "comprehension", "karma", "body_movement", "qi_blood"),
    "duel": ("willpower", "attack_power", "defense_power", "qi_blood", "true_yuan", "body_movement"),
}
ACTIVITY_STAT_GROWTH_MULTIPLIERS = {
    "bone": 1,
    "comprehension": 1,
    "divine_sense": 1,
    "fortune": 1,
    "willpower": 1,
    "charisma": 1,
    "karma": 1,
    "body_movement": 1,
    "attack_power": 1,
    "defense_power": 1,
    "qi_blood": 14,
    "true_yuan": 12,
}


def _attribute_growth_label(key: str) -> str:
    return {
        "attack_power": "攻击",
        "defense_power": "防御",
        "qi_blood": "气血",
        "true_yuan": "真元",
    }.get(key, ATTRIBUTE_LABELS.get(f"{key}_bonus", key))


def _normalize_activity_stat_growth_rules(raw: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    defaults = DEFAULT_SETTINGS["activity_stat_growth_rules"]
    source = raw if isinstance(raw, dict) else {}
    rules: dict[str, dict[str, int]] = {}
    for key, default_rule in defaults.items():
        current = source.get(key) if isinstance(source.get(key), dict) else {}
        gain_min = max(_coerce_int(current.get("gain_min"), default_rule.get("gain_min", 1), 1), 1)
        gain_max = max(_coerce_int(current.get("gain_max"), default_rule.get("gain_max", gain_min), gain_min), gain_min)
        rules[key] = {
            "chance_percent": min(max(_coerce_int(current.get("chance_percent"), default_rule.get("chance_percent", 0), 0), 0), 95),
            "gain_min": gain_min,
            "gain_max": gain_max,
            "attribute_count": min(max(_coerce_int(current.get("attribute_count"), default_rule.get("attribute_count", 1), 1), 1), 3),
        }
    return rules


def _activity_stat_growth_rules() -> dict[str, dict[str, int]]:
    return _normalize_activity_stat_growth_rules(
        get_xiuxian_settings().get("activity_stat_growth_rules", DEFAULT_SETTINGS["activity_stat_growth_rules"])
    )


def _roll_activity_stat_growth(
    activity_key: str,
    actor_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = _activity_stat_growth_rules()
    rule = rules.get(activity_key) or DEFAULT_SETTINGS["activity_stat_growth_rules"].get(activity_key) or {}
    chance_percent = max(min(int(rule.get("chance_percent") or 0), 95), 0)
    if chance_percent <= 0:
        return {"triggered": False, "changes": [], "patch": {}, "chance": 0, "roll": None}

    stats = actor_stats if isinstance(actor_stats, dict) else {}
    fortune = max(int(stats.get("fortune") or 0), 0)
    karma = max(int(stats.get("karma") or 0), 0)
    chance_roll = roll_probability_percent(
        chance_percent,
        actor_fortune=fortune + karma // 2,
        actor_weight=0.16,
        minimum=0,
        maximum=95,
    )
    if not chance_roll["success"]:
        return {"triggered": False, "changes": [], "patch": {}, "chance": chance_roll["chance"], "roll": chance_roll["roll"]}

    pool = list(ACTIVITY_STAT_GROWTH_POOLS.get(activity_key) or [])
    if not pool:
        return {"triggered": False, "changes": [], "patch": {}, "chance": chance_roll["chance"], "roll": chance_roll["roll"]}
    random.shuffle(pool)
    count = min(max(int(rule.get("attribute_count") or 1), 1), min(len(pool), 3))
    gain_min = max(int(rule.get("gain_min") or 1), 1)
    gain_max = max(int(rule.get("gain_max") or gain_min), gain_min)

    changes = []
    patch: dict[str, int] = {}
    for key in pool[:count]:
        base_delta = random.randint(gain_min, gain_max)
        actual_delta = base_delta * int(ACTIVITY_STAT_GROWTH_MULTIPLIERS.get(key, 1) or 1)
        patch[key] = int(patch.get(key, 0) or 0) + actual_delta
        changes.append(
            {
                "key": key,
                "label": _attribute_growth_label(key),
                "base_delta": base_delta,
                "value": actual_delta,
            }
        )
    return {
        "triggered": bool(changes),
        "changes": changes,
        "patch": patch,
        "chance": chance_roll["chance"],
        "roll": chance_roll["roll"],
    }


def _apply_activity_stat_growth_to_profile_row(
    profile_row: XiuxianProfile,
    activity_key: str,
    actor_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    growth = _roll_activity_stat_growth(activity_key, actor_stats)
    if not growth.get("triggered"):
        return growth
    for key, delta in (growth.get("patch") or {}).items():
        setattr(profile_row, key, int(getattr(profile_row, key, 0) or 0) + int(delta or 0))
    profile_row.updated_at = utcnow()
    return growth


def _normalize_root_quality_value_rules(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    # 后台可以覆盖灵根档位数值，但必须把缺失字段补齐成完整配置，前端展示和战斗结算才稳定。
    defaults = DEFAULT_SETTINGS["root_quality_value_rules"]
    rules = {}
    raw = raw if isinstance(raw, dict) else {}
    for name, level in ROOT_QUALITY_LEVELS.items():
        default_rule = defaults.get(name, {})
        source = raw.get(name) if isinstance(raw.get(name), dict) else {}
        rules[name] = {
            "level": level,
            "cultivation_rate": _coerce_float(source.get("cultivation_rate"), default_rule.get("cultivation_rate", 1.0), 0.1),
            "breakthrough_bonus": _coerce_int(source.get("breakthrough_bonus"), default_rule.get("breakthrough_bonus", 0)),
            "combat_factor": _coerce_float(source.get("combat_factor"), default_rule.get("combat_factor", 1.0), 0.1),
            "color": ROOT_QUALITY_COLORS[name],
        }
    return rules


def _normalize_item_quality_value_rules(raw: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    # 物品品质倍率同样按“默认值 + 管理员覆盖”归一化，避免升级后旧配置缺字段。
    defaults = DEFAULT_SETTINGS["item_quality_value_rules"]
    rules = {}
    raw = raw if isinstance(raw, dict) else {}
    for name, default_rule in defaults.items():
        source = raw.get(name) if isinstance(raw.get(name), dict) else {}
        rules[name] = {
            "artifact_multiplier": _coerce_float(source.get("artifact_multiplier"), default_rule.get("artifact_multiplier", 1.0), 0.0),
            "pill_multiplier": _coerce_float(source.get("pill_multiplier"), default_rule.get("pill_multiplier", 1.0), 0.0),
            "talisman_multiplier": _coerce_float(source.get("talisman_multiplier"), default_rule.get("talisman_multiplier", 1.0), 0.0),
        }
    return rules


def _item_quality_multiplier(item: dict[str, Any] | None, item_kind: str) -> float:
    field_map = {
        "artifact": "artifact_multiplier",
        "pill": "pill_multiplier",
        "talisman": "talisman_multiplier",
    }
    rules = _normalize_item_quality_value_rules(
        get_xiuxian_settings().get("item_quality_value_rules", DEFAULT_SETTINGS["item_quality_value_rules"])
    )
    rarity = str((item or {}).get("rarity") or "凡品").strip() or "凡品"
    fallback = rules.get("凡品", DEFAULT_SETTINGS["item_quality_value_rules"]["凡品"])
    current = rules.get(rarity, fallback)
    value = current.get(field_map[item_kind], 1.0)
    return float(1.0 if value is None else value)


def _empty_talisman_active_effects() -> dict[str, float]:
    return {key: 0.0 for key in TALISMAN_ACTIVE_EFFECT_FIELDS}


def _talisman_quality_level(talisman: dict[str, Any] | None) -> int:
    if not talisman:
        return 1
    try:
        level = int((talisman or {}).get("rarity_level") or 0)
    except (TypeError, ValueError):
        level = 0
    if level <= 0:
        level = int(get_quality_meta((talisman or {}).get("rarity")).get("level") or 1)
    return max(min(level, 7), 1)


def _clamp_talisman_percent(value: Any, *, cap: float) -> float:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(min(numeric, cap), 0.0)


def _normalize_talisman_active_effects(raw: Any) -> dict[str, float]:
    source = raw if isinstance(raw, dict) else {}
    aliases = {
        "drop_rate_bonus": "exploration_drop_bonus",
        "explore_drop_bonus": "exploration_drop_bonus",
        "explore_quantity_bonus": "exploration_quantity_bonus",
        "explore_stone_bonus": "exploration_stone_bonus",
        "explore_repeat_count": "exploration_repeat_count",
        "repeat_count": "exploration_repeat_count",
        "risk_reduce": "exploration_risk_reduce",
        "death_risk_reduce": "exploration_risk_reduce",
        "empty_reduce": "fishing_empty_reduce",
        "fish_empty_reduce": "fishing_empty_reduce",
        "fish_luck_bonus": "fishing_luck_bonus",
        "fish_quantity_bonus": "fishing_quantity_bonus",
        "craft_bonus": "craft_success_bonus",
        "craft_success_rate": "craft_success_bonus",
        "world_boss_damage_bonus": "boss_damage_bonus",
        "crit_bonus": "boss_crit_bonus",
        "stone_bonus": "practice_stone_bonus",
    }
    caps = {
        "cultivation_bonus": 28.0,
        "craft_success_bonus": 24.0,
        "exploration_drop_bonus": 32.0,
        "exploration_quantity_bonus": 35.0,
        "exploration_stone_bonus": 35.0,
        "exploration_risk_reduce": 45.0,
        "fishing_luck_bonus": 32.0,
        "fishing_empty_reduce": 28.0,
        "fishing_quantity_bonus": 35.0,
        "exploration_repeat_count": 5.0,
        "boss_damage_bonus": 55.0,
        "boss_crit_bonus": 18.0,
        "practice_stone_bonus": 35.0,
    }
    effects = _empty_talisman_active_effects()
    for key, value in source.items():
        normalized_key = aliases.get(str(key or "").strip(), str(key or "").strip())
        if normalized_key not in effects:
            continue
        effects[normalized_key] = _clamp_talisman_percent(value, cap=caps[normalized_key])
    return effects


def _infer_talisman_active_effects(talisman: dict[str, Any] | None) -> dict[str, float]:
    if not talisman:
        return _empty_talisman_active_effects()
    effects = _empty_talisman_active_effects()
    level = _talisman_quality_level(talisman)
    name_text = f"{talisman.get('name') or ''}{talisman.get('description') or ''}"
    combat_config = talisman.get("combat_config") if isinstance(talisman.get("combat_config"), dict) else {}
    skill_kinds = {
        str(item.get("kind") or "").strip()
        for key in ("skills", "passives")
        for item in (combat_config.get(key) or [])
        if isinstance(item, dict)
    }
    attack = float(talisman.get("attack_bonus") or 0)
    defense = float(talisman.get("defense_bonus") or 0)
    divine_sense = float(talisman.get("divine_sense_bonus") or 0)
    fortune = float(talisman.get("fortune_bonus") or 0)
    body_movement = float(talisman.get("body_movement_bonus") or 0)
    qi_blood = float(talisman.get("qi_blood_bonus") or 0)
    true_yuan = float(talisman.get("true_yuan_bonus") or 0)
    comprehension = float(talisman.get("comprehension_bonus") or 0)
    duel_rate = float(talisman.get("duel_rate_bonus") or 0)

    main_key = ""
    for keyword, effect_key in TALISMAN_UTILITY_KEYWORDS:
        if keyword and keyword in name_text:
            main_key = effect_key
            break
    if not main_key:
        if skill_kinds & {"shield", "guard", "heal"} or defense + qi_blood * 0.18 >= attack + body_movement:
            main_key = "exploration_risk_reduce"
        elif skill_kinds & {"dodge"} or body_movement >= max(attack, defense, divine_sense):
            main_key = "fishing_empty_reduce"
        elif skill_kinds & {"armor_break", "burn", "bleed", "extra_damage", "attack"} or attack + duel_rate * 2 >= defense + divine_sense:
            main_key = "boss_damage_bonus"
        elif divine_sense + fortune >= attack + defense:
            main_key = "exploration_drop_bonus"
        elif comprehension + true_yuan * 0.08 >= attack + defense:
            main_key = "cultivation_bonus"
        else:
            main_key = "exploration_drop_bonus"

    if main_key == "boss_damage_bonus":
        effects["boss_damage_bonus"] = min(7 + level * 3 + attack / 8 + duel_rate, 55)
        effects["boss_crit_bonus"] = min(1 + level + divine_sense / 14 + fortune / 18, 18)
    elif main_key == "exploration_risk_reduce":
        effects["exploration_risk_reduce"] = min(5 + level * 3 + defense / 6 + qi_blood / 55, 45)
        effects["exploration_stone_bonus"] = min(2 + level + fortune / 8, 35)
    elif main_key == "fishing_empty_reduce":
        effects["fishing_empty_reduce"] = min(3 + level * 2 + body_movement / 6, 28)
        effects["fishing_luck_bonus"] = min(2 + level * 2 + fortune / 4, 32)
    elif main_key == "craft_success_bonus":
        effects["craft_success_bonus"] = min(3 + level * 2 + comprehension / 5 + divine_sense / 8, 24)
    elif main_key == "cultivation_bonus":
        effects["cultivation_bonus"] = min(2 + level * 2 + comprehension / 5 + true_yuan / 80, 28)
        effects["practice_stone_bonus"] = min(level + fortune / 5, 35)
    else:
        effects["exploration_drop_bonus"] = min(4 + level * 2 + divine_sense / 5 + fortune / 8, 32)
        effects["exploration_quantity_bonus"] = min(level + fortune / 8, 35)
    if "多次探索" in name_text or "连探" in name_text:
        effects["exploration_repeat_count"] = min(2 + max(level - 4, 0), 5)

    effects["exploration_drop_bonus"] = min(effects["exploration_drop_bonus"] + divine_sense / 12 + fortune / 20, 32)
    effects["fishing_luck_bonus"] = min(effects["fishing_luck_bonus"] + fortune / 8, 32)
    effects["practice_stone_bonus"] = min(effects["practice_stone_bonus"] + max(level - 2, 0), 35)
    return {key: round(float(value), 2) for key, value in effects.items()}


def resolve_talisman_active_effects(
    profile: dict[str, Any] | None,
    talisman: dict[str, Any] | None,
) -> dict[str, float]:
    _ = profile
    if not talisman:
        return _empty_talisman_active_effects()
    combat_config = talisman.get("combat_config") if isinstance(talisman.get("combat_config"), dict) else {}
    explicit = _normalize_talisman_active_effects(
        combat_config.get("active_effects")
        if isinstance(combat_config.get("active_effects"), dict)
        else combat_config.get("utility_effects")
    )
    if any(float(value or 0) > 0 for value in explicit.values()):
        return explicit
    return _infer_talisman_active_effects(talisman)


def active_talisman_effect_summary(effects: dict[str, Any] | None) -> list[str]:
    source = effects or {}
    labels = [
        ("cultivation_bonus", "修炼"),
        ("craft_success_bonus", "炼制"),
        ("exploration_drop_bonus", "探索掉落"),
        ("exploration_quantity_bonus", "探索数量"),
        ("exploration_stone_bonus", "探索灵石"),
        ("exploration_risk_reduce", "秘境避险"),
        ("fishing_luck_bonus", "垂钓机缘"),
        ("fishing_empty_reduce", "空竿减免"),
        ("fishing_quantity_bonus", "钓获数量"),
        ("exploration_repeat_count", "多次探索"),
        ("boss_damage_bonus", "Boss伤害"),
        ("boss_crit_bonus", "Boss会心"),
        ("practice_stone_bonus", "吐纳灵石"),
    ]
    rows: list[str] = []
    for key, label in labels:
        value = float(source.get(key) or 0)
        if value <= 0:
            continue
        if key == "cultivation_bonus":
            rows.append(f"{label}+{value:g}")
        elif key == "exploration_repeat_count":
            rows.append(f"{label}×{int(value)}")
        else:
            rows.append(f"{label}+{value:g}%")
    return rows


def _normalize_artifact_curse_effects(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    actions: list[str] = []
    raw_actions = payload.get("trigger_actions")
    if isinstance(raw_actions, str):
        raw_actions = re.split(r"[\s,，、;；|/]+", raw_actions.strip())
    for item in raw_actions or []:
        action = str(item or "").strip()
        if action in CURSE_TRIGGER_ACTION_LABELS and action not in actions:
            actions.append(action)
    return {
        "label": str(payload.get("label") or "").strip() or "诅咒反噬",
        "summary": str(payload.get("summary") or "").strip(),
        "trigger_text": str(payload.get("trigger_text") or "").strip(),
        "trigger_chance_percent": max(min(_coerce_int(payload.get("trigger_chance_percent"), 0), 100), 0),
        "stone_loss_percent": max(min(_coerce_int(payload.get("stone_loss_percent"), 0), 100), 0),
        "stone_loss_min": max(_coerce_int(payload.get("stone_loss_min"), 0), 0),
        "stone_loss_cap": max(_coerce_int(payload.get("stone_loss_cap"), 0), 0),
        "dan_poison_gain": max(_coerce_int(payload.get("dan_poison_gain"), 0), 0),
        "trigger_actions": actions,
    }


def _artifact_curse_effects(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not artifact:
        return {}
    if isinstance(artifact.get("curse_effects"), dict):
        return _normalize_artifact_curse_effects(artifact.get("curse_effects"))
    combat_config = artifact.get("combat_config") if isinstance(artifact.get("combat_config"), dict) else {}
    return _normalize_artifact_curse_effects(combat_config.get("curse_effects"))


def _roll_artifact_curse_trigger(
    action: str,
    equipped_artifacts: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    triggered: dict[str, Any] | None = None
    for artifact in equipped_artifacts or []:
        curse = _artifact_curse_effects(artifact)
        chance = int(curse.get("trigger_chance_percent") or 0)
        if chance <= 0 or action not in set(curse.get("trigger_actions") or []):
            continue
        roll = random.randint(1, 100)
        if roll > chance:
            continue
        candidate = {
            "artifact": artifact,
            "curse": curse,
            "roll": roll,
        }
        if triggered is None or chance > int((triggered.get("curse") or {}).get("trigger_chance_percent") or 0):
            triggered = candidate
    return triggered


def _apply_artifact_curse_backlash(
    tg: int,
    action: str,
    *,
    equipped_artifacts: list[dict[str, Any]] | None = None,
    session: Session | None = None,
    profile_row: XiuxianProfile | None = None,
) -> dict[str, Any] | None:
    triggered = _roll_artifact_curse_trigger(action, equipped_artifacts)
    if triggered is None:
        return None

    artifact = triggered["artifact"] or {}
    curse = triggered["curse"] or {}
    own_session = session is None
    active_session = session or Session()
    try:
        profile = profile_row
        if profile is None:
            profile = active_session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.consented:
            return None

        current_stone = max(int(get_shared_spiritual_stone_total(int(tg), session=active_session, for_update=True) or 0), 0)
        stone_loss_percent = int(curse.get("stone_loss_percent") or 0)
        stone_loss_min = int(curse.get("stone_loss_min") or 0)
        stone_loss_cap = int(curse.get("stone_loss_cap") or 0)
        planned_stone_loss = 0
        if current_stone > 0 and (stone_loss_percent > 0 or stone_loss_min > 0):
            planned_stone_loss = max(int(round(current_stone * stone_loss_percent / 100.0)), stone_loss_min)
            if stone_loss_cap > 0:
                planned_stone_loss = min(planned_stone_loss, stone_loss_cap)
        actual_stone_loss = min(current_stone, max(planned_stone_loss, 0))
        if actual_stone_loss > 0:
            apply_spiritual_stone_delta(
                active_session,
                int(tg),
                -actual_stone_loss,
                action_text=f"诅咒物【{artifact.get('name') or '未知法宝'}】反噬",
                enforce_currency_lock=False,
                allow_dead=False,
                apply_tribute=False,
            )

        before_poison = max(int(profile.dan_poison or 0), 0)
        profile.dan_poison = min(before_poison + max(int(curse.get("dan_poison_gain") or 0), 0), CURSE_DAN_POISON_CAP)
        actual_poison_gain = max(int(profile.dan_poison or 0) - before_poison, 0)
        profile.updated_at = utcnow()

        if actual_stone_loss <= 0 and actual_poison_gain <= 0:
            if own_session:
                active_session.rollback()
            return None

        if own_session:
            active_session.commit()

        action_label = CURSE_TRIGGER_ACTION_LABELS.get(action, action)
        artifact_name = str(artifact.get("name") or "未知法宝").strip() or "未知法宝"
        trigger_text = str(curse.get("trigger_text") or "").strip()
        if not trigger_text:
            trigger_text = f"诅咒物【{artifact_name}】在{action_label}后忽然噬主。"
        effect_parts: list[str] = []
        if actual_stone_loss > 0:
            effect_parts.append(f"吞走 {actual_stone_loss} 灵石")
        if actual_poison_gain > 0:
            effect_parts.append(f"丹毒 +{actual_poison_gain}")
        summary = "，".join(effect_parts)
        if summary:
            message = f"{trigger_text}{summary}。"
        else:
            message = trigger_text
        return {
            "artifact_id": int(artifact.get("id") or 0),
            "artifact_name": artifact_name,
            "label": str(curse.get("label") or "诅咒反噬").strip() or "诅咒反噬",
            "action": action,
            "action_label": action_label,
            "trigger_chance_percent": int(curse.get("trigger_chance_percent") or 0),
            "roll": int(triggered.get("roll") or 0),
            "stone_loss": actual_stone_loss,
            "dan_poison_gain": actual_poison_gain,
            "message": message,
        }
    finally:
        if own_session:
            active_session.close()


def _record_artifact_curse_event(tg: int, curse_event: dict[str, Any] | None) -> None:
    if not curse_event:
        return
    create_journal(
        int(tg),
        "curse",
        str(curse_event.get("label") or "诅咒反噬"),
        str(curse_event.get("message") or "").strip() or None,
    )


def _root_quality_payload(name: str | None) -> dict[str, Any]:
    rules = _normalize_root_quality_value_rules(
        get_xiuxian_settings().get("root_quality_value_rules", DEFAULT_SETTINGS["root_quality_value_rules"])
    )
    return rules.get(name or "中品灵根", rules["中品灵根"])


def _normalized_root_quality(profile: dict[str, Any] | None) -> str:
    profile = profile or {}

    raw_quality = str(profile.get("root_quality") or "").strip()
    if raw_quality in ROOT_QUALITY_LEVELS:
        return raw_quality
    if raw_quality == "地灵根":
        return "极品灵根"

    try:
        quality_level = int(profile.get("root_quality_level") or 0)
    except (TypeError, ValueError):
        quality_level = 0
    if quality_level > 0:
        for name, level in ROOT_QUALITY_LEVELS.items():
            if level == quality_level:
                return name

    root_type = str(profile.get("root_type") or "").strip()
    relation = str(profile.get("root_relation") or "").strip()
    try:
        root_bonus = int(profile.get("root_bonus") or 0)
    except (TypeError, ValueError):
        root_bonus = 0

    if root_type == "天灵根" or root_bonus >= ROOT_SPECIAL_BONUS["天灵根"]:
        return "天灵根"
    if root_type == "变异灵根":
        return "变异灵根"
    if root_type == "地灵根" or root_bonus >= ROOT_SPECIAL_BONUS["地灵根"]:
        return "极品灵根"
    if root_type == "双灵根":
        if relation == "相克" or root_bonus < 0:
            return "中品灵根"
        return "上品灵根"
    if root_type == "单灵根":
        return "中品灵根"
    return "中品灵根"


def _root_combat_offset(quality_level: int, root_type: str | None = None) -> int:
    baseline = int(ROOT_QUALITY_LEVELS[ROOT_COMBAT_BASELINE_QUALITY])
    offset = max(min(int(quality_level or baseline) - baseline, 2), -2)
    if str(root_type or "").strip() in {"天灵根", "变异灵根"}:
        offset += 1
    return offset


def _resolved_root_combat_factor(
    profile: dict[str, Any],
    quality_payload: dict[str, Any],
    opponent_profile: dict[str, Any] | None = None,
) -> float:
    factor = float(quality_payload.get("combat_factor", 1.0) or 1.0)
    factor = max(min(factor, ROOT_COMBAT_FACTOR_MAX), ROOT_COMBAT_FACTOR_MIN)
    if opponent_profile:
        factor += _root_element_duel_modifier(profile, opponent_profile) * ROOT_ELEMENT_FACTOR_WEIGHT
    if str(profile.get("root_type") or "").strip() == "变异灵根":
        factor += ROOT_VARIANT_FACTOR_BONUS
    return max(factor, 0.9)


def _roll_root_quality() -> str:
    roll = random.randint(1, 100)
    cursor = 0
    for name, weight in ROOT_QUALITY_ROLLS:
        cursor += weight
        if roll <= cursor:
            return name
    return "中品灵根"


def _profile_root_elements(profile: dict[str, Any]) -> list[str]:
    elements = []
    primary = str(profile.get("root_primary") or "").strip()
    secondary = str(profile.get("root_secondary") or "").strip()
    if primary:
        elements.append(primary)
    if secondary and secondary != primary:
        elements.append(secondary)
    return elements


def _sum_item_stats(*effect_sets: dict[str, Any] | None) -> dict[str, float]:
    totals = {key: 0.0 for key in ITEM_STAT_FIELDS}
    for effects in effect_sets:
        for key in totals:
            totals[key] += float((effects or {}).get(key, 0) or 0)
    return totals


def _build_opening_stats(root_payload: dict[str, Any]) -> dict[str, int]:
    quality = _root_quality_payload(root_payload.get("root_quality"))
    quality_level = int(quality["level"])
    root_type = str(root_payload.get("root_type") or "").strip()
    root_quality = str(root_payload.get("root_quality") or "").strip()
    root_offset = _root_combat_offset(quality_level, root_type)
    fortune_special = 1 if root_type in {"地灵根", "天灵根", "变异灵根"} else 0
    will_special = 1 if root_type in {"地灵根", "天灵根"} else 0
    karma_special = 1 if root_quality in {"上品灵根", "极品灵根", "天灵根", "变异灵根"} else 0
    bone = random.randint(11, 16) + root_offset
    comprehension = random.randint(11, 16) + root_offset
    divine_sense = random.randint(10, 15) + root_offset + (2 if root_payload.get("root_primary") in {"水", "雷", "风"} else 0)
    fortune = random.randint(9, 14) + max(root_offset, 0) + fortune_special
    willpower = random.randint(9, 14) + max(root_offset, 0) // 2 + will_special
    charisma = random.randint(9, 14) + (2 if root_payload.get("root_primary") in {"木", "水", "风"} else 0)
    karma = random.randint(9, 14) + max(root_offset, 0) + karma_special
    body_movement = random.randint(9, 14) + root_offset + (2 if root_payload.get("root_primary") in {"风", "火", "雷"} else 0)
    attack_power = random.randint(14, 19) + root_offset + (3 if root_payload.get("root_primary") in {"火", "金", "雷"} else 0)
    defense_power = random.randint(14, 19) + root_offset + (3 if root_payload.get("root_primary") in {"土", "金", "水"} else 0)
    qi_blood = 240 + bone * 13 + defense_power * 6 + random.randint(0, 40) + max(root_offset, 0) * 12
    true_yuan = 220 + comprehension * 10 + divine_sense * 7 + random.randint(0, 36) + max(root_offset, 0) * 10
    return {
        "bone": bone,
        "comprehension": comprehension,
        "divine_sense": divine_sense,
        "fortune": fortune,
        "willpower": willpower,
        "charisma": charisma,
        "karma": karma,
        "qi_blood": qi_blood,
        "true_yuan": true_yuan,
        "body_movement": body_movement,
        "attack_power": attack_power,
        "defense_power": defense_power,
    }


def _realm_progress_score(stage: str | None, layer: int | None) -> int:
    return max(realm_index(stage), 0) * 9 + max(int(layer or 1), 1) - 1


def _profile_layer_progress(profile: dict[str, Any]) -> tuple[int, float, float]:
    stage = normalize_realm_stage(profile.get("realm_stage") or FIRST_REALM_STAGE)
    layer = max(int(profile.get("realm_layer") or 1), 1)
    threshold = max(cultivation_threshold(stage, layer), 1)
    current_cultivation = min(max(int(profile.get("cultivation") or 0), 0), threshold)
    progress_ratio = current_cultivation / threshold
    # 把当前层内修为折算成连续层进度，保证同层修炼时数值平滑增长，升层后不会回落。
    layer_progress_value = max(layer - 1, 0) + progress_ratio
    return layer, progress_ratio, layer_progress_value


def _profile_growth_floor(profile: dict[str, Any]) -> dict[str, int]:
    quality = _root_quality_payload(_normalized_root_quality(profile))
    quality_level = int(quality["level"])
    quality_name = _normalized_root_quality(profile)
    root_type = str(profile.get("root_type") or "").strip()
    primary = str(profile.get("root_primary") or "").strip()
    stage_index = max(realm_index(profile.get("realm_stage")), 0)
    layer, progress_ratio, layer_progress = _profile_layer_progress(profile)
    layer_progress_half = int(layer_progress // 2)
    layer_progress_third = int(layer_progress // 3)
    layer_progress_full = int(layer_progress)
    root_offset = _root_combat_offset(quality_level, root_type)
    fortune_special = 1 if root_type in {"地灵根", "天灵根", "变异灵根"} else 0
    will_special = 1 if root_type in {"地灵根", "天灵根"} else 0
    karma_special = 1 if quality_name in {"上品灵根", "极品灵根", "天灵根", "变异灵根"} else 0
    bone = 11 + stage_index * 5 + layer_progress_half + root_offset + (2 if primary in {"土", "金"} else 0)
    comprehension = 11 + stage_index * 5 + layer_progress_half + root_offset + (2 if primary in {"木", "水"} else 0)
    divine_sense = 10 + stage_index * 5 + layer_progress_third + root_offset + (2 if primary in {"雷", "风", "水"} else 0)
    fortune = 9 + stage_index * 4 + layer_progress_third + max(root_offset, 0) + fortune_special
    willpower = 9 + stage_index * 4 + layer_progress_half + max(root_offset, 0) // 2 + will_special
    charisma = 9 + stage_index * 4 + layer_progress_third + (2 if primary in {"木", "水", "风"} else 0)
    karma = 9 + stage_index * 4 + layer_progress_half + max(root_offset, 0) + karma_special
    attack_power = 14 + stage_index * 10 + layer_progress_full * 2 + root_offset + (3 if primary in {"火", "金", "雷"} else 0)
    defense_power = 14 + stage_index * 10 + layer_progress_full * 2 + root_offset + (3 if primary in {"土", "金", "水"} else 0)
    body_movement = 9 + stage_index * 5 + layer_progress_half + root_offset + (2 if primary in {"风", "火", "雷"} else 0)
    qi_blood = 240 + bone * 15 + defense_power * 7 + stage_index * 200 + int(round((layer + progress_ratio) * 30)) + max(root_offset, 0) * 12
    true_yuan = 220 + comprehension * 11 + divine_sense * 9 + stage_index * 180 + int(round((layer + progress_ratio) * 28)) + max(root_offset, 0) * 10
    return {
        "bone": bone,
        "comprehension": comprehension,
        "divine_sense": divine_sense,
        "fortune": fortune,
        "willpower": willpower,
        "charisma": charisma,
        "karma": karma,
        "qi_blood": qi_blood,
        "true_yuan": true_yuan,
        "body_movement": body_movement,
        "attack_power": attack_power,
        "defense_power": defense_power,
    }


def _major_breakthrough_reward_patch(profile: XiuxianProfile | dict[str, Any], next_stage: str) -> dict[str, int]:
    payload = serialize_profile(profile) if not isinstance(profile, dict) else dict(profile)
    stage_index = max(realm_index(next_stage), 0)
    immortal_boundary = max(realm_index("人仙"), 0)
    immortal_bonus = 1 if stage_index >= immortal_boundary else 0
    basic_gain = 1 + stage_index // 5 + immortal_bonus
    perception_gain = 1 + stage_index // 6 + immortal_bonus
    fortune_gain = 1 + stage_index // 7
    willpower_gain = 1 + stage_index // 6 + immortal_bonus
    charisma_gain = 1 if stage_index >= 3 else 0
    karma_gain = 1 + stage_index // 8 + (1 if stage_index >= max(realm_index("渡劫"), 0) else 0)
    combat_gain = 2 + stage_index // 4 + immortal_bonus
    movement_gain = 1 + stage_index // 6 + immortal_bonus
    vitality_gain = 24 + stage_index * 8 + immortal_bonus * 16
    mana_gain = 20 + stage_index * 7 + immortal_bonus * 14
    return {
        "bone": int(payload.get("bone") or 0) + basic_gain,
        "comprehension": int(payload.get("comprehension") or 0) + basic_gain,
        "divine_sense": int(payload.get("divine_sense") or 0) + perception_gain,
        "fortune": int(payload.get("fortune") or 0) + fortune_gain,
        "willpower": int(payload.get("willpower") or 0) + willpower_gain,
        "charisma": int(payload.get("charisma") or 0) + charisma_gain,
        "karma": int(payload.get("karma") or 0) + karma_gain,
        "qi_blood": int(payload.get("qi_blood") or 0) + vitality_gain,
        "true_yuan": int(payload.get("true_yuan") or 0) + mana_gain,
        "body_movement": int(payload.get("body_movement") or 0) + movement_gain,
        "attack_power": int(payload.get("attack_power") or 0) + combat_gain,
        "defense_power": int(payload.get("defense_power") or 0) + combat_gain,
    }


BREAKTHROUGH_PROTECTED_STATS = (
    "bone",
    "comprehension",
    "divine_sense",
    "fortune",
    "willpower",
    "charisma",
    "karma",
    "qi_blood",
    "true_yuan",
    "body_movement",
    "attack_power",
    "defense_power",
)

BREAKTHROUGH_PROTECTED_ITEM_BONUS_FIELDS = {
    "bone": "bone_bonus",
    "comprehension": "comprehension_bonus",
    "divine_sense": "divine_sense_bonus",
    "fortune": "fortune_bonus",
    "qi_blood": "qi_blood_bonus",
    "true_yuan": "true_yuan_bonus",
    "body_movement": "body_movement_bonus",
    "attack_power": "attack_bonus",
    "defense_power": "defense_bonus",
}


def _stabilize_breakthrough_patch(
    profile: dict[str, Any],
    next_stage: str,
    breakthrough_patch: dict[str, int],
    artifact_effects: dict[str, Any] | None = None,
    talisman_effects: dict[str, Any] | None = None,
    sect_effects: dict[str, Any] | None = None,
    technique_effects: dict[str, Any] | None = None,
    title_effects: dict[str, Any] | None = None,
) -> dict[str, int]:
    before_stats = _effective_stats(profile, artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)
    after_profile = dict(profile)
    after_profile.update(breakthrough_patch)
    after_profile["realm_stage"] = next_stage
    after_profile["realm_layer"] = 1
    after_profile["cultivation"] = 0
    after_stats = _effective_stats(after_profile, artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)
    totals = _sum_item_stats(artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)

    # 大境界突破会重置层内进度，这里把有效属性拉回到突破前下限以上，避免任何核心项回退。
    stabilized_patch = dict(breakthrough_patch)
    for key in BREAKTHROUGH_PROTECTED_STATS:
        before_value = float(before_stats.get(key) or 0.0)
        after_value = float(after_stats.get(key) or 0.0)
        if after_value >= before_value:
            continue
        bonus_field = BREAKTHROUGH_PROTECTED_ITEM_BONUS_FIELDS.get(key)
        static_bonus = float(totals.get(bonus_field, 0.0) or 0.0) if bonus_field else 0.0
        minimum_base = int(ceil(before_value - static_bonus))
        current_base = int(after_profile.get(key) or 0)
        if minimum_base <= current_base:
            continue
        stabilized_patch[key] = minimum_base
        after_profile[key] = minimum_base
    return stabilized_patch


def _apply_profile_growth_floor(tg: int, explicit_fields: set[str] | None = None) -> dict[str, Any]:
    profile = serialize_profile(get_profile(tg, create=False))
    if profile is None or not profile.get("consented"):
        raise ValueError("玩家不存在")
    explicit = set(explicit_fields or set())
    patch = {}
    for key, minimum in _profile_growth_floor(profile).items():
        if key in explicit:
            continue
        current = int(profile.get(key) or 0)
        if current < minimum:
            patch[key] = minimum
    if not patch:
        return profile
    updated = upsert_profile(tg, **patch)
    return serialize_profile(updated)


def _effective_stats(
    profile: dict[str, Any],
    artifact_effects: dict[str, Any] | None = None,
    talisman_effects: dict[str, Any] | None = None,
    sect_effects: dict[str, Any] | None = None,
    technique_effects: dict[str, Any] | None = None,
    title_effects: dict[str, Any] | None = None,
) -> dict[str, float]:
    totals = _sum_item_stats(artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)
    growth_floor = _profile_growth_floor(profile)
    stats = {
        "bone": max(float(profile.get("bone", 0) or 0), float(growth_floor["bone"])) + totals["bone_bonus"],
        "comprehension": max(float(profile.get("comprehension", 0) or 0), float(growth_floor["comprehension"])) + totals["comprehension_bonus"],
        "divine_sense": max(float(profile.get("divine_sense", 0) or 0), float(growth_floor["divine_sense"])) + totals["divine_sense_bonus"],
        "fortune": max(float(profile.get("fortune", 0) or 0), float(growth_floor["fortune"])) + totals["fortune_bonus"],
        "willpower": max(float(profile.get("willpower", 0) or 0), float(growth_floor["willpower"])),
        "charisma": max(float(profile.get("charisma", 0) or 0), float(growth_floor["charisma"])),
        "karma": max(float(profile.get("karma", 0) or 0), float(growth_floor["karma"])),
        "qi_blood": max(float(profile.get("qi_blood", 0) or 0), float(growth_floor["qi_blood"])) + totals["qi_blood_bonus"],
        "true_yuan": max(float(profile.get("true_yuan", 0) or 0), float(growth_floor["true_yuan"])) + totals["true_yuan_bonus"],
        "body_movement": max(float(profile.get("body_movement", 0) or 0), float(growth_floor["body_movement"])) + totals["body_movement_bonus"],
        "attack_power": max(float(profile.get("attack_power", 0) or 0), float(growth_floor["attack_power"])) + totals["attack_bonus"],
        "defense_power": max(float(profile.get("defense_power", 0) or 0), float(growth_floor["defense_power"])) + totals["defense_bonus"],
        "duel_rate_bonus": totals["duel_rate_bonus"],
        "cultivation_bonus": totals["cultivation_bonus"],
    }
    stats["qi_blood"] = max(stats["qi_blood"], 1.0)
    stats["true_yuan"] = max(stats["true_yuan"], 1.0)
    return stats


def resolve_technique_effects(
    profile: dict[str, Any],
    technique: dict[str, Any] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> dict[str, float]:
    if technique is None:
        return {
            "attack_bonus": 0.0,
            "defense_bonus": 0.0,
            "bone_bonus": 0.0,
            "comprehension_bonus": 0.0,
            "divine_sense_bonus": 0.0,
            "fortune_bonus": 0.0,
            "qi_blood_bonus": 0.0,
            "true_yuan_bonus": 0.0,
            "body_movement_bonus": 0.0,
            "duel_rate_bonus": 0.0,
            "cultivation_bonus": 0.0,
            "breakthrough_bonus": 0.0,
        }
    return {
        "attack_bonus": float(technique.get("attack_bonus", 0) or 0),
        "defense_bonus": float(technique.get("defense_bonus", 0) or 0),
        "bone_bonus": float(technique.get("bone_bonus", 0) or 0),
        "comprehension_bonus": float(technique.get("comprehension_bonus", 0) or 0),
        "divine_sense_bonus": float(technique.get("divine_sense_bonus", 0) or 0),
        "fortune_bonus": float(technique.get("fortune_bonus", 0) or 0),
        "qi_blood_bonus": float(technique.get("qi_blood_bonus", 0) or 0),
        "true_yuan_bonus": float(technique.get("true_yuan_bonus", 0) or 0),
        "body_movement_bonus": float(technique.get("body_movement_bonus", 0) or 0),
        "duel_rate_bonus": float(technique.get("duel_rate_bonus", 0) or 0),
        "cultivation_bonus": float(technique.get("cultivation_bonus", 0) or 0),
        "breakthrough_bonus": float(technique.get("breakthrough_bonus", 0) or 0),
    }


def resolve_title_effects(
    profile: dict[str, Any],
    title: dict[str, Any] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> dict[str, float]:
    if title is None:
        return {
            "attack_bonus": 0.0,
            "defense_bonus": 0.0,
            "bone_bonus": 0.0,
            "comprehension_bonus": 0.0,
            "divine_sense_bonus": 0.0,
            "fortune_bonus": 0.0,
            "qi_blood_bonus": 0.0,
            "true_yuan_bonus": 0.0,
            "body_movement_bonus": 0.0,
            "duel_rate_bonus": 0.0,
            "cultivation_bonus": 0.0,
            "breakthrough_bonus": 0.0,
        }
    return {
        "attack_bonus": float(title.get("attack_bonus", 0) or 0),
        "defense_bonus": float(title.get("defense_bonus", 0) or 0),
        "bone_bonus": float(title.get("bone_bonus", 0) or 0),
        "comprehension_bonus": float(title.get("comprehension_bonus", 0) or 0),
        "divine_sense_bonus": float(title.get("divine_sense_bonus", 0) or 0),
        "fortune_bonus": float(title.get("fortune_bonus", 0) or 0),
        "qi_blood_bonus": float(title.get("qi_blood_bonus", 0) or 0),
        "true_yuan_bonus": float(title.get("true_yuan_bonus", 0) or 0),
        "body_movement_bonus": float(title.get("body_movement_bonus", 0) or 0),
        "duel_rate_bonus": float(title.get("duel_rate_bonus", 0) or 0),
        "cultivation_bonus": float(title.get("cultivation_bonus", 0) or 0),
        "breakthrough_bonus": float(title.get("breakthrough_bonus", 0) or 0),
    }


def _root_element_duel_modifier(attacker: dict[str, Any], defender: dict[str, Any]) -> float:
    attacker_elements = _profile_root_elements(attacker)
    defender_elements = _profile_root_elements(defender)
    modifier = 0.0
    for own in attacker_elements:
        for rival in defender_elements:
            if ELEMENT_CONTROLS.get(own) == rival:
                modifier += 0.025
            if ELEMENT_CONTROLS.get(rival) == own:
                modifier -= 0.025
            if ELEMENT_GENERATES.get(own) == rival:
                modifier += 0.01
            if ELEMENT_GENERATES.get(rival) == own:
                modifier -= 0.01
    return max(min(modifier, 0.08), -0.08)

def resolve_artifact_effects(
    profile: dict[str, Any],
    artifact: dict[str, Any] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> dict[str, float]:
    if artifact is None:
        return {
            "attack_bonus": 0.0,
            "defense_bonus": 0.0,
            "bone_bonus": 0.0,
            "comprehension_bonus": 0.0,
            "divine_sense_bonus": 0.0,
            "fortune_bonus": 0.0,
            "qi_blood_bonus": 0.0,
            "true_yuan_bonus": 0.0,
            "body_movement_bonus": 0.0,
            "duel_rate_bonus": 0.0,
            "cultivation_bonus": 0.0,
        }
    multiplier = _item_quality_multiplier(artifact, "artifact")
    return {
        "attack_bonus": float(artifact.get("attack_bonus", 0) or 0) * multiplier,
        "defense_bonus": float(artifact.get("defense_bonus", 0) or 0) * multiplier,
        "bone_bonus": float(artifact.get("bone_bonus", 0) or 0) * multiplier,
        "comprehension_bonus": float(artifact.get("comprehension_bonus", 0) or 0) * multiplier,
        "divine_sense_bonus": float(artifact.get("divine_sense_bonus", 0) or 0) * multiplier,
        "fortune_bonus": float(artifact.get("fortune_bonus", 0) or 0) * multiplier,
        "qi_blood_bonus": float(artifact.get("qi_blood_bonus", 0) or 0) * multiplier,
        "true_yuan_bonus": float(artifact.get("true_yuan_bonus", 0) or 0) * multiplier,
        "body_movement_bonus": float(artifact.get("body_movement_bonus", 0) or 0) * multiplier,
        "duel_rate_bonus": float(artifact.get("duel_rate_bonus", 0) or 0) * multiplier,
        "cultivation_bonus": float(artifact.get("cultivation_bonus", 0) or 0) * multiplier,
    }


def resolve_talisman_effects(
    profile: dict[str, Any],
    talisman: dict[str, Any] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> dict[str, float]:
    if talisman is None:
        return {
            "attack_bonus": 0.0,
            "defense_bonus": 0.0,
            "bone_bonus": 0.0,
            "comprehension_bonus": 0.0,
            "divine_sense_bonus": 0.0,
            "fortune_bonus": 0.0,
            "qi_blood_bonus": 0.0,
            "true_yuan_bonus": 0.0,
            "body_movement_bonus": 0.0,
            "duel_rate_bonus": 0.0,
        }
    multiplier = _item_quality_multiplier(talisman, "talisman")
    return {
        "attack_bonus": float(talisman.get("attack_bonus", 0) or 0) * multiplier,
        "defense_bonus": float(talisman.get("defense_bonus", 0) or 0) * multiplier,
        "bone_bonus": float(talisman.get("bone_bonus", 0) or 0) * multiplier,
        "comprehension_bonus": float(talisman.get("comprehension_bonus", 0) or 0) * multiplier,
        "divine_sense_bonus": float(talisman.get("divine_sense_bonus", 0) or 0) * multiplier,
        "fortune_bonus": float(talisman.get("fortune_bonus", 0) or 0) * multiplier,
        "qi_blood_bonus": float(talisman.get("qi_blood_bonus", 0) or 0) * multiplier,
        "true_yuan_bonus": float(talisman.get("true_yuan_bonus", 0) or 0) * multiplier,
        "body_movement_bonus": float(talisman.get("body_movement_bonus", 0) or 0) * multiplier,
        "duel_rate_bonus": float(talisman.get("duel_rate_bonus", 0) or 0) * multiplier,
    }


def resolve_pill_effects(
    profile: dict[str, Any],
    pill: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, float]:
    if pill is None:
        return {
            "effect_value": 0.0,
            "poison_delta": 0.0,
            "success_rate_bonus": 0.0,
            "clear_poison": 0.0,
            "cultivation_gain": 0.0,
            "stone_gain": 0.0,
            "insight_gain": 0.0,
            "attack_bonus": 0.0,
            "defense_bonus": 0.0,
            "bone_bonus": 0.0,
            "comprehension_bonus": 0.0,
            "divine_sense_bonus": 0.0,
            "fortune_bonus": 0.0,
            "willpower_bonus": 0.0,
            "charisma_bonus": 0.0,
            "karma_bonus": 0.0,
            "qi_blood_bonus": 0.0,
            "true_yuan_bonus": 0.0,
            "body_movement_bonus": 0.0,
            "root_quality_gain": 0.0,
            "root_quality_floor": 0.0,
        }
    pill_type = pill.get("pill_type")
    multiplier = _item_quality_multiplier(pill, "pill")
    base_effect_value = max(float(pill.get("effect_value", 0) or 0) * multiplier, 0.0)
    payload = {
        "effect_value": base_effect_value,
        "poison_delta": float(pill.get("poison_delta", 0) or 0),
        "success_rate_bonus": 0.0,
        "clear_poison": base_effect_value if pill_type == "clear_poison" else 0.0,
        "cultivation_gain": base_effect_value if pill_type == "cultivation" else 0.0,
        "stone_gain": 0.0,
        "insight_gain": 0.0,
        "attack_bonus": float(pill.get("attack_bonus", 0) or 0) * multiplier,
        "defense_bonus": float(pill.get("defense_bonus", 0) or 0) * multiplier,
        "bone_bonus": float(pill.get("bone_bonus", 0) or 0) * multiplier,
        "comprehension_bonus": float(pill.get("comprehension_bonus", 0) or 0) * multiplier,
        "divine_sense_bonus": float(pill.get("divine_sense_bonus", 0) or 0) * multiplier,
        "fortune_bonus": float(pill.get("fortune_bonus", 0) or 0) * multiplier,
        "willpower_bonus": 0.0,
        "charisma_bonus": 0.0,
        "karma_bonus": 0.0,
        "qi_blood_bonus": float(pill.get("qi_blood_bonus", 0) or 0) * multiplier,
        "true_yuan_bonus": float(pill.get("true_yuan_bonus", 0) or 0) * multiplier,
        "body_movement_bonus": float(pill.get("body_movement_bonus", 0) or 0) * multiplier,
        "root_quality_gain": 0.0,
        "root_quality_floor": 0.0,
    }
    if pill_type == "foundation":
        payload["success_rate_bonus"] = base_effect_value
    elif pill_type == "bone":
        payload["bone_bonus"] += base_effect_value
    elif pill_type == "comprehension":
        payload["comprehension_bonus"] += base_effect_value
    elif pill_type == "divine_sense":
        payload["divine_sense_bonus"] += base_effect_value
    elif pill_type == "fortune":
        payload["fortune_bonus"] += base_effect_value
    elif pill_type == "willpower":
        payload["willpower_bonus"] += base_effect_value
    elif pill_type == "charisma":
        payload["charisma_bonus"] += base_effect_value
    elif pill_type == "karma":
        payload["karma_bonus"] += base_effect_value
    elif pill_type == "qi_blood":
        payload["qi_blood_bonus"] += base_effect_value
    elif pill_type == "true_yuan":
        payload["true_yuan_bonus"] += base_effect_value
    elif pill_type == "body_movement":
        payload["body_movement_bonus"] += base_effect_value
    elif pill_type == "attack":
        payload["attack_bonus"] += base_effect_value
    elif pill_type == "defense":
        payload["defense_bonus"] += base_effect_value
    elif pill_type == "root_refine":
        payload["root_quality_gain"] = max(base_effect_value, 0.0)
    elif pill_type == "root_remold":
        payload["root_quality_floor"] = max(base_effect_value, 0.0)
    return payload


def _pill_usage_reason(profile_data: dict[str, Any], pill: dict[str, Any]) -> str:
    if not realm_requirement_met(profile_data, pill.get("min_realm_stage"), pill.get("min_realm_layer")):
        return f"需要达到 {format_realm_requirement(pill.get('min_realm_stage'), pill.get('min_realm_layer'))} 才能服用这枚丹药。"
    pill_type = str(pill.get("pill_type") or "").strip()
    if pill_type == "stone":
        return "灵石收益类丹药已删除，当前无法服用。"
    if pill_type == "foundation":
        return "破境丹只能在对应的大境界突破时配合使用。"
    fortune_reason = _fortune_pill_usage_reason(profile_data, pill)
    if fortune_reason:
        return fortune_reason
    if pill_type == "root_refine":
        effects = resolve_pill_effects(profile_data, pill)
        steps = max(int(round(float(effects.get("root_quality_gain", 0) or 0))), 0)
        current_quality = _normalized_root_quality(profile_data)
        if current_quality in ROOT_SPECIAL_QUALITIES:
            return "当前已是特殊灵根，无法再用此丹淬炼。"
        if steps <= 0:
            return "这枚淬灵丹没有可生效的品阶。"
        if _refined_root_payload(profile_data, steps) is None:
            return "当前灵根品质已达可淬炼上限。"
    if pill_type in ROOT_TRANSFORM_PILL_TYPES:
        if _transformed_root_payload(profile_data, pill_type, pill.get("effect_value")) is None:
            return "这枚丹药当前无法改变你的灵根。"
    return ""


def _pill_supports_batch_use(pill: dict[str, Any] | None) -> bool:
    pill_type = str((pill or {}).get("pill_type") or "").strip()
    return pill_type in PILL_BATCH_USE_TYPES


def _pill_batch_use_note(pill: dict[str, Any] | None) -> str:
    pill_type = str((pill or {}).get("pill_type") or "").strip()
    if pill_type == "fortune":
        return "这类丹药支持按数量连续服用，但机缘只提升到当前境界丹药上限。"
    if pill_type in PILL_BATCH_USE_TYPES:
        return "这类丹药支持按数量连续服用。"
    if pill_type == "foundation":
        return "破境丹需要配合突破，当前仅支持单次服用。"
    if pill_type == "root_refine" or pill_type == "root_remold" or pill_type in ROOT_TRANSFORM_PILL_TYPES:
        return "灵根改造类丹药会改变当前状态，当前仅支持单次服用。"
    return "当前仅支持单次服用。"


def _pill_effect_summary(before_profile: dict[str, Any], after_profile: dict[str, Any]) -> str:
    parts: list[str] = []
    before_root = format_root(before_profile)
    after_root = format_root(after_profile)
    before_stage = normalize_realm_stage(before_profile.get("realm_stage") or FIRST_REALM_STAGE)
    after_stage = normalize_realm_stage(after_profile.get("realm_stage") or FIRST_REALM_STAGE)
    before_layer = max(int(before_profile.get("realm_layer") or 1), 1)
    after_layer = max(int(after_profile.get("realm_layer") or 1), 1)

    def cultivation_progress_total(profile: dict[str, Any]) -> int:
        stage = normalize_realm_stage(profile.get("realm_stage") or FIRST_REALM_STAGE)
        layer = max(int(profile.get("realm_layer") or 1), 1)
        cultivation = max(int(profile.get("cultivation") or 0), 0)
        total = cultivation
        for current_layer in range(1, layer):
            total += cultivation_threshold(stage, current_layer)
        return total

    if before_root != after_root:
        parts.append(f"灵根：{before_root} -> {after_root}")
    if before_stage != after_stage or before_layer != after_layer:
        parts.append(f"境界：{before_stage}{before_layer}层 -> {after_stage}{after_layer}层")
    cultivation_delta = (
        cultivation_progress_total(after_profile) - cultivation_progress_total(before_profile)
        if before_stage == after_stage
        else int(after_profile.get("cultivation") or 0) - int(before_profile.get("cultivation") or 0)
    )
    if cultivation_delta:
        parts.append(f"修为 {'+' if cultivation_delta > 0 else ''}{cultivation_delta}")
    for key in (
        "spiritual_stone",
        "bone",
        "comprehension",
        "divine_sense",
        "fortune",
        "willpower",
        "charisma",
        "karma",
        "qi_blood",
        "true_yuan",
        "body_movement",
        "attack_power",
        "defense_power",
        "dan_poison",
    ):
        delta = int(after_profile.get(key) or 0) - int(before_profile.get(key) or 0)
        if not delta:
            continue
        label = {
            "cultivation": "修为",
            "spiritual_stone": "灵石",
            "attack_power": "攻击",
            "defense_power": "防御",
            "dan_poison": "丹毒",
        }.get(key, ATTRIBUTE_LABELS.get(f"{key}_bonus", key))
        parts.append(f"{label} {'+' if delta > 0 else ''}{delta}")
    return "；".join(parts) if parts else "药力已经化开。"


def _profile_base_name(profile: dict[str, Any]) -> str:
    return (
        str(profile.get("display_label") or "").strip()
        or str(profile.get("display_name") or "").strip()
        or (f"@{profile['username']}" if str(profile.get("username") or "").strip() else f"TG {profile.get('tg', 0)}")
    )


def _profile_title_name(profile: dict[str, Any], title: dict[str, Any] | None = None) -> str:
    if title and str(title.get("name") or "").strip():
        return str(title.get("name") or "").strip()
    return str(profile.get("current_title_name") or "").strip()


def _profile_name_with_title(profile: dict[str, Any], title: dict[str, Any] | None = None) -> str:
    base_name = _profile_base_name(profile)
    title_name = _profile_title_name(profile, title)
    if not title_name:
        return base_name
    return f"「{title_name}」{base_name}"


def _artifact_effect_template() -> dict[str, float]:
    return {
        "attack_bonus": 0.0,
        "defense_bonus": 0.0,
        "bone_bonus": 0.0,
        "comprehension_bonus": 0.0,
        "divine_sense_bonus": 0.0,
        "fortune_bonus": 0.0,
        "qi_blood_bonus": 0.0,
        "true_yuan_bonus": 0.0,
        "body_movement_bonus": 0.0,
        "duel_rate_bonus": 0.0,
        "cultivation_bonus": 0.0,
        "breakthrough_bonus": 0.0,
    }


def _artifact_set_index() -> dict[int, dict[str, Any]]:
    return {
        int(item["id"]): dict(item)
        for item in list_artifact_sets(enabled_only=True)
        if int(item.get("id") or 0) > 0
    }


def _decorate_artifact_with_set(artifact: dict[str, Any], artifact_set_map: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    if artifact_set_map is None:
        artifact_set_map = _artifact_set_index()
    set_id = int(artifact.get("artifact_set_id") or 0)
    artifact_set = dict(artifact_set_map.get(set_id) or {})
    artifact["artifact_set"] = artifact_set or None
    artifact["artifact_set_name"] = artifact_set.get("name")
    return artifact


def _artifact_set_effects(artifact_set: dict[str, Any] | None) -> dict[str, float]:
    if artifact_set is None:
        return _artifact_effect_template()
    return {
        "attack_bonus": float(artifact_set.get("attack_bonus", 0) or 0),
        "defense_bonus": float(artifact_set.get("defense_bonus", 0) or 0),
        "bone_bonus": float(artifact_set.get("bone_bonus", 0) or 0),
        "comprehension_bonus": float(artifact_set.get("comprehension_bonus", 0) or 0),
        "divine_sense_bonus": float(artifact_set.get("divine_sense_bonus", 0) or 0),
        "fortune_bonus": float(artifact_set.get("fortune_bonus", 0) or 0),
        "qi_blood_bonus": float(artifact_set.get("qi_blood_bonus", 0) or 0),
        "true_yuan_bonus": float(artifact_set.get("true_yuan_bonus", 0) or 0),
        "body_movement_bonus": float(artifact_set.get("body_movement_bonus", 0) or 0),
        "duel_rate_bonus": float(artifact_set.get("duel_rate_bonus", 0) or 0),
        "cultivation_bonus": float(artifact_set.get("cultivation_bonus", 0) or 0),
        "breakthrough_bonus": float(artifact_set.get("breakthrough_bonus", 0) or 0),
    }


def _resolve_active_artifact_sets(equipped_artifacts: list[dict[str, Any]] | None) -> dict[str, Any]:
    artifact_set_map = _artifact_set_index()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for artifact in equipped_artifacts or []:
        set_id = int(artifact.get("artifact_set_id") or 0)
        if set_id <= 0 or set_id not in artifact_set_map:
            continue
        grouped.setdefault(set_id, []).append(artifact)

    totals = _artifact_effect_template()
    sets: list[dict[str, Any]] = []
    for set_id, artifacts in grouped.items():
        artifact_set = dict(artifact_set_map[set_id])
        equipped_count = len(artifacts)
        required_count = max(int(artifact_set.get("required_count") or 2), 1)
        active = equipped_count >= required_count
        resolved_effects = _artifact_set_effects(artifact_set) if active else _artifact_effect_template()
        if active:
            for key in totals:
                totals[key] += float(resolved_effects.get(key, 0) or 0)
        artifact_set["equipped_count"] = equipped_count
        artifact_set["active"] = active
        artifact_set["artifact_names"] = [str(item.get("name") or "") for item in artifacts if str(item.get("name") or "").strip()]
        artifact_set["resolved_effects"] = resolved_effects
        sets.append(artifact_set)

    sets.sort(key=lambda item: (-int(item.get("active") or 0), -int(item.get("equipped_count") or 0), int(item.get("id") or 0)))
    return {"sets": sets, "totals": totals}


def collect_equipped_artifacts(tg: int) -> list[dict[str, Any]]:
    artifact_set_map = _artifact_set_index()
    return [_decorate_artifact_with_set(row["artifact"], artifact_set_map) for row in list_equipped_artifacts(tg)]


def _bulk_collect_equipped_artifacts(tgs: list[int] | tuple[int, ...] | set[int]) -> dict[int, list[dict[str, Any]]]:
    owner_tgs = sorted({int(tg or 0) for tg in tgs if int(tg or 0) > 0})
    if not owner_tgs:
        return {}

    artifact_set_map = _artifact_set_index()
    payload: dict[int, list[dict[str, Any]]] = {tg: [] for tg in owner_tgs}
    with Session() as session:
        rows = (
            session.query(XiuxianEquippedArtifact, XiuxianArtifact)
            .join(XiuxianArtifact, XiuxianArtifact.id == XiuxianEquippedArtifact.artifact_id)
            .filter(XiuxianEquippedArtifact.tg.in_(owner_tgs))
            .order_by(
                XiuxianEquippedArtifact.tg.asc(),
                XiuxianEquippedArtifact.slot.asc(),
                XiuxianEquippedArtifact.id.asc(),
            )
            .all()
        )

    for equipped, artifact in rows:
        owner_tg = int(equipped.tg or 0)
        if owner_tg <= 0:
            continue
        payload.setdefault(owner_tg, []).append(
            _decorate_artifact_with_set(serialize_artifact(artifact) or {}, artifact_set_map)
        )
    return payload


def merge_artifact_effects(
    profile: dict[str, Any],
    equipped_artifacts: list[dict[str, Any]] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> dict[str, float]:
    totals = _artifact_effect_template()
    for artifact in equipped_artifacts or []:
        effects = resolve_artifact_effects(profile, artifact, opponent_profile)
        for key in totals:
            totals[key] += float(effects.get(key, 0) or 0)
    active_set_bundle = _resolve_active_artifact_sets(equipped_artifacts)
    for key in totals:
        totals[key] += float((active_set_bundle.get("totals") or {}).get(key, 0) or 0)
    return totals


def build_user_artifact_rows(
    profile_data: dict[str, Any],
    tg: int,
    retreating: bool,
    equip_limit: int,
    equipped_ids: set[int],
    equipped_slot_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    artifact_set_map = _artifact_set_index()
    occupied_slots = {normalize_artifact_slot(slot) for slot in (equipped_slot_names or set()) if slot}
    rows = []
    for row in list_user_artifacts(tg):
        total_quantity = max(int(row.get("quantity") or 0), 0)
        bound_quantity = max(min(int(row.get("bound_quantity") or 0), total_quantity), 0)
        equipped_quantity = max(min(int(row.get("equipped_quantity") or 0), total_quantity - bound_quantity), 0)
        item = _decorate_artifact_with_set(row["artifact"], artifact_set_map)
        item["resolved_effects"] = resolve_artifact_effects(profile_data, item)
        item["equipped"] = int(item["id"]) in equipped_ids
        row["bound_quantity"] = bound_quantity
        row["unbound_quantity"] = max(total_quantity - bound_quantity, 0)
        row["consumable_quantity"] = max(total_quantity - bound_quantity - equipped_quantity, 0)
        row["tradeable_quantity"] = row["consumable_quantity"]
        usable = realm_requirement_met(profile_data, item.get("min_realm_stage"), item.get("min_realm_layer"))
        if usable:
            reason = ""
        else:
            reason = f"需要达到 {format_realm_requirement(item.get('min_realm_stage'), item.get('min_realm_layer'))}"
        target_slot = normalize_artifact_slot(item.get("equip_slot"))
        slot_replaceable = bool(target_slot and target_slot in occupied_slots)
        if not item["equipped"] and len(equipped_ids) >= equip_limit and not slot_replaceable:
            usable = False
            reason = f"当前最多只能装备 {equip_limit} 件法宝"
        if retreating:
            usable = False
            reason = "闭关之中，法宝已与心神相系，不可轻换。"
        item["usable"] = usable or item["equipped"]
        item["unusable_reason"] = "" if item["equipped"] else reason
        item["action_label"] = "卸下法宝" if item["equipped"] else f"装备到{item.get('equip_slot_label') or '槽位'}"
        item["bound"] = bound_quantity > 0
        item["bound_quantity"] = bound_quantity
        rows.append(row)
    return rows


def _build_user_technique_rows(profile_data: dict[str, Any], tg: int) -> list[dict[str, Any]]:
    current_id = int(profile_data.get("current_technique_id") or 0)
    rows = []
    for row in list_user_techniques(tg, enabled_only=True):
        technique = dict(row.get("technique") or {})
        if not technique:
            continue
        technique["resolved_effects"] = resolve_technique_effects(profile_data, technique)
        technique["active"] = int(technique.get("id") or 0) == current_id
        technique["source"] = row.get("source")
        technique["obtained_note"] = row.get("obtained_note")
        usable = realm_requirement_met(profile_data, technique.get("min_realm_stage"), technique.get("min_realm_layer"))
        reason = "" if usable else f"需要达到 {format_realm_requirement(technique.get('min_realm_stage'), technique.get('min_realm_layer'))}"
        technique["usable"] = usable or technique["active"]
        technique["unusable_reason"] = "" if technique["active"] else reason
        technique["action_label"] = "当前功法" if technique["active"] else "切换功法"
        rows.append(technique)
    return rows


def _current_technique_payload(profile_data: dict[str, Any]) -> dict[str, Any] | None:
    technique_id = int(profile_data.get("current_technique_id") or 0)
    if not technique_id:
        return None
    technique = serialize_technique(get_technique(technique_id))
    if not technique or not technique.get("enabled"):
        return None
    technique["resolved_effects"] = resolve_technique_effects(profile_data, technique)
    technique["active"] = True
    return technique


SEED_DATA_VERSION = "2026-05-27-xiuxian-top-tier-expansion-v2"
DEFAULT_ARTIFACT_SET_SYNC_SETTING = "default_artifact_set_sync_version"
DEFAULT_ARTIFACT_SET_SYNC_VERSION = "2026-05-12-expanded-artifact-set-links-v1"
DEFAULT_BOSS_SYNC_SETTING = "default_boss_sync_version"
DEFAULT_BOSS_SYNC_VERSION = "2026-05-09-editable-default-bosses-v1"
SEED_DATA_READY = False
SEED_DATA_LOCK = threading.RLock()
SEED_DATA_DB_LOCK_KEY = 2026041701
SEED_DATA_DB_LOCK_NAME = "echo_xiuxian_seed_data"
DEFAULT_OFFICIAL_SHOP_ITEMS = (
    {"item_kind": "artifact", "item_name": "凡铁剑", "quantity": 4},
    {"item_kind": "artifact", "item_name": "青罡剑", "quantity": 3},
    {"item_kind": "artifact", "item_name": "玄龟盾", "quantity": 3},
    {"item_kind": "artifact", "item_name": "逐云履", "quantity": 2},
    {"item_kind": "artifact", "item_name": "赤焰珠", "quantity": 2},
    {"item_kind": "artifact", "item_name": "残修青罡古剑", "quantity": 1},
    {"item_kind": "artifact", "item_name": "残修玄龟古盾", "quantity": 1},
    {"item_kind": "pill", "item_name": "筑基丹", "quantity": 10},
    {"item_kind": "pill", "item_name": "清心丹", "quantity": 12},
    {"item_kind": "pill", "item_name": "聚气丹", "quantity": 10},
    {"item_kind": "pill", "item_name": "洗髓丹", "quantity": 8},
    {"item_kind": "pill", "item_name": "悟道丹", "quantity": 8},
    {"item_kind": "pill", "item_name": "凝神丹", "quantity": 8},
    {"item_kind": "pill", "item_name": "轻灵丹", "quantity": 8},
    {"item_kind": "pill", "item_name": "血魄丹", "quantity": 6},
    {"item_kind": "pill", "item_name": "蕴元丹", "quantity": 6},
    {"item_kind": "pill", "item_name": "天运丹", "quantity": 4},
    {"item_kind": "pill", "item_name": "锐金丹", "quantity": 5},
    {"item_kind": "pill", "item_name": "护脉丹", "quantity": 5},
    {"item_kind": "talisman", "item_name": "疾风符", "quantity": 12},
    {"item_kind": "talisman", "item_name": "轻身符", "quantity": 10},
    {"item_kind": "talisman", "item_name": "雷火符", "quantity": 8},
    {"item_kind": "talisman", "item_name": "金钟符", "quantity": 8},
    {"item_kind": "talisman", "item_name": "破甲符", "quantity": 6},
    {"item_kind": "material", "item_name": "灵露滴", "quantity": 16},
    {"item_kind": "material", "item_name": "清心兰", "quantity": 10},
    {"item_kind": "material", "item_name": "风灵石", "quantity": 8},
    {"item_kind": "material", "item_name": "鬼画符骨", "quantity": 6},
    {"item_kind": "material", "item_name": "寒铁", "quantity": 6},
    {"item_kind": "material", "item_name": "太白精金", "quantity": 4},
    {"item_kind": "material", "item_name": "天师袍角", "quantity": 4},
    {"item_kind": "material", "item_name": "九幽寒莲", "quantity": 2},
    {"item_kind": "material", "item_name": "曜金雷髓", "quantity": 2},
    {"item_kind": "material", "item_name": "大道符纸", "quantity": 1},
    {"item_kind": "material", "item_name": "开天神石", "quantity": 1},
    {"item_kind": "material", "item_name": "轮回祖符", "quantity": 1},
)


def _get_seed_data_version() -> str:
    with Session() as session:
        row = session.query(XiuxianSetting).filter(XiuxianSetting.setting_key == "seed_data_version").first()
        if row is None or row.setting_value is None:
            return ""
        return str(row.setting_value).strip()


def _setting_value(setting_key: str) -> str:
    key = str(setting_key or "").strip()
    if not key:
        return ""
    with Session() as session:
        row = session.query(XiuxianSetting).filter(XiuxianSetting.setting_key == key).first()
        if row is None or row.setting_value is None:
            return ""
        return str(row.setting_value).strip()


@contextmanager
def _seed_data_db_lock(timeout_seconds: int = 60):
    connection = engine.connect()
    lock_acquired = False
    try:
        if DB_BACKEND == "postgresql":
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": SEED_DATA_DB_LOCK_KEY})
            lock_acquired = True
        elif DB_BACKEND == "mysql":
            result = connection.execute(
                text("SELECT GET_LOCK(:name, :timeout)"),
                {"name": SEED_DATA_DB_LOCK_NAME, "timeout": timeout_seconds},
            ).scalar()
            if int(result or 0) != 1:
                raise RuntimeError("修仙种子数据初始化锁获取失败，请稍后重试")
            lock_acquired = True
        yield
    finally:
        try:
            if lock_acquired and DB_BACKEND == "postgresql":
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SEED_DATA_DB_LOCK_KEY})
            elif lock_acquired and DB_BACKEND == "mysql":
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": SEED_DATA_DB_LOCK_NAME})
        finally:
            connection.close()


def _resolve_seed_result_ref_id(
    kind: str,
    name: str,
    *,
    artifact_map: dict[str, dict[str, Any]],
    pill_map: dict[str, dict[str, Any]],
    talisman_map: dict[str, dict[str, Any]],
    material_map: dict[str, dict[str, Any]],
    technique_map: dict[str, dict[str, Any]] | None = None,
    recipe_map: dict[str, dict[str, Any]] | None = None,
) -> int:
    lookup = {
        "artifact": artifact_map,
        "pill": pill_map,
        "talisman": talisman_map,
        "material": material_map,
        "technique": technique_map or {},
        "recipe": recipe_map or {},
    }.get(kind)
    if lookup is None or name not in lookup:
        raise ValueError(f"未找到默认种子引用：{kind}::{name}")
    return int(lookup[name]["id"])


def _collect_missing_seed_refs(
    refs: list[tuple[str, str]],
    *,
    artifact_map: dict[str, dict[str, Any]],
    pill_map: dict[str, dict[str, Any]],
    talisman_map: dict[str, dict[str, Any]],
    material_map: dict[str, dict[str, Any]],
    technique_map: dict[str, dict[str, Any]] | None = None,
    recipe_map: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    missing: list[str] = []
    lookup_map = {
        "artifact": artifact_map,
        "pill": pill_map,
        "talisman": talisman_map,
        "material": material_map,
        "technique": technique_map or {},
        "recipe": recipe_map or {},
    }
    for kind, name in refs:
        if name not in lookup_map.get(kind, {}):
            missing.append(f"{kind}::{name}")
    return missing


def _raise_on_missing_seed_refs(context: str, refs: list[str]) -> None:
    if not refs:
        return
    unique_refs = sorted(set(refs))
    preview = ", ".join(unique_refs[:12])
    suffix = "" if len(unique_refs) <= 12 else f" 等 {len(unique_refs)} 项"
    raise ValueError(f"{context}存在未解析引用：{preview}{suffix}")


def _default_artifact_set_links() -> dict[str, str]:
    links: dict[str, str] = {}
    for blueprint in ARTIFACT_SET_BLUEPRINTS:
        set_name = str(blueprint.get("name") or "").strip()
        if not set_name:
            continue
        for item in blueprint.get("items") or []:
            artifact_name = str((item or {}).get("name") or "").strip()
            if artifact_name:
                links[artifact_name] = set_name
    return links


def _sync_default_artifact_set_links(force: bool = False) -> None:
    if _setting_value(DEFAULT_ARTIFACT_SET_SYNC_SETTING) == DEFAULT_ARTIFACT_SET_SYNC_VERSION and not force:
        return

    default_set_map: dict[str, dict[str, Any]] = {
        str(item.get("name") or ""): item
        for item in list_artifact_sets(enabled_only=False)
    }
    for payload in DEFAULT_ARTIFACT_SETS:
        set_name = str(payload.get("name") or "").strip()
        if not set_name or set_name in default_set_map:
            continue
        artifact_set = sync_artifact_set_by_name(**payload, enabled=True)
        default_set_map[str(artifact_set.get("name") or "")] = artifact_set

    link_map = _default_artifact_set_links()
    if not link_map:
        set_xiuxian_settings({DEFAULT_ARTIFACT_SET_SYNC_SETTING: DEFAULT_ARTIFACT_SET_SYNC_VERSION})
        return

    changed = False
    with Session() as session:
        rows = (
            session.query(XiuxianArtifact)
            .filter(XiuxianArtifact.name.in_(list(link_map.keys())))
            .with_for_update()
            .all()
        )
        for row in rows:
            if int(row.artifact_set_id or 0) > 0 and not force:
                continue
            set_name = link_map.get(str(row.name or ""))
            artifact_set = default_set_map.get(str(set_name or ""))
            set_id = int((artifact_set or {}).get("id") or 0)
            if set_id <= 0 or int(row.artifact_set_id or 0) == set_id:
                continue
            row.artifact_set_id = set_id
            row.updated_at = utcnow()
            changed = True
        if changed:
            _queue_catalog_cache_invalidation(session, "artifacts", "artifact-sets")
            session.commit()
        else:
            session.rollback()

    set_xiuxian_settings({DEFAULT_ARTIFACT_SET_SYNC_SETTING: DEFAULT_ARTIFACT_SET_SYNC_VERSION})


_DEFAULT_BOSS_LOOT_MAPS = (
    ("loot_pills_json", "pill"),
    ("loot_materials_json", "material"),
    ("loot_artifacts_json", "artifact"),
    ("loot_talismans_json", "talisman"),
    ("loot_recipes_json", "recipe"),
    ("loot_techniques_json", "technique"),
)


def _resolve_default_boss_payload(
    payload: dict[str, Any],
    *,
    artifact_map: dict[str, dict[str, Any]],
    pill_map: dict[str, dict[str, Any]],
    talisman_map: dict[str, dict[str, Any]],
    material_map: dict[str, dict[str, Any]],
    technique_map: dict[str, dict[str, Any]],
    recipe_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    boss_payload = dict(payload)
    lookup_map = {
        "artifact": artifact_map,
        "pill": pill_map,
        "talisman": talisman_map,
        "material": material_map,
        "technique": technique_map,
        "recipe": recipe_map,
    }
    for loot_field, kind in _DEFAULT_BOSS_LOOT_MAPS:
        raw_rows = boss_payload.pop(loot_field, None) or []
        resolved_rows = []
        for entry in raw_rows:
            entry_name = str(entry.get("name") or "").strip()
            ref_payload = lookup_map.get(kind, {}).get(entry_name)
            if not ref_payload:
                continue
            resolved_rows.append(
                {
                    "ref_id": int(ref_payload["id"]),
                    "chance": int(entry.get("chance") or 0),
                    "quantity_min": int(entry.get("quantity_min") or 1),
                    "quantity_max": int(entry.get("quantity_max") or 1),
                }
            )
        boss_payload[loot_field] = resolved_rows
    return boss_payload


def _boss_has_configured_loot(boss: dict[str, Any] | None) -> bool:
    if not boss:
        return False
    return any(bool(boss.get(loot_field)) for loot_field, _kind in _DEFAULT_BOSS_LOOT_MAPS)


def _normalized_boss_loot_signature(boss: dict[str, Any] | None) -> tuple[tuple[str, tuple[tuple[int, int, int, int], ...]], ...]:
    if not boss:
        return ()
    signature = []
    for loot_field, _kind in _DEFAULT_BOSS_LOOT_MAPS:
        rows = []
        for row in boss.get(loot_field) or []:
            if not isinstance(row, dict):
                continue
            rows.append(
                (
                    int(row.get("ref_id") or 0),
                    int(row.get("chance") or 0),
                    int(row.get("quantity_min") or 1),
                    int(row.get("quantity_max") or row.get("quantity_min") or 1),
                )
            )
        signature.append((loot_field, tuple(sorted(rows))))
    return tuple(signature)


def _boss_has_legacy_default_loot(
    boss: dict[str, Any] | None,
    legacy_payload: dict[str, Any] | None,
    *,
    artifact_map: dict[str, dict[str, Any]],
    pill_map: dict[str, dict[str, Any]],
    talisman_map: dict[str, dict[str, Any]],
    material_map: dict[str, dict[str, Any]],
    technique_map: dict[str, dict[str, Any]],
    recipe_map: dict[str, dict[str, Any]],
) -> bool:
    if not boss or not legacy_payload:
        return False
    resolved_legacy = _resolve_default_boss_payload(
        legacy_payload,
        artifact_map=artifact_map,
        pill_map=pill_map,
        talisman_map=talisman_map,
        material_map=material_map,
        technique_map=technique_map,
        recipe_map=recipe_map,
    )
    return _normalized_boss_loot_signature(boss) == _normalized_boss_loot_signature(resolved_legacy)


def _sync_default_boss_configs(
    *,
    artifact_map: dict[str, dict[str, Any]],
    pill_map: dict[str, dict[str, Any]],
    talisman_map: dict[str, dict[str, Any]],
    material_map: dict[str, dict[str, Any]],
    technique_map: dict[str, dict[str, Any]],
    recipe_map: dict[str, dict[str, Any]],
    patch_empty_world_loot: bool = True,
) -> None:
    existing_by_name = {
        str(item.get("name") or ""): item
        for item in list_boss_configs(enabled_only=False)
        if str(item.get("name") or "").strip()
    }
    for payload in DEFAULT_BOSS_CONFIGS:
        boss_payload = _resolve_default_boss_payload(
            payload,
            artifact_map=artifact_map,
            pill_map=pill_map,
            talisman_map=talisman_map,
            material_map=material_map,
            technique_map=technique_map,
            recipe_map=recipe_map,
        )
        existing = existing_by_name.get(str(boss_payload.get("name") or ""))
        if not existing:
            created = create_boss_config(**boss_payload)
            existing_by_name[str(created.get("name") or "")] = created
            continue

        is_world_boss = str(existing.get("boss_type") or boss_payload.get("boss_type") or "") == "world"
        legacy_payload = LEGACY_WORLD_BOSS_LOOT_CONFIGS.get(str(existing.get("name") or ""))
        should_patch_loot = (
            patch_empty_world_loot
            and is_world_boss
            and (
                not _boss_has_configured_loot(existing)
                or _boss_has_legacy_default_loot(
                    existing,
                    legacy_payload,
                    artifact_map=artifact_map,
                    pill_map=pill_map,
                    talisman_map=talisman_map,
                    material_map=material_map,
                    technique_map=technique_map,
                    recipe_map=recipe_map,
                )
            )
        )
        if should_patch_loot:
            patch = {loot_field: boss_payload.get(loot_field) or [] for loot_field, _kind in _DEFAULT_BOSS_LOOT_MAPS}
            updated = patch_boss_config(int(existing.get("id") or 0), **patch)
            if updated:
                existing_by_name[str(updated.get("name") or "")] = updated


def _ensure_default_boss_configs_synced(force: bool = False) -> None:
    settings = get_xiuxian_settings()
    if settings.get(DEFAULT_BOSS_SYNC_SETTING) == DEFAULT_BOSS_SYNC_VERSION and not force:
        return
    artifact_map = {item["name"]: item for item in list_artifacts()}
    pill_map = {item["name"]: item for item in list_pills()}
    talisman_map = {item["name"]: item for item in list_talismans()}
    material_map = {item["name"]: item for item in list_materials()}
    technique_map = {item["name"]: item for item in list_techniques()}
    recipe_map = {item["name"]: item for item in list_recipes()}
    _sync_default_boss_configs(
        artifact_map=artifact_map,
        pill_map=pill_map,
        talisman_map=talisman_map,
        material_map=material_map,
        technique_map=technique_map,
        recipe_map=recipe_map,
        patch_empty_world_loot=True,
    )
    set_xiuxian_settings({DEFAULT_BOSS_SYNC_SETTING: DEFAULT_BOSS_SYNC_VERSION})


def _seed_listing_realm_markup(payload: dict[str, Any]) -> int:
    stage = str(payload.get("min_realm_stage") or "").strip()
    layer = max(int(payload.get("min_realm_layer") or 0), 0)
    stage_index = max(realm_index(stage), 0) if stage else 0
    return stage_index * 14 + layer * 4


def _seed_listing_skill_count(payload: dict[str, Any]) -> int:
    combat_config = payload.get("combat_config") or {}
    return sum(len(combat_config.get(key) or []) for key in ("skills", "passives"))


def _weighted_seed_stat_value(payload: dict[str, Any], weights: dict[str, float]) -> float:
    total = 0.0
    for key, weight in weights.items():
        total += max(float(payload.get(key) or 0), 0.0) * weight
    return total


def _seed_text_keyword_score(text: str, keyword_weights: tuple[tuple[str, float], ...]) -> float:
    source = str(text or "")
    if not source:
        return 0.0
    score = 0.0
    for keyword, weight in keyword_weights:
        if keyword and keyword in source:
            score += float(weight)
    return score


def _material_seed_attribute_score(payload: dict[str, Any]) -> float:
    source_text = " ".join(
        filter(
            None,
            [
                str(payload.get("name") or "").strip(),
                str(payload.get("description") or "").strip(),
            ],
        )
    )
    if not source_text:
        return 0.0

    offense_score = _seed_text_keyword_score(
        source_text,
        (
            ("攻伐", 3.6),
            ("杀伐", 3.4),
            ("爆发", 2.8),
            ("破甲", 2.8),
            ("锋", 1.9),
            ("锐", 1.8),
            ("雷", 1.3),
            ("火", 1.2),
            ("焰", 1.2),
            ("剑", 1.1),
            ("斧", 1.1),
            ("枪", 1.1),
        ),
    )
    defense_score = _seed_text_keyword_score(
        source_text,
        (
            ("护体", 3.4),
            ("防御", 3.0),
            ("守护", 1.8),
            ("护持", 1.7),
            ("稳固", 1.8),
            ("卸力", 1.7),
            ("盾", 1.6),
            ("甲片", 1.7),
            ("龟甲", 1.8),
            ("壁", 1.3),
            ("玄武", 2.6),
        ),
    )
    support_score = _seed_text_keyword_score(
        source_text,
        (
            ("修炼", 3.0),
            ("悟道", 3.0),
            ("凝神", 2.7),
            ("定心", 2.4),
            ("安神", 2.2),
            ("生机", 2.8),
            ("疗伤", 2.8),
            ("恢复", 2.4),
            ("温养", 2.4),
            ("神魂", 2.2),
            ("识海", 2.0),
        ),
    )
    mobility_score = _seed_text_keyword_score(
        source_text,
        (
            ("轻灵", 2.6),
            ("迅捷", 2.6),
            ("腾挪", 2.4),
            ("身法", 2.4),
            ("极速", 2.8),
            ("风", 1.2),
            ("羽", 1.0),
        ),
    )
    destiny_score = _seed_text_keyword_score(
        source_text,
        (
            ("气运", 3.0),
            ("因果", 3.2),
            ("命运", 3.6),
            ("轮回", 4.0),
            ("天道", 4.2),
            ("大道", 4.0),
            ("鸿蒙", 4.4),
            ("混沌", 4.0),
            ("本源", 4.2),
            ("创世", 4.8),
            ("开天", 4.8),
            ("至宝", 4.0),
            ("无上", 3.0),
        ),
    )
    craft_scope_score = _seed_text_keyword_score(
        source_text,
        (
            ("炼器", 2.6),
            ("炼丹", 2.6),
            ("制符", 2.6),
            ("符箓", 2.4),
            ("法宝", 2.2),
            ("丹药", 2.0),
            ("药引", 2.2),
            ("主材", 2.8),
            ("主药", 2.8),
            ("核心", 3.0),
            ("符骨", 2.4),
            ("符纸", 2.2),
            ("药材", 2.0),
        ),
    )

    trait_hits = sum(1 for value in (offense_score, defense_score, support_score, mobility_score, destiny_score) if value > 0)
    versatility_bonus = max(trait_hits - 1, 0) * 5.5
    return (
        offense_score * 1.08
        + defense_score * 1.02
        + support_score * 1.06
        + mobility_score * 1.04
        + destiny_score * 1.12
        + craft_scope_score * 1.35
        + versatility_bonus
    )


def _official_seed_item_payload(item_kind: str, item_ref_id: int) -> dict[str, Any] | None:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "artifact":
        return serialize_artifact(get_artifact(item_ref_id))
    if normalized_kind == "pill":
        return serialize_pill(get_pill(item_ref_id))
    if normalized_kind == "talisman":
        return serialize_talisman(get_talisman(item_ref_id))
    if normalized_kind == "material":
        return serialize_material(get_material(item_ref_id))
    if normalized_kind == "technique":
        return serialize_technique(get_technique(item_ref_id))
    if normalized_kind == "recipe":
        return serialize_recipe(get_recipe(item_ref_id))
    return None


def _round_seed_shop_price(value: float) -> int:
    return max(int(ceil(max(float(value), 1.0) / 5.0) * 5), 5)


def _is_immortal_stone_payload(item_kind: str, payload: dict[str, Any]) -> bool:
    return str(item_kind or "").strip() == "material" and str((payload or {}).get("name") or "").strip() == IMMORTAL_STONE_NAME


def _immortal_stone_exchange_cost() -> int:
    settings = get_xiuxian_settings()
    return max(_coerce_int(settings.get("gambling_exchange_cost_stone"), DEFAULT_SETTINGS["gambling_exchange_cost_stone"], 1), 1)


def _immortal_stone_recycle_limit() -> int:
    return max(_immortal_stone_exchange_cost() - 1, 1)


def _seed_quality_price_multiplier(level: int, *, item_kind: str) -> float:
    rarity_level = max(int(level or 1), 1)
    base_step = {
        "artifact": 0.20,
        "pill": 0.18,
        "talisman": 0.19,
        "material": 0.17,
        "technique": 0.21,
        "recipe": 0.16,
    }.get(str(item_kind or "").strip(), 0.18)
    advanced_bonus = max(rarity_level - 4, 0) * 0.05
    mythic_bonus = max(rarity_level - 6, 0) * 0.08
    return 1.0 + (rarity_level - 1) * base_step + advanced_bonus + mythic_bonus


def _artifact_seed_shop_price(payload: dict[str, Any]) -> int:
    rarity_level = max(int(payload.get("rarity_level") or 1), 1)
    type_bonus = 18 if str(payload.get("artifact_type") or "").strip() == "battle" else 12
    unique_bonus = 140 if payload.get("unique_item") else 0
    base = (
        46
        + rarity_level * 34
        + int(round(_seed_listing_realm_markup(payload) * 1.25))
        + _seed_listing_skill_count(payload) * 28
        + type_bonus
        + unique_bonus
    )
    stats = _weighted_seed_stat_value(
        payload,
        {
            "attack_bonus": 2.8,
            "defense_bonus": 2.4,
            "bone_bonus": 9.2,
            "comprehension_bonus": 9.8,
            "divine_sense_bonus": 8.8,
            "fortune_bonus": 9.2,
            "qi_blood_bonus": 0.52,
            "true_yuan_bonus": 0.48,
            "body_movement_bonus": 2.2,
            "duel_rate_bonus": 18.0,
            "cultivation_bonus": 15.0,
        },
    )
    multiplier = _seed_quality_price_multiplier(rarity_level, item_kind="artifact")
    return _round_seed_shop_price((base + stats) * multiplier)


def _pill_seed_shop_price(payload: dict[str, Any]) -> int:
    rarity_level = max(int(payload.get("rarity_level") or 1), 1)
    pill_type = str(payload.get("pill_type") or "").strip()
    effect_value = max(float(payload.get("effect_value") or 0), 0.0)
    poison_delta = max(float(payload.get("poison_delta") or 0), 0.0)
    type_base = {
        "foundation": 48,
        "clear_poison": 20,
        "cultivation": 26,
        "stone": 22,
        "bone": 28,
        "comprehension": 30,
        "divine_sense": 28,
        "fortune": 38,
        "willpower": 30,
        "charisma": 28,
        "karma": 36,
        "qi_blood": 28,
        "true_yuan": 28,
        "body_movement": 30,
        "attack": 32,
        "defense": 32,
        "root_refine": 180,
        "root_remold": 240,
        "root_single": 210,
        "root_double": 210,
        "root_earth": 360,
        "root_heaven": 520,
        "root_variant": 460,
    }
    type_weight = {
        "foundation": 3.6,
        "clear_poison": 1.5,
        "cultivation": 0.82,
        "stone": 0.78,
        "bone": 18.0,
        "comprehension": 18.5,
        "divine_sense": 17.0,
        "fortune": 22.0,
        "willpower": 19.0,
        "charisma": 18.0,
        "karma": 22.0,
        "qi_blood": 0.85,
        "true_yuan": 0.82,
        "body_movement": 17.0,
        "attack": 18.0,
        "defense": 18.0,
        "root_refine": 180.0,
        "root_remold": 260.0,
        "root_single": 210.0,
        "root_double": 210.0,
        "root_earth": 380.0,
        "root_heaven": 520.0,
        "root_variant": 460.0,
    }
    stat_bonus = _weighted_seed_stat_value(
        payload,
        {
            "attack_bonus": 14.0,
            "defense_bonus": 14.0,
            "bone_bonus": 16.0,
            "comprehension_bonus": 16.0,
            "divine_sense_bonus": 15.0,
            "fortune_bonus": 18.0,
            "qi_blood_bonus": 0.75,
            "true_yuan_bonus": 0.72,
            "body_movement_bonus": 15.0,
        },
    )
    base = 18 + rarity_level * 22 + int(round(_seed_listing_realm_markup(payload) * 1.1)) + int(type_base.get(pill_type, 28))
    effect_price = effect_value * float(type_weight.get(pill_type, 12.0))
    multiplier = _seed_quality_price_multiplier(rarity_level, item_kind="pill")
    return _round_seed_shop_price((base + effect_price + poison_delta * 1.25 + stat_bonus) * multiplier)


def _talisman_seed_shop_price(payload: dict[str, Any]) -> int:
    rarity_level = max(int(payload.get("rarity_level") or 1), 1)
    effect_uses = max(int(payload.get("effect_uses") or 1), 1)
    base = (
        26
        + rarity_level * 22
        + int(round(_seed_listing_realm_markup(payload) * 1.15))
        + _seed_listing_skill_count(payload) * 22
        + effect_uses * 10
    )
    stats = _weighted_seed_stat_value(
        payload,
        {
            "attack_bonus": 2.2,
            "defense_bonus": 2.0,
            "bone_bonus": 6.8,
            "comprehension_bonus": 6.8,
            "divine_sense_bonus": 6.8,
            "fortune_bonus": 6.8,
            "qi_blood_bonus": 0.40,
            "true_yuan_bonus": 0.36,
            "body_movement_bonus": 1.9,
            "duel_rate_bonus": 14.5,
        },
    )
    multiplier = _seed_quality_price_multiplier(rarity_level, item_kind="talisman")
    return _round_seed_shop_price((base + stats) * multiplier)


def _material_seed_shop_price(payload: dict[str, Any]) -> int:
    if _is_immortal_stone_payload("material", payload):
        return _immortal_stone_exchange_cost()
    quality_level = max(int(payload.get("quality_level") or 1), 1)
    seed_price = max(int(payload.get("seed_price_stone") or 0), 0)
    growth_minutes = max(int(payload.get("growth_minutes") or 0), 0)
    yield_min = max(int(payload.get("yield_min") or 0), 0)
    yield_max = max(int(payload.get("yield_max") or 0), yield_min)
    yield_average = (yield_min + yield_max) / 2 if (yield_min or yield_max) else 0.0
    yield_span = max(yield_max - yield_min, 0)
    base = (
        20
        + quality_level * 26
        + int(round(_seed_listing_realm_markup(payload) * 1.1))
        + (24 if payload.get("can_plant") else 0)
    )
    growth_markup = min(growth_minutes / 10.0, 150.0)
    yield_markup = yield_average * (6.5 + quality_level * 1.1) + min(float(yield_span * 8), 120.0)
    attribute_score = _material_seed_attribute_score(payload)
    attribute_markup = attribute_score * (5.4 + quality_level * 1.25)
    multiplier = _seed_quality_price_multiplier(quality_level, item_kind="material")
    seed_anchor = float(seed_price) * 1.7 if seed_price > 0 else 0.0
    quality_floor = (40.0 + quality_level * 30.0) * multiplier * (1.0 + max(quality_level - 1, 0) * 0.08)
    return _round_seed_shop_price(max((base + growth_markup + yield_markup + attribute_markup) * multiplier, quality_floor, seed_anchor, 15.0))


def _recipe_result_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    result_kind = str(payload.get("result_kind") or "").strip()
    result_ref_id = int(payload.get("result_ref_id") or 0)
    if not result_kind or result_ref_id <= 0 or result_kind == "recipe":
        return result_kind, None
    try:
        return result_kind, _official_seed_item_payload(result_kind, result_ref_id)
    except Exception:
        return result_kind, None


def _official_payload_quality_level(item_kind: str, payload: dict[str, Any]) -> int:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "recipe":
        _result_kind, result_payload = _recipe_result_payload(payload)
        if result_payload:
            return max(int(result_payload.get("rarity_level") or result_payload.get("quality_level") or 1), 1)
    return max(int(payload.get("rarity_level") or payload.get("quality_level") or 1), 1)


def _official_payload_quality_label(item_kind: str, payload: dict[str, Any], quality_level: int) -> str:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "recipe":
        _result_kind, result_payload = _recipe_result_payload(payload)
        result_quality = ""
        if result_payload:
            result_quality = str(
                result_payload.get("rarity")
                or result_payload.get("quality_label")
                or f"{quality_level}阶"
            ).strip()
        recipe_kind = str(payload.get("recipe_kind_label") or "配方").strip() or "配方"
        return f"{result_quality or f'{quality_level}阶'}{recipe_kind}"
    return str(payload.get("rarity") or payload.get("quality_label") or f"{quality_level}阶").strip() or f"{quality_level}阶"


def _official_payload_quality_color(item_kind: str, payload: dict[str, Any]) -> str | None:
    normalized_kind = str(item_kind or "").strip()
    if payload.get("quality_color"):
        return payload.get("quality_color")
    if normalized_kind == "recipe":
        _result_kind, result_payload = _recipe_result_payload(payload)
        if result_payload:
            return result_payload.get("quality_color")
    return None


def _technique_seed_shop_price(payload: dict[str, Any]) -> int:
    rarity_level = max(int(payload.get("rarity_level") or 1), 1)
    type_bonus = {
        "cultivation": 34,
        "battle": 40,
        "body": 30,
        "support": 28,
    }.get(str(payload.get("technique_type") or "").strip(), 32)
    base = (
        64
        + rarity_level * 42
        + int(round(_seed_listing_realm_markup(payload) * 1.25))
        + _seed_listing_skill_count(payload) * 34
        + type_bonus
    )
    stats = _weighted_seed_stat_value(
        payload,
        {
            "attack_bonus": 2.4,
            "defense_bonus": 2.2,
            "bone_bonus": 10.0,
            "comprehension_bonus": 10.5,
            "divine_sense_bonus": 9.5,
            "fortune_bonus": 9.8,
            "qi_blood_bonus": 0.46,
            "true_yuan_bonus": 0.44,
            "body_movement_bonus": 2.5,
            "duel_rate_bonus": 17.0,
            "cultivation_bonus": 18.0,
            "breakthrough_bonus": 20.0,
        },
    )
    multiplier = _seed_quality_price_multiplier(rarity_level, item_kind="technique")
    return _round_seed_shop_price((base + stats) * multiplier)


def _recipe_seed_shop_price(payload: dict[str, Any]) -> int:
    quality_level = _official_payload_quality_level("recipe", payload)
    result_quantity = max(int(payload.get("result_quantity") or 1), 1)
    success_rate = min(max(float(payload.get("base_success_rate") or 0), 1.0), 100.0)
    result_kind, result_payload = _recipe_result_payload(payload)
    result_anchor = 0
    if result_payload and result_kind in (RECYCLABLE_ITEM_KINDS - {"recipe"}):
        try:
            result_anchor = _seed_official_shop_price(result_kind, result_payload)
        except ValueError:
            result_anchor = 0
    multiplier = _seed_quality_price_multiplier(quality_level, item_kind="recipe")
    base = 52 + quality_level * 30 + result_quantity * 10
    rarity_markup = max(100.0 - success_rate, 0.0) * (0.75 + quality_level * 0.08)
    result_markup = result_anchor * result_quantity * (0.30 + success_rate / 300.0)
    return _round_seed_shop_price(max((base + rarity_markup) * multiplier, result_markup, 35.0))


def _seed_official_shop_price(item_kind: str, payload: dict[str, Any]) -> int:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "artifact":
        return _artifact_seed_shop_price(payload)
    if normalized_kind == "pill":
        return _pill_seed_shop_price(payload)
    if normalized_kind == "talisman":
        return _talisman_seed_shop_price(payload)
    if normalized_kind == "material":
        return _material_seed_shop_price(payload)
    if normalized_kind == "technique":
        return _technique_seed_shop_price(payload)
    if normalized_kind == "recipe":
        return _recipe_seed_shop_price(payload)
    raise ValueError("默认官方商店暂不支持该物品类型")


def _official_recycle_anchor_price(item_kind: str, payload: dict[str, Any]) -> int:
    normalized_kind = str(item_kind or "").strip()
    if _is_immortal_stone_payload(normalized_kind, payload):
        return _immortal_stone_exchange_cost()
    if normalized_kind in RECYCLABLE_ITEM_KINDS:
        return _seed_official_shop_price(normalized_kind, payload)
    raise ValueError("当前物品类型暂不支持万宝归炉")


def _official_recycle_ratio(item_kind: str, quality_level: int, payload: dict[str, Any]) -> float:
    normalized_kind = str(item_kind or "").strip()
    level = max(int(quality_level or 1), 1)
    if normalized_kind == "artifact":
        ratio = min(0.60, (0.22 + (level - 1) * 0.035) * 1.38)
        if payload.get("unique_item"):
            ratio = max(ratio - 0.05, 0.38)
        return ratio
    if normalized_kind == "pill":
        return min(0.58, (0.24 + (level - 1) * 0.028) * 1.38)
    if normalized_kind == "talisman":
        return min(0.59, (0.23 + (level - 1) * 0.03) * 1.38)
    if normalized_kind == "material":
        plant_bonus = 0.02 if payload.get("can_plant") else 0.0
        return min(0.62, (0.26 + (level - 1) * 0.03 + plant_bonus) * 1.38)
    if normalized_kind == "technique":
        return min(0.57, (0.20 + (level - 1) * 0.032) * 1.38)
    if normalized_kind == "recipe":
        return min(0.54, (0.18 + (level - 1) * 0.028) * 1.38)
    raise ValueError("当前物品类型暂不支持万宝归炉")


def _official_recycle_charisma_bonus_percent(charisma: int) -> int:
    return min(max(int(charisma or 0) - 10, 0) // 4, 10)


def _official_recycle_price_cap(item_kind: str, quality_level: int, payload: dict[str, Any]) -> int:
    normalized_kind = str(item_kind or "").strip()
    if _is_immortal_stone_payload(normalized_kind, payload):
        return _immortal_stone_recycle_limit()
    level = max(int(quality_level or 1), 1)
    if normalized_kind == "artifact":
        stat_score = _weighted_seed_stat_value(
            payload,
            {
                "attack_bonus": 6.0,
                "defense_bonus": 5.5,
                "bone_bonus": 8.0,
                "comprehension_bonus": 8.0,
                "divine_sense_bonus": 7.5,
                "fortune_bonus": 9.0,
                "qi_blood_bonus": 0.4,
                "true_yuan_bonus": 0.36,
                "body_movement_bonus": 6.0,
                "duel_rate_bonus": 12.0,
                "cultivation_bonus": 9.0,
            },
        )
        return max(
            _round_seed_shop_price(
                90
                + level * 180
                + _seed_listing_skill_count(payload) * 55
                + stat_score / 3.2
                + (120 if payload.get("unique_item") else 0)
            ),
            5,
        )
    if normalized_kind == "pill":
        stat_score = _weighted_seed_stat_value(
            payload,
            {
                "attack_bonus": 8.0,
                "defense_bonus": 8.0,
                "bone_bonus": 10.0,
                "comprehension_bonus": 10.0,
                "divine_sense_bonus": 10.0,
                "fortune_bonus": 11.0,
                "qi_blood_bonus": 0.5,
                "true_yuan_bonus": 0.46,
                "body_movement_bonus": 8.0,
            },
        )
        return max(
            _round_seed_shop_price(
                80
                + level * 125
                + min(max(int(payload.get("effect_value") or 0), 0) * 4, 260)
                + stat_score / 4.0
            ),
            5,
        )
    if normalized_kind == "talisman":
        stat_score = _weighted_seed_stat_value(
            payload,
            {
                "attack_bonus": 7.0,
                "defense_bonus": 6.0,
                "bone_bonus": 8.0,
                "comprehension_bonus": 8.0,
                "divine_sense_bonus": 8.0,
                "fortune_bonus": 8.0,
                "qi_blood_bonus": 0.38,
                "true_yuan_bonus": 0.34,
                "body_movement_bonus": 6.5,
                "duel_rate_bonus": 12.0,
            },
        )
        return max(
            _round_seed_shop_price(
                90
                + level * 140
                + max(int(payload.get("effect_uses") or 1), 1) * 55
                + _seed_listing_skill_count(payload) * 40
                + stat_score / 3.8
            ),
            5,
        )
    if normalized_kind == "material":
        seed_price = max(int(payload.get("seed_price_stone") or 0), 0)
        yield_bonus = max(int(payload.get("yield_max") or 0), 0) * 18
        attribute_score = _material_seed_attribute_score(payload)
        return max(
            _round_seed_shop_price(
                60
                + level * 110
                + min(seed_price / 2.0, 260.0)
                + min(float(yield_bonus), 180.0)
                + attribute_score * (4.0 + level * 0.75)
                + (30 if payload.get("can_plant") else 0)
            ),
            5,
        )
    if normalized_kind == "technique":
        stat_score = _weighted_seed_stat_value(
            payload,
            {
                "attack_bonus": 5.5,
                "defense_bonus": 5.2,
                "bone_bonus": 8.5,
                "comprehension_bonus": 9.0,
                "divine_sense_bonus": 8.2,
                "fortune_bonus": 8.6,
                "qi_blood_bonus": 0.38,
                "true_yuan_bonus": 0.36,
                "body_movement_bonus": 6.5,
                "duel_rate_bonus": 12.0,
                "cultivation_bonus": 13.0,
                "breakthrough_bonus": 14.0,
            },
        )
        return max(
            _round_seed_shop_price(
                110
                + level * 165
                + int(round(_seed_listing_realm_markup(payload) * 2.0))
                + _seed_listing_skill_count(payload) * 65
                + stat_score / 3.2
            ),
            5,
        )
    if normalized_kind == "recipe":
        result_quantity = max(int(payload.get("result_quantity") or 1), 1)
        success_rate = min(max(float(payload.get("base_success_rate") or 0), 1.0), 100.0)
        result_kind, result_payload = _recipe_result_payload(payload)
        result_anchor = 0
        if result_payload and result_kind in (RECYCLABLE_ITEM_KINDS - {"recipe"}):
            try:
                result_anchor = _seed_official_shop_price(result_kind, result_payload)
            except ValueError:
                result_anchor = 0
        return max(
            _round_seed_shop_price(
                80
                + level * 120
                + min(result_anchor * result_quantity * 0.42, 640.0)
                + max(100.0 - success_rate, 0.0) * 1.8
            ),
            5,
        )
    raise ValueError("当前物品类型暂不支持万宝归炉")


def build_official_recycle_quote(
    item_kind: str,
    item_payload: dict[str, Any],
    *,
    available_quantity: int,
    quantity: int = 1,
    charisma: int = 0,
) -> dict[str, Any]:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind not in RECYCLABLE_ITEM_KINDS:
        raise ValueError("当前物品类型暂不支持万宝归炉")
    payload = dict(item_payload or {})
    item_ref_id = int(payload.get("id") or 0)
    if item_ref_id <= 0:
        raise ValueError("未曾寻得可供归炉之物。")
    available = max(int(available_quantity or 0), 0)
    if available <= 0:
        raise ValueError("囊中空空，无可归炉之物。")
    requested = max(int(quantity or 0), 1)
    quality_level = _official_payload_quality_level(normalized_kind, payload)
    quality_label = _official_payload_quality_label(normalized_kind, payload, quality_level)
    quality_color = _official_payload_quality_color(normalized_kind, payload)
    anchor_price = _official_recycle_anchor_price(normalized_kind, payload)
    ratio = _official_recycle_ratio(normalized_kind, quality_level, payload)
    hard_limit = _round_seed_shop_price(anchor_price * 0.72)
    cap_price = _official_recycle_price_cap(normalized_kind, quality_level, payload)
    unit_price = _round_seed_shop_price(anchor_price * ratio)
    charisma_bonus_percent = _official_recycle_charisma_bonus_percent(charisma)
    if charisma_bonus_percent > 0:
        unit_price = _round_seed_shop_price(unit_price * (1 + charisma_bonus_percent / 100.0))
    unit_price = max(min(unit_price, hard_limit, cap_price), 5)
    if _is_immortal_stone_payload(normalized_kind, payload):
        unit_price = min(unit_price, _immortal_stone_recycle_limit())
    quote_note = (
        f"按{quality_label}品阶、属性与魅力折价归炉，品质越高、属性越强，归炉价越高"
        f"{f'，本次魅力加成 {charisma_bonus_percent}%' if charisma_bonus_percent else ''}，但仍低于官方商店售价。"
    )
    if _is_immortal_stone_payload(normalized_kind, payload):
        quote_note = (
            f"{IMMORTAL_STONE_NAME}按当前兑换成本折价归炉"
            f"{f'，本次魅力加成 {charisma_bonus_percent}%' if charisma_bonus_percent else ''}，回收价不会高于兑换成本。"
        )
    return {
        "shop_name": OFFICIAL_RECYCLE_NAME,
        "item_kind": normalized_kind,
        "item_kind_label": ITEM_KIND_LABELS.get(normalized_kind, normalized_kind),
        "item_ref_id": item_ref_id,
        "item_name": str(payload.get("name") or f"{normalized_kind}#{item_ref_id}"),
        "quality_level": quality_level,
        "quality_label": quality_label,
        "quality_color": quality_color,
        "available_quantity": available,
        "requested_quantity": requested,
        "unit_price_stone": unit_price,
        "total_price_stone": unit_price * requested,
        "max_total_price_stone": unit_price * available,
        "anchor_price_stone": anchor_price,
        "charisma_bonus_percent": charisma_bonus_percent,
        "quote_note": quote_note,
    }


def _official_recycle_source_payload(row: dict[str, Any], item_key: str) -> dict[str, Any]:
    nested_payload = row.get(item_key)
    if isinstance(nested_payload, dict):
        return dict(nested_payload)
    if int(row.get("id") or 0) > 0 and str(row.get("name") or "").strip():
        return dict(row)
    return {}


def attach_official_recycle_quotes(bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        return bundle
    entries: list[dict[str, Any]] = []
    charisma = int((bundle.get("effective_stats") or {}).get("charisma") or (bundle.get("profile") or {}).get("charisma") or 0)
    source_specs = (
        ("artifact", "artifacts", "artifact"),
        ("pill", "pills", "pill"),
        ("talisman", "talismans", "talisman"),
        ("material", "materials", "material"),
        ("technique", "techniques", "technique"),
        ("recipe", "recipes", "recipe"),
    )
    for item_kind, source_key, item_key in source_specs:
        for row in bundle.get(source_key) or []:
            if not isinstance(row, dict):
                continue
            item_payload = _official_recycle_source_payload(row, item_key)
            if not item_payload:
                continue
            if "tradeable_quantity" in row and row.get("tradeable_quantity") is not None:
                available_quantity = max(int(row.get("tradeable_quantity") or 0), 0)
            elif item_kind in {"technique", "recipe"}:
                available_quantity = 1
            else:
                available_quantity = max(int(row.get("quantity") or 0), 0)
            if available_quantity <= 0:
                continue
            try:
                entries.append(
                    build_official_recycle_quote(
                        item_kind,
                        item_payload,
                        available_quantity=available_quantity,
                        quantity=available_quantity,
                        charisma=charisma,
                    )
                )
            except ValueError:
                continue
    entries.sort(
        key=lambda row: (
            -int(row.get("quality_level") or 0),
            -int(row.get("unit_price_stone") or 0),
            str(row.get("item_name") or ""),
        )
    )
    bundle["official_recycle"] = {
        "shop_name": OFFICIAL_RECYCLE_NAME,
        "description": "万宝归炉会按物品品阶和属性统一折价，法宝、丹药、符箓、材料、功法与配方都可归炉成灵石。",
        "items": entries,
    }
    return bundle


def _find_official_recycle_quote_for_user(tg: int, item_kind: str, item_ref_id: int) -> dict[str, Any] | None:
    normalized_kind = str(item_kind or "").strip()
    profile = get_profile(int(tg), create=False)
    profile_payload = serialize_profile(profile) if profile is not None else {}
    try:
        charisma = int((_battle_bundle(profile_payload).get("stats") or {}).get("charisma") or profile_payload.get("charisma") or 0)
    except Exception:
        charisma = int(profile_payload.get("charisma") or 0)
    source_map: dict[str, tuple[list[dict[str, Any]], str]] = {
        "artifact": (list_user_artifacts(tg), "artifact"),
        "pill": (list_user_pills(tg), "pill"),
        "talisman": (list_user_talismans(tg), "talisman"),
        "material": (list_user_materials(tg), "material"),
        "technique": (list_user_techniques(tg, enabled_only=False), "technique"),
        "recipe": (list_user_recipes(tg, enabled_only=False), "recipe"),
    }
    rows, item_key = source_map.get(normalized_kind, ([], ""))
    target_ref_id = int(item_ref_id or 0)
    if target_ref_id <= 0 or not item_key:
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_payload = _official_recycle_source_payload(row, item_key)
        if int(item_payload.get("id") or 0) != target_ref_id:
            continue
        if "tradeable_quantity" in row and row.get("tradeable_quantity") is not None:
            available_quantity = max(int(row.get("tradeable_quantity") or 0), 0)
        elif normalized_kind in {"technique", "recipe"}:
            available_quantity = 1
        else:
            available_quantity = max(int(row.get("quantity") or 0), 0)
        if available_quantity <= 0:
            return None
        try:
            return build_official_recycle_quote(
                normalized_kind,
                item_payload,
                available_quantity=available_quantity,
                quantity=1,
                charisma=charisma,
            )
        except ValueError:
            return None
    return None


def _restore_inventory_item_after_failure(
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    *,
    action_text: str,
) -> None:
    normalized_kind = str(item_kind or "").strip()
    amount = max(int(quantity or 0), 0)
    if amount <= 0:
        return
    if normalized_kind in {"artifact", "pill", "talisman", "material"}:
        grant_item_to_user(int(tg), normalized_kind, int(item_ref_id), amount)
        return
    if normalized_kind == "technique":
        grant_technique_to_user(
            int(tg),
            int(item_ref_id),
            source="rollback",
            obtained_note=f"{action_text}失败返还",
            auto_equip_if_empty=True,
        )
        return
    if normalized_kind == "recipe":
        grant_recipe_to_user(
            int(tg),
            int(item_ref_id),
            source="rollback",
            obtained_note=f"{action_text}失败返还",
        )
        return
    raise ValueError("不支持的物品类型")


def _rollback_consumed_item_or_raise(
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    *,
    action_text: str,
    item_name: str,
) -> None:
    try:
        _restore_inventory_item_after_failure(
            tg,
            item_kind,
            item_ref_id,
            quantity,
            action_text=action_text,
        )
    except Exception as rollback_exc:
        raise RuntimeError(f"{action_text}失败，且自动返还【{item_name}】时出错，请尽快联系管理员处理。") from rollback_exc


def _ensure_default_official_shop_listings(
    *,
    settings: dict[str, Any],
    artifact_map: dict[str, dict[str, Any]],
    pill_map: dict[str, dict[str, Any]],
    talisman_map: dict[str, dict[str, Any]],
    material_map: dict[str, dict[str, Any]],
) -> None:
    official_name = str(settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"]) or DEFAULT_SETTINGS["official_shop_name"]).strip() or DEFAULT_SETTINGS["official_shop_name"]
    max_official_quality_level = 3
    source_map = {
        "artifact": artifact_map,
        "pill": pill_map,
        "talisman": talisman_map,
        "material": material_map,
    }
    source_id_map = {
        kind: {
            int(payload.get("id") or 0): payload
            for payload in values.values()
            if int(payload.get("id") or 0) > 0
        }
        for kind, values in source_map.items()
    }
    existing_items = {
        (str(item.get("item_kind") or "").strip(), int(item.get("item_ref_id") or 0)): item
        for item in list_shop_items(official_only=True, include_disabled=True)
        if int(item.get("item_ref_id") or 0) > 0
    }

    for (item_kind, item_id), item in existing_items.items():
        payload = (source_id_map.get(item_kind) or {}).get(item_id)
        if payload is None or not payload.get("enabled"):
            continue
        if _official_payload_quality_level(item_kind, payload) > max_official_quality_level:
            if bool(item.get("enabled", True)):
                update_shop_item(int(item.get("id") or 0), enabled=False)
            continue
        resolved_price = _seed_official_shop_price(item_kind, payload)
        patch: dict[str, Any] = {}
        resolved_name = str(payload.get("name") or item.get("item_name") or "").strip()
        if resolved_name and str(item.get("item_name") or "").strip() != resolved_name:
            patch["item_name"] = resolved_name
        if str(item.get("shop_name") or "").strip() != official_name:
            patch["shop_name"] = official_name
        if int(item.get("price_stone") or 0) != resolved_price:
            patch["price_stone"] = resolved_price
        if patch:
            update_shop_item(int(item.get("id") or 0), **patch)

    for seed in DEFAULT_OFFICIAL_SHOP_ITEMS:
        item_kind = str(seed["item_kind"]).strip()
        item_name = str(seed["item_name"]).strip()
        payload = (source_map.get(item_kind) or {}).get(item_name)
        if not payload or not payload.get("enabled"):
            continue
        if _official_payload_quality_level(item_kind, payload) > max_official_quality_level:
            continue
        item_id = int(payload.get("id") or 0)
        if item_id <= 0:
            continue
        key = (item_kind, item_id)
        if key in existing_items:
            continue
        create_shop_item(
            owner_tg=None,
            shop_name=official_name,
            item_kind=item_kind,
            item_ref_id=item_id,
            item_name=str(payload.get("name") or item_name),
            quantity=max(int(seed.get("quantity") or 1), 1),
            price_stone=_seed_official_shop_price(item_kind, payload),
            is_official=True,
        )
        existing_items[key] = {"id": 0}


def ensure_seed_data(force: bool = False) -> None:
    global SEED_DATA_READY
    if SEED_DATA_READY and not force:
        _sync_default_artifact_set_links()
        _ensure_default_boss_configs_synced()
        return
    with SEED_DATA_LOCK:
        persisted_version = _get_seed_data_version()
        if persisted_version == SEED_DATA_VERSION and not force:
            _sync_default_artifact_set_links()
            _ensure_default_boss_configs_synced()
            SEED_DATA_READY = True
            return

        with _seed_data_db_lock():
            persisted_version = _get_seed_data_version()
            if persisted_version == SEED_DATA_VERSION and not force:
                _sync_default_artifact_set_links()
                _ensure_default_boss_configs_synced()
                SEED_DATA_READY = True
                return

            title_map: dict[str, dict[str, Any]] = {}
            for payload in DEFAULT_TITLES:
                title = sync_title_by_name(**payload, enabled=True)
                title_map[title["name"]] = title

            artifact_set_map: dict[str, dict[str, Any]] = {}
            for payload in DEFAULT_ARTIFACT_SETS:
                artifact_set = sync_artifact_set_by_name(**payload, enabled=True)
                artifact_set_map[artifact_set["name"]] = artifact_set

            for payload in DEFAULT_ARTIFACTS:
                artifact_payload = dict(payload)
                artifact_set_name = str(artifact_payload.pop("artifact_set_name", "") or "").strip()
                if artifact_set_name:
                    artifact_payload["artifact_set_id"] = int(artifact_set_map[artifact_set_name]["id"])
                sync_artifact_by_name(**artifact_payload)
            artifact_map = {item["name"]: item for item in list_artifacts()}
            _sync_default_artifact_set_links()

            for payload in DEFAULT_PILLS:
                sync_pill_by_name(**payload)
            pill_map = {item["name"]: item for item in list_pills()}

            for payload in DEFAULT_TALISMANS:
                sync_talisman_by_name(**payload)
            talisman_map = {item["name"]: item for item in list_talismans()}

            for payload in DEFAULT_TECHNIQUES:
                sync_technique_by_name(**payload)
            technique_map = {item["name"]: item for item in list_techniques()}

            for payload in DEFAULT_MATERIALS:
                sync_material_by_name(**payload, enabled=True)
            material_map = {item["name"]: item for item in list_materials()}
            recipe_missing_refs: list[str] = []
            for recipe in DEFAULT_RECIPES:
                recipe_missing_refs.extend(
                    _collect_missing_seed_refs(
                        [
                            (str(recipe["result_kind"]), str(recipe["result_name"])),
                            *[
                                ("material", str(item["material_name"]))
                                for item in recipe.get("ingredients") or []
                            ],
                        ],
                        artifact_map=artifact_map,
                        pill_map=pill_map,
                        talisman_map=talisman_map,
                        material_map=material_map,
                        technique_map=technique_map,
                    )
                )
            _raise_on_missing_seed_refs("默认种子配方", recipe_missing_refs)
            settings = get_xiuxian_settings()
            sync_official_shop_name(
                str(settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"]) or DEFAULT_SETTINGS["official_shop_name"])
            )
            _ensure_default_official_shop_listings(
                settings=settings,
                artifact_map=artifact_map,
                pill_map=pill_map,
                talisman_map=talisman_map,
                material_map=material_map,
            )

            for recipe in DEFAULT_RECIPES:
                result_ref_id = _resolve_seed_result_ref_id(
                    str(recipe["result_kind"]),
                    str(recipe["result_name"]),
                    artifact_map=artifact_map,
                    pill_map=pill_map,
                    talisman_map=talisman_map,
                    material_map=material_map,
                    technique_map=technique_map,
                )
                sync_recipe_with_ingredients_by_name(
                    name=str(recipe["name"]),
                    recipe_kind=str(recipe["recipe_kind"]),
                    result_kind=str(recipe["result_kind"]),
                    result_ref_id=result_ref_id,
                    result_quantity=int(recipe["result_quantity"]),
                    base_success_rate=int(recipe["base_success_rate"]),
                    broadcast_on_success=bool(recipe.get("broadcast_on_success")),
                    ingredients=[
                        {
                            "material_id": _resolve_seed_result_ref_id(
                                "material",
                                str(item["material_name"]),
                                artifact_map=artifact_map,
                                pill_map=pill_map,
                                talisman_map=talisman_map,
                                material_map=material_map,
                                technique_map=technique_map,
                            ),
                            "quantity": int(item["quantity"]),
                        }
                        for item in recipe.get("ingredients") or []
                    ],
                )
            recipe_map = {item["name"]: item for item in list_recipes()}
            content_missing_refs: list[str] = []
            for scene in DEFAULT_SCENES:
                content_missing_refs.extend(
                    _collect_missing_seed_refs(
                        [
                            (
                                str(event.get("bonus_reward_kind") or "material"),
                                str(event.get("bonus_reward_ref_id_name")),
                            )
                            for event in scene.get("event_pool") or []
                            if event.get("bonus_reward_ref_id_name")
                        ]
                        + [
                            (
                                str(drop.get("reward_kind") or "material"),
                                str(drop.get("reward_ref_id_name")),
                            )
                            for drop in scene.get("drops") or []
                            if drop.get("reward_ref_id_name")
                        ],
                        artifact_map=artifact_map,
                        pill_map=pill_map,
                        talisman_map=talisman_map,
                        material_map=material_map,
                        technique_map=technique_map,
                        recipe_map=recipe_map,
                    )
                )
            for encounter in DEFAULT_ENCOUNTER_TEMPLATES:
                reward_item_name = str(encounter.get("reward_item_ref_name") or "").strip()
                if not reward_item_name:
                    continue
                content_missing_refs.extend(
                    _collect_missing_seed_refs(
                        [(str(encounter.get("reward_item_kind") or "material"), reward_item_name)],
                        artifact_map=artifact_map,
                        pill_map=pill_map,
                        talisman_map=talisman_map,
                        material_map=material_map,
                        technique_map=technique_map,
                        recipe_map=recipe_map,
                    )
                )
            _raise_on_missing_seed_refs("默认种子内容", content_missing_refs)

            for payload in DEFAULT_SECTS:
                sync_sect_with_roles_by_name(**payload)

            for scene in DEFAULT_SCENES:
                resolved_events = []
                for event in scene.get("event_pool") or []:
                    payload = dict(event)
                    if payload.get("bonus_reward_ref_id_name"):
                        payload["bonus_reward_ref_id"] = _resolve_seed_result_ref_id(
                            str(payload.get("bonus_reward_kind") or "material"),
                            str(payload.get("bonus_reward_ref_id_name")),
                            artifact_map=artifact_map,
                            pill_map=pill_map,
                            talisman_map=talisman_map,
                            material_map=material_map,
                            technique_map=technique_map,
                            recipe_map=recipe_map,
                        )
                    payload.pop("bonus_reward_ref_id_name", None)
                    resolved_events.append(payload)
                resolved_drops = []
                for drop in scene.get("drops") or []:
                    payload = dict(drop)
                    if payload.get("reward_ref_id_name"):
                        payload["reward_ref_id"] = _resolve_seed_result_ref_id(
                            str(payload.get("reward_kind") or "material"),
                            str(payload.get("reward_ref_id_name")),
                            artifact_map=artifact_map,
                            pill_map=pill_map,
                            talisman_map=talisman_map,
                            material_map=material_map,
                            technique_map=technique_map,
                            recipe_map=recipe_map,
                        )
                    payload.pop("reward_ref_id_name", None)
                    resolved_drops.append(payload)
                sync_scene_with_drops_by_name(
                    name=str(scene["name"]),
                    description=str(scene.get("description") or ""),
                    image_url=str(scene.get("image_url") or ""),
                    max_minutes=int(scene.get("max_minutes") or 60),
                    min_realm_stage=scene.get("min_realm_stage"),
                    min_realm_layer=int(scene.get("min_realm_layer") or 1),
                    min_combat_power=int(scene.get("min_combat_power") or 0),
                    event_pool=resolved_events,
                    drops=resolved_drops,
                )

            for encounter in DEFAULT_ENCOUNTER_TEMPLATES:
                encounter_payload = dict(encounter)
                reward_item_name = str(encounter_payload.pop("reward_item_ref_name", "") or "").strip()
                if reward_item_name:
                    encounter_payload["reward_item_ref_id"] = _resolve_seed_result_ref_id(
                        str(encounter_payload.get("reward_item_kind") or "material"),
                        reward_item_name,
                        artifact_map=artifact_map,
                        pill_map=pill_map,
                        talisman_map=talisman_map,
                        material_map=material_map,
                        technique_map=technique_map,
                        recipe_map=recipe_map,
                    )
                sync_encounter_template_by_name(**encounter_payload)

            for payload in DEFAULT_ACHIEVEMENTS:
                achievement_payload = dict(payload)
                reward_config = dict(achievement_payload.get("reward_config") or {})
                reward_title_names = [str(name) for name in reward_config.pop("reward_title_names", []) if str(name).strip()]
                reward_config["titles"] = [
                    int(title_map[name]["id"])
                    for name in reward_title_names
                    if name in title_map
                ]
                achievement_payload["reward_config"] = reward_config
                sync_achievement_by_key(**achievement_payload)

            _sync_default_boss_configs(
                artifact_map=artifact_map,
                pill_map=pill_map,
                talisman_map=talisman_map,
                material_map=material_map,
                technique_map=technique_map,
                recipe_map=recipe_map,
                patch_empty_world_loot=True,
            )

            purge_removed_pill_types()
            set_xiuxian_settings({
                "seed_data_version": SEED_DATA_VERSION,
                DEFAULT_BOSS_SYNC_SETTING: DEFAULT_BOSS_SYNC_VERSION,
            })
            SEED_DATA_READY = True


def china_now():
    return utcnow() + timedelta(hours=8)


def is_same_china_day(left, right) -> bool:
    if left is None or right is None:
        return False
    return (left + timedelta(hours=8)).date() == (right + timedelta(hours=8)).date()


def realm_requirement_met(profile: dict[str, Any], min_stage: str | None, min_layer: int | None) -> bool:
    if not min_stage:
        return True

    current_stage = realm_index(profile.get("realm_stage"))
    required_stage = realm_index(min_stage)
    current_layer = int(profile.get("realm_layer") or 0)
    required_layer = int(min_layer or 1)
    if current_stage != required_stage:
        return current_stage > required_stage
    return current_layer >= required_layer


def format_realm_requirement(min_stage: str | None, min_layer: int | None) -> str:
    if not min_stage:
        return "无限制"
    return f"{min_stage}{int(min_layer or 1)}层"


def apply_cultivation_gain(stage: str, layer: int, cultivation: int, gain: int) -> tuple[int, int, list[int], int]:
    current_layer = max(int(layer or 1), 1)
    current_cultivation = max(int(cultivation or 0), 0) + max(int(gain or 0), 0)
    upgraded_layers: list[int] = []
    threshold = cultivation_threshold(stage, current_layer)

    while current_layer < 9 and current_cultivation >= threshold:
        current_cultivation -= threshold
        current_layer += 1
        upgraded_layers.append(current_layer)
        threshold = cultivation_threshold(stage, current_layer)

    if current_layer >= 9:
        current_cultivation = min(current_cultivation, threshold)

    remaining = max(threshold - current_cultivation, 0)
    return current_layer, current_cultivation, upgraded_layers, remaining


def _settle_profile_cultivation(profile: XiuxianProfile, gain: int = 0) -> tuple[int, int, list[int], int]:
    layer, cultivation, upgraded_layers, remaining = apply_cultivation_gain(
        normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE),
        int(profile.realm_layer or 1),
        int(profile.cultivation or 0),
        gain,
    )
    profile.realm_layer = layer
    profile.cultivation = cultivation
    return layer, cultivation, upgraded_layers, remaining


def _compute_immortal_touch_gain(stage: str, layer: int, cultivation: int, infusion_layers: int) -> int:
    simulated_layer = max(int(layer or 1), 1)
    simulated_cultivation = max(int(cultivation or 0), 0)
    remaining_layers = max(int(infusion_layers or 1), 1)
    total_gain = 0

    while remaining_layers > 0:
        threshold = cultivation_threshold(stage, simulated_layer)
        current = min(simulated_cultivation, threshold)
        total_gain += max(threshold - current, 0)
        if simulated_layer >= 9:
            break
        simulated_layer += 1
        simulated_cultivation = 0
        remaining_layers -= 1

    return total_gain


def immortal_touch_infuse_cultivation(actor_tg: int, target_tg: int) -> dict[str, Any]:
    if actor_tg == target_tg:
        raise ValueError("请回复其他道友后再施展仙人抚顶。")

    target = _repair_profile_realm_state(target_tg)
    if target is None or not target.consented:
        raise ValueError("被回复的道友还没有踏入仙途。")

    ensure_not_in_retreat(target_tg)
    settings = get_xiuxian_settings()
    configured_layers = _coerce_int(
        settings.get("immortal_touch_infusion_layers"),
        DEFAULT_SETTINGS["immortal_touch_infusion_layers"],
        1,
    )
    stage = normalize_realm_stage(target.realm_stage or FIRST_REALM_STAGE)
    current_layer = int(target.realm_layer or 1)
    current_cultivation = int(target.cultivation or 0)
    gain = _compute_immortal_touch_gain(stage, current_layer, current_cultivation, configured_layers)
    if gain <= 0:
        raise ValueError("对方当前修为已圆满，暂时无法继续灌注。")
    gain, gain_meta = adjust_cultivation_gain_for_social_mode(target, gain, settings=settings)

    next_layer, next_cultivation, upgraded_layers, remaining = apply_cultivation_gain(
        stage,
        current_layer,
        current_cultivation,
        gain,
    )
    updated = upsert_profile(
        target_tg,
        cultivation=next_cultivation,
        realm_layer=next_layer,
    )
    threshold = cultivation_threshold(stage, next_layer)
    extra_note = f"（避世效率 {gain_meta['efficiency_percent']}%）" if gain_meta.get("reduced") else ""
    create_journal(actor_tg, "immortal_touch", "仙人抚顶", f"为 TG {target_tg} 灌注了 {gain} 点修为{extra_note}")
    create_journal(target_tg, "immortal_touch", "获仙人抚顶", f"获得 TG {actor_tg} 灌注的 {gain} 点修为{extra_note}")
    return {
        "gain": gain,
        "configured_layers": configured_layers,
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "breakthrough_ready": bool(next_layer >= 9 and next_cultivation >= threshold),
        "threshold": threshold,
        "profile": serialize_profile(updated),
    }


def build_progress(stage: str, layer: int, cultivation: int) -> dict[str, int | bool]:
    threshold = cultivation_threshold(stage, layer)
    current = min(max(int(cultivation or 0), 0), threshold)
    if layer < 9:
        return {
            "threshold": threshold,
            "current": current,
            "remaining": max(threshold - current, 0),
            "breakthrough_ready": False,
        }
    return {
        "threshold": threshold,
        "current": min(current, threshold),
        "remaining": max(threshold - min(current, threshold), 0),
        "breakthrough_ready": min(current, threshold) >= threshold,
    }


def _compute_retreat_plan(profile) -> dict[str, int]:
    profile_data = serialize_profile(profile)
    artifact_effects = merge_artifact_effects(profile_data, collect_equipped_artifacts(profile.tg))
    sect_effects = get_sect_effects(profile_data)
    technique_effects = resolve_technique_effects(profile_data, _current_technique_payload(profile_data))
    title_effects = resolve_title_effects(profile_data, get_current_title(profile.tg))
    artifact_bonus = (
        int(artifact_effects.get("cultivation_bonus", 0))
        + int(sect_effects.get("cultivation_bonus", 0))
        + int(technique_effects.get("cultivation_bonus", 0))
        + int(title_effects.get("cultivation_bonus", 0))
        + int(profile_data.get("insight_bonus", 0) or 0)
    )
    stage = normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE)
    stage_rule = _realm_stage_rule(stage)
    poison_penalty = min(int(profile.dan_poison or 0) // 4, 25)
    gain_per_hour = max(
        int(stage_rule.get("retreat_hourly_base", 150))
        + int(profile.realm_layer or 1) * 18
        + int(realm_index(stage)) * 48
        + artifact_bonus * 3
        - poison_penalty * 4,
        60,
    )
    cost_per_hour = max(ceil(gain_per_hour / 10), 12)
    return {
        "gain_per_minute": max(gain_per_hour // 60, 1),
        "cost_per_minute": max(cost_per_hour // 60, 1),
    }


def _is_retreating(profile) -> bool:
    return bool(profile and profile.retreat_started_at and profile.retreat_end_at and int(profile.retreat_minutes_total or 0) > int(profile.retreat_minutes_resolved or 0))


def _settle_retreat_progress(tg: int) -> dict[str, Any] | None:
    profile = get_profile(tg, create=False)
    if profile is None or not _is_retreating(profile):
        return None

    retreat_end_at = profile.retreat_end_at
    now = datetime.now(retreat_end_at.tzinfo) if retreat_end_at is not None and retreat_end_at.tzinfo is not None else utcnow()
    end_at = profile.retreat_end_at or now
    started_at = profile.retreat_started_at or now
    total_minutes = max(int(profile.retreat_minutes_total or 0), 0)
    resolved_minutes = max(int(profile.retreat_minutes_resolved or 0), 0)
    elapsed_minutes = int(max(min(now, end_at) - started_at, timedelta()).total_seconds() // 60)
    target_minutes = min(max(elapsed_minutes, 0), total_minutes)
    delta_minutes = max(target_minutes - resolved_minutes, 0)

    if delta_minutes <= 0:
        if now >= end_at and resolved_minutes >= total_minutes:
            upsert_profile(
                tg,
                retreat_started_at=None,
                retreat_end_at=None,
                retreat_gain_per_minute=0,
                retreat_cost_per_minute=0,
                retreat_minutes_total=0,
                retreat_minutes_resolved=0,
            )
        return None

    gain_per_minute = max(int(profile.retreat_gain_per_minute or 0), 0)
    cost_per_minute = max(int(profile.retreat_cost_per_minute or 0), 0)
    affordable_minutes = delta_minutes
    insufficient_stone = False
    if cost_per_minute > 0:
        # 灵石不足时只结算当前能支付的分钟数，避免把剩余闭关进度直接跳过。
        available_stone = max(int(get_shared_spiritual_stone_total(tg) or 0), 0)
        affordable_minutes = min(delta_minutes, available_stone // cost_per_minute)
        insufficient_stone = affordable_minutes < delta_minutes

    if affordable_minutes <= 0:
        if insufficient_stone or now >= end_at:
            with Session() as session:
                updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
                if updated is None:
                    return None
                updated.retreat_started_at = None
                updated.retreat_end_at = None
                updated.retreat_gain_per_minute = 0
                updated.retreat_cost_per_minute = 0
                updated.retreat_minutes_total = 0
                updated.retreat_minutes_resolved = 0
                updated.updated_at = utcnow()
                session.commit()
            return {
                "gain": 0,
                "cost": 0,
                "upgraded_layers": [],
                "remaining": 0,
                "finished": True,
                "insufficient_stone": True,
                "profile": serialize_profile(updated),
            }
        return None

    gain = affordable_minutes * gain_per_minute
    cost = affordable_minutes * cost_per_minute
    layer, cultivation, upgraded_layers, remaining = apply_cultivation_gain(
        normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE),
        int(profile.realm_layer or 1),
        int(profile.cultivation or 0),
        gain,
    )

    settled_minutes = min(resolved_minutes + affordable_minutes, total_minutes)
    finished = insufficient_stone or settled_minutes >= total_minutes or now >= end_at
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if updated is None:
            return None
        if cost > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -cost,
                action_text="闭关消耗灵石",
                enforce_currency_lock=True,
                allow_dead=False,
                apply_tribute=False,
            )
        updated.cultivation = cultivation
        updated.realm_layer = layer
        updated.retreat_minutes_resolved = 0 if finished else settled_minutes
        updated.retreat_started_at = None if finished else profile.retreat_started_at
        updated.retreat_end_at = None if finished else profile.retreat_end_at
        updated.retreat_gain_per_minute = 0 if finished else int(profile.retreat_gain_per_minute or 0)
        updated.retreat_cost_per_minute = 0 if finished else int(profile.retreat_cost_per_minute or 0)
        updated.retreat_minutes_total = 0 if finished else total_minutes
        updated.updated_at = utcnow()
        session.commit()

    return {
        "gain": gain,
        "cost": cost,
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "finished": finished,
        "insufficient_stone": insufficient_stone,
        "profile": serialize_profile(updated),
    }


def ensure_not_in_retreat(tg: int) -> None:
    profile = get_profile(tg, create=False)
    if profile is not None:
        _assert_gender_ready(profile, "执行当前操作")
    if profile is not None and _is_retreating(profile):
        raise ValueError("你正在闭关中，当前不能执行这个操作。")


def build_plugin_url(path: str) -> str | None:
    from bot.plugins.sdk import build_plugin_url as sdk_build_plugin_url

    return sdk_build_plugin_url(path)


def xiuxian_entry_button() -> InlineKeyboard:
    return ikb([[("初入仙途", "xiuxian:entry")]])


def xiuxian_confirm_keyboard() -> InlineKeyboard:
    app_url = build_plugin_url("/plugins/xiuxian/app")
    rows = [[("确认入道", "xiuxian:confirm"), ("返回", "back_start")]]
    if app_url:
        rows.append([("打开修仙面板", app_url, "url")])
    return ikb(rows)


def xiuxian_profile_keyboard() -> InlineKeyboard:
    app_url = build_plugin_url("/plugins/xiuxian/app")
    rows = [[("吐纳修炼", "xiuxian:train"), ("尝试突破", "xiuxian:break")]]
    if app_url:
        rows.append([("打开修仙面板", app_url, "url")])
    rows.append([("返回主页", "back_start")])
    return ikb(rows)


def leaderboard_keyboard(kind: str, page: int, total_pages: int) -> InlineKeyboard:
    keyboard = InlineKeyboard()
    keyboard.row(
        InlineButton("灵石榜", "xiuxian:rank:stone:1"),
        InlineButton("境界榜", "xiuxian:rank:realm:1"),
        InlineButton("法宝榜", "xiuxian:rank:artifact:1"),
    )
    pager = []
    if page > 1:
        pager.append(InlineButton("上一页", f"xiuxian:rank:{kind}:{page - 1}"))
    pager.append(InlineButton(f"{page}/{max(total_pages, 1)}", "xiuxian:noop"))
    if page < total_pages:
        pager.append(InlineButton("下一页", f"xiuxian:rank:{kind}:{page + 1}"))
    keyboard.row(*pager)
    return keyboard


def duel_keyboard(challenger_tg: int, defender_tg: int, stake: int, bet_seconds: int, duel_mode: str = "standard") -> InlineKeyboard:
    mode = _normalize_duel_mode(duel_mode)
    accept_label = {
        "standard": "🟢 接受斗法",
        "master": "⛓️ 接下炉鼎契",
        "death": "☠️ 立下血契",
    }.get(mode, "🟢 接受斗法")
    return ikb(
        [
            [
                (accept_label, f"xiuxian:duel:accept:{mode}:{challenger_tg}:{defender_tg}:{stake}:{bet_seconds}"),
                ("🚫 拒绝", f"xiuxian:duel:reject:{mode}:{challenger_tg}:{defender_tg}:{stake}:{bet_seconds}"),
            ],
            [
                ("🛑 发起者撤销", f"xiuxian:duel:cancel:{mode}:{challenger_tg}:{defender_tg}:{stake}:{bet_seconds}"),
            ],
        ]
    )


def cultivation_threshold(stage: str, layer: int) -> int:
    return calculate_realm_threshold(stage, layer)


def next_realm_stage(stage: str) -> str | None:
    idx = realm_index(stage)
    if idx >= len(REALM_ORDER) - 1:
        return None
    return REALM_ORDER[idx + 1]


def determine_relation(primary: str, secondary: str) -> tuple[str, int]:
    if ELEMENT_GENERATES.get(primary) == secondary or ELEMENT_GENERATES.get(secondary) == primary:
        return "相生", 5
    if ELEMENT_CONTROLS.get(primary) == secondary or ELEMENT_CONTROLS.get(secondary) == primary:
        return "相克", -5
    return "平衡", 0


def ensure_xiuxian_profile(tg: int) -> dict[str, Any]:
    profile = get_profile(tg, create=True)
    return serialize_profile(profile)


def _legacy_serialize_full_profile(tg: int) -> dict[str, Any]:
    ensure_seed_data()
    profile = _repair_profile_realm_state(tg)
    if profile is None:
        profile = get_profile(tg, create=True)
    if profile and profile.consented:
        _settle_retreat_progress(tg)
        _apply_profile_growth_floor(tg)
        profile = _repair_profile_realm_state(tg) or get_profile(tg, create=False)

    profile_data = serialize_profile(profile)
    if profile_data is None:
        raise ValueError("未找到修仙档案。")
    raw_spiritual_stone = int(profile_data.get("spiritual_stone") or 0)
    shared_spiritual_stone = (
        get_shared_spiritual_stone_total(tg)
        if profile_data.get("consented")
        else raw_spiritual_stone
    )
    profile_data["personal_spiritual_stone"] = raw_spiritual_stone
    profile_data["spiritual_stone"] = shared_spiritual_stone

    progress = build_progress(
        profile_data["realm_stage"],
        int(profile_data["realm_layer"] or 1),
        int(profile_data["cultivation"] or 0),
    )
    retreating = _is_retreating(profile)
    xiuxian_settings = get_xiuxian_settings()
    equip_limit = max(int(xiuxian_settings.get("artifact_equip_limit", DEFAULT_SETTINGS["artifact_equip_limit"]) or 0), 1)
    equipped_rows = list_equipped_artifacts(tg)
    artifact_set_map = _artifact_set_index()
    equipped = []
    equipped_ids: set[int] = set()
    equipped_slot_names: set[str] = set()
    for row in equipped_rows:
        item = _decorate_artifact_with_set(row["artifact"], artifact_set_map)
        item["resolved_effects"] = resolve_artifact_effects(profile_data, item)
        item["equipped"] = True
        item["slot"] = row["slot"]
        equipped.append(item)
        equipped_ids.add(int(item["id"]))
        equipped_slot = normalize_artifact_slot(item.get("equip_slot"))
        if equipped_slot:
            equipped_slot_names.add(equipped_slot)
    active_talisman = serialize_talisman(get_talisman(profile.active_talisman_id)) if profile and profile.active_talisman_id else None
    if active_talisman:
        active_talisman["resolved_effects"] = resolve_talisman_effects(profile_data, active_talisman)
        active_talisman["active_effects"] = resolve_talisman_active_effects(profile_data, active_talisman)
        active_talisman["active_effect_summary"] = active_talisman_effect_summary(active_talisman["active_effects"])
    current_technique = _current_technique_payload(profile_data)
    current_title = get_current_title(tg)
    if current_title:
        current_title["resolved_effects"] = resolve_title_effects(profile_data, current_title)
    profile_data["current_title_name"] = (current_title or {}).get("name")
    profile_data["display_name_with_title"] = _profile_name_with_title(profile_data, current_title)
    profile_data["is_dead"] = bool(profile_data.get("death_at"))
    profile_data["social_mode"] = profile_social_mode(profile_data)
    profile_data["social_mode_label"] = SOCIAL_MODE_LABELS.get(profile_data["social_mode"], "入世")
    profile_data["is_secluded"] = profile_data["social_mode"] == "secluded"
    master_profile = serialize_profile(get_profile(int(profile_data["master_tg"]), create=False)) if profile_data.get("master_tg") else None
    slave_profiles = [_decorate_furnace_profile_for_owner(profile_data, row) for row in list_slave_profiles(tg)]
    profile_data["master_name"] = (master_profile or {}).get("display_label")
    profile_data["slave_names"] = [item.get("display_label") or f"TG {item.get('tg')}" for item in slave_profiles]
    gender_lock_reason = _gender_lock_reason(profile_data)
    gender_locked = bool(gender_lock_reason)
    profile_data["furnace_harvested_today"] = is_same_china_day(profile.furnace_harvested_at, utcnow())
    rebirth_cooldown = _rebirth_cooldown_state(profile_data, xiuxian_settings)
    profile_data["rebirth_cooldown_enabled"] = rebirth_cooldown["enabled"]
    profile_data["rebirth_cooldown_hours"] = rebirth_cooldown["cooldown_hours"]
    profile_data["rebirth_cooldown_remaining_seconds"] = rebirth_cooldown["remaining_seconds"]
    profile_data["rebirth_available_at"] = rebirth_cooldown["available_at"]
    profile_data["rebirth_locked"] = rebirth_cooldown["blocked"]
    profile_data["rebirth_cooldown_reason"] = rebirth_cooldown["reason"]

    artifact_set_bundle = _resolve_active_artifact_sets(equipped)
    artifacts = build_user_artifact_rows(profile_data, tg, retreating, equip_limit, equipped_ids, equipped_slot_names)
    techniques = _build_user_technique_rows(profile_data, tg)
    pills = []
    for row in list_user_pills(tg):
        item = row["pill"]
        item["resolved_effects"] = resolve_pill_effects(profile_data, item)
        reason = _pill_usage_reason(profile_data, item)
        usable = not reason
        batch_usable = _pill_supports_batch_use(item)
        row["pill"]["usable"] = usable
        row["pill"]["unusable_reason"] = reason
        row["pill"]["batch_usable"] = batch_usable
        row["pill"]["batch_use_max"] = _pill_batch_use_max(profile_data, item, row.get("quantity"))
        row["pill"]["batch_use_note"] = _pill_batch_use_note(item)
        pills.append(row)

    talismans = []
    for row in list_user_talismans(tg):
        total_quantity = max(int(row.get("quantity") or 0), 0)
        bound_quantity = max(min(int(row.get("bound_quantity") or 0), total_quantity), 0)
        item = row["talisman"]
        item["resolved_effects"] = resolve_talisman_effects(profile_data, item)
        item["active_effects"] = resolve_talisman_active_effects(profile_data, item)
        item["active_effect_summary"] = active_talisman_effect_summary(item["active_effects"])
        usable = realm_requirement_met(profile_data, item.get("min_realm_stage"), item.get("min_realm_layer"))
        reason = "" if usable else f"需要达到 {format_realm_requirement(item.get('min_realm_stage'), item.get('min_realm_layer'))}"
        row["bound_quantity"] = bound_quantity
        row["unbound_quantity"] = max(total_quantity - bound_quantity, 0)
        row["consumable_quantity"] = row["unbound_quantity"]
        row["tradeable_quantity"] = row["unbound_quantity"]
        item["usable"] = usable and not retreating
        item["active"] = profile_data.get("active_talisman_id") == item["id"]
        item["unusable_reason"] = "闭关之中，法力内收，不宜引动符箓外力。" if usable and not item["active"] and retreating else reason
        item["bound"] = bound_quantity > 0
        item["bound_quantity"] = bound_quantity
        talismans.append(row)

    materials = list_user_materials(tg)

    titles = []
    current_title_id = int(profile_data.get("current_title_id") or 0)
    for row in list_user_titles(tg):
        title = row.get("title") or {}
        title["resolved_effects"] = resolve_title_effects(profile_data, title)
        title["equipped"] = int(title.get("id") or 0) == current_title_id
        title["action_label"] = "卸下称号" if title["equipped"] else "佩戴称号"
        row["title"] = title
        titles.append(row)

    achievement_overview = build_user_achievement_overview(tg)

    all_personal_shop = list_shop_items(official_only=False)
    personal_shop = [item for item in all_personal_shop if item["owner_tg"] == tg]
    community_shop = [item for item in all_personal_shop if item["owner_tg"] not in {None, tg}]
    all_active_auctions = list_auction_items(status="active")
    personal_auctions = list_auction_items(owner_tg=tg, include_inactive=True, limit=20)
    community_auctions = [item for item in all_active_auctions if int(item.get("owner_tg") or 0) != int(tg)]
    settings = {
        **get_exchange_settings(),
        "coin_stone_exchange_enabled": bool(
            xiuxian_settings.get("coin_stone_exchange_enabled", DEFAULT_SETTINGS.get("coin_stone_exchange_enabled", True))
        ),
        "artifact_equip_limit": equip_limit,
        "equipment_unbind_cost": int(xiuxian_settings.get("equipment_unbind_cost", DEFAULT_SETTINGS["equipment_unbind_cost"]) or 0),
        "artifact_plunder_chance": int(
            xiuxian_settings.get("artifact_plunder_chance", DEFAULT_SETTINGS["artifact_plunder_chance"]) or 0
        ),
        "duel_invite_timeout_seconds": max(
            int(xiuxian_settings.get("duel_invite_timeout_seconds", DEFAULT_SETTINGS["duel_invite_timeout_seconds"]) or 0),
            10,
        ),
        "duel_winner_steal_percent": int(
            xiuxian_settings.get("duel_winner_steal_percent", DEFAULT_SETTINGS["duel_winner_steal_percent"]) or 0
        ),
        "official_shop_name": str(xiuxian_settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"]) or DEFAULT_SETTINGS["official_shop_name"]),
        "auction_fee_percent": max(int(xiuxian_settings.get("auction_fee_percent", DEFAULT_SETTINGS["auction_fee_percent"]) or 0), 0),
        "auction_duration_minutes": max(int(xiuxian_settings.get("auction_duration_minutes", DEFAULT_SETTINGS["auction_duration_minutes"]) or 0), 1),
        "allow_user_task_publish": bool(xiuxian_settings.get("allow_user_task_publish", DEFAULT_SETTINGS["allow_user_task_publish"])),
        "task_publish_cost": max(int(xiuxian_settings.get("task_publish_cost", DEFAULT_SETTINGS["task_publish_cost"]) or 0), 0),
        "user_task_daily_limit": max(int(xiuxian_settings.get("user_task_daily_limit", DEFAULT_SETTINGS["user_task_daily_limit"]) or 0), 0),
        "slave_tribute_percent": max(int(xiuxian_settings.get("slave_tribute_percent", DEFAULT_SETTINGS["slave_tribute_percent"]) or 0), 0),
        "slave_challenge_cooldown_hours": max(int(xiuxian_settings.get("slave_challenge_cooldown_hours", DEFAULT_SETTINGS["slave_challenge_cooldown_hours"]) or 0), 1),
        "rebirth_cooldown_enabled": bool(xiuxian_settings.get("rebirth_cooldown_enabled", DEFAULT_SETTINGS["rebirth_cooldown_enabled"])),
        "rebirth_cooldown_base_hours": min(
            max(
                int(xiuxian_settings.get("rebirth_cooldown_base_hours", DEFAULT_SETTINGS["rebirth_cooldown_base_hours"]) or 0),
                0,
            ),
            8760,
        ),
        "rebirth_cooldown_increment_hours": min(
            max(
                int(
                    xiuxian_settings.get(
                        "rebirth_cooldown_increment_hours",
                        DEFAULT_SETTINGS["rebirth_cooldown_increment_hours"],
                    )
                    or 0
                ),
                0,
            ),
            8760,
        ),
        "furnace_harvest_cultivation_percent": max(int(xiuxian_settings.get("furnace_harvest_cultivation_percent", DEFAULT_SETTINGS["furnace_harvest_cultivation_percent"]) or 0), 0),
        "sect_salary_min_stay_days": max(int(xiuxian_settings.get("sect_salary_min_stay_days", DEFAULT_SETTINGS["sect_salary_min_stay_days"]) or 0), 1),
        "sect_betrayal_cooldown_days": max(int(xiuxian_settings.get("sect_betrayal_cooldown_days", DEFAULT_SETTINGS["sect_betrayal_cooldown_days"]) or 0), 1),
        "sect_betrayal_stone_percent": max(int(xiuxian_settings.get("sect_betrayal_stone_percent", DEFAULT_SETTINGS["sect_betrayal_stone_percent"]) or 0), 0),
        "sect_betrayal_stone_min": max(int(xiuxian_settings.get("sect_betrayal_stone_min", DEFAULT_SETTINGS["sect_betrayal_stone_min"]) or 0), 0),
        "sect_betrayal_stone_max": max(int(xiuxian_settings.get("sect_betrayal_stone_max", DEFAULT_SETTINGS["sect_betrayal_stone_max"]) or 0), 0),
        "error_log_retention_count": max(int(xiuxian_settings.get("error_log_retention_count", DEFAULT_SETTINGS["error_log_retention_count"]) or 0), 1),
        "seclusion_cultivation_efficiency_percent": seclusion_cultivation_efficiency_percent(xiuxian_settings),
    }
    active_duel_lock = get_active_duel_lock(tg)
    breakthrough_requirement = _breakthrough_requirement(profile_data.get("realm_stage"))
    attribute_effects = [
        {
            "key": key,
            "label": label,
            "value": int(profile_data.get(key) or 0),
            "effective_value": int(profile_data.get(key) or 0),
            "effect": ATTRIBUTE_EFFECT_HINTS.get(key, ""),
        }
        for key, label in (
            ("bone", "根骨"),
            ("comprehension", "悟性"),
            ("divine_sense", "神识"),
            ("fortune", "机缘"),
            ("willpower", "心志"),
            ("charisma", "魅力"),
            ("karma", "因果"),
            ("qi_blood", "气血"),
            ("true_yuan", "真元"),
            ("body_movement", "身法"),
            ("attack_power", "攻击"),
            ("defense_power", "防御"),
        )
    ]

    capabilities = {
        "can_train": profile_data["consented"] and not profile_data["is_dead"] and not gender_locked and not retreating and not is_same_china_day(profile.last_train_at, utcnow()),
        "train_reason": (
            gender_lock_reason
            if gender_locked
            else (
                "角色已死亡，只能重新踏出仙途"
                if profile_data["is_dead"]
                else ("" if not retreating and not is_same_china_day(profile.last_train_at, utcnow()) else ("闭关之中，心神内敛，无暇吐纳外气。" if retreating else "今日吐纳已毕，经脉已盈，再行运气恐伤道基。"))
            )
        ),
        "can_breakthrough": profile_data["consented"] and not profile_data["is_dead"] and not gender_locked and not retreating and int(profile_data["realm_layer"] or 0) >= 9 and bool(progress["breakthrough_ready"]),
        "breakthrough_reason": (
            gender_lock_reason
            if gender_locked
            else (
                "角色已死亡，只能重新踏出仙途"
                if profile_data["is_dead"]
                else ("" if not retreating and int(profile_data["realm_layer"] or 0) >= 9 and progress["breakthrough_ready"] else ("闭关之中，气机未满，尚难叩问破境之机。" if retreating else "只有达到当前境界九层且满修为后才能突破"))
            )
        ),
        "required_breakthrough_pill_name": (breakthrough_requirement or {}).get("pill_name"),
        "required_breakthrough_scene_name": (breakthrough_requirement or {}).get("scene_name"),
        "can_retreat": profile_data["consented"] and not profile_data["is_dead"] and not gender_locked and not retreating,
        "retreat_reason": gender_lock_reason if gender_locked else ("角色已死亡，只能重新踏出仙途" if profile_data["is_dead"] else ("" if not retreating else "你正在闭关中")),
        "is_in_retreat": retreating,
        "is_dead": profile_data["is_dead"],
        "death_reason": rebirth_cooldown["reason"] if rebirth_cooldown["blocked"] else ("角色已死亡，只能重新踏出仙途" if profile_data["is_dead"] else ""),
        "can_enter_path": not profile_data["consented"] and not rebirth_cooldown["blocked"],
        "enter_reason": rebirth_cooldown["reason"],
        "rebirth_locked": rebirth_cooldown["blocked"],
        "social_mode": profile_data["social_mode"],
        "social_mode_label": profile_data["social_mode_label"],
        "is_secluded": profile_data["is_secluded"],
        "can_toggle_social_mode": profile_data["consented"] and not profile_data["is_dead"] and not gender_locked,
        "social_mode_toggle_reason": gender_lock_reason if gender_locked else ("角色已死亡，只能重新踏出仙途" if profile_data["is_dead"] else ""),
        "social_interaction_lock_reason": (
            gender_lock_reason
            if gender_locked
            else (
                f"你当前处于避世状态，对外互动已关闭，修为收益按 {settings['seclusion_cultivation_efficiency_percent']}% 结算。"
                if profile_data["is_secluded"]
                else ""
            )
        ),
        "gender_required": gender_locked,
        "gender_lock_reason": gender_lock_reason,
        "shared_spiritual_stone_total": shared_spiritual_stone,
        "shared_inventory_enabled": False,
        "shared_inventory_note": (
            "结为道侣后，灵石与背包会自动共享。"
            if not gender_locked
            else ""
        ),
        "artifact_equip_limit": equip_limit,
        "equipped_artifact_count": len(equipped),
        "duel_locked": bool(active_duel_lock),
        "duel_lock": active_duel_lock,
        "duel_lock_reason": "" if not active_duel_lock else f"{active_duel_lock['duel_mode_label']}结算前，禁止灵石与交易操作",
    }

    return {
        "profile": profile_data,
        "progress": progress,
        "capabilities": capabilities,
        "emby_balance": get_emby_balance(tg),
        "equipped_artifact": equipped[0] if equipped else None,
        "equipped_artifacts": equipped,
        "active_talisman": active_talisman,
        "current_technique": current_technique,
        "current_title": current_title,
        "active_artifact_sets": artifact_set_bundle["sets"],
        "artifacts": artifacts,
        "pills": pills,
        "talismans": talismans,
        "materials": materials,
        "techniques": techniques,
        "recipes": list_user_recipes(tg, enabled_only=False),
        "technique_owned_count": len(techniques),
        "technique_total_count": len(list_techniques(enabled_only=True)),
        "titles": titles,
        "achievements": achievement_overview.get("achievements") or [],
        "achievement_metric_progress": achievement_overview.get("metric_progress") or {},
        "achievement_unlocked_count": int(achievement_overview.get("unlocked_count") or 0),
        "achievement_total_count": int(achievement_overview.get("total_count") or 0),
        "attribute_effects": attribute_effects,
        "master_profile": master_profile,
        "slave_profiles": slave_profiles,
        "settings": settings,
        "official_shop": list_shop_items(official_only=True),
        "community_shop": community_shop,
        "personal_shop": personal_shop,
        "community_auctions": community_auctions,
        "personal_auctions": personal_auctions,
    }


def _find_pill_in_inventory(tg: int, pill_type: str) -> dict[str, Any] | None:
    for row in list_user_pills(tg):
        pill = row["pill"]
        if pill["pill_type"] == pill_type and row["quantity"] > 0:
            return row
    return None


def _find_pill_in_inventory_by_name(tg: int, pill_name: str) -> dict[str, Any] | None:
    target_name = str(pill_name or "").strip()
    if not target_name:
        return None
    for row in list_user_pills(tg):
        pill = row["pill"] or {}
        if str(pill.get("name") or "").strip() == target_name and int(row.get("quantity") or 0) > 0:
            return row
    return None


def _gender_lock_reason(profile: XiuxianProfile | dict[str, Any] | None) -> str:
    if profile is None:
        return "请先设置性别。"
    if isinstance(profile, dict):
        if profile.get("gender_set"):
            return ""
        consented = bool(profile.get("consented"))
    else:
        if normalize_gender(getattr(profile, "gender", None)):
            return ""
        consented = bool(getattr(profile, "consented", False))
    if not consented:
        return ""
    return "请先在姻缘面板设置性别，设置后才能继续使用修仙玩法。"


def _assert_gender_ready(profile: XiuxianProfile | dict[str, Any] | None, action_text: str) -> None:
    reason = _gender_lock_reason(profile)
    if reason:
        raise ValueError(reason)


def _require_consented_profile_obj(tg: int, action_text: str) -> Any:
    profile = _repair_profile_realm_state(tg)
    if profile is None or not profile.consented:
        raise ValueError("你尚未踏入仙途，道基未立。")
    assert_profile_alive(profile, action_text)
    return profile


def _require_alive_profile_obj(tg: int, action_text: str) -> Any:
    profile = _require_consented_profile_obj(tg, action_text)
    _assert_gender_ready(profile, action_text)
    return profile


def profile_social_mode(profile: Any | dict[str, Any] | None) -> str:
    if isinstance(profile, dict):
        return normalize_social_mode(profile.get("social_mode"))
    return normalize_social_mode(getattr(profile, "social_mode", None))


def is_profile_secluded(profile: Any | dict[str, Any] | None) -> bool:
    return profile_social_mode(profile) == "secluded"


def seclusion_cultivation_efficiency_percent(settings: dict[str, Any] | None = None) -> int:
    source = settings or get_xiuxian_settings()
    raw = source.get(
        "seclusion_cultivation_efficiency_percent",
        DEFAULT_SETTINGS["seclusion_cultivation_efficiency_percent"],
    )
    return min(max(int(raw or 0), 0), 100)


def adjust_cultivation_gain_for_social_mode(
    profile: Any | dict[str, Any] | None,
    gain: int,
    *,
    settings: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    base_gain = max(int(gain or 0), 0)
    mode = profile_social_mode(profile)
    efficiency_percent = 100 if mode != "secluded" else seclusion_cultivation_efficiency_percent(settings)
    effective_gain = base_gain
    if mode == "secluded":
        effective_gain = int(round(base_gain * efficiency_percent / 100.0))
        if base_gain > 0 and efficiency_percent > 0:
            effective_gain = max(effective_gain, 1)
    effective_gain = max(effective_gain, 0)
    return effective_gain, {
        "base_gain": base_gain,
        "effective_gain": effective_gain,
        "mode": mode,
        "mode_label": SOCIAL_MODE_LABELS.get(mode, "入世"),
        "efficiency_percent": efficiency_percent,
        "reduced": effective_gain != base_gain,
    }


def _social_action_error(profile: Any | dict[str, Any] | None, action_text: str, *, actor: bool) -> None:
    if not is_profile_secluded(profile):
        return
    display_label = ""
    if isinstance(profile, dict):
        display_label = str(profile.get("display_label") or "").strip()
    else:
        display_name = getattr(profile, "display_name", None)
        username = getattr(profile, "username", None)
        if display_name:
            display_label = str(display_name).strip()
        elif username:
            display_label = f"@{username}"
    if actor:
        raise ValueError(f"你当前处于避世状态，无法进行{action_text}。")
    if display_label:
        raise ValueError(f"{display_label} 当前处于避世状态，无法进行{action_text}。")
    raise ValueError(f"对方当前处于避世状态，无法进行{action_text}。")


def assert_social_action_allowed(
    actor_profile: Any | dict[str, Any] | None,
    target_profile: Any | dict[str, Any] | None,
    action_text: str,
) -> None:
    _social_action_error(actor_profile, action_text, actor=True)
    _social_action_error(target_profile, action_text, actor=False)


def switch_social_mode_for_user(tg: int, social_mode: str) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "切换入世状态")
    target_mode = normalize_social_mode(social_mode)
    current_mode = profile_social_mode(profile)
    if current_mode == target_mode:
        return {
            "changed": False,
            "social_mode": target_mode,
            "social_mode_label": SOCIAL_MODE_LABELS.get(target_mode, "入世"),
            "profile": serialize_full_profile(tg),
        }

    updated = upsert_profile(
        tg,
        social_mode=target_mode,
        social_mode_updated_at=utcnow(),
    )
    create_journal(
        tg,
        "social_mode",
        "切换入世状态",
        f"由【{SOCIAL_MODE_LABELS.get(current_mode, '入世')}】切换为【{SOCIAL_MODE_LABELS.get(target_mode, '入世')}】。",
    )
    return {
        "changed": True,
        "social_mode": target_mode,
        "social_mode_label": SOCIAL_MODE_LABELS.get(target_mode, "入世"),
        "profile": serialize_full_profile(updated.tg),
    }


def harvest_furnace_for_user(tg: int, furnace_tg: int) -> dict[str, Any]:
    actor_tg = int(tg)
    target_tg = int(furnace_tg)
    if actor_tg <= 0 or target_tg <= 0:
        raise ValueError("采补对象无效。")
    if actor_tg == target_tg:
        raise ValueError("你不能采补自己。")

    now = utcnow()
    settings = get_xiuxian_settings()
    with Session() as session:
        owner = session.query(XiuxianProfile).filter(XiuxianProfile.tg == actor_tg).with_for_update().first()
        if owner is None or not owner.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        assert_profile_alive(owner, "采补炉鼎")
        furnace = session.query(XiuxianProfile).filter(XiuxianProfile.tg == target_tg).with_for_update().first()
        if furnace is None or not furnace.consented:
            raise ValueError("对方还没有踏入仙途。")
        furnace_name = _profile_display_label(furnace, "该炉鼎")
        if furnace.death_at is not None:
            raise ValueError(f"{furnace_name} 当前已身死道消，无法继续采补。")
        reason = _furnace_harvest_reason(owner, furnace, settings=settings, now=now)
        if reason:
            raise ValueError(reason)

        preview = _furnace_harvest_preview(owner, furnace, settings=settings)
        if preview["furnace_loss"] <= 0 or preview["master_gain_raw"] <= 0:
            raise ValueError(f"{furnace_name} 当前修为过低，暂无可采补收益。")

        owner_layer, owner_cultivation, upgraded_layers, remaining = apply_cultivation_gain(
            normalize_realm_stage(owner.realm_stage or FIRST_REALM_STAGE),
            int(owner.realm_layer or 1),
            int(owner.cultivation or 0),
            preview["master_gain_raw"],
        )
        furnace_layer, furnace_cultivation, actual_loss = _apply_stage_cultivation_loss(
            normalize_realm_stage(furnace.realm_stage or FIRST_REALM_STAGE),
            int(furnace.realm_layer or 1),
            int(furnace.cultivation or 0),
            preview["furnace_loss"],
        )
        furnace.realm_layer = furnace_layer
        furnace.cultivation = furnace_cultivation
        furnace.furnace_harvested_at = now
        furnace.updated_at = now
        owner.realm_layer = owner_layer
        owner.cultivation = owner_cultivation
        owner.updated_at = now
        _queue_servitude_cache_invalidation(session, actor_tg, target_tg)
        session.commit()
        owner_name = _profile_display_label(owner, "主人")
        furnace_realm_text = f"{normalize_realm_stage(furnace.realm_stage or FIRST_REALM_STAGE)}{max(int(furnace.realm_layer or 1), 1)}层"
        owner_realm_text = f"{normalize_realm_stage(owner.realm_stage or FIRST_REALM_STAGE)}{owner_layer}层"

    create_journal(
        actor_tg,
        "furnace",
        "采补炉鼎",
        f"今日从 {furnace_name} 身上采补一次，抽取其 {actual_loss} 点本境修为，折算为自身 {preview['master_gain_raw']} 点修为。",
    )
    create_journal(
        target_tg,
        "furnace",
        "被主人采补",
        f"{owner_name} 今日对你采补一次，你流失了 {actual_loss} 点本境修为。",
    )
    return {
        "owner_tg": actor_tg,
        "owner_name": owner_name,
        "owner_realm_text": owner_realm_text,
        "furnace_tg": target_tg,
        "furnace_name": furnace_name,
        "furnace_realm_text": furnace_realm_text,
        "harvest_percent": preview["harvest_percent"],
        "furnace_loss": preview["furnace_loss"],
        "master_gain": preview["master_gain_raw"],
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "harvested_at": serialize_datetime(now),
        "message": f"你与 {furnace_name} 完成一次采补，抽取其 {actual_loss} 点本境修为，折算为自身 {preview['master_gain_raw']} 点修为。",
    }


MENTORSHIP_REQUEST_EXPIRE_HOURS = 72
MENTORSHIP_GRADUATE_BOND = 120
MENTORSHIP_GRADUATE_TEACH_COUNT = 5
MENTORSHIP_GRADUATE_CONSULT_COUNT = 3
MARRIAGE_REQUEST_EXPIRE_HOURS = 72


def _normalize_mentorship_action(action: str | None) -> str:
    value = str(action or "").strip().lower()
    aliases = {
        "accept": "accept",
        "agree": "accept",
        "同意": "accept",
        "reject": "reject",
        "decline": "reject",
        "refuse": "reject",
        "拒绝": "reject",
        "cancel": "cancel",
        "revoke": "cancel",
        "撤回": "cancel",
    }
    return aliases.get(value, "accept")


def _mentorship_realm_score(profile: XiuxianProfile | dict[str, Any]) -> int:
    if isinstance(profile, dict):
        stage = profile.get("realm_stage")
        layer = profile.get("realm_layer")
    else:
        stage = profile.realm_stage
        layer = profile.realm_layer
    return max(realm_index(stage), 0) * 10 + max(int(layer or 0), 0)


def _mentorship_capacity(profile: XiuxianProfile | dict[str, Any]) -> int:
    score = _mentorship_realm_score(profile)
    base = 1 + max(score // 15, 0)
    return min(max(base, 1), 5)


def _mentorship_bond_label(value: int) -> str:
    bond = max(int(value or 0), 0)
    if bond >= 180:
        return "衣钵相承"
    if bond >= 120:
        return "心印相通"
    if bond >= 60:
        return "相知相授"
    if bond >= 20:
        return "渐入佳境"
    return "初结师缘"


def _mentorship_breakthrough_text(stage: str | None, upgraded_layers: list[int] | None) -> str:
    layers = [max(int(layer or 0), 0) for layer in (upgraded_layers or []) if int(layer or 0) > 0]
    if not layers:
        return ""
    normalized_stage = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    if len(layers) == 1:
        return f"，并突破至 {normalized_stage}{layers[0]} 层"
    return f"，并连破 {len(layers)} 层至 {normalized_stage}{layers[-1]} 层"


def _mentorship_pending_expire_at() -> datetime:
    return utcnow() + timedelta(hours=MENTORSHIP_REQUEST_EXPIRE_HOURS)


def _mentorship_profile_row(session: Session, tg: int, action_text: str) -> XiuxianProfile:
    row = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
    if row is None or not row.consented:
        raise ValueError("你尚未踏入仙途，道基未立。")
    assert_profile_alive(row, action_text)
    _assert_gender_ready(row, action_text)
    return row


def _ensure_target_profile_active(profile: XiuxianProfile | None, fallback: str = "对方") -> XiuxianProfile:
    if profile is None or not profile.consented:
        raise ValueError(f"{fallback}还没有踏入仙途。")
    if profile.death_at is not None:
        label = str(profile.display_name or (f"@{profile.username}" if profile.username else fallback)).strip() or fallback
        raise ValueError(f"{label} 当前已身死道消，无法结下新的师徒因果。")
    _assert_gender_ready(profile, f"{fallback}参与互动")
    return profile


def _expire_pending_mentorship_requests(session: Session) -> int:
    now = utcnow()
    rows = (
        session.query(XiuxianMentorshipRequest)
        .filter(
            XiuxianMentorshipRequest.status == "pending",
            XiuxianMentorshipRequest.expires_at.isnot(None),
            XiuxianMentorshipRequest.expires_at <= now,
        )
        .all()
    )
    for row in rows:
        row.status = "expired"
        row.responded_at = now
        row.updated_at = now
    return len(rows)


def _active_mentor_relations(session: Session, mentor_tg: int, *, for_update: bool = False) -> list[XiuxianMentorship]:
    query = session.query(XiuxianMentorship).filter(
        XiuxianMentorship.mentor_tg == int(mentor_tg),
        XiuxianMentorship.status == "active",
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianMentorship.created_at.asc(), XiuxianMentorship.id.asc()).all()


def _active_mentorship_for_disciple(session: Session, disciple_tg: int, *, for_update: bool = False) -> XiuxianMentorship | None:
    query = session.query(XiuxianMentorship).filter(
        XiuxianMentorship.disciple_tg == int(disciple_tg),
        XiuxianMentorship.status == "active",
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianMentorship.created_at.desc(), XiuxianMentorship.id.desc()).first()


def _pair_mentorship(
    session: Session,
    mentor_tg: int,
    disciple_tg: int,
    *,
    for_update: bool = False,
) -> XiuxianMentorship | None:
    query = session.query(XiuxianMentorship).filter(
        XiuxianMentorship.mentor_tg == int(mentor_tg),
        XiuxianMentorship.disciple_tg == int(disciple_tg),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianMentorship.id.desc()).first()


def _profile_display_label(profile: XiuxianProfile | dict[str, Any] | None, fallback: str = "道友") -> str:
    if profile is None:
        return fallback
    if isinstance(profile, dict):
        return (
            str(profile.get("display_name_with_title") or "").strip()
            or str(profile.get("display_label") or "").strip()
            or fallback
        )
    return (
        str(profile.display_name or "").strip()
        or (f"@{profile.username}" if profile.username else "")
        or fallback
    )


def _mentorship_chain_has_target(session: Session, start_tg: int, target_tg: int) -> bool:
    visited: set[int] = set()
    current = int(start_tg)
    while current and current not in visited:
        visited.add(current)
        relation = _active_mentorship_for_disciple(session, current)
        if relation is None:
            return False
        current = int(relation.mentor_tg or 0)
        if current == int(target_tg):
            return True
    return False


def _mentorship_profile_summary(profile: XiuxianProfile | dict[str, Any] | None, *, bundle: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = dict(profile) if isinstance(profile, dict) else serialize_profile(profile)
    if not data:
        return None
    title = bundle.get("current_title") if bundle and int((bundle.get("profile") or {}).get("tg") or 0) == int(data.get("tg") or 0) else None
    if title is None and data.get("current_title_id"):
        title = get_current_title(int(data["tg"]))
    display_name_with_title = _profile_name_with_title(data, title)
    combat_power = int(bundle.get("combat_power") or 0) if bundle and int((bundle.get("profile") or {}).get("tg") or 0) == int(data.get("tg") or 0) else int(round(_battle_bundle(data)["power"]))
    return {
        "tg": int(data.get("tg") or 0),
        "display_label": data.get("display_label") or f"TG {data.get('tg')}",
        "display_name_with_title": display_name_with_title,
        "username": data.get("username"),
        "realm_stage": data.get("realm_stage"),
        "realm_layer": int(data.get("realm_layer") or 0),
        "realm_text": f"{data.get('realm_stage') or '炼气'}{int(data.get('realm_layer') or 0)}层",
        "combat_power": combat_power,
        "social_mode": data.get("social_mode") or "worldly",
        "social_mode_label": data.get("social_mode_label") or SOCIAL_MODE_LABELS.get(data.get("social_mode") or "worldly", "入世"),
        "is_secluded": bool(data.get("is_secluded")),
        "current_title_name": (title or {}).get("name"),
    }


def _mentorship_validate_pair(
    session: Session,
    mentor_profile: XiuxianProfile,
    disciple_profile: XiuxianProfile,
) -> dict[str, Any]:
    mentor_tg = int(mentor_profile.tg or 0)
    disciple_tg = int(disciple_profile.tg or 0)
    if mentor_tg <= 0 or disciple_tg <= 0:
        raise ValueError("师徒目标无效。")
    if mentor_tg == disciple_tg:
        raise ValueError("不能自己和自己结为师徒。")
    _ensure_target_profile_active(mentor_profile, "师尊")
    _ensure_target_profile_active(disciple_profile, "徒弟")
    assert_social_action_allowed(mentor_profile, disciple_profile, "师徒往来")

    current_master = _active_mentorship_for_disciple(session, disciple_tg, for_update=True)
    if current_master is not None and int(current_master.mentor_tg or 0) != mentor_tg:
        raise ValueError("对方已有师尊，需先解除当前师门关系。")
    if current_master is not None and int(current_master.mentor_tg or 0) == mentor_tg:
        raise ValueError("双方当前已经是正式师徒，无需重复递交拜帖。")

    active_relations = _active_mentor_relations(session, mentor_tg, for_update=True)
    capacity = _mentorship_capacity(mentor_profile)
    if all(int(item.disciple_tg or 0) != disciple_tg for item in active_relations) and len(active_relations) >= capacity:
        raise ValueError(f"你当前最多只能带 {capacity} 名弟子，已没有空闲名额。")

    mentor_score = _mentorship_realm_score(mentor_profile)
    disciple_score = _mentorship_realm_score(disciple_profile)
    if mentor_score <= disciple_score:
        raise ValueError("师尊的境界至少需要高过弟子当前境界。")

    mentor_power = int(round(_battle_bundle(serialize_profile(mentor_profile) or {})["power"]))
    disciple_power = int(round(_battle_bundle(serialize_profile(disciple_profile) or {})["power"]))
    min_required_power = max(int(round(disciple_power * 1.15)), disciple_power + 120)
    if mentor_power < min_required_power:
        raise ValueError("师尊当前战力压制还不够稳妥，至少需要高出对方约 15% 才能收徒。")

    if _mentorship_chain_has_target(session, mentor_tg, disciple_tg):
        raise ValueError("当前传承链会形成循环师门，暂不允许这样结成师徒。")

    # 出师/解除关系后的冷却期内禁止重新结成师徒
    prior = (
        session.query(XiuxianMentorship)
        .filter(
            XiuxianMentorship.mentor_tg.in_([mentor_tg, disciple_tg]),
            XiuxianMentorship.disciple_tg.in_([mentor_tg, disciple_tg]),
            XiuxianMentorship.status.in_(["graduated", "dissolved"]),
            XiuxianMentorship.ended_at >= utcnow() - timedelta(days=30),
        )
        .first()
    )
    if prior is not None:
        label = "已出师" if normalize_mentorship_status(prior.status) == "graduated" else "已解除"
        raise ValueError(f"你们之间已有过师徒关系（{label}），请等待冷却期结束后再重新建立。")

    return {
        "mentor_score": mentor_score,
        "disciple_score": disciple_score,
        "mentor_power": mentor_power,
        "disciple_power": disciple_power,
        "capacity": capacity,
        "used_slots": len(active_relations),
    }


def _mentorship_graduation_state(relation: XiuxianMentorship, disciple_profile: XiuxianProfile) -> dict[str, Any]:
    start_score = max(
        realm_index(relation.disciple_realm_stage_snapshot) * 10 + max(int(relation.disciple_realm_layer_snapshot or 0), 0),
        0,
    )
    current_score = _mentorship_realm_score(disciple_profile)
    growth_score = max(current_score - start_score, 0)
    required_growth = 5
    ready = (
        int(relation.bond_value or 0) >= MENTORSHIP_GRADUATE_BOND
        and int(relation.teach_count or 0) >= MENTORSHIP_GRADUATE_TEACH_COUNT
        and int(relation.consult_count or 0) >= MENTORSHIP_GRADUATE_CONSULT_COUNT
        and growth_score >= required_growth
    )
    hint = (
        f"师徒缘 {int(relation.bond_value or 0)}/{MENTORSHIP_GRADUATE_BOND}，"
        f"传道 {int(relation.teach_count or 0)}/{MENTORSHIP_GRADUATE_TEACH_COUNT}，"
        f"问道 {int(relation.consult_count or 0)}/{MENTORSHIP_GRADUATE_CONSULT_COUNT}，"
        f"道行提升 {growth_score}/{required_growth}。"
    )
    return {
        "ready": ready,
        "hint": hint,
        "growth_score": growth_score,
        "required_growth": required_growth,
    }


def _roll_mentorship_consult_growth(mentor_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = mentor_stats if isinstance(mentor_stats, dict) else {}
    count = 1 + (1 if max(int(stats.get("comprehension") or 0), 0) >= 80 and random.randint(1, 100) <= 35 else 0)
    pool = ["comprehension", "divine_sense", "willpower", "fortune", "true_yuan"]
    random.shuffle(pool)
    patch: dict[str, int] = {}
    changes: list[dict[str, Any]] = []
    for key in pool[:count]:
        if key == "true_yuan":
            delta = random.randint(12, 24)
        else:
            delta = random.randint(1, 3)
        patch[key] = patch.get(key, 0) + delta
        changes.append({"key": key, "label": _attribute_growth_label(key), "value": delta})
    return {"patch": patch, "changes": changes}


def _apply_mentorship_titles(mentor_tg: int, disciple_tg: int) -> list[dict[str, Any]]:
    awarded: list[dict[str, Any]] = []
    mentor_title = sync_title_by_name(
        name="传道授业",
        description="讲道不倦，已能把门下弟子一路带到出师。",
        color="#2563eb",
        comprehension_bonus=5,
        true_yuan_bonus=36,
        cultivation_bonus=4,
        enabled=True,
    )
    disciple_title = sync_title_by_name(
        name="门下高徒",
        description="承其衣钵，终于凭本事独当一面。",
        color="#16a34a",
        comprehension_bonus=3,
        attack_bonus=2,
        defense_bonus=2,
        enabled=True,
    )
    mentor_grant = grant_title_to_user(mentor_tg, int(mentor_title["id"]), source="mentorship", auto_equip_if_empty=True)
    disciple_grant = grant_title_to_user(disciple_tg, int(disciple_title["id"]), source="mentorship", auto_equip_if_empty=True)
    awarded.append({"tg": mentor_tg, "title": (mentor_grant or {}).get("title") or mentor_title})
    awarded.append({"tg": disciple_tg, "title": (disciple_grant or {}).get("title") or disciple_title})
    return awarded


def build_mentorship_overview(tg: int, *, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    with Session() as session:
        expired = _expire_pending_mentorship_requests(session)
        if expired:
            session.commit()
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).first()
        if profile is None or not profile.consented:
            return {
                "self_profile": None,
                "mentor_relation": None,
                "disciple_relations": [],
                "incoming_requests": [],
                "outgoing_requests": [],
                "mentor_capacity": 0,
                "used_slots": 0,
                "available_slots": 0,
                "can_take_disciple": False,
                "can_seek_mentor": False,
                "request_hint": "踏入仙途后才可缔结师徒关系。",
            }

        mentor_relation = _active_mentorship_for_disciple(session, tg)
        disciple_relations = _active_mentor_relations(session, tg)
        request_rows = (
            session.query(XiuxianMentorshipRequest)
            .filter(
                XiuxianMentorshipRequest.status == "pending",
                (XiuxianMentorshipRequest.sponsor_tg == int(tg)) | (XiuxianMentorshipRequest.target_tg == int(tg)),
            )
            .order_by(XiuxianMentorshipRequest.created_at.desc(), XiuxianMentorshipRequest.id.desc())
            .all()
        )

        related_tgs = {int(tg)}
        if mentor_relation is not None:
            related_tgs.add(int(mentor_relation.mentor_tg or 0))
            related_tgs.add(int(mentor_relation.disciple_tg or 0))
        for row in disciple_relations:
            related_tgs.add(int(row.mentor_tg or 0))
            related_tgs.add(int(row.disciple_tg or 0))
        for row in request_rows:
            related_tgs.add(int(row.sponsor_tg or 0))
            related_tgs.add(int(row.target_tg or 0))
            payload = serialize_mentorship_request(row) or {}
            related_tgs.add(int(payload.get("mentor_tg") or 0))
            related_tgs.add(int(payload.get("disciple_tg") or 0))

        profile_rows = {
            int(row.tg): row
            for row in session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_([item for item in related_tgs if item > 0])).all()
        }
        profile_cards: dict[int, dict[str, Any] | None] = {}
        for related_tg in related_tgs:
            row = profile_rows.get(int(related_tg))
            if row is None:
                continue
            if bundle and int((bundle.get("profile") or {}).get("tg") or 0) == int(related_tg):
                profile_cards[int(related_tg)] = _mentorship_profile_summary(bundle.get("profile") or {}, bundle=bundle)
            else:
                profile_cards[int(related_tg)] = _mentorship_profile_summary(row)

        def relation_view(row: XiuxianMentorship) -> dict[str, Any]:
            payload = serialize_mentorship(row) or {}
            mentor_profile = profile_rows.get(int(row.mentor_tg or 0))
            disciple_profile = profile_rows.get(int(row.disciple_tg or 0))
            mentor_card = profile_cards.get(int(row.mentor_tg or 0))
            disciple_card = profile_cards.get(int(row.disciple_tg or 0))
            social_reason = ""
            try:
                assert_social_action_allowed(mentor_profile, disciple_profile, "师徒往来")
            except ValueError as exc:
                social_reason = str(exc)
            graduation = _mentorship_graduation_state(row, disciple_profile) if disciple_profile is not None else {"ready": False, "hint": "徒弟档案异常，暂不可出师。"}
            payload.update(
                {
                    "bond_label": _mentorship_bond_label(payload.get("bond_value") or 0),
                    "mentor_profile": mentor_card,
                    "disciple_profile": disciple_card,
                    "actor_role": "mentor" if int(row.mentor_tg or 0) == int(tg) else "disciple",
                    "can_teach_today": row.status == "active" and not social_reason and not is_same_china_day(row.last_teach_at, utcnow()),
                    "teach_reason": social_reason or ("今日已经传道过了。" if is_same_china_day(row.last_teach_at, utcnow()) else ""),
                    "can_consult_today": row.status == "active" and not social_reason and not is_same_china_day(row.last_consult_at, utcnow()),
                    "consult_reason": social_reason or ("今日已经问道过了。" if is_same_china_day(row.last_consult_at, utcnow()) else ""),
                    "graduation_ready": bool(graduation.get("ready")),
                    "graduation_hint": graduation.get("hint") or "",
                }
            )
            return payload

        incoming_requests: list[dict[str, Any]] = []
        outgoing_requests: list[dict[str, Any]] = []
        for row in request_rows:
            payload = serialize_mentorship_request(row) or {}
            payload["sponsor_profile"] = profile_cards.get(int(payload.get("sponsor_tg") or 0))
            payload["target_profile"] = profile_cards.get(int(payload.get("target_tg") or 0))
            payload["mentor_profile"] = profile_cards.get(int(payload.get("mentor_tg") or 0))
            payload["disciple_profile"] = profile_cards.get(int(payload.get("disciple_tg") or 0))
            payload["counterpart_profile"] = (
                payload["target_profile"] if int(payload.get("sponsor_tg") or 0) == int(tg) else payload["sponsor_profile"]
            )
            if int(payload.get("target_tg") or 0) == int(tg):
                incoming_requests.append(payload)
            else:
                outgoing_requests.append(payload)

        mentor_capacity = _mentorship_capacity(profile)
        used_slots = len(disciple_relations)
        request_hint = "可主动搜索道友，递上拜师申请或发出收徒邀请。"
        is_dead = bool(profile.death_at)
        if is_dead:
            request_hint = "当前角色已身死道消，无法再处理师徒因果。"
        elif is_profile_secluded(profile):
            request_hint = "你当前处于避世状态，暂时无法发起或接受师徒往来。"
        elif mentor_relation is not None:
            request_hint = "你已有师尊，仍可继续带徒，但无法再拜入新的师门。"

        return {
            "self_profile": profile_cards.get(int(tg)),
            "mentor_relation": relation_view(mentor_relation) if mentor_relation is not None else None,
            "disciple_relations": [relation_view(row) for row in disciple_relations],
            "incoming_requests": incoming_requests,
            "outgoing_requests": outgoing_requests,
            "mentor_capacity": mentor_capacity,
            "used_slots": used_slots,
            "available_slots": max(mentor_capacity - used_slots, 0),
            "can_take_disciple": not is_dead and not is_profile_secluded(profile) and used_slots < mentor_capacity,
            "can_seek_mentor": not is_dead and not is_profile_secluded(profile) and mentor_relation is None,
            "request_hint": request_hint,
        }


def create_mentorship_request_for_user(tg: int, target_tg: int, sponsor_role: str, message: str = "") -> dict[str, Any]:
    role = normalize_mentorship_request_role(sponsor_role)
    note = str(message or "").strip()[:255]
    with Session() as session:
        _expire_pending_mentorship_requests(session)
        actor = _mentorship_profile_row(session, tg, "递上师徒拜帖")
        target = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(target_tg)).with_for_update().first()
        _ensure_target_profile_active(target, "对方")
        mentor = actor if role == "mentor" else target
        disciple = target if role == "mentor" else actor
        _mentorship_validate_pair(session, mentor, disciple)
        duplicate = (
            session.query(XiuxianMentorshipRequest)
            .filter(
                XiuxianMentorshipRequest.status == "pending",
                XiuxianMentorshipRequest.sponsor_tg == int(actor.tg),
                XiuxianMentorshipRequest.target_tg == int(target.tg),
                XiuxianMentorshipRequest.sponsor_role == role,
            )
            .first()
        )
        if duplicate is not None:
            raise ValueError("同一封师徒拜帖还在等待对方处理。")
        pair_duplicate = None
        for row in (
            session.query(XiuxianMentorshipRequest)
            .filter(
                XiuxianMentorshipRequest.status == "pending",
                (
                    (XiuxianMentorshipRequest.sponsor_tg == int(actor.tg))
                    & (XiuxianMentorshipRequest.target_tg == int(target.tg))
                )
                | (
                    (XiuxianMentorshipRequest.sponsor_tg == int(target.tg))
                    & (XiuxianMentorshipRequest.target_tg == int(actor.tg))
                ),
            )
            .all()
        ):
            payload = serialize_mentorship_request(row) or {}
            if int(payload.get("mentor_tg") or 0) == int(mentor.tg) and int(payload.get("disciple_tg") or 0) == int(disciple.tg):
                pair_duplicate = row
                break
        if pair_duplicate is not None:
            raise ValueError("双方已有待处理的师徒因果帖，请先处理现有申请。")

        row = XiuxianMentorshipRequest(
            sponsor_tg=int(actor.tg),
            target_tg=int(target.tg),
            sponsor_role=role,
            message=note or None,
            status="pending",
            expires_at=_mentorship_pending_expire_at(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        payload = serialize_mentorship_request(row) or {}
        actor_name = _profile_display_label(serialize_profile(actor), "道友")
        target_name = _profile_display_label(serialize_profile(target), "对方")
    create_journal(tg, "mentorship", "递上师徒拜帖", f"向 {target_name} 发起了{payload.get('sponsor_role_label') or '师徒申请'}。")
    create_journal(int(target_tg), "mentorship", "收到师徒拜帖", f"{actor_name} 向你发来了{payload.get('sponsor_role_label') or '师徒申请'}。")
    return {
        "request": payload,
        "message": f"已向 {target_name} 送出{payload.get('sponsor_role_label') or '师徒拜帖'}。",
    }


def respond_mentorship_request_for_user(tg: int, request_id: int, action: str) -> dict[str, Any]:
    normalized_action = _normalize_mentorship_action(action)
    now = utcnow()
    with Session() as session:
        _expire_pending_mentorship_requests(session)
        row = (
            session.query(XiuxianMentorshipRequest)
            .filter(XiuxianMentorshipRequest.id == int(request_id))
            .with_for_update()
            .first()
        )
        if row is None:
            raise ValueError("未找到对应的师徒拜帖。")
        if normalize_mentorship_request_status(row.status) != "pending":
            raise ValueError("这封师徒拜帖已经处理过了。")
        if row.expires_at and row.expires_at <= now:
            row.status = "expired"
            row.responded_at = now
            row.updated_at = now
            session.commit()
            raise ValueError("这封师徒拜帖已经过期。")

        actor = _mentorship_profile_row(session, tg, "处理师徒拜帖")
        payload = serialize_mentorship_request(row) or {}
        sponsor = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(row.sponsor_tg)).with_for_update().first()
        target = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(row.target_tg)).with_for_update().first()
        _ensure_target_profile_active(sponsor, "发帖人")
        _ensure_target_profile_active(target, "目标道友")

        if normalized_action == "cancel":
            if int(row.sponsor_tg or 0) != int(actor.tg):
                raise ValueError("只有发帖人自己才能撤回这封师徒拜帖。")
            row.status = "cancelled"
            row.responded_at = now
            row.updated_at = now
            session.commit()
            create_journal(int(actor.tg), "mentorship", "撤回师徒拜帖", "你撤回了一封待处理的师徒拜帖。")
            return {
                "action": "cancel",
                "request": payload,
                "message": "已撤回这封师徒拜帖。",
                "achievement_unlocks": [],
            }

        if int(row.target_tg or 0) != int(actor.tg):
            raise ValueError("只有收帖方才能处理这封师徒拜帖。")

        if normalized_action == "reject":
            row.status = "rejected"
            row.responded_at = now
            row.updated_at = now
            session.commit()
            actor_name = _profile_display_label(serialize_profile(actor), "对方")
            create_journal(int(actor.tg), "mentorship", "婉拒师徒拜帖", "你婉拒了一封师徒拜帖。")
            create_journal(int(row.sponsor_tg), "mentorship", "师徒拜帖被婉拒", f"{actor_name} 婉拒了你的师徒拜帖。")
            return {
                "action": "reject",
                "request": payload,
                "message": "你已婉拒这封师徒拜帖。",
                "achievement_unlocks": [],
            }

        mentor = sponsor if payload.get("sponsor_role") == "mentor" else target
        disciple = target if payload.get("sponsor_role") == "mentor" else sponsor
        _mentorship_validate_pair(session, mentor, disciple)

        relation = _pair_mentorship(session, int(mentor.tg), int(disciple.tg), for_update=True)
        if relation is None:
            relation = XiuxianMentorship(mentor_tg=int(mentor.tg), disciple_tg=int(disciple.tg))
            session.add(relation)
        relation.status = "active"
        relation.bond_value = 0
        relation.teach_count = 0
        relation.consult_count = 0
        relation.last_teach_at = None
        relation.last_consult_at = None
        relation.mentor_realm_stage_snapshot = mentor.realm_stage
        relation.mentor_realm_layer_snapshot = int(mentor.realm_layer or 0)
        relation.disciple_realm_stage_snapshot = disciple.realm_stage
        relation.disciple_realm_layer_snapshot = int(disciple.realm_layer or 0)
        relation.graduated_at = None
        relation.ended_at = None
        relation.updated_at = now
        if relation.created_at is None:
            relation.created_at = now

        row.status = "accepted"
        row.responded_at = now
        row.updated_at = now
        other_requests = (
            session.query(XiuxianMentorshipRequest)
            .filter(
                XiuxianMentorshipRequest.status == "pending",
                XiuxianMentorshipRequest.id != int(row.id),
                (
                    (XiuxianMentorshipRequest.sponsor_tg == int(disciple.tg))
                    | (XiuxianMentorshipRequest.target_tg == int(disciple.tg))
                ),
            )
            .all()
        )
        for item in other_requests:
            item.status = "cancelled"
            item.responded_at = now
            item.updated_at = now
        session.commit()
        session.refresh(relation)
        relation_payload = serialize_mentorship(relation) or {}
        mentor_name = _profile_display_label(serialize_profile(mentor), "师尊")
        disciple_name = _profile_display_label(serialize_profile(disciple), "徒弟")

    mentor_unlocks = record_achievement_progress(
        int(relation_payload.get("mentor_tg") or 0),
        {"mentor_accept_count": 1},
        source="mentorship_accept",
    )["unlocks"]
    create_journal(int(relation_payload["mentor_tg"]), "mentorship", "收下一名弟子", f"{disciple_name} 正式拜入门下。")
    create_journal(int(relation_payload["disciple_tg"]), "mentorship", "拜入师门", f"正式拜入 {mentor_name} 门下。")
    return {
        "action": "accept",
        "request": payload,
        "mentorship": relation_payload,
        "message": f"{disciple_name} 与 {mentor_name} 的师徒关系已正式结成。",
        "achievement_unlocks": mentor_unlocks,
    }


def mentor_teach_for_user(tg: int, disciple_tg: int) -> dict[str, Any]:
    now = utcnow()
    mentor_upgraded_layers: list[int] = []
    disciple_upgraded_layers: list[int] = []
    mentor_remaining = 0
    disciple_remaining = 0
    mentor_stage = FIRST_REALM_STAGE
    disciple_stage = FIRST_REALM_STAGE
    with Session() as session:
        relation = _pair_mentorship(session, tg, disciple_tg, for_update=True)
        if relation is None or normalize_mentorship_status(relation.status) != "active":
            raise ValueError("你与该道友之间没有有效的师徒关系。")
        mentor = _mentorship_profile_row(session, tg, "向弟子传道")
        disciple = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(disciple_tg)).with_for_update().first()
        disciple = _ensure_target_profile_active(disciple, "徒弟")
        assert_social_action_allowed(mentor, disciple, "师徒往来")
        if is_same_china_day(relation.last_teach_at, now):
            raise ValueError("今日已经为这名弟子传道过了。")

        mentor_profile = serialize_profile(mentor) or {}
        disciple_profile = serialize_profile(disciple) or {}
        mentor_score = _mentorship_realm_score(mentor_profile)
        disciple_score = _mentorship_realm_score(disciple_profile)
        mentor_power = int(round(_battle_bundle(mentor_profile)["power"]))
        disciple_power = int(round(_battle_bundle(disciple_profile)["power"]))
        stage_gap = max(mentor_score - disciple_score, 1)
        raw_disciple_gain = min(42 + mentor_score * 3 + stage_gap * 6 + max((mentor_power - disciple_power) // 600, 0), 520)
        raw_mentor_gain = max(int(round(raw_disciple_gain * 0.28)), 18)
        disciple_gain, disciple_meta = adjust_cultivation_gain_for_social_mode(disciple, raw_disciple_gain)
        mentor_gain, mentor_meta = adjust_cultivation_gain_for_social_mode(mentor, raw_mentor_gain)

        disciple_bundle = _battle_bundle(disciple_profile)
        attribute_growth = _apply_activity_stat_growth_to_profile_row(disciple, "practice", disciple_bundle.get("stats"))
        bond_gain = min(8 + stage_gap * 2, 20)

        mentor_stage = normalize_realm_stage(mentor.realm_stage or FIRST_REALM_STAGE)
        disciple_stage = normalize_realm_stage(disciple.realm_stage or FIRST_REALM_STAGE)
        _, _, mentor_upgraded_layers, mentor_remaining = _settle_profile_cultivation(mentor, mentor_gain)
        _, _, disciple_upgraded_layers, disciple_remaining = _settle_profile_cultivation(disciple, disciple_gain)
        relation.bond_value = int(relation.bond_value or 0) + bond_gain
        relation.teach_count = int(relation.teach_count or 0) + 1
        relation.last_teach_at = now
        relation.updated_at = now
        mentor.updated_at = now
        disciple.updated_at = now
        session.commit()
        current_bond = int(relation.bond_value or 0)

    unlocks = record_achievement_progress(int(tg), {"mentor_teach_count": 1}, source="mentorship_teach")["unlocks"]
    disciple_name = _profile_display_label(serialize_profile(get_profile(int(disciple_tg), create=False)), "弟子")
    disciple_breakthrough_text = _mentorship_breakthrough_text(disciple_stage, disciple_upgraded_layers)
    mentor_breakthrough_text = _mentorship_breakthrough_text(mentor_stage, mentor_upgraded_layers)
    create_journal(int(tg), "mentorship", "传道授业", f"今日为 {disciple_name} 传道一次，师徒缘增加 {bond_gain}。")
    create_journal(int(disciple_tg), "mentorship", "得师尊传道", f"{_profile_display_label(serialize_profile(get_profile(int(tg), create=False)), '师尊')} 今日为你传道一次。")
    return {
        "disciple_tg": int(disciple_tg),
        "disciple_name": disciple_name,
        "disciple_gain": disciple_gain,
        "mentor_gain": mentor_gain,
        "bond_gain": bond_gain,
        "bond_value": current_bond,
        "bond_label": _mentorship_bond_label(current_bond),
        "attribute_growth": attribute_growth.get("changes") or [],
        "disciple_upgraded_layers": disciple_upgraded_layers,
        "mentor_upgraded_layers": mentor_upgraded_layers,
        "disciple_remaining": disciple_remaining,
        "mentor_remaining": mentor_remaining,
        "disciple_gain_raw": disciple_meta.get("base_gain", raw_disciple_gain),
        "mentor_gain_raw": mentor_meta.get("base_gain", raw_mentor_gain),
        "achievement_unlocks": unlocks,
        "message": (
            f"你为 {disciple_name} 讲解一轮功法关窍，对方获得 {disciple_gain} 修为{disciple_breakthrough_text}，"
            f"你自身也沉淀了 {mentor_gain} 修为{mentor_breakthrough_text}。"
        ),
    }


def consult_mentor_for_user(tg: int) -> dict[str, Any]:
    now = utcnow()
    mentor_upgraded_layers: list[int] = []
    disciple_upgraded_layers: list[int] = []
    mentor_remaining = 0
    disciple_remaining = 0
    mentor_stage = FIRST_REALM_STAGE
    disciple_stage = FIRST_REALM_STAGE
    with Session() as session:
        relation = _active_mentorship_for_disciple(session, tg, for_update=True)
        if relation is None or normalize_mentorship_status(relation.status) != "active":
            raise ValueError("你当前没有可问道的师尊。")
        mentor = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(relation.mentor_tg)).with_for_update().first()
        mentor = _ensure_target_profile_active(mentor, "师尊")
        disciple = _mentorship_profile_row(session, tg, "向师尊问道")
        assert_social_action_allowed(disciple, mentor, "师徒往来")
        if is_same_china_day(relation.last_consult_at, now):
            raise ValueError("今日已经向师尊问道过了。")

        mentor_profile = serialize_profile(mentor) or {}
        disciple_profile = serialize_profile(disciple) or {}
        mentor_score = _mentorship_realm_score(mentor_profile)
        disciple_score = _mentorship_realm_score(disciple_profile)
        stage_gap = max(mentor_score - disciple_score, 1)
        raw_disciple_gain = min(26 + mentor_score * 2 + stage_gap * 4, 360)
        raw_mentor_gain = max(int(round(raw_disciple_gain * 0.2)), 12)
        disciple_gain, _ = adjust_cultivation_gain_for_social_mode(disciple, raw_disciple_gain)
        mentor_gain, _ = adjust_cultivation_gain_for_social_mode(mentor, raw_mentor_gain)
        mentor_stats = _battle_bundle(mentor_profile).get("stats")
        growth = _roll_mentorship_consult_growth(mentor_stats)
        for key, delta in (growth.get("patch") or {}).items():
            setattr(disciple, key, int(getattr(disciple, key, 0) or 0) + int(delta or 0))

        bond_gain = min(6 + stage_gap, 14)
        disciple_stage = normalize_realm_stage(disciple.realm_stage or FIRST_REALM_STAGE)
        mentor_stage = normalize_realm_stage(mentor.realm_stage or FIRST_REALM_STAGE)
        _, _, disciple_upgraded_layers, disciple_remaining = _settle_profile_cultivation(disciple, disciple_gain)
        _, _, mentor_upgraded_layers, mentor_remaining = _settle_profile_cultivation(mentor, mentor_gain)
        relation.bond_value = int(relation.bond_value or 0) + bond_gain
        relation.consult_count = int(relation.consult_count or 0) + 1
        relation.last_consult_at = now
        relation.updated_at = now
        mentor.updated_at = now
        disciple.updated_at = now
        session.commit()
        mentor_tg = int(relation.mentor_tg or 0)

    unlocks = record_achievement_progress(int(tg), {"disciple_consult_count": 1}, source="mentorship_consult")["unlocks"]
    mentor_name = _profile_display_label(serialize_profile(get_profile(mentor_tg, create=False)), "师尊")
    disciple_breakthrough_text = _mentorship_breakthrough_text(disciple_stage, disciple_upgraded_layers)
    mentor_breakthrough_text = _mentorship_breakthrough_text(mentor_stage, mentor_upgraded_layers)
    create_journal(int(tg), "mentorship", "向师尊问道", f"今日向 {mentor_name} 问道一次，师徒缘增加 {bond_gain}。")
    create_journal(mentor_tg, "mentorship", "为弟子解惑", f"{_profile_display_label(serialize_profile(get_profile(int(tg), create=False)), '弟子')} 今日前来问道。")
    return {
        "mentor_tg": mentor_tg,
        "mentor_name": mentor_name,
        "disciple_gain": disciple_gain,
        "mentor_gain": mentor_gain,
        "bond_gain": bond_gain,
        "attribute_growth": growth.get("changes") or [],
        "disciple_upgraded_layers": disciple_upgraded_layers,
        "mentor_upgraded_layers": mentor_upgraded_layers,
        "disciple_remaining": disciple_remaining,
        "mentor_remaining": mentor_remaining,
        "achievement_unlocks": unlocks,
        "message": (
            f"你向 {mentor_name} 问清了几处修行疑难，获得 {disciple_gain} 修为{disciple_breakthrough_text}，"
            f"师尊也因点拨沉淀了 {mentor_gain} 修为{mentor_breakthrough_text}。"
        ),
    }


def _resolve_active_mentorship_for_actor(session: Session, tg: int, target_tg: int, *, for_update: bool = False) -> XiuxianMentorship:
    relation = _pair_mentorship(session, tg, target_tg, for_update=for_update)
    if relation is None:
        relation = _pair_mentorship(session, target_tg, tg, for_update=for_update)
    if relation is None or normalize_mentorship_status(relation.status) != "active":
        raise ValueError("双方当前没有有效的师徒关系。")
    if int(tg) not in {int(relation.mentor_tg or 0), int(relation.disciple_tg or 0)}:
        raise ValueError("你无权处理这段师徒关系。")
    return relation


def graduate_mentorship_for_user(tg: int, target_tg: int) -> dict[str, Any]:
    now = utcnow()
    with Session() as session:
        relation = _resolve_active_mentorship_for_actor(session, tg, target_tg, for_update=True)
        mentor = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(relation.mentor_tg)).with_for_update().first()
        disciple = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(relation.disciple_tg)).with_for_update().first()
        mentor = _ensure_target_profile_active(mentor, "师尊")
        disciple = _ensure_target_profile_active(disciple, "徒弟")
        assert_social_action_allowed(mentor, disciple, "师徒往来")
        graduation = _mentorship_graduation_state(relation, disciple)
        if not graduation.get("ready"):
            raise ValueError(graduation.get("hint") or "当前仍未满足出师条件。")

        mentor_score = _mentorship_realm_score(mentor)
        disciple_gain = min(160 + mentor_score * 6 + int(relation.bond_value or 0) // 2, 880)
        mentor_gain = max(int(round(disciple_gain * 0.65)), 120)
        _settle_profile_cultivation(mentor, mentor_gain)
        _settle_profile_cultivation(disciple, disciple_gain)
        relation.status = "graduated"
        relation.graduated_at = now
        relation.ended_at = now
        relation.updated_at = now
        mentor.updated_at = now
        disciple.updated_at = now
        session.commit()
        mentor_tg = int(relation.mentor_tg or 0)
        disciple_tg_value = int(relation.disciple_tg or 0)

    title_rewards = _apply_mentorship_titles(mentor_tg, disciple_tg_value)
    unlocks = []
    unlocks.extend(record_achievement_progress(mentor_tg, {"mentor_graduate_count": 1}, source="mentorship_graduate")["unlocks"])
    unlocks.extend(record_achievement_progress(disciple_tg_value, {"disciple_graduate_count": 1}, source="mentorship_graduate")["unlocks"])
    mentor_name = _profile_display_label(serialize_profile(get_profile(mentor_tg, create=False)), "师尊")
    disciple_name = _profile_display_label(serialize_profile(get_profile(disciple_tg_value, create=False)), "弟子")
    create_journal(mentor_tg, "mentorship", "门下弟子出师", f"{disciple_name} 已经正式出师，传承告一段落。")
    create_journal(disciple_tg_value, "mentorship", "正式出师", f"在 {mentor_name} 门下修成，今日正式出师。")
    return {
        "mentor_tg": mentor_tg,
        "disciple_tg": disciple_tg_value,
        "mentor_name": mentor_name,
        "disciple_name": disciple_name,
        "mentor_gain": mentor_gain,
        "disciple_gain": disciple_gain,
        "title_rewards": title_rewards,
        "achievement_unlocks": unlocks,
        "message": f"{disciple_name} 已正式出师，双方都从这段传承中获得了新的体悟。",
    }


def dissolve_mentorship_for_user(tg: int, target_tg: int) -> dict[str, Any]:
    now = utcnow()
    with Session() as session:
        relation = _resolve_active_mentorship_for_actor(session, tg, target_tg, for_update=True)
        relation.status = "dissolved"
        relation.ended_at = now
        relation.updated_at = now
        session.commit()
        mentor_tg = int(relation.mentor_tg or 0)
        disciple_tg_value = int(relation.disciple_tg or 0)
    mentor_name = _profile_display_label(serialize_profile(get_profile(mentor_tg, create=False)), "师尊")
    disciple_name = _profile_display_label(serialize_profile(get_profile(disciple_tg_value, create=False)), "弟子")
    actor_role = "mentor" if int(tg) == mentor_tg else "disciple"
    if actor_role == "mentor":
        create_journal(mentor_tg, "mentorship", "解除师徒关系", f"你与 {disciple_name} 的师徒关系已解除。")
        create_journal(disciple_tg_value, "mentorship", "被逐出师门", f"{mentor_name} 已解除与你的师徒关系。")
    else:
        create_journal(disciple_tg_value, "mentorship", "离开师门", f"你与 {mentor_name} 的师徒关系已解除。")
        create_journal(mentor_tg, "mentorship", "弟子离开师门", f"{disciple_name} 主动离开了门下。")
    return {
        "mentor_tg": mentor_tg,
        "disciple_tg": disciple_tg_value,
        "mentor_name": mentor_name,
        "disciple_name": disciple_name,
        "message": f"{mentor_name} 与 {disciple_name} 的师徒关系已解除。",
        "achievement_unlocks": [],
    }


def _normalize_marriage_action(action: str | None) -> str:
    value = str(action or "").strip().lower()
    aliases = {
        "accept": "accept",
        "agree": "accept",
        "同意": "accept",
        "reject": "reject",
        "decline": "reject",
        "拒绝": "reject",
        "cancel": "cancel",
        "revoke": "cancel",
        "撤回": "cancel",
    }
    return aliases.get(value, "accept")


def _marriage_bond_label(value: int) -> str:
    bond = max(int(value or 0), 0)
    if bond >= 180:
        return "比翼同修"
    if bond >= 100:
        return "灵契相守"
    if bond >= 40:
        return "情丝初结"
    return "新缔良缘"


def _marriage_pending_expire_at() -> datetime:
    return utcnow() + timedelta(hours=MARRIAGE_REQUEST_EXPIRE_HOURS)


def _marriage_profile_row(session: Session, tg: int, action_text: str) -> XiuxianProfile:
    row = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
    if row is None or not row.consented:
        raise ValueError("你尚未踏入仙途，道基未立。")
    assert_profile_alive(row, action_text)
    _assert_gender_ready(row, action_text)
    return row


def _ensure_marriage_target_profile(profile: XiuxianProfile | None, fallback: str = "对方") -> XiuxianProfile:
    if profile is None or not profile.consented:
        raise ValueError(f"{fallback}还没有踏入仙途。")
    if profile.death_at is not None:
        label = str(profile.display_name or (f"@{profile.username}" if profile.username else fallback)).strip() or fallback
        raise ValueError(f"{label} 当前已身死道消，无法缔结姻缘。")
    _assert_gender_ready(profile, f"{fallback}参与姻缘")
    return profile


def _expire_pending_marriage_requests(session: Session) -> int:
    now = utcnow()
    rows = (
        session.query(XiuxianMarriageRequest)
        .filter(
            XiuxianMarriageRequest.status == "pending",
            XiuxianMarriageRequest.expires_at.isnot(None),
            XiuxianMarriageRequest.expires_at <= now,
        )
        .all()
    )
    for row in rows:
        row.status = "expired"
        row.responded_at = now
        row.updated_at = now
    return len(rows)


def _active_marriage_for_user_service(session: Session, tg: int, *, for_update: bool = False) -> XiuxianMarriage | None:
    query = session.query(XiuxianMarriage).filter(
        XiuxianMarriage.status == "active",
        (XiuxianMarriage.husband_tg == int(tg)) | (XiuxianMarriage.wife_tg == int(tg)),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianMarriage.id.desc()).first()


def _pair_marriage(session: Session, husband_tg: int, wife_tg: int, *, for_update: bool = False) -> XiuxianMarriage | None:
    query = session.query(XiuxianMarriage).filter(
        XiuxianMarriage.husband_tg == int(husband_tg),
        XiuxianMarriage.wife_tg == int(wife_tg),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianMarriage.id.desc()).first()


def _marriage_spouse_tg(relation: XiuxianMarriage, tg: int) -> int:
    return int(relation.wife_tg if int(relation.husband_tg or 0) == int(tg) else relation.husband_tg or 0)


def _cancel_pending_marriage_requests_for_tgs(session: Session, tgs: list[int], *, now: datetime | None = None) -> int:
    valid_tgs = [int(item) for item in tgs if int(item or 0) > 0]
    if not valid_tgs:
        return 0
    current = now or utcnow()
    rows = (
        session.query(XiuxianMarriageRequest)
        .filter(
            XiuxianMarriageRequest.status == "pending",
            (
                XiuxianMarriageRequest.sponsor_tg.in_(valid_tgs)
                | XiuxianMarriageRequest.target_tg.in_(valid_tgs)
            ),
        )
        .with_for_update()
        .all()
    )
    for row in rows:
        row.status = "cancelled"
        row.responded_at = current
        row.updated_at = current
    return len(rows)


def _end_marriage_for_user(session: Session, tg: int, *, ended_at: datetime | None = None) -> dict[str, Any] | None:
    current = ended_at or utcnow()
    relation = _active_marriage_for_user_service(session, tg, for_update=True)
    if relation is None or normalize_marriage_status(relation.status) != "active":
        _cancel_pending_marriage_requests_for_tgs(session, [tg], now=current)
        return None
    spouse_tg = _marriage_spouse_tg(relation, tg)
    relation.status = "divorced"
    relation.ended_at = current
    relation.updated_at = current
    _cancel_pending_marriage_requests_for_tgs(
        session,
        [int(relation.husband_tg or 0), int(relation.wife_tg or 0)],
        now=current,
    )
    return {
        "relation": serialize_marriage(relation) or {},
        "spouse_tg": int(spouse_tg or 0),
    }


def _marriage_profile_summary(profile: XiuxianProfile | dict[str, Any] | None, *, bundle: dict[str, Any] | None = None) -> dict[str, Any] | None:
    payload = _mentorship_profile_summary(profile, bundle=bundle)
    if payload is None:
        return None
    source = dict(profile) if isinstance(profile, dict) else serialize_profile(profile)
    payload["gender"] = source.get("gender") if source else None
    payload["gender_label"] = source.get("gender_label") if source else ""
    return payload


def _marriage_validate_pair(session: Session, husband_profile: XiuxianProfile, wife_profile: XiuxianProfile) -> None:
    husband_tg = int(husband_profile.tg or 0)
    wife_tg = int(wife_profile.tg or 0)
    if husband_tg <= 0 or wife_tg <= 0:
        raise ValueError("姻缘目标无效。")
    if husband_tg == wife_tg:
        raise ValueError("不能和自己结为道侣。")
    _ensure_marriage_target_profile(husband_profile, "男方")
    _ensure_marriage_target_profile(wife_profile, "女方")
    if normalize_gender(husband_profile.gender) != "male" or normalize_gender(wife_profile.gender) != "female":
        raise ValueError("当前姻缘系统仅支持男女缔结道侣。")
    assert_social_action_allowed(husband_profile, wife_profile, "缔结姻缘")
    husband_relation = _active_marriage_for_user_service(session, husband_tg, for_update=True)
    if husband_relation is not None and int(_marriage_spouse_tg(husband_relation, husband_tg) or 0) != wife_tg:
        raise ValueError("男方当前已有道侣，需先和离。")
    wife_relation = _active_marriage_for_user_service(session, wife_tg, for_update=True)
    if wife_relation is not None and int(_marriage_spouse_tg(wife_relation, wife_tg) or 0) != husband_tg:
        raise ValueError("女方当前已有道侣，需先和离。")
    if husband_relation is not None and wife_relation is not None:
        raise ValueError("双方当前已经是道侣，无需重复缔结。")
    # 和离后冷却期，期间不可再与他人缔结道侣
    divorce_cooldown_days = max(int(get_xiuxian_settings().get("marriage_divorce_cooldown_days", DEFAULT_SETTINGS.get("marriage_divorce_cooldown_days", 7)) or 0), 1)
    cooldown_deadline = utcnow() - timedelta(days=divorce_cooldown_days)
    for tg, label in [(husband_tg, "男方"), (wife_tg, "女方")]:
        recent_divorce = (
            session.query(XiuxianMarriage)
            .filter(
                (XiuxianMarriage.husband_tg == tg) | (XiuxianMarriage.wife_tg == tg),
                XiuxianMarriage.status == "divorced",
                XiuxianMarriage.ended_at >= cooldown_deadline,
            )
            .first()
        )
        if recent_divorce is not None:
            raise ValueError(f"{label}刚经历了和离，请等待冷却期结束后再缔结新的姻缘。")


def build_marriage_overview(tg: int, *, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    with Session() as session:
        expired = _expire_pending_marriage_requests(session)
        if expired:
            session.commit()
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).first()
        if profile is None or not profile.consented:
            return {
                "self_profile": None,
                "gender": None,
                "gender_label": "",
                "gender_set": False,
                "can_set_gender": False,
                "gender_change_reason": "踏入仙途后才可设置性别。",
                "current_marriage": None,
                "incoming_requests": [],
                "outgoing_requests": [],
                "can_request_marriage": False,
                "request_hint": "踏入仙途后才可缔结姻缘。",
                "shared_assets_enabled": False,
                "shared_assets_hint": "结为道侣后，灵石与背包会自动共享。",
            }

        gender = normalize_gender(profile.gender)
        relation = _active_marriage_for_user_service(session, tg)
        request_rows = (
            session.query(XiuxianMarriageRequest)
            .filter(
                XiuxianMarriageRequest.status == "pending",
                (XiuxianMarriageRequest.sponsor_tg == int(tg)) | (XiuxianMarriageRequest.target_tg == int(tg)),
            )
            .order_by(XiuxianMarriageRequest.created_at.desc(), XiuxianMarriageRequest.id.desc())
            .all()
        )
        related_tgs = {int(tg)}
        if relation is not None:
            related_tgs.add(int(relation.husband_tg or 0))
            related_tgs.add(int(relation.wife_tg or 0))
        for row in request_rows:
            related_tgs.add(int(row.sponsor_tg or 0))
            related_tgs.add(int(row.target_tg or 0))
        profile_rows = {
            int(row.tg): row
            for row in session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_([item for item in related_tgs if item > 0])).all()
        }
        profile_cards: dict[int, dict[str, Any] | None] = {}
        for related_tg in related_tgs:
            row = profile_rows.get(int(related_tg))
            if row is None:
                continue
            if bundle and int((bundle.get("profile") or {}).get("tg") or 0) == int(related_tg):
                profile_cards[int(related_tg)] = _marriage_profile_summary(bundle.get("profile") or {}, bundle=bundle)
            else:
                profile_cards[int(related_tg)] = _marriage_profile_summary(row)

        marriage_payload = None
        if relation is not None:
            spouse_tg = _marriage_spouse_tg(relation, tg)
            spouse_profile = profile_rows.get(int(spouse_tg))
            social_reason = ""
            try:
                assert_social_action_allowed(profile, spouse_profile, "道侣双修")
            except ValueError as exc:
                social_reason = str(exc)
            marriage_payload = serialize_marriage(relation) or {}
            marriage_payload.update(
                {
                    "bond_label": _marriage_bond_label(marriage_payload.get("bond_value") or 0),
                    "actor_role": "husband" if int(relation.husband_tg or 0) == int(tg) else "wife",
                    "spouse_tg": int(spouse_tg or 0),
                    "spouse_profile": profile_cards.get(int(spouse_tg or 0)),
                    "husband_profile": profile_cards.get(int(relation.husband_tg or 0)),
                    "wife_profile": profile_cards.get(int(relation.wife_tg or 0)),
                    "can_dual_cultivate_today": not social_reason and not is_same_china_day(relation.last_dual_cultivation_at, utcnow()),
                    "dual_cultivate_reason": social_reason or ("今日已经双修过了。" if is_same_china_day(relation.last_dual_cultivation_at, utcnow()) else ""),
                    "shared_spiritual_stone_total": get_shared_spiritual_stone_total(tg),
                }
            )

        incoming_requests: list[dict[str, Any]] = []
        outgoing_requests: list[dict[str, Any]] = []
        for row in request_rows:
            payload = serialize_marriage_request(row) or {}
            payload["sponsor_profile"] = profile_cards.get(int(payload.get("sponsor_tg") or 0))
            payload["target_profile"] = profile_cards.get(int(payload.get("target_tg") or 0))
            payload["counterpart_profile"] = (
                payload["target_profile"] if int(payload.get("sponsor_tg") or 0) == int(tg) else payload["sponsor_profile"]
            )
            if int(payload.get("target_tg") or 0) == int(tg):
                incoming_requests.append(payload)
            else:
                outgoing_requests.append(payload)

        is_dead = bool(profile.death_at)
        shared_assets_enabled = relation is not None and not is_dead
        if is_dead:
            request_hint = "当前角色已身死道消，无法处理姻缘事务。"
        elif not gender:
            request_hint = "请先设置性别，不设置则无法继续使用修仙玩法。"
        elif relation is not None:
            request_hint = "你已结为道侣，婚后灵石与背包自动共享。"
        elif is_profile_secluded(profile):
            request_hint = "你当前处于避世状态，暂时无法发起或接受姻缘请求。"
        else:
            request_hint = "可搜索异性道友，递上结缘信物。"

        return {
            "self_profile": profile_cards.get(int(tg)),
            "gender": gender,
            "gender_label": (serialize_profile(profile) or {}).get("gender_label") or "",
            "gender_set": bool(gender),
            "can_set_gender": relation is None and not is_dead,
            "gender_change_reason": "已结为道侣，当前不可更改性别。" if relation is not None else ("角色已死亡，当前不可设置性别。" if is_dead else ""),
            "current_marriage": marriage_payload,
            "incoming_requests": incoming_requests,
            "outgoing_requests": outgoing_requests,
            "can_request_marriage": bool(gender) and relation is None and not is_dead and not is_profile_secluded(profile),
            "request_hint": request_hint,
            "shared_assets_enabled": shared_assets_enabled,
            "shared_assets_hint": "当前灵石与背包已共享。" if shared_assets_enabled else "结为道侣后，灵石与背包会自动共享。",
        }


def set_gender_for_user(tg: int, gender: str) -> dict[str, Any]:
    normalized = normalize_gender(gender)
    if normalized not in {"male", "female"}:
        raise ValueError("性别仅支持设置为男或女。")
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        assert_profile_alive(profile, "设置性别")
        relation = _active_marriage_for_user_service(session, tg, for_update=True)
        current_gender = normalize_gender(profile.gender)
        if relation is not None and current_gender and current_gender != normalized:
            raise ValueError("已结为道侣，当前不可更改性别。")
        profile.gender = normalized
        profile.updated_at = utcnow()
        session.commit()
    label = "男" if normalized == "male" else "女"
    create_journal(tg, "marriage", "设置性别", f"将自身性别设为【{label}】。")
    return {
        "gender": normalized,
        "gender_label": label,
        "message": f"性别已设置为{label}。",
        "profile": serialize_full_profile(tg),
    }


def create_marriage_request_for_user(tg: int, target_tg: int, message: str = "") -> dict[str, Any]:
    note = str(message or "").strip()[:255]
    with Session() as session:
        _expire_pending_marriage_requests(session)
        actor = _marriage_profile_row(session, tg, "递上结缘信物")
        target = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(target_tg)).with_for_update().first()
        target = _ensure_marriage_target_profile(target, "对方")
        actor_gender = normalize_gender(actor.gender)
        target_gender = normalize_gender(target.gender)
        if actor_gender == target_gender:
            raise ValueError("当前姻缘系统仅支持男女缔结道侣。")
        husband = actor if actor_gender == "male" else target
        wife = target if actor_gender == "male" else actor
        _marriage_validate_pair(session, husband, wife)
        pair_duplicate = (
            session.query(XiuxianMarriageRequest)
            .filter(
                XiuxianMarriageRequest.status == "pending",
                (
                    (XiuxianMarriageRequest.sponsor_tg == int(actor.tg))
                    & (XiuxianMarriageRequest.target_tg == int(target.tg))
                )
                | (
                    (XiuxianMarriageRequest.sponsor_tg == int(target.tg))
                    & (XiuxianMarriageRequest.target_tg == int(actor.tg))
                ),
            )
            .first()
        )
        if pair_duplicate is not None:
            raise ValueError("双方已有待处理的姻缘请求，请先处理现有信物。")
        row = XiuxianMarriageRequest(
            sponsor_tg=int(actor.tg),
            target_tg=int(target.tg),
            message=note or None,
            status="pending",
            expires_at=_marriage_pending_expire_at(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        payload = serialize_marriage_request(row) or {}
        actor_name = _profile_display_label(serialize_profile(actor), "道友")
        target_name = _profile_display_label(serialize_profile(target), "对方")
    create_journal(tg, "marriage", "递上结缘信物", f"向 {target_name} 发起了道侣请求。")
    create_journal(int(target_tg), "marriage", "收到结缘信物", f"{actor_name} 向你递来了一封结缘信物。")
    return {
        "request": payload,
        "message": f"已向 {target_name} 送出结缘信物。",
    }


def respond_marriage_request_for_user(tg: int, request_id: int, action: str) -> dict[str, Any]:
    normalized_action = _normalize_marriage_action(action)
    now = utcnow()
    with Session() as session:
        _expire_pending_marriage_requests(session)
        row = (
            session.query(XiuxianMarriageRequest)
            .filter(XiuxianMarriageRequest.id == int(request_id))
            .with_for_update()
            .first()
        )
        if row is None:
            raise ValueError("未找到对应的结缘信物。")
        if normalize_marriage_request_status(row.status) != "pending":
            raise ValueError("这封结缘信物已经处理过了。")
        if row.expires_at and row.expires_at <= now:
            row.status = "expired"
            row.responded_at = now
            row.updated_at = now
            session.commit()
            raise ValueError("这封结缘信物已经过期。")
        actor = _marriage_profile_row(session, tg, "处理结缘信物")
        payload = serialize_marriage_request(row) or {}
        sponsor = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(row.sponsor_tg)).with_for_update().first()
        target = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(row.target_tg)).with_for_update().first()
        sponsor = _ensure_marriage_target_profile(sponsor, "发信人")
        target = _ensure_marriage_target_profile(target, "目标道友")

        if normalized_action == "cancel":
            if int(row.sponsor_tg or 0) != int(actor.tg):
                raise ValueError("只有发信人自己才能撤回这封结缘信物。")
            row.status = "cancelled"
            row.responded_at = now
            row.updated_at = now
            session.commit()
            create_journal(int(actor.tg), "marriage", "撤回结缘信物", "你撤回了一封待处理的结缘信物。")
            return {"action": "cancel", "request": payload, "message": "已撤回这封结缘信物。"}

        if int(row.target_tg or 0) != int(actor.tg):
            raise ValueError("只有收信人才能处理这封结缘信物。")

        if normalized_action == "reject":
            row.status = "rejected"
            row.responded_at = now
            row.updated_at = now
            session.commit()
            actor_name = _profile_display_label(serialize_profile(actor), "对方")
            create_journal(int(actor.tg), "marriage", "婉拒结缘信物", "你婉拒了一封结缘信物。")
            create_journal(int(row.sponsor_tg), "marriage", "结缘信物被婉拒", f"{actor_name} 婉拒了你的结缘信物。")
            return {"action": "reject", "request": payload, "message": "你已婉拒这封结缘信物。"}

        sponsor_gender = normalize_gender(sponsor.gender)
        target_gender = normalize_gender(target.gender)
        if sponsor_gender == target_gender:
            raise ValueError("当前姻缘系统仅支持男女缔结道侣。")
        husband = sponsor if sponsor_gender == "male" else target
        wife = target if sponsor_gender == "male" else sponsor
        _marriage_validate_pair(session, husband, wife)

        relation = _pair_marriage(session, int(husband.tg), int(wife.tg), for_update=True)
        if relation is None:
            relation = XiuxianMarriage(husband_tg=int(husband.tg), wife_tg=int(wife.tg))
            session.add(relation)
        relation.status = "active"
        relation.bond_value = 0
        relation.dual_cultivation_count = 0
        relation.last_dual_cultivation_at = None
        relation.ended_at = None
        relation.updated_at = now
        if relation.created_at is None:
            relation.created_at = now
        row.status = "accepted"
        row.responded_at = now
        row.updated_at = now
        other_requests = (
            session.query(XiuxianMarriageRequest)
            .filter(
                XiuxianMarriageRequest.status == "pending",
                XiuxianMarriageRequest.id != int(row.id),
                (
                    XiuxianMarriageRequest.sponsor_tg.in_([int(sponsor.tg), int(target.tg)])
                    | XiuxianMarriageRequest.target_tg.in_([int(sponsor.tg), int(target.tg)])
                ),
            )
            .all()
        )
        for item in other_requests:
            item.status = "cancelled"
            item.responded_at = now
            item.updated_at = now
        session.commit()
        session.refresh(relation)
        relation_payload = serialize_marriage(relation) or {}
        husband_name = _profile_display_label(serialize_profile(husband), "男方")
        wife_name = _profile_display_label(serialize_profile(wife), "女方")
    invalidate_xiuxian_user_view_cache(int(sponsor.tg), int(target.tg))
    create_journal(int(relation_payload["husband_tg"]), "marriage", "喜结道侣", f"与 {wife_name} 结成道侣，自此共修仙途。")
    create_journal(int(relation_payload["wife_tg"]), "marriage", "喜结道侣", f"与 {husband_name} 结成道侣，自此共修仙途。")
    return {
        "action": "accept",
        "request": payload,
        "marriage": relation_payload,
        "message": f"{husband_name} 与 {wife_name} 已正式结为道侣。",
    }


def _marriage_item_payload(kind: str, item_ref_id: int) -> dict[str, Any] | None:
    if kind == "artifact":
        return serialize_artifact(get_artifact(item_ref_id))
    if kind == "pill":
        return serialize_pill(get_pill(item_ref_id))
    if kind == "talisman":
        return serialize_talisman(get_talisman(item_ref_id))
    if kind == "material":
        return serialize_material(get_material(item_ref_id))
    return None


def _marriage_item_quality_level(kind: str, payload: dict[str, Any] | None) -> int:
    if not payload:
        return 1
    if kind == "material":
        return max(int(payload.get("quality_level") or 1), 1)
    return max(int(payload.get("rarity_level") or 1), 1)


def _marriage_collect_inventory_entries(session: Session, left_tg: int, right_tg: int) -> list[dict[str, Any]]:
    pair_tgs = [int(left_tg), int(right_tg)]
    result: list[dict[str, Any]] = []
    for kind, model_cls, ref_field in (
        ("artifact", XiuxianArtifactInventory, "artifact_id"),
        ("pill", XiuxianPillInventory, "pill_id"),
        ("talisman", XiuxianTalismanInventory, "talisman_id"),
        ("material", XiuxianMaterialInventory, "material_id"),
    ):
        rows = session.query(model_cls).filter(model_cls.tg.in_(pair_tgs)).with_for_update().all()
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            ref_id = int(getattr(row, ref_field) or 0)
            if ref_id <= 0:
                continue
            entry = grouped.get(ref_id)
            if entry is None:
                payload = _marriage_item_payload(kind, ref_id) or {"id": ref_id}
                entry = {
                    "kind": kind,
                    "ref_id": ref_id,
                    "quantity": 0,
                    "bound_quantity": 0,
                    "payload": payload,
                    "quality_level": _marriage_item_quality_level(kind, payload),
                }
                grouped[ref_id] = entry
            quantity = max(int(getattr(row, "quantity", 0) or 0), 0)
            entry["quantity"] += quantity
            if hasattr(row, "bound_quantity"):
                entry["bound_quantity"] += max(min(int(getattr(row, "bound_quantity", 0) or 0), quantity), 0)
        result.extend(entry for entry in grouped.values() if int(entry.get("quantity") or 0) > 0)
    return sorted(
        result,
        key=lambda item: (
            -int(item.get("quality_level") or 1),
            -int(item.get("quantity") or 0),
            str(item.get("kind") or ""),
            int(item.get("ref_id") or 0),
        ),
    )


def _marriage_pick_target(score_map: dict[int, int], count_map: dict[int, int], left_tg: int, right_tg: int) -> int:
    targets = [int(left_tg), int(right_tg)]
    random.shuffle(targets)
    return min(targets, key=lambda item: (score_map.get(int(item), 0), count_map.get(int(item), 0)))


def _marriage_split_inventory(entries: list[dict[str, Any]], left_tg: int, right_tg: int) -> dict[int, dict[str, dict[int, dict[str, Any]]]]:
    allocations: dict[int, dict[str, dict[int, dict[str, Any]]]] = {
        int(left_tg): {kind: {} for kind in ("artifact", "pill", "talisman", "material")},
        int(right_tg): {kind: {} for kind in ("artifact", "pill", "talisman", "material")},
    }
    score_map = {int(left_tg): 0, int(right_tg): 0}
    count_map = {int(left_tg): 0, int(right_tg): 0}
    for entry in entries:
        kind = str(entry.get("kind") or "")
        ref_id = int(entry.get("ref_id") or 0)
        quantity = max(int(entry.get("quantity") or 0), 0)
        bound_quantity = max(min(int(entry.get("bound_quantity") or 0), quantity), 0)
        payload = entry.get("payload") or {"id": ref_id}
        quality_weight = max(int(entry.get("quality_level") or 1), 1) * 100
        for index in range(quantity):
            chosen_tg = _marriage_pick_target(score_map, count_map, left_tg, right_tg)
            bucket = allocations[int(chosen_tg)][kind].setdefault(
                ref_id,
                {"quantity": 0, "bound_quantity": 0, "payload": payload},
            )
            bucket["quantity"] += 1
            if index < bound_quantity:
                bucket["bound_quantity"] += 1
            score_map[int(chosen_tg)] += quality_weight
            count_map[int(chosen_tg)] += 1
    return allocations


def _marriage_reset_inventory_state(session: Session, tgs: list[int]) -> None:
    now = utcnow()
    session.query(XiuxianEquippedArtifact).filter(XiuxianEquippedArtifact.tg.in_(tgs)).delete(synchronize_session=False)
    for model_cls in (XiuxianArtifactInventory, XiuxianPillInventory, XiuxianTalismanInventory, XiuxianMaterialInventory):
        session.query(model_cls).filter(model_cls.tg.in_(tgs)).delete(synchronize_session=False)
    rows = session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_(tgs)).with_for_update().all()
    for row in rows:
        row.current_artifact_id = None
        row.active_talisman_id = None
        row.updated_at = now


def _marriage_restore_allocations(session: Session, allocations: dict[int, dict[str, dict[int, dict[str, Any]]]]) -> None:
    for tg_value, kind_map in (allocations or {}).items():
        for kind, ref_map in (kind_map or {}).items():
            for ref_id, payload in (ref_map or {}).items():
                quantity = max(int((payload or {}).get("quantity") or 0), 0)
                if quantity <= 0:
                    continue
                if kind == "artifact":
                    session.add(
                        XiuxianArtifactInventory(
                            tg=int(tg_value),
                            artifact_id=int(ref_id),
                            quantity=quantity,
                            bound_quantity=max(min(int((payload or {}).get("bound_quantity") or 0), quantity), 0),
                        )
                    )
                elif kind == "pill":
                    session.add(XiuxianPillInventory(tg=int(tg_value), pill_id=int(ref_id), quantity=quantity))
                elif kind == "talisman":
                    session.add(
                        XiuxianTalismanInventory(
                            tg=int(tg_value),
                            talisman_id=int(ref_id),
                            quantity=quantity,
                            bound_quantity=max(min(int((payload or {}).get("bound_quantity") or 0), quantity), 0),
                        )
                    )
                elif kind == "material":
                    session.add(XiuxianMaterialInventory(tg=int(tg_value), material_id=int(ref_id), quantity=quantity))


def dual_cultivate_with_spouse(tg: int) -> dict[str, Any]:
    now = utcnow()
    with Session() as session:
        relation = _active_marriage_for_user_service(session, tg, for_update=True)
        if relation is None or normalize_marriage_status(relation.status) != "active":
            raise ValueError("你当前没有可双修的道侣。")
        actor = _marriage_profile_row(session, tg, "道侣双修")
        spouse_tg = _marriage_spouse_tg(relation, tg)
        spouse = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(spouse_tg)).with_for_update().first()
        spouse = _ensure_marriage_target_profile(spouse, "道侣")
        assert_social_action_allowed(actor, spouse, "道侣双修")
        if is_same_china_day(relation.last_dual_cultivation_at, now):
            raise ValueError("今日已经和道侣双修过了。")

        actor_profile = serialize_profile(actor) or {}
        spouse_profile = serialize_profile(spouse) or {}
        actor_score = _mentorship_realm_score(actor_profile)
        spouse_score = _mentorship_realm_score(spouse_profile)
        base_gain = min(36 + min(actor_score, spouse_score) * 3 + max(abs(actor_score - spouse_score), 0), 260)
        actor_gain, actor_meta = adjust_cultivation_gain_for_social_mode(actor, base_gain)
        spouse_gain, spouse_meta = adjust_cultivation_gain_for_social_mode(spouse, base_gain)
        bond_gain = 8 + max(min(abs(actor_score - spouse_score), 6), 0)
        _settle_profile_cultivation(actor, actor_gain)
        _settle_profile_cultivation(spouse, spouse_gain)
        relation.bond_value = int(relation.bond_value or 0) + bond_gain
        relation.dual_cultivation_count = int(relation.dual_cultivation_count or 0) + 1
        relation.last_dual_cultivation_at = now
        relation.updated_at = now
        actor.updated_at = now
        spouse.updated_at = now
        session.commit()
        current_bond = int(relation.bond_value or 0)
    actor_name = _profile_display_label(serialize_profile(get_profile(int(tg), create=False)), "道侣")
    spouse_name = _profile_display_label(serialize_profile(get_profile(int(spouse_tg), create=False)), "道侣")
    create_journal(int(tg), "marriage", "道侣双修", f"今日与 {spouse_name} 双修一次，修为有所精进。")
    create_journal(int(spouse_tg), "marriage", "道侣双修", f"今日与 {actor_name} 双修一次，修为有所精进。")
    return {
        "spouse_tg": int(spouse_tg),
        "spouse_name": spouse_name,
        "actor_gain": actor_gain,
        "spouse_gain": spouse_gain,
        "actor_gain_raw": actor_meta.get("base_gain", base_gain),
        "spouse_gain_raw": spouse_meta.get("base_gain", base_gain),
        "bond_gain": bond_gain,
        "bond_value": current_bond,
        "bond_label": _marriage_bond_label(current_bond),
        "message": f"你与 {spouse_name} 完成了一次双修，双方都略微提升了修为。",
    }


def divorce_with_spouse(tg: int) -> dict[str, Any]:
    now = utcnow()
    with Session() as session:
        relation = _active_marriage_for_user_service(session, tg, for_update=True)
        if relation is None or normalize_marriage_status(relation.status) != "active":
            raise ValueError("双方当前没有有效的道侣关系。")
        left_tg = int(relation.husband_tg or 0)
        right_tg = int(relation.wife_tg or 0)
        profiles = {
            int(row.tg): row
            for row in session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_([left_tg, right_tg])).with_for_update().all()
        }
        left_profile = profiles.get(left_tg)
        right_profile = profiles.get(right_tg)
        if left_profile is None or right_profile is None:
            raise ValueError("道侣档案异常，暂时无法和离。")
        total_stone = max(int(left_profile.spiritual_stone or 0), 0) + max(int(right_profile.spiritual_stone or 0), 0)
        entries = _marriage_collect_inventory_entries(session, left_tg, right_tg)
        allocations = _marriage_split_inventory(entries, left_tg, right_tg)
        _marriage_reset_inventory_state(session, [left_tg, right_tg])
        _marriage_restore_allocations(session, allocations)
        stone_base = total_stone // 2
        extra_owner = random.choice([left_tg, right_tg]) if total_stone % 2 else left_tg
        left_profile.spiritual_stone = stone_base + (1 if total_stone % 2 and extra_owner == left_tg else 0)
        right_profile.spiritual_stone = stone_base + (1 if total_stone % 2 and extra_owner == right_tg else 0)
        left_profile.updated_at = now
        right_profile.updated_at = now
        relation.status = "divorced"
        relation.ended_at = now
        relation.updated_at = now
        for request in (
            session.query(XiuxianMarriageRequest)
            .filter(
                XiuxianMarriageRequest.status == "pending",
                (
                    XiuxianMarriageRequest.sponsor_tg.in_([left_tg, right_tg])
                    | XiuxianMarriageRequest.target_tg.in_([left_tg, right_tg])
                ),
            )
            .all()
        ):
            request.status = "cancelled"
            request.responded_at = now
            request.updated_at = now
        session.commit()

    invalidate_xiuxian_user_view_cache(left_tg, right_tg)
    left_name = _profile_display_label(serialize_profile(get_profile(left_tg, create=False)), "道侣")
    right_name = _profile_display_label(serialize_profile(get_profile(right_tg, create=False)), "道侣")
    create_journal(left_tg, "marriage", "和离分家", f"你与 {right_name} 已经和离，灵石与背包已完成重新分配。")
    create_journal(right_tg, "marriage", "和离分家", f"你与 {left_name} 已经和离，灵石与背包已完成重新分配。")
    return {
        "husband_tg": left_tg,
        "wife_tg": right_tg,
        "husband_name": left_name,
        "wife_name": right_name,
        "husband_stone": max(int((serialize_profile(get_profile(left_tg, create=False)) or {}).get("spiritual_stone") or 0), 0),
        "wife_stone": max(int((serialize_profile(get_profile(right_tg, create=False)) or {}).get("spiritual_stone") or 0), 0),
        "message": f"{left_name} 与 {right_name} 已完成和离，灵石已平分，背包物品也重新分配完毕。",
    }


def equip_artifact_for_user(tg: int, artifact_id: int) -> dict[str, Any]:
    ensure_not_in_retreat(tg)
    profile = serialize_profile(_require_alive_profile_obj(tg, "装备法宝"))

    owned = {row["artifact"]["id"] for row in list_user_artifacts(tg)}
    if artifact_id not in owned:
        raise ValueError("你的背包里没有这件法宝。")
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
    if not realm_requirement_met(profile, artifact.min_realm_stage, artifact.min_realm_layer):
        raise ValueError(f"需要达到 {format_realm_requirement(artifact.min_realm_stage, artifact.min_realm_layer)} 才能装备这件法宝。")

    equip_limit = max(int(get_xiuxian_settings().get("artifact_equip_limit", DEFAULT_SETTINGS["artifact_equip_limit"]) or 0), 1)
    result = set_equipped_artifact(tg, artifact_id, equip_limit)
    if result is None:
        raise ValueError("法宝装备状态更新失败。")
    return {
        "action": result["action"],
        "artifact_name": artifact.name,
        "profile": serialize_full_profile(tg),
    }


def bind_artifact_for_user(tg: int, artifact_id: int) -> dict[str, Any]:
    _require_alive_profile_obj(tg, "绑定法宝")
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
    result = bind_user_artifact(tg, artifact_id, 1)
    return {
        "artifact": serialize_artifact(artifact),
        "bound_quantity": int(result.get("bound_quantity") or 0),
        "profile": serialize_full_profile(tg),
    }


def unbind_artifact_for_user(tg: int, artifact_id: int) -> dict[str, Any]:
    _require_alive_profile_obj(tg, "解绑法宝")
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
    cost = max(int(get_xiuxian_settings().get("equipment_unbind_cost", DEFAULT_SETTINGS["equipment_unbind_cost"]) or 0), 0)
    result = unbind_user_artifact(tg, artifact_id, cost, 1)
    return {
        "artifact": serialize_artifact(artifact),
        "bound_quantity": int(result.get("bound_quantity") or 0),
        "cost": int(result.get("cost") or 0),
        "profile": serialize_full_profile(tg),
    }


def activate_talisman_for_user(tg: int, talisman_id: int) -> dict[str, Any]:
    ensure_not_in_retreat(tg)
    profile_obj = _require_alive_profile_obj(tg, "启用符箓")
    if int(profile_obj.active_talisman_id or 0) == int(talisman_id):
        talisman = get_talisman(talisman_id)
        if talisman is None or not talisman.enabled:
            raise ValueError("符匣空空，未觅得可启之符。")
        return {
            "talisman": serialize_talisman(talisman),
            "profile": serialize_full_profile(tg),
            "replaced_talisman_id": None,
        }

    owned = {row["talisman"]["id"] for row in list_user_talismans(tg)}
    if talisman_id not in owned:
        raise ValueError("你的背包里没有这张符箓。")

    talisman = get_talisman(talisman_id)
    if talisman is None or not talisman.enabled:
        raise ValueError("符匣空空，未觅得可启之符。")
    if not realm_requirement_met(serialize_profile(profile_obj), talisman.min_realm_stage, talisman.min_realm_layer):
        raise ValueError(f"需要达到 {format_realm_requirement(talisman.min_realm_stage, talisman.min_realm_layer)} 才能启用这张符箓。")
    if not consume_user_talisman(tg, talisman_id, 1):
        raise ValueError("你的背包里没有足够的符箓。")

    replaced_talisman_id = int(profile_obj.active_talisman_id or 0) or None
    set_active_talisman(tg, talisman_id)
    return {
        "talisman": serialize_talisman(talisman),
        "profile": serialize_full_profile(tg),
        "replaced_talisman_id": replaced_talisman_id,
    }


def bind_talisman_for_user(tg: int, talisman_id: int) -> dict[str, Any]:
    _require_alive_profile_obj(tg, "绑定符箓")
    talisman = get_talisman(talisman_id)
    if talisman is None or not talisman.enabled:
        raise ValueError("符匣空空，未觅得可启之符。")
    result = bind_user_talisman(tg, talisman_id, 1)
    return {
        "talisman": serialize_talisman(talisman),
        "bound_quantity": int(result.get("bound_quantity") or 0),
        "profile": serialize_full_profile(tg),
    }


def unbind_talisman_for_user(tg: int, talisman_id: int) -> dict[str, Any]:
    _require_alive_profile_obj(tg, "解绑符箓")
    talisman = get_talisman(talisman_id)
    if talisman is None or not talisman.enabled:
        raise ValueError("符匣空空，未觅得可启之符。")
    cost = max(int(get_xiuxian_settings().get("equipment_unbind_cost", DEFAULT_SETTINGS["equipment_unbind_cost"]) or 0), 0)
    result = unbind_user_talisman(tg, talisman_id, cost, 1)
    return {
        "talisman": serialize_talisman(talisman),
        "bound_quantity": int(result.get("bound_quantity") or 0),
        "cost": int(result.get("cost") or 0),
        "profile": serialize_full_profile(tg),
    }


def activate_technique_for_user(tg: int, technique_id: int) -> dict[str, Any]:
    ensure_seed_data()
    profile_obj = _require_alive_profile_obj(tg, "参悟功法")
    requested_id = int(technique_id or 0)
    if requested_id <= 0:
        raise ValueError("请选择要参悟的功法。")
    owned_ids = {
        int((row.get("technique") or {}).get("id") or 0)
        for row in list_user_techniques(tg, enabled_only=False)
        if (row.get("technique") or {}).get("enabled")
    }
    if requested_id not in owned_ids:
        raise ValueError("你尚未获得这门功法，需要先通过探索或机缘参悟。")
    technique = get_technique(requested_id)
    if technique is None or not technique.enabled:
        raise ValueError("识海之中未存此法，需先通过秘境或机缘参悟。")
    profile_data = serialize_profile(profile_obj)
    if not realm_requirement_met(profile_data, technique.min_realm_stage, technique.min_realm_layer):
        raise ValueError(f"需要达到 {format_realm_requirement(technique.min_realm_stage, technique.min_realm_layer)} 才能参悟这门功法。")
    if int(profile_data.get("current_technique_id") or 0) == requested_id:
        return {
            "technique": serialize_technique(technique),
            "profile": serialize_full_profile(tg),
        }
    set_current_technique(tg, requested_id)
    return {
        "technique": serialize_technique(technique),
        "profile": serialize_full_profile(tg),
    }


def set_current_title_for_user(tg: int, title_id: int | None) -> dict[str, Any]:
    _require_alive_profile_obj(tg, "切换称号")
    title = set_current_title(tg, title_id)
    return {
        "title": title,
        "profile": serialize_full_profile(tg),
    }


def start_retreat_for_user(tg: int, hours: int) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "开始闭关")
    assert_currency_operation_allowed(tg, "开始闭关", profile=profile)
    if _is_retreating(profile):
        raise ValueError("你已入定闭关，心神内守，莫再扰动。")

    retreat_hours = max(min(int(hours or 0), 4), 1)
    plan = _compute_retreat_plan(profile)
    total_minutes = retreat_hours * 60
    total_cost = plan["cost_per_minute"] * total_minutes
    if max(int(get_shared_spiritual_stone_total(tg) or 0), 0) < total_cost:
        raise ValueError(f"囊中灵石不足，闭关 {retreat_hours} 时辰共计需 {total_cost} 灵石。")

    now = utcnow()
    updated = upsert_profile(
        tg,
        retreat_started_at=now,
        retreat_end_at=now + timedelta(hours=retreat_hours),
        retreat_gain_per_minute=plan["gain_per_minute"],
        retreat_cost_per_minute=plan["cost_per_minute"],
        retreat_minutes_total=total_minutes,
        retreat_minutes_resolved=0,
    )
    return {
        "hours": retreat_hours,
        "estimated_gain": plan["gain_per_minute"] * total_minutes,
        "estimated_cost": total_cost,
        "profile": serialize_full_profile(tg),
    }


def finish_retreat_for_user(tg: int) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "结束闭关")
    assert_currency_operation_allowed(tg, "结束闭关", profile=profile)
    result = _settle_retreat_progress(tg)
    if result is None and not _is_retreating(profile):
        raise ValueError("你此刻并未处于闭关之中，何来出关之说？")

    upsert_profile(
        tg,
        retreat_started_at=None,
        retreat_end_at=None,
        retreat_gain_per_minute=0,
        retreat_cost_per_minute=0,
        retreat_minutes_total=0,
        retreat_minutes_resolved=0,
    )
    return {
        "settled": result or {"gain": 0, "cost": 0, "upgraded_layers": [], "finished": True},
        "profile": serialize_full_profile(tg),
    }


def create_personal_shop_listing(
    *,
    tg: int,
    shop_name: str,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    price_stone: int,
    broadcast: bool,
) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "上架坊市")
    if _is_retreating(profile):
        raise ValueError("闭关之中，俗务暂搁，出关后方可打理坊市。")
    assert_currency_operation_allowed(tg, "上架坊市", profile=profile)

    normalized_kind = str(item_kind or "").strip()
    item_name = ""
    if normalized_kind == "artifact":
        artifact = get_artifact(item_ref_id)
        if artifact is None:
            raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
        if not use_user_artifact_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("可交易的法宝数量不足，已绑定或已装备的法宝无法上架。")
        item_name = artifact.name
    elif normalized_kind == "pill":
        pill = get_pill(item_ref_id)
        if pill is None:
            raise ValueError("未寻得此丹踪迹，或许已化作药尘散去。")
        if not use_user_pill_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("背包里的丹药数量不足。")
        item_name = pill.name
    elif normalized_kind == "material":
        material = get_material(item_ref_id)
        if material is None:
            raise ValueError("未寻得此物踪迹，或已消散于天地之间。")
        if not use_user_material_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("背包里的材料数量不足。")
        item_name = material.name
    elif normalized_kind == "talisman":
        talisman = get_talisman(item_ref_id)
        if talisman is None:
            raise ValueError("未寻得此符踪迹，灵纹或已黯淡消逝。")
        if not use_user_talisman_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("可交易的符箓数量不足，已绑定的符箓无法上架。")
        item_name = talisman.name
    else:
        raise ValueError("不支持的上架物品类型。")

    settings = get_xiuxian_settings()
    broadcast_cost = int(settings.get("shop_broadcast_cost", DEFAULT_SETTINGS["shop_broadcast_cost"]) or 0)
    charisma_discount = min(max(int(profile.charisma or 0) - 10, 0) // 4, broadcast_cost)
    final_broadcast_cost = max(broadcast_cost - charisma_discount, 0)
    if broadcast and max(int(get_shared_spiritual_stone_total(tg) or 0), 0) < final_broadcast_cost:
        raise ValueError("囊中灵石不足，无力支付灵鹤传讯之费。")

    resolved_shop_name = str(shop_name or profile.shop_name or PERSONAL_SHOP_NAME).strip() or PERSONAL_SHOP_NAME

    try:
        listing = create_shop_item(
            owner_tg=tg,
            shop_name=resolved_shop_name,
            item_kind=normalized_kind,
            item_ref_id=item_ref_id,
            item_name=item_name,
            quantity=quantity,
            price_stone=price_stone,
            is_official=False,
        )
    except Exception:
        _rollback_consumed_item_or_raise(
            tg,
            normalized_kind,
            item_ref_id,
            quantity,
            action_text="上架坊市",
            item_name=item_name or f"{normalized_kind}#{item_ref_id}",
        )
        raise

    try:
        with Session() as session:
            updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
            if updated is None or not updated.consented:
                raise ValueError("你尚未踏入仙途，道基未立。")
            if broadcast and final_broadcast_cost > 0:
                apply_spiritual_stone_delta(
                    session,
                    tg,
                    -final_broadcast_cost,
                    action_text="支付坊市播报费用",
                    enforce_currency_lock=True,
                    allow_dead=False,
                    apply_tribute=False,
                )
            updated.shop_name = resolved_shop_name
            updated.shop_broadcast = bool(broadcast)
            updated.updated_at = utcnow()
            session.commit()
    except Exception:
        listing_id = int((listing or {}).get("id") or 0)
        try:
            if listing_id > 0:
                sql_cancel_personal_shop_item(tg, listing_id)
            else:
                _rollback_consumed_item_or_raise(
                    tg,
                    normalized_kind,
                    item_ref_id,
                    quantity,
                    action_text="上架坊市",
                    item_name=item_name or f"{normalized_kind}#{item_ref_id}",
                )
        except Exception as rollback_exc:
            raise RuntimeError("上架坊市失败，且自动撤销上架时出错，请尽快联系管理员处理。") from rollback_exc
        raise

    return {
        "listing": listing,
        "broadcast_cost": final_broadcast_cost if broadcast else 0,
        "broadcast_discount": charisma_discount if broadcast else 0,
        "profile": serialize_full_profile(tg),
    }


def create_personal_auction_listing(
    *,
    tg: int,
    seller_name: str,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    opening_price_stone: int,
    bid_increment_stone: int,
    buyout_price_stone: int | None = None,
) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "发起拍卖")
    if _is_retreating(profile):
        raise ValueError("闭关之中，心神内守，出关后再行拍卖之事。")
    assert_currency_operation_allowed(tg, "发起拍卖", profile=profile)

    normalized_kind = str(item_kind or "").strip()
    item_name = ""
    if normalized_kind == "artifact":
        artifact = get_artifact(item_ref_id)
        if artifact is None:
            raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
        if not use_user_artifact_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("可交易的法宝数量不足，已绑定或已装备的法宝无法拍卖。")
        item_name = artifact.name
    elif normalized_kind == "pill":
        pill = get_pill(item_ref_id)
        if pill is None:
            raise ValueError("未寻得此丹踪迹，或许已化作药尘散去。")
        if not use_user_pill_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("背包里的丹药数量不足。")
        item_name = pill.name
    elif normalized_kind == "material":
        material = get_material(item_ref_id)
        if material is None:
            raise ValueError("未寻得此物踪迹，或已消散于天地之间。")
        if not use_user_material_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("背包里的材料数量不足。")
        item_name = material.name
    elif normalized_kind == "talisman":
        talisman = get_talisman(item_ref_id)
        if talisman is None:
            raise ValueError("未寻得此符踪迹，灵纹或已黯淡消逝。")
        if not use_user_talisman_listing_stock(tg, item_ref_id, quantity):
            raise ValueError("可交易的符箓数量不足，已绑定的符箓无法拍卖。")
        item_name = talisman.name
    elif normalized_kind == "technique":
        technique = get_technique(item_ref_id)
        if technique is None or not technique.enabled:
            raise ValueError("未寻得此功法，或许藏于某处秘境待君探索。")
        if int(quantity or 0) != 1:
            raise ValueError("功法拍卖数量固定为 1。")
        if not revoke_technique_from_user(tg, item_ref_id):
            raise ValueError("未掌握该功法，无法发起拍卖。")
        item_name = technique.name
    else:
        raise ValueError("不支持的拍卖物品类型。")

    settings = get_xiuxian_settings()
    duration_minutes = max(
        int(settings.get("auction_duration_minutes", DEFAULT_SETTINGS["auction_duration_minutes"]) or 0),
        1,
    )
    fee_percent = max(int(settings.get("auction_fee_percent", DEFAULT_SETTINGS["auction_fee_percent"]) or 0), 0)
    resolved_seller_name = (
        str(seller_name or "").strip()
        or str(profile.display_name or "").strip()
        or (f"@{profile.username}" if str(profile.username or "").strip() else f"TG {tg}")
    )

    try:
        auction = create_auction_item(
            owner_tg=tg,
            owner_display_name=resolved_seller_name,
            item_kind=normalized_kind,
            item_ref_id=item_ref_id,
            item_name=item_name,
            quantity=quantity,
            opening_price_stone=opening_price_stone,
            bid_increment_stone=bid_increment_stone,
            buyout_price_stone=buyout_price_stone,
            fee_percent=fee_percent,
            end_at=utcnow() + timedelta(minutes=duration_minutes),
        )
    except Exception:
        _rollback_consumed_item_or_raise(
            tg,
            normalized_kind,
            item_ref_id,
            quantity,
            action_text="发起拍卖",
            item_name=item_name or f"{normalized_kind}#{item_ref_id}",
        )
        raise
    return {
        "auction": auction,
        "duration_minutes": duration_minutes,
        "profile": serialize_full_profile(tg),
    }


def create_official_shop_listing(
    *,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    price_stone: int,
    shop_name: str | None = None,
) -> dict[str, Any]:
    settings = get_xiuxian_settings()
    official_name = str(settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"]) or DEFAULT_SETTINGS["official_shop_name"]).strip() or DEFAULT_SETTINGS["official_shop_name"]
    payload = _official_seed_item_payload(item_kind, item_ref_id)
    if payload is None:
        if item_kind == "artifact":
            raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
        if item_kind == "pill":
            raise ValueError("未寻得此丹踪迹，或许已化作药尘散去。")
        if item_kind == "talisman":
            raise ValueError("未寻得此符踪迹，灵纹或已黯淡消逝。")
        if item_kind == "material":
            raise ValueError("未寻得此物踪迹，或已消散于天地之间。")
        raise ValueError("不支持的官方商店物品类型。")
    if item_kind == "artifact":
        artifact = get_artifact(item_ref_id)
        if artifact is None:
            raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
        if bool(getattr(artifact, "unique_item", False)) and int(quantity or 0) > 1:
            raise ValueError(f"唯一法宝【{getattr(artifact, 'name', item_ref_id)}】在官方商店最多只能上架 1 件。")
    if _official_payload_quality_level(item_kind, payload) > 3:
        raise ValueError("官方商店只出售中品及以下物品，上品及以上需由玩家自行获取。")
    item_name = str(payload.get("name") or item_ref_id)
    resolved_price = _seed_official_shop_price(item_kind, payload)

    return create_shop_item(
        owner_tg=None,
        shop_name=official_name,
        item_kind=item_kind,
        item_ref_id=item_ref_id,
        item_name=item_name,
        quantity=quantity,
        price_stone=resolved_price,
        is_official=True,
    )


def _official_recycle_insufficient_message(item_kind: str) -> str:
    normalized_kind = str(item_kind or "").strip()
    return {
        "artifact": "可归炉的法宝数量不足，已绑定或已装备的法宝无法归炉。",
        "pill": "囊中药丹不足，难以引动归炉之火。",
        "talisman": "可归炉的符箓数量不足，已绑定的符箓无法归炉。",
        "material": "囊中灵材不足，难以引动归炉之火。",
        "technique": "未掌握该功法，无法归炉。",
        "recipe": "未掌握该配方，无法归炉。",
    }.get(normalized_kind, "当前没有可归炉的该类物品。")


def _validate_official_recycle_request(
    *,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
) -> dict[str, Any]:
    normalized_kind = str(item_kind or "").strip()
    requested_quantity = max(int(quantity or 0), 1)
    quote = _find_official_recycle_quote_for_user(tg, normalized_kind, int(item_ref_id))
    insufficient_message = _official_recycle_insufficient_message(normalized_kind)
    if quote is None:
        raise ValueError(insufficient_message)
    if normalized_kind == "technique" and requested_quantity != 1:
        raise ValueError("功法每次只能归炉一部。")
    if normalized_kind == "recipe" and requested_quantity != 1:
        raise ValueError("配方每次只能归炉一张。")
    available_quantity = max(int(quote.get("available_quantity") or 0), 0)
    if available_quantity < requested_quantity:
        raise ValueError(insufficient_message)

    unit_price = max(int(quote.get("unit_price_stone") or 0), 0)
    total_price = unit_price * requested_quantity
    if total_price <= 0:
        raise ValueError("该物品当前无法归炉。")
    return {
        "normalized_kind": normalized_kind,
        "requested_quantity": requested_quantity,
        "available_quantity": available_quantity,
        "quote": quote,
        "unit_price": unit_price,
        "total_price": total_price,
        "insufficient_message": insufficient_message,
    }


def recycle_item_to_official_shop(
    *,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int = 1,
) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, OFFICIAL_RECYCLE_NAME)
    assert_currency_operation_allowed(tg, OFFICIAL_RECYCLE_NAME, profile=profile)

    validation = _validate_official_recycle_request(
        tg=tg,
        item_kind=item_kind,
        item_ref_id=item_ref_id,
        quantity=quantity,
    )
    normalized_kind = str(validation["normalized_kind"])
    requested_quantity = int(validation["requested_quantity"])
    available_quantity = int(validation["available_quantity"])
    unit_price = int(validation["unit_price"])
    total_price = int(validation["total_price"])
    quote = dict(validation["quote"] or {})
    insufficient_message = str(validation["insufficient_message"])

    if normalized_kind == "artifact":
        if not use_user_artifact_listing_stock(tg, item_ref_id, requested_quantity):
            raise ValueError(insufficient_message)
    elif normalized_kind == "pill":
        if not use_user_pill_listing_stock(tg, item_ref_id, requested_quantity):
            raise ValueError(insufficient_message)
    elif normalized_kind == "talisman":
        if not use_user_talisman_listing_stock(tg, item_ref_id, requested_quantity):
            raise ValueError(insufficient_message)
    elif normalized_kind == "material":
        if not use_user_material_listing_stock(tg, item_ref_id, requested_quantity):
            raise ValueError(insufficient_message)
    elif normalized_kind == "technique":
        if requested_quantity != 1:
            raise ValueError("功法每次只能归炉一部。")
        if not revoke_technique_from_user(tg, item_ref_id):
            raise ValueError(insufficient_message)
    elif normalized_kind == "recipe":
        if requested_quantity != 1:
            raise ValueError("配方每次只能归炉一张。")
        if not revoke_recipe_from_user(tg, item_ref_id):
            raise ValueError(insufficient_message)
    else:
        raise ValueError("当前物品类型暂不支持万宝归炉。")

    try:
        with Session() as session:
            stone_result = apply_spiritual_stone_delta(
                session,
                tg,
                total_price,
                action_text=OFFICIAL_RECYCLE_NAME,
                enforce_currency_lock=True,
                allow_dead=False,
                apply_tribute=True,
            )
            session.commit()
    except Exception:
        _rollback_consumed_item_or_raise(
            tg,
            normalized_kind,
            item_ref_id,
            requested_quantity,
            action_text=OFFICIAL_RECYCLE_NAME,
            item_name=quote.get("item_name") or f"{normalized_kind}#{item_ref_id}",
        )
        raise

    return {
        "shop_name": OFFICIAL_RECYCLE_NAME,
        "item_kind": normalized_kind,
        "item_kind_label": quote.get("item_kind_label") or ITEM_KIND_LABELS.get(normalized_kind, normalized_kind),
        "item_ref_id": int(item_ref_id),
        "item_name": quote.get("item_name") or f"{normalized_kind}#{item_ref_id}",
        "quality_level": int(quote.get("quality_level") or 1),
        "quality_label": quote.get("quality_label") or "",
        "quality_color": quote.get("quality_color"),
        "quantity": requested_quantity,
        "available_quantity_before": available_quantity,
        "available_quantity_after": max(available_quantity - requested_quantity, 0),
        "unit_price_stone": unit_price,
        "total_price_stone": total_price,
        "quote_note": quote.get("quote_note") or "",
        "spiritual_stone_after": int(getattr(stone_result.get("profile"), "spiritual_stone", 0) or 0),
        "net_stone_gain": int(stone_result.get("net_delta") if stone_result.get("net_delta") is not None else total_price),
    }


def recycle_items_to_official_shop(
    *,
    tg: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, OFFICIAL_RECYCLE_NAME)
    assert_currency_operation_allowed(tg, OFFICIAL_RECYCLE_NAME, profile=profile)

    normalized_items: list[dict[str, int | str]] = []
    aggregate_index: dict[tuple[str, int], int] = {}
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        normalized_kind = str(raw.get("item_kind") or "").strip()
        try:
            item_ref_id = int(raw.get("item_ref_id") or 0)
        except (TypeError, ValueError):
            item_ref_id = 0
        try:
            requested_quantity = max(int(raw.get("quantity") or 0), 1)
        except (TypeError, ValueError):
            requested_quantity = 1
        if not normalized_kind or item_ref_id <= 0:
            continue
        key = (normalized_kind, item_ref_id)
        existing_index = aggregate_index.get(key)
        if existing_index is None:
            aggregate_index[key] = len(normalized_items)
            normalized_items.append(
                {
                    "item_kind": normalized_kind,
                    "item_ref_id": item_ref_id,
                    "quantity": requested_quantity,
                }
            )
        else:
            normalized_items[existing_index]["quantity"] = int(normalized_items[existing_index]["quantity"]) + requested_quantity

    if not normalized_items:
        raise ValueError("请先勾选至少一项可归炉物品。")

    for entry in normalized_items:
        _validate_official_recycle_request(
            tg=tg,
            item_kind=str(entry["item_kind"]),
            item_ref_id=int(entry["item_ref_id"]),
            quantity=int(entry["quantity"]),
        )

    recycled_items: list[dict[str, Any]] = []
    partial_error = ""
    for entry in normalized_items:
        try:
            recycled_items.append(
                recycle_item_to_official_shop(
                    tg=tg,
                    item_kind=str(entry["item_kind"]),
                    item_ref_id=int(entry["item_ref_id"]),
                    quantity=int(entry["quantity"]),
                )
            )
        except Exception as exc:
            partial_error = str(exc or "批量归炉中断。").strip() or "批量归炉中断。"
            break

    if not recycled_items and partial_error:
        raise ValueError(partial_error)

    total_quantity = sum(max(int(item.get("quantity") or 0), 0) for item in recycled_items)
    total_price = sum(max(int(item.get("total_price_stone") or 0), 0) for item in recycled_items)
    total_net_gain = sum(max(int(item.get("net_stone_gain") or item.get("total_price_stone") or 0), 0) for item in recycled_items)
    preview_names = "、".join(
        f"{item.get('item_name') or '未知物品'} x{max(int(item.get('quantity') or 0), 0)}"
        for item in recycled_items[:4]
    )
    if len(recycled_items) > 4:
        preview_names = f"{preview_names} 等 {len(recycled_items)} 项"
    summary_text = f"已归炉 {len(recycled_items)} 项，共 {total_quantity} 件，到账 {total_net_gain} 灵石"
    if preview_names:
        summary_text = f"{summary_text}：{preview_names}"

    result = {
        "shop_name": OFFICIAL_RECYCLE_NAME,
        "items": recycled_items,
        "recycled_line_count": len(recycled_items),
        "total_quantity": total_quantity,
        "total_price_stone": total_price,
        "net_stone_gain": total_net_gain,
        "summary_text": summary_text,
        "spiritual_stone_after": int(recycled_items[-1].get("spiritual_stone_after") or 0) if recycled_items else 0,
    }
    if partial_error:
        result["partial_success"] = True
        result["error_message"] = partial_error
    return result


def patch_shop_listing(item_id: int, **fields) -> dict[str, Any] | None:
    current = next(
        (item for item in list_shop_items(official_only=None, include_disabled=True) if int(item.get("id") or 0) == int(item_id)),
        None,
    )
    if "quantity" in fields:
        if current is not None and str(current.get("item_kind") or "") == "artifact":
            artifact = get_artifact(int(current.get("item_ref_id") or 0))
            if artifact is not None and bool(getattr(artifact, "unique_item", False)) and int(fields.get("quantity") or 0) > 1:
                raise ValueError(f"唯一法宝【{getattr(artifact, 'name', current.get('item_ref_id'))}】最多只能上架 1 件。")
    if current is not None and bool(current.get("is_official")):
        payload = _official_seed_item_payload(str(current.get("item_kind") or ""), int(current.get("item_ref_id") or 0))
        if payload is not None:
            fields["item_name"] = str(payload.get("name") or current.get("item_name") or "")
            fields["price_stone"] = _seed_official_shop_price(str(current.get("item_kind") or ""), payload)
    return update_shop_item(item_id, **fields)


def patch_auction_listing(auction_id: int, **fields) -> dict[str, Any] | None:
    return update_auction_item(auction_id, **fields)


def _normalize_notice_group_id(value: Any) -> int | str:
    if value in {None, ""}:
        return 0
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def _default_arena_stage_rule_map() -> dict[str, dict[str, int]]:
    rules: dict[str, dict[str, int]] = {}
    for entry in list(DEFAULT_SETTINGS.get("arena_stage_rules") or []):
        stage = normalize_realm_stage((entry or {}).get("realm_stage") or FIRST_REALM_STAGE)
        if stage not in REALM_ORDER or stage in rules:
            continue
        rules[stage] = {
            "duration_minutes": max(int((entry or {}).get("duration_minutes") or 60), 1),
            "reward_cultivation": max(int((entry or {}).get("reward_cultivation") or 0), 0),
        }
    for stage in REALM_ORDER:
        rules.setdefault(
            stage,
            {
                "duration_minutes": 120,
                "reward_cultivation": calculate_arena_cultivation_cap(stage),
            },
        )
    return rules


def _normalize_arena_stage_rules(raw: Any) -> list[dict[str, int | str]]:
    defaults = _default_arena_stage_rule_map()
    normalized_map: dict[str, dict[str, int | str]] = {}
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            stage = normalize_realm_stage(entry.get("realm_stage") or FIRST_REALM_STAGE)
            if stage not in REALM_ORDER or stage in normalized_map:
                continue
            default_rule = defaults.get(stage) or defaults[FIRST_REALM_STAGE]
            legacy_reward = max(int(cultivation_threshold(stage, 1) or 0), 0)
            normalized_reward = max(_coerce_int(entry.get("reward_cultivation"), int(default_rule["reward_cultivation"]), 0), 0)
            if normalized_reward == legacy_reward:
                normalized_reward = int(default_rule["reward_cultivation"])
            normalized_map[stage] = {
                "realm_stage": stage,
                "duration_minutes": min(
                    max(_coerce_int(entry.get("duration_minutes"), int(default_rule["duration_minutes"]), 10), 10),
                    7 * 24 * 60,
                ),
                "reward_cultivation": min(normalized_reward, 10**12),
            }
    rows: list[dict[str, int | str]] = []
    for stage in REALM_ORDER:
        rule = normalized_map.get(stage)
        if rule is None:
            default_rule = defaults.get(stage) or defaults[FIRST_REALM_STAGE]
            rule = {
                "realm_stage": stage,
                "duration_minutes": int(default_rule["duration_minutes"]),
                "reward_cultivation": int(default_rule["reward_cultivation"]),
            }
        rows.append(rule)
    return rows


def update_xiuxian_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current_settings = get_xiuxian_settings()
    patch = dict(payload)
    if "coin_stone_exchange_enabled" in patch:
        patch["coin_stone_exchange_enabled"] = bool(patch["coin_stone_exchange_enabled"])
    if "duel_bet_minutes" in patch and patch.get("duel_bet_seconds") is None:
        patch["duel_bet_seconds"] = max(
            _coerce_int(patch.get("duel_bet_minutes"), DEFAULT_SETTINGS.get("duel_bet_minutes", 2), 1),
            1,
        ) * 60
    duel_bet_keys = {
        "duel_bet_enabled",
        "duel_bet_seconds",
        "duel_bet_min_amount",
        "duel_bet_max_amount",
        "duel_bet_amount_options",
        "duel_bet_minutes",
    }
    if duel_bet_keys & set(patch):
        candidate = dict(current_settings)
        candidate.update(patch)
        patch.update(resolve_duel_bet_settings(candidate))
        patch.pop("duel_bet_minutes", None)
    if "auction_fee_percent" in patch and patch["auction_fee_percent"] is not None:
        patch["auction_fee_percent"] = min(
            max(_coerce_int(patch["auction_fee_percent"], DEFAULT_SETTINGS["auction_fee_percent"], 0), 0),
            100,
        )
    if "auction_duration_minutes" in patch and patch["auction_duration_minutes"] is not None:
        patch["auction_duration_minutes"] = min(
            max(_coerce_int(patch["auction_duration_minutes"], DEFAULT_SETTINGS["auction_duration_minutes"], 1), 1),
            7 * 24 * 60,
        )
    if "shop_broadcast_cost" in patch and patch["shop_broadcast_cost"] is not None:
        patch["shop_broadcast_cost"] = min(
            _coerce_int(
                patch["shop_broadcast_cost"],
                DEFAULT_SETTINGS["shop_broadcast_cost"],
                0,
            ),
            1000000,
        )
    if "shop_notice_group_id" in patch:
        patch["shop_notice_group_id"] = _normalize_notice_group_id(patch.get("shop_notice_group_id"))
    if "official_shop_name" in patch and patch["official_shop_name"] is not None:
        patch["official_shop_name"] = str(patch["official_shop_name"]).strip() or DEFAULT_SETTINGS["official_shop_name"]
    if "auction_notice_group_id" in patch:
        patch["auction_notice_group_id"] = _normalize_notice_group_id(patch.get("auction_notice_group_id"))
    if "allow_user_task_publish" in patch:
        patch["allow_user_task_publish"] = bool(patch["allow_user_task_publish"])
    if "task_publish_cost" in patch and patch["task_publish_cost"] is not None:
        patch["task_publish_cost"] = min(
            _coerce_int(
                patch["task_publish_cost"],
                DEFAULT_SETTINGS["task_publish_cost"],
                0,
            ),
            1000000,
        )
    if "user_task_daily_limit" in patch and patch["user_task_daily_limit"] is not None:
        patch["user_task_daily_limit"] = min(
            _coerce_int(
                patch["user_task_daily_limit"],
                DEFAULT_SETTINGS["user_task_daily_limit"],
                0,
            ),
            1000,
        )
    if "chat_cultivation_chance" in patch and patch["chat_cultivation_chance"] is not None:
        patch["chat_cultivation_chance"] = min(
            _coerce_int(
                patch["chat_cultivation_chance"],
                DEFAULT_SETTINGS["chat_cultivation_chance"],
                0,
            ),
            100,
        )
    if "chat_cultivation_min_gain" in patch and patch["chat_cultivation_min_gain"] is not None:
        patch["chat_cultivation_min_gain"] = min(
            _coerce_int(
                patch["chat_cultivation_min_gain"],
                DEFAULT_SETTINGS["chat_cultivation_min_gain"],
                1,
            ),
            100000,
        )
    if "chat_cultivation_max_gain" in patch and patch["chat_cultivation_max_gain"] is not None:
        patch["chat_cultivation_max_gain"] = min(
            _coerce_int(
                patch["chat_cultivation_max_gain"],
                DEFAULT_SETTINGS["chat_cultivation_max_gain"],
                1,
            ),
            100000,
        )
    if "chat_cultivation_min_gain" in patch or "chat_cultivation_max_gain" in patch:
        min_value = int(patch.get("chat_cultivation_min_gain", DEFAULT_SETTINGS["chat_cultivation_min_gain"]) or 1)
        max_value = int(patch.get("chat_cultivation_max_gain", DEFAULT_SETTINGS["chat_cultivation_max_gain"]) or min_value)
        if max_value < min_value:
            if "chat_cultivation_max_gain" in patch:
                patch["chat_cultivation_max_gain"] = min_value
            else:
                patch["chat_cultivation_min_gain"] = max_value
    if "robbery_daily_limit" in patch and patch["robbery_daily_limit"] is not None:
        patch["robbery_daily_limit"] = min(
            _coerce_int(
                patch["robbery_daily_limit"],
                DEFAULT_SETTINGS["robbery_daily_limit"],
                0,
            ),
            100,
        )
    if "robbery_max_steal" in patch and patch["robbery_max_steal"] is not None:
        patch["robbery_max_steal"] = min(
            _coerce_int(
                patch["robbery_max_steal"],
                DEFAULT_SETTINGS["robbery_max_steal"],
                0,
            ),
            1000000,
        )
    if "encounter_auto_dispatch_enabled" in patch:
        patch["encounter_auto_dispatch_enabled"] = bool(patch["encounter_auto_dispatch_enabled"])
    if "encounter_auto_dispatch_hour" in patch and patch["encounter_auto_dispatch_hour"] is not None:
        patch["encounter_auto_dispatch_hour"] = min(
            max(
                _coerce_int(
                    patch["encounter_auto_dispatch_hour"],
                    DEFAULT_SETTINGS["encounter_auto_dispatch_hour"],
                    0,
                ),
                0,
            ),
            23,
        )
    if "encounter_auto_dispatch_minute" in patch and patch["encounter_auto_dispatch_minute"] is not None:
        patch["encounter_auto_dispatch_minute"] = min(
            max(
                _coerce_int(
                    patch["encounter_auto_dispatch_minute"],
                    DEFAULT_SETTINGS["encounter_auto_dispatch_minute"],
                    0,
                ),
                0,
            ),
            59,
        )
    if "encounter_auto_dispatch_last_dates" in patch:
        raw_dates = patch["encounter_auto_dispatch_last_dates"] if isinstance(patch["encounter_auto_dispatch_last_dates"], dict) else {}
        patch["encounter_auto_dispatch_last_dates"] = {
            str(chat_id): str(day_key)
            for chat_id, day_key in raw_dates.items()
            if str(chat_id or "").strip() and str(day_key or "").strip()
        }
    if "equipment_unbind_cost" in patch and patch["equipment_unbind_cost"] is not None:
        patch["equipment_unbind_cost"] = min(
            _coerce_int(
                patch["equipment_unbind_cost"],
                DEFAULT_SETTINGS["equipment_unbind_cost"],
                0,
            ),
            1000000,
        )
    if "artifact_plunder_chance" in patch and patch["artifact_plunder_chance"] is not None:
        patch["artifact_plunder_chance"] = min(
            _coerce_int(
                patch["artifact_plunder_chance"],
                DEFAULT_SETTINGS["artifact_plunder_chance"],
                0,
            ),
            100,
        )
    if "artifact_equip_limit" in patch and patch["artifact_equip_limit"] is not None:
        patch["artifact_equip_limit"] = min(
            max(
                _coerce_int(
                    patch["artifact_equip_limit"],
                    DEFAULT_SETTINGS["artifact_equip_limit"],
                    1,
                ),
                1,
            ),
            12,
        )
    if "duel_winner_steal_percent" in patch and patch["duel_winner_steal_percent"] is not None:
        patch["duel_winner_steal_percent"] = min(
            _coerce_int(
                patch["duel_winner_steal_percent"],
                DEFAULT_SETTINGS["duel_winner_steal_percent"],
                0,
            ),
            100,
        )
    if "duel_invite_timeout_seconds" in patch and patch["duel_invite_timeout_seconds"] is not None:
        patch["duel_invite_timeout_seconds"] = min(
            _coerce_int(
                patch["duel_invite_timeout_seconds"],
                DEFAULT_SETTINGS["duel_invite_timeout_seconds"],
                10,
            ),
            1800,
        )
    if "arena_open_fee_stone" in patch and patch["arena_open_fee_stone"] is not None:
        patch["arena_open_fee_stone"] = min(
            _coerce_int(
                patch["arena_open_fee_stone"],
                DEFAULT_SETTINGS["arena_open_fee_stone"],
                0,
            ),
            1000000,
        )
    if "arena_challenge_fee_stone" in patch and patch["arena_challenge_fee_stone"] is not None:
        patch["arena_challenge_fee_stone"] = min(
            _coerce_int(
                patch["arena_challenge_fee_stone"],
                DEFAULT_SETTINGS["arena_challenge_fee_stone"],
                0,
            ),
            1000000,
        )
    if "arena_notice_group_id" in patch:
        patch["arena_notice_group_id"] = _normalize_notice_group_id(patch.get("arena_notice_group_id"))
    if "arena_stage_rules" in patch:
        patch["arena_stage_rules"] = _normalize_arena_stage_rules(patch.get("arena_stage_rules"))
    if "event_summary_interval_minutes" in patch and patch["event_summary_interval_minutes"] is not None:
        patch["event_summary_interval_minutes"] = min(
            max(
                _coerce_int(
                    patch["event_summary_interval_minutes"],
                    DEFAULT_SETTINGS.get("event_summary_interval_minutes", 10),
                    0,
                ),
                0,
            ),
            1440,
        )
    if "slave_tribute_percent" in patch and patch["slave_tribute_percent"] is not None:
        patch["slave_tribute_percent"] = min(
            _coerce_int(
                patch["slave_tribute_percent"],
                DEFAULT_SETTINGS["slave_tribute_percent"],
                0,
            ),
            100,
        )
    if "slave_challenge_cooldown_hours" in patch and patch["slave_challenge_cooldown_hours"] is not None:
        patch["slave_challenge_cooldown_hours"] = min(
            _coerce_int(
                patch["slave_challenge_cooldown_hours"],
                DEFAULT_SETTINGS["slave_challenge_cooldown_hours"],
                1,
            ),
            720,
        )
    if "rebirth_cooldown_enabled" in patch:
        patch["rebirth_cooldown_enabled"] = bool(patch["rebirth_cooldown_enabled"])
    if "rebirth_cooldown_base_hours" in patch and patch["rebirth_cooldown_base_hours"] is not None:
        patch["rebirth_cooldown_base_hours"] = min(
            _coerce_int(
                patch["rebirth_cooldown_base_hours"],
                DEFAULT_SETTINGS["rebirth_cooldown_base_hours"],
                0,
            ),
            8760,
        )
    if "rebirth_cooldown_increment_hours" in patch and patch["rebirth_cooldown_increment_hours"] is not None:
        patch["rebirth_cooldown_increment_hours"] = min(
            _coerce_int(
                patch["rebirth_cooldown_increment_hours"],
                DEFAULT_SETTINGS["rebirth_cooldown_increment_hours"],
                0,
            ),
            8760,
        )
    if "furnace_harvest_cultivation_percent" in patch and patch["furnace_harvest_cultivation_percent"] is not None:
        patch["furnace_harvest_cultivation_percent"] = min(
            _coerce_int(
                patch["furnace_harvest_cultivation_percent"],
                DEFAULT_SETTINGS["furnace_harvest_cultivation_percent"],
                0,
            ),
            100,
        )
    if "sect_salary_min_stay_days" in patch and patch["sect_salary_min_stay_days"] is not None:
        patch["sect_salary_min_stay_days"] = min(
            _coerce_int(
                patch["sect_salary_min_stay_days"],
                DEFAULT_SETTINGS["sect_salary_min_stay_days"],
                1,
            ),
            3650,
        )
    if "sect_betrayal_cooldown_days" in patch and patch["sect_betrayal_cooldown_days"] is not None:
        patch["sect_betrayal_cooldown_days"] = min(
            _coerce_int(
                patch["sect_betrayal_cooldown_days"],
                DEFAULT_SETTINGS["sect_betrayal_cooldown_days"],
                1,
            ),
            3650,
        )
    if "sect_betrayal_stone_percent" in patch and patch["sect_betrayal_stone_percent"] is not None:
        patch["sect_betrayal_stone_percent"] = min(
            _coerce_int(
                patch["sect_betrayal_stone_percent"],
                DEFAULT_SETTINGS["sect_betrayal_stone_percent"],
                0,
            ),
            100,
        )
    if "sect_betrayal_stone_min" in patch and patch["sect_betrayal_stone_min"] is not None:
        patch["sect_betrayal_stone_min"] = min(
            _coerce_int(
                patch["sect_betrayal_stone_min"],
                DEFAULT_SETTINGS["sect_betrayal_stone_min"],
                0,
            ),
            1000000,
        )
    if "sect_betrayal_stone_max" in patch and patch["sect_betrayal_stone_max"] is not None:
        patch["sect_betrayal_stone_max"] = min(
            _coerce_int(
                patch["sect_betrayal_stone_max"],
                DEFAULT_SETTINGS["sect_betrayal_stone_max"],
                0,
            ),
            1000000,
        )
    if "sect_betrayal_stone_min" in patch or "sect_betrayal_stone_max" in patch:
        min_value = int(patch.get("sect_betrayal_stone_min", DEFAULT_SETTINGS["sect_betrayal_stone_min"]) or 0)
        max_value = int(patch.get("sect_betrayal_stone_max", DEFAULT_SETTINGS["sect_betrayal_stone_max"]) or 0)
        if max_value < min_value:
            if "sect_betrayal_stone_max" in patch:
                patch["sect_betrayal_stone_max"] = min_value
            else:
                patch["sect_betrayal_stone_min"] = max_value
    if "error_log_retention_count" in patch and patch["error_log_retention_count"] is not None:
        patch["error_log_retention_count"] = min(
            _coerce_int(
                patch["error_log_retention_count"],
                DEFAULT_SETTINGS["error_log_retention_count"],
                1,
            ),
            10000,
        )
    if "message_auto_delete_seconds" in patch and patch["message_auto_delete_seconds"] is not None:
        patch["message_auto_delete_seconds"] = min(
            _coerce_int(
                patch["message_auto_delete_seconds"],
                DEFAULT_SETTINGS["message_auto_delete_seconds"],
                0,
            ),
            86400,
        )
    if "seclusion_cultivation_efficiency_percent" in patch and patch["seclusion_cultivation_efficiency_percent"] is not None:
        patch["seclusion_cultivation_efficiency_percent"] = min(
            _coerce_int(
                patch["seclusion_cultivation_efficiency_percent"],
                DEFAULT_SETTINGS["seclusion_cultivation_efficiency_percent"],
                0,
            ),
            100,
        )
    if "root_quality_value_rules" in patch:
        patch["root_quality_value_rules"] = _normalize_root_quality_value_rules(patch["root_quality_value_rules"])
    if "item_quality_value_rules" in patch:
        patch["item_quality_value_rules"] = _normalize_item_quality_value_rules(patch["item_quality_value_rules"])
    if "activity_stat_growth_rules" in patch:
        patch["activity_stat_growth_rules"] = _normalize_activity_stat_growth_rules(patch["activity_stat_growth_rules"])
    if "exploration_drop_weight_rules" in patch:
        defaults = DEFAULT_SETTINGS["exploration_drop_weight_rules"]
        raw = patch["exploration_drop_weight_rules"] if isinstance(patch["exploration_drop_weight_rules"], dict) else {}
        patch["exploration_drop_weight_rules"] = {
            "material_divine_sense_divisor": _coerce_int(raw.get("material_divine_sense_divisor"), defaults["material_divine_sense_divisor"], 1),
            "high_quality_threshold": min(
                _coerce_int(raw.get("high_quality_threshold"), defaults["high_quality_threshold"], 1),
                max(ROOT_QUALITY_LEVELS.values()),
            ),
            "high_quality_fortune_divisor": _coerce_int(raw.get("high_quality_fortune_divisor"), defaults["high_quality_fortune_divisor"], 1),
            "high_quality_root_level_start": _coerce_int(raw.get("high_quality_root_level_start"), defaults["high_quality_root_level_start"], 0),
        }
    if "high_quality_broadcast_level" in patch and patch["high_quality_broadcast_level"] is not None:
        patch["high_quality_broadcast_level"] = max(6, min(
            _coerce_int(patch["high_quality_broadcast_level"], DEFAULT_SETTINGS["high_quality_broadcast_level"], 1),
            max(ROOT_QUALITY_LEVELS.values()),
        ))
    if "gambling_exchange_cost_stone" in patch and patch["gambling_exchange_cost_stone"] is not None:
        patch["gambling_exchange_cost_stone"] = min(
            _coerce_int(
                patch["gambling_exchange_cost_stone"],
                DEFAULT_SETTINGS["gambling_exchange_cost_stone"],
                1,
            ),
            1000000,
        )
    if "gambling_exchange_max_count" in patch and patch["gambling_exchange_max_count"] is not None:
        patch["gambling_exchange_max_count"] = min(
            _coerce_int(
                patch["gambling_exchange_max_count"],
                DEFAULT_SETTINGS["gambling_exchange_max_count"],
                1,
            ),
            999,
        )
    if "gambling_open_max_count" in patch and patch["gambling_open_max_count"] is not None:
        patch["gambling_open_max_count"] = min(
            _coerce_int(
                patch["gambling_open_max_count"],
                DEFAULT_SETTINGS["gambling_open_max_count"],
                1,
            ),
            999,
        )
    if "gambling_broadcast_quality_level" in patch and patch["gambling_broadcast_quality_level"] is not None:
        patch["gambling_broadcast_quality_level"] = max(6, min(
            _coerce_int(
                patch["gambling_broadcast_quality_level"],
                DEFAULT_SETTINGS["gambling_broadcast_quality_level"],
                1,
            ),
            max(ROOT_QUALITY_LEVELS.values()),
        ))
    if "gambling_fortune_divisor" in patch and patch["gambling_fortune_divisor"] is not None:
        patch["gambling_fortune_divisor"] = min(
            _coerce_int(
                patch["gambling_fortune_divisor"],
                DEFAULT_SETTINGS["gambling_fortune_divisor"],
                1,
            ),
            1000,
        )
    if "gambling_fortune_bonus_per_quality_percent" in patch and patch["gambling_fortune_bonus_per_quality_percent"] is not None:
        patch["gambling_fortune_bonus_per_quality_percent"] = min(
            _coerce_int(
                patch["gambling_fortune_bonus_per_quality_percent"],
                DEFAULT_SETTINGS["gambling_fortune_bonus_per_quality_percent"],
                0,
            ),
            500,
        )
    if "gambling_quality_weight_rules" in patch:
        patch["gambling_quality_weight_rules"] = _normalize_gambling_quality_weight_rules(patch["gambling_quality_weight_rules"])
    if "fishing_quality_weight_rules" in patch:
        patch["fishing_quality_weight_rules"] = _normalize_fishing_quality_weight_rules(patch["fishing_quality_weight_rules"])
    source_gambling_pool = patch.get("gambling_reward_pool", current_settings.get("gambling_reward_pool"))
    if isinstance(source_gambling_pool, list):
        normalized_gambling_pool = _normalize_gambling_reward_pool(source_gambling_pool)
        should_persist_pool = "gambling_reward_pool" in patch or any(
            not int((entry or {}).get("item_ref_id") or 0)
            or not int((entry or {}).get("quality_level") or 0)
            or "gambling_weight" not in (entry or {})
            or "fishing_weight" not in (entry or {})
            or "gambling_enabled" not in (entry or {})
            or "fishing_enabled" not in (entry or {})
            for entry in source_gambling_pool
            if isinstance(entry, dict)
        )
        if should_persist_pool:
            patch["gambling_reward_pool"] = normalized_gambling_pool
    if "immortal_touch_infusion_layers" in patch and patch["immortal_touch_infusion_layers"] is not None:
        patch["immortal_touch_infusion_layers"] = min(
            _coerce_int(
                patch["immortal_touch_infusion_layers"],
                DEFAULT_SETTINGS["immortal_touch_infusion_layers"],
                1,
            ),
            9,
        )
    settings = set_xiuxian_settings(patch)
    if "official_shop_name" in patch:
        sync_official_shop_name(settings["official_shop_name"])
    return settings


def build_gambling_bundle(tg: int, bundle: dict[str, Any] | None = None, *, include_source_labels: bool = False) -> dict[str, Any]:
    ensure_seed_data()
    current_bundle = bundle or {}
    settings = get_xiuxian_settings()
    immortal_stone = _immortal_stone_material()
    material_id = int(immortal_stone.get("id") or 0)
    if isinstance(current_bundle.get("materials"), list):
        owned_row = next(
            (
                row
                for row in current_bundle.get("materials") or []
                if int(((row or {}).get("material") or {}).get("id") or 0) == material_id
                or str(((row or {}).get("material") or {}).get("name") or "").strip() == IMMORTAL_STONE_NAME
            ),
            None,
        )
        owned_quantity = int((owned_row or {}).get("quantity") or 0)
    else:
        with Session() as session:
            owned_quantity = sum(
                max(int(row.quantity or 0), 0)
                for row in session.query(XiuxianMaterialInventory)
                .filter(XiuxianMaterialInventory.tg == int(tg), XiuxianMaterialInventory.material_id == material_id)
                .all()
            )
    effective_stats = current_bundle.get("effective_stats") or {}
    profile = current_bundle.get("profile") or serialize_profile(get_profile(tg, create=False)) or {}
    fortune_value = int(effective_stats.get("fortune", profile.get("fortune", FORTUNE_BASELINE)) or FORTUNE_BASELINE)
    quality_rules = _normalize_gambling_quality_weight_rules(settings.get("gambling_quality_weight_rules"))
    raw_pool = _configured_gambling_pool(settings)
    source_catalog = get_item_source_catalog() if include_source_labels else {}
    empty_chance = _gambling_empty_chance(fortune_value)
    enabled_pool = []
    total_effective_weight = 0.0
    for entry in raw_pool:
        weight = _gambling_entry_effective_weight(entry, fortune_value, settings)
        if _reward_pool_entry_enabled(entry, "gambling") and int(entry.get("item_ref_id") or 0) > 0 and weight > 0:
            payload = {
                **entry,
                "effective_weight": round(weight, 6),
            }
            total_effective_weight += weight
            enabled_pool.append(payload)
    for entry in enabled_pool:
        chance = (
            float(entry.get("effective_weight") or 0.0) / total_effective_weight * 100.0 * max(1.0 - empty_chance, 0.0)
        ) if total_effective_weight > 0 else 0.0
        if include_source_labels:
            source_labels = source_catalog.get(
                (str(entry.get("item_kind") or "").strip(), int(entry.get("item_ref_id") or 0)),
                [],
            )
            route_labels = [label for label in source_labels if label != "仙界奇石"] or source_labels
            if not route_labels and str(entry.get("item_kind") or "").strip() == "recipe":
                route_labels = _recipe_fragment_source_labels(int(entry.get("item_ref_id") or 0), source_catalog)
            entry["source_labels"] = route_labels[:6]
            entry["source_summary"] = "、".join(route_labels[:4]) if route_labels else ""
        entry["chance_percent"] = chance
    enabled_pool.sort(
        key=lambda item: (
            -int(item.get("quality_level") or 0),
            -float(item.get("chance_percent") or 0.0),
            str(item.get("item_name") or ""),
        )
    )
    return {
        "immortal_stone_material_id": int(immortal_stone.get("id") or 0),
        "immortal_stone_name": IMMORTAL_STONE_NAME,
        "immortal_stone_item": immortal_stone,
        "owned_count": owned_quantity,
        "exchange_cost_stone": max(
            int(settings.get("gambling_exchange_cost_stone", DEFAULT_SETTINGS["gambling_exchange_cost_stone"]) or 0),
            1,
        ),
        "exchange_max_count": max(
            int(settings.get("gambling_exchange_max_count", DEFAULT_SETTINGS["gambling_exchange_max_count"]) or 0),
            1,
        ),
        "open_max_count": max(
            int(settings.get("gambling_open_max_count", DEFAULT_SETTINGS["gambling_open_max_count"]) or 0),
            1,
        ),
        "broadcast_quality_level": max(
            int(settings.get("gambling_broadcast_quality_level", DEFAULT_SETTINGS["gambling_broadcast_quality_level"]) or 0),
            6,
        ),
        "fortune_value": fortune_value,
        "empty_chance_percent": round(empty_chance * 100.0, 2),
        "fortune_hint": _gambling_fortune_hint(fortune_value, settings),
        "quality_weight_rules": quality_rules,
        "pool_preview": enabled_pool,
        "pool_size": len(enabled_pool),
    }


def _gambling_effective_fortune(tg: int) -> tuple[int, dict[str, Any]]:
    profile_obj = get_profile(int(tg), create=False)
    profile_payload = serialize_profile(profile_obj) if profile_obj is not None else {}
    if not profile_payload:
        return FORTUNE_BASELINE, {}
    battle_bundle = _battle_bundle(profile_payload)
    effective_stats = battle_bundle.get("stats") or {}
    fortune_value = int(effective_stats.get("fortune") or profile_payload.get("fortune") or FORTUNE_BASELINE)
    return max(fortune_value, 0), profile_payload


def exchange_immortal_stones(tg: int, count: int) -> dict[str, Any]:
    ensure_seed_data()
    amount = max(int(count or 0), 0)
    if amount <= 0:
        raise ValueError("兑换数量必须大于 0。")
    settings = get_xiuxian_settings()
    max_count = max(int(settings.get("gambling_exchange_max_count", DEFAULT_SETTINGS["gambling_exchange_max_count"]) or 0), 1)
    if amount > max_count:
        raise ValueError(f"单次最多只能兑换 {max_count} 枚仙界奇石。")
    if not _configured_gambling_pool(settings):
        raise ValueError("当前赌坊奖池尚未配置，请稍后再试。")
    stone_cost = max(int(settings.get("gambling_exchange_cost_stone", DEFAULT_SETTINGS["gambling_exchange_cost_stone"]) or 0), 1)
    total_cost = stone_cost * amount
    immortal_stone = _immortal_stone_material()
    material_id = int(immortal_stone.get("id") or 0)

    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("请先踏入仙途后再进入赌坊。")
        assert_profile_alive(profile, "兑换仙界奇石")
        assert_currency_operation_allowed(int(tg), "兑换仙界奇石", session=session, profile=profile)
        apply_spiritual_stone_delta(
            session,
            int(tg),
            -total_cost,
            action_text=f"兑换{amount}枚仙界奇石",
            allow_dead=False,
            apply_tribute=False,
        )
        row = (
            session.query(XiuxianMaterialInventory)
            .filter(XiuxianMaterialInventory.tg == int(tg), XiuxianMaterialInventory.material_id == material_id)
            .with_for_update()
            .first()
        )
        if row is None:
            row = XiuxianMaterialInventory(tg=int(tg), material_id=material_id, quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        session.commit()
        remaining_quantity = int(row.quantity or 0)

    create_journal(
        int(tg),
        "gambling",
        "兑换仙界奇石",
        f"消耗 {total_cost} 灵石，兑换了 {amount} 枚{IMMORTAL_STONE_NAME}。",
    )
    profile = serialize_profile(get_profile(int(tg), create=False)) or {}
    return {
        "exchange_count": amount,
        "cost_per_stone": stone_cost,
        "total_cost_stone": total_cost,
        "immortal_stone_quantity": remaining_quantity,
        "immortal_stone_item": immortal_stone,
        "profile": profile,
    }


def open_immortal_stones(tg: int, count: int) -> dict[str, Any]:
    ensure_seed_data()
    amount = max(int(count or 0), 0)
    if amount <= 0:
        raise ValueError("开启数量必须大于 0。")
    settings = get_xiuxian_settings()
    max_count = max(int(settings.get("gambling_open_max_count", DEFAULT_SETTINGS["gambling_open_max_count"]) or 0), 1)
    if amount > max_count:
        raise ValueError(f"单次最多只能开启 {max_count} 枚仙界奇石。")

    fortune_value, _ = _gambling_effective_fortune(int(tg))
    empty_chance = _gambling_empty_chance(fortune_value)
    reward_pool = [
        entry
        for entry in _configured_gambling_pool(settings)
        if _reward_pool_entry_enabled(entry, "gambling") and int(entry.get("item_ref_id") or 0) > 0
    ]
    weighted_pool = [
        {
            **entry,
            "effective_weight": _gambling_entry_effective_weight(entry, fortune_value, settings),
        }
        for entry in reward_pool
    ]
    weighted_pool = [entry for entry in weighted_pool if float(entry.get("effective_weight") or 0.0) > 0]
    if not weighted_pool:
        raise ValueError("当前赌坊奖池为空，请联系主人先配置奖励。")
    immortal_stone = _immortal_stone_material()
    immortal_stone_id = int(immortal_stone.get("id") or 0)
    broadcast_level = max(
        int(settings.get("gambling_broadcast_quality_level", DEFAULT_SETTINGS["gambling_broadcast_quality_level"]) or 0),
        6,
    )

    results: list[dict[str, Any]] = []
    empty_count = 0
    with Session() as session:
        artifact_meta_map: dict[int, XiuxianArtifact] = {}
        selected_unique_artifact_ids: set[int] = set()

        def _artifact_meta(artifact_id: int) -> XiuxianArtifact | None:
            artifact_value = int(artifact_id or 0)
            if artifact_value <= 0:
                return None
            if artifact_value not in artifact_meta_map:
                artifact_meta_map[artifact_value] = (
                    session.query(XiuxianArtifact)
                    .filter(XiuxianArtifact.id == artifact_value)
                    .with_for_update()
                    .first()
                )
            return artifact_meta_map.get(artifact_value)

        def _reward_entry_available(entry: dict[str, Any]) -> bool:
            if str(entry.get("item_kind") or "") != "artifact":
                return True
            artifact_id = int(entry.get("item_ref_id") or 0)
            artifact = _artifact_meta(artifact_id)
            if artifact is None:
                return False
            if not bool(artifact.unique_item):
                return True
            if artifact_id in selected_unique_artifact_ids:
                return False
            holder = (
                session.query(XiuxianArtifactInventory)
                .filter(
                    XiuxianArtifactInventory.artifact_id == artifact_id,
                    XiuxianArtifactInventory.quantity > 0,
                    XiuxianArtifactInventory.tg != int(tg),
                )
                .with_for_update()
                .first()
            )
            if holder is not None:
                return False
            owned = (
                session.query(XiuxianArtifactInventory)
                .filter(
                    XiuxianArtifactInventory.artifact_id == artifact_id,
                    XiuxianArtifactInventory.tg == int(tg),
                    XiuxianArtifactInventory.quantity > 0,
                )
                .with_for_update()
                .first()
            )
            return owned is None

        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("请先踏入仙途后再进入赌坊。")
        assert_profile_alive(profile, "开启仙界奇石")
        assert_currency_operation_allowed(int(tg), "开启仙界奇石", session=session, profile=profile)
        drawn_entries: list[dict[str, Any]] = []
        for _ in range(amount):
            available_entries = [entry for entry in weighted_pool if _reward_entry_available(entry)]
            if not available_entries:
                empty_count += 1
                continue
            if secrets.SystemRandom().random() < empty_chance:
                empty_count += 1
                continue
            chosen_entry = secrets.SystemRandom().choices(
                available_entries,
                weights=[float(entry["effective_weight"]) for entry in available_entries],
                k=1,
            )[0]
            drawn_entries.append(chosen_entry)
            if str(chosen_entry.get("item_kind") or "") == "artifact":
                artifact = _artifact_meta(int(chosen_entry.get("item_ref_id") or 0))
                if artifact is not None and bool(artifact.unique_item):
                    selected_unique_artifact_ids.add(int(artifact.id or 0))
        remaining = amount
        rows = _ordered_owner_rows(session, XiuxianMaterialInventory, int(tg), "material_id", immortal_stone_id)
        total_owned = sum(max(int(row.quantity or 0), 0) for row in rows)
        if total_owned < remaining:
            raise ValueError(f"你的{IMMORTAL_STONE_NAME}数量不足。")
        for row in rows:
            if remaining <= 0:
                break
            available = max(int(row.quantity or 0), 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.quantity = available - delta
            row.updated_at = utcnow()
            remaining -= delta
            if row.quantity <= 0:
                session.delete(row)
        for entry in drawn_entries:
            item_kind = str(entry.get("item_kind") or "")
            quantity = 1 if item_kind in {"recipe", "technique"} else random.randint(
                max(int(entry.get("quantity_min") or 1), 1),
                max(int(entry.get("quantity_max") or entry.get("quantity_min") or 1), max(int(entry.get("quantity_min") or 1), 1)),
            )
            reward_payload = None
            actual_quantity = max(int(quantity or 0), 0)
            if item_kind not in {"recipe", "technique"}:
                reward_payload = _grant_gambling_reward_in_session(
                    session,
                    int(tg),
                    item_kind,
                    int(entry.get("item_ref_id") or 0),
                    quantity,
                )
                actual_quantity = max(int((reward_payload or {}).get("quantity") or quantity), 0)
            results.append(
                {
                    "item_kind": item_kind,
                    "item_kind_label": entry.get("item_kind_label"),
                    "item_ref_id": entry.get("item_ref_id"),
                    "item_name": entry.get("item_name"),
                    "quality_level": entry.get("quality_level"),
                    "quality_label": entry.get("quality_label"),
                    "quality_color": entry.get("quality_color"),
                    "quantity": actual_quantity,
                    "broadcasted": int(entry.get("quality_level") or 0) >= broadcast_level,
                    "reward": reward_payload,
                    "_post_commit": {
                        "item_kind": item_kind,
                        "item_ref_id": int(entry.get("item_ref_id") or 0),
                        "quantity": quantity,
                    } if item_kind in {"recipe", "technique"} else None,
                }
            )
        session.commit()

    for row in results:
        post_commit = row.pop("_post_commit", None)
        if not isinstance(post_commit, dict):
            continue
        row["reward"] = _grant_gambling_reward_after_commit(
            int(tg),
            str(post_commit.get("item_kind") or ""),
            int(post_commit.get("item_ref_id") or 0),
            int(post_commit.get("quantity") or 1),
        )

    summary = _format_gambling_reward_summary(results)
    summary_text = "、".join(
        (
            f"重复[{row['quality_label']}] {row['item_name']}折灵石 +{int(row.get('stone_compensation') or 0)}"
            if row.get("duplicate_converted")
            else f"[{row['quality_label']}] {row['item_name']} x{row['quantity']}"
        )
        for row in summary[:8]
    )
    if len(summary) > 8:
        summary_text += f" 等 {len(summary)} 项"
    if not summary_text:
        summary_text = "空手而归"
    if empty_count > 0:
        summary_text = f"{summary_text}（轮空 {empty_count} 次）" if results else f"空手而归 {empty_count} 次"
    create_journal(
        int(tg),
        "gambling",
        "开启仙界奇石",
        f"开启了 {amount} 枚{IMMORTAL_STONE_NAME}，获得：{summary_text}。",
    )
    remaining_quantity = next(
        (
            int(row.get("quantity") or 0)
            for row in list_user_materials(int(tg))
            if str(((row or {}).get("material") or {}).get("name") or "").strip() == IMMORTAL_STONE_NAME
        ),
        0,
    )
    return {
        "opened_count": amount,
        "remaining_immortal_stone": remaining_quantity,
        "fortune_value": fortune_value,
        "fortune_hint": _gambling_fortune_hint(fortune_value, settings),
        "empty_count": empty_count,
        "empty_chance_percent": round(empty_chance * 100.0, 2),
        "broadcast_quality_level": broadcast_level,
        "results": results,
        "summary": summary,
        "summary_text": summary_text,
    }


def grant_item_to_user(tg: int, item_kind: str, item_ref_id: int, quantity: int) -> dict[str, Any]:
    if item_kind == "artifact":
        return grant_artifact_to_user(tg, item_ref_id, quantity)
    if item_kind == "material":
        return grant_material_to_user(tg, item_ref_id, quantity)
    if item_kind == "pill":
        return grant_pill_to_user(tg, item_ref_id, quantity)
    if item_kind == "talisman":
        return grant_talisman_to_user(tg, item_ref_id, quantity)
    if item_kind == "recipe":
        return grant_recipe_to_user(tg, item_ref_id, source="admin", obtained_note="后台发放")
    if item_kind == "technique":
        return grant_technique_to_user(
            tg,
            item_ref_id,
            source="admin",
            obtained_note="后台发放",
            auto_equip_if_empty=True,
        )
    raise ValueError("不支持的发放物品类型。")


def purchase_shop_item(tg: int, item_id: int, quantity: int = 1) -> dict[str, Any]:
    ensure_not_in_retreat(tg)
    return sql_purchase_shop_item(tg, item_id, quantity)


def place_auction_bid(tg: int, auction_id: int, *, bidder_name: str = "", use_buyout: bool = False) -> dict[str, Any]:
    ensure_not_in_retreat(tg)
    profile = _require_alive_profile_obj(tg, "参与拍卖")
    assert_currency_operation_allowed(tg, "参与拍卖", profile=profile)
    return sql_place_auction_bid(
        auction_id,
        bidder_tg=tg,
        bidder_display_name=bidder_name,
        use_buyout=use_buyout,
    )


def finalize_auction_listing(auction_id: int, *, force: bool = False) -> dict[str, Any] | None:
    return sql_finalize_auction_item(auction_id, force=force)


def cancel_personal_auction_listing(tg: int, auction_id: int) -> dict[str, Any] | None:
    ensure_not_in_retreat(tg)
    profile = _require_alive_profile_obj(tg, "取消拍卖")
    assert_currency_operation_allowed(tg, "取消拍卖", profile=profile)
    return cancel_auction_item(auction_id, owner_tg=tg)


def compute_artifact_score(
    profile: dict[str, Any],
    equipped_artifacts: list[dict[str, Any]] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> int:
    if not equipped_artifacts:
        return 0
    effects = merge_artifact_effects(profile, equipped_artifacts, opponent_profile)
    return (
        int(round(effects.get("attack_bonus", 0)))
        + int(round(effects.get("defense_bonus", 0)))
        + int(round(effects.get("bone_bonus", 0)))
        + int(round(effects.get("comprehension_bonus", 0)))
        + int(round(effects.get("divine_sense_bonus", 0)))
        + int(round(effects.get("fortune_bonus", 0)))
        + int(round(effects.get("body_movement_bonus", 0)))
        + int(round(effects.get("qi_blood_bonus", 0) / 10))
        + int(round(effects.get("true_yuan_bonus", 0) / 10))
        + int(round(effects.get("duel_rate_bonus", 0))) * 10
        + int(round(effects.get("cultivation_bonus", 0))) * 2
    )


def compute_talisman_score(
    profile: dict[str, Any],
    active_talisman: dict[str, Any] | None,
    opponent_profile: dict[str, Any] | None = None,
) -> int:
    if active_talisman is None:
        return 0
    effects = resolve_talisman_effects(profile, active_talisman, opponent_profile)
    return (
        int(round(effects.get("attack_bonus", 0)))
        + int(round(effects.get("defense_bonus", 0)))
        + int(round(effects.get("bone_bonus", 0)))
        + int(round(effects.get("comprehension_bonus", 0)))
        + int(round(effects.get("divine_sense_bonus", 0)))
        + int(round(effects.get("fortune_bonus", 0)))
        + int(round(effects.get("body_movement_bonus", 0)))
        + int(round(effects.get("qi_blood_bonus", 0) / 10))
        + int(round(effects.get("true_yuan_bonus", 0) / 10))
        + int(round(effects.get("duel_rate_bonus", 0))) * 10
    )


def build_leaderboard(kind: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    profiles = [serialize_profile(row) for row in list_profiles()]
    kind = {
        "stone": "stone",
        "stones": "stone",
        "realm": "realm",
        "realms": "realm",
        "artifact": "artifact",
        "artifacts": "artifact",
    }.get(str(kind or "stone").strip().lower(), "stone")

    tgs = [int(item["tg"]) for item in profiles]
    emby_name_map = get_emby_name_map(tgs)
    equipped_artifact_map = _bulk_collect_equipped_artifacts(tgs) if kind == "artifact" else {}

    rows = []
    for item in profiles:
        tg = int(item["tg"])
        equipped_artifacts = equipped_artifact_map.get(tg, []) if kind == "artifact" else []
        artifact_name = ", ".join(artifact["name"] for artifact in equipped_artifacts[:3]) if equipped_artifacts else None
        artifact_score = compute_artifact_score(item, equipped_artifacts) if equipped_artifacts else 0
        base = {
            "tg": tg,
            "name": emby_name_map.get(tg, f"TG {tg}"),
            "realm_stage": item["realm_stage"],
            "realm_layer": item["realm_layer"],
            "cultivation": int(item["cultivation"] or 0),
            "spiritual_stone": item["spiritual_stone"],
            "artifact_name": artifact_name,
            "artifact_score": artifact_score,
            "realm_stage_rank": realm_index(item["realm_stage"]),
        }
        if kind == "stone":
            base["score"] = int(item["spiritual_stone"] or 0)
        elif kind == "realm":
            base["score"] = base["realm_stage_rank"]
        else:
            base["score"] = base["artifact_score"]
        rows.append(base)

    if kind == "realm":
        rows.sort(
            key=lambda row: (
                -int(row["realm_stage_rank"]),
                -int(row["realm_layer"] or 0),
                -int(row["cultivation"] or 0),
                -int(row["spiritual_stone"] or 0),
                int(row["tg"]),
            )
        )
    else:
        rows.sort(key=lambda row: (-int(row["score"] or 0), int(row["tg"])))
    rows = rows[:100]
    total = len(rows)
    total_pages = max((total + page_size - 1) // page_size, 1)
    current_page = min(max(int(page), 1), total_pages)
    start = (current_page - 1) * page_size
    items = rows[start:start + page_size]

    for index, item in enumerate(items, start=start + 1):
        item["rank"] = index

    return {
        "kind": kind,
        "page": current_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "items": items,
    }


def format_leaderboard_text(result: dict[str, Any]) -> str:
    def _rich_escape(value: Any) -> str:
        return re.sub(r"([_*\[`])", r"\\\1", str(value or ""))

    title_map = {
        "stone": "灵石排行榜",
        "realm": "境界排行榜",
        "artifact": "法宝排行榜",
    }
    lines = [f"🏆 **{title_map.get(result['kind'], '排行榜')}**", f"📄 页码：`{result['page']}/{result['total_pages']}`", ""]
    if not result["items"]:
        lines.append("📭 当前没有可显示的数据。")
        return "\n".join(lines)

    for item in result["items"]:
        if result["kind"] == "stone":
            desc = f"💎 灵石：`{item['spiritual_stone']}`"
        elif result["kind"] == "realm":
            desc = f"🏯 境界：`{_rich_escape(str(item['realm_stage']) + str(item['realm_layer']) + '层')}`"
        else:
            desc = f"🧿 本命法宝：{_rich_escape(item['artifact_name'] or '暂无装备法宝')}"
        lines.append(f"{item['rank']}. {_rich_escape(item['name'])}")
        lines.append(f"↳ {desc}")
    return "\n".join(lines)


def create_foundation_pill_for_user_if_missing(tg: int) -> None:
    pill_row = _find_pill_in_inventory(tg, "foundation")
    if pill_row is not None:
        return

    starter_pill = _select_starter_foundation_pill()
    if starter_pill is not None:
        grant_pill_to_user(tg, int(starter_pill["id"]), 1)


def _starter_foundation_pill_sort_key(pill: dict[str, Any]) -> tuple[int, int, int, str]:
    stage = normalize_realm_stage(pill.get("min_realm_stage"))
    if stage in REALM_ORDER:
        stage_rank = realm_index(stage)
    else:
        stage_rank = len(REALM_ORDER) + 1
    layer = int(pill.get("min_realm_layer") or 99)
    effect_value = int(pill.get("effect_value") or 0)
    return (stage_rank, layer, effect_value, str(pill.get("name") or ""))


def _select_starter_foundation_pill() -> dict[str, Any] | None:
    foundation_pills = [
        pill for pill in list_pills(enabled_only=True)
        if str(pill.get("pill_type") or "") == "foundation"
    ]
    if not foundation_pills:
        return None

    named_match = next(
        (
            pill for pill in foundation_pills
            if str(pill.get("name") or "").strip() == STARTER_FOUNDATION_PILL_NAME
        ),
        None,
    )
    if named_match is not None:
        return named_match

    early_stage_matches = [
        pill for pill in foundation_pills
        if normalize_realm_stage(pill.get("min_realm_stage")) == "炼气"
    ]
    if early_stage_matches:
        return min(early_stage_matches, key=_starter_foundation_pill_sort_key)

    return min(foundation_pills, key=_starter_foundation_pill_sort_key)


def _grant_entry_starter_assets(tg: int) -> None:
    ensure_seed_data()
    starter_title = next((item for item in list_titles(enabled_only=True) if str(item.get("name") or "") == STARTER_TITLE_NAME), None)
    starter_technique = next((item for item in list_techniques(enabled_only=True) if str(item.get("name") or "") == STARTER_TECHNIQUE_NAME), None)
    starter_artifact = next((item for item in list_artifacts(enabled_only=True) if str(item.get("name") or "") == STARTER_ARTIFACT_NAME), None)

    if starter_title is not None:
        grant_title_to_user(
            tg,
            int(starter_title["id"]),
            source="entry",
            obtained_note="初入仙途赠礼",
            auto_equip_if_empty=True,
        )
    if starter_technique is not None:
        grant_technique_to_user(
            tg,
            int(starter_technique["id"]),
            source="entry",
            obtained_note="初入仙途赠礼",
            auto_equip_if_empty=True,
        )
    if starter_artifact is not None:
        grant_starter_artifact_once(tg, int(starter_artifact["id"]))

    if starter_artifact is None:
        return

    starter_artifact_id = int(starter_artifact["id"])
    owned_artifact_ids = {
        int(((item.get("artifact") or {}).get("id") or 0))
        for item in list_user_artifacts(tg)
    }
    if starter_artifact_id not in owned_artifact_ids:
        return
    equipped_artifact_ids = {
        int(((item.get("artifact") or {}).get("id") or 0))
        for item in list_equipped_artifacts(tg)
    }
    if starter_artifact_id not in equipped_artifact_ids:
        set_equipped_artifact(tg, starter_artifact_id)


def admin_seed_demo_assets(tg: int) -> dict[str, Any]:
    ensure_seed_data()
    first_artifact = next((item for item in list_artifacts(enabled_only=True)), None)
    foundation_pill = _select_starter_foundation_pill()
    clear_pill = next((item for item in list_pills(enabled_only=True) if item["pill_type"] == "clear_poison"), None)
    first_talisman = next((item for item in list_talismans(enabled_only=True)), None)

    if first_artifact:
        grant_artifact_to_user(tg, first_artifact["id"], 1)
    if foundation_pill:
        grant_pill_to_user(tg, foundation_pill["id"], 1)
    if clear_pill:
        grant_pill_to_user(tg, clear_pill["id"], 1)
    if first_talisman:
        grant_talisman_to_user(tg, first_talisman["id"], 1)

    return serialize_full_profile(tg)


def maybe_gain_cultivation_from_chat(tg: int) -> dict[str, Any] | None:
    profile = _repair_profile_realm_state(tg) or get_profile(tg, create=False)
    if profile is None or not profile.consented or _is_retreating(profile):
        return None

    settings = get_xiuxian_settings()
    base_chance = max(min(int(settings.get("chat_cultivation_chance", DEFAULT_SETTINGS["chat_cultivation_chance"]) or 0), 100), 0)
    if base_chance <= 0:
        return None
    chance_roll = roll_probability_percent(
        base_chance,
        actor_fortune=int(profile.fortune or 0),
        actor_weight=0.35,
        minimum=0,
        maximum=100,
    )
    if not chance_roll["success"]:
        return None

    min_gain = max(int(settings.get("chat_cultivation_min_gain", DEFAULT_SETTINGS["chat_cultivation_min_gain"]) or 1), 1)
    max_gain = max(int(settings.get("chat_cultivation_max_gain", DEFAULT_SETTINGS["chat_cultivation_max_gain"]) or min_gain), min_gain)
    raw_gain = random.randint(min_gain, max_gain)
    gain, gain_meta = adjust_cultivation_gain_for_social_mode(profile, raw_gain, settings=settings)
    layer, cultivation, upgraded_layers, remaining = apply_cultivation_gain(
        normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE),
        int(profile.realm_layer or 1),
        int(profile.cultivation or 0),
        gain,
    )
    updated = upsert_profile(
        tg,
        cultivation=cultivation,
        realm_layer=layer,
    )
    _apply_profile_growth_floor(tg)
    return {
        "gain": gain,
        "gain_raw": raw_gain,
        "cultivation_efficiency_percent": int(gain_meta.get("efficiency_percent") or 100),
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "profile": serialize_profile(get_profile(updated.tg, create=False)),
    }


def broadcast_shop_copy(seller_name: str, shop_name: str, item_name: str, price_stone: int) -> str:
    return (
        f"📣 **坊市播报**\n"
        f"🧑‍🌾 {seller_name} 刚刚在 **{shop_name}** 上架了 **{item_name}**\n"
        f"💰 售价：{price_stone} 灵石\n"
        "🛍️ 感兴趣的道友可以前往修仙面板查看。"
    )


def _immortal_stone_material() -> dict[str, Any]:
    ensure_seed_data()
    material = next(
        (row for row in list_materials(enabled_only=True) if str(row.get("name") or "").strip() == IMMORTAL_STONE_NAME),
        None,
    )
    if material is None:
        raise ValueError(f"未找到特殊材料【{IMMORTAL_STONE_NAME}】。")
    return material


def _item_quality_level(kind: str, item: dict[str, Any]) -> int:
    if kind == "material":
        return int(item.get("quality_level") or 1)
    if kind == "recipe":
        result_kind = str(item.get("result_kind") or "").strip()
        result_ref_id = int(item.get("result_ref_id") or 0)
        if result_kind and result_ref_id > 0:
            result_item = _get_item_payload(result_kind, result_ref_id)
            if isinstance(result_item, dict):
                return _item_quality_level(result_kind, result_item)
        return 1
    if item.get("rarity_level") is not None:
        return max(int(item.get("rarity_level") or 1), 1)
    return int(get_quality_meta(item.get("rarity")).get("level") or 1)


def _gambling_reward_invalid_reason(kind: str, item: dict[str, Any] | None) -> str:
    normalized_kind = str(kind or "").strip()
    if item is None:
        return "未找到对应物品"
    if normalized_kind == "artifact" and bool(item.get("unique_item")):
        return "唯一法宝不能进入共享奖池"
    if normalized_kind == "pill" and str(item.get("pill_type") or "").strip() == "foundation":
        return "破境丹不能进入共享奖池"
    if normalized_kind == "material" and str(item.get("name") or "").strip() == IMMORTAL_STONE_NAME:
        return "仙界奇石不能作为自身奖池奖励"
    if normalized_kind == "recipe":
        result_kind = str(item.get("result_kind") or "").strip()
        result_ref_id = int(item.get("result_ref_id") or 0)
        result_item = _get_item_payload(result_kind, result_ref_id) if result_kind and result_ref_id > 0 else None
        if result_kind == "pill" and str((result_item or {}).get("pill_type") or "").strip() == "foundation":
            return "破境丹丹方不能进入共享奖池"
    return ""


def _reward_pool_quantity_range(kind: str, quality_level: int) -> tuple[int, int]:
    level = max(int(quality_level or 1), 1)
    normalized_kind = str(kind or "").strip()
    if normalized_kind == "material":
        if level <= 1:
            return 2, 4
        if level == 2:
            return 1, 3
        if level <= 4:
            return 1, 2
        return 1, 1
    if normalized_kind == "pill" and level <= 2:
        return 1, 2
    return 1, 1


def _reward_pool_default_weight(kind: str, quality_level: int, channel: str) -> float:
    level = max(min(int(quality_level or 1), 7), 1)
    quality_base = {
        1: 96.0,
        2: 52.0,
        3: 24.0,
        4: 10.0,
        5: 3.5,
        6: 1.0,
        7: 0.22,
    }
    factor_map = {
        "gambling": {
            "material": 1.0,
            "pill": 0.72,
            "talisman": 0.32,
            "artifact": 0.28,
            "recipe": 0.15,
            "technique": 0.11,
        },
        "fishing": {
            "material": 1.0,
            "pill": 0.58,
            "talisman": 0.22,
            "artifact": 0.16,
            "recipe": 0.08,
            "technique": 0.06,
        },
    }
    normalized_channel = "fishing" if str(channel or "").strip() == "fishing" else "gambling"
    normalized_kind = str(kind or "").strip()
    return round(quality_base.get(level, 1.0) * factor_map[normalized_channel].get(normalized_kind, 0.25), 3)


def _dynamic_gambling_reward_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    sources = {
        "material": list_materials(enabled_only=True),
        "artifact": list_artifacts(enabled_only=True),
        "pill": list_pills(enabled_only=True),
        "talisman": list_talismans(enabled_only=True),
        "recipe": list_recipes(enabled_only=True),
        "technique": list_techniques(enabled_only=True),
    }
    kind_order = {kind: index for index, kind in enumerate(["material", "artifact", "pill", "talisman", "recipe", "technique"])}
    for kind, rows in sources.items():
        for item in rows:
            invalid_reason = _gambling_reward_invalid_reason(kind, item)
            if invalid_reason:
                continue
            quality_level = max(_item_quality_level(kind, item), 1)
            quality = get_quality_meta(quality_level)
            quantity_min, quantity_max = _reward_pool_quantity_range(kind, quality_level)
            catalog.append(
                {
                    "item_kind": kind,
                    "item_kind_label": ITEM_KIND_LABELS.get(kind, kind),
                    "item_ref_id": int(item.get("id") or 0),
                    "item_name": str(item.get("name") or "").strip(),
                    "quality_level": int(quality["level"]),
                    "quality_label": str(quality["label"]),
                    "quality_color": str(quality["color"]),
                    "quantity_min": quantity_min,
                    "quantity_max": quantity_max,
                    "base_weight": _reward_pool_default_weight(kind, quality_level, "gambling"),
                    "gambling_weight": _reward_pool_default_weight(kind, quality_level, "gambling"),
                    "fishing_weight": _reward_pool_default_weight(kind, quality_level, "fishing"),
                    "enabled": True,
                    "gambling_enabled": True,
                    "fishing_enabled": True,
                    "invalid_reason": "",
                }
            )
    catalog.sort(
        key=lambda item: (
            kind_order.get(str(item.get("item_kind") or "").strip(), 99),
            int(item.get("quality_level") or 0),
            str(item.get("item_name") or ""),
            int(item.get("item_ref_id") or 0),
        )
    )
    return catalog


def _merge_catalog_gambling_reward_pool(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = _dynamic_gambling_reward_catalog()
    if not catalog:
        return entries
    saved_map = {
        (str(entry.get("item_kind") or "").strip(), int(entry.get("item_ref_id") or 0)): entry
        for entry in entries
        if int(entry.get("item_ref_id") or 0) > 0 and not str(entry.get("invalid_reason") or "").strip()
    }
    merged: list[dict[str, Any]] = []
    for row in catalog:
        current = saved_map.get((str(row.get("item_kind") or "").strip(), int(row.get("item_ref_id") or 0)), {})
        quantity_min = max(int(current.get("quantity_min") or row.get("quantity_min") or 1), 1)
        quantity_max = max(int(current.get("quantity_max") or row.get("quantity_max") or quantity_min), quantity_min)
        if str(row.get("item_kind") or "").strip() in {"recipe", "technique"}:
            quantity_min = 1
            quantity_max = 1
        gambling_weight = max(float(current.get("gambling_weight", current.get("base_weight", row.get("gambling_weight") or 0.0)) or 0.0), 0.0)
        fishing_weight = max(float(current.get("fishing_weight", current.get("base_weight", row.get("fishing_weight") or 0.0)) or 0.0), 0.0)
        merged.append(
            {
                **row,
                "quantity_min": quantity_min,
                "quantity_max": quantity_max,
                "base_weight": gambling_weight,
                "gambling_weight": gambling_weight,
                "fishing_weight": fishing_weight,
                "enabled": bool(current.get("enabled", row.get("enabled", True))),
                "gambling_enabled": bool(current.get("gambling_enabled", current.get("enabled", row.get("gambling_enabled", True)))),
                "fishing_enabled": bool(current.get("fishing_enabled", current.get("enabled", row.get("fishing_enabled", True)))),
            }
        )
    return merged


def _resolve_gambling_reward_item(
    item_kind: str,
    *,
    item_ref_id: int | None = None,
    item_name: str | None = None,
) -> dict[str, Any] | None:
    kind = str(item_kind or "").strip()
    ref_id = int(item_ref_id or 0) or None
    target_name = str(item_name or "").strip()
    if kind not in GAMBLING_SUPPORTED_ITEM_KINDS:
        return None

    rows = {
        "artifact": list_artifacts(enabled_only=True),
        "pill": list_pills(enabled_only=True),
        "talisman": list_talismans(enabled_only=True),
        "material": list_materials(enabled_only=True),
        "recipe": list_recipes(enabled_only=True),
        "technique": list_techniques(enabled_only=True),
    }.get(kind, [])
    row = None
    if ref_id:
        row = next((item for item in rows if int(item.get("id") or 0) == ref_id), None)
    if row is None and target_name:
        row = next((item for item in rows if str(item.get("name") or "").strip() == target_name), None)
    if row is None:
        return None
    quality_level = _item_quality_level(kind, row)
    quality = get_quality_meta(quality_level)
    return {
        "item_kind": kind,
        "item_kind_label": ITEM_KIND_LABELS.get(kind, kind),
        "item_ref_id": int(row.get("id") or 0),
        "item_name": str(row.get("name") or "").strip(),
        "quality_level": int(quality["level"]),
        "quality_label": str(quality["label"]),
        "quality_color": str(quality["color"]),
        "item": row,
    }


def _default_gambling_quality_weight_rules() -> dict[str, dict[str, float]]:
    defaults = DEFAULT_SETTINGS.get("gambling_quality_weight_rules") or {}
    result: dict[str, dict[str, float]] = {}
    for quality_label, payload in defaults.items():
        result[str(quality_label)] = {
            "weight_multiplier": max(float((payload or {}).get("weight_multiplier", 1.0) or 0.0), 0.0),
        }
    return result


def _normalize_gambling_quality_weight_rules(raw: Any) -> dict[str, dict[str, float]]:
    defaults = _default_gambling_quality_weight_rules()
    rows = raw if isinstance(raw, dict) else {}
    result: dict[str, dict[str, float]] = {}
    for quality_label in defaults:
        payload = rows.get(quality_label) if isinstance(rows.get(quality_label), dict) else {}
        result[quality_label] = {
            "weight_multiplier": max(
                float(payload.get("weight_multiplier", defaults[quality_label]["weight_multiplier"]) or 0.0),
                0.0,
            ),
        }
    return result


def _default_fishing_quality_weight_rules() -> dict[str, dict[str, float]]:
    defaults = DEFAULT_SETTINGS.get("fishing_quality_weight_rules") or {}
    result: dict[str, dict[str, float]] = {}
    for quality_label, payload in defaults.items():
        result[str(quality_label)] = {
            "weight_multiplier": max(float((payload or {}).get("weight_multiplier", 1.0) or 0.0), 0.0),
        }
    return result


def _normalize_fishing_quality_weight_rules(raw: Any) -> dict[str, dict[str, float]]:
    defaults = _default_fishing_quality_weight_rules()
    rows = raw if isinstance(raw, dict) else {}
    result: dict[str, dict[str, float]] = {}
    for quality_label in defaults:
        payload = rows.get(quality_label) if isinstance(rows.get(quality_label), dict) else {}
        result[quality_label] = {
            "weight_multiplier": max(
                float(payload.get("weight_multiplier", defaults[quality_label]["weight_multiplier"]) or 0.0),
                0.0,
            ),
        }
    return result


def _normalize_gambling_reward_pool(raw: Any) -> list[dict[str, Any]]:
    entries = raw if isinstance(raw, list) else []
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        payload = entry if isinstance(entry, dict) else {}
        item_kind = str(payload.get("item_kind") or "").strip()
        item_name = str(payload.get("item_name") or "").strip() or None
        item_ref_id = _coerce_int(payload.get("item_ref_id"), 0) or None
        resolved = _resolve_gambling_reward_item(item_kind, item_ref_id=item_ref_id, item_name=item_name)
        invalid_reason = ""
        if item_kind not in GAMBLING_SUPPORTED_ITEM_KINDS:
            invalid_reason = "不支持的物品类型"
        elif resolved is None:
            invalid_reason = "未找到对应物品"
        else:
            invalid_reason = _gambling_reward_invalid_reason(item_kind, (resolved or {}).get("item"))
        if invalid_reason:
            resolved = None

        quality_level = int((resolved or {}).get("quality_level") or get_quality_meta(payload.get("quality_level")).get("level") or 1)
        quality = get_quality_meta(quality_level)
        quantity_min = max(_coerce_int(payload.get("quantity_min"), 1, 1), 1)
        quantity_max = max(_coerce_int(payload.get("quantity_max"), quantity_min, quantity_min), quantity_min)
        if item_kind in {"recipe", "technique"}:
            quantity_min = 1
            quantity_max = 1
        legacy_weight = max(float(payload.get("base_weight", 1.0) or 0.0), 0.0)
        legacy_enabled = bool(payload.get("enabled", True))
        gambling_weight = max(float(payload.get("gambling_weight", legacy_weight) or 0.0), 0.0)
        fishing_weight = max(float(payload.get("fishing_weight", legacy_weight) or 0.0), 0.0)
        gambling_enabled = bool(payload.get("gambling_enabled", legacy_enabled))
        fishing_enabled = bool(payload.get("fishing_enabled", legacy_enabled))
        normalized.append(
            {
                "item_kind": item_kind if item_kind in GAMBLING_SUPPORTED_ITEM_KINDS else "material",
                "item_kind_label": ITEM_KIND_LABELS.get(item_kind, item_kind or "材料"),
                "item_ref_id": int((resolved or {}).get("item_ref_id") or 0) or None,
                "item_name": str((resolved or {}).get("item_name") or item_name or "").strip() or None,
                "quality_level": int(quality["level"]),
                "quality_label": str(quality["label"]),
                "quality_color": str(quality["color"]),
                "quantity_min": quantity_min,
                "quantity_max": quantity_max,
                "base_weight": gambling_weight,
                "enabled": gambling_enabled and not invalid_reason,
                "gambling_weight": gambling_weight,
                "fishing_weight": fishing_weight,
                "gambling_enabled": gambling_enabled and not invalid_reason,
                "fishing_enabled": fishing_enabled and not invalid_reason,
                "invalid_reason": invalid_reason,
            }
        )
    return normalized


def _configured_gambling_pool(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current = settings or get_xiuxian_settings()
    from bot.plugins.xiuxian_game.cache import CATALOG_TTL, load_multi_versioned_json

    return load_multi_versioned_json(
        version_part_groups=(
            ("settings",),
            ("catalog", "artifacts"),
            ("catalog", "materials"),
            ("catalog", "pills"),
            ("catalog", "recipes"),
            ("catalog", "talismans"),
            ("catalog", "techniques"),
        ),
        cache_parts=("gambling", "reward-pool"),
        ttl=CATALOG_TTL,
        loader=lambda: _merge_catalog_gambling_reward_pool(_normalize_gambling_reward_pool(current.get("gambling_reward_pool"))),
    )


def _reward_pool_entry_enabled(entry: dict[str, Any], channel: str) -> bool:
    key = f"{channel}_enabled"
    return bool(entry.get(key, entry.get("enabled", True)))


def _reward_pool_entry_weight(entry: dict[str, Any], channel: str) -> float:
    if channel == "gambling":
        return max(float(entry.get("gambling_weight", entry.get("base_weight") or 0.0) or 0.0), 0.0)
    return max(float(entry.get("fishing_weight", entry.get("base_weight") or 0.0) or 0.0), 0.0)


def _gambling_entry_effective_weight(entry: dict[str, Any], fortune_value: int | float, settings: dict[str, Any]) -> float:
    if not _reward_pool_entry_enabled(entry, "gambling"):
        return 0.0
    quality_label = str(entry.get("quality_label") or get_quality_meta(entry.get("quality_level")).get("label") or "凡品")
    quality_level = int(entry.get("quality_level") or get_quality_meta(quality_label).get("level") or 1)
    quality_rules = _normalize_gambling_quality_weight_rules(settings.get("gambling_quality_weight_rules"))
    base_weight = _reward_pool_entry_weight(entry, "gambling")
    quality_multiplier = max(float((quality_rules.get(quality_label) or {}).get("weight_multiplier", 1.0) or 0.0), 0.0)
    if base_weight <= 0 or quality_multiplier <= 0:
        return 0.0
    fortune_gap = max(float(fortune_value or 0.0) - float(FORTUNE_BASELINE), 0.0)
    fortune_divisor = max(int(settings.get("gambling_fortune_divisor", DEFAULT_SETTINGS["gambling_fortune_divisor"]) or 1), 1)
    bonus_percent = max(
        int(
            settings.get(
                "gambling_fortune_bonus_per_quality_percent",
                DEFAULT_SETTINGS["gambling_fortune_bonus_per_quality_percent"],
            )
            or 0
        ),
        0,
    )
    rare_steps = max(quality_level - 1, 0)
    scaled_fortune = 1.0 - exp(-fortune_gap / max(float(fortune_divisor) * 7.5, 1.0))
    fortune_multiplier = 1.0 + max(rare_steps * (bonus_percent / 100.0) * 2.35 * scaled_fortune, 0.0)
    return base_weight * quality_multiplier * fortune_multiplier


def _gambling_empty_chance(fortune_value: int | float) -> float:
    fortune_gap = max(float(fortune_value or 0.0) - float(FORTUNE_BASELINE), 0.0)
    reduction = 0.17 * (1.0 - exp(-fortune_gap / 80.0))
    return max(min(0.32 - reduction, 0.42), 0.1)


def _recipe_fragment_source_labels(
    recipe_id: int,
    source_catalog: dict[tuple[str, int], list[str]] | None = None,
) -> list[str]:
    resolved_recipe_id = int(recipe_id or 0)
    if resolved_recipe_id <= 0:
        return []
    catalog = source_catalog or get_item_source_catalog()
    labels: list[str] = []
    for ingredient in list_recipe_ingredients(resolved_recipe_id):
        material = ingredient.get("material") or {}
        material_id = int(material.get("id") or ingredient.get("material_id") or 0)
        material_name = str(material.get("name") or "").strip()
        if material_id <= 0 or "残页" not in material_name:
            continue
        for label in catalog.get(("material", material_id), []):
            normalized_label = str(label or "").strip()
            if not normalized_label or normalized_label == "仙界奇石" or normalized_label in labels:
                continue
            labels.append(normalized_label)
    return labels


def _gambling_fortune_hint(fortune_value: int | float, settings: dict[str, Any]) -> str:
    fortune_gap = max(float(fortune_value or 0.0) - float(FORTUNE_BASELINE), 0.0)
    if fortune_gap <= 0:
        return "当前机缘未触发额外稀有加成。"
    divisor = max(int(settings.get("gambling_fortune_divisor", DEFAULT_SETTINGS["gambling_fortune_divisor"]) or 1), 1)
    bonus_percent = max(
        int(
            settings.get(
                "gambling_fortune_bonus_per_quality_percent",
                DEFAULT_SETTINGS["gambling_fortune_bonus_per_quality_percent"],
            )
            or 0
        ),
        0,
    )
    scaled_fortune = 1.0 - exp(-fortune_gap / max(float(divisor) * 7.5, 1.0))
    top_bonus = 6 * bonus_percent * 2.35 * scaled_fortune
    empty_reduction = (0.32 - _gambling_empty_chance(fortune_value)) * 100
    return f"当前机缘最多可为高品阶奖励额外提供约 {round(top_bonus, 1)}% 权重加成，并降低约 {round(empty_reduction, 1)}% 轮空率。"


def _grant_gambling_reward_in_session(
    session: Session,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
) -> dict[str, Any]:
    def _get_or_create_inventory_row(model_cls, ref_field: str, **defaults: Any):
        for pending in session.new:
            if not isinstance(pending, model_cls):
                continue
            if int(getattr(pending, "tg", 0) or 0) != int(tg):
                continue
            if int(getattr(pending, ref_field, 0) or 0) != int(item_ref_id):
                continue
            return pending
        row = (
            session.query(model_cls)
            .filter(model_cls.tg == int(tg), getattr(model_cls, ref_field) == int(item_ref_id))
            .with_for_update()
            .first()
        )
        if row is not None:
            return row
        row = model_cls(tg=int(tg), **{ref_field: int(item_ref_id)}, **defaults)
        session.add(row)
        return row

    amount = max(int(quantity or 0), 1)
    if item_kind == "artifact":
        artifact, _, granted_quantity = _grant_artifact_inventory_in_session(
            session,
            int(tg),
            int(item_ref_id),
            amount,
            reject_if_owned=True,
            strict_quantity=False,
        )
        return {"artifact": serialize_artifact(artifact), "quantity": granted_quantity}
    if item_kind == "pill":
        row = _get_or_create_inventory_row(
            XiuxianPillInventory,
            "pill_id",
            quantity=0,
        )
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        return {"pill": serialize_pill(get_pill(int(item_ref_id))), "quantity": amount}
    if item_kind == "talisman":
        row = _get_or_create_inventory_row(
            XiuxianTalismanInventory,
            "talisman_id",
            quantity=0,
            bound_quantity=0,
        )
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        return {"talisman": serialize_talisman(get_talisman(int(item_ref_id))), "quantity": amount}
    if item_kind == "material":
        row = _get_or_create_inventory_row(
            XiuxianMaterialInventory,
            "material_id",
            quantity=0,
        )
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        return {"material": serialize_material(get_material(int(item_ref_id))), "quantity": amount}
    raise ValueError("当前奖池仅支持实物奖励在事务内发放。")


def _grant_gambling_reward_after_commit(
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    if item_kind == "recipe":
        return grant_recipe_to_user(int(tg), int(item_ref_id), source="gambling", obtained_note="仙界奇石所得")
    if item_kind == "technique":
        return grant_technique_to_user(
            int(tg),
            int(item_ref_id),
            source="gambling",
            obtained_note="仙界奇石所得",
            auto_equip_if_empty=True,
        )
    return grant_item_to_user(int(tg), item_kind, int(item_ref_id), amount)


def _format_gambling_reward_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary_map: dict[tuple[str, int], dict[str, Any]] = {}
    for row in results:
        reward_payload = row.get("reward") if isinstance(row.get("reward"), dict) else {}
        duplicate_converted = bool(reward_payload.get("duplicate_converted"))
        key_kind = f"{row.get('item_kind')}:converted" if duplicate_converted else str(row.get("item_kind") or "")
        key = (key_kind, int(row.get("item_ref_id") or 0))
        current = summary_map.get(key)
        if current is None:
            current = {
                "item_kind": row.get("item_kind"),
                "item_kind_label": row.get("item_kind_label"),
                "item_ref_id": row.get("item_ref_id"),
                "item_name": row.get("item_name"),
                "quality_level": row.get("quality_level"),
                "quality_label": row.get("quality_label"),
                "quality_color": row.get("quality_color"),
                "quantity": 0,
                "stone_compensation": 0,
                "duplicate_converted": duplicate_converted,
                "broadcasted": False,
            }
            summary_map[key] = current
        current["quantity"] = int(current.get("quantity") or 0) + int(row.get("quantity") or 0)
        current["stone_compensation"] = int(current.get("stone_compensation") or 0) + int(reward_payload.get("stone_compensation") or 0)
        current["broadcasted"] = bool(current.get("broadcasted")) or bool(row.get("broadcasted"))
    summary = list(summary_map.values())
    summary.sort(
        key=lambda item: (
            -int(item.get("quality_level") or 0),
            -int(item.get("quantity") or 0),
            str(item.get("item_name") or ""),
        )
    )
    return summary


def convert_emby_coin_to_stone(tg: int, amount: int) -> dict[str, Any]:
    ensure_not_in_retreat(tg)
    return convert_coin_to_stone(tg, amount)


def convert_stone_to_emby_coin(tg: int, amount: int) -> dict[str, Any]:
    ensure_not_in_retreat(tg)
    return convert_stone_to_coin(tg, amount)


def list_public_shop_items() -> dict[str, Any]:
    settings = get_xiuxian_settings()
    return {
        "official_shop_name": settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"]),
        "coin_stone_exchange_enabled": bool(
            settings.get("coin_stone_exchange_enabled", DEFAULT_SETTINGS.get("coin_stone_exchange_enabled", True))
        ),
        "official_items": list_shop_items(official_only=True),
    }


def search_xiuxian_players(
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_secluded: bool = True,
) -> dict[str, Any]:
    return search_profiles(query=query, page=page, page_size=page_size, include_secluded=include_secluded)


def admin_clear_all_xiuxian_data() -> dict[str, Any]:
    return clear_all_xiuxian_user_data()


def admin_patch_player(tg: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    root_fields = {"root_type", "root_primary", "root_secondary", "root_relation", "root_bonus", "root_quality"}
    if root_fields.intersection(patch):
        profile = serialize_profile(get_profile(tg, create=False))
        if profile is None or not profile.get("consented"):
            return None

        merged = {**profile, **patch}
        for key in ("root_type", "root_primary", "root_secondary", "root_relation", "root_quality"):
            if key in merged:
                merged[key] = str(merged.get(key) or "").strip() or None

        root_type = merged.get("root_type")
        if root_type != "双灵根":
            patch["root_secondary"] = None
            merged["root_secondary"] = None
        if root_type in {"单灵根", "地灵根"}:
            patch["root_relation"] = "平稳中正"
            merged["root_relation"] = "平稳中正"
        elif root_type == "天灵根":
            patch["root_relation"] = "天道垂青"
            merged["root_relation"] = "天道垂青"
        elif root_type == "变异灵根":
            patch["root_relation"] = "异灵独秀"
            merged["root_relation"] = "异灵独秀"

        has_root = any(merged.get(key) for key in ("root_type", "root_primary", "root_secondary", "root_quality"))
        if has_root:
            quality_name = _normalized_root_quality(merged)
            quality = _root_quality_payload(quality_name)
            patch["root_quality"] = quality_name
            patch["root_quality_level"] = int(quality["level"])
            patch["root_quality_color"] = quality["color"]
        else:
            patch["root_quality"] = None
            patch["root_quality_level"] = 1
            patch["root_quality_color"] = None
    result = admin_patch_profile(tg, **patch)
    if result is None:
        return None
    return _apply_profile_growth_floor(tg, explicit_fields=set(patch.keys()))


def build_admin_player_detail(tg: int) -> dict[str, Any] | None:
    profile = get_profile(tg, create=False)
    if profile is None or not profile.consented:
        return None
    bundle = serialize_full_profile(tg)
    bundle["materials"] = list_user_materials(tg)
    bundle["recipes"] = list_user_recipes(tg, enabled_only=False)
    return bundle


def admin_grant_player_resource(
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int = 1,
    equip: bool = False,
) -> dict[str, Any]:
    profile = get_profile(tg, create=False)
    if profile is None or not profile.consented:
        raise ValueError("玩家不存在")
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "title":
        grant_title_to_user(
            tg,
            int(item_ref_id),
            source="admin",
            obtained_note="后台发放",
            equip=equip,
            auto_equip_if_empty=equip,
        )
    elif normalized_kind == "technique":
        grant_technique_to_user(
            tg,
            int(item_ref_id),
            source="admin",
            obtained_note="后台发放",
            auto_equip_if_empty=equip,
        )
        if equip:
            set_current_technique(tg, int(item_ref_id))
    else:
        grant_item_to_user(tg, normalized_kind, int(item_ref_id), max(int(quantity or 1), 1))
    return build_admin_player_detail(tg) or {}


def admin_set_player_inventory(
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    bound_quantity: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(tg, create=False)
    if profile is None or not profile.consented:
        raise ValueError("玩家不存在")
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "artifact":
        admin_set_user_artifact_inventory(tg, int(item_ref_id), int(quantity), bound_quantity)
    elif normalized_kind == "pill":
        admin_set_user_pill_inventory(tg, int(item_ref_id), int(quantity))
    elif normalized_kind == "talisman":
        admin_set_user_talisman_inventory(tg, int(item_ref_id), int(quantity), bound_quantity)
    elif normalized_kind == "material":
        admin_set_user_material_inventory(tg, int(item_ref_id), int(quantity))
    else:
        raise ValueError("不支持的背包类型")
    return build_admin_player_detail(tg) or {}


def admin_revoke_player_resource(tg: int, item_kind: str, item_ref_id: int) -> dict[str, Any]:
    profile = get_profile(tg, create=False)
    if profile is None or not profile.consented:
        raise ValueError("玩家不存在")
    normalized_kind = str(item_kind or "").strip()
    removed = False
    if normalized_kind == "title":
        removed = revoke_title_from_user(tg, int(item_ref_id))
    elif normalized_kind == "technique":
        removed = revoke_technique_from_user(tg, int(item_ref_id))
    elif normalized_kind == "recipe":
        removed = revoke_recipe_from_user(tg, int(item_ref_id))
    else:
        raise ValueError("不支持的移除类型")
    if not removed:
        raise ValueError("玩家未持有该条目")
    return build_admin_player_detail(tg) or {}


def _admin_remove_inventory_item_if_present(tg: int, item_kind: str, item_ref_id: int, quantity: int) -> bool:
    normalized_kind = str(item_kind or "").strip()
    amount = max(int(quantity or 0), 1)
    if normalized_kind == "artifact":
        with Session() as session:
            row = (
                session.query(XiuxianArtifactInventory)
                .filter(
                    XiuxianArtifactInventory.tg == int(tg),
                    XiuxianArtifactInventory.artifact_id == int(item_ref_id),
                )
                .with_for_update()
                .first()
            )
            if row is None or int(row.quantity or 0) <= 0:
                return False
            removable = min(int(row.quantity or 0), amount)
            bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
            row.quantity = max(int(row.quantity or 0) - removable, 0)
            row.bound_quantity = min(bound_quantity, row.quantity)
            row.updated_at = utcnow()
            if row.quantity <= 0:
                session.delete(row)
            session.commit()
        return True
    if normalized_kind == "pill":
        with Session() as session:
            row = (
                session.query(XiuxianPillInventory)
                .filter(
                    XiuxianPillInventory.tg == int(tg),
                    XiuxianPillInventory.pill_id == int(item_ref_id),
                )
                .with_for_update()
                .first()
            )
            if row is None or int(row.quantity or 0) <= 0:
                return False
            removable = min(int(row.quantity or 0), amount)
            row.quantity = max(int(row.quantity or 0) - removable, 0)
            row.updated_at = utcnow()
            if row.quantity <= 0:
                session.delete(row)
            session.commit()
        return True
    if normalized_kind == "talisman":
        with Session() as session:
            row = (
                session.query(XiuxianTalismanInventory)
                .filter(
                    XiuxianTalismanInventory.tg == int(tg),
                    XiuxianTalismanInventory.talisman_id == int(item_ref_id),
                )
                .with_for_update()
                .first()
            )
            if row is None or int(row.quantity or 0) <= 0:
                return False
            removable = min(int(row.quantity or 0), amount)
            bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
            row.quantity = max(int(row.quantity or 0) - removable, 0)
            row.bound_quantity = min(bound_quantity, row.quantity)
            row.updated_at = utcnow()
            if row.quantity <= 0:
                session.delete(row)
            session.commit()
        return True
    if normalized_kind == "material":
        with Session() as session:
            row = (
                session.query(XiuxianMaterialInventory)
                .filter(
                    XiuxianMaterialInventory.tg == int(tg),
                    XiuxianMaterialInventory.material_id == int(item_ref_id),
                )
                .with_for_update()
                .first()
            )
            if row is None or int(row.quantity or 0) <= 0:
                return False
            removable = min(int(row.quantity or 0), amount)
            row.quantity = max(int(row.quantity or 0) - removable, 0)
            row.updated_at = utcnow()
            if row.quantity <= 0:
                session.delete(row)
            session.commit()
        return True
    return False


def admin_batch_update_player_resource(
    item_kind: str,
    item_ref_id: int,
    quantity: int = 1,
    *,
    operation: str = "grant",
    equip: bool = False,
) -> dict[str, Any]:
    normalized_kind = str(item_kind or "").strip()
    normalized_operation = str(operation or "").strip().lower()
    amount = max(int(quantity or 0), 1)
    if normalized_operation not in {"grant", "deduct"}:
        raise ValueError("批量操作类型不支持")

    processed = 0
    succeeded = 0
    skipped = 0
    failed = 0
    skipped_tgs: list[int] = []
    failed_rows: list[dict[str, Any]] = []

    for profile in list_profiles():
        tg = int(getattr(profile, "tg", 0) or 0)
        if tg <= 0:
            continue
        processed += 1
        try:
            if normalized_operation == "grant":
                admin_grant_player_resource(tg, normalized_kind, int(item_ref_id), quantity=amount, equip=equip)
                create_journal(
                    tg,
                    "admin",
                    "主人批量发放",
                    f"主人批量发放了 {normalized_kind}:{int(item_ref_id)} x{amount}",
                )
                succeeded += 1
                continue

            if normalized_kind in {"title", "technique", "recipe"}:
                removed = False
                if normalized_kind == "title":
                    removed = revoke_title_from_user(tg, int(item_ref_id))
                elif normalized_kind == "technique":
                    removed = revoke_technique_from_user(tg, int(item_ref_id))
                elif normalized_kind == "recipe":
                    removed = revoke_recipe_from_user(tg, int(item_ref_id))
                if not removed:
                    skipped += 1
                    skipped_tgs.append(tg)
                    continue
            else:
                removed = _admin_remove_inventory_item_if_present(tg, normalized_kind, int(item_ref_id), amount)
                if not removed:
                    skipped += 1
                    skipped_tgs.append(tg)
                    continue

            create_journal(
                tg,
                "admin",
                "主人批量扣除",
                f"主人批量扣除了 {normalized_kind}:{int(item_ref_id)} x{amount}",
            )
            succeeded += 1
        except Exception as exc:
            failed += 1
            failed_rows.append({"tg": tg, "reason": str(exc) or "未知错误"})

    return {
        "operation": normalized_operation,
        "item_kind": normalized_kind,
        "item_ref_id": int(item_ref_id),
        "quantity": amount,
        "processed_count": processed,
        "success_count": succeeded,
        "skipped_count": skipped,
        "failed_count": failed,
        "skipped_tgs": skipped_tgs[:50],
        "failed_rows": failed_rows[:20],
    }


def admin_set_player_selection(tg: int, selection_kind: str, item_ref_id: int | None = None) -> dict[str, Any]:
    profile = get_profile(tg, create=False)
    if profile is None or not profile.consented:
        raise ValueError("玩家不存在")
    normalized_kind = str(selection_kind or "").strip()
    target_id = None if item_ref_id in {None, 0} else int(item_ref_id)
    if normalized_kind == "title":
        set_current_title(tg, target_id)
    elif normalized_kind == "technique":
        owned_technique_ids = {
            int((item.get("technique") or {}).get("id") or item.get("technique_id") or 0)
            for item in list_user_techniques(tg, enabled_only=False)
        }
        if target_id is not None and target_id not in owned_technique_ids:
            raise ValueError("玩家未持有该功法")
        set_current_technique(tg, target_id)
    elif normalized_kind == "talisman":
        if target_id is not None and target_id not in {
            int((row.get("talisman") or {}).get("id") or 0)
            for row in list_user_talismans(tg)
        }:
            raise ValueError("玩家未持有该符箓")
        set_active_talisman(tg, target_id)
    elif normalized_kind == "artifact":
        if target_id is None:
            raise ValueError("法宝选择不能为空")
        if target_id not in {
            int((row.get("artifact") or {}).get("id") or 0)
            for row in list_user_artifacts(tg)
        }:
            raise ValueError("玩家背包里没有这件法宝")
        equip_limit = max(int(get_xiuxian_settings().get("artifact_equip_limit", DEFAULT_SETTINGS["artifact_equip_limit"]) or 0), 1)
        set_equipped_artifact(tg, target_id, equip_limit)
    else:
        raise ValueError("不支持的当前配置类型")
    return build_admin_player_detail(tg) or {}


def _battle_bundle(bundle_or_profile: dict[str, Any], opponent_profile: dict[str, Any] | None = None, apply_random: bool = False) -> dict[str, Any]:
    if "profile" in bundle_or_profile:
        bundle = bundle_or_profile
        profile = dict(bundle["profile"])
        artifacts = bundle.get("equipped_artifacts") or []
        talisman = bundle.get("active_talisman")
        technique = bundle.get("current_technique")
    else:
        profile = dict(bundle_or_profile)
        artifacts = collect_equipped_artifacts(int(profile["tg"]))
        active_talisman_id = profile.get("active_talisman_id")
        talisman = serialize_talisman(get_talisman(int(active_talisman_id))) if active_talisman_id else None
        current_technique_id = profile.get("current_technique_id")
        technique = serialize_technique(get_technique(int(current_technique_id))) if current_technique_id else None
    title = None
    if "profile" in bundle_or_profile:
        title = bundle.get("current_title")
    elif profile.get("current_title_id"):
        title = get_current_title(int(profile["tg"]))

    quality_name = _normalized_root_quality(profile)
    quality = _root_quality_payload(quality_name)
    sect_effects = get_sect_effects(profile)
    artifact_effects = merge_artifact_effects(profile, artifacts, opponent_profile)
    talisman_effects = resolve_talisman_effects(profile, talisman, opponent_profile) if talisman else None
    talisman_active_effects = resolve_talisman_active_effects(profile, talisman) if talisman else {}
    technique_effects = resolve_technique_effects(profile, technique, opponent_profile) if technique else None
    title_effects = resolve_title_effects(profile, title, opponent_profile) if title else None
    stats = _effective_stats(profile, artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)

    stage_index = max(realm_index(profile.get("realm_stage")), 0)
    layer, progress_ratio, _ = _profile_layer_progress(profile)
    realm_score = 560 + stage_index * 1750 + (layer + progress_ratio) * 200
    attribute_score = (
        stats["bone"] * 5.2
        + stats["comprehension"] * 5.8
        + stats["divine_sense"] * 5.9
        + stats["fortune"] * 2.4
        + stats["willpower"] * 4.6
        + stats["charisma"] * 1.5
        + stats["karma"] * 3.0
    )
    combat_score = (
        stats["attack_power"] * 19.5
        + stats["defense_power"] * 17.5
        + stats["body_movement"] * 12.5
        + stats["qi_blood"] * 0.40
        + stats["true_yuan"] * 0.32
    )
    root_factor = _resolved_root_combat_factor(profile, quality, opponent_profile)
    duel_rate_factor = 1 + max(min(stats["duel_rate_bonus"], 40), -40) / 120
    random_factor = random.uniform(0.98, 1.04) if apply_random else 1.0
    power = (realm_score + (attribute_score + combat_score) * root_factor) * max(duel_rate_factor, 0.75) * random_factor
    return {
        "profile": profile,
        "quality": quality_name,
        "quality_payload": quality,
        "root_factor": float(root_factor),
        "realm_score": float(realm_score),
        "stats": stats,
        "artifact_effects": artifact_effects,
        "talisman_effects": talisman_effects or {},
        "talisman_active_effects": talisman_active_effects,
        "sect_effects": sect_effects,
        "technique_effects": technique_effects or {},
        "title_effects": title_effects or {},
        "power": float(power),
    }


def _self_profile_snapshot(bundle: dict[str, Any]) -> dict[str, Any]:
    profile = bundle.get("profile") or {}
    current_title = bundle.get("current_title")
    return {
        "profile": dict(profile) if isinstance(profile, dict) else {},
        "current_title": dict(current_title) if isinstance(current_title, dict) else None,
        "combat_power": int(bundle.get("combat_power") or 0),
    }


def serialize_full_profile(tg: int) -> dict[str, Any]:
    bundle = _legacy_serialize_full_profile(tg)
    profile = bundle.get("profile") or {}
    has_root = bool(str(profile.get("root_type") or "").strip() or str(profile.get("root_quality") or "").strip())
    if has_root:
        quality_name = _normalized_root_quality(profile)
        quality = _root_quality_payload(quality_name)
        profile["root_quality"] = quality_name
        profile["root_quality_level"] = profile.get("root_quality_level") or quality["level"]
        profile["root_quality_color"] = profile.get("root_quality_color") or quality["color"]
    else:
        profile["root_quality"] = None
        profile["root_quality_level"] = None
        profile["root_quality_color"] = None
    profile["root_text"] = format_root(profile)
    battle = _battle_bundle(bundle)
    bundle["effective_stats"] = {
        key: int(round(value)) if isinstance(value, (int, float)) else value
        for key, value in battle["stats"].items()
    }
    bundle["combat_power"] = int(round(battle["power"]))
    self_snapshot = _self_profile_snapshot(bundle)
    bundle["commissions"] = build_spirit_stone_commissions(tg)
    bundle["mentorship"] = build_mentorship_overview(tg, bundle=self_snapshot)
    bundle["marriage"] = build_marriage_overview(tg, bundle=self_snapshot)
    bundle["capabilities"]["shared_inventory_enabled"] = bool((bundle.get("marriage") or {}).get("shared_assets_enabled"))
    bundle["capabilities"]["shared_inventory_note"] = str((bundle.get("marriage") or {}).get("shared_assets_hint") or "")
    for entry in bundle.get("attribute_effects") or []:
        key = str(entry.get("key") or "")
        if key in bundle["effective_stats"]:
            entry["effective_value"] = int(bundle["effective_stats"].get(key) or 0)
    return bundle


def generate_root_payload() -> dict[str, Any]:
    quality_name = _roll_root_quality()
    quality = _root_quality_payload(quality_name)
    if quality_name == "天灵根":
        primary = random.choice(FIVE_ELEMENTS)
        return {
            "root_type": "天灵根",
            "root_primary": primary,
            "root_secondary": None,
            "root_relation": "天道垂青",
            "root_bonus": 12,
            "root_quality": quality_name,
            "root_quality_level": quality["level"],
            "root_quality_color": quality["color"],
        }
    if quality_name == "变异灵根":
        primary = random.choice(ROOT_VARIANT_ELEMENTS)
        return {
            "root_type": "变异灵根",
            "root_primary": primary,
            "root_secondary": None,
            "root_relation": "异灵独秀",
            "root_bonus": 10,
            "root_quality": quality_name,
            "root_quality_level": quality["level"],
            "root_quality_color": quality["color"],
        }
    if random.randint(1, 100) <= 10:
        primary, secondary = random.sample(FIVE_ELEMENTS, 2)
        relation, bonus = determine_relation(primary, secondary)
        return {
            "root_type": "双灵根",
            "root_primary": primary,
            "root_secondary": secondary,
            "root_relation": relation,
            "root_bonus": bonus,
            "root_quality": quality_name,
            "root_quality_level": quality["level"],
            "root_quality_color": quality["color"],
        }
    primary = random.choice(FIVE_ELEMENTS)
    return {
        "root_type": "单灵根",
        "root_primary": primary,
        "root_secondary": None,
        "root_relation": "平稳中正",
        "root_bonus": 0,
        "root_quality": quality_name,
        "root_quality_level": quality["level"],
        "root_quality_color": quality["color"],
    }


def _refined_root_payload(profile: dict[str, Any], steps: int) -> dict[str, Any] | None:
    quality_name = _normalized_root_quality(profile)
    if quality_name in ROOT_SPECIAL_QUALITIES:
        return None
    current_quality = quality_name if quality_name in ROOT_COMMON_QUALITY_ORDER else "中品灵根"
    current_index = ROOT_COMMON_QUALITY_ORDER.index(current_quality)
    target_index = min(current_index + max(int(steps or 0), 0), len(ROOT_COMMON_QUALITY_ORDER) - 1)
    if target_index <= current_index:
        return None
    target_quality = ROOT_COMMON_QUALITY_ORDER[target_index]
    quality = _root_quality_payload(target_quality)
    return {
        "root_type": profile.get("root_type"),
        "root_primary": profile.get("root_primary"),
        "root_secondary": profile.get("root_secondary"),
        "root_relation": profile.get("root_relation"),
        "root_bonus": int(profile.get("root_bonus") or 0),
        "root_quality": target_quality,
        "root_quality_level": int(quality["level"]),
        "root_quality_color": quality["color"],
    }


def _generate_root_payload_with_floor(floor_level: int) -> dict[str, Any]:
    minimum = max(min(int(floor_level or 0), ROOT_QUALITY_LEVELS["极品灵根"]), 0)
    best = generate_root_payload()
    best_level = int(best.get("root_quality_level") or 0)
    if minimum <= 0 or best_level >= minimum:
        return best
    for _ in range(31):
        candidate = generate_root_payload()
        candidate_level = int(candidate.get("root_quality_level") or 0)
        if candidate_level >= minimum:
            return candidate
        if candidate_level > best_level:
            best = candidate
            best_level = candidate_level
    return best


def _common_root_quality_name(level: int) -> str:
    clamped_level = max(1, min(int(level or 1), ROOT_QUALITY_LEVELS["极品灵根"]))
    return ROOT_COMMON_QUALITY_ORDER[clamped_level - 1]


def _current_common_root_level(profile: dict[str, Any]) -> int:
    current_quality = _normalized_root_quality(profile)
    if current_quality in ROOT_SPECIAL_QUALITIES:
        return ROOT_QUALITY_LEVELS["极品灵根"]
    return max(1, min(ROOT_QUALITY_LEVELS.get(current_quality, 1), ROOT_QUALITY_LEVELS["极品灵根"]))


def _build_single_root_payload(profile: dict[str, Any], floor_level: int) -> dict[str, Any]:
    quality_level = max(
        _current_common_root_level(profile),
        max(min(int(floor_level or 0), ROOT_QUALITY_LEVELS["极品灵根"]), 0),
        ROOT_QUALITY_LEVELS["中品灵根"],
    )
    quality_name = _common_root_quality_name(quality_level)
    quality = _root_quality_payload(quality_name)
    return {
        "root_type": "单灵根",
        "root_primary": random.choice(FIVE_ELEMENTS),
        "root_secondary": None,
        "root_relation": "平稳中正",
        "root_bonus": 0,
        "root_quality": quality_name,
        "root_quality_level": int(quality["level"]),
        "root_quality_color": quality["color"],
    }


def _build_double_root_payload(profile: dict[str, Any], floor_level: int) -> dict[str, Any]:
    primary, secondary = random.sample(FIVE_ELEMENTS, 2)
    relation, bonus = determine_relation(primary, secondary)
    baseline = ROOT_QUALITY_LEVELS["中品灵根"] if relation == "相克" else ROOT_QUALITY_LEVELS["上品灵根"]
    quality_level = max(
        _current_common_root_level(profile),
        max(min(int(floor_level or 0), ROOT_QUALITY_LEVELS["极品灵根"]), 0),
        baseline,
    )
    quality_name = _common_root_quality_name(quality_level)
    quality = _root_quality_payload(quality_name)
    return {
        "root_type": "双灵根",
        "root_primary": primary,
        "root_secondary": secondary,
        "root_relation": relation,
        "root_bonus": bonus,
        "root_quality": quality_name,
        "root_quality_level": int(quality["level"]),
        "root_quality_color": quality["color"],
    }


def _build_earth_root_payload() -> dict[str, Any]:
    quality = _root_quality_payload("极品灵根")
    return {
        "root_type": "地灵根",
        "root_primary": random.choice(FIVE_ELEMENTS),
        "root_secondary": None,
        "root_relation": "平稳中正",
        "root_bonus": ROOT_SPECIAL_BONUS["地灵根"],
        "root_quality": "极品灵根",
        "root_quality_level": int(quality["level"]),
        "root_quality_color": quality["color"],
    }


def _build_heaven_root_payload() -> dict[str, Any]:
    primary = random.choice(FIVE_ELEMENTS)
    quality = _root_quality_payload("天灵根")
    return {
        "root_type": "天灵根",
        "root_primary": primary,
        "root_secondary": None,
        "root_relation": "天道垂青",
        "root_bonus": 12,
        "root_quality": "天灵根",
        "root_quality_level": int(quality["level"]),
        "root_quality_color": quality["color"],
    }


def _build_variant_root_payload() -> dict[str, Any]:
    primary = random.choice(ROOT_VARIANT_ELEMENTS)
    quality = _root_quality_payload("变异灵根")
    return {
        "root_type": "变异灵根",
        "root_primary": primary,
        "root_secondary": None,
        "root_relation": "异灵独秀",
        "root_bonus": 10,
        "root_quality": "变异灵根",
        "root_quality_level": int(quality["level"]),
        "root_quality_color": quality["color"],
    }


def _transformed_root_payload(profile: dict[str, Any], pill_type: str, effect_value: float | int | None = None) -> dict[str, Any] | None:
    floor_level = max(int(round(float(effect_value or 0))), 0)
    if pill_type == "root_single":
        return _build_single_root_payload(profile, floor_level)
    if pill_type == "root_double":
        return _build_double_root_payload(profile, floor_level)
    if pill_type == "root_earth":
        return _build_earth_root_payload()
    if pill_type == "root_heaven":
        return _build_heaven_root_payload()
    if pill_type == "root_variant":
        return _build_variant_root_payload()
    return None


def format_root(payload: dict[str, Any]) -> str:
    root_type = str(payload.get("root_type") or "").strip()
    if not root_type:
        return "尚未踏入仙途"

    quality = _normalized_root_quality(payload)
    primary = str(payload.get("root_primary") or "")
    secondary = str(payload.get("root_secondary") or "")
    relation = str(payload.get("root_relation") or "")
    if root_type in {"天灵根", "变异灵根"}:
        return f"{quality} · {primary}"
    if root_type == "双灵根":
        return f"{quality} · {primary}/{secondary} · {relation}"
    return f"{quality} · {primary}"


def init_path_for_user(tg: int) -> dict[str, Any]:
    ensure_seed_data()
    profile = get_profile(tg, create=True)
    if profile and profile.consented and profile.death_at is None:
        return serialize_full_profile(tg)

    is_rebirth = bool(profile and profile.death_at is not None)
    if is_rebirth:
        rebirth_cooldown = _rebirth_cooldown_state(profile)
        if rebirth_cooldown["blocked"]:
            raise ValueError(rebirth_cooldown["reason"])
    if is_rebirth:
        with Session() as session:
            session.query(XiuxianExploration).filter(
                XiuxianExploration.tg == int(tg),
                XiuxianExploration.claimed.is_(False),
            ).delete(synchronize_session=False)
            session.query(XiuxianTaskClaim).filter(
                XiuxianTaskClaim.tg == int(tg),
            ).delete(synchronize_session=False)
            _end_marriage_for_user(session, tg)
            session.commit()

    root_payload = generate_root_payload()
    stats = _build_opening_stats(root_payload)
    updated = upsert_profile(
        tg,
        consented=True,
        root_type=root_payload["root_type"],
        root_primary=root_payload["root_primary"],
        root_secondary=root_payload["root_secondary"],
        root_relation=root_payload["root_relation"],
        root_bonus=root_payload["root_bonus"],
        root_quality=root_payload["root_quality"],
        root_quality_level=root_payload["root_quality_level"],
        root_quality_color=root_payload["root_quality_color"],
        realm_stage=FIRST_REALM_STAGE,
        realm_layer=1,
        cultivation=0,
        spiritual_stone=50,
        gender=None,
        dan_poison=0,
        master_tg=None,
        servitude_started_at=None,
        servitude_challenge_available_at=None,
        furnace_harvested_at=None,
        death_at=None,
        sect_id=None,
        sect_role_key=None,
        sect_contribution=0,
        sect_joined_at=None,
        sect_betrayal_until=None,
        current_artifact_id=None,
        active_talisman_id=None,
        current_technique_id=None,
        current_title_id=None,
        retreat_started_at=None,
        retreat_end_at=None,
        retreat_gain_per_minute=0,
        retreat_cost_per_minute=0,
        retreat_minutes_total=0,
        retreat_minutes_resolved=0,
        last_train_at=None,
        last_salary_claim_at=None,
        robbery_daily_count=0,
        robbery_day_key=None,
        explore_daily_count=0,
        explore_day_key=None,
        fish_daily_count=0,
        fish_day_key=None,
        encounter_daily_count=0,
        encounter_day_key=None,
        shop_name="",
        shop_broadcast=False,
        rebirth_count=int(profile.rebirth_count or 0) + (1 if is_rebirth else 0),
        **stats,
    )
    _grant_entry_starter_assets(tg)
    return serialize_full_profile(tg)


def practice_for_user(tg: int) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "吐纳修炼")
    if _is_retreating(profile):
        raise ValueError("闭关之中，心神内敛，无暇吐纳外气。")
    if is_same_china_day(profile.last_train_at, utcnow()):
        raise ValueError("今日吐纳已毕，经脉已盈，再行运气恐伤道基。")

    profile_data = serialize_profile(profile)
    equipped_artifacts = collect_equipped_artifacts(tg)
    artifact_effects = merge_artifact_effects(profile_data, equipped_artifacts)
    active_talisman = serialize_talisman(get_talisman(profile.active_talisman_id)) if profile.active_talisman_id else None
    talisman_effects = resolve_talisman_effects(profile_data, active_talisman) if active_talisman else None
    talisman_active_effects = resolve_talisman_active_effects(profile_data, active_talisman) if active_talisman else {}
    current_technique = _current_technique_payload(profile_data)
    technique_effects = resolve_technique_effects(profile_data, current_technique) if current_technique else None
    current_title = get_current_title(tg)
    title_effects = resolve_title_effects(profile_data, current_title) if current_title else None
    sect_effects = get_sect_effects(profile_data)
    stats = _effective_stats(profile_data, artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)
    quality = _root_quality_payload(_normalized_root_quality(profile_data))
    stage = normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE)
    stage_rule = _realm_stage_rule(stage)
    poison_penalty = max(float(profile.dan_poison or 0) - stats["bone"] * 0.45, 0.0) / 110
    base_gain = random.randint(int(stage_rule["practice_gain_min"]), int(stage_rule["practice_gain_max"]))
    gain = int(
        round(
            (
                base_gain
                + stats["bone"] * 0.55
                + stats["comprehension"] * 0.75
                + stats["cultivation_bonus"]
                + float(talisman_active_effects.get("cultivation_bonus") or 0)
            )
            * quality["cultivation_rate"]
            * max(0.55, 1 - poison_penalty)
            * DAILY_PRACTICE_CULTIVATION_FACTOR
        )
    )
    gain = max(gain, max(int(round(stage_rule["practice_gain_min"] * 0.55 * DAILY_PRACTICE_CULTIVATION_FACTOR)), 6))
    raw_gain = gain
    stone_gain = max(
        int(
            round(
                (
                    random.randint(int(stage_rule["practice_stone_min"]), int(stage_rule["practice_stone_max"]))
                    + int(stats["fortune"] // 8)
                    + int(stats["charisma"] // 10)
                )
                * DAILY_PRACTICE_STONE_FACTOR
                * (1 + max(float(talisman_active_effects.get("practice_stone_bonus") or 0), 0.0) / 100.0)
            )
        ),
        1,
    )
    activity_growth = {"triggered": False, "changes": [], "patch": {}, "chance": 0, "roll": None}
    cultivation_meta = {
        "base_gain": raw_gain,
        "effective_gain": raw_gain,
        "efficiency_percent": 100,
        "reduced": False,
    }
    curse_event = None
    layer = int(profile.realm_layer or 1)
    cultivation = int(profile.cultivation or 0)
    upgraded_layers: list[int] = []
    remaining = 0
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if updated is None or not updated.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        if _is_retreating(updated):
            raise ValueError("闭关之中，心神内敛，无暇吐纳外气。")
        now = utcnow()
        # 再次在行锁内校验，避免双击或并发请求绕过“每日一次”的限制。
        if is_same_china_day(updated.last_train_at, now):
            raise ValueError("今日吐纳已毕，经脉已盈，再行运气恐伤道基。")
        gain, cultivation_meta = adjust_cultivation_gain_for_social_mode(updated, raw_gain)
        layer, cultivation, upgraded_layers, remaining = apply_cultivation_gain(
            normalize_realm_stage(updated.realm_stage or FIRST_REALM_STAGE),
            int(updated.realm_layer or 1),
            int(updated.cultivation or 0),
            gain,
        )
        apply_spiritual_stone_delta(session, tg, stone_gain, action_text="获取吐纳灵石", allow_dead=False, apply_tribute=True)
        updated.cultivation = cultivation
        updated.realm_layer = layer
        updated.last_train_at = now
        activity_growth = _apply_activity_stat_growth_to_profile_row(updated, "practice", stats)
        curse_event = _apply_artifact_curse_backlash(
            tg,
            "practice",
            equipped_artifacts=equipped_artifacts,
            session=session,
            profile_row=updated,
        )
        updated.updated_at = now
        session.commit()
    if active_talisman and any(float(value or 0) > 0 for value in talisman_active_effects.values()):
        set_active_talisman(tg, None)
    _record_artifact_curse_event(tg, curse_event)
    _apply_profile_growth_floor(tg)
    return {
        "gain": gain,
        "gain_raw": raw_gain,
        "cultivation_efficiency_percent": int(cultivation_meta.get("efficiency_percent") or 100),
        "stone_gain": stone_gain,
        "attribute_growth": activity_growth.get("changes") or [],
        "curse_event": curse_event,
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "profile": serialize_full_profile(tg),
    }


def breakthrough_for_user(tg: int, use_pill: bool = False) -> dict[str, Any]:
    profile = _require_alive_profile_obj(tg, "突破境界")
    if _is_retreating(profile):
        raise ValueError("闭关之中，气机未满，尚难叩问破境之机。")
    if int(profile.realm_layer or 0) < 9:
        raise ValueError("只有达到当前大境界九层后才能尝试突破。")

    stage = normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE)
    required_cultivation = cultivation_threshold(stage, 9)
    if int(profile.cultivation or 0) < required_cultivation:
        raise ValueError(f"当前修为尚未圆满，还差 {required_cultivation - int(profile.cultivation or 0)} 点修为。")
    next_stage = next_realm_stage(stage)
    if next_stage is None:
        raise ValueError("你已经走到当前修炼体系的尽头。")
    requirement = _breakthrough_requirement(stage)
    required_pill_name = str((requirement or {}).get("pill_name") or "").strip()
    if required_pill_name and not use_pill:
        raise ValueError(f"突破至 {next_stage} 需要先服用对应破境丹【{required_pill_name}】。")

    profile_data = serialize_profile(profile)
    artifact_effects = merge_artifact_effects(profile_data, collect_equipped_artifacts(tg))
    active_talisman = serialize_talisman(get_talisman(profile.active_talisman_id)) if profile.active_talisman_id else None
    talisman_effects = resolve_talisman_effects(profile_data, active_talisman) if active_talisman else None
    current_technique = _current_technique_payload(profile_data)
    technique_effects = resolve_technique_effects(profile_data, current_technique) if current_technique else None
    current_title = get_current_title(tg)
    title_effects = resolve_title_effects(profile_data, current_title) if current_title else None
    sect_effects = get_sect_effects(profile_data)
    stats = _effective_stats(profile_data, artifact_effects, talisman_effects, sect_effects, technique_effects, title_effects)
    quality = _root_quality_payload(_normalized_root_quality(profile_data))
    success_rate = BREAKTHROUGH_BASE_RATE.get(stage, 12)
    success_rate += int(round((stats["bone"] - 12) * 0.45))
    success_rate += int(round((stats["comprehension"] - 12) * 0.6))
    success_rate += int(quality["breakthrough_bonus"])
    success_rate += int(round((artifact_effects or {}).get("breakthrough_bonus", 0)))
    success_rate += int(round((technique_effects or {}).get("breakthrough_bonus", 0)))
    success_rate += int(round((title_effects or {}).get("breakthrough_bonus", 0)))
    success_rate += int(round((stats["willpower"] - 10) * 0.35))
    success_rate += int(round((stats["karma"] - 10) * 0.2))
    success_rate -= int(max(float(profile.dan_poison or 0) - stats["bone"] * 0.3, 0) // 8)
    if _normalized_root_quality(profile_data) == "天灵根":
        success_rate += 4

    pill_bonus = 0
    used_pill_name = None
    pill_row = None
    if use_pill and required_pill_name:
        pill_row = _find_pill_in_inventory_by_name(tg, required_pill_name)
        if pill_row is None:
            raise ValueError(f"你还未备好对应的破境丹【{required_pill_name}】。")
        used_pill_name = pill_row["pill"]["name"]
        pill_effects = resolve_pill_effects(profile_data, pill_row["pill"], {"base_success_rate": success_rate})
        base_bonus = max(int((requirement or {}).get("success_floor") or 0) - success_rate, 12)
        pill_bonus = max(int(round(pill_effects.get("success_rate_bonus", 0))), base_bonus)
        success_rate += pill_bonus

    success_rate = max(min(success_rate, 95), 1)
    success_roll = roll_probability_percent(
        success_rate,
        actor_fortune=stats["fortune"],
        actor_weight=0.45,
        minimum=1,
        maximum=95,
    )
    success_rate = success_roll["chance"]
    roll = success_roll["roll"]
    success = bool(success_roll["success"])
    if use_pill and used_pill_name:
        if pill_row is None or not consume_user_pill(tg, pill_row["pill"]["id"], 1):
            raise ValueError("破境丹消耗失败，请稍后再试。")

    if success:
        breakthrough_patch = _major_breakthrough_reward_patch(profile, next_stage)
        breakthrough_patch = _stabilize_breakthrough_patch(
            profile_data,
            next_stage,
            breakthrough_patch,
            artifact_effects,
            talisman_effects,
            sect_effects,
            technique_effects,
            title_effects,
        )
        updated = upsert_profile(
            tg,
            realm_stage=next_stage,
            realm_layer=1,
            cultivation=0,
            breakthrough_pill_uses=int(profile.breakthrough_pill_uses or 0) + (1 if use_pill else 0),
            **breakthrough_patch,
        )
        _apply_profile_growth_floor(tg)
    else:
        updated = upsert_profile(
            tg,
            cultivation=max(int(profile.cultivation or 0) - required_cultivation // 2, 0),
            breakthrough_pill_uses=int(profile.breakthrough_pill_uses or 0) + (1 if use_pill else 0),
            willpower=int(profile.willpower or 0) + 1,
        )
    return {
        "success": success,
        "roll": roll,
        "success_rate": success_rate,
        "pill_bonus": pill_bonus,
        "used_pill": used_pill_name,
        "profile": serialize_full_profile(tg),
    }


def _apply_pill_effect_once(
    session: Session,
    tg: int,
    profile: XiuxianProfile,
    pill: Any,
    pill_data: dict[str, Any],
) -> dict[str, Any]:
    profile_data = serialize_profile(profile) or {}
    usage_reason = _pill_usage_reason(profile_data, pill_data)
    if usage_reason:
        raise ValueError(usage_reason)
    effects = resolve_pill_effects(profile_data, pill_data)
    sect_effects = get_sect_effects(profile_data)
    poison_cap = 100 + int(sect_effects.get("pill_poison_cap_bonus", 0))
    poison_resist = float(sect_effects.get("pill_poison_resist", 0.0))
    bone_resistance = min((float(profile.bone or 0) / 200), 0.45)
    realm_bonus_resistance = min(realm_index(profile.realm_stage or FIRST_REALM_STAGE) * 0.02, 0.20)
    total_resistance = min(bone_resistance + realm_bonus_resistance, 0.55)
    raw_poison_delta = float(effects.get("poison_delta", 0) or 0)
    effective_poison = raw_poison_delta * (1 - total_resistance) * (1 - poison_resist)
    dan_poison = min(int(profile.dan_poison or 0) + int(round(effective_poison)), poison_cap)
    # 每个大境界的属性上限，防止丹药无限堆叠
    _max_base = {0: 300, 1: 600, 2: 1200, 3: 2500, 4: 5000, 5: 10000, 6: 20000, 7: 40000, 8: 80000}
    stat_cap = _max_base.get(realm_index(profile.realm_stage or FIRST_REALM_STAGE), 100000)
    combat_cap = stat_cap * 3
    cultivation = int(profile.cultivation or 0)
    bone = min(int(profile.bone or 0) + int(round(effects.get("bone_bonus", 0))), stat_cap)
    comprehension = min(int(profile.comprehension or 0) + int(round(effects.get("comprehension_bonus", 0))), stat_cap)
    divine_sense = min(int(profile.divine_sense or 0) + int(round(effects.get("divine_sense_bonus", 0))), stat_cap)
    fortune_cap = stat_cap
    if pill.pill_type == "fortune":
        fortune_cap = min(fortune_cap, _fortune_pill_cap_for_profile(profile))
    fortune = min(int(profile.fortune or 0) + int(round(effects.get("fortune_bonus", 0))), fortune_cap)
    willpower = min(int(profile.willpower or 0) + int(round(effects.get("willpower_bonus", 0))), stat_cap)
    charisma = min(int(profile.charisma or 0) + int(round(effects.get("charisma_bonus", 0))), stat_cap)
    karma = min(int(profile.karma or 0) + int(round(effects.get("karma_bonus", 0))), stat_cap)
    qi_blood = min(int(profile.qi_blood or 0) + int(round(effects.get("qi_blood_bonus", 0))), combat_cap)
    true_yuan = min(int(profile.true_yuan or 0) + int(round(effects.get("true_yuan_bonus", 0))), combat_cap)
    body_movement = min(int(profile.body_movement or 0) + int(round(effects.get("body_movement_bonus", 0))), combat_cap)
    attack_power = min(int(profile.attack_power or 0) + int(round(effects.get("attack_bonus", 0))), combat_cap)
    defense_power = min(int(profile.defense_power or 0) + int(round(effects.get("defense_bonus", 0))), combat_cap)
    root_patch: dict[str, Any] | None = None

    if pill.pill_type == "clear_poison":
        dan_poison = max(dan_poison - int(round(effects.get("clear_poison", effects.get("effect_value", 50)))), 0)
    elif pill.pill_type == "cultivation":
        cultivation += int(round(effects.get("cultivation_gain", effects.get("effect_value", 0))))
    elif pill.pill_type == "root_refine":
        steps = max(int(round(float(effects.get("root_quality_gain", 0) or 0))), 0)
        root_patch = _refined_root_payload(profile_data, steps)
    elif pill.pill_type == "root_remold":
        floor_level = max(int(round(float(effects.get("root_quality_floor", 0) or 0))), 0)
        root_patch = _generate_root_payload_with_floor(floor_level)
    elif pill.pill_type in ROOT_TRANSFORM_PILL_TYPES:
        root_patch = _transformed_root_payload(profile_data, pill.pill_type, effects.get("effect_value", pill_data.get("effect_value", 0)))

    layer, cultivation, _, _ = apply_cultivation_gain(
        normalize_realm_stage(profile.realm_stage or FIRST_REALM_STAGE),
        int(profile.realm_layer or 1),
        cultivation,
        0,
    )
    profile.dan_poison = dan_poison
    profile.cultivation = cultivation
    profile.bone = bone
    profile.comprehension = comprehension
    profile.divine_sense = divine_sense
    profile.fortune = fortune
    profile.willpower = willpower
    profile.charisma = charisma
    profile.karma = karma
    profile.qi_blood = qi_blood
    profile.true_yuan = true_yuan
    profile.body_movement = body_movement
    profile.attack_power = attack_power
    profile.defense_power = defense_power
    profile.realm_layer = layer
    for key, value in (root_patch or {}).items():
        setattr(profile, key, value)
    return effects


def consume_pill_for_user(tg: int, pill_id: int, quantity: int = 1) -> dict[str, Any]:
    pill = get_pill(pill_id)
    if pill is None or not pill.enabled:
        raise ValueError("丹囊空空，未觅得可服之丹。")
    pill_data = serialize_pill(pill)
    profile_data: dict[str, Any] = {}
    profile_after: dict[str, Any] = {}
    effects: dict[str, Any] = {}
    requested_quantity = max(int(quantity or 0), 1)
    batch_usable = _pill_supports_batch_use(pill_data)
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        assert_profile_alive(profile, "服用丹药")
        _assert_gender_ready(profile, "服用丹药")

        profile_data = serialize_profile(profile) or {}
        usage_reason = _pill_usage_reason(profile_data, pill_data)
        if usage_reason:
            raise ValueError(usage_reason)

        rows = _ordered_owner_rows(session, XiuxianPillInventory, tg, "pill_id", pill_id)
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        if total_quantity < 1:
            raise ValueError("你的背包里没有这枚丹药。")
        if requested_quantity > 1 and not batch_usable:
            raise ValueError("这枚丹药当前仅支持单次服用。")
        effective_quantity = requested_quantity
        if pill.pill_type == "fortune":
            effective_quantity = min(requested_quantity, _fortune_pill_remaining_uses(profile_data, pill_data, total_quantity))
            if effective_quantity <= 0:
                raise ValueError(_fortune_pill_usage_reason(profile_data, pill_data) or "机缘已达当前境界丹药可提升上限。")
        if total_quantity < effective_quantity:
            raise ValueError("背包里的丹药数量不足。")

        now = utcnow()
        remaining = effective_quantity
        for row in rows:
            if remaining <= 0:
                break
            available = max(int(row.quantity or 0), 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.quantity = available - delta
            row.updated_at = now
            remaining -= delta
            if row.quantity <= 0:
                session.delete(row)

        for _ in range(effective_quantity):
            effects = _apply_pill_effect_once(session, tg, profile, pill, pill_data)
        profile.updated_at = now
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        profile_after = serialize_profile(profile) or {}
        session.commit()
    return {
        "pill": {
            **pill_data,
            "resolved_effects": effects,
            "batch_usable": batch_usable,
            "batch_use_note": _pill_batch_use_note(pill_data),
        },
        "profile": profile_after,
        "summary": _pill_effect_summary(profile_data, profile_after),
        "used_quantity": effective_quantity,
        "batch_used": effective_quantity > 1,
    }


def _duel_display_name(profile: dict[str, Any]) -> str:
    return _profile_name_with_title(profile)


def _duel_md_escape(value: Any) -> str:
    return re.sub(r"([_*\[`])", r"\\\1", str(value or ""))


def _duel_item_names(items: list[dict[str, Any]] | None, fallback: str) -> str:
    rows = [str(item.get("name") or "").strip() for item in (items or []) if str(item.get("name") or "").strip()]
    return "、".join(rows[:3]) if rows else fallback


def _duel_source_token(source_type: str, payload: dict[str, Any]) -> str:
    source_id = int(payload.get("id") or 0)
    source_name = str(payload.get("name") or source_type).strip()
    return f"{source_type}:{source_id}:{source_name}"


def _build_duel_source_uses(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    talisman = bundle.get("active_talisman") or {}
    if not talisman:
        return {}
    limit = max(int(talisman.get("effect_uses") or 1), 1)
    token = _duel_source_token("符箓", talisman)
    return {
        token: {
            "source_type": "符箓",
            "source_name": str(talisman.get("name") or "符箓"),
            "limit": limit,
            "remaining": limit,
        }
    }


def _duel_combat_entries(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows = {"skills": [], "passives": [], "openings": []}
    sources: list[tuple[str, dict[str, Any]]] = []
    if bundle.get("current_technique"):
        sources.append(("功法", bundle["current_technique"]))
    if bundle.get("active_talisman"):
        sources.append(("符箓", bundle["active_talisman"]))
    for artifact in bundle.get("equipped_artifacts") or []:
        sources.append(("法宝", artifact))
    for source_type, payload in sources:
        config = payload.get("combat_config") or {}
        if not isinstance(config, dict):
            continue
        source_token = _duel_source_token(source_type, payload)
        opening_text = str(config.get("opening_text") or "").strip()
        if opening_text:
            rows["openings"].append(f"{payload.get('name') or source_type}：{opening_text}")
        for key in ("skills", "passives"):
            for item in config.get(key) or []:
                if not isinstance(item, dict) or not str(item.get("kind") or "").strip():
                    continue
                rows[key].append(
                    {
                        **item,
                        "source_type": source_type,
                        "source_name": str(payload.get("name") or source_type),
                        "source_token": source_token,
                        "display_name": str(item.get("name") or item.get("kind") or source_type),
                    }
                )
    return rows


def _create_duel_actor(bundle: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    profile = bundle["profile"]
    stats = state["stats"]
    return {
        "tg": int(profile["tg"]),
        "name": _duel_display_name(profile),
        "profile": profile,
        "stats": stats,
        "power": float(state["power"]),
        "max_hp": max(int(round(stats["qi_blood"])), 1),
        "hp": max(int(round(stats["qi_blood"])), 1),
        "max_mp": max(int(round(stats["true_yuan"])), 1),
        "mp": max(int(round(stats["true_yuan"])), 1),
        "active_talisman": bundle.get("active_talisman") or None,
        "combat_entries": _duel_combat_entries(bundle),
        "source_uses": _build_duel_source_uses(bundle),
        "effects": {
            "burn": [],
            "bleed": [],
            "shield": [],
            "guard": [],
            "dodge": [],
            "armor_break": [],
        },
    }


def _append_duel_log(logs: list[dict[str, Any]], round_no: int, text: str, kind: str = "action") -> None:
    logs.append({"round": round_no, "kind": kind, "text": text})


def _duel_actor_effect_rows(actor: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for effect in actor["effects"].get("burn", []):
        rows.append(f"灼烧-{int(effect.get('damage') or 0)}/{int(effect.get('remaining') or 0)}轮")
    for effect in actor["effects"].get("bleed", []):
        rows.append(f"流血-{int(effect.get('damage') or 0)}/{int(effect.get('remaining') or 0)}轮")
    for effect in actor["effects"].get("shield", []):
        rows.append(f"护盾{int(effect.get('pool') or 0)}/{int(effect.get('remaining') or 0)}轮")
    for effect in actor["effects"].get("guard", []):
        rows.append(f"格挡{int(round(float(effect.get('ratio') or 0) * 100))}%/{int(effect.get('remaining') or 0)}轮")
    for effect in actor["effects"].get("dodge", []):
        rows.append(f"闪避+{int(effect.get('bonus') or 0)}/{int(effect.get('remaining') or 0)}轮")
    for effect in actor["effects"].get("armor_break", []):
        rows.append(f"破甲{int(round(float(effect.get('ratio') or 0) * 100))}%/{int(effect.get('remaining') or 0)}轮")
    return rows


def _duel_actor_status_payload(actor: dict[str, Any]) -> dict[str, Any]:
    effect_rows = _duel_actor_effect_rows(actor)
    return {
        "hp": int(actor.get("hp") or 0),
        "max_hp": int(actor.get("max_hp") or 0),
        "mp": int(actor.get("mp") or 0),
        "max_mp": int(actor.get("max_mp") or 0),
        "effects_text": "、".join(effect_rows) if effect_rows else "无",
    }


def _append_duel_state_log(
    logs: list[dict[str, Any]],
    round_no: int,
    challenger_actor: dict[str, Any],
    defender_actor: dict[str, Any],
    *,
    text: str | None = None,
) -> None:
    challenger_status = _duel_actor_status_payload(challenger_actor)
    defender_status = _duel_actor_status_payload(defender_actor)
    logs.append(
        {
            "round": round_no,
            "kind": "state",
            "text": text
            or (
                f"状态回读：{challenger_actor['name']} 气血 {challenger_status['hp']}/{challenger_status['max_hp']}、真元 {challenger_status['mp']}/{challenger_status['max_mp']}、状态 {challenger_status['effects_text']}；"
                f"{defender_actor['name']} 气血 {defender_status['hp']}/{defender_status['max_hp']}、真元 {defender_status['mp']}/{defender_status['max_mp']}、状态 {defender_status['effects_text']}。"
            ),
            "challenger_status": challenger_status,
            "defender_status": defender_status,
        }
    )


def _active_effect_value(actor: dict[str, Any], effect_kind: str, value_key: str) -> float:
    total = 0.0
    for item in actor["effects"].get(effect_kind, []):
        total += float(item.get(value_key) or 0)
    return total


def _duel_entry_remaining_uses(actor: dict[str, Any], entry: dict[str, Any]) -> int | None:
    token = str(entry.get("source_token") or "").strip()
    if not token:
        return None
    usage = actor.get("source_uses", {}).get(token)
    if not usage:
        return None
    return max(int(usage.get("remaining") or 0), 0)


def _consume_duel_entry_use(
    actor: dict[str, Any],
    entry: dict[str, Any],
    round_no: int,
    logs: list[dict[str, Any]],
) -> bool:
    token = str(entry.get("source_token") or "").strip()
    if not token:
        return True
    usage = actor.get("source_uses", {}).get(token)
    if not usage:
        return True
    remaining = max(int(usage.get("remaining") or 0), 0)
    if remaining <= 0:
        return False
    usage["remaining"] = remaining - 1
    if usage["remaining"] <= 0:
        _append_duel_log(
            logs,
            round_no,
            f"{actor['name']} 所祭出的{usage.get('source_name') or '符箓'}灵意已尽，本场无法再继续显化。",
            "state",
        )
    return True


def _consume_shield(actor: dict[str, Any], damage: int) -> int:
    remaining = max(int(damage), 0)
    absorbed = 0
    updated = []
    for effect in actor["effects"]["shield"]:
        pool = max(int(effect.get("pool") or 0), 0)
        if remaining > 0 and pool > 0:
            current_absorb = min(pool, remaining)
            pool -= current_absorb
            remaining -= current_absorb
            absorbed += current_absorb
        if pool > 0:
            effect["pool"] = pool
            updated.append(effect)
    actor["effects"]["shield"] = updated
    return absorbed


def _tick_duel_dot(actor: dict[str, Any], effect_kind: str, round_no: int, logs: list[dict[str, Any]]) -> None:
    survivors = []
    for effect in actor["effects"].get(effect_kind, []):
        damage = max(int(effect.get("damage") or 0), 1)
        actor["hp"] = max(actor["hp"] - damage, 0)
        if effect_kind == "burn":
            _append_duel_log(logs, round_no, f"{actor['name']} 被{effect.get('name') or '灼烧'}反复炙烤，气血 -{damage}。", "dot")
        else:
            _append_duel_log(logs, round_no, f"{actor['name']} 伤口被{effect.get('name') or '流血'}牵动，气血 -{damage}。", "dot")
        effect["remaining"] = max(int(effect.get("remaining") or 1) - 1, 0)
        if effect["remaining"] > 0:
            survivors.append(effect)
    actor["effects"][effect_kind] = survivors


def _decay_duel_effects(actor: dict[str, Any]) -> None:
    for effect_kind in ("guard", "dodge", "armor_break", "shield"):
        next_rows = []
        for effect in actor["effects"].get(effect_kind, []):
            effect["remaining"] = max(int(effect.get("remaining") or 1) - 1, 0)
            if effect_kind == "shield":
                if effect["remaining"] > 0 and int(effect.get("pool") or 0) > 0:
                    next_rows.append(effect)
            elif effect["remaining"] > 0:
                next_rows.append(effect)
        actor["effects"][effect_kind] = next_rows


def _apply_duel_effect(
    source: dict[str, Any],
    target: dict[str, Any],
    effect: dict[str, Any],
    round_no: int,
    logs: list[dict[str, Any]],
) -> None:
    kind = str(effect.get("kind") or "").strip()
    name = effect.get("display_name") or effect.get("name") or kind
    duration = max(int(effect.get("duration") or 1), 1)
    flat_damage = max(int(effect.get("flat_damage") or 0), 0)
    flat_heal = max(int(effect.get("flat_heal") or 0), 0)
    ratio_percent = int(effect.get("ratio_percent") or 0)
    text = str(effect.get("text") or "").strip()
    if kind == "burn":
        damage = max(flat_damage + int(source["stats"]["attack_power"] * max(ratio_percent, 0) / 100), 6)
        target["effects"]["burn"].append({"name": name, "damage": damage, "remaining": duration})
        _append_duel_log(logs, round_no, text or f"{source['name']} 让 {target['name']} 身上残留离火，后续将持续受创。")
    elif kind == "bleed":
        damage = max(flat_damage + int(source["stats"]["attack_power"] * max(ratio_percent, 0) / 100), 5)
        target["effects"]["bleed"].append({"name": name, "damage": damage, "remaining": duration})
        _append_duel_log(logs, round_no, text or f"{target['name']} 被撕开伤口，气血开始一点点外泄。")
    elif kind == "shield":
        pool = max(flat_damage + flat_heal + max(int(effect.get("flat_shield") or 0), 0) + int(source["stats"]["defense_power"] * max(ratio_percent, 0) / 100), 1)
        source["effects"]["shield"].append({"name": name, "pool": pool, "remaining": duration})
        _append_duel_log(logs, round_no, text or f"{source['name']} 身前升起一层护体灵罩，可抵消 {pool} 点伤害。")
    elif kind == "guard":
        ratio = max(float(effect.get("defense_ratio_percent") or ratio_percent or 0) / 100.0, 0.0)
        source["effects"]["guard"].append({"name": name, "ratio": ratio, "remaining": duration})
        _append_duel_log(logs, round_no, text or f"{source['name']} 沉气护体，接下来承伤将被削弱。")
    elif kind == "dodge":
        bonus = max(int(effect.get("dodge_bonus") or 0), 0)
        source["effects"]["dodge"].append({"name": name, "bonus": bonus, "remaining": duration})
        _append_duel_log(logs, round_no, text or f"{source['name']} 身法一提，短时间内更难被锁定。")
    elif kind == "armor_break":
        ratio = max(float(effect.get("defense_ratio_percent") or ratio_percent or 0) / 100.0, 0.0)
        target["effects"]["armor_break"].append({"name": name, "ratio": ratio, "remaining": duration})
        _append_duel_log(logs, round_no, text or f"{target['name']} 的护体灵气被撕开一角，防御出现破绽。")
    elif kind == "heal":
        heal_value = max(flat_heal + int(source["stats"]["true_yuan"] * max(ratio_percent, 0) / 100), 1)
        source["hp"] = min(source["max_hp"], source["hp"] + heal_value)
        _append_duel_log(logs, round_no, text or f"{source['name']} 调匀气息，气血回升 {heal_value}。")


def _choose_duel_skill(actor: dict[str, Any], round_no: int, logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    skills = list(actor["combat_entries"].get("skills") or [])
    random.shuffle(skills)
    for skill in skills:
        cost_true_yuan = max(int(skill.get("cost_true_yuan") or 0), 0)
        if actor["mp"] < cost_true_yuan:
            continue
        remaining_uses = _duel_entry_remaining_uses(actor, skill)
        if remaining_uses is not None and remaining_uses <= 0:
            continue
        chance = max(min(int(skill.get("chance") or 0), 100), 0)
        if chance <= 0:
            continue
        if not roll_probability_percent(chance)["success"]:
            continue
        if not _consume_duel_entry_use(actor, skill, round_no, logs):
            continue
        actor["mp"] = max(actor["mp"] - cost_true_yuan, 0)
        return skill
    return None


def _execute_duel_turn(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    round_no: int,
    logs: list[dict[str, Any]],
) -> None:
    if attacker["hp"] <= 0 or defender["hp"] <= 0:
        return
    skill = _choose_duel_skill(attacker, round_no, logs)
    move_name = skill.get("display_name") if skill else "寻常一击"
    hit_bonus = int(skill.get("hit_bonus") or 0) if skill else 0
    dodge_bonus = _active_effect_value(defender, "dodge", "bonus")
    dodge_chance = max(min(int(8 + (defender["stats"]["body_movement"] - attacker["stats"]["body_movement"]) * 0.45 + dodge_bonus - hit_bonus), 40), 5)
    if roll_probability_percent(dodge_chance)["success"]:
        _append_duel_log(
            logs,
            round_no,
            f"{attacker['name']} 施展 {move_name}，却被 {defender['name']} 凭身法错开，攻势落空。",
            "dodge",
        )
        return

    defense_break_ratio = min(_active_effect_value(defender, "armor_break", "ratio"), 0.45)
    effective_defense = max(defender["stats"]["defense_power"] * (1 - defense_break_ratio), 1)
    base_damage = attacker["stats"]["attack_power"] * random.uniform(0.88, 1.18)
    if skill:
        base_damage += attacker["stats"]["attack_power"] * max(int(skill.get("ratio_percent") or 0), 0) / 100
        base_damage += max(int(skill.get("flat_damage") or 0), 0)
    else:
        base_damage += attacker["stats"]["attack_power"] * 0.18
    crit_chance = max(min(int(9 + (attacker["stats"]["divine_sense"] - defender["stats"]["divine_sense"]) * 0.35 + attacker["stats"]["fortune"] * 0.18), 32), 6)
    critical = roll_probability_percent(crit_chance)["success"]
    if critical:
        base_damage *= 1.45
    damage = max(int(round(base_damage - effective_defense * 0.38)), 1)
    guard_ratio = min(_active_effect_value(defender, "guard", "ratio"), 0.6)
    damage = max(int(round(damage * (1 - guard_ratio))), 1)
    absorbed = _consume_shield(defender, damage)
    damage_after_shield = max(damage - absorbed, 0)
    defender["hp"] = max(defender["hp"] - damage_after_shield, 0)
    crit_text = " 会心一击。" if critical else ""
    shield_text = f" 其中 {absorbed} 点被护盾挡下。" if absorbed else ""
    skill_text = ""
    if skill and skill.get("text"):
        skill_text = f"{skill.get('text')} "
    _append_duel_log(
        logs,
        round_no,
        f"{skill_text}{attacker['name']} 以 {move_name} 命中 {defender['name']}，造成 {damage_after_shield} 点伤害。{shield_text}{crit_text}".strip(),
    )
    if skill:
        _apply_duel_effect(attacker, defender, skill, round_no, logs)
    for passive in attacker["combat_entries"].get("passives") or []:
        remaining_uses = _duel_entry_remaining_uses(attacker, passive)
        if remaining_uses is not None and remaining_uses <= 0:
            continue
        chance = max(min(int(passive.get("chance") or 0), 100), 0)
        if chance <= 0 or not roll_probability_percent(chance)["success"]:
            continue
        if not _consume_duel_entry_use(attacker, passive, round_no, logs):
            continue
        _apply_duel_effect(attacker, defender, passive, round_no, logs)
    if damage_after_shield <= 0 and absorbed > 0:
        _append_duel_log(logs, round_no, f"{defender['name']} 的护体灵光完全吃下了这波冲击。", "shield")


def _simulate_duel_battle(
    challenger_bundle: dict[str, Any],
    defender_bundle: dict[str, Any],
    challenger_state: dict[str, Any],
    defender_state: dict[str, Any],
) -> dict[str, Any]:
    challenger_actor = _create_duel_actor(challenger_bundle, challenger_state)
    defender_actor = _create_duel_actor(defender_bundle, defender_state)
    logs: list[dict[str, Any]] = []
    for actor in (challenger_actor, defender_actor):
        talisman = actor.get("active_talisman") or {}
        if talisman:
            effect_uses = max(int(talisman.get("effect_uses") or 1), 1)
            _append_duel_log(
                logs,
                0,
                f"{actor['name']} 先行祭起符箓【{talisman.get('name') or '无名符箓'}】，本场最多显化 {effect_uses} 次。",
                "opening",
            )
    for opening in challenger_actor["combat_entries"]["openings"]:
        _append_duel_log(logs, 0, f"{challenger_actor['name']} 起手运转，{opening}", "opening")
    for opening in defender_actor["combat_entries"]["openings"]:
        _append_duel_log(logs, 0, f"{defender_actor['name']} 也不示弱，{opening}", "opening")
    _append_duel_state_log(logs, 0, challenger_actor, defender_actor, text="斗法台禁制已经落下，双方起手气机被完整记录。")

    max_rounds = 8
    round_count = 0
    for round_no in range(1, max_rounds + 1):
        round_count = round_no
        _append_duel_log(logs, round_no, f"第 {round_no} 回合，双方气机再度碰撞。", "round")
        for actor in (challenger_actor, defender_actor):
            _tick_duel_dot(actor, "burn", round_no, logs)
            _tick_duel_dot(actor, "bleed", round_no, logs)
        if challenger_actor["hp"] <= 0 or defender_actor["hp"] <= 0:
            break
        challenger_speed = challenger_actor["stats"]["body_movement"] + random.uniform(0, 12)
        defender_speed = defender_actor["stats"]["body_movement"] + random.uniform(0, 12)
        order = (
            [(challenger_actor, defender_actor), (defender_actor, challenger_actor)]
            if challenger_speed >= defender_speed
            else [(defender_actor, challenger_actor), (challenger_actor, defender_actor)]
        )
        for attacker, defender in order:
            _execute_duel_turn(attacker, defender, round_no, logs)
            if defender["hp"] <= 0:
                _append_duel_log(logs, round_no, f"{defender['name']} 气机溃散，已难再战。", "finish")
                break
        _decay_duel_effects(challenger_actor)
        _decay_duel_effects(defender_actor)
        _append_duel_state_log(logs, round_no, challenger_actor, defender_actor)
        if challenger_actor["hp"] <= 0 or defender_actor["hp"] <= 0:
            break

    if challenger_actor["hp"] == defender_actor["hp"]:
        challenger_score = challenger_actor["hp"] / challenger_actor["max_hp"] * 100 + challenger_actor["power"] / 30
        defender_score = defender_actor["hp"] / defender_actor["max_hp"] * 100 + defender_actor["power"] / 30
        challenger_win = challenger_score >= defender_score
    else:
        challenger_win = challenger_actor["hp"] > defender_actor["hp"]
    winner = challenger_actor if challenger_win else defender_actor
    loser = defender_actor if challenger_win else challenger_actor
    summary = (
        f"{winner['name']} 以剩余气血 {winner['hp']}/{winner['max_hp']} "
        f"压过 {loser['name']} 的 {loser['hp']}/{loser['max_hp']}，斗法告一段落。"
    )
    _append_duel_state_log(logs, round_count, challenger_actor, defender_actor, text="斗法余波散尽，最终状态已经锁定。")
    return {
        "challenger_actor": challenger_actor,
        "defender_actor": defender_actor,
        "winner_tg": winner["tg"],
        "loser_tg": loser["tg"],
        "summary": summary,
        "round_count": round_count,
        "battle_log": logs,
    }


def _build_duel_snapshot(
    bundle: dict[str, Any],
    state: dict[str, Any],
    opponent_profile: dict[str, Any],
    win_rate: float,
) -> dict[str, Any]:
    profile = bundle["profile"]
    technique = bundle.get("current_technique") or {}
    talisman = bundle.get("active_talisman") or {}
    root_modifier = _root_element_duel_modifier(profile, opponent_profile) * ROOT_ELEMENT_FACTOR_WEIGHT
    root_factor = float(state.get("root_factor") or _resolved_root_combat_factor(profile, state.get("quality_payload") or {}, opponent_profile))
    stats = {
        key: int(round(value))
        for key, value in state["stats"].items()
        if key in {
            "bone",
            "comprehension",
            "divine_sense",
            "fortune",
            "qi_blood",
            "true_yuan",
            "body_movement",
            "attack_power",
            "defense_power",
            "duel_rate_bonus",
        }
    }
    return {
        "name": _duel_display_name(profile),
        "realm_text": f"{profile['realm_stage']}{profile['realm_layer']}层",
        "power": round(state["power"], 2),
        "win_rate": round(win_rate * 100, 1),
        "root_text": format_root(profile),
        "root_quality": state["quality"],
        "root_modifier_percent": round(root_modifier * 100, 1),
        "root_factor": round(root_factor, 3),
        "technique_name": technique.get("name") or "未修功法",
        "artifact_names": _duel_item_names(bundle.get("equipped_artifacts"), "未装备法宝"),
        "talisman_name": talisman.get("name") or "未备符箓",
        "stats": stats,
    }


def _format_duel_side_block(snapshot: dict[str, Any], label: str) -> list[str]:
    stats = snapshot["stats"]
    side_emoji = "🟥" if label == "挑战者" else "🟦" if label == "应战者" else "⚔️"
    return [
        f"{side_emoji} {label}：{_duel_md_escape(snapshot['name'])}",
        f"🏯 境界：`{_duel_md_escape(snapshot['realm_text'])}`",
        f"⚡ 战力：`{snapshot['power']:.1f}` ｜ 🎯 预测胜率：`{snapshot['win_rate']:.1f}%`",
        f"🌱 灵根：{_duel_md_escape(snapshot['root_text'])}",
        f"🧭 五行修正：`{snapshot['root_modifier_percent']:+.1f}%` ｜ 🪨 战斗系数：`{snapshot['root_factor']:.3f}`",
        f"📜 功法：{_duel_md_escape(snapshot['technique_name'])}",
        f"🧰 法宝：{_duel_md_escape(snapshot['artifact_names'])}",
        f"🧿 符箓：{_duel_md_escape(snapshot['talisman_name'])}",
        f"⚔️ 核心：`攻 {stats['attack_power']}` ｜ `防 {stats['defense_power']}` ｜ `斗法 {stats['duel_rate_bonus']:+d}%`",
        f"🩸 续航：`气血 {stats['qi_blood']}` ｜ `真元 {stats['true_yuan']}` ｜ `身法 {stats['body_movement']}`",
        f"🧠 资质：`根骨 {stats['bone']}` ｜ `悟性 {stats['comprehension']}` ｜ `神识 {stats['divine_sense']}` ｜ `机缘 {stats['fortune']}`",
    ]


def _normalize_duel_mode(raw: str | None) -> str:
    value = str(raw or "standard").strip().lower()
    aliases = {
        "standard": "standard",
        "normal": "standard",
        "master": "master",
        "furnace": "master",
        "slave": "master",
        "servant": "master",
        "主仆": "master",
        "炉鼎": "master",
        "death": "death",
        "dead": "death",
        "生死": "death",
    }
    return aliases.get(value, "standard")


def _parse_optional_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _slave_cooldown_delta() -> timedelta:
    settings = get_xiuxian_settings()
    hours = max(int(settings.get("slave_challenge_cooldown_hours", DEFAULT_SETTINGS["slave_challenge_cooldown_hours"]) or 0), 1)
    return timedelta(hours=hours)


def _furnace_harvest_percent(settings: dict[str, Any] | None = None) -> int:
    source = settings or get_xiuxian_settings()
    return max(
        min(int(source.get("furnace_harvest_cultivation_percent", DEFAULT_SETTINGS["furnace_harvest_cultivation_percent"]) or 0), 100),
        0,
    )


def _profile_optional_datetime_value(profile: XiuxianProfile | dict[str, Any] | None, field: str) -> datetime | None:
    if profile is None:
        return None
    raw = profile.get(field) if isinstance(profile, dict) else getattr(profile, field, None)
    if isinstance(raw, datetime):
        return raw
    return _parse_optional_datetime(raw)


def _rebirth_cooldown_state(
    profile: XiuxianProfile | dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = settings or get_xiuxian_settings()
    enabled = bool(source.get("rebirth_cooldown_enabled", DEFAULT_SETTINGS["rebirth_cooldown_enabled"]))
    base_hours = min(
        max(_coerce_int(source.get("rebirth_cooldown_base_hours"), DEFAULT_SETTINGS["rebirth_cooldown_base_hours"], 0), 0),
        8760,
    )
    increment_hours = min(
        max(
            _coerce_int(
                source.get("rebirth_cooldown_increment_hours"),
                DEFAULT_SETTINGS["rebirth_cooldown_increment_hours"],
                0,
            ),
            0,
        ),
        8760,
    )
    rebirth_count = 0
    if profile is not None:
        rebirth_count = int((profile.get("rebirth_count") if isinstance(profile, dict) else getattr(profile, "rebirth_count", 0)) or 0)
    death_at = _profile_optional_datetime_value(profile, "death_at")
    configured_cooldown_hours = max(base_hours + rebirth_count * increment_hours, 0) if death_at is not None else 0
    cooldown_hours = configured_cooldown_hours if enabled else 0
    available_at = death_at + timedelta(hours=cooldown_hours) if death_at is not None and cooldown_hours > 0 else None
    now = datetime.now(available_at.tzinfo) if available_at is not None and available_at.tzinfo is not None else utcnow()
    remaining_seconds = max(int((available_at - now).total_seconds()), 0) if available_at is not None else 0
    blocked = bool(enabled and death_at is not None and cooldown_hours > 0 and remaining_seconds > 0)
    reason = ""
    if blocked and available_at is not None:
        reason = (
            f"转世重修冷却中，还需等待 {_format_countdown(timedelta(seconds=remaining_seconds))}，"
            f"预计 {serialize_datetime(available_at) or '稍后'} 后可重新踏入仙途。"
        )
    return {
        "enabled": enabled,
        "base_hours": base_hours,
        "increment_hours": increment_hours,
        "cooldown_hours": cooldown_hours,
        "started_at": serialize_datetime(death_at),
        "available_at": serialize_datetime(available_at),
        "remaining_seconds": remaining_seconds,
        "blocked": blocked,
        "reason": reason,
    }


def _profile_is_dead(profile: XiuxianProfile | dict[str, Any] | None) -> bool:
    return _profile_optional_datetime_value(profile, "death_at") is not None


def _profile_retreating_state(profile: XiuxianProfile | dict[str, Any] | None) -> bool:
    if profile is None:
        return False
    if isinstance(profile, dict):
        return bool(
            profile.get("retreat_started_at")
            and profile.get("retreat_end_at")
            and int(profile.get("retreat_minutes_total") or 0) > int(profile.get("retreat_minutes_resolved") or 0)
        )
    return _is_retreating(profile)


def _profile_realm_layer_value(profile: XiuxianProfile | dict[str, Any] | None) -> int:
    if profile is None:
        return 1
    raw = profile.get("realm_layer") if isinstance(profile, dict) else getattr(profile, "realm_layer", 1)
    return max(int(raw or 1), 1)


def _profile_cultivation_threshold(profile: XiuxianProfile | dict[str, Any] | None) -> int:
    if isinstance(profile, dict):
        stage = normalize_realm_stage(profile.get("realm_stage") or FIRST_REALM_STAGE)
    else:
        stage = normalize_realm_stage(getattr(profile, "realm_stage", None) or FIRST_REALM_STAGE)
    return cultivation_threshold(stage, _profile_realm_layer_value(profile))


def _profile_stage_cultivation_total(profile: XiuxianProfile | dict[str, Any] | None) -> int:
    if isinstance(profile, dict):
        stage = normalize_realm_stage(profile.get("realm_stage") or FIRST_REALM_STAGE)
        layer = max(int(profile.get("realm_layer") or 1), 1)
        cultivation = max(int(profile.get("cultivation") or 0), 0)
    else:
        stage = normalize_realm_stage(getattr(profile, "realm_stage", None) or FIRST_REALM_STAGE)
        layer = max(int(getattr(profile, "realm_layer", 1) or 1), 1)
        cultivation = max(int(getattr(profile, "cultivation", 0) or 0), 0)
    total = cultivation
    for current_layer in range(1, layer):
        total += cultivation_threshold(stage, current_layer)
    return total


def _apply_stage_cultivation_loss(stage: str, layer: int, cultivation: int, loss: int) -> tuple[int, int, int]:
    current_stage = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    current_layer = max(int(layer or 1), 1)
    current_cultivation = min(max(int(cultivation or 0), 0), cultivation_threshold(current_stage, current_layer))
    remaining_loss = max(int(loss or 0), 0)
    before_total = _profile_stage_cultivation_total(
        {
            "realm_stage": current_stage,
            "realm_layer": current_layer,
            "cultivation": current_cultivation,
        }
    )

    while remaining_loss > 0:
        if current_cultivation >= remaining_loss:
            current_cultivation -= remaining_loss
            remaining_loss = 0
            break
        remaining_loss -= current_cultivation
        if current_layer <= 1:
            current_cultivation = 0
            remaining_loss = 0
            break
        current_layer -= 1
        current_cultivation = cultivation_threshold(current_stage, current_layer)

    after_total = _profile_stage_cultivation_total(
        {
            "realm_stage": current_stage,
            "realm_layer": current_layer,
            "cultivation": current_cultivation,
        }
    )
    return current_layer, current_cultivation, max(before_total - after_total, 0)


def _furnace_harvest_preview(
    owner_profile: XiuxianProfile | dict[str, Any] | None,
    furnace_profile: XiuxianProfile | dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, int]:
    percent = _furnace_harvest_percent(settings)
    owner_threshold = _profile_cultivation_threshold(owner_profile)
    furnace_threshold = _profile_cultivation_threshold(furnace_profile)
    furnace_total_progress = _profile_stage_cultivation_total(furnace_profile)
    if isinstance(furnace_profile, dict):
        furnace_stage = normalize_realm_stage(furnace_profile.get("realm_stage") or FIRST_REALM_STAGE)
        furnace_current = max(int(furnace_profile.get("cultivation") or 0), 0)
    else:
        furnace_stage = normalize_realm_stage(getattr(furnace_profile, "realm_stage", None) or FIRST_REALM_STAGE)
        furnace_current = max(int(getattr(furnace_profile, "cultivation", 0) or 0), 0)
    furnace_layer = _profile_realm_layer_value(furnace_profile)
    furnace_loss = 0
    furnace_layer_after = furnace_layer
    furnace_cultivation_after = furnace_current
    if percent > 0 and furnace_total_progress > 0:
        planned_loss = max(int(round(furnace_total_progress * percent / 100)), 1)
        furnace_layer_after, furnace_cultivation_after, furnace_loss = _apply_stage_cultivation_loss(
            furnace_stage,
            furnace_layer,
            furnace_current,
            planned_loss,
        )
    master_gain_raw = 0
    if furnace_loss > 0:
        master_gain_raw = max(int(round(furnace_loss * owner_threshold / max(furnace_threshold, 1))), 1)
    return {
        "harvest_percent": percent,
        "owner_threshold": owner_threshold,
        "furnace_threshold": furnace_threshold,
        "furnace_current": furnace_total_progress,
        "furnace_current_layer_cultivation": furnace_current,
        "furnace_progress_total": furnace_total_progress,
        "furnace_loss": furnace_loss,
        "furnace_layer_after": furnace_layer_after,
        "furnace_cultivation_after": furnace_cultivation_after,
        "master_gain_raw": master_gain_raw,
    }


def _furnace_harvest_reason(
    owner_profile: XiuxianProfile | dict[str, Any] | None,
    furnace_profile: XiuxianProfile | dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> str:
    if owner_profile is None or furnace_profile is None:
        return "当前没有可采补的炉鼎。"
    if isinstance(owner_profile, dict):
        owner_tg = int(owner_profile.get("tg") or 0)
    else:
        owner_tg = int(getattr(owner_profile, "tg", 0) or 0)
    if isinstance(furnace_profile, dict):
        furnace_master_tg = int(furnace_profile.get("master_tg") or 0)
    else:
        furnace_master_tg = int(getattr(furnace_profile, "master_tg", 0) or 0)
    furnace_name = _profile_display_label(furnace_profile, "该炉鼎")
    if owner_tg <= 0 or furnace_master_tg != owner_tg:
        return f"{furnace_name} 并非你的炉鼎。"
    if _profile_is_dead(owner_profile):
        return "角色已死亡，只能重新踏出仙途。"
    if _profile_is_dead(furnace_profile):
        return f"{furnace_name} 当前已身死道消，无法继续采补。"
    if _profile_retreating_state(owner_profile):
        return "闭关期间无法采补炉鼎。"
    if _profile_retreating_state(furnace_profile):
        return f"{furnace_name} 正在闭关，暂时无法采补。"
    try:
        assert_social_action_allowed(owner_profile, furnace_profile, "采补")
    except ValueError as exc:
        return str(exc)
    if _furnace_harvest_percent(settings) <= 0:
        return "当前炉鼎采补比例为 0%，已被后台关闭。"
    timestamp = _profile_optional_datetime_value(furnace_profile, "furnace_harvested_at")
    current_time = now or utcnow()
    if is_same_china_day(timestamp, current_time):
        return "今日已经对这名炉鼎采补过了。"
    preview = _furnace_harvest_preview(owner_profile, furnace_profile, settings=settings)
    if preview["furnace_current"] <= 0 or preview["furnace_loss"] <= 0 or preview["master_gain_raw"] <= 0:
        return f"{furnace_name} 当前修为过低，暂无可采补收益。"
    return ""


def _decorate_furnace_profile_for_owner(
    owner_profile: dict[str, Any],
    furnace_profile: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(furnace_profile or {})
    preview = _furnace_harvest_preview(owner_profile, payload, settings=settings)
    reason = _furnace_harvest_reason(owner_profile, payload, settings=settings)
    payload.update(
        {
            "can_harvest_today": not reason,
            "harvest_reason": reason,
            "estimated_harvest_gain": preview["master_gain_raw"],
            "estimated_harvest_loss": preview["furnace_loss"],
            "harvest_percent": preview["harvest_percent"],
            "realm_text": f"{payload.get('realm_stage') or FIRST_REALM_STAGE}{_profile_realm_layer_value(payload)}层",
            "furnace_relation_label": "炉鼎",
        }
    )
    return payload


def _validate_duel_mode(duel: dict[str, Any], duel_mode: str) -> dict[str, Any]:
    challenger_profile = duel["challenger"]["profile"]
    defender_profile = duel["defender"]["profile"]
    challenger_tg = int(challenger_profile["tg"])
    defender_tg = int(defender_profile["tg"])
    mode = _normalize_duel_mode(duel_mode)
    context = {
        "duel_mode": mode,
        "break_free_tg": None,
        "owner_tg": None,
    }
    if mode != "master":
        return context
    challenger_master = int(challenger_profile.get("master_tg") or 0)
    defender_master = int(defender_profile.get("master_tg") or 0)
    if challenger_master and challenger_master != defender_tg:
        raise ValueError("你已是他人炉鼎，只能向自己的主人发起脱离挑战。")
    if defender_master and defender_master != challenger_tg:
        raise ValueError("对方已归于他人名下，无法再发起新的炉鼎对决。")
    if challenger_master == defender_tg:
        available = _parse_optional_datetime(challenger_profile.get("servitude_challenge_available_at"))
        if available and available > utcnow():
            remaining = available - utcnow()
            hours = max(int(remaining.total_seconds() // 3600), 0)
            minutes = max(int((remaining.total_seconds() % 3600) // 60), 0)
            raise ValueError(f"脱离挑战冷却中，还需约 {hours} 小时 {minutes} 分钟。")
        context["break_free_tg"] = challenger_tg
        context["owner_tg"] = defender_tg
        return context
    if defender_master == challenger_tg:
        raise ValueError("主人无需再次发起炉鼎对决，等待炉鼎自行挑战即可。")
    if challenger_master or defender_master:
        raise ValueError("炉鼎对决只允许自由身之间对决，或炉鼎向主人发起脱离挑战。")
    return context


def _duel_mode_preview_lines(duel: dict[str, Any], duel_mode: str) -> list[str]:
    mode = _normalize_duel_mode(duel_mode)
    challenger_profile = duel["challenger"]["profile"]
    defender_profile = duel["defender"]["profile"]
    if mode == "master":
        if int(challenger_profile.get("master_tg") or 0) == int(defender_profile["tg"]):
            return [
                "⛓️ 脱离挑战：炉鼎胜，则立即摆脱炉鼎印记；主人胜，则延长下一次强制挑战冷却。",
            ]
        return [
            "⛓️ 炉鼎对决：败者将被烙上炉鼎印记，名帖公开归属，后续灵石收益按后台比例上供。",
        ]
    if mode == "death":
        return [
            "☠️ 生死斗：胜者继承败者全部灵石、物品与修为。",
            "☠️ 修为继承不会越过当前大境界上限，仍需自行突破。",
            "☠️ 败者角色死亡，只能重新踏出仙途。",
        ]
    return []


def format_duel_matchup_text(
    duel: dict[str, Any],
    stake: int = 0,
    title: str = "⚔️ **斗法邀请**",
    plunder_percent: int | None = None,
    duel_mode: str = "standard",
) -> str:
    settings = get_xiuxian_settings()
    if plunder_percent is None:
        plunder_percent = max(
            min(
                int(
                    settings.get(
                        "duel_winner_steal_percent",
                        DEFAULT_SETTINGS["duel_winner_steal_percent"],
                    )
                    or 0
                ),
                100,
            ),
            0,
        )
    artifact_plunder_chance = max(
        min(int(settings.get("artifact_plunder_chance", DEFAULT_SETTINGS["artifact_plunder_chance"]) or 0), 100),
        0,
    )
    lines = [
        title,
        *_format_duel_side_block(duel["challenger_snapshot"], "挑战者"),
        "",
        *_format_duel_side_block(duel["defender_snapshot"], "应战者"),
        "",
        f"📊 综合预测：挑战者 `{duel['challenger_rate'] * 100:.1f}%` / 应战者 `{duel['defender_rate'] * 100:.1f}%`",
    ]
    if stake:
        lines.append(f"💰 赌注：每人 `{stake}` 灵石")
    lines.append(f"🎁 胜者掠夺：败者当前灵石的 `{plunder_percent}%`")
    lines.append(f"🗡️ 法宝掠夺：基础 `{artifact_plunder_chance}%` 夺取 1 件未绑定法宝，受双方机缘影响")
    lines.extend(_duel_mode_preview_lines(duel, duel_mode))
    return "\n".join(lines)


def _duel_odds_score(profile: dict[str, Any], state: dict[str, Any], opponent_profile: dict[str, Any] | None = None) -> float:
    stats = state["stats"]
    offense = max(float(stats.get("attack_power") or 0), 0.0)
    defense = max(float(stats.get("defense_power") or 0), 0.0)
    qi_blood = max(float(stats.get("qi_blood") or 0), 0.0)
    true_yuan = max(float(stats.get("true_yuan") or 0), 0.0)
    movement = max(float(stats.get("body_movement") or 0), 0.0)
    divine_sense = max(float(stats.get("divine_sense") or 0), 0.0)
    fortune = max(float(stats.get("fortune") or 0), 0.0)
    bone = max(float(stats.get("bone") or 0), 0.0)
    comprehension = max(float(stats.get("comprehension") or 0), 0.0)
    karma = max(float(stats.get("karma") or 0), 0.0)
    duel_rate_bonus = float(stats.get("duel_rate_bonus") or 0)

    score = (
        max(float(state.get("power") or 0.0), 1.0)
        + offense * 5.0
        + defense * 4.0
        + qi_blood * 0.08
        + true_yuan * 0.06
        + movement * 4.2
        + divine_sense * 2.8
        + fortune * 1.7
        + bone * 1.4
        + comprehension * 1.6
        + karma * 1.8
        + duel_rate_bonus * 18.0
    )

    if offense <= 0:
        score *= 0.42
    elif offense < 5:
        score *= 0.72
    if defense <= 0:
        score *= 0.78
    if offense <= 0 and defense <= 0:
        score *= 0.72
    return max(score, 1.0)


def compute_duel_odds(challenger_tg: int, defender_tg: int, duel_mode: str = "standard") -> dict[str, Any]:
    challenger = serialize_full_profile(challenger_tg)
    defender = serialize_full_profile(defender_tg)
    challenger_profile = challenger["profile"]
    defender_profile = defender["profile"]
    if not challenger_profile["consented"] or not defender_profile["consented"]:
        raise ValueError("斗法双方都必须已经踏入仙途。")
    assert_profile_alive(challenger_profile, "发起斗法")
    assert_profile_alive(defender_profile, "应战斗法")
    duel_mode_value = _normalize_duel_mode(duel_mode)
    mode_context = _validate_duel_mode({"challenger": challenger, "defender": defender}, duel_mode_value)
    is_break_free_duel = bool(
        duel_mode_value == "master"
        and int(mode_context.get("break_free_tg") or 0) > 0
        and int(mode_context.get("owner_tg") or 0) > 0
    )
    if not is_break_free_duel:
        assert_social_action_allowed(challenger_profile, defender_profile, "斗法")

    challenger_state = _battle_bundle(challenger, defender_profile)
    defender_state = _battle_bundle(defender, challenger_profile)
    challenger_score = _duel_odds_score(challenger_profile, challenger_state, defender_profile)
    defender_score = _duel_odds_score(defender_profile, defender_state, challenger_profile)
    stage_diff = realm_index(challenger_profile["realm_stage"]) - realm_index(defender_profile["realm_stage"])
    score_gap = challenger_score - defender_score
    scale = max((challenger_score + defender_score) * 0.12, 240.0)
    rate = 1.0 / (1.0 + exp(-score_gap / scale))
    rate = adjust_probability_rate(
        rate,
        actor_fortune=challenger_state["stats"]["fortune"],
        opponent_fortune=defender_state["stats"]["fortune"],
        actor_weight=0.12,
        opponent_weight=0.12,
        minimum=0.04,
        maximum=0.96,
    )
    defender_rate = max(min(1 - rate, 0.999), 0.001)
    challenger_snapshot = _build_duel_snapshot(challenger, challenger_state, defender_profile, rate)
    defender_snapshot = _build_duel_snapshot(defender, defender_state, challenger_profile, defender_rate)
    duel_payload = {
        "challenger": challenger,
        "defender": defender,
        "duel_mode": duel_mode_value,
        "challenger_snapshot": challenger_snapshot,
        "defender_snapshot": defender_snapshot,
        "challenger_rate": round(rate, 4),
        "defender_rate": round(defender_rate, 4),
        "challenger_power": round(challenger_state["power"], 2),
        "defender_power": round(defender_state["power"], 2),
        "weights": {
            "stage_diff": stage_diff,
            "challenger_score": round(challenger_score, 2),
            "defender_score": round(defender_score, 2),
            "root_modifier": round(_root_element_duel_modifier(challenger_profile, defender_profile), 4),
            "challenger_quality": challenger_state["quality"],
            "defender_quality": defender_state["quality"],
            "challenger_attack": round(challenger_state["stats"]["attack_power"]),
            "challenger_defense": round(challenger_state["stats"]["defense_power"]),
            "challenger_qi_blood": round(challenger_state["stats"]["qi_blood"]),
            "challenger_true_yuan": round(challenger_state["stats"]["true_yuan"]),
            "challenger_body_movement": round(challenger_state["stats"]["body_movement"]),
            "defender_attack": round(defender_state["stats"]["attack_power"]),
            "defender_defense": round(defender_state["stats"]["defense_power"]),
            "defender_qi_blood": round(defender_state["stats"]["qi_blood"]),
            "defender_true_yuan": round(defender_state["stats"]["true_yuan"]),
            "defender_body_movement": round(defender_state["stats"]["body_movement"]),
        },
        "mode_context": mode_context,
    }
    return duel_payload


def assert_duel_stake_affordable(
    challenger_profile: dict[str, Any],
    defender_profile: dict[str, Any],
    stake_amount: int,
) -> None:
    stake = max(int(stake_amount or 0), 0)
    if stake <= 0:
        return
    shortages = []
    for profile in (challenger_profile, defender_profile):
        current_stone = int(profile.get("spiritual_stone") or 0)
        if current_stone >= stake:
            continue
        shortages.append(f"{_duel_display_name(profile)} 当前仅有 {current_stone} 灵石")
    if shortages:
        raise ValueError(f"赌注 {stake} 灵石无法成立：" + "；".join(shortages) + "。")


def _resolve_duel_stake_amount(stake: int, *, settings: dict[str, Any] | None = None, allow_zero: bool = False) -> int:
    amount = max(int(stake or 0), 0)
    source = settings or get_xiuxian_settings()
    minimum = max(int(source.get("duel_bet_min_amount", DEFAULT_SETTINGS["duel_bet_min_amount"]) or 0), 1)
    maximum = max(int(source.get("duel_bet_max_amount", DEFAULT_SETTINGS["duel_bet_max_amount"]) or 0), minimum)
    if allow_zero and amount == 0:
        return 0
    if amount < minimum:
        raise ValueError(f"斗法赌注至少需要 {minimum} 灵石。")
    if amount > maximum:
        raise ValueError(f"斗法赌注最多只能设置为 {maximum} 灵石。")
    return amount


def _clear_duel_active_talismans(*tgs: int) -> None:
    cleared: set[int] = set()
    for tg in tgs:
        if tg in cleared:
            continue
        set_active_talisman(int(tg), None)
        cleared.add(int(tg))


def _clear_servitude_marks(row: XiuxianProfile) -> None:
    row.master_tg = None
    row.servitude_started_at = None
    row.servitude_challenge_available_at = None
    row.furnace_harvested_at = None


def _queue_servitude_cache_invalidation(session: Session, *tgs: int) -> None:
    affected = sorted({int(tg or 0) for tg in tgs if int(tg or 0) > 0})
    if not affected:
        return
    _queue_profile_cache_invalidation(session, *affected)
    _queue_user_view_cache_invalidation(session, *affected)


def _reassign_slave_roster(session: Session, from_master_tg: int, to_master_tg: int) -> list[int]:
    rows = (
        session.query(XiuxianProfile)
        .filter(XiuxianProfile.master_tg == int(from_master_tg), XiuxianProfile.tg != int(to_master_tg))
        .with_for_update()
        .all()
    )
    reassigned: list[int] = []
    for row in rows:
        row.master_tg = int(to_master_tg)
        row.furnace_harvested_at = None
        row.updated_at = utcnow()
        reassigned.append(int(row.tg))
    return reassigned


def _transfer_inventory_rows(session: Session, model_cls, ref_field: str, loser_tg: int, winner_tg: int) -> None:
    rows = session.query(model_cls).filter(model_cls.tg == int(loser_tg)).with_for_update().all()
    ref_column = getattr(model_cls, ref_field)
    protected_starter_artifact_id = None
    protect_starter_artifact = False
    if model_cls is XiuxianArtifactInventory and ref_field == "artifact_id":
        starter_artifact = session.query(XiuxianArtifact.id).filter(XiuxianArtifact.name == STARTER_ARTIFACT_NAME).first()
        protected_starter_artifact_id = int(starter_artifact[0]) if starter_artifact else None
        protect_starter_artifact = bool(protected_starter_artifact_id and starter_artifact_protection_active(loser_tg))
    for row in rows:
        ref_id = int(getattr(row, ref_field))
        unique_artifact = None
        if model_cls is XiuxianArtifactInventory and ref_field == "artifact_id":
            unique_artifact = (
                session.query(XiuxianArtifact)
                .filter(XiuxianArtifact.id == int(ref_id))
                .with_for_update()
                .first()
            )
        total_quantity = max(int(getattr(row, "quantity", 0) or 0), 0)
        total_bound_quantity = 0
        if hasattr(row, "bound_quantity"):
            total_bound_quantity = max(min(int(getattr(row, "bound_quantity", 0) or 0), total_quantity), 0)
        retained_quantity = 0
        retained_bound_quantity = 0
        if protect_starter_artifact and int(ref_id) == int(protected_starter_artifact_id or 0):
            retained_quantity = min(total_quantity, 1)
            retained_bound_quantity = min(total_bound_quantity, retained_quantity)
        transfer_quantity = max(total_quantity - retained_quantity, 0)
        transfer_bound_quantity = max(total_bound_quantity - retained_bound_quantity, 0)
        if unique_artifact is not None and bool(unique_artifact.unique_item):
            transfer_quantity = min(transfer_quantity, 1)
            transfer_bound_quantity = min(transfer_bound_quantity, transfer_quantity)
        if transfer_quantity <= 0:
            if retained_quantity > 0:
                row.quantity = retained_quantity
                if hasattr(row, "bound_quantity"):
                    row.bound_quantity = retained_bound_quantity
                row.updated_at = utcnow()
            continue
        existing = (
            session.query(model_cls)
            .filter(model_cls.tg == int(winner_tg), ref_column == ref_id)
            .with_for_update()
            .first()
        )
        if unique_artifact is not None and bool(unique_artifact.unique_item) and existing is not None and int(existing.quantity or 0) > 0:
            if retained_quantity > 0:
                row.quantity = retained_quantity
                if hasattr(row, "bound_quantity"):
                    row.bound_quantity = retained_bound_quantity
                row.updated_at = utcnow()
            else:
                session.delete(row)
            continue
        if existing is None:
            if retained_quantity > 0:
                transfer_payload = {
                    "tg": int(winner_tg),
                    ref_field: ref_id,
                    "quantity": transfer_quantity,
                }
                if hasattr(row, "bound_quantity"):
                    transfer_payload["bound_quantity"] = transfer_bound_quantity
                session.add(model_cls(**transfer_payload))
                row.quantity = retained_quantity
                if hasattr(row, "bound_quantity"):
                    row.bound_quantity = retained_bound_quantity
                row.updated_at = utcnow()
            else:
                row.tg = int(winner_tg)
                row.quantity = transfer_quantity
                if hasattr(row, "bound_quantity"):
                    row.bound_quantity = transfer_bound_quantity
                row.updated_at = utcnow()
            continue
        existing.quantity = int(existing.quantity or 0) + transfer_quantity
        if hasattr(existing, "bound_quantity"):
            existing.bound_quantity = int(getattr(existing, "bound_quantity", 0) or 0) + transfer_bound_quantity
        existing.updated_at = utcnow()
        if retained_quantity > 0:
            row.quantity = retained_quantity
            if hasattr(row, "bound_quantity"):
                row.bound_quantity = retained_bound_quantity
            row.updated_at = utcnow()
        else:
            session.delete(row)


def _transfer_user_knowledge(session: Session, model_cls, ref_field: str, loser_tg: int, winner_tg: int) -> None:
    rows = session.query(model_cls).filter(model_cls.tg == int(loser_tg)).with_for_update().all()
    ref_column = getattr(model_cls, ref_field)
    for row in rows:
        ref_id = int(getattr(row, ref_field))
        existing = (
            session.query(model_cls)
            .filter(model_cls.tg == int(winner_tg), ref_column == ref_id)
            .with_for_update()
            .first()
        )
        if existing is None:
            row.tg = int(winner_tg)
            row.updated_at = utcnow()
            continue
        session.delete(row)


def _mark_profile_dead(session: Session, row: XiuxianProfile) -> None:
    _end_marriage_for_user(session, int(row.tg or 0), ended_at=utcnow())
    row.consented = False
    row.gender = None
    row.root_type = None
    row.root_primary = None
    row.root_secondary = None
    row.root_relation = None
    row.root_bonus = 0
    row.root_quality = None
    row.root_quality_level = 1
    row.root_quality_color = None
    row.realm_stage = FIRST_REALM_STAGE
    row.realm_layer = 0
    row.cultivation = 0
    row.spiritual_stone = 0
    row.sect_id = None
    row.sect_role_key = None
    row.sect_contribution = 0
    row.current_artifact_id = None
    row.active_talisman_id = None
    row.current_technique_id = None
    row.current_title_id = None
    row.shop_broadcast = False
    row.last_salary_claim_at = None
    row.sect_joined_at = None
    row.sect_betrayal_until = None
    row.last_train_at = None
    row.retreat_started_at = None
    row.retreat_end_at = None
    row.retreat_gain_per_minute = 0
    row.retreat_cost_per_minute = 0
    row.retreat_minutes_total = 0
    row.retreat_minutes_resolved = 0
    row.robbery_daily_count = 0
    row.robbery_day_key = None
    row.explore_daily_count = 0
    row.explore_day_key = None
    row.fish_daily_count = 0
    row.fish_day_key = None
    row.encounter_daily_count = 0
    row.encounter_day_key = None
    _clear_servitude_marks(row)
    row.death_at = utcnow()
    row.updated_at = utcnow()


def _apply_master_duel_outcome(
    session: Session,
    duel: dict[str, Any],
    winner_tg: int,
    loser_tg: int,
) -> dict[str, Any] | None:
    if _normalize_duel_mode(duel.get("duel_mode")) != "master":
        return None
    now = utcnow()
    cooldown_until = now + _slave_cooldown_delta()
    winner = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(winner_tg)).with_for_update().first()
    loser = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(loser_tg)).with_for_update().first()
    if winner is None or loser is None:
        return None
    mode_context = duel.get("mode_context") or {}
    break_free_tg = int(mode_context.get("break_free_tg") or 0)
    owner_tg = int(mode_context.get("owner_tg") or 0)
    if break_free_tg and owner_tg:
        slave = session.query(XiuxianProfile).filter(XiuxianProfile.tg == break_free_tg).with_for_update().first()
        if slave is None:
            return None
        if int(winner_tg) == break_free_tg:
            _clear_servitude_marks(slave)
            slave.updated_at = now
            _queue_servitude_cache_invalidation(session, break_free_tg, owner_tg)
            return {"kind": "break_free", "slave_tg": break_free_tg, "owner_tg": owner_tg}
        slave.servitude_challenge_available_at = cooldown_until
        slave.updated_at = now
        _queue_servitude_cache_invalidation(session, break_free_tg, owner_tg)
        return {"kind": "master_defended", "slave_tg": break_free_tg, "owner_tg": owner_tg, "next_challenge_at": cooldown_until.isoformat()}

    loser.master_tg = int(winner_tg)
    loser.servitude_started_at = now
    loser.servitude_challenge_available_at = cooldown_until
    loser.furnace_harvested_at = None
    loser.updated_at = now
    inherited_slaves = _reassign_slave_roster(session, int(loser_tg), int(winner_tg))
    _queue_servitude_cache_invalidation(session, int(winner_tg), int(loser_tg), *inherited_slaves)
    return {
        "kind": "subjugated",
        "master_tg": int(winner_tg),
        "slave_tg": int(loser_tg),
        "inherited_slave_tgs": inherited_slaves,
        "next_challenge_at": cooldown_until.isoformat(),
    }


def _apply_death_duel_outcome(session: Session, winner_tg: int, loser_tg: int) -> dict[str, Any]:
    winner = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(winner_tg)).with_for_update().first()
    loser = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(loser_tg)).with_for_update().first()
    if winner is None or loser is None:
        raise ValueError("生死斗结算失败，角色资料缺失。")
    inherited_stone = int(loser.spiritual_stone or 0)
    inherited_cultivation = int(loser.cultivation or 0)
    if inherited_stone > 0:
        apply_spiritual_stone_delta(session, winner_tg, inherited_stone, action_text="继承生死斗遗产", allow_dead=False, apply_tribute=True)
    cultivation_cap = cultivation_threshold(normalize_realm_stage(winner.realm_stage or FIRST_REALM_STAGE), 9)
    _settle_profile_cultivation(winner, inherited_cultivation)
    winner.updated_at = utcnow()
    _transfer_inventory_rows(session, XiuxianArtifactInventory, "artifact_id", loser_tg, winner_tg)
    _transfer_inventory_rows(session, XiuxianPillInventory, "pill_id", loser_tg, winner_tg)
    _transfer_inventory_rows(session, XiuxianTalismanInventory, "talisman_id", loser_tg, winner_tg)
    _transfer_inventory_rows(session, XiuxianMaterialInventory, "material_id", loser_tg, winner_tg)
    _transfer_user_knowledge(session, XiuxianUserRecipe, "recipe_id", loser_tg, winner_tg)
    _transfer_user_knowledge(session, XiuxianUserTechnique, "technique_id", loser_tg, winner_tg)
    inherited_slaves = _reassign_slave_roster(session, loser_tg, winner_tg)
    session.query(XiuxianEquippedArtifact).filter(XiuxianEquippedArtifact.tg == int(loser_tg)).delete()
    _mark_profile_dead(session, loser)
    return {
        "kind": "death",
        "winner_tg": int(winner_tg),
        "loser_tg": int(loser_tg),
        "inherited_stone": inherited_stone,
        "inherited_cultivation": inherited_cultivation,
        "cultivation_cap": cultivation_cap,
        "inherited_slave_tgs": inherited_slaves,
    }


def resolve_duel(
    challenger_tg: int,
    defender_tg: int,
    stake: int = 0,
    duel_mode: str = "standard",
    *,
    allow_zero_stake: bool = False,
    allow_plunder: bool = True,
    allow_artifact_plunder: bool = True,
    use_rate_outcome: bool = False,
    consent_verified: bool = False,
) -> dict[str, Any]:
    if int(challenger_tg) == int(defender_tg):
        raise ValueError("不能与自己决斗。")
    duel = compute_duel_odds(challenger_tg, defender_tg, duel_mode=duel_mode)
    challenger_profile = duel["challenger"]["profile"]
    defender_profile = duel["defender"]["profile"]
    duel_mode_value = _normalize_duel_mode(duel.get("duel_mode"))
    mode_context = duel.get("mode_context") or {}
    is_break_free_duel = bool(
        duel_mode_value == "master"
        and int(mode_context.get("break_free_tg") or 0) > 0
        and int(mode_context.get("owner_tg") or 0) > 0
    )
    settings = get_xiuxian_settings()
    stake_amount = _resolve_duel_stake_amount(stake, settings=settings, allow_zero=allow_zero_stake or is_break_free_duel)
    plunder_percent = max(
        min(int(settings.get("duel_winner_steal_percent", DEFAULT_SETTINGS["duel_winner_steal_percent"]) or 0), 100),
        0,
    )
    artifact_plunder_base_chance = max(
        min(int(settings.get("artifact_plunder_chance", DEFAULT_SETTINGS["artifact_plunder_chance"]) or 0), 100),
        0,
    )
    assert_duel_stake_affordable(challenger_profile, defender_profile, stake_amount)

    challenger_state = _battle_bundle(duel["challenger"], defender_profile, apply_random=True)
    defender_state = _battle_bundle(duel["defender"], challenger_profile, apply_random=True)
    dynamic_rate = float(duel["challenger_rate"])
    if use_rate_outcome:
        rate_roll = roll_probability_percent(
            int(round(dynamic_rate * 100)),
            actor_fortune=int(challenger_state["stats"]["fortune"] or 0),
            opponent_fortune=int(defender_state["stats"]["fortune"] or 0),
            actor_weight=0.12,
            opponent_weight=0.12,
            minimum=1,
            maximum=99,
        )
        simulated_battle = {
            "winner_tg": challenger_tg if rate_roll["success"] else defender_tg,
            "loser_tg": defender_tg if rate_roll["success"] else challenger_tg,
            "summary": f"本场按综合胜率判定：挑战者胜率 {rate_roll['chance']}%，掷点 {rate_roll['roll']}。",
            "battle_log": [],
            "round_count": 0,
        }
    else:
        simulated_battle = _simulate_duel_battle(duel["challenger"], duel["defender"], challenger_state, defender_state)
    winner_tg = int(simulated_battle["winner_tg"])
    loser_tg = int(simulated_battle["loser_tg"])
    challenger_win = winner_tg == challenger_tg
    winner_state = challenger_state if challenger_win else defender_state
    loser_state = defender_state if challenger_win else challenger_state
    plunder_amount = 0
    mode_outcome = None
    with Session() as session:
        challenger_profile_obj = session.query(XiuxianProfile).filter(XiuxianProfile.tg == challenger_tg).with_for_update().first()
        defender_profile_obj = session.query(XiuxianProfile).filter(XiuxianProfile.tg == defender_tg).with_for_update().first()
        winner_profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == winner_tg).with_for_update().first()
        loser_profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == loser_tg).with_for_update().first()
        if challenger_profile_obj is None or defender_profile_obj is None or winner_profile is None or loser_profile is None:
            raise ValueError("斗法双方的修仙资料缺失。")
        if stake_amount > 0:
            apply_spiritual_stone_delta(session, challenger_tg, -stake_amount, action_text="支付斗法赌注", allow_dead=False, apply_tribute=False)
            apply_spiritual_stone_delta(session, defender_tg, -stake_amount, action_text="支付斗法赌注", allow_dead=False, apply_tribute=False)
        if allow_plunder and plunder_percent > 0:
            loser_current = session.query(XiuxianProfile).filter(XiuxianProfile.tg == loser_tg).with_for_update().first()
            loser_balance = int(loser_current.spiritual_stone or 0) if loser_current is not None else 0
            plunder_amount = loser_balance * plunder_percent // 100
            if plunder_amount > 0:
                apply_spiritual_stone_delta(session, loser_tg, -plunder_amount, action_text="斗法被掠夺", allow_dead=False, apply_tribute=False)
        winnings = stake_amount * 2 + plunder_amount
        if winnings > 0:
            apply_spiritual_stone_delta(session, winner_tg, winnings, action_text="斗法结算", allow_dead=False, apply_tribute=True)
        if duel_mode_value == "master":
            mode_outcome = _apply_master_duel_outcome(session, duel, winner_tg, loser_tg)
        elif duel_mode_value == "death":
            mode_outcome = _apply_death_duel_outcome(session, winner_tg, loser_tg)
        session.commit()

    winner_growth = {"triggered": False, "changes": [], "patch": {}, "chance": 0, "roll": None}
    if duel_mode_value != "death":
        with Session() as session:
            winner_row = session.query(XiuxianProfile).filter(XiuxianProfile.tg == winner_tg).with_for_update().first()
            if winner_row is not None and winner_row.consented:
                winner_growth = _apply_activity_stat_growth_to_profile_row(winner_row, "duel", winner_state["stats"])
                session.commit()

    artifact_plunder_roll = {
        "chance": 0,
        "roll": None,
        "success": False,
    }
    if allow_artifact_plunder:
        artifact_plunder_roll = roll_probability_percent(
            artifact_plunder_base_chance,
            actor_fortune=winner_state["stats"]["fortune"],
            opponent_fortune=loser_state["stats"]["fortune"],
            actor_weight=0.45,
            opponent_weight=0.35,
            minimum=0,
            maximum=95,
        )
    artifact_plunder = None
    if allow_artifact_plunder and duel_mode_value != "death" and artifact_plunder_roll["success"]:
        artifact_plunder = plunder_random_artifact_to_user(winner_tg, loser_tg)
        if artifact_plunder and artifact_plunder.get("artifact"):
            artifact_name = artifact_plunder["artifact"].get("name", "未知法宝")
            create_journal(winner_tg, "duel", "斗法夺宝", f"斗法取胜后夺得法宝【{artifact_name}】")
            create_journal(loser_tg, "duel", "斗法失宝", f"斗法落败后被夺走法宝【{artifact_name}】")

    create_duel_record(
        challenger_tg=challenger_tg,
        defender_tg=defender_tg,
        winner_tg=winner_tg,
        loser_tg=loser_tg,
        duel_mode=duel_mode_value,
        challenger_rate=int(round(dynamic_rate * 1000)),
        defender_rate=int(round((1 - dynamic_rate) * 1000)),
        summary=str(simulated_battle["summary"]),
        battle_log=simulated_battle["battle_log"],
    )
    _clear_duel_active_talismans(challenger_tg, defender_tg)
    achievement_unlocks = record_duel_metrics(challenger_tg, defender_tg, winner_tg, loser_tg)
    return {
        "challenger": serialize_full_profile(challenger_tg),
        "defender": serialize_full_profile(defender_tg),
        "duel_mode": duel_mode_value,
        "winner_tg": winner_tg,
        "loser_tg": loser_tg,
        "challenger_rate": dynamic_rate,
        "defender_rate": 1 - dynamic_rate,
        "roll": None,
        "winner_power": round(max(challenger_state["power"], defender_state["power"]), 2),
        "loser_power": round(min(challenger_state["power"], defender_state["power"]), 2),
        "stake": stake_amount,
        "pot": stake_amount * 2,
        "plunder_percent": plunder_percent,
        "plunder_amount": plunder_amount,
        "artifact_plunder": {
            **artifact_plunder_roll,
            "artifact": None if artifact_plunder is None else artifact_plunder.get("artifact"),
            "was_equipped": bool(artifact_plunder and artifact_plunder.get("was_equipped")),
        },
        "summary": str(simulated_battle["summary"]),
        "battle_log": simulated_battle["battle_log"],
        "round_count": int(simulated_battle["round_count"]),
        "mode_outcome": mode_outcome,
        "winner_attribute_growth": winner_growth.get("changes") or [],
        "achievement_unlocks": achievement_unlocks,
    }


ARENA_MIN_DURATION_MINUTES = 10
ARENA_MAX_DURATION_MINUTES = 720
ARENA_DEFAULT_DURATION_MINUTES = 120
ARENA_FINALIZE_BUSY_RETRY_SECONDS = 5


def _arena_duration_minutes(raw: int | None) -> int:
    return min(max(int(raw or ARENA_DEFAULT_DURATION_MINUTES), ARENA_MIN_DURATION_MINUTES), ARENA_MAX_DURATION_MINUTES)


def _arena_open_fee_stone(settings: dict[str, Any] | None = None) -> int:
    source = settings or get_xiuxian_settings()
    return max(int(source.get("arena_open_fee_stone", DEFAULT_SETTINGS.get("arena_open_fee_stone", 0)) or 0), 0)


def _arena_challenge_fee_stone(settings: dict[str, Any] | None = None) -> int:
    source = settings or get_xiuxian_settings()
    return max(int(source.get("arena_challenge_fee_stone", DEFAULT_SETTINGS.get("arena_challenge_fee_stone", 0)) or 0), 0)


def _arena_stage_rule(stage: str | None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    source = settings or get_xiuxian_settings()
    target_stage = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    legacy_default_reward = max(int(cultivation_threshold(target_stage, 1) or 0), 0)
    default_reward = calculate_arena_cultivation_cap(target_stage)
    for row in list(source.get("arena_stage_rules") or []):
        if normalize_realm_stage((row or {}).get("realm_stage")) != target_stage:
            continue
        configured_reward = max(int((row or {}).get("reward_cultivation") or 0), 0)
        if configured_reward == legacy_default_reward:
            configured_reward = default_reward
        return {
            "realm_stage": target_stage,
            "duration_minutes": _arena_duration_minutes(int((row or {}).get("duration_minutes") or ARENA_DEFAULT_DURATION_MINUTES)),
            "reward_cultivation": configured_reward,
        }
    return {
        "realm_stage": target_stage,
        "duration_minutes": _arena_duration_minutes(ARENA_DEFAULT_DURATION_MINUTES),
        "reward_cultivation": default_reward,
    }


def _profile_realm_stage_only(profile: XiuxianProfile | dict[str, Any] | None) -> str:
    if isinstance(profile, dict):
        return normalize_realm_stage(profile.get("realm_stage") or FIRST_REALM_STAGE)
    return normalize_realm_stage(getattr(profile, "realm_stage", None) or FIRST_REALM_STAGE)


def _assert_arena_realm_match(profile: XiuxianProfile, arena_stage: str, *, action_text: str) -> str:
    current_stage = _profile_realm_stage_only(profile)
    if current_stage != normalize_realm_stage(arena_stage):
        raise ValueError(f"{action_text}仅限 {normalize_realm_stage(arena_stage)} 修士参加，你当前为 {current_stage}。")
    return current_stage


def _arena_effective_reward_cap(stage: str | None, arena: XiuxianArena | dict[str, Any] | None) -> int:
    target_stage = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    if isinstance(arena, dict):
        configured_reward = max(int(arena.get("reward_cultivation") or 0), 0)
    else:
        configured_reward = max(int(getattr(arena, "reward_cultivation", 0) or 0), 0)
    legacy_default_reward = max(int(cultivation_threshold(target_stage, 1) or 0), 0)
    default_reward = calculate_arena_cultivation_cap(target_stage)
    if configured_reward <= 0 or configured_reward == legacy_default_reward:
        return default_reward
    return configured_reward


def _arena_reward_values(profile: XiuxianProfile, arena: XiuxianArena) -> dict[str, int]:
    reward_cultivation = _arena_effective_reward_cap(getattr(arena, "realm_stage", None), arena)
    challenge_count = max(int(getattr(arena, "challenge_count", 0) or 0), 0)
    defense_count = max(int(getattr(arena, "defense_success_count", 0) or 0), 0)
    change_count = max(int(getattr(arena, "champion_change_count", 0) or 0), 0)
    fortune = max(int(getattr(profile, "fortune", 0) or 0), 0)
    fortune_factor = 1.0 + (1.0 - exp(-max(fortune - FORTUNE_BASELINE, 0) / 72.0)) * 0.18
    activity_factor = 0.72 if challenge_count <= 0 else 0.55 + min(challenge_count, 8) * 0.11 + defense_count * 0.08 + change_count * 0.04
    cultivation_reward = max(int(round(reward_cultivation * activity_factor * fortune_factor)), 0)
    if challenge_count <= 0 and reward_cultivation > 0:
        cultivation_reward = max(cultivation_reward, max(int(round(reward_cultivation * 0.55)), 1))
    stone_reward = max(int(round(cultivation_reward * 0.18)) + 8 + challenge_count * 3 + defense_count * 4, 0)
    return {
        "stone_reward": stone_reward,
        "cultivation_reward": cultivation_reward,
        "fortune": fortune,
    }


def _arena_duel_reward_cap(stage: str, arena: XiuxianArena | dict[str, Any] | None) -> int:
    return _arena_effective_reward_cap(stage, arena)


def _arena_duel_cultivation_rewards(stage: str, arena: XiuxianArena | dict[str, Any], duel_result: dict[str, Any]) -> dict[str, int]:
    target_stage = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    threshold = max(int(cultivation_threshold(target_stage, 1) or 0), 1)
    reward_cap = _arena_duel_reward_cap(target_stage, arena)
    if reward_cap <= 0:
        return {
            "winner_reward": 0,
            "loser_reward": 0,
            "reward_cap": 0,
        }
    challenger_rate = min(max(float(duel_result.get("challenger_rate") or 0.5), 0.01), 0.99)
    winner_tg = int(duel_result.get("winner_tg") or 0)
    challenger_tg = int(((duel_result.get("challenger") or {}).get("profile") or {}).get("tg") or 0)
    winner_rate = challenger_rate if winner_tg == challenger_tg else 1 - challenger_rate
    intensity_factor = max(0.0, 1.0 - abs(challenger_rate - 0.5) * 2)
    underdog_factor = max(0.5 - winner_rate, 0.0) * 2

    challenge_count = max(int(arena.get("challenge_count") if isinstance(arena, dict) else getattr(arena, "challenge_count", 0)) or 0, 0)
    settled_challenge_count = challenge_count + 1
    no_challenge_floor = max(int(round(reward_cap * 0.55)), 1)
    active_floor = max(int(round(no_challenge_floor / max(settled_challenge_count, 1))), 1)
    # 单场奖励用指数曲线压住爆发，但保证有人攻擂时不比空擂补偿更寒酸。
    winner_gain = max(int(round(threshold * (0.015 + intensity_factor * 0.007 + underdog_factor * 0.006))), active_floor, 8)
    loser_gain = max(int(round(threshold * (0.006 + intensity_factor * 0.003))), max(active_floor // 2, 3))
    winner_gain = min(winner_gain, reward_cap)
    loser_gain = min(loser_gain, max(reward_cap // 2, 1))
    return {
        "winner_reward": max(winner_gain, 0),
        "loser_reward": max(loser_gain, 0),
        "reward_cap": max(reward_cap, 0),
    }


def list_group_arenas(
    *,
    status: str | None = None,
    group_chat_id: int | None = None,
    realm_stage: str | None = None,
) -> list[dict[str, Any]]:
    with Session() as session:
        query = session.query(XiuxianArena)
        if status:
            query = query.filter(XiuxianArena.status == str(status))
        if group_chat_id is not None:
            query = query.filter(XiuxianArena.group_chat_id == int(group_chat_id))
        if realm_stage:
            query = query.filter(XiuxianArena.realm_stage == normalize_realm_stage(realm_stage))
        query = query.order_by(XiuxianArena.id.desc())
        return [serialize_arena(row) for row in query.all()]


def get_group_arena(arena_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(XiuxianArena).filter(XiuxianArena.id == int(arena_id)).first()
        return serialize_arena(row)


def get_active_group_arena(group_chat_id: int, realm_stage: str | None = None) -> dict[str, Any] | None:
    with Session() as session:
        query = session.query(XiuxianArena).filter(XiuxianArena.group_chat_id == int(group_chat_id), XiuxianArena.status == "active")
        if realm_stage:
            query = query.filter(XiuxianArena.realm_stage == normalize_realm_stage(realm_stage))
        row = query.order_by(XiuxianArena.id.desc()).first()
        return serialize_arena(row)


def patch_group_arena(arena_id: int, **fields) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(XiuxianArena).filter(XiuxianArena.id == int(arena_id)).first()
        if row is None:
            return None
        for key, value in fields.items():
            if not hasattr(row, key):
                continue
            setattr(row, key, value)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_arena(row)


def cancel_group_arena(
    arena_id: int,
    *,
    owner_tg: int | None = None,
    reason: str = "",
    refund_open_fee_stone: int = 0,
) -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianArena)
            .filter(XiuxianArena.id == int(arena_id))
            .with_for_update()
            .first()
        )
        if row is None:
            return None
        if owner_tg is not None and int(row.owner_tg or 0) != int(owner_tg):
            raise ValueError("你无权取消这座擂台。")
        if str(row.status or "") != "active":
            return {"result": "noop", "arena": serialize_arena(row)}
        row.status = "cancelled"
        row.battle_in_progress = False
        row.current_challenger_tg = None
        row.current_challenger_display_name = None
        row.completed_at = utcnow()
        row.updated_at = row.completed_at
        refunded_stone = 0
        refund_amount = max(int(refund_open_fee_stone or 0), 0)
        if refund_amount > 0 and int(row.owner_tg or 0) > 0:
            apply_spiritual_stone_delta(
                session,
                int(row.owner_tg),
                refund_amount,
                action_text="擂台开设手续费退回",
                allow_dead=True,
                apply_tribute=False,
            )
            refunded_stone = refund_amount
        if reason:
            row.latest_result_summary = str(reason).strip()
        session.commit()
        return {
            "result": "cancelled",
            "arena": serialize_arena(row),
            "refund_open_fee_stone": refunded_stone,
        }


def open_group_arena_for_user(
    tg: int,
    *,
    group_chat_id: int,
    champion_display_name: str = "",
    duration_minutes: int | None = None,
) -> dict[str, Any]:
    actor_tg = int(tg)
    chat_id = int(group_chat_id)
    if actor_tg <= 0 or chat_id == 0:
        raise ValueError("擂台参数无效。")
    settings = get_xiuxian_settings()
    open_fee_stone = _arena_open_fee_stone(settings)

    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == actor_tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        assert_currency_operation_allowed(actor_tg, "开设擂台", session=session, profile=profile)
        if is_profile_secluded(profile):
            raise ValueError("你当前处于避世状态，无法开设擂台。")
        arena_stage = _assert_arena_realm_match(profile, profile.realm_stage or FIRST_REALM_STAGE, action_text="开擂")
        arena_rule = _arena_stage_rule(arena_stage, settings)
        duration = int(arena_rule["duration_minutes"])
        reward_cultivation = int(arena_rule["reward_cultivation"])
        active = (
            session.query(XiuxianArena)
            .filter(
                XiuxianArena.group_chat_id == chat_id,
                XiuxianArena.status == "active",
                XiuxianArena.realm_stage == arena_stage,
            )
            .with_for_update()
            .order_by(XiuxianArena.id.desc())
            .first()
        )
        if active is not None:
            raise ValueError(f"当前已存在一座 {arena_stage} 擂台正在开启，请先等这一期结束。")
        if open_fee_stone > 0:
            apply_spiritual_stone_delta(
                session,
                actor_tg,
                -open_fee_stone,
                action_text="开设擂台手续费",
                allow_dead=False,
                apply_tribute=False,
            )
        display_name = str(champion_display_name or "").strip() or _profile_display_label(profile, f"TG {actor_tg}")
        now = utcnow()
        row = XiuxianArena(
            owner_tg=actor_tg,
            owner_display_name=display_name,
            champion_tg=actor_tg,
            champion_display_name=display_name,
            group_chat_id=chat_id,
            realm_stage=arena_stage,
            duration_minutes=duration,
            reward_cultivation=reward_cultivation,
            challenge_count=0,
            defense_success_count=0,
            champion_change_count=0,
            battle_in_progress=False,
            end_at=now + timedelta(minutes=duration),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        arena = serialize_arena(row)

    create_journal(
        actor_tg,
        "arena",
        "开设擂台",
        (
            f"在群 {chat_id} 开设一座 {arena_stage} 擂台，持续 {duration} 分钟，实战修为改为每场攻擂后即时结算。"
            + (f" 支付 {open_fee_stone} 灵石开擂手续费。" if open_fee_stone > 0 else "")
        ),
    )
    achievement_unlocks = record_arena_metrics(actor_tg, opened=1, crowned=1)
    return {
        "arena": arena,
        "achievement_unlocks": achievement_unlocks,
        "open_fee_stone": open_fee_stone,
    }


def challenge_group_arena_for_user(
    arena_id: int,
    challenger_tg: int,
    *,
    challenger_display_name: str = "",
) -> dict[str, Any]:
    arena_id_value = int(arena_id)
    actor_tg = int(challenger_tg)
    if arena_id_value <= 0 or actor_tg <= 0:
        raise ValueError("擂台参数无效。")

    challenger_name = str(challenger_display_name or "").strip()
    champion_tg = 0
    champion_display_name = ""
    current_summary = ""
    forfeit = False
    settings = get_xiuxian_settings()
    challenge_fee_stone = _arena_challenge_fee_stone(settings)

    with Session() as session:
        arena = (
            session.query(XiuxianArena)
            .filter(XiuxianArena.id == arena_id_value)
            .with_for_update()
            .first()
        )
        if arena is None:
            raise ValueError("擂台不存在。")
        if str(arena.status or "") != "active":
            raise ValueError("这座擂台已经结束。")
        if arena.end_at <= utcnow():
            raise ValueError("这座擂台已经到期。")
        if arena.battle_in_progress:
            raise ValueError("当前已有道友正在攻擂，请稍后再试。")
        if int(arena.champion_tg or 0) == actor_tg:
            raise ValueError("你已经是当前擂主，无需再次挑战自己。")
        arena_stage = normalize_realm_stage(arena.realm_stage or FIRST_REALM_STAGE)

        challenger = session.query(XiuxianProfile).filter(XiuxianProfile.tg == actor_tg).with_for_update().first()
        if challenger is None or not challenger.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")
        assert_currency_operation_allowed(actor_tg, "攻擂", session=session, profile=challenger)
        if is_profile_secluded(challenger):
            raise ValueError("你当前处于避世状态，无法攻擂。")
        _assert_arena_realm_match(challenger, arena_stage, action_text="攻擂")
        if challenge_fee_stone > 0:
            apply_spiritual_stone_delta(
                session,
                actor_tg,
                -challenge_fee_stone,
                action_text="攻擂手续费",
                allow_dead=False,
                apply_tribute=False,
            )

        if not challenger_name:
            challenger_name = _profile_display_label(challenger, f"TG {actor_tg}")

        champion_tg = int(arena.champion_tg or 0)
        champion = session.query(XiuxianProfile).filter(XiuxianProfile.tg == champion_tg).with_for_update().first()
        champion_display_name = str(arena.champion_display_name or "").strip() or _profile_display_label(champion, f"TG {champion_tg}")

        if (
            champion is None
            or not champion.consented
            or champion.death_at is not None
            or is_profile_secluded(champion)
            or _profile_realm_stage_only(champion) != arena_stage
        ):
            forfeit = True
            current_summary = f"{challenger_name} 登台时发现旧擂主已失去 {arena_stage} 守擂资格，直接接掌擂台。"
            now = utcnow()
            arena.challenge_count = max(int(arena.challenge_count or 0), 0) + 1
            arena.champion_change_count = max(int(arena.champion_change_count or 0), 0) + 1
            arena.champion_tg = actor_tg
            arena.champion_display_name = challenger_name
            arena.last_winner_tg = actor_tg
            arena.last_winner_display_name = challenger_name
            arena.last_loser_tg = champion_tg or None
            arena.last_loser_display_name = champion_display_name
            arena.latest_result_summary = current_summary
            arena.updated_at = now
            session.commit()
            arena_payload = serialize_arena(arena)
        else:
            arena.battle_in_progress = True
            arena.current_challenger_tg = actor_tg
            arena.current_challenger_display_name = challenger_name
            arena.updated_at = utcnow()
            session.commit()
            arena_payload = None

    if forfeit:
        create_journal(actor_tg, "arena", "登擂夺冠", current_summary)
        if champion_tg > 0:
            create_journal(champion_tg, "arena", "擂主失位", f"{challenger_name} 登台时，你已失去守擂资格，擂主之位被直接接管。")
        achievement_unlocks = record_arena_metrics(actor_tg, crowned=1)
        return {
            "result": "forfeit",
            "arena": arena_payload,
            "duel_result": None,
            "champion_changed": True,
            "achievement_unlocks": achievement_unlocks,
            "summary": current_summary,
            "challenge_fee_stone": challenge_fee_stone,
        }

    duel_result = None
    try:
        duel_result = resolve_duel(
            actor_tg,
            champion_tg,
            0,
            duel_mode="standard",
            allow_zero_stake=True,
            allow_plunder=False,
            allow_artifact_plunder=False,
            use_rate_outcome=True,
        )
    except Exception:
        with Session() as session:
            arena = session.query(XiuxianArena).filter(XiuxianArena.id == arena_id_value).with_for_update().first()
            if arena is not None and str(arena.status or "") == "active":
                arena.battle_in_progress = False
                arena.current_challenger_tg = None
                arena.current_challenger_display_name = None
                arena.updated_at = utcnow()
            if challenge_fee_stone > 0:
                apply_spiritual_stone_delta(
                    session,
                    actor_tg,
                    challenge_fee_stone,
                    action_text="攻擂手续费退回",
                    allow_dead=True,
                    apply_tribute=False,
                )
            session.commit()
        raise

    winner_tg = int(duel_result.get("winner_tg") or 0)
    loser_tg = int(duel_result.get("loser_tg") or 0)
    challenger_profile = (duel_result.get("challenger") or {}).get("profile") or {}
    defender_profile = (duel_result.get("defender") or {}).get("profile") or {}
    winner_profile = challenger_profile if int(challenger_profile.get("tg") or 0) == winner_tg else defender_profile
    loser_profile = defender_profile if int(defender_profile.get("tg") or 0) == loser_tg else challenger_profile
    winner_name = _duel_display_name(winner_profile)
    loser_name = _duel_display_name(loser_profile)
    champion_changed = winner_tg == actor_tg
    summary = f"{winner_name} 在擂台斗法中击败 {loser_name}。{duel_result.get('summary') or ''}".strip()
    winner_cultivation_reward = 0
    loser_cultivation_reward = 0

    with Session() as session:
        arena = (
            session.query(XiuxianArena)
            .filter(XiuxianArena.id == arena_id_value)
            .with_for_update()
            .first()
        )
        if arena is None:
            raise ValueError("擂台记录丢失，无法回写结果。")
        now = utcnow()
        battle_rewards = _arena_duel_cultivation_rewards(arena_stage, arena, duel_result)
        winner_cultivation_reward = int(battle_rewards.get("winner_reward") or 0)
        loser_cultivation_reward = int(battle_rewards.get("loser_reward") or 0)
        winner_row = session.query(XiuxianProfile).filter(XiuxianProfile.tg == winner_tg).with_for_update().first()
        loser_row = session.query(XiuxianProfile).filter(XiuxianProfile.tg == loser_tg).with_for_update().first()
        if winner_row is not None and winner_cultivation_reward > 0:
            _settle_profile_cultivation(winner_row, winner_cultivation_reward)
            winner_row.updated_at = now
        if loser_row is not None and loser_cultivation_reward > 0:
            _settle_profile_cultivation(loser_row, loser_cultivation_reward)
            loser_row.updated_at = now
        arena.challenge_count = max(int(arena.challenge_count or 0), 0) + 1
        if champion_changed:
            arena.champion_change_count = max(int(arena.champion_change_count or 0), 0) + 1
            arena.champion_tg = winner_tg
            arena.champion_display_name = winner_name
        else:
            arena.defense_success_count = max(int(arena.defense_success_count or 0), 0) + 1
        arena.last_winner_tg = winner_tg
        arena.last_winner_display_name = winner_name
        arena.last_loser_tg = loser_tg
        arena.last_loser_display_name = loser_name
        if winner_cultivation_reward > 0 or loser_cultivation_reward > 0:
            summary = f"{summary} 本场修为：{winner_name} +{winner_cultivation_reward}，{loser_name} +{loser_cultivation_reward}。".strip()
        arena.latest_result_summary = summary
        arena.battle_in_progress = False
        arena.current_challenger_tg = None
        arena.current_challenger_display_name = None
        arena.updated_at = now
        session.commit()
        arena_payload = serialize_arena(arena)

    create_journal(
        winner_tg,
        "arena",
        "擂台胜出",
        f"在擂台斗法中击败 {loser_name}，并通过实战收获 {winner_cultivation_reward} 修为。",
    )
    create_journal(
        loser_tg,
        "arena",
        "擂台落败",
        f"在擂台斗法中败给 {winner_name}，但仍从实战中收获 {loser_cultivation_reward} 修为。",
    )

    achievement_unlocks = list(duel_result.get("achievement_unlocks") or [])
    if champion_changed:
        achievement_unlocks.extend(record_arena_metrics(winner_tg, crowned=1))
    else:
        achievement_unlocks.extend(record_arena_metrics(winner_tg, defended=1))

    return {
        "result": "duel",
        "arena": arena_payload,
        "duel_result": duel_result,
        "champion_changed": champion_changed,
        "achievement_unlocks": achievement_unlocks,
        "summary": summary,
        "ended": bool(arena_payload and arena_payload.get("ended")),
        "challenge_fee_stone": challenge_fee_stone,
        "winner_cultivation_reward": winner_cultivation_reward,
        "loser_cultivation_reward": loser_cultivation_reward,
        "challenger_cultivation_reward": winner_cultivation_reward if winner_tg == actor_tg else loser_cultivation_reward,
        "defender_cultivation_reward": loser_cultivation_reward if winner_tg == actor_tg else winner_cultivation_reward,
    }


def finalize_group_arena(arena_id: int, *, force: bool = False) -> dict[str, Any] | None:
    arena_id_value = int(arena_id)
    if arena_id_value <= 0:
        return None

    with Session() as session:
        arena = (
            session.query(XiuxianArena)
            .filter(XiuxianArena.id == arena_id_value)
            .with_for_update()
            .first()
        )
        if arena is None:
            return None
        if str(arena.status or "") != "active":
            return {"result": "noop", "arena": serialize_arena(arena), "achievement_unlocks": []}
        if not force and arena.end_at > utcnow():
            raise ValueError("擂台尚未结束。")
        if arena.battle_in_progress:
            return {"result": "busy", "arena": serialize_arena(arena), "achievement_unlocks": []}

        now = utcnow()
        arena.status = "finished"
        arena.completed_at = now
        arena.updated_at = now
        arena.current_challenger_tg = None
        arena.current_challenger_display_name = None

        arena_stage = normalize_realm_stage(arena.realm_stage or FIRST_REALM_STAGE)
        champion = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(arena.champion_tg or 0)).with_for_update().first()
        if (
            champion is None
            or not champion.consented
            or champion.death_at is not None
            or is_profile_secluded(champion)
            or _profile_realm_stage_only(champion) != arena_stage
        ):
            arena.latest_result_summary = arena.latest_result_summary or f"擂台期满，但最终已无符合 {arena_stage} 境界要求的擂主可领取奖励。"
            session.commit()
            return {
                "result": "finished_no_reward",
                "arena": serialize_arena(arena),
                "champion_tg": int(arena.champion_tg or 0) or None,
                "champion_name": str(arena.champion_display_name or "").strip(),
                "achievement_unlocks": [],
            }

        reward = _arena_reward_values(champion, arena)
        stage = normalize_realm_stage(champion.realm_stage or FIRST_REALM_STAGE)
        layer, _, upgraded_layers, remaining = _settle_profile_cultivation(champion, reward["cultivation_reward"])
        if int(reward.get("stone_reward") or 0) > 0:
            apply_spiritual_stone_delta(
                session,
                int(champion.tg or 0),
                int(reward["stone_reward"]),
                action_text="擂台期满奖励",
                allow_dead=False,
                apply_tribute=True,
            )
        champion.updated_at = now
        arena.latest_result_summary = (
            f"{_profile_display_label(champion, '擂主')} 守到擂台落幕，"
            f"获得期满补偿：灵石 +{int(reward['stone_reward'])}，修为 +{int(reward['cultivation_reward'])}。"
        )
        session.commit()
        arena_payload = serialize_arena(arena)
        champion_name = _profile_display_label(champion, "擂主")
        champion_tg = int(champion.tg or 0)

    create_journal(
        champion_tg,
        "arena",
        "擂台结算",
        f"擂台落幕，获得期满补偿：灵石 +{int(reward['stone_reward'])}，修为 +{int(reward['cultivation_reward'])}。",
    )
    achievement_unlocks = record_arena_metrics(champion_tg, final_win=1)
    return {
        "result": "finished",
        "arena": arena_payload,
        "champion_tg": champion_tg,
        "champion_name": champion_name,
        "champion_stage": stage,
        "champion_layer": layer,
        "defense_success_count": max(int(arena_payload.get("defense_success_count") or 0), 0),
        "challenge_count": max(int(arena_payload.get("challenge_count") or 0), 0),
        "stone_reward": reward["stone_reward"],
        "cultivation_reward": reward["cultivation_reward"],
        "fortune_used": reward["fortune"],
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "achievement_unlocks": achievement_unlocks,
    }


def generate_shop_name(first_name: str) -> str:
    return PERSONAL_SHOP_NAME


def format_duel_settlement_text(
    result: dict[str, Any],
    bet_settlement: dict[str, Any] | None = None,
    page: int = 1,
    page_size: int = 10,
) -> str:
    challenger = result["challenger"]["profile"]
    defender = result["defender"]["profile"]
    duel_mode = _normalize_duel_mode(result.get("duel_mode"))
    winner_profile = challenger if int(result["winner_tg"]) == int(challenger["tg"]) else defender
    loser_profile = defender if int(result["loser_tg"]) == int(defender["tg"]) else challenger
    winner_name = _duel_md_escape(_duel_display_name(winner_profile))
    loser_name = _duel_md_escape(_duel_display_name(loser_profile))
    lines = [
        {
            "standard": "⚖️ **斗法已结算**",
            "master": "⛓️ **炉鼎对决已结算**",
            "death": "☠️ **生死斗已结算**",
        }.get(duel_mode, "⚖️ **斗法已结算**"),
        f"🏆 胜者：{winner_name}",
        f"💥 败者：{loser_name}",
        f"📝 战报：{_duel_md_escape(result['summary'])}",
    ]
    mode_outcome = result.get("mode_outcome") or {}
    if mode_outcome:
        lines.append("")
        if mode_outcome.get("kind") == "subjugated":
            lines.append(f"⛓️ 炉鼎结果：{winner_name} 收下 {loser_name} 为炉鼎。")
        elif mode_outcome.get("kind") == "break_free":
            lines.append(f"🕊️ 脱离结果：{winner_name} 斩断炉鼎印记，重获自由。")
        elif mode_outcome.get("kind") == "master_defended":
            lines.append(f"🔒 脱离结果：{winner_name} 守住炉鼎印记，{loser_name} 需等待下一次强制挑战。")
        elif mode_outcome.get("kind") == "death":
            lines.append(f"☠️ 生死结果：{winner_name} 继承了 {loser_name} 的全部遗产，{loser_name} 已身死道消。")

    battle_log = list(result.get("battle_log") or [])
    if battle_log:
        lines.extend(["", f"⏱️ 回合：`{int(result.get('round_count') or 0)}`"])

    stake = int(result.get("stake") or 0)
    if stake > 0:
        lines.extend(
            [
                "",
                "💰 **赌斗盈亏**",
                f"• {winner_name}：`+{stake}` 灵石",
                f"• {loser_name}：`-{stake}` 灵石",
            ]
        )

    plunder_percent = int(result.get("plunder_percent") or 0)
    if plunder_percent > 0:
        lines.extend(
            [
                "",
                "🪙 **胜者掠夺**",
                f"• 额外掠夺：`{int(result.get('plunder_amount') or 0)}` 灵石",
                f"• 掠夺比例：`{plunder_percent}%`",
            ]
        )

    artifact_plunder = result.get("artifact_plunder") or {}
    artifact_payload = artifact_plunder.get("artifact") or {}
    if artifact_payload:
        lines.extend(
            [
                "",
                "🗡️ **法宝掠夺**",
                f"• 掠夺结果：{winner_name} 夺取了 {loser_name} 的 {_duel_md_escape(artifact_payload.get('name', '未知法宝'))}",
                f"• 触发概率：`{artifact_plunder.get('chance', 0)}%`",
            ]
        )

    winner_growth = [
        item for item in (result.get("winner_attribute_growth") or [])
        if int(item.get("value") or 0) > 0
    ]
    if winner_growth:
        lines.extend(
            [
                "",
                "🌱 **斗法感悟**",
                f"• {winner_name} 在鏖战后额外提升 " + "、".join(
                    f"{_duel_md_escape(item.get('label', item.get('key', '属性')))} +{int(item.get('value') or 0)}"
                    for item in winner_growth
                ),
            ]
        )

    rows = list((bet_settlement or {}).get("entries") or [])
    page_size = max(int(page_size or 10), 1)
    total_pages = max(ceil(len(rows) / page_size), 1)
    current_page = min(max(int(page or 1), 1), total_pages)
    start = (current_page - 1) * page_size
    page_rows = rows[start : start + page_size]
    side_label = {
        "challenger": "挑战者",
        "defender": "应战者",
    }
    lines.append("")
    lines.append("🎯 **押注结算**")
    if not rows:
        lines.append("📭 暂无道友参与押注。")
    else:
        header = "📈 按净收益从高到低："
        if total_pages > 1:
            header += f" 第 {current_page}/{total_pages} 页"
        lines.append(header)
        for index, row in enumerate(page_rows, start=start + 1):
            bettor_name = _duel_md_escape(row["name"])
            if row.get("result") == "win":
                lines.append(
                    f"{index}. {bettor_name} ｜ 押中{side_label.get(row.get('side'), '胜方')} ｜ 下注 `{row['bet_amount']}` ｜ 净赚 `{row['net_profit']}` ｜ 返还 `{row['amount']}`"
                )
            else:
                lines.append(
                    f"{index}. {bettor_name} ｜ 押错{side_label.get(row.get('side'), '败方')} ｜ 下注 `{row['bet_amount']}` ｜ 净亏 `{abs(int(row.get('net_profit') or 0))}`"
                )

    lines.extend(
        [
            "",
            "✨ 愿胜者道心愈坚、再攀一层；愿败者锋芒不折、来日再战。",
            "🍀 也愿诸位观战押注的道友财运常在、仙途长青。",
        ]
    )
    return "\n".join(lines)


def generate_duel_preview_text(duel: dict[str, Any], stake: int = 0, duel_mode: str = "standard") -> str:
    mode = _normalize_duel_mode(duel_mode or duel.get("duel_mode"))
    title = {
        "standard": "⚔️ **斗法邀请**",
        "master": "⛓️ **炉鼎对决名帖**",
        "death": "☠️ **生死斗血契**",
    }.get(mode, "⚔️ **斗法邀请**")
    return format_duel_matchup_text(duel, stake=stake, title=title, duel_mode=mode)


from bot.plugins.xiuxian_game.features.pills import (  # noqa: E402
    pill_effect_summary as _pill_effect_summary,
    pill_usage_reason as _pill_usage_reason,
    resolve_pill_effects as resolve_pill_effects,
)
from bot.plugins.xiuxian_game.features.retreat import (  # noqa: E402
    ensure_not_in_retreat as ensure_not_in_retreat,
    finish_retreat_for_user as finish_retreat_for_user,
    is_retreating as _is_retreating,
    settle_retreat_progress as _settle_retreat_progress,
    start_retreat_for_user as start_retreat_for_user,
)
