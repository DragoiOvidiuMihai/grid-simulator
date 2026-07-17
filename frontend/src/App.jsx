/**
 * App.jsx — Main Layout
 * Three-panel layout with Snapshot / Time-Series / Fault Study mode toggle.
 */

import { useCallback } from 'react'
import { useGridStore } from './store/gridStore'
import Sidebar from './components/sidebar/Sidebar'
import Canvas from './components/canvas/Canvas'
import PropertiesPanel from './components/properties/PropertiesPanel'
import ResultsPanel from './components/results/ResultsPanel'
import SaveLoadPanel from './components/SaveLoadPanel'

export default function App() {
  const {
    runSimulation, runTimeSeriesSimulation, runFaultStudy,
    isSimulating, clearGrid, gridName, setGridName,
    simulationMode, setSimulationMode,
    tsSeason, setTsSeason,
    tsMultiplier, setTsMultiplier,
  } = useGridStore()

  const handleSimulate = useCallback(async () => {
    if (simulationMode === 'snapshot') {
      await runSimulation()
    } else if (simulationMode === 'timeseries') {
      await runTimeSeriesSimulation()
    } else if (simulationMode === 'fault') {
      await runFaultStudy()
    }
  }, [simulationMode, runSimulation, runTimeSeriesSimulation, runFaultStudy])

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 font-mono overflow-hidden">

      {/* ── Top Bar ──────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 shrink-0 gap-4">

        {/* Logo */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-blue-500" />
            <div className="w-3 h-3 rounded-full bg-yellow-400" />
            <div className="w-3 h-3 rounded-full bg-green-500" />
          </div>
          <span className="text-sm font-bold tracking-widest text-gray-200 uppercase">
            Grid Simulator
          </span>
        </div>

        {/* Mode toggle */}
        <div className="flex items-center gap-1 bg-gray-800 rounded p-1 shrink-0">
          <button
            onClick={() => setSimulationMode('snapshot')}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              simulationMode === 'snapshot'
                ? 'bg-blue-600 text-white font-bold'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Snapshot
          </button>
          <button
            onClick={() => setSimulationMode('timeseries')}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              simulationMode === 'timeseries'
                ? 'bg-blue-600 text-white font-bold'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Time-Series
          </button>
          <button
            onClick={() => setSimulationMode('fault')}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              simulationMode === 'fault'
                ? 'bg-red-700 text-white font-bold'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Fault Study
          </button>
        </div>

        {/* Time-series parameters */}
        {simulationMode === 'timeseries' && (
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-500">Season:</span>
              <select
                value={tsSeason}
                onChange={e => setTsSeason(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
              >
                <option value="summer">☀ Summer</option>
                <option value="winter">❄ Winter</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Load:</span>
              <input
                type="range" min="0.5" max="2.0" step="0.1" value={tsMultiplier}
                onChange={e => setTsMultiplier(parseFloat(e.target.value))}
                className="w-20 accent-blue-500"
              />
              <span className="text-xs text-blue-400 w-8">{tsMultiplier.toFixed(1)}×</span>
            </div>
          </div>
        )}

        {/* Fault study info */}
        {simulationMode === 'fault' && (
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-red-400 border border-red-900 rounded px-2 py-1">
              ⚡ Calculates 3-phase and single L-G fault currents at all buses
            </span>
          </div>
        )}

        {/* Grid name */}
        <input
          type="text"
          value={gridName}
          onChange={e => setGridName(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-xs text-gray-200 w-40 focus:outline-none focus:border-blue-500"
          placeholder="Grid name..."
        />

        {/* Action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <SaveLoadPanel />
          <button
            onClick={clearGrid}
            className="px-3 py-1 text-xs rounded border border-gray-600 text-gray-400 hover:border-gray-400 hover:text-gray-200 transition-colors"
          >
            Clear
          </button>
          <button
            onClick={handleSimulate}
            disabled={isSimulating}
            className={`px-4 py-1 text-xs rounded font-bold tracking-wider transition-colors ${
              isSimulating
                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                : simulationMode === 'timeseries'
                  ? 'bg-green-700 hover:bg-green-600 text-white'
                  : simulationMode === 'fault'
                    ? 'bg-red-700 hover:bg-red-600 text-white'
                    : 'bg-blue-600 hover:bg-blue-500 text-white'
            }`}
          >
            {isSimulating
              ? 'Running...'
              : simulationMode === 'timeseries' ? '▶ Run 24h Simulation'
              : simulationMode === 'fault'      ? '⚡ Run Fault Study'
              : '▶ Run Simulation'
            }
          </button>
        </div>
      </header>

      {/* ── Main Content ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-48 shrink-0 bg-gray-900 border-r border-gray-700 overflow-y-auto">
          <Sidebar />
        </aside>
        <main className="flex-1 relative">
          <Canvas />
        </main>
        <aside className="w-72 shrink-0 bg-gray-900 border-l border-gray-700 flex flex-col overflow-hidden">
          <PropertiesPanel />
          <ResultsPanel />
        </aside>
      </div>
    </div>
  )
}
