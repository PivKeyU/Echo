# 修仙插件手册

## 1. 插件概览

`xiuxian-game` 是一个独立的修仙玩法插件，目录在：

```text
bot/plugins/xiuxian_game/
├── plugin.json
├── plugin.py
├── service.py
└── static/
```

当前版本已经接入以下能力：

- 初入仙途与灵根抽取
- 境界、层数、修炼、突破
- 筑基丹、清心丹、丹毒
- 法宝、丹药、背包
- 官方商店“风月阁”
- 个人商店
- 灵石与 Emby 货币互兑
- 群内斗法邀请
- 灵石榜、境界榜、法宝榜
- Mini App 用户页
- Mini App 管理页

### 1.1 2026-04 更新摘要

以下内容为当前版本的增量更新，若与旧版描述冲突，以本节和当前代码实现为准：

- Mini App 用户拍卖行已接入，可发起个人拍卖并查看群内拍卖盘。
- 新增多档打工/委托玩法，收益按门槛和风险分层，高投入对应更高回报。
- 修炼、打工、秘境、斗法胜出都可概率触发小幅属性成长，且概率、单次涨幅、抽取属性数可在后台配置。
- 奇遇中的心志/魅力/因果奖励已从用户侧玩法中剔除，避免出现无效配置。
- 宗门默认门槛新增战力要求，基础加成和职位薪资已按当前战力体系重调。
- 炼制配方会直接标注材料来源，支持显示秘境、事件、官坊与其他炼制链路。
- `/rob` 的偷取灵石不再是固定值，而是与攻击、身法、机缘、神识和双方战力差挂钩。
- `/gift` 支持回复目标后直接使用 `/gift <灵石数量>`，Mini App 内也支持搜索用户名后赠石或赠送背包物品。
- Mini App 页面补充了群聊快捷命令提示，并对赠送、炼制、拍卖等区域做了更适合手机端的交互优化。

## 2. 用户侧入口

### 2.1 Telegram 私聊入口

用户先私聊机器人发送：

```text
/start
```

在 `/start` 面板里会多出一个：

```text
🪷 初入仙途
```

点击后会弹出确认按钮：

```text
我愿踏入仙途
```

确认后会为当前 TG 用户初始化修仙档案。

### 2.2 修仙命令

当前用户侧命令如下：

- `/xiuxian`
- `/仙途`

说明：

- 仅私聊可用
- 如果用户还没有入道，会提示先踏入仙途
- 如果已经入道，会显示当前修仙面板

### 2.3 群内命令

- `/xiuxian_rank [stone|realm|artifact] [页码]`
- `/train`
- `/work [委托名]`
- `/salary`
- `/duel [赌注]`
- `/deathduel [赌注]`
- `/servitudeduel [赌注]`
- `/seek`
- `/rob`
- `/gift <灵石数量>`（回复目标时使用）
- `/gift <TGID> <灵石数量>`（兼容旧写法）

说明：

- `/xiuxian_rank` 群内查看排行榜，默认打开灵石榜第一页
- `/train` 群内直接完成一次吐纳修炼
- `/work` 群内直接结算灵石委托；不填委托名时会按收益从高到低一键完成当前全部可承接的委托
- `/salary` 群内直接领取宗门俸禄
- `/gift` 支持 reply 目标后直接赠石，不再强制填写 TGID
- `/rob` 会按双方当前属性和战力动态计算可偷取灵石

### 2.4 斗法命令

群里回复目标用户后发送：

```text
/duel
```

或者：

```text
/斗法
```

也可以带赌注：

```text
/duel 100
```

说明：

- 必须回复某个真实用户消息
- 不能对自己发起斗法
- 赌注单位是灵石
- 双方都需要先踏入仙途

## 3. 初入仙途与灵根规则

### 3.1 初始状态

用户确认踏入仙途后，默认获得：

- 境界：炼气一层
- 修为：0
- 灵石：50
- 丹毒：0

### 3.2 灵根判定

当前实现是逐次概率判定：

1. 天灵根：1%
2. 地灵根：1%
3. 如果前两者都没中，则判定是否为双灵根：10%
4. 如果不是双灵根，则为单灵根

### 3.3 五行灵根

五行池：

- 金
- 木
- 水
- 火
- 土

双灵根会从五行中随机抽出两个不同属性。

### 3.4 相生相克

双灵根会按五行关系计算斗法修正：

- 相生：斗法胜率 +5%
- 相克：斗法胜率 -5%
- 平衡：0%

特殊灵根额外修正：

- 天灵根：+15%
- 地灵根：+10%

