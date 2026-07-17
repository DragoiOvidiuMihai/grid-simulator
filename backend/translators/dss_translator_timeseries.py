"""
Time-Series DSS Translator
===========================
Extends the Phase 1 snapshot translator with a daily simulation mode.

Key differences from snapshot (translate_grid):
  - Defines LoadShape objects for each load type (48 half-hour points)
  - Defines a TShape object for PVSystem irradiance
  - Sets simulation mode to daily (Mode=1) with 48 steps of 0.5hr each
  - Collects results at each time step via the solver

OpenDSS daily simulation flow:
  1. Define LoadShapes (normalised 0-1 multiplier curves)
  2. Assign each Load object a daily= property pointing to its LoadShape
  3. Define TShape for irradiance (in kW/m²)
  4. Assign each PVSystem object a daily= property pointing to the TShape
  5. Set Mode=1 (daily), StepSize=0.5h, Number=48
  6. Solve — OpenDSS iterates through all 48 steps automatically
"""

from backend.models.models import (
    Grid,
    TwoWindingTransformer,
    OverheadLine,
    UndergroundCable,
    ResidentialLoad,
    IndustrialLoad,
    SynchronousGenerator,
    SolarPV,
    TransformerConnection,
)
from backend.solver.profiles import ScaledProfiles


def _clean_id(raw_id: str) -> str:
    return raw_id.replace(" ", "_").upper()


def _format_dss_array(values: list[float], precision: int = 4) -> str:
    """
    Format a Python list as an OpenDSS array string.
    Example: [0.3, 0.5, 1.0] → '(0.3000, 0.5000, 1.0000)'
    """
    formatted = ", ".join(f"{v:.{precision}f}" for v in values)
    return f"({formatted})"


