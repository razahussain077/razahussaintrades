import type {
  CoinData,
  Signal,
  MarketOverview,
  KillZoneData,
  PortfolioSettings,
  RiskCalculation,
  Candle,
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
  return apiFetch<CoinData[]>('/api/coins')
}

export async function fetchSignals(): Promise<Signal[]> {
  return apiFetch<Signal[]>('/api/signals')
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
