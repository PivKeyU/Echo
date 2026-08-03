from datetime import datetime


from bot import LOGGER, partition_libs
from bot.func_helper.emby import emby
from bot.sql_helper.sql_emby import sql_get_emby
from bot.sql_helper.sql_partition import (
    sql_get_partition_code,
    sql_redeem_partition_code_atomic,
    sql_set_partition_grant_status,
)

async def _redeem_partition_code(code: str, tg_id: int):
    now = datetime.now()

    record = sql_get_partition_code(code)
    if not record:
        return False, "❌ 分区码无效。"

    libs = partition_libs.get(record.partition, []) if partition_libs else []
    if not libs:
        LOGGER.warning("分区码对应分区未配置库: %s", record.partition)
        return False, "⚠️ 分区未配置库，请联系主人。"

    emby_row = sql_get_emby(tg=tg_id)
    if not emby_row or not emby_row.embyid:
        return False, "⚠️ 未找到您的 Emby 账户，请先完成注册绑定。"

    ok, partition, expires_at = sql_redeem_partition_code_atomic(
        code=code,
        tg=tg_id,
        embyid=emby_row.embyid,
        embyname=emby_row.name,
        now=now,
    )
    if not ok or not partition or not expires_at:
        return False, "❌ 分区码无效或已被使用。"

    show_ok = await emby.show_folders_by_names(emby_row.embyid, libs)
    libs_text = "、".join(libs)
    if not show_ok:
        # The code has been consumed, but the grant remains pending until
        # the Emby side effect succeeds.  It is not reported as active.
        sql_set_partition_grant_status(tg_id, partition, "pending_activation")
        LOGGER.error(
            "分区激活媒体库失败 tg=%s 分区=%s 媒体库=%s", tg_id, partition, libs_text
        )
        return (
            False,
            f"⚠️ 分区 {partition} 已记录为待激活，但媒体库开通失败。\n"
            f"系统将自动重试开通，请稍候或联系管理员。\n"
            f"媒体库：{libs_text}\n"
            f"授权到期：{expires_at:%Y-%m-%d %H:%M:%S}",
        )
    if not sql_set_partition_grant_status(tg_id, partition, "active"):
        LOGGER.error("分区授权已开通但本地状态更新失败 tg=%s 分区=%s", tg_id, partition)
        return False, "⚠️ 媒体库已尝试开通，但本地状态同步失败，请联系管理员。"
    return (
        True,
        f"✅ 已激活分区 {partition}\n"
        f"已激活媒体库：{libs_text}\n"
        f"可访问至：{expires_at:%Y-%m-%d %H:%M:%S}",
    )
