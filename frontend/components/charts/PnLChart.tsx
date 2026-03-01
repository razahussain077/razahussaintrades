'use client'

interface PnLEntry {
  date: string
  pnl: number
  win: boolean
}

interface PnLChartProps {
  entries?: PnLEntry[]
}

export function PnLChart({ entries = [] }: PnLChartProps) {
  if (entries.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="text-sm font-bold text-gray-900 mb-2">Cumulative P&amp;L</h3>
        <div className="h-40 flex items-center justify-center text-sm text-gray-400">
          No trade history yet
        </div>
      </div>
    )
  }

  // Build cumulative PnL
  let cumulative = 0
  const points = entries.map((e, i) => {
    cumulative += e.pnl
    return { x: i, y: cumulative, win: e.win, date: e.date, pnl: e.pnl }
  })

  const minY = Math.min(0, ...points.map((p) => p.y))
  const maxY = Math.max(0, ...points.map((p) => p.y))
  const rangeY = maxY - minY || 1
  const width = 600
  const height = 180
  const padX = 10
  const padY = 20

  const toSvgX = (i: number) =>
    padX + (i / Math.max(1, points.length - 1)) * (width - 2 * padX)

  const toSvgY = (y: number) =>
    padY + ((maxY - y) / rangeY) * (height - 2 * padY)

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(i)} ${toSvgY(p.y)}`)
    .join(' ')

  const zeroY = toSvgY(0)
  const finalPnl = points[points.length - 1]?.y ?? 0
  const wins = entries.filter((e) => e.win).length
  const losses = entries.length - wins
  const winRate = Math.round((wins / entries.length) * 100)

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-gray-900">Cumulative P&amp;L</h3>
          <p className="text-xs text-gray-500 mt-0.5">{entries.length} trades</p>
        </div>
        <div className="text-right">
          <p className={`text-lg font-bold ${finalPnl >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            {finalPnl >= 0 ? '+' : ''}{finalPnl.toFixed(2)} USDT
          </p>
          <p className="text-xs text-gray-500">
            {wins}W / {losses}L · {winRate}% WR
          </p>
        </div>
      </div>

      {/* SVG chart */}
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          style={{ minWidth: 300 }}
        >
          {/* Zero line */}
          <line
            x1={padX}
            y1={zeroY}
            x2={width - padX}
            y2={zeroY}
            stroke="#e5e7eb"
            strokeWidth="1"
            strokeDasharray="4 4"
          />

          {/* Area fill */}
          <path
            d={`${pathD} L ${toSvgX(points.length - 1)} ${zeroY} L ${toSvgX(0)} ${zeroY} Z`}
            fill={finalPnl >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)'}
          />

          {/* Line */}
          <path
            d={pathD}
            fill="none"
            stroke={finalPnl >= 0 ? '#10b981' : '#ef4444'}
            strokeWidth="2"
            strokeLinejoin="round"
          />

          {/* Data points */}
          {points.map((p, i) => (
            <circle
              key={i}
              cx={toSvgX(i)}
              cy={toSvgY(p.y)}
              r="3"
              fill={p.win ? '#10b981' : '#ef4444'}
            />
          ))}
        </svg>
      </div>

      {/* Win/loss breakdown */}
      <div className="flex gap-4 mt-3 pt-3 border-t border-gray-100 text-sm">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span className="text-gray-600">{wins} Wins</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
          <span className="text-gray-600">{losses} Losses</span>
        </div>
        <div className="ml-auto text-gray-500">Win rate: <strong className="text-gray-900">{winRate}%</strong></div>
      </div>
    </div>
  )
}
