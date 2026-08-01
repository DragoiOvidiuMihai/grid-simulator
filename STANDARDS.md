# Standards Reference — Grid Simulator & SCADA/HMI

This document lists every IEC and EN standard used in Grid Simulator and the SCADA/HMI module, explaining what each one governs and how it is applied. All component parameters, result limits, alarm thresholds, and diagram symbols are sourced from these standards rather than assumed or approximated.

---

## Voltage Quality

### EN 50160 — Voltage Characteristics of Electricity Supplied by Public Distribution Networks

**Scope:** Defines the main voltage parameters and their permissible deviation ranges at the customer's point of connection in public low voltage and medium voltage distribution networks across Europe.

**Applied in Grid Simulator:**

| Clause | Requirement | Implementation |
|--------|-------------|----------------|
| 3.3 (LV) | Voltage magnitude within ±10% of nominal (230 V phase-to-neutral / 400 V line-to-line) for 95% of 10-minute mean values over any week | All LV bus voltages checked against 0.90–1.10 pu after every simulation step |
| 4.2 (MV) | Voltage magnitude within ±10% of nominal (11 kV) under normal operating conditions | All MV bus voltages checked against 0.90–1.10 pu after every simulation step |

**Limit applied:** ±10% from nominal (0.90 pu to 1.10 pu) for both MV and LV buses in steady-state power flow.

**In time-series mode:** The limit is applied at every 30-minute step. The results panel and PDF report show the number of violations across all 48 steps. A bus with zero violations is fully EN 50160 compliant for the simulated day.

**Nominal voltages used:**
- MV network: 11 kV line-to-line / 6.35 kV line-to-neutral
- LV network: 0.4 kV line-to-line / 0.231 kV line-to-neutral

**Applied in SCADA/HMI:**

| Threshold | Limit | Alarm Priority |
|-----------|-------|---------------|
| Voltage high warning | > 1.06 pu (+6%) | MEDIUM |
| Voltage high critical | > 1.10 pu (+10%) | HIGH |
| Voltage low warning | < 0.94 pu (−6%) | MEDIUM |
| Voltage low critical | < 0.90 pu (−10%) | HIGH |

The SCADA alarm engine evaluates these thresholds on every simulation tick (every 5 seconds). Warning thresholds are set at ±6% to give operators advance warning before the statutory ±10% limit is reached. Reference lines at ±6% (amber) and ±10% (red) are drawn on the historical voltage trend charts.

---

## Overhead Conductors

### IEC 61089 — Round Wire Concentric Lay Overhead Electrical Stranded Conductors

**Scope:** Specifies requirements for round wire concentric lay stranded overhead conductors including ACSR (Aluminium Conductor Steel Reinforced) and all-aluminium conductors. Covers conductor construction, mechanical properties, and electrical resistance values.

**Applied in Grid Simulator:**

The overhead line component uses ACSR 150 mm² as its reference conductor. All electrical parameters are sourced from IEC 61089 tables:

| Parameter | Value | Source |
|-----------|-------|--------|
| DC resistance at 20°C | 0.194 Ω/km | IEC 61089, Al strand resistance for 150 mm² |
| AC resistance at 75°C (R1) | 0.196 Ω/km | Temperature corrected using resistance-temperature coefficient for aluminium |
| Positive-sequence reactance (X1) | 0.332 Ω/km | Calculated for typical 11 kV pole-top geometry (1 m geometric mean distance between phases) |
| Zero-sequence resistance (R0) | 0.588 Ω/km | ≈ 3 × R1, earth return path approximation (no ground wire) |
| Zero-sequence reactance (X0) | 0.996 Ω/km | ≈ 3 × X1, earth return path approximation |
| Ampacity at 75°C | 415 A | IEC 61089 continuous current rating for ACSR 150 mm² in still air |

### EN 50182 — Conductors for Overhead Lines — Round Wire Concentric Lay Stranded Conductors

**Scope:** European standard specifying the construction and dimensions of concentric lay stranded overhead conductors. Supplements IEC 61089 with European-specific conductor designations.

**Applied in Grid Simulator:** The ACSR 150 mm² conductor designation follows EN 50182 naming conventions. The 150 mm² refers to the cross-sectional area of the aluminium strands (the current-carrying portion), which is the standard way overhead conductors are specified in European practice.

---

## Underground Cables

### IEC 60502-2 — Power Cables with Extruded Insulation and Their Accessories for Rated Voltages from 6 kV up to 30 kV

**Scope:** Specifies the construction, dimensions, and test requirements for extruded-insulation power cables used in medium voltage distribution networks. Covers XLPE (cross-linked polyethylene) insulated cables, which are the standard for modern underground MV distribution.

**Applied in Grid Simulator:**

