'use client'

import { useEffect, useRef, useState } from 'react'
import type {
  IChartApi,
  ISeriesApi,
  CandlestickSeriesOptions,
  LineSeriesOptions,
  CandlestickData,
  Time,
} from 'lightweight-charts'
import { fetchCandles } from '@/lib/api'
import type { Signal, Candle } from '@/lib/types'
import { formatPrice } from '@/lib/utils'

interface TradingChartProps {
  symbol: string
  timeframe: string
  signal?: Signal
  height?: number
}

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1H', '4H', '1D', '1W']

export function TradingChart({ symbol, timeframe: initialTimeframe, signal, height = 420 }: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const [timeframe, setTimeframe] = useState(initialTimeframe)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return

    let chart: IChartApi | null = null

    const init = async () => {
      const { createChart, CrosshairMode } = await import('lightweight-charts')
      if (!containerRef.current) return

      chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
        layout: {
          background: { color: '#ffffff' },
          textColor: '#374151',
        },
        grid: {
          vertLines: { color: '#f1f5f9' },
          horzLines: { color: '#f1f5f9' },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: {
          borderColor: '#e5e7eb',
        },
        timeScale: {
          borderColor: '#e5e7eb',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      chartRef.current = chart

      const candleSeries = chart.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        borderUpColor: '#10b981',
        borderDownColor: '#ef4444',
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
      } as Partial<CandlestickSeriesOptions>)

      candleSeriesRef.current = candleSeries

      // Resize handler
      const resizeObserver = new ResizeObserver(() => {
        if (containerRef.current && chart) {
          chart.applyOptions({ width: containerRef.current.clientWidth })
        }
      })
      if (containerRef.current) resizeObserver.observe(containerRef.current)

      return () => {
        resizeObserver.disconnect()
        chart?.remove()
      }
    }

    const cleanup = init()
    return () => {
      void cleanup.then((fn) => fn?.())
    }
  }, [])

  // Load candles when symbol/timeframe changes
  useEffect(() => {
    if (!candleSeriesRef.current) return

    setLoading(true)
    setError(null)

    fetchCandles(symbol, timeframe)
      .then((candles: Candle[]) => {
        if (!candleSeriesRef.current) return
        const data: CandlestickData[] = candles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
        candleSeriesRef.current.setData(data)
        chartRef.current?.timeScale().fitContent()
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [symbol, timeframe])

  // Draw signal levels
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || !signal) return

    const drawLine = (price: number, color: string, style: number, title: string) => {
      try {
        const priceLine = candleSeriesRef.current!.createPriceLine({
          price,
          color,
          lineWidth: 1,
          lineStyle: style,
          axisLabelVisible: true,
          title,
        })
        return priceLine
      } catch {
        return null
      }
    }

    // LineStyle: 0=Solid, 1=Dotted, 2=Dashed
    const lines = [
      drawLine(signal.entry_low, '#3b82f6', 2, 'Entry Low'),
      drawLine(signal.entry_high, '#3b82f6', 2, 'Entry High'),
      drawLine(signal.stop_loss, '#ef4444', 2, 'Stop Loss'),
      drawLine(signal.take_profit_1, '#10b981', 2, 'TP1'),
      drawLine(signal.take_profit_2, '#10b981', 2, 'TP2'),
      drawLine(signal.take_profit_3, '#10b981', 2, 'TP3'),
    ]

    return () => {
      lines.forEach((line) => {
        if (line && candleSeriesRef.current) {
          try {
            candleSeriesRef.current.removePriceLine(line)
          } catch {
            // ignore
          }
        }
      })
    }
  }, [signal])

  return (
    <div className="space-y-3">
      {/* Timeframe selector */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1 flex-wrap">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                timeframe === tf
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Signal levels legend */}
        {signal && (
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-4 border-t-2 border-blue-500 border-dashed inline-block" />
              Entry
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 border-t-2 border-red-500 border-dashed inline-block" />
              SL {formatPrice(signal.stop_loss)}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 border-t-2 border-emerald-500 border-dashed inline-block" />
              TP {formatPrice(signal.take_profit_1)}
            </span>
          </div>
        )}
      </div>

      {/* Chart container */}
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 bg-white bg-opacity-80 flex items-center justify-center z-10 rounded-lg">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              Loading chart...
            </div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 bg-white flex items-center justify-center z-10 rounded-lg">
            <p className="text-sm text-red-500">Failed to load chart data</p>
          </div>
        )}
        <div ref={containerRef} className="w-full rounded-lg overflow-hidden border border-gray-100" />
      </div>
    </div>
  )
}
