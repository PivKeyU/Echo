"""add multi-use fields to Rcode

Revision ID: 20260329_03
Revises: 20260315_02
Create Date: 2026-03-29 14:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260329_03"
down_revision = "20260315_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("Rcode")}
    code_table = sa.table(
        "Rcode",
        sa.column("code", sa.String(length=50)),
        sa.column("used", sa.BigInteger()),
        sa.column("use_limit", sa.Integer()),
        sa.column("use_count", sa.Integer()),
    )

    if "use_limit" not in column_names:
        op.add_column(
            "Rcode",
            sa.Column("use_limit", sa.Integer(), nullable=False, server_default="1"),
        )

    if "use_count" not in column_names:
        op.add_column(
            "Rcode",
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        )

    bind.execute(
        code_table.update().values(
            use_limit=sa.func.coalesce(code_table.c.use_limit, 1),
        )
    )
    bind.execute(
        code_table.update().values(
            use_count=sa.case(
                (code_table.c.used.is_(None), sa.func.coalesce(code_table.c.use_count, 0)),
                else_=sa.func.greatest(sa.func.coalesce(code_table.c.use_count, 0), 1),
            )
        )
    )
    bind.execute(
        code_table.update()
        .where(code_table.c.use_limit < 1)
        .values(use_limit=1)
    )
    op.alter_column("Rcode", "use_limit", server_default=None)
    op.alter_column("Rcode", "use_count", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("Rcode")}

    if "use_count" in column_names:
        op.drop_column("Rcode", "use_count")

    if "use_limit" in column_names:
        op.drop_column("Rcode", "use_limit")
