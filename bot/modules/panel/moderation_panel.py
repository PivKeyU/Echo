from __future__ import annotations

from pyrogram import filters

from bot import LOGGER, bot, owner, prefixes
from bot.func_helper.filters import admins_on_filter
from bot.func_helper.moderation import (
    ModerationAmbiguousError,
    ModerationLookupError,
    ModerationServiceError,
    clear_chat_member_warning,
    get_chat_warning_state,
    kick_chat_member,
    mute_chat_member,
    pin_chat_message,
    resolve_chat_member,
    set_chat_member_title,
    unpin_chat_message,
    update_warning_config,
    warn_chat_member,
)
from bot.func_helper.msg_utils import sendMessage


def _actor_label(msg) -> str:
    if msg.sender_chat:
        return str(msg.sender_chat.title or msg.sender_chat.id)
    if msg.from_user:
        return f"[{msg.from_user.first_name}](tg://user?id={msg.from_user.id})"
    return "管理员"


def _actor_id(msg) -> int | None:
    if msg.from_user:
        return int(msg.from_user.id)
    return None


def _member_link(member: dict) -> str:
    label = member.get("display_name") or member.get("username") or f"TG {member.get('tg')}"
    return f"[{label}](tg://user?id={member['tg']})"


def _format_ambiguous_matches(matches: list[dict]) -> str:
    if not matches:
        return ""
    lines = []
    for item in matches[:5]:
        parts = [
            _member_link(item),
            f"`{item['tg']}`",
            f"@{item['username']}" if item.get("username") else "",
            item.get("status_text") or "",
        ]
        lines.append(" · ".join(part for part in parts if part))
    return "\n".join(lines)


async def _resolve_target_from_command(msg):
    reply_user = getattr(getattr(msg, "reply_to_message", None), "from_user", None)
    if reply_user is not None:
        return await resolve_chat_member(msg.chat.id, reply_user=reply_user), list(msg.command[1:])

    if len(msg.command) < 2:
        raise ModerationLookupError("请回复目标用户，或提供 TGID / @username / 昵称关键词。")

    target = msg.command[1]
    return await resolve_chat_member(msg.chat.id, target=target), list(msg.command[2:])


async def _ensure_not_owner_target(msg, member: dict) -> bool:
    actor_id = _actor_id(msg)
    if int(member["tg"]) == int(owner) and actor_id != int(owner):
        await sendMessage(msg, "⚠️ 不能对主人执行这个操作。", timer=60)
        return False
    return True


@bot.on_message(filters.command("mute", prefixes) & admins_on_filter & filters.group)
async def mute_group_member(_, msg):
    try:
        member, remaining = await _resolve_target_from_command(msg)
        if not await _ensure_not_owner_target(msg, member):
            return
        if not remaining:
            return await sendMessage(
                msg,
                "用法：回复用户 `/mute 60 原因`，或 `/mute TGID|@username|昵称 60 原因`\n`0` 分钟表示解除禁言。",
                timer=90,
            )
        try:
            minutes = int(remaining[0])
        except (TypeError, ValueError):
            return await sendMessage(msg, "禁言分钟数必须是整数。", timer=60)

        reason = " ".join(remaining[1:]).strip() or None
        result = await mute_chat_member(msg.chat.id, member["tg"], minutes)
        action_text = "解除禁言" if minutes <= 0 else "禁言"
        lines = [
            f"· 操作 | {action_text}",
            f"· 对象 | {_member_link(member)}",
            f"· 时长 | {'已解除' if minutes <= 0 else f'{minutes} 分钟'}",
            f"· 执行人 | {_actor_label(msg)}",
        ]
        if reason:
            lines.append(f"· 原因 | {reason}")
        await sendMessage(msg, "\n".join(lines), timer=120)
        LOGGER.info(f"moderation mute actor={_actor_id(msg)} chat={msg.chat.id} target={member['tg']} minutes={minutes} result={result}")
    except ModerationAmbiguousError as exc:
        await sendMessage(msg, f"{exc}\n\n{_format_ambiguous_matches(exc.matches)}", timer=120)
    except (ModerationLookupError, ModerationServiceError) as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("kick", prefixes) & admins_on_filter & filters.group)
