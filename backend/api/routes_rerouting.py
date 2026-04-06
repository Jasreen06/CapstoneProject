"""
routes_rerouting.py
===================
Rerouting recommendation endpoints for DockWise AI v2.
"""

from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data.ais_store import vessel_store
from data.portwatch import portwatch_store
from analytics.rerouting import get_rerouting_for_vessel
from config import resolve_port_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rerouting", tags=["rerouting"])


class ReroutingRequest(BaseModel):
    mmsi: int
    destination_override: str | None = None


@router.post("/evaluate")
async def evaluate_rerouting(req: ReroutingRequest):
    """Full rerouting evaluation for a vessel."""
    vessel = await vessel_store.get_vessel(req.mmsi)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel {req.mmsi} not found")

    if req.destination_override:
        vessel = {**vessel, "destination": req.destination_override}

    result = get_rerouting_for_vessel(vessel=vessel, portwatch_store=portwatch_store)
    return result


@router.get("/alerts")
async def rerouting_alerts():
    """
    Returns all vessels that should consider rerouting.
    Only includes vessels where:
    - Destination resolves to a known US port
    - That port has HIGH congestion
    - Rerouting IS actually recommended
    """
    all_vessels = await vessel_store.get_all_vessels()
    alerts = []

    # Get top congested ports
    top_ports = portwatch_store.get_top_ports(n=50)
    high_ports = {p["port"]: p for p in top_ports if p.get("congestion_level") == "HIGH"}

    for v in all_vessels:
        raw_dest = v.get("destination", "")
        if not raw_dest:
            continue

        resolved = resolve_port_name(raw_dest)
        if not resolved:
            continue

        # Check if resolved port is HIGH congestion
        if resolved not in high_ports:
            continue

        try:
            rerouting = get_rerouting_for_vessel(vessel=v, portwatch_store=portwatch_store)
            if rerouting.get("should_reroute"):
                alerts.append({
                    "vessel": {
                        "mmsi": v.get("mmsi"),
                        "name": v.get("name", ""),
                        "vessel_type_label": v.get("vessel_type_label", "Unknown"),
                        "lat": v.get("lat"),
                        "lon": v.get("lon"),
                        "sog": v.get("sog", 0),
                        "cog": v.get("cog", 0),
                        "destination": raw_dest,
                    },
                    "resolved_port": resolved,
                    "congestion_score": high_ports[resolved].get("congestion_score", 0),
                    "congestion_level": "HIGH",
                    "rerouting": rerouting,
                })
        except Exception as e:
            logger.debug(f"Rerouting eval failed for MMSI {v.get('mmsi')}: {e}")
            continue

    # Sort by congestion score descending
    alerts.sort(key=lambda x: x["congestion_score"], reverse=True)

    return {
        "alerts": alerts[:50],  # Cap at 50 for performance
        "total": len(alerts),
        "high_congestion_ports": len(high_ports),
    }
