"""
api.py
======
FastAPI backend — serves cleaned data, metrics, forecasts, and model comparison
results to the React dashboard.

Start:  uvicorn api:app --reload --port 8000
"""

from __future__ import annotations
import json
import logging
import os
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Import our pipeline modules ──────────────────────────────
from dotenv import load_dotenv
load_dotenv()

from data_cleaning import (load_and_clean, get_port_daily_series,
                            load_and_clean_chokepoints, get_chokepoint_daily_series)
from forecasting import ALL_MODELS, get_model
from metrics import evaluate_forecast
from weather import fetch_current_weather, fetch_weather_forecast
from llm import chat as llm_chat
from forecast_tracker import save_forecast, validate, get_log

# Chokepoints used as leading indicators in XGBoost (global trade coverage)
LEADING_CHOKEPOINTS = ["Suez Canal", "Panama Canal", "Strait of Hormuz", "Malacca Strait"]

# Port region → relevant upstream chokepoints + typical transit lag (days)
_WEST_COAST  = ["Malacca Strait", "Taiwan Strait", "Panama Canal", "Luzon Strait"]
_GULF_COAST  = ["Panama Canal", "Strait of Hormuz", "Bab el-Mandeb Strait", "Suez Canal"]
_EAST_COAST  = ["Suez Canal", "Bab el-Mandeb Strait", "Panama Canal", "Dover Strait"]
_GREAT_LAKES = ["Suez Canal", "Panama Canal", "Dover Strait", "Gibraltar Strait"]

_WEST_KEYWORDS  = ["los angeles","long beach","seattle","tacoma","oakland","san diego",
                    "portland","san francisco","everett","olympia","anchorage","honolulu",
                    "richmond, ca","benicia","el segundo"]
_GULF_KEYWORDS  = ["houston","new orleans","corpus christi","galveston","baton rouge",
                    "beaumont","port arthur","lake charles","mobile","tampa","pensacola",
                    "south louisiana","port lavaca","freeport","pascagoula"]
_LAKES_KEYWORDS = ["chicago","detroit","cleveland","toledo","gary","duluth","milwaukee",
                    "indiana harbor","ashtabula","burns harbor","sandusky","presque isle",
                    "muskegon","green bay","port huron","superior"]

def _get_port_chokepoints(port: str) -> list[str]:
    p = port.lower()
    if any(k in p for k in _WEST_KEYWORDS):
        return _WEST_COAST
    if any(k in p for k in _GULF_KEYWORDS):
        return _GULF_COAST
    if any(k in p for k in _LAKES_KEYWORDS):
        return _GREAT_LAKES
    return _EAST_COAST  # default: East Coast

app = FastAPI(title="DockWise AI — PortWatch API", version="1.0")

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE        = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
CHOKEPOINT_FILE  = os.environ.get("CHOKEPOINT_FILE", "chokepoint_data.csv")
COMPARISON_FILE  = "model_comparison_results.json"

# ──────────────────────────────────────────────
# In-memory cache for the loaded dataset
# ──────────────────────────────────────────────

_cache: dict = {}


def get_df() -> pd.DataFrame:
    if "df" not in _cache:
        if not Path(DATA_FILE).exists():
            raise HTTPException(503, f"Data file '{DATA_FILE}' not found. Set DATA_FILE env var or place the CSV in the working directory.")
        logger.info(f"Loading data from {DATA_FILE}")
        _cache["df"] = load_and_clean(DATA_FILE)
    return _cache["df"]


def get_chokepoint_df() -> pd.DataFrame:
    if "chokepoints" not in _cache:
        if not Path(CHOKEPOINT_FILE).exists():
            raise HTTPException(503, f"Chokepoint file '{CHOKEPOINT_FILE}' not found.")
        logger.info(f"Loading chokepoint data from {CHOKEPOINT_FILE}")
        _cache["chokepoints"] = load_and_clean_chokepoints(CHOKEPOINT_FILE)
    return _cache["chokepoints"]


