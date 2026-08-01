/**
 * SldElements.jsx — Reusable SVG primitives for the Single-Line Diagram
 * ======================================================================
 * All coordinates are in the parent SVG's viewBox space (900 × 480).
 * Every element is a pure function of its props — no internal state.
 *
 * Colour convention (follows IEC 60617 / real SCADA practice):
 *   #22c55e  green  — energised, healthy (within EN 50160 limits)
 *   #eab308  amber  — warning (approaching limit)
 *   #ef4444  red    — alarm / de-energised / fault
 *   #6b7280  grey   — open breaker or de-energised path
 *   #94a3b8  slate  — neutral label text
 */

// ─────────────────────────────────────────────────────────────────────────────
// COLOUR HELPERS
// ─────────────────────────────────────────────────────────────────────────────

export function voltageColour(pu) {
  if (!pu || pu === 0) return '#6b7280'
  if (pu < 0.90 || pu > 1.10) return '#ef4444'
  if (pu < 0.94 || pu > 1.06) return '#eab308'
  return '#22c55e'
}

export function loadingColour(pct) {
  if (!pct || pct === 0) return '#6b7280'
  if (pct > 90) return '#ef4444'
  if (pct > 70) return '#eab308'
  return '#22c55e'
}

export function energisedColour(energised) {
  return energised ? '#22c55e' : '#6b7280'
}

// ─────────────────────────────────────────────────────────────────────────────
// BUSBAR
// A thick horizontal line representing an HV or LV busbar.
// ─────────────────────────────────────────────────────────────────────────────

