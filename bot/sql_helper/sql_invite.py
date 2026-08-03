from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text

from bot import group
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby, sql_invalidate_emby_cache


UTC_TZ = timezone.utc
SHANGHAI_TZ = timezone(timedelta(hours=8))

DEFAULT_INVITE_SETTINGS = {
    "enabled": False,
    "target_chat_id": None,
    "expire_hours": 24,
    "strict_target": True,
    "group_verification_enabled": True,
    "channel_verification_enabled": False,
    "account_open_days": 30,
}

INVITE_CREDIT_TYPE_GROUP = "group_join"
INVITE_CREDIT_TYPE_ACCOUNT_OPEN = "account_open"
LEGACY_INVITE_CREDIT_TYPE = "invite_credit"
INVITE_CREDIT_TYPES = {INVITE_CREDIT_TYPE_GROUP, INVITE_CREDIT_TYPE_ACCOUNT_OPEN}
INVITE_CREDIT_TYPE_TEXT = {
    INVITE_CREDIT_TYPE_GROUP: "入群资格",
    INVITE_CREDIT_TYPE_ACCOUNT_OPEN: "注册资格",
}
INVITE_CREDIT_SOURCE_QUALIFICATION_REVOKE = "qualification_revoke"
INVITE_CREDIT_SOURCE_SLOT_BOX = "slot_box"
INVITE_RECORD_ACTIVE_STATUSES = {"pending"}
INVITE_RECORD_FINAL_STATUSES = {"approved", "declined", "revoked", "expired", "granted"}
GROUP_INVITE_CONSUMING_STATUSES = {"pending", "approved", "expired"}


def utcnow() -> datetime:
    return datetime.utcnow()


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TZ)
    return value.astimezone(SHANGHAI_TZ).isoformat()


def _first_config_group_id() -> int | None:
    for raw in group:
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


