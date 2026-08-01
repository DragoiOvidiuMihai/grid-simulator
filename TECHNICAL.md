# Technical Documentation — Grid Simulator & SCADA/HMI

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [System Architecture](#2-system-architecture)
3. [Data Model](#3-data-model)
4. [DSS Script Translator](#4-dss-script-translator)
5. [OpenDSS Solver Integration](#5-opendss-solver-integration)
6. [Time-Series Simulation](#6-time-series-simulation)
7. [Fault Study Implementation](#7-fault-study-implementation)
8. [EN 50160 Compliance Engine](#8-en-50160-compliance-engine)
9. [PDF Report Generator](#9-pdf-report-generator)
10. [Frontend Architecture — Grid Simulator](#10-frontend-architecture--grid-simulator)
11. [Key Engineering Decisions — Grid Simulator](#11-key-engineering-decisions--grid-simulator)
12. [Validation and Correctness](#12-validation-and-correctness)
13. [SCADA/HMI Module Architecture](#13-scadahmi-module-architecture)
14. [SCADA Data Sources](#14-scada-data-sources)
15. [SCADA Alarm Engine](#15-scada-alarm-engine)
16. [SCADA WebSocket Protocol](#16-scada-websocket-protocol)
17. [SCADA History Store](#17-scada-history-store)
18. [SCADA Frontend Architecture](#18-scada-frontend-architecture)
19. [Key Engineering Decisions — SCADA](#19-key-engineering-decisions--scada)

---

## 1. Design Philosophy

Grid Simulator was built around three core principles that shaped every technical decision:

**Wrap a validated solver rather than build one.**
OpenDSS implements three-phase unbalanced power flow with full Ybus admittance matrix construction, iterative Newton-Raphson solving, and convergence handling for ill-conditioned networks. Reimplementing this from scratch would take years and produce results that are difficult to validate. By wrapping OpenDSS via the `opendssdirect.py` Python interface, the simulation results inherit the correctness of a solver that has been validated against hundreds of published test cases and is used in production by utilities worldwide.

**Model fewer components correctly rather than many components loosely.**
The component library contains 8 components. Every parameter — conductor impedance, transformer vector group, cable capacitance — is sourced from the actual IEC/EN standards that govern those components in European distribution networks. This is more valuable engineering than offering 30 components with approximate or assumed parameters.

**Separate concerns cleanly.**
The system is divided into four layers that never overlap: data validation (Pydantic models), network description (DSS script translator), simulation (OpenDSS solver wrapper), and presentation (React frontend). Each layer has a single responsibility and communicates with adjacent layers through well-defined interfaces.

**The SCADA module extends without modifying.**
The SCADA/HMI module was designed as a plugin: it adds a new FastAPI router, a new React route, and a new backend package (`backend/scada/`) without touching any existing file from the original Grid Simulator. The existing REST endpoints, frontend canvas, data models, and solvers are completely unaffected.

---

## 2. System Architecture

### Request lifecycle

```
User draws grid on canvas
        │
        ▼
Zustand store (gridStore.js)
  buildGridPayload() converts React Flow nodes/edges → Grid JSON
        │
        ▼ HTTP POST
FastAPI endpoint (main.py)
  Pydantic validates Grid JSON against data models
        │
        ▼
DSS Script Translator (dss_translator.py)
  Grid object → multi-line DSS script string
        │
        ▼
OpenDSS Solver Wrapper (solver.py)
  DSS script → opendssdirect.py API → simulation results
        │
        ▼
SimulationResult dataclass
  to_dict() → JSON response
        │
        ▼ HTTP response
React Frontend
  Results panel displays voltages, currents, losses
```

### SCADA/HMI data flow

```
asyncio background task (SimulationLoop)
  every 5 seconds:
        │
        ▼
DataSource.get_measurements(breaker_states)
  SyntheticDataSource   → mathematical profile
  OpenDSSDataSource     → real power flow via opendssdirect
        │
        ▼
AlarmEngine.evaluate(measurements)
  check each measurement against thresholds
  update alarm lifecycle (ACTIVE / ACKNOWLEDGED / CLEARED)
        │
        ▼
EventLog  → record newly raised / cleared alarms
HistoryStore → write to SQLite
        │
        ▼
ConnectionManager.broadcast(packet)
  push JSON to all connected WebSocket clients
        │
        ▼ WebSocket push
React SCADA frontend
  scadaStore ← applyStateUpdate(packet)
  SingleLineDiagram re-renders with new colours/values
  AlarmPanel re-renders with new alarm list
```

### Technology choices

| Layer | Technology | Reason |
|-------|-----------|--------|
| Simulation engine | OpenDSS via opendssdirect.py | Professional-grade validated solver |
| Backend framework | FastAPI | Async-capable, auto-generates API docs, native Pydantic integration, WebSocket support |
| Data validation | Pydantic v2 | Schema enforcement with custom validators, clean error messages |
| PDF generation | ReportLab | Full programmatic control over layout, tables, and colours |
| SCADA persistence | SQLite | Zero-configuration, file-based, sufficient for 7-day time-series at 5-second intervals |
| Frontend framework | React | Component model suits both the grid component library and SCADA panel concepts |
| Canvas library | React Flow | Purpose-built for node/edge diagrams, handles drag, drop, and connections |
| SCADA diagram | SVG + React state | Fixed-topology diagrams suit SVG better than React Flow; full control over IEC 60617 symbols |
| SCADA charts | Recharts | Composable, handles time-series line charts with reference lines well |
| State management | Zustand | Minimal boilerplate, no Provider wrapper, component access in one line |
| Styling | Tailwind CSS | Utility-first, no fighting a UI framework |
| Build tool | Vite | Fast HMR during development, optimised production builds |

---

## 3. Data Model

### Overview

The data model (`backend/models/models.py`) defines the contract between the frontend and backend. Every component is a Pydantic `BaseModel` with typed fields, default values, and validators.

### Component hierarchy

```
Grid
├── list[BusPrimary]           — MV buses (11 kV)
├── list[BusSecondary]         — LV buses (0.4 kV)
├── list[TwoWindingTransformer]
├── list[OverheadLine]
├── list[UndergroundCable]
├── list[ResidentialLoad]
├── list[IndustrialLoad]
├── list[SynchronousGenerator]
└── list[SolarPV]
```

### Design decisions in the data model

**Explicit units in field names.**
Every field name includes its unit: `length_km`, `r1_ohm_per_km`, `rated_kv`, `kw_peak`. This prevents unit conversion errors — one of the most common sources of bugs in engineering software.

**kVAR stored explicitly, not power factor.**
OpenDSS requires both `kW` and `kVAR` for load objects. It does not accept power factor alone. The data model stores `kvar` explicitly on every load component, with the value pre-calculated from the rated power and power factor. This prevents a class of errors where the translator would need to compute reactive power from a power factor and might make sign or angle errors.

**Separate BusPrimary and BusSecondary classes.**
MV and LV buses are separate classes rather than a single `Bus` class with a voltage field. This allows the validator to enforce that residential loads can only reference LV buses and that transformers connect MV to LV — not LV to LV. It also makes the translator code clearer.

**Cross-field validators on the Grid class.**
Three validators run at the Grid level after all individual components are valid:

```python
@model_validator(mode="after")
def validate_has_buses(self) -> Grid:
    if not self.mv_buses and not self.lv_buses:
        raise ValueError("Grid must contain at least one bus.")

@model_validator(mode="after")
def validate_unique_ids(self) -> Grid:
    # All component IDs across the entire network must be unique.
    # Duplicate IDs would produce a broken DSS script silently.

@model_validator(mode="after")
def validate_slack_bus(self) -> Grid:
    # At most one generator can be marked as slack bus.
    # Two slack buses would make the power flow unsolvable.
```

These validators catch topological errors before any DSS script is generated, producing clear error messages rather than cryptic OpenDSS failures.

### Enum usage

```python
class TransformerConnection(str, Enum):
    DYN11 = "Dyn11"   # Delta primary, Star+neutral secondary — EU standard
    YNyn0 = "YNyn0"
    Dd0   = "Dd0"

class PhaseCount(int, Enum):
    SINGLE = 1
    THREE  = 3
```

Enums enforce valid choices at the schema boundary. An invalid vector group string is rejected by Pydantic before reaching the translator.

---

## 4. DSS Script Translator

### Purpose

The translator (`backend/translators/dss_translator.py`) converts a validated `Grid` object into a DSS script string that OpenDSS can execute. This is the most engineering-intensive component in the backend — it requires understanding both the Pydantic data model and the OpenDSS command syntax for every component type.

### Script structure

A generated DSS script follows this structure:

```
Clear
New Circuit.[grid_id] basekv=[mv_voltage] pu=1.0 phases=3 bus1=[source_bus]

! Conductor definitions (LineCode objects)
New LineCode.ACSR150 nphases=3 R1=0.196 X1=0.332 R0=0.588 X0=0.996 units=km
New LineCode.XLPE150CU nphases=3 R1=0.124 X1=0.113 R0=0.372 X0=0.113 C1=0.28 units=km

! Buses (comment only — buses are created implicitly by component references)

! Transformers
New Transformer.[id] phases=3 windings=2 buses=[mv_bus,lv_bus]
    conns=[delta,wye] kVs=[11,0.4] kVAs=[500,500] %R=1.1 XHL=4.0

! Lines
New Line.[id] bus1=[from_bus] bus2=[to_bus] linecode=ACSR150 length=1.0 units=km

! Loads
New Load.[id] phases=1 bus1=[lv_bus].1 kV=0.231 kW=5 kVAR=1.64 Model=1

! Generation
New Generator.[id] phases=3 bus1=[mv_bus] kV=11 kW=500 PF=0.8 Model=1
New PVSystem.[id] phases=3 bus1=[lv_bus] kV=0.4 kVA=102 Pmpp=100 irradiance=1 PF=1

Set VoltageBases=[11, 0.4]
CalcVoltageBases
Set Mode=0
Solve
```

### Critical translator decisions

**Bus anchor reactors removed.**
An early version used near-zero-impedance reactors to anchor bus nodes in the OpenDSS topology. This was found to disrupt `CalcVoltageBases` propagation through transformers, producing near-zero per-unit voltages. Buses are now declared as comments only — OpenDSS creates them implicitly when components reference them, which is the correct approach.

**`CalcVoltageBases` before `Solve`.**
OpenDSS requires explicit voltage base assignment before solving. Without `Set VoltageBases=[...]` and `CalcVoltageBases`, all per-unit calculations are based on an undefined reference and produce meaningless results. The translator always emits these commands, ordered after all component definitions.

**Dyn11 vector group translation.**
```python
conn_map = {
    TransformerConnection.DYN11: "[delta, wye]",
    TransformerConnection.YNyn0: "[wye, wye]",
    TransformerConnection.Dd0:   "[delta, delta]",
}
```
OpenDSS does not accept the IEC vector group notation directly. The translator maps IEC vector group enums to the OpenDSS `conns=` parameter format.

**Phase suffix on single-phase loads.**
Residential loads must specify which phase of the LV bus they connect to:
```
New Load.HOUSE1 phases=1 bus1=BUS_LV_01.1 kV=0.231 ...
```
The `.1` suffix selects phase A. The `PhaseAssignment` enum (A=1, B=2, C=3) maps directly to this suffix.

**PVSystem object, not Generator.**
Solar PV must use the OpenDSS `PVSystem` object rather than `Generator`. `PVSystem` correctly models inverter current-limiting behaviour, irradiance-dependent output scaling, and volt-VAR response. A `Generator` object would produce incorrect results for solar PV — it would not scale output with irradiance and would not respect the inverter kVA rating.

**`maxkvar`/`minkvar` parameter names.**
The current version of opendssdirect.py uses `maxkvar` and `minkvar` as the parameter names for generator reactive power limits. Earlier OpenDSS versions used `kVARmax`/`kVARmin`. The translator uses the current names to avoid deprecation warnings and command rejection.

---

## 5. OpenDSS Solver Integration

### Command execution

A critical finding during development: `opendssdirect.py` must receive DSS commands **one line at a time**. Passing a multi-line script as a single string to `dss.Text.Command()` silently ignores everything after the first newline, producing an essentially empty circuit with near-zero voltages.

```python
# WRONG — only the first line executes
dss.Text.Command(entire_script)

# CORRECT — every line executes
for line in dss_script.splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        continue
    dss.Text.Command(stripped)
```

This was the root cause of the most persistent debugging session during development. The symptom (near-zero voltages on all buses, solver converges in 2 iterations) was misleading — OpenDSS was solving an empty circuit, which trivially converges.

### Deprecated API migration

The `dss.run_command()` method is deprecated in current versions of opendssdirect.py. The correct API is `dss.Text.Command()` for single commands and `dss.Text.Result()` to read the result string. All solver code uses the current API.

### Reading PVSystem powers

OpenDSS `PVSystem` objects return power in **kW** from `dss.CktElement.Powers()`, unlike `Generator` objects which return power in **W**. This unit difference is not documented clearly and caused a factor-of-1000 error in early results (100 kW PV system reporting 0.1 kW output).

Additionally, `Powers()` returns values for both terminals of the element. For a PVSystem with two terminals, the array contains 8 values: `[P_A_t1, Q_A_t1, P_B_t1, Q_B_t1, P_C_t1, Q_C_t1, P_t2, Q_t2]`. Only terminal 1 (first 6 values) should be summed — terminal 2 values nearly cancel terminal 1 and produce near-zero results if included.

```python
# Correct: terminal 1 only, no /1000 conversion for PVSystem
terminal1 = powers[:6]
total_p = -sum(terminal1[i] for i in range(0, 6, 2))
```

### Voltage reading

Per-unit voltages are read using `dss.Bus.puVmagAngle()` which returns values already divided by the bus base voltage. This is more reliable than reading raw voltages in Volts and dividing manually, because it uses the same base voltage that OpenDSS computed via `CalcVoltageBases`.

```python
pu_vm_ang     = dss.Bus.puVmagAngle()
pu_magnitudes = [pu_vm_ang[i] for i in range(0, len(pu_vm_ang), 2)]
pu            = sum(pu_magnitudes) / len(pu_magnitudes)  # average across phases
```

---

## 6. Time-Series Simulation

### Approach: manual multiplier injection

OpenDSS supports a native daily simulation mode (`Mode=1`) with `LoadShape` objects that define how loads vary over time. During development, this mode was found to be unreliable for step-by-step result reading — the `LoadShape` multipliers were not being applied when solving one step at a time using `dss.Text.Command("Solve")`.

The robust alternative adopted is **manual multiplier injection with repeated snapshot solves**:

```python
for step in range(48):
    # Update each load directly
    dss.Text.Command(f"Load.{name}.kW={peak_kw * profile[step]}")
    dss.Text.Command(f"Load.{name}.kVAR={peak_kvar * profile[step]}")

    # Update PV irradiance
    dss.Text.Command(f"PVSystem.{name}.irradiance={irr_profile[step]}")

    # Solve snapshot
    dss.Text.Command("Set Mode=0")
    dss.Text.Command("Solve")

    # Read results for this step
```

This approach is more verbose but completely reliable — each step is an independent snapshot solve with exactly the correct parameter values.

### Romanian daily profiles

Load profiles are based on ENTSO-E Romanian demand patterns and standard Eastern European household consumption studies. The 48-point (30-minute interval) profiles are:

**Residential load** — characterised by two daily peaks reflecting Romanian household behaviour:
- Morning peak: 07:00–09:00 (0.82–1.00 pu) — morning preparation and commute
- Evening peak: 18:00–21:00 (0.90–1.00 pu) — return home, cooking, lighting
- Night trough: 01:00–05:00 (0.23–0.25 pu)

**Industrial load** — flatter profile with three-shift pattern:
- Day shift: 06:00–16:00 (0.92–1.00 pu)
- Night shift: 00:00–06:00, 16:00–24:00 (0.50–0.68 pu)
- Slight midday dip: 12:00–13:00 (0.82–0.85 pu) for lunch break

**Solar irradiance** — clear-sky model based on solar geometry at 44.4°N (Bucharest):
- Summer (June 21): sunrise ~05:30, sunset ~21:00, peak GHI 0.85 kW/m² at solar noon ~13:00
- Winter (December 21): sunrise ~07:50, sunset ~16:10, peak GHI 0.35 kW/m² at solar noon ~12:10
- The 4.4× ratio between summer and winter peak irradiance reflects the actual difference in solar elevation angle at this latitude

All profiles are normalised to 0–1 and scaled by component peak values and the user-configurable load multiplier at runtime.

---

## 7. Fault Study Implementation

### Method

The fault study uses OpenDSS `FaultStudy` mode to compute the Thevenin equivalent impedance at every bus in the network. From the Thevenin impedances, fault currents are calculated analytically:

**Three-phase symmetrical fault:**
```
I_3ph = V_LN / |Z1|
```

**Single line-to-ground fault:**
```
I_1LG = 3 × V_LN / (2×|Z1| + |Z0|)
```

Where:
- `V_LN` = pre-fault line-to-neutral voltage (nominal, in kV)
- `Z1` = positive-sequence Thevenin impedance at the bus (from `dss.Bus.Zsc1()`)
- `Z0` = zero-sequence Thevenin impedance at the bus (from `dss.Bus.Zsc0()`)

The single line-to-ground formula uses the symmetrical components method, assuming `Z1 = Z2` (positive and negative sequence impedances are equal for balanced networks).

### Solve sequence

```python
# 1. Load the network in snapshot mode
dss.Text.Command("Set Mode=0")
dss.Text.Command("Solve")  # Establishes Ybus matrix

# 2. Switch to fault study mode
dss.Text.Command("Set Mode=FaultStudy")
dss.Text.Command("Solve")  # Computes Zsc at all buses

# 3. Read Thevenin impedances at each bus
dss.Circuit.SetActiveBus(bus_name)
zsc1 = dss.Bus.Zsc1()  # [R1, X1] in Ohms
zsc0 = dss.Bus.Zsc0()  # [R0, X0] in Ohms
```

The snapshot solve must run first to establish the network admittance matrix. The fault study then inverts this matrix to compute Thevenin impedances.

### X/R ratio

The X/R ratio of the positive-sequence impedance is reported for each bus:
```python
x_r_ratio = x1 / r1
```

This value is critical for protection engineers — a high X/R ratio means the fault current has a large DC offset component, which increases the required interrupting duty of circuit breakers beyond the symmetrical fault current value.

---

## 8. EN 50160 Compliance Engine

EN 50160 is the European standard for voltage characteristics of public distribution networks. The key steady-state limit applied in this project is:

**Clause 4.2 (MV networks) and Clause 3.3 (LV networks):**
Under normal operating conditions, the 10-minute mean RMS voltage shall be within ±10% of the declared voltage for 95% of the time.

For steady-state power flow (snapshot mode), we apply the limit strictly to every bus:

```python
EN50160_LIMIT_PU = 0.10  # ±10%

def _voltage_within_limits(pu: float) -> bool:
    return (1.0 - EN50160_LIMIT_PU) <= pu <= (1.0 + EN50160_LIMIT_PU)
    # i.e. 0.90 pu to 1.10 pu
```

For time-series mode, the limit is applied at every time step and the number of violations is counted across all 48 steps. A bus with zero violations across 48 steps is fully EN 50160 compliant for the simulated day.

Violations trigger:
1. A warning message in the results panel
2. The bus node border turning red on the canvas
3. A FAIL status in the PDF report compliance table

---

## 9. PDF Report Generator

The PDF generator (`backend/api/report_generator.py`) uses **ReportLab Platypus** — a flow-based document layout engine that handles page breaks, repeating headers, and table styles automatically.

### Document structure

```python
story = []

# 1. Cover page (navy background, project title, metadata, standards badge)
_build_cover_page(story, styles, ...)

# 2. Page break
story.append(PageBreak())

# 3. Results pages (different function per simulation mode)
if is_timeseries:
    _build_timeseries_results(story, styles, result)
elif is_fault:
    _build_fault_results(story, styles, result)
else:
    _build_snapshot_results(story, styles, result)

# 4. Build with header/footer callback
doc.build(story, onFirstPage=..., onLaterPages=_draw_header_footer)
```

### Header and footer

Page headers and footers are drawn using ReportLab's canvas callbacks rather than Platypus flowables. This ensures they appear on every page regardless of content flow:

```python
def _draw_header_footer(canvas, doc, grid_name, report_date):
    # Navy header bar with project name and grid name
    # Gray footer bar with standards references and page number
```

### Table styling

All result tables use a consistent style: navy header row, alternating gray/white body rows, medium grid lines. Pass/fail rows receive green or red background highlighting:

```python
def _color_status_row(table, row_idx, ok):
    bg = LIGHT_GREEN if ok else LIGHT_RED
    fg = GREEN if ok else RED
    table._addCommand(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
    table._addCommand(('TEXTCOLOR', (-1, row_idx), (-1, row_idx), fg))
```

---

## 10. Frontend Architecture — Grid Simulator

### State management

All application state lives in a single Zustand store (`gridStore.js`). The store has five responsibilities:

1. **React Flow state** — `nodes` and `edges` arrays managed via `applyNodeChanges` and `applyEdgeChanges`
2. **Component data** — `COMPONENT_DEFINITIONS` object defines default parameters for all 8 components
3. **Simulation state** — `simulationResult`, `timeSeriesResult`, `faultResult`, `isSimulating`, `simulationError`
4. **Payload construction** — `buildGridPayload()` converts the React Flow graph into the Grid JSON the API expects
5. **Persistence** — `saveGrid()`, `loadGrid()`, `deleteGrid()` manage browser localStorage

### Canvas node types

React Flow requires node types to be registered before use:

```javascript
const nodeTypes = {
  BUS_MV:                GridNode,
  BUS_LV:                GridNode,
  OVERHEAD_LINE:         GridNode,
  // ... all 8 types
}
```

All 8 component types use the same `GridNode` renderer, which adapts its appearance based on `node.type` and `node.data`. After simulation, `GridNode` looks up the voltage result for its bus ID and overlays it directly on the node, changing the border colour based on EN 50160 compliance.

### Edge classification

When the user draws a connection between two nodes, `onConnect` classifies the connection type and attaches component data to the edge:

```javascript
const isMvToLv = srcNode.type === 'BUS_MV' && tgtNode.type === 'BUS_LV'
const componentType = isMvToLv ? 'TRANSFORMER' : 'OVERHEAD_LINE'
const def = COMPONENT_DEFINITIONS[componentType]

return {
  ...edge,
  label: isMvToLv ? 'TX (Dyn11)' : 'OHL',
  data:  { componentType, ...def.defaultData },
}
```

This `data` object is what `buildGridPayload()` reads to classify edges into transformers, overhead lines, or underground cables when building the API payload.

### Payload construction

`buildGridPayload()` is the bridge between the React Flow graph and the backend API:

```javascript
// Nodes → buses, loads, generators
nodes.forEach(node => {
  switch (node.type) {
    case 'BUS_MV': payload.mv_buses.push({ id: node.id, ...node.data }); break
    case 'RESIDENTIAL_LOAD': payload.residential_loads.push(...); break
    // ...
  }
})

// Edges → transformers, lines, cables
edges.forEach(edge => {
  if (loadTypes.includes(tgtNode.type)) return  // skip bus→load edges
  const edgeType = isMvToLv ? 'TRANSFORMER' : edge.data?.componentType
  switch (edgeType) {
    case 'TRANSFORMER': payload.transformers.push(...); break
    case 'OVERHEAD_LINE': payload.overhead_lines.push(...); break
    // ...
  }
})
```

Bus-to-load and bus-to-generator connections are filtered out — they exist only to set the `bus_id` on the load/generator node data, not to create a physical element in the network.

---

## 11. Key Engineering Decisions — Grid Simulator

### Why not build a power flow solver from scratch?

Power flow mathematics is deceptively easy to get approximately right and extremely difficult to get precisely correct. The per-unit system, slack bus handling, Ybus construction for three-phase unbalanced networks, and convergence criteria for ill-conditioned systems all have subtleties that take years of specialised study to implement properly. A from-scratch solver built in a portfolio timeframe would produce numbers that look plausible but are wrong in ways that are difficult to detect without reference cases. OpenDSS has been validated against thousands of test cases over two decades. Using it means the results are trustworthy.

### Why EU/IEC standards and not US/IEEE?

The IEEE 13-bus and 34-bus test feeders (US standards, 12.47 kV / 4.16 kV) are the most common examples in OpenDSS documentation and tutorials. Choosing EU/IEC standards (11 kV / 0.4 kV, IEC conductor specifications, EN 50160 voltage limits) required additional research but produces a more distinctive project. It also demonstrates awareness that power systems engineering practice varies significantly between regions.

### Why Dyn11 transformer vector group?

Dyn11 (Delta primary, Star with neutral secondary, 30° phase shift) is the dominant vector group for 11 kV / 0.4 kV distribution transformers across Europe. It provides:
- A solidly earthed neutral on the LV side (required for single-phase loads)
- Zero-sequence current isolation between MV and LV networks
- Third harmonic suppression on the MV side (delta winding)

Omitting the vector group from the transformer model would cause incorrect zero-sequence current flow in fault analysis.

### Why manual multiplier injection for time-series?

OpenDSS LoadShape objects in daily mode (`Mode=1`) are the intended approach for time-series simulation. However, during development it was found that reading per-step results during a stepped daily solve was unreliable — the LoadShape multipliers were not consistently applied when advancing through steps manually. The manual multiplier injection approach (updating `kW`, `kVAR`, and `irradiance` directly before each snapshot solve) is more verbose but produces deterministically correct results for every time step.

### Why separate BusPrimary and BusSecondary classes?

A single `Bus` class with a `voltage_kv` field would work technically, but would require the translator to infer voltage levels at runtime. Separate classes make the data model self-documenting and allow Pydantic validators to enforce topology rules (e.g., transformers must connect MV to LV, not LV to LV) at validation time rather than at translation time.

---

## 12. Validation and Correctness

### Voltage base validation

The most common source of incorrect results in OpenDSS is wrong voltage base assignment. The translator always emits:

```
Set VoltageBases=[11, 0.4]
CalcVoltageBases
```

after all component definitions. `CalcVoltageBases` propagates the declared base voltages through transformers to every bus in the network. Without this, per-unit calculations are meaningless.

### Known correct results

The simple test network (MV Bus → OHL → MV Bus → TX → LV Bus → Residential Load + Solar PV) produces these verified results:

| Bus | Expected (pu) | Actual (pu) | Status |
|-----|--------------|-------------|--------|
| MV Bus (source) | 1.000 | 1.000 | ✓ |
| MV Bus (load end) | ~1.000 | 1.000 | ✓ |
| LV Bus | ~1.002 | 1.0023 | ✓ |

The slight LV voltage rise (0.23%) is physically correct — 100 kW of solar generation feeding 5 kW of load produces 95 kW of reverse power flow through the transformer, which raises the LV bus voltage.

### Fault current validation

For the same simple network, MV bus fault current:

```
Z1 = 0.01467 + j0.07043 Ω  →  |Z1| = 0.07194 Ω
V_LN = 11/√3 = 6.3509 kV
I_3ph = 6350.9 / 0.07194 = 88,274 A = 88.3 kA  ✓
```

This is consistent with a typical strong grid connection with low source impedance at the MV level.

### Time-series validation

Summer simulation energy totals for 100 kW PV panel:
- Total PV energy: ~665 kWh/day
- This implies an average output of ~27.7 kW over 24 hours, or ~66.5% of peak rating
- Capacity factor of 66.5% over the daylight-only hours (~13.5 hours) = 665 / (100 × 13.5) = 49% of peak during daylight
- This is consistent with published clear-sky day capacity factors for Romania in summer

---

## 13. SCADA/HMI Module Architecture

The SCADA module (`backend/scada/`) is a self-contained package added alongside the existing backend code. It is registered in `main.py` via:

```python
app.include_router(scada_router)
```

and started/stopped via the FastAPI lifespan context manager:

```python
@asynccontextmanager
async def lifespan(app):
    use_opendss = os.environ.get("USE_OPENDSS", "false").lower() == "true"
    _manager, _state, _loop = init_scada(use_opendss=use_opendss)
    _state.history_store.open()
    _loop.start()
    yield
    _loop.stop()
    _state.history_store.close()
```

### Module components

| Class | File | Responsibility |
|-------|------|----------------|
| `DataSource` | `data_source.py` | Abstract interface — one method: `get_measurements()` |
| `SyntheticDataSource` | `data_source.py` | Generates measurements mathematically from time-of-day profiles |
| `OpenDSSDataSource` | `data_source.py` | Runs real power flow; builds DSS script from breaker states |
| `ScadaState` | `simulation_loop.py` | Mutable session state: breaker positions, last measurements, alarm engine, event log, history store |
| `ConnectionManager` | `simulation_loop.py` | Tracks WebSocket connections, broadcasts packets |
| `SimulationLoop` | `simulation_loop.py` | asyncio background task, runs every 5 seconds |
| `AlarmEngine` | `alarm_engine.py` | Threshold evaluation, alarm lifecycle management |
| `EventLog` | `event_log.py` | Ring buffer of timestamped events (500 entries) |
| `HistoryStore` | `history_store.py` | SQLite persistence for trend data |

### Why asyncio instead of a thread?

The simulation loop runs as an `asyncio.Task` (not a thread) because FastAPI/uvicorn is built on asyncio. Running the loop in the same event loop as the WebSocket handlers means broadcasts are non-blocking and there is no need for thread-safe locks around the shared `ScadaState`. The loop calls `await asyncio.sleep(interval)` between ticks, yielding control to the event loop so WebSocket messages and REST requests are handled normally between ticks.

---

## 14. SCADA Data Sources

### DataSource abstraction

```python
class DataSource(ABC):
    @abstractmethod
    def get_measurements(self, breaker_states: Dict[str, str]) -> ScadaMeasurements:
        ...
```

All SCADA backend code interacts only with this interface. The concrete implementation is chosen at startup via `USE_OPENDSS` and injected into `SimulationLoop`.

### SyntheticDataSource

Generates physically plausible measurements without OpenDSS:

- **Voltage profile:** composite sinusoidal function of time-of-day, modelling morning load dip (~08:00), solar support midday (~14:00), and evening peak (~19:00), plus ±0.003 pu random noise per tick
- **Load factor:** sinusoidal daily curve (peak at ~09:00 and ~19:00, minimum at ~03:00)
- **Energisation logic:** mirrors the backend interlock rules — open breakers cause downstream buses to read 0.0 pu, which triggers DE_ENERGISED alarms

### OpenDSSDataSource

Builds a complete DSS script for the fixed substation topology on every call to `get_measurements()`. Breaker states are modelled as OpenDSS Line switch elements — closed breakers use near-zero impedance, open breakers are disabled (`enabled=n`). Commands are issued one line at a time via `dss.Text.Command()`. If the power flow fails to converge, `OpenDSSDataSource` returns zero measurements rather than crashing the simulation loop.

---

## 15. SCADA Alarm Engine

### Alarm lifecycle

```
Condition detected on tick N
        │
        ▼
ACTIVE alarm created (raised_at = now)
Logged to EventLog
        │
        ▼ (operator clicks ACK)
ACKNOWLEDGED (acked_at = now)
Logged to EventLog
        │
        ▼ (condition clears on tick M)
CLEARED (cleared_at = now)
Logged to EventLog
Removed from active alarm dict
```

Acknowledging an alarm does not clear it. Clearing happens automatically when the measurement returns to within limits.

### Alarm IDs

Alarm IDs are deterministic: `ALM-{element_id}-{condition_id}` (e.g. `ALM-BUS_A-VOLT_HIGH`). This means the frontend can always correlate the same alarm across multiple WebSocket packets without a UUID lookup table.

### Threshold evaluation

Every tick, the engine evaluates all thresholds against all elements. If a condition is newly active and no alarm exists for that ID, a new alarm is created. If a condition is no longer active and an alarm exists, it is cleared. The engine never duplicates alarms — re-evaluation of an already-active alarm only updates the message.

---

## 16. SCADA WebSocket Protocol

### Connection lifecycle

1. Client connects to `ws://localhost:8000/scada/ws`
2. Backend registers client with `ConnectionManager`
3. Backend immediately sends the latest measurement snapshot so the UI is not blank
4. Backend broadcasts a new packet on every simulation tick (every 5 seconds)
5. Client may send control messages at any time between ticks
6. On disconnect, backend removes client from `ConnectionManager`

### Packet format (backend → client)

```json
{
  "type": "state_update",
  "timestamp": "2026-07-27T18:23:01.234567+00:00",
  "breaker_states": { "CB1": "CLOSED", "CB3": "OPEN" },
  "buses": {
    "BUS_A": { "voltage_kv": 11.023, "voltage_pu": 1.0021, "voltage_nom": 11.0 }
  },
  "branches": {
    "FEEDER1": { "current_a": 45.2, "ampacity_a": 200.0, "loading_pct": 22.6, "power_kw": 380.1, "power_kvar": 120.3 }
  },
  "transformers": {
    "TX1": { "primary_kv": 11.0, "secondary_kv": 0.4, "current_a": 18.1, "rated_kva": 630.0, "loading_pct": 34.2, "power_kw": 212.0, "power_kvar": 65.0 }
  },
  "alarms": [
    {
      "id": "ALM-BUS_A-VOLT_HIGH",
      "priority": "MEDIUM",
      "state": "ACTIVE",
      "element": "BUS_A",
      "condition": "VOLT_HIGH",
      "message": "BUS_A voltage 1.0723 pu exceeds warning high limit (1.06 pu / EN 50160)",
      "raised_at": "2026-07-27T18:21:03.000000+00:00",
      "acked_at": null,
      "cleared_at": null
    }
  ]
}
```

### Control messages (client → backend)

```json
{ "type": "breaker_command", "breaker_id": "CB3", "command": "OPEN" }
{ "type": "alarm_ack",       "alarm_id":   "ALM-BUS_A-VOLT_HIGH" }
```

On receiving a `breaker_command`, the backend applies the state change, logs the operation, re-runs measurements immediately, re-evaluates alarms, and broadcasts the updated packet to all connected clients.

---

## 17. SCADA History Store

### Database location

`backend/scada/scada_history.db` — created automatically on first startup.

### Write rate and storage estimate

At 5-second intervals with 4 buses, 2 transformers, and 3 branches: approximately 9 rows per tick × 12 ticks per minute × 60 minutes × 24 hours × 7 days = ~1.09 million rows per week. At roughly 100 bytes per row this is approximately 109 MB for a full 7-day retention window.

### Downsampling

Query responses are downsampled before being sent to the frontend:

| Window | Minimum interval between points | Max points per series |
|--------|--------------------------------|----------------------|
| 1h | 10 seconds | ~360 |
| 6h | 30 seconds | ~720 |
| 24h | 2 minutes | ~720 |
| 7d | 10 minutes | ~1008 |

### WAL mode

The database is opened with `PRAGMA journal_mode=WAL` (Write-Ahead Logging). WAL allows concurrent readers during writes, which matters because the simulation loop writes every 5 seconds while the REST endpoints may be reading simultaneously.

---

## 18. SCADA Frontend Architecture

### Component tree

```
ScadaApp.jsx (route: /scada)
├── SingleLineDiagram.jsx     — SVG, reads from scadaStore
│   ├── SldElements.jsx       — reusable SVG primitives
│   └── (onClick → dialog)
├── BreakerControlDialog.jsx  — modal, evaluates interlocks
│   └── interlock_engine.js   — pure functions, no React state
├── AlarmPanel.jsx            — active + acknowledged alarms
├── Section (collapsible)
│   ├── BusesTable
│   └── TransformersTable
├── HistoricalTrends.jsx      — tabbed chart panel
│   └── TrendChart.jsx        — Recharts wrapper
└── EventLog.jsx              — REST-polled event table
```

### Two Zustand stores

`gridStore.js` — Grid Simulator state (nodes, edges, simulation results). Completely independent of SCADA.

`scadaStore.js` — SCADA state: WebSocket status, live measurements, breaker states, alarms. The WebSocket hook (`useWebSocket.js`) writes into this store on every incoming packet; all components read from it.

### Interlock engine design

`interlock_engine.js` is a pure JavaScript module with no React dependencies. It exports `evaluateOperation(breakerId, command, breakerStates)` which returns `{ outcome, findings }`. The module mirrors the backend energisation logic exactly — both use the same topology rules.

Running interlock evaluation on the frontend means operators see the interlock result immediately on hover, without a round trip. The backend still enforces correctness — the frontend prevents the command from being sent in the first place.

---

## 19. Key Engineering Decisions — SCADA

### Why not proxy the SCADA WebSocket through Vite?

Vite's proxy does support WebSocket (`ws: true`). However, during development the WebSocket connection is more reliable when pointed directly at `ws://localhost:8000/scada/ws` rather than routing through the proxy. The proxy was retained in `vite.config.js` for completeness but the hook uses the direct URL.

### Why SQLite for history instead of a time-series database?

InfluxDB and TimescaleDB are excellent but require separate installation and configuration. SQLite is a single file, requires no server, and is bundled with Python. For a 7-day retention window at 5-second intervals, SQLite with WAL mode and appropriate indexes handles the write rate comfortably. The `HistoryStore` class abstracts the storage layer, so replacing SQLite with a proper TSDB in a production deployment would only require implementing a new class behind the same interface.

### Why SVG instead of React Flow for the SCADA diagram?

SCADA single-line diagrams have fixed layouts that operators memorise. The diagram is not user-editable. React Flow is designed for interactive node editors where the user controls layout — it would add unnecessary complexity and fight against the fixed-layout requirement. Raw SVG with React state overlaid gives complete control over symbol placement, line routing, and IEC 60617 symbol shapes.

### Why synthetic data by default?

The synthetic data source allows the entire SCADA stack — WebSocket, alarm engine, event log, history store, trend charts — to be developed and tested independently of OpenDSS. This means a developer without opendssdirect installed can still run and understand the SCADA module. OpenDSS mode is opt-in via environment variable.

### Why is the SCADA topology fixed?

Real SCADA systems are always configured for a specific fixed substation — operators need to memorise the layout. Making the topology dynamic (user-editable like Grid Simulator) would require auto-layout of SVG diagrams, dynamic interlock rule generation, and a topology editor that duplicates Grid Simulator's functionality. The fixed topology approach correctly represents how production SCADA systems work and keeps the complexity in the right places: data flow, alarm management, and interlock logic.
