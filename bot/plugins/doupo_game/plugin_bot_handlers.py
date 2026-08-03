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
from bot.sql_helper.sql_doupo import (
    build_doupo_leaderboard,
    build_feature_overview,
    build_growth_snapshot,
    claim_sect_quest,
    compute_doupo_duel_preview,
    get_daily_action_usage,
    get_economy_snapshot,
    get_or_create_profile,
    get_sect_panel,
    get_settings,
    join_sect,
    leave_sect,
    list_sect_options,
    list_player_inventory_grouped,
    resolve_doupo_duel,
    run_action,
    transfer_sect,
    upsert_profile_identity,
)


DOUPO_BOT_COMMANDS = [
    BotCommand("doupo", "打开斗破玩法入口 [私聊/群聊]"),
    BotCommand("dp_me", "展示斗破名帖 [群聊]"),
    BotCommand("dp_rank", "查看斗破排行榜 [群聊]"),
    BotCommand("dp_bag", "查看纳戒背包 [群聊]"),
    BotCommand("dp_train", "群内静室凝气 [群聊]"),
    BotCommand("dp_hunt", "群内魔兽山脉历练 [群聊]"),
    BotCommand("dp_sect", "选择斗破宗门 [群聊]"),
    BotCommand("dp_duel", "回复目标发起斗战 [群聊]"),
    BotCommand("dp_alchemy", "群内开炉炼药 [群聊]"),
    BotCommand("dp_fire", "群内追踪异火 [群聊]"),
    BotCommand("dp_boss", "群内魔兽Boss讨伐 [群聊]"),
]

GROUP_ACTION_COMMANDS = {
    "dp_train": ("train_breath", "静室凝气"),
    "dp_hunt": ("mountain_hunt", "魔兽山脉历练"),
    "dp_alchemy": ("alchemy_refine", "一品炼药"),
    "dp_fire": ("fire_capture", "异火线索"),
    "dp_boss": ("boss_challenge", "魔兽Boss讨伐"),
}

COMMAND_DISPATCH_CACHE: dict[tuple[int, int, str], float] = {}
PENDING_DUEL_INVITES: dict[str, dict[str, Any]] = {}
MESSAGE_AUTO_DELETE_TASKS: dict[tuple[int, int], asyncio.Task] = {}
PLAIN_PARSE_MODE = None

# Telegram MarkdownV2 特殊字符(作字面量时必须反斜杠转义)
_MD_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"
# 播报卡片分隔线
_MD_BROADCAST_DIVIDER = "━" * 18


def _md_escape(value: Any) -> str:
    """转义 Telegram MarkdownV2 特殊字符,防止动态内容破坏排版。"""
    text = str(value or "")
    return "".join(f"\\{ch}" if ch in _MD_V2_SPECIAL_CHARS else ch for ch in text)


def _md_broadcast_card(title: str, icon: str, lines: list[str]) -> str:
    """将标题与内容行拼装为带分隔线的 MarkdownV2 播报卡片。"""
    return "\n".join([f"{icon} **{title}** {icon}", _MD_BROADCAST_DIVIDER, *lines, _MD_BROADCAST_DIVIDER])


def _ensure_doupo_bot_commands() -> None:
    for command_list in (user_p, admin_p, owner_p):
        existing = {item.command for item in command_list}
        for command in DOUPO_BOT_COMMANDS:
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
        LOGGER.debug(f"doupo command refresh skipped: {exc}")


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
            chat_id = int(str(item or "").strip() or "0")
        except (TypeError, ValueError):
            continue
        if chat_id and chat_id not in seen:
            seen.add(chat_id)
            chat_ids.append(chat_id)
    return chat_ids


def _main_group_chat_id() -> int | None:
    chat_ids = _configured_group_chat_ids()
    return chat_ids[0] if chat_ids else None


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
        LOGGER.debug(f"doupo auto delete skipped chat={key[0]} message={key[1]}: {exc}")
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


async def _delete_user_command_message(message) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except Exception as exc:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        message_id = getattr(message, "id", None)
        LOGGER.debug(f"doupo command delete skipped chat={chat_id} message={message_id}: {exc}")


