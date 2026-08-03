# Echo Plugin Guide

插件目录结构：

```text
运行时插件（推荐，多开发者协作时优先）：
data/runtime_plugins/<your_plugin>/
├── plugin.json
├── plugin.py
├── static/           # 可选，Mini App / 后台静态资源
└── migrations/       # 可选，插件专属数据库迁移

内置插件（随镜像/仓库发版）：
bot/plugins/<your_plugin>/
├── plugin.json
├── plugin.py
└── static/
```

`plugin.json` 推荐示例：

```json
{
  "schema_version": 2,
  "id": "xiuxian-game",
  "name": "修仙玩法",
  "version": "0.1.0",
  "description": "示例：独立玩法插件",
  "entry": "plugin",
  "enabled": true,
  "plugin_type": "runtime",
  "requires_restart": false,
  "permissions": [
    "telegram.commands",
    "web.routes",
    "database.plugin_migrations",
    "database.plugin_tables"
  ],
  "dependencies": {
    "python": []
  },
  "database": {
    "migrations_dir": "migrations"
  }
}
```

`plugin.py` 可选入口：

```python
from fastapi import APIRouter
from pyrogram import filters

from bot import prefixes


def register_bot(bot, context=None) -> None:
    @bot.on_message(filters.command("plugin_ping", prefixes))
    async def plugin_ping(_, msg):
        await msg.reply_text("plugin ok")


def register_web(app, context=None) -> None:
    router = APIRouter(prefix="/plugins/template", tags=["Template"])

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    app.include_router(router)
```

约定：

- 运行时插件会安装到 `data/runtime_plugins/`，Docker 重建后仍然保留
- `enabled: true` 时，程序会在 **Bot 启动阶段**（`main.py`）自动装载插件的 TG 指令与回调
- 若同时启用了 Web API（`api.status = true`），还会在 FastAPI 启动时注册插件 Web 路由
- `register_bot(bot, context)` 用于注册 bot 指令、回调或事件；第二个参数 `context` 可选
- `register_web(app, context)` 用于暴露 FastAPI 路由；第二个参数 `context` 可选
- 已加载和未启用的插件都会出现在 `/admin` 面板的插件区
- 插件自带的 `migrations/*.py` 会在加载前自动执行一次，系统会记录已执行历史
- 修改已执行过的迁移文件内容是不允许的；请新增新的迁移文件
- 插件声明了额外 Python 依赖时，需要在本地构建模式下重建容器，构建阶段会自动安装这些依赖
- `plugin_type=core` 仅适合随仓库和镜像一起发布，不支持后台 ZIP 运行时导入
- 仓库内置了 `echo_template` 样例插件，可用于快速验活

Docker 环境下推荐分成两种流程：

### 1. 默认镜像模式

适用场景：

- 插件没有额外 Python 依赖
- 插件只是纯 Python 逻辑、TG 指令或 Web 页面

流程：

1. 在 `/admin` 上传新的插件 ZIP
2. 如果后台没有提示 `container_rebuild_required`，插件会在下一次加载流程中直接启用

### 2. 本地构建模式

适用场景：

- `dependencies.python` 不为空
- 插件需要第三方 Python 包
- 插件需要系统依赖或编译型依赖

建议额外创建 `docker-compose.override.yml`：

```yaml
services:
  echo:
    build:
      context: .
      dockerfile: Dockerfile
    image: echo:local
    pull_policy: never
```

然后执行：

```bash
docker compose up -d --build echo
```

容器启动后，系统会自动执行插件依赖安装、数据库迁移与插件加载。

如果你只想看完整说明，直接回到仓库根 README 的“插件开发流程”章节。

当前仓库内已经落地的修仙插件手册见：

- `bot/plugins/xiuxian_game/README.md`
