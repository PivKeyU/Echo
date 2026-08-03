"""add xiuxian marriage tables

Revision ID: 20260417_36a
Revises: 20260417_35a
Create Date: 2026-04-17 20:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_36a"
down_revision = "20260417_35a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    if _has_table("xiuxian_profiles") and not _has_column("xiuxian_profiles", "gender"):
        op.add_column("xiuxian_profiles", sa.Column("gender", sa.String(length=16), nullable=True))

    if not _has_table("xiuxian_marriages"):
        op.create_table(
            "xiuxian_marriages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("husband_tg", sa.BigInteger(), nullable=False),
            sa.Column("wife_tg", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("bond_value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("dual_cultivation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_dual_cultivation_at", sa.DateTime(), nullable=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("husband_tg", "wife_tg", name="uq_xiuxian_marriage_pair"),
        )

    if not _has_table("xiuxian_marriage_requests"):
        op.create_table(
            "xiuxian_marriage_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sponsor_tg", sa.BigInteger(), nullable=False),
            sa.Column("target_tg", sa.BigInteger(), nullable=False),
            sa.Column("message", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("responded_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _has_table("xiuxian_marriage_requests"):
        op.drop_table("xiuxian_marriage_requests")

    if _has_table("xiuxian_marriages"):
        op.drop_table("xiuxian_marriages")

    if _has_table("xiuxian_profiles") and _has_column("xiuxian_profiles", "gender"):
        op.drop_column("xiuxian_profiles", "gender")
