"""
main.py
=======
FastAPI application entry point for DockWise AI v2.

Start with:
    uvicorn main:app --reload --port 8004
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import FRONTEND_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="DockWise AI v2",
    description="Real-time maritime port intelligence platform",
    version="2.0.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include routers ───────────────────────────────────────────────────────────
from api.routes_ports import router as ports_router
from api.routes_vessels import router as vessels_router
from api.routes_chokepoints import router as chokepoints_router
from api.routes_weather import router as weather_router
from api.routes_rerouting import router as rerouting_router
from api.routes_chat import router as chat_router

app.include_router(ports_router)
app.include_router(vessels_router)
app.include_router(chokepoints_router)
app.include_router(weather_router)
app.include_router(rerouting_router)
app.include_router(chat_router)


# ── Startup / Shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    logger.info("DockWise AI v2 starting up...")

    # Start AIS consumer as background task
    from data.ais_consumer import start_ais_consumer
    asyncio.create_task(start_ais_consumer())
    logger.info("AIS consumer background task started")

    # Load PortWatch data (non-blocking)
    from data.portwatch import portwatch_store
    asyncio.create_task(_load_portwatch(portwatch_store))

    # Schedule PortWatch refresh every 6 hours
    asyncio.create_task(_portwatch_refresh_loop(portwatch_store))


async def _load_portwatch(store) -> None:
    try:
        logger.info("Loading PortWatch data...")
        await store.load_data()
        logger.info("PortWatch data loaded successfully")
    except Exception as e:
        logger.error(f"PortWatch load failed: {e}")


async def _portwatch_refresh_loop(store) -> None:
    while True:
        await asyncio.sleep(6 * 3600)  # 6 hours
        try:
            logger.info("Refreshing PortWatch data...")
            await store.refresh()
        except Exception as e:
            logger.error(f"PortWatch refresh failed: {e}")


# ── Health & Stats ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    from data.ais_store import vessel_store
    from data.portwatch import portwatch_store

    vessel_count = await vessel_store.get_vessel_count()
    portwatch_loaded = (
        portwatch_store.ports_df is not None and not portwatch_store.ports_df.empty
    )

    return {
        "status": "ok",
        "vessel_count": vessel_count,
        "portwatch_loaded": portwatch_loaded,
        "portwatch_last_updated": (
            portwatch_store.last_updated.isoformat() if portwatch_store.last_updated else None
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/stats")
async def api_stats():
    from data.ais_store import vessel_store
    from data.portwatch import portwatch_store

    vessel_count = await vessel_store.get_vessel_count()
    port_count = len(portwatch_store.get_port_names())

    return {
        "live_vessels": vessel_count,
        "ports_tracked": port_count,
        "portwatch_last_updated": (
            portwatch_store.last_updated.isoformat() if portwatch_store.last_updated else None
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
