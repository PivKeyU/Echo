import asyncio

from cacheout import Cache
from pykeyboard import InlineKeyboard, InlineButton
from pyrogram.types import InlineKeyboardMarkup
from pyromod.helpers import ikb, array_chunk
from bot import chanel, main_group, bot_name, extra_emby_libs, tz_id, tz_ad, tz_api, tz_version, tz_username, tz_password, _open, sakura_b, \
    schedall, auto_update, fuxx_pitao, moviepilot, red_envelope, config, LOGGER
from bot.func_helper import nezha_res
from bot.func_helper.emby import emby
from bot.func_helper.utils import async_memoize
from bot.sql_helper.sql_invite import (
    INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
    INVITE_CREDIT_TYPE_GROUP,
    available_invite_credit_count,
    has_viewing_access,
    list_invite_records,
    qualification_revoked,
    user_has_account_open_history,
)
from bot.sql_helper.sql_emby import sql_get_emby

cache = Cache()


def _is_placeholder_telegram_ref(value) -> bool:
    normalized = str(value or "").strip()
    if normalized.startswith("https://t.me/") or normalized.startswith("http://t.me/"):
        normalized = normalized.rsplit("/", 1)[-1]
    normalized = normalized.strip().lstrip("@").lower()
    return not normalized or normalized in {
        "0",
        "none",
        "null",
        "your_main_group_username",
        "your_channel_username",
    } or "replace_with" in normalized


def _telegram_entry_url(value) -> str | None:
    if _is_placeholder_telegram_ref(value):
        return None
    text = str(value).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("t.me/") or text.startswith("telegram.me/"):
        return f"https://{text}"
    if text.lstrip("-").isdigit():
        return None
    if text.startswith("+"):
        return f"https://t.me/{text}"
    return f"https://t.me/{text.lstrip('@')}"


def _build_join_verify_keyboard() -> InlineKeyboardMarkup:
    first_row = []
    channel_url = _telegram_entry_url(chanel)
    group_url = _telegram_entry_url(main_group)
    if channel_url:
        first_row.append(('🌟 频道入口', channel_url, 'url'))
    if group_url:
        first_row.append(('💫 群组入口', group_url, 'url'))
    lines = []
    if first_row:
        lines.append(first_row)
    lines.append([('🔄 我已加入，重新验证', 'back_start')])
    lines.append([('❌ 关闭消息', 'closeit')])
    return ikb(lines)

"""start面板 ↓"""


def judge_start_ikb(is_admin: bool, account: bool, user_id: int | None = None) -> InlineKeyboardMarkup:
    """
    start面板按钮
    """
    if not account:
        d = []
        d.append(['🎟️ 使用注册码', 'exchange'])
        d.append(['👑 创建账户', 'create'])
        d.append(['⭕ 换绑TG', 'changetg'])
        d.append(['🔍 绑定TG', 'bindtg'])
        # 如果邀请等级为d （未注册用户也能使用），则显示兑换商店
        if _open.invite_lv == 'd':
            d.append(['🏪 兑换商店', 'storeall'])
    else:
        d = [['️👥 用户功能', 'members'], ['🌐 服务器', 'server']]
        if schedall.check_ex:
            d.append(['🎟️ 使用续期码', 'exchange'])
        if schedall.partition_check and len(config.partition_libs) > 0:
            d.append(['🎟️ 使用分区码', 'partitioncode'])
    if _open.checkin:
        d.append(['🎯 签、签一下', 'checkin'])
    lines = array_chunk(d, 2)
    if is_admin: lines.append([['👮🏻‍♂️ admin', 'manage']])
    keyword = ikb(lines)
    return keyword


# un_group_answer
group_f = ikb([[('点击我(●ˇ∀ˇ●)', f't.me/{bot_name}', 'url')]])
# un in group
judge_group_ikb = _build_join_verify_keyboard()

"""members ↓"""


def members_ikb(is_admin: bool = False, account: bool = False) -> InlineKeyboardMarkup:
    """
    判断用户面板
    """
    if account:
        normal = [[('🏪 兑换商店', 'storeall'), ('🗑️ 删除账号', 'delme')],
                    [('🎬 显示/隐藏', 'embyblock'), ('⭕ 重置密码', 'reset')],
                    [('🔐 更换安全码', 'change_pwd2'), ('⭕ 换绑TG', 'changetg')],
                    [('💠 我的设备', 'my_devices')],
                    ]
        if moviepilot.status:
            normal.append([('🍿 点播中心', 'download_center')])
        normal.append([('♻️ 主界面', 'back_start')])
        return ikb(normal)
    else:
        return judge_start_ikb(is_admin, account)
        # return ikb(
        #     [[('👑 创建账户', 'create')], [('⭕ 换绑TG', 'changetg'), ('🔍 绑定TG', 'bindtg')],
        #      [('♻️ 主界面', 'back_start')]])


