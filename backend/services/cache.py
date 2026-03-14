from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

QUOTE_TTL_SECONDS = 30
COINGECKO_TTL_SECONDS = 60
NEWS_TTL_SECONDS = 300

T = TypeVar("T")


@dataclass
class CacheEntry:
    """Single cache entry with absolute expiration timestamp."""

    value: Any
    expires_at: datetime


class SimpleCache:
    """Lightweight async-safe in-memory cache with TTL support."""

    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= datetime.now(timezone.utc):
                del self._store[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store value with TTL in seconds."""
        expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        async with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=expiry)

    async def delete(self, key: str) -> None:
        """Remove one cache key if it exists."""
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Remove all cached entries."""
        async with self._lock:
            self._store.clear()

    async def get_or_set(self, key: str, ttl_seconds: int, fetcher: Callable[[], Awaitable[T]]) -> T:
        """Return cached value or fetch, store and return a fresh one."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await fetcher()
        await self.set(key, value, ttl_seconds)
        return value


shared_cache = SimpleCache()