async def kick_group_member(_, msg):
    try:
        member, remaining = await _resolve_target_from_command(msg)
        if not await _ensure_not_owner_target(msg, member):
            return
        reason = " ".join(remaining).strip() or None
        result = await kick_chat_member(msg.chat.id, member["tg"])
        lines = [
            "· 操作 | 踢出群组",
            f"· 对象 | {_member_link(member)}",
            f"· 执行人 | {_actor_label(msg)}",
        ]
        if reason:
            lines.append(f"· 原因 | {reason}")
        await sendMessage(msg, "\n".join(lines), timer=120)
        LOGGER.info(f"moderation kick actor={_actor_id(msg)} chat={msg.chat.id} target={member['tg']} result={result}")
    except ModerationAmbiguousError as exc:
        await sendMessage(msg, f"{exc}\n\n{_format_ambiguous_matches(exc.matches)}", timer=120)
    except (ModerationLookupError, ModerationServiceError) as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("settitle", prefixes) & admins_on_filter & filters.group)
async def set_group_member_title(_, msg):
    try:
        member, remaining = await _resolve_target_from_command(msg)
        if not await _ensure_not_owner_target(msg, member):
            return
        title = " ".join(remaining).strip()
        if not title:
            return await sendMessage(
                msg,
                "用法：回复管理员 `/settitle 新头衔`，或 `/settitle TGID|@username|昵称 新头衔`",
                timer=90,
            )
        result = await set_chat_member_title(msg.chat.id, member["tg"], title)
        await sendMessage(
            msg,
            "\n".join(
                [
                    "· 操作 | 设置头衔",
                    f"· 对象 | {_member_link(member)}",
                    f"· 新头衔 | {result['title']}",
                    f"· 执行人 | {_actor_label(msg)}",
                ]
            ),
            timer=120,
        )
        LOGGER.info(f"moderation title actor={_actor_id(msg)} chat={msg.chat.id} target={member['tg']} title={result['title']}")
    except ModerationAmbiguousError as exc:
        await sendMessage(msg, f"{exc}\n\n{_format_ambiguous_matches(exc.matches)}", timer=120)
    except (ModerationLookupError, ModerationServiceError) as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("pin", prefixes) & admins_on_filter & filters.group)
async def pin_group_message(_, msg):
    reply_message = getattr(msg, "reply_to_message", None)
    if reply_message is not None:
        message_id = int(reply_message.id)
    else:
        try:
            message_id = int(msg.command[1])
        except (IndexError, TypeError, ValueError):
            return await sendMessage(msg, "用法：回复需要置顶的消息发送 `/pin`，或 `/pin 消息ID`", timer=90)

    try:
        result = await pin_chat_message(msg.chat.id, message_id)
        await sendMessage(
            msg,
            f"· 操作 | 置顶消息\n· 消息ID | `{result['message_id']}`\n· 执行人 | {_actor_label(msg)}",
            timer=120,
        )
        LOGGER.info(f"moderation pin actor={_actor_id(msg)} chat={msg.chat.id} message_id={message_id}")
    except ModerationServiceError as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("unpin", prefixes) & admins_on_filter & filters.group)
async def unpin_group_message(_, msg):
    reply_message = getattr(msg, "reply_to_message", None)
    message_id = None
    if reply_message is not None:
        message_id = int(reply_message.id)
    elif len(msg.command) >= 2:
        try:
            message_id = int(msg.command[1])
        except (TypeError, ValueError):
            return await sendMessage(msg, "消息 ID 必须是整数。", timer=60)

    try:
        result = await unpin_chat_message(msg.chat.id, message_id)
        scope_text = f"`{result['message_id']}`" if result.get("message_id") is not None else "最近一条置顶消息"
        await sendMessage(
            msg,
            f"· 操作 | 取消置顶\n· 目标 | {scope_text}\n· 执行人 | {_actor_label(msg)}",
            timer=120,
        )
        LOGGER.info(f"moderation unpin actor={_actor_id(msg)} chat={msg.chat.id} message_id={message_id}")
    except ModerationServiceError as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("warn", prefixes) & admins_on_filter & filters.group)
