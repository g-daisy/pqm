"""Agent API routes — WorkerPool + agent_loop based."""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.memory.persistent_session import session_memory
from app.api.monitor import increment_query_count
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


# =============================================================================
# 请求/响应模型
# =============================================================================
class QueryRequest(BaseModel):
    question: str = Field(..., description="用户问题")
    session_id: str = Field(default="default", description="Session ID")
    mode: str = Field(default="auto", description="模式")


class QueryResponse(BaseModel):
    success: bool
    question: str
    session_id: str
    answer: Optional[str] = None
    cancelled: bool = False


class HistoryResponse(BaseModel):
    session_id: str
    history: List[Dict[str, Any]]
    turn_count: int


class HealthResponse(BaseModel):
    status: str
    memory_sessions: int


class SessionInfo(BaseModel):
    session_id: str
    title: Optional[str] = None
    turn_count: int = 0
    last_active: Optional[str] = None


class CreateSessionRequest(BaseModel):
    session_id: str
    title: str = ""


# =============================================================================
# 内部工具
# =============================================================================
async def _submit_and_wait(question: str, session_id: str) -> asyncio.Queue:
    from app.main import worker_pool
    from app.runtime.task import Task

    result_queue: asyncio.Queue = asyncio.Queue()
    task = Task(
        task_type="chat",
        session_id=session_id,
        input={"question": question, "messages": []},
        result_queue=result_queue,
    )
    await worker_pool.submit(task)
    return result_queue


async def _stream_from_queue(queue: asyncio.Queue):
    """Yield SSE data lines from a WorkerPool result queue."""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=120.0)
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'error': '请求超时'}, ensure_ascii=False)}\n\n"
            break

        event_type = event.get("type")
        if event_type == "done":
            payload = json.dumps({
                "type": "done",
                "answer": event.get("answer", ""),
                "cancelled": False,
            }, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            break
        elif event_type == "error":
            yield f"data: {json.dumps({'type': 'error', 'error': event.get('error', '')}, ensure_ascii=False)}\n\n"
            break


# =============================================================================
# API 端点
# =============================================================================
@router.post("/stream")
async def stream_query(request: QueryRequest):
    """流式查询接口（SSE）— WorkerPool + agent_loop"""
    queue = await _submit_and_wait(request.question, request.session_id)
    increment_query_count()
    return StreamingResponse(
        _stream_from_queue(queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/stream2")
async def stream_query_v2(request: QueryRequest):
    """ReAct harness SSE 流式接口 — WorkerPool + agent_loop"""
    queue = await _submit_and_wait(request.question, request.session_id)
    increment_query_count()
    return StreamingResponse(
        _stream_from_queue(queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """同步查询接口 — WorkerPool + agent_loop"""
    try:
        queue = await _submit_and_wait(request.question, request.session_id)
        event = await asyncio.wait_for(queue.get(), timeout=120.0)
        answer = event.get("answer", "") if event.get("type") == "done" else ""
        success = event.get("type") == "done"
        increment_query_count()
        return QueryResponse(
            success=success,
            question=request.question,
            session_id=request.session_id,
            answer=answer,
        )
    except asyncio.TimeoutError:
        return QueryResponse(
            success=False,
            question=request.question,
            session_id=request.session_id,
            answer="请求超时",
        )
    except Exception as e:
        logger.error(f"Agent query failed: {e}")
        return QueryResponse(
            success=False,
            question=request.question,
            session_id=request.session_id,
            answer=f"查询失败: {e}",
        )


@router.get("/sessions", response_model=List[SessionInfo])
async def list_sessions(limit: int = 20):
    """列出所有会话（按最近活跃倒序）"""
    rows = await session_memory.list_sessions(limit=limit)
    return rows


@router.post("/sessions", response_model=SessionInfo)
async def create_session(body: CreateSessionRequest):
    """创建新会话"""
    await session_memory.create_session(body.session_id, body.title)
    info = await session_memory.get_session_info(body.session_id)
    return info or {"session_id": body.session_id, "title": body.title, "turn_count": 0}


@router.get("/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str, limit: int = 10):
    """获取对话历史"""
    history = await session_memory.get_history(session_id, limit=limit * 2)
    info = await session_memory.get_session_info(session_id)
    turn_count = info.get("turn_count", 0) if info else 0
    return HistoryResponse(session_id=session_id, history=history, turn_count=turn_count)


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """清除会话历史"""
    await session_memory.clear_session(session_id)
    return {"message": f"Session {session_id} 已清除"}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """检查 Agent 服务状态"""
    sessions = await session_memory.list_sessions(limit=1000)
    return HealthResponse(
        status="healthy",
        memory_sessions=len(sessions),
    )
