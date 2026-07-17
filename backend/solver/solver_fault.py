"""
Fault Study Solver
==================
Runs an OpenDSS fault study and returns short-circuit currents
at every bus in the network.

Supported fault types:
  - Three-phase (3PH)     : most severe, symmetrical fault
  - Single line-to-ground (1LG): most common in real networks

Fault current calculations:
  I_3ph  = V_LN / |Z1|
  I_1LG  = 3 * V_LN / (2*|Z1| + |Z0|)

where V_LN is the pre-fault line-to-neutral voltage (nominal),
Z1 is the positive-sequence Thevenin impedance at the bus,
Z0 is the zero-sequence Thevenin impedance at the bus.

All currents returned in kA for readability.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math
import opendssdirect as dss


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BusFaultResult:
    """
    Short-circuit fault current results for a single bus.

    bus_id          : bus identifier
    voltage_kv_ll   : nominal line-to-line voltage at this bus in kV
    z1_real         : positive-sequence resistance (Thevenin) in Ohms
    z1_imag         : positive-sequence reactance (Thevenin) in Ohms
    z0_real         : zero-sequence resistance (Thevenin) in Ohms
    z0_imag         : zero-sequence reactance (Thevenin) in Ohms
    i3ph_ka         : three-phase symmetrical fault current in kA
    i1lg_ka         : single line-to-ground fault current in kA
    x_r_ratio       : X/R ratio of positive-sequence impedance
                      (important for protection relay settings)
    """
    bus_id:         str
    voltage_kv_ll:  float
    z1_real:        float
    z1_imag:        float
    z0_real:        float
    z0_imag:        float
    i3ph_ka:        float
    i1lg_ka:        float
    x_r_ratio:      float


@dataclass
class FaultStudyResult:
    """Complete fault study result for the entire network."""
    success:        bool
    bus_results:    list[BusFaultResult] = field(default_factory=list)
    warnings:       list[str]            = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success":  self.success,
            "warnings": self.warnings,
            "bus_results": [
                {
                    "bus_id":        r.bus_id,
                    "voltage_kv_ll": round(r.voltage_kv_ll, 3),
                    "z1_real":       round(r.z1_real,       6),
                    "z1_imag":       round(r.z1_imag,       6),
                    "z0_real":       round(r.z0_real,       6),
                    "z0_imag":       round(r.z0_imag,       6),
                    "i3ph_ka":       round(r.i3ph_ka,       4),
                    "i1lg_ka":       round(r.i1lg_ka,       4),
                    "i3ph_a":        round(r.i3ph_ka * 1000, 1),
                    "i1lg_a":        round(r.i1lg_ka * 1000, 1),
                    "x_r_ratio":     round(r.x_r_ratio,     2),
                }
                for r in self.bus_results
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FAULT SOLVER
# ─────────────────────────────────────────────────────────────────────────────

def run_fault_study(dss_script: str) -> FaultStudyResult:
    """
    Run a fault study on the network defined by dss_script.

    Strategy:
      1. Load the network in snapshot mode and solve (establishes Ybus)
      2. Switch to FaultStudy mode and solve (computes Zsc at all buses)
      3. Read Zsc1 and Zsc0 at each bus
      4. Calculate I3ph and I1LG from Thevenin impedances

    Parameters
    ----------
    dss_script : str
        Complete DSS script from dss_translator.translate_grid()

    Returns
    -------
    FaultStudyResult
        Fault currents at every bus.
    """

    warnings: list[str] = []

    # ── Step 1: Load network in snapshot mode ─────────────────────────────────
    try:
        dss.Text.Command("Clear")
        for line in dss_script.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("!"):
                continue
            # Skip the Solve command — we'll run fault study instead
            if stripped.lower() == "solve":
                continue
            dss.Text.Command(stripped)
            result_str = dss.Text.Result()
            if result_str and "error" in result_str.lower():
                return FaultStudyResult(
                    success=False,
                    warnings=[f"DSS command failed: '{stripped}' -> {result_str}"]
                )
    except Exception as e:
        return FaultStudyResult(
            success=False,
            warnings=[f"Network load failed: {str(e)}"]
        )

    # ── Step 2: Run snapshot solve first to establish Ybus ────────────────────
    try:
        dss.Text.Command("Set Mode=0")
        dss.Text.Command("Solve")
        if not dss.Solution.Converged():
            warnings.append("Snapshot solve did not converge — fault study results may be unreliable.")
    except Exception as e:
        warnings.append(f"Snapshot solve warning: {str(e)}")

    # ── Step 3: Run fault study ───────────────────────────────────────────────
    try:
        dss.Text.Command("Set Mode=FaultStudy")
        dss.Text.Command("Solve")
    except Exception as e:
        return FaultStudyResult(
            success=False,
            warnings=[f"Fault study solve failed: {str(e)}"]
        )

    # ── Step 4: Read results at each bus ──────────────────────────────────────
    bus_results: list[BusFaultResult] = []

    bus_names = [
        b for b in dss.Circuit.AllBusNames()
        if b.lower() not in ("sourcebus", "source")
    ]

    for bus_name in bus_names:
        try:
            dss.Circuit.SetActiveBus(bus_name)

            kv_base_ln = dss.Bus.kVBase()           # line-to-neutral kV
            kv_ll      = kv_base_ln * math.sqrt(3)  # line-to-line kV

            zsc1 = dss.Bus.Zsc1()  # [R1, X1] in Ohms
            zsc0 = dss.Bus.Zsc0()  # [R0, X0] in Ohms

            if not zsc1 or len(zsc1) < 2:
                warnings.append(f"Bus '{bus_name}': no Zsc1 data available — skipping.")
                continue

            r1, x1 = zsc1[0], zsc1[1]
            z1      = math.sqrt(r1**2 + x1**2)

            if not zsc0 or len(zsc0) < 2:
                # Fall back to Z0 = Z1 if zero-sequence data unavailable
                warnings.append(f"Bus '{bus_name}': no Zsc0 data — using Z0=Z1 approximation.")
                r0, x0 = r1, x1
            else:
                r0, x0 = zsc0[0], zsc0[1]

            z0 = math.sqrt(r0**2 + x0**2)

            # Three-phase fault: I3ph = V_LN / Z1
            i3ph_ka = (kv_base_ln / z1) if z1 > 1e-9 else 0.0

            # Single line-to-ground: I1LG = 3*V_LN / (2*Z1 + Z0)
            denom_1lg = 2 * z1 + z0
            i1lg_ka   = (3 * kv_base_ln / denom_1lg) if denom_1lg > 1e-9 else 0.0

            # X/R ratio
            x_r_ratio = (x1 / r1) if r1 > 1e-9 else 0.0

            bus_results.append(BusFaultResult(
                bus_id        = bus_name,
                voltage_kv_ll = kv_ll,
                z1_real       = r1,
                z1_imag       = x1,
                z0_real       = r0,
                z0_imag       = x0,
                i3ph_ka       = i3ph_ka,
                i1lg_ka       = i1lg_ka,
                x_r_ratio     = x_r_ratio,
            ))

        except Exception as e:
            warnings.append(f"Bus '{bus_name}': error reading fault data — {str(e)}")

    if not bus_results:
        return FaultStudyResult(
            success=False,
            warnings=warnings + ["No bus fault data could be retrieved."]
        )

    return FaultStudyResult(
        success=True,
        bus_results=bus_results,
        warnings=warnings,
    )
