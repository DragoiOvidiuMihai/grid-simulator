"""
data_source.py — SCADA Data Source Abstraction
===============================================
Defines the DataSource interface and two concrete implementations:

  SyntheticDataSource   — generates realistic measurements mathematically.
                          No OpenDSS required. Used by default.

  OpenDSSDataSource     — runs an actual power flow via the existing Grid
                          Simulator solver. Activated via config flag.

The rest of the SCADA backend only ever calls DataSource methods and never
knows which implementation is active. Switching is done in scada_router.py.

Substation topology (fixed):
  Feeder 1 (11kV) ──CB1──┐
                        Bus A ──CB3── Bus B ──CB2── Feeder 2 (11kV)
                          │                   │
                         CB4                 CB5
                          │                   │
                         TX1                 TX2   (11kV / 0.4kV)
                          │                   │
                        Bus C               Bus D
                        /   \               /   \
                      CB6   CB7           CB8   CB9
                       │     │             │     │
                     Load1  PV1          Load2  Load3
"""

from __future__ import annotations

import logging
import math
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BusMeasurement:
    bus_id:      str
    voltage_kv:  float          # actual voltage in kV
    voltage_pu:  float          # per-unit voltage (nominal = 1.0)
    voltage_nom: float          # nominal voltage in kV


@dataclass
class BranchMeasurement:
    branch_id:    str
    current_a:    float         # RMS current in Amperes
    ampacity_a:   float         # rated ampacity in Amperes
    loading_pct:  float         # current / ampacity * 100
    power_kw:     float         # active power flow in kW
    power_kvar:   float         # reactive power flow in kvar


@dataclass
class TransformerMeasurement:
    tx_id:           str
    primary_kv:      float
    secondary_kv:    float
    current_a:       float      # primary-side current
    rated_kva:       float
    loading_pct:     float      # apparent power / rated kVA * 100
    power_kw:        float
    power_kvar:      float


@dataclass
class ScadaMeasurements:
    timestamp:      str                              # ISO-8601 UTC
    buses:          Dict[str, BusMeasurement]        = field(default_factory=dict)
    branches:       Dict[str, BranchMeasurement]     = field(default_factory=dict)
    transformers:   Dict[str, TransformerMeasurement]= field(default_factory=dict)
    breaker_states: Dict[str, str]                   = field(default_factory=dict)
    # str values: "CLOSED" | "OPEN"


# ─────────────────────────────────────────────────────────────────────────────
# ABSTRACT BASE
# ─────────────────────────────────────────────────────────────────────────────