back_start_ikb = ikb([[('💫 回、回去啦', 'back_start')]])
back_members_ikb = ikb([[('💨 勉强返回', 'members')]])
back_manage_ikb = ikb([[('💨 勉强返回', 'manage')]])
re_create_ikb = ikb([[('🍥 真是的，重新输入', 'create'), ('💫 用户主页', 'members')]])
re_changetg_ikb = ikb([[('✨ 换绑TG', 'changetg'), ('💫 用户主页', 'members')]])
re_bindtg_ikb = ikb([[('✨ 绑定TG', 'bindtg'), ('💫 用户主页', 'members')]])
re_delme_ikb = ikb([[('♻️ 再试一次啦', 'delme')], [('🔙 算了返回', 'members')]])
re_reset_ikb = ikb([[('♻️ 重试', 'reset')], [('🔙 返回', 'members')]])
re_change_pwd2_ikb = ikb([[('♻️ 重试', 'change_pwd2')], [('🔙 返回', 'members')]])
re_exchange_b_ikb = ikb([[('♻️ 再给你一次机会', 'exchange'), ('❌ 算了', 'closeit')]])
re_born_ikb = ikb([[('✨ 重输', 'store-reborn'), ('💫 返回', 'storeall')]])


def send_changetg_ikb(cr_id, rp_id):
    """
    :param cr_id: 当前操作id
    :param rp_id: 替换id
    :return:
    """
    return ikb([[('✅ 通过', f'changetg_{cr_id}_{rp_id}'), ('❎ 驳回', f'nochangetg_{cr_id}_{rp_id}')]])


def store_ikb():
    return ikb([[(f'♾️ 兑换白名单', 'store-whitelist'), (f'🔥 兑换解封禁', 'store-reborn')],
                [(f'🎟️ 兑换注册码', 'store-invite'), (f'🔍 查询注册码', 'store-query')],
                [(f'❌ 取消', 'members')]])


re_store_renew = ikb([[('✨ 重新输入', 'changetg'), ('💫 取消输入', 'storeall')]])


def del_me_ikb(embyid) -> InlineKeyboardMarkup:
    return ikb([[('🎯 确定', f'delemby-{embyid}')], [('🔙 取消', 'members')]])


def emby_block_ikb(embyid) -> InlineKeyboardMarkup:
    return ikb(
        [[("✔️️ - 显示", f"emby_unblock-{embyid}"), ("✖️ - 隐藏", f"emby_block-{embyid}")], [("🔙 返回", "members")]])


user_emby_block_ikb = ikb([[('✅ 已隐藏', 'members')]])
user_emby_unblock_ikb = ikb([[('❎ 已显示', 'members')]])

"""server ↓"""


@async_memoize(ttl=120)
async def cr_page_server():
    """
    翻页服务器面板
    :return:
    """
    sever = await nezha_res.sever_info(tz_ad, tz_api, tz_id, tz_version, tz_username, tz_password)
    if not sever:
        return ikb([[('🔙 - 用户', 'members'), ('❌ - 上一级', 'back_start')]]), None
    d = []
    for i in sever:
        d.append([i['name'], f'server:{i["id"]}'])
    lines = array_chunk(d, 3)
    lines.append([['🔙 - 用户', 'members'], ['❌ - 上一级', 'back_start']])
    # keyboard是键盘，a是sever
    return ikb(lines), sever


"""admins ↓"""

gm_ikb_content = ikb([[('⭕ 注册状态', 'open-menu'), ('🎟️ 注册/续期码', 'cr_link')],
                      [('💊 查询注册', 'ch_link'), ('🏬 兑换设置', 'set_renew')],
                      [('👥 用户列表', 'normaluser'), ('👑 白名单列表', 'whitelist'), ('💠 设备列表', 'user_devices')],
                      [('🌏 定时', 'schedall'), ('🕹️ 主界面', 'back_start'), ('其他 🪟', 'back_config')]])


