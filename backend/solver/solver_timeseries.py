"""
Time-Series Solver
==================
Runs a 48-step daily simulation via OpenDSS and collects structured
results at each time step.

Approach: manual multiplier injection per step (snapshot mode × 48)
This is more reliable than OpenDSS LoadShape in daily mode, which
requires specific circuit configurations to propagate multipliers.
At each step we:
  1. Update Load.kW and Load.kVAR directly from the profile
  2. Update PVSystem.irradiance from the irradiance profile
  3. Run a snapshot solve (Mode=0)
  4. Collect bus voltages, losses, and generation output
"""

from __future__ import annotations
from dataclasses import dataclass, field
import opendssdirect as dss
from backend.solver.profiles import ScaledProfiles, RESIDENTIAL_LOAD_PROFILE, INDUSTRIAL_LOAD_PROFILE


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TimeStepVoltage:
    bus_id:        str
    per_unit:      float
    voltage_kv:    float
    within_limits: bool
    deviation_pct: float


@dataclass
class TimeStepResult:
    step:          int
    time_label:    str
    converged:     bool
    bus_voltages:  list[TimeStepVoltage] = field(default_factory=list)
    total_loss_kw: float = 0.0
    pv_output_kw:  float = 0.0
    gen_output_kw: float = 0.0


@dataclass
class VoltageSummary:
    bus_id:     str
    min_pu:     float
    max_pu:     float
    min_time:   str
    max_time:   str
    violations: int


