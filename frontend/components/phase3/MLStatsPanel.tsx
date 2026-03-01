'use client'

import { useEffect, useState } from 'react'
import { fetchMLStats } from '@/lib/api'
import type { MLStats } from '@/lib/types'
import { Brain, TrendingUp, Database, Clock } from 'lucide-react'

export function MLStatsPanel() {
  const [stats, setStats] = useState<MLStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchMLStats().then(setStats).catch(() => null).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="h-20 animate-pulse bg-gray-100 rounded-lg" />
      </div>
    )
  }

  if (!stats) return null

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Brain className="w-5 h-5 text-purple-600" />
        <h3 className="font-bold text-gray-900">ML Model</h3>
        {stats.active ? (
          <span className="px-1.5 py-0.5 text-xs font-bold bg-emerald-100 text-emerald-700 rounded-full">Active</span>
        ) : (
          <span className="px-1.5 py-0.5 text-xs font-bold bg-gray-100 text-gray-600 rounded-full">
            Training ({stats.buffered_samples}/{stats.min_samples_needed})
          </span>
        )}
      </div>

      {stats.active ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-purple-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">Accuracy</p>
            <p className="text-lg font-bold text-purple-700">{stats.accuracy}%</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">Trained On</p>
            <p className="text-lg font-bold text-gray-900">{stats.total_samples}</p>
            <p className="text-xs text-gray-400">signals</p>
          </div>
          {stats.last_trained && (
            <div className="col-span-2 flex items-center gap-1.5 text-xs text-gray-400">
              <Clock className="w-3 h-3" />
              Last trained: {new Date(stats.last_trained).toLocaleDateString()}
            </div>
          )}
          {Object.keys(stats.feature_importance).length > 0 && (
            <div className="col-span-2">
              <p className="text-xs text-gray-500 mb-2">Top Features</p>
              {Object.entries(stats.feature_importance)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 3)
                .map(([name, pct]) => (
                  <div key={name} className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-gray-600 w-28">{name}</span>
                    <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                      <div className="bg-purple-400 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-xs text-gray-500 w-8">{pct}%</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-sm text-gray-500">
          <p>Collecting training data...</p>
          <div className="mt-2 bg-gray-200 rounded-full h-2">
            <div
              className="bg-purple-400 h-2 rounded-full"
              style={{ width: `${(stats.buffered_samples / stats.min_samples_needed) * 100}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {stats.samples_until_active} more signals needed to activate ML
          </p>
        </div>
      )}
    </div>
  )
}
