import asyncio
import os
from sys import argv, executable

from pyrogram import filters
from pyrogram.types import Message

from bot import LOGGER, _open, bot, owner, prefixes, sakura_b, save_config, schedall
from bot.func_helper.filters import admins_on_filter, user_in_group_on_filter
from bot.func_helper.fix_bottons import sched_buttons, plays_list_button
from bot.func_helper.msg_utils import callAnswer, editMessage, deleteMessage
from bot.func_helper.scheduler import scheduler
from bot.func_helper.runtime import get_or_create_event_loop
from bot.scheduler import *
from bot.scheduler.auto_update import ensure_auto_update_schedule, run_auto_update


# 初始化命令 开机检查重启
loop = get_or_create_event_loop()
loop.call_later(5, lambda: loop.create_task(BotCommands.set_commands(client=bot)))
loop.call_later(5, lambda: loop.create_task(check_restart()))

# 启动定时任务
auto_backup_db = DbBackupUtils.auto_backup_db
user_plays_rank = Uplaysinfo.user_plays_rank
check_low_activity = Uplaysinfo.check_low_activity

async def user_day_plays(): await user_plays_rank(1)


async def user_week_plays(): await user_plays_rank(7)


# 写优雅点
# 字典，method相应的操作函数
action_dict = {
    "dayrank": day_ranks,
    "weekrank": week_ranks,
    "dayplayrank": user_day_plays,
    "weekplayrank": user_week_plays,
    "check_ex": check_expired,
    "low_activity": check_low_activity,
    "backup_db": auto_backup_db,
    "partition_check": check_partition_access,
}

# 字典，对应的操作函数的参数和id
args_dict = {
    "dayrank": {'hour': 18, 'minute': 30, 'id': 'day_ranks'},
    "weekrank": {'day_of_week': "sun", 'hour': 23, 'minute': 59, 'id': 'week_ranks'},
    "dayplayrank": {'hour': 23, 'minute': 0, 'id': 'user_day_plays'},
    "weekplayrank": {'day_of_week': "sun", 'hour': 23, 'minute': 0, 'id': 'user_week_plays'},
    "check_ex": {'hour': 1, 'minute': 30, 'id': 'check_expired'},
    "low_activity": {'hour': 8, 'minute': 30, 'id': 'check_low_activity'},
    "backup_db": {'hour': 2, 'minute': 30, 'id': 'backup_db'},
    "partition_check": {'minute': '*/10', 'id': 'partition_check'},
}


def set_all_sche():
    for key, value in action_dict.items():
        if getattr(schedall, key):
            action = action_dict[key]
            args = args_dict[key]
            scheduler.add_job(action, 'cron', **args)


set_all_sche()
ensure_auto_update_schedule()


async def sched_panel(_, msg):
    # await deleteMessage(msg)
    await editMessage(msg,
                      text=f'🎮 **管理定时任务面板**\n\n',
                      buttons=sched_buttons())


@bot.on_callback_query(filters.regex('sched') & admins_on_filter)
async def sched_change_policy(_, call):
    try:
        method = call.data.split('-')[1]
        # 根据method的值来添加或移除相应的任务
        action = action_dict[method]
        args = args_dict[method]
        if getattr(schedall, method):
            ok = scheduler.remove_job(job_id=args['id'], jobstore='default')
        else:
            # replace_existing=True：重复添加时直接替换，避免 ConflictingIdError
            ok = scheduler.add_job(action, 'cron', **args, replace_existing=True)
        if not ok:
            LOGGER.error(f"定时任务 {method} 切换失败：add/remove 返回失败")
            await callAnswer(call, f'❌ {method} 更改失败，请查看日志', True)
            return
        # 仅任务切换成功后才更新状态并保存配置，避免配置与调度器不一致
        setattr(schedall, method, not getattr(schedall, method))
        save_config()
        await asyncio.gather(callAnswer(call, f'⭕️ {method} 更改成功'), sched_panel(_, call.message))
    except IndexError:
        await sched_panel(_, call.message)


