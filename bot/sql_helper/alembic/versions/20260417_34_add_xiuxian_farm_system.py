"""add xiuxian farm system

Revision ID: 20260417_35a
Revises: 20260417_34a
Create Date: 2026-04-17 20:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_35a"
down_revision = "20260417_34a"
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
    if _has_table("xiuxian_materials"):
        with op.batch_alter_table("xiuxian_materials") as batch_op:
            if not _has_column("xiuxian_materials", "can_plant"):
                batch_op.add_column(sa.Column("can_plant", sa.Boolean(), nullable=False, server_default=sa.false()))
            if not _has_column("xiuxian_materials", "seed_price_stone"):
                batch_op.add_column(sa.Column("seed_price_stone", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_materials", "growth_minutes"):
                batch_op.add_column(sa.Column("growth_minutes", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_materials", "yield_min"):
                batch_op.add_column(sa.Column("yield_min", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_materials", "yield_max"):
                batch_op.add_column(sa.Column("yield_max", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_materials", "unlock_realm_stage"):
                batch_op.add_column(sa.Column("unlock_realm_stage", sa.String(length=32), nullable=True))
            if not _has_column("xiuxian_materials", "unlock_realm_layer"):
                batch_op.add_column(sa.Column("unlock_realm_layer", sa.Integer(), nullable=False, server_default="1"))

    if not _has_table("xiuxian_farm_plots"):
        op.create_table(
            "xiuxian_farm_plots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tg", sa.BigInteger(), nullable=False),
            sa.Column("slot_index", sa.Integer(), nullable=False),
            sa.Column("unlocked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("current_material_id", sa.Integer(), sa.ForeignKey("xiuxian_materials.id", ondelete="SET NULL"), nullable=True),
            sa.Column("planted_at", sa.DateTime(), nullable=True),
            sa.Column("mature_at", sa.DateTime(), nullable=True),
            sa.Column("harvest_deadline_at", sa.DateTime(), nullable=True),
            sa.Column("base_yield", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("needs_watering", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("watered", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("pest_risk", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("pest_cleared", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("fertilized", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tg", "slot_index", name="uq_xiuxian_farm_plot_slot"),
        )


def downgrade() -> None:
    if _has_table("xiuxian_farm_plots"):
        op.drop_table("xiuxian_farm_plots")

    if _has_table("xiuxian_materials"):
        with op.batch_alter_table("xiuxian_materials") as batch_op:
            if _has_column("xiuxian_materials", "unlock_realm_layer"):
                batch_op.drop_column("unlock_realm_layer")
            if _has_column("xiuxian_materials", "unlock_realm_stage"):
                batch_op.drop_column("unlock_realm_stage")
            if _has_column("xiuxian_materials", "yield_max"):
                batch_op.drop_column("yield_max")
            if _has_column("xiuxian_materials", "yield_min"):
                batch_op.drop_column("yield_min")
            if _has_column("xiuxian_materials", "growth_minutes"):
                batch_op.drop_column("growth_minutes")
            if _has_column("xiuxian_materials", "seed_price_stone"):
                batch_op.drop_column("seed_price_stone")
            if _has_column("xiuxian_materials", "can_plant"):
                batch_op.drop_column("can_plant")
