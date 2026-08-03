"""
小功能 - 给所有未被封禁的 emby 延长指定天数。加货币
"""
import asyncio
import time
from datetime import timedelta

from pyrogram import filters
from pyrogram.errors import FloodWait
from sqlalchemy import or_
from bot import bot, prefixes, bot_photo, LOGGER, sakura_b
from bot.func_helper.msg_utils import sendMessage, deleteMessage, ask_return
from bot.func_helper.filters import admins_on_filter
from bot.sql_helper.sql_emby import get_all_emby, Emby, sql_update_embys, sql_clear_emby_iv, sql_adjust_emby_iv


_batch_lock = asyncio.Lock()


async def _acquire_batch_lock(msg) -> bool:
    """批量任务互斥：同一时间只允许一个批量命令执行。"""
    if _batch_lock.locked():
        await sendMessage(msg, '⏳ 已有批量任务正在运行，请等待完成后再试', timer=60)
        return False
    await _batch_lock.acquire()
    return True




@bot.on_message(filters.command('renewall', prefixes) & admins_on_filter)
async def renew_all(_, msg):
    if not await _acquire_batch_lock(msg):
        return
    try:
        await _renew_all_impl(_, msg)
    finally:
        _batch_lock.release()


async def _renew_all_impl(_, msg):
    await deleteMessage(msg)
    # send_chat
    try:
        a = float(msg.command[1])
    except (IndexError, ValueError):
        return await sendMessage(msg,
                                 "🔔 **使用格式：**/renewall [+/-天数]\n\n  给所有未封禁emby [+/-天数]", timer=60)

    send = await bot.send_photo(msg.chat.id, photo=bot_photo, caption="⚡【派送任务】\n  **正在开启派送中...请稍后**")
    rst = get_all_emby(Emby.lv == 'b')
    if rst is None:
        LOGGER.info(
            f"【派送任务】 -{msg.from_user.first_name}({msg.from_user.id}) 没有检测到任何emby账户，结束")
        return await send.edit("⚡【派送任务】\n\n结束，没有一个有号的")

    b = 0
    ls = []
    start = time.perf_counter()
    for i in rst:
        if i.ex is None:
            continue
        b += 1
        ex_new = i.ex + timedelta(days=a)
        ls.append([i.tg, ex_new])
    if sql_update_embys(some_list=ls, method='ex'):
        end = time.perf_counter()
        times = end - start
        await send.edit(
            f"⚡【派送任务】\n  批量派出 {a} 天 * {b} ，耗时：{times:.3f}s\n 时间已到账，正在向每个拥有emby的用户私发消息，短时间内请不要重复使用")
        LOGGER.info(
            f"【派送任务】 - {msg.from_user.first_name}({msg.from_user.id}) 派出 {a} 天 * {b} 更改用时{times:.3f} s")
        for l in ls:
            await bot.send_message(l[0], f"🎯 主人 {msg.from_user.first_name} 调节了您的账户 到期时间：{a}天"
                                         f'\n📅 实时到期：{l[1].strftime("%Y-%m-%d %H:%M:%S")}')
        LOGGER.info(
            f"【派送任务】 - {msg.from_user.first_name}({msg.from_user.id}) 派出 {a} 天 * {b}，消息私发完成")
    else:
        await msg.reply("❌ 数据库操作出错，请检查重试")


# coinsall 全部人加片刻碎片
@bot.on_message(filters.command('coinsall', prefixes) & admins_on_filter)
async def coins_all(_, msg):
    if not await _acquire_batch_lock(msg):
        return
    try:
        await _coins_all_impl(_, msg)
    finally:
        _batch_lock.release()


