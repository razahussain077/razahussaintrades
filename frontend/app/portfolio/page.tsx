import { BudgetInput } from '@/components/portfolio/BudgetInput'
import { RiskMeter } from '@/components/portfolio/RiskMeter'
import { PositionTracker } from '@/components/portfolio/PositionTracker'
import { LeverageDisplay } from '@/components/portfolio/LeverageDisplay'

export default function PortfolioPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Portfolio</h1>
        <p className="text-sm text-gray-500 mt-1">
          Track positions, manage risk and monitor leverage
        </p>
      </div>

      {/* Budget + Risk row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <BudgetInput />
        <RiskMeter />
      </div>

      {/* Leverage display */}
      <LeverageDisplay />

      {/* Position tracker */}
      <PositionTracker />
    </div>
  )
}
