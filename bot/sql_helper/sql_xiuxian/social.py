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

def _admin_social_profile_cards(session: Session, tgs: Iterable[int]) -> dict[int, dict[str, Any]]:
    valid_tgs = sorted({int(tg or 0) for tg in tgs if int(tg or 0) > 0})
    if not valid_tgs:
        return {}
    rows = session.query(XiuxianProfile).filter(XiuxianProfile.tg.in_(valid_tgs)).all()
    cards: dict[int, dict[str, Any]] = {}
    for row in rows:
        payload = serialize_profile(row) or {}
        cards[int(row.tg)] = {
            "tg": int(row.tg),
            "display_name": payload.get("display_name") or "",
            "username": payload.get("username") or "",
            "display_label": payload.get("display_label") or f"TG {int(row.tg)}",
            "realm_stage": payload.get("realm_stage") or "",
            "realm_layer": int(payload.get("realm_layer") or 0),
            "gender_label": payload.get("gender_label") or "",
            "social_mode_label": payload.get("social_mode_label") or "",
        }
    for tg in valid_tgs:
        cards.setdefault(tg, {"tg": tg, "display_label": f"TG {tg}"})
    return cards


def _attach_mentorship_admin_profiles(payload: dict[str, Any], cards: dict[int, dict[str, Any]]) -> dict[str, Any]:
    payload["mentor_profile"] = cards.get(int(payload.get("mentor_tg") or 0))
    payload["disciple_profile"] = cards.get(int(payload.get("disciple_tg") or 0))
    return payload


def _attach_request_admin_profiles(payload: dict[str, Any], cards: dict[int, dict[str, Any]]) -> dict[str, Any]:
    payload["sponsor_profile"] = cards.get(int(payload.get("sponsor_tg") or 0))
    payload["target_profile"] = cards.get(int(payload.get("target_tg") or 0))
    if "mentor_tg" in payload:
        payload["mentor_profile"] = cards.get(int(payload.get("mentor_tg") or 0))
    if "disciple_tg" in payload:
        payload["disciple_profile"] = cards.get(int(payload.get("disciple_tg") or 0))
    return payload


def _attach_marriage_admin_profiles(payload: dict[str, Any], cards: dict[int, dict[str, Any]]) -> dict[str, Any]:
    payload["husband_profile"] = cards.get(int(payload.get("husband_tg") or 0))
    payload["wife_profile"] = cards.get(int(payload.get("wife_tg") or 0))
    return payload


def list_admin_mentorships(limit: int = 200) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianMentorship)
            .order_by(XiuxianMentorship.status.asc(), XiuxianMentorship.id.desc())
            .limit(max(int(limit or 200), 1))
            .all()
        )
        payloads = [serialize_mentorship(row) or {} for row in rows]
        cards = _admin_social_profile_cards(
            session,
            [tg for item in payloads for tg in (item.get("mentor_tg"), item.get("disciple_tg"))],
        )
        return [_attach_mentorship_admin_profiles(item, cards) for item in payloads]


def list_admin_mentorship_requests(limit: int = 200) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianMentorshipRequest)
            .order_by(XiuxianMentorshipRequest.status.asc(), XiuxianMentorshipRequest.id.desc())
            .limit(max(int(limit or 200), 1))
            .all()
        )
        payloads = [serialize_mentorship_request(row) or {} for row in rows]
        cards = _admin_social_profile_cards(
            session,
            [tg for item in payloads for tg in (item.get("sponsor_tg"), item.get("target_tg"))],
        )
        return [_attach_request_admin_profiles(item, cards) for item in payloads]


def list_admin_marriages(limit: int = 200) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianMarriage)
            .order_by(XiuxianMarriage.status.asc(), XiuxianMarriage.id.desc())
            .limit(max(int(limit or 200), 1))
            .all()
        )
        payloads = [serialize_marriage(row) or {} for row in rows]
        cards = _admin_social_profile_cards(
            session,
            [tg for item in payloads for tg in (item.get("husband_tg"), item.get("wife_tg"))],
        )
        return [_attach_marriage_admin_profiles(item, cards) for item in payloads]


