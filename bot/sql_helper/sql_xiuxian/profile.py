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

def _load_cached_model(model_cls, *, version_parts: tuple[Any, ...], cache_parts: tuple[Any, ...], ttl: int, loader):
    payload = xiuxian_cache.load_versioned_json(
        version_parts=version_parts,
        cache_parts=cache_parts,
        ttl=ttl,
        loader=lambda: _serialize_model_snapshot(loader()),
    )
    return _restore_model_snapshot(model_cls, payload)


def _load_user_view_cache(actor_tg: int, *cache_parts: Any, loader):
    return xiuxian_cache.load_versioned_json(
        version_parts=("user-view", int(actor_tg)),
        cache_parts=("user-view", int(actor_tg), *cache_parts),
        ttl=xiuxian_cache.USER_VIEW_TTL,
        loader=loader,
    )


def _queue_profile_cache_invalidation(session: Session, *tgs: int) -> None:
    bucket = session.info.setdefault(_PENDING_PROFILE_CACHE_INVALIDATIONS, set())
    for tg in tgs:
        value = int(tg or 0)
        if value > 0:
            bucket.add(value)


def _queue_user_view_cache_invalidation(session: Session, *tgs: int) -> None:
    bucket = session.info.setdefault(_PENDING_USER_VIEW_CACHE_INVALIDATIONS, set())
    resolved: set[int] = set()
    for tg in tgs:
        actor_tg = int(tg or 0)
        if actor_tg <= 0:
            continue
        resolved.add(actor_tg)
        for related_tg in _shared_profile_tgs(session, actor_tg, for_update=False):
            value = int(related_tg or 0)
            if value > 0:
                resolved.add(value)
    bucket.update(resolved)


def _queue_catalog_cache_invalidation(session: Session, *names: str) -> None:
    bucket = session.info.setdefault(_PENDING_CATALOG_CACHE_INVALIDATIONS, set())
    for name in names:
        normalized = str(name or "").strip()
        if normalized:
            bucket.add(normalized)


def _queue_settings_cache_invalidation(session: Session) -> None:
    session.info[_PENDING_SETTINGS_CACHE_INVALIDATIONS] = True


def invalidate_xiuxian_user_view_cache(*tgs: int) -> int:
    resolved: set[int] = set()
    if not tgs:
        return 0
    with Session() as session:
        for tg in tgs:
            actor_tg = int(tg or 0)
            if actor_tg <= 0:
                continue
            resolved.add(actor_tg)
            for related_tg in _shared_profile_tgs(session, actor_tg, for_update=False):
                value = int(related_tg or 0)
                if value > 0:
                    resolved.add(value)
    return xiuxian_cache.bump_user_view_versions(*sorted(resolved))


@event.listens_for(OrmSession, "after_commit")
def _flush_xiuxian_cache_invalidations(session) -> None:
    if session.info.pop(_PENDING_SETTINGS_CACHE_INVALIDATIONS, False):
        xiuxian_cache.bump_settings_version()

    catalogs = session.info.pop(_PENDING_CATALOG_CACHE_INVALIDATIONS, set())
    if catalogs:
        xiuxian_cache.bump_catalog_versions(*sorted(catalogs))

    profile_tgs = session.info.pop(_PENDING_PROFILE_CACHE_INVALIDATIONS, set())
    if profile_tgs:
        xiuxian_cache.bump_profile_versions(*sorted(profile_tgs))

    user_view_tgs = session.info.pop(_PENDING_USER_VIEW_CACHE_INVALIDATIONS, set())
    if user_view_tgs:
        xiuxian_cache.bump_user_view_versions(*sorted(user_view_tgs))


@event.listens_for(OrmSession, "after_rollback")
def _clear_xiuxian_cache_invalidations(session) -> None:
    session.info.pop(_PENDING_SETTINGS_CACHE_INVALIDATIONS, None)
    session.info.pop(_PENDING_CATALOG_CACHE_INVALIDATIONS, None)
    session.info.pop(_PENDING_PROFILE_CACHE_INVALIDATIONS, None)
    session.info.pop(_PENDING_USER_VIEW_CACHE_INVALIDATIONS, None)


