"""End-to-end import_plugin_archive tests with mocked DB layer (workflow: 插件管理器加固).

Monkeypatches RUNTIME_PLUGIN_ROOT / RUNTIME_PLUGIN_BACKUP_ROOT to temp dirs and
fakes bot.sql_helper.sql_plugin, so the whole archive-import pipeline runs without
a real database.
"""
import importlib.util
import io
import json
import stat
import sys
import tempfile
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGER = HERE.parent / "bot" / "plugins" / "manager.py"

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def raises(name, exc_type, fn, *args, **kwargs):
    global PASS, FAIL
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        PASS += 1
        print(f"  ok   {name} ({e})")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL {name} (raised {type(e).__name__}: {e})")
    else:
        FAIL += 1
        print(f"  FAIL {name} (no exception raised)")


# ---------------------------------------------------------------------------
# Fake bot.* modules so manager functions can import them lazily.
# ---------------------------------------------------------------------------
class FakeLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): print(f"[LOGGER.error] {a[0] if a else ''}")


fake_bot = types.ModuleType("bot")
fake_bot.LOGGER = FakeLogger()
fake_bot.config = types.SimpleNamespace(plugin_enabled={})
fake_bot.bot = None
sys.modules["bot"] = fake_bot

fake_sql_helper = types.ModuleType("bot.sql_helper")
fake_sql_helper.Session = None
fake_sql_helper.Base = object
sys.modules["bot.sql_helper"] = fake_sql_helper

fake_sql_plugin = types.ModuleType("bot.sql_helper.sql_plugin")
fake_sql_plugin.upsert_calls = []
fake_sql_plugin.fail_upsert = False
fake_sql_plugin.applied = {}


def fake_upsert(plugin_id, **kwargs):
    if fake_sql_plugin.fail_upsert:
        raise RuntimeError("DB down")
    fake_sql_plugin.upsert_calls.append((plugin_id, kwargs))
    return None


fake_sql_plugin.upsert_plugin_installation = fake_upsert
fake_sql_plugin.list_applied_plugin_migrations = lambda pid: dict(fake_sql_plugin.applied.get(pid, {}))
fake_sql_plugin.update_plugin_migration_checksum = lambda pid, name, cksum: True
fake_sql_plugin.mark_plugin_loaded = lambda pid: None
fake_sql_plugin.mark_plugin_error = lambda pid, err: None
sys.modules["bot.sql_helper.sql_plugin"] = fake_sql_plugin

spec = importlib.util.spec_from_file_location("plugin_manager_e2e", MANAGER)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

# ---------------------------------------------------------------------------
# Sandbox roots
# ---------------------------------------------------------------------------
TMP = Path(tempfile.mkdtemp(prefix="plugin-e2e-"))
RUNTIME = TMP / "runtime_plugins"
BACKUP = TMP / "runtime_plugin_backups"
m.RUNTIME_PLUGIN_ROOT = RUNTIME
m.RUNTIME_PLUGIN_BACKUP_ROOT = BACKUP
m._PLUGIN_BACKUP_LIMIT = 2

MANIFEST = {
    "schema_version": 1,
    "id": "e2e-demo",
    "name": "E2E Demo",
    "version": "1.0.0",
    "entry": "plugin",
    "enabled": True,
    "permissions": ["storage.plugin_data"],
}


