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
import requests as _requests
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
from llm import (chat as llm_chat, generate_followups as llm_followups,
                 generate_briefing as llm_briefing, generate_scenario as llm_scenario,
                 generate_comparison as llm_comparison)
import data_pull
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

COMPARISON_FILE = "model_comparison_results.json"
CRON_SECRET     = os.environ.get("CRON_SECRET", "")

# AIS microservice base URL (Phase 6A — staleness reconciliation)
AIS_BASE_URL = os.environ.get("AIS_BASE_URL", "http://localhost:8001")
_AIS_TIMEOUT_SEC = 2.0
_STALENESS_DAYS_THRESHOLD = 7  # PortWatch lag above this triggers AIS reconciliation


def _fetch_ais_anchor_stats(lat: float, lon: float, port_name: str,
                             radius_nm: float = 15.0) -> dict | None:
    """Fetch live anchor counts near a port from the AIS microservice.

    Returns the parsed JSON dict on success, None on any failure
    (timeout, connection refused, non-200, JSON error). Fail-soft by design —
    callers must handle None as "live data unavailable".
    """
    try:
        res = _requests.get(
            f"{AIS_BASE_URL}/api/vessels/anchor-stats",
            params={"lat": lat, "lon": lon, "radius_nm": radius_nm},
            timeout=_AIS_TIMEOUT_SEC,
        )
        if res.status_code != 200:
            logger.warning(
                f"[Reconcile] AIS anchor-stats returned {res.status_code} for '{port_name}'"
            )
            return None
        return res.json()
    except Exception as e:
        logger.warning(f"[Reconcile] AIS anchor-stats failed for '{port_name}': {e}")
        return None

# ──────────────────────────────────────────────
# In-memory cache for the loaded dataset
# ──────────────────────────────────────────────

_cache: dict = {}


@app.on_event("startup")
async def ensure_data():
    """Init DB tables and auto-pull data if the DB is empty."""
    try:
        from db import init_tables, get_engine
        init_tables()
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM port_data")).scalar()
        if count == 0:
            logger.info("DB empty — pulling port data from PortWatch API...")
            data_pull.run_ports()
            data_pull.run_chokepoints()
            logger.info("Initial data pull complete.")
    except Exception as e:
        logger.error(f"Startup data check failed: {e}")


def get_df() -> pd.DataFrame:
    if "df" not in _cache:
        try:
            _cache["df"] = load_and_clean()
        except Exception as e:
            raise HTTPException(503, f"Could not load port data: {e}")
    return _cache["df"]


