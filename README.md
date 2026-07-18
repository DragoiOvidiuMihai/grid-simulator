# Grid Simulator

An interactive distribution grid simulator built on **OpenDSS** with a React frontend. Draw single-line diagrams, run professional-grade power flow simulations, and export engineering reports — all from a browser interface.

Built as a portfolio project by an Electrical Engineering and Computers student at UNSTPB. All components, parameters, and results follow **EU/IEC standards**.

---

## Screenshots

### Network Canvas
![Canvas with a built network](images/canvas.png)

### Simulation Results
![Simulation results panel](images/results.png)

### Exported Engineering Report
![PDF engineering report](images/report.png)
---

## What it does

### Three simulation modes

**Snapshot — AC Power Flow**
Solves a steady-state AC power flow using the Newton-Raphson method via OpenDSS. Returns bus voltages in per-unit, line currents as a percentage of ampacity, transformer and line losses, and generator reactive output. Results are checked automatically against **EN 50160** voltage quality limits.

**Time-Series — 24-Hour Daily Simulation**
Runs 48 consecutive snapshot solves (30-minute intervals) using built-in Romanian daily load profiles and solar irradiance curves based on Bucharest's geographic coordinates (44.4°N). Supports summer and winter seasonal profiles and a configurable load multiplier. Results include voltage profiles across the day, total energy generated and lost, and EN 50160 compliance statistics across all time steps.

**Fault Study — Short-Circuit Analysis**
Calculates three-phase and single line-to-ground fault currents at every bus using the Thevenin impedance method (EN 60909 methodology). Returns fault currents in kA, Thevenin impedances (Z1 and Z0), and X/R ratios for protection relay coordination.

### Professional PDF reports
Every simulation mode produces a downloadable PDF report formatted for engineering use — EN 50160 compliance summary, bus voltage tables, loss breakdowns, and fault current tables with Thevenin impedances.

### Save / Load
Named grid configurations are saved to browser localStorage and can be reloaded at any time.

---

## Technical architecture

```
┌─────────────────────────────────────────┐
│           React Frontend                │
│   React Flow canvas  │  Zustand store   │
│   Tailwind CSS       │  Axios HTTP      │
└──────────────────────┬──────────────────┘
                       │ REST API (JSON)
┌──────────────────────▼──────────────────┐
│           FastAPI Backend               │
│   Pydantic validation                   │
│   DSS script translator                 │
│   OpenDSS solver wrapper                │
│   ReportLab PDF generator               │
└──────────────────────┬──────────────────┘
                       │ opendssdirect.py
┌──────────────────────▼──────────────────┐
│              OpenDSS Engine             │
│   AC power flow  │  Fault study         │
│   Daily mode     │  Thevenin Zsc        │
└─────────────────────────────────────────┘
```

**Why OpenDSS instead of a custom solver?**
OpenDSS is a professional-grade distribution system simulator used by utilities, research institutions, and the US Department of Energy. Using it as the computational core — rather than implementing power flow from scratch — means the simulation results are validated and correct. The engineering contribution of this project is the data model, the DSS script translator, the EU/IEC standards compliance layer, and the frontend interface.

---

## Component library

8 components modelled to EU/IEC specifications:

| Component | Standard | Key Parameters |
|-----------|----------|---------------|
| MV Bus (11 kV) | — | Base voltage 11 kV, 3-phase |
| LV Bus (0.4 kV) | — | Base voltage 0.4 kV, 3-phase |
| Two-Winding Transformer | Dyn11 vector group | 500 kVA, 11/0.4 kV, %R=1.1, %X=4.0 |
| Overhead Line | IEC 61089 / EN 50182 | ACSR 150mm², R1=0.196 Ω/km, ampacity 415 A |
| Underground Cable | IEC 60502-2 / IEC 60228 | 12/20kV XLPE 150mm² Cu, R1=0.124 Ω/km |
| Residential Load | — | Single-phase, 5 kW default, PF 0.95 |
| Industrial Load | — | Three-phase, 250 kW default, PF 0.90 |
| Synchronous Generator | — | 500 kW, configurable kV and PF |
| Solar PV | IEC 61215 (STC) | 100 kW peak, inverter-based, PVSystem object |

---

## Standards compliance

