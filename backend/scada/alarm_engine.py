"""
alarm_engine.py — SCADA Alarm Engine
=====================================
Evaluates measurements against thresholds and manages the alarm lifecycle.

Alarm lifecycle:
  ACTIVE → ACKNOWLEDGED → CLEARED
               ↑
         operator must explicitly do this via alarm_ack WebSocket message

Design principles:
  - One alarm object per unique (element, condition) pair.
  - Re-evaluation on every tick: if condition clears, alarm moves to CLEARED.
  - Acknowledged alarms that clear are removed from the active set entirely.
  - New alarm for same element/condition after clearing starts fresh.
  - Alarm IDs are deterministic: f"ALM-{element}-{condition}" — this means
    the frontend can always correlate an alarm across updates without
    needing a UUID lookup.

Thresholds follow EN 50160 voltage quality standard and IEC 60076-1
transformer loading guidance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.scada.data_source import ScadaMeasurements

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Voltage limits (per-unit) — EN 50160
VOLT_HIGH_WARN  = 1.06   # +6% of nominal
VOLT_HIGH_CRIT  = 1.10   # +10% of nominal
VOLT_LOW_WARN   = 0.94   # −6% of nominal
VOLT_LOW_CRIT   = 0.90   # −10% of nominal

# Loading limits (%) — IEC 60076-1 / general practice
LOADING_WARN    = 70.0
LOADING_CRIT    = 90.0

# Priorities
HIGH   = "HIGH"
MEDIUM = "MEDIUM"
LOW    = "LOW"

# States
ACTIVE       = "ACTIVE"
ACKNOWLEDGED = "ACKNOWLEDGED"
CLEARED      = "CLEARED"


# ─────────────────────────────────────────────────────────────────────────────
# ALARM DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Alarm:
    id:        str           # deterministic: "ALM-{element}-{condition}"
    priority:  str           # HIGH | MEDIUM | LOW
    state:     str           # ACTIVE | ACKNOWLEDGED | CLEARED
    element:   str           # e.g. "BUS_A", "TX1", "FEEDER1"
    condition: str           # e.g. "VOLT_HIGH", "OVERLOAD_WARN"
    message:   str           # human-readable description
    raised_at: str           # ISO-8601 UTC timestamp
    acked_at:  Optional[str] = None
    cleared_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "priority":   self.priority,
            "state":      self.state,
            "element":    self.element,
            "condition":  self.condition,
            "message":    self.message,
            "raised_at":  self.raised_at,
            "acked_at":   self.acked_at,
            "cleared_at": self.cleared_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLD DEFINITIONS
# Each entry is (condition_id, priority, check_fn, message_fn)
# check_fn(value) → True if alarm should be ACTIVE
# message_fn(element, value) → human-readable string
# ─────────────────────────────────────────────────────────────────────────────

def _bus_thresholds():
    return [
        (
            "VOLT_VERY_HIGH", HIGH,
            lambda pu: pu > 0 and pu > VOLT_HIGH_CRIT,
            lambda el, pu: f"{el} voltage {pu:.4f} pu exceeds critical high limit ({VOLT_HIGH_CRIT} pu / EN 50160)",
        ),
        (
            "VOLT_HIGH", MEDIUM,
            lambda pu: pu > 0 and VOLT_HIGH_WARN < pu <= VOLT_HIGH_CRIT,
            lambda el, pu: f"{el} voltage {pu:.4f} pu exceeds warning high limit ({VOLT_HIGH_WARN} pu / EN 50160)",
        ),
        (
            "VOLT_VERY_LOW", HIGH,
            lambda pu: pu > 0 and pu < VOLT_LOW_CRIT,
            lambda el, pu: f"{el} voltage {pu:.4f} pu below critical low limit ({VOLT_LOW_CRIT} pu / EN 50160)",
        ),
        (
            "VOLT_LOW", MEDIUM,
            lambda pu: pu > 0 and VOLT_LOW_CRIT <= pu < VOLT_LOW_WARN,
            lambda el, pu: f"{el} voltage {pu:.4f} pu below warning low limit ({VOLT_LOW_WARN} pu / EN 50160)",
        ),
        (
            "DE_ENERGISED", HIGH,
            lambda pu: pu == 0,
            lambda el, _: f"{el} is de-energised (voltage = 0)",
        ),
    ]


def _loading_thresholds(equipment_type: str):
    return [
        (
            "OVERLOAD_CRIT", HIGH,
            lambda pct: pct > LOADING_CRIT,
            lambda el, pct: (
                f"{el} loading {pct:.1f}% exceeds critical limit "
                f"({LOADING_CRIT}% / IEC 60076-1)"
            ),
        ),
        (
            "OVERLOAD_WARN", MEDIUM,
            lambda pct: LOADING_WARN < pct <= LOADING_CRIT,
            lambda el, pct: (
                f"{el} loading {pct:.1f}% exceeds warning limit "
                f"({LOADING_WARN}%)"
            ),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ALARM ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class AlarmEngine:
    """
    Maintains a dictionary of active/acknowledged alarms keyed by alarm ID.
    Call evaluate(measurements) on every simulation tick.
    """

    def __init__(self):
        # alarm_id → Alarm
        self._alarms: Dict[str, Alarm] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate(self, m: ScadaMeasurements) -> List[Alarm]:
        """
        Run all threshold checks against the latest measurements.
        Updates internal alarm state and returns the current alarm list
        (ACTIVE + ACKNOWLEDGED only — CLEARED alarms are pruned).
        """
        now = datetime.now(timezone.utc).isoformat()

        # Collect all (alarm_id, priority, is_active, message) tuples
        findings: List[tuple] = []

        # Bus voltage checks
        for bus_id, bus in m.buses.items():
            for cond_id, priority, check, msg_fn in _bus_thresholds():
                alarm_id  = f"ALM-{bus_id}-{cond_id}"
                is_active = check(bus.voltage_pu)
                message   = msg_fn(bus_id, bus.voltage_pu) if is_active else ""
                findings.append((alarm_id, bus_id, cond_id, priority, is_active, message))

        # Transformer loading checks
        for tx_id, tx in m.transformers.items():
            for cond_id, priority, check, msg_fn in _loading_thresholds("transformer"):
                alarm_id  = f"ALM-{tx_id}-{cond_id}"
                is_active = check(tx.loading_pct)
                message   = msg_fn(tx_id, tx.loading_pct) if is_active else ""
                findings.append((alarm_id, tx_id, cond_id, priority, is_active, message))

        # Branch loading checks
        for branch_id, branch in m.branches.items():
            for cond_id, priority, check, msg_fn in _loading_thresholds("branch"):
                alarm_id  = f"ALM-{branch_id}-{cond_id}"
                is_active = check(branch.loading_pct)
                message   = msg_fn(branch_id, branch.loading_pct) if is_active else ""
                findings.append((alarm_id, branch_id, cond_id, priority, is_active, message))

        # Process findings
        active_ids = set()
        for alarm_id, element, condition, priority, is_active, message in findings:
            if is_active:
                active_ids.add(alarm_id)
                if alarm_id not in self._alarms:
                    # New alarm
                    alarm = Alarm(
                        id        = alarm_id,
                        priority  = priority,
                        state     = ACTIVE,
                        element   = element,
                        condition = condition,
                        message   = message,
                        raised_at = now,
                    )
                    self._alarms[alarm_id] = alarm
                    logger.info("ALARM RAISED: %s — %s", alarm_id, message)
                else:
                    # Update message (value may have changed)
                    existing = self._alarms[alarm_id]
                    if existing.state == CLEARED:
                        # Re-raised after clearing
                        existing.state      = ACTIVE
                        existing.raised_at  = now
                        existing.acked_at   = None
                        existing.cleared_at = None
                    existing.message = message
            else:
                # Condition not active — clear if previously active
                if alarm_id in self._alarms:
                    existing = self._alarms[alarm_id]
                    if existing.state in (ACTIVE, ACKNOWLEDGED):
                        existing.state      = CLEARED
                        existing.cleared_at = now
                        logger.info("ALARM CLEARED: %s", alarm_id)

        # Prune CLEARED alarms from the dictionary
        self._alarms = {
            k: v for k, v in self._alarms.items()
            if v.state != CLEARED
        }

        return self.active_alarms()

    def acknowledge(self, alarm_id: str) -> bool:
        """
        Acknowledge an alarm. Returns True if found and acknowledged.
        Only ACTIVE alarms can be acknowledged.
        """
        alarm = self._alarms.get(alarm_id)
        if alarm is None:
            logger.warning("ACK for unknown alarm: %s", alarm_id)
            return False
        if alarm.state != ACTIVE:
            logger.info("ACK for already-%s alarm: %s", alarm.state, alarm_id)
            return False

        alarm.state   = ACKNOWLEDGED
        alarm.acked_at = datetime.now(timezone.utc).isoformat()
        logger.info("ALARM ACKNOWLEDGED: %s", alarm_id)
        return True

    def active_alarms(self) -> List[Alarm]:
        """Return all ACTIVE and ACKNOWLEDGED alarms, sorted by priority then time."""
        priority_order = {HIGH: 0, MEDIUM: 1, LOW: 2}
        alarms = [a for a in self._alarms.values() if a.state != CLEARED]
        return sorted(alarms, key=lambda a: (priority_order.get(a.priority, 9), a.raised_at))

    def unacknowledged_count(self) -> int:
        return sum(1 for a in self._alarms.values() if a.state == ACTIVE)

    def total_count(self) -> int:
        return len(self._alarms)
