from __future__ import annotations

from typing import Any


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def create_personal_shop_listing(
    *,
    tg: int,
    shop_name: str,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    price_stone: int,
    broadcast: bool,
) -> dict[str, Any]:
    return _legacy_service().create_personal_shop_listing(
        tg=tg,
        shop_name=shop_name,
        item_kind=item_kind,
        item_ref_id=item_ref_id,
        quantity=quantity,
        price_stone=price_stone,
        broadcast=broadcast,
    )


def create_personal_auction_listing(
    *,
    tg: int,
    seller_name: str,
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    opening_price_stone: int,
    bid_increment_stone: int,
    buyout_price_stone: int | None = None,
) -> dict[str, Any]:
    return _legacy_service().create_personal_auction_listing(
        tg=tg,
        seller_name=seller_name,
        item_kind=item_kind,
        item_ref_id=item_ref_id,
        quantity=quantity,
        opening_price_stone=opening_price_stone,
        bid_increment_stone=bid_increment_stone,
        buyout_price_stone=buyout_price_stone,
    )


def create_official_shop_listing(
    item_kind: str,
    item_ref_id: int,
    quantity: int,
    price_stone: int,
    shop_name: str | None = None,
) -> dict[str, Any]:
    return _legacy_service().create_official_shop_listing(
        item_kind=item_kind,
        item_ref_id=item_ref_id,
        quantity=quantity,
        price_stone=price_stone,
        shop_name=shop_name,
    )


def recycle_item_to_official_shop(
    *,
    tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int = 1,
) -> dict[str, Any]:
    return _legacy_service().recycle_item_to_official_shop(
        tg=tg,
        item_kind=item_kind,
        item_ref_id=item_ref_id,
        quantity=quantity,
    )


def recycle_items_to_official_shop(
    *,
    tg: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return _legacy_service().recycle_items_to_official_shop(
        tg=tg,
        items=items,
    )


def attach_official_recycle_quotes(bundle: dict[str, Any]) -> dict[str, Any]:
    return _legacy_service().attach_official_recycle_quotes(bundle)


def patch_shop_listing(item_id: int, **fields) -> dict[str, Any] | None:
    return _legacy_service().patch_shop_listing(item_id, **fields)


def patch_auction_listing(auction_id: int, **fields) -> dict[str, Any] | None:
    return _legacy_service().patch_auction_listing(auction_id, **fields)


def purchase_shop_item(tg: int, item_id: int, quantity: int = 1) -> dict[str, Any]:
    return _legacy_service().purchase_shop_item(tg, item_id, quantity=quantity)


def place_auction_bid(tg: int, auction_id: int, *, bidder_name: str = "", use_buyout: bool = False) -> dict[str, Any]:
    return _legacy_service().place_auction_bid(
        tg,
        auction_id,
        bidder_name=bidder_name,
        use_buyout=use_buyout,
    )


def finalize_auction_listing(auction_id: int, *, force: bool = False) -> dict[str, Any] | None:
    return _legacy_service().finalize_auction_listing(auction_id, force=force)


def cancel_personal_auction_listing(tg: int, auction_id: int) -> dict[str, Any] | None:
    return _legacy_service().cancel_personal_auction_listing(tg, auction_id)


def grant_item_to_user(tg: int, item_kind: str, item_ref_id: int, quantity: int) -> dict[str, Any]:
    return _legacy_service().grant_item_to_user(tg, item_kind, item_ref_id, quantity)


def convert_emby_coin_to_stone(tg: int, amount: int) -> dict[str, Any]:
    return _legacy_service().convert_emby_coin_to_stone(tg, amount)


def convert_stone_to_emby_coin(tg: int, amount: int) -> dict[str, Any]:
    return _legacy_service().convert_stone_to_emby_coin(tg, amount)


def list_public_shop_items() -> dict[str, Any]:
    return _legacy_service().list_public_shop_items()


def search_xiuxian_players(
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_secluded: bool = True,
) -> dict[str, Any]:
    return _legacy_service().search_xiuxian_players(
        query=query,
        page=page,
        page_size=page_size,
        include_secluded=include_secluded,
    )


def generate_shop_name(first_name: str) -> str:
    return _legacy_service().generate_shop_name(first_name)


def broadcast_shop_copy(seller_name: str, shop_name: str, item_name: str, price_stone: int) -> str:
    return _legacy_service().broadcast_shop_copy(seller_name, shop_name, item_name, price_stone)
