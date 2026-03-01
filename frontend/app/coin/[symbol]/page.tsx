'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import dynamic from 'next/dynamic'
import { fetchCoinDetail, fetchSignals } from '@/lib/api'
import type { CoinData, Signal } from '@/lib/types'
import {
  formatPrice,
  formatPercentage,
  formatVolume,
  formatMarketCap,
} from '@/lib/utils'
import { SignalCard } from '@/components/dashboard/SignalCard'
import { ArrowLeft, TrendingUp, TrendingDown } from 'lucide-react'
import Link from 'next/link'

const TradingChart = dynamic(
  () => import('@/components/charts/TradingChart').then((m) => m.TradingChart),
  { ssr: false, loading: () => <div className="h-96 bg-gray-100 rounded-xl animate-pulse" /> }
)

export default function CoinDetailPage() {
  const params = useParams()
  const symbol = typeof params.symbol === 'string' ? decodeURIComponent(params.symbol) : ''
  const [coin, setCoin] = useState<CoinData | null>(null)
  const [signal, setSignal] = useState<Signal | null>(null)
  const [timeframe, setTimeframe] = useState('1H')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true)
    Promise.all([fetchCoinDetail(symbol), fetchSignals()])
      .then(([coinData, signals]) => {
        setCoin(coinData)
        const sig = signals.find(
          (s) => s.coin.toUpperCase() === symbol.toUpperCase() && s.is_active
        )
        setSignal(sig ?? null)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [symbol])

  const timeframes = ['1m', '5m', '15m', '30m', '1H', '4H', '1D', '1W']

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="h-96 bg-gray-100 rounded-xl animate-pulse" />
      </div>
    )
  }

  if (!coin) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <h2 className="text-xl font-semibold text-gray-700">Coin not found</h2>
        <Link href="/" className="mt-4 text-blue-600 hover:underline flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </Link>
      </div>
    )
  }

  const changePositive = coin.price_change_pct_24h >= 0

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link href="/" className="text-blue-600 hover:underline flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> Dashboard
        </Link>
        <span className="text-gray-400">/</span>
        <span className="text-gray-700 font-medium">{coin.symbol.toUpperCase()}</span>
      </div>

      {/* Coin header */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            {coin.image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={coin.image} alt={coin.name} className="w-12 h-12 rounded-full" />
            )}
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{coin.name}</h1>
              <span className="text-sm text-gray-500 font-medium">{coin.symbol.toUpperCase()}</span>
            </div>
          </div>

          <div className="flex items-end gap-3">
            <span className="text-3xl font-bold text-gray-900">{formatPrice(coin.price)}</span>
            <span
              className={`flex items-center gap-1 text-sm font-semibold px-2.5 py-1 rounded-full ${
                changePositive
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {changePositive ? (
                <TrendingUp className="w-3.5 h-3.5" />
              ) : (
                <TrendingDown className="w-3.5 h-3.5" />
              )}
              {formatPercentage(coin.price_change_pct_24h)}
            </span>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-5 border-t border-gray-100">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">24h Volume</p>
            <p className="text-sm font-semibold text-gray-900 mt-0.5">
              {formatVolume(coin.volume_24h)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Market Cap</p>
            <p className="text-sm font-semibold text-gray-900 mt-0.5">
              {formatMarketCap(coin.market_cap)}
            </p>
          </div>
          {coin.funding_rate !== undefined && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide">Funding Rate</p>
              <p
                className={`text-sm font-semibold mt-0.5 ${
                  coin.funding_rate >= 0 ? 'text-emerald-600' : 'text-red-600'
                }`}
              >
                {(coin.funding_rate * 100).toFixed(4)}%
              </p>
            </div>
          )}
          {coin.open_interest !== undefined && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide">Open Interest</p>
              <p className="text-sm font-semibold text-gray-900 mt-0.5">
                {formatVolume(coin.open_interest)}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Chart + timeframe */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-900">Price Chart</h2>
          <div className="flex gap-1">
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  timeframe === tf
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
        <TradingChart symbol={symbol} timeframe={timeframe} signal={signal ?? undefined} />
      </div>

      {/* Active signal for this coin */}
      {signal && (
        <div>
          <h2 className="text-lg font-bold text-gray-900 mb-3">Active Signal</h2>
          <div className="max-w-lg">
            <SignalCard signal={signal} />
          </div>
        </div>
      )}
    </div>
  )
}
