"""新增魂环来源字段,记录魂环出自的知名魂兽(斗罗全系列内容扩充)。

仅扩展 douluo_soul_rings,新增列可空,老魂环无需回填。
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
    if not _has_table(connection, "douluo_soul_rings"):
        return
    columns = _column_names(connection, "douluo_soul_rings")
    if "source_name" not in columns:
        connection.execute(sa.text("ALTER TABLE douluo_soul_rings ADD COLUMN source_name VARCHAR(64) NULL"))


def downgrade(connection) -> None:
    # 保留玩家成长数据,不回滚列。
    return None
