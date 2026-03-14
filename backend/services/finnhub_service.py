from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
import websockets

from config import get_settings
from services.cache import QUOTE_TTL_SECONDS, SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, InvalidSymbolError, RateLimitExceededError

logger = logging.getLogger("market_intelligence.services.finnhub")


class MinuteSemaphoreLimiter:
    """Semaphore-based limiter that refills every 60 seconds."""

    def __init__(self, permits_per_minute: int) -> None:
        self._semaphore = asyncio.BoundedSemaphore(permits_per_minute)
        self._permits_per_minute = permits_per_minute
        self._reset_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire one request slot from the current minute window."""
        await self._semaphore.acquire()
        await self._ensure_reset_task()

    async def _ensure_reset_task(self) -> None:
        async with self._lock:
            if self._reset_task is None or self._reset_task.done():
                self._reset_task = asyncio.create_task(self._reset_window())

    async def _reset_window(self) -> None:
        await asyncio.sleep(60)
        for _ in range(self._permits_per_minute):
            try:
                self._semaphore.release()
            except ValueError:
                break


class FinnhubService:
    """Client for Finnhub REST and WebSocket APIs."""

    def __init__(self, api_key: Optional[str] = None, cache: Optional[SimpleCache] = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.finnhub_api_key
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(base_url="https://finnhub.io/api/v1", timeout=httpx.Timeout(15.0))
        self._limiter = MinuteSemaphoreLimiter(55)

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    def has_api_key(self) -> bool:
        """Return True when a Finnhub API key is configured."""
        return bool(self._api_key)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest quote for one stock symbol."""
        cache_key = "finnhub:quote:{symbol}".format(symbol=symbol.upper())
        return await self._get_with_cache(cache_key, QUOTE_TTL_SECONDS, self._request_quote, symbol)

    async def get_candles(self, symbol: str, resolution: str, from_ts: int, to_ts: int) -> Dict[str, Any]:
        """Fetch OHLC candles for one symbol/time window."""
        cache_key = "finnhub:candles:{0}:{1}:{2}:{3}".format(symbol.upper(), resolution, from_ts, to_ts)
        return await self._get_with_cache(
            cache_key,
            QUOTE_TTL_SECONDS,
            self._request_candles,
            symbol,
            resolution,
            from_ts,
            to_ts,
        )

    async def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Fetch company profile metadata."""
        cache_key = "finnhub:profile:{symbol}".format(symbol=symbol.upper())
        return await self._get_with_cache(cache_key, 300, self._request_company_profile, symbol)

    async def connect_finnhub_ws(
        self,
        symbols: List[str],
        on_message: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """Connect to Finnhub WebSocket stream with reconnect logic."""
        if len(symbols) > 50:
            raise ValueError("Finnhub WebSocket supports at most 50 symbols.")
        api_key = self._require_api_key()
        subscribe_symbols = [symbol.upper() for symbol in symbols]

        while True:
            try:
                ws_url = "wss://ws.finnhub.io?token={0}".format(api_key)
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
                    for symbol in subscribe_symbols:
                        await websocket.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                    async for message in websocket:
                        payload = json.loads(message)
                        if on_message is not None:
                            await on_message(payload)
            except asyncio.CancelledError:
                logger.info("Finnhub WebSocket task cancelled.", extra={"event": "finnhub_ws_cancelled"})
                raise
            except Exception:
                logger.exception("Finnhub WebSocket disconnected; reconnecting.", extra={"event": "finnhub_ws_retry"})
                await asyncio.sleep(5)

    async def _get_with_cache(self, key: str, ttl: int, fetcher: Callable[..., Awaitable[Dict[str, Any]]], *args: Any) -> Dict[str, Any]:
        async def _fetch() -> Dict[str, Any]:
            return await fetcher(*args)

        return await self._cache.get_or_set(key, ttl, _fetch)

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise ExternalAPIError("FINNHUB_API_KEY is missing.")
        return self._api_key

    async def _request_quote(self, symbol: str) -> Dict[str, Any]:
        payload = await self._request("quote", {"symbol": symbol.upper()})
        if not payload or float(payload.get("c", 0.0)) <= 0:
            raise InvalidSymbolError("No quote data for symbol {0}.".format(symbol))
        return payload

    async def _request_candles(self, symbol: str, resolution: str, from_ts: int, to_ts: int) -> Dict[str, Any]:
        payload = await self._request(
            "stock/candle",
            {"symbol": symbol.upper(), "resolution": resolution, "from": from_ts, "to": to_ts},
        )
        if payload.get("s") == "no_data":
            raise InvalidSymbolError("No candles returned for symbol {0}.".format(symbol))
        return payload

    async def _request_company_profile(self, symbol: str) -> Dict[str, Any]:
        payload = await self._request("stock/profile2", {"symbol": symbol.upper()})
        if not payload:
            raise InvalidSymbolError("No company profile returned for symbol {0}.".format(symbol))
        return payload

    async def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        request_params = dict(params)
        request_params["token"] = self._require_api_key()

        for attempt in range(3):
            try:
                await self._limiter.acquire()
                response = await self._client.get(endpoint, params=request_params)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("error"):
                    raise ExternalAPIError(payload["error"])
                return payload
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    raise RateLimitExceededError("Finnhub rate limit reached.") from exc
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Finnhub request failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Finnhub request failed due to network error.") from exc

        raise ExternalAPIError("Finnhub request failed after retries.")