def get_xiuxian_settings() -> dict[str, Any]:
    def _loader() -> dict[str, Any]:
        from .activities import DEPRECATED_XIUXIAN_SETTING_KEYS, _merge_default_gambling_reward_pool
        from .combat import _merge_default_arena_stage_rules, resolve_duel_bet_settings

        with Session() as session:
            rows = session.query(XiuxianSetting).all()
            settings = {row.setting_key: row.setting_value for row in rows}
        for key in DEPRECATED_XIUXIAN_SETTING_KEYS:
            settings.pop(key, None)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(settings)
        merged["gambling_reward_pool"] = _merge_default_gambling_reward_pool(merged.get("gambling_reward_pool"))
        merged["arena_stage_rules"] = _merge_default_arena_stage_rules(merged.get("arena_stage_rules"))
        if "duel_bet_seconds" not in settings and "duel_bet_minutes" in settings:
            merged["duel_bet_seconds"] = max(_coerce_int(settings.get("duel_bet_minutes"), DEFAULT_SETTINGS["duel_bet_minutes"]), 1) * 60
        merged.update(resolve_duel_bet_settings(merged))
        return merged

    return xiuxian_cache.load_versioned_json(
        version_parts=("settings",),
        cache_parts=("settings",),
        ttl=xiuxian_cache.SETTINGS_TTL,
        loader=_loader,
    )


def set_xiuxian_settings(patch: dict[str, Any]) -> dict[str, Any]:
    from .activities import DEPRECATED_XIUXIAN_SETTING_KEYS

    sanitized_patch = {key: value for key, value in patch.items() if key not in DEPRECATED_XIUXIAN_SETTING_KEYS}
    with Session() as session:
        for key, value in sanitized_patch.items():
            row = session.query(XiuxianSetting).filter(XiuxianSetting.setting_key == key).first()
            if row is None:
                row = XiuxianSetting(setting_key=key, setting_value=value)
                session.add(row)
            else:
                row.setting_value = value
                row.updated_at = utcnow()
        _queue_settings_cache_invalidation(session)
        session.commit()
    return get_xiuxian_settings()


def list_image_upload_permissions() -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianImageUploadPermission)
            .order_by(XiuxianImageUploadPermission.updated_at.desc(), XiuxianImageUploadPermission.tg.asc())
            .all()
        )
        return [serialize_image_upload_permission(row) for row in rows]


def has_image_upload_permission(tg: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianImageUploadPermission).filter(XiuxianImageUploadPermission.tg == tg).first()
        return row is not None


def grant_image_upload_permission(tg: int) -> dict[str, Any]:
    with Session() as session:
        row = session.query(XiuxianImageUploadPermission).filter(XiuxianImageUploadPermission.tg == tg).first()
        if row is None:
            row = XiuxianImageUploadPermission(tg=tg)
            session.add(row)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_image_upload_permission(row)


def revoke_image_upload_permission(tg: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianImageUploadPermission).filter(XiuxianImageUploadPermission.tg == tg).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def get_profile(tg: int, create: bool = False) -> XiuxianProfile | None:
    actor_tg = int(tg or 0)
    if actor_tg <= 0:
        return None

    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == actor_tg).first()
        if profile is None:
            if not create:
                return None
            profile = XiuxianProfile(tg=actor_tg)
            session.add(profile)
            _queue_user_view_cache_invalidation(session, actor_tg)
            session.commit()
        return profile


