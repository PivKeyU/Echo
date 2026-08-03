"""add xiuxian duel modes, servitude, death state, and richer sect gates

Revision ID: 20260415_28
Revises: 20260414_27
Create Date: 2026-04-15 10:20:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "20260415_28"
down_revision = "20260414_27"
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
            if not _has_column("xiuxian_profiles", "master_tg"):
                batch_op.add_column(sa.Column("master_tg", sa.BigInteger(), nullable=True))
            if not _has_column("xiuxian_profiles", "servitude_started_at"):
                batch_op.add_column(sa.Column("servitude_started_at", sa.DateTime(), nullable=True))
            if not _has_column("xiuxian_profiles", "servitude_challenge_available_at"):
                batch_op.add_column(sa.Column("servitude_challenge_available_at", sa.DateTime(), nullable=True))
            if not _has_column("xiuxian_profiles", "death_at"):
                batch_op.add_column(sa.Column("death_at", sa.DateTime(), nullable=True))
            if not _has_column("xiuxian_profiles", "rebirth_count"):
                batch_op.add_column(sa.Column("rebirth_count", sa.Integer(), nullable=False, server_default="0"))

    if _has_table("xiuxian_sects"):
        with op.batch_alter_table("xiuxian_sects") as batch_op:
            if not _has_column("xiuxian_sects", "min_willpower"):
                batch_op.add_column(sa.Column("min_willpower", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_sects", "min_charisma"):
                batch_op.add_column(sa.Column("min_charisma", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_sects", "min_karma"):
                batch_op.add_column(sa.Column("min_karma", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_sects", "min_body_movement"):
                batch_op.add_column(sa.Column("min_body_movement", sa.Integer(), nullable=False, server_default="0"))
            if not _has_column("xiuxian_sects", "min_combat_power"):
                batch_op.add_column(sa.Column("min_combat_power", sa.Integer(), nullable=False, server_default="0"))

    if _has_table("xiuxian_duel_bet_pools") and not _has_column("xiuxian_duel_bet_pools", "duel_mode"):
        with op.batch_alter_table("xiuxian_duel_bet_pools") as batch_op:
            batch_op.add_column(sa.Column("duel_mode", sa.String(length=16), nullable=False, server_default="standard"))

    if _has_table("xiuxian_duel_records") and not _has_column("xiuxian_duel_records", "duel_mode"):
        with op.batch_alter_table("xiuxian_duel_records") as batch_op:
            batch_op.add_column(sa.Column("duel_mode", sa.String(length=16), nullable=False, server_default="standard"))

    if _has_table("xiuxian_settings"):
        settings = sa.table(
            "xiuxian_settings",
            sa.column("setting_key", sa.String(length=64)),
            sa.column("setting_value", sa.JSON()),
            sa.column("updated_at", sa.DateTime()),
        )
        bind = op.get_bind()
        default_rows = [
            {
                "setting_key": "slave_tribute_percent",
                "setting_value": 20,
                "updated_at": datetime.utcnow(),
            },
            {
                "setting_key": "slave_challenge_cooldown_hours",
                "setting_value": 24,
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
    if _has_table("xiuxian_settings"):
        settings = sa.table(
            "xiuxian_settings",
            sa.column("setting_key", sa.String(length=64)),
        )
        op.get_bind().execute(
            settings.delete().where(
                settings.c.setting_key.in_(["slave_tribute_percent", "slave_challenge_cooldown_hours"])
            )
        )

    if _has_table("xiuxian_duel_records") and _has_column("xiuxian_duel_records", "duel_mode"):
        with op.batch_alter_table("xiuxian_duel_records") as batch_op:
            batch_op.drop_column("duel_mode")

    if _has_table("xiuxian_duel_bet_pools") and _has_column("xiuxian_duel_bet_pools", "duel_mode"):
        with op.batch_alter_table("xiuxian_duel_bet_pools") as batch_op:
            batch_op.drop_column("duel_mode")

    if _has_table("xiuxian_sects"):
        with op.batch_alter_table("xiuxian_sects") as batch_op:
            if _has_column("xiuxian_sects", "min_combat_power"):
                batch_op.drop_column("min_combat_power")
            if _has_column("xiuxian_sects", "min_body_movement"):
                batch_op.drop_column("min_body_movement")
            if _has_column("xiuxian_sects", "min_karma"):
                batch_op.drop_column("min_karma")
            if _has_column("xiuxian_sects", "min_charisma"):
                batch_op.drop_column("min_charisma")
            if _has_column("xiuxian_sects", "min_willpower"):
                batch_op.drop_column("min_willpower")

    if _has_table("xiuxian_profiles"):
        with op.batch_alter_table("xiuxian_profiles") as batch_op:
            if _has_column("xiuxian_profiles", "rebirth_count"):
                batch_op.drop_column("rebirth_count")
            if _has_column("xiuxian_profiles", "death_at"):
                batch_op.drop_column("death_at")
            if _has_column("xiuxian_profiles", "servitude_challenge_available_at"):
                batch_op.drop_column("servitude_challenge_available_at")
            if _has_column("xiuxian_profiles", "servitude_started_at"):
                batch_op.drop_column("servitude_started_at")
            if _has_column("xiuxian_profiles", "master_tg"):
                batch_op.drop_column("master_tg")
