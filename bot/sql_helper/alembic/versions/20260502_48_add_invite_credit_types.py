"""split invite credits into account-open and group-join types

Revision ID: 20260502_48a
Revises: 20260428_47a
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260502_48a"
down_revision = "20260428_47a"
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


def _has_index(table: str, index: str) -> bool:
    if not _has_table(table):
        return False
    return index in {item["name"] for item in _inspector().get_indexes(table)}


def upgrade() -> None:
    if _has_table("invite_credits"):
        if not _has_column("invite_credits", "credit_type"):
            op.add_column(
                "invite_credits",
                sa.Column("credit_type", sa.String(length=32), nullable=False, server_default="group_join"),
            )
        if not _has_column("invite_credits", "invite_days"):
            op.add_column(
                "invite_credits",
                sa.Column("invite_days", sa.Integer(), nullable=False, server_default="0"),
            )
        if not _has_index("invite_credits", "ix_invite_credits_type_owner_status"):
            op.create_index(
                "ix_invite_credits_type_owner_status",
                "invite_credits",
                ["credit_type", "owner_tg", "consumed_at", "revoked_at"],
            )

    if _has_table("invite_records"):
        if not _has_column("invite_records", "record_type"):
            op.add_column(
                "invite_records",
                sa.Column("record_type", sa.String(length=32), nullable=False, server_default="group_join"),
            )
        if not _has_column("invite_records", "invite_days"):
            op.add_column(
                "invite_records",
                sa.Column("invite_days", sa.Integer(), nullable=False, server_default="0"),
            )
        if not _has_index("invite_records", "ix_invite_records_type_inviter"):
            op.create_index(
                "ix_invite_records_type_inviter",
                "invite_records",
                ["record_type", "inviter_tg", "created_at"],
            )


def downgrade() -> None:
    if _has_table("invite_records"):
        if _has_index("invite_records", "ix_invite_records_type_inviter"):
            op.drop_index("ix_invite_records_type_inviter", table_name="invite_records")
        if _has_column("invite_records", "invite_days"):
            op.drop_column("invite_records", "invite_days")
        if _has_column("invite_records", "record_type"):
            op.drop_column("invite_records", "record_type")

    if _has_table("invite_credits"):
        if _has_index("invite_credits", "ix_invite_credits_type_owner_status"):
            op.drop_index("ix_invite_credits_type_owner_status", table_name="invite_credits")
        if _has_column("invite_credits", "invite_days"):
            op.drop_column("invite_credits", "invite_days")
        if _has_column("invite_credits", "credit_type"):
            op.drop_column("invite_credits", "credit_type")
