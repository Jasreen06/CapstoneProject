"""
congestion_agent.py
===================
Port Congestion Agent for DockWise AI.

Computes current congestion signals using a Prophet seasonal baseline
with V2 improvements:
  - Historical residual std (not prediction interval width) for z-score
  - Prophet + XGBoost ensemble for baseline comparison
  - 3-day momentum adjustment

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


def _compute_residual_std(daily: pd.DataFrame) -> float | None:
    """
    V2 FIX 1: Compute historical residual std.

    Fit Prophet on first 80% of data, predict last 20%,
    measure how much actuals deviate from predictions.
    This gives a realistic std for z-score computation.
    """
    try:
        from prophet import Prophet

        n = len(daily)
        split = int(n * 0.8)
        if split < MIN_PROPHET_DAYS:
            return None

        train = daily.iloc[:split][["date", "portcalls"]].copy()
        train = train.rename(columns={"date": "ds", "portcalls": "y"})
        train["y"] = pd.to_numeric(train["y"], errors="coerce").fillna(0).clip(lower=0)

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

        # Predict on validation portion
        val_dates = pd.DataFrame({"ds": daily.iloc[split:]["date"].values})
        val_pred = m.predict(val_dates)

        actuals = daily.iloc[split:]["portcalls"].values.astype(float)
        predicted = np.maximum(val_pred["yhat"].values, 0)
        residuals = actuals - predicted

        residual_std = float(np.std(residuals))
        logger.info(f"[CongestionAgent] Residual std: {residual_std:.3f}")
        return max(residual_std, 1.0)

    except Exception as e:
        logger.warning(f"[CongestionAgent] Residual std computation failed: {e}")
        return None


def _compute_xgb_baseline(daily: pd.DataFrame) -> float | None:
    """
    V2 FIX 3: XGBoost prediction for ensemble.

    Fits XGBoost on all data except last day, predicts last day.
    Returns predicted portcalls or None if it fails.
    """
    try:
        from forecasting import XGBoostModel

        train = daily.iloc[:-1].copy()
        if len(train) < 30:
            return None

        model = XGBoostModel()
        model.fit(train)
        fcst = model.predict(horizon=1)
        xgb_pred = float(max(fcst["yhat"].iloc[0], 0))

        logger.info(f"[CongestionAgent] XGBoost baseline: {xgb_pred:.1f}")
        return xgb_pred

    except Exception as e:
        logger.warning(f"[CongestionAgent] XGBoost baseline failed: {e}")
        return None


def _compute_momentum(vals: np.ndarray, window: int = 3) -> float:
    """
    V2 FIX 2: Compute short-term momentum.

    Returns the average daily change over the last `window` days.
    Positive = traffic rising, negative = falling.
    """
    if len(vals) < window + 1:
        return 0.0
    recent = vals[-(window + 1):]
    daily_changes = np.diff(recent)
    return float(np.mean(daily_changes))


def run(state: "RiskState") -> "RiskState":
    """
    Compute current port congestion signals using V2 ensemble approach.

    V2 improvements over original:
      1. Historical residual std (realistic variance for z-score)
      2. Prophet + XGBoost ensemble (60/40 weight) for baseline
      3. 3-day momentum adjustment

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
            prophet_expected = round(expected, 1)

            # ── V2 FIX 3: Ensemble with XGBoost ─────────────────────────────
            xgb_pred = _compute_xgb_baseline(daily)
            if xgb_pred is not None:
                # Ensemble: Prophet 60% + XGBoost 40%
                mean_baseline = 0.6 * expected + 0.4 * xgb_pred
                baseline_label = "ensemble(prophet+xgb)"
                logger.info(
                    f"[CongestionAgent] Ensemble baseline: "
                    f"prophet={expected:.1f} xgb={xgb_pred:.1f} → {mean_baseline:.1f}"
                )
            else:
                mean_baseline = expected

            # ── V2 FIX 1: Historical residual std ────────────────────────────
            residual_std = _compute_residual_std(daily)
            if residual_std is not None:
                std_est = residual_std
            else:
                # Fallback to prediction interval width
                std_est = max((upper - lower) / (2 * 1.96), 1.0)

        else:
            # ── Fallback: 90-day rolling mean ────────────────────────────────
            logger.info(f"[CongestionAgent] Falling back to 90-day rolling mean")
            baseline_label   = "rolling_mean"
            baseline         = vals[-90:] if len(vals) >= 90 else vals
            mean_baseline    = float(baseline.mean())
            std_est          = float(baseline.std()) if len(baseline) > 1 else 1.0
            prophet_expected = None

        # ── V2 FIX 2: Momentum adjustment ───────────────────────────────────
        momentum = _compute_momentum(vals)
        # Adjust current value by momentum (captures recent trend direction)
        adjusted_val = current_val + momentum
        adjusted_val = max(adjusted_val, 0)

        logger.info(
            f"[CongestionAgent] Momentum: {momentum:+.2f} | "
            f"current={current_val:.1f} → adjusted={adjusted_val:.1f}"
        )

        # ── Congestion score (0–100) ─────────────────────────────────────────
        z = float(np.clip((adjusted_val - mean_baseline) / (std_est or 1.0), -3, 3))
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
            f"current={current_val:.1f}  expected={mean_baseline:.1f}  std={std_est:.2f}  "
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
