"""add unique constraint on partition_grants(tg, partition)

Revision ID: 20260803_61a
Revises: 20260714_60a
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260803_61a"
down_revision = "20260714_60a"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "uq_partition_grants_tg_partition"
_TABLE = "partition_grants"


def _constraint_or_index_exists(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    for constraint in inspector.get_unique_constraints(table):
        if constraint.get("name") == _CONSTRAINT_NAME:
            return True
    for index in inspector.get_indexes(table):
        if index.get("name") == _CONSTRAINT_NAME:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    if _constraint_or_index_exists(bind, _TABLE):
        return

    # 建唯一约束前先去重：同一 (tg, partition) 只保留授权到期最晚的一行
    # （并发或历史缺陷可能已产生重复授权）。去重与建约束放在同一迁移内，
    # PostgreSQL 下整体在事务中执行；MySQL 下 DDL 自动提交。
    dup_groups = bind.execute(
        sa.text(
            "SELECT tg, partition FROM partition_grants "
            "GROUP BY tg, partition HAVING COUNT(*) > 1"
        )
    ).fetchall()
    for tg, partition in dup_groups:
        keep_id = bind.execute(
            sa.text(
                "SELECT id FROM partition_grants "
                "WHERE tg = :tg AND partition = :partition "
                "ORDER BY expires_at DESC, id DESC LIMIT 1"
            ),
            {"tg": tg, "partition": partition},
        ).scalar()
        bind.execute(
            sa.text(
                "DELETE FROM partition_grants "
                "WHERE tg = :tg AND partition = :partition AND id != :keep_id"
            ),
            {"tg": tg, "partition": partition, "keep_id": keep_id},
        )

    op.create_unique_constraint(_CONSTRAINT_NAME, _TABLE, ["tg", "partition"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    constraint_names = {
        c.get("name") for c in inspector.get_unique_constraints(_TABLE)
    }
    index_names = {i.get("name") for i in inspector.get_indexes(_TABLE)}
    if _CONSTRAINT_NAME in constraint_names:
        # PostgreSQL 等以约束形式存在
        op.execute(f'ALTER TABLE {_TABLE} DROP CONSTRAINT "{_CONSTRAINT_NAME}"')
    elif _CONSTRAINT_NAME in index_names:
        # MySQL 等以唯一索引形式存在
        op.drop_index(_CONSTRAINT_NAME, table_name=_TABLE)