class InviteSetting(Base):
    __tablename__ = "invite_settings"

    setting_key = Column(String(64), primary_key=True)
    setting_value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class InviteCredit(Base):
    __tablename__ = "invite_credits"
    __table_args__ = (
        Index("ix_invite_credits_owner_status", "owner_tg", "consumed_at", "revoked_at"),
        Index("ix_invite_credits_type_owner_status", "credit_type", "owner_tg", "consumed_at", "revoked_at"),
        Index("ix_invite_credits_source", "source", "source_ref"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    credit_type = Column(String(32), default=INVITE_CREDIT_TYPE_GROUP, nullable=False)
    owner_tg = Column(BigInteger, nullable=False)
    invite_days = Column(Integer, default=0, nullable=False)
    source = Column(String(32), default="admin", nullable=False)
    source_ref = Column(String(128), nullable=True)
    granted_by_tg = Column(BigInteger, nullable=True)
    note = Column(String(255), nullable=True)
    consumed_record_id = Column(Integer, nullable=True)
    granted_at = Column(DateTime, default=utcnow, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_tg = Column(BigInteger, nullable=True)
    revoke_reason = Column(String(255), nullable=True)


class InviteRecord(Base):
    __tablename__ = "invite_records"
    __table_args__ = (
        Index("ix_invite_records_inviter", "inviter_tg", "created_at"),
        Index("ix_invite_records_invitee", "invitee_tg", "created_at"),
        Index("ix_invite_records_type_inviter", "record_type", "inviter_tg", "created_at"),
        Index("ix_invite_records_status", "status", "expires_at"),
        Index("ix_invite_records_link", "target_chat_id", "invite_link"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    credit_id = Column(Integer, ForeignKey("invite_credits.id", ondelete="SET NULL"), nullable=True)
    record_type = Column(String(32), default=INVITE_CREDIT_TYPE_GROUP, nullable=False)
    inviter_tg = Column(BigInteger, nullable=False)
    invitee_tg = Column(BigInteger, nullable=False)
    target_chat_id = Column(BigInteger, nullable=False)
    invite_link = Column(String(512), nullable=False)
    invite_days = Column(Integer, default=0, nullable=False)
    link_name = Column(String(128), nullable=True)
    status = Column(String(32), default="pending", nullable=False)
    created_by_tg = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    reviewed_by_tg = Column(BigInteger, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)
    last_request_tg = Column(BigInteger, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)


def has_viewing_access(user: Emby | None) -> bool:
    if user is None or not user.embyid:
        return False
    return str(user.lv or "").lower() in {"a", "b"}


def normalize_invite_credit_type(value: str | None) -> str:
    normalized = str(value or INVITE_CREDIT_TYPE_GROUP).strip().lower()
    if normalized == LEGACY_INVITE_CREDIT_TYPE:
        return INVITE_CREDIT_TYPE_GROUP
    if normalized not in INVITE_CREDIT_TYPES:
        raise ValueError("邀请资格类型不正确")
    return normalized


def invite_credit_type_text(credit_type: str | None) -> str:
    try:
        normalized = normalize_invite_credit_type(credit_type)
    except ValueError:
        normalized = INVITE_CREDIT_TYPE_GROUP
    return INVITE_CREDIT_TYPE_TEXT.get(normalized, normalized)


def normalize_invite_days(value: int | None = None) -> int:
    try:
        days = int(value or 0)
    except (TypeError, ValueError):
        days = 0
    if days <= 0:
        days = int(get_invite_settings().get("account_open_days") or DEFAULT_INVITE_SETTINGS["account_open_days"])
    return min(max(days, 1), 3650)


def _sanitize_invite_settings(data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_INVITE_SETTINGS)
    merged.update(data or {})
    merged["enabled"] = bool(merged.get("enabled", False))

    raw_group_verification = merged.get("group_verification_enabled")
    if raw_group_verification is None:
        raw_group_verification = merged.get("strict_target", True)
    merged["group_verification_enabled"] = bool(raw_group_verification)
    merged["strict_target"] = bool(merged["group_verification_enabled"])

    raw_channel_verification = merged.get("channel_verification_enabled")
    if raw_channel_verification is None:
        raw_channel_verification = DEFAULT_INVITE_SETTINGS["channel_verification_enabled"]
    merged["channel_verification_enabled"] = bool(raw_channel_verification)

    raw_chat = merged.get("target_chat_id")
    if raw_chat in {"", 0, "0"}:
        raw_chat = None
    try:
        merged["target_chat_id"] = int(raw_chat) if raw_chat is not None else _first_config_group_id()
    except (TypeError, ValueError):
        merged["target_chat_id"] = _first_config_group_id()

    try:
        expire_hours = int(merged.get("expire_hours", DEFAULT_INVITE_SETTINGS["expire_hours"]) or 24)
    except (TypeError, ValueError):
        expire_hours = DEFAULT_INVITE_SETTINGS["expire_hours"]
    merged["expire_hours"] = min(max(expire_hours, 1), 168)

    try:
        account_open_days = int(merged.get("account_open_days", DEFAULT_INVITE_SETTINGS["account_open_days"]) or 30)
    except (TypeError, ValueError):
        account_open_days = DEFAULT_INVITE_SETTINGS["account_open_days"]
    merged["account_open_days"] = min(max(account_open_days, 1), 3650)
    return merged


def get_invite_settings() -> dict[str, Any]:
    with Session() as session:
        rows = session.query(InviteSetting).all()
        data = {row.setting_key: row.setting_value for row in rows}
    return _sanitize_invite_settings(data)


def set_invite_settings(patch: dict[str, Any]) -> dict[str, Any]:
    clean = _sanitize_invite_settings({**get_invite_settings(), **(patch or {})})
    writable = {
        "enabled": clean["enabled"],
        "target_chat_id": clean["target_chat_id"],
        "expire_hours": clean["expire_hours"],
        "strict_target": clean["strict_target"],
        "group_verification_enabled": clean["group_verification_enabled"],
        "channel_verification_enabled": clean["channel_verification_enabled"],
        "account_open_days": clean["account_open_days"],
    }
    with Session() as session:
        for key, value in writable.items():
            row = session.query(InviteSetting).filter(InviteSetting.setting_key == key).first()
            if row is None:
                row = InviteSetting(setting_key=key, setting_value=value)
                session.add(row)
            else:
                row.setting_value = value
        session.commit()
    return get_invite_settings()


def invite_credit_status(row: InviteCredit) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if row.consumed_at is not None:
        return "used"
    return "available"


def serialize_invite_credit(row: InviteCredit | None) -> dict[str, Any] | None:
    if row is None:
        return None
    status = invite_credit_status(row)
    credit_type = normalize_invite_credit_type(row.credit_type)
    return {
        "id": row.id,
        "credit_type": credit_type,
        "credit_type_text": invite_credit_type_text(credit_type),
        "owner_tg": int(row.owner_tg),
        "invite_days": int(row.invite_days or 0),
        "source": row.source,
        "source_ref": row.source_ref,
        "granted_by_tg": row.granted_by_tg,
        "note": row.note or "",
        "consumed_record_id": row.consumed_record_id,
        "status": status,
        "status_text": {"available": "可用", "used": "已使用", "revoked": "已删除"}.get(status, status),
        "available": status == "available",
        "granted_at": serialize_datetime(row.granted_at),
        "consumed_at": serialize_datetime(row.consumed_at),
        "revoked_at": serialize_datetime(row.revoked_at),
        "revoked_by_tg": row.revoked_by_tg,
        "revoke_reason": row.revoke_reason or "",
    }


def serialize_invite_record(row: InviteRecord | None) -> dict[str, Any] | None:
    if row is None:
        return None
    record_type = normalize_invite_credit_type(row.record_type)
    if record_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
        status_text = {
            "pending": "待审核",
            "approved": "已发放",
            "granted": "已发放",
            "declined": "已拒绝",
            "revoked": "已撤销",
            "expired": "已过期",
        }.get(row.status, row.status)
    else:
        status_text = {
            "pending": "待入群",
            "approved": "已入群",
            "declined": "已拒绝",
            "revoked": "已撤销",
            "expired": "已过期",
            "granted": "已发放",
        }.get(row.status, row.status)
    return {
        "id": row.id,
        "credit_id": row.credit_id,
        "record_type": record_type,
        "record_type_text": invite_credit_type_text(record_type),
        "inviter_tg": int(row.inviter_tg),
        "invitee_tg": int(row.invitee_tg),
        "target_chat_id": int(row.target_chat_id),
        "invite_link": row.invite_link,
        "invite_days": int(row.invite_days or 0),
        "link_name": row.link_name or "",
        "status": row.status,
        "status_text": status_text,
        "created_by_tg": row.created_by_tg,
        "created_at": serialize_datetime(row.created_at),
        "expires_at": serialize_datetime(row.expires_at),
        "used_at": serialize_datetime(row.used_at),
        "revoked_at": serialize_datetime(row.revoked_at),
        "reviewed_by_tg": row.reviewed_by_tg,
        "reviewed_at": serialize_datetime(row.reviewed_at),
        "review_note": row.review_note or "",
        "last_request_tg": row.last_request_tg,
        "metadata": row.metadata_json or {},
        "note": row.note or "",
    }


def _require_invite_owner(
    session,
    owner_tg: int,
    credit_type: str | None = None,
    *,
    for_update: bool = False,
) -> Emby:
    query = session.query(Emby).filter(Emby.tg == int(owner_tg))
    if for_update:
        # 先锁住发起人，避免并发请求把同一资格重复创建出来。
        query = query.with_for_update()
    user = query.first()
    if not has_viewing_access(user):
        label = invite_credit_type_text(credit_type)
        raise ValueError(f"只有拥有 Emby 观影资格的用户才能获取{label}")
    return user


def _owner_has_account_open_history(session, owner_tg: int) -> bool:
    return (
        session.query(InviteRecord.id)
        .filter(
            InviteRecord.inviter_tg == int(owner_tg),
            InviteRecord.record_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
            InviteRecord.status.in_(["pending", "approved", "granted"]),
        )
        .first()
        is not None
    )


def _owner_has_account_open_credit(session, owner_tg: int) -> bool:
    return (
        session.query(InviteCredit.id)
        .filter(
            InviteCredit.owner_tg == int(owner_tg),
            InviteCredit.credit_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
            InviteCredit.revoked_at.is_(None),
        )
        .first()
        is not None
    )


def validate_invite_credit_grant(
    *,
    owner_tg: int,
    count: int = 1,
    credit_type: str = INVITE_CREDIT_TYPE_GROUP,
) -> None:
    normalized_type = normalize_invite_credit_type(credit_type)
    if normalized_type == INVITE_CREDIT_TYPE_GROUP:
        raise ValueError("入群资格已改为观影用户自动拥有一次，不支持手动发放")
    if normalized_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
        raise ValueError("注册资格已改为申请制，请在后台处理开通申请或使用后台代发")
    with Session() as session:
        _require_invite_owner(session, int(owner_tg), normalized_type)
        if _qualification_revoked(session, int(owner_tg), normalized_type) is not None:
            raise ValueError(f"该用户的{invite_credit_type_text(normalized_type)}已被后台撤销")
        if normalized_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
            if int(count or 1) != 1:
                raise ValueError("注册资格每次只能发放 1 个")
            if _owner_has_account_open_credit(session, int(owner_tg)) or _owner_has_account_open_history(session, int(owner_tg)):
                raise ValueError("该用户已经拥有或使用过注册资格，每个观影用户只能提交一次开通申请")


def _available_invite_credit_query(session, owner_tg: int, credit_type: str):
    return session.query(InviteCredit).filter(
        InviteCredit.owner_tg == int(owner_tg),
        InviteCredit.credit_type == normalize_invite_credit_type(credit_type),
        InviteCredit.source != INVITE_CREDIT_SOURCE_QUALIFICATION_REVOKE,
        InviteCredit.consumed_at.is_(None),
        InviteCredit.revoked_at.is_(None),
    )


def _available_invite_credit_count_in_session(session, owner_tg: int, credit_type: str) -> int:
    return int(_available_invite_credit_query(session, owner_tg, credit_type).count() or 0)


def _available_invite_credit_row(session, owner_tg: int, credit_type: str, *, for_update: bool = False) -> InviteCredit | None:
    query = _available_invite_credit_query(session, owner_tg, credit_type).order_by(InviteCredit.id.asc())
    if for_update:
        query = query.with_for_update()
    return query.first()


def invite_credit_summary(owner_tg: int | None = None, *, credit_type: str | None = None) -> dict[str, int]:
    normalized_type = normalize_invite_credit_type(credit_type) if credit_type else None
    with Session() as session:
        query = session.query(InviteCredit)
        query = query.filter(InviteCredit.source != INVITE_CREDIT_SOURCE_QUALIFICATION_REVOKE)
        if owner_tg is not None:
            query = query.filter(InviteCredit.owner_tg == int(owner_tg))
        if normalized_type is not None:
            query = query.filter(InviteCredit.credit_type == normalized_type)
        total = query.count()
        available = query.filter(InviteCredit.consumed_at.is_(None), InviteCredit.revoked_at.is_(None)).count()
        used = query.filter(InviteCredit.consumed_at.isnot(None)).count()
        revoked = query.filter(InviteCredit.revoked_at.isnot(None)).count()
    return {
        "total": int(total or 0),
        "available": int(available or 0),
        "used": int(used or 0),
        "revoked": int(revoked or 0),
    }


def grant_invite_credits(
    *,
    owner_tg: int,
    count: int = 1,
    granted_by_tg: int | None = None,
    source: str = "admin",
    source_ref: str | None = None,
    note: str = "",
    credit_type: str = INVITE_CREDIT_TYPE_GROUP,
    invite_days: int | None = None,
) -> list[dict[str, Any]]:
    normalized_type = normalize_invite_credit_type(credit_type)
    if normalized_type == INVITE_CREDIT_TYPE_GROUP:
        raise ValueError("入群资格已改为观影用户自动拥有一次，不支持手动发放")
    if normalized_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
        raise ValueError("注册资格已改为申请制，请在后台处理开通申请或使用后台代发")
    normalized_count = min(max(int(count or 1), 1), 500)
    if normalized_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
        if int(count or 1) != 1:
            raise ValueError("注册资格每次只能发放 1 个")
        normalized_count = 1
    normalized_days = normalize_invite_days(invite_days) if normalized_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN else 0
    with Session() as session:
        _require_invite_owner(session, int(owner_tg), normalized_type)
        if normalized_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN and (
            _owner_has_account_open_credit(session, int(owner_tg)) or _owner_has_account_open_history(session, int(owner_tg))
        ):
            raise ValueError("该用户已经拥有或使用过注册资格，每个观影用户只能提交一次开通申请")
        rows = [
            InviteCredit(
                credit_type=normalized_type,
                owner_tg=int(owner_tg),
                invite_days=normalized_days,
                granted_by_tg=int(granted_by_tg) if granted_by_tg is not None else None,
                source=str(source or "admin")[:32],
                source_ref=str(source_ref or "").strip()[:128] or None,
                note=str(note or "").strip()[:255] or None,
            )
            for _ in range(normalized_count)
        ]
        session.add_all(rows)
        session.commit()
        for row in rows:
            session.refresh(row)
        return [serialize_invite_credit(row) for row in rows]


def list_invite_credits(
    *,
    owner_tg: int | None = None,
    status: str = "all",
    credit_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    expire_stale_invites()
    normalized_status = str(status or "all").lower()
    normalized_type = normalize_invite_credit_type(credit_type) if credit_type else None
    with Session() as session:
        query = session.query(InviteCredit)
        query = query.filter(InviteCredit.source != INVITE_CREDIT_SOURCE_QUALIFICATION_REVOKE)
        if owner_tg is not None:
            query = query.filter(InviteCredit.owner_tg == int(owner_tg))
        if normalized_type is not None:
            query = query.filter(InviteCredit.credit_type == normalized_type)
        if normalized_status == "available":
            query = query.filter(InviteCredit.consumed_at.is_(None), InviteCredit.revoked_at.is_(None))
        elif normalized_status == "used":
            query = query.filter(InviteCredit.consumed_at.isnot(None))
        elif normalized_status == "revoked":
            query = query.filter(InviteCredit.revoked_at.isnot(None))
        rows = (
            query.order_by(InviteCredit.id.desc())
            .limit(min(max(int(limit or 100), 1), 500))
            .all()
        )
        return [serialize_invite_credit(row) for row in rows]


def available_invite_credit_count(owner_tg: int, *, credit_type: str = INVITE_CREDIT_TYPE_GROUP) -> int:
    normalized_type = normalize_invite_credit_type(credit_type)
    if normalized_type == INVITE_CREDIT_TYPE_GROUP:
        return available_group_invite_credit_count(owner_tg)
    with Session() as session:
        if _qualification_revoked(session, int(owner_tg), normalized_type) is not None:
            return 0
        return _available_invite_credit_count_in_session(session, int(owner_tg), normalized_type)


def user_has_group_invite_history(owner_tg: int) -> bool:
    with Session() as session:
        return (
            session.query(InviteRecord.id)
            .filter(
                InviteRecord.inviter_tg == int(owner_tg),
                InviteRecord.record_type == INVITE_CREDIT_TYPE_GROUP,
                InviteRecord.credit_id.is_(None),
                InviteRecord.status.in_(list(GROUP_INVITE_CONSUMING_STATUSES)),
            )
            .first()
            is not None
        )


def user_has_account_open_history(owner_tg: int) -> bool:
    with Session() as session:
        return _owner_has_account_open_history(session, int(owner_tg))


def _qualification_revoked(session, owner_tg: int, credit_type: str) -> InviteCredit | None:
    return (
        session.query(InviteCredit)
        .filter(
            InviteCredit.owner_tg == int(owner_tg),
            InviteCredit.credit_type == credit_type,
            InviteCredit.source == INVITE_CREDIT_SOURCE_QUALIFICATION_REVOKE,
            InviteCredit.revoked_at.is_(None),
        )
        .first()
    )


def qualification_revoked(owner_tg: int, *, credit_type: str) -> bool:
    normalized_type = normalize_invite_credit_type(credit_type)
    with Session() as session:
        return _qualification_revoked(session, int(owner_tg), normalized_type) is not None


def grant_slot_group_invite_credit(
    *,
    owner_tg: int,
    granted_by_tg: int | None = None,
    source_ref: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    with Session() as session:
        if _qualification_revoked(session, int(owner_tg), INVITE_CREDIT_TYPE_GROUP) is not None:
            raise ValueError("你的入群邀请资格已被后台撤销")
        row = InviteCredit(
            credit_type=INVITE_CREDIT_TYPE_GROUP,
            owner_tg=int(owner_tg),
            invite_days=0,
            granted_by_tg=int(granted_by_tg) if granted_by_tg is not None else None,
            source=INVITE_CREDIT_SOURCE_SLOT_BOX,
            source_ref=str(source_ref or "").strip()[:128] or None,
            note=str(note or "老虎机背包使用邀请资格").strip()[:255] or None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_invite_credit(row)


def set_invite_qualification(
    *,
    owner_tg: int,
    credit_type: str,
    enabled: bool,
    actor_tg: int | None = None,
    reason: str = "",
) -> dict[str, Any]:
    normalized_type = normalize_invite_credit_type(credit_type)
    with Session() as session:
        _require_invite_owner(session, int(owner_tg), normalized_type)
        row = _qualification_revoked(session, int(owner_tg), normalized_type)
        if enabled:
            if row is not None:
                row.revoked_at = utcnow()
                row.revoked_by_tg = int(actor_tg) if actor_tg is not None else None
                row.revoke_reason = str(reason or "后台恢复资格").strip()[:255] or None
        elif row is None:
            session.add(
                InviteCredit(
                    credit_type=normalized_type,
                    owner_tg=int(owner_tg),
                    invite_days=0,
                    source=INVITE_CREDIT_SOURCE_QUALIFICATION_REVOKE,
                    granted_by_tg=int(actor_tg) if actor_tg is not None else None,
                    note=str(reason or "后台撤销资格").strip()[:255] or None,
                )
            )
        session.commit()
    return invite_qualification_status(owner_tg)


def invite_qualification_status(owner_tg: int) -> dict[str, Any]:
    with Session() as session:
        account = session.query(Emby).filter(Emby.tg == int(owner_tg)).first()
        viewing_access = has_viewing_access(account)
        group_revoked = _qualification_revoked(session, int(owner_tg), INVITE_CREDIT_TYPE_GROUP) is not None
        account_revoked = _qualification_revoked(session, int(owner_tg), INVITE_CREDIT_TYPE_ACCOUNT_OPEN) is not None
        manual_group_count = 0 if group_revoked else _available_invite_credit_count_in_session(
            session, int(owner_tg), INVITE_CREDIT_TYPE_GROUP
        )
        group_history = (
            session.query(InviteRecord.id)
            .filter(
                InviteRecord.inviter_tg == int(owner_tg),
                InviteRecord.record_type == INVITE_CREDIT_TYPE_GROUP,
                InviteRecord.credit_id.is_(None),
                InviteRecord.status.in_(list(GROUP_INVITE_CONSUMING_STATUSES)),
            )
            .first()
            is not None
        )
        account_history = _owner_has_account_open_history(session, int(owner_tg))
        automatic_group_available = bool(viewing_access and not group_revoked and not group_history)
    group_available_credits = int(manual_group_count or 0) + (1 if automatic_group_available else 0)
    return {
        "owner_tg": int(owner_tg),
        "has_viewing_access": bool(viewing_access),
        "group_join": {
            "revoked": bool(group_revoked),
            "used": bool(group_history),
            "available": group_available_credits > 0,
            "available_credits": group_available_credits,
        },
        "account_open": {
            "revoked": bool(account_revoked),
            "used": bool(account_history),
            "available": bool(viewing_access and not account_revoked and not account_history),
        },
    }


def available_group_invite_credit_count(owner_tg: int) -> int:
    with Session() as session:
        if _qualification_revoked(session, int(owner_tg), INVITE_CREDIT_TYPE_GROUP) is not None:
            return 0
        manual_count = _available_invite_credit_count_in_session(session, int(owner_tg), INVITE_CREDIT_TYPE_GROUP)
        user = session.query(Emby).filter(Emby.tg == int(owner_tg)).first()
        automatic_count = 0
        if has_viewing_access(user):
            consumed = (
                session.query(InviteRecord.id)
                .filter(
                    InviteRecord.inviter_tg == int(owner_tg),
                    InviteRecord.record_type == INVITE_CREDIT_TYPE_GROUP,
                    InviteRecord.credit_id.is_(None),
                    InviteRecord.status.in_(list(GROUP_INVITE_CONSUMING_STATUSES)),
                )
                .first()
                is not None
            )
            automatic_count = 0 if consumed else 1
        return int(manual_count or 0) + automatic_count


def revoke_invite_credit(credit_id: int, *, revoked_by_tg: int | None = None, reason: str = "") -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(InviteCredit).filter(InviteCredit.id == int(credit_id)).first()
        if row is None:
            return None
        if row.consumed_at is None:
            row.revoked_at = utcnow()
            row.revoked_by_tg = int(revoked_by_tg) if revoked_by_tg is not None else None
            row.revoke_reason = str(reason or "").strip()[:255] or None
        session.commit()
        session.refresh(row)
        return serialize_invite_credit(row)


def create_invite_record(
    *,
    inviter_tg: int,
    invitee_tg: int,
    target_chat_id: int,
    invite_link: str,
    link_name: str = "",
    expires_at: datetime | None = None,
    created_by_tg: int | None = None,
    note: str = "",
) -> dict[str, Any]:
    normalized_type = INVITE_CREDIT_TYPE_GROUP
    inviter = int(inviter_tg)
    invitee = int(invitee_tg)
    if invitee <= 0:
        raise ValueError("被邀请人 TGID 不正确")
    if invitee == inviter:
        raise ValueError("不能把邀请码发给自己")

    now = utcnow()
    with Session() as session:
        if _qualification_revoked(session, inviter, normalized_type) is not None:
            raise ValueError("你的入群邀请资格已被后台撤销")
        manual_credit = _available_invite_credit_row(session, inviter, normalized_type, for_update=True)
        if manual_credit is None:
            _require_invite_owner(session, inviter, normalized_type, for_update=True)
        existing = (
            session.query(InviteRecord)
            .filter(
                InviteRecord.invitee_tg == invitee,
                InviteRecord.target_chat_id == int(target_chat_id),
                InviteRecord.record_type == normalized_type,
                InviteRecord.status.in_(list(INVITE_RECORD_ACTIVE_STATUSES)),
            )
            .first()
        )
        if existing is not None and (existing.expires_at is None or existing.expires_at > now):
            raise ValueError("该用户已经有一条待使用的邀请码")

        if manual_credit is None:
            existing_by_inviter = (
                session.query(InviteRecord)
                .filter(
                    InviteRecord.inviter_tg == inviter,
                    InviteRecord.record_type == normalized_type,
                    InviteRecord.credit_id.is_(None),
                    InviteRecord.status.in_(list(GROUP_INVITE_CONSUMING_STATUSES)),
                )
                .with_for_update()
                .first()
            )
            if existing_by_inviter is not None:
                raise ValueError("你已经使用过本次入群邀请资格")

        record = InviteRecord(
            credit_id=int(manual_credit.id) if manual_credit is not None else None,
            record_type=normalized_type,
            inviter_tg=inviter,
            invitee_tg=invitee,
            target_chat_id=int(target_chat_id),
            invite_link=str(invite_link).strip(),
            invite_days=0,
            link_name=str(link_name or "").strip()[:128] or None,
            status="pending",
            created_by_tg=int(created_by_tg) if created_by_tg is not None else inviter,
            expires_at=expires_at,
            note=str(note or "").strip() or None,
        )
        session.add(record)
        session.flush()
        if manual_credit is not None:
            manual_credit.consumed_at = now
            manual_credit.consumed_record_id = int(record.id)
        session.commit()
        session.refresh(record)
        return serialize_invite_record(record)


def create_account_open_invite_record(
    *,
    inviter_tg: int,
    invitee_tg: int,
    created_by_tg: int | None = None,
    note: str = "",
    auto_approve: bool = False,
    reviewed_by_tg: int | None = None,
    review_note: str = "",
) -> dict[str, Any]:
    inviter = int(inviter_tg)
    invitee = int(invitee_tg)
    if invitee <= 0:
        raise ValueError("被邀请人 TGID 不正确")
    if invitee == inviter:
        raise ValueError("不能给自己提交开通申请")

    with Session() as session:
        _require_invite_owner(session, inviter, INVITE_CREDIT_TYPE_ACCOUNT_OPEN, for_update=True)
        if _qualification_revoked(session, inviter, INVITE_CREDIT_TYPE_ACCOUNT_OPEN) is not None:
            raise ValueError("你的开通申请资格已被后台撤销")
        if _owner_has_account_open_history(session, inviter):
            raise ValueError("该用户已经提交或完成过开通申请，不能重复申请")

        invitee_row = session.query(Emby).filter(Emby.tg == invitee).with_for_update().first()
        if invitee_row is None:
            invitee_row = Emby(tg=invitee, lv="d", us=0, iv=0)
            session.add(invitee_row)
            session.flush()
        if invitee_row.embyid:
            raise ValueError("被邀请人已经拥有 Emby 账号，不能发放注册资格")
        if int(invitee_row.us or 0) > 0:
            raise ValueError("被邀请人已经拥有注册资格，请先使用现有资格")

        now = utcnow()
        invite_days = normalize_invite_days(None)
        status = "approved" if auto_approve else "pending"
        record = InviteRecord(
            credit_id=None,
            record_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
            inviter_tg=inviter,
            invitee_tg=invitee,
            target_chat_id=0,
            invite_link="",
            invite_days=invite_days,
            link_name=None,
            status=status,
            created_by_tg=int(created_by_tg) if created_by_tg is not None else inviter,
            created_at=now,
            used_at=now if auto_approve else None,
            reviewed_by_tg=int(reviewed_by_tg) if reviewed_by_tg is not None else (
                int(created_by_tg) if auto_approve and created_by_tg is not None else None
            ),
            reviewed_at=now if auto_approve else None,
            review_note=str(review_note or "").strip() or None,
            metadata_json={"credited_us": invite_days} if auto_approve else {},
            note=str(note or "").strip() or None,
        )
        session.add(record)
        session.flush()
        if auto_approve:
            invitee_row.us = int(invitee_row.us or 0) + invite_days
        session.commit()
        session.refresh(record)
        result = serialize_invite_record(record)

    if auto_approve:
        sql_invalidate_emby_cache(invitee)
    return result


def update_invite_credit(
    credit_id: int,
    *,
    owner_tg: int | None = None,
    invite_days: int | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(InviteCredit).filter(InviteCredit.id == int(credit_id)).with_for_update().first()
        if row is None:
            return None
        if row.consumed_at is not None or row.revoked_at is not None:
            raise ValueError("已使用或已删除的资格不能编辑")
        credit_type = normalize_invite_credit_type(row.credit_type)
        if owner_tg is not None:
            new_owner = int(owner_tg)
            _require_invite_owner(session, new_owner, credit_type)
            if credit_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN and new_owner != int(row.owner_tg):
                if _owner_has_account_open_credit(session, new_owner) or _owner_has_account_open_history(session, new_owner):
                    raise ValueError("新归属用户已经拥有或使用过注册资格")
            row.owner_tg = new_owner
        if invite_days is not None and credit_type == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
            row.invite_days = normalize_invite_days(invite_days)
        if note is not None:
            row.note = str(note or "").strip()[:255] or None
        session.commit()
        session.refresh(row)
        return serialize_invite_credit(row)


def approve_account_open_invite_record(
    record_id: int,
    *,
    reviewer_tg: int | None = None,
    invite_days: int | None = None,
    review_note: str = "",
) -> dict[str, Any] | None:
    invitee = None
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).with_for_update().first()
        if row is None:
            return None
        if normalize_invite_credit_type(row.record_type) != INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
            raise ValueError("该记录不是开通申请")
        if row.status != "pending":
            raise ValueError("只有待审核的开通申请可以通过")

        invitee = int(row.invitee_tg)
        invitee_row = session.query(Emby).filter(Emby.tg == invitee).with_for_update().first()
        if invitee_row is None:
            invitee_row = Emby(tg=invitee, lv="d", us=0, iv=0)
            session.add(invitee_row)
            session.flush()
        if invitee_row.embyid:
            raise ValueError("被申请人已经拥有 Emby 账号，不能发放注册资格")
        if int(invitee_row.us or 0) > 0:
            raise ValueError("被申请人已经拥有注册资格，请先使用现有资格")

        now = utcnow()
        days = normalize_invite_days(invite_days or row.invite_days)
        row.invite_days = days
        row.status = "approved"
        row.used_at = now
        row.reviewed_by_tg = int(reviewer_tg) if reviewer_tg is not None else None
        row.reviewed_at = now
        row.review_note = str(review_note or "").strip() or None
        row.metadata_json = {**(row.metadata_json or {}), "credited_us": days}
        invitee_row.us = int(invitee_row.us or 0) + days
        session.commit()
        session.refresh(row)
        result = serialize_invite_record(row)

    if invitee is not None:
        sql_invalidate_emby_cache(invitee)
    return result


def decline_account_open_invite_record(
    record_id: int,
    *,
    reviewer_tg: int | None = None,
    review_note: str = "",
) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).with_for_update().first()
        if row is None:
            return None
        if normalize_invite_credit_type(row.record_type) != INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
            raise ValueError("该记录不是开通申请")
        if row.status != "pending":
            raise ValueError("只有待审核的开通申请可以拒绝")
        row.status = "declined"
        row.reviewed_by_tg = int(reviewer_tg) if reviewer_tg is not None else None
        row.reviewed_at = utcnow()
        row.review_note = str(review_note or "").strip() or None
        session.commit()
        session.refresh(row)
        return serialize_invite_record(row)


def revoke_account_open_invite_record(
    record_id: int,
    *,
    reviewer_tg: int | None = None,
    review_note: str = "",
) -> dict[str, Any] | None:
    invitee = None
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).with_for_update().first()
        if row is None:
            return None
        if normalize_invite_credit_type(row.record_type) != INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
            raise ValueError("该记录不是开通申请")
        if row.status == "revoked":
            session.refresh(row)
            return serialize_invite_record(row)
        if row.status not in {"pending", "approved", "granted"}:
            raise ValueError("当前状态不能撤销")

        now = utcnow()
        if row.status in {"approved", "granted"}:
            invitee = int(row.invitee_tg)
            invitee_row = session.query(Emby).filter(Emby.tg == invitee).with_for_update().first()
            if invitee_row is not None and not invitee_row.embyid:
                credited = int((row.metadata_json or {}).get("credited_us") or row.invite_days or 0)
                if credited > 0:
                    invitee_row.us = max(int(invitee_row.us or 0) - credited, 0)
        row.status = "revoked"
        row.revoked_at = now
        row.reviewed_by_tg = int(reviewer_tg) if reviewer_tg is not None else row.reviewed_by_tg
        row.reviewed_at = now
        row.review_note = str(review_note or "").strip() or row.review_note
        session.commit()
        session.refresh(row)
        result = serialize_invite_record(row)

    if invitee is not None:
        sql_invalidate_emby_cache(invitee)
    return result


def expire_stale_invites() -> int:
    now = utcnow()
    with Session() as session:
        changed = (
            session.query(InviteRecord)
            .filter(
                InviteRecord.status == "pending",
                InviteRecord.expires_at.isnot(None),
                InviteRecord.expires_at < now,
            )
            .update({InviteRecord.status: "expired"}, synchronize_session=False)
        )
        if changed:
            session.commit()
        else:
            session.rollback()
        return int(changed or 0)


def list_invite_records(
    *,
    status: str = "all",
    inviter_tg: int | None = None,
    invitee_tg: int | None = None,
    credit_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    expire_stale_invites()
    normalized_status = str(status or "all").lower()
    normalized_type = normalize_invite_credit_type(credit_type) if credit_type else None
    with Session() as session:
        query = session.query(InviteRecord)
        if normalized_status != "all":
            query = query.filter(InviteRecord.status == normalized_status)
        if inviter_tg is not None:
            query = query.filter(InviteRecord.inviter_tg == int(inviter_tg))
        if invitee_tg is not None:
            query = query.filter(InviteRecord.invitee_tg == int(invitee_tg))
        if normalized_type is not None:
            query = query.filter(InviteRecord.record_type == normalized_type)
        rows = (
            query.order_by(InviteRecord.id.desc())
            .limit(min(max(int(limit or 100), 1), 500))
            .all()
        )
        return [serialize_invite_record(row) for row in rows]


def get_invite_record(record_id: int) -> dict[str, Any] | None:
    expire_stale_invites()
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).first()
        return serialize_invite_record(row)


def find_pending_invite_by_link(target_chat_id: int, invite_link: str) -> dict[str, Any] | None:
    expire_stale_invites()
    link = str(invite_link or "").strip()
    if not link:
        return None
    with Session() as session:
        row = (
            session.query(InviteRecord)
            .filter(
                InviteRecord.target_chat_id == int(target_chat_id),
                InviteRecord.invite_link == link,
                InviteRecord.record_type == INVITE_CREDIT_TYPE_GROUP,
                InviteRecord.status == "pending",
            )
            .first()
        )
        return serialize_invite_record(row)


def mark_invite_record_request(record_id: int, requester_tg: int, status: str | None = None) -> dict[str, Any] | None:
    normalized_status = str(status or "").strip().lower() or None
    if normalized_status is not None and normalized_status not in INVITE_RECORD_ACTIVE_STATUSES.union(INVITE_RECORD_FINAL_STATUSES):
        raise ValueError("邀请状态不正确")
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).with_for_update().first()
        if row is None:
            return None
        row.last_request_tg = int(requester_tg)
        if normalized_status:
            row.status = normalized_status
            if normalized_status == "approved":
                row.used_at = utcnow()
            if normalized_status == "revoked":
                row.revoked_at = utcnow()
        session.commit()
        session.refresh(row)
        return serialize_invite_record(row)


def revoke_invite_record(record_id: int, *, requester_tg: int | None = None) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).with_for_update().first()
        if row is None:
            return None
        if normalize_invite_credit_type(row.record_type) == INVITE_CREDIT_TYPE_ACCOUNT_OPEN:
            raise ValueError("开通申请请使用审核撤销")
        if row.status == "pending":
            row.status = "revoked"
            row.revoked_at = utcnow()
            if requester_tg is not None:
                row.last_request_tg = int(requester_tg)
        session.commit()
        session.refresh(row)
        return serialize_invite_record(row)


def cancel_pending_invite_record(record_id: int, *, reason: str = "") -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(InviteRecord).filter(InviteRecord.id == int(record_id)).with_for_update().first()
        if row is None:
            return None
        if row.status == "pending":
            row.status = "revoked"
            row.revoked_at = utcnow()
            row.note = str(reason or "").strip() or row.note
            if row.credit_id is not None:
                credit = session.query(InviteCredit).filter(InviteCredit.id == int(row.credit_id)).with_for_update().first()
                if credit is not None and credit.consumed_record_id == row.id:
                    credit.consumed_at = None
                    credit.consumed_record_id = None
        session.commit()
        session.refresh(row)
        return serialize_invite_record(row)
