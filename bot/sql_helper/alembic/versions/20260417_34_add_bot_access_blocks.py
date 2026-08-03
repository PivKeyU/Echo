"""add bot access blocks

Revision ID: 20260417_34a
Revises: 20260417_33
Create Date: 2026-04-17 19:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_34a"
down_revision = "20260417_33"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("bot_access_blocks"):
        return

    op.create_table(
        "bot_access_blocks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tg", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tg", name="uq_bot_access_blocks_tg"),
        sa.UniqueConstraint("username", name="uq_bot_access_blocks_username"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    if _has_table("bot_access_blocks"):
        op.drop_table("bot_access_blocks")
