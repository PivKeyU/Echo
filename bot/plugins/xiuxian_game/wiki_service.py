from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from bot.plugins.xiuxian_game.achievement_service import ACHIEVEMENT_METRIC_LABELS
from bot.plugins.xiuxian_game.features.content_catalog import FARMABLE_MATERIAL_RULES
from bot.plugins.xiuxian_game.features.fishing import (
    FISHING_SPOTS,
    _build_fishing_candidates,
    _build_item_lookups,
    _spot_candidates,
)
from bot.plugins.xiuxian_game.features.growth import ensure_seed_data
from bot.sql_helper.sql_xiuxian import (
    ITEM_KIND_LABELS,
    PILL_EFFECT_VALUE_LABELS,
    get_quality_meta,
    get_xiuxian_settings,
    list_artifacts,
    list_artifact_sets,
    list_achievements,
    list_boss_configs,
    list_encounter_templates,
    list_materials,
    list_pills,
    list_recipe_ingredients,
    list_recipes,
    list_scene_drops,
    list_scenes,
    list_shop_items,
    list_talismans,
    list_tasks,
    list_techniques,
    list_titles,
)

GUIDE_PATH = Path(__file__).with_name("PLAYER_GUIDE.md")
GUIDE_FALLBACK = """# 修仙玩家玩法手册

## 一、先做什么

- 先入道、设性别，再看灵根、境界、背包与称号。
- 每次上线先做固定收益，再决定斗法、探索、交易还是炼制。

## 二、日常节奏

- 优先吐纳、打工、领取俸禄与收取探索、灵田、任务奖励。
- 想搜索具体玩法、材料、装备或配方获取方式，直接用页面里的 Wiki 搜索。
"""

SOURCE_PREFIXES = (
    ("探索·", "探索"),
    ("垂钓·", "垂钓"),
    ("灵田·", "灵田"),
    ("炼制·", "炼制"),
    ("奇遇·", "奇遇"),
    ("仙界奇石", "奇石"),
    ("官方任务·", "任务"),
    ("宗门任务·", "任务"),
    ("成就·", "成就"),
    ("师徒·", "师徒"),
    ("入道·", "入道"),
    ("官方商店", "商店"),
)

