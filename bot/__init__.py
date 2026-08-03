#! /usr/bin/python3
# -*- coding: utf-8 -*-
import contextlib
import os
import time
from pathlib import Path

BOT_TIMEZONE = "Asia/Shanghai"
os.environ["TZ"] = BOT_TIMEZONE
if hasattr(time, "tzset"):
    time.tzset()

from .func_helper.logger_config import logu, Now
from .func_helper.runtime import configure_runtime_limits

LOGGER = logu(__name__)

from .schemas import Config

config = Config.load_config()


def save_config():
    config.save_config()


'''从config对象中获取属性值'''
# bot
bot_name = config.bot_name
bot_token = config.bot_token
owner_api = config.owner_api
owner_hash = config.owner_hash
owner = config.owner
group = config.group
main_group = config.main_group
chanel = config.chanel
bot_photo = config.bot_photo
_open = config.open
admins = config.admins
pivkeyu = config.money
# 兼容旧模块中仍然引用的货币变量名，避免插件升级后导入失败。
money = pivkeyu
sakura_b = pivkeyu
ranks = config.ranks
emotion_cfg = config.emotion
prefixes = ['/', '!', '.', '，', '。']
schedall = config.schedall

# 等级到数值的映射，数值越大权限越高。新等级需要在此注册。
_LV_RANK = {"a": 4, "b": 3, "c": 2, "d": 1}


def lv_allowed(user_lv: str, required_lv: str) -> bool:
    """返回 user_lv 是否满足 required_lv 的最低等级要求。"""
    return _LV_RANK.get(user_lv, 0) >= _LV_RANK.get(required_lv, 0)
# emby设置
emby_api = config.emby_api
emby_url = config.emby_url
emby_line = config.emby_line
emby_whitelist_line = config.emby_whitelist_line
emby_block = config.emby_block
extra_emby_libs = config.extra_emby_libs
partition_libs = config.partition_libs
# # 数据库
db_backend = config.db_backend
db_url = config.db_url
db_host = config.db_host
db_user = config.db_user
db_pwd = config.db_pwd
db_name = config.db_name
db_port = config.db_port
db_is_docker = config.db_is_docker
db_docker_name = config.db_docker_name
db_backup_dir = config.db_backup_dir
db_backup_maxcount = config.db_backup_maxcount
# 探针
tz_ad = config.tz_ad
tz_api = config.tz_api
tz_id = config.tz_id
tz_version = config.tz_version
tz_username = config.tz_username
tz_password = config.tz_password

w_anti_channel_ids = config.w_anti_channel_ids
kk_gift_days = config.kk_gift_days
fuxx_pitao = config.fuxx_pitao
activity_check_days = config.activity_check_days
red_envelope = config.red_envelope

moviepilot = config.moviepilot
auto_update = config.auto_update
api = config.api
plugin_nav = config.plugin_nav


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


def _adaptive_pyrogram_workers() -> int:
    cpu_count = max(int(os.cpu_count() or 2), 1)
    return min(max(cpu_count * 4, 8), 32)


def _adaptive_pyrogram_transmissions(workers: int) -> int:
    baseline = max(int(workers or 0), 1) * 2
    return min(max(baseline, 32), 96)


def _validate_telegram_credentials():
    issues = []

    normalized_bot_token = str(bot_token or "").strip()
    normalized_owner_hash = str(owner_hash or "").strip().lower()
    if (
        not isinstance(bot_token, str)
        or ":" not in normalized_bot_token
        or normalized_bot_token.startswith("5701:AA")
        or "replace_with" in normalized_bot_token
        or normalized_bot_token.startswith("1234567890:")
    ):
        issues.append("bot_token")

    if not isinstance(owner_api, int) or owner_api <= 0 or owner_api in {73711, 12345678}:
        issues.append("owner_api")

    if (
        not isinstance(owner_hash, str)
        or len(normalized_owner_hash) < 16
        or "replace_with" in normalized_owner_hash
    ):
        issues.append("owner_hash")

    if issues:
        raise RuntimeError(
            "Telegram 凭据未配置完整: "
            + ", ".join(issues)
            + "。Pyrogram 启动本女仆需要 bot_token、owner_api(api_id)、owner_hash(api_hash)。"
            + "请在 data/config.json 中填写 BotFather 提供的 bot_token，"
            + "以及 https://my.telegram.org 获取的 api_id/api_hash。"
        )


_validate_telegram_credentials()
save_config()

# 启动时清理残留的定时注册状态（计时任务已随进程退出而丢失）
if _open.timing > 0:
    LOGGER.warning(f"检测到残留的定时注册状态 timing={_open.timing}，已自动重置")
    _open.timing = 0
    _open.stat = False
    save_config()

configure_runtime_limits()

LOGGER.info("配置文件加载完毕")
from pyrogram.types import BotCommand

'''定义不同等级的人使用不同命令'''
user_p = [
    BotCommand("start", "[私聊] 开启用户面板"),
    BotCommand("myinfo", "[用户] 查看状态"),
    BotCommand("count", "[用户] 媒体库数量"),
    BotCommand("red", "[用户/禁言] 发红包"),
    BotCommand("srank", "[用户/禁言] 查看计分")]

