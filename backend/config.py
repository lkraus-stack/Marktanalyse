from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Markt-Intelligence API"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./market_intelligence.db"
    neon_database_url: Optional[str] = None
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    frontend_url: Optional[str] = None
    redis_url: Optional[str] = None
    internal_api_key: Optional[str] = None
    sentry_dsn: Optional[str] = None
    sentry_traces_sample_rate: float = 0.05

    finnhub_api_key: Optional[str] = None
    coingecko_api_key: Optional[str] = None
    alpha_vantage_api_key: Optional[str] = None
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    reddit_user_agent: str = "markt-intelligence/0.1 by lukas"
    perplexity_api_key: Optional[str] = None
    perplexity_daily_budget_usd: float = 0.5
    perplexity_request_cost_usd: float = 0.006
    finbert_enabled: bool = False
    sentiment_batch_size: int = 16
    sentiment_process_limit: int = 100
    signal_weight_sentiment: float = 0.35
    signal_weight_technical: float = 0.40
    signal_weight_volume: float = 0.15
    signal_weight_momentum: float = 0.10
    alert_cooldown_minutes: int = 60
    alert_delivery_retries: int = 2
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_use_tls: bool = True
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    alpaca_api_key: Optional[str] = None
    alpaca_secret_key: Optional[str] = None
    alpaca_paper_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_live_base_url: str = "https://api.alpaca.markets"
    kraken_api_key: Optional[str] = None
    kraken_secret_key: Optional[str] = None
    kraken_base_url: str = "https://api.kraken.com"
    auto_trader_mode: str = "manual"
    auto_is_live: bool = False
    auto_max_position_size_usd: float = 1000.0
    auto_max_positions: int = 5
    auto_min_signal_strength: float = 60.0
    auto_stop_loss_pct: float = 5.0
    auto_take_profit_pct: float = 10.0
    auto_double_confirm_threshold_eur: float = 500.0
    auto_daily_loss_limit_eur: float = 100.0
    auto_max_trades_per_day: int = 10
    binance_api_key: Optional[str] = None
    enable_scheduler: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        """Allow CORS origins as comma-separated string or list."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        raise TypeError("CORS origins must be a list or comma-separated string.")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
