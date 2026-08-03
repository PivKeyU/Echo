import asyncio
import contextlib
import os
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from bot import LOGGER


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效整数，回退到默认值 {default}")
        return default


def _env_float(name: str, default: float, minimum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, float(raw))
    except (TypeError, ValueError):
        LOGGER.warning(f"环境变量 {name}={raw!r} 不是有效数字，回退到默认值 {default}")
        return default


REGISTER_QUEUE_WORKERS = _env_int("PIVKEYU_REGISTER_QUEUE_WORKERS", 2, 1)
REGISTER_QUEUE_MAXSIZE = _env_int("PIVKEYU_REGISTER_QUEUE_MAXSIZE", 64, 1)
REGISTER_QUEUE_JOB_TIMEOUT = _env_float("PIVKEYU_REGISTER_QUEUE_JOB_TIMEOUT", 120.0, 10.0)
# 任务超时被取消后，远端(Emby)可能已部分完成创建，冷却期内该用户仍按"处理中"处理，
# 避免超时后立刻重复提交造成无法区分的重复创建。
REGISTER_QUEUE_TIMEOUT_COOLDOWN = _env_float("PIVKEYU_REGISTER_QUEUE_TIMEOUT_COOLDOWN", 60.0, 10.0)


@dataclass(slots=True)
class RegisterQueueSubmitResult:
    accepted: bool
    duplicate: bool
    ahead: int = 0
    capacity: int = REGISTER_QUEUE_MAXSIZE


@dataclass(slots=True)
class _RegisterQueueJob:
    user_id: int
    runner: Callable[[], Awaitable[None]]
    enqueued_at: float = field(default_factory=time.monotonic)


class RegisterQueue:
    def __init__(self, workers: int = REGISTER_QUEUE_WORKERS, maxsize: int = REGISTER_QUEUE_MAXSIZE):
        self._worker_count = max(1, int(workers))
        self._queue: asyncio.Queue[_RegisterQueueJob] = asyncio.Queue(maxsize=max(1, int(maxsize)))
        self._workers: list[asyncio.Task] = []
        self._worker_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._pending_user_ids: list[int] = []
        self._running_user_ids: set[int] = set()
        self._active_user_ids: set[int] = set()
        # user_id -> 超时冷却截止时间(monotonic)，期间该用户保持"处理中"语义
        self._timeout_cooldown_until: dict[int, float] = {}

    @property
    def capacity(self) -> int:
        return self._queue.maxsize

    def _ahead_for_new_job(self) -> int:
        return len(self._running_user_ids) + len(self._pending_user_ids)

    def _ahead_for_existing_user(self, user_id: int) -> int:
        if user_id in self._running_user_ids:
            return 0
        try:
            index = self._pending_user_ids.index(int(user_id))
        except ValueError:
            return self._ahead_for_new_job()
        return len(self._running_user_ids) + index

    def _in_timeout_cooldown(self, user_id: int) -> bool:
        deadline = self._timeout_cooldown_until.get(user_id)
        if deadline is None:
            return False
        if time.monotonic() < deadline:
            return True
        self._timeout_cooldown_until.pop(user_id, None)
        # The cooldown has ended; allow a fresh submission.
        # 仅当该用户没有正在运行/排队的任务时才解除"处理中"标记
        # （正常流程下冷却期内不可能有新任务，此防御保证状态不被误清理）。
        if user_id not in self._running_user_ids and user_id not in self._pending_user_ids:
            self._active_user_ids.discard(user_id)
        return False

    async def _ensure_workers(self) -> None:
        async with self._worker_lock:
            active_workers = [task for task in self._workers if not task.done()]
            self._workers = active_workers
            missing_workers = self._worker_count - len(self._workers)
            for index in range(max(0, missing_workers)):
                task = asyncio.create_task(self._worker_loop(), name=f"register-queue-{len(self._workers) + index + 1}")
                self._workers.append(task)

    async def submit(self, user_id: int, runner: Callable[[], Awaitable[None]]) -> RegisterQueueSubmitResult:
        normalized_user_id = int(user_id)
        await self._ensure_workers()
        async with self._state_lock:
            # 必须先求值 _in_timeout_cooldown：它负责在冷却期结束后清理过期条目，
            # 若把它放在 or 的右侧，active 命中会短路跳过清理，导致冷却期永不结束
            # （超时用户被永久当作 duplicate 拒绝）。
            if self._in_timeout_cooldown(normalized_user_id) or normalized_user_id in self._active_user_ids:
                # 冷却期内同样视为"处理中"，避免超时任务可能已部分完成时重复创建
                return RegisterQueueSubmitResult(
                accepted=False,
                duplicate=True,
                ahead=self._ahead_for_existing_user(normalized_user_id),
                capacity=self.capacity,
            )

            if self._queue.full():
                return RegisterQueueSubmitResult(
                    accepted=False,
                    duplicate=False,
                    ahead=self._ahead_for_new_job(),
                    capacity=self.capacity,
                )

            job = _RegisterQueueJob(user_id=normalized_user_id, runner=runner)
            # 登记与入队作为一个整体：任一步失败都回滚，避免用户被永久标记为"处理中"
            try:
                self._active_user_ids.add(normalized_user_id)
                self._pending_user_ids.append(normalized_user_id)
                self._queue.put_nowait(job)
            except Exception:
                self._active_user_ids.discard(normalized_user_id)
                with contextlib.suppress(ValueError):
                    self._pending_user_ids.remove(normalized_user_id)
                raise
            return RegisterQueueSubmitResult(
                accepted=True,
                duplicate=False,
                ahead=max(0, self._ahead_for_existing_user(normalized_user_id)),
                capacity=self.capacity,
            )

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            user_id = int(job.user_id)
            try:
                with contextlib.suppress(ValueError):
                    async with self._state_lock:
                        self._pending_user_ids.remove(user_id)
                async with self._state_lock:
                    self._running_user_ids.add(user_id)
                await asyncio.wait_for(job.runner(), timeout=REGISTER_QUEUE_JOB_TIMEOUT)
            except asyncio.TimeoutError:
                # 超时只代表本地等待被取消：远端(Emby)可能已部分完成创建，
                # 冷却期内该用户仍按"处理中"处理，不允许立刻重复提交
                async with self._state_lock:
                    self._timeout_cooldown_until[user_id] = time.monotonic() + REGISTER_QUEUE_TIMEOUT_COOLDOWN
                LOGGER.error(
                    f"注册队列任务超时 user={user_id}，任务已取消；"
                    f"为避免与可能已部分完成的注册重复创建，"
                    f"该用户将在 {REGISTER_QUEUE_TIMEOUT_COOLDOWN:.0f}s 冷却期内保持处理中，禁止重复提交"
                )
            except Exception as exc:
                LOGGER.exception(f"注册队列任务执行失败 user={user_id}: {exc}")
            finally:
                async with self._state_lock:
                    self._running_user_ids.discard(user_id)
                    if user_id not in self._timeout_cooldown_until or self._timeout_cooldown_until[user_id] <= time.monotonic():
                        self._active_user_ids.discard(user_id)
                self._queue.task_done()
register_create_queue = RegisterQueue()
