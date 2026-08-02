from __future__ import annotations

import hashlib
import io
import importlib
import importlib.metadata
import json
import keyword
import inspect
import os
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import ModuleType
from threading import RLock
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = Path(__file__).resolve().parent
BUILTIN_PLUGIN_ROOT = PLUGIN_ROOT
RUNTIME_PLUGIN_ROOT = PROJECT_ROOT / "data" / "runtime_plugins"
RUNTIME_PLUGIN_BACKUP_ROOT = PROJECT_ROOT / "data" / "runtime_plugin_backups"
PLUGIN_NAMESPACE = "bot.plugins"


def _env_archive_limit(name: str, default: int, minimum: int) -> int:
    try:
        return max(int(os.getenv(name, str(default)) or default), minimum)
    except (TypeError, ValueError):
        return default


PLUGIN_MAX_ARCHIVE_BYTES = _env_archive_limit("PIVKEYU_PLUGIN_MAX_ARCHIVE_BYTES", 128 * 1024 * 1024, 1024 * 1024)
PLUGIN_MAX_ARCHIVE_MEMBERS = _env_archive_limit("PIVKEYU_PLUGIN_MAX_ARCHIVE_MEMBERS", 10_000, 100)
PLUGIN_MAX_MEMBER_BYTES = _env_archive_limit("PIVKEYU_PLUGIN_MAX_MEMBER_BYTES", 256 * 1024 * 1024, 1024 * 1024)
PLUGIN_MAX_UNCOMPRESSED_BYTES = _env_archive_limit(
    "PIVKEYU_PLUGIN_MAX_UNCOMPRESSED_BYTES", 1024 * 1024 * 1024, 1024 * 1024
)
PLUGIN_MAX_COMPRESSION_RATIO = _env_archive_limit("PIVKEYU_PLUGIN_MAX_COMPRESSION_RATIO", 500, 10)
PLUGIN_MAX_MANIFEST_BYTES = 1024 * 1024
KNOWN_PLUGIN_PERMISSIONS = {
    "telegram.commands",
    "telegram.callback_query",
    "telegram.inline_query",
    "telegram.read_group_messages",
    "telegram.read_private_messages",
    "telegram.send_group_messages",
    "telegram.send_private_messages",
    "telegram.manage_group_messages",
    "web.routes",
    "web.static",
    "storage.upload_files",
    "storage.plugin_data",
    "database.plugin_migrations",
    "database.plugin_tables",
    "database.shared_read",
    "database.shared_write",
    "config.read",
    "config.write",
}
_DISCOVERED: dict[str, "PluginRecord"] = {}
_LOADED = False
_MIGRATION_SUMMARY_CACHE: dict[str, dict[str, Any]] = {}
_MIGRATION_SUMMARY_LOCK = RLock()
_MIGRATION_CHECKSUM_PREFIX = "sha256-lf:"
_LEGACY_MIGRATION_CHECKSUM_ALIASES: dict[tuple[str, str, str], frozenset[str]] = {
    (
        "doupo-game",
        "001_init_tables.py",
        "eab0e036cf086774d8e7e2f16e22c42b5164cb147919a5081d314e36462a57f6",
    ): frozenset(
        {
            # Published by the previous image from a mixed-EOL Windows worktree.
            "448110a703cea1f5d513feee63798c6664a1f061fbb7832f1a5c1ebbb912c9ce",
        }
    ),
}


class PluginImportError(ValueError):
    pass


class PluginMigrationError(RuntimeError):
    pass


def _migration_checksum_values(content: bytes) -> tuple[str, str, set[str]]:
    normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    normalized_digest = hashlib.sha256(normalized).hexdigest()
    raw_digest = hashlib.sha256(content).hexdigest()
    crlf_digest = hashlib.sha256(normalized.replace(b"\n", b"\r\n")).hexdigest()
    canonical = f"{_MIGRATION_CHECKSUM_PREFIX}{normalized_digest}"
    return raw_digest, canonical, {raw_digest, normalized_digest, crlf_digest, canonical}


def _migration_checksum_matches(
    plugin_id: str,
    migration_name: str,
    applied_checksum: str,
    content: bytes,
) -> tuple[bool, str]:
    _raw_digest, canonical, candidates = _migration_checksum_values(content)
    applied = str(applied_checksum or "").strip()
    if applied in candidates:
        return True, canonical
    normalized_digest = canonical.removeprefix(_MIGRATION_CHECKSUM_PREFIX)
    aliases = _LEGACY_MIGRATION_CHECKSUM_ALIASES.get((plugin_id, migration_name, normalized_digest), frozenset())
    return applied in aliases, canonical


