'use client'

import { useEffect, useState } from 'react'
import { getPortfolioSettings, savePortfolioSettings } from '@/lib/api'
import type { PortfolioSettings } from '@/lib/types'
import { Clock } from 'lucide-react'

const ALL_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1H', '4H', '1D', '1W']

export function TimeframeSelector() {
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

  const selected = settings?.preferred_timeframes ?? []

  const toggle = async (tf: string) => {
    if (!settings) return
    const next = selected.includes(tf)
      ? selected.filter((t) => t !== tf)
      : [...selected, tf]
    const updated = { ...settings, preferred_timeframes: next }
    setSettings(updated)
    setSaving(true)
    try {
      await savePortfolioSettings(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-5">
        <div className="w-8 h-8 bg-purple-50 rounded-lg flex items-center justify-center">
          <Clock className="w-4 h-4 text-purple-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-gray-900">Preferred Timeframes</h3>
          <p className="text-xs text-gray-500">Select timeframes for signal filtering</p>
        </div>
        {saved && (
          <span className="ml-auto text-xs text-emerald-600 font-medium">✓ Saved</span>
        )}
      </div>

      {loading ? (
        <div className="flex gap-2">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-9 w-12 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {ALL_TIMEFRAMES.map((tf) => {
              const isSelected = selected.includes(tf)
              return (
                <button
                  key={tf}
                  onClick={() => void toggle(tf)}
                  disabled={saving}
                  className={`px-3 py-1.5 text-sm font-semibold rounded-lg border transition-colors ${
                    isSelected
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : 'bg-white border-gray-200 text-gray-600 hover:border-blue-300 hover:text-blue-600'
                  }`}
                >
                  {tf}
                </button>
              )
            })}
          </div>
          <p className="text-xs text-gray-500">
            {selected.length === 0
              ? 'No timeframes selected – all signals will be shown.'
              : `${selected.length} timeframe${selected.length !== 1 ? 's' : ''} selected: ${selected.join(', ')}`}
          </p>
        </div>
      )}
    </div>
  )
}