def upsert_profile(tg: int, **fields) -> XiuxianProfile:
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        old_master_tg = int(profile.master_tg or 0) if profile is not None else 0
        if profile is None:
            profile = XiuxianProfile(tg=tg)
            session.add(profile)

        if "realm_stage" in fields:
            fields["realm_stage"] = normalize_realm_stage(fields.get("realm_stage"))

        for key, value in fields.items():
            setattr(profile, key, value)

        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        new_master_tg = int(profile.master_tg or 0)
        if old_master_tg > 0:
            _queue_user_view_cache_invalidation(session, old_master_tg)
        if new_master_tg > 0:
            _queue_user_view_cache_invalidation(session, new_master_tg)
        session.commit()
        return profile


def migrate_all_profile_realms(preview_limit: int = 20) -> dict[str, Any]:
    preview: list[dict[str, Any]] = []
    migrated = 0
    repaired = 0
    unchanged = 0
    with Session() as session:
        rows = (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.consented.is_(True))
            .order_by(XiuxianProfile.updated_at.desc(), XiuxianProfile.tg.asc())
            .all()
        )
        for row in rows:
            result = migrate_legacy_realm_state(row.realm_stage, row.realm_layer, row.cultivation)
            if not result["changed"]:
                unchanged += 1
                continue
            before_stage = str(row.realm_stage or "").strip() or REALM_ORDER[0]
            before_layer = int(row.realm_layer or 0)
            before_cultivation = int(row.cultivation or 0)
            row.realm_stage = result["target_stage"]
            row.realm_layer = int(result["target_layer"])
            row.cultivation = int(result["target_cultivation"])
            row.updated_at = utcnow()
            if result.get("legacy"):
                migrated += 1
            else:
                repaired += 1
            if len(preview) < max(int(preview_limit or 0), 0):
                preview.append(
                    {
                        "tg": int(row.tg),
                        "before_stage": before_stage,
                        "before_layer": before_layer,
                        "before_cultivation": before_cultivation,
                        "after_stage": row.realm_stage,
                        "after_layer": int(row.realm_layer or 0),
                        "after_cultivation": int(row.cultivation or 0),
                        "legacy": bool(result.get("legacy")),
                        "rebased": bool(result.get("rebased")),
                    }
                )
        session.commit()
    return {
        "checked": migrated + repaired + unchanged,
        "migrated": migrated,
        "repaired": repaired,
        "unchanged": unchanged,
        "preview": preview,
    }


