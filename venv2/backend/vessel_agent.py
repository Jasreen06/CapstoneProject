"""
vessel_agent.py
===============
Vessel Arrival Risk Agent for DockWise AI.

Estimates vessel arrival risk signals from historical PortWatch data:
    vessel_count       — projected vessels arriving in next 72 hours
    vessel_delay_score — delay risk based on traffic vs baseline (0-1)
    mega_vessel_flag   — True if port handles ultra-large container vessels

Data source: portwatch_us_data.csv via data_cleaning module.
Uses 7-day recent window vs 90-day baseline to assess arrival pressure.
"""

from __future__ import annotations
import os
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from agents import RiskState

logger = logging.getLogger(__name__)

# US ports known to regularly handle mega-vessels (10,000+ TEU)
MEGA_VESSEL_PORTS = {
    "Los Angeles-Long Beach",
    "New York-New Jersey",
    "Savannah",
    "Houston",
    "Norfolk",
    "Charleston",
    "Oakland",
    "Seattle",
    "Tacoma",
    "Port of Virginia",
}


def run(state: "RiskState") -> "RiskState":
    """
    Vessel Arrival Risk Agent — estimates near-term arrival pressure.

    Uses historical PortWatch daily port-call data to compute:
      - vessel_count:       projected 72-hour arrivals (7-day avg × 3)
      - vessel_delay_score: delay risk score 0–1 (recent vs 90-day baseline)
      - mega_vessel_flag:   True if port handles ultra-large container vessels

    Reads:  state["port"]
    Writes: vessel_count, vessel_delay_score, mega_vessel_flag
    """
    from data_cleaning import load_and_clean, get_port_daily_series

    port      = state["port"]
    data_file = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
    logger.info(f"[VesselAgent] Assessing vessel arrival risk for '{port}'")

    try:
        df    = load_and_clean(data_file)
        daily = get_port_daily_series(df, port)

        if daily.empty or len(daily) < 7:
            logger.warning(f"[VesselAgent] Insufficient data for '{port}' — returning defaults")
            return {
                **state,
                "vessel_count":       0,
                "vessel_delay_score": 0.0,
                "mega_vessel_flag":   port in MEGA_VESSEL_PORTS,
            }

        vals = daily["portcalls"].values.astype(float)

        # ── vessel_count: 72-hour projected arrivals ────────────────────────
        recent_7d = vals[-7:]
        avg_daily = float(recent_7d.mean())
        vessel_count = int(round(avg_daily * 3))  # 3 days = 72 hours

        # ── vessel_delay_score: traffic pressure vs baseline ────────────────
        recent_avg   = float(recent_7d.mean())
        baseline_vals = vals[-90:] if len(vals) >= 90 else vals
        baseline_avg = float(baseline_vals.mean())

        # Ratio-based: 80% of baseline → 0.0 delay, 140% → 1.0 delay
        ratio      = recent_avg / (baseline_avg + 1e-6)
        delay_base = min(max((ratio - 0.8) / 0.6, 0.0), 1.0)

        # Variance bonus: high volatility = less predictable = higher risk
        recent_std     = float(recent_7d.std()) if len(recent_7d) > 1 else 0.0
        variance_bonus = min(recent_std / (baseline_avg + 1.0), 0.2)

        vessel_delay_score = round(min(delay_base + variance_bonus, 1.0), 3)

        # ── mega_vessel_flag: ultra-large vessel detection ──────────────────
        container_vals = daily["portcalls_container"].values.astype(float)
        container_avg  = float(container_vals[-7:].mean()) if len(container_vals) >= 7 else 0.0
        mega_vessel_flag = container_avg >= 5.0 or port in MEGA_VESSEL_PORTS

        logger.info(
            f"[VesselAgent] port={port}  count_72h={vessel_count}  "
            f"delay_score={vessel_delay_score}  mega={mega_vessel_flag}  "
            f"recent_avg={recent_avg:.1f}  baseline_avg={baseline_avg:.1f}  "
            f"ratio={ratio:.2f}  container_avg={container_avg:.1f}"
        )

        return {
            **state,
            "vessel_count":       vessel_count,
            "vessel_delay_score": vessel_delay_score,
            "mega_vessel_flag":   mega_vessel_flag,
        }

    except Exception as e:
        logger.error(f"[VesselAgent] Error: {e}")
        return {
            **state,
            "vessel_count":       0,
            "vessel_delay_score": 0.0,
            "mega_vessel_flag":   port in MEGA_VESSEL_PORTS,
        }