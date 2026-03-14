from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import get_settings
from services.cache import SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, RateLimitExceededError
from services.rate_limit import DailyBudgetLimiter, SlidingWindowRateLimiter

logger = logging.getLogger("market_intelligence.services.perplexity")


class PerplexityService:
    """Client for Perplexity Sonar market summaries."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        settings = get_settings()
        self._api_key = settings.perplexity_api_key
        self._model = "sonar"
        self._request_cost_usd = settings.perplexity_request_cost_usd
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(base_url="https://api.perplexity.ai", timeout=httpx.Timeout(30.0))
        self._budget_limiter = DailyBudgetLimiter(max_usd_per_day=settings.perplexity_daily_budget_usd)
        self._rate_limiter = SlidingWindowRateLimiter(limit=30, window_seconds=60, wait_for_slot=True)

    async def close(self) -> None:
        """Close HTTP client resources."""
        await self._client.aclose()

    def has_api_key(self) -> bool:
        """Return True if Perplexity API key is configured."""
        return bool(self._api_key)

    async def get_market_summary(self, asset_symbol: str, asset_name: str) -> str:
        """Generate compact market summary for one asset."""
        key = "perplexity:summary:{0}".format(asset_symbol.upper())
        return await self._cache.get_or_set(key, 4 * 3600, lambda: self._summary_uncached(asset_symbol, asset_name))

    async def get_trending_topics(self) -> Dict[str, List[str]]:
        """Return top trending stock and crypto symbols."""
        key = "perplexity:trending_topics"
        return await self._cache.get_or_set(key, 4 * 3600, self._trending_uncached)

    async def _summary_uncached(self, asset_symbol: str, asset_name: str) -> str:
        prompt = (
            "Provide a concise market sentiment summary for {0} ({1}). "
            "Limit to max 3 short bullet points, include risks and momentum."
        ).format(asset_name, asset_symbol.upper())
        return await self._chat_completion(prompt, max_tokens=220)

    async def _trending_uncached(self) -> Dict[str, List[str]]:
        prompt = (
            "Return JSON only with this schema: "
            '{"stocks":["SYM1","SYM2","SYM3","SYM4","SYM5"],'
            '"crypto":["SYM1","SYM2","SYM3","SYM4","SYM5"]}. '
            "Focus on globally trending liquid assets today."
        )
        content = await self._chat_completion(prompt, max_tokens=220)
        return self._parse_trending_json(content)

    async def _chat_completion(self, prompt: str, max_tokens: int) -> str:
        if not self._api_key:
            raise ExternalAPIError("PERPLEXITY_API_KEY missing.")
        await self._budget_limiter.reserve(self._request_cost_usd)
        try:
            return await self._request_completion(prompt, max_tokens)
        except Exception:
            await self._budget_limiter.refund(self._request_cost_usd)
            raise

    async def _request_completion(self, prompt: str, max_tokens: int) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "You are a financial market analyst."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": "Bearer {0}".format(self._api_key), "Content-Type": "application/json"}
        for attempt in range(3):
            try:
                await self._rate_limiter.acquire()
                response = await self._client.post("/chat/completions", json=payload, headers=headers)
                if response.status_code == 429:
                    raise RateLimitExceededError("Perplexity rate limit reached.")
                response.raise_for_status()
                data = response.json()
                return self._extract_content(data)
            except RateLimitExceededError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Perplexity request failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Perplexity request failed due to network error.") from exc
        raise ExternalAPIError("Perplexity request failed after retries.")

    def _extract_content(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise ExternalAPIError("Perplexity response missing choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ExternalAPIError("Perplexity response missing content.")
        return content.strip()

    def _parse_trending_json(self, content: str) -> Dict[str, List[str]]:
        try:
            data = json.loads(content)
            stocks = self._normalize_topic_list(data.get("stocks"))
            crypto = self._normalize_topic_list(data.get("crypto"))
            return {"stocks": stocks[:5], "crypto": crypto[:5]}
        except json.JSONDecodeError:
            logger.warning("Perplexity trending response was not valid JSON.", extra={"event": "perplexity_json_parse_failed"})
            return {"stocks": [], "crypto": []}

    def _normalize_topic_list(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        normalized = []
        for item in value:
            text = str(item).upper().strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized
