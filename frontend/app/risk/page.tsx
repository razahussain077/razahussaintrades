'use client'

import { useState, useEffect } from 'react'
import {
  fetchPositionSize,
  fetchPortfolioExposure,
  fetchRiskSettings,
  updateRiskSettings,
  type PositionSizeParams,
  type RiskSettings,
} from '@/lib/api'
import { Shield, Calculator, PieChart, Settings, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'

export default function RiskManagerPage() {
  // Position size calculator state
  const [calcForm, setCalcForm] = useState<PositionSizeParams>({
    balance: 1000,
    risk_pct: 1,
    entry_price: 0,
    stop_loss_price: 0,
    confidence_score: 70,
    signal_type: 'LONG',
  })
  const [calcResult, setCalcResult] = useState<Record<string, unknown> | null>(null)
  const [calcLoading, setCalcLoading] = useState(false)
  const [calcError, setCalcError] = useState<string | null>(null)

  // Portfolio exposure state
  const [portfolio, setPortfolio] = useState<Record<string, unknown> | null>(null)
  const [portfolioLoading, setPortfolioLoading] = useState(true)

  // Risk settings state
  const [settings, setSettings] = useState<RiskSettings>({ balance: 1000, risk_pct: 1, max_trades: 5 })
  const [settingsSaved, setSettingsSaved] = useState(false)

  useEffect(() => {
    fetchRiskSettings()
      .then((s) => setSettings(s))
      .catch(() => null)

    fetchPortfolioExposure()
      .then(setPortfolio)
      .catch(() => null)
      .finally(() => setPortfolioLoading(false))
  }, [])

  const handleCalc = async () => {
    if (!calcForm.entry_price || !calcForm.stop_loss_price) {
      setCalcError('Entry price and stop loss are required.')
      return
    }
    setCalcError(null)
    setCalcLoading(true)
    try {
      const result = await fetchPositionSize(calcForm)
      setCalcResult(result)
    } catch (e) {
      setCalcError('Failed to calculate position size.')
    } finally {
      setCalcLoading(false)
    }
  }

  const handleSaveSettings = async () => {
    try {
      await updateRiskSettings(settings)
      setSettingsSaved(true)
      setTimeout(() => setSettingsSaved(false), 2000)
    } catch {
      // silent
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Shield className="w-6 h-6 text-blue-600" />
          Risk Manager
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Calculate position sizes, monitor portfolio exposure, and manage risk settings
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Position Size Calculator */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Calculator className="w-5 h-5 text-blue-600" />
            <h2 className="font-bold text-gray-900">Position Size Calculator</h2>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Balance (USD)</label>
                <input
                  type="number"
                  value={calcForm.balance}
                  onChange={(e) => setCalcForm({ ...calcForm, balance: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Risk %</label>
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  max="10"
                  value={calcForm.risk_pct}
                  onChange={(e) => setCalcForm({ ...calcForm, risk_pct: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Entry Price</label>
                <input
                  type="number"
                  value={calcForm.entry_price || ''}
                  onChange={(e) => setCalcForm({ ...calcForm, entry_price: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. 42000"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Stop Loss Price</label>
                <input
                  type="number"
                  value={calcForm.stop_loss_price || ''}
                  onChange={(e) => setCalcForm({ ...calcForm, stop_loss_price: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. 41000"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Confidence Score</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={calcForm.confidence_score}
                  onChange={(e) => setCalcForm({ ...calcForm, confidence_score: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="0–100 (default 70)"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Direction</label>
                <select
                  value={calcForm.signal_type}
                  onChange={(e) => setCalcForm({ ...calcForm, signal_type: e.target.value as 'LONG' | 'SHORT' })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="LONG">LONG</option>
                  <option value="SHORT">SHORT</option>
                </select>
              </div>
            </div>

            {calcError && (
              <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg p-2.5">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                {calcError}
              </div>
            )}

            <button
              onClick={handleCalc}
              disabled={calcLoading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-50"
            >
              {calcLoading ? 'Calculating...' : 'Calculate Position Size'}
            </button>
          </div>

          {/* Calculation Result */}
          {calcResult && (
            <div className="mt-4 bg-blue-50 rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide mb-2">Result</p>
              {Object.entries(calcResult).map(([key, val]) => (
                <div key={key} className="flex justify-between text-sm">
                  <span className="text-gray-600 capitalize">{key.replace(/_/g, ' ')}</span>
                  <span className="font-semibold text-gray-900">
                    {typeof val === 'number' ? val.toFixed(4) : String(val)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Portfolio Exposure */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <PieChart className="w-5 h-5 text-purple-600" />
            <h2 className="font-bold text-gray-900">Portfolio Exposure</h2>
          </div>

          {portfolioLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : portfolio ? (
            <div className="space-y-3">
              {typeof portfolio.open_signals === 'number' && (
                <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <span className="text-sm text-gray-600">Open Signals</span>
                  <span className="font-bold text-gray-900">{portfolio.open_signals as number}</span>
                </div>
              )}
              {typeof portfolio.long_count === 'number' && typeof portfolio.short_count === 'number' && (
                <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <span className="text-sm text-gray-600">Long / Short</span>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-sm font-bold text-emerald-600">
                      <TrendingUp className="w-3.5 h-3.5" />
                      {portfolio.long_count as number}
                    </span>
                    <span className="text-gray-400">/</span>
                    <span className="flex items-center gap-1 text-sm font-bold text-red-600">
                      <TrendingDown className="w-3.5 h-3.5" />
                      {portfolio.short_count as number}
                    </span>
                  </div>
                </div>
              )}
              {typeof portfolio.total_risk_pct === 'number' && (
                <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <span className="text-sm text-gray-600">Total Risk Exposure</span>
                  <span className={`font-bold text-sm ${(portfolio.total_risk_pct as number) > 5 ? 'text-red-600' : 'text-gray-900'}`}>
                    {(portfolio.total_risk_pct as number).toFixed(1)}%
                  </span>
                </div>
              )}
              {typeof portfolio.risk_level === 'string' && (
                <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <span className="text-sm text-gray-600">Risk Level</span>
                  <span className={`px-2.5 py-0.5 text-xs font-bold rounded-full ${
                    portfolio.risk_level === 'HIGH'
                      ? 'bg-red-100 text-red-700'
                      : portfolio.risk_level === 'MEDIUM'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    {portfolio.risk_level as string}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-500 text-center py-6">No portfolio data available</p>
          )}
        </div>
      </div>

      {/* Risk Settings */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Settings className="w-5 h-5 text-gray-600" />
          <h2 className="font-bold text-gray-900">Risk Settings</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Account Balance (USD)</label>
            <input
              type="number"
              value={settings.balance ?? ''}
              onChange={(e) => setSettings({ ...settings, balance: Number(e.target.value) })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Risk Per Trade (%)</label>
            <input
              type="number"
              step="0.1"
              min="0.1"
              max="10"
              value={settings.risk_pct ?? ''}
              onChange={(e) => setSettings({ ...settings, risk_pct: Number(e.target.value) })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Max Concurrent Trades</label>
            <input
              type="number"
              min="1"
              max="20"
              value={settings.max_trades ?? ''}
              onChange={(e) => setSettings({ ...settings, max_trades: Number(e.target.value) })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSaveSettings}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            Save Settings
          </button>
          {settingsSaved && (
            <span className="text-sm text-emerald-600 font-medium">✓ Settings saved</span>
          )}
        </div>
      </div>
    </div>
  )
}
