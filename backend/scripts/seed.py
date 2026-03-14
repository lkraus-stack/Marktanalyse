from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Dict, List

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import AsyncSessionLocal, create_tables
from models import Asset, AssetType, WatchStatus


DEFAULT_ASSETS: List[Dict[str, str]] = [
    {"symbol": "AAPL", "name": "Apple Inc.", "asset_type": AssetType.STOCK.value, "exchange": "NASDAQ"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "asset_type": AssetType.STOCK.value, "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "asset_type": AssetType.STOCK.value, "exchange": "NASDAQ"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "asset_type": AssetType.STOCK.value, "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "asset_type": AssetType.STOCK.value, "exchange": "NASDAQ"},
    {"symbol": "BTC", "name": "Bitcoin", "asset_type": AssetType.CRYPTO.value, "exchange": "Kraken"},
    {"symbol": "ETH", "name": "Ethereum", "asset_type": AssetType.CRYPTO.value, "exchange": "Kraken"},
    {"symbol": "SOL", "name": "Solana", "asset_type": AssetType.CRYPTO.value, "exchange": "Kraken"},
    {"symbol": "XRP", "name": "XRP", "asset_type": AssetType.CRYPTO.value, "exchange": "Kraken"},
    {"symbol": "DOGE", "name": "Dogecoin", "asset_type": AssetType.CRYPTO.value, "exchange": "Kraken"},
]


async def seed_assets() -> None:
    """Create tables and seed default tracked assets."""
    await create_tables()

    async with AsyncSessionLocal() as session:
        symbols = [item["symbol"] for item in DEFAULT_ASSETS]
        existing = await session.execute(select(Asset.symbol).where(Asset.symbol.in_(symbols)))
        existing_symbols = set(existing.scalars().all())

        new_assets = []
        for item in DEFAULT_ASSETS:
            if item["symbol"] in existing_symbols:
                continue
            new_assets.append(
                Asset(
                    symbol=item["symbol"],
                    name=item["name"],
                    asset_type=AssetType(item["asset_type"]),
                    exchange=item["exchange"],
                    watch_status=WatchStatus.NONE,
                    is_active=True,
                )
            )

        if not new_assets:
            print("Seed abgeschlossen: keine neuen Assets eingefuegt.")
            return

        session.add_all(new_assets)
        await session.commit()
        print(f"Seed abgeschlossen: {len(new_assets)} Assets eingefuegt.")


def main() -> None:
    """Entry point for CLI execution."""
    asyncio.run(seed_assets())


if __name__ == "__main__":
    main()
