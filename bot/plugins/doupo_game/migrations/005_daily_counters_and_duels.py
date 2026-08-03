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

    counters = Table(
        "doupo_daily_action_counters",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("day_key", String(16), nullable=False),
        Column("action_type", String(32), nullable=False),
        Column("used_count", Integer, nullable=False, server_default="0"),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        UniqueConstraint("tg", "day_key", "action_type", name="uq_doupo_daily_counter_tg_day_type"),
    )

    duels = Table(
        "doupo_duel_histories",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("challenger_tg", BigInteger, nullable=False),
        Column("defender_tg", BigInteger, nullable=False),
        Column("winner_tg", BigInteger, nullable=False),
        Column("loser_tg", BigInteger, nullable=False),
        Column("stake_gold", Integer, nullable=False, server_default="0"),
        Column("challenger_power", Integer, nullable=False, server_default="0"),
        Column("defender_power", Integer, nullable=False, server_default="0"),
        Column("challenger_win_rate", Integer, nullable=False, server_default="50"),
        Column("roll", Integer, nullable=False, server_default="0"),
        Column("battle_log", JSON, nullable=True),
        Column("created_at", DateTime, nullable=False),
    )

    _create_table_if_missing(connection, counters)
    _create_table_if_missing(connection, duels)

    existing_names = _index_or_constraint_names(connection, "doupo_daily_action_counters")
    if "ix_doupo_daily_counter_tg_day" not in existing_names:
        sa.Index("ix_doupo_daily_counter_tg_day", counters.c.tg, counters.c.day_key).create(bind=connection)

    existing_names = _index_or_constraint_names(connection, "doupo_duel_histories")
    if "ix_doupo_duel_challenger" not in existing_names:
        sa.Index("ix_doupo_duel_challenger", duels.c.challenger_tg, duels.c.created_at).create(bind=connection)
    if "ix_doupo_duel_defender" not in existing_names:
        sa.Index("ix_doupo_duel_defender", duels.c.defender_tg, duels.c.created_at).create(bind=connection)
    if "ix_doupo_duel_winner" not in existing_names:
        sa.Index("ix_doupo_duel_winner", duels.c.winner_tg, duels.c.created_at).create(bind=connection)


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    for table_name in ("doupo_duel_histories", "doupo_daily_action_counters"):
        table = metadata.tables.get(table_name)
        if table is not None:
            table.drop(bind=connection)
