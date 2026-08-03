from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from typing import Any

from bot.sql_helper.sql_xiuxian import (
    DEFAULT_SETTINGS,
    Session,
    XiuxianEncounterInstance,
    XiuxianEncounterTemplate,
    XiuxianProfile,
    apply_spiritual_stone_delta,
    assert_artifact_receivable_by_user,
    create_encounter_instance,
    create_encounter_template as sql_create_encounter_template,
    delete_encounter_template as sql_delete_encounter_template,
    find_active_group_encounter,
    get_encounter_instance,
    get_latest_group_encounter_time,
    get_xiuxian_settings,
    list_encounter_templates as sql_list_encounter_templates,
    patch_encounter_instance,
    patch_encounter_template as sql_patch_encounter_template,
    serialize_encounter_instance,
    serialize_encounter_template,
    serialize_artifact,
    serialize_profile,
    utcnow,
)


AUTO_ENCOUNTER_PITY_STEP = 6
AUTO_ENCOUNTER_FORCE_AFTER = 12
AUTO_ENCOUNTER_STREAKS: dict[int, int] = {}


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def _legacy_world_service():
    from bot.plugins.xiuxian_game import world_service as legacy_world_service

    return legacy_world_service


MARKDOWN_ESCAPE_PATTERN = re.compile(r"([_*\[`])")
# 群播报卡片分隔线(与斗罗/斗破/修仙播报同款样式)
_MD_BROADCAST_DIVIDER = "━" * 18


def _md_escape(value: Any) -> str:
    return MARKDOWN_ESCAPE_PATTERN.sub(r"\\\1", str(value or ""))


def _format_broadcast_card(title: str, *, emoji: str, lines: list[str], footer: str | None = None) -> str:
    """带分隔线边框的群播报卡片:图标标题 + 分隔线 + 正文 + 分隔线。"""
    rows = [f"{emoji} **{_md_escape(title)}** {emoji}", _MD_BROADCAST_DIVIDER]
    rows.extend(str(line).strip() for line in lines if str(line or "").strip())
    if footer:
        rows.extend([_MD_BROADCAST_DIVIDER, str(footer).strip()])
    else:
        rows.append(_MD_BROADCAST_DIVIDER)
    return "\n".join(rows)


def list_encounter_templates(enabled_only: bool = False) -> list[dict[str, Any]]:
    _legacy_service().ensure_seed_data()
    return sql_list_encounter_templates(enabled_only=enabled_only)


def create_encounter_template(**fields) -> dict[str, Any]:
    return sql_create_encounter_template(**fields)


def patch_encounter_template(template_id: int, **fields) -> dict[str, Any] | None:
    return sql_patch_encounter_template(template_id, **fields)


def delete_encounter_template(template_id: int) -> bool:
    return sql_delete_encounter_template(template_id)


