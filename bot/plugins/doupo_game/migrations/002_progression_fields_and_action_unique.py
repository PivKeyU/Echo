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


def _index_or_constraint_names(connection, table_name: str) -> set[str]:
    if not _has_table(connection, table_name):
        return set()
    inspector = sa.inspect(connection)
    names = {item["name"] for item in inspector.get_indexes(table_name) if item.get("name")}
    names.update(item["name"] for item in inspector.get_unique_constraints(table_name) if item.get("name"))
    return names


def upgrade(connection) -> None:
    if _has_table(connection, "doupo_profiles"):
        columns = _column_names(connection, "doupo_profiles")
        for name in ("fire_seed", "alchemy_exp", "beast_core"):
            if name not in columns:
                connection.execute(sa.text(f"ALTER TABLE doupo_profiles ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"))

    if not _has_table(connection, "doupo_actions"):
        return

    duplicate_rows = connection.execute(
        sa.text(
            """
            SELECT action_key, MIN(id) AS keep_id
            FROM doupo_actions
            GROUP BY action_key
            HAVING COUNT(*) > 1
            """
        )
    ).mappings()
    for row in duplicate_rows:
        connection.execute(
            sa.text("DELETE FROM doupo_actions WHERE action_key = :action_key AND id <> :keep_id"),
            {"action_key": row["action_key"], "keep_id": row["keep_id"]},
        )

    existing_names = _index_or_constraint_names(connection, "doupo_actions")
    if "uq_doupo_action_key" not in existing_names:
        metadata = sa.MetaData()
        table = sa.Table("doupo_actions", metadata, sa.Column("action_key", sa.String(64)))
        sa.Index("uq_doupo_action_key", table.c.action_key, unique=True).create(bind=connection)


def downgrade(connection) -> None:
    if not _has_table(connection, "doupo_actions"):
        return
    existing_names = _index_or_constraint_names(connection, "doupo_actions")
    if "uq_doupo_action_key" in existing_names:
        metadata = sa.MetaData()
        table = sa.Table("doupo_actions", metadata, sa.Column("action_key", sa.String(64)))
        sa.Index("uq_doupo_action_key", table.c.action_key, unique=True).drop(bind=connection)
