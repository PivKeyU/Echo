"""魂兽 Boss 讨伐(领域玩法)。"""

from __future__ import annotations

import random
from typing import Any

from bot.plugins.douluo_game.core import BATTLE_ARMOR_ITEM_KEY, BOSS_CATALOG, boss_by_key, random_soulbone_by_part, random_soulbone_by_rarity
from bot.sql_helper import Session
from bot.sql_helper.sql_douluo.models import DouluoBossRecord, DouluoJournal, utcnow
from bot.sql_helper.sql_douluo.service import (
    _action_point_cost,
    _apply_daily_income_caps,
    _build_douluo_broadcast_event,
    _check_daily_action_limit,
    _check_daily_action_points,
    _compute_battle_power_session,
    _consume_daily_action_points,
    _economy_day_key,
    _increment_daily_action_counter,
    _grant_inventory_item_session,
    _load_profile,
    _serialize_profile_row,
    get_settings,
)

_BOSS_TIER_TO_BONE_RARITY: dict[str, str] = {
    "魂王": "万年",
    "魂帝": "万年",
    "魂圣": "十万年",
    "魂斗罗": "十万年",
    "封号斗罗": "神级",
    "神": "神级",
}


def list_bosses() -> list[dict[str, Any]]:
    return BOSS_CATALOG


def _accessible_bosses(stage: str) -> list[dict[str, Any]]:
    from bot.plugins.douluo_game.core.realm import realm_index

    player_idx = realm_index(stage)
    return [b for b in BOSS_CATALOG if realm_index(str(b.get("realm_stage_min") or "魂士")) <= player_idx]


def challenge_boss(tg: int, boss_key: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    now = utcnow()
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        if not profile.wuhun_key:
            raise ValueError("尚未觉醒武魂,先觉醒武魂再讨伐魂兽")
        stage = str(profile.realm_stage or "魂士")
        boss: dict[str, Any] | None = None
        if boss_key:
            boss = boss_by_key(boss_key)
            if boss is None:
                raise ValueError("Boss 不存在")
            if not _accessible_bosses(stage) or boss["key"] not in [b["key"] for b in _accessible_bosses(stage)]:
                raise ValueError("当前境界无法讨伐该 Boss")
        else:
            candidates = _accessible_bosses(stage)
            if not candidates:
                raise ValueError("当前境界还没有可讨伐的魂兽 Boss")
            boss = candidates[-1]

        action_counter, _, _ = _check_daily_action_points(session, tg, "boss", settings, now)
        daily_counter, limit = _check_daily_action_limit(session, tg, "boss", settings, now)
        entry_coin = max(int(boss.get("entry_coin") or 0), 0)
        if int(profile.coin or 0) < entry_coin:
            raise ValueError(f"讨伐该 Boss 需要 {entry_coin} 金魂币,当前不足")
        if entry_coin > 0:
            profile.coin = int(profile.coin or 0) - entry_coin
        _consume_daily_action_points(action_counter, _action_point_cost(settings, "boss"))
        _increment_daily_action_counter(daily_counter)

        player_power = _compute_battle_power_session(session, profile)
        boss_power = int(boss.get("recommended_power") or 1000)
        variance_range = max(int(boss_power * 0.05), 100)
        effective = player_power + random.randint(-variance_range, variance_range)
        win = effective >= boss_power

        record = session.query(DouluoBossRecord).filter(DouluoBossRecord.tg == tg, DouluoBossRecord.boss_key == boss["key"]).first()
        if record is None:
            record = DouluoBossRecord(tg=tg, boss_key=boss["key"], boss_name=boss.get("name", boss["key"]), times=0, wins=0, best_score=0)
            session.add(record)
        record.times = int(record.times or 0) + 1
        record.last_result = "win" if win else "loss"
        record.last_fought_at = now
        record.updated_at = utcnow()

        rewards: dict[str, Any] = {"coin": 0, "soul_power": 0, "score": 0, "soulbone": None, "win": win}
        if win:
            record.wins = int(record.wins or 0) + 1
            reward_cfg = boss.get("rewards", {})
            coin_raw = random.randint(int(reward_cfg.get("coin_min") or 0), int(reward_cfg.get("coin_max") or 0))
            sp_raw = random.randint(int(reward_cfg.get("soul_power_min") or 0), int(reward_cfg.get("soul_power_max") or 0))
            gained = _apply_daily_income_caps(
                session, tg, _economy_day_key(now), settings, coin=coin_raw, soul_power=sp_raw
            )
            profile.coin = int(profile.coin or 0) + gained["coin"]
            profile.soul_power = int(profile.soul_power or 0) + gained["soul_power"]
            score = random.randint(int(reward_cfg.get("score_min") or 0), int(reward_cfg.get("score_max") or 0))
            profile.boss_score = int(profile.boss_score or 0) + score
            record.best_score = max(int(record.best_score or 0), score)
            soulbone_chance = float(reward_cfg.get("soulbone_chance") or 0)
            rewards["coin"] = gained["coin"]
            rewards["soul_power"] = gained["soul_power"]
            rewards["score"] = score
            if random.random() < soulbone_chance:
                part = str(reward_cfg.get("soulbone_part") or "").strip() or None
                bone = None
                if part:
                    bone = random_soulbone_by_part(part)
                else:
                    rarity = _BOSS_TIER_TO_BONE_RARITY.get(stage, "万年")
                    bone = random_soulbone_by_rarity(rarity)
                if bone:
                    granted = _grant_inventory_item_session(session, tg, bone["key"], 1)
                    if granted:
                        rewards["soulbone"] = {"key": bone["key"], "name": bone["name"], "rarity": bone.get("rarity")}
            armor_chance = float(reward_cfg.get("armor_chance") or 0)
            if random.random() < armor_chance:
                granted = _grant_inventory_item_session(session, tg, BATTLE_ARMOR_ITEM_KEY, 1)
                if granted:
                    rewards["armor"] = {"key": BATTLE_ARMOR_ITEM_KEY, "name": "斗铠"}
        profile.updated_at = utcnow()
        session.commit()
        session.refresh(profile)
        power = _compute_battle_power_session(session, profile)
    try:
        from bot.sql_helper.sql_douluo.daily_service import report_task_progress

        report_task_progress(tg, "boss", 1)
    except Exception:
        pass
    try:
        with Session() as session:
            session.add(
                DouluoJournal(
                    tg=tg,
                    action_type="boss",
                    title="魂兽讨伐",
                    detail=f"讨伐 {boss.get('name')}:{'胜利' if win else '战败'},boss_score +{rewards['score']}",
                )
            )
            session.commit()
    except Exception:
        pass
    result = {
        "tg": tg,
        "boss": {"key": boss["key"], "name": boss.get("name")},
        "win": win,
        "player_power": player_power,
        "boss_power": boss_power,
        "entry_coin": entry_coin,
        "rewards": rewards,
        "profile": _serialize_profile_row(profile),
        "battle_power": power,
        "boss_score": int(profile.boss_score or 0),
    }
    result["broadcast"] = _build_douluo_broadcast_event(profile, result, settings)
    return result
