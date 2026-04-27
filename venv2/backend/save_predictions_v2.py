"""
save_predictions_v2.py
======================
Improved congestion prediction with three fixes:

Fix 1: Use historical residual std (not prediction interval width) for z-score.
        Prophet's interval is too narrow → everything maps to MEDIUM.
Fix 2: Add 3-day momentum adjustment to Prophet point forecast.
Fix 3: Ensemble Prophet + XGBoost for more variance in predictions.

Usage:
    cd venv2/backend
    python save_predictions_v2.py

Output:
    predictions/predictions_v2_YYYYMMDD.csv
"""

from __future__ import annotations
import os
import logging
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from data_cleaning import load_and_clean, get_port_daily_series
from forecasting import ProphetModel, XGBoostModel

# ── Config ────────────────────────────────────────────────────
DATA_FILE = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
OUTPUT_DIR = Path("predictions")
HORIZON = 7

TOP_PORTS = [
    "Los Angeles-Long Beach",
    "New York-New Jersey",
    "Savannah",
    "Houston",
    "Seattle",
    "Charleston",
    "Norfolk",
    "Oakland",
    "Baltimore",
    "New Orleans",
    "Corpus Christi",
    "Tampa",
    "Philadelphia",
    "Miami",
    "Jacksonville",
    "Tacoma",
    "Portland, OR",
    "Honolulu",
    "Anchorage (Alaska)",
]


def compute_congestion_score(actual: float, expected: float, std_est: float) -> float:
    """Same z-score formula used in congestion_agent.py."""
    z = float(np.clip((actual - expected) / (std_est or 1.0), -3, 3))
    return round((z + 3) / 6 * 100, 1)


def compute_residual_std(daily: pd.DataFrame) -> tuple[float, float]:
    """
    FIX 1: Compute Prophet's historical residual std.

    Fit Prophet on first 80% of data, predict last 20%,
    measure how much actuals deviate from predictions.
    This gives a realistic std for z-score computation.

    Also returns the mean baseline (Prophet's average prediction).
    """
    from prophet import Prophet

    n = len(daily)
    split = int(n * 0.8)
    train = daily.iloc[:split][["date", "portcalls"]].copy()
    test = daily.iloc[split:][["date", "portcalls"]].copy()

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

    # Predict on test dates
    test_dates = pd.DataFrame({"ds": test["date"].values})
    fcst = m.predict(test_dates)

    actuals = test["portcalls"].values.astype(float)
    predicted = np.maximum(fcst["yhat"].values, 0)
    residuals = actuals - predicted

    residual_std = float(np.std(residuals))
    mean_baseline = float(np.mean(predicted))

    return max(residual_std, 1.0), mean_baseline


