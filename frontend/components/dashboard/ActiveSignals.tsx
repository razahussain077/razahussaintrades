'use client'

import { useSignals } from '@/hooks/useSignals'
import { SignalCard } from './SignalCard'
import { TrendingUp } from 'lucide-react'

export function ActiveSignals() {
  const { signals, isLoading } = useSignals()
  const active = signals.filter((s) => s.is_active)

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-lg font-bold text-gray-900">Active Signals</h2>
        {!isLoading && (
          <span className="px-2 py-0.5 text-xs font-bold bg-blue-100 text-blue-700 rounded-full">
            {active.length}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-80 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : active.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center bg-white rounded-xl border border-gray-200">
          <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3">
            <TrendingUp className="w-6 h-6 text-gray-400" />
          </div>
          <p className="text-sm font-semibold text-gray-600">No active signals</p>
          <p className="text-xs text-gray-400 mt-1">
            Signals will appear here when market conditions align
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {active.slice(0, 6).map((signal) => (
            <SignalCard key={signal.id} signal={signal} />
          ))}
        </div>
      )}
    </div>
  )
}
