'use client'

import { useState, useEffect } from 'react'
import { fetchUpcomingEvents } from '@/lib/api'
import type { EconomicEvent } from '@/lib/types'
import { Calendar, AlertTriangle, Clock } from 'lucide-react'

const IMPACT_STYLES: Record<string, string> = {
  HIGH: 'bg-red-100 text-red-700 border-red-200',
  MEDIUM: 'bg-amber-100 text-amber-700 border-amber-200',
  LOW: 'bg-gray-100 text-gray-600 border-gray-200',
}

export default function EventsPage() {
  const [events, setEvents] = useState<EconomicEvent[]>([])
  const [nextEvent, setNextEvent] = useState<EconomicEvent | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [daysAhead, setDaysAhead] = useState(7)

  const loadEvents = async () => {
    setLoading(true)
    try {
      const res = await fetchUpcomingEvents(daysAhead)
      setEvents(res.events ?? [])
      setNextEvent(res.next_event ?? null)
      setWarnings(res.active_warnings ?? [])
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadEvents()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [daysAhead])

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Calendar className="w-6 h-6 text-blue-600" />
          Economic Calendar
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Upcoming high-impact economic events that may affect crypto markets
        </p>
      </div>

      {/* Active Warnings */}
      {warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-1.5">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <p className="font-bold text-amber-800 text-sm">Active Event Warnings</p>
          </div>
          {warnings.map((w, i) => (
            <p key={i} className="text-sm text-amber-700">{w}</p>
          ))}
        </div>
      )}

      {/* Next Event Banner */}
      {nextEvent && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-blue-600" />
            <p className="font-bold text-blue-800 text-sm">Next Event</p>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <p className="font-semibold text-gray-900">{nextEvent.title}</p>
              <p className="text-xs text-gray-500">{nextEvent.currency} • {new Date(nextEvent.datetime).toLocaleString()}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-2.5 py-0.5 text-xs font-bold rounded-full border ${IMPACT_STYLES[nextEvent.impact] ?? IMPACT_STYLES.LOW}`}>
                {nextEvent.impact} IMPACT
              </span>
              {nextEvent.minutes_until != null && (
                <span className="text-xs text-gray-500">
                  in {nextEvent.minutes_until < 60
                    ? `${nextEvent.minutes_until}m`
                    : `${Math.floor(nextEvent.minutes_until / 60)}h ${nextEvent.minutes_until % 60}m`}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-600">Days ahead:</label>
        <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white">
          {[3, 7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDaysAhead(d)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                daysAhead === d ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Events List */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-14 bg-gray-100 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="p-12 text-center text-gray-400 text-sm">
            <Calendar className="w-10 h-10 mx-auto mb-3 text-gray-300" />
            No events found for the next {daysAhead} days
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {events.map((event) => (
              <div
                key={event.id}
                className={`px-4 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 ${
                  event.is_warning_active ? 'bg-amber-50' : ''
                }`}
              >
                <div className="flex items-start gap-3">
                  {event.is_warning_active && (
                    <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                  )}
                  <div>
                    <p className="font-semibold text-gray-900 text-sm">{event.title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-gray-500">{event.currency}</span>
                      <span className="text-gray-300">•</span>
                      <span className="text-xs text-gray-500">
                        {new Date(event.datetime).toLocaleString()}
                      </span>
                      {event.minutes_until != null && event.minutes_until > 0 && (
                        <>
                          <span className="text-gray-300">•</span>
                          <span className="text-xs text-blue-600 font-medium">
                            in {event.minutes_until < 60
                              ? `${event.minutes_until}m`
                              : `${Math.floor(event.minutes_until / 60)}h ${event.minutes_until % 60}m`}
                          </span>
                        </>
                      )}
                    </div>
                    {event.description && (
                      <p className="text-xs text-gray-400 mt-1">{event.description}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {event.forecast && (
                    <div className="text-xs text-center">
                      <p className="text-gray-400">Forecast</p>
                      <p className="font-semibold text-gray-700">{event.forecast}</p>
                    </div>
                  )}
                  {event.previous && (
                    <div className="text-xs text-center">
                      <p className="text-gray-400">Previous</p>
                      <p className="font-semibold text-gray-700">{event.previous}</p>
                    </div>
                  )}
                  <span className={`px-2.5 py-0.5 text-xs font-bold rounded-full border ${IMPACT_STYLES[event.impact] ?? IMPACT_STYLES.LOW}`}>
                    {event.impact}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
