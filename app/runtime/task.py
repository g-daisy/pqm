"""Task Contract: data model passed from WorkerPool to agent_loop."""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    task_type: str                              # "chat" | "scheduled"
    session_id: str
    input: dict                                 # {"question": "...", "messages": [...]}
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 5                           # lower = higher priority
    result_queue: Optional[asyncio.Queue] = None  # SSE write-back channel
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __lt__(self, other: "Task") -> bool:
        return self.priority < other.priority


@dataclass
class TaskResult:
    success: bool
    data: dict
    error: Optional[str] = None
    duration_ms: int = 0