def clear_all_xiuxian_user_data() -> dict[str, Any]:
    with Session() as session:
        counts = {
            "duel_bets": session.query(XiuxianDuelBet).delete(synchronize_session=False),
            "duel_pools": session.query(XiuxianDuelBetPool).delete(synchronize_session=False),
            "auction_bids": session.query(XiuxianAuctionBid).delete(synchronize_session=False),
            "auction_items": session.query(XiuxianAuctionItem).delete(synchronize_session=False),
            "arenas": session.query(XiuxianArena).delete(synchronize_session=False),
            "equipped_artifacts": session.query(XiuxianEquippedArtifact).delete(synchronize_session=False),
            "artifact_inventory": session.query(XiuxianArtifactInventory).delete(synchronize_session=False),
            "pill_inventory": session.query(XiuxianPillInventory).delete(synchronize_session=False),
            "talisman_inventory": session.query(XiuxianTalismanInventory).delete(synchronize_session=False),
            "material_inventory": session.query(XiuxianMaterialInventory).delete(synchronize_session=False),
            "farm_plots": session.query(XiuxianFarmPlot).delete(synchronize_session=False),
            "user_titles": session.query(XiuxianUserTitle).delete(synchronize_session=False),
            "user_techniques": session.query(XiuxianUserTechnique).delete(synchronize_session=False),
            "user_recipes": session.query(XiuxianUserRecipe).delete(synchronize_session=False),
            "achievement_progress": session.query(XiuxianAchievementProgress).delete(synchronize_session=False),
            "user_achievements": session.query(XiuxianUserAchievement).delete(synchronize_session=False),
            "marriage_requests": session.query(XiuxianMarriageRequest).delete(synchronize_session=False),
            "marriages": session.query(XiuxianMarriage).delete(synchronize_session=False),
            "mentorship_requests": session.query(XiuxianMentorshipRequest).delete(synchronize_session=False),
            "mentorships": session.query(XiuxianMentorship).delete(synchronize_session=False),
            "explorations": session.query(XiuxianExploration).delete(synchronize_session=False),
            "task_claims": session.query(XiuxianTaskClaim).delete(synchronize_session=False),
            "sect_treasury_items": session.query(XiuxianSectTreasuryItem).delete(synchronize_session=False),
            "encounter_instances": session.query(XiuxianEncounterInstance).delete(synchronize_session=False),
            "red_envelope_claims": session.query(XiuxianRedEnvelopeClaim).delete(synchronize_session=False),
            "red_envelopes": session.query(XiuxianRedEnvelope).delete(synchronize_session=False),
            "journals": session.query(XiuxianJournal).delete(synchronize_session=False),
            "duel_records": session.query(XiuxianDuelRecord).delete(synchronize_session=False),
            "player_shop_items": session.query(XiuxianShopItem).filter(XiuxianShopItem.owner_tg.isnot(None)).delete(synchronize_session=False),
            "player_tasks": session.query(XiuxianTask).filter(XiuxianTask.owner_tg.isnot(None)).delete(synchronize_session=False),
            "profiles": session.query(XiuxianProfile).delete(synchronize_session=False),
        }
        counts["official_tasks_reset"] = (
            session.query(XiuxianTask)
            .filter(XiuxianTask.owner_tg.is_(None))
            .update(
                {
                    XiuxianTask.claimants_count: 0,
                    XiuxianTask.winner_tg: None,
                    XiuxianTask.status: "open",
                    XiuxianTask.group_message_id: None,
                    XiuxianTask.updated_at: utcnow(),
                },
                synchronize_session=False,
            )
        )
        session.commit()
    return counts


def is_profile_dead(profile: XiuxianProfile | dict[str, Any] | None) -> bool:
    if profile is None:
        return False
    if isinstance(profile, dict):
        return bool(profile.get("death_at"))
    return profile.death_at is not None


def assert_profile_alive(profile: XiuxianProfile | dict[str, Any] | None, action_text: str = "继续行动") -> None:
    if is_profile_dead(profile):
        raise ValueError(f"你已身死道消，无法{action_text}，只能重新踏出仙途。")



def assert_currency_operation_allowed(
    tg: int,
    action_text: str = "进行灵石操作",
    *,
    session: Session | None = None,
    profile: XiuxianProfile | None = None,
) -> None:
    from .combat import _active_duel_pool_row, _cleanup_stale_duel_locks

    own_session = session is None
    active_session = session or Session()
    try:
        profile_row = profile
        if profile_row is None:
            query = active_session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg)
            if not own_session:
                query = query.with_for_update()
            profile_row = query.first()
        assert_profile_alive(profile_row, action_text)
        cleaned_ids = _cleanup_stale_duel_locks(active_session, tg, for_update=not own_session)
        if cleaned_ids and own_session:
            active_session.commit()
        active_duel = _active_duel_pool_row(active_session, tg, for_update=not own_session)
        if active_duel is not None:
            duel_mode = str(active_duel.duel_mode or "standard")
            raise ValueError(f"{DUEL_MODE_LABELS.get(duel_mode, '斗法')}结算前，禁止{action_text}。")
    finally:
        if own_session:
            active_session.close()


def _clear_servitude_fields(profile: XiuxianProfile) -> None:
    profile.master_tg = None
    profile.servitude_started_at = None
    profile.servitude_challenge_available_at = None
    profile.furnace_harvested_at = None


