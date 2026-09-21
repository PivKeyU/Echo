<div align="center">

# 🎬 Echo

**一个面向 Emby 服主的 Telegram 一体化管理系统**

Telegram Bot · Web 管理后台 · Mini App · 运行时插件系统

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.112-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-2.0-2CA5E0?logo=telegram&logoColor=white)](https://docs.pyrogram.org/)

*Emby 服主的一站式管理方案：注册、续费、封禁、统计、点播、修仙游戏，全在 Telegram 里搞定。*

</div>

---

## 📖 目录

- [✨ 功能亮点](#-功能亮点)
- [🖼️ 截图预览](#-截图预览)
- [🚀 快速开始](#-快速开始)
- [🏗️ 架构总览](#-架构总览)
- [⚙️ 配置说明](#-配置说明)
- [🌐 Web 后台与 Mini App](#-web-后台与-mini-app)
- [🧩 插件系统](#-插件系统)
- [🔐 安全设计](#-安全设计)
- [📦 升级与发布](#-升级与发布)
- [🧰 开发指南](#-开发指南)
- [❓ 常见问题](#-常见问题)
- [🤝 贡献](#-贡献)
- [📄 许可证](#-许可证)

---

## ✨ 功能亮点

| | 功能 | 说明 |
|---|---|---|
| 🤖 | **Telegram 一体化管理** | 注册、续期、封禁、解封、积分/货币、媒体库权限、到期检测，全部通过群聊/私聊指令完成 |
| 🌐 | **Web 管理后台** | 内置 `/admin` 管理面板：用户管理、分区授权、插件管理、点播记录、自动更新设置 |
| 📱 | **Telegram Mini App** | 内置 `/miniapp` 面板，用户在 Telegram 内即可查看状态、续期、管理媒体库 |
| 🧩 | **运行时插件系统** | 支持 ZIP 后台上传、权限声明、数据库迁移、依赖检测、启停开关，无需改主程序 |
| 🎮 | **内置文字游戏** | 修仙（xiuxian）、斗罗大陆、斗破苍穹、盲盒抽卡等完整玩法，附 Mini App 页面 |
| 🎬 | **点播系统** | 对接 MoviePilot，用户点播 → 自动下载 → 入库通知，全流程可追踪 |
| 🔔 | **追更提醒** | 可选对接 Emotion 服务端，新集上线自动推送 TG 通知（支持 HMAC 签名与幂等） |
| 🗄️ | **PostgreSQL + Redis** | 事务化数据存储 + 热点读缓存（读穿透、写失效），支撑高并发注册与查询 |
| 🐳 | **Docker Compose 开箱即用** | PostgreSQL + Redis + Caddy HTTPS 反代 + 健康检查，一条命令启动 |
| 🔐 | **凭据加密存储** | Emby 密码使用 Fernet 加密落库，密钥可配置、支持轮换脚本 |
| 🛡️ | **Webhook 签名验证** | Emby Webhook 要求 HMAC 签名 + 时间戳窗口 + 重放保护 |
| 📊 | **排行榜系统** | 播放次数日榜/周榜、观影时长榜，自动生成海报推送群聊 |

---

## 🖼️ 截图预览

> 项目正在持续开发中，截图占位区——欢迎提交截图 PR。

| 管理后台 | Mini App | 群播报 |
|---|---|---|
| ![admin](docs/screenshots/admin.png) | ![miniapp](docs/screenshots/miniapp.png) | ![rank](docs/screenshots/rank.png) |

---

## 🚀 快速开始

### 1. 准备条件

- Linux 服务器（推荐 Docker Engine + Docker Compose v2）
- 一个 [@BotFather](https://t.me/BotFather) 创建的 Telegram Bot Token
- Telegram `api_id` / `api_hash`（在 [my.telegram.org](https://my.telegram.org) 获取）
- Emby 服务器管理员 API Key
- （可选）一个 HTTPS 域名，用于 Web 后台与 Mini App

### 2. 获取项目并初始化

```bash
git clone https://github.com/PivKeyU/Echo.git
cd Echo
mkdir -p data log db caddy/data caddy/config
cp config_example.json data/config.json
```

### 3. 修改 `data/config.json`

至少替换以下字段（也可通过环境变量注入，见下文）：

| 字段 | 说明 |
|---|---|
| `bot_token` | BotFather 提供的 Token |
| `owner_api` / `owner_hash` | Telegram api_id / api_hash |
| `owner` | 机器人主人 TG ID |
| `group` | 主群聊 ID |
| `emby_url` / `emby_api` | Emby 地址与管理密钥 |

> 💡 **环境变量注入**：也可以在 `.env` 中配置 `PIVKEYU_BOT_TOKEN`、`PIVKEYU_OWNER_API`、`PIVKEYU_OWNER_HASH`，程序启动时会优先读取并覆盖占位符。

### 4. 启动服务

```bash
docker compose pull    # 拉取官方镜像
docker compose up -d   # 启动
```

如果你改了本地源码，改用本地构建：

```bash
docker compose up -d --build
```

默认启动四个服务：`postgres`、`redis`、`echo`（主应用）、`echo-caddy`（HTTPS 反代）。

### 5. 验证

```bash
docker compose ps
docker compose logs -f echo
curl http://127.0.0.1:8838/health
```

健康检查会同时返回 Redis 的启用与连通状态：

```json
{"ok": true, "redis": {"enabled": true, "available": true}}
```

默认入口：

- Web 后台：`http://127.0.0.1:8838/admin`
- Mini App：`http://127.0.0.1:8838/miniapp`
- 绑定域名后：`https://你的域名/admin`

---

## 🏗️ 架构总览

```text
┌─────────────┐    ┌──────────────────────────────┐
│  Telegram   │◄──►│          Echo 主容器          │
│  用户/群聊   │    │  ┌──────────┐  ┌───────────┐ │
└─────────────┘    │  │ Pyrogram │  │  FastAPI  │ │
                   │  │  Bot     │  │  Web API  │ │
                   │  └────┬─────┘  └─────┬─────┘ │
                   │       │             │       │
                   │  ┌────▼─────────────▼─────┐ │
                   │  │   运行时插件系统         │ │
                   │  │  (TG 处理器/Web 路由/   │ │
                   │  │   Mini App/迁移/依赖)   │ │
                   │  └────┬─────────────┬─────┘ │
                   └───────┼─────────────┼───────┘
                           │             │
              ┌────────────▼──┐   ┌──────▼────────┐
              │  PostgreSQL   │   │     Redis     │
              │  (Alembic 迁移)│   │ (热点读缓存)  │
              └───────────────┘   └───────────────┘

        ┌─────────────────────────────────────────┐
        │  Emby / Emotion / MoviePilot (外部服务)  │
        └─────────────────────────────────────────┘
```

- **Pyrogram Bot**：处理 TG 指令、内联键盘、回调、入群事件
- **FastAPI Web**：管理后台、Mini App 后端、Emby Webhook 接收器
- **SQLAlchemy + Alembic**：数据层与自动迁移（启动时 `upgrade head`）
- **Redis**：Emby 用户与游戏数据的热点读缓存（写操作主动失效）
- **APScheduler**：到期检测、排行榜推送、备份、点播同步等定时任务

---

## ⚙️ 配置说明

### 目录结构

```text
.
├── bot/                         # 主代码（Bot / Web / 插件 / 数据层）
├── caddy/                       # Caddy HTTPS 反代配置
├── data/                        # 持久化数据
│   ├── config.json              # 主配置（程序优先读取）
│   ├── runtime_plugins/         # 运行时插件
│   └── plugin_state/            # 插件私有数据
├── db/                          # PostgreSQL 数据目录
├── log/                         # 日志
├── config_example.json          # 配置模板
├── docker-compose.yml           # 一键部署编排
└── Dockerfile                   # 本地构建用
```

### 关键配置

```jsonc
{
  // Telegram 身份
  "bot_name": "your_bot_username_without_at",
  "bot_token": "1234567890:xxxx",
  "owner_api": 12345678,
  "owner_hash": "your_api_hash",

  // Emby
  "emby_url": "http://127.0.0.1:8096",
  "emby_api": "emby_admin_api_key",
  "emby_line": "http://你的Emby线路",

  // Web API（可选，开启后台需要）
  "api": {
    "status": true,
    "public_url": "https://bot.example.com",
    "access_token": "普通API令牌",
    "admin_token": "后台管理令牌（与 access_token 不同）",
    "webhook_secret": "Webhook HMAC 签名密钥"
  }
}
```

### 凭据加密（可选但推荐）

Emby 密码使用 `PIVKEYU_CREDENTIAL_KEY`（Fernet 密钥）加密落库；未配置时从 bot secret 派生。轮换密钥使用仓库自带脚本：

```bash
export PIVKEYU_CREDENTIAL_KEY_OLD="旧密钥"
export PIVKEYU_CREDENTIAL_KEY="新密钥"
python3 scripts/reencrypt_credentials.py          # dry-run 统计
python3 scripts/reencrypt_credentials.py --apply  # 真正重加密
```

---

## 🌐 Web 后台与 Mini App

### 管理后台（/admin）

- 用户增删改查、积分/货币调整、到期时间管理
- 分区授权码生成与回收
- 插件管理：上传 ZIP、启停、导航显示、依赖与迁移状态
- 点播（MoviePilot）记录与下载状态追踪
- 自动更新设置（镜像、容器名、服务名）

### Mini App（/miniapp）

用户在 Telegram 内打开即可：

- 查看账户状态（等级、到期时间、积分）
- 自助续期、修改安全码、显隐媒体库
- 参与文字游戏（修仙/斗罗/斗破/盲盒）
- 使用插件提供的扩展页面

> 通过 Telegram `initData` 签名校验登录，无需额外密码。

---

## 🧩 插件系统

Echo 的插件不止是"加指令"，而是完整的扩展体系：

| 能力 | 说明 |
|---|---|
| TG 处理器 | `register_bot(bot)` 注册指令/回调/事件 |
| Web 路由 | `register_web(app)` 注册 FastAPI 路由 |
| Mini App 页面 | 声明 `miniapp.path`，挂独立前端页面 |
| 后台页面 | 声明 `miniapp.admin_path`，嵌入管理后台 |
| 数据库迁移 | `migrations/` 目录 + 校验和防篡改 |
| 依赖声明 | `dependencies.python` 自动安装检测 |
| 权限声明 | `permissions` 声明所需能力，按需授权 |
| 持久化目录 | 每个插件独立的 `data/plugin_state/<id>/` |

### 插件形态

- **runtime**：后台上传 ZIP，推荐用于功能扩展
- **builtin**：随仓库维护（修仙、斗罗、斗破、盲盒、商城）
- **core**：强耦合核心功能，不可 ZIP 导入

### 最小插件示例

```json
{
  "id": "hello-plugin",
  "name": "示例插件",
  "version": "0.1.0",
  "entry": "plugin",
  "enabled": true,
  "permissions": ["telegram.commands", "web.routes"]
}
```

```python
from fastapi import APIRouter
from pyrogram import filters
from bot import prefixes


def register_bot(bot, context=None) -> None:
    @bot.on_message(filters.command("hello", prefixes))
    async def hello(_, msg):
        await msg.reply_text("Hello from Echo plugin!")


def register_web(app, context=None) -> None:
    router = APIRouter(prefix="/plugins/hello")

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    app.include_router(router)
```

📚 完整插件开发文档见 [bot/plugins/README.md](bot/plugins/README.md)，样例插件见 [bot/plugins/echo_template](bot/plugins/echo_template)。

---

## 🔐 安全设计

| 项目 | 实现 |
|---|---|
| 凭据加密 | Emby 密码 Fernet 加密落库，密文不进缓存外的任何响应 |
| Webhook 签名 | HMAC-SHA256（时间戳 + 原始请求体）+ 时间窗（默认 300s）+ Redis/进程内重放保护 |
| API 分级 | `access_token`（普通 API）与 `admin_token`（后台）分离，管理操作强制管理员 |
| Telegram 校验 | Mini App 通过 `initData` HMAC 校验，管理员身份二次确认 |
| CORS 收紧 | 不再接受 `*` 通配，自动收敛为 `public_url` 同源 |
| 请求限制 | Webhook 请求体上限、登录失败限流、Web 线程池上限 |
| 插件沙箱 | ZIP 成员路径穿越检测、软链拒绝、清单严格校验、迁移校验和 |
| 敏感信息 | 密码/安全码不再在 TG 消息、后台接口、日志中回显 |

---

## 📦 升级与发布

### 标准升级

```bash
docker compose pull
docker compose up -d --force-recreate
```

只更新主应用：

```bash
docker compose pull echo
docker compose up -d --force-recreate echo
```

### Docker Hub 发布（仓库维护者）

GitHub Actions 已内置两条发布线：

- 推送到 `master`/`main` → 构建并推送 `latest`
- 发布 GitHub Release → 构建并推送对应版本标签

均构建 `linux/amd64` + `linux/arm64` 双架构。仓库 Secrets 需配置 `DOCKER_USERNAME` 与 `DOCKER_PASSWORD`，默认镜像名为 `${DOCKER_USERNAME}/echo`。

---

## 🧰 开发指南

```bash
# Python 语法检查（无需安装依赖）
python3 -m compileall main.py bot scripts

# Docker 编排校验
docker compose config

# 冒烟检查（需服务运行中）
python3 scripts/smoke_checks.py

# 本地构建开发
docker compose up -d --build echo
```

### 插件开发的本地构建模式

创建 `docker-compose.override.yml`：

```yaml
services:
  echo:
    build:
      context: .
      dockerfile: Dockerfile
    image: echo:local
    pull_policy: never
```

```bash
docker compose up -d --build echo
```

---

## ❓ 常见问题

**Q: 不配置 Web 相关字段能启动吗？**
可以。`api.status = false` 时只启动 Telegram Bot，Web 服务自动跳过。

**Q: 数据库密码/用户名必须叫 echo 吗？**
默认 `POSTGRES_USER/DB/PASSWORD` 为 `echo`，可在 `docker-compose.yml` 与 `data/config.json` 中按需修改，两者保持一致即可。

**Q: 迁移失败导致无法启动怎么办？**
启动时会自动执行 Alembic 迁移并重试连接；如遇迁移脚本异常，可设置 `PIVKEYU_DB_MIGRATE_FALLBACK=1` 临时降级为 `create_all` 兜底建表（仅建议排查时使用）。

**Q: 更换服务器如何迁移数据？**
备份 `data/`（配置、运行时插件、插件状态）、`db/`（数据库）、`log/` 即可，直接拷贝到新服务器对应目录后 `docker compose up -d`。

**Q: 如何关闭某个内置游戏？**
在 `data/config.json` 的 `plugin_enabled` 中设置 `"xiuxian-game": false`（插件 ID 见各插件 `plugin.json`），重启后生效。

**Q: 用户密码为什么不在后台显示了？**
出于安全考虑，Emby 密码加密存储，后台与 TG 消息不再回显明文；请通过 Emby 客户端或专用重置流程处理。

---

## 🤝 贡献

欢迎任何形式的贡献：

1. Fork 本仓库并创建功能分支
2. 提交改动并附上清晰的提交信息
3. 发起 Pull Request，描述改动动机与影响

开发插件并希望收录为内置插件，也欢迎通过 Issue/PR 联系。

---

## 📄 许可证

[GPL-3.0](LICENSE) © Echo 项目贡献者

---

<div align="center">

**Echo — 让 Emby 管理回归简单**

⭐ 如果这个项目对你有帮助，欢迎点个 Star ⭐

</div>
