"""
backtest.py
===========
Holdout backtest: train on data up to a cutoff date, predict next 7 days,
compare against actuals. Tests both v1 (Prophet only) and v2 (ensemble +
momentum + historical residual std) approaches side by side.

Usage:
    cd venv2/backend
    python backtest.py

Output:
    Prints v1 vs v2 comparison table
"""

from __future__ import annotations
import os
import logging
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from data_cleaning import load_and_clean, get_port_daily_series
from forecasting import ProphetModel, XGBoostModel

DATA_FILE = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
HORIZON = 7
CUTOFF = "2026-04-03"

TOP_PORTS = [
    "Los Angeles-Long Beach", "New York-New Jersey", "Savannah", "Houston",
    "Seattle", "Charleston", "Norfolk", "Oakland", "Baltimore", "New Orleans",
    "Corpus Christi", "Tampa", "Philadelphia", "Miami", "Jacksonville",
    "Tacoma", "Portland, OR", "Honolulu", "Anchorage (Alaska)",
]


def compute_congestion_score(actual, expected, std_est):
    z = float(np.clip((actual - expected) / (std_est or 1.0), -3, 3))
    return round((z + 3) / 6 * 100, 1)


def score_to_tier(score):
    if score >= 67: return "HIGH"
    elif score >= 33: return "MEDIUM"
    else: return "LOW"


