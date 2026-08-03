from __future__ import annotations

from typing import Any

from bot.sql_helper.sql_xiuxian import (
    consume_user_pill,
    get_pill,
    get_profile,
    normalize_realm_stage,
    serialize_pill,
    serialize_profile,
    upsert_profile,
)
from bot.plugins.xiuxian_game.features.retreat import is_retreating


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def _pill_poison_lock_reason(profile: dict[str, Any], pill_type: str) -> str:
    current_poison = max(int(profile.get("dan_poison") or 0), 0)
    from bot.plugins.xiuxian_game.world_service import get_sect_effects
    sect_effects = get_sect_effects(profile)
    poison_cap = 100 + int(sect_effects.get("pill_poison_cap_bonus", 0))
    if pill_type != "clear_poison" and current_poison >= poison_cap:
        return f"丹毒已满（{poison_cap}/100上限），普通丹药药力会反噬，请先服用解毒丹。"
    return ""


def resolve_pill_effects(
    profile: dict[str, Any],
    pill: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, float]:
    legacy_service = _legacy_service()
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
    multiplier = legacy_service._item_quality_multiplier(pill, "pill")
    base_effect_value = max(float(pill.get("effect_value", 0) or 0) * multiplier, 0.0)
    poison_delta = 0.0 if pill_type == "clear_poison" else float(pill.get("poison_delta", 0) or 0)
    payload = {
        "effect_value": base_effect_value,
        "poison_delta": poison_delta,
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
        payload["root_quality_gain"] = base_effect_value
    elif pill_type == "root_remold":
        payload["root_quality_floor"] = base_effect_value
    return payload


def pill_usage_reason(profile_data: dict[str, Any], pill: dict[str, Any]) -> str:
    legacy_service = _legacy_service()
    if not legacy_service.realm_requirement_met(
        profile_data,
        pill.get("min_realm_stage"),
        pill.get("min_realm_layer"),
    ):
        return (
            f"需要达到 {legacy_service.format_realm_requirement(pill.get('min_realm_stage'), pill.get('min_realm_layer'))}"
            " 才能服用这枚丹药。"
        )
    pill_type = str(pill.get("pill_type") or "").strip()
    poison_reason = _pill_poison_lock_reason(profile_data, pill_type)
    if poison_reason:
        return poison_reason
    if pill_type == "stone":
        return "灵石收益类丹药已删除，当前无法服用。"
    if pill_type == "foundation":
        return "破境丹只能在对应的大境界突破时配合使用。"
    fortune_reason = legacy_service._fortune_pill_usage_reason(profile_data, pill)
    if fortune_reason:
        return fortune_reason
    if pill_type == "root_refine":
        effects = resolve_pill_effects(profile_data, pill)
        steps = max(int(round(float(effects.get("root_quality_gain", 0) or 0))), 0)
        current_quality = legacy_service._normalized_root_quality(profile_data)
        if current_quality in legacy_service.ROOT_SPECIAL_QUALITIES:
            return "当前已是特殊灵根，无法再用此丹淬炼。"
        if steps <= 0:
            return "这枚淬灵丹没有可生效的品阶。"
        if legacy_service._refined_root_payload(profile_data, steps) is None:
            return "当前灵根品质已达可淬炼上限。"
    if pill_type in legacy_service.ROOT_TRANSFORM_PILL_TYPES:
        if legacy_service._transformed_root_payload(profile_data, pill_type, pill.get("effect_value")) is None:
            return "这枚丹药当前无法改变你的灵根。"
    return ""


def pill_effect_summary(before_profile: dict[str, Any], after_profile: dict[str, Any]) -> str:
    legacy_service = _legacy_service()
    parts: list[str] = []
    before_root = legacy_service.format_root(before_profile)
    after_root = legacy_service.format_root(after_profile)
    first_stage = legacy_service.FIRST_REALM_STAGE
    before_stage = normalize_realm_stage(before_profile.get("realm_stage") or first_stage)
    after_stage = normalize_realm_stage(after_profile.get("realm_stage") or first_stage)
    before_layer = max(int(before_profile.get("realm_layer") or 1), 1)
    after_layer = max(int(after_profile.get("realm_layer") or 1), 1)

    def cultivation_progress_total(profile: dict[str, Any]) -> int:
        stage = normalize_realm_stage(profile.get("realm_stage") or first_stage)
        layer = max(int(profile.get("realm_layer") or 1), 1)
        cultivation = max(int(profile.get("cultivation") or 0), 0)
        total = cultivation
        for current_layer in range(1, layer):
            total += legacy_service.cultivation_threshold(stage, current_layer)
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
        }.get(key, legacy_service.ATTRIBUTE_LABELS.get(f"{key}_bonus", key))
        parts.append(f"{label} {'+' if delta > 0 else ''}{delta}")
    return "；".join(parts) if parts else "药力已经化开。"


def consume_pill_for_user(tg: int, pill_id: int, quantity: int = 1) -> dict[str, Any]:
    return _legacy_service().consume_pill_for_user(tg, pill_id, quantity=quantity)

def consume_pill_for_user_batch(tg: int, pill_id: int, quantity: int = 1) -> dict[str, Any]:
    legacy_service = _legacy_service()
    requested_quantity = max(int(quantity or 1), 1)

    if requested_quantity == 1:
        result = consume_pill_for_user(tg, pill_id)
        return {
            **result,
            "requested_quantity": 1,
            "used_count": 1,
            "completed": True,
            "stopped_reason": "",
        }

    pill = get_pill(pill_id)
    if pill is None or not pill.enabled:
        raise ValueError("未找到可用的丹药。")

    profile = legacy_service._require_alive_profile_obj(tg, "批量服用丹药")
    if is_retreating(profile):
        raise ValueError("闭关期间无法服用丹药。")

    before_profile = serialize_profile(profile)
    last_result: dict[str, Any] | None = None
    used_count = 0
    stopped_reason = ""

    for _ in range(requested_quantity):
        try:
            last_result = consume_pill_for_user(tg, pill_id)
        except ValueError as exc:
            if used_count <= 0:
                raise
            stopped_reason = str(exc).strip() or "后续已无法继续服用。"
            break
        used_count += 1

    if last_result is None:
        raise ValueError("服用丹药失败，请稍后再试。")

    bundle = last_result.get("profile") or legacy_service.serialize_full_profile(tg)
    after_profile = (bundle or {}).get("profile") or before_profile

    return {
        **last_result,
        "summary": pill_effect_summary(before_profile, after_profile),
        "requested_quantity": requested_quantity,
        "used_count": used_count,
        "completed": used_count >= requested_quantity and not stopped_reason,
        "stopped_reason": stopped_reason,
    }
