from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import httpx

from config import get_settings
from services.cache import QUOTE_TTL_SECONDS, SimpleCache, shared_cache
from services.exceptions import ExternalAPIError, InvalidSymbolError, RateLimitExceededError
from services.rate_limit import SlidingWindowRateLimiter

logger = logging.getLogger("market_intelligence.services.reddit")

TARGET_SUBREDDITS = ["wallstreetbets", "stocks", "investing", "cryptocurrency", "CryptoMarkets"]
TICKER_PATTERN = re.compile(r"(?<![A-Z0-9_])\$([A-Z]{1,10})(?![A-Z0-9_])")


class RedditService:
    """Reddit OAuth2 client for subreddit posts and comments."""

    def __init__(self, cache: Optional[SimpleCache] = None) -> None:
        settings = get_settings()
        self._client_id = settings.reddit_client_id
        self._client_secret = settings.reddit_client_secret
        self._user_agent = settings.reddit_user_agent
        self._cache = cache or shared_cache
        self._oauth_client = httpx.AsyncClient(base_url="https://www.reddit.com", timeout=httpx.Timeout(20.0))
        self._api_client = httpx.AsyncClient(base_url="https://oauth.reddit.com", timeout=httpx.Timeout(20.0))
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._token_lock = asyncio.Lock()
        self._rate_limiter = SlidingWindowRateLimiter(limit=95, window_seconds=60, wait_for_slot=True)

    async def close(self) -> None:
        """Close managed HTTP clients."""
        await asyncio.gather(self._oauth_client.aclose(), self._api_client.aclose())

    def has_credentials(self) -> bool:
        """Return True when Reddit OAuth credentials are configured."""
        return bool(self._client_id and self._client_secret)

    async def get_subreddit_posts(self, subreddit: str, sort: str = "new", limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch subreddit posts list."""
        bounded_limit = max(1, min(limit, 100))
        cache_key = "reddit:posts:{0}:{1}:{2}".format(subreddit.lower(), sort, bounded_limit)
        return await self._cache.get_or_set(cache_key, QUOTE_TTL_SECONDS, lambda: self._fetch_posts(subreddit, sort, bounded_limit))

    async def get_post_comments(self, post_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch top-level comments for one post id."""
        bounded_limit = max(1, min(limit, 100))
        cache_key = "reddit:comments:{0}:{1}".format(post_id, bounded_limit)
        return await self._cache.get_or_set(cache_key, QUOTE_TTL_SECONDS, lambda: self._fetch_comments(post_id, bounded_limit))

    async def search_subreddit(self, subreddit: str, query: str, sort: str = "relevance", limit: int = 25) -> List[Dict[str, Any]]:
        """Search subreddit posts by free-text query."""
        bounded_limit = max(1, min(limit, 100))
        cache_key = "reddit:search:{0}:{1}:{2}:{3}".format(subreddit.lower(), query.lower(), sort, bounded_limit)
        return await self._cache.get_or_set(
            cache_key,
            QUOTE_TTL_SECONDS,
            lambda: self._search_posts(subreddit, query, sort, bounded_limit),
        )

    def extract_ticker_mentions(self, text: str, tracked_symbols: Sequence[str]) -> List[str]:
        """Extract tracked $TICKER mentions while avoiding 1-char false positives."""
        symbols = {item.upper() for item in tracked_symbols}
        mentions: set[str] = set()
        for match in TICKER_PATTERN.finditer(text.upper()):
            ticker = match.group(1)
            if len(ticker) < 2:
                continue
            if ticker in symbols:
                mentions.add(ticker)
        return sorted(mentions)

    async def _fetch_posts(self, subreddit: str, sort: str, limit: int) -> List[Dict[str, Any]]:
        path = "/r/{0}/{1}.json".format(subreddit, sort)
        payload = await self._authorized_get(path, {"limit": limit})
        return self._extract_listing(payload)

    async def _fetch_comments(self, post_id: str, limit: int) -> List[Dict[str, Any]]:
        path = "/comments/{0}.json".format(post_id)
        payload = await self._authorized_get(path, {"limit": limit, "depth": 1})
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        return self._extract_listing(payload[1])

    async def _search_posts(self, subreddit: str, query: str, sort: str, limit: int) -> List[Dict[str, Any]]:
        path = "/r/{0}/search.json".format(subreddit)
        params = {"q": query, "sort": sort, "limit": limit, "restrict_sr": 1}
        payload = await self._authorized_get(path, params)
        return self._extract_listing(payload)

    async def _authorized_get(self, path: str, params: Dict[str, Any]) -> Any:
        token = await self._get_access_token()
        headers = {"Authorization": "Bearer {0}".format(token), "User-Agent": self._user_agent}
        return await self._request_with_reauth(path, params, headers)

    async def _request_with_reauth(self, path: str, params: Dict[str, Any], headers: Dict[str, str]) -> Any:
        for attempt in range(3):
            try:
                await self._rate_limiter.acquire()
                response = await self._api_client.get(path, params=params, headers=headers)
                if response.status_code == 401:
                    await self._refresh_token(force=True)
                    headers["Authorization"] = "Bearer {0}".format(await self._get_access_token())
                    continue
                if response.status_code == 429:
                    raise RateLimitExceededError("Reddit rate limit reached.")
                response.raise_for_status()
                return response.json()
            except RateLimitExceededError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Reddit API failed with HTTP {0}.".format(exc.response.status_code)) from exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ExternalAPIError("Reddit request failed due to network error.") from exc
        raise ExternalAPIError("Reddit request failed after retries.")

    async def _get_access_token(self) -> str:
        if self._token and self._token_expiry and self._token_expiry > datetime.now(timezone.utc):
            return self._token
        await self._refresh_token(force=False)
        if not self._token:
            raise ExternalAPIError("Failed to obtain Reddit access token.")
        return self._token

    async def _refresh_token(self, force: bool) -> None:
        async with self._token_lock:
            if not force and self._token and self._token_expiry and self._token_expiry > datetime.now(timezone.utc):
                return
            if not self._client_id or not self._client_secret:
                raise ExternalAPIError("REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET missing.")
            data = {"grant_type": "client_credentials"}
            headers = {"User-Agent": self._user_agent}
            response = await self._oauth_client.post(
                "/api/v1/access_token",
                data=data,
                auth=(self._client_id, self._client_secret),
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 3600))
            if not token:
                raise ExternalAPIError("Reddit token response missing access_token.")
            self._token = token
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 30))

    def _extract_listing(self, payload: Any) -> List[Dict[str, Any]]:
        try:
            children = payload["data"]["children"]
        except (TypeError, KeyError):
            raise InvalidSymbolError("Unexpected Reddit listing format.")
        entries: List[Dict[str, Any]] = []
        for child in children:
            data = child.get("data", {})
            entries.append(
                {
                    "id": data.get("id"),
                    "title": data.get("title") or "",
                    "selftext": data.get("selftext") or data.get("body") or "",
                    "url": data.get("url"),
                    "permalink": data.get("permalink"),
                    "author": data.get("author"),
                    "subreddit": data.get("subreddit"),
                    "created_utc": data.get("created_utc"),
                }
            )
        return entries