@dataclass(frozen=True)
class PluginContext:
    plugin_id: str
    name: str
    version: str
    install_scope: str
    plugin_type: str
    path: str
    permissions: tuple[str, ...]
    requires_restart: bool
    requires_container_rebuild: bool
    data_dir: str
    backup_dir: str
    migrations_dir: str | None = None

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def require_permissions(self, *permissions: str) -> None:
        missing = [permission for permission in permissions if permission not in self.permissions]
        if missing:
            raise PermissionError(f"插件 {self.plugin_id} 缺少权限声明: {', '.join(missing)}")

    def plugin_data_path(self, *parts: str) -> Path:
        base = Path(self.data_dir)
        target = base.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str
    description: str
    entry: str
    schema_version: int
    install_scope: str
    plugin_type: str
    manifest_enabled: bool
    enabled: bool
    path: Path
    permissions: list[str] = field(default_factory=list)
    unknown_permissions: list[str] = field(default_factory=list)
    permission_review_required: bool = False
    python_dependencies: list[str] = field(default_factory=list)
    missing_python_dependencies: list[str] = field(default_factory=list)
    requires_restart: bool = False
    requires_container_rebuild: bool = False
    migrations_dir: str | None = None
    miniapp_path: str | None = None
    admin_path: str | None = None
    miniapp_label: str | None = None
    miniapp_icon: str | None = None
    bottom_nav_default: bool = False
    overrides_builtin: bool = False
    module: ModuleType | None = None
    loaded: bool = False
    web_registered: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        migration_summary = _describe_plugin_migrations(self)
        return {
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "entry": self.entry,
            "schema_version": self.schema_version,
            "install_scope": self.install_scope,
            "plugin_type": self.plugin_type,
            "manifest_enabled": self.manifest_enabled,
            "enabled": self.enabled,
            "permissions": self.permissions,
            "unknown_permissions": self.unknown_permissions,
            "permission_review_required": self.permission_review_required,
            "python_dependencies": self.python_dependencies,
            "missing_python_dependencies": self.missing_python_dependencies,
            "requires_restart": self.requires_restart,
            "requires_container_rebuild": self.requires_container_rebuild,
            "migrations_dir": self.migrations_dir,
            "migration_summary": migration_summary,
            "miniapp_path": self.miniapp_path,
            "admin_path": self.admin_path,
            "miniapp_label": self.miniapp_label,
            "miniapp_icon": self.miniapp_icon,
            "bottom_nav_default": self.bottom_nav_default,
            "overrides_builtin": self.overrides_builtin,
            "runtime_disable_pending": bool(self.loaded and not self.enabled),
            "loaded": self.loaded,
            "web_registered": self.web_registered,
            "error": self.error,
            "path": str(self.path),
        }

    def to_miniapp_dict(self) -> dict[str, Any]:
        return {
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
            "miniapp_path": self.miniapp_path,
            "miniapp_label": self.miniapp_label,
            "miniapp_icon": self.miniapp_icon,
            "bottom_nav_default": self.bottom_nav_default,
            "loaded": self.loaded,
            "web_registered": self.web_registered,
            "error": self.error,
        }


def _configured_enabled(plugin_id: str, manifest_enabled: bool) -> bool:
    try:
        from bot import config
    except ModuleNotFoundError:
        return bool(manifest_enabled)

    override = getattr(config, "plugin_enabled", {}).get(plugin_id)
    if override is None:
        return bool(manifest_enabled)
    return bool(override)


def _refresh_record_state(record: PluginRecord) -> PluginRecord:
    record.enabled = _configured_enabled(record.plugin_id, record.manifest_enabled)
    return record


def _ensure_runtime_dirs() -> None:
    RUNTIME_PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
    RUNTIME_PLUGIN_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


def _ensure_runtime_plugin_path() -> None:
    plugin_package = sys.modules.get(PLUGIN_NAMESPACE)
    if plugin_package is None:
        return

    package_path = getattr(plugin_package, "__path__", None)
    if package_path is None:
        return

    runtime_path = str(RUNTIME_PLUGIN_ROOT)
    current_paths = [str(item) for item in package_path]
    if runtime_path in current_paths:
        package_path[:] = [runtime_path, *[item for item in current_paths if item != runtime_path]]
        return
    package_path.insert(0, runtime_path)


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        value = [value]

    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_permissions(value: Any) -> tuple[list[str], list[str], bool]:
    permissions = _normalize_string_list(value)
    unknown = [item for item in permissions if item not in KNOWN_PLUGIN_PERMISSIONS]
    return permissions, unknown, bool(unknown)


def _normalize_plugin_relative_dir(name: str | None) -> str | None:
    if name is None:
        return None

    normalized = name.replace("\\", "/").strip().strip("/")
    if not normalized:
        return None

    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise PluginImportError("插件 manifest 中的相对目录配置不合法。")
    return normalized


