'use client'

interface LiquidationHeatmapProps {
  currentPrice: number
}

export function LiquidationHeatmap({ currentPrice }: LiquidationHeatmapProps) {
  const range = 0.20
  const minPrice = currentPrice * (1 - range)
  const maxPrice = currentPrice * (1 + range)
  const priceRange = maxPrice - minPrice

  // Simulate liquidation density (bell curves around price levels)
  const levels = Array.from({ length: 40 }, (_, i) => {
    const price = maxPrice - (i / 39) * priceRange
    const distPct = (price - currentPrice) / currentPrice

    // Long liquidations below current price, short liquidations above
    let longDensity = 0
    let shortDensity = 0

    if (distPct < 0) {
      // Long liquidations increase as price drops (leveraged longs get liquidated)
      longDensity = Math.max(0, Math.min(1, Math.exp(distPct * 8) * 1.5))
    } else {
      // Short liquidations above current price
      shortDensity = Math.max(0, Math.min(1, Math.exp(-distPct * 8) * 1.5))
    }

    return { price, longDensity, shortDensity, distPct }
  })

  const formatP = (p: number) => {
    if (p >= 1000) return `$${(p / 1000).toFixed(1)}k`
    return `$${p.toFixed(2)}`
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-gray-900">Liquidation Heatmap</h3>
        <p className="text-xs text-gray-500 mt-0.5">Estimated liquidation density ±20% from current price</p>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mb-3 text-xs">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-emerald-400" />
          <span className="text-gray-600">Long liquidations</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-red-400" />
          <span className="text-gray-600">Short liquidations</span>
        </div>
      </div>

      {/* Heatmap */}
      <div className="flex gap-2">
        {/* Price labels */}
        <div className="flex flex-col justify-between text-right w-20 flex-shrink-0">
          {[0, 10, 20, 30, 39].map((idx) => (
            <span key={idx} className="text-xs text-gray-400 leading-none">
              {formatP(levels[idx].price)}
            </span>
          ))}
        </div>

        {/* Bars */}
        <div className="flex-1 space-y-0.5">
          {levels.map((level, i) => {
            const isCurrentPrice = Math.abs(level.distPct) < 0.005
            return (
              <div key={i} className="relative flex items-center h-4">
                {isCurrentPrice && (
                  <div className="absolute inset-0 border-t-2 border-blue-500 z-10" />
                )}
                {/* Long density (left side, green) */}
                <div className="flex-1 flex justify-end">
                  {level.longDensity > 0 && (
                    <div
                      className="h-3 rounded-l-sm"
                      style={{
                        width: `${level.longDensity * 100}%`,
                        backgroundColor: `rgba(16, 185, 129, ${0.2 + level.longDensity * 0.8})`,
                      }}
                    />
                  )}
                </div>
                {/* Divider */}
                <div className="w-px h-4 bg-gray-200 flex-shrink-0" />
                {/* Short density (right side, red) */}
                <div className="flex-1">
                  {level.shortDensity > 0 && (
                    <div
                      className="h-3 rounded-r-sm"
                      style={{
                        width: `${level.shortDensity * 100}%`,
                        backgroundColor: `rgba(239, 68, 68, ${0.2 + level.shortDensity * 0.8})`,
                      }}
                    />
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Current price marker */}
      <div className="flex items-center gap-1.5 mt-3 text-xs">
        <div className="w-4 border-t-2 border-blue-500 border-dashed" />
        <span className="text-blue-600 font-medium">Current: {formatP(currentPrice)}</span>
      </div>
    </div>
  )
}
