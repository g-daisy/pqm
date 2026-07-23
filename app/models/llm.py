"""LLM clients: MiniMax OpenAI-compat client (agent_loop) + LangChain wrapper (services)."""
import os
from typing import Optional, Any

from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic


# ── AsyncOpenAI client (used by agent_loop) ────────────────────────────────
_client = None


def get_minimax_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI  # lazy: only needed when agent_loop runs
        api_key = os.getenv("MiniMax_API_KEY", "")
        base_url = os.getenv("MiniMax_BASE_URL", "https://api.minimaxi.com/anthropic")
        openai_base_url = base_url.replace("/anthropic", "/v1")
        _client = AsyncOpenAI(api_key=api_key, base_url=openai_base_url)
    return _client


class BaseLLM:
    """LangChain-based LLM wrapper (synchronous invoke, used by services)."""

    def __init__(self):
        self._llm: Optional[ChatAnthropic] = None

    @property
    def llm(self) -> ChatAnthropic:
        if self._llm is None:
            self._llm = ChatAnthropic(
                model=os.getenv("MiniMax_MODEL", "MiniMax-M2.7"),
                anthropic_api_key=os.getenv("MiniMax_API_KEY", ""),
                base_url=os.getenv("MiniMax_BASE_URL", "https://api.minimaxi.com/anthropic"),
                max_tokens=4096,
                temperature=0.7,
            )
        return self._llm

    def invoke(self, messages: list[Any]) -> str:
        response = self.llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text", "")
            return ""
        return str(content)


_shared_llm: Optional[BaseLLM] = None


def create_chat_llm() -> BaseLLM:
    """Return process-level singleton BaseLLM (for services/knowledge)."""
    global _shared_llm
    if _shared_llm is None:
        _shared_llm = BaseLLM()
    return _shared_llm
