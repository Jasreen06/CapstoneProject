# DockWise AI — Maritime Port Intelligence Dashboard
## Full Project Documentation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Data Sources](#3-data-sources)
4. [Data Pipeline](#4-data-pipeline)
5. [Scoring Methodology](#5-scoring-methodology)
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

**DockWise AI** is a real-time maritime port intelligence dashboard that combines:

- Live shipping data from the IMF/World Bank PortWatch API
- Statistical forecasting models (ARIMA, Prophet, XGBoost)
- Global chokepoint disruption monitoring
- Weather-based operational risk scoring
- **Live AIS vessel tracking** via aisstream.io — real-time anchor/moored/incoming vessel classification
- **Multi-agent risk assessment pipeline** (LangGraph) — Weather Agent + Congestion Agent + Vessel Agent → Risk Orchestrator
- An AI advisor powered by Groq (LLaMA-3.3-70B) + LangChain

**Target users:** Logistics managers, port operators, supply chain analysts who need to monitor US port congestion, anticipate disruptions 14–28 days in advance, and get actionable recommendations.

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
│  data_cleaning.py    → Normalisation, dedup, z-score scoring     │
│  forecasting.py      → ARIMA / Prophet / XGBoost models          │
│  weather.py          → OpenWeatherMap fetch + risk scoring        │
│  llm.py              → LangChain + Groq AI workflow              │
│  api.py              → FastAPI REST endpoints (port 8004)         │
│                                                                  │
│  ┌── Multi-Agent Risk Pipeline (LangGraph) ───────────────────┐  │
│  │  congestion_agent.py → Prophet baseline + z-score scoring  │  │
│  │  weather.py          → Weather disruption scoring          │  │
│  │  vessel_agent.py     → Live AIS classification + delay     │  │
│  │  agents.py           → Risk orchestrator (weighted blend)  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  AIS/ais_consumer.py → Live WebSocket feed from aisstream.io     │
│  AIS/ais_store.py    → In-memory vessel store (keyed by MMSI)    │
│  AIS/ais_api.py      → FastAPI REST + SSE endpoints (port 8001)  │
└───────────────────────────┬──────────────────────────────────────┘
                            │  HTTP / JSON / SSE
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   FRONTEND (React + Vite)                         │
│                                                                  │
│  Tab 1: Port Intelligence                                        │
│    CongestionHero, 7-Day Outlook, Trend Timeline,                │
│    WeatherCard, VesselMix, SupplyChainRiskCard                   │
│                                                                  │
│  Tab 2: Live Vessels                                             │
│    VesselMap (Leaflet) — real-time AIS positions, port congestion │
│                                                                  │
│  Tab 3: Chokepoints                                              │
│    ChokepointList, ChokepointDetailPanel                         │
│                                                                  │
│  Tab 4: AI Advisor                                               │
│    Chat interface (Groq LLaMA-3.3-70B)                          │
└──────────────────────────────────────────────────────────────────┘
```

**Server:** FastAPI served by Uvicorn on port **8004**
**AIS Server:** Standalone FastAPI on port **8001** (live vessel streaming)
**Frontend:** React (Vite) on port **5173**
**State:** In-memory cache (DataFrames loaded once per server restart)

---

## 3. Data Sources

### 3.1 IMF PortWatch — US Port Data
- **URL:** ArcGIS FeatureServer (`Daily_Ports_Data`)
- **Coverage:** 117 US ports, daily records
- **History:** Full available history (several years of daily data)
- **Key fields:**
  - `portname` — port name (e.g., "Los Angeles-Long Beach")
  - `date` — date string (YYYY-MM-DD)
  - `portcalls` — total vessel arrivals that day
  - `portcalls_container`, `portcalls_dry_bulk`, `portcalls_general_cargo`, `portcalls_roro`, `portcalls_tanker` — vessel type breakdown
  - `import` (→ renamed `import_total`), `export` (→ renamed `export_total`) — trade flow metrics
- **Stored in:** `venv2/backend/portwatch_us_data.csv`

### 3.2 IMF PortWatch — Global Chokepoint Data
- **URL:** ArcGIS FeatureServer (`Daily_Chokepoints_Data`)
- **Coverage:** Major global chokepoints
- **History:** From 2017-01-01 (API data starts ~2019 in practice)
- **Key fields:**
  - `portname` — chokepoint name (e.g., "Suez Canal")
  - `date` — **raw format is Unix milliseconds** (converted to YYYY-MM-DD on save)
  - `n_total`, `n_container`, `n_dry_bulk`, `n_general_cargo`, `n_roro`, `n_tanker` — daily transit counts by vessel type
  - `capacity`, `capacity_container`, `capacity_cargo`, etc. — deadweight tonnage capacity
- **Stored in:** `venv2/backend/chokepoint_data.csv`

### 3.3 OpenWeatherMap
- **Current weather:** `/data/2.5/weather` — real-time conditions
- **Forecast:** Tries `/data/2.5/forecast/daily` (16-day paid) first; falls back to `/data/2.5/forecast` (5-day/3h free tier) automatically
- **API Key:** `WEATHER_API_KEY` in `.env`

### 3.4 Groq (LLM)
- **Model:** `llama-3.3-70b-versatile`
- **API Key:** `GROQ_API_KEY` in `.env`
- **Framework:** LangChain LCEL (LangChain Expression Language)

### 3.5 aisstream.io (Live AIS)
- **URL:** `wss://stream.aisstream.io/v0/stream` (WebSocket)
- **Coverage:** US waters — 5 bounding boxes (West Coast, Gulf Coast, East Coast, Hawaii, Alaska)
- **Message types:** `PositionReport` (Class A), `StandardClassBPositionReport` (Class B), `ShipStaticData`
- **Key fields:** MMSI, lat/lon, speed over ground (SOG), course over ground (COG), heading, navigational status, vessel name, type, destination, ETA, IMO, call sign
- **API Key:** `AISSTREAM_API_KEY` in `.env`

---

## 4. Data Pipeline

### 4.1 Incremental Pull (`data_pull.py`)

The system uses **watermark-based incremental fetching** — it only downloads data newer than what is already stored.

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

**Pagination logic:** Each ArcGIS batch returns up to 2,000 records. The fetcher loops with `resultOffset` until fewer than 2,000 records are returned (signals end of data). A 200ms sleep between batches prevents rate-limiting.

**First-time run:** If no CSV exists, fetches full history. For chokepoints, the start date is set to `2017-01-01` (pre-COVID baseline).

**Date format quirk fixed:** Chokepoint dates from ArcGIS come as Unix milliseconds (e.g., `1546300800000`). The `_save()` function converts these using `pd.to_datetime(df["date"], unit="ms")`.

### 4.2 Data Cleaning (`data_cleaning.py`)

**Port data (`load_and_clean`):**
1. Rename ambiguous columns: `import` → `import_total`, `export` → `export_total`
2. Parse dates with `errors="coerce"`, drop unparseable rows
3. Strip whitespace from string columns
4. Coerce all numeric columns to float, fill NaN → 0, clip negative values to 0
5. Remove duplicate `(portname, date)` rows
6. Sort by `portname`, `date`

**Chokepoint data (`load_and_clean_chokepoints`):** Same steps, then additionally:
- Computes `disruption_score` and `disruption_level` (see Section 5.2)

**Daily series (`get_port_daily_series`, `get_chokepoint_daily_series`):**
- Filters to a single port/chokepoint
- Resamples to daily frequency (`resample("D").sum()`)
- Fills calendar gaps with zeros (no vessel activity days)

---

## 5. Scoring Methodology

### 5.1 Port Congestion Score

**Formula:** Z-score of `portcalls` against a 90-day rolling baseline, normalized to 0–100.

```python
rolling_mean = portcalls.rolling(90, min_periods=1).mean()
rolling_std  = portcalls.rolling(90, min_periods=1).std()
z            = clip((portcalls - rolling_mean) / rolling_std, -3, 3)
score        = (z + 3) / 6 * 100
```

**Interpretation:**

| Score Range | Level  | Meaning |
|-------------|--------|---------|
| 0 – 33      | LOW    | Traffic below 90-day baseline — port operating with capacity |
| 34 – 66     | MEDIUM | Near-normal — monitor for trend changes |
| 67 – 100    | HIGH   | Traffic significantly above baseline — expect delays, anchorage queues, berth waits 3–5 days |

**Key design decisions:**
- **90-day window** captures seasonal patterns while remaining responsive to recent changes
- **Z-score normalization** makes scores comparable across ports of very different sizes (a small port with 5 calls/day vs. LA-LB with 80+ calls/day)
- **±3 sigma clip** prevents outliers from distorting the scale
- **`min_periods=1`** ensures a score is always available even at the start of the dataset

**7-day trend direction** (used in KPI cards):
```
last7  = mean congestion score over the last 7 days
prior7 = mean congestion score over the 7 days before that
diff   = last7 - prior7

"rising"  if diff > 2
"falling" if diff < -2
"stable"  otherwise
```

**% vs Normal:**
```
pct_vs_normal = (current_score - baseline_mean_90d) / baseline_mean_90d × 100
```

### 5.2 Chokepoint Disruption Score

Uses the **same z-score formula** as the congestion score, but applied to `n_total` (daily transit vessel count) per chokepoint:

```python
rolling_mean = n_total.rolling(90, min_periods=1).mean()
rolling_std  = n_total.rolling(90, min_periods=1).std()
z            = clip((n_total - rolling_mean) / rolling_std, -3, 3)
disruption_score = (z + 3) / 6 * 100
```

**Disruption levels:**

| Score Range | Level  |
|-------------|--------|
| 0 – 32      | LOW    |
| 33 – 66     | MEDIUM |
| 67 – 100    | HIGH   |

**Note:** A HIGH disruption score means unusually HIGH transit traffic (or in a disruption event, unusually LOW — the z-score captures both extremes through the normalization).

### 5.3 Forecasted Congestion Scores

Forecast models predict future `portcalls` values. These are converted to congestion scores using the **90-day historical baseline** anchored to the last known data:

```python
baseline  = hist_vals[-90:]    # last 90 actual portcalls values
mean_90   = baseline.mean()
std_90    = baseline.std()

for each forecast yhat:
    z     = clip((yhat - mean_90) / std_90, -3, 3)
    score = (z + 3) / 6 * 100
```

---

## 6. Forecasting Models

All three models share a common interface: `fit(daily_df)` → `predict(horizon=7)` → DataFrame with columns `[ds, yhat, yhat_lower, yhat_upper, model]`.

### 6.1 ARIMA

**Library:** `statsmodels`

**Auto-configuration:**
1. ADF (Augmented Dickey-Fuller) test determines differencing order `d` (0 if stationary p<0.05, else 1)
2. Grid search over `p ∈ [0,3]`, `q ∈ [0,3]` → selects order with lowest AIC
3. Fits final ARIMA(p, d, q) model on full history

**Output:** `get_forecast(horizon).conf_int(alpha=0.05)` gives 95% confidence intervals.

**Best for:** Short, stationary series; interpretable output.

### 6.2 Prophet

**Library:** `prophet` (Meta/Facebook)

**Configuration:**
- `yearly_seasonality=True` — captures annual shipping cycles (peak season Aug–Oct, CNY dip)
- `weekly_seasonality=True` — captures weekday vs. weekend vessel arrival patterns
- `seasonality_mode="multiplicative"` if min portcalls > 0, else `"additive"`
- `changepoint_prior_scale=0.05` — conservative trend flexibility
- `uncertainty_samples=200` — used for `yhat_lower` / `yhat_upper`

**Best for:** Long time series with strong seasonality; handles missing data gracefully.

### 6.3 XGBoost

**Library:** `xgboost`

**Feature engineering (per training sample):**

| Feature Group | Features | Count |
|--------------|----------|-------|
| Lag features | portcalls at t-1, t-2, t-3, t-7, t-14, t-21 | 6 |
| Rolling stats | 7-day mean, 14-day mean, 7-day std | 3 |
| Calendar | day-of-week, month, year, is_weekend | 4 |
| Chokepoint lags | 4 chokepoints × 3 lags (14/21/28 days) | 12 |
| **Total** | | **25** |

**Chokepoint leading indicators:** XGBoost is the only model that uses chokepoint data as features. The 4 chokepoints used are:
- Suez Canal
- Panama Canal
- Strait of Hormuz
- Malacca Strait

**Lag logic:** Transit volume at these chokepoints 14, 21, and 28 days ago predicts US port arrivals today — reflecting realistic ocean transit times.

**During prediction:** Chokepoint buffers are extended with their last known value (hold-forward assumption) for the forecast horizon.

**Confidence intervals:** ±1.96 × residual standard deviation from training fit.

**Hyperparameters:**
```
n_estimators=200, learning_rate=0.05, max_depth=4,
subsample=0.8, colsample_bytree=0.8, random_state=42
```

**Best for:** Captures non-linear interactions between chokepoints and port traffic; most powerful for medium-term forecasts.

---

## 7. Weather Integration

### 7.1 Data Fetched

**Current conditions** (`fetch_current_weather`):
- Temperature, feels-like, humidity, pressure
- Wind speed (m/s), wind direction, gusts
- Visibility (metres)
- Weather description (Clear, Rain, Fog, etc.)
- Rainfall last 1 hour (mm), snowfall
- Cloud cover %

**Forecast** (`fetch_weather_forecast`):
- Tries paid 16-day daily endpoint first
- Falls back to free 5-day/3-hour endpoint automatically
- Aggregates 3-hour intervals to daily summaries (max wind, max/min temp, total rain)

### 7.2 Weather Risk Scoring

Port operational risk is scored based on four thresholds:

| Condition | Threshold | Risk Level | Operational Impact |
|-----------|-----------|------------|-------------------|
| Wind speed | ≥ 20 m/s (45 mph) | HIGH | Crane operations suspended |
| Wind speed | ≥ 15 m/s (33 mph) | MEDIUM | Crane operations marginal |
| Visibility | ≤ 500 m | HIGH | Vessel movement restricted |
| Visibility | ≤ 1,000 m | MEDIUM | Fog advisory |
| Rainfall | ≥ 10 mm/h | MEDIUM | Bulk cargo loading affected |
| Weather | Thunderstorm/Tornado/Hurricane | HIGH | Severe weather |

**Logic:** Takes the most severe individual condition as the overall risk level.

### 7.3 Port Coordinates

`weather.py` contains a hardcoded `PORT_COORDS` dictionary with lat/lon for all 117 US ports. Used to look up coordinates from port name and pass to OpenWeatherMap API.

---

## 8. Multi-Agent Risk Assessment Pipeline

### 8.1 Architecture

The risk assessment uses a **LangGraph state-graph pipeline** where three independent agents each analyze a different signal, and a fourth orchestrator node blends them into a final score.

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
     │ (live API) │  │ (Prophet)  │  │ (live AIS) │
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
- Outputs: `disruption_score` (0–1), `risk_level` (LOW/MEDIUM/HIGH), `summary`, `active_warnings`

**Congestion Agent (`congestion_agent.py`):**
- Source: PortWatch CSV (historical, ~3–5 day lag)
- Method: Prophet seasonal baseline → z-score of current portcalls vs Prophet expected value
- Outputs: `congestion_score` (0–100), `congestion_ratio`, `trend_direction`, `seasonal_context`, `prophet_expected`
- Prophet config: yearly + weekly seasonality, multiplicative mode, changepoint_prior_scale=0.05

**Vessel Agent (`vessel_agent.py`):**
- Source: Live AIS microservice on port 8001 (real-time)
- Classifies each vessel as:
  - **Moored** — nav_status = "Moored" AND within moored radius (default 5nm)
  - **At Anchor** — nav_status = "At Anchor" AND within anchor radius (default 15nm)
  - **Incoming ≤72h** — destination fuzzy-matches port AND distance/SOG ≤ 72 hours
- Per-port coordinate overrides for ship-channel ports (e.g., South Louisiana uses 60nm anchor radius)
- Mega-vessel detection: draught ≥ 12m at qualifying ports
- Outputs: `vessel_delay_score` (0–1), `vessel_count`, `anchor_count`, `moored_count`, `incoming_72h`, `queue_pressure`, `mega_vessel_flag`, `mega_vessel_count`

**Delay Score formula:**
```
delay_score = 0.60 × queue_contribution    (anchor/berth ratio)
            + 0.40 × surge_contribution    (inbound vs historical median)
            + 0.15 × backlog_bonus         (absolute queue size)
            capped at 1.0
```

**Queue Pressure:**
```
queue_pressure = anchor_count / (moored_count + 1)
```

### 8.3 Risk Orchestrator (`agents.py`)

Blends all three agents into a final risk score:

```
risk_score = 0.40 × congestion_normalized
           + 0.25 × vessel_delay_score
           + 0.35 × weather_disruption_score
           + 0.05 × mega_vessel_bonus       (if mega_vessel_flag is True)
           capped at 1.0
```

**Risk tiers:**

| Score Range | Tier |
|---|---|
| ≥ 0.67 | HIGH |
| ≥ 0.33 | MEDIUM |
| < 0.33 | LOW |

The orchestrator also generates a natural-language explanation via Groq (LLaMA-3.3-70B) incorporating all agent signals: weather conditions, congestion trend, anchor/moored/incoming counts, and queue pressure.

### 8.4 Data Freshness

The pipeline operates on **two different time clocks**:

| Signal | Source | Freshness |
|---|---|---|
| Weather | OpenWeatherMap API | Real-time |
| Vessel (AIS) | aisstream.io WebSocket | Real-time |
| Congestion | PortWatch CSV | ~3–5 day lag (intrinsic to source) |

The UI transparently labels each data point with its actual date and shows a color-coded "Data freshness" indicator (green = current, amber = 3–7 day lag, red = >7 day lag).

---

## 9. LLM AI Advisor

### 8.1 Architecture

```
User Question
     │
     ▼
build_context()          ← assembles live data into structured text
     │
     ▼
MARITIME_KNOWLEDGE       ← static knowledge base (always included)
     │
     ▼
Conversation History     ← sliding window of last 8 exchanges (16 messages)
     │
     ▼
ChatGroq (llama-3.3-70b-versatile)
     │
     ▼
Answer
```

### 8.2 Static Knowledge Base (`MARITIME_KNOWLEDGE`)

Built into `llm.py`, included in every query. Contains:

- **9 global chokepoints:** Suez Canal, Panama Canal, Strait of Hormuz, Malacca Strait, Bab el-Mandeb, Dover Strait, Taiwan Strait, Gibraltar, Luzon Strait — with traffic volumes, risk factors, and historical incidents
- **4 US port clusters:** West Coast, East Coast, Gulf Coast, Great Lakes — with characteristics, TEU volumes, and vulnerabilities
- **Congestion score interpretation** (0–100 scale with operational meanings)
- **Leading indicator lag times** (chokepoint → US port: 14–28 days)
- **Weather risk thresholds** for port operations
- **Seasonal patterns** (peak season, Chinese New Year, hurricane season)
- **Freight rate context** (FBX, Baltic Dry Index benchmarks)
- **Recommendations framework** for HIGH congestion, chokepoint disruptions, and weather risk

### 8.3 Live Context Builder (`build_context`)

Pulls real-time data from the dashboard and formats it as structured text:

```
=== LIVE DASHBOARD DATA ===

Selected Port: Los Angeles-Long Beach
  Congestion Score: 72.3 / 100  (HIGH)
  Last Port Calls: 84.0 vessels/day
  7-Day Trend: rising
  vs 90-Day Normal: +14.2%
  Data as of: 2025-03-20

7-Day Congestion Forecast:
  2025-03-21: score=74.1, level=HIGH
  ...

Port Weather (current):
  Conditions: Clear Sky, Temp: 18°C
  Wind: 6.2 m/s, Gusts: 9.1 m/s
  Visibility: 10000 m
  Ops Risk: LOW — Conditions normal for port operations

Upstream Chokepoints for Los Angeles-Long Beach:
  Malacca Strait: disruption=58 (MEDIUM), trend=stable, transits=82.3 ships/day
  Taiwan Strait: disruption=44 (MEDIUM), ...

Global Chokepoints — HIGH disruption: Bab el-Mandeb Strait
Global Chokepoints — MEDIUM (watch): Suez Canal, Panama Canal
=== END LIVE DATA ===
```

### 8.4 Conversation Memory

- **Sliding window:** Keeps last 8 exchanges (16 messages = 8 human + 8 AI)
- **Memory efficiency:** Only the trimmed user question (without bulky knowledge base) is stored in history
- **Reset:** `/api/chat` accepts `reset_memory: true` to clear history
- **Scope:** Module-level (shared across all users — single-user assumption for now)

### 8.5 LLM Configuration

```python
ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,     # low → more deterministic, factual
    max_tokens=1024,
)
```

---

## 10. API Endpoints

All endpoints run on `http://localhost:8004`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ports` | List all 117 port names |
| GET | `/api/overview?port=X` | KPIs, 90-day trend, vessel mix, cargo flow |
| GET | `/api/top-ports?top_n=50` | All ports ranked by congestion (lowest first) |
| GET | `/api/forecast?port=X&model=Prophet&horizon=7` | 7-day forecast + history |
| GET | `/api/model-comparison` | Saved model evaluation results |
| GET | `/api/metrics?port=X&model=Prophet` | Single hold-out evaluation (MAE, RMSE, MAPE) |
| GET | `/api/port-chokepoints?port=X` | Upstream chokepoints for a specific port |
| GET | `/api/chokepoints` | All chokepoints with current disruption scores |
| GET | `/api/chokepoints/overview?name=X` | Detailed stats for one chokepoint |
| GET | `/api/weather?port=X` | Current weather + 5-day forecast + risk score |
| GET | `/api/risk-assessment?port=X` | Multi-agent risk score (weather + congestion + vessel) |
| POST | `/api/chat` | AI Advisor (LangChain + Groq) |
| GET | `/health` | Health check |

### AIS Endpoints (port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels/stream` | SSE stream — pushes all vessel positions every 5 seconds |
| GET | `/api/vessels` | JSON snapshot of all live vessels with valid lat/lon |
| GET | `/api/vessels/stats` | Summary: total count, breakdown by vessel type and nav status |
| GET | `/health` | Health check |

### `/api/overview` Response Structure
```json
{
  "kpi": {
    "port": "Los Angeles-Long Beach",
    "congestion_score": 72.3,
    "congestion_level": "HIGH",
    "last_portcalls": 84.0,
    "data_lag_days": 3,
    "pct_vs_normal": 14.2,
    "trend_direction": "rising",
    "last_date": "2025-03-20",
    "avg_daily_visits": 78.4,
    "total_incoming": 12400,
    "total_outgoing": 9800
  },
  "trend": [...],
  "vessel_mix": [...],
  "cargo_flow": [...]
}
```

### `/api/chat` Request/Response
```json
// Request (POST body)
{
  "question": "What's causing the current congestion level?",
  "port": "Los Angeles-Long Beach",
  "reset_memory": false
}

// Response
{
  "answer": "The current HIGH congestion score of 72.3 at LA-Long Beach...",
  "port": "Los Angeles-Long Beach"
}
```

### `/api/risk-assessment` Response Structure
```json
{
  "risk_score": 0.42,
  "risk_tier": "MEDIUM",
  "explanation": "Moderate risk driven by...",
  "signals": {
    "weather": {
      "disruption_score": 0.1,
      "risk_level": "LOW",
      "summary": "Clear skies, calm winds",
      "active_warnings": []
    },
    "congestion": {
      "score": 58.3,
      "ratio": 1.12,
      "trend": "rising",
      "seasonal_context": "Off-peak period"
    },
    "vessel": {
      "vessel_count": 31,
      "vessel_delay_score": 0.32,
      "mega_vessel_flag": true,
      "anchor_count": 22,
      "moored_count": 50,
      "incoming_72h": 9,
      "queue_pressure": 0.43,
      "mega_vessel_count": 1
    }
  }
}
```

---

## 11. Frontend Dashboard

Built with React + Vite. Uses Recharts for charts and Leaflet for the vessel map.

### Tab 1: Port Intelligence

| Component | What it shows |
|-----------|---------------|
| **Port selector** (left sidebar) | All ports ranked by congestion score; color-coded LOW/MEDIUM/HIGH |
| **Model selector** | ARIMA / Prophet / XGBoost toggle |
| **CongestionHero** | Score gauge, trend (last 7d in data), % vs normal, data freshness indicator with color-coded lag (green/amber/red). Labels show actual data date ("Ships on 2026-04-03") instead of misleading "Ships yesterday" |
| **7-Day Outlook** | Forecast score for each of the next 7 days |
| **Timeline + Insights** | 90-day historical congestion chart + 7-day forecast overlay |
| **WeatherCard** | Current conditions grid + 5-day forecast strip + risk banner |
| **RiskAssessmentCard** | Multi-agent risk score (0–100) with 3 agent panels side-by-side: **Weather Agent** (disruption score, risk level, warnings), **Congestion Agent** (score vs baseline, trend, seasonal context), **Vessel Agent** (delay score, anchor/moored/incoming counts, queue pressure, mega-vessel badge) |
| **VesselMix** | Monthly vessel type breakdown (stacked bar) |
| **AlternativePorts** | Nearby lower-congestion ports |
| **SupplyChainRiskCard** | 4 upstream chokepoints with disruption score bars |

### Tab 2: Live Vessels

| Component | What it shows |
|-----------|---------------|
| **VesselMap** (Leaflet) | Interactive map of real-time AIS vessel positions in US waters |
| **PortDropdown** | Searchable dropdown of 55 US ports (★ = major port); selects to zoom-to-port |
| **Vessel filters** | Filter by vessel type (Cargo, Tanker, Passenger, etc.) and navigational status |
| **Port congestion circles** | Color-coded circles per port (red/amber/green by congestion score) with sonar pulse animation for HIGH congestion ports |
| **VesselPanel** | Side panel with selected vessel details (MMSI, type, speed, course, destination) |
| **Stats overlay** | Live vessel count + SSE connection status |
| **Legend** | Vessel type colors, nav status colors, port congestion color scale |

- **Data:** SSE stream from AIS backend (port 8001), port congestion from main API (port 8004)
- **Map tiles:** CartoDB Dark (`dark_all`), locked to North America (`maxBounds`)
- **Rendering:** `preferCanvas={true}` for fast rendering of ~4,000+ simultaneous vessel markers

### Tab 3: Chokepoints

| Component | What it shows |
|-----------|---------------|
| **ChokepointList** | All chokepoints ranked by disruption score |
| **ChokepointDetailPanel** | 90-day transit history chart + vessel mix + KPIs for selected chokepoint |

### Tab 4: AI Advisor

- Chat interface with suggested starter questions
- Powered by `/api/chat`
- Shows port context from the currently selected port
- "New chat" button resets conversation memory

### Color Scheme

| Level | Color |
|-------|-------|
| LOW | Green (`#22c55e`) |
| MEDIUM | Yellow (`#eab308`) |
| HIGH | Red (`#ef4444`) |

---

## 12. Port-to-Chokepoint Mapping

Each US port is mapped to 4 relevant upstream chokepoints based on its geographic region and typical trade routes:

| Region | Keywords (partial match) | Chokepoints |
|--------|--------------------------|-------------|
| **West Coast** | los angeles, oakland, seattle, tacoma, san diego, honolulu, etc. | Malacca Strait, Taiwan Strait, Panama Canal, Luzon Strait |
| **Gulf Coast** | houston, new orleans, corpus christi, galveston, mobile, tampa, etc. | Panama Canal, Strait of Hormuz, Bab el-Mandeb Strait, Suez Canal |
| **Great Lakes** | chicago, detroit, cleveland, duluth, milwaukee, etc. | Suez Canal, Panama Canal, Dover Strait, Gibraltar Strait |
| **East Coast** | (default — all other ports) | Suez Canal, Bab el-Mandeb Strait, Panama Canal, Dover Strait |

**Rationale:**
- West Coast imports primarily from Asia → Malacca/Taiwan Strait are leading indicators
- Gulf Coast energy trade → Hormuz and Bab el-Mandeb matter most
- East Coast receives Europe-Asia cargo routed via Suez
- Great Lakes limited to Atlantic trade routes

---

## 13. File Structure

```
Dockwise_AI/
├── README.md                          ← this file
├── start.bat                          ← double-click launcher
│
└── venv2/
    ├── backend/
    │   ├── .env                       ← API keys (WEATHER_API_KEY, GROQ_API_KEY)
    │   ├── requirements.txt           ← Python dependencies
    │   ├── data_pull.py               ← ArcGIS incremental fetch
    │   ├── data_cleaning.py           ← Data normalisation + z-score scoring
    │   ├── forecasting.py             ← ARIMA, Prophet, XGBoost models
    │   ├── metrics.py                 ← MAE, RMSE, MAPE, SMAPE, coverage
    │   ├── weather.py                 ← OpenWeatherMap fetch + risk scoring
    │   ├── congestion_agent.py        ← Prophet baseline + z-score congestion scoring
    │   ├── vessel_agent.py            ← Live AIS vessel classification + delay scoring
    │   ├── agents.py                  ← LangGraph risk pipeline + orchestrator
    │   ├── model_comparison.py        ← Walk-forward CV across all 3 models
    │   ├── llm.py                     ← LangChain + Groq AI workflow
    │   ├── api.py                     ← FastAPI REST server (port 8004)
    │   ├── portwatch_us_data.csv      ← US port data (incremental)
    │   ├── chokepoint_data.csv        ← Global chokepoint data (incremental)
    │   └── AIS/
    │       ├── __init__.py            ← Package init
    │       ├── ais_consumer.py        ← WebSocket consumer for aisstream.io
    │       ├── ais_store.py           ← In-memory vessel store (singleton, keyed by MMSI)
    │       └── ais_api.py             ← FastAPI REST + SSE server (port 8001)
    │
    └── frontend/
        ├── src/
        │   ├── App.jsx                ← Main app + tab switcher (4 tabs)
        │   ├── VesselMap.jsx          ← Live Vessels map (Leaflet + AIS SSE)
        │   ├── hooks/
        │   │   └── useApi.js          ← All API hooks (BASE = http://localhost:8004)
        │   └── components/
        │       ├── CongestionHero.jsx
        │       ├── WeatherCard.jsx
        │       ├── SupplyChainRiskCard.jsx
        │       ├── ChokepointView.jsx
        │       ├── ChokepointDetailPanel.jsx
        │       ├── AIAdvisor.jsx
        │       └── ...
        └── package.json
```

---

## 14. Environment Setup

### Python Dependencies (`requirements.txt`)
```
fastapi
uvicorn
pydantic
pandas
numpy
prophet
statsmodels
xgboost
scikit-learn
requests
python-dotenv
langchain-groq
langchain-core
websockets
```

### Environment Variables (`.env`)
```
WEATHER_API_KEY=your_openweathermap_api_key
GROQ_API_KEY=your_groq_api_key
AISSTREAM_API_KEY=your_aisstream_api_key
```

### Critical: `load_dotenv()` placement

`load_dotenv()` must be called **before** any module that reads environment variables at import time. In `api.py`, this is enforced by placing it before all other local imports:

```python
from dotenv import load_dotenv
load_dotenv()                    # MUST be before weather.py import

from weather import fetch_current_weather, ...
```

`weather.py` reads the API key at **call time** (not import time) to avoid the timing issue:
```python
def _api_key() -> str:
    return os.getenv("WEATHER_API_KEY", "")   # called when fetch_current_weather() runs
```

---

## 15. How to Run

### Option A: `start.bat` (recommended)
Double-click `start.bat` from the project root. It:
1. Kills any process on port 8004
2. Deletes `__pycache__` (prevents stale bytecode)
3. Starts the backend: `venv2/Scripts/python.exe -m uvicorn api:app --port 8004`
4. Starts the frontend: `npm run dev` in `venv2/frontend`

> **First run on a new machine:** The backend will automatically detect missing data files (`portwatch_us_data.csv`, `chokepoint_data.csv`) and download them from the IMF PortWatch API. This one-time download takes **2-5 minutes** (~42MB). Subsequent startups load instantly from the cached CSV files.

### Option B: Manual (if start.bat fails)

**Step 1 — Kill stuck processes (run as Administrator):**
```
taskkill /IM python.exe /F
rmdir /s /q "venv2\backend\__pycache__"
```

**Step 2 — Start backend:**
```
cd venv2/backend
../Scripts/python.exe -m uvicorn api:app --port 8004 --reload
```

**Step 3 — Start AIS backend (separate terminal):**
```
cd venv2/backend
../Scripts/python.exe -m uvicorn AIS.ais_api:app --port 8001
```

**Step 4 — Start frontend (separate terminal):**
```
cd venv2/frontend
npm run dev
```

**Step 5 — Update data (optional, run separately):**
```
cd venv2/backend
../Scripts/python.exe data_pull.py
```

### Accessing the Dashboard
- Frontend: `http://localhost:5173`
- API docs (Swagger): `http://localhost:8004/docs`
- AIS API docs (Swagger): `http://localhost:8001/docs`

---

## 16. Known Issues & Workarounds

### Issue 1: Port 8004 stuck with old server
**Symptom:** API returns old responses; new endpoints show 404.
**Cause:** Multiple Python processes holding the port; Windows blocks non-admin kills.
**Fix:** Kill all `python.exe` processes via Task Manager or run Command Prompt as Administrator:
```
taskkill /IM python.exe /F
```

### Issue 2: WEATHER_API_KEY empty at runtime
**Cause:** `weather.py` originally set `WEATHER_API_KEY = os.getenv(...)` at module import time, before `load_dotenv()` ran.
**Fix:** Changed `weather.py` to use `_api_key()` function that reads env var at call time. `load_dotenv()` moved before all local imports in `api.py`.

### Issue 3: Chokepoint dates as Unix milliseconds
**Cause:** ArcGIS returns the `date` field as Unix epoch milliseconds (e.g., `1546300800000`).
**Fix:** `_save()` in `data_pull.py` accepts `convert_date_ms=True` flag: `pd.to_datetime(df["date"], unit="ms").dt.strftime("%Y-%m-%d")`.

### Issue 4: Stale `__pycache__` serving old code
**Cause:** Python caches compiled bytecode; Uvicorn may serve old `.pyc` files.
**Fix:** `start.bat` deletes `__pycache__` directory before launching server.

### Issue 5: Wrong Python environment
**Cause:** System default `python.exe` points to Anaconda environment, not the project venv.
**Fix:** Always use explicit path: `venv2/Scripts/python.exe -m uvicorn ...`

### Issue 6: Port 8000 permanently occupied
**History:** Earlier development used port 8000. An unkillable process took hold permanently.
**Workaround:** Moved all development to port **8004**. Frontend `BASE_URL` updated accordingly.

### Issue 7: PortWatch data lag (3–12 days)
**Symptom:** Congestion scores reflect a date 3–12 days in the past, not today.
**Cause:** IMF PortWatch has an intrinsic 3–5 day processing lag. If `data_pull.py` hasn't been run recently, the lag compounds further.
**Mitigation:**
- Run `python data_pull.py` daily (or set up a cron job) to minimize self-inflicted lag
- UI now transparently labels all PortWatch-derived numbers with their actual date and a color-coded "Data freshness" indicator
- Live AIS signals (vessel agent) provide real-time context alongside the stale congestion data

### Issue 8: AIS coverage gaps for inland/river ports
**Symptom:** Vessel agent shows 0 vessels for ports like New Orleans, Mobile, Jacksonville, Corpus Christi.
**Cause:** AISStream's satellite/coastal AIS feed doesn't reach inland river ports (Mississippi system, St. Johns River, Mobile Bay). These ports have vessel traffic, but AISStream cannot see it.
**Workaround:** The vessel agent falls back to historical median portcall data for ports with no AIS coverage. The delay score for these ports is based on historical patterns rather than live data.

### Issue 9: Frontend proxy and API base URL mismatch
**Symptom:** Ports not appearing in UI; VesselMap showing fixed congestion of 50 for all ports.
**Cause:** `package.json` proxy and `VesselMap.jsx` API_BASE were pointing to port 8000 instead of 8004.
**Fix:** Updated proxy to `http://localhost:8004` in `package.json` and `API_BASE` in `VesselMap.jsx`.

---

## Appendix: Congestion Score Quick Reference

```
Example 1 — HIGH congestion:
  portcalls_today  = 94  vessels
  rolling_mean_90d = 78  vessels
  rolling_std_90d  =  8  vessels
  z = (94 - 78) / 8 = 2.0
  score = (2.0 + 3) / 6 × 100 = 83.3  → HIGH

Example 2 — MEDIUM congestion:
  portcalls_today  = 72
  rolling_mean_90d = 78
  rolling_std_90d  =  8
  z = (72 - 78) / 8 = -0.75
  score = (-0.75 + 3) / 6 × 100 = 37.5  → MEDIUM

Example 3 — LOW congestion:
  portcalls_today  = 55
  rolling_mean_90d = 78
  rolling_std_90d  =  8
  z = (55 - 78) / 8 = -2.875  (clipped to -3)
  score = (-3 + 3) / 6 × 100 = 0  → LOW
```

---

*DockWise AI v2.0 | April 2026*
