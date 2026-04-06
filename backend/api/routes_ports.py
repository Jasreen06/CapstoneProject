"""
routes_ports.py
===============
Port Intelligence API endpoints for DockWise AI v2.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query

from data.portwatch import portwatch_store
from analytics.forecasting import forecast_congestion

router = APIRouter(prefix="/api/ports", tags=["ports"])


@router.get("/")
async def list_ports():
    """List all available US port names."""
    ports = portwatch_store.get_port_names()
    return {"ports": ports, "count": len(ports)}


@router.get("/top")
async def top_ports(n: int = Query(20, ge=1, le=117)):
    """Top N ports ranked by current congestion score."""
    ports = portwatch_store.get_top_ports(n=n)
    return {"ports": ports, "count": len(ports)}


@router.get("/{port}/overview")
async def port_overview(port: str):
    """KPIs, congestion score, trend, and 7-day recent history for a port."""
    overview = portwatch_store.get_port_overview(port)
    if "error" in overview:
        raise HTTPException(status_code=404, detail=overview["error"])
    return overview


@router.get("/{port}/forecast")
async def port_forecast(
    port: str,
    model: str = Query("Prophet", regex="^(Prophet|XGBoost|ARIMA)$"),
    horizon: int = Query(7, ge=1, le=30),
):
    """Congestion forecast for a port using the specified model."""
    df = portwatch_store.get_port_time_series(port)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for port '{port}'")

    forecast = forecast_congestion(port_name=port, df=df, model=model, horizon_days=horizon)
    return {
        "port": port,
        "model": model,
        "horizon_days": horizon,
        "forecast": forecast,
    }
