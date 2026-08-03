"""add xiuxian web auth tables

Revision ID: 20260708_58a
Revises: 20260519_57a
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260708_58a"
down_revision = "20260519_57a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    if not _has_table(table):
        return False
    return index_name in {item["name"] for item in _inspector().get_indexes(table)}


def upgrade() -> None:
    if not _has_table("xiuxian_web_accounts"):
        op.create_table(
            "xiuxian_web_accounts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("tg", sa.BigInteger(), nullable=True),
            sa.Column("display_name", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("username", name="uq_xiuxian_web_accounts_username"),
            sa.UniqueConstraint("tg", name="uq_xiuxian_web_accounts_tg"),
        )
    if not _has_index("xiuxian_web_accounts", "ix_xiuxian_web_accounts_username"):
        op.create_index("ix_xiuxian_web_accounts_username", "xiuxian_web_accounts", ["username"], unique=False)
    if not _has_index("xiuxian_web_accounts", "ix_xiuxian_web_accounts_tg"):
        op.create_index("ix_xiuxian_web_accounts_tg", "xiuxian_web_accounts", ["tg"], unique=False)

    if not _has_table("xiuxian_web_sessions"):
        op.create_table(
            "xiuxian_web_sessions",
            sa.Column("token_hash", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("xiuxian_web_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
    if not _has_index("xiuxian_web_sessions", "ix_xiuxian_web_sessions_account_id"):
        op.create_index("ix_xiuxian_web_sessions_account_id", "xiuxian_web_sessions", ["account_id"], unique=False)
    if not _has_index("xiuxian_web_sessions", "ix_xiuxian_web_sessions_expires_at"):
        op.create_index("ix_xiuxian_web_sessions_expires_at", "xiuxian_web_sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    if _has_table("xiuxian_web_sessions"):
        if _has_index("xiuxian_web_sessions", "ix_xiuxian_web_sessions_expires_at"):
            op.drop_index("ix_xiuxian_web_sessions_expires_at", table_name="xiuxian_web_sessions")
        if _has_index("xiuxian_web_sessions", "ix_xiuxian_web_sessions_account_id"):
            op.drop_index("ix_xiuxian_web_sessions_account_id", table_name="xiuxian_web_sessions")
        op.drop_table("xiuxian_web_sessions")
    if _has_table("xiuxian_web_accounts"):
        if _has_index("xiuxian_web_accounts", "ix_xiuxian_web_accounts_tg"):
            op.drop_index("ix_xiuxian_web_accounts_tg", table_name="xiuxian_web_accounts")
        if _has_index("xiuxian_web_accounts", "ix_xiuxian_web_accounts_username"):
            op.drop_index("ix_xiuxian_web_accounts_username", table_name="xiuxian_web_accounts")
        op.drop_table("xiuxian_web_accounts")
