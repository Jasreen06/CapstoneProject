"""
backtest_v3.py
==============
V3 improvements over V2:
  1. Per-port adaptive thresholds (learned from historical score distribution)
  2. Multi-window walk-forward (4 windows, not just one)
  3. Chokepoint features fed into XGBoost
  4. ARIMA added to ensemble (Prophet 50% + XGBoost 30% + ARIMA 20%)
  5. Day-of-week adjustment

Compares V1 vs V2 vs V3 side by side.

Usage:
    cd venv2/backend
    python backtest_v3.py
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

from data_cleaning import load_and_clean, get_port_daily_series, load_and_clean_chokepoints
from forecasting import ProphetModel, XGBoostModel, ARIMAModel

DATA_FILE = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
CHOKEPOINT_FILE = os.environ.get("CHOKEPOINT_FILE", "chokepoint_data.csv")
HORIZON = 7

# Walk-forward windows: each cutoff creates a 7-day test window
CUTOFFS = ["2026-03-13", "2026-03-20", "2026-03-27", "2026-04-03"]

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
    if score >= 67:
        return "HIGH"
    elif score >= 33:
        return "MEDIUM"
    else:
        return "LOW"


def score_to_tier_adaptive(score, low_thresh, high_thresh):
    """Per-port adaptive thresholds."""
    if score >= high_thresh:
        return "HIGH"
    elif score >= low_thresh:
        return "MEDIUM"
    else:
        return "LOW"


def learn_adaptive_thresholds(daily: pd.DataFrame, baseline_expected: float, std_est: float):
    """
    FIX 1: Learn per-port thresholds from historical congestion score distribution.

    Instead of fixed 33/67, use the 25th and 75th percentile of historical
    congestion scores. This means a volatile port (New Orleans) gets wider
    thresholds, while a stable port (Houston) gets tighter ones.
    """
    vals = daily["portcalls"].values.astype(float)
    # Compute historical congestion scores for last 90 days
    scores = []
    for v in vals[-90:]:
        s = compute_congestion_score(v, baseline_expected, std_est)
        scores.append(s)

    scores = np.array(scores)
    # Use 30th percentile as LOW/MED boundary, 70th as MED/HIGH boundary
    low_thresh = float(np.percentile(scores, 30))
    high_thresh = float(np.percentile(scores, 70))

    # Clamp to reasonable range
    low_thresh = max(20, min(45, low_thresh))
    high_thresh = max(55, min(80, high_thresh))

    return low_thresh, high_thresh


def get_dow_adjustment(daily: pd.DataFrame) -> dict[int, float]:
    """
    FIX 5: Day-of-week adjustment factors.

    Compute average portcalls per day-of-week, return ratio vs overall mean.
    Monday traffic of 80% of average → factor 0.8.
    """
    df = daily.copy()
    df["dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    overall_mean = df["portcalls"].mean()
    if overall_mean == 0:
        return {i: 1.0 for i in range(7)}

    dow_means = df.groupby("dow")["portcalls"].mean()
    factors = {}
    for dow in range(7):
        if dow in dow_means.index and dow_means[dow] > 0:
            factors[dow] = float(dow_means[dow] / overall_mean)
        else:
            factors[dow] = 1.0
    return factors


def fit_prophet_baseline(daily, cutoff_date):
    """Fit Prophet baseline on data up to cutoff."""
    from prophet import Prophet

    train = daily[daily["date"] <= cutoff_date].iloc[:-1][["date", "portcalls"]].copy()
    train = train.rename(columns={"date": "ds", "portcalls": "y"})
    train["y"] = pd.to_numeric(train["y"], errors="coerce").fillna(0).clip(lower=0)

    mode = "multiplicative" if train["y"].min() > 0 else "additive"
    if mode == "multiplicative":
        train["y"] = train["y"].replace(0, 1e-6)

    m = Prophet(
        yearly_seasonality=True, weekly_seasonality=True,
        daily_seasonality=False, seasonality_mode=mode,
        changepoint_prior_scale=0.05, uncertainty_samples=200,
    )
    m.fit(train)

    last_train_date = daily[daily["date"] <= cutoff_date]["date"].iloc[-1]
    bp = m.predict(pd.DataFrame({"ds": [last_train_date]}))
    expected = float(max(bp["yhat"].iloc[0], 0))
    lower = float(max(bp["yhat_lower"].iloc[0], 0))
    upper = float(max(bp["yhat_upper"].iloc[0], 0))

    return expected, lower, upper


def compute_residual_std(daily, cutoff_date):
    """Historical residual std from 80/20 split of training data."""
    from prophet import Prophet

    train = daily[daily["date"] <= cutoff_date].copy()
    n = len(train)
    split = int(n * 0.8)

    tr80 = train.iloc[:split][["date", "portcalls"]].rename(columns={"date": "ds", "portcalls": "y"})
    tr80["y"] = pd.to_numeric(tr80["y"], errors="coerce").fillna(0).clip(lower=0)

    mode = "multiplicative" if tr80["y"].min() > 0 else "additive"
    if mode == "multiplicative":
        tr80["y"] = tr80["y"].replace(0, 1e-6)

    m = Prophet(
        yearly_seasonality=True, weekly_seasonality=True,
        daily_seasonality=False, seasonality_mode=mode,
        changepoint_prior_scale=0.05, uncertainty_samples=200,
    )
    m.fit(tr80)

    val_dates = pd.DataFrame({"ds": train.iloc[split:]["date"].values})
    val_pred = m.predict(val_dates)
    residuals = train.iloc[split:]["portcalls"].values.astype(float) - np.maximum(val_pred["yhat"].values, 0)

    return max(float(np.std(residuals)), 1.0)


def main():
    logger.info(f"Loading data from {DATA_FILE}")
    df = load_and_clean(DATA_FILE)

    # Load chokepoint data for XGBoost
    try:
        chk_df = load_and_clean_chokepoints(CHOKEPOINT_FILE)
        chokepoints = sorted(chk_df["portname"].unique())
        logger.info(f"Loaded {len(chokepoints)} chokepoints for XGBoost features")
    except Exception as e:
        logger.warning(f"Chokepoint data not available: {e}")
        chk_df = None

    all_v1 = []
    all_v2 = []
    all_v3 = []

    for cutoff_str in CUTOFFS:
        cutoff_date = pd.Timestamp(cutoff_str)
        logger.info(f"\n{'='*60}")
        logger.info(f"Window: cutoff={cutoff_str} → predict {cutoff_str} + 1..7")
        logger.info(f"{'='*60}")

        for port in TOP_PORTS:
            full_daily = get_port_daily_series(df, port)
            if full_daily.empty or len(full_daily) < 90:
                continue

            train = full_daily[full_daily["date"] <= cutoff_date].copy()
            test = full_daily[
                (full_daily["date"] > cutoff_date) &
                (full_daily["date"] <= cutoff_date + pd.Timedelta(days=HORIZON))
            ].copy()

            if len(train) < 90 or test.empty:
                continue

            vals = train["portcalls"].values.astype(float)

            # ── Baseline ─────────────────────────────────────
            try:
                baseline_expected, baseline_lower, baseline_upper = fit_prophet_baseline(full_daily, cutoff_date)
            except Exception:
                continue

            # ── V1 std (interval-based) ──────────────────────
            v1_std = max((baseline_upper - baseline_lower) / (2 * 1.96), 1.0)

            # ── V2 std (historical residual) ─────────────────
            try:
                v2_std = compute_residual_std(full_daily, cutoff_date)
            except Exception:
                v2_std = v1_std

            # V3 uses same residual std as V2
            v3_std = v2_std

            # ── V2/V3 Momentum ───────────────────────────────
            momentum = 0.0
            if len(vals) >= 4:
                momentum = float(np.mean(np.diff(vals[-4:])))

            # ── V3 FIX 1: Adaptive thresholds ────────────────
            try:
                low_thresh, high_thresh = learn_adaptive_thresholds(train, baseline_expected, v3_std)
            except Exception:
                low_thresh, high_thresh = 33.0, 67.0

            # ── V3 FIX 5: Day-of-week adjustment ────────────
            dow_factors = get_dow_adjustment(train)

            # ── Prophet forecast ─────────────────────────────
            try:
                prophet_model = ProphetModel()
                prophet_model.fit(train)
                prophet_fcst = prophet_model.predict(horizon=HORIZON)
            except Exception:
                continue

            # ── XGBoost forecast (V3 FIX 3: with chokepoints) ─
            try:
                xgb_model = XGBoostModel()
                # Prepare chokepoint data for XGBoost
                chk_data = {}
                if chk_df is not None:
                    for cp in chk_df["portname"].unique():
                        cp_daily = chk_df[chk_df["portname"] == cp][["date", "n_total"]].copy()
                        cp_daily = cp_daily[cp_daily["date"] <= cutoff_date]
                        if not cp_daily.empty:
                            chk_data[cp] = cp_daily

                if chk_data:
                    xgb_model.fit(train, chokepoint_data=chk_data)
                else:
                    xgb_model.fit(train)
                xgb_fcst = xgb_model.predict(horizon=HORIZON)
                has_xgb = True
            except Exception:
                has_xgb = False

            # ── V3 FIX 4: ARIMA forecast ─────────────────────
            try:
                arima_model = ARIMAModel()
                arima_model.fit(train)
                arima_fcst = arima_model.predict(horizon=HORIZON)
                has_arima = True
            except Exception:
                has_arima = False

            # ── Compare per day ──────────────────────────────
            for i, (_, row) in enumerate(prophet_fcst.iterrows()):
                pred_date = pd.Timestamp(row["ds"])
                actual_row = test[test["date"] == pred_date]
                if actual_row.empty:
                    continue

                actual_pc = float(actual_row["portcalls"].iloc[0])
                prophet_pred = float(row["yhat"])

                # ── V1 ───────────────────────────────────────
                v1_cong = compute_congestion_score(prophet_pred, baseline_expected, v1_std)
                actual_cong_v1 = compute_congestion_score(actual_pc, baseline_expected, v1_std)
                all_v1.append({
                    "port": port, "cutoff": cutoff_str, "date": pred_date.date(),
                    "predicted_pc": round(prophet_pred, 1), "actual_pc": round(actual_pc, 1),
                    "pred_cong": v1_cong, "actual_cong": actual_cong_v1,
                    "pred_tier": score_to_tier(v1_cong),
                    "actual_tier": score_to_tier(actual_cong_v1),
                })

                # ── V2 (ensemble + momentum) ─────────────────
                if has_xgb:
                    v2_ensemble = 0.6 * prophet_pred + 0.4 * float(xgb_fcst.iloc[i]["yhat"])
                else:
                    v2_ensemble = prophet_pred
                decay = max(0, 1.0 - i * 0.15)
                v2_pred = max(v2_ensemble + momentum * decay, 0)
                v2_cong = compute_congestion_score(v2_pred, baseline_expected, v2_std)
                actual_cong_v2 = compute_congestion_score(actual_pc, baseline_expected, v2_std)
                all_v2.append({
                    "port": port, "cutoff": cutoff_str, "date": pred_date.date(),
                    "predicted_pc": round(v2_pred, 1), "actual_pc": round(actual_pc, 1),
                    "pred_cong": v2_cong, "actual_cong": actual_cong_v2,
                    "pred_tier": score_to_tier(v2_cong),
                    "actual_tier": score_to_tier(actual_cong_v2),
                })

                # ── V3 (all improvements) ────────────────────
                # Ensemble: Prophet 50% + XGBoost 30% + ARIMA 20%
                v3_pred = prophet_pred * 0.5
                if has_xgb:
                    v3_pred += float(xgb_fcst.iloc[i]["yhat"]) * 0.3
                else:
                    v3_pred += prophet_pred * 0.3
                if has_arima:
                    v3_pred += float(arima_fcst.iloc[i]["yhat"]) * 0.2
                else:
                    v3_pred += prophet_pred * 0.2

                # Momentum with decay
                v3_pred = max(v3_pred + momentum * decay, 0)

                # Day-of-week adjustment
                dow = pred_date.dayofweek
                dow_factor = dow_factors.get(dow, 1.0)
                v3_pred_adj = v3_pred * dow_factor

                v3_cong = compute_congestion_score(v3_pred_adj, baseline_expected, v3_std)
                actual_cong_v3 = compute_congestion_score(actual_pc, baseline_expected, v3_std)

                # Use adaptive thresholds for V3
                v3_pred_tier = score_to_tier_adaptive(v3_cong, low_thresh, high_thresh)
                v3_actual_tier = score_to_tier_adaptive(actual_cong_v3, low_thresh, high_thresh)

                all_v3.append({
                    "port": port, "cutoff": cutoff_str, "date": pred_date.date(),
                    "predicted_pc": round(v3_pred_adj, 1), "actual_pc": round(actual_pc, 1),
                    "pred_cong": v3_cong, "actual_cong": actual_cong_v3,
                    "pred_tier": v3_pred_tier,
                    "actual_tier": v3_actual_tier,
                    "low_thresh": low_thresh, "high_thresh": high_thresh,
                })

    # ── Results ──────────────────────────────────────────────
    v1_df = pd.DataFrame(all_v1)
    v2_df = pd.DataFrame(all_v2)
    v3_df = pd.DataFrame(all_v3)

    print("\n" + "=" * 80)
    print("MULTI-WINDOW BACKTEST: V1 vs V2 vs V3")
    print(f"Windows: {CUTOFFS}")
    print(f"Ports: {len(TOP_PORTS)} | Horizon: {HORIZON} days")
    print("=" * 80)

    for label, rdf in [
        ("V1 (Prophet, interval std, fixed thresholds)", v1_df),
        ("V2 (Prophet+XGB, residual std, momentum)", v2_df),
        ("V3 (3-model ensemble, adaptive thresholds, DoW adj)", v3_df),
    ]:
        rdf["tier_correct"] = rdf["pred_tier"] == rdf["actual_tier"]
        rdf["pc_abs_error"] = (rdf["predicted_pc"] - rdf["actual_pc"]).abs()
        rdf["pc_pct_error"] = rdf.apply(
            lambda r: abs(r["predicted_pc"] - r["actual_pc"]) / r["actual_pc"] * 100
            if r["actual_pc"] > 0 else 0, axis=1
        )
        rdf["cong_abs_error"] = (rdf["pred_cong"] - rdf["actual_cong"]).abs()

        print(f"\n── {label} ──")
        print(f"  Total predictions:      {len(rdf)}")
        print(f"  Portcall MAE:           {rdf['pc_abs_error'].mean():.1f}")
        print(f"  Portcall MAPE:          {rdf['pc_pct_error'].mean():.1f}%")
        print(f"  Congestion Score MAE:   {rdf['cong_abs_error'].mean():.1f} / 100")
        print(f"  Tier Accuracy:          {rdf['tier_correct'].mean() * 100:.1f}%")
        print(f"  Predicted tiers: {rdf['pred_tier'].value_counts().to_dict()}")
        print(f"  Actual tiers:    {rdf['actual_tier'].value_counts().to_dict()}")

    # Per-port comparison
    print(f"\n── Per-Port Tier Accuracy (all windows) ──")
    print(f"  {'Port':<25} {'V1':>7} {'V2':>7} {'V3':>7} {'Best':>6}")
    print(f"  {'─'*25} {'─'*7} {'─'*7} {'─'*7} {'─'*6}")

    for port in sorted(v1_df["port"].unique()):
        t1 = (v1_df[v1_df.port == port].pred_tier == v1_df[v1_df.port == port].actual_tier).mean() * 100
        t2 = (v2_df[v2_df.port == port].pred_tier == v2_df[v2_df.port == port].actual_tier).mean() * 100
        t3 = (v3_df[v3_df.port == port].pred_tier == v3_df[v3_df.port == port].actual_tier).mean() * 100
        best = "V3" if t3 >= t2 and t3 >= t1 else ("V2" if t2 >= t1 else "V1")
        print(f"  {port:<25} {t1:>6.1f}% {t2:>6.1f}% {t3:>6.1f}% {best:>6}")

    # Per-window breakdown
    print(f"\n── Per-Window Tier Accuracy ──")
    print(f"  {'Cutoff':<14} {'V1':>7} {'V2':>7} {'V3':>7}")
    print(f"  {'─'*14} {'─'*7} {'─'*7} {'─'*7}")
    for cutoff in CUTOFFS:
        t1 = (v1_df[v1_df.cutoff == cutoff].pred_tier == v1_df[v1_df.cutoff == cutoff].actual_tier).mean() * 100
        t2 = (v2_df[v2_df.cutoff == cutoff].pred_tier == v2_df[v2_df.cutoff == cutoff].actual_tier).mean() * 100
        t3 = (v3_df[v3_df.cutoff == cutoff].pred_tier == v3_df[v3_df.cutoff == cutoff].actual_tier).mean() * 100
        print(f"  {cutoff:<14} {t1:>6.1f}% {t2:>6.1f}% {t3:>6.1f}%")

    # Summary
    t1_all = (v1_df["pred_tier"] == v1_df["actual_tier"]).mean() * 100
    t2_all = (v2_df["pred_tier"] == v2_df["actual_tier"]).mean() * 100
    t3_all = (v3_df["pred_tier"] == v3_df["actual_tier"]).mean() * 100

    print(f"\n{'=' * 80}")
    print(f"  TIER ACCURACY:  V1 = {t1_all:.1f}%  →  V2 = {t2_all:.1f}%  →  V3 = {t3_all:.1f}%")
    print(f"  IMPROVEMENT:    V1→V3 = {t3_all - t1_all:+.1f}%")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
