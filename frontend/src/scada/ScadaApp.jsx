/**
 * ScadaApp.jsx — SCADA/HMI Root Component (Phase 5)
 * ===================================================
 * Phase 5 adds historical trend charts above the event log.
 */

import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useScadaStore } from './store/scadaStore'
import SingleLineDiagram from './components/sld/SingleLineDiagram'
import BreakerControlDialog from './components/controls/BreakerControlDialog'
import AlarmPanel from './components/alarms/AlarmPanel'
import EventLog from './components/events/EventLog'
import HistoricalTrends from './components/trends/HistoricalTrends'

function StatusBadge({ status }) {
  const cfg = {
    connected:    { dot: 'bg-green-400',               text: 'text-green-400',  label: 'ONLINE'     },
    connecting:   { dot: 'bg-yellow-400 animate-pulse', text: 'text-yellow-400', label: 'CONNECTING' },
    disconnected: { dot: 'bg-gray-500',                text: 'text-gray-400',   label: 'OFFLINE'    },
    error:        { dot: 'bg-red-500',                 text: 'text-red-400',    label: 'ERROR'      },
  }[status] ?? { dot: 'bg-gray-500', text: 'text-gray-400', label: status.toUpperCase() }
  return (
    <div className="flex items-center gap-2">
      <div className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
      <span className={`text-xs font-bold tracking-widest ${cfg.text}`}>{cfg.label}</span>
    </div>
  )
}

function VoltageCell({ pu }) {
  if (!pu || pu === 0) return <span className="text-gray-600">—</span>
  const colour = pu < 0.90 || pu > 1.10 ? 'text-red-400' : pu < 0.94 || pu > 1.06 ? 'text-yellow-400' : 'text-green-400'
  return <span className={colour}>{pu.toFixed(4)} pu</span>
}

function LoadingCell({ pct }) {
  if (!pct || pct === 0) return <span className="text-gray-600">—</span>
  const colour = pct > 90 ? 'text-red-400' : pct > 70 ? 'text-yellow-400' : 'text-green-400'
  return <span className={colour}>{pct.toFixed(1)}%</span>
}

function Section({ title, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="bg-gray-900 border border-gray-700 rounded">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between px-4 py-2 border-b border-gray-700 hover:bg-gray-800 transition-colors">
        <span className="text-xs font-bold tracking-widest text-gray-400 uppercase">{title}</span>
        <span className="text-gray-600 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="p-4">{children}</div>}
    </div>
  )
}

