"""
routes_chokepoints.py
=====================
Chokepoint monitoring endpoints for DockWise AI v2.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException

from data.portwatch import portwatch_store

router = APIRouter(prefix="/api/chokepoints", tags=["chokepoints"])


@router.get("/")
async def list_chokepoints():
    """All global chokepoints with current disruption scores."""
    chokepoints = portwatch_store.get_chokepoints()
    return {"chokepoints": chokepoints, "count": len(chokepoints)}


@router.get("/{name}")
async def get_chokepoint(name: str):
    """Detailed stats for a single chokepoint including 90-day history."""
    data = portwatch_store.get_chokepoint(name)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data
