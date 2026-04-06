"""
routes_weather.py
=================
Weather risk endpoints for DockWise AI v2.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException

from data.weather import fetch_weather_for_port
from config import PORT_COORDS

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/{port}")
async def get_port_weather(port: str):
    """Current weather conditions, forecast, and operational risk for a port."""
    if port not in PORT_COORDS:
        # Try case-insensitive match
        matches = [k for k in PORT_COORDS if k.lower() == port.lower()]
        if not matches:
            raise HTTPException(status_code=404, detail=f"Unknown port: {port}")
        port = matches[0]

    weather = await fetch_weather_for_port(port)
    if "error" in weather:
        raise HTTPException(status_code=503, detail=weather["error"])
    return weather