## 4. 境界与突破规则

### 4.1 境界顺序

当前顺序如下：

1. 凡人
2. 炼气
3. 筑基
4. 结丹
5. 元婴
6. 化神
7. 须弥
8. 芥子
9. 混元一体
10. 炼虚
11. 合体
12. 渡劫
13. 真仙

### 4.2 层数规则

- 每个境界最高九层
- 只有达到九层后，才允许尝试突破下一个大境界

### 4.3 炼气突破筑基

当前规则：

- 基础成功率：45%
- 使用筑基丹后增加成功率

筑基丹加成为：

```text
50 - 历史使用次数 * 5
```

但最低不会低于：

```text
30
```

也就是：

- 第 1 次使用：+50
- 第 2 次使用：+45
- 第 3 次使用：+40
- ...
- 最低保底：+30

当前一次突破尝试只支持“本次是否使用筑基丹”的单次判定，不支持一次突破中连续塞多颗丹。

### 4.4 突破结果

成功：

- 升入下一境界一层
- 修为清零

失败：

- 扣除一部分当前修为
- 如果本次使用了筑基丹，会消耗对应丹药

## 5. 修炼、丹毒、丹药

### 5.1 修炼

Mini App 用户页和回调面板都可以执行：

- 吐纳修炼

修炼会带来：

- 修为增长
- 灵石增长

### 5.2 丹毒

当前上限：

```text
100
```

丹毒越高，修炼收益会被压低。

### 5.3 当前内置丹药

默认会自动种子生成一组基础与进阶丹药：

- 筑基丹
- 清心丹
- 洗髓丹
- 悟道丹
- 凝神丹
- 天运丹
- 血魄丹
- 蕴元丹
- 轻灵丹
- 补天丹
- 洗灵丹

说明：

- 筑基丹：用于突破时提高成功率
- 清心丹：减少 50 点丹毒
- 洗髓丹：永久提升根骨
- 悟道丹：永久提升悟性
- 凝神丹：永久提升神识
- 天运丹：永久提升机缘
- 血魄丹：永久提升气血
- 蕴元丹：永久提升真元
- 轻灵丹：永久提升身法
- 补天丹：灵根品质提升 1 阶，最高至极品灵根
- 洗灵丹：重塑整条灵根，结果至少保底中品灵根

### 5.4 自定义丹药

管理员可以在修仙管理页新增丹药，支持字段：

- 名称
- 类型
- 图片 URL
- 描述
- 效果值
- 丹毒增量
- 是否启用

当前已支持的 `pill_type`：

- `foundation`
- `clear_poison`
- `cultivation`
- `bone`
- `comprehension`
- `divine_sense`
- `fortune`
- `qi_blood`
- `true_yuan`
- `body_movement`
- `attack`
- `defense`
- `root_refine`
- `root_remold`
- `root_single`
- `root_double`
- `root_earth`
- `root_heaven`
- `root_variant`

含义：

- `foundation`：突破辅助丹
- `clear_poison`：清丹毒
- `cultivation`：直接加修为
- `bone`：直接加根骨
- `comprehension`：直接加悟性
- `divine_sense`：直接加神识
- `fortune`：直接加机缘
- `qi_blood`：直接加气血
- `true_yuan`：直接加真元
- `body_movement`：直接加身法
- `attack`：直接加攻击
- `defense`：直接加防御
- `root_refine`：按效果值提升灵根品阶，最高到极品灵根
- `root_remold`：重塑灵根，效果值表示保底品阶（0-5 对应无保底到极品保底）
- `root_single`：改造成单灵根，效果值表示保底品阶（0-5）
- `root_double`：改造成双灵根，效果值表示保底品阶（0-5）
- `root_earth`：改造成地灵根，效果值不参与计算
- `root_heaven`：改造成天灵根，效果值不参与计算
- `root_variant`：改造成变异灵根，效果值不参与计算

### 5.5 图片上传权限

修仙插件已经接入图片上传能力，管理员可以直接在后台为法宝、丹药、符箓、宗门、材料、场景和任务上传配图。

权限控制分为两层：

- 全局开关：在修仙后台设置中启用“允许非管理员用户上传图片”后，普通用户也可上传任务配图。
- 单独授权：若全局开关关闭，管理员仍可按用户单独放行。
- 管理员默认始终拥有上传权限。

快捷指令：

- 回复目标用户消息后发送 `/allow_upload`
- 回复目标用户消息后发送 `/remove_upload`
- `/delete_upload` 与 `/remove_upload` 等价

## 6. 法宝系统

### 6.1 管理员可维护字段

