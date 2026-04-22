"""
vessel_agent.py
===============
Vessel Arrival Risk Agent for DockWise AI.

Implements the original project plan:
  "How many vessels arriving at this port in the next 72 hours?"

Uses LIVE AIS data (from the AIS microservice on port 8001) combined with
historical PortWatch baselines to produce a real 72-hour arrival pressure
signal for each port.

Signals computed
----------------
    anchor_count       — vessels currently at anchor within ~15 nm of port
                         (already waiting for a berth — guaranteed future load)
    moored_count       — vessels currently moored within ~5 nm of port
                         (at berth right now — capacity reference)
    incoming_72h       — vessels underway whose destination resolves to this
                         port AND whose ETA (distance / SOG) is ≤ 72 hours
    vessel_count       — live 72-hour arrival pressure = anchor + incoming_72h
                         (replaces the old historical extrapolation)
    mega_vessel_count  — vessels meeting mega-vessel criteria among the above
    queue_pressure     — anchor_count / (moored_count + 1)
                         (how many are waiting per vessel currently serviced)
    vessel_delay_score — 0–1 combined delay risk:
                           60% queue pressure + 40% arrival surge vs baseline
                           + 0.15 bonus if anchor_count > moored_count
    mega_vessel_flag   — True if any mega vessels observed or port in hardcoded
                         mega-vessel set

Data sources
------------
- LIVE:   GET http://localhost:8001/api/vessels  (AIS microservice)
- HIST:   portwatch_us_data.csv                  (baseline for surge comparison)
- COORDS: weather.PORT_COORDS                    (port lat/lon lookup)

Fallback
--------
If the AIS service is unreachable, falls back to a historical-only projection
so the risk pipeline never breaks.
"""

from __future__ import annotations
import os
import math
import logging
from typing import TYPE_CHECKING

import numpy as np
import requests

if TYPE_CHECKING:
    from agents import RiskState

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AIS_API_URL = os.environ.get("AIS_API_URL", "http://localhost:8001/api/vessels")
AIS_TIMEOUT = 3.0  # seconds

# Default spatial thresholds (nautical miles)
ANCHOR_RADIUS_NM = 15.0   # vessels at anchor within this radius = "waiting"
MOORED_RADIUS_NM = 5.0    # vessels moored within this radius = "at berth"

# Per-port anchorage overrides for ports where the city-center coordinates in
# weather.PORT_COORDS don't reflect actual anchorage/berth locations — typically
# elongated river/channel ports that span tens of miles.
#
# Format: port_name → (lat, lon, anchor_radius_nm, moored_radius_nm)
#
# Empirically validated against live AIS data. Add new entries here as needed.
PORT_ANCHORAGE_OVERRIDES: dict[str, tuple[float, float, float, float]] = {
    # Mississippi River — port spans ~70 miles along the river corridor.
    # Center on Convent area; large radius covers from St. Charles to Baton Rouge.
    "South Louisiana": (30.00, -90.55, 60.0, 15.0),
    # Houston Ship Channel — slightly larger moored radius to catch the upper
    # channel terminals (Barbours Cut, Bayport).
    "Houston":         (29.75, -95.08, 15.0, 8.0),
}

# Forecast horizon
ETA_HORIZON_HOURS = 72.0  # the plan: "arriving in next 72 hours"
MIN_SOG_KNOTS     = 0.5   # below this, vessel is effectively stationary

# Mega-vessel detection
MEGA_DRAUGHT_M = 12.0     # draught threshold for ultra-large container/tankers

# Ports known to regularly handle mega-vessels (10,000+ TEU)
MEGA_VESSEL_PORTS = {
    "Los Angeles-Long Beach", "New York-New Jersey", "Savannah", "Houston",
    "Norfolk", "Charleston", "Oakland", "Seattle", "Tacoma", "Port of Virginia",
}


# ── Destination → US port fuzzy matching ──────────────────────────────────────
# Mirrors the JS logic in frontend/VesselMap.jsx::resolveUSPort

_PORT_KEYWORDS: dict[str, str] | None = None


