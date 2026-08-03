from datetime import timedelta, datetime

from pyrogram import filters
from pyrogram.errors import BadRequest

from bot import bot, prefixes, LOGGER
from bot.func_helper.emby import emby
from bot.func_helper.filters import admins_on_filter
from bot.func_helper.msg_utils import deleteMessage, sendMessage
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby
from bot.sql_helper.sql_emby2 import sql_get_emby2, sql_update_emby2, Emby2


async def get_user_input(msg):
    await deleteMessage(msg)
    gm_name = msg.sender_chat.title if msg.sender_chat else f'主人 [{msg.from_user.first_name}]({msg.from_user.id})'
    if msg.reply_to_message is None:
        try:
            b = msg.command[1]  # name
            c = float(msg.command[2])  # 天数
        except (IndexError, KeyError, BadRequest, ValueError, AttributeError):
            return None, None, None, None
    else:
        try:
            b = msg.reply_to_message.from_user.id
            c = float(msg.command[1])
        except (IndexError, KeyError, BadRequest, ValueError, AttributeError):
            return None, None, None, None

    e = sql_get_emby(tg=b)
    stats = None
    if not e:
        e2 = sql_get_emby2(name=b)
        if not e2:
            await sendMessage(msg, f"♻️ 未检索到Emby {b}，请确认重试或手动检查。")
            return None, None, None, None
        e = e2
        stats = 1

    return c, e, stats, gm_name


@bot.on_message(filters.command('renew', prefixes) & admins_on_filter)
async def renew_user(_, msg):
    days, e, stats, gm_name = await get_user_input(msg)
    if not e:
        return await sendMessage(msg,
                                 f"🔔 **使用格式：**\n\n/renew [Emby账户名] [+/-天数]\n或回复某人 /renew [+/-天数]",
                                 timer=60)
    reply = await msg.reply(f"🍓 正在处理ing···/·")
    try:
        name = f'[{e.name}]({e.tg})' if e.tg else e.name
    except:
        name = e.name
    # 时间是 utc 来算的；e.ex 可能为空，空时从当前时间起算
    Now = datetime.now()
    ex_base = e.ex if isinstance(e.ex, datetime) else None
    start_from = ex_base if (ex_base and ex_base > Now) else Now
    ex_new = start_from + timedelta(days=days)
    lv = e.lv
    # 无脑 允许播放
    if ex_new > Now:
        lv = 'a' if e.lv == 'a' else 'b'
        if e.embyid and not await emby.emby_change_policy(emby_id=e.embyid, disable=False):
            await reply.edit("❌ Emby 策略修改失败（允许播放），数据库未变更，请检查 Emby 服务后重试")
            LOGGER.error(f"【admin】[renew]：{gm_name} 对 emby账户 {name} 允许播放策略修改失败")
            return

    # 没有白名单就寄
    elif ex_new < Now:
        if e.lv == 'a':
            pass
        else:
            lv = 'c'
            if e.embyid and not await emby.emby_change_policy(emby_id=e.embyid, disable=True):
                await reply.edit("❌ Emby 策略修改失败（禁用播放），数据库未变更，请检查 Emby 服务后重试")
                LOGGER.error(f"【admin】[renew]：{gm_name} 对 emby账户 {name} 禁用播放策略修改失败")
                return
    if stats == 1:
        expired = 1 if lv == 'c' else 0
        updated = sql_update_emby2(Emby2.embyid == e.embyid, ex=ex_new, expired=expired)
    else:
        updated = sql_update_emby(Emby.tg == e.tg, ex=ex_new, lv=lv)

    if not updated:
        # DB 写入失败：回滚 Emby 策略（若刚改过），避免 Emby 与数据库不一致。
        LOGGER.error(f"【admin】[renew]：{gm_name} 对 emby账户 {name} 数据库写入失败，尝试回滚 Emby 策略")
        try:
            if e.embyid:
                await emby.emby_change_policy(emby_id=e.embyid, disable=(lv == 'c'))
        except Exception as exc:
            LOGGER.error(f"【admin】[renew]：{name} Emby 策略回滚失败: {exc}")
        return await reply.edit("❌ 数据库写入失败，Emby 策略已回滚，请稍后重试")
    i = await reply.edit(
        f'🍒 __ {gm_name} 已调整 emby 用户 {name} 到期时间 {days} 天 (以当前时间计)__'
        f'\n📅 实时到期：{ex_new.strftime("%Y-%m-%d %H:%M:%S")}')
    try:
        await i.forward(e.tg)
    except:
        pass

    LOGGER.info(
        f"【admin】[renew]：{gm_name} 对 emby账户 {name} 调节 {days} 天，"
        f"实时到期：{ex_new.strftime('%Y-%m-%d %H:%M:%S')}")
