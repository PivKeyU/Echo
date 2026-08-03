"""add xiuxian sect duty and metric task fields

Revision ID: 20260424_43a
Revises: 20260422_42a
Create Date: 2026-04-24 10:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_43a"
down_revision = "20260422_42a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    if _has_table("xiuxian_profiles"):
        if not _has_column("xiuxian_profiles", "last_sect_attendance_at"):
            op.add_column("xiuxian_profiles", sa.Column("last_sect_attendance_at", sa.DateTime(), nullable=True))
        if not _has_column("xiuxian_profiles", "last_sect_attendance_method"):
            op.add_column("xiuxian_profiles", sa.Column("last_sect_attendance_method", sa.String(length=16), nullable=True))

    if not _has_table("xiuxian_sect_treasury_items"):
        op.create_table(
            "xiuxian_sect_treasury_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sect_id", sa.Integer(), sa.ForeignKey("xiuxian_sects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("item_kind", sa.String(length=16), nullable=False),
            sa.Column("item_ref_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("sect_id", "item_kind", "item_ref_id", name="uq_xiuxian_sect_treasury_item"),
        )

    if _has_table("xiuxian_tasks"):
        if not _has_column("xiuxian_tasks", "reward_cultivation"):
            op.add_column("xiuxian_tasks", sa.Column("reward_cultivation", sa.Integer(), nullable=False, server_default="0"))
        if not _has_column("xiuxian_tasks", "reward_scale_mode"):
            op.add_column("xiuxian_tasks", sa.Column("reward_scale_mode", sa.String(length=16), nullable=False, server_default="fixed"))
        if not _has_column("xiuxian_tasks", "requirement_metric_key"):
            op.add_column("xiuxian_tasks", sa.Column("requirement_metric_key", sa.String(length=64), nullable=True))
        if not _has_column("xiuxian_tasks", "requirement_metric_target"):
            op.add_column("xiuxian_tasks", sa.Column("requirement_metric_target", sa.Integer(), nullable=False, server_default="0"))

    if _has_table("xiuxian_task_claims"):
        if not _has_column("xiuxian_task_claims", "metric_start_value"):
            op.add_column("xiuxian_task_claims", sa.Column("metric_start_value", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    if _has_table("xiuxian_task_claims") and _has_column("xiuxian_task_claims", "metric_start_value"):
        op.drop_column("xiuxian_task_claims", "metric_start_value")

    if _has_table("xiuxian_tasks"):
        if _has_column("xiuxian_tasks", "requirement_metric_target"):
            op.drop_column("xiuxian_tasks", "requirement_metric_target")
        if _has_column("xiuxian_tasks", "requirement_metric_key"):
            op.drop_column("xiuxian_tasks", "requirement_metric_key")
        if _has_column("xiuxian_tasks", "reward_scale_mode"):
            op.drop_column("xiuxian_tasks", "reward_scale_mode")
        if _has_column("xiuxian_tasks", "reward_cultivation"):
            op.drop_column("xiuxian_tasks", "reward_cultivation")

    if _has_table("xiuxian_sect_treasury_items"):
        op.drop_table("xiuxian_sect_treasury_items")

    if _has_table("xiuxian_profiles"):
        if _has_column("xiuxian_profiles", "last_sect_attendance_method"):
            op.drop_column("xiuxian_profiles", "last_sect_attendance_method")
        if _has_column("xiuxian_profiles", "last_sect_attendance_at"):
            op.drop_column("xiuxian_profiles", "last_sect_attendance_at")