def open_menu_ikb(openstats, timingstats) -> InlineKeyboardMarkup:
    return ikb([[(f'{openstats} 自由注册', 'open_stat'), (f'{timingstats} 定时注册', 'open_timing')],
                [('🤖注册账号天数', 'open_us'),('⭕ 注册限制', 'all_user_limit')], [('🌟 返回上一级', 'manage')]])


back_free_ikb = ikb([[('🔙 返回上一级', 'open-menu')]])
back_open_menu_ikb = ikb([[('🪪 重新定时', 'open_timing'), ('🔙 注册状态', 'open-menu')]])
re_cr_link_ikb = ikb([[('♻️ 继续创建', 'cr_link'), ('🎗️ 返回主页', 'manage')]])
close_it_ikb = ikb([[('❌ - Close', 'closeit')]])


def ch_link_ikb(ls: list) -> InlineKeyboardMarkup:
    lines = array_chunk(ls, 2)
    lines.append([["💫 回到首页", "manage"]])
    return ikb(lines)


def date_ikb(i) -> InlineKeyboardMarkup:
    return ikb([[('🌘 - 月', f'register_mon_{i}'), ('🌗 - 季', f'register_sea_{i}'),
                 ('🌖 - 半年', f'register_half_{i}')],
                [('🌕 - 年', f'register_year_{i}'), ('🌑 - 未用', f'register_unused_{i}'), ('🎟️ - 已用', f'register_used_{i}')],
                [('🔙 - 返回', 'ch_link')]])

# 翻页按钮
async def cr_paginate(total_page: int, current_page: int, n, tg: int | None = None) -> InlineKeyboardMarkup:
    """
    :param total_page: 总数
    :param current_page: 目前
    :param n: mode 可变项
    :return:
    """
    keyboard = InlineKeyboard()
    callback_suffix = f'_{n}' if tg is None else f'_{n}_{tg}'
    keyboard.paginate(total_page, current_page, 'pagination_keyboard:{number}' + callback_suffix)
    next = InlineButton('⏭️ 后退+5', f'pagination_keyboard:{current_page + 5}{callback_suffix}')
    previous = InlineButton('⏮️ 前进-5', f'pagination_keyboard:{current_page - 5}{callback_suffix}')
    followUp = [InlineButton('❌ 关闭', f'closeit')]
    if total_page > 5:
        if current_page - 5 >= 1:
            followUp.append(previous)
        if current_page + 5 < total_page:
            followUp.append(next)
    keyboard.row(*followUp)
    return keyboard


async def users_iv_button(total_page: int, current_page: int, tg) -> InlineKeyboardMarkup:
    """
    :param total_page: 总页数
    :param current_page: 当前页数
    :param tg: 可操作的tg_id
    :return:
    """
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'users_iv:{number}' + f'_{tg}')
    next = InlineButton('⏭️ 后退+5', f'users_iv:{current_page + 5}_{tg}')
    previous = InlineButton('⏮️ 前进-5', f'users_iv:{current_page - 5}_{tg}')
    followUp = [InlineButton('❌ 关闭', f'closeit')]
    if total_page > 5:
        if current_page - 5 >= 1:
            followUp.append(previous)
        if current_page + 5 < total_page:
            followUp.append(next)
    keyboard.row(*followUp)
    return keyboard


async def plays_list_button(total_page: int, current_page: int, days) -> InlineKeyboardMarkup:
    """
    :param total_page: 总页数
    :param current_page: 当前页数
    :param days: 请求获取多少天
    :return:
    """
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'uranks:{number}' + f'_{days}')
    # 添加按钮,前进5, 后退5
    next = InlineButton('⏭️ 后退+5', f'uranks:{current_page + 5}_{days}')
    previous = InlineButton('⏮️ 前进-5', f'uranks:{current_page - 5}_{days}')
    followUp = [InlineButton('❌ 关闭', f'closeit')]
    if total_page > 5:
        if current_page - 5 >= 1:
            followUp.append(previous)
        if current_page + 5 < total_page:
            followUp.append(next)
    keyboard.row(*followUp)
    return keyboard


