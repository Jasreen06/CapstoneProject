"""
vessel_agent.py
===============
Vessel Arrival Risk Agent for DockWise AI.

A multi-phase analytical agent that combines **live AIS vessel data** with
**historical PortWatch baselines** to assess near-term vessel arrival pressure.

Architecture — four phases:

    Phase 1 — DATA EXTRACTION
        a) Fetch live AIS vessel positions from the AIS microservice.
        b) Load historical PortWatch time series; validate freshness and depth.

    Phase 2 — MULTI-SIGNAL ANALYSIS
        a) Live vessel classification: anchor / moored / incoming-72h.
        b) Vessel mix decomposition (5 types) with z-score anomaly detection.
        c) Day-of-week-aware 72-hour arrival projection (historical fallback).
        d) 4-component delay risk scoring:
             35% queue pressure (live AIS)
           + 25% historical traffic pressure
           + 25% volatility (CV)
           + 15% trend momentum
        e) Anomaly detection: surge, collapse, weekend, acceleration, queue-building.

    Phase 3 — LLM REFLECTION
        Groq-powered analyst briefing with chain-of-thought reasoning.
        Receives both live AIS signals and historical analytics for rich context.
        Falls back to rule-based note if LLM is unavailable.

    Phase 4 — CONFIDENCE VALIDATION
        Scores overall confidence (HIGH/MEDIUM/LOW) based on data freshness,
        history depth, AIS availability, and signal agreement.

Data sources
------------
- LIVE:   GET http://localhost:8001/api/vessels  (AIS microservice)
- HIST:   portwatch_us_data.csv                  (PortWatch baseline)
- COORDS: weather.PORT_COORDS                    (port lat/lon lookup)

Outputs written to RiskState (union of AIS + analytical fields):
    vessel_count          — 72h arrival pressure: anchor + incoming_72h (live)
                            or day-of-week projection (historical fallback)
    vessel_delay_score    — 0–1 composite delay risk
    mega_vessel_flag      — True if mega-vessels detected or port in known list
    anchor_count          — vessels at anchor waiting for berth (live AIS)
    moored_count          — vessels moored at berth (live AIS)
    incoming_72h          — vessels underway with ETA <= 72h (live AIS)
    queue_pressure        — anchor_count / (moored_count + 1)
    mega_vessel_count     — count of mega-vessels in the 72h window
    vessel_analyst_note   — LLM-generated analyst briefing
    vessel_anomalies      — detected anomalies (list of strings)
    vessel_mix_summary    — vessel type composition analysis
    vessel_confidence     — HIGH / MEDIUM / LOW
"""

from __future__ import annotations
import os
import math
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import requests

if TYPE_CHECKING:
    from agents import RiskState

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# ── AIS Configuration ────────────────────────────────────────────────────────
AIS_API_URL = os.environ.get("AIS_API_URL", "http://localhost:8001/api/vessels")
AIS_TIMEOUT = 3.0  # seconds

# Default spatial thresholds (nautical miles)
ANCHOR_RADIUS_NM = 15.0   # vessels at anchor within this radius = "waiting"
MOORED_RADIUS_NM = 5.0    # vessels moored within this radius = "at berth"

# Per-port anchorage overrides for elongated river/channel ports
PORT_ANCHORAGE_OVERRIDES: dict[str, tuple[float, float, float, float]] = {
    "South Louisiana": (30.00, -90.55, 60.0, 15.0),
    "Houston":         (29.75, -95.08, 15.0, 8.0),
}

# Forecast horizon
ETA_HORIZON_HOURS = 72.0
MIN_SOG_KNOTS     = 0.5   # below this, vessel is effectively stationary

# Mega-vessel detection
MEGA_DRAUGHT_M = 12.0     # draught threshold for ultra-large container/tankers

# ── Port & Vessel Domain Constants ───────────────────────────────────────────

# US ports known to regularly handle mega-vessels (10,000+ TEU)
MEGA_VESSEL_PORTS = {
    "Los Angeles-Long Beach", "New York-New Jersey", "Savannah", "Houston",
    "Norfolk", "Charleston", "Oakland", "Seattle", "Tacoma", "Port of Virginia",
}

# Vessel types in PortWatch data
VESSEL_TYPES = ["container", "dry_bulk", "general_cargo", "roro", "tanker"]

# ── Anomaly Detection ────────────────────────────────────────────────────────
ANOMALY_Z_THRESHOLD = 2.0

# ── Delay Score Thresholds ───────────────────────────────────────────────────
DELAY_FLOOR_RATIO = 0.85
DELAY_CEIL_RATIO  = 1.35

# ── Confidence Thresholds ────────────────────────────────────────────────────
MIN_DAYS_HIGH_CONFIDENCE   = 180
MIN_DAYS_MEDIUM_CONFIDENCE = 30
MIN_DAYS_ANY_ANALYSIS      = 7


# ──────────────────────────────────────────────────────────────────────────────
# AIS INFRASTRUCTURE (from Jasreen's AIS integration)
# ──────────────────────────────────────────────────────────────────────────────

_PORT_KEYWORDS: dict[str, str] | None = None


