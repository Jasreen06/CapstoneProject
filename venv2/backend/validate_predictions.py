"""
validate_predictions.py
=======================
Step 2 of congestion score validation.

After pulling fresh PortWatch data, run this script to compare
the predictions saved earlier against actual portcall values.

Usage:
    1. First, run:  python save_predictions.py   (saves predictions)
    2. Wait a few days, then:  python data_pull.py  (get fresh data)
    3. Then run:  python validate_predictions.py   (compare)

Output:
    predictions/validation_YYYYMMDD.csv   — full comparison table
    Prints summary metrics (MAE, MAPE, accuracy by tier)
"""

from __future__ import annotations
import os
import sys
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

# ── Config ────────────────────────────────────────────────────
DATA_FILE = os.environ.get("DATA_FILE", "portwatch_us_data.csv")
PREDICTIONS_DIR = Path("predictions")


def compute_congestion_score(actual: float, expected: float, std_est: float) -> float:
    """Same z-score formula used in congestion_agent.py."""
    z = float(np.clip((actual - expected) / (std_est or 1.0), -3, 3))
    return round((z + 3) / 6 * 100, 1)


def score_to_tier(score: float) -> str:
    if score >= 67:
        return "HIGH"
    elif score >= 33:
        return "MEDIUM"
    else:
        return "LOW"


