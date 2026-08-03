from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, MetaData, String, Table


def _has_table(connection, table_name: str) -> bool:
    return table_name in sa.inspect(connection).get_table_names()


def upgrade(connection) -> None:
    if _has_table(connection, "doupo_expeditions"):
        return
    metadata = MetaData()
    table = Table(
        "doupo_expeditions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tg", BigInteger, nullable=False),
        Column("region_key", String(64), nullable=False),
        Column("status", String(24), nullable=False, server_default="active"),
        Column("step", Integer, nullable=False, server_default="0"),
        Column("max_steps", Integer, nullable=False, server_default="4"),
        Column("vitality", Integer, nullable=False, server_default="100"),
        Column("max_vitality", Integer, nullable=False, server_default="100"),
        Column("danger", Integer, nullable=False, server_default="0"),
        Column("loot", JSON, nullable=True),
        Column("current_event_key", String(64), nullable=True),
        Column("history", JSON, nullable=True),
        Column("settlement", JSON, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
        Column("completed_at", DateTime, nullable=True),
    )
    table.create(bind=connection)
    sa.Index("ix_doupo_expeditions_tg_status", table.c.tg, table.c.status).create(bind=connection)
    sa.Index("ix_doupo_expeditions_updated", table.c.updated_at).create(bind=connection)


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    table = metadata.tables.get("doupo_expeditions")
    if table is not None:
        table.drop(bind=connection)
