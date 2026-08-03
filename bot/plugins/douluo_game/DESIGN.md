# 斗罗大陆插件设计文档

> 开发规范对齐 `doupo_game`(MVP+装备体量)与 `xiuxian_game`(深度体量),目标为**豪华版**。

## 一、定位与总览

- 插件 ID:`douluo-game`,目录 `bot/plugins/douluo_game/`,数据层 `bot/sql_helper/sql_douluo/`。
- 玩法范围(豪华版):魂力境界修炼、武魂觉醒、猎杀魂兽获取魂环、魂骨与暗器装备、宗门学院、斗魂场 PvP、魂兽 Boss 讨伐、拍卖会、每日任务、奇遇事件、碎片互通经济。
- 前端:带 Mini App 网页端(用户端 `/plugins/douluo/app`,后台 `/plugins/douluo/admin`)。
- 命令集:精简,8 条 `dl_` 前缀命令;低频玩法走入口 + 内联键盘 + Mini App。
- 经济:游戏货币「金魂币」,与 Emby 碎片(`Emby.iv`)双向兑换。

## 二、命令集(精简,8 条)

| 命令 | 说明 | 场景 |
| --- | --- | --- |
| `/douluo` | 斗罗大陆入口(总览+行动键盘) | 私聊/群聊 |
| `/dl_me` | 魂师名帖 | 群聊 |
| `/dl_rank` | 排行榜 `/dl_rank [power\|ring\|coin]` | 群聊 |
| `/dl_bag` | 储物魂导器(背包) | 群聊 |
| `/dl_train` | 魂力修炼 | 群聊 |
| `/dl_hunt` | 猎杀魂兽获取魂环 | 群聊 |
| `/dl_wuhun` | 武魂觉醒/查看武魂 | 群聊 |
| `/dl_duel` | 回复目标发起斗魂 | 群聊 |

入口 `/douluo` 同时下发内联键盘(修炼/猎杀/武魂/背包/兑换),低频玩法(宗门、拍卖、任务、Boss、奇遇)在 Mini App 展开,并保留必要的回调按钮。

## 三、境界体系(魂师)

`core/realm.py` 数据驱动,形态对齐 doupo `DEFAULT_REALM_THRESHOLDS`。

| 序号 | 境界 | 星级 | 每星魂力 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 魂士 | 9 | 100 | 新手 |
| 2 | 魂师 | 9 | 220 | |
| 3 | 大魂师 | 9 | 380 | |
| 4 | 魂尊 | 9 | 620 | |
| 5 | 魂宗 | 9 | 920 | |
| 6 | 魂王 | 9 | 1320 | |
| 7 | 魂帝 | 9 | 1850 | |
| 8 | 魂圣 | 9 | 2550 | |
| 9 | 魂斗罗 | 9 | 3400 | |
| 10 | 封号斗罗 | 9 | 5200 | 突破时随机封号 |
| 11 | 神 | 1 | 12000 | 极限 |

- 每阶满星可突破,突破消耗金魂币,有成功率与保底(`BREAKTHROUGH_RULES`)。
- 突破失败损失少量魂力并累计保底计数。
- 行动力系统:每日行动力上限(默认 12),每种行动消耗不等;另有按行动类型的每日次数限制(修炼 5、猎杀 3、斗魂 3、拍卖 3、讨伐 2、兑换 3、觉醒 1 等)。

## 四、武魂觉醒

`core/wuhun.py`:约 32 个武魂,5 大系别(强攻/敏攻/防御/辅助/控制),5 档品质(凡品/良品/精品/珍品/神品)。

- 每位玩家**唯一**武魂。初始进入随机觉醒(高品质低概率),提供一次免费重铸(有冷却)。
- 每个武魂携带:先天魂力区间、四维属性加成(攻击/防御/速度/精神)、9 个魂技(对应 9 个魂环槽位,随魂环开启)。
- 控制/辅助系另有精神成长。

## 五、魂环与猎杀

`core/soulbeast.py`:

- 魂环槽位 9 个(`douluo_soul_rings`,UNIQUE(tg, slot))。
- 年限档位与颜色:十年(白)、百年(黄)、千年(紫)、万年(黑)、十万年(红)、百万年(蓝金)。
- 猎杀:按境界开放区域,每区域含魂兽池;花费行动力+金魂币,根据境界/运气产出魂环(年限、魂技)。首次猎杀必得第 1 魂环。
- 魂环为成长核心:加战力、提供魂技。可花费金魂币吸收更高年限替换(保留槽位)。
- 境界越高可吸收的魂环年限上限越高。

## 六、魂骨与暗器装备

- **魂骨**(`core/soulbone.py`):6 部位(头骨/左臂骨/右臂骨/左腿骨/右腿骨/躯干骨),6 档年限(十年~神级)。每块提供攻击/防御/速度加成 + 魂骨技名称。
- **暗器**(`core/ambush.py`):唐门系暗器(含沙射影、袖箭、诸葛神弩、孔雀翎、佛怒唐莲、观音泪等),单武器位,加攻击 + 概率触发额外伤害。
- 装备统一走通用背包 `douluo_inventory_items` + `douluo_item_definitions` 内容目录(对齐 doupo 物品版本管理思路),`equipped_slot` 区分部位。
- 战力计算:`魂力基础 + 境界系数 + 武魂品质/系别 + Σ魂环 + Σ魂骨 + 暗器 + 精神/辅助修正`。