def main():
    # Find the most recent predictions file (prefer v2 if available)
    pred_files_v2 = sorted(PREDICTIONS_DIR.glob("predictions_v2_*.csv"))
    pred_files_v1 = sorted(PREDICTIONS_DIR.glob("predictions_*.csv"))
    # Filter out v2 files from v1 list
    pred_files_v1 = [f for f in pred_files_v1 if "_v2_" not in f.name]

    if pred_files_v2:
        pred_file = pred_files_v2[-1]
    elif pred_files_v1:
        pred_file = pred_files_v1[-1]
    else:
        logger.error("No prediction files found in predictions/. Run save_predictions.py first.")
        sys.exit(1)
    logger.info(f"Loading predictions from: {pred_file}")
    predictions = pd.read_csv(pred_file)
    predictions["predicted_date"] = pd.to_datetime(predictions["predicted_date"])

    # Load fresh PortWatch data
    logger.info(f"Loading fresh data from: {DATA_FILE}")
    df = load_and_clean(DATA_FILE)
    fresh_last_date = df["date"].max()
    logger.info(f"Fresh data goes up to: {fresh_last_date.date()}")

    # Compare predictions vs actuals
    results = []
    ports_with_data = 0
    ports_without_data = 0

    for port in predictions["port"].unique():
        port_preds = predictions[predictions["port"] == port]
        # Skip ports not in fresh data
        if port not in df["portname"].unique():
            logger.warning(f"  {port}: not in fresh data, skipping")
            ports_without_data += 1
            continue
        try:
            daily = get_port_daily_series(df, port)
        except Exception as e:
            logger.warning(f"  {port}: failed to build daily series ({e}), skipping")
            ports_without_data += 1
            continue

        if daily.empty:
            logger.warning(f"  {port}: no data in fresh CSV, skipping")
            ports_without_data += 1
            continue

        port_found = False
        for _, pred in port_preds.iterrows():
            pred_date = pred["predicted_date"]

            # Find actual value for this date
            actual_row = daily[daily["date"] == pred_date]
            if actual_row.empty:
                continue

            port_found = True
            actual_portcalls = float(actual_row["portcalls"].iloc[0])

            # Compute actual congestion score using the SAME baseline
            actual_congestion = compute_congestion_score(
                actual_portcalls,
                pred["baseline_expected"],
                pred["baseline_std"],
            )

            # Errors
            portcall_error = actual_portcalls - pred["predicted_portcalls"]
            portcall_abs_error = abs(portcall_error)
            portcall_pct_error = (
                abs(portcall_error) / actual_portcalls * 100
                if actual_portcalls > 0 else 0
            )

            congestion_error = actual_congestion - pred["predicted_congestion_score"]

            # Tier comparison
            predicted_tier = score_to_tier(pred["predicted_congestion_score"])
            actual_tier = score_to_tier(actual_congestion)
            tier_match = predicted_tier == actual_tier

            # Was actual within prediction interval?
            within_interval = (
                pred["predicted_lower"] <= actual_portcalls <= pred["predicted_upper"]
            )

            results.append({
                "port": port,
                "date": pred_date.date(),
                "predicted_portcalls": pred["predicted_portcalls"],
                "actual_portcalls": round(actual_portcalls, 1),
                "portcall_error": round(portcall_error, 1),
                "portcall_abs_error": round(portcall_abs_error, 1),
                "portcall_pct_error": round(portcall_pct_error, 1),
                "within_95_interval": within_interval,
                "predicted_congestion": pred["predicted_congestion_score"],
                "actual_congestion": actual_congestion,
                "congestion_error": round(congestion_error, 1),
                "predicted_tier": predicted_tier,
                "actual_tier": actual_tier,
                "tier_correct": tier_match,
                "baseline_expected": pred["baseline_expected"],
            })

        if port_found:
            ports_with_data += 1
        else:
            ports_without_data += 1

    if not results:
        logger.error(
            "No overlapping dates found between predictions and fresh data.\n"
            f"Predictions cover: {predictions['predicted_date'].min().date()} → {predictions['predicted_date'].max().date()}\n"
            f"Fresh data covers up to: {fresh_last_date.date()}\n"
            "Pull newer data and try again."
        )
        sys.exit(1)

    # ── Build results DataFrame ──────────────────────────────
    results_df = pd.DataFrame(results)

    # Save full comparison
    timestamp = datetime.now().strftime("%Y%m%d")
    outfile = PREDICTIONS_DIR / f"validation_{timestamp}.csv"
    results_df.to_csv(outfile, index=False)

    # ── Print summary metrics ────────────────────────────────
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)

    print(f"\nPorts validated: {ports_with_data}")
    print(f"Ports without fresh data: {ports_without_data}")
    print(f"Total prediction-actual pairs: {len(results_df)}")

    # Portcall accuracy
    mae = results_df["portcall_abs_error"].mean()
    mape = results_df["portcall_pct_error"].mean()
    coverage = results_df["within_95_interval"].mean() * 100

    print(f"\n── Portcall Forecast Accuracy ──")
    print(f"  MAE  (Mean Absolute Error):     {mae:.1f} portcalls")
    print(f"  MAPE (Mean Absolute % Error):   {mape:.1f}%")
    print(f"  95% Interval Coverage:          {coverage:.1f}% (target: ≥95%)")

    # Congestion tier accuracy
    tier_accuracy = results_df["tier_correct"].mean() * 100
    print(f"\n── Congestion Tier Accuracy ──")
    print(f"  Tier match (LOW/MEDIUM/HIGH):   {tier_accuracy:.1f}%")

    # Confusion matrix
    print(f"\n  Tier Confusion Matrix:")
    tiers = ["LOW", "MEDIUM", "HIGH"]
    print(f"  {'':>12} {'Actual LOW':>12} {'Actual MED':>12} {'Actual HIGH':>12}")
    for pt in tiers:
        row = []
        for at in tiers:
            count = len(results_df[(results_df["predicted_tier"] == pt) & (results_df["actual_tier"] == at)])
            row.append(count)
        label = f"Pred {pt}"
        print(f"  {label:>12} {row[0]:>12} {row[1]:>12} {row[2]:>12}")

    # Per-port breakdown
    print(f"\n── Per-Port Summary ──")
    print(f"  {'Port':<25} {'MAE':>6} {'MAPE%':>7} {'Tier%':>7} {'Coverage%':>10}")
    print(f"  {'─'*25} {'─'*6} {'─'*7} {'─'*7} {'─'*10}")

    for port in sorted(results_df["port"].unique()):
        pdf = results_df[results_df["port"] == port]
        p_mae = pdf["portcall_abs_error"].mean()
        p_mape = pdf["portcall_pct_error"].mean()
        p_tier = pdf["tier_correct"].mean() * 100
        p_cov = pdf["within_95_interval"].mean() * 100
        print(f"  {port:<25} {p_mae:>6.1f} {p_mape:>6.1f}% {p_tier:>6.1f}% {p_cov:>9.1f}%")

    # Congestion score errors
    cong_mae = results_df["congestion_error"].abs().mean()
    cong_rmse = float(np.sqrt((results_df["congestion_error"] ** 2).mean()))
    print(f"\n── Congestion Score Error ──")
    print(f"  MAE  (Mean Absolute Error):     {cong_mae:.1f} points (out of 100)")
    print(f"  RMSE (Root Mean Squared Error): {cong_rmse:.1f} points")

    # ── Additional regression metric: SMAPE ──
    pred_pc = results_df["predicted_portcalls"].values
    act_pc  = results_df["actual_portcalls"].values
    denom = (np.abs(pred_pc) + np.abs(act_pc)) / 2
    smape = float(np.mean(np.where(denom == 0, 0, np.abs(pred_pc - act_pc) / np.where(denom == 0, 1, denom))) * 100)

    pc_rmse = float(np.sqrt(((pred_pc - act_pc) ** 2).mean()))
    print(f"\n── Additional Portcall Metrics ──")
    print(f"  RMSE:                            {pc_rmse:.2f} portcalls")
    print(f"  SMAPE (Symmetric MAPE):          {smape:.1f}%  (handles zero actuals)")

    # ── Per-tier Precision / Recall / F1 ──
    print(f"\n── Per-Tier Precision / Recall / F1 ──")
    print(f"  {'Tier':<8} {'Precision':>10} {'Recall':>8} {'F1':>6} {'Support':>8}")
    for tier in tiers:
        tp = len(results_df[(results_df["predicted_tier"] == tier) & (results_df["actual_tier"] == tier)])
        fp = len(results_df[(results_df["predicted_tier"] == tier) & (results_df["actual_tier"] != tier)])
        fn = len(results_df[(results_df["predicted_tier"] != tier) & (results_df["actual_tier"] == tier)])
        support = tp + fn
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        print(f"  {tier:<8} {precision:>9.2%} {recall:>7.2%} {f1:>5.2f} {support:>8}")

    # ── Cohen's Kappa (accuracy adjusted for class imbalance) ──
    n = len(results_df)
    po = results_df["tier_correct"].mean()
    pe = sum(
        (len(results_df[results_df["predicted_tier"] == t]) / n) *
        (len(results_df[results_df["actual_tier"] == t]) / n)
        for t in tiers
    )
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 0 else 0.0
    print(f"\n── Cohen's Kappa ──")
    print(f"  κ = {kappa:.3f}  (0=chance, 1=perfect; >0.6 substantial agreement)")

    # ── Directional accuracy (per port) ──
    # Did we correctly predict whether congestion would rise or fall vs the previous day's actual?
    dir_correct, dir_total = 0, 0
    for port in results_df["port"].unique():
        pdf = results_df[results_df["port"] == port].sort_values("date").reset_index(drop=True)
        for i in range(1, len(pdf)):
            prev_actual = pdf.loc[i-1, "actual_congestion"]
            pred_dir   = np.sign(pdf.loc[i, "predicted_congestion"] - prev_actual)
            actual_dir = np.sign(pdf.loc[i, "actual_congestion"] - prev_actual)
            if pred_dir == actual_dir:
                dir_correct += 1
            dir_total += 1
    dir_acc = (dir_correct / dir_total * 100) if dir_total > 0 else 0.0
    print(f"\n── Directional Accuracy (rise/fall prediction) ──")
    print(f"  {dir_acc:.1f}%  ({dir_correct}/{dir_total} correct direction predictions)")

    # ── Skill Score vs Naive Baseline (persistence: tomorrow = today) ──
    # If naive forecast = previous day's actual, what would its MAE be?
    naive_errors = []
    for port in results_df["port"].unique():
        pdf = results_df[results_df["port"] == port].sort_values("date").reset_index(drop=True)
        for i in range(1, len(pdf)):
            naive_errors.append(abs(pdf.loc[i, "actual_portcalls"] - pdf.loc[i-1, "actual_portcalls"]))
    if naive_errors:
        naive_mae = float(np.mean(naive_errors))
        skill = (1 - mae / naive_mae) * 100 if naive_mae > 0 else 0.0
        print(f"\n── Skill Score vs Naive Baseline (persistence) ──")
        print(f"  Naive MAE (tomorrow=today):      {naive_mae:.2f} portcalls")
        print(f"  Model MAE:                        {mae:.2f} portcalls")
        print(f"  Skill score:                      {skill:+.1f}%  (>0 means model beats naive)")

    print(f"\n✓ Full results saved to: {outfile}")
    print(f"\nInterpretation:")
    print(f"  - MAPE < 20%: Good forecast")
    print(f"  - MAPE < 10%: Excellent forecast")
    print(f"  - Tier accuracy > 70%: Congestion scoring is reliable")
    print(f"  - Cohen's κ > 0.6: Substantial agreement (better than chance)")
    print(f"  - Directional accuracy > 60%: Trend predictions are reliable")
    print(f"  - Skill score > 0: Model beats naive 'tomorrow = today' baseline")
    print(f"  - 95% coverage ≈ 95%: Prediction intervals are well calibrated")


if __name__ == "__main__":
    main()