管理员可以在修仙管理页创建法宝，支持：

- 名称
- 稀有度
- 图片 URL
- 描述
- 威能加成
- 斗法胜率加成
- 修炼加成
- 是否启用

### 6.2 玩家使用

法宝进入背包后，用户可以在修仙 Mini App 中：

- 查看法宝库存
- 设置本命法宝

本命法宝会影响：

- 斗法
- 修炼收益

## 7. 商店系统

### 7.1 官方商店：风月阁

管理员可在后台上架：

- 法宝
- 丹药

可设置：

- 引用物品 ID
- 库存
- 售价
- 店铺名

当前后台还支持：

- 改库存
- 改售价
- 上架
- 下架

### 7.2 个人商店

用户可以在修仙 Mini App 中把自己背包里的物品上架到个人商店。

当前支持上架：

- 法宝
- 丹药

可填写：

- 铺子名称
- 物品类型
- 物品 ID
- 数量
- 售价
- 是否全群播报

### 7.3 全群播报

当用户勾选全群播报时，会按修仙设置中的广播成本扣灵石，并向主群发送上架广播。

当前成本项：

```text
shop_broadcast_cost
```

## 8. 货币互兑

### 8.1 两种货币

当前互通的是：

- 灵石
- Emby 货币（当前项目里显示为“片刻碎片”）

### 8.2 可配置项

管理员可在修仙后台设置：

- `coin_exchange_rate`

说明：

- `coin_exchange_rate`
  - 1 片刻碎片可兑换多少灵石，反向也按同一比例整份兑换

### 8.3 当前实现规则

- Emby 货币 -> 灵石：按比例直接兑换，不收手续费
- 灵石 -> Emby 货币：按比例整份兑换，不收手续费；不足一份的灵石留在余额中

相关封装在：

- [emby_currency.py](../../func_helper/emby_currency.py)

后续股市、赌场等插件可以直接复用这里的封装。

## 9. 斗法系统

### 9.1 发起方式

群内回复某位用户消息后发送：

```text
/duel
```

或：

```text
/duel 100
```

### 9.2 胜率基础

默认双方起始胜率：

```text
50% / 50%
```

之后再按权重修正。

### 9.3 当前权重来源

当前已经接入：

- 境界差
- 层数差
- 法宝差
- 灵根修正

### 9.4 碾压保底

如果大境界差距达到 2 个及以上：

- 弱势方不会低于 0.1%
- 强势方不会高于 99.9%

也就是保留最小翻盘概率。

### 9.5 赌注

可选带灵石赌注。

如果带赌注：

- 双方都要有足够灵石
- 结算时根据胜负转移赌注

## 10. 排行榜

当前支持三类：

- 灵石排行榜
- 境界排行榜
- 法宝排行榜

### 10.1 Bot 侧

群里可用：

- `/xiuxian_rank`
- `/仙榜`

配合按钮翻页。

### 10.2 分页规则

- 总榜最多取前 100 名
- 每页 20 名

### 10.3 Mini App 侧

修仙 Mini App 里也可切换：

- 灵石榜
- 境界榜
- 法宝榜

## 11. Mini App 页面说明

### 11.1 用户页

地址：

```text
/plugins/xiuxian/app
```

主要模块：

- 初入仙途
- 个人状态
- 修炼操作
- 货币互兑
- 法宝与丹药背包
- 官方商店
- 群修市集
- 个人上架
- 排行榜

### 11.2 管理页

地址：

```text
/plugins/xiuxian/admin
```

主要模块：

- 修仙设置
- 法宝管理
- 丹药管理
- 发放物品
- 官方商店管理

管理员打开方式：

- 在 Telegram Mini App 管理页中点插件管理
- 或者直接访问 `/plugins/xiuxian/admin`
- Telegram 管理员身份可直接进
- 浏览器兜底可用 `admin_token`

## 12. 数据表说明

修仙插件使用独立表，便于后续拆卸插件。

### 12.1 `xiuxian_settings`

作用：

- 修仙玩法全局配置

当前主要字段：

- `coin_exchange_rate`
- `shop_broadcast_cost`
- `official_shop_name`

### 12.2 `xiuxian_profiles`

作用：

- 用户修仙主档案

主要内容：

- 是否已入道
- 灵根类型
- 五行属性
- 境界与层数
- 修为
- 灵石
- 丹毒
- 历史筑基丹使用次数
- 当前装备法宝
- 店铺名

### 12.3 `xiuxian_artifacts`

作用：

- 法宝主表

### 12.4 `xiuxian_pills`

作用：

- 丹药主表

