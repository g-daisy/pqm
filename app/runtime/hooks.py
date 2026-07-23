"""Lightweight event hook registry (before/after/error lifecycle)."""
import asyncio
from collections import defaultdict
from typing import Callable


class HookRegistry:
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable) -> None:
        self._hooks[event].append(handler)

    async def emit(self, event: str, *args, **kwargs) -> None:
        for handler in self._hooks.get(event, []):
            try:
                result = handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # hooks must not crash the main flow
