from __future__ import annotations

import sqlalchemy as sa


def _column_names(connection, table_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(item["name"]) for item in inspector.get_columns(table_name)}


def upgrade(connection) -> None:
    columns = _column_names(connection, "doupo_profiles")
    if columns and "breakthrough_failures" not in columns:
        connection.execute(
            sa.text(
                "ALTER TABLE doupo_profiles "
                "ADD COLUMN breakthrough_failures INTEGER NOT NULL DEFAULT 0"
            )
        )


def downgrade(connection) -> None:
    # SQLite/MySQL/PostgreSQL have different portable DROP COLUMN behavior.
    # Keeping a zero-valued compatibility column is safer for plugin rollback.
    return None
