'use client'

import { useEffect, useState } from 'react'
import { fetchPortfolioExposure, fetchPositionSize, fetchRiskSettings, updateRiskSettings } from '@/lib/api'
import type { PortfolioExposure, PositionSizeResult } from '@/lib/types'
import { Shield, AlertTriangle, TrendingUp, TrendingDown, DollarSign, Zap } from 'lucide-react'

export default function RiskPage() {
  const [exposure, setExposure] = useState<PortfolioExposure | null>(null)
  const [posResult, setPosResult] = useState<PositionSizeResult | null>(null)
  const [settings, setSettings] = useState({ balance: 1000, risk_pct: 1, max_trades: 5 })
  const [calcInputs, setCalcInputs] = useState({
    balance: 1000,
    risk_pct: 1,
    entry_price: 0,
    stop_loss_price: 0,
    confidence_score: 75,
    signal_type: 'LONG',
  })
  const [loading, setLoading] = useState(true)
  const [calcLoading, setCalcLoading] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const [exp, s] = await Promise.all([
          fetchPortfolioExposure().catch(() => null),
          fetchRiskSettings().catch(() => null),
        ])
        if (exp) setExposure(exp)
        if (s) {
          setSettings(s)
          setCalcInputs((prev) => ({ ...prev, balance: s.balance, risk_pct: s.risk_pct }))
        }
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleSaveSettings = async () => {
    await updateRiskSettings(settings)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
    const exp = await fetchPortfolioExposure().catch(() => null)
    if (exp) setExposure(exp)
  }

  const handleCalculate = async () => {
    if (!calcInputs.entry_price || !calcInputs.stop_loss_price) return
    setCalcLoading(true)
    try {
      const result = await fetchPositionSize(calcInputs)
      setPosResult(result)
    } catch (e) {
      console.error(e)
    } finally {
      setCalcLoading(false)
    }
  }

  const riskColors = {
    green: 'bg-emerald-500',
    yellow: 'bg-amber-500',
    red: 'bg-red-500',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Risk Manager</h1>
        <p className="text-sm text-gray-500 mt-1">Position sizing, portfolio exposure, and risk controls</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Portfolio Exposure */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-600" />
            <h2 className="font-bold text-gray-900">Portfolio Exposure</h2>
          </div>

          {loading ? (
            <div className="text-gray-400 text-sm">Loading...</div>
          ) : exposure ? (
            <>
              {/* Risk Meter */}
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>Risk Level: <span className="font-bold">{exposure.risk_label}</span></span>
                  <span>{exposure.total_open_signals}/{exposure.max_trades} positions</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div
                    className={`h-2.5 rounded-full ${riskColors[exposure.risk_level]}`}
                    style={{ width: `${Math.min((exposure.total_open_signals / exposure.max_trades) * 100, 100)}%` }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <MetricBox label="Long Signals" value={exposure.long_count.toString()} sub="open" color="emerald" />
                <MetricBox label="Short Signals" value={exposure.short_count.toString()} sub="open" color="red" />
                <MetricBox label="Daily P&L" value={`$${exposure.daily_pnl.toFixed(2)}`} sub={`${exposure.daily_pnl_pct.toFixed(2)}%`} color={exposure.daily_pnl >= 0 ? 'emerald' : 'red'} />
                <MetricBox label="L/S Ratio" value={exposure.long_short_ratio.toFixed(2)} sub="long/short" color="blue" />
              </div>

              {exposure.daily_loss_warning && (
                <div className="flex gap-2 text-red-700 bg-red-50 rounded-lg p-3 text-xs">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  {exposure.daily_loss_message}
                </div>
              )}
              {exposure.over_max_warning && (
                <div className="flex gap-2 text-amber-700 bg-amber-50 rounded-lg p-3 text-xs">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  ⚠️ Max concurrent trades reached ({exposure.max_trades}) — new signals still shown
                </div>
              )}
            </>
          ) : (
            <div className="text-gray-400 text-sm">No exposure data</div>
          )}
        </div>

        {/* Risk Settings */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
          <div className="flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-amber-500" />
            <h2 className="font-bold text-gray-900">Risk Settings</h2>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Account Balance (USD)</label>
              <input
                type="number"
                value={settings.balance}
                onChange={(e) => setSettings((s) => ({ ...s, balance: Number(e.target.value) }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                min={0}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Risk per Trade (%)</label>
              <input
                type="number"
                value={settings.risk_pct}
                onChange={(e) => setSettings((s) => ({ ...s, risk_pct: Number(e.target.value) }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                min={0.1}
                max={10}
                step={0.1}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Max Concurrent Trades</label>
              <input
                type="number"
                value={settings.max_trades}
                onChange={(e) => setSettings((s) => ({ ...s, max_trades: Number(e.target.value) }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                min={1}
                max={20}
              />
            </div>
            <button
              onClick={handleSaveSettings}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {saved ? '✓ Saved!' : 'Save Settings'}
            </button>
          </div>
        </div>
      </div>

      {/* Position Size Calculator */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-purple-500" />
          <h2 className="font-bold text-gray-900">Position Size Calculator</h2>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Balance (USD)</label>
            <input
              type="number"
              value={calcInputs.balance}
              onChange={(e) => setCalcInputs((c) => ({ ...c, balance: Number(e.target.value) }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Risk % per Trade</label>
            <input
              type="number"
              value={calcInputs.risk_pct}
              onChange={(e) => setCalcInputs((c) => ({ ...c, risk_pct: Number(e.target.value) }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              step={0.1}
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Signal Direction</label>
            <select
              value={calcInputs.signal_type}
              onChange={(e) => setCalcInputs((c) => ({ ...c, signal_type: e.target.value }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="LONG">LONG</option>
              <option value="SHORT">SHORT</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Entry Price</label>
            <input
              type="number"
              value={calcInputs.entry_price || ''}
              onChange={(e) => setCalcInputs((c) => ({ ...c, entry_price: Number(e.target.value) }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. 67000"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Stop Loss Price</label>
            <input
              type="number"
              value={calcInputs.stop_loss_price || ''}
              onChange={(e) => setCalcInputs((c) => ({ ...c, stop_loss_price: Number(e.target.value) }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. 66500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Signal Confidence (%)</label>
            <input
              type="number"
              value={calcInputs.confidence_score}
              onChange={(e) => setCalcInputs((c) => ({ ...c, confidence_score: Number(e.target.value) }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              min={0}
              max={100}
            />
          </div>
        </div>

        <button
          onClick={handleCalculate}
          disabled={calcLoading || !calcInputs.entry_price || !calcInputs.stop_loss_price}
          className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {calcLoading ? 'Calculating...' : 'Calculate Position'}
        </button>

        {posResult && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
            <ResultBox label="Position Size" value={posResult.position_size.toFixed(4)} unit="coins" />
            <ResultBox label="Position Value" value={`$${posResult.position_value.toFixed(2)}`} unit="" />
            <ResultBox label="Risk Amount" value={`$${posResult.risk_amount.toFixed(2)}`} unit={`(${posResult.risk_pct}%)`} />
            <ResultBox label="Suggested Leverage" value={`${posResult.suggested_leverage}x`} unit={posResult.tier} highlight={posResult.suggested_leverage > 10} />
            <ResultBox label="Liquidation Price" value={`$${posResult.liquidation_price.toFixed(2)}`} unit="" highlight />
            <ResultBox label="SL Distance" value={`$${posResult.sl_distance?.toFixed(2) ?? '—'}`} unit="" />
          </div>
        )}
      </div>
    </div>
  )
}

function MetricBox({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  const colorMap: Record<string, string> = {
    emerald: 'text-emerald-600',
    red: 'text-red-600',
    blue: 'text-blue-600',
  }
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold ${colorMap[color] ?? 'text-gray-900'}`}>{value}</p>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  )
}

function ResultBox({ label, value, unit, highlight }: { label: string; value: string; unit: string; highlight?: boolean }) {
  return (
    <div className={`rounded-lg p-3 border ${highlight ? 'bg-red-50 border-red-100' : 'bg-gray-50 border-gray-100'}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-bold ${highlight ? 'text-red-600' : 'text-gray-900'}`}>{value}</p>
      {unit && <p className="text-xs text-gray-400">{unit}</p>}
    </div>
  )
}
