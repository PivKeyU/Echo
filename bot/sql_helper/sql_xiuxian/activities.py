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
from .constants import *  # noqa: F401 F403
from .models import *  # noqa: F401 F403
from .serializers import *  # noqa: F401 F403
from .profile import *  # noqa: F401 F403
from .items import *  # noqa: F401 F403

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


def _gambling_pool_entry_key(entry: dict[str, Any] | None) -> tuple[str, str] | None:
    payload = entry if isinstance(entry, dict) else {}
    item_kind = str(payload.get("item_kind") or "").strip()
    item_name = str(payload.get("item_name") or "").strip()
    item_ref_id = int(payload.get("item_ref_id") or 0)
    if not item_kind:
        return None
    if item_name:
        return (item_kind, f"name:{item_name}")
    if item_ref_id > 0:
        return (item_kind, f"id:{item_ref_id}")
    return None


def _merge_default_gambling_reward_pool(raw: Any) -> list[dict[str, Any]]:
    current = copy.deepcopy(raw if isinstance(raw, list) else [])
    if not current:
        return copy.deepcopy(DEFAULT_GAMBLING_REWARD_POOL)
    default_keys = {
        key
        for key in (_gambling_pool_entry_key(entry) for entry in DEFAULT_GAMBLING_REWARD_POOL)
        if key is not None
    }
    current_keys = {
        key
        for key in (_gambling_pool_entry_key(entry) for entry in current)
        if key is not None
    }
    # 仅为默认奖池及其轻度改动补齐新增条目，避免覆盖后台自定义奖池。
    if current_keys and not current_keys.issubset(default_keys):
        return current
    for entry in DEFAULT_GAMBLING_REWARD_POOL:
        key = _gambling_pool_entry_key(entry)
        if key is None or key in current_keys:
            continue
        current.append(copy.deepcopy(entry))
        current_keys.add(key)
    return current


DEPRECATED_XIUXIAN_SETTING_KEYS = {
    "red_packet_merit_min_stone",
    "red_packet_merit_min_count",
    "red_packet_merit_reward",
    "red_packet_merit_modes",
}



