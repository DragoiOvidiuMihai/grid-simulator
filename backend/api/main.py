"""
FastAPI Application — Grid Simulator Backend
============================================
Exposes a single endpoint for Phase 1:

  POST /simulate
    Accepts a Grid JSON payload
    Returns simulation results (voltages, currents, losses, generator outputs)

Run with:
  uvicorn backend.api.main:app --reload --port 8000

Then open:
  http://localhost:8000/docs   ← interactive API documentation (auto-generated)
  http://localhost:8000/redoc  ← alternative docs view
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from backend.models.models import Grid
from backend.translators.dss_translator import translate_grid
from backend.solver.solver import run_power_flow

from backend.models.models import Grid, TimeSeriesRequest
from backend.translators.dss_translator_timeseries import translate_grid_timeseries
from backend.solver.solver_timeseries import run_timeseries
from backend.solver.profiles import get_scaled_profiles

from fastapi.responses import Response
from backend.api.report_generator import generate_report

from backend.solver.solver_fault import run_fault_study

# ── SCADA module ──────────────────────────────────────────────────────────────
from backend.api.scada_router import router as scada_router, init_scada
import os


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN — start/stop the SCADA simulation loop with the app
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Read config from environment variable
    # Set USE_OPENDSS=true before starting uvicorn to enable real power flow
    use_opendss = os.environ.get("USE_OPENDSS", "false").lower() == "true"

    # Start SCADA background loop on startup
    _manager, _state, _loop = init_scada(use_opendss=use_opendss)
    _state.history_store.open()
    _loop.start()
    yield
    # Stop cleanly on shutdown
    _loop.stop()
    _state.history_store.close()


# ─────────────────────────────────────────────────────────────────────────────
# APP INITIALISATION
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Grid Simulator API",
    description = (
        "Backend API for the Distribution Grid Simulator. "
        "Accepts grid topology as JSON, runs an AC power flow via OpenDSS, "
        "and returns bus voltages, line currents, power losses, and generator outputs. "
        "All components and results follow EU/IEC standards."
    ),
    version  = "0.2.0",
    lifespan = lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# CORS MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# SCADA ROUTER
# All SCADA endpoints are mounted under /scada
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(scada_router)


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Grid Simulator API is running"}


# ─────────────────────────────────────────────────────────────────────────────
# /simulate ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/simulate")
def simulate(grid: Grid):
    """
    Run an AC power flow simulation on the submitted grid.

    Request body: a complete Grid JSON object (see models.py for schema)
    Response:     simulation results including voltages, currents, losses

    HTTP status codes:
      200 — simulation ran (check result.converged for solver success)
      422 — grid JSON failed Pydantic validation (malformed input)
      500 — unexpected server error
    """

    # ── Step 1: Translate Grid → DSS script ───────────────────────────────────
    try:
        dss_script = translate_grid(grid)
    except Exception as e:
        raise HTTPException(
            status_code = 422,
            detail      = f"Grid translation failed: {str(e)}"
        )

    # ── Step 2: Run power flow via OpenDSS ────────────────────────────────────
    try:
        result = run_power_flow(dss_script)
    except Exception as e:
        raise HTTPException(
            status_code = 500,
            detail      = f"Solver error: {str(e)}"
        )

    return result.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# DEBUG ENDPOINT — DSS Script Preview
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/preview-dss")
def preview_dss(grid: Grid):
    """
    Returns the raw DSS script that would be sent to OpenDSS.
    Use this during development to inspect and verify translator output.
    """
    try:
        dss_script = translate_grid(grid)
    except Exception as e:
        raise HTTPException(
            status_code = 422,
            detail      = f"Grid translation failed: {str(e)}"
        )

    return {
        "grid_id":    grid.id,
        "grid_name":  grid.name,
        "dss_script": dss_script,
    }

@app.post("/simulate-timeseries")
def simulate_timeseries(request: TimeSeriesRequest):
    """
    Run a 48-step daily time-series simulation on the submitted grid.
    """

    peak_residential = max(
        (l.kw for l in request.grid.residential_loads), default=5.0
    )
    peak_industrial = max(
        (l.kw for l in request.grid.industrial_loads), default=250.0
    )

    try:
        profiles = get_scaled_profiles(
            peak_residential_kw  = peak_residential,
            peak_industrial_kw   = peak_industrial,
            peak_load_multiplier = request.peak_load_multiplier,
            season               = request.season,
        )
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Profile generation failed: {str(e)}"
        )

    try:
        dss_script = translate_grid_timeseries(request.grid, profiles)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Grid translation failed: {str(e)}"
        )

    try:
        result = run_timeseries(
            dss_script           = dss_script,
            profiles             = profiles,
            season               = request.season,
            peak_load_multiplier = request.peak_load_multiplier,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Time-series solver error: {str(e)}"
        )

    return result.to_dict()

@app.post("/export-pdf")
def export_pdf(payload: dict):
    try:
        pdf_bytes = generate_report(
            grid_name         = payload.get("grid_name", "Grid Report"),
            simulation_result = payload.get("simulation_result"),
            timeseries_result = payload.get("timeseries_result"),
            fault_result      = payload.get("fault_result"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    return Response(
        content    = pdf_bytes,
        media_type = "application/pdf",
        headers    = {"Content-Disposition": 'attachment; filename="grid_report.pdf"'}
    )

@app.post("/fault-study")
def fault_study(grid: Grid):
    """
    Run a fault study on the submitted grid.
    Returns three-phase and single line-to-ground fault currents
    at every bus, plus Thevenin impedances and X/R ratios.
    """
    try:
        dss_script = translate_grid(grid)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Grid translation failed: {str(e)}")

    try:
        result = run_fault_study(dss_script)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fault study error: {str(e)}")

    return result.to_dict()
