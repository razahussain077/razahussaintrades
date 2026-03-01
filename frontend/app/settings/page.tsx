import { RiskSettings } from '@/components/settings/RiskSettings'
import { TimeframeSelector } from '@/components/settings/TimeframeSelector'
import { NotificationSettings } from '@/components/settings/NotificationSettings'

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">
          Configure risk tolerance, preferred timeframes and notifications
        </p>
      </div>

      <RiskSettings />
      <TimeframeSelector />
      <NotificationSettings />
    </div>
  )
}
