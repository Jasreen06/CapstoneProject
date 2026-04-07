# AIS Backend Integration

## Overview
Added a standalone AIS (Automatic Identification System) microservice that connects to aisstream.io's live WebSocket feed, ingests real-time vessel position and static data for US waters, and exposes it via REST + SSE endpoints.

## Files Created

### `venv2/backend/AIS/__init__.py`
Empty package init making `AIS/` a Python subpackage of the backend.

### `venv2/backend/AIS/ais_store.py`
Thread-safe in-memory vessel store (singleton pattern).
- **`VesselStore`** class — async dict keyed by MMSI (Maritime Mobile Service Identity)
- **`update_position(mmsi, data)`** — merges lat/lon/sog/cog/heading/nav_status into vessel record, sets `last_update` timestamp
- **`update_static(mmsi, data)`** — merges name/call_sign/imo/vessel_type/destination/eta into vessel record
- **`get_all_vessels()`** — returns all vessels as a list of dicts (includes MMSI in each dict)
- **`cleanup_stale(max_age_minutes=30)`** — removes vessels with no update within the threshold
- Module-level singleton: `vessel_store = VesselStore()`

### `venv2/backend/AIS/ais_consumer.py`
Async WebSocket consumer for aisstream.io.
- Connects to `wss://stream.aisstream.io/v0/stream` with the API key from `AISSTREAM_API_KEY` env var
- Subscribes to 5 US bounding boxes: West Coast, Gulf Coast, East Coast, Hawaii, Alaska
- Processes 3 AIS message types:
  - `PositionReport` — Class A vessel positions
  - `StandardClassBPositionReport` — Class B vessel positions
  - `ShipStaticData` — vessel name, type, destination, ETA, IMO, call sign
- Parses navigational status labels (0–15) and vessel type labels (30–99 ranges)
- Runs stale vessel cleanup every 10 minutes
- Exponential backoff reconnection (1s → 60s max) on connection failures
- Loads `.env` explicitly from `backend/` root via `dotenv`

### `venv2/backend/AIS/ais_api.py`
Standalone FastAPI app on **port 8001** (separate from main `api.py` on port 8000).
- **`/api/vessels/stream`** — SSE (Server-Sent Events) endpoint pushing all vessel positions every 5 seconds
- **`/api/vessels`** — JSON snapshot of all live vessels with valid lat/lon
- **`/api/vessels/stats`** — Summary: total count, breakdown by vessel type and navigational status
- **`/health`** — Health check
- CORS configured for `localhost:3000`, `localhost:5173`, `localhost:8000`
- Starts `ais_consumer` as a background task on app startup

## Configuration
- Requires `AISSTREAM_API_KEY` in `venv2/backend/.env`
- Start: `cd venv2/backend && uvicorn AIS.ais_api:app --port 8001`

## Architecture Decision
The AIS service runs as a **separate FastAPI app on its own port** rather than being added to the existing `api.py`. This keeps the original backend untouched and avoids coupling live WebSocket streaming with the existing PortWatch/forecasting endpoints.
