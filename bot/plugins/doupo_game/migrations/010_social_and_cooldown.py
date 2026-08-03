from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, MetaData, String, Table


def _has_table(connection, table_name: str) -> bool:
    return table_name in sa.inspect(connection).get_table_names()


def _column_names(connection, table_name: str) -> set[str]:
    if not _has_table(connection, table_name):
        return set()
    return {str(item["name"]) for item in sa.inspect(connection).get_columns(table_name)}


def upgrade(connection) -> None:
    metadata = MetaData()
    profiles = Table(
        "doupo_profiles",
        metadata,
        Column("tg", sa.BigInteger, primary_key=True, autoincrement=False),
    )

    if not _has_table(connection, "doupo_profiles"):
        return

    names = _column_names(connection, "doupo_profiles")
    if "cooldown_map" not in names:
        connection.execute(sa.text("ALTER TABLE doupo_profiles ADD COLUMN cooldown_map JSON NULL"))
    if "sect_changed_at" not in names:
        connection.execute(sa.text("ALTER TABLE doupo_profiles ADD COLUMN sect_changed_at TIMESTAMP NULL"))
    if "last_sect_quest_at" not in names:
        connection.execute(sa.text("ALTER TABLE doupo_profiles ADD COLUMN last_sect_quest_at TIMESTAMP NULL"))

    # P1 老境界名回填：斗尊拆九转、斗圣拆四亚阶。精确匹配，重复执行无副作用。
    if "realm_stage" in names:
        connection.execute(
            sa.text("UPDATE doupo_profiles SET realm_stage='斗尊·一转' WHERE realm_stage='斗尊'")
        )
        connection.execute(
            sa.text("UPDATE doupo_profiles SET realm_stage='斗圣·初期' WHERE realm_stage='斗圣'")
        )


def downgrade(connection) -> None:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    if not _has_table(connection, "doupo_profiles"):
        return
    names = _column_names(connection, "doupo_profiles")
    for column in ("cooldown_map", "sect_changed_at", "last_sect_quest_at"):
        if column in names:
            # SQLite 不支持 DROP COLUMN；PostgreSQL/MySQL 支持。此处用条件尝试，兼容跨数据库回滚。
            try:
                connection.execute(sa.text(f"ALTER TABLE doupo_profiles DROP COLUMN {column}"))
            except Exception:
                pass
