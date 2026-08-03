"""add xiuxian mentorship tables

Revision ID: 20260417_33
Revises: 20260417_32
Create Date: 2026-04-17 18:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_33"
down_revision = "20260417_32"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("xiuxian_mentorships"):
        op.create_table(
            "xiuxian_mentorships",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("mentor_tg", sa.BigInteger(), nullable=False),
            sa.Column("disciple_tg", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("bond_value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("teach_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("consult_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_teach_at", sa.DateTime(), nullable=True),
            sa.Column("last_consult_at", sa.DateTime(), nullable=True),
            sa.Column("mentor_realm_stage_snapshot", sa.String(length=32), nullable=True),
            sa.Column("mentor_realm_layer_snapshot", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("disciple_realm_stage_snapshot", sa.String(length=32), nullable=True),
            sa.Column("disciple_realm_layer_snapshot", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("graduated_at", sa.DateTime(), nullable=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("mentor_tg", "disciple_tg", name="uq_xiuxian_mentorship_pair"),
        )

    if not _has_table("xiuxian_mentorship_requests"):
        op.create_table(
            "xiuxian_mentorship_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sponsor_tg", sa.BigInteger(), nullable=False),
            sa.Column("target_tg", sa.BigInteger(), nullable=False),
            sa.Column("sponsor_role", sa.String(length=16), nullable=False),
            sa.Column("message", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("responded_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _has_table("xiuxian_mentorship_requests"):
        op.drop_table("xiuxian_mentorship_requests")

    if _has_table("xiuxian_mentorships"):
        op.drop_table("xiuxian_mentorships")