def _active_marriage_for_user(session: Session, tg: int, *, for_update: bool = False) -> XiuxianMarriage | None:
    query = session.query(XiuxianMarriage).filter(
        XiuxianMarriage.status == "active",
        (XiuxianMarriage.husband_tg == int(tg)) | (XiuxianMarriage.wife_tg == int(tg)),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(XiuxianMarriage.id.desc()).first()


def _marriage_partner_tg(session: Session, tg: int, *, for_update: bool = False) -> int | None:
    relation = _active_marriage_for_user(session, tg, for_update=for_update)
    if relation is None:
        return None
    if int(relation.husband_tg or 0) == int(tg):
        return int(relation.wife_tg or 0) or None
    return int(relation.husband_tg or 0) or None


def _shared_profile_tgs(session: Session, tg: int, *, for_update: bool = False) -> list[int]:
    actor_tg = int(tg or 0)
    if actor_tg <= 0:
        return []
    partner_tg = _marriage_partner_tg(session, actor_tg, for_update=for_update)
    if not partner_tg or int(partner_tg) == actor_tg:
        return [actor_tg]
    return [actor_tg, int(partner_tg)]


def _shared_profile_rows(session: Session, tg: int, *, for_update: bool = False) -> list[XiuxianProfile]:
    tgs = _shared_profile_tgs(session, tg, for_update=for_update)
    if not tgs:
        return []
    query = session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_(tgs))
    if for_update:
        query = query.with_for_update()
    rows = {int(row.tg): row for row in query.all()}
    return [rows[item] for item in tgs if int(item) in rows]


def get_shared_spiritual_stone_total(tg: int, *, session: Session | None = None, for_update: bool = False) -> int:
    own_session = session is None
    active_session = session or Session()
    try:
        rows = _shared_profile_rows(active_session, tg, for_update=for_update and not own_session)
        return sum(max(int(row.spiritual_stone or 0), 0) for row in rows)
    finally:
        if own_session:
            active_session.close()


def _deduct_shared_spiritual_stone(
    session: Session,
    actor: XiuxianProfile,
    amount: int,
    *,
    action_text: str,
) -> None:
    need = max(int(amount or 0), 0)
    if need <= 0:
        return
    rows = _shared_profile_rows(session, int(actor.tg or 0), for_update=True)
    if not rows:
        raise ValueError("你还没有踏入仙途")
    total = sum(max(int(row.spiritual_stone or 0), 0) for row in rows)
    if total < need:
        raise ValueError("灵石不足")
    ordered_rows = sorted(rows, key=lambda row: (0 if int(row.tg or 0) == int(actor.tg or 0) else 1, int(row.tg or 0)))
    now = utcnow()
    for row in ordered_rows:
        if need <= 0:
            break
        current = max(int(row.spiritual_stone or 0), 0)
        if current <= 0:
            continue
        delta = min(current, need)
        row.spiritual_stone = current - delta
        row.updated_at = now
        need -= delta
    if need > 0:
        raise ValueError(f"{action_text}失败：共享灵石扣减异常。")


