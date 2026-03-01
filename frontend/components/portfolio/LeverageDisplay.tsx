'use client'

import { useSignals } from '@/hooks/useSignals'
import { formatPrice } from '@/lib/utils'
import { AlertTriangle, Shield } from 'lucide-react'

export function LeverageDisplay() {
  const { signals } = useSignals()
  const active = signals.filter((s) => s.is_active)

  if (active.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-bold text-gray-900 mb-3">Leverage Overview</h3>
        <p className="text-sm text-gray-400">No active signals to display leverage for.</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="text-sm font-bold text-gray-900">Leverage Overview</h3>
        <p className="text-xs text-gray-500 mt-0.5">Recommended leverage for active signals</p>
      </div>

      <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {active.map((signal) => {
          const isHighLev = signal.recommended_leverage > 10
          const isSafe = !isHighLev

          return (
            <div
              key={signal.id}
              className={`rounded-lg border p-3 ${
                isHighLev ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-bold text-gray-900">
                    {signal.coin.toUpperCase()}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${
                      signal.signal_type === 'LONG'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {signal.signal_type}
                  </span>
                </div>
                {isSafe ? (
                  <Shield className="w-4 h-4 text-emerald-500" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-red-500" />
                )}
              </div>

              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Leverage</span>
                  <span
                    className={`font-bold ${isHighLev ? 'text-red-600' : 'text-gray-900'}`}
                  >
                    {signal.recommended_leverage}x
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Liquidation</span>
                  <span className="font-medium text-red-600">
                    {formatPrice(signal.liquidation_price)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">R:R</span>
                  <span className="font-medium text-gray-900">
                    1:{signal.risk_reward.toFixed(1)}
                  </span>
                </div>
              </div>

              {isHighLev && (
                <div className="mt-2 flex items-start gap-1 text-xs text-red-600">
                  <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                  High leverage – increased liquidation risk
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
