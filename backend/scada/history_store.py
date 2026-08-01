"""
history_store.py — SCADA Historical Data Store
===============================================
Persists measurement snapshots to a SQLite database for trend analysis.

Schema
------
  measurements          — bus voltage history (one row per bus per tick)
  transformer_history   — transformer loading history
  branch_history        — branch/feeder loading history

Retention policy: 7 days. Records older than 7 days are pruned
automatically on every write cycle (once per minute check).

The database file is created at backend/scada/scada_history.db
relative to the project root. It is created automatically on first run.

Thread safety: all calls are synchronous and run in the asyncio event
loop — SQLite's default thread mode is fine since FastAPI/uvicorn runs
in a single thread with asyncio.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from backend.scada.data_source import ScadaMeasurements

logger = logging.getLogger(__name__)

# Path to the SQLite database file (project root / backend / scada /)
_DB_PATH = os.path.join(
    os.path.dirname(__file__), "scada_history.db"
)

# Retention: keep 7 days of history
RETENTION_DAYS = 7

# Prune at most once every 60 seconds to avoid overhead
_PRUNE_INTERVAL_S = 60


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    bus_id      TEXT    NOT NULL,
    voltage_pu  REAL    NOT NULL,
    voltage_kv  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS transformer_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    tx_id       TEXT    NOT NULL,
    loading_pct REAL    NOT NULL,
    power_kw    REAL    NOT NULL,
    power_kvar  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS branch_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    branch_id   TEXT    NOT NULL,
    loading_pct REAL    NOT NULL,
    current_a   REAL    NOT NULL,
    power_kw    REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meas_time   ON measurements(timestamp);
CREATE INDEX IF NOT EXISTS idx_meas_bus    ON measurements(bus_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_time     ON transformer_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_id       ON transformer_history(tx_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_br_time     ON branch_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_br_id       ON branch_history(branch_id, timestamp);
"""


# ─────────────────────────────────────────────────────────────────────────────
# HISTORY STORE
# ─────────────────────────────────────────────────────────────────────────────

