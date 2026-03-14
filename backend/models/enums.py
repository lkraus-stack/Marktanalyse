from __future__ import annotations

from enum import Enum


class AssetType(str, Enum):
    """Supported asset categories."""

    STOCK = "stock"
    CRYPTO = "crypto"


class WatchStatus(str, Enum):
    """User-defined tracking status for assets."""

    NONE = "none"
    WATCHLIST = "watchlist"
    HOLDING = "holding"


class PriceTimeframe(str, Enum):
    """Supported OHLCV timeframes."""

    M1 = "1m"
    M5 = "5m"
    H1 = "1h"
    D1 = "1d"


class SentimentSource(str, Enum):
    """Sources used to ingest sentiment data."""

    REDDIT = "reddit"
    STOCKTWITS = "stocktwits"
    NEWS = "news"
    TWITTER = "twitter"
    PERPLEXITY = "perplexity"


class SentimentLabel(str, Enum):
    """Classified sentiment categories."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class SentimentModel(str, Enum):
    """NLP model/source that produced a sentiment label."""

    FINVADER = "finvader"
    FINBERT = "finbert"
    PRE_LABELED = "pre_labeled"


class AggregationTimeframe(str, Enum):
    """Supported windows for aggregated sentiment."""

    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class AggregationSource(str, Enum):
    """Source scope for aggregated sentiment records."""

    REDDIT = "reddit"
    STOCKTWITS = "stocktwits"
    NEWS = "news"
    TWITTER = "twitter"
    PERPLEXITY = "perplexity"
    ALL = "all"


class SignalType(str, Enum):
    """Trading signal directions."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class AlertType(str, Enum):
    """Types of alert rules."""

    SIGNAL_THRESHOLD = "signal_threshold"
    PRICE_TARGET = "price_target"
    SENTIMENT_SHIFT = "sentiment_shift"
    CUSTOM = "custom"


class DeliveryMethod(str, Enum):
    """Delivery channels for alerts."""

    WEBSOCKET = "websocket"
    EMAIL = "email"
    TELEGRAM = "telegram"


class BrokerName(str, Enum):
    """Supported broker backends."""

    ALPACA_PAPER = "alpaca_paper"
    KRAKEN = "kraken"


class TradeSide(str, Enum):
    """Order side direction."""

    BUY = "buy"
    SELL = "sell"


class TradeStatus(str, Enum):
    """Lifecycle status of one trade/order."""

    PENDING_CONFIRMATION = "pending_confirmation"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    FAILED = "failed"


class AutoTradeMode(str, Enum):
    """Autotrader operation mode."""

    MANUAL = "manual"
    SEMI_AUTO = "semi_auto"
    AUTO = "auto"
