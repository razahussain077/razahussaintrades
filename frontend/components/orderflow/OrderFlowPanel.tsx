'use client'

import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Activity, AlertTriangle } from 'lucide-react'

import {
  fetchOrderFlow,
  fetchOrderFlowDivergence,
  type OrderFlowDivergence,
  type OrderFlowSnapshot,
} from '@/lib/api'

interface Props {
  symbol: string
  pollMs?: number
}

function formatUsd(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

function deltaTone(d: number): string {
  if (d >= 0.2) return 'text-green-700 bg-green-50'
  if (d <= -0.2) return 'text-red-700 bg-red-50'
  return 'text-gray-600 bg-gray-50'
}

export default function OrderFlowPanel({ symbol, pollMs = 5_000 }: Props) {
  const [snap, setSnap] = useState<OrderFlowSnapshot | null>(null)
  const [div, setDiv] = useState<OrderFlowDivergence | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [s, d] = await Promise.all([
          fetchOrderFlow(symbol),
          fetchOrderFlowDivergence(symbol).catch(() => null),
        ])
        if (cancelled) return
        setSnap(s)
        setDiv(d)
        setError(null)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = window.setInterval(load, pollMs)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [symbol, pollMs])

  if (loading && !snap) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <Activity className="w-4 h-4" /> Order Flow (live)
        </h3>
        <p className="text-sm text-gray-500 mt-2">Loading…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-xl border border-red-200 p-4">
        <h3 className="font-semibold text-red-900 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Order Flow unavailable
        </h3>
        <p className="text-sm text-red-700 mt-2">{error}</p>
      </div>
    )
  }

  const haveCvd = !!snap?.cvd.have_data
  const cvd = snap?.cvd
  const lp = snap?.large_prints

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <Activity className="w-4 h-4" /> Order Flow (live)
        </h3>
        {!haveCvd && (
          <span className="text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md">
            Awaiting first prints…
          </span>
        )}
      </div>

      {haveCvd && cvd && (
        <>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className={`rounded-lg p-2 ${deltaTone(cvd.delta_1m_normalized)}`}>
              <p className="text-[11px] uppercase tracking-wide opacity-70">
                Δ 1m (normalized)
              </p>
              <p className="font-bold">{cvd.delta_1m_normalized.toFixed(2)}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2">
              <p className="text-[11px] uppercase tracking-wide text-gray-500">
                Trades buffered
              </p>
              <p className="font-bold text-gray-900">{cvd.trades_recorded}</p>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 text-xs">
            {([
              ['1m', cvd.cvd_1m],
              ['5m', cvd.cvd_5m],
              ['15m', cvd.cvd_15m],
              ['1h', cvd.cvd_1h],
            ] as const).map(([label, val]) => (
              <div key={label} className="rounded-md bg-gray-50 p-2">
                <p className="text-gray-500">{label} CVD</p>
                <p className={`font-semibold ${val >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                  {val >= 0 ? '+' : ''}
                  {formatUsd(val)}
                </p>
              </div>
            ))}
          </div>

          {lp && lp.have_data && (lp.large_buy_count > 0 || lp.large_sell_count > 0) && (
            <div className="border-t border-gray-100 pt-2">
              <p className="text-xs text-gray-500 mb-1">Large prints (last 1m)</p>
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1 text-green-700">
                  <TrendingUp className="w-3.5 h-3.5" />
                  {lp.large_buy_count}× / {formatUsd(lp.large_buy_volume)}
                </span>
                <span className="flex items-center gap-1 text-red-700">
                  <TrendingDown className="w-3.5 h-3.5" />
                  {lp.large_sell_count}× / {formatUsd(lp.large_sell_volume)}
                </span>
              </div>
            </div>
          )}

          {div && div.have_data && (div.bullish_divergence || div.bearish_divergence) && (
            <div
              className={`rounded-lg p-2 text-sm border ${
                div.bullish_divergence
                  ? 'border-green-200 bg-green-50 text-green-800'
                  : 'border-red-200 bg-red-50 text-red-800'
              }`}
            >
              {div.bullish_divergence
                ? 'Bullish CVD divergence: price lower low, CVD higher low (absorption)'
                : 'Bearish CVD divergence: price higher high, CVD lower high (absorption)'}
            </div>
          )}
        </>
      )}
    </div>
  )
}
