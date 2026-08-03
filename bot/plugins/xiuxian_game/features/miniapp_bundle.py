from __future__ import annotations

import copy
from typing import Any

from bot.func_helper.emby_currency import get_emby_balance, get_exchange_settings
from bot.sql_helper.sql_xiuxian import (
    DEFAULT_SETTINGS,
    SOCIAL_MODE_LABELS,
    list_achievements,
    list_auction_items,
    list_equipped_artifacts,
    list_recent_journals,
    list_recipes,
    list_scenes,
    list_scene_drops,
    list_shop_items,
    list_slave_profiles,
    list_techniques,
    list_user_artifacts,
    list_user_materials,
    list_user_pills,
    list_user_recipes,
    list_user_talismans,
    list_user_techniques,
    list_user_titles,
    normalize_artifact_slot,
    serialize_profile,
)
from bot.plugins.xiuxian_game.achievement_service import ACHIEVEMENT_METRIC_LABELS, build_user_achievement_overview
from bot.plugins.xiuxian_game.features.bundle_cache import load_cached_bootstrap_core_bundle
from bot.plugins.xiuxian_game.features.exploration import _scene_requirement_state
from bot.plugins.xiuxian_game.features.farm import build_farm_bundle
from bot.plugins.xiuxian_game.features.fishing import build_fishing_bundle
from bot.plugins.xiuxian_game.features.gambling import build_gambling_bundle
from bot.plugins.xiuxian_game.features.crafting import (
    build_recipe_catalog,
    build_recipe_fragment_synthesis_catalog,
)
from bot.plugins.xiuxian_game.features.growth import build_spirit_stone_commissions
from bot.plugins.xiuxian_game.features.shop import attach_official_recycle_quotes
from bot.plugins.xiuxian_game.features.runtime_facade import (
    _apply_profile_growth_floor,
    _artifact_set_index,
    _battle_bundle,
    _breakthrough_requirement,
    _build_user_technique_rows,
    _current_technique_payload,
    _decorate_artifact_with_set,
    _decorate_furnace_profile_for_owner,
    _gender_lock_reason,
    _get_active_exploration,
    _get_item_payload,
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
    _scene_exploration_counts,
    _self_profile_snapshot,
    _settle_retreat_progress,
    _user_task_daily_limit,
    _user_task_publish_count_today,
    active_talisman_effect_summary,
    build_marriage_overview,
    build_mentorship_overview,
    build_progress,
    build_user_artifact_rows,
    format_realm_requirement,
    format_root,
    get_active_duel_lock,
    get_current_sect_bundle,
    get_current_title,
    get_profile,
    get_talisman,
    get_xiuxian_settings,
    is_same_china_day,
    list_sects_for_user,
    list_tasks_for_user,
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


VALID_PROFILE_SECTIONS = {
    "inventory",
    "technique",
    "official_shop",
    "official_recycle",
    "market",
    "auction",
    "sect",
    "task",
    "craft",
    "explore",
    "journal",
    "gift",
    "title",
    "furnace",
    "mentorship",
    "commission",
    "farm",
    "marriage",
    "fishing",
    "gambling",
}

INVENTORY_SECTION_KEYS = ("artifacts", "pills", "talismans", "materials", "recipes", "techniques")


def build_full_profile_bundle(
    tg: int,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    bundle = serialize_full_profile(tg)
    from bot.plugins.xiuxian_game.features.world_bundle import build_world_bundle

    world_bundle = build_world_bundle(tg)
    bundle.update({key: value for key, value in world_bundle.items() if key != "settings"})
    attach_official_recycle_quotes(bundle)
    _apply_scene_requirement_state(bundle)
    _apply_capabilities(
        bundle,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    )
    bundle["gambling"] = build_gambling_bundle(tg, bundle=bundle)
    return bundle


def build_bootstrap_core_bundle(
    tg: int,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    bundle = _build_core_profile_bundle(tg)
    _apply_capabilities(
        bundle,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    )
    return bundle


def build_deferred_profile_sections(
    tg: int,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    bundle = copy.deepcopy(load_cached_bootstrap_core_bundle(
        tg,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    ))
    bundle["sects"] = list_sects_for_user(tg)
    bundle["tasks"] = list_tasks_for_user(tg)
    bundle["achievements"] = build_user_achievement_overview(tg)
    bundle["journal"] = list_recent_journals(tg)
    bundle["bundle_mode"] = "deferred"
    return bundle


def build_profile_section_bundle(
    tg: int,
    section: str,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    normalized = str(section or "").strip().replace("-", "_")
    if normalized not in VALID_PROFILE_SECTIONS:
        raise ValueError("未知的延迟加载模块")

    bundle = copy.deepcopy(load_cached_bootstrap_core_bundle(
        tg,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    ))
    if normalized in {"inventory", "gift", "official_recycle", "market", "auction", "task", "craft"}:
        _attach_inventory_section(bundle, tg)

    if normalized == "inventory" or normalized == "gift":
        attach_official_recycle_quotes(bundle)
    elif normalized == "technique":
        bundle["techniques"] = _build_technique_rows(bundle, tg)
        bundle["technique_owned_count"] = len(bundle["techniques"])
        bundle["technique_total_count"] = len(list_techniques(enabled_only=True))
    elif normalized == "official_shop":
        bundle.update(_build_official_shop_section())
    elif normalized == "official_recycle":
        bundle["techniques"] = _build_technique_rows(bundle, tg)
        bundle["recipes"] = list_user_recipes(tg, enabled_only=False)
        attach_official_recycle_quotes(bundle)
    elif normalized == "market":
        bundle.update(_build_market_section(tg))
    elif normalized == "auction":
        bundle.update(_build_auction_section(tg))
    elif normalized == "sect":
        bundle.update(_build_core_world_bundle(tg))
    elif normalized == "task":
        bundle.update(_build_task_section(tg))
    elif normalized == "craft":
        bundle.update(_build_craft_section(tg))
    elif normalized == "explore":
        bundle.update(_build_explore_section(tg, bundle))
    elif normalized == "journal":
        bundle["journal"] = list_recent_journals(tg)
    elif normalized == "title":
        bundle.update(_build_title_section(tg, bundle))
    elif normalized == "furnace":
        bundle.update(_build_furnace_section(tg, bundle))
    elif normalized == "mentorship":
        bundle["mentorship"] = build_mentorship_overview(tg, bundle=_self_profile_snapshot(bundle))
    elif normalized == "commission":
        bundle["commissions"] = build_spirit_stone_commissions(tg)
    elif normalized == "farm":
        bundle["farm"] = build_farm_bundle(tg)
    elif normalized == "marriage":
        marriage = build_marriage_overview(tg, bundle=_self_profile_snapshot(bundle))
        bundle["marriage"] = marriage
        bundle["capabilities"]["shared_inventory_enabled"] = bool(marriage.get("shared_assets_enabled"))
        bundle["capabilities"]["shared_inventory_note"] = str(marriage.get("shared_assets_hint") or "")
    elif normalized == "fishing":
        bundle["fishing"] = build_fishing_bundle(tg)
    elif normalized == "gambling":
        bundle["gambling"] = build_gambling_bundle(tg, bundle=bundle)
    bundle["bundle_section"] = normalized
    return bundle


def build_fishing_cast_bundle_patch(
    tg: int,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    bundle = _build_core_profile_bundle(tg)
    bundle["journal"] = list_recent_journals(tg)
    bundle["fishing"] = build_fishing_bundle(tg)
    bundle["bundle_section"] = "fishing"
    _apply_capabilities(
        bundle,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    )
    return bundle


def build_gambling_action_bundle_patch(
    tg: int,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    bundle = _build_core_profile_bundle(tg)
    bundle["gambling"] = build_gambling_bundle(tg, bundle=bundle)
    bundle["bundle_section"] = "gambling"
    _apply_capabilities(
        bundle,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    )
    return bundle


def build_craft_action_bundle_patch(
    tg: int,
    *,
    can_upload_images: bool = False,
    upload_image_reason: str = "",
    allow_non_admin_image_upload: bool = False,
    is_admin: bool = False,
    admin_panel_url: str | None = None,
) -> dict[str, Any]:
    bundle = _build_core_profile_bundle(tg)
    _attach_inventory_section(bundle, tg)
    bundle.update(_build_craft_section(tg))
    bundle["bundle_section"] = "craft"
    _apply_capabilities(
        bundle,
        can_upload_images=can_upload_images,
        upload_image_reason=upload_image_reason,
        allow_non_admin_image_upload=allow_non_admin_image_upload,
        is_admin=is_admin,
        admin_panel_url=admin_panel_url,
    )
    return bundle


def _build_core_profile_bundle(tg: int) -> dict[str, Any]:
    _prepare_profile_state(tg)
    profile_obj = _repair_profile_realm_state(tg)
    if profile_obj is None:
        profile_obj = get_profile(tg, create=True)
    profile = dict(serialize_profile(profile_obj) or {})
    if not profile:
        raise ValueError("未找到修仙档案。")
    raw_spiritual_stone = int(profile.get("spiritual_stone") or 0)
    shared_spiritual_stone = (
        raw_spiritual_stone if not profile.get("consented") else int(profile.get("spiritual_stone") or 0)
    )
    profile["personal_spiritual_stone"] = raw_spiritual_stone
    profile["spiritual_stone"] = shared_spiritual_stone
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
    progress = build_progress(
        profile["realm_stage"],
        int(profile.get("realm_layer") or 1),
        int(profile.get("cultivation") or 0),
    )
    retreating = bool(profile_obj and _is_retreating(profile_obj))
    xiuxian_settings = get_xiuxian_settings()
    equip_limit = max(int(xiuxian_settings.get("artifact_equip_limit", DEFAULT_SETTINGS["artifact_equip_limit"]) or 0), 1)
    equipped_artifacts = []
    artifact_set_map = _artifact_set_index()
    for row in list_equipped_artifacts(tg):
        artifact = dict(row.get("artifact") or {})
        if not artifact:
            continue
        artifact = _decorate_artifact_with_set(artifact, artifact_set_map)
        artifact["equipped"] = True
        artifact["slot"] = row.get("slot")
        equipped_artifacts.append(artifact)
    artifact_set_bundle = _resolve_active_artifact_sets(equipped_artifacts)
    active_talisman = serialize_talisman(get_talisman(profile_obj.active_talisman_id)) if profile_obj and profile_obj.active_talisman_id else None
    current_technique = _current_technique_payload(profile)
    current_title = get_current_title(tg)
    battle = _battle_bundle(
        {
            "profile": profile,
            "equipped_artifacts": equipped_artifacts,
            "active_talisman": active_talisman,
            "current_technique": current_technique,
            "current_title": current_title,
        }
    )
    effective_stats = {
        key: int(round(value)) if isinstance(value, (int, float)) else value
        for key, value in battle["stats"].items()
    }
    combat_power = int(round(battle["power"]))
    if current_title:
        profile["current_title_name"] = current_title.get("name")
        profile["display_name_with_title"] = _profile_name_with_title(profile, current_title)
    else:
        profile["current_title_name"] = None
    profile["is_dead"] = bool(profile.get("death_at"))
    profile["social_mode"] = profile_social_mode(profile)
    profile["social_mode_label"] = SOCIAL_MODE_LABELS.get(profile["social_mode"], "入世")
    profile["is_secluded"] = profile["social_mode"] == "secluded"
    rebirth_cooldown = _rebirth_cooldown_state(profile, xiuxian_settings)
    profile["rebirth_cooldown_enabled"] = rebirth_cooldown["enabled"]
    profile["rebirth_cooldown_hours"] = rebirth_cooldown["cooldown_hours"]
    profile["rebirth_cooldown_remaining_seconds"] = rebirth_cooldown["remaining_seconds"]
    profile["rebirth_available_at"] = rebirth_cooldown["available_at"]
    profile["rebirth_locked"] = rebirth_cooldown["blocked"]
    profile["rebirth_cooldown_reason"] = rebirth_cooldown["reason"]
    gender_lock_reason = _gender_lock_reason(profile_obj or profile)
    gender_locked = bool(gender_lock_reason)
    active_duel_lock = get_active_duel_lock(tg)
    breakthrough_requirement = _breakthrough_requirement(profile.get("realm_stage"))
    settings = {
        **get_exchange_settings(),
        "coin_stone_exchange_enabled": bool(
            xiuxian_settings.get("coin_stone_exchange_enabled", DEFAULT_SETTINGS.get("coin_stone_exchange_enabled", True))
        ),
        "artifact_equip_limit": equip_limit,
        "equipment_unbind_cost": int(xiuxian_settings.get("equipment_unbind_cost", DEFAULT_SETTINGS["equipment_unbind_cost"]) or 0),
        "official_shop_name": str(
            xiuxian_settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"])
            or DEFAULT_SETTINGS["official_shop_name"]
        ),
        "allow_user_task_publish": bool(
            xiuxian_settings.get("allow_user_task_publish", DEFAULT_SETTINGS["allow_user_task_publish"])
        ),
        "task_publish_cost": max(int(xiuxian_settings.get("task_publish_cost", DEFAULT_SETTINGS["task_publish_cost"]) or 0), 0),
        "user_task_daily_limit": _user_task_daily_limit(),
        "user_task_published_today": _user_task_publish_count_today(tg),
        "furnace_harvest_cultivation_percent": max(
            int(
                xiuxian_settings.get(
                    "furnace_harvest_cultivation_percent",
                    DEFAULT_SETTINGS["furnace_harvest_cultivation_percent"],
                )
                or 0
            ),
            0,
        ),
        "seclusion_cultivation_efficiency_percent": seclusion_cultivation_efficiency_percent(xiuxian_settings),
    }
    capabilities = {
        "can_train": profile["consented"] and not profile["is_dead"] and not gender_locked and not retreating and not is_same_china_day(profile_obj.last_train_at if profile_obj else None, utcnow_placeholder()),
        "train_reason": (
            gender_lock_reason
            if gender_locked
            else (
                "角色已死亡，只能重新踏出仙途"
                if profile["is_dead"]
                else ("" if not retreating and not is_same_china_day(profile_obj.last_train_at if profile_obj else None, utcnow_placeholder()) else ("闭关之中，心神内敛，无暇吐纳外气。" if retreating else "今日吐纳已毕，经脉已盈，再行运气恐伤道基。"))
            )
        ),
        "can_breakthrough": profile["consented"] and not profile["is_dead"] and not gender_locked and not retreating and int(profile.get("realm_layer") or 0) >= 9 and bool(progress["breakthrough_ready"]),
        "breakthrough_reason": (
            gender_lock_reason
            if gender_locked
            else (
                "角色已死亡，只能重新踏出仙途"
                if profile["is_dead"]
                else ("" if not retreating and int(profile.get("realm_layer") or 0) >= 9 and progress["breakthrough_ready"] else ("闭关之中，气机未满，尚难叩问破境之机。" if retreating else "只有达到当前境界九层且满修为后才能突破"))
            )
        ),
        "required_breakthrough_pill_name": (breakthrough_requirement or {}).get("pill_name"),
        "required_breakthrough_scene_name": (breakthrough_requirement or {}).get("scene_name"),
        "can_retreat": profile["consented"] and not profile["is_dead"] and not gender_locked and not retreating,
        "retreat_reason": gender_lock_reason if gender_locked else ("角色已死亡，只能重新踏出仙途" if profile["is_dead"] else ("" if not retreating else "你正在闭关中")),
        "is_in_retreat": retreating,
        "is_dead": profile["is_dead"],
        "death_reason": rebirth_cooldown["reason"] if rebirth_cooldown["blocked"] else ("角色已死亡，只能重新踏出仙途" if profile["is_dead"] else ""),
        "can_enter_path": not profile["consented"] and not rebirth_cooldown["blocked"],
        "enter_reason": rebirth_cooldown["reason"],
        "rebirth_locked": rebirth_cooldown["blocked"],
        "social_mode": profile["social_mode"],
        "social_mode_label": profile["social_mode_label"],
        "is_secluded": profile["is_secluded"],
        "can_toggle_social_mode": profile["consented"] and not profile["is_dead"] and not gender_locked,
        "social_mode_toggle_reason": gender_lock_reason if gender_locked else ("角色已死亡，只能重新踏出仙途" if profile["is_dead"] else ""),
        "social_interaction_lock_reason": (
            gender_lock_reason
            if gender_locked
            else (
                f"你当前处于避世状态，对外互动已关闭，修为收益按 {settings['seclusion_cultivation_efficiency_percent']}% 结算。"
                if profile["is_secluded"]
                else ""
            )
        ),
        "gender_required": gender_locked,
        "gender_lock_reason": gender_lock_reason,
        "shared_spiritual_stone_total": shared_spiritual_stone,
        "shared_inventory_enabled": False,
        "shared_inventory_note": "结为道侣后，灵石与背包会自动共享。" if not gender_locked else "",
        "artifact_equip_limit": equip_limit,
        "equipped_artifact_count": len(equipped_artifacts),
        "duel_locked": bool(active_duel_lock),
        "duel_lock": active_duel_lock,
        "duel_lock_reason": "" if not active_duel_lock else f"{active_duel_lock['duel_mode_label']}结算前，禁止灵石与交易操作",
    }

    bundle = {
        "profile": profile,
        "progress": progress,
        "capabilities": capabilities,
        "emby_balance": get_emby_balance(tg),
        "equipped_artifact": equipped_artifacts[0] if equipped_artifacts else None,
        "equipped_artifacts": equipped_artifacts,
        "active_talisman": active_talisman,
        "current_technique": current_technique,
        "current_title": current_title,
        "active_artifact_sets": artifact_set_bundle["sets"],
        "settings": settings,
        "effective_stats": effective_stats,
        "combat_power": combat_power,
        "attribute_effects": _build_attribute_effects(profile, effective_stats),
        "commissions": [],
        "mentorship": {},
        "marriage": {},
        "master_profile": None,
        "slave_profiles": [],
        "titles": [],
        "achievements": [],
        "achievement_metric_progress": {},
        "achievement_unlocked_count": 0,
        "achievement_total_count": 0,
        "technique_owned_count": 0,
        "technique_total_count": 0,
    }
    return bundle


def _inventory_context(bundle: dict[str, Any], tg: int) -> dict[str, Any]:
    profile = bundle.get("profile") or {}
    settings = bundle.get("settings") or {}
    retreating = bool(bundle.get("capabilities", {}).get("is_in_retreat"))
    equipped_rows = list_equipped_artifacts(tg)
    equipped_ids: set[int] = set()
    equipped_slot_names: set[str] = set()
    for row in equipped_rows:
        artifact = row.get("artifact") or {}
        if int(artifact.get("id") or 0) > 0:
            equipped_ids.add(int(artifact["id"]))
        slot = normalize_artifact_slot(artifact.get("equip_slot"))
        if slot:
            equipped_slot_names.add(slot)
    equip_limit = max(int(settings.get("artifact_equip_limit") or bundle.get("capabilities", {}).get("artifact_equip_limit") or 1), 1)
    return {
        "profile": profile,
        "retreating": retreating,
        "equipped_ids": equipped_ids,
        "equipped_slot_names": equipped_slot_names,
        "equip_limit": equip_limit,
    }


def _build_artifact_rows(bundle: dict[str, Any], tg: int) -> list[dict[str, Any]]:
    context = _inventory_context(bundle, tg)
    return build_user_artifact_rows(
        context["profile"],
        tg,
        bool(context["retreating"]),
        int(context["equip_limit"]),
        context["equipped_ids"],
        context["equipped_slot_names"],
    )


def _build_pill_rows(bundle: dict[str, Any], tg: int) -> list[dict[str, Any]]:
    profile = bundle.get("profile") or {}
    rows = []
    for row in list_user_pills(tg):
        item = row.get("pill") or {}
        item["resolved_effects"] = resolve_pill_effects(profile, item)
        reason = _pill_usage_reason(profile, item)
        row["pill"]["usable"] = not reason
        row["pill"]["unusable_reason"] = reason
        batch_usable = _pill_supports_batch_use(item)
        row["pill"]["batch_usable"] = batch_usable
        row["pill"]["batch_use_max"] = _pill_batch_use_max(profile, item, row.get("quantity"))
        row["pill"]["batch_use_note"] = _pill_batch_use_note(item)
        rows.append(row)
    return rows


def _build_talisman_rows(bundle: dict[str, Any], tg: int) -> list[dict[str, Any]]:
    profile = bundle.get("profile") or {}
    retreating = bool(bundle.get("capabilities", {}).get("is_in_retreat"))
    rows = []
    for row in list_user_talismans(tg):
        total_quantity = max(int(row.get("quantity") or 0), 0)
        bound_quantity = max(min(int(row.get("bound_quantity") or 0), total_quantity), 0)
        item = row.get("talisman") or {}
        item["resolved_effects"] = resolve_talisman_effects(profile, item)
        item["active_effects"] = resolve_talisman_active_effects(profile, item)
        item["active_effect_summary"] = active_talisman_effect_summary(item["active_effects"])
        usable = realm_requirement_met(profile, item.get("min_realm_stage"), item.get("min_realm_layer"))
        reason = "" if usable else f"需要达到 {format_realm_requirement(item.get('min_realm_stage'), item.get('min_realm_layer'))}"
        row["bound_quantity"] = bound_quantity
        row["unbound_quantity"] = max(total_quantity - bound_quantity, 0)
        row["consumable_quantity"] = row["unbound_quantity"]
        row["tradeable_quantity"] = row["unbound_quantity"]
        item["usable"] = usable and not retreating
        item["active"] = profile.get("active_talisman_id") == item.get("id")
        item["unusable_reason"] = "闭关之中，法力内收，不宜引动符箓外力。" if usable and not item["active"] and retreating else reason
        item["bound"] = bound_quantity > 0
        item["bound_quantity"] = bound_quantity
        rows.append(row)
    return rows


def _build_technique_rows(bundle: dict[str, Any], tg: int) -> list[dict[str, Any]]:
    return _build_user_technique_rows(bundle.get("profile") or {}, tg)


def _attach_inventory_section(bundle: dict[str, Any], tg: int) -> None:
    bundle["artifacts"] = _build_artifact_rows(bundle, tg)
    bundle["pills"] = _build_pill_rows(bundle, tg)
    bundle["talismans"] = _build_talisman_rows(bundle, tg)
    bundle["materials"] = list_user_materials(tg)
    bundle["recipes"] = list_user_recipes(tg, enabled_only=False)
    bundle["techniques"] = _build_technique_rows(bundle, tg)
    bundle["technique_owned_count"] = len(bundle["techniques"])
    bundle["technique_total_count"] = len(list_techniques(enabled_only=True))
    bundle["recipe_discovered_count"] = len(bundle["recipes"])


def _build_official_shop_section() -> dict[str, Any]:
    settings = get_xiuxian_settings()
    return {
        "official_shop": list_shop_items(official_only=True),
        "settings": {
            "official_shop_name": str(
                settings.get("official_shop_name", DEFAULT_SETTINGS["official_shop_name"])
                or DEFAULT_SETTINGS["official_shop_name"]
            ),
        },
    }


def _build_market_section(tg: int) -> dict[str, Any]:
    all_personal_shop = list_shop_items(official_only=False)
    return {
        "personal_shop": [item for item in all_personal_shop if int(item.get("owner_tg") or 0) == int(tg)],
        "community_shop": [item for item in all_personal_shop if int(item.get("owner_tg") or 0) not in {0, int(tg)}],
    }


def _build_auction_section(tg: int) -> dict[str, Any]:
    all_active_auctions = list_auction_items(status="active")
    settings = get_xiuxian_settings()
    return {
        "community_auctions": [item for item in all_active_auctions if int(item.get("owner_tg") or 0) != int(tg)],
        "personal_auctions": list_auction_items(owner_tg=tg, include_inactive=True, limit=20),
        "settings": {
            "auction_fee_percent": max(int(settings.get("auction_fee_percent", DEFAULT_SETTINGS["auction_fee_percent"]) or 0), 0),
            "auction_duration_minutes": max(int(settings.get("auction_duration_minutes", DEFAULT_SETTINGS["auction_duration_minutes"]) or 0), 1),
        },
    }


def _build_task_section(tg: int) -> dict[str, Any]:
    settings = get_xiuxian_settings()
    return {
        "tasks": list_tasks_for_user(tg),
        "achievement_metric_presets": [
            {"key": key, "label": label}
            for key, label in sorted(ACHIEVEMENT_METRIC_LABELS.items(), key=lambda item: item[1])
        ],
        "settings": {
            "allow_user_task_publish": bool(settings.get("allow_user_task_publish", DEFAULT_SETTINGS["allow_user_task_publish"])),
            "task_publish_cost": max(int(settings.get("task_publish_cost", DEFAULT_SETTINGS["task_publish_cost"]) or 0), 0),
            "user_task_daily_limit": _user_task_daily_limit(),
            "user_task_published_today": _user_task_publish_count_today(tg),
        },
    }


def _build_craft_section(tg: int) -> dict[str, Any]:
    recipes = build_recipe_catalog(tg)
    return {
        "recipes": recipes,
        "recipe_discovered_count": len(recipes),
        "recipe_total_count": len(list_recipes(enabled_only=True)),
        "recipe_fragment_syntheses": build_recipe_fragment_synthesis_catalog(tg),
    }


def _build_explore_section(tg: int, bundle: dict[str, Any]) -> dict[str, Any]:
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
    result = {
        "scenes": scenes,
        "active_exploration": _get_active_exploration(tg),
    }
    merged = {**bundle, **result}
    _apply_scene_requirement_state(merged)
    result["scenes"] = merged.get("scenes") or scenes
    return result


def _build_title_section(tg: int, bundle: dict[str, Any]) -> dict[str, Any]:
    profile = bundle.get("profile") or {}
    current_title_id = int(profile.get("current_title_id") or 0)
    titles = []
    for row in list_user_titles(tg):
        title = row.get("title") or {}
        title["resolved_effects"] = resolve_title_effects(profile, title)
        title["equipped"] = int(title.get("id") or 0) == current_title_id
        title["action_label"] = "卸下称号" if title["equipped"] else "佩戴称号"
        row["title"] = title
        titles.append(row)
    achievement_overview = build_user_achievement_overview(tg)
    return {
        "titles": titles,
        "achievements": achievement_overview.get("achievements") or [],
        "achievement_metric_progress": achievement_overview.get("metric_progress") or {},
        "achievement_unlocked_count": int(achievement_overview.get("unlocked_count") or 0),
        "achievement_total_count": int(achievement_overview.get("total_count") or len(list_achievements(enabled_only=True)) or 0),
    }


def _build_furnace_section(tg: int, bundle: dict[str, Any]) -> dict[str, Any]:
    profile = bundle.get("profile") or {}
    profile_obj = get_profile(tg, create=False)
    master_profile = serialize_profile(get_profile(int(profile.get("master_tg") or 0), create=False)) if profile.get("master_tg") else None
    slave_profiles = [_decorate_furnace_profile_for_owner(profile, row) for row in list_slave_profiles(tg)]
    profile["master_name"] = (master_profile or {}).get("display_label")
    profile["slave_names"] = [item.get("display_label") or f"TG {item.get('tg')}" for item in slave_profiles]
    profile["furnace_harvested_today"] = is_same_china_day(profile_obj.furnace_harvested_at if profile_obj else None, utcnow_placeholder())
    return {
        "profile": profile,
        "master_profile": master_profile,
        "slave_profiles": slave_profiles,
    }


def _prepare_profile_state(tg: int) -> None:
    profile = _repair_profile_realm_state(tg)
    if profile is None:
        profile = get_profile(tg, create=True)
    if profile and profile.consented:
        _settle_retreat_progress(tg)
        _apply_profile_growth_floor(tg)


def _build_core_world_bundle(tg: int) -> dict[str, Any]:
    settings = get_xiuxian_settings()
    return {
        "sects": list_sects_for_user(tg),
        "current_sect": get_current_sect_bundle(tg),
        "settings": {
            "allow_user_task_publish": bool(settings.get("allow_user_task_publish", DEFAULT_SETTINGS["allow_user_task_publish"])),
            "task_publish_cost": max(int(settings.get("task_publish_cost", DEFAULT_SETTINGS["task_publish_cost"]) or 0), 0),
            "user_task_daily_limit": _user_task_daily_limit(),
            "user_task_published_today": _user_task_publish_count_today(tg),
        },
    }


def _build_attribute_effects(profile: dict[str, Any], effective_stats: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    labels = (
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
    for key, label in labels:
        rows.append(
            {
                "key": key,
                "label": label,
                "value": int(profile.get(key) or 0),
                "effective_value": int(effective_stats.get(key) or 0),
                "effect": "",
            }
        )
    return rows


def utcnow_placeholder():
    return utcnow()


def _apply_scene_requirement_state(bundle: dict[str, Any]) -> None:
    profile = bundle.get("profile") or {}
    combat_power = int(bundle.get("combat_power") or 0)
    for scene in bundle.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scene["requirement_state"] = _scene_requirement_state(profile, scene, combat_power)


def _apply_capabilities(
    bundle: dict[str, Any],
    *,
    can_upload_images: bool,
    upload_image_reason: str,
    allow_non_admin_image_upload: bool,
    is_admin: bool,
    admin_panel_url: str | None,
) -> None:
    bundle.setdefault("capabilities", {})
    bundle["capabilities"]["can_upload_images"] = can_upload_images
    bundle["capabilities"]["upload_image_reason"] = upload_image_reason
    bundle["capabilities"]["is_admin"] = is_admin
    bundle["capabilities"]["admin_panel_url"] = admin_panel_url if is_admin else None
    bundle.setdefault("settings", {})
    bundle["settings"]["allow_non_admin_image_upload"] = bool(allow_non_admin_image_upload)
