from __future__ import annotations

from typing import Any

from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    XiuxianProfile,
    _marriage_partner_tg,
    apply_spiritual_stone_delta,
    assert_artifact_receivable_by_user,
    assert_currency_operation_allowed,
    assert_profile_alive,
    create_journal,
    get_artifact,
    get_material,
    get_pill,
    get_profile,
    get_talisman,
    list_user_artifacts,
    list_user_materials,
    list_user_pills,
    list_user_talismans,
    serialize_artifact,
    serialize_material,
    serialize_pill,
    serialize_profile,
    serialize_talisman,
    use_user_artifact_listing_stock,
    use_user_material_listing_stock,
    use_user_pill_listing_stock,
    use_user_talisman_listing_stock,
    utcnow,
)
from bot.plugins.xiuxian_game.achievement_service import record_gift_metrics
from bot.plugins.xiuxian_game.features.retreat import ensure_not_in_retreat


def _legacy_service():
    from bot.plugins.xiuxian_game import service as legacy_service

    return legacy_service


def _is_active_spouse_pair(session: Session, actor_tg: int, target_tg: int) -> bool:
    actor_id = int(actor_tg or 0)
    target_id = int(target_tg or 0)
    if actor_id <= 0 or target_id <= 0 or actor_id == target_id:
        return False
    return int(_marriage_partner_tg(session, actor_id, for_update=True) or 0) == target_id


def gift_spirit_stone(sender_tg: int, target_tg: int, amount: int) -> dict[str, Any]:
    if int(sender_tg) == int(target_tg):
        raise ValueError("不能给自己赠送灵石")
    amount = max(int(amount or 0), 0)
    if amount <= 0:
        raise ValueError("赠送灵石数量必须大于 0")

    ensure_not_in_retreat(sender_tg)
    legacy_service = _legacy_service()

    with Session() as session:
        sender = session.query(XiuxianProfile).filter(XiuxianProfile.tg == sender_tg).with_for_update().first()
        receiver = session.query(XiuxianProfile).filter(XiuxianProfile.tg == target_tg).with_for_update().first()
        if sender is None or receiver is None or not sender.consented or not receiver.consented:
            raise ValueError("双方都需要已踏入仙途")
        assert_profile_alive(sender, "赠送灵石")
        assert_profile_alive(receiver, "接收灵石")
        legacy_service._assert_gender_ready(sender, "赠送灵石")
        legacy_service._assert_gender_ready(receiver, "接收灵石")
        legacy_service.assert_social_action_allowed(sender, receiver, "赠送灵石")
        if _is_active_spouse_pair(session, sender_tg, target_tg):
            raise ValueError("道侣之间灵石共享，不能互相赠送灵石。")
        assert_currency_operation_allowed(sender_tg, "赠送灵石", session=session, profile=sender)
        assert_currency_operation_allowed(target_tg, "接收灵石", session=session, profile=receiver)
        apply_spiritual_stone_delta(
            session,
            sender_tg,
            -amount,
            action_text="赠送灵石",
            allow_dead=False,
            apply_tribute=False,
        )
        apply_spiritual_stone_delta(
            session,
            target_tg,
            amount,
            action_text="接收灵石",
            allow_dead=False,
            apply_tribute=True,
        )
        session.commit()

    create_journal(sender_tg, "gift", "赠送灵石", f"向 TG {target_tg} 赠送了 {amount} 灵石")
    create_journal(target_tg, "gift", "收到灵石", f"收到 TG {sender_tg} 赠送的 {amount} 灵石")
    return {
        "amount": amount,
        "sender": serialize_profile(get_profile(sender_tg, create=False)),
        "receiver": serialize_profile(get_profile(target_tg, create=False)),
        "achievement_unlocks": record_gift_metrics(sender_tg, amount),
    }


def _inventory_item_payload(item_kind: str, item_ref_id: int) -> dict[str, Any] | None:
    if item_kind == "artifact":
        return {"artifact": serialize_artifact(get_artifact(item_ref_id))}
    if item_kind == "pill":
        return {"pill": serialize_pill(get_pill(item_ref_id))}
    if item_kind == "talisman":
        return {"talisman": serialize_talisman(get_talisman(item_ref_id))}
    if item_kind == "material":
        return {"material": serialize_material(get_material(item_ref_id))}
    return None


