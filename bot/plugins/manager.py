from __future__ import annotations

import hashlib
import io
import importlib
import importlib.metadata
import json
import keyword
import inspect
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
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
_PLUGIN_OPERATION_LOCK = RLock()
_MIGRATION_EXECUTION_LOCK = RLock()
_PLUGIN_BACKUP_LIMIT = min(_env_archive_limit("PIVKEYU_PLUGIN_BACKUP_LIMIT", 3, 1), 10)
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
        target = _resolve_contained_path(self.data_dir, *parts)
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
    web_registration_attempted: bool = False
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
            "web_registration_attempted": self.web_registration_attempted,
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
    record.enabled = bool(record.manifest_enabled and not record.permission_review_required)
    if record.enabled:
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
    builtin_path = str(BUILTIN_PLUGIN_ROOT)
    current_paths = [str(item) for item in package_path if str(item) not in {runtime_path, builtin_path}]
    # Keep shipped plugins authoritative when a runtime archive reuses a
    # built-in directory name. Unique runtime packages remain importable after
    # the repository package path.
    package_path[:] = [builtin_path, *current_paths, runtime_path]


_PLUGIN_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PLUGIN_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_PLUGIN_NAME_MAX = 128
_REQUIREMENT_MAX = 256
_MIGRATION_NAME_RE = re.compile(r"^[0-9]{3,}_[A-Za-z0-9][A-Za-z0-9_.-]*\.py$")


def _require_text(value: Any, field: str, *, maximum: int, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str):
        raise PluginImportError(f"plugin.json 字段 {field} 必须是字符串。")
    text = value.strip()
    if not text or len(text) > maximum:
        raise PluginImportError(f"plugin.json 字段 {field} 长度不合法。")
    if pattern is not None and not pattern.fullmatch(text):
        raise PluginImportError(f"plugin.json 字段 {field} 包含非法字符。")
    return text


def _normalize_string_list(value: Any, field: str = "字段", *, maximum_items: int = 128, item_maximum: int = _REQUIREMENT_MAX) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PluginImportError(f"plugin.json 字段 {field} 必须是字符串数组。")
    if len(value) > maximum_items:
        raise PluginImportError(f"plugin.json 字段 {field} 项目过多。")
    normalized: list[str] = []
    for item in value:
        text = _require_text(item, field, maximum=item_maximum)
        if text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_permissions(value: Any) -> tuple[list[str], list[str], bool]:
    permissions = _normalize_string_list(value, "permissions", item_maximum=96)
    unknown = [item for item in permissions if item not in KNOWN_PLUGIN_PERMISSIONS]
    return permissions, unknown, bool(unknown)


def _resolve_contained_path(base: str | Path, *parts: str) -> Path:
    base_path = Path(base).resolve(strict=False)
    for raw_part in parts:
        part = str(raw_part)
        windows_part = PureWindowsPath(part)
        posix_part = PurePosixPath(part.replace("\\", "/"))
        if windows_part.is_absolute() or windows_part.drive or part.startswith(("\\\\", "//")) or posix_part.is_absolute():
            raise PluginImportError("插件路径不能是绝对路径或跨磁盘路径。")
    try:
        target = base_path.joinpath(*(str(part) for part in parts)).resolve(strict=False)
    except (TypeError, ValueError) as exc:
        raise PluginImportError("插件路径参数不合法。") from exc
    try:
        target.relative_to(base_path)
    except ValueError as exc:
        raise PluginImportError("插件路径超出允许目录范围。") from exc
    return target


