export interface CoinData {
  symbol: string
  name: string
  image?: string
  price: number
  price_change_24h: number
  price_change_pct_24h: number
  volume_24h: number
  market_cap: number
  market_cap_category: string
  signal_status: 'LONG' | 'SHORT' | 'WAIT'
  confidence_score: number
  volatility_score: number
  funding_rate?: number
  open_interest?: number
}

export interface EntryLevel {
  level_name: string
  price: number
  allocation_pct: number
  description: string
}

export interface Signal {
  id: string
  coin: string
  exchange: string
  signal_type: 'LONG' | 'SHORT'
  timeframe: string
  entry_low: number
  entry_high: number
  stop_loss: number
  stop_loss_pct: number
  take_profit_1: number
  take_profit_1_pct: number
  take_profit_2: number
  take_profit_2_pct: number
  take_profit_3: number
  take_profit_3_pct: number
  recommended_leverage: number
  liquidation_price: number
  risk_reward: number
  confidence_score: number
  setup_type: string
  reasoning: string[]
  invalidation: string
  kill_zone: string
  created_at: string
  is_active: boolean
  taken?: boolean
  // Phase 3 additions
  result?: string
  pnl_pct?: number
  current_price?: number
  unrealized_pnl_pct?: number
  progress_to_tp1?: number
  entries?: EntryLevel[]
  weighted_average_entry?: number
  ml_confidence?: number
  regime?: string
  regime_emoji?: string
  funding_rate?: number
  funding_direction?: string
  liq_magnet_price?: number
  liq_magnet_direction?: string
  event_warning?: string
}

export interface MarketOverview {
  total_market_cap: number
  total_volume_24h: number
  btc_dominance: number
  eth_dominance: number
  market_change_24h: number
  fear_greed_index: number
  fear_greed_label: string
  active_coins: number
}

export interface KillZone {
  name: string
  is_active: boolean
  start_pkt: string
  end_pkt: string
  next_start_pkt?: string
  minutes_until_next?: number
}

export interface KillZoneData {
  current_time_pkt: string
  active_session: string | null
  zones: KillZone[]
}

export interface PortfolioSettings {
  budget: number
  risk_tolerance: number
  preferred_timeframes: string[]
  preferred_exchanges: string[]
  notification_enabled: boolean
}

export interface RiskCalculation {
  recommended_leverage: number
  max_safe_leverage: number
  liquidation_price: number
  position_size: number
  risk_amount: number
  is_safe: boolean
  warnings: string[]
}

export interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OrderBlock {
  type: 'bullish' | 'bearish'
  high: number
  low: number
  time: number
  strength: number
}

export interface FairValueGap {
  type: 'bullish' | 'bearish'
  top: number
  bottom: number
  time: number
  filled: boolean
}

export interface LiquidityLevel {
  price: number
  type: 'equal_high' | 'equal_low'
  touches: number
  time: number
}

// Phase 3 Types

export interface LiquidationZone {
  price: number
  long_liquidation_value: number
  short_liquidation_value: number
  total_liquidation_value: number
  density: 'low' | 'medium' | 'high'
  leverages: number[]
}

export interface LiquidationMagnet {
  price: number
  direction: 'above' | 'below'
  distance_pct: number
  liquidation_value: number
  density: string
}

export interface LiquidationHeatmap {
  symbol: string
  current_price: number
  open_interest: number
  heatmap_zones: LiquidationZone[]
  liquidation_magnet: LiquidationMagnet | null
  real_events_count: number
}

export interface FundingRateData {
  symbol: string
  current_rate: number
  current_rate_pct: number
  mark_price: number
  interpretation: {
    direction: string
    description: string
    sentiment: 'bullish' | 'bearish' | 'neutral'
    long_confidence_boost: number
    short_confidence_boost: number
  }
  reversal_signal: { detected: boolean; type?: string; description?: string }
  history: Array<{ rate: number; timestamp: string }>
}

export interface MarketRegime {
  regime: 'trending' | 'ranging' | 'volatile' | 'squeeze'
  label: string
  emoji: string
  adx: number
  bb_width: number
  atr_ratio: number
  description: string
}

export interface EconomicEvent {
  name: string
  impact: 'HIGH' | 'MEDIUM' | 'LOW'
  currency: string
  datetime_utc: string
  datetime_pkt: string
  minutes_until: number
  is_active_warning: boolean
  warning_message: string | null
}

export interface PortfolioExposure {
  total_open_signals: number
  long_count: number
  short_count: number
  long_short_ratio: number
  total_risk_usd: number
  daily_pnl: number
  daily_pnl_pct: number
  daily_loss_warning: boolean
  daily_loss_message: string | null
  risk_level: 'green' | 'yellow' | 'red'
  risk_label: string
  max_trades: number
  over_max_warning: boolean
}

export interface PositionSizeResult {
  position_size: number
  position_value: number
  risk_amount: number
  risk_pct: number
  suggested_leverage: number
  tier: string
  liquidation_price: number
  entry_price: number
  stop_loss_price: number
  sl_distance?: number
}

export interface MLStats {
  accuracy: number
  last_trained: string | null
  total_samples: number
  feature_importance: Record<string, number>
  active: boolean
  buffered_samples: number
  min_samples_needed: number
  samples_until_active: number
}

export interface BacktestStats {
  total_signals: number
  win_count: number
  loss_count: number
  win_rate: number
  avg_rr: number
  profit_factor: number
  max_drawdown_pct: number
  best_trade_pct: number
  worst_trade_pct: number
  sharpe_ratio: number
  total_pnl_pct: number
  equity_curve: number[]
}

export interface BacktestResult {
  symbol: string
  timeframe: string
  days: number
  run_at: string
  stats: BacktestStats
  trades: Array<{
    symbol: string
    signal_type: string
    entry_price: number
    exit_price?: number
    result: string
    pnl_pct: number
    rr: number
    bars_held: number
  }>
}

export interface SignalStats {
  WIN: number
  LOSS: number
  BE: number
  total_trades: number
  win_rate: number
  total_pnl: number
}