def _build_port_keywords() -> dict[str, str]:
    """Build a lowercase keyword -> canonical port-name map."""
    from weather import PORT_COORDS

    keywords: dict[str, str] = {}
    for name in PORT_COORDS.keys():
        keywords[name.lower()] = name
        for part in name.replace(",", "-").split("-"):
            trimmed = part.strip().lower()
            if len(trimmed) > 3:
                keywords[trimmed] = name

    # Common AIS destination abbreviations
    keywords.update({
        "la": "Los Angeles-Long Beach",
        "long beach": "Los Angeles-Long Beach",
        "lb": "Los Angeles-Long Beach",
        "la/lb": "Los Angeles-Long Beach",
        "nyc": "New York-New Jersey",
        "new york": "New York-New Jersey",
        "nynj": "New York-New Jersey",
        "ny/nj": "New York-New Jersey",
        "nola": "New Orleans",
        "philly": "Philadelphia",
        "san fran": "San Francisco",
        "sf": "San Francisco",
        "jax": "Jacksonville",
        "bal": "Baltimore",
        "balt": "Baltimore",
        "sav": "Savannah",
        "chs": "Charleston",
        "mia": "Miami",
        "tpa": "Tampa",
        "hou": "Houston",
        "corpus": "Corpus Christi",
        "pt arthur": "Port Arthur",
        "lake chas": "Lake Charles",
        "norf": "Norfolk",
    })
    return keywords


def _resolve_us_port(destination: str | None) -> str | None:
    """Fuzzy-match an AIS destination string to a canonical PORT_COORDS key."""
    global _PORT_KEYWORDS
    if _PORT_KEYWORDS is None:
        _PORT_KEYWORDS = _build_port_keywords()

    if not destination:
        return None

    dest_lower = destination.lower().strip()
    if not dest_lower:
        return None

    if dest_lower in _PORT_KEYWORDS:
        return _PORT_KEYWORDS[dest_lower]

    for keyword in sorted(_PORT_KEYWORDS.keys(), key=len, reverse=True):
        if keyword in dest_lower:
            return _PORT_KEYWORDS[keyword]

    return None


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in nautical miles."""
    R_NM = 3440.065
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * R_NM * math.asin(math.sqrt(a))


def _eta_hours(distance_nm: float, sog_knots: float) -> float | None:
    """Return estimated hours to destination, or None if vessel isn't moving."""
    if sog_knots is None or sog_knots < MIN_SOG_KNOTS:
        return None
    return distance_nm / sog_knots


def _fetch_live_vessels() -> list[dict]:
    """Fetch the current snapshot of live vessels from the AIS microservice."""
    try:
        res = requests.get(AIS_API_URL, timeout=AIS_TIMEOUT)
        res.raise_for_status()
        data = res.json()
        return data.get("vessels", [])
    except Exception as e:
        logger.warning(f"[VesselAgent] AIS fetch failed ({e}); falling back to historical")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1a — LIVE AIS VESSEL CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def _classify_live_vessels(port: str) -> dict:
    """
    Fetch live AIS data and classify vessels relative to the target port.

    Returns a dict with:
        ais_available   — whether the AIS service responded with data
        anchor_count    — vessels at anchor within port radius
        moored_count    — vessels moored at berth
        incoming_72h    — vessels underway with ETA <= 72 hours
        mega_vessel_count — mega-vessels among the above
        queue_pressure  — anchor_count / (moored_count + 1)
        vessel_count_live — anchor_count + incoming_72h
    """
    from weather import PORT_COORDS

    # Resolve port coordinates and radii
    if port in PORT_ANCHORAGE_OVERRIDES:
        port_lat, port_lon, anchor_radius_nm, moored_radius_nm = PORT_ANCHORAGE_OVERRIDES[port]
    elif port in PORT_COORDS:
        port_lat, port_lon = PORT_COORDS[port]
        anchor_radius_nm = ANCHOR_RADIUS_NM
        moored_radius_nm = MOORED_RADIUS_NM
    else:
        logger.warning(f"[VesselAgent] No coordinates for '{port}' — AIS classification skipped")
        return _ais_empty()

    vessels = _fetch_live_vessels()
    if not vessels:
        return _ais_empty()

    anchor_count = 0
    moored_count = 0
    incoming_72h = 0
    mega_vessel_count = 0

    for v in vessels:
        lat = v.get("lat")
        lon = v.get("lon")
        if lat is None or lon is None:
            continue

        nav_status = (v.get("nav_status_label") or "").strip()
        destination = v.get("destination")
        draught = float(v.get("draught") or 0.0)
        vtype = (v.get("vessel_type_label") or "").strip()
        sog = v.get("sog")

        distance_nm = _haversine_nm(port_lat, port_lon, lat, lon)
        near_anchor = distance_nm <= anchor_radius_nm
        near_berth = distance_nm <= moored_radius_nm

        is_mega = draught >= MEGA_DRAUGHT_M and vtype in ("Cargo", "Tanker")

        if near_berth and nav_status == "Moored":
            moored_count += 1
            if is_mega:
                mega_vessel_count += 1
        elif near_anchor and nav_status == "At Anchor":
            anchor_count += 1
            if is_mega:
                mega_vessel_count += 1
        else:
            resolved = _resolve_us_port(destination)
            if resolved == port and nav_status in ("Under Way Using Engine", "Under Way Sailing"):
                eta_h = _eta_hours(distance_nm, sog)
                if eta_h is not None and eta_h <= ETA_HORIZON_HOURS:
                    incoming_72h += 1
                    if is_mega:
                        mega_vessel_count += 1

    vessel_count_live = anchor_count + incoming_72h
    queue_pressure = round(anchor_count / (moored_count + 1), 3)

    return {
        "ais_available":    True,
        "anchor_count":     anchor_count,
        "moored_count":     moored_count,
        "incoming_72h":     incoming_72h,
        "mega_vessel_count": mega_vessel_count,
        "queue_pressure":   queue_pressure,
        "vessel_count_live": vessel_count_live,
    }