async def _coins_all_impl(_, msg):
    await deleteMessage(msg)
    try:
        coin = int(msg.command[1])
        lv = msg.command[2]
        # 获取是否发送私信的参数，默认为 False（不发送）
        send_msg = False
        if len(msg.command) > 3:
            send_msg_param = msg.command[3].lower()
            send_msg = send_msg_param == 'true'
    except (IndexError, ValueError):
        return await sendMessage(msg,
                                 f"🔔 **使用格式：**/coinsall [+/-数量] [等级] [发送消息]\n\n给指定等级的用户 [+/- {sakura_b}]\n示例： `/coinsall 100 b` 给所有b级用户加100{sakura_b}\n示例： `/coinsall 100 b true` 给所有b级用户加100{sakura_b}并私发消息\n等级说明:\na- 白名单账户\nb- 正常账户\nc- 已封禁账户\n发送消息参数：true 表示发送私信，默认不发送\n", timer=60)
    send = await bot.send_photo(msg.chat.id, photo=bot_photo,
                                caption=f"⚡【{sakura_b}任务】\n  **正在开启派送{sakura_b}中...请稍后**")
    rst = get_all_emby(Emby.lv == lv)
    if rst is None:
        LOGGER.info(
            f"【{sakura_b}任务】 -{msg.from_user.first_name}({msg.from_user.id}) 没有检测到任何emby账户，结束")
        return await send.edit("⚡【派送任务】\n\n结束，没有一个有号的")

    b = 0
    skipped = 0
    ls = []
    start = time.perf_counter()
    sign_name = f'{msg.sender_chat.title}' if msg.sender_chat else f'{msg.from_user.first_name}'
    for i in rst:
        # 逐用户原子调整：避免批量读改写覆盖并发消费，且扣减不会使余额为负
        new_iv = sql_adjust_emby_iv(i.tg, coin)
        if new_iv is None:
            skipped += 1
            continue
        b += 1
        ls.append([i.tg, new_iv])
    end = time.perf_counter()
    times = end - start
    summary = f"⚡【{sakura_b}任务】\n\n  批量派出 {coin} {sakura_b} * {b} ，耗时：{times:.3f}s\n 已到账"
    if send_msg:
        summary += "\n 正在向每个拥有emby的用户私发消息，短时间内请不要重复使用"
    if skipped:
        summary += f"\n ⚠️ {skipped} 个用户余额不足或不存在，未变更"
    await send.edit(summary)
    LOGGER.info(
        f"【派送{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 派出 {coin} * {b}（跳过 {skipped}）更改用时{times:.3f} s")

    # 根据参数决定是否发送私信
    if send_msg:
        for l in ls:
            try:
                await bot.send_message(l[0], f"🎯 主人 {sign_name} 调节了您的账户{sakura_b} {coin}"
                                         f'\n📅 实时数量：{l[1]}')
            except FloodWait as f:
                LOGGER.warning(str(f))
                await asyncio.sleep(f.value * 1.2)
                await bot.send_message(l[0], f"🎯 主人 {sign_name} 调节了您的账户{sakura_b} {coin}"
                                         f'\n📅 实时数量：{l[1]}')
            except Exception as e:
                LOGGER.error(f"派送{sakura_b}任务失败：{l[0]} {e}")
                continue
        LOGGER.info(
            f"【派送{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 派出 {coin} {sakura_b} * {b}，消息私发完成")

# coinsclear 清除用户片刻碎片
@bot.on_message(filters.command('coinsclear', prefixes) & admins_on_filter)
async def coinsclear(_, msg):
    if not await _acquire_batch_lock(msg):
        return
    try:
        await _coinsclear_impl(_, msg)
    finally:
        _batch_lock.release()


