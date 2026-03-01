'use client'

import { useEffect, useState } from 'react'
import { fetchKillZones } from '@/lib/api'
import type { KillZoneData, KillZone } from '@/lib/types'

const SESSION_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  Asian: { bg: 'bg-blue-50', text: 'text-blue-700', dot: 'bg-blue-500' },
  London: { bg: 'bg-orange-50', text: 'text-orange-700', dot: 'bg-orange-500' },
  'New York': { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  NY: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  'London Close': { bg: 'bg-purple-50', text: 'text-purple-700', dot: 'bg-purple-500' },
}

const DEFAULT_STYLE = { bg: 'bg-gray-50', text: 'text-gray-600', dot: 'bg-gray-400' }

export function KillZoneBar() {
  const [data, setData] = useState<KillZoneData | null>(null)
  const [countdown, setCountdown] = useState<string>('')

  useEffect(() => {
    const load = async () => {
      try {
        const kz = await fetchKillZones()
        setData(kz)
      } catch {
        // silently fail
      }
    }
    void load()
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!data) return

    const nextZone = data.zones.find((z) => !z.is_active && z.minutes_until_next !== undefined)
    if (!nextZone || nextZone.minutes_until_next === undefined) {
      setCountdown('')
      return
    }

    let remaining = nextZone.minutes_until_next * 60 // convert to seconds
    const tick = () => {
      remaining = Math.max(0, remaining - 1)
      const h = Math.floor(remaining / 3600)
      const m = Math.floor((remaining % 3600) / 60)
      const s = remaining % 60
      const parts = []
      if (h > 0) parts.push(`${h}h`)
      parts.push(`${m}m`)
      parts.push(`${s.toString().padStart(2, '0')}s`)
      setCountdown(parts.join(' '))
    }
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [data])

  const activeZone = data?.zones.find((z) => z.is_active)
  const nextZone = data?.zones.find((z) => !z.is_active && z.minutes_until_next !== undefined)

  const activeStyle = activeZone
    ? (SESSION_STYLES[activeZone.name] ?? DEFAULT_STYLE)
    : DEFAULT_STYLE

  return (
    <div className={`w-full h-5 flex items-center px-4 md:px-6 gap-4 text-xs ${activeZone ? activeStyle.bg : 'bg-gray-50'}`}>
      {/* Active session */}
      {activeZone ? (
        <div className={`flex items-center gap-1.5 ${activeStyle.text} font-medium`}>
          <div className={`w-1.5 h-1.5 rounded-full ${activeStyle.dot} animate-pulse`} />
          {activeZone.name} Session Active
          <span className="opacity-60">
            ({activeZone.start_pkt} – {activeZone.end_pkt} PKT)
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-gray-500">
          <div className="w-1.5 h-1.5 rounded-full bg-gray-400" />
          No Active Session
        </div>
      )}

      {/* Countdown to next session */}
      {nextZone && countdown && (
        <div className="text-gray-500 hidden sm:block">
          Next:{' '}
          <span className="font-medium text-gray-700">{nextZone.name}</span>
          {' '}in{' '}
          <span className="font-mono text-gray-700">{countdown}</span>
        </div>
      )}

      {/* All sessions compact */}
      <div className="ml-auto hidden lg:flex items-center gap-3">
        {data?.zones.map((zone: KillZone) => {
          const style = SESSION_STYLES[zone.name] ?? DEFAULT_STYLE
          return (
            <div
              key={zone.name}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${
                zone.is_active ? `${style.bg} ${style.text} font-medium` : 'text-gray-400'
              }`}
            >
              <div
                className={`w-1 h-1 rounded-full ${zone.is_active ? style.dot : 'bg-gray-300'}`}
              />
              {zone.name.split(' ')[0]}
            </div>
          )
        })}
      </div>
    </div>
  )
}