async def store_query_page(total_page: int, current_page: int) -> InlineKeyboardMarkup:
    """
    member的注册码查询分页
    :param total_page: 总
    :param current_page: 当前
    :return:
    """
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'store-query:{number}')
    next = InlineButton('⏭️ 后退+5', f'store-query:{current_page + 5}')
    previous = InlineButton('⏮️ 前进-5', f'store-query:{current_page - 5}')
    followUp = [InlineButton('🔙 Back', 'storeall')]
    if total_page > 5:
        if current_page - 5 >= 1:
            followUp.append(previous)
        if current_page + 5 < total_page:
            followUp.append(next)
    keyboard.row(*followUp)
    return keyboard

async def whitelist_page_ikb(total_page: int, current_page: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'whitelist:{number}')
    next = InlineButton('⏭️ 后退+5', f'whitelist:{current_page + 5}')
    previous = InlineButton('⏮️ 前进-5', f'whitelist:{current_page - 5}')
    followUp = [InlineButton('🔙 Back', 'manage')]
    if total_page > 5:
        if current_page - 5 >= 1:
            followUp.append(previous)
        if current_page + 5 < total_page:
            followUp.append(next)
    keyboard.row(*followUp)
    return keyboard
async def normaluser_page_ikb(total_page: int, current_page: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'normaluser:{number}')
    next = InlineButton('⏭️ 后退+5', f'normaluser:{current_page + 5}')
    previous = InlineButton('⏮️ 前进-5', f'normaluser:{current_page - 5}')
    followUp = [InlineButton('🔙 Back', 'manage')]
    if total_page > 5:
        if current_page - 5 >= 1:
            followUp.append(previous)
        if current_page + 5 < total_page:
            followUp.append(next)
    keyboard.row(*followUp)
    return keyboard
def devices_page_ikb( has_prev: bool, has_next: bool, page: int) -> InlineKeyboardMarkup:
    # 构建分页按钮
    buttons = []
    if has_prev or has_next:
        nav_buttons = []
        if has_prev:
            nav_buttons.append(('⬅️', f'devices:{page-1}'))
        nav_buttons.append((f'第 {page} 页', 'none'))
        if has_next:
            nav_buttons.append(('➡️', f'devices:{page+1}'))
        buttons.append(nav_buttons)
    # 添加返回按钮
    buttons.append([('🔙 返回', 'manage')])
    keyboard = ikb(buttons)
    return keyboard
def cr_renew_ikb():
    checkin = '✔️' if _open.checkin else '❌'
    exchange = '✔️' if _open.exchange else '❌'
    whitelist = '✔️' if _open.whitelist else '❌'
    invite = '✔️' if _open.invite else '❌'
    # 添加邀请等级的显示
    lv_dic = {
        'a': '白名单',
        'b': '普通用户',
        'c': '已禁用用户',
        'd': '所有人'
    }
    invite_lv_text = lv_dic.get(_open.invite_lv, '未知')
    checkin_lv_text = lv_dic.get(_open.checkin_lv, '未知')
    keyboard = InlineKeyboard(row_width=2)
    keyboard.add(InlineButton(f'{checkin} 每日签到', f'set_renew-checkin'),
                 InlineButton(f'签到等级: {checkin_lv_text}', f'set_checkin_lv'),
                 InlineButton(f'{exchange} 自动{sakura_b}续期', f'set_renew-exchange'),
                 InlineButton(f'{whitelist} 兑换白名单', f'set_renew-whitelist'),
                 InlineButton(f'{invite} 兑换邀请码', f'set_renew-invite'),
                 InlineButton(f'邀请等级: {invite_lv_text}', f'set_invite_lv')
                 )
    keyboard.row(InlineButton(f'◀ 返回', 'manage'))
    return keyboard
def invite_lv_ikb():
    keyboard = ikb([
        [('🅰️ 白名单', 'set_invite_lv-a'), ('🅱️ 普通用户', 'set_invite_lv-b')],
        [('©️ 已禁用用户', 'set_invite_lv-c'), ('🅳️  所有用户', 'set_invite_lv-d')],
        [('🔙 返回', 'set_renew')]
    ])
    return keyboard

def checkin_lv_ikb():
    keyboard = ikb([
        [('🅰️ 白名单', 'set_checkin_lv-a'), ('🅱️ 普通用户', 'set_checkin_lv-b')],
        [('©️ 已禁用用户', 'set_checkin_lv-c'), ('🅳️  所有用户', 'set_checkin_lv-d')],
        [('🔙 返回', 'set_renew')]
    ])
    return keyboard
""" config_panel ↓"""