def build_zip(entries):
    """entries: list of (arcname, bytes|None) — None means a directory entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for arcname, data in entries:
            if data is None:
                info = zipfile.ZipInfo(arcname + "/")
                zf.writestr(info, b"")
            else:
                zf.writestr(arcname, data)
    return buf.getvalue()


def legit_zip(plugin_id="e2e-demo", version="1.0.0", root="e2e_demo"):
    manifest = dict(MANIFEST, id=plugin_id, version=version)
    prefix = f"{root}/" if root else ""
    return build_zip([
        (prefix + "plugin.json", json.dumps(manifest).encode()),
        (prefix + "plugin.py", b"def register_bot(bot): pass\n"),
        (prefix + "static/index.html", b"<html>hi</html>"),
    ])


def symlink_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("plugin.json", json.dumps(MANIFEST).encode())
        zf.writestr("plugin.py", b"x = 1\n")
        info = zipfile.ZipInfo("evil_link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        info.create_system = 3
        zf.writestr(info, b"/etc/passwd")
    return buf.getvalue()


def force_encrypted(zip_bytes: bytes, name: str) -> bytes:
    """zipfile clears the encryption flag when writing; patch it back in the
    central directory so the archive looks encrypted on read."""
    data = bytearray(zip_bytes)
    pos = 0
    patched = 0
    while True:
        idx = data.find(name.encode(), pos)
        if idx < 0:
            break
        # central directory header: PK\x01\x02, flags live at header_start + 8
        header_start = idx - 46
        if header_start >= 0 and data[header_start:header_start + 4] == b"PK\x01\x02":
            flags = int.from_bytes(data[header_start + 8:header_start + 10], "little")
            data[header_start + 8:header_start + 10] = (flags | 0x1).to_bytes(2, "little")
            patched += 1
        pos = idx + len(name)
    if not patched:
        raise RuntimeError("failed to patch encryption flag")
    return bytes(data)


def encrypted_zip():
    return force_encrypted(
        build_zip([("plugin.json", json.dumps(MANIFEST).encode()), ("plugin.py", b"x = 1\n")]),
        "plugin.json",
    )


# ---------------------------------------------------------------------------
# 1. Traversal and hostile archives are rejected
# ---------------------------------------------------------------------------
print("[1] hostile archives rejected")

raises("traversal ../evil.py", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", b"{}"), ("plugin.py", b""), ("../evil.py", b"x")]), "evil.zip")
raises("absolute /etc/passwd", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", b"{}"), ("/etc/passwd", b"x")]), "evil.zip")
raises("windows drive C:\\x", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", b"{}"), ("C:\\x\\y.py", b"x")]), "evil.zip")
raises("symlink member", m.PluginImportError, m.import_plugin_archive, symlink_zip(), "evil.zip")
raises("encrypted member", m.PluginImportError, m.import_plugin_archive, encrypted_zip(), "evil.zip")
raises("duplicate path", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", b"{}"), ("plugin.json", b"{}")]), "dup.zip")
raises("file/dir prefix conflict", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", b"{}"), ("plugin.py", b"x"), ("x", b"file"), ("x/y.py", b"z")]), "conflict.zip")
raises("no plugin.json", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.py", b"x")]), "nomanifest.zip")
raises("multi top dirs", m.PluginImportError, m.import_plugin_archive,
       build_zip([("a/plugin.json", b"{}"), ("b/plugin.py", b"x")]), "multi.zip")
raises("empty archive", m.PluginImportError, m.import_plugin_archive, b"", "empty.zip")
raises("not a zip", m.PluginImportError, m.import_plugin_archive, b"PK\x03\x04garbage", "bad.zip")
raises("missing entry module", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", json.dumps(dict(MANIFEST, entry="nope")).encode())]), "noentry.zip")
raises("invalid id", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", json.dumps(dict(MANIFEST, id="../evil")).encode())]), "badid.zip")
raises("core type runtime import", m.PluginImportError, m.import_plugin_archive,
       build_zip([("plugin.json", json.dumps(dict(MANIFEST, plugin_type="core")).encode()),
                  ("plugin.py", b"x")]), "core.zip")

print("[1b] clean rejection leaves no residue")
check("runtime root still empty", not any(RUNTIME.iterdir()))
check("backup root still empty", not any(BACKUP.iterdir()))

print("[1c] unknown permissions -> review required")

result = m.import_plugin_archive(
    build_zip([("plugin.json", json.dumps(dict(MANIFEST, id="e2e-perm", permissions=["telegram.hack"])).encode()),
               ("plugin.py", b"x")]), "perm.zip")
check("unknown permission -> review required", result.get("permission_review_required") is True, str(result))
check("unknown permission -> manifest disabled", result.get("manifest_enabled") is False, str(result))
raises("unknown permission plugin cannot be force-loaded", m.PluginImportError, m._load_plugin,
       m._discover_plugins(force_refresh=True)["e2e-perm"])

# ---------------------------------------------------------------------------
# 2. Legit archive imports
# ---------------------------------------------------------------------------
print("[2] legit archive import")

fake_sql_plugin.upsert_calls = []
result = m.import_plugin_archive(legit_zip(), "demo.zip")
check("imported ok", result["status"] == "imported" and result["plugin_id"] == "e2e-demo", str(result))
check("permissions preserved", result["permissions"] == ["storage.plugin_data"])
check("no unknown permissions", result["unknown_permissions"] == [])
check("plugin.json written", (RUNTIME / "e2e_demo" / "plugin.json").exists())
check("plugin.py written", (RUNTIME / "e2e_demo" / "plugin.py").exists())
check("static asset written", (RUNTIME / "e2e_demo" / "static" / "index.html").read_bytes() == b"<html>hi</html>")
check("persisted once", len(fake_sql_plugin.upsert_calls) == 1)
check("upsert enabled True", fake_sql_plugin.upsert_calls[0][1]["enabled"] is True)

raises("reimport without replace rejected", m.PluginImportError, m.import_plugin_archive, legit_zip(), "demo.zip")
raises("imported plugin not loadable-> still rejected", m.PluginImportError, m.import_plugin_archive, legit_zip(), "demo.zip", replace_existing=False)

# ---------------------------------------------------------------------------
# 3. replace_existing + backup rotation
# ---------------------------------------------------------------------------
print("[3] replace_existing + backup rotation")

result = m.import_plugin_archive(legit_zip(version="1.1.0"), "demo.zip", replace_existing=True)
check("replaced ok", result["replaced"] is True, str(result))
backup_dir = BACKUP / "e2e-demo"
backups = sorted(backup_dir.iterdir()) if backup_dir.exists() else []
check("backup created", len(backups) == 1, str(backups))
check("backup has old version", "1.0.0" in backups[0].name)
check("backup contains old files", (backups[0] / "plugin.py").exists())
check("new version on disk", (RUNTIME / "e2e_demo" / "plugin.json").read_text(encoding="utf-8").find("1.1.0") >= 0)

result = m.import_plugin_archive(legit_zip(version="1.2.0"), "demo.zip", replace_existing=True)
result = m.import_plugin_archive(legit_zip(version="1.3.0"), "demo.zip", replace_existing=True)
backups = sorted(backup_dir.iterdir())
check("backup rotation capped at 2", len(backups) == 2, f"{len(backups)} backups")

# ---------------------------------------------------------------------------
# 4. Dir-name collision protections
# ---------------------------------------------------------------------------
print("[4] dir name collision protections")

# Same dir name, different plugin id must be rejected
raises("different id same dir name rejected", m.PluginImportError, m.import_plugin_archive,
       legit_zip(plugin_id="e2e-other", root="e2e_demo"), "other.zip")
# A second plugin with a different id must not clobber
result = m.import_plugin_archive(legit_zip(plugin_id="e2e-second", version="0.1.0", root="e2e_second"), "second.zip")
check("second plugin imported", result["plugin_id"] == "e2e-second")

# ---------------------------------------------------------------------------
# 5. DB persist failure -> rollback
# ---------------------------------------------------------------------------
print("[5] DB persist failure rollback")

fake_sql_plugin.fail_upsert = True
raises("persist failure raises", m.PluginImportError, m.import_plugin_archive,
       legit_zip(plugin_id="e2e-rollback", version="0.1.0", root="e2e_rollback"), "rollback.zip")
check("rolled-back dir removed", not (RUNTIME / "e2e_rollback").exists())

# Replace-failure rollback restores previous copy (still failing DB)
raises("replace persist failure raises", m.PluginImportError, m.import_plugin_archive,
       legit_zip(plugin_id="e2e-demo", version="9.9.9"), "demo.zip", replace_existing=True)
check("previous version restored on rollback",
      (RUNTIME / "e2e_demo" / "plugin.json").read_text(encoding="utf-8").find("9.9.9") < 0)
fake_sql_plugin.fail_upsert = False

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(1 if FAIL else 0)
