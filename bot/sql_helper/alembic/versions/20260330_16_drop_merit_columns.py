"""drop merit columns

Revision ID: 20260330_16
Revises: 20260330_15
Create Date: 2026-03-31 01:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260330_16"
down_revision = "20260330_15"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _drop_column_if_exists(inspector, table_name: str, column_name: str) -> None:
    if _has_table(inspector, table_name) and _has_column(inspector, table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # xiuxian_profiles.merit
    _drop_column_if_exists(inspector, "xiuxian_profiles", "merit")

    # xiuxian_sects.min_merit
    _drop_column_if_exists(inspector, "xiuxian_sects", "min_merit")

    # xiuxian_sect_roles.merit_bonus
    _drop_column_if_exists(inspector, "xiuxian_sect_roles", "merit_bonus")

    # xiuxian_artifacts.merit_bonus
    _drop_column_if_exists(inspector, "xiuxian_artifacts", "merit_bonus")

    # xiuxian_talismans.merit_bonus
    _drop_column_if_exists(inspector, "xiuxian_talismans", "merit_bonus")

    # xiuxian_recipes.required_merit
    _drop_column_if_exists(inspector, "xiuxian_recipes", "required_merit")

    # xiuxian_scene_drops.merit_reward
    _drop_column_if_exists(inspector, "xiuxian_scene_drops", "merit_reward")

    # xiuxian_explorations.merit_reward
    _drop_column_if_exists(inspector, "xiuxian_explorations", "merit_reward")

    # xiuxian_tasks.reward_merit
    _drop_column_if_exists(inspector, "xiuxian_tasks", "reward_merit")

    # xiuxian_red_envelopes.merit_rewarded
    _drop_column_if_exists(inspector, "xiuxian_red_envelopes", "merit_rewarded")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _add_if_missing(table: str, col: sa.Column) -> None:
        if _has_table(inspector, table) and not _has_column(inspector, table, col.name):
            op.add_column(table, col)

    _add_if_missing("xiuxian_profiles", sa.Column("merit", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_sects", sa.Column("min_merit", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_sect_roles", sa.Column("merit_bonus", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_artifacts", sa.Column("merit_bonus", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_talismans", sa.Column("merit_bonus", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_recipes", sa.Column("required_merit", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_scene_drops", sa.Column("merit_reward", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_explorations", sa.Column("merit_reward", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_tasks", sa.Column("reward_merit", sa.Integer(), nullable=False, server_default="0"))
    _add_if_missing("xiuxian_red_envelopes", sa.Column("merit_rewarded", sa.Boolean(), nullable=False, server_default=sa.false()))