async def _reply_text(message, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    kwargs.setdefault("parse_mode", PLAIN_PARSE_MODE)
    sent = await message.reply_text(text, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


async def _send_message(client, chat_id: int, text: str, *, persistent: bool = False, auto_delete_seconds: int | None = None, **kwargs):
    kwargs.setdefault("parse_mode", PLAIN_PARSE_MODE)
    sent = await client.send_message(chat_id, text, **kwargs)
    return _apply_message_auto_delete(sent, persistent=persistent, seconds=auto_delete_seconds)


def _miniapp_keyboard() -> InlineKeyboardMarkup | None:
    url = build_plugin_url("/plugins/doupo/app")
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 打开斗破 Mini App", url=url)]])


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


def _sync_pyrogram_user_identity(user) -> int:
    if user is None:
        raise ValueError("无法识别 Telegram 用户")
    display_name = " ".join(
        part
        for part in [str(getattr(user, "first_name", "") or "").strip(), str(getattr(user, "last_name", "") or "").strip()]
        if part
    ).strip()
    username = str(getattr(user, "username", "") or "").strip().lstrip("@") or None
    upsert_profile_identity(int(user.id), display_name=display_name or None, username=username)
    return int(user.id)


def _actor_name_label(message) -> str:
    """命令使用者的显示名（用于消息头部标注操作者账号）。"""
    tg, display_name, username = _display_user(message)
    return (display_name or username or f"玩家{tg}").strip()


def _format_economy_line(economy: dict[str, Any]) -> str:
    cap = economy.get("daily_gold_action_cap")
    income = int(economy.get("gold_income") or 0)
    sink = int(economy.get("gold_sink") or 0)
    if cap is None or int(cap or 0) <= 0:
        return f"🪙 今日行动金币：{income}，今日回收：{sink}"
    return f"🪙 今日行动金币：{income}/{int(cap)}，今日回收：{sink}"


def _profile_bundle(tg: int) -> dict[str, Any]:
    profile = get_or_create_profile(tg)
    settings = get_settings()
    return {
        "profile": profile,
        "growth": build_growth_snapshot(profile, settings),
        "features": build_feature_overview(profile),
        "economy": get_economy_snapshot(tg, settings),
        "inventory": list_player_inventory_grouped(tg),
        "daily_usage": get_daily_action_usage(tg, settings),
    }


def _format_profile_text(bundle: dict[str, Any]) -> str:
    profile = bundle["profile"]
    growth = bundle["growth"]
    features = bundle["features"]
    economy = bundle["economy"]
    daily_usage = bundle.get("daily_usage") or {}
    action_points = daily_usage.get("action_points") or {}
    douqi_income = daily_usage.get("douqi_income") or {}
    fire = features.get("heavenly_fire") or {}
    technique = features.get("technique") or {}
    display_name = profile.get("display_name") or f"TG {profile.get('tg')}"
    return "\n".join(
        [
            "🔥 斗破名帖",
            f"👤 玩家：{display_name}",
            f"🌟 境界：{profile.get('realm_stage')} {int(profile.get('realm_stars') or 1)}星",
            f"⚔️ 战力：{int(profile.get('battle_power') or 0)}",
            f"🌀 斗气：{int(growth.get('douqi_current') or 0)}/{int(growth.get('douqi_per_star') or 1)}",
            f"⚡ 今日行动力：{int(action_points.get('used') or 0)}/{int(action_points.get('limit') or 0) or '不限'}，🌀 成长斗气 {int(douqi_income.get('earned') or 0)}/{int(douqi_income.get('hard_cap') or 0) or '不限'}",
            f"🪙 金币：{int(profile.get('gold') or 0)}",
            _format_economy_line(economy),
            f"⚗️ 炼药：{features.get('alchemy', {}).get('rank') or '未入品'}，丹药 {int(profile.get('pill_stock') or 0)}",
            f"🔥 异火：{fire.get('name') or '未收服'}，线索 {int(profile.get('fire_progress') or 0)}",
            f"📜 斗技：{technique.get('name') or '未习得'} {int(technique.get('level') or 0)}级",
            f"⛩️ 宗门：{profile.get('sect_name') or '未入宗门'}，贡献 {int(profile.get('sect_contribution') or 0)}",
        ]
    )


def _format_inventory_text(inventory: dict[str, Any], display: str | None = None) -> str:
    header = f"💍 {display} · 纳戒背包" if display else "💍 纳戒背包"
    lines = [header]
    nonempty = [category for category in inventory.get("categories") or [] if int(category.get("total_quantity") or 0) > 0]
    if not nonempty:
        lines.append("当前纳戒暂无物品。先试试 /dp_hunt 或 /dp_train。")
        return "\n".join(lines)
    for category in nonempty:
        items = category.get("items") or []
        item_text = "、".join(f"{item.get('name')} x{int(item.get('quantity') or 0)}" for item in items[:4])
        if len(items) > 4:
            item_text += f" 等 {len(items)} 种"
        lines.append(f"📦 {category.get('name')}：{item_text}")
    return "\n".join(lines)


def _sect_keyboard(actor_tg: int) -> InlineKeyboardMarkup:
    rows = []
    for sect in list_sect_options():
        rows.append([InlineKeyboardButton(f"加入 {sect['name']}", callback_data=f"doupo:sect:join:{sect['key']}:{int(actor_tg)}")])
    return InlineKeyboardMarkup(rows)


def _format_sect_options_text() -> str:
    lines = ["⛩️ 斗破宗门", "选择宗门后才可执行宗门委托与斗技阁相关行动。"]
    for sect in list_sect_options():
        lines.append(f"⛩️ {sect['name']}｜门槛 {sect.get('realm_stage_min') or '斗之气'}｜{sect.get('bonus') or ''}")
    return "\n".join(lines)


def _format_sect_panel_text(panel: dict[str, Any], profile: dict[str, Any]) -> str:
    quest = panel.get("quest") or {}
    members = panel.get("members") or []
    transfer = panel.get("transfer") or {}
    lines = [
        "⛩️ 宗门面板",
        f"⛩️ 宗门：{profile.get('sect_name')}",
        f"🎖️ 位阶：{quest.get('rank') or profile.get('sect_rank') or '外门弟子'}（委托倍率 x{quest.get('multiplier') or 1}）",
        f"🏅 贡献：{int(profile.get('sect_contribution') or 0)}",
        f"📋 每日委托：{'今日已领取，明日再来' if quest.get('claimed') else '可领取'}",
        f"👥 成员（{len(members)}）：",
    ]
    for member in members[:6]:
        lines.append(
            f"  {member.get('display_name')}｜{member.get('realm_stage')} {int(member.get('realm_stars') or 1)}星｜{member.get('sect_rank')}｜贡献 {int(member.get('sect_contribution') or 0)}"
        )
    if len(members) > 6:
        lines.append(f"  ... 等共 {len(members)} 人")
    remaining = int(transfer.get("remaining_days") or 0)
    cooldown_hint = f"，转宗冷却 {remaining} 天" if remaining > 0 else ""
    lines.append(f"🌀 转宗费用 {int(transfer.get('cost') or 0)} 金币{cooldown_hint}｜🚪 离开费用 {int(panel.get('leave_cost') or 0)} 金币")
    return "\n".join(lines)


def _sect_panel_keyboard(actor_tg: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("每日委托", callback_data=f"doupo:sect:quest:{int(actor_tg)}")],
            [
                InlineKeyboardButton("转宗", callback_data=f"doupo:sect:transfer:{int(actor_tg)}"),
                InlineKeyboardButton("离开宗门", callback_data=f"doupo:sect:leave:{int(actor_tg)}"),
            ],
            [InlineKeyboardButton("刷新面板", callback_data=f"doupo:sect:panel:{int(actor_tg)}")],
        ]
    )