def config_preparation() -> InlineKeyboardMarkup:
    mp_set = '✅' if moviepilot.status else '❎'
    auto_up = '✅' if auto_update.status else '❎'
    leave_ban = '✅' if _open.leave_ban else '❎'
    uplays = '✅' if _open.uplays else '❎'
    fuxx_pt = '✅' if fuxx_pitao else '❎'
    red_envelope_status = '✅' if red_envelope.status else '❎'
    allow_private = '✅' if red_envelope.allow_private else '❎'
    checkin_lv_text = {'a': '白名单', 'b': '普通用户', 'd': '所有人'}.get(_open.checkin_lv, '所有人')
    keyboard = ikb(
        [[('📄 导出日志', 'log_out'), ('📌 设置探针', 'set_tz')],
         [('🎬 显/隐指定库', 'set_block'), (f'{fuxx_pt} 皮套人过滤功能', 'set_fuxx_pitao')],
         [('💠 普通用户线路', 'set_line'),('🌟 白名单线路', 'set_whitelist_line')],
         [(f'{leave_ban} 退群封禁', 'leave_ban'), (f'{uplays} 观影奖励结算', 'set_uplays')],
         [(f'{auto_up} 自动更新本女仆', 'set_update'), (f'{mp_set} Moviepilot点播', 'set_mp')],
         [(f'{red_envelope_status} 红包', 'set_red_envelope_status'), (f'{allow_private} 专属红包', 'set_red_envelope_allow_private')],
            [('🎟️ 分区通行码', 'partition_code_panel')],
         [(f'设置赠送资格天数({config.kk_gift_days}天)', 'set_kk_gift_days'), (f'设置活跃检测天数({config.activity_check_days}天)', 'set_activity_check_days')],
         [(f'设置封存账号天数({config.freeze_days}天)', 'set_freeze_days')],
         [(f'更换安全码费用({config.open.change_pwd2_cost}{sakura_b})', 'set_change_pwd2_cost')],
         [(f'设置签到权限({checkin_lv_text})', 'set_checkin_lv')],
         [('🔙 返回', 'manage')]])
    return keyboard


back_config_p_ikb = ikb([[("🎮  ️返回主控", "back_config")]])


def back_set_ikb(method) -> InlineKeyboardMarkup:
    return ikb([[("♻️ 重新设置", f"{method}"), ("🔙 返回主页", "back_config")]])


""" other """
register_code_ikb = ikb([[('🎟️ 注册', 'create'), ('⭕ 取消', 'closeit')]])
dp_g_ikb = ikb([[("联系主人", "https://t.me/pivkeyu", "url")]])


