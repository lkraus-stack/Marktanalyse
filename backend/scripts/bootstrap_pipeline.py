from __future__ import annotations

import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.data_collector import DataCollector
from services.sentiment_engine import SentimentEngine
from services.signal_engine import SignalEngine


async def run_bootstrap() -> None:
    collector = DataCollector()
    sentiment_engine = SentimentEngine()
    signal_engine = SignalEngine()
    try:
        backfill_h1 = await collector.backfill_analysis_candles(h1_limit=120)
        backfill_m1 = await collector.backfill_m1_history(days=7)
        prices = await collector.collect_all()
        social = await collector.collect_social_data()
        processed = await sentiment_engine.process_unscored_records(limit=500, use_finbert=False)
        aggregated = await sentiment_engine.aggregate_all_assets(timeframe="1h")
        generated = await signal_engine.generate_all_signals(timeframe="1h")
    finally:
        await collector.shutdown()
    print("backfilled_h1:", backfill_h1)
    print("backfilled_m1:", backfill_m1)
    print("prices:", prices)
    print("social:", social)
    print("sentiment_processed:", processed)
    print("aggregated_assets_1h:", aggregated)
    print("generated_signals:", generated)


def main() -> None:
    asyncio.run(run_bootstrap())


if __name__ == "__main__":
    main()
