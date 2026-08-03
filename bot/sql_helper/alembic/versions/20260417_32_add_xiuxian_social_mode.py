"""add xiuxian social mode

Revision ID: 20260417_32
Revises: 20260417_31
Create Date: 2026-04-17 14:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_32"
down_revision = "20260417_31"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column.get("name") == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if not _has_table("xiuxian_profiles"):
        return
    with op.batch_alter_table("xiuxian_profiles") as batch_op:
        if not _has_column("xiuxian_profiles", "social_mode"):
            batch_op.add_column(sa.Column("social_mode", sa.String(length=16), nullable=False, server_default="worldly"))
        if not _has_column("xiuxian_profiles", "social_mode_updated_at"):
            batch_op.add_column(sa.Column("social_mode_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if not _has_table("xiuxian_profiles"):
        return
    with op.batch_alter_table("xiuxian_profiles") as batch_op:
        if _has_column("xiuxian_profiles", "social_mode_updated_at"):
            batch_op.drop_column("social_mode_updated_at")
        if _has_column("xiuxian_profiles", "social_mode"):
            batch_op.drop_column("social_mode")