async def cr_kk_ikb(uid, first):
    text = ''
    text1 = ''
    keyboard = []
    account = sql_get_emby(uid)
    if account is None:
        text += f'**· 🆔 TG** ：[{first}](tg://user?id={uid}) [`{uid}`]\n数据库中没有此ID。ta 还没有私聊过我'
    else:
        name = account.name or '无账户信息'
        embyid = account.embyid
        iv = account.iv
        lv_dict = {'a': '白名单', 'b': '**正常**', 'c': '**已禁用**', 'd': '未注册'}
        lv = lv_dict.get(account.lv, '未知')
        if lv == '白名单':
            ex = '+ ∞'
        elif account.name is not None and schedall.low_activity and not schedall.check_ex:
            ex = f'__若{config.activity_check_days}天无观看将封禁__'
        elif account.name is not None and not schedall.low_activity and not schedall.check_ex:
            ex = ' __无需保号，放心食用__'
        else:
            ex = account.ex or '无账户信息'
        cust_task = None
        if name != '无账户信息':
            ban = "🌟 解除禁用" if lv == "**已禁用**" else '💢 禁用账户'
            keyboard = [[ban, f'user_ban-{uid}'], ['⚠️ 删除账户', f'closeemby-{uid}']]
            if len(extra_emby_libs) > 0:
                success, rep = await emby.user(emby_id=embyid)
                if success:
                    try:
                        policy = rep.get("Policy", {})
                        current_enabled_folders = policy.get("EnabledFolders", [])
                        enable_all_folders = policy.get("EnableAllFolders", False)
                        extra_folder_ids = await emby.get_folder_ids_by_names(extra_emby_libs)
                        if enable_all_folders is True:
                            libs, embyextralib = ['关闭', f'embyextralib_block-{uid}']
                        elif extra_folder_ids and len(extra_folder_ids) > 0:
                            if all(folder_id in current_enabled_folders for folder_id in extra_folder_ids):
                                libs, embyextralib = ['关闭', f'embyextralib_block-{uid}']
                            else:
                                libs, embyextralib = ['开启', f'embyextralib_unblock-{uid}']
                        else:
                            libs, embyextralib = ['关闭', f'embyextralib_block-{uid}']
                        keyboard.append([f'{libs} 额外媒体库', embyextralib])
                    except Exception as e:
                        LOGGER.error(f"获取额外媒体库状态失败: {str(e)}")
                        keyboard.append([f'关闭额外媒体库', f'embyextralib_block-{uid}'])
            cust_task = asyncio.ensure_future(emby.emby_cust_commit(emby_id=embyid, days=30))
        else:
            keyboard.append(['✨ 赠送资格', f'gift-{uid}'])
        text += f"**· 🍉 TG&名称** | [{first}](tg://user?id={uid})\n" \
                f"**· 🍒 识别のID** | `{uid}`\n" \
                f"**· 🍓 当前状态** | {lv}\n" \
                f"**· 🍥 持有{sakura_b}** | {iv}\n" \
                f"**· 💠 账号名称** | {name}\n" \
                f"**· 🚨 到期时间** | **{ex}**\n"
        try:
            viewing_access = has_viewing_access(account)
            group_credit_count = available_invite_credit_count(uid, credit_type=INVITE_CREDIT_TYPE_GROUP)
            group_revoked = qualification_revoked(uid, credit_type=INVITE_CREDIT_TYPE_GROUP)
            account_revoked = qualification_revoked(uid, credit_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN)
            account_open_records = list_invite_records(
                inviter_tg=uid,
                credit_type=INVITE_CREDIT_TYPE_ACCOUNT_OPEN,
                limit=1,
            )
            group_records = list_invite_records(
                inviter_tg=uid,
                credit_type=INVITE_CREDIT_TYPE_GROUP,
                limit=1,
            )
            latest_open = account_open_records[0] if account_open_records else None
            latest_group = group_records[0] if group_records else None
            account_history = user_has_account_open_history(uid) if viewing_access else False
            account_apply_text = "有" if viewing_access and not account_history and not account_revoked else "无"
            if latest_open:
                account_apply_text += f"（最近：TG {latest_open.get('invitee_tg')} · {latest_open.get('status_text')}）"
            if account_revoked:
                account_apply_text += "（后台已撤销）"
            invite_text = "有" if group_credit_count > 0 else "无"
            if latest_group:
                invite_text += f"（最近：TG {latest_group.get('invitee_tg')} · {latest_group.get('status_text')}）"
            if group_revoked:
                invite_text += "（后台已撤销）"
            text += (
                f"**· 🎬 观影资格** | {'有' if viewing_access else '无'}\n"
                f"**· 📨 入群邀请资格** | {invite_text}\n"
                f"**· 📝 开号申请资格** | {account_apply_text}\n"
            )
        except Exception as exc:
            LOGGER.warning(f"kk invite qualification load failed uid={uid}: {exc}")
        if cust_task is not None:
            try:
                rst = await cust_task
                last_time = rst[0][0]
                toltime = rst[0][1]
                text1 = f"**· 🔋 上次活动** | {last_time.split('.')[0]}\n" \
                        f"**· 📅 过去30天** | {toltime} 分钟"
            except (TypeError, IndexError, ValueError):
                text1 = f"**· 📅 过去30天未有记录**"
        text += text1
        keyboard.extend([['🚫 踢出并封禁', f'fuckoff-{uid}'], ['❌ 删除消息', f'closeit']])
        lines = array_chunk(keyboard, 2)
        keyboard = ikb(lines)
    return text, keyboard


def uinfo_ikb(embyid, lv=None):
    row1 = []
    row2 = []
    if lv == 'c':
        row1.append(('✅ 启用账户', f'uinfo_enable-{embyid}'))
    elif lv in ('a', 'b'):
        row1.append(('🚫 禁用账户', f'uinfo_disable-{embyid}'))
    if lv != 'd':
        row1.append(('🌏 播放查询', f'userip-{embyid}'))
        row2 = [('🗑️ 删除账户', f'uinfo_delete-{embyid}')]
    row2.append(('❌ 关闭', 'closeit'))

    return ikb([row1, row2])


