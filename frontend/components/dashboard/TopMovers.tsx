'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { fetchCoins } from '@/lib/api'
import type { CoinData } from '@/lib/types'
import { formatPrice, formatPercentage } from '@/lib/utils'
import { TrendingUp, TrendingDown } from 'lucide-react'

export function TopMovers() {
  const [coins, setCoins] = useState<CoinData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCoins()
      .then(setCoins)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const sorted = [...coins].sort((a, b) => b.price_change_pct_24h - a.price_change_pct_24h)
  const gainers = sorted.slice(0, 5)
  const losers = sorted.slice(-5).reverse()

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <div className="h-6 w-32 bg-gray-100 rounded animate-pulse" />
        {[...Array(10)].map((_, i) => (
          <div key={i} className="h-8 bg-gray-100 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100">
        <h2 className="text-base font-bold text-gray-900">Top Movers</h2>
        <p className="text-xs text-gray-500 mt-0.5">24h price change</p>
      </div>

      <div className="divide-y divide-gray-50">
        {/* Gainers */}
        <div className="p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingUp className="w-4 h-4 text-emerald-500" />
            <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wide">Top Gainers</span>
          </div>
          <div className="space-y-1">
            {gainers.map((coin) => (
              <MoverRow key={coin.symbol} coin={coin} />
            ))}
          </div>
        </div>

        {/* Losers */}
        <div className="p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingDown className="w-4 h-4 text-red-500" />
            <span className="text-xs font-semibold text-red-600 uppercase tracking-wide">Top Losers</span>
          </div>
          <div className="space-y-1">
            {losers.map((coin) => (
              <MoverRow key={coin.symbol} coin={coin} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function MoverRow({ coin }: { coin: CoinData }) {
  const positive = coin.price_change_pct_24h >= 0
  return (
    <Link
      href={`/coin/${encodeURIComponent(coin.symbol)}`}
      className="flex items-center justify-between py-1 px-2 rounded-lg hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-center gap-2 min-w-0">
        {coin.image && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={coin.image} alt={coin.name} className="w-5 h-5 rounded-full flex-shrink-0" />
        )}
        <span className="text-sm font-semibold text-gray-900 truncate">
          {coin.symbol.toUpperCase()}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-xs text-gray-500">{formatPrice(coin.price)}</span>
        <span
          className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            positive ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
          }`}
        >
          {formatPercentage(coin.price_change_pct_24h)}
        </span>
      </div>
    </Link>
  )
}
