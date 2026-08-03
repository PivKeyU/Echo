from __future__ import annotations

import copy
import random
import re
from datetime import datetime, timedelta, timezone
from math import ceil
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

def list_pill_type_options() -> list[dict[str, str]]:
    # 管理页丹药类型统一以后端定义为准，避免前端写死后升级不生效。
    return [
        {
            "value": key,
            "label": label,
            "effect": PILL_EFFECT_VALUE_LABELS.get(key, "主效果"),
        }
        for key, label in PILL_TYPE_LABELS.items()
    ]
ATTRIBUTE_LABELS = {
    "bone_bonus": "根骨",
    "comprehension_bonus": "悟性",
    "divine_sense_bonus": "神识",
    "fortune_bonus": "机缘",
    "willpower_bonus": "心志",
    "charisma_bonus": "魅力",
    "karma_bonus": "因果",
    "qi_blood_bonus": "气血",
    "true_yuan_bonus": "真元",
    "body_movement_bonus": "身法",
    "attack_bonus": "攻击",
    "defense_bonus": "防御",
}
ATTRIBUTE_EFFECT_HINTS = {
    "bone": "道基之本，关乎吐纳周天快慢、丹毒化解之速与气血深浅",
    "comprehension": "开窍之钥，决定功法参悟快慢、丹器炼制手感与那灵光一闪的破境时机",
    "divine_sense": "灵台之眼，秘境中辨吉凶、斗法中窥破绽，全仗此念清明",
    "fortune": "冥冥之中自有定数——影响奇遇临门、宝物品质与天道垂青的一线生机",
    "willpower": "道心坚固则万劫不摧，冲击瓶颈时稳住灵台、持久战中不退反进",
    "charisma": "影响坊市议价余地、播报花费与部分身份门面——行走修真界，人缘也是实力",
    "karma": "因果之力最难捉摸，却暗中影响突破时机、委托回报与秘境凶吉",
    "qi_blood": "影响斗法气血上限，血厚者方能在硬战中站到最后",
    "true_yuan": "影响斗法真元续航，元力绵长者招招不断",
    "body_movement": "影响斗法闪避与身法类门槛，身形如电者先手制敌",
    "attack_power": "影响斗法攻击威能，一剑破万法全赖此力",
    "defense_power": "影响斗法防御承伤，金身不破方能立于不败",
}
ROOT_QUALITY_LEVELS = {
    "废灵根": 1,
    "下品灵根": 2,
    "中品灵根": 3,
    "上品灵根": 4,
    "极品灵根": 5,
    "天灵根": 6,
    "变异灵根": 7,
}
ROOT_QUALITY_COLORS = {
    "废灵根": "#6b7280",
    "下品灵根": "#22c55e",
    "中品灵根": "#3b82f6",
    "上品灵根": "#8b5cf6",
    "极品灵根": "#f59e0b",
    "天灵根": "#ef4444",
    "变异灵根": "#ec4899",
}
ROOT_VARIANT_ELEMENTS = ["雷", "风"]
SHANGHAI_TZ = timezone(timedelta(hours=8))
UTC_TZ = timezone.utc



