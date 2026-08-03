"""后台管理服务:玩家编辑、物品发放、内容目录管理。"""

from __future__ import annotations

from typing import Any

from bot.sql_helper import Session
from bot.sql_helper.sql_douluo.models import (
    DouluoAuctionListing,
    DouluoInventoryItem,
    DouluoItemDefinition,
    DouluoProfile,
    DouluoSoulRing,
    utcnow,
)
from bot.sql_helper.sql_douluo.service import (
    _compute_battle_power_session,
    _load_profile,
    _serialize_profile_row,
    grant_inventory_item,
    get_item_definition,
    get_settings,
    set_settings,
)

_PROFILE_EDITABLE_FIELDS = {
    "soul_power": int,
    "coin": int,
    "spirit_power": int,
    "innate_soul_power": int,
    "realm_stage": str,
    "realm_stars": int,
    "boss_score": int,
}


def admin_get_overview() -> dict[str, Any]:
    with Session() as session:
        player_count = session.query(DouluoProfile).count()
        ring_count = session.query(DouluoSoulRing).count()
        open_listings = (
            session.query(DouluoAuctionListing)
            .filter(DouluoAuctionListing.status == "open")
            .count()
        )
        item_defs = session.query(DouluoItemDefinition).count()
    return {
        "player_count": player_count,
        "ring_count": ring_count,
        "open_listings": open_listings,
        "item_defs": item_defs,
    }


def admin_list_players(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 200)
    offset = max(int(offset or 0), 0)
    with Session() as session:
        rows = (
            session.query(DouluoProfile)
            .order_by(DouluoProfile.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = session.query(DouluoProfile).count()
        items = []
        for profile in rows:
            payload = _serialize_profile_row(profile)
            payload["battle_power"] = _compute_battle_power_session(session, profile)
            items.append(payload)
    return {"total": total, "offset": offset, "limit": limit, "items": items}


def admin_set_profile(tg: int, patch: dict[str, Any]) -> dict[str, Any]:
    tg = int(tg)
    if not isinstance(patch, dict) or not patch:
        raise ValueError("缺少修改字段")
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        changed = False
        for key, converter in _PROFILE_EDITABLE_FIELDS.items():
            if key not in patch:
                continue
            value = patch[key]
            if converter is int:
                value = max(int(value or 0), 0)
            setattr(profile, key, value)
            changed = True
        if changed:
            profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        payload = _serialize_profile_row(profile)
        payload["battle_power"] = _compute_battle_power_session(session, profile)
    return payload


def admin_grant_item(tg: int, item_key: str, quantity: int = 1) -> dict[str, Any]:
    item_key = str(item_key or "").strip()
    quantity = max(int(quantity or 1), 1)
    definition = get_item_definition(item_key)
    if definition is None:
        raise ValueError("物品不存在")
    granted = grant_inventory_item(int(tg), item_key, quantity)
    if granted is None:
        raise ValueError("物品发放失败")
    return granted


def admin_upsert_item_definition(payload: dict[str, Any]) -> dict[str, Any]:
    item_key = str(payload.get("item_key") or "").strip()
    if not item_key:
        raise ValueError("缺少 item_key")
    name = str(payload.get("name") or item_key).strip()
    category = str(payload.get("category") or "material").strip()
    rarity = str(payload.get("rarity") or "凡品").strip()
    with Session() as session:
        row = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == item_key).first()
        if row is None:
            row = DouluoItemDefinition(
                item_key=item_key,
                name=name,
                category=category,
                rarity=rarity,
                version=1,
                is_builtin=False,
            )
            session.add(row)
        else:
            row.name = name
            row.category = category
            row.rarity = rarity
        row.description = payload.get("description") or ""
        row.icon = payload.get("icon") or ""
        row.equipment_slot = payload.get("equipment_slot")
        row.attack = max(int(payload.get("attack") or 0), 0)
        row.defense = max(int(payload.get("defense") or 0), 0)
        row.speed = max(int(payload.get("speed") or 0), 0)
        row.spirit = max(int(payload.get("spirit") or 0), 0)
        row.trigger_chance = payload.get("trigger_chance")
        row.skill = payload.get("skill")
        row.enabled = bool(payload.get("enabled", True))
        row.version = int(row.version or 1) + 1
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        from bot.sql_helper.sql_douluo.service import _serialize_item_definition_row

        return _serialize_item_definition_row(row)


def admin_toggle_item_definition(item_key: str, enabled: bool) -> dict[str, Any]:
    item_key = str(item_key or "").strip()
    with Session() as session:
        row = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == item_key).first()
        if row is None:
            raise ValueError("物品不存在")
        row.enabled = bool(enabled)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        from bot.sql_helper.sql_douluo.service import _serialize_item_definition_row

        return _serialize_item_definition_row(row)


def admin_reset_profile(tg: int) -> dict[str, Any]:
    tg = int(tg)
    with Session() as session:
        profile = session.query(DouluoProfile).filter(DouluoProfile.tg == tg).first()
        if profile is not None:
            session.delete(profile)
        session.query(DouluoSoulRing).filter(DouluoSoulRing.tg == tg).delete()
        session.query(DouluoInventoryItem).filter(DouluoInventoryItem.tg == tg).delete()
        session.commit()
    return admin_set_profile(tg, {})


def admin_update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict) or not patch:
        raise ValueError("缺少设置字段")
    set_settings(patch)
    return get_settings()


def admin_get_settings() -> dict[str, Any]:
    return get_settings()
