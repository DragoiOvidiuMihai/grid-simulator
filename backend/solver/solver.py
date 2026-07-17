"""
OpenDSS Solver Wrapper
======================
Feeds a DSS script into OpenDSS via opendssdirect and returns
structured simulation results.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import opendssdirect as dss

@dataclass
class BusVoltageResult:
    bus_id:         str
    per_unit:       float
    voltage_kv:     float
    nominal_kv:     float
    within_limits:  bool
    deviation_pct:  float


@dataclass
class LineCurrentResult:
    line_id:        str
    current_a:      float
    ampacity_a:     float
    loading_pct:    float
    overloaded:     bool


@dataclass
class PowerLossResult:
    element_id:         str
    element_type:       str
    active_loss_kw:     float
    reactive_loss_kvar: float


@dataclass
class GeneratorOutputResult:
    generator_id:   str
    kw_output:      float
    kvar_output:    float


@dataclass
class SimulationResult:
    converged:          bool
    iterations:         int
    total_loss_kw:      float
    total_loss_kvar:    float
    bus_voltages:       list[BusVoltageResult]      = field(default_factory=list)
    line_currents:      list[LineCurrentResult]     = field(default_factory=list)
    power_losses:       list[PowerLossResult]       = field(default_factory=list)
    generator_outputs:  list[GeneratorOutputResult] = field(default_factory=list)
    warnings:           list[str]                   = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "converged":        self.converged,
            "iterations":       self.iterations,
            "total_loss_kw":    round(self.total_loss_kw,   3),
            "total_loss_kvar":  round(self.total_loss_kvar, 3),
            "warnings":         self.warnings,
            "bus_voltages": [
                {
                    "bus_id":        r.bus_id,
                    "per_unit":      round(r.per_unit,      4),
                    "voltage_kv":    round(r.voltage_kv,    4),
                    "nominal_kv":    r.nominal_kv,
                    "within_limits": r.within_limits,
                    "deviation_pct": round(r.deviation_pct, 2),
                }
                for r in self.bus_voltages
            ],
            "line_currents": [
                {
                    "line_id":      r.line_id,
                    "current_a":    round(r.current_a,   2),
                    "ampacity_a":   r.ampacity_a,
                    "loading_pct":  round(r.loading_pct, 1),
                    "overloaded":   r.overloaded,
                }
                for r in self.line_currents
            ],
            "power_losses": [
                {
                    "element_id":         r.element_id,
                    "element_type":       r.element_type,
                    "active_loss_kw":     round(r.active_loss_kw,     3),
                    "reactive_loss_kvar": round(r.reactive_loss_kvar, 3),
                }
                for r in self.power_losses
            ],
            "generator_outputs": [
                {
                    "generator_id": r.generator_id,
                    "kw_output":    round(r.kw_output,   3),
                    "kvar_output":  round(r.kvar_output, 3),
                }
                for r in self.generator_outputs
            ],
        }


EN50160_LIMIT_PU = 0.10


def _voltage_within_limits(pu: float) -> bool:
    return (1.0 - EN50160_LIMIT_PU) <= pu <= (1.0 + EN50160_LIMIT_PU)


AMPACITY_LOOKUP: dict[str, float] = {
    "ACSR150":   415.0,
    "XLPE150CU": 360.0,
}


def _get_ampacity(line_name: str) -> float:
    line_name_upper = line_name.upper()
    for code, ampacity in AMPACITY_LOOKUP.items():
        if code in line_name_upper:
            return ampacity
    return 200.0


def run_power_flow(dss_script: str) -> SimulationResult:
    """Execute a power flow simulation and return structured results."""

    warnings: list[str] = []

    # ── Step 1: Run the DSS script line by line ───────────────────────────────
    try:
        dss.Text.Command("Clear")
        for line in dss_script.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("!"):
                continue
            dss.Text.Command(stripped)
            result_str = dss.Text.Result()
            if result_str and "error" in result_str.lower():
                return SimulationResult(
                    converged=False,
                    iterations=0,
                    total_loss_kw=0.0,
                    total_loss_kvar=0.0,
                    warnings=[f"DSS command failed: '{stripped}' -> {result_str}"]
                )
    except Exception as e:
        return SimulationResult(
            converged=False,
            iterations=0,
            total_loss_kw=0.0,
            total_loss_kvar=0.0,
            warnings=[f"DSS script execution failed: {str(e)}"]
        )

    # ── Step 2: Check convergence ─────────────────────────────────────────────
    converged  = dss.Solution.Converged()
    iterations = dss.Solution.Iterations()

    if not converged:
        warnings.append(
            f"Power flow did not converge after {iterations} iterations. "
            "Check for: isolated buses, missing slack bus, or extreme loading conditions."
        )
        return SimulationResult(
            converged=False,
            iterations=iterations,
            total_loss_kw=0.0,
            total_loss_kvar=0.0,
            warnings=warnings
        )

    # ── Step 3: Read bus voltages ─────────────────────────────────────────────
    bus_voltage_results: list[BusVoltageResult] = []

    for bus_name in dss.Circuit.AllBusNames():
        if bus_name.lower() in ("sourcebus", "source"):
            continue

        dss.Circuit.SetActiveBus(bus_name)
        nominal_kv_ln = dss.Bus.kVBase()
        pu_vm_ang     = dss.Bus.puVmagAngle()

        if not pu_vm_ang or len(pu_vm_ang) < 2:
            vm_ang = dss.Bus.VMagAngle()
            if not vm_ang or len(vm_ang) < 2:
                warnings.append(f"No voltage data for bus '{bus_name}' — skipping.")
                continue
            magnitudes_v   = [vm_ang[i] for i in range(0, len(vm_ang), 2)]
            avg_voltage_kv = sum(magnitudes_v) / len(magnitudes_v) / 1000.0
            pu             = avg_voltage_kv / nominal_kv_ln if nominal_kv_ln > 0 else 0.0
        else:
            pu_magnitudes  = [pu_vm_ang[i] for i in range(0, len(pu_vm_ang), 2)]
            pu             = sum(pu_magnitudes) / len(pu_magnitudes)
            avg_voltage_kv = pu * nominal_kv_ln

        if nominal_kv_ln == 0:
            pu = 0.0
            warnings.append(f"Bus '{bus_name}' has zero base kV.")

        deviation_pct = (pu - 1.0) * 100.0
        within_limits = _voltage_within_limits(pu)

        if not within_limits:
            warnings.append(
                f"Bus '{bus_name}' voltage {pu:.4f} pu is outside EN 50160 limits "
                f"(0.90-1.10 pu). Deviation: {deviation_pct:+.1f}%"
            )

        bus_voltage_results.append(BusVoltageResult(
            bus_id        = bus_name,
            per_unit      = pu,
            voltage_kv    = avg_voltage_kv,
            nominal_kv    = nominal_kv_ln,
            within_limits = within_limits,
            deviation_pct = deviation_pct,
        ))

    # ── Step 4: Read line currents ────────────────────────────────────────────
    line_current_results: list[LineCurrentResult] = []

    line_name = dss.Lines.First()
    while line_name > 0:
        name     = dss.Lines.Name()
        ampacity = _get_ampacity(name)
        currents = dss.CktElement.CurrentsMagAng()
        phases   = dss.Lines.Phases()

        if currents and len(currents) >= phases * 2:
            mags      = [currents[i] for i in range(0, phases * 2, 2)]
            current_a = max(mags)
        else:
            current_a = 0.0
            warnings.append(f"No current data for line '{name}' — skipping.")

        loading_pct = (current_a / ampacity * 100.0) if ampacity > 0 else 0.0
        overloaded  = loading_pct > 100.0

        if overloaded:
            warnings.append(
                f"Line '{name}' is OVERLOADED: {current_a:.1f} A / {ampacity:.1f} A "
                f"({loading_pct:.1f}%). Reduce loading or upsize conductor."
            )

        line_current_results.append(LineCurrentResult(
            line_id     = name,
            current_a   = current_a,
            ampacity_a  = ampacity,
            loading_pct = loading_pct,
            overloaded  = overloaded,
        ))

        line_name = dss.Lines.Next()

    # ── Step 5: Read power losses ─────────────────────────────────────────────
    power_loss_results: list[PowerLossResult] = []

    line_name = dss.Lines.First()
    while line_name > 0:
        name   = dss.Lines.Name()
        losses = dss.CktElement.Losses()
        if losses and len(losses) >= 2:
            power_loss_results.append(PowerLossResult(
                element_id         = name,
                element_type       = "line",
                active_loss_kw     = losses[0] / 1000.0,
                reactive_loss_kvar = losses[1] / 1000.0,
            ))
        line_name = dss.Lines.Next()

    tx_name = dss.Transformers.First()
    while tx_name > 0:
        name = dss.Transformers.Name()
        dss.Circuit.SetActiveElement(f"Transformer.{name}")
        losses = dss.CktElement.Losses()
        if losses and len(losses) >= 2:
            power_loss_results.append(PowerLossResult(
                element_id         = name,
                element_type       = "transformer",
                active_loss_kw     = losses[0] / 1000.0,
                reactive_loss_kvar = losses[1] / 1000.0,
            ))
        tx_name = dss.Transformers.Next()

    # ── Step 6: Total system losses ───────────────────────────────────────────
    total_losses    = dss.Circuit.Losses()
    total_loss_kw   = total_losses[0] / 1000.0 if total_losses else 0.0
    total_loss_kvar = total_losses[1] / 1000.0 if total_losses else 0.0

    # ── Step 7: Read generator outputs ───────────────────────────────────────
    generator_output_results: list[GeneratorOutputResult] = []

    # Synchronous generators — terminal 1 only
    gen_name = dss.Generators.First()
    while gen_name > 0:
        name = dss.Generators.Name()
        dss.Circuit.SetActiveElement(f"Generator.{name}")
        powers = dss.CktElement.Powers()
        if powers and len(powers) >= 6:
            terminal1 = powers[:6]
            total_p   = -sum(terminal1[i]   for i in range(0, 6, 2)) / 1000.0
            total_q   = -sum(terminal1[i+1] for i in range(0, 6, 2)) / 1000.0
            generator_output_results.append(GeneratorOutputResult(
                generator_id = name,
                kw_output    = total_p,
                kvar_output  = total_q,
            ))
        gen_name = dss.Generators.Next()

    # Solar PV systems — terminal 1 only
    pv_name = dss.PVsystems.First()
    while pv_name > 0:
        name = dss.PVsystems.Name()
        dss.Circuit.SetActiveElement(f"PVSystem.{name}")
        powers = dss.CktElement.Powers()
        if powers and len(powers) >= 6:
            terminal1 = powers[:6]
            
            total_p   = -sum(terminal1[i]   for i in range(0, 6, 2)) 
            total_q   = -sum(terminal1[i+1] for i in range(0, 6, 2)) 
            generator_output_results.append(GeneratorOutputResult(
                generator_id = f"PV_{name}",
                kw_output    = total_p,
                kvar_output  = total_q,
            ))
        pv_name = dss.PVsystems.Next()

    # ── Assemble and return ───────────────────────────────────────────────────
    return SimulationResult(
        converged           = converged,
        iterations          = iterations,
        total_loss_kw       = total_loss_kw,
        total_loss_kvar     = total_loss_kvar,
        bus_voltages        = bus_voltage_results,
        line_currents       = line_current_results,
        power_losses        = power_loss_results,
        generator_outputs   = generator_output_results,
        warnings            = warnings,
    )