### 12.5 `xiuxian_artifact_inventory`

作用：

- 用户法宝背包

### 12.6 `xiuxian_pill_inventory`

作用：

- 用户丹药背包

### 12.7 `xiuxian_shop_items`

作用：

- 官方商店和个人商店共用商品表

区分方式：

- `is_official = true`：官方商店
- `is_official = false`：个人商店

### 12.8 `xiuxian_duel_records`

作用：

- 记录斗法结果

保存内容：

- 发起方
- 应战方
- 胜者
- 败者
- 双方预估胜率
- 本次斗法摘要

## 13. 管理员常用操作

### 13.1 初始化体验资源

私聊机器人发送：

```text
/xiuxian_seed <tg_id>
```

作用：

- 给指定用户补一套测试资源
- 方便演示修仙页

### 13.2 新增法宝

进入：

```text
/plugins/xiuxian/admin
```

填写法宝表单即可。

### 13.3 新增丹药

同上，填写丹药表单即可。

### 13.4 给用户发物品

在管理页填写：

- TG ID
- 物品类型
- 物品 ID
- 数量

### 13.5 调整兑换比例

在修仙管理页的“货币与商店设置”里修改：

- 1 片刻碎片可兑换多少灵石

### 13.6 管理风月阁

当前支持：

- 新上架商品
- 修改库存
- 修改价格
- 上架
- 下架

## 14. 接口清单

### 14.1 用户接口

- `POST /plugins/xiuxian/api/bootstrap`
- `POST /plugins/xiuxian/api/enter`
- `POST /plugins/xiuxian/api/train`
- `POST /plugins/xiuxian/api/commission/claim`
- `POST /plugins/xiuxian/api/breakthrough`
- `POST /plugins/xiuxian/api/pill/use`
- `POST /plugins/xiuxian/api/artifact/equip`
- `POST /plugins/xiuxian/api/explore/start`
- `POST /plugins/xiuxian/api/explore/claim`
- `POST /plugins/xiuxian/api/recipe/craft`
- `POST /plugins/xiuxian/api/exchange`
- `POST /plugins/xiuxian/api/shop/personal`
- `POST /plugins/xiuxian/api/auction/personal`
- `POST /plugins/xiuxian/api/shop/purchase`
- `POST /plugins/xiuxian/api/player/search`
- `POST /plugins/xiuxian/api/gift`
- `POST /plugins/xiuxian/api/gift/item`
- `POST /plugins/xiuxian/api/sect/join`
- `POST /plugins/xiuxian/api/sect/leave`
- `POST /plugins/xiuxian/api/sect/salary`
- `POST /plugins/xiuxian/api/leaderboard`
- `GET /plugins/xiuxian/api/shop`

### 14.2 管理接口

- `POST /plugins/xiuxian/admin-api/bootstrap`
- `POST /plugins/xiuxian/admin-api/settings`
- `POST /plugins/xiuxian/admin-api/artifact`
- `POST /plugins/xiuxian/admin-api/pill`
- `POST /plugins/xiuxian/admin-api/grant`
- `POST /plugins/xiuxian/admin-api/shop/official`
- `PATCH /plugins/xiuxian/admin-api/shop/{item_id}`

## 15. 当前已实现与后续可扩展点

当前已经实现的是“完整可跑的第一版”。

后续还适合继续扩展的方向：

- 更多丹药类型
- 更多法宝稀有度与词条
- 更多境界专属突破条件
- 更多斗法战报样式
- 个人商店订单流水
- 修仙成就系统
- 更多群内事件玩法
- 与后续赌场/股市插件共用钱包中心

## 16. 部署后推荐验收

建议按这个顺序验收：

1. 用户私聊 `/start`
2. 点击 `🪷 初入仙途`
3. 打开修仙 Mini App
4. 执行一次吐纳修炼
5. 查看灵石榜和境界榜
6. 管理员打开修仙管理页
7. 新建一个法宝
8. 新建一个丹药
9. 给测试用户发放法宝和丹药
10. 在风月阁上架商品
11. 用户购买商品
12. 用户发起一场个人拍卖并在群里看到竞价消息
13. 群内回复他人测试 `/gift 100`
14. 群内执行一次 `/train`、`/work`、`/salary`
15. 群内回复他人发起一次 `/duel`
16. 群内回复他人测试一次 `/rob`
17. Mini App 内搜索一个 `@username` 并完成一次物品赠送
18. 后台修改一组“玩法属性小成长”参数后再次验证修炼/打工/秘境结算

这套流程都通过后，修仙插件就可以对外开放使用了。