ENTRY_SOURCE_LABEL = "入道·初入仙途赠礼"
STARTER_ARTIFACT_NAME = "凡铁剑"
STARTER_TECHNIQUE_NAME = "长青诀"
STARTER_TITLE_NAME = "初入仙途"
MENTORSHIP_TITLE_SOURCES = {
    "传道授业": "师徒·带徒出师",
    "门下高徒": "师徒·完成出师",
}
BONUS_LABELS = (
    ("attack_bonus", "攻击"),
    ("defense_bonus", "防御"),
    ("bone_bonus", "根骨"),
    ("comprehension_bonus", "悟性"),
    ("divine_sense_bonus", "神识"),
    ("fortune_bonus", "机缘"),
    ("qi_blood_bonus", "气血"),
    ("true_yuan_bonus", "真元"),
    ("body_movement_bonus", "身法"),
    ("duel_rate_bonus", "斗法胜率"),
    ("cultivation_bonus", "修炼效率"),
    ("breakthrough_bonus", "突破加成"),
)
BONUS_PERCENT_FIELDS = {"duel_rate_bonus", "cultivation_bonus", "breakthrough_bonus"}
ATTRIBUTE_WIKI_ENTRIES = (
    {
        "key": "bone",
        "label": "根骨",
        "subtitle": "养成资质 · 抗丹毒 · 战力基础",
        "description": "根骨主要影响吐纳修炼收益、突破成功率、丹毒减免、气血成长，并计入综合战力。",
        "lines": [
            "吐纳修炼：根骨越高，每日吐纳得到的修为越多。",
            "突破境界：根骨会提高突破成功率，并减轻丹毒对突破的负面影响。",
            "丹药与成长：根骨会降低服丹新增丹毒；境界和层数提升时也会抬高气血底线。",
            "战力与门槛：根骨计入综合战力，也会作为部分委托、宗门和成长事件的条件或收益加成。",
        ],
        "tags": ["吐纳", "突破", "丹毒", "气血"],
        "filters": ["starter", "combat", "task", "sect"],
        "keywords": ["体魄", "道基", "抗丹毒", "修炼收益"],
    },
    {
        "key": "comprehension",
        "label": "悟性",
        "subtitle": "修炼效率 · 炼制成功 · 技术委托",
        "description": "悟性主要影响吐纳修为、突破成功率、炼丹炼器制符成功率，并计入综合战力。",
        "lines": [
            "吐纳修炼：悟性越高，每日吐纳得到的修为越多。",
            "突破境界：悟性是突破成功率的重要来源之一。",
            "炼制玩法：炼丹、炼器、制符会按悟性给成功率加成，材料品质和宗门加成也会叠加。",
            "委托与宗门：部分技术类委托、宗门准入和宗门任务会要求悟性，并把悟性转成额外收益。",
        ],
        "tags": ["吐纳", "突破", "炼制", "委托"],
        "filters": ["starter", "crafting", "task", "sect"],
        "keywords": ["炼丹", "炼器", "制符", "成功率", "参悟"],
    },
    {
        "key": "divine_sense",
        "label": "神识",
        "subtitle": "探索掉落 · 暴击会心 · 查探对手",
        "description": "神识主要影响秘境掉落权重、空探索概率、斗法会心、Boss伤害，并用于看破他人虚实。",
        "lines": [
            "秘境探索：神识会提高材料类掉落权重，并降低高品阶场景的空手概率。",
            "斗法战斗：神识差会影响会心概率；部分神识类功法、符箓和破甲效果也依赖它。",
            "Boss玩法：神识会直接提高对 Boss 的伤害，并提高会心概率。",
            "社交侦查：查看他人更详细虚实时，需要自己的神识高于对方。",
        ],
        "tags": ["探索", "斗法", "Boss", "查探"],
        "filters": ["explore", "combat", "boss", "social", "sect"],
        "keywords": ["暴击", "会心", "掉落权重", "看破", "虚实"],
    },
    {
        "key": "fortune",
        "label": "机缘",
        "subtitle": "概率修正 · 稀有奖励 · 灵石收益",
        "description": "机缘主要影响各种概率判定和稀有奖励权重，包括突破、聊天修为、炼制、探索、垂钓、赌坊、抢劫和夺宝。",
        "lines": [
            "概率判定：突破、聊天获得修为、属性小成长、斗法胜率、夺宝等概率都会受机缘修正。",
            "探索与垂钓：机缘会提高高品阶掉落权重、降低空手或空竿概率，并影响钓到高品阶奖励的机会。",
            "炼制玩法：机缘参与炼制成功率加成，并在最终概率上再次修正。",
            "收益玩法：吐纳灵石、委托灵石、赌坊稀有奖励和抢劫收益都会吃机缘。",
        ],
        "tags": ["概率", "稀有", "探索", "赌坊"],
        "filters": ["starter", "explore", "crafting", "combat", "task", "gambling"],
        "keywords": ["运气", "概率", "稀有掉落", "空竿", "开石", "夺宝"],
    },
    {
        "key": "willpower",
        "label": "心志",
        "subtitle": "突破稳定 · 高阶委托 · 斗法成长",
        "description": "心志主要影响突破成功率、部分委托门槛与收益、宗门门槛，并计入综合战力。",
        "lines": [
            "突破境界：心志会提高突破成功率；突破失败时也会额外增长心志。",
            "委托玩法：仙坊打工、值守地火室、镇守裂隙等委托会要求心志，并把心志折算为修为或灵石收益。",
            "宗门门槛：部分宗门要求最低心志，入宗前需要先把有效属性堆到门槛。",
            "斗法成长：斗法胜出后可能触发心志成长；心志本身也计入综合战力评分。",
        ],
        "tags": ["突破", "委托", "宗门", "成长"],
        "filters": ["starter", "combat", "task", "sect"],
        "keywords": ["道心", "突破失败", "地火", "裂隙", "打工"],
    },
    {
        "key": "charisma",
        "label": "魅力",
        "subtitle": "灵石收益 · 委托门槛 · 综合战力",
        "description": "魅力主要影响部分灵石收益和委托要求，也会少量计入综合战力。",
        "lines": [
            "吐纳收益：魅力会少量提高每日吐纳时获得的灵石。",
            "委托收益：仙坊打工、照料灵田、修补灵剑等委托会把魅力折算进灵石收益，部分高阶委托还会要求魅力。",
            "成长来源：部分委托成功后可能触发魅力小成长。",
            "战力评分：魅力在综合战力里的权重较低，更偏收益和门槛属性。",
        ],
        "tags": ["灵石", "委托", "收益"],
        "filters": ["starter", "task"],
        "keywords": ["人缘", "坊市", "修剑", "打工"],
    },
    {
        "key": "karma",
        "label": "因果",
        "subtitle": "突破辅助 · 探索事件 · 成长概率",
        "description": "因果主要影响突破辅助、秘境额外事件、委托修为收益和属性成长概率，并计入综合战力。",
        "lines": [
            "突破境界：因果会小幅提高突破成功率。",
            "秘境探索：因果会提高部分额外奖励事件的触发机会，并影响探索属性成长。",
            "委托收益：部分实战或技术委托会把因果折算为修为收益。",
            "成长概率：属性小成长判定会把机缘与部分因果一起用于概率修正。",
        ],
        "tags": ["突破", "探索", "委托", "成长"],
        "filters": ["explore", "task", "combat"],
        "keywords": ["额外事件", "概率修正", "修为收益"],
    },
    {
        "key": "qi_blood",
        "label": "气血",
        "subtitle": "生命上限 · 持久战 · 实战委托",
        "description": "气血主要决定斗法生命上限，并明显计入综合战力、抢劫收益和高风险委托。",
        "lines": [
            "斗法战斗：气血就是战斗中的生命上限，打到 0 即难以再战。",
            "战力评分：气血会计入综合战力，数值通常比普通属性更大。",
            "委托玩法：巡拣矿脉、云舟押阵、镇守裂隙等委托会要求或奖励气血路线。",
            "成长来源：委托、探索和斗法胜出后都有机会触发气血成长。",
        ],
        "tags": ["生命", "斗法", "委托", "战力"],
        "filters": ["combat", "task", "explore"],
        "keywords": ["血量", "生命上限", "续航", "硬战"],
    },
    {
        "key": "true_yuan",
        "label": "真元",
        "subtitle": "技能资源 · 修炼底子 · 耐力委托",
        "description": "真元主要决定斗法技能消耗资源，并影响综合战力、技术/耐力委托和部分功法续航。",
        "lines": [
            "斗法战斗：真元是战斗中的技能资源，功法和符箓技能会消耗真元；真元不足时技能不会触发。",
            "功法续航：治疗、护盾、破甲、闪避等技能常配置真元消耗，真元越高越能撑完整场。",
            "委托玩法：照料灵田、值守地火室、检修护山阵、修补灵剑等会要求真元，并把真元折算为收益。",
            "属性成长：吐纳和斗法胜出都有机会让真元成长；真元也计入综合战力。",
        ],
        "tags": ["技能", "斗法", "委托", "续航"],
        "filters": ["combat", "task", "crafting", "sect"],
        "keywords": ["蓝量", "法力", "技能消耗", "地火", "护山阵", "灵田"],
    },
    {
        "key": "body_movement",
        "label": "身法",
        "subtitle": "先手闪避 · 抢劫攻防 · 门槛属性",
        "description": "身法主要影响斗法先手和闪避，也影响抢劫、委托、宗门门槛与综合战力。",
        "lines": [
            "斗法战斗：每回合出手顺序按身法加随机值决定；双方身法差会影响闪避概率。",
            "抢劫玩法：抢劫成功后的灵石金额、失败后的赔付，以及攻防压力都会计算身法。",
            "委托与宗门：打工、代捕灵兽、护送商队、云舟押阵等会要求或奖励身法，部分宗门也有最低身法门槛。",
            "成长来源：委托、探索和斗法胜出都有机会触发身法成长。",
        ],
        "tags": ["先手", "闪避", "抢劫", "委托"],
        "filters": ["combat", "task", "social", "sect"],
        "keywords": ["速度", "先攻", "闪避率", "偷窃", "抢劫"],
    },
    {
        "key": "attack_power",
        "label": "攻击",
        "subtitle": "伤害输出 · 抢劫压力 · Boss伤害",
        "description": "攻击主要决定斗法和 Boss 的伤害输出，也影响抢劫成功收益、高风险委托和综合战力。",
        "lines": [
            "斗法战斗：攻击决定普通攻击、持续伤害、额外伤害等大多数输出效果。",
            "Boss玩法：攻击是 Boss 伤害的核心来源，同时参与最低伤害下限。",
            "抢劫玩法：攻击会提高出手压力和得手金额；防守方则更看防御、身法、机缘和神识。",
            "委托与门槛：代捕灵兽、护送商队、云舟押阵、镇守裂隙等实战委托会要求攻击。",
        ],
        "tags": ["伤害", "斗法", "Boss", "抢劫"],
        "filters": ["combat", "boss", "task", "social"],
        "keywords": ["输出", "破防", "伤害", "攻伐"],
    },
    {
        "key": "defense_power",
        "label": "防御",
        "subtitle": "承伤减免 · 护盾格挡 · 抢劫防守",
        "description": "防御主要减少斗法承伤、增强护盾或格挡类效果，并影响抢劫防守、委托门槛和综合战力。",
        "lines": [
            "斗法战斗：防御会抵消伤害；护盾和格挡类技能常按防御放大效果。",
            "抢劫防守：防守方防御越高，越能压低对方得手压力，并提高对方失手赔付。",
            "委托玩法：巡拣矿脉、护送商队、值守地火室、云舟押阵、镇守裂隙等会要求防御。",
            "战力评分：防御是综合战力的核心战斗属性之一。",
        ],
        "tags": ["承伤", "护盾", "抢劫", "委托"],
        "filters": ["combat", "task", "social", "sect"],
        "keywords": ["减伤", "格挡", "护体", "防守"],
    },
)
COMBAT_BONUS_FIELDS = (
    "attack_bonus",
    "defense_bonus",
    "qi_blood_bonus",
    "true_yuan_bonus",
    "body_movement_bonus",
    "duel_rate_bonus",
)
COMBAT_EFFECT_LABELS = {
    "extra_damage": "追击伤害",
    "attack": "攻击",
    "shield": "护盾",
    "guard": "格挡",
    "dodge": "闪避",
    "armor_break": "破甲",
    "heal": "治疗",
    "burn": "灼烧",
    "bleed": "流血",
}
TUTORIAL_FILTER_RULES = (
    ("starter", ("开局", "新手前三天", "先做什么", "第一天", "第二天", "第三天", "每日上线", "常用指令", "首页 wiki", "修仙 wiki")),
    ("explore", ("探索", "秘境", "垂钓", "灵田", "奇遇")),
    ("crafting", ("炼制", "炼丹", "炼器", "制符", "残页", "配方", "丹修", "农修")),
    ("combat", ("战修", "斗法", "擂台", "抢劫", "偷窃", "炉鼎", "生死斗", "/duel", "/deathduel", "/leitai", "/rob")),
    ("task", ("任务", "悬赏", "委托", "/work")),
    ("social", ("师徒", "道侣", "红包", "赠礼", "双修", "问道", "传道", "出师", "/gift")),
    ("sect", ("宗门", "俸禄", "贡献", "入宗", "叛宗", "/salary")),
)
ACHIEVEMENT_ROUTE_HINTS = {
    "red_envelope_sent_count": "玩法链路：群内发红包 -> 累计发放次数 -> 领取成就奖励。",
    "red_envelope_sent_stone": "玩法链路：群内发红包 -> 累计发放灵石总量 -> 领取成就奖励。",
    "duel_initiated_count": "玩法链路：搜寻对手并发起斗法 -> 累计对战场次 -> 解锁成就奖励。",
    "duel_total_count": "玩法链路：持续参与斗法、擂台或生死斗 -> 累计场次 -> 解锁更高阶斗法成就。",
    "duel_win_count": "玩法链路：提升战力与法宝搭配 -> 赢下斗法 -> 解锁胜场成就。",
    "duel_loss_count": "玩法链路：参与高风险斗法也会累计败场 -> 达标后领取韧性类成就。",
    "rob_attempt_count": "玩法链路：发起抢劫或偷窃 -> 累计尝试次数 -> 解锁邪修路线成就。",
    "rob_success_count": "玩法链路：抢劫得手 -> 累计成功次数 -> 解锁夺宝成就。",
    "rob_fail_count": "玩法链路：抢劫失手也会累计 -> 达标后可拿到补偿型成就奖励。",
    "rob_stone_total": "玩法链路：靠抢劫获取灵石 -> 累计得手总额 -> 解锁高阶邪修成就。",
    "gift_sent_count": "玩法链路：赠礼给其他道友 -> 累计赠送次数 -> 解锁人情路线成就。",
    "gift_sent_stone": "玩法链路：赠送灵石或资助同道 -> 累计灵石总量 -> 解锁善缘成就。",
    "mentor_accept_count": "玩法链路：收徒成功 -> 建立师徒关系 -> 解锁传承成就。",
    "mentor_teach_count": "玩法链路：每日传道 -> 累计传道次数 -> 解锁师尊路线成就。",
    "disciple_consult_count": "玩法链路：每日向师尊问道 -> 累计问道次数 -> 解锁弟子路线成就。",
    "mentor_graduate_count": "玩法链路：培养弟子完成出师 -> 累计带徒出师次数 -> 解锁师门传承成就。",
    "disciple_graduate_count": "玩法链路：完成师徒出师流程 -> 累计出师次数 -> 解锁弟子成就与称号。",
    "craft_attempt_count": "玩法链路：获取配方与材料后开炉 -> 累计炼制尝试次数 -> 解锁炼制成就。",
    "craft_success_count": "玩法链路：稳定提高炼制成功次数 -> 解锁炼器炼丹路线成就。",
    "repair_success_count": "玩法链路：收集破损法宝与修复材料 -> 修复成功 -> 解锁修复成就。",
    "exploration_count": "玩法链路：持续秘境探索 -> 累计探索结算次数 -> 解锁秘境成就。",
    "exploration_danger_count": "玩法链路：在秘境中遭遇危险并活着归来 -> 累计险境次数 -> 解锁生还成就。",
    "exploration_recipe_drop_count": "玩法链路：秘境中刷残页或配方 -> 累计获得次数 -> 解锁残页成就。",
    "arena_open_count": "玩法链路：在群内开启擂台 -> 累计开台次数 -> 解锁擂主路线成就。",
    "arena_crowned_count": "玩法链路：登擂夺冠成为擂主 -> 累计夺冠次数 -> 解锁擂台成就。",
    "arena_defend_win_count": "玩法链路：守擂成功击退挑战者 -> 累计守擂次数 -> 解锁擂台防守成就。",
    "arena_final_win_count": "玩法链路：擂台结算时保持最终擂主 -> 累计终局夺魁次数 -> 解锁顶级擂主成就。",
}