function BusesTable({ buses }) {
  const rows = Object.entries(buses)
  if (rows.length === 0) return <p className="text-gray-600 text-xs">Waiting for data...</p>
  return (
    <table className="w-full text-xs font-mono">
      <thead><tr className="text-gray-500 border-b border-gray-800">
        <th className="text-left pb-2 pr-4">Bus</th>
        <th className="text-right pb-2 pr-4">Voltage (kV)</th>
        <th className="text-right pb-2 pr-4">Voltage (pu)</th>
        <th className="text-right pb-2">Nominal (kV)</th>
      </tr></thead>
      <tbody>
        {rows.map(([id, b]) => (
          <tr key={id} className="border-b border-gray-800 last:border-0">
            <td className="py-1.5 pr-4 text-gray-300">{id}</td>
            <td className="py-1.5 pr-4 text-right text-gray-200">{b.voltage_kv === 0 ? <span className="text-gray-600">—</span> : b.voltage_kv.toFixed(4)}</td>
            <td className="py-1.5 pr-4 text-right"><VoltageCell pu={b.voltage_pu} /></td>
            <td className="py-1.5 text-right text-gray-500">{b.voltage_nom}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TransformersTable({ transformers }) {
  const rows = Object.entries(transformers)
  if (rows.length === 0) return <p className="text-gray-600 text-xs">Waiting for data...</p>
  return (
    <table className="w-full text-xs font-mono">
      <thead><tr className="text-gray-500 border-b border-gray-800">
        <th className="text-left pb-2 pr-4">TX</th>
        <th className="text-right pb-2 pr-4">Loading</th>
        <th className="text-right pb-2 pr-4">P (kW)</th>
        <th className="text-right pb-2 pr-4">Q (kvar)</th>
        <th className="text-right pb-2">I primary (A)</th>
      </tr></thead>
      <tbody>
        {rows.map(([id, tx]) => (
          <tr key={id} className="border-b border-gray-800 last:border-0">
            <td className="py-1.5 pr-4 text-gray-300">{id}</td>
            <td className="py-1.5 pr-4 text-right"><LoadingCell pct={tx.loading_pct} /></td>
            <td className="py-1.5 pr-4 text-right text-gray-200">{tx.power_kw.toFixed(1)}</td>
            <td className="py-1.5 pr-4 text-right text-gray-200">{tx.power_kvar.toFixed(1)}</td>
            <td className="py-1.5 text-right text-gray-200">{tx.current_a.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function BranchesTable({ branches }) {
  const rows = Object.entries(branches)
  if (rows.length === 0) return <p className="text-gray-600 text-xs">Waiting for data...</p>
  return (
    <table className="w-full text-xs font-mono">
      <thead><tr className="text-gray-500 border-b border-gray-800">
        <th className="text-left pb-2 pr-4">Branch</th>
        <th className="text-right pb-2 pr-4">Loading</th>
        <th className="text-right pb-2 pr-4">I (A)</th>
        <th className="text-right pb-2 pr-4">Ampacity (A)</th>
        <th className="text-right pb-2 pr-4">P (kW)</th>
        <th className="text-right pb-2">Q (kvar)</th>
      </tr></thead>
      <tbody>
        {rows.map(([id, br]) => (
          <tr key={id} className="border-b border-gray-800 last:border-0">
            <td className="py-1.5 pr-4 text-gray-300">{id}</td>
            <td className="py-1.5 pr-4 text-right"><LoadingCell pct={br.loading_pct} /></td>
            <td className="py-1.5 pr-4 text-right text-gray-200">{br.current_a.toFixed(1)}</td>
            <td className="py-1.5 pr-4 text-right text-gray-500">{br.ampacity_a}</td>
            <td className="py-1.5 pr-4 text-right text-gray-200">{br.power_kw.toFixed(1)}</td>
            <td className="py-1.5 text-right text-gray-200">{br.power_kvar.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function BreakerGrid({ breakerStates, onBreakerClick }) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(breakerStates).map(([id, state]) => {
        const closed = state === 'CLOSED'
        return (
          <button key={id} onClick={() => onBreakerClick(id)}
            className={`flex flex-col items-center px-3 py-2 rounded border text-xs font-mono transition-colors hover:opacity-80 cursor-pointer ${closed ? 'border-green-700 bg-green-950 text-green-400' : 'border-gray-700 bg-gray-900 text-gray-500'}`}>
            <span className="font-bold">{id}</span>
            <span className="text-[10px] mt-0.5">{state}</span>
          </button>
        )
      })}
    </div>
  )
}

export default function ScadaApp() {
  useWebSocket()
  const { wsStatus, lastUpdated, buses, branches, transformers, breakerStates, alarms, ackAlarm, sendBreakerCommand } = useScadaStore()
  const [selectedBreaker, setSelectedBreaker] = useState(null)
  const [dataSource, setDataSource] = useState('synthetic')

  useEffect(() => {
    fetch('/scada/health')
      .then(r => r.json())
      .then(d => setDataSource(d.data_source ?? 'synthetic'))
      .catch(() => {})
  }, [])

  const unackedCount = alarms.filter(a => a.state === 'ACTIVE').length
  const formattedTime = lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : '—'

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 font-mono overflow-hidden">

      <header className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-700 shrink-0">
        <div className="flex items-center gap-4">
          <a href="/" className="text-xs text-gray-500 hover:text-gray-300 transition-colors">← Grid Simulator</a>
          <div className="w-px h-4 bg-gray-700" />
          <span className="text-sm font-bold tracking-widest text-gray-200 uppercase">SCADA / HMI</span>
          <span className="text-xs text-gray-600">11kV / 0.4kV Substation</span>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded border font-mono tracking-widest ${
            dataSource === 'opendss'
              ? 'border-blue-700 bg-blue-950 text-blue-400'
              : 'border-gray-700 bg-gray-900 text-gray-500'
          }`}>
            {dataSource === 'opendss' ? '⚡ OPENDSS' : '~ SYNTHETIC'}
          </span>
        </div>
        <div className="flex items-center gap-4">
          {unackedCount > 0 ? (
            <span className="flex items-center gap-1.5 text-[10px] font-bold px-2 py-0.5 rounded border border-red-700 bg-red-950 text-red-400 animate-pulse">
              ⚠ {unackedCount} ALARM{unackedCount > 1 ? 'S' : ''}
            </span>
          ) : (
            <span className="text-[10px] text-green-700 font-mono border border-green-900 rounded px-2 py-0.5">● No alarms</span>
          )}
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>Last update:</span>
            <span className="text-gray-300">{formattedTime}</span>
          </div>
          <StatusBadge status={wsStatus} />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <SingleLineDiagram onBreakerClick={setSelectedBreaker} />
        <AlarmPanel alarms={alarms} onAck={ackAlarm} />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Section title="Bus Voltages"><BusesTable buses={buses} /></Section>
          <Section title="Transformers"><TransformersTable transformers={transformers} /></Section>
        </div>

        <Section title="Branches & Feeders" defaultOpen={false}>
          <BranchesTable branches={branches} />
        </Section>

        <Section title="Breaker States" defaultOpen={false}>
          <BreakerGrid breakerStates={breakerStates} onBreakerClick={setSelectedBreaker} />
        </Section>

        {/* Phase 5 — Historical Trends */}
        <HistoricalTrends />

        <EventLog />
      </div>

      {selectedBreaker && (
        <BreakerControlDialog
          breakerId={selectedBreaker}
          breakerStates={breakerStates}
          onCommand={sendBreakerCommand}
          onClose={() => setSelectedBreaker(null)}
        />
      )}
    </div>
  )
}
