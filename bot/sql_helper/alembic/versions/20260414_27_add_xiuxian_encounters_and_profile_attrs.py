"""add xiuxian encounters and profile attrs

Revision ID: 20260414_27
Revises: 20260414_26
Create Date: 2026-04-14 23:58:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_27"
down_revision = "20260414_26"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column.get("name") == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if _has_table("xiuxian_profiles"):
        with op.batch_alter_table("xiuxian_profiles") as batch_op:
            if not _has_column("xiuxian_profiles", "willpower"):
                batch_op.add_column(sa.Column("willpower", sa.Integer(), nullable=False, server_default="10"))
            if not _has_column("xiuxian_profiles", "charisma"):
                batch_op.add_column(sa.Column("charisma", sa.Integer(), nullable=False, server_default="10"))
            if not _has_column("xiuxian_profiles", "karma"):
                batch_op.add_column(sa.Column("karma", sa.Integer(), nullable=False, server_default="10"))

    if not _has_table("xiuxian_encounter_templates"):
        op.create_table(
            "xiuxian_encounter_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("image_url", sa.String(length=512), nullable=True),
            sa.Column("button_text", sa.String(length=64), nullable=True),
            sa.Column("success_text", sa.Text(), nullable=True),
            sa.Column("broadcast_text", sa.Text(), nullable=True),
            sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("active_seconds", sa.Integer(), nullable=False, server_default="90"),
            sa.Column("min_realm_stage", sa.String(length=32), nullable=True),
            sa.Column("min_realm_layer", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("min_combat_power", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_stone_min", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_stone_max", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_cultivation_min", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_cultivation_max", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_item_kind", sa.String(length=16), nullable=True),
            sa.Column("reward_item_ref_id", sa.Integer(), nullable=True),
            sa.Column("reward_item_quantity_min", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reward_item_quantity_max", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reward_willpower", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_charisma", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_karma", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("xiuxian_encounter_instances"):
        op.create_table(
            "xiuxian_encounter_instances",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_id", sa.Integer(), sa.ForeignKey("xiuxian_encounter_templates.id", ondelete="SET NULL"), nullable=True),
            sa.Column("template_name", sa.String(length=128), nullable=False),
            sa.Column("group_chat_id", sa.BigInteger(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=True),
            sa.Column("button_text", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("reward_payload", sa.JSON(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("claimer_tg", sa.BigInteger(), nullable=True),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    if _has_table("xiuxian_encounter_instances"):
        op.drop_table("xiuxian_encounter_instances")
    if _has_table("xiuxian_encounter_templates"):
        op.drop_table("xiuxian_encounter_templates")

    if _has_table("xiuxian_profiles"):
        with op.batch_alter_table("xiuxian_profiles") as batch_op:
            if _has_column("xiuxian_profiles", "karma"):
                batch_op.drop_column("karma")
            if _has_column("xiuxian_profiles", "charisma"):
                batch_op.drop_column("charisma")
            if _has_column("xiuxian_profiles", "willpower"):
                batch_op.drop_column("willpower")
