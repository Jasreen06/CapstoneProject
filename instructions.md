# DockWise AI v2 — Project Instructions for Claude Code

## Project Identity

**Project Name:** DockWise AI v2 — Maritime Intelligence Platform
**Team:** Pramod Krishnachari, Jasreen Kaur, Darsini Lakshmiah
**Course:** MS Data Science Capstone, George Washington University
**Repository:** https://github.com/Jasreen06/CapstoneProject
**Branch:** `v2-live-ais` (create this branch from `main`)
**Deployment:** Vercel (frontend) + Railway/Render (backend)

---

## What We're Building

A real-time maritime intelligence platform that combines three live data streams to provide vessel-level congestion-aware rerouting recommendations across all US ports:

1. **Live AIS vessel tracking** (aisstream.io WebSocket) — real-time positions, speeds, headings, destinations for every vessel near US ports
2. **Port congestion analytics** (IMF PortWatch API) — daily port call counts and trade volumes for 117 US ports + 28 global chokepoints
3. **Weather risk scoring** (OpenWeatherMap API) — current conditions and forecasts affecting port operations

The platform answers a question no existing tool answers at the vessel level: **"This specific vessel is heading to a congested port — should it reroute, and where?"**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     DATA SOURCES                         │
│                                                         │
│  aisstream.io ──WebSocket──→ Backend AIS Consumer        │
│  PortWatch ArcGIS API ──REST──→ Backend Data Pull        │
│  OpenWeatherMap ──REST──→ Backend Weather Module          │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              BACKEND (FastAPI + Python)                   │
│                                                         │
│  ais_consumer.py      → WebSocket consumer for live AIS  │
│  ais_store.py         → In-memory vessel state store     │
│  trajectory.py        → 72-hour trajectory prediction    │
│  rerouting.py         → Congestion-aware rerouting engine│
│  portwatch.py         → PortWatch data pull + scoring    │
│  weather.py           → Weather fetch + ops risk scoring │
│  api.py               → FastAPI REST + SSE endpoints     │
│                                                         │
│  Deploy: Railway or Render (needs persistent WebSocket)  │
└──────────────────────┬──────────────────────────────────┘
                       │  REST API + Server-Sent Events
                       ▼
┌─────────────────────────────────────────────────────────┐
│              FRONTEND (React + Vite + Tailwind)          │
│                                                         │
│  Live Vessel Map (Mapbox GL / Leaflet)                   │
│  Port Congestion Dashboard                               │
│  Vessel Detail + Rerouting Panel                         │
│  Chokepoint Monitor                                      │
│  Weather Risk Cards                                      │
│  AI Advisor Chat (Groq LLaMA-3.3-70B)                   │
│                                                         │
│  Deploy: Vercel                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
CapstoneProject/
├── README.md
├── INSTRUCTIONS.md              ← this file
├── VERCEL_SETUP.md              ← Vercel deployment guide
│
├── backend/
│   ├── requirements.txt
│   ├── .env.example             ← template for API keys
│   ├── main.py                  ← FastAPI app entry point
│   ├── config.py                ← Environment config + constants
│   │
│   ├── data/
│   │   ├── ais_consumer.py      ← aisstream.io WebSocket consumer
│   │   ├── ais_store.py         ← In-memory vessel state (latest positions)
│   │   ├── portwatch.py         ← PortWatch ArcGIS data pull + cleaning
│   │   └── weather.py           ← OpenWeatherMap fetch + risk scoring
│   │
│   ├── analytics/
│   │   ├── congestion.py        ← Z-score congestion scoring
│   │   ├── trajectory.py        ← 72-hour trajectory prediction
│   │   ├── rerouting.py         ← Rerouting decision engine
│   │   └── forecasting.py       ← ARIMA/Prophet/XGBoost models
│   │
│   ├── llm/
│   │   ├── advisor.py           ← LangChain + Groq AI advisor
│   │   └── knowledge.py         ← Maritime knowledge base
│   │
│   └── api/
│       ├── routes_ports.py      ← Port endpoints
│       ├── routes_vessels.py    ← Vessel tracking endpoints
│       ├── routes_chokepoints.py← Chokepoint endpoints
│       ├── routes_weather.py    ← Weather endpoints
│       ├── routes_rerouting.py  ← Rerouting recommendation endpoints
│       └── routes_chat.py       ← AI chat endpoint
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   ├── vercel.json              ← Vercel config for SPA routing
│   │
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/
│       │   └── client.js        ← API client + SSE hooks
│       ├── components/
│       │   ├── Layout.jsx       ← App shell with nav tabs
│       │   ├── VesselMap.jsx    ← Main map with live vessel positions
│       │   ├── VesselDetail.jsx ← Vessel info + rerouting panel
│       │   ├── PortDashboard.jsx← Port congestion overview
│       │   ├── PortSelector.jsx ← Port picker with congestion ranking
│       │   ├── CongestionHero.jsx
│       │   ├── ForecastCard.jsx
│       │   ├── WeatherCard.jsx
│       │   ├── ChokepointView.jsx
│       │   ├── ReroutingPanel.jsx
│       │   └── AIAdvisor.jsx    ← Chat interface
│       ├── hooks/
│       │   ├── useVessels.js    ← SSE hook for live vessel data
│       │   ├── usePortData.js
│       │   └── useWeather.js
│       └── utils/
│           ├── trajectory.js    ← Client-side trajectory projection
│           └── constants.js     ← Port coords, vessel type codes, colors
│
└── scripts/
    ├── seed_portwatch.py        ← One-time full PortWatch data pull
    └── test_aisstream.py        ← Quick aisstream.io connection test
