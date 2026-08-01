"""
simulation_loop.py — SCADA Simulation Loop
==========================================
Manages the set of active WebSocket connections and runs a periodic
background task that:

  1. Fetches fresh measurements from the DataSource
  2. Serialises them to a JSON state_update packet
  3. Broadcasts to every connected WebSocket client

Usage
-----
The loop is started once when the FastAPI app starts (via lifespan) and
runs until the app shuts down. Individual WebSocket clients register and
deregister themselves via ConnectionManager.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import WebSocket

from backend.scada.data_source import DataSource, ScadaMeasurements
from backend.scada.alarm_engine import AlarmEngine, Alarm
from backend.scada.event_log import EventLog
from backend.scada.history_store import HistoryStore

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT BREAKER STATES
# All breakers start CLOSED (normal operating configuration).
# CB3 (bus coupler) starts OPEN — standard practice: only close coupler
# when one feeder is lost.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_BREAKER_STATES: Dict[str, str] = {
    "CB1": "CLOSED",   # Feeder 1 → Bus A
    "CB2": "CLOSED",   # Feeder 2 → Bus B
    "CB3": "OPEN",     # Bus coupler (A ↔ B) — normally open
    "CB4": "CLOSED",   # Bus A → TX1
    "CB5": "CLOSED",   # Bus B → TX2
    "CB6": "CLOSED",   # TX1 LV → Load 1
    "CB7": "CLOSED",   # TX1 LV → PV 1
    "CB8": "CLOSED",   # TX2 LV → Load 2
    "CB9": "CLOSED",   # TX2 LV → Load 3
}


# ─────────────────────────────────────────────────────────────────────────────
# CONNECTION MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """
    Tracks active WebSocket connections and broadcasts messages to all of them.
    Thread-safe for use with asyncio (single-threaded event loop).
    """

    def __init__(self):
        self._active: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active.add(websocket)
        logger.info(
            "SCADA WebSocket client connected. "
            "Total connections: %d", len(self._active)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self._active.discard(websocket)
        logger.info(
            "SCADA WebSocket client disconnected. "
            "Total connections: %d", len(self._active)
        )

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected clients. Remove dead connections."""
        dead: Set[WebSocket] = set()
        payload = json.dumps(message, default=str)

        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self._active.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._active)


# ─────────────────────────────────────────────────────────────────────────────
# SCADA STATE
# Centralised mutable state for the running SCADA session.
# In Phase 3+ this will grow to include alarm state, event log, etc.
# ─────────────────────────────────────────────────────────────────────────────

class ScadaState:
    """
    Holds the current SCADA session state:
      - breaker positions (operator-controlled)
      - last measurement snapshot
    """

    def __init__(self):
        self.breaker_states: Dict[str, str] = dict(DEFAULT_BREAKER_STATES)
        self.last_measurements: ScadaMeasurements | None = None
        self.alarm_engine: AlarmEngine = AlarmEngine()
        self.event_log:    EventLog    = EventLog()
        self.history_store: HistoryStore = HistoryStore()

    def set_breaker(self, breaker_id: str, command: str) -> bool:
        """
        Apply a breaker command. Returns True if the state actually changed.
        command must be "OPEN" or "CLOSE".
        """
        if breaker_id not in self.breaker_states:
            logger.warning("Unknown breaker: %s", breaker_id)
            return False

        new_state = "OPEN" if command == "OPEN" else "CLOSED"
        if self.breaker_states[breaker_id] == new_state:
            return False   # no change

        self.breaker_states[breaker_id] = new_state
        logger.info("Breaker %s → %s", breaker_id, new_state)
        return True


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION LOOP
# ─────────────────────────────────────────────────────────────────────────────

