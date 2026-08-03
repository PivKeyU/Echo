from __future__ import annotations

import json
import time

from bot.plugins.xiuxian_game.service import (
    build_mentorship_overview,
    consult_mentor_for_user,
    create_mentorship_request_for_user,
    ensure_seed_data,
    graduate_mentorship_for_user,
    init_path_for_user,
    mentor_teach_for_user,
    respond_mentorship_request_for_user,
)
from bot.sql_helper import Session
from bot.sql_helper.sql_xiuxian import XiuxianMentorship, upsert_profile


def _prepare_profiles(mentor_tg: int, disciple_tg: int) -> None:
    init_path_for_user(mentor_tg)
    init_path_for_user(disciple_tg)
    upsert_profile(
        mentor_tg,
        consented=True,
        display_name="师尊联调号",
        gender="male",
        realm_stage="金丹",
        realm_layer=6,
        spiritual_stone=9999,
        attack_power=520,
        defense_power=460,
        qi_blood=3600,
        true_yuan=920,
        bone=88,
        comprehension=96,
        divine_sense=92,
        fortune=78,
        willpower=90,
        body_movement=130,
        social_mode="worldly",
        death_at=None,
    )
    upsert_profile(
        disciple_tg,
        consented=True,
        display_name="弟子联调号",
        gender="female",
        realm_stage="筑基",
        realm_layer=2,
        spiritual_stone=8888,
        attack_power=180,
        defense_power=150,
        qi_blood=1500,
        true_yuan=360,
        bone=62,
        comprehension=68,
        divine_sense=64,
        fortune=55,
        willpower=60,
        body_movement=82,
        social_mode="worldly",
        death_at=None,
    )


def _force_graduate_ready(mentor_tg: int, disciple_tg: int) -> None:
    upsert_profile(
        disciple_tg,
        realm_stage="筑基",
        realm_layer=8,
        attack_power=240,
        defense_power=210,
        qi_blood=1850,
        true_yuan=430,
    )
    with Session() as session:
        relation = (
            session.query(XiuxianMentorship)
            .filter(
                XiuxianMentorship.mentor_tg == mentor_tg,
                XiuxianMentorship.disciple_tg == disciple_tg,
                XiuxianMentorship.status == "active",
            )
            .order_by(XiuxianMentorship.id.desc())
            .first()
        )
        if relation is None:
            raise RuntimeError("未找到已建立的师徒关系，无法继续验证出师流程。")
        relation.bond_value = 128
        relation.teach_count = 5
        relation.consult_count = 3
        relation.last_teach_at = None
        relation.last_consult_at = None
        session.commit()


def main() -> None:
    suffix = int(time.time()) % 100000
    mentor_tg = 910000000 + suffix
    disciple_tg = 920000000 + suffix

    ensure_seed_data()
    _prepare_profiles(mentor_tg, disciple_tg)

    request_result = create_mentorship_request_for_user(
        disciple_tg,
        mentor_tg,
        "disciple",
        message="联调：请求拜师",
    )
    request_id = int((request_result.get("request") or {}).get("id") or 0)
    if request_id <= 0:
        raise RuntimeError(f"师徒拜帖创建失败: {request_result}")

    accept_result = respond_mentorship_request_for_user(mentor_tg, request_id, "accept")
    teach_result = mentor_teach_for_user(mentor_tg, disciple_tg)
    consult_result = consult_mentor_for_user(disciple_tg)
    before_graduate = build_mentorship_overview(mentor_tg)

    _force_graduate_ready(mentor_tg, disciple_tg)
    graduate_result = graduate_mentorship_for_user(mentor_tg, disciple_tg)
    after_graduate = build_mentorship_overview(mentor_tg)

    print(
        json.dumps(
            {
                "mentor_tg": mentor_tg,
                "disciple_tg": disciple_tg,
                "request_id": request_id,
                "accept_message": accept_result.get("message"),
                "teach_message": teach_result.get("message"),
                "consult_message": consult_result.get("message"),
                "graduate_message": graduate_result.get("message"),
                "before_graduate_active_relations": len(before_graduate.get("disciple_relations") or []),
                "after_graduate_active_relations": len(after_graduate.get("disciple_relations") or []),
                "after_graduate_title_rewards": [
                    (item.get("title") or {}).get("name")
                    for item in (graduate_result.get("title_rewards") or [])
                    if item.get("title")
                ],
                "after_graduate_can_take_disciple": after_graduate.get("can_take_disciple"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