def get_scene(scene_id: int) -> XiuxianScene | None:
    scene_value = int(scene_id or 0)
    if scene_value <= 0:
        return None

    def _loader() -> XiuxianScene | None:
        with Session() as session:
            return session.query(XiuxianScene).filter(XiuxianScene.id == scene_value).first()

    return _load_cached_model(
        XiuxianScene,
        version_parts=("catalog", "scenes"),
        cache_parts=("catalog", "scenes", "detail", scene_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_scenes(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianScene)
            if enabled_only:
                query = query.filter(XiuxianScene.enabled.is_(True))
            return [serialize_scene(row) for row in query.order_by(XiuxianScene.id.desc()).all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "scenes"),
        cache_parts=("catalog", "scenes", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def create_scene(**fields) -> dict[str, Any]:
    fields = dict(fields)
    fields["name"] = str(fields.get("name") or "").strip()
    fields["description"] = str(fields.get("description") or "").strip()
    fields["image_url"] = str(fields.get("image_url") or "").strip()
    fields["max_minutes"] = max(_coerce_int(fields.get("max_minutes"), 60), 1)
    min_realm_stage = fields.get("min_realm_stage")
    fields["min_realm_stage"] = normalize_realm_stage(min_realm_stage) if min_realm_stage else None
    fields["min_realm_layer"] = max(_coerce_int(fields.get("min_realm_layer"), 1), 1)
    fields["min_combat_power"] = max(_coerce_int(fields.get("min_combat_power"), 0), 0)
    fields["event_pool"] = _normalize_scene_event_pool(fields.get("event_pool"))
    fields["enabled"] = _coerce_bool(fields.get("enabled"), True)
    with Session() as session:
        scene = XiuxianScene(**fields)
        session.add(scene)
        _queue_catalog_cache_invalidation(session, "scenes")
        session.commit()
        session.refresh(scene)
        return serialize_scene(scene)


def delete_scene(scene_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianScene).filter(XiuxianScene.id == scene_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "scenes")
        session.commit()
        return True


def create_scene_drop(**fields) -> dict[str, Any]:
    with Session() as session:
        drop = XiuxianSceneDrop(**fields)
        session.add(drop)
        _queue_catalog_cache_invalidation(session, "scenes")
        session.commit()
        session.refresh(drop)
        return serialize_scene_drop(drop)


def list_scene_drops(scene_id: int) -> list[dict[str, Any]]:
    scene_value = int(scene_id or 0)
    if scene_value <= 0:
        return []

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianSceneDrop)
                .filter(XiuxianSceneDrop.scene_id == scene_value)
                .order_by(XiuxianSceneDrop.id.asc())
                .all()
            )
            return [serialize_scene_drop(row) for row in rows]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "scenes"),
        cache_parts=("catalog", "scenes", "drops", scene_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def get_encounter_template(template_id: int) -> XiuxianEncounterTemplate | None:
    with Session() as session:
        return session.query(XiuxianEncounterTemplate).filter(XiuxianEncounterTemplate.id == template_id).first()


def list_encounter_templates(enabled_only: bool = False) -> list[dict[str, Any]]:
    with Session() as session:
        query = session.query(XiuxianEncounterTemplate)
        if enabled_only:
            query = query.filter(XiuxianEncounterTemplate.enabled.is_(True))
        return [serialize_encounter_template(row) for row in query.order_by(XiuxianEncounterTemplate.id.desc()).all()]



def create_encounter_template(**fields) -> dict[str, Any]:
    payload = _normalize_encounter_template_fields(fields)
    with Session() as session:
        row = XiuxianEncounterTemplate(**payload)
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_encounter_template(row)


def sync_encounter_template_by_name(**fields) -> dict[str, Any]:
    payload = _normalize_encounter_template_fields(fields)
    with Session() as session:
        row = session.query(XiuxianEncounterTemplate).filter(XiuxianEncounterTemplate.name == payload["name"]).first()
        if row is None:
            row = XiuxianEncounterTemplate(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
            row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_encounter_template(row)


def patch_encounter_template(template_id: int, **fields) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(XiuxianEncounterTemplate).filter(XiuxianEncounterTemplate.id == template_id).first()
        if row is None:
            return None
        current = serialize_encounter_template(row) or {}
        current.update({key: value for key, value in fields.items() if value is not None})
        payload = _normalize_encounter_template_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_encounter_template(row)


def delete_encounter_template(template_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianEncounterTemplate).filter(XiuxianEncounterTemplate.id == template_id).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def create_encounter_instance(
    *,
    template_id: int | None,
    template_name: str,
    group_chat_id: int,
    button_text: str,
    reward_payload: dict[str, Any],
    expires_at,
) -> dict[str, Any]:
    with Session() as session:
        row = XiuxianEncounterInstance(
            template_id=template_id,
            template_name=template_name,
            group_chat_id=group_chat_id,
            button_text=button_text,
            reward_payload=_sanitize_json_value(reward_payload),
            expires_at=expires_at,
            status="active",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_encounter_instance(row)


def get_encounter_instance(instance_id: int) -> XiuxianEncounterInstance | None:
    with Session() as session:
        return session.query(XiuxianEncounterInstance).filter(XiuxianEncounterInstance.id == instance_id).first()


def patch_encounter_instance(instance_id: int, **fields) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(XiuxianEncounterInstance).filter(XiuxianEncounterInstance.id == instance_id).first()
        if row is None:
            return None
        for key, value in fields.items():
            if key == "reward_payload":
                value = _sanitize_json_value(value)
            setattr(row, key, value)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_encounter_instance(row)


def find_active_group_encounter(group_chat_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianEncounterInstance)
            .filter(
                XiuxianEncounterInstance.group_chat_id == group_chat_id,
                XiuxianEncounterInstance.status == "active",
                XiuxianEncounterInstance.expires_at > utcnow(),
            )
            .order_by(XiuxianEncounterInstance.id.desc())
            .first()
        )
        return serialize_encounter_instance(row)


def get_latest_group_encounter_time(group_chat_id: int):
    with Session() as session:
        row = (
            session.query(XiuxianEncounterInstance)
            .filter(XiuxianEncounterInstance.group_chat_id == group_chat_id)
            .order_by(XiuxianEncounterInstance.id.desc())
            .first()
        )
        return row.created_at if row is not None else None


# ── Boss CRUD ──────────────────────────────────────────────────


_BOSS_LOOT_FIELDS = (
    "loot_pills_json",
    "loot_materials_json",
    "loot_artifacts_json",
    "loot_talismans_json",
    "loot_recipes_json",
    "loot_techniques_json",
)



def get_boss_config(boss_id: int) -> XiuxianBossConfig | None:
    with Session() as session:
        return session.query(XiuxianBossConfig).filter(XiuxianBossConfig.id == boss_id).first()


def list_boss_configs(boss_type: str | None = None, *, enabled_only: bool = True) -> list[dict[str, Any]]:
    normalized_type = str(boss_type or "").strip().lower()
    if normalized_type not in {"personal", "world"}:
        normalized_type = ""

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianBossConfig)
            if enabled_only:
                query = query.filter(XiuxianBossConfig.enabled.is_(True))
            if normalized_type:
                query = query.filter(XiuxianBossConfig.boss_type == normalized_type)
            query = query.order_by(XiuxianBossConfig.sort_order.asc(), XiuxianBossConfig.id.asc())
            return [serialize_boss_config(row) for row in query.all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "bosses"),
        cache_parts=(
            "catalog",
            "bosses",
            normalized_type or "all",
            "enabled" if enabled_only else "all",
        ),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def create_boss_config(**fields) -> dict[str, Any]:
    payload = _normalize_boss_config_fields(dict(fields))
    with Session() as session:
        row = XiuxianBossConfig(**payload)
        session.add(row)
        _queue_catalog_cache_invalidation(session, "bosses")
        session.commit()
        session.refresh(row)
        return serialize_boss_config(row)


def patch_boss_config(boss_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianBossConfig).filter(XiuxianBossConfig.id == boss_id).first()
        if row is None:
            return None
        current = serialize_boss_config(row) or {}
        current.update(patch)
        payload = _normalize_boss_config_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "bosses")
        session.commit()
        session.refresh(row)
        return serialize_boss_config(row)


