"""expand xiuxian artifact equipment limit

Revision ID: 20260512_56a
Revises: 20260508_55a
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "20260512_56a"
down_revision = "20260508_55a"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("xiuxian_settings"):
        return
    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    bind = op.get_bind()
    row = bind.execute(
        sa.select(settings.c.setting_value).where(settings.c.setting_key == "artifact_equip_limit")
    ).first()
    if row is None:
        bind.execute(
            settings.insert().values(
                setting_key="artifact_equip_limit",
                setting_value=6,
                updated_at=datetime.utcnow(),
            )
        )
        return
    try:
        current_value = int(row[0] or 0)
    except (TypeError, ValueError):
        current_value = 0
    if current_value <= 3:
        bind.execute(
            settings.update()
            .where(settings.c.setting_key == "artifact_equip_limit")
            .values(setting_value=6, updated_at=datetime.utcnow())
        )


def downgrade() -> None:
    if not _has_table("xiuxian_settings"):
        return
    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    bind = op.get_bind()
    row = bind.execute(
        sa.select(settings.c.setting_value).where(settings.c.setting_key == "artifact_equip_limit")
    ).first()
    try:
        current_value = int((row or [None])[0] or 0)
    except (TypeError, ValueError):
        current_value = 0
    if current_value == 6:
        bind.execute(
            settings.update()
            .where(settings.c.setting_key == "artifact_equip_limit")
            .values(setting_value=3, updated_at=datetime.utcnow())
        )
