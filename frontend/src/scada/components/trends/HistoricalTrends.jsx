/**
 * HistoricalTrends.jsx — SCADA Historical Trend Charts
 * ======================================================
 * Tabbed panel showing voltage and loading trends over selectable
 * time windows. Data is fetched from /scada/history and refreshed
 * every 30 seconds.
 *
 * Tabs:    Voltage (pu) | TX Loading (%) | Branch Loading (%)
 * Windows: 1h | 6h | 24h | 7d
 */

import { useEffect, useState, useCallback } from 'react'
import TrendChart from './TrendChart'

// ─────────────────────────────────────────────────────────────────────────────
// CONFIG
// ─────────────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'voltage',        label: 'Bus Voltage',     metric: 'voltage',        unit: 'pu'  },
  { id: 'loading',        label: 'TX Loading',      metric: 'loading',        unit: '%'   },
  { id: 'branch_loading', label: 'Branch Loading',  metric: 'branch_loading', unit: '%'   },
]

const WINDOWS = [
  { id: '1h',  label: '1h'  },
  { id: '6h',  label: '6h'  },
  { id: '24h', label: '24h' },
  { id: '7d',  label: '7d'  },
]

const REFRESH_INTERVAL_MS = 30_000   // 30 seconds

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function HistoricalTrends() {
  const [activeTab,    setActiveTab]    = useState('voltage')
  const [activeWindow, setActiveWindow] = useState('1h')
  const [seriesData,   setSeriesData]   = useState({})
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState(null)
  const [lastFetched,  setLastFetched]  = useState(null)

  const currentTab = TABS.find(t => t.id === activeTab) ?? TABS[0]

  const fetchData = useCallback(async () => {
    try {
      const res  = await fetch(
        `/scada/history?window=${activeWindow}&metric=${currentTab.metric}`
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSeriesData(data.series ?? {})
      setLastFetched(new Date().toLocaleTimeString())
      setError(null)
    } catch (err) {
      setError('Failed to load trend data')
    } finally {
      setLoading(false)
    }
  }, [activeTab, activeWindow])

  // Fetch on mount and whenever tab/window changes
  useEffect(() => {
    setLoading(true)
    fetchData()
  }, [fetchData])

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchData])

  const pointCount = Object.values(seriesData).reduce((sum, arr) => sum + arr.length, 0)

  return (
    <div className="bg-gray-900 border border-gray-700 rounded overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold tracking-widest text-gray-400 uppercase">
            Historical Trends
          </span>
          {lastFetched && (
            <span className="text-[10px] text-gray-600 font-mono">
              fetched {lastFetched}
            </span>
          )}
          {pointCount > 0 && (
            <span className="text-[10px] text-gray-700 font-mono">
              {pointCount} points
            </span>
          )}
        </div>

        {/* Time window selector */}
        <div className="flex items-center gap-1">
          {WINDOWS.map(w => (
            <button
              key={w.id}
              onClick={() => setActiveWindow(w.id)}
              className={`text-[10px] px-2 py-0.5 rounded font-mono transition-colors ${
                activeWindow === w.id
                  ? 'bg-gray-700 text-gray-200'
                  : 'text-gray-600 hover:text-gray-400'
              }`}
            >
              {w.label}
            </button>
          ))}
          <button
            onClick={() => { setLoading(true); fetchData() }}
            className="text-[10px] px-2 py-0.5 rounded font-mono text-gray-600
                       hover:text-gray-400 border border-gray-800 ml-1"
            title="Refresh"
          >
            ↺
          </button>
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <div className="flex border-b border-gray-800">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-xs font-mono transition-colors ${
              activeTab === tab.id
                ? 'text-gray-200 border-b-2 border-green-500'
                : 'text-gray-600 hover:text-gray-400'
            }`}
          >
            {tab.label}
            <span className="ml-1 text-[9px] text-gray-700">({tab.unit})</span>
          </button>
        ))}
      </div>

      {/* ── Chart area ──────────────────────────────────────────────────── */}
      <div className="p-4">

        {/* EN 50160 note for voltage tab */}
        {activeTab === 'voltage' && (
          <p className="text-[10px] text-gray-700 font-mono mb-3">
            Dashed lines: EN 50160 warning (±6%, amber) and critical (±10%, red) voltage limits
          </p>
        )}

        {activeTab === 'loading' && (
          <p className="text-[10px] text-gray-700 font-mono mb-3">
            Dashed lines: IEC 60076-1 warning (70%) and critical (90%) loading limits
          </p>
        )}

        {loading && (
          <div className="flex items-center justify-center h-56 text-xs text-gray-700 font-mono">
            Loading trend data...
          </div>
        )}

        {!loading && error && (
          <div className="flex items-center justify-center h-56 text-xs text-red-700 font-mono">
            {error}
          </div>
        )}

        {!loading && !error && (
          <TrendChart
            series={seriesData}
            metric={activeTab === 'voltage' ? 'voltage_pu' : 'loading_pct'}
            window={activeWindow}
            height={240}
          />
        )}

      </div>
    </div>
  )
}
