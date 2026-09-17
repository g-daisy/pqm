"""RAG retrieval capability: cache check → query rewrite → RagFlow retrieval → LLM synthesis."""
import asyncio
from app.models.llm import create_chat_llm
from app.knowledge.ragflow_client import get_ragflow_client
from app.knowledge.rewrite import maybe_rewrite
from app.cache.redis_client import get_cached, set_cached
from app.utils.logger import get_logger
from langchain_core.messages import HumanMessage, SystemMessage

logger = get_logger(__name__)

RAG_SYNTHESIS_PROMPT = """你是质量检验知识库专家。根据检索文档回答用户问题。

【输出格式】
按 5M1E 维度组织，格式如下：

### 👤 人员
- 条目

---

### ⚙️ 设备
- 条目

---

（以此类推：📦 材料 / 📋 方法 / 📐 测量 / 🌡️ 环境）

【规则】
- 保留文档中所有条目，不得删减条数
- 每条只去掉多余的解释说明，保留核心结论和关键数值，控制在 30 ��以内
- 若问题只问原因，只输出原因；只问对策，只输出对策；两者都问则在每个维度内先列"**原因：**"再列"**对策：**"
- 若某维度无相关内容则跳过

【检索文档】
{context}

【用户问题】
{question}"""


async def retrieve_and_synthesize(question: str, session_id: str) -> dict:
    """
    Flow:
    1. Check cache with original question (skip rewrite on cache hit)
    2. Maybe rewrite follow-up question to standalone
    3. Check cache with rewritten question
    4. Retrieve from RagFlow + synthesize with LLM
    5. Cache result under both original and rewritten question keys
    Returns {"answer": str, "search_question": str}
    """
    # ① 先用原始问题查缓存 — 命中则完全跳过 rewrite 和检索
    cached = await get_cached(question)
    if cached:
        return cached

    search_question = await maybe_rewrite(question, session_id)

    # ② 改写后的问题再查一次（追问展开后 key 可能不同）
    if search_question != question:
        cached = await get_cached(search_question)
        if cached:
            await set_cached(question, cached)
            return cached

    try:
        client = get_ragflow_client()
        raw = await client.retrieval(query=search_question, top_k=5)

        chunks = raw.get("chunks", [])
        answer = raw.get("answer", "")

        if not chunks and not answer:
            return {"answer": "未找到相关文档", "search_question": search_question}

        context = "\n\n".join(c.get("content", "") for c in chunks) if chunks else answer

        llm = create_chat_llm()
        result = await asyncio.to_thread(llm.invoke, [
            SystemMessage(content="你是质量检验专家，擅长提炼知识库内容。"),
            HumanMessage(content=RAG_SYNTHESIS_PROMPT.format(
                context=context, question=search_question)),
        ])

        logger.info(f"RAG synthesis done, answer length: {len(result)} chars")
        result_dict = {"answer": result, "search_question": search_question}

        # ③ 同时缓存原始问题和改写后的问题，保证两种问法下次都能命中
        await set_cached(search_question, result_dict)
        if question != search_question:
            await set_cached(question, result_dict)

        return result_dict

    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        return {"answer": f"RAG 检索失败: {str(e)}", "search_question": search_question}