def apply_spiritual_stone_delta(
    session: Session,
    tg: int,
    delta: int,
    *,
    action_text: str = "进行灵石操作",
    enforce_currency_lock: bool = False,
    allow_create: bool = False,
    allow_dead: bool = False,
    apply_tribute: bool = True,
) -> dict[str, Any]:
    amount = int(delta or 0)
    profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
    if profile is None:
        if not allow_create:
            raise ValueError("你还没有踏入仙途")
        profile = XiuxianProfile(tg=tg)
        session.add(profile)
        session.flush()
    if not allow_dead:
        assert_profile_alive(profile, action_text)
    if enforce_currency_lock and profile.consented:
        assert_currency_operation_allowed(tg, action_text, session=session, profile=profile)

    current = int(profile.spiritual_stone or 0)
    tribute_amount = 0
    tribute_master = None
    if amount < 0:
        _deduct_shared_spiritual_stone(session, profile, -amount, action_text=action_text)
        return {
            "profile": profile,
            "tribute_amount": 0,
            "tribute_master": None,
            "net_delta": amount,
        }

    if amount > 0 and apply_tribute and profile.consented and profile.master_tg:
        master = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(profile.master_tg)).with_for_update().first()
        if master is None or not master.consented or master.death_at is not None or int(master.tg) == int(profile.tg):
            _clear_servitude_fields(profile)
        else:
            settings = get_xiuxian_settings()
            tribute_percent = max(min(int(settings.get("slave_tribute_percent", DEFAULT_SETTINGS.get("slave_tribute_percent", 20)) or 0), 100), 0)
            tribute_amount = min(amount, amount * tribute_percent // 100)
            if tribute_amount > 0:
                master.spiritual_stone = int(master.spiritual_stone or 0) + tribute_amount
                master.updated_at = utcnow()
                tribute_master = master

    profile.spiritual_stone = max(current + amount - tribute_amount, 0)
    profile.updated_at = utcnow()
    _queue_profile_cache_invalidation(session, int(profile.tg or 0))
    _queue_user_view_cache_invalidation(session, int(profile.tg or 0))
    if tribute_master is not None:
        _queue_profile_cache_invalidation(session, int(tribute_master.tg or 0))
        _queue_user_view_cache_invalidation(session, int(tribute_master.tg or 0))
    return {
        "profile": profile,
        "tribute_amount": tribute_amount,
        "tribute_master": tribute_master,
        "net_delta": amount - tribute_amount,
    }



def get_emby_name_map(tgs: list[int]) -> dict[int, str]:
    if not tgs:
        return {}

    with Session() as session:
        mapping: dict[int, str] = {}
        profiles = session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_(tgs)).all()
        for profile in profiles:
            label = profile.display_name or (f"@{profile.username}" if profile.username else None)
            if label:
                mapping[int(profile.tg)] = label
        emby_rows = session.query(Emby).filter(Emby.tg.in_(tgs)).all()
        for row in emby_rows:
            mapping.setdefault(int(row.tg), row.name or row.embyid or f"TG {row.tg}")
        for tg in tgs:
            mapping.setdefault(int(tg), f"TG {tg}")
        return mapping


def get_emby_account_map(tgs: list[int]) -> dict[int, dict[str, Any]]:
    if not tgs:
        return {}

    with Session() as session:
        rows = session.query(Emby).filter(Emby.tg.in_(tgs)).all()
        return {int(row.tg): serialize_emby_account(row) for row in rows}


def get_emby_account(tg: int) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(Emby).filter(Emby.tg == tg).first()
        return serialize_emby_account(row)


def list_profiles() -> list[XiuxianProfile]:
    with Session() as session:
        return session.query(XiuxianProfile).filter(XiuxianProfile.consented.is_(True)).all()


def list_slave_profiles(master_tg: int) -> list[dict[str, Any]]:
    actor_tg = int(master_tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianProfile)
                .filter(
                    XiuxianProfile.master_tg == actor_tg,
                    XiuxianProfile.consented.is_(True),
                )
                .order_by(XiuxianProfile.updated_at.desc(), XiuxianProfile.tg.asc())
                .all()
            )
            return [serialize_profile(row) for row in rows]

    return _load_user_view_cache(actor_tg, "slave-profiles", loader=_loader)


def search_profiles(
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_secluded: bool = True,
) -> dict[str, Any]:
    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 20), 50), 1)
    offset = (page - 1) * page_size
    with Session() as session:
        q = session.query(XiuxianProfile).outerjoin(Emby, Emby.tg == XiuxianProfile.tg).filter(XiuxianProfile.consented.is_(True))
        if not include_secluded:
            q = q.filter(or_(XiuxianProfile.social_mode.is_(None), XiuxianProfile.social_mode != "secluded"))
        if query and query.strip():
            keyword = query.strip()
            normalized_keyword = keyword.lstrip("@")
            if keyword.isdigit():
                q = q.filter(or_(XiuxianProfile.tg == int(keyword), Emby.embyid == keyword))
            else:
                pattern = f"%{keyword}%"
                account_pattern = f"%{normalized_keyword}%"
                q = q.filter(
                    or_(
                        XiuxianProfile.display_name.ilike(pattern),
                        XiuxianProfile.username.ilike(account_pattern),
                        Emby.name.ilike(pattern),
                        Emby.embyid.ilike(account_pattern),
                    )
                )
        total = q.count()
        rows = q.order_by(XiuxianProfile.updated_at.desc()).offset(offset).limit(page_size).all()
        account_map = get_emby_account_map([int(row.tg) for row in rows])
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    **serialize_profile(row),
                    "emby_account": account_map.get(int(row.tg)),
                }
                for row in rows
            ],
        }


