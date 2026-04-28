# DockWise AI — Multi-Agent Port Congestion Prediction System
## Capstone Project Report

---

## 1. Problem Statement

Global supply chains depend on the efficient flow of goods through maritime ports. Port congestion — when vessel arrivals exceed a port's processing capacity — causes cascading delays, increased costs, and supply chain disruptions. The COVID-19 pandemic exposed how vulnerable these systems are: in 2021, ships waited 2-3 weeks to dock at Los Angeles-Long Beach alone.

**The challenge:** There is no unified system that combines historical port traffic patterns, live vessel positions, weather conditions, and upstream chokepoint disruptions to predict port congestion. Existing tools address these signals in isolation.

**Our solution:** DockWise AI is a multi-agent system that fuses four independent data streams — historical port data (IMF PortWatch), live vessel tracking (AIS), weather forecasts (OpenWeatherMap), and global chokepoint monitoring — into a single congestion prediction and risk assessment platform for 118 US ports.

---

## 2. System Architecture

DockWise AI consists of three layers:

### 2.1 Data Layer
- **IMF PortWatch:** Daily vessel arrival counts for 118 US ports and major global chokepoints (updated weekly on Tuesdays)
- **AIS (Automatic Identification System):** Real-time vessel positions, speeds, destinations, and navigational status via aisstream.io WebSocket
- **OpenWeatherMap:** Current conditions and 5-day forecasts for port locations
- **Groq LLaMA-3.3-70B:** Large language model for natural-language risk explanations

### 2.2 Intelligence Layer
- **Forecasting Engine:** Three statistical models (ARIMA, Prophet, XGBoost) generate 7-day portcall predictions
- **V2 Ensemble Scoring:** Prophet + XGBoost ensemble baseline with historical residual std and momentum adjustment for congestion scoring
- **Multi-Agent Pipeline (LangGraph):** Three independent agents (Weather, Congestion, Vessel) analyze different signals, fused by a Risk Orchestrator into a unified risk score
- **AI Advisor:** Context-aware conversational agent powered by Groq LLaMA-3.3-70B

### 2.3 Presentation Layer
- **React Dashboard:** Four-tab interface — Port Intelligence, Live Vessels (interactive Leaflet map), Chokepoints, AI Advisor
- **Real-time updates:** AIS vessel positions stream via Server-Sent Events (SSE), refreshing every 5 seconds

---

## 3. Congestion Scoring Methodology

### 3.1 The Core Problem

How do you define "congested" for a port? A raw vessel count is meaningless without context — 10 ships at Los Angeles is quiet; 10 ships at Gary, Indiana is unprecedented. The score must be relative to each port's own seasonal baseline.

### 3.2 V1 Approach (Baseline)

The initial approach used Prophet's prediction interval width as the standard deviation for z-score computation:

```
z = (actual - prophet_expected) / ((upper - lower) / 3.92)
score = (z + 3) / 6 * 100
```

**Problem:** Prophet's prediction intervals were too narrow, making z-scores too extreme. Ports were frequently classified as HIGH or LOW with little MEDIUM.

**Result:** 57% tier accuracy on holdout backtest.

### 3.3 V2 Approach (Final)

Three improvements were made:

**1. Historical Residual Std** — Instead of using Prophet's prediction intervals, we fit Prophet on 80% of history, predict the remaining 20%, and measure the actual standard deviation of residuals. This gives a realistic measure of how much traffic normally deviates from predictions.

**2. Prophet + XGBoost Ensemble (60/40)** — Prophet captures seasonality (yearly cycles, weekly patterns). XGBoost captures non-seasonal signals (recent trends, chokepoint-port interactions). The 60/40 blend reduces individual model errors.

**3. 3-Day Momentum** — The average daily change over the last 3 days is added to the current value before scoring. This captures short-term trends (e.g., traffic ramping up before a holiday).

**Result:** 70% tier accuracy — a 13-point improvement over V1.

### 3.4 V3 Experiment (Over-Engineering)

We tested adding adaptive thresholds, ARIMA as a third ensemble member, and day-of-week adjustments. Accuracy **dropped to 51%** — 19 points below V2.

**Key finding:** More model complexity does not always improve performance. The V3 additions introduced more noise than signal. This validates the principle of parsimony — the simplest model that captures the dominant patterns (seasonality + recent trends) outperforms more complex alternatives.

### 3.5 Low-Volume Port Handling

