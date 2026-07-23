"""Tool Contract: executes LLM tool_calls and appends results to messages."""
import json
from typing import Any
from .registry import ToolRegistry
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def dispatch(self, tool_calls: list[Any], messages: list) -> None:
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            logger.info(f"Dispatching tool: {name}({list(args.keys())})")
            try:
                tool = self.registry.get(name)
                result = await tool.run(**args)
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}")
                result = {"error": str(e)}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
