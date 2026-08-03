"""expand emby balance column

Revision ID: 20260504_51a
Revises: 20260504_50a
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260504_51a"
down_revision = "20260504_50a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {item["name"] for item in _inspector().get_columns(table)}


def upgrade() -> None:
    if not _has_column("emby", "iv"):
        return
    with op.batch_alter_table("emby") as batch_op:
        batch_op.alter_column(
            "iv",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )


def downgrade() -> None:
    if not _has_column("emby", "iv"):
        return
    with op.batch_alter_table("emby") as batch_op:
        batch_op.alter_column(
            "iv",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
