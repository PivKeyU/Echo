"""斗罗后续作品玩法字段:血脉(龙王传说/终极斗罗)、魂导师(绝世唐门)。

仅扩展 douluo_profiles,新增列全部带默认值,老玩家无需回填。
"""

from __future__ import annotations

import sqlalchemy as sa


def _has_table(connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def _column_names(connection, table_name: str) -> set[str]:
    if not _has_table(connection, table_name):
        return set()
    inspector = sa.inspect(connection)
    return {item["name"] for item in inspector.get_columns(table_name)}


def upgrade(connection) -> None:
    if not _has_table(connection, "douluo_profiles"):
        return

    columns = _column_names(connection, "douluo_profiles")
    specs = {
        "bloodline_key": "VARCHAR(64)",
        "bloodline_level": "INTEGER NOT NULL DEFAULT 0",
        "bloodline_at": "TIMESTAMP NULL",
        "craftsman_rank": "INTEGER NOT NULL DEFAULT 1",
        "craftsman_exp": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, ddl in specs.items():
        if name not in columns:
            connection.execute(sa.text(f"ALTER TABLE douluo_profiles ADD COLUMN {name} {ddl}"))


def downgrade(connection) -> None:
    # 保留玩家成长数据,不回滚列。
    return None
