"""add invite account-open request review fields

Revision ID: 20260503_49a
Revises: 20260502_48a
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260503_49a"
down_revision = "20260502_48a"
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
    if not _has_table("invite_records"):
        return
    if not _has_column("invite_records", "reviewed_by_tg"):
        op.add_column("invite_records", sa.Column("reviewed_by_tg", sa.BigInteger(), nullable=True))
    if not _has_column("invite_records", "reviewed_at"):
        op.add_column("invite_records", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    if not _has_column("invite_records", "review_note"):
        op.add_column("invite_records", sa.Column("review_note", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_table("invite_records"):
        return
    if _has_column("invite_records", "review_note"):
        op.drop_column("invite_records", "review_note")
    if _has_column("invite_records", "reviewed_at"):
        op.drop_column("invite_records", "reviewed_at")
    if _has_column("invite_records", "reviewed_by_tg"):
        op.drop_column("invite_records", "reviewed_by_tg")
