from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, JSON, MetaData, String, Table, Text, UniqueConstraint


def _has_table(connection, table_name: str) -> bool:
    return table_name in sa.inspect(connection).get_table_names()


def _column_names(connection, table_name: str) -> set[str]:
    if not _has_table(connection, table_name):
        return set()
    return {str(item["name"]) for item in sa.inspect(connection).get_columns(table_name)}


def _index_or_constraint_names(connection, table_name: str) -> set[str]:
    if not _has_table(connection, table_name):
        return set()
    inspector = sa.inspect(connection)
    names = {str(item["name"]) for item in inspector.get_indexes(table_name) if item.get("name")}
    names.update(str(item["name"]) for item in inspector.get_unique_constraints(table_name) if item.get("name"))
    return names


def upgrade(connection) -> None:
    metadata = MetaData()
    definitions = Table(
        "doupo_item_definitions",
        metadata,
        Column("item_key", String(64), primary_key=True),
        Column("name", String(128), nullable=False),
        Column("category", String(32), nullable=False),
        Column("rarity", String(32), nullable=False),
        Column("description", Text, nullable=True),
        Column("icon", String(512), nullable=True),
        Column("tradable", Boolean, nullable=False),
        Column("stack_limit", Integer, nullable=False),
        Column("equipment_slot", String(32), nullable=True),
        Column("attack", Integer, nullable=False),
        Column("defense", Integer, nullable=False),
        Column("agility", Integer, nullable=False),
        Column("fire_bonus", Integer, nullable=False),
        Column("alchemy_bonus", Integer, nullable=False),
        Column("recipe_config", JSON, nullable=True),
        Column("drop_sources", JSON, nullable=True),
        Column("version", Integer, nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("is_builtin", Boolean, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )
    versions = Table(
        "doupo_item_definition_versions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("item_key", String(64), nullable=False),
        Column("version", Integer, nullable=False),
        Column("snapshot", JSON, nullable=False),
        Column("change_note", String(255), nullable=True),
        Column("created_by", BigInteger, nullable=True),
        Column("created_at", DateTime, nullable=False),
        UniqueConstraint("item_key", "version", name="uq_doupo_item_version"),
    )
    if not _has_table(connection, definitions.name):
        definitions.create(bind=connection)
    if not _has_table(connection, versions.name):
        versions.create(bind=connection)

    if _has_table(connection, "doupo_inventory_items") and "equipped_slot" not in _column_names(connection, "doupo_inventory_items"):
        connection.execute(sa.text("ALTER TABLE doupo_inventory_items ADD COLUMN equipped_slot VARCHAR(32) NULL"))

    definition_names = _index_or_constraint_names(connection, definitions.name)
    if "ix_doupo_item_definitions_category" not in definition_names:
        sa.Index("ix_doupo_item_definitions_category", definitions.c.category, definitions.c.enabled).create(bind=connection)
    if "ix_doupo_item_definitions_updated" not in definition_names:
        sa.Index("ix_doupo_item_definitions_updated", definitions.c.updated_at).create(bind=connection)

    version_names = _index_or_constraint_names(connection, versions.name)
    if "uq_doupo_item_version" not in version_names:
        try:
            sa.Index("uq_doupo_item_version", versions.c.item_key, versions.c.version, unique=True).create(bind=connection)
        except Exception:
            pass
    if "ix_doupo_item_versions_key_created" not in version_names:
        sa.Index("ix_doupo_item_versions_key_created", versions.c.item_key, versions.c.created_at).create(bind=connection)

    inventory = Table("doupo_inventory_items", metadata, autoload_with=connection)
    inventory_names = _index_or_constraint_names(connection, inventory.name)
    if "ix_doupo_inventory_tg_equipped" not in inventory_names:
        sa.Index("ix_doupo_inventory_tg_equipped", inventory.c.tg, inventory.c.equipped_slot).create(bind=connection)


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    for table_name in ("doupo_item_definition_versions", "doupo_item_definitions"):
        table = metadata.tables.get(table_name)
        if table is not None:
            table.drop(bind=connection)
    # equipped_slot is intentionally retained for cross-database rollback compatibility.
