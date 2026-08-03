"""
用户区面板代码
先检测有无账户
无 -> 创建账户、换绑tg

有 -> 账户续期，重置密码，删除账户，显隐媒体库
"""
import asyncio
import datetime
import math
import random
import re
from datetime import timedelta, datetime
from bot.schemas import ExDate, Yulv
from bot import bot, LOGGER, _open, emby_line, sakura_b, ranks, group, config, schedall, lv_allowed
from pyrogram import filters
from bot.func_helper.emby import emby
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.utils import members_info, tem_adduser, cr_link_one, judge_admins, tem_deluser, pwd_create, refresh_registration_slots
from bot.func_helper.register_queue import register_create_queue
from bot.func_helper.fix_bottons import members_ikb, back_members_ikb, re_create_ikb, del_me_ikb, re_delme_ikb, \
    re_reset_ikb, re_changetg_ikb, emby_block_ikb, user_emby_block_ikb, user_emby_unblock_ikb, re_exchange_b_ikb, \
    store_ikb, re_bindtg_ikb, close_it_ikb, store_query_page, re_born_ikb, send_changetg_ikb, \
    re_change_pwd2_ikb
from bot.func_helper.msg_utils import callAnswer, editMessage, callListen, sendMessage, ask_return, deleteMessage
from bot.modules.commands import p_start
from bot.modules.commands.partition_code import _redeem_partition_code
from bot.modules.commands.exchange import rgs_code
from bot.sql_helper.sql_code import sql_count_c_code, sql_get_code, sql_get_code_redeem_history
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby
from bot.sql_helper.sql_emby2 import sql_get_emby2, sql_delete_emby2

_SECURITY_CODE_PATTERN = re.compile(r"^\d{4,6}$")
_REGISTRATION_CAPACITY_LOCK = asyncio.Lock()


def _is_valid_security_code(value: str) -> bool:
    return bool(_SECURITY_CODE_PATTERN.fullmatch((value or "").strip()))


def _emby_expiry_display(lv, ex) -> str:
    return "无限期" if str(lv or "").strip() == "a" else str(ex or "未设置")


def _mask_register_code(code_value: str) -> str:
    code_value = str(code_value or "")
    if len(code_value) <= 7:
        return "░" * len(code_value)
    return f"{code_value[:-7]}{'░' * 7}"


def _latest_register_code_summary(user_id: int):
    history = sql_get_code_redeem_history(user_id=user_id, limit=1)
    if not history:
        return None

    redeem = history[0]
    record = sql_get_code(redeem.code)
    use_count = int(getattr(record, "use_count", None) or getattr(redeem, "use_index", 0) or 0)
    use_limit = int(getattr(record, "use_limit", None) or 1)
    days = int(getattr(redeem, "code_days", None) or getattr(record, "us", None) or 0)
    return {
        "code": _mask_register_code(redeem.code),
        "usage": f"{use_count}/{max(use_limit, 1)}",
        "days": days,
    }


async def _broadcast_register_create_success(status_message, user_id: int, username: str, expires_text: str):
    code_summary = _latest_register_code_summary(user_id)
    if code_summary:
        source_text = (
            f"🎫 注册码 - {code_summary['code']}\n"
            f"📊 使用进度 - {code_summary['usage']}\n"
            f"📅 注册天数 - {code_summary['days']} 天"
        )
    else:
        source_text = "🎫 注册码 - 未找到最近兑换记录"

    result = await sendMessage(
        status_message,
        f"✅ 注册成功 - [{user_id}](tg://user?id={user_id}) 创建了 `{username}`\n"
        f"{source_text}\n"
        f"⏰ 到期时间 - {expires_text}",
        send=True,
        chat_id=group,
    )
    if isinstance(result, str):
        LOGGER.warning(f"【注册成功播报】发送失败 user={user_id} username={username}: {result}")


# 创号函数
async def create_user(_, call, us, stats):
    msg = await ask_return(call,
                           text='🤖**哼...既然你要注册，本女仆勉为其难告诉你规则：\n\n• 请在2min内输入 `[用户名][空格][安全码]`\n• 举个例子🌰：`苏苏 1234`**\n\n• 用户名中不限制中/英文/emoji，🚫**特殊字符**'
                                '\n• 安全码为敏感操作时附加验证，请填入最熟悉的数字4~6位；退出请点 /cancel', timer=120,
                           button=close_it_ikb)
    if not msg:
        return

    elif msg.text == '/cancel':
        return await asyncio.gather(msg.delete(), bot.delete_messages(msg.from_user.id, msg.id - 1))

    try:
        emby_name, emby_pwd2 = msg.text.split()
    except (IndexError, ValueError):
        await msg.reply(f'⚠️ 格式错了啦！才不是本女仆的问题...\n\n输入内容\n **真是的，会话结束！**')
    else:
        send = await msg.reply(
            f'🆗 会话结束，收到设置\n\n用户名：**{emby_name}** 安全码已接收\n\n__正在接入注册队列__......'
        )

        async def _run_create_job():
            await _perform_create_user(
                status_message=send,
                user_id=call.from_user.id,
                username=emby_name,
                security_code=emby_pwd2,
                days=us,
                open_register=stats,
            )

        enqueue_result = await register_create_queue.submit(call.from_user.id, _run_create_job)
        if enqueue_result.duplicate:
            await editMessage(
                send,
                f'⏳ 你已经在注册队列中啦。\n\n'
                f'· 用户名 | `{emby_name}`\n'
                f'· 安全码 | 已接收\n'
                f'· 前方任务 | `{enqueue_result.ahead}` 个\n\n'
                f'轮到你后会自动继续。',
                re_create_ikb,
            )
            return

        if not enqueue_result.accepted:
            await editMessage(
                send,
                f'⏳ 当前注册请求过多，队列已满。\n\n'
                f'· 队列容量 | `{enqueue_result.capacity}`\n'
                f'· 当前积压 | `{enqueue_result.ahead}` 个以上\n\n'
                f'请稍后再试。',
                re_create_ikb,
            )
            return

        if enqueue_result.ahead > 0:
            await editMessage(
                send,
                f'⏳ 当前注册请求较多，你已进入排队队列。\n\n'
                f'· 用户名 | `{emby_name}`\n'
                f'· 安全码 | 已接收\n'
                f'· 前方任务 | `{enqueue_result.ahead}` 个\n\n'
                f'轮到你后会自动继续创建账号，请不要重复点击。',
            )
            return

        await editMessage(
            send,
            f'🪄 已接收注册请求。\n\n'
            f'· 用户名 | `{emby_name}`\n'
            f'· 安全码 | 已接收\n\n'
            f'__正在为您初始化账户，更新用户策略__......'
        )


