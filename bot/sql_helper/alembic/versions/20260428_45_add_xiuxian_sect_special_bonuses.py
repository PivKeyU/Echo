"""add xiuxian sect special bonus columns for thematic sect differentiation

Revision ID: 20260428_45a
Revises: 20260427_44a
Create Date: 2026-04-28
"""
from alembic import op
from sqlalchemy import Column, Float, Integer


revision = "20260428_45a"
down_revision = "20260427_44a"


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(conn)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("xiuxian_sects", "pill_poison_resist"):
        op.add_column("xiuxian_sects", Column("pill_poison_resist", Float, default=0.0, nullable=False, server_default="0.0"))
    if not _has_column("xiuxian_sects", "pill_poison_cap_bonus"):
        op.add_column("xiuxian_sects", Column("pill_poison_cap_bonus", Integer, default=0, nullable=False, server_default="0"))
    if not _has_column("xiuxian_sects", "farm_growth_speed"):
        op.add_column("xiuxian_sects", Column("farm_growth_speed", Float, default=0.0, nullable=False, server_default="0.0"))
    if not _has_column("xiuxian_sects", "explore_drop_rate"):
        op.add_column("xiuxian_sects", Column("explore_drop_rate", Integer, default=0, nullable=False, server_default="0"))
    if not _has_column("xiuxian_sects", "craft_success_rate"):
        op.add_column("xiuxian_sects", Column("craft_success_rate", Integer, default=0, nullable=False, server_default="0"))
    if not _has_column("xiuxian_sects", "death_penalty_reduce"):
        op.add_column("xiuxian_sects", Column("death_penalty_reduce", Float, default=0.0, nullable=False, server_default="0.0"))


def downgrade() -> None:
    for col in ("pill_poison_resist", "pill_poison_cap_bonus", "farm_growth_speed", "explore_drop_rate", "craft_success_rate", "death_penalty_reduce"):
        if _has_column("xiuxian_sects", col):
            op.drop_column("xiuxian_sects", col)
