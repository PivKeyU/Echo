"""init schema

Revision ID: 20260315_01
Revises:
Create Date: 2026-03-15 12:00:00
"""

from alembic import op
import sqlalchemy as sa

from bot.sql_helper.sql_code import Code
from bot.sql_helper.sql_emby import Emby
from bot.sql_helper.sql_emby2 import Emby2
from bot.sql_helper.sql_partition import PartitionCode, PartitionGrant
from bot.sql_helper.sql_request_record import RequestRecord


revision = "20260315_01"
down_revision = None
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    for table in (
        Emby.__table__,
        Emby2.__table__,
        Code.__table__,
        RequestRecord.__table__,
        PartitionCode.__table__,
        PartitionGrant.__table__,
    ):
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    table_names = _table_names(bind)

    for table_name in (
        "partition_grants",
        "partition_codes",
        "emby_favorites",
        "request_records",
        "Rcode",
        "emby2",
        "emby",
    ):
        if table_name in table_names:
            op.drop_table(table_name)