def _unique_append(target: dict[Any, list[str]], key: Any, value: str) -> None:
    if not value:
        return
    rows = target[key]
    if value not in rows:
        rows.append(value)


def _clean_markdown_line(line: str) -> str:
    text = str(line or "").strip()
    if not text:
        return ""
    if text.startswith("- "):
        text = f"· {text[2:].strip()}"
    else:
        text = re.sub(r"^(\d+)\.\s+", "", text)
    return text.replace("`", "").strip()


def _extract_keywords(*values: str) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        raw = str(value or "")
        for token in re.findall(r"/[\w_]+|[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", raw):
            normalized = token.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rows.append(token.strip())
    return rows


def _merge_filter_keys(*values: Any) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        items = value if isinstance(value, (list, tuple, set)) else [value]
        for item in items:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            rows.append(text)
    return rows


def _filters_from_source_labels(labels: list[str]) -> list[str]:
    filters: list[str] = []
    for label in labels:
        text = str(label or "").strip()
        if not text:
            continue
        if text.startswith(("探索·", "垂钓·", "灵田·", "奇遇·")):
            filters.append("explore")
        if text.startswith("炼制·"):
            filters.append("crafting")
        if text.startswith("官方任务·"):
            filters.append("task")
        if text.startswith("宗门任务·"):
            filters.extend(["task", "sect"])
        if text.startswith("师徒·"):
            filters.append("social")
        if text.startswith("入道·"):
            filters.append("starter")
    return _merge_filter_keys(filters)


def _filters_from_metric_key(metric_key: str) -> list[str]:
    key = str(metric_key or "").strip()
    if not key:
        return []
    if key.startswith(("duel_", "arena_", "rob_")):
        return ["combat"]
    if key.startswith(("craft_", "repair_")):
        return ["crafting"]
    if key.startswith("exploration_"):
        return ["explore"]
    if key.startswith(("mentor_", "disciple_", "gift_", "red_envelope_")):
        return ["social"]
    return []


def _filters_from_tutorial_text(title: str, subtitle: str, body_lines: list[str]) -> list[str]:
    haystack = " ".join([str(title or ""), str(subtitle or ""), *[str(line or "") for line in body_lines]]).lower()
    filters: list[str] = []
    for filter_key, keywords in TUTORIAL_FILTER_RULES:
        if any(str(keyword).lower() in haystack for keyword in keywords):
            filters.append(filter_key)
    return _merge_filter_keys(filters)


def _has_combat_bonus(payload: dict[str, Any]) -> bool:
    return any(int(payload.get(field) or 0) != 0 for field in COMBAT_BONUS_FIELDS)


def _read_guide_text() -> str:
    try:
        content = GUIDE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        content = ""
    return content or GUIDE_FALLBACK


def _format_bonus_summary(payload: dict[str, Any], limit: int = 5) -> str:
    parts: list[str] = []
    for field, label in BONUS_LABELS:
        value = int(payload.get(field) or 0)
        if value == 0:
            continue
        prefix = "+" if value > 0 else ""
        suffix = "%" if field in BONUS_PERCENT_FIELDS else ""
        parts.append(f"{label}{prefix}{value}{suffix}")
    if not parts:
        return "暂无直接属性加成"
    visible = parts[:limit]
    suffix = f" 等 {len(parts)} 项" if len(parts) > limit else ""
    return "、".join(visible) + suffix


def _format_realm_requirement(payload: dict[str, Any]) -> str:
    stage = str(payload.get("min_realm_stage") or "").strip()
    layer = max(int(payload.get("min_realm_layer") or 0), 0)
    if not stage:
        return "无境界门槛"
    return f"{stage}{layer}层" if layer > 0 else stage


def _format_pill_primary_effect(item: dict[str, Any]) -> str:
    pill_type = str(item.get("pill_type") or "").strip()
    label = str(item.get("effect_value_label") or PILL_EFFECT_VALUE_LABELS.get(pill_type) or "主效果").strip()
    value = int(item.get("effect_value") or 0)
    if pill_type == "foundation":
        return f"{label}：+{value}%"
    if pill_type == "clear_poison":
        return f"{label}：-{value} 丹毒"
    if pill_type in {"root_earth", "root_heaven", "root_variant"}:
        return f"{label}：固定改造为{str(item.get('pill_type_label') or '指定灵根').replace('洗成', '')}"
    prefix = "+" if value > 0 else ""
    return f"{label}：{prefix}{value}"


def _format_combat_effect_detail(effect: dict[str, Any]) -> str:
    kind = str(effect.get("kind") or "").strip()
    name = str(effect.get("name") or effect.get("display_name") or COMBAT_EFFECT_LABELS.get(kind) or kind or "战斗效果").strip()
    parts: list[str] = []
    chance = int(effect.get("chance") or 0)
    if chance > 0:
        parts.append(f"触发{chance}%")
    duration = int(effect.get("duration") or 0)
    if duration > 0:
        parts.append(f"持续{duration}轮")
    flat_damage = int(effect.get("flat_damage") or 0)
    if flat_damage:
        parts.append(f"固定伤害{flat_damage:+d}")
    flat_shield = int(effect.get("flat_shield") or 0)
    if flat_shield:
        parts.append(f"护盾+{flat_shield}")
    flat_heal = int(effect.get("flat_heal") or 0)
    if flat_heal:
        parts.append(f"治疗+{flat_heal}")
    ratio_percent = int(effect.get("ratio_percent") or 0)
    if ratio_percent:
        parts.append(f"倍率{ratio_percent:+d}%")
    dodge_bonus = int(effect.get("dodge_bonus") or 0)
    if dodge_bonus:
        parts.append(f"闪避{dodge_bonus:+d}")
    hit_bonus = int(effect.get("hit_bonus") or 0)
    if hit_bonus:
        parts.append(f"命中{hit_bonus:+d}")
    defense_ratio = int(effect.get("defense_ratio_percent") or 0)
    if defense_ratio:
        parts.append(f"防御影响{defense_ratio:+d}%")
    attack_ratio = int(effect.get("attack_ratio_percent") or 0)
    if attack_ratio:
        parts.append(f"攻击影响{attack_ratio:+d}%")
    cost = int(effect.get("cost_true_yuan") or 0)
    if cost > 0:
        parts.append(f"真元消耗{cost}")
    kind_label = COMBAT_EFFECT_LABELS.get(kind, kind)
    detail = f"{name}（{kind_label}）" if kind_label and kind_label != name else name
    return f"{detail}：{'、'.join(parts)}" if parts else detail


def _format_combat_config_summary(payload: dict[str, Any], *, limit: int = 4) -> str:
    config = payload.get("combat_config") if isinstance(payload.get("combat_config"), dict) else {}
    if not config:
        return "暂无战斗技能配置"
    rows: list[str] = []
    opening_text = str(config.get("opening_text") or "").strip()
    if opening_text:
        rows.append(f"起手：{opening_text}")
    for key, label in (("skills", "主动"), ("passives", "被动")):
        for effect in config.get(key) or []:
            if isinstance(effect, dict) and str(effect.get("kind") or "").strip():
                rows.append(f"{label}{_format_combat_effect_detail(effect)}")
    if not rows:
        return "暂无战斗技能配置"
    visible = rows[:limit]
    suffix = f" 等 {len(rows)} 项" if len(rows) > limit else ""
    return "；".join(visible) + suffix


def _build_artifact_set_catalog() -> dict[int, dict[str, Any]]:
    return {
        int(item["id"]): item
        for item in list_artifact_sets(enabled_only=True)
        if int(item.get("id") or 0) > 0
    }


def _artifact_set_member_names(item_catalog: dict[str, dict[int, dict[str, Any]]], artifact_set_id: int) -> list[str]:
    names = [
        str(item.get("name") or "").strip()
        for item in item_catalog.get("artifact", {}).values()
        if int(item.get("artifact_set_id") or 0) == int(artifact_set_id or 0)
    ]
    return [name for name in names if name]


def _format_reward_summary(
    reward: dict[str, Any],
    item_catalog: dict[str, dict[int, dict[str, Any]]],
    title_catalog: dict[int, dict[str, Any]],
) -> str:
    parts: list[str] = []
    stone = int(reward.get("spiritual_stone") or 0)
    cultivation = int(reward.get("cultivation") or 0)
    if stone > 0:
        parts.append(f"{stone} 灵石")
    if cultivation > 0:
        parts.append(f"{cultivation} 修为")
    for title_id in reward.get("titles") or []:
        title = title_catalog.get(int(title_id or 0)) or {}
        title_name = str(title.get("name") or "").strip()
        if title_name:
            parts.append(f"称号【{title_name}】")
    for item in reward.get("items") or []:
        kind = str((item or {}).get("kind") or "").strip()
        ref_id = int((item or {}).get("ref_id") or 0)
        quantity = max(int((item or {}).get("quantity") or 0), 0)
        if not kind or ref_id <= 0 or quantity <= 0:
            continue
        payload = (item_catalog.get(kind) or {}).get(ref_id) or {}
        item_name = str(payload.get("name") or f"{ITEM_KIND_LABELS.get(kind, kind)}#{ref_id}").strip()
        parts.append(f"{item_name} x{quantity}")
    message = str(reward.get("message") or "").strip()
    if message:
        parts.append(message)
    return "、".join(parts) if parts else "无额外奖励"