def translate_grid_timeseries(grid: Grid, profiles: ScaledProfiles) -> str:
    """
    Convert a validated Grid object into a complete DSS script for
    daily (24-hour) time-series simulation.

    Parameters
    ----------
    grid : Grid
        Validated grid object from models.py
    profiles : ScaledProfiles
        Scaled 48-point profiles from profiles.get_scaled_profiles()

    Returns
    -------
    str
        Complete multi-line DSS script for daily simulation mode.
        Feed line-by-line to OpenDSS via dss.Text.Command()
    """

    # Collect voltage bases
    voltage_bases: list[float] = []
    for bus in grid.mv_buses:
        if bus.base_kv not in voltage_bases:
            voltage_bases.append(bus.base_kv)
    for bus in grid.lv_buses:
        if bus.base_kv not in voltage_bases:
            voltage_bases.append(bus.base_kv)
    voltage_bases_str = ", ".join(str(v) for v in sorted(voltage_bases, reverse=True))

    source_bus = (
        _clean_id(grid.mv_buses[0].id) if grid.mv_buses
        else _clean_id(grid.lv_buses[0].id)
    )
    source_kv = (
        grid.mv_buses[0].base_kv if grid.mv_buses
        else grid.lv_buses[0].base_kv
    )

    sections: list[str] = []

    # ── 1. Header ─────────────────────────────────────────────────────────────
    sections.append(
        f"! ═══════════════════════════════════════════════════════════════\n"
        f"! Grid Simulator — Time-Series DSS Script\n"
        f"! Grid: {grid.name} | Season: {profiles.season} | "
        f"Load multiplier: {profiles.peak_load_multiplier}x\n"
        f"! Location: Bucharest, Romania (44.4°N) | Resolution: 30 min × 48 steps\n"
        f"! ═══════════════════════════════════════════════════════════════\n"
        f"\n"
        f"Clear\n"
        f"\n"
        f"New Circuit.{_clean_id(grid.id)} "
        f"basekv={source_kv} pu=1.0 phases=3 bus1={source_bus} basefreq=50"
    )

    # ── 2. LoadShape definitions ──────────────────────────────────────────────
    # OpenDSS LoadShape objects define how load varies over time.
    # npts=48, sinterval=1800 (seconds) → 48 × 30min = 24 hours
    # mult= array is the per-unit multiplier at each time step.
    # The actual kW at each step = Load.kW × LoadShape.mult[step]
    #
    # We normalise the profiles back to 0-1 range for OpenDSS,
    # since the Load object already carries the peak kW value.

    res_profile   = profiles.residential_kw
    ind_profile   = profiles.industrial_kw
    peak_res      = max(res_profile) if max(res_profile) > 0 else 1.0
    peak_ind      = max(ind_profile) if max(ind_profile) > 0 else 1.0

    res_normalised = [v / peak_res for v in res_profile]
    ind_normalised = [v / peak_ind for v in ind_profile]

    sections.append(
        f"\n! ── LoadShape Definitions ──────────────────────────────────────\n"
        f"! Residential load shape — Romanian daily profile\n"
        f"New LoadShape.ResShape "
        f"npts=48 sinterval=1800 "
        f"mult={_format_dss_array(res_normalised)}\n"
        f"\n"
        f"! Industrial load shape — Romanian daily profile\n"
        f"New LoadShape.IndShape "
        f"npts=48 sinterval=1800 "
        f"mult={_format_dss_array(ind_normalised)}"
    )

    # ── 3. LoadShape definition (irradiance for PVSystem) ────────────────────────
    # LoadShape is the OpenDSS object for temperature/irradiance time-series.
    # For PVSystem, the 'daily' property references a LoadShape with irradiance
    # values in kW/m². OpenDSS scales PV output by irradiance/1.0 (STC).
    irr_profile = profiles.irradiance_kw_m2

    if any(v > 0 for v in irr_profile) and grid.solar_pv_systems:
        sections.append(
            f"\n! ── Irradiance LoadShape ───────────────────────────────────────\n"
            f"! Solar irradiance profile — {profiles.season.capitalize()}, "
            f"Bucharest Romania (44.4°N)\n"
            f"New LoadShape.SolarShape "
            f"npts=48 sinterval=1800 "
            f"mult={_format_dss_array(irr_profile, precision=4)}"
        )

    # ── 4. Buses ──────────────────────────────────────────────────────────────
    bus_lines = (
        [f"! MV Bus: {b.name} ({b.base_kv} kV)" for b in grid.mv_buses] +
        [f"! LV Bus: {b.name} ({b.base_kv} kV)" for b in grid.lv_buses]
    )
    if bus_lines:
        sections.append(
            "\n! ── Buses ──────────────────────────────────────────────────────\n" +
            "\n".join(bus_lines)
        )

    # ── 5. Conductor definitions ──────────────────────────────────────────────
    if grid.overhead_lines:
        l = grid.overhead_lines[0]
        sections.append(
            f"\n! ── Conductor Definitions ──────────────────────────────────────\n"
            f"New LineCode.ACSR150 nphases=3 "
            f"R1={l.r1_ohm_per_km} X1={l.x1_ohm_per_km} "
            f"R0={l.r0_ohm_per_km} X0={l.x0_ohm_per_km} "
            f"units=km basefreq=50"
        )

    if grid.underground_cables:
        c = grid.underground_cables[0]
        sections.append(
            f"New LineCode.XLPE150CU nphases=3 "
            f"R1={c.r1_ohm_per_km} X1={c.x1_ohm_per_km} "
            f"R0={c.r0_ohm_per_km} X0={c.x0_ohm_per_km} "
            f"C1={c.c1_uf_per_km} units=km basefreq=50"
        )

    # ── 6. Transformers ───────────────────────────────────────────────────────
    if grid.transformers:
        conn_map = {
            TransformerConnection.DYN11: "[delta, wye]",
            TransformerConnection.YNyn0: "[wye, wye]",
            TransformerConnection.Dd0:   "[delta, delta]",
        }
        tx_lines = []
        for t in grid.transformers:
            name     = _clean_id(t.id)
            from_bus = _clean_id(t.from_bus_id)
            to_bus   = _clean_id(t.to_bus_id)
            tx_lines.append(
                f"! Transformer: {t.name}\n"
                f"New Transformer.{name} phases={t.phases.value} windings=2 "
                f"buses=[{from_bus},{to_bus}] conns={conn_map[t.vector_group]} "
                f"kVs=[{t.primary_kv},{t.secondary_kv}] "
                f"kVAs=[{t.rating_kva},{t.rating_kva}] "
                f"%R={t.percent_r} XHL={t.percent_x}"
            )
        sections.append(
            "\n! ── Transformers ───────────────────────────────────────────────\n" +
            "\n".join(tx_lines)
        )

    # ── 7. Lines ──────────────────────────────────────────────────────────────
    if grid.overhead_lines:
        line_strs = []
        for l in grid.overhead_lines:
            name     = _clean_id(l.id)
            from_bus = _clean_id(l.from_bus_id)
            to_bus   = _clean_id(l.to_bus_id)
            line_strs.append(
                f"New Line.{name} bus1={from_bus} bus2={to_bus} "
                f"linecode=ACSR150 length={l.length_km} phases={l.phases.value} units=km"
            )
        sections.append(
            "\n! ── Overhead Lines ─────────────────────────────────────────────\n" +
            "\n".join(line_strs)
        )

    if grid.underground_cables:
        cable_strs = []
        for c in grid.underground_cables:
            name     = _clean_id(c.id)
            from_bus = _clean_id(c.from_bus_id)
            to_bus   = _clean_id(c.to_bus_id)
            cable_strs.append(
                f"New Line.{name} bus1={from_bus} bus2={to_bus} "
                f"linecode=XLPE150CU length={c.length_km} phases={c.phases.value} units=km"
            )
        sections.append(
            "\n! ── Underground Cables ─────────────────────────────────────────\n" +
            "\n".join(cable_strs)
        )

    # ── 8. Loads — with daily LoadShape references ────────────────────────────
    # The key difference from snapshot mode:
    # Each load gets a 'daily=ShapeName' property which tells OpenDSS
    # to use the LoadShape multiplier at each time step.
    load_lines = []

    for l in grid.residential_loads:
        name    = _clean_id(l.id)
        bus     = _clean_id(l.bus_id)
        # Scale peak kW by multiplier for this load
        peak_kw = l.kw * profiles.peak_load_multiplier
        peak_kvar = l.kvar * profiles.peak_load_multiplier
        load_lines.append(
            f"! Residential Load: {l.name}\n"
            f"New Load.{name} phases=1 bus1={bus}.{l.phase.value} "
            f"kV={l.base_kv} kW={peak_kw} kVAR={peak_kvar} "
            f"Model={l.load_model.value} daily=ResShape"
        )

    for l in grid.industrial_loads:
        name    = _clean_id(l.id)
        bus     = _clean_id(l.bus_id)
        peak_kw   = l.kw   * profiles.peak_load_multiplier
        peak_kvar = l.kvar * profiles.peak_load_multiplier
        load_lines.append(
            f"! Industrial Load: {l.name}\n"
            f"New Load.{name} phases={l.phases.value} bus1={bus} "
            f"kV={l.base_kv} kW={peak_kw} kVAR={peak_kvar} "
            f"Model={l.load_model.value} daily=IndShape"
        )

    if load_lines:
        sections.append(
            "\n! ── Loads (with daily LoadShape) ───────────────────────────────\n" +
            "\n".join(load_lines)
        )

    # ── 9. Generation — with daily TShape references ──────────────────────────
    gen_lines = []

    for g in grid.synchronous_generators:
        name = _clean_id(g.id)
        bus  = _clean_id(g.bus_id)
        slack = "  ! ← SLACK BUS" if g.is_slack else ""
        gen_lines.append(
            f"! Synchronous Generator: {g.name}{slack}\n"
            f"New Generator.{name} phases={g.phases.value} bus1={bus} "
            f"kV={g.rated_kv} kW={g.rated_kw} PF={g.power_factor} "
            f"Model={g.model.value} maxkvar={g.kvar_max} minkvar={g.kvar_min}"
        )

    for p in grid.solar_pv_systems:
        name = _clean_id(p.id)
        bus  = _clean_id(p.bus_id)
        gen_lines.append(
            f"! Solar PV: {p.name}\n"
            f"New PVSystem.{name} phases={p.phases.value} bus1={bus} "
            f"kV={p.rated_kv} kVA={p.kva_rated} Pmpp={p.kw_peak} "
            f"irradiance=1.0 PF={p.power_factor} basefreq=50 "
            f"daily=SolarShape"
        )

    if gen_lines:
        sections.append(
            "\n! ── Generation ─────────────────────────────────────────────────\n" +
            "\n".join(gen_lines)
        )

    # ── 10. Solve — daily mode ────────────────────────────────────────────────
    # Mode=1   = daily simulation
    # StepSize = 0.5h (30 minutes) — matches our 48-point profiles
    # Number   = 48   — run all 48 half-hour intervals
    sections.append(
        f"\n! ── Solve (Daily Mode) ─────────────────────────────────────────\n"
        f"Set VoltageBases=[{voltage_bases_str}]\n"
        f"CalcVoltageBases\n"
        f"Set Mode=1\n"
        f"Set StepSize=0.5h\n"
        f"Set Number=48\n"
        f"Solve"
    )

    return "\n".join(sections)