# 取消 BotCommand("exchange", "[私聊] 使用注册码")
admin_p = user_p + [
    BotCommand("kk", "管理用户 [管理]"),
    BotCommand("score", "加/减积分 [管理]"),
    BotCommand("coins", f"加/减{pivkeyu} [管理]"),
    BotCommand("deleted", "清理死号 [管理]"),
    BotCommand("kick_not_emby", "踢出当前群内无号崽 [管理]"),
    BotCommand("renew", "调整到期时间 [管理]"),
    BotCommand("rmemby", "删除用户[包括非tg] [管理]"),
    BotCommand("prouser", "增加白名单 [管理]"),
    BotCommand("revuser", "减少白名单 [管理]"),
    BotCommand("rev_white_channel", "移除皮套人白名单 [管理]"),
    BotCommand("white_channel", "添加皮套人白名单 [管理]"),
    BotCommand("unban_channel", "解封皮套人 [管理]"),
    BotCommand("syncgroupm", "消灭不在群的人 [管理]"),
    BotCommand("syncunbound", "消灭未绑定本女仆的emby账户 [管理]"),
    BotCommand("scan_embyname", "扫描同名的用户记录 [管理]"),
    BotCommand("low_activity", "手动运行活跃检测 [管理]"),
    BotCommand("check_ex", "手动到期检测 [管理]"),
    BotCommand("uranks", "召唤观影时长榜，失效时用 [管理]"),
    BotCommand("days_ranks", "召唤播放次数日榜，失效时用 [管理]"),
    BotCommand("week_ranks", "召唤播放次数周榜，失效时用 [管理]"),
    BotCommand("embyadmin", "开启emby控制台权限 [管理]"),
    BotCommand("ucr", "私聊创建非tg的emby用户 [管理]"),
    BotCommand("uinfo", "查询指定用户名 [管理]"),
    BotCommand("urm", "删除指定用户名 [管理]"),
    BotCommand("userip", "查询指定用户播放过的设备&ip [管理]"),
    BotCommand("udeviceid", "查询指定设备ID [管理]"),
    BotCommand("auditip", "根据IP地址审计用户活动 [管理]"),
    BotCommand("auditdevice", "根据设备名审计用户 [管理]"),
    BotCommand("auditclient", "根据客户端名审计用户 [管理]"),
    BotCommand("renewall", "一键派送天数给所有未封禁的用户 [管理]"),
    BotCommand("coinsall", "一键派送片刻碎片给指定等级的用户 [管理]"),
    BotCommand("coinsclear", "一键清除所有用户的片刻碎片 [管理]"),
    BotCommand("callall", "群发消息给每个人 [管理]"),
    BotCommand("only_rm_emby", "删除指定的Emby账号 [管理]"),
    BotCommand("only_rm_record", "删除指定的tgid数据库记录 [管理]"),
    BotCommand("mute", "禁言/解除禁言群成员 [管理]"),
    BotCommand("kick", "踢出群成员 [管理]"),
    BotCommand("settitle", "设置管理员头衔 [管理]"),
    BotCommand("pin", "置顶群消息 [管理]"),
    BotCommand("unpin", "取消置顶消息 [管理]"),
    BotCommand("warn", "警告群成员并累计次数 [管理]"),
    BotCommand("clearwarn", "清空群成员警告 [管理]"),
    BotCommand("warnconfig", "设置当前群警告阈值与处罚 [管理]"),
    BotCommand("restart", "重启本女仆 [管理]"),
    BotCommand("update_bot", "更新本女仆 [管理]"),
]

owner_p = admin_p + [
    BotCommand("proadmin", "添加本女仆管理 [owner]"),
    BotCommand("revadmin", "移除本女仆管理 [owner]"),
    BotCommand("bindall_id", "一键更新用户们Embyid [owner]"),
    BotCommand("backup_db", "手动备份数据库[owner]"),
    BotCommand("unbanall", "解除所有用户的禁用状态 [owner]"),
    BotCommand("banall", "禁用所有用户 [owner]"),
    BotCommand("paolu", "跑路!!!删除所有用户 [owner]"),
    BotCommand('restore_from_db', '恢复Emby账户[owner]'),
    BotCommand("config", "开启本女仆高级控制面板 [owner]"),
    BotCommand("embylibs_unblockall", "一键开启所有用户的媒体库 [owner]"),
    BotCommand("embylibs_blockall", "一键关闭所有用户的媒体库 [owner]")
]
if len(extra_emby_libs) > 0:
    owner_p += [BotCommand("extraembylibs_blockall", "一键关闭所有用户的额外媒体库 [owner]"),
                BotCommand("extraembylibs_unblockall", "一键开启所有用户的额外媒体库 [owner]")]

with contextlib.suppress(ImportError):
    import uvloop

    uvloop.install()
from pyrogram import enums
from pyromod import Client

proxy = {} if not config.proxy.scheme else config.proxy.dict()
session_dir = Path("data/session")
session_dir.mkdir(parents=True, exist_ok=True)
pyrogram_workers = _env_int("PIVKEYU_PYROGRAM_WORKERS", _adaptive_pyrogram_workers(), 1)
pyrogram_max_concurrent_transmissions = _env_int(
    "PIVKEYU_PYROGRAM_MAX_CONCURRENT_TRANSMISSIONS",
    _adaptive_pyrogram_transmissions(pyrogram_workers),
    1,
)
LOGGER.info(
    f"Pyrogram 运行参数 workers={pyrogram_workers} "
    f"max_concurrent_transmissions={pyrogram_max_concurrent_transmissions}"
)

bot = Client(bot_name, api_id=owner_api, api_hash=owner_hash, bot_token=bot_token, proxy=proxy,
             workdir=str(session_dir),
             workers=pyrogram_workers,
             max_concurrent_transmissions=pyrogram_max_concurrent_transmissions, parse_mode=enums.ParseMode.MARKDOWN)


LOGGER.info("Clinet 客户端准备")
