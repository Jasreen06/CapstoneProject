"""
routes_vessels.py
=================
Live vessel tracking API endpoints for DockWise AI v2.
"""

from __future__ import annotations
import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from data.ais_store import vessel_store
from analytics.trajectory import predict_trajectory, estimate_eta
from analytics.rerouting import get_rerouting_for_vessel
from data.portwatch import portwatch_store

router = APIRouter(prefix="/api/vessels", tags=["vessels"])


def _filter_vessels(
    vessels: list[dict],
    vessel_type: str | None = None,
    nav_status: int | None = None,
    destination: str | None = None,
) -> list[dict]:
    result = vessels
    if vessel_type:
        result = [v for v in result if v.get("vessel_type_label", "").lower() == vessel_type.lower()]
    if nav_status is not None:
        result = [v for v in result if v.get("nav_status") == nav_status]
    if destination:
        dest_lower = destination.lower()
        result = [v for v in result if dest_lower in (v.get("destination") or "").lower()]
    return result


@router.get("/stats")
async def vessel_stats():
    """Summary statistics: total vessels, by type, by nav status."""
    vessels = await vessel_store.get_all_vessels()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for v in vessels:
        t = v.get("vessel_type_label", "Unknown")
        by_type[t] = by_type.get(t, 0) + 1
        s = v.get("nav_status_label", "Unknown")
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "total": len(vessels),
        "by_type": by_type,
        "by_nav_status": by_status,
    }


@router.get("/stream")
async def vessel_stream(
    vessel_type: str | None = None,
    nav_status: int | None = None,
):
    """
    Server-Sent Events stream of vessel position updates.
    Pushes batched updates every 5 seconds.
    """
    async def event_generator():
        while True:
            vessels = await vessel_store.get_all_vessels()
            filtered = _filter_vessels(vessels, vessel_type=vessel_type, nav_status=nav_status)
            # Send lightweight position updates only
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
                for v in filtered
                if v.get("lat") and v.get("lon")
            ]
            yield {
                "event": "vessels",
                "data": json.dumps({"vessels": updates, "count": len(updates)}),
            }
            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())


@router.get("/bbox")
async def vessels_in_bbox(
    lat_min: float = Query(...),
    lat_max: float = Query(...),
    lon_min: float = Query(...),
    lon_max: float = Query(...),
):
    """All vessels within a bounding box."""
    vessels = await vessel_store.get_vessels_in_bbox(lat_min, lat_max, lon_min, lon_max)
    return {"vessels": vessels, "count": len(vessels)}


@router.get("/")
async def list_vessels(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    vessel_type: str | None = None,
    nav_status: int | None = None,
    destination: str | None = None,
):
    """Paginated list of all live vessels with optional filters."""
    vessels = await vessel_store.get_all_vessels()
    filtered = _filter_vessels(vessels, vessel_type=vessel_type, nav_status=nav_status, destination=destination)

    # Filter to only vessels with valid positions
    filtered = [v for v in filtered if v.get("lat") and v.get("lon")]

    total = len(filtered)
    start = (page - 1) * limit
    page_data = filtered[start: start + limit]

    return {
        "vessels": page_data,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/{mmsi}")
async def get_vessel(mmsi: int):
    """Get full details for a single vessel by MMSI."""
    vessel = await vessel_store.get_vessel(mmsi)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel {mmsi} not found")
    return vessel


@router.get("/{mmsi}/trajectory")
async def vessel_trajectory(
    mmsi: int,
    hours: int = Query(72, ge=1, le=168),
):
    """Predicted trajectory for a vessel over the next N hours."""
    vessel = await vessel_store.get_vessel(mmsi)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel {mmsi} not found")

    trajectory = predict_trajectory(
        lat=vessel.get("lat", 0),
        lon=vessel.get("lon", 0),
        sog_knots=vessel.get("sog", 10),
        cog_degrees=vessel.get("cog", 0),
        rate_of_turn=vessel.get("rate_of_turn", 0),
        destination_port=vessel.get("destination"),
        hours=hours,
    )

    eta = None
    if vessel.get("destination") and vessel.get("sog"):
        eta = estimate_eta(
            lat=vessel["lat"],
            lon=vessel["lon"],
            sog_knots=vessel["sog"],
            destination_port=vessel["destination"],
        )

    return {
        "mmsi": mmsi,
        "vessel_name": vessel.get("name", ""),
        "current_position": {"lat": vessel.get("lat"), "lon": vessel.get("lon")},
        "trajectory": trajectory,
        "eta_hours": eta,
        "destination": vessel.get("destination"),
    }


@router.get("/{mmsi}/rerouting")
async def vessel_rerouting(mmsi: int):
    """Full rerouting evaluation for a vessel."""
    vessel = await vessel_store.get_vessel(mmsi)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel {mmsi} not found")

    result = get_rerouting_for_vessel(vessel=vessel, portwatch_store=portwatch_store)
    return result
