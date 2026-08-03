from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.plugins.xiuxian_game.service import _fortune_pill_cap_for_profile
from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import (
    XiuxianJournal,
    XiuxianProfile,
    invalidate_xiuxian_user_view_cache,
    serialize_profile,
    utcnow,
)


DEFAULT_PREVIEW_LIMIT = 30
DEFAULT_BATCH_SIZE = 200


@dataclass(frozen=True)
class Candidate:
    tg: int
    display_name: str
    realm_stage: str
    realm_layer: int
    current_fortune: int
    cap: int
    overflow: int


def _candidate_for_profile(profile: XiuxianProfile) -> Candidate | None:
    payload = serialize_profile(profile) or {}
    current = max(int(payload.get("fortune") or 0), 0)
    cap = _fortune_pill_cap_for_profile(payload)
    if current <= cap:
        return None
    return Candidate(
        tg=int(profile.tg),
        display_name=str(profile.display_name or profile.username or ""),
        realm_stage=str(payload.get("realm_stage") or ""),
        realm_layer=max(int(payload.get("realm_layer") or 1), 1),
        current_fortune=current,
        cap=cap,
        overflow=current - cap,
    )


def _build_candidates(tg: int | None = None) -> list[Candidate]:
    with Session() as session:
        query = session.query(XiuxianProfile).filter(XiuxianProfile.consented.is_(True))
        if tg is not None:
            query = query.filter(XiuxianProfile.tg == int(tg))
        rows = query.order_by(XiuxianProfile.realm_stage.asc(), XiuxianProfile.fortune.desc()).all()
        candidates = [item for profile in rows if (item := _candidate_for_profile(profile)) is not None]
    return candidates


def _apply_candidates(candidates: list[Candidate], batch_size: int) -> dict[str, int]:
    if not candidates:
        return {"updated_users": 0, "skipped_during_apply": 0}

    updated_users = 0
    skipped_during_apply = 0
    changed_tgs: list[int] = []

    with Session() as session:
        for index, candidate in enumerate(candidates, start=1):
            profile = (
                session.query(XiuxianProfile)
                .filter(XiuxianProfile.tg == int(candidate.tg))
                .with_for_update()
                .first()
            )
            if profile is None or not profile.consented:
                skipped_during_apply += 1
                continue

            current_candidate = _candidate_for_profile(profile)
            if current_candidate is None:
                skipped_during_apply += 1
                continue

            cap = current_candidate.cap
            before = current_candidate.current_fortune
            profile.fortune = cap
            profile.updated_at = utcnow()
            session.add(
                XiuxianJournal(
                    tg=int(profile.tg),
                    action_type="system_repair",
                    title="机缘修复",
                    detail=f"机缘丹历史叠加超出当前境界上限，基础机缘由 {before} 回落至 {cap}。",
                )
            )
            changed_tgs.append(int(profile.tg))
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
        print("preview: no over-cap profiles")
        return
    print(f"preview: showing {min(len(candidates), preview_limit)} / {len(candidates)} candidates")
    for item in candidates[:preview_limit]:
        print(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="修复机缘丹历史无限叠加造成的基础机缘超上限数据。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写入数据库；默认仅预览。",
    )
    parser.add_argument(
        "--apply-all",
        action="store_true",
        help="允许 --apply 在未指定 --tg 时修复所有候选；默认禁止全量写库。",
    )
    parser.add_argument(
        "--tg",
        type=int,
        default=None,
        help="只检查或修复指定 TG 用户；默认扫描所有已同意修仙的用户。",
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
    candidates = _build_candidates(args.tg)
    overflow_total = sum(item.overflow for item in candidates)
    summary: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "scope": f"tg:{args.tg}" if args.tg is not None else "all",
        "candidate_count": len(candidates),
        "overflow_total": overflow_total,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    _print_preview(candidates, max(int(args.preview_limit or 0), 0))

    if not args.apply:
        print("dry-run only; rerun with --apply to write changes")
        return
    if args.tg is None and not args.apply_all:
        raise SystemExit("refusing global apply without --apply-all; use --tg to repair one user or add --apply-all after reviewing preview")

    result = _apply_candidates(candidates, batch_size=max(int(args.batch_size or 1), 1))
    print(json.dumps({"apply_result": result}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
