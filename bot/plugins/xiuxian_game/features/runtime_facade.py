"""Legacy runtime facade for xiuxian profile/world composition.

This module centralizes the compatibility surface that still relies on
`service.py` / `world_service.py`. New feature code should depend on this
facade (or dedicated feature modules), not import legacy service modules
directly.
"""

from __future__ import annotations

from bot.plugins.xiuxian_game.service import (
    _apply_profile_growth_floor,
    _artifact_set_index,
    _battle_bundle,
    _breakthrough_requirement,
    _build_user_technique_rows,
    _current_technique_payload,
    _decorate_artifact_with_set,
    _decorate_furnace_profile_for_owner,
    _gender_lock_reason,
    _is_retreating,
    _normalized_root_quality,
    _pill_batch_use_max,
    _pill_batch_use_note,
    _pill_supports_batch_use,
    _pill_usage_reason,
    _profile_name_with_title,
    _rebirth_cooldown_state,
    _repair_profile_realm_state,
    _resolve_active_artifact_sets,
    _root_quality_payload,
    _self_profile_snapshot,
    _settle_retreat_progress,
    active_talisman_effect_summary,
    build_marriage_overview,
    build_mentorship_overview,
    build_progress,
    build_user_artifact_rows,
    format_realm_requirement,
    format_root,
    get_active_duel_lock,
    get_current_title,
    get_profile,
    get_talisman,
    get_xiuxian_settings,
    is_same_china_day,
    list_user_techniques,
    profile_social_mode,
    realm_requirement_met,
    resolve_pill_effects,
    resolve_talisman_active_effects,
    resolve_talisman_effects,
    resolve_title_effects,
    seclusion_cultivation_efficiency_percent,
    serialize_full_profile,
    serialize_talisman,
    utcnow,
)
from bot.plugins.xiuxian_game.world_service import (
    _get_active_exploration,
    _get_item_payload,
    _scene_exploration_counts,
    _user_task_daily_limit,
    _user_task_publish_count_today,
    get_current_sect_bundle,
    list_sects_for_user,
    list_tasks_for_user,
)

__all__ = [name for name in globals() if not name.startswith("__")]
