"""add redeem history table for codes

Revision ID: 20260329_04
Revises: 20260329_03
Create Date: 2026-03-29 18:20:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = "20260329_04"
down_revision = "20260329_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "RcodeRedeem" not in table_names:
        op.create_table(
            "RcodeRedeem",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("owner_tg", sa.BigInteger(), nullable=True),
            sa.Column("code_days", sa.Integer(), nullable=True),
            sa.Column("use_index", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("redeemed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["code"], ["Rcode.code"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", "user_id", name="uq_rcode_redeem_code_user"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("ix_rcode_redeem_user_id", "RcodeRedeem", ["user_id"], unique=False)
        op.create_index("ix_rcode_redeem_redeemed_at", "RcodeRedeem", ["redeemed_at"], unique=False)

    code_table = sa.table(
        "Rcode",
        sa.column("code", sa.String(length=50)),
        sa.column("tg", sa.BigInteger()),
        sa.column("us", sa.Integer()),
        sa.column("used", sa.BigInteger()),
        sa.column("usedtime", sa.DateTime()),
        sa.column("use_count", sa.Integer()),
    )
    redeem_table = sa.table(
        "RcodeRedeem",
        sa.column("code", sa.String(length=50)),
        sa.column("user_id", sa.BigInteger()),
        sa.column("owner_tg", sa.BigInteger()),
        sa.column("code_days", sa.Integer()),
        sa.column("use_index", sa.Integer()),
        sa.column("redeemed_at", sa.DateTime()),
    )
    code_rows = bind.execute(
        sa.select(
            code_table.c.code,
            code_table.c.used,
            code_table.c.tg,
            code_table.c.us,
            code_table.c.use_count,
            code_table.c.usedtime,
        ).where(code_table.c.used.is_not(None))
    ).all()
    if code_rows:
        existing_pairs = {
            (row[0], row[1])
            for row in bind.execute(sa.select(redeem_table.c.code, redeem_table.c.user_id))
        }
        rows_to_insert = []
        for code, used, owner_tg, code_days, use_count, usedtime in code_rows:
            pair = (code, used)
            if pair in existing_pairs:
                continue
            rows_to_insert.append(
                {
                    "code": code,
                    "user_id": used,
                    "owner_tg": owner_tg,
                    "code_days": code_days,
                    "use_index": max(int(use_count or 1), 1),
                    "redeemed_at": usedtime or datetime.utcnow(),
                }
            )
        if rows_to_insert:
            bind.execute(redeem_table.insert(), rows_to_insert)

    op.alter_column("RcodeRedeem", "use_index", server_default=None)
    op.alter_column("RcodeRedeem", "redeemed_at", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "RcodeRedeem" in table_names:
        op.drop_index("ix_rcode_redeem_redeemed_at", table_name="RcodeRedeem")
        op.drop_index("ix_rcode_redeem_user_id", table_name="RcodeRedeem")
        op.drop_table("RcodeRedeem")
