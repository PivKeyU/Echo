"""add xiuxian profile lookup indexes

Revision ID: 20260508_55a
Revises: 20260508_54a
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_55a"
down_revision = "20260508_54a"
branch_labels = None
depends_on = None


TABLE_NAME = "xiuxian_profiles"
INDEX_DEFS = [
    ("ix_xiuxian_profiles_consented", ["consented"]),
    ("ix_xiuxian_profiles_master_tg", ["master_tg"]),
    ("ix_xiuxian_profiles_sect_id", ["sect_id"]),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    if not _has_table(table):
        return False
    return index_name in {item["name"] for item in _inspector().get_indexes(table)}


def upgrade() -> None:
    if not _has_table(TABLE_NAME):
        return
    for name, columns in INDEX_DEFS:
        if _has_index(TABLE_NAME, name):
            continue
        op.create_index(name, TABLE_NAME, columns, unique=False)


def downgrade() -> None:
    for name, _ in INDEX_DEFS:
        if not _has_index(TABLE_NAME, name):
            continue
        op.drop_index(name, table_name=TABLE_NAME)
