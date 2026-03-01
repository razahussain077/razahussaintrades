'use client'

import { useEffect, useRef, useState } from 'react'
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
    if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
      const incoming = data as Record<string, unknown>
      const updated: Record<string, number> = {}
      for (const [key, val] of Object.entries(incoming)) {
        if (typeof val === 'number') {
          updated[key] = val
        }
      }
      setPrices((prev) => ({ ...prev, ...updated }))
    }
  }, [data])

  return { prices, isConnected }
}
