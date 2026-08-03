from __future__ import annotations

from datetime import datetime
from typing import Any
from threading import RLock

_MIGRATION_DB_LOCK = RLock()

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint

from bot.sql_helper import Base, Session


def utcnow() -> datetime:
    return datetime.utcnow()


class PluginInstallation(Base):
    __tablename__ = "plugin_installations"

    plugin_id = Column(String(96), primary_key=True, nullable=False)
    name = Column(String(128), nullable=False)
    version = Column(String(64), nullable=False, default="0.0.0")
    install_scope = Column(String(16), nullable=False, default="runtime")
    plugin_type = Column(String(16), nullable=False, default="runtime")
    install_path = Column(String(512), nullable=False)
    source_filename = Column(String(255), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    requires_restart = Column(Boolean, nullable=False, default=False)
    requires_container_rebuild = Column(Boolean, nullable=False, default=False)
    permissions = Column(JSON, nullable=False, default=list)
    python_dependencies = Column(JSON, nullable=False, default=list)
    manifest = Column(JSON, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    installed_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow)
    last_loaded_at = Column(DateTime, nullable=True)


class PluginMigrationRecord(Base):
    __tablename__ = "plugin_migration_records"
    __table_args__ = (
        UniqueConstraint("plugin_id", "migration_name", name="uq_plugin_migration_plugin_name"),
        Index("ix_plugin_migration_plugin_id", "plugin_id"),
        Index("ix_plugin_migration_applied_at", "applied_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    plugin_id = Column(String(96), nullable=False)
    migration_name = Column(String(255), nullable=False)
    checksum = Column(String(96), nullable=False)
    applied_at = Column(DateTime, nullable=False, default=utcnow)


def upsert_plugin_installation(
    plugin_id: str,
    *,
    name: str,
    version: str,
    install_scope: str,
    plugin_type: str,
    install_path: str,
    enabled: bool,
    requires_restart: bool,
    requires_container_rebuild: bool,
    permissions: list[str],
    python_dependencies: list[str],
    manifest: dict[str, Any],
    source_filename: str | None = None,
    last_error: str | None = None,
) -> None:
    with Session() as session:
        row = session.get(PluginInstallation, plugin_id)
        if row is None:
            row = PluginInstallation(plugin_id=plugin_id)
            row.installed_at = utcnow()
            session.add(row)

        row.name = name
        row.version = version
        row.install_scope = install_scope
        row.plugin_type = plugin_type
        row.install_path = install_path
        row.source_filename = source_filename
        row.enabled = bool(enabled)
        row.requires_restart = bool(requires_restart)
        row.requires_container_rebuild = bool(requires_container_rebuild)
        row.permissions = list(permissions or [])
        row.python_dependencies = list(python_dependencies or [])
        row.manifest = dict(manifest or {})
        row.last_error = last_error
        row.updated_at = utcnow()
        session.commit()


def mark_plugin_loaded(plugin_id: str) -> None:
    with Session() as session:
        row = session.get(PluginInstallation, plugin_id)
        if row is None:
            return
        row.last_loaded_at = utcnow()
        row.last_error = None
        row.updated_at = utcnow()
        session.commit()


def mark_plugin_error(plugin_id: str, error: str | None) -> None:
    with Session() as session:
        row = session.get(PluginInstallation, plugin_id)
        if row is None:
            return
        row.last_error = error
        row.updated_at = utcnow()
        session.commit()


def list_applied_plugin_migrations(plugin_id: str) -> dict[str, str]:
    with _MIGRATION_DB_LOCK, Session() as session:
        rows = (
            session.query(PluginMigrationRecord)
            .filter(PluginMigrationRecord.plugin_id == plugin_id)
            .order_by(PluginMigrationRecord.id.asc())
            .all()
        )
        return {row.migration_name: row.checksum for row in rows}


def update_plugin_migration_checksum(plugin_id: str, migration_name: str, checksum: str) -> bool:
    with _MIGRATION_DB_LOCK, Session() as session:
        row = (
            session.query(PluginMigrationRecord)
            .filter(
                PluginMigrationRecord.plugin_id == str(plugin_id),
                PluginMigrationRecord.migration_name == str(migration_name),
            )
            .with_for_update()
            .first()
        )
        if row is None:
            return False
        row.checksum = str(checksum)
        session.commit()
        return True
