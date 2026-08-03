from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

from bot import LOGGER, admin_p, group, owner_p, prefixes, user_p
from bot.func_helper.runtime import get_or_create_event_loop
from bot.plugins.sdk import build_plugin_url
from bot.scheduler.bot_commands import BotCommands
from bot.sql_helper.sql_douluo import (
    awaken_bloodline,
    awaken_wuhun,
    build_douluo_leaderboard,
    compute_duel_preview,
    get_bloodline_payload,
    get_craftsman_info,
    get_daily_action_usage,
    get_settings,
    get_wuhun_payload,
    hunt_soul_beast,
    list_player_inventory_grouped,
    prospect_materials,
    resolve_duel,
    serialize_profile,
    train_soul_power,
    upsert_profile_identity,
)

PLUGIN_VERSION = "0.2.0"

DOULUO_BOT_COMMANDS = [
    BotCommand("douluo", "打开斗罗大陆玩法入口 [私聊/群聊]"),
    BotCommand("dl_me", "展示魂师名帖 [群聊]"),
    BotCommand("dl_rank", "查看斗罗排行榜 [群聊]"),
    BotCommand("dl_bag", "查看储物魂导器背包 [群聊]"),
    BotCommand("dl_train", "群内魂力修炼 [群聊]"),
    BotCommand("dl_hunt", "群内猎杀魂兽获取魂环 [群聊]"),
    BotCommand("dl_wuhun", "觉醒/查看武魂 [群聊]"),
    BotCommand("dl_duel", "回复目标发起斗魂 [群聊]"),
    BotCommand("dl_bloodline", "觉醒/查看血脉 [群聊]"),
    BotCommand("dl_prospect", "群内勘探矿脉获取锻造材料 [群聊]"),
]

GROUP_ACTION_COMMANDS = {
    "dl_train": ("train_soul_power", "魂力修炼"),
    "dl_hunt": ("hunt_soul_beast", "猎杀魂兽"),
}

COMMAND_DISPATCH_CACHE: dict[tuple[int, int, str], float] = {}
PENDING_DUEL_INVITES: dict[str, dict[str, Any]] = {}
MESSAGE_AUTO_DELETE_TASKS: dict[tuple[int, int], asyncio.Task] = {}
PLAIN_PARSE_MODE = None
_BOT: Any = None

RING_COLOR_EMOJI = {
    "白": "⚪",
    "黄": "🟡",
    "紫": "🟣",
    "黑": "⚫",
    "红": "🔴",
    "蓝金": "💎",
}


def _ensure_douluo_bot_commands() -> None:
    for command_list in (user_p, admin_p, owner_p):
        existing = {item.command for item in command_list}
        for command in DOULUO_BOT_COMMANDS:
            if command.command not in existing:
                command_list.append(command)
                existing.add(command.command)


def _schedule_command_refresh(bot_instance) -> None:
    try:
        loop = get_or_create_event_loop()
        def _refresh_safe() -> None:
            # call_later 回调运行在事件循环线程；bot 若在 5s 内开始关停，
            # create_task 可能抛 RuntimeError，此处吞掉避免未捕获异常告警。
            try:
                loop.create_task(BotCommands.set_commands(client=bot_instance))
            except Exception as exc:
                LOGGER.debug(f"xiuxian command refresh skipped: {exc}")

        loop.call_later(5, _refresh_safe)
    except Exception as exc:
        LOGGER.debug(f"douluo command refresh skipped: {exc}")


def _register_command_dispatch(message, command_name: str, *, ttl_seconds: int = 30) -> bool:
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    message_id = getattr(message, "id", None)
    if chat_id is None or message_id is None:
        return True
    now = time.monotonic()
    expire_before = now - max(int(ttl_seconds), 1)
    stale_keys = [key for key, seen_at in COMMAND_DISPATCH_CACHE.items() if seen_at < expire_before]
    for key in stale_keys:
        COMMAND_DISPATCH_CACHE.pop(key, None)
    cache_key = (int(chat_id), int(message_id), str(command_name or "").strip().lower())
    if cache_key in COMMAND_DISPATCH_CACHE:
        return False
    COMMAND_DISPATCH_CACHE[cache_key] = now
    return True