def _sect_transfer_keyboard(actor_tg: int) -> InlineKeyboardMarkup:
    rows = []
    for sect in list_sect_options():
        rows.append([InlineKeyboardButton(sect["name"], callback_data=f"doupo:sect:transfer:{sect['key']}:{int(actor_tg)}")])
    rows.append([InlineKeyboardButton("返回面板", callback_data=f"doupo:sect:panel:{int(actor_tg)}")])
    return InlineKeyboardMarkup(rows)


def _format_leaderboard_text(result: dict[str, Any]) -> str:
    lines = [f"🏆 斗破{result.get('label') or '排行榜'}"]
    items = result.get("items") or []
    if not items:
        lines.append("暂无玩家数据。")
        return "\n".join(lines)
    for index, profile in enumerate(items, 1):
        lines.append(
            f"{index}. {profile.get('display_name')}｜{profile.get('realm_stage')} {int(profile.get('realm_stars') or 1)}星｜战力 {int(profile.get('battle_power') or 0)}"
        )
    return "\n".join(lines)


def _format_items_delta(items: list[dict[str, Any]]) -> str:
    visible = [item for item in items if int(item.get("quantity") or 0) != 0]
    if not visible:
        return ""
    return "💍 纳戒：" + "、".join(
        f"{item.get('name') or item.get('item_key')} {int(item.get('quantity') or 0):+d}" for item in visible[:5]
    )


def _format_action_result(result: dict[str, Any]) -> str:
    profile = result.get("profile") or {}
    display_name = profile.get("display_name") or f"TG {profile.get('tg') or ''}"
    lines = [
        f"✨ {result.get('action_name') or '行动'}完成",
        f"👤 玩家：{display_name}",
        f"🌟 境界：{profile.get('realm_stage') or '-'} {int(profile.get('realm_stars') or 1)}星，⚔️ 战力 {int(profile.get('battle_power') or 0)}",
        str(result.get("detail") or ""),
    ]
    item_line = _format_items_delta(result.get("items_delta") or [])
    if item_line:
        lines.append(item_line)
    economy = result.get("economy") or {}
    if economy:
        lines.append(_format_economy_line(economy))
    if result.get("economy_capped"):
        lines.append("🪙 今日行动金币已到上限，后续正向金币会被截断，但材料和修为仍可获得。")
    return "\n".join(line for line in lines if str(line or "").strip())


