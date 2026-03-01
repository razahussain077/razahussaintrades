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

export interface EntryZone {
  price: number
  level_name: string
  allocation_pct: number
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
  // Phase 3 fields
  regime?: string
  regime_emoji?: string
  ml_confidence?: number
  funding_boost?: number
  funding_direction?: string
  liq_magnet_price?: number
  liq_magnet_direction?: string
  entries?: EntryZone[]
  weighted_average_entry?: number
  event_warning?: string
  result?: string
  pnl_pct?: number
  unrealized_pnl_pct?: number
  progress_to_tp1?: number
  current_price?: number
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

export interface FundingRateData {
  symbol: string
  current_rate: number
  current_rate_pct: number
  interpretation?: {
    sentiment: 'bullish' | 'bearish' | 'neutral'
    description: string
  }
  history?: { time: number; rate: number }[]
}

export interface MLStats {
  active: boolean
  accuracy: number
  total_samples: number
  last_trained?: string
  feature_importance: Record<string, number>
  buffered_samples: number
  min_samples_needed: number
  samples_until_active: number
}

export interface BacktestResult {
  symbol: string
  timeframe: string
  days: number
  total_trades: number
  win_rate: number
  profit_factor: number
  sharpe_ratio: number
  total_return_pct: number
  max_drawdown_pct: number
  equity_curve: { time: number; equity: number }[]
  trades: {
    id: string
    signal_type: string
    entry: number
    exit: number
    result: string
    pnl_pct: number
  }[]
}

export interface EconomicEvent {
  id: string
  title: string
  datetime: string
  impact: 'LOW' | 'MEDIUM' | 'HIGH'
  currency: string
  description?: string
  forecast?: string
  previous?: string
  minutes_until?: number
  is_warning_active?: boolean
}

export interface SignalStats {
  total_signals: number
  total_wins: number
  total_losses: number
  win_rate: number
  total_pnl_pct: number
  avg_pnl_pct: number
  best_trade_pct: number
  worst_trade_pct: number
  profit_factor: number
  avg_confidence: number
  long_signals: number
  short_signals: number
}
