import { MarketOverview } from '@/components/dashboard/MarketOverview'
import { CoinTable } from '@/components/dashboard/CoinTable'
import { ActiveSignals } from '@/components/dashboard/ActiveSignals'
import { TopMovers } from '@/components/dashboard/TopMovers'

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Smart Money Crypto Signal Bot
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Real-time SMC signals based on order blocks, FVGs &amp; liquidity sweeps
        </p>
      </div>

      {/* Market overview row */}
      <MarketOverview />

      {/* Signals + Top movers row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <ActiveSignals />
        </div>
        <div>
          <TopMovers />
        </div>
      </div>

      {/* Full coin table */}
      <CoinTable />
    </div>
  )
}
