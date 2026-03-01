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
  Brain,
  DollarSign,
  Activity,
} from 'lucide-react'

interface EnhancedSignalCardProps {
  signal: Signal
  balance?: number
  riskPct?: number
}

export function EnhancedSignalCard({ signal, balance = 1000, riskPct = 1 }: EnhancedSignalCardProps) {
  const [taken, setTaken] = useState(signal.taken ?? false)
  const [loading, setLoading] = useState(false)

  const isLong = signal.signal_type === 'LONG'
  const entry = (signal.entry_low + signal.entry_high) / 2
  const riskAmount = balance * (riskPct / 100)
  const slDistance = Math.abs(entry - signal.stop_loss)
  const positionSize = slDistance > 0 ? riskAmount / slDistance : 0
  const positionValue = positionSize * entry
  const leverage = signal.recommended_leverage

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
    signal.confidence_score >= 80 ? 'text-emerald-600' :
    signal.confidence_score >= 65 ? 'text-amber-600' :
    'text-red-600'

  const confidenceBg =
    signal.confidence_score >= 80 ? 'bg-emerald-50 border-emerald-200' :
    signal.confidence_score >= 65 ? 'bg-amber-50 border-amber-200' :
    'bg-red-50 border-red-200'

  const headerBg = isLong ? 'bg-emerald-600' : 'bg-red-600'

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden flex flex-col shadow-sm">
      {/* Header bar */}
      <div className={`${headerBg} px-4 py-3 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          {isLong ? (
            <TrendingUp className="w-4 h-4 text-white" />
          ) : (
            <TrendingDown className="w-4 h-4 text-white" />
          )}
          <span className="font-bold text-white text-base">{signal.coin}</span>
          <span className="text-xs text-white/70">{signal.timeframe}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-0.5 text-xs font-bold rounded-full bg-white/20 text-white`}>
            {signal.signal_type}
          </span>
          {signal.regime_emoji && (
            <span className="text-sm" title={`Regime: ${signal.regime}`}>{signal.regime_emoji}</span>
          )}
        </div>
      </div>

      <div className="p-4 flex-1 space-y-3">
        {/* Confidence Row */}
        <div className="flex items-center justify-between">
          <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border text-sm font-bold ${confidenceBg} ${confidenceColor}`}>
            <Zap className="w-3.5 h-3.5" />
            {signal.confidence_score}% Conf
          </div>
          {signal.ml_confidence != null && (
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border bg-purple-50 border-purple-200 text-xs font-bold text-purple-700">
              <Brain className="w-3.5 h-3.5" />
              🧠 ML: {signal.ml_confidence}%
            </div>
          )}
          <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
            {signal.setup_type?.split(' ').slice(0, 2).join(' ')}
          </span>
        </div>

        {/* Entry Zone (Scale-In) */}
        {signal.entries && signal.entries.length > 0 ? (
          <div className={`rounded-lg p-3 space-y-1.5 text-xs border ${isLong ? 'bg-emerald-50 border-emerald-100' : 'bg-red-50 border-red-100'}`}>
            <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">ENTRY ZONE</p>
            {signal.entries.map((e, i) => (
              <div key={i} className="flex justify-between items-center">
                <span className="text-gray-600">{e.level_name.split('—')[0].trim()}</span>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-gray-900">{formatPrice(e.price)}</span>
                  <span className="text-gray-400">({e.allocation_pct}%)</span>
                </div>
              </div>
            ))}
            {signal.weighted_average_entry && (
              <div className="flex justify-between items-center pt-1 border-t border-gray-200 mt-1">
                <span className="font-semibold text-gray-700">Avg Entry</span>
                <span className="font-bold text-gray-900">{formatPrice(signal.weighted_average_entry)}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-gray-50 rounded-lg p-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Entry Low</span>
              <span className="font-semibold">{formatPrice(signal.entry_low)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Entry High</span>
              <span className="font-semibold">{formatPrice(signal.entry_high)}</span>
            </div>
          </div>
        )}

        {/* SL + TPs */}
        <div className="space-y-1 text-sm">
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
            { label: 'TP 1', price: signal.take_profit_1, pct: signal.take_profit_1_pct, rr: (signal.take_profit_1_pct / (signal.stop_loss_pct || 1)).toFixed(1) },
            { label: 'TP 2', price: signal.take_profit_2, pct: signal.take_profit_2_pct, rr: (signal.take_profit_2_pct / (signal.stop_loss_pct || 1)).toFixed(1) },
            { label: 'TP 3', price: signal.take_profit_3, pct: signal.take_profit_3_pct, rr: (signal.take_profit_3_pct / (signal.stop_loss_pct || 1)).toFixed(1) },
          ].map(({ label, price, pct, rr }) => (
            <div key={label} className="flex justify-between items-center py-1 border-b border-gray-50">
              <div className="flex items-center gap-1.5 text-emerald-600">
                <Target className="w-3.5 h-3.5" />
                <span className="font-medium">{label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-emerald-600">{formatPrice(price)}</span>
                <span className="text-xs text-gray-400">1:{rr}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Risk Info Row */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-gray-500 mb-0.5">Leverage</p>
            <p className={`font-bold text-sm ${leverage > 10 ? 'text-red-600' : 'text-gray-900'}`}>
              {leverage}x {leverage > 10 && <AlertTriangle className="w-3 h-3 inline" />}
            </p>
          </div>
          <div className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-gray-500 mb-0.5">R:R Ratio</p>
            <p className="font-bold text-sm text-gray-900">1:{signal.risk_reward.toFixed(1)}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-gray-500 mb-0.5">Position ({riskPct}% risk)</p>
            <p className="font-bold text-sm text-gray-900">${positionValue.toFixed(0)}</p>
          </div>
          <div className="bg-red-50 rounded-lg p-2.5">
            <p className="text-gray-500 mb-0.5">Liquidation</p>
            <p className="font-bold text-sm text-red-600">{formatPrice(signal.liquidation_price)}</p>
          </div>
        </div>

        {/* Market Context Row */}
        {(signal.funding_direction || signal.liq_magnet_price || signal.regime) && (
          <div className="space-y-1 text-xs">
            {signal.regime && (
              <div className="flex justify-between">
                <span className="text-gray-500">📈 Regime</span>
                <span className="font-medium text-gray-700">{signal.regime_emoji} {signal.regime?.toUpperCase()}</span>
              </div>
            )}
            {signal.funding_direction && (
              <div className="flex justify-between">
                <span className="text-gray-500">💰 Funding</span>
                <span className="font-medium text-gray-700">{signal.funding_direction}</span>
              </div>
            )}
            {signal.liq_magnet_price && (
              <div className="flex justify-between">
                <span className="text-gray-500">🔥 Liq Magnet</span>
                <span className="font-medium text-gray-700">
                  {formatPrice(signal.liq_magnet_price)} ({signal.liq_magnet_direction})
                </span>
              </div>
            )}
          </div>
        )}

        {/* Reasoning */}
        {signal.reasoning.length > 0 && (
          <div className="bg-blue-50 rounded-lg p-3">
            <p className="text-xs font-semibold text-blue-700 mb-1.5 uppercase tracking-wide">Engine Confluence</p>
            <ul className="space-y-1">
              {signal.reasoning.slice(0, 4).map((r, i) => (
                <li key={i} className="text-xs text-blue-800 flex gap-1.5">
                  <span className="text-emerald-500 mt-0.5">✅</span>
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Event Warning */}
        {signal.event_warning && (
          <div className="flex gap-1.5 text-xs text-amber-700 bg-amber-50 rounded-lg p-2.5">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>{signal.event_warning}</span>
          </div>
        )}

        {/* Invalidation */}
        {signal.invalidation && (
          <div className="flex gap-1.5 text-xs text-red-700 bg-red-50 rounded-lg p-2.5">
            <Shield className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>{signal.invalidation}</span>
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

      {/* Take Trade Button */}
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
