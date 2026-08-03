"""add shop tables

Revision ID: 20260413_21
Revises: 20260413_20
Create Date: 2026-04-13 22:30:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "20260413_21"
down_revision = "20260413_20"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "shop_settings"):
        op.create_table(
            "shop_settings",
            sa.Column("setting_key", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("setting_value", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _has_table(inspector, "shop_items"):
        op.create_table(
            "shop_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_tg", sa.BigInteger(), nullable=True),
            sa.Column("owner_display_name", sa.String(length=128), nullable=True),
            sa.Column("owner_username", sa.String(length=64), nullable=True),
            sa.Column("title", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("image_url", sa.String(length=512), nullable=True),
            sa.Column("delivery_text", sa.Text(), nullable=True),
            sa.Column("price_iv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sold_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notify_group", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("official", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _has_table(inspector, "shop_orders"):
        op.create_table(
            "shop_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("item_id", sa.Integer(), nullable=True),
            sa.Column("buyer_tg", sa.BigInteger(), nullable=False),
            sa.Column("seller_tg", sa.BigInteger(), nullable=True),
            sa.Column("item_title", sa.String(length=128), nullable=False),
            sa.Column("image_url", sa.String(length=512), nullable=True),
            sa.Column("delivery_text", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price_iv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_price_iv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="delivered"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    settings = sa.table(
        "shop_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    default_rows = [
        {"setting_key": "allow_user_listing", "setting_value": False, "updated_at": datetime.utcnow()},
        {"setting_key": "currency_name", "setting_value": "片刻碎片", "updated_at": datetime.utcnow()},
        {"setting_key": "shop_title", "setting_value": "仙舟小铺", "updated_at": datetime.utcnow()},
        {"setting_key": "shop_notice", "setting_value": "欢迎使用 Emby 货币购买数字商品。", "updated_at": datetime.utcnow()},
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

    if _has_table(inspector, "shop_orders"):
        op.drop_table("shop_orders")

    if _has_table(inspector, "shop_items"):
        op.drop_table("shop_items")

    if _has_table(inspector, "shop_settings"):
        op.drop_table("shop_settings")