def list_admin_marriage_requests(limit: int = 200) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianMarriageRequest)
            .order_by(XiuxianMarriageRequest.status.asc(), XiuxianMarriageRequest.id.desc())
            .limit(max(int(limit or 200), 1))
            .all()
        )
        payloads = [serialize_marriage_request(row) or {} for row in rows]
        cards = _admin_social_profile_cards(
            session,
            [tg for item in payloads for tg in (item.get("sponsor_tg"), item.get("target_tg"))],
        )
        return [_attach_request_admin_profiles(item, cards) for item in payloads]


def admin_patch_mentorship(mentorship_id: int, *, status: str | None = None, bond_value: int | None = None) -> dict[str, Any] | None:
    now = utcnow()
    with Session() as session:
        row = session.query(XiuxianMentorship).filter(XiuxianMentorship.id == int(mentorship_id)).with_for_update().first()
        if row is None:
            return None
        if status is not None:
            normalized = normalize_mentorship_status(status)
            row.status = normalized
            if normalized == "active":
                row.ended_at = None
                row.graduated_at = None
            else:
                row.ended_at = row.ended_at or now
                if normalized == "graduated":
                    row.graduated_at = row.graduated_at or now
        if bond_value is not None:
            row.bond_value = max(int(bond_value or 0), 0)
        row.updated_at = now
        _queue_user_view_cache_invalidation(session, int(row.mentor_tg or 0), int(row.disciple_tg or 0))
        payload = serialize_mentorship(row) or {}
        cards = _admin_social_profile_cards(session, [payload.get("mentor_tg"), payload.get("disciple_tg")])
        session.commit()
        return _attach_mentorship_admin_profiles(payload, cards)


def admin_patch_mentorship_request(request_id: int, *, status: str | None = None) -> dict[str, Any] | None:
    now = utcnow()
    with Session() as session:
        row = session.query(XiuxianMentorshipRequest).filter(XiuxianMentorshipRequest.id == int(request_id)).with_for_update().first()
        if row is None:
            return None
        if status is not None:
            normalized = normalize_mentorship_request_status(status)
            row.status = normalized
            row.responded_at = None if normalized == "pending" else (row.responded_at or now)
        row.updated_at = now
        _queue_user_view_cache_invalidation(session, int(row.sponsor_tg or 0), int(row.target_tg or 0))
        payload = serialize_mentorship_request(row) or {}
        cards = _admin_social_profile_cards(session, [payload.get("sponsor_tg"), payload.get("target_tg")])
        session.commit()
        return _attach_request_admin_profiles(payload, cards)


def admin_patch_marriage(marriage_id: int, *, status: str | None = None, bond_value: int | None = None) -> dict[str, Any] | None:
    now = utcnow()
    with Session() as session:
        row = session.query(XiuxianMarriage).filter(XiuxianMarriage.id == int(marriage_id)).with_for_update().first()
        if row is None:
            return None
        if status is not None:
            normalized = normalize_marriage_status(status)
            row.status = normalized
            row.ended_at = None if normalized == "active" else (row.ended_at or now)
        if bond_value is not None:
            row.bond_value = max(int(bond_value or 0), 0)
        row.updated_at = now
        _queue_user_view_cache_invalidation(session, int(row.husband_tg or 0), int(row.wife_tg or 0))
        payload = serialize_marriage(row) or {}
        cards = _admin_social_profile_cards(session, [payload.get("husband_tg"), payload.get("wife_tg")])
        session.commit()
        return _attach_marriage_admin_profiles(payload, cards)


def admin_patch_marriage_request(request_id: int, *, status: str | None = None) -> dict[str, Any] | None:
    now = utcnow()
    with Session() as session:
        row = session.query(XiuxianMarriageRequest).filter(XiuxianMarriageRequest.id == int(request_id)).with_for_update().first()
        if row is None:
            return None
        if status is not None:
            normalized = normalize_marriage_request_status(status)
            row.status = normalized
            row.responded_at = None if normalized == "pending" else (row.responded_at or now)
        row.updated_at = now
        _queue_user_view_cache_invalidation(session, int(row.sponsor_tg or 0), int(row.target_tg or 0))
        payload = serialize_marriage_request(row) or {}
        cards = _admin_social_profile_cards(session, [payload.get("sponsor_tg"), payload.get("target_tg")])
        session.commit()
        return _attach_request_admin_profiles(payload, cards)



