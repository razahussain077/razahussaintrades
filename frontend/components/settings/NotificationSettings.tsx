'use client'

import { useEffect, useState } from 'react'
import { getPortfolioSettings, savePortfolioSettings } from '@/lib/api'
import type { PortfolioSettings } from '@/lib/types'
import { Bell, BellOff, CheckCircle } from 'lucide-react'

type NotifyEvent = 'new_signal' | 'signal_invalidated' | 'kill_zone_start'

interface NotifyPrefs {
  new_signal: boolean
  signal_invalidated: boolean
  kill_zone_start: boolean
}

const NOTIFY_PREFS_KEY = 'smc_notify_prefs'

const EVENT_LABELS: Record<NotifyEvent, { label: string; desc: string }> = {
  new_signal: { label: 'New Signal', desc: 'When a new trading signal is generated' },
  signal_invalidated: { label: 'Signal Invalidated', desc: 'When an active signal is invalidated' },
  kill_zone_start: { label: 'Kill Zone Start', desc: 'When a trading session begins' },
}

export function NotificationSettings() {
  const [enabled, setEnabled] = useState(false)
  const [permission, setPermission] = useState<NotificationPermission>('default')
  const [prefs, setPrefs] = useState<NotifyPrefs>({
    new_signal: true,
    signal_invalidated: true,
    kill_zone_start: false,
  })
  const [settings, setSettings] = useState<PortfolioSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      setPermission(Notification.permission)
    }

    try {
      const stored = localStorage.getItem(NOTIFY_PREFS_KEY)
      if (stored) setPrefs(JSON.parse(stored) as NotifyPrefs)
    } catch {}

    getPortfolioSettings()
      .then((s) => {
        setSettings(s)
        setEnabled(s.notification_enabled)
      })
      .catch(() => {})
  }, [])

  const requestPermission = async () => {
    if (!('Notification' in window)) return
    const result = await Notification.requestPermission()
    setPermission(result)
    if (result === 'granted') {
      setEnabled(true)
      await persistEnabled(true)
    }
  }

  const persistEnabled = async (val: boolean) => {
    if (!settings) return
    setSaving(true)
    try {
      const updated = { ...settings, notification_enabled: val }
      await savePortfolioSettings(updated)
      setSettings(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = async () => {
    const next = !enabled
    setEnabled(next)
    await persistEnabled(next)
  }

  const togglePref = (event: NotifyEvent) => {
    const updated = { ...prefs, [event]: !prefs[event] }
    setPrefs(updated)
    localStorage.setItem(NOTIFY_PREFS_KEY, JSON.stringify(updated))
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-5">
        <div className="w-8 h-8 bg-amber-50 rounded-lg flex items-center justify-center">
          <Bell className="w-4 h-4 text-amber-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-gray-900">Notification Settings</h3>
          <p className="text-xs text-gray-500">Browser push notifications</p>
        </div>
        {saved && (
          <span className="ml-auto text-xs text-emerald-600 font-medium">✓ Saved</span>
        )}
      </div>

      <div className="space-y-4">
        {/* Permission status */}
        {permission !== 'granted' ? (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <BellOff className="w-4 h-4 text-amber-600 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-amber-800">Notifications not enabled</p>
                <p className="text-xs text-amber-600 mt-0.5">
                  {permission === 'denied'
                    ? 'Notifications are blocked. Please enable in browser settings.'
                    : 'Allow browser notifications to receive trading alerts.'}
                </p>
              </div>
            </div>
            {permission !== 'denied' && (
              <button
                onClick={requestPermission}
                className="flex-shrink-0 px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                Enable
              </button>
            )}
          </div>
        ) : (
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-600" />
            <p className="text-sm text-emerald-700 font-medium">
              Browser notifications are enabled
            </p>
          </div>
        )}

        {/* Master toggle */}
        <div className="flex items-center justify-between py-2 border-b border-gray-100">
          <div>
            <p className="text-sm font-semibold text-gray-900">Enable Notifications</p>
            <p className="text-xs text-gray-500 mt-0.5">Receive alerts for trading events</p>
          </div>
          <button
            onClick={() => void toggleEnabled()}
            disabled={saving || permission !== 'granted'}
            className={`relative w-11 h-6 rounded-full transition-colors disabled:opacity-50 ${
              enabled && permission === 'granted' ? 'bg-blue-600' : 'bg-gray-200'
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                enabled && permission === 'granted' ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        {/* Event toggles */}
        {enabled && permission === 'granted' && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Notify me when:</p>
            {(Object.entries(EVENT_LABELS) as [NotifyEvent, { label: string; desc: string }][]).map(
              ([event, { label, desc }]) => (
                <div key={event} className="flex items-center justify-between py-1.5">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{label}</p>
                    <p className="text-xs text-gray-500">{desc}</p>
                  </div>
                  <button
                    onClick={() => togglePref(event)}
                    className={`relative w-9 h-5 rounded-full transition-colors ${
                      prefs[event] ? 'bg-blue-600' : 'bg-gray-200'
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                        prefs[event] ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  )
}
