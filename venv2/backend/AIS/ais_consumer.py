"""
ais_consumer.py
===============
Async WebSocket consumer for aisstream.io.
Connects to the live AIS stream and maintains vessel_store with
latest positions and static data for all vessels near US ports.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend root (parent of AIS/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from AIS.ais_store import vessel_store

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
WSS_URL = "wss://stream.aisstream.io/v0/stream"

BOUNDING_BOXES = [
    [[32.5, -125.0], [49.0, -117.0]],   # West Coast
    [[24.5, -97.5], [30.5, -80.0]],      # Gulf Coast
    [[25.0, -82.0], [45.0, -66.0]],      # East Coast
    [[18.0, -161.0], [23.0, -154.0]],    # Hawaii
    [[55.0, -170.0], [65.0, -140.0]],    # Alaska
]

MESSAGE_TYPES = ["PositionReport", "ShipStaticData", "StandardClassBPositionReport"]

NAV_STATUS_LABELS = {
    0: "Under Way Using Engine", 1: "At Anchor", 2: "Not Under Command",
    3: "Restricted Manoeuvrability", 4: "Constrained by Draught", 5: "Moored",
    6: "Aground", 7: "Engaged in Fishing", 8: "Under Way Sailing",
    14: "AIS-SART active", 15: "Not Defined",
}


def _get_vessel_type_label(type_code: int) -> str:
    if 30 <= type_code <= 39: return "Fishing"
    elif 40 <= type_code <= 49: return "High Speed Craft"
    elif 50 <= type_code <= 59: return "Special Craft"
    elif 60 <= type_code <= 69: return "Passenger"
    elif 70 <= type_code <= 79: return "Cargo"
    elif 80 <= type_code <= 89: return "Tanker"
    elif 90 <= type_code <= 99: return "Other"
    return "Unknown"


def _parse_position_report(msg: dict) -> dict:
    pos = msg["Message"]["PositionReport"]
    meta = msg.get("MetaData", {})
    nav_status = pos.get("NavigationalStatus", 15)
    return {
        "mmsi": pos.get("UserID", 0),
        "lat": pos.get("Latitude"),
        "lon": pos.get("Longitude"),
        "sog": round(pos.get("Sog", 0), 1),
        "cog": round(pos.get("Cog", 0), 1),
        "heading": pos.get("TrueHeading", 511),
        "nav_status": nav_status,
        "nav_status_label": NAV_STATUS_LABELS.get(nav_status, "Unknown"),
        "name": meta.get("ShipName", "").strip(),
    }


def _parse_class_b_position(msg: dict) -> dict:
    pos = msg["Message"]["StandardClassBPositionReport"]
    meta = msg.get("MetaData", {})
    return {
        "mmsi": pos.get("UserID", 0),
        "lat": pos.get("Latitude"),
        "lon": pos.get("Longitude"),
        "sog": round(pos.get("Sog", 0), 1),
        "cog": round(pos.get("Cog", 0), 1),
        "heading": pos.get("TrueHeading", 511),
        "nav_status": 0,
        "nav_status_label": "Under Way Using Engine",
        "name": meta.get("ShipName", "").strip(),
    }


def _parse_static_data(msg: dict) -> dict:
    static = msg["Message"]["ShipStaticData"]
    vessel_type = static.get("Type", 0)
    eta = static.get("Eta", {})
    return {
        "mmsi": static.get("UserID", 0),
        "name": static.get("Name", "").strip(),
        "call_sign": static.get("CallSign", "").strip(),
        "imo": static.get("ImoNumber", 0),
        "vessel_type": vessel_type,
        "vessel_type_label": _get_vessel_type_label(vessel_type),
        "draught": static.get("MaximumStaticDraught", 0),
        "destination": static.get("Destination", "").strip(),
        "eta_crew": (
            f"{eta.get('Month', 0):02d}-{eta.get('Day', 0):02d} "
            f"{eta.get('Hour', 0):02d}:{eta.get('Minute', 0):02d}"
            if eta else ""
        ),
    }


async def _process_message(raw: str) -> None:
    try:
        msg = json.loads(raw)
        msg_type = msg.get("MessageType")

        if msg_type == "PositionReport":
            data = _parse_position_report(msg)
            mmsi = data.pop("mmsi")
            if data.get("lat") and data.get("lon"):
                await vessel_store.update_position(mmsi, data)

        elif msg_type == "StandardClassBPositionReport":
            data = _parse_class_b_position(msg)
            mmsi = data.pop("mmsi")
            if data.get("lat") and data.get("lon"):
                await vessel_store.update_position(mmsi, data)

        elif msg_type == "ShipStaticData":
            data = _parse_static_data(msg)
            mmsi = data.pop("mmsi")
            await vessel_store.update_static(mmsi, data)

    except (KeyError, json.JSONDecodeError, TypeError) as e:
        logger.debug(f"Message parse error: {e}")


async def connect_aisstream() -> None:
    """Connect to aisstream.io and consume messages."""
    subscription = {
        "APIKey": AISSTREAM_API_KEY,
        "BoundingBoxes": BOUNDING_BOXES,
        "FilterMessageTypes": MESSAGE_TYPES,
    }

    logger.info("Connecting to aisstream.io...")
    async with websockets.connect(WSS_URL, ping_interval=30, ping_timeout=10) as ws:
        await ws.send(json.dumps(subscription))
        logger.info("AIS stream connected — receiving vessel data")

        last_cleanup = datetime.now(timezone.utc)

        async for raw in ws:
            await _process_message(raw)

            now = datetime.now(timezone.utc)
            if (now - last_cleanup).seconds > 600:
                removed = await vessel_store.cleanup_stale(max_age_minutes=30)
                if removed:
                    logger.info(f"Cleaned up {removed} stale vessels")
                last_cleanup = now


async def start_ais_consumer() -> None:
    """Main loop with exponential backoff reconnects."""
    if not AISSTREAM_API_KEY:
        logger.warning("AISSTREAM_API_KEY not set — AIS consumer disabled")
        return

    backoff = 1
    max_backoff = 60

    while True:
        try:
            await connect_aisstream()
            backoff = 1
        except ConnectionClosed as e:
            logger.warning(f"AIS stream closed: {e}. Reconnecting in {backoff}s...")
        except WebSocketException as e:
            logger.error(f"AIS WebSocket error: {e}. Reconnecting in {backoff}s...")
        except OSError as e:
            logger.error(f"AIS network error: {e}. Reconnecting in {backoff}s...")
        except Exception as e:
            logger.error(f"AIS unexpected error: {e}. Reconnecting in {backoff}s...")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
