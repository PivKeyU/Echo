from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from bot.sql_helper import Session
from .models import XiuxianWebAccount, XiuxianWebSession, utcnow


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = max(int(os.getenv("PIVKEYU_XIUXIAN_PASSWORD_ITERATIONS", "200000") or 200000), 120000)
WEB_SESSION_DAYS = max(int(os.getenv("PIVKEYU_XIUXIAN_WEB_SESSION_DAYS", "30") or 30), 1)
WEB_SESSION_CACHE_TTL = max(int(os.getenv("PIVKEYU_XIUXIAN_WEB_SESSION_CACHE_TTL", "30") or 30), 5)
WEB_LOGIN_FAILURE_LIMIT = max(int(os.getenv("PIVKEYU_WEB_LOGIN_FAILURE_LIMIT", "6") or 6), 1)
WEB_LOGIN_FAILURE_WINDOW = max(int(os.getenv("PIVKEYU_WEB_LOGIN_FAILURE_WINDOW", "300") or 300), 30)
WEB_LOGIN_MAX_CONCURRENCY = max(int(os.getenv("PIVKEYU_WEB_LOGIN_MAX_CONCURRENCY", "4") or 4), 1)
_WEB_AUTH_CACHE_LOCK = threading.RLock()
_WEB_AUTH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_WEB_LOGIN_LOCK = threading.RLock()
_WEB_LOGIN_FAILURES: dict[str, list[float]] = {}
_WEB_LOGIN_SLOTS = threading.BoundedSemaphore(WEB_LOGIN_MAX_CONCURRENCY)


class WebAuthRateLimitError(ValueError):
    def __init__(self, retry_after: int):
        self.retry_after = max(int(retry_after or 1), 1)
        super().__init__(f"登录尝试过于频繁，请在 {self.retry_after} 秒后重试")


def _login_failure_key(username: str) -> str:
    return hashlib.sha256(str(username or "").encode("utf-8")).hexdigest()


def _prune_login_failures(key: str, now: float) -> list[float]:
    threshold = now - WEB_LOGIN_FAILURE_WINDOW
    attempts = [item for item in _WEB_LOGIN_FAILURES.get(key, []) if item > threshold]
    if attempts:
        _WEB_LOGIN_FAILURES[key] = attempts
    else:
        _WEB_LOGIN_FAILURES.pop(key, None)
    return attempts


def _check_login_rate_limit(username: str) -> None:
    now = time.monotonic()
    key = _login_failure_key(username)
    with _WEB_LOGIN_LOCK:
        attempts = _prune_login_failures(key, now)
        if len(attempts) >= WEB_LOGIN_FAILURE_LIMIT:
            retry_after = int(max(attempts[0] + WEB_LOGIN_FAILURE_WINDOW - now, 1))
            raise WebAuthRateLimitError(retry_after)


def _record_login_failure(username: str) -> None:
    now = time.monotonic()
    key = _login_failure_key(username)
    with _WEB_LOGIN_LOCK:
        attempts = _prune_login_failures(key, now)
        attempts.append(now)
        _WEB_LOGIN_FAILURES[key] = attempts
        if len(_WEB_LOGIN_FAILURES) > 4096:
            oldest_key = min(_WEB_LOGIN_FAILURES, key=lambda item: _WEB_LOGIN_FAILURES[item][-1])
            _WEB_LOGIN_FAILURES.pop(oldest_key, None)


def _clear_login_failures(username: str) -> None:
    with _WEB_LOGIN_LOCK:
        _WEB_LOGIN_FAILURES.pop(_login_failure_key(username), None)


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _WEB_AUTH_CACHE_LOCK:
        item = _WEB_AUTH_CACHE.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= now:
            _WEB_AUTH_CACHE.pop(key, None)
            return None
        return dict(payload)


def _cache_set(key: str, payload: dict[str, Any], ttl: int) -> None:
    with _WEB_AUTH_CACHE_LOCK:
        if key not in _WEB_AUTH_CACHE and len(_WEB_AUTH_CACHE) >= 1024:
            oldest_key = min(_WEB_AUTH_CACHE, key=lambda item: _WEB_AUTH_CACHE[item][0])
            _WEB_AUTH_CACHE.pop(oldest_key, None)
        _WEB_AUTH_CACHE[key] = (time.monotonic() + max(int(ttl or 1), 1), dict(payload))