def delete_boss_config(boss_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianBossConfig).filter(XiuxianBossConfig.id == boss_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "bosses")
        session.commit()
        return True


def sync_boss_config_by_name(name: str, **fields) -> dict[str, Any]:
    payload = dict(fields)
    payload["name"] = name
    payload.pop("loot_pills_json_refs", None)
    payload.pop("loot_materials_json_refs", None)
    payload.pop("loot_artifacts_json_refs", None)
    payload.pop("loot_talismans_json_refs", None)
    payload.pop("loot_recipes_json_refs", None)
    payload.pop("loot_techniques_json_refs", None)
    payload = _normalize_boss_config_fields(payload)
    with Session() as session:
        row = session.query(XiuxianBossConfig).filter(XiuxianBossConfig.name == payload["name"]).first()
        if row is None:
            row = XiuxianBossConfig(**payload)
            session.add(row)
            _queue_catalog_cache_invalidation(session, "bosses")
            session.commit()
            session.refresh(row)
            return serialize_boss_config(row)
        changed = False
        for key, value in payload.items():
            if getattr(row, key) != value:
                setattr(row, key, value)
                changed = True
        if changed:
            row.updated_at = utcnow()
            _queue_catalog_cache_invalidation(session, "bosses")
            session.commit()
            session.refresh(row)
        return serialize_boss_config(row)


def get_boss_defeat(tg: int, boss_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianBossDefeat)
            .filter(XiuxianBossDefeat.tg == tg, XiuxianBossDefeat.boss_id == boss_id)
            .first()
        )
        return serialize_boss_defeat(row)


