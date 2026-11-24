"""Query rewrite for follow-up questions: ensures retrieval gets a complete question."""
import asyncio
from app.models.llm import create_chat_llm
from app.memory.short_term_memory import session_memory
from app.utils.logger import get_logger
from langchain_core.messages import HumanMessage

logger = get_logger(__name__)

QUERY_REWRITE_PROMPT = """你是对话理解专家。结合对话历史，将用户的追问改写为完整独立的问题。
只输出改写后的问题，不要任何解释或其他内容。若当前问题已经完整清晰，则原样输出。

{history}

【当前问题】
{question}"""


def _is_followup(question: str) -> bool:
    if len(question) <= 15:
        return True
    q = question.strip()
    followup_starts = ["那", "再", "以及", "那么", "那对策", "那怎么", "那如何", "还有"]
    followup_ends = ["呢", "呢？", "呢?"]
    followup_contains = ["对策", "怎么处理", "如何解决", "那怎么办"]
    return (
        any(q.startswith(w) for w in followup_starts)
        or any(q.endswith(w) for w in followup_ends)
        or any(w in q for w in followup_contains)
    )


async def maybe_rewrite(question: str, session_id: str) -> str:
    """返回问题的独立版本，并结合历史对话将后续追问重写为独立问题."""
    history_context = session_memory.get_context_for_llm(session_id, limit=3)
    if not history_context or not _is_followup(question):
        return question
    try:
        llm = create_chat_llm()
        rewritten = await asyncio.to_thread(llm.invoke, [HumanMessage(
            content=QUERY_REWRITE_PROMPT.format(
                history=history_context, question=question)
        )])
        if rewritten and rewritten.strip():
            logger.info(f"Query rewrite: '{question}' → '{rewritten.strip()}'")
            return rewritten.strip()
    except Exception as e:
        logger.warning(f"Query rewrite failed, using original: {e}")
    return question
