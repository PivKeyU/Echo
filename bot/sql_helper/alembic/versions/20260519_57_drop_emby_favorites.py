"""drop emby_favorites table

Revision ID: 20260519_57a
Revises: 20260512_56a
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260519_57a"
down_revision = "20260512_56a"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("emby_favorites"):
        op.drop_table("emby_favorites")


def downgrade() -> None:
    if _has_table("emby_favorites"):
        return
    op.create_table(
        "emby_favorites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("embyid", sa.String(length=64), nullable=False),
        sa.Column("embyname", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("item_name", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("embyid", "item_id", name="uix_emby_item"),
    )
