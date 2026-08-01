"""
event_log.py — SCADA Event Log
================================
Records every significant event with a precise UTC timestamp:
  - Alarm raised / cleared / acknowledged
  - Breaker operated (operator action)
  - System events (simulation start/stop)

The log is an in-memory ring buffer capped at MAX_EVENTS entries.
A REST endpoint (/scada/events) exposes it for the frontend event log table.

In Phase 5 this will be backed by SQLite for persistence across restarts.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

MAX_EVENTS = 500   # ring buffer cap


# ─────────────────────────────────────────────────────────────────────────────
# EVENT TYPES
# ─────────────────────────────────────────────────────────────────────────────

class EventType:
    ALARM_RAISED  = "ALARM_RAISED"
    ALARM_ACKED   = "ALARM_ACKED"
    ALARM_CLEARED = "ALARM_CLEARED"
    BREAKER_OP    = "BREAKER_OP"
    SYSTEM        = "SYSTEM"


# ─────────────────────────────────────────────────────────────────────────────
# EVENT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Event:
    timestamp:   str    # ISO-8601 UTC
    event_type:  str    # EventType constant
    element:     str    # affected element (bus ID, breaker ID, "SYSTEM")
    description: str    # human-readable summary
    priority:    str    # "HIGH" | "MEDIUM" | "LOW" | "INFO"
    alarm_id:    str = ""  # set for alarm events

    def to_dict(self) -> dict:
        return {
            "timestamp":   self.timestamp,
            "event_type":  self.event_type,
            "element":     self.element,
            "description": self.description,
            "priority":    self.priority,
            "alarm_id":    self.alarm_id,
        }


# ─────────────────────────────────────────────────────────────────────────────
# EVENT LOG
# ─────────────────────────────────────────────────────────────────────────────

class EventLog:
    """
    In-memory ring buffer of SCADA events.
    Thread-safe for single-threaded asyncio use.
    """

    def __init__(self, max_events: int = MAX_EVENTS):
        self._events: deque[Event] = deque(maxlen=max_events)

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _add(self, event: Event) -> None:
        self._events.appendleft(event)   # newest first

    # ── Public logging methods ────────────────────────────────────────────────

    def log_alarm_raised(self, alarm_id: str, element: str, priority: str, message: str) -> None:
        self._add(Event(
            timestamp   = self._now(),
            event_type  = EventType.ALARM_RAISED,
            element     = element,
            description = f"ALARM: {message}",
            priority    = priority,
            alarm_id    = alarm_id,
        ))

    def log_alarm_acknowledged(self, alarm_id: str, element: str) -> None:
        self._add(Event(
            timestamp   = self._now(),
            event_type  = EventType.ALARM_ACKED,
            element     = element,
            description = f"Operator acknowledged alarm {alarm_id}",
            priority    = "INFO",
            alarm_id    = alarm_id,
        ))

    def log_alarm_cleared(self, alarm_id: str, element: str) -> None:
        self._add(Event(
            timestamp   = self._now(),
            event_type  = EventType.ALARM_CLEARED,
            element     = element,
            description = f"Alarm condition cleared: {alarm_id}",
            priority    = "INFO",
            alarm_id    = alarm_id,
        ))

    def log_breaker_operation(
        self,
        breaker_id: str,
        new_state:  str,
        operator:   str = "OPERATOR",
    ) -> None:
        self._add(Event(
            timestamp   = self._now(),
            event_type  = EventType.BREAKER_OP,
            element     = breaker_id,
            description = f"{operator} operated {breaker_id} → {new_state}",
            priority    = "INFO",
        ))

    def log_system(self, message: str) -> None:
        self._add(Event(
            timestamp   = self._now(),
            event_type  = EventType.SYSTEM,
            element     = "SYSTEM",
            description = message,
            priority    = "INFO",
        ))

    # ── Query ─────────────────────────────────────────────────────────────────

    def recent(self, limit: int = 100) -> List[dict]:
        """Return the most recent `limit` events as dicts (newest first)."""
        return [e.to_dict() for e in list(self._events)[:limit]]

    def __len__(self) -> int:
        return len(self._events)
