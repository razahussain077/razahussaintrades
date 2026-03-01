'use client'

import { useState } from 'react'
import { runBacktest } from '@/lib/api'
import type { BacktestResult } from '@/lib/types'
import { FlaskConical, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'

export default function BacktestPage() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)

  const handleRun = async () => {
    if (!symbol) return
    setError(null)
    setLoading(true)
    try {
      const res = await runBacktest({ symbol: symbol.toUpperCase(), timeframe, days })
      setResult(res)
    } catch {
      setError('Backtest failed. Ensure the symbol is valid and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-blue-600" />
          Backtesting Engine
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Test the SMC signal strategy against historical data
        </p>
      </div>

      {/* Config Form */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="font-bold text-gray-900 mb-4">Run Backtest</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. BTCUSDT"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              {['15m', '1h', '4h', '1d'].map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Days (max 90)</label>
            <input
              type="number"
              min={7}
              max={90}
              value={days}
              onChange={(e) => setDays(Math.min(90, Math.max(7, Number(e.target.value))))}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {error && (
          <div className="mt-3 flex items-center gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg p-2.5">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            {error}
          </div>
        )}

        <button
          onClick={handleRun}
          disabled={loading}
          className="mt-4 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? 'Running Backtest...' : 'Run Backtest'}
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-5">
          {/* Summary Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { label: 'Win Rate', value: `${(result.win_rate ?? 0).toFixed(1)}%`, color: result.win_rate >= 50 ? 'text-emerald-600' : 'text-red-600' },
              { label: 'Total Trades', value: result.total_trades ?? 0 },
              { label: 'Total Return', value: `${(result.total_return_pct ?? 0) >= 0 ? '+' : ''}${(result.total_return_pct ?? 0).toFixed(1)}%`, color: (result.total_return_pct ?? 0) >= 0 ? 'text-emerald-600' : 'text-red-600' },
              { label: 'Profit Factor', value: (result.profit_factor ?? 0).toFixed(2) },
              { label: 'Sharpe Ratio', value: (result.sharpe_ratio ?? 0).toFixed(2) },
              { label: 'Max Drawdown', value: `${(result.max_drawdown_pct ?? 0).toFixed(1)}%`, color: 'text-red-600' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 mb-1">{label}</p>
                <p className={`text-xl font-bold ${color ?? 'text-gray-900'}`}>{value}</p>
              </div>
            ))}
          </div>

          {/* Trade List */}
          {result.trades && result.trades.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100">
                <h3 className="font-bold text-gray-900">Trade Log ({result.trades.length} trades)</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="text-left px-4 py-2 text-xs font-semibold text-gray-600 uppercase">#</th>
                      <th className="text-left px-4 py-2 text-xs font-semibold text-gray-600 uppercase">Type</th>
                      <th className="text-right px-4 py-2 text-xs font-semibold text-gray-600 uppercase">Entry</th>
                      <th className="text-right px-4 py-2 text-xs font-semibold text-gray-600 uppercase">Exit</th>
                      <th className="text-center px-4 py-2 text-xs font-semibold text-gray-600 uppercase">Result</th>
                      <th className="text-right px-4 py-2 text-xs font-semibold text-gray-600 uppercase">P&L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {result.trades.slice(0, 50).map((trade, i) => {
                      const isLong = trade.signal_type === 'LONG'
                      return (
                        <tr key={trade.id ?? i} className="hover:bg-gray-50">
                          <td className="px-4 py-2 text-gray-500">{i + 1}</td>
                          <td className="px-4 py-2">
                            <span className={`inline-flex items-center gap-1 text-xs font-bold ${isLong ? 'text-emerald-600' : 'text-red-600'}`}>
                              {isLong ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                              {trade.signal_type}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-gray-700">
                            {typeof trade.entry === 'number' ? trade.entry.toLocaleString() : trade.entry}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-gray-700">
                            {typeof trade.exit === 'number' ? trade.exit.toLocaleString() : trade.exit}
                          </td>
                          <td className="px-4 py-2 text-center">
                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                              trade.result === 'WIN' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                            }`}>
                              {trade.result}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-right">
                            <span className={`font-bold ${trade.pnl_pct >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                              {trade.pnl_pct >= 0 ? '+' : ''}{trade.pnl_pct?.toFixed(2)}%
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
