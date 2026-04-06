"""
routes_chat.py
==============
AI Advisor chat endpoint for DockWise AI v2.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from llm.advisor import answer_chat
from llm.knowledge import build_context
from data.portwatch import portwatch_store
from data.ais_store import vessel_store
from data.weather import fetch_weather_for_port

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    port_context: str | None = None
    vessel_mmsi: int | None = None
    port_name: str | None = None
    history: list[dict] | None = None


@router.post("/")
async def chat_endpoint(req: ChatRequest):
    """Send a question to the AI maritime advisor."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Build context from live data
    ports_data = None
    weather_data = None
    chokepoints_data = None
    vessels_data = None

    if req.port_name:
        ports_data = portwatch_store.get_port_overview(req.port_name)
        if "error" in ports_data:
            ports_data = None
        try:
            weather_data = await fetch_weather_for_port(req.port_name)
        except Exception:
            weather_data = None

    try:
        chokepoints_data = portwatch_store.get_chokepoints()
    except Exception:
        chokepoints_data = []

    vessel_rerouting = None
    if req.vessel_mmsi:
        vessels_data = await vessel_store.get_all_vessels()
        vessel = await vessel_store.get_vessel(req.vessel_mmsi)
        if vessel:
            from analytics.rerouting import get_rerouting_for_vessel
            try:
                vessel_rerouting = get_rerouting_for_vessel(vessel=vessel, portwatch_store=portwatch_store)
            except Exception:
                pass

    context = build_context(
        port_name=req.port_name,
        vessel_mmsi=req.vessel_mmsi,
        ports_data=ports_data,
        vessels_data=vessels_data,
        weather_data=weather_data,
        chokepoints_data=chokepoints_data,
        vessel_rerouting=vessel_rerouting,
    )

    # Merge with any additional context from the request
    if req.port_context:
        context = req.port_context + "\n\n" + context

    try:
        response = await answer_chat(
            message=req.message,
            port_context=context,
            history=req.history or [],
        )
        return {"response": response, "status": "ok"}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI advisor error: {e}")