def upsert_boss_defeat(tg: int, boss_id: int, won: bool) -> dict[str, Any]:
    from datetime import date
    today = date.today().strftime("%Y%m%d")
    with Session() as session:
        row = (
            session.query(XiuxianBossDefeat)
            .filter(XiuxianBossDefeat.tg == tg, XiuxianBossDefeat.boss_id == boss_id)
            .with_for_update()
            .first()
        )
        if row is None:
            row = XiuxianBossDefeat(
                tg=tg,
                boss_id=boss_id,
                defeat_count=1 if won else 0,
                daily_attempts=1,
                day_key=today,
                last_defeated_at=utcnow() if won else None,
            )
            session.add(row)
        else:
            if row.day_key != today:
                row.daily_attempts = 0
                row.day_key = today
            row.daily_attempts = max(int(row.daily_attempts or 0) + 1, 1)
            if won:
                row.defeat_count = max(int(row.defeat_count or 0) + 1, 1)
                row.last_defeated_at = utcnow()
            row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_boss_defeat(row)


def get_active_world_boss() -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianWorldBossInstance)
            .filter(
                XiuxianWorldBossInstance.status == "active",
                XiuxianWorldBossInstance.expires_at > utcnow(),
            )
            .order_by(XiuxianWorldBossInstance.id.desc())
            .first()
        )
        return serialize_world_boss_instance(row)


def create_world_boss_instance(boss_id: int, max_hp: int, expires_at: datetime, **kwargs) -> dict[str, Any]:
    with Session() as session:
        row = XiuxianWorldBossInstance(
            boss_id=boss_id,
            current_hp=max_hp,
            max_hp=max_hp,
            status="active",
            expires_at=expires_at,
            **kwargs,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_world_boss_instance(row)


def update_world_boss_hp(instance_id: int, hp_delta: int) -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianWorldBossInstance)
            .filter(XiuxianWorldBossInstance.id == instance_id)
            .with_for_update()
            .first()
        )
        if row is None or row.status != "active":
            return None
        row.current_hp = max(int(row.current_hp or 0) + hp_delta, 0)
        if row.current_hp <= 0:
            row.status = "defeated"
            row.defeated_at = utcnow()
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_world_boss_instance(row)


def settle_world_boss_instance(instance_id: int, status: str = "defeated") -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianWorldBossInstance)
            .filter(XiuxianWorldBossInstance.id == instance_id)
            .with_for_update()
            .first()
        )
        if row is None:
            return None
        row.status = status
        if status == "defeated":
            row.defeated_at = utcnow()
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_world_boss_instance(row)


def upsert_world_boss_damage(instance_id: int, tg: int, damage: int) -> dict[str, Any]:
    with Session() as session:
        row = (
            session.query(XiuxianWorldBossDamage)
            .filter(
                XiuxianWorldBossDamage.instance_id == instance_id,
                XiuxianWorldBossDamage.tg == tg,
            )
            .with_for_update()
            .first()
        )
        if row is None:
            row = XiuxianWorldBossDamage(
                instance_id=instance_id,
                tg=tg,
                total_damage=damage,
                attack_count=1,
                last_attack_at=utcnow(),
            )
            session.add(row)
        else:
            row.total_damage = max(int(row.total_damage or 0) + damage, 0)
            row.attack_count = max(int(row.attack_count or 0) + 1, 1)
            row.last_attack_at = utcnow()
            row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_world_boss_damage(row)


def list_world_boss_damages(instance_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianWorldBossDamage)
            .filter(XiuxianWorldBossDamage.instance_id == instance_id)
            .order_by(XiuxianWorldBossDamage.total_damage.desc())
            .all()
        )
        return [serialize_world_boss_damage(row) for row in rows]


def get_task(task_id: int) -> XiuxianTask | None:
    with Session() as session:
        return session.query(XiuxianTask).filter(XiuxianTask.id == task_id).first()


def list_tasks(enabled_only: bool = True) -> list[dict[str, Any]]:
    with Session() as session:
        query = session.query(XiuxianTask)
        if enabled_only:
            query = query.filter(XiuxianTask.enabled.is_(True))
        return [serialize_task(row) for row in query.order_by(XiuxianTask.id.desc()).all()]


