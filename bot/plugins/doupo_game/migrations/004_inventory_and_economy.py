from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, MetaData, String, Table, UniqueConstraint


def _has_table(connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def _create_table_if_missing(connection, table: Table) -> None:
    if _has_table(connection, table.name):
        return
    table.create(bind=connection)


def _index_or_constraint_names(connection, table_name: str) -> set[str]:
    if not _has_table(connection, table_name):
        return set()
    inspector = sa.inspect(connection)
    names = {item["name"] for item in inspector.get_indexes(table_name) if item.get("name")}
    names.update(item["name"] for item in inspector.get_unique_constraints(table_name) if item.get("name"))
    return names


def upgrade(connection) -> None:
    metadata = MetaData()

    inventory = Table(
        "doupo_inventory_items",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("item_key", String(64), nullable=False),
        Column("category", String(32), nullable=False),
        Column("name", String(128), nullable=False),
        Column("rarity", String(32), nullable=True),
        Column("quantity", Integer, nullable=False, server_default="0"),
        Column("item_meta", JSON, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "item_key", name="uq_doupo_inventory_tg_item"),
    )

    economy = Table(
        "doupo_economy_ledgers",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("day_key", String(16), nullable=False),
        Column("gold_income", Integer, nullable=False, server_default="0"),
        Column("gold_sink", Integer, nullable=False, server_default="0"),
        Column("action_count", Integer, nullable=False, server_default="0"),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "day_key", name="uq_doupo_economy_tg_day"),
    )

    _create_table_if_missing(connection, inventory)
    _create_table_if_missing(connection, economy)

    existing_names = _index_or_constraint_names(connection, "doupo_inventory_items")
    if "ix_doupo_inventory_tg_category" not in existing_names:
        sa.Index("ix_doupo_inventory_tg_category", inventory.c.tg, inventory.c.category).create(bind=connection)
    if "ix_doupo_inventory_updated" not in existing_names:
        sa.Index("ix_doupo_inventory_updated", inventory.c.updated_at).create(bind=connection)

    existing_names = _index_or_constraint_names(connection, "doupo_economy_ledgers")
    if "ix_doupo_economy_day" not in existing_names:
        sa.Index("ix_doupo_economy_day", economy.c.day_key).create(bind=connection)


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    for table_name in ("doupo_economy_ledgers", "doupo_inventory_items"):
        table = metadata.tables.get(table_name)
        if table is not None:
            table.drop(bind=connection)
