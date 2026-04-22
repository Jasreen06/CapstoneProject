"""
model_comparison.py
===================
Step 5: Walk-forward cross-validation across all three models and ports.
Selects the best model, saves results to model_comparison_results.json.

Usage:
    python model_comparison.py                              # uses portwatch_us_data.csv
    python model_comparison.py --data my_data.csv --ports "Los Angeles,Houston"
    python model_comparison.py --top-n 5                   # evaluate top-5 busiest ports
"""

from __future__ import annotations
import argparse
import json
import logging
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_FILE = "model_comparison_results.json"


# ──────────────────────────────────────────────────────────────
# Main comparison runner
# ──────────────────────────────────────────────────────────────

def run_comparison(
    filepath: str,
    ports: list[str] | None = None,
    top_n: int = 5,
    initial_train_days: int = 365,
    horizon: int = 7,
    n_folds: int = 8,
) -> dict:
    """
    Run walk-forward CV for each (port, model) combination.

    Returns a results dict which is also written to OUTPUT_FILE.
    """
    from data_cleaning import load_and_clean, get_port_daily_series
    from feature_engineering import build_features
    from forecasting import ALL_MODELS, get_model
    from metrics import evaluate_forecast, summarise_metrics, walk_forward_splits, pick_best_model

    df = load_and_clean(filepath)

    # ── Select ports ─────────────────────────────────────────
    if ports:
        port_list = [p for p in ports if p in df["portname"].unique()]
        if not port_list:
            raise ValueError(f"None of the requested ports found in data: {ports}")
    else:
        # Top-N by total portcalls
        port_list = (
            df.groupby("portname")["portcalls"]
            .sum()
            .sort_values(ascending=False)
            .head(top_n)
            .index.tolist()
        )

    logger.info(f"Evaluating {len(port_list)} ports: {port_list}")

    results_by_port: dict[str, dict] = {}
    agg_by_model: dict[str, list] = {m: [] for m in ALL_MODELS}

    for port in port_list:
        logger.info(f"\n{'─'*60}\nPort: {port}")
        daily = get_port_daily_series(df, port)

        if len(daily) < initial_train_days + horizon * 2:
            logger.warning(f"  Skipping {port} — not enough data ({len(daily)} days).")
            continue

        results_by_port[port] = {}
        values = daily["portcalls"].values.astype(float)
        step   = max(horizon, len(values) // (n_folds + 1))

        splits = walk_forward_splits(
            n=len(values),
            initial_train_size=initial_train_days,
            horizon=horizon,
            step=step,
        )
        # Limit to n_folds
        splits = splits[:n_folds]
        logger.info(f"  {len(splits)} CV folds")

        for model_name in ALL_MODELS:
            fold_metrics = []
            for fold_idx, (train_idx, test_idx) in enumerate(splits):
                train_slice = daily.iloc[train_idx].copy()
                test_vals   = values[test_idx]

                try:
                    t0 = time.time()
                    model = get_model(model_name)
                    model.fit(train_slice)
                    fcst = model.predict(horizon=len(test_idx))
                    elapsed = time.time() - t0

                    y_pred  = fcst["yhat"].values
                    y_lower = fcst["yhat_lower"].values
                    y_upper = fcst["yhat_upper"].values

                    m = evaluate_forecast(
                        y_true=test_vals,
                        y_pred=y_pred,
                        y_lower=y_lower,
                        y_upper=y_upper,
                        fit_time_s=elapsed,
                    )
                    fold_metrics.append(m)

                except Exception as e:
                    logger.warning(f"  {model_name} fold {fold_idx} failed: {e}")

            if fold_metrics:
                summary = summarise_metrics(fold_metrics)
                results_by_port[port][model_name] = summary
                agg_by_model[model_name].append(summary)
                logger.info(
                    f"  {model_name:8s}  MAPE={summary.get('mape',np.nan):.1f}%  "
                    f"RMSE={summary.get('rmse',np.nan):.3f}  "
                    f"t={summary.get('fit_time_s',0):.2f}s"
                )
            else:
                logger.warning(f"  {model_name} — no valid folds.")

    # ── Aggregate across ports ───────────────────────────────
    from metrics import summarise_metrics as _sm

    aggregate_summary: dict[str, dict] = {}
    for mname, fold_list in agg_by_model.items():
        if fold_list:
            agg = _sm(fold_list)
            agg["ports_evaluated"] = len(fold_list)
            aggregate_summary[mname] = agg

    best_model = _pick_best(aggregate_summary)
    recommendation = _build_recommendation(aggregate_summary, best_model)

    output = {
        "best_model":         best_model,
        "recommendation":     recommendation,
        "aggregate_summary":  aggregate_summary,
        "per_port_results":   results_by_port,
        "evaluation_config":  {
            "ports":               port_list,
            "initial_train_days":  initial_train_days,
            "horizon":             horizon,
            "n_folds":             n_folds,
        },
    }

    try:
        from db import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM model_comparison_results"))
            conn.execute(text(
                "INSERT INTO model_comparison_results (results) VALUES (:r)"
            ), {"r": json.dumps(output, default=_json_safe)})
            conn.commit()
        logger.info("Model comparison results saved to database.")
    except Exception as e:
        logger.error(f"Failed to save model comparison results to DB: {e}")

    logger.info(f"\n{'='*60}")
    logger.info(f"Best model: {best_model}")
    _print_summary_table(aggregate_summary)

    return output


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _pick_best(aggregate_summary: dict) -> str:
    """Choose model with lowest SMAPE; fall back to MAPE then MAE."""
    def score(m: dict) -> float:
        for key in ["smape", "mape", "mae"]:
            v = m.get(key, np.nan)
            if not np.isnan(v):
                return v
        return np.inf

    if not aggregate_summary:
        return "Prophet"
    return min(aggregate_summary, key=lambda n: score(aggregate_summary[n]))


def _build_recommendation(summary: dict, best: str) -> str:
    if not summary:
        return "Insufficient data for comparison."
    lines = [f"Recommended model: {best}."]
    for name, m in summary.items():
        mape_str = f"{m.get('mape', float('nan')):.1f}%"
        smape_str = f"{m.get('smape', float('nan')):.1f}%"
        lines.append(f"  {name}: MAPE={mape_str}, SMAPE={smape_str}")
    if len(summary) > 1:
        sorted_m = sorted(summary.items(), key=lambda x: x[1].get("smape", np.inf))
        if len(sorted_m) >= 2:
            winner = sorted_m[0][0]
            runner = sorted_m[1][0]
            diff   = sorted_m[1][1].get("smape", 0) - sorted_m[0][1].get("smape", 0)
            lines.append(f"  {winner} outperforms {runner} by {diff:.1f}pp SMAPE.")
    return " ".join(lines)


def _print_summary_table(summary: dict):
    from metrics import metrics_to_dataframe
    if not summary:
        return
    df = metrics_to_dataframe(summary)
    print("\nModel comparison summary:")
    print(df.to_string())


def _json_safe(obj):
    """JSON serialiser that handles numpy scalars."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare ARIMA / Prophet / XGBoost.")
    parser.add_argument("--data",    default="portwatch_us_data.csv", help="CSV path")
    parser.add_argument("--ports",   default=None, help="Comma-separated port names")
    parser.add_argument("--top-n",   type=int, default=5, help="Top-N busiest ports (if --ports not set)")
    parser.add_argument("--horizon", type=int, default=7, help="Forecast horizon in days")
    parser.add_argument("--folds",   type=int, default=8, help="Max CV folds per port")
    parser.add_argument("--train",   type=int, default=365, help="Initial training window (days)")
    args = parser.parse_args()

    port_list = [p.strip() for p in args.ports.split(",")] if args.ports else None

    run_comparison(
        filepath=args.data,
        ports=port_list,
        top_n=args.top_n,
        initial_train_days=args.train,
        horizon=args.horizon,
        n_folds=args.folds,
    )
