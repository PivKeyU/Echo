from __future__ import annotations

from bot import LOGGER
from bot.sql_helper import Session
from bot.sql_helper.sql_emby import Emby, sql_get_emby
from bot.sql_helper.sql_xiuxian import (
    XiuxianProfile,
    apply_spiritual_stone_delta,
    assert_currency_operation_allowed,
    create_journal,
    get_shared_spiritual_stone_total,
    get_xiuxian_settings,
)


def get_emby_balance(tg: int) -> int:
    user = sql_get_emby(tg)
    return 0 if user is None else int(user.iv or 0)


def add_emby_balance(tg: int, amount: int) -> int:
    delta = int(amount)
    with Session() as session:
        user = session.query(Emby).filter(Emby.tg == tg).with_for_update().first()
        if user is None:
            raise ValueError("Emby 账号不存在")
        new_balance = int(user.iv or 0) + delta
        if new_balance < 0:
            raise ValueError("片刻碎片不足")
        user.iv = new_balance
        session.commit()
        return new_balance


def get_exchange_settings() -> dict:
    settings = get_xiuxian_settings()
    rate = max(int(settings.get("coin_exchange_rate", 100) or 100), 1)
    return {
        "enabled": bool(settings.get("coin_stone_exchange_enabled", True)),
        "rate": rate,
        "fee_percent": 0,
        "min_coin_exchange": rate,
        "stone_to_coin_min_stone": rate,
    }


def _remember_exchange_journal(tg: int, title: str, detail: str) -> None:
    try:
        create_journal(tg, "exchange", title, detail)
    except Exception as exc:
        LOGGER.warning(f"exchange journal write failed: tg={tg}, title={title}, error={exc}")


def preview_coin_to_stone(coin_amount: int) -> dict:
    settings = get_exchange_settings()
    gross_stone = max(int(coin_amount or 0), 0) * settings["rate"]
    return {
        "direction": "coin_to_stone",
        "gross": gross_stone,
        "fee": 0,
        "net": gross_stone,
        "settings": settings,
    }


def preview_stone_to_coin(stone_amount: int) -> dict:
    settings = get_exchange_settings()
    requested_stone = max(int(stone_amount or 0), 0)
    gross_coin = requested_stone // settings["rate"]
    spent_stone = gross_coin * settings["rate"]
    return {
        "direction": "stone_to_coin",
        "gross": gross_coin,
        "spent_stone": spent_stone,
        "fee": 0,
        "net": gross_coin,
        "remainder_stone": requested_stone - spent_stone,
        "fee_free_applied": False,
        "settings": settings,
    }


def convert_coin_to_stone(tg: int, coin_amount: int) -> dict:
    amount = max(int(coin_amount), 0)
    if amount <= 0:
        raise ValueError("兑换数量必须大于 0")

    preview = preview_coin_to_stone(amount)
    if not preview["settings"].get("enabled", True):
        raise ValueError("灵石互兑功能当前未开启。")
    if preview["gross"] <= 0 or preview["net"] <= 0:
        raise ValueError("当前比例下可兑换的灵石不足 1")

    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你还没有踏入仙途")
        assert_currency_operation_allowed(tg, "兑换灵石", session=session, profile=profile)
        user = session.query(Emby).filter(Emby.tg == tg).with_for_update().first()
        if user is None:
            raise ValueError("Emby 账号不存在")
        if int(user.iv or 0) < amount:
            raise ValueError("片刻碎片不足")

        user.iv = int(user.iv or 0) - amount
        apply_spiritual_stone_delta(
            session,
            tg,
            int(preview["net"]),
            action_text="兑换灵石",
            enforce_currency_lock=False,
            allow_dead=False,
            apply_tribute=False,
        )
        session.commit()
        new_coin_balance = int(user.iv or 0)
        stone_balance = int(profile.spiritual_stone or 0)
        shared_stone_balance = int(get_shared_spiritual_stone_total(tg, session=session, for_update=False) or 0)
    _remember_exchange_journal(
        tg,
        "碎片兑换灵石",
        (
            f"消耗 {amount} 片刻碎片，获得 {int(preview['net'])} 灵石。"
            f"当前灵石 {shared_stone_balance}，片刻碎片 {new_coin_balance}。"
        ),
    )
    return {
        "spent_coin": amount,
        "received_stone": preview["net"],
        "gross_stone": preview["gross"],
        "emby_balance": new_coin_balance,
        "stone_balance": stone_balance,
        "shared_stone_balance": shared_stone_balance,
        "fee": preview["fee"],
        "rate": preview["settings"]["rate"],
    }


def convert_stone_to_coin(tg: int, stone_amount: int) -> dict:
    amount = max(int(stone_amount), 0)
    if amount <= 0:
        raise ValueError("兑换数量必须大于 0")

    preview = preview_stone_to_coin(amount)
    if not preview["settings"].get("enabled", True):
        raise ValueError("灵石互兑功能当前未开启。")
    minimum_stone = max(int(preview["settings"].get("stone_to_coin_min_stone") or 0), 1)
    if preview["spent_stone"] < minimum_stone:
        raise ValueError(f"最低需要 {minimum_stone} 灵石才能兑换片刻碎片")
    if preview["gross"] <= 0 or preview["net"] <= 0:
        raise ValueError("当前比例下可兑换的片刻碎片不足 1")

    with Session() as session:
        profile = session.query(XiuxianProfile).filter(XiuxianProfile.tg == tg).with_for_update().first()
        if profile is None or not profile.consented:
            raise ValueError("你还没有踏入仙途")
        assert_currency_operation_allowed(tg, "兑换片刻碎片", session=session, profile=profile)
        available_stone = int(get_shared_spiritual_stone_total(tg, session=session, for_update=True) or 0)
        if available_stone < int(preview["spent_stone"]):
            raise ValueError("灵石不足")
        user = session.query(Emby).filter(Emby.tg == tg).with_for_update().first()
        if user is None:
            raise ValueError("Emby 账号不存在")

        apply_spiritual_stone_delta(
            session,
            tg,
            -int(preview["spent_stone"]),
            action_text="兑换片刻碎片",
            enforce_currency_lock=False,
            allow_dead=False,
            apply_tribute=False,
        )
        user.iv = int(user.iv or 0) + int(preview["net"])
        session.commit()
        new_coin_balance = int(user.iv or 0)
        stone_balance = int(profile.spiritual_stone or 0)
        shared_stone_balance = int(get_shared_spiritual_stone_total(tg, session=session, for_update=False) or 0)
    _remember_exchange_journal(
        tg,
        "灵石兑换碎片",
        (
            f"消耗 {int(preview['spent_stone'])} 灵石，获得 {int(preview['net'])} 片刻碎片。"
            f"当前灵石 {shared_stone_balance}，片刻碎片 {new_coin_balance}。"
        ),
    )
    return {
        "spent_stone": preview["spent_stone"],
        "received_coin": preview["net"],
        "gross_coin": preview["gross"],
        "emby_balance": new_coin_balance,
        "stone_balance": stone_balance,
        "shared_stone_balance": shared_stone_balance,
        "fee": preview["fee"],
        "fee_free_applied": bool(preview.get("fee_free_applied")),
        "rate": preview["settings"]["rate"],
    }