The underground cable component uses a 12/20 kV XLPE 150 mm² Cu cable as its reference. The voltage designation 12/20 kV means:
- **12 kV** — maximum continuous phase-to-ground voltage
- **20 kV** — maximum continuous phase-to-phase voltage (system voltage)

This is the correct IEC designation for a cable used in an 11 kV network. All parameters are sourced from IEC 60502-2:

| Parameter | Value | Source |
|-----------|-------|--------|
| Rated voltage | 12/20 kV | IEC 60502-2, suitable for 11 kV system voltage |
| AC resistance at 90°C (R1) | 0.124 Ω/km | IEC 60228 Class 2 conductor, 150 mm² Cu at maximum operating temperature |
| Positive-sequence reactance (X1) | 0.113 Ω/km | Typical value for XLPE 150 mm² in trefoil formation |
| Zero-sequence resistance (R0) | 0.372 Ω/km | ≈ 3 × R1, metallic screen return path |
| Zero-sequence reactance (X0) | 0.113 Ω/km | Equal to X1 for trefoil formation with continuous screen |
| Shunt capacitance (C1) | 0.28 µF/km | Typical for 12/20 kV XLPE construction |
| Ampacity (direct buried, 20°C soil) | 360 A | IEC 60502-2, 150 mm² Cu direct buried at standard soil thermal resistivity |

### IEC 60228 — Conductors of Insulated Cables

**Scope:** Specifies the construction of conductors used in insulated cables, including resistance values per unit length at 20°C for different conductor classes and cross-sections.

**Applied in Grid Simulator:** The copper conductor resistance for the underground cable (150 mm² Cu) is sourced from IEC 60228 Class 2 (stranded conductor) tables and corrected to the maximum operating temperature of 90°C for XLPE insulation.

---

## Transformers

### Dyn11 Vector Group (IEC 60076-1)

**Scope:** IEC 60076-1 (Power Transformers — General) defines transformer vector groups. The vector group notation specifies the winding connection type and the phase displacement between primary and secondary voltages.

**Applied in Grid Simulator:**

The transformer component uses Dyn11 as its vector group:

| Symbol | Meaning |
|--------|---------|
| **D** | Primary winding connected in Delta |
| **y** | Secondary winding connected in Star (wye) |
| **n** | Neutral point of secondary winding brought out |
| **11** | Phase displacement of 30° lag (secondary lags primary by 330°) |

**Why Dyn11 is the EU distribution standard:**
- The delta primary winding suppresses third-harmonic voltages on the MV network
- The star secondary with neutral provides a solidly earthed neutral on the LV side, required for single-phase 230 V loads
- The neutral isolation between MV and LV networks means zero-sequence fault currents on the LV side do not propagate to the MV network
- The 30° phase displacement provides harmonic cancellation benefits in larger networks with multiple transformers

**OpenDSS implementation:** The vector group is translated to the `conns=[delta, wye]` parameter in OpenDSS transformer objects.

**Transformer parameters used (Grid Simulator):**

| Parameter | Value | Basis |
|-----------|-------|-------|
| Rated power | 500 kVA | Typical EU urban distribution transformer |
| Primary voltage | 11 kV | EU standard MV distribution voltage |
| Secondary voltage | 0.4 kV | EU standard LV distribution voltage |
| Winding resistance (%R) | 1.1% | Typical value for 500 kVA distribution transformer |
| Leakage reactance (%X) | 4.0% | Typical value for 500 kVA distribution transformer |

**Applied in SCADA/HMI:**

The SCADA substation includes TX1 and TX2, each 630 kVA, modelled with %Z = 4% (%X = 4%, %R = 0.5%) in the OpenDSS data source. IEC 60076-1 loading limits are applied as SCADA alarm thresholds:

| Threshold | Limit | Alarm Priority |
|-----------|-------|---------------|
| Transformer loading warning | > 70% rated kVA | MEDIUM |
| Transformer loading critical | > 90% rated kVA | HIGH |

Reference lines at 70% (amber) and 90% (red) are drawn on the TX Loading historical trend chart.

---

## Solar PV

### IEC 61215 — Terrestrial Photovoltaic (PV) Modules — Design Qualification and Type Approval

**Scope:** Specifies requirements for design qualification and type approval of terrestrial PV modules for long-term operation. Defines Standard Test Conditions (STC) for PV module rating.

**Applied in Grid Simulator:**

PV system output is rated at Standard Test Conditions (STC):

| STC Parameter | Value |
|---------------|-------|
| Irradiance | 1.0 kW/m² |
| Cell temperature | 25°C |
| Air mass | AM 1.5 |

In Grid Simulator, the `kw_peak` parameter of the Solar PV component represents the DC nameplate power at STC. The irradiance field (default 1.0 kW/m²) scales the output proportionally — at 0.5 kW/m² the system produces approximately 50% of rated output.

