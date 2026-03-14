"""Pydantic schemas package."""

from schemas.aggregated_sentiment import (
    AggregatedSentimentCreate,
    AggregatedSentimentRead,
    AggregatedSentimentUpdate,
)
from schemas.alert import AlertCreate, AlertRead, AlertUpdate
from schemas.alert_history import AlertHistoryCreate, AlertHistoryRead, AlertHistoryUpdate
from schemas.asset import AssetCreate, AssetRead, AssetUpdate
from schemas.portfolio_snapshot import PortfolioSnapshotCreate, PortfolioSnapshotRead
from schemas.price_data import PriceDataCreate, PriceDataRead, PriceDataUpdate
from schemas.sentiment_record import SentimentRecordCreate, SentimentRecordRead, SentimentRecordUpdate
from schemas.trade import TradeCreate, TradeRead, TradeUpdate
from schemas.trading_signal import TradingSignalCreate, TradingSignalRead, TradingSignalUpdate

__all__ = [
    "AggregatedSentimentCreate",
    "AggregatedSentimentRead",
    "AggregatedSentimentUpdate",
    "AlertCreate",
    "AlertHistoryCreate",
    "AlertHistoryRead",
    "AlertHistoryUpdate",
    "AlertRead",
    "AlertUpdate",
    "AssetCreate",
    "AssetRead",
    "AssetUpdate",
    "PortfolioSnapshotCreate",
    "PortfolioSnapshotRead",
    "PriceDataCreate",
    "PriceDataRead",
    "PriceDataUpdate",
    "SentimentRecordCreate",
    "SentimentRecordRead",
    "SentimentRecordUpdate",
    "TradingSignalCreate",
    "TradingSignalRead",
    "TradingSignalUpdate",
    "TradeCreate",
    "TradeRead",
    "TradeUpdate",
]