def _weighted_choice(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    total = sum(max(int(row.get("weight") or 0), 1) for row in rows)
    pick = random.randint(1, max(total, 1))
    cursor = 0
    for row in rows:
        cursor += max(int(row.get("weight") or 0), 1)
        if pick <= cursor:
            return row
    return rows[-1]


def _encounter_reward_payload(template: dict[str, Any]) -> dict[str, Any]:
    stone_min = max(int(template.get("reward_stone_min") or 0), 0)
    stone_max = max(int(template.get("reward_stone_max") or stone_min), stone_min)
    cultivation_min = max(int(template.get("reward_cultivation_min") or 0), 0)
    cultivation_max = max(int(template.get("reward_cultivation_max") or cultivation_min), cultivation_min)
    quantity_min = max(int(template.get("reward_item_quantity_min") or 1), 1)
    quantity_max = max(int(template.get("reward_item_quantity_max") or quantity_min), quantity_min)
    payload = {
        "stone_reward": random.randint(stone_min, stone_max) if stone_max > 0 else 0,
        "cultivation_reward": random.randint(cultivation_min, cultivation_max) if cultivation_max > 0 else 0,
        "reward_item_kind": template.get("reward_item_kind"),
        "reward_item_ref_id": int(template.get("reward_item_ref_id") or 0) or None,
        "reward_item_quantity": random.randint(quantity_min, quantity_max) if template.get("reward_item_kind") and template.get("reward_item_ref_id") else 0,
    }
    return payload


def maybe_spawn_group_encounter(chat_id: int) -> dict[str, Any] | None:
    chat_id_value = int(chat_id or 0)
    if not chat_id_value:
        return None
    _legacy_service().ensure_seed_data()
    if find_active_group_encounter(chat_id_value):
        AUTO_ENCOUNTER_STREAKS.pop(chat_id_value, None)
        return None

    settings = get_xiuxian_settings()
    cooldown_minutes = max(
        int(settings.get("encounter_group_cooldown_minutes", DEFAULT_SETTINGS.get("encounter_group_cooldown_minutes", 12)) or 0),
        0,
    )
    latest_time = get_latest_group_encounter_time(chat_id_value)
    if latest_time and utcnow() - latest_time < timedelta(minutes=cooldown_minutes):
        AUTO_ENCOUNTER_STREAKS.pop(chat_id_value, None)
        return None

    base_chance = max(
        min(int(settings.get("encounter_spawn_chance", DEFAULT_SETTINGS.get("encounter_spawn_chance", 5)) or 0), 100),
        0,
    )
    if base_chance <= 0:
        AUTO_ENCOUNTER_STREAKS.pop(chat_id_value, None)
        return None
    streak = max(int(AUTO_ENCOUNTER_STREAKS.get(chat_id_value) or 0), 0) + 1
    effective_chance = min(base_chance + max(streak - 1, 0) * AUTO_ENCOUNTER_PITY_STEP, 100)
    force_spawn = streak >= AUTO_ENCOUNTER_FORCE_AFTER
    if not force_spawn and random.randint(1, 100) > effective_chance:
        AUTO_ENCOUNTER_STREAKS[chat_id_value] = streak
        return None

    template = _weighted_choice(list_encounter_templates(enabled_only=True))
    if not template:
        AUTO_ENCOUNTER_STREAKS[chat_id_value] = streak
        return None

    active_seconds = max(
        int(template.get("active_seconds") or settings.get("encounter_active_seconds", DEFAULT_SETTINGS.get("encounter_active_seconds", 90)) or 90),
        15,
    )
    instance = create_encounter_instance(
        template_id=int(template.get("id") or 0) or None,
        template_name=str(template.get("name") or "无名奇遇"),
        group_chat_id=chat_id_value,
        button_text=str(template.get("button_text") or "争抢机缘"),
        reward_payload=_encounter_reward_payload(template),
        expires_at=utcnow() + timedelta(seconds=active_seconds),
    )
    AUTO_ENCOUNTER_STREAKS.pop(chat_id_value, None)
    return {"template": template, "instance": instance}


def spawn_group_encounter(chat_id: int, template_id: int | None = None) -> dict[str, Any]:
    if not int(chat_id or 0):
        raise ValueError("缺少可投放的群聊 ID。")
    _legacy_service().ensure_seed_data()
    if find_active_group_encounter(int(chat_id)):
        raise ValueError("当前群里已有未结束的奇遇，请等这桩机缘结算后再投放。")

    template: dict[str, Any] | None = None
    if int(template_id or 0) > 0:
        template = next(
            (
                row
                for row in sql_list_encounter_templates(enabled_only=False)
                if int(row.get("id") or 0) == int(template_id)
            ),
            None,
        )
        if template is None:
            raise ValueError("奇遇模板不存在。")
        if not bool(template.get("enabled", True)):
            raise ValueError("该奇遇模板未启用，无法手动投放。")
    else:
        template = _weighted_choice(list_encounter_templates(enabled_only=True))
        if template is None:
            raise ValueError("当前没有可投放的启用奇遇模板。")

    settings = get_xiuxian_settings()
    active_seconds = max(
        int(template.get("active_seconds") or settings.get("encounter_active_seconds", DEFAULT_SETTINGS.get("encounter_active_seconds", 90)) or 90),
        15,
    )
    instance = create_encounter_instance(
        template_id=int(template.get("id") or 0) or None,
        template_name=str(template.get("name") or "无名奇遇"),
        group_chat_id=int(chat_id),
        button_text=str(template.get("button_text") or "争抢机缘"),
        reward_payload=_encounter_reward_payload(template),
        expires_at=utcnow() + timedelta(seconds=active_seconds),
    )
    return {"template": template, "instance": instance}


def mark_group_encounter_message(instance_id: int, message_id: int) -> dict[str, Any] | None:
    return patch_encounter_instance(instance_id, message_id=message_id)


def _encounter_reward_summary(reward_payload: dict[str, Any]) -> str:
    rows = []
    if int(reward_payload.get("stone_reward") or 0) > 0:
        rows.append(f"{int(reward_payload['stone_reward'])} 灵石")
    if int(reward_payload.get("cultivation_reward") or 0) > 0:
        rows.append(f"{int(reward_payload['cultivation_reward'])} 修为")
    reward_item_kind = reward_payload.get("reward_item_kind")
    reward_item_ref_id = int(reward_payload.get("reward_item_ref_id") or 0)
    reward_item_quantity = int(reward_payload.get("reward_item_quantity") or 0)
    if reward_item_kind and reward_item_ref_id and reward_item_quantity > 0:
        item = _legacy_world_service()._get_item_payload(reward_item_kind, reward_item_ref_id)
        item_name = (item or {}).get("name") or f"{reward_item_kind}#{reward_item_ref_id}"
        rows.append(f"{reward_item_quantity} 个{item_name}")
    return "、".join(rows) if rows else "随机机缘"


def render_group_encounter_text(template: dict[str, Any], instance: dict[str, Any]) -> str:
    reward_summary = _encounter_reward_summary(instance.get("reward_payload") or {})
    action_text = template.get("broadcast_text") or f"群内忽有异象显化，{template.get('name') or '一桩奇遇'} 出世。"
    expires_at = instance.get("expires_at") or "很快"
    requirements = []
    if template.get("min_realm_stage"):
        requirements.append(f"境界至少 {_claim_requirement_message(template)}")
    if int(template.get("min_combat_power") or 0) > 0:
        requirements.append(f"战力至少 {int(template.get('min_combat_power') or 0)}")
    requirement_text = "；".join(requirements) if requirements else "无门槛，先到先得"
    return (
        _format_broadcast_card(
            "群机缘降世",
            emoji="🌠",
            lines=[
                f"📜 奇遇：**{_md_escape(template.get('name') or '未命名奇遇')}**",
                f"📝 异象：{_md_escape(action_text)}",
                f"🎁 奖励预览：{_md_escape(reward_summary)}",
                f"📌 领取要求：{_md_escape(requirement_text)}",
                f"⏳ 截止：{_md_escape(expires_at)}",
            ],
            footer="⚡ 谁先抢到，机缘便归谁。",
        )
    )


def _claim_requirement_message(template: dict[str, Any]) -> str:
    legacy_service = _legacy_service()
    if template.get("min_realm_stage"):
        return legacy_service.format_realm_requirement(template.get("min_realm_stage"), template.get("min_realm_layer"))
    return "当前修为"


def _assert_encounter_reward_receivable(tg: int, reward_payload: dict[str, Any]) -> None:
    reward_kind = str(reward_payload.get("reward_item_kind") or "")
    reward_ref_id = int(reward_payload.get("reward_item_ref_id") or 0)
    reward_quantity = int(reward_payload.get("reward_item_quantity") or 0)
    if reward_kind != "artifact" or reward_ref_id <= 0 or reward_quantity <= 0:
        return
    artifact = serialize_artifact(_legacy_service().get_artifact(reward_ref_id))
    if not artifact:
        raise ValueError("未寻得此宝踪迹，或许早已流失于岁月之中。")
    if bool(artifact.get("unique_item")) and reward_quantity > 1:
        raise ValueError(f"唯一法宝【{artifact.get('name') or reward_ref_id}】每次只能获得 1 件。")
    assert_artifact_receivable_by_user(int(tg), reward_ref_id, allow_existing_owner=False)


def claim_group_encounter(instance_id: int, tg: int) -> dict[str, Any]:
    legacy_service = _legacy_service()
    bundle = legacy_service.serialize_full_profile(tg)
    profile_data = bundle.get("profile") or {}
    if not profile_data.get("consented"):
        raise ValueError("你尚未踏入仙途，道基未立。")
    if bundle.get("capabilities", {}).get("gender_required"):
        raise ValueError(str(bundle.get("capabilities", {}).get("gender_lock_reason") or "请先设置性别。"))
    # Daily encounter claim limit
    from bot.plugins.xiuxian_game.world_service import _ensure_daily_limit
    from bot.sql_helper.sql_xiuxian import get_profile as _get_profile

    profile_obj = _get_profile(tg, create=False)
    if profile_obj is not None:
        _ensure_daily_limit(profile_obj, "encounter_daily_count", "encounter_day_key", "encounter_claim_daily_limit", "奇遇领取")

    with Session() as session:
        instance = (
            session.query(XiuxianEncounterInstance)
            .filter(XiuxianEncounterInstance.id == instance_id)
            .with_for_update()
            .first()
        )
        if instance is None:
            raise ValueError("奇遇已经消散。")
        template = None
        if instance.template_id:
            template = session.query(XiuxianEncounterTemplate).filter(XiuxianEncounterTemplate.id == instance.template_id).first()
        template_payload = serialize_encounter_template(template) or {
            "name": instance.template_name,
            "button_text": instance.button_text,
            "success_text": None,
            "broadcast_text": None,
            "min_realm_stage": None,
            "min_realm_layer": 1,
            "min_combat_power": 0,
        }
        now = utcnow()
        if instance.status != "active":
            raise ValueError("这桩奇遇已经被别人抢走了。")
        if instance.expires_at <= now:
            instance.status = "expired"
            instance.updated_at = now
            session.commit()
            raise ValueError("你还是慢了一步，机缘已经消散。")
        if template_payload.get("min_realm_stage") and not legacy_service.realm_requirement_met(
            profile_data,
            template_payload.get("min_realm_stage"),
            template_payload.get("min_realm_layer"),
        ):
            raise ValueError(f"境界不足，需要至少达到 {_claim_requirement_message(template_payload)}。")
        if int(bundle.get("combat_power") or 0) < int(template_payload.get("min_combat_power") or 0):
            raise ValueError(f"战力不足，需要至少 {int(template_payload.get('min_combat_power') or 0)} 战力。")

        reward_payload = dict(instance.reward_payload or {})
        _assert_encounter_reward_receivable(tg, reward_payload)
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你尚未踏入仙途，道基未立。")

        cultivation_gain = max(int(reward_payload.get("cultivation_reward") or 0), 0)
        raw_cultivation_gain = cultivation_gain
        cultivation_gain, gain_meta = legacy_service.adjust_cultivation_gain_for_social_mode(
            profile,
            cultivation_gain,
            settings=legacy_service.get_xiuxian_settings(),
        )
        stone_reward = max(int(reward_payload.get("stone_reward") or 0), 0)
        layer, cultivation, upgraded_layers, remaining = legacy_service.apply_cultivation_gain(
            legacy_service.normalize_realm_stage(profile.realm_stage or legacy_service.FIRST_REALM_STAGE),
            int(profile.realm_layer or 1),
            int(profile.cultivation or 0),
            cultivation_gain,
        )
        if stone_reward > 0:
            apply_spiritual_stone_delta(
                session,
                tg,
                stone_reward,
                action_text="群内奇遇奖励灵石",
                enforce_currency_lock=False,
                allow_dead=False,
                apply_tribute=True,
            )
        profile.cultivation = cultivation
        profile.realm_layer = layer
        profile.updated_at = now

        instance.status = "claimed"
        instance.claimer_tg = tg
        instance.claimed_at = now
        instance.updated_at = now
        session.commit()
        session.refresh(instance)

    item_reward = None
    reward_item_kind = reward_payload.get("reward_item_kind")
    reward_item_ref_id = int(reward_payload.get("reward_item_ref_id") or 0)
    reward_item_quantity = int(reward_payload.get("reward_item_quantity") or 0)
    if reward_item_kind and reward_item_ref_id and reward_item_quantity > 0:
        item_reward = legacy_service.grant_item_to_user(tg, reward_item_kind, reward_item_ref_id, reward_item_quantity)

    legacy_service._apply_profile_growth_floor(tg)
    final_bundle = legacy_service.serialize_full_profile(tg)
    from bot.plugins.xiuxian_game.world_service import _bump_daily_counter
    _bump_daily_counter(tg, "encounter_daily_count")
    legacy_service.create_journal(
        tg,
        "encounter",
        "夺得奇遇",
        f"在群内抢到了【{template_payload.get('name') or instance.template_name}】，收获 {_encounter_reward_summary(reward_payload)}",
    )
    return {
        "instance": serialize_encounter_instance(get_encounter_instance(instance_id)),
        "template": template_payload,
        "reward": reward_payload,
        "item_reward": item_reward,
        "profile": final_bundle,
        "upgraded_layers": upgraded_layers,
        "remaining": remaining,
        "cultivation_gain_raw": raw_cultivation_gain,
        "cultivation_efficiency_percent": int(gain_meta.get("efficiency_percent") or 100),
    }


def expire_group_encounter(instance_id: int) -> dict[str, Any] | None:
    instance = get_encounter_instance(instance_id)
    if instance is None:
        return None
    if instance.status != "active":
        return instance
    expires_at = instance.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except ValueError:
                expires_at = None
        if expires_at is not None and expires_at > utcnow():
            return instance
    return patch_encounter_instance(instance_id, status="expired")


def render_group_encounter_success_text(result: dict[str, Any], winner_name: str) -> str:
    template = result.get("template") or {}
    reward = result.get("reward") or {}
    success_text = str(template.get("success_text") or "").strip()
    reward_summary = _encounter_reward_summary(reward)
    mapping = {
        "{user}": winner_name,
        "{encounter}": str(template.get("name") or "奇遇"),
        "{reward}": reward_summary,
        "{stone}": str(int(reward.get("stone_reward") or 0)),
        "{cultivation}": str(int(reward.get("cultivation_reward") or 0)),
    }
    for key, value in mapping.items():
        success_text = success_text.replace(key, value)
    if success_text:
        return "\n".join(
            [
                "🎉 **奇遇已被夺得**",
                _md_escape(success_text),
                f"🎁 收获：{_md_escape(reward_summary)}",
            ]
        )
    return (
        f"🎉 **奇遇已被夺得**\n"
        f"🏆 夺得者：{_md_escape(winner_name)}\n"
        f"📜 奇遇：**{_md_escape(template.get('name') or '一桩奇遇')}**\n"
        f"🎁 收获：{_md_escape(reward_summary)}"
    )
