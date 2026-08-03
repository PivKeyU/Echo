import functools
import hashlib
import json

import pytz

from bot import bot, _open, save_config, owner, admins, bot_name, ranks, schedall, group, config
from bot.sql_helper.sql_code import sql_add_code
from bot.sql_helper.sql_emby import sql_count_emby, sql_get_emby
from cacheout import Cache

cache = Cache()


def async_memoize(ttl=120):
    """Async-safe memoization decorator.

    Unlike cacheout.Cache.memoize which caches the coroutine object when
    applied to async functions, this decorator awaits the coroutine and
    caches the actual result.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = _memo_key(func, args, kwargs)
            result = cache.get(key)
            if result is not None:
                return result
            result = await func(*args, **kwargs)
            if result is not None:
                cache.set(key, result, ttl=ttl)
            return result

        def _memo_key(fn, args, kwargs):
            raw = ":".join([
                fn.__qualname__,
                hashlib.md5(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest(),
                hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest(),
            ])
            return f"async_memoize:{raw}"

        def invalidate(*args, **kwargs):
            """按相同函数名删除该函数全部缓存条目（结算类逻辑防重复）。

            类方法（classmethod + memoize）经绑定后参数含 cls，调用方难以
            复现完全一致的 key，因此按函数限定名前缀删除更稳妥。
            """
            prefix = f"async_memoize:{func.__qualname__}:"
            stale = [key for key in cache.keys() if str(key).startswith(prefix)]
            if stale:
                cache.delete_many(*stale)


        wrapper.invalidate = invalidate
        return wrapper

    return decorator


def judge_admins(uid):
    """
    判断是否admin
    :param uid: tg_id
    :return: bool
    """
    if uid != owner and uid not in admins and uid not in group:
        return False
    else:
        return True


# @cache.memoize(ttl=60)
async def members_info(tg=None, name=None):
    """
    基础资料 - 可传递 tg,emby_name
    :param tg: tg_id
    :param name: emby_name
    :return: name, lv, ex, us, embyid, pwd2
    """
    if tg is None:
        tg = name
    data = sql_get_emby(tg)
    if data is None:
        return None
    else:
        name = data.name or '无账户信息'
        pwd2 = data.pwd2
        embyid = data.embyid
        iv = data.iv
        lv_dict = {'a': '白名单', 'b': '**正常**', 'c': '**已禁用**', 'd': '未注册'}  # , 'e': '**21天未活跃/无信息**'
        lv = lv_dict.get(data.lv, '未知')
        if lv == '白名单':
            ex = '+ ∞'
        elif data.name is not None and schedall.low_activity and not schedall.check_ex:
            ex = f'__若{config.activity_check_days}天无观看将封禁__'
        elif data.name is not None and not schedall.low_activity and not schedall.check_ex:
            ex = ' __无需保号，放心食用__'
        else:
            ex = data.ex or '无账户信息'
        return name, lv, ex, iv, embyid, pwd2


async def open_check():
    """
    对config查询open
    :return: open_stats, all_user, tem, timing
    """
    open_stats = _open.stat
    all_user = _open.all_user
    tem = refresh_registration_slots()
    timing = _open.timing
    return open_stats, all_user, tem, timing


def tem_adduser():
    return refresh_registration_slots()


def tem_deluser():
    return refresh_registration_slots()


def refresh_registration_slots() -> int:
    _, registered_count, _ = sql_count_emby()
    current_count = int(registered_count or 0)
    changed = int(_open.tem or 0) != current_count
    _open.tem = current_count
    if current_count >= int(_open.all_user or 0) and _open.stat:
        _open.stat = False
        changed = True
    if changed:
        save_config()
    return current_count


from random import choice
import string
import re


async def pwd_create(length=8, chars=string.ascii_letters + string.digits):
    """
    简短地生成随机密码，包括大小写字母、数字，可以指定密码长度
    :param length: 长度
    :param chars: 字符 -> python3中为string.ascii_letters,而python2下则可以使用string.letters和string.ascii_letters
    :return: 密码
    """
    return ''.join([choice(chars) for i in range(length)])


_CODE_SUFFIX_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def _normalize_fixed_suffix(raw_suffix: str) -> str:
    suffix = (raw_suffix or "").strip()
    if not suffix:
        raise ValueError("固定后缀不能为空")
    if not _CODE_SUFFIX_PATTERN.fullmatch(suffix):
        raise ValueError("固定后缀只能包含字母、数字、下划线和短横线，长度 1-20")
    return suffix


async def _build_code_suffix(index: int, count: int, suffix_mode: str, suffix_text: str | None) -> str:
    mode = (suffix_mode or "random").lower()
    if mode == "random":
        return await pwd_create(10)
    if mode != "fixed":
        raise ValueError("后缀模式只能是 random 或 fixed")

    suffix = _normalize_fixed_suffix(suffix_text)
    if count > 1:
        suffix = f"{suffix}-{index}"
    return suffix


async def _build_codes(
    tg: int,
    times,
    count: int,
    days: int,
    method: str,
    code_kind: str,
    usage_limit: int = 1,
    suffix_mode: str = "random",
    suffix_text: str | None = None,
):
    links = ""
    code_list = []
    normalized_usage_limit = max(int(usage_limit or 1), 1)
    normalized_method = (method or "").lower()

    if normalized_method not in {"code", "link"}:
        raise ValueError("生成模式只能是 code 或 link")

    for index in range(1, int(count) + 1):
        suffix = await _build_code_suffix(index, int(count), suffix_mode, suffix_text)
        uid = f"{ranks.logo}-{times}-{code_kind}_{suffix}"
        if len(uid) > 50:
            raise ValueError("注册码过长，请缩短固定后缀")

        code_list.append({"code": uid, "use_limit": normalized_usage_limit})
        if normalized_method == "code":
            links += f"`{uid}`\n"
        else:
            links += f"t.me/{bot_name}?start={uid}\n"

    if sql_add_code(code_list, tg, days, use_limit=normalized_usage_limit) is False:
        return None
    return links


async def cr_link_one(
    tg: int,
    times,
    count,
    days: int,
    method: str,
    usage_limit: int = 1,
    suffix_mode: str = "random",
    suffix_text: str | None = None,
):
    return await _build_codes(
        tg=tg,
        times=times,
        count=count,
        days=days,
        method=method,
        code_kind="Register",
        usage_limit=usage_limit,
        suffix_mode=suffix_mode,
        suffix_text=suffix_text,
    )


async def rn_link_one(
    tg: int,
    times,
    count,
    days: int,
    method: str,
    usage_limit: int = 1,
    suffix_mode: str = "random",
    suffix_text: str | None = None,
):
    return await _build_codes(
        tg=tg,
        times=times,
        count=count,
        days=days,
        method=method,
        code_kind="Renew",
        usage_limit=usage_limit,
        suffix_mode=suffix_mode,
        suffix_text=suffix_text,
    )


async def cr_link_two(tg: int, for_tg, days: int):
    code_list = []
    invite_code = await pwd_create(11)
    uid = f'{for_tg}-{invite_code}'
    code_list.append(uid)
    link = f't.me/{bot_name}?start={uid}'
    if sql_add_code(code_list, tg, days) is False:
        return None
    return link


from datetime import datetime, timedelta


async def convert_s(seconds: int):
    # 创建一个时间间隔对象，换算以后返回计算出的字符串
    duration = timedelta(seconds=seconds)
    days = duration.days
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    days = '' if days == 0 else f'{days} 天'
    hours = '' if hours == 0 else f'{hours} 小时'
    return f"{days} {hours} {minutes} 分钟"


def convert_runtime(RunTimeTicks: int):
    # 创建一个时间间隔对象，换算以后返回计算出的字符串
    seconds = RunTimeTicks // 10000000
    duration = timedelta(seconds=seconds)
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    hours = '' if hours == 0 else f'{hours} 小时'
    return f"{hours} {minutes} 分钟"


def convert_to_beijing_time(original_date):
    original_date = original_date.split(".")[0].replace('T', ' ')
    dt = datetime.strptime(original_date, "%Y-%m-%d %H:%M:%S") + timedelta(hours=8)
    # 使用pytz.timezone函数获取北京时区对象
    beijing_tz = pytz.timezone("Asia/Shanghai")
    # 使用beijing_tz.localize函数将dt对象转换为有时区的对象
    dt = beijing_tz.localize(dt)
    return dt


@async_memoize(ttl=300)
async def get_users():
    # 创建一个空字典来存储用户的 first_name 和 id
    members_dict = {}
    async for member in bot.get_chat_members(group[0]):
        try:
            members_dict[member.user.id] = member.user.first_name
        except Exception as e:
            print(f'{e} 某名bug {member}')
    return members_dict


def split_long_message(content, max_length=2000):
    """
    将过长的消息内容分割成多个部分，确保每部分都不超过Telegram的长度限制
    
    Args:
        content (str): 要分割的内容
        max_length (int): 每条消息的最大长度限制，默认1000字符（留缓冲）
    
    Returns:
        list: 分割后的消息列表
    """
    if len(content) <= max_length:
        return [content]
    
    messages = []
    lines = content.split('\n')
    current_message = ""
    
    for line in lines:
        # 检查添加这一行后是否会超长
        test_message = current_message + ('\n' if current_message else '') + line
        
        if len(test_message) <= max_length:
            current_message = test_message
        else:
            # 如果当前消息不为空，保存它
            if current_message:
                messages.append(current_message)
                current_message = line
            else:
                # 如果单行就超长，需要强制分割
                if len(line) > max_length:
                    # 按字符分割超长的单行
                    while len(line) > max_length:
                        messages.append(line[:max_length])
                        line = line[max_length:]
                    if line:
                        current_message = line
                else:
                    current_message = line
    
    # 添加最后一部分
    if current_message:
        messages.append(current_message)
    
    return messages


import abc


class Singleton(abc.ABCMeta, type):
    """
    类单例
    """

    _instances: dict = {}

    def __call__(cls, *args, **kwargs):
        key = (cls, args, frozenset(kwargs.items()))
        if key not in cls._instances:
            cls._instances[key] = super().__call__(*args, **kwargs)
        return cls._instances[key]

# import random
# import grequests


# def err_handler(request, exception):
#     get_bot_wlc()


# def random_shici_data(data_list, x):
#     try:
#         # 根据不同的url返回的数据结构，获取相应的字段
#         if x == 0:
#             ju, nm = data_list[0]["content"], f'{data_list[0]["author"]}《{data_list[0]["origin"]}》'
#         elif x == 1:
#             ju, nm = data_list[1]["hitokoto"], f'{data_list[1]["from_who"]}《{data_list[1]["from"]}》'
#         elif x == 2:
#             ju, nm = data_list[2]["content"], data_list[2]["source"]
#             # 如果没有作者信息，就不显示
#         return ju, nm
#     except:
#         return False


# # 请求每日诗词
# def get_bot_shici():
#     try:
#         urls = ['https://v1.jinrishici.com/all.json', 'https://international.v1.hitokoto.cn/?c=i',
#                 'http://yijuzhan.com/api/word.php?m=json']
#         reqs = [grequests.get(url) for url in urls]
#         res_list = grequests.map(reqs)  # exception_handler=err_handler
#         data_list = [res.json() for res in res_list]
#         # print(data_list)
#         seq = [0, 1, 2]
#         x = random.choice(seq)
#         seq.remove(x)
#         e = random.choice(seq)
#         ju, nm = random_shici_data(data_list, x=x)
#         e_ju, e_nm = random_shici_data(data_list, x=e)
#         e_ju = random.sample(e_ju, 6)
#         T = ju
#         t = random.sample(ju, 2)
#         e_ju.extend(t)
#         random.shuffle(e_ju)
#         for i in t:
#             ju = ju.replace(i, '░')  # ░
#         print(T, e_ju, ju, nm)
#         return T, e_ju, ju, nm
#     except Exception as e:
#         print(e)
#         # await get_bot_shici()