```

---

## API Keys Required

Create `backend/.env` from `backend/.env.example`:

```env
AISSTREAM_API_KEY=20b40af859998057d4b74c8854ec3db33f477e39
WEATHER_API_KEY=<your_openweathermap_key>
GROQ_API_KEY=<your_groq_key>
FRONTEND_URL=http://localhost:5173
```

**IMPORTANT:** Never commit `.env` to git. Add it to `.gitignore`.

---

## Backend Implementation Details

### 1. AIS Consumer (`data/ais_consumer.py`)

Connects to aisstream.io via WebSocket and maintains an in-memory store of latest vessel positions.

```python
# WebSocket URL
WSS_URL = "wss://stream.aisstream.io/v0/stream"

# Subscription covers all major US port regions
BOUNDING_BOXES = [
    # US West Coast (San Diego to Seattle)
    [[32.5, -125.0], [49.0, -117.0]],
    # US Gulf Coast (Brownsville to Key West)
    [[24.5, -97.5], [30.5, -80.0]],
    # US East Coast (Miami to Maine)
    [[25.0, -82.0], [45.0, -66.0]],
    # Hawaii
    [[18.0, -161.0], [23.0, -154.0]],
    # Alaska (major ports)
    [[55.0, -170.0], [65.0, -140.0]],
]

# Message types to subscribe to
MESSAGE_TYPES = ["PositionReport", "ShipStaticData", "StandardClassBPositionReport"]
```

**Key behaviors:**
- Runs as an asyncio background task when the FastAPI app starts
- Processes ~300 messages/second at peak (global subscription)
- Stores latest position per MMSI in `ais_store.py` (dict keyed by MMSI)
- Merges static data (vessel name, type, dimensions, destination) with position reports
- Auto-reconnects on WebSocket disconnect with exponential backoff
- CRITICAL: aisstream.io does NOT support browser CORS — must be consumed server-side

**Vessel state object:**
```python
{
    "mmsi": 366999999,
    "name": "COSCO BEIJING",
    "vessel_type": 70,          # IMO vessel type code
    "vessel_type_label": "Cargo",
    "lat": 33.72,
    "lon": -118.27,
    "sog": 12.5,                # speed over ground (knots)
    "cog": 308.0,               # course over ground (degrees)
    "heading": 310,             # true heading
    "nav_status": 0,            # 0=underway, 1=anchored, 5=moored
    "nav_status_label": "Under Way Using Engine",
    "rate_of_turn": 0,
    "draught": 12.5,            # meters
    "destination": "LOS ANGELES",
    "eta_crew": "04-10 14:00",  # crew-entered ETA
    "dimensions": {"a": 200, "b": 50, "c": 20, "d": 12},
    "last_update": "2026-04-05T21:30:00Z",
    "call_sign": "VRBC7",
    "imo": 9345678,
}
```

### 2. AIS Store (`data/ais_store.py`)

In-memory vessel state management.

```python
class VesselStore:
    """Thread-safe in-memory store for latest vessel positions."""

    def get_all_vessels() -> list[dict]
    def get_vessel(mmsi: int) -> dict | None
    def get_vessels_in_bbox(lat_min, lat_max, lon_min, lon_max) -> list[dict]
    def get_vessels_by_destination(port_name: str) -> list[dict]
    def get_vessel_count() -> int
    def update_position(mmsi, position_data)
    def update_static(mmsi, static_data)
    def cleanup_stale(max_age_minutes=30)  # remove vessels not heard from in 30 min
