"""add xiuxian auction tables

Revision ID: 20260417_31
Revises: 20260416_30
Create Date: 2026-04-17 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_31"
down_revision = "20260416_30"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("xiuxian_auction_items"):
        op.create_table(
            "xiuxian_auction_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_tg", sa.BigInteger(), nullable=False),
            sa.Column("owner_display_name", sa.String(length=128), nullable=True),
            sa.Column("item_kind", sa.String(length=16), nullable=False),
            sa.Column("item_ref_id", sa.Integer(), nullable=False),
            sa.Column("item_name", sa.String(length=64), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("opening_price_stone", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_price_stone", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bid_increment_stone", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("buyout_price_stone", sa.Integer(), nullable=True),
            sa.Column("fee_percent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("highest_bidder_tg", sa.BigInteger(), nullable=True),
            sa.Column("highest_bidder_display_name", sa.String(length=128), nullable=True),
            sa.Column("winner_tg", sa.BigInteger(), nullable=True),
            sa.Column("winner_display_name", sa.String(length=128), nullable=True),
            sa.Column("bid_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("group_chat_id", sa.BigInteger(), nullable=True),
            sa.Column("group_message_id", sa.Integer(), nullable=True),
            sa.Column("final_price_stone", sa.Integer(), nullable=True),
            sa.Column("seller_income_stone", sa.Integer(), nullable=True),
            sa.Column("fee_amount_stone", sa.Integer(), nullable=True),
            sa.Column("end_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table("xiuxian_auction_bids"):
        op.create_table(
            "xiuxian_auction_bids",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("auction_id", sa.Integer(), sa.ForeignKey("xiuxian_auction_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("bidder_tg", sa.BigInteger(), nullable=False),
            sa.Column("bidder_display_name", sa.String(length=128), nullable=True),
            sa.Column("bid_amount_stone", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("action_type", sa.String(length=16), nullable=False, server_default="bid"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _has_table("xiuxian_auction_bids"):
        op.drop_table("xiuxian_auction_bids")

    if _has_table("xiuxian_auction_items"):
        op.drop_table("xiuxian_auction_items")