class DataSource(ABC):
    """
    Abstract interface every data source must implement.
    One method: get_measurements() → ScadaMeasurements
    """

    @abstractmethod
    def get_measurements(self, breaker_states: Dict[str, str]) -> ScadaMeasurements:
        """
        Return the current SCADA measurements snapshot.

        Parameters
        ----------
        breaker_states : dict
            Current breaker positions keyed by breaker ID (e.g. "CB1": "CLOSED").
            The data source uses this to determine which parts of the network are
            energised and how power flows.

        Returns
        -------
        ScadaMeasurements
            Full set of bus voltages, branch currents, and transformer loadings.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC DATA SOURCE
# ─────────────────────────────────────────────────────────────────────────────

class SyntheticDataSource(DataSource):
    """
    Generates physically plausible measurements without OpenDSS.

    Behaviour:
    - Voltages follow a 24-hour sinusoidal profile (low at ~08:00 peak load,
      high at ~14:00 during solar generation) with small random noise.
    - Currents and loadings are derived from voltage deviations.
    - Open breakers cause downstream buses to lose voltage (0.0 pu).
    - All values respect the fixed substation topology.

    Rated values (realistic for an 11kV/0.4kV urban substation):
      TX1, TX2  : 630 kVA each
      Feeders   : ampacity 200 A at 11kV
      LV cables : ampacity 250 A at 0.4kV
    """

    # Nominal voltages
    HV_NOM_KV  = 11.0    # 11kV busbars (Bus A, Bus B)
    LV_NOM_KV  = 0.4     # 0.4kV busbars (Bus C, Bus D)

    # Equipment ratings
    TX_RATED_KVA   = 630.0   # kVA per transformer
    HV_AMPACITY_A  = 200.0   # HV feeder / busbar ampacity
    LV_AMPACITY_A  = 250.0   # LV feeder ampacity

    def __init__(self):
        self._noise_seed = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_measurements(self, breaker_states: Dict[str, str]) -> ScadaMeasurements:
        now_utc = datetime.now(timezone.utc)
        hour    = now_utc.hour + now_utc.minute / 60.0

        # Base voltage profile: 1.02 pu at 03:00 (light load),
        # dips to 0.97 pu at 09:00 (morning peak),
        # recovers to 1.01 pu at 14:00 (solar support),
        # dips again to 0.975 at 19:00 (evening peak)
        v_base = self._voltage_profile(hour)

        buses        = self._bus_measurements(breaker_states, v_base)
        branches     = self._branch_measurements(breaker_states, v_base, hour)
        transformers = self._transformer_measurements(breaker_states, v_base, hour)

        return ScadaMeasurements(
            timestamp      = now_utc.isoformat(),
            buses          = buses,
            branches       = branches,
            transformers   = transformers,
            breaker_states = dict(breaker_states),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _voltage_profile(self, hour: float) -> float:
        """
        Returns a base per-unit voltage for the given hour of day.
        Shaped to mimic real distribution network voltage behaviour.
        """
        # Primary sinusoid: morning dip
        morning_dip  = 0.025 * math.sin(math.pi * (hour - 3) / 9)
        # Secondary: evening dip
        evening_dip  = 0.020 * math.sin(math.pi * (hour - 14) / 8)
        # Solar boost midday
        solar_boost  = 0.010 * math.sin(math.pi * max(hour - 8, 0) / 8) if 8 <= hour <= 16 else 0.0
        # Small random noise (±0.003 pu)
        noise        = (random.random() - 0.5) * 0.006

        return 1.000 - morning_dip - evening_dip + solar_boost + noise

    def _is_energised(self, bus_id: str, breaker_states: Dict[str, str]) -> bool:
        """
        Determine if a bus is energised based on breaker states and topology.

        Topology energisation rules:
          Bus A — energised if CB1 closed (Feeder 1 source)
          Bus B — energised if CB2 closed (Feeder 2 source) OR
                  (CB3 closed AND Bus A energised)
          Bus C — energised if Bus A energised AND CB4 closed
          Bus D — energised if Bus B energised AND CB5 closed
        """
        def cb(name: str) -> bool:
            return breaker_states.get(name, "CLOSED") == "CLOSED"

        if bus_id == "BUS_A":
            return cb("CB1")
        if bus_id == "BUS_B":
            return cb("CB2") or (cb("CB3") and self._is_energised("BUS_A", breaker_states))
        if bus_id == "BUS_C":
            return self._is_energised("BUS_A", breaker_states) and cb("CB4")
        if bus_id == "BUS_D":
            return self._is_energised("BUS_B", breaker_states) and cb("CB5")
        return False

    def _bus_measurements(
        self,
        breaker_states: Dict[str, str],
        v_base: float,
    ) -> Dict[str, BusMeasurement]:

        buses = {}

        specs = [
            ("BUS_A", self.HV_NOM_KV,  0.000),   # slack-connected, minimal drop
            ("BUS_B", self.HV_NOM_KV,  0.002),   # slight drop via coupler
            ("BUS_C", self.LV_NOM_KV,  0.015),   # LV: larger drop through TX
            ("BUS_D", self.LV_NOM_KV,  0.018),
        ]

        for bus_id, nom_kv, drop in specs:
            energised = self._is_energised(bus_id, breaker_states)
            if energised:
                pu   = round(v_base - drop + (random.random() - 0.5) * 0.002, 4)
                kv   = round(pu * nom_kv, 4)
            else:
                pu   = 0.0
                kv   = 0.0

            buses[bus_id] = BusMeasurement(
                bus_id      = bus_id,
                voltage_kv  = kv,
                voltage_pu  = pu,
                voltage_nom = nom_kv,
            )

        return buses

    def _load_factor(self, hour: float) -> float:
        """Current load as fraction of peak (0–1)."""
        base = 0.45 + 0.30 * math.sin(math.pi * (hour - 6) / 12)
        return max(0.2, min(1.0, base + (random.random() - 0.5) * 0.05))

    def _branch_measurements(
        self,
        breaker_states: Dict[str, str],
        v_base: float,
        hour:   float,
    ) -> Dict[str, BranchMeasurement]:

        lf = self._load_factor(hour)

        def cb(name: str) -> bool:
            return breaker_states.get(name, "CLOSED") == "CLOSED"

        def make(branch_id, energised, base_kw, base_kvar, ampacity):
            if not energised:
                return BranchMeasurement(branch_id, 0, ampacity, 0, 0, 0)
            kw       = round(base_kw   * lf * (1 + (random.random() - 0.5) * 0.1), 1)
            kvar     = round(base_kvar * lf * (1 + (random.random() - 0.5) * 0.1), 1)
            # S = √(P²+Q²), I = S / (√3 · V)
            s_kva    = math.sqrt(kw**2 + kvar**2)
            i_a      = round(s_kva / (math.sqrt(3) * self.HV_NOM_KV), 1)
            loading  = round(i_a / ampacity * 100, 1)
            return BranchMeasurement(branch_id, i_a, ampacity, loading, kw, kvar)

        a_en = self._is_energised("BUS_A", breaker_states)
        b_en = self._is_energised("BUS_B", breaker_states)

        branches = {}

        # Feeder 1 → Bus A
        branches["FEEDER1"] = make(
            "FEEDER1", a_en and cb("CB1"),
            base_kw=380, base_kvar=120, ampacity=self.HV_AMPACITY_A,
        )
        # Feeder 2 → Bus B
        branches["FEEDER2"] = make(
            "FEEDER2", b_en and cb("CB2"),
            base_kw=350, base_kvar=110, ampacity=self.HV_AMPACITY_A,
        )
        # Bus coupler CB3
        coupler_en = a_en and b_en and cb("CB3")
        branches["COUPLER"] = make(
            "COUPLER", coupler_en,
            base_kw=80, base_kvar=25, ampacity=self.HV_AMPACITY_A,
        )

        return branches

    def _transformer_measurements(
        self,
        breaker_states: Dict[str, str],
        v_base: float,
        hour:   float,
    ) -> Dict[str, TransformerMeasurement]:

        lf = self._load_factor(hour)

        def cb(name: str) -> bool:
            return breaker_states.get(name, "CLOSED") == "CLOSED"

        def make_tx(tx_id, hv_bus, lv_cb, base_kw, base_kvar):
            hv_en = self._is_energised(hv_bus, breaker_states)
            en    = hv_en and cb(lv_cb)
            if not en:
                return TransformerMeasurement(
                    tx_id, self.HV_NOM_KV, self.LV_NOM_KV,
                    0, self.TX_RATED_KVA, 0, 0, 0,
                )
            kw       = round(base_kw   * lf * (1 + (random.random() - 0.5) * 0.08), 1)
            kvar     = round(base_kvar * lf * (1 + (random.random() - 0.5) * 0.08), 1)
            s_kva    = math.sqrt(kw**2 + kvar**2)
            i_a      = round(s_kva / (math.sqrt(3) * self.HV_NOM_KV), 1)
            loading  = round(s_kva / self.TX_RATED_KVA * 100, 1)
            return TransformerMeasurement(
                tx_id        = tx_id,
                primary_kv   = self.HV_NOM_KV,
                secondary_kv = self.LV_NOM_KV,
                current_a    = i_a,
                rated_kva    = self.TX_RATED_KVA,
                loading_pct  = loading,
                power_kw     = kw,
                power_kvar   = kvar,
            )

        return {
            "TX1": make_tx("TX1", "BUS_A", "CB4", base_kw=290, base_kvar=90),
            "TX2": make_tx("TX2", "BUS_B", "CB5", base_kw=270, base_kvar=85),
        }


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def create_data_source(use_opendss: bool = False) -> DataSource:
    """
    Return the appropriate DataSource implementation.

    Parameters
    ----------
    use_opendss : bool
        If True, return an OpenDSSDataSource (real power flow).
        If False (default), return a SyntheticDataSource.
    """
    if use_opendss:
        return OpenDSSDataSource()
    return SyntheticDataSource()


# ─────────────────────────────────────────────────────────────────────────────
# OPENDSS DATA SOURCE
# ─────────────────────────────────────────────────────────────────────────────

class OpenDSSDataSource(DataSource):
    """
    Runs a real AC power flow via OpenDSS for the fixed SCADA substation
    topology. Breaker open/close operations are modelled by switching line
    impedances between near-zero (closed) and very high (open).

    Topology modelled in DSS:
      - Voltage source (11kV slack, represents the external grid)
      - Feeder 1: source → CB1 switch → Bus A
      - Feeder 2: source → CB2 switch → Bus B
      - Bus coupler: Bus A → CB3 switch → Bus B
      - TX1: Bus A → CB4 switch → transformer primary → Bus C
      - TX2: Bus B → CB5 switch → transformer primary → Bus D
      - LV feeders: Bus C → CB6/CB7 → Load1/PV1
                    Bus D → CB8/CB9 → Load2/Load3

    Breakers are modelled as OpenDSS Line objects with SwtControl.
    This is the standard OpenDSS way to represent switching devices.

    Load values follow the same 24-hour profile as SyntheticDataSource
    to give physically consistent results across both modes.

    Equipment ratings match SyntheticDataSource exactly:
      TX1, TX2 : 630 kVA, 11kV/0.4kV, Dyn11, uk=4%
      Loads     : base peak values scaled by time-of-day load factor
      PV1       : 50 kW peak (connected to Bus C via CB7)
    """

    # Base load values (kW) — scaled by load factor each tick
    LOAD1_PEAK_KW = 180.0
    LOAD2_PEAK_KW = 165.0
    LOAD3_PEAK_KW = 140.0
    PV_PEAK_KW    =  50.0

    # Rated power factor for loads
    LOAD_PF       = 0.95
    TX_RATED_KVA  = 630.0
    HV_AMPACITY_A = 200.0
    LV_AMPACITY_A = 250.0
    HV_NOM_KV     = 11.0
    LV_NOM_KV     = 0.4

    def __init__(self):
        import opendssdirect as dss
        self._dss = dss
        self._last_breaker_states: Dict[str, str] = {}
        logger.info("OpenDSSDataSource initialised")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_measurements(self, breaker_states: Dict[str, str]) -> ScadaMeasurements:
        now_utc   = datetime.now(timezone.utc)
        hour      = now_utc.hour + now_utc.minute / 60.0
        lf        = self._load_factor(hour)
        pv_factor = self._pv_factor(hour)

        # Rebuild DSS circuit whenever breaker states change
        dss_script = self._build_dss_script(breaker_states, lf, pv_factor)
        result     = self._run(dss_script, breaker_states)

        return ScadaMeasurements(
            timestamp      = now_utc.isoformat(),
            buses          = result["buses"],
            branches       = result["branches"],
            transformers   = result["transformers"],
            breaker_states = dict(breaker_states),
        )

    @property
    def source_name(self) -> str:
        return "OpenDSS"

    # ── DSS script builder ────────────────────────────────────────────────────

    def _build_dss_script(
        self,
        bs:        Dict[str, str],
        lf:        float,
        pv_factor: float,
    ) -> str:
        """
        Build a complete DSS script for the SCADA substation.
        Breaker state is encoded as line switch state.
        """
        cb = lambda name: bs.get(name, "CLOSED") == "CLOSED"

        # Load values scaled by load factor
        p1   = round(self.LOAD1_PEAK_KW * lf, 1)
        p2   = round(self.LOAD2_PEAK_KW * lf, 1)
        p3   = round(self.LOAD3_PEAK_KW * lf, 1)
        pv_p = round(self.PV_PEAK_KW * pv_factor, 1)
        pf   = self.LOAD_PF

        def sw(closed: bool) -> str:
            """Switch line: closed = low impedance, open = high impedance."""
            return "switch=y enabled=y" if closed else "switch=y enabled=n"

        lines = [
            "Clear",
            "Set DefaultBaseFrequency=50",
            "",
            "! ── Voltage source (external grid, 11kV slack) ──────────────",
            "New Circuit.SCADA_Substation basekv=11.0 pu=1.0 phases=3 bus1=SOURCE_BUS",
            "  ~ Isc3=10000 Isc1=9000",
            "",
            "! ── HV busbars (zero-impedance lines to represent busbars) ──",
            "New Line.BUSBAR_A  bus1=SOURCE_BUS.1.2.3 bus2=BUS_A.1.2.3  r1=0.0001 x1=0.001 c1=0 length=0.001 units=km phases=3",
            "New Line.BUSBAR_B  bus1=SOURCE_BUS.1.2.3 bus2=BUS_B_SRC.1.2.3 r1=0.0001 x1=0.001 c1=0 length=0.001 units=km phases=3",
            "",
            "! ── Feeder incomers (CB1, CB2) ───────────────────────────────",
            f"New Line.CB1  bus1=BUS_A.1.2.3     bus2=BUS_A_CB1.1.2.3  r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB1'))}",
            f"New Line.CB2  bus1=BUS_B_SRC.1.2.3 bus2=BUS_B.1.2.3      r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB2'))}",
            "",
            "! ── Bus coupler (CB3) ────────────────────────────────────────",
            f"New Line.CB3  bus1=BUS_A_CB1.1.2.3 bus2=BUS_B.1.2.3      r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB3'))}",
            "",
            "! ── TX1 branch (CB4 + transformer) ──────────────────────────",
            f"New Line.CB4  bus1=BUS_A_CB1.1.2.3 bus2=BUS_A_TX1.1.2.3  r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB4'))}",
            "New Transformer.TX1 phases=3 windings=2",
            "  ~ wdg=1 bus=BUS_A_TX1.1.2.3  kv=11.0 kva=630 conn=delta",
            "  ~ wdg=2 bus=BUS_C.1.2.3      kv=0.4  kva=630 conn=wye   %r=0.5 xhl=4.0",
            "",
            "! ── TX2 branch (CB5 + transformer) ──────────────────────────",
            f"New Line.CB5  bus1=BUS_B.1.2.3     bus2=BUS_B_TX2.1.2.3  r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB5'))}",
            "New Transformer.TX2 phases=3 windings=2",
            "  ~ wdg=1 bus=BUS_B_TX2.1.2.3  kv=11.0 kva=630 conn=delta",
            "  ~ wdg=2 bus=BUS_D.1.2.3      kv=0.4  kva=630 conn=wye   %r=0.5 xhl=4.0",
            "",
            "! ── LV feeders ───────────────────────────────────────────────",
            f"New Line.CB6  bus1=BUS_C.1.2.3 bus2=BUS_C_L1.1.2.3 r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB6'))}",
            f"New Line.CB7  bus1=BUS_C.1.2.3 bus2=BUS_C_PV.1.2.3 r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB7'))}",
            f"New Line.CB8  bus1=BUS_D.1.2.3 bus2=BUS_D_L2.1.2.3 r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB8'))}",
            f"New Line.CB9  bus1=BUS_D.1.2.3 bus2=BUS_D_L3.1.2.3 r1=0.001 x1=0.01 c1=0 length=0.001 units=km phases=3 {sw(cb('CB9'))}",
            "",
            "! ── Loads ────────────────────────────────────────────────────",
            f"New Load.LOAD1 bus1=BUS_C_L1.1.2.3 phases=3 kv=0.4 kw={p1} pf={pf} model=1",
            f"New Load.LOAD2 bus1=BUS_D_L2.1.2.3 phases=3 kv=0.4 kw={p2} pf={pf} model=1",
            f"New Load.LOAD3 bus1=BUS_D_L3.1.2.3 phases=3 kv=0.4 kw={p3} pf={pf} model=1",
            "",
            "! ── PV system ────────────────────────────────────────────────",
            f"New Generator.PV1 bus1=BUS_C_PV.1.2.3 phases=3 kv=0.4 kw={pv_p} pf=1.0 model=1" if pv_p > 0 else "! PV offline (night)",
            "",
            "! ── Solve ───────────────────────────────────────────────────",
            "Set VoltageBases=[11.0, 0.4]",
            "CalcVoltageBases",
            "Set MaxIter=100",
            "Set Tolerance=0.0001",
            "Solve",
        ]
        return "\n".join(lines)

    # ── OpenDSS runner ────────────────────────────────────────────────────────

    def _run(
        self,
        dss_script:     str,
        breaker_states: Dict[str, str],
    ) -> dict:
        """Execute DSS script and map results to ScadaMeasurements fields."""
        dss = self._dss

        try:
            dss.Text.Command("Clear")
            for line in dss_script.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("!"):
                    continue
                dss.Text.Command(stripped)
        except Exception as exc:
            logger.error("OpenDSS script error: %s", exc)
            return self._fallback(breaker_states)

        if not dss.Solution.Converged():
            logger.warning("OpenDSS power flow did not converge — using synthetic fallback")
            return self._fallback(breaker_states)

        buses        = self._read_buses(breaker_states)
        branches     = self._read_branches(breaker_states)
        transformers = self._read_transformers(breaker_states, buses)

        return {"buses": buses, "branches": branches, "transformers": transformers}

    # ── Result readers ────────────────────────────────────────────────────────

    def _read_buses(self, breaker_states: Dict[str, str]) -> Dict[str, BusMeasurement]:
        dss = self._dss
        buses = {}

        mapping = {
            "BUS_A":    ("BUS_A_CB1",  self.HV_NOM_KV),
            "BUS_B":    ("BUS_B",      self.HV_NOM_KV),
            "BUS_C":    ("BUS_C",      self.LV_NOM_KV),
            "BUS_D":    ("BUS_D",      self.LV_NOM_KV),
        }

        for scada_id, (dss_bus, nom_kv) in mapping.items():
            try:
                dss.Circuit.SetActiveBus(dss_bus)
                pu_data = dss.Bus.puVmagAngle()
                if pu_data and len(pu_data) >= 2:
                    pus = [pu_data[i] for i in range(0, len(pu_data), 2)]
                    pu  = round(sum(pus) / len(pus), 4)
                    kv  = round(pu * nom_kv, 4)
                else:
                    pu, kv = 0.0, 0.0
            except Exception:
                pu, kv = 0.0, 0.0

            buses[scada_id] = BusMeasurement(
                bus_id      = scada_id,
                voltage_kv  = kv,
                voltage_pu  = pu,
                voltage_nom = nom_kv,
            )

        return buses

    def _read_branches(self, breaker_states: Dict[str, str]) -> Dict[str, BranchMeasurement]:
        dss = self._dss
        branches = {}
        cb = lambda name: breaker_states.get(name, "CLOSED") == "CLOSED"

        feeder_map = {
            "FEEDER1": ("CB1",  self.HV_AMPACITY_A),
            "FEEDER2": ("CB2",  self.HV_AMPACITY_A),
            "COUPLER": ("CB3",  self.HV_AMPACITY_A),
        }

        for branch_id, (cb_line, ampacity) in feeder_map.items():
            try:
                dss.Circuit.SetActiveElement(f"Line.{cb_line}")
                powers   = dss.CktElement.Powers()
                currents = dss.CktElement.CurrentsMagAng()

                if currents and len(currents) >= 2:
                    mags      = [currents[i] for i in range(0, min(6, len(currents)), 2)]
                    current_a = round(max(mags), 1)
                else:
                    current_a = 0.0

                if powers and len(powers) >= 6:
                    kw   = round(-sum(powers[i]   for i in range(0, 6, 2)) / 1000, 1)
                    kvar = round(-sum(powers[i+1] for i in range(0, 6, 2)) / 1000, 1)
                else:
                    kw = kvar = 0.0

                loading = round(current_a / ampacity * 100, 1) if ampacity > 0 else 0.0

            except Exception:
                current_a = kw = kvar = loading = 0.0

            branches[branch_id] = BranchMeasurement(
                branch_id   = branch_id,
                current_a   = current_a,
                ampacity_a  = ampacity,
                loading_pct = loading,
                power_kw    = kw,
                power_kvar  = kvar,
            )

        return branches

    def _read_transformers(
        self,
        breaker_states: Dict[str, str],
        buses: Dict[str, BusMeasurement],
    ) -> Dict[str, TransformerMeasurement]:
        dss = self._dss
        transformers = {}

        tx_map = {
            "TX1": ("TX1", "BUS_C"),
            "TX2": ("TX2", "BUS_D"),
        }

        for tx_id, (dss_name, lv_bus) in tx_map.items():
            try:
                dss.Circuit.SetActiveElement(f"Transformer.{dss_name}")
                powers   = dss.CktElement.Powers()
                currents = dss.CktElement.CurrentsMagAng()

                if currents and len(currents) >= 2:
                    mags      = [currents[i] for i in range(0, min(6, len(currents)), 2)]
                    current_a = round(max(mags), 1)
                else:
                    current_a = 0.0

                if powers and len(powers) >= 6:
                    kw   = round(-sum(powers[i]   for i in range(0, 6, 2)) / 1000, 1)
                    kvar = round(-sum(powers[i+1] for i in range(0, 6, 2)) / 1000, 1)
                else:
                    kw = kvar = 0.0

                s_kva    = math.sqrt(kw**2 + kvar**2) * 1000
                loading  = round(s_kva / self.TX_RATED_KVA * 100, 1)

            except Exception:
                current_a = kw = kvar = loading = 0.0

            transformers[tx_id] = TransformerMeasurement(
                tx_id        = tx_id,
                primary_kv   = self.HV_NOM_KV,
                secondary_kv = self.LV_NOM_KV,
                current_a    = current_a,
                rated_kva    = self.TX_RATED_KVA,
                loading_pct  = loading,
                power_kw     = kw,
                power_kvar   = kvar,
            )

        return transformers

    def _fallback(self, breaker_states: Dict[str, str]) -> dict:
        """Return zero measurements on solver failure."""
        zero_bus = lambda bus_id, nom: BusMeasurement(bus_id, 0.0, 0.0, nom)
        zero_br  = lambda br_id, amp: BranchMeasurement(br_id, 0.0, amp, 0.0, 0.0, 0.0)
        zero_tx  = lambda tx_id: TransformerMeasurement(tx_id, self.HV_NOM_KV, self.LV_NOM_KV, 0.0, self.TX_RATED_KVA, 0.0, 0.0, 0.0)
        return {
            "buses":        {b: zero_bus(b, n) for b, n in [("BUS_A", 11.0), ("BUS_B", 11.0), ("BUS_C", 0.4), ("BUS_D", 0.4)]},
            "branches":     {b: zero_br(b, a)  for b, a in [("FEEDER1", 200.0), ("FEEDER2", 200.0), ("COUPLER", 200.0)]},
            "transformers": {t: zero_tx(t)      for t in ["TX1", "TX2"]},
        }

    # ── Profile helpers (same shape as SyntheticDataSource) ──────────────────

    def _load_factor(self, hour: float) -> float:
        base = 0.45 + 0.30 * math.sin(math.pi * (hour - 6) / 12)
        return max(0.2, min(1.0, base))

    def _pv_factor(self, hour: float) -> float:
        if hour < 6 or hour > 20:
            return 0.0
        return max(0.0, math.sin(math.pi * (hour - 6) / 14))
