"""add xiuxian boss tables for boss battle gameplay

Revision ID: 20260428_46a
Revises: 20260428_45a
Create Date: 2026-04-28
"""
from alembic import op
from sqlalchemy import Column, BigInteger, Integer, String, Text, JSON, DateTime, Float, Boolean

revision = "20260428_46a"
down_revision = "20260428_45a"


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(conn)
    return table in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(conn)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    # xiuxian_boss_config
    if not _has_table("xiuxian_boss_config"):
        op.create_table(
            "xiuxian_boss_config",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("name", String(128), nullable=False),
            Column("boss_type", String(16), nullable=False, server_default="personal"),
            Column("realm_stage", String(32), nullable=False),
            Column("description", Text, nullable=True),
            Column("image_url", String(512), nullable=True),
            Column("hp", Integer, nullable=False, server_default="500"),
            Column("attack_power", Integer, nullable=False, server_default="30"),
            Column("defense_power", Integer, nullable=False, server_default="15"),
            Column("body_movement", Integer, nullable=False, server_default="10"),
            Column("divine_sense", Integer, nullable=False, server_default="10"),
            Column("fortune", Integer, nullable=False, server_default="10"),
            Column("qi_blood", Integer, nullable=False, server_default="500"),
            Column("true_yuan", Integer, nullable=False, server_default="200"),
            Column("skill_name", String(64), nullable=True),
            Column("skill_ratio_percent", Integer, nullable=False, server_default="30"),
            Column("skill_hit_bonus", Integer, nullable=False, server_default="0"),
            Column("passive_name", String(64), nullable=True),
            Column("passive_effect_kind", String(16), nullable=True),
            Column("passive_ratio_percent", Integer, nullable=False, server_default="0"),
            Column("passive_chance", Integer, nullable=False, server_default="25"),
            Column("loot_pills_json", JSON, nullable=True),
            Column("loot_materials_json", JSON, nullable=True),
            Column("loot_artifacts_json", JSON, nullable=True),
            Column("loot_talismans_json", JSON, nullable=True),
            Column("loot_recipes_json", JSON, nullable=True),
            Column("loot_techniques_json", JSON, nullable=True),
            Column("stone_reward_min", Integer, nullable=False, server_default="0"),
            Column("stone_reward_max", Integer, nullable=False, server_default="0"),
            Column("cultivation_reward", Integer, nullable=False, server_default="0"),
            Column("daily_attempt_limit", Integer, nullable=False, server_default="3"),
            Column("ticket_cost_stone", Integer, nullable=False, server_default="100"),
            Column("flavor_text", Text, nullable=True),
            Column("sort_order", Integer, nullable=False, server_default="0"),
            Column("enabled", Boolean, nullable=False, server_default="1"),
            Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
            Column("updated_at", DateTime, nullable=False, server_default=op.f("now()")),
        )

    # xiuxian_boss_defeats
    if not _has_table("xiuxian_boss_defeats"):
        op.create_table(
            "xiuxian_boss_defeats",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("tg", BigInteger, nullable=False),
            Column("boss_id", Integer, nullable=False),
            Column("defeat_count", Integer, nullable=False, server_default="1"),
            Column("daily_attempts", Integer, nullable=False, server_default="0"),
            Column("day_key", String(16), nullable=False, server_default=""),
            Column("last_defeated_at", DateTime, nullable=True),
            Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
            Column("updated_at", DateTime, nullable=False, server_default=op.f("now()")),
        )
        op.create_unique_constraint("uq_boss_defeat_tg_boss", "xiuxian_boss_defeats", ["tg", "boss_id"])

    # xiuxian_world_boss_instances
    if not _has_table("xiuxian_world_boss_instances"):
        op.create_table(
            "xiuxian_world_boss_instances",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("boss_id", Integer, nullable=False),
            Column("current_hp", Integer, nullable=False),
            Column("max_hp", Integer, nullable=False),
            Column("status", String(16), nullable=False, server_default="active"),
            Column("spawned_at", DateTime, nullable=False, server_default=op.f("now()")),
            Column("expires_at", DateTime, nullable=False),
            Column("defeated_at", DateTime, nullable=True),
            Column("notice_message_id", Integer, nullable=True),
            Column("notice_group_chat_id", BigInteger, nullable=True),
            Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
            Column("updated_at", DateTime, nullable=False, server_default=op.f("now()")),
        )

    # xiuxian_world_boss_damages
    if not _has_table("xiuxian_world_boss_damages"):
        op.create_table(
            "xiuxian_world_boss_damages",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("instance_id", Integer, nullable=False),
            Column("tg", BigInteger, nullable=False),
            Column("total_damage", Integer, nullable=False, server_default="0"),
            Column("attack_count", Integer, nullable=False, server_default="0"),
            Column("last_attack_at", DateTime, nullable=True),
            Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
            Column("updated_at", DateTime, nullable=False, server_default=op.f("now()")),
        )
        op.create_unique_constraint("uq_world_boss_dmg_instance_tg", "xiuxian_world_boss_damages", ["instance_id", "tg"])


def downgrade() -> None:
    for table in ("xiuxian_world_boss_damages", "xiuxian_world_boss_instances", "xiuxian_boss_defeats", "xiuxian_boss_config"):
        if _has_table(table):
            op.drop_table(table)