def _slugify_achievement_key(raw: str | None, fallback: str) -> str:
    source = str(raw or fallback or "").strip().lower()
    source = re.sub(r"[^a-z0-9_-]+", "_", source)
    source = re.sub(r"_+", "_", source).strip("_")
    return source or "achievement"



def get_sect(sect_id: int) -> XiuxianSect | None:
    sect_value = int(sect_id or 0)
    if sect_value <= 0:
        return None

    def _loader() -> XiuxianSect | None:
        with Session() as session:
            return session.query(XiuxianSect).filter(XiuxianSect.id == sect_value).first()

    return _load_cached_model(
        XiuxianSect,
        version_parts=("catalog", "sects"),
        cache_parts=("catalog", "sects", "detail", sect_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_sects(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianSect)
            if enabled_only:
                query = query.filter(XiuxianSect.enabled.is_(True))
            return [serialize_sect(item) for item in query.order_by(XiuxianSect.id.desc()).all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "sects"),
        cache_parts=("catalog", "sects", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def create_sect(**fields) -> dict[str, Any]:
    fields = _normalize_sect_fields(dict(fields))
    with Session() as session:
        sect = XiuxianSect(**fields)
        session.add(sect)
        _queue_catalog_cache_invalidation(session, "sects")
        session.commit()
        session.refresh(sect)
        return serialize_sect(sect)


def patch_sect(sect_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianSect).filter(XiuxianSect.id == sect_id).first()
        if row is None:
            return None
        current = serialize_sect(row) or {}
        current.update(patch)
        payload = _normalize_sect_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "sects")
        session.commit()
        session.refresh(row)
        return serialize_sect(row)


def delete_sect(sect_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianSect).filter(XiuxianSect.id == sect_id).first()
        if row is None:
            return False
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "sects")
        session.commit()
        return True


def replace_sect_roles(sect_id: int, roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with Session() as session:
        session.query(XiuxianSectRole).filter(XiuxianSectRole.sect_id == sect_id).delete()
        payloads = []
        for role in roles:
            row = XiuxianSectRole(sect_id=sect_id, **role)
            session.add(row)
            payloads.append(row)
        _queue_catalog_cache_invalidation(session, "sects")
        session.commit()
        return [serialize_sect_role(row) for row in payloads]


def list_sect_roles(sect_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianSectRole)
            .filter(XiuxianSectRole.sect_id == sect_id)
            .order_by(XiuxianSectRole.sort_order.asc(), XiuxianSectRole.id.asc())
            .all()
        )
        return [serialize_sect_role(row) for row in rows]


def list_sect_treasury_items(sect_id: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianSectTreasuryItem)
            .filter(XiuxianSectTreasuryItem.sect_id == int(sect_id or 0))
            .order_by(XiuxianSectTreasuryItem.updated_at.desc(), XiuxianSectTreasuryItem.id.desc())
            .all()
        )
        return [serialize_sect_treasury_item(row) for row in rows]



def create_title(**fields) -> dict[str, Any]:
    payload = _normalize_title_fields(dict(fields))
    with Session() as session:
        row = XiuxianTitle(**payload)
        session.add(row)
        _queue_catalog_cache_invalidation(session, "titles")
        session.commit()
        session.refresh(row)
        return serialize_title(row)


def sync_title_by_name(**fields) -> dict[str, Any]:
    from .items import _sync_named_entity

    return _sync_named_entity(
        XiuxianTitle,
        serialize_title,
        _normalize_title_fields(dict(fields)),
        catalog_key="titles",
    )


def get_title(title_id: int) -> XiuxianTitle | None:
    title_value = int(title_id or 0)
    if title_value <= 0:
        return None

    def _loader() -> XiuxianTitle | None:
        with Session() as session:
            return session.query(XiuxianTitle).filter(XiuxianTitle.id == title_value).first()

    return _load_cached_model(
        XiuxianTitle,
        version_parts=("catalog", "titles"),
        cache_parts=("catalog", "titles", "detail", title_value),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def list_titles(enabled_only: bool = False) -> list[dict[str, Any]]:
    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianTitle)
            if enabled_only:
                query = query.filter(XiuxianTitle.enabled.is_(True))
            rows = query.order_by(XiuxianTitle.id.desc()).all()
            return [serialize_title(row) for row in rows]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "titles"),
        cache_parts=("catalog", "titles", "list", "enabled" if enabled_only else "all"),
        ttl=xiuxian_cache.CATALOG_TTL,
        loader=_loader,
    )


