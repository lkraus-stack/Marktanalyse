from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

import httpx

from config import get_settings
from services.cache import COINGECKO_TTL_SECONDS, SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, InvalidSymbolError, RateLimitExceededError

logger = logging.getLogger("market_intelligence.services.coingecko")

SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
}


class CoinGeckoService:
    """Client for CoinGecko REST API with minute and monthly limits."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        settings = get_settings()
        self._api_key = settings.coingecko_api_key
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(base_url="https://api.coingecko.com/api/v3", timeout=httpx.Timeout(20.0))
        self._minute_window: deque[float] = deque()
        self._minute_lock = asyncio.Lock()
        self._monthly_limit = 10000
        self._monthly_count = 0
        self._month_key = self._current_month_key()
        self._monthly_lock = asyncio.Lock()

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    @staticmethod
    def map_symbol(symbol: str) -> str:
        """Map internal symbol to CoinGecko coin id."""
        normalized = symbol.lower().strip()
        if normalized in SYMBOL_TO_ID.values():
            return normalized
        return SYMBOL_TO_ID.get(symbol.upper(), normalized)

    async def get_price(self, ids: Union[str, Sequence[str]]) -> Dict[str, Any]:
        """Fetch spot price snapshot for one or many coin ids."""
        coin_ids = self._normalize_ids(ids)
        cache_key = "coingecko:price:{0}".format(",".join(sorted(coin_ids)))
        params = {"ids": ",".join(coin_ids), "vs_currencies": "usd", "include_24hr_vol": "true", "include_24hr_change": "true"}
        return await self._cache.get_or_set(cache_key, COINGECKO_TTL_SECONDS, lambda: self._request("/simple/price", params))

    async def get_market_data(self, ids: Union[str, Sequence[str]]) -> List[Dict[str, Any]]:
        """Fetch market metadata list for one or many coin ids."""
        coin_ids = self._normalize_ids(ids)
        cache_key = "coingecko:markets:{0}".format(",".join(sorted(coin_ids)))
        params = {"vs_currency": "usd", "ids": ",".join(coin_ids), "order": "market_cap_desc", "per_page": len(coin_ids), "page": 1}
        return await self._cache.get_or_set(cache_key, COINGECKO_TTL_SECONDS, lambda: self._request("/coins/markets", params))

    async def get_historical(self, coin_id: str, days: Union[int, str]) -> Dict[str, Any]:
        """Fetch historical market chart for one coin id."""
        mapped_id = self.map_symbol(coin_id)
        days_value = str(days)
        cache_key = "coingecko:historical:{0}:{1}".format(mapped_id, days_value)
        params = {"vs_currency": "usd", "days": days_value}
        endpoint = "/coins/{0}/market_chart".format(mapped_id)
        return await self._cache.get_or_set(cache_key, COINGECKO_TTL_SECONDS, lambda: self._request(endpoint, params))

    async def _request(self, endpoint: str, params: Dict[str, Any]) -> Any:
        for attempt in range(3):
            try:
                await self._consume_rate_limits()
                headers = self._build_headers()
                response = await self._client.get(endpoint, params=params, headers=headers)
                if response.status_code == 429:
                    raise RateLimitExceededError("CoinGecko rate limit reached.")
                if response.status_code == 404:
                    raise InvalidSymbolError("CoinGecko id not found.")
                response.raise_for_status()
                return response.json()
            except (RateLimitExceededError, InvalidSymbolError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("CoinGecko request failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("CoinGecko request failed due to network error.") from exc

        raise ExternalAPIError("CoinGecko request failed after retries.")

    async def _consume_rate_limits(self) -> None:
        await self._consume_monthly_limit()
        await self._consume_minute_limit()

    async def _consume_minute_limit(self) -> None:
        async with self._minute_lock:
            now = time.monotonic()
            while self._minute_window and now - self._minute_window[0] >= 60:
                self._minute_window.popleft()
            if len(self._minute_window) >= 30:
                raise RateLimitExceededError("CoinGecko minute limit exceeded.")
            self._minute_window.append(now)

    async def _consume_monthly_limit(self) -> None:
        async with self._monthly_lock:
            month_key = self._current_month_key()
            if month_key != self._month_key:
                self._month_key = month_key
                self._monthly_count = 0
            if self._monthly_count >= self._monthly_limit:
                raise RateLimitExceededError("CoinGecko monthly limit exceeded.")
            self._monthly_count += 1

    def _current_month_key(self) -> str:
        now = datetime.now(timezone.utc)
        return "{0:04d}-{1:02d}".format(now.year, now.month)

    def _build_headers(self) -> Dict[str, str]:
        if not self._api_key:
            return {}
        return {"x-cg-demo-api-key": self._api_key}

    def _normalize_ids(self, ids: Union[str, Sequence[str]]) -> List[str]:
        values: Iterable[str]
        if isinstance(ids, str):
            values = [item.strip() for item in ids.split(",") if item.strip()]
        else:
            values = ids
        mapped = [self.map_symbol(item) for item in values]
        if not mapped:
            raise InvalidSymbolError("No CoinGecko ids provided.")
        logger.debug("CoinGecko ids resolved.", extra={"event": "coingecko_ids", "ids": ",".join(mapped)})
        return mapped
