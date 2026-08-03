"""extend shared game accounts with Telegram identity and status

Revision ID: 20260713_59a
Revises: 20260708_58a
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260713_59a"
down_revision = "20260708_58a"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {str(item["name"]) for item in inspector.get_columns(table)}


def upgrade() -> None:
    table = "xiuxian_web_accounts"
    columns = _column_names(table)
    if not columns:
        return
    if "telegram_username" not in columns:
        op.add_column(table, sa.Column("telegram_username", sa.String(length=64), nullable=True))
    if "telegram_display_name" not in columns:
        op.add_column(table, sa.Column("telegram_display_name", sa.String(length=128), nullable=True))
    if "enabled" not in columns:
        op.add_column(
            table,
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    table = "xiuxian_web_accounts"
    columns = _column_names(table)
    if "enabled" in columns:
        op.drop_column(table, "enabled")
    if "telegram_display_name" in columns:
        op.drop_column(table, "telegram_display_name")
    if "telegram_username" in columns:
        op.drop_column(table, "telegram_username")