Small ports (e.g., Gary, Green Bay) have near-zero baselines. A single vessel would cause a z-score spike to 100 (HIGH). We enforce a minimum std floor of 2.0 to prevent this — 1 vessel at a tiny port scores ~57 (MEDIUM) instead of 100.

---

## 4. Multi-Agent Risk Assessment

### 4.1 Why Multi-Agent?

No single data source captures the full picture of port risk:

| Signal | Source | Strength | Weakness |
|--------|--------|----------|----------|
| Historical portcalls | PortWatch | Seasonal patterns | 4-11 day data lag |
| Live vessel positions | AIS | Real-time | No historical context |
| Weather | OpenWeatherMap | Real-time | Doesn't predict traffic |

A multi-agent architecture lets each signal be analyzed by a specialized agent, then fused by an orchestrator that understands the relative reliability and freshness of each source.

### 4.2 Agent Descriptions

**Weather Agent:** Queries OpenWeatherMap for current conditions. Scores wind speed, visibility, rainfall, and severe weather against operational thresholds. A HIGH weather risk means cranes may stop, vessel movement restricted.

**Congestion Agent:** Runs the V2 ensemble pipeline on PortWatch data. Outputs congestion score (0-100), congestion ratio (actual/expected), trend direction, and seasonal context (peak season, CNY, hurricane season).

**Vessel Agent:** Queries the live AIS microservice. Classifies each vessel near the port as moored, at anchor, or incoming (within 72 hours). Computes queue pressure (anchor/moored ratio) and surge contribution (inbound vs historical median). Detects mega-vessels (draught >= 12m).

### 4.3 Risk Orchestrator

Blends all three signals with learned weights:
```
risk_score = 0.40 * congestion + 0.25 * vessel_delay + 0.35 * weather
```

Generates a natural-language explanation via Groq LLaMA-3.3-70B incorporating all signals.

### 4.4 Chokepoint-Port Correlation

We investigated whether chokepoint disruptions statistically predict port congestion using anomaly-based lagged cross-correlation. All correlations were weak (r < 0.15). This validates the multi-agent fusion approach — chokepoint signals are informative as context but not predictive in isolation. The transit lag lookup (real ocean shipping times from chokepoint to US port region) provides the actionable connection.

---

## 5. Live Vessel Tracking

### 5.1 AIS Data Pipeline

```
aisstream.io WebSocket → ais_consumer.py → ais_store.py → ais_api.py → SSE → VesselMap
```

- WebSocket connection receives ~1,800+ vessel positions across US waters
- In-memory store keyed by MMSI (Maritime Mobile Service Identity)
- SSE endpoint pushes full vessel list every 5 seconds to the frontend
- Vessels are filtered to US-bound (destination matching) or in US waters (bounding box)

### 5.2 Vessel Classification on the Map

- **Hidden:** Vessels with unknown type AND no destination (no useful information)
- **Dimmed:** Vessels with a type but no destination (visible at 25% opacity)
- **Full visibility:** Vessels with a destination
- **Tooltip shows:** At port (anchored/moored) count vs en-route count per port

### 5.3 Port Visualization

- All 118 ports shown with congestion-colored circles (red/amber/green)
- Sonar pulse animations on all ports — speed and intensity vary by congestion level
- Permanent name labels for 15 major ports
- Clickable to zoom in

---

## 6. Validation Results

### 6.1 Holdout Backtest

**Setup:** Train on data up to cutoff date, predict next 7 days, compare against actuals. Tested across 19 top US ports.

| Metric | V1 | V2 | Improvement |
|--------|----|----|-------------|
| Tier Accuracy | 57.1% | 67.7% | +10.6% |
| Congestion Score MAE | 16.6 | 13.0 | -3.6 |
| Portcall MAE | 3.1 | 2.8 | -0.3 |

### 6.2 Multi-Window Walk-Forward

**Setup:** 4 cutoff windows across the dataset, 19 ports each, 532 total predictions.

| Version | Approach | Tier Accuracy |
|---------|----------|---------------|
| V1 | Prophet only | 57.0% |
| **V2** | **Ensemble + residual std + momentum** | **70.1%** |
| V3 | V2 + adaptive + ARIMA + DoW | 51.3% |

### 6.3 Per-Port Performance (V2)

V2 wins or ties on 17 out of 19 ports. Only Tacoma shows V1 performing better (likely due to its unusual traffic pattern not fitting the ensemble assumptions).

### 6.4 Real Holdout Validation (April 2026)

