# pivkeyu_emby

pivkeyu_emby 是一个面向 Emby 服主的 Telegram 管理系统，核心栈为 Telegram Bot + FastAPI + PostgreSQL + Redis + Docker Compose。

它不是只停留在 TG 指令层的 Emby 机器人，而是把以下几件事一起做完整了：

- 机器人用户功能
- Web 管理后台 ` /admin `
- Telegram Mini App ` /miniapp `
- 插件系统，包括运行时导入、权限声明、数据库迁移、依赖检测
- 面向 Docker Compose 的日常部署与升级流程

如果你最关心的是怎么部署，直接看 [Docker Compose 安装](#docker-compose-安装)。
如果你最关心的是怎么扩展，直接看 [插件开发流程](#插件开发流程)。

## 为什么选 pivkeyu_emby

- 默认使用已发布的 Docker Hub 镜像，常规部署不需要本地先 `docker build`
- 自带 Web 管理后台和 Telegram Mini App，不需要再单独补一套 Web 面板
- 插件不只是命令扩展，还可以挂 Web 路由、静态资源、Mini App 页面、后台页面
- 运行时插件支持 ZIP 导入、数据库迁移记录、依赖检查、启停开关
- `data/` 会持久化配置、运行时插件、插件状态，重建容器后不会丢
- Compose 内置 PostgreSQL、Redis、Caddy、健康检查和一组默认性能参数，开箱即可跑

## 相较于 Sakura_embyboss 的区别

下面这张表说的是两者当前公开文档里最直观的使用体验差异，不是“谁绝对更强”，而是项目定位不同。

| 维度 | Sakura_embyboss 官方文档主流程 | pivkeyu_emby |
| --- | --- | --- |
| Docker 部署入口 | 以拉源码、复制 `config.json`、在项目目录执行 `docker-compose up -d` 为主 | 默认直接使用 Docker Hub 镜像，`docker compose pull && docker compose up -d` 即可 |
| 配置持久化 | 主要映射单个 `config.json` 和 `log/` | 默认持久化 `data/`、`log/`、`db/`，运行时插件和插件状态也一起保留 |
| Web 能力 | 项目简介里仍写着 “敬请期待 重写 + web操作” | 已经落地 `/admin`、`/miniapp`、插件后台页、插件 Mini App 页 |
| 插件开发 | 公开文档重点仍在 bot 本体部署与配置 | 提供 manifest、权限声明、运行时 ZIP 导入、迁移记录、依赖检测、Mini App 元信息 |
| 反代与入口 | 文档主要聚焦 Bot 和 Compose 本身 | 默认附带 Caddy 反代，适合直接挂 HTTPS 域名 |
| 发版方式 | 更偏源码使用和镜像拉取混合 | 更偏“官方镜像给使用者，源码仓库给开发者和插件作者” |

如果你只是想要一个 TG Emby Bot，Sakura_embyboss 仍然是一个成熟选项。
如果你想要的是“Bot + Web 管理台 + Mini App + 插件扩展”的一体化方案，pivkeyu_emby 更直接。

## Docker Compose 安装

### 1. 准备条件

- Linux 服务器，推荐直接使用 Docker Compose
- Docker Engine 和 Docker Compose v2
- 一个可用的 Telegram Bot
- Telegram `api_id` / `api_hash`
- Emby 管理员 API Key
- 一个外网 HTTPS 域名，如果你要启用 Web 后台和 Mini App

### 2. 获取项目

```bash
git clone https://github.com/PivKeyU/Pivkeyu_emby.git
cd Pivkeyu_emby
```

### 3. 初始化目录

```bash
mkdir -p data log db caddy/data caddy/config
cp config_example.json data/config.json
```

说明：

- 程序优先读取 `data/config.json`
- `docker-compose.yml` 默认使用 `pivkeyu/pivkeyu_emby:latest`
- PostgreSQL 数据会写到 `./db`
- 运行时插件会写到 `./data/runtime_plugins`

### 4. 修改 `data/config.json`

至少先把这些字段替换成你自己的：

- `bot_name`
- `bot_token`
- `owner_api`
- `owner_hash`
- `owner`
- `group`
- `main_group`
- `chanel`
- `emby_api`
- `emby_url`
- `emby_line`

如果你要启用 Web 后台和 Mini App，还必须配置：

- `api.status = true`
- `api.public_url`
- `api.access_token`
- `api.admin_token`

最常见的 Web 配置示例：

```json
"api": {
  "status": true,
  "http_url": "0.0.0.0",
  "http_port": 8838,
  "public_url": "https://bot.example.com",
  "miniapp_title": "片刻面板",
  "access_token": "replace_with_a_separate_api_access_token",
  "admin_token": "replace_with_a_long_random_admin_token",
  "webapp_auth_max_age": 86400,
  "allow_origins": ["https://bot.example.com"]
}
```

`access_token` 用于 Emby Webhook 及普通 API，`admin_token` 只用于后台管理；两者必须不同，且只能通过请求头传递。`allow_origins` 必须填写实际访问后台的站点来源，不再支持 `*`。

### 5. 可选：配置 Caddy 域名

如果你要直接使用仓库自带的 Caddy，可以创建 `.env`：

```bash
cat > .env <<'EOF'
PIVKEYU_PUBLIC_DOMAIN=bot.example.com
PIVKEYU_UPSTREAM=127.0.0.1:8838
EOF
```

如果你自己有 Nginx、Traefik、Cloudflare Tunnel 或其他反代，也可以不用仓库里的 Caddy 服务。

### 6. 启动服务

```bash
docker compose pull
docker compose up -d
```

如果你改过当前仓库源码，改用下面这条命令把本地修改重新打进镜像：

```bash
docker compose up -d --build
```

默认会启动：

- `postgres`
- `redis`
- `pivkeyu_emby`
- `pivkeyu-caddy`

### 7. 验证服务

查看容器状态：

```bash
docker compose ps
```

查看应用日志：

```bash
docker compose logs -f pivkeyu_emby
```

健康检查：

```bash
curl http://127.0.0.1:8838/health
```

如果启用了默认 Compose 配置，`/health` 也会返回 Redis 的启用和连通状态，方便确认缓存层是否已经接管热点查询。

当前 Redis 主要用于热点读缓存，不做异步写回。除了 Emby 账户查询外，修仙插件的设置、基础目录数据、背包/已装备/称号等高频读取也会优先命中 Redis；写操作提交后会主动失效对应缓存，避免长时间脏读。

默认入口：

- `http://127.0.0.1:8838/admin`
- `http://127.0.0.1:8838/miniapp`
- `https://你的域名/admin`
- `https://你的域名/miniapp`

## Docker Compose 升级

标准升级方式：

```bash
docker compose pull
docker compose up -d --force-recreate
```

如果你在当前仓库里做了二开，升级本地改动时建议使用：

```bash
docker compose up -d --build --force-recreate
```

如果你只想更新主应用：

```bash
docker compose pull pivkeyu_emby
docker compose up -d --force-recreate pivkeyu_emby
```

升级后可以确认容器到底跑的是哪个镜像：

```bash
docker inspect pivkeyu_emby --format '{{.Config.Image}}'
```

正常应该看到：

```text
pivkeyu/pivkeyu_emby:latest
```

## Docker Hub 发布

仓库已经内置 GitHub Actions 发布流程，分成两条线：

- 推送到 `master` 或 `main` 时，自动构建并发布 `latest`
- 发布 GitHub Release 时，自动构建并发布对应的版本号标签

两条流程都会同时构建 `linux/amd64` 和 `linux/arm64`。

你只需要在仓库的 GitHub Secrets 里配置：

- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`

默认镜像名是：

```text
${DOCKER_USERNAME}/pivkeyu_emby
```

如果你要在本地直接手动发布双架构镜像，可以使用：

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t pivkeyu/pivkeyu_emby:latest \
  --push .
```

## 目录与持久化说明

```text
.
├── bot/                         # 主代码、Web、插件、数据库逻辑
├── caddy/                       # Caddy 反代配置
├── data/                        # 配置、运行时插件、插件状态、session
│   ├── config.json
│   ├── runtime_plugins/
│   └── plugin_state/
├── db/                          # PostgreSQL 数据目录
├── log/                         # 日志目录
├── mysql/                       # 兼容旧 MySQL 部署保留的配置目录
├── scripts/                     # 冒烟检查和辅助脚本
├── config_example.json          # 配置模板
├── docker-compose.yml           # 默认镜像部署编排
└── Dockerfile                   # 本地构建或自定义镜像时使用
```

重点记住：

- `data/config.json` 是你的主配置
- `data/runtime_plugins/` 是运行时插件目录
- `data/plugin_state/` 是插件自己的持久化数据目录
- `db/` 和 `log/` 也应该保留，不建议随便删

## 插件开发流程

这一节是本项目和普通 Emby TG Bot 差别最大的地方。

你开发的插件不只可以加 TG 指令，还可以：

- 提供 FastAPI 路由
- 提供独立 Mini App 页面
- 提供插件后台页面
- 声明数据库迁移
- 声明 Python 依赖

### 1. 先区分三种插件形态

- `runtime`：推荐，支持后台上传 ZIP，适合大多数功能扩展
- `builtin`：随仓库源码一起维护，适合仓库内置功能
- `core`：强耦合核心插件，不适合运行时 ZIP 导入

### 2. 目录结构

推荐的运行时插件目录：

```text
data/runtime_plugins/<your_plugin>/
├── plugin.json
├── plugin.py
├── static/          # 可选，插件自己的静态资源
└── migrations/      # 可选，插件专属数据库迁移
```

仓库内置插件目录：

```text
bot/plugins/<your_plugin>/
├── plugin.json
├── plugin.py
└── static/
```

最快的起步方式是直接参考样例插件：

- [bot/plugins/pivkeyu_template](bot/plugins/pivkeyu_template)
- [bot/plugins/xiuxian_game](bot/plugins/xiuxian_game)

### 3. 编写 `plugin.json`

一个较完整的示例：

```json
{
  "schema_version": 2,
  "id": "hello-plugin",
  "name": "示例插件",
  "version": "0.1.0",
  "description": "最小可用插件示例",
  "entry": "plugin",
  "enabled": true,
  "plugin_type": "runtime",
  "permissions": [
    "telegram.commands",
    "web.routes",
    "web.static",
    "database.plugin_migrations"
  ],
  "dependencies": {
    "python": []
  },
  "database": {
    "migrations_dir": "migrations"
  },
  "miniapp": {
    "path": "/plugins/hello/app",
    "admin_path": "/plugins/hello/admin",
    "label": "Hello",
    "icon": "✨",
    "bottom_nav_default": true
  }
}
```

几个关键字段：

- `id`：插件唯一标识，不要和其他插件冲突
- `entry`：入口模块名，默认就是 `plugin`
- `permissions`：声明插件会使用哪些能力
- `dependencies.python`：额外 Python 依赖列表
- `database.migrations_dir`：迁移目录
- `miniapp.path`：插件 Mini App 路径
- `miniapp.admin_path`：插件后台路径

### 4. 编写 `plugin.py`

最小示例：

```python
from fastapi import APIRouter
from pyrogram import filters

from bot import prefixes


def register_bot(bot, context=None) -> None:
    @bot.on_message(filters.command("plugin_ping", prefixes))
    async def plugin_ping(_, msg):
        await msg.reply_text("plugin ok")


def register_web(app, context=None) -> None:
    router = APIRouter(prefix="/plugins/hello", tags=["Hello Plugin"])

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    app.include_router(router)
```

说明：

- `register_bot(bot, context=None)`：注册 TG 指令、回调、事件
- `register_web(app, context=None)`：注册 FastAPI 路由
- 第二个参数 `context` 是可选的，插件管理器会自动兼容

### 5. 如果插件需要 Mini App / 后台页

你可以在 `plugin.json` 里声明：

- `miniapp.path`
- `miniapp.admin_path`
- `miniapp.label`
- `miniapp.icon`

然后在 `register_web()` 中自己挂载静态资源和页面路由。

仓库里的修仙插件就是一个完整例子：

- 用户页：`/plugins/xiuxian/app`
- 后台页：`/plugins/xiuxian/admin`

### 6. 如果插件需要数据库迁移

把迁移脚本放到 `migrations/` 目录，格式类似：

```python
def upgrade(connection):
    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS hello_plugin_records (id INTEGER PRIMARY KEY)"
    )
```

迁移规则：

- 系统会在插件加载前自动执行未执行过的迁移
- 已执行过的迁移文件不能改内容
- 如果逻辑有变化，请新增一个迁移文件，不要覆盖旧文件

### 7. 插件自己的持久化数据放哪里

每个插件都会拿到独立目录：

```text
data/plugin_state/<plugin_id>/
```

适合存：

- 插件自己的缓存
- 插件自己的 JSON 配置
- 导入文件、临时文件、生成结果

### 8. 开发、打包、导入

推荐流程：

1. 先从 `bot/plugins/pivkeyu_template` 复制一个最小插件
2. 在本地调通 `plugin.json` 和 `plugin.py`
3. 如果是运行时插件，把压缩包根目录做成：

```text
your_plugin.zip
├── plugin.json
├── plugin.py
├── static/
└── migrations/
```

4. 到 `/admin` 后台上传 ZIP
5. 根据后台提示决定是“直接启用”还是“需要本地构建模式”

### 9. 什么时候可以直接热更新，什么时候必须本地构建

可以直接上传并启用：

- 没有额外 Python 依赖
- 不依赖系统级库
- 只是新增 TG 指令、Web 路由、静态页面、纯 Python 逻辑

建议切换到本地构建模式：

- `dependencies.python` 不为空
- 需要 `pip install` 第三方库
- 需要系统库、编译型依赖或额外二进制支持

### 10. 插件开发推荐的 Compose 本地构建模式

默认 `docker-compose.yml` 是“直接拉官方镜像”的使用者模式。

如果你在开发插件，建议额外创建一个 `docker-compose.override.yml`：

```yaml
services:
  pivkeyu_emby:
    build:
      context: .
      dockerfile: Dockerfile
    image: pivkeyu_emby:local
    pull_policy: never
```

然后用这套命令：

```bash
docker compose up -d --build pivkeyu_emby
```

这样容器在构建时会自动执行：

- 运行时插件依赖安装
- 代码打包进镜像
- 启动后自动插件迁移

这也是插件作者最推荐的开发姿势。

## 对接 Emotion

把 `data/config.json` 中的 Emby 地址和管理密钥指向 Emotion：

```json
{
  "emby_url": "https://emotion.example.com",
  "emby_api": "Emotion 后台生成的独立 API Key"
}
```

不要使用 Emotion 的主 `API_KEY`，建议在 Emotion 后台为 Bot 单独生成密钥，备注为 `pivkeyu_emby`，便于单独撤销。

联动后：

- TG 注册创建 Emotion 用户时会同步 Telegram User ID。
- TG 绑定已有账号时，密码验证成功后会回写 Telegram 身份。
- 原有创建、改密、封禁、媒体库权限和会话管理继续使用 Emby 兼容接口。
- TG 管理员可使用 `/emotionaudit 24` 查看最近 24 小时 Google Drive 实际回源、流量、登录失败和设备异常。

Bot 与 Emotion 之间应优先走 Docker 内网或私有网络，不要把管理 API Key 暴露在公网 URL 查询参数中。

## 开发检查

### Python 语法检查

```bash
python3 -m compileall main.py bot scripts
```

### Docker 配置检查

```bash
docker compose config
```

### 冒烟检查

```bash
python3 scripts/smoke_checks.py
```

## 相关文档

- [REVERSE_PROXY.md](REVERSE_PROXY.md)
- [bot/plugins/README.md](bot/plugins/README.md)
- [bot/plugins/xiuxian_game/README.md](bot/plugins/xiuxian_game/README.md)

## 对比参考

下面这些页面用于说明上面“相较于 Sakura_embyboss 的区别”一节的对比背景：

- Sakura 项目简介：https://berry8838.github.io/Sakura_embyboss/show/
- Sakura Docker Compose 部署文档：https://berry8838.github.io/Sakura_embyboss/deploy/start_docker/
- Sakura `docker-compose.yml` 模板：https://berry8838.github.io/Sakura_embyboss/deploy/compose/
