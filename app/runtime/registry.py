"""Tool registry: maps tool names to BaseTool instances."""
from app.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def all_schemas(self) -> list[dict]:
        return [{"type": "function", "function": t.schema} for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())
