"""expand xiuxian title color length

Revision ID: 20260417_37a
Revises: 20260417_36a
Create Date: 2026-04-17 20:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_37a"
down_revision = "20260417_36a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_length(table_name: str, column_name: str) -> int | None:
    if not _has_table(table_name):
        return None
    for column in _inspector().get_columns(table_name):
        if column.get("name") == column_name:
            return getattr(column.get("type"), "length", None)
    return None


def upgrade() -> None:
    if not _has_table("xiuxian_titles"):
        return
    current_length = _column_length("xiuxian_titles", "color")
    if current_length is None or current_length >= 255:
        return
    with op.batch_alter_table("xiuxian_titles") as batch_op:
        batch_op.alter_column(
            "color",
            existing_type=sa.String(length=current_length),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade() -> None:
    if not _has_table("xiuxian_titles"):
        return
    current_length = _column_length("xiuxian_titles", "color")
    if current_length == 32:
        return
    with op.batch_alter_table("xiuxian_titles") as batch_op:
        batch_op.alter_column(
            "color",
            existing_type=sa.String(length=current_length or 255),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
