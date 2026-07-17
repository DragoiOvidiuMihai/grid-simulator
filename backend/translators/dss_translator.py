"""
DSS Script Translator
=====================
Converts a validated Grid object (from models.py) into a DSS script string
that OpenDSS can execute directly.

Structure:
  - One private function per component type  (_translate_*)
  - One public function that assembles the full script (translate_grid)

Every function receives a component object and returns a string —
one or more lines of valid DSS syntax.
"""

from backend.models.models import (
    Grid,
    BusPrimary,
    BusSecondary,
    TwoWindingTransformer,
    OverheadLine,
    UndergroundCable,
    ResidentialLoad,
    IndustrialLoad,
    SynchronousGenerator,
    SolarPV,
    PhaseAssignment,
    TransformerConnection,
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _clean_id(raw_id: str) -> str:
    """
    OpenDSS names cannot contain spaces.
    Replace any spaces with underscores and upper-case everything.
    Example: 'Bus MV 01' → 'BUS_MV_01'
    """
    return raw_id.replace(" ", "_").upper()


# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT TRANSLATORS
# Each function takes one component and returns a DSS string.
# ─────────────────────────────────────────────────────────────────────────────

def _translate_mv_bus(bus: BusPrimary) -> str:
    """
    OpenDSS creates buses implicitly when components reference them.
    Anchor reactors must NOT be used — they create isolated voltage islands
    that break CalcVoltageBases, producing near-zero pu voltages.
    Buses come alive when a transformer, line, or load references them.
    """
    return f"! MV Bus declared: {bus.name} ({bus.base_kv} kV)"


def _translate_lv_bus(bus: BusSecondary) -> str:
    return f"! LV Bus declared: {bus.name} ({bus.base_kv} kV)"


def _translate_transformer(tx: TwoWindingTransformer) -> str:
    """
    Key fields:
      buses  = [primary_bus, secondary_bus]
      conns  = [delta, wye] for Dyn11  |  [wye, wye] for YNyn0
      kVs    = [primary_kV, secondary_kV]
      kVAs   = [rating, rating]  (same on both sides for a standard 2-winding TX)
      %R     = winding resistance as percentage
      XHL    = leakage reactance High-to-Low as percentage
    """
    name       = _clean_id(tx.id)
    from_bus   = _clean_id(tx.from_bus_id)
    to_bus     = _clean_id(tx.to_bus_id)

    # Map vector group enum to OpenDSS connection strings
    conn_map = {
        TransformerConnection.DYN11: "[delta, wye]",
        TransformerConnection.YNyn0: "[wye, wye]",
        TransformerConnection.Dd0:   "[delta, delta]",
    }
    conns = conn_map[tx.vector_group]

    return (
        f"! Transformer: {tx.name} ({tx.vector_group.value})\n"
        f"New Transformer.{name} "
        f"phases={tx.phases.value} "
        f"windings=2 "
        f"buses=[{from_bus}, {to_bus}] "
        f"conns={conns} "
        f"kVs=[{tx.primary_kv}, {tx.secondary_kv}] "
        f"kVAs=[{tx.rating_kva}, {tx.rating_kva}] "
        f"%R={tx.percent_r} "
        f"XHL={tx.percent_x}"
    )


def _translate_overhead_line(line: OverheadLine, linecode_name: str = "ACSR150") -> str:
    """
    OpenDSS lines reference a LineCode for conductor properties.
    The LineCode is defined once at the top of the script (see translate_grid).
    Individual line sections just reference it by name and add length + buses.
    """
    name     = _clean_id(line.id)
    from_bus = _clean_id(line.from_bus_id)
    to_bus   = _clean_id(line.to_bus_id)

    return (
        f"! Overhead Line: {line.name}  ({line.length_km} km)\n"
        f"New Line.{name} "
        f"bus1={from_bus} "
        f"bus2={to_bus} "
        f"linecode={linecode_name} "
        f"length={line.length_km} "
        f"phases={line.phases.value} "
        f"units=km"
    )


def _translate_underground_cable(cable: UndergroundCable, linecode_name: str = "XLPE150CU") -> str:
    name     = _clean_id(cable.id)
    from_bus = _clean_id(cable.from_bus_id)
    to_bus   = _clean_id(cable.to_bus_id)

    return (
        f"! Underground Cable: {cable.name}  ({cable.length_km} km)\n"
        f"New Line.{name} "
        f"bus1={from_bus} "
        f"bus2={to_bus} "
        f"linecode={linecode_name} "
        f"length={cable.length_km} "
        f"phases={cable.phases.value} "
        f"units=km"
    )


def _translate_residential_load(load: ResidentialLoad) -> str:
    """
    Critical points:
      - phases=1        single-phase household
      - bus1=BUS.N      the .N suffix tells OpenDSS which phase (1=A, 2=B, 3=C)
      - kV=0.231        phase-to-neutral voltage, NOT line-to-line
      - Model=1         constant P and Q (steady-state power flow default)
    """
    name    = _clean_id(load.id)
    bus     = _clean_id(load.bus_id)
    phase_n = load.phase.value   # PhaseAssignment.A → 1, .B → 2, .C → 3

    return (
        f"! Residential Load: {load.name}  (Phase {load.phase.name})\n"
        f"New Load.{name} "
        f"phases=1 "
        f"bus1={bus}.{phase_n} "
        f"kV={load.base_kv} "
        f"kW={load.kw} "
        f"kVAR={load.kvar} "
        f"Model={load.load_model.value}"
    )


def _translate_industrial_load(load: IndustrialLoad) -> str:
    """
    Three-phase load — no phase suffix needed on the bus name.
    kV is line-to-line (0.4 kV), not phase-to-neutral.
    """
    name = _clean_id(load.id)
    bus  = _clean_id(load.bus_id)

    return (
        f"! Industrial Load: {load.name}\n"
        f"New Load.{name} "
        f"phases={load.phases.value} "
        f"bus1={bus} "
        f"kV={load.base_kv} "
        f"kW={load.kw} "
        f"kVAR={load.kvar} "
        f"Model={load.load_model.value}"
    )


def _translate_synchronous_generator(gen: SynchronousGenerator) -> str:
    """
    Model=1 → PV node (generator controls kW output and terminal voltage).
    The AVR holds terminal voltage at rated kV; the solver finds kVAR.
    kVARmax / kVARmin enforce the reactive capability limits.

    If is_slack=True, this generator also acts as the circuit reference.
    OpenDSS handles this automatically when it is the only voltage source.
    """
    name = _clean_id(gen.id)
    bus  = _clean_id(gen.bus_id)

    slack_comment = "  ! ← SLACK BUS (voltage/angle reference)" if gen.is_slack else ""

    return (
        f"! Synchronous Generator: {gen.name}{slack_comment}\n"
        f"New Generator.{name} "
        f"phases={gen.phases.value} "
        f"bus1={bus} "
        f"kV={gen.rated_kv} "
        f"kW={gen.rated_kw} "
        f"PF={gen.power_factor} "
        f"Model={gen.model.value} "
        f"maxkvar={gen.kvar_max} "
        f"minkvar={gen.kvar_min}"
    )


def _translate_solar_pv(pv: SolarPV) -> str:
    """
    MUST use 'PVSystem' object — not 'Generator'.
    PVSystem correctly models:
      - Inverter current limiting (cannot exceed kVA rating)
      - Irradiance-dependent output scaling (Pmpp × irradiance)
      - Temperature derating (via temp_coefficient, used in Phase 2 time-series)
      - Volt-VAR response (configurable in Phase 2)

    In Phase 1 (steady-state), irradiance is fixed at 1.0 kW/m² (STC).
    """
    name = _clean_id(pv.id)
    bus  = _clean_id(pv.bus_id)

    return (
        f"! Solar PV: {pv.name}\n"
        f"New PVSystem.{name} "
        f"phases={pv.phases.value} "
        f"bus1={bus} "
        f"kV={pv.rated_kv} "
        f"kVA={pv.kva_rated} "
        f"Pmpp={pv.kw_peak} "
        f"irradiance={pv.irradiance_kw_per_m2} "
        f"PF={pv.power_factor} "
        f"basefreq=50"
    )


# ─────────────────────────────────────────────────────────────────────────────
# LINECODE DEFINITIONS
# These define conductor electrical properties once at the top of the script.
# Line and Cable objects then reference them by name.
# ─────────────────────────────────────────────────────────────────────────────

def _overhead_linecode_block(lines: list[OverheadLine]) -> str:
    """
    If the grid contains any overhead lines, emit the ACSR150 LineCode.
    We derive the values from the first overhead line's stored parameters
    (all lines share the same conductor type in Phase 1).
    """
    if not lines:
        return ""
    l = lines[0]   # All Phase 1 overhead lines use the same conductor type
    return (
        f"! Conductor definition: ACSR 150mm² (IEC 61089 / EN 50182)\n"
        f"New LineCode.ACSR150 "
        f"nphases=3 "
        f"R1={l.r1_ohm_per_km} "
        f"X1={l.x1_ohm_per_km} "
        f"R0={l.r0_ohm_per_km} "
        f"X0={l.x0_ohm_per_km} "
        f"units=km "
        f"basefreq=50"
    )


def _underground_linecode_block(cables: list[UndergroundCable]) -> str:
    """
    If the grid contains any underground cables, emit the XLPE150CU LineCode.
    C1 (shunt capacitance) is included — important for longer cable runs.
    """
    if not cables:
        return ""
    c = cables[0]
    return (
        f"! Conductor definition: 12/20kV XLPE 150mm² Cu (IEC 60502-2)\n"
        f"New LineCode.XLPE150CU "
        f"nphases=3 "
        f"R1={c.r1_ohm_per_km} "
        f"X1={c.x1_ohm_per_km} "
        f"R0={c.r0_ohm_per_km} "
        f"X0={c.x0_ohm_per_km} "
        f"C1={c.c1_uf_per_km} "
        f"units=km "
        f"basefreq=50"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TRANSLATOR — public API
# This is the only function the rest of your backend needs to call.
# ─────────────────────────────────────────────────────────────────────────────

def translate_grid(grid: Grid) -> str:
    """
    Convert a validated Grid object into a complete, executable DSS script.

    Usage:
        from backend.translators.dss_translator import translate_grid
        dss_script = translate_grid(my_grid)

    Returns:
        A multi-line string of DSS commands ready to pass to OpenDSS.
    """

    # Collect all voltage levels present in the grid so we can set VoltageBases
    voltage_bases: list[float] = []
    for bus in grid.mv_buses:
        if bus.base_kv not in voltage_bases:
            voltage_bases.append(bus.base_kv)
    for bus in grid.lv_buses:
        if bus.base_kv not in voltage_bases:
            voltage_bases.append(bus.base_kv)
    voltage_bases_str = ", ".join(str(v) for v in sorted(voltage_bases, reverse=True))

    # Determine the source bus (first MV bus, or first LV bus if no MV exists)
    source_bus = (
        _clean_id(grid.mv_buses[0].id) if grid.mv_buses
        else _clean_id(grid.lv_buses[0].id)
    )
    source_kv = (
        grid.mv_buses[0].base_kv if grid.mv_buses
        else grid.lv_buses[0].base_kv
    )

    # ── Assemble the script section by section ────────────────────────────────
    sections: list[str] = []

    # 1. Header
    sections.append(
        f"! ═══════════════════════════════════════════════════════════════\n"
        f"! Grid Simulator — Auto-generated DSS Script\n"
        f"! Grid: {grid.name}\n"
        f"! ═══════════════════════════════════════════════════════════════\n"
        f"\n"
        f"Clear\n"
        f"\n"
        f"! Circuit definition — sets the slack/reference bus\n"
        f"New Circuit.{_clean_id(grid.id)} "
        f"basekv={source_kv} "
        f"pu=1.0 "
        f"phases=3 "
        f"bus1={source_bus} "
        f"basefreq=50"
    )

    # 2. Conductor definitions (must come before any Line objects)
    linecode_block = "\n".join(filter(None, [
        _overhead_linecode_block(grid.overhead_lines),
        _underground_linecode_block(grid.underground_cables),
    ]))
    if linecode_block:
        sections.append(f"\n! ── Conductor Definitions ──────────────────────────────────────\n{linecode_block}")

    # 3. Buses
    bus_lines = [_translate_mv_bus(b) for b in grid.mv_buses] + \
                [_translate_lv_bus(b) for b in grid.lv_buses]
    if bus_lines:
        sections.append(
            "\n! ── Buses ──────────────────────────────────────────────────────\n" +
            "\n".join(bus_lines)
        )

    # 4. Transformers
    if grid.transformers:
        sections.append(
            "\n! ── Transformers ───────────────────────────────────────────────\n" +
            "\n".join(_translate_transformer(t) for t in grid.transformers)
        )

    # 5. Lines
    if grid.overhead_lines:
        sections.append(
            "\n! ── Overhead Lines ─────────────────────────────────────────────\n" +
            "\n".join(_translate_overhead_line(l) for l in grid.overhead_lines)
        )

    # 6. Cables
    if grid.underground_cables:
        sections.append(
            "\n! ── Underground Cables ─────────────────────────────────────────\n" +
            "\n".join(_translate_underground_cable(c) for c in grid.underground_cables)
        )

    # 7. Loads
    load_lines = (
        [_translate_residential_load(l) for l in grid.residential_loads] +
        [_translate_industrial_load(l)  for l in grid.industrial_loads]
    )
    if load_lines:
        sections.append(
            "\n! ── Loads ──────────────────────────────────────────────────────\n" +
            "\n".join(load_lines)
        )

    # 8. Generation
    gen_lines = (
        [_translate_synchronous_generator(g) for g in grid.synchronous_generators] +
        [_translate_solar_pv(p)              for p in grid.solar_pv_systems]
    )
    if gen_lines:
        sections.append(
            "\n! ── Generation ─────────────────────────────────────────────────\n" +
            "\n".join(gen_lines)
        )

    # 9. Solve commands (always last)
    # Mode=0 (snapshot) = single steady-state AC power flow — correct for Phase 1
    # CalcVoltageBases MUST run before Solve so OpenDSS knows the per-unit base
    # at every bus. Without it, pu values are meaningless.
    sections.append(
        f"\n! ── Solve ──────────────────────────────────────────────────────\n"
        f"Set VoltageBases=[{voltage_bases_str}]\n"
        f"CalcVoltageBases\n"
        f"Set Mode=0\n"
        f"Solve"
    )

    return "\n".join(sections)
