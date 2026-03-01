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