def create_task(**fields) -> dict[str, Any]:
    fields = dict(fields)
    if fields.get("required_item_kind"):
        fields["required_item_kind"] = str(fields.get("required_item_kind")).strip() or None
    fields["required_item_ref_id"] = int(fields.get("required_item_ref_id") or 0) or None
    fields["required_item_quantity"] = max(int(fields.get("required_item_quantity") or 0), 0)
    fields["reward_cultivation"] = max(int(fields.get("reward_cultivation") or 0), 0)
    fields["reward_scale_mode"] = str(fields.get("reward_scale_mode") or "fixed").strip() or "fixed"
    if fields.get("requirement_metric_key"):
        fields["requirement_metric_key"] = str(fields.get("requirement_metric_key")).strip() or None
    else:
        fields["requirement_metric_key"] = None
    fields["requirement_metric_target"] = max(int(fields.get("requirement_metric_target") or 0), 0)
    if fields.get("reward_item_kind"):
        fields["reward_item_kind"] = str(fields.get("reward_item_kind")).strip() or None
    fields["reward_item_ref_id"] = int(fields.get("reward_item_ref_id") or 0) or None
    fields["reward_item_quantity"] = max(int(fields.get("reward_item_quantity") or 0), 0)
    with Session() as session:
        task = XiuxianTask(**fields)
        session.add(task)
        session.commit()
        session.refresh(task)
        return serialize_task(task)


def delete_task(task_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianTask).filter(XiuxianTask.id == task_id).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_task_claims(task_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianTaskClaim)
            .filter(XiuxianTaskClaim.task_id == task_id)
            .order_by(XiuxianTaskClaim.id.asc())
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


