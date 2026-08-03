from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import aliased

from bot.plugins.xiuxian_game.service import (
    STARTER_FOUNDATION_PILL_NAME,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    REALM_ORDER,
    XiuxianPillInventory,
    XiuxianProfile,
    invalidate_xiuxian_user_view_cache,
    list_pills,
    normalize_realm_stage,
    realm_index,
    utcnow,
)


DEFAULT_CREATED_WINDOW_MINUTES = 10
DEFAULT_MAX_SOURCE_QUANTITY = 1
DEFAULT_PREVIEW_LIMIT = 20
DEFAULT_BATCH_SIZE = 200


@dataclass(frozen=True)
class Candidate:
    tg: int
    display_name: str
    realm_stage: str
    realm_layer: int
    profile_created_at: str
    source_quantity: int
    target_quantity: int
    source_created_at: str
    source_updated_at: str
    created_gap_minutes: float | None


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(sep=" ", timespec="seconds")


def _starter_foundation_pill_sort_key(pill: dict[str, Any]) -> tuple[int, int, int, str]:
    stage = normalize_realm_stage(pill.get("min_realm_stage"))
    if stage in REALM_ORDER:
        stage_rank = realm_index(stage)
    else:
        stage_rank = len(REALM_ORDER) + 1
    layer = int(pill.get("min_realm_layer") or 99)
    effect_value = int(pill.get("effect_value") or 0)
    return (stage_rank, layer, effect_value, str(pill.get("name") or ""))


def _list_foundation_pills() -> list[dict[str, Any]]:
    return [
        pill
        for pill in list_pills(enabled_only=True)
        if str(pill.get("pill_type") or "") == "foundation"
    ]


def _detect_target_pill(explicit_name: str | None) -> dict[str, Any]:
    foundation_pills = _list_foundation_pills()
    if not foundation_pills:
        raise RuntimeError("未找到可用的突破丹配置。")

    if explicit_name:
        matched = next(
            (
                pill for pill in foundation_pills
                if str(pill.get("name") or "").strip() == explicit_name.strip()
            ),
            None,
        )
        if matched is None:
            raise RuntimeError(f"未找到目标突破丹：{explicit_name}")
        return matched

    named_match = next(
        (
            pill for pill in foundation_pills
            if str(pill.get("name") or "").strip() == STARTER_FOUNDATION_PILL_NAME
        ),
        None,
    )
    if named_match is not None:
        return named_match

    early_stage_matches = [
        pill for pill in foundation_pills
        if normalize_realm_stage(pill.get("min_realm_stage")) == "炼气"
    ]
    if early_stage_matches:
        return min(early_stage_matches, key=_starter_foundation_pill_sort_key)
    return min(foundation_pills, key=_starter_foundation_pill_sort_key)


def _detect_source_pill(explicit_name: str | None) -> dict[str, Any]:
    foundation_pills = _list_foundation_pills()
    if not foundation_pills:
        raise RuntimeError("未找到可用的突破丹配置。")

    if explicit_name:
        matched = next(
            (
                pill for pill in foundation_pills
                if str(pill.get("name") or "").strip() == explicit_name.strip()
            ),
            None,
        )
        if matched is None:
            raise RuntimeError(f"未找到错误来源突破丹：{explicit_name}")
        return matched

    return foundation_pills[0]


