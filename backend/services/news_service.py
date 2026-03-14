from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import get_settings
from services.cache import NEWS_TTL_SECONDS, SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, RateLimitExceededError
from services.rate_limit import DailyUsageLimiter, SlidingWindowRateLimiter

logger = logging.getLogger("market_intelligence.services.news")


class NewsService:
    """Collects market news from Alpha Vantage with Finnhub fallback."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        settings = get_settings()
        self._alpha_key = settings.alpha_vantage_api_key
        self._finnhub_key = settings.finnhub_api_key
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        self._alpha_daily_quota = DailyUsageLimiter(max_units_per_day=25)
        self._finnhub_rate_limiter = SlidingWindowRateLimiter(limit=55, window_seconds=60, wait_for_slot=True)

    async def close(self) -> None:
        """Close HTTP client resources."""
        await self._client.aclose()

    def has_available_provider(self) -> bool:
        """Return True when at least one news provider can be used."""
        return bool(self._alpha_key or self._finnhub_key)

    async def collect_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Collect symbol-specific news from primary and fallback sources."""
        normalized = symbol.upper().strip()
        cache_key = "news:collect:{0}".format(normalized)
        return await self._cache.get_or_set(cache_key, NEWS_TTL_SECONDS, lambda: self._collect_news_uncached(normalized))

    async def _collect_news_uncached(self, symbol: str) -> List[Dict[str, Any]]:
        alpha_items = await self._collect_alpha_news(symbol)
        if alpha_items:
            return alpha_items
        return await self._collect_finnhub_news(symbol)

    async def _collect_alpha_news(self, symbol: str) -> List[Dict[str, Any]]:
        if not self._alpha_key:
            return []
        try:
            await self._alpha_daily_quota.consume(1)
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "sort": "LATEST",
                "limit": 20,
                "apikey": self._alpha_key,
            }
            payload = await self._request("https://www.alphavantage.co/query", params)
            return self._normalize_alpha_items(payload.get("feed", []))
        except RateLimitExceededError:
            logger.warning("Alpha Vantage daily quota exceeded.", extra={"event": "alpha_quota_exceeded"})
            return []
        except ExternalAPIError:
            logger.exception("Alpha Vantage request failed; fallback to Finnhub.", extra={"event": "alpha_request_failed"})
            return []

    async def _collect_finnhub_news(self, symbol: str) -> List[Dict[str, Any]]:
        if not self._finnhub_key:
            logger.warning("Finnhub fallback skipped: missing API key.", extra={"event": "finnhub_news_skipped"})
            return []
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=7)
        params = {"symbol": symbol, "from": start_date.isoformat(), "to": end_date.isoformat(), "token": self._finnhub_key}
        await self._finnhub_rate_limiter.acquire()
        payload = await self._request("https://finnhub.io/api/v1/company-news", params)
        if not isinstance(payload, list):
            return []
        return self._normalize_finnhub_items(payload)

    async def _request(self, url: str, params: Dict[str, Any]) -> Any:
        for attempt in range(3):
            try:
                response = await self._client.get(url, params=params)
                if response.status_code == 429:
                    raise RateLimitExceededError("News provider rate limit reached.")
                response.raise_for_status()
                return response.json()
            except RateLimitExceededError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("News request failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("News request failed due to network error.") from exc
        raise ExternalAPIError("News request failed after retries.")

    def _normalize_alpha_items(self, items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            summary = item.get("summary") or ""
            title = item.get("title") or ""
            text = "{0} {1}".format(title, summary).strip()
            normalized.append(
                {
                    "text": text[:500],
                    "title": title[:250],
                    "url": item.get("url"),
                    "author": self._normalize_alpha_authors(item.get("authors")),
                    "created_at": self._parse_alpha_time(item.get("time_published")),
                    "provider": "alpha_vantage",
                }
            )
        return normalized

    def _normalize_finnhub_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in items:
            summary = item.get("summary") or ""
            headline = item.get("headline") or ""
            text = "{0} {1}".format(headline, summary).strip()
            normalized.append(
                {
                    "text": text[:500],
                    "title": headline[:250],
                    "url": item.get("url"),
                    "author": item.get("source"),
                    "created_at": self._parse_unix(item.get("datetime")),
                    "provider": "finnhub",
                }
            )
        return normalized

    def _normalize_alpha_authors(self, authors: Any) -> Optional[str]:
        if isinstance(authors, list):
            parts = [str(item).strip() for item in authors if str(item).strip()]
            return ", ".join(parts) if parts else None
        if isinstance(authors, str):
            return authors.strip() or None
        return None

    def _parse_alpha_time(self, value: Any) -> datetime:
        if not isinstance(value, str) or len(value) < 15:
            return datetime.now(timezone.utc)
        parsed = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        return parsed.replace(tzinfo=timezone.utc)

    def _parse_unix(self, value: Any) -> datetime:
        if value in (None, 0, "0"):
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
