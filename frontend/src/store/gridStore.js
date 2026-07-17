/**
 * Grid Simulator — Global State Store
 * =====================================
 * Built with Zustand — a lightweight state management library.
 */

import { create } from 'zustand'
import { applyNodeChanges, applyEdgeChanges, addEdge } from 'reactflow'
import axios from 'axios'

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENT DEFINITIONS
// ─────────────────────────────────────────────────────────────────────────────

export const COMPONENT_DEFINITIONS = {
  BUS_MV: {
    type:        'BUS_MV',
    label:       'MV Bus',
    description: '11 kV medium voltage bus',
    color:       '#2E75B6',
    defaultData: { name: 'MV Bus', base_kv: 11.0, phases: 3 },
  },
  BUS_LV: {
    type:        'BUS_LV',
    label:       'LV Bus',
    description: '0.4 kV low voltage bus',
    color:       '#70AD47',
    defaultData: { name: 'LV Bus', base_kv: 0.4, phases: 3 },
  },
  TRANSFORMER: {
    type:        'TRANSFORMER',
    label:       'Transformer',
    description: 'Two-winding Dyn11, 11/0.4 kV',
    color:       '#ED7D31',
    defaultData: {
      name: 'Transformer', rating_kva: 500.0, primary_kv: 11.0,
      secondary_kv: 0.4, percent_r: 1.1, percent_x: 4.0,
      vector_group: 'Dyn11', phases: 3,
    },
  },
  OVERHEAD_LINE: {
    type:        'OVERHEAD_LINE',
    label:       'Overhead Line',
    description: 'ACSR 150mm², IEC 61089',
    color:       '#FFC000',
    defaultData: {
      name: 'Overhead Line', length_km: 1.0,
      r1_ohm_per_km: 0.196, x1_ohm_per_km: 0.332,
      r0_ohm_per_km: 0.588, x0_ohm_per_km: 0.996,
      ampacity_a: 415.0, phases: 3,
    },
  },
  UNDERGROUND_CABLE: {
    type:        'UNDERGROUND_CABLE',
    label:       'Underground Cable',
    description: '12/20kV XLPE 150mm² Cu, IEC 60502-2',
    color:       '#7030A0',
    defaultData: {
      name: 'Underground Cable', length_km: 0.5,
      r1_ohm_per_km: 0.124, x1_ohm_per_km: 0.113,
      r0_ohm_per_km: 0.372, x0_ohm_per_km: 0.113,
      c1_uf_per_km: 0.28, ampacity_a: 360.0, phases: 3,
    },
  },
  RESIDENTIAL_LOAD: {
    type:        'RESIDENTIAL_LOAD',
    label:       'Residential Load',
    description: 'Single-phase household',
    color:       '#C00000',
    defaultData: { name: 'House', kw: 5.0, kvar: 1.64, base_kv: 0.231, phase: 1, phases: 1 },
  },
  INDUSTRIAL_LOAD: {
    type:        'INDUSTRIAL_LOAD',
    label:       'Industrial Load',
    description: 'Three-phase factory / facility',
    color:       '#843C0C',
    defaultData: { name: 'Factory', kw: 250.0, kvar: 121.0, base_kv: 0.4, phases: 3 },
  },
  SYNCHRONOUS_GENERATOR: {
    type:        'SYNCHRONOUS_GENERATOR',
    label:       'Generator',
    description: 'Synchronous generator / diesel genset',
    color:       '#1F3864',
    defaultData: {
      name: 'Generator', rated_kw: 500.0, rated_kv: 0.4,
      power_factor: 0.8, kvar_max: 375.0, kvar_min: -375.0,
      phases: 3, is_slack: false,
    },
  },
  SOLAR_PV: {
    type:        'SOLAR_PV',
    label:       'Solar PV',
    description: 'Inverter-based PV system',
    color:       '#F4B942',
    defaultData: {
      name: 'Solar PV', kw_peak: 100.0, kva_rated: 102.0, rated_kv: 0.4,
      power_factor: 1.0, efficiency: 0.98, irradiance_kw_per_m2: 1.0,
      temp_coefficient_pct: -0.35, phases: 3,
    },
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// ID GENERATOR
// ─────────────────────────────────────────────────────────────────────────────

let _idCounter = 0
export const generateId = (type) => {
  _idCounter += 1
  return `${type}_${_idCounter}_${Date.now()}`
}

// ─────────────────────────────────────────────────────────────────────────────
// GRID → API PAYLOAD CONVERTER
// ─────────────────────────────────────────────────────────────────────────────

const buildGridPayload = (nodes, edges, gridId, gridName) => {
  const payload = {
    id: gridId, name: gridName,
    mv_buses: [], lv_buses: [], transformers: [],
    overhead_lines: [], underground_cables: [],
    residential_loads: [], industrial_loads: [],
    synchronous_generators: [], solar_pv_systems: [],
  }

  const nodeMap = {}
  nodes.forEach(n => { nodeMap[n.id] = n })

  nodes.forEach(node => {
    const { type, data } = node
    const id = node.id
    switch (type) {
      case 'BUS_MV':
        payload.mv_buses.push({ id, ...data })
        break
      case 'BUS_LV':
        payload.lv_buses.push({ id, ...data })
        break
      case 'RESIDENTIAL_LOAD':
        payload.residential_loads.push({ id, bus_id: data.bus_id || '', ...data })
        break
      case 'INDUSTRIAL_LOAD':
        payload.industrial_loads.push({ id, bus_id: data.bus_id || '', ...data })
        break
      case 'SYNCHRONOUS_GENERATOR':
        payload.synchronous_generators.push({ id, bus_id: data.bus_id || '', ...data })
        break
      case 'SOLAR_PV':
        payload.solar_pv_systems.push({ id, bus_id: data.bus_id || '', ...data })
        break
      default:
        break
    }
  })

  const loadTypes = ['RESIDENTIAL_LOAD', 'INDUSTRIAL_LOAD', 'SYNCHRONOUS_GENERATOR', 'SOLAR_PV']
  const busTypes  = ['BUS_MV', 'BUS_LV']

  edges.forEach(edge => {
    const { source, target, data = {}, id } = edge
    const srcNode = nodeMap[source]
    const tgtNode = nodeMap[target]
    if (!srcNode || !tgtNode) return

    // Skip load/generator edges — those only carry bus_id assignment
    if (loadTypes.includes(tgtNode.type) || loadTypes.includes(srcNode.type)) return

    // Skip non-bus edges
    if (!busTypes.includes(srcNode.type) || !busTypes.includes(tgtNode.type)) return

    // MV→LV = Transformer, anything else = Overhead Line (or explicit type)
    const isMvToLv  = srcNode.type === 'BUS_MV' && tgtNode.type === 'BUS_LV'
    const edgeType  = isMvToLv ? 'TRANSFORMER' : (data.componentType || 'OVERHEAD_LINE')

    switch (edgeType) {
      case 'TRANSFORMER':
        payload.transformers.push({
          id, from_bus_id: source, to_bus_id: target,
          name:         data.name         || 'Transformer',
          rating_kva:   data.rating_kva   || 500.0,
          primary_kv:   data.primary_kv   || 11.0,
          secondary_kv: data.secondary_kv || 0.4,
          percent_r:    data.percent_r    || 1.1,
          percent_x:    data.percent_x    || 4.0,
          vector_group: data.vector_group || 'Dyn11',
          phases:       data.phases       || 3,
        })
        break
      case 'OVERHEAD_LINE':
        payload.overhead_lines.push({
          id, from_bus_id: source, to_bus_id: target,
          name:           data.name           || 'Overhead Line',
          length_km:      data.length_km      || 1.0,
          r1_ohm_per_km:  data.r1_ohm_per_km  || 0.196,
          x1_ohm_per_km:  data.x1_ohm_per_km  || 0.332,
          r0_ohm_per_km:  data.r0_ohm_per_km  || 0.588,
          x0_ohm_per_km:  data.x0_ohm_per_km  || 0.996,
          ampacity_a:     data.ampacity_a     || 415.0,
          phases:         data.phases         || 3,
        })
        break
      case 'UNDERGROUND_CABLE':
        payload.underground_cables.push({
          id, from_bus_id: source, to_bus_id: target,
          name:           data.name           || 'Cable',
          length_km:      data.length_km      || 0.5,
          r1_ohm_per_km:  data.r1_ohm_per_km  || 0.124,
          x1_ohm_per_km:  data.x1_ohm_per_km  || 0.113,
          r0_ohm_per_km:  data.r0_ohm_per_km  || 0.372,
          x0_ohm_per_km:  data.x0_ohm_per_km  || 0.113,
          c1_uf_per_km:   data.c1_uf_per_km   || 0.28,
          ampacity_a:     data.ampacity_a     || 360.0,
          phases:         data.phases         || 3,
        })
        break
      default:
        break
    }
  })

  
  return payload
}

// ─────────────────────────────────────────────────────────────────────────────
// THE STORE
// ─────────────────────────────────────────────────────────────────────────────

export const useGridStore = create((set, get) => ({

  // ── React Flow state ──────────────────────────────────────────────────────
  nodes: [],
  edges: [],

  // ── UI state ──────────────────────────────────────────────────────────────
  selectedNode: null,
  gridName:     'My Grid',
  gridId:       'GRID_001',

  // ── Simulation state ──────────────────────────────────────────────────────
  simulationResult: null,
  timeSeriesResult: null,
  faultResult:      null,
  isSimulating:     false,
  simulationError:  null,

  // ── Mode ──────────────────────────────────────────────────────────────────
  simulationMode: 'snapshot',

  setSimulationMode: (mode) => set({
    simulationMode:   mode,
    simulationResult: null,
    timeSeriesResult: null,
    faultResult:      null,
    simulationError:  null,
    selectedTimeStep: 0,
  }),

  // ── Time-series state ──────────────────────────────────────────────────────
  selectedTimeStep: 0,
  tsSeason:         'summer',
  tsMultiplier:     1.0,

  setTsSeason:         (season)     => set({ tsSeason: season }),
  setTsMultiplier:     (multiplier) => set({ tsMultiplier: multiplier }),
  setSelectedTimeStep: (step)       => set({ selectedTimeStep: step }),

  // ── React Flow handlers ───────────────────────────────────────────────────

  onNodesChange: (changes) => {
    set(state => ({ nodes: applyNodeChanges(changes, state.nodes) }))
  },

  onEdgesChange: (changes) => {
    set(state => ({ edges: applyEdgeChanges(changes, state.edges) }))
  },

  onConnect: (connection) => {
    const { nodes, edges } = get()
    const srcNode = nodes.find(n => n.id === connection.source)
    const tgtNode = nodes.find(n => n.id === connection.target)
    const newEdges = addEdge(connection, edges)

    const loadTypes = ['RESIDENTIAL_LOAD', 'INDUSTRIAL_LOAD', 'SYNCHRONOUS_GENERATOR', 'SOLAR_PV']

    // Bus → Load/Generator: assign bus_id to the component
    if (tgtNode && loadTypes.includes(tgtNode.type)) {
      set({
        edges: newEdges,
        nodes: nodes.map(n =>
          n.id === tgtNode.id
            ? { ...n, data: { ...n.data, bus_id: connection.source } }
            : n
        ),
      })
      return
    }

    // Bus → Bus: create labelled edge with component data attached
    const isMvToLv      = srcNode?.type === 'BUS_MV' && tgtNode?.type === 'BUS_LV'
    const componentType = isMvToLv ? 'TRANSFORMER' : 'OVERHEAD_LINE'
    const def           = COMPONENT_DEFINITIONS[componentType]

    const labelledEdges = newEdges.map(e => {
      if (e.source === connection.source && e.target === connection.target) {
        return {
          ...e,
          label:          isMvToLv ? 'TX (Dyn11)' : 'OHL',
          labelStyle:     { fontSize: 9, fill: '#9CA3AF' },
          labelBgStyle:   { fill: '#1F2937', fillOpacity: 0.8 },
          data:           { componentType, ...def.defaultData },
        }
      }
      return e
    })
    set({ edges: labelledEdges })
  },

  // ── Node management ───────────────────────────────────────────────────────

  addNode: (componentType, position) => {
    const def = COMPONENT_DEFINITIONS[componentType]
    if (!def) return
    const id      = generateId(componentType)
    const newNode = {
      id,
      type:     componentType,
      position: position || { x: 200, y: 200 },
      data:     { id, ...def.defaultData, label: `${def.defaultData.name} ${_idCounter}` },
    }
    set(state => ({ nodes: [...state.nodes, newNode] }))
  },

  selectNode: (nodeId) => {
    const node = get().nodes.find(n => n.id === nodeId) || null
    set({ selectedNode: node })
  },

  clearSelection: () => set({ selectedNode: null }),

  updateNodeData: (nodeId, newData) => {
    set(state => ({
      nodes: state.nodes.map(n =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...newData } } : n
      ),
      selectedNode: state.selectedNode?.id === nodeId
        ? { ...state.selectedNode, data: { ...state.selectedNode.data, ...newData } }
        : state.selectedNode,
    }))
  },

  // ── Simulations ───────────────────────────────────────────────────────────

  runSimulation: async () => {
    const { nodes, edges, gridId, gridName } = get()
    if (nodes.length === 0) {
      set({ simulationError: 'Add at least one component to the canvas before simulating.' })
      return
    }
    set({ isSimulating: true, simulationError: null, simulationResult: null })
    try {
      const payload  = buildGridPayload(nodes, edges, gridId, gridName)
      const response = await axios.post('/simulate', payload)
      set({ simulationResult: response.data, isSimulating: false })
    } catch (err) {
      const raw    = err.response?.data?.detail
      const detail = Array.isArray(raw)
        ? raw.map(e => `${e.loc?.join('.')} — ${e.msg}`).join('\n')
        : typeof raw === 'string' ? raw : err.message || 'Unknown error'
      set({ simulationError: detail, isSimulating: false })
    }
  },

  runTimeSeriesSimulation: async () => {
    const { nodes, edges, gridId, gridName, tsSeason, tsMultiplier } = get()
    if (nodes.length === 0) {
      set({ simulationError: 'Add at least one component before simulating.' })
      return
    }
    set({ isSimulating: true, simulationError: null, timeSeriesResult: null })
    try {
      const grid     = buildGridPayload(nodes, edges, gridId, gridName)
      const payload  = { grid, season: tsSeason, peak_load_multiplier: tsMultiplier }
      const response = await axios.post('/simulate-timeseries', payload)
      set({ timeSeriesResult: response.data, selectedTimeStep: 0, isSimulating: false })
    } catch (err) {
      const raw    = err.response?.data?.detail
      const detail = Array.isArray(raw)
        ? raw.map(e => `${e.loc?.join('.')} — ${e.msg}`).join('\n')
        : typeof raw === 'string' ? raw : err.message || 'Unknown error'
      set({ simulationError: detail, isSimulating: false })
    }
  },

  runFaultStudy: async () => {
    const { nodes, edges, gridId, gridName } = get()
    if (nodes.length === 0) {
      set({ simulationError: 'Add at least one component before running a fault study.' })
      return
    }
    set({ isSimulating: true, simulationError: null, faultResult: null })
    try {
      const payload  = buildGridPayload(nodes, edges, gridId, gridName)
      const response = await axios.post('/fault-study', payload)
      set({ faultResult: response.data, isSimulating: false })
    } catch (err) {
      const raw    = err.response?.data?.detail
      const detail = Array.isArray(raw)
        ? raw.map(e => `${e.loc?.join('.')} — ${e.msg}`).join('\n')
        : typeof raw === 'string' ? raw : err.message || 'Unknown error'
      set({ simulationError: detail, isSimulating: false })
    }
  },

  // ── Results management ────────────────────────────────────────────────────

  clearResults: () => set({
    simulationResult: null,
    timeSeriesResult: null,
    faultResult:      null,
    simulationError:  null,
  }),

  clearGrid: () => set({
    nodes:            [],
    edges:            [],
    selectedNode:     null,
    simulationResult: null,
    timeSeriesResult: null,
    faultResult:      null,
    simulationError:  null,
    selectedTimeStep: 0,
  }),

  setGridName: (name) => set({ gridName: name }),

  // ── Save / Load ───────────────────────────────────────────────────────────

  getSavedGridNames: () => {
    try {
      const index = localStorage.getItem('grid_simulator_index')
      return index ? JSON.parse(index) : []
    } catch { return [] }
  },

  saveGrid: (saveName) => {
    try {
      const { nodes, edges, gridName, gridId } = get()
      const key  = `grid_simulator_save_${saveName}`
      const data = { nodes, edges, gridName, gridId, savedAt: new Date().toISOString() }
      localStorage.setItem(key, JSON.stringify(data))
      const index = get().getSavedGridNames()
      if (!index.includes(saveName)) {
        localStorage.setItem('grid_simulator_index', JSON.stringify([...index, saveName]))
      }
      return true
    } catch { return false }
  },

  loadGrid: (saveName) => {
    try {
      const key  = `grid_simulator_save_${saveName}`
      const raw  = localStorage.getItem(key)
      if (!raw) return false
      const data = JSON.parse(raw)
      set({
        nodes:            data.nodes    || [],
        edges:            data.edges    || [],
        gridName:         data.gridName || saveName,
        gridId:           data.gridId   || 'GRID_001',
        selectedNode:     null,
        simulationResult: null,
        timeSeriesResult: null,
        faultResult:      null,
        simulationError:  null,
        selectedTimeStep: 0,
      })
      return true
    } catch { return false }
  },

  deleteGrid: (saveName) => {
    try {
      localStorage.removeItem(`grid_simulator_save_${saveName}`)
      const index = get().getSavedGridNames().filter(n => n !== saveName)
      localStorage.setItem('grid_simulator_index', JSON.stringify(index))
      return true
    } catch { return false }
  },

}))
