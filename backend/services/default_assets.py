from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def seed_default_assets(session: AsyncSession) -> Dict[str, Any]:
    """Insert the default tracked assets when they are missing."""
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

    if new_assets:
        session.add_all(new_assets)
        await session.commit()

    active_assets_total = int(
        (await session.execute(select(func.count(Asset.id)).where(Asset.is_active.is_(True)))).scalar_one() or 0
    )
    return {
        "seeded_count": len(new_assets),
        "existing_count": len(existing_symbols),
        "total_defaults": len(DEFAULT_ASSETS),
        "active_assets_total": active_assets_total,
        "symbols_added": [asset.symbol for asset in new_assets],
    }
