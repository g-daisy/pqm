"""APScheduler wrapper: fires scheduled tasks into the WorkerPool queue."""
from typing import TYPE_CHECKING

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from .worker import WorkerPool

logger = get_logger(__name__)


class Scheduler:
    def __init__(self, worker_pool: "WorkerPool"):
        self.worker_pool = worker_pool
        self._scheduler = None

    async def start(self) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._scheduler = AsyncIOScheduler()
            self._scheduler.start()
            logger.info("Scheduler started")
        except ImportError:
            logger.warning("apscheduler not installed — Scheduler disabled")

    async def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def add_cron_job(self, job_id: str, cron_expr: str,
                     question: str, session_id: str = "scheduler") -> None:
        if self._scheduler is None:
            return
        minute, hour, dom, month, dow = cron_expr.split()
        self._scheduler.add_job(
            self._dispatch,
            "cron",
            id=job_id,
            minute=minute, hour=hour, day=dom, month=month, day_of_week=dow,
            kwargs={"question": question, "session_id": session_id},
            replace_existing=True,
        )
        logger.info(f"Scheduled job '{job_id}' with cron '{cron_expr}'")

    async def _dispatch(self, question: str, session_id: str) -> None:
        from .task import Task
        task = Task(
            task_type="scheduled",
            session_id=session_id,
            input={"question": question, "messages": []},
            priority=8,
        )
        await self.worker_pool.submit(task)
        logger.info(f"Scheduled task submitted: {question[:40]}")