def _configured_group_chat_ids() -> list[int]:
    if group is None:
        return []
    raw_groups = [group] if isinstance(group, (str, int)) else group
    chat_ids: list[int] = []
    seen: set[int] = set()
    for item in raw_groups or []:
        try:
            chat_id = int(item)
        except (TypeError, ValueError):
            continue
        if chat_id in seen:
            continue
        seen.add(chat_id)
        chat_ids.append(chat_id)
    return chat_ids


def _message_auto_delete_seconds() -> int:
    try:
        raw = get_settings().get("message_auto_delete_seconds", 180)
        return max(int(raw or 0), 0)
    except (TypeError, ValueError):
        return 180


async def _delete_message_after_delay(message, key: tuple[int, int], delay: int) -> None:
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        LOGGER.debug(f"douluo auto delete skipped chat={key[0]} message={key[1]}: {exc}")
    finally:
        task = MESSAGE_AUTO_DELETE_TASKS.get(key)
        if task is asyncio.current_task():
            MESSAGE_AUTO_DELETE_TASKS.pop(key, None)


def _apply_message_auto_delete(message, *, persistent: bool = False, seconds: int | None = None):
    if message is None:
        return None
    chat = getattr(message, "chat", None)
    message_id = getattr(message, "id", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None or message_id is None:
        return message
    key = (int(chat_id), int(message_id))
    existing = MESSAGE_AUTO_DELETE_TASKS.pop(key, None)
    if existing is not None:
        existing.cancel()
    delay = max(int(seconds if seconds is not None else _message_auto_delete_seconds()), 0)
    if persistent or delay <= 0:
        return message
    MESSAGE_AUTO_DELETE_TASKS[key] = asyncio.create_task(_delete_message_after_delay(message, key, delay))
    return message


async def _reply_text(message, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    kwargs.setdefault("parse_mode", PLAIN_PARSE_MODE)
    sent = await message.reply_text(text, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


async def _send_message(client, chat_id: int, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    kwargs.setdefault("parse_mode", PLAIN_PARSE_MODE)
    sent = await client.send_message(chat_id, text, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


async def _delete_user_command_message(message) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except Exception as exc:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        message_id = getattr(message, "id", None)
        LOGGER.debug(f"douluo command delete skipped chat={chat_id} message={message_id}: {exc}")


async def _push_broadcast_if_needed(client, chat_id: int, result: dict[str, Any]) -> None:
    """群播报:动作结果含 broadcast 事件时,向指定群发送 MarkdownV2 排版的播报卡片。

    优先使用事件携带的 md(排版文本)发送,失败时回退为纯文本 text。
    """
    event = (result or {}).get("broadcast") or {}
    text = str(event.get("text") or "").strip()
    if not text:
        return
    title = str(event.get("title") or "斗罗播报").strip()
    md_text = str(event.get("md") or "").strip()
    try:
        if md_text:
            await _send_message(client, int(chat_id), md_text, persistent=True, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await _send_message(client, int(chat_id), f"【{title}】\n{text}", persistent=True)
    except Exception:
        # MarkdownV2 失败(如特殊字符漏转义)时回退纯文本,保证播报不丢失。
        try:
            await _send_message(client, int(chat_id), f"【{title}】\n{text}", persistent=True)
        except Exception as exc:
            LOGGER.warning(f"douluo broadcast failed chat={chat_id}: {exc}")


async def _push_result_broadcast_to_groups(result: dict[str, Any]) -> None:
    """Web 端动作触发的群播报:发送到所有已配置群。"""
    if not (result or {}).get("broadcast") or _BOT is None:
        return
    for chat_id in _configured_group_chat_ids():
        await _push_broadcast_if_needed(_BOT, chat_id, result)


def _miniapp_keyboard() -> InlineKeyboardMarkup | None:
    url = build_plugin_url("/plugins/douluo/app")
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("打开斗罗 Mini App", url=url)]])


def _action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚔️ 魂力修炼", callback_data="douluo:train"),
                InlineKeyboardButton("🎯 猎杀魂兽", callback_data="douluo:hunt"),
            ],
            [
                InlineKeyboardButton("🧬 我的武魂", callback_data="douluo:wuhun"),
                InlineKeyboardButton("💍 魂环·魂骨", callback_data="douluo:rings"),
            ],
            [
                InlineKeyboardButton("🩸 血脉", callback_data="douluo:bloodline"),
                InlineKeyboardButton("🎒 背包", callback_data="douluo:bag"),
            ],
            [
                InlineKeyboardButton("🏆 排行榜", callback_data="douluo:rank"),
            ],
        ]
    )