def _ais_empty() -> dict:
    """Empty AIS result when service is unavailable or port has no coordinates."""
    return {
        "ais_available":    False,
        "anchor_count":     0,
        "moored_count":     0,
        "incoming_72h":     0,
        "mega_vessel_count": 0,
        "queue_pressure":   0.0,
        "vessel_count_live": 0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1b — HISTORICAL DATA EXTRACTION & VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def _extract_and_validate(port: str) -> dict:
    """
    Load PortWatch historical data and perform quality checks.

    Returns a dict with:
        daily       — DataFrame of daily port-call series
        vals        — numpy array of total portcalls
        data_days   — number of days of history
        last_date   — most recent date in the data
        data_lag    — days between last data point and today
        is_valid    — whether historical analysis can proceed
        issues      — list of data quality warnings
    """
    from data_cleaning import load_and_clean, get_port_daily_series

    data_file = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
    issues = []

    try:
        df    = load_and_clean(data_file)
        daily = get_port_daily_series(df, port)
    except FileNotFoundError:
        return {"is_valid": False, "issues": [f"Data file not found: {data_file}"],
                "daily": pd.DataFrame(), "vals": np.array([]), "data_days": 0,
                "last_date": None, "data_lag": 999}
    except Exception as e:
        return {"is_valid": False, "issues": [f"Data load error: {e}"],
                "daily": pd.DataFrame(), "vals": np.array([]), "data_days": 0,
                "last_date": None, "data_lag": 999}

    if daily.empty or len(daily) < MIN_DAYS_ANY_ANALYSIS:
        issues.append(f"Insufficient history: {len(daily)} days (need {MIN_DAYS_ANY_ANALYSIS}+)")
        return {"is_valid": False, "issues": issues,
                "daily": daily, "vals": np.array([]), "data_days": len(daily),
                "last_date": None, "data_lag": 999}

    vals      = daily["portcalls"].values.astype(float)
    last_date = pd.Timestamp(daily["date"].iloc[-1])
    data_lag  = max(0, (pd.Timestamp.today().normalize() - last_date).days)

    if data_lag > 14:
        issues.append(f"Stale data: last update {data_lag} days ago ({last_date.date()})")
    if len(daily) < MIN_DAYS_MEDIUM_CONFIDENCE:
        issues.append(f"Limited history: {len(daily)} days — trend analysis may be unreliable")

    return {
        "daily":     daily,
        "vals":      vals,
        "data_days": len(daily),
        "last_date": last_date,
        "data_lag":  data_lag,
        "is_valid":  True,
        "issues":    issues,
    }


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2a — VESSEL MIX DECOMPOSITION
# ──────────────────────────────────────────────────────────────────────────────

def _analyze_vessel_mix(daily: pd.DataFrame) -> dict:
    """
    Decompose vessel traffic by type. For each vessel type, compute:
        - Current 7-day average
        - 90-day baseline average
        - Share of total traffic (%)
        - Change vs baseline (%)
        - Whether the type is anomalously high (z-score > threshold)

    Returns dict with per-type analysis and a text summary.
    """
    vals_total   = daily["portcalls"].values.astype(float)
    recent_total = float(vals_total[-7:].mean()) if len(vals_total) >= 7 else float(vals_total.mean())

    type_analysis = {}
    anomalies     = []
    summary_parts = []

    for vtype in VESSEL_TYPES:
        col = f"portcalls_{vtype}"
        if col not in daily.columns:
            continue

        type_vals  = daily[col].values.astype(float)
        recent_avg = float(type_vals[-7:].mean()) if len(type_vals) >= 7 else float(type_vals.mean())
        baseline   = type_vals[-90:] if len(type_vals) >= 90 else type_vals
        base_avg   = float(baseline.mean())
        base_std   = float(baseline.std()) if len(baseline) > 1 else 1.0

        share_pct  = round(recent_avg / (recent_total + 1e-6) * 100, 1)
        change_pct = round((recent_avg - base_avg) / (base_avg + 1e-6) * 100, 1)
        z_score    = (recent_avg - base_avg) / (base_std + 1e-6)

        is_anomaly = abs(z_score) > ANOMALY_Z_THRESHOLD

        type_analysis[vtype] = {
            "recent_avg":   round(recent_avg, 2),
            "baseline_avg": round(base_avg, 2),
            "share_pct":    share_pct,
            "change_pct":   change_pct,
            "z_score":      round(z_score, 2),
            "is_anomaly":   is_anomaly,
        }

        if is_anomaly:
            direction = "surge" if z_score > 0 else "drop"
            anomalies.append(
                f"{vtype.replace('_', ' ').title()} {direction}: "
                f"{recent_avg:.1f}/day vs {base_avg:.1f} baseline "
                f"({change_pct:+.0f}%, z={z_score:.1f})"
            )

        if share_pct >= 10:
            summary_parts.append(f"{vtype.replace('_', ' ').title()}: {share_pct}%")

    if type_analysis:
        dominant = max(type_analysis, key=lambda t: type_analysis[t]["share_pct"])
        dominant_share = type_analysis[dominant]["share_pct"]
    else:
        dominant, dominant_share = "unknown", 0.0

    summary = (
        f"Mix: {', '.join(summary_parts)}. "
        f"Dominant type: {dominant.replace('_', ' ')} ({dominant_share}%)."
    )
    if anomalies:
        summary += f" Anomalies detected: {len(anomalies)}."

    return {
        "type_analysis":  type_analysis,
        "anomalies":      anomalies,
        "dominant_type":  dominant,
        "dominant_share": dominant_share,
        "summary":        summary,
    }


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2b — DAY-OF-WEEK-AWARE 72-HOUR PROJECTION (historical fallback)
# ──────────────────────────────────────────────────────────────────────────────

def _project_72h_arrivals(daily: pd.DataFrame) -> tuple[int, str]:
    """
    Project vessel arrivals for the next 72 hours using day-of-week patterns.

    Used as the primary vessel_count when AIS data is unavailable. When AIS
    is available, this still runs to provide a historical baseline for surge
    comparison.

    Returns (vessel_count, method_description).
    """
    vals  = daily["portcalls"].values.astype(float)
    dates = pd.DatetimeIndex(daily["date"].values)

    if len(vals) < 28:
        avg = float(vals[-7:].mean()) if len(vals) >= 7 else float(vals.mean())
        return int(round(avg * 3)), "simple_avg"

    window = min(90, len(vals))
    recent_dates = dates[-window:]
    recent_vals  = vals[-window:]
    dow_avgs     = {}
    for dow in range(7):
        mask = np.array([d.dayofweek == dow for d in recent_dates])
        if mask.sum() > 0:
            dow_avgs[dow] = float(recent_vals[mask].mean())
        else:
            dow_avgs[dow] = float(recent_vals.mean())

    last_date = dates[-1]
    total     = 0.0
    for offset in range(1, 4):
        future_dow = (last_date + pd.Timedelta(days=offset)).dayofweek
        total += dow_avgs[future_dow]

    return int(round(total)), "dow_adjusted"


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2c — DELAY RISK SCORING (4-component: queue + pressure + volatility + momentum)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_delay_score(vals: np.ndarray, ais: dict) -> tuple[float, dict]:
    """
    Score delay risk (0-1) using four components:

    1. Queue pressure (35% weight) — LIVE AIS SIGNAL:
       anchor_count / (moored_count + 1), saturating at 3.0.
       Only active when AIS data is available; otherwise this component
       defers its weight to historical pressure.

    2. Historical traffic pressure (25% weight, or 60% if no AIS):
       Recent 7-day avg vs 90-day baseline. Mapped from DELAY_FLOOR_RATIO
       (score=0) to DELAY_CEIL_RATIO (score=1).

    3. Volatility penalty (25% weight):
       Coefficient of variation of the recent 7 days.

    4. Trend momentum (15% weight):
       Rising traffic in last 7 days vs prior 7 days.

    When AIS is unavailable, weights revert to 60/25/15 (3-component).

    Returns (delay_score, component_breakdown).
    """
    recent_7d  = vals[-7:]  if len(vals) >= 7  else vals[-3:]
    baseline   = vals[-90:] if len(vals) >= 90  else vals
    recent_avg = float(recent_7d.mean())
    base_avg   = float(baseline.mean())

    # Component 1: Queue pressure (live AIS)
    ais_available = ais.get("ais_available", False)
    queue_pressure_raw = ais.get("queue_pressure", 0.0)
    queue_component = min(queue_pressure_raw / 3.0, 1.0)

    # Component 2: Historical traffic pressure
    ratio          = recent_avg / (base_avg + 1e-6)
    pressure_range = DELAY_CEIL_RATIO - DELAY_FLOOR_RATIO
    pressure       = min(max((ratio - DELAY_FLOOR_RATIO) / pressure_range, 0.0), 1.0)

    # Component 3: Volatility penalty (coefficient of variation)
    recent_std = float(recent_7d.std()) if len(recent_7d) > 1 else 0.0
    cv         = recent_std / (recent_avg + 1e-6)
    volatility = min(cv / 0.5, 1.0)

    # Component 4: Trend momentum
    if len(vals) >= 14:
        prior_7d   = vals[-14:-7]
        trend_diff = float(recent_7d.mean() - prior_7d.mean())
        momentum   = min(max(trend_diff / 5.0, 0.0), 1.0)
    else:
        momentum = 0.0

    # Weighted combination — weights shift based on AIS availability
    if ais_available:
        # Full 4-component scoring with live queue data
        w_queue    = 0.35
        w_pressure = 0.25
        w_vol      = 0.25
        w_momentum = 0.15
        delay_score = (
            w_queue    * queue_component
            + w_pressure * pressure
            + w_vol      * volatility
            + w_momentum * momentum
        )
        formula = "0.35*queue + 0.25*pressure + 0.25*volatility + 0.15*momentum"

        # Backlog-building bonus: queue is growing faster than it drains
        anchor = ais.get("anchor_count", 0)
        moored = ais.get("moored_count", 0)
        if anchor > moored and moored > 0:
            delay_score = min(delay_score + 0.10, 1.0)
            formula += " + 0.10 backlog bonus"
    else:
        # Fallback: 3-component historical scoring (no queue data)
        w_pressure = 0.60
        w_vol      = 0.25
        w_momentum = 0.15
        delay_score = (
            w_pressure * pressure
            + w_vol      * volatility
            + w_momentum * momentum
        )
        formula = "0.60*pressure + 0.25*volatility + 0.15*momentum (no AIS)"

    delay_score = round(min(delay_score, 1.0), 3)

    breakdown = {
        "ais_available":        ais_available,
        "queue_pressure_raw":   round(queue_pressure_raw, 3),
        "queue_component":      round(queue_component, 3),
        "traffic_ratio":        round(ratio, 3),
        "pressure_component":   round(pressure, 3),
        "volatility_cv":        round(cv, 3),
        "volatility_component": round(volatility, 3),
        "trend_momentum":       round(momentum, 3),
        "formula":              formula,
    }

    return delay_score, breakdown


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2d — SURGE / ANOMALY DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def _detect_anomalies(vals: np.ndarray, daily: pd.DataFrame, ais: dict) -> list[str]:
    """
    Detect anomalous patterns in vessel traffic.

    Checks:
    1. Overall traffic surge (z-score > 2.0 vs 90-day baseline)
    2. Overall traffic collapse (z-score < -2.0)
    3. Weekend surge (weekend > weekday in last 14 days)
    4. Acceleration (second derivative of weekly averages)
    5. Queue building (AIS: anchor_count > moored_count)
    """
    anomalies = []
    baseline  = vals[-90:] if len(vals) >= 90 else vals
    base_avg  = float(baseline.mean())
    base_std  = float(baseline.std()) if len(baseline) > 1 else 1.0

    # 1. Overall traffic surge/collapse
    recent_avg = float(vals[-7:].mean()) if len(vals) >= 7 else float(vals.mean())
    z = (recent_avg - base_avg) / (base_std + 1e-6)

    if z > ANOMALY_Z_THRESHOLD:
        anomalies.append(
            f"Traffic surge: {recent_avg:.1f}/day vs {base_avg:.1f} baseline "
            f"(+{(recent_avg - base_avg) / (base_avg + 1e-6) * 100:.0f}%, z={z:.1f})"
        )
    elif z < -ANOMALY_Z_THRESHOLD:
        anomalies.append(
            f"Traffic drop: {recent_avg:.1f}/day vs {base_avg:.1f} baseline "
            f"({(recent_avg - base_avg) / (base_avg + 1e-6) * 100:.0f}%, z={z:.1f})"
        )

    # 2. Weekend anomaly
    if len(daily) >= 14:
        dates = pd.DatetimeIndex(daily["date"].values)
        last14_vals  = vals[-14:]
        last14_dates = dates[-14:]
        weekend_mask = np.array([d.dayofweek >= 5 for d in last14_dates])
        weekday_mask = ~weekend_mask

        if weekend_mask.sum() > 0 and weekday_mask.sum() > 0:
            weekend_avg = float(last14_vals[weekend_mask].mean())
            weekday_avg = float(last14_vals[weekday_mask].mean())
            if weekend_avg > weekday_avg * 1.15 and weekday_avg > 1:
                anomalies.append(
                    f"Unusual weekend activity: {weekend_avg:.1f}/day vs "
                    f"{weekday_avg:.1f} weekday avg (+{(weekend_avg / weekday_avg - 1) * 100:.0f}%)"
                )

    # 3. Acceleration
    if len(vals) >= 21:
        week1 = vals[-21:-14].mean()
        week2 = vals[-14:-7].mean()
        week3 = vals[-7:].mean()
        accel = (week3 - week2) - (week2 - week1)
        if accel > 3.0:
            anomalies.append(
                f"Accelerating arrivals: week-over-week rate increasing "
                f"({week1:.0f} -> {week2:.0f} -> {week3:.0f} ships/day)"
            )

    # 4. AIS queue-building anomaly
    if ais.get("ais_available", False):
        anchor = ais.get("anchor_count", 0)
        moored = ais.get("moored_count", 0)
        if anchor > moored and anchor >= 3:
            anomalies.append(
                f"Queue building: {anchor} vessels at anchor vs {moored} at berth "
                f"(queue pressure {ais.get('queue_pressure', 0):.1f}x)"
            )

    return anomalies


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3 — LLM REFLECTION (Analyst Note)
# ──────────────────────────────────────────────────────────────────────────────

def _generate_analyst_note(
    port: str,
    vessel_count: int,
    delay_score: float,
    delay_breakdown: dict,
    mega_flag: bool,
    mix_analysis: dict,
    anomalies: list[str],
    confidence: str,
    ais: dict,
) -> str:
    """
    Call Groq LLM to generate a structured vessel arrival briefing.

    Receives both live AIS signals and historical analytics for rich context.
    Uses chain-of-thought prompting with few-shot examples.
    Falls back to rule-based note if the LLM is unavailable.
    """
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage, SystemMessage

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return _fallback_analyst_note(
                port, vessel_count, delay_score, delay_breakdown,
                mega_flag, mix_analysis, anomalies, confidence, ais,
            )

        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=api_key,
            temperature=0.15,
            max_tokens=350,
        )

        system = """You are a senior port operations analyst at DockWise AI.
You produce vessel arrival risk briefings for logistics managers and terminal operators.

Your analysis style:
- Lead with the most operationally impactful finding.
- Use specific numbers from the data — never generalize when you have exact figures.
- If anomalies are detected, explain what they mean for terminal operations.
- End with 1-2 specific recommendations tied to the data.
- Be concise: 3-4 sentences maximum.

Example briefing for a HIGH delay risk:
"Houston faces elevated arrival pressure with 127 vessels projected over 72 hours (1.28x baseline). Tanker traffic has surged +34% above the 90-day average, likely driven by increased Gulf LNG export demand. Terminal operators should pre-position berth allocation for tanker priority and expect 2-3 day anchorage queues. Recommend diverting non-urgent bulk cargo to Corpus Christi or Freeport."

Example briefing for a LOW delay risk:
"Oakland vessel arrivals are running 12% below seasonal baseline at 34 projected over 72 hours. Container share has dropped to 45% from the typical 62%, suggesting possible carrier blank sailings on Transpacific lanes. No operational adjustments needed, but monitor for post-CNY volume recovery in the next 14 days."
"""

        # Build the structured data prompt with both AIS and historical signals
        anomaly_text = "\n    ".join(anomalies) if anomalies else "None detected"
        mix_text = mix_analysis.get("summary", "Not available")

        # AIS live signals section (only if available)
        if ais.get("ais_available", False):
            ais_section = f"""
Live AIS Snapshot (real-time):
  Vessels at anchor (waiting): {ais['anchor_count']}
  Vessels moored (at berth):   {ais['moored_count']}
  Vessels inbound ETA <= 72h:  {ais['incoming_72h']}
  Queue pressure:              {ais['queue_pressure']:.1f}x (waiting per berth)
  Mega-vessels detected:       {ais['mega_vessel_count']}"""
        else:
            ais_section = "\nLive AIS: Unavailable — analysis based on historical data only."

        prompt = f"""Analyze this vessel arrival data and produce a briefing:

Port: {port}
72-Hour Vessel Pressure: {vessel_count} vessels
Delay Risk Score: {delay_score:.3f} / 1.0
  - Queue pressure (AIS): {delay_breakdown.get('queue_component', 0):.2f}
  - Traffic ratio vs baseline: {delay_breakdown['traffic_ratio']:.2f}x
  - Pressure component: {delay_breakdown['pressure_component']:.2f}
  - Volatility (CV): {delay_breakdown['volatility_cv']:.2f}
  - Trend momentum: {delay_breakdown['trend_momentum']:.2f}
  - Scoring formula: {delay_breakdown['formula']}
Mega-Vessel Port: {"Yes" if mega_flag else "No"}
Vessel Mix (historical): {mix_text}
{ais_section}
Anomalies Detected:
    {anomaly_text}
Data Confidence: {confidence}

Think step by step:
1. What is the primary risk signal? (queue backup, historical pressure, volatility, or mix change)
2. What does the vessel mix tell us about cargo type demand?
3. Are the anomalies operationally significant?
4. What should a terminal operator do in the next 72 hours?

Now write the 3-4 sentence analyst briefing:"""

        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()

    except Exception as e:
        logger.warning(f"[VesselAgent] LLM analyst note failed: {e}")
        return _fallback_analyst_note(
            port, vessel_count, delay_score, delay_breakdown,
            mega_flag, mix_analysis, anomalies, confidence, ais,
        )


