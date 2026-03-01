'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useWebSocket } from './useWebSocket'
import { fetchSignals, WS_SIGNALS_URL } from '@/lib/api'
import type { Signal } from '@/lib/types'

export function useSignals(): {
  signals: Signal[]
  isLoading: boolean
  refresh: () => void
} {
  const [signals, setSignals] = useState<Signal[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const { data } = useWebSocket(WS_SIGNALS_URL)

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const result = await fetchSignals()
      setSignals(result)
    } catch {
      // keep previous signals on error
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!data) return
    if (Array.isArray(data)) {
      setSignals(data as Signal[])
    } else if (typeof data === 'object' && data !== null) {
      const msg = data as { type?: string; signal?: Signal; signals?: Signal[] }
      if (msg.type === 'new_signal' && msg.signal) {
        setSignals((prev) => {
          const exists = prev.find((s) => s.id === msg.signal!.id)
          return exists ? prev : [msg.signal!, ...prev]
        })
      } else if (msg.type === 'update_signals' && msg.signals) {
        setSignals(msg.signals)
      }
    }
  }, [data])

  return { signals, isLoading, refresh: load }
}