def _build_port_keywords() -> dict[str, str]:
    """Build a lowercase keyword → canonical port-name map."""
    from weather import PORT_COORDS

    keywords: dict[str, str] = {}
    for name in PORT_COORDS.keys():
        keywords[name.lower()] = name
        # Split on commas and hyphens to get sub-parts (e.g., "Wilmington, NC" → "wilmington")
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
    """
    Fuzzy-match an AIS destination string to a canonical PORT_COORDS key.
    Returns None if no match found.
    """
    global _PORT_KEYWORDS
    if _PORT_KEYWORDS is None:
        _PORT_KEYWORDS = _build_port_keywords()

    if not destination:
        return None

    dest_lower = destination.lower().strip()
    if not dest_lower:
        return None

    # Exact match first
    if dest_lower in _PORT_KEYWORDS:
        return _PORT_KEYWORDS[dest_lower]

    # Substring match (longer keywords take priority to avoid "la" matching "dallas")
    for keyword in sorted(_PORT_KEYWORDS.keys(), key=len, reverse=True):
        if keyword in dest_lower:
            return _PORT_KEYWORDS[keyword]

    return None


# ── Geospatial helpers ────────────────────────────────────────────────────────

def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in nautical miles."""
    R_NM = 3440.065  # Earth radius in nautical miles
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


# ── Live AIS fetch ────────────────────────────────────────────────────────────

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


# ── Historical baseline (for arrival surge comparison) ────────────────────────

def _historical_daily_median(port: str) -> float:
    """
    Median daily portcalls over a non-overlapping 90-day window (ending before
    the last 7 days), used as the baseline for arrival surge comparison.
    Uses median instead of mean to be robust against outliers (strikes, storms).
    """
    try:
        from data_cleaning import load_and_clean, get_port_daily_series
        data_file = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
        df = load_and_clean(data_file)
        daily = get_port_daily_series(df, port)
        if daily.empty:
            return 0.0
        vals = daily["portcalls"].values.astype(float)
        if len(vals) >= 97:
            baseline = vals[-97:-7]        # clean 90-day window
        elif len(vals) > 7:
            baseline = vals[:-7]           # whatever's available, excluding recent
        else:
            baseline = vals                # too little data; use everything
        return float(np.median(baseline)) if len(baseline) else 0.0
    except Exception as e:
        logger.warning(f"[VesselAgent] historical baseline failed for {port}: {e}")
        return 0.0


# ── Main agent entry point ────────────────────────────────────────────────────

def run(state: "RiskState") -> "RiskState":
    """
    Vessel Arrival Risk Agent — live AIS + 72-hour ETA filtering.

    Reads:  state["port"]
    Writes: vessel_count, vessel_delay_score, mega_vessel_flag,
            anchor_count, moored_count, incoming_72h,
            queue_pressure, mega_vessel_count
    """
    from weather import PORT_COORDS

    port = state["port"]
    logger.info(f"[VesselAgent] Assessing 72-hour arrival pressure for '{port}'")

    # Resolve coordinates and radii: prefer override, fall back to PORT_COORDS
    if port in PORT_ANCHORAGE_OVERRIDES:
        port_lat, port_lon, anchor_radius_nm, moored_radius_nm = PORT_ANCHORAGE_OVERRIDES[port]
    elif port in PORT_COORDS:
        port_lat, port_lon = PORT_COORDS[port]
        anchor_radius_nm = ANCHOR_RADIUS_NM
        moored_radius_nm = MOORED_RADIUS_NM
    else:
        logger.warning(f"[VesselAgent] No coordinates for '{port}' — returning defaults")
        return _defaults(state, port)

    vessels = _fetch_live_vessels()

    if not vessels:
        return _historical_fallback(state, port)

    # ── Classify vessels ────────────────────────────────────────────────────
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

        # Classification priority: moored > anchored > incoming-within-72h
        classified_as_incoming = False

        if near_berth and nav_status == "Moored":
            moored_count += 1
            if is_mega:
                mega_vessel_count += 1
        elif near_anchor and nav_status == "At Anchor":
            anchor_count += 1
            if is_mega:
                mega_vessel_count += 1
        else:
            # Not at/near the port — check if heading there AND will arrive in 72h
            resolved = _resolve_us_port(destination)
            if resolved == port and nav_status in ("Under Way Using Engine", "Under Way Sailing"):
                eta_h = _eta_hours(distance_nm, sog)
                if eta_h is not None and eta_h <= ETA_HORIZON_HOURS:
                    incoming_72h += 1
                    classified_as_incoming = True
                    if is_mega:
                        mega_vessel_count += 1

    # ── Derived signals ─────────────────────────────────────────────────────

    # Total 72-hour arrival pressure: already-waiting + arriving-within-72h
    vessel_count = anchor_count + incoming_72h

    # Queue pressure: how many are waiting per berth currently occupied?
    queue_pressure = round(anchor_count / (moored_count + 1), 3)

    # Arrival surge: vessels arriving in 72h vs historical 72h throughput
    baseline_daily = _historical_daily_median(port)
    baseline_72h = baseline_daily * 3.0
    if baseline_72h > 0:
        arrival_surge_ratio = vessel_count / baseline_72h
    else:
        arrival_surge_ratio = 0.0

    # Combined delay score (0–1):
    #   60% queue pressure (saturates at ~3 waiting per berth)
    #   40% arrival surge (saturates at 2× normal 72h throughput)
    queue_contrib = min(queue_pressure / 3.0, 1.0)
    surge_contrib = min(arrival_surge_ratio / 2.0, 1.0)
    vessel_delay_score = 0.60 * queue_contrib + 0.40 * surge_contrib

    # Backlog-building bonus: if more vessels are waiting than being serviced,
    # the queue is growing faster than it's draining
    if anchor_count > moored_count and moored_count > 0:
        vessel_delay_score = min(vessel_delay_score + 0.15, 1.0)

    vessel_delay_score = round(vessel_delay_score, 3)
    mega_vessel_flag = mega_vessel_count > 0 or port in MEGA_VESSEL_PORTS

    logger.info(
        f"[VesselAgent] port={port}  anchor={anchor_count}  moored={moored_count}  "
        f"incoming_72h={incoming_72h}  queue_pressure={queue_pressure}  "
        f"surge={arrival_surge_ratio:.2f}  delay={vessel_delay_score}  "
        f"mega={mega_vessel_flag} ({mega_vessel_count})"
    )

    return {
        **state,
        "vessel_count":       vessel_count,
        "vessel_delay_score": vessel_delay_score,
        "mega_vessel_flag":   mega_vessel_flag,
        "anchor_count":       anchor_count,
        "moored_count":       moored_count,
        "incoming_72h":       incoming_72h,
        "queue_pressure":     queue_pressure,
        "mega_vessel_count":  mega_vessel_count,
    }


# ── Fallbacks ─────────────────────────────────────────────────────────────────

def _defaults(state: "RiskState", port: str) -> "RiskState":
    """Zero-valued defaults when port is unknown."""
    return {
        **state,
        "vessel_count":       0,
        "vessel_delay_score": 0.0,
        "mega_vessel_flag":   port in MEGA_VESSEL_PORTS,
        "anchor_count":       0,
        "moored_count":       0,
        "incoming_72h":       0,
        "queue_pressure":     0.0,
        "mega_vessel_count":  0,
    }


def _historical_fallback(state: "RiskState", port: str) -> "RiskState":
    """
    Legacy historical-only path used when AIS microservice is unreachable.
    Projects 72-hour arrivals from recent 7-day mean and scores delay risk
    from a non-overlapping 90-day baseline.
    """
    try:
        from data_cleaning import load_and_clean, get_port_daily_series
        data_file = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
        df = load_and_clean(data_file)
        daily = get_port_daily_series(df, port)

        if daily.empty or len(daily) < 7:
            return _defaults(state, port)

        vals = daily["portcalls"].values.astype(float)
        recent_7d = vals[-7:]
        recent_avg = float(recent_7d.mean())
        vessel_count = int(round(recent_avg * 3))

        # Non-overlapping baseline
        if len(vals) >= 97:
            baseline_vals = vals[-97:-7]
        elif len(vals) > 7:
            baseline_vals = vals[:-7]
        else:
            baseline_vals = vals
        baseline_avg = float(baseline_vals.mean())

        ratio = recent_avg / (baseline_avg + 1e-6)
        delay_base = min(max((ratio - 0.8) / 0.6, 0.0), 1.0)
        recent_std = float(recent_7d.std()) if len(recent_7d) > 1 else 0.0
        variance_bonus = min(recent_std / (baseline_avg + 1.0), 0.2)
        vessel_delay_score = round(min(delay_base + variance_bonus, 1.0), 3)

        container_vals = daily["portcalls_container"].values.astype(float)
        container_avg = float(container_vals[-7:].mean()) if len(container_vals) >= 7 else 0.0
        mega_vessel_flag = container_avg >= 5.0 or port in MEGA_VESSEL_PORTS

        logger.info(
            f"[VesselAgent:fallback] port={port}  count={vessel_count}  "
            f"delay={vessel_delay_score}  mega={mega_vessel_flag}"
        )

        return {
            **state,
            "vessel_count":       vessel_count,
            "vessel_delay_score": vessel_delay_score,
            "mega_vessel_flag":   mega_vessel_flag,
            "anchor_count":       0,
            "moored_count":       0,
            "incoming_72h":       vessel_count,
            "queue_pressure":     0.0,
            "mega_vessel_count":  0,
        }
    except Exception as e:
        logger.error(f"[VesselAgent:fallback] error: {e}")
        return _defaults(state, port)