def get_artifact(artifact_id: int) -> XiuxianArtifact | None:
    artifact_value = int(artifact_id or 0)
    if artifact_value <= 0:
        return None

    def _loader() -> XiuxianArtifact | None:
        with Session() as session:
            return session.query(XiuxianArtifact).filter(XiuxianArtifact.id == artifact_value).first()

    return _load_cached_model(
        XiuxianArtifact,
        version_parts=("catalog", "artifacts"),
        cache_parts=("catalog", "artifacts", "detail", artifact_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def get_pill(pill_id: int) -> XiuxianPill | None:
    pill_value = int(pill_id or 0)
    if pill_value <= 0:
        return None

    def _loader() -> XiuxianPill | None:
        with Session() as session:
            return session.query(XiuxianPill).filter(XiuxianPill.id == pill_value).first()

    return _load_cached_model(
        XiuxianPill,
        version_parts=("catalog", "pills"),
        cache_parts=("catalog", "pills", "detail", pill_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def get_talisman(talisman_id: int) -> XiuxianTalisman | None:
    talisman_value = int(talisman_id or 0)
    if talisman_value <= 0:
        return None

    def _loader() -> XiuxianTalisman | None:
        with Session() as session:
            return session.query(XiuxianTalisman).filter(XiuxianTalisman.id == talisman_value).first()

    return _load_cached_model(
        XiuxianTalisman,
        version_parts=("catalog", "talismans"),
        cache_parts=("catalog", "talismans", "detail", talisman_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def get_technique(technique_id: int) -> XiuxianTechnique | None:
    technique_value = int(technique_id or 0)
    if technique_value <= 0:
        return None

    def _loader() -> XiuxianTechnique | None:
        with Session() as session:
            return session.query(XiuxianTechnique).filter(XiuxianTechnique.id == technique_value).first()

    return _load_cached_model(
        XiuxianTechnique,
        version_parts=("catalog", "techniques"),
        cache_parts=("catalog", "techniques", "detail", technique_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def get_artifact_set(artifact_set_id: int) -> XiuxianArtifactSet | None:
    artifact_set_value = int(artifact_set_id or 0)
    if artifact_set_value <= 0:
        return None

    def _loader() -> XiuxianArtifactSet | None:
        with Session() as session:
            return session.query(XiuxianArtifactSet).filter(XiuxianArtifactSet.id == artifact_set_value).first()

    return _load_cached_model(
        XiuxianArtifactSet,
        version_parts=("catalog", "artifact-sets"),
        cache_parts=("catalog", "artifact-sets", "detail", artifact_set_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_artifacts(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianArtifact)
            if enabled_only:
                query = query.filter(XiuxianArtifact.enabled.is_(True))
            rows = [serialize_artifact(item) for item in query.order_by(XiuxianArtifact.id.desc()).all()]
            return sorted(rows, key=lambda item: _named_quality_sort_key(item or {}, "rarity_level"))

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "artifacts"),
        cache_parts=("catalog", "artifacts", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_pills(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianPill)
            if enabled_only:
                query = query.filter(XiuxianPill.enabled.is_(True))
            rows = [serialize_pill(item) for item in query.order_by(XiuxianPill.id.desc()).all()]
            return sorted(rows, key=lambda item: _named_quality_sort_key(item or {}, "rarity_level"))

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "pills"),
        cache_parts=("catalog", "pills", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_talismans(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianTalisman)
            if enabled_only:
                query = query.filter(XiuxianTalisman.enabled.is_(True))
            rows = [serialize_talisman(item) for item in query.order_by(XiuxianTalisman.id.desc()).all()]
            return sorted(rows, key=lambda item: _named_quality_sort_key(item or {}, "rarity_level"))

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "talismans"),
        cache_parts=("catalog", "talismans", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_techniques(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianTechnique)
            if enabled_only:
                query = query.filter(XiuxianTechnique.enabled.is_(True))
            return [serialize_technique(item) for item in query.order_by(XiuxianTechnique.id.desc()).all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "techniques"),
        cache_parts=("catalog", "techniques", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_user_techniques(tg: int, enabled_only: bool = False) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianUserTechnique)
                .filter(XiuxianUserTechnique.tg == actor_tg)
                .order_by(XiuxianUserTechnique.created_at.asc(), XiuxianUserTechnique.id.asc())
                .all()
            )
            technique_ids = [item.technique_id for item in rows] or [-1]
            technique_map = {
                row.id: row
                for row in session.query(XiuxianTechnique).filter(XiuxianTechnique.id.in_(technique_ids)).all()
            }
            payloads: list[dict[str, Any]] = []
            for row in rows:
                technique = serialize_technique(technique_map.get(row.technique_id))
                if enabled_only and not (technique or {}).get("enabled"):
                    continue
                payloads.append(serialize_user_technique(row, technique))
            return payloads

    return xiuxian_cache.load_versioned_json(
        version_parts=("user-view", actor_tg),
        cache_parts=("user-view", actor_tg, "techniques", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.USER_VIEW_TTL,
        loader=_loader,
    )


def user_has_technique(tg: int, technique_id: int) -> bool:
    with Session() as session:
        row = (
            session.query(XiuxianUserTechnique)
            .filter(XiuxianUserTechnique.tg == tg, XiuxianUserTechnique.technique_id == technique_id)
            .first()
        )
        return row is not None


def _integrity_error_message(exc: IntegrityError) -> str:
    return str(getattr(exc, "orig", exc) or exc).lower()


def _integrity_error_sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    for attr in ("sqlstate", "pgcode"):
        value = getattr(orig, attr, None)
        if value:
            return str(value)
    diag = getattr(orig, "diag", None)
    value = getattr(diag, "sqlstate", None)
    return str(value) if value else None


def _integrity_error_constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    return str(constraint_name) if constraint_name else None


def _is_duplicate_integrity_error(exc: IntegrityError, constraint_name: str) -> bool:
    actual_constraint_name = _integrity_error_constraint_name(exc)
    if actual_constraint_name and actual_constraint_name.lower() == constraint_name.lower():
        return True

    message = _integrity_error_message(exc)
    return constraint_name.lower() in message and (
        "duplicate key value" in message
        or "duplicate entry" in message
        or "unique constraint" in message
    )


def _is_primary_key_id_insert_conflict(exc: IntegrityError, table_name: str) -> bool:
    if _is_duplicate_integrity_error(exc, f"{table_name}_pkey"):
        return True

    message = _integrity_error_message(exc)
    statement = str(getattr(exc, "statement", "") or "").lower()
    sqlstate = _integrity_error_sqlstate(exc)
    return (
        sqlstate in {None, "23505"}
        and table_name.lower() in statement
        and "insert into" in statement
        and "key (id)=" in message
        and "already exists" in message
        and (
            "duplicate key value" in message
            or "duplicate entry" in message
            or "unique constraint" in message
        )
    )


def _sync_sequence_for_primary_key_conflict(exc: IntegrityError, table_name: str) -> bool:
    if not _is_primary_key_id_insert_conflict(exc, table_name):
        return False
    from bot.sql_helper import sync_postgresql_sequences

    sync_postgresql_sequences(table_names={table_name})
    return True


def _recover_user_technique_insert_conflict(session: OrmSession, exc: IntegrityError, tg: int, technique_id: int) -> bool:
    session.rollback()
    existing = (
        session.query(XiuxianUserTechnique)
        .filter(XiuxianUserTechnique.tg == tg, XiuxianUserTechnique.technique_id == technique_id)
        .first()
    )
    if existing is not None:
        return True
    return _sync_sequence_for_primary_key_conflict(exc, "xiuxian_user_techniques")


def _knowledge_quality_level(session: OrmSession, item_kind: str, item: Any) -> int:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind == "recipe":
        result_kind = str(getattr(item, "result_kind", "") or "").strip()
        result_ref_id = int(getattr(item, "result_ref_id", 0) or 0)
        if result_kind == "material" and result_ref_id > 0:
            material = session.query(XiuxianMaterial).filter(XiuxianMaterial.id == result_ref_id).first()
            return max(int(getattr(material, "quality_level", 1) or 1), 1)
        model_cls = {
            "artifact": XiuxianArtifact,
            "pill": XiuxianPill,
            "talisman": XiuxianTalisman,
            "technique": XiuxianTechnique,
        }.get(result_kind)
        if model_cls is not None and result_ref_id > 0:
            result_item = session.query(model_cls).filter(model_cls.id == result_ref_id).first()
            return max(int(QUALITY_LABEL_LEVELS.get(str(getattr(result_item, "rarity", "") or "").strip(), 1)), 1)
        return 1
    if normalized_kind == "technique":
        return max(int(QUALITY_LABEL_LEVELS.get(str(getattr(item, "rarity", "") or "").strip(), 1)), 1)
    return 1


def _round_knowledge_duplicate_stone(value: float) -> int:
    return max(int(ceil(max(float(value), 1.0) / 5.0) * 5), 5)


def _knowledge_duplicate_stone_amount(session: OrmSession, item_kind: str, item: Any, quantity: int = 1) -> int:
    normalized_kind = str(item_kind or "").strip()
    amount = max(int(quantity or 1), 1)
    quality_level = _knowledge_quality_level(session, normalized_kind, item)
    if normalized_kind == "recipe":
        result_quantity = max(int(getattr(item, "result_quantity", 1) or 1), 1)
        success_rate = min(max(float(getattr(item, "base_success_rate", 60) or 60), 1.0), 100.0)
        base_value = 42.0 + quality_level * 28.0 + result_quantity * 8.0 + max(100.0 - success_rate, 0.0) * 0.55
        ratio = min(0.38, 0.18 + (quality_level - 1) * 0.028)
        return _round_knowledge_duplicate_stone(base_value * ratio) * amount
    if normalized_kind == "technique":
        stat_score = sum(
            max(int(getattr(item, attr, 0) or 0), 0) * weight
            for attr, weight in {
                "attack_bonus": 1.2,
                "defense_bonus": 1.1,
                "bone_bonus": 2.8,
                "comprehension_bonus": 2.9,
                "divine_sense_bonus": 2.7,
                "fortune_bonus": 2.8,
                "qi_blood_bonus": 0.18,
                "true_yuan_bonus": 0.18,
                "body_movement_bonus": 1.3,
                "duel_rate_bonus": 4.5,
                "cultivation_bonus": 4.8,
                "breakthrough_bonus": 5.0,
            }.items()
        )
        base_value = 68.0 + quality_level * 40.0 + stat_score
        ratio = min(0.41, 0.20 + (quality_level - 1) * 0.032)
        return _round_knowledge_duplicate_stone(base_value * ratio) * amount
    return 0


def grant_duplicate_knowledge_compensation_in_session(
    session: OrmSession,
    tg: int,
    item_kind: str,
    item: Any,
    *,
    quantity: int = 1,
    action_text: str | None = None,
) -> dict[str, Any]:
    normalized_kind = str(item_kind or "").strip()
    if normalized_kind not in {"recipe", "technique"}:
        raise ValueError("只有重复丹谱或功法可以折算灵石")
    stone_amount = _knowledge_duplicate_stone_amount(session, normalized_kind, item, quantity=quantity)
    label = ITEM_KIND_LABELS.get(normalized_kind, normalized_kind)
    if stone_amount > 0:
        apply_spiritual_stone_delta(
            session,
            int(tg),
            stone_amount,
            action_text=action_text or f"重复{label}折算灵石",
            allow_create=True,
            allow_dead=True,
            apply_tribute=False,
        )
    _queue_profile_cache_invalidation(session, int(tg))
    _queue_user_view_cache_invalidation(session, int(tg))
    item_payload = serialize_recipe(item) if normalized_kind == "recipe" else serialize_technique(item)
    return {
        normalized_kind: item_payload,
        "quantity": 0,
        "duplicate_converted": True,
        "stone_compensation": stone_amount,
        "converted_to_stone": stone_amount,
        "item_kind": normalized_kind,
        "item_kind_label": label,
        "item_name": (item_payload or {}).get("name") or f"{normalized_kind}#{getattr(item, 'id', 0)}",
    }


def _recover_shop_item_insert_conflict(session: OrmSession, exc: IntegrityError) -> bool:
    session.rollback()
    return _sync_sequence_for_primary_key_conflict(exc, "xiuxian_shop_items")


def grant_technique_to_user(
    tg: int,
    technique_id: int,
    *,
    source: str | None = None,
    obtained_note: str | None = None,
    auto_equip_if_empty: bool = False,
) -> dict[str, Any]:
    normalized_source = (source or "").strip() or None
    normalized_note = (obtained_note or "").strip() or None if obtained_note is not None else None
    last_error: IntegrityError | None = None
    for _ in range(2):
        with Session() as session:
            technique = session.query(XiuxianTechnique).filter(XiuxianTechnique.id == technique_id).first()
            if technique is None:
                raise ValueError("technique not found")
            profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
            if profile is None:
                profile = XiuxianProfile(tg=tg)
                session.add(profile)
            row = (
                session.query(XiuxianUserTechnique)
                .filter(XiuxianUserTechnique.tg == tg, XiuxianUserTechnique.technique_id == technique_id)
                .with_for_update()
                .first()
            )
            if row is None:
                row = XiuxianUserTechnique(
                    tg=tg,
                    technique_id=technique_id,
                    source=normalized_source,
                    obtained_note=normalized_note,
                )
                session.add(row)
            else:
                result = grant_duplicate_knowledge_compensation_in_session(
                    session,
                    tg,
                    "technique",
                    technique,
                    action_text="重复功法折算灵石",
                )
                try:
                    session.commit()
                except IntegrityError as exc:
                    last_error = exc
                    if _recover_user_technique_insert_conflict(session, exc, tg, technique_id):
                        continue
                    raise
                return result
            if auto_equip_if_empty and not profile.current_technique_id:
                profile.current_technique_id = technique_id
                profile.updated_at = utcnow()
            _queue_profile_cache_invalidation(session, tg)
            _queue_user_view_cache_invalidation(session, tg)
            try:
                session.commit()
            except IntegrityError as exc:
                last_error = exc
                if _recover_user_technique_insert_conflict(session, exc, tg, technique_id):
                    continue
                raise
            session.refresh(row)
            return serialize_user_technique(row, serialize_technique(technique))
    if last_error is not None:
        raise last_error
    raise RuntimeError("grant technique failed unexpectedly")


def revoke_technique_from_user(tg: int, technique_id: int) -> bool:
    with Session() as session:
        row = (
            session.query(XiuxianUserTechnique)
            .filter(XiuxianUserTechnique.tg == tg, XiuxianUserTechnique.technique_id == technique_id)
            .first()
        )
        if row is None:
            return False
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is not None and int(profile.current_technique_id or 0) == int(technique_id):
            profile.current_technique_id = None
            profile.updated_at = utcnow()
        session.delete(row)
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def list_artifact_sets(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianArtifactSet)
            if enabled_only:
                query = query.filter(XiuxianArtifactSet.enabled.is_(True))
            return [serialize_artifact_set(item) for item in query.order_by(XiuxianArtifactSet.id.desc()).all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "artifact-sets"),
        cache_parts=("catalog", "artifact-sets", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )



def _sanitize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_json_value(item) for item in value]
    return str(value)



def _sync_named_entity(model_cls, serializer, fields: dict[str, Any], *, catalog_key: str | None = None) -> dict[str, Any]:
    # 默认种子按名称原地同步，避免镜像升级后后台仍显示旧数据。
    with Session() as session:
        row = session.query(model_cls).filter(model_cls.name == fields["name"]).first()
        if row is None:
            row = model_cls(**fields)
            session.add(row)
            try:
                if catalog_key:
                    _queue_catalog_cache_invalidation(session, catalog_key)
                session.commit()
                session.refresh(row)
                return serializer(row)
            except IntegrityError:
                # 多实例并发初始化时，另一方可能已先插入同名种子；回滚后改为读取并同步现有行。
                session.rollback()
                row = session.query(model_cls).filter(model_cls.name == fields["name"]).first()
                if row is None:
                    raise

        changed = False
        for key, value in fields.items():
            if getattr(row, key) != value:
                setattr(row, key, value)
                changed = True
        if changed:
            if catalog_key:
                _queue_catalog_cache_invalidation(session, catalog_key)
            session.commit()
            session.refresh(row)
        return serializer(row)


def create_artifact(**fields) -> dict[str, Any]:
    fields = _normalize_artifact_fields(dict(fields))
    with Session() as session:
        artifact = XiuxianArtifact(**fields)
        session.add(artifact)
        _queue_catalog_cache_invalidation(session, "artifacts")
        session.commit()
        session.refresh(artifact)
        return serialize_artifact(artifact)


def create_pill(**fields) -> dict[str, Any]:
    fields = _normalize_pill_fields(dict(fields))
    with Session() as session:
        pill = XiuxianPill(**fields)
        session.add(pill)
        _queue_catalog_cache_invalidation(session, "pills")
        session.commit()
        session.refresh(pill)
        return serialize_pill(pill)


def create_talisman(**fields) -> dict[str, Any]:
    fields = _normalize_talisman_fields(dict(fields))
    with Session() as session:
        talisman = XiuxianTalisman(**fields)
        session.add(talisman)
        _queue_catalog_cache_invalidation(session, "talismans")
        session.commit()
        session.refresh(talisman)
        return serialize_talisman(talisman)


def create_technique(**fields) -> dict[str, Any]:
    fields = _normalize_technique_fields(dict(fields))
    with Session() as session:
        technique = XiuxianTechnique(**fields)
        session.add(technique)
        _queue_catalog_cache_invalidation(session, "techniques")
        session.commit()
        session.refresh(technique)
        return serialize_technique(technique)


def create_artifact_set(**fields) -> dict[str, Any]:
    fields = _normalize_artifact_set_fields(dict(fields))
    with Session() as session:
        artifact_set = XiuxianArtifactSet(**fields)
        session.add(artifact_set)
        _queue_catalog_cache_invalidation(session, "artifact-sets")
        session.commit()
        session.refresh(artifact_set)
        return serialize_artifact_set(artifact_set)


def _assert_unique_artifact_circulation_safe(session: OrmSession, artifact_id: int, artifact_name: str) -> None:
    inventory_rows = (
        session.query(XiuxianArtifactInventory)
        .filter(
            XiuxianArtifactInventory.artifact_id == int(artifact_id),
            XiuxianArtifactInventory.quantity > 0,
        )
        .with_for_update()
        .all()
    )
    owned_quantity = sum(max(int(row.quantity or 0), 0) for row in inventory_rows)
    shop_quantity = sum(
        max(int(row.quantity or 0), 0)
        for row in (
            session.query(XiuxianShopItem)
            .filter(
                XiuxianShopItem.item_kind == "artifact",
                XiuxianShopItem.item_ref_id == int(artifact_id),
                XiuxianShopItem.enabled.is_(True),
            )
            .with_for_update()
            .all()
        )
    )
    auction_quantity = sum(
        max(int(row.quantity or 0), 0)
        for row in (
            session.query(XiuxianAuctionItem)
            .filter(
                XiuxianAuctionItem.item_kind == "artifact",
                XiuxianAuctionItem.item_ref_id == int(artifact_id),
                XiuxianAuctionItem.status == "active",
            )
            .with_for_update()
            .all()
        )
    )
    total_circulating = owned_quantity + shop_quantity + auction_quantity
    if total_circulating > 1:
        raise ValueError(
            f"法宝【{artifact_name or artifact_id}】当前已有多份在流通中，无法直接改为唯一法宝，请先清理库存/商店/拍卖中的重复份数。"
        )


def patch_artifact(artifact_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianArtifact).filter(XiuxianArtifact.id == artifact_id).first()
        if row is None:
            return None
        current = serialize_artifact(row) or {}
        current.update(patch)
        payload = _normalize_artifact_fields(current)
        if bool(payload.get("unique_item")):
            _assert_unique_artifact_circulation_safe(session, int(artifact_id), str(payload.get("name") or row.name or ""))
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "artifacts")
        session.commit()
        session.refresh(row)
        return serialize_artifact(row)


def patch_pill(pill_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianPill).filter(XiuxianPill.id == pill_id).first()
        if row is None:
            return None
        current = serialize_pill(row) or {}
        current.update(patch)
        payload = _normalize_pill_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "pills")
        session.commit()
        session.refresh(row)
        return serialize_pill(row)


def patch_talisman(talisman_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianTalisman).filter(XiuxianTalisman.id == talisman_id).first()
        if row is None:
            return None
        current = serialize_talisman(row) or {}
        current.update(patch)
        payload = _normalize_talisman_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "talismans")
        session.commit()
        session.refresh(row)
        return serialize_talisman(row)


def patch_technique(technique_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianTechnique).filter(XiuxianTechnique.id == technique_id).first()
        if row is None:
            return None
        current = serialize_technique(row) or {}
        current.update(patch)
        payload = _normalize_technique_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "techniques")
        session.commit()
        session.refresh(row)
        return serialize_technique(row)


def patch_artifact_set(artifact_set_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianArtifactSet).filter(XiuxianArtifactSet.id == artifact_set_id).first()
        if row is None:
            return None
        current = serialize_artifact_set(row) or {}
        current.update(patch)
        payload = _normalize_artifact_set_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "artifact-sets")
        session.commit()
        session.refresh(row)
        return serialize_artifact_set(row)


def sync_artifact_by_name(**fields) -> dict[str, Any]:
    return _sync_named_entity(
        XiuxianArtifact,
        serialize_artifact,
        _normalize_artifact_fields(dict(fields)),
        catalog_key="artifacts",
    )


def sync_pill_by_name(**fields) -> dict[str, Any]:
    return _sync_named_entity(
        XiuxianPill,
        serialize_pill,
        _normalize_pill_fields(dict(fields)),
        catalog_key="pills",
    )


def sync_talisman_by_name(**fields) -> dict[str, Any]:
    return _sync_named_entity(
        XiuxianTalisman,
        serialize_talisman,
        _normalize_talisman_fields(dict(fields)),
        catalog_key="talismans",
    )


def sync_technique_by_name(**fields) -> dict[str, Any]:
    return _sync_named_entity(
        XiuxianTechnique,
        serialize_technique,
        _normalize_technique_fields(dict(fields)),
        catalog_key="techniques",
    )


def sync_artifact_set_by_name(**fields) -> dict[str, Any]:
    return _sync_named_entity(
        XiuxianArtifactSet,
        serialize_artifact_set,
        _normalize_artifact_set_fields(dict(fields)),
        catalog_key="artifact-sets",
    )


def delete_artifact(artifact_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianArtifact).filter(XiuxianArtifact.id == artifact_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "artifacts")
        session.commit()
        return True


def delete_pill(pill_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianPill).filter(XiuxianPill.id == pill_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "pills")
        session.commit()
        return True


def _sanitize_removed_pill_reward_config(raw: Any, removed_ids: set[int]) -> dict[str, Any]:
    payload = _sanitize_json_value(raw) or {}
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items")
    if not isinstance(items, list):
        return payload
    sanitized_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or item.get("item_kind") or "").strip()
        ref_id = int(item.get("ref_id") or item.get("item_ref_id") or 0)
        if kind == "pill" and ref_id in removed_ids:
            continue
        sanitized_items.append(_sanitize_json_value(item))
    payload["items"] = sanitized_items
    return payload


def _sanitize_removed_pill_event_pool(raw: Any, removed_ids: set[int]) -> Any:
    rows = _sanitize_json_value(raw)
    if not isinstance(rows, list):
        return rows
    sanitized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            sanitized_rows.append(row)
            continue
        payload = dict(_sanitize_json_value(row) or {})
        reward_kind = str(payload.get("bonus_reward_kind") or "").strip()
        reward_ref_id = int(payload.get("bonus_reward_ref_id") or 0)
        if reward_kind == "pill" and reward_ref_id in removed_ids:
            payload["bonus_reward_kind"] = None
            payload["bonus_reward_ref_id"] = None
            payload["bonus_quantity_min"] = 1
            payload["bonus_quantity_max"] = 1
            payload["bonus_chance"] = 0
        sanitized_rows.append(payload)
    return sanitized_rows


def _sanitize_removed_pill_reward_pool(raw: Any, removed_ids: set[int]) -> Any:
    rows = _sanitize_json_value(raw)
    if not isinstance(rows, list):
        return rows
    return [
        row for row in rows
        if not (
            isinstance(row, dict)
            and str(row.get("item_kind") or "").strip() == "pill"
            and int(row.get("item_ref_id") or 0) in removed_ids
        )
    ]


def _sanitize_removed_pill_encounter_reward(raw: Any, removed_ids: set[int]) -> dict[str, Any]:
    payload = _sanitize_json_value(raw) or {}
    if not isinstance(payload, dict):
        return {}
    reward_kind = str(payload.get("reward_item_kind") or "").strip()
    reward_ref_id = int(payload.get("reward_item_ref_id") or 0)
    if reward_kind == "pill" and reward_ref_id in removed_ids:
        payload["reward_item_kind"] = None
        payload["reward_item_ref_id"] = None
        payload["reward_item_quantity"] = 0
    return payload


def purge_removed_pill_types() -> dict[str, int]:
    removed_types = tuple(sorted(str(item).strip() for item in REMOVED_PILL_TYPES if str(item).strip()))
    if not removed_types:
        return {"pill_count": 0}

    with Session() as session:
        rows = (
            session.query(XiuxianPill)
            .filter(XiuxianPill.pill_type.in_(removed_types))
            .all()
        )
        pill_ids = {int(row.id) for row in rows if int(getattr(row, "id", 0) or 0) > 0}
        if not pill_ids:
            return {"pill_count": 0}

        affected_tgs = {
            int(tg)
            for (tg,) in (
                session.query(XiuxianPillInventory.tg)
                .filter(XiuxianPillInventory.pill_id.in_(pill_ids))
                .distinct()
                .all()
            )
            if int(tg or 0) > 0
        }
        listing_owner_tgs = {
            int(owner_tg)
            for (owner_tg,) in (
                session.query(XiuxianShopItem.owner_tg)
                .filter(
                    XiuxianShopItem.item_kind == "pill",
                    XiuxianShopItem.item_ref_id.in_(pill_ids),
                    XiuxianShopItem.owner_tg.isnot(None),
                )
                .distinct()
                .all()
            )
            if int(owner_tg or 0) > 0
        }
        listing_owner_tgs.update(
            {
                int(owner_tg)
                for (owner_tg,) in (
                    session.query(XiuxianAuctionItem.owner_tg)
                    .filter(
                        XiuxianAuctionItem.item_kind == "pill",
                        XiuxianAuctionItem.item_ref_id.in_(pill_ids),
                        XiuxianAuctionItem.owner_tg.isnot(None),
                    )
                    .distinct()
                    .all()
                )
                if int(owner_tg or 0) > 0
            }
        )

        shop_deleted = session.query(XiuxianShopItem).filter(
            XiuxianShopItem.item_kind == "pill",
            XiuxianShopItem.item_ref_id.in_(pill_ids),
        ).delete(synchronize_session=False)
        auction_deleted = session.query(XiuxianAuctionItem).filter(
            XiuxianAuctionItem.item_kind == "pill",
            XiuxianAuctionItem.item_ref_id.in_(pill_ids),
        ).delete(synchronize_session=False)
        treasury_deleted = session.query(XiuxianSectTreasuryItem).filter(
            XiuxianSectTreasuryItem.item_kind == "pill",
            XiuxianSectTreasuryItem.item_ref_id.in_(pill_ids),
        ).delete(synchronize_session=False)
        inventory_deleted = session.query(XiuxianPillInventory).filter(
            XiuxianPillInventory.pill_id.in_(pill_ids),
        ).delete(synchronize_session=False)
        recipe_deleted = session.query(XiuxianRecipe).filter(
            XiuxianRecipe.result_kind == "pill",
            XiuxianRecipe.result_ref_id.in_(pill_ids),
        ).delete(synchronize_session=False)
        scene_drop_deleted = session.query(XiuxianSceneDrop).filter(
            XiuxianSceneDrop.reward_kind == "pill",
            XiuxianSceneDrop.reward_ref_id.in_(pill_ids),
        ).delete(synchronize_session=False)
        exploration_updated = session.query(XiuxianExploration).filter(
            XiuxianExploration.reward_kind == "pill",
            XiuxianExploration.reward_ref_id.in_(pill_ids),
        ).update(
            {
                "reward_kind": None,
                "reward_ref_id": None,
                "reward_quantity": 0,
                "updated_at": utcnow(),
            },
            synchronize_session=False,
        )
        task_required_updated = session.query(XiuxianTask).filter(
            XiuxianTask.required_item_kind == "pill",
            XiuxianTask.required_item_ref_id.in_(pill_ids),
        ).update(
            {
                "required_item_kind": None,
                "required_item_ref_id": None,
                "required_item_quantity": 0,
                "updated_at": utcnow(),
            },
            synchronize_session=False,
        )
        task_reward_updated = session.query(XiuxianTask).filter(
            XiuxianTask.reward_item_kind == "pill",
            XiuxianTask.reward_item_ref_id.in_(pill_ids),
        ).update(
            {
                "reward_item_kind": None,
                "reward_item_ref_id": None,
                "reward_item_quantity": 0,
                "updated_at": utcnow(),
            },
            synchronize_session=False,
        )
        encounter_updated = session.query(XiuxianEncounterTemplate).filter(
            XiuxianEncounterTemplate.reward_item_kind == "pill",
            XiuxianEncounterTemplate.reward_item_ref_id.in_(pill_ids),
        ).update(
            {
                "reward_item_kind": None,
                "reward_item_ref_id": None,
                "reward_item_quantity_min": 1,
                "reward_item_quantity_max": 1,
                "updated_at": utcnow(),
            },
            synchronize_session=False,
        )

        achievement_updated = 0
        for achievement in session.query(XiuxianAchievement).all():
            current_config = _sanitize_json_value(achievement.reward_config) or {}
            sanitized_config = _sanitize_removed_pill_reward_config(current_config, pill_ids)
            if sanitized_config != current_config:
                achievement.reward_config = sanitized_config
                achievement.updated_at = utcnow()
                achievement_updated += 1

        scene_updated = 0
        for scene in session.query(XiuxianScene).all():
            current_pool = _sanitize_json_value(scene.event_pool) or []
            sanitized_pool = _sanitize_removed_pill_event_pool(current_pool, pill_ids)
            if sanitized_pool != current_pool:
                scene.event_pool = sanitized_pool
                scene.updated_at = utcnow()
                scene_updated += 1

        encounter_instance_updated = 0
        for instance in session.query(XiuxianEncounterInstance).all():
            current_reward = _sanitize_json_value(instance.reward_payload) or {}
            sanitized_reward = _sanitize_removed_pill_encounter_reward(current_reward, pill_ids)
            if sanitized_reward != current_reward:
                instance.reward_payload = sanitized_reward
                instance.updated_at = utcnow()
                encounter_instance_updated += 1

        settings_updated = 0
        for setting in session.query(XiuxianSetting).filter(
            XiuxianSetting.setting_key.in_(("gambling_reward_pool",))
        ).all():
            current_value = _sanitize_json_value(setting.setting_value)
            sanitized_value = _sanitize_removed_pill_reward_pool(current_value, pill_ids)
            if sanitized_value != current_value:
                setting.setting_value = sanitized_value
                settings_updated += 1
        if settings_updated:
            _queue_settings_cache_invalidation(session)

        pill_count = len(pill_ids)
        for row in rows:
            session.delete(row)

        if affected_tgs or listing_owner_tgs:
            _queue_profile_cache_invalidation(session, *(affected_tgs | listing_owner_tgs))
            _queue_user_view_cache_invalidation(session, *(affected_tgs | listing_owner_tgs))
        _queue_catalog_cache_invalidation(session, "pills", "shop-items", "recipes", "scenes")
        session.commit()

    return {
        "pill_count": pill_count,
        "shop_count": int(shop_deleted or 0),
        "auction_count": int(auction_deleted or 0),
        "treasury_count": int(treasury_deleted or 0),
        "inventory_count": int(inventory_deleted or 0),
        "recipe_count": int(recipe_deleted or 0),
        "scene_drop_count": int(scene_drop_deleted or 0),
        "exploration_count": int(exploration_updated or 0),
        "task_required_count": int(task_required_updated or 0),
        "task_reward_count": int(task_reward_updated or 0),
        "encounter_count": int(encounter_updated or 0),
        "encounter_instance_count": int(encounter_instance_updated or 0),
        "achievement_count": int(achievement_updated or 0),
        "scene_count": int(scene_updated or 0),
        "settings_count": int(settings_updated or 0),
    }


def delete_talisman(talisman_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianTalisman).filter(XiuxianTalisman.id == talisman_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "talismans")
        session.commit()
        return True


def delete_technique(technique_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianTechnique).filter(XiuxianTechnique.id == technique_id).first()
        if row is None:
            return False
        session.query(XiuxianProfile).filter(XiuxianProfile.current_technique_id == technique_id).update(
            {"current_technique_id": None, "updated_at": utcnow()},
            synchronize_session=False,
        )
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "techniques")
        session.commit()
        return True


def delete_artifact_set(artifact_set_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianArtifactSet).filter(XiuxianArtifactSet.id == artifact_set_id).first()
        if row is None:
            return False
        session.query(XiuxianArtifact).filter(XiuxianArtifact.artifact_set_id == artifact_set_id).update(
            {"artifact_set_id": None, "updated_at": utcnow()},
            synchronize_session=False,
        )
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "artifact-sets", "artifacts")
        session.commit()
        return True


def _artifact_unique_item_enabled(artifact: XiuxianArtifact | dict[str, Any] | None) -> bool:
    if artifact is None:
        return False
    if isinstance(artifact, dict):
        return bool(artifact.get("unique_item"))
    return bool(getattr(artifact, "unique_item", False))


def _unique_artifact_holder_tg_in_session(
    session: OrmSession,
    artifact_id: int,
    *,
    exclude_tgs: set[int] | None = None,
) -> int | None:
    query = (
        session.query(XiuxianArtifactInventory)
        .filter(
            XiuxianArtifactInventory.artifact_id == int(artifact_id),
            XiuxianArtifactInventory.quantity > 0,
        )
        .with_for_update()
    )
    excluded = {int(tg_value) for tg_value in (exclude_tgs or set()) if int(tg_value or 0) > 0}
    if excluded:
        query = query.filter(~XiuxianArtifactInventory.tg.in_(excluded))
    row = query.order_by(XiuxianArtifactInventory.id.asc()).first()
    return int(row.tg or 0) if row is not None else None


def assert_artifact_receivable_by_user(
    tg: int,
    artifact_id: int,
    *,
    allow_existing_owner: bool = False,
    exclude_owner_tgs: set[int] | None = None,
) -> dict[str, Any]:
    with Session() as session:
        artifact = (
            session.query(XiuxianArtifact)
            .filter(XiuxianArtifact.id == int(artifact_id))
            .with_for_update()
            .first()
        )
        if artifact is None:
            raise ValueError("未找到目标法宝。")
        if not _artifact_unique_item_enabled(artifact):
            return serialize_artifact(artifact) or {}

        holder_tg = _unique_artifact_holder_tg_in_session(
            session,
            int(artifact_id),
            exclude_tgs={int(tg), *(exclude_owner_tgs or set())},
        )
        if holder_tg is not None:
            raise ValueError(f"唯一法宝【{artifact.name}】已被其他人获得，无法再次获取。")

        owned_row = (
            session.query(XiuxianArtifactInventory)
            .filter(
                XiuxianArtifactInventory.tg == int(tg),
                XiuxianArtifactInventory.artifact_id == int(artifact_id),
                XiuxianArtifactInventory.quantity > 0,
            )
            .with_for_update()
            .first()
        )
        if owned_row is not None and not allow_existing_owner:
            raise ValueError(f"你已经拥有唯一法宝【{artifact.name}】了。")
        return serialize_artifact(artifact) or {}


def _grant_artifact_inventory_in_session(
    session: OrmSession,
    tg: int,
    artifact_id: int,
    quantity: int = 1,
    *,
    reject_if_owned: bool = False,
    strict_quantity: bool = False,
    exclude_owner_tgs: set[int] | None = None,
) -> tuple[XiuxianArtifact, XiuxianArtifactInventory, int]:
    tg_value = int(tg)
    artifact_value = int(artifact_id)
    artifact = (
        session.query(XiuxianArtifact)
        .filter(XiuxianArtifact.id == artifact_value)
        .with_for_update()
        .first()
    )
    if artifact is None:
        raise ValueError("未找到目标法宝。")

    requested = max(int(quantity or 0), 1)
    row = next(
        (
            pending
            for pending in session.new
            if isinstance(pending, XiuxianArtifactInventory)
            and int(getattr(pending, "tg", 0) or 0) == tg_value
            and int(getattr(pending, "artifact_id", 0) or 0) == artifact_value
        ),
        None,
    )
    if row is None:
        row = (
        session.query(XiuxianArtifactInventory)
        .filter(
            XiuxianArtifactInventory.tg == tg_value,
            XiuxianArtifactInventory.artifact_id == artifact_value,
        )
        .with_for_update()
        .first()
        )
    if row is None:
        row = XiuxianArtifactInventory(tg=tg_value, artifact_id=artifact_value, quantity=0, bound_quantity=0)
        session.add(row)

    if _artifact_unique_item_enabled(artifact):
        if strict_quantity and requested > 1:
            raise ValueError(f"唯一法宝【{artifact.name}】每次只能获取 1 件。")
        holder_tg = _unique_artifact_holder_tg_in_session(
            session,
            artifact_value,
            exclude_tgs={tg_value, *(exclude_owner_tgs or set())},
        )
        if holder_tg is not None:
            raise ValueError(f"唯一法宝【{artifact.name}】已被其他人获得，无法再次获取。")
        already_owned = max(int(row.quantity or 0), 0)
        if reject_if_owned and already_owned > 0:
            raise ValueError(f"你已经拥有唯一法宝【{artifact.name}】了。")
        actual_granted = 0 if already_owned > 0 else 1
        row.quantity = max(already_owned, 1)
    else:
        row.quantity = max(int(row.quantity or 0), 0) + requested
        actual_granted = requested

    row.bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
    row.updated_at = utcnow()
    return artifact, row, actual_granted


def grant_artifact_to_user(tg: int, artifact_id: int, quantity: int = 1) -> dict[str, Any]:
    with Session() as session:
        artifact, row, _ = _grant_artifact_inventory_in_session(session, int(tg), int(artifact_id), int(quantity))
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return {
            "artifact": serialize_artifact(artifact),
            "quantity": max(int(row.quantity or 0), 0),
            "bound_quantity": int(row.bound_quantity or 0),
        }


def grant_pill_to_user(tg: int, pill_id: int, quantity: int = 1) -> dict[str, Any]:
    with Session() as session:
        row = (
            session.query(XiuxianPillInventory)
            .filter(
                XiuxianPillInventory.tg == tg,
                XiuxianPillInventory.pill_id == pill_id,
            )
            .first()
        )
        if row is None:
            row = XiuxianPillInventory(tg=tg, pill_id=pill_id, quantity=0)
            session.add(row)
        row.quantity += max(int(quantity), 1)
        row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        pill = session.query(XiuxianPill).filter(XiuxianPill.id == pill_id).first()
        return {
            "pill": serialize_pill(pill),
            "quantity": row.quantity,
        }


def grant_talisman_to_user(tg: int, talisman_id: int, quantity: int = 1) -> dict[str, Any]:
    with Session() as session:
        row = (
            session.query(XiuxianTalismanInventory)
            .filter(
                XiuxianTalismanInventory.tg == tg,
                XiuxianTalismanInventory.talisman_id == talisman_id,
            )
            .first()
        )
        if row is None:
            row = XiuxianTalismanInventory(tg=tg, talisman_id=talisman_id, quantity=0)
            session.add(row)
        row.quantity += max(int(quantity), 1)
        row.bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
        row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        talisman = session.query(XiuxianTalisman).filter(XiuxianTalisman.id == talisman_id).first()
        return {
            "talisman": serialize_talisman(talisman),
            "quantity": row.quantity,
            "bound_quantity": int(row.bound_quantity or 0),
        }


def _shared_inventory_owner_tgs(session: Session, tg: int, *, for_update: bool = False) -> list[int]:
    owner_tgs = _shared_profile_tgs(session, tg, for_update=for_update)
    return [int(item) for item in owner_tgs if int(item) > 0]


def _ordered_owner_rows(session: Session, model_cls, tg: int, ref_field: str, ref_id: int) -> list[Any]:
    owner_tgs = _shared_inventory_owner_tgs(session, tg, for_update=True)
    if not owner_tgs:
        return []
    ref_column = getattr(model_cls, ref_field)
    rows = (
        session.query(model_cls)
        .filter(model_cls.tg.in_(owner_tgs), ref_column == int(ref_id))
        .with_for_update()
        .all()
    )
    row_map = {int(row.tg or 0): row for row in rows}
    return [row_map[item] for item in owner_tgs if item in row_map]


def list_user_artifacts(tg: int) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            owner_tgs = _shared_inventory_owner_tgs(session, actor_tg)
            if not owner_tgs:
                return []
            rows = (
                session.query(XiuxianArtifactInventory, XiuxianArtifact)
                .join(XiuxianArtifact, XiuxianArtifact.id == XiuxianArtifactInventory.artifact_id)
                .filter(XiuxianArtifactInventory.tg.in_(owner_tgs))
                .order_by(XiuxianArtifact.id.desc())
                .all()
            )
            equipped_counts: dict[int, int] = {}
            for equipped in (
                session.query(XiuxianEquippedArtifact)
                .filter(XiuxianEquippedArtifact.tg.in_(owner_tgs))
                .all()
            ):
                artifact_id = int(equipped.artifact_id or 0)
                if artifact_id <= 0:
                    continue
                equipped_counts[artifact_id] = equipped_counts.get(artifact_id, 0) + 1
            payload_map: dict[int, dict[str, Any]] = {}
            for inventory, artifact in rows:
                artifact_id = int(inventory.artifact_id or 0)
                entry = payload_map.get(artifact_id)
                if entry is None:
                    entry = {
                        "quantity": 0,
                        "bound_quantity": 0,
                        "equipped_quantity": equipped_counts.get(artifact_id, 0),
                        "artifact": serialize_artifact(artifact),
                    }
                    payload_map[artifact_id] = entry
                quantity = max(int(inventory.quantity or 0), 0)
                entry["quantity"] += quantity
                entry["bound_quantity"] += max(min(int(inventory.bound_quantity or 0), quantity), 0)
            payload = list(payload_map.values())
            return sorted(
                payload,
                key=lambda row: _named_quality_sort_key((row.get("artifact") or {}), "rarity_level"),
            )

    return _load_user_view_cache(actor_tg, "artifacts", loader=_loader)


def list_equipped_artifacts(tg: int) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianEquippedArtifact, XiuxianArtifact)
                .join(XiuxianArtifact, XiuxianArtifact.id == XiuxianEquippedArtifact.artifact_id)
                .filter(XiuxianEquippedArtifact.tg == actor_tg)
                .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
                .all()
            )
            return [
                {
                    "slot": equipped.slot,
                    "artifact": serialize_artifact(artifact),
                }
                for equipped, artifact in rows
            ]

    return _load_user_view_cache(actor_tg, "equipped-artifacts", loader=_loader)