def patch_title(title_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianTitle).filter(XiuxianTitle.id == title_id).first()
        if row is None:
            return None
        current = serialize_title(row) or {}
        current.update(patch)
        payload = _normalize_title_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "titles")
        session.commit()
        session.refresh(row)
        return serialize_title(row)


def delete_title(title_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianTitle).filter(XiuxianTitle.id == title_id).first()
        if row is None:
            return False
        session.query(XiuxianProfile).filter(XiuxianProfile.current_title_id == title_id).update(
            {"current_title_id": None, "updated_at": utcnow()},
            synchronize_session=False,
        )
        session.delete(row)
        _queue_catalog_cache_invalidation(session, "titles")
        session.commit()
        return True


def list_user_titles(tg: int, enabled_only: bool = False) -> list[dict[str, Any]]:
    actor_tg = int(tg or 0)

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            rows = (
                session.query(XiuxianUserTitle)
                .filter(XiuxianUserTitle.tg == actor_tg)
                .order_by(XiuxianUserTitle.created_at.asc(), XiuxianUserTitle.id.asc())
                .all()
            )
            titles = {
                row.id: row
                for row in session.query(XiuxianTitle)
                .filter(XiuxianTitle.id.in_([item.title_id for item in rows] or [-1]))
                .all()
            }
            serialized: list[dict[str, Any]] = []
            for row in rows:
                title = serialize_title(titles.get(row.title_id))
                if enabled_only and not (title or {}).get("enabled"):
                    continue
                serialized.append(serialize_user_title(row, title))
            return serialized

    return _load_user_view_cache(actor_tg, "titles", "enabled" if enabled_only else "all", loader=_loader)


def get_current_title(tg: int, enabled_only: bool = False) -> dict[str, Any] | None:
    actor_tg = int(tg or 0)

    def _loader() -> dict[str, Any] | None:
        with Session() as session:
            profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == actor_tg).first()
            if profile is None or not profile.current_title_id:
                return None
            row = session.query(XiuxianTitle).filter(XiuxianTitle.id == profile.current_title_id).first()
            if row is None or (enabled_only and not row.enabled):
                return None
            return serialize_title(row)

    return _load_user_view_cache(actor_tg, "current-title", "enabled" if enabled_only else "all", loader=_loader)


def grant_title_to_user(
    tg: int,
    title_id: int,
    *,
    source: str | None = None,
    obtained_note: str | None = None,
    equip: bool = False,
    auto_equip_if_empty: bool = False,
) -> dict[str, Any]:
    with Session() as session:
        title = session.query(XiuxianTitle).filter(XiuxianTitle.id == title_id).first()
        if title is None:
            raise ValueError("title not found")
        row = (
            session.query(XiuxianUserTitle)
            .filter(XiuxianUserTitle.tg == tg, XiuxianUserTitle.title_id == title_id)
            .first()
        )
        if row is None:
            row = XiuxianUserTitle(
                tg=tg,
                title_id=title_id,
                source=(source or "").strip() or None,
                obtained_note=(obtained_note or "").strip() or None,
            )
            session.add(row)
        else:
            if source is not None:
                row.source = (source or "").strip() or None
            if obtained_note is not None:
                row.obtained_note = (obtained_note or "").strip() or None
            row.updated_at = utcnow()
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is None:
            profile = XiuxianProfile(tg=tg)
            session.add(profile)
        if equip or (auto_equip_if_empty and not profile.current_title_id):
            profile.current_title_id = title_id
            profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        session.refresh(row)
        return serialize_user_title(row, serialize_title(title))