def get_chokepoint_df() -> pd.DataFrame:
    if "chokepoints" not in _cache:
        try:
            _cache["chokepoints"] = load_and_clean_chokepoints()
        except Exception as e:
            raise HTTPException(503, f"Could not load chokepoint data: {e}")
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

    # ── Live-data reconciliation (Phase 6A) ─────────────────────────────────
    # When PortWatch is stale, ask the AIS microservice for live anchor counts
    # near this port. If they exceed the per-port p75 threshold, bump the
    # displayed congestion_level by one tier. The numeric congestion_score is
    # NEVER modified — only the displayed tier label.
    portwatch_tier         = current_level
    tier_adjusted          = False
    tier_adjustment_reason = None
    live_data_available    = None        # None = not checked (lag <= threshold)
    live_anchor_count      = None
    live_anchor_threshold  = None
    # Phase 6A.1 — spatial coverage classification
    # "covered"     = AIS sees >= 3 vessels near this port (live signal trustworthy)
    # "sparse"      = AIS sees 1-2 vessels (live signal weak; absence of anchors not informative)
    # "dark"        = AIS sees 0 vessels (typical for inland Great Lakes ports outside AIS reception)
    # "unavailable" = AIS service did not respond at all
    # None          = coverage not checked (lag <= threshold; no AIS call made)
    live_coverage          = None

    if data_lag_days > _STALENESS_DAYS_THRESHOLD:
        from weather import PORT_COORDS
        from port_anchor_thresholds import get_anchor_threshold

        if port in PORT_COORDS:
            p_lat, p_lon = PORT_COORDS[port]
            ais_stats = _fetch_ais_anchor_stats(p_lat, p_lon, port)
            if ais_stats is None:
                live_data_available    = False
                live_coverage          = "unavailable"
                tier_adjustment_reason = "Live AIS data unavailable; tier reflects PortWatch only."
            else:
                live_data_available   = True
                live_anchor_count     = int(ais_stats.get("anchor_count", 0))
                threshold             = max(get_anchor_threshold(port), 5)
                live_anchor_threshold = threshold
                total_nearby          = int(ais_stats.get("total_nearby", 0))
                if total_nearby >= 3:
                    live_coverage = "covered"
                elif total_nearby > 0:
                    live_coverage = "sparse"
                else:
                    live_coverage = "dark"

                # Phase 6A.1 safety guard: only allow tier-bump when live coverage is
                # trustworthy. If we can't see the port (sparse/dark), the absence of
                # anchors is not evidence of "no congestion" — it's evidence of
                # "we can't see the port." Don't pretend silence is signal.
                if live_anchor_count >= threshold and live_coverage == "covered":
                    bumped = {"LOW": "MEDIUM", "MEDIUM": "HIGH", "HIGH": "HIGH"}.get(
                        current_level, current_level
                    )
                    if bumped != current_level:
                        current_level          = bumped
                        tier_adjusted          = True
                        tier_adjustment_reason = (
                            f"PortWatch data is {data_lag_days} days stale; "
                            f"live AIS shows {live_anchor_count} vessels at anchor "
                            f"near this port (threshold: {threshold}). "
                            f"Tier adjusted upward."
                        )
                    else:
                        # Already at HIGH — flag confirmation but no bump
                        tier_adjustment_reason = (
                            f"PortWatch data is {data_lag_days} days stale; "
                            f"live AIS confirms {live_anchor_count} vessels at anchor — "
                            f"already at HIGH."
                        )

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
        # Phase 6A — staleness reconciliation (additive, backward-compatible)
        "portwatch_tier":         portwatch_tier,
        "tier_adjusted":          tier_adjusted,
        "tier_adjustment_reason": tier_adjustment_reason,
        "live_data_available":    live_data_available,
        "live_anchor_count":      live_anchor_count,
        "live_anchor_threshold":  live_anchor_threshold,
        # Phase 6A.1 — spatial coverage classification (additive)
        "live_coverage":          live_coverage,
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


_TOP_PORTS_DESCRIPTION = (
    "Ports ranked by per-port z-score deviation from their own historical "
    "baseline. Highlights ports having unusual days, NOT necessarily the "
    "most loaded ports."
)


@app.get("/api/top-ports")
def top_ports(
    top_n: int = Query(50),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
):
    """Return ports sorted by current (last-known) congestion. Default asc = least anomalous first."""
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
    latest["ranking_type"] = "anomaly"
    ascending = sort_order == "asc"
    latest = latest.sort_values("current_score", ascending=ascending).head(top_n)
    return {
        "description": _TOP_PORTS_DESCRIPTION,
        "sort_order": sort_order,
        "ports": _df_to_records(
            latest[["portname", "current_score", "last_portcalls", "status", "ranking_type"]]
        ),
    }


# ── Phase 6B-revised, Part 2 — absolute-load ranking ────────────
_TOP_LOADED_DESCRIPTION = (
    "Ports ranked by absolute current vessel call volume. Highlights the "
    "busiest ports right now."
)


@app.get("/api/top-loaded-ports")
def top_loaded_ports(n: int = Query(10, ge=1, le=100)):
    """Return ports sorted by current portcalls desc; ties broken by 7-day mean."""
    scored = get_scored_df().sort_values(["portname", "date"]).copy()
    scored["portcalls_7d"] = (
        scored.groupby("portname")["portcalls"]
        .transform(lambda s: s.rolling(7, min_periods=1).mean())
    )
    latest = (
        scored.groupby("portname")
        .last()
        .reset_index()[["portname", "portcalls", "portcalls_7d", "congestion_score"]]
    )
    latest["current_portcalls"] = latest["portcalls"].round(1)
    latest["trailing_7d_mean"] = latest["portcalls_7d"].round(2)
    latest["congestion_level"] = latest["congestion_score"].apply(
        lambda x: "HIGH" if x >= 67 else ("MEDIUM" if x >= 33 else "LOW")
    )
    latest["ranking_type"] = "absolute_load"
    latest = latest.sort_values(
        ["current_portcalls", "trailing_7d_mean"], ascending=[False, False]
    ).head(n)
    return {
        "description": _TOP_LOADED_DESCRIPTION,
        "ports": _df_to_records(
            latest[[
                "portname",
                "current_portcalls",
                "trailing_7d_mean",
                "congestion_level",
                "ranking_type",
            ]]
        ),
    }


