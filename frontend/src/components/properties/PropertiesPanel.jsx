/**
 * PropertiesPanel.jsx — Component Parameter Editor
 * ==================================================
 * Shows editable fields for whichever node is selected on the canvas.
 * When no node is selected, shows a placeholder message.
 */

import { useGridStore } from '../../store/gridStore'

// Fields to show for each component type
// Format: { key, label, type, unit, step, min }
const FIELD_DEFINITIONS = {
  BUS_MV: [
    { key: 'name',    label: 'Name',         type: 'text' },
    { key: 'base_kv', label: 'Voltage',      type: 'number', unit: 'kV',   step: 0.1,  min: 0 },
    { key: 'phases',  label: 'Phases',       type: 'number', unit: '',     step: 1,    min: 1 },
  ],
  BUS_LV: [
    { key: 'name',    label: 'Name',         type: 'text' },
    { key: 'base_kv', label: 'Voltage',      type: 'number', unit: 'kV',   step: 0.01, min: 0 },
    { key: 'phases',  label: 'Phases',       type: 'number', unit: '',     step: 1,    min: 1 },
  ],
  TRANSFORMER: [
    { key: 'name',         label: 'Name',       type: 'text' },
    { key: 'rating_kva',   label: 'Rating',     type: 'number', unit: 'kVA', step: 10,   min: 0 },
    { key: 'primary_kv',   label: 'Primary',    type: 'number', unit: 'kV',  step: 0.1,  min: 0 },
    { key: 'secondary_kv', label: 'Secondary',  type: 'number', unit: 'kV',  step: 0.01, min: 0 },
    { key: 'percent_r',    label: '%R',         type: 'number', unit: '%',   step: 0.1,  min: 0 },
    { key: 'percent_x',    label: '%X',         type: 'number', unit: '%',   step: 0.1,  min: 0 },
  ],
  OVERHEAD_LINE: [
    { key: 'name',      label: 'Name',   type: 'text' },
    { key: 'length_km', label: 'Length', type: 'number', unit: 'km', step: 0.1, min: 0 },
  ],
  UNDERGROUND_CABLE: [
    { key: 'name',      label: 'Name',   type: 'text' },
    { key: 'length_km', label: 'Length', type: 'number', unit: 'km', step: 0.1, min: 0 },
  ],
  RESIDENTIAL_LOAD: [
    { key: 'name',  label: 'Name',  type: 'text' },
    { key: 'kw',    label: 'Power', type: 'number', unit: 'kW',   step: 0.5, min: 0 },
    { key: 'kvar',  label: 'kVAR',  type: 'number', unit: 'kVAR', step: 0.1, min: 0 },
    { key: 'phase', label: 'Phase', type: 'select', options: [
      { value: 1, label: 'Phase A' },
      { value: 2, label: 'Phase B' },
      { value: 3, label: 'Phase C' },
    ]},
  ],
  INDUSTRIAL_LOAD: [
    { key: 'name', label: 'Name',  type: 'text' },
    { key: 'kw',   label: 'Power', type: 'number', unit: 'kW',   step: 10, min: 0 },
    { key: 'kvar', label: 'kVAR',  type: 'number', unit: 'kVAR', step: 5,  min: 0 },
  ],
  SYNCHRONOUS_GENERATOR: [
    { key: 'name',         label: 'Name',     type: 'text' },
    { key: 'rated_kw',     label: 'Rating',   type: 'number', unit: 'kW',  step: 10,  min: 0 },
    { key: 'rated_kv',     label: 'Voltage',  type: 'number', unit: 'kV',  step: 0.1, min: 0 },
    { key: 'power_factor', label: 'PF',       type: 'number', unit: '',    step: 0.01, min: 0, max: 1 },
    { key: 'is_slack',     label: 'Slack bus',type: 'checkbox' },
  ],
  SOLAR_PV: [
    { key: 'name',                 label: 'Name',        type: 'text' },
    { key: 'kw_peak',              label: 'Peak power',  type: 'number', unit: 'kW',     step: 5,    min: 0 },
    { key: 'kva_rated',            label: 'Inverter',    type: 'number', unit: 'kVA',    step: 5,    min: 0 },
    { key: 'irradiance_kw_per_m2', label: 'Irradiance',  type: 'number', unit: 'kW/m²', step: 0.05, min: 0, max: 1.5 },
    { key: 'power_factor',         label: 'PF',          type: 'number', unit: '',       step: 0.01, min: -1, max: 1 },
  ],
}

export default function PropertiesPanel() {
  const { selectedNode, updateNodeData } = useGridStore()

  if (!selectedNode) {
    return (
      <div className="p-3 border-b border-gray-700">
        <p className="text-xs text-gray-600 uppercase tracking-widest mb-2">Properties</p>
        <p className="text-xs text-gray-600">
          Select a component on the canvas to edit its parameters.
        </p>
      </div>
    )
  }

  const fields = FIELD_DEFINITIONS[selectedNode.type] || []
  const data   = selectedNode.data

  const handleChange = (key, value) => {
    updateNodeData(selectedNode.id, { [key]: value })
  }

  return (
    <div className="p-3 border-b border-gray-700 overflow-y-auto max-h-80">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <p className="text-xs text-gray-500 uppercase tracking-widest">Properties</p>
        <span className="text-xs text-gray-600">— {selectedNode.type.replace(/_/g, ' ')}</span>
      </div>

      {/* Fields */}
      <div className="flex flex-col gap-2">
        {fields.map(field => (
          <div key={field.key} className="flex items-center justify-between gap-2">
            <label className="text-xs text-gray-400 shrink-0 w-20">
              {field.label}
            </label>

            {field.type === 'text' && (
              <input
                type="text"
                value={data[field.key] || ''}
                onChange={e => handleChange(field.key, e.target.value)}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
              />
            )}

            {field.type === 'number' && (
              <div className="flex items-center gap-1 flex-1">
                <input
                  type="number"
                  value={data[field.key] ?? ''}
                  step={field.step || 1}
                  min={field.min}
                  max={field.max}
                  onChange={e => handleChange(field.key, parseFloat(e.target.value))}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500 min-w-0"
                />
                {field.unit && (
                  <span className="text-xs text-gray-600 shrink-0">{field.unit}</span>
                )}
              </div>
            )}

            {field.type === 'select' && (
              <select
                value={data[field.key] ?? ''}
                onChange={e => handleChange(field.key, parseInt(e.target.value))}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
              >
                {field.options.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            )}

            {field.type === 'checkbox' && (
              <input
                type="checkbox"
                checked={data[field.key] || false}
                onChange={e => handleChange(field.key, e.target.checked)}
                className="w-4 h-4 accent-blue-500"
              />
            )}
          </div>
        ))}
      </div>

      {/* Node ID (read-only, useful for debugging) */}
      <p className="text-xs text-gray-700 mt-3 font-mono truncate">
        id: {selectedNode.id}
      </p>
    </div>
  )
}