def create_journal(tg: int, action_type: str, title: str, detail: str | None = None) -> dict[str, Any]:
    with Session() as session:
        row = XiuxianJournal(
            tg=tg,
            action_type=(action_type or "system").strip()[:32],
            title=(title or "未知操作").strip()[:128],
            detail=(detail or "").strip() or None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_journal(row)


def _has_journal_action_in_session(session: Session, tg: int, action_type: str) -> bool:
    row = (
        session.query(XiuxianJournal.id)
        .filter(
            XiuxianJournal.tg == int(tg),
            XiuxianJournal.action_type == str(action_type or "").strip(),
        )
        .first()
    )
    return row is not None


def _starter_artifact_id_in_session(session: Session) -> int | None:
    row = session.query(XiuxianArtifact.id).filter(XiuxianArtifact.name == STARTER_ARTIFACT_NAME).first()
    return int(row[0]) if row else None


def _starter_artifact_protection_active_in_session(session: Session, tg: int) -> bool:
    return _has_journal_action_in_session(session, tg, STARTER_ARTIFACT_GRANTED_ACTION) and not _has_journal_action_in_session(
        session,
        tg,
        STARTER_ARTIFACT_RELEASED_ACTION,
    )


def has_starter_artifact_claim_record(tg: int) -> bool:
    with Session() as session:
        return _has_journal_action_in_session(session, tg, STARTER_ARTIFACT_GRANTED_ACTION)


def starter_artifact_protection_active(tg: int) -> bool:
    with Session() as session:
        return _starter_artifact_protection_active_in_session(session, tg)


def grant_starter_artifact_once(tg: int, artifact_id: int) -> dict[str, Any]:
    with Session() as session:
        artifact = session.query(XiuxianArtifact).filter(XiuxianArtifact.id == int(artifact_id)).first()
        if artifact is None:
            raise ValueError("artifact not found")
        if _has_journal_action_in_session(session, tg, STARTER_ARTIFACT_GRANTED_ACTION):
            row = (
                session.query(XiuxianArtifactInventory)
                .filter(
                    XiuxianArtifactInventory.tg == int(tg),
                    XiuxianArtifactInventory.artifact_id == int(artifact_id),
                )
                .first()
            )
            return {
                "artifact": serialize_artifact(artifact),
                "quantity": max(int((row.quantity if row is not None else 0) or 0), 0),
                "bound_quantity": max(int((row.bound_quantity if row is not None else 0) or 0), 0),
                "granted": False,
            }
        _, row, granted_quantity = _grant_artifact_inventory_in_session(session, int(tg), int(artifact_id), 1)
        session.add(
            XiuxianJournal(
                tg=int(tg),
                action_type=STARTER_ARTIFACT_GRANTED_ACTION,
                title="获赠新手法宝",
                detail="入道时获赠【凡铁剑】。此宝默认不会因击杀掠夺失去；若你将其用于上架出售或拍卖，则保护失效，且日后重修不会再次补发。",
            )
        )
        _queue_user_view_cache_invalidation(session, int(tg))
        session.commit()
        return {
            "artifact": serialize_artifact(artifact),
            "quantity": max(int(row.quantity or 0), 0),
            "bound_quantity": max(int(row.bound_quantity or 0), 0),
            "granted": granted_quantity > 0,
        }


def release_starter_artifact_protection(tg: int, *, reason: str = "") -> bool:
    with Session() as session:
        if not _starter_artifact_protection_active_in_session(session, tg):
            return False
        session.add(
            XiuxianJournal(
                tg=int(tg),
                action_type=STARTER_ARTIFACT_RELEASED_ACTION,
                title="新手法宝保护失效",
                detail=(reason or "你已将新手法宝用于交易，它不再具备新手保护。").strip() or None,
            )
        )
        session.commit()
        return True


def list_recent_journals(tg: int, hours: int = 24) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(hours=max(int(hours or 24), 1))
    with Session() as session:
        rows = (
            session.query(XiuxianJournal)
            .filter(XiuxianJournal.tg == tg, XiuxianJournal.created_at >= since)
            .order_by(XiuxianJournal.created_at.desc(), XiuxianJournal.id.desc())
            .all()
        )
        return [serialize_journal(row) for row in rows]


def _prune_error_logs(session, keep_count: int) -> None:
    keep = max(int(keep_count or 0), 1)
    stale_rows = (
        session.query(XiuxianErrorLog)
        .order_by(XiuxianErrorLog.id.desc())
        .offset(keep)
        .all()
    )
    for row in stale_rows:
        session.delete(row)


def create_error_log(
    *,
    tg: int | None = None,
    username: str | None = None,
    display_name: str | None = None,
    scope: str = "user",
    level: str = "ERROR",
    operation: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    message: str,
    detail: str | None = None,
) -> dict[str, Any]:
    settings = get_xiuxian_settings()
    retention = max(int(settings.get("error_log_retention_count", DEFAULT_SETTINGS["error_log_retention_count"]) or 0), 1)
    with Session() as session:
        row = XiuxianErrorLog(
            tg=tg,
            username=str(username or "").strip() or None,
            display_name=str(display_name or "").strip() or None,
            scope=str(scope or "user").strip() or "user",
            level=str(level or "ERROR").strip().upper() or "ERROR",
            operation=str(operation or "").strip() or None,
            method=str(method or "").strip().upper() or None,
            path=str(path or "").strip() or None,
            status_code=int(status_code) if status_code is not None else None,
            message=str(message or "unknown error").strip() or "unknown error",
            detail=str(detail or "").strip() or None,
        )
        session.add(row)
        session.flush()
        payload = serialize_error_log(row)
        _prune_error_logs(session, retention)
        session.commit()
        return payload


def list_error_logs(
    *,
    limit: int = 100,
    tg: int | None = None,
    level: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    with Session() as session:
        query = session.query(XiuxianErrorLog)
        if tg is not None:
            query = query.filter(XiuxianErrorLog.tg == int(tg))
        if level:
            query = query.filter(XiuxianErrorLog.level == str(level).strip().upper())
        if keyword:
            pattern = f"%{str(keyword).strip()}%"
            query = query.filter(
                or_(
                    XiuxianErrorLog.message.like(pattern),
                    XiuxianErrorLog.detail.like(pattern),
                    XiuxianErrorLog.operation.like(pattern),
                    XiuxianErrorLog.path.like(pattern),
                    XiuxianErrorLog.display_name.like(pattern),
                    XiuxianErrorLog.username.like(pattern),
                )
            )
        rows = query.order_by(XiuxianErrorLog.id.desc()).limit(max(int(limit or 0), 1)).all()
        return [serialize_error_log(row) for row in rows]


__all__ = [name for name in globals() if not name.startswith("__")]
