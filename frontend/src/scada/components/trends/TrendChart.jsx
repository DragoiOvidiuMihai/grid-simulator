/**
 * TrendChart.jsx — Single-metric Recharts line chart
 * ====================================================
 * Renders a time-series line chart for one metric (voltage or loading).
 * Each key in the series gets its own coloured line.
 *
 * Props:
 *   series   {object}  — { BUS_A: [{timestamp, value}, ...], ... }
 *   metric   {string}  — "voltage_pu" | "loading_pct"
 *   window   {string}  — "1h" | "6h" | "24h" | "7d" (for axis formatting)
 *   height   {number}  — chart height in px (default 220)
 */

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts'

// ─────────────────────────────────────────────────────────────────────────────
// COLOURS — one per series key
// ─────────────────────────────────────────────────────────────────────────────

const SERIES_COLOURS = {
  BUS_A:   '#22c55e',   // green
  BUS_B:   '#3b82f6',   // blue
  BUS_C:   '#a78bfa',   // violet
  BUS_D:   '#f59e0b',   // amber
  TX1:     '#22c55e',
  TX2:     '#3b82f6',
  FEEDER1: '#22c55e',
  FEEDER2: '#3b82f6',
  COUPLER: '#6b7280',
}

const FALLBACK_COLOURS = [
  '#22c55e', '#3b82f6', '#f59e0b', '#a78bfa', '#ef4444',
]

function seriesColour(key, index) {
  return SERIES_COLOURS[key] ?? FALLBACK_COLOURS[index % FALLBACK_COLOURS.length]
}

// ─────────────────────────────────────────────────────────────────────────────
// DATA HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Merge all series into a flat array of { timestamp, BUS_A, BUS_B, ... }
 * that Recharts expects for multi-line charts.
 */
function mergeSeriesData(series) {
  if (!series || Object.keys(series).length === 0) return []

  // Collect all unique timestamps
  const tsSet = new Set()
  for (const points of Object.values(series)) {
    for (const p of points) tsSet.add(p.timestamp)
  }
  const timestamps = [...tsSet].sort()

  // Build lookup per series
  const lookup = {}
  for (const [key, points] of Object.entries(series)) {
    lookup[key] = {}
    for (const p of points) lookup[key][p.timestamp] = p.value
  }

  return timestamps.map(ts => {
    const row = { timestamp: ts }
    for (const key of Object.keys(series)) {
      row[key] = lookup[key][ts] ?? null
    }
    return row
  })
}

function formatTimestamp(ts, window) {
  const d = new Date(ts)
  if (window === '7d') {
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ─────────────────────────────────────────────────────────────────────────────
// TOOLTIP
// ─────────────────────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label, metric }) {
  if (!active || !payload?.length) return null
  const time = new Date(label).toLocaleTimeString()
  const unit = metric === 'voltage_pu' ? ' pu' : '%'

  return (
    <div className="bg-gray-900 border border-gray-700 rounded p-2 text-xs font-mono shadow-xl">
      <p className="text-gray-500 mb-1">{time}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.dataKey}: {p.value != null ? p.value.toFixed(4) : '—'}{unit}
        </p>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CHART
// ─────────────────────────────────────────────────────────────────────────────

export default function TrendChart({ series = {}, metric = 'voltage_pu', window = '1h', height = 220 }) {
  const data    = mergeSeriesData(series)
  const keys    = Object.keys(series)
  const isVolt  = metric === 'voltage_pu'

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-gray-700 font-mono"
        style={{ height }}
      >
        No data yet — collecting history...
      </div>
    )
  }

  // Y-axis domain
  const yDomain = isVolt ? [0.88, 1.12] : [0, 110]
  const yUnit   = isVolt ? ' pu' : '%'

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />

        <XAxis
          dataKey="timestamp"
          tickFormatter={(ts) => formatTimestamp(ts, window)}
          tick={{ fill: '#4b5563', fontSize: 9, fontFamily: 'monospace' }}
          tickLine={false}
          axisLine={{ stroke: '#1e293b' }}
          interval="preserveStartEnd"
          minTickGap={40}
        />

        <YAxis
          domain={yDomain}
          tickFormatter={(v) => `${v}${yUnit}`}
          tick={{ fill: '#4b5563', fontSize: 9, fontFamily: 'monospace' }}
          tickLine={false}
          axisLine={{ stroke: '#1e293b' }}
          width={52}
        />

        <Tooltip content={<CustomTooltip metric={metric} />} />

        <Legend
          wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: '#6b7280' }}
        />

        {/* Reference lines for voltage limits (EN 50160) */}
        {isVolt && (
          <>
            <ReferenceLine y={1.06} stroke="#eab308" strokeDasharray="4 3" strokeWidth={1} label={{ value: '+6%', fill: '#eab308', fontSize: 8, fontFamily: 'monospace' }} />
            <ReferenceLine y={0.94} stroke="#eab308" strokeDasharray="4 3" strokeWidth={1} label={{ value: '−6%', fill: '#eab308', fontSize: 8, fontFamily: 'monospace' }} />
            <ReferenceLine y={1.10} stroke="#ef4444" strokeDasharray="4 3" strokeWidth={1} />
            <ReferenceLine y={0.90} stroke="#ef4444" strokeDasharray="4 3" strokeWidth={1} />
          </>
        )}

        {/* Loading reference lines */}
        {!isVolt && (
          <>
            <ReferenceLine y={70} stroke="#eab308" strokeDasharray="4 3" strokeWidth={1} label={{ value: '70%', fill: '#eab308', fontSize: 8, fontFamily: 'monospace' }} />
            <ReferenceLine y={90} stroke="#ef4444" strokeDasharray="4 3" strokeWidth={1} label={{ value: '90%', fill: '#ef4444', fontSize: 8, fontFamily: 'monospace' }} />
          </>
        )}

        {/* One line per series key */}
        {keys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={seriesColour(key, i)}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
