"""add xiuxian red envelope image

Revision ID: 20260413_20
Revises: 20260413_19
Create Date: 2026-04-13 20:30:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "20260413_20"
down_revision = "20260413_19"
branch_labels = None
depends_on = None


MERIT_SETTING_KEYS = [
    "red_packet_merit_min_stone",
    "red_packet_merit_min_count",
    "red_packet_merit_reward",
    "red_packet_merit_modes",
]


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "xiuxian_red_envelopes") and not _has_column(inspector, "xiuxian_red_envelopes", "image_url"):
        op.add_column("xiuxian_red_envelopes", sa.Column("image_url", sa.String(length=512), nullable=True))

    if not _has_table(inspector, "xiuxian_settings"):
        return

    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
    )
    bind.execute(settings.delete().where(settings.c.setting_key.in_(MERIT_SETTING_KEYS)))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "xiuxian_settings"):
        settings = sa.table(
            "xiuxian_settings",
            sa.column("setting_key", sa.String(length=64)),
            sa.column("setting_value", sa.JSON()),
            sa.column("updated_at", sa.DateTime()),
        )
        default_rows = [
            {
                "setting_key": "red_packet_merit_min_stone",
                "setting_value": 100,
                "updated_at": datetime.utcnow(),
            },
            {
                "setting_key": "red_packet_merit_min_count",
                "setting_value": 3,
                "updated_at": datetime.utcnow(),
            },
            {
                "setting_key": "red_packet_merit_reward",
                "setting_value": 2,
                "updated_at": datetime.utcnow(),
            },
            {
                "setting_key": "red_packet_merit_modes",
                "setting_value": ["normal", "lucky", "exclusive"],
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

    if _has_table(inspector, "xiuxian_red_envelopes") and _has_column(inspector, "xiuxian_red_envelopes", "image_url"):
        op.drop_column("xiuxian_red_envelopes", "image_url")
