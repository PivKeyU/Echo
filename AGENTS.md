# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project overview

Echo is a Telegram bot management system for Emby media servers. It bundles a Telegram Bot (Pyrogram), FastAPI web server (admin panel + Telegram Mini App), and a runtime plugin system, all orchestrated with Docker Compose.

**Core stack**: Python 3.10, Pyrogram (TG client), FastAPI (web), SQLAlchemy + Alembic (DB), PostgreSQL, Redis, Docker Compose.

## Commands

```bash
# Python syntax check (fast, no deps needed)
python3 -m compileall main.py bot scripts

# Docker config validation
docker compose config

# Smoke checks (requires running services)
python3 scripts/smoke_checks.py

# Run with published Docker image (default user workflow)
docker compose pull && docker compose up -d

# Build and run locally (developer workflow)
docker compose up -d --build

# Rebuild a single service
docker compose up -d --build echo

# View logs
docker compose logs -f echo

# Health check
curl http://127.0.0.1:8838/health
```

No formal test suite or linter is configured. `python3 -m compileall` is the primary pre-commit check.

## Architecture

```
main.py                          # Entry point: imports modules, loads plugins, starts bot
bot/
  __init__.py                    # Config loading, Pyrogram Client init, global vars
  schemas/schemas.py             # Pydantic models for config.json validation
  web/
    __init__.py                  # FastAPI app setup, static mounts, CORS, uvicorn lifecycle
    api/__init__.py              # Route aggregation: /emby, /user, /auth, /admin-api, miniapp
    api/admin.py                 # Admin panel API (largest API file, ~57K)
    api/miniapp.py               # Telegram Mini App backend
    api/webhook/                 # Emby webhook receivers (client_filter)
    static/                      # SPA static assets (admin.html, miniapp.html)
    migration_bundle.py          # Historical migration tracking for runtime plugins
  modules/
    commands/                    # TG bot command handlers (/kk, /score, /renew, etc.)
    callback/                    # Inline keyboard callback handlers
    panel/                       # User-facing TG panel (inline keyboards, menus)
    extra/                       # Misc handlers (messages, red envelopes, etc.)
  plugins/
    __init__.py                  # Re-exports from manager
    manager.py                   # Plugin loader: discovery, ZIP import, migration, enable/disable
    xiuxian_game/                # Built-in cultivation game plugin (large)
    emby_shop/                   # Built-in Emby shop plugin
    echo_template/                 # Minimal example plugin for reference
  sql_helper/
    __init__.py                  # SQLAlchemy engine/session factory, DB startup/validation
    alembic/                     # Core Alembic migration scripts
    sql_emby.py                  # Emby user queries
    sql_xiuxian.py               # Cultivation game queries (~400K, largest file)
    sql_invite.py, sql_shop.py, sql_moderation.py, ...
  func_helper/
    emby.py                      # Emby HTTP API client (~69K, second largest helper)
    redis_cache.py               # Redis cache layer (read-through, write-invalidate)
    fix_bottons.py               # Inline keyboard builders
    moderation.py                # Group moderation logic
    emby_currency.py             # Virtual currency/integration helper
    register_queue.py            # Async registration queue (bounded, worker-based)
    ...
  scheduler/
    auto_update.py               # Docker image poll and self-update
    ranks_task.py                # Daily/weekly ranking posts
    check_ex.py                  # Expiration checks
    backup_db.py                 # DB backup
    userplays_rank.py            # Play-count ranking
    ...
  ranks_helper/                  # Ranking image generation (Pillow)
    red/                         # Red envelope logic
```

## Key conventions

- **Config**: Primary config at `data/config.json`, template at `config_example.json`. If `data/config.json` is missing on startup, it's auto-generated from the template. Config is loaded once in `bot/__init__.py` and module-level variables export common fields for import throughout the codebase.
- **Bot commands**: Telegram commands use prefixes `['/', '!', '.', '，', '。']`. Three-tier command visibility: `user_p` (everyone), `admin_p` (admins), `owner_p` (bot owner).
- **Database**: SQLAlchemy ORM with session-per-request pattern. Supports PostgreSQL (default) and MySQL. Connection pool config via environment variables (`PIVKEYU_DB_POOL_SIZE`, etc.).
- **Redis**: Used for hot-read caching of Emby user data, cultivation game settings/catalog/inventory. Write-through invalidation — cache is deleted on write, not updated. No async write-back.
- **Plugin entry points**: `register_bot(bot, context=None)` for TG handlers, `register_web(app, context=None)` for FastAPI routes. The second `context` parameter is optional (loader auto-detects signature). Plugin types: `runtime` (ZIP importable), `builtin` (shipped with repo), `core` (tightly coupled, no ZIP import).
- **Path constants**: Config resolves `data/config.json` first, falls back to legacy `config.json`. Runtime plugins live under `data/runtime_plugins/`, plugin persistent data under `data/plugin_state/<plugin_id>/`.
- **Timezone**: Hardcoded to `Asia/Shanghai`.