@dataclass
class TimeSeriesResult:
    converged_steps:      int
    total_steps:          int
    season:               str
    peak_load_multiplier: float
    timesteps:            list[TimeStepResult]  = field(default_factory=list)
    voltage_summaries:    list[VoltageSummary]  = field(default_factory=list)
    total_energy_loss_kwh:  float = 0.0
    total_pv_energy_kwh:    float = 0.0
    total_gen_energy_kwh:   float = 0.0
    peak_loss_kw:           float = 0.0
    peak_loss_time:         str   = ""
    warnings:               list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "converged_steps":       self.converged_steps,
            "total_steps":           self.total_steps,
            "season":                self.season,
            "peak_load_multiplier":  self.peak_load_multiplier,
            "total_energy_loss_kwh": round(self.total_energy_loss_kwh, 3),
            "total_pv_energy_kwh":   round(self.total_pv_energy_kwh,   3),
            "total_gen_energy_kwh":  round(self.total_gen_energy_kwh,  3),
            "peak_loss_kw":          round(self.peak_loss_kw,          3),
            "peak_loss_time":        self.peak_loss_time,
            "warnings":              self.warnings,
            "voltage_summaries": [
                {
                    "bus_id":     s.bus_id,
                    "min_pu":     round(s.min_pu,  4),
                    "max_pu":     round(s.max_pu,  4),
                    "min_time":   s.min_time,
                    "max_time":   s.max_time,
                    "violations": s.violations,
                }
                for s in self.voltage_summaries
            ],
            "timesteps": [
                {
                    "step":          ts.step,
                    "time_label":    ts.time_label,
                    "converged":     ts.converged,
                    "total_loss_kw": round(ts.total_loss_kw, 4),
                    "pv_output_kw":  round(ts.pv_output_kw,  3),
                    "gen_output_kw": round(ts.gen_output_kw, 3),
                    "bus_voltages": [
                        {
                            "bus_id":        v.bus_id,
                            "per_unit":      round(v.per_unit,      4),
                            "voltage_kv":    round(v.voltage_kv,    4),
                            "within_limits": v.within_limits,
                            "deviation_pct": round(v.deviation_pct, 2),
                        }
                        for v in ts.bus_voltages
                    ],
                }
                for ts in self.timesteps
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

EN50160_LIMIT_PU = 0.10
STEP_DURATION_H  = 0.5

TIME_LABELS = [
    f"{i // 2:02d}:{'30' if i % 2 else '00'}"
    for i in range(48)
]


def _voltage_within_limits(pu: float) -> bool:
    return (1.0 - EN50160_LIMIT_PU) <= pu <= (1.0 + EN50160_LIMIT_PU)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TIME-SERIES SOLVER
# ─────────────────────────────────────────────────────────────────────────────

def run_timeseries(
    dss_script:           str,
    profiles:             ScaledProfiles,
    season:               str   = "summer",
    peak_load_multiplier: float = 1.0,
) -> TimeSeriesResult:
    """
    Run a 48-step daily power flow simulation and return structured results.

    Strategy: load the network once in snapshot mode, then for each of the
    48 half-hour steps, update component values from the profile arrays and
    run a fresh snapshot solve. This is more reliable than OpenDSS daily
    mode LoadShape application.
    """

    warnings:         list[str]         = []
    timestep_results: list[TimeStepResult] = []

    # ── Step 1: Load the base network ─────────────────────────────────────────
    try:
        dss.Text.Command("Clear")
        for line in dss_script.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("!"):
                continue
            dss.Text.Command(stripped)
            result_str = dss.Text.Result()
            if result_str and "error" in result_str.lower():
                return TimeSeriesResult(
                    converged_steps=0, total_steps=48,
                    season=season, peak_load_multiplier=peak_load_multiplier,
                    warnings=[f"DSS command failed: '{stripped}' -> {result_str}"]
                )
    except Exception as e:
        return TimeSeriesResult(
            converged_steps=0, total_steps=48,
            season=season, peak_load_multiplier=peak_load_multiplier,
            warnings=[f"DSS script load failed: {str(e)}"]
        )

    # ── Step 2: Collect component names for per-step updates ─────────────────
    # Gather load names and their peak values
    residential_loads: list[tuple[str, float, float]] = []  # (name, peak_kw, peak_kvar)
    industrial_loads:  list[tuple[str, float, float]] = []
    pv_systems:        list[str] = []
    generators:        list[str] = []

    load_idx = dss.Loads.First()
    while load_idx > 0:
        name = dss.Loads.Name()
        kw   = dss.Loads.kW()
        kvar = dss.Loads.kvar()
        # Determine type by name prefix (set by translator)
        if "residential" in name.lower() or name.startswith("load_res"):
            residential_loads.append((name, kw, kvar))
        else:
            industrial_loads.append((name, kw, kvar))
        load_idx = dss.Loads.Next()

    pv_idx = dss.PVsystems.First()
    while pv_idx > 0:
        pv_systems.append(dss.PVsystems.Name())
        pv_idx = dss.PVsystems.Next()

    gen_idx = dss.Generators.First()
    while gen_idx > 0:
        generators.append(dss.Generators.Name())
        gen_idx = dss.Generators.Next()

    bus_names = [
        b for b in dss.Circuit.AllBusNames()
        if b.lower() not in ("sourcebus", "source")
    ]

    # ── Step 3: Run 48 snapshot solves ───────────────────────────────────────
    irr_profile = profiles.irradiance_kw_m2
    res_profile  = RESIDENTIAL_LOAD_PROFILE
    ind_profile  = INDUSTRIAL_LOAD_PROFILE

    for step in range(48):
        time_label  = TIME_LABELS[step]
        res_mult    = res_profile[step]
        ind_mult    = ind_profile[step]
        irr_value   = irr_profile[step]

        try:
            # Update residential loads
            for name, peak_kw, peak_kvar in residential_loads:
                new_kw   = peak_kw   * res_mult
                new_kvar = peak_kvar * res_mult
                dss.Text.Command(f"Load.{name}.kW={new_kw:.4f}")
                dss.Text.Command(f"Load.{name}.kVAR={new_kvar:.4f}")

            # Update industrial loads
            for name, peak_kw, peak_kvar in industrial_loads:
                new_kw   = peak_kw   * ind_mult
                new_kvar = peak_kvar * ind_mult
                dss.Text.Command(f"Load.{name}.kW={new_kw:.4f}")
                dss.Text.Command(f"Load.{name}.kVAR={new_kvar:.4f}")

            # Update PV irradiance
            for name in pv_systems:
                dss.Text.Command(f"PVSystem.{name}.irradiance={irr_value:.4f}")

            # Solve snapshot
            dss.Text.Command("Set Mode=0")
            dss.Text.Command("Solve")
            converged = dss.Solution.Converged()

        except Exception as e:
            warnings.append(f"Step {step} ({time_label}): update error — {str(e)}")
            timestep_results.append(TimeStepResult(
                step=step, time_label=time_label, converged=False
            ))
            continue

        if not converged:
            warnings.append(f"Step {step} ({time_label}): did not converge.")
            timestep_results.append(TimeStepResult(
                step=step, time_label=time_label, converged=False
            ))
            continue

        # Read bus voltages
        step_voltages: list[TimeStepVoltage] = []
        for bus_name in bus_names:
            dss.Circuit.SetActiveBus(bus_name)
            nominal_kv = dss.Bus.kVBase()
            pu_vm_ang  = dss.Bus.puVmagAngle()
            if not pu_vm_ang or len(pu_vm_ang) < 2:
                continue
            pu_magnitudes = [pu_vm_ang[i] for i in range(0, len(pu_vm_ang), 2)]
            pu            = sum(pu_magnitudes) / len(pu_magnitudes)
            voltage_kv    = pu * nominal_kv
            within_limits = _voltage_within_limits(pu)
            deviation_pct = (pu - 1.0) * 100.0
            step_voltages.append(TimeStepVoltage(
                bus_id        = bus_name,
                per_unit      = pu,
                voltage_kv    = voltage_kv,
                within_limits = within_limits,
                deviation_pct = deviation_pct,
            ))

        # Read total losses
        total_losses  = dss.Circuit.Losses()
        total_loss_kw = total_losses[0] / 1000.0 if total_losses else 0.0

        # Read PV output — terminal 1 only, values already in kW
        pv_output_kw = 0.0
        for name in pv_systems:
            dss.Circuit.SetActiveElement(f"PVSystem.{name}")
            powers = dss.CktElement.Powers()
            if powers and len(powers) >= 6:
                terminal1     = powers[:6]
                pv_output_kw += -sum(terminal1[i] for i in range(0, 6, 2))

        # Read generator output — terminal 1 only, values in W → kW
        gen_output_kw = 0.0
        for name in generators:
            dss.Circuit.SetActiveElement(f"Generator.{name}")
            powers = dss.CktElement.Powers()
            if powers and len(powers) >= 6:
                terminal1      = powers[:6]
                gen_output_kw += -sum(terminal1[i] for i in range(0, 6, 2)) / 1000.0

        timestep_results.append(TimeStepResult(
            step          = step,
            time_label    = time_label,
            converged     = True,
            bus_voltages  = step_voltages,
            total_loss_kw = total_loss_kw,
            pv_output_kw  = pv_output_kw,
            gen_output_kw = gen_output_kw,
        ))

    # ── Step 4: Compute summary statistics ───────────────────────────────────
    converged_steps = sum(1 for ts in timestep_results if ts.converged)

    voltage_summaries: list[VoltageSummary] = []
    for bus_name in bus_names:
        bus_steps = [
            (ts.time_label, v)
            for ts in timestep_results if ts.converged
            for v in ts.bus_voltages if v.bus_id == bus_name
        ]
        if not bus_steps:
            continue
        pu_values  = [v.per_unit for _, v in bus_steps]
        min_pu     = min(pu_values)
        max_pu     = max(pu_values)
        min_time   = bus_steps[pu_values.index(min_pu)][0]
        max_time   = bus_steps[pu_values.index(max_pu)][0]
        violations = sum(1 for _, v in bus_steps if not v.within_limits)

        if violations > 0:
            warnings.append(
                f"Bus '{bus_name}': {violations}/48 steps outside EN 50160 limits. "
                f"Min: {min_pu:.4f} pu at {min_time}, Max: {max_pu:.4f} pu at {max_time}."
            )

        voltage_summaries.append(VoltageSummary(
            bus_id     = bus_name,
            min_pu     = min_pu,
            max_pu     = max_pu,
            min_time   = min_time,
            max_time   = max_time,
            violations = violations,
        ))

    total_energy_loss_kwh = sum(
        ts.total_loss_kw * STEP_DURATION_H
        for ts in timestep_results if ts.converged
    )
    total_pv_energy_kwh = sum(
        ts.pv_output_kw * STEP_DURATION_H
        for ts in timestep_results if ts.converged
    )
    total_gen_energy_kwh = sum(
        ts.gen_output_kw * STEP_DURATION_H
        for ts in timestep_results if ts.converged
    )

    loss_steps = [(ts.time_label, ts.total_loss_kw) for ts in timestep_results if ts.converged]
    if loss_steps:
        peak_loss_time, peak_loss_kw = max(loss_steps, key=lambda x: x[1])
    else:
        peak_loss_kw   = 0.0
        peak_loss_time = ""

    return TimeSeriesResult(
        converged_steps       = converged_steps,
        total_steps           = 48,
        season                = season,
        peak_load_multiplier  = peak_load_multiplier,
        timesteps             = timestep_results,
        voltage_summaries     = voltage_summaries,
        total_energy_loss_kwh = total_energy_loss_kwh,
        total_pv_energy_kwh   = total_pv_energy_kwh,
        total_gen_energy_kwh  = total_gen_energy_kwh,
        peak_loss_kw          = peak_loss_kw,
        peak_loss_time        = peak_loss_time,
        warnings              = warnings,
    )