```

### 3. PortWatch Data (`data/portwatch.py`)

Pulls from IMF PortWatch ArcGIS FeatureServer. Same data source as Darsini's repo but with improved pipeline.

**Endpoints:**
- US Ports: `https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query`
- Chokepoints: `https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query`

**Behavior:**
- On startup: loads last 180 days of port data + chokepoint data into memory (pandas DataFrames)
- Background task: refreshes every 6 hours (PortWatch updates weekly on Tuesdays, but we check more often)
- Incremental fetch using watermark (max date in current data)
- Computes congestion scores using 90-day rolling z-score (same formula as Darsini's repo)
- Stores CSV locally as cache (`data/portwatch_us_data.csv`, `data/chokepoint_data.csv`)

### 4. Congestion Scoring (`analytics/congestion.py`)

Z-score based, normalized to 0-100:

```python
rolling_mean = portcalls.rolling(90, min_periods=1).mean()
rolling_std  = portcalls.rolling(90, min_periods=1).std()
z = clip((portcalls - rolling_mean) / rolling_std, -3, 3)
score = (z + 3) / 6 * 100

# Levels:
# 0-33   = LOW    (port has capacity)
# 34-66  = MEDIUM (near normal, monitor)
# 67-100 = HIGH   (expect delays, anchorage queues)
```

### 5. Trajectory Prediction (`analytics/trajectory.py`)

Predicts vessel position over next 72 hours using dead reckoning with great circle projection.

**Inputs:** current lat, lon, SOG, COG, RateOfTurn, destination port
**Output:** list of predicted positions at 1-hour intervals for 72 hours

```python
def predict_trajectory(
    lat: float,
    lon: float,
    sog_knots: float,
    cog_degrees: float,
    rate_of_turn: float = 0,
    destination_port: str | None = None,
    hours: int = 72,
) -> list[dict]:
    """
    Returns list of {lat, lon, timestamp, hours_from_now} for each hour.

    Logic:
    1. If destination port is known and vessel is heading roughly toward it:
       - Compute great circle route to destination
       - Project along that route at current SOG
       - Apply speed reduction near port (slow to 8 knots within 20nm)
    2. If no destination or heading away:
       - Simple rhumb line projection at current COG + SOG
       - Apply rate of turn for curved trajectories
    3. Compute ETA = distance_to_destination / average_speed
    """
```

### 6. Rerouting Engine (`analytics/rerouting.py`)

The core differentiator. Evaluates whether a vessel should reroute to an alternative port.

```python
def evaluate_rerouting(
    vessel: dict,                    # from ais_store
    trajectory: list[dict],          # from trajectory prediction
    destination_congestion: dict,    # current + forecasted congestion at destination
    destination_weather: dict,       # weather forecast at destination
    alternative_ports: list[str],    # candidate alternatives by region
) -> dict:
    """
    Returns:
    {
        "should_reroute": bool,
        "reason": str,
        "destination": {
            "port": "Los Angeles-Long Beach",
            "congestion_score": 78.3,
            "congestion_level": "HIGH",
            "eta_hours": 42,
            "weather_risk": "LOW",
        },
        "alternatives": [
            {
                "port": "Oakland",
                "congestion_score": 31.2,
                "congestion_level": "LOW",
                "additional_distance_nm": 340,
                "additional_time_hours": 18,
                "draught_compatible": True,
                "vessel_type_compatible": True,
                "weather_risk": "LOW",
                "recommendation": "STRONG",
            },
            ...
        ]
    }
    """
