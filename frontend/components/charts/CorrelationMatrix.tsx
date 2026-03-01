'use client'

import { useEffect, useState } from 'react'
import { fetchCorrelationMatrix } from '@/lib/api'

export function CorrelationMatrix() {
  const [data, setData] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCorrelationMatrix()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const getColor = (val: number): string => {
    if (val >= 0.7) return 'bg-emerald-500 text-white'
    if (val >= 0.4) return 'bg-emerald-200 text-emerald-800'
    if (val >= 0.1) return 'bg-emerald-100 text-emerald-700'
    if (val >= -0.1) return 'bg-gray-100 text-gray-600'
    if (val >= -0.4) return 'bg-red-100 text-red-700'
    if (val >= -0.7) return 'bg-red-200 text-red-800'
    return 'bg-red-500 text-white'
  }

  const pairs = Object.entries(data)

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="h-5 w-48 bg-gray-100 rounded animate-pulse mb-3" />
        <div className="grid grid-cols-4 gap-1">
          {[...Array(16)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (pairs.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="text-sm font-bold text-gray-900 mb-2">BTC Correlation Matrix</h3>
        <p className="text-sm text-gray-500">Correlation data unavailable</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-gray-900">BTC Correlation Matrix</h3>
        <p className="text-xs text-gray-500 mt-0.5">30-day price correlation with Bitcoin</p>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-2 mb-4 flex-wrap text-xs">
        {[
          { label: 'Strong +', cls: 'bg-emerald-500 text-white' },
          { label: 'Moderate +', cls: 'bg-emerald-200 text-emerald-800' },
          { label: 'Neutral', cls: 'bg-gray-100 text-gray-600' },
          { label: 'Moderate –', cls: 'bg-red-200 text-red-800' },
          { label: 'Strong –', cls: 'bg-red-500 text-white' },
        ].map(({ label, cls }) => (
          <div key={label} className="flex items-center gap-1">
            <div className={`w-4 h-4 rounded text-xs flex items-center justify-center ${cls}`} />
            <span className="text-gray-500">{label}</span>
          </div>
        ))}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
        {pairs.map(([symbol, corr]) => (
          <div
            key={symbol}
            className={`rounded-lg p-2.5 text-center ${getColor(corr)}`}
          >
            <p className="text-xs font-bold truncate">{symbol.replace('USDT', '')}</p>
            <p className="text-sm font-bold mt-0.5">{corr.toFixed(2)}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
