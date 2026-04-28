# DockWise AI — Multi-Agent Port Congestion Prediction System
## Full Project Documentation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Data Sources](#3-data-sources)
4. [Data Pipeline](#4-data-pipeline)
5. [Congestion Scoring — V2 Ensemble](#5-congestion-scoring--v2-ensemble)
6. [Forecasting Models](#6-forecasting-models)
7. [Weather Integration](#7-weather-integration)
8. [Multi-Agent Risk Assessment Pipeline](#8-multi-agent-risk-assessment-pipeline)
9. [LLM AI Advisor](#9-llm-ai-advisor)
10. [API Endpoints](#10-api-endpoints)
11. [Frontend Dashboard](#11-frontend-dashboard)
12. [Port-to-Chokepoint Mapping](#12-port-to-chokepoint-mapping)
13. [File Structure](#13-file-structure)
14. [Environment Setup](#14-environment-setup)
15. [How to Run](#15-how-to-run)
16. [Known Issues & Workarounds](#16-known-issues--workarounds)

---

## 1. Project Overview

**DockWise AI** is a multi-agent port congestion prediction system that combines:

- Live shipping data from the IMF/World Bank PortWatch API (118 US ports)
- Statistical forecasting models (ARIMA, Prophet, XGBoost)
- **V2 ensemble scoring** — Prophet + XGBoost baseline with historical residual std and momentum adjustment
- Global chokepoint disruption monitoring with transit lag estimation
- Weather-based operational risk scoring
- **Live AIS vessel tracking** via aisstream.io — real-time vessel classification (at port / en route)
- **Multi-agent risk assessment pipeline** (LangGraph) — Weather Agent + Congestion Agent + Vessel Agent → Risk Orchestrator
- An AI advisor powered by Groq (LLaMA-3.3-70B) + LangChain

**Target users:** Logistics managers, port operators, supply chain analysts who need to monitor US port congestion, anticipate disruptions, and get actionable recommendations.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│  ArcGIS PortWatch (US Ports)   ArcGIS PortWatch (Chokepoints)  │
│  OpenWeatherMap API             Groq API (LLaMA-3.3-70B)       │
│  aisstream.io (Live AIS)                                        │
└───────────────┬────────────────────────────┬────────────────────┘
                │                            │
                ▼                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + Python)                     │
│                                                                  │
│  data_pull.py        → Incremental CSV download from ArcGIS      │
│  data_cleaning.py    → Normalisation, dedup, scoring             │
│  forecasting.py      → ARIMA / Prophet / XGBoost models          │
│  weather.py          → OpenWeatherMap fetch + risk scoring        │
│  llm.py              → LangChain + Groq AI workflow              │
│  api.py              → FastAPI REST endpoints (port 8004)         │
│                        V2 Prophet+XGBoost ensemble at startup     │
│                                                                  │
│  ┌── Multi-Agent Risk Pipeline (LangGraph) ───────────────────┐  │
│  │  congestion_agent.py → V2 ensemble baseline + z-score      │  │
│  │  weather.py          → Weather disruption scoring          │  │
│  │  vessel_agent.py     → Live AIS classification + delay     │  │
│  │  agents.py           → Risk orchestrator (weighted blend)  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  AIS/ais_consumer.py → Live WebSocket feed from aisstream.io     │
│  AIS/ais_store.py    → In-memory vessel store (keyed by MMSI)    │
│  AIS/ais_api.py      → FastAPI REST + SSE endpoints (port 8001)  │
│                                                                  │
└───────────────────────────┬──────────────────────────────────────┘
                            │  HTTP / JSON / SSE
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   FRONTEND (React)                                │
│                                                                  │
│  Tab 1: Port Intelligence                                        │
│    CongestionHero, 7-Day Outlook, Trend Timeline,                │
│    WeatherCard, VesselMix, SupplyChainRiskCard                   │
│                                                                  │
│  Tab 2: Live Vessels                                             │
│    VesselMap (Leaflet) — real-time AIS positions, port           │
│    congestion circles, clickable ports, sonar pulses,            │
│    permanent labels for major ports                               │
│                                                                  │
│  Tab 3: Chokepoints                                              │
│    ChokepointList, ChokepointDetailPanel                         │
│                                                                  │
│  Tab 4: AI Advisor                                               │
│    Chat interface (Groq LLaMA-3.3-70B)                          │
└──────────────────────────────────────────────────────────────────┘
```

**Server:** FastAPI served by Uvicorn on port **8004** (local) / Cloud Run (production)
**AIS Server:** Standalone FastAPI on port **8001** (local) / Cloud Run (production)
**Frontend:** React on port **3000** (local) / Cloud Run (production)
**State:** In-memory cache (DataFrames loaded from `DATABASE_URL` on startup; V2 scores computed at startup)

### Production URLs (Cloud Run)
| Service | URL |
|---------|-----|
| Frontend | `https://dockwise-frontend-322700197744.us-central1.run.app` |
| Main Backend | `https://dockwise-backend-322700197744.us-central1.run.app` |
| AIS Backend | `https://capstoneproject-322700197744.us-central1.run.app` |

---

## 3. Data Sources

### 3.1 IMF PortWatch — US Port Data
- **URL:** ArcGIS FeatureServer (`Daily_Ports_Data`)
- **Coverage:** 118 US ports, daily records
- **Update schedule:** Weekly on Tuesdays at 9 AM ET, with 3-7 day processing lag (total lag: 4-11 days)
- **Key fields:** `portname`, `date`, `portcalls`, vessel type breakdowns, `import_total`, `export_total`
- **Stored in:** `venv2/backend/portwatch_us_data.csv`

### 3.2 IMF PortWatch — Global Chokepoint Data
- **URL:** ArcGIS FeatureServer (`Daily_Chokepoints_Data`)
- **Coverage:** Major global chokepoints (Suez Canal, Panama Canal, Strait of Hormuz, Malacca Strait, etc.)
- **Key fields:** `portname`, `date` (Unix ms → converted), `n_total`, vessel type breakdowns, capacity metrics
- **Stored in:** `venv2/backend/chokepoint_data.csv`

### 3.3 OpenWeatherMap
- **Current weather + forecast** for all 118 US ports
- **API Key:** `WEATHER_API_KEY` in `.env`

### 3.4 Groq (LLM)
- **Model:** `llama-3.3-70b-versatile`
- **API Key:** `GROQ_API_KEY` in `.env`
- **Framework:** LangChain LCEL

### 3.5 aisstream.io (Live AIS)
- **URL:** `wss://stream.aisstream.io/v0/stream` (WebSocket)
- **Coverage:** US waters — 5 bounding boxes (West Coast, Gulf Coast, East Coast, Hawaii, Alaska)
- **Message types:** `PositionReport`, `StandardClassBPositionReport`, `ShipStaticData`
- **API Key:** `AISSTREAM_API_KEY` in `.env`

---

## 4. Data Pipeline

### 4.1 Incremental Pull (`data_pull.py`)

Uses **watermark-based incremental fetching** — only downloads data newer than what is already stored.

```
run_ports()
  └── get_last_date("portwatch_us_data.csv")   ← reads max(date) from CSV
  └── WHERE country='UNITED STATES' AND date > {last_date}
  └── _paginated_fetch()                        ← batch_size=2000, offset pagination
  └── _save()                                   ← appends to CSV

run_chokepoints()
  └── get_last_date("chokepoint_data.csv")
  └── WHERE date > {last_date}
  └── _paginated_fetch()
  └── _save(convert_date_ms=True)              ← converts Unix ms → YYYY-MM-DD
```

**First-time run:** If no CSV exists, fetches full history automatically on startup.

### 4.2 Data Cleaning (`data_cleaning.py`)

1. Rename ambiguous columns: `import` → `import_total`, `export` → `export_total`
2. Parse dates, drop unparseable rows
3. Strip whitespace, coerce numeric columns, fill NaN → 0, clip negatives
4. Remove duplicate `(portname, date)` rows
5. Sort by `portname`, `date`

---

## 5. Congestion Scoring — V2 Ensemble

### 5.1 Evolution: V1 → V2 → V3

| Version | Approach | Tier Accuracy |
|---------|----------|---------------|
| **V1** | Prophet baseline, prediction interval width as std | 57% |
| **V2** | Prophet+XGBoost ensemble, historical residual std, momentum | **70%** |
| **V3** | V2 + adaptive thresholds + ARIMA + day-of-week adjustment | 51% (worse) |

**Key finding:** V3 over-engineering degraded performance. More complexity does not always improve accuracy. V2 represents the optimal balance.

### 5.2 V2 Scoring Pipeline

The V2 congestion score is computed in three steps:

#### Step 1: Prophet + XGBoost Ensemble Baseline

```python
# Prophet predicts expected portcalls based on seasonality
prophet_expected = Prophet(yearly + weekly seasonality).predict(today)

# XGBoost predicts based on lag features, calendar, chokepoint signals
xgb_expected = XGBoost(25 features).predict(today)

# Ensemble: 60% Prophet (strong at seasonality) + 40% XGBoost (captures non-seasonal)
mean_baseline = 0.6 * prophet_expected + 0.4 * xgb_expected
```

**Why 60/40?** Port traffic is heavily seasonal (holidays, CNY, hurricane season), so Prophet gets higher weight. XGBoost captures volume shifts and port-specific trends Prophet misses.

#### Step 2: Historical Residual Std

```python
# Fit Prophet on 80% of history, predict remaining 20%
# Measure how much actuals deviate from predictions
residuals = actuals[80%:] - prophet_predicted[80%:]
std_est = max(std(residuals), 2.0)    # floor at 2.0 to prevent low-volume port spikes
```

**Why not prediction intervals?** V1 used Prophet's prediction interval width `(upper - lower) / (2 × 1.96)` as std. These intervals were too narrow, making z-scores too extreme — everything looked HIGH or LOW. Historical residual std gives a realistic measure of actual variance.

#### Step 3: 3-Day Momentum + Z-Score

```python
# Momentum: average daily change over last 3 days
momentum = mean(diff(portcalls[-4:]))
adjusted_val = max(current_portcalls + momentum, 0)

# Z-score against ensemble baseline
z = clip((adjusted_val - mean_baseline) / std_est, -3, 3)
congestion_score = (z + 3) / 6 * 100
```

### 5.3 Score Interpretation

| Score | Level | Meaning |
|-------|-------|---------|
| 0–33 | LOW | Below expected — port operating with capacity |
| 34–66 | MEDIUM | Near expected — normal conditions |
| 67–100 | HIGH | Above expected — potential delays, congestion |

**50 = perfectly normal.** A score of 50 means actual traffic exactly matches the Prophet+XGBoost prediction. The score measures deviation from the port's own seasonal baseline, not absolute volume.

### 5.4 Low-Volume Port Handling

Small ports (e.g., Gary, Green Bay) have near-zero baselines. Without safeguards, a single vessel could spike the score to 100. The `std_est` floor of 2.0 prevents this — 1 vessel at a tiny port now scores ~57 (MEDIUM) instead of 100 (HIGH).

---

## 6. Forecasting Models

All three models share a common interface: `fit(daily_df)` → `predict(horizon=7)` → DataFrame with `[ds, yhat, yhat_lower, yhat_upper, model]`.

### 6.1 ARIMA
- **Library:** `statsmodels`
- Auto-configured via ADF test for differencing + AIC grid search for (p, q)
- Best for: short, stationary series

### 6.2 Prophet
- **Library:** `prophet` (Meta)
- Yearly + weekly seasonality, multiplicative mode, `changepoint_prior_scale=0.05`
- Best for: long series with strong seasonal patterns

### 6.3 XGBoost
- **Library:** `xgboost`
- 25 features: 6 lag, 3 rolling stats, 4 calendar, 12 chokepoint lags
- Chokepoint leading indicators: Suez, Panama, Hormuz, Malacca at 14/21/28-day lags
- Best for: non-linear interactions, medium-term forecasts

---

## 7. Weather Integration

### 7.1 Risk Scoring

| Condition | Threshold | Risk Level |
|-----------|-----------|------------|
| Wind speed | >= 20 m/s | HIGH |
| Wind speed | >= 15 m/s | MEDIUM |
| Visibility | <= 500 m | HIGH |
| Visibility | <= 1,000 m | MEDIUM |
| Rainfall | >= 10 mm/h | MEDIUM |
| Thunderstorm/Hurricane | Any | HIGH |

---

## 8. Multi-Agent Risk Assessment Pipeline

### 8.1 Architecture (LangGraph)

```
                    ┌─────────────────┐
                    │  Initial State  │
                    │  (port name)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │  Weather   │  │ Congestion │  │  Vessel    │
     │  Agent     │  │  Agent     │  │  Agent     │
     │ (live API) │  │(V2 ensem.) │  │ (live AIS) │
     └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           ▼
                  ┌─────────────────┐
                  │ Risk Orchestrator│
                  │ (weighted blend) │
                  └────────┬────────┘
                           ▼
              risk_score, risk_tier, explanation
```

### 8.2 Agent Details

**Weather Agent (`weather.py`):**
- Source: OpenWeatherMap API (real-time)
- Outputs: `disruption_score` (0–1), `risk_level`, `summary`, `active_warnings`

**Congestion Agent (`congestion_agent.py`) — V2:**
- Source: PortWatch CSV (3–11 day lag)
- Method: Prophet+XGBoost ensemble baseline → historical residual std → 3-day momentum → z-score
- Outputs: `congestion_score` (0–100), `congestion_ratio`, `trend_direction`, `seasonal_context`, `prophet_expected`

**Vessel Agent (`vessel_agent.py`):**
- Source: Live AIS via port 8001 (real-time)
- Classifies vessels as: **Moored**, **At Anchor**, **Incoming ≤72h**
- Mega-vessel detection: draught >= 12m
- Outputs: `vessel_delay_score` (0–1), vessel counts, `queue_pressure`

### 8.3 Risk Orchestrator (`agents.py`)

```
risk_score = 0.40 * congestion_normalized
           + 0.25 * vessel_delay_score
           + 0.35 * weather_disruption_score
           + 0.05 * mega_vessel_bonus
           capped at 1.0
```

| Score Range | Tier |
|---|---|
| >= 0.67 | HIGH |
| >= 0.33 | MEDIUM |
| < 0.33 | LOW |

### 8.4 Data Freshness

| Signal | Source | Freshness |
|---|---|---|
| Weather | OpenWeatherMap API | Real-time |
| Vessel (AIS) | aisstream.io WebSocket | Real-time |
| Congestion | PortWatch CSV | 4–11 day lag |

---

## 9. LLM AI Advisor

- **Model:** Groq LLaMA-3.3-70B (`temperature=0.3`)
- **Knowledge base:** 9 global chokepoints, 4 US port clusters, seasonal patterns, freight rate context
- **Live context:** Pulls current congestion score, forecast, weather, chokepoint data for the selected port
- **Memory:** Sliding window of 8 exchanges (16 messages)

---

## 10. API Endpoints

### Main API (port 8004)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ports` | List all 118 port names |
| GET | `/api/overview?port=X` | KPIs, 90-day trend, vessel mix, cargo flow |
| GET | `/api/top-ports?top_n=50` | All ports ranked by congestion (V2 scores) |
| GET | `/api/forecast?port=X&model=Prophet&horizon=7` | 7-day forecast + history |
| GET | `/api/model-comparison` | Model evaluation results |
| GET | `/api/port-chokepoints?port=X` | Upstream chokepoints with transit lag + impact notes |
| GET | `/api/chokepoints` | All chokepoints with disruption scores |
| GET | `/api/weather?port=X` | Current weather + forecast + risk score |
| GET | `/api/risk-assessment?port=X` | Multi-agent risk score |
| POST | `/api/chat` | AI Advisor (LangChain + Groq) |

### AIS API (port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels/stream` | SSE stream — vessel positions every 5 seconds |
| GET | `/api/vessels` | JSON snapshot of all live vessels |
| GET | `/api/vessels/stats` | Summary by vessel type and nav status |

---

## 11. Frontend Dashboard

### Tab 1: Port Intelligence
- **Sidebar** (visible only on this tab): Port list sorted by congestion, model selector (Prophet/ARIMA/XGBoost)
- **CongestionHero:** Score gauge, trend, % vs normal, data freshness indicator
- **7-Day Outlook:** Forecasted congestion per day
- **Timeline:** 90-day history + 7-day forecast overlay
- **WeatherCard:** Current conditions + 5-day forecast + risk banner
- **RiskAssessmentCard:** Multi-agent risk score with Weather/Congestion/Vessel agent panels
- **SupplyChainRiskCard:** Upstream chokepoints with disruption scores, transit lag days, and impact prediction notes

### Tab 2: Live Vessels
- **VesselMap** (Leaflet): Real-time AIS vessel positions in US waters
- **Port congestion circles:** All ports show color-coded circles (red/amber/green) with sonar pulse animations — fast red for HIGH, moderate amber for MEDIUM, slow green for LOW
- **Permanent labels:** Major ports show name + score directly on the map
- **Clickable ports:** Click any port circle to zoom in
- **Vessel filtering:** By type (Cargo, Tanker, etc.) and nav status; unknown/no-destination vessels are hidden or dimmed
- **Tooltips:** Show daily arrivals (PortWatch), at-port count (anchored/moored from AIS), en-route count (AIS)
- **Port search dropdown:** Searchable list of 55+ US ports

### Tab 3: Chokepoints
- All chokepoints ranked by disruption score
- 90-day transit history chart + vessel mix + KPIs

### Tab 4: AI Advisor
- Chat interface with suggested starter questions
- Context-aware: uses selected port's live data
- Powered by Groq LLaMA-3.3-70B

---

## 12. Port-to-Chokepoint Mapping

Each US port is mapped to upstream chokepoints based on geographic region, with **real ocean transit lag** times:

### Transit Lag (days from chokepoint to US port region)

| Chokepoint | West Coast | Gulf Coast | East Coast | Great Lakes |
|-----------|-----------|-----------|-----------|------------|
| Malacca Strait | 16 | — | — | — |
| Taiwan Strait | 14 | — | — | — |
| Panama Canal | 14 | 5 | 8 | 18 |
| Suez Canal | — | 30 | 18 | 22 |
| Strait of Hormuz | — | 35 | 28 | — |
| Bab el-Mandeb | — | 28 | 22 | — |
| Dover Strait | — | — | 12 | 20 |
| Korea Strait | 12 | — | — | — |

### Impact Notes (shown on UI)

Based on the chokepoint's current disruption level:
- **HIGH:** "Disruption detected — expect elevated arrivals in ~X days"
- **MEDIUM:** "Monitor — potential impact in ~X days if disruption escalates"
- **LOW:** "Clear — normal transit flow, ~X-day shipping lane"

---

## 13. File Structure

```
DockWise_AI/
├── README.md
├── cloudbuild.frontend.yaml           ← Cloud Build config for frontend deployment
│
└── venv2/
    ├── backend/
    │   ├── .env                       ← API keys (local only — use Cloud Run env vars in prod)
    │   ├── Dockerfile                 ← Main backend container (port 8004)
    │   ├── Dockerfile.ais             ← AIS backend container (port 8001)
    │   ├── api.py                     ← FastAPI server (port 8004) + V2 scoring
    │   ├── data_pull.py               ← ArcGIS incremental fetch
    │   ├── data_cleaning.py           ← Data normalisation + scoring (DB or CSV)
    │   ├── db.py                      ← SQLAlchemy engine (reads DATABASE_URL)
    │   ├── forecasting.py             ← ARIMA, Prophet, XGBoost models
    │   ├── congestion_agent.py        ← V2 ensemble congestion scoring
    │   ├── vessel_agent.py            ← Live AIS vessel classification
    │   ├── weather.py                 ← Weather fetch + risk scoring
    │   ├── weather_agent.py           ← Weather agent wrapper
    │   ├── agents.py                  ← LangGraph risk pipeline + orchestrator
    │   ├── llm.py                     ← LangChain + Groq AI advisor
    │   ├── metrics.py                 ← MAE, RMSE, MAPE, SMAPE, coverage
    │   ├── model_comparison.py        ← Walk-forward CV across models
    │   ├── feature_engineering.py     ← Feature engineering utilities
    │   ├── forecast_tracker.py        ← Forecast tracking
    │   ├── portwatch_us_data.csv      ← US port data (local fallback; prod uses DB)
    │   ├── chokepoint_data.csv        ← Chokepoint data (local fallback; prod uses DB)
    │   └── AIS/
    │       ├── __init__.py
    │       ├── ais_consumer.py        ← WebSocket consumer for aisstream.io
    │       ├── ais_store.py           ← In-memory vessel store (by MMSI)
    │       └── ais_api.py             ← FastAPI REST + SSE server (port 8001)
    │
    └── frontend/
        ├── Dockerfile                 ← Frontend container (nginx, port 80)
        └── src/
            ├── App.jsx                ← Main app (4 tabs, sidebar, all components)
            ├── VesselMap.jsx          ← Live vessel map (Leaflet + AIS SSE)
            ├── hooks/useApi.js        ← API hooks (reads REACT_APP_API_URL at build time)
            └── index.js              ← Entry point
```

---

## 14. Environment Setup

### Python Dependencies
```
fastapi, uvicorn, pydantic, pandas, numpy, prophet, statsmodels,
xgboost, scikit-learn, requests, python-dotenv, langchain-groq,
langchain-core, websockets
```

### Environment Variables (`.env` for local / Cloud Run env vars for production)
```
WEATHER_API_KEY=your_openweathermap_api_key
GROQ_API_KEY=your_groq_api_key
AISSTREAM_API_KEY=your_aisstream_api_key

# Required for Cloud Run — points to Supabase/PostgreSQL (replaces CSV files)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Required for Cloud Run — set to the frontend Cloud Run URL (no trailing slash)
ALLOWED_ORIGINS=https://dockwise-frontend-322700197744.us-central1.run.app
```

---

## 15. How to Run

### Step 1 — Start backend API (port 8004):
```bash
cd venv2/backend
python -m uvicorn api:app --port 8004 --host 0.0.0.0
```
> First request triggers V2 Prophet+XGBoost scoring for all 118 ports (takes 2-4 minutes). Results are cached for the session.

### Step 2 — Start AIS server (port 8001):
```bash
cd venv2/backend
python -m uvicorn AIS.ais_api:app --port 8001 --host 0.0.0.0
```

### Step 3 — Start frontend (port 3000):
```bash
cd venv2/frontend
npm start
```

### Step 4 — Update data (optional):
```bash
cd venv2/backend
python data_pull.py
```
> Best run on Tuesdays after 9 AM ET when PortWatch publishes fresh data.

### Accessing the Dashboard (Local)
- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8004/docs`
- AIS API docs: `http://localhost:8001/docs`

---

## 15b. Cloud Run Deployment

### Prerequisites
- GCP project with Cloud Build, Cloud Run, and Artifact Registry enabled
- Artifact Registry repository `dockwise` created in `us-central1`:
  ```bash
  gcloud artifacts repositories create dockwise \
    --repository-format=docker \
    --location=us-central1
  ```

### Deploy via Cloud Build triggers
Each service has its own Cloud Build config at the project root:
- `cloudbuild.frontend.yaml` — builds and deploys the React frontend
- Backend services are deployed separately with their own Dockerfiles

### Backend env vars (set once per service)
```bash
gcloud run services update dockwise-backend --region=us-central1 \
  --update-env-vars DATABASE_URL="...",GROQ_API_KEY="...",WEATHER_API_KEY="...",\
ALLOWED_ORIGINS="https://dockwise-frontend-322700197744.us-central1.run.app"

gcloud run services update dockwise-ais --region=us-central1 \
  --update-env-vars AISSTREAM_API_KEY="...",\
ALLOWED_ORIGINS="https://dockwise-frontend-322700197744.us-central1.run.app"
```

### Frontend build-time env vars
`REACT_APP_API_URL` and `REACT_APP_AIS_URL` are baked in at build time — they are set as substitutions in `cloudbuild.frontend.yaml` and cannot be changed via Cloud Run env vars.

---

## 16. Known Issues & Workarounds

| Issue | Cause | Fix |
|-------|-------|-----|
| Port 8004 stuck | Multiple Python processes | Kill all python processes, restart |
| Congestion scores all 50 | Backend not running or data not loaded | Start backend, wait for V2 scoring |
| Supply Chain Risk empty | Malformed row in chokepoint CSV | Fixed with `on_bad_lines="skip"` |
| AIS shows 0 vessels for inland ports | AIS feed doesn't reach river ports | Vessel agent falls back to historical data |
| PortWatch data 4-11 days old | Intrinsic source lag + weekly Tuesday updates | Run `data_pull.py` weekly; UI shows data date |
| V2 scoring slow on first request | Prophet fits for 118 ports | One-time cost, cached after first run |
| Low-volume port false HIGH scores | 1 vessel at near-zero baseline | std floor of 2.0 prevents z-score spikes |
| No ports shown on Cloud Run frontend | `REACT_APP_API_URL` baked in as placeholder at build time | Update `cloudbuild.frontend.yaml` substitutions with real backend URLs and retrigger build |
| CORS errors in browser console | `ALLOWED_ORIGINS` not set on backend Cloud Run services | Set `ALLOWED_ORIGINS` env var to frontend Cloud Run URL (no trailing slash) on both backend services |
| `top-ports` / `top-loaded-ports` slow on Cloud Run | Prophet fits 118 ports on first request; Cloud Run cold start adds latency | Results are cached after first call; subsequent requests are fast |

---

*DockWise AI v2.0 — Multi-Agent Port Congestion Prediction System | April 2026*
