/**
 * scadaStore.js — Zustand store for SCADA/HMI state
 * ==================================================
 * Phase 4: adds alarms array and ackAlarm action.
 */

import { create } from 'zustand'

const INITIAL_BREAKER_STATES = {
  CB1: 'CLOSED', CB2: 'CLOSED', CB3: 'OPEN',
  CB4: 'CLOSED', CB5: 'CLOSED', CB6: 'CLOSED',
  CB7: 'CLOSED', CB8: 'CLOSED', CB9: 'CLOSED',
}

export const useScadaStore = create((set, get) => ({

  // ── Connection ─────────────────────────────────────────────────────────────
  wsStatus:    'disconnected',
  wsRef:       null,
  lastUpdated: null,

  // ── Live data ──────────────────────────────────────────────────────────────
  buses:         {},
  branches:      {},
  transformers:  {},
  breakerStates: INITIAL_BREAKER_STATES,

  // ── Alarms ─────────────────────────────────────────────────────────────────
  alarms: [],   // Array of alarm objects from backend

  // ── Actions ────────────────────────────────────────────────────────────────

  setWsStatus: (status) => set({ wsStatus: status }),
  setWsRef:    (ref)    => set({ wsRef: ref }),

  /**
   * Called by useWebSocket when a state_update packet arrives.
   */
  applyStateUpdate: (packet) => {
    set({
      buses:         packet.buses          ?? {},
      branches:      packet.branches       ?? {},
      transformers:  packet.transformers   ?? {},
      breakerStates: packet.breaker_states ?? get().breakerStates,
      lastUpdated:   packet.timestamp      ?? new Date().toISOString(),
      alarms:        packet.alarms         ?? [],
    })
  },

  /**
   * Send a breaker command via WebSocket.
   */
  sendBreakerCommand: (breakerId, command) => {
    const ws = get().wsRef
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[SCADA] WebSocket not open — cannot send breaker command')
      return
    }
    ws.send(JSON.stringify({ type: 'breaker_command', breaker_id: breakerId, command }))
  },

  /**
   * Send an alarm acknowledgement via WebSocket.
   */
  ackAlarm: (alarmId) => {
    const ws = get().wsRef
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[SCADA] WebSocket not open — cannot send alarm ack')
      return
    }
    ws.send(JSON.stringify({ type: 'alarm_ack', alarm_id: alarmId }))
  },

}))
