'use client'

import { useEffect, useState } from 'react'
import { getPortfolioSettings } from '@/lib/api'
import type { PortfolioSettings } from '@/lib/types'

interface RiskLevel {
  label: string
  color: string
  textColor: string
  bg: string
}

function getRiskLevel(pct: number): RiskLevel {
  if (pct < 3) return { label: 'Low Risk', color: '#10b981', textColor: 'text-emerald-600', bg: 'bg-emerald-100' }
  if (pct <= 5) return { label: 'Moderate Risk', color: '#f59e0b', textColor: 'text-amber-600', bg: 'bg-amber-100' }
  return { label: 'High Risk', color: '#ef4444', textColor: 'text-red-600', bg: 'bg-red-100' }
}

export function RiskMeter() {
  const [risk, setRisk] = useState(1.5)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getPortfolioSettings()
      .then((s: PortfolioSettings) => setRisk(s.risk_tolerance))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const level = getRiskLevel(risk)

  // SVG arc gauge
  const size = 180
  const cx = size / 2
  const cy = size / 2
  const r = 70
  const strokeWidth = 14
  const startAngle = -210
  const endAngle = 30
  const totalAngle = endAngle - startAngle // 240 degrees

  const toRad = (deg: number) => (deg * Math.PI) / 180
  const describeArc = (start: number, end: number) => {
    const s = toRad(start)
    const e = toRad(end)
    const x1 = cx + r * Math.cos(s)
    const y1 = cy + r * Math.sin(s)
    const x2 = cx + r * Math.cos(e)
    const y2 = cy + r * Math.sin(e)
    const largeArc = end - start > 180 ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`
  }

  // Clamp risk percentage for display (0-10% range)
  const riskPct = Math.min(Math.max(risk, 0), 10)
  const fillFraction = riskPct / 10
  const fillAngle = startAngle + fillFraction * totalAngle

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="mb-2">
        <h3 className="text-sm font-bold text-gray-900">Risk Meter</h3>
        <p className="text-xs text-gray-500 mt-0.5">Per-trade risk tolerance</p>
      </div>

      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="flex flex-col items-center">
          {/* Gauge SVG */}
          <svg width={size} height={size * 0.7} viewBox={`0 0 ${size} ${size}`}>
            {/* Track */}
            <path
              d={describeArc(startAngle, endAngle)}
              fill="none"
              stroke="#f1f5f9"
              strokeWidth={strokeWidth}
              strokeLinecap="round"
            />
            {/* Fill */}
            <path
              d={describeArc(startAngle, fillAngle)}
              fill="none"
              stroke={level.color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
            />
            {/* Center label */}
            <text
              x={cx}
              y={cy - 5}
              textAnchor="middle"
              className="text-2xl font-bold"
              fill="#111827"
              fontSize="26"
              fontWeight="bold"
            >
              {risk.toFixed(1)}%
            </text>
            <text
              x={cx}
              y={cy + 18}
              textAnchor="middle"
              fill="#6b7280"
              fontSize="11"
            >
              risk/trade
            </text>
          </svg>

          {/* Level badge */}
          <span className={`mt-1 px-3 py-1 rounded-full text-sm font-semibold ${level.bg} ${level.textColor}`}>
            {level.label}
          </span>

          {/* Scale */}
          <div className="w-full flex justify-between text-xs text-gray-400 mt-3 px-2">
            <span>0%</span>
            <span>5%</span>
            <span>10%</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-500 mt-1" />
        </div>
      )}
    </div>
  )
}