```

**Rerouting decision factors:**
- Destination congestion score at predicted arrival time (from forecasting models)
- Weather risk at destination during arrival window
- Alternative port congestion scores
- Draught compatibility (vessel draught vs. port channel depth)
- Vessel type compatibility (container ports vs. bulk vs. tanker)
- Additional transit distance and time
- Regional port groupings for alternatives

**Port region → alternatives mapping:**

```python
ALTERNATIVES = {
    "West Coast": {
        "Los Angeles-Long Beach": ["Oakland", "Seattle", "Tacoma", "San Diego"],
        "Oakland": ["Los Angeles-Long Beach", "Seattle", "Tacoma"],
        "Seattle": ["Tacoma", "Oakland", "Los Angeles-Long Beach"],
        "Tacoma": ["Seattle", "Oakland", "Los Angeles-Long Beach"],
    },
    "East Coast": {
        "New York-New Jersey": ["Philadelphia", "Baltimore", "Norfolk", "Savannah"],
        "Savannah": ["Charleston", "Jacksonville", "Norfolk"],
        "Charleston": ["Savannah", "Norfolk", "Jacksonville"],
        "Baltimore": ["Norfolk", "Philadelphia", "New York-New Jersey"],
    },
    "Gulf Coast": {
        "Houston": ["Corpus Christi", "New Orleans", "Freeport", "Galveston"],
        "New Orleans": ["Houston", "Baton Rouge", "Mobile"],
        "Corpus Christi": ["Houston", "Port Lavaca", "Freeport"],
    },
}
```

**Port channel depths (minimum for draught check):**

```python
PORT_DEPTHS_METERS = {
    "Los Angeles-Long Beach": 16.8,
    "Oakland": 15.2,
    "New York-New Jersey": 15.2,
    "Savannah": 14.0,
    "Houston": 14.0,
    "Seattle": 15.8,
    # ... etc for all major ports
}
```

### 7. Weather Module (`data/weather.py`)

Same as Darsini's implementation but covering all 117 US ports. Fetches from OpenWeatherMap.

**Risk thresholds:**
- Wind >= 20 m/s → HIGH (crane ops suspended)
- Wind >= 15 m/s → MEDIUM (crane ops marginal)
- Visibility <= 500m → HIGH (vessel movement restricted)
- Visibility <= 1000m → MEDIUM (fog advisory)
- Rain >= 10 mm/h → MEDIUM (bulk cargo loading affected)
- Thunderstorm/Tornado/Hurricane keywords → HIGH

### 8. AI Advisor (`llm/advisor.py`)

LangChain + Groq (LLaMA-3.3-70B) chatbot. Same pattern as Darsini's `llm.py` but with live vessel context.

**Enhanced context includes:**
- Live vessel data for selected port (count, types, anchored vs. underway)
- Current congestion score + 7-day forecast
- Weather conditions + risk
- Upstream chokepoint disruption scores
- Any active rerouting recommendations

### 9. API Endpoints (`api/`)

**Port Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ports` | List all 117 US port names |
| GET | `/api/ports/{port}/overview` | KPIs, congestion, trend, vessel mix |
| GET | `/api/ports/top?n=20` | Top N ports ranked by congestion |
| GET | `/api/ports/{port}/forecast?model=Prophet&horizon=7` | Congestion forecast |

**Vessel Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels` | All live vessels (paginated, filterable) |
| GET | `/api/vessels/{mmsi}` | Single vessel details |
| GET | `/api/vessels/{mmsi}/trajectory?hours=72` | Predicted trajectory |
| GET | `/api/vessels/{mmsi}/rerouting` | Rerouting recommendation |
| GET | `/api/vessels/bbox?lat_min=&lat_max=&lon_min=&lon_max=` | Vessels in area |
| GET | `/api/vessels/stream` | SSE stream of vessel position updates |
| GET | `/api/vessels/stats` | Summary stats (total vessels, by type, by status) |

**Chokepoint Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/chokepoints` | All chokepoints with disruption scores |
| GET | `/api/chokepoints/{name}` | Detailed stats for one chokepoint |

**Weather Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/weather/{port}` | Current weather + forecast + risk |

**Chat Endpoint:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | AI advisor query |

**System:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/stats` | System stats (vessel count, data freshness) |

---

## Frontend Implementation Details

### Tech Stack
- **React 18** with hooks
- **Vite** for build tooling
- **Tailwind CSS** for styling
- **Mapbox GL JS** (or Leaflet + react-leaflet) for the vessel map
- **Recharts** for charts and graphs
- **Deployed on Vercel**

### Tab Structure

