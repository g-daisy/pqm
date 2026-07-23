"""Tool: query_sip_database — Text-to-SQL via text2sql service."""
from app.tools.base import BaseTool
from app.services.text2sql import query as _query


class SqlTool(BaseTool):
    @property
    def name(self) -> str:
        return "query_sip_database"

    @property
    def description(self) -> str:
        return "将自然语言问题转化为 SQL 并查询 SIP 检验标准数据库，适用于查询具体的检验标准、规范、参数、客户零件信息等"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的问题，例如：北汽A柱出货包装标准是什么？",
                },
                "session_id": {
                    "type": "string",
                    "description": "会话 ID，用于读取对话历史上下文",
                    "default": "default",
                },
            },
            "required": ["question"],
        }

    async def run(self, *, question: str, session_id: str = "default") -> dict:
        return await _query(question, session_id)
