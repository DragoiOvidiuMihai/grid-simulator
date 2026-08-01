/**
 * EventLog.jsx — SCADA Event Log
 * =================================
 * Displays a scrollable, filterable table of timestamped events.
 * Events are fetched from the /scada/events REST endpoint on mount
 * and refreshed every 10 seconds.
 *
 * Columns: Time | Type | Element | Description
 * Filters: All | Alarms | Operator | System
 */

import { useEffect, useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// EVENT TYPE STYLES
// ─────────────────────────────────────────────────────────────────────────────

const TYPE_STYLE = {
  ALARM_RAISED:  { label: 'ALARM',    colour: 'text-red-400',    bg: 'bg-red-950/50 border-red-900'     },
  ALARM_ACKED:   { label: 'ACK',      colour: 'text-yellow-400', bg: 'bg-yellow-950/30 border-yellow-900' },
  ALARM_CLEARED: { label: 'CLEARED',  colour: 'text-green-600',  bg: 'bg-green-950/20 border-green-900' },
  BREAKER_OP:    { label: 'OPERATOR', colour: 'text-blue-400',   bg: 'bg-blue-950/30 border-blue-900'   },
  SYSTEM:        { label: 'SYSTEM',   colour: 'text-gray-500',   bg: 'bg-gray-900 border-gray-800'      },
}

const PRIORITY_COLOUR = {
  HIGH:   'text-red-400',
  MEDIUM: 'text-yellow-400',
  LOW:    'text-blue-400',
  INFO:   'text-gray-600',
}

// ─────────────────────────────────────────────────────────────────────────────
// FILTER TABS
// ─────────────────────────────────────────────────────────────────────────────

const FILTERS = [
  { label: 'All',      value: 'ALL' },
  { label: 'Alarms',   value: 'ALARM' },
  { label: 'Operator', value: 'BREAKER_OP' },
  { label: 'System',   value: 'SYSTEM' },
]

function filterEvents(events, filter) {
  if (filter === 'ALL') return events
  if (filter === 'ALARM') return events.filter(e => e.event_type.startsWith('ALARM'))
  return events.filter(e => e.event_type === filter)
}

// ─────────────────────────────────────────────────────────────────────────────
// EVENT ROW
// ─────────────────────────────────────────────────────────────────────────────

function EventRow({ event }) {
  const style  = TYPE_STYLE[event.event_type] ?? TYPE_STYLE.SYSTEM
  const time   = new Date(event.timestamp).toLocaleTimeString()
  const pColour = PRIORITY_COLOUR[event.priority] ?? 'text-gray-600'

  return (
    <tr className={`border-b border-gray-800/50 last:border-0 text-xs font-mono`}>
      <td className="py-1.5 pr-3 text-gray-600 whitespace-nowrap">{time}</td>
      <td className="py-1.5 pr-3">
        <span className={`text-[9px] font-bold tracking-widest ${style.colour}`}>
          {style.label}
        </span>
      </td>
      <td className="py-1.5 pr-3 text-gray-400 whitespace-nowrap">{event.element}</td>
      <td className={`py-1.5 ${pColour} leading-relaxed`}>{event.description}</td>
    </tr>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EVENT LOG COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function EventLog() {
  const [events,      setEvents]      = useState([])
  const [filter,      setFilter]      = useState('ALL')
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState(null)
  const [totalCount,  setTotalCount]  = useState(0)

  async function fetchEvents() {
    try {
      const res  = await fetch('/scada/events?limit=100')
      const data = await res.json()
      setEvents(data.events ?? [])
      setTotalCount(data.total ?? 0)
      setError(null)
    } catch (err) {
      setError('Failed to load events')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchEvents()
    const interval = setInterval(fetchEvents, 10_000)
    return () => clearInterval(interval)
  }, [])

  const filtered = filterEvents(events, filter)

  return (
    <div className="bg-gray-900 border border-gray-700 rounded overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold tracking-widest text-gray-400 uppercase">
            Event Log
          </span>
          <span className="text-[10px] text-gray-600 font-mono">
            {totalCount} total
          </span>
        </div>

        {/* Filter tabs */}
        <div className="flex items-center gap-1">
          {FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`text-[10px] px-2 py-0.5 rounded font-mono transition-colors ${
                filter === f.value
                  ? 'bg-gray-700 text-gray-200'
                  : 'text-gray-600 hover:text-gray-400'
              }`}
            >
              {f.label}
            </button>
          ))}
          <button
            onClick={fetchEvents}
            className="text-[10px] px-2 py-0.5 rounded font-mono text-gray-600
                       hover:text-gray-400 border border-gray-800 ml-1"
            title="Refresh"
          >
            ↺
          </button>
        </div>
      </div>

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="overflow-y-auto max-h-64 p-3">
        {loading && (
          <p className="text-xs text-gray-600 font-mono text-center py-4">Loading events...</p>
        )}
        {error && (
          <p className="text-xs text-red-600 font-mono text-center py-4">{error}</p>
        )}
        {!loading && !error && filtered.length === 0 && (
          <p className="text-xs text-gray-700 font-mono text-center py-4">
            No events yet — events appear as the simulation runs.
          </p>
        )}
        {!loading && filtered.length > 0 && (
          <table className="w-full">
            <thead>
              <tr className="text-[10px] text-gray-600 border-b border-gray-800">
                <th className="text-left pb-1.5 pr-3 font-normal">Time</th>
                <th className="text-left pb-1.5 pr-3 font-normal">Type</th>
                <th className="text-left pb-1.5 pr-3 font-normal">Element</th>
                <th className="text-left pb-1.5 font-normal">Description</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((event, i) => (
                <EventRow key={`${event.timestamp}-${i}`} event={event} />
              ))}
            </tbody>
          </table>
        )}
      </div>

    </div>
  )
}
