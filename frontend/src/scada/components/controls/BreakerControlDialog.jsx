/**
 * BreakerControlDialog.jsx — Breaker Control Modal
 * =================================================
 * Shown when the operator clicks a breaker on the single-line diagram.
 *
 * Structure:
 *   Header      — breaker ID, name, current state badge
 *   Interlock   — evaluation result for the proposed operation
 *   Action area — OPEN / CLOSE buttons (disabled if BLOCKED)
 *   Footer      — cancel button
 *
 * The dialog evaluates interlocks live as the operator hovers over each
 * action button, so they see the consequence before clicking.
 *
 * Props:
 *   breakerId     {string}   — e.g. 'CB3'
 *   breakerStates {object}   — full current breaker state map
 *   onCommand     {function} — called with (breakerId, command) on confirm
 *   onClose       {function} — called when dialog should close
 */

import { useState } from 'react'
import { evaluateOperation, breakerDescription } from './interlock_engine'

// ─────────────────────────────────────────────────────────────────────────────
// OUTCOME STYLES
// ─────────────────────────────────────────────────────────────────────────────

const OUTCOME_STYLE = {
  ALLOWED: {
    border: 'border-green-800',
    bg:     'bg-green-950',
    icon:   '✓',
    colour: 'text-green-400',
    label:  'Permitted',
  },
  WARNING: {
    border: 'border-yellow-700',
    bg:     'bg-yellow-950',
    icon:   '⚠',
    colour: 'text-yellow-400',
    label:  'Warning',
  },
  BLOCKED: {
    border: 'border-red-800',
    bg:     'bg-red-950',
    icon:   '✕',
    colour: 'text-red-400',
    label:  'Blocked',
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERLOCK RESULT PANEL
// ─────────────────────────────────────────────────────────────────────────────

function InterlockPanel({ breakerId, command, breakerStates }) {
  if (!command) {
    return (
      <div className="border border-gray-800 rounded p-3 text-xs text-gray-600 font-mono">
        Select an operation to evaluate interlocks.
      </div>
    )
  }

  const { outcome, findings } = evaluateOperation(breakerId, command, breakerStates)
  const style = OUTCOME_STYLE[outcome]

  return (
    <div className={`border ${style.border} ${style.bg} rounded p-3 space-y-2`}>
      {/* Overall result */}
      <div className="flex items-center gap-2">
        <span className={`font-bold text-sm ${style.colour}`}>{style.icon}</span>
        <span className={`text-xs font-bold tracking-widest ${style.colour} uppercase`}>
          {style.label}
        </span>
        <span className="text-xs text-gray-600 ml-auto font-mono">
          {command} {breakerId}
        </span>
      </div>

      {/* Individual findings */}
      {findings.length === 0 && (
        <p className="text-xs text-green-600 font-mono">
          No interlock conditions triggered. Operation is clear.
        </p>
      )}
      {findings.map((f) => {
        const fs = OUTCOME_STYLE[f.outcome]
        return (
          <div key={f.ruleId} className="space-y-1">
            <div className="flex items-center gap-1.5">
              <span className={`text-xs ${fs.colour}`}>{fs.icon}</span>
              <span className="text-xs text-gray-400 font-mono font-bold">{f.ruleName}</span>
            </div>
            <p className="text-xs text-gray-400 font-mono leading-relaxed pl-4">
              {f.message}
            </p>
          </div>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN DIALOG
// ─────────────────────────────────────────────────────────────────────────────

export default function BreakerControlDialog({
  breakerId,
  breakerStates,
  onCommand,
  onClose,
}) {
  const [hoveredCommand, setHoveredCommand] = useState(null)
  const [pendingCommand, setPendingCommand] = useState(null)
  const [confirming,    setConfirming]      = useState(false)

  const currentState = breakerStates[breakerId] ?? 'UNKNOWN'
  const description  = breakerDescription(breakerId)

  // The command being previewed in the interlock panel
  const previewCommand = pendingCommand ?? hoveredCommand

  // Evaluate both operations up front so we know which buttons to disable
  const openEval  = evaluateOperation(breakerId, 'OPEN',  breakerStates)
  const closeEval = evaluateOperation(breakerId, 'CLOSE', breakerStates)

  function handleCommandClick(command) {
    const eval_ = command === 'OPEN' ? openEval : closeEval
    if (eval_.outcome === 'BLOCKED') return   // hard block — button should be disabled
    setPendingCommand(command)
    setConfirming(true)
  }

  function handleConfirm() {
    if (pendingCommand) {
      onCommand(breakerId, pendingCommand)
      onClose()
    }
  }

  function handleCancel() {
    if (confirming) {
      setPendingCommand(null)
      setConfirming(false)
    } else {
      onClose()
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/70 z-40"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
                      w-full max-w-md bg-gray-900 border border-gray-700 rounded-lg
                      shadow-2xl font-mono overflow-hidden">

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-gray-700 bg-gray-900">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <span className="text-lg font-bold text-gray-100">{breakerId}</span>
              {/* State badge */}
              <span className={`text-xs font-bold px-2 py-0.5 rounded border ${
                currentState === 'CLOSED'
                  ? 'border-green-700 bg-green-950 text-green-400'
                  : 'border-gray-600 bg-gray-800 text-gray-400'
              }`}>
                {currentState}
              </span>
            </div>
            <p className="text-xs text-gray-500">{description}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-600 hover:text-gray-300 text-lg leading-none mt-0.5"
          >
            ✕
          </button>
        </div>

        {/* ── Body ────────────────────────────────────────────────────── */}
        <div className="px-5 py-4 space-y-4">

          {!confirming ? (
            <>
              {/* Action buttons */}
              <div className="grid grid-cols-2 gap-3">

                {/* OPEN button */}
                <ActionButton
                  label="OPEN"
                  command="OPEN"
                  currentState={currentState}
                  eval_={openEval}
                  onHover={setHoveredCommand}
                  onClick={handleCommandClick}
                />

                {/* CLOSE button */}
                <ActionButton
                  label="CLOSE"
                  command="CLOSE"
                  currentState={currentState}
                  eval_={closeEval}
                  onHover={setHoveredCommand}
                  onClick={handleCommandClick}
                />

              </div>

              {/* Interlock panel — shows result for hovered command */}
              <InterlockPanel
                breakerId={breakerId}
                command={previewCommand}
                breakerStates={breakerStates}
              />
            </>
          ) : (
            <>
              {/* Confirmation step */}
              <div className="space-y-1">
                <p className="text-xs text-gray-500 uppercase tracking-widest">Confirm Operation</p>
                <p className="text-sm text-gray-200">
                  Send command:{' '}
                  <span className={`font-bold ${
                    pendingCommand === 'OPEN' ? 'text-yellow-400' : 'text-green-400'
                  }`}>
                    {pendingCommand} {breakerId}
                  </span>
                  ?
                </p>
              </div>

              {/* Show interlock result for this specific command */}
              <InterlockPanel
                breakerId={breakerId}
                command={pendingCommand}
                breakerStates={breakerStates}
              />
            </>
          )}

        </div>

        {/* ── Footer ──────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 px-5 py-3 border-t border-gray-700 bg-gray-950">
          <button
            onClick={handleCancel}
            className="px-4 py-1.5 text-xs text-gray-400 border border-gray-700
                       rounded hover:bg-gray-800 hover:text-gray-200 transition-colors"
          >
            {confirming ? 'Back' : 'Cancel'}
          </button>

          {confirming && (
            <button
              onClick={handleConfirm}
              className={`px-4 py-1.5 text-xs font-bold rounded border transition-colors ${
                pendingCommand === 'OPEN'
                  ? 'border-yellow-700 bg-yellow-950 text-yellow-400 hover:bg-yellow-900'
                  : 'border-green-700 bg-green-950 text-green-400 hover:bg-green-900'
              }`}
            >
              Confirm {pendingCommand}
            </button>
          )}
        </div>

      </div>
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ACTION BUTTON
// ─────────────────────────────────────────────────────────────────────────────

function ActionButton({ label, command, currentState, eval_, onHover, onClick }) {
  const isCurrentState = currentState === command ||
    (command === 'OPEN'  && currentState === 'OPEN') ||
    (command === 'CLOSE' && currentState === 'CLOSED')

  const isBlocked  = eval_.outcome === 'BLOCKED'
  const isWarning  = eval_.outcome === 'WARNING'
  const isCurrent  = isCurrentState
  const isDisabled = isBlocked || isCurrent

  let classes = 'relative px-4 py-3 rounded border text-xs font-bold transition-colors '

  if (isCurrent) {
    classes += 'border-gray-700 bg-gray-800 text-gray-600 cursor-default '
  } else if (isBlocked) {
    classes += 'border-red-900 bg-red-950/30 text-red-800 cursor-not-allowed '
  } else if (isWarning) {
    classes += command === 'OPEN'
      ? 'border-yellow-700 bg-yellow-950 text-yellow-400 hover:bg-yellow-900 cursor-pointer '
      : 'border-yellow-700 bg-yellow-950 text-yellow-400 hover:bg-yellow-900 cursor-pointer '
  } else {
    classes += command === 'OPEN'
      ? 'border-orange-700 bg-orange-950 text-orange-400 hover:bg-orange-900 cursor-pointer '
      : 'border-green-700 bg-green-950 text-green-400 hover:bg-green-900 cursor-pointer '
  }

  return (
    <button
      className={classes}
      disabled={isDisabled}
      onMouseEnter={() => !isDisabled && onHover(command)}
      onMouseLeave={() => onHover(null)}
      onClick={() => !isDisabled && onClick(command)}
    >
      <span className="block text-center tracking-widest">{label}</span>
      {isCurrent  && <span className="block text-center text-[10px] mt-0.5 text-gray-600">current state</span>}
      {isBlocked  && !isCurrent && <span className="block text-center text-[10px] mt-0.5">INTERLOCKED</span>}
      {isWarning  && !isCurrent && <span className="block text-center text-[10px] mt-0.5">⚠ with warning</span>}
    </button>
  )
}
