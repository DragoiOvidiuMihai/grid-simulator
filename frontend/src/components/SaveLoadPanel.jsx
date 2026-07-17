/**
 * SaveLoadPanel.jsx — Save / Load Grid Configurations
 * =====================================================
 * Dropdown panel triggered from the top bar.
 * Allows saving the current grid under a name,
 * loading any previously saved grid, and deleting saves.
 */

import { useState, useEffect, useRef } from 'react'
import { useGridStore } from '../store/gridStore'

export default function SaveLoadPanel() {
  const [open,     setOpen]     = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saves,    setSaves]    = useState([])
  const [message,  setMessage]  = useState(null)
  const panelRef = useRef(null)

  const { saveGrid, loadGrid, deleteGrid, getSavedGridNames, gridName } = useGridStore()

  // Refresh saves list whenever panel opens
  useEffect(() => {
    if (open) {
      setSaves(getSavedGridNames())
      setSaveName(gridName)
    }
  }, [open, gridName, getSavedGridNames])

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const showMessage = (msg, isError = false) => {
    setMessage({ text: msg, error: isError })
    setTimeout(() => setMessage(null), 2500)
  }

  const handleSave = () => {
    const name = saveName.trim()
    if (!name) { showMessage('Enter a name first.', true); return }
    const ok = saveGrid(name)
    if (ok) {
      setSaves(getSavedGridNames())
      showMessage(`Saved as "${name}"`)
    } else {
      showMessage('Save failed.', true)
    }
  }

  const handleLoad = (name) => {
    const ok = loadGrid(name)
    if (ok) {
      showMessage(`Loaded "${name}"`)
      setOpen(false)
    } else {
      showMessage(`Could not load "${name}".`, true)
    }
  }

  const handleDelete = (name, e) => {
    e.stopPropagation()
    deleteGrid(name)
    setSaves(getSavedGridNames())
    showMessage(`Deleted "${name}"`)
  }

  return (
    <div className="relative" ref={panelRef}>

      {/* Trigger button */}
      <button
        onClick={() => setOpen(o => !o)}
        className="px-3 py-1 text-xs rounded border border-gray-600 text-gray-400 hover:border-gray-400 hover:text-gray-200 transition-colors"
      >
        ☰ Saves
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute right-0 top-8 w-64 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 p-3 flex flex-col gap-3">

          {/* Feedback message */}
          {message && (
            <p className={`text-xs rounded px-2 py-1 ${
              message.error
                ? 'bg-red-950 text-red-400 border border-red-800'
                : 'bg-green-950 text-green-400 border border-green-800'
            }`}>
              {message.text}
            </p>
          )}

          {/* Save current grid */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Save Current Grid</p>
            <div className="flex gap-1">
              <input
                type="text"
                value={saveName}
                onChange={e => setSaveName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSave()}
                placeholder="Save name..."
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={handleSave}
                className="px-2 py-1 text-xs bg-blue-700 hover:bg-blue-600 text-white rounded"
              >
                Save
              </button>
            </div>
          </div>

          {/* Saved grids list */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">
              Saved Grids {saves.length > 0 && `(${saves.length})`}
            </p>

            {saves.length === 0 ? (
              <p className="text-xs text-gray-700 italic">No saved grids yet.</p>
            ) : (
              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
                {saves.map(name => (
                  <div
                    key={name}
                    onClick={() => handleLoad(name)}
                    className="flex items-center justify-between px-2 py-1.5 rounded bg-gray-800 border border-gray-700 cursor-pointer hover:border-blue-600 hover:bg-gray-750 transition-colors group"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-gray-200 truncate">{name}</p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="text-xs text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity">
                        Load
                      </span>
                      <button
                        onClick={e => handleDelete(name, e)}
                        className="text-xs text-gray-600 hover:text-red-400 ml-1 transition-colors"
                        title="Delete this save"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  )
}
