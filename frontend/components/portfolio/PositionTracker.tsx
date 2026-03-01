'use client'

import { useState, useEffect } from 'react'
import { useLivePrices } from '@/hooks/useLivePrices'
import { formatPrice, formatPercentage } from '@/lib/utils'
import { X, TrendingUp, TrendingDown } from 'lucide-react'

interface Position {
  id: string
  coin: string
  type: 'LONG' | 'SHORT'
  entry: number
  quantity: number
  leverage: number
  timestamp: string
  closed?: boolean
  closePrice?: number
}

const STORAGE_KEY = 'smc_positions'

function loadPositions(): Position[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as Position[]
  } catch {
    return []
  }
}

function savePositions(positions: Position[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(positions))
}

export function PositionTracker() {
  const [positions, setPositions] = useState<Position[]>([])
  const { prices } = useLivePrices()

  useEffect(() => {
    setPositions(loadPositions())
  }, [])

  const openPositions = positions.filter((p) => !p.closed)
  const closedPositions = positions.filter((p) => p.closed)

  const handleClose = (id: string) => {
    setPositions((prev) => {
      const updated = prev.map((p) => {
        if (p.id !== id) return p
        const currentPrice = prices[p.coin] ?? prices[`${p.coin}USDT`] ?? p.entry
        return { ...p, closed: true, closePrice: currentPrice }
      })
      savePositions(updated)
      return updated
    })
  }

  const getPnl = (position: Position) => {
    const currentPrice = position.closed
      ? (position.closePrice ?? position.entry)
      : (prices[position.coin] ?? prices[`${position.coin}USDT`] ?? position.entry)

    const priceDiff = currentPrice - position.entry
    const pnlPct =
      (priceDiff / position.entry) *
      position.leverage *
      (position.type === 'SHORT' ? -1 : 1) *
      100
    const pnlUsdt = (position.quantity * pnlPct) / 100
    return { pnlPct, pnlUsdt, currentPrice }
  }

  if (positions.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-bold text-gray-900 mb-4">Position Tracker</h3>
        <div className="py-12 text-center text-sm text-gray-400">
          No positions tracked yet.{' '}
          <span className="text-gray-500">Take a signal to start tracking.</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="text-sm font-bold text-gray-900">Position Tracker</h3>
        <p className="text-xs text-gray-500 mt-0.5">
          {openPositions.length} open · {closedPositions.length} closed
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px]">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th scope="col" className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Coin</th>
              <th scope="col" className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Type</th>
              <th scope="col" className="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Entry</th>
              <th scope="col" className="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Current</th>
              <th scope="col" className="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase">P&amp;L</th>
              <th scope="col" className="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Lev.</th>
              <th scope="col" className="px-4 py-2 text-center text-xs font-semibold text-gray-500 uppercase">Status</th>
              <th scope="col" className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {[...openPositions, ...closedPositions].map((pos) => {
              const { pnlPct, pnlUsdt, currentPrice } = getPnl(pos)
              const positive = pnlPct >= 0
              return (
                <tr key={pos.id} className={pos.closed ? 'opacity-60' : 'hover:bg-gray-50'}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {pos.type === 'LONG' ? (
                        <TrendingUp className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <TrendingDown className="w-4 h-4 text-red-500" />
                      )}
                      <span className="text-sm font-semibold text-gray-900">{pos.coin}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        pos.type === 'LONG'
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {pos.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-gray-600">
                    {formatPrice(pos.entry)}
                  </td>
                  <td className="px-4 py-3 text-right text-sm font-medium text-gray-900">
                    {formatPrice(currentPrice)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className={`text-sm font-bold ${positive ? 'text-emerald-600' : 'text-red-600'}`}>
                      {formatPercentage(pnlPct)}
                    </div>
                    <div className={`text-xs ${positive ? 'text-emerald-500' : 'text-red-500'}`}>
                      {positive ? '+' : ''}{pnlUsdt.toFixed(2)} USDT
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-gray-600">
                    {pos.leverage}x
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        pos.closed
                          ? 'bg-gray-100 text-gray-500'
                          : 'bg-blue-100 text-blue-700'
                      }`}
                    >
                      {pos.closed ? 'Closed' : 'Open'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {!pos.closed && (
                      <button
                        onClick={() => handleClose(pos.id)}
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                        title="Close position"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
