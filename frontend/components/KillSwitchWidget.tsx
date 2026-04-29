'use client'

import { useEffect, useState } from 'react'
import { fetchNotificationsStatus, sendTelegramTest, setKillSwitch } from '@/lib/api'
import type { NotificationsStatus } from '@/lib/api'
import { ShieldAlert, ShieldCheck, Send } from 'lucide-react'

export function KillSwitchWidget() {
  const [status, setStatus] = useState<NotificationsStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  const refresh = async () => {
    try {
      const s = await fetchNotificationsStatus()
      setStatus(s)
    } catch {
      // silent
    }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 15000)
    return () => clearInterval(t)
  }, [])

  if (!status) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="h-12 animate-pulse bg-gray-100 rounded-lg" />
      </div>
    )
  }

  const ks = status.kill_switch
  const onToggle = async () => {
    setBusy(true)
    try {
      const reason = ks.active ? undefined : window.prompt('Reason for engaging the kill switch?') ?? 'manual'
      await setKillSwitch(!ks.active, reason)
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  const onTest = async () => {
    setBusy(true)
    setTestResult(null)
    try {
      const r = await sendTelegramTest()
      setTestResult(r.ok ? 'sent' : (r.reason ?? 'failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {ks.active ? (
            <ShieldAlert className="w-5 h-5 text-red-600" />
          ) : (
            <ShieldCheck className="w-5 h-5 text-emerald-600" />
          )}
          <div>
            <h3 className="font-bold text-gray-900">Kill switch</h3>
            <p className="text-xs text-gray-500">
              {ks.active
                ? `Engaged${ks.reason ? ` — ${ks.reason}` : ''}`
                : 'Disengaged · signals + Telegram push are live'}
            </p>
          </div>
        </div>
        <button
          onClick={onToggle}
          disabled={busy}
          className={`text-xs font-bold px-3 py-1.5 rounded-lg transition ${
            ks.active
              ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
              : 'bg-red-100 text-red-700 hover:bg-red-200'
          } disabled:opacity-50`}
        >
          {ks.active ? 'Release' : 'Engage'}
        </button>
      </div>

      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between gap-2">
        <div className="text-xs text-gray-500">
          Telegram:{' '}
          {status.telegram_configured ? (
            <span className="text-emerald-700 font-medium">configured</span>
          ) : (
            <span className="text-gray-700">not configured</span>
          )}
          {!status.notifications_enabled && (
            <span className="ml-1 text-amber-700">(disabled in env)</span>
          )}
        </div>
        <button
          onClick={onTest}
          disabled={busy || !status.telegram_configured}
          className="text-xs font-medium px-2.5 py-1 rounded-md border border-gray-200 hover:bg-gray-50 disabled:opacity-40 flex items-center gap-1"
        >
          <Send className="w-3 h-3" />
          Test
        </button>
      </div>
      {testResult && (
        <p className={`mt-2 text-xs ${testResult === 'sent' ? 'text-emerald-700' : 'text-red-600'}`}>
          {testResult === 'sent' ? 'Test message sent.' : `Test failed: ${testResult}`}
        </p>
      )}
    </div>
  )
}