def _fallback_analyst_note(
    port: str,
    vessel_count: int,
    delay_score: float,
    delay_breakdown: dict,
    mega_flag: bool,
    mix_analysis: dict,
    anomalies: list[str],
    confidence: str,
    ais: dict,
) -> str:
    """Rule-based analyst note when LLM is unavailable."""
    parts = []
    ratio = delay_breakdown["traffic_ratio"]

    # Lead sentence
    if delay_score >= 0.67:
        parts.append(
            f"HIGH arrival pressure at {port}: {vessel_count} vessels projected "
            f"over 72 hours ({ratio:.2f}x baseline)."
        )
    elif delay_score >= 0.33:
        parts.append(
            f"MODERATE arrival pressure at {port}: {vessel_count} vessels projected "
            f"over 72 hours ({ratio:.2f}x baseline)."
        )
    else:
        parts.append(
            f"LOW arrival pressure at {port}: {vessel_count} vessels projected "
            f"over 72 hours ({ratio:.2f}x baseline)."
        )

    # AIS queue insight (if available)
    if ais.get("ais_available", False):
        anchor = ais["anchor_count"]
        moored = ais["moored_count"]
        incoming = ais["incoming_72h"]
        if anchor > 0 or incoming > 0:
            parts.append(
                f"Live AIS: {anchor} at anchor, {moored} at berth, "
                f"{incoming} inbound within 72h."
            )

    # Mix insight
    dominant = mix_analysis.get("dominant_type", "").replace("_", " ")
    dominant_share = mix_analysis.get("dominant_share", 0)
    if dominant and dominant_share > 40:
        parts.append(f"Traffic is {dominant}-dominant ({dominant_share}% of calls).")

    # Anomalies
    if anomalies:
        parts.append(f"Alert: {anomalies[0]}.")

    # Mega-vessel note
    if mega_flag and delay_score >= 0.5:
        parts.append("Mega-vessel capable port under pressure — expect berth competition.")

    return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4 — CONFIDENCE VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def _assess_confidence(
    data_days: int, data_lag: int, issues: list[str], ais_available: bool
) -> str:
    """
    Score overall confidence in the vessel analysis.

    HIGH:   AIS available + 180+ days history + data < 3 days old + no issues
            OR AIS available + 30+ days history (live data compensates for stale CSV)
    MEDIUM: 30+ days of history + data < 14 days old
            OR AIS available (live data alone provides medium confidence)
    LOW:    anything below MEDIUM thresholds
    """
    if ais_available:
        # AIS live data boosts confidence
        if (data_days >= MIN_DAYS_HIGH_CONFIDENCE
                and data_lag <= 3
                and not issues):
            return "HIGH"
        elif data_days >= MIN_DAYS_MEDIUM_CONFIDENCE:
            return "HIGH"  # AIS + decent history = HIGH
        else:
            return "MEDIUM"  # AIS alone = MEDIUM
    else:
        # Historical-only confidence (original logic)
        if (data_days >= MIN_DAYS_HIGH_CONFIDENCE
                and data_lag <= 3
                and not issues):
            return "HIGH"
        elif data_days >= MIN_DAYS_MEDIUM_CONFIDENCE and data_lag <= 14:
            return "MEDIUM"
        else:
            return "LOW"


