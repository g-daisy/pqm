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
    1，先用原始问题检查缓存（如果缓存命中，就跳过重写步骤）
    2，视情况将后续追问重写成独立的问题
    3,用重写后的问题再次检查缓存
    4,从 RagFlow 中检索信息，并结合大语言模型（LLM）生成回答
    5,将结果分别以原始问题和重写后的问题作为键（key）存入缓存
    6,最后返回一个包含 answer（回答内容）和 search_question（实际用于搜索的问题）的对象
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
