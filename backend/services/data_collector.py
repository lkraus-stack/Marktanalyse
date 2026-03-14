from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database import AsyncSessionLocal
from models import (
    Asset,
    AssetType,
    PriceData,
    PriceTimeframe,
    SentimentLabel,
    SentimentModel,
    SentimentRecord,
    SentimentSource,
)
from services.binance_service import BinanceService
from services.coingecko_service import CoinGeckoService
from services.exceptions import ExternalAPIError, InvalidSymbolError, RateLimitExceededError
from services.finnhub_service import FinnhubService
from services.news_service import NewsService
from services.perplexity_service import PerplexityService
from services.price_stream import price_pubsub
from services.reddit_service import RedditService, TARGET_SUBREDDITS
from services.stocktwits_service import StockTwitsService

logger = logging.getLogger("market_intelligence.services.data_collector")

M1_BACKFILL_MAX_DAYS = 7
M1_BACKFILL_CHUNK_LIMIT = 1000
M1_STEP_MS = 60_000
DB_IN_CLAUSE_CHUNK = 400


class DataCollector:
    """Coordinates market data retrieval and persistence."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        finnhub_service: Optional[FinnhubService] = None,
        binance_service: Optional[BinanceService] = None,
        coingecko_service: Optional[CoinGeckoService] = None,
        reddit_service: Optional[RedditService] = None,
        stocktwits_service: Optional[StockTwitsService] = None,
        news_service: Optional[NewsService] = None,
        perplexity_service: Optional[PerplexityService] = None,
    ) -> None:
        self._session_factory = session_factory
        self._finnhub = finnhub_service or FinnhubService()
        self._binance = binance_service or BinanceService()
        self._coingecko = coingecko_service or CoinGeckoService()
        self._reddit = reddit_service or RedditService()
        self._stocktwits = stocktwits_service or StockTwitsService()
        self._news = news_service or NewsService()
        self._perplexity = perplexity_service or PerplexityService()
        self._ws_tasks: List[asyncio.Task[None]] = []

    async def collect_stock_prices(self) -> int:
        """Collect stock quotes from Finnhub and store them as 1m snapshots."""
        if not self._finnhub.has_api_key():
            logger.warning("Skipping stock collection: FINNHUB_API_KEY missing.", extra={"event": "collect_stock_skipped"})
            return 0
        assets = await self._get_active_assets(AssetType.STOCK)
        success_count = 0
        for asset in assets:
            try:
                quote = await self._finnhub.get_quote(asset.symbol)
                timestamp = self._timestamp_from_unix(quote.get("t"))
                await self._save_price_data(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    timestamp=timestamp,
                    source="finnhub",
                    open_price=self._to_decimal(quote.get("o", quote.get("c", 0.0))),
                    high_price=self._to_decimal(quote.get("h", quote.get("c", 0.0))),
                    low_price=self._to_decimal(quote.get("l", quote.get("c", 0.0))),
                    close_price=self._to_decimal(quote.get("c", 0.0)),
                    volume=float(quote.get("v", 0.0)),
                )
                success_count += 1
            except Exception:
                logger.exception("Stock collection failed.", extra={"event": "collect_stock_error", "symbol": asset.symbol})
        return success_count

    async def collect_crypto_prices(self) -> int:
        """Collect crypto quotes from Binance with CoinGecko fallback."""
        assets = await self._get_active_assets(AssetType.CRYPTO)
        success_count = 0
        for asset in assets:
            try:
                snapshot = await self._fetch_crypto_snapshot(asset.symbol)
                await self._save_price_data(asset_id=asset.id, symbol=asset.symbol, **snapshot)
                success_count += 1
            except Exception:
                logger.exception("Crypto collection failed.", extra={"event": "collect_crypto_error", "symbol": asset.symbol})
        return success_count

    async def collect_all(self) -> Dict[str, int]:
        """Collect stock and crypto snapshots in one cycle."""
        stock_count, crypto_count = await asyncio.gather(self.collect_stock_prices(), self.collect_crypto_prices())
        return {"stocks": stock_count, "crypto": crypto_count}

    async def backfill_analysis_candles(self, h1_limit: int = 120) -> Dict[str, int]:
        """Backfill H1 candles to make technical signals available quickly."""
        safe_limit = max(50, min(h1_limit, 500))
        assets = await self._get_all_active_assets()
        inserted = {"stocks": 0, "crypto": 0}
        coverage_window_start = datetime.now(timezone.utc) - timedelta(days=30)
        for asset in assets:
            try:
                existing_count = await self._count_recent_price_points(
                    asset_id=asset.id,
                    timeframe=PriceTimeframe.H1,
                    since=coverage_window_start,
                )
                if existing_count >= safe_limit:
                    continue
                candles, source = await self._fetch_h1_candles(asset, safe_limit)
                if not candles:
                    continue
                saved = await self._save_price_batch(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    timeframe=PriceTimeframe.H1,
                    source=source,
                    points=candles,
                    publish=False,
                )
                key = "stocks" if asset.asset_type == AssetType.STOCK else "crypto"
                inserted[key] += int(saved)
            except Exception:
                logger.exception(
                    "H1 backfill failed.",
                    extra={"event": "backfill_h1_failed", "symbol": asset.symbol},
                )
        return inserted

    async def backfill_m1_history(self, days: int = M1_BACKFILL_MAX_DAYS) -> Dict[str, int]:
        """Backfill minute candles to improve momentum/volume components."""
        safe_days = max(1, min(days, M1_BACKFILL_MAX_DAYS))
        assets = await self._get_all_active_assets()
        inserted = {"stocks": 0, "crypto": 0}
        since = datetime.now(timezone.utc) - timedelta(days=safe_days)
        for asset in assets:
            try:
                existing_count = await self._count_recent_price_points(
                    asset_id=asset.id,
                    timeframe=PriceTimeframe.M1,
                    since=since,
                )
                min_required = self._target_m1_points(asset.asset_type, safe_days)
                if existing_count >= min_required:
                    continue
                count = await self._backfill_asset_m1(asset, safe_days)
                key = "stocks" if asset.asset_type == AssetType.STOCK else "crypto"
                inserted[key] += int(count)
            except Exception:
                logger.exception(
                    "M1 backfill failed.",
                    extra={"event": "backfill_m1_failed", "symbol": asset.symbol},
                )
        return inserted

    async def collect_social_data(self) -> Dict[str, int]:
        """Collect Reddit, StockTwits and news text records."""
        assets = await self._get_all_active_assets()
        tracked_symbols = [asset.symbol for asset in assets]
        assets_by_symbol = {asset.symbol: asset for asset in assets}
        reddit_count = await self._collect_reddit_records(assets_by_symbol, tracked_symbols)
        stocktwits_count = await self._collect_stocktwits_records(assets)
        news_count = await self._collect_news_records(assets)
        return {"reddit": reddit_count, "stocktwits": stocktwits_count, "news": news_count}

    async def collect_perplexity_summaries(self) -> int:
        """Collect Perplexity summaries for top assets and overall market topics."""
        if not self._perplexity.has_api_key():
            logger.warning("Skipping Perplexity collection: API key missing.", extra={"event": "collect_perplexity_skipped"})
            return 0
        total_saved = 0
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        try:
            trending = await self._perplexity.get_trending_topics()
            text = self._format_trending_topics(trending)
            record = self._build_sentiment_record(
                asset_id=None,
                source=SentimentSource.PERPLEXITY,
                text=text,
                source_url="perplexity://trending/{0}".format(now.isoformat()),
                author="perplexity-sonar",
                created_at=now,
            )
            total_saved += await self._insert_sentiment_records([record])
        except Exception:
            logger.exception("Perplexity trending topics collection failed.", extra={"event": "collect_perplexity_trending_error"})
        top_assets = await self._get_top_assets_by_volume(limit=10)
        for asset in top_assets:
            try:
                summary = await self._perplexity.get_market_summary(asset.symbol, asset.name)
                record = self._build_sentiment_record(
                    asset_id=asset.id,
                    source=SentimentSource.PERPLEXITY,
                    text=summary,
                    source_url="perplexity://summary/{0}/{1}".format(asset.symbol, now.isoformat()),
                    author="perplexity-sonar",
                    created_at=now,
                )
                total_saved += await self._insert_sentiment_records([record])
            except Exception:
                logger.exception("Perplexity summary failed.", extra={"event": "collect_perplexity_asset_error", "symbol": asset.symbol})
        return total_saved

    async def start_websockets(self, stock_symbols: Sequence[str], crypto_symbols: Sequence[str]) -> None:
        """Start background WebSocket consumers with auto-reconnect."""
        await self.stop_websockets()
        if stock_symbols and self._finnhub.has_api_key():
            stock_task = asyncio.create_task(
                self._finnhub.connect_finnhub_ws(list(stock_symbols), on_message=self._handle_finnhub_ws_message)
            )
            self._ws_tasks.append(stock_task)
        elif stock_symbols:
            logger.warning("Finnhub WebSocket skipped: API key missing.", extra={"event": "finnhub_ws_skipped"})
        if crypto_symbols:
            crypto_task = asyncio.create_task(
                self._binance.connect_binance_ws(list(crypto_symbols), on_message=self._handle_binance_ws_message)
            )
            self._ws_tasks.append(crypto_task)

    async def stop_websockets(self) -> None:
        """Cancel all running WebSocket tasks."""
        if not self._ws_tasks:
            return
        for task in self._ws_tasks:
            task.cancel()
        await asyncio.gather(*self._ws_tasks, return_exceptions=True)
        self._ws_tasks.clear()

    async def shutdown(self) -> None:
        """Close all managed resources."""
        await self.stop_websockets()
        await asyncio.gather(
            self._finnhub.close(),
            self._binance.close(),
            self._coingecko.close(),
            self._reddit.close(),
            self._stocktwits.close(),
            self._news.close(),
            self._perplexity.close(),
        )

    async def _fetch_crypto_snapshot(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = await self._binance.get_ticker(symbol)
            return {
                "timestamp": self._timestamp_from_millis(ticker.get("closeTime")),
                "source": "binance",
                "open_price": self._to_decimal(ticker.get("openPrice")),
                "high_price": self._to_decimal(ticker.get("highPrice")),
                "low_price": self._to_decimal(ticker.get("lowPrice")),
                "close_price": self._to_decimal(ticker.get("lastPrice")),
                "volume": float(ticker.get("volume", 0.0)),
            }
        except (InvalidSymbolError, RateLimitExceededError, ExternalAPIError):
            price_payload = await self._coingecko.get_price([symbol])
            coin_id = self._coingecko.map_symbol(symbol)
            coin_data = price_payload.get(coin_id, {})
            price = self._to_decimal(coin_data.get("usd", 0.0))
            return {
                "timestamp": datetime.now(timezone.utc),
                "source": "coingecko",
                "open_price": price,
                "high_price": price,
                "low_price": price,
                "close_price": price,
                "volume": float(coin_data.get("usd_24h_vol", 0.0)),
            }

    async def _fetch_h1_candles(self, asset: Asset, limit: int) -> tuple[List[Dict[str, Any]], str]:
        if asset.asset_type == AssetType.CRYPTO:
            payload = await self._binance.get_klines(asset.symbol, interval="1h", limit=limit)
            rows: List[Dict[str, Any]] = []
            for item in payload:
                if len(item) < 7:
                    continue
                rows.append(
                    {
                        "timestamp": self._timestamp_from_millis(item[6]),
                        "open_price": self._to_decimal(item[1]),
                        "high_price": self._to_decimal(item[2]),
                        "low_price": self._to_decimal(item[3]),
                        "close_price": self._to_decimal(item[4]),
                        "volume": float(item[5]),
                    }
                )
            return rows[-limit:], "binance_h1_backfill"

        if asset.asset_type == AssetType.STOCK:
            if not self._finnhub.has_api_key():
                return [], "finnhub_h1_backfill"
            now_ts = int(datetime.now(timezone.utc).timestamp())
            from_ts = now_ts - (90 * 24 * 3600)
            payload = await self._finnhub.get_candles(asset.symbol, resolution="60", from_ts=from_ts, to_ts=now_ts)
            if str(payload.get("s", "")).lower() != "ok":
                return [], "finnhub_h1_backfill"
            ts = payload.get("t") or []
            opens = payload.get("o") or []
            highs = payload.get("h") or []
            lows = payload.get("l") or []
            closes = payload.get("c") or []
            volumes = payload.get("v") or []
            rows = []
            for idx, value in enumerate(ts):
                try:
                    rows.append(
                        {
                            "timestamp": self._timestamp_from_unix(value),
                            "open_price": self._to_decimal(opens[idx]),
                            "high_price": self._to_decimal(highs[idx]),
                            "low_price": self._to_decimal(lows[idx]),
                            "close_price": self._to_decimal(closes[idx]),
                            "volume": float(volumes[idx]),
                        }
                    )
                except Exception:
                    continue
            return rows[-limit:], "finnhub_h1_backfill"

        return [], "unknown_h1_backfill"

    async def _backfill_asset_m1(self, asset: Asset, days: int) -> int:
        if asset.asset_type == AssetType.STOCK:
            points = await self._fetch_stock_m1_points(asset, days)
            if not points:
                return 0
            return await self._save_price_batch(
                asset_id=asset.id,
                symbol=asset.symbol,
                timeframe=PriceTimeframe.M1,
                source="finnhub_m1_backfill",
                points=points,
                publish=False,
            )

        if asset.asset_type == AssetType.CRYPTO:
            return await self._fetch_and_store_crypto_m1_points(asset, days)

        return 0

    async def _fetch_stock_m1_points(self, asset: Asset, days: int) -> List[Dict[str, Any]]:
        if not self._finnhub.has_api_key():
            return []
        now_ts = int(datetime.now(timezone.utc).timestamp())
        from_ts = now_ts - (max(1, days) * 24 * 3600)
        payload = await self._finnhub.get_candles(asset.symbol, resolution="1", from_ts=from_ts, to_ts=now_ts)
        if str(payload.get("s", "")).lower() != "ok":
            return []
        timestamps = payload.get("t") or []
        opens = payload.get("o") or []
        highs = payload.get("h") or []
        lows = payload.get("l") or []
        closes = payload.get("c") or []
        volumes = payload.get("v") or []
        points: List[Dict[str, Any]] = []
        for idx, unix_ts in enumerate(timestamps):
            try:
                points.append(
                    {
                        "timestamp": self._timestamp_from_unix(unix_ts),
                        "open_price": self._to_decimal(opens[idx]),
                        "high_price": self._to_decimal(highs[idx]),
                        "low_price": self._to_decimal(lows[idx]),
                        "close_price": self._to_decimal(closes[idx]),
                        "volume": float(volumes[idx]),
                    }
                )
            except Exception:
                continue
        return points

    async def _fetch_and_store_crypto_m1_points(self, asset: Asset, days: int) -> int:
        total_saved = 0
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - (max(1, days) * 24 * 3600 * 1000)
        cursor_ms = start_ms
        max_loops = 200

        for _ in range(max_loops):
            if cursor_ms > end_ms:
                break
            payload = await self._binance.get_klines(
                asset.symbol,
                interval="1m",
                limit=M1_BACKFILL_CHUNK_LIMIT,
                start_time_ms=cursor_ms,
                end_time_ms=end_ms,
            )
            if not payload:
                break
            points: List[Dict[str, Any]] = []
            for item in payload:
                if len(item) < 7:
                    continue
                points.append(
                    {
                        "timestamp": self._timestamp_from_millis(item[6]),
                        "open_price": self._to_decimal(item[1]),
                        "high_price": self._to_decimal(item[2]),
                        "low_price": self._to_decimal(item[3]),
                        "close_price": self._to_decimal(item[4]),
                        "volume": float(item[5]),
                    }
                )
            if points:
                total_saved += await self._save_price_batch(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    timeframe=PriceTimeframe.M1,
                    source="binance_m1_backfill",
                    points=points,
                    publish=False,
                )

            try:
                last_open_ms = int(payload[-1][0])
            except Exception:
                break
            next_cursor = last_open_ms + M1_STEP_MS
            if next_cursor <= cursor_ms:
                break
            cursor_ms = next_cursor
            if len(payload) < M1_BACKFILL_CHUNK_LIMIT:
                break

        return total_saved

    async def _get_active_assets(self, asset_type: AssetType) -> List[Asset]:
        async with self._session_factory() as session:
            query = select(Asset).where(Asset.asset_type == asset_type, Asset.is_active.is_(True)).order_by(Asset.symbol.asc())
            result = await session.execute(query)
            return list(result.scalars().all())

    async def _get_all_active_assets(self) -> List[Asset]:
        async with self._session_factory() as session:
            query = select(Asset).where(Asset.is_active.is_(True)).order_by(Asset.symbol.asc())
            result = await session.execute(query)
            return list(result.scalars().all())

    async def _get_top_assets_by_volume(self, limit: int) -> List[Asset]:
        async with self._session_factory() as session:
            latest_subquery = (
                select(PriceData.asset_id, func.max(PriceData.timestamp).label("latest_ts"))
                .where(PriceData.timeframe == PriceTimeframe.M1)
                .group_by(PriceData.asset_id)
                .subquery()
            )
            query = (
                select(Asset)
                .join(latest_subquery, Asset.id == latest_subquery.c.asset_id)
                .join(
                    PriceData,
                    and_(
                        PriceData.asset_id == latest_subquery.c.asset_id,
                        PriceData.timestamp == latest_subquery.c.latest_ts,
                        PriceData.timeframe == PriceTimeframe.M1,
                    ),
                )
                .where(Asset.is_active.is_(True))
                .order_by(PriceData.volume.desc(), Asset.symbol.asc())
                .limit(limit)
            )
            rows = list((await session.execute(query)).scalars().all())
        if rows:
            return rows
        all_assets = await self._get_all_active_assets()
        return all_assets[:limit]

    async def _count_recent_price_points(self, asset_id: int, timeframe: PriceTimeframe, since: datetime) -> int:
        async with self._session_factory() as session:
            query = select(func.count(PriceData.id)).where(
                PriceData.asset_id == asset_id,
                PriceData.timeframe == timeframe,
                PriceData.timestamp >= since,
            )
            return int((await session.execute(query)).scalar_one() or 0)

    def _target_m1_points(self, asset_type: AssetType, days: int) -> int:
        safe_days = max(1, int(days))
        if asset_type == AssetType.STOCK:
            # ~390 regular-trading minutes/day; keep buffer for weekends/holidays.
            return max(300, int(safe_days * 390 * 0.6))
        return max(600, int(safe_days * 24 * 60 * 0.85))

    async def _save_price_data(
        self,
        asset_id: int,
        symbol: str,
        timestamp: datetime,
        source: str,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: float,
        timeframe: PriceTimeframe = PriceTimeframe.M1,
        publish: bool = True,
    ) -> None:
        await self._save_price_batch(
            asset_id=asset_id,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            points=[
                {
                    "timestamp": timestamp,
                    "open_price": open_price,
                    "high_price": high_price,
                    "low_price": low_price,
                    "close_price": close_price,
                    "volume": volume,
                }
            ],
            publish=publish,
        )

    async def _save_price_batch(
        self,
        asset_id: int,
        symbol: str,
        timeframe: PriceTimeframe,
        source: str,
        points: Sequence[Dict[str, Any]],
        publish: bool,
    ) -> int:
        if not points:
            return 0
        prepared_by_ts: Dict[datetime, Dict[str, Any]] = {}
        for point in points:
            timestamp = point.get("timestamp")
            if not isinstance(timestamp, datetime):
                continue
            normalized_ts = self._normalize_timestamp(timestamp)
            prepared_by_ts[normalized_ts] = {
                "timestamp": normalized_ts,
                "open_price": self._to_decimal(point.get("open_price")),
                "high_price": self._to_decimal(point.get("high_price")),
                "low_price": self._to_decimal(point.get("low_price")),
                "close_price": self._to_decimal(point.get("close_price")),
                "volume": float(point.get("volume", 0.0)),
            }
        prepared: List[Dict[str, Any]] = list(prepared_by_ts.values())
        if not prepared:
            return 0

        timestamps = [item["timestamp"] for item in prepared]
        async with self._session_factory() as session:
            existing_by_ts: Dict[datetime, PriceData] = {}
            for chunk in self._chunked(timestamps, DB_IN_CLAUSE_CHUNK):
                existing_query = select(PriceData).where(
                    PriceData.asset_id == asset_id,
                    PriceData.timeframe == timeframe,
                    PriceData.timestamp.in_(chunk),
                )
                existing_rows = list((await session.execute(existing_query)).scalars().all())
                for row in existing_rows:
                    existing_by_ts[self._normalize_timestamp(row.timestamp)] = row

            for item in prepared:
                existing = existing_by_ts.get(item["timestamp"])
                if existing is None:
                    session.add(
                        PriceData(
                            asset_id=asset_id,
                            timestamp=item["timestamp"],
                            timeframe=timeframe,
                            source=source,
                            open=item["open_price"],
                            high=item["high_price"],
                            low=item["low_price"],
                            close=item["close_price"],
                            volume=item["volume"],
                        )
                    )
                else:
                    existing.open = item["open_price"]
                    existing.high = item["high_price"]
                    existing.low = item["low_price"]
                    existing.close = item["close_price"]
                    existing.volume = item["volume"]
                    existing.source = source
            await session.commit()

        if publish and timeframe == PriceTimeframe.M1:
            for item in prepared:
                await price_pubsub.publish(
                    {
                        "type": "price_update",
                        "symbol": symbol.upper(),
                        "source": source,
                        "timeframe": timeframe.value,
                        "timestamp": item["timestamp"].isoformat(),
                        "open": float(item["open_price"]),
                        "high": float(item["high_price"]),
                        "low": float(item["low_price"]),
                        "close": float(item["close_price"]),
                        "volume": float(item["volume"]),
                    }
                )
        return len(prepared)

    def _chunked(self, values: Sequence[datetime], size: int) -> List[List[datetime]]:
        chunk_size = max(1, int(size))
        return [list(values[idx : idx + chunk_size]) for idx in range(0, len(values), chunk_size)]

    def _normalize_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(second=0, microsecond=0)

    async def _collect_reddit_records(self, assets_by_symbol: Dict[str, Asset], tracked_symbols: Sequence[str]) -> int:
        if not self._reddit.has_credentials():
            logger.warning("Skipping Reddit collection: OAuth credentials missing.", extra={"event": "collect_reddit_skipped"})
            return 0
        records: List[SentimentRecord] = []
        for subreddit in TARGET_SUBREDDITS:
            try:
                posts = await self._reddit.get_subreddit_posts(subreddit=subreddit, sort="new", limit=50)
            except Exception:
                logger.exception("Reddit subreddit collection failed.", extra={"event": "collect_reddit_subreddit_error", "subreddit": subreddit})
                continue
            for post in posts:
                text = self._combine_text(post.get("title"), post.get("selftext"))
                mentions = self._reddit.extract_ticker_mentions(text, tracked_symbols)
                if not mentions:
                    continue
                created_at = self._timestamp_from_unix(post.get("created_utc"))
                source_url = self._build_reddit_url(post)
                author = post.get("author")
                for symbol in mentions:
                    asset = assets_by_symbol.get(symbol)
                    if asset is None:
                        continue
                    records.append(
                        self._build_sentiment_record(
                            asset_id=asset.id,
                            source=SentimentSource.REDDIT,
                            text=text,
                            source_url=source_url,
                            author=author,
                            created_at=created_at,
                        )
                    )
        return await self._insert_sentiment_records(records)

    async def _collect_stocktwits_records(self, assets: Sequence[Asset]) -> int:
        saved_count = 0
        for asset in assets:
            try:
                messages = await self._stocktwits.get_symbol_stream(asset.symbol, limit=20)
                records = [self._stocktwits_to_record(asset.id, item) for item in messages]
                saved_count += await self._insert_sentiment_records(records)
            except InvalidSymbolError:
                logger.warning("StockTwits symbol unsupported.", extra={"event": "collect_stocktwits_invalid_symbol", "symbol": asset.symbol})
            except RateLimitExceededError:
                logger.warning("StockTwits hourly limit reached; stopping current cycle.", extra={"event": "collect_stocktwits_rate_limit"})
                break
            except Exception:
                logger.exception("StockTwits collection failed.", extra={"event": "collect_stocktwits_error", "symbol": asset.symbol})
        return saved_count

    async def _collect_news_records(self, assets: Sequence[Asset]) -> int:
        if not self._news.has_available_provider():
            logger.warning("Skipping news collection: no provider credentials configured.", extra={"event": "collect_news_skipped"})
            return 0
        saved_count = 0
        for asset in assets:
            try:
                items = await self._news.collect_news(asset.symbol)
                records = [self._news_to_record(asset.id, item) for item in items]
                saved_count += await self._insert_sentiment_records(records)
            except Exception:
                logger.exception("News collection failed.", extra={"event": "collect_news_error", "symbol": asset.symbol})
        return saved_count

    async def _insert_sentiment_records(self, records: Sequence[SentimentRecord]) -> int:
        if not records:
            return 0
        saved = 0
        async with self._session_factory() as session:
            for record in records:
                if await self._sentiment_record_exists(session, record):
                    continue
                session.add(record)
                saved += 1
            await session.commit()
        return saved

    async def _sentiment_record_exists(self, session: AsyncSession, record: SentimentRecord) -> bool:
        if not record.source_url:
            return False
        query = select(SentimentRecord.id).where(
            SentimentRecord.source == record.source,
            SentimentRecord.source_url == record.source_url,
            SentimentRecord.asset_id == record.asset_id,
        )
        return (await session.execute(query)).scalar_one_or_none() is not None

    def _stocktwits_to_record(self, asset_id: int, message: Dict[str, Any]) -> SentimentRecord:
        label, score = self._map_stocktwits_sentiment(message.get("basic_sentiment"))
        return self._build_sentiment_record(
            asset_id=asset_id,
            source=SentimentSource.STOCKTWITS,
            text=message.get("body") or "",
            source_url=message.get("source_url"),
            author=message.get("user"),
            created_at=self._parse_datetime(message.get("created_at")),
            sentiment_score=score,
            sentiment_label=label,
            model_used=SentimentModel.PRE_LABELED,
            confidence=0.8,
        )

    def _news_to_record(self, asset_id: int, item: Dict[str, Any]) -> SentimentRecord:
        return self._build_sentiment_record(
            asset_id=asset_id,
            source=SentimentSource.NEWS,
            text=item.get("text") or "",
            source_url=item.get("url"),
            author=item.get("author"),
            created_at=self._parse_datetime(item.get("created_at")),
        )

    def _build_sentiment_record(
        self,
        asset_id: Optional[int],
        source: SentimentSource,
        text: str,
        source_url: Optional[str],
        author: Optional[str],
        created_at: datetime,
        sentiment_score: Optional[float] = None,
        sentiment_label: Optional[SentimentLabel] = None,
        model_used: Optional[SentimentModel] = None,
        confidence: Optional[float] = None,
    ) -> SentimentRecord:
        snippet = self._truncate_text(text)
        return SentimentRecord(
            asset_id=asset_id,
            source=source,
            text_snippet=snippet,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            model_used=model_used,
            confidence=confidence,
            source_url=source_url,
            author=author,
            created_at=created_at,
        )

    def _combine_text(self, title: Any, body: Any) -> str:
        title_text = str(title or "").strip()
        body_text = str(body or "").strip()
        return "{0} {1}".format(title_text, body_text).strip()

    def _truncate_text(self, value: str) -> str:
        cleaned = value.strip()
        return cleaned[:500] if len(cleaned) > 500 else cleaned

    def _build_reddit_url(self, post: Dict[str, Any]) -> Optional[str]:
        permalink = post.get("permalink")
        if isinstance(permalink, str) and permalink.strip():
            return "https://reddit.com{0}".format(permalink)
        url = post.get("url")
        if isinstance(url, str) and url.strip():
            return url
        return None

    def _map_stocktwits_sentiment(self, raw_value: Any) -> tuple[SentimentLabel, float]:
        value = str(raw_value or "").strip().lower()
        if value == "bullish":
            return (SentimentLabel.POSITIVE, 0.5)
        if value == "bearish":
            return (SentimentLabel.NEGATIVE, -0.5)
        return (SentimentLabel.NEUTRAL, 0.0)

    def _format_trending_topics(self, topics: Dict[str, List[str]]) -> str:
        stocks = ", ".join(topics.get("stocks", [])[:5]) or "n/a"
        crypto = ", ".join(topics.get("crypto", [])[:5]) or "n/a"
        return "Trending stocks: {0}. Trending crypto: {1}.".format(stocks, crypto)

    def _parse_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)

    async def _handle_finnhub_ws_message(self, payload: Dict[str, Any]) -> None:
        if payload.get("type") != "trade":
            return
        for trade in payload.get("data", []):
            logger.debug("Finnhub WS trade", extra={"event": "finnhub_trade", "symbol": trade.get("s")})

    async def _handle_binance_ws_message(self, payload: Dict[str, Any]) -> None:
        if payload.get("e") not in {"24hrTicker", "kline"}:
            return
        logger.debug("Binance WS event", extra={"event": "binance_stream", "type": payload.get("e")})

    def _timestamp_from_unix(self, value: Any) -> datetime:
        if value in (None, 0, "0"):
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(int(value), tz=timezone.utc)

    def _timestamp_from_millis(self, value: Any) -> datetime:
        if value in (None, 0, "0"):
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(int(value) / 1000.0, tz=timezone.utc)

    def _to_decimal(self, value: Any) -> Decimal:
        return Decimal(str(value or 0.0))
