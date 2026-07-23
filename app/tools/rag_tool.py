"""Tool: search_knowledge_base — RAG retrieval via knowledge/ layer."""
from app.tools.base import BaseTool
from app.knowledge.retrieval import retrieve_and_synthesize


class RagTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_knowledge_base"

    @property
    def description(self) -> str:
        return "从知识库检索工序异常的发生原因和解决对策，适用于包含'原因/解决/异常/缺陷/对策/为什么'等关键词的问题"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的问题，例如：热压工序出现暗裂的原因是什么？",
                },
                "session_id": {
                    "type": "string",
                    "description": "会话 ID，用于追问改写",
                    "default": "default",
                },
            },
            "required": ["question"],
        }

    async def run(self, *, question: str, session_id: str = "default") -> dict:
        result = await retrieve_and_synthesize(question, session_id)
        return {
            "answer": result["answer"],
            "search_question": result["search_question"],
        }
