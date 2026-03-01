'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

export function useWebSocket(url: string): {
  data: unknown
  isConnected: boolean
  error: string | null
} {
  const [data, setData] = useState<unknown>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const retryDelay = useRef(1000)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmounted = useRef(false)

  const connect = useCallback(() => {
    if (unmounted.current) return

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (unmounted.current) return
        setIsConnected(true)
        setError(null)
        retryDelay.current = 1000
      }

      ws.onmessage = (event: MessageEvent) => {
        if (unmounted.current) return
        try {
          const parsed: unknown = JSON.parse(event.data as string)
          setData(parsed)
        } catch {
          setData(event.data)
        }
      }

      ws.onerror = () => {
        if (unmounted.current) return
        setError('WebSocket connection error')
      }

      ws.onclose = () => {
        if (unmounted.current) return
        setIsConnected(false)
        const delay = Math.min(retryDelay.current, 30000)
        retryDelay.current = delay * 2
        retryTimer.current = setTimeout(connect, delay)
      }
    } catch (err) {
      setError('Failed to create WebSocket')
      const delay = Math.min(retryDelay.current, 30000)
      retryDelay.current = delay * 2
      retryTimer.current = setTimeout(connect, delay)
    }
  }, [url])

  useEffect(() => {
    unmounted.current = false
    connect()

    return () => {
      unmounted.current = true
      if (retryTimer.current) clearTimeout(retryTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  return { data, isConnected, error }
}