async def _perform_create_user(status_message, user_id: int, username: str, security_code: str, days: int, open_register: bool):
    # Registration capacity, remote creation, and local binding are one
    # serialized critical section.  This avoids two queue workers observing
    # the same free slot and creating more accounts than configured.
    async with _REGISTRATION_CAPACITY_LOCK:
        return await _perform_create_user_locked(
            status_message, user_id, username, security_code, days, open_register
        )


async def _perform_create_user_locked(status_message, user_id: int, username: str, security_code: str, days: int, open_register: bool):
    current_user = sql_get_emby(tg=user_id)
    if not current_user:
        await editMessage(status_message, '⚠️ 数据库里找不到你呢...才、才不是本女仆把你弄丢的！请重新 /start 录入啦。', re_create_ikb)
        return

    if current_user.embyid:
        await editMessage(status_message, '💦 哼，不是已经有账户了嘛...别、别贪心啦！', back_members_ikb)
        return

    current_registered = int(refresh_registration_slots() or 0)
    if current_registered >= _open.all_user:
        await editMessage(
            status_message,
            f'**🚫 注、注册满了啦...({current_registered}/{_open.all_user})。这不是本女仆的错！等主人加位置吧。**',
            back_members_ikb,
        )
        return

    if not open_register and int(current_user.us or 0) <= 0:
        await editMessage(status_message, '⚠️ 你的注册资格已失效，请重新获取后再试。', back_members_ikb)
        return

    await editMessage(
        status_message,
        f'🪄 已轮到你，开始创建账号。\n\n'
        f'· 用户名 | `{username}`\n'
        f'· 安全码 | 已接收\n\n'
        f'__正在为您初始化账户，更新用户策略__......'
    )

    data = await emby.emby_create(name=username, days=days, tg_id=user_id)
    if not data:
        await editMessage(
            status_message,
            '**- ❎ 已有此账户名，请重新输入注册\n- ❎ 或检查有无特殊字符\n- ❎ 或emby服务器连接不通，会话已结束！**',
            re_create_ikb,
        )
        LOGGER.error(f"【创建账户】：user={user_id} 用户名={username} 创建失败")
        return

    password = data[1]
    emby_id = data[0]
    expires_at = data[2]

    binding_changes = {
        "embyid": emby_id,
        "name": username,
        "pwd": password,
        "pwd2": security_code,
        "lv": "b",
        "cr": datetime.now(),
        "ex": expires_at,
    }
    if not open_register:
        binding_changes["us"] = 0
    if not sql_update_emby(Emby.tg == user_id, **binding_changes):
        LOGGER.error(f"【创建账户】远端账号已创建但本地绑定失败 user={user_id} emby_id={emby_id}")
        try:
            await emby.emby_del(emby_id)
        except Exception as cleanup_error:
            LOGGER.error(f"【创建账户】清理孤儿 Emby 账号失败 user={user_id}: {cleanup_error}")
        await editMessage(
            status_message,
            '⚠️ 远端账号创建成功，但本地绑定失败。系统已尝试回滚，请联系管理员确认状态。',
            re_create_ikb,
        )
        return

    tem_adduser()

    if schedall.check_ex:
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S")
    elif schedall.low_activity:
        expires_text = f'__若{config.activity_check_days}天无观看将封禁__'
    else:
        expires_text = '__无需保号，放心食用__'

    await editMessage(
        status_message,
        f'**▎哼，才不是特别为你创建的呢...其实是成功啦！🎉**\n\n'
        f'· 用户名称 | `{username}`\n'
        f'· 用户密码 | 已安全保存，请通过 Emby 客户端或管理员重置\n'
        f'· 安全密码 | 已接收（仅发送一次）\n'
        f'· 到期时间 | `{expires_text}`\n'
        f'· 当前线路：\n'
        f'{emby_line}\n\n'
        f'**·【服务器】 - 查看线路和密码**'
    )

    if open_register:
        LOGGER.info(f"【创建账户】[开注状态]：{user_id} - 建立了 {username} ")
    else:
        await _broadcast_register_create_success(status_message, user_id, username, expires_text)
        LOGGER.info(f"【创建账户】：{user_id} - 建立了 {username} ")


# 键盘中转
@bot.on_callback_query(filters.regex('members'))
async def members(_, call):
    data = await members_info(tg=call.from_user.id)
    if not data:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)
    await callAnswer(call, f"✅ 用户界面")
    name, lv, ex, us, embyid, pwd2 = data
    expires_text = _emby_expiry_display(lv, ex)
    text = f"▎__哼...又来看面板了？{call.from_user.first_name}？才、才没说不让你看呢。__\n\n" \
           f"**· 🆔 用户のID** | `{call.from_user.id}`\n" \
           f"**· 📊 当前状态** | {lv}\n" \
           f"**· 🍒 积分{sakura_b}** | {us}\n" \
           f"**· 💠 账号名称** | [{name}](tg://user?id={call.from_user.id})\n" \
           f"**· 🚨 到期时间** | {expires_text}"
    if not embyid:
        is_admin = judge_admins(call.from_user.id)
        await editMessage(call, text, members_ikb(is_admin, False))
    else:
        await editMessage(call, text, members_ikb(account=True))


