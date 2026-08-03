"""Encryption helpers for Emby credentials.

Credentials remain decryptable by the application (they are not hashed), while
legacy plaintext values continue to be accepted during reads.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


LOGGER = logging.getLogger(__name__)
_PREFIX = "enc:v1:"
_KEY_ENV = "PIVKEYU_CREDENTIAL_KEY"
_FALLBACK_WARNING_EMITTED = False
_FERNET: Fernet | None = None


def _derive_key() -> bytes:
    """Return a stable Fernet key without ever using a hard-coded key."""
    global _FALLBACK_WARNING_EMITTED
    configured = (os.getenv(_KEY_ENV) or "").strip()
    if configured:
        try:
            Fernet(configured.encode("ascii"))
            return configured.encode("ascii")
        except (ValueError, TypeError, UnicodeEncodeError):
            # Accept a human-readable secret as well as a generated Fernet key,
            # but make the conversion deterministic.
            return base64.urlsafe_b64encode(hashlib.sha256(configured.encode("utf-8")).digest())

    # Import lazily: bot imports the SQL helper package during initialization.
    try:
        from bot import bot_token, owner_hash
    except Exception:
        bot_token = None
        owner_hash = None
    secret = str(bot_token or owner_hash or "").strip()
    if not secret:
        raise RuntimeError(
            f"未配置 {_KEY_ENV}，且无法从已有 bot secret 派生凭据加密密钥"
        )
    if not _FALLBACK_WARNING_EMITTED:
        LOGGER.warning(
            f"未配置 {_KEY_ENV}，将从已有 bot secret 派生凭据加密密钥；"
            "建议显式配置该环境变量以便密钥轮换"
        )
        _FALLBACK_WARNING_EMITTED = True
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        _FERNET = Fernet(_derive_key())
    return _FERNET


def encrypt_credential(value: Any) -> Any:
    """Encrypt a credential, preserving NULL and already encrypted values."""
    if value is None:
        return None
    text = str(value)
    if text.startswith(_PREFIX):
        return text
    return _PREFIX + _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_credential(value: Any) -> Any:
    """Decrypt a credential, returning legacy plaintext unchanged."""
    if value is None:
        return None
    text = str(value)
    if not text.startswith(_PREFIX):
        return text
    token = text[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("凭据密文无法解码") from exc


class CredentialType(TypeDecorator):
    """SQLAlchemy string type that encrypts on bind and decrypts on result."""

    impl = String(1024)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(String(1024))

    def process_bind_param(self, value, dialect):
        return encrypt_credential(value)

    def process_result_value(self, value, dialect):
        return decrypt_credential(value)