def _duel_prepare_seconds(settings: dict[str, Any], override: int | None = None) -> int:
    if override is not None:
        return min(max(int(override or 0), 0), 600)
    return min(max(int(settings.get("duel_prepare_seconds") or 0), 0), 600)


def _parse_duel_args_from_message(message) -> tuple[int, int | None]:
    args = getattr(message, "command", None) or []
    if len(args) <= 1:
        return 0, None
    try:
        stake = max(int(str(args[1]).strip()), 0)
    except (TypeError, ValueError):
        raise ValueError("赌注需要填写整数金币")
    if len(args) <= 2:
        return stake, None
    try:
        prepare_seconds = min(max(int(str(args[2]).strip()), 0), 600)
    except (TypeError, ValueError):
        raise ValueError("备战秒数需要填写整数，范围 0-600")
    return stake, prepare_seconds


def _duel_invite_keyboard(nonce: str, challenger_tg: int, defender_tg: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("接受并开战", callback_data=f"doupo:duel:accept:{nonce}")],
            [
                InlineKeyboardButton("拒绝", callback_data=f"doupo:duel:reject:{nonce}"),
                InlineKeyboardButton("撤销", callback_data=f"doupo:duel:cancel:{nonce}"),
            ],
        ]
    )


def _format_duel_preview_text(preview: dict[str, Any], prepare_seconds: int) -> str:
    challenger = preview["challenger"]
    defender = preview["defender"]
    stake = int(preview.get("stake_gold") or 0)
    lines = [
        "⚔️ 斗破斗战邀请",
        f"⚔️ 挑战者：{challenger['display_name']}｜{challenger['realm']}｜战力 {challenger['battle_power']}",
        f"🛡️ 应战者：{defender['display_name']}｜{defender['realm']}｜战力 {defender['battle_power']}",
        f"📊 胜率预估：挑战者 {int(preview.get('challenger_win_rate') or 0)}% / 应战者 {int(preview.get('defender_win_rate') or 0)}%",
        f"🪙 赌注：{stake} 金币（双方各需持有，结算只在双方之间转移）",
        f"⏱️ 备战：接受后 {int(prepare_seconds)} 秒开始推演战况。",
        "应战者点击接受后进入斗战流程。",
    ]
    return "\n".join(lines)


def _format_duel_result_text(result: dict[str, Any]) -> str:
    challenger = result["challenger"]
    defender = result["defender"]
    winner = result["winner"]
    lines = [
        "🏆 斗破斗战结算",
        f"{challenger['display_name']} vs {defender['display_name']}",
        f"📊 胜率：挑战者 {int(result.get('challenger_win_rate') or 0)}% / 应战者 {int(result.get('defender_win_rate') or 0)}%",
        f"🎲 判定：{int(result.get('roll') or 0)}",
        f"🏆 胜者：{winner['display_name']}",
    ]
    stake = int(result.get("stake_gold") or 0)
    if stake:
        lines.append(f"🪙 金币转移：{stake}")
    battle_log = list(result.get("battle_log") or [])
    if battle_log:
        lines.append("⚔️ 战况：")
        lines.extend(f"- {line}" for line in battle_log[:4])
    return "\n".join(lines)


async def _edit_message_text(message, text: str, **kwargs):
    kwargs.setdefault("parse_mode", PLAIN_PARSE_MODE)
    try:
        return await message.edit_text(text, **kwargs)
    except Exception as exc:
        LOGGER.warning(f"doupo message edit failed: {exc}")
        return message


def _format_duel_stream_text(result: dict[str, Any], shown: int) -> str:
    challenger = result["challenger"]
    defender = result["defender"]
    battle_log = list(result.get("battle_log") or [])
    shown = max(min(int(shown or 0), len(battle_log)), 0)
    lines = [
        "⚔️ 斗破斗战推演",
        f"{challenger['display_name']} vs {defender['display_name']}",
        f"🪙 赌注：{int(result.get('stake_gold') or 0)} 金币",
        "",
        "⚔️ 战况：",
    ]
    if shown <= 0:
        lines.append("🌀 双方斗气正在交锋。")
    else:
        lines.extend(f"{index}. {line}" for index, line in enumerate(battle_log[:shown], 1))
    if shown < len(battle_log):
        lines.append("")
        lines.append("⏳ 胜负未分，战况继续推演。")
    return "\n".join(lines)


