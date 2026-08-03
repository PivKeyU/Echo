"""add xiuxian arena tables

Revision ID: 20260417_39a
Revises: 20260417_38a
Create Date: 2026-04-17 23:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_39a"
down_revision = "20260417_38a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("xiuxian_arenas"):
        return
    op.create_table(
        "xiuxian_arenas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_tg", sa.BigInteger(), nullable=False),
        sa.Column("owner_display_name", sa.String(length=128), nullable=True),
        sa.Column("champion_tg", sa.BigInteger(), nullable=False),
        sa.Column("champion_display_name", sa.String(length=128), nullable=True),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("group_message_id", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("challenge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defense_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("champion_change_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("battle_in_progress", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_challenger_tg", sa.BigInteger(), nullable=True),
        sa.Column("current_challenger_display_name", sa.String(length=128), nullable=True),
        sa.Column("last_winner_tg", sa.BigInteger(), nullable=True),
        sa.Column("last_winner_display_name", sa.String(length=128), nullable=True),
        sa.Column("last_loser_tg", sa.BigInteger(), nullable=True),
        sa.Column("last_loser_display_name", sa.String(length=128), nullable=True),
        sa.Column("latest_result_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    if not _has_table("xiuxian_arenas"):
        return
    op.drop_table("xiuxian_arenas")
