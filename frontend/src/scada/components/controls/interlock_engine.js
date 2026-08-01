/**
 * interlock_engine.js — Frontend Interlock Engine
 * ================================================
 * Evaluates whether a breaker operation is permitted before the command
 * is sent to the backend. This mirrors real substation interlock practice
 * where hardware/software interlocks prevent dangerous switching sequences.
 *
 * Each rule returns one of three outcomes:
 *   BLOCKED  — operation must not proceed (hard interlock)
 *   WARNING  — operation is allowed but operator should be aware of consequences
 *   ALLOWED  — no issues found
 *
 * Rules implemented:
 *   NO_PARALLEL_SOURCES  — CB3 cannot close while CB1 AND CB2 are both closed
 *                          (would parallel two independent 11kV sources without
 *                          synchronisation check — dangerous in real systems)
 *   NO_DEAD_CLOSE        — Cannot close a breaker onto a de-energised upstream bus
 *                          (closing onto an unknown network state)
 *   LAST_SOURCE_WARNING  — Opening the only source feeding live loads triggers warning
 *   COUPLER_ISLAND       — Closing CB3 when one feeder is lost is the correct recovery
 *                          action — engine should ALLOW and inform, not block
 *
 * Usage:
 *   import { evaluateOperation } from './interlock_engine'
 *   const result = evaluateOperation('CB3', 'CLOSE', currentBreakerStates)
 *   // result: { outcome: 'BLOCKED'|'WARNING'|'ALLOWED', rules: [...] }
 */

// ─────────────────────────────────────────────────────────────────────────────
// TOPOLOGY HELPERS
// Mirror of data_source.py _is_energised() — must stay in sync with backend.
// ─────────────────────────────────────────────────────────────────────────────

function isEnergised(busId, bs) {
  const cb = (id) => bs[id] === 'CLOSED'

  switch (busId) {
    case 'BUS_A': return cb('CB1')
    case 'BUS_B': return cb('CB2') || (cb('CB3') && isEnergised('BUS_A', bs))
    case 'BUS_C': return isEnergised('BUS_A', bs) && cb('CB4')
    case 'BUS_D': return isEnergised('BUS_B', bs) && cb('CB5')
    default:      return false
  }
}

// Which bus does a breaker connect FROM (upstream side)?
const BREAKER_UPSTREAM_BUS = {
  CB1: null,      // CB1 connects from external feeder (always energised source)
  CB2: null,      // CB2 connects from external feeder
  CB3: 'BUS_A',  // Coupler: upstream is Bus A
  CB4: 'BUS_A',
  CB5: 'BUS_B',
  CB6: 'BUS_C',
  CB7: 'BUS_C',
  CB8: 'BUS_D',
  CB9: 'BUS_D',
}

// Which bus does a breaker feed INTO (downstream side)?
const BREAKER_DOWNSTREAM = {
  CB1: 'BUS_A',
  CB2: 'BUS_B',
  CB3: 'BUS_B',   // Coupler feeds Bus B from Bus A
  CB4: 'TX1',
  CB5: 'TX2',
  CB6: 'LOAD1',
  CB7: 'PV1',
  CB8: 'LOAD2',
  CB9: 'LOAD3',
}

// Human-readable names for breakers
export const BREAKER_NAMES = {
  CB1: 'Feeder 1 Incomer',
  CB2: 'Feeder 2 Incomer',
  CB3: 'Bus Coupler (A ↔ B)',
  CB4: 'TX1 HV Isolator',
  CB5: 'TX2 HV Isolator',
  CB6: 'Load 1 Feeder',
  CB7: 'PV 1 Feeder',
  CB8: 'Load 2 Feeder',
  CB9: 'Load 3 Feeder',
}

// ─────────────────────────────────────────────────────────────────────────────
// RULE DEFINITIONS
// Each rule is a function(breakerId, command, breakerStates) → result | null
// Return null if rule does not apply.
// ─────────────────────────────────────────────────────────────────────────────

