"""add xiuxian journal commission lookup index

Revision ID: 20260508_54a
Revises: 20260508_53a
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_54a"
down_revision = "20260508_53a"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_xiuxian_journals_tg_action_title_created_id"
TABLE_NAME = "xiuxian_journals"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    if not _has_table(table):
        return False
    return index_name in {item["name"] for item in _inspector().get_indexes(table)}


def upgrade() -> None:
    if not _has_table(TABLE_NAME) or _has_index(TABLE_NAME, INDEX_NAME):
        return
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["tg", "action_type", "title", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    if not _has_index(TABLE_NAME, INDEX_NAME):
        return
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
