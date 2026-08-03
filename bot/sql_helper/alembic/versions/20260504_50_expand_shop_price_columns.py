"""expand shop price columns

Revision ID: 20260504_50a
Revises: 20260503_49a
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260504_50a"
down_revision = "20260503_49a"
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


def _alter_integer_to_bigint(table: str, column: str) -> None:
    if not _has_column(table, column):
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            column,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
            existing_server_default="0",
        )


def _alter_bigint_to_integer(table: str, column: str) -> None:
    if not _has_column(table, column):
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
            existing_server_default="0",
        )


def upgrade() -> None:
    _alter_integer_to_bigint("shop_items", "price_iv")
    _alter_integer_to_bigint("shop_orders", "unit_price_iv")
    _alter_integer_to_bigint("shop_orders", "total_price_iv")


def downgrade() -> None:
    _alter_bigint_to_integer("shop_orders", "total_price_iv")
    _alter_bigint_to_integer("shop_orders", "unit_price_iv")
    _alter_bigint_to_integer("shop_items", "price_iv")