def revoke_title_from_user(tg: int, title_id: int) -> bool:
    with Session() as session:
        row = (
            session.query(XiuxianUserTitle)
            .filter(XiuxianUserTitle.tg == tg, XiuxianUserTitle.title_id == title_id)
            .first()
        )
        if row is None:
            return False
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is not None and int(profile.current_title_id or 0) == int(title_id):
            profile.current_title_id = None
            profile.updated_at = utcnow()
        session.delete(row)
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return True


def set_current_title(tg: int, title_id: int | None) -> dict[str, Any] | None:
    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).first()
        if profile is None:
            profile = XiuxianProfile(tg=tg)
            session.add(profile)
        if title_id in {None, 0}:
            profile.current_title_id = None
            profile.updated_at = utcnow()
            _queue_profile_cache_invalidation(session, tg)
            _queue_user_view_cache_invalidation(session, tg)
            session.commit()
            return None
        owned = (
            session.query(XiuxianUserTitle)
            .filter(XiuxianUserTitle.tg == tg, XiuxianUserTitle.title_id == int(title_id))
            .first()
        )
        if owned is None:
            raise ValueError("user does not own this title")
        title = session.query(XiuxianTitle).filter(XiuxianTitle.id == int(title_id)).first()
        if title is None:
            raise ValueError("title not found")
        profile.current_title_id = int(title_id)
        profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, tg)
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()
        return serialize_title(title)


def create_achievement(**fields) -> dict[str, Any]:
    payload = _normalize_achievement_fields(dict(fields))
    with Session() as session:
        row = XiuxianAchievement(**payload)
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_achievement(row)


def sync_achievement_by_key(**fields) -> dict[str, Any]:
    payload = _normalize_achievement_fields(dict(fields))
    with Session() as session:
        row = (
            session.query(XiuxianAchievement)
            .filter(XiuxianAchievement.achievement_key == payload["achievement_key"])
            .first()
        )
        if row is None:
            row = XiuxianAchievement(**payload)
            session.add(row)
            session.commit()
            session.refresh(row)
            return serialize_achievement(row)
        changed = False
        for key, value in payload.items():
            if getattr(row, key) != value:
                setattr(row, key, value)
                changed = True
        if changed:
            row.updated_at = utcnow()
            session.commit()
            session.refresh(row)
        return serialize_achievement(row)


def get_achievement(achievement_id: int) -> XiuxianAchievement | None:
    with Session() as session:
        return session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()


def list_achievements(enabled_only: bool = False) -> list[dict[str, Any]]:
    with Session() as session:
        query = session.query(XiuxianAchievement)
        if enabled_only:
            query = query.filter(XiuxianAchievement.enabled.is_(True))
        rows = (
            query.order_by(
                XiuxianAchievement.sort_order.asc(),
                XiuxianAchievement.target_value.asc(),
                XiuxianAchievement.id.asc(),
            )
            .all()
        )
        return [serialize_achievement(row) for row in rows]


def list_achievements_by_metric(metric_keys: list[str], enabled_only: bool = True) -> list[dict[str, Any]]:
    metric_keys = [str(item).strip() for item in metric_keys if str(item).strip()]
    if not metric_keys:
        return []
    with Session() as session:
        query = session.query(XiuxianAchievement).filter(XiuxianAchievement.metric_key.in_(metric_keys))
        if enabled_only:
            query = query.filter(XiuxianAchievement.enabled.is_(True))
        rows = (
            query.order_by(
                XiuxianAchievement.sort_order.asc(),
                XiuxianAchievement.target_value.asc(),
                XiuxianAchievement.id.asc(),
            )
            .all()
        )
        return [serialize_achievement(row) for row in rows]


def patch_achievement(achievement_id: int, **fields) -> dict[str, Any] | None:
    patch = dict(fields)
    with Session() as session:
        row = session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()
        if row is None:
            return None
        current = serialize_achievement(row) or {}
        current.update(patch)
        payload = _normalize_achievement_fields(current)
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_achievement(row)


def delete_achievement(achievement_id: int) -> bool:
    with Session() as session:
        row = session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_user_achievement_progress(tg: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianAchievementProgress)
            .filter(XiuxianAchievementProgress.tg == tg)
            .order_by(XiuxianAchievementProgress.metric_key.asc())
            .all()
        )
        return [serialize_achievement_progress(row) for row in rows]


