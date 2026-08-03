from __future__ import annotations

import copy
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import event
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    or_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from bot.plugins.xiuxian_game import cache as xiuxian_cache
from bot.sql_helper import Base, Session
from bot.sql_helper.sql_emby import Emby
from .constants import *  # noqa: F401 F403
from .models import *  # noqa: F401 F403
from .serializers import *  # noqa: F401 F403
from .profile import *  # noqa: F401 F403
from .items import *  # noqa: F401 F403

def list_shop_items(
    owner_tg: int | None = None,
    official_only: bool | None = None,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    owner_value = int(owner_tg) if owner_tg is not None else "all"
    official_value = "official" if official_only is True else "personal" if official_only is False else "mixed"

    def _loader() -> list[dict[str, Any]]:
        with Session() as session:
            query = session.query(XiuxianShopItem)
            if not include_disabled:
                query = query.filter(XiuxianShopItem.enabled.is_(True))
            if owner_tg is not None:
                query = query.filter(XiuxianShopItem.owner_tg == owner_tg)
            if official_only is True:
                query = query.filter(XiuxianShopItem.is_official.is_(True))
            elif official_only is False:
                query = query.filter(XiuxianShopItem.is_official.is_(False))
            return [serialize_shop_item(item) for item in query.order_by(XiuxianShopItem.id.desc()).all()]

    return xiuxian_cache.load_versioned_json(
        version_parts=("catalog", "shop-items"),
        cache_parts=("catalog", "shop-items", owner_value, official_value, "with-disabled" if include_disabled else "enabled"),
        ttl=xiuxian_cache.USER_VIEW_TTL,
        loader=_loader,
    )


def get_shop_item(item_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(XiuxianShopItem).filter(XiuxianShopItem.id == int(item_id)).first()
        return serialize_shop_item(row)


def create_shop_item(
    *,
    owner_tg: int | None,
    shop_name: str,
    item_kind: str,
    item_ref_id: int,
    item_name: str,
    quantity: int,
    price_stone: int,
    is_official: bool,
) -> dict[str, Any]:
    last_error: IntegrityError | None = None
    for _ in range(2):
        with Session() as session:
            item = XiuxianShopItem(
                owner_tg=owner_tg,
                shop_name=shop_name,
                item_kind=item_kind,
                item_ref_id=item_ref_id,
                item_name=item_name,
                quantity=max(int(quantity), 1),
                price_stone=max(int(price_stone), 1),
                is_official=is_official,
                enabled=True,
            )
            session.add(item)
            _queue_catalog_cache_invalidation(session, "shop-items")
            try:
                session.commit()
            except IntegrityError as exc:
                last_error = exc
                if _recover_shop_item_insert_conflict(session, exc):
                    continue
                raise
            session.refresh(item)
            return serialize_shop_item(item)
    if last_error is not None:
        raise last_error
    raise RuntimeError("create shop item failed unexpectedly")


def sync_official_shop_name(shop_name: str) -> int:
    resolved_name = str(shop_name or "").strip() or DEFAULT_SETTINGS["official_shop_name"]
    with Session() as session:
        rows = session.query(XiuxianShopItem).filter(XiuxianShopItem.is_official.is_(True)).all()
        changed = 0
        for row in rows:
            if row.shop_name == resolved_name:
                continue
            row.shop_name = resolved_name
            row.updated_at = utcnow()
            changed += 1
        if changed > 0:
            _queue_catalog_cache_invalidation(session, "shop-items")
        session.commit()
        return changed


def update_shop_item(item_id: int, **fields) -> dict[str, Any] | None:
    with Session() as session:
        item = session.query(XiuxianShopItem).filter(XiuxianShopItem.id == item_id).first()
        if item is None:
            return None
        for key, value in fields.items():
            setattr(item, key, value)
        item.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "shop-items")
        session.commit()
        session.refresh(item)
        return serialize_shop_item(item)


def _auction_has_bid(item: XiuxianAuctionItem) -> bool:
    return max(int(item.current_price_stone or 0), 0) > 0 and max(int(item.bid_count or 0), 0) > 0


def _auction_next_bid_price(item: XiuxianAuctionItem) -> int:
    opening_price = max(int(item.opening_price_stone or 0), 0)
    current_price = max(int(item.current_price_stone or 0), 0)
    bid_increment = max(int(item.bid_increment_stone or 0), 1)
    return opening_price if not _auction_has_bid(item) else current_price + bid_increment


def _grant_auction_item_to_inventory(
    session: Session,
    *,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    source: str | None = None,
    obtained_note: str | None = None,
    auto_equip_if_empty: bool | None = None,
) -> dict[str, Any] | None:
    amount = max(int(quantity or 0), 0)
    if amount <= 0:
        return None
    normalized_kind = str(item_kind or "").strip()
    normalized_source = str(source or "").strip() or None
    normalized_note = (str(obtained_note or "").strip() or None) if obtained_note is not None else None
    auto_equip = True if auto_equip_if_empty is None else bool(auto_equip_if_empty)

    def _pending_row(model_cls, **keys: int):
        for pending in session.new:
            if not isinstance(pending, model_cls):
                continue
            if all(int(getattr(pending, key, 0) or 0) == int(value) for key, value in keys.items()):
                return pending
        return None

    def _grant_technique_in_session(target_tg: int, technique_id: int) -> dict[str, Any]:
        technique = session.query(XiuxianTechnique).filter(XiuxianTechnique.id == int(technique_id)).first()
        if technique is None:
            raise ValueError("technique not found")
        profile = (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.tg == int(target_tg))
            .with_for_update()
            .first()
        )
        if profile is None:
            profile = XiuxianProfile(tg=int(target_tg))
            session.add(profile)
            session.flush()
        row = _pending_row(XiuxianUserTechnique, tg=int(target_tg), technique_id=int(technique_id))
        if row is None:
            row = (
            session.query(XiuxianUserTechnique)
            .filter(
                XiuxianUserTechnique.tg == int(target_tg),
                XiuxianUserTechnique.technique_id == int(technique_id),
            )
            .with_for_update()
            .first()
            )
        if row is None:
            row = XiuxianUserTechnique(
                tg=int(target_tg),
                technique_id=int(technique_id),
                source=normalized_source or "auction",
                obtained_note=normalized_note if obtained_note is not None else "拍卖所得",
            )
            session.add(row)
        else:
            return grant_duplicate_knowledge_compensation_in_session(
                session,
                int(target_tg),
                "technique",
                technique,
                action_text="重复功法折算灵石",
            )
        if auto_equip and not profile.current_technique_id:
            profile.current_technique_id = int(technique_id)
            profile.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, int(target_tg))
        _queue_user_view_cache_invalidation(session, int(target_tg))
        return serialize_user_technique(row, serialize_technique(technique))

    def _grant_recipe_in_session(target_tg: int, recipe_id: int) -> dict[str, Any]:
        recipe = session.query(XiuxianRecipe).filter(XiuxianRecipe.id == int(recipe_id)).first()
        if recipe is None:
            raise ValueError("recipe not found")
        row = _pending_row(XiuxianUserRecipe, tg=int(target_tg), recipe_id=int(recipe_id))
        if row is None:
            row = (
            session.query(XiuxianUserRecipe)
            .filter(
                XiuxianUserRecipe.tg == int(target_tg),
                XiuxianUserRecipe.recipe_id == int(recipe_id),
            )
            .with_for_update()
            .first()
            )
        if row is None:
            row = XiuxianUserRecipe(
                tg=int(target_tg),
                recipe_id=int(recipe_id),
                source=normalized_source or "auction",
                obtained_note=normalized_note if obtained_note is not None else "拍卖所得",
            )
            session.add(row)
        else:
            return grant_duplicate_knowledge_compensation_in_session(
                session,
                int(target_tg),
                "recipe",
                recipe,
                action_text="重复丹谱折算灵石",
            )
        _queue_user_view_cache_invalidation(session, int(target_tg))
        return serialize_user_recipe(row, serialize_recipe(recipe))

    if normalized_kind == "artifact":
        artifact, row, _ = _grant_artifact_inventory_in_session(
            session,
            int(tg),
            int(item_ref_id),
            amount,
            reject_if_owned=False,
            strict_quantity=False,
        )
        _queue_user_view_cache_invalidation(session, int(tg))
        return {
            "artifact": serialize_artifact(artifact),
            "quantity": max(int(row.quantity or 0), 0),
            "bound_quantity": int(row.bound_quantity or 0),
        }

    if normalized_kind == "pill":
        row = _pending_row(XiuxianPillInventory, tg=int(tg), pill_id=int(item_ref_id))
        if row is None:
            row = (
            session.query(XiuxianPillInventory)
            .filter(
                XiuxianPillInventory.tg == int(tg),
                XiuxianPillInventory.pill_id == int(item_ref_id),
            )
            .with_for_update()
            .first()
            )
        if row is None:
            row = XiuxianPillInventory(tg=int(tg), pill_id=int(item_ref_id), quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, int(tg))
        pill = session.query(XiuxianPill).filter(XiuxianPill.id == int(item_ref_id)).first()
        return {
            "pill": serialize_pill(pill),
            "quantity": int(row.quantity or 0),
        }

    if normalized_kind == "talisman":
        row = _pending_row(XiuxianTalismanInventory, tg=int(tg), talisman_id=int(item_ref_id))
        if row is None:
            row = (
            session.query(XiuxianTalismanInventory)
            .filter(
                XiuxianTalismanInventory.tg == int(tg),
                XiuxianTalismanInventory.talisman_id == int(item_ref_id),
            )
            .with_for_update()
            .first()
            )
        if row is None:
            row = XiuxianTalismanInventory(tg=int(tg), talisman_id=int(item_ref_id), quantity=0, bound_quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.bound_quantity = max(min(int(row.bound_quantity or 0), int(row.quantity or 0)), 0)
        row.updated_at = utcnow()
        _queue_profile_cache_invalidation(session, int(tg))
        _queue_user_view_cache_invalidation(session, int(tg))
        talisman = session.query(XiuxianTalisman).filter(XiuxianTalisman.id == int(item_ref_id)).first()
        return {
            "talisman": serialize_talisman(talisman),
            "quantity": int(row.quantity or 0),
            "bound_quantity": int(row.bound_quantity or 0),
        }

    if normalized_kind == "material":
        row = _pending_row(XiuxianMaterialInventory, tg=int(tg), material_id=int(item_ref_id))
        if row is None:
            row = (
            session.query(XiuxianMaterialInventory)
            .filter(
                XiuxianMaterialInventory.tg == int(tg),
                XiuxianMaterialInventory.material_id == int(item_ref_id),
            )
            .with_for_update()
            .first()
            )
        if row is None:
            row = XiuxianMaterialInventory(tg=int(tg), material_id=int(item_ref_id), quantity=0)
            session.add(row)
        row.quantity = int(row.quantity or 0) + amount
        row.updated_at = utcnow()
        _queue_user_view_cache_invalidation(session, int(tg))
        material = session.query(XiuxianMaterial).filter(XiuxianMaterial.id == int(item_ref_id)).first()
        return {
            "material": serialize_material(material),
            "quantity": int(row.quantity or 0),
        }

    if normalized_kind == "technique":
        return _grant_technique_in_session(int(tg), int(item_ref_id))

    if normalized_kind == "recipe":
        return _grant_recipe_in_session(int(tg), int(item_ref_id))

    raise ValueError("不支持的物品类型")


def list_auction_items(
    owner_tg: int | None = None,
    *,
    status: str | None = None,
    include_inactive: bool = False,
    exclude_owner_tg: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    with Session() as session:
        query = session.query(XiuxianAuctionItem)
        if owner_tg is not None:
            query = query.filter(XiuxianAuctionItem.owner_tg == int(owner_tg))
        if exclude_owner_tg is not None:
            query = query.filter(XiuxianAuctionItem.owner_tg != int(exclude_owner_tg))
        if status:
            query = query.filter(XiuxianAuctionItem.status == str(status))
        elif not include_inactive:
            query = query.filter(XiuxianAuctionItem.status == "active")
        query = query.order_by(XiuxianAuctionItem.id.desc())
        if limit is not None:
            query = query.limit(max(int(limit or 0), 1))
        return [serialize_auction_item(item) for item in query.all()]


def get_auction_item(auction_id: int) -> dict[str, Any] | None:
    with Session() as session:
        row = session.query(XiuxianAuctionItem).filter(XiuxianAuctionItem.id == int(auction_id)).first()
        return serialize_auction_item(row)


def create_auction_item(
    *,
    owner_tg: int,
    owner_display_name: str,
    item_kind: str,
    item_ref_id: int,
    item_name: str,
    quantity: int,
    opening_price_stone: int,
    bid_increment_stone: int,
    buyout_price_stone: int | None,
    fee_percent: int,
    end_at: datetime,
    group_chat_id: int | None = None,
    group_message_id: int | None = None,
) -> dict[str, Any]:
    opening_price = max(int(opening_price_stone or 0), 0)
    bid_increment = max(int(bid_increment_stone or 0), 1)
    buyout_price = max(int(buyout_price_stone or 0), 0) or None
    if buyout_price is not None and buyout_price < opening_price:
        raise ValueError("一口价不能低于起拍价")

    with Session() as session:
        item = XiuxianAuctionItem(
            owner_tg=int(owner_tg),
            owner_display_name=str(owner_display_name or "").strip(),
            item_kind=str(item_kind or "").strip(),
            item_ref_id=int(item_ref_id),
            item_name=str(item_name or "").strip(),
            quantity=max(int(quantity or 0), 1),
            opening_price_stone=opening_price,
            current_price_stone=0,
            bid_increment_stone=bid_increment,
            buyout_price_stone=buyout_price,
            fee_percent=max(int(fee_percent or 0), 0),
            status="active",
            group_chat_id=int(group_chat_id) if group_chat_id is not None else None,
            group_message_id=int(group_message_id) if group_message_id is not None else None,
            end_at=end_at,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return serialize_auction_item(item)


def update_auction_item(auction_id: int, **fields) -> dict[str, Any] | None:
    with Session() as session:
        item = session.query(XiuxianAuctionItem).filter(XiuxianAuctionItem.id == int(auction_id)).first()
        if item is None:
            return None
        for key, value in fields.items():
            if not hasattr(item, key):
                continue
            setattr(item, key, value)
        item.updated_at = utcnow()
        session.commit()
        session.refresh(item)
        return serialize_auction_item(item)


def list_auction_bids(auction_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    with Session() as session:
        rows = (
            session.query(XiuxianAuctionBid)
            .filter(XiuxianAuctionBid.auction_id == int(auction_id))
            .order_by(XiuxianAuctionBid.id.desc())
            .limit(max(int(limit or 50), 1))
            .all()
        )
        return [serialize_auction_bid(item) for item in rows]


def _settle_auction_row(session: Session, auction: XiuxianAuctionItem) -> dict[str, Any]:
    now = utcnow()
    current_price = max(int(auction.current_price_stone or 0), 0)
    fee_percent = max(int(auction.fee_percent or 0), 0)
    has_bid = _auction_has_bid(auction)

    auction.updated_at = now
    auction.completed_at = now

    if not has_bid:
        returned_item = _grant_auction_item_to_inventory(
            session,
            tg=int(auction.owner_tg),
            item_kind=str(auction.item_kind or ""),
            item_ref_id=int(auction.item_ref_id),
            quantity=int(auction.quantity or 0),
            source="auction_expired",
            obtained_note="拍卖流拍返还",
        )
        auction.status = "expired"
        auction.winner_tg = None
        auction.winner_display_name = None
        auction.final_price_stone = 0
        auction.seller_income_stone = 0
        auction.fee_amount_stone = 0
        return {
            "result": "expired",
            "auction": serialize_auction_item(auction),
            "winner_tg": None,
            "winner_display_name": None,
            "seller_tg": int(auction.owner_tg),
            "returned_item": returned_item,
            "returned_quantity": max(int(auction.quantity or 0), 0),
        }

    fee_amount = current_price * fee_percent // 100
    seller_income = max(current_price - fee_amount, 0)

    winner_tg = int(auction.highest_bidder_tg or 0)
    if winner_tg <= 0:
        raise ValueError("拍卖状态异常，缺少最高出价者")
    if (
        str(auction.item_kind or "") == "technique"
        and session.query(XiuxianUserTechnique)
        .filter(
            XiuxianUserTechnique.tg == winner_tg,
            XiuxianUserTechnique.technique_id == int(auction.item_ref_id or 0),
        )
        .first()
        is not None
    ):
        bidder = (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.tg == winner_tg)
            .with_for_update()
            .first()
        )
        if bidder is not None and current_price > 0:
            apply_spiritual_stone_delta(
                session,
                winner_tg,
                current_price,
                action_text="拍卖结算失败返还灵石",
                allow_dead=True,
                apply_tribute=False,
            )
        returned_item = _grant_auction_item_to_inventory(
            session,
            tg=int(auction.owner_tg),
            item_kind=str(auction.item_kind or ""),
            item_ref_id=int(auction.item_ref_id),
            quantity=int(auction.quantity or 0),
            source="auction_cancelled",
            obtained_note="拍卖结算取消返还",
        )
        auction.status = "cancelled"
        auction.winner_tg = None
        auction.winner_display_name = None
        auction.final_price_stone = 0
        auction.seller_income_stone = 0
        auction.fee_amount_stone = 0
        auction.highest_bidder_tg = None
        auction.highest_bidder_display_name = None
        auction.current_price_stone = 0
        return {
            "result": "cancelled",
            "auction": serialize_auction_item(auction),
            "winner_tg": None,
            "winner_display_name": None,
            "seller_tg": int(auction.owner_tg),
            "returned_item": returned_item,
            "returned_quantity": max(int(auction.quantity or 0), 0),
        }

    seller = (
        session.query(XiuxianProfile)
        .filter(XiuxianProfile.tg == int(auction.owner_tg))
        .with_for_update()
        .first()
    )
    if seller is not None and seller_income > 0:
        apply_spiritual_stone_delta(
            session,
            int(auction.owner_tg),
            seller_income,
            action_text="拍卖成交入账",
            allow_dead=True,
            apply_tribute=False,
        )

    _grant_auction_item_to_inventory(
        session,
        tg=winner_tg,
        item_kind=str(auction.item_kind or ""),
        item_ref_id=int(auction.item_ref_id),
        quantity=int(auction.quantity or 0),
    )

    auction.status = "sold"
    auction.winner_tg = winner_tg
    auction.winner_display_name = str(auction.highest_bidder_display_name or "").strip() or None
    auction.final_price_stone = current_price
    auction.seller_income_stone = seller_income
    auction.fee_amount_stone = fee_amount

    return {
        "result": "sold",
        "auction": serialize_auction_item(auction),
        "winner_tg": winner_tg,
        "winner_display_name": auction.winner_display_name or "",
        "seller_tg": int(auction.owner_tg),
        "seller_income_stone": seller_income,
        "fee_amount_stone": fee_amount,
    }


def finalize_auction_item(auction_id: int, *, force: bool = False) -> dict[str, Any] | None:
    with Session() as session:
        auction = (
            session.query(XiuxianAuctionItem)
            .filter(XiuxianAuctionItem.id == int(auction_id))
            .with_for_update()
            .first()
        )
        if auction is None:
            return None
        if str(auction.status or "") != "active":
            return {
                "result": "noop",
                "auction": serialize_auction_item(auction),
                "winner_tg": int(auction.winner_tg or 0) or None,
                "winner_display_name": str(auction.winner_display_name or ""),
                "seller_tg": int(auction.owner_tg or 0) or None,
            }
        if not force and auction.end_at > utcnow():
            raise ValueError("拍卖尚未结束")
        payload = _settle_auction_row(session, auction)
        session.commit()
        return payload


def cancel_auction_item(auction_id: int, *, owner_tg: int | None = None) -> dict[str, Any] | None:
    with Session() as session:
        auction = (
            session.query(XiuxianAuctionItem)
            .filter(XiuxianAuctionItem.id == int(auction_id))
            .with_for_update()
            .first()
        )
        if auction is None:
            return None
        if owner_tg is not None and int(auction.owner_tg or 0) != int(owner_tg):
            raise ValueError("你无权取消这场拍卖")
        if str(auction.status or "") != "active":
            return {
                "result": "noop",
                "auction": serialize_auction_item(auction),
            }

        now = utcnow()
        current_price = max(int(auction.current_price_stone or 0), 0)
        current_bidder_tg = int(auction.highest_bidder_tg or 0)
        if current_bidder_tg > 0 and current_price > 0:
            bidder = (
                session.query(XiuxianProfile)
                .filter(XiuxianProfile.tg == current_bidder_tg)
                .with_for_update()
                .first()
            )
            if bidder is not None:
                apply_spiritual_stone_delta(
                    session,
                    current_bidder_tg,
                    current_price,
                    action_text="拍卖撤销返还灵石",
                    allow_dead=True,
                    apply_tribute=False,
                )

        returned_item = _grant_auction_item_to_inventory(
            session,
            tg=int(auction.owner_tg),
            item_kind=str(auction.item_kind or ""),
            item_ref_id=int(auction.item_ref_id),
            quantity=int(auction.quantity or 0),
            source="auction_cancelled",
            obtained_note="取消拍卖返还",
        )

        auction.status = "cancelled"
        auction.updated_at = now
        auction.completed_at = now
        auction.final_price_stone = 0
        auction.seller_income_stone = 0
        auction.fee_amount_stone = 0
        auction.winner_tg = None
        auction.winner_display_name = None

        session.commit()
        return {
            "result": "cancelled",
            "auction": serialize_auction_item(auction),
            "refunded_bidder_tg": current_bidder_tg or None,
            "returned_item": returned_item,
            "returned_quantity": max(int(auction.quantity or 0), 0),
        }


def place_auction_bid(
    auction_id: int,
    *,
    bidder_tg: int,
    bidder_display_name: str = "",
    use_buyout: bool = False,
) -> dict[str, Any]:
    with Session() as session:
        auction = (
            session.query(XiuxianAuctionItem)
            .filter(XiuxianAuctionItem.id == int(auction_id))
            .with_for_update()
            .first()
        )
        if auction is None:
            raise ValueError("拍卖不存在")
        if str(auction.status or "") != "active":
            raise ValueError("拍卖已经结束")
        if auction.end_at <= utcnow():
            raise ValueError("拍卖已经结束")
        if int(auction.owner_tg or 0) == int(bidder_tg):
            raise ValueError("不能给自己发起的拍卖加价")
        if (
            str(auction.item_kind or "") == "technique"
            and session.query(XiuxianUserTechnique)
            .filter(
                XiuxianUserTechnique.tg == int(bidder_tg),
                XiuxianUserTechnique.technique_id == int(auction.item_ref_id or 0),
            )
            .first()
            is not None
        ):
            raise ValueError("你已经掌握这门功法，无法重复竞拍。")

        current_bidder_tg = int(auction.highest_bidder_tg or 0)
        current_price = max(int(auction.current_price_stone or 0), 0)
        buyout_price = max(int(auction.buyout_price_stone or 0), 0)
        next_price = _auction_next_bid_price(auction)
        is_buyout = bool(use_buyout)
        if is_buyout:
            if buyout_price <= 0:
                raise ValueError("这场拍卖没有设置一口价")
            next_price = buyout_price
        elif buyout_price > 0 and next_price >= buyout_price:
            next_price = buyout_price
            is_buyout = True

        bidder = (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.tg == int(bidder_tg))
            .with_for_update()
            .first()
        )
        if bidder is None or not bidder.consented:
            raise ValueError("你还没有踏入仙途")

        now = utcnow()
        bidder_name = str(bidder_display_name or "").strip()
        bid_action = "buyout" if is_buyout else "bid"

        if current_bidder_tg == int(bidder_tg):
            if not is_buyout:
                raise ValueError("你已经是当前领先者，无需重复加价")
            additional_cost = max(next_price - current_price, 0)
            if additional_cost <= 0:
                raise ValueError("当前价格已经达到一口价")
            if get_shared_spiritual_stone_total(int(bidder_tg), session=session, for_update=True) < additional_cost:
                raise ValueError("灵石不足，无法完成一口价")
            apply_spiritual_stone_delta(
                session,
                int(bidder_tg),
                -additional_cost,
                action_text="拍卖一口价补差",
                allow_dead=False,
                apply_tribute=False,
            )
        else:
            if get_shared_spiritual_stone_total(int(bidder_tg), session=session, for_update=True) < next_price:
                raise ValueError("灵石不足，无法完成出价")
            apply_spiritual_stone_delta(
                session,
                int(bidder_tg),
                -next_price,
                action_text="拍卖出价",
                allow_dead=False,
                apply_tribute=False,
            )
            if current_bidder_tg > 0 and current_price > 0:
                previous_bidder = (
                    session.query(XiuxianProfile)
                    .filter(XiuxianProfile.tg == current_bidder_tg)
                    .with_for_update()
                    .first()
                )
                if previous_bidder is not None:
                    apply_spiritual_stone_delta(
                        session,
                        current_bidder_tg,
                        current_price,
                        action_text="拍卖退还出价",
                        allow_dead=True,
                        apply_tribute=False,
                    )

        auction.current_price_stone = next_price
        auction.highest_bidder_tg = int(bidder_tg)
        auction.highest_bidder_display_name = bidder_name or auction.highest_bidder_display_name
        auction.bid_count = max(int(auction.bid_count or 0), 0) + 1
        auction.updated_at = now

        session.add(
            XiuxianAuctionBid(
                auction_id=int(auction.id),
                bidder_tg=int(bidder_tg),
                bidder_display_name=bidder_name or None,
                bid_amount_stone=next_price,
                action_type=bid_action,
            )
        )

        if is_buyout:
            payload = _settle_auction_row(session, auction)
            session.commit()
            return payload

        session.commit()
        return {
            "result": "bid",
            "auction": serialize_auction_item(auction),
            "winner_tg": None,
            "winner_display_name": None,
            "seller_tg": int(auction.owner_tg or 0) or None,
        }


def purchase_shop_item(buyer_tg: int, item_id: int, quantity: int = 1) -> dict[str, Any]:
    with Session() as session:
        item = (
            session.query(XiuxianShopItem)
            .filter(XiuxianShopItem.id == item_id, XiuxianShopItem.enabled.is_(True))
            .with_for_update()
            .first()
        )
        if item is None:
            raise ValueError("商品不存在或已下架")

        amount = max(int(quantity), 1)
        if item.quantity < amount:
            raise ValueError("商品库存不足")
        if item.owner_tg is not None and int(item.owner_tg) == int(buyer_tg):
            raise ValueError("你不能购买自己的挂单，请使用下架功能")

        buyer = (
            session.query(XiuxianProfile)
            .filter(XiuxianProfile.tg == buyer_tg)
            .with_for_update()
            .first()
        )
        if buyer is None or not buyer.consented:
            raise ValueError("买家尚未踏入仙途")

        base_total_cost = item.price_stone * amount
        charisma_discount_percent = 0
        discount_amount = 0
        if item.owner_tg is None:
            charisma_discount_percent = min(max(int(buyer.charisma or 0) - 10, 0) // 4, 20)
            discount_amount = base_total_cost * charisma_discount_percent // 100
        total_cost = max(base_total_cost - discount_amount, 0)
        if get_shared_spiritual_stone_total(int(buyer_tg), session=session, for_update=True) < total_cost:
            raise ValueError("灵石不足")

        apply_spiritual_stone_delta(
            session,
            int(buyer_tg),
            -total_cost,
            action_text="购买商品",
            allow_dead=False,
            apply_tribute=False,
        )

        seller = None
        if item.owner_tg is not None:
            seller = (
                session.query(XiuxianProfile)
                .filter(XiuxianProfile.tg == item.owner_tg)
                .with_for_update()
                .first()
            )
            if seller is not None:
                apply_spiritual_stone_delta(
                    session,
                    int(item.owner_tg),
                    total_cost,
                    action_text="商品售出入账",
                    allow_dead=True,
                    apply_tribute=False,
                )

        seller_tg = item.owner_tg
        item.quantity -= amount
        item.updated_at = utcnow()
        if item.quantity <= 0:
            item.enabled = False

        if item.item_kind == "artifact":
            _grant_artifact_inventory_in_session(
                session,
                int(buyer_tg),
                int(item.item_ref_id),
                amount,
                reject_if_owned=True,
                strict_quantity=True,
            )
        elif item.item_kind == "pill":
            row = (
                session.query(XiuxianPillInventory)
                .filter(
                    XiuxianPillInventory.tg == buyer_tg,
                    XiuxianPillInventory.pill_id == item.item_ref_id,
                )
                .first()
            )
            if row is None:
                row = XiuxianPillInventory(tg=buyer_tg, pill_id=item.item_ref_id, quantity=0)
                session.add(row)
            row.quantity += amount
            row.updated_at = utcnow()
        elif item.item_kind == "talisman":
            row = (
                session.query(XiuxianTalismanInventory)
                .filter(
                    XiuxianTalismanInventory.tg == buyer_tg,
                    XiuxianTalismanInventory.talisman_id == item.item_ref_id,
                )
                .first()
            )
            if row is None:
                row = XiuxianTalismanInventory(tg=buyer_tg, talisman_id=item.item_ref_id, quantity=0)
                session.add(row)
            row.quantity += amount
            row.updated_at = utcnow()
        elif item.item_kind == "material":
            row = (
                session.query(XiuxianMaterialInventory)
                .filter(
                    XiuxianMaterialInventory.tg == buyer_tg,
                    XiuxianMaterialInventory.material_id == item.item_ref_id,
                )
                .first()
            )
            if row is None:
                row = XiuxianMaterialInventory(tg=buyer_tg, material_id=item.item_ref_id, quantity=0)
                session.add(row)
            row.quantity += amount
            row.updated_at = utcnow()
        else:
            raise ValueError("不支持的商品类型")

        session.flush()
        serialized_item = serialize_shop_item(item)
        buyer_balance = get_shared_spiritual_stone_total(int(buyer_tg), session=session, for_update=False)
        seller_balance = None if seller is None else get_shared_spiritual_stone_total(int(item.owner_tg), session=session, for_update=False)
        _queue_catalog_cache_invalidation(session, "shop-items")
        _queue_profile_cache_invalidation(session, buyer_tg, int(item.owner_tg or 0))
        _queue_user_view_cache_invalidation(session, buyer_tg, int(item.owner_tg or 0))
        session.commit()

    name_map = get_emby_name_map([buyer_tg] + ([seller_tg] if seller_tg else []))
    return {
        "item": serialized_item,
        "buyer_balance": buyer_balance,
        "seller_balance": seller_balance,
        "total_cost": total_cost,
        "base_total_cost": base_total_cost,
        "discount_amount": discount_amount,
        "discount_percent": charisma_discount_percent,
        "buyer_tg": buyer_tg,
        "buyer_name": name_map.get(buyer_tg, f"TG {buyer_tg}"),
        "seller_tg": seller_tg,
        "seller_name": name_map.get(seller_tg, f"TG {seller_tg}") if seller_tg else None,
    }



def cancel_personal_shop_item(owner_tg: int, item_id: int) -> dict[str, Any]:
    with Session() as session:
        item = (
            session.query(XiuxianShopItem)
            .filter(
                XiuxianShopItem.id == item_id,
                XiuxianShopItem.owner_tg == owner_tg,
                XiuxianShopItem.is_official.is_(False),
            )
            .with_for_update()
            .first()
        )
        if item is None:
            raise ValueError("未找到可取消的个人上架商品")

        restore_quantity = max(int(item.quantity or 0), 0)
        if restore_quantity > 0:
            _grant_auction_item_to_inventory(
                session,
                tg=int(owner_tg),
                item_kind=str(item.item_kind or ""),
                item_ref_id=int(item.item_ref_id or 0),
                quantity=restore_quantity,
                source="shop_cancel",
                obtained_note="取消上架返还",
                auto_equip_if_empty=False,
            )

        item.quantity = 0
        item.enabled = False
        item.updated_at = utcnow()
        _queue_catalog_cache_invalidation(session, "shop-items")
        session.commit()
        session.refresh(item)
        return {
            "item": serialize_shop_item(item),
            "restored_quantity": restore_quantity,
        }


__all__ = [name for name in globals() if not name.startswith("__")]