def compute_momentum(vals: np.ndarray, window: int = 3) -> float:
    """
    FIX 2: Compute short-term momentum.

    Returns the average daily change over the last `window` days.
    Positive = traffic rising, negative = falling.
    """
    if len(vals) < window + 1:
        return 0.0
    recent = vals[-(window + 1):]
    daily_changes = np.diff(recent)
    return float(np.mean(daily_changes))


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    logger.info(f"Loading data from {DATA_FILE}")
    df = load_and_clean(DATA_FILE)

    last_date = df["date"].max()
    logger.info(f"Last date in data: {last_date.date()}")
    logger.info(f"Predicting next {HORIZON} days: {(last_date + pd.Timedelta(days=1)).date()} → {(last_date + pd.Timedelta(days=HORIZON)).date()}")

    results = []

    for port in TOP_PORTS:
        daily = get_port_daily_series(df, port)
        if daily.empty or len(daily) < 90:
            logger.warning(f"  {port}: insufficient data ({len(daily)} days), skipping")
            continue

        logger.info(f"  {port}: {len(daily)} days of history")
        vals = daily["portcalls"].values.astype(float)
        current_val = float(vals[-1])

        # ── FIX 1: Historical residual std ────────────────────
        try:
            residual_std, _ = compute_residual_std(daily)
        except Exception as e:
            logger.warning(f"  {port}: residual std failed ({e}), using rolling std")
            residual_std = float(vals[-90:].std()) if len(vals) >= 90 else 1.0

        # ── FIX 2: Momentum ──────────────────────────────────
        momentum = compute_momentum(vals)

        # ── Prophet forecast ─────────────────────────────────
        try:
            prophet_model = ProphetModel()
            prophet_model.fit(daily)
            prophet_forecast = prophet_model.predict(horizon=HORIZON)
        except Exception as e:
            logger.error(f"  {port}: Prophet failed — {e}")
            continue

        # ── FIX 3: XGBoost forecast (ensemble) ───────────────
        try:
            xgb_model = XGBoostModel()
            xgb_model.fit(daily)
            xgb_forecast = xgb_model.predict(horizon=HORIZON)
            has_xgb = True
        except Exception as e:
            logger.warning(f"  {port}: XGBoost failed ({e}), using Prophet only")
            has_xgb = False

        # ── Prophet baseline for current day ─────────────────
        try:
            from prophet import Prophet as _Prophet
            train = daily.iloc[:-1][["date", "portcalls"]].copy()
            train = train.rename(columns={"date": "ds", "portcalls": "y"})
            train["y"] = pd.to_numeric(train["y"], errors="coerce").fillna(0).clip(lower=0)
            mode = "multiplicative" if train["y"].min() > 0 else "additive"
            if mode == "multiplicative":
                train["y"] = train["y"].replace(0, 1e-6)

            m = _Prophet(
                yearly_seasonality=True, weekly_seasonality=True,
                daily_seasonality=False, seasonality_mode=mode,
                changepoint_prior_scale=0.05, uncertainty_samples=200,
            )
            m.fit(train)
            baseline_pred = m.predict(pd.DataFrame({"ds": [daily["date"].iloc[-1]]}))
            baseline_expected = float(max(baseline_pred["yhat"].iloc[0], 0))
        except Exception:
            baseline_expected = float(vals[-90:].mean())

        current_congestion = compute_congestion_score(current_val, baseline_expected, residual_std)

        # ── Build predictions per day ────────────────────────
        for i, (_, row) in enumerate(prophet_forecast.iterrows()):
            prophet_pred = float(row["yhat"])

            # FIX 3: Ensemble average (Prophet 60% + XGBoost 40%)
            if has_xgb:
                xgb_pred = float(xgb_forecast.iloc[i]["yhat"])
                ensemble_pred = 0.6 * prophet_pred + 0.4 * xgb_pred
            else:
                xgb_pred = None
                ensemble_pred = prophet_pred

            # FIX 2: Add decaying momentum (stronger for day 1, weaker for day 7)
            decay = max(0, 1.0 - i * 0.15)  # 1.0, 0.85, 0.70, ..., 0.1
            adjusted_pred = ensemble_pred + momentum * decay

            # Keep non-negative
            adjusted_pred = max(adjusted_pred, 0)

            # Compute congestion score using residual_std (FIX 1)
            predicted_congestion = compute_congestion_score(
                adjusted_pred, baseline_expected, residual_std
            )

            # Prediction interval using residual std
            pred_lower = max(adjusted_pred - 1.96 * residual_std, 0)
            pred_upper = adjusted_pred + 1.96 * residual_std

            results.append({
                "port": port,
                "prediction_made_on": last_date.date(),
                "predicted_date": pd.Timestamp(row["ds"]).date(),
                "prophet_pred": round(prophet_pred, 1),
                "xgb_pred": round(xgb_pred, 1) if xgb_pred is not None else None,
                "ensemble_pred": round(ensemble_pred, 1),
                "momentum_adj": round(momentum * decay, 2),
                "predicted_portcalls": round(adjusted_pred, 1),
                "predicted_lower": round(pred_lower, 1),
                "predicted_upper": round(pred_upper, 1),
                "predicted_congestion_score": predicted_congestion,
                "baseline_expected": round(baseline_expected, 1),
                "baseline_std": round(residual_std, 2),
                "residual_std_method": "historical",
                "current_portcalls": round(current_val, 1),
                "current_congestion_score": current_congestion,
            })

    if not results:
        logger.error("No predictions generated!")
        return

    results_df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y%m%d")
    outfile = OUTPUT_DIR / f"predictions_v2_{timestamp}.csv"
    results_df.to_csv(outfile, index=False)

    logger.info(f"\nSaved {len(results_df)} predictions to {outfile}")

    # Print preview
    print("\n" + "=" * 80)
    print("V2 PREDICTION SNAPSHOT (first 3 ports)")
    print("=" * 80)
    for port in results_df["port"].unique()[:3]:
        port_df = results_df[results_df["port"] == port]
        print(f"\n{port}")
        print(f"  Baseline: {port_df['baseline_expected'].iloc[0]} | Residual std: {port_df['baseline_std'].iloc[0]} | Current: {port_df['current_portcalls'].iloc[0]}")
        print(f"  {'Date':<14} {'Prophet':>8} {'XGB':>8} {'Ensemble':>9} {'Mom.Adj':>8} {'Final':>8} {'Score':>8}")
        print(f"  {'─'*14} {'─'*8} {'─'*8} {'─'*9} {'─'*8} {'─'*8} {'─'*8}")
        for _, r in port_df.iterrows():
            xgb_str = f"{r['xgb_pred']:>8.1f}" if r['xgb_pred'] is not None else "     N/A"
            print(f"  {r['predicted_date']}   {r['prophet_pred']:>6.1f} {xgb_str} {r['ensemble_pred']:>8.1f} {r['momentum_adj']:>+7.2f} {r['predicted_portcalls']:>7.1f} {r['predicted_congestion_score']:>7.1f}")

    print(f"\n✓ V2 predictions saved to: {outfile}")
    print(f"  Improvements: historical residual std + momentum + Prophet/XGBoost ensemble")


if __name__ == "__main__":
    main()
