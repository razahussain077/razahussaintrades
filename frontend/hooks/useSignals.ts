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
      const msg = data as { type?: string; data?: Signal | Signal[]; signal?: Signal; signals?: Signal[] }
      if (msg.type === 'initial_signals' && Array.isArray(msg.data)) {
        setSignals(msg.data as Signal[])
      } else if (msg.type === 'signal' && msg.data && !Array.isArray(msg.data)) {
        const sig = msg.data as Signal
        setSignals((prev) => {
          const exists = prev.find((s) => s.id === sig.id)
          return exists ? prev : [sig, ...prev]
        })
      } else if (msg.type === 'signals_update' && Array.isArray(msg.data)) {
        setSignals(msg.data as Signal[])
      } else if (msg.type === 'new_signal' && msg.signal) {
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
