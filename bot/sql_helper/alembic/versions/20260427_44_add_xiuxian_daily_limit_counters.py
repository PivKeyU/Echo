"""add xiuxian daily limit counters for exploration / fishing / encounter claim

Revision ID: 20260427_44a
Revises: 20260424_43a
Create Date: 2026-04-27
"""
from alembic import op
from sqlalchemy import Column, Integer, String

revision = "20260427_44a"
down_revision = "20260424_43a"


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(conn)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("xiuxian_profiles", "explore_daily_count"):
        op.add_column("xiuxian_profiles", Column("explore_daily_count", Integer, default=0, nullable=False, server_default="0"))
    if not _has_column("xiuxian_profiles", "explore_day_key"):
        op.add_column("xiuxian_profiles", Column("explore_day_key", String(16), nullable=True))
    if not _has_column("xiuxian_profiles", "fish_daily_count"):
        op.add_column("xiuxian_profiles", Column("fish_daily_count", Integer, default=0, nullable=False, server_default="0"))
    if not _has_column("xiuxian_profiles", "fish_day_key"):
        op.add_column("xiuxian_profiles", Column("fish_day_key", String(16), nullable=True))
    if not _has_column("xiuxian_profiles", "encounter_daily_count"):
        op.add_column("xiuxian_profiles", Column("encounter_daily_count", Integer, default=0, nullable=False, server_default="0"))
    if not _has_column("xiuxian_profiles", "encounter_day_key"):
        op.add_column("xiuxian_profiles", Column("encounter_day_key", String(16), nullable=True))


def downgrade() -> None:
    for col in ("explore_daily_count", "explore_day_key", "fish_daily_count", "fish_day_key", "encounter_daily_count", "encounter_day_key"):
        if _has_column("xiuxian_profiles", col):
            op.drop_column("xiuxian_profiles", col)
