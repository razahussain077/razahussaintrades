'use client'

import { useEffect, useState } from 'react'
import { fetchFundingRate } from '@/lib/api'
import type { FundingRateData } from '@/lib/types'

interface FundingRateBadgeProps {
  symbol?: string
  compact?: boolean
}

export function FundingRateBadge({ symbol = 'BTCUSDT', compact = false }: FundingRateBadgeProps) {
  const [data, setData] = useState<FundingRateData | null>(null)

  useEffect(() => {
    fetchFundingRate(symbol).then(setData).catch(() => null)
    const interval = setInterval(() => {
      fetchFundingRate(symbol).then(setData).catch(() => null)
    }, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [symbol])

  if (!data) return null

  const rate = data.current_rate_pct
  const sentiment = data.interpretation?.sentiment ?? 'neutral'

  const bgColor =
    sentiment === 'bullish'
      ? 'bg-emerald-100 text-emerald-700'
      : sentiment === 'bearish'
      ? 'bg-red-100 text-red-700'
      : 'bg-gray-100 text-gray-600'

  if (compact) {
    return (
      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono ${bgColor}`}>
        {rate >= 0 ? '+' : ''}{rate.toFixed(4)}%
      </span>
    )
  }

  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs ${bgColor}`}>
      <span className="font-medium">Funding</span>
      <span className="font-bold font-mono">{rate >= 0 ? '+' : ''}{rate.toFixed(4)}%</span>
      {sentiment === 'bullish' && <span title="Shorts paying — bullish">↑</span>}
      {sentiment === 'bearish' && <span title="Longs paying — bearish">↓</span>}
    </div>
  )
}
