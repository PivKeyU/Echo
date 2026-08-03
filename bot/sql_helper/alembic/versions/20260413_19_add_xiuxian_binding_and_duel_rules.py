"""add xiuxian binding and duel rules

Revision ID: 20260413_19
Revises: 20260401_18
Create Date: 2026-04-13 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "20260413_19"
down_revision = "20260401_18"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "xiuxian_artifact_inventory") and not _has_column(inspector, "xiuxian_artifact_inventory", "bound_quantity"):
        op.add_column(
            "xiuxian_artifact_inventory",
            sa.Column("bound_quantity", sa.Integer(), nullable=False, server_default="0"),
        )

    if _has_table(inspector, "xiuxian_talisman_inventory") and not _has_column(inspector, "xiuxian_talisman_inventory", "bound_quantity"):
        op.add_column(
            "xiuxian_talisman_inventory",
            sa.Column("bound_quantity", sa.Integer(), nullable=False, server_default="0"),
        )

    if not _has_table(inspector, "xiuxian_settings"):
        return

    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    default_rows = [
        {
            "setting_key": "equipment_unbind_cost",
            "setting_value": 100,
            "updated_at": datetime.utcnow(),
        },
        {
            "setting_key": "duel_winner_steal_percent",
            "setting_value": 25,
            "updated_at": datetime.utcnow(),
        },
    ]
    existing_keys = {
        row[0]
        for row in bind.execute(
            sa.select(settings.c.setting_key).where(
                settings.c.setting_key.in_([row["setting_key"] for row in default_rows])
            )
        )
    }
    missing_rows = [row for row in default_rows if row["setting_key"] not in existing_keys]
    if missing_rows:
        bind.execute(settings.insert(), missing_rows)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "xiuxian_settings"):
        settings = sa.table(
            "xiuxian_settings",
            sa.column("setting_key", sa.String(length=64)),
        )
        bind.execute(
            settings.delete().where(
                settings.c.setting_key.in_(["equipment_unbind_cost", "duel_winner_steal_percent"])
            )
        )

    if _has_table(inspector, "xiuxian_talisman_inventory") and _has_column(inspector, "xiuxian_talisman_inventory", "bound_quantity"):
        op.drop_column("xiuxian_talisman_inventory", "bound_quantity")

    if _has_table(inspector, "xiuxian_artifact_inventory") and _has_column(inspector, "xiuxian_artifact_inventory", "bound_quantity"):
        op.drop_column("xiuxian_artifact_inventory", "bound_quantity")