def main():
    logger.info(f"Loading data from {DATA_FILE}")
    df = load_and_clean(DATA_FILE)
    cutoff_date = pd.Timestamp(CUTOFF)

    logger.info(f"Cutoff: {CUTOFF} | Predicting {HORIZON} days after")

    v1_results = []
    v2_results = []

    for port in TOP_PORTS:
        full_daily = get_port_daily_series(df, port)
        if full_daily.empty or len(full_daily) < 90:
            continue

        # Split: train on data up to cutoff, test on days after
        train = full_daily[full_daily["date"] <= cutoff_date].copy()
        test = full_daily[
            (full_daily["date"] > cutoff_date) &
            (full_daily["date"] <= cutoff_date + pd.Timedelta(days=HORIZON))
        ].copy()

        if train.empty or test.empty:
            continue

        vals = train["portcalls"].values.astype(float)

        # ── Prophet baseline ─────────────────────────────────
        try:
            from prophet import Prophet
            train_p = train.iloc[:-1][["date", "portcalls"]].rename(columns={"date": "ds", "portcalls": "y"})
            train_p["y"] = pd.to_numeric(train_p["y"], errors="coerce").fillna(0).clip(lower=0)
            mode = "multiplicative" if train_p["y"].min() > 0 else "additive"
            if mode == "multiplicative":
                train_p["y"] = train_p["y"].replace(0, 1e-6)

            m = Prophet(
                yearly_seasonality=True, weekly_seasonality=True,
                daily_seasonality=False, seasonality_mode=mode,
                changepoint_prior_scale=0.05, uncertainty_samples=200,
            )
            m.fit(train_p)
            bp = m.predict(pd.DataFrame({"ds": [train["date"].iloc[-1]]}))
            baseline_expected = float(max(bp["yhat"].iloc[0], 0))
            baseline_lower = float(max(bp["yhat_lower"].iloc[0], 0))
            baseline_upper = float(max(bp["yhat_upper"].iloc[0], 0))
        except Exception as e:
            logger.warning(f"  {port}: baseline failed — {e}")
            continue

        # ── V1: Original approach (interval-based std) ───────
        v1_std = max((baseline_upper - baseline_lower) / (2 * 1.96), 1.0)

        # ── V2: Historical residual std ──────────────────────
        try:
            n = len(train)
            split = int(n * 0.8)
            tr80 = train.iloc[:split][["date", "portcalls"]].rename(columns={"date": "ds", "portcalls": "y"})
            tr80["y"] = pd.to_numeric(tr80["y"], errors="coerce").fillna(0).clip(lower=0)
            md = "multiplicative" if tr80["y"].min() > 0 else "additive"
            if md == "multiplicative":
                tr80["y"] = tr80["y"].replace(0, 1e-6)
            m2 = Prophet(
                yearly_seasonality=True, weekly_seasonality=True,
                daily_seasonality=False, seasonality_mode=md,
                changepoint_prior_scale=0.05, uncertainty_samples=200,
            )
            m2.fit(tr80)
            val_dates = pd.DataFrame({"ds": train.iloc[split:]["date"].values})
            val_pred = m2.predict(val_dates)
            residuals = train.iloc[split:]["portcalls"].values.astype(float) - np.maximum(val_pred["yhat"].values, 0)
            v2_std = max(float(np.std(residuals)), 1.0)
        except Exception:
            v2_std = v1_std

        # ── V2: Momentum ─────────────────────────────────────
        momentum = 0.0
        if len(vals) >= 4:
            recent = vals[-4:]
            momentum = float(np.mean(np.diff(recent)))

        # ── Prophet forecast ─────────────────────────────────
        try:
            prophet_model = ProphetModel()
            prophet_model.fit(train)
            prophet_fcst = prophet_model.predict(horizon=HORIZON)
        except Exception:
            continue

        # ── XGBoost forecast ─────────────────────────────────
        try:
            xgb_model = XGBoostModel()
            xgb_model.fit(train)
            xgb_fcst = xgb_model.predict(horizon=HORIZON)
            has_xgb = True
        except Exception:
            has_xgb = False

        # ── Compare per day ──────────────────────────────────
        for i, (_, row) in enumerate(prophet_fcst.iterrows()):
            pred_date = pd.Timestamp(row["ds"])
            actual_row = test[test["date"] == pred_date]
            if actual_row.empty:
                continue

            actual_pc = float(actual_row["portcalls"].iloc[0])

            # V1 prediction
            v1_pred = float(row["yhat"])
            v1_cong = compute_congestion_score(v1_pred, baseline_expected, v1_std)
            actual_cong_v1 = compute_congestion_score(actual_pc, baseline_expected, v1_std)

            v1_results.append({
                "port": port, "date": pred_date.date(),
                "predicted_pc": round(v1_pred, 1), "actual_pc": round(actual_pc, 1),
                "pred_cong": v1_cong, "actual_cong": actual_cong_v1,
                "pred_tier": score_to_tier(v1_cong), "actual_tier": score_to_tier(actual_cong_v1),
            })

            # V2 prediction (ensemble + momentum)
            if has_xgb:
                xgb_pred = float(xgb_fcst.iloc[i]["yhat"])
                ensemble = 0.6 * v1_pred + 0.4 * xgb_pred
            else:
                ensemble = v1_pred

            decay = max(0, 1.0 - i * 0.15)
            v2_pred = max(ensemble + momentum * decay, 0)
            v2_cong = compute_congestion_score(v2_pred, baseline_expected, v2_std)
            actual_cong_v2 = compute_congestion_score(actual_pc, baseline_expected, v2_std)

            v2_results.append({
                "port": port, "date": pred_date.date(),
                "predicted_pc": round(v2_pred, 1), "actual_pc": round(actual_pc, 1),
                "pred_cong": v2_cong, "actual_cong": actual_cong_v2,
                "pred_tier": score_to_tier(v2_cong), "actual_tier": score_to_tier(actual_cong_v2),
            })

    # ── Compare results ──────────────────────────────────────
    v1_df = pd.DataFrame(v1_results)
    v2_df = pd.DataFrame(v2_results)

    print("\n" + "=" * 80)
    print("BACKTEST: V1 (original) vs V2 (improved)")
    print(f"Cutoff: {CUTOFF} | Forecast horizon: {HORIZON} days")
    print("=" * 80)

    for label, rdf in [("V1 (Prophet, interval std)", v1_df), ("V2 (Ensemble, residual std, momentum)", v2_df)]:
        rdf["tier_correct"] = rdf["pred_tier"] == rdf["actual_tier"]
        rdf["pc_abs_error"] = (rdf["predicted_pc"] - rdf["actual_pc"]).abs()
        rdf["pc_pct_error"] = rdf.apply(
            lambda r: abs(r["predicted_pc"] - r["actual_pc"]) / r["actual_pc"] * 100
            if r["actual_pc"] > 0 else 0, axis=1
        )
        rdf["cong_abs_error"] = (rdf["pred_cong"] - rdf["actual_cong"]).abs()

        print(f"\n── {label} ──")
        print(f"  Portcall MAE:           {rdf['pc_abs_error'].mean():.1f}")
        print(f"  Portcall MAPE:          {rdf['pc_pct_error'].mean():.1f}%")
        print(f"  Congestion Score MAE:   {rdf['cong_abs_error'].mean():.1f} / 100")
        print(f"  Tier Accuracy:          {rdf['tier_correct'].mean() * 100:.1f}%")

        # Tier distribution
        print(f"  Predicted tiers: {rdf['pred_tier'].value_counts().to_dict()}")
        print(f"  Actual tiers:    {rdf['actual_tier'].value_counts().to_dict()}")

    # Per-port comparison
    print(f"\n── Per-Port Tier Accuracy ──")
    print(f"  {'Port':<25} {'V1 Tier%':>10} {'V2 Tier%':>10} {'Winner':>8}")
    print(f"  {'─'*25} {'─'*10} {'─'*10} {'─'*8}")

    for port in sorted(v1_df["port"].unique()):
        p1 = v1_df[v1_df["port"] == port]
        p2 = v2_df[v2_df["port"] == port]
        t1 = (p1["pred_tier"] == p1["actual_tier"]).mean() * 100
        t2 = (p2["pred_tier"] == p2["actual_tier"]).mean() * 100
        winner = "V2" if t2 > t1 else ("V1" if t1 > t2 else "TIE")
        print(f"  {port:<25} {t1:>9.1f}% {t2:>9.1f}% {winner:>8}")

    # Summary
    v1_tier = (v1_df["pred_tier"] == v1_df["actual_tier"]).mean() * 100
    v2_tier = (v2_df["pred_tier"] == v2_df["actual_tier"]).mean() * 100
    improvement = v2_tier - v1_tier

    print(f"\n{'=' * 80}")
    print(f"  TIER ACCURACY: V1 = {v1_tier:.1f}%  →  V2 = {v2_tier:.1f}%  (Δ = {improvement:+.1f}%)")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