def _command_name(message) -> str:
    command = getattr(message, "command", None) or []
    return str(command[0] if command else "").strip().lower()


def _display_user(message) -> tuple[int, str | None, str | None]:
    user = getattr(message, "from_user", None)
    if user is None:
        raise ValueError("无法识别你的 Telegram 身份")
    display_name = " ".join(
        part
        for part in [str(getattr(user, "first_name", "") or "").strip(), str(getattr(user, "last_name", "") or "").strip()]
        if part
    ).strip()
    username = str(getattr(user, "username", "") or "").strip().lstrip("@") or None
    return int(user.id), display_name or None, username


def _sync_actor_identity(message) -> int:
    tg, display_name, username = _display_user(message)
    upsert_profile_identity(tg, display_name=display_name, username=username)
    return tg


def _actor_name_label(message) -> str:
    """命令使用者的显示名（用于消息头部标注操作者账号）。"""
    tg, display_name, username = _display_user(message)
    return (display_name or username or f"玩家{tg}").strip()


def _sync_pyrogram_user_identity(user) -> int:
    if user is None:
        raise ValueError("无法识别 Telegram 用户")
    display_name = " ".join(
        part
        for part in [str(getattr(user, "first_name", "") or "").strip(), str(getattr(user, "last_name", "") or "").strip()]
        if part
    ).strip()
    username = str(getattr(user, "username", "") or "").strip().lstrip("@") or None
    tg = int(user.id)
    upsert_profile_identity(tg, display_name=display_name or None, username=username or None)
    return tg


def _parse_duel_args_from_message(message) -> tuple[int, int | None]:
    args = getattr(message, "command", None) or []
    stake = 0
    prepare_override = None
    for token in args[1:]:
        if token.isdigit():
            if prepare_override is None:
                stake = int(token)
            else:
                stake = int(token)
        elif token.startswith("@"):
            continue
        else:
            try:
                prepare_override = int(token)
            except (TypeError, ValueError):
                continue
    return stake, prepare_override


def _ring_line(ring: dict[str, Any]) -> str:
    emoji = RING_COLOR_EMOJI.get(str(ring.get("color") or ""), "⚪")
    years = int(ring.get("years") or 0)
    if years >= 10000:
        years_text = f"{years // 10000}万" if years % 10000 == 0 else f"{years / 10000:.1f}万"
    else:
        years_text = str(years)
    source = f"【{ring.get('source_name')}】" if ring.get("source_name") else ""
    return f"{emoji}{source}第{ring.get('slot')}魂环·{ring.get('tier')}({years_text}年) {ring.get('skill_name') or ''}".rstrip()


def _profile_bundle(tg: int) -> dict[str, Any]:
    payload = serialize_profile(tg, include_rings=True, include_equipment=True, include_actions=True)
    usage = get_daily_action_usage(tg)
    payload["action_points"] = usage.get("action_points", {})
    return payload


def _format_profile_text(bundle: dict[str, Any]) -> str:
    profile = bundle.get("profile", bundle)
    wuhun = profile.get("wuhun") or {}
    rings = bundle.get("rings") or []
    equipment = bundle.get("equipment") or {}
    action_points = bundle.get("action_points") or {}

    display = profile.get("display_name") or "魂师" + str(profile.get("tg") or "")
    lines = [
        "🪪【" + display + " · 魂师名帖】",
        f"🏔️ 境界：{profile.get('realm_stage')} {profile.get('realm_stars')}星",
        f"💪 魂力：{profile.get('soul_power')} ｜ 🪙 金魂币：{profile.get('coin')} ｜ 🧠 精神力：{profile.get('spirit_power')}",
        f"⚔️ 战力：{bundle.get('battle_power') or 0}",
    ]
    if wuhun.get("name"):
        lines.append(
            f"🧬 武魂：{wuhun.get('name')}({wuhun.get('system')}系·{wuhun.get('quality')}) 先天魂力{wuhun.get('innate_soul_power') or 0}"
        )
    if rings:
        lines.append("💍 魂环：" + "  ".join(_ring_line(ring) for ring in rings[:4]))
        if len(rings) > 4:
            lines.append("      " + "  ".join(_ring_line(ring) for ring in rings[4:]))
    else:
        lines.append("💍 魂环：无(使用 /dl_hunt 猎杀魂兽获取)")
    bone_count = sum(1 for item in equipment.values() if item.get("category") == "soulbone")
    ambush = next((item for item in equipment.values() if item.get("category") == "ambush"), None)
    lines.append(f"🦴 魂骨：{bone_count}/6 ｜ 🗡️ 暗器：{ambush.get('name') if ambush else '未装备'}")
    if profile.get("sect_key"):
        lines.append(f"🏛️ 宗门：{profile.get('sect_key')}({profile.get('sect_position') or '弟子'}) 贡献 {profile.get('sect_contribution') or 0}")
    lines.append(
        f"🏆 战绩：斗魂 {profile.get('arena_wins') or 0}胜/{profile.get('arena_losses') or 0}负 ｜ 👹 Boss分 {profile.get('boss_score') or 0}"
    )
    if action_points:
        lines.append(
            f"⚡ 行动力：{action_points.get('remaining') if action_points.get('limit') else '∞'}/{action_points.get('limit')}"
        )
    return "\n".join(lines)


