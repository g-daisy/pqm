"""ReAct while-True harness: the core agent loop."""
import json
import os
from app.models.llm import get_minimax_client
from app.runtime.registry import ToolRegistry
from app.runtime.dispatcher import ToolDispatcher
from app.utils.logger import get_logger

logger = get_logger(__name__)

MODEL = os.getenv("MiniMax_MODEL", "MiniMax-M2.7")

SYSTEM = """你是 PQM 质量检验知识库助手。通过调用工具完成用户的问题。

可用工具：
- query_sip_database：查询 SIP 检验标准（客户、零件、工序、检验项等结构化数据）
- search_knowledge_base：从知识库检索工序异常原因与对策
- get_database_schema：获取数据库表结构（当你不确定字段名时使用）

思考步骤：先判断用户意图，选择合适的工具，综合工具结果后回复。"""

_rounds_since_todo = 0


async def agent_loop(messages: list, registry: ToolRegistry,
                     dispatcher: ToolDispatcher) -> None:
    global _rounds_since_todo
    client = get_minimax_client()

    while True:
        reminder = []
        if _rounds_since_todo >= 3:
            reminder = [{"role": "user", "content":
                         "Reminder: 请更新你的进度追踪后再继续。"}]

        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM}] + messages + reminder,
            tools=registry.all_schemas(),
            max_tokens=8000,
        )
        msg = response.choices[0].message

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in (msg.tool_calls or [])],
        })

        if response.choices[0].finish_reason != "tool_calls":
            logger.info(f"agent_loop done (finish_reason={response.choices[0].finish_reason})")
            return

        logger.info(f"agent_loop: dispatching {len(msg.tool_calls)} tool call(s)")
        await dispatcher.dispatch(msg.tool_calls, messages)

        # Short-circuit: search_knowledge_base already synthesised a complete answer
        if (len(msg.tool_calls) == 1 and
                msg.tool_calls[0].function.name == "search_knowledge_base"):
            try:
                tool_content = json.loads(messages[-1]["content"])
                answer = tool_content.get("answer", "")
                if answer and not answer.startswith("RAG 检索失败") and answer != "未找到相关文档":
                    messages.append({"role": "assistant", "content": answer, "tool_calls": []})
                    logger.info("agent_loop: RAG answer used directly (skipped final LLM call)")
                    return
            except Exception:
                pass

        used_todo = any(tc.function.name == "todo_write"
                        for tc in (msg.tool_calls or []))
        _rounds_since_todo = 0 if used_todo else _rounds_since_todo + 1
