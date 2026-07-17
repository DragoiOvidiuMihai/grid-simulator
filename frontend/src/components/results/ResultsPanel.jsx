/**
 * ResultsPanel.jsx — Results Display
 * Handles snapshot, time-series, and fault study results.
 */

import axios from 'axios'
import { useGridStore } from '../../store/gridStore'

// ─────────────────────────────────────────────────────────────────────────────
// PDF EXPORT — plain function, no hooks
// ─────────────────────────────────────────────────────────────────────────────

const exportPDF = async (gridName, simulationResult, timeseriesResult, faultResult = null) => {
  try {
    const response = await axios.post('/export-pdf', {
      grid_name:         gridName,
      simulation_result: simulationResult || null,
      timeseries_result: timeseriesResult || null,
      fault_result:      faultResult      || null,
    }, { responseType: 'blob' })

    const url  = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href  = url
    link.setAttribute('download', `${gridName.replace(/\s+/g, '_')}_report.pdf`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    console.error('PDF export failed:', err)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function ResultsPanel() {
  const {
    simulationResult, timeSeriesResult, faultResult,
    simulationError, isSimulating,
    clearResults, simulationMode,
    selectedTimeStep, setSelectedTimeStep,
  } = useGridStore()

  if (isSimulating) {
    return (
      <div className="flex-1 p-3 flex items-center justify-center">
        <div className="text-center">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <p className="text-xs text-gray-500">
            {simulationMode === 'timeseries' ? 'Running 48 steps...' : 'Running...'}
          </p>
        </div>
      </div>
    )
  }

  if (simulationError) {
    return (
      <div className="flex-1 p-3 overflow-y-auto">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-gray-500 uppercase tracking-widest">Results</p>
          <button onClick={clearResults} className="text-xs text-gray-600 hover:text-gray-400">✕</button>
        </div>
        <div className="rounded bg-red-950 border border-red-800 p-2">
          <p className="text-xs font-bold text-red-400 mb-1">Failed</p>
          <p className="text-xs text-red-300 break-words">{simulationError}</p>
        </div>
      </div>
    )
  }

  if (faultResult) {
    return <FaultResultsPanel result={faultResult} />
  }

  if (timeSeriesResult) {
    return (
      <TimeSeriesResultsPanel
        result={timeSeriesResult}
        selectedStep={selectedTimeStep}
        setStep={setSelectedTimeStep}
      />
    )
  }

  if (simulationResult) {
    return <SnapshotResultsPanel result={simulationResult} />
  }

  return (
    <div className="flex-1 p-3">
      <p className="text-xs text-gray-600 uppercase tracking-widest mb-2">Results</p>
      <p className="text-xs text-gray-700">
        {simulationMode === 'timeseries'
          ? 'Press Run 24h Simulation to see voltage profiles and energy totals.'
          : simulationMode === 'fault'
            ? 'Press Run Fault Study to calculate short-circuit currents at each bus.'
            : 'Press Run Simulation to see voltage, current, and loss results.'
        }
      </p>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SNAPSHOT RESULTS
// ─────────────────────────────────────────────────────────────────────────────

function SnapshotResultsPanel({ result: r }) {
  const { clearResults, gridName } = useGridStore()
  return (
    <div className="flex-1 p-3 overflow-y-auto flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-widest">Results</p>
        <div className="flex gap-2">
          <button
            onClick={() => exportPDF(gridName, r, null)}
            className="text-xs text-blue-400 hover:text-blue-300 border border-blue-800 rounded px-2 py-0.5"
          >↓ PDF</button>
          <button onClick={clearResults} className="text-xs text-gray-600 hover:text-gray-400">✕ Clear</button>
        </div>
      </div>

      <div className={`rounded px-2 py-1 text-xs font-bold ${
        r.converged ? 'bg-green-950 border border-green-800 text-green-400'
                    : 'bg-red-950 border border-red-800 text-red-400'
      }`}>
        {r.converged ? `✓ Converged in ${r.iterations} iterations` : '✗ Did not converge'}
      </div>

      {r.warnings?.length > 0 && (
        <div className="rounded bg-yellow-950 border border-yellow-800 p-2 flex flex-col gap-1">
          <p className="text-xs font-bold text-yellow-400">⚠ Warnings</p>
          {r.warnings.map((w, i) => <p key={i} className="text-xs text-yellow-300 leading-relaxed">{w}</p>)}
        </div>
      )}

      {r.bus_voltages?.length > 0 && (
        <Section title="Bus Voltages">
          {r.bus_voltages.map(v => (
            <ResultRow key={v.bus_id} label={v.bus_id}
              value={`${v.per_unit.toFixed(4)} pu`}
              sub={`${v.voltage_kv.toFixed(4)} kV  (${v.deviation_pct > 0 ? '+' : ''}${v.deviation_pct.toFixed(2)}%)`}
              ok={v.within_limits} />
          ))}
        </Section>
      )}

      {r.line_currents?.length > 0 && (
        <Section title="Line Currents">
          {r.line_currents.map(l => (
            <ResultRow key={l.line_id} label={l.line_id}
              value={`${l.current_a.toFixed(1)} A`}
              sub={`${l.loading_pct.toFixed(1)}% of ${l.ampacity_a} A`}
              ok={!l.overloaded} />
          ))}
        </Section>
      )}

      <Section title="System Losses">
        <ResultRow label="Total active"   value={`${r.total_loss_kw.toFixed(3)} kW`}    ok={true} />
        <ResultRow label="Total reactive" value={`${r.total_loss_kvar.toFixed(3)} kVAR`} ok={true} />
        {r.power_losses?.map(p => (
          <ResultRow key={p.element_id}
            label={`${p.element_type}: ${p.element_id.startsWith('reactflow') ? p.element_type.toUpperCase() : p.element_id}`}
            value={`${p.active_loss_kw.toFixed(3)} kW`}
            sub={`${p.reactive_loss_kvar.toFixed(3)} kVAR`} ok={true} />
        ))}
      </Section>

      {r.generator_outputs?.length > 0 && (
        <Section title="Generator Output">
          {r.generator_outputs.map(g => (
            <ResultRow key={g.generator_id}
              label={g.generator_id.replace('PV_', '☀ ').split('_').slice(0, 3).join('_')}
              value={`${g.kw_output.toFixed(2)} kW`}
              sub={`${g.kvar_output.toFixed(2)} kVAR`} ok={true} />
          ))}
        </Section>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TIME-SERIES RESULTS
// ─────────────────────────────────────────────────────────────────────────────

function TimeSeriesResultsPanel({ result: r, selectedStep, setStep }) {
  const { clearResults, gridName } = useGridStore()
  const ts = r.timesteps?.[selectedStep]
  const lvSummary  = r.voltage_summaries?.find(s => s.bus_id.includes('lv'))
  const pvData     = r.timesteps?.map(t => t.pv_output_kw) || []
  const lvVoltages = r.timesteps?.map(t =>
    t.bus_voltages?.find(v => v.bus_id.includes('lv'))?.per_unit ?? null
  ) || []
  const maxPv = Math.max(...pvData, 0.001)

  return (
    <div className="flex-1 p-3 overflow-y-auto flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-widest">24h Results</p>
        <div className="flex gap-2">
          <button
            onClick={() => exportPDF(gridName, null, r)}
            className="text-xs text-blue-400 hover:text-blue-300 border border-blue-800 rounded px-2 py-0.5"
          >↓ PDF</button>
          <button onClick={clearResults} className="text-xs text-gray-600 hover:text-gray-400">✕</button>
        </div>
      </div>

      <div className="rounded px-2 py-1 text-xs font-bold bg-green-950 border border-green-800 text-green-400">
        ✓ {r.converged_steps}/48 steps converged · {r.season} · {r.peak_load_multiplier}× load
      </div>

      {r.warnings?.length > 0 && (
        <div className="rounded bg-yellow-950 border border-yellow-800 p-2">
          <p className="text-xs font-bold text-yellow-400 mb-1">⚠ {r.warnings.length} warning{r.warnings.length > 1 ? 's' : ''}</p>
          {r.warnings.map((w, i) => <p key={i} className="text-xs text-yellow-300 leading-relaxed">{w}</p>)}
        </div>
      )}

      <Section title="Energy Totals (24h)">
        <ResultRow label="PV generated" value={`${r.total_pv_energy_kwh.toFixed(1)} kWh`}  ok={true} />
        <ResultRow label="Grid losses"  value={`${r.total_energy_loss_kwh.toFixed(3)} kWh`} ok={true} />
        <ResultRow label="Peak loss"    value={`${r.peak_loss_kw.toFixed(3)} kW`} sub={`at ${r.peak_loss_time}`} ok={true} />
      </Section>

      {lvSummary && (
        <Section title="LV Bus Voltage Range">
          <ResultRow label="Min voltage" value={`${lvSummary.min_pu.toFixed(4)} pu`} sub={`at ${lvSummary.min_time}`} ok={lvSummary.min_pu >= 0.9} />
          <ResultRow label="Max voltage" value={`${lvSummary.max_pu.toFixed(4)} pu`} sub={`at ${lvSummary.max_time}`} ok={lvSummary.max_pu <= 1.1} />
          <ResultRow label="Violations"  value={`${lvSummary.violations}/48`} ok={lvSummary.violations === 0} />
        </Section>
      )}

      <div>
        <p className="text-xs text-gray-600 uppercase tracking-widest mb-1">LV Voltage Profile</p>
        <MiniChart data={lvVoltages} selectedStep={selectedStep} color="#70AD47" minY={0.98} maxY={1.02} refLine={1.0} unit="pu" />
      </div>

      {maxPv > 0 && (
        <div>
          <p className="text-xs text-gray-600 uppercase tracking-widest mb-1">PV Output</p>
          <MiniChart data={pvData} selectedStep={selectedStep} color="#F4B942" minY={0} maxY={maxPv} unit="kW" />
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-gray-600 uppercase tracking-widest">Timeline</p>
          <span className="text-xs text-blue-400 font-bold">{ts?.time_label || '00:00'}</span>
        </div>
        <input type="range" min={0} max={47} step={1} value={selectedStep}
          onChange={e => setStep(parseInt(e.target.value))} className="w-full accent-blue-500" />
        <div className="flex justify-between text-xs text-gray-700 mt-1">
          <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:30</span>
        </div>
      </div>

      {ts && (
        <Section title={`Step ${selectedStep} — ${ts.time_label}`}>
          {ts.bus_voltages?.map(v => (
            <ResultRow key={v.bus_id} label={v.bus_id}
              value={`${v.per_unit.toFixed(4)} pu`}
              sub={`${v.deviation_pct > 0 ? '+' : ''}${v.deviation_pct.toFixed(2)}%`}
              ok={v.within_limits} />
          ))}
          <ResultRow label="PV output"   value={`${ts.pv_output_kw.toFixed(2)} kW`}  ok={true} />
          <ResultRow label="Grid losses" value={`${ts.total_loss_kw.toFixed(4)} kW`} ok={true} />
        </Section>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FAULT STUDY RESULTS
// ─────────────────────────────────────────────────────────────────────────────

function FaultResultsPanel({ result: r }) {
  const { clearResults, gridName } = useGridStore()
  return (
    <div className="flex-1 p-3 overflow-y-auto flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-widest">Fault Study</p>
        <div className="flex gap-2">
          <button
            onClick={() => exportPDF(gridName, null, null, r)}
            className="text-xs text-blue-400 hover:text-blue-300 border border-blue-800 rounded px-2 py-0.5"
          >
            ↓ PDF
          </button>
          <button onClick={clearResults} className="text-xs text-gray-600 hover:text-gray-400">✕ Clear</button>
        </div>
      </div>

      <div className={`rounded px-2 py-1 text-xs font-bold ${
        r.success ? 'bg-green-950 border border-green-800 text-green-400'
                  : 'bg-red-950 border border-red-800 text-red-400'
      }`}>
        {r.success ? '✓ Fault study complete' : '✗ Fault study failed'}
      </div>

      {r.warnings?.length > 0 && (
        <div className="rounded bg-yellow-950 border border-yellow-800 p-2">
          <p className="text-xs font-bold text-yellow-400 mb-1">⚠ Warnings</p>
          {r.warnings.map((w, i) => (
            <p key={i} className="text-xs text-yellow-300 leading-relaxed">{w}</p>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-600 leading-relaxed">
        Short-circuit currents calculated via Thevenin impedance method.
        EN 60909 methodology. Values shown for bolted fault at bus terminals.
      </p>

      {r.bus_results?.map(b => (
        <div key={b.bus_id} className="rounded bg-gray-800 border border-gray-700 p-2 flex flex-col gap-1">
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs font-bold text-red-400">{b.bus_id}</p>
            <p className="text-xs text-gray-500">{b.voltage_kv_ll} kV (L-L)</p>
          </div>
          <ResultRow label="3-phase fault"    value={`${b.i3ph_ka.toFixed(3)} kA`} sub={`${b.i3ph_a.toFixed(0)} A`}  ok={true} />
          <ResultRow label="Single L-G fault" value={`${b.i1lg_ka.toFixed(3)} kA`} sub={`${b.i1lg_a.toFixed(0)} A`}  ok={true} />
          <ResultRow label="X/R ratio"        value={b.x_r_ratio.toFixed(2)}        ok={true} />
          <ResultRow label="Z1 (pos-seq)"     value={`${b.z1_real.toFixed(5)} + j${b.z1_imag.toFixed(5)} Ω`} ok={true} />
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MINI CHART
// ─────────────────────────────────────────────────────────────────────────────

function MiniChart({ data, selectedStep, color, minY, maxY, refLine, unit }) {
  const W = 220, H = 48, pad = 2
  const range = maxY - minY || 1
  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (W - pad * 2)
    const y = H - pad - (((v ?? minY) - minY) / range) * (H - pad * 2)
    return `${x},${y}`
  }).join(' ')
  const selX = pad + (selectedStep / (data.length - 1)) * (W - pad * 2)
  const refY = refLine != null ? H - pad - ((refLine - minY) / range) * (H - pad * 2) : null
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded bg-gray-800" style={{ height: H }}>
      {refY != null && <line x1={pad} y1={refY} x2={W - pad} y2={refY} stroke="#374151" strokeWidth="1" strokeDasharray="3,2" />}
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
      <line x1={selX} y1={pad} x2={selX} y2={H - pad} stroke="#60A5FA" strokeWidth="1" opacity="0.7" />
      {data[selectedStep] != null && (() => {
        const sy = H - pad - (((data[selectedStep] ?? minY) - minY) / range) * (H - pad * 2)
        return <circle cx={selX} cy={sy} r="2.5" fill="#60A5FA" />
      })()}
      <text x={pad + 2} y={H - 2} fontSize="7" fill="#6B7280">{minY.toFixed(unit === 'pu' ? 2 : 0)}{unit}</text>
      <text x={pad + 2} y={8}     fontSize="7" fill="#6B7280">{maxY.toFixed(unit === 'pu' ? 2 : 0)}{unit}</text>
    </svg>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div>
      <p className="text-xs text-gray-600 uppercase tracking-widest mb-1">{title}</p>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  )
}

function ResultRow({ label, value, sub, ok }) {
  return (
    <div className="flex items-start justify-between gap-2 py-1 border-b border-gray-800">
      <span className="text-xs text-gray-400 truncate min-w-0 font-mono">{label}</span>
      <div className="text-right shrink-0">
        <span className={`text-xs font-bold ${ok ? 'text-green-400' : 'text-red-400'}`}>{value}</span>
        {sub && <p className="text-xs text-gray-600 leading-tight">{sub}</p>}
      </div>
    </div>
  )
}