# ── Phase 6B-revised, Part 3 — nearby-port advisor ──────────────
def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_NM = 3440.065
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return float(2 * R_NM * np.arcsin(np.sqrt(a)))


def _classify_recommendation(level: str, trend: str) -> str:
    if level == "HIGH":
        return "avoid"
    if level == "MEDIUM" and trend == "rising":
        return "avoid"
    if level == "LOW" and trend in ("stable", "falling"):
        return "good_alternative"
    return "watch"


@app.get("/api/advisor/nearby-ports")
def nearby_ports(
    port: str = Query(...),
    radius_nm: float = Query(300.0, gt=0),
    max_results: int = Query(6, ge=1, le=20),
):
    """Ports within radius_nm of the selected port, ranked by alternative-route suitability."""
    from weather import PORT_COORDS

    radius_nm = min(float(radius_nm), 1000.0)
    if port not in PORT_COORDS:
        raise HTTPException(404, f"Port '{port}' has no known coordinates")
    p_lat, p_lon = PORT_COORDS[port]

    scored = get_scored_df().sort_values(["portname", "date"]).copy()
    candidates = []
    for other, (lat, lon) in PORT_COORDS.items():
        if other == port:
            continue
        d_nm = _haversine_nm(p_lat, p_lon, lat, lon)
        if d_nm > radius_nm:
            continue
        sub = scored[scored["portname"] == other]
        if sub.empty:
            continue
        sub_tail = sub.tail(14)
        if len(sub_tail) < 2:
            continue
        last7 = sub_tail.tail(7)["portcalls"].mean()
        prior7 = sub_tail.head(len(sub_tail) - 7)["portcalls"].mean() if len(sub_tail) > 7 else last7
        if prior7 and prior7 > 0:
            delta_pct = (last7 - prior7) / prior7 * 100.0
        else:
            delta_pct = 0.0
        if delta_pct > 5:
            trend = "rising"
        elif delta_pct < -5:
            trend = "falling"
        else:
            trend = "stable"
        latest_row = sub.iloc[-1]
        score = float(latest_row["congestion_score"])
        level = "HIGH" if score >= 67 else ("MEDIUM" if score >= 33 else "LOW")
        recommendation = _classify_recommendation(level, trend)
        candidates.append({
            "portname": other,
            "distance_nm": round(d_nm, 1),
            "current_score": round(score, 1),
            "congestion_level": level,
            "trend": trend,
            "trend_delta_pct": round(delta_pct, 1),
            "recommendation": recommendation,
        })

    rec_order = {"good_alternative": 0, "watch": 1, "avoid": 2}
    candidates.sort(key=lambda c: (rec_order[c["recommendation"]], c["distance_nm"]))
    candidates = candidates[:max_results]

    return {
        "port": port,
        "radius_nm": radius_nm,
        "description": (
            f"Ports within {radius_nm:.0f} nm of {port}, ranked by "
            "alternative-route suitability (good alternatives first, nearest first)."
        ),
        "ports": candidates,
    }


# ── Phase 6A.2 — live AIS coverage snapshot for map ring ───────
_coverage_cache: dict = {}  # {"data": dict, "ts": float}
_COVERAGE_TTL = 30          # seconds


