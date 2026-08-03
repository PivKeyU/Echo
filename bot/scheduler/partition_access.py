from collections import defaultdict
from datetime import datetime
from typing import List, Set

from bot import partition_libs, bot, LOGGER
from bot.func_helper.emby import emby
from bot.sql_helper.sql_emby import sql_get_emby
from bot.sql_helper.sql_partition import (
    sql_get_active_grants_for_users,
    sql_get_expired_grants,
    sql_get_pending_grants,
    sql_claim_expired_grants,
    sql_restore_grants_active,
    sql_mark_grants_expired,
    sql_clear_expired_pending_grants,
    sql_set_partition_grant_status,
)

async def check_partition_access():
    """
    定时检查分区授权是否到期，过期则收回对应库的访问权限。
    同时重试上一轮媒体库开通失败的待激活授权。
    """
    now = datetime.now()
    if not partition_libs:
        return

    # 清理已过期且长期无法激活的 pending 授权（激活失败死胡同）
    expired_pending = sql_clear_expired_pending_grants(now)
    if expired_pending:
        LOGGER.info(f"清理过期待激活分区授权 {expired_pending} 条")

    # 重试上一轮开通失败的待激活授权（分区码已消耗，仅差 Emby 侧生效）
    pending = sql_get_pending_grants(now)
    for grant in pending:
        emby_row = sql_get_emby(tg=int(grant.tg))
        if not emby_row or not emby_row.embyid:
            continue
        libs = partition_libs.get(grant.partition, [])
        if not libs:
            continue
        shown = await emby.show_folders_by_names(emby_row.embyid, libs)
        if not shown:
            continue  # 保持 pending，下一轮继续重试
        if sql_set_partition_grant_status(int(grant.tg), grant.partition, "active"):
            LOGGER.info("分区待激活重试成功 tg=%s 分区=%s", grant.tg, grant.partition)
            try:
                await bot.send_message(
                    int(grant.tg),
                    f"✅ 分区 {grant.partition} 已自动开通\n"
                    f"可访问至：{grant.expires_at:%Y-%m-%d %H:%M:%S}",
                )
            except Exception as e:
                LOGGER.warning("分区开通通知发送失败 tg=%s: %s", grant.tg, e)
        else:
            LOGGER.error("分区待激活重试后状态更新失败 tg=%s 分区=%s", grant.tg, grant.partition)

    expired = sql_get_expired_grants(now)
    if not expired:
        return
    claimed_ids = sql_claim_expired_grants([int(grant.id) for grant in expired], now)
    if not claimed_ids:
        return
    claimed_set = set(claimed_ids)
    expired = [grant for grant in expired if int(grant.id) in claimed_set]

    by_user = defaultdict(list)
    for grant in expired:
        by_user[grant.tg].append(grant)

    processed_ids: List[int] = []
    failed_ids: List[int] = []
    for tg_id, grants in by_user.items():
        emby_row = sql_get_emby(tg=tg_id)
        if not emby_row or not emby_row.embyid:
            processed_ids.extend([g.id for g in grants])
            continue

        # 逐个用户重新读取当前有效授权：避免处理期间用户续费/新开分区后，
        # 仍按旧快照把已续期分区的库误隐藏。
        active_map = sql_get_active_grants_for_users([int(tg_id)], now)
        active_parts = {g.partition for g in active_map.get(int(tg_id), [])}
        keep_libs: Set[str] = set()
        for part in active_parts:
            keep_libs.update(partition_libs.get(part, []))

        # 需要撤销的库集合
        revoke_libs: Set[str] = set()
        for grant in grants:
            revoke_libs.update(partition_libs.get(grant.partition, []))

        # 只隐藏那些不再被其它分区授权覆盖的库
        hide_targets = [lib for lib in revoke_libs if lib not in keep_libs]
        hide_ok = True
        if hide_targets:
            hide_ok = await emby.hide_folders_by_names(emby_row.embyid, hide_targets)

        expired_parts = sorted({g.partition for g in grants})
        expired_parts_text = "、".join(expired_parts)
        hide_targets_text = "、".join(hide_targets) if hide_targets else ""

        if hide_targets and not hide_ok:
            # 隐藏失败：恢复为 active，下一轮继续重试，不得假报成功。
            failed_ids.extend(int(grant.id) for grant in grants)
            LOGGER.error(
                "分区到期隐藏媒体库失败，授权暂不收回 tg=%s 分区=%s 媒体库=%s",
                tg_id, expired_parts_text, hide_targets_text,
            )
            notice = (
                "⚠️ 分区授权到期提醒\n"
                f"到期分区：{expired_parts_text}\n"
                f"媒体库禁用失败：{hide_targets_text}\n"
                "授权暂未收回，请稍后重试或联系管理员检查 Emby 配置。"
            )
            try:
                await bot.send_message(tg_id, notice)
            except Exception as e:
                LOGGER.warning("分区到期通知发送失败 tg=%s: %s", tg_id, e)
            continue

        if hide_targets:
            notice = (
                "❌ 分区授权到期提醒\n"
                f"到期分区：{expired_parts_text}\n"
                f"已禁用媒体库：{hide_targets_text}"
            )

        # hide 成功但隐藏与续费存在竞态窗口：处理期间用户可能刚续费/新开分区，
        # 隐藏后立刻复查一次有效授权，若目标库已被重新授权则反向恢复，
        # 避免有效授权被误隐藏后无法自愈。
        if hide_targets and hide_ok:
            recheck = sql_get_active_grants_for_users([int(tg_id)], datetime.now())
            recheck_parts = {g.partition for g in recheck.get(int(tg_id), [])}
            restored_libs = [
                lib for lib in hide_targets
                if any(lib in partition_libs.get(part, []) for part in recheck_parts)
            ]
            if restored_libs:
                shown = await emby.show_folders_by_names(emby_row.embyid, restored_libs)
                if shown:
                    LOGGER.info(
                        "分区隐藏后复查发现已续期，反向恢复媒体库 tg=%s 库=%s",
                        tg_id, "、".join(restored_libs),
                    )
                else:
                    LOGGER.error(
                        "分区隐藏后复查恢复媒体库失败 tg=%s 库=%s",
                        tg_id, "、".join(restored_libs),
                    )

        try:
            await bot.send_message(tg_id, notice)
        except Exception as e:
            LOGGER.warning("分区到期通知发送失败 tg=%s: %s", tg_id, e)

        processed_ids.extend([g.id for g in grants])

    if failed_ids:
        sql_restore_grants_active(failed_ids)
    if processed_ids:
        sql_mark_grants_expired(processed_ids)
