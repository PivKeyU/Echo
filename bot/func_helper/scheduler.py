import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.util import JobLookupError
from bot import LOGGER
from bot.func_helper.runtime import get_or_create_event_loop
from bot.func_helper.utils import Singleton


_get_loop = get_or_create_event_loop

class Scheduler(metaclass=Singleton):
    def __init__(self, timezone='Asia/Shanghai', misfire_grace_time=60, event_loop=None):
        # 创建一个AsyncIOScheduler对象，并传入时区、容忍度和事件循环参数
        self.SCHEDULER = AsyncIOScheduler(
            timezone=timezone,
            job_defaults={
                "misfire_grace_time": misfire_grace_time,
                "max_instances": 1,
                "coalesce": True,
            },
            event_loop=event_loop or _get_loop(),
        )
        # 启动调度器
        self.SCHEDULER.start()
        # 设置日志级别为INFO
        # logging.basicConfig(level=logging.INFO)

    # 函数、触发器、
    def add_job(self, func, trigger, **kwargs) -> bool:
        """
        添加定时任务。

        默认 replace_existing=True：同一 id 的任务已存在时直接替换，
        避免重复注册（如 MoviePilot 同步任务）触发 ConflictingIdError。
        成功返回 True，失败返回 False（不向外抛异常，由调用方决定后续处理）。
        """
        # 调用调度器的add_job方法，添加定时任务
        kwargs.setdefault('replace_existing', True)
        try:
            self.SCHEDULER.add_job(func, trigger, **kwargs)
            LOGGER.info(f"Added a job: {func.__name__} with {trigger} trigger and {kwargs} arguments.")
            return True
        except Exception as e:
            LOGGER.error(f"Failed to add a job: {e}")
            return False

    def remove_job(self, job_id=None, jobstore=None) -> bool:
        """
        幂等移除一个定时任务。

        任务不存在（JobLookupError）时视为目标状态已达成，返回 True；
        成功移除返回 True；其它失败返回 False（不向外抛异常）。
        这样调用方（配置面板）不会因为任务本就缺失而拒绝关闭对应开关。
        """
        # 调用调度器的remove_job方法，移除一个定时任务
        try:
            self.SCHEDULER.remove_job(job_id, jobstore)
            LOGGER.info(f"Removed a job: {job_id} from {jobstore}.")
            return True
        except JobLookupError:
            LOGGER.info(f"Job {job_id} not found in {jobstore}, nothing to remove.")
            return True
        except Exception as e:
            LOGGER.error(f"Failed to remove a job: {e}")
            return False

    def shutdown(self):
        # 调用调度器的shutdown方法，关闭调度器
        try:
            self.SCHEDULER.shutdown()
            LOGGER.info("Shutdown the scheduler successfully.")
        except Exception as e:
            LOGGER.error(f"Failed to shutdown the scheduler: {e}")

    @property
    def running(self):
        # 返回调度器是否正在运行
        return self.SCHEDULER.running


    def pause(self): \
            # 调用调度器的pause方法，暂停调度器
        try:
            self.SCHEDULER.pause()
            LOGGER.info("Paused the scheduler successfully.")
        except Exception as e:
            LOGGER.error(f"Failed to pause the scheduler: {e}")

    def resume(self):
        # 调用调度器的resume方法，恢复调度器
        try:
            self.SCHEDULER.resume()
            LOGGER.info("Resumed the scheduler successfully.")
        except Exception as e:
            LOGGER.error(f"Failed to resume the scheduler: {e}")

    def modify_job(self, job_id, **changes):
        # 调用调度器的modify_job方法，修改某个任务的属性
        try:
            self.SCHEDULER.modify_job(job_id, **changes)
            LOGGER.info(f"Modified a job: {job_id} with {changes} changes.")
        except Exception as e:
            LOGGER.error(f"Failed to modify a job: {e}")

scheduler = Scheduler()
# scheduler.add_job(check_expired, 'cron', hour=1, id='check_expired')