def uinfo_delete_confirm_ikb(embyid):
    return ikb([
        [('⚠️ 确认删除', f'uinfo_delete_confirm-{embyid}'), ('🔙 取消', f'uinfo_delete_cancel-{embyid}')]
    ])


def gog_rester_ikb(link=None) -> InlineKeyboardMarkup:
    link_ikb = ikb([[('🎁 点击领取', link, 'url')]]) if link else ikb([[('👆🏻 点击注册', f't.me/{bot_name}', 'url')]])
    return link_ikb


""" sched_panel ↓"""


def sched_buttons():
    dayrank = '✅' if schedall.dayrank else '❎'
    weekrank = '✅' if schedall.weekrank else '❎'
    dayplayrank = '✅' if schedall.dayplayrank else '❎'
    weekplayrank = '✅' if schedall.weekplayrank else '❎'
    check_ex = '✅' if schedall.check_ex else '❎'
    low_activity = '✅' if schedall.low_activity else '❎'
    backup_db = '✅' if schedall.backup_db else '❎'
    partition_check = '✅' if getattr(schedall, 'partition_check', True) else '❎'
    keyboard = InlineKeyboard(row_width=2)
    keyboard.add(InlineButton(f'{dayrank} 播放日榜', f'sched-dayrank'),
                 InlineButton(f'{weekrank} 播放周榜', f'sched-weekrank'),
                 InlineButton(f'{dayplayrank} 观影日榜', f'sched-dayplayrank'),
                 InlineButton(f'{weekplayrank} 观影周榜', f'sched-weekplayrank'),
                 InlineButton(f'{check_ex} 到期保号', f'sched-check_ex'),
                 InlineButton(f'{low_activity} 活跃保号', f'sched-low_activity'),
                 InlineButton(f'{backup_db} 自动备份数据库', f'sched-backup_db'),
                 InlineButton(f'{partition_check} 分区授权检查', f'sched-partition_check')
                 )
    keyboard.row(InlineButton(f'🫧 返回', 'manage'))
    return keyboard


""" checkin 按钮↓"""

# def shici_button(ls: list):
#     shici = []
#     for l in ls:
#         l = [l, f'checkin-{l}']
#         shici.append(l)
#     # print(shici)
#     lines = array_chunk(shici, 4)
#     return ikb(lines)


# checkin_button = ikb([[('🔋 重新签到', 'checkin'), ('🎮 返回主页', 'back_start')]])

""" Request_media """

# request_tips_ikb = ikb([[('✔️ 已转向私聊求片', 'go_to_qiupian')]])

request_tips_ikb = None


re_download_center_ikb = ikb([
    [('🍿 点播', 'get_resource'), ('📶 下载进度', 'download_rate')],
    [('🔙 返回', 'members')]])
continue_search_ikb = ikb([
    [('🔄 继续搜索', 'continue_search'), ('❌ 取消搜索', 'cancel_search')],
    [('🔙 返回', 'download_center')]
])
def request_record_page_ikb(has_prev: bool, has_next: bool):
    buttons = []
    if has_prev:
        buttons.append(('< 上一页', 'request_record_prev'))
    if has_next:
        buttons.append(('下一页 >', 'request_record_next'))
    return ikb([buttons, [('🔙 返回', 'download_center')]])
def mp_search_page_ikb(has_prev: bool, has_next: bool, page: int):
    buttons = []
    if has_prev:
        buttons.append(('< 上一页', 'mp_search_prev_page'))
    if has_next:
        buttons.append(('下一页 >', 'mp_search_next_page'))
    return ikb([buttons, [('💾 选择下载', 'mp_search_select_download'), ('❌ 取消搜索', 'cancel_search')]])

# 添加 MoviePilot 设置按钮
def mp_config_ikb():
    """MoviePilot 设置面板按钮"""
    mp_status = '✅' if moviepilot.status else '❎'
    lv_text = '无'
    if moviepilot.lv == 'a':
        lv_text = '白名单'
    elif moviepilot.lv == 'b':
        lv_text = '普通用户'
    keyboard = ikb([
        [(f'{mp_status} 点播功能', 'set_mp_status')],
        [('💰 设置点播价格', 'set_mp_price'), ('👥 设置用户权限', 'set_mp_lv')],
        [('📝 设置日志频道', 'set_mp_log_channel')],
        [('🔙 返回', 'back_config')]
    ])
    return keyboard
