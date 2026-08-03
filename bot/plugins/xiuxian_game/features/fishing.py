from __future__ import annotations

import random
from math import exp
from typing import Any

from bot.plugins.xiuxian_game.cache import CATALOG_TTL, load_multi_versioned_json
from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    ITEM_KIND_LABELS,
    QUALITY_LEVEL_COLORS,
    QUALITY_LEVEL_LABELS,
    XiuxianProfile,
    apply_spiritual_stone_delta,
    assert_profile_alive,
    create_journal,
    get_shared_spiritual_stone_total,
    get_profile,
    get_talisman,
    grant_artifact_to_user,
    grant_material_to_user,
    grant_pill_to_user,
    grant_recipe_to_user,
    grant_talisman_to_user,
    grant_technique_to_user,
    list_artifacts,
    list_materials,
    list_pills,
    list_recipes,
    list_talismans,
    list_techniques,
    realm_index,
    serialize_talisman,
)


FISHING_SPOTS: dict[str, dict[str, Any]] = {
    "brook": {
        "key": "brook",
        "name": "青溪灵涧",
        "description": "溪流平缓，最适合试竿，常有基础灵材、低阶丹药顺水而来。",
        "cast_cost_stone": 18,
        "min_realm_stage": None,
        "min_realm_layer": 1,
        "quality_min": 1,
        "quality_max": 3,
        "tier_weights": {1: 580, 2: 260, 3: 80},
        "kind_weights": {"material": 1.0, "pill": 0.32, "talisman": 0.12, "recipe": 0.03, "technique": 0.02},
        "fortune_scale": 0.35,
    },
    "moon_lake": {
        "key": "moon_lake",
        "name": "寒月灵湖",
        "description": "月华长期沉在湖底，容易勾出带寒性的灵草、丹药与符箓。",
        "cast_cost_stone": 36,
        "min_realm_stage": "筑基",
        "min_realm_layer": 2,
        "quality_min": 1,
        "quality_max": 4,
        "tier_weights": {1: 380, 2: 280, 3: 130, 4: 38},
        "kind_weights": {"material": 0.82, "pill": 0.48, "talisman": 0.24, "recipe": 0.06, "technique": 0.04},
        "fortune_scale": 0.48,
    },
    "lava_pool": {
        "key": "lava_pool",
        "name": "火鳞熔潭",
        "description": "潭口热浪翻卷，偶尔会把高热药材、战斗丹与法宝胚胎卷上岸。",
        "cast_cost_stone": 68,
        "min_realm_stage": "筑基",
        "min_realm_layer": 3,
        "quality_min": 2,
        "quality_max": 5,
        "tier_weights": {2: 340, 3: 210, 4: 80, 5: 22},
        "kind_weights": {"material": 0.68, "pill": 0.58, "talisman": 0.20, "artifact": 0.16, "recipe": 0.08, "technique": 0.06},
        "fortune_scale": 0.62,
    },
    "star_sea": {
        "key": "star_sea",
        "name": "星渊古海",
        "description": "海眼与星潮相连，重宝虽少却并非绝迹，最吃机缘。",
        "cast_cost_stone": 128,
        "min_realm_stage": "金丹",
        "min_realm_layer": 2,
        "quality_min": 3,
        "quality_max": 7,
        "tier_weights": {3: 260, 4: 180, 5: 80, 6: 22, 7: 5},
        "kind_weights": {"material": 0.52, "pill": 0.48, "talisman": 0.28, "artifact": 0.22, "recipe": 0.12, "technique": 0.10},
        "fortune_scale": 0.82,
    },
}

