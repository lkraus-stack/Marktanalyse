"""API routers package."""

from routers.alerts import router as alerts_router
from routers.market_data import router as market_data_router
from routers.signals import router as signals_router
from routers.sentiment import router as sentiment_router
from routers.social_data import router as social_data_router
from routers.trading import router as trading_router

__all__ = ["alerts_router", "market_data_router", "signals_router", "sentiment_router", "social_data_router", "trading_router"]