def _format_wuhun_text(payload: dict[str, Any], display: str | None = None) -> str:
    if not payload:
        return "🧬 尚未觉醒武魂。\n\n使用 /dl_wuhun 觉醒武魂,或打开 Mini App 选择觉醒。"
    skills = payload.get("unlocked_skills") or []
    header = f"🧬【{display} · 武魂】{payload.get('name')}" if display else f"🧬 武魂:{payload.get('name')}"
    lines = [
        header,
        f"🌀 系别：{payload.get('system')}系 ｜ 💎 品质：{payload.get('quality')}",
        f"✨ 先天魂力：{payload.get('innate_soul_power')}",
    ]
    stats = payload.get("stats") or {}
    if stats:
        lines.append(
            f"📊 属性加成：攻+{stats.get('attack', 0)} 防+{stats.get('defense', 0)} 速+{stats.get('speed', 0)} 精神+{stats.get('spirit', 0)}"
        )
    desc = payload.get("description") or ""
    if desc:
        lines.append(f"📜 描述:{desc}")
    if skills:
        lines.append("🔓 已解锁魂技:")
        for index, skill in enumerate(skills, start=1):
            lines.append(f"  💠 第{index}魂环:{skill}")
    return "\n".join(lines)


def _format_inventory_text(inventory: dict[str, Any], display: str | None = None) -> str:
    categories = inventory.get("categories") or {}
    header = f"🎒【{display} · 储物魂导器】" if display else "🎒 储物魂导器"
    if not categories:
        return f"{header}空空如也。\n\n通过修炼、猎杀、讨伐与拍卖获取魂骨、暗器等物资。"
    category_emoji = {
        "soulbone": "🦴",
        "ambush": "🗡️",
        "pill": "💊",
        "material": "🧱",
        "contract": "📜",
        "ticket": "🎫",
    }
    category_label = {
        "soulbone": "魂骨",
        "ambush": "暗器",
        "pill": "丹药",
        "material": "材料",
        "contract": "契约",
        "ticket": "凭证",
    }
    lines = [header]
    for category, items in categories.items():
        label = category_label.get(category, category)
        icon = category_emoji.get(category, "📦")
        lines.append(f"▌{icon} {label}")
        for item in items:
            equipped = " ✅" if item.get("equipped_slot") else ""
            lines.append(f"  {item['name']} ×{item['quantity']}{equipped}")
    return "\n".join(lines)


def _format_bloodline_text(payload: dict[str, Any] | None, display: str | None = None, craftsman: dict[str, Any] | None = None) -> str:
    lines: list[str] = []
    header = f"🧬【{display} · 血脉与魂导】" if display else "🧬 血脉与魂导"
    if payload:
        lines.append(f"{header}\n血脉:{payload.get('name')}({payload.get('rarity')}) Lv.{payload.get('level')}")
        lines.append(f"🌀 体系:{payload.get('system')} ｜ 📜 特性:{payload.get('skill') or '无'}")
        lines.append(f"💪 血脉加成战力:{payload.get('power')}")
    else:
        lines.append(f"{header}\n血脉:未觉醒\n(需达到 魂尊 且已觉醒武魂,使用 /dl_bloodline 觉醒)")
    if craftsman:
        rank = int(craftsman.get("rank") or 1)
        exp = int(craftsman.get("exp") or 0)
        next_exp = craftsman.get("next_exp")
        progress = f"{exp}/{next_exp}" if next_exp else f"{exp}(已满级)"
        lines.append(f"🔧 魂导师等级:{rank} ｜ 熟练度:{progress}")
    return "\n".join(lines)


