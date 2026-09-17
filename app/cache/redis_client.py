"""异步 Redis 客户端单例，用于 RAG 问答缓存。"""
import hashlib
import json
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def _cache_key(question: str) -> str:
    h = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"pqm:rag:{h}"


async def get_cached(question: str) -> Optional[dict]:
    try:
        raw = await get_redis().get(_cache_key(question))
        if raw:
            logger.info(f"RAG cache HIT: {question[:50]}...")
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"Redis get failed (ignored): {e}")
    return None


async def set_cached(question: str, value: dict) -> None:
    try:
        await get_redis().setex(
            _cache_key(question),
            settings.REDIS_CACHE_TTL,
            json.dumps(value, ensure_ascii=False),
        )
        logger.info(f"RAG cache SET: {question[:50]}... (TTL={settings.REDIS_CACHE_TTL}s)")
    except Exception as e:
        logger.warning(f"Redis set failed (ignored): {e}")
