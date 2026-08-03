"""add advanced xiuxian fields and talisman tables

Revision ID: 20260329_06
Revises: 20260329_05
Create Date: 2026-03-29 22:30:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = "20260329_06"
down_revision = "20260329_05"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    table_names = _table_names()
    bind = op.get_bind()

    if "xiuxian_profiles" in table_names:
        columns = _column_names("xiuxian_profiles")
        if "active_talisman_id" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("active_talisman_id", sa.Integer(), nullable=True),
            )
        if "retreat_started_at" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("retreat_started_at", sa.DateTime(), nullable=True),
            )
        if "retreat_end_at" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("retreat_end_at", sa.DateTime(), nullable=True),
            )
        if "retreat_gain_per_minute" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("retreat_gain_per_minute", sa.Integer(), nullable=False, server_default="0"),
            )
        if "retreat_cost_per_minute" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("retreat_cost_per_minute", sa.Integer(), nullable=False, server_default="0"),
            )
        if "retreat_minutes_total" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("retreat_minutes_total", sa.Integer(), nullable=False, server_default="0"),
            )
        if "retreat_minutes_resolved" not in columns:
            op.add_column(
                "xiuxian_profiles",
                sa.Column("retreat_minutes_resolved", sa.Integer(), nullable=False, server_default="0"),
            )

        columns = _column_names("xiuxian_profiles")
        for column_name in (
            "retreat_gain_per_minute",
            "retreat_cost_per_minute",
            "retreat_minutes_total",
            "retreat_minutes_resolved",
        ):
            if column_name in columns:
                op.alter_column("xiuxian_profiles", column_name, server_default=None)

    if "xiuxian_artifacts" in table_names:
        columns = _column_names("xiuxian_artifacts")
        if "min_realm_stage" not in columns:
            op.add_column(
                "xiuxian_artifacts",
                sa.Column("min_realm_stage", sa.String(length=32), nullable=True),
            )
        if "min_realm_layer" not in columns:
            op.add_column(
                "xiuxian_artifacts",
                sa.Column("min_realm_layer", sa.Integer(), nullable=False, server_default="1"),
            )
            op.alter_column("xiuxian_artifacts", "min_realm_layer", server_default=None)

    if "xiuxian_pills" in table_names:
        columns = _column_names("xiuxian_pills")
        if "min_realm_stage" not in columns:
            op.add_column(
                "xiuxian_pills",
                sa.Column("min_realm_stage", sa.String(length=32), nullable=True),
            )
        if "min_realm_layer" not in columns:
            op.add_column(
                "xiuxian_pills",
                sa.Column("min_realm_layer", sa.Integer(), nullable=False, server_default="1"),
            )
            op.alter_column("xiuxian_pills", "min_realm_layer", server_default=None)

    if "xiuxian_talismans" not in table_names:
        op.create_table(
            "xiuxian_talismans",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("rarity", sa.String(length=32), nullable=False, server_default="凡品"),
            sa.Column("image_url", sa.String(length=512), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("power_bonus", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duel_rate_bonus", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("merit_bonus", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_realm_stage", sa.String(length=32), nullable=True),
            sa.Column("min_realm_layer", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_xiuxian_talisman_name"),
        )
        op.alter_column("xiuxian_talismans", "rarity", server_default=None)
        op.alter_column("xiuxian_talismans", "power_bonus", server_default=None)
        op.alter_column("xiuxian_talismans", "duel_rate_bonus", server_default=None)
        op.alter_column("xiuxian_talismans", "merit_bonus", server_default=None)
        op.alter_column("xiuxian_talismans", "min_realm_layer", server_default=None)
        op.alter_column("xiuxian_talismans", "enabled", server_default=None)
        op.alter_column("xiuxian_talismans", "created_at", server_default=None)
        op.alter_column("xiuxian_talismans", "updated_at", server_default=None)

    table_names = _table_names()
    if "xiuxian_talisman_inventory" not in table_names:
        op.create_table(
            "xiuxian_talisman_inventory",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tg", sa.BigInteger(), nullable=False),
            sa.Column("talisman_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["talisman_id"], ["xiuxian_talismans.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tg", "talisman_id", name="uq_xiuxian_talisman_inventory"),
        )
        op.alter_column("xiuxian_talisman_inventory", "quantity", server_default=None)
        op.alter_column("xiuxian_talisman_inventory", "created_at", server_default=None)
        op.alter_column("xiuxian_talisman_inventory", "updated_at", server_default=None)

    table_names = _table_names()
    if "xiuxian_duel_records" in table_names:
        index_names = _index_names("xiuxian_duel_records")
        if "ix_xiuxian_duel_created_at" not in index_names:
            op.create_index("ix_xiuxian_duel_created_at", "xiuxian_duel_records", ["created_at"], unique=False)

    settings = sa.table(
        "xiuxian_settings",
        sa.column("setting_key", sa.String(length=64)),
        sa.column("setting_value", sa.JSON()),
        sa.column("updated_at", sa.DateTime()),
    )
    default_rows = [
        {"setting_key": "chat_cultivation_chance", "setting_value": 8, "updated_at": datetime.utcnow()},
        {"setting_key": "chat_cultivation_min_gain", "setting_value": 1, "updated_at": datetime.utcnow()},
        {"setting_key": "chat_cultivation_max_gain", "setting_value": 3, "updated_at": datetime.utcnow()},
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

    min_coin_exchange = bind.execute(
        sa.select(settings.c.setting_value).where(settings.c.setting_key == "min_coin_exchange")
    ).scalar_one_or_none()
    normalized_value = min_coin_exchange
    if isinstance(min_coin_exchange, str):
        try:
            normalized_value = int(min_coin_exchange)
        except ValueError:
            normalized_value = min_coin_exchange
    if normalized_value == 100:
        bind.execute(
            settings.update()
            .where(settings.c.setting_key == "min_coin_exchange")
            .values(setting_value=1, updated_at=datetime.utcnow())
        )


def downgrade() -> None:
    table_names = _table_names()

    if "xiuxian_talisman_inventory" in table_names:
        op.drop_table("xiuxian_talisman_inventory")

    table_names = _table_names()
    if "xiuxian_talismans" in table_names:
        op.drop_table("xiuxian_talismans")

    if "xiuxian_pills" in table_names:
        columns = _column_names("xiuxian_pills")
        if "min_realm_layer" in columns:
            op.drop_column("xiuxian_pills", "min_realm_layer")
        if "min_realm_stage" in columns:
            op.drop_column("xiuxian_pills", "min_realm_stage")

    if "xiuxian_artifacts" in table_names:
        columns = _column_names("xiuxian_artifacts")
        if "min_realm_layer" in columns:
            op.drop_column("xiuxian_artifacts", "min_realm_layer")
        if "min_realm_stage" in columns:
            op.drop_column("xiuxian_artifacts", "min_realm_stage")

    if "xiuxian_profiles" in table_names:
        columns = _column_names("xiuxian_profiles")
        for column_name in (
            "retreat_minutes_resolved",
            "retreat_minutes_total",
            "retreat_cost_per_minute",
            "retreat_gain_per_minute",
            "retreat_end_at",
            "retreat_started_at",
            "active_talisman_id",
        ):
            if column_name in columns:
                op.drop_column("xiuxian_profiles", column_name)

    if "xiuxian_settings" in table_names:
        settings = sa.table(
            "xiuxian_settings",
            sa.column("setting_key", sa.String(length=64)),
        )
        op.get_bind().execute(
            settings.delete().where(
                settings.c.setting_key.in_(
                    [
                        "chat_cultivation_chance",
                        "chat_cultivation_min_gain",
                        "chat_cultivation_max_gain",
                    ]
                )
            )
        )
