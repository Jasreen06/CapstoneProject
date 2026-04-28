# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DockWise AI is a maritime port intelligence dashboard with real-time AIS vessel tracking, congestion forecasting, weather risk analysis, and an AI advisory chat. It targets logistics managers and supply chain analysts.

## Architecture

Three independently running services:

- **Main Backend** (FastAPI, port 8004) — `venv2/backend/api.py`: Port data, forecasting, weather, AI advisor, risk orchestration. Loads CSV data into in-memory DataFrames on startup.
- **AIS Backend** (FastAPI, port 8001) — `venv2/backend/AIS/ais_api.py`: Live vessel positions via WebSocket connection to aisstream.io, served to frontend via SSE stream.
- **Frontend** (React + Vite, port 3000) — `venv2/frontend/`: 4-tab dashboard (Port Intelligence, Live Vessels, Chokepoints, AI Advisor).

### Data Flow

1. `data_pull.py` fetches from IMF PortWatch ArcGIS API using watermark-based incremental pulls → saves to `portwatch_us_data.csv` and `chokepoint_data.csv`
2. `data_cleaning.py` normalizes, deduplicates, computes z-score-based congestion/disruption scores (0-100 scale: LOW 0-33, MEDIUM 34-66, HIGH 67-100)
3. `api.py` loads CSVs on startup, serves endpoints for ports, forecasts, weather, risk, and chat
4. `AIS/ais_consumer.py` connects to aisstream.io WebSocket → `ais_store.py` (in-memory dict) → `ais_api.py` serves via SSE

### Multi-Agent Risk Pipeline (LangGraph)

`agents.py` orchestrates three agents in parallel via LangGraph:
- **Weather Agent** (`weather_agent.py`): wind/visibility/rainfall thresholds → disruption score
- **Congestion Agent** (`congestion_agent.py`): Prophet baseline vs current portcalls → z-score
- **Vessel Agent** (`vessel_agent.py`): Live AIS anchor/moored/incoming classification → delay score

Final risk = 0.40×congestion + 0.25×vessel + 0.35×weather + 0.05×mega_bonus (capped 0-1)

### Forecasting Models

`forecasting.py` provides three models with a uniform interface:
- **ARIMA**: Auto-differencing + grid search (p,q)
- **Prophet**: Yearly/weekly seasonality, multiplicative mode
- **XGBoost**: 25 features (lags, rolling stats, calendar, chokepoint leading indicators at 14/21/28 days)

## Commands

All backend commands require the venv activated first:
```bash
source venv2/venv/bin/activate
```

### Run Services

```bash
# Main backend (port 8004)
cd venv2/backend && python -m uvicorn api:app --port 8004 --reload

# AIS backend (port 8001)
cd venv2/backend && python -m uvicorn AIS.ais_api:app --port 8001

# Frontend (port 3000)
cd venv2/frontend && npm start
```

### Data Refresh

```bash
cd venv2/backend && python data_pull.py
```
First run auto-downloads ~42MB of CSV data (2-5 minutes). Subsequent runs are incremental.

### Frontend Install

```bash
cd venv2/frontend && npm install
```

### Kill Stuck Ports

```bash
lsof -ti :8004 | xargs kill
lsof -ti :8001 | xargs kill
```

## Environment Variables

File: `venv2/backend/.env` (loaded via `python-dotenv` in `api.py`)

| Key | Service | Required For |
|-----|---------|-------------|
| `WEATHER_API_KEY` | OpenWeatherMap | Weather tab, weather agent |
| `GROQ_API_KEY` | Groq (LLaMA-3.3-70B) | AI Advisor chat, risk explanations |
| `AISSTREAM_API_KEY` | aisstream.io | Live Vessels tab |

App starts without keys but affected features return errors/empty data.

## Key Patterns

- **State**: No database — all data lives in in-memory pandas DataFrames loaded from CSVs at startup. Restart backend after data refresh.
- **Port-to-chokepoint mapping**: Regional keyword matching in `api.py:_get_port_chokepoints()`
- **Chokepoint dates**: Arrive as Unix milliseconds from ArcGIS (handled with `convert_date_ms=True` in `data_pull.py`)
- **AIS microservice**: Fully async — WebSocket consumer and SSE endpoints use `asyncio`
- **AI Advisor** (`llm.py`): LangChain + Groq with maritime knowledge base prompt and per-session conversation memory
- **Frontend API layer**: All backend calls centralized in `venv2/frontend/src/hooks/useApi.js`
- **Design system**: Navy background, teal accents, risk colors (red/amber/green) — defined as tokens in `App.jsx`
- **Data freshness**: UI shows green (≤3d), amber (3-7d), red (>7d) indicators based on actual data dates
- **Database**: Code reads from SQLAlchemy (`DATABASE_URL` in `.env`). Local dev uses SQLite: `DATABASE_URL=sqlite:///dockwise_local.db`. Seeded from CSVs (310K port rows, 74K chokepoint rows).
- **Groq rate limit**: `llama-3.3-70b-versatile` has 100K TPD on free tier. `llama-3.1-8b-instant` has separate quota as fallback.

