# DockWise AI — Multi-Agent Port Congestion Prediction System

A multi-agent maritime intelligence dashboard combining live AIS vessel tracking, PortWatch historical data, weather risk, and LLM-powered analysis for 118 US ports.

> **Full technical report:** [REPORT.md](REPORT.md)

---

## Live URLs (Google Cloud Run)

| Service | URL |
|---------|-----|
| **Frontend** | https://dockwise-frontend-322700197744.us-central1.run.app |
| **Main Backend** | https://dockwise-backend-322700197744.us-central1.run.app |
| **AIS Backend** | https://capstoneproject-322700197744.us-central1.run.app |

---

## Architecture

```
ArcGIS PortWatch ──┐
OpenWeatherMap  ──┤──► FastAPI Backend (8004) ──► React Frontend (3000)
Groq LLaMA-70B  ──┤         ▲ LangGraph multi-agent pipeline
aisstream.io    ──┘──► AIS Backend (8001) ──────► Live Vessels tab (SSE)
                              ▲ PostgreSQL (Supabase)
```

Three independently running services:
- **Main Backend** (`venv2/backend/api.py`) — port 8004
- **AIS Backend** (`venv2/backend/AIS/ais_api.py`) — port 8001
- **Frontend** (`venv2/frontend/`) — port 3000

---

## Environment Variables

Create `venv2/backend/.env`:

```
WEATHER_API_KEY=your_openweathermap_key
GROQ_API_KEY=your_groq_key
AISSTREAM_API_KEY=your_aisstream_key
DATABASE_URL=postgresql://user:password@host:5432/dbname
ALLOWED_ORIGINS=http://localhost:3000
```

---

## Run Locally

```bash
# 1. Main backend (port 8004)
cd venv2/backend
python -m uvicorn api:app --port 8004 --reload

# 2. AIS backend (port 8001)
cd venv2/backend
python -m uvicorn AIS.ais_api:app --port 8001

# 3. Frontend (port 3000)
cd venv2/frontend
npm install && npm start
```

> First request triggers V2 Prophet+XGBoost scoring for all ports (~1 min). Cached for the session.

Refresh data (run on Tuesdays after 9 AM ET):
```bash
cd venv2/backend && python data_pull.py
```

---

## File Structure

```
venv2/
├── backend/
│   ├── api.py                  ← FastAPI server + V2 scoring
│   ├── data_pull.py            ← ArcGIS incremental fetch
│   ├── data_cleaning.py        ← Normalisation + scoring (DB or CSV fallback)
│   ├── db.py                   ← SQLAlchemy engine
│   ├── forecasting.py          ← ARIMA, Prophet, XGBoost
│   ├── congestion_agent.py     ← V2 ensemble agent
│   ├── vessel_agent.py         ← Live AIS classification
│   ├── weather.py / weather_agent.py
│   ├── agents.py               ← LangGraph orchestrator
│   ├── llm.py                  ← LangChain + Groq
│   ├── backtest.py             ← V1/V2 backtest
│   ├── save_predictions_v2.py  ← Save forecast snapshots
│   ├── validate_predictions.py ← Compare forecasts vs actuals
│   ├── Dockerfile / Dockerfile.ais
│   └── AIS/
│       ├── ais_consumer.py     ← WebSocket consumer
│       ├── ais_store.py        ← In-memory vessel store
│       └── ais_api.py          ← SSE server
└── frontend/
    ├── src/
    │   ├── App.jsx             ← 3-tab dashboard
    │   ├── VesselMap.jsx       ← Leaflet map + AIS
    │   ├── hooks/useApi.js
    │   └── components/advisor/
    └── Dockerfile
```

---

## Known Limitations

| Issue | Cause |
|-------|-------|
| PortWatch data 4–11 days old | Weekly Tuesday publication + processing lag |
| AIS shows 0 for inland ports | Shore-based receivers don't reach river/lake ports |
| V2 scoring slow on first load | Prophet fits 118 ports at startup (~1 min) |

---

*DockWise AI v2.0 — Capstone Project | April 2026*