const RULES = [

  // ── Rule 1: No parallel sources via coupler ─────────────────────────────
  {
    id:   'NO_PARALLEL_SOURCES',
    name: 'Parallel Source Interlock',
    check(breakerId, command, bs) {
      if (breakerId !== 'CB3' || command !== 'CLOSE') return null
      const cb1Closed = bs['CB1'] === 'CLOSED'
      const cb2Closed = bs['CB2'] === 'CLOSED'
      if (cb1Closed && cb2Closed) {
        return {
          outcome: 'BLOCKED',
          message:
            'Cannot close bus coupler CB3 while both Feeder 1 (CB1) and ' +
            'Feeder 2 (CB2) are closed. Closing CB3 would parallel two ' +
            'independent 11kV sources without synchronisation. Open CB1 ' +
            'or CB2 before closing the coupler.',
        }
      }
      return null
    },
  },

  // ── Rule 2: Coupler close — correct recovery action ─────────────────────
  {
    id:   'COUPLER_RECOVERY',
    name: 'Bus Coupler Recovery',
    check(breakerId, command, bs) {
      if (breakerId !== 'CB3' || command !== 'CLOSE') return null
      const cb1Closed = bs['CB1'] === 'CLOSED'
      const cb2Closed = bs['CB2'] === 'CLOSED'
      // One feeder lost — this is the correct recovery action
      if (cb1Closed !== cb2Closed) {
        const lostFeeder = cb1Closed ? 'Feeder 2 (CB2)' : 'Feeder 1 (CB1)'
        const activeFeeder = cb1Closed ? 'Feeder 1 (CB1)' : 'Feeder 2 (CB2)'
        return {
          outcome: 'WARNING',
          message:
            `${lostFeeder} is open. Closing CB3 will restore supply to the ` +
            `de-energised busbar via ${activeFeeder}. This is the correct ` +
            `loss-of-supply recovery switching sequence. Confirm before proceeding.`,
        }
      }
      return null
    },
  },

  // ── Rule 3: Dead close warning ───────────────────────────────────────────
  {
    id:   'DEAD_BUS_CLOSE',
    name: 'Dead Bus Close Warning',
    check(breakerId, command, bs) {
      if (command !== 'CLOSE') return null
      const upstreamBus = BREAKER_UPSTREAM_BUS[breakerId]
      if (upstreamBus === null) return null  // feeder incomers — always live
      if (!isEnergised(upstreamBus, bs)) {
        return {
          outcome: 'BLOCKED',
          message:
            `Cannot close ${breakerId} — upstream bus ${upstreamBus} is ` +
            `de-energised. Restore supply to ${upstreamBus} before ` +
            `closing this breaker.`,
        }
      }
      return null
    },
  },

  // ── Rule 4: Last source warning ──────────────────────────────────────────
  {
    id:   'LAST_SOURCE',
    name: 'Last Source Warning',
    check(breakerId, command, bs) {
      if (command !== 'OPEN') return null

      // Simulate the new state after opening this breaker
      const newBs = { ...bs, [breakerId]: 'OPEN' }

      // Check if any load-serving bus becomes de-energised
      const busCAffected = isEnergised('BUS_C', bs) && !isEnergised('BUS_C', newBs)
      const busDAffected = isEnergised('BUS_D', bs) && !isEnergised('BUS_D', newBs)

      if (busCAffected || busDAffected) {
        const affected = [
          busCAffected ? 'Bus C (Load 1, PV 1)' : null,
          busDAffected ? 'Bus D (Load 2, Load 3)' : null,
        ].filter(Boolean).join(' and ')

        return {
          outcome: 'WARNING',
          message:
            `Opening ${breakerId} will de-energise ${affected}. ` +
            `Affected loads will lose supply. Confirm this is the intended action.`,
        }
      }
      return null
    },
  },

  // ── Rule 5: TX isolator open warning ────────────────────────────────────
  {
    id:   'TX_ISOLATOR',
    name: 'Transformer Isolator Warning',
    check(breakerId, command, bs) {
      if (command !== 'OPEN') return null
      if (breakerId !== 'CB4' && breakerId !== 'CB5') return null

      const txLabel = breakerId === 'CB4' ? 'TX1' : 'TX2'
      const lvBus   = breakerId === 'CB4' ? 'BUS_C' : 'BUS_D'

      if (isEnergised(lvBus, bs)) {
        return {
          outcome: 'WARNING',
          message:
            `Opening ${breakerId} will isolate ${txLabel} and de-energise ` +
            `${lvBus}. Open the LV feeder breakers (` +
            (breakerId === 'CB4' ? 'CB6, CB7' : 'CB8, CB9') +
            `) first to de-load the transformer before isolating.`,
        }
      }
      return null
    },
  },

]

// ─────────────────────────────────────────────────────────────────────────────
// PUBLIC API
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Evaluate whether a breaker operation is permitted.
 *
 * @param {string} breakerId   — e.g. 'CB3'
 * @param {string} command     — 'OPEN' | 'CLOSE'
 * @param {object} breakerStates — current breaker state map
 *
 * @returns {{
 *   outcome:  'ALLOWED' | 'WARNING' | 'BLOCKED',
 *   findings: Array<{ ruleId, ruleName, outcome, message }>
 * }}
 */
export function evaluateOperation(breakerId, command, breakerStates) {
  const findings = []

  for (const rule of RULES) {
    const result = rule.check(breakerId, command, breakerStates)
    if (result) {
      findings.push({
        ruleId:   rule.id,
        ruleName: rule.name,
        outcome:  result.outcome,
        message:  result.message,
      })
    }
  }

  // Overall outcome: worst finding wins
  // BLOCKED > WARNING > ALLOWED
  let outcome = 'ALLOWED'
  for (const f of findings) {
    if (f.outcome === 'BLOCKED') { outcome = 'BLOCKED'; break }
    if (f.outcome === 'WARNING') outcome = 'WARNING'
  }

  return { outcome, findings }
}

/**
 * Return a short summary of what this breaker does in the topology.
 */
export function breakerDescription(breakerId) {
  return BREAKER_NAMES[breakerId] ?? breakerId
}