ADMIN_EDITABLE_PROFILE_FIELDS = {
    "spiritual_stone", "cultivation", "realm_stage", "realm_layer",
    "bone", "comprehension", "divine_sense", "fortune", "willpower", "charisma", "karma",
    "qi_blood", "true_yuan", "body_movement", "attack_power", "defense_power",
    "insight_bonus", "dan_poison", "sect_contribution",
    "technique_capacity",
    "display_name", "username",
    "root_type", "root_primary", "root_secondary", "root_relation",
    "root_bonus", "root_quality", "root_quality_level", "root_quality_color",
}

ADMIN_NULLABLE_STRING_FIELDS = {
    "display_name",
    "username",
    "root_type",
    "root_primary",
    "root_secondary",
    "root_relation",
    "root_quality",
    "root_quality_color",
}
ADMIN_INTEGER_PROFILE_FIELDS = ADMIN_EDITABLE_PROFILE_FIELDS - ADMIN_NULLABLE_STRING_FIELDS - {"realm_stage"}
ADMIN_NONNEGATIVE_PROFILE_FIELDS = {
    "spiritual_stone",
    "cultivation",
    "realm_layer",
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
    "insight_bonus",
    "sect_contribution",
    "technique_capacity",
    "root_quality_level",
}


def admin_patch_profile(tg: int, **fields) -> dict[str, Any] | None:
    safe = {k: v for k, v in fields.items() if k in ADMIN_EDITABLE_PROFILE_FIELDS}
    if not safe:
        raise ValueError("没有可更新的字段")
    for key in ADMIN_INTEGER_PROFILE_FIELDS:
        if key in safe:
            safe[key] = _coerce_int(safe.get(key), 0)
    if "realm_stage" in safe:
        safe["realm_stage"] = normalize_realm_stage(safe.get("realm_stage"))
    if "realm_layer" in safe:
        safe["realm_layer"] = normalize_realm_layer(safe.get("realm_layer"), 1)
    if "technique_capacity" in safe:
        safe["technique_capacity"] = normalize_technique_capacity(safe.get("technique_capacity"))
    for key in ADMIN_NONNEGATIVE_PROFILE_FIELDS:
        if key in safe:
            safe[key] = max(_coerce_int(safe.get(key), 0), 0)
    if "dan_poison" in safe:
        safe["dan_poison"] = max(min(_coerce_int(safe.get("dan_poison"), 0), 100), 0)
    for key in ADMIN_NULLABLE_STRING_FIELDS:
        if key in safe:
            safe[key] = None if safe[key] is None else (str(safe[key]).strip() or None)
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is None or not profile.consented:
            return None
        target_stage = safe.get("realm_stage", profile.realm_stage)
        target_layer = safe.get("realm_layer", profile.realm_layer)
        if {"cultivation", "realm_stage", "realm_layer"}.intersection(safe):
            cultivation = safe.get("cultivation", profile.cultivation)
            safe["cultivation"] = min(
                max(_coerce_int(cultivation, 0), 0),
                calculate_realm_threshold(target_stage, target_layer),
            )
        for key, value in safe.items():
            setattr(profile, key, value)
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return serialize_profile(profile)


__all__ = [name for name in globals() if not name.startswith("__")]
