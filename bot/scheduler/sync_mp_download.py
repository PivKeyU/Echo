import asyncio

from pyrogram import enums

from bot import LOGGER, config, bot
from bot.func_helper.moviepilot import get_download_task, get_history_transfer_task_by_title_download_id
from bot.sql_helper.sql_request_record import sql_update_request_status, sql_get_request_record_by_transfer_state, sql_get_request_record_by_download_id
from bot.func_helper.scheduler import scheduler

_SYNC_DOWNLOAD_LOCK = asyncio.Lock()

# 明确成功的转移状态：只有该值才标记 completed 并通知用户
TRANSFER_STATE_SUCCESS = 'success'
# 明确失败的转移状态：写入 failed 后不再参与转移检查
TRANSFER_STATE_FAILED = 'failed'


def _is_transfer_success(value):
    """是否为明确成功（兼容旧版接口可能返回的布尔值）。"""
    return value in (TRANSFER_STATE_SUCCESS, True)


def _is_transfer_failed(value):
    """是否为明确失败（兼容旧版接口可能返回的布尔值）。"""
    return value in (TRANSFER_STATE_FAILED, False)


async def _sync_download_tasks_once():
    """同步MoviePilot下载任务状态到数据库"""
    try:
        # 获取所有下载任务
        download_tasks = await get_download_task()
        if download_tasks is None:
            LOGGER.error("[MoviePilot] 获取下载任务失败，本次跳过下载状态同步")
        download_count = 0
        if download_tasks is not None:
            # 更新每个任务的状态
            for task in download_tasks:
                record = sql_get_request_record_by_download_id(task['download_id'])
                if record is None:
                    continue
                download_id = task['download_id']
                download_state = task['state']
                progress = task['progress']
                left_time = task.get('left_time', '未知')

                # 根据状态更新数据库
                if download_state == 'downloading':
                    # 正在下载中
                    sql_update_request_status(
                        download_id=download_id,
                        download_state='downloading',
                        progress=progress,
                        left_time=left_time
                    )
                elif download_state == 'completed':
                    # 下载完成
                    sql_update_request_status(
                        download_id=download_id,
                        download_state='completed',
                        progress=100,
                        left_time='0'
                    )
                elif download_state == 'failed':
                    # 下载失败
                    sql_update_request_status(
                        download_id=download_id,
                        download_state='failed',
                        progress=progress,
                        left_time='失败'
                    )
                elif download_state == 'pending':
                    # 等待下载
                    sql_update_request_status(
                        download_id=download_id,
                        download_state='pending',
                        progress=0,
                        left_time='等待中'
                    )
                download_count += 1

        # 获取需要检查转移状态的记录（transfer_state 尚未写入明确结果）
        transfer_tasks = sql_get_request_record_by_transfer_state()
        transfer_count = 0
        if transfer_tasks is not None:
            # 检查每个记录的转移状态
            for record in transfer_tasks:
                transfer_state = await get_history_transfer_task_by_title_download_id("", record.download_id, count=100)
                if transfer_state is None:
                    # 查询失败或未查到，保留原状态等待下次同步
                    continue
                if _is_transfer_success(transfer_state):
                    # 仅明确成功才通知并标记完成，禁止 truthy 即完成
                    try:
                        await bot.send_message(
                            chat_id=record.tg,
                            text=f"💯恭喜您点播的「{record.request_name}」已成功入库！",
                            parse_mode=enums.ParseMode.DISABLED,
                        )
                    except Exception as e:
                        LOGGER.error(f"[MoviePilot] 发送通知到{record.tg}失败: {str(e)}")
                    updated = sql_update_request_status(
                        download_id=record.download_id,
                        transfer_state=TRANSFER_STATE_SUCCESS,
                        download_state='completed',
                        progress=100,
                        left_time='0'
                    )
                    if not updated:
                        LOGGER.warning(f"[MoviePilot] 更新记录 {record.download_id} 转移成功状态失败（记录可能已不存在）")
                    transfer_count += 1
                elif _is_transfer_failed(transfer_state):
                    # 明确失败：写入 failed，不再参与后续转移检查
                    updated = sql_update_request_status(
                        download_id=record.download_id,
                        transfer_state=TRANSFER_STATE_FAILED,
                        download_state='failed'
                    )
                    if not updated:
                        LOGGER.warning(f"[MoviePilot] 更新记录 {record.download_id} 转移失败状态失败（记录可能已不存在）")
                    LOGGER.warning(f"[MoviePilot] 点播「{record.request_name}」(download_id={record.download_id}) 入库失败")
                    transfer_count += 1
                else:
                    # 中间态/未知状态：保留待重试，不标记完成
                    LOGGER.debug(f"[MoviePilot] 记录 {record.download_id} 转移状态为 {transfer_state}，等待下次同步")
        if download_count > 0 or transfer_count > 0:
            LOGGER.info(f"[MoviePilot] 同步了 {download_count} 个下载任务状态, {transfer_count} 个转移任务状态")
    except Exception as e:
        LOGGER.error(f"[MoviePilot] 同步下载任务状态时出错: {str(e)}")


async def sync_download_tasks():
    if _SYNC_DOWNLOAD_LOCK.locked():
        LOGGER.warning("[MoviePilot] 上一轮同步尚未完成，跳过本轮重复执行")
        return
    async with _SYNC_DOWNLOAD_LOCK:
        await _sync_download_tasks_once()


# 如果MoviePilot功能开启，添加定时任务
if config.moviepilot.status:
    scheduler.add_job(sync_download_tasks, 'interval',
                     seconds=60, id='sync_download_tasks', max_instances=1, coalesce=True)
