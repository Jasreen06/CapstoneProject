"""
test_aisstream.py
=================
Quick test to verify aisstream.io API key and WebSocket connection.

Usage:
    python scripts/test_aisstream.py

Prints 10 vessel position messages from the LA port area.
"""

import asyncio
import json
import os
import sys

# Load .env from backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
except ImportError:
    pass

import websockets

API_KEY = os.getenv("AISSTREAM_API_KEY", "")


async def test():
    if not API_KEY:
        print("ERROR: AISSTREAM_API_KEY not set. Check backend/.env")
        return

    print(f"Connecting to aisstream.io with key: {API_KEY[:8]}...")
    try:
        async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
            await ws.send(json.dumps({
                "APIKey": API_KEY,
                "BoundingBoxes": [[[33.5, -118.5], [33.9, -118.0]]],  # LA port area
                "FilterMessageTypes": ["PositionReport"],
            }))
            print("Subscription sent. Waiting for vessel data...\n")

            count = 0
            async for raw in ws:
                if count >= 10:
                    break
                try:
                    msg = json.loads(raw)
                    if msg.get("MessageType") == "PositionReport":
                        pos = msg["Message"]["PositionReport"]
                        meta = msg.get("MetaData", {})
                        print(
                            f"  {meta.get('ShipName', 'UNKNOWN'):20s} | "
                            f"MMSI={pos['UserID']:9d} | "
                            f"({pos['Latitude']:7.4f}, {pos['Longitude']:9.4f}) | "
                            f"SOG={pos['Sog']:5.1f}kn  COG={pos['Cog']:5.0f}°"
                        )
                        count += 1
                except (KeyError, json.JSONDecodeError):
                    pass

            print(f"\nSuccess! Received {count} vessel messages.")
    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == "__main__":
    asyncio.run(test())
