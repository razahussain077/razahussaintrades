'use client'

import { useState } from 'react'
import { runBacktest } from '@/lib/api'
import type { BacktestResult } from '@/lib/types'
import { Play, BarChart3, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'AVAXUSDT']
const TIMEFRAMES = ['1h', '4h', '1d']
const DAY_OPTIONS = [7, 14, 30, 60, 90]

export default function BacktestPage() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [days, setDays] = useState(30)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await runBacktest({ symbol, timeframe, days })
      setResult(res)
    } catch (e: any) {
      setError(e.message ?? 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  const stats = result?.stats

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Backtesting Engine</h1>
        <p className="text-sm text-gray-500 mt-1">Test strategy performance on historical data</p>
      </div>

      {/* Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-bold text-gray-900 mb-4">Run Backtest</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Symbol</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Days of History</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {DAY_OPTIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleRun}
              disabled={running}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Play className="w-4 h-4" />
              {running ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>
        {error && (
          <div className="flex gap-2 text-red-600 bg-red-50 rounded-lg p-3 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {stats && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatsCard label="Total Signals" value={stats.total_signals.toString()} color="blue" />
            <StatsCard
              label="Win Rate"
              value={`${stats.win_rate}%`}
              color={stats.win_rate >= 50 ? 'emerald' : 'red'}
            />
            <StatsCard
              label="Profit Factor"
              value={stats.profit_factor === 999 ? '∞' : stats.profit_factor.toFixed(2)}
              color={stats.profit_factor >= 1.5 ? 'emerald' : 'amber'}
            />
            <StatsCard
              label="Max Drawdown"
              value={`${stats.max_drawdown_pct.toFixed(1)}%`}
              color={stats.max_drawdown_pct <= 15 ? 'emerald' : 'red'}
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatsCard label="Avg R:R" value={`1:${stats.avg_rr.toFixed(2)}`} color="blue" />
            <StatsCard label="Sharpe Ratio" value={stats.sharpe_ratio.toFixed(2)} color={stats.sharpe_ratio >= 1 ? 'emerald' : 'amber'} />
            <StatsCard label="Best Trade" value={`+${stats.best_trade_pct.toFixed(2)}%`} color="emerald" />
            <StatsCard label="Worst Trade" value={`${stats.worst_trade_pct.toFixed(2)}%`} color="red" />
          </div>

          {/* Equity Curve */}
          {stats.equity_curve.length > 1 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <h2 className="font-bold text-gray-900 mb-3">Equity Curve</h2>
              <div className="h-32 flex items-end gap-0.5">
                {stats.equity_curve.map((val, i) => {
                  const min = Math.min(...stats.equity_curve)
                  const max = Math.max(...stats.equity_curve)
                  const range = max - min || 1
                  const heightPct = ((val - min) / range) * 100
                  const isAboveStart = val >= stats.equity_curve[0]
                  return (
                    <div
                      key={i}
                      className={`flex-1 rounded-sm ${isAboveStart ? 'bg-emerald-400' : 'bg-red-400'}`}
                      style={{ height: `${Math.max(heightPct, 4)}%` }}
                      title={`$${val.toFixed(2)}`}
                    />
                  )
                })}
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>Start: $1,000</span>
                <span>End: ${stats.equity_curve[stats.equity_curve.length - 1]?.toFixed(2)}</span>
              </div>
            </div>
          )}

          {/* Trade Table */}
          {result?.trades && result.trades.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100">
                <h2 className="font-bold text-gray-900">Recent Trades ({result.trades.length})</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-4 py-2 text-xs text-gray-500">#</th>
                      <th className="text-left px-4 py-2 text-xs text-gray-500">Dir</th>
                      <th className="text-right px-4 py-2 text-xs text-gray-500">Entry</th>
                      <th className="text-right px-4 py-2 text-xs text-gray-500">Exit</th>
                      <th className="text-right px-4 py-2 text-xs text-gray-500">Result</th>
                      <th className="text-right px-4 py-2 text-xs text-gray-500">P&L</th>
                      <th className="text-right px-4 py-2 text-xs text-gray-500">R:R</th>
                      <th className="text-right px-4 py-2 text-xs text-gray-500">Bars</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(-30).map((trade, i) => (
                      <tr key={i} className={`border-b border-gray-50 ${trade.pnl_pct >= 0 ? 'bg-emerald-50/20' : 'bg-red-50/20'}`}>
                        <td className="px-4 py-2 text-gray-400 text-xs">{i + 1}</td>
                        <td className="px-4 py-2">
                          <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                            trade.signal_type === 'LONG' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                          }`}>{trade.signal_type}</span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-xs">${trade.entry_price.toFixed(2)}</td>
                        <td className="px-4 py-2 text-right font-mono text-xs">${trade.exit_price?.toFixed(2) ?? '—'}</td>
                        <td className="px-4 py-2 text-right">
                          <span className={`text-xs font-bold ${
                            trade.result === 'SL' ? 'text-red-600' : 'text-emerald-600'
                          }`}>{trade.result}</span>
                        </td>
                        <td className={`px-4 py-2 text-right text-xs font-medium ${trade.pnl_pct >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                          {trade.pnl_pct >= 0 ? '+' : ''}{trade.pnl_pct.toFixed(2)}%
                        </td>
                        <td className="px-4 py-2 text-right text-xs text-gray-600">1:{trade.rr.toFixed(1)}</td>
                        <td className="px-4 py-2 text-right text-xs text-gray-400">{trade.bars_held}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StatsCard({ label, value, color }: { label: string; value: string; color: string }) {
  const colorMap: Record<string, string> = {
    blue: 'bg-blue-50 border-blue-100',
    emerald: 'bg-emerald-50 border-emerald-100',
    red: 'bg-red-50 border-red-100',
    amber: 'bg-amber-50 border-amber-100',
  }
  return (
    <div className={`rounded-xl border p-4 ${colorMap[color] ?? colorMap.blue}`}>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  )
}
