from __future__ import annotations

from bot.sql_helper.sql_emby import Emby


LEVEL_META = {
    "a": {
        "code": "a",
        "text": "白名单用户",
        "short_text": "白名单",
        "description": "主人亲自盖章的小宝贝，享有更稳定线路与更完整的观影体验。",
        "tone": "vip",
    },
    "b": {
        "code": "b",
        "text": "正常用户",
        "short_text": "正常",
        "description": "已领取观影资格的小可爱，可以正常解锁日常观影体验。",
        "tone": "normal",
    },
    "c": {
        "code": "c",
        "text": "已封禁用户",
        "short_text": "已封禁",
        "description": "当前已被禁用，需要主人处理或等待恢复。",
        "tone": "danger",
    },
    "d": {
        "code": "d",
        "text": "未注册用户",
        "short_text": "未注册",
        "description": "仅录入了 Telegram 信息，还没有有效 Emby 账号。",
        "tone": "pending",
    },
}

UNKNOWN_LEVEL_META = {
    "code": "?",
    "text": "未知状态",
    "short_text": "未知",
    "description": "系统未识别这个等级，请检查数据库。",
    "tone": "unknown",
}


def get_level_meta(level: str | None) -> dict:
    return LEVEL_META.get((level or "").lower(), UNKNOWN_LEVEL_META)


def serialize_emby_user(user: Emby) -> dict:
    level_meta = get_level_meta(user.lv)
    return {
        "tg": user.tg,
        "embyid": user.embyid,
        "name": user.name,
        "lv": user.lv,
        "lv_text": level_meta["text"],
        "lv_short_text": level_meta["short_text"],
        "lv_description": level_meta["description"],
        "lv_tone": level_meta["tone"],
        "cr": user.cr.isoformat() if user.cr else None,
        "ex": user.ex.isoformat() if user.ex else None,
        "us": user.us,
        "iv": user.iv,
        "ch": user.ch.isoformat() if user.ch else None,
    }