PREVIEW_REWARD_LIMIT = 8
FISHING_REWARD_POOL_VERSION_GROUPS = (
    ("settings",),
    ("catalog", "materials"),
    ("catalog", "pills"),
    ("catalog", "talismans"),
    ("catalog", "artifacts"),
    ("catalog", "recipes"),
    ("catalog", "techniques"),
)


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def _active_talisman_for_profile(profile_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile_payload:
        return None
    active_talisman_id = int((profile_payload or {}).get("active_talisman_id") or 0)
    if active_talisman_id <= 0:
        return None
    return serialize_talisman(get_talisman(active_talisman_id))


def _shared_reward_pool(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    service = _legacy_service()
    current_settings = settings or service.get_xiuxian_settings()
    return service._configured_gambling_pool(current_settings)


def _weighted_choice(rows: list[dict[str, Any]], weight_key: str = "weight") -> dict[str, Any] | None:
    if not rows:
        return None
    weighted_rows = [(item, max(float(item.get(weight_key) or 0.0), 0.0)) for item in rows]
    total = sum(weight for _, weight in weighted_rows)
    if total <= 0:
        return None
    cursor = random.random() * total
    passed = 0.0
    for item, weight in weighted_rows:
        if weight <= 0:
            continue
        passed += weight
        if cursor <= passed:
            return item
    return weighted_rows[-1][0]


def _grant_item_by_kind(tg: int, kind: str, ref_id: int, quantity: int) -> dict[str, Any] | None:
    if kind == "artifact":
        return grant_artifact_to_user(tg, ref_id, quantity)
    if kind == "pill":
        return grant_pill_to_user(tg, ref_id, quantity)
    if kind == "talisman":
        return grant_talisman_to_user(tg, ref_id, quantity)
    if kind == "material":
        return grant_material_to_user(tg, ref_id, quantity)
    if kind == "recipe":
        return grant_recipe_to_user(tg, ref_id, source="fishing", obtained_note="垂钓所得")
    if kind == "technique":
        return grant_technique_to_user(
            tg,
            ref_id,
            source="fishing",
            obtained_note="垂钓所得",
            auto_equip_if_empty=True,
        )
    raise ValueError("不支持的钓获物类型")


def _quality_meta(level: int) -> dict[str, Any]:
    normalized = max(min(int(level or 1), 7), 1)
    return {
        "level": normalized,
        "label": QUALITY_LEVEL_LABELS.get(normalized, "凡品"),
        "color": QUALITY_LEVEL_COLORS.get(normalized, "#9ca3af"),
    }


def _meets_realm_requirement(profile: XiuxianProfile | dict[str, Any] | None, stage: str | None, layer: int = 1) -> bool:
    if not stage:
        return True
    if profile is None:
        return False
    current_stage = getattr(profile, "realm_stage", None) if not isinstance(profile, dict) else profile.get("realm_stage")
    current_layer = getattr(profile, "realm_layer", None) if not isinstance(profile, dict) else profile.get("realm_layer")
    current_index = realm_index(current_stage)
    target_index = realm_index(stage)
    if current_index != target_index:
        return current_index > target_index
    return max(int(current_layer or 1), 1) >= max(int(layer or 1), 1)


def _spot_requirement_text(spot: dict[str, Any]) -> str:
    stage = str(spot.get("min_realm_stage") or "").strip()
    layer = max(int(spot.get("min_realm_layer") or 1), 1)
    return f"{stage}{layer}层" if stage else "入道后即可"


def _catch_quantity_range(kind: str, quality_level: int) -> tuple[int, int]:
    quality = max(int(quality_level or 1), 1)
    if kind == "material":
        if quality <= 1:
            return 2, 4
        if quality == 2:
            return 1, 3
        if quality <= 4:
            return 1, 2
        return 1, 1
    if kind == "pill" and quality <= 2:
        return 1, 2
    return 1, 1


def _item_quality_level(kind: str, item: dict[str, Any] | None) -> int:
    if not item:
        return 1
    if kind == "material":
        return max(int(item.get("quality_level") or 1), 1)
    if kind == "recipe":
        result_kind = str(item.get("result_kind") or "").strip()
        result_ref_id = int(item.get("result_ref_id") or 0)
        service = _legacy_service()
        return _item_quality_level(result_kind, service._get_item_payload(result_kind, result_ref_id))
    return max(int(item.get("rarity_level") or item.get("quality_level") or 1), 1)


def _build_item_lookups() -> dict[str, dict[int, dict[str, Any]]]:
    materials = {int(item["id"]): item for item in list_materials(enabled_only=True) if int(item.get("id") or 0) > 0}
    pills = {int(item["id"]): item for item in list_pills(enabled_only=True) if int(item.get("id") or 0) > 0}
    talismans = {int(item["id"]): item for item in list_talismans(enabled_only=True) if int(item.get("id") or 0) > 0}
    artifacts = {int(item["id"]): item for item in list_artifacts(enabled_only=True) if int(item.get("id") or 0) > 0}
    recipes = {int(item["id"]): item for item in list_recipes(enabled_only=True) if int(item.get("id") or 0) > 0}
    techniques = {int(item["id"]): item for item in list_techniques(enabled_only=True) if int(item.get("id") or 0) > 0}
    return {
        "material": materials,
        "pill": pills,
        "talisman": talismans,
        "artifact": artifacts,
        "recipe": recipes,
        "technique": techniques,
    }


def _build_fishing_candidates(
    item_lookups: dict[str, dict[int, dict[str, Any]]],
    *,
    owned_recipe_ids: set[int] | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _ = owned_recipe_ids
    for entry in _shared_reward_pool(settings):
        if not bool(entry.get("fishing_enabled", entry.get("enabled", True))):
            continue
        kind = str(entry.get("item_kind") or "").strip()
        ref_id = int(entry.get("item_ref_id") or 0)
        if kind not in {"material", "pill", "talisman", "artifact", "recipe", "technique"} or ref_id <= 0:
            continue
        item = (item_lookups.get(kind) or {}).get(ref_id)
        if not item:
            continue
        if kind == "pill" and str(item.get("pill_type") or "").strip() == "foundation":
            continue
        quality_level = _item_quality_level(kind, item)
        quality = _quality_meta(quality_level)
        rows.append(
            {
                "kind": kind,
                "kind_label": ITEM_KIND_LABELS.get(kind, kind),
                "ref_id": ref_id,
                "name": str(item.get("name") or "").strip(),
                "item": item,
                "quality_level": quality_level,
                "quality_label": quality["label"],
                "quality_color": quality["color"],
                "quantity_min": max(int(entry.get("quantity_min") or 1), 1),
                "quantity_max": max(int(entry.get("quantity_max") or entry.get("quantity_min") or 1), max(int(entry.get("quantity_min") or 1), 1)),
                "fishing_weight": max(float(entry.get("fishing_weight", entry.get("base_weight") or 0.0) or 0.0), 0.0),
            }
        )
    return [row for row in rows if row.get("ref_id") and row.get("name") and float(row.get("fishing_weight") or 0.0) > 0]


def _base_fishing_candidates(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current_settings = settings or _legacy_service().get_xiuxian_settings()
    return load_multi_versioned_json(
        version_part_groups=FISHING_REWARD_POOL_VERSION_GROUPS,
        cache_parts=("fishing", "reward-pool"),
        ttl=CATALOG_TTL,
        loader=lambda: _build_fishing_candidates(_build_item_lookups(), settings=current_settings),
    )


def _spot_candidates(spot: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_kinds = set((spot.get("kind_weights") or {}).keys())
    quality_min = max(int(spot.get("quality_min") or 1), 1)
    quality_max = max(int(spot.get("quality_max") or quality_min), quality_min)
    return [
        row
        for row in candidates
        if row.get("kind") in allowed_kinds
        and quality_min <= int(row.get("quality_level") or 0) <= quality_max
    ]


def _tier_weights_for_spot(spot: dict[str, Any], fortune: int, tiers: set[int], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not tiers:
        return []
    service = _legacy_service()
    current_settings = settings or service.get_xiuxian_settings()
    quality_rules = service._normalize_fishing_quality_weight_rules(current_settings.get("fishing_quality_weight_rules"))
    available_tiers = sorted(tiers)
    median_tier = available_tiers[len(available_tiers) // 2]
    fortune_gap = float(int(fortune or 0) - 12)
    if fortune_gap >= 0:
        luck_delta = 0.92 * (1.0 - exp(-fortune_gap / 34.0))
    else:
        luck_delta = -0.24 * (1.0 - exp(fortune_gap / 18.0))
    fortune_scale = max(float(spot.get("fortune_scale") or 0), 0.0)
    rows: list[dict[str, Any]] = []
    for tier in available_tiers:
        base_weight = int((spot.get("tier_weights") or {}).get(tier) or 0)
        if base_weight <= 0:
            continue
        shift = int(tier) - int(median_tier)
        raw_multiplier = 1.0 + shift * luck_delta * fortune_scale
        multiplier = 0.26 + 1.72 / (1.0 + exp(-(raw_multiplier - 1.0) * 1.35))
        quality_multiplier = max(
            float((quality_rules.get(_quality_meta(tier)["label"]) or {}).get("weight_multiplier", 1.0) or 0.0),
            0.0,
        )
        total_weight = base_weight * multiplier * quality_multiplier
        if total_weight <= 0:
            continue
        rows.append({"quality_level": tier, "weight": total_weight})
    return rows


def _fishing_empty_chance(spot: dict[str, Any], fortune: int) -> float:
    quality_max = max(int(spot.get("quality_max") or 1), 1)
    fortune_gap = max(int(fortune or 0) - 12, 0)
    base = 0.18 + max(quality_max - 1, 0) * 0.035
    reduction = 0.17 * (1.0 - exp(-fortune_gap / 90.0))
    return max(min(base - reduction, 0.42), 0.08)


def _apply_fishing_empty_reduce(empty_chance: float, effects: dict[str, Any] | None) -> float:
    empty_reduce = max(float((effects or {}).get("fishing_empty_reduce") or 0), 0.0)
    if empty_reduce <= 0:
        return empty_chance
    return max(empty_chance * (1 - min(empty_reduce, 85.0) / 100.0), 0.02)


def _kind_weights_for_tier(spot: dict[str, Any], tier_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available_kinds = {str(row.get("kind") or "") for row in tier_rows if str(row.get("kind") or "")}
    weights = []
    for kind, base_weight in (spot.get("kind_weights") or {}).items():
        if kind not in available_kinds:
            continue
        weights.append(
            {
                "kind": kind,
                "weight": max(int(round(float(base_weight or 0) * 100)), 1),
            }
        )
    return weights


def _preview_rewards(candidates: list[dict[str, Any]], limit: int = PREVIEW_REWARD_LIMIT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    preferred: list[dict[str, Any]] = []
    for kind in ("artifact", "technique", "recipe", "talisman", "pill", "material"):
        kind_rows = [row for row in candidates if row.get("kind") == kind]
        kind_rows.sort(key=lambda item: (-int(item.get("quality_level") or 0), str(item.get("name") or "")))
        if kind_rows:
            preferred.append(kind_rows[0])
    sorted_rows = sorted(
        candidates,
        key=lambda item: (-int(item.get("quality_level") or 0), str(item.get("kind") or ""), str(item.get("name") or "")),
    )
    for source in preferred + sorted_rows:
        name = str(source.get("name") or "").strip()
        if not name or name in seen_names:
            continue
        rows.append(
            {
                "name": name,
                "kind": source.get("kind"),
                "kind_label": source.get("kind_label"),
                "quality_level": int(source.get("quality_level") or 1),
                "quality_label": source.get("quality_label"),
                "quality_color": source.get("quality_color"),
            }
        )
        seen_names.add(name)
        if len(rows) >= limit:
            break
    return rows


def _build_spot_bundle(
    spot: dict[str, Any],
    profile: XiuxianProfile,
    candidates: list[dict[str, Any]],
    *,
    current_fortune: int,
    profile_stone: int,
    talisman_active_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    available = _meets_realm_requirement(profile, spot.get("min_realm_stage"), int(spot.get("min_realm_layer") or 1))
    stone_cost = max(int(spot.get("cast_cost_stone") or 0), 0)
    if available and profile_stone < stone_cost:
        available = False
        available_reason = f"抛竿至少需要 {stone_cost} 灵石"
    elif available:
        available_reason = ""
    else:
        available_reason = f"需达到 {_spot_requirement_text(spot)}"

    tier_weights = _tier_weights_for_spot(spot, current_fortune, {int(row.get("quality_level") or 0) for row in candidates})
    total_weight = sum(max(float(row.get("weight") or 0.0), 0.0) for row in tier_weights)
    odds_preview = [
        {
            **_quality_meta(int(row.get("quality_level") or 1)),
            "chance_percent": round(max(float(row.get("weight") or 0.0), 0.0) * 100 / max(total_weight, 1.0), 1),
        }
        for row in tier_weights
    ]
    quality_min = max(int(spot.get("quality_min") or 1), 1)
    quality_max = max(int(spot.get("quality_max") or quality_min), quality_min)
    empty_chance = _apply_fishing_empty_reduce(
        _fishing_empty_chance(spot, current_fortune),
        talisman_active_effects,
    )
    return {
        "key": spot["key"],
        "name": spot["name"],
        "description": spot["description"],
        "cast_cost_stone": stone_cost,
        "min_realm_stage": spot.get("min_realm_stage"),
        "min_realm_layer": int(spot.get("min_realm_layer") or 1),
        "requirement_text": _spot_requirement_text(spot),
        "quality_band_label": f"{QUALITY_LEVEL_LABELS.get(quality_min, '凡品')} - {QUALITY_LEVEL_LABELS.get(quality_max, '凡品')}",
        "kind_labels": [ITEM_KIND_LABELS.get(kind, kind) for kind in (spot.get("kind_weights") or {}).keys()],
        "available": bool(available and candidates),
        "available_reason": available_reason if candidates else "当前没有可从该钓场钓出的物品",
        "candidate_count": len(candidates),
        "empty_chance_percent": round(empty_chance * 100.0, 1),
        "reward_preview": _preview_rewards(candidates),
        "odds_preview": odds_preview,
    }


def build_fishing_bundle(tg: int) -> dict[str, Any]:
    _legacy_service().ensure_seed_data()
    profile = get_profile(tg, create=False)
    if profile is None or not profile.consented:
        return {
            "spots": [],
            "current_fortune": 0,
            "available_spot_count": 0,
            "note": "踏入仙途后才能开始垂钓。",
        }
    current_fortune = max(int(profile.fortune or 0), 0)
    profile_payload = _legacy_service().serialize_profile(profile)
    battle_bundle = _legacy_service()._battle_bundle(profile_payload) if profile_payload else {}
    active_talisman = _active_talisman_for_profile(profile_payload)
    talisman_active_effects = battle_bundle.get("talisman_active_effects") or {}
    effective_stats = battle_bundle.get("stats") or {}
    effective_fortune = max(int(effective_stats.get("fortune") or current_fortune), 0)
    if active_talisman:
        effective_fortune += max(int(round(float(talisman_active_effects.get("fishing_luck_bonus") or 0))), 0)
    profile_stone = max(int(get_shared_spiritual_stone_total(int(profile.tg or 0)) or 0), 0)
    base_candidates = _base_fishing_candidates()
    spots = [
        _build_spot_bundle(
            spot,
            profile,
            _spot_candidates(spot, base_candidates),
            current_fortune=effective_fortune,
            profile_stone=profile_stone,
            talisman_active_effects=talisman_active_effects,
        )
        for spot in FISHING_SPOTS.values()
    ]
    return {
        "spots": spots,
        "current_fortune": current_fortune,
        "effective_fortune": effective_fortune,
        "available_spot_count": sum(1 for spot in spots if spot.get("available")),
        "note": "垂钓与仙界奇石共用同一套奖励池，但会额外压低高品阶权重，并且存在空竿；共享奖池会自动排除破境丹、破境丹丹方、唯一法宝与仙界奇石本体。",
    }


def cast_fishing_line_for_user(tg: int, spot_key: str) -> dict[str, Any]:
    _legacy_service().ensure_seed_data()
    settings = _legacy_service().get_xiuxian_settings()
    spot = FISHING_SPOTS.get(str(spot_key or "").strip())
    if not spot:
        raise ValueError("钓场不存在")

    # Daily fishing limit
    from bot.plugins.xiuxian_game.world_service import _ensure_daily_limit
    from bot.sql_helper.sql_xiuxian import get_profile as _get_profile

    profile_obj = _get_profile(tg, create=False)
    if profile_obj is not None:
        _ensure_daily_limit(profile_obj, "fish_daily_count", "fish_day_key", "fishing_daily_limit", "垂钓")

    profile_payload = _legacy_service().serialize_profile(profile_obj) if profile_obj is not None else {}
    battle_bundle = _legacy_service()._battle_bundle(profile_payload) if profile_payload else {}
    active_talisman = _active_talisman_for_profile(profile_payload)
    talisman_active_effects = battle_bundle.get("talisman_active_effects") or {}
    effective_stats = battle_bundle.get("stats") or {}
    effective_fortune = max(int(effective_stats.get("fortune") or profile_payload.get("fortune") or 0), 0)
    if active_talisman:
        effective_fortune += max(int(round(float(talisman_active_effects.get("fishing_luck_bonus") or 0))), 0)
    empty_chance = _fishing_empty_chance(spot, effective_fortune)
    if active_talisman:
        empty_chance = _apply_fishing_empty_reduce(empty_chance, talisman_active_effects)
    base_candidates = _base_fishing_candidates(settings)
    candidates = _spot_candidates(spot, base_candidates)
    if not candidates:
        raise ValueError("该钓场当前没有可钓取的奖励")
    chosen = None
    chosen_kind = ""
    cast_cost_stone = max(int(spot.get("cast_cost_stone") or 0), 0)

    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立")
        assert_profile_alive(profile, "前往钓鱼")
        if not _meets_realm_requirement(profile, spot.get("min_realm_stage"), int(spot.get("min_realm_layer") or 1)):
            raise ValueError(f"前往 {spot['name']} 需达到 {_spot_requirement_text(spot)}")

        if cast_cost_stone > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -cast_cost_stone,
                action_text=f"前往 {spot['name']} 抛竿",
                apply_tribute=False,
            )
        session.commit()

    from bot.plugins.xiuxian_game.world_service import _bump_daily_counter
    _bump_daily_counter(tg, "fish_daily_count")

    if random.random() >= empty_chance:
        tier_pick = _weighted_choice(
            _tier_weights_for_spot(spot, effective_fortune, {int(row.get("quality_level") or 0) for row in candidates}, settings),
            weight_key="weight",
        )
        if not tier_pick:
            raise ValueError("当前无法计算钓鱼概率")
        chosen_tier = int(tier_pick.get("quality_level") or 1)
        tier_candidates = [row for row in candidates if int(row.get("quality_level") or 0) == chosen_tier]
        kind_pick = _weighted_choice(_kind_weights_for_tier(spot, tier_candidates), weight_key="weight")
        if not kind_pick:
            raise ValueError("当前钓场没有可用的奖励种类")
        chosen_kind = str(kind_pick.get("kind") or "")
        kind_candidates = [row for row in tier_candidates if str(row.get("kind") or "") == chosen_kind]
        chosen = _weighted_choice(kind_candidates, weight_key="fishing_weight")
        if not chosen:
            raise ValueError("当前钓场没有可用的奖励物品")

    if chosen is None:
        message = f"灵波一圈圈荡开又收拢，竿尖始终没有半点动静——{spot['name']}之下，今日并无灵物愿上钩。"
        create_journal(
            tg,
            "fishing",
            "灵河垂钓",
            f"在{spot['name']}守了半日，灵河无获——本次轮空。",
        )
        curse_event = _legacy_service()._apply_artifact_curse_backlash(
            tg,
            "fishing",
            equipped_artifacts=_legacy_service().collect_equipped_artifacts(tg),
        )
        _legacy_service()._record_artifact_curse_event(tg, curse_event)
        if curse_event:
            message += f" {curse_event.get('message') or ''}".rstrip()
        return {
            "spot_key": spot["key"],
            "spot_name": spot["name"],
            "cast_cost_stone": cast_cost_stone,
            "fortune_used": effective_fortune,
            "reward_kind": None,
            "reward_kind_label": "",
            "reward_item": None,
            "quantity": 0,
            "quality_level": 0,
            "quality_label": "",
            "quality_color": "",
            "message": message,
            "empty_handed": True,
            "empty_chance_percent": round(empty_chance * 100.0, 2),
            "curse_event": curse_event,
            "active_talisman": None if not active_talisman else {
                "name": active_talisman.get("name"),
                "effects": talisman_active_effects,
                "summary": _legacy_service().active_talisman_effect_summary(talisman_active_effects),
            },
        }

    quantity = random.randint(int(chosen.get("quantity_min") or 1), int(chosen.get("quantity_max") or 1))
    if active_talisman:
        quantity_bonus = max(float(talisman_active_effects.get("fishing_quantity_bonus") or 0), 0.0)
        if quantity_bonus > 0:
            quantity = max(int(round(quantity * (1 + quantity_bonus / 100.0))), 1)
    granted_reward = None
    try:
        granted_reward = _grant_item_by_kind(tg, chosen_kind, int(chosen.get("ref_id") or 0), quantity)
    except Exception as exc:
        if cast_cost_stone > 0:
            with Session() as session:
                apply_spiritual_stone_delta(
                    session,
                    tg,
                    cast_cost_stone,
                    action_text=f"{spot['name']} 垂钓异常返还灵石",
                    apply_tribute=False,
                )
                session.commit()
        raise ValueError("垂钓奖励发放失败，已返还本次灵石，请稍后重试。") from exc

    reward_name = str(chosen.get("name") or "未知物品").strip() or "未知物品"
    kind_label = str(chosen.get("kind_label") or ITEM_KIND_LABELS.get(chosen_kind, chosen_kind))
    quality_level = max(int(chosen.get("quality_level") or 1), 1)
    quality = _quality_meta(quality_level)
    luck_note = ""
    if effective_fortune >= 18 and quality_level >= max(int(spot.get("quality_min") or 1) + 1, 3):
        luck_note = "冥冥中似有气运加身，原本咬钩的不过寻常灵物，拉上来时却已蜕变成更高品阶的宝物。"
    elif quality_level >= 6:
        luck_note = "水面忽然裂开一道灵光裂隙，转瞬便要合拢——你几乎是在最后一息抓住了那团光芒。"
    message = f"竿身猛地一沉！{spot['name']}水底翻起一串灵泡，你收线拉起了{quality['label']}{kind_label}【{reward_name}】"
    if quantity > 1:
        message += f" ×{quantity}"
    message += "。"
    if isinstance(granted_reward, dict) and granted_reward.get("duplicate_converted"):
        message += f"你早已掌握此物，重复所得已折为 {int(granted_reward.get('stone_compensation') or 0)} 灵石。"
    if luck_note:
        message += luck_note
    if active_talisman:
        summary = _legacy_service().active_talisman_effect_summary(talisman_active_effects)
        if summary:
            message += f"随身符箓【{active_talisman.get('name') or '符箓'}】微微一亮，{ '、'.join(summary[:2]) }。"

    create_journal(
        tg,
        "fishing",
        "灵河垂钓",
        f"在 {spot['name']} 钓起【{reward_name}】×{quantity}，品阶 {quality['label']}。",
    )
    curse_event = _legacy_service()._apply_artifact_curse_backlash(
        tg,
        "fishing",
        equipped_artifacts=_legacy_service().collect_equipped_artifacts(tg),
    )
    _legacy_service()._record_artifact_curse_event(tg, curse_event)
    if curse_event:
        message += f" {curse_event.get('message') or ''}".rstrip()
    return {
        "spot_key": spot["key"],
        "spot_name": spot["name"],
        "cast_cost_stone": max(int(spot.get("cast_cost_stone") or 0), 0),
        "fortune_used": effective_fortune,
        "reward_kind": chosen_kind,
        "reward_kind_label": kind_label,
        "reward_item": granted_reward or chosen.get("item"),
        "quantity": 0 if isinstance(granted_reward, dict) and granted_reward.get("duplicate_converted") else quantity,
        "stone_compensation": int((granted_reward or {}).get("stone_compensation") or 0) if isinstance(granted_reward, dict) else 0,
        "duplicate_converted": bool(isinstance(granted_reward, dict) and granted_reward.get("duplicate_converted")),
        "quality_level": quality_level,
        "quality_label": quality["label"],
        "quality_color": quality["color"],
        "message": message,
        "empty_handed": False,
        "empty_chance_percent": round(empty_chance * 100.0, 2),
        "curse_event": curse_event,
        "active_talisman": None if not active_talisman else {
            "name": active_talisman.get("name"),
            "effects": talisman_active_effects,
            "summary": _legacy_service().active_talisman_effect_summary(talisman_active_effects),
        },
    }