async def warn_group_member(_, msg):
    try:
        member, remaining = await _resolve_target_from_command(msg)
        if not await _ensure_not_owner_target(msg, member):
            return
        reason = " ".join(remaining).strip() or None
        result = await warn_chat_member(
            msg.chat.id,
            member["tg"],
            actor_tg=_actor_id(msg),
            reason=reason,
        )
        warning = result["warning"] or {}
        settings = result["settings"] or {}
        lines = [
            "· 操作 | 警告用户",
            f"· 对象 | {_member_link(member)}",
            f"· 当前警告 | {warning.get('warn_count', 0)} / {settings.get('warn_threshold', 0)}",
            f"· 达标处罚 | {settings.get('warn_action', 'mute')}",
            f"· 执行人 | {_actor_label(msg)}",
        ]
        if settings.get("warn_action") == "mute":
            lines.append(f"· 自动禁言 | {settings.get('mute_minutes', 0)} 分钟")
        if reason:
            lines.append(f"· 原因 | {reason}")
        if result.get("action_triggered") and result.get("action_result"):
            lines.append(f"· 自动处罚 | {result['action_result']['message']}")
        elif result.get("action_error"):
            lines.append(f"· 自动处罚失败 | {result['action_error']}")
        await sendMessage(msg, "\n".join(lines), timer=150)
        LOGGER.info(
            f"moderation warn actor={_actor_id(msg)} chat={msg.chat.id} target={member['tg']} "
            f"warn_count={warning.get('warn_count')} action_triggered={result.get('action_triggered')}"
        )
    except ModerationAmbiguousError as exc:
        await sendMessage(msg, f"{exc}\n\n{_format_ambiguous_matches(exc.matches)}", timer=120)
    except (ModerationLookupError, ModerationServiceError) as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("clearwarn", prefixes) & admins_on_filter & filters.group)
async def clear_group_member_warn(_, msg):
    try:
        member, _ = await _resolve_target_from_command(msg)
        if not await _ensure_not_owner_target(msg, member):
            return
        result = clear_chat_member_warning(msg.chat.id, member["tg"])
        if not result.get("removed"):
            return await sendMessage(msg, f"{_member_link(member)} 当前没有警告记录。", timer=90)
        await sendMessage(
            msg,
            "\n".join(
                [
                    "· 操作 | 清空警告",
                    f"· 对象 | {_member_link(member)}",
                    f"· 执行人 | {_actor_label(msg)}",
                ]
            ),
            timer=120,
        )
        LOGGER.info(f"moderation clearwarn actor={_actor_id(msg)} chat={msg.chat.id} target={member['tg']}")
    except ModerationAmbiguousError as exc:
        await sendMessage(msg, f"{exc}\n\n{_format_ambiguous_matches(exc.matches)}", timer=120)
    except (ModerationLookupError, ModerationServiceError) as exc:
        await sendMessage(msg, str(exc), timer=90)


@bot.on_message(filters.command("warnconfig", prefixes) & admins_on_filter & filters.group)
async def warn_config_group(_, msg):
    actor_id = _actor_id(msg)
    if len(msg.command) == 1:
        state = get_chat_warning_state(msg.chat.id, actor_id or 0)
        settings = state["settings"] or {}
        lines = [
            "当前群警告配置：",
            f"· 阈值 | {settings.get('warn_threshold', 0)} 次",
            f"· 处罚 | {settings.get('warn_action', 'mute')}",
            f"· 禁言时长 | {settings.get('mute_minutes', 0)} 分钟",
        ]
        return await sendMessage(msg, "\n".join(lines), timer=120)

    if len(msg.command) < 3:
        return await sendMessage(
            msg,
            "用法：`/warnconfig 次数 mute 禁言分钟` 或 `/warnconfig 次数 kick`\n例如：`/warnconfig 3 mute 60`",
            timer=120,
        )

    try:
        threshold = int(msg.command[1])
    except (TypeError, ValueError):
        return await sendMessage(msg, "警告次数阈值必须是整数。", timer=60)

    action = str(msg.command[2] or "").strip().lower()
    if action not in {"mute", "kick"}:
        return await sendMessage(msg, "处罚动作只能是 `mute` 或 `kick`。", timer=60)

    mute_minutes = 60
    if action == "mute":
        try:
            mute_minutes = int(msg.command[3]) if len(msg.command) >= 4 else 60
        except (TypeError, ValueError):
            return await sendMessage(msg, "禁言分钟数必须是整数。", timer=60)

    try:
        settings = await update_warning_config(
            msg.chat.id,
            warn_threshold=threshold,
            warn_action=action,
            mute_minutes=mute_minutes,
            updated_by=actor_id,
        )
        lines = [
            "· 操作 | 更新警告配置",
            f"· 群组 | `{msg.chat.id}`",
            f"· 阈值 | {settings['warn_threshold']} 次",
            f"· 处罚 | {settings['warn_action']}",
            f"· 禁言时长 | {settings['mute_minutes']} 分钟",
            f"· 执行人 | {_actor_label(msg)}",
        ]
        await sendMessage(msg, "\n".join(lines), timer=150)
        LOGGER.info(f"moderation warnconfig actor={actor_id} chat={msg.chat.id} settings={settings}")
    except ModerationServiceError as exc:
        await sendMessage(msg, str(exc), timer=90)