async def _stream_doupo_duel_battle(message, result: dict[str, Any]):
    battle_log = list(result.get("battle_log") or [])
    if not battle_log:
        return message
    current_message = await _edit_message_text(message, _format_duel_stream_text(result, 0))
    await asyncio.sleep(1.2)
    for shown in range(1, len(battle_log) + 1):
        current_message = await _edit_message_text(current_message, _format_duel_stream_text(result, shown))
        await asyncio.sleep(1.1)
    return current_message


async def _push_duel_broadcast_if_needed(client, chat_id: int, result: dict[str, Any]) -> None:
    if not chat_id:
        return
    try:
        settings = await run_in_threadpool(get_settings)
    except Exception as exc:
        LOGGER.warning(f"doupo duel broadcast setting read failed: {exc}")
        settings = {"broadcast_enabled": True}
    if not bool(settings.get("broadcast_enabled", True)):
        return
    winner = result.get("winner") or {}
    loser = result.get("loser") or {}
    stake = int(result.get("stake_gold") or 0)
    winner_name = str(winner.get("display_name") or "胜者").strip()
    loser_name = str(loser.get("display_name") or "败者").strip()
    lines = [f"🏆 **{_md_escape(winner_name)}** 赢下斗战，击败 **{_md_escape(loser_name)}**！"]
    if stake > 0:
        lines.append(f"🪙 金币转移：**{_md_escape(stake)}**")
    lines.append("🔥 *斗气之约，一战定胜负。*")
    md_text = _md_broadcast_card("斗破斗战播报", "⚔️", lines)
    try:
        await _send_message(client, chat_id, md_text, persistent=True, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        # MarkdownV2 失败时回退纯文本,保证播报不丢失。
        fallback_lines = [f"⚔️ 斗破斗战播报", f"🏆 {winner_name} 赢下斗战。"]
        if stake > 0:
            fallback_lines.append(f"🪙 金币转移：{stake}")
        try:
            await _send_message(client, chat_id, "\n".join(fallback_lines), persistent=True)
        except Exception as exc:
            LOGGER.warning(f"doupo duel broadcast failed chat={chat_id}: {exc}")


async def _finalize_doupo_duel_after_prepare(
    client,
    message,
    challenger_tg: int,
    defender_tg: int,
    stake: int,
    prepare_seconds: int,
) -> None:
    try:
        if prepare_seconds > 0:
            current_message = await _edit_message_text(
                message,
                f"⚔️ 斗战已接受\n⏱️ 备战倒计时 {int(prepare_seconds)} 秒。\n双方可在此期间调整资源，结算时会再次校验金币。",
            )
            await asyncio.sleep(int(prepare_seconds))
        else:
            current_message = await _edit_message_text(message, "⚔️ 斗战已接受\n🌀 斗气碰撞，战况开始推演。")
        result = await run_in_threadpool(resolve_doupo_duel, challenger_tg, defender_tg, stake)
        current_message = await _stream_doupo_duel_battle(current_message, result)
        await _edit_message_text(current_message, _format_duel_result_text(result))
        chat_id = int(getattr(getattr(current_message, "chat", None), "id", 0) or 0)
        await _push_duel_broadcast_if_needed(client, chat_id, result)
    except Exception as exc:
        LOGGER.exception(f"doupo duel finalize failed: {exc}")
        await _edit_message_text(message, f"⚠️ 斗战已取消\n{exc}")


async def _push_broadcast_if_needed(client, chat_id: int, result: dict[str, Any]) -> None:
    """群播报:动作结果含 broadcast 事件时,向指定群发送 MarkdownV2 排版的播报卡片。

    优先使用事件携带的 md(排版文本)发送,失败时回退为纯文本 text。
    """
    event = result.get("broadcast") or {}
    text = str(event.get("text") or "").strip()
    if not text:
        return
    title = str(event.get("title") or "斗破播报").strip()
    md_text = str(event.get("md") or "").strip()
    try:
        if md_text:
            await _send_message(client, chat_id, md_text, persistent=True, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await _send_message(client, chat_id, f"📢 {title}\n{text}", persistent=True)
    except Exception:
        # MarkdownV2 失败(如特殊字符漏转义)时回退纯文本,保证播报不丢失。
        try:
            await _send_message(client, chat_id, f"📢 {title}\n{text}", persistent=True)
        except Exception as exc:
            LOGGER.warning(f"doupo broadcast failed chat={chat_id}: {exc}")


async def _run_group_action(client, message, action_key: str) -> None:
    actor_tg = await run_in_threadpool(_sync_actor_identity, message)
    result = await run_in_threadpool(run_action, actor_tg, action_key)
    await _reply_text(message, _format_action_result(result), quote=True)
    chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)
    if chat_id:
        await _push_broadcast_if_needed(client, chat_id, result)


def register_bot(bot_instance) -> None:
    _ensure_doupo_bot_commands()
    _schedule_command_refresh(bot_instance)

    @bot_instance.on_message(filters.command(["doupo", "dp"], prefixes) & filters.private)
    async def doupo_private_command(_, message):
        try:
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            bundle = await run_in_threadpool(_profile_bundle, actor_tg)
            await _reply_text(
                message,
                _format_profile_text(bundle) + "\n\n群内可用：/dp_me /dp_bag /dp_rank /dp_sect /dp_duel /dp_train /dp_hunt /dp_alchemy /dp_fire /dp_boss",
                reply_markup=_miniapp_keyboard(),
                persistent=True,
            )
        except Exception as exc:
            LOGGER.exception(f"doupo private command failed: {exc}")
            await _reply_text(message, f"❌ 斗破入口加载失败：{exc}", quote=True)

    @bot_instance.on_message(filters.command(["doupo", "dp"], prefixes) & filters.chat(group))
    async def doupo_group_command(_, message):
        try:
            if not _register_command_dispatch(message, _command_name(message) or "doupo"):
                return
            lines = [
                "🎮 斗破玩法",
                "私聊机器人发送 /doupo 可打开斗破总览。",
                "群内命令：/dp_me 名帖，/dp_bag 纳戒，/dp_rank 排行。",
                "互动命令：/dp_sect 选择宗门，回复玩家 /dp_duel [金币] [备战秒数] 发起斗战。",
                "群内行动：/dp_train 修炼，/dp_hunt 历练，/dp_alchemy 炼药，/dp_fire 异火，/dp_boss 讨伐。",
                "关键突破、异火、稀有掉落和高战绩讨伐会自动播报。",
            ]
            await _reply_text(message, "\n".join(lines), quote=True, reply_markup=_miniapp_keyboard())
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dp_me", "doupo_me"], prefixes) & filters.chat(group))
    async def doupo_me_command(_, message):
        try:
            if not _register_command_dispatch(message, "dp_me"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            bundle = await run_in_threadpool(_profile_bundle, actor_tg)
            await _reply_text(message, _format_profile_text(bundle), quote=True)
        except Exception as exc:
            LOGGER.exception(f"doupo me command failed: {exc}")
            await _reply_text(message, f"❌ 斗破名帖加载失败：{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dp_bag", "doupo_bag"], prefixes) & filters.chat(group))
    async def doupo_bag_command(_, message):
        try:
            if not _register_command_dispatch(message, "dp_bag"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            inventory = await run_in_threadpool(list_player_inventory_grouped, actor_tg)
            await _reply_text(message, _format_inventory_text(inventory, display=_actor_name_label(message)), quote=True)
        except Exception as exc:
            LOGGER.exception(f"doupo bag command failed: {exc}")
            await _reply_text(message, f"❌ 纳戒读取失败：{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dp_rank", "doupo_rank"], prefixes) & filters.chat(group))
    async def doupo_rank_command(_, message):
        try:
            if not _register_command_dispatch(message, "dp_rank"):
                return
            args = getattr(message, "command", None) or []
            kind = str(args[1] if len(args) > 1 else "power")
            result = await run_in_threadpool(build_doupo_leaderboard, kind, 10)
            await _reply_text(message, _format_leaderboard_text(result), quote=True)
        except Exception as exc:
            LOGGER.exception(f"doupo rank command failed: {exc}")
            await _reply_text(message, f"❌ 排行榜读取失败：{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dp_sect", "doupo_sect"], prefixes) & filters.chat(group))
    async def doupo_sect_command(_, message):
        try:
            if not _register_command_dispatch(message, "dp_sect"):
                return
            actor_tg = await run_in_threadpool(_sync_actor_identity, message)
            bundle = await run_in_threadpool(_profile_bundle, actor_tg)
            if bundle["profile"].get("sect_name"):
                panel = await run_in_threadpool(get_sect_panel, actor_tg)
                await _reply_text(
                    message,
                    _format_sect_panel_text(panel, bundle["profile"]),
                    quote=True,
                    persistent=True,
                    reply_markup=_sect_panel_keyboard(actor_tg),
                )
                return
            await _reply_text(
                message,
                _format_sect_options_text(),
                quote=True,
                persistent=True,
                reply_markup=_sect_keyboard(actor_tg),
            )
        except Exception as exc:
            LOGGER.exception(f"doupo sect command failed: {exc}")
            await _reply_text(message, f"❌ 宗门读取失败：{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_message(filters.command(["dp_duel", "doupo_duel"], prefixes) & filters.chat(group))
    async def doupo_duel_command(_, message):
        try:
            if not _register_command_dispatch(message, "dp_duel"):
                return
            reply = getattr(message, "reply_to_message", None)
            target_user = getattr(reply, "from_user", None)
            if target_user is None:
                await _reply_text(message, "请回复一位玩家后使用 /dp_duel [金币] 发起斗战。", quote=True)
                return
            if bool(getattr(target_user, "is_bot", False)):
                await _reply_text(message, "不能向机器人发起斗战。", quote=True)
                return
            challenger_tg = await run_in_threadpool(_sync_actor_identity, message)
            defender_tg = await run_in_threadpool(_sync_pyrogram_user_identity, target_user)
            if challenger_tg == defender_tg:
                await _reply_text(message, "不能向自己发起斗战。", quote=True)
                return
            stake, prepare_override = _parse_duel_args_from_message(message)
            settings = await run_in_threadpool(get_settings)
            prepare_seconds = _duel_prepare_seconds(settings, prepare_override)
            preview = await run_in_threadpool(compute_doupo_duel_preview, challenger_tg, defender_tg, stake)
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
                reply_markup=_duel_invite_keyboard(nonce, challenger_tg, defender_tg),
            )
        except ValueError as exc:
            await _reply_text(message, str(exc), quote=True)
        except Exception as exc:
            LOGGER.exception(f"doupo duel command failed: {exc}")
            await _reply_text(message, f"❌ 斗战发起失败：{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:sect:join:([a-z_]+):(\d+)$"))
    async def doupo_sect_join_callback(_, call):
        sect_key = call.matches[0].group(1)
        actor_tg = int(call.matches[0].group(2))
        if int(getattr(call.from_user, "id", 0) or 0) != actor_tg:
            await call.answer("这不是你的宗门选择。", show_alert=True)
            return
        try:
            await run_in_threadpool(_sync_pyrogram_user_identity, call.from_user)
            result = await run_in_threadpool(join_sect, actor_tg, sect_key)
            text = f"⛩️ 宗门加入成功\n👤 玩家：{result['profile'].get('display_name')}\n⛩️ 宗门：{result['profile'].get('sect_name')}\n🏅 贡献：{int(result['profile'].get('sect_contribution') or 0)}"
            await call.message.edit_text(text, parse_mode=PLAIN_PARSE_MODE, reply_markup=_sect_panel_keyboard(actor_tg))
            await call.answer("已加入宗门")
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:sect:panel:(\d+)$"))
    async def doupo_sect_panel_callback(_, call):
        actor_tg = int(call.matches[0].group(1))
        if int(getattr(call.from_user, "id", 0) or 0) != actor_tg:
            await call.answer("这不是你的宗门面板。", show_alert=True)
            return
        try:
            await run_in_threadpool(_sync_pyrogram_user_identity, call.from_user)
            profile = await run_in_threadpool(get_or_create_profile, actor_tg)
            panel = await run_in_threadpool(get_sect_panel, actor_tg)
            await call.message.edit_text(
                _format_sect_panel_text(panel, profile),
                parse_mode=PLAIN_PARSE_MODE,
                reply_markup=_sect_panel_keyboard(actor_tg),
            )
            await call.answer("已刷新")
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:sect:quest:(\d+)$"))
    async def doupo_sect_quest_callback(_, call):
        actor_tg = int(call.matches[0].group(1))
        if int(getattr(call.from_user, "id", 0) or 0) != actor_tg:
            await call.answer("这不是你的宗门委托。", show_alert=True)
            return
        try:
            await run_in_threadpool(_sync_pyrogram_user_identity, call.from_user)
            result = await run_in_threadpool(claim_sect_quest, actor_tg)
            text = f"✅ 宗门委托完成\n{result['detail']}"
            await call.message.edit_text(text, parse_mode=PLAIN_PARSE_MODE, reply_markup=_sect_panel_keyboard(actor_tg))
            await call.answer("委托完成")
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:sect:transfer:(\d+)$"))
    async def doupo_sect_transfer_pick_callback(_, call):
        actor_tg = int(call.matches[0].group(1))
        if int(getattr(call.from_user, "id", 0) or 0) != actor_tg:
            await call.answer("这不是你的转宗操作。", show_alert=True)
            return
        try:
            await call.message.edit_text(
                "🌀 选择转宗目标",
                parse_mode=PLAIN_PARSE_MODE,
                reply_markup=_sect_transfer_keyboard(actor_tg),
            )
            await call.answer()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:sect:transfer:([a-z_]+):(\d+)$"))
    async def doupo_sect_transfer_callback(_, call):
        sect_key = call.matches[0].group(1)
        actor_tg = int(call.matches[0].group(2))
        if int(getattr(call.from_user, "id", 0) or 0) != actor_tg:
            await call.answer("这不是你的转宗操作。", show_alert=True)
            return
        try:
            await run_in_threadpool(_sync_pyrogram_user_identity, call.from_user)
            result = await run_in_threadpool(transfer_sect, actor_tg, sect_key)
            text = f"🌀 转宗成功\n{result['detail']}"
            await call.message.edit_text(text, parse_mode=PLAIN_PARSE_MODE, reply_markup=_sect_panel_keyboard(actor_tg))
            await call.answer("转宗成功")
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:sect:leave:(\d+)$"))
    async def doupo_sect_leave_callback(_, call):
        actor_tg = int(call.matches[0].group(1))
        if int(getattr(call.from_user, "id", 0) or 0) != actor_tg:
            await call.answer("这不是你的宗门操作。", show_alert=True)
            return
        try:
            await run_in_threadpool(_sync_pyrogram_user_identity, call.from_user)
            result = await run_in_threadpool(leave_sect, actor_tg)
            text = f"🚪 离开宗门\n{result['detail']}"
            await call.message.edit_text(text, parse_mode=PLAIN_PARSE_MODE)
            await call.answer("已离开宗门")
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_callback_query(filters.regex(r"^doupo:duel:(accept|reject|cancel):([a-f0-9]{12})$"))
    async def doupo_duel_callback(client, call):
        action = call.matches[0].group(1)
        nonce = call.matches[0].group(2)
        invite = PENDING_DUEL_INVITES.get(nonce)
        if invite is None:
            await call.answer("斗战邀请已失效。", show_alert=True)
            return
        caller_tg = int(getattr(call.from_user, "id", 0) or 0)
        challenger_tg = int(invite["challenger_tg"])
        defender_tg = int(invite["defender_tg"])
        if time.monotonic() - float(invite.get("created_at") or 0) > 300:
            PENDING_DUEL_INVITES.pop(nonce, None)
            await call.message.edit_text("⏰ 斗战邀请已超时", parse_mode=PLAIN_PARSE_MODE)
            await call.answer("邀请已超时", show_alert=True)
            return
        if action == "cancel":
            if caller_tg != challenger_tg:
                await call.answer("只有挑战者可以撤销。", show_alert=True)
                return
            PENDING_DUEL_INVITES.pop(nonce, None)
            await call.message.edit_text("↩️ 斗战邀请已撤销", parse_mode=PLAIN_PARSE_MODE)
            await call.answer("已撤销")
            return
        if caller_tg != defender_tg:
            await call.answer("只有应战者可以处理这个邀请。", show_alert=True)
            return
        if action == "reject":
            PENDING_DUEL_INVITES.pop(nonce, None)
            await call.message.edit_text("❌ 斗战邀请已被拒绝", parse_mode=PLAIN_PARSE_MODE)
            await call.answer("已拒绝")
            return
        try:
            await run_in_threadpool(_sync_pyrogram_user_identity, call.from_user)
            stake = int(invite.get("stake") or 0)
            prepare_seconds = _duel_prepare_seconds({"duel_prepare_seconds": invite.get("prepare_seconds")})
            PENDING_DUEL_INVITES.pop(nonce, None)
            edited = await _edit_message_text(call.message, "⚔️ 斗战已接受\n🌀 斗气正在汇聚。")
            asyncio.create_task(
                _finalize_doupo_duel_after_prepare(
                    client,
                    edited,
                    challenger_tg,
                    defender_tg,
                    stake,
                    prepare_seconds,
                )
            )
            await call.answer("斗战已开始")
        except Exception as exc:
            LOGGER.exception(f"doupo duel callback failed: {exc}")
            await call.answer(str(exc), show_alert=True)

    @bot_instance.on_message(filters.command(list(GROUP_ACTION_COMMANDS.keys()), prefixes) & filters.chat(group))
    async def doupo_group_action_command(client, message):
        command_name = _command_name(message)
        try:
            if not _register_command_dispatch(message, command_name):
                return
            action = GROUP_ACTION_COMMANDS.get(command_name)
            if action is None:
                await _reply_text(message, "未知斗破行动。", quote=True)
                return
            action_key, _label = action
            await _run_group_action(client, message, action_key)
        except ValueError as exc:
            await _reply_text(message, str(exc) or "行动条件不足。", quote=True)
        except Exception as exc:
            LOGGER.exception(f"doupo group action failed command={command_name}: {exc}")
            await _reply_text(message, f"❌ 行动失败：{exc}", quote=True)
        finally:
            await _delete_user_command_message(message)

    LOGGER.info("Doupo bot handlers registered")
