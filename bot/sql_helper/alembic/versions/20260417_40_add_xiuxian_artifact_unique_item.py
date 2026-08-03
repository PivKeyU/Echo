"""add xiuxian artifact unique item flag

Revision ID: 20260417_40a
Revises: 20260417_39a
Create Date: 2026-04-20 16:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_40a"
down_revision = "20260417_39a"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _has_table(inspector, "xiuxian_artifacts") and not _has_column(inspector, "xiuxian_artifacts", "unique_item"):
        op.add_column(
            "xiuxian_artifacts",
            sa.Column("unique_item", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _has_table(inspector, "xiuxian_artifacts") and _has_column(inspector, "xiuxian_artifacts", "unique_item"):
        op.drop_column("xiuxian_artifacts", "unique_item")