def reindex_equipped_artifact_slots_in_session(
    session: OrmSession,
    tg: int,
    rows: list[XiuxianEquippedArtifact] | None = None,
) -> list[XiuxianEquippedArtifact]:
    actor_tg = int(tg or 0)
    ordered_rows = list(rows) if rows is not None else (
        session.query(XiuxianEquippedArtifact)
        .filter(XiuxianEquippedArtifact.tg == actor_tg)
        .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
        .all()
    )
    if not ordered_rows:
        return []

    max_existing_slot = (
        session.query(XiuxianEquippedArtifact.slot)
        .filter(XiuxianEquippedArtifact.tg == actor_tg)
        .order_by(XiuxianEquippedArtifact.slot.desc())
        .limit(1)
        .scalar()
    )
    temp_slot_base = max(int(max_existing_slot or 0), len(ordered_rows)) + len(ordered_rows) + 1

    staged = False
    for offset, row in enumerate(ordered_rows):
        temp_slot = temp_slot_base + offset
        if int(row.slot or 0) == temp_slot:
            continue
        row.slot = temp_slot
        row.updated_at = utcnow()
        staged = True
    if staged:
        session.flush()

    reindexed = False
    for index, row in enumerate(ordered_rows, start=1):
        if int(row.slot or 0) == index:
            continue
        row.slot = index
        row.updated_at = utcnow()
        reindexed = True
    if reindexed:
        session.flush()

    return ordered_rows


