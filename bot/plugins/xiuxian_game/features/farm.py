from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    XiuxianFarmPlot,
    XiuxianMaterial,
    XiuxianMaterialInventory,
    XiuxianProfile,
    XiuxianRecipe,
    XiuxianRecipeIngredient,
    apply_spiritual_stone_delta,
    assert_profile_alive,
    create_journal,
    get_profile,
    get_shared_spiritual_stone_total,
    realm_index,
    serialize_datetime,
    serialize_material,
    serialize_profile,
    utcnow,
)


FARM_SOURCE_LABEL = "灵田"
FARM_PLOT_COUNT = 5
DEFAULT_UNLOCKED_SLOTS = 3
DEFAULT_HARVEST_WINDOW_MINUTES = 60

FARM_UNLOCK_RULES: dict[int, dict[str, Any]] = {
    1: {"default_unlocked": True, "unlock_cost_stone": 0, "unlock_realm_stage": None, "unlock_realm_layer": 1},
    2: {"default_unlocked": True, "unlock_cost_stone": 0, "unlock_realm_stage": None, "unlock_realm_layer": 1},
    3: {"default_unlocked": True, "unlock_cost_stone": 0, "unlock_realm_stage": None, "unlock_realm_layer": 1},
    4: {"default_unlocked": False, "unlock_cost_stone": 600, "unlock_realm_stage": "筑基", "unlock_realm_layer": 3},
    5: {"default_unlocked": False, "unlock_cost_stone": 1600, "unlock_realm_stage": "金丹", "unlock_realm_layer": 1},
}

FARM_ACTION_ALIASES = {
    "water": "water",
    "浇水": "water",
    "watering": "water",
    "fertilize": "fertilize",
    "施肥": "fertilize",
    "fertilizer": "fertilize",
    "clear_pest": "clear_pest",
    "clear-pest": "clear_pest",
    "pest": "clear_pest",
    "除虫": "clear_pest",
    "驱虫": "clear_pest",
}


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def _ensure_seed_data() -> None:
    _legacy_service().ensure_seed_data()


def _plot_rule(slot_index: int) -> dict[str, Any]:
    rule = FARM_UNLOCK_RULES.get(int(slot_index))
    if not rule:
        raise ValueError("灵田地块不存在")
    return rule


def _unlock_requirement_text(rule: dict[str, Any]) -> str:
    realm_stage = str(rule.get("unlock_realm_stage") or "").strip()
    realm_layer = max(int(rule.get("unlock_realm_layer") or 1), 1)
    cost = max(int(rule.get("unlock_cost_stone") or 0), 0)
    if not realm_stage and cost <= 0:
        return "初始开放"
    parts: list[str] = []
    if realm_stage:
        parts.append(f"{realm_stage}{realm_layer}层")
    if cost > 0:
        parts.append(f"{cost} 灵石")
    return " · ".join(parts) or "初始开放"


def _material_unlock_text(material: XiuxianMaterial | dict[str, Any]) -> str:
    stage = str(getattr(material, "unlock_realm_stage", None) if not isinstance(material, dict) else material.get("unlock_realm_stage") or "").strip()
    layer = max(
        int(
            getattr(material, "unlock_realm_layer", 1)
            if not isinstance(material, dict)
            else material.get("unlock_realm_layer") or 1
        ),
        1,
    )
    return f"{stage}{layer}层可种植" if stage else "入道后即可种植"


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


def _load_profile_for_farm(session: Session, tg: int, action_text: str) -> XiuxianProfile:
    profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
    if profile is None or not profile.consented:
        raise ValueError("你尚未踏入仙途，道基未立")
    assert_profile_alive(profile, action_text)
    return profile


def _load_recipe_map(session: Session) -> dict[int, list[dict[str, Any]]]:
    rows = (
        session.query(XiuxianRecipeIngredient.material_id, XiuxianRecipe.id, XiuxianRecipe.name)
        .join(XiuxianRecipe, XiuxianRecipe.id == XiuxianRecipeIngredient.recipe_id)
        .filter(
            XiuxianRecipe.enabled.is_(True),
            XiuxianRecipe.recipe_kind == "pill",
        )
        .order_by(XiuxianRecipe.name.asc(), XiuxianRecipe.id.asc())
        .all()
    )
    catalog: dict[int, list[dict[str, Any]]] = {}
    for material_id, recipe_id, recipe_name in rows:
        key = int(material_id or 0)
        if key <= 0:
            continue
        catalog.setdefault(key, []).append({"id": int(recipe_id or 0), "name": str(recipe_name or "").strip()})
    return catalog


