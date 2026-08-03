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
    if not _has_table(connection, "doupo_profiles"):
        return
    columns = _column_names(connection, "doupo_profiles")
    specs = {
        "method_level": "INTEGER NOT NULL DEFAULT 0",
        "fire_rank": "INTEGER NOT NULL DEFAULT 0",
        "academy_fire_energy": "INTEGER NOT NULL DEFAULT 0",
        "faction_reputation": "INTEGER NOT NULL DEFAULT 0",
        "black_corner_infamy": "INTEGER NOT NULL DEFAULT 0",
        "pet_key": "VARCHAR(64)",
        "pet_level": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, ddl in specs.items():
        if name not in columns:
            connection.execute(sa.text(f"ALTER TABLE doupo_profiles ADD COLUMN {name} {ddl}"))


def downgrade(connection) -> None:
    return None
