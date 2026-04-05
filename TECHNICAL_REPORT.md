# DockWise AI — Technical Report
## Dataset Analysis, Feature Engineering, Forecasting Methodology & Risk Scoring

---

## Table of Contents

1. [Dataset Overview & Structure](#1-dataset-overview--structure)
2. [Exploratory Data Analysis (EDA)](#2-exploratory-data-analysis-eda)
3. [Data Cleaning Decisions](#3-data-cleaning-decisions)
4. [Feature Engineering — Thinking Process](#4-feature-engineering--thinking-process)
5. [Congestion Risk Scoring — Full Methodology](#5-congestion-risk-scoring--full-methodology)
6. [Forecasting Models — Build & Rationale](#6-forecasting-models--build--rationale)
7. [Model Evaluation Strategy](#7-model-evaluation-strategy)
8. [Chokepoint Disruption Scoring](#8-chokepoint-disruption-scoring)
9. [Weather Risk Scoring](#9-weather-risk-scoring)
10. [XGBoost Chokepoint Feature Design](#10-xgboost-chokepoint-feature-design)
11. [LLM Integration Architecture](#11-llm-integration-architecture)
12. [End-to-End Data Flow Summary](#12-end-to-end-data-flow-summary)

---

## 1. Dataset Overview & Structure

### 1.1 Port Dataset (IMF/World Bank PortWatch)

**Source:** ArcGIS FeatureServer — `Daily_Ports_Data`
**Coverage:** 117 US ports, daily granularity, multi-year history

Each row in `portwatch_us_data.csv` represents **one port on one day**:

| Column | Type | Description |
|--------|------|-------------|
| `date` | string → datetime | YYYY-MM-DD format |
| `portname` | string | e.g., "Los Angeles-Long Beach" |
| `country` | string | Always "UNITED STATES" |
| `portcalls` | float | Total vessel arrivals that day |
| `portcalls_container` | float | Container ship arrivals |
| `portcalls_dry_bulk` | float | Dry bulk carrier arrivals |
| `portcalls_general_cargo` | float | General cargo arrivals |
| `portcalls_roro` | float | Roll-on/Roll-off arrivals |
| `portcalls_tanker` | float | Tanker arrivals |
| `import` → `import_total` | float | Import trade volume (renamed to avoid Python reserved word) |
| `export` → `export_total` | float | Export trade volume |

**Scale of data:**
- ~117 ports × ~365 days/year × several years ≈ **hundreds of thousands of rows**
- Ports range from major hubs (LA-Long Beach: 60–100 portcalls/day) to small inland ports (2–5 portcalls/day)
- Not all ports have complete time series — smaller ports have more gaps

### 1.2 Chokepoint Dataset (IMF/World Bank PortWatch)

**Source:** ArcGIS FeatureServer — `Daily_Chokepoints_Data`
**Coverage:** Major global maritime chokepoints, daily data from ~2019

**Critical data quirk discovered during pull:** The `date` column arrives as **Unix epoch milliseconds**, not a human-readable string.
- Raw value example: `1546300800000`
- Converted: `pd.to_datetime(1546300800000, unit="ms")` → `2019-01-01`
- Fix applied in `data_pull.py`: `convert_date_ms=True` flag during save

Each row represents **one chokepoint on one day**:

| Column | Description |
|--------|-------------|
| `portname` | Chokepoint name (e.g., "Suez Canal") |
| `n_total` | Total vessel transits that day |
| `n_container` / `n_tanker` / `n_dry_bulk` / `n_roro` / `n_general_cargo` | Transits by vessel type |
| `capacity` | Total DWT (deadweight tonnage) of transiting vessels |
| `capacity_container` / `capacity_tanker` / etc. | DWT by vessel type |

**Chokepoints covered:**
- Suez Canal, Panama Canal, Strait of Hormuz, Malacca Strait
- Bab el-Mandeb Strait, Dover Strait, Taiwan Strait, Gibraltar Strait, Luzon Strait
- Danish Straits, Strait of Bosphorus, and others

---

## 2. Exploratory Data Analysis (EDA)

### 2.1 What We Observed in the Port Data

**Distribution of portcalls across ports:**
The data is highly skewed. A handful of mega-ports (LA-Long Beach, Houston, New York/NJ) drive the majority of vessel calls. Smaller ports like Searsport or Davisville have 2–5 calls/day. This immediately told us we **cannot use absolute portcalls numbers** for comparison across ports — a score of "75 vessels/day" means something very different at LA-LB versus Searsport. This drove the decision to use **z-score normalization** (relative scoring against each port's own baseline).

**Temporal patterns observed:**
- Clear **weekly seasonality**: vessel arrivals consistently lower on weekends/Sundays (reduced port operations)
- Clear **annual seasonality**: peak in August–October (pre-Christmas shipping surge), trough around Chinese New Year (January/February factory shutdowns create a 2–3 week lag before vessels bunch up)
- Some ports show strong **monthly seasonality** tied to commodity cycles (grain export seasons, heating oil demand peaks)

**Missing data / zero days:**
Not every port reports every day. Calendar gaps exist — some ports have missing dates (not zero activity, but absent records). The cleaning step fills these gaps with zeros using `resample("D").sum()` + `reindex(full_date_range, fill_value=0)`. This is important because time-series models need a contiguous daily index.

**Negative values:**
Rare but present — likely data entry errors. Clipped to 0 using `.clip(lower=0)` since negative portcalls are physically impossible.

**Duplicate rows:**
Some (portname, date) pairs appeared more than once — likely from API pagination overlaps or re-submissions. Deduplicated by keeping the first occurrence.

### 2.2 What We Observed in the Chokepoint Data

**Transit volumes vary enormously by chokepoint:**
- Malacca Strait: ~80–100 vessels/day (world's busiest lane)
- Dover Strait: ~500 vessels/day (busiest by count)
- Strait of Hormuz: ~20–25 tankers/day
- Bab el-Mandeb: Significant drop-off visible post-late 2023 (Houthi attacks diverted traffic to Cape of Good Hope)

**The 2023–24 Bab el-Mandeb shock is clearly visible in the data:** Transit counts dropped by ~80–90% over a period of weeks — a textbook disruption event that our z-score captures as a very LOW score (traffic well below baseline).

**Vessel mix insights:**
- Suez Canal: Heavy container + tanker mix
- Strait of Hormuz: Almost entirely tanker (energy corridor)
- Malacca Strait: Mixed, with high container share (Asia supply chain)

**Lag relationship observation (key insight):**
By plotting chokepoint disruptions alongside port congestion with a time shift, we observed that spikes or drops at major chokepoints (Malacca Strait, Suez) tend to appear at downstream US ports 14–28 days later. This is the ocean transit time. This observation became the foundation for XGBoost's chokepoint lag features.

### 2.3 Weather Data Profile

**117 port coordinate pairs** hardcoded in `weather.py`. For each port, the OpenWeatherMap API returns:
- Temperature, humidity, pressure (standard meteorological variables)
- Wind speed in m/s (critical for crane and vessel operations)
- Visibility in metres (critical for vessel navigation)
- Precipitation (1-hour accumulation)
- Qualitative description (Clear, Rain, Thunderstorm, etc.)

**Key operational thresholds identified from maritime standards:**
- Container crane operations are typically suspended above **15 m/s (Beaufort 7)**
- Vessel movement in restricted waters is suspended below **1,000m visibility** (VTS fog advisory)
- Critical visibility (< 500m) triggers complete vessel movement restrictions at most ports

---

## 3. Data Cleaning Decisions

### 3.1 Column Renaming
The raw PortWatch API uses `import` and `export` as column names. `import` is a reserved keyword in Python. Renamed immediately to `import_total` / `export_total` at load time to prevent downstream bugs.

### 3.2 Date Parsing
Ports: dates arrive as strings (`"2023-05-14"`) → parsed with `pd.to_datetime(errors="coerce")`. Unparseable dates are dropped (very rare).

Chokepoints: dates arrive as Unix milliseconds → converted with `pd.to_datetime(df["date"], unit="ms")` in `data_pull.py` at save time. All subsequent reads treat the column as a normal YYYY-MM-DD string.

### 3.3 Deduplication Strategy
Using `drop_duplicates(subset=["portname", "date"])` — keeps first occurrence. The rationale: if the same (port, date) pair appears twice, the first fetch is likely the "official" record. No merging/averaging was done because the volumes should be identical if it's a true duplicate.

### 3.4 Zero-Filling vs NaN
All missing numeric values are filled with 0, not NaN. Reasoning:
- A missing `portcalls_container` most likely means zero container ships, not "unknown"
- Time-series models (especially ARIMA/Prophet) cannot handle NaN values mid-series
- Calendar gaps (missing dates) are also filled with 0 — absence from the data = no vessel activity reported

### 3.5 Why We Clip Negatives
Physical constraint: you cannot have negative vessel arrivals. Any negative value is a data artefact. `.clip(lower=0)` is applied to all numeric columns during cleaning.

---

## 4. Feature Engineering — Thinking Process

Feature engineering (`feature_engineering.py`) builds a rich representation of each day's state for the ML model. The thinking follows the question: **"What does a port operations expert look at to understand congestion?"**

### 4.1 Calendar Features — Why They Matter

```python
day_of_week, month, week_of_year, is_weekend, quarter, year
```

**Reasoning:**
- Ports operate differently on weekends vs weekdays (reduced administrative staff, fewer scheduled berths)
- Month captures seasonal shipping peaks (August = pre-Christmas, January/February = post-CNY bunching)
- `is_weekend` as a binary flag gives the model an explicit signal rather than having to infer it from `day_of_week`
- Quarter groups seasonal effects at a coarser level, useful when month-level data is sparse

Without these features, a model trained on average data would systematically over-predict Sunday and under-predict Monday.

### 4.2 Lag Features — The Core Signal

```python
portcalls_lag1, portcalls_lag7, portcalls_lag14, portcalls_lag28
```

**Reasoning:**
- **Lag 1 (yesterday):** Short-term autocorrelation — if a port was busy yesterday, it's likely busy today
- **Lag 7 (same day last week):** Weekly seasonality signal — removes the weekday/weekend effect without explicitly encoding it
- **Lag 14 (two weeks ago):** Medium-term trend; important for catching sustained congestion episodes
- **Lag 28 (four weeks ago):** Monthly cycle; captures demand patterns tied to shipping schedules (most liner services run on roughly 28-day rotations)

The choice of these specific lags was deliberate — they correspond to natural shipping rhythms, not arbitrary round numbers.

### 4.3 Rolling Window Features — Smoothed Trend

```python
portcalls_roll7, portcalls_roll14, portcalls_roll30        # rolling means
portcalls_roll7_std, portcalls_roll14_std, portcalls_roll30_std  # rolling volatility
portcalls_roll7_slope, portcalls_roll30_slope              # momentum
```

**Reasoning:**
- **Rolling means** denoise the series — daily portcall counts have random noise (weather, ship scheduling). A 7-day mean gives a cleaner signal of the underlying trend.
- **Rolling standard deviation** captures volatility. A port with consistently high variability (std) behaves differently from one with stable, predictable flows. The model needs this to calibrate confidence.
- **Rolling slope** is a momentum feature. Computed as `(last_value - first_value) / window`. A positive slope = accelerating congestion; negative = easing. This is a synthetic "momentum" signal that helps the model anticipate turning points.

### 4.4 Flow Features — Trade Balance Signal

```python
net_flow = import_total - export_total
import_export_ratio = import_total / export_total
import_roll7, export_roll7
```

**Reasoning:**
Ports with high net imports (imports >> exports) behave differently from balanced ports. Import-heavy ports generate outbound empty container moves, which add to port congestion without adding cargo value. This ratio contextualizes vessel activity. A West Coast port importing consumer goods from Asia has a very different operational profile than a Gulf Coast port exporting grain.

### 4.5 Vessel Mix Features — Operational Complexity

```python
container_share, tanker_share, dry_bulk_share, general_cargo_share, roro_share
```

**Reasoning:**
Each vessel type has a different **port dwell time and handling complexity:**
- **Container ships:** Require cranes, intense port labor, time-critical (just-in-time schedules). High container share → tighter congestion sensitivity.
- **Tankers:** Single-point mooring, less labor-intensive, longer dwell times but more predictable. High tanker share → smoother congestion dynamics.
- **Dry bulk:** High variability in loading times based on commodity and equipment.
- **RoRo:** Fast turnaround but needs specialized berths.

A day with 90% tanker calls looks operationally different from 90% container calls even if `portcalls` is identical.

### 4.6 Congestion Score as a Feature

```python
congestion_score (0–100), congestion_z (raw z-score)
```

Including the congestion score itself as an input feature for the ML model is intentional. It gives the model the **relative position of today's traffic vs its own history** — the exact same signal that human analysts use. The raw z-score (`congestion_z`) is retained for models that can exploit the unbounded continuous version.

---

## 5. Congestion Risk Scoring — Full Methodology

### 5.1 Why Z-Score Normalization?

The fundamental problem: ports vary enormously in absolute size. A score of 75 portcalls/day means:
- LA-Long Beach: perfectly normal (below average)
- Searsport, ME: extreme congestion (5× its daily average)

Absolute numbers cannot be compared. We need a **relative measure** — "how does today compare to this port's own history?"

The z-score provides exactly this:

```
z = (today's portcalls - rolling_90d_mean) / rolling_90d_std
```

This gives a number that says "today is Z standard deviations above/below the typical level."

### 5.2 Why a 90-Day Rolling Window?

Several alternatives were considered:

| Window | Problem |
|--------|---------|
| 7-day | Too short — the baseline itself moves rapidly, making the score unstable |
| 30-day | Captures monthly patterns but is overly sensitive to outlier weeks |
| 90-day | Covers one full seasonal quarter — stable enough to anchor scores |
| 365-day | Too long — slow to adapt to structural changes (new terminal opening, port dredging) |

90 days was chosen as the best balance between **stability** (not chasing noise) and **responsiveness** (adapting to medium-term structural changes). It also captures roughly one quarter of the business year, which is the planning horizon for most logistics operations.

### 5.3 The ±3 Sigma Clip

```python
z = clip(z, -3, 3)
```

Without clipping, a single extreme outlier (e.g., a COVID lockdown week with 0 portcalls) would generate a z-score of -8 or -10, pushing the score to negative infinity. This is mathematically valid but operationally useless.

Clipping to ±3 sigma means:
- Any event more than 3 standard deviations from normal is treated as "maximally extreme"
- Scores are guaranteed to fall in [0, 100]
- The clip threshold (±3) is the statistical convention for "extremely unusual" in a normal distribution (99.7% of observations fall within ±3σ)

### 5.4 Linear Mapping to 0–100

```python
score = (z + 3) / 6 * 100
```

The z-score range [-3, +3] is linearly mapped to [0, 100]:
- z = -3 → score = 0 (minimum possible — far below normal)
- z = 0 → score = 50 (exactly at the 90-day mean)
- z = +3 → score = 100 (maximum — far above normal)

**Why 50 is "normal":** A score of 50 means today's portcalls equals the 90-day mean exactly. This is the intended "normal" operating point.

### 5.5 Risk Tier Boundaries

```
LOW    : 0–33    (more than 1σ below mean)
MEDIUM : 34–66   (within ±1σ of mean)
HIGH   : 67–100  (more than 1σ above mean)
```

The 33/67 thresholds correspond to approximately **±1 standard deviation** from the mean in the z-score space. This is operationally meaningful:
- Within ±1σ: normal fluctuation, no action needed → MEDIUM
- Beyond +1σ: statistically elevated, monitor/act → HIGH
- Below -1σ: unusually quiet (possible opportunity or seasonal trough) → LOW

### 5.6 Trend Detection

```python
last7  = mean(congestion_score over last 7 days)
prior7 = mean(congestion_score over days 8–14 ago)
diff   = last7 - prior7

"rising"  if diff > 2
"falling" if diff < -2
"stable"  otherwise
```

The threshold of ±2 points (out of 100) was chosen to filter out minor noise. A true trend change needs to move the 7-day average by more than 2 congestion score points to be flagged. This prevents the "rising/falling" indicator from flickering due to day-to-day noise.

### 5.7 Worked Examples

**Example 1 — HIGH congestion:**
```
Today's portcalls = 94 vessels
90-day rolling mean = 78 vessels
90-day rolling std  = 8 vessels

z     = (94 - 78) / 8 = +2.0
score = (2.0 + 3) / 6 × 100 = 83.3  → HIGH
```

**Example 2 — MEDIUM (below normal):**
```
Today's portcalls = 72 vessels
90-day rolling mean = 78 vessels
90-day rolling std  = 8 vessels

z     = (72 - 78) / 8 = -0.75
score = (-0.75 + 3) / 6 × 100 = 37.5  → MEDIUM
```

**Example 3 — LOW (very quiet day):**
```
Today's portcalls = 55 vessels
90-day rolling mean = 78 vessels
90-day rolling std  = 8 vessels

z     = (55 - 78) / 8 = -2.875  → clipped to -3.0
score = (-3 + 3) / 6 × 100 = 0.0  → LOW
```

---

## 6. Forecasting Models — Build & Rationale

Three models were implemented to give users a choice and enable comparison. Each has different strengths:

| Model | Approach | Best For | Confidence Interval Method |
|-------|----------|----------|---------------------------|
| ARIMA | Statistical, linear | Short, stationary series | 95% CI from model's fitted distribution |
| Prophet | Trend + seasonality decomposition | Long series with clear seasonality | Uncertainty samples (Monte Carlo) |
| XGBoost | Gradient boosted trees | Non-linear patterns, cross-feature interactions | ±1.96 × training residual std |

### 6.1 ARIMA

**How it works:**
ARIMA(p, d, q) models the series as a function of:
- `p` lagged values of the series itself (autoregression)
- `d` differencing operations (to achieve stationarity)
- `q` lagged forecast errors (moving average)

**Auto-configuration logic:**
1. **ADF test for `d`:** Run Augmented Dickey-Fuller test. If p-value < 0.05 (series is stationary), use d=0. Otherwise d=1 (first-difference to remove trend).
2. **Grid search for `p`, `q`:** Try all combinations of p ∈ {0,1,2,3} and q ∈ {0,1,2,3}. Select the combination with the lowest AIC (Akaike Information Criterion). AIC penalizes complexity, preventing overfitting.
3. **Final fit:** Re-fit on the full training series with the best (p, d, q).

**Why AIC for model selection?** AIC = 2k - 2ln(L), where k = number of parameters and L = likelihood. It rewards goodness-of-fit while penalizing over-parameterization. Lower AIC = better model.

**Strengths:** Well-understood, fast, interpretable. Works well for ports with simple, near-stationary series.
**Weaknesses:** Linear — cannot capture non-linear interactions. No explicit seasonality handling. Struggles with ports that have strong weekly patterns.

### 6.2 Prophet

**How it works:**
Prophet decomposes the time series into:
```
y(t) = trend(t) + seasonality(t) + holidays(t) + noise
```

- **Trend:** Piecewise linear (with changepoints where the growth rate changes)
- **Yearly seasonality:** Fourier series of order 10 — captures annual shipping cycles
- **Weekly seasonality:** Fourier series of order 3 — captures weekday patterns
- **Uncertainty:** Simulated via `uncertainty_samples=200` (Monte Carlo forecasts)

**Multiplicative vs additive mode:**
```python
mode = "multiplicative" if pdf["y"].min() > 0 else "additive"
```
- **Multiplicative:** Seasonal effect is proportional to trend level. Use when a busy port has bigger absolute swings in busy months (which is typical for shipping).
- **Additive:** Seasonal effect is constant regardless of level. Use when series includes zeros (additive is more stable near zero).

**Changepoint prior scale = 0.05:** This controls how flexible the trend is. Low value (0.05) = conservative, avoids overfitting to short-term fluctuations. Set deliberately conservatively because port traffic trends are gradual; we don't want the model to treat a congestion episode as a permanent trend shift.

**Strengths:** Handles missing data natively. Excellent for series with strong seasonality. Gives intuitive uncertainty bands.
**Weaknesses:** Slower to fit than ARIMA. Multiplicative mode can produce unstable forecasts for ports with near-zero activity.

### 6.3 XGBoost

**How it works:**
Frames the forecasting problem as a **supervised regression task:**
- Features (X): past values, rolling stats, calendar info, chokepoint lags
- Target (y): portcalls at the next day

**Training:** For each position i in the series (starting from max_lag=21), construct a feature vector from the historical window ending at i, with label = portcalls[i]. This gives thousands of training examples from a single port's history.

**Prediction (recursive multi-step):**
For each future day:
1. Build features from the current history buffer
2. Predict the next portcall value
3. Append the prediction to the buffer
4. Repeat for the next day

**Confidence intervals:** Not natively probabilistic. Uses `±1.96 × residual_std` where `residual_std` is the standard deviation of (y_actual - y_predicted) on the training set. This approximates a 95% prediction interval assuming normally distributed residuals.

**Hyperparameter choices:**
```python
n_estimators=200    # enough trees for good fit without excessive compute
learning_rate=0.05  # conservative → more trees needed but better generalization
max_depth=4         # shallow → prevents overfitting on a relatively small dataset
subsample=0.8       # row sampling → regularization
colsample_bytree=0.8 # column sampling → regularization
```

**Strengths:** Captures non-linear interactions between features. The only model that incorporates chokepoint leading indicators. Best for medium-term forecasts where external signals matter.
**Weaknesses:** Cannot extrapolate beyond the training distribution. Requires more data to fit well. Confidence intervals are approximate.

---

## 7. Model Evaluation Strategy

### 7.1 Hold-Out Evaluation

Single split: train on first N days, test on next 7 days. Used for `/api/metrics` endpoint.
```
train = daily[:train_days]
test  = daily[train_days:train_days + horizon]
```

### 7.2 Walk-Forward Cross-Validation

Implemented in `metrics.py` as `walk_forward_splits()`. This is the correct approach for time series:

```
Fold 1: Train [0..364]    Test [365..371]
Fold 2: Train [0..371]    Test [372..378]
Fold 3: Train [0..378]    Test [379..385]
...
```

**Why walk-forward (not random k-fold)?**
Time series data has temporal ordering. Using future data to predict the past is **data leakage**. Walk-forward ensures the model is always trained on past data and evaluated on genuinely unseen future data — exactly how it would be used in production.

### 7.3 Metrics Used

| Metric | Formula | Why Used |
|--------|---------|----------|
| **MAE** | mean(|y_true - y_pred|) | Interpretable in original units (vessels/day). Robust to outliers. |
| **RMSE** | sqrt(mean((y_true - y_pred)²)) | Penalizes large errors more heavily. Good for catching systematic bias. |
| **MAPE** | mean(|error| / |y_true|) × 100% | Percentage error — scale-independent, comparable across ports. Skips zero actuals. |
| **SMAPE** | mean(|error| / ((|y_true| + |y_pred|)/2)) × 100% | Symmetric MAPE — bounded [0, 200%]. More stable near zero than MAPE. |
| **Coverage** | fraction(y_true within [lower, upper]) | Measures whether the confidence intervals are well-calibrated. Target: ~0.95 for 95% CI. |
| **Interval Width** | mean(upper - lower) | Measures precision of confidence intervals. Narrower = more useful. |
| **Fit Time (s)** | Wall clock training time | Practical consideration for API response speed. |

**Why SMAPE as the primary ranking metric?**
MAPE is undefined when `y_true = 0` (which happens at ports with zero-activity days). SMAPE handles this gracefully because the denominator includes both `y_true` and `y_pred`. The `pick_best_model()` function in `metrics.py` uses SMAPE as the primary ranking criterion with MAPE → MAE as fallback.

### 7.4 Coverage Interpretation

Ideally, a 95% prediction interval should contain the actual value 95% of the time (coverage = 0.95). In practice:
- ARIMA: Well-calibrated coverage if model order is correct
- Prophet: Generally good coverage due to Monte Carlo sampling
- XGBoost: Often under-covers (intervals are approximations based on training residuals)

---

## 8. Chokepoint Disruption Scoring

### 8.1 Same Formula, Different Signal

The disruption score for chokepoints uses the **identical z-score methodology** as the port congestion score, but applied to `n_total` (daily transit counts):

```python
rolling_mean = n_total.rolling(90, min_periods=1).mean()
rolling_std  = n_total.rolling(90, min_periods=1).std()
z            = clip((n_total - rolling_mean) / rolling_std, -3, 3)
disruption_score = (z + 3) / 6 * 100
```

### 8.2 What "Disruption" Means

Importantly, a disruption score of 100 (HIGH) can mean either:
- **Extreme traffic:** More vessels transiting than usual (e.g., bunching after a period of delay)
- **Extreme scarcity:** Far fewer vessels than usual (e.g., Bab el-Mandeb during Houthi attacks)

Both extremes represent a deviation from normal that signals supply chain risk. The score is not "high = dangerous" — it's "far from normal = risk." Context (is `n_total` itself high or low?) tells you which direction the disruption is.

### 8.3 Trend Detection for Chokepoints

Same last7/prior7 comparison as ports, but with a threshold of ±1 transit/day (vs ±2 points for congestion score):
```python
diff  = last7_transits - prior7_transits
"rising"  if diff > 1
"falling" if diff < -1
"stable"  otherwise
```

The smaller threshold reflects that chokepoint transit counts are more stable day-to-day (scheduled, predictable routes) than port congestion scores.

---

## 9. Weather Risk Scoring

### 9.1 Operational Thresholds

Weather risk for port operations is based on four independent conditions, each with a threshold:

```python
WIND_HIGH    = 15.0   # m/s ≈ Beaufort 7 (Near Gale): crane ops marginal
WIND_EXTREME = 20.0   # m/s ≈ Beaufort 8 (Gale): crane ops suspended
VIS_LOW      = 1000   # metres: fog advisory, VTS restriction
VIS_CRITICAL = 500    # metres: vessel movement restricted
RAIN_HIGH    = 10.0   # mm/h: heavy rain, bulk cargo loading affected
```

**Source of thresholds:** These align with internationally recognized maritime standards:
- IMO/IACS crane operation guidelines cite ~15 m/s as the operational limit for container cranes
- IALA VTS guidelines specify 1,000m as the standard fog signal advisory threshold
- 500m visibility is the standard "restricted visibility" definition under COLREGS (maritime collision avoidance rules)

### 9.2 Risk Level Logic

```python
def _weather_risk(current):
    level = "LOW"

    if wind >= 20:       level = "HIGH"
    elif wind >= 15:     level = "MEDIUM"

    if vis <= 500:       level = "HIGH"          # overrides wind-only MEDIUM
    elif vis <= 1000:    if level == "LOW": level = "MEDIUM"

    if rain >= 10:       if level == "LOW": level = "MEDIUM"

    if severe_weather (thunderstorm/tornado/hurricane):  level = "HIGH"
```

**Key design principle:** The logic takes the **most severe** individual condition. A strong wind that would normally be MEDIUM can be overridden to HIGH by critical visibility. Conditions combine upward, not downward.

### 9.3 Beaufort Scale Classification

Wind speed is also classified on the Beaufort scale for human readability:

| Speed (m/s) | Beaufort Classification |
|------------|------------------------|
| < 5.5 | Light |
| 5.5 – 10.8 | Moderate |
| 10.8 – 17.2 | Strong |
| 17.2 – 24.5 | Gale |
| ≥ 24.5 | Storm |

### 9.4 Free vs Paid API Fallback

OpenWeatherMap has two forecast endpoints:
- `/data/2.5/forecast/daily`: 16-day daily forecast (paid tier)
- `/data/2.5/forecast`: 5-day with 3-hour intervals (free tier)

The code tries paid first, falls back to free automatically:
```python
# Try paid 16-day daily
r = requests.get(OWM_FORECAST_URL, ...)
if r.status_code == 200:
    return _parse_daily_forecast(r.json())

# Fallback: aggregate 3h intervals to daily
r = requests.get(OWM_FREE_URL, ...)
return _parse_3h_to_daily(r.json(), days)
```

**3-hour aggregation logic (`_parse_3h_to_daily`):**
For each day, groups all 3h readings and takes:
- `temp_max`: max of all 3h readings
- `temp_min`: min of all 3h readings
- `wind_speed_ms`: **max** (not mean) — for risk scoring we care about the worst-case wind, not average
- `rain_mm`: **sum** of all 3h accumulations → daily total
- Mid-day reading for qualitative description and clouds

---

## 10. XGBoost Chokepoint Feature Design

### 10.1 The Leading Indicator Hypothesis

The core idea behind including chokepoints in XGBoost:

> *If transit volumes at Malacca Strait drop today (due to piracy or congestion), the vessels that would have passed through will arrive at US West Coast ports 14–21 days later — either delayed (fewer arrivals in the short term) or bunched (a surge of arrivals once conditions normalize).*

This is the maritime equivalent of a supply chain "bullwhip effect." Chokepoint data at time t provides genuine predictive power for port congestion at time t+14 to t+28.

### 10.2 Lag Selection

```python
CHOKEPOINT_LAGS = [14, 21, 28]   # days
```

These were chosen based on realistic ocean transit times:
- **14 days:** Malacca Strait → US West Coast (typical Transpacific voyage time is ~14–18 days)
- **21 days:** Panama Canal → US East/Gulf Coast; Suez → Europe/Mediterranean
- **28 days:** Suez Canal → US East Coast (Asia-Europe-US routing adds extra time)

### 10.3 The 4 Leading Chokepoints Selected

```python
LEADING_CHOKEPOINTS = ["Suez Canal", "Panama Canal", "Strait of Hormuz", "Malacca Strait"]
```

These 4 were chosen because they collectively cover:
- **All 4 main US port regions:** Each region has different chokepoint dependencies
- **All major commodity types:** Oil (Hormuz), container (Malacca/Suez), both coasts (Panama)
- **Data availability:** These 4 have the longest and most complete records in the chokepoint dataset

### 10.4 Feature Count

With 4 chokepoints × 3 lags = **12 chokepoint features**, plus 13 base features:
- 6 port lag features
- 3 rolling stats
- 4 calendar features

**Total: 25 features per training sample when chokepoint data is available; 13 without.**

If chokepoint data is unavailable (file missing, API error), XGBoost degrades gracefully to 13 features only — this is handled via the `try/except` block in `/api/forecast`.

---

## 11. LLM Integration Architecture

### 11.1 Why LangChain + Groq?

- **Groq:** Provides LLaMA-3.3-70B inference at extremely low latency (~1–2s for a full response). Critical for a real-time chat interface.
- **LangChain:** Provides the conversation memory management, message history handling, and clean abstraction over the LLM API.
- **LLaMA-3.3-70B-versatile:** Large enough to reason about complex maritime relationships; "versatile" variant handles instruction-following well.

### 11.2 Temperature = 0.3

```python
ChatGroq(temperature=0.3)
```

Temperature controls randomness. Lower = more deterministic and factual. 0.3 was chosen to balance:
- **Consistency:** Same question about a port gives a consistent answer
- **Flexibility:** Not so rigid that the model can't paraphrase or synthesize

For a tool giving operational recommendations, consistency and accuracy matter more than creativity.

### 11.3 Context Architecture

Every query to the LLM includes three layers:

```
Layer 1: SYSTEM_PROMPT        (50 tokens, fixed)
  "You are DockWise AI, a maritime port intelligence advisor..."

Layer 2: MARITIME_KNOWLEDGE   (~800 tokens, fixed, sent every query)
  Chokepoint facts, port characteristics, risk thresholds, recommendations framework

Layer 3: LIVE_DASHBOARD_DATA  (~200-400 tokens, dynamic, built per query)
  Current congestion scores, 7-day forecast, weather, upstream chokepoints

Layer 4: CONVERSATION_HISTORY (sliding window, last 8 exchanges)
  Previous Q&A for context continuity

Layer 5: USER_QUESTION        (variable)
  The actual question
```

**Why include MARITIME_KNOWLEDGE in every query?**
The knowledge base is the ground truth for maritime domain facts. Without it, the LLM falls back on its training data (which may be outdated, especially for 2023–2024 events like Houthi attacks). Re-including it every query ensures factual consistency even as the conversation history scrolls away.

### 11.4 Memory Efficiency

The full query (MARITIME_KNOWLEDGE + LIVE_DATA + question) is what gets sent to the LLM, but only the trimmed version is stored in `_history`:
```python
# What gets stored (compact):
_history.append(HumanMessage(content=f"[Port: {port}] {question}"))
_history.append(AIMessage(content=answer))
```

This prevents the history from growing to thousands of tokens. The model sees full context for the current question, but only brief summaries of past exchanges.

---

## 12. End-to-End Data Flow Summary

```
USER OPENS DASHBOARD
    │
    ▼
React selects port (default: first alphabetically)
    │
    ▼
/api/top-ports → returns all 117 ports with current congestion scores
  - get_scored_df() loads CSV, applies z-score to each port's entire history
  - Returns latest row per port, sorted by congestion score
    │
    ▼
User clicks a port (e.g., "Los Angeles-Long Beach")
    │
    ├──► /api/overview?port=Los Angeles-Long Beach
    │      - 90-day trend, vessel mix, cargo flow, KPIs
    │
    ├──► /api/forecast?port=X&model=Prophet&horizon=7
    │      - fits Prophet on full port history
    │      - predicts 7 days ahead
    │      - converts yhat → congestion scores using 90d baseline
    │
    ├──► /api/weather?port=X
    │      - looks up lat/lon from PORT_COORDS
    │      - fetches current + forecast from OpenWeatherMap
    │      - applies _weather_risk() to each data point
    │
    └──► /api/port-chokepoints?port=X
           - maps port to region (West/Gulf/East/Great Lakes)
           - returns 4 upstream chokepoints with disruption scores
    │
    ▼
User asks AI Advisor: "What's causing the current congestion?"
    │
    ▼
POST /api/chat
  - gathers overview, forecast, weather, chokepoints into context
  - calls build_context() → structured text block
  - prepends MARITIME_KNOWLEDGE + SYSTEM_PROMPT
  - calls ChatGroq (llama-3.3-70b-versatile)
  - returns natural language answer
```

---

## Appendix A: Why These Three Models?

These three were selected to represent three different paradigms of time series forecasting:

| Model | Paradigm | Data Requirement | Interpretability |
|-------|---------|-----------------|-----------------|
| ARIMA | Classical statistics | Low (30+ days) | High |
| Prophet | Decomposition | Medium (90+ days) | Medium |
| XGBoost | Machine learning | High (200+ days) | Low |

This gives users a meaningful comparison: ARIMA establishes a simple baseline, Prophet handles seasonality, and XGBoost exploits external signals. In practice, ARIMA tends to win for small/simple ports; Prophet wins for ports with clear seasonal patterns; XGBoost wins when chokepoint signals are present and the port has years of history.

## Appendix B: Scoring Formula Quick Reference

```
CONGESTION SCORE (ports):
  z = clip( (portcalls - rolling_mean_90d) / rolling_std_90d, -3, 3 )
  score = (z + 3) / 6 × 100
  LOW: 0–33  |  MEDIUM: 34–66  |  HIGH: 67–100

DISRUPTION SCORE (chokepoints):
  z = clip( (n_total - rolling_mean_90d) / rolling_std_90d, -3, 3 )
  score = (z + 3) / 6 × 100
  LOW: 0–32  |  MEDIUM: 33–66  |  HIGH: 67–100

WEATHER RISK (port operations):
  HIGH:   wind ≥ 20 m/s  OR  visibility ≤ 500m  OR  severe weather event
  MEDIUM: wind ≥ 15 m/s  OR  visibility ≤ 1000m  OR  rain ≥ 10 mm/h
  LOW:    all conditions below thresholds
```

---

*DockWise AI v1.0 — Technical Report | March 2026*
