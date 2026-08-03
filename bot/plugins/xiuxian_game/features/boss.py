from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    XiuxianBossConfig,
    XiuxianBossDefeat,
    XiuxianProfile,
    XiuxianWorldBossDamage,
    XiuxianWorldBossInstance,
    apply_spiritual_stone_delta,
    get_boss_config,
    get_boss_defeat,
    get_active_world_boss,
    get_profile,
    list_boss_configs,
    list_world_boss_damages,
    realm_index,
    serialize_boss_config,
    serialize_profile,
    serialize_world_boss_damage,
    serialize_world_boss_instance,
    create_world_boss_instance,
    utcnow,
    _queue_user_view_cache_invalidation,
)
from bot.plugins.xiuxian_game.probability import roll_probability_percent
from bot.plugins.xiuxian_game.achievement_service import record_boss_metrics


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service
    return legacy_service


def _grant_item_by_kind_in_session(session: Session, tg: int, kind: str, ref_id: int, quantity: int) -> dict[str, Any]:
    from bot.plugins.xiuxian_game.world_service import _grant_item_in_session as _grant
    return _grant(session, tg, kind, ref_id, quantity, source="boss", obtained_note="Boss掉落")


def _granted_item_payload(granted: dict[str, Any], kind: str) -> dict[str, Any]:
    payload = granted.get(kind) or granted.get("artifact") or granted.get("pill") or granted.get("talisman") or granted.get("material") or granted.get("recipe") or granted.get("technique") or {}
    if isinstance(payload, dict):
        return payload
    return {
        "id": int(getattr(payload, "id", 0) or 0),
        "name": str(getattr(payload, "name", "") or ""),
    }


def _boss_loot_chance(entry: dict[str, Any]) -> int:
    raw = entry.get("chance")
    if raw is None:
        return 100
    try:
        chance = int(raw)
    except (TypeError, ValueError):
        chance = 0
    return max(min(chance, 100), 0)


_STACKABLE_BOSS_LOOT_KINDS = {"artifact", "pill", "talisman", "material"}
_KNOWLEDGE_BOSS_LOOT_KINDS = {"recipe", "technique"}