@app.get("/api/coverage-snapshot")
def coverage_snapshot():
    """Return per-port live-AIS coverage classification used by the map ring.

    Response shape: {"coverage": {"<port>": "covered"|"sparse"|"dark"|"unavailable"}, "cached": bool}

    Fails open by design: if anything goes wrong (AIS service down, timeout,
    unexpected exception), this returns {"coverage": {}}. The frontend then
    treats every port as "covered" — i.e. the visual coverage signal fails
    OPEN, not closed. Honest data is preferred over pessimistic data when
    our own pipeline is the failure mode.
    """
    now = time.time()
    if _coverage_cache.get("data") is not None and (now - _coverage_cache.get("ts", 0)) < _COVERAGE_TTL:
        return {"coverage": _coverage_cache["data"], "cached": True}

    try:
        from weather import PORT_COORDS
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _classify(item):
            name, (lat, lon) = item
            stats = _fetch_ais_anchor_stats(lat, lon, name)
            if stats is None:
                return name, "unavailable"
            total_nearby = int(stats.get("total_nearby", 0))
            if total_nearby >= 3:
                return name, "covered"
            if total_nearby > 0:
                return name, "sparse"
            return name, "dark"

        items = list(PORT_COORDS.items())
        result: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_classify, it) for it in items]
            for fut in as_completed(futures, timeout=8.0):
                try:
                    name, cov = fut.result()
                    result[name] = cov
                except Exception:
                    pass

        # Fails-open guard: if every port came back "unavailable", the AIS
        # service itself is almost certainly down. Returning a full dict of
        # "unavailable" would dash the entire map, falsely implying all live
        # data is bad. Honest behaviour when our own pipeline is the failure
        # mode: return {} so the frontend renders every port as covered.
        if result and all(v == "unavailable" for v in result.values()):
            logger.warning(
                f"/api/coverage-snapshot: all {len(result)} ports unavailable — "
                f"AIS service likely down. Returning {{}} (fails-open)."
            )
            result = {}

        _coverage_cache["data"] = result
        _coverage_cache["ts"] = now
        return {"coverage": result, "cached": False}
    except Exception as e:
        logger.warning(f"/api/coverage-snapshot failed: {e}")
        return {"coverage": {}, "cached": False}


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
        result = llm_chat(
            question=req.question,
            port=req.port,
            overview=overview_data,
            forecast=forecast_data,
            chokepoints=all_chokepoints,
            port_chokepoints=port_chk_data,
            weather=weather_data,
            reset_memory=req.reset_memory,
        )
        # result is now {"answer": str, "sources": list}
        if isinstance(result, dict):
            return {"answer": result["answer"], "sources": result.get("sources", []), "port": req.port}
        # Fallback for plain string (shouldn't happen but be safe)
        return {"answer": result, "sources": [], "port": req.port}
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.error(f"/api/chat error: {e}")
        raise HTTPException(500, f"LLM error: {e}")


class FollowupRequest(BaseModel):
    answer: str
    port: str | None = None


@app.post("/api/chat/followups")
def followup_endpoint(req: FollowupRequest):
    """Generate 3 follow-up question chips based on an AI answer."""
    try:
        followups = llm_followups(req.answer, req.port)
        return {"followups": followups}
    except Exception as e:
        logger.error(f"/api/chat/followups error: {e}")
        return {"followups": []}


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
      3. VesselArrivalAgent      — live AIS-based 72h arrival pressure
      4. RiskOrchestrator        — combines signals → risk_score + explanation

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
            "vessel": {
                "vessel_count":       result.get("vessel_count", 0),
                "vessel_delay_score": result.get("vessel_delay_score", 0.0),
                "mega_vessel_flag":   result.get("mega_vessel_flag", False),
                "anchor_count":       result.get("anchor_count", 0),
                "moored_count":       result.get("moored_count", 0),
                "incoming_72h":       result.get("incoming_72h", 0),
                "queue_pressure":     result.get("queue_pressure", 0.0),
                "mega_vessel_count":  result.get("mega_vessel_count", 0),
                "analyst_note":       result.get("vessel_analyst_note", ""),
                "anomalies":          result.get("vessel_anomalies", []),
                "mix_summary":        result.get("vessel_mix_summary", ""),
                "confidence":         result.get("vessel_confidence", "LOW"),
            },
        },
    }


# ── Advisor: Briefing (3A) ───────────────────────────────────
_briefing_cache: dict = {}  # {"cards": [...], "ts": float}
_BRIEFING_TTL = 600  # 10 minutes