def _build_candidates(
    *,
    source_pill_id: int,
    target_pill_id: int,
    max_source_quantity: int,
    created_within_minutes: int,
    include_users_with_target: bool,
) -> tuple[list[Candidate], dict[str, int]]:
    source_inventory = aliased(XiuxianPillInventory)
    target_inventory = aliased(XiuxianPillInventory)
    skip_stats = {
        "already_has_target": 0,
        "source_quantity_too_large": 0,
        "created_gap_too_large": 0,
    }

    with Session() as session:
        rows = (
            session.query(
                XiuxianProfile.tg,
                XiuxianProfile.display_name,
                XiuxianProfile.realm_stage,
                XiuxianProfile.realm_layer,
                XiuxianProfile.created_at,
                source_inventory.quantity.label("source_quantity"),
                source_inventory.created_at.label("source_created_at"),
                source_inventory.updated_at.label("source_updated_at"),
                target_inventory.quantity.label("target_quantity"),
            )
            .join(
                source_inventory,
                and_(
                    source_inventory.tg == XiuxianProfile.tg,
                    source_inventory.pill_id == source_pill_id,
                ),
            )
            .outerjoin(
                target_inventory,
                and_(
                    target_inventory.tg == XiuxianProfile.tg,
                    target_inventory.pill_id == target_pill_id,
                ),
            )
            .order_by(source_inventory.created_at.asc(), XiuxianProfile.tg.asc())
            .all()
        )

    candidates: list[Candidate] = []
    for row in rows:
        source_quantity = max(int(row.source_quantity or 0), 0)
        target_quantity = max(int(row.target_quantity or 0), 0)
        if source_quantity <= 0:
            continue
        if not include_users_with_target and target_quantity > 0:
            skip_stats["already_has_target"] += 1
            continue
        if max_source_quantity > 0 and source_quantity > max_source_quantity:
            skip_stats["source_quantity_too_large"] += 1
            continue

        created_gap_minutes: float | None = None
        if row.created_at and row.source_created_at:
            created_gap_minutes = abs(
                (row.source_created_at - row.created_at).total_seconds()
            ) / 60.0
            if created_within_minutes > 0 and created_gap_minutes > created_within_minutes:
                skip_stats["created_gap_too_large"] += 1
                continue

        candidates.append(
            Candidate(
                tg=int(row.tg or 0),
                display_name=str(row.display_name or ""),
                realm_stage=str(row.realm_stage or ""),
                realm_layer=int(row.realm_layer or 0),
                profile_created_at=_format_dt(row.created_at),
                source_quantity=source_quantity,
                target_quantity=target_quantity,
                source_created_at=_format_dt(row.source_created_at),
                source_updated_at=_format_dt(row.source_updated_at),
                created_gap_minutes=(
                    round(created_gap_minutes, 3)
                    if created_gap_minutes is not None
                    else None
                ),
            )
        )
    return candidates, skip_stats


def _apply_candidates(
    candidates: list[Candidate],
    *,
    source_pill_id: int,
    target_pill_id: int,
    batch_size: int,
) -> dict[str, int]:
    if not candidates:
        return {"updated_users": 0, "skipped_during_apply": 0}

    updated_users = 0
    skipped_during_apply = 0
    changed_tgs: list[int] = []

    with Session() as session:
        for index, candidate in enumerate(candidates, start=1):
            source_row = (
                session.query(XiuxianPillInventory)
                .filter(
                    XiuxianPillInventory.tg == candidate.tg,
                    XiuxianPillInventory.pill_id == source_pill_id,
                )
                .with_for_update()
                .first()
            )
            if source_row is None or int(source_row.quantity or 0) <= 0:
                skipped_during_apply += 1
                continue

            target_row = (
                session.query(XiuxianPillInventory)
                .filter(
                    XiuxianPillInventory.tg == candidate.tg,
                    XiuxianPillInventory.pill_id == target_pill_id,
                )
                .with_for_update()
                .first()
            )
            now = utcnow()
            source_row.quantity = max(int(source_row.quantity or 0) - 1, 0)
            source_row.updated_at = now
            if int(source_row.quantity or 0) <= 0:
                session.delete(source_row)

            if target_row is None:
                target_row = XiuxianPillInventory(
                    tg=int(candidate.tg),
                    pill_id=int(target_pill_id),
                    quantity=0,
                )
                session.add(target_row)
            target_row.quantity = max(int(target_row.quantity or 0), 0) + 1
            target_row.updated_at = now

            changed_tgs.append(int(candidate.tg))
            updated_users += 1

            if index % max(batch_size, 1) == 0:
                session.commit()
        session.commit()

    if changed_tgs:
        invalidate_xiuxian_user_view_cache(*sorted(set(changed_tgs)))
    return {
        "updated_users": updated_users,
        "skipped_during_apply": skipped_during_apply,
    }


