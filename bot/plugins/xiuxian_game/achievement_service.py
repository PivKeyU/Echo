"""修仙成就统计与发奖服务。

负责把各玩法上报的行为指标累加到用户进度，并在达成阈值后发放奖励。
"""

from __future__ import annotations

from typing import Any

from bot.sql_helper.sql_xiuxian import (
    ITEM_KIND_LABELS,
    apply_achievement_progress_deltas,
    get_profile,
    get_title,
    get_user_achievement,
    get_user_achievement_progress_map,
    grant_artifact_to_user,
    grant_material_to_user,
    grant_pill_to_user,
    grant_talisman_to_user,
    grant_title_to_user,
    list_achievements,
    list_achievements_by_metric,
    list_user_achievements,
    serialize_profile,
    unlock_user_achievement,
    upsert_profile,
)

# 成就面板与后台配置共用这份指标预设，避免各处手写同名 key。
ACHIEVEMENT_METRIC_PRESETS: list[dict[str, str]] = [
    {"key": "red_envelope_sent_count", "label": "发放红包次数", "description": "累计发放灵石红包的次数。"},
    {"key": "red_envelope_sent_stone", "label": "发放红包灵石总量", "description": "累计通过红包发出的灵石总量。"},
    {"key": "duel_initiated_count", "label": "发起斗法次数", "description": "累计主动发起并完成的斗法次数。"},
    {"key": "duel_total_count", "label": "参与斗法次数", "description": "累计参与的斗法总场次。"},
    {"key": "duel_win_count", "label": "斗法胜利次数", "description": "累计斗法获胜次数。"},
    {"key": "duel_loss_count", "label": "斗法失败次数", "description": "累计斗法落败次数。"},
    {"key": "rob_attempt_count", "label": "偷窃尝试次数", "description": "累计发起偷窃或抢劫的次数。"},
    {"key": "rob_success_count", "label": "偷窃成功次数", "description": "累计偷窃成功的次数。"},
    {"key": "rob_fail_count", "label": "偷窃失败次数", "description": "累计偷窃失败的次数。"},
    {"key": "rob_stone_total", "label": "偷窃得手灵石总量", "description": "累计通过偷窃获得的灵石总量。"},
    {"key": "gift_sent_count", "label": "赠送灵石次数", "description": "累计赠送灵石给其他道友的次数。"},
    {"key": "gift_sent_stone", "label": "赠送灵石总量", "description": "累计赠送给他人的灵石总量。"},
    {"key": "mentor_accept_count", "label": "收徒成功次数", "description": "累计成功收下徒弟的次数。"},
    {"key": "mentor_teach_count", "label": "传道次数", "description": "累计亲自为门下弟子传道授业的次数。"},
    {"key": "disciple_consult_count", "label": "问道次数", "description": "累计向师尊请教并完成问道的次数。"},
    {"key": "mentor_graduate_count", "label": "带徒出师次数", "description": "累计培养弟子顺利出师的次数。"},
    {"key": "disciple_graduate_count", "label": "出师次数", "description": "累计自身完成出师的次数。"},
    {"key": "craft_attempt_count", "label": "炼制尝试次数", "description": "累计尝试炼制装备、丹药或符箓的次数。"},
    {"key": "craft_success_count", "label": "炼制成功次数", "description": "累计炼制成功的次数。"},
    {"key": "repair_success_count", "label": "法宝修复成功次数", "description": "累计成功修复破损法宝的次数。"},
    {"key": "exploration_count", "label": "秘境探索次数", "description": "累计完成秘境探索并结算奖励的次数。"},
    {"key": "exploration_danger_count", "label": "危险遭遇次数", "description": "累计在秘境中遭遇危险事件并活着归来的次数。"},
    {"key": "exploration_recipe_drop_count", "label": "配方残页获得次数", "description": "累计在秘境中得到配方残页或图录的次数。"},
    {"key": "arena_open_count", "label": "开启擂台次数", "description": "累计在群内开启擂台、向所有人发起守擂邀请的次数。"},
    {"key": "arena_crowned_count", "label": "成为擂主次数", "description": "累计登上擂台并成为当期擂主的次数。"},
    {"key": "arena_defend_win_count", "label": "守擂成功次数", "description": "累计在擂台中成功击退挑战者的次数。"},
    {"key": "arena_final_win_count", "label": "终局夺魁次数", "description": "累计在擂台结束时以最终擂主身份完成结算的次数。"},
    {"key": "boss_kill_count", "label": "Boss击杀次数", "description": "累计击败个人Boss的次数。"},
    {"key": "boss_world_damage_total", "label": "世界Boss伤害总量", "description": "累计对世界Boss造成的总伤害值。"},
    {"key": "boss_world_mvp_count", "label": "世界Boss MVP次数", "description": "累计在世界Boss讨伐中获得伤害排名第一的次数。"},
]
ACHIEVEMENT_METRIC_LABELS = {item["key"]: item["label"] for item in ACHIEVEMENT_METRIC_PRESETS}