**Setup:** Predictions saved on 2026-04-28 for dates 2026-04-18 → 2026-04-24 using live V2 model. Validated against actual PortWatch data after publication. 12 ports, 84 prediction-actual pairs.

| Metric | Result |
|--------|--------|
| **Tier Accuracy** | **77.4%** |
| Congestion Score MAE | 12.0 / 100 |
| Congestion Score RMSE | 15.5 / 100 |
| Portcall MAE | 1.4 portcalls |
| 95% Interval Coverage | 96.4% |
| **Directional Accuracy** | **73.6%** |
| **Skill Score vs Naive Baseline** | **+16.0%** |
| Cohen's Kappa | 0.145 |

**Key observations:**
- 77.4% tier accuracy on true out-of-sample data confirms V2 generalizes well beyond backtests
- Model beats naive "tomorrow = today" persistence baseline by 16%
- 73.6% directional accuracy — reliable trend-direction signal for logistics decisions
- HIGH tier precision = 100% (never false alarms), but recall = 16.7% (conservative — misses some HIGH events)
- Cohen's Kappa = 0.145 reflects class imbalance (most days are MEDIUM)

---

## 7. Supply Chain Risk — Chokepoint Integration

### 7.1 Transit Lag Model

Each port-chokepoint pair has a real ocean transit time lookup based on typical shipping routes:

- West Coast ← Malacca Strait: ~16 days
- Gulf Coast ← Panama Canal: ~5 days
- East Coast ← Suez Canal: ~18 days
- Gulf Coast ← Strait of Hormuz: ~35 days

### 7.2 Impact Prediction

The UI shows actionable impact notes based on current disruption level:

- **HIGH disruption:** "Disruption detected — expect elevated arrivals in ~X days"
- **MEDIUM:** "Monitor — potential impact in ~X days if disruption escalates"
- **LOW:** "Clear — normal transit flow, ~X-day shipping lane"

This connects the abstract chokepoint data to concrete port-level predictions.

---

## 8. AI Advisor

The AI Advisor uses Groq's LLaMA-3.3-70B model with:

- **Static knowledge base:** Maritime domain knowledge covering 9 chokepoints, 4 port clusters, seasonal patterns, freight rate benchmarks
- **Live context:** Current congestion score, forecast, weather, and chokepoint data for the selected port
- **Conversation memory:** Sliding window of 8 exchanges

This allows users to ask natural-language questions like "What's causing high congestion at LA?" and get answers grounded in the actual dashboard data.

---

## 9. Technical Challenges

### 9.1 Data Lag
PortWatch data has a 4-11 day lag (3-7 day processing + weekly publication). This is the fundamental challenge — the congestion score reflects the past, not today. Live AIS data partially compensates by providing real-time vessel positions.

### 9.2 AIS Coverage Gaps
The AIS feed doesn't reach inland/river ports (Mississippi system, Mobile Bay). The vessel agent falls back to historical median data for these ports.

### 9.3 Model Complexity vs. Accuracy
V3 showed that adding more models and adjustments can hurt performance. The optimal approach is the simplest one that captures the dominant patterns.

### 9.4 Low-Volume Port Scoring
Ports with near-zero traffic required special handling to prevent false HIGH scores from single vessels. The std floor of 2.0 solves this.

### 9.5 Startup Performance
V2 Prophet+XGBoost scoring for 118 ports takes 2-4 minutes at startup. This is a one-time cost — results are cached for the session.

---

## 10. Technologies Used

| Component | Technology |
|-----------|-----------|
| Backend API | Python, FastAPI, Uvicorn |
| Forecasting | Prophet, XGBoost, ARIMA (statsmodels) |
| Multi-Agent Pipeline | LangGraph |
| AI Advisor | LangChain, Groq (LLaMA-3.3-70B) |
| AIS Streaming | WebSocket (aisstream.io), Server-Sent Events |
| Frontend | React, Leaflet (maps), Recharts |
| Data Source | IMF PortWatch (ArcGIS), OpenWeatherMap, aisstream.io |

---

## 11. Future Work

- **AWS deployment** for 24/7 AIS data collection and scheduled data pulls
- **Prediction intervals** on the forecast chart for uncertainty visualization
- **Port capacity data** from Army Corps of Engineers to compute actual utilization rates
- **Historical AIS aggregation** to build a real-time portcall counter independent of PortWatch lag
- **Model retraining pipeline** to automatically update Prophet/XGBoost as new data arrives

---

*DockWise AI — Multi-Agent Port Congestion Prediction System*
*Capstone Project | April 2026*
