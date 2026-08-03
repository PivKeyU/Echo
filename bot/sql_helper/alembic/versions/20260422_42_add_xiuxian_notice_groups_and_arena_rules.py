"""add xiuxian notice group and arena rule fields

Revision ID: 20260422_42a
Revises: 20260421_41a
Create Date: 2026-04-22 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260422_42a"
down_revision = "20260421_41a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    if _has_table("xiuxian_shop_items"):
        if not _has_column("xiuxian_shop_items", "notice_group_chat_id"):
            op.add_column("xiuxian_shop_items", sa.Column("notice_group_chat_id", sa.BigInteger(), nullable=True))
        if not _has_column("xiuxian_shop_items", "notice_group_message_id"):
            op.add_column("xiuxian_shop_items", sa.Column("notice_group_message_id", sa.Integer(), nullable=True))

    if _has_table("xiuxian_arenas"):
        if not _has_column("xiuxian_arenas", "realm_stage"):
            op.add_column(
                "xiuxian_arenas",
                sa.Column("realm_stage", sa.String(length=32), nullable=False, server_default="炼气"),
            )
        if not _has_column("xiuxian_arenas", "reward_cultivation"):
            op.add_column(
                "xiuxian_arenas",
                sa.Column("reward_cultivation", sa.Integer(), nullable=False, server_default="0"),
            )


def downgrade() -> None:
    if _has_table("xiuxian_arenas"):
        if _has_column("xiuxian_arenas", "reward_cultivation"):
            op.drop_column("xiuxian_arenas", "reward_cultivation")
        if _has_column("xiuxian_arenas", "realm_stage"):
            op.drop_column("xiuxian_arenas", "realm_stage")

    if _has_table("xiuxian_shop_items"):
        if _has_column("xiuxian_shop_items", "notice_group_message_id"):
            op.drop_column("xiuxian_shop_items", "notice_group_message_id")
        if _has_column("xiuxian_shop_items", "notice_group_chat_id"):
            op.drop_column("xiuxian_shop_items", "notice_group_chat_id")