**Temperature coefficient:** The `temp_coefficient_pct` parameter (default -0.35%/°C) captures the reduction in PV output as cell temperature rises above 25°C. This parameter is used in time-series simulations where temperature derating is relevant.

**OpenDSS PVSystem object:** Solar PV uses the dedicated `PVSystem` object rather than a `Generator` object. The PVSystem object correctly implements irradiance-dependent output scaling, inverter current limiting, and volt-VAR response.

**Applied in SCADA/HMI:** The SCADA substation includes PV1 (50 kW peak) connected to Bus C via CB7. In synthetic mode, PV output follows the same irradiance profile as Grid Simulator (zero between 20:00 and 06:00). In OpenDSS mode, PV1 is modelled as a generator with output scaled by the time-of-day irradiance factor.

---

## Fault Analysis

### EN 60909 — Short-Circuit Currents in Three-Phase AC Systems

**Scope:** International standard (adopted in Europe as EN 60909) specifying methods for calculating short-circuit currents in three-phase AC power systems. Defines the equivalent voltage source method and the Thevenin impedance method for fault current calculation.

**Applied in Grid Simulator:**

The fault study uses the Thevenin impedance method:

**Three-phase symmetrical fault current:**
```
I_3ph = V_LN / |Z1|
```

**Single line-to-ground fault current (symmetrical components):**
```
I_1LG = 3 x V_LN / (2 x |Z1| + |Z0|)
```

Where:
- `V_LN` = pre-fault line-to-neutral voltage (nominal, in kV)
- `Z1` = positive-sequence Thevenin impedance at the faulted bus (ohms)
- `Z0` = zero-sequence Thevenin impedance at the faulted bus (ohms)

The assumption Z1 = Z2 (positive and negative sequence impedances are equal) is valid for balanced, passive network elements and is standard practice in distribution network fault studies.

**Results provided:**

| Result | Engineering use |
|--------|----------------|
| I_3ph (kA and A) | Circuit breaker short-circuit rating verification |
| I_1LG (kA and A) | Earth fault protection relay setting |
| X/R ratio | DC offset factor for breaker interrupting duty calculation |
| Z1, Z0 (ohms) | Distance relay and differential protection setting |

---

## Graphical Symbols

### IEC 60617 — Graphical Symbols for Diagrams

**Scope:** Provides graphical symbols for use in electrotechnical diagrams, including symbols for switching devices, transformers, measuring instruments, busbars, and connection points.

**Applied in SCADA/HMI:**

The SCADA single-line diagram SVG follows IEC 60617 symbol conventions:

| Symbol | IEC 60617 Basis | Implementation |
|--------|----------------|----------------|
| Circuit breaker | Square on conductor line (IEC 60617-7) | Filled square (closed), hollow square (open) |
| Busbar | Thick horizontal line | 6px stroke, coloured by voltage state |
| Two-winding transformer | Two interlocking circles | Upper circle (primary), lower circle (secondary) |
| Load | Rectangle with internal lines | Resistor symbol inside rectangle |
| PV source | Circle with rays | Sun symbol with filled core |
| Power flow direction | Arrow on conductor | Downward arrow at feeder entry points |

Colour coding is not specified by IEC 60617 but follows common industrial practice: green for energised/healthy, amber for warning, red for alarm/fault, grey for de-energised.

---

## Summary Table

| Standard | Full title | Governs |
|----------|-----------|---------|
| **EN 50160** | Voltage Characteristics of Electricity Supplied by Public Distribution Networks | Voltage quality limits (±10% nominal). Applied to all bus voltage results in Grid Simulator and to SCADA alarm thresholds (±6% warning, ±10% critical). |
| **IEC 61089** | Round Wire Concentric Lay Overhead Electrical Stranded Conductors | ACSR 150mm² resistance and ampacity values |
| **EN 50182** | Conductors for Overhead Lines — Round Wire Concentric Lay Stranded Conductors | ACSR 150mm² European naming and construction |
| **IEC 60502-2** | Power Cables with Extruded Insulation for 6 kV to 30 kV | 12/20kV XLPE cable ratings and construction |
| **IEC 60228** | Conductors of Insulated Cables | 150mm² Cu conductor resistance at rated temperature |
| **IEC 60076-1** | Power Transformers — General | Dyn11 vector group definition, transformer parameters, and SCADA loading alarm thresholds (70%/90%) |
| **IEC 61215** | Terrestrial PV Modules — Design Qualification and Type Approval | Standard Test Conditions (1.0 kW/m², 25°C) for PV rating |
| **EN 60909** | Short-Circuit Currents in Three-Phase AC Systems | Fault current calculation methodology (Thevenin method) |
| **IEC 60617** | Graphical Symbols for Diagrams | SCADA single-line diagram symbol conventions |