export function Busbar({ x, y, width, colour = '#22c55e', label, voltage }) {
  return (
    <g>
      <line
        x1={x} y1={y} x2={x + width} y2={y}
        stroke={colour} strokeWidth={6} strokeLinecap="round"
      />
      {label && (
        <text
          x={x} y={y - 10}
          fill="#94a3b8" fontSize={11} fontFamily="monospace"
          fontWeight="bold"
        >
          {label}
        </text>
      )}
      {voltage && (
        <text
          x={x + width} y={y - 10}
          fill={colour} fontSize={10} fontFamily="monospace"
          textAnchor="end"
        >
          {voltage}
        </text>
      )}
    </g>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CIRCUIT BREAKER
// A small square on a vertical conductor. Filled = closed, hollow = open.
// IEC 60617 symbol: square on line.
// ─────────────────────────────────────────────────────────────────────────────

export function CircuitBreaker({ cx, cy, closed, onClick, label, size = 14 }) {
  const half    = size / 2
  const colour  = closed ? '#22c55e' : '#6b7280'
  const fill    = closed ? colour : '#1e293b'

  return (
    <g
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      {/* Clickable hit area — larger than visible symbol */}
      {onClick && (
        <rect
          x={cx - half - 8} y={cy - half - 8}
          width={size + 16} height={size + 16}
          fill="transparent"
        />
      )}
      <rect
        x={cx - half} y={cy - half}
        width={size} height={size}
        fill={fill} stroke={colour} strokeWidth={2}
        rx={2}
      />
      {/* Closed indicator: filled dot */}
      {closed && (
        <circle cx={cx} cy={cy} r={3} fill="#1e293b" />
      )}
      {label && (
        <text
          x={cx + half + 5} y={cy + 4}
          fill="#64748b" fontSize={9} fontFamily="monospace"
        >
          {label}
        </text>
      )}
    </g>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TRANSFORMER
// IEC 60617 symbol: two circles (primary winding, secondary winding).
// ─────────────────────────────────────────────────────────────────────────────

export function Transformer({ cx, cy, colour = '#22c55e', label, loading }) {
  const r = 14
  return (
    <g>
      {/* Primary winding (top circle) */}
      <circle
        cx={cx} cy={cy - r + 2}
        r={r} fill="#1e293b"
        stroke={colour} strokeWidth={2}
      />
      {/* Secondary winding (bottom circle) */}
      <circle
        cx={cx} cy={cy + r - 2}
        r={r} fill="#1e293b"
        stroke={colour} strokeWidth={2}
      />
      {/* Label */}
      {label && (
        <text
          x={cx + r + 6} y={cy - 4}
          fill="#94a3b8" fontSize={10} fontFamily="monospace"
          fontWeight="bold"
        >
          {label}
        </text>
      )}
      {/* Loading % */}
      {loading !== undefined && (
        <text
          x={cx + r + 6} y={cy + 10}
          fill={loadingColour(loading)} fontSize={10} fontFamily="monospace"
        >
          {loading.toFixed(1)}%
        </text>
      )}
    </g>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CONDUCTOR (vertical or horizontal wire)
// ─────────────────────────────────────────────────────────────────────────────

export function Wire({ x1, y1, x2, y2, colour = '#22c55e', dashed = false }) {
  return (
    <line
      x1={x1} y1={y1} x2={x2} y2={y2}
      stroke={colour} strokeWidth={2}
      strokeDasharray={dashed ? '4 3' : undefined}
      strokeLinecap="round"
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// LOAD SYMBOL
// A simple resistor box representing a load.
// ─────────────────────────────────────────────────────────────────────────────

export function LoadSymbol({ cx, cy, colour = '#22c55e', label }) {
  return (
    <g>
      <rect
        x={cx - 10} y={cy - 7}
        width={20} height={14}
        fill="#1e293b" stroke={colour} strokeWidth={1.5}
        rx={2}
      />
      {/* Three horizontal lines inside to represent resistance */}
      {[-3, 0, 3].map((dy, i) => (
        <line
          key={i}
          x1={cx - 6} y1={cy + dy}
          x2={cx + 6} y2={cy + dy}
          stroke={colour} strokeWidth={1}
        />
      ))}
      {label && (
        <text
          x={cx} y={cy + 22}
          fill="#64748b" fontSize={9} fontFamily="monospace"
          textAnchor="middle"
        >
          {label}
        </text>
      )}
    </g>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PV SYMBOL
// Sun-like symbol for a photovoltaic source.
// ─────────────────────────────────────────────────────────────────────────────

export function PvSymbol({ cx, cy, colour = '#22c55e', label }) {
  const rays = 8
  return (
    <g>
      <circle cx={cx} cy={cy} r={8} fill="#1e293b" stroke={colour} strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={4} fill={colour} />
      {Array.from({ length: rays }).map((_, i) => {
        const angle = (i * 360) / rays
        const rad   = (angle * Math.PI) / 180
        const x1    = cx + 10 * Math.cos(rad)
        const y1    = cy + 10 * Math.sin(rad)
        const x2    = cx + 14 * Math.cos(rad)
        const y2    = cy + 14 * Math.sin(rad)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={colour} strokeWidth={1.5} />
      })}
      {label && (
        <text
          x={cx} y={cy + 26}
          fill="#64748b" fontSize={9} fontFamily="monospace"
          textAnchor="middle"
        >
          {label}
        </text>
      )}
    </g>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FEEDER ARROW
// Arrow at the top of each incoming feeder to indicate source direction.
// ─────────────────────────────────────────────────────────────────────────────

export function FeederArrow({ cx, cy, colour = '#22c55e', label, current }) {
  return (
    <g>
      {/* Arrow pointing down (power flowing in) */}
      <polygon
        points={`${cx},${cy + 10} ${cx - 7},${cy - 4} ${cx + 7},${cy - 4}`}
        fill={colour} opacity={0.85}
      />
      <line x1={cx} y1={cy - 4} x2={cx} y2={cy - 16} stroke={colour} strokeWidth={2} />
      {label && (
        <text
          x={cx} y={cy - 22}
          fill="#94a3b8" fontSize={10} fontFamily="monospace"
          textAnchor="middle" fontWeight="bold"
        >
          {label}
        </text>
      )}
      {current !== undefined && (
        <text
          x={cx} y={cy + 26}
          fill={colour} fontSize={9} fontFamily="monospace"
          textAnchor="middle"
        >
          {current.toFixed(1)} A
        </text>
      )}
    </g>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MEASUREMENT TOOLTIP BOX
// Small floating label showing a key measurement near an element.
// ─────────────────────────────────────────────────────────────────────────────

export function MeasurementTag({ x, y, lines = [], anchor = 'start' }) {
  const lineHeight = 13
  const height     = lines.length * lineHeight + 8
  const maxLen     = Math.max(...lines.map(l => l.value?.toString().length ?? 0))
  const width      = Math.max(70, maxLen * 7 + 20)

  const bx = anchor === 'end' ? x - width : x

  return (
    <g>
      <rect
        x={bx} y={y}
        width={width} height={height}
        fill="#0f172a" stroke="#334155"
        strokeWidth={1} rx={3} opacity={0.9}
      />
      {lines.map((line, i) => (
        <text
          key={i}
          x={bx + 6}
          y={y + 12 + i * lineHeight}
          fill={line.colour ?? '#94a3b8'}
          fontSize={9} fontFamily="monospace"
        >
          <tspan fill="#475569">{line.label}: </tspan>
          {line.value}
        </text>
      ))}
    </g>
  )
}
