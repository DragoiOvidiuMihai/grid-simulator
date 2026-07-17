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
    version = "0.1.0",
)


# ─────────────────────────────────────────────────────────────────────────────
# CORS MIDDLEWARE
# CORS (Cross-Origin Resource Sharing) allows your React frontend running on
# localhost:3000 to make requests to this API running on localhost:8000.
# Without this, the browser blocks the requests for security reasons.
# In production this would be locked down to your actual domain.
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:3000"],  # React dev server
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# A simple endpoint to verify the server is running.
# Hit http://localhost:8000/health in your browser to confirm.
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
    # If the translator raises an exception it means the grid is valid per
    # Pydantic but has a logical issue the translator caught (e.g. a bus
    # referenced by a load doesn't exist in the bus list).
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

    # ── Step 3: Return results ────────────────────────────────────────────────
    # to_dict() converts the SimulationResult dataclass into a plain dictionary
    # which FastAPI automatically serialises to JSON.
    return result.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# DEBUG ENDPOINT — DSS Script Preview
# This is a development tool. It returns the raw DSS script that would be
# sent to OpenDSS for a given grid, without actually running the simulation.
# Very useful for debugging translator output during development.
# Remove or protect this endpoint before any public deployment.
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

    Request body: TimeSeriesRequest containing:
      - grid: complete Grid JSON object
      - season: 'summer' or 'winter'
      - peak_load_multiplier: 0.1 to 2.0 (default 1.0)

    Response: 48-step results with voltage profiles, energy totals,
              and EN 50160 violation counts.
    """

    # ── Step 1: Build scaled profiles ─────────────────────────────────────────
    # Find peak load values from the grid components
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

    # ── Step 2: Translate grid to time-series DSS script ──────────────────────
    try:
        dss_script = translate_grid_timeseries(request.grid, profiles)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Grid translation failed: {str(e)}"
        )

    # ── Step 3: Run time-series simulation ────────────────────────────────────
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