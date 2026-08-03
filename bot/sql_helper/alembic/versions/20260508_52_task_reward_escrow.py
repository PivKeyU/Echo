"""add task reward escrow flag

Revision ID: 20260508_52a
Revises: 20260504_51a
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_52a"
down_revision = "20260504_51a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {item["name"] for item in _inspector().get_columns(table)}


def upgrade() -> None:
    if not _has_table("xiuxian_tasks") or _has_column("xiuxian_tasks", "reward_item_escrowed"):
        return
    with op.batch_alter_table("xiuxian_tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reward_item_escrowed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("xiuxian_tasks") as batch_op:
        batch_op.alter_column("reward_item_escrowed", server_default=None)


def downgrade() -> None:
    if not _has_column("xiuxian_tasks", "reward_item_escrowed"):
        return
    with op.batch_alter_table("xiuxian_tasks") as batch_op:
        batch_op.drop_column("reward_item_escrowed")
