/**
 * useWebSocket.js — SCADA WebSocket connection hook
 * ==================================================
 * Manages the WebSocket lifecycle:
 *   - Opens connection to /scada/ws on mount
 *   - Writes incoming state_update packets into scadaStore
 *   - Reconnects automatically on unexpected close (up to MAX_RETRIES)
 *   - Closes cleanly on unmount
 *
 * Usage: call once at the top of ScadaApp.jsx. No props needed.
 */

import { useEffect, useRef } from 'react'
import { useScadaStore } from '../store/scadaStore'

const WS_URL = `ws://${window.location.host}/scada/ws`
const MAX_RETRIES  = 5
const RETRY_DELAY  = 3000   // ms between reconnect attempts

export function useWebSocket() {
  const { setWsStatus, setWsRef, applyStateUpdate } = useScadaStore()

  const retryCount = useRef(0)
  const retryTimer = useRef(null)
  const wsRef      = useRef(null)

  useEffect(() => {
    connect()
    return () => {
      // Cleanup: cancel any pending reconnect and close the socket
      clearTimeout(retryTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null   // prevent reconnect loop on intentional close
        wsRef.current.close()
      }
    }
  }, [])

  function connect() {
    setWsStatus('connecting')

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws
    setWsRef(ws)

    ws.onopen = () => {
      console.log('[SCADA WS] Connected')
      setWsStatus('connected')
      retryCount.current = 0
    }

    ws.onmessage = (event) => {
      let packet
      try {
        packet = JSON.parse(event.data)
      } catch {
        console.warn('[SCADA WS] Non-JSON message:', event.data)
        return
      }

      switch (packet.type) {
        case 'state_update':
          applyStateUpdate(packet)
          break

        case 'breaker_ack':
          // Breaker command acknowledged — the next state_update will
          // carry the new breaker position. No action needed here.
          console.log(
            `[SCADA WS] Breaker ${packet.breaker_id} → ${packet.new_state}`,
            packet.changed ? '(changed)' : '(no change)'
          )
          break

        case 'error':
          console.error('[SCADA WS] Server error:', packet.message)
          break

        default:
          console.log('[SCADA WS] Unknown packet type:', packet.type)
      }
    }

    ws.onerror = (err) => {
      console.error('[SCADA WS] Error:', err)
      setWsStatus('error')
    }

    ws.onclose = (event) => {
      console.warn(`[SCADA WS] Closed (code=${event.code})`)
      setWsStatus('disconnected')
      wsRef.current = null
      setWsRef(null)

      // Attempt reconnect unless we hit the retry limit
      if (retryCount.current < MAX_RETRIES) {
        retryCount.current += 1
        console.log(
          `[SCADA WS] Reconnecting in ${RETRY_DELAY}ms ` +
          `(attempt ${retryCount.current}/${MAX_RETRIES})...`
        )
        retryTimer.current = setTimeout(connect, RETRY_DELAY)
      } else {
        console.error('[SCADA WS] Max retries reached. Give up.')
        setWsStatus('error')
      }
    }
  }
}
