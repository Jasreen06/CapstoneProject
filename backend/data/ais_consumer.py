"""
ais_consumer.py
===============
Async WebSocket consumer for aisstream.io.
Connects to the live AIS stream and maintains vessel_store with
latest positions and static data for all vessels near US ports.

IMPORTANT: aisstream.io does NOT support browser CORS — this must be
consumed server-side only.
"""

from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from config import (
    AISSTREAM_API_KEY,
    WSS_URL,
    BOUNDING_BOXES,
    MESSAGE_TYPES,
    NAV_STATUS_LABELS,
    get_vessel_type_label,
)
from data.ais_store import vessel_store

logger = logging.getLogger(__name__)


def _parse_position_report(msg: dict) -> dict:
    pos = msg["Message"]["PositionReport"]
    meta = msg.get("MetaData", {})
    mmsi = pos.get("UserID", 0)
    nav_status = pos.get("NavigationalStatus", 15)
    return {
        "mmsi": mmsi,
        "lat": pos.get("Latitude"),
        "lon": pos.get("Longitude"),
        "sog": round(pos.get("Sog", 0), 1),
        "cog": round(pos.get("Cog", 0), 1),
        "heading": pos.get("TrueHeading", 511),
        "nav_status": nav_status,
        "nav_status_label": NAV_STATUS_LABELS.get(nav_status, "Unknown"),
        "rate_of_turn": pos.get("RateOfTurn", 0),
        "name": meta.get("ShipName", "").strip(),
    }


def _parse_class_b_position(msg: dict) -> dict:
    pos = msg["Message"]["StandardClassBPositionReport"]
    meta = msg.get("MetaData", {})
    mmsi = pos.get("UserID", 0)
    return {
        "mmsi": mmsi,
        "lat": pos.get("Latitude"),
        "lon": pos.get("Longitude"),
        "sog": round(pos.get("Sog", 0), 1),
        "cog": round(pos.get("Cog", 0), 1),
        "heading": pos.get("TrueHeading", 511),
        "nav_status": 0,
        "nav_status_label": "Under Way Using Engine",
        "rate_of_turn": 0,
        "name": meta.get("ShipName", "").strip(),
    }


def _parse_static_data(msg: dict) -> dict:
    static = msg["Message"]["ShipStaticData"]
    mmsi = static.get("UserID", 0)
    vessel_type = static.get("Type", 0)
    dim = static.get("Dimension", {})
    eta = static.get("Eta", {})
    return {
        "mmsi": mmsi,
        "name": static.get("Name", "").strip(),
        "call_sign": static.get("CallSign", "").strip(),
        "imo": static.get("ImoNumber", 0),
        "vessel_type": vessel_type,
        "vessel_type_label": get_vessel_type_label(vessel_type),
        "draught": static.get("MaximumStaticDraught", 0),
        "destination": static.get("Destination", "").strip(),
        "eta_crew": (
            f"{eta.get('Month', 0):02d}-{eta.get('Day', 0):02d} "
            f"{eta.get('Hour', 0):02d}:{eta.get('Minute', 0):02d}"
            if eta else ""
        ),
        "dimensions": {
            "a": dim.get("A", 0),
            "b": dim.get("B", 0),
            "c": dim.get("C", 0),
            "d": dim.get("D", 0),
        },
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
    """Connect to aisstream.io and consume messages until disconnected."""
    subscription = {
        "APIKey": AISSTREAM_API_KEY,
        "BoundingBoxes": BOUNDING_BOXES,
        "FilterMessageTypes": MESSAGE_TYPES,
    }

    logger.info("Connecting to aisstream.io...")
    async with websockets.connect(WSS_URL, ping_interval=30, ping_timeout=10) as ws:
        await ws.send(json.dumps(subscription))
        logger.info("AIS stream subscription sent — receiving vessel data")

        # Periodic cleanup task
        last_cleanup = datetime.now(timezone.utc)

        async for raw in ws:
            await _process_message(raw)

            # Clean up stale vessels every 10 minutes
            now = datetime.now(timezone.utc)
            if (now - last_cleanup).seconds > 600:
                removed = await vessel_store.cleanup_stale(max_age_minutes=30)
                if removed:
                    logger.info(f"Cleaned up {removed} stale vessels")
                last_cleanup = now


async def start_ais_consumer() -> None:
    """
    Main loop: connect to aisstream with exponential backoff reconnects.
    Call this as an asyncio background task on app startup.
    """
    if not AISSTREAM_API_KEY:
        logger.warning("AISSTREAM_API_KEY not set — AIS consumer disabled")
        return

    backoff = 1
    max_backoff = 60

    while True:
        try:
            await connect_aisstream()
            # If we get here normally (stream closed), reset backoff
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
