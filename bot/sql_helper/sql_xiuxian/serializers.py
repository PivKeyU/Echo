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

from bot.plugins.xiuxian_game.asset_images import resolve_image_url
from bot.plugins.xiuxian_game import cache as xiuxian_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby
from .constants import *  # noqa: F401 F403
from .models import *  # noqa: F401 F403

def utcnow() -> datetime:
    return datetime.utcnow()


def shanghai_now() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TZ)
    return value.astimezone(SHANGHAI_TZ).isoformat()


def _sanitize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_json_value(item) for item in value]
    return str(value)


def _slugify_achievement_key(raw: str | None, fallback: str) -> str:
    source = str(raw or fallback or "").strip().lower()
    key = re.sub(r"[^a-z0-9_\-]+", "_", source)
    key = re.sub(r"_+", "_", key).strip("_-")
    return key or "achievement"


def normalize_realm_stage(stage: str | None) -> str:
    raw = str(stage or "").strip()
    if not raw:
        return REALM_ORDER[0]
    normalized = LEGACY_REALM_ALIASES.get(raw, raw)
    if normalized in REALM_ORDER:
        return normalized
    return LEGACY_TO_NEW_REALM_STAGE.get(normalized, REALM_ORDER[0])


def _normalize_legacy_realm_stage(stage: str | None) -> str:
    raw = str(stage or "").strip()
    if not raw:
        return LEGACY_REALM_ORDER[0]
    normalized = LEGACY_REALM_ALIASES.get(raw, raw)
    return normalized if normalized in LEGACY_REALM_ORDER else LEGACY_REALM_ORDER[0]


def normalize_realm_layer(layer: int | str | None, default: int = 1) -> int:
    try:
        value = int(layer or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, REALM_LAYER_LIMIT))


def get_realm_stage_rule(stage: str | None) -> dict[str, int]:
    normalized = normalize_realm_stage(stage)
    return REALM_STAGE_RULES.get(normalized, REALM_STAGE_RULES[REALM_ORDER[0]])

def calculate_realm_threshold(stage: str | None, layer: int | str | None) -> int:
    rule = get_realm_stage_rule(stage)
    current_layer = normalize_realm_layer(layer)
    linear_threshold = int(rule["threshold_base"]) + (current_layer - 1) * int(rule["threshold_step"])
    layer_growth = max(current_layer - 1, 0)
    growth_multiplier = 1 + layer_growth * REALM_LAYER_THRESHOLD_GROWTH_RATE
    return max(int(round(linear_threshold * growth_multiplier)), linear_threshold)


def calculate_legacy_realm_threshold(stage: str | None, layer: int | str | None) -> int:
    current_stage = _normalize_legacy_realm_stage(stage)
    current_layer = normalize_realm_layer(layer)
    return 80 + LEGACY_REALM_ORDER.index(current_stage) * 30 + current_layer * 18


def is_legacy_realm_stage(stage: str | None) -> bool:
    normalized = _normalize_legacy_realm_stage(stage)
    return normalized in LEGACY_REALM_ORDER and normalized not in REALM_ORDER


def migrate_legacy_realm_state(stage: str | None, layer: int | str | None, cultivation: int | str | None) -> dict[str, Any]:
    raw_stage = str(stage or "").strip()
    target_stage = normalize_realm_stage(raw_stage)
    normalized_layer = normalize_realm_layer(layer)
    try:
        current_cultivation = max(int(cultivation or 0), 0)
    except (TypeError, ValueError):
        current_cultivation = 0
    try:
        original_layer = int(layer or normalized_layer)
    except (TypeError, ValueError):
        original_layer = normalized_layer

    if raw_stage in REALM_ORDER:
        threshold = calculate_realm_threshold(target_stage, normalized_layer)
        capped_cultivation = min(current_cultivation, threshold)
        return {
            "source_stage": raw_stage or target_stage,
            "target_stage": target_stage,
            "target_layer": normalized_layer,
            "target_cultivation": capped_cultivation,
            "changed": (
                target_stage != raw_stage
                or normalized_layer != original_layer
                or capped_cultivation != current_cultivation
            ),
            "legacy": False,
        }

    legacy_stage = _normalize_legacy_realm_stage(raw_stage)
    if legacy_stage not in LEGACY_REALM_ORDER:
        threshold = calculate_realm_threshold(target_stage, normalized_layer)
        capped_cultivation = min(current_cultivation, threshold)
        return {
            "source_stage": raw_stage or target_stage,
            "target_stage": target_stage,
            "target_layer": normalized_layer,
            "target_cultivation": capped_cultivation,
            "changed": (
                target_stage != raw_stage
                or normalized_layer != original_layer
                or capped_cultivation != current_cultivation
            ),
            "legacy": False,
        }

    legacy_threshold = calculate_legacy_realm_threshold(legacy_stage, normalized_layer)
    capped_cultivation = min(current_cultivation, legacy_threshold)
    legacy_progress = min(capped_cultivation / max(legacy_threshold, 1), 1.0)
    final_stage = normalize_realm_stage(legacy_stage)
    final_layer = normalized_layer
    final_threshold = calculate_realm_threshold(final_stage, final_layer)
    final_cultivation = min(int(round(final_threshold * legacy_progress)), final_threshold)

    return {
        "source_stage": legacy_stage,
        "target_stage": final_stage,
        "target_layer": final_layer,
        "target_cultivation": final_cultivation,
        "changed": (
            final_stage != raw_stage
            or final_layer != original_layer
            or final_cultivation != current_cultivation
        ),
        "legacy": True,
    }


def normalize_quality_level(level: int | str | None) -> int:
    if isinstance(level, str):
        level = QUALITY_LABEL_LEVELS.get(level.strip(), level)
    try:
        value = int(level or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(value, max(QUALITY_LEVEL_LABELS)))


def normalize_quality_label(label: str | None) -> str:
    level = normalize_quality_level(label or QUALITY_LEVEL_LABELS[1])
    return QUALITY_LEVEL_LABELS[level]


def get_quality_meta(level_or_label: int | str | None) -> dict[str, Any]:
    level = normalize_quality_level(level_or_label)
    return {
        "level": level,
        "label": QUALITY_LEVEL_LABELS[level],
        "color": QUALITY_LEVEL_COLORS.get(level, "#9ca3af"),
        "description": QUALITY_LEVEL_DESCRIPTIONS.get(level, ""),
        "feature": QUALITY_LEVEL_FEATURES.get(level, ""),
    }



def realm_index(stage: str | None) -> int:
    try:
        return REALM_ORDER.index(normalize_realm_stage(stage))
    except ValueError:
        return 0


def normalize_social_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    aliases = {
        "worldly": "worldly",
        "world": "worldly",
        "public": "worldly",
        "visible": "worldly",
        "入世": "worldly",
        "出世": "worldly",
        "secluded": "secluded",
        "hidden": "secluded",
        "hide": "secluded",
        "private": "secluded",
        "避世": "secluded",
        "隐世": "secluded",
    }
    return aliases.get(value, "worldly")


def normalize_mentorship_request_role(role: str | None) -> str:
    value = str(role or "").strip().lower()
    aliases = {
        "mentor": "mentor",
        "master": "mentor",
        "teacher": "mentor",
        "收徒": "mentor",
        "invite": "mentor",
        "disciple": "disciple",
        "student": "disciple",
        "apprentice": "disciple",
        "拜师": "disciple",
        "apply": "disciple",
    }
    return aliases.get(value, "disciple")


def normalize_gender(gender: str | None) -> str | None:
    value = str(gender or "").strip().lower()
    if not value:
        return None
    aliases = {
        "male": "male",
        "man": "male",
        "boy": "male",
        "m": "male",
        "男": "male",
        "female": "female",
        "woman": "female",
        "girl": "female",
        "f": "female",
        "女": "female",
    }
    return aliases.get(value)


def normalize_mentorship_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    aliases = {
        "active": "active",
        "ongoing": "active",
        "在籍": "active",
        "graduated": "graduated",
        "graduate": "graduated",
        "出师": "graduated",
        "dissolved": "dissolved",
        "ended": "dissolved",
        "leave": "dissolved",
        "解除": "dissolved",
    }
    return aliases.get(value, "active")


def normalize_mentorship_request_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    aliases = {
        "pending": "pending",
        "wait": "pending",
        "待处理": "pending",
        "accepted": "accepted",
        "accept": "accepted",
        "同意": "accepted",
        "rejected": "rejected",
        "reject": "rejected",
        "拒绝": "rejected",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "cancel": "cancelled",
        "撤回": "cancelled",
        "expired": "expired",
        "过期": "expired",
    }
    return aliases.get(value, "pending")


def normalize_marriage_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    aliases = {
        "active": "active",
        "married": "active",
        "已婚": "active",
        "结为道侣": "active",
        "divorced": "divorced",
        "divorce": "divorced",
        "ended": "divorced",
        "离婚": "divorced",
        "和离": "divorced",
        "解除": "divorced",
    }
    return aliases.get(value, "active")


def normalize_marriage_request_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    aliases = {
        "pending": "pending",
        "wait": "pending",
        "待处理": "pending",
        "accepted": "accepted",
        "accept": "accepted",
        "同意": "accepted",
        "rejected": "rejected",
        "reject": "rejected",
        "拒绝": "rejected",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "cancel": "cancelled",
        "撤回": "cancelled",
        "expired": "expired",
        "过期": "expired",
    }
    return aliases.get(value, "pending")