@app.post("/api/advisor/briefing")
def advisor_briefing():
    """Generate 3 insight cards from current port data. Cached for 10 minutes."""
    now = time.time()
    if _briefing_cache.get("cards") and (now - _briefing_cache.get("ts", 0)) < _BRIEFING_TTL:
        return {"cards": _briefing_cache["cards"], "cached": True}

    scored = get_scored_df()
    latest = (
        scored.sort_values("date")
        .groupby("portname")
        .last()
        .reset_index()
    )

    # Build port summaries with trend info
    summaries = []
    for _, row in latest.iterrows():
        port_hist = scored[scored["portname"] == row["portname"]].sort_values("date")
        last = port_hist["date"].max()
        last7 = port_hist[port_hist["date"] > last - pd.Timedelta(days=7)]["congestion_score"].mean()
        prior7 = port_hist[
            (port_hist["date"] > last - pd.Timedelta(days=14)) &
            (port_hist["date"] <= last - pd.Timedelta(days=7))
        ]["congestion_score"].mean()
        diff = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
        trend = "rising" if diff > 2 else ("falling" if diff < -2 else "stable")

        p90 = port_hist[port_hist["date"] >= last - pd.Timedelta(days=89)]
        baseline_mean = float(p90["congestion_score"].mean()) if not p90.empty else 50.0
        current_score = round(float(row["congestion_score"]), 1)
        pct_vs = round((current_score - baseline_mean) / max(baseline_mean, 1) * 100, 1)

        summaries.append({
            "portname": row["portname"],
            "score": current_score,
            "status": "HIGH" if current_score >= 67 else ("MEDIUM" if current_score >= 33 else "LOW"),
            "last_portcalls": round(float(row["portcalls"]), 1),
            "trend_direction": trend,
            "pct_vs_normal": pct_vs,
        })

    # Sort by most interesting signals: biggest abs deviation from normal first
    summaries.sort(key=lambda x: abs(x.get("pct_vs_normal", 0)), reverse=True)

    try:
        cards = llm_briefing(summaries)
        if cards:
            _briefing_cache["cards"] = cards
            _briefing_cache["ts"] = now
            return {"cards": cards, "cached": False}
    except Exception as e:
        logger.error(f"/api/advisor/briefing error: {e}")

    raise HTTPException(503, "Could not generate briefing. LLM may be unavailable.")


# ── Advisor: Scenario Simulator (3B) ────────────────────────
class ScenarioRequest(BaseModel):
    scenario: str

@app.post("/api/advisor/scenario")
def advisor_scenario(req: ScenarioRequest):
    """Run a what-if scenario analysis using current port + chokepoint data."""
    if not req.scenario.strip():
        raise HTTPException(400, "scenario must not be empty.")

    scored = get_scored_df()
    latest = (
        scored.sort_values("date")
        .groupby("portname")
        .last()
        .reset_index()
    )
    summaries = [
        {
            "portname": row["portname"],
            "score": round(float(row["congestion_score"]), 1),
            "status": "HIGH" if row["congestion_score"] >= 67 else ("MEDIUM" if row["congestion_score"] >= 33 else "LOW"),
        }
        for _, row in latest.iterrows()
    ]

    chokepoints_data = None
    try:
        df_chk = get_chokepoint_df()
        chk_latest = df_chk.sort_values("date").groupby("portname").last().reset_index()
        chokepoints_data = [
            {
                "portname": row["portname"],
                "disruption_score": _safe_float(row["disruption_score"]),
                "disruption_level": row["disruption_level"],
            }
            for _, row in chk_latest.iterrows()
        ]
    except Exception:
        pass

    try:
        result = llm_scenario(req.scenario, summaries, chokepoints_data)
        return result
    except Exception as e:
        logger.error(f"/api/advisor/scenario error: {e}")
        raise HTTPException(503, f"Scenario analysis failed: {e}")


# ── Advisor: Port Comparison (3C) ───────────────────────────
class CompareRequest(BaseModel):
    ports: list[str]

