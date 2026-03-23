export interface AssetResponse {
  id: number;
  symbol: string;
  name: string;
  asset_type: "stock" | "crypto";
  exchange: string | null;
  watch_status: "none" | "watchlist" | "holding";
  watch_notes: string | null;
  is_tool_suggested: boolean;
  is_active: boolean;
  latest_close: string | number | null;
  latest_timestamp: string | null;
  latest_source: string | null;
}

export interface PricePointResponse {
  symbol: string;
  timeframe: string;
  source: string;
  timestamp: string;
  open: string | number;
  high: string | number;
  low: string | number;
  close: string | number;
  volume: string | number;
}

export interface SentimentOverviewResponse {
  symbol: string;
  score: number | null;
  label: "positive" | "neutral" | "negative";
  mentions_1h: number;
  updated_at: string | null;
}

export interface SentimentHistoryResponse {
  period_start: string;
  period_end: string;
  score: number;
  avg_score: number;
  total_mentions: number;
}

export interface SignalRecommendationResponse {
  symbol: string;
  asset_type: "stock" | "crypto";
  watch_status: "none" | "watchlist" | "holding";
  signal_type: "buy" | "sell" | "hold";
  strength: number;
  composite_score: number;
  reasoning: string;
  created_at: string;
  expires_at: string | null;
}

export interface SignalResponse {
  symbol: string;
  signal_type: "buy" | "sell" | "hold";
  strength: number;
  composite_score: number;
  price_at_signal: string | number;
  sentiment_component: number;
  technical_component: number;
  volume_component: number;
  momentum_component: number;
  reasoning: string;
  execution_id: string | null;
  strategy_id: string | null;
  is_active: boolean;
  created_at: string;
  expires_at: string | null;
}

export interface SignalLeaderboardResponse {
  top_buy: SignalResponse[];
  top_sell: SignalResponse[];
}

export interface SignalPipelineStatusResponse {
  assets_total: number;
  price_points_1m: number;
  price_points_h1: number;
  scored_sentiment_records: number;
  aggregated_1h: number;
  active_signals: number;
  blockers: string[];
}

export interface SocialStatsResponse {
  symbol: string;
  total_mentions: number;
  by_source: Record<string, number>;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  avg_sentiment_score: number | null;
}

export interface MarketSummaryResponse {
  source: "reddit" | "stocktwits" | "news" | "twitter" | "perplexity";
  text_snippet: string;
  created_at: string;
  source_url: string | null;
  asset_symbol: string | null;
  author: string | null;
}

export interface MarketSummaryAttempt {
  scope: string;
  asset_symbol: string | null;
  model: string | null;
  status: string;
  status_code: number | null;
  message: string;
  response_excerpt: string | null;
  provider: string | null;
  endpoint: string | null;
}

export interface MarketSummaryRefreshResponse {
  status: "success" | "partial" | "error";
  saved_count: number;
  provider: string;
  base_url: string;
  chat_completions_path: string;
  primary_model: string;
  validation_model: string | null;
  used_models: string[];
  attempts: MarketSummaryAttempt[];
  errors: MarketSummaryAttempt[];
  summary: MarketSummaryResponse | null;
}

export interface DefaultAssetSeedResponse {
  seeded_count: number;
  existing_count: number;
  total_defaults: number;
  active_assets_total: number;
  symbols_added: string[];
}

export interface SocialFeedItemResponse {
  id: number;
  source: "reddit" | "stocktwits" | "news" | "twitter" | "perplexity";
  text_snippet: string;
  sentiment_score: number | null;
  sentiment_label: "positive" | "neutral" | "negative" | null;
  model_used: string | null;
  confidence: number | null;
  source_url: string | null;
  author: string | null;
  created_at: string;
}

export interface SentimentSnapshotResponse {
  symbol: string;
  score: number | null;
  label: "positive" | "neutral" | "negative";
  mentions_1h: number;
  mentions_1d: number;
  updated_at: string | null;
}

export interface PriceUpdateMessage {
  type: "price_update";
  symbol: string;
  source: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface AlertTriggeredMessage {
  type: "alert_triggered";
  channel: "alerts";
  alert_id: number;
  alert_type: "signal_threshold" | "price_target" | "sentiment_shift" | "custom";
  delivery_method: "websocket" | "email" | "telegram";
  asset_id: number | null;
  symbol: string | null;
  signal_id: number | null;
  message: string;
  delivered: boolean;
  created_at: string;
}

export type AlertType = "signal_threshold" | "price_target" | "sentiment_shift" | "custom";
export type DeliveryMethod = "websocket" | "email" | "telegram";

export interface AlertResponse {
  id: number;
  asset_id: number | null;
  asset_symbol?: string | null;
  alert_type: AlertType;
  condition_json: Record<string, unknown>;
  delivery_method: DeliveryMethod;
  is_enabled: boolean;
  last_triggered: string | null;
  created_at: string;
}

export interface AlertHistoryResponse {
  id: number;
  alert_id: number;
  signal_id: number | null;
  message: string;
  delivered: boolean;
  created_at: string;
  alert_type?: AlertType;
  asset_symbol?: string | null;
}

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

export interface SentimentPanelItem {
  symbol: string;
  score: number;
  mentions: number;
}

export interface AssetTableRow {
  symbol: string;
  name: string;
  assetType: "stock" | "crypto";
  exchange: string | null;
  watchStatus: "none" | "watchlist" | "holding";
  isToolSuggested: boolean;
  price: number | null;
  change24h: number | null;
  sentimentScore: number;
  mentions: number;
  signal: "buy" | "sell" | "hold";
}

export type TradeSide = "buy" | "sell";
export type TradeStatus =
  | "pending_confirmation"
  | "submitted"
  | "filled"
  | "canceled"
  | "rejected"
  | "failed";

export interface TradingAccountResponse {
  broker: "multi" | "alpaca_paper" | "kraken" | string;
  is_paper: boolean;
  is_live?: boolean;
  connected: boolean;
  equity: number;
  cash: number;
  buying_power: number;
  status: string;
  live_stop_reason?: string | null;
}

export interface TradingPositionResponse {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  side: string;
}

export interface TradingOrderResponse {
  id: number;
  asset_id: number | null;
  symbol: string | null;
  broker: string;
  order_id: string | null;
  side: TradeSide;
  quantity: string | number;
  price: string | number;
  total_value: string | number;
  status: TradeStatus;
  signal_id: number | null;
  is_paper: boolean;
  created_at: string;
  filled_at: string | null;
  notes: string | null;
}

export interface PortfolioSnapshotResponse {
  id: number;
  broker: string;
  total_value: number;
  cash: number;
  positions_value: number;
  daily_pnl: number;
  total_pnl: number;
  snapshot_at: string;
}

export interface TradingPerformanceResponse {
  total_trades: number;
  filled_trades: number;
  failed_trades: number;
  fill_rate: number;
  latest_total_value: number;
  daily_pnl: number;
  total_pnl: number;
  latest_snapshot_at: string | null;
}

export interface TradingSettingsResponse {
  mode: "manual" | "semi_auto" | "auto";
  is_live: boolean;
  max_position_size_usd: number;
  max_positions: number;
  min_signal_strength: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  double_confirm_threshold_eur: number;
  daily_loss_limit_eur: number;
  max_trades_per_day: number;
  live_stop_reason?: string | null;
}

export interface TradingStatusResponse {
  alpaca_configured: boolean;
  kraken_configured: boolean;
  is_live: boolean;
  live_stop_reason: string | null;
  mode: "manual" | "semi_auto" | "auto";
}