def _format_prospect_text(result: dict[str, Any], display: str | None = None) -> str:
    region = result.get("region") or {}
    materials = result.get("materials") or []
    lines = [
        f"⛏️ {display} 在【{region.get('name')}】勘探矿脉!" if display else f"⛏️ 在【{region.get('name')}】勘探矿脉!",
        "🏺 收获锻造材料:",
    ]
    for material in materials:
        lines.append(f"  · {material.get('name')}({material.get('rarity')})")
    lines.append(f"🏔️ 当前境界:{result['profile']['realm_stage']} {result['profile']['realm_stars']}星")
    return "\n".join(lines)


def _format_leaderboard_text(result: dict[str, Any]) -> str:
    lines = [f"🏆【斗罗排行榜 · {result.get('label')}】"]
    for index, item in enumerate(result.get("items") or [], start=1):
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"{index}."
        lines.append(f"{medal} {item['display_name']} —— {item['value']} ({item['sub']})")
    return "\n".join(lines)


def _format_train_text(result: dict[str, Any], display: str | None = None) -> str:
    header = f"⚔️ {display} 静室凝神,魂力流转!" if display else "⚔️ 静室凝神,魂力流转!"
    lines = [
        header,
        f"💪 魂力 +{result['soul_power_gained']} ｜ 🪙 金魂币 +{result['coin_gained']}",
        f"🏔️ 当前境界:{result['profile']['realm_stage']} {result['profile']['realm_stars']}星 ｜ 💪 魂力 {result['profile']['soul_power']}",
    ]
    event = result.get("event")
    if event:
        lines.append(f"✨ 奇遇:{event.get('title')}:{event.get('text', '')}")
    return "\n".join(lines)


def _format_hunt_text(result: dict[str, Any], display: str | None = None) -> str:
    emoji = RING_COLOR_EMOJI.get(result.get("color") or "", "⚪")
    header = f"🎯 {display} 在【{result['region']['name']}】遭遇 {result['beast']['name']}!" if display else f"🎯 在【{result['region']['name']}】遭遇 {result['beast']['name']}!"
    lines = [
        header,
        f"💪 击杀成功,获得魂力 +{result['soul_power_gained']}、🪙 金魂币 +{result['coin_gained']}",
    ]
    ring = result.get("ring") or {}
    action = ring.get("action")
    if action == "absorb":
        lines.append(f"{emoji} 吸收【{ring.get('source_name')}】的 {ring.get('tier')}魂环({ring.get('years')}年),解锁第{ring.get('slot')}魂技·{ring.get('skill_name')}")
    elif action == "replace":
        lines.append(f"{emoji} 以【{ring.get('source_name')}】的 {ring.get('tier')}魂环({ring.get('years')}年)替换第{ring.get('slot')}魂环")
    elif action == "give_up":
        lines.append(f"{emoji} 斩获【{ring.get('source_name')}】的 {ring.get('tier')}魂环({ring.get('years')}年),但{ring.get('reason')}")
    event = result.get("event")
    if event:
        lines.append(f"✨ 奇遇:{event.get('title')}:{event.get('text', '')}")
    return "\n".join(lines)


def _format_duel_preview_text(preview: dict[str, Any], prepare_seconds: int) -> str:
    return (
        f"⚔️ 斗魂邀约\n"
        f"🏆 {preview['challenger_name']}(战力 {preview['challenger_power']}) 挑战 "
        f"{preview['defender_name']}(战力 {preview['defender_power']})\n"
        f"🪙 押注:{preview['stake']} 金魂币 ｜ 📊 预估胜率 {preview['challenger_win_chance'] * 100:.0f}%\n"
        f"⏱️ {prepare_seconds} 秒后自动开始,或点下方按钮确认。"
    )


def _format_duel_result_text(result: dict[str, Any]) -> str:
    challenger_win = bool(result["challenger_win"])
    winner_text = "挑战方" if challenger_win else "被挑战方"
    return (
        f"⚔️ 斗魂结算\n"
        f"🎉 {winner_text}获胜!\n"
        f"⚔️ 挑战方战力 {result['challenger_power']} vs 🛡️ 被挑战方战力 {result['defender_power']}\n"
        f"🪙 押注 {result['stake']} 金魂币已结算。"
    )


