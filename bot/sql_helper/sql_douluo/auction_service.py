"""拍卖会(领域玩法):上架、竞价、到期结算。"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from bot.sql_helper import Session
from bot.sql_helper.sql_douluo.models import DouluoAuctionListing, DouluoJournal, DouluoProfile, utcnow
from bot.sql_helper.sql_douluo.service import (
    _consume_inventory_item_session,
    _grant_inventory_item_session,
    _load_profile,
    get_settings,
)

TRADABLE_CATEGORIES = {"soulbone", "ambush", "material"}
LOGGER = logging.getLogger(__name__)


def _serialize_listing(row: DouluoAuctionListing) -> dict[str, Any]:
    bids = row.bids if isinstance(row.bids, dict) else {}
    history = bids.get("history", []) if isinstance(bids, dict) else []
    return {
        "id": int(row.id),
        "seller_tg": int(row.seller_tg),
        "item_key": row.item_key,
        "item_name": row.item_name,
        "category": row.category,
        "rarity": row.rarity,
        "start_price": int(row.start_price or 0),
        "current_bid": int(row.current_bid or 0),
        "bidder_tg": int(row.bidder_tg) if row.bidder_tg else None,
        "bidder_display": row.bidder_display,
        "ends_at": row.ends_at,
        "status": row.status,
        "bid_count": len(history),
    }


def list_auction_listings(tg: int | None = None, *, status: str = "open") -> list[dict[str, Any]]:
    settle_expired_auctions()
    with Session() as session:
        query = session.query(DouluoAuctionListing).filter(DouluoAuctionListing.status == str(status or "open"))
        rows = query.order_by(DouluoAuctionListing.ends_at.asc()).limit(50).all()
        items = [_serialize_listing(row) for row in rows]
    if tg is not None:
        for item in items:
            item["is_mine"] = int(item["seller_tg"]) == int(tg)
            item["is_high_bidder"] = int(item.get("bidder_tg") or 0) == int(tg) and bool(item.get("bidder_tg"))
    return items


def place_auction_listing(tg: int, item_key: str, price: int, duration_hours: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    tg = int(tg)
    price = max(int(price or 0), 0)
    if price <= 0:
        raise ValueError("上架价格必须大于 0")
    item_key = str(item_key or "").strip()
    fee_percent = min(max(int(settings.get("auction_fee_percent") or 5), 0), 50)
    duration_hours = max(int(duration_hours or 0), 1) if duration_hours else max(int(settings.get("auction_duration_hours") or 12), 1)
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        from bot.sql_helper.sql_douluo.models import DouluoInventoryItem, DouluoItemDefinition

        row = (
            session.query(DouluoInventoryItem)
            .filter(DouluoInventoryItem.tg == tg, DouluoInventoryItem.item_key == item_key)
            .with_for_update()
            .first()
        )
        if row is None or int(row.quantity or 0) <= 0:
            raise ValueError("背包中没有该物品")
        definition = session.query(DouluoItemDefinition).filter(DouluoItemDefinition.item_key == item_key).first()
        if definition is None:
            raise ValueError("物品不存在")
        if not bool(definition.enabled):
            raise ValueError("该物品当前已停用，不能上架")
        if str(definition.category) not in TRADABLE_CATEGORIES:
            raise ValueError("该物品不可上架拍卖")
        if row.equipped_slot:
            raise ValueError("已装备的物品请先卸下")
        fee = int(math.ceil(price * fee_percent / 100.0))
        if int(profile.coin or 0) < fee:
            raise ValueError(f"上架手续费 {fee} 金魂币不足")
        profile.coin = int(profile.coin or 0) - fee
        profile.updated_at = utcnow()
        _consume_inventory_item_session(session, tg, item_key, 1)
        listing = DouluoAuctionListing(
            seller_tg=tg,
            item_key=item_key,
            item_name=definition.name,
            category=definition.category,
            rarity=definition.rarity,
            start_price=price,
            current_bid=price,
            fee_paid=fee,
            ends_at=utcnow() + timedelta(hours=duration_hours),
            status="open",
            bids={
                "_meta": {
                    "attack": int(definition.attack or 0),
                    "defense": int(definition.defense or 0),
                    "speed": int(definition.speed or 0),
                    "spirit": int(definition.spirit or 0),
                    "trigger_chance": definition.trigger_chance,
                    "skill": definition.skill,
                    "equipment_slot": definition.equipment_slot,
                },
                "history": [],
            },
        )
        session.add(listing)
        session.add(DouluoJournal(tg=tg, action_type="auction", title="拍卖上架", detail=f"上架 {definition.name},起拍价 {price}"))
        session.commit()
        session.refresh(listing)
        serialized = _serialize_listing(listing)
    try:
        from bot.sql_helper.sql_douluo.daily_service import report_task_progress

        report_task_progress(tg, "auction", 1)
    except Exception:
        pass
    return {"listing": serialized, "fee": fee, "coin": int(profile.coin or 0)}


def place_auction_bid(tg: int, listing_id: int, price: int) -> dict[str, Any]:
    tg = int(tg)
    price = max(int(price or 0), 0)
    with Session() as session:
        profile = _load_profile(session, tg, for_update=True)
        listing = (
            session.query(DouluoAuctionListing)
            .filter(DouluoAuctionListing.id == int(listing_id))
            .with_for_update()
            .first()
        )
        if listing is None or listing.status != "open":
            raise ValueError("拍卖单不存在或已结束")
        if int(listing.seller_tg) == tg:
            raise ValueError("不能竞价自己上架的商品")
        if listing.ends_at <= utcnow():
            raise ValueError("拍卖已结束")
        current = int(listing.current_bid or 0)
        increment = max(int(math.ceil(current * 0.05)), 10)
        if price < current + increment:
            raise ValueError(f"出价需至少 {current + increment} 金魂币")
        previous_bidder = int(listing.bidder_tg) if listing.bidder_tg else None
        # 当前最高出价者继续加价时，旧出价已经在托管中，只需补足差额。
        required_funds = price - current if previous_bidder == tg else price
        if int(profile.coin or 0) < required_funds:
            raise ValueError("金魂币不足")
        profile.coin = int(profile.coin or 0) - required_funds
        profile.updated_at = utcnow()
        # 新竞拍者接替最高价时，退还上一出价者已经托管的完整金额。
        if previous_bidder and previous_bidder != tg:
            prev_profile = session.query(DouluoProfile).filter(DouluoProfile.tg == previous_bidder).with_for_update().first()
            if prev_profile is None:
                raise ValueError("上一出价者账户不存在，暂时无法继续竞价")
            prev_profile.coin = int(prev_profile.coin or 0) + current
            prev_profile.updated_at = utcnow()
        # JSON 字段使用新对象赋值，确保 SQLAlchemy 能检测到历史记录变化。
        bids = dict(listing.bids) if isinstance(listing.bids, dict) else {}
        history = list(bids.get("history", []))
        history.append({"tg": tg, "price": price, "at": utcnow().isoformat()})
        bids["history"] = history[-20:]
        listing.bids = bids
        listing.current_bid = price
        listing.bidder_tg = tg
        listing.bidder_display = str(profile.display_name or profile.username or f"魂师{tg}")
        listing.updated_at = utcnow()
        session.commit()
        session.refresh(listing)
        serialized = _serialize_listing(listing)
    try:
        from bot.sql_helper.sql_douluo.daily_service import report_task_progress

        report_task_progress(tg, "auction", 1)
    except Exception:
        pass
    return {"listing": serialized, "coin": int(profile.coin or 0)}


def _settle_expired_auction(listing_id: int, now: datetime) -> bool:
    """在独立事务中结算一条拍卖，失败不会影响其他拍卖。"""
    with Session() as session:
        listing = (
            session.query(DouluoAuctionListing)
            .filter(
                DouluoAuctionListing.id == int(listing_id),
                DouluoAuctionListing.status == "open",
                DouluoAuctionListing.ends_at <= now,
            )
            .with_for_update()
            .first()
        )
        if listing is None:
            return False
        bids = listing.bids if isinstance(listing.bids, dict) else {}
        meta = bids.get("_meta", {}) if isinstance(bids, dict) else {}
        buyer_tg = int(listing.bidder_tg) if listing.bidder_tg else None
        if buyer_tg:
            granted = _grant_inventory_item_session(
                session,
                buyer_tg,
                listing.item_key,
                1,
                meta=meta,
                allow_disabled=True,
            )
            seller = (
                session.query(DouluoProfile)
                .filter(DouluoProfile.tg == int(listing.seller_tg))
                .with_for_update()
                .first()
            )
            if granted is None:
                raise RuntimeError(f"拍卖物品 {listing.item_key} 无法发放，结算已回滚")
            if seller is None:
                raise RuntimeError(f"卖家 {listing.seller_tg} 不存在，结算已回滚")
            seller.coin = int(seller.coin or 0) + int(listing.current_bid or 0)
            seller.updated_at = utcnow()
            listing.status = "sold"
            session.add(
                DouluoJournal(
                    tg=int(listing.seller_tg),
                    action_type="auction",
                    title="拍卖成交",
                    detail=f"{listing.item_name} 以 {listing.current_bid} 金魂币成交",
                )
            )
            session.add(
                DouluoJournal(
                    tg=buyer_tg,
                    action_type="auction",
                    title="竞得物品",
                    detail=f"竞得 {listing.item_name}({listing.current_bid} 金魂币)",
                )
            )
        else:
            returned = _grant_inventory_item_session(
                session,
                int(listing.seller_tg),
                listing.item_key,
                1,
                meta=meta,
                allow_disabled=True,
            )
            if returned is None:
                raise RuntimeError(f"流拍物品 {listing.item_key} 无法退回，结算已回滚")
            listing.status = "expired"
            session.add(
                DouluoJournal(
                    tg=int(listing.seller_tg),
                    action_type="auction",
                    title="拍卖流拍",
                    detail=f"{listing.item_name} 流拍,物品已退回",
                )
            )
        listing.updated_at = utcnow()
        session.commit()
    return True


def settle_expired_auctions(max_batch: int = 100) -> int:
    now = utcnow()
    batch_size = max(min(int(max_batch or 100), 500), 1)
    with Session() as session:
        candidates = (
            session.query(DouluoAuctionListing)
            .filter(DouluoAuctionListing.status == "open", DouluoAuctionListing.ends_at <= now)
            .order_by(DouluoAuctionListing.id.asc())
            .limit(batch_size)
            .all()
        )
        listing_ids = [int(row.id) for row in candidates]

    settled = 0
    for listing_id in listing_ids:
        try:
            settled += int(_settle_expired_auction(listing_id, now))
        except Exception as exc:
            LOGGER.exception("Failed to settle douluo auction listing_id=%s: %s", listing_id, exc)
    return settled


def my_listings(tg: int) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(DouluoAuctionListing)
            .filter(DouluoAuctionListing.seller_tg == int(tg))
            .order_by(DouluoAuctionListing.created_at.desc())
            .limit(20)
            .all()
        )
        return [_serialize_listing(row) for row in rows]
