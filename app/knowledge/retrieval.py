"""RAG retrieval capability: query rewrite → RagFlow retrieval → LLM synthesis."""
import asyncio
from app.models.llm import create_chat_llm
from app.knowledge.ragflow_client import get_ragflow_client
from app.knowledge.rewrite import maybe_rewrite
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
- 每条只去掉多余的解释说明，保留核心结论和关键数值，控制在 30 字以内
- 若问题只问原因，只输出原因；只问对策，只输出对策；两者都问则在每个维度内先列"**原因：**"再列"**对策：**"
- 若某维度无相关内容则跳过

【检索文档】
{context}

【用户问题】
{question}"""


async def retrieve_and_synthesize(question: str, session_id: str) -> dict:
    """
    1. Maybe rewrite follow-up question to standalone
    2. Retrieve from RagFlow
    3. Synthesize with LLM in 5M1E format
    Returns {"answer": str, "search_question": str}
    """
    search_question = await maybe_rewrite(question, session_id)

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
        return {"answer": result, "search_question": search_question}

    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        return {"answer": f"RAG 检索失败: {str(e)}", "search_question": search_question}
