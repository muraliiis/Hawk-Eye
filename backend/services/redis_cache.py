"""
Redis cache wrapper using aioredis.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, TypeVar

import redis.asyncio as aioredis

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T")


class RedisCache:
    """Thin async wrapper around aioredis with JSON serialisation."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or settings.redis_url
        self._client: aioredis.Redis | None = None

    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    async def connect(self) -> None:
        self._client = await aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis connected: %s", self._url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Redis connection closed")

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("RedisCache is not connected. Call connect() first.")
        return self._client

    # ──────────────────────────────────────────────
    # Basic operations
    # ──────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Return the deserialised value for *key*, or None if missing / error."""
        try:
            raw = await self.client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis GET failed for key=%r: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Serialise *value* as JSON and store it with the given *ttl* (seconds)."""
        try:
            serialised = json.dumps(value, default=str)
            await self.client.set(key, serialised, ex=ttl)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis SET failed for key=%r: %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        """Delete *key*. Returns True if the key existed."""
        try:
            count = await self.client.delete(key)
            return count > 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis DELETE failed for key=%r: %s", key, exc)
            return False

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.client.exists(key))
        except Exception:  # noqa: BLE001
            return False

    # ──────────────────────────────────────────────
    # Cache-aside helper
    # ──────────────────────────────────────────────

    async def get_or_set(
        self,
        key: str,
        coro: Callable[[], Awaitable[T]],
        ttl: int = 300,
    ) -> T:
        """
        Return cached value for *key* if it exists; otherwise execute *coro*,
        cache the result, and return it.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        result = await coro()
        await self.set(key, result, ttl=ttl)
        return result

    # ──────────────────────────────────────────────
    # Convenience: ping
    # ──────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception:  # noqa: BLE001
            return False


# Module-level singleton — initialised during app lifespan
redis_cache: RedisCache = RedisCache()