async def _execute_action_and_reply(message, action_func, *, format_func=None, success_prefix=None, error_prefix="❌ 操作失败"):
    try:
        result = await run_in_threadpool(action_func)
        if format_func:
            text = format_func(result)
        else:
            text = str(result)
        await _reply_text(message, text, quote=True)
    except ValueError as exc:
        await _reply_text(message, f"{error_prefix}:{exc}", quote=True)
    except Exception as exc:
        LOGGER.exception(f"douluo action failed: {exc}")
        await _reply_text(message, f"{error_prefix}:{exc}", quote=True)


def register_bot(bot_instance) -> None:
    global _BOT
    _BOT = bot_instance
    _ensure_douluo_bot_commands()
    _schedule_command_refresh(bot_instance)

    @bot_instance.on_message(filters.command(["douluo", "dl"], prefixes) & filters.private)
    async def douluo_private_command(_, message):
        try:
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            bundle = await run_in_threadpool(_profile_bundle, actor_tg)
            await _reply_text(
                message,
                _format_profile_text(bundle) + "\n\n群内可用:/dl_me /dl_bag /dl_rank /dl_train /dl_hunt /dl_wuhun /dl_bloodline /dl_prospect /dl_duel",
                reply_markup=_action_keyboard(),
                persistent=True,
            )
        except Exception as exc:
            LOGGER.exception(f"douluo private command failed: {exc}")
            await _reply_text(message, f"❌ 斗罗入口加载失败:{exc}", quote=True)

    @bot_instance.on_message(filters.command(["douluo", "dl"], prefixes) & filters.chat(group))
    async def douluo_group_command(_, message):
        try:
            if not _register_command_dispatch(message, _command_name(message) or "douluo"):
                return
            lines = [
                "🎮【斗罗大陆玩法】",
                "💬 私聊机器人发送 /douluo 可打开斗罗总览与行动面板。",
                "📋 群内命令:/dl_me 名帖,/dl_bag 背包,/dl_rank 排行。",
                "🧬 互动命令:/dl_wuhun 觉醒武魂,/dl_bloodline 觉醒血脉,回复玩家 /dl_duel [金魂币] 发起斗魂。",
                "⚔️ 群内行动:/dl_train 修炼,/dl_hunt 猎杀魂兽,/dl_prospect 勘探矿脉获取锻造材料。",
                "🏛️ 宗门、拍卖、每日任务、魂兽讨伐、魂导锻造、斗铠与魂核请在 Mini App 中展开。",
                "📢 关键突破、高阶魂环、稀有魂骨和讨伐会自动播报。",
            ]
            await _reply_text(message, "\n".join(lines), quote=True, reply_markup=_miniapp_keyboard())
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_me", "douluo_me"], prefixes) & filters.chat(group))
    async def douluo_me_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_me"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            bundle = await run_in_threadpool(_profile_bundle, actor_tg)
            await _reply_text(message, _format_profile_text(bundle), quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo me command failed: {exc}")
            await _reply_text(message, f"❌ 魂师名帖加载失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_bag", "douluo_bag"], prefixes) & filters.chat(group))
    async def douluo_bag_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_bag"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            inventory = await run_in_threadpool(list_player_inventory_grouped, actor_tg)
            await _reply_text(message, _format_inventory_text(inventory, display=_actor_name_label(message)), quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo bag command failed: {exc}")
            await _reply_text(message, f"❌ 背包读取失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_rank", "douluo_rank"], prefixes) & filters.chat(group))
    async def douluo_rank_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_rank"):
                return
            args = getattr(message, "command", None) or []
            kind = str(args[1] if len(args) > 1 else "power")
            result = await run_in_threadpool(build_douluo_leaderboard, kind, 10)
            await _reply_text(message, _format_leaderboard_text(result), quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo rank command failed: {exc}")
            await _reply_text(message, f"❌ 排行榜读取失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_wuhun", "douluo_wuhun"], prefixes) & filters.chat(group))
    async def douluo_wuhun_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_wuhun"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            display = _actor_name_label(message)
            payload = await run_in_threadpool(get_wuhun_payload, actor_tg)
            if not payload:
                result = await run_in_threadpool(awaken_wuhun, actor_tg)
                wuhun = result.get("wuhun", {})
                await _reply_text(
                    message,
                    f"🧬 {display} 武魂觉醒!\n"
                    f"武魂:{wuhun.get('name')} ｜ {wuhun.get('system')}系 · {wuhun.get('quality')}\n"
                    f"先天魂力:{result.get('innate_soul_power')}\n"
                    f"第1魂技:{wuhun.get('skills', [''])[0]}\n\n使用 /dl_hunt 获取第1魂环解锁魂技。",
                    quote=True,
                )
                return
            await _reply_text(message, _format_wuhun_text(payload, display=display), quote=True)
        except ValueError as exc:
            await _reply_text(message, f"❌ 武魂操作失败:{exc}", quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo wuhun command failed: {exc}")
            await _reply_text(message, f"❌ 武魂操作失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_bloodline", "douluo_bloodline"], prefixes) & filters.chat(group))
    async def douluo_bloodline_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_bloodline"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            display = _actor_name_label(message)
            payload = await run_in_threadpool(get_bloodline_payload, actor_tg)
            craftsman = await run_in_threadpool(get_craftsman_info, actor_tg)
            if not payload:
                result = await run_in_threadpool(awaken_bloodline, actor_tg)
                await _reply_text(
                    message,
                    f"🧬 {display} 血脉觉醒!\n"
                    f"血脉:{result['bloodline']['name']}({result['bloodline']['rarity']}) Lv.{result['bloodline']['level']}\n"
                    f"🌀 体系:{result['bloodline'].get('system')} ｜ 📜 特性:{result['bloodline'].get('skill')}\n"
                    f"💪 血脉加成战力:{result['bloodline'].get('power')}\n\n"
                    f"使用 /dl_bloodline 查看详情,或打开 Mini App 淬炼血脉。",
                    quote=True,
                )
                chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
                if chat_id:
                    await _push_broadcast_if_needed(bot_instance, chat_id, result)
                return
            await _reply_text(
                message, _format_bloodline_text(payload, display=display, craftsman=craftsman), quote=True
            )
        except ValueError as exc:
            await _reply_text(message, f"❌ 血脉操作失败:{exc}", quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo bloodline command failed: {exc}")
            await _reply_text(message, f"❌ 血脉操作失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_prospect", "douluo_prospect"], prefixes) & filters.chat(group))
    async def douluo_prospect_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_prospect"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            args = getattr(message, "command", None) or []
            region_key = str(args[1]) if len(args) > 1 else None
            result = await run_in_threadpool(prospect_materials, actor_tg, region_key)
            await _reply_text(message, _format_prospect_text(result, display=_actor_name_label(message)), quote=True)
            chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
            if chat_id:
                await _push_broadcast_if_needed(bot_instance, chat_id, result)
        except ValueError as exc:
            await _reply_text(message, f"❌ 勘探失败:{exc}", quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo prospect command failed: {exc}")
            await _reply_text(message, f"❌ 勘探失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_train", "douluo_train"], prefixes) & filters.chat(group))
    async def douluo_train_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_train"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            result = await run_in_threadpool(train_soul_power, actor_tg)
            await _reply_text(message, _format_train_text(result, display=_actor_name_label(message)), quote=True)
        except ValueError as exc:
            await _reply_text(message, f"❌ 修炼失败:{exc}", quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo train command failed: {exc}")
            await _reply_text(message, f"❌ 修炼失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_hunt", "douluo_hunt"], prefixes) & filters.chat(group))
    async def douluo_hunt_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_hunt"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            args = getattr(message, "command", None) or []
            region_key = str(args[1]) if len(args) > 1 else None
            result = await run_in_threadpool(hunt_soul_beast, actor_tg, region_key)
            await _reply_text(message, _format_hunt_text(result, display=_actor_name_label(message)), quote=True)
            chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
            if chat_id:
                await _push_broadcast_if_needed(bot_instance, chat_id, result)
        except ValueError as exc:
            await _reply_text(message, f"❌ 猎杀失败:{exc}", quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo hunt command failed: {exc}")
            await _reply_text(message, f"❌ 猎杀失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dl_duel", "douluo_duel"], prefixes) & filters.chat(group))
    async def douluo_duel_command(_, message):
        try:
            if not _register_command_dispatch(message, "dl_duel"):
                return
            reply = getattr(message, "reply_to_message", None)
            target_user = getattr(reply, "from_user", None)
            if target_user is None:
                await _reply_text(message, "⚠️ 请回复一位玩家后使用 /dl_duel [金魂币] 发起斗魂。", quote=True)
                return
            if bool(getattr(target_user, "is_bot", False)):
                await _reply_text(message, "🚫 不能向机器人发起斗魂。", quote=True)
                return
            challenger_tg = await run_in_threadpool(_sync_actor_identity, message)
            defender_tg = await run_in_threadpool(_sync_pyrogram_user_identity, target_user)
            if challenger_tg == defender_tg:
                await _reply_text(message, "🚫 不能向自己发起斗魂。", quote=True)
                return
            stake, prepare_override = _parse_duel_args_from_message(message)
            preview = await run_in_threadpool(compute_duel_preview, challenger_tg, defender_tg, stake)
            prepare_seconds = prepare_override if prepare_override is not None else 8
            nonce = uuid4().hex[:12]
            PENDING_DUEL_INVITES[nonce] = {
                "challenger_tg": challenger_tg,
                "defender_tg": defender_tg,
                "stake": stake,
                "prepare_seconds": prepare_seconds,
                "created_at": time.monotonic(),
            }
            await _reply_text(
                message,
                _format_duel_preview_text(preview, prepare_seconds),
                quote=True,
                persistent=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(f"确认应战(押注 {stake} 魂币)", callback_data=f"douluo:duel_accept:{nonce}")]]
                ),
            )
        except ValueError as exc:
            await _reply_text(message, f"❌ 斗魂失败:{exc}", quote=True)
        except Exception as exc:
            LOGGER.exception(f"douluo duel command failed: {exc}")
            await _reply_text(message, f"❌ 斗魂失败:{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_callback_query()
    async def douluo_callback(bot_callback_query, callback_query):
        from pyrogram.enums import ParseMode

        data = str(getattr(callback_query, "data", "") or "")
        if not data.startswith("douluo:"):
            return
        try:
            from_user = getattr(callback_query, "from_user", None)
            if from_user is None:
                raise ValueError("无法识别身份")
            tg = int(from_user.id)
            parts = data.split(":")
            action = parts[1] if len(parts) > 1 else ""

            if action == "duel_accept" and len(parts) >= 3:
                nonce = parts[2]
                invite = PENDING_DUEL_INVITES.get(nonce)
                if invite is None:
                    await callback_query.answer("邀约已失效", show_alert=True)
                    return
                if time.monotonic() - float(invite.get("created_at") or 0) > 300:
                    PENDING_DUEL_INVITES.pop(nonce, None)
                    await callback_query.answer("邀约已过期", show_alert=True)
                    return
                if int(invite["defender_tg"]) != tg:
                    await callback_query.answer("你不是被挑战者", show_alert=True)
                    return
                # 在第一次 await 前消费邀请，防止连续点击并发触发两次结算。
                invite = PENDING_DUEL_INVITES.pop(nonce, None)
                if invite is None:
                    await callback_query.answer("邀约已失效", show_alert=True)
                    return
                result = await run_in_threadpool(
                    resolve_duel, invite["challenger_tg"], invite["defender_tg"], invite["stake"]
                )
                await callback_query.message.reply_text(_format_duel_result_text(result), parse_mode=ParseMode.HTML)
                await callback_query.answer("斗魂开始!", show_alert=False)
                return

            payload_map = {
                "train": (train_soul_power, _format_train_text, "修炼失败"),
                "hunt": (lambda: hunt_soul_beast(tg), _format_hunt_text, "猎杀失败"),
                "wuhun": (lambda: get_wuhun_payload(tg), _format_wuhun_text, "武魂读取失败"),
                "bloodline": (
                    lambda: (get_bloodline_payload(tg), get_craftsman_info(tg)),
                    lambda data: _format_bloodline_text(data[0], craftsman=data[1]),
                    "血脉读取失败",
                ),
                "bag": (lambda: list_player_inventory_grouped(tg), _format_inventory_text, "背包读取失败"),
                "rank": (lambda: build_douluo_leaderboard("power", 10), _format_leaderboard_text, "排行榜读取失败"),
            }
            handler = payload_map.get(action)
            if handler is None:
                await callback_query.answer("未知操作", show_alert=True)
                return
            func, formatter, error_prefix = handler
            result = await run_in_threadpool(func)
            text = formatter(result)
            await callback_query.message.reply_text(text, parse_mode=ParseMode.HTML)
            await callback_query.answer("完成", show_alert=False)
        except ValueError as exc:
            await callback_query.answer(str(exc), show_alert=True)
        except Exception as exc:
            LOGGER.exception(f"douluo callback failed: {exc}")
            await callback_query.answer("操作失败,请稍后再试", show_alert=True)