def _cache_delete(key: str) -> None:
    with _WEB_AUTH_CACHE_LOCK:
        _WEB_AUTH_CACHE.pop(key, None)


def _normalize_username(username: str) -> str:
    normalized = str(username or "").strip().lower()
    if not USERNAME_RE.fullmatch(normalized):
        raise ValueError("账号需为 3-64 位，可使用字母、数字、点、下划线、短横线或 @")
    return normalized


def _validate_password(password: str) -> str:
    value = str(password or "")
    if len(value) < 8:
        raise ValueError("密码至少需要 8 位")
    if len(value) > 128:
        raise ValueError("密码不能超过 128 位")
    return value


def _hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${digest}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected = str(password_hash or "").split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
    except (TypeError, ValueError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(digest, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _session_cache_key(token_hash: str) -> str:
    return f"xiuxian:web-session:{token_hash}"


def _serialize_account(row: XiuxianWebAccount) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "username": str(row.username or ""),
        "display_name": str(row.display_name or row.username or ""),
        "tg": int(row.tg) if row.tg else None,
        "bound": bool(row.tg),
        "telegram_username": str(row.telegram_username or ""),
        "telegram_display_name": str(row.telegram_display_name or ""),
        "telegram_label": (
            str(row.telegram_display_name or "").strip()
            or (f"@{str(row.telegram_username).strip().lstrip('@')}" if row.telegram_username else "")
            or (f"TG {int(row.tg)}" if row.tg else "未绑定")
        ),
        "enabled": bool(row.enabled),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
    }


def _new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _create_session_row(session, account_id: int, now: datetime) -> tuple[str, XiuxianWebSession]:
    token = _new_session_token()
    row = XiuxianWebSession(
        token_hash=_token_hash(token),
        account_id=int(account_id),
        created_at=now,
        expires_at=now + timedelta(days=WEB_SESSION_DAYS),
    )
    session.add(row)
    return token, row


def _session_response(token: str, account: XiuxianWebAccount) -> dict[str, Any]:
    return {
        "session_token": token,
        "session_days": WEB_SESSION_DAYS,
        "account": _serialize_account(account),
    }


def register_xiuxian_web_account(
    username: str,
    password: str,
    *,
    display_name: str | None = None,
) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    password_value = _validate_password(password)
    nickname = str(display_name or "").strip()[:80] or normalized_username
    now = utcnow()
    with Session() as session:
        account = XiuxianWebAccount(
            username=normalized_username,
            password_hash=_hash_password(password_value),
            display_name=nickname,
            enabled=True,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        session.add(account)
        try:
            session.flush()
            token, _ = _create_session_row(session, int(account.id), now)
            session.commit()
            session.refresh(account)
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("账号已存在，请换一个账号名") from exc
    return _session_response(token, account)


def login_xiuxian_web_account(username: str, password: str) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    password_value = _validate_password(password)
    _check_login_rate_limit(normalized_username)
    if not _WEB_LOGIN_SLOTS.acquire(blocking=False):
        raise WebAuthRateLimitError(1)
    now = utcnow()
    try:
        with Session() as session:
            account = session.query(XiuxianWebAccount).filter(XiuxianWebAccount.username == normalized_username).first()
            if account is None or not _verify_password(password_value, account.password_hash):
                _record_login_failure(normalized_username)
                raise ValueError("账号或密码错误")
            if not bool(account.enabled):
                raise ValueError("账号已被管理员停用")
            _clear_login_failures(normalized_username)
            token, _ = _create_session_row(session, int(account.id), now)
            account.last_login_at = now
            account.updated_at = now
            session.commit()
            session.refresh(account)
    finally:
        _WEB_LOGIN_SLOTS.release()
    return _session_response(token, account)


def authenticate_xiuxian_web_session(token: str) -> dict[str, Any]:
    normalized = str(token or "").strip()
    if not normalized:
        raise ValueError("缺少登录会话")
    hashed = _token_hash(normalized)
    cache_key = _session_cache_key(hashed)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    now = utcnow()
    with Session() as session:
        session_row = session.query(XiuxianWebSession).filter(XiuxianWebSession.token_hash == hashed).first()
        if session_row is None:
            raise ValueError("登录已失效，请重新登录")
        if session_row.expires_at <= now:
            session.delete(session_row)
            session.commit()
            raise ValueError("登录已过期，请重新登录")
        account = session.query(XiuxianWebAccount).filter(XiuxianWebAccount.id == session_row.account_id).first()
        if account is None:
            session.delete(session_row)
            session.commit()
            raise ValueError("账号不存在，请重新登录")
        if not bool(account.enabled):
            session.delete(session_row)
            session.commit()
            raise ValueError("账号已被管理员停用")
        payload = _serialize_account(account)
        seconds_left = int((session_row.expires_at - now).total_seconds())

    _cache_set(cache_key, payload, min(WEB_SESSION_CACHE_TTL, max(seconds_left, 1)))
    return payload


def logout_xiuxian_web_session(token: str) -> bool:
    normalized = str(token or "").strip()
    if not normalized:
        return False
    hashed = _token_hash(normalized)
    with Session() as session:
        row = session.query(XiuxianWebSession).filter(XiuxianWebSession.token_hash == hashed).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
    _cache_delete(_session_cache_key(hashed))
    return True


def bind_xiuxian_web_account_to_telegram(token: str, telegram_user: dict[str, Any]) -> dict[str, Any]:
    normalized = str(token or "").strip()
    if not normalized:
        raise ValueError("请先登录网页账号")
    tg = int((telegram_user or {}).get("id") or 0)
    if tg <= 0:
        raise ValueError("Telegram 身份无效")
    username = str((telegram_user or {}).get("username") or "").strip().lstrip("@")
    display_name = " ".join(
        part
        for part in [
            str((telegram_user or {}).get("first_name") or "").strip(),
            str((telegram_user or {}).get("last_name") or "").strip(),
        ]
        if part
    ).strip()
    hashed = _token_hash(normalized)
    now = utcnow()
    with Session() as session:
        session_row = session.query(XiuxianWebSession).filter(XiuxianWebSession.token_hash == hashed).first()
        if session_row is None or session_row.expires_at <= now:
            raise ValueError("登录已失效，请重新登录")
        account = (
            session.query(XiuxianWebAccount)
            .filter(XiuxianWebAccount.id == session_row.account_id)
            .with_for_update()
            .first()
        )
        if account is None:
            raise ValueError("账号不存在，请重新登录")
        if not bool(account.enabled):
            raise ValueError("账号已被管理员停用")
        if account.tg and int(account.tg) != tg:
            raise ValueError("该网页账号已绑定其他 Telegram")
        other = (
            session.query(XiuxianWebAccount)
            .filter(XiuxianWebAccount.tg == tg, XiuxianWebAccount.id != account.id)
            .first()
        )
        if other is not None:
            raise ValueError("该 Telegram 已绑定其他网页账号")
        account.tg = tg
        account.telegram_username = username[:64] or None
        account.telegram_display_name = display_name[:128] or None
        account.updated_at = now
        account_token_hashes = [
            str(value)
            for (value,) in (
                session.query(XiuxianWebSession.token_hash)
                .filter(XiuxianWebSession.account_id == int(account.id))
                .all()
            )
        ]
        session.commit()
        session.refresh(account)
        payload = _serialize_account(account)

    _clear_session_cache(account_token_hashes)
    return payload


def _revoke_account_sessions(session, account_id: int) -> list[str]:
    token_hashes = [
        str(value)
        for (value,) in (
            session.query(XiuxianWebSession.token_hash)
            .filter(XiuxianWebSession.account_id == int(account_id))
            .all()
        )
    ]
    session.query(XiuxianWebSession).filter(XiuxianWebSession.account_id == int(account_id)).delete(
        synchronize_session=False
    )
    return token_hashes


def _clear_session_cache(token_hashes: list[str]) -> None:
    for hashed in token_hashes:
        _cache_delete(_session_cache_key(hashed))


def list_xiuxian_web_accounts(
    query: str = "",
    *,
    bound: bool | None = None,
    enabled: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    resolved_page = max(int(page or 1), 1)
    resolved_page_size = min(max(int(page_size or 20), 1), 100)
    with Session() as session:
        base = session.query(XiuxianWebAccount)
        if normalized_query:
            filters = [
                XiuxianWebAccount.username.ilike(f"%{normalized_query}%"),
                XiuxianWebAccount.display_name.ilike(f"%{normalized_query}%"),
                XiuxianWebAccount.telegram_username.ilike(f"%{normalized_query.lstrip('@')}%"),
                XiuxianWebAccount.telegram_display_name.ilike(f"%{normalized_query}%"),
            ]
            try:
                numeric_query = int(normalized_query)
            except (TypeError, ValueError):
                numeric_query = 0
            if numeric_query > 0:
                filters.extend((XiuxianWebAccount.id == numeric_query, XiuxianWebAccount.tg == numeric_query))
            base = base.filter(or_(*filters))
        if bound is True:
            base = base.filter(XiuxianWebAccount.tg.isnot(None))
        elif bound is False:
            base = base.filter(XiuxianWebAccount.tg.is_(None))
        if enabled is not None:
            base = base.filter(XiuxianWebAccount.enabled.is_(bool(enabled)))
        total = int(base.count() or 0)
        rows = (
            base.order_by(XiuxianWebAccount.updated_at.desc(), XiuxianWebAccount.id.desc())
            .offset((resolved_page - 1) * resolved_page_size)
            .limit(resolved_page_size)
            .all()
        )
        total_accounts = int(session.query(func.count(XiuxianWebAccount.id)).scalar() or 0)
        bound_accounts = int(
            session.query(func.count(XiuxianWebAccount.id)).filter(XiuxianWebAccount.tg.isnot(None)).scalar() or 0
        )
        disabled_accounts = int(
            session.query(func.count(XiuxianWebAccount.id)).filter(XiuxianWebAccount.enabled.is_(False)).scalar() or 0
        )
    return {
        "items": [_serialize_account(row) for row in rows],
        "total": total,
        "page": resolved_page,
        "page_size": resolved_page_size,
        "summary": {
            "total": total_accounts,
            "bound": bound_accounts,
            "unbound": max(total_accounts - bound_accounts, 0),
            "disabled": disabled_accounts,
        },
    }


def set_xiuxian_web_account_enabled(account_id: int, enabled: bool) -> dict[str, Any]:
    token_hashes: list[str] = []
    with Session() as session:
        account = (
            session.query(XiuxianWebAccount)
            .filter(XiuxianWebAccount.id == int(account_id))
            .with_for_update()
            .first()
        )
        if account is None:
            raise ValueError("游戏账号不存在")
        account.enabled = bool(enabled)
        account.updated_at = utcnow()
        if not account.enabled:
            token_hashes = _revoke_account_sessions(session, int(account.id))
        session.commit()
        session.refresh(account)
        payload = _serialize_account(account)
    _clear_session_cache(token_hashes)
    return payload


def unbind_xiuxian_web_account(account_id: int) -> dict[str, Any]:
    with Session() as session:
        account = (
            session.query(XiuxianWebAccount)
            .filter(XiuxianWebAccount.id == int(account_id))
            .with_for_update()
            .first()
        )
        if account is None:
            raise ValueError("游戏账号不存在")
        account.tg = None
        account.telegram_username = None
        account.telegram_display_name = None
        account.updated_at = utcnow()
        token_hashes = _revoke_account_sessions(session, int(account.id))
        session.commit()
        session.refresh(account)
        payload = _serialize_account(account)
    _clear_session_cache(token_hashes)
    return payload


def revoke_xiuxian_web_account_sessions(account_id: int) -> int:
    with Session() as session:
        exists = session.query(XiuxianWebAccount.id).filter(XiuxianWebAccount.id == int(account_id)).first()
        if exists is None:
            raise ValueError("游戏账号不存在")
        token_hashes = _revoke_account_sessions(session, int(account_id))
        session.commit()
    _clear_session_cache(token_hashes)
    return len(token_hashes)