def get_scored_df() -> pd.DataFrame:
    if "scored" not in _cache:
        df = get_df()
        scored = df.sort_values(["portname", "date"]).copy()

        def _congestion_series(s: pd.Series) -> pd.Series:
            rolling_mean = s.rolling(90, min_periods=1).mean()
            rolling_std  = s.rolling(90, min_periods=1).std().replace(0, np.nan)
            z = ((s - rolling_mean) / rolling_std).fillna(0).clip(-3, 3)
            return ((z + 3) / 6 * 100).round(1)

        # transform preserves all columns including the groupby key (portname)
        scored["congestion_score"] = (
            scored.groupby("portname")["portcalls"].transform(_congestion_series)
        )
        scored["traffic_level"] = scored["congestion_score"].apply(
            lambda x: "HIGH" if x >= 67 else ("MEDIUM" if x >= 33 else "LOW")
        )
        _cache["scored"] = scored
    return _cache["scored"]


# ──────────────────────────────────────────────
# Serialisation helper
# ──────────────────────────────────────────────

def _safe_float(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), 4)


def _portcalls_to_congestion(portcalls: float, mean_90: float, std_90: float) -> tuple[float, str]:
    """Convert a portcalls value to congestion score/level using a rolling baseline."""
    if std_90 == 0 or np.isnan(std_90):
        z = 0.0
    else:
        z = float(np.clip((portcalls - mean_90) / std_90, -3.0, 3.0))
    score = round((z + 3.0) / 6.0 * 100.0, 1)
    level = "HIGH" if score >= 67 else ("MEDIUM" if score >= 33 else "LOW")
    return score, level


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-safe list of dicts."""
    records = []
    for row in df.to_dict("records"):
        clean = {}
        for k, v in row.items():
            if v is pd.NaT:
                clean[k] = None
            elif isinstance(v, (pd.Timestamp,)):
                clean[k] = v.isoformat()[:10]
            elif isinstance(v, float) and np.isnan(v):
                clean[k] = None
            elif isinstance(v, (np.integer,)):
                clean[k] = int(v)
            elif isinstance(v, (np.floating,)):
                clean[k] = _safe_float(v)
            else:
                clean[k] = v
        records.append(clean)
    return records


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/api/ports")
def list_ports():
    """List all available port names."""
    df = get_df()
    ports = sorted(df["portname"].unique().tolist())
    return {"ports": ports}


@app.get("/api/overview")
def port_overview(port: str = Query(..., description="Port name")):
    """Return current-state KPIs, 90-day trend, vessel mix, and cargo flow for a port."""
    scored = get_scored_df()
    p = scored[scored["portname"] == port].sort_values("date").copy()
    if p.empty:
        raise HTTPException(404, f"Port '{port}' not found.")

    last = p["date"].max()

    # ── Current state (last available data point) ────────────────────────
    last_row      = p.iloc[-1]
    current_score = round(float(last_row["congestion_score"]), 1)
    current_level = "HIGH" if current_score >= 67 else ("MEDIUM" if current_score >= 33 else "LOW")
    last_portcalls= round(float(last_row["portcalls"]), 1)
    data_lag_days = max(0, (pd.Timestamp.today().normalize() - last).days)

    # ── 90-day window ─────────────────────────────────────────────────────
    p90 = p[p["date"] >= last - pd.Timedelta(days=89)]
    baseline_mean = float(p90["congestion_score"].mean())
    pct_vs_normal = round((current_score - baseline_mean) / baseline_mean * 100, 1) if baseline_mean > 0 else 0.0

    # ── 7-day trend direction (last 7 vs prior 7 days) ───────────────────
    last7  = p[p["date"] >  last - pd.Timedelta(days=7)]["congestion_score"].mean()
    prior7 = p[(p["date"] > last - pd.Timedelta(days=14)) &
               (p["date"] <= last - pd.Timedelta(days=7))]["congestion_score"].mean()
    diff = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
    trend_direction = "rising" if diff > 2 else ("falling" if diff < -2 else "stable")

    kpi = {
        "port":             port,
        "congestion_score": current_score,
        "congestion_level": current_level,
        "last_portcalls":   last_portcalls,
        "data_lag_days":    data_lag_days,
        "pct_vs_normal":    pct_vs_normal,
        "trend_direction":  trend_direction,
        "last_date":        str(last.date()),
        "avg_daily_visits": round(float(p90["portcalls"].mean()), 2),
        "total_incoming":   int(p90["import_total"].sum()) if "import_total" in p90.columns else 0,
        "total_outgoing":   int(p90["export_total"].sum()) if "export_total" in p90.columns else 0,
    }

    # ── Trend: last 90 days with congestion score ─────────────────────────
    trend = p90[["date", "portcalls", "congestion_score"]].copy()
    trend["portcalls_7d"] = trend["portcalls"].rolling(7, min_periods=1).mean().round(2)

    # ── Vessel mix — last 6 months monthly ───────────────────────────────
    mix_cols = [c for c in ["portcalls_container","portcalls_dry_bulk",
                             "portcalls_general_cargo","portcalls_roro","portcalls_tanker"]
                if c in p.columns]
    mix = p[p["date"] >= last - pd.Timedelta(days=180)].copy()
    mix["month"] = mix["date"].dt.to_period("M").dt.to_timestamp()
    mix_monthly = mix.groupby("month")[mix_cols].sum().reset_index()

    # ── Cargo flow monthly ────────────────────────────────────────────────
    flow_cols = [c for c in ["import_total","export_total"] if c in p.columns]
    flow = mix.groupby("month")[flow_cols].sum().reset_index()

    return {
        "kpi":        kpi,
        "trend":      _df_to_records(trend[["date","portcalls","portcalls_7d","congestion_score"]]),
        "vessel_mix": _df_to_records(mix_monthly),
        "cargo_flow": _df_to_records(flow),
    }


@app.get("/api/top-ports")
def top_ports(top_n: int = Query(50)):
    """Return ports sorted by current (last-known) congestion — lowest first."""
    scored = get_scored_df()
    latest = (
        scored.sort_values("date")
        .groupby("portname")
        .last()
        .reset_index()[["portname", "congestion_score", "portcalls"]]
    )
    latest["current_score"] = latest["congestion_score"].round(1)
    latest["last_portcalls"] = latest["portcalls"].round(1)
    latest["status"] = latest["current_score"].apply(
        lambda x: "HIGH" if x >= 67 else ("MEDIUM" if x >= 33 else "LOW")
    )
    latest = latest.sort_values("current_score", ascending=True).head(top_n)
    return {"ports": _df_to_records(latest[["portname","current_score","last_portcalls","status"]])}


@app.get("/api/forecast")
def forecast(
    port:  str = Query(...),
    model: str = Query("Prophet", description="ARIMA | Prophet | XGBoost"),
    horizon: int = Query(7, ge=1, le=30),
):
    """Run the requested model and return a 7-day (or custom horizon) forecast."""
    if model not in ALL_MODELS:
        raise HTTPException(400, f"model must be one of {ALL_MODELS}")

    df    = get_df()
    daily = get_port_daily_series(df, port)
    if daily.empty:
        raise HTTPException(404, f"Port '{port}' not found.")

    # ── Build chokepoint leading-indicator features for XGBoost ──────────
    chokepoint_data = None
    if model == "XGBoost":
        try:
            chk_df = get_chokepoint_df()
            chokepoint_data = {
                name: get_chokepoint_daily_series(chk_df, name)
                for name in LEADING_CHOKEPOINTS
                if name in chk_df["portname"].values
            }
        except Exception:
            chokepoint_data = None  # degrade gracefully if chokepoint data unavailable

    t0 = time.time()
    try:
        m = get_model(model)
        if model == "XGBoost" and chokepoint_data:
            m.fit(daily, chokepoint_data=chokepoint_data)
        else:
            m.fit(daily)
        fcst = m.predict(horizon=horizon)
    except Exception as e:
        raise HTTPException(500, str(e))

    elapsed = time.time() - t0

    # ── Forecasted congestion scores ─────────────────────────────────────
    # Anchor on the 90-day rolling baseline from history
    hist_vals = daily["portcalls"].values.astype(float)
    baseline  = hist_vals[-90:] if len(hist_vals) >= 90 else hist_vals
    mean_90   = float(baseline.mean())
    std_90    = float(baseline.std()) if len(baseline) > 1 else 0.0

    cong_scores, cong_levels = [], []
    for yhat_val in fcst["yhat"].values:
        s, lv = _portcalls_to_congestion(max(float(yhat_val), 0.0), mean_90, std_90)
        cong_scores.append(s)
        cong_levels.append(lv)

    fcst = fcst.copy()
    fcst["congestion_score"] = cong_scores
    fcst["congestion_level"] = cong_levels

    # ── Last 90 days of history for chart context (with congestion) ───────
    scored    = get_scored_df()
    port_hist = scored[scored["portname"] == port].sort_values("date")
    hist = (
        daily.tail(90)[["date","portcalls"]]
        .merge(port_hist[["date","congestion_score"]], on="date", how="left")
        .copy()
    )
    hist["congestion_score"] = hist["congestion_score"].fillna(50.0).round(1)
    hist["portcalls_smooth"] = hist["portcalls"].rolling(3, min_periods=1).mean().round(2)

    # ── Log predictions for ALL 3 models for validation later ────────────
    # Always logs all models regardless of which one the user requested.
    # This gives a complete comparison when actual data arrives.
    try:
        # Always save the requested model first (already fitted above)
        save_forecast(port, model, fcst)

        # Fit and save the other two models in the background
        other_models = [m for m in ALL_MODELS if m != model]
        for other in other_models:
            try:
                om = get_model(other)
                if other == "XGBoost":
                    try:
                        chk_df = get_chokepoint_df()
                        chk_data = {
                            name: get_chokepoint_daily_series(chk_df, name)
                            for name in LEADING_CHOKEPOINTS
                            if name in chk_df["portname"].values
                        }
                        om.fit(daily, chokepoint_data=chk_data)
                    except Exception:
                        om.fit(daily)
                else:
                    om.fit(daily)
                other_fcst = om.predict(horizon=horizon)
                save_forecast(port, other, other_fcst)
                logger.info(f"Forecast tracker: logged {other} predictions for {port}")
            except Exception as e:
                logger.warning(f"Forecast tracker: could not log {other} for {port}: {e}")
    except Exception as e:
        logger.warning(f"Forecast tracker save failed: {e}")

    return {
        "port":        port,
        "model":       model,
        "horizon":     horizon,
        "fit_seconds": round(elapsed, 2),
        "history":     _df_to_records(hist),
        "forecast":    _df_to_records(fcst),
    }


@app.get("/api/model-comparison")
def model_comparison_results():
    """Return saved model comparison results (run model_comparison.py first)."""
    if not Path(COMPARISON_FILE).exists():
        return {
            "available": False,
            "message": f"Run 'python model_comparison.py' to generate {COMPARISON_FILE}",
        }
    with open(COMPARISON_FILE) as f:
        data = json.load(f)
    data["available"] = True
    return data


@app.get("/api/metrics")
def compute_metrics(
    port:  str = Query(...),
    model: str = Query("Prophet"),
    train_days: int = Query(365),
    horizon:    int = Query(7),
):
    """
    Run a single hold-out evaluation for the given port/model combo
    and return metrics (MAE, RMSE, MAPE, SMAPE, coverage).
    """
    if model not in ALL_MODELS:
        raise HTTPException(400, f"model must be one of {ALL_MODELS}")

    df    = get_df()
    daily = get_port_daily_series(df, port)
    if len(daily) < train_days + horizon:
        raise HTTPException(400, "Not enough data for the requested train/horizon split.")

    train = daily.iloc[:train_days]
    test  = daily.iloc[train_days:train_days + horizon]

    t0 = time.time()
    try:
        m = get_model(model)
        m.fit(train)
        fcst = m.predict(horizon=horizon)
    except Exception as e:
        raise HTTPException(500, str(e))
    elapsed = time.time() - t0

    metrics = evaluate_forecast(
        y_true=test["portcalls"].values,
        y_pred=fcst["yhat"].values,
        y_lower=fcst["yhat_lower"].values,
        y_upper=fcst["yhat_upper"].values,
        fit_time_s=elapsed,
    )
    return {"port": port, "model": model, "metrics": {k: _safe_float(v) for k, v in metrics.items()}}


@app.get("/api/port-chokepoints")
def port_chokepoints(port: str = Query(..., description="Port name")):
    """Return the upstream chokepoints relevant to a specific port with their current status."""
    chk_names = _get_port_chokepoints(port)
    df = get_chokepoint_df()

    result = []
    for name in chk_names:
        chk = df[df["portname"] == name].sort_values("date")
        if chk.empty:
            continue
        last_row = chk.iloc[-1]
        last = chk["date"].max()
        last90 = chk[chk["date"] >= last - pd.Timedelta(days=89)]
        last7  = chk[chk["date"] >  last - pd.Timedelta(days=7)]["n_total"].mean()
        prior7 = chk[
            (chk["date"] > last - pd.Timedelta(days=14)) &
            (chk["date"] <= last - pd.Timedelta(days=7))
        ]["n_total"].mean()
        diff  = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
        trend = "rising" if diff > 1 else ("falling" if diff < -1 else "stable")

        result.append({
            "portname":           name,
            "disruption_score":   _safe_float(last_row["disruption_score"]),
            "disruption_level":   last_row["disruption_level"],
            "n_total":            _safe_float(last_row["n_total"]),
            "trend":              trend,
            "last_date":          str(last.date()),
            "avg_daily_transits": _safe_float(last90["n_total"].mean()),
            "pct_vs_normal":      _safe_float(
                round((float(last_row["disruption_score"]) - float(last90["disruption_score"].mean()))
                      / max(float(last90["disruption_score"].mean()), 1) * 100, 1)
            ),
        })

    return {"port": port, "chokepoints": result}


@app.get("/api/chokepoints")
def list_chokepoints():
    """Return all chokepoints with their latest disruption score and 90-day trend."""
    df = get_chokepoint_df()

    latest = (
        df.sort_values("date")
        .groupby("portname")
        .last()
        .reset_index()
    )

    result = []
    for _, row in latest.iterrows():
        chk_hist = df[df["portname"] == row["portname"]].sort_values("date")
        last90 = chk_hist[chk_hist["date"] >= chk_hist["date"].max() - pd.Timedelta(days=89)]
        last7  = chk_hist[chk_hist["date"] >  chk_hist["date"].max() - pd.Timedelta(days=7)]["n_total"].mean()
        prior7 = chk_hist[
            (chk_hist["date"] > chk_hist["date"].max() - pd.Timedelta(days=14)) &
            (chk_hist["date"] <= chk_hist["date"].max() - pd.Timedelta(days=7))
        ]["n_total"].mean()
        diff = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
        trend = "rising" if diff > 1 else ("falling" if diff < -1 else "stable")

        result.append({
            "portname":         row["portname"],
            "disruption_score": _safe_float(row["disruption_score"]),
            "disruption_level": row["disruption_level"],
            "last_date":        str(row["date"].date()),
            "n_total":          _safe_float(row["n_total"]),
            "capacity":         _safe_float(row["capacity"]),
            "trend":            trend,
            "avg_daily_transits": _safe_float(last90["n_total"].mean()),
        })

    result.sort(key=lambda x: x["disruption_score"] or 0)
    return {"chokepoints": result}


@app.get("/api/chokepoints/overview")
def chokepoint_overview(name: str = Query(..., description="Chokepoint name")):
    """Return detailed stats + 90-day history for a single chokepoint."""
    df = get_chokepoint_df()
    chk = df[df["portname"] == name].sort_values("date").copy()
    if chk.empty:
        raise HTTPException(404, f"Chokepoint '{name}' not found.")

    last     = chk["date"].max()
    last_row = chk.iloc[-1]
    lag      = max(0, (pd.Timestamp.today().normalize() - last).days)

    last90 = chk[chk["date"] >= last - pd.Timedelta(days=89)]
    baseline_mean = float(last90["disruption_score"].mean())
    pct_vs_normal = (
        round((float(last_row["disruption_score"]) - baseline_mean) / baseline_mean * 100, 1)
        if baseline_mean > 0 else 0.0
    )

    last7  = chk[chk["date"] >  last - pd.Timedelta(days=7)]["n_total"].mean()
    prior7 = chk[
        (chk["date"] > last - pd.Timedelta(days=14)) &
        (chk["date"] <= last - pd.Timedelta(days=7))
    ]["n_total"].mean()
    diff  = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
    trend = "rising" if diff > 1 else ("falling" if diff < -1 else "stable")

    kpi = {
        "portname":          name,
        "disruption_score":  _safe_float(last_row["disruption_score"]),
        "disruption_level":  last_row["disruption_level"],
        "last_date":         str(last.date()),
        "data_lag_days":     lag,
        "n_total":           _safe_float(last_row["n_total"]),
        "n_container":       _safe_float(last_row["n_container"]),
        "n_tanker":          _safe_float(last_row["n_tanker"]),
        "n_dry_bulk":        _safe_float(last_row["n_dry_bulk"]),
        "capacity":          _safe_float(last_row["capacity"]),
        "pct_vs_normal":     pct_vs_normal,
        "trend":             trend,
        "avg_daily_transits": _safe_float(last90["n_total"].mean()),
    }

    # 90-day history with 7-day smoothing
    hist = last90[["date", "n_total", "disruption_score"]].copy()
    hist["n_total_7d"] = hist["n_total"].rolling(7, min_periods=1).mean().round(2)

    # Vessel type breakdown — last 6 months monthly
    mix_cols = [c for c in ["n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker"] if c in chk.columns]
    mix = chk[chk["date"] >= last - pd.Timedelta(days=180)].copy()
    mix["month"] = mix["date"].dt.to_period("M").dt.to_timestamp()
    mix_monthly = mix.groupby("month")[mix_cols].sum().reset_index()

    return {
        "kpi":       kpi,
        "history":   _df_to_records(hist[["date", "n_total", "n_total_7d", "disruption_score"]]),
        "vessel_mix": _df_to_records(mix_monthly),
    }


@app.get("/api/weather")
def port_weather(port: str = Query(..., description="Port name")):
    """Return current weather conditions and 7-day forecast for a port."""
    current  = fetch_current_weather(port)
    forecast = fetch_weather_forecast(port, days=7)

    if current is None and not forecast:
        raise HTTPException(503, f"Weather data unavailable for '{port}'. Check API key or port coordinates.")

    return {
        "port":     port,
        "current":  current,
        "forecast": forecast,
    }


class ChatRequest(BaseModel):
    question: str
    port: str | None = None
    reset_memory: bool = False


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    """
    Send a question to the DockWise AI advisor.
    Automatically fetches live data for the selected port to enrich the context.
    """
    if not req.question.strip():
        raise HTTPException(400, "question must not be empty.")

    # Gather live context for the selected port
    overview_data       = None
    forecast_data       = None
    weather_data        = None
    port_chk_data       = None
    all_chokepoints     = None

    if req.port:
        try:
            # Port overview
            scored = get_scored_df()
            p = scored[scored["portname"] == req.port].sort_values("date").copy()
            if not p.empty:
                last = p["date"].max()
                last_row = p.iloc[-1]
                p90 = p[p["date"] >= last - pd.Timedelta(days=89)]
                baseline_mean = float(p90["congestion_score"].mean())
                current_score = round(float(last_row["congestion_score"]), 1)
                pct_vs_normal = round((current_score - baseline_mean) / baseline_mean * 100, 1) if baseline_mean > 0 else 0.0
                last7  = p[p["date"] >  last - pd.Timedelta(days=7)]["congestion_score"].mean()
                prior7 = p[(p["date"] > last - pd.Timedelta(days=14)) & (p["date"] <= last - pd.Timedelta(days=7))]["congestion_score"].mean()
                diff = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
                overview_data = {"kpi": {
                    "port": req.port,
                    "congestion_score": current_score,
                    "congestion_level": "HIGH" if current_score >= 67 else ("MEDIUM" if current_score >= 33 else "LOW"),
                    "last_portcalls": round(float(last_row["portcalls"]), 1),
                    "trend_direction": "rising" if diff > 2 else ("falling" if diff < -2 else "stable"),
                    "pct_vs_normal": pct_vs_normal,
                    "last_date": str(last.date()),
                }}
        except Exception:
            pass

        try:
            # 7-day forecast (Prophet — fastest)
            df = get_df()
            daily = get_port_daily_series(df, req.port)
            if not daily.empty:
                m = get_model("Prophet")
                m.fit(daily)
                fcst = m.predict(horizon=7)
                hist_vals = daily["portcalls"].values.astype(float)
                baseline  = hist_vals[-90:] if len(hist_vals) >= 90 else hist_vals
                mean_90   = float(baseline.mean())
                std_90    = float(baseline.std()) if len(baseline) > 1 else 0.0
                rows = []
                for _, row in fcst.iterrows():
                    s, lv = _portcalls_to_congestion(max(float(row["yhat"]), 0.0), mean_90, std_90)
                    rows.append({"date": str(row["date"])[:10], "congestion_score": s, "congestion_level": lv})
                forecast_data = rows
        except Exception:
            pass

        try:
            weather_data = {"current": fetch_current_weather(req.port), "forecast": fetch_weather_forecast(req.port)}
        except Exception:
            pass

        try:
            chk_names = _get_port_chokepoints(req.port)
            df_chk = get_chokepoint_df()
            port_chk_data = []
            for name in chk_names:
                chk = df_chk[df_chk["portname"] == name].sort_values("date")
                if chk.empty:
                    continue
                last_row = chk.iloc[-1]
                port_chk_data.append({
                    "portname":         name,
                    "disruption_score": _safe_float(last_row["disruption_score"]),
                    "disruption_level": last_row["disruption_level"],
                    "n_total":          _safe_float(last_row["n_total"]),
                    "trend":            "stable",
                })
        except Exception:
            pass

    try:
        df_chk = get_chokepoint_df()
        latest = df_chk.sort_values("date").groupby("portname").last().reset_index()
        all_chokepoints = [
            {
                "portname":         row["portname"],
                "disruption_score": _safe_float(row["disruption_score"]),
                "disruption_level": row["disruption_level"],
            }
            for _, row in latest.iterrows()
        ]
    except Exception:
        pass

    try:
        answer = llm_chat(
            question=req.question,
            port=req.port,
            overview=overview_data,
            forecast=forecast_data,
            chokepoints=all_chokepoints,
            port_chokepoints=port_chk_data,
            weather=weather_data,
            reset_memory=req.reset_memory,
        )
        return {"answer": answer, "port": req.port}
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.error(f"/api/chat error: {e}")
        raise HTTPException(500, f"LLM error: {e}")


@app.get("/api/forecast-validation")
def forecast_validation():
    """
    Validate saved forecasts against actual data.
    Returns accuracy metrics (MAE, RMSE, MAPE, coverage) per model
    for all predictions where actual data is now available.
    """
    return validate(DATA_FILE)


@app.get("/api/forecast-log")
def forecast_log(
    port:  str = Query(None, description="Filter by port name"),
    model: str = Query(None, description="Filter by model name"),
):
    """Return the raw forecast log, optionally filtered by port or model."""
    return get_log(port=port, model=model)


@app.get("/api/risk-assessment")
def risk_assessment(port: str = Query(..., description="Port name")):
    """
    Run the multi-agent risk assessment pipeline for a port.

    Agents:
      1. WeatherDisruptionAgent  — scores operational weather risk
      2. PortCongestionAgent     — scores current congestion signals
      3. RiskOrchestrator        — combines signals → risk_score + explanation

    Returns combined risk score (0–1), tier (LOW/MEDIUM/HIGH),
    LLM explanation, and raw agent signals.
    """
    from agents import run_risk_assessment

    df = get_df()
    if port not in df["portname"].values:
        raise HTTPException(404, f"Port '{port}' not found.")

    try:
        result = run_risk_assessment(port)
    except Exception as e:
        logger.error(f"/api/risk-assessment error: {e}")
        raise HTTPException(500, str(e))

    return {
        "port":        result["port"],
        "risk_score":  result["risk_score"],
        "risk_tier":   result["risk_tier"],
        "explanation": result["explanation"],
        "signals": {
            "weather": {
                "disruption_score": result["weather_disruption_score"],
                "risk_level":       result["weather_risk_level"],
                "active_warnings":  result["active_warnings"],
                "summary":          result["weather_summary"],
            },
            "congestion": {
                "score":             result["congestion_score"],
                "ratio":             result["congestion_ratio"],
                "trend":             result["trend_direction"],
                "seasonal_context":  result["seasonal_context"],
                "prophet_expected":  result["prophet_expected"],
            },
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}
