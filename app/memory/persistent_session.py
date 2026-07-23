"""Persistent session memory backed by PostgreSQL (chat_sessions + chat_messages)."""
from typing import List, Optional
from app.db.connection import execute, fetch_all, fetch_one
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PersistentSessionMemory:
    """DB-backed session memory; same interface as SessionMemory."""

    async def create_session(self, session_id: str, title: str = "") -> None:
        await execute(
            """INSERT INTO chat_sessions (session_id, title)
               VALUES ($1, $2)
               ON CONFLICT (session_id) DO NOTHING""",
            (session_id, title),
        )

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        # Ensure session row exists first
        await execute(
            """INSERT INTO chat_sessions (session_id, title)
               VALUES ($1, '')
               ON CONFLICT (session_id) DO NOTHING""",
            (session_id,),
        )
        # Set title from first user message; always bump last_active
        if role == "user":
            await execute(
                """UPDATE chat_sessions
                   SET title       = CASE WHEN title = '' THEN $2 ELSE title END,
                       last_active = NOW(),
                       turn_count  = turn_count + 1
                   WHERE session_id = $1""",
                (session_id, content[:30]),
            )
        else:
            await execute(
                "UPDATE chat_sessions SET last_active = NOW() WHERE session_id = $1",
                (session_id,),
            )
        await execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES ($1, $2, $3)",
            (session_id, role, content),
        )

    async def get_history(self, session_id: str, limit: int = 10) -> List[dict]:
        rows = await fetch_all(
            """SELECT role, content, created_at::text AS timestamp
               FROM chat_messages
               WHERE session_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            (session_id, limit),
        )
        return list(reversed(rows))

    async def get_context_for_llm(self, session_id: str, limit: int = 5) -> str:
        history = await self.get_history(session_id, limit=limit * 2)
        if not history:
            return ""
        lines = ["【对话历史】"]
        for msg in history:
            label = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{label}: {msg['content']}")
        return "\n".join(lines)

    async def list_sessions(self, limit: int = 20) -> List[dict]:
        return await fetch_all(
            """SELECT session_id, title, turn_count, last_active::text AS last_active
               FROM chat_sessions
               ORDER BY last_active DESC
               LIMIT $1""",
            (limit,),
        )

    async def clear_session(self, session_id: str) -> None:
        await execute(
            "DELETE FROM chat_sessions WHERE session_id = $1",
            (session_id,),
        )

    async def get_session_info(self, session_id: str) -> Optional[dict]:
        return await fetch_one(
            """SELECT session_id, title, turn_count, last_active::text AS last_active
               FROM chat_sessions WHERE session_id = $1""",
            (session_id,),
        )


session_memory = PersistentSessionMemory()