def _parse_guide_sections() -> list[dict[str, Any]]:
    text = _read_guide_text()
    current_h2 = ""
    current_title = ""
    current_lines: list[str] = []
    sections: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if not current_title:
            return
        body_lines = [_clean_markdown_line(line) for line in current_lines]
        body_lines = [line for line in body_lines if line]
        if not body_lines:
            return
        section_id = f"tutorial-{len(sections) + 1}"
        preview = body_lines[:3]
        title = current_title.strip()
        tags = []
        if current_h2:
            tags.append(current_h2)
        tags.extend(_extract_keywords(title, " ".join(preview))[:4])
        sections.append(
            {
                "id": section_id,
                "kind": "tutorial",
                "group": "tutorial",
                "filter_keys": _merge_filter_keys("tutorial", _filters_from_tutorial_text(title, current_h2, body_lines)),
                "kind_label": "玩法教程",
                "title": title,
                "subtitle": current_h2 if current_h2 and current_h2 != title else "玩家玩法手册",
                "description": preview[0],
                "body_lines": body_lines,
                "tags": tags[:5],
                "keywords": _extract_keywords(title, current_h2, " ".join(body_lines)),
            }
        )

    for raw_line in text.splitlines():
        line = str(raw_line or "").rstrip()
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            flush()
            current_h2 = line[3:].strip()
            current_title = current_h2
            current_lines = []
            continue
        if line.startswith("### "):
            flush()
            heading = line[4:].strip()
            current_title = f"{current_h2} · {heading}" if current_h2 else heading
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
    flush()
    return sections


def _join_labels(labels: list[str], limit: int = 4) -> str:
    rows = [str(label or "").strip() for label in labels if str(label or "").strip()]
    if not rows:
        return "暂未标注"
    visible = rows[:limit]
    suffix = f" 等 {len(rows)} 处" if len(rows) > limit else ""
    return "、".join(visible) + suffix


def _source_type_tags(labels: list[str]) -> list[str]:
    tags: list[str] = []
    for label in labels:
        for prefix, source_type in SOURCE_PREFIXES:
            if str(label or "").startswith(prefix) and source_type not in tags:
                tags.append(source_type)
    return tags


def _source_route_summary(labels: list[str]) -> str:
    routes = _source_type_tags(labels)
    return "、".join(routes) if routes else "多玩法联动"


def _resolve_item_ref_id(
    item_catalog: dict[str, dict[int, dict[str, Any]]],
    kind: str,
    ref_id: int,
    item_name: str,
) -> int:
    catalog = item_catalog.get(kind) or {}
    if ref_id > 0 and ref_id in catalog:
        return ref_id
    name = str(item_name or "").strip()
    if not name:
        return 0
    for candidate_id, item in catalog.items():
        if str(item.get("name") or "").strip() == name:
            return int(candidate_id)
    return 0


def _build_source_catalog(
    item_catalog: dict[str, dict[int, dict[str, Any]]],
    title_catalog: dict[int, dict[str, Any]],
) -> dict[tuple[str, int], list[str]]:
    source_map: dict[tuple[str, int], list[str]] = defaultdict(list)

    for scene in list_scenes(enabled_only=True):
        scene_name = str(scene.get("name") or "").strip()
        if not scene_name:
            continue
        for event in scene.get("event_pool") or []:
            kind = str((event or {}).get("bonus_reward_kind") or "").strip()
            ref_id = int((event or {}).get("bonus_reward_ref_id") or 0)
            if kind and ref_id > 0:
                _unique_append(source_map, (kind, ref_id), f"探索·{scene_name}")
        for drop in list_scene_drops(int(scene.get("id") or 0)):
            kind = str(drop.get("reward_kind") or "").strip()
            ref_id = int(drop.get("reward_ref_id") or 0)
            if kind and ref_id > 0:
                _unique_append(source_map, (kind, ref_id), f"探索·{scene_name}")

    for encounter in list_encounter_templates(enabled_only=True):
        kind = str(encounter.get("reward_item_kind") or "").strip()
        ref_id = int(encounter.get("reward_item_ref_id") or 0)
        name = str(encounter.get("name") or "").strip()
        if kind and ref_id > 0 and name:
            _unique_append(source_map, (kind, ref_id), f"奇遇·{name}")

    for shop_item in list_shop_items(official_only=True):
        kind = str(shop_item.get("item_kind") or "").strip()
        ref_id = int(shop_item.get("item_ref_id") or 0)
        if kind and ref_id > 0:
            shop_name = str(shop_item.get("shop_name") or "").strip()
            label = f"官方商店·{shop_name}" if shop_name else "官方商店"
            _unique_append(source_map, (kind, ref_id), label)

    fishing_candidates = _build_fishing_candidates(_build_item_lookups(), owned_recipe_ids=set())
    for spot in FISHING_SPOTS.values():
        spot_name = str(spot.get("name") or "").strip()
        if not spot_name:
            continue
        for row in _spot_candidates(spot, fishing_candidates):
            kind = str(row.get("kind") or "").strip()
            ref_id = int(row.get("ref_id") or 0)
            if kind and ref_id > 0:
                _unique_append(source_map, (kind, ref_id), f"垂钓·{spot_name}")

    for recipe in list_recipes(enabled_only=True):
        result_kind = str(recipe.get("result_kind") or "").strip()
        result_ref_id = int(recipe.get("result_ref_id") or 0)
        recipe_name = str(recipe.get("name") or "").strip()
        if result_kind == "material" and result_ref_id > 0 and recipe_name:
            _unique_append(source_map, ("material", result_ref_id), f"炼制·{recipe_name}")

    for reward in get_xiuxian_settings().get("gambling_reward_pool") or []:
        if not bool(reward.get("gambling_enabled", reward.get("enabled", True))):
            continue
        kind = str(reward.get("item_kind") or "").strip()
        ref_id = _resolve_item_ref_id(
            item_catalog,
            kind,
            int(reward.get("item_ref_id") or 0),
            str(reward.get("item_name") or "").strip(),
        )
        if kind and ref_id > 0:
            _unique_append(source_map, (kind, ref_id), "仙界奇石")

    for task in list_tasks(enabled_only=True):
        if int(task.get("owner_tg") or 0) > 0:
            continue
        task_scope = str(task.get("task_scope") or "").strip()
        if task_scope not in {"official", "sect"}:
            continue
        kind = str(task.get("reward_item_kind") or "").strip()
        ref_id = int(task.get("reward_item_ref_id") or 0)
        if not kind or ref_id <= 0:
            continue
        title = str(task.get("title") or "").strip() or "未命名任务"
        prefix = "官方任务" if task_scope == "official" else "宗门任务"
        _unique_append(source_map, (kind, ref_id), f"{prefix}·{title}")

    for achievement in list_achievements(enabled_only=True):
        reward = achievement.get("reward_config") or {}
        label = f"成就·{str(achievement.get('name') or '').strip() or '未命名成就'}"
        for title_id in reward.get("titles") or []:
            normalized_title_id = int(title_id or 0)
            if normalized_title_id > 0 and normalized_title_id in title_catalog:
                _unique_append(source_map, ("title", normalized_title_id), label)
        for reward_item in reward.get("items") or []:
            kind = str((reward_item or {}).get("kind") or "").strip()
            ref_id = int((reward_item or {}).get("ref_id") or 0)
            if kind and ref_id > 0:
                _unique_append(source_map, (kind, ref_id), label)

    for material in list_materials(enabled_only=True):
        material_id = int(material.get("id") or 0)
        material_name = str(material.get("name") or "").strip()
        if material_id <= 0 or not material_name:
            continue
        rules = FARMABLE_MATERIAL_RULES.get(material_name) or {}
        can_plant = bool(material.get("can_plant")) or bool(rules.get("can_plant"))
        if not can_plant:
            continue
        stage = str(material.get("unlock_realm_stage") or rules.get("unlock_realm_stage") or "炼气").strip()
        layer = max(int(material.get("unlock_realm_layer") or rules.get("unlock_realm_layer") or 1), 1)
        price = max(int(material.get("seed_price_stone") or rules.get("seed_price_stone") or 0), 0)
        price_text = f"·种子 {price} 灵石" if price > 0 else ""
        _unique_append(source_map, ("material", material_id), f"灵田·{stage}{layer}层可种{price_text}")

    for item_id, item in item_catalog.get("artifact", {}).items():
        if str(item.get("name") or "").strip() == STARTER_ARTIFACT_NAME:
            _unique_append(source_map, ("artifact", item_id), ENTRY_SOURCE_LABEL)
            break

    for item_id, item in item_catalog.get("technique", {}).items():
        if str(item.get("name") or "").strip() == STARTER_TECHNIQUE_NAME:
            _unique_append(source_map, ("technique", item_id), ENTRY_SOURCE_LABEL)
            break

    for title_id, title in title_catalog.items():
        title_name = str(title.get("name") or "").strip()
        if title_name == STARTER_TITLE_NAME:
            _unique_append(source_map, ("title", title_id), ENTRY_SOURCE_LABEL)
        mentorship_source = MENTORSHIP_TITLE_SOURCES.get(title_name)
        if mentorship_source:
            _unique_append(source_map, ("title", title_id), mentorship_source)

    return source_map


