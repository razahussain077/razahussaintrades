'use client'

import { useState } from 'react'
import type { Signal } from '@/lib/types'
import { formatPrice, formatPercentage, timeAgo } from '@/lib/utils'
import { takeSignal } from '@/lib/api'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle,
  Target,
  Shield,
  Zap,
  Clock,
} from 'lucide-react'

interface SignalCardProps {
  signal: Signal
}

export function SignalCard({ signal }: SignalCardProps) {
  const [taken, setTaken] = useState(signal.taken ?? false)
  const [loading, setLoading] = useState(false)

  const isLong = signal.signal_type === 'LONG'

  const handleTake = async () => {
    if (taken || loading) return
    setLoading(true)
    try {
      await takeSignal(signal.id)
      setTaken(true)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const confidenceColor =
    signal.confidence_score >= 75
      ? 'text-emerald-600'
      : signal.confidence_score >= 50
      ? 'text-amber-600'
      : 'text-red-600'

  const confidenceBg =
    signal.confidence_score >= 75
      ? 'bg-emerald-50 border-emerald-200'
      : signal.confidence_score >= 50
      ? 'bg-amber-50 border-amber-200'
      : 'bg-red-50 border-red-200'

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden flex flex-col">
      {/* Header */}
      <div
        className={`flex items-center justify-between px-4 py-3 border-b ${
          isLong ? 'bg-emerald-50 border-emerald-100' : 'bg-red-50 border-red-100'
        }`}
      >
        <div className="flex items-center gap-2">
          {isLong ? (
            <TrendingUp className="w-4 h-4 text-emerald-600" />
          ) : (
            <TrendingDown className="w-4 h-4 text-red-600" />
          )}
          <span className="font-bold text-gray-900 text-base">{signal.coin.toUpperCase()}</span>
          <span className="text-xs text-gray-500">{signal.exchange}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2.5 py-0.5 text-xs font-bold rounded-full ${
              isLong ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'
            }`}
          >
            {signal.signal_type}
          </span>
          <span className="text-xs text-gray-400">{signal.timeframe}</span>
        </div>
      </div>

      {/* Body */}
      <div className="p-4 flex-1 space-y-3">
        {/* Confidence + Setup */}
        <div className="flex items-center justify-between">
          <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border text-sm font-bold ${confidenceBg} ${confidenceColor}`}>
            <Zap className="w-3.5 h-3.5" />
            {signal.confidence_score}% Confidence
          </div>
          <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-lg">
            {signal.setup_type}
          </span>
        </div>

        {/* Entry Zone */}
        <div className="bg-gray-50 rounded-lg p-3 space-y-2 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-gray-500 text-xs font-medium uppercase tracking-wide">Entry Zone</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Low</span>
            <span className="font-semibold text-gray-900">{formatPrice(signal.entry_low)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">High</span>
            <span className="font-semibold text-gray-900">{formatPrice(signal.entry_high)}</span>
          </div>
        </div>

        {/* SL + TPs */}
        <div className="space-y-1.5 text-sm">
          <div className="flex justify-between items-center py-1 border-b border-gray-100">
            <div className="flex items-center gap-1.5 text-red-600">
              <Shield className="w-3.5 h-3.5" />
              <span className="font-medium">Stop Loss</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-red-600">{formatPrice(signal.stop_loss)}</span>
              <span className="text-xs text-gray-400">{formatPercentage(-Math.abs(signal.stop_loss_pct))}</span>
            </div>
          </div>

          {[
            { label: 'TP 1', price: signal.take_profit_1, pct: signal.take_profit_1_pct },
            { label: 'TP 2', price: signal.take_profit_2, pct: signal.take_profit_2_pct },
            { label: 'TP 3', price: signal.take_profit_3, pct: signal.take_profit_3_pct },
          ].map(({ label, price, pct }) => (
            <div key={label} className="flex justify-between items-center py-1 border-b border-gray-50">
              <div className="flex items-center gap-1.5 text-emerald-600">
                <Target className="w-3.5 h-3.5" />
                <span className="font-medium">{label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-emerald-600">{formatPrice(price)}</span>
                <span className="text-xs text-gray-400">+{pct.toFixed(1)}%</span>
              </div>
            </div>
          ))}
        </div>

        {/* Leverage + R:R */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-xs text-gray-500 mb-0.5">Leverage</p>
            <p className={`font-bold ${signal.recommended_leverage > 10 ? 'text-red-600' : 'text-gray-900'}`}>
              {signal.recommended_leverage}x
              {signal.recommended_leverage > 10 && (
                <AlertTriangle className="w-3.5 h-3.5 inline ml-1" />
              )}
            </p>
          </div>
          <div className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-xs text-gray-500 mb-0.5">Risk / Reward</p>
            <p className="font-bold text-gray-900">1 : {signal.risk_reward.toFixed(1)}</p>
          </div>
        </div>

        {/* Liquidation price */}
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Liquidation Price</span>
          <span className="font-medium text-red-600">{formatPrice(signal.liquidation_price)}</span>
        </div>

        {/* Reasoning */}
        {signal.reasoning.length > 0 && (
          <div className="bg-blue-50 rounded-lg p-3">
            <p className="text-xs font-semibold text-blue-700 mb-1.5 uppercase tracking-wide">Analysis</p>
            <ul className="space-y-1">
              {signal.reasoning.slice(0, 3).map((r, i) => (
                <li key={i} className="text-xs text-blue-800 flex gap-1.5">
                  <span className="text-blue-400 mt-0.5">•</span>
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Invalidation */}
        {signal.invalidation && (
          <div className="flex gap-1.5 text-xs text-amber-700 bg-amber-50 rounded-lg p-2.5">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span><strong>Invalidation:</strong> {signal.invalidation}</span>
          </div>
        )}

        {/* Kill zone + time */}
        <div className="flex items-center justify-between text-xs text-gray-400">
          <div className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {signal.kill_zone}
          </div>
          <span>{timeAgo(signal.created_at)}</span>
        </div>
      </div>

      {/* Footer: Take trade button */}
      <div className="px-4 pb-4">
        <button
          onClick={handleTake}
          disabled={taken || loading}
          className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors ${
            taken
              ? 'bg-gray-100 text-gray-500 cursor-not-allowed'
              : isLong
              ? 'bg-emerald-500 hover:bg-emerald-600 text-white'
              : 'bg-red-500 hover:bg-red-600 text-white'
          }`}
        >
          {taken ? (
            <span className="flex items-center justify-center gap-1.5">
              <CheckCircle className="w-4 h-4" />
              Trade Taken
            </span>
          ) : loading ? (
            'Processing...'
          ) : (
            `Take ${signal.signal_type} Trade`
          )}
        </button>
      </div>
    </div>
  )
}
