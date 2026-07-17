"""
Distribution Grid Simulator — Component Data Models
====================================================
These Pydantic schemas define the data contract between:
  - The React frontend (what the user builds visually)
  - The FastAPI backend (what gets validated and stored)
  - The OpenDSS translator (what gets converted to DSS script)

All electrical values follow IEC standards (EU grid).
Units are explicit in every field name to avoid ambiguity.

Author: Grid Simulator Project
Standard: IEC 61089, IEC 60502-2, IEC 60228, EN 50182
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# Enums enforce valid choices at the schema level — if the frontend sends
# an invalid value, Pydantic rejects it before it ever reaches the solver.
# ─────────────────────────────────────────────────────────────────────────────

class PhaseCount(int, Enum):
    SINGLE = 1
    THREE  = 3


class ConnectionType(str, Enum):
    WYE   = "wye"
    DELTA = "delta"


class LoadModel(int, Enum):
    """
    OpenDSS load models.
    Model 1 = Constant P & Q (default for most steady-state studies)
    Model 2 = Constant impedance Z (voltage-dependent, used for some industrial loads)
    Model 5 = Constant current magnitude
    """
    CONSTANT_PQ = 1
    CONSTANT_Z  = 2
    CONSTANT_I  = 5


class GeneratorModel(int, Enum):
    """
    OpenDSS generator models.
    Model 1 = PV node — generator controls kW output and terminal voltage.
               This is the correct model for a synchronous generator in power flow.
    Model 7 = Inverter model — used for inverter-based resources (PVSystem handles
               this automatically, so Generator objects should always use Model 1).
    """
    PV_NODE = 1


class TransformerConnection(str, Enum):
    """
    Standard EU distribution transformer vector groups.
    Dyn11 is the dominant standard across European 11kV/0.4kV networks.
    """
    DYN11 = "Dyn11"   # Delta primary, Star+neutral secondary, 30° lag — EU standard
    YNyn0 = "YNyn0"   # Star primary and secondary, 0° — used in some HV/MV applications
    Dd0   = "Dd0"     # Delta-Delta, 0° — industrial, no neutral


# ─────────────────────────────────────────────────────────────────────────────
# 1. BUS (PRIMARY — MV)
#
# A bus is a node in the network. Every other component connects TO a bus.
# Think of it as a junction point in the single-line diagram.
# The primary bus represents a Medium Voltage (11 kV) node — typically at the
# top of a distribution feeder or on the MV side of a transformer.
# ─────────────────────────────────────────────────────────────────────────────

class BusPrimary(BaseModel):
    id:           str   = Field(..., description="Unique identifier, e.g. 'BUS_MV_01'")
    name:         str   = Field(..., description="Human-readable label shown on canvas")
    base_kv:      float = Field(default=11.0,  gt=0, description="Nominal voltage in kV. EU MV standard: 11 kV")
    phases:       PhaseCount = Field(default=PhaseCount.THREE)

    # OpenDSS translation hint (used by the translator layer, not editable by user)
    @property
    def dss_name(self) -> str:
        return self.id.replace(" ", "_").upper()

    class Config:
        # Allows the property above to coexist with Pydantic fields
        arbitrary_types_allowed = True


# ─────────────────────────────────────────────────────────────────────────────
# 2. BUS (SECONDARY — LV)
#
# Represents a Low Voltage (0.4 kV) node — typically the secondary side of a
# distribution transformer, where loads and small generators connect.
# Kept as a separate class from BusPrimary because the voltage level affects
# how connected components are validated (e.g. residential loads must connect
# to LV buses, not MV buses).
# ─────────────────────────────────────────────────────────────────────────────

class BusSecondary(BaseModel):
    id:      str        = Field(..., description="Unique identifier, e.g. 'BUS_LV_01'")
    name:    str        = Field(..., description="Human-readable label shown on canvas")
    base_kv: float      = Field(default=0.4, gt=0, description="Nominal voltage in kV. EU LV standard: 0.4 kV")
    phases:  PhaseCount = Field(default=PhaseCount.THREE)

    @property
    def dss_name(self) -> str:
        return self.id.replace(" ", "_").upper()


# ─────────────────────────────────────────────────────────────────────────────
# 3. TWO-WINDING TRANSFORMER
#
# Connects a primary (MV) bus to a secondary (LV) bus.
# The most critical parameters for OpenDSS are %R and %X (per-unit impedance
# expressed as percentages). These come from the nameplate / test certificate.
# Vector group (Dyn11) determines how zero-sequence current flows — essential
# for correct fault analysis later.
# ─────────────────────────────────────────────────────────────────────────────

class TwoWindingTransformer(BaseModel):
    id:              str   = Field(..., description="Unique identifier, e.g. 'TX_01'")
    name:            str   = Field(..., description="Human-readable label")
    from_bus_id:     str   = Field(..., description="ID of the primary (MV) bus")
    to_bus_id:       str   = Field(..., description="ID of the secondary (LV) bus")

    # Ratings
    rating_kva:      float = Field(default=500.0,  gt=0,  description="Apparent power rating in kVA")
    primary_kv:      float = Field(default=11.0,   gt=0,  description="Primary winding voltage in kV")
    secondary_kv:    float = Field(default=0.4,    gt=0,  description="Secondary winding voltage in kV")

    # Impedance (from nameplate or test certificate)
    percent_r:       float = Field(default=1.1,    gt=0,  le=5.0,  description="Winding resistance as % of rated impedance")
    percent_x:       float = Field(default=4.0,    gt=0,  le=10.0, description="Leakage reactance as % of rated impedance")

    # Connection
    vector_group:    TransformerConnection = Field(default=TransformerConnection.DYN11)
    phases:          PhaseCount            = Field(default=PhaseCount.THREE)

    @model_validator(mode="after")
    def validate_voltage_ratio(self) -> TwoWindingTransformer:
        """
        Sanity check: primary must be higher voltage than secondary.
        If someone wires it backwards the translator would produce wrong results.
        """
        if self.primary_kv <= self.secondary_kv:
            raise ValueError(
                f"primary_kv ({self.primary_kv}) must be greater than secondary_kv ({self.secondary_kv}). "
                "Check your transformer winding assignment."
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 4. OVERHEAD LINE
#
# Represents a span of ACSR 150 mm² overhead conductor between two buses.
# In OpenDSS, lines are defined via a LineCode (the conductor properties) and
# a Line object (the specific length and bus connections).
# Both positive-sequence (R1, X1) and zero-sequence (R0, X0) values are
# required for unbalanced power flow and fault analysis.
# ─────────────────────────────────────────────────────────────────────────────

class OverheadLine(BaseModel):
    id:             str        = Field(..., description="Unique identifier, e.g. 'OHL_01'")
    name:           str        = Field(..., description="Human-readable label")
    from_bus_id:    str        = Field(..., description="ID of the sending-end bus")
    to_bus_id:      str        = Field(..., description="ID of the receiving-end bus")
    length_km:      float      = Field(..., gt=0, description="Length of this line section in km")

    # IEC 61089 / EN 50182 values for ACSR 150 mm²
    r1_ohm_per_km:  float = Field(default=0.196, gt=0, description="Positive-sequence resistance Ω/km at 75°C")
    x1_ohm_per_km:  float = Field(default=0.332, gt=0, description="Positive-sequence reactance Ω/km")
    r0_ohm_per_km:  float = Field(default=0.588, gt=0, description="Zero-sequence resistance Ω/km (earth return)")
    x0_ohm_per_km:  float = Field(default=0.996, gt=0, description="Zero-sequence reactance Ω/km (earth return)")
    ampacity_a:     float = Field(default=415.0, gt=0, description="Thermal current limit in Amperes at 75°C")
    phases:         PhaseCount = Field(default=PhaseCount.THREE)

    @model_validator(mode="after")
    def validate_buses_differ(self) -> OverheadLine:
        if self.from_bus_id == self.to_bus_id:
            raise ValueError("from_bus_id and to_bus_id must be different — a line cannot connect a bus to itself.")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 5. UNDERGROUND CABLE
#
# Represents a section of 12/20 kV XLPE 150 mm² Cu cable.
# Key difference from overhead line: cables have significant shunt capacitance
# (C1) which affects voltage profiles on long cable runs — this is why it has
# its own class rather than reusing OverheadLine.
# The voltage rating (12/20 kV) means: 12 kV phase-to-phase, 20 kV system
# voltage — correct IEC 60502-2 designation for an 11 kV network cable.
# ─────────────────────────────────────────────────────────────────────────────

class UndergroundCable(BaseModel):
    id:             str        = Field(..., description="Unique identifier, e.g. 'UGC_01'")
    name:           str        = Field(..., description="Human-readable label")
    from_bus_id:    str        = Field(..., description="ID of the sending-end bus")
    to_bus_id:      str        = Field(..., description="ID of the receiving-end bus")
    length_km:      float      = Field(..., gt=0, description="Length of this cable section in km")

    # IEC 60502-2 / IEC 60228 values for 12/20 kV XLPE 150 mm² Cu
    r1_ohm_per_km:  float = Field(default=0.124, gt=0, description="Positive-sequence resistance Ω/km at 90°C")
    x1_ohm_per_km:  float = Field(default=0.113, gt=0, description="Positive-sequence reactance Ω/km (trefoil)")
    r0_ohm_per_km:  float = Field(default=0.372, gt=0, description="Zero-sequence resistance Ω/km (screen return)")
    x0_ohm_per_km:  float = Field(default=0.113, gt=0, description="Zero-sequence reactance Ω/km")
    c1_uf_per_km:   float = Field(default=0.28,  gt=0, description="Positive-sequence shunt capacitance µF/km")
    ampacity_a:     float = Field(default=360.0, gt=0, description="Thermal current limit in Amperes (direct buried, 20°C soil)")
    phases:         PhaseCount = Field(default=PhaseCount.THREE)

    @model_validator(mode="after")
    def validate_buses_differ(self) -> UndergroundCable:
        if self.from_bus_id == self.to_bus_id:
            raise ValueError("from_bus_id and to_bus_id must be different.")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 6. RESIDENTIAL LOAD
#
# Represents a single-phase household consumer connected to an LV bus.
# Critical modelling decisions:
#   - Single-phase (phases=1): a house draws from one phase, not three.
#     In OpenDSS this means connecting to BUS.1 (phase A), BUS.2 (phase B),
#     or BUS.3 (phase C). Phase assignment is tracked here.
#   - base_kv is phase-to-neutral (0.4/√3 = 0.231 kV), NOT line-to-line.
#   - OpenDSS requires BOTH kw and kvar — power factor alone is not accepted.
#     kvar is stored explicitly (derived: kw × tan(arccos(pf))).
# ─────────────────────────────────────────────────────────────────────────────

class PhaseAssignment(int, Enum):
    """Which phase of the LV bus this single-phase load connects to."""
    A = 1
    B = 2
    C = 3


class ResidentialLoad(BaseModel):
    id:             str            = Field(..., description="Unique identifier, e.g. 'LOAD_RES_01'")
    name:           str            = Field(..., description="Human-readable label")
    bus_id:         str            = Field(..., description="ID of the LV bus this load connects to")
    phase:          PhaseAssignment = Field(default=PhaseAssignment.A, description="Which phase (A/B/C) this household draws from")

    # Power
    kw:             float = Field(default=5.0,   gt=0, description="Active power demand in kW (peak)")
    kvar:           float = Field(default=1.64,  ge=0, description="Reactive power demand in kVAR (lagging). Derived: kw × tan(arccos(0.95))")
    base_kv:        float = Field(default=0.231, gt=0, description="Phase-to-neutral voltage in kV (0.4/√3 = 0.231)")
    load_model:     LoadModel = Field(default=LoadModel.CONSTANT_PQ)
    phases:         PhaseCount = Field(default=PhaseCount.SINGLE)

    @model_validator(mode="after")
    def validate_kvar_not_larger_than_kw(self) -> ResidentialLoad:
        """
        A residential load with kvar > kw would imply PF < 0.707.
        That's physically possible but almost certainly a data entry error
        for a household — warn the user.
        """
        if self.kvar > self.kw:
            raise ValueError(
                f"kvar ({self.kvar}) > kw ({self.kw}) implies PF < 0.707. "
                "This is unusual for a residential load — check your inputs."
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 7. INDUSTRIAL LOAD
#
# Represents a three-phase industrial consumer (factory, warehouse, etc.)
# connected to an LV or MV bus.
# Key differences from ResidentialLoad:
#   - Three-phase: industrial loads are balanced three-phase consumers.
#   - Higher kvar: industrial motors have lower power factor (0.85–0.92 typical).
#   - base_kv is line-to-line (0.4 kV), not phase-to-neutral.
#   - No phase assignment — connects to all three phases simultaneously.
# ─────────────────────────────────────────────────────────────────────────────

class IndustrialLoad(BaseModel):
    id:          str       = Field(..., description="Unique identifier, e.g. 'LOAD_IND_01'")
    name:        str       = Field(..., description="Human-readable label")
    bus_id:      str       = Field(..., description="ID of the bus this load connects to")

    # Power
    kw:          float     = Field(default=250.0, gt=0,  description="Active power demand in kW (peak)")
    kvar:        float     = Field(default=121.0, ge=0,  description="Reactive power demand in kVAR (lagging). Derived: 250 × tan(arccos(0.90)) = 121.1")
    base_kv:     float     = Field(default=0.4,   gt=0,  description="Line-to-line bus voltage in kV")
    load_model:  LoadModel = Field(default=LoadModel.CONSTANT_PQ)
    phases:      PhaseCount = Field(default=PhaseCount.THREE)


# ─────────────────────────────────────────────────────────────────────────────
# 8a. SYNCHRONOUS GENERATOR
#
# Represents a diesel genset or any rotating synchronous machine.
# In OpenDSS this is a 'Generator' object operating as a PV node:
#   - P is fixed (the generator produces a set kW output)
#   - V is held constant (the AVR regulates terminal voltage)
#   - Q is calculated by the solver (within the kvar capability limits)
#
# If this is the only generator in an islanded network it becomes the
# slack bus — the reference for voltage magnitude and angle.
# ─────────────────────────────────────────────────────────────────────────────

class SynchronousGenerator(BaseModel):
    id:              str           = Field(..., description="Unique identifier, e.g. 'GEN_SYNC_01'")
    name:            str           = Field(..., description="Human-readable label")
    bus_id:          str           = Field(..., description="ID of the bus this generator connects to")

    # Ratings
    rated_kw:        float = Field(default=500.0,  gt=0, description="Nameplate active power output in kW")
    rated_kv:        float = Field(default=0.4,    gt=0, description="Terminal voltage in kV (line-to-line)")
    power_factor:    float = Field(default=0.8,    gt=0, le=1.0, description="Rated power factor (lagging)")

    # Reactive capability — derived: rated_kw × tan(arccos(pf))
    kvar_max:        float = Field(default=375.0,  description="Maximum reactive power output in kVAR (absorb or inject)")
    kvar_min:        float = Field(default=-375.0, description="Minimum reactive power (negative = absorbing)")

    # OpenDSS model
    model:           GeneratorModel = Field(default=GeneratorModel.PV_NODE)
    phases:          PhaseCount     = Field(default=PhaseCount.THREE)
    connection:      ConnectionType = Field(default=ConnectionType.WYE)
    is_slack:        bool = Field(default=False, description="Set True if this generator is the network slack/reference bus")

    @model_validator(mode="after")
    def validate_kvar_symmetry(self) -> SynchronousGenerator:
        if self.kvar_min >= self.kvar_max:
            raise ValueError("kvar_min must be less than kvar_max.")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 8b. SOLAR PV (INVERTER-BASED)
#
# Represents a grid-connected solar PV array with an inverter.
# MUST use OpenDSS 'PVSystem' object — NOT a Generator object.
# Key differences from SynchronousGenerator:
#   - Output is weather-dependent (irradiance, temperature)
#   - The inverter limits current to rated kVA — it cannot overload
#   - Reactive power capability depends on inverter headroom (S² = P² + Q²)
#   - In Phase 1 (steady-state AC) irradiance is fixed at 1.0 kW/m² (STC)
#   - In Phase 2 (time-series) irradiance becomes a profile input
#
# kva_rated is slightly above kw_peak to account for the inverter
# operating at non-unity PF. Rule of thumb: kva_rated = kw_peak / 0.98
# ─────────────────────────────────────────────────────────────────────────────

class SolarPV(BaseModel):
    id:                   str   = Field(..., description="Unique identifier, e.g. 'PV_01'")
    name:                 str   = Field(..., description="Human-readable label")
    bus_id:               str   = Field(..., description="ID of the LV bus this PV system connects to")

    # Ratings
    kw_peak:              float = Field(default=100.0, gt=0, description="DC nameplate power at STC (1.0 kW/m², 25°C) in kW")
    kva_rated:            float = Field(default=102.0, gt=0, description="Inverter apparent power rating in kVA. Rule: kw_peak / efficiency")
    rated_kv:             float = Field(default=0.4,   gt=0, description="AC terminal voltage in kV (line-to-line)")

    # Inverter settings
    power_factor:         float = Field(default=1.0,   ge=-1.0, le=1.0, description="Operating PF. 1.0 = unity. Negative = leading (absorbing Q)")
    efficiency:           float = Field(default=0.98,  gt=0,    le=1.0, description="Inverter efficiency at rated output")

    # Irradiance (Phase 1: fixed at STC; Phase 2: will become a time-series profile)
    irradiance_kw_per_m2: float = Field(default=1.0,   gt=0, description="Incident irradiance in kW/m². 1.0 = Standard Test Condition (IEC 61215)")
    temp_coefficient_pct: float = Field(default=-0.35, description="Power temperature coefficient in %/°C (negative = output drops with heat)")

    phases:               PhaseCount     = Field(default=PhaseCount.THREE)
    connection:           ConnectionType = Field(default=ConnectionType.WYE)

    @model_validator(mode="after")
    def validate_kva_covers_kw(self) -> SolarPV:
        if self.kva_rated < self.kw_peak * self.efficiency:
            raise ValueError(
                f"kva_rated ({self.kva_rated}) is less than kw_peak × efficiency "
                f"({self.kw_peak} × {self.efficiency} = {self.kw_peak * self.efficiency:.1f}). "
                "The inverter cannot deliver the panel's rated output."
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
# TOP-LEVEL GRID MODEL
#
# This is the envelope that wraps every component into a single object.
# When the frontend sends a simulation request to the backend, it sends
# ONE Grid object — the entire network in a single JSON payload.
# The backend validates it with Pydantic, then passes it to the translator.
# ─────────────────────────────────────────────────────────────────────────────

class Grid(BaseModel):
    """
    The complete network definition.
    This is what gets serialised to JSON and sent from frontend to backend.
    """
    id:           str  = Field(..., description="Unique grid/scenario identifier")
    name:         str  = Field(..., description="Human-readable scenario name, e.g. 'Urban Feeder with Solar'")
    description:  Optional[str] = Field(default=None)

    # Component lists — a grid can have zero or more of each
    mv_buses:             list[BusPrimary]           = Field(default_factory=list)
    lv_buses:             list[BusSecondary]          = Field(default_factory=list)
    transformers:         list[TwoWindingTransformer] = Field(default_factory=list)
    overhead_lines:       list[OverheadLine]          = Field(default_factory=list)
    underground_cables:   list[UndergroundCable]      = Field(default_factory=list)
    residential_loads:    list[ResidentialLoad]       = Field(default_factory=list)
    industrial_loads:     list[IndustrialLoad]        = Field(default_factory=list)
    synchronous_generators: list[SynchronousGenerator] = Field(default_factory=list)
    solar_pv_systems:     list[SolarPV]               = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_has_buses(self) -> Grid:
        """A grid with no buses cannot be simulated."""
        if not self.mv_buses and not self.lv_buses:
            raise ValueError("Grid must contain at least one bus before it can be simulated.")
        return self

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Grid:
        """
        Every component across the entire grid must have a unique ID.
        Duplicate IDs would cause the translator to produce a broken DSS script.
        """
        all_components = (
            self.mv_buses + self.lv_buses + self.transformers +
            self.overhead_lines + self.underground_cables +
            self.residential_loads + self.industrial_loads +
            self.synchronous_generators + self.solar_pv_systems
        )
        ids = [c.id for c in all_components]
        duplicates = [id for id in ids if ids.count(id) > 1]
        if duplicates:
            raise ValueError(f"Duplicate component IDs found: {list(set(duplicates))}. Every component must have a unique ID.")
        return self

    @model_validator(mode="after")
    def validate_slack_bus(self) -> Grid:
        """
        A valid power flow requires exactly one slack bus reference.
        In OpenDSS the 'sourcebus' acts as slack by default, but if the user
        places a synchronous generator marked as slack, exactly one must exist.
        """
        slack_gens = [g for g in self.synchronous_generators if g.is_slack]
        if len(slack_gens) > 1:
            raise ValueError(
                f"Only one generator can be the slack bus. "
                f"Found {len(slack_gens)}: {[g.id for g in slack_gens]}"
            )
        return self

# ─────────────────────────────────────────────────────────────────────────────
# TIME-SERIES SIMULATION REQUEST
# Wraps the existing Grid model with Phase 2 parameters.
# ─────────────────────────────────────────────────────────────────────────────

class TimeSeriesRequest(BaseModel):
    """
    Request body for POST /simulate-timeseries.
    Contains the full grid definition plus time-series parameters.
    """
    grid:                 Grid
    season:               str   = Field(default="summer", pattern="^(summer|winter)$")
    peak_load_multiplier: float = Field(default=1.0, gt=0.1, le=2.0)