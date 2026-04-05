"""
congestion_agent.py
===================
Port Congestion Agent for DockWise AI.

Computes current congestion signals using a Prophet seasonal baseline
instead of a simple rolling mean. Prophet accounts for day-of-week and
yearly seasonality, giving a smarter "expected" value to compare against.

Outputs:
    congestion_score  — 0-100 z-score vs Prophet expected value
    congestion_ratio  — current portcalls / Prophet expected value
    trend_direction   — rising / stable / falling (last 7d vs prior 7d)
    seasonal_context  — peak season / off-peak / CNY / hurricane season
    prophet_expected  — what Prophet expected for today (for transparency)
"""

from __future__ import annotations
import os
import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from agents import RiskState

logger = logging.getLogger(__name__)

# ── Seasonal constants ─────────────────────────────────────────────────────────
PEAK_MONTHS      = {8, 9, 10}        # Aug–Oct: pre-Christmas peak season
CNY_MONTHS       = {1, 2}            # Jan–Feb: Chinese New Year vessel bunching
HURRICANE_MONTHS = {6, 7, 8, 9, 10, 11}  # Gulf/East Coast elevated risk

# Minimum days of history needed to fit Prophet reliably
MIN_PROPHET_DAYS = 90


def _fit_prophet_baseline(daily: pd.DataFrame) -> tuple[float, float, float] | None:
    """
    Fit Prophet on all history except the last day, then predict
    what today's portcalls should be based on seasonality.

    Returns (expected, lower, upper) or None if Prophet fails.
    """
    try:
        from prophet import Prophet

        # Train on everything except the last day
        train = daily.iloc[:-1][["date", "portcalls"]].copy()
        train = train.rename(columns={"date": "ds", "portcalls": "y"})
        train = train.dropna(subset=["ds", "y"])
        train["y"] = pd.to_numeric(train["y"], errors="coerce").fillna(0).clip(lower=0)

        if len(train) < MIN_PROPHET_DAYS:
            return None

        mode = "multiplicative" if train["y"].min() > 0 else "additive"
        if mode == "multiplicative":
            train["y"] = train["y"].replace(0, 1e-6)

        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode=mode,
            changepoint_prior_scale=0.05,
            uncertainty_samples=200,
        )
        m.fit(train)

        # Predict for the last day (today's date in the data)
        last_date = pd.DataFrame({"ds": [daily["date"].iloc[-1]]})
        fcst = m.predict(last_date)

        expected = float(max(fcst["yhat"].iloc[0], 0))
        lower    = float(max(fcst["yhat_lower"].iloc[0], 0))
        upper    = float(max(fcst["yhat_upper"].iloc[0], 0))

        logger.info(
            f"[CongestionAgent] Prophet baseline: "
            f"expected={expected:.1f}  lower={lower:.1f}  upper={upper:.1f}"
        )
        return expected, lower, upper

    except Exception as e:
        logger.warning(f"[CongestionAgent] Prophet baseline failed: {e}")
        return None


def run(state: "RiskState") -> "RiskState":
    """
    Compute current port congestion signals using Prophet as the baseline.

    Primary baseline: Prophet seasonal forecast (accounts for day-of-week
    and yearly seasonality — e.g. Mondays in October are naturally busier).

    Fallback: 90-day rolling mean (used if Prophet fails or data is sparse).

    Reads:  state["port"]
    Writes: congestion_score, congestion_ratio,
            trend_direction, seasonal_context, prophet_expected
    """
    from data_cleaning import load_and_clean, get_port_daily_series

    port      = state["port"]
    data_file = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
    logger.info(f"[CongestionAgent] Assessing congestion for '{port}'")

    try:
        df    = load_and_clean(data_file)
        daily = get_port_daily_series(df, port)

        if daily.empty:
            logger.warning(f"[CongestionAgent] No data found for '{port}'")
            return {
                **state,
                "congestion_score":   50.0,
                "congestion_ratio":   1.0,
                "trend_direction":    "stable",
                "seasonal_context":   "No data available",
                "prophet_expected":   None,
            }

        vals        = daily["portcalls"].values.astype(float)
        current_val = float(vals[-1])

        # ── Try Prophet baseline first ───────────────────────────────────────
        prophet_result = _fit_prophet_baseline(daily)
        baseline_label = "prophet"

        if prophet_result is not None:
            expected, lower, upper = prophet_result
            # Use Prophet's uncertainty interval width as std proxy
            std_est = max((upper - lower) / (2 * 1.96), 1.0)
            mean_baseline = expected
            prophet_expected = round(expected, 1)
        else:
            # ── Fallback: 90-day rolling mean ────────────────────────────────
            logger.info(f"[CongestionAgent] Falling back to 90-day rolling mean")
            baseline_label   = "rolling_mean"
            baseline         = vals[-90:] if len(vals) >= 90 else vals
            mean_baseline    = float(baseline.mean())
            std_est          = float(baseline.std()) if len(baseline) > 1 else 1.0
            prophet_expected = None

        # ── Congestion score (0–100) ─────────────────────────────────────────
        z = float(np.clip((current_val - mean_baseline) / (std_est or 1.0), -3, 3))
        congestion_score = round((z + 3) / 6 * 100, 1)

        # ── Congestion ratio ─────────────────────────────────────────────────
        congestion_ratio = round(current_val / mean_baseline, 3) if mean_baseline > 0 else 1.0

        # ── 7-day trend ──────────────────────────────────────────────────────
        last7  = vals[-7:].mean()    if len(vals) >= 7  else current_val
        prior7 = vals[-14:-7].mean() if len(vals) >= 14 else last7
        diff   = float(last7 - prior7)
        trend  = "rising" if diff > 2 else ("falling" if diff < -2 else "stable")

        # ── Seasonal context ─────────────────────────────────────────────────
        last_date = pd.Timestamp(daily["date"].iloc[-1])
        month     = last_date.month

        if month in PEAK_MONTHS:
            seasonal_context = "Peak season (Aug–Oct) — pre-Christmas imports elevated"
        elif month in CNY_MONTHS:
            seasonal_context = "Chinese New Year period — post-CNY vessel bunching likely"
        elif month in HURRICANE_MONTHS:
            seasonal_context = "Hurricane season — Gulf/East Coast weather risk elevated"
        else:
            seasonal_context = "Off-peak period — baseline conditions"

        logger.info(
            f"[CongestionAgent] baseline={baseline_label}  "
            f"current={current_val:.1f}  expected={mean_baseline:.1f}  "
            f"score={congestion_score}  ratio={congestion_ratio}  trend={trend}"
        )

        return {
            **state,
            "congestion_score":  congestion_score,
            "congestion_ratio":  congestion_ratio,
            "trend_direction":   trend,
            "seasonal_context":  seasonal_context,
            "prophet_expected":  prophet_expected,
        }

    except Exception as e:
        logger.error(f"[CongestionAgent] Error: {e}")
        return {
            **state,
            "congestion_score":  50.0,
            "congestion_ratio":  1.0,
            "trend_direction":   "stable",
            "seasonal_context":  "Unable to compute — data error",
            "prophet_expected":  None,
        }