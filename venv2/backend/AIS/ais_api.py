"""
ais_api.py
==========
Standalone FastAPI app for live vessel tracking via aisstream.io.
Runs on port 8001 alongside the main api.py (port 8000).

Start:  uvicorn AIS.ais_api:app --port 8001
"""

from __future__ import annotations
import asyncio
import json
import logging
import math
import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from AIS.ais_store import vessel_store
from AIS.ais_consumer import start_ais_consumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DockWise AI — AIS Vessel Tracker", version="1.0")

_ais_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ais_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _start_ais():
    asyncio.create_task(start_ais_consumer())


@app.get("/api/vessels/stream")
async def vessel_stream():
    """SSE stream of live vessel positions, updated every 5 seconds."""
    async def event_generator():
        while True:
            vessels = await vessel_store.get_all_vessels()
            updates = [
                {
                    "mmsi": v.get("mmsi"),
                    "lat": v.get("lat"),
                    "lon": v.get("lon"),
                    "sog": v.get("sog"),
                    "cog": v.get("cog"),
                    "name": v.get("name"),
                    "destination": v.get("destination"),
                    "nav_status": v.get("nav_status"),
                    "nav_status_label": v.get("nav_status_label"),
                    "vessel_type_label": v.get("vessel_type_label"),
                    "last_update": v.get("last_update"),
                }
                for v in vessels
                if v.get("lat") and v.get("lon")
            ]
            payload = json.dumps({"vessels": updates, "count": len(updates)})
            yield f"event: vessels\ndata: {payload}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/vessels/stats")
async def vessel_stats():
    """Summary: total vessels, breakdown by type and nav status."""
    vessels = await vessel_store.get_all_vessels()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for v in vessels:
        t = v.get("vessel_type_label", "Unknown")
        by_type[t] = by_type.get(t, 0) + 1
        s = v.get("nav_status_label", "Unknown")
        by_status[s] = by_status.get(s, 0) + 1
    return {"total": len(vessels), "by_type": by_type, "by_nav_status": by_status}


@app.get("/api/vessels")
async def list_vessels():
    """All live vessels with valid positions."""
    vessels = await vessel_store.get_all_vessels()
    result = [v for v in vessels if v.get("lat") and v.get("lon")]
    return {"vessels": result, "count": len(result)}


@app.get("/api/vessels/anchor-stats")
async def anchor_stats(
    lat: float = Query(..., description="Port latitude"),
    lon: float = Query(..., description="Port longitude"),
    radius_nm: float = Query(15.0, description="Search radius in nautical miles"),
):
    """Count vessels within `radius_nm` of (lat, lon) by nav status.

    Used by the main backend's staleness reconciliation (api.py:port_overview).
    """
    R_NM = 3440.065

    def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        return 2 * R_NM * math.asin(math.sqrt(a))

    vessels = await vessel_store.get_all_vessels()
    anchor_count = 0
    moored_count = 0
    total_nearby = 0
    for v in vessels:
        v_lat = v.get("lat")
        v_lon = v.get("lon")
        if v_lat is None or v_lon is None:
            continue
        if haversine_nm(lat, lon, v_lat, v_lon) <= radius_nm:
            total_nearby += 1
            status = (v.get("nav_status_label") or "").strip()
            if status == "At Anchor":
                anchor_count += 1
            elif status == "Moored":
                moored_count += 1

    return {
        "lat": lat,
        "lon": lon,
        "radius_nm": radius_nm,
        "anchor_count": anchor_count,
        "moored_count": moored_count,
        "total_nearby": total_nearby,
        "vessel_store_size": len(vessels),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "ais"}