| Standard | Governs |
|----------|---------|
| **EN 50160** | Voltage quality limits (±10% nominal). Applied to all bus voltage results. |
| **IEC 61089** | Overhead conductor specifications (ACSR 150mm² impedance values). |
| **EN 50182** | Overhead conductor construction (ACSR strand geometry). |
| **IEC 60502-2** | Underground cable ratings (12/20kV XLPE construction). |
| **IEC 60228** | Conductor resistance at rated temperature (150mm² Cu at 90°C). |
| **EN 60909** | Short-circuit current calculation methodology (fault study). |
| **IEC 61215** | PV module standard test conditions (1.0 kW/m², 25°C). |

---

## Installation

### Requirements

- Python 3.11+
- Node.js 18+

### Clone and install

```bash
git clone https://github.com/DragoiOvidiuMihai/grid-simulator.git
cd grid-simulator
```

**Backend:**
```bash
python -m venv venv

# Windows
venv\Scripts\activate
# Mac / Linux
source venv/bin/activate

pip install fastapi uvicorn opendssdirect.py pydantic reportlab
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### Run

Open two terminals from the project root:

**Terminal 1 — Backend:**
```bash
uvicorn backend.api.main:app --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server health check |
| `POST` | `/simulate` | AC snapshot power flow |
| `POST` | `/simulate-timeseries` | 24-hour time-series simulation |
| `POST` | `/fault-study` | Short-circuit fault study |
| `POST` | `/export-pdf` | Generate PDF report |
| `POST` | `/preview-dss` | Preview raw DSS script (development) |

Interactive API documentation available at **http://localhost:8000/docs** when the backend is running.

---

## Project structure

```
grid-simulator/
├── backend/
│   ├── api/
│   │   ├── main.py                     # FastAPI endpoints
│   │   └── report_generator.py         # ReportLab PDF generator
│   ├── models/
│   │   └── models.py                   # Pydantic data models (8 components)
│   ├── translators/
│   │   ├── dss_translator.py           # Grid → DSS script (snapshot)
│   │   └── dss_translator_timeseries.py # Grid → DSS script (time-series)
│   └── solver/
│       ├── solver.py                   # OpenDSS snapshot wrapper
│       ├── solver_timeseries.py        # OpenDSS time-series wrapper
│       ├── solver_fault.py             # OpenDSS fault study wrapper
│       └── profiles.py                 # Romanian load/irradiance profiles
├── frontend/
│   └── src/
│       ├── App.jsx                     # Main layout and mode toggle
│       ├── store/
│       │   └── gridStore.js            # Zustand state store
│       └── components/
│           ├── canvas/
│           │   ├── Canvas.jsx          # React Flow canvas
│           │   └── GridNode.jsx        # Custom node renderer
│           ├── sidebar/
│           │   └── Sidebar.jsx         # Component library panel
│           ├── properties/
│           │   └── PropertiesPanel.jsx # Parameter editor
│           ├── results/
│           │   └── ResultsPanel.jsx    # Simulation results display
│           └── SaveLoadPanel.jsx       # Save/load grid configurations
├── USER_GUIDE.md                       # End-user documentation
├── TECHNICAL.md                        # Technical implementation details
├── STANDARDS.md                        # IEC/EN standards reference
└── README.md                           # This file
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [USER_GUIDE.md](USER_GUIDE.md) | Installation, circuit-building rules, simulation modes, worked example, common mistakes |
| [TECHNICAL.md](TECHNICAL.md) | Architecture decisions, data model design, DSS translator, solver integration, EN 50160 implementation |
| [STANDARDS.md](STANDARDS.md) | IEC/EN standards reference with parameter sources |

---

## Known limitations

- **Component variety** — the library is intentionally focused: one transformer type, one overhead conductor, one cable type. This ensures every component is modelled correctly rather than offering many loosely parameterised options.
- **Single voltage level** — the network operates at 11 kV / 0.4 kV (EU standard distribution). HV transmission and other voltage levels are not modelled.
- **Balanced three-phase** — the power flow assumes balanced three-phase conditions. Unbalanced analysis is not implemented.
- **Browser localStorage** — saved grids are stored in the browser and do not persist across different browsers or computers without manual transfer.
- **DC power flow** — not implemented in the current version.

---

## Built with

**Backend:** Python, FastAPI, Pydantic, OpenDSSDirect.py, ReportLab

**Frontend:** React, React Flow, Zustand, Tailwind CSS, Vite, Axios

**Solver:** OpenDSS (via opendssdirect.py)

---

## Author

**Dragoi Ovidiu Mihai**
Electrical Engineering and Computers Student
[GitHub](https://github.com/DragoiOvidiuMihai)
