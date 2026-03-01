'use client'

import { useEffect, useState } from 'react'
import { getPktTime } from '@/lib/utils'
import { useLivePrices } from '@/hooks/useLivePrices'
import { useWebSocket } from '@/hooks/useWebSocket'
import { WS_MARKET_URL } from '@/lib/api'
import { formatPrice, formatMarketCap } from '@/lib/utils'
import { Wifi, WifiOff, AlertTriangle, Calendar } from 'lucide-react'
import { KillZoneBar } from './KillZoneBar'
import { FundingRateBadge } from '@/components/phase3/FundingRateBadge'
import { fetchUpcomingEvents } from '@/lib/api'
import type { EconomicEvent } from '@/lib/types'

export function Header() {
  const [pktTime, setPktTime] = useState('')
  const { prices, isConnected: pricesConnected } = useLivePrices()
  const { data: marketData, isConnected: marketConnected } = useWebSocket(WS_MARKET_URL)
  const [nextEvent, setNextEvent] = useState<EconomicEvent | null>(null)
  const [hasEventWarning, setHasEventWarning] = useState(false)

  const isConnected = pricesConnected || marketConnected

  const btcPrice = prices['BTC'] ?? prices['BTCUSDT'] ?? null
  const marketOverview =
    marketData && typeof marketData === 'object' && !Array.isArray(marketData)
      ? (marketData as Record<string, unknown>)
      : null

  useEffect(() => {
    setPktTime(getPktTime())
    const interval = setInterval(() => setPktTime(getPktTime()), 1000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const loadEvents = async () => {
      try {
        const data = await fetchUpcomingEvents(7)
        setNextEvent(data.next_event)
        setHasEventWarning(data.has_active_warnings)
      } catch {
        // silently ignore
      }
    }
    loadEvents()
    const interval = setInterval(loadEvents, 60000)
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="fixed top-0 left-0 right-0 md:left-60 h-16 bg-white border-b border-gray-200 z-20 flex flex-col">
      {/* Kill zone bar */}
      <KillZoneBar />

      {/* Main header row */}
      <div className="flex items-center justify-between px-4 md:px-6 flex-1 gap-2 overflow-hidden">
        {/* Left: PKT time */}
        <div className="flex items-center gap-1.5 text-sm text-gray-600 flex-shrink-0">
          <span className="hidden sm:inline text-gray-400 text-xs">PKT</span>
          <span className="font-mono font-medium">{pktTime}</span>
        </div>

        {/* Center: mini market stats */}
        <div className="flex items-center gap-3 text-sm overflow-hidden flex-1 justify-center">
          {btcPrice !== null && (
            <div className="hidden sm:flex items-center gap-1.5">
              <span className="text-gray-500 text-xs font-medium">BTC</span>
              <span className="font-semibold text-gray-900">{formatPrice(btcPrice)}</span>
            </div>
          )}
          {marketOverview && typeof marketOverview.btc_dominance === 'number' && (
            <div className="hidden md:flex items-center gap-1.5">
              <span className="text-gray-500 text-xs font-medium">Dom</span>
              <span className="font-semibold text-gray-900">
                {(marketOverview.btc_dominance as number).toFixed(1)}%
              </span>
            </div>
          )}
          {/* Funding Rate Badge */}
          <div className="hidden lg:block">
            <FundingRateBadge symbol="BTCUSDT" compact={false} />
          </div>
          {/* Next event countdown */}
          {nextEvent && (
            <div className={`hidden xl:flex items-center gap-1.5 px-2 py-0.5 rounded text-xs ${hasEventWarning ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-600'}`}>
              {hasEventWarning && <AlertTriangle className="w-3 h-3" />}
              <Calendar className="w-3 h-3" />
              <span>
                {nextEvent.name.split(' ').slice(0, 2).join(' ')} in{' '}
                {nextEvent.minutes_until > 60
                  ? `${Math.floor(nextEvent.minutes_until / 60)}h`
                  : `${nextEvent.minutes_until}m`}
              </span>
            </div>
          )}
        </div>

        {/* Right: connection status */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
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
