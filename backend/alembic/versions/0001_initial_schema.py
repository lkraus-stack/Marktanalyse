"""Initial schema for market intelligence platform.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-13 14:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


asset_type_enum = sa.Enum("stock", "crypto", name="assettype", native_enum=False)
price_timeframe_enum = sa.Enum("1m", "5m", "1h", "1d", name="pricetimeframe", native_enum=False)
sentiment_source_enum = sa.Enum(
    "reddit",
    "stocktwits",
    "news",
    "twitter",
    "perplexity",
    name="sentimentsource",
    native_enum=False,
)
sentiment_label_enum = sa.Enum("positive", "negative", "neutral", name="sentimentlabel", native_enum=False)
sentiment_model_enum = sa.Enum("finvader", "finbert", "pre_labeled", name="sentimentmodel", native_enum=False)
aggregation_timeframe_enum = sa.Enum("1h", "4h", "1d", name="aggregationtimeframe", native_enum=False)
aggregation_source_enum = sa.Enum(
    "reddit",
    "stocktwits",
    "news",
    "twitter",
    "perplexity",
    "all",
    name="aggregationsource",
    native_enum=False,
)
signal_type_enum = sa.Enum("buy", "sell", "hold", name="signaltype", native_enum=False)
alert_type_enum = sa.Enum(
    "signal_threshold",
    "price_target",
    "sentiment_shift",
    "custom",
    name="alerttype",
    native_enum=False,
)
delivery_method_enum = sa.Enum("websocket", "email", "telegram", name="deliverymethod", native_enum=False)


def _create_assets_table() -> None:
    """Create base assets table and indexes."""
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("asset_type", asset_type_enum, nullable=False),
        sa.Column("exchange", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", name="uq_assets_symbol"),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"], unique=False)
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"], unique=False)
    op.create_index("ix_assets_is_active", "assets", ["is_active"], unique=False)


def _create_price_data_table() -> None:
    """Create OHLCV table with time-based uniqueness."""
    op.create_table(
        "price_data",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("open", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe", price_timeframe_enum, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("asset_id", "timestamp", "timeframe", name="uq_price_data_asset_timestamp_timeframe"),
    )
    op.create_index("ix_price_data_asset_id", "price_data", ["asset_id"], unique=False)
    op.create_index("ix_price_data_timestamp", "price_data", ["timestamp"], unique=False)
    op.create_index("ix_price_data_timeframe", "price_data", ["timeframe"], unique=False)
    op.create_index("ix_price_data_source", "price_data", ["source"], unique=False)


def _create_sentiment_records_table() -> None:
    """Create raw sentiment records table."""
    op.create_table(
        "sentiment_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("source", sentiment_source_enum, nullable=False),
        sa.Column("text_snippet", sa.String(length=500), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("sentiment_label", sentiment_label_enum, nullable=False),
        sa.Column("model_used", sentiment_model_enum, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("author", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("sentiment_score >= -1.0 AND sentiment_score <= 1.0", name="ck_sentiment_score_range"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_sentiment_confidence_range"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_sentiment_records_asset_id", "sentiment_records", ["asset_id"], unique=False)
    op.create_index("ix_sentiment_records_source", "sentiment_records", ["source"], unique=False)
    op.create_index("ix_sentiment_records_sentiment_label", "sentiment_records", ["sentiment_label"], unique=False)
    op.create_index("ix_sentiment_records_model_used", "sentiment_records", ["model_used"], unique=False)
    op.create_index("ix_sentiment_records_created_at", "sentiment_records", ["created_at"], unique=False)


def _create_aggregated_sentiments_table() -> None:
    """Create aggregated sentiment metrics table."""
    op.create_table(
        "aggregated_sentiments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe", aggregation_timeframe_enum, nullable=False),
        sa.Column("avg_score", sa.Float(), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("neutral_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_mentions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", aggregation_source_enum, nullable=False),
        sa.Column("weighted_score", sa.Float(), nullable=False),
        sa.CheckConstraint("avg_score >= -1.0 AND avg_score <= 1.0", name="ck_agg_avg_score_range"),
        sa.CheckConstraint("weighted_score >= -1.0 AND weighted_score <= 1.0", name="ck_agg_weighted_score_range"),
        sa.CheckConstraint("positive_count >= 0", name="ck_agg_positive_count_nonnegative"),
        sa.CheckConstraint("negative_count >= 0", name="ck_agg_negative_count_nonnegative"),
        sa.CheckConstraint("neutral_count >= 0", name="ck_agg_neutral_count_nonnegative"),
        sa.CheckConstraint("total_mentions >= 0", name="ck_agg_total_mentions_nonnegative"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("asset_id", "period_start", "timeframe", "source", name="uq_aggregated_sentiment_window"),
    )
    op.create_index("ix_aggregated_sentiments_asset_id", "aggregated_sentiments", ["asset_id"], unique=False)
    op.create_index("ix_aggregated_sentiments_period_start", "aggregated_sentiments", ["period_start"], unique=False)
    op.create_index("ix_aggregated_sentiments_timeframe", "aggregated_sentiments", ["timeframe"], unique=False)
    op.create_index("ix_aggregated_sentiments_source", "aggregated_sentiments", ["source"], unique=False)


def _create_trading_signals_table() -> None:
    """Create generated signals table with audit metadata."""
    op.create_table(
        "trading_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("signal_type", signal_type_enum, nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("composite_score", sa.Float(), nullable=False),
        sa.Column("price_at_signal", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("sentiment_component", sa.Float(), nullable=False),
        sa.Column("technical_component", sa.Float(), nullable=False),
        sa.Column("volume_component", sa.Float(), nullable=False),
        sa.Column("momentum_component", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.String(length=100), nullable=True),
        sa.Column("strategy_id", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("strength >= 0.0 AND strength <= 100.0", name="ck_signal_strength_range"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_trading_signals_asset_id", "trading_signals", ["asset_id"], unique=False)
    op.create_index("ix_trading_signals_signal_type", "trading_signals", ["signal_type"], unique=False)
    op.create_index("ix_trading_signals_is_active", "trading_signals", ["is_active"], unique=False)
    op.create_index("ix_trading_signals_created_at", "trading_signals", ["created_at"], unique=False)
    op.create_index("ix_trading_signals_expires_at", "trading_signals", ["expires_at"], unique=False)
    op.create_index("ix_trading_signals_execution_id", "trading_signals", ["execution_id"], unique=False)
    op.create_index("ix_trading_signals_strategy_id", "trading_signals", ["strategy_id"], unique=False)


def _create_alerts_table() -> None:
    """Create configurable alerts table."""
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("alert_type", alert_type_enum, nullable=False),
        sa.Column("condition_json", sa.JSON(), nullable=False),
        sa.Column("delivery_method", delivery_method_enum, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_triggered", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"], unique=False)
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"], unique=False)
    op.create_index("ix_alerts_delivery_method", "alerts", ["delivery_method"], unique=False)
    op.create_index("ix_alerts_is_enabled", "alerts", ["is_enabled"], unique=False)
    op.create_index("ix_alerts_last_triggered", "alerts", ["last_triggered"], unique=False)
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"], unique=False)


def _create_alert_history_table() -> None:
    """Create alert delivery history table."""
    op.create_table(
        "alert_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signal_id"], ["trading_signals.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_alert_history_alert_id", "alert_history", ["alert_id"], unique=False)
    op.create_index("ix_alert_history_signal_id", "alert_history", ["signal_id"], unique=False)
    op.create_index("ix_alert_history_delivered", "alert_history", ["delivered"], unique=False)
    op.create_index("ix_alert_history_created_at", "alert_history", ["created_at"], unique=False)


def upgrade() -> None:
    """Apply initial database schema."""
    _create_assets_table()
    _create_price_data_table()
    _create_sentiment_records_table()
    _create_aggregated_sentiments_table()
    _create_trading_signals_table()
    _create_alerts_table()
    _create_alert_history_table()


def downgrade() -> None:
    """Revert initial database schema."""
    op.drop_table("alert_history")
    op.drop_table("alerts")
    op.drop_table("trading_signals")
    op.drop_table("aggregated_sentiments")
    op.drop_table("sentiment_records")
    op.drop_table("price_data")
    op.drop_table("assets")
