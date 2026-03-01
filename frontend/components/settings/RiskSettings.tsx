'use client'

import { useEffect, useState } from 'react'
import { getPortfolioSettings, savePortfolioSettings } from '@/lib/api'
import type { PortfolioSettings } from '@/lib/types'
import { Shield } from 'lucide-react'

const PRESETS = [
  { label: 'Conservative', value: 1.0, color: 'bg-emerald-500 hover:bg-emerald-600 text-white' },
  { label: 'Moderate', value: 1.5, color: 'bg-blue-500 hover:bg-blue-600 text-white' },
  { label: 'Aggressive', value: 2.0, color: 'bg-amber-500 hover:bg-amber-600 text-white' },
]

export function RiskSettings() {
  const [settings, setSettings] = useState<PortfolioSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getPortfolioSettings()
      .then(setSettings)
      .catch(() =>
        setSettings({
          budget: 0,
          risk_tolerance: 1.5,
          preferred_timeframes: ['1H', '4H'],
          preferred_exchanges: ['Binance'],
          notification_enabled: false,
        })
      )
      .finally(() => setLoading(false))
  }, [])

  const save = async (tolerance: number) => {
    if (!settings) return
    setSaving(true)
    try {
      const updated = { ...settings, risk_tolerance: tolerance }
      await savePortfolioSettings(updated)
      setSettings(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const currentRisk = settings?.risk_tolerance ?? 1.5
  const riskColor =
    currentRisk < 1.2
      ? 'text-emerald-600'
      : currentRisk <= 2
      ? 'text-blue-600'
      : 'text-amber-600'

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-5">
        <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
          <Shield className="w-4 h-4 text-blue-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-gray-900">Risk Settings</h3>
          <p className="text-xs text-gray-500">Risk per trade as % of total budget</p>
        </div>
        {saved && (
          <span className="ml-auto text-xs text-emerald-600 font-medium">✓ Saved</span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          <div className="h-10 bg-gray-100 rounded animate-pulse" />
          <div className="h-6 bg-gray-100 rounded animate-pulse" />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Presets */}
          <div className="flex gap-2">
            {PRESETS.map(({ label, value, color }) => (
              <button
                key={label}
                onClick={() => void save(value)}
                disabled={saving}
                className={`flex-1 py-2 text-sm font-semibold rounded-lg transition-colors ${
                  Math.abs(currentRisk - value) < 0.01
                    ? color
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {label}
                <span className="block text-xs font-normal opacity-80">{value}%</span>
              </button>
            ))}
          </div>

          {/* Custom slider */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Custom Risk</span>
              <span className={`font-bold ${riskColor}`}>{currentRisk.toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min={0.5}
              max={3}
              step={0.1}
              value={currentRisk}
              onChange={(e) => {
                const val = parseFloat(e.target.value)
                setSettings((s) => s ? { ...s, risk_tolerance: val } : s)
                setSaved(false)
              }}
              onMouseUp={() => void save(currentRisk)}
              onTouchEnd={() => void save(currentRisk)}
              className="w-full accent-blue-600"
            />
            <div className="flex justify-between text-xs text-gray-400">
              <span>0.5% (Safe)</span>
              <span>3% (Risky)</span>
            </div>
          </div>

          {/* Description */}
          <div className="bg-blue-50 rounded-lg p-3 text-xs text-blue-700">
            <strong>
              {currentRisk < 1.2
                ? 'Conservative:'
                : currentRisk <= 2
                ? 'Moderate:'
                : 'Aggressive:'}
            </strong>{' '}
            {currentRisk < 1.2
              ? 'Lower risk per trade, slower growth but safer capital preservation.'
              : currentRisk <= 2
              ? 'Balanced approach with moderate risk and consistent growth.'
              : 'Higher risk per trade, potential for faster growth but larger drawdowns.'}
          </div>
        </div>
      )}
    </div>
  )
}
