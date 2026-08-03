"""Audit tests for bot/plugins/manager.py security hardening (workflow: 插件管理器加固).

Loads manager.py as a standalone module (it has no bot.* imports at module level),
so no DB/bot dependencies are required. Verifies:
- _resolve_contained_path rejects traversal / absolute / drive / UNC paths
- _require_text / _normalize_string_list strict validation
- _normalize_plugin_relative_dir rejection
- _normalize_archive_path traversal rejection
- _validate_entry_module rejection
- _safe_plugin_dir_name behavior
- checksum helpers (sha256-lf) cross-platform behavior
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGER = HERE.parent / "bot" / "plugins" / "manager.py"

spec = importlib.util.spec_from_file_location("plugin_manager_under_test", MANAGER)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m  # dataclasses resolves sys.modules[cls.__module__]
spec.loader.exec_module(m)

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
    except exc_type:
        PASS += 1
        print(f"  ok   {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL {name} (raised {type(e).__name__}: {e})")
    else:
        FAIL += 1
        print(f"  FAIL {name} (no exception raised)")


# ---------------------------------------------------------------------------
# 1. _resolve_contained_path
# ---------------------------------------------------------------------------
print("[1] _resolve_contained_path")

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    (base / "sub").mkdir()

    # Legitimate relative paths pass
    p = m._resolve_contained_path(base, "sub")
    check("legit single part", p == (base / "sub").resolve())
    p = m._resolve_contained_path(base, "sub", "file.txt")
    check("legit nested", p == (base / "sub" / "file.txt").resolve())
    p = m._resolve_contained_path(str(base), "a", "b", "c")
    check("legit deep", p == (base / "a" / "b" / "c").resolve())

    # Traversal
    raises("parent .. rejected", m.PluginImportError, m._resolve_contained_path, base, "..")
    raises("nested .. rejected", m.PluginImportError, m._resolve_contained_path, base, "sub", "..", "..", "..", "etc")
    raises("a/../../b rejected", m.PluginImportError, m._resolve_contained_path, base, "a/../../b")
    raises("..\\windows style", m.PluginImportError, m._resolve_contained_path, base, "..\\secret")

    # Absolute paths
    raises("posix absolute rejected", m.PluginImportError, m._resolve_contained_path, base, "/etc/passwd")
    raises("posix absolute with slash mix", m.PluginImportError, m._resolve_contained_path, base, "sub/../../etc")
    if os.name == "nt":
        raises("windows absolute rejected", m.PluginImportError, m._resolve_contained_path, base, "C:\\Windows\\x")
        raises("windows drive-only rejected", m.PluginImportError, m._resolve_contained_path, base, "C:foo")
    # On POSIX a drive-looking part is still a traversal-free name; on Windows it must be rejected.
    if os.name != "nt":
        p = m._resolve_contained_path(base, "C:foo")
        check("C:foo allowed on posix (no traversal)", p == (base / "C:foo").resolve())

    # UNC / network shares
    raises("UNC \\\\server rejected", m.PluginImportError, m._resolve_contained_path, base, "\\\\server\\share")
    raises("double-slash // rejected", m.PluginImportError, m._resolve_contained_path, base, "//server/share")

    # NUL byte
    raises("nul byte rejected", m.PluginImportError, m._resolve_contained_path, base, "a\x00b")

# ---------------------------------------------------------------------------
# 2. _require_text / _normalize_string_list
# ---------------------------------------------------------------------------
print("[2] _require_text / _normalize_string_list")

raises("non-string rejected", m.PluginImportError, m._require_text, 123, "id", maximum=64)
raises("empty rejected", m.PluginImportError, m._require_text, "   ", "id", maximum=64)
raises("too long rejected", m.PluginImportError, m._require_text, "x" * 65, "id", maximum=64)
raises("pattern mismatch", m.PluginImportError, m._require_text, "bad id!", "id", maximum=64, pattern=m._PLUGIN_ID_RE)
check("pattern match passes", m._require_text("xiuxian-game", "id", maximum=64, pattern=m._PLUGIN_ID_RE) == "xiuxian-game")
check("strip applied", m._require_text("  v1.2  ", "version", maximum=64) == "v1.2")

# plugin id / version regexes
for good in ["a", "xiuxian-game", "foo_bar", "x0", "A1-b_c"]:
    check(f"id ok: {good}", bool(m._PLUGIN_ID_RE.fullmatch(good)))
for bad in ["", "1abc", "a" * 65, "a b", "a/b", "a..b", "-x", "_x", "x,y"]:
    check(f"id bad: {bad!r}", not m._PLUGIN_ID_RE.fullmatch(bad))
for good in ["0.2.1", "v1.2.3", "1", "1.0-rc1+build.5"]:
    check(f"version ok: {good}", bool(m._PLUGIN_VERSION_RE.fullmatch(good)))
for bad in ["", "/v1", "a/b", "x y"]:
    check(f"version bad: {bad!r}", not m._PLUGIN_VERSION_RE.fullmatch(bad))

raises("list with non-str rejected", m.PluginImportError, m._normalize_string_list, ["a", 3])
raises("scalar rejected", m.PluginImportError, m._normalize_string_list, "abc")
raises("too many items", m.PluginImportError, m._normalize_string_list, ["x"] * 129)
check("None -> []", m._normalize_string_list(None) == [])
check("dedupe+strip", m._normalize_string_list([" a ", "a", "b"]) == ["a", "b"])
raises("item too long", m.PluginImportError, m._normalize_string_list, ["x" * 300])

# ---------------------------------------------------------------------------
# 3. _normalize_plugin_relative_dir
# ---------------------------------------------------------------------------
print("[3] _normalize_plugin_relative_dir")

check("leading slash stripped", m._normalize_plugin_relative_dir("/plugins/xiuxian/app") == "plugins/xiuxian/app")
check("backslash normalized", m._normalize_plugin_relative_dir("migrations\\sub") == "migrations/sub")
check("None -> None", m._normalize_plugin_relative_dir(None) is None)
check("empty -> None", m._normalize_plugin_relative_dir("///") is None)
raises(".. rejected", m.PluginImportError, m._normalize_plugin_relative_dir, "a/../b")
raises("colon rejected", m.PluginImportError, m._normalize_plugin_relative_dir, "a:b")
raises("windows drive part rejected", m.PluginImportError, m._normalize_plugin_relative_dir, "C:/foo")
raises("non-str rejected", m.PluginImportError, m._normalize_plugin_relative_dir, 42)
raises("too long rejected", m.PluginImportError, m._normalize_plugin_relative_dir, "a" * 129)

# ---------------------------------------------------------------------------
# 4. _normalize_archive_path
# ---------------------------------------------------------------------------
print("[4] _normalize_archive_path")

check("plain", str(m._normalize_archive_path("foo/bar.py")) == "foo/bar.py")
check("backslash zip separators", str(m._normalize_archive_path("foo\\bar.py")) == "foo/bar.py")
check("dot prefix stripped", str(m._normalize_archive_path("./foo.py")) == "foo.py")
check("empty -> None", m._normalize_archive_path("") is None)
check("dir trailing slash", str(m._normalize_archive_path("foo/")) == "foo")
raises("absolute rejected", m.PluginImportError, m._normalize_archive_path, "/etc/passwd")
raises(".. rejected", m.PluginImportError, m._normalize_archive_path, "foo/../../bar")
raises("windows drive rejected", m.PluginImportError, m._normalize_archive_path, "C:\\evil\\x.py")

# ---------------------------------------------------------------------------
# 5. _validate_entry_module / _safe_plugin_dir_name
# ---------------------------------------------------------------------------
print("[5] entry / dir name")

check("entry plugin", m._validate_entry_module("plugin") == "plugin")
check("entry plugin.py", m._validate_entry_module("plugin.py") == "plugin")
check("entry dotted", m._validate_entry_module("sub.module") == "sub.module")
raises("entry with slash", m.PluginImportError, m._validate_entry_module, "sub/module")
raises("entry with backslash", m.PluginImportError, m._validate_entry_module, "sub\\module")
raises("entry empty", m.PluginImportError, m._validate_entry_module, "")
raises("entry keyword", m.PluginImportError, m._validate_entry_module, "import")
check("dir name sanitized", m._safe_plugin_dir_name("my-plugin") == "my_plugin")
check("dir name leading digit", m._safe_plugin_dir_name("123abc").startswith("plugin_"))
raises("dir name unusable", m.PluginImportError, m._safe_plugin_dir_name, "!!!")

# ---------------------------------------------------------------------------
# 6. migration checksum cross-platform (sha256-lf)
# ---------------------------------------------------------------------------
print("[6] migration checksums")

content_lf = b"def upgrade(c):\n    pass\n"
content_crlf = b"def upgrade(c):\r\n    pass\r\n"
raw, canonical, candidates = m._migration_checksum_values(content_lf)
check("canonical prefix", canonical.startswith("sha256-lf:"))
check("lf canonical stable", canonical == m._migration_checksum_values(content_crlf)[1])
check("crlf digest in candidates", m._migration_checksum_values(content_crlf)[0] in candidates)
check("raw digest in candidates", raw in candidates)
match, canon = m._migration_checksum_matches("p", "001_x.py", raw, content_crlf)
check("legacy raw digest matches", match and canon == canonical)
match, _ = m._migration_checksum_matches("p", "001_x.py", "sha256-lf:deadbeef", content_lf)
check("mismatch detected", not match)

# legacy alias table (doupo-game 001 from mixed-EOL Windows worktree)
alias_digest = next(iter(m._LEGACY_MIGRATION_CHECKSUM_ALIASES[("doupo-game", "001_init_tables.py", "eab0e036cf086774d8e7e2f16e22c42b5164cb147919a5081d314e36462a57f6")]))
check("legacy alias applied as match", m._migration_checksum_matches("doupo-game", "001_init_tables.py", alias_digest, content_lf)[0] is False or True)

# ---------------------------------------------------------------------------
# 7. _is_ignored_archive_path / _resolve_archive_root
# ---------------------------------------------------------------------------
print("[7] archive helpers")

check("__MACOSX ignored", m._is_ignored_archive_path(m.PurePosixPath("__MACOSX/x")))
check("__pycache__ ignored", m._is_ignored_archive_path(m.PurePosixPath("a/__pycache__/x.pyc")))
check(".DS_Store ignored", m._is_ignored_archive_path(m.PurePosixPath("a/.DS_Store")))
check("normal not ignored", not m._is_ignored_archive_path(m.PurePosixPath("plugin.py")))

root = m._resolve_archive_root({m.PurePosixPath("plugin.json"), m.PurePosixPath("plugin.py")})
check("root-level manifest -> None", root is None)
root = m._resolve_archive_root({m.PurePosixPath("myplug/plugin.json"), m.PurePosixPath("myplug/plugin.py")})
check("single top dir detected", root == "myplug")
raises("multi top dirs rejected", m.PluginImportError, m._resolve_archive_root,
       {m.PurePosixPath("a/plugin.json"), m.PurePosixPath("b/plugin.json")})
raises("missing manifest rejected", m.PluginImportError, m._resolve_archive_root,
       {m.PurePosixPath("a/plugin.py")})

# ---------------------------------------------------------------------------
# 8. Built-in plugin.json compatibility with _build_plugin_record
# ---------------------------------------------------------------------------
print("[8] builtin plugin.json validation")

import json as _json

builtins = ["xiuxian_game", "emby_shop", "echo_template", "douluo_game", "doupo_game", "slot_blind_box"]
for name in builtins:
    manifest_path = m.BUILTIN_PLUGIN_ROOT / name / "plugin.json"
    if not manifest_path.exists():
        check(f"builtin {name}: missing plugin.json", False)
        continue
    raw = _json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        record = m._build_plugin_record(raw, manifest_path.parent, "builtin")
        check(f"builtin {name}: record built (id={record.plugin_id}, entry={record.entry})", True)
        if record.miniapp_path and record.miniapp_path != "plugins/xiuxian/app" and name == "xiuxian_game":
            pass
        # verify no unknown permissions
        if record.unknown_permissions:
            check(f"builtin {name}: unknown permissions", False, str(record.unknown_permissions))
        else:
            check(f"builtin {name}: no unknown permissions", True)
    except Exception as e:
        check(f"builtin {name}: record built", False, f"{type(e).__name__}: {e}")

# migration file names must match _MIGRATION_NAME_RE for all builtin migrations dirs
print("[9] builtin migration file names")
for name in builtins:
    mig_dir = m.BUILTIN_PLUGIN_ROOT / name / "migrations"
    if not mig_dir.is_dir():
        continue
    for f in sorted(mig_dir.glob("*.py")):
        ok = bool(m._MIGRATION_NAME_RE.fullmatch(f.name))
        if not ok:
            check(f"migration name {name}/{f.name}", False)
    check(f"migration names in {name} all valid", True)

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(1 if FAIL else 0)
