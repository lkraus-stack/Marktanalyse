from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import time
from typing import Optional

from services.exceptions import RateLimitExceededError


class SlidingWindowRateLimiter:
    """Async sliding-window limiter with optional waiting."""

    def __init__(self, limit: int, window_seconds: int, wait_for_slot: bool = True) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._wait_for_slot = wait_for_slot
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Consume one request slot or wait until available."""
        while True:
            delay = await self._reserve_or_delay()
            if delay is None:
                return
            if not self._wait_for_slot:
                raise RateLimitExceededError("Rate limit reached.")
            await asyncio.sleep(delay)

    async def _reserve_or_delay(self) -> Optional[float]:
        async with self._lock:
            now = time.monotonic()
            while self._events and now - self._events[0] >= self._window_seconds:
                self._events.popleft()
            if len(self._events) < self._limit:
                self._events.append(now)
                return None
            head_age = now - self._events[0]
            wait_seconds = max(0.05, self._window_seconds - head_age + 0.01)
            return wait_seconds


class DailyUsageLimiter:
    """Thread-safe daily request counter."""

    def __init__(self, max_units_per_day: int) -> None:
        self._max_units = max_units_per_day
        self._used_units = 0
        self._day_key = self._today_key()
        self._lock = asyncio.Lock()

    async def consume(self, units: int = 1) -> None:
        """Consume daily quota units or raise when exhausted."""
        async with self._lock:
            self._reset_if_day_changed()
            if self._used_units + units > self._max_units:
                raise RateLimitExceededError("Daily quota exceeded.")
            self._used_units += units

    def _reset_if_day_changed(self) -> None:
        key = self._today_key()
        if key != self._day_key:
            self._day_key = key
            self._used_units = 0

    def _today_key(self) -> str:
        now = datetime.now(timezone.utc)
        return "{0:04d}-{1:02d}-{2:02d}".format(now.year, now.month, now.day)


class DailyBudgetLimiter:
    """Thread-safe daily budget tracker in USD."""

    def __init__(self, max_usd_per_day: float) -> None:
        self._max_usd = max_usd_per_day
        self._spent_usd = 0.0
        self._day_key = self._today_key()
        self._lock = asyncio.Lock()

    async def reserve(self, amount_usd: float) -> None:
        """Reserve budget amount atomically."""
        async with self._lock:
            self._reset_if_day_changed()
            if self._spent_usd + amount_usd > self._max_usd:
                raise RateLimitExceededError("Daily budget exceeded.")
            self._spent_usd += amount_usd

    async def refund(self, amount_usd: float) -> None:
        """Refund reserved budget when request failed before completion."""
        async with self._lock:
            self._reset_if_day_changed()
            self._spent_usd = max(0.0, self._spent_usd - amount_usd)

    async def spent_today(self) -> float:
        """Return currently tracked spend for today."""
        async with self._lock:
            self._reset_if_day_changed()
            return self._spent_usd

    def _reset_if_day_changed(self) -> None:
        key = self._today_key()
        if key != self._day_key:
            self._day_key = key
            self._spent_usd = 0.0

    def _today_key(self) -> str:
        now = datetime.now(timezone.utc)
        return "{0:04d}-{1:02d}-{2:02d}".format(now.year, now.month, now.day)