**Tab 1: Live Vessel Map**
- Full-screen map showing all live vessel positions as dots
- Dots color-coded: green (destination LOW congestion), yellow (MEDIUM), red (HIGH), gray (no destination)
- Dot shape by vessel type: circle (cargo), triangle (tanker), square (container), diamond (other)
- Click a vessel → side panel shows vessel detail + predicted trajectory line on map
- Trajectory line: gradient from solid (near-term) to dashed (72h out)
- If rerouting recommended: show alternative route as dotted line in different color
- Toggle layers: vessel positions, density heatmap, traffic lanes
- Filter by: vessel type, nav status (underway/anchored/moored), destination port

**Tab 2: Port Intelligence**
- Left sidebar: port selector ranked by congestion (color-coded)
- Main area: congestion hero card, 7-day outlook, trend timeline
- Weather card with current conditions + forecast + risk banner
- Vessel mix breakdown (by type, monthly stacked bar)
- Upstream chokepoint risk cards (4 per port based on region)
- Inbound vessel list: vessels currently heading to this port with ETAs

**Tab 3: Chokepoint Monitor**
- All 28 chokepoints ranked by disruption score
- Click for detail: 90-day transit history, vessel type breakdown, trend

**Tab 4: Rerouting Advisor**
- Select a vessel (search by name, MMSI, or click from map)
- Shows current position, destination, predicted ETA
- Congestion forecast at destination for arrival window
- Weather forecast at destination
- Alternative port recommendations with comparison table
- "Ask AI" button for natural language analysis

**Tab 5: AI Advisor**
- Chat interface
- Suggested questions: "Which inbound vessels to Houston should consider rerouting?", "What's the congestion outlook for LA this week?", "How will the Suez disruption affect East Coast ports?"

### Color Scheme (Dark Maritime Theme)
```
Background:      #0f172a (slate-900)
Card background: #1e293b (slate-800)
Text primary:    #f1f5f9 (slate-100)
Text secondary:  #94a3b8 (slate-400)
Accent blue:     #3b82f6
LOW green:       #22c55e
MEDIUM yellow:   #eab308
HIGH red:        #ef4444
```

### Live Data Updates
- **Vessel positions:** Server-Sent Events (SSE) from `/api/vessels/stream`
  - Backend pushes position updates every 5 seconds (batched)
  - Frontend updates map markers in real-time
- **Port data:** Polled every 5 minutes from `/api/ports/{port}/overview`
- **Weather:** Polled every 15 minutes

---

## Vessel Type Codes (IMO)

```
70-79: Cargo vessels
  70: Cargo, all types
  71: Cargo, Hazardous A
  72: Cargo, Hazardous B
  73: Cargo, Hazardous C
  74: Cargo, Hazardous D
  75-79: Cargo, reserved

80-89: Tanker
  80: Tanker, all types
  81: Tanker, Hazardous A
  82-89: Tanker variants

60-69: Passenger
90-99: Other (fishing, tug, pilot, SAR, etc.)
30-39: Fishing
40-49: High-speed craft
50-59: Special craft (dredger, military, sailing)
```

### Navigational Status Codes
```
0: Under way using engine
1: At anchor
2: Not under command
3: Restricted manoeuvrability
4: Constrained by draught
5: Moored
6: Aground
7: Engaged in fishing
8: Under way sailing
9-14: Reserved
15: Not defined
```

---

## Port-to-Chokepoint Mapping

Same as Darsini's implementation:

| Region | Port Keywords | Upstream Chokepoints |
|--------|--------------|---------------------|
| West Coast | los angeles, oakland, seattle, tacoma, san diego, honolulu | Malacca Strait, Taiwan Strait, Panama Canal, Luzon Strait |
| Gulf Coast | houston, new orleans, corpus christi, galveston, mobile, tampa | Panama Canal, Strait of Hormuz, Bab el-Mandeb Strait, Suez Canal |
| Great Lakes | chicago, detroit, cleveland, duluth, milwaukee | Suez Canal, Panama Canal, Dover Strait, Gibraltar Strait |
| East Coast | (default) | Suez Canal, Bab el-Mandeb Strait, Panama Canal, Dover Strait |

---

## Implementation Order (Priority)

### Phase 1: Foundation (do first)
1. Set up project structure (directory layout, package.json, requirements.txt)
2. Implement `ais_consumer.py` + `ais_store.py` — prove WebSocket works
3. Implement basic FastAPI with `/api/vessels` endpoint
4. Create React app with Vite + Tailwind + map component showing vessel dots
5. Deploy backend to Railway, frontend to Vercel — prove the pipeline works end-to-end

