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
        "sect_name": "VARCHAR(64)",
        "sect_contribution": "INTEGER NOT NULL DEFAULT 0",
        "pill_stock": "INTEGER NOT NULL DEFAULT 0",
        "technique_key": "VARCHAR(64)",
        "technique_level": "INTEGER NOT NULL DEFAULT 0",
        "fire_name": "VARCHAR(64)",
        "fire_progress": "INTEGER NOT NULL DEFAULT 0",
        "boss_score": "INTEGER NOT NULL DEFAULT 0",
        "tower_floor": "INTEGER NOT NULL DEFAULT 0",
        "auction_credit": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, ddl in specs.items():
        if name not in columns:
            connection.execute(sa.text(f"ALTER TABLE doupo_profiles ADD COLUMN {name} {ddl}"))


def downgrade(connection) -> None:
    # Keep player progression data on downgrade.
    return None