def _harvest_window_minutes(material: XiuxianMaterial | dict[str, Any]) -> int:
    growth_minutes = max(
        int(getattr(material, "growth_minutes", 0) if not isinstance(material, dict) else material.get("growth_minutes") or 0),
        1,
    )
    return max(DEFAULT_HARVEST_WINDOW_MINUTES, growth_minutes // 2)


def _watering_chance(material: XiuxianMaterial) -> float:
    quality = max(int(material.quality_level or 1), 1)
    growth_minutes = max(int(material.growth_minutes or 1), 1)
    base = 0.42 + (quality - 1) * 0.08
    if growth_minutes >= 150:
        base += 0.08
    return min(max(base, 0.2), 0.82)


def _pest_chance(material: XiuxianMaterial) -> float:
    quality = max(int(material.quality_level or 1), 1)
    growth_minutes = max(int(material.growth_minutes or 1), 1)
    base = 0.18 + (quality - 1) * 0.07
    if growth_minutes >= 180:
        base += 0.05
    return min(max(base, 0.05), 0.6)


def _fertilize_cost(material: XiuxianMaterial | dict[str, Any]) -> int:
    seed_cost = max(
        int(getattr(material, "seed_price_stone", 0) if not isinstance(material, dict) else material.get("seed_price_stone") or 0),
        0,
    )
    quality = max(
        int(getattr(material, "quality_level", 1) if not isinstance(material, dict) else material.get("quality_level") or 1),
        1,
    )
    return max(12, seed_cost // 2 + (quality - 1) * 4)


def _reset_plot(plot: XiuxianFarmPlot) -> None:
    plot.current_material_id = None
    plot.planted_at = None
    plot.mature_at = None
    plot.harvest_deadline_at = None
    plot.base_yield = 0
    plot.needs_watering = False
    plot.watered = False
    plot.pest_risk = False
    plot.pest_cleared = False
    plot.fertilized = False
    plot.updated_at = utcnow()


def _plot_has_crop(plot: XiuxianFarmPlot) -> bool:
    return bool(
        int(plot.current_material_id or 0) > 0
        and plot.planted_at is not None
        and plot.mature_at is not None
        and plot.harvest_deadline_at is not None
    )


def _ensure_farm_plots(session: Session, tg: int, *, for_update: bool = False) -> tuple[list[XiuxianFarmPlot], bool]:
    query = session.query(XiuxianFarmPlot).filter(XiuxianFarmPlot.tg == int(tg)).order_by(XiuxianFarmPlot.slot_index.asc())
    if for_update:
        query = query.with_for_update()
    rows = query.all()
    row_map = {int(row.slot_index): row for row in rows}
    changed = False
    for slot_index in range(1, FARM_PLOT_COUNT + 1):
        rule = _plot_rule(slot_index)
        row = row_map.get(slot_index)
        if row is None:
            row = XiuxianFarmPlot(
                tg=int(tg),
                slot_index=slot_index,
                unlocked=bool(rule.get("default_unlocked")),
            )
            session.add(row)
            row_map[slot_index] = row
            changed = True
            continue
        if rule.get("default_unlocked") and not row.unlocked:
            row.unlocked = True
            row.updated_at = utcnow()
            changed = True
        if int(row.current_material_id or 0) > 0 and not row.unlocked:
            row.unlocked = True
            row.updated_at = utcnow()
            changed = True
    if changed:
        session.flush()
    return [row_map[index] for index in range(1, FARM_PLOT_COUNT + 1)], changed


def _serialize_farm_material(
    material: XiuxianMaterial,
    recipe_map: dict[int, list[dict[str, Any]]],
    profile: XiuxianProfile | None = None,
) -> dict[str, Any] | None:
    base = serialize_material(material)
    if not base:
        return None
    recipes = recipe_map.get(int(material.id), [])
    if not recipes:
        return None
    recipe_names = [str(item.get("name") or "").strip() for item in recipes if str(item.get("name") or "").strip()]
    realm_unlocked = _meets_realm_requirement(profile, material.unlock_realm_stage, int(material.unlock_realm_layer or 1))
    seed_cost = max(int(material.seed_price_stone or 0), 0)
    available_stone = max(int(get_shared_spiritual_stone_total(int(profile.tg or 0)) or 0), 0) if profile is not None else seed_cost
    base.update(
        {
            "recipe_names": recipe_names,
            "recipe_summary": "、".join(recipe_names[:3]) + (" 等丹方" if len(recipe_names) > 3 else ""),
            "recipe_count": len(recipe_names),
            "unlock_requirement_text": _material_unlock_text(material),
            "realm_unlocked": realm_unlocked,
            "plantable_now": realm_unlocked,
            "seed_affordable": bool(profile is None or available_stone >= seed_cost),
            "fertilize_cost_stone": _fertilize_cost(material),
            "growth_label": f"{max(int(material.growth_minutes or 0), 1)} 分钟",
            "yield_label": f"{max(int(material.yield_min or 0), 1)} - {max(int(material.yield_max or material.yield_min or 1), int(material.yield_min or 1), 1)} 份",
        }
    )
    return base


def _list_farm_materials(
    session: Session,
    *,
    profile: XiuxianProfile | None = None,
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    recipe_map = _load_recipe_map(session)
    rows = (
        session.query(XiuxianMaterial)
        .filter(
            XiuxianMaterial.enabled.is_(True),
            XiuxianMaterial.can_plant.is_(True),
        )
        .order_by(XiuxianMaterial.id.asc())
        .all()
    )
    payloads = [
        item
        for item in (_serialize_farm_material(row, recipe_map, profile) for row in rows)
        if item is not None
    ]
    payloads.sort(
        key=lambda item: (
            -int(item.get("quality_level") or 0),
            int(item.get("seed_price_stone") or 0),
            str(item.get("name") or ""),
        )
    )
    return payloads, recipe_map


def _load_plot_materials(session: Session, plots: list[XiuxianFarmPlot]) -> dict[int, XiuxianMaterial]:
    material_ids = sorted({int(plot.current_material_id or 0) for plot in plots if int(plot.current_material_id or 0) > 0})
    if not material_ids:
        return {}
    rows = (
        session.query(XiuxianMaterial)
        .filter(XiuxianMaterial.id.in_(material_ids))
        .all()
    )
    return {int(row.id): row for row in rows}


def _calculate_harvest_outcome(plot: XiuxianFarmPlot, now) -> dict[str, Any]:
    base_yield = max(int(plot.base_yield or 0), 0)
    water_bonus = 1 if plot.needs_watering and plot.watered else 0
    dry_penalty = 1 if plot.needs_watering and not plot.watered else 0
    fertilize_bonus = 1 if plot.fertilized else 0
    pest_penalty = 1 if plot.pest_risk and not plot.pest_cleared else 0
    overdue_penalty = 0
    if plot.harvest_deadline_at and now > plot.harvest_deadline_at:
        interval_minutes = max(
            DEFAULT_HARVEST_WINDOW_MINUTES // 2,
            int((plot.harvest_deadline_at - plot.mature_at).total_seconds() // 60) or 30,
        )
        overdue_minutes = max(int((now - plot.harvest_deadline_at).total_seconds() // 60), 0)
        overdue_penalty = 1 + overdue_minutes // max(interval_minutes, 1)
    quantity = max(base_yield + water_bonus + fertilize_bonus - dry_penalty - pest_penalty - overdue_penalty, 0)
    return {
        "quantity": quantity,
        "base_yield": base_yield,
        "water_bonus": water_bonus,
        "dry_penalty": dry_penalty,
        "fertilize_bonus": fertilize_bonus,
        "pest_penalty": pest_penalty,
        "overdue_penalty": overdue_penalty,
        "withered": quantity <= 0,
    }


def _plot_status(plot: XiuxianFarmPlot, now) -> tuple[str, str]:
    if not plot.unlocked:
        return "locked", "未解锁"
    if not _plot_has_crop(plot):
        return "idle", "空置中"
    if plot.mature_at and now < plot.mature_at:
        return "growing", "成长中"
    if plot.harvest_deadline_at and now > plot.harvest_deadline_at:
        return "overdue", "灵气流失"
    return "ready", "可收获"


def _serialize_plot(
    plot: XiuxianFarmPlot,
    material: XiuxianMaterial | None,
    recipe_map: dict[int, list[dict[str, Any]]],
    profile: XiuxianProfile | None,
    now,
) -> dict[str, Any]:
    rule = _plot_rule(int(plot.slot_index))
    status, status_label = _plot_status(plot, now)
    occupied = bool(material and _plot_has_crop(plot))
    requirement_text = _unlock_requirement_text(rule)
    realm_ok = _meets_realm_requirement(profile, rule.get("unlock_realm_stage"), int(rule.get("unlock_realm_layer") or 1))
    current_stone = max(int(get_shared_spiritual_stone_total(int(profile.tg or 0)) or 0), 0) if profile else 0
    unlock_cost = max(int(rule.get("unlock_cost_stone") or 0), 0)
    can_unlock = (not plot.unlocked) and realm_ok and current_stone >= unlock_cost
    locked_reason = ""
    if not plot.unlocked:
        if not realm_ok:
            locked_reason = f"需达到 {requirement_text}"
        elif current_stone < unlock_cost:
            locked_reason = f"解锁需要 {unlock_cost} 灵石"
    recipe_names = []
    if material is not None:
        recipe_names = [item["name"] for item in recipe_map.get(int(material.id), []) if item.get("name")]
    harvest_preview = _calculate_harvest_outcome(plot, now) if occupied else {"quantity": 0}
    seconds_until_mature = 0
    seconds_until_deadline = 0
    progress_percent = 0
    if occupied and plot.mature_at:
        seconds_until_mature = max(int((plot.mature_at - now).total_seconds()), 0)
        if plot.harvest_deadline_at:
            seconds_until_deadline = int((plot.harvest_deadline_at - now).total_seconds())
        total_grow_seconds = max(int((plot.mature_at - plot.planted_at).total_seconds()), 1) if plot.planted_at else 1
        elapsed_seconds = max(total_grow_seconds - seconds_until_mature, 0)
        progress_percent = min(max(int(round(elapsed_seconds * 100 / total_grow_seconds)), 0), 100)

    care_tags: list[str] = []
    if occupied:
        if plot.needs_watering:
            care_tags.append("已浇灌" if plot.watered else "待浇灌")
        else:
            care_tags.append("水脉平稳")
        if plot.pest_risk:
            care_tags.append("虫害已清" if plot.pest_cleared else "有虫害")
        else:
            care_tags.append("无虫害")
        if plot.fertilized:
            care_tags.append("已施肥")

    can_water = occupied and status == "growing" and plot.needs_watering and not plot.watered
    can_fertilize = occupied and status == "growing" and not plot.fertilized
    can_clear_pest = occupied and bool(plot.pest_risk) and not plot.pest_cleared
    can_harvest = occupied and status in {"ready", "overdue"}
    fertilize_cost = _fertilize_cost(material) if material is not None else 0
    return {
        "slot_index": int(plot.slot_index),
        "unlocked": bool(plot.unlocked),
        "occupied": occupied,
        "status": status,
        "status_label": status_label,
        "unlock_cost_stone": unlock_cost,
        "unlock_realm_stage": rule.get("unlock_realm_stage"),
        "unlock_realm_layer": int(rule.get("unlock_realm_layer") or 1),
        "unlock_requirement_text": requirement_text,
        "can_unlock": can_unlock,
        "locked_reason": locked_reason,
        "material_id": int(material.id) if material is not None else 0,
        "material": serialize_material(material) if material is not None else None,
        "recipe_names": recipe_names,
        "recipe_summary": "、".join(recipe_names[:3]) + (" 等丹方" if len(recipe_names) > 3 else ""),
        "planted_at": serialize_datetime(plot.planted_at),
        "mature_at": serialize_datetime(plot.mature_at),
        "harvest_deadline_at": serialize_datetime(plot.harvest_deadline_at),
        "seconds_until_mature": seconds_until_mature,
        "seconds_until_deadline": seconds_until_deadline,
        "progress_percent": progress_percent,
        "base_yield": max(int(plot.base_yield or 0), 0),
        "yield_preview": max(int(harvest_preview.get("quantity") or 0), 0),
        "needs_watering": bool(plot.needs_watering),
        "watered": bool(plot.watered),
        "pest_risk": bool(plot.pest_risk),
        "pest_cleared": bool(plot.pest_cleared),
        "fertilized": bool(plot.fertilized),
        "care_tags": care_tags,
        "can_water": can_water,
        "can_fertilize": can_fertilize,
        "can_clear_pest": can_clear_pest,
        "can_harvest": can_harvest,
        "fertilize_cost_stone": fertilize_cost,
    }


def _append_inventory_material(session: Session, tg: int, material_id: int, quantity: int) -> int:
    row = (
        session.query(XiuxianMaterialInventory)
        .filter(
            XiuxianMaterialInventory.tg == int(tg),
            XiuxianMaterialInventory.material_id == int(material_id),
        )
        .with_for_update()
        .first()
    )
    if row is None:
        row = XiuxianMaterialInventory(tg=int(tg), material_id=int(material_id), quantity=0)
        session.add(row)
    row.quantity = max(int(row.quantity or 0) + max(int(quantity or 0), 0), 0)
    row.updated_at = utcnow()
    return int(row.quantity)


def _load_farmable_material_or_raise(
    session: Session,
    profile: XiuxianProfile,
    material_id: int,
) -> tuple[XiuxianMaterial, list[str]]:
    material = (
        session.query(XiuxianMaterial)
        .filter(XiuxianMaterial.id == int(material_id))
        .with_for_update()
        .first()
    )
    if material is None or not material.enabled:
        raise ValueError("灵种对应的材料不存在")
    if not material.can_plant:
        raise ValueError("该材料当前不能通过灵田种植")
    recipe_map = _load_recipe_map(session)
    recipe_names = [item["name"] for item in recipe_map.get(int(material.id), []) if item.get("name")]
    if not recipe_names:
        raise ValueError("该材料当前没有可用丹方，暂时不能种植")
    if not _meets_realm_requirement(profile, material.unlock_realm_stage, int(material.unlock_realm_layer or 1)):
        raise ValueError(f"{material.name} 需达到 {_material_unlock_text(material)}")
    return material, recipe_names


def build_farm_bundle(tg: int) -> dict[str, Any]:
    _ensure_seed_data()
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).first()
        if profile is None or not profile.consented:
            return {
                "slot_count": FARM_PLOT_COUNT,
                "plots": [],
                "plantable_materials": [],
                "ready_count": 0,
                "occupied_count": 0,
                "unlocked_count": 0,
                "empty_count": 0,
                "unlockable_count": 0,
                "empty_slots": [],
                "next_mature_at": None,
            }

        plots, changed = _ensure_farm_plots(session, tg, for_update=False)
        material_map = _load_plot_materials(session, plots)
        invalid_plot_found = False
        for plot in plots:
            if _plot_has_crop(plot) and int(plot.current_material_id or 0) > 0 and int(plot.current_material_id or 0) not in material_map:
                _reset_plot(plot)
                invalid_plot_found = True
        if invalid_plot_found:
            session.commit()
            plots, _ = _ensure_farm_plots(session, tg, for_update=False)
            material_map = _load_plot_materials(session, plots)
        elif changed:
            session.commit()

        plantable_materials, recipe_map = _list_farm_materials(session, profile=profile)
        now = utcnow()
        serialized_plots = [_serialize_plot(plot, material_map.get(int(plot.current_material_id or 0)), recipe_map, profile, now) for plot in plots]
        ready_count = sum(1 for plot in serialized_plots if plot.get("can_harvest"))
        occupied_count = sum(1 for plot in serialized_plots if plot.get("occupied"))
        unlocked_count = sum(1 for plot in serialized_plots if plot.get("unlocked"))
        empty_slots = [int(plot["slot_index"]) for plot in serialized_plots if plot.get("unlocked") and not plot.get("occupied")]
        unlockable_count = sum(1 for plot in serialized_plots if plot.get("can_unlock"))
        mature_times = [
            plot["mature_at"]
            for plot in serialized_plots
            if plot.get("occupied") and plot.get("status") == "growing" and plot.get("mature_at")
        ]
        return {
            "slot_count": FARM_PLOT_COUNT,
            "plots": serialized_plots,
            "plantable_materials": plantable_materials,
            "ready_count": ready_count,
            "occupied_count": occupied_count,
            "unlocked_count": unlocked_count,
            "empty_count": len(empty_slots),
            "unlockable_count": unlockable_count,
            "empty_slots": empty_slots,
            "next_mature_at": min(mature_times) if mature_times else None,
        }


def append_farm_source_labels(recipes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not recipes:
        return recipes
    with Session() as session:
        farmable_material_ids = {int(item["id"]) for item in _list_farm_materials(session)[0] if int(item.get("id") or 0) > 0}
    rows: list[dict[str, Any]] = []
    for recipe in recipes:
        payload = dict(recipe)
        ingredients = []
        for item in recipe.get("ingredients") or []:
            ingredient = dict(item)
            material_id = int((ingredient.get("material") or {}).get("id") or ingredient.get("material_id") or 0)
            source_labels = [str(label).strip() for label in ingredient.get("sources") or [] if str(label).strip()]
            if material_id in farmable_material_ids and FARM_SOURCE_LABEL not in source_labels:
                source_labels.append(FARM_SOURCE_LABEL)
            ingredient["sources"] = source_labels
            ingredient["source_text"] = "、".join(source_labels[:5]) if source_labels else "暂未标注"
            ingredients.append(ingredient)
        payload["ingredients"] = ingredients
        rows.append(payload)
    return rows


def farm_source_labels_for_material(material_id: int) -> list[str]:
    with Session() as session:
        farmable_material_ids = {int(item["id"]) for item in _list_farm_materials(session)[0] if int(item.get("id") or 0) > 0}
    return [FARM_SOURCE_LABEL] if int(material_id) in farmable_material_ids else []


def plant_crop_for_user(tg: int, slot_index: int, material_id: int) -> dict[str, Any]:
    _ensure_seed_data()
    slot_index = int(slot_index)
    material_id = int(material_id)
    _plot_rule(slot_index)
    with Session() as session:
        profile = _load_profile_for_farm(session, tg, "种植灵田")
        plots, _ = _ensure_farm_plots(session, tg, for_update=True)
        plot = next((item for item in plots if int(item.slot_index) == slot_index), None)
        if plot is None:
            raise ValueError("灵田地块不存在")
        if not plot.unlocked:
            raise ValueError(f"该地块尚未解锁，需满足 {_unlock_requirement_text(_plot_rule(slot_index))}")
        if _plot_has_crop(plot):
            raise ValueError("该地块已有灵药生长中，请先收获或等待成熟")

        material, recipe_names = _load_farmable_material_or_raise(session, profile, material_id)
        seed_cost = max(int(material.seed_price_stone or 0), 0)
        if seed_cost > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -seed_cost,
                action_text="购买灵种",
                apply_tribute=False,
            )

        now = utcnow()
        growth_minutes = max(int(material.growth_minutes or 0), 1)
        from bot.plugins.xiuxian_game.world_service import get_sect_effects
        profile_data = serialize_profile(get_profile(tg, create=False))
        sect_effects = get_sect_effects(profile_data) if profile_data else {}
        farm_speed = float(sect_effects.get("farm_growth_speed", 0.0))
        effective_growth = max(int(growth_minutes * (1.0 - farm_speed)), 5)
        base_yield_min = max(int(material.yield_min or 0), 1)
        base_yield_max = max(int(material.yield_max or material.yield_min or 0), base_yield_min)
        plot.unlocked = True
        plot.current_material_id = int(material.id)
        plot.planted_at = now
        plot.mature_at = now + timedelta(minutes=effective_growth)
        plot.harvest_deadline_at = plot.mature_at + timedelta(minutes=_harvest_window_minutes(material))
        plot.base_yield = random.randint(base_yield_min, base_yield_max)
        plot.needs_watering = random.random() < _watering_chance(material)
        plot.watered = False
        plot.pest_risk = random.random() < _pest_chance(material)
        plot.pest_cleared = False
        plot.fertilized = False
        plot.updated_at = utcnow()
        material_payload = serialize_material(material)
        material_name = str(material.name or "").strip() or "未知灵药"
        mature_at = serialize_datetime(plot.mature_at)
        harvest_deadline_at = serialize_datetime(plot.harvest_deadline_at)
        session.commit()

    create_journal(
        tg,
        "farm",
        "灵田播种",
        f"在 {slot_index} 号灵田播下【{material_name}】，预计可用于 {('、'.join(recipe_names[:2]) + ('等丹方' if len(recipe_names) > 2 else '')) or '丹药炼制'}。",
    )
    return {
        "slot_index": slot_index,
        "material": material_payload,
        "seed_cost_stone": seed_cost,
        "mature_at": mature_at,
        "harvest_deadline_at": harvest_deadline_at,
        "message": f"灵种落入田垄的刹那泛起一抹微光——{slot_index} 号灵田已种下{material_name}，待灵时圆满即可收取。",
    }


def tend_farm_plot_for_user(tg: int, slot_index: int, action: str) -> dict[str, Any]:
    _ensure_seed_data()
    slot_index = int(slot_index)
    normalized_action = FARM_ACTION_ALIASES.get(str(action or "").strip().lower()) or FARM_ACTION_ALIASES.get(str(action or "").strip())
    if not normalized_action:
        raise ValueError("不支持的灵田操作")
    _plot_rule(slot_index)
    with Session() as session:
        _load_profile_for_farm(session, tg, "照料灵田")
        plots, _ = _ensure_farm_plots(session, tg, for_update=True)
        plot = next((item for item in plots if int(item.slot_index) == slot_index), None)
        if plot is None or not plot.unlocked:
            raise ValueError("该地块尚未解锁")
        if not _plot_has_crop(plot):
            raise ValueError("该地块当前没有种植灵药")
        material = (
            session.query(XiuxianMaterial)
            .filter(XiuxianMaterial.id == int(plot.current_material_id or 0))
            .with_for_update()
            .first()
        )
        if material is None:
            _reset_plot(plot)
            session.commit()
            raise ValueError("地块中的灵药数据已失效，已自动清空，请重新种植")

        now = utcnow()
        if normalized_action == "water":
            if plot.mature_at and now >= plot.mature_at:
                raise ValueError("灵药已经成熟，无需再浇灌")
            if not plot.needs_watering:
                raise ValueError("这一茬灵药根部已触到地下暗泉，水汽充盈，不必再添灵泉。")
            if plot.watered:
                raise ValueError("这块灵田已经浇灌过了")
            plot.watered = True
            plot.updated_at = utcnow()
            session.commit()
            return {
                "slot_index": slot_index,
                "action": normalized_action,
                "yield_bonus": 1,
                "stone_cost": 0,
                "message": f"灵泉沿地脉渗入，{slot_index} 号灵田泛起淡淡水光，灵药根须又往下扎了几分——收成预计 +1。",
            }

        if normalized_action == "fertilize":
            if plot.mature_at and now >= plot.mature_at:
                raise ValueError("灵药已经成熟，无需再施肥催熟")
            if plot.fertilized:
                raise ValueError("这块灵田已施过灵肥，肥力尚在，不必再添。")
            stone_cost = _fertilize_cost(material)
            if stone_cost > 0:
                apply_spiritual_stone_delta(
                    session,
                    tg,
                    -stone_cost,
                    action_text="购入灵肥",
                    apply_tribute=False,
                )
            remaining_seconds = max(int((plot.mature_at - now).total_seconds()), 0)
            speed_up_seconds = max(int(remaining_seconds * 0.35), 8 * 60)
            new_remaining_seconds = max(remaining_seconds - speed_up_seconds, 0)
            plot.mature_at = now + timedelta(seconds=new_remaining_seconds)
            plot.harvest_deadline_at = plot.mature_at + timedelta(minutes=_harvest_window_minutes(material))
            plot.fertilized = True
            plot.updated_at = utcnow()
            session.commit()
            return {
                "slot_index": slot_index,
                "action": normalized_action,
                "yield_bonus": 1,
                "stone_cost": stone_cost,
                "mature_at": serialize_datetime(plot.mature_at),
                "message": f"灵肥入土化为一团暖雾，{slot_index} 号灵田的叶片似又青翠了些，成熟之日比先前更近——收成预计 +1。",
            }

        if not plot.pest_risk:
            raise ValueError("这块灵田目前灵虫未至，不必驱虫。")
        if plot.pest_cleared:
            raise ValueError("这块灵田的虫害已除，灵药正在恢复，无需重复驱虫。")
        plot.pest_cleared = True
        plot.updated_at = utcnow()
        session.commit()
        return {
            "slot_index": slot_index,
            "action": normalized_action,
            "yield_bonus": 0,
            "stone_cost": 0,
            "message": f"灵虫被一一引出田垄，{slot_index} 号灵田终于恢复了清净，灵药叶片重新舒展——减产风险解除。",
        }


def harvest_farm_plot_for_user(tg: int, slot_index: int) -> dict[str, Any]:
    _ensure_seed_data()
    slot_index = int(slot_index)
    _plot_rule(slot_index)
    with Session() as session:
        _load_profile_for_farm(session, tg, "收取灵田")
        plots, _ = _ensure_farm_plots(session, tg, for_update=True)
        plot = next((item for item in plots if int(item.slot_index) == slot_index), None)
        if plot is None or not plot.unlocked:
            raise ValueError("该地块尚未解锁")
        if not _plot_has_crop(plot):
            raise ValueError("该地块当前没有可收获的灵药")
        material = (
            session.query(XiuxianMaterial)
            .filter(XiuxianMaterial.id == int(plot.current_material_id or 0))
            .with_for_update()
            .first()
        )
        if material is None:
            _reset_plot(plot)
            session.commit()
            raise ValueError("地块中的灵药数据已失效，已自动清空，请重新种植")

        now = utcnow()
        if plot.mature_at and now < plot.mature_at:
            raise ValueError("灵药尚未成熟，暂时无法收获")

        outcome = _calculate_harvest_outcome(plot, now)
        mutation_bonus = 0
        if int(outcome["quantity"]) > 0:
            mutation_chance = 8
            if plot.fertilized:
                mutation_chance += 4
            if not plot.needs_watering or plot.watered:
                mutation_chance += 4
            if not plot.pest_risk or plot.pest_cleared:
                mutation_chance += 4
            if random.randint(1, 100) <= mutation_chance:
                mutation_bonus = 1
        total_quantity = max(int(outcome["quantity"]) + mutation_bonus, 0)
        final_inventory_quantity = 0
        material_payload = serialize_material(material)
        material_name = str(material.name or "").strip() or "未知灵药"
        if total_quantity > 0:
            final_inventory_quantity = _append_inventory_material(session, tg, int(material.id), total_quantity)
        _reset_plot(plot)
        session.commit()

    if total_quantity > 0:
        create_journal(
            tg,
            "farm",
            "灵田收获",
            f"从 {slot_index} 号灵田收获【{material_name}】×{total_quantity}，已收入材料背包。",
        )
        detail_parts = [f"收获 {material_name} ×{total_quantity}"]
        if mutation_bonus > 0:
            detail_parts.append("药性异熟额外 +1")
        if int(outcome.get("overdue_penalty") or 0) > 0:
            detail_parts.append(f"错过最佳采收期 -{int(outcome['overdue_penalty'])}")
        if int(outcome.get("pest_penalty") or 0) > 0:
            detail_parts.append("虫害未清 -1")
        if int(outcome.get("dry_penalty") or 0) > 0:
            detail_parts.append("缺少浇灌 -1")
        return {
            "slot_index": slot_index,
            "material": material_payload,
            "quantity": total_quantity,
            "inventory_quantity": final_inventory_quantity,
            "mutation_bonus": mutation_bonus,
            "withered": False,
            "message": "，".join(detail_parts),
        }

    create_journal(
        tg,
        "farm",
        "灵田失收",
        f"{slot_index} 号灵田中的【{material_name}】因照料不当或拖延过久而枯萎。",
    )
    return {
        "slot_index": slot_index,
        "material": material_payload,
        "quantity": 0,
        "inventory_quantity": 0,
        "mutation_bonus": 0,
        "withered": True,
        "message": f"{slot_index} 号灵田中的 {material_name} 已枯萎，本次未能收获材料。",
    }


def auto_harvest_farm_for_user(tg: int) -> dict[str, Any]:
    _ensure_seed_data()
    bundle = build_farm_bundle(tg)
    ready_slots = [
        int(plot.get("slot_index") or 0)
        for plot in bundle.get("plots") or []
        if bool(plot.get("can_harvest")) and int(plot.get("slot_index") or 0) > 0
    ]
    if not ready_slots:
        raise ValueError("当前没有成熟可收获的灵田。")

    results: list[dict[str, Any]] = []
    total_quantity = 0
    withered_count = 0
    for slot_index in ready_slots:
        result = harvest_farm_plot_for_user(tg, slot_index)
        results.append(result)
        total_quantity += max(int(result.get("quantity") or 0), 0)
        if result.get("withered"):
            withered_count += 1

    material_totals: dict[int, dict[str, Any]] = {}
    for result in results:
        material = result.get("material") or {}
        material_id = int(material.get("id") or 0)
        if material_id <= 0:
            continue
        row = material_totals.setdefault(
            material_id,
            {
                "material": material,
                "quantity": 0,
            },
        )
        row["quantity"] = int(row.get("quantity") or 0) + max(int(result.get("quantity") or 0), 0)

    summary = [
        f"{(row.get('material') or {}).get('name') or '材料'} ×{int(row.get('quantity') or 0)}"
        for row in material_totals.values()
        if int(row.get("quantity") or 0) > 0
    ]
    message = f"已自动收获 {len(results)} 块灵田"
    if summary:
        message += f"，获得 {'、'.join(summary)}"
    if withered_count > 0:
        message += f"，其中 {withered_count} 块失收"
    return {
        "harvested_count": len(results),
        "total_quantity": total_quantity,
        "withered_count": withered_count,
        "results": results,
        "material_totals": list(material_totals.values()),
        "message": message,
    }


def unlock_farm_plot_for_user(tg: int, slot_index: int) -> dict[str, Any]:
    _ensure_seed_data()
    slot_index = int(slot_index)
    rule = _plot_rule(slot_index)
    with Session() as session:
        profile = _load_profile_for_farm(session, tg, "开垦灵田")
        plots, _ = _ensure_farm_plots(session, tg, for_update=True)
        plot = next((item for item in plots if int(item.slot_index) == slot_index), None)
        if plot is None:
            raise ValueError("灵田地块不存在")
        if plot.unlocked:
            raise ValueError("该地块已经解锁")
        if not _meets_realm_requirement(profile, rule.get("unlock_realm_stage"), int(rule.get("unlock_realm_layer") or 1)):
            raise ValueError(f"解锁 {slot_index} 号灵田需满足 {_unlock_requirement_text(rule)}")
        unlock_cost = max(int(rule.get("unlock_cost_stone") or 0), 0)
        if unlock_cost > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -unlock_cost,
                action_text="开垦灵田",
                apply_tribute=False,
            )
        plot.unlocked = True
        plot.updated_at = utcnow()
        session.commit()

    create_journal(
        tg,
        "farm",
        "开垦灵田",
        f"成功开垦 {slot_index} 号灵田，今后可用于种植丹药材料。",
    )
    return {
        "slot_index": slot_index,
        "unlock_cost_stone": unlock_cost,
        "message": f"{slot_index} 号灵田已经开垦完成，可以播种新的灵药。",
    }
