"""
save_predictions.py
===================
Step 1 of congestion score validation.

Runs Prophet on the current PortWatch data and saves predictions for the
next 7 days (the days we DON'T have data for yet). Once fresh PortWatch
data is pulled later, run `validate_predictions.py` to compare predicted
vs actual portcalls and congestion scores.

Usage:
    cd venv2/backend
    python save_predictions.py

Output:
    predictions/predictions_YYYYMMDD.csv
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
from forecasting import ProphetModel

# ── Config ────────────────────────────────────────────────────
DATA_FILE = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
OUTPUT_DIR = Path("predictions")
HORIZON = 7

# Top US ports to validate (high-traffic, reliable data)
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


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    logger.info(f"Loading data from {DATA_FILE}")
    df = load_and_clean(DATA_FILE)

    # Determine the last date in our data
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

        # Fit Prophet on ALL available data
        try:
            model = ProphetModel()
            model.fit(daily)
            forecast = model.predict(horizon=HORIZON)
        except Exception as e:
            logger.error(f"  {port}: Prophet failed — {e}")
            continue

        # Also compute the Prophet baseline stats for congestion scoring
        # (same approach as congestion_agent.py: fit on all-but-last, predict last)
        vals = daily["portcalls"].values.astype(float)
        current_val = float(vals[-1])

        # Fit Prophet for baseline (train on all except last day)
        try:
            from prophet import Prophet as _Prophet
            train = daily.iloc[:-1][["date", "portcalls"]].copy()
            train = train.rename(columns={"date": "ds", "portcalls": "y"})
            train["y"] = pd.to_numeric(train["y"], errors="coerce").fillna(0).clip(lower=0)
            mode = "multiplicative" if train["y"].min() > 0 else "additive"
            if mode == "multiplicative":
                train["y"] = train["y"].replace(0, 1e-6)

            m = _Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                seasonality_mode=mode,
                changepoint_prior_scale=0.05,
                uncertainty_samples=200,
            )
            m.fit(train)

            # Get baseline stats (used for std estimation in z-score)
            baseline_pred = m.predict(pd.DataFrame({"ds": [daily["date"].iloc[-1]]}))
            baseline_expected = float(max(baseline_pred["yhat"].iloc[0], 0))
            baseline_lower = float(max(baseline_pred["yhat_lower"].iloc[0], 0))
            baseline_upper = float(max(baseline_pred["yhat_upper"].iloc[0], 0))
            std_est = max((baseline_upper - baseline_lower) / (2 * 1.96), 1.0)

            current_congestion = compute_congestion_score(current_val, baseline_expected, std_est)
        except Exception:
            baseline_expected = float(vals[-90:].mean())
            std_est = float(vals[-90:].std()) if len(vals) >= 90 else 1.0
            current_congestion = compute_congestion_score(current_val, baseline_expected, std_est)

        # Save each forecast day
        for _, row in forecast.iterrows():
            predicted_portcalls = round(float(row["yhat"]), 1)
            predicted_lower = round(float(row["yhat_lower"]), 1)
            predicted_upper = round(float(row["yhat_upper"]), 1)

            # Predicted congestion score (using predicted value as "actual" against baseline)
            predicted_congestion = compute_congestion_score(predicted_portcalls, baseline_expected, std_est)

            results.append({
                "port": port,
                "prediction_made_on": last_date.date(),
                "predicted_date": pd.Timestamp(row["ds"]).date(),
                "predicted_portcalls": predicted_portcalls,
                "predicted_lower": predicted_lower,
                "predicted_upper": predicted_upper,
                "predicted_congestion_score": predicted_congestion,
                "baseline_expected": round(baseline_expected, 1),
                "baseline_std": round(std_est, 2),
                "current_portcalls": round(current_val, 1),
                "current_congestion_score": current_congestion,
            })

    if not results:
        logger.error("No predictions generated!")
        return

    # Save to CSV
    results_df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y%m%d")
    outfile = OUTPUT_DIR / f"predictions_{timestamp}.csv"
    results_df.to_csv(outfile, index=False)

    logger.info(f"\nSaved {len(results_df)} predictions to {outfile}")
    logger.info(f"\nSummary:")
    logger.info(f"  Ports: {results_df['port'].nunique()}")
    logger.info(f"  Date range: {results_df['predicted_date'].min()} → {results_df['predicted_date'].max()}")

    # Print a preview
    print("\n" + "=" * 80)
    print("PREDICTION SNAPSHOT (first 3 ports)")
    print("=" * 80)
    for port in results_df["port"].unique()[:3]:
        port_df = results_df[results_df["port"] == port]
        print(f"\n{port} (baseline expected: {port_df['baseline_expected'].iloc[0]} portcalls/day)")
        print(f"  Current: {port_df['current_portcalls'].iloc[0]} portcalls → congestion {port_df['current_congestion_score'].iloc[0]}")
        print(f"  {'Date':<14} {'Predicted':>10} {'Lower':>8} {'Upper':>8} {'Congestion':>12}")
        print(f"  {'─'*14} {'─'*10} {'─'*8} {'─'*8} {'─'*12}")
        for _, r in port_df.iterrows():
            print(f"  {r['predicted_date']}   {r['predicted_portcalls']:>8.1f} {r['predicted_lower']:>8.1f} {r['predicted_upper']:>8.1f} {r['predicted_congestion_score']:>10.1f}")

    print(f"\n✓ Predictions saved to: {outfile}")
    print(f"  Next step: pull fresh PortWatch data, then run validate_predictions.py")


if __name__ == "__main__":
    main()
