# User Guide — Grid Simulator

## Table of Contents

1. [What is Grid Simulator?](#1-what-is-grid-simulator)
2. [Installation](#2-installation)
3. [Starting the Application](#3-starting-the-application)
4. [Interface Overview](#4-interface-overview)
5. [Component Library](#5-component-library)
6. [Building a Circuit — Rules and Best Practices](#6-building-a-circuit--rules-and-best-practices)
7. [Simulation Modes](#7-simulation-modes)
8. [Reading Your Results](#8-reading-your-results)
9. [Saving and Loading Grids](#9-saving-and-loading-grids)
10. [Exporting PDF Reports](#10-exporting-pdf-reports)
11. [Common Mistakes and Fixes](#11-common-mistakes-and-fixes)
12. [Worked Example — Step by Step](#12-worked-example--step-by-step)

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

## 2. Installation

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
pip install fastapi uvicorn opendssdirect.py pydantic reportlab
```

### Frontend setup

```bash
cd frontend
npm install
cd ..
```

---

## 3. Starting the Application

You need **two terminal windows** running simultaneously.

### Terminal 1 — Backend

```bash
# From the project root, with venv activated
uvicorn backend.api.main:app --port 8000
```

You should see:
```
INFO: Uvicorn running on http://127.0.0.1:8000
```

### Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

You should see:
```
VITE ready in Xms
Local: http://localhost:5173/
```

Open **http://localhost:5173** in your browser. The application will load.

> Both terminals must stay open while you use the app. Closing either one stops the application.

---

## 4. Interface Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  TOP BAR — Mode toggle │ Season/Load controls │ Grid name │ Buttons │
├──────────┬──────────────────────────────────────┬───────────────────┤
│          │                                      │                   │
│ SIDEBAR  │           CANVAS                     │  PROPERTIES       │
│          │                                      │  PANEL            │
│ Component│   Drag components here.              │                   │
│ library  │   Connect them with wires.           ├───────────────────┤
│          │   Click to select and edit.          │                   │
│          │                                      │  RESULTS          │
│          │                                      │  PANEL            │
│          │                                      │                   │
└──────────┴──────────────────────────────────────┴───────────────────┘
```

**Top bar** — switch between Snapshot, Time-Series, and Fault Study modes. Run simulations, save/load grids, clear the canvas.

**Sidebar** — all 8 available components grouped by category. Drag any component onto the canvas to place it.

**Canvas** — the main drawing area. Place components, draw connections, and see simulation results overlaid directly on the diagram.

**Properties panel** — click any component on the canvas to see and edit its parameters.

**Results panel** — shows simulation output after running. Includes voltage tables, loss breakdowns, generator output, and time-series charts.

---

## 5. Component Library

Grid Simulator includes 8 components based on real EU/IEC specifications.

### Nodes

| Component | Voltage | Standard Use |
|-----------|---------|--------------|
| **MV Bus** | 11 kV | Medium voltage network node. The main connection point for generators, transformers, and MV-level lines. |
| **LV Bus** | 0.4 kV | Low voltage network node. Where residential and industrial loads connect after the transformer. |

### Connections

| Component | Standard | Use |
|-----------|----------|-----|
| **Transformer** | Dyn11, IEC | Connects an MV Bus to an LV Bus. Steps voltage down from 11 kV to 0.4 kV. Created automatically when you connect MV Bus → LV Bus. |
| **Overhead Line** | ACSR 150mm², IEC 61089 / EN 50182 | Connects two MV buses. R1 = 0.196 Ω/km. Created automatically when you connect MV Bus → MV Bus. |
| **Underground Cable** | 12/20kV XLPE 150mm² Cu, IEC 60502-2 | Alternative to overhead line for underground routing. Must be placed manually — drag from sidebar then connect. |

### Loads

| Component | Phases | Default | Notes |
|-----------|--------|---------|-------|
| **Residential Load** | 1 (single-phase) | 5 kW, PF 0.95 | Connects to LV Bus. Represents a household. |
| **Industrial Load** | 3 (three-phase) | 250 kW, PF 0.90 | Can connect to LV or MV Bus — see voltage rules below. |

### Generation

| Component | Type | Notes |
|-----------|------|-------|
| **Synchronous Generator** | Rotating machine | Diesel genset or grid connection. Set `rated_kv` to match the bus it connects to. |
| **Solar PV** | Inverter-based DER | Connects to LV Bus. Output scales with irradiance in time-series mode. |

---

## 6. Building a Circuit — Rules and Best Practices

> This section is critical. Most simulation errors come from not following these rules.

### Rule 1 — Always connect from Bus to Component, not the other way around

When connecting a load, generator, or solar PV to a bus, **drag from the bus handle downward to the component**. Do not drag from the component to the bus.

✅ Correct: drag from **MV Bus bottom handle → Generator**
❌ Wrong: drag from **Generator handle → MV Bus**

If you connect the wrong way, the component's `bus_id` will not be set and the simulation will fail or produce zero voltages.

### Rule 2 — Match component voltage to its bus

Every component has a `rated_kv` or `base_kv` parameter that must match the bus it connects to.

| Bus type | Bus voltage | Component setting required |
|----------|-------------|--------------------------|
| MV Bus | 11 kV | Generator: set `rated_kv = 11.0` |
| LV Bus | 0.4 kV | Generator: set `rated_kv = 0.4` |
| LV Bus | 0.4 kV | Industrial Load: `base_kv = 0.4` ✅ (default) |
| MV Bus | 11 kV | Industrial Load: change `base_kv = 11.0` in properties |

Mismatched voltages cause OpenDSS to create phantom buses (you will see a bus named `kv` in your results) and zero voltages on affected buses.

### Rule 3 — Every network needs a voltage source

OpenDSS needs a reference voltage to solve from. The application provides a built-in grid source at the first MV Bus you place. This means:

- Your network must contain at least one **MV Bus**
- The first MV Bus you place acts as the slack bus (voltage reference)
- Everything else in the network is powered from this reference

### Rule 4 — Connection types are determined automatically

You do not need to drag Transformer or Overhead Line from the sidebar to create connections between buses. The type is determined automatically:

- **MV Bus → LV Bus** = Transformer (Dyn11, 500 kVA)
- **MV Bus → MV Bus** = Overhead Line (ACSR 150mm², 1 km)
- **LV Bus → LV Bus** = Overhead Line (ACSR 150mm², 1 km)

To use an **Underground Cable** instead of an Overhead Line, drag the Underground Cable component from the sidebar onto the canvas, then connect it between two buses manually.

### Rule 5 — Residential loads are single-phase

Residential loads connect to a single phase (A, B, or C) of the LV Bus. The default is Phase A. You can change this in the Properties panel. For a balanced network, distribute multiple residential loads across all three phases.

### Rule 6 — Draw connections in this order

Build your network top-down:

1. Place all buses first
2. Connect buses to each other (creates lines and transformers)
3. Place loads and generators
4. Connect each load/generator to its bus

This order prevents accidental wrong connections and makes the diagram easier to read.

---

## 7. Simulation Modes

Switch between modes using the toggle in the top bar.

### Snapshot (AC Power Flow)

Solves a single steady-state AC power flow. Use this to:
- Check bus voltages at a specific operating point
- Verify the network is within EN 50160 voltage limits
- See transformer and line losses
- Check line loading against ampacity limits

**When to use:** initial network design, checking a specific operating condition, verifying a change you made to the network.

### Time-Series (24-Hour Simulation)

Runs 48 consecutive snapshot solves (one per 30-minute interval) using Romanian daily load and solar irradiance profiles. Use this to:
- See how voltage changes throughout the day
- Identify the worst-case voltage rise during peak solar generation
- Calculate total energy generated and lost over 24 hours
- Check EN 50160 compliance across all time steps

**Parameters:**
- **Season** — Summer uses June 21 profiles for Bucharest (44.4°N), 13.5 hours of daylight, peak irradiance 0.85 kW/m². Winter uses December 21 profiles, 8 hours of daylight, peak irradiance 0.35 kW/m².
- **Load multiplier** — scales all loads up or down. 1.0× = normal day, 1.3× = heavy load day, 0.7× = light load day.

**When to use:** studying the impact of solar generation on voltage profiles, sizing transformers and lines for daily peak conditions, energy yield analysis.

### Fault Study

Calculates short-circuit currents at every bus using the Thevenin impedance method (EN 60909 methodology). Reports:
- **I_3ph** — three-phase symmetrical fault current (worst case for equipment rating)
- **I_1LG** — single line-to-ground fault current (most common fault type)
- **X/R ratio** — critical for protection relay and circuit breaker selection
- **Z1, Z0** — Thevenin impedances for relay setting calculations

**When to use:** verifying circuit breaker fault ratings, protection relay coordination studies, network short-circuit level assessment.

---

## 8. Reading Your Results

### Voltage results

| Value | Meaning | Good range |
|-------|---------|------------|
| **pu (per-unit)** | Voltage as a fraction of nominal. 1.0 = exactly nominal. | 0.90 – 1.10 pu (EN 50160) |
| **kV** | Actual voltage magnitude | Depends on bus type |
| **Deviation %** | How far from nominal, as a percentage | ±10% maximum |

A bus showing **green** in the results is within EN 50160 limits. **Red** means a violation — the voltage is too high or too low and corrective action is needed (add compensation, resize conductors, or adjust generation).

### Line current results

| Value | Meaning |
|-------|---------|
| **current_a** | Actual current in Amperes |
| **loading_pct** | Current as a percentage of the conductor's thermal limit |
| **overloaded** | True if loading_pct > 100% — conductor will overheat |

### Fault study results

| Value | Meaning |
|-------|---------|
| **I_3ph** | Three-phase fault current. Use this to size circuit breakers. |
| **I_1LG** | Single line-to-ground fault current. Use this for earth fault protection. |
| **X/R ratio** | Higher values mean more DC offset in the fault current. Affects breaker interrupting duty. |

---

## 9. Saving and Loading Grids

Click **☰ Saves** in the top bar to open the save/load panel.

**To save:**
1. Type a name for your grid in the input box
2. Press **Save** or hit Enter
3. The grid appears in the saved list

**To load:**
1. Click any grid name in the saved list
2. The canvas restores immediately

**To delete:**
1. Click the **✕** button next to any saved grid

Saved grids are stored in your browser's local storage. They persist between sessions on the same browser and computer but will not transfer to another computer automatically. To share a grid, use the GitHub repository or copy the `localStorage` data manually.

---

## 10. Exporting PDF Reports

After running any simulation, a **↓ PDF** button appears in the results panel header. Click it to download a professionally formatted report containing:

**Snapshot report:**
- Simulation metadata (solver, mode, convergence)
- EN 50160 compliance summary (pass/fail)
- Bus voltage table with deviation percentages
- Power losses by element
- Generator and DER output

**Time-series report:**
- 24-hour simulation summary
- Season, load multiplier, location reference
- EN 50160 compliance across all 48 steps
- Bus voltage range (min/max with timestamps)
- Hourly snapshot table at 2-hour intervals

**Fault study report:**
- Short-circuit currents at every bus (kA and A)
- Thevenin impedances (Z1 and Z0)
- X/R ratios
- EN 60909 methodology statement

Reports are saved as `[gridname]_report.pdf` in your Downloads folder.

---

## 11. Common Mistakes and Fixes

### Zero voltage on one or more buses

**Cause:** A component has an empty `bus_id` — it was never properly connected to a bus, or was connected in the wrong direction.

**Fix:** Delete the affected component, redraw it, and reconnect by dragging **from the bus** to the component.

---

### A bus named "kv" appears in results

**Cause:** A component (usually an Industrial Load or Generator) has a voltage mismatch. Its `base_kv` or `rated_kv` doesn't match the bus it's connected to, causing OpenDSS to misread the parameter as a bus name.

**Fix:** Click the affected component, open the Properties panel, and set `base_kv` or `rated_kv` to match the connected bus voltage (11.0 for MV buses, 0.4 for LV buses).

---

### Simulation converges but generator output is 0 kW

**Cause:** The generator's `rated_kv` doesn't match the bus voltage, or the generator has no `bus_id`.

**Fix:** Check the generator is connected to a bus (Properties panel should show a bus ID). Set `rated_kv` to match the bus (11.0 for MV, 0.4 for LV).

---

### Time-series shows "kVARmax unknown parameter" error

**Cause:** Version mismatch with the OpenDSS parameter name for reactive power limits.

**Fix:** This is handled in the current version. If you see this error, ensure you are running the latest version of the backend code.

---

### Transformer not appearing in payload / lines empty

**Cause:** Connections between buses were drawn before the correct version of the store was loaded (old cached edges have no component data).

**Fix:** Clear the canvas and redraw all connections from scratch. Do not load an old saved grid that was created before this was fixed.

---

### PDF download does nothing

**Cause:** The `/export-pdf` route is not in the Vite proxy configuration.

**Fix:** Check `frontend/vite.config.js` includes `'/export-pdf': 'http://localhost:8000'` in the proxy block.

---

## 12. Worked Example — Step by Step

This example builds a simple but complete network: a generator feeding an MV feeder with a transformer, LV loads, and a solar PV system.

### Network topology

```
[Generator] ──── [MV Bus A] ──OHL──  [MV Bus B] ──TX── [LV Bus C]
                                                             │
                                                    [Residential Load]
                                                             │
                                                        [Solar PV]
```

### Step 1 — Place buses

1. Drag **MV Bus** onto the canvas. This is Bus A — the source.
2. Drag a second **MV Bus** to the right of the first. This is Bus B.
3. Drag **LV Bus** below Bus B. This is Bus C.

### Step 2 — Connect buses

1. Hover over **MV Bus A** until the bottom handle appears (small circle).
2. Click and drag from the handle to **MV Bus B**. An overhead line appears labelled `OHL`.
3. Hover over **MV Bus B** and drag from its handle to **LV Bus C**. A transformer appears labelled `TX (Dyn11)`.

### Step 3 — Place and connect loads

1. Drag **Residential Load** onto the canvas near LV Bus C.
2. Hover over **LV Bus C** and drag from its handle to the **Residential Load**. The load's bus_id is now set.
3. Drag **Solar PV** onto the canvas near LV Bus C.
4. Hover over **LV Bus C** and drag from its handle to the **Solar PV**.

### Step 4 — Place and connect generator

1. Drag **Synchronous Generator** onto the canvas near MV Bus A.
2. Hover over **MV Bus A** and drag from its handle to the **Generator**.
3. Click the **Generator** to select it.
4. In the Properties panel, change `rated_kv` from `0.4` to `11.0`.

### Step 5 — Run Snapshot simulation

1. Make sure **Snapshot** is selected in the top bar toggle.
2. Press **▶ Run Simulation**.
3. Results appear in the right panel. All buses should show green (within EN 50160 limits).

### Step 6 — Run Time-Series simulation

1. Switch to **Time-Series** in the top bar.
2. Select **Summer** season, leave multiplier at **1.0×**.
3. Press **▶ Run 24h Simulation**.
4. Drag the timeline slider to see voltage and PV output change through the day.
5. Note the voltage rise around solar noon (11:30) and the voltage drop during the evening load peak (18:30).

### Step 7 — Run Fault Study

1. Switch to **Fault Study** in the top bar.
2. Press **⚡ Run Fault Study**.
3. Results show fault currents at MV Bus A, MV Bus B, and LV Bus C.
4. Note that MV Bus A has the highest fault level (closest to the grid source) and LV Bus C has the lowest (limited by transformer impedance).

### Step 8 — Export a report

1. Switch back to **Snapshot** and run the simulation.
2. Press **↓ PDF** in the results panel.
3. A PDF report downloads to your Downloads folder.

### Step 9 — Save your grid

1. Click **☰ Saves** in the top bar.
2. Type `Simple Feeder Example` and press **Save**.
3. The grid is now saved and can be reloaded at any time.
