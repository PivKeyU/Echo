"""add group moderation tables

Revision ID: 20260421_41a
Revises: 20260417_40a
Create Date: 2026-04-21 14:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260421_41a"
down_revision = "20260417_40a"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in _inspector().get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("group_moderation_settings"):
        op.create_table(
            "group_moderation_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column("warn_threshold", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("warn_action", sa.String(length=16), nullable=False, server_default="mute"),
            sa.Column("mute_minutes", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("updated_by", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("chat_id", name="uq_group_moderation_settings_chat_id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )

    if not _has_table("group_moderation_warnings"):
        op.create_table(
            "group_moderation_warnings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column("tg", sa.BigInteger(), nullable=False),
            sa.Column("warn_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_reason", sa.String(length=255), nullable=True),
            sa.Column("last_warned_by", sa.BigInteger(), nullable=True),
            sa.Column("last_warned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("last_action", sa.String(length=16), nullable=True),
            sa.Column("last_action_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("chat_id", "tg", name="uq_group_moderation_warning_chat_tg"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )

    if _has_table("group_moderation_warnings") and not _has_index("group_moderation_warnings", "ix_group_moderation_warning_chat_id"):
        op.create_index("ix_group_moderation_warning_chat_id", "group_moderation_warnings", ["chat_id"], unique=False)
    if _has_table("group_moderation_warnings") and not _has_index("group_moderation_warnings", "ix_group_moderation_warning_tg"):
        op.create_index("ix_group_moderation_warning_tg", "group_moderation_warnings", ["tg"], unique=False)
    if _has_table("group_moderation_warnings") and not _has_index("group_moderation_warnings", "ix_group_moderation_warning_count"):
        op.create_index("ix_group_moderation_warning_count", "group_moderation_warnings", ["warn_count"], unique=False)


def downgrade() -> None:
    if _has_table("group_moderation_warnings"):
        if _has_index("group_moderation_warnings", "ix_group_moderation_warning_count"):
            op.drop_index("ix_group_moderation_warning_count", table_name="group_moderation_warnings")
        if _has_index("group_moderation_warnings", "ix_group_moderation_warning_tg"):
            op.drop_index("ix_group_moderation_warning_tg", table_name="group_moderation_warnings")
        if _has_index("group_moderation_warnings", "ix_group_moderation_warning_chat_id"):
            op.drop_index("ix_group_moderation_warning_chat_id", table_name="group_moderation_warnings")
        op.drop_table("group_moderation_warnings")

    if _has_table("group_moderation_settings"):
        op.drop_table("group_moderation_settings")
