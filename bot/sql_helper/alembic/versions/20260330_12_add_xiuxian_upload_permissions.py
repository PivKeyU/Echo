"""add xiuxian upload permissions

Revision ID: 20260330_12
Revises: 20260330_11
Create Date: 2026-03-30 21:10:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "20260330_12"
down_revision = "20260330_11"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "xiuxian_image_upload_permissions"):
        op.create_table(
            "xiuxian_image_upload_permissions",
            sa.Column("tg", sa.BigInteger(), primary_key=True, autoincrement=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )

    if _has_table(inspector, "xiuxian_settings") and not _has_column(inspector, "xiuxian_settings", "setting_key"):
        return

    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    exists = bind.execute(
        sa.select(settings.c.setting_key).where(settings.c.setting_key == "allow_non_admin_image_upload")
    ).scalar_one_or_none()
    if exists is None:
        bind.execute(
            settings.insert(),
            [
                {
                    "setting_key": "allow_non_admin_image_upload",
                    "setting_value": False,
                    "updated_at": datetime.utcnow(),
                }
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "xiuxian_settings"):
        settings = sa.table(
            "xiuxian_settings",
            sa.column("setting_key", sa.String(length=64)),
        )
        bind.execute(settings.delete().where(settings.c.setting_key == "allow_non_admin_image_upload"))

    if _has_table(inspector, "xiuxian_image_upload_permissions"):
        op.drop_table("xiuxian_image_upload_permissions")
