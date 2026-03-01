'use client'

import { useState, useEffect } from 'react'
import { fetchSignalHistory, fetchSignalStats } from '@/lib/api'
import type { Signal, SignalStats } from '@/lib/types'
import { History, TrendingUp, TrendingDown, Trophy, AlertCircle } from 'lucide-react'

interface StatCardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
}

function StatCard({ label, value, sub, color = 'text-gray-900' }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function HistoryPage() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [stats, setStats] = useState<SignalStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [coinFilter, setCoinFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState<'' | 'LONG' | 'SHORT'>('')

  const loadData = async () => {
    setLoading(true)
    try {
      const [histRes, statsRes] = await Promise.all([
        fetchSignalHistory({ limit: 100, coin: coinFilter || undefined, signal_type: typeFilter || undefined }),
        fetchSignalStats(),
      ])
      setSignals(histRes.signals)
      setStats(statsRes)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coinFilter, typeFilter])

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <History className="w-6 h-6 text-blue-600" />
          Signal History & P&L
        </h1>
        <p className="text-sm text-gray-500 mt-1">Closed signals with performance data</p>
      </div>

      {/* Stats Grid */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard
            label="Win Rate"
            value={`${(stats.win_rate ?? 0).toFixed(1)}%`}
            color={stats.win_rate >= 60 ? 'text-emerald-600' : stats.win_rate >= 50 ? 'text-amber-600' : 'text-red-600'}
          />
          <StatCard label="Total Trades" value={stats.total_signals ?? 0} />
          <StatCard
            label="Total P&L"
            value={`${(stats.total_pnl_pct ?? 0) >= 0 ? '+' : ''}${(stats.total_pnl_pct ?? 0).toFixed(1)}%`}
            color={(stats.total_pnl_pct ?? 0) >= 0 ? 'text-emerald-600' : 'text-red-600'}
          />
          <StatCard
            label="Best Trade"
            value={`+${(stats.best_trade_pct ?? 0).toFixed(1)}%`}
            color="text-emerald-600"
          />
          <StatCard
            label="Worst Trade"
            value={`${(stats.worst_trade_pct ?? 0).toFixed(1)}%`}
            color="text-red-600"
          />
          <StatCard label="Profit Factor" value={(stats.profit_factor ?? 0).toFixed(2)} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          placeholder="Filter by coin (e.g. BTC)"
          value={coinFilter}
          onChange={(e) => setCoinFilter(e.target.value.toUpperCase())}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-48"
        />
        <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white">
          {(['', 'LONG', 'SHORT'] as const).map((f) => (
            <button
              key={f || 'ALL'}
              onClick={() => setTypeFilter(f)}
              className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-1.5 ${
                typeFilter === f
                  ? f === 'LONG'
                    ? 'bg-emerald-500 text-white'
                    : f === 'SHORT'
                    ? 'bg-red-500 text-white'
                    : 'bg-blue-600 text-white'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f === 'LONG' && <TrendingUp className="w-3.5 h-3.5" />}
              {f === 'SHORT' && <TrendingDown className="w-3.5 h-3.5" />}
              {f || 'ALL'}
            </button>
          ))}
        </div>
      </div>

      {/* Signal History Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Coin</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Type</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Timeframe</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Confidence</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">R:R</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Result</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">P&L</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600 uppercase tracking-wide">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                [...Array(6)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(8)].map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 bg-gray-100 rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : signals.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-gray-400 text-sm">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    No signal history found
                  </td>
                </tr>
              ) : (
                signals.map((sig) => {
                  const isLong = sig.signal_type === 'LONG'
                  const resultBadge =
                    sig.result === 'WIN'
                      ? 'bg-emerald-100 text-emerald-700'
                      : sig.result === 'LOSS'
                      ? 'bg-red-100 text-red-700'
                      : sig.result === 'BE'
                      ? 'bg-gray-100 text-gray-600'
                      : 'bg-amber-100 text-amber-700'

                  return (
                    <tr key={sig.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 font-bold text-gray-900">{sig.coin}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
                          isLong ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                        }`}>
                          {isLong ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                          {sig.signal_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{sig.timeframe}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{sig.confidence_score}%</td>
                      <td className="px-4 py-3 text-right text-gray-700">1:{sig.risk_reward?.toFixed(1)}</td>
                      <td className="px-4 py-3 text-center">
                        {sig.result ? (
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${resultBadge}`}>
                            {sig.result === 'WIN' && <Trophy className="w-3 h-3 inline mr-0.5" />}
                            {sig.result}
                          </span>
                        ) : (
                          <span className="text-gray-400 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {sig.pnl_pct != null ? (
                          <span className={`font-bold ${sig.pnl_pct >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                            {sig.pnl_pct >= 0 ? '+' : ''}{sig.pnl_pct.toFixed(2)}%
                          </span>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-500 text-xs">
                        {new Date(sig.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
