import asyncio
import random
from datetime import datetime, timezone, timedelta

from pyrogram import filters

from bot import bot, _open, sakura_b, lv_allowed
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.msg_utils import callAnswer, sendMessage, deleteMessage
from bot.sql_helper.sql_emby import sql_get_emby, sql_try_daily_checkin


@bot.on_callback_query(filters.regex('checkin') & user_in_group_on_filter)
async def user_in_checkin(_, call):
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.strftime("%Y-%m-%d")
    if _open.checkin:
        e = sql_get_emby(call.from_user.id)
        if not e:
            await callAnswer(call, '🧮 找不到你...才、才不是本女仆丢的！', True)

        elif not e.ch or e.ch.strftime("%Y-%m-%d") < today:
            if _open.checkin_lv:
                if not lv_allowed(e.lv, _open.checkin_lv):
                    await callAnswer(call, f'❌ 您无权签到，如有异议，请不要有异议。', True)
                    return
            reward = random.randint(_open.checkin_reward[0], _open.checkin_reward[1])
            result = sql_try_daily_checkin(call.from_user.id, reward, now)
            if not result.get("ok"):
                await callAnswer(call, '❌ 结算失败了...哼，才不是本女仆的问题。等、等一下再试啦。', True)
                return
            if result.get("already_checked"):
                await callAnswer(call, '⭕ 今天签过了啦！这么无聊的活动...你、你居然天天来？', True)
                return
            if not result.get("checked_in"):
                await callAnswer(call, '🧮 找不到你...才、才不是本女仆丢的！', True)
                return
            s = int(result.get("balance") or 0)
            text = f'🎉 哼、才不是特意给你奖励呢...\n**签到成功** | {reward} {sakura_b}\n💴 **当前持有** | {s} {sakura_b}\n⏳ **签到日期** | {now.strftime("%Y-%m-%d")}\n\n...算了，明天也、也可以来哦。'
            await asyncio.gather(deleteMessage(call), sendMessage(call, text=text))

        else:
            await callAnswer(call, '⭕ 今天签过了啦！这么无聊的活动...你、你居然天天来？', True)
    else:
        await callAnswer(call, '❌ 签到没开啦...等主人想起来再说。', True)
