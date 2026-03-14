from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from services.cache import QUOTE_TTL_SECONDS, SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, InvalidSymbolError, RateLimitExceededError
from services.rate_limit import SlidingWindowRateLimiter

logger = logging.getLogger("market_intelligence.services.stocktwits")


class StockTwitsService:
    """Client for StockTwits public streams."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(
            base_url="https://api.stocktwits.com/api/2",
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": "markt-intelligence/0.1"},
        )
        self._rate_limiter = SlidingWindowRateLimiter(limit=180, window_seconds=3600, wait_for_slot=False)

    async def close(self) -> None:
        """Close HTTP client resources."""
        await self._client.aclose()

    async def get_symbol_stream(self, symbol: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch symbol stream messages."""
        normalized = symbol.upper().strip()
        bounded_limit = max(1, min(limit, 30))
        cache_key = "stocktwits:symbol:{0}:{1}".format(normalized, bounded_limit)
        return await self._cache.get_or_set(
            cache_key,
            QUOTE_TTL_SECONDS,
            lambda: self._fetch_symbol_stream(normalized, bounded_limit),
        )

    async def get_trending(self) -> List[Dict[str, Any]]:
        """Fetch currently trending symbols."""
        cache_key = "stocktwits:trending"
        return await self._cache.get_or_set(cache_key, QUOTE_TTL_SECONDS, self._fetch_trending)

    async def _fetch_symbol_stream(self, symbol: str, limit: int) -> List[Dict[str, Any]]:
        payload = await self._request("/streams/symbol/{0}.json".format(symbol), {"limit": limit})
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            raise InvalidSymbolError("Unexpected StockTwits symbol payload.")
        return [self._normalize_message(item, symbol) for item in messages]

    async def _fetch_trending(self) -> List[Dict[str, Any]]:
        payload = await self._request("/trending/symbols.json", {})
        symbols = payload.get("symbols", [])
        if not isinstance(symbols, list):
            raise ExternalAPIError("Unexpected StockTwits trending payload.")
        return symbols

    async def _request(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                await self._rate_limiter.acquire()
                response = await self._client.get(path, params=params)
                if response.status_code == 429:
                    raise RateLimitExceededError("StockTwits rate limit reached.")
                if response.status_code == 404:
                    raise InvalidSymbolError("StockTwits symbol not found.")
                response.raise_for_status()
                return response.json()
            except (RateLimitExceededError, InvalidSymbolError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("StockTwits request failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("StockTwits request failed due to network error.") from exc
        raise ExternalAPIError("StockTwits request failed after retries.")

    def _normalize_message(self, item: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        sentiment = item.get("entities", {}).get("sentiment")
        basic = None
        if isinstance(sentiment, dict):
            basic = sentiment.get("basic")
        return {
            "id": item.get("id"),
            "symbol": symbol,
            "body": item.get("body") or "",
            "created_at": item.get("created_at"),
            "user": (item.get("user") or {}).get("username"),
            "source_url": "https://stocktwits.com/message/{0}".format(item.get("id")),
            "basic_sentiment": basic,
        }
