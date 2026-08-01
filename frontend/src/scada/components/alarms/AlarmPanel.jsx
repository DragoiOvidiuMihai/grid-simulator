/**
 * AlarmPanel.jsx — SCADA Alarm Panel
 * =====================================
 * Displays active and acknowledged alarms with acknowledgement workflow.
 *
 * Layout:
 *   Header     — alarm count badge, unacknowledged count
 *   Active     — unacknowledged alarms (flashing border for HIGH priority)
 *   Acknowledged — acknowledged alarms (muted, collapsible)
 *
 * Props:
 *   alarms   {Array}    — alarm objects from scadaStore
 *   onAck    {function} — called with alarm_id when operator clicks ACK
 */

import { useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// PRIORITY STYLES
// ─────────────────────────────────────────────────────────────────────────────

const PRIORITY_STYLE = {
  HIGH: {
    border:  'border-red-700',
    bg:      'bg-red-950/60',
    badge:   'bg-red-900 text-red-300 border-red-700',
    dot:     'bg-red-500',
    text:    'text-red-300',
    pulse:   'animate-pulse',
  },
  MEDIUM: {
    border:  'border-yellow-700',
    bg:      'bg-yellow-950/40',
    badge:   'bg-yellow-900 text-yellow-300 border-yellow-800',
    dot:     'bg-yellow-400',
    text:    'text-yellow-300',
    pulse:   '',
  },
  LOW: {
    border:  'border-blue-800',
    bg:      'bg-blue-950/30',
    badge:   'bg-blue-900 text-blue-300 border-blue-800',
    dot:     'bg-blue-400',
    text:    'text-blue-300',
    pulse:   '',
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// SINGLE ALARM ROW
// ─────────────────────────────────────────────────────────────────────────────

function AlarmRow({ alarm, onAck, dimmed = false }) {
  const style    = PRIORITY_STYLE[alarm.priority] ?? PRIORITY_STYLE.MEDIUM
  const isActive = alarm.state === 'ACTIVE'

  const raisedTime = new Date(alarm.raised_at).toLocaleTimeString()
  const ackedTime  = alarm.acked_at ? new Date(alarm.acked_at).toLocaleTimeString() : null

  return (
    <div className={`
      border rounded p-3 space-y-1.5 transition-opacity
      ${dimmed ? 'opacity-50' : ''}
      ${isActive ? `${style.border} ${style.bg}` : 'border-gray-800 bg-gray-900/40'}
    `}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* Priority dot — pulses for unacknowledged HIGH */}
          <div className={`
            w-2 h-2 rounded-full shrink-0
            ${isActive ? style.dot : 'bg-gray-600'}
            ${isActive && alarm.priority === 'HIGH' ? style.pulse : ''}
          `} />

          {/* Priority badge */}
          <span className={`
            text-[9px] font-bold px-1.5 py-0.5 rounded border tracking-widest shrink-0
            ${isActive ? style.badge : 'bg-gray-800 text-gray-500 border-gray-700'}
          `}>
            {alarm.priority}
          </span>

          {/* Element */}
          <span className="text-xs font-bold text-gray-300 font-mono shrink-0">
            {alarm.element}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Timestamp */}
          <span className="text-[10px] text-gray-600 font-mono">{raisedTime}</span>

          {/* ACK button — only for ACTIVE alarms */}
          {isActive && onAck && (
            <button
              onClick={() => onAck(alarm.id)}
              className="text-[10px] font-bold px-2 py-0.5 rounded border
                         border-gray-600 bg-gray-800 text-gray-400
                         hover:border-gray-400 hover:text-gray-200 transition-colors
                         tracking-widest"
            >
              ACK
            </button>
          )}

          {/* Acknowledged indicator */}
          {alarm.state === 'ACKNOWLEDGED' && (
            <span className="text-[10px] text-gray-600 font-mono">
              acked {ackedTime}
            </span>
          )}
        </div>
      </div>

      {/* Message */}
      <p className={`text-xs font-mono leading-relaxed pl-4 ${
        isActive ? style.text : 'text-gray-600'
      }`}>
        {alarm.message}
      </p>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ALARM PANEL
// ─────────────────────────────────────────────────────────────────────────────

export default function AlarmPanel({ alarms, onAck }) {
  const [showAcked, setShowAcked] = useState(true)

  const activeAlarms = alarms.filter(a => a.state === 'ACTIVE')
  const ackedAlarms  = alarms.filter(a => a.state === 'ACKNOWLEDGED')
  const totalCount   = alarms.length
  const unackedCount = activeAlarms.length

  return (
    <div className="bg-gray-900 border border-gray-700 rounded overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold tracking-widest text-gray-400 uppercase">
            Alarms
          </span>

          {/* Unacknowledged count badge */}
          {unackedCount > 0 && (
            <span className="flex items-center gap-1.5 text-[10px] font-bold
                             px-2 py-0.5 rounded border
                             border-red-700 bg-red-950 text-red-400
                             animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {unackedCount} UNACK
            </span>
          )}

          {totalCount === 0 && (
            <span className="text-[10px] text-green-700 font-mono">● No active alarms</span>
          )}
        </div>

        <span className="text-[10px] text-gray-600 font-mono">
          {totalCount} total
        </span>
      </div>

      <div className="p-3 space-y-3">

        {/* ── Active (unacknowledged) alarms ──────────────────────────── */}
        {activeAlarms.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] text-gray-600 font-mono uppercase tracking-widest px-1">
              Unacknowledged ({activeAlarms.length})
            </p>
            {activeAlarms.map(alarm => (
              <AlarmRow key={alarm.id} alarm={alarm} onAck={onAck} />
            ))}
          </div>
        )}

        {/* ── Acknowledged alarms ─────────────────────────────────────── */}
        {ackedAlarms.length > 0 && (
          <div className="space-y-2">
            <button
              onClick={() => setShowAcked(s => !s)}
              className="flex items-center gap-2 text-[10px] text-gray-600
                         font-mono uppercase tracking-widest px-1
                         hover:text-gray-400 transition-colors"
            >
              <span>{showAcked ? '▼' : '▶'}</span>
              Acknowledged ({ackedAlarms.length})
            </button>
            {showAcked && ackedAlarms.map(alarm => (
              <AlarmRow key={alarm.id} alarm={alarm} onAck={null} dimmed />
            ))}
          </div>
        )}

        {/* ── Empty state ─────────────────────────────────────────────── */}
        {totalCount === 0 && (
          <div className="py-4 text-center">
            <p className="text-xs text-gray-700 font-mono">
              All measurements within normal limits
            </p>
          </div>
        )}

      </div>
    </div>
  )
}
