'use client'

import { useEffect, useState } from 'react'
import { fetchUpcomingEvents } from '@/lib/api'
import type { EconomicEvent } from '@/lib/types'
import { Calendar, AlertTriangle, Clock, TrendingUp } from 'lucide-react'

export default function EventsPage() {
  const [events, setEvents] = useState<EconomicEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [nextEvent, setNextEvent] = useState<EconomicEvent | null>(null)
  const [hasWarnings, setHasWarnings] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchUpcomingEvents(7)
        setEvents(data.events)
        setNextEvent(data.next_event)
        setHasWarnings(data.has_active_warnings)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [])

  const impactColors = {
    HIGH: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200', dot: 'bg-red-500' },
    MEDIUM: { bg: 'bg-amber-100', text: 'text-amber-700', border: 'border-amber-200', dot: 'bg-amber-500' },
    LOW: { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-200', dot: 'bg-green-500' },
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Economic Calendar</h1>
        <p className="text-sm text-gray-500 mt-1">Upcoming market-moving events — trade with caution around HIGH impact events</p>
      </div>

      {/* Active Warning Banner */}
      {hasWarnings && (
        <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-bold text-red-800">⚠️ Active Event Warning</p>
            <p className="text-sm text-red-700 mt-0.5">
              A high-impact event is within its warning window. Trade with caution — consider wider stop losses (+50%).
            </p>
          </div>
        </div>
      )}

      {/* Next Event Countdown */}
      {nextEvent && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-5 h-5 text-blue-600" />
            <h2 className="font-bold text-gray-900">Next Event</h2>
          </div>
          <div className="flex items-start gap-4">
            <div className="flex-1">
              <p className="font-bold text-gray-900 text-lg">{nextEvent.name}</p>
              <p className="text-sm text-gray-500 mt-1">{nextEvent.datetime_pkt}</p>
              <p className="text-sm text-gray-400">{nextEvent.currency} • Impact: <span className={`font-bold ${impactColors[nextEvent.impact]?.text}`}>{nextEvent.impact}</span></p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-gray-900">
                {nextEvent.minutes_until > 60
                  ? `${Math.floor(nextEvent.minutes_until / 60)}h ${nextEvent.minutes_until % 60}m`
                  : `${nextEvent.minutes_until}m`}
              </p>
              <p className="text-xs text-gray-400">until event</p>
            </div>
          </div>
        </div>
      )}

      {/* Event List */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <h2 className="font-bold text-gray-900">Upcoming Events (7 days)</h2>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading events...</div>
        ) : events.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No upcoming events found</div>
        ) : (
          <div className="divide-y divide-gray-50">
            {events.map((event, i) => {
              const colors = impactColors[event.impact] ?? impactColors.LOW
              return (
                <div
                  key={i}
                  className={`flex items-center gap-4 px-4 py-3 ${event.is_active_warning ? 'bg-red-50' : ''}`}
                >
                  {/* Impact indicator */}
                  <div className={`w-2 h-8 rounded-full flex-shrink-0 ${colors.dot}`} />

                  {/* Event info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-gray-900 text-sm truncate">{event.name}</p>
                      {event.is_active_warning && (
                        <AlertTriangle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">{event.datetime_pkt} • {event.currency}</p>
                    {event.warning_message && (
                      <p className="text-xs text-red-600 mt-0.5">{event.warning_message}</p>
                    )}
                  </div>

                  {/* Impact badge */}
                  <span className={`px-2 py-0.5 rounded text-xs font-bold border flex-shrink-0 ${colors.bg} ${colors.text} ${colors.border}`}>
                    {event.impact}
                  </span>

                  {/* Countdown */}
                  <div className="text-right flex-shrink-0 w-16">
                    <p className="text-sm font-bold text-gray-900">
                      {event.minutes_until > 1440
                        ? `${Math.floor(event.minutes_until / 1440)}d`
                        : event.minutes_until > 60
                        ? `${Math.floor(event.minutes_until / 60)}h`
                        : `${event.minutes_until}m`}
                    </p>
                    <p className="text-xs text-gray-400">away</p>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Impact Level Guide */}
      <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
        <h3 className="font-bold text-gray-700 mb-3 text-sm">Impact Level Guide</h3>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-red-500 flex-shrink-0" />
            <span className="font-bold text-red-700">HIGH</span>
            <span className="text-gray-500">— FOMC, CPI, NFP: Warning 30min before, 1h after. Wider SL +50% recommended.</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-amber-500 flex-shrink-0" />
            <span className="font-bold text-amber-700">MEDIUM</span>
            <span className="text-gray-500">— PPI, GDP: Warning 15min before, 30min after. Monitor closely.</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-green-500 flex-shrink-0" />
            <span className="font-bold text-green-700">LOW</span>
            <span className="text-gray-500">— Minor data releases: No signal modification.</span>
          </div>
        </div>
      </div>
    </div>
  )
}