def _build_item_catalog() -> dict[str, dict[int, dict[str, Any]]]:
    return {
        "material": {int(item["id"]): item for item in list_materials(enabled_only=True) if int(item.get("id") or 0) > 0},
        "artifact": {int(item["id"]): item for item in list_artifacts(enabled_only=True) if int(item.get("id") or 0) > 0},
        "pill": {int(item["id"]): item for item in list_pills(enabled_only=True) if int(item.get("id") or 0) > 0},
        "talisman": {int(item["id"]): item for item in list_talismans(enabled_only=True) if int(item.get("id") or 0) > 0},
        "technique": {int(item["id"]): item for item in list_techniques(enabled_only=True) if int(item.get("id") or 0) > 0},
    }


def _build_title_catalog() -> dict[int, dict[str, Any]]:
    return {
        int(item["id"]): item
        for item in list_titles(enabled_only=True)
        if int(item.get("id") or 0) > 0
    }


def _item_name(item_catalog: dict[str, dict[int, dict[str, Any]]], kind: str, ref_id: int) -> str:
    payload = (item_catalog.get(str(kind or "").strip()) or {}).get(int(ref_id or 0)) or {}
    return str(payload.get("name") or "").strip()


def _reward_name(item_catalog: dict[str, dict[int, dict[str, Any]]], kind: str, ref_id: int) -> str:
    name = _item_name(item_catalog, kind, ref_id)
    if name:
        return name
    label = ITEM_KIND_LABELS.get(kind, kind or "奖励")
    return f"{label}#{int(ref_id or 0)}" if int(ref_id or 0) > 0 else str(label)


def _reward_names_from_pool(
    item_catalog: dict[str, dict[int, dict[str, Any]]],
    rows: Any,
    *,
    limit: int = 4,
) -> list[str]:
    names: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("item_kind") or row.get("kind") or "").strip()
        ref_id = int(row.get("item_ref_id") or row.get("ref_id") or 0)
        name = str(row.get("item_name") or "").strip() or _item_name(item_catalog, kind, ref_id)
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _scene_requirement_text(scene: dict[str, Any]) -> str:
    stage = str(scene.get("min_realm_stage") or "").strip()
    layer = max(int(scene.get("min_realm_layer") or 1), 1)
    power = max(int(scene.get("min_combat_power") or 0), 0)
    parts: list[str] = []
    if stage:
        parts.append(f"{stage}{layer}层")
    if power > 0:
        parts.append(f"战力 {power}")
    return "、".join(parts) if parts else "入道后即可进入"


def _boss_loot_names(item_catalog: dict[str, dict[int, dict[str, Any]]], boss: dict[str, Any], limit: int = 5) -> list[str]:
    fields = (
        ("loot_artifacts_json", "artifact"),
        ("loot_pills_json", "pill"),
        ("loot_talismans_json", "talisman"),
        ("loot_materials_json", "material"),
        ("loot_recipes_json", "recipe"),
        ("loot_techniques_json", "technique"),
    )
    names: list[str] = []
    for field, kind in fields:
        for row in boss.get(field) or []:
            if not isinstance(row, dict):
                continue
            ref_id = int(row.get("ref_id") or 0)
            if ref_id <= 0:
                continue
            name = _reward_name(item_catalog, kind, ref_id)
            chance = max(int(row.get("chance") or 0), 0)
            label = f"{name}({chance}%)" if chance > 0 else name
            if label not in names:
                names.append(label)
            if len(names) >= limit:
                return names
    return names


