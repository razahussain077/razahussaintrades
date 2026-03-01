import type {
  CoinData,
  Signal,
  MarketOverview,
  KillZoneData,
  PortfolioSettings,
  RiskCalculation,
  Candle,
  FundingRateData,
  MLStats,
  BacktestResult,
  EconomicEvent,
  SignalStats,
} from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'

export const WS_PRICES_URL = `${WS_BASE}/ws/prices`
export const WS_SIGNALS_URL = `${WS_BASE}/ws/signals`
export const WS_MARKET_URL = `${WS_BASE}/ws/market`

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export async function fetchCoins(): Promise<CoinData[]> {
  const res = await apiFetch<{ coins: CoinData[]; count: number } | CoinData[]>('/api/coins')
  if (Array.isArray(res)) return res
  return res.coins ?? []
}

export async function fetchSignals(): Promise<Signal[]> {
  const res = await apiFetch<{ signals: Signal[]; count: number } | Signal[]>('/api/signals')
  if (Array.isArray(res)) return res
  return res.signals ?? []
}

export async function fetchMarketOverview(): Promise<MarketOverview> {
  return apiFetch<MarketOverview>('/api/market/overview')
}

export async function fetchKillZones(): Promise<KillZoneData> {
  return apiFetch<KillZoneData>('/api/killzones')
}

export async function fetchCoinDetail(symbol: string): Promise<CoinData> {
  return apiFetch<CoinData>(`/api/coins/${encodeURIComponent(symbol)}`)
}

export async function fetchCandles(symbol: string, timeframe: string): Promise<Candle[]> {
  return apiFetch<Candle[]>(
    `/api/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`
  )
}

export async function fetchCorrelationMatrix(): Promise<Record<string, number>> {
  return apiFetch<Record<string, number>>('/api/correlation')
}

export async function savePortfolioSettings(settings: PortfolioSettings): Promise<void> {
  await apiFetch<void>('/api/portfolio/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  })
}

export async function getPortfolioSettings(): Promise<PortfolioSettings> {
  return apiFetch<PortfolioSettings>('/api/portfolio/settings')
}

export interface RiskParams {
  entry_price: number
  stop_loss: number
  leverage: number
  budget: number
  risk_tolerance: number
}

export async function calculateRisk(params: RiskParams): Promise<RiskCalculation> {
  return apiFetch<RiskCalculation>('/api/risk/calculate', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export async function takeSignal(signalId: string): Promise<void> {
  await apiFetch<void>(`/api/signals/${encodeURIComponent(signalId)}/take`, {
    method: 'POST',
  })
}

// ─── Phase 3 API Functions ───────────────────────────────────────────────────

export async function fetchFundingRate(symbol: string): Promise<FundingRateData> {
  return apiFetch<FundingRateData>(`/api/funding-rate/${encodeURIComponent(symbol)}`)
}

export async function fetchMLStats(): Promise<MLStats> {
  return apiFetch<MLStats>('/api/ml/stats')
}

export async function fetchActiveSignalsLive(): Promise<{ signals: Signal[]; count: number }> {
  return apiFetch<{ signals: Signal[]; count: number }>('/api/signals/active')
}

export async function runBacktest(params: {
  symbol: string
  timeframe: string
  days: number
}): Promise<BacktestResult> {
  return apiFetch<BacktestResult>('/api/backtest/run', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export async function fetchUpcomingEvents(daysAhead: number = 7): Promise<{
  events: EconomicEvent[]
  next_event: EconomicEvent | null
  active_warnings: string[]
  has_active_warnings: boolean
}> {
  return apiFetch(`/api/events/upcoming?days_ahead=${daysAhead}`)
}

export async function fetchSignalHistory(params: {
  limit?: number
  coin?: string
  signal_type?: string
}): Promise<{ signals: Signal[]; count: number; page: number }> {
  const query = new URLSearchParams()
  if (params.limit) query.set('limit', String(params.limit))
  if (params.coin) query.set('coin', params.coin)
  if (params.signal_type) query.set('signal_type', params.signal_type)
  const qs = query.toString()
  return apiFetch(`/api/signals/history${qs ? `?${qs}` : ''}`)
}

export async function fetchSignalStats(): Promise<SignalStats> {
  return apiFetch<SignalStats>('/api/signals/stats')
}

export interface PositionSizeParams {
  balance: number
  risk_pct: number
  entry_price: number
  stop_loss_price: number
  confidence_score?: number
  signal_type?: 'LONG' | 'SHORT'
}

export async function fetchPositionSize(params: PositionSizeParams): Promise<Record<string, unknown>> {
  const query = new URLSearchParams({
    balance: String(params.balance),
    risk_pct: String(params.risk_pct),
    entry_price: String(params.entry_price),
    stop_loss_price: String(params.stop_loss_price),
    confidence_score: String(params.confidence_score ?? 70),
    signal_type: params.signal_type ?? 'LONG',
  })
  return apiFetch(`/api/risk/position-size?${query.toString()}`)
}

export async function fetchPortfolioExposure(): Promise<Record<string, unknown>> {
  return apiFetch('/api/risk/portfolio')
}

export interface RiskSettings {
  balance?: number
  risk_pct?: number
  max_trades?: number
}

export async function fetchRiskSettings(): Promise<RiskSettings> {
  return apiFetch<RiskSettings>('/api/risk/settings')
}

export async function updateRiskSettings(settings: RiskSettings): Promise<{ message: string; settings: RiskSettings }> {
  return apiFetch('/api/risk/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  })
}

export async function fetchMarketRegime(symbol: string): Promise<Record<string, unknown>> {
  return apiFetch(`/api/regime/${encodeURIComponent(symbol)}`)
}

export async function fetchLiquidationHeatmap(symbol: string): Promise<Record<string, unknown>> {
  return apiFetch(`/api/liquidation-heatmap/${encodeURIComponent(symbol)}`)
}
