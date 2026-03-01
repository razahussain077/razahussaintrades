'use client'

import { useEffect, useState } from 'react'
import { fetchSignalHistory, fetchSignalStats } from '@/lib/api'
import type { Signal, SignalStats } from '@/lib/types'
import { formatPrice, formatPercentage, timeAgo } from '@/lib/utils'
import { TrendingUp, TrendingDown, Trophy, XCircle, BarChart3, DollarSign } from 'lucide-react'

export default function HistoryPage() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [stats, setStats] = useState<SignalStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'LONG' | 'SHORT'>('all')

  useEffect(() => {
    async function load() {
      try {
        const [historyRes, statsRes] = await Promise.all([
          fetchSignalHistory({ limit: 100 }),
          fetchSignalStats(),
        ])
        setSignals(historyRes.signals)
        setStats(statsRes)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const filtered = filter === 'all' ? signals : signals.filter((s) => s.signal_type === filter)

  const winRate = stats?.win_rate ?? 0
  const totalPnl = stats?.total_pnl ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Signal History & P&L</h1>
        <p className="text-sm text-gray-500 mt-1">Track performance of all past signals</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Trades"
          value={stats?.total_trades?.toString() ?? '—'}
          icon={<BarChart3 className="w-5 h-5 text-blue-500" />}
          color="blue"
        />
        <StatCard
          label="Win Rate"
          value={stats ? `${winRate}%` : '—'}
          icon={<Trophy className="w-5 h-5 text-emerald-500" />}
          color={winRate >= 50 ? 'emerald' : 'red'}
        />
        <StatCard
          label="Total P&L"
          value={stats ? `$${totalPnl.toFixed(2)}` : '—'}
          icon={<DollarSign className="w-5 h-5 text-amber-500" />}
          color={totalPnl >= 0 ? 'emerald' : 'red'}
        />
        <StatCard
          label="Wins / Losses"
          value={stats ? `${stats.WIN} / ${stats.LOSS}` : '—'}
          icon={<TrendingUp className="w-5 h-5 text-purple-500" />}
          color="purple"
        />
      </div>

      {/* Equity Curve placeholder */}
      {stats && stats.total_trades > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Cumulative P&L</h2>
          <div className="h-24 flex items-end gap-1">
            {signals.slice(-30).map((s, i) => {
              const pnl = s.pnl_pct ?? 0
              const height = Math.min(Math.abs(pnl) * 8 + 4, 80)
              return (
                <div
                  key={i}
                  className={`flex-1 rounded-sm ${pnl >= 0 ? 'bg-emerald-400' : 'bg-red-400'}`}
                  style={{ height: `${height}px` }}
                  title={`${pnl >= 0 ? '+' : ''}${pnl?.toFixed(2) ?? '0'}%`}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Filter + Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-bold text-gray-900">All Signals</h2>
          <div className="flex gap-1">
            {(['all', 'LONG', 'SHORT'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  filter === f ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                {f === 'all' ? 'All' : f}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading history...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No closed signals yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="text-left px-4 py-2 text-xs text-gray-500 font-medium">Coin</th>
                  <th className="text-left px-4 py-2 text-xs text-gray-500 font-medium">Dir</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">Entry</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">SL</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">TP1</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">Result</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">P&L</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">R:R</th>
                  <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((sig) => {
                  const isLong = sig.signal_type === 'LONG'
                  const entry = (sig.entry_low + sig.entry_high) / 2
                  const result = sig.result
                  const pnl = sig.pnl_pct

                  return (
                    <tr
                      key={sig.id}
                      className={`border-b border-gray-50 hover:bg-gray-50 ${
                        result === 'WIN' ? 'bg-emerald-50/30' : result === 'LOSS' ? 'bg-red-50/30' : ''
                      }`}
                    >
                      <td className="px-4 py-2.5 font-semibold text-gray-900">{sig.coin}</td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                            isLong ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                          }`}
                        >
                          {sig.signal_type}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">{formatPrice(entry)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-red-600">{formatPrice(sig.stop_loss)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-emerald-600">{formatPrice(sig.take_profit_1)}</td>
                      <td className="px-4 py-2.5 text-right">
                        {result ? (
                          <span
                            className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                              result === 'WIN' ? 'bg-emerald-100 text-emerald-700' :
                              result === 'LOSS' ? 'bg-red-100 text-red-700' :
                              'bg-gray-100 text-gray-600'
                            }`}
                          >
                            {result}
                          </span>
                        ) : (
                          <span className="text-gray-400 text-xs">—</span>
                        )}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono text-xs font-medium ${
                        pnl != null ? (pnl >= 0 ? 'text-emerald-600' : 'text-red-600') : 'text-gray-400'
                      }`}>
                        {pnl != null ? `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right text-xs text-gray-600">1:{sig.risk_reward.toFixed(1)}</td>
                      <td className="px-4 py-2.5 text-right text-xs text-gray-400">{timeAgo(sig.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, icon, color }: { label: string; value: string; icon: React.ReactNode; color: string }) {
  const colorMap: Record<string, string> = {
    blue: 'bg-blue-50 border-blue-100',
    emerald: 'bg-emerald-50 border-emerald-100',
    red: 'bg-red-50 border-red-100',
    amber: 'bg-amber-50 border-amber-100',
    purple: 'bg-purple-50 border-purple-100',
  }
  return (
    <div className={`rounded-xl border p-4 ${colorMap[color] ?? colorMap.blue}`}>
      <div className="flex items-center gap-2 mb-2">{icon}<span className="text-xs text-gray-500">{label}</span></div>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  )
}
