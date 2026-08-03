"""expand Emby credential columns for encrypted values

Revision ID: 20260714_60a
Revises: 20260713_59a
Create Date: 2026-07-14
"""
import logging

from alembic import op
import sqlalchemy as sa

from bot.sql_helper.credential_crypto import decrypt_credential, encrypt_credential

LOGGER = logging.getLogger(__name__)

revision = "20260714_60a"
down_revision = "20260713_59a"
branch_labels = None
depends_on = None

_PREFIX = "enc:v1:"


def _columns(table: str) -> dict[str, dict]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return {}
    return {str(item["name"]): item for item in inspector.get_columns(table)}


def _credential_table(table_name: str, key_column: str):
    return sa.table(
        table_name,
        sa.column(key_column),
        sa.column("pwd", sa.String()),
        sa.column("pwd2", sa.String()),
    )


def _encrypt_legacy_values(table_name: str, key_column: str) -> None:
    bind = op.get_bind()
    table = _credential_table(table_name, key_column)
    rows = bind.execute(sa.select(table.c[key_column], table.c.pwd, table.c.pwd2)).mappings()
    for row in rows:
        values = {}
        for column in ("pwd", "pwd2"):
            value = row.get(column)
            if value is not None and not str(value).startswith(_PREFIX):
                values[column] = encrypt_credential(value)
        if values:
            bind.execute(
                table.update()
                .where(table.c[key_column] == row[key_column])
                .values(**values)
            )


def _decrypt_credential_values(table_name: str, key_column: str) -> None:
    """Reverse the upgrade: restore plaintext so the pre-crypto code keeps working."""
    bind = op.get_bind()
    table = _credential_table(table_name, key_column)
    rows = bind.execute(sa.select(table.c[key_column], table.c.pwd, table.c.pwd2)).mappings()
    for row in rows:
        values = {}
        for column in ("pwd", "pwd2"):
            value = row.get(column)
            if value is not None and str(value).startswith(_PREFIX):
                try:
                    values[column] = decrypt_credential(value)
                except ValueError as exc:
                    LOGGER.warning(
                        f"凭据降级解密失败，保留原值: {table_name}.{column} "
                        f"{key_column}={row[key_column]!r}: {exc}"
                    )
        if values:
            bind.execute(
                table.update()
                .where(table.c[key_column] == row[key_column])
                .values(**values)
            )


def _resize_credential_columns(table: str, length: int) -> None:
    columns = _columns(table)
    changed = [name for name in ("pwd", "pwd2") if name in columns]
    if not changed:
        return
    with op.batch_alter_table(table) as batch_op:
        for column in changed:
            existing = columns[column]
            batch_op.alter_column(
                column,
                existing_type=existing["type"],
                type_=sa.String(length=length),
                existing_nullable=existing.get("nullable", True),
            )


def upgrade() -> None:
    for table, key_column in (("emby", "tg"), ("emby2", "embyid")):
        # 先扩列到 1024，密文比明文长。
        _resize_credential_columns(table, 1024)
        columns = _columns(table)
        if "pwd" in columns or "pwd2" in columns:
            _encrypt_legacy_values(table, key_column)


def downgrade() -> None:
    for table, key_column in (("emby", "tg"), ("emby2", "embyid")):
        columns = _columns(table)
        if "pwd" in columns or "pwd2" in columns:
            # 先还原明文，再缩回 255：避免密文长度超过列上限。
            _decrypt_credential_values(table, key_column)
        _resize_credential_columns(table, 255)
