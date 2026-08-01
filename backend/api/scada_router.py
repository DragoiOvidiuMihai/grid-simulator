"""
scada_router.py — SCADA API Router
====================================
Mounts under the prefix /scada in main.py.

Endpoints
---------
  GET  /scada/health      — confirms SCADA module is running
  GET  /scada/state       — returns latest measurement snapshot as JSON (REST)
  WS   /scada/ws          — WebSocket: receives live state_update packets
                            and sends breaker_command / alarm_ack messages

The ConnectionManager, SimulationLoop and ScadaState are all created once
in main.py and passed into this module via module-level variables set by
init_scada(). This keeps the lifespan management in one place.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.scada.simulation_loop import (
    ConnectionManager,
    ScadaState,
    SimulationLoop,
    _build_state_packet,
)
from backend.scada.data_source import create_data_source
from backend.scada.alarm_engine import Alarm


def _get_full_packet() -> dict:
    """Build a state packet including current alarms."""
    if _state is None or _state.last_measurements is None:
        return {}
    return _build_state_packet(
        _state.last_measurements,
        _state.alarm_engine.active_alarms(),
    )

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scada", tags=["SCADA"])

# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons (set by init_scada called from main.py lifespan)
# ─────────────────────────────────────────────────────────────────────────────
_manager: Optional[ConnectionManager] = None
_state:   Optional[ScadaState]        = None
_loop:    Optional[SimulationLoop]    = None


def init_scada(use_opendss: bool = False) -> tuple[ConnectionManager, ScadaState, SimulationLoop]:
    """
    Create and wire up all SCADA singletons.
    Called once from main.py's lifespan context manager.

    Returns the three objects so main.py can call loop.start() / loop.stop().
    """
    global _manager, _state, _loop

    data_source = create_data_source(use_opendss=use_opendss)
    _manager    = ConnectionManager()
    _state      = ScadaState()
    _loop       = SimulationLoop(
        data_source      = data_source,
        manager          = _manager,
        state            = _state,
        interval_seconds = 5.0,
    )

    logger.info(
        "SCADA module initialised (data_source=%s)",
        type(data_source).__name__,
    )
    return _manager, _state, _loop


# ─────────────────────────────────────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health")
def scada_health():
    """Quick liveness check for the SCADA module."""
    clients     = _manager.client_count if _manager else 0
    source_name = type(_loop._data_source).__name__.replace("DataSource", "").lower() if _loop else "unknown"
    return {
        "status":      "ok",
        "module":      "SCADA/HMI",
        "ws_clients":  clients,
        "data_source": source_name,
    }


@router.get("/state")
def scada_state():
    """
    Return the latest measurement snapshot as a plain JSON response.
    Useful for polling clients or debugging without a WebSocket connection.
    """
    if _state is None or _state.last_measurements is None:
        return {"status": "no_data", "message": "Simulation loop not yet started or no tick completed."}
    return _get_full_packet()


@router.get("/alarms")
def scada_alarms():
    """Return current active and acknowledged alarms."""
    if _state is None:
        return {"alarms": []}
    return {
        "alarms":              [a.to_dict() for a in _state.alarm_engine.active_alarms()],
        "unacknowledged_count": _state.alarm_engine.unacknowledged_count(),
        "total_count":          _state.alarm_engine.total_count(),
    }


@router.get("/events")
def scada_events(limit: int = 100):
    """Return the most recent events from the event log (newest first)."""
    if _state is None:
        return {"events": []}
    return {
        "events": _state.event_log.recent(limit=limit),
        "total":  len(_state.event_log),
    }


@router.get("/history")
def scada_history(window: str = "1h", metric: str = "voltage"):
    """
    Return historical measurement data for trend charts.

    Parameters
    ----------
    window : str
        Time window: 1h | 6h | 24h | 7d
    metric : str
        Data series: voltage | loading | branch_loading

    Returns
    -------
    dict
        { series: { BUS_A: [{timestamp, value}, ...], ... }, window, metric }
    """
    if _state is None:
        return {"series": {}, "window": window, "metric": metric}

    valid_windows = {"1h", "6h", "24h", "7d"}
    if window not in valid_windows:
        window = "1h"

    store = _state.history_store

    if metric == "voltage":
        return store.query_voltage(window)
    elif metric == "loading":
        return store.query_loading(window)
    elif metric == "branch_loading":
        return store.query_branch_loading(window)
    else:
        return store.query_voltage(window)


@router.get("/history/stats")
def scada_history_stats():
    """Return row counts in the history database — useful for debugging."""
    if _state is None:
        return {}
    return _state.history_store.record_count()


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def scada_websocket(websocket: WebSocket):
    """
    Main SCADA WebSocket endpoint.

    On connect:
      - Registers client with ConnectionManager
      - Immediately sends the latest state snapshot so the UI is not blank

    Incoming messages from the client:
      { "type": "breaker_command", "breaker_id": "CB1", "command": "OPEN" }
      { "type": "alarm_ack",       "alarm_id":   "ALM001" }           ← Phase 4

    Outgoing messages (broadcast by simulation loop every 5 s):
      { "type": "state_update", "timestamp": "...", "buses": {...}, ... }
    """
    if _manager is None or _state is None:
        await websocket.close(code=1013, reason="SCADA module not initialised")
        return

    await _manager.connect(websocket)

    # Send an immediate snapshot so the frontend is not blank on load
    if _state.last_measurements is not None:
        import json
        await websocket.send_text(
            json.dumps(_build_state_packet(_state.last_measurements), default=str)
        )

    try:
        while True:
            # Wait for a control message from this client
            raw = await websocket.receive_text()
            await _handle_client_message(websocket, raw)

    except WebSocketDisconnect:
        logger.info("SCADA WebSocket client disconnected normally.")
    except Exception as exc:
        logger.exception("Unexpected error in SCADA WebSocket handler: %s", exc)
    finally:
        _manager.disconnect(websocket)


async def _handle_client_message(websocket: WebSocket, raw: str) -> None:
    """
    Dispatch an incoming WebSocket message from the operator.
    Sends an immediate acknowledgement back to the sender.
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Invalid JSON"})
        )
        return

    msg_type = msg.get("type")

    if msg_type == "breaker_command":
        breaker_id = msg.get("breaker_id", "")
        command    = msg.get("command", "")   # "OPEN" or "CLOSE"

        if command not in ("OPEN", "CLOSE"):
            await websocket.send_text(json.dumps({
                "type":    "error",
                "message": f"Invalid command '{command}'. Must be OPEN or CLOSE."
            }))
            return

        changed = _state.set_breaker(breaker_id, command)

        # Acknowledge back to the sender immediately
        await websocket.send_text(json.dumps({
            "type":       "breaker_ack",
            "breaker_id": breaker_id,
            "new_state":  _state.breaker_states.get(breaker_id, "UNKNOWN"),
            "changed":    changed,
        }))

        # If state changed, force an immediate broadcast so all clients update
        # without waiting for the next scheduled tick
        if changed and _state.last_measurements is not None:
            # Log breaker operation to event log
            _state.event_log.log_breaker_operation(breaker_id, _state.breaker_states[breaker_id])
            # Regenerate measurements with new breaker state immediately
            new_measurements = _loop._data_source.get_measurements(
                _state.breaker_states
            )
            _state.last_measurements = new_measurements
            # Re-evaluate alarms with new measurements
            current_alarms = _state.alarm_engine.evaluate(new_measurements)
            await _manager.broadcast(
                _build_state_packet(new_measurements, current_alarms)
            )

    elif msg_type == "alarm_ack":
        alarm_id = msg.get("alarm_id", "")
        acked    = _state.alarm_engine.acknowledge(alarm_id)

        if acked:
            # Find element for event log
            element = alarm_id.split("-")[1] if "-" in alarm_id else alarm_id
            _state.event_log.log_alarm_acknowledged(alarm_id, element)

        await websocket.send_text(json.dumps({
            "type":     "alarm_ack_response",
            "alarm_id": alarm_id,
            "success":  acked,
        }))

        # Broadcast updated alarm list immediately
        if acked and _state.last_measurements is not None:
            packet = _build_state_packet(
                _state.last_measurements,
                _state.alarm_engine.active_alarms(),
            )
            await _manager.broadcast(packet)

    else:
        await websocket.send_text(json.dumps({
            "type":    "error",
            "message": f"Unknown message type: '{msg_type}'"
        }))