def _check_python_dependencies(requirements: list[str]) -> list[str]:
    if not requirements:
        return []

    missing: list[str] = []
    try:
        from packaging.requirements import Requirement
    except Exception:
        Requirement = None

    for raw_requirement in requirements:
        requirement = raw_requirement.strip()
        if not requirement:
            continue

        if Requirement is None:
            package_name = requirement.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip()
            try:
                importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                missing.append(requirement)
            continue

        parsed = Requirement(requirement)
        try:
            installed_version = importlib.metadata.version(parsed.name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(requirement)
            continue

        if parsed.specifier and installed_version not in parsed.specifier:
            missing.append(f"{requirement} (当前 {installed_version})")

    return missing


def _build_plugin_record(raw: dict[str, Any], directory: Path, install_scope: str) -> PluginRecord:
    miniapp = raw.get("miniapp", {}) or {}
    permissions, unknown_permissions, permission_review_required = _normalize_permissions(raw.get("permissions"))
    dependencies = raw.get("dependencies", {}) or {}
    python_dependencies = _normalize_string_list(dependencies.get("python"))
    missing_python_dependencies = _check_python_dependencies(python_dependencies)
    migrations_dir = _normalize_plugin_relative_dir((raw.get("database", {}) or {}).get("migrations_dir"))
    if migrations_dir is None and (directory / "migrations").is_dir():
        migrations_dir = "migrations"

    plugin_type = str(raw.get("plugin_type") or ("builtin" if install_scope == "builtin" else "runtime")).strip().lower()
    if plugin_type not in {"builtin", "runtime", "core"}:
        plugin_type = "runtime" if install_scope == "runtime" else "builtin"

    requires_container_rebuild = bool(
        raw.get("requires_container_rebuild", False)
        or bool(missing_python_dependencies)
    )
    if plugin_type == "core" and install_scope == "runtime":
        requires_container_rebuild = True

    return PluginRecord(
        plugin_id=str(raw["id"]).strip(),
        name=raw.get("name", raw["id"]),
        version=raw.get("version", "0.0.0"),
        description=raw.get("description", ""),
        entry=raw.get("entry", "plugin"),
        schema_version=int(raw.get("schema_version", 1) or 1),
        install_scope=install_scope,
        plugin_type=plugin_type,
        manifest_enabled=bool(raw.get("enabled", True)),
        enabled=False,
        path=directory,
        permissions=permissions,
        unknown_permissions=unknown_permissions,
        permission_review_required=permission_review_required,
        python_dependencies=python_dependencies,
        missing_python_dependencies=missing_python_dependencies,
        requires_restart=bool(raw.get("requires_restart", False)),
        requires_container_rebuild=requires_container_rebuild,
        migrations_dir=migrations_dir,
        miniapp_path=miniapp.get("path"),
        admin_path=miniapp.get("admin_path"),
        miniapp_label=miniapp.get("label"),
        miniapp_icon=miniapp.get("icon"),
        bottom_nav_default=bool(miniapp.get("bottom_nav_default", False)),
    )


def _plugin_roots() -> list[tuple[str, Path]]:
    _ensure_runtime_dirs()
    _ensure_runtime_plugin_path()
    return [
        ("runtime", RUNTIME_PLUGIN_ROOT),
        ("builtin", BUILTIN_PLUGIN_ROOT),
    ]


def _scan_plugins(existing: dict[str, PluginRecord] | None = None) -> dict[str, PluginRecord]:
    records: dict[str, PluginRecord] = {}
    seen_dirs: dict[str, str] = {}

    for install_scope, root in _plugin_roots():
        if not root.exists():
            continue

        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue

            manifest_path = directory / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                with manifest_path.open("r", encoding="utf-8") as manifest_file:
                    raw = json.load(manifest_file)

                record = _build_plugin_record(raw, directory, install_scope)
            except Exception as exc:
                try:
                    from bot import LOGGER

                    LOGGER.error(f"Failed to discover plugin from {manifest_path}: {exc}")
                except Exception:
                    pass
                continue

            if not record.plugin_id:
                continue

            previous = (existing or {}).get(record.plugin_id)
            if previous is not None and previous.path == directory:
                record.module = previous.module
                record.loaded = previous.loaded
                record.web_registered = previous.web_registered
                record.error = previous.error

            if record.plugin_id in records:
                records[record.plugin_id].overrides_builtin = True
                continue

            if directory.name in seen_dirs:
                current_owner = seen_dirs[directory.name]
                if current_owner != record.plugin_id:
                    continue

            seen_dirs[directory.name] = record.plugin_id
            records[record.plugin_id] = _refresh_record_state(record)

    return records


def _discover_plugins(force_refresh: bool = False) -> dict[str, PluginRecord]:
    global _DISCOVERED

    if force_refresh or not _DISCOVERED:
        if force_refresh:
            with _MIGRATION_SUMMARY_LOCK:
                _MIGRATION_SUMMARY_CACHE.clear()
        _DISCOVERED = _scan_plugins(_DISCOVERED)
        return _DISCOVERED

    for record in _DISCOVERED.values():
        _refresh_record_state(record)

    return _DISCOVERED


def _is_valid_module_name(name: str) -> bool:
    return bool(name) and name.isidentifier() and not keyword.iskeyword(name)


def _safe_plugin_dir_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    cleaned = cleaned.strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    if not cleaned:
        raise PluginImportError("插件目录名无效，请使用字母、数字或下划线。")
    if cleaned[0].isdigit():
        cleaned = f"plugin_{cleaned}"
    if not _is_valid_module_name(cleaned):
        raise PluginImportError("插件目录名无法作为 Python 模块导入，请检查压缩包目录或插件 ID。")
    return cleaned


def _normalize_archive_path(name: str) -> PurePosixPath | None:
    normalized = (name or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return None
    if normalized.startswith("/"):
        raise PluginImportError("压缩包内存在绝对路径，已拒绝导入。")

    path = PurePosixPath(normalized)
    clean_parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise PluginImportError("压缩包内存在非法的上级目录路径，已拒绝导入。")
        clean_parts.append(part)

    if clean_parts and clean_parts[0].endswith(":"):
        raise PluginImportError("压缩包内存在非法磁盘路径，已拒绝导入。")
    if not clean_parts:
        return None
    return PurePosixPath(*clean_parts)


def _is_ignored_archive_path(path: PurePosixPath) -> bool:
    if not path.parts:
        return True
    if path.parts[0] == "__MACOSX":
        return True
    if "__pycache__" in path.parts:
        return True
    if path.name == ".DS_Store":
        return True
    return False


def _resolve_archive_root(paths: set[PurePosixPath]) -> str | None:
    if PurePosixPath("plugin.json") in paths:
        return None

    top_levels = {path.parts[0] for path in paths if path.parts}
    if len(top_levels) != 1:
        raise PluginImportError("压缩包需要在根目录，或唯一一级目录内包含 plugin.json。")

    top_level = next(iter(top_levels))
    if PurePosixPath(top_level, "plugin.json") not in paths:
        raise PluginImportError("未在压缩包根目录找到 plugin.json。")

    return top_level


def _validate_entry_module(entry: str) -> str:
    module_name = entry.strip().removesuffix(".py")
    if not module_name:
        raise PluginImportError("plugin.json 中的 entry 不能为空。")
    if "/" in module_name or "\\" in module_name:
        raise PluginImportError("plugin.json 中的 entry 只能是模块名，不能包含路径分隔符。")

    parts = module_name.split(".")
    if any(not _is_valid_module_name(part) for part in parts):
        raise PluginImportError("plugin.json 中的 entry 不是有效的 Python 模块名。")
    return module_name


def _module_name(record: PluginRecord) -> str:
    return f"{PLUGIN_NAMESPACE}.{record.path.name}.{record.entry.removesuffix('.py')}"


def _plugin_context(record: PluginRecord) -> PluginContext:
    plugin_data_root = PROJECT_ROOT / "data" / "plugin_state" / record.plugin_id
    plugin_data_root.mkdir(parents=True, exist_ok=True)
    return PluginContext(
        plugin_id=record.plugin_id,
        name=record.name,
        version=record.version,
        install_scope=record.install_scope,
        plugin_type=record.plugin_type,
        path=str(record.path),
        permissions=tuple(record.permissions),
        requires_restart=record.requires_restart,
        requires_container_rebuild=record.requires_container_rebuild,
        data_dir=str(plugin_data_root),
        backup_dir=str(RUNTIME_PLUGIN_BACKUP_ROOT / record.plugin_id),
        migrations_dir=str(record.path / record.migrations_dir) if record.migrations_dir else None,
    )


def _describe_plugin_migrations(record: PluginRecord) -> dict[str, Any]:
    with _MIGRATION_SUMMARY_LOCK:
        cached = _MIGRATION_SUMMARY_CACHE.get(record.plugin_id)
    if cached is not None:
        return {**cached, "pending_files": list(cached.get("pending_files") or [])}

    migration_dir = _resolve_plugin_migration_dir(record)
    if migration_dir is None:
        summary = {"supported": False, "dir": None, "total": 0, "applied": 0, "pending": 0, "pending_files": []}
        with _MIGRATION_SUMMARY_LOCK:
            _MIGRATION_SUMMARY_CACHE[record.plugin_id] = summary
        return dict(summary)

    from bot.sql_helper.sql_plugin import list_applied_plugin_migrations

    files = sorted(migration_dir.glob("*.py"))
    applied = list_applied_plugin_migrations(record.plugin_id)
    pending_files = [file.name for file in files if file.name not in applied]
    summary = {
        "supported": True,
        "dir": str(migration_dir),
        "total": len(files),
        "applied": len(files) - len(pending_files),
        "pending": len(pending_files),
        "pending_files": pending_files,
    }
    with _MIGRATION_SUMMARY_LOCK:
        _MIGRATION_SUMMARY_CACHE[record.plugin_id] = summary
    return {**summary, "pending_files": list(pending_files)}


def _resolve_plugin_migration_dir(record: PluginRecord) -> Path | None:
    if not record.migrations_dir:
        return None
    migration_dir = record.path / record.migrations_dir
    if not migration_dir.is_dir():
        return None
    return migration_dir


def _apply_plugin_migrations(record: PluginRecord) -> dict[str, Any]:
    migration_dir = _resolve_plugin_migration_dir(record)
    if migration_dir is None:
        with _MIGRATION_SUMMARY_LOCK:
            _MIGRATION_SUMMARY_CACHE[record.plugin_id] = {
                "supported": False,
                "dir": None,
                "total": 0,
                "applied": 0,
                "pending": 0,
                "pending_files": [],
            }
        return {"applied": [], "pending": [], "supported": False}

    from bot.sql_helper import Session
    from bot.sql_helper.sql_plugin import (
        PluginMigrationRecord,
        list_applied_plugin_migrations,
        update_plugin_migration_checksum,
    )

    applied_checksums = list_applied_plugin_migrations(record.plugin_id)
    migration_files = sorted(migration_dir.glob("*.py"))
    applied_now: list[str] = []

    for migration_file in migration_files:
        migration_content = migration_file.read_bytes()
        checksum = _migration_checksum_values(migration_content)[1]
        applied_checksum = applied_checksums.get(migration_file.name)
        if applied_checksum:
            matches, canonical_checksum = _migration_checksum_matches(
                record.plugin_id,
                migration_file.name,
                applied_checksum,
                migration_content,
            )
            if not matches:
                raise PluginMigrationError(
                    f"插件 {record.plugin_id} 的迁移 {migration_file.name} 已执行过，但文件内容已变化，请改用新迁移文件。"
                )
            if applied_checksum != canonical_checksum:
                update_plugin_migration_checksum(record.plugin_id, migration_file.name, canonical_checksum)
                applied_checksums[migration_file.name] = canonical_checksum
            continue

        module_name = f"_plugin_migrations_{record.plugin_id}_{migration_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, migration_file)
        if spec is None or spec.loader is None:
            raise PluginMigrationError(f"无法载入插件迁移文件: {migration_file.name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        upgrade = getattr(module, "upgrade", None)
        if not callable(upgrade):
            raise PluginMigrationError(f"插件迁移 {migration_file.name} 缺少 upgrade(connection) 函数。")

        with Session() as session:
            connection = session.connection()
            upgrade(connection)
            session.add(
                PluginMigrationRecord(
                    plugin_id=record.plugin_id,
                    migration_name=migration_file.name,
                    checksum=checksum,
                )
            )
            session.commit()

        applied_now.append(migration_file.name)
        applied_checksums[migration_file.name] = checksum

    pending_files = [file.name for file in migration_files if file.name not in applied_checksums]
    with _MIGRATION_SUMMARY_LOCK:
        _MIGRATION_SUMMARY_CACHE[record.plugin_id] = {
            "supported": True,
            "dir": str(migration_dir),
            "total": len(migration_files),
            "applied": len(migration_files) - len(pending_files),
            "pending": len(pending_files),
            "pending_files": list(pending_files),
        }
    return {
        "supported": True,
        "applied": applied_now,
        "pending": pending_files,
    }


def _persist_plugin_installation(record: PluginRecord, *, source_filename: str | None = None, error: str | None = None) -> None:
    from bot.sql_helper.sql_plugin import upsert_plugin_installation

    manifest: dict[str, Any] = {
        "schema_version": record.schema_version,
        "id": record.plugin_id,
        "name": record.name,
        "version": record.version,
        "description": record.description,
        "entry": record.entry,
        "plugin_type": record.plugin_type,
        "enabled": record.manifest_enabled,
        "permissions": record.permissions,
        "dependencies": {"python": record.python_dependencies},
    }
    if record.migrations_dir:
        manifest["database"] = {"migrations_dir": record.migrations_dir}

    upsert_plugin_installation(
        record.plugin_id,
        name=record.name,
        version=record.version,
        install_scope=record.install_scope,
        plugin_type=record.plugin_type,
        install_path=str(record.path),
        source_filename=source_filename,
        enabled=record.enabled,
        requires_restart=record.requires_restart,
        requires_container_rebuild=record.requires_container_rebuild,
        permissions=record.permissions,
        python_dependencies=record.python_dependencies,
        manifest=manifest,
        last_error=error,
    )


def _clear_plugin_modules(record: PluginRecord) -> None:
    prefix = f"{PLUGIN_NAMESPACE}.{record.path.name}"
    for module_name in list(sys.modules):
        if module_name == prefix or module_name.startswith(prefix + "."):
            sys.modules.pop(module_name, None)


def _invoke_plugin_hook(callback: Any, primary: Any, record: PluginRecord) -> None:
    try:
        parameters = list(inspect.signature(callback).parameters.values())
    except (TypeError, ValueError):
        callback(primary)
        return

    if len(parameters) >= 2:
        callback(primary, _plugin_context(record))
    else:
        callback(primary)


def _backup_runtime_plugin(record: PluginRecord | None) -> str | None:
    if record is None or record.install_scope != "runtime" or not record.path.exists():
        return None

    backup_dir = RUNTIME_PLUGIN_BACKUP_ROOT / record.plugin_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{record.version or '0.0.0'}_{record.path.name}"
    destination = backup_dir / backup_name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(record.path, destination)
    return str(destination)


def import_plugin_archive(
    archive_bytes: bytes,
    filename: str,
    *,
    replace_existing: bool = False,
) -> dict[str, Any]:
    _ensure_runtime_dirs()

    if not archive_bytes:
        raise PluginImportError("上传文件为空，无法导入插件。")
    if len(archive_bytes) > PLUGIN_MAX_ARCHIVE_BYTES:
        raise PluginImportError(f"插件压缩包不能超过 {PLUGIN_MAX_ARCHIVE_BYTES // (1024 * 1024)}MB。")

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise PluginImportError("上传文件不是有效的 ZIP 压缩包。") from exc

    with archive:
        normalized_members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        visible_paths: set[PurePosixPath] = set()
        total_uncompressed = 0
        archive_members = archive.infolist()
        if len(archive_members) > PLUGIN_MAX_ARCHIVE_MEMBERS:
            raise PluginImportError(f"插件压缩包文件数量不能超过 {PLUGIN_MAX_ARCHIVE_MEMBERS}。")

        for info in archive_members:
            normalized_path = _normalize_archive_path(info.filename)
            if normalized_path is None or _is_ignored_archive_path(normalized_path):
                continue

            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PluginImportError("插件压缩包中不能包含符号链接。")
            if info.flag_bits & 0x1:
                raise PluginImportError("插件压缩包中不能包含加密文件。")
            if info.file_size > PLUGIN_MAX_MEMBER_BYTES:
                raise PluginImportError(f"插件压缩包中的单个文件不能超过 {PLUGIN_MAX_MEMBER_BYTES // (1024 * 1024)}MB。")
            total_uncompressed += int(info.file_size or 0)
            if total_uncompressed > PLUGIN_MAX_UNCOMPRESSED_BYTES:
                raise PluginImportError(
                    f"插件压缩包解压后的总大小不能超过 {PLUGIN_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)}MB。"
                )
            compressed_size = max(int(info.compress_size or 0), 1)
            if info.file_size > 1024 * 1024 and info.file_size / compressed_size > PLUGIN_MAX_COMPRESSION_RATIO:
                raise PluginImportError("插件压缩包包含异常压缩比文件，已拒绝导入。")

            normalized_members.append((info, normalized_path))
            visible_paths.add(normalized_path)

        if not visible_paths:
            raise PluginImportError("压缩包中没有可导入的插件文件。")

        archive_root = _resolve_archive_root(visible_paths)
        manifest_path = PurePosixPath("plugin.json") if archive_root is None else PurePosixPath(archive_root, "plugin.json")

        try:
            manifest_info = archive.getinfo(manifest_path.as_posix())
            if manifest_info.file_size > PLUGIN_MAX_MANIFEST_BYTES:
                raise PluginImportError("plugin.json 不能超过 1MB。")
            manifest_raw = json.loads(archive.read(manifest_path.as_posix()).decode("utf-8-sig"))
        except KeyError as exc:
            raise PluginImportError("压缩包中缺少 plugin.json。") from exc
        except UnicodeDecodeError as exc:
            raise PluginImportError("plugin.json 需要使用 UTF-8 编码。") from exc
        except json.JSONDecodeError as exc:
            raise PluginImportError(f"plugin.json 格式不正确: {exc.msg}") from exc

        if not isinstance(manifest_raw, dict):
            raise PluginImportError("plugin.json 顶层必须是 JSON 对象。")

        plugin_id = str(manifest_raw.get("id") or "").strip()
        if not plugin_id:
            raise PluginImportError("plugin.json 缺少插件 id。")

        manifest_record = _build_plugin_record(manifest_raw, Path("."), "runtime")
        if manifest_record.plugin_type == "core":
            raise PluginImportError("plugin_type=core 的插件不能通过后台运行时导入，请将其并入仓库镜像后再部署。")

        entry_module = _validate_entry_module(str(manifest_raw.get("entry", "plugin") or "plugin"))
        entry_path = PurePosixPath(*entry_module.split("."))
        module_file = entry_path.with_suffix(".py")
        package_init = entry_path / "__init__.py"
        module_candidate = module_file if archive_root is None else PurePosixPath(archive_root, module_file.as_posix())
        package_candidate = package_init if archive_root is None else PurePosixPath(archive_root, package_init.as_posix())
        if module_candidate not in visible_paths and package_candidate not in visible_paths:
            raise PluginImportError(f"未在压缩包中找到插件入口 {entry_module}。")

        records = _discover_plugins()
        existing_record = records.get(plugin_id)
        preferred_dir = archive_root if archive_root is not None and _is_valid_module_name(archive_root) else plugin_id
        destination_name = existing_record.path.name if existing_record is not None else _safe_plugin_dir_name(preferred_dir)
        destination_path = RUNTIME_PLUGIN_ROOT / destination_name
        existing_dir_record = next(
            (record for record in records.values() if record.path.name == destination_name and record.install_scope == "runtime"),
            None,
        )

        if not replace_existing:
            if existing_record is not None:
                raise PluginImportError(f"插件 {plugin_id} 已存在，如需覆盖请勾选“覆盖已存在插件”。")
            if existing_dir_record is not None and existing_dir_record.plugin_id != plugin_id:
                raise PluginImportError(f"插件目录 {destination_name} 已被 {existing_dir_record.plugin_id} 占用。")
            if destination_path.exists() and existing_dir_record is None:
                raise PluginImportError(f"插件目录 {destination_name} 已存在，无法直接覆盖。")
        else:
            if existing_record is not None and (existing_record.loaded or existing_record.web_registered):
                raise PluginImportError(
                    f"插件 {plugin_id} 当前已经在进程中加载，覆盖更新前请先重启本女仆。"
                )
            if existing_dir_record is not None and existing_dir_record.plugin_id != plugin_id:
                raise PluginImportError(f"插件目录 {destination_name} 已被 {existing_dir_record.plugin_id} 占用。")
            if destination_path.exists() and existing_record is None and existing_dir_record is None:
                raise PluginImportError(f"插件目录 {destination_name} 已存在，无法确认归属，已拒绝覆盖。")

        extracted_members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info, normalized_path in normalized_members:
            if archive_root is not None:
                if normalized_path.parts[0] != archive_root:
                    raise PluginImportError("压缩包只能包含一个插件目录。")
                relative_path = PurePosixPath(*normalized_path.parts[1:])
            else:
                relative_path = normalized_path

            if not relative_path.parts:
                continue
            extracted_members.append((info, relative_path))

        if not extracted_members:
            raise PluginImportError("压缩包中没有可写入的插件文件。")

        backup_path = _backup_runtime_plugin(existing_dir_record)
        with tempfile.TemporaryDirectory(prefix="plugin-import-", dir=RUNTIME_PLUGIN_ROOT) as temp_dir:
            temp_plugin_dir = Path(temp_dir) / destination_name
            temp_plugin_dir.mkdir(parents=True, exist_ok=True)

            for info, relative_path in extracted_members:
                target_path = temp_plugin_dir.joinpath(*relative_path.parts)
                if not str(target_path.resolve()).startswith(str(temp_plugin_dir.resolve())):
                    raise PluginImportError("检测到非法写入路径，已拒绝导入。")
                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target_path.open("wb") as extracted_file:
                    shutil.copyfileobj(source, extracted_file, length=1024 * 1024)

            if replace_existing and destination_path.exists():
                shutil.rmtree(destination_path)

            shutil.move(str(temp_plugin_dir), str(destination_path))

    importlib.invalidate_caches()
    refreshed = _discover_plugins(force_refresh=True)
    imported_record = refreshed.get(plugin_id)
    if imported_record is None:
        raise PluginImportError("插件导入完成后未能重新识别，请检查 plugin.json。")

    imported_record.enabled = _configured_enabled(imported_record.plugin_id, imported_record.manifest_enabled)
    _persist_plugin_installation(imported_record, source_filename=filename)

    return {
        "plugin_id": imported_record.plugin_id,
        "name": imported_record.name,
        "install_scope": imported_record.install_scope,
        "plugin_type": imported_record.plugin_type,
        "manifest_enabled": imported_record.manifest_enabled,
        "directory": imported_record.path.name,
        "requires_restart": imported_record.requires_restart,
        "requires_container_rebuild": imported_record.requires_container_rebuild,
        "permissions": imported_record.permissions,
        "unknown_permissions": imported_record.unknown_permissions,
        "missing_python_dependencies": imported_record.missing_python_dependencies,
        "migration_summary": _describe_plugin_migrations(imported_record),
        "replaced": bool(replace_existing and existing_record is not None),
        "backup_path": backup_path,
        "source_filename": filename,
    }


def _load_plugin(record: PluginRecord) -> None:
    from bot import LOGGER, bot

    if record.loaded and record.module is not None:
        return

    _ensure_runtime_plugin_path()

    if record.requires_container_rebuild and record.install_scope == "runtime":
        raise RuntimeError(
            f"插件 {record.plugin_id} 需要先完成容器重建或依赖补齐后才能启用。"
        )
    if record.missing_python_dependencies:
        raise RuntimeError(
            f"插件 {record.plugin_id} 缺少 Python 依赖: {', '.join(record.missing_python_dependencies)}"
        )

    migration_result = _apply_plugin_migrations(record)
    if migration_result.get("applied"):
        LOGGER.info(
            f"Applied plugin migrations for {record.plugin_id}: {', '.join(migration_result['applied'])}"
        )

    module_name = _module_name(record)
    _clear_plugin_modules(record)
    module = importlib.import_module(module_name)
    record.module = module

    register_bot = getattr(module, "register_bot", None)
    web_only = str(os.getenv("PIVKEYU_WEB_ONLY", "")).strip().lower() in {"1", "true", "yes", "on"}
    if callable(register_bot) and not web_only:
        _invoke_plugin_hook(register_bot, bot, record)

    record.loaded = True
    record.error = None
    try:
        from bot.sql_helper.sql_plugin import mark_plugin_loaded

        mark_plugin_loaded(record.plugin_id)
    except Exception as exc:
        LOGGER.warning(f"Failed to update plugin load state for {record.plugin_id}: {exc}")
    LOGGER.info(f"Loaded plugin: {record.plugin_id}")


def _register_web(record: PluginRecord, app: Any) -> None:
    from bot import LOGGER

    if not record.loaded or record.web_registered or record.module is None:
        return

    register_web = getattr(record.module, "register_web", None)
    if not callable(register_web):
        return

    _invoke_plugin_hook(register_web, app, record)
    record.web_registered = True
    record.error = None
    LOGGER.info(f"Registered web routes for plugin: {record.plugin_id}")


def load_plugins() -> list[dict[str, Any]]:
    global _LOADED

    started_at = time.perf_counter()
    records = _discover_plugins()
    from bot import LOGGER

    for record in records.values():
        if not record.loaded:
            _persist_plugin_installation(record)
        if not record.enabled or record.loaded:
            continue

        try:
            plugin_started_at = time.perf_counter()
            _load_plugin(record)
            elapsed_ms = int((time.perf_counter() - plugin_started_at) * 1000)
            LOGGER.info(f"Plugin startup timing: {record.plugin_id} {elapsed_ms}ms")
        except Exception as exc:
            record.error = str(exc)
            _persist_plugin_installation(record, error=record.error)
            LOGGER.error(f"Failed to load plugin {record.plugin_id}: {exc}")

    _LOADED = True
    LOGGER.info(f"Plugin startup complete: {int((time.perf_counter() - started_at) * 1000)}ms")
    return [record.to_dict() for record in records.values()]


def register_web_plugins(app: Any) -> None:
    started_at = time.perf_counter()
    for record in _discover_plugins().values():
        if not record.enabled or not record.loaded:
            continue

        try:
            _register_web(record, app)
        except Exception as exc:
            from bot import LOGGER

            record.error = str(exc)
            _persist_plugin_installation(record, error=record.error)
            LOGGER.error(f"Failed to register web routes for plugin {record.plugin_id}: {exc}")
    from bot import LOGGER

    LOGGER.info(f"Plugin web route registration complete: {int((time.perf_counter() - started_at) * 1000)}ms")


def has_loaded_plugins() -> bool:
    return any(record.enabled and record.loaded for record in _discover_plugins().values())


def sync_plugin_runtime_state(plugin_id: str, app: Any | None = None) -> dict[str, Any]:
    records = _discover_plugins()
    record = records.get(plugin_id)
    if record is None:
        raise KeyError(plugin_id)

    _refresh_record_state(record)
    restart_required = bool(record.requires_restart)

    if record.enabled and not record.loaded:
        try:
            _load_plugin(record)
        except Exception as exc:
            from bot import LOGGER

            record.error = str(exc)
            _persist_plugin_installation(record, error=record.error)
            LOGGER.error(f"Failed to load plugin {record.plugin_id}: {exc}")

    if record.enabled and app is not None:
        try:
            _register_web(record, app)
        except Exception as exc:
            from bot import LOGGER

            record.error = str(exc)
            _persist_plugin_installation(record, error=record.error)
            LOGGER.error(f"Failed to register web routes for plugin {record.plugin_id}: {exc}")

    if not record.enabled and (record.loaded or record.web_registered):
        restart_required = True

    _persist_plugin_installation(record, error=record.error)
    payload = record.to_dict()
    payload["restart_required"] = restart_required
    payload["container_rebuild_required"] = bool(record.requires_container_rebuild)
    return payload


def list_plugins() -> list[dict[str, Any]]:
    return [record.to_dict() for record in _discover_plugins().values()]


def list_miniapp_plugins() -> list[dict[str, Any]]:
    return [record.to_miniapp_dict() for record in _discover_plugins().values()]
