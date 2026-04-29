# DockWise AI: Multi-Agent Port Congestion Prediction System

> **Full technical report:** [REPORT.md](REPORT.md)

---

## Problem

Port congestion causes cascading supply chain delays and billions in costs. No unified system exists that combines historical port traffic, live vessel positions, weather conditions, and upstream chokepoint disruptions into a single risk view. Existing tools address these signals in isolation.

## Solution

DockWise AI fuses four independent data streams through a multi-agent pipeline into a unified congestion prediction and risk assessment platform for **118 US ports**:

- **IMF PortWatch**: 5+ years of daily vessel arrival history per port
- **Live AIS**: Real-time vessel positions via aisstream.io WebSocket (~1,800+ vessels)
- **OpenWeatherMap**: Current weather and 5-day forecasts
- **Groq LLaMA-3.3-70B**: Natural-language risk explanations and AI advisor

Three specialized agents (Weather, Congestion, Vessel) run in parallel via **LangGraph**, fused by a Risk Orchestrator into a single risk score. The congestion model uses a **V2 Prophet+XGBoost ensemble** achieving **77.4% tier accuracy** on real holdout data. The dashboard offers four forecasting options (Ensemble ★ best, Prophet, ARIMA, XGBoost), the Ensemble is the default and powers both the congestion score gauge and the 7-day outlook for methodological consistency.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Backend | Python, FastAPI, Uvicorn |
| Forecasting | Prophet, XGBoost, ARIMA (statsmodels) |
| Multi-Agent | LangGraph |
| AI / LLM | LangChain, Groq (LLaMA-3.3-70B) |
| AIS Streaming | WebSocket (aisstream.io), Server-Sent Events |
| Frontend | React, Leaflet, Recharts |
| Database | PostgreSQL (Supabase) |
| Deployment | Docker, Google Cloud Run |

## Demo

**Live:** https://dockwise-frontend-322700197744.us-central1.run.app

**Run locally:**
```bash
# 1. Clone and set up environment variables
cp venv2/backend/.env.example venv2/backend/.env
# Fill in: WEATHER_API_KEY, GROQ_API_KEY, AISSTREAM_API_KEY, DATABASE_URL

# 2. Start main backend (port 8004)
cd venv2/backend
python -m uvicorn api:app --port 8004 --reload

# 3. Start AIS backend (port 8001)
python -m uvicorn AIS.ais_api:app --port 8001

# 4. Start frontend (port 3000)
cd venv2/frontend
npm install && npm start
```
Open http://localhost:3000, first load takes ~1 min while V2 scores are computed for all ports.

---

## Production URLs

| Service | URL |
|---------|-----|
| **Frontend** | https://dockwise-frontend-322700197744.us-central1.run.app |
| **Main Backend** | https://dockwise-backend-322700197744.us-central1.run.app |
| **AIS Backend** | https://capstoneproject-322700197744.us-central1.run.app |

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

*DockWise AI v2.0, Capstone Project | April 2026*
