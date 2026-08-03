#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
凭据密钥轮换重加密脚本。

背景：Emby 凭据（emby.pwd / emby.pwd2 / emby2.pwd / emby2.pwd2）用
PIVKEYU_CREDENTIAL_KEY（或从 bot secret 派生）加密存储（enc:v1: 前缀）。
更换该密钥后，存量密文将无法用新密钥解密，导致登录凭据读取失败。

本脚本在切换密钥前执行：用「旧密钥」解密存量密文，再用「新密钥」重新加密，
使密钥轮换不丢失任何凭据。

用法（在容器内或本机执行）：
    # 1. 设旧密钥（当前正在用的密钥）
    export PIVKEYU_CREDENTIAL_KEY_OLD="<当前密钥>"
    # 2. 设新密钥（切换后要用的密钥）
    export PIVKEYU_CREDENTIAL_KEY="<新密钥>"
    # 3. 执行重加密（默认 dry-run，只统计）
    python3 scripts/reencrypt_credentials.py
    # 4. 确认统计无误后真正执行
    python3 scripts/reencrypt_credentials.py --apply

注意：
- 未设置 PIVKEYU_CREDENTIAL_KEY_OLD 时，回退使用 PIVKEYU_CREDENTIAL_KEY
  对应的解密密钥（即"新钥即旧钥"，用于检查/修补）。
- 明文值（无 enc:v1: 前缀）视为无需解密，直接用新钥加密。
- 每行数据独立处理，单行解密失败会跳过并计数，不会中断整体。
- 建议在执行前先备份数据库。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"


def _fernet_from_env(name: str) -> Fernet:
    configured = (os.getenv(name) or "").strip()
    if configured:
        try:
            return Fernet(configured.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError):
            return Fernet(base64.urlsafe_b64encode(hashlib.sha256(configured.encode("utf-8")).digest()))
    return None


def _decrypt_with(fernet: Fernet | None, value: str) -> str | None:
    if not value.startswith(_PREFIX):
        return value  # 明文透传
    if fernet is None:
        return None
    token = value[len(_PREFIX):]
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError, UnicodeEncodeError):
        return None


def _encrypt_with(fernet: Fernet, plaintext: str) -> str:
    return _PREFIX + fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def _collect_rows(engine, table: str, key_column: str):
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT {key_column}, pwd, pwd2 FROM {table}")).mappings().all()
    return rows


def _reencrypt_table(engine, table: str, key_column: str, old: Fernet | None, new: Fernet, apply: bool):
    from sqlalchemy import text

    rows = _collect_rows(engine, table, key_column)
    total = plain = encrypted = failed = 0
    with engine.begin() as conn:
        for row in rows:
            total += 1
            updates = {}
            for column in ("pwd", "pwd2"):
                value = row.get(column)
                if value is None:
                    continue
                plaintext = _decrypt_with(old, str(value))
                if plaintext is None:
                    failed += 1
                    continue
                if not str(value).startswith(_PREFIX):
                    plain += 1
                else:
                    encrypted += 1
                updates[column] = _encrypt_with(new, plaintext)
            if updates and apply:
                conn.execute(
                    text(f"UPDATE {table} SET pwd = :pwd, pwd2 = :pwd2 WHERE {key_column} = :key"),
                    {"pwd": updates.get("pwd"), "pwd2": updates.get("pwd2"), "key": row[key_column]},
                )
    return total, plain, encrypted, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="凭据密钥轮换重加密")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run 只统计）")
    args = parser.parse_args()

    new = _fernet_from_env("PIVKEYU_CREDENTIAL_KEY")
    if new is None:
        print("错误：未设置 PIVKEYU_CREDENTIAL_KEY（新密钥）", file=sys.stderr)
        return 2
    old = _fernet_from_env("PIVKEYU_CREDENTIAL_KEY_OLD") or new

    # 惰性加载项目 DB 配置（避免 import bot 时触发整个运行时初始化）
    try:
        from bot.sql_helper import engine, db_backend
    except Exception as exc:
        print(f"错误：无法初始化数据库连接: {exc}", file=sys.stderr)
        return 2

    tables = [("emby", "tg"), ("emby2", "embyid")]
    print(f"数据库: {db_backend}")
    print(f"模式: {'APPLY（写库）' if args.apply else 'dry-run（只统计）'}")
    for table, key_column in tables:
        total, plain, encrypted, failed = _reencrypt_table(engine, table, key_column, old, new, args.apply)
        print(
            f"表 {table}: 共 {total} 行, 明文 {plain}, 已加密 {encrypted}, "
            f"解密失败 {failed}（失败行保持原值）"
        )
    print("完成。若解密失败为 0，可安全切换 PIVKEYU_CREDENTIAL_KEY 为新密钥。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