class HistoryStore:
    """
    SQLite-backed time-series store for SCADA measurements.

    Usage
    -----
    store = HistoryStore()
    store.open()                        # create DB + tables
    store.write(measurements)           # called every tick
    rows = store.query_voltage("1h")    # fetch for frontend
    store.close()                       # on shutdown
    """

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path  = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._last_prune: Optional[datetime] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open (or create) the database and apply the schema."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
        self._conn.execute("PRAGMA synchronous=NORMAL") # balance safety/speed
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("SCADA history store opened: %s", self._db_path)

    def close(self) -> None:
        """Flush and close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("SCADA history store closed.")

    # ── Write ─────────────────────────────────────────────────────────────────

    def write(self, m: ScadaMeasurements) -> None:
        """
        Persist one measurement snapshot to the database.
        Called every simulation tick (every 5 seconds).
        Also triggers pruning once per minute.
        """
        if self._conn is None:
            return

        ts = m.timestamp

        # Bus voltages
        bus_rows = [
            (ts, bus_id, b.voltage_pu, b.voltage_kv)
            for bus_id, b in m.buses.items()
        ]
        self._conn.executemany(
            "INSERT INTO measurements (timestamp, bus_id, voltage_pu, voltage_kv) "
            "VALUES (?, ?, ?, ?)",
            bus_rows,
        )

        # Transformer loadings
        tx_rows = [
            (ts, tx_id, tx.loading_pct, tx.power_kw, tx.power_kvar)
            for tx_id, tx in m.transformers.items()
        ]
        self._conn.executemany(
            "INSERT INTO transformer_history "
            "(timestamp, tx_id, loading_pct, power_kw, power_kvar) "
            "VALUES (?, ?, ?, ?, ?)",
            tx_rows,
        )

        # Branch loadings
        br_rows = [
            (ts, br_id, br.loading_pct, br.current_a, br.power_kw)
            for br_id, br in m.branches.items()
        ]
        self._conn.executemany(
            "INSERT INTO branch_history "
            "(timestamp, branch_id, loading_pct, current_a, power_kw) "
            "VALUES (?, ?, ?, ?, ?)",
            br_rows,
        )

        self._conn.commit()

        # Prune old records periodically
        self._maybe_prune()

    # ── Query ─────────────────────────────────────────────────────────────────

    def query_voltage(self, window: str = "1h") -> Dict:
        """
        Return bus voltage history for the given time window.

        Parameters
        ----------
        window : str
            One of "1h", "6h", "24h", "7d"

        Returns
        -------
        dict
            {
              "series": {
                "BUS_A": [{"timestamp": ..., "value": ...}, ...],
                ...
              },
              "window": "1h",
              "metric": "voltage_pu"
            }
        """
        if self._conn is None:
            return {"series": {}, "window": window, "metric": "voltage_pu"}

        since = self._since(window)
        # Downsample for larger windows to keep response size reasonable
        interval = _downsample_interval(window)

        rows = self._conn.execute(
            """
            SELECT bus_id, timestamp, voltage_pu
            FROM measurements
            WHERE timestamp >= ?
            ORDER BY bus_id, timestamp ASC
            """,
            (since,),
        ).fetchall()

        return {
            "series": _group_and_downsample(rows, key_col=0, ts_col=1, val_col=2, interval=interval),
            "window": window,
            "metric": "voltage_pu",
        }

    def query_loading(self, window: str = "1h") -> Dict:
        """
        Return transformer loading history for the given time window.
        """
        if self._conn is None:
            return {"series": {}, "window": window, "metric": "loading_pct"}

        since    = self._since(window)
        interval = _downsample_interval(window)

        rows = self._conn.execute(
            """
            SELECT tx_id, timestamp, loading_pct
            FROM transformer_history
            WHERE timestamp >= ?
            ORDER BY tx_id, timestamp ASC
            """,
            (since,),
        ).fetchall()

        return {
            "series": _group_and_downsample(rows, key_col=0, ts_col=1, val_col=2, interval=interval),
            "window": window,
            "metric": "loading_pct",
        }

    def query_branch_loading(self, window: str = "1h") -> Dict:
        """Return branch/feeder loading history."""
        if self._conn is None:
            return {"series": {}, "window": window, "metric": "loading_pct"}

        since    = self._since(window)
        interval = _downsample_interval(window)

        rows = self._conn.execute(
            """
            SELECT branch_id, timestamp, loading_pct
            FROM branch_history
            WHERE timestamp >= ?
            ORDER BY branch_id, timestamp ASC
            """,
            (since,),
        ).fetchall()

        return {
            "series": _group_and_downsample(rows, key_col=0, ts_col=1, val_col=2, interval=interval),
            "window": window,
            "metric": "loading_pct",
        }

    def record_count(self) -> Dict[str, int]:
        """Return approximate row counts for diagnostics."""
        if self._conn is None:
            return {}
        return {
            "measurements":         self._conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0],
            "transformer_history":  self._conn.execute("SELECT COUNT(*) FROM transformer_history").fetchone()[0],
            "branch_history":       self._conn.execute("SELECT COUNT(*) FROM branch_history").fetchone()[0],
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _since(self, window: str) -> str:
        """Convert a window string to an ISO-8601 cutoff timestamp."""
        deltas = {
            "1h":  timedelta(hours=1),
            "6h":  timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d":  timedelta(days=7),
        }
        delta = deltas.get(window, timedelta(hours=1))
        cutoff = datetime.now(timezone.utc) - delta
        return cutoff.isoformat()

    def _maybe_prune(self) -> None:
        """Prune records older than RETENTION_DAYS, at most once per minute."""
        now = datetime.now(timezone.utc)
        if self._last_prune and (now - self._last_prune).total_seconds() < _PRUNE_INTERVAL_S:
            return

        cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat()
        self._conn.execute("DELETE FROM measurements        WHERE timestamp < ?", (cutoff,))
        self._conn.execute("DELETE FROM transformer_history WHERE timestamp < ?", (cutoff,))
        self._conn.execute("DELETE FROM branch_history      WHERE timestamp < ?", (cutoff,))
        self._conn.commit()
        self._last_prune = now
        logger.debug("SCADA history pruned records older than %s", cutoff)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _downsample_interval(window: str) -> int:
    """
    Return the minimum gap (in seconds) between points for a given window.
    Keeps the frontend chart from receiving thousands of points.
      1h  → every 10s  → max ~360 points
      6h  → every 30s  → max ~720 points
      24h → every 120s → max ~720 points
      7d  → every 600s → max ~1008 points
    """
    return {"1h": 10, "6h": 30, "24h": 120, "7d": 600}.get(window, 10)


def _group_and_downsample(
    rows:     list,
    key_col:  int,
    ts_col:   int,
    val_col:  int,
    interval: int,
) -> Dict[str, List[Dict]]:
    """
    Group rows by key_col (e.g. bus_id), then downsample so that
    consecutive points are at least `interval` seconds apart.

    Returns: { key: [{"timestamp": ..., "value": ...}, ...] }
    """
    grouped: Dict[str, List] = {}
    for row in rows:
        key = row[key_col]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((row[ts_col], row[val_col]))

    result = {}
    for key, points in grouped.items():
        downsampled = []
        last_ts = None
        for ts_str, value in points:
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            if last_ts is None or (ts - last_ts).total_seconds() >= interval:
                downsampled.append({"timestamp": ts_str, "value": round(value, 4)})
                last_ts = ts
        result[key] = downsampled

    return result
