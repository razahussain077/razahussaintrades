'use client'

import { useEffect, useState } from 'react'
import { fetchMarketOverview } from '@/lib/api'
import type { MarketOverview } from '@/lib/types'
import { formatMarketCap, formatVolume, formatPercentage } from '@/lib/utils'
import { DollarSign, TrendingUp, BarChart2, Activity } from 'lucide-react'

function getFearGreedColor(index: number): string {
  if (index >= 75) return 'text-emerald-600'
  if (index >= 55) return 'text-blue-600'
  if (index >= 45) return 'text-yellow-600'
  if (index >= 25) return 'text-orange-600'
  return 'text-red-600'
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  valueClass = '',
  iconBg = 'bg-blue-50',
  iconColor = 'text-blue-600',
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  sub?: string
  valueClass?: string
  iconBg?: string
  iconColor?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${iconBg}`}>
        <Icon className={`w-5 h-5 ${iconColor}`} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">{label}</p>
        <p className={`text-xl font-bold text-gray-900 mt-0.5 truncate ${valueClass}`}>{value}</p>
        {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export function MarketOverview() {
  const [data, setData] = useState<MarketOverview | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchMarketOverview()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  if (!data) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-white rounded-xl border border-gray-200 p-5 flex items-center justify-center">
            <span className="text-sm text-gray-400">Unavailable</span>
          </div>
        ))}
      </div>
    )
  }

  const changePositive = data.market_change_24h >= 0

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        icon={DollarSign}
        label="Total Market Cap"
        value={formatMarketCap(data.total_market_cap)}
        sub={
          `${formatPercentage(data.market_change_24h)} 24h`
        }
        iconBg="bg-blue-50"
        iconColor="text-blue-600"
        valueClass=""
      />
      <StatCard
        icon={TrendingUp}
        label="BTC Dominance"
        value={`${data.btc_dominance.toFixed(1)}%`}
        sub={`ETH: ${data.eth_dominance.toFixed(1)}%`}
        iconBg="bg-amber-50"
        iconColor="text-amber-600"
      />
      <StatCard
        icon={Activity}
        label="Fear & Greed"
        value={`${data.fear_greed_index} – ${data.fear_greed_label}`}
        sub="Market sentiment"
        iconBg="bg-purple-50"
        iconColor="text-purple-600"
        valueClass={getFearGreedColor(data.fear_greed_index)}
      />
      <StatCard
        icon={BarChart2}
        label="24h Volume"
        value={formatVolume(data.total_volume_24h)}
        sub={`${data.active_coins.toLocaleString()} active coins`}
        iconBg="bg-emerald-50"
        iconColor="text-emerald-600"
      />
    </div>
  )
}