class SimulationLoop:
    """
    Runs an asyncio background task that periodically fetches measurements
    and broadcasts them to all WebSocket clients.

    Parameters
    ----------
    data_source : DataSource
        The measurement provider (synthetic or OpenDSS).
    manager : ConnectionManager
        Tracks WebSocket clients and handles broadcasting.
    state : ScadaState
        Shared mutable SCADA state.
    interval_seconds : float
        How often to update (default: 5s for synthetic, use ~15s for OpenDSS).
    """

    def __init__(
        self,
        data_source:      DataSource,
        manager:          ConnectionManager,
        state:            ScadaState,
        interval_seconds: float = 5.0,
    ):
        self._data_source = data_source
        self._manager     = manager
        self._state       = state
        self._interval    = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background loop task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info(
                "SCADA simulation loop started (interval=%.1fs)", self._interval
            )

    def stop(self) -> None:
        """Cancel the background loop task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("SCADA simulation loop stopped.")

    async def _run(self) -> None:
        """Main loop body — runs until cancelled."""
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in SCADA simulation loop: %s", exc)

            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        """One update cycle: fetch → evaluate alarms → store → broadcast."""
        measurements = self._data_source.get_measurements(
            self._state.breaker_states
        )

        # Track which alarms existed before evaluation
        prev_alarm_ids = {
            a.id for a in self._state.alarm_engine.active_alarms()
        }

        # Evaluate alarm thresholds
        current_alarms = self._state.alarm_engine.evaluate(measurements)

        # Log newly raised and newly cleared alarms to event log
        current_alarm_ids = {a.id for a in current_alarms}
        for alarm in current_alarms:
            if alarm.id not in prev_alarm_ids:
                self._state.event_log.log_alarm_raised(
                    alarm.id, alarm.element, alarm.priority, alarm.message
                )
        for alarm_id in prev_alarm_ids - current_alarm_ids:
            self._state.event_log.log_alarm_cleared(alarm_id, alarm_id.split("-")[1])

        self._state.last_measurements = measurements

        # Persist to history store
        self._state.history_store.write(measurements)

        # Only broadcast if there are connected clients (avoid wasted work)
        if self._manager.client_count == 0:
            return

        packet = _build_state_packet(measurements, current_alarms)
        await self._manager.broadcast(packet)


# ─────────────────────────────────────────────────────────────────────────────
# PACKET BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_state_packet(m: ScadaMeasurements, alarms: list | None = None) -> dict:
    """
    Serialise a ScadaMeasurements snapshot into the WebSocket wire format.

    Wire format:
    {
      "type": "state_update",
      "timestamp": "<ISO-8601>",
      "breaker_states": { "CB1": "CLOSED", ... },
      "buses": {
        "BUS_A": { "voltage_kv": 11.02, "voltage_pu": 1.002, "voltage_nom": 11.0 },
        ...
      },
      "branches": {
        "FEEDER1": { "current_a": 45.2, "ampacity_a": 200.0,
                     "loading_pct": 22.6, "power_kw": 380.0, "power_kvar": 120.0 },
        ...
      },
      "transformers": {
        "TX1": { "current_a": 18.1, "rated_kva": 630.0, "loading_pct": 34.2,
                 "power_kw": 212.0, "power_kvar": 65.0 },
        ...
      }
    }
    """
    def bus_dict(b):
        return {
            "voltage_kv":  b.voltage_kv,
            "voltage_pu":  b.voltage_pu,
            "voltage_nom": b.voltage_nom,
        }

    def branch_dict(br):
        return {
            "current_a":   br.current_a,
            "ampacity_a":  br.ampacity_a,
            "loading_pct": br.loading_pct,
            "power_kw":    br.power_kw,
            "power_kvar":  br.power_kvar,
        }

    def tx_dict(tx):
        return {
            "primary_kv":   tx.primary_kv,
            "secondary_kv": tx.secondary_kv,
            "current_a":    tx.current_a,
            "rated_kva":    tx.rated_kva,
            "loading_pct":  tx.loading_pct,
            "power_kw":     tx.power_kw,
            "power_kvar":   tx.power_kvar,
        }

    return {
        "type":           "state_update",
        "timestamp":      m.timestamp,
        "breaker_states": m.breaker_states,
        "buses":          {k: bus_dict(v)    for k, v in m.buses.items()},
        "branches":       {k: branch_dict(v) for k, v in m.branches.items()},
        "transformers":   {k: tx_dict(v)     for k, v in m.transformers.items()},
        "alarms":         [a.to_dict() for a in alarms] if alarms else [],
    }
