# DockWise AI v2 — Architecture Overview

## System Architecture

```
+-------------------+     SSE (real-time)     +------------------+
|                   | <---------------------- |                  |
|    React SPA      |     REST (on-demand)    |   FastAPI        |
|    (Vite)         | ----------------------> |   Backend        |
|    Port 5173      |                         |   Port 8004      |
|                   |                         |                  |
+-------------------+                         +------------------+
        |                                            |
        |                                     +------+------+
        |                                     |             |
        v                                     v             v
  Leaflet/OSM                           AIS Stream     PortWatch
  (CartoDB tiles)                       (WebSocket)    (CSV data)
                                              |             |
                                              v             v
                                        vessel_store   portwatch_store
                                        (in-memory)    (in-memory)
```

## Frontend Architecture

### Page Components
- **VesselMap** (`/vessels`) — Leaflet map with real-time vessel tracking
- **PortDashboard** (`/ports`) — Port intelligence with 5+ visualization cards
- **ReroutingTab** (`/rerouting`) — Server-driven rerouting advisor
- **ChokepointView** (`/chokepoints`) — Global chokepoint monitoring
- **AIAdvisor** (`/advisor`) — LLM-powered maritime Q&A

### Data Flow
```
useVessels() hook -> SSE /api/vessels/stream -> vessel_store -> AIS WebSocket
usePortData() hook -> REST /api/ports/{port}/overview -> portwatch_store
useTopPorts() hook -> REST /api/ports/top?n=50 -> portwatch_store
Rerouting alerts -> REST /api/rerouting/alerts -> resolve_port_name() + portwatch_store
```

### Cross-Page Navigation
URL parameters enable seamless navigation between pages:
- `/vessels?focus=MMSI&dest=PORT&alts=ALT1,ALT2` — Isolated vessel view
- `/ports?port=PORT` — Pre-selected port dashboard

### Key Utility Modules
- `utils/constants.js` — All shared constants, colors, labels, port data
- `utils/trajectory.js` — Haversine distance, ETA, dead reckoning projection
- `api/client.js` — API fetch wrappers + SSE factory

## Backend Architecture

### API Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/api/vessels/stream` | GET (SSE) | Real-time vessel positions |
| `/api/vessels/{mmsi}` | GET | Single vessel details |
| `/api/vessels/{mmsi}/rerouting` | GET | Rerouting analysis for a vessel |
| `/api/ports/` | GET | List all ports |
| `/api/ports/top` | GET | Top N ports by congestion |
| `/api/ports/{port}/overview` | GET | Port congestion overview |
| `/api/ports/{port}/forecast` | GET | Congestion forecast |
| `/api/rerouting/evaluate` | POST | Evaluate rerouting for vessel |
| `/api/rerouting/alerts` | GET | All vessels needing rerouting |
| `/api/weather/{port}` | GET | Weather conditions |
| `/api/chokepoints/` | GET | Chokepoint disruption data |
| `/api/chat/` | POST | AI advisor chat |

### Port Name Resolution Pipeline
```
Raw AIS destination (e.g., "SOUTH PHILLY")
  |
  v
resolve_port_name() in config.py
  |-- Direct match against PORT_COORDS keys
  |-- Keyword matching against ~55 patterns
  |
  v
Resolved port name (e.g., "Philadelphia") or None
  |
  v
portwatch_store.get_port_overview("Philadelphia")
  |
  v
Congestion data: {score: 96.8, level: "HIGH", ...}
```

### Rerouting Engine Pipeline
```
Vessel data + resolved destination
  |
  v
get_rerouting_for_vessel()
  |-- Resolve destination -> lookup congestion
  |-- Get alternative ports for region
  |-- Lookup alternative congestion scores
  |-- Project trajectory (dead reckoning)
  |-- Evaluate: compare dest vs alts
  |
  v
{should_reroute, reason, destination, alternatives[]}
```

## Technology Stack

### Frontend
- **React 18** with functional components and hooks
- **Vite 5** for build and dev server
- **Tailwind CSS 3** for styling
- **Leaflet + react-leaflet 5** for interactive maps
- **Recharts** for data visualizations
- **Lucide React** for icons
- **React Router 6** for client-side routing

### Backend
- **FastAPI** for REST API and SSE
- **Python 3.11+** with async/await
- **Pydantic** for request validation
- **aisstream.io** WebSocket for live AIS data
- **PortWatch** CSV data for port congestion
- **Groq LLM** for AI advisor chat

### External Data Sources
- **AIS Stream** (aisstream.io) — Real-time vessel position reports
- **PortWatch** (World Bank) — Port congestion metrics
- **OpenWeatherMap** — Port weather conditions
- **OpenStreetMap/CartoDB** — Map tiles
