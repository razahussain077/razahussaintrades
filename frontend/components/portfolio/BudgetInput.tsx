'use client'

import { useEffect, useState } from 'react'
import { getPortfolioSettings, savePortfolioSettings } from '@/lib/api'
import type { PortfolioSettings } from '@/lib/types'
import { DollarSign } from 'lucide-react'

const STORAGE_KEY = 'smc_budget'

export function BudgetInput() {
  const [budget, setBudget] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    // Load from localStorage first for instant display
    const local = localStorage.getItem(STORAGE_KEY)
    if (local) setBudget(local)

    // Then try server
    getPortfolioSettings()
      .then((s: PortfolioSettings) => {
        if (s.budget > 0) {
          const val = s.budget.toString()
          setBudget(val)
          localStorage.setItem(STORAGE_KEY, val)
        }
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    const num = parseFloat(budget.replace(/,/g, ''))
    if (isNaN(num) || num <= 0) return

    setSaving(true)
    try {
      const existing = await getPortfolioSettings().catch(() => ({
        budget: 0,
        risk_tolerance: 1.5,
        preferred_timeframes: ['1H', '4H'],
        preferred_exchanges: ['Binance'],
        notification_enabled: false,
      } as PortfolioSettings))

      await savePortfolioSettings({ ...existing, budget: num })
      localStorage.setItem(STORAGE_KEY, num.toString())
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const formatted =
    parseFloat(budget.replace(/,/g, '')) > 0
      ? `$${parseFloat(budget.replace(/,/g, '')).toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })} USDT`
      : null

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
          <DollarSign className="w-4 h-4 text-blue-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-gray-900">Total Budget</h3>
          <p className="text-xs text-gray-500">Trading capital in USDT</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm font-medium">$</span>
          <input
            type="text"
            value={budget}
            onChange={(e) => {
              const raw = e.target.value.replace(/[^0-9.]/g, '')
              setBudget(raw)
              setSaved(false)
            }}
            onKeyDown={(e) => e.key === 'Enter' && void handleSave()}
            placeholder="0.00"
            className="w-full pl-7 pr-16 py-3 border border-gray-200 rounded-lg text-lg font-semibold text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">USDT</span>
        </div>

        {formatted && (
          <p className="text-sm text-gray-500">≈ {formatted}</p>
        )}

        <button
          onClick={handleSave}
          disabled={saving || !budget}
          className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors ${
            saved
              ? 'bg-emerald-500 text-white'
              : 'bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed'
          }`}
        >
          {saved ? '✓ Saved' : saving ? 'Saving...' : 'Save Budget'}
        </button>
      </div>
    </div>
  )
}