### Phase 2: Port Intelligence
6. Implement `portwatch.py` — pull PortWatch data, compute congestion scores
7. Add port endpoints (`/api/ports`, `/api/ports/{port}/overview`)
8. Build Port Intelligence tab in frontend
9. Add weather module + weather endpoints
10. Add chokepoint data + endpoints

### Phase 3: Vessel Intelligence
11. Implement `trajectory.py` — dead reckoning prediction
12. Add trajectory endpoint + map overlay
13. Implement `rerouting.py` — decision engine
14. Build Rerouting Advisor tab
15. Add SSE streaming for real-time vessel updates

### Phase 4: AI + Polish
16. Implement AI Advisor with Groq
17. Add forecasting models (Prophet/XGBoost)
18. Polish UI, add loading states, error handling
19. Write README with screenshots
20. Final deployment + demo prep

---

## Key Technical Decisions

1. **No database** — In-memory storage (dicts + DataFrames). Vessel positions are ephemeral (latest only). PortWatch data is small enough for pandas. This keeps deployment simple and free-tier compatible.

2. **SSE over WebSocket for frontend** — Server-Sent Events are simpler, work through Vercel's proxy, and are sufficient for one-way position updates. The aisstream WebSocket is backend-only.

3. **No historical AIS in this version** — The scope is US-wide live tracking. Historical pattern matching can be added later as a BigQuery integration.

4. **Groq over OpenAI** — Free tier, fast inference, LLaMA-3.3-70B is excellent for structured maritime analysis.

5. **Mapbox GL over Leaflet** — Better performance with thousands of vessel markers. Free tier allows 50k map loads/month. Fall back to Leaflet + OpenStreetMap if Mapbox token is unavailable.

---

## Environment Setup

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn main:app --reload --port 8004
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### requirements.txt
```
fastapi
uvicorn[standard]
pydantic
pandas
numpy
requests
python-dotenv
websockets
asyncio
prophet
statsmodels
xgboost
scikit-learn
langchain-groq
langchain-core
sse-starlette
```

### package.json dependencies
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.20.0",
    "mapbox-gl": "^3.4.0",
    "recharts": "^2.12.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.4.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

---

## Git Workflow

```bash
# Clone and create branch
git clone https://github.com/Jasreen06/CapstoneProject.git
cd CapstoneProject
git checkout -b v2-live-ais

# Work in feature branches off v2-live-ais
git checkout -b feature/ais-consumer
# ... make changes ...
git add .
git commit -m "feat: implement aisstream.io WebSocket consumer"
git push origin feature/ais-consumer
# Create PR to v2-live-ais

# Commit message format:
# feat: new feature
# fix: bug fix
# docs: documentation
# refactor: code restructuring
# style: UI/formatting changes
```

---

## Testing the AIS Stream

Quick test to verify your API key works:

```python
# scripts/test_aisstream.py
import asyncio
import websockets
import json

async def test():
    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        await ws.send(json.dumps({
            "APIKey": "20b40af859998057d4b74c8854ec3db33f477e39",
            "BoundingBoxes": [[[33.5, -118.5], [33.9, -118.0]]],  # LA port area
            "FilterMessageTypes": ["PositionReport"]
        }))
        for i in range(10):
            msg = json.loads(await ws.recv())
            pos = msg["Message"]["PositionReport"]
            meta = msg["MetaData"]
            print(f"  {meta.get('ShipName','?'):20s} | "
                  f"MMSI={pos['UserID']} | "
                  f"({pos['Latitude']:.4f}, {pos['Longitude']:.4f}) | "
                  f"SOG={pos['Sog']:.1f}kn COG={pos['Cog']:.0f}°")

asyncio.run(test())
```

---

## Notes for Claude Code

- Always check if code changes break the existing functionality before committing
- Use type hints in all Python functions
- Use async/await for all I/O operations in the backend
- Frontend components should be functional React with hooks, never class components
- Use Tailwind utility classes, not custom CSS files
- All API responses should use consistent JSON structure with proper error handling
- Never hardcode API keys — always read from environment variables
- The aisstream API key in this file is real — treat it as sensitive
- When adding new API endpoints, also add CORS middleware configuration
- Test WebSocket connection before building dependent features