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
import os

from fastapi import FastAPI
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "ais"}