# 创建账户
@bot.on_callback_query(filters.regex('create') & user_in_group_on_filter)
async def create(_, call):
    """

    当队列已满时，用户会收到等待提示。
    信号量和计数器正确释放。
    代码保存至收藏夹，改版时勿忘加入排队机制
    :param _:
    :param call:
    :return:
    """
    e = sql_get_emby(tg=call.from_user.id)
    if not e:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)

    if e.embyid:
        await callAnswer(call, '💦 你已经有账户啦！请勿重复注册。', True)
    elif not _open.stat and int(e.us) <= 0:
        await callAnswer(call, f'🤖 自助注册已关闭，等待开启或使用注册码注册。', True)
    elif not _open.stat and int(e.us) > 0:
        send = await callAnswer(call, f'🪙 资质核验成功，请稍后。', True)
        if send is False:
            return
        else:
            await create_user(_, call, us=e.us, stats=False)
    elif _open.stat:
        send = await callAnswer(call, f"🪙 开放注册中，免除资质核验。", True)
        if send is False:
            return
        else:
            await create_user(_, call, us=_open.open_us, stats=True)


# 换绑tg
@bot.on_callback_query(filters.regex('changetg') & user_in_group_on_filter)
async def change_tg(_, call):
    try:
        status, current_id_str, replace_id_str = call.data.split('_')
        if not judge_admins(call.from_user.id): return await callAnswer(call, '⚠️ 你什么档次？', True)
        current_id = int(current_id_str)
        replace_id = int(replace_id_str)
        if status == 'nochangetg':
            return await asyncio.gather(
                editMessage(call,
                            f' ❎ 好的，[您](tg://user?id={call.from_user.id})已拒绝[{current_id}](tg://user?id={current_id})的换绑请求，原TG：`{replace_id}`。'),
                bot.send_message(current_id, '❌ 您的换绑请求已被拒。请在群组中详细说明情况。'))

        await editMessage(call,
                          f' ✅ 好的，[您](tg://user?id={call.from_user.id})已通过[{current_id}](tg://user?id={current_id})的换绑请求，原TG：`{replace_id}`。')
        e = sql_get_emby(tg=replace_id)
        if not e or not e.embyid: return await bot.send_message(current_id, '⁉️ 出错了，您所换绑账户已不存在。')

        # 清空原账号信息但保留tg
        if sql_update_emby(Emby.tg == replace_id, embyid=None, name=None, pwd=None, pwd2=None,
                          lv='d', cr=None, ex=None, us=0, iv=0, ch=None):
            LOGGER.info(f'【TG改绑】清空原账户 id{e.tg} 成功')
        else:
            await bot.send_message(current_id, "🍰 **⭕#TG改绑 原账户清空错误，请联系闺蜜（管理）！**")
            LOGGER.error(f"【TG改绑】清空原账户 id{e.tg} 失败, Emby:{e.name}未转移...")
            return

        # 将原账号的币值转移到新账号
        old_iv = e.iv
        if sql_update_emby(Emby.tg == current_id, embyid=e.embyid, name=e.name, pwd=e.pwd, pwd2=e.pwd2,
                           lv=e.lv, cr=e.cr, ex=e.ex, iv=old_iv):
            expires_text = _emby_expiry_display(e.lv, e.ex)
            text = f'⭕ 请接收您的信息！\n\n' \
                   f'· 用户名称 | `{e.name}`\n' \
                   f'· 用户密码 | 已安全保存，请通过 Emby 客户端或管理员重置\n' \
                   f'· 安全密码 | 已更新\n' \
                   f'· 到期时间 | `{expires_text}`\n\n' \
                   f'· 当前线路：\n{emby_line}\n\n' \
                   f'**·在【服务器】按钮 - 查看线路和密码**'
            await bot.send_message(current_id, text)
            LOGGER.info(
                f'【TG改绑】 emby账户 {e.name} 绑定至 {current_id}')
        else:
            await bot.send_message(current_id, '🍰 **【TG改绑】数据库处理出错，请联系闺蜜（管理）！**')
            LOGGER.error(f"【TG改绑】 emby账户{e.name} 绑定未知错误。")
        return
    except (IndexError, ValueError):
        pass
    d = sql_get_emby(tg=call.from_user.id)
    if not d:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)
    if d.embyid:
        return await callAnswer(call, '⚖️ 您已经拥有账户，请不要钻空子', True)

    await callAnswer(call, '⚖️ 更换绑定的TG')
    send = await editMessage(call,
                             '🔰 **【更换绑定emby的tg】**\n'
                             '须知：\n'
                             '- **请确保您之前用其他tg账户注册过**\n'
                             '- **请确保您注册的其他tg账户呈已注销状态**\n'
                             '- **请确保输入正确的emby用户名，安全码/密码**\n\n'
                             '您有120s回复 `[emby用户名] [安全码/密码]`\n例如 `苏苏 5210` ，若密码为空则填写"None"，退出点 /cancel')
    if send is False:
        return

    m = await callListen(call, 120, buttons=back_members_ikb)
    if m is False:
        return

    elif m.text == '/cancel':
        await m.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！** ✅', back_members_ikb)
    else:
        try:
            await m.delete()
            emby_name, emby_pwd = m.text.split()
        except (IndexError, ValueError):
            return await editMessage(call, f'⚠️ 输入格式错误\n【输入内容】\n **会话已结束！**', re_changetg_ikb)

        e = sql_get_emby(tg=emby_name)
        if e is None:
            # 在emby2中，验证安全码 或者密码
            e2 = sql_get_emby2(name=emby_name)
            if e2 is None:
                return await editMessage(call, f'❓ 未查询到本女仆数据中名为 {emby_name} 的账户，请使用 **绑定TG** 功能。',
                                         buttons=re_bindtg_ikb)
            if emby_pwd != e2.pwd2:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'💢 安全码or密码验证错误，请检查输入\n请输入正确凭据后重试。',
                                             buttons=re_changetg_ikb)
                sql_update_emby(Emby.tg == call.from_user.id, embyid=embyid, name=e2.name, pwd=emby_pwd,
                                pwd2=e2.pwd2, lv=e2.lv, cr=e2.cr, ex=e2.ex)
                sql_delete_emby2(embyid=e2.embyid)
                expires_text = _emby_expiry_display(e2.lv, e2.ex)
                text = f'⭕ 账户 {emby_name} 的密码验证成功！\n\n' \
                       f'· 用户名称 | `{emby_name}`\n' \
                       f'· 用户密码 | 已安全保存，请通过 Emby 客户端或管理员重置\n' \
                       f'· 安全密码 | 已验证\n' \
                       f'· 到期时间 | `{expires_text}`\n\n' \
                       f'· 当前线路：\n{emby_line}\n\n' \
                       f'**·在【服务器】按钮 - 查看线路和密码**'
                await sendMessage(call,
                                  f'⭕#TG改绑 原emby账户 #{emby_name}\n\n'
                                  f'从emby2表绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                  send=True)
                LOGGER.info(f'【TG改绑】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
                await editMessage(call, text)

            elif emby_pwd == e2.pwd2:
                expires_text = _emby_expiry_display(e2.lv, e2.ex)
                text = f'⭕ 账户 {emby_name} 的安全码验证成功！\n\n' \
                       f'· 用户名称 | `{emby_name}`\n' \
                       f'· 用户密码 | 已安全保存，请通过 Emby 客户端或管理员重置\n' \
                       f'· 安全密码 | 已更新\n' \
                       f'· 到期时间 | `{expires_text}`\n\n' \
                       f'· 当前线路：\n{emby_line}\n\n' \
                       f'**·在【服务器】按钮 - 查看线路和密码**'
                sql_update_emby(Emby.tg == call.from_user.id, embyid=e2.embyid, name=e2.name, pwd=e2.pwd,
                                pwd2=emby_pwd, lv=e2.lv, cr=e2.cr, ex=e2.ex)
                sql_delete_emby2(embyid=e2.embyid)
                await sendMessage(call,
                                  f'⭕#TG改绑 原emby账户 #{emby_name}\n\n'
                                  f'从emby2表绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                  send=True)
                LOGGER.info(f'【TG改绑】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
                await editMessage(call, text)

        else:
            if call.from_user.id == e.tg: return await editMessage(call, '⚠️ 您已经拥有账户。')
            if emby_pwd != e.pwd2:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'💢 安全码or密码验证错误，请检查输入\n请输入正确凭据后重试。',
                                             buttons=re_changetg_ikb)
            await  asyncio.gather(editMessage(call,
                                              f'✔️ 会话结束，验证成功\n\n'
                                              f'🔰 用户名：**{emby_name}** 安全码/密码已验证......\n\n'
                                              f'🎯 已向授权群发送申请，请联系并等待主人确认......'),
                                  sendMessage(call,
                                              f'⭕#TG改绑\n'
                                              f'**用户 [{call.from_user.id}](tg://user?id={call.from_user.id}) 正在试图改绑Emby: [{e.name}](tg://user?id={e.tg})，原TG: `{e.tg}`，已通过安全/密码核验\n\n'
                                              f'请主人审核决定：**',
                                              buttons=send_changetg_ikb(call.from_user.id, e.tg),
                                              send=True))
            LOGGER.info(
                f'【TG改绑】 {call.from_user.first_name}-{call.from_user.id} 通过验证账户，已递交对Emby: {emby_name}, Tg:{e.tg} 的换绑申请')


@bot.on_callback_query(filters.regex('bindtg') & user_in_group_on_filter)
async def bind_tg(_, call):
    d = sql_get_emby(tg=call.from_user.id)
    if d is not None and d.embyid is not None:
        return await callAnswer(call, '⚖️ 您已经拥有账户，请不要钻空子', True)
    await callAnswer(call, '⚖️ 将账户绑定TG')
    send = await editMessage(call,
                             '🔰 **【已有emby绑定至tg】**\n'
                             '须知：\n'
                             '- **请确保您需绑定的账户不在本女仆中**\n'
                             '- **请确保您不是恶意绑定他人的账户**\n'
                             '- **请确保输入正确的emby用户名，密码**\n\n'
                             '您有120s回复 `[emby用户名] [密码]`\n例如 `苏苏 5210` ，若密码为空则填写“None”，退出点 /cancel')
    if send is False:
        return

    m = await callListen(call, 120, buttons=back_members_ikb)
    if m is False:
        return

    elif m.text == '/cancel':
        await m.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！** ✅', back_members_ikb)
    else:
        try:
            await m.delete()
            emby_name, emby_pwd = m.text.split()
        except (IndexError, ValueError):
            return await editMessage(call, f'⚠️ 输入格式错误\n【输入内容】\n **会话已结束！**', re_bindtg_ikb)
        await editMessage(call,
                          f'✔️ 会话结束，收到设置\n\n用户名：**{emby_name}** 正在验证密码......')
        e = sql_get_emby(tg=emby_name)
        if e is None:
            e2 = sql_get_emby2(name=emby_name)
            if e2 is None:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             '🍥 很遗憾绑定失败，账户密码验证不通过，请仔细确认后再次尝试',
                                             buttons=re_bindtg_ikb)
                else:
                    security_pwd = await pwd_create(4)
                    pwd = ['空（直接回车）', security_pwd] if emby_pwd == 'None' else [emby_pwd, emby_pwd]
                    ex = (datetime.now() + timedelta(days=30))
                    text = f'✅ 账户 {emby_name} 成功绑定\n\n' \
                           f'· 用户名称 | `{emby_name}`\n' \
                           f'· 用户密码 | 已安全保存，请通过 Emby 客户端或管理员重置\n' \
                           f'· 安全密码 | 已更新\n' \
                           f'· 到期时间 | `{ex}`\n\n' \
                           f'· 当前线路：\n{emby_line}\n\n' \
                           f'· **在【服务器】按钮 - 查看线路和密码**'
                    sql_update_emby(Emby.tg == call.from_user.id, embyid=embyid, name=emby_name, pwd=pwd[0],
                                    pwd2=pwd[1], lv='b', cr=datetime.now(), ex=ex)
                    await editMessage(call, text)
                    await sendMessage(call,
                                      f'⭕#新TG绑定 原emby账户 #{emby_name} \n\n已绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                      send=True)
                    LOGGER.info(
                        f'【新TG绑定】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
            else:
                await editMessage(call, '🔍 数据库已有此账户，不可绑定，请使用 **换绑TG**', buttons=re_changetg_ikb)
        else:
            await editMessage(call, '🔍 数据库已有此账户，不可绑定，请使用 **换绑TG**', buttons=re_changetg_ikb)


# kill yourself
@bot.on_callback_query(filters.regex('delme'))
async def del_me(_, call):
    e = sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)
    else:
        if e.embyid is None:
            return await callAnswer(call, '未查询到账户，不许乱点！💢', True)
        await callAnswer(call, "🔴 请先进行 安全码 验证")
        edt = await editMessage(call, '**🔰账户安全验证**：\n\n👮🏻验证是否本人进行敏感操作，请对我发送您设置的安全码。倒计时 120s\n'
                                      '🛑 **停止请点 /cancel**')
        if edt is False:
            return

        m = await callListen(call, 120)
        if m is False:
            return

        elif m.text == '/cancel':
            await m.delete()
            await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        else:
            if m.text == e.pwd2:
                await m.delete()
                await editMessage(call, '**⚠️ 哼...真的要删吗？到期的话本女仆会帮你封存的。但删了的话，就、就真的什么都没有了...才不是舍不得你呢。\n**',
                                  buttons=del_me_ikb(e.embyid))
            else:
                await m.delete()
                await editMessage(call, '**💢 验证不通过，安全码错误。**', re_delme_ikb)


@bot.on_callback_query(filters.regex('delemby'))
async def del_emby(_, call):
    send = await callAnswer(call, "🎯 get，正在删除ing。。。")
    if send is False:
        return

    embyid = call.data.split('-')[1]
    if await emby.emby_del(emby_id=embyid):
        sql_update_emby(Emby.embyid == embyid, embyid=None, name=None, pwd=None, pwd2=None, lv='d', cr=None, ex=None)
        tem_deluser()
        send1 = await editMessage(call, '🗑️ 好了，已经为您删除...\n愿来日各自安好，山高水长，我们有缘再见！',
                                  buttons=back_members_ikb)
        if send1 is False:
            return

        LOGGER.info(f"【删除账号】：{call.from_user.id} 已删除！")
    else:
        await editMessage(call, '🥧 蛋糕辣~ 好像哪里出问题了，请向管理反应', buttons=back_members_ikb)
        LOGGER.error(f"【删除账号】：{call.from_user.id} 失败！")


# 重置密码为空密码
@bot.on_callback_query(filters.regex('reset'))
async def reset(_, call):
    e = sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)
    if e.embyid is None:
        return await bot.answer_callback_query(call.id, '未查询到账户，不许乱点！💢', show_alert=True)
    else:
        await callAnswer(call, "🔴 请先进行 安全码 验证")
        send = await editMessage(call, '**🔰账户安全验证**：\n\n 👮🏻验证是否本人进行敏感操作，请对我发送您设置的安全码。倒计时 120 s\n'
                                       '🛑 **停止请点 /cancel**')
        if send is False:
            return

        m = await callListen(call, 120, buttons=back_members_ikb)
        if m is False:
            return

        elif m.text == '/cancel':
            await m.delete()
            await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        else:
            if m.text != e.pwd2:
                await m.delete()
                await editMessage(call, f'**💢 验证不通过，安全码错误。**', buttons=re_reset_ikb)
            else:
                await m.delete()
                await editMessage(call, '🎯 请在 120s内 输入你要更新的密码,不限制中英文，emoji。特殊字符部分支持，其他概不负责。\n\n'
                                        '点击 /cancel 将重置为空密码并退出。 无更改退出状态请等待120s')
                mima = await callListen(call, 120, buttons=back_members_ikb)
                if mima is False:
                    return

                elif mima.text == '/cancel':
                    await mima.delete()
                    await editMessage(call, '**🎯 收到，正在重置ing。。。**')
                    if await emby.emby_reset(emby_id=e.embyid) is True:
                        await editMessage(call, '🕶️ 操作完成！已为您重置密码为 空。', buttons=back_members_ikb)
                        LOGGER.info(f"【重置密码】：{call.from_user.id} 成功重置了空密码！")
                    else:
                        await editMessage(call, '🫥 重置密码操作失败！请联系主人。')
                        LOGGER.error(f"【重置密码】：{call.from_user.id} 重置密码失败 ！")

                else:
                    await mima.delete()
                    await editMessage(call, '**🎯 收到，正在重置ing。。。**')
                    if await emby.emby_reset(emby_id=e.embyid, new_password=mima.text) is True:
                        await editMessage(call, f'🕶️ 操作完成！已为您重置密码已更新，请通过 Emby 客户端或管理员重置。',
                                          buttons=back_members_ikb)
                        LOGGER.info(f"【重置密码】：{call.from_user.id} 成功重置了密码更新成功！")
                    else:
                        await editMessage(call, '🫥 操作失败！请联系主人。', buttons=back_members_ikb)
                        LOGGER.error(f"【重置密码】：{call.from_user.id} 重置密码失败 ！")


@bot.on_callback_query(filters.regex('^change_pwd2$'))
async def change_pwd2(_, call):
    e = sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)
    if e.embyid is None:
        return await bot.answer_callback_query(call.id, '未查询到账户，不许乱点！💢', show_alert=True)

    change_cost = max(0, int(getattr(_open, 'change_pwd2_cost', 0) or 0))
    if e.iv < change_cost:
        return await bot.answer_callback_query(
            call.id,
            f'❌ 当前更换安全码需要 {change_cost}{sakura_b}，而您只有 {e.iv}{sakura_b}',
            show_alert=True
        )

    await callAnswer(call, "🔴 请先进行 安全码 验证")
    send = await editMessage(
        call,
        f'**🔰安全码更换**：\n\n'
        f'👮🏻 请先发送当前安全码进行验证。\n'
        f'💰 本次操作将扣除 `{change_cost}` {sakura_b}\n'
        f'🛑 **停止请点 /cancel**',
        buttons=back_members_ikb
    )
    if send is False:
        return

    old_code_message = await callListen(call, 120, buttons=back_members_ikb)
    if old_code_message is False:
        return

    if old_code_message.text == '/cancel':
        await old_code_message.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        return

    if old_code_message.text != e.pwd2:
        await old_code_message.delete()
        await editMessage(call, f'**💢 验证不通过，安全码错误。**', buttons=re_change_pwd2_ikb)
        return

    await old_code_message.delete()
    await editMessage(
        call,
        f'🎯 请在 120s 内输入新的安全码\n\n'
        f'· 仅支持 **4 到 6 位数字**\n'
        f'· 本次操作将扣除 `{change_cost}` {sakura_b}\n'
        f'· 发送 /cancel 可取消，本次不会扣费',
        buttons=back_members_ikb
    )

    new_code_message = await callListen(call, 120, buttons=back_members_ikb)
    if new_code_message is False:
        return

    if new_code_message.text == '/cancel':
        await new_code_message.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        return

    new_code = (new_code_message.text or "").strip()
    await new_code_message.delete()

    if not _is_valid_security_code(new_code):
        await editMessage(
            call,
            f'**💢 新安全码格式错误。**\n\n'
            f'您输入的安全码格式不正确。\n'
            f'请使用 **4 到 6 位数字**。',
            buttons=re_change_pwd2_ikb
        )
        return

    current_user = sql_get_emby(tg=call.from_user.id)
    if current_user is None or current_user.embyid is None:
        await editMessage(call, '🫥 未找到当前账户信息，请重新 /start 后再试。', buttons=back_members_ikb)
        return

    if new_code == (current_user.pwd2 or ""):
        await editMessage(call, '🫥 新安全码不能和当前安全码相同。', buttons=re_change_pwd2_ikb)
        return

    if current_user.iv < change_cost:
        await editMessage(
            call,
            f'🫥 当前余额不足，无法完成更换。\n\n需要 {change_cost}{sakura_b}，当前只有 {current_user.iv}{sakura_b}。',
            buttons=back_members_ikb
        )
        return

    remaining_iv = current_user.iv - change_cost
    if sql_update_emby(Emby.tg == call.from_user.id, pwd2=new_code, iv=remaining_iv, ch=datetime.now()):
        await editMessage(
            call,
            f'🕶️ 操作完成！安全码已更新。\n'
            f'本次扣除 `{change_cost}` {sakura_b}，剩余 `{remaining_iv}` {sakura_b}。',
            buttons=back_members_ikb
        )
        LOGGER.info(
            f"【更换安全码】：{call.from_user.id} 成功更新安全码，扣除 {change_cost}{sakura_b}，剩余 {remaining_iv}{sakura_b}"
        )
    else:
        await editMessage(call, '🫥 更换安全码失败！请联系主人。', buttons=back_members_ikb)
        LOGGER.error(f"【更换安全码】：{call.from_user.id} 更新安全码失败")


# 显示/隐藏某些库
@bot.on_callback_query(filters.regex('embyblock'))
async def embyblocks(_, call):
    data = sql_get_emby(tg=call.from_user.id)
    if not data:
        return await callAnswer(call, '⚠️ 找不到你...才、才不是本女仆忘了！重新 /start 一下啦。', True)
    if data.embyid is None:
        return await callAnswer(call, '❓ 未查询到账户，不许乱点!', True)
    elif data.lv == "c":
        return await callAnswer(call, '💢 账户到期，封禁中无法使用！', True)
    elif len(config.emby_block) == 0:
        send = await editMessage(call, '⭕ 主人未设置。。。 快催催\no(*////▽////*)q', buttons=back_members_ikb)
        if send is False:
            return
    else:
        success, rep = await emby.user(emby_id=data.embyid)
        try:
            if success is False:
                stat = '💨 未知'
            else:
                # 新版本使用 EnabledFolders 和 EnableAllFolders 控制访问
                policy = rep.get("Policy", {})
                enable_all_folders = policy.get("EnableAllFolders")
                enabled_folders = policy.get("EnabledFolders", [])

                if enable_all_folders:
                    # 如果启用所有文件夹，检查是否有特定的阻止设置
                    stat = '🟢 显示'
                else:
                    # 检查目标媒体库是否在启用列表中
                    # 需要获取媒体库ID来进行比较
                    target_folder_ids = await emby.get_folder_ids_by_names(config.emby_block)
                    if target_folder_ids and any(folder_id in enabled_folders for folder_id in target_folder_ids):
                        stat = '🟢 显示'
                    else:
                        stat = '🔴 隐藏'
        except KeyError:
            stat = '💨 未知'
        block = ", ".join(config.emby_block)
        await asyncio.gather(callAnswer(call, "✅ 到位"),
                             editMessage(call,
                                         f'🤺 用户状态：{stat}\n🎬 目前设定的库为: \n\n**{block}**\n\n请选择你的操作。',
                                         buttons=emby_block_ikb(data.embyid)))


# 隐藏
@bot.on_callback_query(filters.regex('emby_block'))
async def user_emby_block(_, call):
    embyid = call.data.split('-')[1]
    send = await callAnswer(call, f'🎬 正在为您关闭显示ing')
    if send is False:
        return
    success, rep = await emby.user(emby_id=embyid)
    if success:
        try:
            # 使用封装的隐藏媒体库方法
            re = await emby.hide_folders_by_names(embyid, config.emby_block)
            if re is True:
                send1 = await editMessage(call, f'🕶️ ο(=•ω＜=)ρ⌒☆\n 小尾巴隐藏好了！ ', buttons=user_emby_block_ikb)
                if send1 is False:
                    return
            else:
                await editMessage(call, f'🕶️ Error!\n 隐藏失败，请上报管理检查)', buttons=back_members_ikb)
        except Exception as e:
            LOGGER.error(f"隐藏媒体库失败: {str(e)}")
            await editMessage(call, f'🕶️ Error!\n 隐藏失败，请上报管理检查)', buttons=back_members_ikb)


# 显示
@bot.on_callback_query(filters.regex('emby_unblock'))
async def user_emby_unblock(_, call):
    embyid = call.data.split('-')[1]
    send = await callAnswer(call, f'🎬 正在为您开启显示ing')
    if send is False:
        return
    success, rep = await emby.user(emby_id=embyid)
    if success:
        try:
            # 使用封装的显示媒体库方法
            re = await emby.show_folders_by_names(embyid, config.emby_block)
            if re is True:
                send1 = await editMessage(call, f'🕶️ ο(=•ω＜=)ρ⌒☆\n 小尾巴显示好了！ ', buttons=user_emby_unblock_ikb)
                if send1 is False:
                    return
            else:
                await editMessage(call, f'🕶️ Error!\n 显示失败，请上报管理检查设置', buttons=back_members_ikb)
        except Exception as e:
            LOGGER.error(f"显示媒体库失败: {str(e)}")
            await editMessage(call, f'🕶️ Error!\n 显示失败，请上报管理检查设置', buttons=back_members_ikb)


@bot.on_callback_query(filters.regex('exchange') & user_in_group_on_filter)
async def call_exchange(_, call):
    await asyncio.gather(callAnswer(call, '🔋 使用注册/续期码'), deleteMessage(call))
    msg = await ask_return(call, text='🔋 **【使用注册/续期码】**：\n\n'
                                      f'- 请在120s内对我发送你的注册/续期码，形如\n`{ranks.logo}-xx-xxxx`\n退出点 /cancel',
                           button=re_exchange_b_ikb)
    if not msg:
        return
    elif msg.text == '/cancel':
        await asyncio.gather(msg.delete(), p_start(_, msg))
    else:
        await rgs_code(_, msg, register_code=msg.text)


@bot.on_callback_query(filters.regex('partitioncode') & user_in_group_on_filter)
async def call_partition_code(_, call):
    await asyncio.gather(callAnswer(call, '🎟️ 使用分区码'), deleteMessage(call))
    msg = await ask_return(call, text='🎟️ **【使用分区码】**：\n\n- 请在120s内发送分区码\n- 退出点 /cancel',
                           button=re_exchange_b_ikb)
    if not msg:
        return
    if msg.text == '/cancel':
        await asyncio.gather(msg.delete(), p_start(_, msg))
        return

    ok, text = await _redeem_partition_code(msg.text.strip(), call.from_user.id)
    await asyncio.gather(msg.delete(), sendMessage(call, text, timer=120 if ok else 60))


@bot.on_callback_query(filters.regex('storeall'))
async def do_store(_, call):
    await asyncio.gather(callAnswer(call, '✔️ 欢迎进入兑换商店'),
                         editMessage(call,
                                     f'**🏪 请选择想要使用的服务：**\n\n🤖 自动{sakura_b}续期状态：{_open.exchange} {_open.exchange_cost}/月',
                                     buttons=store_ikb()))


@bot.on_callback_query(filters.regex('store-reborn'))
async def do_store_reborn(_, call):
    e = sql_get_emby(tg=call.from_user.id)
    if not e:
        return
    if not e.embyid or not e.name:
        return await callAnswer(call, '❌ 未查询到账户，不许乱点！', True)
    await callAnswer(call,
                     '✔️ 请仔细阅读：\n\n本功能仅为 因未活跃而被封禁的用户解封使用，到期状态下封禁的账户请勿使用，以免浪费积分。',
                     True)
    if all([e.lv == 'c', e.iv >= _open.exchange_cost, schedall.low_activity]):
        await editMessage(call,
                          f'🏪 您已满足基础要求，此次将花费 {_open.exchange_cost}{sakura_b} 解除未活跃的封禁，确认请回复 /ok，退出 /cancel')
        m = await callListen(call, 120, buttons=re_born_ikb)
        if m is False:
            return

        elif m.text == '/cancel':
            await asyncio.gather(m.delete(), do_store(_, call))
        else:
            sql_update_emby(Emby.tg == call.from_user.id, iv=e.iv - _open.exchange_cost, lv='b')
            await emby.emby_change_policy(emby_id=e.embyid)
            LOGGER.info(f'【兑换解封】- {call.from_user.id} 已花费 {_open.exchange_cost}{sakura_b},解除封禁')
            await asyncio.gather(m.delete(), do_store(_, call),
                                 sendMessage(call, '解封成功<(￣︶￣)↗[GO!]\n此消息将在20s后自焚', timer=20))
    else:
        await sendMessage(call, '❌ 不满足以下要求！ヘ(￣ω￣ヘ)\n\n'
                                '1. 被封禁账户\n'
                                f'2. 至少持有 {_open.exchange_cost}{sakura_b}\n'
                                f'3. 【定时策略】活跃检测开启\n'
                                f'此消息将在20s后自焚', timer=20)


@bot.on_callback_query(filters.regex('store-whitelist'))
async def do_store_whitelist(_, call):
    if _open.whitelist:
        e = sql_get_emby(tg=call.from_user.id)
        if e is None:
            return
        if not e.embyid or not e.name:
            return await callAnswer(call, '❌ 未查询到账户，不许乱点！', True)
        if e.iv < _open.whitelist_cost or e.lv == 'a':
            return await callAnswer(call,
                                    f'🏪 兑换规则：\n主人~当前兑换白名单需要 {_open.whitelist_cost} {sakura_b}哦~\n已经有白名单的小宝贝就不能再兑换啦，乖乖~',
                                    True)
        await callAnswer(call, f'🌸 主人~您已满足 {_open.whitelist_cost} {sakura_b}要求，正在为您晋升白名单！', True)
        sql_update_emby(Emby.tg == call.from_user.id, lv='a', iv=e.iv - _open.whitelist_cost)
        send = await call.message.edit(f'**{random.choice(Yulv.load_yulv().wh_msg)}**\n\n'
                                       f'🎊 恭喜小宝贝 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) ~ 今日成功晋升为 {ranks["logo"]}白名单 啦！\n主人对您今日的表现非常满意，继续加油哦~ 🌟')
        await send.forward(group[0])
        LOGGER.info(f'【兑换白名单】- {call.from_user.id} 已花费 9999{sakura_b}，晋升白名单')
    else:
        await callAnswer(call, '❌ 主人未开启此兑换', True)


@bot.on_callback_query(filters.regex('store-invite'))
async def do_store_invite(_, call):
    if _open.invite:
        e = sql_get_emby(tg=call.from_user.id)
        if not e:
            return
        # 用户等级为 a（白名单） b(普通用户) c(已禁用) d（未注册用户）
        # 比如当 _open.invite_lv 设置为 d 时，用户等级为 小于等于d 的用户可以兑换，否则无法兑换
        if not lv_allowed(e.lv, _open.invite_lv):
            return await callAnswer(call, '❌ 账号等级不足，无法兑换', True)
        if e.iv < _open.invite_cost:
            return await callAnswer(call,
                                    f'🏪 兑换规则：\n当前兑换注册码至少需要 {_open.invite_cost} {sakura_b}。你的账户只有 {e.iv} {sakura_b}，勉励',
                                    True)
        await editMessage(call,
                          f'🎟️ 请回复创建 [类型] [数量] [模式]\n\n'
                          f'**类型**：月mon，季sea，半年half，年year\n'
                          f'**模式**： link -深链接 | code -码\n'
                          # f'**续期**： F - 注册码，T - 续期码\n'
                          f'**示例**：`mon 1 link` 记作 1条 月度注册链接 \n'
                          f'**示例**：`sea 1 code` 记作 1条 季度注册码\n'
                          f'**注意**：兑率 30天 = {_open.invite_cost}{sakura_b}\n'
                          f'__取消本次操作，请 /cancel__')
        content = await callListen(call, 120)
        if content is False:
            return await do_store(_, call)

        elif content.text == '/cancel':
            return await asyncio.gather(content.delete(), do_store(_, call))
        try:
            times, count, method = content.text.split()
            days = getattr(ExDate(), times)
            count = int(count)
            cost = math.floor((days * count / 30) * _open.invite_cost)
            if e.iv < cost:
                return await asyncio.gather(content.delete(),
                                            sendMessage(call,
                                                        f'您只有 {e.iv}{sakura_b}，而您需要花费 {cost}，超前消费是不可取的哦！？',
                                                        timer=10),
                                            do_store(_, call))
            method = getattr(ExDate(), method)
        except (AttributeError, ValueError, IndexError):
            return await asyncio.gather(sendMessage(call, f'⚠️ 检查输入，格式似乎有误\n{content.text}', timer=10),
                                        do_store(_, call),
                                        content.delete())
        else:
            sql_update_emby(Emby.tg == call.from_user.id, iv=e.iv - cost)
            links = await cr_link_one(call.from_user.id, days, count, days, method)
            if links is None:
                return await editMessage(call, '⚠️ 数据库插入失败，请检查数据库')
            links = f"🎯 本女仆已为您生成 **{days}天** 注册码 {count} 个\n\n" + links
            chunks = [links[i:i + 4096] for i in range(0, len(links), 4096)]
            for chunk in chunks:
                await sendMessage(content, chunk)
            LOGGER.info(f"【注册码兑换】：本女仆已为 {content.from_user.id} 兑换了 {count} 个 {days} 天注册码")
    else:
        await callAnswer(call, '❌ 主人未开启此兑换', True)


@bot.on_callback_query(filters.regex('store-query'))
async def do_store_query(_, call):
    a, b = sql_count_c_code(tg_id=call.from_user.id)
    if not a:
        return await callAnswer(call, '❌ 空', True)
    try:
        number = int(call.data.split(':')[1])
    except (IndexError, KeyError, ValueError):
        number = 1
    await callAnswer(call, '📜 正在翻页')
    await editMessage(call, text=a[number - 1], buttons=await store_query_page(b, number))
@bot.on_callback_query(filters.regex('my_devices'))
async def my_devices(_, call):
    get_emby = sql_get_emby(tg=call.from_user.id)
    if get_emby is None:
        return await callAnswer(call, '您还没有Emby账户', True)
    success, result = await emby.get_emby_userip(emby_id=get_emby.embyid)
    if not success or len(result) == 0:
        return await callAnswer(call, '📭 您好像没播放信息吖')
    else:
        await callAnswer(call, '🔍 正在获取您的设备信息')
        device_count = 0
        ip_count = 0
        device_list = []
        ip_list = []
        device_details = ""
        ip_details = ""
        for r in result:
            device, client, ip = r
            # 统计ip
            if ip not in ip_list:
                ip_count += 1
                ip_list.append(ip)
                ip_details += f'{ip_count}: `{ip}`\n'
            # 统计设备并拼接详情
            if device + client not in device_list:
                device_count += 1
                device_list.append(device + client)
                device_details += f'{device_count}: {device} | {client}  \n'
        text = '**🌏 以下为您播放过的设备&ip 共{}个设备，{}个ip：**\n\n'.format(device_count, ip_count) + '**设备:**\n' + device_details + '**IP:**\n'+ ip_details

        # 以\n分割文本，每20条发送一个消息
        messages = text.split('\n')
        # 每20条消息组成一组
        for i in range(0, len(messages), 20):
            chunk = messages[i:i+20]
            chunk_text = '\n'.join(chunk)
            if not chunk_text.strip():
                continue
            await sendMessage(call.message, chunk_text, buttons=close_it_ikb)
