from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)


def _has_table(connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def _create_table_if_missing(connection, table: Table) -> None:
    if _has_table(connection, table.name):
        return
    table.create(bind=connection)


def _ensure_indexes(connection, table_name: str, definitions: list[tuple[str, Table, list[str]]]) -> None:
    inspector = sa.inspect(connection)
    existing_names = (
        {str(item["name"]) for item in inspector.get_indexes(table_name) if item.get("name")}
        if _has_table(connection, table_name)
        else set()
    )
    for index_name, table, columns in definitions:
        if index_name not in existing_names:
            Index(index_name, *[table.c[column] for column in columns]).create(bind=connection)


def _ensure_unique_constraint(connection, table_name: str, constraint_name: str, columns: list[str]) -> None:
    if not _has_table(connection, table_name):
        return
    existing_names = {
        str(item["name"])
        for item in sa.inspect(connection).get_unique_constraints(table_name)
        if item.get("name")
    }
    if constraint_name in existing_names:
        return
    column_sql = ", ".join(columns)
    connection.execute(
        sa.text(f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} UNIQUE ({column_sql})")
    )


def upgrade(connection) -> None:
    metadata = MetaData()

    douluo_settings = Table(
        "douluo_settings",
        metadata,
        Column("setting_key", String(64), primary_key=True),
        Column("setting_value", JSON, nullable=True),
        Column("updated_at", DateTime, nullable=False),
    )

    douluo_profiles = Table(
        "douluo_profiles",
        metadata,
        Column("tg", BigInteger, primary_key=True, autoincrement=False),
        Column("display_name", String(128), nullable=True),
        Column("username", String(64), nullable=True),
        Column("realm_stage", String(32), nullable=False),
        Column("realm_stars", Integer, nullable=False),
        Column("soul_power", Integer, nullable=False),
        Column("coin", Integer, nullable=False),
        Column("spirit_power", Integer, nullable=False),
        Column("innate_soul_power", Integer, nullable=False),
        Column("wuhun_key", String(64), nullable=True),
        Column("wuhun_name", String(64), nullable=True),
        Column("wuhun_system", String(16), nullable=True),
        Column("wuhun_quality", String(16), nullable=True),
        Column("reforge_at", DateTime, nullable=True),
        Column("breakthrough_failures", Integer, nullable=False),
        Column("sect_key", String(64), nullable=True),
        Column("sect_contribution", Integer, nullable=False),
        Column("sect_position", String(32), nullable=True),
        Column("last_salary_at", DateTime, nullable=True),
        Column("boss_score", Integer, nullable=False),
        Column("arena_wins", Integer, nullable=False),
        Column("arena_losses", Integer, nullable=False),
        Column("total_hunts", Integer, nullable=False),
        Column("last_train_at", DateTime, nullable=True),
        Column("last_breakthrough_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )

    douluo_soul_rings = Table(
        "douluo_soul_rings",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("slot", Integer, nullable=False),
        Column("years", Integer, nullable=False),
        Column("tier", String(16), nullable=False),
        Column("color", String(16), nullable=False),
        Column("skill_name", String(64), nullable=True),
        Column("attack", Integer, nullable=False),
        Column("defense", Integer, nullable=False),
        Column("speed", Integer, nullable=False),
        Column("spirit", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "slot", name="uq_douluo_soul_ring_slot"),
    )

    douluo_inventory_items = Table(
        "douluo_inventory_items",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("item_key", String(64), nullable=False),
        Column("category", String(32), nullable=False),
        Column("name", String(128), nullable=False),
        Column("rarity", String(32), nullable=True),
        Column("quantity", Integer, nullable=False),
        Column("equipped_slot", String(32), nullable=True),
        Column("item_meta", JSON, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "item_key", name="uq_douluo_inventory_tg_item"),
    )

    douluo_item_definitions = Table(
        "douluo_item_definitions",
        metadata,
        Column("item_key", String(64), primary_key=True),
        Column("name", String(128), nullable=False),
        Column("category", String(32), nullable=False),
        Column("rarity", String(32), nullable=False),
        Column("description", Text, nullable=True),
        Column("icon", String(512), nullable=True),
        Column("equipment_slot", String(32), nullable=True),
        Column("attack", Integer, nullable=False),
        Column("defense", Integer, nullable=False),
        Column("speed", Integer, nullable=False),
        Column("spirit", Integer, nullable=False),
        Column("trigger_chance", Float, nullable=True),
        Column("skill", String(64), nullable=True),
        Column("recipe_config", JSON, nullable=True),
        Column("drop_sources", JSON, nullable=True),
        Column("version", Integer, nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("is_builtin", Boolean, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )

    douluo_daily_action_counters = Table(
        "douluo_daily_action_counters",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("day_key", String(16), nullable=False),
        Column("action_type", String(64), nullable=False),
        Column("used_count", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "day_key", "action_type", name="uq_douluo_counter"),
    )

    douluo_journals = Table(
        "douluo_journals",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("action_type", String(32), nullable=False),
        Column("title", String(128), nullable=False),
        Column("detail", Text, nullable=True),
        Column("created_at", DateTime, nullable=False),
    )

    douluo_sect_members = Table(
        "douluo_sect_members",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("sect_key", String(64), nullable=False),
        Column("position", String(32), nullable=False),
        Column("contribution", Integer, nullable=False),
        Column("total_contribution", Integer, nullable=False),
        Column("last_salary_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", name="uq_douluo_sect_member_tg"),
    )

    douluo_daily_tasks = Table(
        "douluo_daily_tasks",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("day_key", String(16), nullable=False),
        Column("task_key", String(64), nullable=False),
        Column("progress", Integer, nullable=False),
        Column("claimed", Boolean, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "day_key", "task_key", name="uq_douluo_daily_task"),
    )

    douluo_auction_listings = Table(
        "douluo_auction_listings",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("seller_tg", BigInteger, nullable=False),
        Column("item_key", String(64), nullable=False),
        Column("item_name", String(128), nullable=False),
        Column("category", String(32), nullable=False),
        Column("rarity", String(32), nullable=True),
        Column("start_price", Integer, nullable=False),
        Column("current_bid", Integer, nullable=False),
        Column("bidder_tg", BigInteger, nullable=True),
        Column("bidder_display", String(128), nullable=True),
        Column("fee_paid", Integer, nullable=False),
        Column("ends_at", DateTime, nullable=False),
        Column("status", String(16), nullable=False),
        Column("bids", JSON, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )

    douluo_boss_records = Table(
        "douluo_boss_records",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("boss_key", String(64), nullable=False),
        Column("boss_name", String(64), nullable=False),
        Column("times", Integer, nullable=False),
        Column("wins", Integer, nullable=False),
        Column("best_score", Integer, nullable=False),
        Column("last_result", String(16), nullable=True),
        Column("last_fought_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "boss_key", name="uq_douluo_boss_record"),
    )

    for table in (
        douluo_settings,
        douluo_profiles,
        douluo_soul_rings,
        douluo_inventory_items,
        douluo_item_definitions,
        douluo_daily_action_counters,
        douluo_journals,
        douluo_sect_members,
        douluo_daily_tasks,
        douluo_auction_listings,
        douluo_boss_records,
    ):
        _create_table_if_missing(connection, table)

    _ensure_indexes(
        connection,
        "douluo_profiles",
        [
            ("ix_douluo_profiles_realm", douluo_profiles, ["realm_stage", "realm_stars"]),
            ("ix_douluo_profiles_updated", douluo_profiles, ["updated_at"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_soul_rings",
        [
            ("ix_douluo_soul_rings_tg", douluo_soul_rings, ["tg"]),
            ("ix_douluo_soul_rings_tg_years", douluo_soul_rings, ["tg", "years"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_inventory_items",
        [
            ("ix_douluo_inventory_tg_category", douluo_inventory_items, ["tg", "category"]),
            ("ix_douluo_inventory_tg_equipped", douluo_inventory_items, ["tg", "equipped_slot"]),
            ("ix_douluo_inventory_updated", douluo_inventory_items, ["updated_at"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_item_definitions",
        [
            ("ix_douluo_item_definitions_category", douluo_item_definitions, ["category", "enabled"]),
            ("ix_douluo_item_definitions_updated", douluo_item_definitions, ["updated_at"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_daily_action_counters",
        [
            ("ix_douluo_counters_tg_day", douluo_daily_action_counters, ["tg", "day_key"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_journals",
        [
            ("ix_douluo_journals_tg_created", douluo_journals, ["tg", "created_at"]),
            ("ix_douluo_journals_action", douluo_journals, ["action_type", "created_at"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_sect_members",
        [
            ("ix_douluo_sect_members_sect", douluo_sect_members, ["sect_key", "contribution"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_daily_tasks",
        [
            ("ix_douluo_daily_tasks_tg_day", douluo_daily_tasks, ["tg", "day_key"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_auction_listings",
        [
            ("ix_douluo_auctions_seller", douluo_auction_listings, ["seller_tg", "status"]),
            ("ix_douluo_auctions_status_ends", douluo_auction_listings, ["status", "ends_at"]),
        ],
    )
    _ensure_indexes(
        connection,
        "douluo_boss_records",
        [
            ("ix_douluo_boss_records_tg", douluo_boss_records, ["tg"]),
            ("ix_douluo_boss_records_boss", douluo_boss_records, ["boss_key"]),
        ],
    )

    # 新表建表时已携带约束；这些检查用于修复旧的部分迁移状态，失败时必须中止迁移。
    _ensure_unique_constraint(connection, "douluo_soul_rings", "uq_douluo_soul_ring_slot", ["tg", "slot"])
    _ensure_unique_constraint(connection, "douluo_inventory_items", "uq_douluo_inventory_tg_item", ["tg", "item_key"])
    _ensure_unique_constraint(
        connection,
        "douluo_daily_action_counters",
        "uq_douluo_counter",
        ["tg", "day_key", "action_type"],
    )
    _ensure_unique_constraint(connection, "douluo_sect_members", "uq_douluo_sect_member_tg", ["tg"])
    _ensure_unique_constraint(connection, "douluo_daily_tasks", "uq_douluo_daily_task", ["tg", "day_key", "task_key"])
    _ensure_unique_constraint(connection, "douluo_boss_records", "uq_douluo_boss_record", ["tg", "boss_key"])


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    for table_name in (
        "douluo_boss_records",
        "douluo_auction_listings",
        "douluo_daily_tasks",
        "douluo_sect_members",
        "douluo_journals",
        "douluo_daily_action_counters",
        "douluo_item_definitions",
        "douluo_inventory_items",
        "douluo_soul_rings",
        "douluo_profiles",
        "douluo_settings",
    ):
        table = metadata.tables.get(table_name)
        if table is not None:
            table.drop(bind=connection)