def _build_recipe_entries(
    source_map: dict[tuple[str, int], list[str]],
    material_use_map: dict[int, list[str]],
    crafted_by_map: dict[tuple[str, int], list[str]],
    item_catalog: dict[str, dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for recipe in list_recipes(enabled_only=True):
        recipe_id = int(recipe.get("id") or 0)
        if recipe_id <= 0:
            continue
        result_kind = str(recipe.get("result_kind") or "").strip()
        result_ref_id = int(recipe.get("result_ref_id") or 0)
        result_item = (item_catalog.get(result_kind) or {}).get(result_ref_id) or {}
        result_name = str(result_item.get("name") or recipe.get("name") or "").strip()
        quality = get_quality_meta(result_item.get("rarity") or result_item.get("quality_level") or 1)
        ingredient_lines: list[str] = []
        fragment_lines: list[str] = []
        ingredient_names: list[str] = []
        ingredient_source_labels: list[str] = []
        for ingredient in list_recipe_ingredients(recipe_id):
            material = ingredient.get("material") or {}
            material_id = int(material.get("id") or ingredient.get("material_id") or 0)
            material_name = str(material.get("name") or "").strip()
            quantity = max(int(ingredient.get("quantity") or 1), 1)
            ingredient_names.append(material_name)
            sources = source_map.get(("material", material_id), [])
            ingredient_source_labels.extend(sources)
            ingredient_lines.append(f"{material_name} x{quantity}（{_join_labels(sources, limit=3)}）")
            _unique_append(material_use_map, material_id, str(recipe.get("name") or "").strip())
            if "残页" in material_name:
                fragment_lines.append(f"{material_name} x{quantity}（{_join_labels(sources, limit=3)}）")
        recipe_sources = source_map.get(("recipe", recipe_id), [])
        body_lines = [
            f"产物：{ITEM_KIND_LABELS.get(result_kind, result_kind)}【{result_name}】",
            f"基础成功率：{max(int(recipe.get('base_success_rate') or 0), 0)}%",
        ]
        if recipe_sources:
            body_lines.append(f"配方获取：{_join_labels(recipe_sources)}")
        elif fragment_lines:
            body_lines.append(f"残页参悟：{'；'.join(fragment_lines[:3])}")
        if ingredient_lines:
            body_lines.append(f"炼制材料：{'；'.join(ingredient_lines[:4])}")
        route_labels = recipe_sources or ingredient_source_labels
        filter_keys = _merge_filter_keys(
            "recipe",
            "crafting",
            _filters_from_source_labels(recipe_sources),
            _filters_from_source_labels(ingredient_source_labels),
        )
        if fragment_lines:
            body_lines.append(f"玩法链路：先从{_source_route_summary(route_labels)}收集残页与主材，再到炼制页参悟并开炉。")
        else:
            body_lines.append(f"玩法链路：先拿到配方，再通过{_source_route_summary(route_labels)}补齐材料后炼制成品。")
        entries.append(
            {
                "id": f"recipe-{recipe_id}",
                "kind": "recipe",
                "group": "recipe",
                "filter_keys": filter_keys,
                "kind_label": "配方",
                "title": str(recipe.get("name") or "").strip(),
                "subtitle": f"{recipe.get('recipe_kind_label') or '炼制配方'} · 产物：{result_name}",
                "description": str(recipe.get("description") or result_item.get("description") or "").strip() or f"可炼制 {result_name}",
                "body_lines": body_lines,
                "tags": [
                    ITEM_KIND_LABELS.get(result_kind, result_kind),
                    str(quality.get("label") or ""),
                    f"{max(int(recipe.get('base_success_rate') or 0), 0)}%",
                    *_source_type_tags(recipe_sources),
                ][:5],
                "keywords": _extract_keywords(
                    str(recipe.get("name") or ""),
                    str(recipe.get("recipe_kind_label") or ""),
                    str(recipe.get("description") or ""),
                    result_name,
                    result_kind,
                    " ".join(ingredient_names),
                    " ".join(recipe_sources),
                ),
            }
        )
        _unique_append(crafted_by_map, (result_kind, result_ref_id), str(recipe.get("name") or "").strip())
    return entries


def _build_material_entries(
    source_map: dict[tuple[str, int], list[str]],
    material_use_map: dict[int, list[str]],
    item_catalog: dict[str, dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for material in item_catalog.get("material", {}).values():
        material_id = int(material.get("id") or 0)
        name = str(material.get("name") or "").strip()
        if material_id <= 0 or not name:
            continue
        rules = FARMABLE_MATERIAL_RULES.get(name) or {}
        can_plant = bool(material.get("can_plant")) or bool(rules.get("can_plant"))
        quality = get_quality_meta(material.get("quality_level") or 1)
        sources = source_map.get(("material", material_id), [])
        used_by = material_use_map.get(material_id, [])
        body_lines = []
        if sources:
            body_lines.append(f"主要来源：{_join_labels(sources)}")
        else:
            body_lines.append("主要来源：暂未标注，可留意探索、垂钓、奇遇、奇石与后台补充。")
        if used_by:
            body_lines.append(f"常见用途：{_join_labels(used_by, limit=5)}")
        if can_plant:
            stage = str(material.get("unlock_realm_stage") or rules.get("unlock_realm_stage") or "炼气").strip()
            layer = max(int(material.get("unlock_realm_layer") or rules.get("unlock_realm_layer") or 1), 1)
            body_lines.append(f"灵田种植：{stage}{layer}层后可播种。")
        if can_plant and sources:
            body_lines.append(f"玩法链路：先通过{_source_route_summary(sources)}拿到首批材料或种子，再转灵田稳定产出。")
        elif sources:
            body_lines.append(f"玩法链路：优先走{_source_route_summary(sources)}获取，再按常见用途推进后续炼制或突破。")
        filter_keys = _merge_filter_keys(
            "material",
            _filters_from_source_labels(sources),
            "crafting" if used_by else "",
        )
        entries.append(
            {
                "id": f"material-{material_id}",
                "kind": "material",
                "group": "material",
                "filter_keys": filter_keys,
                "kind_label": "材料",
                "title": name,
                "subtitle": f"材料 · {quality.get('label') or '凡品'}",
                "description": str(material.get("description") or "").strip() or "炼器、炼丹与制符常用材料。",
                "body_lines": body_lines,
                "tags": [
                    str(quality.get("label") or ""),
                    *(_source_type_tags(sources)[:3]),
                    "可种植" if can_plant else "",
                ],
                "keywords": _extract_keywords(name, str(material.get("description") or ""), " ".join(sources), " ".join(used_by)),
            }
        )
    return entries


def _build_item_entries(
    source_map: dict[tuple[str, int], list[str]],
    crafted_by_map: dict[tuple[str, int], list[str]],
    item_catalog: dict[str, dict[int, dict[str, Any]]],
    artifact_set_catalog: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for kind in ("artifact", "pill", "talisman", "technique"):
        for item in item_catalog.get(kind, {}).values():
            item_id = int(item.get("id") or 0)
            name = str(item.get("name") or "").strip()
            if item_id <= 0 or not name:
                continue
            quality = get_quality_meta(item.get("rarity_level") or item.get("rarity") or item.get("quality_level") or 1)
            direct_sources = source_map.get((kind, item_id), [])
            crafted_by = crafted_by_map.get((kind, item_id), [])
            body_lines = []
            if kind != "technique" and crafted_by:
                body_lines.append(f"炼制方式：{_join_labels(crafted_by, limit=4)}")
            if direct_sources:
                source_label = "主要来源" if kind == "technique" else "直接获取"
                body_lines.append(f"{source_label}：{_join_labels(direct_sources, limit=4)}")
            set_payload: dict[str, Any] = {}
            set_member_names: list[str] = []
            if kind == "artifact":
                set_id = int(item.get("artifact_set_id") or 0)
                set_payload = artifact_set_catalog.get(set_id) or {}
                set_member_names = _artifact_set_member_names(item_catalog, set_id) if set_payload else []
                body_lines.append(
                    "装备信息："
                    f"{str(item.get('artifact_role_label') or item.get('artifact_role') or '法宝').strip()} · "
                    f"{str(item.get('equip_slot_label') or item.get('equip_slot') or '未标注部位').strip()} · "
                    f"{str(item.get('equip_category_label') or item.get('equip_category') or '未分类').strip()}"
                    + (" · 唯一装备" if bool(item.get("unique_item")) else "")
                )
                body_lines.append(f"装备门槛：{_format_realm_requirement(item)}")
                body_lines.append(f"基础属性：{_format_bonus_summary(item, limit=12)}")
                body_lines.append(f"战斗效果：{_format_combat_config_summary(item)}")
                if set_payload:
                    body_lines.append(
                        f"所属套装：{str(set_payload.get('name') or '').strip()}（{max(int(set_payload.get('required_count') or 0), 1)} 件激活）"
                    )
                    if set_member_names:
                        body_lines.append(f"套装部件：{_join_labels(set_member_names, limit=6)}")
                    body_lines.append(f"套装效果：{_format_bonus_summary(set_payload, limit=12)}")
                    set_description = str(set_payload.get("description") or "").strip()
                    if set_description:
                        body_lines.append(f"套装说明：{set_description}")
                else:
                    body_lines.append("所属套装：无")
            elif kind == "pill":
                body_lines.append(f"丹药类型：{str(item.get('pill_type_label') or item.get('pill_type') or '未分类').strip()}")
                body_lines.append(f"服用门槛：{_format_realm_requirement(item)}")
                body_lines.append(f"主要效果：{_format_pill_primary_effect(item)}")
                poison_delta = int(item.get("poison_delta") or 0)
                poison_prefix = "+" if poison_delta > 0 else ""
                body_lines.append(f"丹毒变化：{poison_prefix}{poison_delta}")
                body_lines.append(f"附加属性：{_format_bonus_summary(item, limit=12)}")
            elif kind == "talisman":
                body_lines.append(f"使用门槛：{_format_realm_requirement(item)}")
                body_lines.append(f"基础属性：{_format_bonus_summary(item, limit=12)}")
                body_lines.append(f"显化次数：斗法内最多 {max(int(item.get('effect_uses') or 1), 1)} 次")
                body_lines.append(f"战斗效果：{_format_combat_config_summary(item)}")
            if kind == "technique":
                technique_type = str(item.get("technique_type_label") or item.get("technique_type") or "功法").strip()
                realm_stage = str(item.get("min_realm_stage") or "").strip()
                realm_layer = max(int(item.get("min_realm_layer") or 0), 0)
                if realm_stage:
                    layer_text = f"{realm_layer}层" if realm_layer > 0 else ""
                    body_lines.append(f"修习门槛：{realm_stage}{layer_text}")
                body_lines.append(f"主要加成：{_format_bonus_summary(item)}")
                body_lines.append(f"战斗效果：{_format_combat_config_summary(item)}")
            if not body_lines:
                fallback = "获取方式：暂未标注，可先搜索同名配方或查看相关玩法教程。"
                if kind == "technique":
                    fallback = "获取方式：暂未标注，可留意探索、奇遇、入道赠礼与后台补充。"
                body_lines.append(fallback)
            if kind != "technique" and direct_sources and crafted_by:
                body_lines.append(f"玩法链路：可直接走{_source_route_summary(direct_sources)}获取，也可先搜同名配方走炼制路线。")
            elif direct_sources:
                body_lines.append(f"玩法链路：优先走{_source_route_summary(direct_sources)}获取。")
            elif kind != "technique" and crafted_by:
                body_lines.append("玩法链路：先搜索同名配方，补齐材料后再炼制。")
            elif kind == "technique":
                body_lines.append(f"玩法链路：优先走{_source_route_summary(direct_sources)}掌握功法，再按门槛切换修习。")
            subtitle_parts = [ITEM_KIND_LABELS.get(kind, kind), str(quality.get("label") or "凡品")]
            if kind == "artifact":
                subtitle_parts.append(str(item.get("equip_slot_label") or item.get("equip_slot") or ""))
                if set_payload:
                    subtitle_parts.append(str(set_payload.get("name") or ""))
            if kind == "pill":
                subtitle_parts.append(str(item.get("pill_type_label") or item.get("pill_type") or ""))
            if kind == "talisman":
                subtitle_parts.append(f"显化 {max(int(item.get('effect_uses') or 1), 1)} 次")
            if kind == "technique":
                subtitle_parts.append(str(item.get("technique_type_label") or item.get("technique_type") or "功法"))
            filter_keys = _merge_filter_keys(
                kind,
                _filters_from_source_labels(direct_sources),
                "crafting" if kind in {"pill", "talisman"} or crafted_by else "",
                "combat" if kind in {"artifact", "talisman"} or _has_combat_bonus(item) else "",
            )
            entries.append(
                {
                    "id": f"{kind}-{item_id}",
                    "kind": kind,
                    "group": kind,
                    "filter_keys": filter_keys,
                    "kind_label": ITEM_KIND_LABELS.get(kind, kind),
                    "title": name,
                    "subtitle": " · ".join(part for part in subtitle_parts if part),
                    "description": str(item.get("description") or "").strip() or "可在修仙世界中获取与使用。",
                    "body_lines": body_lines,
                    "tags": [
                        ITEM_KIND_LABELS.get(kind, kind),
                        str(quality.get("label") or ""),
                        str(set_payload.get("name") or "") if kind == "artifact" and set_payload else "",
                        str(item.get("pill_type_label") or "") if kind == "pill" else "",
                        str(item.get("equip_slot_label") or "") if kind == "artifact" else "",
                        *(_source_type_tags(direct_sources)[:3]),
                    ],
                    "keywords": _extract_keywords(
                        name,
                        str(item.get("description") or ""),
                        " ".join(crafted_by),
                        " ".join(direct_sources),
                        str(set_payload.get("name") or ""),
                        str(set_payload.get("description") or ""),
                        " ".join(set_member_names),
                        _format_bonus_summary(item, limit=12),
                        _format_bonus_summary(set_payload, limit=12) if set_payload else "",
                        _format_combat_config_summary(item),
                        str(item.get("pill_type_label") or ""),
                    ),
                }
            )
    return entries


def _build_title_entries(
    source_map: dict[tuple[str, int], list[str]],
    title_catalog: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for title in title_catalog.values():
        title_id = int(title.get("id") or 0)
        name = str(title.get("name") or "").strip()
        if title_id <= 0 or not name:
            continue
        sources = source_map.get(("title", title_id), [])
        body_lines = [
            f"主要来源：{_join_labels(sources, limit=4)}" if sources else "主要来源：暂未标注，可留意成就、师徒、入道赠礼与后台补充。",
            f"称号效果：{_format_bonus_summary(title)}",
        ]
        if sources:
            body_lines.append(f"玩法链路：围绕{_source_route_summary(sources)}推进，对应达标后即可领取称号。")
        filter_keys = _merge_filter_keys(
            "title",
            _filters_from_source_labels(sources),
            "combat" if _has_combat_bonus(title) else "",
        )
        entries.append(
            {
                "id": f"title-{title_id}",
                "kind": "title",
                "group": "title",
                "filter_keys": filter_keys,
                "kind_label": "称号",
                "title": name,
                "subtitle": "称号",
                "description": str(title.get("description") or "").strip() or "佩戴后可提供额外加成。",
                "body_lines": body_lines,
                "tags": ["称号", *_source_type_tags(sources)[:3]],
                "keywords": _extract_keywords(name, str(title.get("description") or ""), " ".join(sources)),
            }
        )
    return entries


def _build_achievement_entries(
    item_catalog: dict[str, dict[int, dict[str, Any]]],
    title_catalog: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for achievement in list_achievements(enabled_only=True):
        achievement_id = int(achievement.get("id") or 0)
        if achievement_id <= 0:
            continue
        reward = achievement.get("reward_config") or {}
        reward_titles = [
            str((title_catalog.get(int(title_id or 0)) or {}).get("name") or "").strip()
            for title_id in reward.get("titles") or []
            if int(title_id or 0) > 0
        ]
        reward_titles = [title for title in reward_titles if title]
        reward_items = []
        for reward_item in reward.get("items") or []:
            kind = str((reward_item or {}).get("kind") or "").strip()
            ref_id = int((reward_item or {}).get("ref_id") or 0)
            quantity = max(int((reward_item or {}).get("quantity") or 0), 0)
            if not kind or ref_id <= 0 or quantity <= 0:
                continue
            payload = (item_catalog.get(kind) or {}).get(ref_id) or {}
            reward_items.append(str(payload.get("name") or f"{ITEM_KIND_LABELS.get(kind, kind)}#{ref_id}").strip())
        metric_key = str(achievement.get("metric_key") or "").strip()
        metric_label = ACHIEVEMENT_METRIC_LABELS.get(metric_key, metric_key or "未标注")
        route_hint = ACHIEVEMENT_ROUTE_HINTS.get(metric_key, "玩法链路：推进对应玩法并累计次数、胜场或收益后，即可解锁该成就。")
        filter_keys = _merge_filter_keys("achievement", _filters_from_metric_key(metric_key))
        entries.append(
            {
                "id": f"achievement-{achievement_id}",
                "kind": "achievement",
                "group": "achievement",
                "filter_keys": filter_keys,
                "kind_label": "成就",
                "title": str(achievement.get("name") or "").strip() or f"成就#{achievement_id}",
                "subtitle": f"成就 · {metric_label} · 目标 {max(int(achievement.get('target_value') or 0), 1)}",
                "description": str(achievement.get("description") or "").strip() or "达成指定玩法目标后可领取奖励。",
                "body_lines": [
                    f"统计项目：{metric_label}" + (f"（{metric_key}）" if metric_key and metric_label != metric_key else ""),
                    f"达成目标：{max(int(achievement.get('target_value') or 0), 1)}",
                    f"奖励内容：{_format_reward_summary(reward, item_catalog, title_catalog)}",
                    route_hint,
                ],
                "tags": [
                    "成就",
                    metric_label,
                    *(reward_titles[:2]),
                ],
                "keywords": _extract_keywords(
                    str(achievement.get("name") or ""),
                    str(achievement.get("achievement_key") or ""),
                    str(achievement.get("description") or ""),
                    metric_key,
                    metric_label,
                    " ".join(reward_titles),
                    " ".join(reward_items),
                    route_hint,
                ),
            }
        )
    return entries


def _build_scene_entries(
    item_catalog: dict[str, dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for scene in list_scenes(enabled_only=True):
        scene_id = int(scene.get("id") or 0)
        name = str(scene.get("name") or "").strip()
        if scene_id <= 0 or not name:
            continue
        drops = list_scene_drops(scene_id)
        drop_names = [
            _reward_name(item_catalog, str(drop.get("reward_kind") or ""), int(drop.get("reward_ref_id") or 0))
            for drop in drops
            if int(drop.get("reward_ref_id") or 0) > 0
        ]
        event_names: list[str] = []
        event_rewards: list[str] = []
        for event in scene.get("event_pool") or []:
            if not isinstance(event, dict):
                continue
            event_name = str(event.get("name") or event.get("description") or "").strip()
            if event_name:
                event_names.append(event_name)
            kind = str(event.get("bonus_reward_kind") or "").strip()
            ref_id = int(event.get("bonus_reward_ref_id") or 0)
            if kind and ref_id > 0:
                event_rewards.append(_reward_name(item_catalog, kind, ref_id))
        reward_preview = _join_labels([*drop_names, *event_rewards], limit=6)
        entries.append(
            {
                "id": f"scene-{scene_id}",
                "kind": "scene",
                "group": "scene",
                "filter_keys": _merge_filter_keys("scene", "activity", "explore"),
                "kind_label": "秘境",
                "title": name,
                "subtitle": f"探索 · {_scene_requirement_text(scene)}",
                "description": str(scene.get("description") or "").strip() or "可派遣角色探索并结算材料、配方、灵石或奇遇。",
                "body_lines": [
                    f"进入要求：{_scene_requirement_text(scene)}",
                    f"最长探索：{max(int(scene.get('max_minutes') or 0), 0)} 分钟",
                    f"主要掉落：{reward_preview}",
                    f"事件线索：{_join_labels(event_names, limit=4)}" if event_names else "事件线索：暂无额外事件标注。",
                    "玩法链路：按境界和战力解锁秘境，探索结算后再把掉落材料投入炼制、任务或交易。",
                ],
                "tags": ["探索", "秘境", *_source_type_tags([f"探索·{name}"])[:2]],
                "keywords": _extract_keywords(name, str(scene.get("description") or ""), " ".join(drop_names), " ".join(event_names), " ".join(event_rewards)),
            }
        )
    return entries


def _build_encounter_entries(item_catalog: dict[str, dict[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for encounter in list_encounter_templates(enabled_only=True):
        encounter_id = int(encounter.get("id") or 0)
        name = str(encounter.get("name") or "").strip()
        if encounter_id <= 0 or not name:
            continue
        reward_kind = str(encounter.get("reward_item_kind") or "").strip()
        reward_ref_id = int(encounter.get("reward_item_ref_id") or 0)
        reward_name = _reward_name(item_catalog, reward_kind, reward_ref_id) if reward_kind and reward_ref_id > 0 else ""
        stone_min = max(int(encounter.get("reward_stone_min") or 0), 0)
        stone_max = max(int(encounter.get("reward_stone_max") or 0), stone_min)
        lines = [
            f"触发按钮：{str(encounter.get('button_text') or '响应奇遇').strip()}",
            f"奖励物品：{reward_name}" if reward_name else "奖励物品：暂无固定物品奖励。",
            f"灵石奖励：{stone_min}-{stone_max}" if stone_max > 0 else "灵石奖励：无固定灵石奖励。",
            "玩法链路：群内自动触发或管理员派发后，按按钮参与奇遇并结算奖励。",
        ]
        entries.append(
            {
                "id": f"encounter-{encounter_id}",
                "kind": "encounter",
                "group": "encounter",
                "filter_keys": _merge_filter_keys("encounter", "activity", "explore", "social"),
                "kind_label": "奇遇",
                "title": name,
                "subtitle": "群内奇遇",
                "description": str(encounter.get("description") or "").strip() or "群内可参与的限时事件。",
                "body_lines": lines,
                "tags": ["奇遇", reward_name, "群内事件"],
                "keywords": _extract_keywords(name, str(encounter.get("description") or ""), reward_name, str(encounter.get("success_text") or "")),
            }
        )
    return entries


def _build_boss_entries(item_catalog: dict[str, dict[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    type_labels = {"personal": "个人Boss", "world": "世界Boss"}
    for boss in list_boss_configs(enabled_only=True):
        boss_id = int(boss.get("id") or 0)
        name = str(boss.get("name") or "").strip()
        if boss_id <= 0 or not name:
            continue
        boss_type = str(boss.get("boss_type") or "personal").strip()
        type_label = type_labels.get(boss_type, "Boss")
        loot_names = _boss_loot_names(item_catalog, boss)
        reward_line = f"奖励：灵石 {int(boss.get('stone_reward_min') or 0)}-{int(boss.get('stone_reward_max') or 0)}，修为 {int(boss.get('cultivation_reward') or 0)}"
        if loot_names:
            reward_line += f"，掉落 {_join_labels(loot_names, limit=5)}"
        entries.append(
            {
                "id": f"boss-{boss_id}",
                "kind": "boss",
                "group": "boss",
                "filter_keys": _merge_filter_keys("boss", "activity", "combat", "explore"),
                "kind_label": "Boss",
                "title": name,
                "subtitle": f"{type_label} · {str(boss.get('realm_stage') or '未知境界')}",
                "description": str(boss.get("description") or boss.get("flavor_text") or "").strip() or "高强度战斗目标，胜利后可获得灵石、修为和掉落。",
                "body_lines": [
                    f"战斗属性：气血 {int(boss.get('qi_blood') or boss.get('hp') or 0)}，攻击 {int(boss.get('attack_power') or 0)}，防御 {int(boss.get('defense_power') or 0)}，身法 {int(boss.get('body_movement') or 0)}",
                    f"主动技能：{str(boss.get('skill_name') or '无').strip()}；被动：{str(boss.get('passive_name') or '无').strip()}",
                    reward_line,
                    f"挑战限制：每日 {int(boss.get('daily_attempt_limit') or 0) or '不限'} 次，门票 {int(boss.get('ticket_cost_stone') or 0)} 灵石",
                    "玩法链路：提升战力与法宝、符箓配置后挑战；世界Boss需要多人累计伤害结算。",
                ],
                "tags": [type_label, str(boss.get("realm_stage") or ""), *_source_type_tags([f"Boss·{name}"])],
                "keywords": _extract_keywords(name, type_label, str(boss.get("description") or ""), str(boss.get("skill_name") or ""), str(boss.get("passive_name") or ""), " ".join(loot_names)),
            }
        )
    return entries


def _build_farm_entries(item_catalog: dict[str, dict[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    plantable = []
    for material in item_catalog.get("material", {}).values():
        material_name = str(material.get("name") or "").strip()
        rules = FARMABLE_MATERIAL_RULES.get(material_name) or {}
        if bool(material.get("can_plant")) or bool(rules.get("can_plant")):
            plantable.append(material_name)
    return [
        {
            "id": "farm-overview",
            "kind": "farm",
            "group": "farm",
            "filter_keys": _merge_filter_keys("farm", "activity", "explore", "crafting"),
            "kind_label": "灵田",
            "title": "灵田种植",
            "subtitle": "材料稳定产出",
            "description": "解锁地块后可种植部分材料，成熟收获进入材料背包，用于炼丹、炼器、制符和任务提交。",
            "body_lines": [
                f"可种材料：{_join_labels(plantable, limit=8)}",
                "地块规则：初始开放 3 块，后续地块按境界与灵石消耗解锁。",
                "田间操作：可浇水、施肥、除虫，成熟后在收获窗口内领取材料。",
                "玩法链路：探索或交易拿到材料后，转灵田做稳定供给，再投入配方炼制。",
            ],
            "tags": ["灵田", "种植", "材料", "炼制"],
            "keywords": _extract_keywords("灵田种植", "灵田", "种植", "浇水", "施肥", "除虫", "材料", " ".join(plantable)),
        }
    ]


def _build_fishing_entries(item_catalog: dict[str, dict[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    candidates = _build_fishing_candidates(_build_item_lookups(), owned_recipe_ids=set())
    for spot in FISHING_SPOTS.values():
        key = str(spot.get("key") or "").strip()
        name = str(spot.get("name") or "").strip()
        if not key or not name:
            continue
        spot_rows = _spot_candidates(spot, candidates)
        reward_names = [str(row.get("name") or "").strip() for row in spot_rows if str(row.get("name") or "").strip()]
        kind_labels = [
            ITEM_KIND_LABELS.get(kind, kind)
            for kind in (spot.get("kind_weights") or {}).keys()
            if str(kind or "").strip()
        ]
        requirement = f"{spot.get('min_realm_stage')}{max(int(spot.get('min_realm_layer') or 1), 1)}层" if spot.get("min_realm_stage") else "入道后即可"
        entries.append(
            {
                "id": f"fishing-{key}",
                "kind": "fishing",
                "group": "fishing",
                "filter_keys": _merge_filter_keys("fishing", "activity", "explore"),
                "kind_label": "垂钓",
                "title": name,
                "subtitle": f"垂钓点 · {requirement}",
                "description": str(spot.get("description") or "").strip() or "消耗灵石抛竿，按机缘和钓点权重获取奖励。",
                "body_lines": [
                    f"进入要求：{requirement}",
                    f"抛竿消耗：{max(int(spot.get('cast_cost_stone') or 0), 0)} 灵石",
                    f"奖励类型：{_join_labels(kind_labels, limit=6)}",
                    f"候选奖励：{_join_labels(reward_names, limit=8)}",
                    "玩法链路：按境界选择钓点，机缘越高越容易钓到高品阶奖励。",
                ],
                "tags": ["垂钓", requirement, *_merge_filter_keys(kind_labels)[:2]],
                "keywords": _extract_keywords(name, str(spot.get("description") or ""), " ".join(kind_labels), " ".join(reward_names)),
            }
        )
    return entries


def _build_gambling_entries(item_catalog: dict[str, dict[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    settings = get_xiuxian_settings()
    pool = [
        row
        for row in settings.get("gambling_reward_pool") or []
        if bool(row.get("gambling_enabled", row.get("enabled", True))) and max(float(row.get("gambling_weight", row.get("base_weight") or 0.0) or 0.0), 0.0) > 0
    ]
    reward_names = _reward_names_from_pool(item_catalog, pool, limit=10)
    exchange_cost = max(int(settings.get("gambling_exchange_cost_stone") or 0), 0)
    return [
        {
            "id": "gambling-immortal-stone",
            "kind": "gambling",
            "group": "gambling",
            "filter_keys": _merge_filter_keys("gambling", "activity", "explore"),
            "kind_label": "赌坊",
            "title": "仙界奇石",
            "subtitle": "赌坊开石",
            "description": "用灵石兑换仙界奇石后开启奖池，机缘会影响稀有奖励权重。",
            "body_lines": [
                f"兑换消耗：{exchange_cost} 灵石/枚" if exchange_cost > 0 else "兑换消耗：按后台当前配置结算。",
                f"奖池规模：{len(pool)} 项",
                f"代表奖励：{_join_labels(reward_names, limit=8)}",
                "玩法链路：先兑换奇石，再批量开石；高品阶奖励基础概率低，机缘越高越容易抬升稀有权重。",
            ],
            "tags": ["仙界奇石", "赌坊", "机缘", "奖池"],
            "keywords": _extract_keywords("仙界奇石", "赌坊", "开石", "机缘", "奖池", " ".join(reward_names)),
        }
    ]


def _build_attribute_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in ATTRIBUTE_WIKI_ENTRIES:
        key = str(entry.get("key") or "").strip()
        label = str(entry.get("label") or key).strip()
        if not key or not label:
            continue
        body_lines = [str(line or "").strip() for line in entry.get("lines") or [] if str(line or "").strip()]
        tags = [str(tag or "").strip() for tag in entry.get("tags") or [] if str(tag or "").strip()]
        keywords = [str(keyword or "").strip() for keyword in entry.get("keywords") or [] if str(keyword or "").strip()]
        entries.append(
            {
                "id": f"attribute-{key}",
                "kind": "attribute",
                "group": "attribute",
                "filter_keys": _merge_filter_keys("attribute", entry.get("filters") or []),
                "kind_label": "属性",
                "title": label,
                "subtitle": str(entry.get("subtitle") or "属性说明").strip(),
                "description": str(entry.get("description") or "修仙角色属性，会影响养成、战斗与玩法门槛。").strip(),
                "body_lines": body_lines,
                "tags": ["属性", *tags][:5],
                "keywords": _extract_keywords(label, key, str(entry.get("subtitle") or ""), str(entry.get("description") or ""), " ".join(body_lines), " ".join(tags), " ".join(keywords)),
            }
        )
    return entries


def build_wiki_bundle() -> dict[str, Any]:
    ensure_seed_data()
    tutorials = _parse_guide_sections()
    item_catalog = _build_item_catalog()
    artifact_set_catalog = _build_artifact_set_catalog()
    title_catalog = _build_title_catalog()
    source_map = _build_source_catalog(item_catalog, title_catalog)
    material_use_map: dict[int, list[str]] = defaultdict(list)
    crafted_by_map: dict[tuple[str, int], list[str]] = defaultdict(list)
    recipe_entries = _build_recipe_entries(source_map, material_use_map, crafted_by_map, item_catalog)
    material_entries = _build_material_entries(source_map, material_use_map, item_catalog)
    item_entries = _build_item_entries(source_map, crafted_by_map, item_catalog, artifact_set_catalog)
    title_entries = _build_title_entries(source_map, title_catalog)
    achievement_entries = _build_achievement_entries(item_catalog, title_catalog)
    scene_entries = _build_scene_entries(item_catalog)
    encounter_entries = _build_encounter_entries(item_catalog)
    boss_entries = _build_boss_entries(item_catalog)
    farm_entries = _build_farm_entries(item_catalog)
    fishing_entries = _build_fishing_entries(item_catalog)
    gambling_entries = _build_gambling_entries(item_catalog)
    attribute_entries = _build_attribute_entries()
    activity_entries = scene_entries + encounter_entries + boss_entries + farm_entries + fishing_entries + gambling_entries
    artifact_count = sum(1 for entry in item_entries if str(entry.get("group") or "") == "artifact")
    pill_count = sum(1 for entry in item_entries if str(entry.get("group") or "") == "pill")
    talisman_count = sum(1 for entry in item_entries if str(entry.get("group") or "") == "talisman")
    technique_count = sum(1 for entry in item_entries if str(entry.get("group") or "") == "technique")
    search_index = tutorials + attribute_entries + activity_entries + material_entries + item_entries + title_entries + recipe_entries + achievement_entries
    featured_tutorials = tutorials[:8]
    return {
        "featured_tutorials": featured_tutorials,
        "search_index": search_index,
        "counts": {
            "tutorial": len(tutorials),
            "attribute": len(attribute_entries),
            "material": len(material_entries),
            "artifact": artifact_count,
            "pill": pill_count,
            "talisman": talisman_count,
            "technique": technique_count,
            "title": len(title_entries),
            "recipe": len(recipe_entries),
            "achievement": len(achievement_entries),
            "activity": len(activity_entries),
            "scene": len(scene_entries),
            "encounter": len(encounter_entries),
            "boss": len(boss_entries),
            "farm": len(farm_entries),
            "fishing": len(fishing_entries),
            "gambling": len(gambling_entries),
        },
        "search_examples": ["真元", "心志", "身法", "闭关", "世界Boss", "仙界奇石", "青溪灵涧", "补天丹", "玄龟盾炼制图", "承道出山"],
    }