def _profile_label(tg: int) -> str:
    profile = serialize_profile(get_profile(tg, create=True)) or {}
    return (
        profile.get("display_label")
        or profile.get("display_name")
        or (f"@{profile['username']}" if profile.get("username") else "")
        or f"TG {tg}"
    )


def _grant_reward_item(tg: int, item: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(item.get("kind") or "").strip()
    ref_id = int(item.get("ref_id") or 0)
    quantity = max(int(item.get("quantity") or 0), 0)
    if ref_id <= 0 or quantity <= 0:
        return None
    if kind == "artifact":
        return grant_artifact_to_user(tg, ref_id, quantity)
    if kind == "pill":
        return grant_pill_to_user(tg, ref_id, quantity)
    if kind == "talisman":
        return grant_talisman_to_user(tg, ref_id, quantity)
    if kind == "material":
        return grant_material_to_user(tg, ref_id, quantity)
    return None


def format_reward_summary(reward_config: dict[str, Any] | None) -> str:
    reward = reward_config or {}
    parts: list[str] = []
    if int(reward.get("spiritual_stone") or 0) > 0:
        parts.append(f"{int(reward['spiritual_stone'])} 灵石")
    if int(reward.get("cultivation") or 0) > 0:
        parts.append(f"{int(reward['cultivation'])} 修为")
    for title_id in reward.get("titles") or []:
        title = get_title(int(title_id))
        if title is None:
            continue
        parts.append(f"称号【{title.name}】")
    for item in reward.get("items") or []:
        kind = str(item.get("kind") or "").strip()
        ref_id = int(item.get("ref_id") or 0)
        quantity = int(item.get("quantity") or 0)
        if quantity <= 0:
            continue
        item_name = f"{ITEM_KIND_LABELS.get(kind, kind)}#{ref_id}"
        if kind == "artifact":
            from bot.sql_helper.sql_xiuxian import get_artifact

            row = get_artifact(ref_id)
            if row is not None:
                item_name = row.name
        elif kind == "pill":
            from bot.sql_helper.sql_xiuxian import get_pill

            row = get_pill(ref_id)
            if row is not None:
                item_name = row.name
        elif kind == "talisman":
            from bot.sql_helper.sql_xiuxian import get_talisman

            row = get_talisman(ref_id)
            if row is not None:
                item_name = row.name
        elif kind == "material":
            from bot.sql_helper.sql_xiuxian import get_material

            row = get_material(ref_id)
            if row is not None:
                item_name = row.name
        parts.append(f"{item_name} x{quantity}")
    if reward.get("message"):
        parts.append(str(reward["message"]).strip())
    return "、".join(parts) if parts else "无额外奖励"


def grant_achievement_rewards(tg: int, reward_config: dict[str, Any] | None) -> dict[str, Any]:
    reward = reward_config or {}
    result: dict[str, Any] = {
        "spiritual_stone": 0,
        "cultivation": 0,
        "titles": [],
        "items": [],
        "message": str(reward.get("message") or "").strip(),
    }
    stone_gain = max(int(reward.get("spiritual_stone") or 0), 0)
    cultivation_gain = max(int(reward.get("cultivation") or 0), 0)
    if stone_gain > 0 or cultivation_gain > 0:
        profile = get_profile(tg, create=True)
        result["spiritual_stone"] = stone_gain
        result["cultivation"] = cultivation_gain
        upsert_profile(
            tg,
            spiritual_stone=int(profile.spiritual_stone or 0) + stone_gain,
            cultivation=int(profile.cultivation or 0) + cultivation_gain,
        )
    for title_id in reward.get("titles") or []:
        title = get_title(int(title_id))
        if title is None:
            continue
        grant_title_to_user(tg, int(title_id), source="achievement", auto_equip_if_empty=True)
        result["titles"].append({"id": int(title_id), "name": title.name})
    for item in reward.get("items") or []:
        granted = _grant_reward_item(tg, item)
        if granted is None:
            continue
        result["items"].append(
            {
                "kind": str(item.get("kind") or "").strip(),
                "ref_id": int(item.get("ref_id") or 0),
                "quantity": int(item.get("quantity") or 0),
                "payload": granted,
            }
        )
    result["summary"] = format_reward_summary(
        {
            "spiritual_stone": result["spiritual_stone"],
            "cultivation": result["cultivation"],
            "titles": [item["id"] for item in result["titles"]],
            "items": [
                {
                    "kind": item["kind"],
                    "ref_id": item["ref_id"],
                    "quantity": item["quantity"],
                }
                for item in result["items"]
            ],
            "message": result["message"],
        }
    )
    return result


def build_user_achievement_overview(tg: int, *, include_disabled: bool = False) -> dict[str, Any]:
    achievements = list_achievements(enabled_only=not include_disabled)
    progress_map = get_user_achievement_progress_map(tg)
    unlocked_map = {item["achievement_id"]: item for item in list_user_achievements(tg)}
    rows: list[dict[str, Any]] = []
    for achievement in achievements:
        current_value = int(progress_map.get(achievement["metric_key"], 0))
        target_value = max(int(achievement.get("target_value") or 0), 1)
        unlocked = unlocked_map.get(achievement["id"])
        reward_snapshot = (unlocked or {}).get("reward_snapshot") or achievement.get("reward_config") or {}
        rows.append(
            {
                **achievement,
                "metric_label": ACHIEVEMENT_METRIC_LABELS.get(achievement["metric_key"], achievement["metric_key"]),
                "current_value": current_value,
                "completed": bool(unlocked) or current_value >= target_value,
                "unlocked": bool(unlocked),
                "unlocked_at": None if unlocked is None else unlocked.get("unlocked_at"),
                "progress_percent": min(round(current_value * 100 / target_value, 2), 100.0),
                "reward_summary": format_reward_summary(reward_snapshot),
                "user_record": unlocked,
            }
        )
    return {
        "metric_progress": progress_map,
        "achievements": rows,
        "unlocked_count": sum(1 for row in rows if row["unlocked"]),
        "total_count": len(rows),
    }


def record_achievement_progress(
    tg: int,
    increments: dict[str, int | float],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    # 先批量刷新所有指标，再统一判断可解锁的成就，避免同一次行为重复读写数据库。
    progress = apply_achievement_progress_deltas(tg, increments)
    unlocks: list[dict[str, Any]] = []
    if not progress:
        return {"progress": {}, "unlocks": []}
    for achievement in list_achievements_by_metric(list(progress.keys()), enabled_only=True):
        metric_value = int(progress.get(achievement["metric_key"], 0))
        if metric_value < int(achievement.get("target_value") or 0):
            continue
        if get_user_achievement(tg, achievement["id"]):
            continue
        unlocked = unlock_user_achievement(
            tg,
            achievement["id"],
            reward_snapshot=achievement.get("reward_config") or {},
        )
        if unlocked is None or not unlocked.get("created"):
            continue
        reward_result = grant_achievement_rewards(tg, achievement.get("reward_config") or {})
        unlocks.append(
            {
                **unlocked,
                "source": source,
                "tg": tg,
                "display_name": _profile_label(tg),
                "achievement": achievement,
                "metric_label": ACHIEVEMENT_METRIC_LABELS.get(achievement["metric_key"], achievement["metric_key"]),
                "metric_value": metric_value,
                "reward_result": reward_result,
                "reward_summary": reward_result.get("summary") or format_reward_summary(achievement.get("reward_config")),
            }
        )
    return {"progress": progress, "unlocks": unlocks}


def record_red_envelope_metrics(tg: int, amount_total: int) -> list[dict[str, Any]]:
    result = record_achievement_progress(
        tg,
        {
            "red_envelope_sent_count": 1,
            "red_envelope_sent_stone": max(int(amount_total or 0), 0),
        },
        source="red_envelope",
    )
    return result["unlocks"]


def record_duel_metrics(challenger_tg: int, defender_tg: int, winner_tg: int, loser_tg: int) -> list[dict[str, Any]]:
    unlocks: list[dict[str, Any]] = []
    unlocks.extend(
        record_achievement_progress(
            challenger_tg,
            {
                "duel_initiated_count": 1,
                "duel_total_count": 1,
                "duel_win_count": 1 if challenger_tg == winner_tg else 0,
                "duel_loss_count": 1 if challenger_tg == loser_tg else 0,
            },
            source="duel",
        )["unlocks"]
    )
    unlocks.extend(
        record_achievement_progress(
            defender_tg,
            {
                "duel_total_count": 1,
                "duel_win_count": 1 if defender_tg == winner_tg else 0,
                "duel_loss_count": 1 if defender_tg == loser_tg else 0,
            },
            source="duel",
        )["unlocks"]
    )
    return unlocks


def record_robbery_metrics(attacker_tg: int, *, success: bool, amount: int = 0) -> list[dict[str, Any]]:
    result = record_achievement_progress(
        attacker_tg,
        {
            "rob_attempt_count": 1,
            "rob_success_count": 1 if success else 0,
            "rob_fail_count": 0 if success else 1,
            "rob_stone_total": max(int(amount or 0), 0) if success else 0,
        },
        source="rob",
    )
    return result["unlocks"]


def record_gift_metrics(sender_tg: int, amount: int) -> list[dict[str, Any]]:
    result = record_achievement_progress(
        sender_tg,
        {
            "gift_sent_count": 1,
            "gift_sent_stone": max(int(amount or 0), 0),
        },
        source="gift",
    )
    return result["unlocks"]


def record_craft_metrics(tg: int, *, success: bool, repair_success: bool = False) -> list[dict[str, Any]]:
    result = record_achievement_progress(
        tg,
        {
            "craft_attempt_count": 1,
            "craft_success_count": 1 if success else 0,
            "repair_success_count": 1 if repair_success else 0,
        },
        source="craft",
    )
    return result["unlocks"]


def record_exploration_metrics(
    tg: int,
    *,
    event_type: str | None = None,
    recipe_drop: bool = False,
) -> list[dict[str, Any]]:
    normalized_event_type = str(event_type or "").strip()
    result = record_achievement_progress(
        tg,
        {
            "exploration_count": 1,
            "exploration_danger_count": 1 if normalized_event_type == "danger" else 0,
            "exploration_recipe_drop_count": 1 if recipe_drop else 0,
        },
        source="exploration",
    )
    return result["unlocks"]


def record_boss_metrics(
    tg: int,
    *,
    kill: int = 0,
    world_damage: int = 0,
    world_mvp: int = 0,
) -> list[dict[str, Any]]:
    increments = {
        "boss_kill_count": max(int(kill or 0), 0),
        "boss_world_damage_total": max(int(world_damage or 0), 0),
        "boss_world_mvp_count": max(int(world_mvp or 0), 0),
    }
    increments = {key: value for key, value in increments.items() if value > 0}
    if not increments:
        return []
    result = record_achievement_progress(tg, increments, source="boss")
    return result["unlocks"]


def record_arena_metrics(
    tg: int,
    *,
    opened: int = 0,
    crowned: int = 0,
    defended: int = 0,
    final_win: int = 0,
) -> list[dict[str, Any]]:
    increments = {
        "arena_open_count": max(int(opened or 0), 0),
        "arena_crowned_count": max(int(crowned or 0), 0),
        "arena_defend_win_count": max(int(defended or 0), 0),
        "arena_final_win_count": max(int(final_win or 0), 0),
    }
    increments = {key: value for key, value in increments.items() if value > 0}
    if not increments:
        return []
    result = record_achievement_progress(tg, increments, source="arena")
    return result["unlocks"]