def serialize_profile(profile: XiuxianProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None

    realm_stage = normalize_realm_stage(profile.realm_stage)
    social_mode = normalize_social_mode(profile.social_mode)
    gender = normalize_gender(profile.gender)
    return {
        "tg": profile.tg,
        "display_name": profile.display_name,
        "username": profile.username,
        "display_label": profile.display_name or (f"@{profile.username}" if profile.username else f"TG {profile.tg}"),
        "consented": profile.consented,
        "gender": gender,
        "gender_label": GENDER_LABELS.get(gender, ""),
        "gender_set": gender in GENDER_LABELS,
        "root_type": profile.root_type,
        "root_primary": profile.root_primary,
        "root_secondary": profile.root_secondary,
        "root_relation": profile.root_relation,
        "root_bonus": profile.root_bonus,
        "root_quality": profile.root_quality,
        "root_quality_level": profile.root_quality_level,
        "root_quality_color": profile.root_quality_color,
        "realm_stage": realm_stage,
        "realm_layer": profile.realm_layer,
        "cultivation": profile.cultivation,
        "spiritual_stone": profile.spiritual_stone,
        "bone": profile.bone,
        "comprehension": profile.comprehension,
        "divine_sense": profile.divine_sense,
        "fortune": profile.fortune,
        "willpower": profile.willpower,
        "charisma": profile.charisma,
        "karma": profile.karma,
        "qi_blood": profile.qi_blood,
        "true_yuan": profile.true_yuan,
        "body_movement": profile.body_movement,
        "attack_power": profile.attack_power,
        "defense_power": profile.defense_power,
        "insight_bonus": profile.insight_bonus,
        "sect_contribution": profile.sect_contribution,
        "dan_poison": profile.dan_poison,
        "breakthrough_pill_uses": profile.breakthrough_pill_uses,
        "sect_id": profile.sect_id,
        "sect_role_key": profile.sect_role_key,
        "sect_role_label": SECT_ROLE_LABELS.get(profile.sect_role_key or "", profile.sect_role_key),
        "last_salary_claim_at": serialize_datetime(profile.last_salary_claim_at),
        "sect_joined_at": serialize_datetime(profile.sect_joined_at),
        "sect_betrayal_until": serialize_datetime(profile.sect_betrayal_until),
        "last_sect_attendance_at": serialize_datetime(profile.last_sect_attendance_at),
        "last_sect_attendance_method": profile.last_sect_attendance_method,
        "master_tg": profile.master_tg,
        "servitude_started_at": serialize_datetime(profile.servitude_started_at),
        "servitude_challenge_available_at": serialize_datetime(profile.servitude_challenge_available_at),
        "furnace_harvested_at": serialize_datetime(profile.furnace_harvested_at),
        "death_at": serialize_datetime(profile.death_at),
        "rebirth_count": int(profile.rebirth_count or 0),
        "robbery_daily_count": profile.robbery_daily_count,
        "robbery_day_key": profile.robbery_day_key,
        "current_artifact_id": profile.current_artifact_id,
        "active_talisman_id": profile.active_talisman_id,
        "current_technique_id": profile.current_technique_id,
        "current_title_id": profile.current_title_id,
        "technique_capacity": normalize_technique_capacity(profile.technique_capacity),
        "shop_name": profile.shop_name,
        "shop_broadcast": profile.shop_broadcast,
        "last_train_at": serialize_datetime(profile.last_train_at),
        "social_mode": social_mode,
        "social_mode_label": SOCIAL_MODE_LABELS.get(social_mode, "入世"),
        "is_secluded": social_mode == "secluded",
        "social_mode_updated_at": serialize_datetime(profile.social_mode_updated_at),
        "retreat_started_at": serialize_datetime(profile.retreat_started_at),
        "retreat_end_at": serialize_datetime(profile.retreat_end_at),
        "retreat_gain_per_minute": profile.retreat_gain_per_minute,
        "retreat_cost_per_minute": profile.retreat_cost_per_minute,
        "retreat_minutes_total": profile.retreat_minutes_total,
        "retreat_minutes_resolved": profile.retreat_minutes_resolved,
        "created_at": serialize_datetime(profile.created_at),
        "updated_at": serialize_datetime(profile.updated_at),
    }


def serialize_journal(row: XiuxianJournal | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tg": row.tg,
        "action_type": row.action_type,
        "title": row.title,
        "detail": row.detail,
        "created_at": serialize_datetime(row.created_at),
    }


def serialize_title(title: XiuxianTitle | None) -> dict[str, Any] | None:
    if title is None:
        return None
    return {
        "id": title.id,
        "name": title.name,
        "description": title.description,
        "color": title.color,
        "image_url": title.image_url,
        "attack_bonus": title.attack_bonus,
        "defense_bonus": title.defense_bonus,
        "bone_bonus": title.bone_bonus,
        "comprehension_bonus": title.comprehension_bonus,
        "divine_sense_bonus": title.divine_sense_bonus,
        "fortune_bonus": title.fortune_bonus,
        "qi_blood_bonus": title.qi_blood_bonus,
        "true_yuan_bonus": title.true_yuan_bonus,
        "body_movement_bonus": title.body_movement_bonus,
        "duel_rate_bonus": title.duel_rate_bonus,
        "cultivation_bonus": title.cultivation_bonus,
        "breakthrough_bonus": title.breakthrough_bonus,
        "extra_effects": title.extra_effects or {},
        "enabled": title.enabled,
        "created_at": serialize_datetime(title.created_at),
        "updated_at": serialize_datetime(title.updated_at),
    }


def serialize_user_title(row: XiuxianUserTitle | None, title: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tg": row.tg,
        "title_id": row.title_id,
        "source": row.source,
        "obtained_note": row.obtained_note,
        "title": title,
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_achievement(achievement: XiuxianAchievement | None) -> dict[str, Any] | None:
    if achievement is None:
        return None
    return {
        "id": achievement.id,
        "achievement_key": achievement.achievement_key,
        "name": achievement.name,
        "description": achievement.description,
        "metric_key": achievement.metric_key,
        "target_value": int(achievement.target_value or 0),
        "reward_config": achievement.reward_config or {},
        "notify_group": achievement.notify_group,
        "notify_private": achievement.notify_private,
        "enabled": achievement.enabled,
        "sort_order": achievement.sort_order,
        "created_at": serialize_datetime(achievement.created_at),
        "updated_at": serialize_datetime(achievement.updated_at),
    }


def serialize_achievement_progress(progress: XiuxianAchievementProgress | None) -> dict[str, Any] | None:
    if progress is None:
        return None
    return {
        "id": progress.id,
        "tg": progress.tg,
        "metric_key": progress.metric_key,
        "value": int(progress.current_value or 0),
        "created_at": serialize_datetime(progress.created_at),
        "updated_at": serialize_datetime(progress.updated_at),
    }


def serialize_user_achievement(
    row: XiuxianUserAchievement | None,
    achievement: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tg": row.tg,
        "achievement_id": row.achievement_id,
        "achievement": achievement,
        "reward_snapshot": row.reward_snapshot or {},
        "unlocked_at": serialize_datetime(row.unlocked_at),
        "private_notified_at": serialize_datetime(row.private_notified_at),
        "group_notified_at": serialize_datetime(row.group_notified_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_mentorship(row: XiuxianMentorship | None) -> dict[str, Any] | None:
    if row is None:
        return None
    status = normalize_mentorship_status(row.status)
    mentor_stage = normalize_realm_stage(row.mentor_realm_stage_snapshot)
    disciple_stage = normalize_realm_stage(row.disciple_realm_stage_snapshot)
    return {
        "id": row.id,
        "mentor_tg": int(row.mentor_tg or 0),
        "disciple_tg": int(row.disciple_tg or 0),
        "status": status,
        "status_label": MENTORSHIP_STATUS_LABELS.get(status, "师徒在籍"),
        "bond_value": max(int(row.bond_value or 0), 0),
        "teach_count": max(int(row.teach_count or 0), 0),
        "consult_count": max(int(row.consult_count or 0), 0),
        "last_teach_at": serialize_datetime(row.last_teach_at),
        "last_consult_at": serialize_datetime(row.last_consult_at),
        "mentor_realm_stage_snapshot": mentor_stage,
        "mentor_realm_layer_snapshot": max(int(row.mentor_realm_layer_snapshot or 0), 0),
        "disciple_realm_stage_snapshot": disciple_stage,
        "disciple_realm_layer_snapshot": max(int(row.disciple_realm_layer_snapshot or 0), 0),
        "mentor_realm_snapshot_text": f"{mentor_stage}{max(int(row.mentor_realm_layer_snapshot or 0), 0)}层" if mentor_stage else "",
        "disciple_realm_snapshot_text": f"{disciple_stage}{max(int(row.disciple_realm_layer_snapshot or 0), 0)}层" if disciple_stage else "",
        "graduated_at": serialize_datetime(row.graduated_at),
        "ended_at": serialize_datetime(row.ended_at),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_mentorship_request(row: XiuxianMentorshipRequest | None) -> dict[str, Any] | None:
    if row is None:
        return None
    sponsor_role = normalize_mentorship_request_role(row.sponsor_role)
    status = normalize_mentorship_request_status(row.status)
    mentor_tg = int(row.sponsor_tg if sponsor_role == "mentor" else row.target_tg)
    disciple_tg = int(row.target_tg if sponsor_role == "mentor" else row.sponsor_tg)
    return {
        "id": row.id,
        "sponsor_tg": int(row.sponsor_tg or 0),
        "target_tg": int(row.target_tg or 0),
        "sponsor_role": sponsor_role,
        "sponsor_role_label": MENTORSHIP_REQUEST_ROLE_LABELS.get(sponsor_role, "拜师申请"),
        "mentor_tg": mentor_tg,
        "disciple_tg": disciple_tg,
        "message": str(row.message or "").strip(),
        "status": status,
        "status_label": MENTORSHIP_REQUEST_STATUS_LABELS.get(status, "待处理"),
        "expires_at": serialize_datetime(row.expires_at),
        "responded_at": serialize_datetime(row.responded_at),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_marriage(row: XiuxianMarriage | None) -> dict[str, Any] | None:
    if row is None:
        return None
    status = normalize_marriage_status(row.status)
    return {
        "id": row.id,
        "husband_tg": int(row.husband_tg or 0),
        "wife_tg": int(row.wife_tg or 0),
        "status": status,
        "status_label": MARRIAGE_STATUS_LABELS.get(status, "已结为道侣"),
        "bond_value": max(int(row.bond_value or 0), 0),
        "dual_cultivation_count": max(int(row.dual_cultivation_count or 0), 0),
        "last_dual_cultivation_at": serialize_datetime(row.last_dual_cultivation_at),
        "ended_at": serialize_datetime(row.ended_at),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_marriage_request(row: XiuxianMarriageRequest | None) -> dict[str, Any] | None:
    if row is None:
        return None
    status = normalize_marriage_request_status(row.status)
    return {
        "id": row.id,
        "sponsor_tg": int(row.sponsor_tg or 0),
        "target_tg": int(row.target_tg or 0),
        "message": str(row.message or "").strip(),
        "status": status,
        "status_label": MARRIAGE_REQUEST_STATUS_LABELS.get(status, "待处理"),
        "expires_at": serialize_datetime(row.expires_at),
        "responded_at": serialize_datetime(row.responded_at),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }



def serialize_sect(sect: XiuxianSect | None) -> dict[str, Any] | None:
    if sect is None:
        return None
    return {
        "id": sect.id,
        "name": sect.name,
        "camp": sect.camp,
        "camp_label": SECT_CAMP_LABELS.get(sect.camp, sect.camp),
        "description": sect.description,
        "image_url": sect.image_url,
        "min_realm_stage": normalize_realm_stage(sect.min_realm_stage) if sect.min_realm_stage else None,
        "min_realm_layer": sect.min_realm_layer,
        "min_stone": sect.min_stone,
        "min_bone": sect.min_bone,
        "min_comprehension": sect.min_comprehension,
        "min_divine_sense": sect.min_divine_sense,
        "min_fortune": sect.min_fortune,
        "min_willpower": sect.min_willpower,
        "min_charisma": sect.min_charisma,
        "min_karma": sect.min_karma,
        "min_body_movement": sect.min_body_movement,
        "min_combat_power": int(sect.min_combat_power or 0),
        "attack_bonus": sect.attack_bonus,
        "defense_bonus": sect.defense_bonus,
        "duel_rate_bonus": sect.duel_rate_bonus,
        "cultivation_bonus": sect.cultivation_bonus,
        "fortune_bonus": sect.fortune_bonus,
        "body_movement_bonus": sect.body_movement_bonus,
        "pill_poison_resist": float(sect.pill_poison_resist or 0.0),
        "pill_poison_cap_bonus": int(sect.pill_poison_cap_bonus or 0),
        "farm_growth_speed": float(sect.farm_growth_speed or 0.0),
        "explore_drop_rate": int(sect.explore_drop_rate or 0),
        "craft_success_rate": int(sect.craft_success_rate or 0),
        "death_penalty_reduce": float(sect.death_penalty_reduce or 0.0),
        "salary_min_stay_days": max(int(sect.salary_min_stay_days or 0), 1),
        "entry_hint": sect.entry_hint,
        "enabled": sect.enabled,
    }


def serialize_error_log(row: XiuxianErrorLog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tg": row.tg,
        "username": row.username,
        "display_name": row.display_name,
        "scope": row.scope,
        "level": row.level,
        "operation": row.operation,
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
        "message": row.message,
        "detail": row.detail,
        "created_at": serialize_datetime(row.created_at),
    }


def serialize_sect_role(role: XiuxianSectRole | None) -> dict[str, Any] | None:
    if role is None:
        return None
    return {
        "id": role.id,
        "sect_id": role.sect_id,
        "role_key": role.role_key,
        "role_name": role.role_name,
        "attack_bonus": role.attack_bonus,
        "defense_bonus": role.defense_bonus,
        "duel_rate_bonus": role.duel_rate_bonus,
        "cultivation_bonus": role.cultivation_bonus,
        "monthly_salary": role.monthly_salary,
        "can_publish_tasks": role.can_publish_tasks,
        "sort_order": role.sort_order,
    }


def serialize_sect_treasury_item(row: XiuxianSectTreasuryItem | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "sect_id": row.sect_id,
        "item_kind": row.item_kind,
        "item_kind_label": ITEM_KIND_LABELS.get(row.item_kind, row.item_kind),
        "item_ref_id": row.item_ref_id,
        "quantity": max(int(row.quantity or 0), 0),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_material(material: XiuxianMaterial | None) -> dict[str, Any] | None:
    if material is None:
        return None
    quality = get_quality_meta(material.quality_level)
    description = str(material.description or "").strip()
    quality_note = description or MATERIAL_QUALITY_NOTES.get(int(quality["level"]), "") or quality["description"]
    can_plant = bool(material.can_plant)
    return {
        "id": material.id,
        "name": material.name,
        "quality_level": material.quality_level,
        "quality_label": quality["label"],
        "quality_color": quality["color"],
        "quality_description": quality["description"],
        "quality_feature": quality_note,
        "image_url": resolve_image_url(material.image_url, kind="material", name=material.name, quality=quality["label"]),
        "description": material.description,
        "can_plant": can_plant,
        "seed_price_stone": int(material.seed_price_stone or 0),
        "growth_minutes": int(material.growth_minutes or 0),
        "yield_min": int(material.yield_min or 0),
        "yield_max": int(material.yield_max or 0),
        "unlock_realm_stage": normalize_realm_stage(material.unlock_realm_stage) if material.unlock_realm_stage else None,
        "unlock_realm_layer": int(material.unlock_realm_layer or 1),
        "enabled": material.enabled,
    }


def serialize_recipe(recipe: XiuxianRecipe | None) -> dict[str, Any] | None:
    if recipe is None:
        return None
    return {
        "id": recipe.id,
        "name": recipe.name,
        "recipe_kind": recipe.recipe_kind,
        "recipe_kind_label": RECIPE_KIND_LABELS.get(recipe.recipe_kind, recipe.recipe_kind),
        "result_kind": recipe.result_kind,
        "result_kind_label": ITEM_KIND_LABELS.get(recipe.result_kind, recipe.result_kind),
        "result_ref_id": recipe.result_ref_id,
        "result_quantity": recipe.result_quantity,
        "base_success_rate": recipe.base_success_rate,
        "broadcast_on_success": recipe.broadcast_on_success,
        "enabled": recipe.enabled,
    }


def serialize_user_recipe(
    row: XiuxianUserRecipe | None,
    recipe: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tg": row.tg,
        "recipe_id": row.recipe_id,
        "source": row.source,
        "obtained_note": row.obtained_note,
        "recipe": recipe,
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_scene(scene: XiuxianScene | None) -> dict[str, Any] | None:
    if scene is None:
        return None
    return {
        "id": scene.id,
        "name": scene.name,
        "description": scene.description,
        "image_url": resolve_image_url(scene.image_url, kind="scene", name=scene.name, quality=scene.min_realm_stage),
        "max_minutes": scene.max_minutes,
        "min_realm_stage": normalize_realm_stage(scene.min_realm_stage) if scene.min_realm_stage else None,
        "min_realm_layer": scene.min_realm_layer,
        "min_combat_power": int(scene.min_combat_power or 0),
        "event_pool": _normalize_scene_event_pool(scene.event_pool),
        "enabled": scene.enabled,
    }


def serialize_scene_drop(drop: XiuxianSceneDrop | None) -> dict[str, Any] | None:
    if drop is None:
        return None
    return {
        "id": drop.id,
        "scene_id": drop.scene_id,
        "reward_kind": drop.reward_kind,
        "reward_kind_label": ITEM_KIND_LABELS.get(drop.reward_kind, drop.reward_kind),
        "reward_ref_id": drop.reward_ref_id,
        "quantity_min": drop.quantity_min,
        "quantity_max": drop.quantity_max,
        "weight": drop.weight,
        "stone_reward": drop.stone_reward,
        "event_text": drop.event_text,
    }


def serialize_exploration(exploration: XiuxianExploration | None) -> dict[str, Any] | None:
    if exploration is None:
        return None
    return {
        "id": exploration.id,
        "tg": exploration.tg,
        "scene_id": exploration.scene_id,
        "started_at": serialize_datetime(exploration.started_at),
        "end_at": serialize_datetime(exploration.end_at),
        "claimed": exploration.claimed,
        "reward_kind": exploration.reward_kind,
        "reward_kind_label": ITEM_KIND_LABELS.get(exploration.reward_kind or "", exploration.reward_kind),
        "reward_ref_id": exploration.reward_ref_id,
        "reward_quantity": exploration.reward_quantity,
        "stone_reward": exploration.stone_reward,
        "event_text": exploration.event_text,
        "outcome_payload": _sanitize_json_value(exploration.outcome_payload) or {},
    }


def serialize_task(task: XiuxianTask | None) -> dict[str, Any] | None:
    if task is None:
        return None
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "task_scope": task.task_scope,
        "task_scope_label": TASK_SCOPE_LABELS.get(task.task_scope, task.task_scope),
        "task_type": task.task_type,
        "task_type_label": TASK_TYPE_LABELS.get(task.task_type, task.task_type),
        "owner_tg": task.owner_tg,
        "sect_id": task.sect_id,
        "question_text": task.question_text,
        "image_url": task.image_url,
        "required_item_kind": task.required_item_kind,
        "required_item_kind_label": ITEM_KIND_LABELS.get(task.required_item_kind or "", task.required_item_kind),
        "required_item_ref_id": task.required_item_ref_id,
        "required_item_quantity": task.required_item_quantity,
        "reward_stone": task.reward_stone,
        "reward_cultivation": int(task.reward_cultivation or 0),
        "reward_item_kind": task.reward_item_kind,
        "reward_item_kind_label": ITEM_KIND_LABELS.get(task.reward_item_kind or "", task.reward_item_kind),
        "reward_item_ref_id": task.reward_item_ref_id,
        "reward_item_quantity": task.reward_item_quantity,
        "reward_item_escrowed": bool(getattr(task, "reward_item_escrowed", False)),
        "reward_stone_escrowed": bool(getattr(task, "reward_stone_escrowed", False)),
        "reward_scale_mode": str(task.reward_scale_mode or "fixed"),
        "requirement_metric_key": task.requirement_metric_key,
        "requirement_metric_target": max(int(task.requirement_metric_target or 0), 0),
        "max_claimants": task.max_claimants,
        "claimants_count": task.claimants_count,
        "active_in_group": task.active_in_group,
        "group_chat_id": task.group_chat_id,
        "group_message_id": task.group_message_id,
        "winner_tg": task.winner_tg,
        "enabled": task.enabled,
        "status": task.status,
        "deadline_at": serialize_datetime(task.deadline_at),
        "created_at": serialize_datetime(task.created_at),
    }


def serialize_encounter_template(template: XiuxianEncounterTemplate | None) -> dict[str, Any] | None:
    if template is None:
        return None
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "image_url": template.image_url,
        "button_text": template.button_text,
        "success_text": template.success_text,
        "broadcast_text": template.broadcast_text,
        "weight": template.weight,
        "active_seconds": template.active_seconds,
        "min_realm_stage": normalize_realm_stage(template.min_realm_stage) if template.min_realm_stage else None,
        "min_realm_layer": template.min_realm_layer,
        "min_combat_power": template.min_combat_power,
        "reward_stone_min": template.reward_stone_min,
        "reward_stone_max": template.reward_stone_max,
        "reward_cultivation_min": template.reward_cultivation_min,
        "reward_cultivation_max": template.reward_cultivation_max,
        "reward_item_kind": template.reward_item_kind,
        "reward_item_kind_label": ITEM_KIND_LABELS.get(template.reward_item_kind or "", template.reward_item_kind),
        "reward_item_ref_id": template.reward_item_ref_id,
        "reward_item_quantity_min": template.reward_item_quantity_min,
        "reward_item_quantity_max": template.reward_item_quantity_max,
        "reward_willpower": 0,
        "reward_charisma": 0,
        "reward_karma": 0,
        "enabled": template.enabled,
        "created_at": serialize_datetime(template.created_at),
        "updated_at": serialize_datetime(template.updated_at),
    }


def serialize_encounter_instance(instance: XiuxianEncounterInstance | None) -> dict[str, Any] | None:
    if instance is None:
        return None
    return {
        "id": instance.id,
        "template_id": instance.template_id,
        "template_name": instance.template_name,
        "group_chat_id": instance.group_chat_id,
        "message_id": instance.message_id,
        "button_text": instance.button_text,
        "status": instance.status,
        "reward_payload": _sanitize_json_value(instance.reward_payload) or {},
        "expires_at": serialize_datetime(instance.expires_at),
        "claimer_tg": instance.claimer_tg,
        "claimed_at": serialize_datetime(instance.claimed_at),
        "created_at": serialize_datetime(instance.created_at),
        "updated_at": serialize_datetime(instance.updated_at),
    }


def serialize_red_envelope(envelope: XiuxianRedEnvelope | None) -> dict[str, Any] | None:
    if envelope is None:
        return None
    target_display_name = ""
    if envelope.target_tg:
        target_display_name = get_emby_name_map([int(envelope.target_tg)]).get(int(envelope.target_tg), "")
    return {
        "id": envelope.id,
        "creator_tg": envelope.creator_tg,
        "cover_text": envelope.cover_text,
        "image_url": envelope.image_url,
        "mode": envelope.mode,
        "mode_label": ENVELOPE_MODE_LABELS.get(envelope.mode, envelope.mode),
        "target_tg": envelope.target_tg,
        "target_display_name": target_display_name,
        "amount_total": envelope.amount_total,
        "count_total": envelope.count_total,
        "remaining_amount": envelope.remaining_amount,
        "remaining_count": envelope.remaining_count,
        "status": envelope.status,
        "group_chat_id": envelope.group_chat_id,
        "message_id": envelope.message_id,
        "created_at": serialize_datetime(envelope.created_at),
    }


def serialize_artifact(artifact: XiuxianArtifact | None) -> dict[str, Any] | None:
    if artifact is None:
        return None
    quality = get_quality_meta(artifact.rarity)
    equip_slot = normalize_artifact_slot(artifact.equip_slot)
    equip_category = artifact_equip_category(equip_slot)
    combat_config = _normalize_combat_config(artifact.combat_config)
    curse_effects = _normalize_curse_effects(combat_config.get("curse_effects"))

    return {
        "id": artifact.id,
        "name": artifact.name,
        "rarity": quality["label"],
        "rarity_level": quality["level"],
        "quality_color": quality["color"],
        "quality_description": quality["description"],
        "quality_feature": quality["feature"],
        "artifact_type": artifact.artifact_type,
        "artifact_type_label": ARTIFACT_TYPE_LABELS.get(artifact.artifact_type, artifact.artifact_type),
        "artifact_role": artifact.artifact_role,
        "artifact_role_label": ARTIFACT_ROLE_LABELS.get(artifact.artifact_role, artifact.artifact_role),
        "equip_slot": equip_slot,
        "equip_slot_raw": artifact.equip_slot,
        "equip_slot_label": artifact_slot_label(equip_slot),
        "equip_category": equip_category,
        "equip_category_label": ARTIFACT_EQUIP_CATEGORY_LABELS.get(equip_category, equip_category),
        "artifact_set_id": artifact.artifact_set_id,
        "unique_item": bool(artifact.unique_item),
        "image_url": resolve_image_url(artifact.image_url, kind="artifact", name=artifact.name, quality=quality["label"]),
        "description": artifact.description,
        "attack_bonus": artifact.attack_bonus,
        "defense_bonus": artifact.defense_bonus,
        "bone_bonus": artifact.bone_bonus,
        "comprehension_bonus": artifact.comprehension_bonus,
        "divine_sense_bonus": artifact.divine_sense_bonus,
        "fortune_bonus": artifact.fortune_bonus,
        "qi_blood_bonus": artifact.qi_blood_bonus,
        "true_yuan_bonus": artifact.true_yuan_bonus,
        "body_movement_bonus": artifact.body_movement_bonus,
        "duel_rate_bonus": artifact.duel_rate_bonus,
        "cultivation_bonus": artifact.cultivation_bonus,
        "combat_config": combat_config,
        "curse_effects": curse_effects,
        "curse_summary": _format_curse_effect_summary(curse_effects),
        "min_realm_stage": normalize_realm_stage(artifact.min_realm_stage) if artifact.min_realm_stage else None,
        "min_realm_layer": artifact.min_realm_layer,
        "enabled": artifact.enabled,
    }


def artifact_equip_category(slot: str | None) -> str | None:
    slot_name = normalize_artifact_slot(slot)
    if not slot_name:
        return None
    return ARTIFACT_SLOT_CATEGORY_MAP.get(slot_name, "other")


def serialize_pill(pill: XiuxianPill | None) -> dict[str, Any] | None:
    if pill is None:
        return None
    quality = get_quality_meta(pill.rarity)

    return {
        "id": pill.id,
        "name": pill.name,
        "rarity": quality["label"],
        "rarity_level": quality["level"],
        "quality_color": quality["color"],
        "quality_description": quality["description"],
        "quality_feature": quality["feature"],
        "pill_type": pill.pill_type,
        "pill_type_label": PILL_TYPE_LABELS.get(pill.pill_type, pill.pill_type),
        "effect_label": PILL_TYPE_LABELS.get(pill.pill_type, pill.pill_type),
        "effect_value_label": PILL_EFFECT_VALUE_LABELS.get(pill.pill_type, "主效果"),
        "image_url": resolve_image_url(pill.image_url, kind="pill", name=pill.name, quality=quality["label"]),
        "description": pill.description,
        "effect_value": pill.effect_value,
        "poison_delta": pill.poison_delta,
        "attack_bonus": pill.attack_bonus,
        "defense_bonus": pill.defense_bonus,
        "bone_bonus": pill.bone_bonus,
        "comprehension_bonus": pill.comprehension_bonus,
        "divine_sense_bonus": pill.divine_sense_bonus,
        "fortune_bonus": pill.fortune_bonus,
        "qi_blood_bonus": pill.qi_blood_bonus,
        "true_yuan_bonus": pill.true_yuan_bonus,
        "body_movement_bonus": pill.body_movement_bonus,
        "min_realm_stage": normalize_realm_stage(pill.min_realm_stage) if pill.min_realm_stage else None,
        "min_realm_layer": pill.min_realm_layer,
        "enabled": pill.enabled,
    }


def serialize_talisman(talisman: XiuxianTalisman | None) -> dict[str, Any] | None:
    if talisman is None:
        return None
    quality = get_quality_meta(talisman.rarity)

    return {
        "id": talisman.id,
        "name": talisman.name,
        "rarity": quality["label"],
        "rarity_level": quality["level"],
        "quality_color": quality["color"],
        "quality_description": quality["description"],
        "quality_feature": quality["feature"],
        "image_url": resolve_image_url(talisman.image_url, kind="talisman", name=talisman.name, quality=quality["label"]),
        "description": talisman.description,
        "attack_bonus": talisman.attack_bonus,
        "defense_bonus": talisman.defense_bonus,
        "bone_bonus": talisman.bone_bonus,
        "comprehension_bonus": talisman.comprehension_bonus,
        "divine_sense_bonus": talisman.divine_sense_bonus,
        "fortune_bonus": talisman.fortune_bonus,
        "qi_blood_bonus": talisman.qi_blood_bonus,
        "true_yuan_bonus": talisman.true_yuan_bonus,
        "body_movement_bonus": talisman.body_movement_bonus,
        "duel_rate_bonus": talisman.duel_rate_bonus,
        "effect_uses": max(int(talisman.effect_uses or 1), 1),
        "combat_config": _normalize_combat_config(talisman.combat_config),
        "min_realm_stage": normalize_realm_stage(talisman.min_realm_stage) if talisman.min_realm_stage else None,
        "min_realm_layer": talisman.min_realm_layer,
        "enabled": talisman.enabled,
    }


def serialize_technique(technique: XiuxianTechnique | None) -> dict[str, Any] | None:
    if technique is None:
        return None
    quality = get_quality_meta(technique.rarity)
    return {
        "id": technique.id,
        "name": technique.name,
        "rarity": quality["label"],
        "rarity_level": quality["level"],
        "quality_color": quality["color"],
        "quality_description": quality["description"],
        "quality_feature": quality["feature"],
        "technique_type": technique.technique_type,
        "technique_type_label": TECHNIQUE_TYPE_LABELS.get(technique.technique_type, technique.technique_type),
        "image_url": resolve_image_url(technique.image_url, kind="technique", name=technique.name, quality=quality["label"]),
        "description": technique.description,
        "attack_bonus": technique.attack_bonus,
        "defense_bonus": technique.defense_bonus,
        "bone_bonus": technique.bone_bonus,
        "comprehension_bonus": technique.comprehension_bonus,
        "divine_sense_bonus": technique.divine_sense_bonus,
        "fortune_bonus": technique.fortune_bonus,
        "qi_blood_bonus": technique.qi_blood_bonus,
        "true_yuan_bonus": technique.true_yuan_bonus,
        "body_movement_bonus": technique.body_movement_bonus,
        "duel_rate_bonus": technique.duel_rate_bonus,
        "cultivation_bonus": technique.cultivation_bonus,
        "breakthrough_bonus": technique.breakthrough_bonus,
        "combat_config": _normalize_combat_config(technique.combat_config),
        "min_realm_stage": normalize_realm_stage(technique.min_realm_stage),
        "min_realm_layer": technique.min_realm_layer,
        "enabled": technique.enabled,
    }


def serialize_user_technique(
    row: XiuxianUserTechnique | None,
    technique: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tg": row.tg,
        "technique_id": row.technique_id,
        "source": row.source,
        "obtained_note": row.obtained_note,
        "technique": technique,
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_artifact_set(artifact_set: XiuxianArtifactSet | None) -> dict[str, Any] | None:
    if artifact_set is None:
        return None
    return {
        "id": artifact_set.id,
        "name": artifact_set.name,
        "description": artifact_set.description,
        "required_count": artifact_set.required_count,
        "attack_bonus": artifact_set.attack_bonus,
        "defense_bonus": artifact_set.defense_bonus,
        "bone_bonus": artifact_set.bone_bonus,
        "comprehension_bonus": artifact_set.comprehension_bonus,
        "divine_sense_bonus": artifact_set.divine_sense_bonus,
        "fortune_bonus": artifact_set.fortune_bonus,
        "qi_blood_bonus": artifact_set.qi_blood_bonus,
        "true_yuan_bonus": artifact_set.true_yuan_bonus,
        "body_movement_bonus": artifact_set.body_movement_bonus,
        "duel_rate_bonus": artifact_set.duel_rate_bonus,
        "cultivation_bonus": artifact_set.cultivation_bonus,
        "breakthrough_bonus": artifact_set.breakthrough_bonus,
        "enabled": artifact_set.enabled,
        "created_at": serialize_datetime(artifact_set.created_at),
        "updated_at": serialize_datetime(artifact_set.updated_at),
    }


def serialize_shop_item(item: XiuxianShopItem | None) -> dict[str, Any] | None:
    if item is None:
        return None

    return {
        "id": item.id,
        "owner_tg": item.owner_tg,
        "shop_name": item.shop_name,
        "item_kind": item.item_kind,
        "item_kind_label": ITEM_KIND_LABELS.get(item.item_kind, item.item_kind),
        "item_ref_id": item.item_ref_id,
        "item_name": item.item_name,
        "quantity": item.quantity,
        "price_stone": item.price_stone,
        "enabled": item.enabled,
        "is_official": item.is_official,
        "notice_group_chat_id": int(item.notice_group_chat_id or 0) or None,
        "notice_group_message_id": int(item.notice_group_message_id or 0) or None,
        "created_at": serialize_datetime(item.created_at),
    }


def serialize_auction_item(item: XiuxianAuctionItem | None) -> dict[str, Any] | None:
    if item is None:
        return None

    current_price = max(int(item.current_price_stone or 0), 0)
    opening_price = max(int(item.opening_price_stone or 0), 0)
    bid_increment = max(int(item.bid_increment_stone or 0), 1)
    has_bid = current_price > 0 and int(item.bid_count or 0) > 0
    next_bid_price = opening_price if not has_bid else current_price + bid_increment
    buyout_price = int(item.buyout_price_stone or 0)
    current_display_price = current_price if has_bid else opening_price
    status_label = {
        "active": "竞拍中",
        "sold": "已成交",
        "expired": "已流拍",
        "cancelled": "已取消",
    }.get(str(item.status or "active"), str(item.status or "active"))

    return {
        "id": item.id,
        "owner_tg": item.owner_tg,
        "owner_display_name": item.owner_display_name or "",
        "item_kind": item.item_kind,
        "item_kind_label": ITEM_KIND_LABELS.get(item.item_kind, item.item_kind),
        "item_ref_id": item.item_ref_id,
        "item_name": item.item_name,
        "quantity": max(int(item.quantity or 0), 0),
        "opening_price_stone": opening_price,
        "current_price_stone": current_price,
        "current_display_price_stone": current_display_price,
        "bid_increment_stone": bid_increment,
        "next_bid_price_stone": next_bid_price,
        "buyout_price_stone": buyout_price,
        "fee_percent": max(int(item.fee_percent or 0), 0),
        "highest_bidder_tg": item.highest_bidder_tg,
        "highest_bidder_display_name": item.highest_bidder_display_name or "",
        "winner_tg": item.winner_tg,
        "winner_display_name": item.winner_display_name or "",
        "bid_count": max(int(item.bid_count or 0), 0),
        "has_bid": has_bid,
        "status": item.status,
        "status_label": status_label,
        "group_chat_id": item.group_chat_id,
        "group_message_id": item.group_message_id,
        "final_price_stone": int(item.final_price_stone or 0),
        "seller_income_stone": int(item.seller_income_stone or 0),
        "fee_amount_stone": int(item.fee_amount_stone or 0),
        "end_at": serialize_datetime(item.end_at),
        "completed_at": serialize_datetime(item.completed_at),
        "created_at": serialize_datetime(item.created_at),
        "updated_at": serialize_datetime(item.updated_at),
    }


def serialize_auction_bid(item: XiuxianAuctionBid | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.id,
        "auction_id": item.auction_id,
        "bidder_tg": item.bidder_tg,
        "bidder_display_name": item.bidder_display_name or "",
        "bid_amount_stone": int(item.bid_amount_stone or 0),
        "action_type": item.action_type,
        "created_at": serialize_datetime(item.created_at),
    }


def serialize_arena(item: XiuxianArena | None) -> dict[str, Any] | None:
    if item is None:
        return None
    remaining_seconds = 0
    if item.end_at is not None:
        remaining_seconds = max(int((item.end_at - utcnow()).total_seconds()), 0)
    status = str(item.status or "active")
    status_label = {
        "active": "开放挑战",
        "finished": "已结束",
        "cancelled": "已取消",
    }.get(status, status)
    if status == "active" and bool(item.battle_in_progress):
        status_label = "攻擂中"
    return {
        "id": item.id,
        "owner_tg": int(item.owner_tg or 0),
        "owner_display_name": item.owner_display_name or "",
        "champion_tg": int(item.champion_tg or 0),
        "champion_display_name": item.champion_display_name or "",
        "group_chat_id": int(item.group_chat_id or 0),
        "group_message_id": int(item.group_message_id or 0) or None,
        "realm_stage": normalize_realm_stage(item.realm_stage),
        "duration_minutes": max(int(item.duration_minutes or 0), 0),
        "reward_cultivation": max(int(item.reward_cultivation or 0), 0),
        "challenge_count": max(int(item.challenge_count or 0), 0),
        "defense_success_count": max(int(item.defense_success_count or 0), 0),
        "champion_change_count": max(int(item.champion_change_count or 0), 0),
        "battle_in_progress": bool(item.battle_in_progress),
        "current_challenger_tg": int(item.current_challenger_tg or 0) or None,
        "current_challenger_display_name": item.current_challenger_display_name or "",
        "last_winner_tg": int(item.last_winner_tg or 0) or None,
        "last_winner_display_name": item.last_winner_display_name or "",
        "last_loser_tg": int(item.last_loser_tg or 0) or None,
        "last_loser_display_name": item.last_loser_display_name or "",
        "latest_result_summary": item.latest_result_summary or "",
        "status": status,
        "status_label": status_label,
        "end_at": serialize_datetime(item.end_at),
        "completed_at": serialize_datetime(item.completed_at),
        "created_at": serialize_datetime(item.created_at),
        "updated_at": serialize_datetime(item.updated_at),
        "remaining_seconds": remaining_seconds,
        "ended": item.end_at <= utcnow() if item.end_at is not None else False,
    }


def serialize_image_upload_permission(permission: XiuxianImageUploadPermission | None) -> dict[str, Any] | None:
    if permission is None:
        return None

    return {
        "tg": permission.tg,
        "created_at": serialize_datetime(permission.created_at),
        "updated_at": serialize_datetime(permission.updated_at),
    }


def serialize_emby_account(account: Emby | None) -> dict[str, Any] | None:
    if account is None:
        return None

    return {
        "tg": int(account.tg),
        "name": account.name,
        "embyid": account.embyid,
        "lv": account.lv,
        "us": int(account.us or 0),
        "iv": int(account.iv or 0),
        "cr": serialize_datetime(account.cr),
        "ex": serialize_datetime(account.ex),
        "ch": serialize_datetime(account.ch),
    }


# ── Boss serializers ──────────────────────────────────────────


def serialize_boss_config(boss: XiuxianBossConfig | None) -> dict[str, Any] | None:
    if boss is None:
        return None
    return {
        "id": int(boss.id),
        "name": boss.name,
        "boss_type": boss.boss_type,
        "realm_stage": boss.realm_stage,
        "description": boss.description,
        "image_url": resolve_image_url(boss.image_url, kind="boss", name=boss.name, quality=boss.realm_stage),
        "hp": int(boss.hp or 0),
        "attack_power": int(boss.attack_power or 0),
        "defense_power": int(boss.defense_power or 0),
        "body_movement": int(boss.body_movement or 0),
        "divine_sense": int(boss.divine_sense or 0),
        "fortune": int(boss.fortune or 0),
        "qi_blood": int(boss.qi_blood or 0),
        "true_yuan": int(boss.true_yuan or 0),
        "skill_name": boss.skill_name,
        "skill_ratio_percent": int(boss.skill_ratio_percent or 0),
        "skill_hit_bonus": int(boss.skill_hit_bonus or 0),
        "passive_name": boss.passive_name,
        "passive_effect_kind": boss.passive_effect_kind,
        "passive_ratio_percent": int(boss.passive_ratio_percent or 0),
        "passive_chance": int(boss.passive_chance or 0),
        "loot_pills_json": boss.loot_pills_json,
        "loot_materials_json": boss.loot_materials_json,
        "loot_artifacts_json": boss.loot_artifacts_json,
        "loot_talismans_json": boss.loot_talismans_json,
        "loot_recipes_json": boss.loot_recipes_json,
        "loot_techniques_json": boss.loot_techniques_json,
        "stone_reward_min": int(boss.stone_reward_min or 0),
        "stone_reward_max": int(boss.stone_reward_max or 0),
        "cultivation_reward": int(boss.cultivation_reward or 0),
        "daily_attempt_limit": int(boss.daily_attempt_limit or 0),
        "ticket_cost_stone": int(boss.ticket_cost_stone or 0),
        "flavor_text": boss.flavor_text,
        "sort_order": int(boss.sort_order or 0),
        "enabled": bool(boss.enabled),
        "created_at": serialize_datetime(boss.created_at),
        "updated_at": serialize_datetime(boss.updated_at),
    }


def serialize_boss_defeat(row: XiuxianBossDefeat | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row.id),
        "tg": int(row.tg),
        "boss_id": int(row.boss_id),
        "defeat_count": int(row.defeat_count or 0),
        "daily_attempts": int(row.daily_attempts or 0),
        "day_key": row.day_key,
        "last_defeated_at": serialize_datetime(row.last_defeated_at),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


def serialize_world_boss_instance(instance: XiuxianWorldBossInstance | None) -> dict[str, Any] | None:
    if instance is None:
        return None
    return {
        "id": int(instance.id),
        "boss_id": int(instance.boss_id),
        "current_hp": int(instance.current_hp or 0),
        "max_hp": int(instance.max_hp or 0),
        "status": instance.status,
        "spawned_at": serialize_datetime(instance.spawned_at),
        "expires_at": serialize_datetime(instance.expires_at),
        "defeated_at": serialize_datetime(instance.defeated_at),
        "notice_message_id": instance.notice_message_id,
        "notice_group_chat_id": instance.notice_group_chat_id,
        "created_at": serialize_datetime(instance.created_at),
        "updated_at": serialize_datetime(instance.updated_at),
    }


def serialize_world_boss_damage(row: XiuxianWorldBossDamage | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row.id),
        "instance_id": int(row.instance_id),
        "tg": int(row.tg),
        "total_damage": int(row.total_damage or 0),
        "attack_count": int(row.attack_count or 0),
        "last_attack_at": serialize_datetime(row.last_attack_at),
        "created_at": serialize_datetime(row.created_at),
        "updated_at": serialize_datetime(row.updated_at),
    }


_PENDING_PROFILE_CACHE_INVALIDATIONS = "xiuxian_pending_profile_cache_invalidations"
_PENDING_USER_VIEW_CACHE_INVALIDATIONS = "xiuxian_pending_user_view_cache_invalidations"
_PENDING_CATALOG_CACHE_INVALIDATIONS = "xiuxian_pending_catalog_cache_invalidations"
_PENDING_SETTINGS_CACHE_INVALIDATIONS = "xiuxian_pending_settings_cache_invalidations"
_BOSS_LOOT_FIELDS = (
    "loot_pills_json",
    "loot_materials_json",
    "loot_artifacts_json",
    "loot_talismans_json",
    "loot_recipes_json",
    "loot_techniques_json",
)
_BOSS_LOOT_FIELD_ALIASES = {
    "loot_pills_json": ("loot_pills",),
    "loot_materials_json": ("loot_materials",),
    "loot_artifacts_json": ("loot_artifacts",),
    "loot_talismans_json": ("loot_talismans",),
    "loot_recipes_json": ("loot_recipes",),
    "loot_techniques_json": ("loot_techniques",),
}


def _restore_datetime_value(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _serialize_model_snapshot(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    payload: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            payload[column.name] = value.isoformat()
        elif isinstance(value, (dict, list)):
            payload[column.name] = copy.deepcopy(value)
        else:
            payload[column.name] = value
    return payload


def _restore_model_snapshot(model_cls, payload: dict[str, Any] | None):
    if not isinstance(payload, dict):
        return None
    normalized = dict(payload)
    for column in model_cls.__table__.columns:
        if isinstance(column.type, DateTime):
            normalized[column.name] = _restore_datetime_value(normalized.get(column.name))
    return model_cls(**normalized)



def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return int(default)


def _named_quality_sort_key(payload: dict[str, Any], quality_key: str = "rarity_level") -> tuple[int, str, int]:
    return (
        -_coerce_int(payload.get(quality_key), 0),
        str(payload.get("name") or ""),
        -_coerce_int(payload.get("id"), 0),
    )


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def normalize_technique_capacity(value: Any, default: int = DEFAULT_TECHNIQUE_CAPACITY) -> int:
    return min(max(_coerce_int(value, default), 1), MAX_TECHNIQUE_CAPACITY)

CURSE_TRIGGER_ACTION_LABELS = {
    "practice": "吐纳",
    "commission": "委托",
    "exploration": "探索",
    "fishing": "垂钓",
    "personal_boss": "个人Boss",
    "world_boss": "世界Boss",
}


def _normalize_curse_effects(raw: Any) -> dict[str, Any]:
    payload = _sanitize_json_value(copy.deepcopy(raw)) if isinstance(raw, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
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


def _format_curse_effect_summary(curse: dict[str, Any] | None) -> str:
    payload = curse or {}
    chance = max(min(_coerce_int(payload.get("trigger_chance_percent"), 0), 100), 0)
    if chance <= 0:
        return ""
    actions = [
        CURSE_TRIGGER_ACTION_LABELS[action]
        for action in payload.get("trigger_actions") or []
        if action in CURSE_TRIGGER_ACTION_LABELS
    ]
    parts = [f"{chance}% 概率反噬"]
    if actions:
        parts.insert(0, "、".join(actions))
    stone_loss_percent = max(min(_coerce_int(payload.get("stone_loss_percent"), 0), 100), 0)
    stone_loss_min = max(_coerce_int(payload.get("stone_loss_min"), 0), 0)
    stone_loss_cap = max(_coerce_int(payload.get("stone_loss_cap"), 0), 0)
    if stone_loss_percent > 0 or stone_loss_min > 0:
        stone_parts: list[str] = []
        if stone_loss_percent > 0:
            stone_parts.append(f"吞走 {stone_loss_percent}% 灵石")
        if stone_loss_min > 0:
            stone_parts.append(f"至少 {stone_loss_min}")
        if stone_loss_cap > 0:
            stone_parts.append(f"至多 {stone_loss_cap}")
        parts.append("，".join(stone_parts))
    poison_gain = max(_coerce_int(payload.get("dan_poison_gain"), 0), 0)
    if poison_gain > 0:
        parts.append(f"丹毒 +{poison_gain}")
    summary = str(payload.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    return "；".join(part for part in parts if part)


def _normalize_duel_bet_amount_options(
    raw_value: Any,
    *,
    minimum: int,
    maximum: int,
) -> list[int]:
    if isinstance(raw_value, str):
        items = [part for part in re.split(r"[\s,，、;；|/]+", raw_value.strip()) if part]
    elif isinstance(raw_value, (list, tuple, set)):
        items = list(raw_value)
    elif raw_value is None:
        items = list(DEFAULT_SETTINGS.get("duel_bet_amount_options") or [])
    else:
        items = [raw_value]

    values: list[int] = []
    seen: set[int] = set()
    for item in items:
        amount = _coerce_int(item, 0)
        if amount < minimum or amount > maximum or amount in seen:
            continue
        seen.add(amount)
        values.append(amount)
    values.sort()
    return values[:8]



def _normalize_combat_config(raw: Any) -> dict[str, Any]:
    # 战斗配置来自后台 JSON 表单，入库前统一裁剪字段和数值范围，避免前端传脏数据。
    payload = _sanitize_json_value(copy.deepcopy(raw)) if isinstance(raw, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    payload["opening_text"] = str(payload.get("opening_text") or "").strip()
    payload["active_effects"] = (
        _sanitize_json_value(copy.deepcopy(payload.get("active_effects")))
        if isinstance(payload.get("active_effects"), dict)
        else {}
    )
    payload["utility_effects"] = (
        _sanitize_json_value(copy.deepcopy(payload.get("utility_effects")))
        if isinstance(payload.get("utility_effects"), dict)
        else {}
    )
    payload["curse_effects"] = _normalize_curse_effects(payload.get("curse_effects"))
    for key in ("skills", "passives"):
        normalized_rows: list[dict[str, Any]] = []
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            entry = {str(k): _sanitize_json_value(v) for k, v in item.items()}
            entry["name"] = str(entry.get("name") or entry.get("label") or "").strip()
            entry["kind"] = str(entry.get("kind") or "").strip()
            entry["chance"] = max(min(_coerce_int(entry.get("chance"), 0), 100), 0)
            entry["duration"] = max(_coerce_int(entry.get("duration"), 0), 0)
            entry["flat_damage"] = _coerce_int(entry.get("flat_damage"), 0)
            entry["flat_shield"] = max(_coerce_int(entry.get("flat_shield"), 0), 0)
            entry["flat_heal"] = max(_coerce_int(entry.get("flat_heal"), 0), 0)
            entry["cost_true_yuan"] = max(_coerce_int(entry.get("cost_true_yuan"), 0), 0)
            entry["ratio_percent"] = _coerce_int(entry.get("ratio_percent"), 0)
            entry["dodge_bonus"] = _coerce_int(entry.get("dodge_bonus"), 0)
            entry["hit_bonus"] = _coerce_int(entry.get("hit_bonus"), 0)
            entry["defense_ratio_percent"] = _coerce_int(entry.get("defense_ratio_percent"), 0)
            entry["attack_ratio_percent"] = _coerce_int(entry.get("attack_ratio_percent"), 0)
            entry["trigger"] = str(entry.get("trigger") or "attack").strip() or "attack"
            entry["text"] = str(entry.get("text") or "").strip()
            if entry["kind"]:
                normalized_rows.append(entry)
        payload[key] = normalized_rows
    return payload


def _normalize_scene_event_pool(raw: Any) -> list[dict[str, Any]]:
    # 兼容旧字符串写法与新结构化写法，升级后旧秘境配置也能继续读取。
    rows: list[dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            rows.append(
                {
                    "name": "",
                    "description": text,
                    "event_type": "encounter",
                    "weight": 1,
                    "stone_bonus_min": 0,
                    "stone_bonus_max": 0,
                    "stone_loss_min": 0,
                    "stone_loss_max": 0,
                    "bonus_reward_kind": None,
                    "bonus_reward_ref_id": None,
                    "bonus_quantity_min": 1,
                    "bonus_quantity_max": 1,
                    "bonus_chance": 0,
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        payload = _sanitize_json_value(item)
        bonus_kind = str(payload.get("bonus_reward_kind") or "").strip() or None
        if bonus_kind and bonus_kind not in ITEM_KIND_LABELS:
            bonus_kind = None
        rows.append(
            {
                "name": str(payload.get("name") or "").strip(),
                "description": str(payload.get("description") or payload.get("text") or "").strip(),
                "event_type": str(payload.get("event_type") or "encounter").strip() or "encounter",
                "weight": max(_coerce_int(payload.get("weight"), 1), 1),
                "stone_bonus_min": max(_coerce_int(payload.get("stone_bonus_min"), 0), 0),
                "stone_bonus_max": max(_coerce_int(payload.get("stone_bonus_max"), payload.get("stone_bonus_min") or 0), 0),
                "stone_loss_min": max(_coerce_int(payload.get("stone_loss_min"), 0), 0),
                "stone_loss_max": max(_coerce_int(payload.get("stone_loss_max"), payload.get("stone_loss_min") or 0), 0),
                "bonus_reward_kind": bonus_kind,
                "bonus_reward_ref_id": _coerce_int(payload.get("bonus_reward_ref_id"), 0) or None,
                "bonus_quantity_min": max(_coerce_int(payload.get("bonus_quantity_min"), 1), 1),
                "bonus_quantity_max": max(_coerce_int(payload.get("bonus_quantity_max"), payload.get("bonus_quantity_min") or 1), 1),
                "bonus_chance": max(min(_coerce_int(payload.get("bonus_chance"), 0), 100), 0),
            }
        )
    return rows


def _normalize_common_bonus_fields(fields: dict[str, Any]) -> dict[str, int]:
    return {
        "attack_bonus": _coerce_int(fields.get("attack_bonus"), 0),
        "defense_bonus": _coerce_int(fields.get("defense_bonus"), 0),
        "bone_bonus": _coerce_int(fields.get("bone_bonus"), 0),
        "comprehension_bonus": _coerce_int(fields.get("comprehension_bonus"), 0),
        "divine_sense_bonus": _coerce_int(fields.get("divine_sense_bonus"), 0),
        "fortune_bonus": _coerce_int(fields.get("fortune_bonus"), 0),
        "qi_blood_bonus": _coerce_int(fields.get("qi_blood_bonus"), 0),
        "true_yuan_bonus": _coerce_int(fields.get("true_yuan_bonus"), 0),
        "body_movement_bonus": _coerce_int(fields.get("body_movement_bonus"), 0),
    }


def _normalize_title_fields(fields: dict[str, Any]) -> dict[str, Any]:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("title name is required")
    payload = {
        "name": name,
        "description": str(fields.get("description") or "").strip(),
        "color": str(fields.get("color") or "").strip()[:255],
        "image_url": str(fields.get("image_url") or "").strip(),
        "enabled": _coerce_bool(fields.get("enabled"), True),
        "extra_effects": fields.get("extra_effects") if isinstance(fields.get("extra_effects"), dict) else {},
    }
    payload.update(_normalize_common_bonus_fields(fields))
    payload["duel_rate_bonus"] = _coerce_int(fields.get("duel_rate_bonus"), 0)
    payload["cultivation_bonus"] = _coerce_int(fields.get("cultivation_bonus"), 0)
    payload["breakthrough_bonus"] = _coerce_int(fields.get("breakthrough_bonus"), 0)
    return payload



def _normalize_reward_config(raw: Any) -> dict[str, Any]:
    # 成就奖励允许后台自由编辑，但这里只保留可识别且安全的奖励字段。
    payload = dict(raw) if isinstance(raw, dict) else {}
    payload["spiritual_stone"] = max(_coerce_int(payload.get("spiritual_stone"), 0), 0)
    payload["cultivation"] = max(_coerce_int(payload.get("cultivation"), 0), 0)
    payload["titles"] = [
        int(item)
        for item in (payload.get("titles") or payload.get("title_ids") or [])
        if str(item).strip().isdigit() and int(item) > 0
    ]
    items: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or item.get("item_kind") or "").strip()
        ref_id = _coerce_int(item.get("ref_id") or item.get("item_ref_id"), 0)
        quantity = max(_coerce_int(item.get("quantity"), 0), 0)
        if kind not in ITEM_KIND_LABELS or ref_id <= 0 or quantity <= 0:
            continue
        items.append(
            {
                "kind": kind,
                "ref_id": ref_id,
                "quantity": quantity,
            }
        )
    payload["items"] = items
    payload["message"] = str(payload.get("message") or "").strip()
    return payload


def _normalize_achievement_fields(fields: dict[str, Any]) -> dict[str, Any]:
    metric_key = str(fields.get("metric_key") or "").strip()
    if not metric_key:
        raise ValueError("achievement metric_key is required")
    target_value = max(int(fields.get("target_value") or 0), 1)
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("achievement name is required")
    achievement_key = _slugify_achievement_key(
        fields.get("achievement_key") or fields.get("key"),
        f"{metric_key}_{target_value}",
    )
    return {
        "achievement_key": achievement_key,
        "name": name,
        "description": str(fields.get("description") or "").strip(),
        "metric_key": metric_key,
        "target_value": target_value,
        "reward_config": _normalize_reward_config(fields.get("reward_config")),
        "notify_group": _coerce_bool(fields.get("notify_group"), True),
        "notify_private": _coerce_bool(fields.get("notify_private"), True),
        "enabled": _coerce_bool(fields.get("enabled"), True),
        "sort_order": max(_coerce_int(fields.get("sort_order"), 0), 0),
    }


def _normalize_common_item_fields(fields: dict[str, Any], *, rarity_default: str = "凡品") -> dict[str, Any]:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    min_realm_stage = fields.get("min_realm_stage")
    return {
        "name": name,
        "rarity": normalize_quality_label(fields.get("rarity") or rarity_default),
        "image_url": str(fields.get("image_url") or "").strip(),
        "description": str(fields.get("description") or "").strip(),
        "min_realm_stage": normalize_realm_stage(min_realm_stage) if min_realm_stage else None,
        "min_realm_layer": max(_coerce_int(fields.get("min_realm_layer"), 1), 1),
        "enabled": _coerce_bool(fields.get("enabled"), True),
    }


def _normalize_artifact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_common_item_fields(fields)
    payload.update(_normalize_common_bonus_fields(fields))
    payload["artifact_type"] = str(fields.get("artifact_type") or "battle").strip() or "battle"
    payload["artifact_role"] = str(fields.get("artifact_role") or payload["artifact_type"] or "battle").strip() or "battle"
    payload["equip_slot"] = normalize_artifact_slot(fields.get("equip_slot") or "weapon")
    payload["artifact_set_id"] = _coerce_int(fields.get("artifact_set_id"), 0) or None
    payload["unique_item"] = _coerce_bool(fields.get("unique_item"), False)
    payload["duel_rate_bonus"] = _coerce_int(fields.get("duel_rate_bonus"), 0)
    payload["cultivation_bonus"] = _coerce_int(fields.get("cultivation_bonus"), 0)
    payload["combat_config"] = _normalize_combat_config(fields.get("combat_config"))
    return payload


def _normalize_artifact_set_fields(fields: dict[str, Any]) -> dict[str, Any]:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("artifact set name is required")
    payload = _normalize_common_bonus_fields(fields)
    payload.update(
        {
            "name": name,
            "description": str(fields.get("description") or "").strip(),
            "required_count": max(_coerce_int(fields.get("required_count"), 2), 2),
            "duel_rate_bonus": _coerce_int(fields.get("duel_rate_bonus"), 0),
            "cultivation_bonus": _coerce_int(fields.get("cultivation_bonus"), 0),
            "breakthrough_bonus": _coerce_int(fields.get("breakthrough_bonus"), 0),
            "enabled": _coerce_bool(fields.get("enabled"), True),
        }
    )
    return payload


def _normalize_sect_fields(fields: dict[str, Any]) -> dict[str, Any]:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("sect name is required")
    min_realm_stage = fields.get("min_realm_stage")
    return {
        "name": name,
        "camp": str(fields.get("camp") or "orthodox").strip() or "orthodox",
        "description": str(fields.get("description") or "").strip(),
        "image_url": str(fields.get("image_url") or "").strip(),
        "min_realm_stage": normalize_realm_stage(min_realm_stage) if min_realm_stage else None,
        "min_realm_layer": max(_coerce_int(fields.get("min_realm_layer"), 1), 1),
        "min_stone": max(_coerce_int(fields.get("min_stone"), 0), 0),
        "min_bone": max(_coerce_int(fields.get("min_bone"), 0), 0),
        "min_comprehension": max(_coerce_int(fields.get("min_comprehension"), 0), 0),
        "min_divine_sense": max(_coerce_int(fields.get("min_divine_sense"), 0), 0),
        "min_fortune": max(_coerce_int(fields.get("min_fortune"), 0), 0),
        "min_willpower": max(_coerce_int(fields.get("min_willpower"), 0), 0),
        "min_charisma": max(_coerce_int(fields.get("min_charisma"), 0), 0),
        "min_karma": max(_coerce_int(fields.get("min_karma"), 0), 0),
        "min_body_movement": max(_coerce_int(fields.get("min_body_movement"), 0), 0),
        "min_combat_power": max(_coerce_int(fields.get("min_combat_power"), 0), 0),
        "attack_bonus": _coerce_int(fields.get("attack_bonus"), 0),
        "defense_bonus": _coerce_int(fields.get("defense_bonus"), 0),
        "duel_rate_bonus": _coerce_int(fields.get("duel_rate_bonus"), 0),
        "cultivation_bonus": _coerce_int(fields.get("cultivation_bonus"), 0),
        "fortune_bonus": _coerce_int(fields.get("fortune_bonus"), 0),
        "body_movement_bonus": _coerce_int(fields.get("body_movement_bonus"), 0),
        "pill_poison_resist": max(min(float(fields.get("pill_poison_resist") or 0.0), 1.0), 0.0),
        "pill_poison_cap_bonus": max(_coerce_int(fields.get("pill_poison_cap_bonus"), 0), 0),
        "farm_growth_speed": max(min(float(fields.get("farm_growth_speed") or 0.0), 1.0), 0.0),
        "explore_drop_rate": max(_coerce_int(fields.get("explore_drop_rate"), 0), 0),
        "craft_success_rate": max(_coerce_int(fields.get("craft_success_rate"), 0), 0),
        "death_penalty_reduce": max(min(float(fields.get("death_penalty_reduce") or 0.0), 1.0), 0.0),
        "salary_min_stay_days": max(_coerce_int(fields.get("salary_min_stay_days"), DEFAULT_SETTINGS["sect_salary_min_stay_days"]), 1),
        "entry_hint": str(fields.get("entry_hint") or "").strip(),
        "enabled": _coerce_bool(fields.get("enabled"), True),
    }


def _normalize_pill_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_common_item_fields(fields)
    payload.update(_normalize_common_bonus_fields(fields))
    pill_type = str(fields.get("pill_type") or "foundation").strip() or "foundation"
    if pill_type in REMOVED_PILL_TYPES:
        raise ValueError("灵石收益类丹药已删除，请改用其他丹药类型。")
    if pill_type not in PILL_TYPE_LABELS:
        raise ValueError("不支持的丹药类型。")
    payload["pill_type"] = pill_type
    payload["effect_value"] = _coerce_int(fields.get("effect_value"), 0)
    payload["poison_delta"] = _coerce_int(fields.get("poison_delta"), 0)
    return payload


def _normalize_talisman_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_common_item_fields(fields)
    payload.update(_normalize_common_bonus_fields(fields))
    payload["duel_rate_bonus"] = _coerce_int(fields.get("duel_rate_bonus"), 0)
    payload["effect_uses"] = max(_coerce_int(fields.get("effect_uses"), 1), 1)
    payload["combat_config"] = _normalize_combat_config(fields.get("combat_config"))
    return payload


def _normalize_technique_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_common_item_fields(fields)
    payload.update(_normalize_common_bonus_fields(fields))
    payload["technique_type"] = str(fields.get("technique_type") or "balanced").strip() or "balanced"
    payload["duel_rate_bonus"] = _coerce_int(fields.get("duel_rate_bonus"), 0)
    payload["cultivation_bonus"] = _coerce_int(fields.get("cultivation_bonus"), 0)
    payload["breakthrough_bonus"] = _coerce_int(fields.get("breakthrough_bonus"), 0)
    payload["combat_config"] = _normalize_combat_config(fields.get("combat_config"))
    return payload



def _normalize_material_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "name": str(fields.get("name") or "").strip(),
        "quality_level": normalize_quality_level(fields.get("quality_level")),
        "image_url": str(fields.get("image_url") or "").strip(),
        "description": str(fields.get("description") or "").strip(),
        "can_plant": _coerce_bool(fields.get("can_plant"), False),
        "seed_price_stone": max(int(fields.get("seed_price_stone") or 0), 0),
        "growth_minutes": max(int(fields.get("growth_minutes") or 0), 0),
        "yield_min": max(int(fields.get("yield_min") or 0), 0),
        "yield_max": max(int(fields.get("yield_max") or 0), 0),
        "unlock_realm_stage": normalize_realm_stage(fields.get("unlock_realm_stage")) if fields.get("unlock_realm_stage") else None,
        "unlock_realm_layer": max(int(fields.get("unlock_realm_layer") or 1), 1),
        "enabled": _coerce_bool(fields.get("enabled"), True),
    }
    if not payload["can_plant"]:
        payload["seed_price_stone"] = 0
        payload["growth_minutes"] = 0
        payload["yield_min"] = 0
        payload["yield_max"] = 0
        payload["unlock_realm_stage"] = None
        payload["unlock_realm_layer"] = 1
    else:
        payload["growth_minutes"] = max(payload["growth_minutes"], 1)
        payload["yield_min"] = max(payload["yield_min"], 1)
        payload["yield_max"] = max(payload["yield_max"], payload["yield_min"])
    if not payload["name"]:
        raise ValueError("material name is required")
    return payload



def _normalize_encounter_template_fields(fields: dict[str, Any]) -> dict[str, Any]:
    payload = dict(fields)
    payload["name"] = str(payload.get("name") or "").strip()
    payload["description"] = str(payload.get("description") or "").strip() or None
    payload["image_url"] = str(payload.get("image_url") or "").strip() or None
    payload["button_text"] = str(payload.get("button_text") or "").strip() or "抢夺机缘"
    payload["success_text"] = str(payload.get("success_text") or "").strip() or None
    payload["broadcast_text"] = str(payload.get("broadcast_text") or "").strip() or None
    payload["weight"] = max(_coerce_int(payload.get("weight"), 1), 1)
    payload["active_seconds"] = max(_coerce_int(payload.get("active_seconds"), 90), 15)
    min_realm_stage = payload.get("min_realm_stage")
    payload["min_realm_stage"] = normalize_realm_stage(min_realm_stage) if min_realm_stage else None
    payload["min_realm_layer"] = max(_coerce_int(payload.get("min_realm_layer"), 1), 1)
    payload["min_combat_power"] = max(_coerce_int(payload.get("min_combat_power"), 0), 0)
    payload["reward_stone_min"] = max(_coerce_int(payload.get("reward_stone_min"), 0), 0)
    payload["reward_stone_max"] = max(_coerce_int(payload.get("reward_stone_max"), payload["reward_stone_min"]), payload["reward_stone_min"])
    payload["reward_cultivation_min"] = max(_coerce_int(payload.get("reward_cultivation_min"), 0), 0)
    payload["reward_cultivation_max"] = max(_coerce_int(payload.get("reward_cultivation_max"), payload["reward_cultivation_min"]), payload["reward_cultivation_min"])
    reward_item_kind = str(payload.get("reward_item_kind") or "").strip() or None
    if reward_item_kind and reward_item_kind not in {"artifact", "pill", "talisman", "material", "recipe", "technique"}:
        raise ValueError("奇遇奖励物类型不支持")
    payload["reward_item_kind"] = reward_item_kind
    payload["reward_item_ref_id"] = _coerce_int(payload.get("reward_item_ref_id"), 0) or None
    payload["reward_item_quantity_min"] = max(_coerce_int(payload.get("reward_item_quantity_min"), 1), 1)
    payload["reward_item_quantity_max"] = max(_coerce_int(payload.get("reward_item_quantity_max"), payload["reward_item_quantity_min"]), payload["reward_item_quantity_min"])
    # 历史版本的奇遇额外词条奖励已经退场，保留字段只做兼容，不再对外开放。
    payload["reward_willpower"] = 0
    payload["reward_charisma"] = 0
    payload["reward_karma"] = 0
    payload["enabled"] = _coerce_bool(payload.get("enabled"), True)
    if not payload["name"]:
        raise ValueError("奇遇名称不能为空")
    if payload["reward_item_kind"] and not payload["reward_item_ref_id"]:
        raise ValueError("奇遇奖励物已选择类型，但没有指定具体物品")
    return payload



def _normalize_boss_loot_list(raw: Any) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    if not isinstance(raw, (list, tuple)):
        return rows
    for item in raw:
        if not isinstance(item, dict):
            continue
        ref_id = max(_coerce_int(item.get("ref_id"), 0), 0)
        if ref_id <= 0:
            continue
        chance = min(max(_coerce_int(item.get("chance"), 0), 0), 100)
        quantity_min = max(_coerce_int(item.get("quantity_min"), 1), 1)
        quantity_max = max(_coerce_int(item.get("quantity_max"), quantity_min), quantity_min)
        rows.append(
            {
                "ref_id": ref_id,
                "chance": chance,
                "quantity_min": quantity_min,
                "quantity_max": quantity_max,
            }
        )
    return rows[:50]


def _normalize_boss_config_fields(fields: dict[str, Any]) -> dict[str, Any]:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("Boss名称不能为空")
    boss_type = str(fields.get("boss_type") or "personal").strip().lower()
    if boss_type not in {"personal", "world"}:
        boss_type = "personal"
    stone_min = max(_coerce_int(fields.get("stone_reward_min"), 0), 0)
    stone_max = max(_coerce_int(fields.get("stone_reward_max"), stone_min), stone_min)
    payload: dict[str, Any] = {
        "name": name,
        "boss_type": boss_type,
        "realm_stage": normalize_realm_stage(fields.get("realm_stage")),
        "description": str(fields.get("description") or "").strip() or None,
        "image_url": str(fields.get("image_url") or "").strip() or None,
        "hp": max(_coerce_int(fields.get("hp"), 500), 1),
        "attack_power": max(_coerce_int(fields.get("attack_power"), 30), 0),
        "defense_power": max(_coerce_int(fields.get("defense_power"), 15), 0),
        "body_movement": max(_coerce_int(fields.get("body_movement"), 10), 0),
        "divine_sense": max(_coerce_int(fields.get("divine_sense"), 10), 0),
        "fortune": max(_coerce_int(fields.get("fortune"), 10), 0),
        "qi_blood": max(_coerce_int(fields.get("qi_blood"), fields.get("hp") or 500), 1),
        "true_yuan": max(_coerce_int(fields.get("true_yuan"), 200), 0),
        "skill_name": str(fields.get("skill_name") or "").strip() or None,
        "skill_ratio_percent": min(max(_coerce_int(fields.get("skill_ratio_percent"), 30), 0), 500),
        "skill_hit_bonus": _coerce_int(fields.get("skill_hit_bonus"), 0),
        "passive_name": str(fields.get("passive_name") or "").strip() or None,
        "passive_effect_kind": str(fields.get("passive_effect_kind") or "").strip() or None,
        "passive_ratio_percent": min(max(_coerce_int(fields.get("passive_ratio_percent"), 0), 0), 500),
        "passive_chance": min(max(_coerce_int(fields.get("passive_chance"), 25), 0), 100),
        "stone_reward_min": stone_min,
        "stone_reward_max": stone_max,
        "cultivation_reward": max(_coerce_int(fields.get("cultivation_reward"), 0), 0),
        "daily_attempt_limit": max(_coerce_int(fields.get("daily_attempt_limit"), 3), 0),
        "ticket_cost_stone": max(_coerce_int(fields.get("ticket_cost_stone"), 100), 0),
        "flavor_text": str(fields.get("flavor_text") or "").strip() or None,
        "sort_order": _coerce_int(fields.get("sort_order"), 0),
        "enabled": _coerce_bool(fields.get("enabled"), True),
    }
    for field in _BOSS_LOOT_FIELDS:
        raw_loot = fields.get(field)
        if raw_loot is None:
            for alias in _BOSS_LOOT_FIELD_ALIASES.get(field, ()):
                if fields.get(alias) is not None:
                    raw_loot = fields.get(alias)
                    break
        payload[field] = _normalize_boss_loot_list(raw_loot)
    return payload


__all__ = [name for name in globals() if not name.startswith("__")]
