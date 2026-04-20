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