def plunder_random_artifact_to_user(receiver_tg: int, owner_tg: int) -> dict[str, Any] | None:
    from .activities import _starter_artifact_id_in_session, _starter_artifact_protection_active_in_session

    if receiver_tg == owner_tg:
        raise ValueError("不能从自己身上掠夺法宝。")

    with Session() as session:
        owner_profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == owner_tg).with_for_update().first()
        receiver_profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == receiver_tg).with_for_update().first()
        if owner_profile is None or receiver_profile is None:
            return None

        owner_rows = (
            session.query(XiuxianArtifactInventory)
            .filter(XiuxianArtifactInventory.tg == owner_tg)
            .with_for_update()
            .all()
        )
        if not owner_rows:
            return None

        starter_artifact_id = _starter_artifact_id_in_session(session)
        starter_protection_active = bool(starter_artifact_id) and _starter_artifact_protection_active_in_session(session, owner_tg)
        equipped_rows = (
            session.query(XiuxianEquippedArtifact)
            .filter(XiuxianEquippedArtifact.tg == owner_tg)
            .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
            .with_for_update()
            .all()
        )
        receiver_rows = (
            session.query(XiuxianArtifactInventory)
            .filter(XiuxianArtifactInventory.tg == receiver_tg, XiuxianArtifactInventory.quantity > 0)
            .with_for_update()
            .all()
        )
        receiver_owned_ids = {int(row.artifact_id or 0) for row in receiver_rows if int(row.quantity or 0) > 0}
        artifact_map = {
            int(item.id or 0): item
            for item in (
                session.query(XiuxianArtifact)
                .filter(XiuxianArtifact.id.in_({int(row.artifact_id or 0) for row in owner_rows if int(row.artifact_id or 0) > 0}))
                .with_for_update()
                .all()
            )
        }
        equipped_count_map: dict[int, int] = {}
        for row in equipped_rows:
            artifact_id = int(row.artifact_id or 0)
            equipped_count_map[artifact_id] = equipped_count_map.get(artifact_id, 0) + 1

        weighted_ids: list[int] = []
        for row in owner_rows:
            total_quantity = int(row.quantity or 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), total_quantity), 0)
            protected_quantity = min(total_quantity, bound_quantity + equipped_count_map.get(int(row.artifact_id), 0))
            if starter_protection_active and int(row.artifact_id or 0) == int(starter_artifact_id or 0):
                protected_quantity = max(protected_quantity, min(total_quantity, 1))
            artifact_payload = artifact_map.get(int(row.artifact_id or 0))
            if _artifact_unique_item_enabled(artifact_payload) and int(row.artifact_id or 0) in receiver_owned_ids:
                continue
            weighted_ids.extend([int(row.artifact_id)] * max(total_quantity - protected_quantity, 0))
        if not weighted_ids:
            return None

        artifact_id = random.choice(weighted_ids)
        owner_row = next((row for row in owner_rows if int(row.artifact_id) == artifact_id), None)
        if owner_row is None:
            return None

        owner_row.quantity = max(int(owner_row.quantity or 0) - 1, 0)
        owner_row.bound_quantity = max(min(int(owner_row.bound_quantity or 0), int(owner_row.quantity or 0)), 0)
        owner_row.updated_at = utcnow()

        if int(owner_row.quantity or 0) <= 0:
            session.delete(owner_row)

        _, receiver_row, _ = _grant_artifact_inventory_in_session(
            session,
            int(receiver_tg),
            int(artifact_id),
            1,
            reject_if_owned=False,
        )

        refreshed_equipped = (
            session.query(XiuxianEquippedArtifact)
            .filter(XiuxianEquippedArtifact.tg == owner_tg)
            .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
            .all()
        )
        refreshed_equipped = reindex_equipped_artifact_slots_in_session(session, owner_tg, refreshed_equipped)

        owner_profile.current_artifact_id = refreshed_equipped[0].artifact_id if refreshed_equipped else None
        owner_profile.updated_at = utcnow()
        receiver_profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, owner_tg, receiver_tg)
        _queue_user_view_cache_invalidation(session, owner_tg, receiver_tg)

        artifact = artifact_map.get(int(artifact_id)) or session.query(XiuxianArtifact).filter(XiuxianArtifact.id == artifact_id).first()
        owner_remaining = max(int(owner_row.quantity or 0), 0)
        receiver_quantity = int(receiver_row.quantity or 0)
        session.commit()
        return {
            "artifact": serialize_artifact(artifact),
            "was_equipped": False,
            "owner_remaining": owner_remaining,
            "receiver_quantity": receiver_quantity,
        }


