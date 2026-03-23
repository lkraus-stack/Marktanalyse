from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import get_settings
from services.cache import SimpleCache, shared_cache
from services.exceptions import ExternalAPIError
from services.rate_limit import DailyBudgetLimiter, SlidingWindowRateLimiter

logger = logging.getLogger("market_intelligence.services.perplexity")


@dataclass
class AIRequestAttempt:
    """One provider/model attempt for a chat completion."""

    model: str
    status: str
    status_code: Optional[int] = None
    error: Optional[str] = None
    response_excerpt: Optional[str] = None
    provider: Optional[str] = None
    endpoint: Optional[str] = None


@dataclass
class AITextResult:
    """Resolved text payload plus model diagnostics."""

    content: str
    model: str
    attempts: List[AIRequestAttempt] = field(default_factory=list)
    cached: bool = False


@dataclass
class AITrendingTopicsResult:
    """Trending topics response plus model diagnostics."""

    topics: Dict[str, List[str]]
    raw_content: str
    model: str
    attempts: List[AIRequestAttempt] = field(default_factory=list)
    cached: bool = False


class PerplexityService:
    """Client for Sonar-compatible market summaries via configurable AI providers."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        settings = get_settings()
        self._api_key = settings.summary_ai_api_key
        self._model = settings.summary_ai_model
        self._validation_model = settings.summary_ai_validation_model
        self._provider = settings.ai_provider
        self._chat_completions_path = settings.summary_ai_chat_completions_path
        self._base_url = settings.summary_ai_base_url
        self._request_cost_usd = settings.perplexity_request_cost_usd
        self._cache = cache or shared_cache
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=httpx.Timeout(30.0))
        self._budget_limiter = DailyBudgetLimiter(max_usd_per_day=settings.perplexity_daily_budget_usd)
        self._rate_limiter = SlidingWindowRateLimiter(limit=30, window_seconds=60, wait_for_slot=True)

    async def close(self) -> None:
        """Close HTTP client resources."""
        await self._client.aclose()

    def has_api_key(self) -> bool:
        """Return True if an AI provider API key is configured."""
        return bool(self._api_key)

    @property
    def provider(self) -> str:
        """Expose provider name for diagnostics."""
        return self._provider

    @property
    def base_url(self) -> str:
        """Expose base URL for diagnostics."""
        return self._base_url

    @property
    def chat_completions_path(self) -> str:
        """Expose request path for diagnostics."""
        return self._chat_completions_path

    @property
    def primary_model(self) -> str:
        """Expose configured primary model."""
        return self._model

    @property
    def validation_model(self) -> Optional[str]:
        """Expose optional validation/fallback model."""
        return self._validation_model

    async def get_market_summary(self, asset_symbol: str, asset_name: str) -> str:
        """Generate compact market summary for one asset."""
        key = "perplexity:summary:{0}".format(asset_symbol.upper())
        return await self._cache.get_or_set(key, 4 * 3600, lambda: self._summary_uncached(asset_symbol, asset_name))

    async def get_market_summary_result(
        self,
        asset_symbol: str,
        asset_name: str,
        *,
        use_cache: bool = False,
    ) -> AITextResult:
        """Return a market summary with per-model diagnostics."""
        if use_cache:
            content = await self.get_market_summary(asset_symbol, asset_name)
            return AITextResult(content=content, model=self._model, cached=True)
        prompt = (
            "Provide a concise market sentiment summary for {0} ({1}). "
            "Limit to max 3 short bullet points, include risks and momentum."
        ).format(asset_name, asset_symbol.upper())
        return await self._chat_completion_result(prompt, max_tokens=220)

    async def get_trending_topics(self) -> Dict[str, List[str]]:
        """Return top trending stock and crypto symbols."""
        key = "perplexity:trending_topics"
        return await self._cache.get_or_set(key, 4 * 3600, self._trending_uncached)

    async def get_trending_topics_result(self, *, use_cache: bool = False) -> AITrendingTopicsResult:
        """Return trending topics with per-model diagnostics."""
        if use_cache:
            topics = await self.get_trending_topics()
            return AITrendingTopicsResult(topics=topics, raw_content=json.dumps(topics), model=self._model, cached=True)
        prompt = (
            "Return JSON only with this schema: "
            '{"stocks":["SYM1","SYM2","SYM3","SYM4","SYM5"],'
            '"crypto":["SYM1","SYM2","SYM3","SYM4","SYM5"]}. '
            "Focus on globally trending liquid assets today."
        )
        result = await self._chat_completion_result(prompt, max_tokens=220)
        return AITrendingTopicsResult(
            topics=self._parse_trending_json(result.content),
            raw_content=result.content,
            model=result.model,
            attempts=result.attempts,
            cached=result.cached,
        )

    async def _summary_uncached(self, asset_symbol: str, asset_name: str) -> str:
        result = await self.get_market_summary_result(asset_symbol, asset_name, use_cache=False)
        return result.content

    async def _trending_uncached(self) -> Dict[str, List[str]]:
        result = await self.get_trending_topics_result(use_cache=False)
        return result.topics

    async def _chat_completion(self, prompt: str, max_tokens: int) -> str:
        """Backward-compatible text-only completion helper."""
        result = await self._chat_completion_result(prompt, max_tokens=max_tokens)
        return result.content

    async def _chat_completion_result(self, prompt: str, max_tokens: int) -> AITextResult:
        """Run one AI completion with optional fallback models and diagnostics."""
        if not self._api_key:
            raise ExternalAPIError("AI_API_KEY/PERPLEXITY_API_KEY missing.")

        attempts: List[AIRequestAttempt] = []
        await self._budget_limiter.reserve(self._request_cost_usd)
        try:
            last_error: Optional[ExternalAPIError] = None
            models = self._candidate_models()
            for model in models:
                try:
                    content, attempt = await self._request_completion(prompt, max_tokens, model)
                    attempts.append(attempt)
                    return AITextResult(content=content, model=model, attempts=attempts)
                except ExternalAPIError as exc:
                    attempts.extend(self._attempts_from_error(exc, fallback_model=model))
                    last_error = exc
            raise ExternalAPIError(
                "All configured AI models failed.",
                provider=self._provider,
                endpoint=self._request_endpoint(),
                attempts=attempts,
                model=models[-1],
            ) from last_error
        except Exception:
            await self._budget_limiter.refund(self._request_cost_usd)
            raise

    async def _request_completion(self, prompt: str, max_tokens: int, model: str) -> tuple[str, AIRequestAttempt]:
        payload = {
            "model": model,
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
                response = await self._client.post(self._chat_completions_path, json=payload, headers=headers)
                if response.status_code == 429:
                    raise ExternalAPIError(
                        "{0} rate limit reached.".format(self._provider),
                        status_code=429,
                        response_body=self._trim_text(response.text),
                        provider=self._provider,
                        endpoint=self._request_endpoint(),
                        model=model,
                    )
                response.raise_for_status()
                data = response.json()
                content = self._extract_content(data)
                return content, AIRequestAttempt(
                    model=model,
                    status="success",
                    status_code=response.status_code,
                    provider=self._provider,
                    endpoint=self._request_endpoint(),
                )
            except ExternalAPIError:
                raise
            except httpx.HTTPStatusError as exc:
                response_excerpt = self._trim_text(exc.response.text)
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError(
                    "{0} request failed with HTTP {1}.".format(self._provider, exc.response.status_code),
                    status_code=exc.response.status_code,
                    response_body=response_excerpt,
                    provider=self._provider,
                    endpoint=self._request_endpoint(),
                    model=model,
                ) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError(
                    "{0} request failed due to network error.".format(self._provider),
                    response_body=self._trim_text(str(exc)),
                    provider=self._provider,
                    endpoint=self._request_endpoint(),
                    model=model,
                ) from exc
        raise ExternalAPIError(
            "{0} request failed after retries.".format(self._provider),
            provider=self._provider,
            endpoint=self._request_endpoint(),
            model=model,
        )

    def _extract_content(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise ExternalAPIError("AI response missing choices.", provider=self._provider, endpoint=self._request_endpoint())
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text_parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    text_parts.append(item.strip())
            if text_parts:
                return "\n".join(text_parts)
        if not isinstance(content, str) or not content.strip():
            raise ExternalAPIError("AI response missing content.", provider=self._provider, endpoint=self._request_endpoint())
        return content.strip()

    def _parse_trending_json(self, content: str) -> Dict[str, List[str]]:
        try:
            data = json.loads(content)
            stocks = self._normalize_topic_list(data.get("stocks"))
            crypto = self._normalize_topic_list(data.get("crypto"))
            return {"stocks": stocks[:5], "crypto": crypto[:5]}
        except json.JSONDecodeError:
            extracted = self._extract_json_object(content)
            if extracted is not None:
                try:
                    data = json.loads(extracted)
                    stocks = self._normalize_topic_list(data.get("stocks"))
                    crypto = self._normalize_topic_list(data.get("crypto"))
                    return {"stocks": stocks[:5], "crypto": crypto[:5]}
                except json.JSONDecodeError:
                    pass
            logger.warning(
                "AI trending response was not valid JSON.",
                extra={"event": "perplexity_json_parse_failed", "provider": self._provider},
            )
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

    def format_author(self, model: str) -> str:
        """Create a compact author string including provider and model."""
        return self._trim_text("{0}:{1}".format(self._provider, model), limit=120)

    def _candidate_models(self) -> List[str]:
        models = [self._model]
        if self._validation_model and self._validation_model not in models:
            models.append(self._validation_model)
        return models

    def _request_endpoint(self) -> str:
        if self._chat_completions_path.startswith("http://") or self._chat_completions_path.startswith("https://"):
            return self._chat_completions_path
        return "{0}{1}".format(self._base_url, self._chat_completions_path)

    def _attempts_from_error(self, error: ExternalAPIError, fallback_model: str) -> List[AIRequestAttempt]:
        if error.attempts:
            return [item for item in error.attempts if isinstance(item, AIRequestAttempt)]
        return [
            AIRequestAttempt(
                model=error.model or fallback_model,
                status="error",
                status_code=error.status_code,
                error=str(error),
                response_excerpt=error.response_body,
                provider=error.provider or self._provider,
                endpoint=error.endpoint or self._request_endpoint(),
            )
        ]

    def _extract_json_object(self, content: str) -> Optional[str]:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return content[start : end + 1]

    def _trim_text(self, value: str, limit: int = 300) -> str:
        normalized = value.strip()
        if len(normalized) <= limit:
            return normalized
        return "{0}...".format(normalized[:limit])