def get_user_achievement_progress_map(tg: int) -> dict[str, int]:
    with Session() as session:
        rows = session.query(XiuxianAchievementProgress).filter(XiuxianAchievementProgress.tg == tg).all()
        return {row.metric_key: int(row.current_value or 0) for row in rows}


def apply_achievement_progress_deltas(tg: int, deltas: dict[str, int | float]) -> dict[str, int]:
    sanitized: dict[str, int] = {}
    for key, value in (deltas or {}).items():
        metric_key = str(key or "").strip()
        if not metric_key:
            continue
        amount = int(value or 0)
        if amount == 0:
            continue
        sanitized[metric_key] = sanitized.get(metric_key, 0) + amount
    if not sanitized:
        return {}
    with Session() as session:
        result: dict[str, int] = {}
        for metric_key, amount in sanitized.items():
            row = (
                session.query(XiuxianAchievementProgress)
                .filter(
                    XiuxianAchievementProgress.tg == tg,
                    XiuxianAchievementProgress.metric_key == metric_key,
                )
                .first()
            )
            if row is None:
                row = XiuxianAchievementProgress(tg=tg, metric_key=metric_key, current_value=0)
                session.add(row)
            row.current_value = max(int(row.current_value or 0) + amount, 0)
            row.updated_at = utcnow()
            result[metric_key] = int(row.current_value or 0)
        session.commit()
        return result


def list_user_achievements(tg: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianUserAchievement)
            .filter(XiuxianUserAchievement.tg == tg)
            .order_by(XiuxianUserAchievement.unlocked_at.asc(), XiuxianUserAchievement.id.asc())
            .all()
        )
        achievements = {
            row.id: row
            for row in session.query(XiuxianAchievement)
            .filter(XiuxianAchievement.id.in_([item.achievement_id for item in rows] or [-1]))
            .all()
        }
        return [
            serialize_user_achievement(row, serialize_achievement(achievements.get(row.achievement_id)))
            for row in rows
        ]


def unlock_user_achievement(
    tg: int,
    achievement_id: int,
    *,
    reward_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    with Session() as session:
        existing = (
            session.query(XiuxianUserAchievement)
            .filter(
                XiuxianUserAchievement.tg == tg,
                XiuxianUserAchievement.achievement_id == achievement_id,
            )
            .first()
        )
        if existing is not None:
            achievement = session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()
            payload = serialize_user_achievement(existing, serialize_achievement(achievement))
            if payload is not None:
                payload["created"] = False
            return payload
        achievement = session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()
        if achievement is None:
            return None
        row = XiuxianUserAchievement(
            tg=tg,
            achievement_id=achievement_id,
            reward_snapshot=reward_snapshot or {},
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        payload = serialize_user_achievement(row, serialize_achievement(achievement))
        if payload is not None:
            payload["created"] = True
        return payload


def get_user_achievement(tg: int, achievement_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = (
            session.query(XiuxianUserAchievement)
            .filter(
                XiuxianUserAchievement.tg == tg,
                XiuxianUserAchievement.achievement_id == achievement_id,
            )
            .first()
        )
        if row is None:
            return None
        achievement = session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()
        return serialize_user_achievement(row, serialize_achievement(achievement))


def mark_user_achievement_notification(tg: int, achievement_id: int, channel: str) -> dict[str, Any] | None:
    channel = str(channel or "").strip().lower()
    if channel not in {"private", "group"}:
        raise ValueError("unsupported achievement notify channel")
    with Session() as session:
        row = (
            session.query(XiuxianUserAchievement)
            .filter(
                XiuxianUserAchievement.tg == tg,
                XiuxianUserAchievement.achievement_id == achievement_id,
            )
            .first()
        )
        if row is None:
            return None
        if channel == "private":
            row.private_notified_at = utcnow()
        else:
            row.group_notified_at = utcnow()
        row.updated_at = utcnow()
        session.commit()
        achievement = session.query(XiuxianAchievement).filter(XiuxianAchievement.id == achievement_id).first()
        return serialize_user_achievement(row, serialize_achievement(achievement))


__all__ = [name for name in globals() if not name.startswith("__")]