def _inventory_total_for_user(tg: int, item_kind: str, item_ref_id: int) -> int:
    target_id = int(item_ref_id or 0)
    if item_kind == "artifact":
        return next(
            (
                max(int(row.get("quantity") or 0), 0)
                for row in list_user_artifacts(tg)
                if int((row.get("artifact") or {}).get("id") or 0) == target_id
            ),
            0,
        )
    if item_kind == "pill":
        return next(
            (
                max(int(row.get("quantity") or 0), 0)
                for row in list_user_pills(tg)
                if int((row.get("pill") or {}).get("id") or 0) == target_id
            ),
            0,
        )
    if item_kind == "talisman":
        return next(
            (
                max(int(row.get("quantity") or 0), 0)
                for row in list_user_talismans(tg)
                if int((row.get("talisman") or {}).get("id") or 0) == target_id
            ),
            0,
        )
    return next(
        (
            max(int(row.get("quantity") or 0), 0)
            for row in list_user_materials(tg)
            if int((row.get("material") or {}).get("id") or 0) == target_id
        ),
        0,
    )


def gift_inventory_item(
    sender_tg: int,
    target_tg: int,
    item_kind: str,
    item_ref_id: int,
    quantity: int = 1,
) -> dict[str, Any]:
    if int(sender_tg) == int(target_tg):
        raise ValueError("不能给自己赠送物品")
    item_kind = str(item_kind or "").strip()
    item_ref_id = int(item_ref_id or 0)
    quantity = max(int(quantity or 0), 0)
    if item_kind not in {"artifact", "pill", "talisman", "material"}:
        raise ValueError("当前只支持赠送法宝、符箓、丹药和材料")
    if item_ref_id <= 0 or quantity <= 0:
        raise ValueError("赠送物品参数不正确")

    ensure_not_in_retreat(sender_tg)
    legacy_service = _legacy_service()

    with Session() as session:
        sender = session.query(XiuxianProfile).filter(XiuxianProfile.tg == sender_tg).with_for_update().first()
        receiver = session.query(XiuxianProfile).filter(XiuxianProfile.tg == target_tg).with_for_update().first()
        if sender is None or receiver is None or not sender.consented or not receiver.consented:
            raise ValueError("双方都需要已踏入仙途")
        assert_profile_alive(sender, "赠送物品")
        assert_profile_alive(receiver, "接收物品")
        legacy_service._assert_gender_ready(sender, "赠送物品")
        legacy_service._assert_gender_ready(receiver, "接收物品")
        legacy_service.assert_social_action_allowed(sender, receiver, "赠送物品")
        assert_currency_operation_allowed(sender_tg, "赠送物品", session=session, profile=sender)
        assert_currency_operation_allowed(target_tg, "接收物品", session=session, profile=receiver)
        sender.updated_at = utcnow()
        receiver.updated_at = utcnow()
        session.commit()

    if item_kind == "artifact":
        artifact = serialize_artifact(get_artifact(item_ref_id))
        if artifact and bool(artifact.get("unique_item")) and quantity > 1:
            raise ValueError(f"唯一法宝【{artifact.get('name') or item_ref_id}】每次只能赠送 1 件。")
        assert_artifact_receivable_by_user(
            target_tg,
            item_ref_id,
            allow_existing_owner=False,
            exclude_owner_tgs={int(sender_tg)},
        )
        if not use_user_artifact_listing_stock(sender_tg, item_ref_id, quantity):
            raise ValueError("可赠送的法宝数量不足，已绑定或已装备的法宝不能赠送")
    elif item_kind == "talisman":
        if not use_user_talisman_listing_stock(sender_tg, item_ref_id, quantity):
            raise ValueError("可赠送的符箓数量不足，已绑定的符箓不能赠送")
    elif item_kind == "pill":
        if not use_user_pill_listing_stock(sender_tg, item_ref_id, quantity):
            raise ValueError("可赠送的丹药数量不足")
    else:
        if not use_user_material_listing_stock(sender_tg, item_ref_id, quantity):
            raise ValueError("可赠送的材料数量不足")

    grant_result = legacy_service.grant_item_to_user(target_tg, item_kind, item_ref_id, quantity)
    sender_remaining = _inventory_total_for_user(sender_tg, item_kind, item_ref_id)
    receiver_quantity = max(int(grant_result.get("quantity") or 0), 0)

    item_payload = _inventory_item_payload(item_kind, item_ref_id)
    item_name = (
        item_payload.get("artifact", {}).get("name")
        or item_payload.get("pill", {}).get("name")
        or item_payload.get("talisman", {}).get("name")
        or item_payload.get("material", {}).get("name")
        or f"{item_kind}#{item_ref_id}"
    )
    create_journal(sender_tg, "gift_item", "赠送物品", f"向 TG {target_tg} 赠送了 {quantity} 个【{item_name}】")
    create_journal(target_tg, "gift_item", "收到物品", f"收到 TG {sender_tg} 赠送的 {quantity} 个【{item_name}】")
    return {
        "item_kind": item_kind,
        "item_ref_id": item_ref_id,
        "quantity": quantity,
        "item": item_payload,
        "sender_remaining": sender_remaining,
        "receiver_quantity": receiver_quantity,
        "sender": serialize_profile(get_profile(sender_tg, create=False)),
        "receiver": serialize_profile(get_profile(target_tg, create=False)),
    }