def _print_preview(candidates: list[Candidate], preview_limit: int) -> None:
    if not candidates:
        print("preview: no candidates")
        return
    print(f"preview: showing {min(len(candidates), preview_limit)} / {len(candidates)} candidates")
    for item in candidates[:preview_limit]:
        print(
            json.dumps(
                asdict(item),
                ensure_ascii=False,
                sort_keys=True,
            )
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量纠正新手错误发放的高阶突破丹，把 1 枚错误丹换回新手突破丹。",
    )
    parser.add_argument(
        "--sync-seed-data",
        action="store_true",
        help="执行前先同步修仙种子数据；默认关闭，避免预览时产生额外写入。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写入数据库；默认仅预览。",
    )
    parser.add_argument(
        "--source-pill-name",
        default="",
        help="指定要扣掉的错误突破丹名称；默认自动按旧逻辑取第一枚 foundation 丹。",
    )
    parser.add_argument(
        "--target-pill-name",
        default="",
        help=f"指定补回的正确突破丹名称；默认优先使用 {STARTER_FOUNDATION_PILL_NAME}。",
    )
    parser.add_argument(
        "--max-source-quantity",
        type=int,
        default=DEFAULT_MAX_SOURCE_QUANTITY,
        help=(
            "只处理错误丹数量不超过该值的玩家。"
            f"默认 {DEFAULT_MAX_SOURCE_QUANTITY}，传 0 表示不限制。"
        ),
    )
    parser.add_argument(
        "--created-within-minutes",
        type=int,
        default=DEFAULT_CREATED_WINDOW_MINUTES,
        help=(
            "只处理错误丹库存创建时间与角色创建时间相差不超过该分钟数的玩家。"
            f"默认 {DEFAULT_CREATED_WINDOW_MINUTES}，传 0 表示不限制。"
        ),
    )
    parser.add_argument(
        "--include-users-with-target",
        action="store_true",
        help="默认跳过已经拥有目标新手丹的玩家；加上此参数后也纳入候选。",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=DEFAULT_PREVIEW_LIMIT,
        help=f"预览输出前多少条，默认 {DEFAULT_PREVIEW_LIMIT}。",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"实际写入时每批提交数量，默认 {DEFAULT_BATCH_SIZE}。",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.sync_seed_data:
        from bot.plugins.xiuxian_game.service import ensure_seed_data

        ensure_seed_data()

    source_pill = _detect_source_pill((args.source_pill_name or "").strip() or None)
    target_pill = _detect_target_pill((args.target_pill_name or "").strip() or None)
    if int(source_pill.get("id") or 0) == int(target_pill.get("id") or 0):
        raise RuntimeError(
            f"来源突破丹与目标突破丹相同：{source_pill.get('name')}，请显式传入 --source-pill-name。"
        )

    candidates, skip_stats = _build_candidates(
        source_pill_id=int(source_pill["id"]),
        target_pill_id=int(target_pill["id"]),
        max_source_quantity=int(args.max_source_quantity or 0),
        created_within_minutes=int(args.created_within_minutes or 0),
        include_users_with_target=bool(args.include_users_with_target),
    )

    summary: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "source_pill": {
            "id": int(source_pill["id"]),
            "name": str(source_pill.get("name") or ""),
            "min_realm_stage": str(source_pill.get("min_realm_stage") or ""),
            "min_realm_layer": int(source_pill.get("min_realm_layer") or 0),
        },
        "target_pill": {
            "id": int(target_pill["id"]),
            "name": str(target_pill.get("name") or ""),
            "min_realm_stage": str(target_pill.get("min_realm_stage") or ""),
            "min_realm_layer": int(target_pill.get("min_realm_layer") or 0),
        },
        "candidate_users": len(candidates),
        "skip_stats": skip_stats,
        "filters": {
            "max_source_quantity": int(args.max_source_quantity or 0),
            "created_within_minutes": int(args.created_within_minutes or 0),
            "include_users_with_target": bool(args.include_users_with_target),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    _print_preview(candidates, max(int(args.preview_limit or 0), 0))

    if not args.apply:
        return

    apply_result = _apply_candidates(
        candidates,
        source_pill_id=int(source_pill["id"]),
        target_pill_id=int(target_pill["id"]),
        batch_size=int(args.batch_size or DEFAULT_BATCH_SIZE),
    )
    print(json.dumps(apply_result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
