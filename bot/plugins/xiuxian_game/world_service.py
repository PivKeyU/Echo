"""修仙世界玩法服务。

这里保留历史兼容出口。
后续新增或维护优先落到 `features/` 下的对应世界玩法文件，再由这里兼容导出。
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    DEFAULT_SETTINGS,
    DUEL_MODE_LABELS,
    QUALITY_LABEL_LEVELS,
    SECT_ROLE_LABELS,
    SECT_ROLE_PRESETS,
    _marriage_partner_tg,
    apply_spiritual_stone_delta,
    assert_artifact_receivable_by_user,
    assert_currency_operation_allowed,
    assert_profile_alive,
    XiuxianArtifactInventory,
    XiuxianEquippedArtifact,
    XiuxianPillInventory,
    XiuxianProfile,
    XiuxianRecipe,
    XiuxianUserRecipe,
    XiuxianUserTechnique,
    XiuxianRecipeIngredient,
    XiuxianSect,
    XiuxianSectRole,
    XiuxianSectTreasuryItem,
    XiuxianTask,
    XiuxianTaskClaim,
    XiuxianMaterialInventory,
    XiuxianTalismanInventory,
    XiuxianExploration,
    XiuxianScene,
    XiuxianSceneDrop,
    XiuxianRedEnvelope,
    XiuxianRedEnvelopeClaim,
    XiuxianDuelBetPool,
    XiuxianDuelBet,
    create_recipe,
    create_scene,
    create_scene_drop,
    create_sect,
    create_task,
    create_journal,
    get_artifact,
    get_emby_name_map,
    get_material,
    get_pill,
    get_profile,
    get_recipe,
    get_red_envelope,
    get_scene,
    get_sect,
    get_technique,
    get_talisman,
    get_user_achievement_progress_map,
    get_xiuxian_settings,
    get_active_duel_lock,
    grant_artifact_to_user,
    grant_material_to_user,
    grant_pill_to_user,
    grant_recipe_to_user,
    grant_talisman_to_user,
    grant_technique_to_user,
    grant_duplicate_knowledge_compensation_in_session,
    consume_user_materials_in_session,
    _queue_catalog_cache_invalidation,
    _queue_user_view_cache_invalidation,
    list_achievements,
    list_recipe_ingredients,
    list_recipes,
    list_recent_journals,
    list_red_envelope_claims,
    list_boss_configs,
    list_scene_drops,
    list_scenes,
    list_shop_items,
    list_sect_treasury_items,
    list_equipped_artifacts,
    list_slave_profiles,
    list_sect_roles,
    list_sects,
    list_tasks,
    list_techniques,
    list_user_materials,
    list_user_recipes,
    list_user_techniques,
    plunder_random_artifact_to_user,
    realm_index,
    patch_sect,
    replace_recipe_ingredients,
    replace_sect_roles,
    serialize_exploration,
    serialize_datetime,
    serialize_material,
    serialize_profile,
    serialize_recipe,
    serialize_red_envelope,
    serialize_scene,
    serialize_sect,
    serialize_technique,
    serialize_talisman,
    serialize_task,
    sync_title_by_name,
    grant_title_to_user,
    upsert_profile,
    utcnow,
)
from bot.plugins.xiuxian_game.cache import CATALOG_TTL, load_multi_versioned_json
from bot.plugins.xiuxian_game.probability import adjust_probability_percent, roll_probability_percent
from bot.plugins.xiuxian_game.achievement_service import (
    ACHIEVEMENT_METRIC_LABELS,
    record_achievement_progress,
    record_craft_metrics,
    record_exploration_metrics,
    record_gift_metrics,
    record_red_envelope_metrics,
    record_robbery_metrics,
)


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


RARITY_LEVEL_MAP = {
    **QUALITY_LABEL_LEVELS,
    "黄品": 2,
    "玄品": 3,
    "地品": 4,
    "天品": 5,
}

SECT_ENTRY_TECHNIQUES = {
    "太玄剑宗": "太玄剑经",
    "药王谷": "青木长生诀",
    "天机阁": "天机观星术",
    "血煞魔宫": "血煞战典",
    "幽冥鬼府": "幽冥夜行录",
    "万毒崖": "万毒归元经",
    "星罗海阁": "星罗潮生诀",
    "灵傀山": "灵傀百炼篇",
    "栖凰山": "栖凰离火录",
}
DUEL_BET_PREVIEW_CACHE_TTL_SECONDS = 20.0
DUEL_BET_PREVIEW_CACHE: dict[int, dict[str, Any]] = {}
ITEM_SOURCE_VERSION_GROUPS = (
    ("settings",),
    ("catalog", "achievements"),
    ("catalog", "recipes"),
    ("catalog", "scenes"),
    ("catalog", "shop-items"),
    ("catalog", "tasks"),
    ("catalog", "bosses"),
)
BOSS_LOOT_SOURCE_FIELDS = (
    ("loot_pills_json", "pill"),
    ("loot_materials_json", "material"),
    ("loot_artifacts_json", "artifact"),
    ("loot_talismans_json", "talisman"),
    ("loot_recipes_json", "recipe"),
    ("loot_techniques_json", "technique"),
)
SECT_ATTENDANCE_METHOD_LABELS = {
    "attendance": "宗门签到",
    "teach": "传功",
    "donate": "捐赠宝库",
}
SECT_DAILY_ATTENDANCE_CONTRIBUTION = 4
SECT_PROMOTION_ROLE_ORDER = [
    "outer_disciple",
    "inner_disciple",
    "outer_deacon",
    "inner_deacon",
    "core",
    "elder",
]
SECT_PROMOTION_THRESHOLDS = {
    "outer_disciple": 0,
    "inner_disciple": 12,
    "outer_deacon": 36,
    "inner_deacon": 72,
    "core": 120,
    "elder": 180,
}
SECT_DONATION_KIND_SCORE = {
    "material": 0,
    "pill": 1,
    "talisman": 1,
    "artifact": 2,
}
ITEM_CONTRIBUTION_BONUS_FIELDS = (
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
    "breakthrough_bonus",
)
TASK_REWARD_SCALE_MODES = {"fixed", "realm"}
METRIC_TASK_ALLOWED_KEYS = set(ACHIEVEMENT_METRIC_LABELS.keys())


def _is_active_spouse_pair(session: Session, actor_tg: int, target_tg: int) -> bool:
    actor_id = int(actor_tg or 0)
    target_id = int(target_tg or 0)
    if actor_id <= 0 or target_id <= 0 or actor_id == target_id:
        return False
    return int(_marriage_partner_tg(session, actor_id, for_update=True) or 0) == target_id


def _sect_entry_technique_payload(sect_name: str) -> dict[str, Any] | None:
    technique_name = str(SECT_ENTRY_TECHNIQUES.get(sect_name) or "").strip()
    if not technique_name:
        return None
    for row in list_techniques(enabled_only=True):
        if str(row.get("name") or "").strip() == technique_name:
            return row
    return None


def china_now():
    return utcnow() + timedelta(hours=8)


def china_day_key() -> str:
    return china_now().strftime("%Y-%m-%d")


def _china_day_key_for(value: datetime | None) -> str:
    normalized = _normalize_comparable_datetime(value)
    if normalized is None:
        return ""
    return (normalized + timedelta(hours=8)).strftime("%Y-%m-%d")


def _sect_attendance_done_today(profile: XiuxianProfile | dict[str, Any] | None) -> bool:
    if profile is None:
        return False
    if isinstance(profile, dict):
        attendance_method = str(profile.get("last_sect_attendance_method") or "").strip()
        last_attendance_at = _parse_optional_datetime(str(profile.get("last_sect_attendance_at") or "") or None)
    else:
        attendance_method = str(getattr(profile, "last_sect_attendance_method", "") or "").strip()
        last_attendance_at = getattr(profile, "last_sect_attendance_at", None)
    if attendance_method != "attendance":
        return False
    return bool(last_attendance_at and _china_day_key_for(last_attendance_at) == china_day_key())


def _count_item_bonus_lines(item: dict[str, Any] | None) -> int:
    payload = item or {}
    bonus_count = sum(1 for field in ITEM_CONTRIBUTION_BONUS_FIELDS if int(payload.get(field) or 0) != 0)
    if int(payload.get("effect_value") or 0) > 0:
        bonus_count += 1
    if bool(payload.get("unique_item")):
        bonus_count += 1
    return bonus_count


def _item_contribution_score(item_kind: str, item: dict[str, Any] | None, quantity: int) -> int:
    amount = max(int(quantity or 0), 1)
    quality = max(_quality_from_item(item_kind, item), 1)
    bonus_lines = min(_count_item_bonus_lines(item), 6)
    kind_score = SECT_DONATION_KIND_SCORE.get(str(item_kind or "").strip(), 0)
    score = ((quality + kind_score) * min(amount, 6) + bonus_lines) // 3
    if bool((item or {}).get("unique_item")):
        score += 2
    return max(min(score, 18), 1)


def _teach_contribution_score(cultivation_amount: int) -> int:
    amount = max(int(cultivation_amount or 0), 0)
    return max(min(amount // 2000, 10), 1)


def _apply_sect_contribution_gain(
    profile: XiuxianProfile,
    roles: list[dict[str, Any]],
    contribution_gain: int,
) -> tuple[str, str, int]:
    before_role_key = str(profile.sect_role_key or "").strip() or "outer_disciple"
    new_contribution = max(int(profile.sect_contribution or 0), 0) + max(int(contribution_gain or 0), 0)
    target_role = _sect_target_role_by_contribution(roles, new_contribution)
    next_role_key = before_role_key
    if target_role is not None and _sect_role_rank(target_role.get("role_key")) > _sect_role_rank(before_role_key):
        next_role_key = str(target_role.get("role_key") or before_role_key)
    profile.sect_contribution = new_contribution
    profile.sect_role_key = next_role_key
    return before_role_key, next_role_key, new_contribution


def _sect_role_rank(role_key: str | None) -> int:
    try:
        return SECT_PROMOTION_ROLE_ORDER.index(str(role_key or "").strip())
    except ValueError:
        return -1


def _sect_target_role_by_contribution(sect_roles: list[dict[str, Any]], contribution: int) -> dict[str, Any] | None:
    role_map = {
        str(role.get("role_key") or "").strip(): role
        for role in (sect_roles or [])
        if str(role.get("role_key") or "").strip()
    }
    target = role_map.get("outer_disciple")
    for role_key in SECT_PROMOTION_ROLE_ORDER:
        role = role_map.get(role_key)
        threshold = int(SECT_PROMOTION_THRESHOLDS.get(role_key, 0) or 0)
        if role is not None and int(contribution or 0) >= threshold:
            target = role
    return target


def _sect_promotion_preview(
    sect_roles: list[dict[str, Any]],
    current_role_key: str | None,
    contribution: int,
) -> dict[str, Any] | None:
    current_rank = _sect_role_rank(current_role_key)
    if current_rank < 0:
        return None
    role_map = {
        str(role.get("role_key") or "").strip(): role
        for role in (sect_roles or [])
        if str(role.get("role_key") or "").strip()
    }
    for role_key in SECT_PROMOTION_ROLE_ORDER[current_rank + 1 :]:
        role = role_map.get(role_key)
        if role is None:
            continue
        threshold = int(SECT_PROMOTION_THRESHOLDS.get(role_key, 0) or 0)
        remaining = max(threshold - int(contribution or 0), 0)
        return {
            "current_role_key": current_role_key,
            "current_role_name": SECT_ROLE_LABELS.get(str(current_role_key or ""), current_role_key),
            "next_role_key": role_key,
            "next_role_name": role.get("role_name") or SECT_ROLE_LABELS.get(role_key, role_key),
            "next_threshold": threshold,
            "remaining_contribution": remaining,
            "ready": remaining <= 0,
        }
    return None


def _grant_sect_role_title(sect: dict[str, Any], role: dict[str, Any]) -> dict[str, Any]:
    sect_name = str((sect or {}).get("name") or "宗门").strip() or "宗门"
    role_name = str((role or {}).get("role_name") or "门下弟子").strip() or "门下弟子"
    return sync_title_by_name(
        name=f"{sect_name}{role_name}",
        description=f"{sect_name}身份称号：{role_name}",
        enabled=True,
    )


def _maybe_promote_sect_member(
    tg: int,
    sect: dict[str, Any],
    before_role_key: str | None,
    after_role_key: str | None,
) -> dict[str, Any] | None:
    previous_rank = _sect_role_rank(before_role_key)
    next_rank = _sect_role_rank(after_role_key)
    if next_rank < 0 or next_rank <= previous_rank:
        return None
    role = get_sect_role_payload(int(sect.get("id") or 0), after_role_key)
    if role is None:
        return None
    title = _grant_sect_role_title(sect, role)
    grant_title_to_user(
        tg,
        int(title["id"]),
        source="sect",
        obtained_note=f"宗门贡献达标，晋升为{role.get('role_name') or after_role_key}",
        auto_equip_if_empty=True,
    )
    create_journal(
        tg,
        "sect",
        "宗门晋升",
        f"因宗门贡献达标，职位由【{SECT_ROLE_LABELS.get(str(before_role_key or ''), before_role_key or '门下弟子')}】晋升为【{role.get('role_name') or after_role_key}】。",
    )
    return {"role": role, "title": title}


def _task_reward_scale_factor(profile: dict[str, Any] | None, scale_mode: str | None) -> float:
    if str(scale_mode or "fixed").strip() != "realm":
        return 1.0
    payload = profile or {}
    stage_index = max(realm_index(payload.get("realm_stage")), 0)
    layer = max(int(payload.get("realm_layer") or 1), 1)
    return min(1.0 + stage_index * 0.14 + (layer - 1) * 0.03, 4.2)


def _scaled_task_reward_values(task: XiuxianTask | dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(task, dict):
        reward_stone = max(int(task.get("reward_stone") or 0), 0)
        reward_cultivation = max(int(task.get("reward_cultivation") or 0), 0)
        scale_mode = str(task.get("reward_scale_mode") or "fixed").strip() or "fixed"
    else:
        reward_stone = max(int(getattr(task, "reward_stone", 0) or 0), 0)
        reward_cultivation = max(int(getattr(task, "reward_cultivation", 0) or 0), 0)
        scale_mode = str(getattr(task, "reward_scale_mode", "fixed") or "fixed").strip() or "fixed"
    factor = _task_reward_scale_factor(profile, scale_mode)
    stone_value = int(round(reward_stone * factor)) if reward_stone > 0 else 0
    cultivation_value = int(round(reward_cultivation * factor)) if reward_cultivation > 0 else 0
    return {
        "reward_stone": stone_value,
        "reward_cultivation": cultivation_value,
        "reward_scale_mode": scale_mode,
        "reward_scale_factor": round(factor, 2),
    }


def _metric_task_progress_payload(
    task: dict[str, Any] | XiuxianTask,
    claim: dict[str, Any] | None,
    progress_map: dict[str, int],
) -> dict[str, Any]:
    if isinstance(task, dict):
        metric_key = str(task.get("requirement_metric_key") or "").strip()
        target = max(int(task.get("requirement_metric_target") or 0), 0)
    else:
        metric_key = str(getattr(task, "requirement_metric_key", "") or "").strip()
        target = max(int(getattr(task, "requirement_metric_target", 0) or 0), 0)
    current_value = max(int(progress_map.get(metric_key, 0) or 0), 0)
    start_value = max(int((claim or {}).get("metric_start_value") or current_value), 0)
    progress_value = max(current_value - start_value, 0) if claim else 0
    return {
        "metric_key": metric_key,
        "metric_label": ACHIEVEMENT_METRIC_LABELS.get(metric_key, metric_key or "计数指标"),
        "metric_current_value": current_value,
        "metric_start_value": start_value if claim else current_value,
        "metric_progress_value": progress_value,
        "metric_target": target,
        "metric_claimable": bool(claim and target > 0 and progress_value >= target),
    }


def _require_alive_profile_data(tg: int, action_text: str) -> tuple[XiuxianProfile, dict[str, Any]]:
    profile_obj = get_profile(tg, create=False)
    if profile_obj is None or not profile_obj.consented:
        raise ValueError("你尚未踏入仙途，道基未立")
    assert_profile_alive(profile_obj, action_text)
    return profile_obj, serialize_profile(profile_obj)


def _full_profile_bundle(tg: int) -> dict[str, Any]:
    from bot.plugins.xiuxian_game.service import serialize_full_profile

    return serialize_full_profile(tg)


def floor_div(left: int, right: int) -> int:
    if right <= 0:
        return 0
    return int(left // right)


def _zero_effects() -> dict[str, int]:
    return {
        "attack_bonus": 0,
        "defense_bonus": 0,
        "bone_bonus": 0,
        "comprehension_bonus": 0,
        "divine_sense_bonus": 0,
        "fortune_bonus": 0,
        "qi_blood_bonus": 0,
        "true_yuan_bonus": 0,
        "body_movement_bonus": 0,
        "duel_rate_bonus": 0,
        "cultivation_bonus": 0,
        "breakthrough_bonus": 0,
    }


def get_sect_role_payload(sect_id: int | None, role_key: str | None) -> dict[str, Any] | None:
    if not sect_id or not role_key:
        return None
    for role in list_sect_roles(int(sect_id)):
        if role["role_key"] == role_key:
            return role
    return None


def get_sect_effects(profile_data: dict[str, Any] | None) -> dict[str, int]:
    if not profile_data:
        return _zero_effects()
    sect = serialize_sect(get_sect(int(profile_data.get("sect_id") or 0))) if profile_data.get("sect_id") else None
    role = get_sect_role_payload(profile_data.get("sect_id"), profile_data.get("sect_role_key"))
    effects = _zero_effects()
    if sect:
        effects["attack_bonus"] += int(sect.get("attack_bonus", 0) or 0)
        effects["defense_bonus"] += int(sect.get("defense_bonus", 0) or 0)
        effects["duel_rate_bonus"] += int(sect.get("duel_rate_bonus", 0) or 0)
        effects["cultivation_bonus"] += int(sect.get("cultivation_bonus", 0) or 0)
        effects["fortune_bonus"] += int(sect.get("fortune_bonus", 0) or 0)
        effects["body_movement_bonus"] += int(sect.get("body_movement_bonus", 0) or 0)
        effects["pill_poison_resist"] = float(sect.get("pill_poison_resist") or 0.0)
        effects["pill_poison_cap_bonus"] = int(sect.get("pill_poison_cap_bonus") or 0)
        effects["farm_growth_speed"] = float(sect.get("farm_growth_speed") or 0.0)
        effects["explore_drop_rate"] = int(sect.get("explore_drop_rate") or 0)
        effects["craft_success_rate"] = int(sect.get("craft_success_rate") or 0)
        effects["death_penalty_reduce"] = float(sect.get("death_penalty_reduce") or 0.0)
    if role:
        effects["attack_bonus"] += int(role.get("attack_bonus", 0) or 0)
        effects["defense_bonus"] += int(role.get("defense_bonus", 0) or 0)
        effects["duel_rate_bonus"] += int(role.get("duel_rate_bonus", 0) or 0)
        effects["cultivation_bonus"] += int(role.get("cultivation_bonus", 0) or 0)
    return effects


def _default_role_payloads() -> list[dict[str, Any]]:
    rows = []
    for role_key, role_name, sort_order in SECT_ROLE_PRESETS:
        salary = 0
        cultivation_bonus = 0
        attack_bonus = 0
        defense_bonus = 0
        if role_key == "outer_disciple":
            salary = 50
        elif role_key == "inner_disciple":
            salary = 120
            cultivation_bonus = 2
        elif role_key == "outer_deacon":
            salary = 200
            attack_bonus = 3
            defense_bonus = 3
        elif role_key == "inner_deacon":
            salary = 350
            cultivation_bonus = 4
            attack_bonus = 5
            defense_bonus = 5
        elif role_key == "core":
            salary = 600
            cultivation_bonus = 7
            attack_bonus = 8
            defense_bonus = 8
            duel_rate_bonus = 2
        elif role_key == "elder":
            salary = 1000
            cultivation_bonus = 12
            attack_bonus = 12
            defense_bonus = 12
            duel_rate_bonus = 5
        elif role_key == "leader":
            salary = 2000
            cultivation_bonus = 18
            attack_bonus = 18
            defense_bonus = 18
            duel_rate_bonus = 8
        rows.append(
            {
                "role_key": role_key,
                "role_name": role_name,
                "attack_bonus": attack_bonus,
                "defense_bonus": defense_bonus,
                "duel_rate_bonus": duel_rate_bonus if role_key in {"core", "elder", "leader"} else 0,
                "cultivation_bonus": cultivation_bonus,
                "monthly_salary": salary,
                "can_publish_tasks": role_key in {"leader", "elder", "inner_deacon", "outer_deacon"},
                "sort_order": sort_order,
            }
        )
    return rows


def create_sect_with_roles(
    *,
    name: str,
    description: str = "",
    image_url: str = "",
    camp: str = "orthodox",
    min_realm_stage: str | None = None,
    min_realm_layer: int = 1,
    min_stone: int = 0,
    min_bone: int = 0,
    min_comprehension: int = 0,
    min_divine_sense: int = 0,
    min_fortune: int = 0,
    min_willpower: int = 0,
    min_charisma: int = 0,
    min_karma: int = 0,
    min_body_movement: int = 0,
    min_combat_power: int = 0,
    attack_bonus: int = 0,
    defense_bonus: int = 0,
    duel_rate_bonus: int = 0,
    cultivation_bonus: int = 0,
    fortune_bonus: int = 0,
    body_movement_bonus: int = 0,
    pill_poison_resist: float = 0.0,
    pill_poison_cap_bonus: int = 0,
    farm_growth_speed: float = 0.0,
    explore_drop_rate: int = 0,
    craft_success_rate: int = 0,
    death_penalty_reduce: float = 0.0,
    salary_min_stay_days: int | None = None,
    entry_hint: str = "",
    roles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sect = create_sect(
        name=name,
        description=description,
        image_url=image_url,
        camp=camp,
        min_realm_stage=min_realm_stage,
        min_realm_layer=max(int(min_realm_layer or 1), 1),
        min_stone=max(int(min_stone or 0), 0),
        min_bone=max(int(min_bone or 0), 0),
        min_comprehension=max(int(min_comprehension or 0), 0),
        min_divine_sense=max(int(min_divine_sense or 0), 0),
        min_fortune=max(int(min_fortune or 0), 0),
        min_willpower=max(int(min_willpower or 0), 0),
        min_charisma=max(int(min_charisma or 0), 0),
        min_karma=max(int(min_karma or 0), 0),
        min_body_movement=max(int(min_body_movement or 0), 0),
        min_combat_power=max(int(min_combat_power or 0), 0),
        attack_bonus=int(attack_bonus or 0),
        defense_bonus=int(defense_bonus or 0),
        duel_rate_bonus=int(duel_rate_bonus or 0),
        cultivation_bonus=int(cultivation_bonus or 0),
        fortune_bonus=int(fortune_bonus or 0),
        body_movement_bonus=int(body_movement_bonus or 0),
        pill_poison_resist=float(pill_poison_resist or 0.0),
        pill_poison_cap_bonus=max(int(pill_poison_cap_bonus or 0), 0),
        farm_growth_speed=float(farm_growth_speed or 0.0),
        explore_drop_rate=max(int(explore_drop_rate or 0), 0),
        craft_success_rate=max(int(craft_success_rate or 0), 0),
        death_penalty_reduce=float(death_penalty_reduce or 0.0),
        salary_min_stay_days=max(int(salary_min_stay_days or _sect_salary_min_stay_days()), 1),
        entry_hint=entry_hint,
        enabled=True,
    )
    role_payloads = roles or _default_role_payloads()
    sanitized = []
    for index, role in enumerate(role_payloads, start=1):
        role_key = str(role.get("role_key") or "").strip() or f"role_{index}"
        sanitized.append(
            {
                "role_key": role_key,
                "role_name": str(role.get("role_name") or SECT_ROLE_LABELS.get(role_key, role_key)).strip(),
                "attack_bonus": int(role.get("attack_bonus", 0) or 0),
                "defense_bonus": int(role.get("defense_bonus", 0) or 0),
                "duel_rate_bonus": int(role.get("duel_rate_bonus", 0) or 0),
                "cultivation_bonus": int(role.get("cultivation_bonus", 0) or 0),
                "monthly_salary": int(role.get("monthly_salary", 0) or 0),
                "can_publish_tasks": bool(role.get("can_publish_tasks", False)),
                "sort_order": int(role.get("sort_order", index) or index),
            }
        )
    sect["roles"] = replace_sect_roles(sect["id"], sanitized)
    return sect


def sync_sect_with_roles_by_name(
    *,
    name: str,
    description: str = "",
    image_url: str = "",
    camp: str = "orthodox",
    min_realm_stage: str | None = None,
    min_realm_layer: int = 1,
    min_stone: int = 0,
    min_bone: int = 0,
    min_comprehension: int = 0,
    min_divine_sense: int = 0,
    min_fortune: int = 0,
    min_willpower: int = 0,
    min_charisma: int = 0,
    min_karma: int = 0,
    min_body_movement: int = 0,
    min_combat_power: int = 0,
    attack_bonus: int = 0,
    defense_bonus: int = 0,
    duel_rate_bonus: int = 0,
    cultivation_bonus: int = 0,
    fortune_bonus: int = 0,
    body_movement_bonus: int = 0,
    pill_poison_resist: float = 0.0,
    pill_poison_cap_bonus: int = 0,
    farm_growth_speed: float = 0.0,
    explore_drop_rate: int = 0,
    craft_success_rate: int = 0,
    death_penalty_reduce: float = 0.0,
    salary_min_stay_days: int | None = None,
    entry_hint: str = "",
    roles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing = next((row for row in list_sects(enabled_only=False) if row.get("name") == name), None)
    if existing is None:
        return create_sect_with_roles(
            name=name,
            description=description,
            image_url=image_url,
            camp=camp,
            min_realm_stage=min_realm_stage,
            min_realm_layer=min_realm_layer,
            min_stone=min_stone,
            min_bone=min_bone,
            min_comprehension=min_comprehension,
            min_divine_sense=min_divine_sense,
            min_fortune=min_fortune,
            min_willpower=min_willpower,
            min_charisma=min_charisma,
            min_karma=min_karma,
            min_body_movement=min_body_movement,
            min_combat_power=min_combat_power,
            attack_bonus=attack_bonus,
            defense_bonus=defense_bonus,
            duel_rate_bonus=duel_rate_bonus,
            cultivation_bonus=cultivation_bonus,
            fortune_bonus=fortune_bonus,
            body_movement_bonus=body_movement_bonus,
            pill_poison_resist=pill_poison_resist,
            pill_poison_cap_bonus=pill_poison_cap_bonus,
            farm_growth_speed=farm_growth_speed,
            explore_drop_rate=explore_drop_rate,
            craft_success_rate=craft_success_rate,
            death_penalty_reduce=death_penalty_reduce,
            salary_min_stay_days=salary_min_stay_days,
            entry_hint=entry_hint,
            roles=roles,
        )
    updated = patch_sect(
        int(existing["id"]),
        name=name,
        description=description,
        image_url=image_url,
        camp=camp,
        min_realm_stage=min_realm_stage,
        min_realm_layer=min_realm_layer,
        min_stone=min_stone,
        min_bone=min_bone,
        min_comprehension=min_comprehension,
        min_divine_sense=min_divine_sense,
        min_fortune=min_fortune,
        min_willpower=min_willpower,
        min_charisma=min_charisma,
        min_karma=min_karma,
        min_body_movement=min_body_movement,
        min_combat_power=min_combat_power,
        attack_bonus=attack_bonus,
        defense_bonus=defense_bonus,
        duel_rate_bonus=duel_rate_bonus,
        cultivation_bonus=cultivation_bonus,
        fortune_bonus=fortune_bonus,
        body_movement_bonus=body_movement_bonus,
        pill_poison_resist=pill_poison_resist,
        pill_poison_cap_bonus=pill_poison_cap_bonus,
        farm_growth_speed=farm_growth_speed,
        explore_drop_rate=explore_drop_rate,
        craft_success_rate=craft_success_rate,
        death_penalty_reduce=death_penalty_reduce,
        salary_min_stay_days=max(int(salary_min_stay_days or _sect_salary_min_stay_days(int(existing["id"]))), 1),
        entry_hint=entry_hint,
        enabled=True,
    ) or existing
    updated["roles"] = replace_sect_roles(int(existing["id"]), roles or _default_role_payloads())
    return updated


def _count_sect_members(sect_id: int) -> int:
    with Session() as session:
        return (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.sect_id == sect_id, XiuxianProfile.consented.is_(True))
            .count()
        )


def _parse_optional_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _normalize_comparable_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _format_remaining_delta(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes or not parts:
        parts.append(f"{minutes} 分钟")
    return "".join(parts[:2])


def _sect_salary_min_stay_days(sect_id: int | None = None) -> int:
    if sect_id:
        sect = serialize_sect(get_sect(int(sect_id)))
        if sect:
            return max(int(sect.get("salary_min_stay_days") or 0), 1)
    settings = get_xiuxian_settings()
    return max(int(settings.get("sect_salary_min_stay_days", DEFAULT_SETTINGS.get("sect_salary_min_stay_days", 30)) or 0), 1)


def _sect_betrayal_cooldown_days() -> int:
    settings = get_xiuxian_settings()
    return max(int(settings.get("sect_betrayal_cooldown_days", DEFAULT_SETTINGS.get("sect_betrayal_cooldown_days", 7)) or 0), 1)


def _sect_betrayal_stone_penalty(balance: int) -> int:
    settings = get_xiuxian_settings()
    current = max(int(balance or 0), 0)
    percent = max(int(settings.get("sect_betrayal_stone_percent", DEFAULT_SETTINGS.get("sect_betrayal_stone_percent", 10)) or 0), 0)
    minimum = max(int(settings.get("sect_betrayal_stone_min", DEFAULT_SETTINGS.get("sect_betrayal_stone_min", 20)) or 0), 0)
    maximum = max(int(settings.get("sect_betrayal_stone_max", DEFAULT_SETTINGS.get("sect_betrayal_stone_max", 300)) or 0), minimum)
    percent_penalty = (current * percent) // 100 if percent > 0 else 0
    return min(max(percent_penalty, minimum), maximum, current)


def _task_publish_day_window() -> tuple[datetime, datetime]:
    current = china_now()
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)
    return day_start, day_start + timedelta(days=1)


def _user_task_daily_limit() -> int:
    settings = get_xiuxian_settings()
    return max(int(settings.get("user_task_daily_limit", DEFAULT_SETTINGS.get("user_task_daily_limit", 3)) or 0), 0)


def _user_task_publish_count_today(tg: int, *, session: Session | None = None) -> int:
    day_start, day_end = _task_publish_day_window()
    owns_session = session is None
    active_session = session or Session()
    try:
        return int(
            active_session.query(XiuxianTask)
            .filter(
                XiuxianTask.owner_tg == int(tg),
                XiuxianTask.created_at >= day_start,
                XiuxianTask.created_at < day_end,
            )
            .count()
            or 0
        )
    finally:
        if owns_session:
            active_session.close()


def _scene_exploration_counts(tg: int) -> dict[int, int]:
    counts: dict[int, int] = {}
    with Session() as session:
        rows = session.query(XiuxianExploration.scene_id).filter(XiuxianExploration.tg == int(tg)).all()
    for row in rows:
        scene_id = int(getattr(row, "scene_id", row[0] if row else 0) or 0)
        if scene_id <= 0:
            continue
        counts[scene_id] = counts.get(scene_id, 0) + 1
    return counts


def _eligible_for_sect(profile_data: dict[str, Any], sect: dict[str, Any], combat_power: int = 0) -> tuple[bool, str]:
    effective_stats = profile_data.get("effective_stats") if isinstance(profile_data.get("effective_stats"), dict) else {}

    def _stat_value(key: str) -> int:
        if key in effective_stats:
            return int(effective_stats.get(key) or 0)
        return int(profile_data.get(key) or 0)

    now = utcnow()
    betrayal_until = _normalize_comparable_datetime(_parse_optional_datetime(profile_data.get("sect_betrayal_until")))
    if betrayal_until and betrayal_until > now:
        return False, f"叛宗余罚未消，需再等 {_format_remaining_delta(betrayal_until - now)} 方可重投山门"
    if sect.get("min_realm_stage") and realm_index(profile_data.get("realm_stage")) < realm_index(sect.get("min_realm_stage")):
        return False, "境界不满足宗门要求"
    if profile_data.get("realm_stage") == sect.get("min_realm_stage") and int(profile_data.get("realm_layer") or 0) < int(sect.get("min_realm_layer") or 1):
        return False, "层数不满足宗门要求"
    if int(profile_data.get("spiritual_stone") or 0) < int(sect.get("min_stone") or 0):
        return False, "灵石不满足宗门要求"
    if _stat_value("bone") < int(sect.get("min_bone") or 0):
        return False, "根骨不满足宗门要求"
    if _stat_value("comprehension") < int(sect.get("min_comprehension") or 0):
        return False, "悟性不满足宗门要求"
    if _stat_value("divine_sense") < int(sect.get("min_divine_sense") or 0):
        return False, "神识不满足宗门要求"
    if _stat_value("fortune") < int(sect.get("min_fortune") or 0):
        return False, "机缘不满足宗门要求"
    if _stat_value("willpower") < int(sect.get("min_willpower") or 0):
        return False, "心志不满足宗门要求"
    if _stat_value("charisma") < int(sect.get("min_charisma") or 0):
        return False, "魅力不满足宗门要求"
    if _stat_value("karma") < int(sect.get("min_karma") or 0):
        return False, "因果不满足宗门要求"
    if _stat_value("body_movement") < int(sect.get("min_body_movement") or 0):
        return False, "身法不满足宗门要求"
    if combat_power < int(sect.get("min_combat_power") or 0):
        return False, "战力不满足宗门要求"
    return True, ""


def _repair_missing_sect_membership(tg: int, profile_data: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    profile = profile_data or serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("sect_id"):
        return profile, None
    sect = serialize_sect(get_sect(int(profile["sect_id"])))
    if sect is not None:
        return profile, sect
    upsert_profile(
        tg,
        sect_id=None,
        sect_role_key=None,
        sect_contribution=0,
        sect_joined_at=None,
        sect_betrayal_until=None,
        last_salary_claim_at=None,
    )
    create_journal(tg, "sect", "因果重理", f"旧日宗门契印（ID {int(profile.get('sect_id') or 0)}）已消散，天道已抹去残留的归属因果。")
    return serialize_profile(get_profile(tg, create=False)), None


def list_sects_for_user(tg: int) -> list[dict[str, Any]]:
    profile_obj = get_profile(tg, create=True)
    profile = serialize_profile(profile_obj)
    profile, _ = _repair_missing_sect_membership(tg, profile)
    combat_power = 0
    effective_stats: dict[str, Any] = {}
    if profile and profile.get("consented") and not profile.get("death_at"):
        from bot.plugins.xiuxian_game.service import serialize_full_profile

        bundle = serialize_full_profile(tg) or {}
        combat_power = int(bundle.get("combat_power") or 0)
        effective_stats = bundle.get("effective_stats") or {}
        profile = bundle.get("profile") or profile
        profile["effective_stats"] = effective_stats
    rows = []
    for sect in list_sects(enabled_only=True):
        sect["roles"] = list_sect_roles(sect["id"])
        sect["member_count"] = _count_sect_members(sect["id"])
        entry_technique = _sect_entry_technique_payload(str(sect.get("name") or ""))
        sect["entry_technique_name"] = (entry_technique or {}).get("name")
        sect["entry_technique_rarity"] = (entry_technique or {}).get("rarity")
        allowed, reason = _eligible_for_sect(profile, sect, combat_power=combat_power)
        sect["joinable"] = profile.get("sect_id") in {None, sect["id"]} and allowed
        sect["join_reason"] = "" if sect["joinable"] else reason or ("你已经加入其他宗门" if profile.get("sect_id") not in {None, sect["id"]} else "")
        rows.append(sect)
    return rows


def _get_sect_roster(sect_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.sect_id == sect_id, XiuxianProfile.consented.is_(True))
            .order_by(XiuxianProfile.updated_at.desc())
            .all()
        )
        return [serialize_profile(row) for row in rows]


def get_current_sect_bundle(tg: int) -> dict[str, Any] | None:
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("sect_id"):
        return None
    profile, sect = _repair_missing_sect_membership(tg, profile)
    if not profile or not profile.get("sect_id"):
        return None
    if sect is None:
        sect = serialize_sect(get_sect(int(profile["sect_id"])))
    if not sect:
        return None
    sect["roles"] = list_sect_roles(sect["id"])
    sect["roster"] = _get_sect_roster(sect["id"])
    sect["current_role"] = get_sect_role_payload(sect["id"], profile.get("sect_role_key"))
    attendance_method = str(profile.get("last_sect_attendance_method") or "").strip()
    attendance_last_at = profile.get("last_sect_attendance_at") if attendance_method == "attendance" else None
    sect["attendance"] = {
        "done_today": _sect_attendance_done_today(profile),
        "last_at": attendance_last_at,
        "last_method": attendance_method if attendance_method == "attendance" else None,
        "last_method_label": (
            SECT_ATTENDANCE_METHOD_LABELS.get(attendance_method, attendance_method)
            if attendance_method == "attendance"
            else None
        ),
    }
    sect["promotion_preview"] = _sect_promotion_preview(
        sect["roles"],
        str(profile.get("sect_role_key") or "").strip() or None,
        int(profile.get("sect_contribution") or 0),
    )
    entry_technique = _sect_entry_technique_payload(str(sect.get("name") or ""))
    sect["entry_technique_name"] = (entry_technique or {}).get("name")
    sect["entry_technique_rarity"] = (entry_technique or {}).get("rarity")
    treasury_items = []
    for row in list_sect_treasury_items(int(sect["id"])):
        item = _get_item_payload(str(row.get("item_kind") or ""), int(row.get("item_ref_id") or 0))
        row["item"] = item
        row["item_name"] = (item or {}).get("name") or row.get("item_kind_label") or row.get("item_kind") or "物品"
        row["quality_level"] = _quality_from_item(str(row.get("item_kind") or ""), item)
        treasury_items.append(row)
    treasury_items.sort(
        key=lambda item: (
            -int(item.get("quality_level") or 1),
            -int(item.get("quantity") or 0),
            str(item.get("item_name") or ""),
        )
    )
    sect["treasury_items"] = treasury_items
    sect["leave_preview"] = {
        "stone_penalty": _sect_betrayal_stone_penalty(int(profile.get("spiritual_stone") or 0)),
        "cooldown_days": _sect_betrayal_cooldown_days(),
    }
    sect["can_leave"] = True
    return sect


def join_sect_for_user(tg: int, sect_id: int) -> dict[str, Any]:
    _, profile = _require_alive_profile_data(tg, "加入宗门")
    profile, _ = _repair_missing_sect_membership(tg, profile)
    if profile.get("sect_id") and int(profile.get("sect_id")) == int(sect_id):
        raise ValueError("你已在该宗门门下，无需重复拜山。")
    if profile.get("sect_id") and int(profile.get("sect_id")) != int(sect_id):
        raise ValueError("你已加入其他宗门")
    sect = serialize_sect(get_sect(sect_id))
    if sect is None or not sect.get("enabled"):
        raise ValueError("宗门不存在")
    from bot.plugins.xiuxian_game.service import serialize_full_profile

    bundle = serialize_full_profile(tg) or {}
    full_profile = bundle.get("profile") or profile
    full_profile["effective_stats"] = bundle.get("effective_stats") or {}
    allowed, reason = _eligible_for_sect(full_profile, sect, combat_power=int(bundle.get("combat_power") or 0))
    if not allowed:
        raise ValueError(reason)
    upsert_profile(
        tg,
        sect_id=sect_id,
        sect_role_key="outer_disciple",
        sect_contribution=0,
        sect_joined_at=utcnow(),
        sect_betrayal_until=None,
        last_salary_claim_at=None,
        last_sect_attendance_at=None,
        last_sect_attendance_method=None,
    )
    entry_technique = _sect_entry_technique_payload(str(sect.get("name") or ""))
    if entry_technique and not any(int((row.get("technique") or {}).get("id") or 0) == int(entry_technique["id"]) for row in list_user_techniques(tg, enabled_only=False)):
        try:
            grant_technique_to_user(
                tg,
                int(entry_technique["id"]),
                source="sect",
                obtained_note=f"拜入{sect['name']}所得",
                auto_equip_if_empty=True,
            )
        except ValueError:
            pass
    create_journal(tg, "sect", "拜入山门", f"整顿衣冠，焚香三拜，正式拜入【{sect['name']}】门下，从此仙途有依。")
    return get_current_sect_bundle(tg)


def leave_sect_for_user(tg: int) -> dict[str, Any]:
    raw_profile = serialize_profile(get_profile(tg, create=False))
    if raw_profile and raw_profile.get("sect_id"):
        repaired_profile, sect = _repair_missing_sect_membership(tg, raw_profile)
        if sect is None and repaired_profile and not repaired_profile.get("sect_id"):
            previous_contribution = int(raw_profile.get("sect_contribution") or 0)
            return {
                "previous_sect": {
                    "id": int(raw_profile.get("sect_id") or 0),
                    "name": f"失效宗门#{int(raw_profile.get('sect_id') or 0)}",
                },
                "profile": repaired_profile,
                "repaired": True,
                "message": "原宗门记录已失效，系统已自动清理残留归属，你现在可以加入其他宗门。",
                "betrayal": {
                    "stone_penalty": 0,
                    "claimed_salary": False,
                    "contribution_cleared": previous_contribution,
                    "cooldown_until": None,
                    "cooldown_days": 0,
                },
            }
    current = get_current_sect_bundle(tg)
    if not current:
        raise ValueError("你当前并未加入宗门")
    updated_profile = None
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "叛出宗门")
        assert_currency_operation_allowed(tg, "叛出宗门", session=session, profile=profile)
        if not profile.sect_id:
            raise ValueError("你当前并未加入宗门")

        current_stone = max(int(profile.spiritual_stone or 0), 0)
        joined_at = _normalize_comparable_datetime(profile.sect_joined_at)
        last_salary_claim_at = _normalize_comparable_datetime(profile.last_salary_claim_at)
        claimed_salary = bool(last_salary_claim_at and (joined_at is None or last_salary_claim_at >= joined_at))
        penalty = _sect_betrayal_stone_penalty(current_stone) if claimed_salary else 0
        if current_stone < penalty:
            raise ValueError(f"叛出宗门需要缴纳 {penalty} 灵石供奉，你当前灵石不足。")
        cooldown_until = utcnow() + timedelta(days=_sect_betrayal_cooldown_days())
        previous_contribution = int(profile.sect_contribution or 0)
        if penalty > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -penalty,
                action_text="叛出宗门",
                allow_dead=False,
                apply_tribute=False,
            )
        update_time = utcnow()
        session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).update(
            {
                XiuxianProfile.sect_id: None,
                XiuxianProfile.sect_role_key: None,
                XiuxianProfile.sect_contribution: 0,
                XiuxianProfile.sect_joined_at: None,
                XiuxianProfile.sect_betrayal_until: cooldown_until,
                XiuxianProfile.last_salary_claim_at: None,
                XiuxianProfile.last_sect_attendance_at: None,
                XiuxianProfile.last_sect_attendance_method: None,
                XiuxianProfile.updated_at: update_time,
            },
            synchronize_session=False,
        )
        session.commit()
    updated_profile = serialize_profile(get_profile(tg, create=False))
    if updated_profile and updated_profile.get("sect_id"):
        raise ValueError("叛出宗门状态刷新失败，请稍后重试。")

    sect_name = (current or {}).get("name", "未知宗门")
    create_journal(
        tg,
        "sect",
        "背离山门",
        (
            f"斩断与【{sect_name}】的因果羁绊，被追回 {penalty} 灵石供奉，{previous_contribution} 点宗门贡献尽数归零，禁投山门至 {cooldown_until.isoformat()}。"
            if penalty > 0
            else f"自断与【{sect_name}】的宗门因果，未曾领取俸禄故未扣灵石，{previous_contribution} 点宗门贡献随风散去，禁投山门至 {cooldown_until.isoformat()}。"
        ),
    )
    return {
        "previous_sect": current,
        "profile": updated_profile,
        "betrayal": {
            "stone_penalty": penalty,
            "claimed_salary": claimed_salary,
            "contribution_cleared": previous_contribution,
            "cooldown_until": cooldown_until.isoformat(),
            "cooldown_days": _sect_betrayal_cooldown_days(),
        },
    }


def set_user_sect_role(tg: int, sect_id: int, role_key: str) -> dict[str, Any]:
    sect = serialize_sect(get_sect(sect_id))
    if sect is None or not sect.get("enabled"):
        raise ValueError("宗门不存在")
    role = get_sect_role_payload(sect_id, role_key)
    if role is None:
        raise ValueError("宗门职位不存在")
    profile_obj = get_profile(tg, create=False)
    if profile_obj is None or not profile_obj.consented:
        raise ValueError("目标用户尚未踏入仙途")
    assert_profile_alive(profile_obj, "调整宗门职位")
    profile_payload = {"sect_id": sect_id, "sect_role_key": role_key}
    if int(profile_obj.sect_id or 0) != int(sect_id):
        profile_payload["sect_joined_at"] = utcnow()
        profile_payload["sect_betrayal_until"] = None
        profile_payload["last_salary_claim_at"] = None
        profile_payload["last_sect_attendance_at"] = None
        profile_payload["last_sect_attendance_method"] = None
        profile_payload["sect_contribution"] = 0
    updated = upsert_profile(tg, **profile_payload)
    return {"profile": serialize_profile(updated), "role": role, "sect": sect}


def claim_sect_salary_for_user(tg: int) -> dict[str, Any]:
    profile_obj, _ = _require_alive_profile_data(tg, "领取宗门俸禄")
    assert_currency_operation_allowed(tg, "领取宗门俸禄", profile=profile_obj)
    role = get_sect_role_payload(profile_obj.sect_id, profile_obj.sect_role_key)
    if not role:
        raise ValueError("当前没有宗门俸禄可领取")
    now = utcnow()
    joined_at = _normalize_comparable_datetime(profile_obj.sect_joined_at)
    fallback_last_claim = _normalize_comparable_datetime(profile_obj.last_salary_claim_at)
    fallback_created_at = _normalize_comparable_datetime(profile_obj.created_at)
    joined_at = joined_at or fallback_last_claim or fallback_created_at or now
    last_claim = _normalize_comparable_datetime(profile_obj.last_salary_claim_at)
    if last_claim is None or last_claim < joined_at:
        min_stay = timedelta(days=_sect_salary_min_stay_days(profile_obj.sect_id))
        if now - joined_at < min_stay:
            remaining = min_stay - (now - joined_at)
            raise ValueError(f"新入门弟子仍在考察期，需再留宗 {_format_remaining_delta(remaining)} 才能领取俸禄。")
    elif now - last_claim < timedelta(days=30):
        remaining = timedelta(days=30) - (now - last_claim)
        raise ValueError(f"距离下次领取俸禄还需 {_format_remaining_delta(remaining)}。")
    salary = int(role.get("monthly_salary", 0) or 0)
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if updated is None or not updated.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        apply_spiritual_stone_delta(session, tg, salary, action_text="领取宗门俸禄", apply_tribute=True)
        updated.last_salary_claim_at = now
        updated.updated_at = now
        session.commit()
    create_journal(tg, "sect", "领取月俸", f"自宗门执事手中接过 {salary} 灵石的月例供奉")
    return {"salary": salary, "profile": _full_profile_bundle(tg)["profile"], "role": role}


def perform_sect_attendance(tg: int) -> dict[str, Any]:
    promotion_payload = None
    contribution_gain = SECT_DAILY_ATTENDANCE_CONTRIBUTION
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "宗门签到")
        if not profile.sect_id:
            raise ValueError("你尚未加入宗门")
        if _sect_attendance_done_today(profile):
            raise ValueError("你今日已经完成宗门签到。")

        sect = serialize_sect(get_sect(int(profile.sect_id or 0)))
        if sect is None:
            raise ValueError("当前宗门不存在")
        roles = list_sect_roles(int(profile.sect_id or 0))
        before_role_key, next_role_key, _ = _apply_sect_contribution_gain(profile, roles, contribution_gain)
        profile.last_sect_attendance_at = utcnow()
        profile.last_sect_attendance_method = "attendance"
        profile.updated_at = utcnow()
        session.commit()

        if next_role_key != before_role_key:
            promotion_payload = _maybe_promote_sect_member(tg, sect, before_role_key, next_role_key)

    create_journal(
        tg,
        "sect",
        "山门点卯",
        f"晨钟声中完成今日山门点卯，宗门贡献 +{contribution_gain}。",
    )
    return {
        "method": "attendance",
        "contribution_gain": contribution_gain,
        "promotion": promotion_payload,
        "sect": get_current_sect_bundle(tg),
    }


def perform_sect_teach(tg: int, cultivation_amount: int) -> dict[str, Any]:
    amount = max(int(cultivation_amount or 0), 0)
    if amount < 1000:
        raise ValueError("传功至少需要投入 1000 修为。")

    promotion_payload = None
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "宗门传功")
        if not profile.sect_id:
            raise ValueError("你尚未加入宗门")
        current_cultivation = max(int(profile.cultivation or 0), 0)
        if current_cultivation < amount:
            raise ValueError(f"当前修为不足，最多只能传功 {current_cultivation}。")

        sect = serialize_sect(get_sect(int(profile.sect_id or 0)))
        if sect is None:
            raise ValueError("当前宗门不存在")
        roles = list_sect_roles(int(profile.sect_id or 0))
        contribution_gain = _teach_contribution_score(amount)
        before_role_key, next_role_key, _ = _apply_sect_contribution_gain(profile, roles, contribution_gain)

        profile.cultivation = current_cultivation - amount
        profile.updated_at = utcnow()
        session.commit()

        if next_role_key != before_role_key:
            promotion_payload = _maybe_promote_sect_member(tg, sect, before_role_key, next_role_key)

    create_journal(
        tg,
        "sect",
        "传功山门",
        f"将 {amount} 点修为灌入宗门传功阁，宗门贡献 +{contribution_gain}。",
    )
    return {
        "method": "teach",
        "cultivation_amount": amount,
        "contribution_gain": contribution_gain,
        "promotion": promotion_payload,
        "sect": get_current_sect_bundle(tg),
    }


def donate_item_to_sect_treasury(tg: int, item_kind: str, item_ref_id: int, quantity: int) -> dict[str, Any]:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind not in {"artifact", "pill", "talisman", "material"}:
        raise ValueError("宗门宝库目前只接收背包中的法宝、丹药、符箓和材料。")
    ref_id = int(item_ref_id or 0)
    amount = max(int(quantity or 0), 0)
    if ref_id <= 0 or amount <= 0:
        raise ValueError("请先选择要捐入宗门宝库的物品和数量。")

    submitted_item = None
    promotion_payload = None
    treasury_payload = None
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "捐赠宗门宝库")
        if not profile.sect_id:
            raise ValueError("你尚未加入宗门")

        sect = serialize_sect(get_sect(int(profile.sect_id or 0)))
        if sect is None:
            raise ValueError("当前宗门不存在")
        roles = list_sect_roles(int(profile.sect_id or 0))
        submitted_item = _consume_required_item(session, tg, normalized_kind, ref_id, amount)
        contribution_gain = _item_contribution_score(normalized_kind, submitted_item, amount)
        before_role_key, next_role_key, _ = _apply_sect_contribution_gain(profile, roles, contribution_gain)

        treasury_row = (
            session.query(XiuxianSectTreasuryItem)
            .filter(
                XiuxianSectTreasuryItem.sect_id == int(profile.sect_id or 0),
                XiuxianSectTreasuryItem.item_kind == normalized_kind,
                XiuxianSectTreasuryItem.item_ref_id == ref_id,
            )
            .with_for_update()
            .first()
        )
        if treasury_row is None:
            treasury_row = XiuxianSectTreasuryItem(
                sect_id=int(profile.sect_id or 0),
                item_kind=normalized_kind,
                item_ref_id=ref_id,
                quantity=0,
            )
            session.add(treasury_row)
        treasury_row.quantity = max(int(treasury_row.quantity or 0), 0) + amount
        treasury_row.updated_at = utcnow()

        profile.updated_at = utcnow()
        session.commit()
        treasury_payload = {
            "item_kind": normalized_kind,
            "item_ref_id": ref_id,
            "quantity": int(treasury_row.quantity or 0),
        }

        if next_role_key != before_role_key:
            promotion_payload = _maybe_promote_sect_member(tg, sect, before_role_key, next_role_key)

    item_name = (submitted_item or {}).get("name") or f"{normalized_kind}#{ref_id}"
    create_journal(
        tg,
        "sect",
        "宝库纳贡",
        f"将 {item_name} × {amount} 送入宗门宝库，宗门贡献 +{contribution_gain}。",
    )
    return {
        "method": "donate",
        "item": submitted_item,
        "item_kind": normalized_kind,
        "item_ref_id": ref_id,
        "quantity": amount,
        "contribution_gain": contribution_gain,
        "promotion": promotion_payload,
        "treasury_item": treasury_payload,
        "sect": get_current_sect_bundle(tg),
    }


def _can_publish_sect_task(tg: int) -> bool:
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("sect_id"):
        return False
    role = get_sect_role_payload(profile.get("sect_id"), profile.get("sect_role_key"))
    return bool(role and role.get("can_publish_tasks"))


def _normalize_quiz_answer_text(answer_text: str | None) -> str:
    raw = str(answer_text or "").strip().casefold()
    raw = raw.strip("，。！？!?；;：:,.、 ")
    return re.sub(r"\s+", "", raw)


def _meaningful_text_length(value: str | None) -> int:
    raw = str(value or "").strip()
    if not raw:
        return 0
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", raw, flags=re.UNICODE)
    return len(normalized or re.sub(r"\s+", "", raw))


def create_bounty_task(
    *,
    actor_tg: int | None,
    title: str,
    description: str,
    task_scope: str,
    task_type: str,
    question_text: str = "",
    answer_text: str = "",
    image_url: str = "",
    required_item_kind: str | None = None,
    required_item_ref_id: int | None = None,
    required_item_quantity: int = 0,
    requirement_metric_key: str | None = None,
    requirement_metric_target: int = 0,
    reward_stone: int = 0,
    reward_cultivation: int = 0,
    reward_scale_mode: str = "fixed",
    reward_item_kind: str | None = None,
    reward_item_ref_id: int | None = None,
    reward_item_quantity: int = 0,
    max_claimants: int = 1,
    sect_id: int | None = None,
    active_in_group: bool = False,
    group_chat_id: int | None = None,
) -> dict[str, Any]:
    title_value = str(title or "").strip()
    description_value = str(description or "").strip()
    question_value = str(question_text or "").strip()
    image_value = str(image_url or "").strip()
    task_scope_value = str(task_scope or "personal").strip() or "personal"
    task_type_value = str(task_type or "custom").strip() or "custom"
    normalized_answer = _normalize_quiz_answer_text(answer_text)
    should_push_group = bool(active_in_group)
    required_kind = str(required_item_kind or "").strip() or None
    required_ref = int(required_item_ref_id or 0) or None
    required_qty = max(int(required_item_quantity or 0), 0)
    metric_key = str(requirement_metric_key or "").strip() or None
    metric_target = max(int(requirement_metric_target or 0), 0)
    reward_kind = str(reward_item_kind or "").strip() or None
    reward_ref = int(reward_item_ref_id or 0) or None
    reward_qty = max(int(reward_item_quantity or 0), 0)
    reward_stone_value = max(int(reward_stone or 0), 0)
    reward_cultivation_value = max(int(reward_cultivation or 0), 0)
    reward_scale_mode_value = str(reward_scale_mode or "fixed").strip() or "fixed"
    max_claimants_value = max(int(max_claimants or 1), 1)
    publish_cost = 0

    if task_scope_value not in {"official", "sect", "personal"}:
        raise ValueError("任务范围不支持")
    if task_type_value not in {"quiz", "custom", "metric"}:
        raise ValueError("任务类型不支持")
    if actor_tg is not None and task_scope_value == "official":
        raise ValueError("玩家不能发布官方任务")
    if _meaningful_text_length(title_value) < 2:
        raise ValueError("任务标题至少填写 2 个字")
    if reward_scale_mode_value not in TASK_REWARD_SCALE_MODES:
        raise ValueError("任务奖励缩放模式不支持")
    if actor_tg is not None and reward_stone_value > 0 and reward_scale_mode_value != "fixed":
        reward_scale_mode_value = "fixed"

    if task_type_value == "quiz":
        if _meaningful_text_length(question_value) < 4:
            raise ValueError("答题任务必须填写清晰的题目内容")
        if not normalized_answer:
            raise ValueError("答题任务必须填写标准答案")
        if not group_chat_id:
            raise ValueError("答题任务必须绑定群聊后才能发布")
        if required_kind:
            raise ValueError("答题任务暂不支持提交物品")
        if metric_key:
            raise ValueError("答题任务暂不支持计数要求")
        should_push_group = True
        max_claimants_value = 1
    elif task_type_value == "metric":
        if _meaningful_text_length(description_value) < 6:
            raise ValueError("计数任务必须填写至少 6 个字的任务说明")
        if required_kind:
            raise ValueError("计数任务暂不支持提交物品")
        if not metric_key or metric_key not in METRIC_TASK_ALLOWED_KEYS:
            raise ValueError("请选择有效的计数任务指标")
        if metric_target <= 0:
            raise ValueError("计数任务目标次数必须大于 0")
    elif _meaningful_text_length(description_value) < 6:
        raise ValueError("普通任务必须填写至少 6 个字的任务说明")

    if task_type_value != "metric":
        metric_key = None
        metric_target = 0

    if required_kind:
        if required_kind not in {"artifact", "pill", "talisman", "material"}:
            raise ValueError("任务提交物类型不支持")
        if required_ref is None:
            raise ValueError("请选择任务需要提交的物品")
        if required_qty <= 0:
            raise ValueError("任务提交物数量必须大于 0")
        if _get_item_payload(required_kind, required_ref) is None:
            raise ValueError("任务提交物不存在")
    else:
        required_ref = None
        required_qty = 0

    if reward_kind:
        if reward_kind not in {"artifact", "pill", "talisman", "material", "recipe", "technique"}:
            raise ValueError("任务奖励物类型不支持")
        if reward_ref is None:
            raise ValueError("请选择任务奖励物")
        if reward_kind in {"recipe", "technique"}:
            reward_qty = 1
            if max_claimants_value > 1:
                raise ValueError("配方和功法奖励只能发布单人委托")
        if reward_qty <= 0:
            raise ValueError("任务奖励物数量必须大于 0")
        if _get_item_payload(reward_kind, reward_ref) is None:
            raise ValueError("任务奖励物不存在")
    else:
        reward_ref = None
        reward_qty = 0

    if reward_stone_value <= 0 and reward_cultivation_value <= 0 and not reward_kind:
        raise ValueError("悬赏任务必须设置奖励，不能发布无奖励任务")

    actor_profile = None
    settings = get_xiuxian_settings()
    if actor_tg is not None:
        # 玩家发布任务先过开关、身份与灵石扣费三道校验。
        if not bool(settings.get("allow_user_task_publish", DEFAULT_SETTINGS.get("allow_user_task_publish", True))):
            raise ValueError("当前未开放玩家发布任务")
        actor_obj, actor_profile = _require_alive_profile_data(actor_tg, "发布任务")
        assert_currency_operation_allowed(actor_tg, "发布任务", profile=actor_obj)
        publish_cost = max(int(settings.get("task_publish_cost", DEFAULT_SETTINGS.get("task_publish_cost", 0)) or 0), 0)
        daily_limit = _user_task_daily_limit()
        published_today = _user_task_publish_count_today(actor_tg)
        if daily_limit > 0 and published_today >= daily_limit:
            raise ValueError(f"你今日已发布 {published_today} 次悬赏，已达到上限 {daily_limit} 次。")

    if task_scope_value == "sect":
        if actor_tg is None:
            if not sect_id:
                raise ValueError("宗门任务必须指定宗门")
        else:
            if not _can_publish_sect_task(actor_tg):
                raise ValueError("当前身份无法发布宗门任务")
            sect_id = int(actor_profile.get("sect_id") or 0)
            if not sect_id:
                raise ValueError("你尚未加入宗门")

    reward_item_escrowed = False
    reward_stone_escrowed = False
    escrow_reward_qty = reward_qty * max_claimants_value if reward_kind else 0
    escrow_reward_stone = reward_stone_value * max_claimants_value if actor_tg is not None and reward_stone_value > 0 else 0
    with Session() as session:
        if actor_tg is not None:
            # 发布时对玩家记录加锁，防止并发发任务导致灵石重复扣减或余额穿透。
            publisher = session.query(XiuxianProfile).filter(XiuxianProfile.tg == actor_tg).with_for_update().first()
            if publisher is None or not publisher.consented:
                raise ValueError("你尚未踏入仙途，道基未立")
            if publish_cost > 0:
                apply_spiritual_stone_delta(
                    session,
                    actor_tg,
                    -publish_cost,
                    action_text="发布任务",
                    enforce_currency_lock=False,
                    allow_dead=False,
                    apply_tribute=False,
                )
            if escrow_reward_stone > 0:
                apply_spiritual_stone_delta(
                    session,
                    actor_tg,
                    -escrow_reward_stone,
                    action_text="扣押任务灵石奖励",
                    enforce_currency_lock=False,
                    allow_dead=False,
                    apply_tribute=False,
                )
                reward_stone_escrowed = True
            reward_item_escrowed = _escrow_reward_item_for_task(
                session,
                actor_tg=actor_tg,
                reward_kind=reward_kind,
                reward_ref=reward_ref,
                reward_qty=escrow_reward_qty,
            )

        task_row = XiuxianTask(
            title=title_value,
            description=description_value or None,
            task_scope=task_scope_value,
            task_type=task_type_value,
            owner_tg=actor_tg,
            sect_id=sect_id,
            question_text=question_value or None,
            answer_text=normalized_answer or None,
            image_url=image_value or None,
            required_item_kind=required_kind,
            required_item_ref_id=required_ref,
            required_item_quantity=required_qty,
            requirement_metric_key=metric_key,
            requirement_metric_target=metric_target,
            reward_stone=reward_stone_value,
            reward_cultivation=reward_cultivation_value,
            reward_item_kind=reward_kind,
            reward_item_ref_id=reward_ref,
            reward_item_quantity=reward_qty,
            reward_item_escrowed=reward_item_escrowed,
            reward_stone_escrowed=reward_stone_escrowed,
            reward_scale_mode=reward_scale_mode_value,
            max_claimants=max_claimants_value,
            active_in_group=should_push_group,
            group_chat_id=group_chat_id,
            status="open",
            enabled=True,
        )
        session.add(task_row)
        _queue_catalog_cache_invalidation(session, "tasks")
        if actor_tg is not None:
            _queue_user_view_cache_invalidation(session, actor_tg)
        session.commit()
        session.refresh(task_row)
        payload = _decorate_task_payload(serialize_task(task_row))

    if payload is not None and actor_tg is not None:
        payload["publish_cost"] = publish_cost
        payload["escrowed_reward_stone"] = escrow_reward_stone
        payload["total_spiritual_stone_cost"] = publish_cost + escrow_reward_stone
    return payload



def _escrow_reward_item_for_task(
    session: Session,
    *,
    actor_tg: int | None,
    reward_kind: str | None,
    reward_ref: int | None,
    reward_qty: int,
) -> bool:
    if actor_tg is None or not reward_kind or not reward_ref or int(reward_qty or 0) <= 0:
        return False
    amount = 1 if reward_kind in {"recipe", "technique"} else max(int(reward_qty or 0), 1)
    _consume_inventory_item_for_task(
        session,
        int(actor_tg),
        str(reward_kind),
        int(reward_ref),
        amount,
        action_label="扣押奖励",
        allow_recipe_or_technique=True,
    )
    return True


def _task_completed_claim_count_in_session(session: Session, task_id: int | None) -> int:
    normalized_task_id = int(task_id or 0)
    if normalized_task_id <= 0:
        return 0
    return int(
        session.query(func.count(XiuxianTaskClaim.id))
        .filter(
            XiuxianTaskClaim.task_id == normalized_task_id,
            XiuxianTaskClaim.status == "completed",
        )
        .scalar()
        or 0
    )


def _task_reward_stone_amount(task: XiuxianTask) -> int:
    return max(int(getattr(task, "reward_stone", 0) or 0), 0)


def _task_reward_max_claimants(task: XiuxianTask) -> int:
    return max(int(getattr(task, "max_claimants", 1) or 1), 1)


def _is_unescrowed_player_stone_task(task: XiuxianTask | dict[str, Any] | None) -> bool:
    if task is None:
        return False
    if isinstance(task, dict):
        owner_tg = int(task.get("owner_tg") or 0)
        reward_stone = max(int(task.get("reward_stone") or 0), 0)
        reward_stone_escrowed = bool(task.get("reward_stone_escrowed"))
    else:
        owner_tg = int(getattr(task, "owner_tg", 0) or 0)
        reward_stone = _task_reward_stone_amount(task)
        reward_stone_escrowed = bool(getattr(task, "reward_stone_escrowed", False))
    return owner_tg > 0 and reward_stone > 0 and not reward_stone_escrowed


def _unescrowed_player_stone_task_reason() -> str:
    return "该玩家任务的灵石奖励未扣押，已暂停领取，请发布者撤销后重新发布。"


def _remaining_unpaid_task_reward_slots(session: Session, task: XiuxianTask) -> int:
    completed_count = _task_completed_claim_count_in_session(session, getattr(task, "id", 0))
    return max(_task_reward_max_claimants(task) - completed_count, 0)


def _refund_task_reward_stone_in_session(session: Session, task: XiuxianTask) -> dict[str, Any] | None:
    if not bool(getattr(task, "reward_stone_escrowed", False)):
        return None
    owner_tg = int(getattr(task, "owner_tg", 0) or 0)
    reward_stone = _task_reward_stone_amount(task)
    remaining_claimants = _remaining_unpaid_task_reward_slots(session, task)
    refund_amount = reward_stone * remaining_claimants
    if owner_tg <= 0 or reward_stone <= 0 or refund_amount <= 0:
        task.reward_stone_escrowed = False
        return None
    apply_spiritual_stone_delta(
        session,
        owner_tg,
        refund_amount,
        action_text="退还任务灵石奖励",
        allow_dead=True,
        apply_tribute=False,
    )
    task.reward_stone_escrowed = False
    task.updated_at = utcnow()
    return {"amount": refund_amount, "remaining_claimants": remaining_claimants}


def _grant_task_reward_stone_in_session(session: Session, task: XiuxianTask, receiver_tg: int, reward_stone: int) -> int:
    amount = max(int(reward_stone or 0), 0)
    if amount <= 0:
        if bool(getattr(task, "reward_stone_escrowed", False)) and _task_reward_stone_amount(task) <= 0:
            task.reward_stone_escrowed = False
        return 0
    if bool(getattr(task, "reward_stone_escrowed", False)):
        amount = min(amount, _task_reward_stone_amount(task))
    if amount <= 0:
        return 0
    apply_spiritual_stone_delta(
        session,
        int(receiver_tg),
        amount,
        action_text="领取任务奖励",
        allow_dead=False,
        apply_tribute=True,
    )
    if bool(getattr(task, "reward_stone_escrowed", False)) and int(getattr(task, "claimants_count", 0) or 0) >= _task_reward_max_claimants(task):
        task.reward_stone_escrowed = False
        task.updated_at = utcnow()
    return amount


def _refund_task_reward_item_in_session(session: Session, task: XiuxianTask) -> dict[str, Any] | None:
    if not bool(getattr(task, "reward_item_escrowed", False)):
        return None
    owner_tg = int(getattr(task, "owner_tg", 0) or 0)
    reward_kind = str(getattr(task, "reward_item_kind", "") or "").strip()
    reward_ref = int(getattr(task, "reward_item_ref_id", 0) or 0)
    reward_qty = int(getattr(task, "reward_item_quantity", 0) or 0)
    remaining_claimants = _remaining_unpaid_task_reward_slots(session, task)
    if owner_tg <= 0 or not reward_kind or reward_ref <= 0 or reward_qty <= 0:
        task.reward_item_escrowed = False
        return None
    refund_qty = reward_qty * remaining_claimants
    if refund_qty <= 0:
        task.reward_item_escrowed = False
        return None
    reward_item = _grant_item_in_session(
        session,
        owner_tg,
        reward_kind,
        reward_ref,
        refund_qty,
        source="task_refund",
        obtained_note="撤销委托退还",
    )
    task.reward_item_escrowed = False
    return reward_item


def _consume_task_reward_escrow_in_session(session: Session, task: XiuxianTask, receiver_tg: int) -> dict[str, Any] | None:
    reward_kind = str(getattr(task, "reward_item_kind", "") or "").strip()
    reward_ref = int(getattr(task, "reward_item_ref_id", 0) or 0)
    reward_qty = int(getattr(task, "reward_item_quantity", 0) or 0)
    if not reward_kind or reward_ref <= 0 or reward_qty <= 0:
        return None
    reward_item = _grant_item_in_session(
        session,
        int(receiver_tg),
        reward_kind,
        reward_ref,
        reward_qty,
        source="task",
        obtained_note="委托奖励",
    )
    if bool(getattr(task, "reward_item_escrowed", False)) and int(getattr(task, "claimants_count", 0) or 0) >= int(getattr(task, "max_claimants", 1) or 1):
        task.reward_item_escrowed = False
        task.updated_at = utcnow()
    return reward_item

def list_task_claims_for_user(tg: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianTaskClaim)
            .filter(XiuxianTaskClaim.tg == tg)
            .order_by(XiuxianTaskClaim.id.desc())
            .all()
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "tg": row.tg,
                "status": row.status,
                "submitted_answer": row.submitted_answer,
                "metric_start_value": max(int(row.metric_start_value or 0), 0),
            }
            for row in rows
        ]


def list_tasks_for_user(tg: int) -> list[dict[str, Any]]:
    profile = serialize_profile(get_profile(tg, create=False)) or {}
    claims_by_task = {claim["task_id"]: claim for claim in list_task_claims_for_user(tg)}
    progress_map = get_user_achievement_progress_map(tg)
    rows = []
    for task in list_tasks(enabled_only=True):
        if task["status"] not in {"open", "active"}:
            continue
        if task["task_scope"] == "sect" and int(task.get("sect_id") or 0) != int(profile.get("sect_id") or 0):
            continue
        if _is_unescrowed_player_stone_task(task):
            task["claim_block_reason"] = _unescrowed_player_stone_task_reason()
            if int(task.get("owner_tg") or 0) != int(tg):
                continue
        task["claimed"] = task["id"] in claims_by_task or int(task.get("winner_tg") or 0) == int(tg)
        task["claim"] = claims_by_task.get(task["id"])
        task.update(_scaled_task_reward_values(task, profile))
        if str(task.get("task_type") or "") == "metric":
            task.update(_metric_task_progress_payload(task, task.get("claim"), progress_map))
        task["can_cancel"] = (
            int(task.get("owner_tg") or 0) == int(tg)
            and task.get("status") in {"open", "active"}
            and not int(task.get("winner_tg") or 0)
        )
        rows.append(_decorate_task_payload(task))
    return rows


def cancel_task_for_user(tg: int, task_id: int) -> dict[str, Any]:
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立")
    with Session() as session:
        task = session.query(XiuxianTask).filter(XiuxianTask.id == task_id).with_for_update().first()
        if task is None or not task.enabled:
            raise ValueError("任务不存在")
        if int(task.owner_tg or 0) != int(tg):
            raise ValueError("只有发布者本人才能撤销任务")
        if task.status not in {"open", "active"}:
            raise ValueError("当前任务状态不允许撤销")
        if int(task.winner_tg or 0):
            raise ValueError("任务已经完成，不能撤销")
        claims = (
            session.query(XiuxianTaskClaim)
            .filter(XiuxianTaskClaim.task_id == task_id)
            .with_for_update()
            .all()
        )
        for claim in claims:
            if claim.status == "completed":
                raise ValueError("任务已经完成，不能撤销")
            claim.status = "cancelled"
        refunded_stone = _refund_task_reward_stone_in_session(session, task)
        _refund_task_reward_item_in_session(session, task)
        task.status = "cancelled"
        task.active_in_group = False
        task.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "tasks")
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        session.refresh(task)
        serialized = _decorate_task_payload(serialize_task(task))
    create_journal(tg, "task", "撤销委托", f"自行撤回了悬赏委托【{serialized['title']}】")
    return {"task": serialized, "refunded_reward_stone": int((refunded_stone or {}).get("amount") or 0)}


def _decorate_task_payload(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if task is None:
        return None
    payload = dict(task)
    if payload.get("required_item_kind") and payload.get("required_item_ref_id"):
        payload["required_item"] = _get_item_payload(payload["required_item_kind"], int(payload["required_item_ref_id"]))
    else:
        payload["required_item"] = None
    if payload.get("reward_item_kind") and payload.get("reward_item_ref_id"):
        payload["reward_item"] = _get_item_payload(payload["reward_item_kind"], int(payload["reward_item_ref_id"]))
    else:
        payload["reward_item"] = None
    if payload.get("requirement_metric_key"):
        payload["metric_label"] = ACHIEVEMENT_METRIC_LABELS.get(
            str(payload.get("requirement_metric_key") or ""),
            payload.get("requirement_metric_key"),
        )
    return payload


def _required_item_name(kind: str, ref_id: int) -> str:
    item = _get_item_payload(kind, ref_id)
    if item and item.get("name"):
        return str(item["name"])
    return f"{kind}#{ref_id}"


def _inventory_item_label(item_kind: str, item: dict[str, Any] | None) -> str:
    if item and item.get("name"):
        return str(item["name"])
    return str(item_kind or "物品")


def _consume_inventory_item_for_task(
    session: Session,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    *,
    action_label: str,
    allow_recipe_or_technique: bool = False,
) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    item = _get_item_payload(item_kind, int(item_ref_id))
    if item is None:
        raise ValueError(f"{action_label}物品不存在")
    item_name = _inventory_item_label(item_kind, item)

    row = None
    if item_kind == "artifact":
        row = (
            session.query(XiuxianArtifactInventory)
            .filter(XiuxianArtifactInventory.tg == tg, XiuxianArtifactInventory.artifact_id == item_ref_id)
            .with_for_update()
            .first()
        )
    elif item_kind == "pill":
        row = (
            session.query(XiuxianPillInventory)
            .filter(XiuxianPillInventory.tg == tg, XiuxianPillInventory.pill_id == item_ref_id)
            .with_for_update()
            .first()
        )
    elif item_kind == "talisman":
        row = (
            session.query(XiuxianTalismanInventory)
            .filter(XiuxianTalismanInventory.tg == tg, XiuxianTalismanInventory.talisman_id == item_ref_id)
            .with_for_update()
            .first()
        )
    elif item_kind == "material":
        row = (
            session.query(XiuxianMaterialInventory)
            .filter(XiuxianMaterialInventory.tg == tg, XiuxianMaterialInventory.material_id == item_ref_id)
            .with_for_update()
            .first()
        )
    elif item_kind == "recipe" and allow_recipe_or_technique:
        row = (
            session.query(XiuxianUserRecipe)
            .filter(XiuxianUserRecipe.tg == tg, XiuxianUserRecipe.recipe_id == item_ref_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise ValueError(f"{action_label}所需配方不足：{item_name} × 1")
        session.delete(row)
        return item
    elif item_kind == "technique" and allow_recipe_or_technique:
        row = (
            session.query(XiuxianUserTechnique)
            .filter(XiuxianUserTechnique.tg == tg, XiuxianUserTechnique.technique_id == item_ref_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise ValueError(f"{action_label}所需功法不足：{item_name} × 1")
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is not None and int(profile.current_technique_id or 0) == int(item_ref_id):
            profile.current_technique_id = None
            profile.updated_at = utcnow()
        session.delete(row)
        return item
    else:
        raise ValueError(f"暂不支持该类型的{action_label}物品")

    if row is None or int(row.quantity or 0) < amount:
        raise ValueError(f"{action_label}所需物品不足：{item_name} × {amount}")

    if item_kind == "artifact":
        bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
        equipped_count = (
            session.query(XiuxianEquippedArtifact)
            .filter(
                XiuxianEquippedArtifact.tg == tg,
                XiuxianEquippedArtifact.artifact_id == item_ref_id,
            )
            .count()
        )
        available_quantity = int(row.quantity or 0) - bound_quantity - int(equipped_count or 0)
        if available_quantity < amount:
            raise ValueError(f"{action_label}所需法宝不足，已绑定或已装备的法宝无法使用：{item_name} × {amount}")
    elif item_kind == "talisman":
        bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
        available_quantity = int(row.quantity or 0) - bound_quantity
        if available_quantity < amount:
            raise ValueError(f"{action_label}所需符箓不足，已绑定的符箓无法使用：{item_name} × {amount}")

    row.quantity = int(row.quantity or 0) - amount
    row.updated_at = utcnow()
    if row.quantity <= 0:
        session.delete(row)
    return item


def _consume_required_item(
    session: Session,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
) -> dict[str, Any]:
    return _consume_inventory_item_for_task(
        session,
        tg,
        item_kind,
        item_ref_id,
        quantity,
        action_label="提交",
        allow_recipe_or_technique=False,
    )


def _pending_inventory_row(session: Session, model_cls: type, **keys: int) -> Any | None:
    for pending in session.new:
        if not isinstance(pending, model_cls):
            continue
        if all(int(getattr(pending, key, 0) or 0) == int(value) for key, value in keys.items()):
            return pending
    return None


def _grant_item_in_session(
    session: Session,
    tg: int,
    kind: str,
    ref_id: int,
    quantity: int,
    *,
    source: str = "task",
    obtained_note: str = "委托奖励",
) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    normalized_kind = str(kind or "").strip()
    if normalized_kind == "artifact":
        artifact = get_artifact(int(ref_id))
        if artifact is None:
            raise ValueError("任务奖励物不存在")
        row = _pending_inventory_row(session, XiuxianArtifactInventory, tg=int(tg), artifact_id=int(ref_id))
        if row is None:
            row = (
                session.query(XiuxianArtifactInventory)
                .filter(XiuxianArtifactInventory.tg == int(tg), XiuxianArtifactInventory.artifact_id == int(ref_id))
                .with_for_update()
                .first()
            )
        if row is None:
            row = XiuxianArtifactInventory(tg=int(tg), artifact_id=int(ref_id), quantity=0, bound_quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
        row.updated_at = utcnow()
        return {"artifact": artifact, "quantity": int(row.quantity or 0), "bound_quantity": int(row.bound_quantity or 0)}
    if normalized_kind == "pill":
        pill = get_pill(int(ref_id))
        if pill is None:
            raise ValueError("任务奖励物不存在")
        row = _pending_inventory_row(session, XiuxianPillInventory, tg=int(tg), pill_id=int(ref_id))
        if row is None:
            row = (
                session.query(XiuxianPillInventory)
                .filter(XiuxianPillInventory.tg == int(tg), XiuxianPillInventory.pill_id == int(ref_id))
                .with_for_update()
                .first()
            )
        if row is None:
            row = XiuxianPillInventory(tg=int(tg), pill_id=int(ref_id), quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        return {"pill": pill, "quantity": int(row.quantity or 0)}
    if normalized_kind == "talisman":
        talisman = get_talisman(int(ref_id))
        if talisman is None:
            raise ValueError("任务奖励物不存在")
        row = _pending_inventory_row(session, XiuxianTalismanInventory, tg=int(tg), talisman_id=int(ref_id))
        if row is None:
            row = (
                session.query(XiuxianTalismanInventory)
                .filter(XiuxianTalismanInventory.tg == int(tg), XiuxianTalismanInventory.talisman_id == int(ref_id))
                .with_for_update()
                .first()
            )
        if row is None:
            row = XiuxianTalismanInventory(tg=int(tg), talisman_id=int(ref_id), quantity=0, bound_quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
        row.updated_at = utcnow()
        return {"talisman": talisman, "quantity": int(row.quantity or 0), "bound_quantity": int(row.bound_quantity or 0)}
    if normalized_kind == "material":
        material = get_material(int(ref_id))
        if material is None:
            raise ValueError("任务奖励物不存在")
        row = _pending_inventory_row(session, XiuxianMaterialInventory, tg=int(tg), material_id=int(ref_id))
        if row is None:
            row = (
                session.query(XiuxianMaterialInventory)
                .filter(XiuxianMaterialInventory.tg == int(tg), XiuxianMaterialInventory.material_id == int(ref_id))
                .with_for_update()
                .first()
            )
        if row is None:
            row = XiuxianMaterialInventory(tg=int(tg), material_id=int(ref_id), quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        return {"material": material, "quantity": int(row.quantity or 0)}
    if normalized_kind == "recipe":
        recipe = get_recipe(int(ref_id))
        if recipe is None:
            raise ValueError("任务奖励物不存在")
        row = (
            session.query(XiuxianUserRecipe)
            .filter(XiuxianUserRecipe.tg == int(tg), XiuxianUserRecipe.recipe_id == int(ref_id))
            .with_for_update()
            .first()
        )
        if row is None:
            row = XiuxianUserRecipe(tg=int(tg), recipe_id=int(ref_id), source=source, obtained_note=obtained_note)
            session.add(row)
        else:
            return grant_duplicate_knowledge_compensation_in_session(
                session,
                int(tg),
                "recipe",
                recipe,
                action_text="重复丹谱折算灵石",
            )
        return {"recipe": recipe, "quantity": 1}
    if normalized_kind == "technique":
        technique = get_technique(int(ref_id))
        if technique is None:
            raise ValueError("任务奖励物不存在")
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if profile is None:
            profile = XiuxianProfile(tg=int(tg))
            session.add(profile)
        row = (
            session.query(XiuxianUserTechnique)
            .filter(XiuxianUserTechnique.tg == int(tg), XiuxianUserTechnique.technique_id == int(ref_id))
            .with_for_update()
            .first()
        )
        if row is None:
            row = XiuxianUserTechnique(tg=int(tg), technique_id=int(ref_id), source=source, obtained_note=obtained_note)
            session.add(row)
        else:
            return grant_duplicate_knowledge_compensation_in_session(
                session,
                int(tg),
                "technique",
                technique,
                action_text="重复功法折算灵石",
            )
        if not profile.current_technique_id:
            profile.current_technique_id = int(ref_id)
            profile.updated_at = utcnow()
        return {"technique": technique, "quantity": 1}
    raise ValueError("不支持的物品类型")


def _grant_item_by_kind(tg: int, kind: str, ref_id: int, quantity: int) -> dict[str, Any]:
    if kind == "artifact":
        return grant_artifact_to_user(tg, ref_id, quantity)
    if kind == "pill":
        return grant_pill_to_user(tg, ref_id, quantity)
    if kind == "talisman":
        return grant_talisman_to_user(tg, ref_id, quantity)
    if kind == "material":
        return grant_material_to_user(tg, ref_id, quantity)
    if kind == "recipe":
        return grant_recipe_to_user(tg, ref_id, source="exploration", obtained_note="秘境所得")
    if kind == "technique":
        return grant_technique_to_user(
            tg,
            ref_id,
            source="exploration",
            obtained_note="秘境所得",
            auto_equip_if_empty=True,
        )
    raise ValueError("不支持的物品类型")


def _assert_reward_item_receivable(tg: int, kind: str | None, ref_id: int, quantity: int) -> None:
    if str(kind or "") != "artifact" or int(ref_id or 0) <= 0 or int(quantity or 0) <= 0:
        return
    artifact = _get_item_payload("artifact", int(ref_id)) or {}
    if bool(artifact.get("unique_item")) and int(quantity or 0) > 1:
        raise ValueError(f"唯一法宝【{artifact.get('name') or ref_id}】每次只能获得 1 件。")
    assert_artifact_receivable_by_user(int(tg), int(ref_id), allow_existing_owner=False)


def _award_task_rewards(tg: int, task: XiuxianTask) -> dict[str, Any]:
    if task is None:
        raise ValueError("任务不存在")
    _assert_reward_item_receivable(
        tg,
        getattr(task, "reward_item_kind", None),
        int(getattr(task, "reward_item_ref_id", 0) or 0),
        int(getattr(task, "reward_item_quantity", 0) or 0),
    )
    legacy_service = _legacy_service()
    profile = serialize_profile(get_profile(tg, create=False)) or {}
    scaled_reward: dict[str, Any] = {
        "reward_stone": 0,
        "reward_cultivation": 0,
        "reward_scale_mode": "fixed",
        "reward_scale_factor": 1.0,
    }
    reward_stone = 0
    cultivation_gain_raw = 0
    cultivation_gain = 0
    cultivation_efficiency_percent = 100
    upgraded_layers: list[int] = []
    remaining = 0
    reward_item = None
    reward_kind = ""
    reward_ref = 0
    reward_qty = 0

    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if updated is None:
            raise ValueError("用户不存在")
        task_row = session.query(XiuxianTask).filter(XiuxianTask.id == int(task.id)).with_for_update().first()
        if task_row is None:
            raise ValueError("任务不存在")
        scaled_reward = _scaled_task_reward_values(task_row, profile)
        reward_stone = int(scaled_reward.get("reward_stone") or 0)
        if _is_unescrowed_player_stone_task(task_row):
            reward_stone = 0
            scaled_reward = dict(scaled_reward)
            scaled_reward["reward_stone"] = 0
            scaled_reward["reward_scale_mode"] = "fixed"
            scaled_reward["reward_scale_factor"] = 1.0
        if bool(getattr(task_row, "reward_stone_escrowed", False)):
            reward_stone = min(reward_stone, _task_reward_stone_amount(task_row))
            scaled_reward = dict(scaled_reward)
            scaled_reward["reward_stone"] = reward_stone
            scaled_reward["reward_scale_mode"] = "fixed"
            scaled_reward["reward_scale_factor"] = 1.0
        cultivation_gain_raw = max(int(scaled_reward.get("reward_cultivation") or 0), 0)
        reward_kind = str(getattr(task_row, "reward_item_kind", "") or "").strip()
        reward_ref = int(getattr(task_row, "reward_item_ref_id", 0) or 0)
        reward_qty = int(getattr(task_row, "reward_item_quantity", 0) or 0)
        if reward_stone > 0:
            reward_stone = _grant_task_reward_stone_in_session(session, task_row, tg, reward_stone)
        if cultivation_gain_raw > 0:
            cultivation_gain, gain_meta = legacy_service.adjust_cultivation_gain_for_social_mode(
                updated,
                cultivation_gain_raw,
                settings=get_xiuxian_settings(),
            )
            cultivation_gain = int(cultivation_gain or 0)
            cultivation_efficiency_percent = int(gain_meta.get("efficiency_percent") or 100)
            layer, cultivation, upgraded_layers, remaining = legacy_service.apply_cultivation_gain(
                legacy_service.normalize_realm_stage(updated.realm_stage or legacy_service.FIRST_REALM_STAGE),
                int(updated.realm_layer or 1),
                int(updated.cultivation or 0),
                cultivation_gain,
            )
            updated.realm_layer = layer
            updated.cultivation = cultivation
        if reward_kind and reward_ref > 0 and reward_qty > 0:
            if bool(getattr(task_row, "reward_item_escrowed", False)):
                reward_item = _consume_task_reward_escrow_in_session(session, task_row, tg)
            else:
                reward_item = _grant_item_in_session(
                    session,
                    tg,
                    reward_kind,
                    reward_ref,
                    reward_qty,
                    source="task",
                    obtained_note="委托奖励",
                )
        updated.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "tasks")
        affected_tgs = [tg]
        owner_tg = int(getattr(task_row, "owner_tg", 0) or 0)
        if owner_tg > 0:
            affected_tgs.append(owner_tg)
        _queue_user_view_cache_invalidation(session, *affected_tgs)
        session.commit()

    if cultivation_gain > 0:
        legacy_service._apply_profile_growth_floor(tg)
    return {
        "profile": _full_profile_bundle(tg)["profile"],
        "reward_stone": reward_stone,
        "reward_cultivation": cultivation_gain,
        "reward_cultivation_raw": cultivation_gain_raw,
        "cultivation_efficiency_percent": cultivation_efficiency_percent,
        "reward_scale_mode": scaled_reward.get("reward_scale_mode"),
        "reward_scale_factor": scaled_reward.get("reward_scale_factor"),
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "reward_item": reward_item,
    }


def mark_task_group_message(task_id: int, chat_id: int, message_id: int) -> dict[str, Any]:
    with Session() as session:
        task = session.query(XiuxianTask).filter(XiuxianTask.id == task_id).first()
        if task is None:
            raise ValueError("任务不存在")
        task.active_in_group = True
        task.group_chat_id = chat_id
        task.group_message_id = message_id
        task.status = "active"
        task.updated_at = utcnow()
        session.commit()
        session.refresh(task)
        return serialize_task(task)


def active_quiz_tasks_for_group(chat_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianTask)
            .filter(
                XiuxianTask.group_chat_id == chat_id,
                XiuxianTask.active_in_group.is_(True),
                XiuxianTask.task_type == "quiz",
                XiuxianTask.status.in_(["open", "active"]),
                XiuxianTask.enabled.is_(True),
            )
            .order_by(XiuxianTask.id.asc())
            .all()
        )
        return [serialize_task(row) for row in rows]





def _get_item_payload(kind: str, ref_id: int) -> dict[str, Any] | None:
    if kind == "artifact":
        from bot.sql_helper.sql_xiuxian import serialize_artifact

        return serialize_artifact(get_artifact(ref_id))
    if kind == "pill":
        from bot.sql_helper.sql_xiuxian import serialize_pill

        return serialize_pill(get_pill(ref_id))
    if kind == "talisman":
        from bot.sql_helper.sql_xiuxian import serialize_talisman

        return serialize_talisman(get_talisman(ref_id))
    if kind == "material":
        return serialize_material(get_material(ref_id))
    if kind == "technique":
        return serialize_technique(get_technique(ref_id))
    if kind == "recipe":
        recipe = serialize_recipe(get_recipe(ref_id))
        if recipe:
            recipe["result_item"] = _get_item_payload(str(recipe.get("result_kind") or ""), int(recipe.get("result_ref_id") or 0))
        return recipe
    return None


def _attach_talisman_preview_effects(item: dict[str, Any] | None, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not item:
        return item
    legacy = _legacy_service()
    profile_payload = profile or {}
    item["resolved_effects"] = legacy.resolve_talisman_effects(profile_payload, item)
    item["active_effects"] = legacy.resolve_talisman_active_effects(profile_payload, item)
    item["active_effect_summary"] = legacy.active_talisman_effect_summary(item["active_effects"])
    return item


def _quality_from_item(kind: str, item: dict[str, Any] | None) -> int:
    if not item:
        return 1
    if kind == "material":
        return max(int(item.get("quality_level", 1) or 1), 1)
    if kind == "recipe":
        return _quality_from_item(
            str(item.get("result_kind") or ""),
            _get_item_payload(str(item.get("result_kind") or ""), int(item.get("result_ref_id") or 0)),
        )
    if kind in {"artifact", "talisman", "pill", "technique"}:
        if item.get("rarity_level") is not None:
            return max(int(item.get("rarity_level") or 1), 1)
        return max(RARITY_LEVEL_MAP.get(item.get("rarity") or "凡品", 1), 1)
    return 1


EXPLORATION_QUALITY_WEIGHT_MULTIPLIERS = {
    1: 1.0,
    2: 0.62,
    3: 0.32,
    4: 0.14,
    5: 0.055,
    6: 0.018,
    7: 0.005,
}


def _exploration_drop_weight_rules() -> dict[str, int]:
    defaults = DEFAULT_SETTINGS["exploration_drop_weight_rules"]
    raw = get_xiuxian_settings().get("exploration_drop_weight_rules", defaults)
    raw = raw if isinstance(raw, dict) else {}

    def pick(key: str, minimum: int) -> int:
        try:
            value = int(raw.get(key, defaults[key]))
        except (TypeError, ValueError):
            value = int(defaults[key])
        return max(value, minimum)

    return {
        "material_divine_sense_divisor": pick("material_divine_sense_divisor", 1),
        "high_quality_threshold": min(pick("high_quality_threshold", 1), max(RARITY_LEVEL_MAP.values())),
        "high_quality_fortune_divisor": pick("high_quality_fortune_divisor", 1),
        "high_quality_root_level_start": pick("high_quality_root_level_start", 0),
    }


def _exploration_empty_chance(max_quality: int, fortune: int, divine_sense: int, root_quality_level: int) -> float:
    base = 0.12 + max(int(max_quality or 1) - 1, 0) * 0.04
    reduction = min(
        max(int(fortune or 0) - 10, 0) / 220.0
        + max(int(divine_sense or 0) - 10, 0) / 260.0
        + max(int(root_quality_level or 1) - 1, 0) * 0.01,
        0.14,
    )
    return max(min(base - reduction, 0.46), 0.08)


def create_recipe_with_ingredients(
    *,
    name: str,
    recipe_kind: str,
    result_kind: str,
    result_ref_id: int,
    result_quantity: int,
    base_success_rate: int,
    broadcast_on_success: bool,
    ingredients: list[dict[str, Any]],
) -> dict[str, Any]:
    recipe = create_recipe(
        name=name,
        recipe_kind=recipe_kind,
        result_kind=result_kind,
        result_ref_id=result_ref_id,
        result_quantity=max(int(result_quantity or 1), 1),
        base_success_rate=max(min(int(base_success_rate or 60), 100), 1),
        broadcast_on_success=bool(broadcast_on_success),
        enabled=True,
    )
    recipe["ingredients"] = replace_recipe_ingredients(
        recipe["id"],
        [
            {
                "material_id": int(item.get("material_id") or 0),
                "quantity": max(int(item.get("quantity") or 1), 1),
            }
            for item in ingredients
        ],
    )
    return recipe


def _append_item_source_label(
    catalog: dict[tuple[str, int], set[str]],
    item_kind: str,
    item_ref_id: int,
    label: str,
) -> None:
    normalized_kind = str(item_kind or "").strip()
    normalized_label = str(label or "").strip()
    ref_id = int(item_ref_id or 0)
    if not normalized_kind or ref_id <= 0 or not normalized_label:
        return
    catalog.setdefault((normalized_kind, ref_id), set()).add(normalized_label)


def _build_item_source_catalog_uncached() -> dict[tuple[str, int], list[str]]:
    catalog: dict[tuple[str, int], set[str]] = {}

    for scene in list_scenes(enabled_only=True):
        scene_name = str(scene.get("name") or "未知秘境").strip()
        if not scene_name:
            continue
        for drop in list_scene_drops(int(scene.get("id") or 0)):
            _append_item_source_label(
                catalog,
                str(drop.get("reward_kind") or ""),
                int(drop.get("reward_ref_id") or 0),
                f"秘境：{scene_name}",
            )
        for event in scene.get("event_pool") or []:
            _append_item_source_label(
                catalog,
                str((event or {}).get("bonus_reward_kind") or ""),
                int((event or {}).get("bonus_reward_ref_id") or 0),
                f"事件：{scene_name}",
            )

    for item in list_shop_items(official_only=True, include_disabled=False):
        shop_name = str(item.get("shop_name") or "").strip() or "官方商店"
        _append_item_source_label(
            catalog,
            str(item.get("item_kind") or ""),
            int(item.get("item_ref_id") or 0),
            f"官坊：{shop_name}",
        )

    for task in list_tasks(enabled_only=True):
        if int(task.get("owner_tg") or 0) > 0:
            continue
        task_scope = str(task.get("task_scope") or "").strip()
        if task_scope not in {"official", "sect"}:
            continue
        title = str(task.get("title") or "").strip() or "未命名任务"
        prefix = "官方任务" if task_scope == "official" else "宗门任务"
        _append_item_source_label(
            catalog,
            str(task.get("reward_item_kind") or ""),
            int(task.get("reward_item_ref_id") or 0),
            f"{prefix}：{title}",
        )

    for boss in list_boss_configs(enabled_only=True):
        boss_name = str(boss.get("name") or "").strip() or "未命名Boss"
        for field, item_kind in BOSS_LOOT_SOURCE_FIELDS:
            for loot in boss.get(field) or []:
                _append_item_source_label(
                    catalog,
                    item_kind,
                    int((loot or {}).get("ref_id") or 0),
                    f"Boss：{boss_name}",
                )

    for achievement in list_achievements(enabled_only=True):
        reward = achievement.get("reward_config") or {}
        label = f"成就：{str(achievement.get('name') or '').strip() or '未命名成就'}"
        for reward_item in reward.get("items") or []:
            _append_item_source_label(
                catalog,
                str((reward_item or {}).get("kind") or ""),
                int((reward_item or {}).get("ref_id") or 0),
                label,
            )

    for reward in get_xiuxian_settings().get("gambling_reward_pool") or []:
        if not bool(reward.get("gambling_enabled", reward.get("enabled", True))):
            continue
        _append_item_source_label(
            catalog,
            str(reward.get("item_kind") or ""),
            int(reward.get("item_ref_id") or 0),
            "仙界奇石",
        )

    return {
        key: sorted(values)
        for key, values in catalog.items()
    }


def _item_source_cache_payload(catalog: dict[tuple[str, int], list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (item_kind, ref_id), labels in sorted(catalog.items(), key=lambda row: (row[0][0], row[0][1])):
        rows.append(
            {
                "kind": str(item_kind),
                "ref_id": int(ref_id),
                "labels": sorted(str(label) for label in labels if str(label or "").strip()),
            }
        )
    return rows


def _restore_item_source_catalog(payload: Any) -> dict[tuple[str, int], list[str]]:
    if isinstance(payload, list):
        catalog: dict[tuple[str, int], list[str]] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            item_kind = str(row.get("kind") or "").strip()
            try:
                ref_id = int(row.get("ref_id") or 0)
            except (TypeError, ValueError):
                ref_id = 0
            if not item_kind or ref_id <= 0:
                continue
            labels = [str(label).strip() for label in row.get("labels") or [] if str(label or "").strip()]
            catalog[(item_kind, ref_id)] = sorted(set(labels))
        return catalog

    if isinstance(payload, dict):
        catalog: dict[tuple[str, int], list[str]] = {}
        for raw_key, labels in payload.items():
            item_kind = ""
            ref_id = 0
            if isinstance(raw_key, (list, tuple)) and len(raw_key) == 2:
                item_kind = str(raw_key[0] or "").strip()
                try:
                    ref_id = int(raw_key[1] or 0)
                except (TypeError, ValueError):
                    ref_id = 0
            elif isinstance(raw_key, str) and ":" in raw_key:
                item_kind, raw_ref_id = raw_key.rsplit(":", 1)
                item_kind = item_kind.strip()
                try:
                    ref_id = int(raw_ref_id or 0)
                except (TypeError, ValueError):
                    ref_id = 0
            if not item_kind or ref_id <= 0:
                continue
            label_rows = [labels] if isinstance(labels, str) else (labels or [])
            catalog[(item_kind, ref_id)] = sorted(str(label).strip() for label in label_rows if str(label or "").strip())
        return catalog

    return {}


def get_item_source_catalog() -> dict[tuple[str, int], list[str]]:
    payload = load_multi_versioned_json(
        version_part_groups=ITEM_SOURCE_VERSION_GROUPS,
        cache_parts=("world", "item-sources"),
        ttl=CATALOG_TTL,
        loader=lambda: _item_source_cache_payload(_build_item_source_catalog_uncached()),
    )
    return _restore_item_source_catalog(payload)


def _material_source_catalog() -> dict[int, list[str]]:
    catalog: dict[int, set[str]] = {
        ref_id: set(labels)
        for (item_kind, ref_id), labels in get_item_source_catalog().items()
        if item_kind == "material"
    }
    for recipe in list_recipes(enabled_only=True):
        if str(recipe.get("result_kind") or "") != "material":
            continue
        material_id = int(recipe.get("result_ref_id") or 0)
        if material_id <= 0:
            continue
        catalog.setdefault(material_id, set()).add(f"炼制：{recipe.get('name') or '未知配方'}")
    return {
        material_id: sorted(values)
        for material_id, values in catalog.items()
    }


_RECIPE_SEARCH_SPLIT_RE = re.compile(r"[\s,，、;；:：/|｜()（）\[\]【】<>《》]+")


def _normalize_recipe_search_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _append_recipe_search_terms(terms: list[str], value: Any) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_recipe_search_terms(terms, item)
        return
    text = _normalize_recipe_search_text(value)
    if not text:
        return
    terms.append(text)
    for part in _RECIPE_SEARCH_SPLIT_RE.split(text):
        part = part.strip()
        if part and part != text:
            terms.append(part)


def _recipe_item_search_fields(item: dict[str, Any] | None) -> list[Any]:
    if not item:
        return []
    return [
        item.get("name"),
        item.get("description"),
        item.get("rarity"),
        item.get("quality_label"),
        item.get("quality_description"),
        item.get("quality_feature"),
        item.get("artifact_type_label"),
        item.get("artifact_role_label"),
        item.get("equip_category_label"),
        item.get("equip_slot_label"),
        item.get("pill_type_label"),
        item.get("effect_label"),
        item.get("talisman_type_label"),
        item.get("technique_type_label"),
        item.get("min_realm_stage"),
    ]


def _recipe_search_terms(recipe: dict[str, Any]) -> list[str]:
    recipe_id = int(recipe.get("id") or 0)
    result_ref_id = int(recipe.get("result_ref_id") or 0)
    terms: list[str] = []
    _append_recipe_search_terms(
        terms,
        [
            recipe.get("name"),
            recipe.get("recipe_kind"),
            recipe.get("recipe_kind_label"),
            recipe.get("result_kind"),
            recipe.get("result_kind_label"),
            recipe.get("source"),
            recipe.get("obtained_note"),
            recipe.get("source_text"),
            recipe.get("source_labels"),
            f"配方id{recipe_id}" if recipe_id > 0 else "",
            f"recipe:{recipe_id}" if recipe_id > 0 else "",
            f"成品id{result_ref_id}" if result_ref_id > 0 else "",
        ],
    )
    _append_recipe_search_terms(terms, _recipe_item_search_fields(recipe.get("result_item") or {}))
    for ingredient in recipe.get("ingredients") or []:
        if not isinstance(ingredient, dict):
            continue
        material = ingredient.get("material") or {}
        material_id = int(material.get("id") or ingredient.get("material_id") or 0)
        _append_recipe_search_terms(
            terms,
            [
                ingredient.get("source_text"),
                ingredient.get("sources"),
                f"材料id{material_id}" if material_id > 0 else "",
                _recipe_item_search_fields(material),
            ],
        )
    for check in (recipe.get("material_check") or {}).get("materials") or []:
        if not isinstance(check, dict):
            continue
        _append_recipe_search_terms(
            terms,
            [
                check.get("material_name"),
                check.get("source_text"),
                check.get("sources"),
            ],
        )
    seen: set[str] = set()
    unique_terms: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            unique_terms.append(term)
    return unique_terms


def attach_recipe_search_indexes(recipes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for recipe in recipes:
        if not isinstance(recipe, dict):
            continue
        terms = _recipe_search_terms(recipe)
        recipe["search_tokens"] = terms
        recipe["search_index"] = " ".join(terms)
    return recipes


def build_recipe_catalog(tg: int | None = None) -> list[dict[str, Any]]:
    material_sources = _material_source_catalog()
    item_sources = get_item_source_catalog()
    rows = []
    profile = serialize_profile(get_profile(tg, create=False)) if tg is not None else None
    material_inventory_map: dict[int, int] = {}
    if tg is not None:
        material_inventory_map = {
            int((row.get("material") or {}).get("id") or 0): max(int(row.get("quantity") or 0), 0)
            for row in list_user_materials(tg)
            if int((row.get("material") or {}).get("id") or 0) > 0
        }
    source_rows: list[dict[str, Any]]
    if tg is None:
        source_rows = list_recipes(enabled_only=True)
    else:
        source_rows = []
        for row in list_user_recipes(tg, enabled_only=True):
            recipe = dict(row.get("recipe") or {})
            if not recipe:
                continue
            recipe["owned"] = True
            recipe["source"] = row.get("source")
            recipe["obtained_note"] = row.get("obtained_note")
            source_rows.append(recipe)
    for recipe in source_rows:
        recipe_id = int(recipe.get("id") or 0)
        ingredients = []
        fragment_source_labels: list[str] = []
        material_check_rows: list[dict[str, Any]] = []
        max_craft_quantity: int | None = None
        for ingredient in list_recipe_ingredients(recipe["id"]):
            ingredient = dict(ingredient or {})
            material = ingredient.get("material") or {}
            material_id = int(material.get("id") or ingredient.get("material_id") or 0)
            source_labels = material_sources.get(material_id, [])
            ingredient["sources"] = source_labels
            ingredient["source_text"] = "、".join(source_labels[:4]) if source_labels else "暂未标注"
            required_quantity = max(int(ingredient.get("quantity") or 1), 1)
            owned_quantity = material_inventory_map.get(material_id, 0) if tg is not None else 0
            missing_quantity = max(required_quantity - owned_quantity, 0)
            ingredient["owned_quantity"] = owned_quantity
            ingredient["required_quantity"] = required_quantity
            ingredient["missing_quantity"] = missing_quantity
            ingredient["enough"] = missing_quantity <= 0
            if tg is not None and material_id > 0:
                craftable_for_material = owned_quantity // required_quantity
                max_craft_quantity = craftable_for_material if max_craft_quantity is None else min(max_craft_quantity, craftable_for_material)
            material_check_rows.append(
                {
                    "material_id": material_id,
                    "material_name": material.get("name") or "材料",
                    "required_quantity": required_quantity,
                    "owned_quantity": owned_quantity,
                    "missing_quantity": missing_quantity,
                    "enough": missing_quantity <= 0,
                    "sources": source_labels,
                    "source_text": ingredient["source_text"],
                }
            )
            material_name = str(material.get("name") or "").strip()
            if "残页" in material_name:
                for label in source_labels:
                    normalized_label = str(label or "").strip()
                    if normalized_label and normalized_label not in fragment_source_labels:
                        fragment_source_labels.append(normalized_label)
            ingredients.append(ingredient)
        recipe["ingredients"] = ingredients
        missing_materials = [row for row in material_check_rows if int(row.get("missing_quantity") or 0) > 0]
        can_craft = bool(tg is not None and ingredients and not missing_materials)
        if tg is not None and ingredients and max_craft_quantity is None:
            max_craft_quantity = 0
        recipe["material_check"] = {
            "can_craft": can_craft,
            "max_craft_quantity": max(int(max_craft_quantity or 0), 0) if tg is not None else None,
            "missing_count": len(missing_materials),
            "missing_materials": missing_materials,
            "materials": material_check_rows,
        }
        recipe_source_labels = item_sources.get(("recipe", recipe_id), [])
        resolved_source_labels = recipe_source_labels or fragment_source_labels
        recipe["source_labels"] = resolved_source_labels
        recipe["source_text"] = "、".join(resolved_source_labels[:4]) if resolved_source_labels else ""
        recipe["result_item"] = _get_item_payload(recipe["result_kind"], int(recipe["result_ref_id"]))
        if str(recipe.get("result_kind") or "") == "talisman":
            recipe["result_item"] = _attach_talisman_preview_effects(recipe["result_item"], profile)
        if profile and profile.get("consented"):
            preview = _recipe_success_preview(recipe, ingredients, profile, recipe["result_item"])
            recipe["current_success_rate"] = preview["current_success_rate"]
        recipe.setdefault("owned", True)
        rows.append(recipe)
    return attach_recipe_search_indexes(rows)


def _recipe_fragment_requirement(recipe_id: int) -> dict[str, Any] | None:
    fragment_rows: list[dict[str, Any]] = []
    for ingredient in list_recipe_ingredients(recipe_id):
        material = dict(ingredient.get("material") or {})
        if not material and int(ingredient.get("material_id") or 0) > 0:
            material = serialize_material(get_material(int(ingredient.get("material_id") or 0))) or {}
        material_name = str(material.get("name") or "")
        if "残页" not in material_name:
            continue
        fragment_rows.append(
            {
                **ingredient,
                "material": material,
                "material_id": int(material.get("id") or ingredient.get("material_id") or 0),
                "quantity": max(int(ingredient.get("quantity") or 1), 1),
            }
        )
    if len(fragment_rows) != 1:
        return None
    return fragment_rows[0]


def build_recipe_fragment_synthesis_catalog(tg: int) -> list[dict[str, Any]]:
    owned_recipe_ids = {
        int((row.get("recipe") or {}).get("id") or 0)
        for row in list_user_recipes(tg)
        if int((row.get("recipe") or {}).get("id") or 0) > 0
    }
    inventory_map = {
        int((row.get("material") or {}).get("id") or 0): max(int(row.get("quantity") or 0), 0)
        for row in list_user_materials(tg)
        if int((row.get("material") or {}).get("id") or 0) > 0
    }
    rows: list[dict[str, Any]] = []
    for recipe in list_recipes(enabled_only=True):
        recipe_id = int(recipe.get("id") or 0)
        if recipe_id <= 0 or recipe_id in owned_recipe_ids:
            continue
        fragment_requirement = _recipe_fragment_requirement(recipe_id)
        if fragment_requirement is None:
            continue
        material = dict(fragment_requirement.get("material") or {})
        material_id = int(material.get("id") or fragment_requirement.get("material_id") or 0)
        required_quantity = max(int(fragment_requirement.get("quantity") or 1), 1)
        owned_quantity = inventory_map.get(material_id, 0)
        result_item = _get_item_payload(str(recipe.get("result_kind") or ""), int(recipe.get("result_ref_id") or 0))
        rows.append(
            {
                "recipe_id": recipe_id,
                "recipe_name": recipe.get("name"),
                "recipe_kind": recipe.get("recipe_kind"),
                "recipe_kind_label": recipe.get("recipe_kind_label"),
                "required_material_id": material_id,
                "required_material_name": material.get("name") or "残页",
                "required_quantity": required_quantity,
                "owned_quantity": owned_quantity,
                "can_synthesize": owned_quantity >= required_quantity,
                "result_item": result_item,
                "result_item_name": (result_item or {}).get("name") or "未知成品",
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            0 if item.get("can_synthesize") else 1,
            str(item.get("recipe_kind_label") or item.get("recipe_kind") or ""),
            str(item.get("recipe_name") or ""),
        ),
    )


def synthesize_recipe_fragment_for_user(tg: int, recipe_id: int) -> dict[str, Any]:
    recipe = serialize_recipe(get_recipe(recipe_id))
    if recipe is None or not recipe.get("enabled"):
        raise ValueError("配方不存在")
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立")
    if any(int((row.get("recipe") or {}).get("id") or 0) == int(recipe_id) for row in list_user_recipes(tg)):
        raise ValueError("你已掌握这张配方，无需再次参悟")
    fragment_requirement = _recipe_fragment_requirement(int(recipe_id))
    if fragment_requirement is None:
        raise ValueError("该配方不支持残页参悟")
    material = dict(fragment_requirement.get("material") or {})
    material_id = int(material.get("id") or fragment_requirement.get("material_id") or 0)
    if material_id <= 0:
        raise ValueError("该残页配置异常，请联系管理员修复")
    required_quantity = max(int(fragment_requirement.get("quantity") or 1), 1)
    with Session() as session:
        row = (
            session.query(XiuxianMaterialInventory)
            .filter(XiuxianMaterialInventory.tg == tg, XiuxianMaterialInventory.material_id == material_id)
            .with_for_update()
            .first()
        )
        if row is None or int(row.quantity or 0) < required_quantity:
            raise ValueError(f"残页不足：{material.get('name') or '对应残页'}")
        row.quantity -= required_quantity
        row.updated_at = utcnow()
        if row.quantity <= 0:
            session.delete(row)
        session.commit()
    try:
        granted = grant_recipe_to_user(
            tg,
            int(recipe_id),
            source="fragment_synthesis",
            obtained_note="残页参悟",
        )
    except Exception:
        with Session() as session:
            refund_row = (
                session.query(XiuxianMaterialInventory)
                .filter(XiuxianMaterialInventory.tg == tg, XiuxianMaterialInventory.material_id == material_id)
                .with_for_update()
                .first()
            )
            if refund_row is None:
                refund_row = XiuxianMaterialInventory(
                    tg=tg,
                    material_id=material_id,
                    quantity=required_quantity,
                )
                session.add(refund_row)
            else:
                refund_row.quantity = max(int(refund_row.quantity or 0), 0) + required_quantity
                refund_row.updated_at = utcnow()
            session.commit()
        raise
    recipe_payload = dict(granted.get("recipe") or recipe)
    recipe_payload["result_item"] = _get_item_payload(str(recipe_payload.get("result_kind") or ""), int(recipe_payload.get("result_ref_id") or 0))
    create_journal(
        tg,
        "craft",
        "配方参悟",
        f"以【{material.get('name') or '残页'}】×{required_quantity} 为引，神识贯通，参悟出配方【{recipe_payload.get('name') or '未知配方'}】。",
    )
    return {
        "recipe": recipe_payload,
        "fragment_material": material,
        "required_quantity": required_quantity,
        "result_item": recipe_payload.get("result_item"),
        "profile": serialize_profile(get_profile(tg, create=False)),
    }


def sync_recipe_with_ingredients_by_name(
    *,
    name: str,
    recipe_kind: str,
    result_kind: str,
    result_ref_id: int,
    result_quantity: int,
    base_success_rate: int,
    broadcast_on_success: bool,
    ingredients: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "name": str(name or "").strip(),
        "recipe_kind": str(recipe_kind or "").strip() or "artifact",
        "result_kind": str(result_kind or "").strip() or "material",
        "result_ref_id": max(int(result_ref_id or 0), 1),
        "result_quantity": max(int(result_quantity or 1), 1),
        "base_success_rate": max(min(int(base_success_rate or 60), 100), 1),
        "broadcast_on_success": bool(broadcast_on_success),
        "enabled": True,
    }
    with Session() as session:
        recipe = session.query(XiuxianRecipe).filter(XiuxianRecipe.name == payload["name"]).first()
        if recipe is None:
            recipe = XiuxianRecipe(**payload)
            session.add(recipe)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                recipe = session.query(XiuxianRecipe).filter(XiuxianRecipe.name == payload["name"]).first()
                if recipe is None:
                    raise
                for key, value in payload.items():
                    setattr(recipe, key, value)
                recipe.updated_at = utcnow()
                session.commit()
            session.refresh(recipe)
        else:
            for key, value in payload.items():
                setattr(recipe, key, value)
            recipe.updated_at = utcnow()
            session.commit()
            session.refresh(recipe)
        recipe_id = int(recipe.id)
    recipe_payload = serialize_recipe(get_recipe(recipe_id))
    recipe_payload["ingredients"] = replace_recipe_ingredients(
        recipe_id,
        [
            {
                "material_id": int(item.get("material_id") or 0),
                "quantity": max(int(item.get("quantity") or 1), 1),
            }
            for item in ingredients
            if int(item.get("material_id") or 0) > 0
        ],
    )
    recipe_payload["result_item"] = _get_item_payload(payload["result_kind"], payload["result_ref_id"])
    return recipe_payload


def patch_recipe_with_ingredients(
    recipe_id: int,
    *,
    name: str,
    recipe_kind: str,
    result_kind: str,
    result_ref_id: int,
    result_quantity: int,
    base_success_rate: int,
    broadcast_on_success: bool,
    ingredients: list[dict[str, Any]],
) -> dict[str, Any]:
    with Session() as session:
        recipe = session.query(XiuxianRecipe).filter(XiuxianRecipe.id == recipe_id).first()
        if recipe is None:
            raise ValueError("配方不存在")
        recipe.name = str(name or "").strip()
        recipe.recipe_kind = str(recipe_kind or "").strip() or recipe.recipe_kind
        recipe.result_kind = str(result_kind or "").strip() or recipe.result_kind
        recipe.result_ref_id = max(int(result_ref_id or 0), 1)
        recipe.result_quantity = max(int(result_quantity or 1), 1)
        recipe.base_success_rate = max(min(int(base_success_rate or 60), 100), 1)
        recipe.broadcast_on_success = bool(broadcast_on_success)
        recipe.enabled = True
        recipe.updated_at = utcnow()
        session.commit()
    recipe_payload = serialize_recipe(get_recipe(recipe_id))
    recipe_payload["ingredients"] = replace_recipe_ingredients(
        recipe_id,
        [
            {
                "material_id": int(item.get("material_id") or 0),
                "quantity": max(int(item.get("quantity") or 1), 1),
            }
            for item in ingredients
            if int(item.get("material_id") or 0) > 0
        ],
    )
    recipe_payload["result_item"] = _get_item_payload(recipe_payload["result_kind"], int(recipe_payload["result_ref_id"]))
    return recipe_payload


def sync_scene_with_drops_by_name(
    *,
    name: str,
    description: str = "",
    image_url: str = "",
    max_minutes: int = 60,
    event_pool: list[dict[str, Any]] | list[str] | None = None,
    drops: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "name": str(name or "").strip(),
        "description": str(description or "").strip(),
        "image_url": str(image_url or "").strip(),
        "max_minutes": max(min(int(max_minutes or 60), 60), 1),
        "event_pool": event_pool or [],
        "enabled": True,
    }
    with Session() as session:
        scene = session.query(XiuxianScene).filter(XiuxianScene.name == payload["name"]).first()
        if scene is None:
            scene = XiuxianScene(**payload)
            session.add(scene)
            session.commit()
            session.refresh(scene)
        else:
            scene.description = payload["description"]
            scene.image_url = payload["image_url"] or None
            scene.max_minutes = payload["max_minutes"]
            scene.event_pool = payload["event_pool"]
            scene.enabled = True
            scene.updated_at = utcnow()
            session.commit()
            session.refresh(scene)
        session.query(XiuxianSceneDrop).filter(XiuxianSceneDrop.scene_id == scene.id).delete()
        for drop in drops or []:
            session.add(
                XiuxianSceneDrop(
                    scene_id=scene.id,
                    reward_kind=str(drop.get("reward_kind") or "material"),
                    reward_ref_id=drop.get("reward_ref_id"),
                    quantity_min=max(int(drop.get("quantity_min", 1) or 1), 1),
                    quantity_max=max(int(drop.get("quantity_max", drop.get("quantity_min", 1)) or 1), 1),
                    weight=max(int(drop.get("weight", 1) or 1), 1),
                    stone_reward=max(int(drop.get("stone_reward", 0) or 0), 0),
                    event_text=str(drop.get("event_text") or "").strip() or None,
                )
            )
        scene_id = int(scene.id)
        session.commit()
    scene_payload = serialize_scene(get_scene(scene_id))
    scene_payload["drops"] = list_scene_drops(scene_id)
    return scene_payload


def patch_scene_with_drops(
    scene_id: int,
    *,
    name: str,
    description: str = "",
    image_url: str = "",
    max_minutes: int = 60,
    event_pool: list[dict[str, Any]] | list[str] | None = None,
    drops: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with Session() as session:
        scene = session.query(XiuxianScene).filter(XiuxianScene.id == scene_id).first()
        if scene is None:
            raise ValueError("场景不存在")
        scene.name = str(name or "").strip()
        scene.description = str(description or "").strip()
        scene.image_url = str(image_url or "").strip() or None
        scene.max_minutes = max(min(int(max_minutes or 60), 60), 1)
        scene.event_pool = event_pool or []
        scene.enabled = True
        scene.updated_at = utcnow()
        session.query(XiuxianSceneDrop).filter(XiuxianSceneDrop.scene_id == scene.id).delete()
        for drop in drops or []:
            session.add(
                XiuxianSceneDrop(
                    scene_id=scene.id,
                    reward_kind=str(drop.get("reward_kind") or "material"),
                    reward_ref_id=drop.get("reward_ref_id"),
                    quantity_min=max(int(drop.get("quantity_min", 1) or 1), 1),
                    quantity_max=max(int(drop.get("quantity_max", drop.get("quantity_min", 1)) or 1), 1),
                    weight=max(int(drop.get("weight", 1) or 1), 1),
                    stone_reward=max(int(drop.get("stone_reward", 0) or 0), 0),
                    event_text=str(drop.get("event_text") or "").strip() or None,
                )
            )
        session.commit()
    scene_payload = serialize_scene(get_scene(scene_id))
    scene_payload["drops"] = list_scene_drops(scene_id)
    return scene_payload


def _weighted_random_choice(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    total_weight = sum(max(int(item.get("weight") or 0), 1) for item in rows)
    cursor = random.randint(1, max(total_weight, 1))
    current = 0
    for item in rows:
        current += max(int(item.get("weight") or 0), 1)
        if cursor <= current:
            return item
    return rows[-1]


def _recipe_like_bonus_item(kind: str | None, ref_id: int | None) -> bool:
    if kind in {"recipe", "technique"}:
        return True
    item = _get_item_payload(str(kind or ""), int(ref_id or 0)) if kind and ref_id else None
    name = str((item or {}).get("name") or "")
    return "谱" in name or "残页" in name or "图录" in name


def _build_exploration_outcome(
    scene: dict[str, Any],
    chosen_drop: dict[str, Any] | None,
    fortune: int,
    divine_sense: int,
) -> dict[str, Any]:
    event = _weighted_random_choice(scene.get("event_pool") or []) or {}
    stone_bonus = 0
    stone_loss = 0
    bonus_reward = None
    if event:
        stone_bonus_min = max(int(event.get("stone_bonus_min") or 0), 0)
        stone_bonus_max = max(int(event.get("stone_bonus_max") or stone_bonus_min), stone_bonus_min)
        if stone_bonus_max > 0:
            stone_bonus = random.randint(stone_bonus_min, stone_bonus_max)
        stone_loss_min = max(int(event.get("stone_loss_min") or 0), 0)
        stone_loss_max = max(int(event.get("stone_loss_max") or stone_loss_min), stone_loss_min)
        if stone_loss_max > 0:
            mitigation = max(fortune // 4 + divine_sense // 6, 0)
            stone_loss = max(random.randint(stone_loss_min, stone_loss_max) - mitigation, 0)
        bonus_reward_kind = event.get("bonus_reward_kind")
        bonus_reward_ref_id = int(event.get("bonus_reward_ref_id") or 0)
        bonus_chance = max(min(int(event.get("bonus_chance") or 0), 100), 0)
        if bonus_reward_kind and bonus_reward_ref_id > 0 and roll_probability_percent(bonus_chance)["success"]:
            bonus_quantity_min = max(int(event.get("bonus_quantity_min") or 1), 1)
            bonus_quantity_max = max(int(event.get("bonus_quantity_max") or bonus_quantity_min), bonus_quantity_min)
            bonus_reward = {
                "kind": bonus_reward_kind,
                "ref_id": bonus_reward_ref_id,
                "quantity": random.randint(bonus_quantity_min, bonus_quantity_max),
                "is_recipe_like": _recipe_like_bonus_item(bonus_reward_kind, bonus_reward_ref_id),
            }
    parts = []
    if event.get("name"):
        parts.append(str(event.get("name")))
    if chosen_drop and chosen_drop.get("event_text"):
        parts.append(str(chosen_drop.get("event_text")))
    if event.get("description"):
        parts.append(str(event.get("description")))
    return {
        "event": event,
        "stone_bonus": stone_bonus,
        "stone_loss": stone_loss,
        "bonus_reward": bonus_reward,
        "empty_handed": chosen_drop is None,
        "event_text": "，".join([part for part in parts if part]).strip("，"),
    }


def craft_recipe_for_user(tg: int, recipe_id: int, quantity: int = 1) -> dict[str, Any]:
    recipe = serialize_recipe(get_recipe(recipe_id))
    if recipe is None or not recipe.get("enabled"):
        raise ValueError("配方不存在")
    if not any(int((row.get("recipe") or {}).get("id") or 0) == int(recipe_id) for row in list_user_recipes(tg, enabled_only=True)):
        raise ValueError("你尚未掌握这张配方，无法开炉炼制")
    requested_quantity = int(quantity or 1)
    if requested_quantity <= 0:
        raise ValueError("炼制数量必须大于 0")
    if requested_quantity > 99:
        raise ValueError("单次最多只能连续炼制 99 炉")
    if str(recipe.get("recipe_kind") or "") != "pill" and requested_quantity > 1:
        raise ValueError("当前仅丹药配方支持批量炼制")
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立")
    active_talisman = serialize_talisman(get_talisman(int(profile.get("active_talisman_id") or 0))) if profile.get("active_talisman_id") else None
    talisman_active_effects = _legacy_service().resolve_talisman_active_effects(profile, active_talisman) if active_talisman else {}
    ingredients = list_recipe_ingredients(recipe_id)
    if not ingredients:
        raise ValueError("该配方还没有配置材料")
    result_item = _get_item_payload(recipe["result_kind"], int(recipe["result_ref_id"]))
    if result_item is None:
        raise ValueError("该配方的成品配置无效，请联系管理员修复后再炼制")
    inventory_map = {row["material"]["id"]: row for row in list_user_materials(tg)}
    missing_rows: list[str] = []
    for item in ingredients:
        material_id = int(item["material_id"])
        owned_quantity = max(int((inventory_map.get(material_id) or {}).get("quantity") or 0), 0)
        required_quantity = max(int(item["quantity"] or 0), 0) * requested_quantity
        if owned_quantity < required_quantity:
            missing_rows.append(
                f"{item['material']['name']} 缺 {required_quantity - owned_quantity}（需 {required_quantity}，持有 {owned_quantity}）"
            )
    if missing_rows:
        raise ValueError("材料不足：" + "；".join(missing_rows))
    with Session() as session:
        for item in ingredients:
            material_id = int(item["material_id"])
            required_quantity = int(item["quantity"] or 0) * requested_quantity
            consumed, owned_quantity = consume_user_materials_in_session(
                session,
                tg,
                material_id,
                required_quantity,
            )
            if not consumed:
                raise ValueError(
                    f"材料数量已变更：{item['material']['name']} 缺 {max(required_quantity - owned_quantity, 0)}"
                    "，请刷新后重新尝试"
                )
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
    preview = _recipe_success_preview(
        recipe,
        ingredients,
        profile,
        result_item,
        talisman_active_effects=talisman_active_effects,
    )
    result_quality = int(preview["result_quality"])
    fortune = int(preview["fortune"])
    success_rate = float(preview["raw_success_rate"])
    rolls: list[int] = []
    success_count = 0
    failure_count = 0
    raw_base_rate = float(success_rate)
    for _ in range(requested_quantity):
        success_roll = roll_probability_percent(
            raw_base_rate,
            actor_fortune=fortune,
            actor_weight=0.25,
            minimum=5,
            maximum=95,
        )
        rolls.append(int(success_roll["roll"]))
        if bool(success_roll["success"]):
            success_count += 1
        else:
            failure_count += 1
    success = success_count > 0
    total_reward_quantity = success_count * int(recipe["result_quantity"])
    reward = None
    if total_reward_quantity > 0:
        reward = _grant_item_by_kind(tg, recipe["result_kind"], int(recipe["result_ref_id"]), total_reward_quantity)
        if requested_quantity > 1:
            create_journal(
                tg,
                "craft",
                "批量炼制有成",
                f"连开 {requested_quantity} 炉，成丹 {success_count} 次，炼得【{(result_item or {}).get('name', '成品')}】×{total_reward_quantity}",
            )
        else:
            create_journal(tg, "craft", "开炉成丹", f"炉火纯青，成功炼得【{(result_item or {}).get('name', '成品')}】")
    else:
        if requested_quantity > 1:
            create_journal(
                tg,
                "craft",
                "批量炼制失利",
                f"连开 {requested_quantity} 炉，尝试炼得【{(result_item or {}).get('name', '成品')}】，然全部化作飞灰",
            )
        else:
            create_journal(tg, "craft", "炼制失利", f"炉中火光大盛，然【{(result_item or {}).get('name', '成品')}】终究未能成形")
    if active_talisman:
        _legacy_service().set_active_talisman(tg, None)
    ingredient_names = {str((item.get("material") or {}).get("name") or "") for item in ingredients}
    is_repair_recipe = any("破损" in name or "残片" in name for name in ingredient_names) or "修复" in str(recipe.get("name") or "")
    if requested_quantity == 1:
        achievement_unlocks = record_craft_metrics(tg, success=success, repair_success=bool(success and is_repair_recipe))
    else:
        increments = {
            "craft_attempt_count": requested_quantity,
            "craft_success_count": success_count,
        }
        if is_repair_recipe and success_count > 0:
            increments["repair_success_count"] = success_count
        achievement_unlocks = record_achievement_progress(tg, increments, source="craft")["unlocks"] if any(
            int(value or 0) > 0 for value in increments.values()
        ) else []
    partial_success = success_count > 0 and failure_count > 0
    if requested_quantity > 1:
        if total_reward_quantity > 0:
            summary_text = (
                f"连续炼制 {requested_quantity} 炉，成功 {success_count} 炉，失败 {failure_count} 炉，"
                f"共获得 {(result_item or {}).get('name', '成品')} ×{total_reward_quantity}"
            )
        else:
            summary_text = f"连续炼制 {requested_quantity} 炉，全部失败，材料已消耗"
    else:
        summary_text = "丹成炉开，成品已发放。" if success else "炉火未济，材料已消耗。"
    return {
        "success": success,
        "all_success": success_count == requested_quantity,
        "partial_success": partial_success,
        "roll": rolls[0] if len(rolls) == 1 else None,
        "rolls": rolls if len(rolls) > 1 else [],
        "success_rate": success_rate,
        "current_success_rate": float(preview["current_success_rate"]),
        "recipe": recipe,
        "result_item": result_item,
        "result_quality": result_quality,
        "reward": reward,
        "requested_quantity": requested_quantity,
        "crafted_times": requested_quantity,
        "success_count": success_count,
        "failure_count": failure_count,
        "total_reward_quantity": total_reward_quantity,
        "summary_text": summary_text,
        "should_broadcast": bool(success and recipe.get("broadcast_on_success") and result_quality >= max(int(get_xiuxian_settings().get("high_quality_broadcast_level", DEFAULT_SETTINGS["high_quality_broadcast_level"]) or 6), 6)),
        "profile": serialize_profile(get_profile(tg, create=False)),
        "achievement_unlocks": achievement_unlocks,
        "active_talisman": None if not active_talisman else {
            "name": active_talisman.get("name"),
            "effects": talisman_active_effects,
            "summary": _legacy_service().active_talisman_effect_summary(talisman_active_effects),
        },
    }


def _recipe_success_preview(
    recipe: dict[str, Any],
    ingredients: list[dict[str, Any]],
    profile: dict[str, Any],
    result_item: dict[str, Any] | None = None,
    *,
    total_quality: int | None = None,
    total_count: int | None = None,
    talisman_active_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result_payload = result_item or _get_item_payload(str(recipe.get("result_kind") or ""), int(recipe.get("result_ref_id") or 0))
    result_quality = _quality_from_item(str(recipe.get("result_kind") or ""), result_payload)
    if total_quality is None or total_count is None:
        computed_total_quality = 0
        computed_total_count = 0
        for item in ingredients or []:
            quantity = int(item.get("quantity") or 0)
            material = item.get("material") or {}
            computed_total_quality += int(material.get("quality_level", 1) or 1) * quantity
            computed_total_count += quantity
        total_quality = computed_total_quality
        total_count = computed_total_count
    avg_material_quality = float(total_quality or 0) / max(int(total_count or 0), 1)
    sect_effects = get_sect_effects(profile)
    comprehension = int(profile.get("comprehension") or 0)
    fortune = int(profile.get("fortune") or 0)
    root_quality_level = int(profile.get("root_quality_level") or 1)
    quality_bonus = int(avg_material_quality * 4) - result_quality * 6
    attribute_bonus = max(comprehension - 12, 0) // 2 + max(fortune - 10, 0) // 3 + root_quality_level * 2
    raw_success_rate = (
        int(recipe.get("base_success_rate") or 0)
        + quality_bonus
        + attribute_bonus
        + int(sect_effects.get("cultivation_bonus", 0))
        + int(sect_effects.get("craft_success_rate", 0))
        + int(round(float((talisman_active_effects or {}).get("craft_success_bonus") or 0)))
    )
    if str(profile.get("root_quality") or "") == "天灵根":
        raw_success_rate += 4
    elif str(profile.get("root_quality") or "") == "变异灵根":
        raw_success_rate += 3
    raw_success_rate = max(min(raw_success_rate, 95), 5)
    current_success_rate = adjust_probability_percent(
        raw_success_rate,
        actor_fortune=fortune,
        actor_weight=0.25,
        minimum=5,
        maximum=95,
    )
    return {
        "result_quality": result_quality,
        "fortune": fortune,
        "raw_success_rate": round(float(raw_success_rate), 2),
        "current_success_rate": round(float(current_success_rate), 2),
    }


def create_scene_with_drops(
    *,
    name: str,
    description: str = "",
    image_url: str = "",
    max_minutes: int = 60,
    event_pool: list[str] | None = None,
    drops: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scene = create_scene(
        name=name,
        description=description,
        image_url=image_url,
        max_minutes=max(min(int(max_minutes or 60), 60), 1),
        event_pool=event_pool or [],
        enabled=True,
    )
    created_drops = []
    for drop in drops or []:
        created_drops.append(
            create_scene_drop(
                scene_id=scene["id"],
                reward_kind=str(drop.get("reward_kind") or "material"),
                reward_ref_id=drop.get("reward_ref_id"),
                quantity_min=max(int(drop.get("quantity_min", 1) or 1), 1),
                quantity_max=max(int(drop.get("quantity_max", drop.get("quantity_min", 1)) or 1), 1),
                weight=max(int(drop.get("weight", 1) or 1), 1),
                stone_reward=max(int(drop.get("stone_reward", 0) or 0), 0),
                event_text=str(drop.get("event_text") or "").strip() or None,
            )
        )
    scene["drops"] = created_drops
    return scene


def _get_active_exploration(tg: int) -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianExploration)
            .filter(XiuxianExploration.tg == tg, XiuxianExploration.claimed.is_(False))
            .order_by(XiuxianExploration.id.desc())
            .first()
        )
        return serialize_exploration(row)


def start_exploration_for_user(tg: int, scene_id: int, minutes: int) -> dict[str, Any]:
    _, profile = _require_alive_profile_data(tg, "进入秘境")
    active = _get_active_exploration(tg)
    if active and not active.get("claimed"):
        raise ValueError("你还有未结算的探索")
    scene = serialize_scene(get_scene(scene_id))
    if not scene or not scene.get("enabled"):
        raise ValueError("场景不存在")
    duration = max(min(int(minutes or 60), int(scene.get("max_minutes") or 60), 60), 1)
    drops = list_scene_drops(scene_id)
    if not drops:
        raise ValueError("该场景尚未配置掉落")
    divine_sense = int(profile.get("divine_sense") or 0)
    fortune = int(profile.get("fortune") or 0)
    root_quality_level = int(profile.get("root_quality_level") or 1)
    weight_rules = _exploration_drop_weight_rules()
    weighted_rows: list[tuple[dict[str, Any], float]] = []
    max_quality = 1
    for drop in drops:
        item_payload = _get_item_payload(str(drop.get("reward_kind") or ""), int(drop.get("reward_ref_id") or 0)) if drop.get("reward_ref_id") else None
        reward_quality = _quality_from_item(str(drop.get("reward_kind") or ""), item_payload)
        max_quality = max(max_quality, reward_quality)
        quality_multiplier = EXPLORATION_QUALITY_WEIGHT_MULTIPLIERS.get(max(min(reward_quality, 7), 1), EXPLORATION_QUALITY_WEIGHT_MULTIPLIERS[1])
        bonus_multiplier = 1.0
        if str(drop.get("reward_kind") or "") == "material":
            bonus_multiplier += min(
                max(divine_sense - 10, 0) / max(int(weight_rules["material_divine_sense_divisor"]), 1) * 0.03,
                0.45,
            )
        if reward_quality >= int(weight_rules["high_quality_threshold"]):
            bonus_multiplier += min(
                max(fortune - 10, 0) / max(int(weight_rules["high_quality_fortune_divisor"]), 1) * 0.025
                + max(root_quality_level - int(weight_rules["high_quality_root_level_start"]), 0) * 0.05,
                0.55,
            )
        effective_weight = max(float(drop.get("weight") or 1), 1.0) * quality_multiplier * bonus_multiplier
        if effective_weight > 0:
            weighted_rows.append((drop, effective_weight))
    empty_chance = _exploration_empty_chance(max_quality, fortune, divine_sense, root_quality_level)
    chosen = None
    if weighted_rows and random.random() >= empty_chance:
        chosen = random.choices(
            [row[0] for row in weighted_rows],
            weights=[row[1] for row in weighted_rows],
            k=1,
        )[0]
    quantity = random.randint(int(chosen.get("quantity_min") or 1), int(chosen.get("quantity_max") or chosen.get("quantity_min") or 1)) if chosen else 0
    outcome = _build_exploration_outcome(scene, chosen, fortune, divine_sense)
    outcome["empty_chance_percent"] = round(empty_chance * 100.0, 2)
    event_text = outcome.get("event_text") or (chosen.get("event_text") if chosen else "") or ""
    if not chosen and not event_text:
        event_text = "你在秘境中搜寻良久，最终空手而归。"
    with Session() as session:
        exploration = XiuxianExploration(
            tg=tg,
            scene_id=scene_id,
            started_at=utcnow(),
            end_at=utcnow() + timedelta(minutes=duration),
            claimed=False,
            reward_kind=chosen.get("reward_kind") if chosen else None,
            reward_ref_id=chosen.get("reward_ref_id") if chosen else None,
            reward_quantity=quantity,
            stone_reward=int(chosen.get("stone_reward", 0) or 0) if chosen else 0,
            event_text=event_text or None,
            outcome_payload=outcome,
        )
        session.add(exploration)
        session.commit()
        session.refresh(exploration)
        return {"scene": scene, "exploration": serialize_exploration(exploration)}


def claim_exploration_for_user(tg: int, exploration_id: int) -> dict[str, Any]:
    _require_alive_profile_data(tg, "结算探索")
    exploration_payload: dict[str, Any] | None = None
    reward_kind = None
    reward_ref_id = 0
    reward_quantity = 0
    stone_reward = 0
    outcome: dict[str, Any] = {}
    bonus_payload: dict[str, Any] | None = None
    with Session() as session:
        exploration = (
            session.query(XiuxianExploration)
            .filter(XiuxianExploration.id == exploration_id, XiuxianExploration.tg == tg)
            .with_for_update()
            .first()
        )
        if exploration is None:
            raise ValueError("探索记录不存在")
        if exploration.claimed:
            raise ValueError("该探索已领取过")
        if exploration.end_at > utcnow():
            raise ValueError("探索尚未结束")
        outcome = dict(exploration.outcome_payload or {})
        bonus_payload = outcome.get("bonus_reward") if isinstance(outcome.get("bonus_reward"), dict) else None
        technique_rewards = []
        if exploration.reward_kind == "technique" and exploration.reward_ref_id:
            technique_rewards.append(int(exploration.reward_ref_id))
        if bonus_payload and str(bonus_payload.get("kind") or "") == "technique" and int(bonus_payload.get("ref_id") or 0) > 0:
            technique_rewards.append(int(bonus_payload.get("ref_id")))
        reward_kind = exploration.reward_kind
        reward_ref_id = int(exploration.reward_ref_id or 0)
        reward_quantity = int(exploration.reward_quantity or 0)
        stone_reward = int(exploration.stone_reward or 0)
        exploration.claimed = True
        exploration.updated_at = utcnow()
        session.commit()
        session.refresh(exploration)
        exploration_payload = serialize_exploration(exploration)
    reward_item = None
    if reward_kind and reward_ref_id and reward_quantity > 0:
        reward_item = _grant_item_by_kind(tg, reward_kind, reward_ref_id, reward_quantity)
    bonus_reward = None
    if bonus_payload and bonus_payload.get("kind") and int(bonus_payload.get("ref_id") or 0) > 0 and int(bonus_payload.get("quantity") or 0) > 0:
        bonus_reward = _grant_item_by_kind(
            tg,
            str(bonus_payload.get("kind")),
            int(bonus_payload.get("ref_id")),
            int(bonus_payload.get("quantity")),
        )
    profile = get_profile(tg, create=False)
    event_stone_bonus = max(int(outcome.get("stone_bonus") or 0), 0)
    event_stone_loss = max(int(outcome.get("stone_loss") or 0), 0)
    current_stone = int(profile.spiritual_stone or 0) if profile else 0
    actual_stone_loss = min(current_stone, event_stone_loss)
    total_stone_delta = stone_reward + event_stone_bonus - actual_stone_loss
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if updated is None or not updated.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        if total_stone_delta:
            apply_spiritual_stone_delta(
                session,
                tg,
                total_stone_delta,
                action_text="结算探索",
                enforce_currency_lock=True,
                allow_dead=False,
                apply_tribute=total_stone_delta > 0,
            )
        session.commit()
    event_type = str((outcome.get("event") or {}).get("event_type") or "").strip()
    recipe_like_drop = bool(bonus_payload and bonus_payload.get("is_recipe_like")) or _recipe_like_bonus_item(
        reward_kind,
        reward_ref_id,
    )
    achievement_unlocks = record_exploration_metrics(
        tg,
        event_type=event_type,
        recipe_drop=recipe_like_drop,
    )
    create_journal(
        tg,
        "explore",
        "秘境归来",
        (
            f"此番探索尘埃落定，灵石{'增收' if total_stone_delta >= 0 else '净损'} {abs(total_stone_delta)}。"
            f"{' 另有一缕机缘傍身。' if bonus_reward else ''}"
        ),
    )
    return {
        "exploration": exploration_payload,
        "reward_item": reward_item,
        "bonus_reward": bonus_reward,
        "stone_gain": stone_reward + event_stone_bonus,
        "stone_loss": actual_stone_loss,
        "stone_delta": total_stone_delta,
        "profile": _full_profile_bundle(tg)["profile"],
        "achievement_unlocks": achievement_unlocks,
    }


def create_red_envelope_for_user(
    *,
    tg: int,
    cover_text: str,
    image_url: str = "",
    mode: str,
    amount_total: int,
    count_total: int,
    target_tg: int | None = None,
    group_chat_id: int | None = None,
) -> dict[str, Any]:
    profile, _ = _require_alive_profile_data(tg, "发放红包")
    assert_currency_operation_allowed(tg, "发放红包", profile=profile)
    normalized_mode = str(mode or "").strip()
    amount_total = max(int(amount_total or 0), 1)
    count_total = max(int(count_total or 1), 1)
    exclusive_target_tg = int(target_tg or 0) if normalized_mode == "exclusive" else 0
    if normalized_mode == "exclusive":
        if exclusive_target_tg <= 0:
            raise ValueError("专属红包需要指定目标 TG ID。")
        if exclusive_target_tg == int(tg):
            raise ValueError("不能给自己发专属红包。")
    if int(profile.spiritual_stone or 0) < amount_total:
        raise ValueError("灵石不足")
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if updated is None or not updated.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        if normalized_mode == "exclusive" and _is_active_spouse_pair(session, tg, exclusive_target_tg):
            raise ValueError("道侣之间灵石共享，不能互发专属红包。")
        apply_spiritual_stone_delta(
            session,
            tg,
            -amount_total,
            action_text="发放红包",
            enforce_currency_lock=False,
            allow_dead=False,
            apply_tribute=False,
        )
        session.commit()
    with Session() as session:
        envelope = XiuxianRedEnvelope(
            creator_tg=tg,
            cover_text=cover_text or "恭喜发财",
            image_url=image_url or None,
            mode=normalized_mode,
            target_tg=exclusive_target_tg or None,
            amount_total=amount_total,
            count_total=count_total,
            remaining_amount=amount_total,
            remaining_count=count_total,
            status="active",
            group_chat_id=group_chat_id,
        )
        session.add(envelope)
        session.commit()
        session.refresh(envelope)
        serialized = serialize_red_envelope(envelope)
    create_journal(tg, "red_envelope", "发放红包", f"洒出 {amount_total} 灵石红包，题曰【{serialized.get('cover_text') or '福运临门'}】")
    return {
        "envelope": serialized,
        "profile": serialize_profile(get_profile(tg, create=False)),
        "achievement_unlocks": record_red_envelope_metrics(tg, amount_total),
    }


def _draw_red_envelope_amount(envelope: XiuxianRedEnvelope) -> int:
    if int(envelope.remaining_count or 1) <= 1:
        return int(envelope.remaining_amount or 0)
    if envelope.mode == "normal":
        average = max(int(envelope.amount_total or 0) // max(int(envelope.count_total or 1), 1), 1)
        reserve = max(int(envelope.remaining_amount or 0) - (int(envelope.remaining_count or 1) - 1), 1)
        return min(average, reserve)
    remaining_amount = max(int(envelope.remaining_amount or 0), 1)
    remaining_count = max(int(envelope.remaining_count or 1), 1)
    average = remaining_amount / remaining_count
    reserve = max(remaining_amount - (remaining_count - 1), 1)
    upper = max(min(int(average * 2), reserve), 1)
    return random.randint(1, upper)


def claim_red_envelope_for_user(envelope_id: int, tg: int) -> dict[str, Any]:
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "领取红包")
        assert_currency_operation_allowed(tg, "领取红包", session=session, profile=profile)
        envelope = session.query(XiuxianRedEnvelope).filter(XiuxianRedEnvelope.id == envelope_id).with_for_update().first()
        if envelope is None or envelope.status != "active":
            raise ValueError("红包不存在或已领完")
        creator_tg = int(envelope.creator_tg or 0)
        if creator_tg == int(tg):
            raise ValueError("不能领取自己发放的红包。")
        if creator_tg > 0 and _is_active_spouse_pair(session, creator_tg, tg):
            raise ValueError("道侣之间灵石共享，不能领取对方发放的红包。")
        if envelope.target_tg and int(envelope.target_tg) != int(tg):
            raise ValueError("这是专属红包，你不能领取")
        existing = (
            session.query(XiuxianRedEnvelopeClaim)
            .filter(XiuxianRedEnvelopeClaim.envelope_id == envelope_id, XiuxianRedEnvelopeClaim.tg == tg)
            .first()
        )
        if existing is not None:
            raise ValueError("你已经领取过这个红包")
        if int(envelope.remaining_count or 0) <= 0 or int(envelope.remaining_amount or 0) <= 0:
            raise ValueError("红包已经被领完")
        amount = min(_draw_red_envelope_amount(envelope), int(envelope.remaining_amount or 0))
        envelope.remaining_amount = max(int(envelope.remaining_amount or 0) - amount, 0)
        envelope.remaining_count = max(int(envelope.remaining_count or 0) - 1, 0)
        if envelope.remaining_count <= 0 or envelope.remaining_amount <= 0:
            envelope.status = "finished"
        envelope.updated_at = utcnow()
        session.add(XiuxianRedEnvelopeClaim(envelope_id=envelope_id, tg=tg, amount=amount))
        session.commit()
    with Session() as session:
        updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if updated is None or not updated.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        apply_spiritual_stone_delta(
            session,
            tg,
            amount,
            action_text="领取红包",
            enforce_currency_lock=True,
            allow_dead=False,
            apply_tribute=True,
        )
        session.commit()
    create_journal(tg, "red_envelope", "喜抢红包", f"眼明手快，抢得 {amount} 灵石红包")
    return {
        "envelope": serialize_red_envelope(get_red_envelope(envelope_id)),
        "amount": amount,
        "profile": _full_profile_bundle(tg)["profile"],
        "claims": list_red_envelope_claims(envelope_id),
    }


def gift_spirit_stone(sender_tg: int, target_tg: int, amount: int) -> dict[str, Any]:
    if int(sender_tg) == int(target_tg):
        raise ValueError("不能给自己赠送灵石")
    amount = max(int(amount or 0), 0)
    if amount <= 0:
        raise ValueError("赠送灵石数量必须大于 0")

    _require_alive_profile_data(sender_tg, "赠送灵石")
    _require_alive_profile_data(target_tg, "接收灵石")
    from bot.plugins.xiuxian_game.service import assert_social_action_allowed

    with Session() as session:
        sender = session.query(XiuxianProfile).filter(XiuxianProfile.tg == sender_tg).with_for_update().first()
        receiver = session.query(XiuxianProfile).filter(XiuxianProfile.tg == target_tg).with_for_update().first()
        if sender is None or receiver is None or not sender.consented or not receiver.consented:
            raise ValueError("双方都需要已踏入仙途")
        assert_social_action_allowed(sender, receiver, "赠送灵石")
        assert_currency_operation_allowed(sender_tg, "赠送灵石", session=session, profile=sender)
        assert_currency_operation_allowed(target_tg, "接收灵石", session=session, profile=receiver)
        apply_spiritual_stone_delta(
            session,
            sender_tg,
            -amount,
            action_text="赠送灵石",
            allow_dead=False,
            apply_tribute=False,
        )
        apply_spiritual_stone_delta(
            session,
            target_tg,
            amount,
            action_text="接收灵石",
            allow_dead=False,
            apply_tribute=True,
        )
        session.commit()

    create_journal(sender_tg, "gift", "赠送灵石", f"袖中取出 {amount} 灵石，赠与 TG {target_tg}")
    create_journal(target_tg, "gift", "收到馈赠", f"收到 TG {sender_tg} 赠予的 {amount} 灵石")
    return {
        "amount": amount,
        "sender": serialize_profile(get_profile(sender_tg, create=False)),
        "receiver": serialize_profile(get_profile(target_tg, create=False)),
        "achievement_unlocks": record_gift_metrics(sender_tg, amount),
    }


def reset_robbery_counter_if_needed(profile_obj: XiuxianProfile) -> XiuxianProfile:
    today = china_day_key()
    if profile_obj.robbery_day_key != today:
        return upsert_profile(profile_obj.tg, robbery_day_key=today, robbery_daily_count=0)
    return profile_obj


def _ensure_daily_limit(
    profile: XiuxianProfile,
    count_attr: str,
    key_attr: str,
    limit_setting_key: str,
    activity_label: str,
    *,
    session: Any = None,
) -> XiuxianProfile:
    """通用日限检查：若跨天则重置计数器，超出限制则抛异常。返回更新后的 profile。"""
    from bot.sql_helper.sql_xiuxian import DEFAULT_SETTINGS, get_xiuxian_settings, upsert_profile

    today = china_day_key()
    current_key = getattr(profile, key_attr, None)
    if current_key != today:
        profile = upsert_profile(int(profile.tg), **{key_attr: today, count_attr: 0})
        if session is not None:
            session.expire(profile)
            profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(profile.tg)).with_for_update().first()
    settings = get_xiuxian_settings()
    limit = max(int(settings.get(limit_setting_key, DEFAULT_SETTINGS.get(limit_setting_key, 999)) or 999), 0)
    current_count = max(int(getattr(profile, count_attr, 0) or 0), 0)
    if limit > 0 and current_count >= limit:
        raise ValueError(f"今日{activity_label}次数已用完（每日 {limit} 次），请明日再来。")
    return profile


def _bump_daily_counter(tg: int, count_attr: str) -> None:
    """递增日限计数器。"""
    from bot.sql_helper.sql_xiuxian import upsert_profile

    profile = get_profile(tg, create=False)
    if profile is not None:
        current = max(int(getattr(profile, count_attr, 0) or 0), 0)
        upsert_profile(tg, **{count_attr: current + 1})


def rob_player(attacker_tg: int, defender_tg: int, success_hint: float = 0.5) -> dict[str, Any]:
    if attacker_tg == defender_tg:
        raise ValueError("不能抢劫自己")
    attacker_obj = reset_robbery_counter_if_needed(_require_alive_profile_data(attacker_tg, "发起抢劫")[0])
    defender_obj = _require_alive_profile_data(defender_tg, "被抢劫")[0]
    if attacker_obj is None or defender_obj is None or not attacker_obj.consented or not defender_obj.consented:
        raise ValueError("双方都需要已踏入仙途")
    if get_active_duel_lock(attacker_tg) or get_active_duel_lock(defender_tg):
        raise ValueError("斗法结算期间无法发起或响应抢劫。")
    settings = get_xiuxian_settings()
    if int(attacker_obj.robbery_daily_count or 0) >= int(settings.get("robbery_daily_limit", DEFAULT_SETTINGS["robbery_daily_limit"]) or 0):
        raise ValueError("今日抢劫次数已用完")
    if int(attacker_obj.spiritual_stone or 0) < 5:
        raise ValueError("至少携带 5 灵石作为押底，才能发起抢劫。")
    from bot.plugins.xiuxian_game.service import assert_social_action_allowed, compute_duel_odds

    assert_social_action_allowed(attacker_obj, defender_obj, "抢劫")

    duel = compute_duel_odds(attacker_tg, defender_tg)
    attacker = duel["challenger"]["profile"]
    defender = duel["defender"]["profile"]
    attacker_stats = duel["challenger_snapshot"]["stats"]
    defender_stats = duel["defender_snapshot"]["stats"]
    attacker_power = float(duel.get("challenger_power") or 0.0)
    defender_power = float(duel.get("defender_power") or 0.0)
    stage_diff = int(duel.get("weights", {}).get("stage_diff", 0) or 0)
    rate = float(duel.get("challenger_rate", success_hint) or success_hint)
    rate = rate * 0.85 + float(success_hint) * 0.15
    rate = max(min(rate, 0.985), 0.015 if abs(stage_diff) >= 2 else 0.05)
    roll = random.random()
    success = roll <= rate
    steal_cap = int(settings.get("robbery_max_steal", DEFAULT_SETTINGS["robbery_max_steal"]) or 180)
    attacker_stone = max(int(attacker_obj.spiritual_stone or 0), 0)
    defender_stone = max(int(defender_obj.spiritual_stone or 0), 0)
    offense_pressure = (
        float(attacker_stats.get("attack_power") or 0) * 0.58
        + float(attacker_stats.get("body_movement") or 0) * 0.34
        + float(attacker_stats.get("fortune") or 0) * 0.28
        + float(attacker_stats.get("divine_sense") or 0) * 0.22
    )
    defense_pressure = max(
        float(defender_stats.get("defense_power") or 0) * 0.52
        + float(defender_stats.get("body_movement") or 0) * 0.28
        + float(defender_stats.get("fortune") or 0) * 0.24
        + float(defender_stats.get("divine_sense") or 0) * 0.26,
        24.0,
    )
    stat_edge = max(min(offense_pressure / defense_pressure, 2.2), 0.55)
    power_edge = max(min((attacker_power + 180.0) / (defender_power + 180.0), 1.95), 0.65)
    artifact_plunder = None
    if success:
        wealth_take_rate = (0.08 + rate * 0.12) * (stat_edge * 0.52 + power_edge * 0.48)
        wealth_take_rate = max(min(wealth_take_rate, 0.34), 0.05)
        agility_bonus = int(
            (
                float(attacker_stats.get("body_movement") or 0)
                + float(attacker_stats.get("fortune") or 0)
                + float(attacker_stats.get("attack_power") or 0) * 0.5
            ) // 7
        )
        amount = int(defender_stone * wealth_take_rate) + agility_bonus
        if defender_stone > 0:
            amount = max(amount, min(max(8, int(offense_pressure // 8)), defender_stone))
        amount = max(min(amount, steal_cap, defender_stone, int(defender_stone * 0.38) + 16), 0)
        with Session() as session:
            attacker_updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == attacker_tg).with_for_update().first()
            defender_updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == defender_tg).with_for_update().first()
            if attacker_updated is None or defender_updated is None:
                raise ValueError("双方都需要已踏入仙途")
            apply_spiritual_stone_delta(session, defender_tg, -amount, action_text="被抢劫", allow_dead=False, apply_tribute=False)
            apply_spiritual_stone_delta(session, attacker_tg, amount, action_text="抢劫得手", allow_dead=False, apply_tribute=True)
            attacker_updated.robbery_daily_count = int(attacker_updated.robbery_daily_count or 0) + 1
            attacker_updated.robbery_day_key = china_day_key()
            attacker_updated.updated_at = utcnow()
            session.commit()
        artifact_roll = roll_probability_percent(
            int(settings.get("artifact_plunder_chance", DEFAULT_SETTINGS["artifact_plunder_chance"]) or 0),
            actor_fortune=float(duel["challenger_snapshot"]["stats"]["fortune"]),
            opponent_fortune=float(duel["defender_snapshot"]["stats"]["fortune"]),
            actor_weight=0.45,
            opponent_weight=0.35,
            minimum=0,
            maximum=95,
        )
        artifact_plunder = {
            **artifact_roll,
            "artifact": None,
            "was_equipped": False,
        }
        if artifact_roll["success"]:
            payload = plunder_random_artifact_to_user(attacker_tg, defender_tg)
            if payload and payload.get("artifact"):
                artifact_plunder["artifact"] = payload.get("artifact")
                artifact_plunder["was_equipped"] = bool(payload.get("was_equipped"))
                artifact_name = artifact_plunder["artifact"].get("name", "未知法宝")
                create_journal(attacker_tg, "rob", "顺手夺宝", f"下手得逞后又顺走法宝【{artifact_name}】")
                create_journal(defender_tg, "rob", "法宝被夺", f"仓皇之际，法宝【{artifact_name}】已落入他人之手")
        defender_label = defender.get("display_label") or defender.get("display_name") or f"TG {defender_tg}"
        attacker_label = attacker.get("display_label") or attacker.get("display_name") or f"TG {attacker_tg}"
        create_journal(attacker_tg, "rob", "打劫得手", f"从 {defender_label} 手中夺走 {amount} 灵石，扬长而去。")
        create_journal(defender_tg, "rob", "遭遇劫掠", f"被 {attacker_label} 劫走 {amount} 灵石，只恨修为不济。")
    else:
        counter_edge = max(min(defense_pressure / max(offense_pressure, 18.0), 1.8), 0.85)
        penalty_ratio = 0.035 + max(0.68 - rate, 0.0) * 0.09
        penalty_ratio *= max(min(counter_edge * 0.55 + ((defender_power + 200.0) / (attacker_power + 200.0)) * 0.45, 1.85), 0.8)
        penalty_bonus = max(int((float(defender_stats.get("body_movement") or 0) + float(defender_stats.get("divine_sense") or 0)) // 10), 3)
        penalty = int(attacker_stone * penalty_ratio) + penalty_bonus
        penalty = min(max(penalty, 5), max(steal_cap // 2, 24), attacker_stone)
        amount = -penalty
        with Session() as session:
            attacker_updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == attacker_tg).with_for_update().first()
            defender_updated = session.query(XiuxianProfile).filter(XiuxianProfile.tg == defender_tg).with_for_update().first()
            if attacker_updated is None or defender_updated is None:
                raise ValueError("双方都需要已踏入仙途")
            apply_spiritual_stone_delta(session, attacker_tg, -penalty, action_text="抢劫失败赔付", allow_dead=False, apply_tribute=False)
            apply_spiritual_stone_delta(session, defender_tg, penalty, action_text="获得抢劫赔付", allow_dead=False, apply_tribute=True)
            attacker_updated.robbery_daily_count = int(attacker_updated.robbery_daily_count or 0) + 1
            attacker_updated.robbery_day_key = china_day_key()
            attacker_updated.updated_at = utcnow()
            session.commit()
        defender_label = defender.get("display_label") or defender.get("display_name") or f"TG {defender_tg}"
        attacker_label = attacker.get("display_label") or attacker.get("display_name") or f"TG {attacker_tg}"
        create_journal(attacker_tg, "rob", "打劫失手", f"出手劫掠 {defender_label} 不成，反赔 {penalty} 灵石，灰溜溜离去。")
        create_journal(defender_tg, "rob", "击退来犯", f"将来犯者 {attacker_label} 击退，得对方赔付 {penalty} 灵石。")
    return {
        "success": success,
        "roll": round(roll, 4),
        "success_rate": round(rate, 4),
        "amount": amount,
        "attacker": serialize_profile(get_profile(attacker_tg, create=False)),
        "defender": serialize_profile(get_profile(defender_tg, create=False)),
        "artifact_plunder": artifact_plunder,
        "achievement_unlocks": record_robbery_metrics(attacker_tg, success=success, amount=max(amount, 0)),
    }


def update_duel_bet_pool_message(pool_id: int, bet_message_id: int) -> None:
    with Session() as session:
        pool = session.query(XiuxianDuelBetPool).filter(XiuxianDuelBetPool.id == pool_id).first()
        if pool is not None:
            pool.bet_message_id = bet_message_id
            pool.updated_at = utcnow()
            session.commit()


def _duel_bet_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    source = settings if isinstance(settings, dict) else get_xiuxian_settings()
    options: list[int] = []
    for value in list(source.get("duel_bet_amount_options") or []):
        try:
            amount = int(value or 0)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            options.append(amount)
    minimum = max(int(source.get("duel_bet_min_amount", DEFAULT_SETTINGS.get("duel_bet_min_amount", 10)) or 0), 1)
    maximum = max(int(source.get("duel_bet_max_amount", DEFAULT_SETTINGS.get("duel_bet_max_amount", 100)) or 0), minimum)
    if not options:
        midpoint = (minimum + maximum) // 2
        options = [minimum]
        if midpoint not in {minimum, maximum}:
            options.append(midpoint)
        if maximum != minimum:
            options.append(maximum)
    return {
        "enabled": bool(source.get("duel_bet_enabled", DEFAULT_SETTINGS.get("duel_bet_enabled", True))),
        "seconds": min(max(int(source.get("duel_bet_seconds", DEFAULT_SETTINGS.get("duel_bet_seconds", 120)) or 0), 10), 3600),
        "min_amount": minimum,
        "max_amount": maximum,
        "amount_options": sorted(set(options)),
    }


def place_duel_bet(pool_id: int, tg: int, side: str, amount: int) -> dict[str, Any]:
    with Session() as session:
        pool = session.query(XiuxianDuelBetPool).filter(XiuxianDuelBetPool.id == pool_id).with_for_update().first()
        if pool is None or pool.resolved:
            raise ValueError("当前斗法下注已结束")
        if utcnow() >= pool.bets_close_at:
            raise ValueError("下注时间已截止")
        bet_settings = _duel_bet_settings()
        if not bet_settings["enabled"]:
            raise ValueError("赌斗下注功能已关闭")
        if tg in {pool.challenger_tg, pool.defender_tg}:
            raise ValueError("斗法双方不能下注")
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "下注")
        assert_currency_operation_allowed(tg, "下注", session=session, profile=profile)
        amount = max(int(amount or 0), 1)
        if amount < bet_settings["min_amount"] or amount > bet_settings["max_amount"]:
            raise ValueError(
                f"当前下注范围为 {bet_settings['min_amount']} - {bet_settings['max_amount']} 灵石"
            )
        if bet_settings["amount_options"] and amount not in bet_settings["amount_options"]:
            allowed = " / ".join(str(value) for value in bet_settings["amount_options"])
            raise ValueError(f"当前仅支持以下下注挡位：{allowed}")
        bet = session.query(XiuxianDuelBet).filter(XiuxianDuelBet.pool_id == pool_id, XiuxianDuelBet.tg == tg).first()
        if bet is None:
            bet = XiuxianDuelBet(pool_id=pool_id, tg=tg, side=side, amount=0)
            session.add(bet)
        elif bet.side != side:
            raise ValueError("同一场斗法只能押注一方")
        bet.amount += amount
        apply_spiritual_stone_delta(session, tg, -amount, action_text="下注", allow_dead=False, apply_tribute=False)
        pool.updated_at = utcnow()
        session.commit()
        challenger_total, defender_total = _duel_bet_totals(session, pool_id)
    return {"totals": {"challenger": challenger_total, "defender": defender_total}}


def settle_duel_bet_pool(pool_id: int, winner_tg: int) -> dict[str, Any]:
    with Session() as session:
        pool = session.query(XiuxianDuelBetPool).filter(XiuxianDuelBetPool.id == pool_id).with_for_update().first()
        if pool is None:
            raise ValueError("下注池不存在")
        if pool.resolved:
            return {"pool_id": pool_id, "resolved": True, "entries": [], "payouts": []}
        pool.resolved = True
        pool.winner_tg = winner_tg
        winner_side = "challenger" if int(winner_tg) == int(pool.challenger_tg) else "defender"
        loser_side = "defender" if winner_side == "challenger" else "challenger"
        winner_bets = session.query(XiuxianDuelBet).filter(XiuxianDuelBet.pool_id == pool_id, XiuxianDuelBet.side == winner_side).all()
        loser_bets = session.query(XiuxianDuelBet).filter(XiuxianDuelBet.pool_id == pool_id, XiuxianDuelBet.side == loser_side).all()
        bettor_tgs = [int(row.tg) for row in winner_bets + loser_bets]
        name_map = get_emby_name_map(bettor_tgs)
        loser_total = sum(int(row.amount or 0) for row in loser_bets)
        winner_total = sum(int(row.amount or 0) for row in winner_bets)
        entries = []
        for bet in winner_bets:
            bonus = floor_div(loser_total * int(bet.amount or 0), winner_total)
            total_back = int(bet.amount or 0) + bonus
            profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == bet.tg).with_for_update().first()
            if profile is not None:
                apply_spiritual_stone_delta(session, int(bet.tg), total_back, action_text="领取斗法押注返还", allow_dead=False, apply_tribute=True)
            entries.append(
                {
                    "tg": int(bet.tg),
                    "name": name_map.get(int(bet.tg), f"TG {bet.tg}"),
                    "side": bet.side,
                    "result": "win",
                    "bet_amount": int(bet.amount or 0),
                    "amount": total_back,
                    "bonus": bonus,
                    "net_profit": bonus,
                }
            )
        for bet in loser_bets:
            entries.append(
                {
                    "tg": int(bet.tg),
                    "name": name_map.get(int(bet.tg), f"TG {bet.tg}"),
                    "side": bet.side,
                    "result": "lose",
                    "bet_amount": int(bet.amount or 0),
                    "amount": -int(bet.amount or 0),
                    "bonus": -int(bet.amount or 0),
                    "net_profit": -int(bet.amount or 0),
                }
            )
        entries.sort(
            key=lambda row: (
                int(row.get("net_profit") or 0),
                int(row.get("bet_amount") or 0),
                -int(row.get("tg") or 0),
            ),
            reverse=True,
        )
        payouts = [row for row in entries if row.get("result") == "win"]
        losses = [row for row in entries if row.get("result") == "lose"]
        pool.updated_at = utcnow()
        session.commit()
    _invalidate_duel_bet_preview(pool_id)
    return {
        "pool_id": pool_id,
        "resolved": True,
        "entries": entries,
        "payouts": payouts,
        "losses": losses,
        "winner_tg": winner_tg,
        "winner_side": winner_side,
        "loser_side": loser_side,
        "winner_total": winner_total,
        "loser_total": loser_total,
    }


def cancel_duel_bet_pool(pool_id: int, reason: str = "") -> dict[str, Any]:
    with Session() as session:
        pool = session.query(XiuxianDuelBetPool).filter(XiuxianDuelBetPool.id == pool_id).with_for_update().first()
        if pool is None:
            raise ValueError("下注池不存在")
        if pool.resolved:
            return {"pool_id": pool_id, "resolved": True, "cancelled": True, "entries": [], "reason": reason}
        bets = session.query(XiuxianDuelBet).filter(XiuxianDuelBet.pool_id == pool_id).all()
        name_map = get_emby_name_map([int(row.tg) for row in bets])
        entries = []
        for bet in bets:
            refund_amount = max(int(bet.amount or 0), 0)
            profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == bet.tg).with_for_update().first()
            if profile is not None and refund_amount > 0:
                apply_spiritual_stone_delta(session, int(bet.tg), refund_amount, action_text="退还斗法押注", allow_dead=False, apply_tribute=True)
            entries.append(
                {
                    "tg": int(bet.tg),
                    "name": name_map.get(int(bet.tg), f"TG {bet.tg}"),
                    "side": bet.side,
                    "bet_amount": refund_amount,
                    "amount": refund_amount,
                    "result": "refund",
                }
            )
        pool.resolved = True
        pool.winner_tg = None
        pool.updated_at = utcnow()
        session.commit()
    _invalidate_duel_bet_preview(pool_id)
    return {
        "pool_id": pool_id,
        "resolved": True,
        "cancelled": True,
        "entries": entries,
        "reason": reason,
    }


def _invalidate_duel_bet_preview(pool_id: int) -> None:
    DUEL_BET_PREVIEW_CACHE.pop(int(pool_id or 0), None)


def _duel_bet_totals(session: Session, pool_id: int) -> tuple[int, int]:
    totals = {"challenger": 0, "defender": 0}
    rows = (
        session.query(
            XiuxianDuelBet.side,
            func.coalesce(func.sum(XiuxianDuelBet.amount), 0),
        )
        .filter(XiuxianDuelBet.pool_id == int(pool_id))
        .group_by(XiuxianDuelBet.side)
        .all()
    )
    for side, total in rows:
        if str(side) in totals:
            totals[str(side)] = int(total or 0)
    return totals["challenger"], totals["defender"]


def _duel_bet_preview(pool: XiuxianDuelBetPool) -> tuple[str, dict[str, Any]]:
    pool_id = int(pool.id or 0)
    duel_mode = str(pool.duel_mode or "standard")
    preview_key = (
        int(pool.challenger_tg or 0),
        int(pool.defender_tg or 0),
        duel_mode,
        int(pool.stake or 0),
        bool(pool.resolved),
    )
    now_monotonic = time.monotonic()
    cached = DUEL_BET_PREVIEW_CACHE.get(pool_id)
    if (
        cached is not None
        and cached.get("key") == preview_key
        and now_monotonic - float(cached.get("at") or 0.0) < DUEL_BET_PREVIEW_CACHE_TTL_SECONDS
    ):
        return str(cached.get("matchup_text") or ""), dict(cached.get("bet_settings") or {})

    from bot.plugins.xiuxian_game.service import compute_duel_odds, format_duel_matchup_text

    duel = compute_duel_odds(int(pool.challenger_tg), int(pool.defender_tg), duel_mode=duel_mode)
    bet_settings = _duel_bet_settings()
    duel_label = DUEL_MODE_LABELS.get(duel_mode, "斗法")
    matchup_text = format_duel_matchup_text(
        duel,
        stake=int(pool.stake or 0),
        title=f"🎯 **{duel_label}押注中**" if not pool.resolved else f"🎯 **{duel_label}押注已结束**",
        duel_mode=duel_mode,
    )
    DUEL_BET_PREVIEW_CACHE[pool_id] = {
        "key": preview_key,
        "at": now_monotonic,
        "matchup_text": matchup_text,
        "bet_settings": bet_settings,
    }
    return matchup_text, dict(bet_settings)


def format_duel_bet_board(pool_id: int) -> str:
    with Session() as session:
        pool = session.query(XiuxianDuelBetPool).filter(XiuxianDuelBetPool.id == pool_id).first()
        if pool is None:
            return "下注池不存在"
        challenger_total, defender_total = _duel_bet_totals(session, pool_id)
        remaining = max(int((pool.bets_close_at - utcnow()).total_seconds()), 0)
        matchup_text, bet_settings = _duel_bet_preview(pool)
        lines = [
            matchup_text,
            "",
            "押注情况：",
            f"挑战者池：{challenger_total} 灵石",
            f"应战者池：{defender_total} 灵石",
            f"总赌池：{challenger_total + defender_total} 灵石",
            f"下注范围：{bet_settings['min_amount']} - {bet_settings['max_amount']} 灵石",
            f"下注挡位：{' / '.join(str(value) for value in bet_settings['amount_options'])}",
        ]
        if pool.resolved:
            winner_side = "挑战者" if int(pool.winner_tg or 0) == int(pool.challenger_tg) else "应战者"
            lines.append(f"押注状态：已结算（胜方：{winner_side}）")
        else:
            if not bet_settings["enabled"]:
                lines.append("下注状态：后台已关闭新下注，仅保留已下注单等待结算")
            lines.append(f"剩余时间：{remaining} 秒")
        return "\n".join(lines)


def claim_task_for_user(tg: int, task_id: int) -> dict[str, Any]:
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立")
    metric_progress_payload = None
    with Session() as session:
        completed_now = False
        submitted_item = None
        task = session.query(XiuxianTask).filter(XiuxianTask.id == task_id).with_for_update().first()
        if task is None or not task.enabled:
            raise ValueError("任务不存在")
        if int(task.owner_tg or 0) == int(tg):
            raise ValueError("不能领取自己发布的任务")
        if _is_unescrowed_player_stone_task(task):
            raise ValueError(_unescrowed_player_stone_task_reason())
        if task.task_scope == "sect" and int(task.sect_id or 0) != int(profile.get("sect_id") or 0):
            raise ValueError("只有同宗门成员才能领取该任务")
        if task.task_type == "quiz":
            raise ValueError("答题任务需要在群内作答")
        existing = (
            session.query(XiuxianTaskClaim)
            .filter(XiuxianTaskClaim.task_id == task_id, XiuxianTaskClaim.tg == tg)
            .first()
        )
        if existing is not None and str(task.task_type or "") != "metric":
            raise ValueError("你已经领取过该任务")
        if existing is None and int(task.claimants_count or 0) >= int(task.max_claimants or 1):
            raise ValueError("该任务已被领取完")

        claim_status = "accepted"
        if str(task.task_type or "") == "metric":
            progress_map = get_user_achievement_progress_map(tg)
            claim_payload = (
                {
                    "metric_start_value": max(int(existing.metric_start_value or 0), 0),
                }
                if existing is not None
                else None
            )
            metric_progress_payload = _metric_task_progress_payload(task, claim_payload, progress_map)
            if existing is None:
                session.add(
                    XiuxianTaskClaim(
                        task_id=task_id,
                        tg=tg,
                        status="accepted",
                        metric_start_value=max(int(metric_progress_payload.get("metric_current_value") or 0), 0),
                    )
                )
                task.updated_at = utcnow()
                session.commit()
                session.refresh(task)
                serialized = _decorate_task_payload(serialize_task(task))
                serialized.update(_scaled_task_reward_values(task, profile))
                serialized.update(
                    _metric_task_progress_payload(
                        task,
                        {"metric_start_value": max(int(metric_progress_payload.get("metric_current_value") or 0), 0)},
                        progress_map,
                    )
                )
                create_journal(tg, "task", "接取任务", f"接取了计数委托【{serialized['title']}】")
                return {"task": serialized, "reward": None, "submitted_item": None}

            if existing.status == "completed":
                raise ValueError("你已经完成过该任务")
            if existing.status == "cancelled":
                raise ValueError("该任务已被撤销，无法继续结算")
            if not metric_progress_payload.get("metric_claimable"):
                metric_label = metric_progress_payload.get("metric_label") or "进度"
                raise ValueError(
                    f"当前计数尚未达标：{metric_label} {metric_progress_payload.get('metric_progress_value', 0)}/{metric_progress_payload.get('metric_target', 0)}。"
                )
            if int(task.claimants_count or 0) >= int(task.max_claimants or 1):
                raise ValueError("该任务奖励已被领取完")
            existing.status = "completed"
            task.claimants_count = int(task.claimants_count or 0) + 1
            completed_now = True
            if task.claimants_count >= int(task.max_claimants or 1):
                task.status = "completed"
            else:
                task.status = "active"
        elif task.required_item_kind and task.required_item_ref_id and int(task.required_item_quantity or 0) > 0:
            submitted_item = _consume_required_item(
                session,
                tg,
                str(task.required_item_kind),
                int(task.required_item_ref_id),
                int(task.required_item_quantity),
            )
            completed_now = True
            claim_status = "completed"
            session.add(XiuxianTaskClaim(task_id=task_id, tg=tg, status=claim_status))
            task.claimants_count = int(task.claimants_count or 0) + 1
            if completed_now and task.claimants_count >= int(task.max_claimants or 1):
                task.status = "completed"
            elif not completed_now and task.claimants_count >= int(task.max_claimants or 1):
                task.status = "active"
        else:
            session.add(XiuxianTaskClaim(task_id=task_id, tg=tg, status=claim_status))
            task.claimants_count = int(task.claimants_count or 0) + 1
            if task.claimants_count >= int(task.max_claimants or 1):
                task.status = "active"
        task.updated_at = utcnow()
        session.commit()
        session.refresh(task)
        serialized = _decorate_task_payload(serialize_task(task))
        serialized.update(_scaled_task_reward_values(task, profile))
        if str(task.task_type or "") == "metric":
            progress_map = get_user_achievement_progress_map(tg)
            claim_for_payload = (
                session.query(XiuxianTaskClaim)
                .filter(XiuxianTaskClaim.task_id == task_id, XiuxianTaskClaim.tg == tg)
                .first()
            )
            serialized.update(
                _metric_task_progress_payload(
                    task,
                    {"metric_start_value": max(int(getattr(claim_for_payload, "metric_start_value", 0) or 0), 0)} if claim_for_payload else None,
                    progress_map,
                )
            )

    if not completed_now:
        create_journal(tg, "task", "接取任务", f"接取了委托【{serialized['title']}】")
        return {"task": serialized, "reward": None, "submitted_item": None}

    with Session() as session:
        refreshed_task = session.query(XiuxianTask).filter(XiuxianTask.id == task_id).first()
        reward = _award_task_rewards(tg, refreshed_task)
        if refreshed_task and refreshed_task.task_scope == "sect":
            profile_obj = get_profile(tg, create=False)
            if profile_obj is not None:
                upsert_profile(tg, sect_contribution=int(profile_obj.sect_contribution or 0) + 1)
        if refreshed_task is not None:
            if str(refreshed_task.task_type or "") == "metric":
                metric_label = ACHIEVEMENT_METRIC_LABELS.get(
                    str(refreshed_task.requirement_metric_key or ""),
                    refreshed_task.requirement_metric_key or "计数指标",
                )
                create_journal(
                    tg,
                    "task",
                    "完成计数委托",
                    f"{metric_label} 已累计至 {int(refreshed_task.requirement_metric_target or 0)}，委托【{refreshed_task.title}】达成。",
                )
            else:
                item_name = _required_item_name(
                    str(refreshed_task.required_item_kind or ""),
                    int(refreshed_task.required_item_ref_id or 0),
                )
                create_journal(
                    tg,
                    "task",
                    "交付物品完成委托",
                    f"奉上 {item_name} × {int(refreshed_task.required_item_quantity or 0)}，委托【{refreshed_task.title}】达成。",
                )
        return {
            "task": _decorate_task_payload(serialize_task(refreshed_task)),
            "reward": reward,
            "submitted_item": {
                "item": submitted_item,
                "quantity": serialized.get("required_item_quantity") or 0,
            },
        }


def resolve_quiz_answer(chat_id: int, tg: int, answer_text: str) -> dict[str, Any] | None:
    normalized = _normalize_quiz_answer_text(answer_text)
    if not normalized:
        return None
    profile = serialize_profile(get_profile(tg, create=False))
    if not profile or not profile.get("consented"):
        return None
    with Session() as session:
        rows = (
            session.query(XiuxianTask)
            .filter(
                XiuxianTask.group_chat_id == chat_id,
                XiuxianTask.active_in_group.is_(True),
                XiuxianTask.task_type == "quiz",
                XiuxianTask.status.in_(["open", "active"]),
                XiuxianTask.enabled.is_(True),
            )
            .with_for_update()
            .all()
        )
        for task in rows:
            if int(task.owner_tg or 0) == int(tg):
                continue
            if _is_unescrowed_player_stone_task(task):
                continue
            if normalized != _normalize_quiz_answer_text(task.answer_text):
                continue
            if task.task_scope == "sect":
                if int(profile.get("sect_id") or 0) != int(task.sect_id or 0):
                    continue
            if task.winner_tg:
                continue
            task.winner_tg = tg
            task.claimants_count = int(task.claimants_count or 0) + 1
            task.status = "completed"
            task.active_in_group = False
            task.updated_at = utcnow()
            claim = (
                session.query(XiuxianTaskClaim)
                .filter(XiuxianTaskClaim.task_id == task.id, XiuxianTaskClaim.tg == tg)
                .first()
            )
            if claim is None:
                session.add(XiuxianTaskClaim(task_id=task.id, tg=tg, status="completed", submitted_answer=normalized))
            else:
                claim.status = "completed"
                claim.submitted_answer = normalized
            session.commit()
            session.refresh(task)
            reward = _award_task_rewards(tg, task)
            if task.task_scope == "sect":
                profile_obj = get_profile(tg, create=False)
                if profile_obj is not None:
                    upsert_profile(tg, sect_contribution=int(profile_obj.sect_contribution or 0) + 1)
            create_journal(tg, "task", "完成答题委托", f"福至心灵，第一个答出【{task.title}】")
            return {"task": _decorate_task_payload(serialize_task(task)), "reward": reward}
    return None


def create_duel_bet_pool_for_duel(
    *,
    challenger_tg: int,
    defender_tg: int,
    stake: int,
    duel_mode: str = "standard",
    bet_seconds: int | None = None,
    bet_minutes: int | None = None,
    group_chat_id: int,
    duel_message_id: int | None = None,
) -> dict[str, Any]:
    mode_aliases = {
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
    duel_mode_value = mode_aliases.get(str(duel_mode or "standard").strip().lower(), "standard")
    for tg in (challenger_tg, defender_tg):
        active_lock = get_active_duel_lock(tg)
        if active_lock is not None:
            raise ValueError(f"{active_lock['duel_mode_label']}尚未结算，暂时不能再次开启新的斗法。")
    settings = get_xiuxian_settings()
    bet_settings = _duel_bet_settings(settings)
    if not bet_settings["enabled"]:
        raise ValueError("赌斗下注功能已关闭")
    configured_seconds = int(bet_settings["seconds"] or DEFAULT_SETTINGS.get("duel_bet_seconds", 120))
    seconds = int(bet_seconds or 0)
    if seconds <= 0 and bet_minutes is not None:
        seconds = max(int(bet_minutes or 0), 1) * 60
    seconds = min(max(seconds or configured_seconds, 10), 3600)
    stake_amount = max(int(stake or 0), 0)
    if stake_amount > 0:
        from bot.plugins.xiuxian_game.service import assert_duel_stake_affordable

        challenger_profile_obj = get_profile(challenger_tg, create=False)
        defender_profile_obj = get_profile(defender_tg, create=False)
        if challenger_profile_obj is None or defender_profile_obj is None:
            raise ValueError("斗法双方的修仙资料缺失。")
        assert_duel_stake_affordable(
            serialize_profile(challenger_profile_obj),
            serialize_profile(defender_profile_obj),
            stake_amount,
        )
    with Session() as session:
        pool = XiuxianDuelBetPool(
            challenger_tg=challenger_tg,
            defender_tg=defender_tg,
            stake=stake_amount,
            group_chat_id=group_chat_id,
            duel_message_id=duel_message_id,
            duel_mode=duel_mode_value,
            bets_close_at=utcnow() + timedelta(seconds=seconds),
            resolved=False,
        )
        session.add(pool)
        session.commit()
        session.refresh(pool)
        return {
            "id": pool.id,
            "challenger_tg": pool.challenger_tg,
            "defender_tg": pool.defender_tg,
            "stake": pool.stake,
            "group_chat_id": pool.group_chat_id,
            "bet_seconds": seconds,
            "duel_mode": duel_mode_value,
            "duel_mode_label": DUEL_MODE_LABELS.get(duel_mode_value, duel_mode_value),
            "bets_close_at": serialize_datetime(pool.bets_close_at),
        }


def build_world_bundle(tg: int) -> dict[str, Any]:
    settings = get_xiuxian_settings()
    scenes = list_scenes(enabled_only=True)
    exploration_counts = _scene_exploration_counts(tg)
    for scene in scenes:
        scene["drops"] = list_scene_drops(scene["id"])
        for drop in scene["drops"]:
            item = _get_item_payload(str(drop.get("reward_kind") or ""), int(drop.get("reward_ref_id") or 0))
            drop["reward_name"] = (item or {}).get("name") or f"{drop.get('reward_kind_label') or drop.get('reward_kind')}"
        for event in scene.get("event_pool") or []:
            if int((event or {}).get("bonus_reward_ref_id") or 0) > 0:
                item = _get_item_payload(str(event.get("bonus_reward_kind") or ""), int(event.get("bonus_reward_ref_id") or 0))
                event["bonus_reward_name"] = (item or {}).get("name")
        scene["user_exploration_count"] = exploration_counts.get(int(scene["id"]), 0)
    recipes = build_recipe_catalog(tg)
    return {
        "sects": list_sects_for_user(tg),
        "current_sect": get_current_sect_bundle(tg),
        "tasks": list_tasks_for_user(tg),
        "achievement_metric_presets": [
            {"key": key, "label": label}
            for key, label in sorted(ACHIEVEMENT_METRIC_LABELS.items(), key=lambda item: item[1])
        ],
        "materials": list_user_materials(tg),
        "recipes": recipes,
        "recipe_discovered_count": len(recipes),
        "recipe_total_count": len(list_recipes(enabled_only=True)),
        "recipe_fragment_syntheses": build_recipe_fragment_synthesis_catalog(tg),
        "technique_total_count": len(list_techniques(enabled_only=True)),
        "scenes": scenes,
        "active_exploration": _get_active_exploration(tg),
        "journal": list_recent_journals(tg),
        "settings": {
            "robbery_daily_limit": int(settings.get("robbery_daily_limit", DEFAULT_SETTINGS["robbery_daily_limit"]) or 3),
            "robbery_max_steal": int(settings.get("robbery_max_steal", DEFAULT_SETTINGS["robbery_max_steal"]) or 180),
            "artifact_plunder_chance": int(settings.get("artifact_plunder_chance", DEFAULT_SETTINGS["artifact_plunder_chance"]) or 0),
            "allow_user_task_publish": bool(settings.get("allow_user_task_publish", DEFAULT_SETTINGS["allow_user_task_publish"])),
            "task_publish_cost": max(int(settings.get("task_publish_cost", DEFAULT_SETTINGS["task_publish_cost"]) or 0), 0),
            "user_task_daily_limit": _user_task_daily_limit(),
            "user_task_published_today": _user_task_publish_count_today(tg),
        },
    }


from bot.plugins.xiuxian_game.features.economy import gift_spirit_stone as gift_spirit_stone  # noqa: E402
from bot.plugins.xiuxian_game.features.exploration import (  # noqa: E402
    _get_active_exploration as _get_active_exploration,
    claim_exploration_for_user as claim_exploration_for_user,
    create_scene_with_drops as create_scene_with_drops,
    patch_scene_with_drops as patch_scene_with_drops,
    start_exploration_for_user as start_exploration_for_user,
    sync_scene_with_drops_by_name as sync_scene_with_drops_by_name,
)
