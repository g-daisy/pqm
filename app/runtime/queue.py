"""Priority task queue wrapping asyncio.PriorityQueue."""
import asyncio
from .task import Task


class TaskQueue:
    def __init__(self):
        self._q: asyncio.PriorityQueue = asyncio.PriorityQueue()

    async def put(self, task: Task) -> None:
        await self._q.put((task.priority, task))

    async def get(self) -> Task:
        _, task = await self._q.get()
        return task

    def task_done(self) -> None:
        self._q.task_done()

    def size(self) -> int:
        return self._q.qsize()
