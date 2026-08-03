from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"
CONFIG_EXAMPLE_PATH = ROOT / "config_example.json"
SCHEMAS_PATH = BOT_DIR / "schemas" / "schemas.py"
PLUGIN_MANAGER_PATH = BOT_DIR / "plugins" / "manager.py"


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def strip_comment_keys(value: Any):
    if isinstance(value, dict):
        return {
            key: strip_comment_keys(item)
            for key, item in value.items()
            if not key.startswith("_comment")
        }
    if isinstance(value, list):
        return [strip_comment_keys(item) for item in value]
    return value


def render_annotation(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return render_annotation(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return render_annotation(node.left) or render_annotation(node.right)
    if isinstance(node, ast.Call):
        return render_annotation(node.func)
    return None


def load_schema_models() -> tuple[dict[str, set[str]], dict[str, str]]:
    tree = ast.parse(SCHEMAS_PATH.read_text(encoding="utf-8"))
    model_fields: dict[str, set[str]] = {}
    nested_models: dict[str, str] = {}
    known_models: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases):
            continue
        known_models.add(node.name)

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in known_models:
            continue

        fields: set[str] = set()
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                fields.add(field_name)
                annotation_name = render_annotation(item.annotation)
                if annotation_name in known_models:
                    nested_models[f"{node.name}.{field_name}"] = annotation_name

        model_fields[node.name] = fields

    return model_fields, nested_models


def validate_model_keys(
    payload: dict[str, Any],
    model_name: str,
    model_fields: dict[str, set[str]],
    nested_models: dict[str, str],
    prefix: str = "",
) -> list[str]:
    errors: list[str] = []
    allowed_keys = model_fields.get(model_name, set())

    for key, value in payload.items():
        if key.startswith("_comment"):
            continue

        if key not in allowed_keys:
            errors.append(f"Unknown config key: {prefix}{key}")
            continue

        nested_model = nested_models.get(f"{model_name}.{key}")
        if nested_model and isinstance(value, dict):
            errors.extend(
                validate_model_keys(
                    value,
                    nested_model,
                    model_fields,
                    nested_models,
                    prefix=f"{prefix}{key}.",
                )
            )

    return errors


def ensure_required_keys(payload: dict[str, Any]) -> None:
    required_top_level = [
        "bot_name",
        "bot_token",
        "owner_api",
        "owner_hash",
        "owner",
        "group",
        "main_group",
        "chanel",
        "emby_api",
        "emby_url",
        "emby_line",
        "open",
        "schedall",
        "ranks",
        "moviepilot",
        "auto_update",
        "red_envelope",
        "api",
    ]

    missing = [key for key in required_top_level if key not in payload]
    if missing:
        raise RuntimeError(f"Missing required config keys: {', '.join(missing)}")


def run_compile_checks() -> None:
    python_files = sorted(
        {
            *BOT_DIR.rglob("*.py"),
            ROOT / "main.py",
            ROOT / "scripts" / "smoke_checks.py",
        }
    )
    syntax_errors: list[str] = []

    for path in python_files:
        try:
            compile(path.read_text(encoding="utf-8", errors="ignore"), str(path), "exec")
        except SyntaxError as exc:
            syntax_errors.append(f"{path}:{exc.lineno}:{exc.offset} {exc.msg}")

    if syntax_errors:
        raise RuntimeError("Python compile checks failed\n" + "\n".join(syntax_errors))


def run_config_checks() -> dict[str, Any]:
    raw_config = json.loads(CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
    model_fields, nested_models = load_schema_models()

    ensure_required_keys(raw_config)
    key_errors = validate_model_keys(raw_config, "Config", model_fields, nested_models)
    if key_errors:
        raise RuntimeError("\n".join(key_errors))

    return strip_comment_keys(raw_config)


def count_plugin_patterns(source: str) -> tuple[int, int]:
    bot_patterns = [
        re.compile(r"@[\w\.]+\.on_message"),
        re.compile(r"@[\w\.]+\.on_callback_query"),
        re.compile(r"@[\w\.]+\.on_inline_query"),
        re.compile(r"@[\w\.]+\.on_chat_member_updated"),
    ]
    web_pattern = re.compile(r"@\w+\.(get|post|put|patch|delete)\(")
    bot_count = sum(len(pattern.findall(source)) for pattern in bot_patterns)
    web_count = len(web_pattern.findall(source))
    return bot_count, web_count


def run_plugin_checks() -> dict[str, Any]:
    manager = load_module("_smoke_plugin_manager", PLUGIN_MANAGER_PATH)
    records = manager._discover_plugins()
    if not records:
        raise RuntimeError("No plugins discovered")

    enabled_plugins = 0
    bot_registration_count = 0
    web_route_count = 0

    for record in records.values():
        entry_name = record.entry.removesuffix(".py")
        entry_path = record.path / f"{entry_name}.py"
        if not entry_path.exists():
            raise RuntimeError(f"Plugin entry not found: {entry_path}")

        source = entry_path.read_text(encoding="utf-8", errors="ignore")
        compile(source, str(entry_path), "exec")
        module_ast = ast.parse(source)
        defined_functions = {
            node.name
            for node in module_ast.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        imported_functions = {
            alias.asname or alias.name
            for node in module_ast.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        entry_functions = defined_functions | imported_functions
        if "register_bot" not in entry_functions and "register_web" not in entry_functions:
            raise RuntimeError(f"Plugin has no register_bot/register_web entry: {entry_path}")

        if record.enabled:
            enabled_plugins += 1

        bot_count, web_count = count_plugin_patterns(source)
        bot_registration_count += bot_count
        web_route_count += web_count

        if record.miniapp_path and not (record.path / "static").exists():
            raise RuntimeError(f"Plugin miniapp assets directory missing: {record.path / 'static'}")

    if enabled_plugins == 0:
        raise RuntimeError("No enabled plugins were found")

    return {
        "discovered": len(records),
        "enabled": enabled_plugins,
        "bot_registrations": bot_registration_count,
        "web_routes": web_route_count,
    }


def build_feature_inventory() -> dict[str, int]:
    modules_dir = BOT_DIR / "modules"
    web_dir = BOT_DIR / "web"

    counts = {
        "message_handlers": 0,
        "callback_handlers": 0,
        "inline_handlers": 0,
        "chat_member_handlers": 0,
        "web_routes": 0,
    }

    handler_patterns = {
        "message_handlers": re.compile(r"@bot\.on_message"),
        "callback_handlers": re.compile(r"@bot\.on_callback_query"),
        "inline_handlers": re.compile(r"@bot\.on_inline_query"),
        "chat_member_handlers": re.compile(r"@bot\.on_chat_member_updated"),
    }
    route_pattern = re.compile(r"@\w+\.(get|post|put|patch|delete)\(")

    for path in modules_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key, pattern in handler_patterns.items():
            counts[key] += len(pattern.findall(text))

    for path in web_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts["web_routes"] += len(route_pattern.findall(text))

    return counts


def main() -> None:
    run_compile_checks()
    config_payload = run_config_checks()
    plugin_stats = run_plugin_checks()
    feature_stats = build_feature_inventory()

    print("Smoke checks passed.")
    print(
        json.dumps(
            {
                "config_path": str(CONFIG_EXAMPLE_PATH),
                "config_sections": sorted(
                    key for key in config_payload.keys() if not key.startswith("_comment")
                ),
                "plugins": plugin_stats,
                "features": feature_stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
