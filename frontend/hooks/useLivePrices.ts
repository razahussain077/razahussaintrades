'use client'

import { useEffect, useState } from 'react'
import { useWebSocket } from './useWebSocket'
import { WS_PRICES_URL } from '@/lib/api'

export function useLivePrices(): {
  prices: Record<string, number>
  isConnected: boolean
} {
  const { data, isConnected } = useWebSocket(WS_PRICES_URL)
  const [prices, setPrices] = useState<Record<string, number>>({})

  useEffect(() => {
    if (!data) return
    if (typeof data !== 'object' || data === null || Array.isArray(data)) return

    const msg = data as Record<string, unknown>
    // Backend sends { type: "prices"|"initial_prices", data: { BTCUSDT: 50000, ... } }
    const payload = msg.data ?? msg

    if (typeof payload === 'object' && payload !== null && !Array.isArray(payload)) {
      const incoming = payload as Record<string, unknown>
      const updated: Record<string, number> = {}
      for (const [key, val] of Object.entries(incoming)) {
        if (typeof val === 'number') {
          updated[key] = val
        }
      }
      if (Object.keys(updated).length > 0) {
        setPrices((prev) => ({ ...prev, ...updated }))
      }
    }
  }, [data])

  return { prices, isConnected }
}
