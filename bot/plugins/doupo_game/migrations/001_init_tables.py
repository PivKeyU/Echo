from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, MetaData, String, Table, Text, BigInteger


def _has_table(connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def _create_table_if_missing(connection, table: Table) -> None:
    if _has_table(connection, table.name):
        return
    table.create(bind=connection)


def upgrade(connection) -> None:
    metadata = MetaData()

    doupo_settings = Table(
        "doupo_settings",
        metadata,
        Column("setting_key", String(64), primary_key=True),
        Column("setting_value", JSON, nullable=True),
        Column("updated_at", DateTime, nullable=False),
    )

    doupo_profiles = Table(
        "doupo_profiles",
        metadata,
        Column("tg", BigInteger, primary_key=True, autoincrement=False),
        Column("display_name", String(128), nullable=True),
        Column("username", String(64), nullable=True),
        Column("realm_stage", String(32), nullable=False),
        Column("realm_stars", Integer, nullable=False),
        Column("douqi", Integer, nullable=False),
        Column("gold", Integer, nullable=False),
        Column("last_train_at", DateTime, nullable=True),
        Column("last_breakthrough_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )

    doupo_actions = Table(
        "doupo_actions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("action_key", String(64), nullable=False),
        Column("name", String(64), nullable=False),
        Column("description", String(255), nullable=True),
        Column("action_type", String(32), nullable=False),
        Column("cooldown_seconds", Integer, nullable=False),
        Column("reward_config", JSON, nullable=True),
        Column("requirement_config", JSON, nullable=True),
        Column("enabled", Boolean, nullable=False),
        Column("sort_order", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )

    doupo_journals = Table(
        "doupo_journals",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("action_type", String(32), nullable=False),
        Column("title", String(128), nullable=False),
        Column("detail", Text, nullable=True),
        Column("created_at", DateTime, nullable=False),
    )

    _create_table_if_missing(connection, doupo_settings)
    _create_table_if_missing(connection, doupo_profiles)
    _create_table_if_missing(connection, doupo_actions)
    _create_table_if_missing(connection, doupo_journals)

    inspector = sa.inspect(connection)
    existing_indexes = {item["name"] for item in inspector.get_indexes("doupo_profiles")} if _has_table(connection, "doupo_profiles") else set()
    if "ix_doupo_profiles_realm" not in existing_indexes:
        sa.Index("ix_doupo_profiles_realm", doupo_profiles.c.realm_stage, doupo_profiles.c.realm_stars).create(bind=connection)
    if "ix_doupo_profiles_updated" not in existing_indexes:
        sa.Index("ix_doupo_profiles_updated", doupo_profiles.c.updated_at).create(bind=connection)

    existing_indexes = {item["name"] for item in inspector.get_indexes("doupo_actions")} if _has_table(connection, "doupo_actions") else set()
    if "ix_doupo_actions_enabled_order" not in existing_indexes:
        sa.Index("ix_doupo_actions_enabled_order", doupo_actions.c.enabled, doupo_actions.c.sort_order).create(bind=connection)

    existing_indexes = {item["name"] for item in inspector.get_indexes("doupo_journals")} if _has_table(connection, "doupo_journals") else set()
    if "ix_doupo_journals_tg_created" not in existing_indexes:
        sa.Index("ix_doupo_journals_tg_created", doupo_journals.c.tg, doupo_journals.c.created_at).create(bind=connection)
    if "ix_doupo_journals_action" not in existing_indexes:
        sa.Index("ix_doupo_journals_action", doupo_journals.c.action_type, doupo_journals.c.created_at).create(bind=connection)


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    for table_name in ("doupo_journals", "doupo_actions", "doupo_profiles", "doupo_settings"):
        table = metadata.tables.get(table_name)
        if table is not None:
            table.drop(bind=connection)