def list_user_pills(tg: int) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            owner_tgs = _shared_inventory_owner_tgs(session, actor_tg)
            if not owner_tgs:
                return []
            rows = (
                session.query(XiuxianPillInventory, XiuxianPill)
                .join(XiuxianPill, XiuxianPill.id == XiuxianPillInventory.pill_id)
                .filter(XiuxianPillInventory.tg.in_(owner_tgs))
                .order_by(XiuxianPill.id.desc())
                .all()
            )
            payload_map: dict[int, dict[str, Any]] = {}
            for inventory, pill in rows:
                pill_id = int(inventory.pill_id or 0)
                entry = payload_map.get(pill_id)
                if entry is None:
                    entry = {"quantity": 0, "pill": serialize_pill(pill)}
                    payload_map[pill_id] = entry
                entry["quantity"] += max(int(inventory.quantity or 0), 0)
            payload = list(payload_map.values())
            return sorted(
                payload,
                key=lambda row: _named_quality_sort_key((row.get("pill") or {}), "rarity_level"),
            )

    return _load_user_view_cache(actor_tg, "pills", loader=_loader)


def list_user_talismans(tg: int) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            owner_tgs = _shared_inventory_owner_tgs(session, actor_tg)
            if not owner_tgs:
                return []
            rows = (
                session.query(XiuxianTalismanInventory, XiuxianTalisman)
                .join(XiuxianTalisman, XiuxianTalisman.id == XiuxianTalismanInventory.talisman_id)
                .filter(XiuxianTalismanInventory.tg.in_(owner_tgs))
                .order_by(XiuxianTalisman.id.desc())
                .all()
            )
            payload_map: dict[int, dict[str, Any]] = {}
            for inventory, talisman in rows:
                talisman_id = int(inventory.talisman_id or 0)
                entry = payload_map.get(talisman_id)
                if entry is None:
                    entry = {
                        "quantity": 0,
                        "bound_quantity": 0,
                        "talisman": serialize_talisman(talisman),
                    }
                    payload_map[talisman_id] = entry
                quantity = max(int(inventory.quantity or 0), 0)
                entry["quantity"] += quantity
                entry["bound_quantity"] += max(min(int(inventory.bound_quantity or 0), quantity), 0)
            payload = list(payload_map.values())
            return sorted(
                payload,
                key=lambda row: _named_quality_sort_key((row.get("talisman") or {}), "rarity_level"),
            )

    return _load_user_view_cache(actor_tg, "talismans", loader=_loader)


