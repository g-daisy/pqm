"""Tool: get_database_schema — returns SIP table schema for LLM context."""
from app.tools.base import BaseTool
from app.db.schema_loader import schema_loader
from app.utils.logger import get_logger

logger = get_logger(__name__)

_cache: dict = {}


class SchemaTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_database_schema"

    @property
    def description(self) -> str:
        return "获取 sip_records 数据库表结构和字段说明，当不确定字段名时使用"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def run(self) -> dict:
        if not _cache:
            _cache["schema"] = schema_loader.generate_schema_context()
            _cache["synonyms"] = schema_loader.generate_synonym_context()
            logger.info("Schema loaded and cached")
        return {
            "schema": _cache["schema"],
            "synonyms": _cache["synonyms"],
        }
