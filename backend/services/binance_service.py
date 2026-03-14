from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
import websockets

from services.cache import QUOTE_TTL_SECONDS, SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, InvalidSymbolError, RateLimitExceededError

logger = logging.getLogger("market_intelligence.services.binance")

SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT",
}


class BinanceService:
    """Client for Binance REST and WebSocket market data APIs."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(base_url="https://api.binance.com/api/v3/", timeout=httpx.Timeout(15.0))

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    @staticmethod
    def map_symbol(symbol: str) -> str:
        """Map internal symbol notation to Binance trading pairs."""
        normalized = symbol.upper().replace("/", "")
        if normalized.endswith("USDT"):
            return normalized
        return SYMBOL_MAP.get(normalized, "{0}USDT".format(normalized))

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch 24h ticker statistics for one symbol."""
        mapped = self.map_symbol(symbol)
        cache_key = "binance:ticker:{0}".format(mapped)
        return await self._cache.get_or_set(cache_key, QUOTE_TTL_SECONDS, lambda: self._request("ticker/24hr", {"symbol": mapped}))

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
    ) -> List[List[Any]]:
        """Fetch klines/candles for one symbol and interval."""
        mapped = self.map_symbol(symbol)
        bounded_limit = max(1, min(limit, 1000))
        start_key = str(start_time_ms) if start_time_ms is not None else "none"
        end_key = str(end_time_ms) if end_time_ms is not None else "none"
        cache_key = "binance:klines:{0}:{1}:{2}:{3}:{4}".format(
            mapped,
            interval,
            bounded_limit,
            start_key,
            end_key,
        )
        params: Dict[str, Any] = {"symbol": mapped, "interval": interval, "limit": bounded_limit}
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        return await self._cache.get_or_set(
            cache_key,
            QUOTE_TTL_SECONDS,
            lambda: self._request("klines", params),
        )

    async def get_orderbook(self, symbol: str, limit: int) -> Dict[str, Any]:
        """Fetch order book depth snapshot for one symbol."""
        mapped = self.map_symbol(symbol)
        bounded_limit = max(5, min(limit, 1000))
        cache_key = "binance:orderbook:{0}:{1}".format(mapped, bounded_limit)
        return await self._cache.get_or_set(
            cache_key,
            QUOTE_TTL_SECONDS,
            lambda: self._request("depth", {"symbol": mapped, "limit": bounded_limit}),
        )

    async def connect_binance_ws(
        self,
        symbols: List[str],
        on_message: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """Connect Binance WebSocket streams with automatic reconnect."""
        mapped_symbols = [self.map_symbol(symbol).lower() for symbol in symbols]
        streams = []
        for symbol in mapped_symbols:
            streams.append("{0}@kline_1m".format(symbol))
            streams.append("{0}@ticker".format(symbol))

        while True:
            try:
                async with websockets.connect("wss://stream.binance.com:9443/ws/", ping_interval=20, ping_timeout=20) as websocket:
                    subscribe = {"method": "SUBSCRIBE", "params": streams, "id": 1}
                    await websocket.send(json.dumps(subscribe))
                    async for message in websocket:
                        payload = json.loads(message)
                        if on_message is not None:
                            await on_message(payload)
            except asyncio.CancelledError:
                logger.info("Binance WebSocket task cancelled.", extra={"event": "binance_ws_cancelled"})
                raise
            except Exception:
                logger.exception("Binance WebSocket disconnected; reconnecting.", extra={"event": "binance_ws_retry"})
                await asyncio.sleep(5)

    async def _request(self, endpoint: str, params: Dict[str, Any]) -> Any:
        for attempt in range(3):
            try:
                response = await self._client.get(endpoint, params=params)
                if response.status_code == 429:
                    raise RateLimitExceededError("Binance rate limit reached.")
                if response.status_code == 400 and "Invalid symbol" in response.text:
                    raise InvalidSymbolError("Invalid Binance symbol.")
                response.raise_for_status()
                return response.json()
            except (RateLimitExceededError, InvalidSymbolError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (418, 429):
                    raise RateLimitExceededError("Binance API temporarily blocked requests.") from exc
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Binance request failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Binance request failed due to network error.") from exc

        raise ExternalAPIError("Binance request failed after retries.")
