import { MarketOverview } from '@/components/dashboard/MarketOverview'
import { CoinTable } from '@/components/dashboard/CoinTable'
import { ActiveSignals } from '@/components/dashboard/ActiveSignals'
import { TopMovers } from '@/components/dashboard/TopMovers'
import { ActiveSignalsPanel } from '@/components/phase3/ActiveSignalsPanel'
import { MLStatsPanel } from '@/components/phase3/MLStatsPanel'

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Market Maker Signal Bot
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Real-time SMC signals · Liquidation heatmaps · Funding rate engine · AI confidence
        </p>
      </div>

      {/* Market overview row */}
      <MarketOverview />

      {/* Main 3-column layout */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Signals — takes 2 cols */}
        <div className="xl:col-span-2 space-y-6">
          <ActiveSignals />
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          <ActiveSignalsPanel />
          <MLStatsPanel />
          <TopMovers />
        </div>
      </div>

      {/* Full coin table */}
      <CoinTable />
    </div>
  )
}
