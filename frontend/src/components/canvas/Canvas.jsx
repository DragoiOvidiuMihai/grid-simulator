/**
 * Canvas.jsx — React Flow Diagram
 * =================================
 * The main interactive canvas where users build their grid.
 * Handles drag-and-drop from the sidebar, node selection, and displays
 * simulation results overlaid on nodes after a simulation runs.
 */

import { useCallback, useRef } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { useGridStore, COMPONENT_DEFINITIONS, generateId } from '../../store/gridStore'
import GridNode from './GridNode'

// Register our custom node types with React Flow
// Every component type maps to the same GridNode renderer —
// it adapts its appearance based on the node's type and data
const nodeTypes = {
  BUS_MV:                GridNode,
  BUS_LV:                GridNode,
  TRANSFORMER:           GridNode,
  OVERHEAD_LINE:         GridNode,
  UNDERGROUND_CABLE:     GridNode,
  RESIDENTIAL_LOAD:      GridNode,
  INDUSTRIAL_LOAD:       GridNode,
  SYNCHRONOUS_GENERATOR: GridNode,
  SOLAR_PV:              GridNode,
}

export default function Canvas() {
  const reactFlowWrapper = useRef(null)
  const {
    nodes, edges,
    onNodesChange, onEdgesChange, onConnect,
    addNode, selectNode, clearSelection,
    simulationResult,
  } = useGridStore()

  // ── Drop handler ─────────────────────────────────────────────────────────
  // When a component is dragged from the sidebar and dropped on the canvas,
  // calculate the canvas position and create a new node there.

  const onDrop = useCallback((event) => {
    event.preventDefault()

    const componentType = event.dataTransfer.getData('application/grid-component')
    if (!componentType) return

    // Convert screen coordinates to React Flow canvas coordinates
    const bounds = reactFlowWrapper.current.getBoundingClientRect()
    const position = {
      x: event.clientX - bounds.left - 60,
      y: event.clientY - bounds.top  - 20,
    }

    addNode(componentType, position)
  }, [addNode])

  const onDragOver = useCallback((event) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  // ── Node click handler ────────────────────────────────────────────────────
  const onNodeClick = useCallback((event, node) => {
    selectNode(node.id)
  }, [selectNode])

  const onPaneClick = useCallback(() => {
    clearSelection()
  }, [clearSelection])

  return (
    <div ref={reactFlowWrapper} className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode="Delete"
        className="bg-gray-950"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="#374151"
        />
        <Controls className="bg-gray-800 border-gray-700" />
        <MiniMap
          nodeColor={node => COMPONENT_DEFINITIONS[node.type]?.color || '#666'}
          className="bg-gray-900 border border-gray-700"
        />

        {/* Empty state message */}
        {nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <p className="text-gray-600 text-sm">Canvas is empty</p>
              <p className="text-gray-700 text-xs mt-1">
                Drag components from the left panel to begin
              </p>
            </div>
          </div>
        )}
      </ReactFlow>
    </div>
  )
}