def _normalized_boss_loot_item(loot: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(loot, dict):
        return None
    kind = str(loot.get("kind") or "").strip()
    try:
        ref_id = int(loot.get("ref_id") or 0)
        quantity = int(loot.get("quantity") or 0)
    except (TypeError, ValueError):
        return None
    quantity = max(quantity, 0)
    if not kind or ref_id <= 0 or quantity <= 0:
        return None
    return {"kind": kind, "ref_id": ref_id, "quantity": quantity}


def _prepare_boss_loot_grants(loot_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    stackable_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for loot in loot_items or []:
        normalized = _normalized_boss_loot_item(loot)
        if normalized is None:
            continue
        kind = str(normalized["kind"])
        if kind in _STACKABLE_BOSS_LOOT_KINDS:
            key = (kind, int(normalized["ref_id"]))
            current = stackable_by_key.get(key)
            if current is None:
                current = dict(normalized)
                stackable_by_key[key] = current
                prepared.append(current)
            else:
                current["quantity"] = int(current.get("quantity") or 0) + int(normalized["quantity"])
            continue
        if kind in _KNOWLEDGE_BOSS_LOOT_KINDS:
            for _ in range(max(int(normalized["quantity"] or 0), 1)):
                prepared.append({**normalized, "quantity": 1})
            continue
        prepared.append(normalized)
    return prepared


def _grant_boss_loot_items_in_session(
    session: Session,
    tg: int,
    loot_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    granted_items: list[dict[str, Any]] = []
    for loot in _prepare_boss_loot_grants(loot_items):
        kind = str(loot["kind"])
        try:
            granted = _grant_item_by_kind_in_session(
                session,
                int(tg),
                kind,
                int(loot["ref_id"]),
                int(loot["quantity"]),
            )
            session.flush()
        except ValueError:
            continue
        if granted:
            duplicate_converted = bool(granted.get("duplicate_converted"))
            row = {
                "kind": kind,
                "ref_id": int(loot["ref_id"]),
                "quantity": 0 if duplicate_converted else int(loot["quantity"]),
                "item": _granted_item_payload(granted, kind),
            }
            if duplicate_converted:
                row.update(
                    {
                        "duplicate_converted": True,
                        "stone_compensation": int(granted.get("stone_compensation") or 0),
                        "converted_to_stone": int(granted.get("converted_to_stone") or 0),
                        "item_kind_label": str(granted.get("item_kind_label") or ""),
                        "item_name": str(granted.get("item_name") or ""),
                    }
                )
            granted_items.append(row)
    return granted_items


def _today_key() -> str:
    return datetime.now().strftime("%Y%m%d")


def _remaining_attempts(limit: int, used: int) -> int:
    limit_value = max(int(limit or 0), 0)
    if limit_value <= 0:
        return 999999
    return max(limit_value - max(int(used or 0), 0), 0)


def _apply_boss_cultivation_reward_in_session(
    session: Session,
    tg: int,
    cultivation_gain: int,
    legacy_service,
) -> int:
    gain = max(int(cultivation_gain or 0), 0)
    if gain <= 0:
        return 0
    from bot.plugins.xiuxian_game.core.realm import apply_cultivation_gain
    profile_obj = session.query(XiuxianProfile).filter(XiuxianProfile.tg == int(tg)).with_for_update().first()
    if profile_obj is None:
        raise ValueError("你尚未踏入仙途，道基未立")
    stage = legacy_service.normalize_realm_stage(profile_obj.realm_stage or legacy_service.FIRST_REALM_STAGE)
    layer = max(int(profile_obj.realm_layer or 1), 1)
    current_cult = max(int(profile_obj.cultivation or 0), 0)
    new_layer, new_cult, _upgraded_layers, _remaining = apply_cultivation_gain(stage, layer, current_cult, gain)
    profile_obj.realm_layer = new_layer
    profile_obj.cultivation = new_cult
    profile_obj.updated_at = utcnow()
    return gain


def _claim_personal_boss_attempt_in_session(
    session: Session,
    tg: int,
    boss_id: int,
    won: bool,
    daily_limit: int,
) -> tuple[int, int]:
    today = _today_key()
    record = (
        session.query(XiuxianBossDefeat)
        .filter(XiuxianBossDefeat.tg == int(tg), XiuxianBossDefeat.boss_id == int(boss_id))
        .with_for_update()
        .first()
    )
    if record is None:
        used_today = 0
        record = XiuxianBossDefeat(
            tg=int(tg),
            boss_id=int(boss_id),
            defeat_count=0,
            daily_attempts=0,
            day_key=today,
        )
        session.add(record)
        session.flush()
    else:
        if record.day_key != today:
            record.day_key = today
            record.daily_attempts = 0
        used_today = int(record.daily_attempts or 0)

    limit = max(int(daily_limit or 0), 0)
    if limit > 0 and used_today >= limit:
        raise ValueError(f"今日挑战次数已尽（{used_today}/{limit}），明日再来吧。")

    record.daily_attempts = used_today + 1
    if won:
        record.defeat_count = max(int(record.defeat_count or 0) + 1, 1)
        record.last_defeated_at = utcnow()
    record.updated_at = utcnow()
    return int(record.daily_attempts or 0), limit


def _add_journal_in_session(session: Session, tg: int, action_type: str, title: str, detail: str | None = None) -> None:
    from bot.sql_helper.sql_xiuxian import XiuxianJournal
    session.add(
        XiuxianJournal(
            tg=int(tg),
            action_type=(action_type or "system").strip()[:32],
            title=(title or "未知操作").strip()[:128],
            detail=(detail or "").strip() or None,
        )
    )


def _active_world_boss_instance_for_update(session: Session, instance_id: int) -> XiuxianWorldBossInstance | None:
    return (
        session.query(XiuxianWorldBossInstance)
        .filter(XiuxianWorldBossInstance.id == int(instance_id))
        .with_for_update()
        .first()
    )


def _world_boss_damage_for_update(session: Session, instance_id: int, tg: int) -> XiuxianWorldBossDamage | None:
    return (
        session.query(XiuxianWorldBossDamage)
        .filter(XiuxianWorldBossDamage.instance_id == int(instance_id), XiuxianWorldBossDamage.tg == int(tg))
        .with_for_update()
        .first()
    )


def _last_world_boss_spawned_at() -> datetime | None:
    with Session() as session:
        row = (
            session.query(XiuxianWorldBossInstance)
            .order_by(XiuxianWorldBossInstance.spawned_at.desc(), XiuxianWorldBossInstance.id.desc())
            .first()
        )
        return row.spawned_at if row is not None else None


def settle_expired_world_bosses() -> list[dict[str, Any]]:
    now = utcnow()
    with Session() as session:
        expired_rows = (
            session.query(XiuxianWorldBossInstance.id)
            .filter(
                XiuxianWorldBossInstance.status == "active",
                XiuxianWorldBossInstance.expires_at <= now,
            )
            .order_by(XiuxianWorldBossInstance.id.asc())
            .all()
        )
        defeated_rows = (
            session.query(XiuxianWorldBossInstance.id)
            .filter(XiuxianWorldBossInstance.status == "defeated")
            .order_by(XiuxianWorldBossInstance.id.asc())
            .all()
        )
    results = [settle_world_boss_timeout(int(row.id)) for row in expired_rows]
    results.extend(_settle_world_boss_kill(int(row.id)) for row in defeated_rows)
    return results


# ── 个人 Boss ──────────────────────────────────────────────────


def list_personal_bosses_for_user(tg: int) -> dict[str, Any]:
    profile_data = serialize_profile(get_profile(tg, create=False))
    if not profile_data or not profile_data.get("consented"):
        return {"bosses": [], "profile": None}

    all_bosses = list_boss_configs(boss_type="personal")
    player_stage_index = realm_index(profile_data.get("realm_stage"))

    boss_list: list[dict[str, Any]] = []
    for boss in all_bosses:
        boss_stage_index = realm_index(boss.get("realm_stage"))
        defeat_record = get_boss_defeat(tg, int(boss["id"]))
        unlocked = boss_stage_index <= player_stage_index
        beaten = bool(defeat_record and int(defeat_record.get("defeat_count") or 0) > 0)
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        daily_used = 0
        if defeat_record and defeat_record.get("day_key") == today:
            daily_used = int(defeat_record.get("daily_attempts") or 0)
        daily_limit = int(boss.get("daily_attempt_limit") or 0)
        boss_list.append({
            **boss,
            "unlocked": unlocked,
            "beaten": beaten,
            "daily_attempts_used": daily_used,
            "daily_attempts_remaining": _remaining_attempts(daily_limit, daily_used),
            "daily_attempts_unlimited": daily_limit <= 0,
            "defeat_count": int((defeat_record or {}).get("defeat_count") or 0),
        })

    boss_list.sort(key=lambda b: (b["sort_order"], realm_index(b.get("realm_stage")), b["id"]))
    return {"bosses": boss_list, "profile": profile_data}


def challenge_personal_boss(tg: int, boss_id: int) -> dict[str, Any]:
    legacy_service = _legacy_service()
    profile_data = serialize_profile(get_profile(tg, create=False))
    if not profile_data or not profile_data.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立")

    boss_row = get_boss_config(boss_id)
    if not boss_row or not boss_row.enabled:
        raise ValueError("这个Boss已消散于天地间，寻不到踪迹。")
    boss = serialize_boss_config(boss_row)

    if boss["boss_type"] != "personal":
        raise ValueError("此乃天地共伐之物，非一人可独战。")

    player_stage_index = realm_index(profile_data.get("realm_stage"))
    boss_stage_index = realm_index(boss.get("realm_stage"))
    if boss_stage_index > player_stage_index:
        raise ValueError("你境界未至，贸然挑战无异于送死。")

    today = _today_key()
    defeat_record = get_boss_defeat(tg, boss_id)
    daily_used = 0
    if defeat_record and defeat_record.get("day_key") == today:
        daily_used = int(defeat_record.get("daily_attempts") or 0)
    daily_limit = max(int(boss.get("daily_attempt_limit") or 0), 0)
    if daily_limit > 0 and daily_used >= daily_limit:
        raise ValueError(f"今日挑战次数已尽（{daily_used}/{daily_limit}），明日再来吧。")

    # 门票消耗
    ticket_cost = int(boss.get("ticket_cost_stone") or 0)
    from bot.sql_helper.sql_xiuxian import get_shared_spiritual_stone_total
    current_stone = max(int(get_shared_spiritual_stone_total(tg) or 0), 0)
    if ticket_cost > 0 and current_stone < ticket_cost:
        raise ValueError(f"囊中灵石不足，挑战此兽需 {ticket_cost} 灵石作为门票。")

    # 闭关检查
    from bot.plugins.xiuxian_game.features.retreat import is_retreating
    if is_retreating(profile_data):
        raise ValueError("闭关之中，心神内敛，不宜外出挑战。")

    # 构建玩家战斗数据
    bundle = legacy_service.serialize_full_profile(tg)
    player_bundle = legacy_service._battle_bundle(bundle, apply_random=True)
    talisman_active_effects = player_bundle.get("talisman_active_effects") or {}
    boss_damage_bonus = max(float(talisman_active_effects.get("boss_damage_bonus") or 0), 0.0)
    boss_crit_bonus = max(float(talisman_active_effects.get("boss_crit_bonus") or 0), 0.0)
    player_state = player_bundle.copy()
    if boss_damage_bonus > 0 or boss_crit_bonus > 0:
        stats = dict(player_state.get("stats") or {})
        if boss_damage_bonus > 0:
            stats["attack_power"] = float(stats.get("attack_power") or 0) * (1 + min(boss_damage_bonus, 70.0) / 100.0)
        if boss_crit_bonus > 0:
            stats["divine_sense"] = float(stats.get("divine_sense") or 0) + boss_crit_bonus * 2
        player_state["stats"] = stats

    # 构建 Boss 战斗数据
    boss_bundle = _build_boss_battle_bundle(boss)
    boss_state = boss_bundle.copy()

    # 执行对战模拟
    result = legacy_service._simulate_duel_battle(player_bundle, boss_bundle, player_state, boss_state)

    won = result.get("winner_tg") == tg

    daily_attempts_used = daily_used + 1
    rewards: dict[str, Any] = {"items": [], "stone": 0, "cultivation": 0}

    with Session() as session:
        if ticket_cost > 0:
            apply_spiritual_stone_delta(session, tg, -ticket_cost, action_text="挑战Boss门票")

        daily_attempts_used, daily_limit = _claim_personal_boss_attempt_in_session(session, tg, boss_id, won, daily_limit)

        if won:
            loot_items = _roll_boss_loot(boss)
            rewards["items"] = _grant_boss_loot_items_in_session(session, tg, loot_items)

            stone_min = int(boss.get("stone_reward_min") or 0)
            stone_max = int(boss.get("stone_reward_max") or 0)
            if stone_max > 0:
                stone_amount = random.randint(stone_min, max(stone_max, stone_min))
                if stone_amount > 0:
                    apply_spiritual_stone_delta(session, tg, stone_amount, action_text="击败Boss灵石奖励")
                    rewards["stone"] = stone_amount

            rewards["cultivation"] = _apply_boss_cultivation_reward_in_session(
                session,
                tg,
                int(boss.get("cultivation_reward") or 0),
                legacy_service,
            )

        if won:
            _add_journal_in_session(
                session,
                tg,
                "boss",
                "Boss讨伐胜利",
                f"击败【{boss['name']}】{'，获得灵石 ' + str(rewards['stone']) if rewards['stone'] else ''}"
                f"{'，修为 +' + str(rewards['cultivation']) if rewards['cultivation'] else ''}",
            )
        else:
            _add_journal_in_session(
                session,
                tg,
                "boss",
                "Boss讨伐失败",
                f"挑战【{boss['name']}】惜败，损失门票 {ticket_cost} 灵石。",
            )
        _queue_user_view_cache_invalidation(session, tg)
        session.commit()

    if won:
        record_boss_metrics(tg, kill=1)

    battle_log = result.get("battle_log") or []
    summary = _format_boss_battle_summary(boss, result, won, rewards)
    challenger_actor = result.get("challenger_actor") or {}
    defender_actor = result.get("defender_actor") or {}

    if talisman_active_effects:
        legacy_service.set_active_talisman(tg, None)
    curse_event = legacy_service._apply_artifact_curse_backlash(
        tg,
        "personal_boss",
        equipped_artifacts=legacy_service.collect_equipped_artifacts(tg),
    )
    legacy_service._record_artifact_curse_event(tg, curse_event)
    updated_profile = serialize_profile(get_profile(tg, create=False))

    return {
        "boss": boss,
        "won": won,
        "summary": summary,
        "battle_log": battle_log,
        "round_count": result.get("round_count", 0),
        "player_hp_remaining": int(challenger_actor.get("hp") or 0),
        "boss_hp_remaining": int(defender_actor.get("hp") or 0),
        "rewards": rewards,
        "active_talisman_effects": talisman_active_effects,
        "curse_event": curse_event,
        "profile": updated_profile,
        "daily_attempts_used": daily_attempts_used,
        "daily_attempts_limit": daily_limit,
        "daily_attempts_remaining": _remaining_attempts(daily_limit, daily_attempts_used),
        "daily_attempts_unlimited": daily_limit <= 0,
    }


def _build_boss_battle_bundle(boss: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "tg": 0,
        "name": boss["name"],
        "realm_stage": boss["realm_stage"],
        "realm_layer": 9,
        "cultivation": 0,
        "bone": int(boss.get("body_movement") or 10),
        "comprehension": 10,
        "divine_sense": int(boss.get("divine_sense") or 10),
        "fortune": int(boss.get("fortune") or 10),
        "willpower": 10,
        "charisma": 10,
        "karma": 10,
        "qi_blood": int(boss.get("qi_blood") or 500),
        "true_yuan": int(boss.get("true_yuan") or 200),
        "body_movement": int(boss.get("body_movement") or 10),
        "attack_power": int(boss.get("attack_power") or 30),
        "defense_power": int(boss.get("defense_power") or 15),
        "consented": True,
    }
    stats = {
        "bone": float(profile["bone"]),
        "comprehension": float(profile["comprehension"]),
        "divine_sense": float(profile["divine_sense"]),
        "fortune": float(profile["fortune"]),
        "willpower": float(profile["willpower"]),
        "charisma": float(profile["charisma"]),
        "karma": float(profile["karma"]),
        "qi_blood": float(profile["qi_blood"]),
        "true_yuan": float(profile["true_yuan"]),
        "body_movement": float(profile["body_movement"]),
        "attack_power": float(profile["attack_power"]),
        "defense_power": float(profile["defense_power"]),
        "duel_rate_bonus": 0.0,
    }
    stage_index = max(realm_index(boss.get("realm_stage")), 0)
    realm_score = 560 + stage_index * 1750 + 9 * 200
    attribute_score = (
        stats["bone"] * 5.2 + stats["comprehension"] * 5.8
        + stats["divine_sense"] * 5.9 + stats["fortune"] * 2.4
        + stats["willpower"] * 4.6 + stats["charisma"] * 1.5
        + stats["karma"] * 3.0
    )
    combat_score = (
        stats["attack_power"] * 19.5 + stats["defense_power"] * 17.5
        + stats["body_movement"] * 12.5 + stats["qi_blood"] * 0.40
        + stats["true_yuan"] * 0.32
    )
    power = (realm_score + (attribute_score + combat_score) * 1.0) * 0.75

    # 为 Boss 构建合成功法配置
    combat_config: dict[str, Any] = {"skills": [], "passives": [], "openings": []}

    skill_name = boss.get("skill_name")
    if skill_name:
        combat_config["skills"].append({
            "kind": "attack",
            "name": skill_name,
            "ratio_percent": int(boss.get("skill_ratio_percent") or 130),
            "hit_bonus": int(boss.get("skill_hit_bonus") or 0),
        })

    passive_name = boss.get("passive_name")
    passive_kind = boss.get("passive_effect_kind")
    if passive_name and passive_kind:
        combat_config["passives"].append({
            "kind": passive_kind,
            "name": passive_name,
            "chance": int(boss.get("passive_chance") or 25),
            "ratio_percent": int(boss.get("passive_ratio_percent") or 0),
        })

    flavor = boss.get("flavor_text") or ""
    if flavor:
        combat_config["openings"].append(flavor)

    synthetic_technique = {
        "name": boss["name"] + "·本命神通",
        "combat_config": combat_config,
    }

    return {
        "profile": profile,
        "quality": "凡品",
        "quality_payload": {"combat_factor": 1.0},
        "root_factor": 1.0,
        "realm_score": float(realm_score),
        "stats": stats,
        "artifact_effects": {},
        "talisman_effects": {},
        "sect_effects": {},
        "technique_effects": {},
        "title_effects": {},
        "power": float(power),
        "combat_power": int(power),
        "equipped_artifacts": [],
        "active_talisman": None,
        "current_technique": synthetic_technique,
        "current_title": None,
    }


def _roll_boss_loot(boss: dict[str, Any]) -> list[dict[str, Any]]:
    drops: list[dict[str, Any]] = []
    loot_specs = [
        ("pill", boss.get("loot_pills_json")),
        ("material", boss.get("loot_materials_json")),
        ("artifact", boss.get("loot_artifacts_json")),
        ("talisman", boss.get("loot_talismans_json")),
        ("recipe", boss.get("loot_recipes_json")),
        ("technique", boss.get("loot_techniques_json")),
    ]
    for kind, loot_json in loot_specs:
        if not loot_json or not isinstance(loot_json, list):
            continue
        for entry in loot_json:
            if not isinstance(entry, dict):
                continue
            ref_id = int(entry.get("ref_id") or 0)
            if ref_id <= 0:
                continue
            chance = _boss_loot_chance(entry)
            if not roll_probability_percent(chance)["success"]:
                continue
            qty_min = max(int(entry.get("quantity_min") or 1), 1)
            qty_max = max(int(entry.get("quantity_max") or qty_min), qty_min)
            quantity = random.randint(qty_min, qty_max)
            if quantity > 0:
                drops.append({"kind": kind, "ref_id": ref_id, "quantity": quantity})
    return drops


def _format_boss_battle_summary(boss: dict[str, Any], result: dict[str, Any], won: bool, rewards: dict[str, Any]) -> str:
    if won:
        parts = [f"大败【{boss['name']}】！鏖战 {result.get('round_count', 0)} 回合，终将其斩于马下。"]
        if rewards.get("stone"):
            parts.append(f"获得灵石 {rewards['stone']}。")
        if rewards.get("cultivation"):
            parts.append(f"修为精进 {rewards['cultivation']}。")
        if rewards.get("items"):
            parts.append("另得灵物若干。")
        return "".join(parts)
    else:
        return f"与【{boss['name']}】苦战 {result.get('round_count', 0)} 合，终究不敌，败下阵来。"


# ── 世界 Boss ──────────────────────────────────────────────────


_WORLD_BOSS_ATTACK_COOLDOWN_SECONDS = 30
_WORLD_BOSS_SPAWN_INTERVAL_HOURS = 6
_WORLD_BOSS_HP_MULTIPLIER = 12
_WORLD_BOSS_TIMEOUT_HOURS = 3


def _parse_serialized_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def get_world_boss_status_for_user(tg: int) -> dict[str, Any]:
    settle_expired_world_bosses()
    instance = get_active_world_boss()
    if not instance:
        return {"active": False, "instance": None, "boss": None, "player_damage": None, "ranking": []}

    boss = serialize_boss_config(get_boss_config(int(instance["boss_id"])))
    player_damage = None
    all_damages = list_world_boss_damages(int(instance["id"]))
    for dmg in all_damages:
        if int(dmg.get("tg") or 0) == tg:
            player_damage = dmg
            break

    # 伤害排名（前十）
    ranking = all_damages[:10]
    from bot.sql_helper.sql_xiuxian import get_emby_name_map
    tgs = [int(r["tg"]) for r in ranking]
    name_map = get_emby_name_map(tgs) if tgs else {}
    for r in ranking:
        r["display_name"] = name_map.get(int(r["tg"]), f"TG {r['tg']}")

    # 攻击冷却
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    cooldown_remaining = 0
    if player_damage:
        last_at = _parse_serialized_datetime(player_damage.get("last_attack_at"))
        if last_at:
            elapsed = (now - last_at).total_seconds()
            cooldown_remaining = max(int(_WORLD_BOSS_ATTACK_COOLDOWN_SECONDS - elapsed), 0)

    return {
        "active": True,
        "instance": instance,
        "boss": boss,
        "player_damage": player_damage,
        "cooldown_seconds_remaining": cooldown_remaining,
        "ranking": ranking,
    }


def attack_world_boss(tg: int) -> dict[str, Any]:
    legacy_service = _legacy_service()
    profile_data = serialize_profile(get_profile(tg, create=False))
    if not profile_data or not profile_data.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立")

    settle_expired_world_bosses()
    instance = get_active_world_boss()
    if not instance:
        raise ValueError("当下并无世界Boss降临，天地一片安宁。")

    boss = serialize_boss_config(get_boss_config(int(instance["boss_id"])))
    if not boss:
        raise ValueError("Boss已消散，等待下次降临吧。")

    # 冷却检查
    from datetime import datetime, timezone
    all_damages = list_world_boss_damages(int(instance["id"]))
    player_dmg = None
    for dmg in all_damages:
        if int(dmg.get("tg") or 0) == tg:
            player_dmg = dmg
            break
    now = datetime.now(timezone.utc)
    if player_dmg:
        last_attack_at = _parse_serialized_datetime(player_dmg.get("last_attack_at"))
    else:
        last_attack_at = None
    if last_attack_at:
        elapsed = (now - last_attack_at).total_seconds()
        if elapsed < _WORLD_BOSS_ATTACK_COOLDOWN_SECONDS:
            remaining = int(_WORLD_BOSS_ATTACK_COOLDOWN_SECONDS - elapsed)
            raise ValueError(f"气力未复，还需等待 {remaining} 秒方可再次出手。")

    # 计算玩家战力
    bundle = legacy_service.serialize_full_profile(tg)
    player_bundle = legacy_service._battle_bundle(bundle, apply_random=False)
    stats = player_bundle.get("stats") or {}
    talisman_active_effects = player_bundle.get("talisman_active_effects") or {}

    # 伤害公式（简化版）
    attack_power = float(stats.get("attack_power") or 0)
    defense_power = float(boss.get("defense_power") or 0)
    divine_sense = float(stats.get("divine_sense") or 0)
    fortune = float(stats.get("fortune") or 0)
    combat_power = float(player_bundle.get("power") or bundle.get("combat_power") or 0)

    base_damage = (
        attack_power * random.uniform(1.8, 2.6)
        + combat_power * random.uniform(0.018, 0.028)
        + divine_sense * 0.75
        + fortune * 0.45
    )
    crit_chance = min(8 + divine_sense * 0.15 + fortune * 0.1 + max(float(talisman_active_effects.get("boss_crit_bonus") or 0), 0.0), 45)
    crit = roll_probability_percent(int(crit_chance))["success"]
    if crit:
        base_damage *= 1.5
    damage_floor = max(8, int(attack_power * 0.6), int(combat_power * 0.004))
    effective_damage = max(int(base_damage - defense_power * 0.18), damage_floor)
    boss_damage_bonus = max(float(talisman_active_effects.get("boss_damage_bonus") or 0), 0.0)
    if boss_damage_bonus > 0:
        effective_damage = max(int(round(effective_damage * (1 + min(boss_damage_bonus, 80.0) / 100.0))), effective_damage + 1)

    with Session() as session:
        instance_row = _active_world_boss_instance_for_update(session, int(instance["id"]))
        if instance_row is None or instance_row.status != "active" or instance_row.expires_at <= utcnow():
            raise ValueError("Boss已消散，等待下次降临吧。")
        damage_row = _world_boss_damage_for_update(session, int(instance_row.id), tg)
        now = datetime.now(timezone.utc)
        if damage_row and damage_row.last_attack_at:
            last_attack_at = _parse_serialized_datetime(damage_row.last_attack_at)
            if last_attack_at:
                elapsed = (now - last_attack_at).total_seconds()
                if elapsed < _WORLD_BOSS_ATTACK_COOLDOWN_SECONDS:
                    remaining = int(_WORLD_BOSS_ATTACK_COOLDOWN_SECONDS - elapsed)
                    raise ValueError(f"气力未复，还需等待 {remaining} 秒方可再次出手。")

        instance_row.current_hp = max(int(instance_row.current_hp or 0) - effective_damage, 0)
        boss_defeated = instance_row.current_hp <= 0
        if boss_defeated:
            instance_row.status = "defeated"
            instance_row.defeated_at = utcnow()
        instance_row.updated_at = utcnow()

        if damage_row is None:
            damage_row = XiuxianWorldBossDamage(
                instance_id=int(instance_row.id),
                tg=int(tg),
                total_damage=0,
                attack_count=0,
            )
            session.add(damage_row)
            session.flush()
        damage_row.total_damage = max(int(damage_row.total_damage or 0) + effective_damage, 0)
        damage_row.attack_count = max(int(damage_row.attack_count or 0) + 1, 1)
        damage_row.last_attack_at = utcnow()
        damage_row.updated_at = utcnow()
        _add_journal_in_session(
            session,
            tg,
            "boss",
            "攻击世界Boss",
            f"对【{boss['name']}】造成 {effective_damage} 点伤害{'（暴击）' if crit else ''}。"
            f"{' Boss已被击败！' if boss_defeated else ''}",
        )
        updated_instance = serialize_world_boss_instance(instance_row)
        damage_record = serialize_world_boss_damage(damage_row)
        session.commit()

    # 击杀则结算奖励
    settlement = None
    if boss_defeated:
        settlement = _settle_world_boss_kill(int(instance["id"]))
    if talisman_active_effects:
        legacy_service.set_active_talisman(tg, None)
    curse_event = legacy_service._apply_artifact_curse_backlash(
        tg,
        "world_boss",
        equipped_artifacts=legacy_service.collect_equipped_artifacts(tg),
    )
    legacy_service._record_artifact_curse_event(tg, curse_event)

    # 记录世界 Boss 伤害成就
    record_boss_metrics(tg, world_damage=effective_damage)

    return {
        "boss": boss,
        "instance": updated_instance,
        "damage_dealt": effective_damage,
        "crit": crit,
        "boss_defeated": boss_defeated,
        "player_total_damage": int((damage_record or {}).get("total_damage") or 0),
        "player_attack_count": int((damage_record or {}).get("attack_count") or 0),
        "active_talisman_effects": talisman_active_effects,
        "curse_event": curse_event,
        "settlement": settlement,
    }


def _settle_world_boss_kill(instance_id: int) -> dict[str, Any]:
    from bot.sql_helper.sql_xiuxian import get_emby_name_map

    rankings: list[dict[str, Any]] = []
    boss: dict[str, Any] | None = None
    with Session() as session:
        instance_row = _active_world_boss_instance_for_update(session, instance_id)
        if instance_row is None:
            return {"rankings": [], "mvp": None, "already_settled": True}
        if instance_row.status == "settled":
            return {"rankings": [], "mvp": None, "already_settled": True}
        if instance_row.status not in {"active", "defeated"}:
            return {"rankings": [], "mvp": None, "already_settled": True}
        boss_id = int(instance_row.boss_id or 0)
        boss_row = session.query(XiuxianBossConfig).filter(XiuxianBossConfig.id == boss_id).first() if boss_id else None
        boss = serialize_boss_config(boss_row) if boss_row else None
        damage_rows = (
            session.query(XiuxianWorldBossDamage)
            .filter(XiuxianWorldBossDamage.instance_id == int(instance_id))
            .order_by(XiuxianWorldBossDamage.total_damage.desc())
            .all()
        )
        damages = [serialize_world_boss_damage(row) for row in damage_rows]
        if not damages:
            instance_row.status = "settled"
            if instance_row.defeated_at is None:
                instance_row.defeated_at = utcnow()
            instance_row.updated_at = utcnow()
            session.commit()
            return {"rankings": [], "mvp": None}

        tgs = [int(d["tg"]) for d in damages]
        name_map = get_emby_name_map(tgs) if tgs else {}

        for rank_idx, dmg in enumerate(damages):
            tg = int(dmg["tg"])
            rank = rank_idx + 1
            tier = "participation"
            loot_multiplier = 1
            if rank == 1:
                tier = "mvp"
                loot_multiplier = 3
            elif rank <= 3:
                tier = "top3"
                loot_multiplier = 2
            elif rank <= 10:
                tier = "top10"
                loot_multiplier = 1

            rankings.append({
                "rank": rank,
                "tg": tg,
                "display_name": name_map.get(tg, f"TG {tg}"),
                "total_damage": int(dmg.get("total_damage") or 0),
                "tier": tier,
                "loot_multiplier": loot_multiplier,
                "rewarded": False,
            })

        if boss:
            legacy_service = _legacy_service()
            for entry in rankings:
                tg = entry["tg"]
                multiplier = entry["loot_multiplier"]
                stone_min = int(boss.get("stone_reward_min") or 0)
                stone_max = int(boss.get("stone_reward_max") or 0)
                stone_amount = random.randint(stone_min, max(stone_max, stone_min)) * multiplier
                if stone_amount > 0:
                    apply_spiritual_stone_delta(session, tg, stone_amount, action_text="世界Boss排名灵石奖励")
                cultivation_reward = _apply_boss_cultivation_reward_in_session(
                    session,
                    tg,
                    int(boss.get("cultivation_reward") or 0) * multiplier,
                    legacy_service,
                )
                granted_items: list[dict[str, Any]] = []
                for _ in range(multiplier):
                    loot_items = _roll_boss_loot(boss)
                    granted_items.extend(_grant_boss_loot_items_in_session(session, tg, loot_items))
                if entry["tier"] == "mvp":
                    _add_journal_in_session(
                        session,
                        tg,
                        "boss",
                        "世界Boss MVP",
                        f"在讨伐【{boss['name']}】中伤害排名第一，获得MVP称号！",
                    )
                entry["stone_reward"] = stone_amount
                entry["cultivation_reward"] = cultivation_reward
                entry["items"] = granted_items
                entry["rewarded"] = True
                _queue_user_view_cache_invalidation(session, tg)
        instance_row.status = "settled"
        if instance_row.defeated_at is None:
            instance_row.defeated_at = utcnow()
        instance_row.updated_at = utcnow()
        session.commit()

    mvp = rankings[0] if rankings else None
    if boss and mvp:
        record_boss_metrics(mvp["tg"], world_mvp=1)

    return {
        "rankings": rankings,
        "mvp": rankings[0] if rankings else None,
        "boss_name": boss["name"] if boss else "",
    }


def settle_world_boss_timeout(instance_id: int) -> dict[str, Any]:
    with Session() as session:
        instance_row = _active_world_boss_instance_for_update(session, instance_id)
        if instance_row is None or instance_row.status != "active":
            return {"rankings": [], "escaped": False, "already_settled": True}
        damage_rows = (
            session.query(XiuxianWorldBossDamage)
            .filter(XiuxianWorldBossDamage.instance_id == int(instance_id))
            .order_by(XiuxianWorldBossDamage.total_damage.desc())
            .all()
        )
        for damage_row in damage_rows:
            tg = int(damage_row.tg or 0)
            consolation_stone = random.randint(20, 80)
            apply_spiritual_stone_delta(session, tg, consolation_stone, action_text="世界Boss参与奖")
            _add_journal_in_session(
                session,
                tg,
                "boss",
                "世界Boss参与奖",
                f"世界Boss已遁走，获得参与奖 {consolation_stone} 灵石。",
            )
            _queue_user_view_cache_invalidation(session, tg)
        instance_row.status = "escaped"
        instance_row.updated_at = utcnow()
        session.commit()

    return {"rankings": [], "escaped": True}


def spawn_world_boss(boss_id: int | None = None) -> dict[str, Any]:
    settle_expired_world_bosses()
    existing = get_active_world_boss()
    if existing:
        raise ValueError("当前已有世界Boss降临，请等待其被击败或消散后再手动降临。")
    if int(boss_id or 0) <= 0:
        last_spawned_at = _last_world_boss_spawned_at()
        if last_spawned_at is not None:
            elapsed = utcnow() - last_spawned_at
            interval = timedelta(hours=_WORLD_BOSS_SPAWN_INTERVAL_HOURS)
            if elapsed < interval:
                remaining_minutes = max(int((interval - elapsed).total_seconds() // 60), 1)
                raise ValueError(f"距离下次世界Boss降临还需约 {remaining_minutes} 分钟。")

    bosses = list_boss_configs(boss_type="world")
    if not bosses:
        raise ValueError("当前没有已启用的世界Boss配置。")

    if int(boss_id or 0) > 0:
        boss = next((item for item in bosses if int(item.get("id") or 0) == int(boss_id)), None)
        if boss is None:
            raise ValueError("指定的世界Boss不存在或未启用。")
    else:
        boss = random.choice(bosses)
    base_hp = int(boss.get("hp") or 500)
    max_hp = base_hp * _WORLD_BOSS_HP_MULTIPLIER
    expires_at = utcnow() + timedelta(hours=_WORLD_BOSS_TIMEOUT_HOURS)

    instance = create_world_boss_instance(int(boss["id"]), max_hp, expires_at)

    # 向主群广播降临消息
    from bot.plugins.xiuxian_game.plugin_bot_handlers import _format_broadcast_card, _main_group_chat_id, _md_escape
    try:
        chat_id = _main_group_chat_id()
        if chat_id:
            text = _format_broadcast_card(
                "世界 Boss 降临",
                emoji="👹",
                lines=[
                    f"🐉 **{_md_escape(boss['name'])}** 撕裂虚空而来！",
                    f"❤️ 全服HP：`{max_hp}/{max_hp}`",
                    f"⏳ 存在时限：`{expires_at.strftime('%m月%d日 %H:%M')}` (北京时间)",
                ],
                footer="⚔️ 所有在群道友速来降妖除魔！",
            )
            # 挂载到实例上，由 bot 客户端代为发送
            instance["broadcast_text"] = text
            instance["broadcast_chat_id"] = chat_id
    except Exception:
        pass

    return {"boss": boss, "instance": instance}


def try_spawn_world_boss() -> dict[str, Any] | None:
    try:
        return spawn_world_boss()
    except ValueError:
        return None