def _normalize_plugin_relative_dir(name: str | None) -> str | None:
    if name is None:
        return None
    if not isinstance(name, str) or len(name) > 128:
        raise PluginImportError("插件 manifest 中的相对目录配置不合法。")

    normalized = name.replace("\\", "/").strip().strip("/")
    if not normalized:
        return None

    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or ":" in normalized or any(PureWindowsPath(part).drive for part in path.parts):
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
        if len(requirement) > _REQUIREMENT_MAX:
            raise PluginImportError("plugin.json requirements 项目过长。")
        if not requirement:
            continue

        if Requirement is None:
            package_name = requirement.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip()
            try:
                importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                missing.append(requirement)
            continue

        try:
            parsed = Requirement(requirement)
        except Exception as exc:
            raise PluginImportError(f"plugin.json requirements 项目无效: {requirement}") from exc
        try:
            installed_version = importlib.metadata.version(parsed.name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(requirement)
            continue

        if parsed.specifier and installed_version not in parsed.specifier:
            missing.append(f"{requirement} (当前 {installed_version})")

    return missing


def _build_plugin_record(raw: dict[str, Any], directory: Path, install_scope: str) -> PluginRecord:
    if not isinstance(raw, dict):
        raise PluginImportError("plugin.json 顶层必须是 JSON 对象。")
    plugin_id = _require_text(raw.get("id"), "id", maximum=64, pattern=_PLUGIN_ID_RE)
    name = _require_text(raw.get("name", plugin_id), "name", maximum=_PLUGIN_NAME_MAX)
    version = _require_text(raw.get("version", "0.0.0"), "version", maximum=64, pattern=_PLUGIN_VERSION_RE)
    entry = _validate_entry_module(_require_text(raw.get("entry", "plugin"), "entry", maximum=128))
    schema_value = raw.get("schema_version", 1)
    if isinstance(schema_value, bool) or not isinstance(schema_value, int) or not 0 <= schema_value <= 10000:
        raise PluginImportError("plugin.json 字段 schema_version 必须是合法整数。")
    description = raw.get("description", "")
    if not isinstance(description, str) or len(description) > 4096:
        raise PluginImportError("plugin.json 字段 description 类型或长度不合法。")
    miniapp = raw.get("miniapp", {})
    if miniapp is None:
        miniapp = {}
    if not isinstance(miniapp, dict):
        raise PluginImportError("plugin.json 字段 miniapp 必须是对象。")
    permissions, unknown_permissions, permission_review_required = _normalize_permissions(raw.get("permissions", []))
    dependencies = raw.get("dependencies", {})
    if dependencies is None:
        dependencies = {}
    if not isinstance(dependencies, dict):
        raise PluginImportError("plugin.json 字段 dependencies 必须是对象。")
    python_dependencies = _normalize_string_list(dependencies.get("python", dependencies.get("requirements", [])), "requirements")
    missing_python_dependencies = _check_python_dependencies(python_dependencies)
    database = raw.get("database", {})
    if database is None:
        database = {}
    if not isinstance(database, dict):
        raise PluginImportError("plugin.json 字段 database 必须是对象。")
    migrations_dir = _normalize_plugin_relative_dir(database.get("migrations_dir"))
    if migrations_dir is None and (directory / "migrations").is_dir():
        migrations_dir = "migrations"

    raw_plugin_type = raw.get("plugin_type")
    if raw_plugin_type is not None and not isinstance(raw_plugin_type, str):
        raise PluginImportError("plugin.json 字段 plugin_type 必须是字符串。")
    plugin_type = str(raw_plugin_type or ("builtin" if install_scope == "builtin" else "runtime")).strip().lower()
    enabled_value = raw.get("enabled", True)
    if not isinstance(enabled_value, bool):
        raise PluginImportError("plugin.json 字段 enabled 必须是布尔值。")
    if plugin_type not in {"builtin", "runtime", "core"}:
        plugin_type = "runtime" if install_scope == "runtime" else "builtin"

    requires_container_rebuild_value = raw.get("requires_container_rebuild", False)
    requires_restart_value = raw.get("requires_restart", False)
    if not isinstance(requires_container_rebuild_value, bool) or not isinstance(requires_restart_value, bool):
        raise PluginImportError("plugin.json 重启/重建标志必须是布尔值。")
    requires_container_rebuild = bool(requires_container_rebuild_value or bool(missing_python_dependencies))
    if plugin_type == "core" and install_scope == "runtime":
        requires_container_rebuild = True

    return PluginRecord(
        plugin_id=plugin_id,
        name=name,
        version=version,
        description=description,
        entry=entry,
        schema_version=schema_value,
        install_scope=install_scope,
        plugin_type=plugin_type,
        manifest_enabled=enabled_value and not permission_review_required,
        enabled=False,
        path=directory,
        permissions=permissions,
        unknown_permissions=unknown_permissions,
        permission_review_required=permission_review_required,
        python_dependencies=python_dependencies,
        missing_python_dependencies=missing_python_dependencies,
        requires_restart=requires_restart_value,
        requires_container_rebuild=requires_container_rebuild,
        migrations_dir=migrations_dir,
        miniapp_path=_normalize_plugin_relative_dir(miniapp.get("path")),
        admin_path=_normalize_plugin_relative_dir(miniapp.get("admin_path")),
        miniapp_label=_require_text(miniapp["label"], "miniapp.label", maximum=64) if "label" in miniapp else None,
        miniapp_icon=_require_text(miniapp["icon"], "miniapp.icon", maximum=32) if "icon" in miniapp else None,
        bottom_nav_default=bool(miniapp.get("bottom_nav_default", False)),
    )


def _plugin_roots() -> list[tuple[str, Path]]:
    _ensure_runtime_dirs()
    _ensure_runtime_plugin_path()
    # Built-ins are scanned first so a runtime directory cannot shadow a
    # shipped plugin with the same ID or package directory.
    return [
        ("builtin", BUILTIN_PLUGIN_ROOT),
        ("runtime", RUNTIME_PLUGIN_ROOT),
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
                record.web_registration_attempted = previous.web_registration_attempted
                record.error = previous.error

            if record.plugin_id in records:
                # Built-ins are authoritative; ignore a runtime duplicate.
                if records[record.plugin_id].install_scope == "builtin" and install_scope == "runtime":
                    continue
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
    plugin_data_root = _resolve_contained_path(PROJECT_ROOT / "data" / "plugin_state", record.plugin_id)
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
        backup_dir=str(_resolve_contained_path(RUNTIME_PLUGIN_BACKUP_ROOT, record.plugin_id)),
        migrations_dir=str(_resolve_contained_path(record.path, *PurePosixPath(record.migrations_dir).parts)) if record.migrations_dir else None,
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

    files = _explicit_migration_files(migration_dir)
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
    migration_dir = _resolve_contained_path(record.path, *PurePosixPath(record.migrations_dir).parts)
    if migration_dir.is_symlink() or not migration_dir.is_dir():
        return None
    return migration_dir


def _explicit_migration_files(migration_dir: Path) -> list[Path]:
    files = []
    base = migration_dir.resolve(strict=False)
    for file in migration_dir.iterdir():
        if file.is_symlink() or not file.is_file() or not _MIGRATION_NAME_RE.fullmatch(file.name):
            continue
        resolved = file.resolve(strict=False)
        try:
            resolved.relative_to(base)
        except ValueError:
            raise PluginMigrationError(f"插件迁移文件越出迁移目录: {file.name}") from None
        files.append(resolved)
    return sorted(files)


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

    migration_files = _explicit_migration_files(migration_dir)
    applied_now: list[str] = []

    with _MIGRATION_EXECUTION_LOCK:
        applied_checksums = list_applied_plugin_migrations(record.plugin_id)
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

    backup_dir = _resolve_contained_path(RUNTIME_PLUGIN_BACKUP_ROOT, record.plugin_id)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{record.version or '0.0.0'}_{record.path.name}_{time.time_ns()}"
    destination = _resolve_contained_path(backup_dir, backup_name)
    if destination.exists():
        shutil.rmtree(destination)
    for current_root, dir_names, file_names in os.walk(record.path, followlinks=False):
        for item in (*dir_names, *file_names):
            if Path(current_root, item).is_symlink():
                raise PluginImportError("已安装插件包含符号链接，拒绝备份或替换。")
    shutil.copytree(record.path, destination, symlinks=False)
    backups = sorted((item for item in backup_dir.iterdir() if item.is_dir()), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in backups[_PLUGIN_BACKUP_LIMIT:]:
        shutil.rmtree(stale, ignore_errors=True)
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
        visible_files: set[PurePosixPath] = set()
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

            if normalized_path in visible_paths:
                raise PluginImportError("压缩包内存在重复文件路径，已拒绝导入。")
            # A file cannot also be a directory prefix (foo and foo/bar).
            if any(normalized_path.parts[:index] in visible_files for index in range(1, len(normalized_path.parts))):
                raise PluginImportError("压缩包内存在文件/目录前缀冲突，已拒绝导入。")
            if any(existing.parts[:index] == normalized_path for existing in visible_files for index in range(1, len(existing.parts))):
                raise PluginImportError("压缩包内存在文件/目录前缀冲突，已拒绝导入。")
            normalized_members.append((info, normalized_path))
            visible_paths.add(normalized_path)
            if not info.is_dir():
                visible_files.add(normalized_path)

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

        plugin_id = _require_text(manifest_raw.get("id"), "id", maximum=64, pattern=_PLUGIN_ID_RE)
        manifest_record = _build_plugin_record(manifest_raw, Path("."), "runtime")
        if manifest_record.permission_review_required:
            manifest_record.manifest_enabled = False
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
        if existing_record is not None and existing_record.install_scope == "builtin":
            raise PluginImportError(
                f"运行时插件不能覆盖内置插件 {plugin_id}，请修改插件 ID 或更新内置版本。"
            )
        preferred_dir = archive_root if archive_root is not None and _is_valid_module_name(archive_root) else plugin_id
        destination_name = existing_record.path.name if existing_record is not None else _safe_plugin_dir_name(preferred_dir)
        destination_path = _resolve_contained_path(RUNTIME_PLUGIN_ROOT, destination_name)
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

        with _PLUGIN_OPERATION_LOCK:
            current_records = _discover_plugins(force_refresh=True)
            current_existing = current_records.get(plugin_id)
            if current_existing is not None and current_existing.path != destination_path and not replace_existing:
                raise PluginImportError(f"插件 {plugin_id} 已存在，如需覆盖请勾选“覆盖已存在插件”。")
            backup_path = _backup_runtime_plugin(current_existing or existing_dir_record)
            with tempfile.TemporaryDirectory(prefix="plugin-import-", dir=RUNTIME_PLUGIN_ROOT) as temp_dir:
                temp_plugin_dir = Path(temp_dir) / destination_name
                temp_plugin_dir.mkdir(parents=True, exist_ok=True)

                for info, relative_path in extracted_members:
                    target_path = _resolve_contained_path(temp_plugin_dir, *relative_path.parts)
                    if target_path == temp_plugin_dir:
                        raise PluginImportError("检测到非法写入路径，已拒绝导入。")
                    if info.is_dir():
                        target_path.mkdir(parents=True, exist_ok=True)
                        continue

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source, target_path.open("wb") as extracted_file:
                        shutil.copyfileobj(source, extracted_file, length=1024 * 1024)

                staged_path = temp_plugin_dir.resolve(strict=False)
                try:
                    staged_path.relative_to(RUNTIME_PLUGIN_ROOT.resolve(strict=False))
                except ValueError as exc:
                    raise PluginImportError("检测到非法暂存路径，已拒绝导入。") from exc
                destination_path = _resolve_contained_path(RUNTIME_PLUGIN_ROOT, destination_name)
                old_path = None
                if replace_existing and destination_path.exists():
                    old_path = destination_path.with_name(f".{destination_name}.old-{os.getpid()}-{time.time_ns()}")
                    os.replace(destination_path, old_path)
                try:
                    os.replace(staged_path, destination_path)
                except Exception:
                    if old_path is not None and old_path.exists():
                        os.replace(old_path, destination_path)
                    raise
                if old_path is not None and old_path.exists():
                    shutil.rmtree(old_path, ignore_errors=True)

    importlib.invalidate_caches()
    refreshed = _discover_plugins(force_refresh=True)
    imported_record = refreshed.get(plugin_id)
    if imported_record is None:
        raise PluginImportError("插件导入完成后未能重新识别，请检查 plugin.json。")

    _refresh_record_state(imported_record)
    try:
        _persist_plugin_installation(imported_record, source_filename=filename)
    except Exception as exc:
        # The filesystem install must not become an orphan when its DB record
        # cannot be persisted. Restore the previous runtime copy when one was
        # backed up; otherwise remove the newly installed directory.
        try:
            if destination_path.exists():
                shutil.rmtree(destination_path, ignore_errors=True)
            if backup_path:
                backup = Path(backup_path)
                if backup.exists():
                    shutil.copytree(backup, destination_path)
        except Exception as rollback_exc:
            raise PluginImportError(
                f"插件记录写入失败且回滚失败: {rollback_exc}"
            ) from exc
        importlib.invalidate_caches()
        _discover_plugins(force_refresh=True)
        raise PluginImportError(f"插件记录写入失败，安装已回滚: {exc}") from exc

    return {
        "status": "imported",
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
        "permission_review_required": imported_record.permission_review_required,
        "missing_python_dependencies": imported_record.missing_python_dependencies,
        "migration_summary": _describe_plugin_migrations(imported_record),
        "replaced": bool(replace_existing and existing_record is not None),
        "backup_path": backup_path,
        "source_filename": filename,
    }


def _load_plugin(record: PluginRecord) -> None:
    from bot import LOGGER, bot

    if record.permission_review_required:
        raise PluginImportError(
            f"插件 {record.plugin_id} 声明了未知权限，必须完成权限审核后才能加载。"
        )
    if not record.enabled:
        raise PluginImportError(f"插件 {record.plugin_id} 当前未启用。")
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

    if not record.loaded or record.web_registered or record.web_registration_attempted or record.module is None:
        return

    register_web = getattr(record.module, "register_web", None)
    if not callable(register_web):
        return

    record.web_registration_attempted = True
    try:
        _invoke_plugin_hook(register_web, app, record)
    except Exception:
        # 失败后允许后续重新尝试注册（如插件被禁用再启用），
        # 否则一次失败会把该插件的 Web 路由永久跳过。
        record.web_registration_attempted = False
        raise
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
    with _PLUGIN_OPERATION_LOCK:
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
    payload["runtime_action"] = "restart_required" if restart_required else ("loaded" if record.loaded else "failed")
    if not record.enabled and (record.loaded or record.web_registered):
        payload["runtime_action"] = "restart_required"
    payload["container_rebuild_required"] = bool(record.requires_container_rebuild)
    return payload


def list_plugins() -> list[dict[str, Any]]:
    return [record.to_dict() for record in _discover_plugins().values()]


def list_miniapp_plugins() -> list[dict[str, Any]]:
    return [record.to_miniapp_dict() for record in _discover_plugins().values()]
