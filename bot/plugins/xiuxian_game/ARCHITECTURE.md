# 修仙模块结构

## 维护入口

以后改功能时，优先改 `bot/plugins/xiuxian_game/features/` 下对应文件，不要先去改 `service.py` 或 `world_service.py`。

## 文件分工

- `api_models.py`
  - Web API / 管理 API 的请求模型定义。
- `features/growth.py`
  - 入道、吐纳、突破、修为成长、名帖序列化。
- `features/retreat.py`
  - 闭关开始、闭关结算、闭关状态校验。
- `features/pills.py`
  - 丹药效果、丹药使用限制、丹药结算。
- `features/content_catalog.py`
  - 新增丹药、材料、法宝、符箓、秘境、奇遇模板等静态内容目录。
- `features/inventory.py`
  - 法宝/符箓/功法/称号的切换、绑定、解绑。
- `features/shop.py`
  - 个人商店、官方商店、买卖、兑换、玩家检索。
- `features/combat.py`
  - 排行榜、斗法预览、斗法结算。
- `features/encounters.py`
  - 群奇遇生成、抢夺、结算、后台奇遇模板管理。
- `features/exploration.py`
  - 秘境场景、探索开始、探索领取、秘境门槛和死亡惩罚。
- `features/sects.py`
  - 宗门创建、入宗、退宗、职位、俸禄。
- `features/tasks.py`
  - 悬赏任务、答题任务、群消息绑定、任务领取。
- `features/crafting.py`
  - 配方、炼制、配方目录。
- `features/social.py`
  - 红包、抢劫、斗法押注。
- `features/economy.py`
  - 灵石转赠等纯经济操作。
- `features/admin_ops.py`
  - 后台玩家编辑、资源发放、修仙设置更新。
- `features/ui.py`
  - 面板 URL、内联键盘等 UI 辅助入口。
- `features/world_bundle.py`
  - 世界玩法聚合包构建。

## 兼容层

- `service.py`
  - 老的核心服务聚合文件，保留给旧调用路径。
- `world_service.py`
  - 老的世界玩法聚合文件，保留给旧调用路径。
- `plugin.py`
  - 薄入口，分别导出 `register_bot` / `register_web`。
- `plugin_bot_handlers.py` / `plugin_web_routes.py`
  - Bot 指令回调与 Web API 注册。

## 数据层

- `bot/sql_helper/sql_xiuxian/`
  - ORM、序列化、底层 CRUD（按领域拆分子模块）。
- `bot/sql_helper/alembic/versions/`
  - 修仙表结构迁移。

## 公共 SDK

- `bot/plugins/sdk/`
  - Mini App 鉴权、底栏导航、公开 URL 等插件公共能力。
  - 新功能优先复用 SDK，避免在各插件内重复实现。

## 这次新增的解耦点

- 高风险逻辑已经从超大文件中抽离：闭关、灵石赠送、丹药、秘境。
- `plugin.py` 不再直接依赖两个超大服务文件的公共能力，而是按领域依赖 `features/`。
- 请求模型集中到 `api_models.py`，避免入口文件里混入大量 schema 定义。
- `shared/request_helpers.py` 统一了 Web/Bot 共用的鉴权、上传、请求上下文解析。
- `shared/runtime_contract.py` 作为 Web 与 Bot 入口共享契约，避免 `plugin_web_routes.py` 直接依赖 `plugin_bot_handlers.py` 的实现细节。
- `features/runtime_facade.py` 收敛了 `miniapp_bundle` 对 `service.py` / `world_service.py` 的遗留依赖，后续按领域逐步替换为纯 `features/` 实现。
