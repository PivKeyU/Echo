"""add xiuxian plugin tables

Revision ID: 20260329_05
Revises: 20260329_04
Create Date: 2026-03-29 20:30:00
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa

from bot.sql_helper.sql_xiuxian import (
    XiuxianArtifact,
    XiuxianArtifactInventory,
    XiuxianArtifactSet,
    XiuxianDuelRecord,
    XiuxianPill,
    XiuxianPillInventory,
    XiuxianProfile,
    XiuxianSetting,
    XiuxianShopItem,
)


revision = "20260329_05"
down_revision = "20260329_04"
branch_labels = None
depends_on = None


DEFAULT_SETTING_ROWS = [
    {"setting_key": "coin_exchange_rate", "setting_value": 100, "updated_at": datetime.utcnow()},
    {"setting_key": "exchange_fee_percent", "setting_value": 1, "updated_at": datetime.utcnow()},
    {"setting_key": "min_coin_exchange", "setting_value": 100, "updated_at": datetime.utcnow()},
    {"setting_key": "shop_broadcast_cost", "setting_value": 20, "updated_at": datetime.utcnow()},
    {"setting_key": "official_shop_name", "setting_value": "风月阁", "updated_at": datetime.utcnow()},
]


def upgrade() -> None:
    bind = op.get_bind()

    for table in (
        XiuxianSetting.__table__,
        XiuxianProfile.__table__,
        XiuxianArtifactSet.__table__,
        XiuxianArtifact.__table__,
        XiuxianPill.__table__,
        XiuxianArtifactInventory.__table__,
        XiuxianPillInventory.__table__,
        XiuxianShopItem.__table__,
        XiuxianDuelRecord.__table__,
    ):
        table.create(bind, checkfirst=True)

    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    existing_keys = {
        row[0]
        for row in bind.execute(
            sa.select(settings.c.setting_key).where(
                settings.c.setting_key.in_([row["setting_key"] for row in DEFAULT_SETTING_ROWS])
            )
        )
    }
    missing_rows = [row for row in DEFAULT_SETTING_ROWS if row["setting_key"] not in existing_keys]
    if missing_rows:
        bind.execute(settings.insert(), missing_rows)


def downgrade() -> None:
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())
    for table_name in (
        "xiuxian_duel_records",
        "xiuxian_shop_items",
        "xiuxian_pill_inventory",
        "xiuxian_artifact_inventory",
        "xiuxian_pills",
        "xiuxian_artifacts",
        "xiuxian_artifact_sets",
        "xiuxian_profiles",
        "xiuxian_settings",
    ):
        if table_name in table_names:
            op.drop_table(table_name)
