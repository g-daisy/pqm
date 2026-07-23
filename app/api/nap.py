"""NoDeskClaw Agent Protocol (NAP) v1.0 接入层

实现平台要求的三个根级别接口：
  GET  /health  — 已在 main.py 处理，此处不重复
  GET  /meta    — Agent 元数据
  POST /stream  — NAP 格式 SSE 流式聊天
"""
import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

nap_router = APIRouter(tags=["NAP"])

_CHUNK_SIZE = 20


# =============================================================================
# 请求体模型
# =============================================================================
class NAPMessage(BaseModel):
    role: str
    content: str


class NAPStreamRequest(BaseModel):
    protocol_version: str = "1.0"
    request_id: str
    session_id: str
    user_id: str
    organization_id: Optional[str] = None
    messages: List[NAPMessage]
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# /meta
# =============================================================================
@nap_router.get("/meta")
async def nap_meta():
    """返回 Agent 元数据，平台 Sync 时调用"""
    return {
        "protocol_version": "1.0",
        "agent_id": "pqm-agent",
        "name": settings.APP_NAME,
        "description": "SIP 检验数据查询 Agent，支持自然语言 Text2SQL 和 RAG 知识库检索",
        "version": settings.APP_VERSION,
        "runtime": "agent_loop",
        "capabilities": ["SIP检验数据查询", "Text2SQL", "知识库检索", "品质异常分析"],
    }


# =============================================================================
# /stream
# =============================================================================
@nap_router.post("/stream")
async def nap_stream(request: NAPStreamRequest):
    """NAP 流式聊天接口（SSE）"""
    question = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            question = msg.content
            break

    if not question:
        async def _invalid():
            payload = json.dumps(
                {"code": "INVALID_REQUEST", "message": "请求中没有用户消息"},
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {payload}\n\n"

        return StreamingResponse(_invalid(), media_type="text/event-stream")

    async def generate():
        try:
            from app.main import worker_pool
            from app.runtime.task import Task

            result_queue: asyncio.Queue = asyncio.Queue()
            task = Task(
                task_type="chat",
                session_id=request.session_id,
                input={"question": question, "messages": []},
                result_queue=result_queue,
            )
            await worker_pool.submit(task)

            event = await asyncio.wait_for(result_queue.get(), timeout=120.0)
            answer = event.get("answer", "") if event.get("type") == "done" else ""

            for i in range(0, len(answer), _CHUNK_SIZE):
                chunk = answer[i: i + _CHUNK_SIZE]
                yield f"event: message\ndata: {chunk}\n\n"
                await asyncio.sleep(0.02)

            yield "event: done\ndata: complete\n\n"

        except asyncio.TimeoutError:
            payload = json.dumps({"code": "TIMEOUT", "message": "请求超时"}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"
        except Exception as e:
            logger.error(f"NAP stream error: {e}")
            payload = json.dumps({"code": "AGENT_ERROR", "message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
