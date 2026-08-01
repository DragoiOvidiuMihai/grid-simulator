# User Guide — Grid Simulator & SCADA/HMI

## Table of Contents

1. [What is Grid Simulator?](#1-what-is-grid-simulator)
2. [What is the SCADA/HMI Module?](#2-what-is-the-scadahmi-module)
3. [Installation](#3-installation)
4. [Starting the Application](#4-starting-the-application)
5. [Grid Simulator — Interface Overview](#5-grid-simulator--interface-overview)
6. [Component Library](#6-component-library)
7. [Building a Circuit — Rules and Best Practices](#7-building-a-circuit--rules-and-best-practices)
8. [Simulation Modes](#8-simulation-modes)
9. [Reading Your Results](#9-reading-your-results)
10. [Saving and Loading Grids](#10-saving-and-loading-grids)
11. [Exporting PDF Reports](#11-exporting-pdf-reports)
12. [Common Mistakes and Fixes](#12-common-mistakes-and-fixes)
13. [Grid Simulator — Worked Example](#13-grid-simulator--worked-example)
14. [SCADA/HMI — Interface Overview](#14-scadahmi--interface-overview)
15. [SCADA — Reading the Single-Line Diagram](#15-scada--reading-the-single-line-diagram)
16. [SCADA — Breaker Control and Interlocks](#16-scada--breaker-control-and-interlocks)
17. [SCADA — Alarm Management](#17-scada--alarm-management)
18. [SCADA — Historical Trends](#18-scada--historical-trends)
19. [SCADA — Event Log](#19-scada--event-log)
20. [SCADA — Switching Sequences](#20-scada--switching-sequences)

---

## 1. What is Grid Simulator?

Grid Simulator is an interactive web application for building and analysing electrical distribution networks. It allows you to:

- Draw a single-line diagram of a distribution network using drag-and-drop components
- Run an **AC power flow** to see voltages, currents, and losses at steady state
- Run a **24-hour time-series simulation** to see how voltage and solar generation vary across a full day
- Run a **fault study** to calculate short-circuit currents at every bus
- Export professional **PDF reports** of any simulation result
- **Save and load** network configurations by name

The simulation engine is **OpenDSS** — the same professional-grade solver used by utilities and research institutions worldwide. Grid Simulator wraps it in a friendlier interface without sacrificing engineering accuracy.

All components, parameters, and results follow **EU/IEC standards** (EN 50160, IEC 61089, IEC 60502-2, IEC 60228, EN 50182).

---

## 2. What is the SCADA/HMI Module?

SCADA (Supervisory Control and Data Acquisition) is the software layer that monitors and controls industrial processes — power plants, substations, water treatment facilities. The HMI (Human-Machine Interface) is the visual layer that the operator looks at.

The SCADA/HMI module is a separate application accessible at `/scada` that provides a real-time operator interface for a fixed 11kV/0.4kV substation. Unlike Grid Simulator (where you build your own network), the SCADA module uses a fixed pre-defined substation topology and focuses on live monitoring and control.

The SCADA module demonstrates concepts that are distinct from power flow analysis: real-time data streaming via WebSocket, alarm management with acknowledgement workflow, breaker interlock logic, timestamped event logging, and historical trend analysis.

**Substation topology:**
```
  Feeder 1 (11kV)         Feeder 2 (11kV)
       │                        │
      CB1                      CB2
       │                        │
    Bus A ────── CB3 ────── Bus B     (11kV busbars, CB3 = bus coupler)
       │                        │
      CB4                      CB5
       │                        │
      TX1  (630 kVA)           TX2  (630 kVA)
       │                        │
    Bus C                    Bus D     (0.4kV busbars)
    /    \                   /    \
  CB6   CB7               CB8   CB9
   │      │                 │      │
 Load1   PV1             Load2  Load3
```

---

## 3. Installation

### Requirements

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.11 or newer | https://www.python.org/downloads/ |
| Node.js | 18 or newer | https://nodejs.org |
| Git | Any recent version | https://git-scm.com |

### Clone the repository

```bash
git clone https://github.com/DragoiOvidiuMihai/grid-simulator.git
cd grid-simulator
```

### Backend setup

```bash
# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate

# Install Python dependencies
pip install fastapi "uvicorn[standard]" opendssdirect.py pydantic reportlab
```

> **Important:** Install `uvicorn[standard]` (with the brackets), not just `uvicorn`. The standard extras include the `websockets` library required by the SCADA WebSocket endpoint. If you install plain `uvicorn`, the SCADA screen will show OFFLINE.

### Frontend setup

```bash
cd frontend
npm install
cd ..
```

---

## 4. Starting the Application

Open two terminals from the project root directory.

**Terminal 1 — Backend:**

```bash
# Activate the virtual environment first
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

# Start with synthetic data (default — no OpenDSS required for SCADA)
uvicorn backend.api.main:app --reload --port 8000

# OR start with OpenDSS real power flow for SCADA
# Windows PowerShell:
$env:USE_OPENDSS = "true"
uvicorn backend.api.main:app --reload --port 8000

# Mac / Linux:
USE_OPENDSS=true uvicorn backend.api.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Open your browser:
- **Grid Simulator:** http://localhost:5173
- **SCADA/HMI:** http://localhost:5173/scada

The backend API documentation is available at http://localhost:8000/docs.

---

## 5. Grid Simulator — Interface Overview

The Grid Simulator interface has five areas:

**Left sidebar — Component library**
Drag components from here onto the canvas. Components are grouped by type: buses, lines, cables, transformers, loads, generators.

**Centre — Canvas**
The working area where you build your network. Pan with middle mouse button or spacebar + drag. Zoom with the scroll wheel.

**Right — Properties panel**
Shows editable parameters for the selected node or edge. Click any component on the canvas to select it and edit its parameters here.

**Bottom — Results panel**
Appears after a successful simulation. Shows bus voltages, line currents, losses, and generator outputs. Tabs switch between snapshot, time-series, and fault study results.

**Top bar — Simulation controls**
Mode selector (Snapshot / Time-Series / Fault Study), Run button, Save/Load panel, Export PDF button.

---

## 6. Component Library

| Component | Icon | Parameters |
|-----------|------|-----------|
| MV Bus | Rectangle (11kV) | Name only — voltage is fixed at 11 kV |
| LV Bus | Rectangle (0.4kV) | Name only — voltage is fixed at 0.4 kV |
| Transformer | Two circles | kVA rating, HV/LV voltages, %R, %X |
| Overhead Line | Dashed line | Length (km), conductor type |
| Underground Cable | Solid line | Length (km), conductor type |
| Residential Load | House symbol | Peak kW, power factor |
| Industrial Load | Factory symbol | Peak kW, power factor |
| Synchronous Generator | Circle with G | kW rating, voltage, power factor |
| Solar PV | Sun symbol | Peak kW (STC rating) |

---

## 7. Building a Circuit — Rules and Best Practices

### Connection rules

**Buses must be connected first.** Components connect between buses, not directly to each other. A transformer must have an MV bus on its primary side and an LV bus on its secondary side. A line connects two buses of the same voltage level.

**Voltage levels must match.** If you connect a load with `base_kv = 11.0` to a 0.4 kV bus, OpenDSS will create a phantom bus at 11 kV and the result will be meaningless. Always set load and generator voltage to match the bus they connect to.

**Every network needs a slack bus.** The power flow needs at least one voltage source (generator or external grid equivalent) to act as a reference. A network with only loads and no generators will not converge.

**Connections are directional.** Draw edges from source to destination: Bus → Transformer, Bus → Line → Bus, Bus → Load. The arrow direction matters for the DSS translator.

### Best practices

Start simple — two buses, one transformer, one load. Verify it converges before adding more components. Add components one at a time. If the simulation stops converging after adding a component, that component is the likely cause.

Use the `/preview-dss` endpoint (accessible via the API docs at http://localhost:8000/docs) to inspect the DSS script before solving. This is the fastest way to diagnose translator issues.

---

## 8. Simulation Modes

### Snapshot — AC Power Flow

Solves a single steady-state AC power flow. Use this to check voltages and currents at a specific operating point.

**Controls:**
- Select **Snapshot** mode in the top bar
- Click **Run Simulation**
- Results appear in the bottom panel within seconds

**What you get:**
- Bus voltage in kV and per-unit, with EN 50160 compliance flag
- Line/cable current in Amperes and as a percentage of ampacity
- Transformer and line losses in kW
- Generator active and reactive output

### Time-Series — 24-Hour Daily Simulation

Runs 48 power flow snapshots (one per 30 minutes) using built-in Romanian daily profiles. Use this to see how voltage varies through the day, when solar generation peaks, and whether any bus violates EN 50160 limits during peak load periods.

**Controls:**
- Select **Time-Series** mode
- Choose **Season** (Summer / Winter) — affects the solar irradiance profile
- Set **Peak Load Multiplier** (default 1.0) — scale the load up or down
- Click **Run Simulation**

**What you get:**
- Voltage profile charts for each bus across 24 hours
- EN 50160 violation count per bus (number of 30-minute steps outside ±10%)
- Total daily energy generated and total losses
- Hour-by-hour PV generation output

### Fault Study — Short-Circuit Analysis

Calculates fault currents at every bus. Use this to size protection equipment and set relay thresholds.

**Controls:**
- Select **Fault Study** mode
- Click **Run Simulation**

**What you get:**
- Three-phase fault current (kA) at every bus
- Single line-to-ground fault current (kA) at every bus
- Thevenin impedance Z1 and Z0 (Ω)
- X/R ratio for each bus (important for relay coordination)

---

## 9. Reading Your Results

### Voltage colours

| Colour | Meaning |
|--------|---------|
| Green | Within EN 50160 limits (0.90–1.10 pu) |
| Amber | Approaching limits (0.94–0.90 pu or 1.06–1.10 pu) |
| Red | Outside EN 50160 limits (< 0.90 pu or > 1.10 pu) |

### Current percentages

Line and cable currents are shown as a percentage of their rated ampacity. Above 100% means the conductor is overloaded. Above 70% is a warning — the conductor is approaching its thermal limit.

### Per-unit voltage

Per-unit (pu) voltage is the bus voltage divided by the nominal voltage. 1.0 pu = exactly nominal. 0.95 pu = 5% below nominal. This makes it easy to compare buses at different voltage levels — a 0.95 pu result means the same thing whether the bus is 11 kV or 0.4 kV.

---

## 10. Saving and Loading Grids

Click **Save** in the top bar, enter a name, and click confirm. The grid is saved to browser localStorage.

Click **Load** to see a list of saved grids. Click a name to load it. The canvas will be populated with the saved components and connections.

> **Note:** Saved grids are stored in your browser's localStorage. They do not transfer to other browsers or computers. To back up a grid, use your browser's developer tools to export localStorage, or take a screenshot of the canvas.

---

## 11. Exporting PDF Reports

After running any simulation, click **Export PDF** in the top bar. The backend generates a PDF report and your browser downloads it automatically.

The PDF includes: grid name, simulation mode, all result tables with colour coding, EN 50160 compliance summary, and a timestamp. It is formatted for engineering use and can be included in technical reports.

---

## 12. Common Mistakes and Fixes

**Simulation returns "did not converge"**
Most common cause: a load or generator has a `base_kv` that doesn't match the bus it's connected to. Check that every load's voltage setting matches the bus voltage. Use `/preview-dss` to inspect the script.

**Bus voltages look wrong (very high or very low)**
Check that `CalcVoltageBases` is being called. This happens automatically, but if the network has disconnected sections OpenDSS may not propagate voltage bases correctly. Ensure every bus is reachable from the slack bus through closed switches.

**Lines show 0% loading even though loads are connected**
The load is likely disconnected from the bus — the edge was drawn but not connected to a bus terminal. Delete and redraw the connection.

**SCADA shows OFFLINE**
The backend is not running, or `uvicorn` was installed without the standard extras. Stop the backend, run `pip install "uvicorn[standard]"`, and restart.

**SCADA Event Log shows "Failed to load events"**
The `/scada/events` proxy route is missing from `vite.config.js`. Add `'/scada/events': 'http://localhost:8000'` to the proxy section and save.

---

## 13. Grid Simulator — Worked Example

This example builds a simple 11kV/0.4kV radial network and runs all three simulation modes.

**Step 1:** Drag an **MV Bus** onto the canvas. Name it `BUS_HV`.

**Step 2:** Drag a **Synchronous Generator** and connect it to `BUS_HV`. Set: kW = 500, kV = 11, PF = 0.95. This is the slack bus.

**Step 3:** Drag an **LV Bus** onto the canvas. Name it `BUS_LV`.

**Step 4:** Drag a **Transformer** and connect: primary to `BUS_HV`, secondary to `BUS_LV`. Set: kVA = 500, HV = 11 kV, LV = 0.4 kV.

**Step 5:** Drag an **Industrial Load** and connect it to `BUS_LV`. Set: kW = 200, kV = 0.4, PF = 0.90.

**Step 6:** Drag a **Solar PV** and connect it to `BUS_LV`. Set: kW = 50.

**Step 7:** Click **Run Simulation** in Snapshot mode. You should see `BUS_HV` at approximately 1.0 pu and `BUS_LV` slightly below 1.0 pu due to transformer impedance drop.

**Step 8:** Switch to Time-Series mode, select Summer, click Run. The BUS_LV voltage chart will show a dip during morning peak load and a rise midday when the PV generation peaks.

**Step 9:** Switch to Fault Study mode, click Run. The three-phase fault current at BUS_LV will be approximately I_k3 = V_n / (√3 × |Z_T|) where Z_T is the transformer impedance referred to the LV side.

**Step 10:** Click Export PDF to download the fault study report.

---

## 14. SCADA/HMI — Interface Overview

Open http://localhost:5173/scada. The SCADA screen has four main areas:

**Top bar**
Left side: navigation back to Grid Simulator, module title. Right side: alarm count badge (red and flashing if unacknowledged alarms exist, green if clear), last update timestamp, connection status badge (ONLINE / CONNECTING / OFFLINE / ERROR), data source badge (SYNTHETIC or OPENDSS).

**Single-Line Diagram**
The main visual display. Shows the substation topology with live colour-coding. All measurements update every 5 seconds.

**Alarm Panel**
Below the diagram. Shows active and acknowledged alarms. Unacknowledged alarms have a flashing priority dot and an ACK button.

**Measurement Tables, Trends, and Event Log**
Collapsible sections below the alarm panel. Bus voltages, transformer loading, branch currents, breaker states, historical trend charts, and timestamped event log.

---

## 15. SCADA — Reading the Single-Line Diagram

### Colour meaning

| Colour | Meaning |
|--------|---------|
| Green | Energised, all measurements within normal limits |
| Amber | Energised, but a measurement is approaching a warning threshold |
| Red | Alarm active, or equipment is de-energised |
| Grey | Open breaker or de-energised conductor/equipment |

### Reading the measurements

Floating measurement tags appear next to each element:

- **Busbars:** voltage in kV and per-unit (coloured green/amber/red by EN 50160 limits)
- **Feeders (top of diagram):** current in Amperes below the feeder arrow
- **Transformers:** loading percentage and active/reactive power (P/Q) in kW and kvar
- **LV busbars:** voltage in kV

### Breaker symbols

Breakers are shown as small squares on the conductor lines. A filled green square means CLOSED (current can flow). A hollow grey square means OPEN (circuit is interrupted).

The bus coupler CB3 (between Bus A and Bus B) starts OPEN by default — this is the normal operating configuration. Each feeder supplies its own half of the substation independently.

---

## 16. SCADA — Breaker Control and Interlocks

### Opening or closing a breaker

Click any breaker square on the single-line diagram. A control dialog opens showing:
- The breaker ID and description
- Current state (OPEN or CLOSED)
- OPEN and CLOSE action buttons

### Two-step confirmation

To prevent accidental operations, every switching action requires two clicks:
1. Click OPEN or CLOSE to see the interlock evaluation and propose the operation
2. Click **Confirm** to send the command

Clicking Cancel or the backdrop dismisses the dialog without any action.

### Interlock results

Before you click Confirm, the dialog shows the interlock evaluation result:

**✓ PERMITTED** — no issues. The operation can proceed safely.

**⚠ WARNING** — the operation is allowed but has consequences you should be aware of (for example, closing the coupler after a feeder loss). The warning message explains the situation. You can still confirm.

**✕ BLOCKED** — the operation is refused. The CLOSE button is red and shows INTERLOCKED. The reason is shown in the interlock panel. You cannot proceed until the blocking condition is resolved.

### Interlock rules

| Rule | Condition | Outcome |
|------|-----------|---------|
| No parallel sources | CB3 CLOSE when both CB1 and CB2 are CLOSED | BLOCKED — would parallel two independent 11kV sources |
| Coupler recovery | CB3 CLOSE when one feeder is open | WARNING — correct recovery action, operator confirmation required |
| Dead bus close | CLOSE any breaker when upstream bus is de-energised | BLOCKED — cannot energise from a dead upstream |
| Last source warning | OPEN a breaker that would de-energise a live load bus | WARNING — loads will lose supply |
| TX isolator sequence | OPEN CB4 or CB5 when the LV bus is live | WARNING — LV feeders should be opened first |

### Effect of switching

When you confirm a breaker operation:
1. The command is sent to the backend via WebSocket
2. The backend applies the new breaker state and re-runs the power flow immediately
3. The updated measurements are broadcast to the frontend
4. The diagram redraws with new colours within one second
5. The event log records the operation with a timestamp

---

## 17. SCADA — Alarm Management

### How alarms appear

When a measurement crosses a threshold, an alarm appears in the Alarm Panel below the diagram. Simultaneously:
- The top bar alarm badge switches from green to red and starts flashing
- The affected element on the single-line diagram changes colour (amber for warning, red for critical)
- The alarm count in the top bar increments

### Alarm priority

| Priority | Colour | Typical conditions |
|----------|--------|-------------------|
| HIGH | Red, flashing dot | Voltage outside ±10%, transformer above 90% loading, bus de-energised |
| MEDIUM | Amber | Voltage between ±6% and ±10%, transformer between 70% and 90% loading |

### Acknowledging an alarm

Click the **ACK** button on an active alarm. This:
- Moves the alarm from the Unacknowledged section to the Acknowledged section
- Stops the flashing dot
- Records an acknowledgement event in the event log with a timestamp

Acknowledging does not clear the alarm. The alarm stays in the Acknowledged section until the underlying measurement returns to normal.

### Automatic clearing

When the measurement returns within limits, the alarm disappears from the panel automatically. A CLEARED event is recorded in the event log. If the condition returns, a new alarm is raised.

### Testing alarms

To trigger a test alarm: click CB1 and open it. Bus A loses supply, Bus C loses supply, and two HIGH priority alarms appear immediately — one for Bus A de-energised and one for Bus C de-energised. The top bar shows ⚠ 2 ALARMS. To clear: click CB1 and close it. Both alarms clear automatically.

---

## 18. SCADA — Historical Trends

The Historical Trends panel shows how measurements have changed over time. It is located below the measurement tables.

### Three chart tabs

**Bus Voltage (pu)** — shows all four buses (BUS_A, BUS_B, BUS_C, BUS_D) as separate coloured lines. Reference lines at ±6% (amber) and ±10% (red) from EN 50160 are overlaid.

**TX Loading (%)** — shows TX1 and TX2 transformer loading percentage over time. Reference lines at 70% (amber) and 90% (red) from IEC 60076-1 are overlaid.

**Branch Loading (%)** — shows FEEDER1, FEEDER2, and COUPLER current loading percentage over time.

### Time windows

Select the time window using the buttons in the top right of the panel: **1h**, **6h**, **24h**, **7d**. The chart automatically adjusts the time axis format and downsamples data to keep the number of points manageable.

### Data availability

The history database starts empty when the backend first runs. The 1h window will show data after approximately 1 minute of operation. The 24h window fills over 24 hours of continuous operation. The 7d window shows up to 7 days of history.

The chart shows "No data yet — collecting history..." if no data is available for the selected window. This is normal on first run.

---

## 19. SCADA — Event Log

The Event Log is at the bottom of the SCADA page. It shows a chronological record of everything that has happened, newest first.

### Event types

| Type label | Colour | When it appears |
|-----------|--------|----------------|
| ALARM | Red | An alarm threshold was crossed |
| ACK | Amber | An operator acknowledged an alarm |
| CLEARED | Green (dim) | An alarm condition resolved automatically |
| OPERATOR | Blue | A breaker was opened or closed |
| SYSTEM | Grey | System startup or other infrastructure events |

### Filtering

Use the filter buttons in the top right of the panel to show only specific event types: **All**, **Alarms**, **Operator**, **System**.

### Refreshing

The event log polls the backend every 10 seconds automatically. Click the **↺** button to refresh immediately.

### Post-incident analysis

After a switching operation or alarm event, the event log is the first place to look. A typical sequence after a feeder loss and coupler closing would appear as:

```
18:21:03  ALARM    BUS_A    ALARM: BUS_A is de-energised (voltage = 0)
18:21:03  ALARM    BUS_C    ALARM: BUS_C is de-energised (voltage = 0)
18:21:08  OPERATOR CB1      Operator operated CB1 → OPEN
18:21:45  OPERATOR CB3      Operator operated CB3 → CLOSED
18:21:45  CLEARED  BUS_A    Alarm condition cleared: ALM-BUS_A-DE_ENERGISED
18:21:45  CLEARED  BUS_C    Alarm condition cleared: ALM-BUS_C-DE_ENERGISED
18:22:10  ACK      BUS_A    Operator acknowledged alarm ALM-BUS_A-DE_ENERGISED
```

---

## 20. SCADA — Switching Sequences

These are the correct switching sequences for common operations. Following the correct sequence avoids interlock blocks and is consistent with real substation practice.

### Normal to coupler backup (one feeder lost)

**Situation:** CB2 has tripped. Bus B and Bus D are de-energised.

1. Confirm CB2 is OPEN (it should be — it tripped)
2. Click CB3 → CLOSE → the interlock will show WARNING (coupler recovery, correct action) → Confirm
3. Bus B and Bus D re-energise from Feeder 1 via the coupler
4. Acknowledge the Bus B / Bus D de-energised alarms

### Return to normal (feeder restored)

**Situation:** Feeder 2 has been restored. CB2 is ready to close. The coupler CB3 is currently CLOSED.

1. Click CB3 → OPEN → Confirm (this removes the parallel path)
2. Click CB2 → CLOSE → Confirm
3. Bus B and Bus D are now fed by Feeder 2 again
4. The system is back to normal configuration

### Isolating a transformer for maintenance

**Situation:** TX1 needs to be taken out of service.

1. Click CB6 → OPEN → Confirm (isolate Load 1)
2. Click CB7 → OPEN → Confirm (isolate PV 1)
3. Click CB4 → OPEN → Confirm (the interlock will ALLOW since LV feeders are already open)
4. TX1 is now de-energised and isolated on both sides

### Restoring a transformer after maintenance

1. Click CB4 → CLOSE → Confirm (Bus C energises via TX1)
2. Click CB6 → CLOSE → Confirm (Load 1 energises)
3. Click CB7 → CLOSE → Confirm (PV 1 energises)
