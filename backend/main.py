from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import asyncio as redis_asyncio
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from config import get_settings
from database import AsyncSessionLocal, create_tables
from rate_limit import limiter
from routers.alerts import router as alerts_router
from routers.market_data import router as market_data_router
from routers.signals import router as signals_router
from routers.sentiment import router as sentiment_router
from routers.social_data import router as social_data_router
from routers.trading import router as trading_router
from services.price_stream import price_pubsub
from services.scheduler import MarketDataScheduler


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, str):
            payload["event"] = event
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
        }
        for key, value in record.__dict__.items():
            if key in reserved or key.startswith("_"):
                continue
            if key in payload:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            else:
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    """Configure root logger to emit JSON logs."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


configure_logging()
settings = get_settings()
logger = logging.getLogger("market_intelligence")
market_scheduler = MarketDataScheduler()

if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            integrations=[FastApiIntegration()],
            traces_sample_rate=max(0.0, min(1.0, settings.sentry_traces_sample_rate)),
        )
        logger.info("Sentry initialized.", extra={"event": "sentry_initialized"})
    except Exception:
        logger.exception("Sentry initialization failed.", extra={"event": "sentry_init_failed"})

if settings.environment.lower() == "production" and settings.frontend_url:
    cors_allow_origins = [settings.frontend_url]
else:
    cors_allow_origins = settings.cors_origins

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(alerts_router)
app.include_router(market_data_router)
app.include_router(signals_router)
app.include_router(sentiment_router)
app.include_router(social_data_router)
app.include_router(trading_router)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Require X-API-Key for protected API endpoints when configured."""
    path = request.url.path
    if path.startswith("/api/") and path != "/api/health":
        expected_key = settings.internal_api_key
        if expected_key:
            provided_key = request.headers.get("X-API-Key", "")
            if not provided_key or not secrets.compare_digest(provided_key, expected_key):
                return JSONResponse(status_code=401, content={"detail": "Ungueltiger API-Key."})
    return await call_next(request)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize infrastructure and log startup completion."""
    try:
        if settings.environment.lower() == "development":
            await create_tables()
        else:
            logger.info(
                "Skipping metadata create_all outside development.",
                extra={"event": "startup_skip_create_all"},
            )
    except Exception:
        logger.exception("Database initialization failed.", extra={"event": "startup_failure"})
        raise

    logger.info("Application startup completed.", extra={"event": "startup", "environment": settings.environment})

    if settings.enable_scheduler:
        try:
            await market_scheduler.start()
        except Exception:
            logger.exception("Scheduler startup failed.", extra={"event": "scheduler_startup_failed"})
            raise


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Release scheduler and external service resources."""
    if settings.enable_scheduler:
        await market_scheduler.shutdown()


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Health endpoint including DB/Redis/API-key status checks."""
    checks: Dict[str, Any] = {
        "database": {"ok": False},
        "redis": {"ok": True, "status": "skipped"},
        "api_keys": {
            "alpaca": bool(settings.alpaca_api_key and settings.alpaca_secret_key),
            "kraken": bool(settings.kraken_api_key and settings.kraken_secret_key),
            "finnhub": bool(settings.finnhub_api_key),
            "perplexity": bool(settings.perplexity_api_key),
        },
    }
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}

    if settings.redis_url:
        client = redis_asyncio.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        try:
            await client.ping()
            checks["redis"] = {"ok": True, "status": "reachable"}
        except Exception as exc:
            checks["redis"] = {"ok": False, "status": "unreachable", "error": str(exc)}
        finally:
            await client.aclose()

    overall_ok = bool(checks["database"]["ok"]) and bool(checks["redis"]["ok"])
    return {
        "status": "ok" if overall_ok else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "checks": checks,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unexpected errors and keep API responses stable."""
    logger.exception(
        "Unhandled exception.",
        extra={"event": "unhandled_exception", "path": request.url.path, "method": request.method},
    )
    return JSONResponse(status_code=500, content={"detail": "Interner Serverfehler."})


@app.websocket("/ws/prices")
async def prices_websocket(websocket: WebSocket) -> None:
    """Push live price and alert updates to connected dashboard clients."""
    await websocket.accept()
    await websocket.send_json({"type": "stream_info", "channels": ["prices", "alerts"]})
    queue = await price_pubsub.subscribe()
    logger.info("Price websocket client connected.", extra={"event": "ws_client_connected"})
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=20)
                await websocket.send_json(payload)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        logger.info("Price websocket client disconnected.", extra={"event": "ws_client_disconnected"})
    finally:
        await price_pubsub.unsubscribe(queue)