# ──────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT — run()
# ──────────────────────────────────────────────────────────────────────────────

def run(state: "RiskState") -> "RiskState":
    """
    Vessel Arrival Risk Agent — live AIS + historical 4-phase analysis.

    Phase 1: Fetch live AIS data + load/validate historical PortWatch data.
    Phase 2: Multi-signal analysis (mix, projection, delay score, anomalies).
    Phase 3: LLM analyst briefing with chain-of-thought reasoning.
    Phase 4: Confidence validation.

    Reads:  state["port"]
    Writes: vessel_count, vessel_delay_score, mega_vessel_flag,
            anchor_count, moored_count, incoming_72h,
            queue_pressure, mega_vessel_count,
            vessel_analyst_note, vessel_anomalies, vessel_mix_summary,
            vessel_confidence
    """
    port = state["port"]
    logger.info(f"[VesselAgent] == Assessing vessel arrival risk for '{port}' ==")

    # ── PHASE 1a: Live AIS Classification ──────────────────────────────────
    ais = _classify_live_vessels(port)

    if ais["ais_available"]:
        logger.info(
            f"[VesselAgent] AIS live: anchor={ais['anchor_count']}  "
            f"moored={ais['moored_count']}  incoming={ais['incoming_72h']}  "
            f"queue={ais['queue_pressure']}  mega={ais['mega_vessel_count']}"
        )

    # ── PHASE 1b: Historical Data Extraction & Validation ──────────────────
    extraction = _extract_and_validate(port)
    hist_valid = extraction["is_valid"]

    if not hist_valid and not ais["ais_available"]:
        # Neither data source available — return safe defaults
        logger.warning(
            f"[VesselAgent] No data sources available for '{port}': "
            f"{extraction['issues']}"
        )
        return {
            **state,
            "vessel_count":        0,
            "vessel_delay_score":  0.0,
            "mega_vessel_flag":    port in MEGA_VESSEL_PORTS,
            "anchor_count":        0,
            "moored_count":        0,
            "incoming_72h":        0,
            "queue_pressure":      0.0,
            "mega_vessel_count":   0,
            "vessel_analyst_note": f"Insufficient data for {port}. {'; '.join(extraction['issues'])}",
            "vessel_anomalies":    [],
            "vessel_mix_summary":  "No data available",
            "vessel_confidence":   "LOW",
        }

    # ── PHASE 2: Multi-Signal Analysis ─────────────────────────────────────

    # 2a: Vessel mix decomposition (requires historical data)
    if hist_valid:
        daily = extraction["daily"]
        vals  = extraction["vals"]
        mix_analysis = _analyze_vessel_mix(daily)
    else:
        daily = pd.DataFrame()
        vals  = np.array([])
        mix_analysis = {
            "type_analysis": {}, "anomalies": [], "dominant_type": "unknown",
            "dominant_share": 0.0, "summary": "Historical data unavailable",
        }

    # 2b: 72-hour arrival projection
    # Primary: live AIS count. Fallback: day-of-week historical projection.
    if ais["ais_available"]:
        vessel_count = ais["vessel_count_live"]
        projection_method = "ais_live"
    elif hist_valid:
        vessel_count, projection_method = _project_72h_arrivals(daily)
    else:
        vessel_count = 0
        projection_method = "none"

    # Also compute historical projection for baseline comparison (if available)
    if hist_valid:
        hist_projected, _ = _project_72h_arrivals(daily)
    else:
        hist_projected = 0

    # 2c: Delay risk scoring (uses both AIS and historical signals)
    if hist_valid:
        vessel_delay_score, delay_breakdown = _compute_delay_score(vals, ais)
    elif ais["ais_available"]:
        # AIS-only delay score: based purely on queue pressure
        qp = ais["queue_pressure"]
        queue_component = min(qp / 3.0, 1.0)
        vessel_delay_score = round(queue_component, 3)
        # Backlog bonus
        if ais["anchor_count"] > ais["moored_count"] and ais["moored_count"] > 0:
            vessel_delay_score = round(min(vessel_delay_score + 0.10, 1.0), 3)
        delay_breakdown = {
            "ais_available":        True,
            "queue_pressure_raw":   round(qp, 3),
            "queue_component":      round(queue_component, 3),
            "traffic_ratio":        0.0,
            "pressure_component":   0.0,
            "volatility_cv":        0.0,
            "volatility_component": 0.0,
            "trend_momentum":       0.0,
            "formula":              "AIS-only: queue_pressure / 3.0 (no historical data)",
        }
    else:
        vessel_delay_score = 0.0
        delay_breakdown = {
            "ais_available": False, "queue_pressure_raw": 0.0,
            "queue_component": 0.0, "traffic_ratio": 0.0,
            "pressure_component": 0.0, "volatility_cv": 0.0,
            "volatility_component": 0.0, "trend_momentum": 0.0,
            "formula": "no data",
        }

    # 2d: Anomaly detection
    if hist_valid:
        traffic_anomalies = _detect_anomalies(vals, daily, ais)
        all_anomalies = mix_analysis["anomalies"] + traffic_anomalies
    elif ais["ais_available"]:
        # AIS-only anomaly: check for queue building
        all_anomalies = []
        anchor = ais["anchor_count"]
        moored = ais["moored_count"]
        if anchor > moored and anchor >= 3:
            all_anomalies.append(
                f"Queue building: {anchor} vessels at anchor vs {moored} at berth "
                f"(queue pressure {ais['queue_pressure']:.1f}x)"
            )
    else:
        all_anomalies = []

    # ── Mega-vessel flag (AIS draught-based + port list + historical inference)
    if ais["ais_available"]:
        mega_vessel_flag = ais["mega_vessel_count"] > 0 or port in MEGA_VESSEL_PORTS
    elif hist_valid:
        container_data = mix_analysis["type_analysis"].get("container", {})
        container_avg = container_data.get("recent_avg", 0.0)
        mega_vessel_flag = container_avg >= 5.0 or port in MEGA_VESSEL_PORTS
    else:
        mega_vessel_flag = port in MEGA_VESSEL_PORTS

    # ── PHASE 4: Confidence Validation ─────────────────────────────────────
    data_days = extraction["data_days"] if hist_valid else 0
    data_lag  = extraction["data_lag"]  if hist_valid else 999
    issues    = extraction["issues"]    if hist_valid else []
    confidence = _assess_confidence(data_days, data_lag, issues, ais["ais_available"])

    # ── PHASE 3: LLM Reflection ────────────────────────────────────────────
    analyst_note = _generate_analyst_note(
        port=port,
        vessel_count=vessel_count,
        delay_score=vessel_delay_score,
        delay_breakdown=delay_breakdown,
        mega_flag=mega_vessel_flag,
        mix_analysis=mix_analysis,
        anomalies=all_anomalies,
        confidence=confidence,
        ais=ais,
    )

    logger.info(
        f"[VesselAgent] port={port}  count_72h={vessel_count} ({projection_method})  "
        f"delay={vessel_delay_score}  mega={mega_vessel_flag}  "
        f"anomalies={len(all_anomalies)}  confidence={confidence}  "
        f"ais={'live' if ais['ais_available'] else 'offline'}  "
        f"anchor={ais['anchor_count']}  moored={ais['moored_count']}  "
        f"incoming={ais['incoming_72h']}  queue={ais['queue_pressure']}  "
        f"ratio={delay_breakdown['traffic_ratio']:.2f}  "
        f"dominant={mix_analysis['dominant_type']}  "
        f"hist_projected={hist_projected}"
    )

    return {
        **state,
        # AIS live signals (populated from AIS or zeroed if unavailable)
        "anchor_count":        ais["anchor_count"],
        "moored_count":        ais["moored_count"],
        "incoming_72h":        ais["incoming_72h"],
        "queue_pressure":      ais["queue_pressure"],
        "mega_vessel_count":   ais["mega_vessel_count"],
        # Composite signals
        "vessel_count":        vessel_count,
        "vessel_delay_score":  vessel_delay_score,
        "mega_vessel_flag":    mega_vessel_flag,
        # Analytical outputs
        "vessel_analyst_note": analyst_note,
        "vessel_anomalies":    all_anomalies,
        "vessel_mix_summary":  mix_analysis["summary"],
        "vessel_confidence":   confidence,
    }
