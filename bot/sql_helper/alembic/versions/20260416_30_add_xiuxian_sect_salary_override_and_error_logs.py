"""add xiuxian sect salary stay override and error logs

Revision ID: 20260416_30
Revises: 20260415_29
Create Date: 2026-04-16 11:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260416_30"
down_revision = "20260415_29"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column.get("name") == column_name for column in _inspector().get_columns(table_name))


def upgrade() -> None:
    if _has_table("xiuxian_sects") and not _has_column("xiuxian_sects", "salary_min_stay_days"):
        with op.batch_alter_table("xiuxian_sects") as batch_op:
            batch_op.add_column(sa.Column("salary_min_stay_days", sa.Integer(), nullable=False, server_default="30"))

        sects = sa.table(
            "xiuxian_sects",
            sa.column("salary_min_stay_days", sa.Integer()),
        )
        op.get_bind().execute(
            sects.update()
            .where(sects.c.salary_min_stay_days.is_(None))
            .values(salary_min_stay_days=30)
        )

    if not _has_table("xiuxian_error_logs"):
        op.create_table(
            "xiuxian_error_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tg", sa.BigInteger(), nullable=True),
            sa.Column("username", sa.String(length=64), nullable=True),
            sa.Column("display_name", sa.String(length=128), nullable=True),
            sa.Column("scope", sa.String(length=32), nullable=False, server_default="user"),
            sa.Column("level", sa.String(length=16), nullable=False, server_default="ERROR"),
            sa.Column("operation", sa.String(length=128), nullable=True),
            sa.Column("method", sa.String(length=16), nullable=True),
            sa.Column("path", sa.String(length=255), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _has_table("xiuxian_error_logs"):
        op.drop_table("xiuxian_error_logs")

    if _has_table("xiuxian_sects") and _has_column("xiuxian_sects", "salary_min_stay_days"):
        with op.batch_alter_table("xiuxian_sects") as batch_op:
            batch_op.drop_column("salary_min_stay_days")
