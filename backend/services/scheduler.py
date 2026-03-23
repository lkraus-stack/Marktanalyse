from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from database import AsyncSessionLocal
from models import Asset, AssetType
from services.data_collector import DataCollector
from services.alert_manager import AlertManager
from services.auto_trader import AutoTrader, get_auto_trader
from services.sentiment_engine import SentimentEngine
from services.signal_engine import SignalEngine

logger = logging.getLogger("market_intelligence.services.scheduler")


class MarketDataScheduler:
    """APScheduler coordinator for stock/crypto collection cycles."""

    def __init__(
        self,
        data_collector: Optional[DataCollector] = None,
        sentiment_engine: Optional[SentimentEngine] = None,
        signal_engine: Optional[SignalEngine] = None,
        alert_manager: Optional[AlertManager] = None,
        auto_trader: Optional[AutoTrader] = None,
    ) -> None:
        self._collector = data_collector or DataCollector()
        self._sentiment_engine = sentiment_engine or SentimentEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._alert_manager = alert_manager or AlertManager()
        self._auto_trader = auto_trader or get_auto_trader()
        self._scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self._started = False

    async def start(self) -> None:
        """Start collection jobs and WebSocket streams."""
        if self._started:
            return
        self._register_jobs()
        self._scheduler.start()
        stock_symbols = await self._get_symbols(AssetType.STOCK)
        crypto_symbols = await self._get_symbols(AssetType.CRYPTO)
        await self._collector.start_websockets(stock_symbols, crypto_symbols)
        self._started = True
        logger.info("Market scheduler started.", extra={"event": "scheduler_started"})

    async def shutdown(self) -> None:
        """Stop scheduler jobs and close service resources."""
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        await self._collector.shutdown()
        await self._alert_manager.shutdown()
        await self._auto_trader.shutdown()
        self._started = False
        logger.info("Market scheduler stopped.", extra={"event": "scheduler_stopped"})

    def _register_jobs(self) -> None:
        self._scheduler.add_job(
            self._run_crypto_collection,
            trigger=IntervalTrigger(minutes=2, timezone=timezone.utc),
            id="collect_crypto_prices",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_social_collection,
            trigger=IntervalTrigger(minutes=30, timezone=timezone.utc),
            id="collect_social_data",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_perplexity_collection,
            trigger=IntervalTrigger(hours=4, timezone=timezone.utc),
            id="collect_perplexity_summaries",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_finvader_cycle,
            trigger=IntervalTrigger(minutes=15, timezone=timezone.utc),
            id="process_finvader_sentiment",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_finbert_cycle,
            trigger=IntervalTrigger(minutes=60, timezone=timezone.utc),
            id="process_finbert_sentiment",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_aggregation_1h_cycle,
            trigger=IntervalTrigger(minutes=30, timezone=timezone.utc),
            id="aggregate_sentiment_1h",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_aggregation_1d_cycle,
            trigger=IntervalTrigger(hours=4, timezone=timezone.utc),
            id="aggregate_sentiment_1d",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_signal_generation_cycle,
            trigger=IntervalTrigger(minutes=30, timezone=timezone.utc),
            id="generate_trading_signals",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_signal_expiration_cycle,
            trigger=IntervalTrigger(hours=1, timezone=timezone.utc),
            id="expire_trading_signals",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_alert_evaluation_cycle,
            trigger=IntervalTrigger(minutes=5, timezone=timezone.utc),
            id="evaluate_alerts",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_trade_check_cycle,
            trigger=IntervalTrigger(minutes=30, timezone=timezone.utc),
            id="paper_trade_check",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_exit_check_cycle,
            trigger=IntervalTrigger(minutes=15, timezone=timezone.utc),
            id="paper_exit_check",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_portfolio_snapshot_cycle,
            trigger=IntervalTrigger(hours=1, timezone=timezone.utc),
            id="paper_portfolio_snapshot",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_stock_collection,
            trigger=CronTrigger(day_of_week="mon-fri", hour="14", minute="30-59/5", timezone=timezone.utc),
            id="collect_stock_prices_opening",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_stock_collection,
            trigger=CronTrigger(day_of_week="mon-fri", hour="15-20", minute="*/5", timezone=timezone.utc),
            id="collect_stock_prices_regular",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_stock_collection,
            trigger=CronTrigger(day_of_week="mon-fri", hour="21", minute="0", timezone=timezone.utc),
            id="collect_stock_prices_close",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

    async def _run_stock_collection(self) -> None:
        try:
            count = await self._collector.collect_stock_prices()
            logger.info("Stock cycle finished.", extra={"event": "collect_stock_cycle", "count": str(count)})
        except Exception:
            logger.exception("Stock cycle failed.", extra={"event": "collect_stock_cycle_failed"})

    async def _run_crypto_collection(self) -> None:
        try:
            count = await self._collector.collect_crypto_prices()
            logger.info("Crypto cycle finished.", extra={"event": "collect_crypto_cycle", "count": str(count)})
        except Exception:
            logger.exception("Crypto cycle failed.", extra={"event": "collect_crypto_cycle_failed"})

    async def _run_social_collection(self) -> None:
        try:
            result = await self._collector.collect_social_data()
            logger.info(
                "Social cycle finished.",
                extra={"event": "collect_social_cycle", "reddit": str(result["reddit"]), "stocktwits": str(result["stocktwits"]), "news": str(result["news"])},
            )
        except Exception:
            logger.exception("Social cycle failed.", extra={"event": "collect_social_cycle_failed"})

    async def _run_perplexity_collection(self) -> None:
        try:
            count = await self._collector.collect_perplexity_summaries()
            logger.info("AI summary cycle finished.", extra={"event": "collect_perplexity_cycle", "count": str(count)})
        except Exception:
            logger.exception("AI summary cycle failed.", extra={"event": "collect_perplexity_cycle_failed"})

    async def _run_finvader_cycle(self) -> None:
        try:
            result = await self._sentiment_engine.process_unscored_records(limit=100, use_finbert=False)
            logger.info(
                "FinVADER sentiment cycle finished.",
                extra={"event": "finvader_cycle", "processed": str(result["processed"])},
            )
        except Exception:
            logger.exception("FinVADER cycle failed.", extra={"event": "finvader_cycle_failed"})

    async def _run_finbert_cycle(self) -> None:
        try:
            upgraded = await self._sentiment_engine.upgrade_records_with_finbert(limit=200)
            logger.info("FinBERT sentiment cycle finished.", extra={"event": "finbert_cycle", "upgraded": str(upgraded)})
        except Exception:
            logger.exception("FinBERT cycle failed.", extra={"event": "finbert_cycle_failed"})

    async def _run_aggregation_1h_cycle(self) -> None:
        try:
            count = await self._sentiment_engine.aggregate_all_assets(timeframe="1h")
            logger.info("Sentiment 1h aggregation finished.", extra={"event": "aggregate_1h_cycle", "assets": str(count)})
        except Exception:
            logger.exception("Sentiment 1h aggregation failed.", extra={"event": "aggregate_1h_cycle_failed"})

    async def _run_aggregation_1d_cycle(self) -> None:
        try:
            count = await self._sentiment_engine.aggregate_all_assets(timeframe="1d")
            logger.info("Sentiment 1d aggregation finished.", extra={"event": "aggregate_1d_cycle", "assets": str(count)})
        except Exception:
            logger.exception("Sentiment 1d aggregation failed.", extra={"event": "aggregate_1d_cycle_failed"})

    async def _run_signal_generation_cycle(self) -> None:
        try:
            count = await self._signal_engine.generate_all_signals(timeframe="1h")
            logger.info("Signal generation cycle finished.", extra={"event": "signal_generation_cycle", "count": str(count)})
        except Exception:
            logger.exception("Signal generation cycle failed.", extra={"event": "signal_generation_cycle_failed"})

    async def _run_signal_expiration_cycle(self) -> None:
        try:
            expired = await self._signal_engine.expire_signals()
            logger.info("Signal expiration cycle finished.", extra={"event": "signal_expiration_cycle", "count": str(expired)})
        except Exception:
            logger.exception("Signal expiration cycle failed.", extra={"event": "signal_expiration_cycle_failed"})

    async def _run_alert_evaluation_cycle(self) -> None:
        try:
            outcome = await self._alert_manager.evaluate_alerts()
            logger.info(
                "Alert evaluation cycle finished.",
                extra={
                    "event": "alert_evaluation_cycle",
                    "evaluated": str(outcome["evaluated"]),
                    "triggered": str(outcome["triggered"]),
                    "delivered": str(outcome["delivered"]),
                },
            )
        except Exception:
            logger.exception("Alert evaluation cycle failed.", extra={"event": "alert_evaluation_cycle_failed"})

    async def _run_trade_check_cycle(self) -> None:
        try:
            outcome = await self._auto_trader.evaluate_and_trade()
            logger.info(
                "Paper trade check finished.",
                extra={
                    "event": "paper_trade_check_cycle",
                    "evaluated": str(outcome.get("evaluated", 0)),
                    "executed": str(outcome.get("executed", 0)),
                    "pending_confirmation": str(outcome.get("pending_confirmation", 0)),
                },
            )
        except Exception:
            logger.exception("Paper trade check failed.", extra={"event": "paper_trade_check_cycle_failed"})

    async def _run_exit_check_cycle(self) -> None:
        try:
            outcome = await self._auto_trader.check_exit_conditions()
            logger.info(
                "Paper exit check finished.",
                extra={
                    "event": "paper_exit_check_cycle",
                    "checked": str(outcome.get("checked", 0)),
                    "executed": str(outcome.get("executed", 0)),
                    "pending_confirmation": str(outcome.get("pending_confirmation", 0)),
                },
            )
        except Exception:
            logger.exception("Paper exit check failed.", extra={"event": "paper_exit_check_cycle_failed"})

    async def _run_portfolio_snapshot_cycle(self) -> None:
        try:
            snapshot = await self._auto_trader.take_portfolio_snapshot()
            logger.info(
                "Portfolio snapshot cycle finished.",
                extra={"event": "paper_snapshot_cycle", "created": str(snapshot is not None)},
            )
        except Exception:
            logger.exception("Portfolio snapshot cycle failed.", extra={"event": "paper_snapshot_cycle_failed"})

    async def _get_symbols(self, asset_type: AssetType) -> List[str]:
        async with AsyncSessionLocal() as session:
            query = select(Asset.symbol).where(Asset.asset_type == asset_type, Asset.is_active.is_(True))
            result = await session.execute(query)
            return [item for item in result.scalars().all()]