---

## Phased Improvement Plan

### OVERARCHING CONSTRAINTS (apply to ALL phases)
1. Do NOT modify: backend forecasting, BQML, weather agent, AIS microservice, data pipelines, congestion score calc, tier downgrade logic.
2. Do NOT restyle existing UI. Match dark theme (navy bg, teal #10B981, gray borders). No new design tokens.
3. Do NOT introduce new UI libraries unless phase explicitly says so — ask first.
4. Before writing code in each phase, list files to touch and wait for user confirmation.
5. After each phase, append to `venv2/CHANGELOG_DOCKWISE.md`.
6. No opportunistic refactoring — flag in changelog, leave alone.
7. Stop after each phase and wait for user confirmation before starting the next.

### Phase 1: AI Advisor Robustness — COMPLETE
See `venv2/CHANGELOG_DOCKWISE.md` for full details.
- Fixed JSON leak in `llm.py:chat()` parse flow
- Three layers: (A) regex extraction, (B) prompt hardening, (C) safe fallback with apology string
- `answer_text` initialized to `None` instead of `raw` — root cause eliminated
- Follow-up chip failures were a downstream symptom — fixed by ensuring clean answer text
- 7 unit tests passed. Live Groq validation pending (rate limit).

### Phase 2: Interactive Sidebars — NEXT UP

#### 2A: Vessel click → rerouting analysis panel
Extend the existing vessel right sidebar (already shows MMSI, type, status, speed, course, destination, position) with a "Rerouting Analysis" section BELOW existing fields.

Logic:
1. Read vessel's destination. If empty/unresolvable → "No destination set", skip.
2. Look up destination port's current congestion tier.
3. LOW → green badge "Destination clear — no rerouting needed."
4. MEDIUM → amber badge "Moderate congestion expected."
5. HIGH → red badge "Destination congested" PLUS "Suggested alternatives":
   - 3 nearest ports (great-circle from current vessel position) with tier LOW or MEDIUM
   - Clickable rows: port name, distance nm, tier, inbound vessel count
   - Clicking pans/zooms map to that port

**CLIENT-SIDE only.** Use existing port data in state. No backend endpoint. Haversine in utility function.

#### 2B: Port click → info panel
When port anchor icon clicked, open right sidebar:
- Port name, coast (derive: west if lon < -100, gulf if lat < 32 and lon -100 to -80, east otherwise)
- Current congestion tier + score + inbound vessel count
- 7-day trend indicator (if available — don't fabricate)
- "Port Profile" section (2-3 sentences)

#### Port Profile source
Do NOT call Wikipedia at runtime. Instead:
1. Create `venv2/backend/port_profiles.json` with top ~25 ports: `{"name", "profile" (2-3 sentences), "notable": [str, str, str]}`
2. Factual, publicly known info only.
3. Serve via `GET /api/port-profile/{name}` → entry or 404.
4. Frontend fetches on click, caches per session.

#### Validation
- Click 5 vessels with varied destination tiers → rerouting renders correctly
- Click 5 ports including 2 not in profiles → graceful "Profile not available"

#### Files to touch
- `venv2/frontend/src/VesselMap.jsx` (sidebar extension)
- `venv2/frontend/src/utils/geo.js` (new — Haversine helper)
- `venv2/backend/port_profiles.json` (new)
- `venv2/backend/api.py` (new endpoint)
- `venv2/CHANGELOG_DOCKWISE.md`

### Phase 3: AI Advisor Creative Features

#### 3A: "Today's Briefing" auto-card
Above suggested-questions, on load, render 3 auto-generated insight cards (horizontal, vertical on mobile). Each: colored icon, 1-line headline, 2-sentence explanation, "Ask more →" link seeding chat.

New endpoint `POST /api/advisor/briefing`:
1. Pull current port data (tiers, vessel counts)
2. Identify top 3 signals (largest congestion change, highest volatility, most-anomalous port)
3. Structured prompt to Groq → `[{headline, body, seed_question}]`
4. Cache server-side 10 min (in-memory dict + timestamp)

#### 3B: Scenario Simulator
"Scenarios" section below category pills. 4 preset buttons:
- "Panama Canal closes for 72 hours"
- "Labor strike at LA-Long Beach (1 week)"
- "Hurricane hits Gulf ports"
- "Suez Canal restrictions tighten"

Click sends structured prompt to Groq with current data + scenario → returns `{impact_summary, affected_ports[], recommended_reroutes[], confidence}`. Render as structured panel (not chat). Follow-ups can be chat-based.

#### 3C: Port Comparison Mode
"Compare Ports" multi-select 2-3 ports (reuse `MultiSelectDropdown` from VesselMap.jsx). "Compare" → radar chart on 6 axes:
- Congestion score (0-100), Volatility CV, 7-day trend momentum, Weather risk (if available), Upstream chokepoint risk, Inbound vessel count — all normalized.

Use Recharts RadarChart (check if installed first — STOP and ask before adding). Below chart: 2-3 sentences LLM commentary.

#### Validation
- Briefing loads within 3s with meaningful content
- Each scenario returns structured panel, not raw text
- Comparison renders for 2 and 3 ports, axes labeled

#### Files to touch
- `venv2/frontend/src/components/advisor/Briefing.jsx` (new)
- `venv2/frontend/src/components/advisor/ScenarioSimulator.jsx` (new)
- `venv2/frontend/src/components/advisor/PortComparison.jsx` (new)
- `venv2/frontend/src/App.jsx` (wire into advisor tab)
- `venv2/backend/api.py` (new endpoints)
- `venv2/backend/llm.py` (new helper functions)
- `venv2/CHANGELOG_DOCKWISE.md`

### Phase 4: Map Performance Tuning

#### Primary: icon thrashing
`getVesselIcon()` called every vessel every render. Memoize in module-level Map keyed by `(vessel_type + color + selected)` — ~42 possible icons. Verify `getPortAnchorIcon` cache works.

#### Secondary: unnecessary re-renders
- Wrap filtered vessel array with `useMemo` keyed on `(usVessels, typeFilters, statusFilter)` (skip if already done)
- Wrap `MarkerClusterGroup`'s `iconCreateFunction` with `useCallback`

#### Do NOT
Change clustering thresholds, library, add virtualization, debounce without measuring.

#### Validation
React DevTools Profiler: record pan+zoom. Report top 3 components by render time BEFORE and AFTER.

#### Files: `venv2/frontend/src/VesselMap.jsx`, `venv2/CHANGELOG_DOCKWISE.md`

### Phase 5: Light/Dark Mode Toggle

#### Approach: CSS custom properties (NOT full refactor)

**Step 1:** In `venv2/frontend/src/index.css`, define `:root[data-theme="dark"]` and `:root[data-theme="light"]` with CSS variables (--bg-navy, --bg-navy2, --text-ink, --text-ink-mid, --border, --accent-teal). Dark = current values. Light = slate/white equivalents.

**Step 2:** Update T design-token objects in `VesselMap.jsx` and wherever else they live — replace hex values with `var()` references.

**Step 3:** Toggle button in top nav (lucide-react Sun/Moon). Toggles `data-theme` attribute on `document.documentElement` + `localStorage.setItem('dockwise-theme', ...)`. On mount read localStorage, default to dark.

#### Known tricky spots
- **Map tiles:** Dark = CartoDB Dark Matter, Light = CartoDB Positron. Swap tile URL.
- **Leaflet icons:** Hardcoded hex in SVG. Read computed CSS variable at creation time via `getComputedStyle(document.documentElement).getPropertyValue(...)`.
- **Chat bubbles:** Check `App.jsx` for hardcoded backgrounds.
- **Congestion colors (red/amber/green):** Keep as-is in BOTH themes — semantic, not theme.

#### Do NOT
Add "auto"/"system" theme, transitions/animations, rename tokens, refactor T structure.

#### Validation
1. Toggle 5 times — no flicker/layout shift
2. Light mode: all tabs readable, no invisible icons, light map tiles, visible vessels
3. Refresh in light mode — stays light (localStorage)
4. Changelog: describe visual issues found, whether fixed or flagged

#### Files: `index.css`, `VesselMap.jsx`, `App.jsx`, possibly 1-2 other components, `CHANGELOG_DOCKWISE.md`

### Final Reporting (after Phase 5)
Single summary: all files touched, anything flagged but not fixed, new dependencies, total LOC added/removed.