def consume_user_pill(tg: int, pill_id: int, quantity: int = 1) -> bool:
    with Session() as session:
        remaining = max(int(quantity or 0), 1)
        rows = _ordered_owner_rows(session, XiuxianPillInventory, tg, "pill_id", pill_id)
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        if total_quantity < remaining:
            return False

        now = utcnow()
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
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def consume_user_talisman(tg: int, talisman_id: int, quantity: int = 1) -> bool:
    with Session() as session:
        remaining = max(int(quantity or 0), 1)
        rows = _ordered_owner_rows(session, XiuxianTalismanInventory, tg, "talisman_id", talisman_id)
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        if total_quantity < remaining:
            return False

        now = utcnow()
        for row in rows:
            if remaining <= 0:
                break
            available = max(int(row.quantity or 0), 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.quantity = available - delta
            row.bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
            row.updated_at = now
            remaining -= delta
            if row.quantity <= 0:
                session.delete(row)
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def admin_set_user_artifact_inventory(
    tg: int,
    artifact_id: int,
    quantity: int,
    bound_quantity: int | None = None,
) -> dict[str, Any]:
    target_quantity = max(int(quantity or 0), 0)
    desired_bound = max(int(bound_quantity or 0), 0) if bound_quantity is not None else None
    with Session() as session:
        artifact = session.query(XiuxianArtifact).filter(XiuxianArtifact.id == artifact_id).first()
        if artifact is None:
            raise ValueError("artifact not found")
        if _artifact_unique_item_enabled(artifact) and target_quantity > 1:
            raise ValueError(f"唯一法宝【{artifact.name}】的库存不能超过 1。")
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None:
            profile = XiuxianProfile(tg=tg)
            session.add(profile)
            session.flush()
        if _artifact_unique_item_enabled(artifact) and target_quantity > 0:
            holder_tg = _unique_artifact_holder_tg_in_session(session, int(artifact_id), exclude_tgs={int(tg)})
            if holder_tg is not None:
                raise ValueError(f"唯一法宝【{artifact.name}】已被其他人获得，无法直接发放。")
        row = (
            session.query(XiuxianArtifactInventory)
            .filter(XiuxianArtifactInventory.tg == tg, XiuxianArtifactInventory.artifact_id == artifact_id)
            .with_for_update()
            .first()
        )
        equipped_rows = (
            session.query(XiuxianEquippedArtifact)
            .filter(XiuxianEquippedArtifact.tg == tg, XiuxianEquippedArtifact.artifact_id == artifact_id)
            .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
            .with_for_update()
            .all()
        )
        if target_quantity < len(equipped_rows):
            for equipped_row in equipped_rows[target_quantity:]:
                session.delete(equipped_row)
            session.flush()
            equipped_rows = equipped_rows[:target_quantity]
        if target_quantity <= 0:
            if row is not None:
                session.delete(row)
        else:
            if row is None:
                row = XiuxianArtifactInventory(tg=tg, artifact_id=artifact_id, quantity=0, bound_quantity=0)
                session.add(row)
            row.quantity = target_quantity
            max_bound = max(target_quantity - len(equipped_rows), 0)
            applied_bound = int(row.bound_quantity or 0) if desired_bound is None else desired_bound
            row.bound_quantity = max(min(applied_bound, max_bound), 0)
            row.updated_at = utcnow()
        refreshed_equipped = (
            session.query(XiuxianEquippedArtifact)
            .filter(XiuxianEquippedArtifact.tg == tg)
            .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
            .all()
        )
        refreshed_equipped = reindex_equipped_artifact_slots_in_session(session, tg, refreshed_equipped)
        profile.current_artifact_id = refreshed_equipped[0].artifact_id if refreshed_equipped else None
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        applied_bound = 0
        if target_quantity > 0:
            refreshed_row = (
                session.query(XiuxianArtifactInventory)
                .filter(XiuxianArtifactInventory.tg == tg, XiuxianArtifactInventory.artifact_id == artifact_id)
                .first()
            )
            applied_bound = int(refreshed_row.bound_quantity or 0) if refreshed_row is not None else 0
        return {
            "artifact": serialize_artifact(artifact),
            "quantity": target_quantity,
            "bound_quantity": applied_bound,
            "equipped_count": len([row for row in refreshed_equipped if int(row.artifact_id) == int(artifact_id)]),
        }


def admin_set_user_pill_inventory(tg: int, pill_id: int, quantity: int) -> dict[str, Any]:
    target_quantity = max(int(quantity or 0), 0)
    with Session() as session:
        pill = session.query(XiuxianPill).filter(XiuxianPill.id == pill_id).first()
        if pill is None:
            raise ValueError("pill not found")
        row = (
            session.query(XiuxianPillInventory)
            .filter(XiuxianPillInventory.tg == tg, XiuxianPillInventory.pill_id == pill_id)
            .with_for_update()
            .first()
        )
        if target_quantity <= 0:
            if row is not None:
                session.delete(row)
        else:
            if row is None:
                row = XiuxianPillInventory(tg=tg, pill_id=pill_id, quantity=0)
                session.add(row)
            row.quantity = target_quantity
            row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return {
            "pill": serialize_pill(pill),
            "quantity": target_quantity,
        }


def admin_set_user_talisman_inventory(
    tg: int,
    talisman_id: int,
    quantity: int,
    bound_quantity: int | None = None,
) -> dict[str, Any]:
    target_quantity = max(int(quantity or 0), 0)
    with Session() as session:
        talisman = session.query(XiuxianTalisman).filter(XiuxianTalisman.id == talisman_id).first()
        if talisman is None:
            raise ValueError("talisman not found")
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None:
            profile = XiuxianProfile(tg=tg)
            session.add(profile)
            session.flush()
        row = (
            session.query(XiuxianTalismanInventory)
            .filter(XiuxianTalismanInventory.tg == tg, XiuxianTalismanInventory.talisman_id == talisman_id)
            .with_for_update()
            .first()
        )
        desired_bound = max(int(bound_quantity or 0), 0) if bound_quantity is not None else (int(row.bound_quantity or 0) if row is not None else 0)
        if target_quantity <= 0:
            if row is not None:
                session.delete(row)
            if int(profile.active_talisman_id or 0) == int(talisman_id):
                profile.active_talisman_id = None
        else:
            if row is None:
                row = XiuxianTalismanInventory(tg=tg, talisman_id=talisman_id, quantity=0, bound_quantity=0)
                session.add(row)
            row.quantity = target_quantity
            row.bound_quantity = max(min(desired_bound, target_quantity), 0)
            row.updated_at = utcnow()
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return {
            "talisman": serialize_talisman(talisman),
            "quantity": target_quantity,
            "bound_quantity": 0 if target_quantity <= 0 else max(min(desired_bound, target_quantity), 0),
            "active": int(profile.active_talisman_id or 0) == int(talisman_id),
        }


def admin_set_user_material_inventory(tg: int, material_id: int, quantity: int) -> dict[str, Any]:
    target_quantity = max(int(quantity or 0), 0)
    with Session() as session:
        material = session.query(XiuxianMaterial).filter(XiuxianMaterial.id == material_id).first()
        if material is None:
            raise ValueError("material not found")
        row = (
            session.query(XiuxianMaterialInventory)
            .filter(XiuxianMaterialInventory.tg == tg, XiuxianMaterialInventory.material_id == material_id)
            .with_for_update()
            .first()
        )
        if target_quantity <= 0:
            if row is not None:
                session.delete(row)
        else:
            if row is None:
                row = XiuxianMaterialInventory(tg=tg, material_id=material_id, quantity=0)
                session.add(row)
            row.quantity = target_quantity
            row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return {
            "material": serialize_material(material),
            "quantity": target_quantity,
        }


def use_user_artifact_listing_stock(tg: int, artifact_id: int, quantity: int = 1) -> bool:
    from .activities import _starter_artifact_id_in_session, release_starter_artifact_protection

    with Session() as session:
        remaining = max(int(quantity or 0), 1)
        rows = _ordered_owner_rows(session, XiuxianArtifactInventory, tg, "artifact_id", artifact_id)
        if not rows:
            return False
        starter_artifact_id = _starter_artifact_id_in_session(session)
        owner_tgs = _shared_inventory_owner_tgs(session, tg, for_update=True)
        equipped_count = 0
        for _equipped in (
            session.query(XiuxianEquippedArtifact)
            .filter(
                XiuxianEquippedArtifact.tg.in_(owner_tgs),
                XiuxianEquippedArtifact.artifact_id == int(artifact_id),
            )
            .with_for_update()
            .all()
        ):
            equipped_count += 1
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        total_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        total_available = max(total_quantity - total_bound_quantity - equipped_count, 0)
        if total_available < remaining:
            return False

        now = utcnow()
        release_owner_tgs: set[int] = set()
        for row in rows:
            if remaining <= 0:
                break
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            available = max(quantity_value - bound_quantity, 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.quantity = quantity_value - delta
            row.bound_quantity = max(min(bound_quantity, int(row.quantity or 0)), 0)
            row.updated_at = now
            if delta > 0 and int(artifact_id or 0) == int(starter_artifact_id or 0):
                release_owner_tgs.add(int(row.tg or 0))
            remaining -= delta
            if row.quantity <= 0:
                session.delete(row)
        _queue_user_view_cache_invalidation(session, tg, *release_owner_tgs)
        session.commit()
        for owner_tg in release_owner_tgs:
            release_starter_artifact_protection(
                owner_tg,
                reason="你将新手法宝用于上架出售或拍卖，此后它不再受新手保护，日后重修也不会再次补发。",
            )
        return True


def use_user_pill_listing_stock(tg: int, pill_id: int, quantity: int = 1) -> bool:
    with Session() as session:
        remaining = max(int(quantity or 0), 1)
        rows = _ordered_owner_rows(session, XiuxianPillInventory, tg, "pill_id", pill_id)
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        if total_quantity < remaining:
            return False

        now = utcnow()
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
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def use_user_material_listing_stock(tg: int, material_id: int, quantity: int = 1) -> bool:
    with Session() as session:
        remaining = max(int(quantity or 0), 1)
        rows = _ordered_owner_rows(session, XiuxianMaterialInventory, tg, "material_id", material_id)
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        if total_quantity < remaining:
            return False

        now = utcnow()
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
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def use_user_talisman_listing_stock(tg: int, talisman_id: int, quantity: int = 1) -> bool:
    with Session() as session:
        remaining = max(int(quantity or 0), 1)
        rows = _ordered_owner_rows(session, XiuxianTalismanInventory, tg, "talisman_id", talisman_id)
        if not rows:
            return False
        total_available = 0
        for row in rows:
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            total_available += max(quantity_value - bound_quantity, 0)
        if total_available < remaining:
            return False

        now = utcnow()
        for row in rows:
            if remaining <= 0:
                break
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            available = max(quantity_value - bound_quantity, 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.quantity = quantity_value - delta
            row.bound_quantity = max(min(bound_quantity, int(row.quantity or 0)), 0)
            row.updated_at = now
            remaining -= delta
            if row.quantity <= 0:
                session.delete(row)
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def bind_user_artifact(tg: int, artifact_id: int, quantity: int = 1) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    with Session() as session:
        rows = _ordered_owner_rows(session, XiuxianArtifactInventory, tg, "artifact_id", artifact_id)
        if not rows:
            raise ValueError("你的背包里没有这件法宝。")
        bindable_quantity = 0
        for row in rows:
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            bindable_quantity += max(quantity_value - bound_quantity, 0)
        if bindable_quantity < amount:
            raise ValueError("没有足够的未绑定法宝可供绑定。")
        remaining = amount
        now = utcnow()
        for row in rows:
            if remaining <= 0:
                break
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            available = max(quantity_value - bound_quantity, 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.bound_quantity = bound_quantity + delta
            row.updated_at = now
            remaining -= delta
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        total_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        return {
            "quantity": total_quantity,
            "bound_quantity": total_bound_quantity,
        }


def unbind_user_artifact(tg: int, artifact_id: int, cost: int, quantity: int = 1) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    unit_cost = max(int(cost or 0), 0)
    total_cost = unit_cost * amount
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        rows = _ordered_owner_rows(session, XiuxianArtifactInventory, tg, "artifact_id", artifact_id)
        if profile is None or not rows:
            raise ValueError("你的背包里没有这件法宝。")
        total_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        if total_bound_quantity < amount:
            raise ValueError("没有足够的已绑定法宝可供解绑。")
        if total_cost > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -total_cost,
                action_text="解绑法宝",
                allow_dead=False,
                apply_tribute=False,
            )
        remaining = amount
        now = utcnow()
        for row in rows:
            if remaining <= 0:
                break
            bound_quantity = max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            if bound_quantity <= 0:
                continue
            delta = min(bound_quantity, remaining)
            row.bound_quantity = bound_quantity - delta
            row.updated_at = now
            remaining -= delta
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        refreshed_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        return {
            "quantity": total_quantity,
            "bound_quantity": refreshed_bound_quantity,
            "cost": total_cost,
            "balance": get_shared_spiritual_stone_total(tg, session=session, for_update=False),
        }


def bind_user_talisman(tg: int, talisman_id: int, quantity: int = 1) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    with Session() as session:
        rows = _ordered_owner_rows(session, XiuxianTalismanInventory, tg, "talisman_id", talisman_id)
        if not rows:
            raise ValueError("你的背包里没有这张符箓。")
        bindable_quantity = 0
        for row in rows:
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            bindable_quantity += max(quantity_value - bound_quantity, 0)
        if bindable_quantity < amount:
            raise ValueError("没有足够的未绑定符箓可供绑定。")
        remaining = amount
        now = utcnow()
        for row in rows:
            if remaining <= 0:
                break
            quantity_value = max(int(row.quantity or 0), 0)
            bound_quantity = max(min(int(row.bound_quantity or 0), quantity_value), 0)
            available = max(quantity_value - bound_quantity, 0)
            if available <= 0:
                continue
            delta = min(available, remaining)
            row.bound_quantity = bound_quantity + delta
            row.updated_at = now
            remaining -= delta
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        total_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        return {
            "quantity": total_quantity,
            "bound_quantity": total_bound_quantity,
        }


def unbind_user_talisman(tg: int, talisman_id: int, cost: int, quantity: int = 1) -> dict[str, Any]:
    amount = max(int(quantity or 0), 1)
    unit_cost = max(int(cost or 0), 0)
    total_cost = unit_cost * amount
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        rows = _ordered_owner_rows(session, XiuxianTalismanInventory, tg, "talisman_id", talisman_id)
        if profile is None or not rows:
            raise ValueError("你的背包里没有这张符箓。")
        total_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        if total_bound_quantity < amount:
            raise ValueError("没有足够的已绑定符箓可供解绑。")
        if total_cost > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                -total_cost,
                action_text="解绑符箓",
                allow_dead=False,
                apply_tribute=False,
            )
        remaining = amount
        now = utcnow()
        for row in rows:
            if remaining <= 0:
                break
            bound_quantity = max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            if bound_quantity <= 0:
                continue
            delta = min(bound_quantity, remaining)
            row.bound_quantity = bound_quantity - delta
            row.updated_at = now
            remaining -= delta
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
        refreshed_bound_quantity = sum(
            max(min(int(row.bound_quantity or 0), max(int(row.quantity or 0), 0)), 0)
            for row in rows
        )
        return {
            "quantity": total_quantity,
            "bound_quantity": refreshed_bound_quantity,
            "cost": total_cost,
            "balance": get_shared_spiritual_stone_total(tg, session=session, for_update=False),
        }


def set_equipped_artifact(tg: int, artifact_id: int, equip_limit: int = 3) -> dict[str, Any] | None:
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None:
            return None
        artifact = session.query(XiuxianArtifact).filter(XiuxianArtifact.id == artifact_id).first()
        if artifact is None:
            return None

        equipped_rows = (
            session.query(XiuxianEquippedArtifact)
            .filter(XiuxianEquippedArtifact.tg == tg)
            .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
            .with_for_update()
            .all()
        )
        existing = next((row for row in equipped_rows if row.artifact_id == artifact_id), None)
        action = "equipped"
        replaced_artifact_id = None

        if existing is not None:
            session.delete(existing)
            session.flush()
            action = "unequipped"
        else:
            target_equip_slot = normalize_artifact_slot(artifact.equip_slot)
            slot_conflicts: list[XiuxianEquippedArtifact] = []
            for row in equipped_rows:
                equipped_artifact = session.query(XiuxianArtifact).filter(XiuxianArtifact.id == row.artifact_id).first()
                if equipped_artifact and normalize_artifact_slot(equipped_artifact.equip_slot) == target_equip_slot:
                    slot_conflicts.append(row)
            if slot_conflicts:
                replaced_artifact_id = int(slot_conflicts[0].artifact_id)
                for slot_conflict in slot_conflicts:
                    session.delete(slot_conflict)
                session.flush()
                conflict_ids = {row.id for row in slot_conflicts}
                equipped_rows = [row for row in equipped_rows if row.id not in conflict_ids]
            safe_limit = max(int(equip_limit or 0), 1)
            if len(equipped_rows) >= safe_limit:
                raise ValueError(f"当前最多只能装备 {safe_limit} 件法宝。")
            used_slots = {row.slot for row in equipped_rows}
            slot = 1
            while slot in used_slots:
                slot += 1
            session.add(XiuxianEquippedArtifact(tg=tg, artifact_id=artifact_id, slot=slot))
            session.flush()

        refreshed = (
            session.query(XiuxianEquippedArtifact)
            .filter(XiuxianEquippedArtifact.tg == tg)
            .order_by(XiuxianEquippedArtifact.slot.asc(), XiuxianEquippedArtifact.id.asc())
            .all()
        )
        refreshed = reindex_equipped_artifact_slots_in_session(session, tg, refreshed)

        profile.current_artifact_id = refreshed[0].artifact_id if refreshed else None
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return {
            "profile": serialize_profile(profile),
            "action": action,
            "replaced_artifact_id": replaced_artifact_id,
            "equipped_count": len(refreshed),
            "equipped_artifact_ids": [row.artifact_id for row in refreshed],
        }


def set_active_talisman(tg: int, talisman_id: int | None) -> dict[str, Any] | None:
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is None:
            return None

        profile.active_talisman_id = talisman_id
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return serialize_profile(profile)


def set_current_technique(tg: int, technique_id: int | None) -> dict[str, Any] | None:
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is None:
            return None
        profile.current_technique_id = technique_id
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return serialize_profile(profile)



def get_material(material_id: int) -> XiuxianMaterial | None:
    material_value = int(material_id or 0)
    if material_value <= 0:
        return None

    def _loader() -> XiuxianMaterial | None:
        with Session() as session:
            return session.query(XiuxianMaterial).filter(XiuxianMaterial.id == material_value).first()

    return _load_cached_model(
        XiuxianMaterial,
        version_parts=("catalog", "materials"),
        cache_parts=("catalog", "materials", "detail", material_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )



def list_materials(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianMaterial)
            if enabled_only:
                query = query.filter(XiuxianMaterial.enabled.is_(True))
            rows = [serialize_material(row) for row in query.order_by(XiuxianMaterial.id.desc()).all()]
            return sorted(rows, key=lambda item: _named_quality_sort_key(item or {}, "quality_level"))

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "materials"),
        cache_parts=("catalog", "materials", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_plantable_materials(enabled_only: bool = True) -> list[dict[str, Any]]:
    return [
        row
        for row in list_materials(enabled_only=enabled_only)
        if bool((row or {}).get("can_plant"))
    ]


def create_material(**fields) -> dict[str, Any]:
    fields = _normalize_material_fields(dict(fields))
    with Session() as session:
        material = XiuxianMaterial(**fields)
        session.add(material)
        _queue_catalog_cache_invalidation(session, "materials")
        session.commit()
        session.refresh(material)
        return serialize_material(material)


def sync_material_by_name(**fields) -> dict[str, Any]:
    payload = _normalize_material_fields(dict(fields))
    return _sync_named_entity(XiuxianMaterial, serialize_material, payload, catalog_key="materials")


def patch_material(material_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianMaterial).filter(XiuxianMaterial.id == material_id).first()
        if row is None:
            return None
        current = serialize_material(row) or {}
        current.update(patch)
        payload = _normalize_material_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "materials")
        session.commit()
        session.refresh(row)
        return serialize_material(row)


def delete_material(material_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianMaterial).filter(XiuxianMaterial.id == material_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "materials")
        session.commit()
        return True


def grant_material_to_user(tg: int, material_id: int, quantity: int = 1) -> dict[str, Any]:
    with Session() as session:
        row = (
            session.query(XiuxianMaterialInventory)
            .filter(
                XiuxianMaterialInventory.tg == tg,
                XiuxianMaterialInventory.material_id == material_id,
            )
            .first()
        )
        if row is None:
            row = XiuxianMaterialInventory(tg=tg, material_id=material_id, quantity=0)
            session.add(row)
        row.quantity += max(int(quantity), 1)
        row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        material = session.query(XiuxianMaterial).filter(XiuxianMaterial.id == material_id).first()
        return {
            "material": serialize_material(material),
            "quantity": row.quantity,
        }


def list_user_materials(tg: int) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            owner_tgs = _shared_inventory_owner_tgs(session, actor_tg)
            if not owner_tgs:
                return []
            rows = (
                session.query(XiuxianMaterialInventory, XiuxianMaterial)
                .join(XiuxianMaterial, XiuxianMaterial.id == XiuxianMaterialInventory.material_id)
                .filter(XiuxianMaterialInventory.tg.in_(owner_tgs))
                .order_by(XiuxianMaterial.id.desc())
                .all()
            )
            payload_map: dict[int, dict[str, Any]] = {}
            for inventory, material in rows:
                material_id = int(inventory.material_id or 0)
                entry = payload_map.get(material_id)
                if entry is None:
                    entry = {"quantity": 0, "material": serialize_material(material)}
                    payload_map[material_id] = entry
                entry["quantity"] += max(int(inventory.quantity or 0), 0)
            payload = list(payload_map.values())
            return sorted(
                payload,
                key=lambda row: _named_quality_sort_key((row.get("material") or {}), "quality_level"),
            )

    return _load_user_view_cache(actor_tg, "materials", loader=_loader)


def consume_user_materials_in_session(
    session: OrmSession,
    tg: int,
    material_id: int,
    quantity: int = 1,
) -> tuple[bool, int]:
    remaining = max(int(quantity or 0), 1)
    rows = _ordered_owner_rows(session, XiuxianMaterialInventory, tg, "material_id", material_id)
    total_quantity = sum(max(int(row.quantity or 0), 0) for row in rows)
    if total_quantity < remaining:
        return False, total_quantity

    now = utcnow()
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
    _queue_user_view_cache_invalidation(session, tg)
    return True, total_quantity


def consume_user_materials(tg: int, material_id: int, quantity: int = 1) -> bool:
    with Session() as session:
        consumed, _owned_quantity = consume_user_materials_in_session(session, tg, material_id, quantity)
        if not consumed:
            return False
        session.commit()
        return True


def get_recipe(recipe_id: int) -> XiuxianRecipe | None:
    recipe_value = int(recipe_id or 0)
    if recipe_value <= 0:
        return None

    def _loader() -> XiuxianRecipe | None:
        with Session() as session:
            return session.query(XiuxianRecipe).filter(XiuxianRecipe.id == recipe_value).first()

    return _load_cached_model(
        XiuxianRecipe,
        version_parts=("catalog", "recipes"),
        cache_parts=("catalog", "recipes", "detail", recipe_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_recipes(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianRecipe)
            if enabled_only:
                query = query.filter(XiuxianRecipe.enabled.is_(True))
            return [serialize_recipe(row) for row in query.order_by(XiuxianRecipe.id.desc()).all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "recipes"),
        cache_parts=("catalog", "recipes", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_user_recipes(tg: int, enabled_only: bool = False) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianUserRecipe)
                .filter(XiuxianUserRecipe.tg == actor_tg)
                .order_by(XiuxianUserRecipe.created_at.asc(), XiuxianUserRecipe.id.asc())
                .all()
            )
            recipe_ids = [item.recipe_id for item in rows] or [-1]
            recipe_map = {
                row.id: row
                for row in session.query(XiuxianRecipe).filter(XiuxianRecipe.id.in_(recipe_ids)).all()
            }
            payloads: list[dict[str, Any]] = []
            for row in rows:
                recipe = serialize_recipe(recipe_map.get(row.recipe_id))
                if enabled_only and not (recipe or {}).get("enabled"):
                    continue
                payloads.append(serialize_user_recipe(row, recipe))
            return payloads

    return _load_user_view_cache(actor_tg, "recipes", "enabled" if enabled_only else "all", loader=_loader)


def user_has_recipe(tg: int, recipe_id: int) -> bool:
    with Session() as session:
        row = (
            session.query(XiuxianUserRecipe)
            .filter(XiuxianUserRecipe.tg == tg, XiuxianUserRecipe.recipe_id == recipe_id)
            .first()
        )
        return row is not None


def _recover_user_recipe_insert_conflict(session: OrmSession, exc: IntegrityError, tg: int, recipe_id: int) -> bool:
    session.rollback()
    existing = (
        session.query(XiuxianUserRecipe)
        .filter(XiuxianUserRecipe.tg == tg, XiuxianUserRecipe.recipe_id == recipe_id)
        .first()
    )
    if existing is not None:
        return True
    return _sync_sequence_for_primary_key_conflict(exc, "xiuxian_user_recipes")


def grant_recipe_to_user(
    tg: int,
    recipe_id: int,
    *,
    source: str | None = None,
    obtained_note: str | None = None,
) -> dict[str, Any]:
    normalized_source = (source or "").strip() or None
    normalized_note = (obtained_note or "").strip() or None if obtained_note is not None else None
    last_error: IntegrityError | None = None
    for _ in range(2):
        with Session() as session:
            recipe = session.query(XiuxianRecipe).filter(XiuxianRecipe.id == recipe_id).first()
            if recipe is None:
                raise ValueError("recipe not found")
            row = (
                session.query(XiuxianUserRecipe)
                .filter(XiuxianUserRecipe.tg == tg, XiuxianUserRecipe.recipe_id == recipe_id)
                .with_for_update()
                .first()
            )
            if row is None:
                row = XiuxianUserRecipe(
                    tg=tg,
                    recipe_id=recipe_id,
                    source=normalized_source,
                    obtained_note=normalized_note,
                )
                session.add(row)
            else:
                result = grant_duplicate_knowledge_compensation_in_session(
                    session,
                    tg,
                    "recipe",
                    recipe,
                    action_text="重复丹谱折算灵石",
                )
                try:
                    session.commit()
                except IntegrityError as exc:
                    last_error = exc
                    if _recover_user_recipe_insert_conflict(session, exc, tg, recipe_id):
                        continue
                    raise
                return result
            _queue_user_view_cache_invalidation(session, tg)
            try:
                session.commit()
            except IntegrityError as exc:
                last_error = exc
                if _recover_user_recipe_insert_conflict(session, exc, tg, recipe_id):
                    continue
                raise
            session.refresh(row)
            return serialize_user_recipe(row, serialize_recipe(recipe))
    if last_error is not None:
        raise last_error
    raise RuntimeError("grant recipe failed unexpectedly")


def revoke_recipe_from_user(tg: int, recipe_id: int) -> bool:
    with Session() as session:
        row = (
            session.query(XiuxianUserRecipe)
            .filter(XiuxianUserRecipe.tg == tg, XiuxianUserRecipe.recipe_id == recipe_id)
            .first()
        )
        if row is None:
            return False
        session.delete(row)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def create_recipe(**fields) -> dict[str, Any]:
    with Session() as session:
        recipe = XiuxianRecipe(**fields)
        session.add(recipe)
        _queue_catalog_cache_invalidation(session, "recipes")
        session.commit()
        session.refresh(recipe)
        return serialize_recipe(recipe)


def delete_recipe(recipe_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianRecipe).filter(XiuxianRecipe.id == recipe_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "recipes")
        session.commit()
        return True


def replace_recipe_ingredients(recipe_id: int, ingredients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with Session() as session:
        session.query(XiuxianRecipeIngredient).filter(XiuxianRecipeIngredient.recipe_id == recipe_id).delete()
        rows = []
        for payload in ingredients:
            row = XiuxianRecipeIngredient(recipe_id=recipe_id, **payload)
            session.add(row)
            rows.append(row)
        _queue_catalog_cache_invalidation(session, "recipes")
        session.commit()
        return [
            {
                "id": row.id,
                "recipe_id": row.recipe_id,
                "material_id": row.material_id,
                "quantity": row.quantity,
            }
            for row in rows
        ]


def list_recipe_ingredients(recipe_id: int) -> list[dict[str, Any]]:
    recipe_value = int(recipe_id or 0)
    if recipe_value <= 0:
        return []

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianRecipeIngredient, XiuxianMaterial)
                .join(XiuxianMaterial, XiuxianMaterial.id == XiuxianRecipeIngredient.material_id)
                .filter(XiuxianRecipeIngredient.recipe_id == recipe_value)
                .order_by(XiuxianRecipeIngredient.id.asc())
                .all()
            )
            return [
                {
                    "id": ingredient.id,
                    "recipe_id": ingredient.recipe_id,
                    "material_id": ingredient.material_id,
                    "quantity": ingredient.quantity,
                    "material": serialize_material(material),
                }
                for ingredient, material in rows
            ]

    return xiuxian_cache.load_multi_versioned_json(
        version_part_groups=(
            ("catalog", "materials"),
            ("catalog", "recipes"),
        ),
        cache_parts=("catalog", "recipes", "ingredients", recipe_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