@app.post("/api/advisor/compare")
def advisor_compare(req: CompareRequest):
    """Compare 2-3 ports on 6 axes with LLM commentary."""
    if len(req.ports) < 2 or len(req.ports) > 3:
        raise HTTPException(400, "Provide 2 or 3 ports to compare.")

    scored = get_scored_df()
    result_ports = []

    for port_name in req.ports:
        p = scored[scored["portname"] == port_name].sort_values("date")
        if p.empty:
            raise HTTPException(404, f"Port '{port_name}' not found.")

        last = p["date"].max()
        last_row = p.iloc[-1]
        current_score = round(float(last_row["congestion_score"]), 1)

        # Volatility: CV of last 90 days congestion score
        p90 = p[p["date"] >= last - pd.Timedelta(days=89)]
        mean_90 = float(p90["congestion_score"].mean()) if not p90.empty else 50.0
        std_90 = float(p90["congestion_score"].std()) if not p90.empty else 0.0
        volatility = round(min((std_90 / max(mean_90, 1)) * 100, 100), 1)

        # 7-day trend momentum: difference last7 vs prior7, scaled to 0-100
        last7 = p[p["date"] > last - pd.Timedelta(days=7)]["congestion_score"].mean()
        prior7 = p[
            (p["date"] > last - pd.Timedelta(days=14)) &
            (p["date"] <= last - pd.Timedelta(days=7))
        ]["congestion_score"].mean()
        diff = float(last7 - prior7) if (last7 == last7 and prior7 == prior7) else 0.0
        # Map diff (-20..+20) to 0-100 scale (50 = stable)
        trend_score = round(min(max((diff + 20) / 40 * 100, 0), 100), 1)

        # Weather risk: try to fetch, default to 0
        weather_risk = 0
        try:
            current_weather = fetch_current_weather(port_name)
            if current_weather and current_weather.get("risk"):
                risk_level = current_weather["risk"].get("level", "LOW")
                weather_risk = 80 if risk_level == "HIGH" else (50 if risk_level == "MEDIUM" else 10)
        except Exception:
            pass

        # Upstream chokepoint risk: average disruption of relevant chokepoints
        chokepoint_risk = 50  # default
        try:
            chk_names = _get_port_chokepoints(port_name)
            df_chk = get_chokepoint_df()
            chk_scores = []
            for cn in chk_names:
                chk = df_chk[df_chk["portname"] == cn].sort_values("date")
                if not chk.empty:
                    chk_scores.append(float(chk.iloc[-1]["disruption_score"]))
            if chk_scores:
                chokepoint_risk = round(sum(chk_scores) / len(chk_scores), 1)
        except Exception:
            pass

        # Inbound vessel count: not available from port data, use portcalls as proxy
        inbound = round(float(last_row["portcalls"]), 1)
        # Normalize to 0-100 based on typical range (0-50 portcalls/day → 0-100)
        inbound_norm = round(min(inbound / 50 * 100, 100), 1)

        result_ports.append({
            "portname": port_name,
            "congestion_score": current_score,
            "volatility": volatility,
            "trend": trend_score,
            "weather_risk": weather_risk,
            "chokepoint_risk": chokepoint_risk,
            "inbound_vessels": inbound_norm,
        })

    # LLM commentary
    commentary = ""
    try:
        commentary = llm_comparison(result_ports)
    except Exception as e:
        logger.warning(f"Comparison commentary failed: {e}")
        commentary = "Commentary unavailable."

    return {"ports": result_ports, "commentary": commentary}


# ── Port profiles (static JSON) ──────────────────────────────
_port_profiles: dict | None = None

def _load_port_profiles() -> dict:
    global _port_profiles
    if _port_profiles is None:
        profiles_path = Path(__file__).parent / "port_profiles.json"
        if profiles_path.exists():
            with open(profiles_path) as f:
                _port_profiles = json.load(f)
        else:
            _port_profiles = {}
    return _port_profiles


@app.get("/api/port-profile/{name}")
def port_profile(name: str):
    """Return the static profile for a port, or 404 if not available."""
    profiles = _load_port_profiles()
    if name not in profiles:
        raise HTTPException(404, f"Profile not available for '{name}'.")
    return profiles[name]


@app.get("/health")
def health():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# Admin / cron endpoints — secured with CRON_SECRET header
# ──────────────────────────────────────────────

from fastapi import Header

def _check_cron_secret(x_cron_secret: str = Header(default="")):
    if CRON_SECRET and x_cron_secret != CRON_SECRET:
        raise HTTPException(401, "Unauthorized")


@app.post("/admin/run-data-pull")
def cron_data_pull(x_cron_secret: str = Header(default="")):
    """Cron: pull latest port + chokepoint data and refresh in-memory cache."""
    _check_cron_secret(x_cron_secret)
    try:
        data_pull.run_ports()
        data_pull.run_chokepoints()
        _cache.clear()   # force reload on next request
        return {"status": "ok", "message": "Data pull complete, cache cleared"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/admin/validate-forecasts")
def cron_validate(x_cron_secret: str = Header(default="")):
    """Cron: validate saved forecast predictions against new actuals."""
    _check_cron_secret(x_cron_secret)
    try:
        result = validate()
        return {"status": "ok", "summary": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/model-comparison/run")
def run_model_comparison(x_cron_secret: str = Header(default="")):
    """Cron (weekly): run walk-forward cross-validation for all models and save results."""
    _check_cron_secret(x_cron_secret)
    try:
        from model_comparison import run_comparison
        # filepath arg is ignored by load_and_clean() which reads from DB
        results = run_comparison("portwatch_us_data.csv", top_n=5)
        with open(COMPARISON_FILE, "w") as f:
            json.dump(results, f, indent=2)
        _cache.pop("comparison", None)
        port_count = len(results.get("results", {}).get("ports", results.get("ports", [])))
        return {"status": "ok", "ports_evaluated": port_count}
    except Exception as e:
        logger.error(f"/api/model-comparison/run error: {e}")
        raise HTTPException(500, str(e))
