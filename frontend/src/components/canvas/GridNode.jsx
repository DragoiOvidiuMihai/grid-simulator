/**
 * GridNode.jsx — Custom Node Renderer
 * =====================================
 * Renders all 8 component types as React Flow nodes.
 * After simulation, overlays voltage results on bus nodes.
 * In time-series mode, updates colors as the timeline slider moves.
 */

import { Handle, Position } from 'reactflow'
import { COMPONENT_DEFINITIONS, useGridStore } from '../../store/gridStore'

const ICONS = {
  BUS_MV:                '⚡',
  BUS_LV:                '🔌',
  TRANSFORMER:           '🔄',
  OVERHEAD_LINE:         '〰',
  UNDERGROUND_CABLE:     '〰',
  RESIDENTIAL_LOAD:      '🏠',
  INDUSTRIAL_LOAD:       '🏭',
  SYNCHRONOUS_GENERATOR: '⚙',
  SOLAR_PV:              '☀',
}

export default function GridNode({ id, type, data, selected }) {
  const def              = COMPONENT_DEFINITIONS[type]
  const simulationResult = useGridStore(state => state.simulationResult)
  const timeSeriesResult = useGridStore(state => state.timeSeriesResult)
  const selectedTimeStep = useGridStore(state => state.selectedTimeStep)

  // ── Find voltage result for this node ─────────────────────────────────────
  // Priority: time-series step result > snapshot result > nothing
  let voltageResult = null

  if (timeSeriesResult) {
    // Look up voltage at the currently selected time step
    const step = timeSeriesResult.timesteps?.[selectedTimeStep]
    if (step) {
      voltageResult = step.bus_voltages?.find(
        v => v.bus_id.toLowerCase() === id.toLowerCase()
      ) || null
    }
  } else if (simulationResult) {
    voltageResult = simulationResult.bus_voltages?.find(
      v => v.bus_id.toLowerCase() === id.toLowerCase()
    ) || null
  }

  // ── Determine border color ────────────────────────────────────────────────
  const isVoltageOk = voltageResult ? voltageResult.within_limits : null
  const borderColor = selected
    ? '#60A5FA'                          // blue when selected
    : isVoltageOk === false
      ? '#EF4444'                        // red — EN 50160 violation
      : isVoltageOk === true
        ? '#22C55E'                      // green — within limits
        : def?.color || '#6B7280'        // default component color

  // ── Time-series PV output for solar nodes ─────────────────────────────────
  let pvOutput = null
  if (timeSeriesResult && type === 'SOLAR_PV') {
    const step = timeSeriesResult.timesteps?.[selectedTimeStep]
    pvOutput = step?.pv_output_kw ?? null
  }

  return (
    <div
      className="relative rounded-lg px-3 py-2 min-w-[110px] cursor-pointer transition-all"
      style={{
        backgroundColor: '#1F2937',
        border:          `2px solid ${borderColor}`,
        boxShadow:       selected ? `0 0 0 1px ${borderColor}` : 'none',
      }}
    >
      {/* Connection handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2"
        style={{ background: def?.color || '#6B7280', border: 'none' }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2"
        style={{ background: def?.color || '#6B7280', border: 'none' }}
      />

      {/* Node content */}
      <div className="flex items-center gap-2">
        <span className="text-base leading-none">{ICONS[type] || '●'}</span>
        <div className="min-w-0">
          <p className="text-xs font-bold text-gray-200 truncate leading-tight">
            {data.label || data.name || def?.label}
          </p>
          <p className="text-xs text-gray-500 truncate leading-tight">
            {def?.label}
          </p>
        </div>
      </div>

      {/* Voltage overlay for bus nodes */}
      {voltageResult && (
        <div
          className="mt-1 pt-1 border-t text-xs"
          style={{ borderColor }}
        >
          <span style={{ color: isVoltageOk ? '#22C55E' : '#EF4444' }}>
            {voltageResult.per_unit.toFixed(4)} pu
          </span>
          <span className="text-gray-500 ml-1">
            {voltageResult.deviation_pct > 0 ? '+' : ''}
            {voltageResult.deviation_pct.toFixed(2)}%
          </span>
        </div>
      )}

      {/* PV output overlay for solar nodes in time-series mode */}
      {pvOutput !== null && (
        <div className="mt-1 pt-1 border-t border-yellow-800 text-xs">
          <span className="text-yellow-400">
            {pvOutput.toFixed(1)} kW
          </span>
        </div>
      )}

      {/* Time-series step indicator (only on bus nodes when in TS mode) */}
      {timeSeriesResult && voltageResult && (
        <div
          className="absolute -top-1 -right-1 w-2 h-2 rounded-full"
          style={{ backgroundColor: isVoltageOk ? '#22C55E' : '#EF4444' }}
        />
      )}
    </div>
  )
}
