"""WorkerPool: pulls Tasks from queue and runs agent_loop concurrently."""
import asyncio
import time
from typing import TYPE_CHECKING

from app.utils.logger import get_logger
from .task import Task, TaskResult
from .queue import TaskQueue

if TYPE_CHECKING:
    from app.runtime.registry import ToolRegistry
    from app.runtime.dispatcher import ToolDispatcher

logger = get_logger(__name__)


class WorkerPool:
    def __init__(self, concurrency: int, registry: "ToolRegistry",
                 dispatcher: "ToolDispatcher"):
        self.concurrency = concurrency
        self.registry = registry
        self.dispatcher = dispatcher
        self.queue = TaskQueue()
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(concurrency)
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        for i in range(self.concurrency):
            t = asyncio.create_task(self._worker_loop(i), name=f"worker-{i}")
            self._workers.append(t)
        logger.info(f"WorkerPool started with concurrency={self.concurrency}")

    async def stop(self) -> None:
        self._running = False
        for t in self._workers:
            t.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        logger.info("WorkerPool stopped")

    async def submit(self, task: Task) -> None:
        await self.queue.put(task)

    async def _worker_loop(self, worker_id: int) -> None:
        from app.agents.loop import agent_loop  # late import avoids circular deps

        while self._running:
            try:
                task = await self.queue.get()
            except asyncio.CancelledError:
                break

            async with self._semaphore:
                task.status = "running"
                t0 = time.monotonic()
                try:
                    await self._run_task(task, agent_loop)
                    task.status = "done"
                except asyncio.CancelledError:
                    task.status = "cancelled"
                    raise
                except Exception as e:
                    task.status = "failed"
                    logger.error(f"[worker-{worker_id}] task {task.task_id} failed: {e}")
                    if task.result_queue:
                        await task.result_queue.put({
                            "type": "error",
                            "error": str(e),
                        })
                finally:
                    elapsed = int((time.monotonic() - t0) * 1000)
                    logger.info(f"[worker-{worker_id}] task {task.task_id} "
                                f"({task.status}) in {elapsed}ms")
                    self.queue.task_done()

    async def _run_task(self, task: Task, agent_loop) -> None:
        from app.memory.persistent_session import session_memory

        # Load conversation history so the LLM has context from prior turns
        history = await session_memory.get_history(task.session_id, limit=10)
        messages: list = [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": task.input["question"]})

        await agent_loop(messages, self.registry, self.dispatcher)

        final = next(
            (m for m in reversed(messages)
             if m.get("role") == "assistant" and m.get("content")),
            None,
        )

        # Persist this turn so subsequent requests can see it
        await session_memory.add_message(task.session_id, "user", task.input["question"])
        if final:
            await session_memory.add_message(task.session_id, "assistant", final["content"])

        if task.result_queue:
            await task.result_queue.put({
                "type": "done",
                "answer": final["content"] if final else "",
                "messages": messages,
            })

