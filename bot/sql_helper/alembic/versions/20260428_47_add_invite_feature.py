"""add emby invite feature tables and shop item type

Revision ID: 20260428_47a
Revises: 20260428_46a
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428_47a"
down_revision = "20260428_46a"
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
    if not _has_table("invite_settings"):
        op.create_table(
            "invite_settings",
            sa.Column("setting_key", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("setting_value", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _has_table("invite_credits"):
        op.create_table(
            "invite_credits",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_tg", sa.BigInteger(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="admin"),
            sa.Column("source_ref", sa.String(length=128), nullable=True),
            sa.Column("granted_by_tg", sa.BigInteger(), nullable=True),
            sa.Column("note", sa.String(length=255), nullable=True),
            sa.Column("consumed_record_id", sa.Integer(), nullable=True),
            sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_by_tg", sa.BigInteger(), nullable=True),
            sa.Column("revoke_reason", sa.String(length=255), nullable=True),
        )
        op.create_index("ix_invite_credits_owner_status", "invite_credits", ["owner_tg", "consumed_at", "revoked_at"])
        op.create_index("ix_invite_credits_source", "invite_credits", ["source", "source_ref"])

    if not _has_table("invite_records"):
        op.create_table(
            "invite_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("credit_id", sa.Integer(), sa.ForeignKey("invite_credits.id", ondelete="SET NULL"), nullable=True),
            sa.Column("inviter_tg", sa.BigInteger(), nullable=False),
            sa.Column("invitee_tg", sa.BigInteger(), nullable=False),
            sa.Column("target_chat_id", sa.BigInteger(), nullable=False),
            sa.Column("invite_link", sa.String(length=512), nullable=False),
            sa.Column("link_name", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("created_by_tg", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_request_tg", sa.BigInteger(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
        )
        op.create_index("ix_invite_records_inviter", "invite_records", ["inviter_tg", "created_at"])
        op.create_index("ix_invite_records_invitee", "invite_records", ["invitee_tg", "created_at"])
        op.create_index("ix_invite_records_status", "invite_records", ["status", "expires_at"])
        op.create_index("ix_invite_records_link", "invite_records", ["target_chat_id", "invite_link"])

    if _has_table("shop_items"):
        if not _has_column("shop_items", "item_type"):
            op.add_column("shop_items", sa.Column("item_type", sa.String(length=32), nullable=False, server_default="digital"))
        if not _has_column("shop_items", "invite_credit_quantity"):
            op.add_column("shop_items", sa.Column("invite_credit_quantity", sa.Integer(), nullable=False, server_default="0"))

    if _has_table("shop_orders"):
        if not _has_column("shop_orders", "item_type"):
            op.add_column("shop_orders", sa.Column("item_type", sa.String(length=32), nullable=False, server_default="digital"))
        if not _has_column("shop_orders", "invite_credit_quantity"):
            op.add_column("shop_orders", sa.Column("invite_credit_quantity", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    if _has_table("shop_orders"):
        if _has_column("shop_orders", "invite_credit_quantity"):
            op.drop_column("shop_orders", "invite_credit_quantity")
        if _has_column("shop_orders", "item_type"):
            op.drop_column("shop_orders", "item_type")

    if _has_table("shop_items"):
        if _has_column("shop_items", "invite_credit_quantity"):
            op.drop_column("shop_items", "invite_credit_quantity")
        if _has_column("shop_items", "item_type"):
            op.drop_column("shop_items", "item_type")

    if _has_table("invite_records"):
        op.drop_index("ix_invite_records_link", table_name="invite_records")
        op.drop_index("ix_invite_records_status", table_name="invite_records")
        op.drop_index("ix_invite_records_invitee", table_name="invite_records")
        op.drop_index("ix_invite_records_inviter", table_name="invite_records")
        op.drop_table("invite_records")

    if _has_table("invite_credits"):
        op.drop_index("ix_invite_credits_source", table_name="invite_credits")
        op.drop_index("ix_invite_credits_owner_status", table_name="invite_credits")
        op.drop_table("invite_credits")

    if _has_table("invite_settings"):
        op.drop_table("invite_settings")