async def _coinsclear_impl(_, msg):
    await deleteMessage(msg)
    try:
        level_param = msg.command[1].lower()
        confirm_param = msg.command[2].lower() if len(msg.command) > 2 else None
    except (IndexError, ValueError):
        return await sendMessage(msg,
                                 f"🔔 **使用格式：**\n\n`/coinsclear [等级/all] true`\n\n清除指定等级用户的{sakura_b}\n等级说明:\na- 白名单账户\nb - 正常账户\nc- 已封禁账户\nd- 无账号用户\n\n示例：\n`/coinsclear all true` - 清除所有用户{sakura_b}\n`/coinsclear a true` - 清除a级用户{sakura_b}\n`/coinsclear b true` - 清除b级用户{sakura_b}\n`/coinsclear c true` - 清除c级用户{sakura_b}\n`/coinsclear d true` - 清除d级用户{sakura_b}", timer=60)
    
    # 验证第二个参数必须是 true
    if confirm_param != 'true':
        return await sendMessage(msg,
                                 f"🔔 **使用格式：**\n\n`/coinsclear [等级/all] true`\n\n⚠️ 第二个参数必须是 `true` 才能执行清除操作\n\n示例：\n`/coinsclear all true` - 清除所有用户{sakura_b}\n`/coinsclear b true` - 清除b级用户{sakura_b}", timer=60)
    
    sign_name = f'{msg.sender_chat.title}' if msg.sender_chat else f'{msg.from_user.first_name}'
    
    # 清除所有用户片刻碎片
    if level_param == 'all':
        send = await bot.send_photo(msg.chat.id, photo=bot_photo,
                                caption=f"⚡【{sakura_b}任务】\n  **正在清除所有用户{sakura_b}...请稍后**")
        rst = sql_clear_emby_iv()
        if rst:
            await send.edit(f"⚡【{sakura_b}任务】\n\n  清除所有用户{sakura_b}完成")
            LOGGER.info(f"【清除{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 清除所有用户{sakura_b}完成")
        else:
            await send.edit(f"⚡【{sakura_b}任务】\n\n  清除所有用户{sakura_b}失败")
            LOGGER.error(f"【清除{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 清除所有用户{sakura_b}失败")
    # 根据等级清除片刻碎片
    elif level_param in ['a', 'b', 'c', 'd']:
        lv = level_param
        send = await bot.send_photo(msg.chat.id, photo=bot_photo,
                                caption=f"⚡【{sakura_b}任务】\n  **正在清除{lv}级用户{sakura_b}...请稍后**")
        
        # 获取指定等级的所有用户
        rst = get_all_emby(Emby.lv == lv)
        if rst is None or len(rst) == 0:
            LOGGER.info(f"【清除{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 没有检测到{lv}级用户")
            return await send.edit(f"⚡【{sakura_b}任务】\n\n  没有检测到{lv}级用户")
        
        # 批量将片刻碎片设置为0
        ls = []
        for i in rst:
            ls.append([i.tg, 0])
        
        if sql_update_embys(some_list=ls, method='iv'):
            count = len(ls)
            await send.edit(f"⚡【{sakura_b}任务】\n\n  清除{lv}级用户{sakura_b}完成\n  共清除 {count} 个用户")
            LOGGER.info(f"【清除{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 清除{lv}级用户{sakura_b}完成，共 {count} 个用户")
        else:
            await send.edit(f"⚡【{sakura_b}任务】\n\n  清除{lv}级用户{sakura_b}失败")
            LOGGER.error(f"【清除{sakura_b}任务】 - {sign_name}({msg.from_user.id}) 清除{lv}级用户{sakura_b}失败")
    else:
        return await sendMessage(msg,
                                 f"🔔 **使用格式：**\n\n`/coinsclear [等级/all] true`\n\n⚠️ 等级参数必须是：`all`、`a`、`b`、`c` 或 `d`\n\n等级说明:\na- 白名单账户\nb - 正常账户\nc- 已封禁账户\nd- 无账号用户\n\n示例：\n`/coinsclear all true` - 清除所有用户{sakura_b}\n`/coinsclear b true` - 清除b级用户{sakura_b}", timer=60)
@bot.on_message(filters.command('callall', prefixes) & admins_on_filter & filters.private)
async def call_all(_, msg):
    if not await _acquire_batch_lock(msg):
        return
    try:
        await _call_all_impl(_, msg)
    finally:
        _batch_lock.release()


async def _call_all_impl(_, msg):
    await msg.delete()
    # 可以做分级 所有 b类 非群组类 ：太麻烦，随便搞搞就行
    m = await ask_return(msg,
                         text='**🕶️ 一键公告**\n\n倒计时10min，发送您想要公告的消息，然后根据提示选择发送的用户组，取消请 /cancel',
                         timer=600)

    if not m:
        return
    elif m.text == '/cancel':
        return

    call = await ask_return(msg,
                         text='📢 回复 `1` - 仅公告账户的人\n回复 `2` - 公告全体成员\n取消请 /cancel',
                         timer=600)

    if not call or call.text == '/cancel':
        return await msg.reply('好的，您已取消操作。✅')
    elif call.text == '2':
        chat_members = get_all_emby(Emby.tg is not None)
    elif call.text == '1':
        chat_members = get_all_emby(Emby.embyid is not None)
    reply = await msg.reply('⏳ 开始执行发送......')
    a = 0
    start = time.perf_counter()
    for member in chat_members:
        try:
            a += 1
            await m.copy(member.tg)
        except FloodWait as f:
            LOGGER.warning(str(f))
            await asyncio.sleep(f.value * 1.2)
            return await m.copy(member.tg)
        except Exception as e:
            LOGGER.warning(str(e))
    end = time.perf_counter()
    times = end - start
    await reply.edit(f'✅ 消息发送完毕\n\n共计：{a} 次，用时 {times:.3f} s')
    LOGGER.info(f'【群发消息】：{msg.from_user.first_name} 消息发送完毕 - 共计：{a} 次，用时 {times:.3f} s')
