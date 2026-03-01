'use client'

import { useState } from 'react'
import { useSignals } from '@/hooks/useSignals'
import { SignalCard } from '@/components/dashboard/SignalCard'
import { TrendingUp, TrendingDown, List } from 'lucide-react'

type Filter = 'ALL' | 'LONG' | 'SHORT'
type SortKey = 'confidence_score' | 'created_at' | 'risk_reward'

export default function SignalsPage() {
  const { signals, isLoading, refresh } = useSignals()
  const [filter, setFilter] = useState<Filter>('ALL')
  const [sortKey, setSortKey] = useState<SortKey>('confidence_score')

  const filtered = signals
    .filter((s) => s.is_active)
    .filter((s) => filter === 'ALL' || s.signal_type === filter)
    .sort((a, b) => {
      if (sortKey === 'confidence_score') return b.confidence_score - a.confidence_score
      if (sortKey === 'risk_reward') return b.risk_reward - a.risk_reward
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Active Signals</h1>
          <p className="text-sm text-gray-500 mt-1">
            {filtered.length} signal{filtered.length !== 1 ? 's' : ''} active
          </p>
        </div>
        <button
          onClick={refresh}
          className="self-start sm:self-auto px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Filters + Sort */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Type filter */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white">
          {(['ALL', 'LONG', 'SHORT'] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-1.5 ${
                filter === f
                  ? f === 'LONG'
                    ? 'bg-emerald-500 text-white'
                    : f === 'SHORT'
                    ? 'bg-red-500 text-white'
                    : 'bg-blue-600 text-white'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f === 'LONG' && <TrendingUp className="w-3.5 h-3.5" />}
              {f === 'SHORT' && <TrendingDown className="w-3.5 h-3.5" />}
              {f === 'ALL' && <List className="w-3.5 h-3.5" />}
              {f}
            </button>
          ))}
        </div>

        {/* Sort */}
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="confidence_score">Sort: Confidence</option>
          <option value="risk_reward">Sort: Risk/Reward</option>
          <option value="created_at">Sort: Newest</option>
        </select>
      </div>

      {/* Signals grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-80 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
            <TrendingUp className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-700">No signals found</h3>
          <p className="text-sm text-gray-500 mt-1">
            {filter !== 'ALL' ? `No active ${filter} signals at this time.` : 'No active signals at this time.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((signal) => (
            <SignalCard key={signal.id} signal={signal} />
          ))}
        </div>
      )}
    </div>
  )
}