## 七、宗门学院

`core/sects.py`:史莱克学院、武魂殿、天斗皇家学院、蓝电霸王龙宗、昊天宗、象甲宗、七宝琉璃宗。

- 入宗(首次免费,转宗有冷却与费用)、贡献、职位(弟子→执事→长老→副宗主→宗主,由贡献解锁)。
- 俸禄:每日领取(与每日任务联动)。
- 宗门技能/俸禄加成可配置。

## 八、斗魂场 PvP

- `/dl_duel` 回复目标发起斗魂,可押注金魂币,预备秒数(默认 8s,管理员可配)。
- 战力 + 随机扰动结算,胜者得押注金;双方产生战绩,进入排行。

## 九、魂兽 Boss 讨伐

`core/bosses.py`:泰坦巨猿、天青牛蟒、人面魔蛛、暗魔邪神虎、深海魔鲸王、地狱魔龙王等,分境界门槛。

- 挑战消耗行动力+金魂币,战力达标可胜;产出魂骨/魂环年限卷/战绩/金魂币。
- 每次产生战绩累计 `boss_score`,进入排行;稀有讨伐自动播报。

## 十、拍卖会

`douluo_auction_listings`:玩家上架魂骨/暗器/材料,金魂币竞价,出价阶梯、结束时间,竞得者得物、卖家得币(抽佣)。

## 十一、每日任务

`core/daily_tasks.py`:修炼 N 次、猎杀 N 次、斗魂 1 次、兑换 1 次、领取俸禄 1 次等;每日刷新,完成领金魂币/魂力。进度存 `douluo_daily_tasks`。

## 十二、奇遇事件

`core/events.py`:修炼/猎杀过程中的随机事件(唐三暗器铺、魂兽幼崽、秘境裂缝、邪魂师、魂骨残片、蓝银皇草……),概率触发,结果正负随机。事件模板数据驱动,后台可增改。

## 十三、经济与互通

- 主货币:金魂币(`douluo_profiles.coin`)。
- 互通:金魂币 ↔ Emby 碎片(`Emby.iv`),双向兑换,汇率/最低额/开关进 `douluo_settings`(对齐 doupo `exchange_currency`)。
- 行动产出金魂币有每日软上限/硬上限与溢出折损(`daily_coin_soft_cap`/`hard_cap`/`overflow_percent`)。

## 十四、数据模型(`sql_douluo/models.py`)

- `DouluoSetting` — 设置键值。
- `DouluoProfile` — 玩家主档(魂力/金魂币/境界星级/武魂字段/精神/宗门贡献职位/Boss战绩/突破失败计数/时间戳)。
- `DouluoSoulRing` — 魂环(tg, slot, years, color, skill_name, stats)。
- `DouluoInventoryItem` — 背包(tg, item_key, category, name, rarity, quantity, equipped_slot, item_meta)。
- `DouluoItemDefinition` — 内容目录(魂骨/暗器/材料/丹药,含属性与掉落源)。
- `DouluoDailyActionCounter` — 行动力/每日次数。
- `DouluoJournal` — 日志。
- `DouluoSectMember` — 宗门成员(职位/贡献/俸禄领取)。
- `DouluoDailyTask` — 每日任务进度。
- `DouluoAuctionListing` — 拍卖单(含竞价快照 JSON)。
- `DouluoBossRecord` — Boss 战绩。

迁移:`migrations/001_init_tables.py` 起,幂等 `_has_table`/`_create_table_if_missing`,`upgrade(connection)`/`downgrade(connection)`,**LF 行尾**(迁移跨平台哈希)。

## 十五、服务层职责(`service.py` + 分领域服务)

- `service.py`:设置缓存/合并、档案、行动力与每日限额、战斗结算、武魂觉醒、修炼、猎杀、装备、兑换、斗魂、日志、排行榜。
- 领域服务文件:`soulbeast_service.py`(猎杀/魂环)、`auction_service.py`(拍卖)、`daily_service.py`(任务/俸禄)、`admin_service.py`(后台编辑/内容目录)。

## 十六、文件清单

```
bot/plugins/douluo_game/
├── plugin.json            # schema_version 2,id douluo-game,miniapp 配置
├── plugin.py              # 薄入口,懒加载 register_bot/register_web
├── plugin_bot_handlers.py # TG 命令 + 内联键盘 + 回调
├── plugin_web_routes.py   # FastAPI 路由
├── api_models.py          # Web API Pydantic 入参
├── DESIGN.md / ARCHITECTURE.md
├── core/                  # realm.py wuhun.py soulbeast.py soulbone.py ambush.py sects.py events.py daily_tasks.py bosses.py
├── features/miniapp_bundle.py
├── shared/request_helpers.py
├── migrations/001_init_tables.py ...
└── static/                # 用户端 + 后台 SPA
bot/sql_helper/sql_douluo/
├── __init__.py models.py service.py
├── soulbeast_service.py auction_service.py daily_service.py admin_service.py
```
