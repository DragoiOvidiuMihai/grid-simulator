/**
 * Sidebar.jsx — Component Library Panel
 * =======================================
 * Shows all 8 components as draggable cards.
 * Drag one onto the canvas to place it.
 */

import { COMPONENT_DEFINITIONS } from '../../store/gridStore'

const CATEGORIES = [
  {
    label: 'Nodes',
    types: ['BUS_MV', 'BUS_LV'],
  },
  {
    label: 'Connections',
    types: ['TRANSFORMER', 'OVERHEAD_LINE', 'UNDERGROUND_CABLE'],
  },
  {
    label: 'Loads',
    types: ['RESIDENTIAL_LOAD', 'INDUSTRIAL_LOAD'],
  },
  {
    label: 'Generation',
    types: ['SYNCHRONOUS_GENERATOR', 'SOLAR_PV'],
  },
]

export default function Sidebar() {
  const onDragStart = (event, componentType) => {
    // Store the component type in the drag event so the canvas knows what to create
    event.dataTransfer.setData('application/grid-component', componentType)
    event.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="p-2 flex flex-col gap-4">
      <p className="text-xs text-gray-500 uppercase tracking-widest pt-1 px-1">
        Components
      </p>

      {CATEGORIES.map(category => (
        <div key={category.label}>
          {/* Category label */}
          <p className="text-xs text-gray-600 uppercase tracking-widest mb-1 px-1">
            {category.label}
          </p>

          {/* Component cards */}
          <div className="flex flex-col gap-1">
            {category.types.map(type => {
              const def = COMPONENT_DEFINITIONS[type]
              return (
                <div
                  key={type}
                  draggable
                  onDragStart={e => onDragStart(e, type)}
                  className="flex items-center gap-2 px-2 py-2 rounded bg-gray-800 border border-gray-700 cursor-grab hover:border-gray-500 hover:bg-gray-750 transition-colors select-none"
                >
                  {/* Color indicator */}
                  <div
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: def.color }}
                  />
                  {/* Label + description */}
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-gray-200 truncate">
                      {def.label}
                    </p>
                    <p className="text-xs text-gray-500 truncate leading-tight">
                      {def.description}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {/* Instructions */}
      <div className="mt-2 p-2 rounded bg-gray-800 border border-gray-700">
        <p className="text-xs text-gray-500 leading-relaxed">
          Drag components onto the canvas. Connect buses with lines by dragging from a node handle.
        </p>
      </div>
    </div>
  )
}