@bot.on_message(filters.command('check_ex', prefixes) & admins_on_filter)
async def check_ex_admin(_, msg):
    await deleteMessage(msg)
    confirm = False
    try:
        confirm = msg.command[1]
    except:
        pass
    if confirm == 'true':
        send = await msg.reply("🍥 正在运行 【到期检测】。。。")
        await asyncio.gather(check_expired(), send.edit("✅ 【到期检测结束】"))
    else:
        await msg.reply("🔔 请输入 `/check_ex true` 确认运行")


# 本女仆数据库手动备份
@bot.on_message(filters.command('backup_db', prefixes) & filters.user(owner))
async def manual_backup_db(_, msg):
    await asyncio.gather(deleteMessage(msg), auto_backup_db())


@bot.on_message(filters.command('days_ranks', prefixes) & admins_on_filter)
async def day_r_ranks(_, msg):
    await asyncio.gather(msg.delete(), day_ranks(pin_mode=False))


@bot.on_message(filters.command('week_ranks', prefixes) & admins_on_filter)
async def week_r_ranks(_, msg):
    await asyncio.gather(msg.delete(), week_ranks(pin_mode=False))


@bot.on_message(filters.command('low_activity', prefixes) & admins_on_filter)
async def run_low_ac(_, msg):
    await deleteMessage(msg)
    confirm = False
    try:
        confirm = msg.command[1]
    except:
        pass
    if confirm == 'true':
        send = await msg.reply("⭕ 不活跃检测运行ing···")
        await asyncio.gather(check_low_activity(), send.delete())
    else:
        await msg.reply("🔔 请输入 `/low_activity true` 确认运行")

@bot.on_message(filters.command('uranks', prefixes) & admins_on_filter)
async def shou_dong_uplayrank(_, msg):
    await deleteMessage(msg)
    try:
        days = int(msg.command[1])
        await user_plays_rank(days=days, uplays=False)
    except (IndexError, ValueError):
        await msg.reply(
            f"🔔 请输入 `/uranks 天数`，此运行手动不会影响{sakura_b}的结算（仅定时运行时结算），放心使用。\n"
            f"定时结算状态: {_open.uplays}")

@bot.on_message(filters.command('restart', prefixes) & admins_on_filter)
async def restart_bot(_, msg):
    await deleteMessage(msg)
    send = await msg.reply("Restarting，等待几秒钟。")
    schedall.restart_chat_id = send.chat.id
    schedall.restart_msg_id = send.id
    save_config()
    try:
        LOGGER.info("重启")
        service_name = os.getenv("PIVKEYU_RESTART_SERVICE", "").strip()
        if service_name and os.path.exists('/bin/systemctl'):
            os.execl('/bin/systemctl', 'systemctl', 'restart', service_name)
        os.execl(executable, executable, *argv)
    except FileNotFoundError:
        exit(1)


@bot.on_callback_query(filters.regex('uranks') & user_in_group_on_filter)
async def page_uplayrank(_, call):
    j, days = map(int, call.data.split(":")[1].split('_'))
    await callAnswer(call, f'将为您翻到第 {j} 页')
    a, b, c = await Uplaysinfo.users_playback_list(days)
    if not a:
        return await callAnswer(call, f'🍥 获取过去{days}天UserPlays失败了嘤嘤嘤 ~ 手动重试', True)
    button = await plays_list_button(b, j, days)
    text = a[j - 1]
    await editMessage(call, text, buttons=button)

@bot.on_message(filters.command('update_bot', prefixes) & admins_on_filter)
async def get_update_bot(_, msg: Message):
    delete_task = msg.delete()
    send_task = bot.send_message(chat_id=msg.chat.id, text='⏳ 正在检查 GitHub 与 Docker 镜像更新，请稍等。。。')
    results = await asyncio.gather(delete_task, send_task)
    if len(results) == 2 and isinstance(results[1], Message):
        reply = results[1]
        try:
            await run_auto_update(manual=True, reply_message=reply)
        except Exception as exc:
            LOGGER.error(f"manual auto update failed: {exc}")
            await reply.edit(f"❌ 自动更新失败：{exc}")
