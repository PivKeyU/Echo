"""add xiuxian artifact slots and artifact fields

Revision ID: 20260330_08
Revises: 20260329_07
Create Date: 2026-03-30 11:30:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = "20260330_08"
down_revision = "20260329_07"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    table_names = _table_names()

    if "xiuxian_artifacts" in table_names:
        columns = _column_names("xiuxian_artifacts")
        if "defense_bonus" not in columns:
            op.add_column(
                "xiuxian_artifacts",
                sa.Column("defense_bonus", sa.Integer(), nullable=False, server_default="0"),
            )
            op.alter_column("xiuxian_artifacts", "defense_bonus", server_default=None)
        if "artifact_type" not in columns:
            op.add_column(
                "xiuxian_artifacts",
                sa.Column("artifact_type", sa.String(length=16), nullable=False, server_default="battle"),
            )
            op.alter_column("xiuxian_artifacts", "artifact_type", server_default=None)

    table_names = _table_names()
    if "xiuxian_equipped_artifacts" not in table_names:
        op.create_table(
            "xiuxian_equipped_artifacts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tg", sa.BigInteger(), nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=False),
            sa.Column("slot", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["artifact_id"], ["xiuxian_artifacts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tg", "slot", name="uq_xiuxian_equipped_artifact_slot"),
            sa.UniqueConstraint("tg", "artifact_id", name="uq_xiuxian_equipped_artifact_unique"),
        )
        op.alter_column("xiuxian_equipped_artifacts", "created_at", server_default=None)
        op.alter_column("xiuxian_equipped_artifacts", "updated_at", server_default=None)

    table_names = _table_names()
    if "xiuxian_equipped_artifacts" in table_names and "xiuxian_profiles" in table_names:
        bind = op.get_bind()
        profiles = sa.table(
            "xiuxian_profiles",
            sa.column("tg", sa.BigInteger()),
            sa.column("current_artifact_id", sa.Integer()),
        )
        equipped = sa.table(
            "xiuxian_equipped_artifacts",
            sa.column("tg", sa.BigInteger()),
            sa.column("artifact_id", sa.Integer()),
            sa.column("slot", sa.Integer()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
        )
        existing_pairs = {
            (row[0], row[1])
            for row in bind.execute(sa.select(equipped.c.tg, equipped.c.artifact_id))
        }
        now = datetime.utcnow()
        rows_to_insert = []
        for tg, artifact_id in bind.execute(
            sa.select(profiles.c.tg, profiles.c.current_artifact_id).where(profiles.c.current_artifact_id.is_not(None))
        ):
            pair = (tg, artifact_id)
            if pair in existing_pairs:
                continue
            rows_to_insert.append(
                {
                    "tg": tg,
                    "artifact_id": artifact_id,
                    "slot": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if rows_to_insert:
            bind.execute(equipped.insert(), rows_to_insert)

    table_names = _table_names()
    if "xiuxian_equipped_artifacts" in table_names:
        index_names = _index_names("xiuxian_equipped_artifacts")
        if "ix_xiuxian_equipped_artifact_tg" not in index_names:
            op.create_index(
                "ix_xiuxian_equipped_artifact_tg",
                "xiuxian_equipped_artifacts",
                ["tg"],
                unique=False,
            )


def downgrade() -> None:
    table_names = _table_names()

    if "xiuxian_equipped_artifacts" in table_names:
        index_names = _index_names("xiuxian_equipped_artifacts")
        if "ix_xiuxian_equipped_artifact_tg" in index_names:
            op.drop_index("ix_xiuxian_equipped_artifact_tg", table_name="xiuxian_equipped_artifacts")
        op.drop_table("xiuxian_equipped_artifacts")

    table_names = _table_names()
    if "xiuxian_artifacts" in table_names:
        columns = _column_names("xiuxian_artifacts")
        if "artifact_type" in columns:
            op.drop_column("xiuxian_artifacts", "artifact_type")
        if "defense_bonus" in columns:
            op.drop_column("xiuxian_artifacts", "defense_bonus")
