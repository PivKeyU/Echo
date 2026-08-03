"""add xiuxian furnace harvest tracking

Revision ID: 20260417_38a
Revises: 20260417_37a
Create Date: 2026-04-17 21:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_38a"
down_revision = "20260417_37a"
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
    if not _has_table("xiuxian_profiles") or _has_column("xiuxian_profiles", "furnace_harvested_at"):
        return
    with op.batch_alter_table("xiuxian_profiles") as batch_op:
        batch_op.add_column(sa.Column("furnace_harvested_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if not _has_table("xiuxian_profiles") or not _has_column("xiuxian_profiles", "furnace_harvested_at"):
        return
    with op.batch_alter_table("xiuxian_profiles") as batch_op:
        batch_op.drop_column("furnace_harvested_at")
