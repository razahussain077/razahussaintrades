'use client'

import { useEffect, useState } from 'react'
import { getPktTime } from '@/lib/utils'
import { useLivePrices } from '@/hooks/useLivePrices'
import { useWebSocket } from '@/hooks/useWebSocket'
import { WS_MARKET_URL } from '@/lib/api'
import { formatPrice, formatMarketCap } from '@/lib/utils'
import { Wifi, WifiOff } from 'lucide-react'
import { KillZoneBar } from './KillZoneBar'

export function Header() {
  const [pktTime, setPktTime] = useState('')
  const { prices, isConnected: pricesConnected } = useLivePrices()
  const { data: marketData, isConnected: marketConnected } = useWebSocket(WS_MARKET_URL)

  const isConnected = pricesConnected || marketConnected

  const btcPrice = prices['BTC'] ?? prices['BTCUSDT'] ?? null
  // Backend WS sends { type: "market_overview", data: { total_market_cap, ... } }
  const marketOverview =
    marketData && typeof marketData === 'object' && !Array.isArray(marketData)
      ? (() => {
          const msg = marketData as Record<string, unknown>
          const d = msg.data
          return d && typeof d === 'object' && !Array.isArray(d)
            ? (d as Record<string, unknown>)
            : msg
        })()
      : null

  useEffect(() => {
    setPktTime(getPktTime())
    const interval = setInterval(() => setPktTime(getPktTime()), 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="fixed top-0 left-0 right-0 md:left-60 h-16 bg-white border-b border-gray-200 z-20 flex flex-col">
      {/* Kill zone bar */}
      <KillZoneBar />

      {/* Main header row */}
      <div className="flex items-center justify-between px-4 md:px-6 flex-1">
        {/* Left: PKT time */}
        <div className="flex items-center gap-1.5 text-sm text-gray-600">
          <span className="hidden sm:inline text-gray-400 text-xs">PKT</span>
          <span className="font-mono font-medium">{pktTime}</span>
        </div>

        {/* Center: mini market stats */}
        <div className="flex items-center gap-4 text-sm">
          {btcPrice !== null && (
            <div className="hidden sm:flex items-center gap-1.5">
              <span className="text-gray-500 text-xs font-medium">BTC</span>
              <span className="font-semibold text-gray-900">{formatPrice(btcPrice)}</span>
            </div>
          )}
          {marketOverview && typeof marketOverview.total_market_cap === 'number' && (
            <div className="hidden md:flex items-center gap-1.5">
              <span className="text-gray-500 text-xs font-medium">Market Cap</span>
              <span className="font-semibold text-gray-900">
                {formatMarketCap(marketOverview.total_market_cap as number)}
              </span>
            </div>
          )}
          {marketOverview && typeof marketOverview.btc_dominance === 'number' && (
            <div className="hidden lg:flex items-center gap-1.5">
              <span className="text-gray-500 text-xs font-medium">BTC Dom.</span>
              <span className="font-semibold text-gray-900">
                {(marketOverview.btc_dominance as number).toFixed(1)}%
              </span>
            </div>
          )}
        </div>

        {/* Right: connection status */}
        <div className="flex items-center gap-1.5">
          {isConnected ? (
            <>
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              <Wifi className="w-4 h-4 text-emerald-500 hidden sm:block" />
              <span className="text-xs text-emerald-600 font-medium hidden sm:block">Live</span>
            </>
          ) : (
            <>
              <div className="w-2 h-2 bg-gray-400 rounded-full" />
              <WifiOff className="w-4 h-4 text-gray-400 hidden sm:block" />
              <span className="text-xs text-gray-500 hidden sm:block">Offline</span>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
