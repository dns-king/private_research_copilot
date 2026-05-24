from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


TaskHandler = Callable[..., Awaitable[Any] | Any]


@dataclass
class QueuedTask:
    name: str
    handler: TaskHandler
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    retries_left: int


class BackgroundTaskQueue:
    def __init__(self, default_retries: int = 2) -> None:
        self.default_retries = default_retries
        self._queue: asyncio.Queue[QueuedTask] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._logger = logging.getLogger("app.tasks")
        self._running = False

    async def start(self, workers: int = 1) -> None:
        if self._running:
            return
        self._running = True
        self._workers = [asyncio.create_task(self._worker(i)) for i in range(workers)]

    async def stop(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def enqueue(
        self,
        name: str,
        handler: TaskHandler,
        *args: Any,
        retries: int | None = None,
        **kwargs: Any,
    ) -> None:
        await self._queue.put(
            QueuedTask(
                name=name,
                handler=handler,
                args=args,
                kwargs=kwargs,
                retries_left=self.default_retries if retries is None else retries,
            )
        )

    async def _worker(self, worker_id: int) -> None:
        while True:
            task = await self._queue.get()
            try:
                self._logger.info("task started: %s worker=%s", task.name, worker_id)
                result = task.handler(*task.args, **task.kwargs)
                if inspect.isawaitable(result):
                    await result
                self._logger.info("task completed: %s", task.name)
            except asyncio.CancelledError:
                raise
            except Exception:
                if task.retries_left > 0:
                    self._logger.exception(
                        "task failed, retrying: %s retries_left=%s",
                        task.name,
                        task.retries_left,
                    )
                    task.retries_left -= 1
                    await asyncio.sleep(1)
                    await self._queue.put(task)
                else:
                    self._logger.exception("task failed permanently: %s", task.name)
            finally:
                self._queue.task_done()

