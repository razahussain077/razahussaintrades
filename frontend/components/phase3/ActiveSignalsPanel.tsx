'use client'

import { useEffect, useState } from 'react'
import { fetchActiveSignalsLive } from '@/lib/api'
import type { Signal } from '@/lib/types'
import { formatPrice, timeAgo } from '@/lib/utils'
import { TrendingUp, TrendingDown, Activity } from 'lucide-react'
import Link from 'next/link'

export function ActiveSignalsPanel() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchActiveSignalsLive()
        setSignals(res.signals.slice(0, 8))
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-blue-600" />
          <h3 className="font-bold text-gray-900 text-sm">Active Signals</h3>
          {!loading && (
            <span className="px-1.5 py-0.5 text-xs font-bold bg-blue-100 text-blue-700 rounded-full">
              {signals.length}
            </span>
          )}
        </div>
        <Link href="/signals" className="text-xs text-blue-600 hover:underline">View All</Link>
      </div>

      {loading ? (
        <div className="p-4 space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-14 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : signals.length === 0 ? (
        <div className="p-6 text-center text-gray-400 text-sm">No active signals</div>
      ) : (
        <div className="divide-y divide-gray-50">
          {signals.map((sig) => {
            const isLong = sig.signal_type === 'LONG'
            const entry = (sig.entry_low + sig.entry_high) / 2
            const pnl = sig.unrealized_pnl_pct ?? 0
            const progress = sig.progress_to_tp1 ?? 0

            return (
              <div key={sig.id} className="px-4 py-3">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    {isLong ? (
                      <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <TrendingDown className="w-3.5 h-3.5 text-red-600" />
                    )}
                    <span className="font-bold text-sm text-gray-900">{sig.coin}</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                      isLong ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                    }`}>{sig.signal_type}</span>
                  </div>
                  <span className={`text-xs font-bold ${pnl >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%
                  </span>
                </div>

                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Entry: {formatPrice(entry)}</span>
                  {sig.current_price && <span>Now: {formatPrice(sig.current_price)}</span>}
                </div>

                {/* Progress bar: SL → Entry → TP1 */}
                <div className="relative h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${pnl >= 0 ? 'bg-emerald-400' : 'bg-red-400'}`}
                    style={{ width: `${Math.min(progress, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>SL</span>
                  <span>{progress.toFixed(0)}% to TP1</span>
                  <span>TP1</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
