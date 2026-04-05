"""
metrics.py
==========
Step 3: Evaluation metrics for forecast model comparison.

Usage:
    from metrics import evaluate_forecast, summarise_metrics
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict


# ──────────────────────────────────────────────
# Core metric functions
# ──────────────────────────────────────────────

def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true: np.ndarray, y_pred: np.ndarray, eps: float = 1e-8) -> float:
    """
    Mean Absolute Percentage Error.
    Skips time-steps where y_true == 0 to avoid division-by-zero inflation.
    """
    mask = np.abs(y_true) > eps
    if mask.sum() == 0:
        return np.nan
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def smape(y_true: np.ndarray, y_pred: np.ndarray, eps: float = 1e-8) -> float:
    """Symmetric MAPE – bounded [0, 200%], more stable than MAPE near zero."""
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2 + eps
    return float(np.mean(np.abs(y_true - y_pred) / denom) * 100)


def coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Fraction of actual values within the [lower, upper] prediction interval."""
    return float(np.mean((y_true >= lower) & (y_true <= upper)))


def interval_width(lower: np.ndarray, upper: np.ndarray) -> float:
    """Average width of prediction intervals."""
    return float(np.mean(upper - lower))


# ──────────────────────────────────────────────
# Unified evaluator
# ──────────────────────────────────────────────

def evaluate_forecast(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_lower: np.ndarray | None = None,
    y_upper: np.ndarray | None = None,
    fit_time_s: float = 0.0,
) -> Dict[str, float]:
    """
    Compute a full metric suite for a single forecast.

    Parameters
    ----------
    y_true     : actual values (numpy 1-D array)
    y_pred     : point forecast
    y_lower    : lower bound of prediction interval (optional)
    y_upper    : upper bound of prediction interval (optional)
    fit_time_s : model fit/train time in seconds

    Returns
    -------
    dict with keys: mae, rmse, mape, smape, coverage, interval_width, fit_time_s
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.maximum(np.asarray(y_pred, dtype=float), 0)

    result: Dict[str, float] = {
        "mae":        mae(y_true, y_pred),
        "rmse":       rmse(y_true, y_pred),
        "mape":       mape(y_true, y_pred),
        "smape":      smape(y_true, y_pred),
        "fit_time_s": fit_time_s,
    }

    if y_lower is not None and y_upper is not None:
        yl = np.asarray(y_lower, dtype=float)
        yu = np.asarray(y_upper, dtype=float)
        result["coverage"]       = coverage(y_true, yl, yu)
        result["interval_width"] = interval_width(yl, yu)
    else:
        result["coverage"]       = np.nan
        result["interval_width"] = np.nan

    return result


def summarise_metrics(results: list[Dict]) -> Dict[str, float]:
    """
    Aggregate a list of per-fold / per-port metric dicts into averages.
    Ignores NaN values when averaging.
    """
    keys = {k for r in results for k in r.keys()}
    return {
        k: float(np.nanmean([r.get(k, np.nan) for r in results]))
        for k in keys
    }


# ──────────────────────────────────────────────
# Walk-forward cross-validation splitter
# ──────────────────────────────────────────────

def walk_forward_splits(
    n: int,
    initial_train_size: int,
    horizon: int,
    step: int | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Generate (train_idx, test_idx) tuples for walk-forward (time-series) CV.

    Parameters
    ----------
    n                  : total number of time steps
    initial_train_size : minimum training window
    horizon            : number of steps to forecast per fold
    step               : how many steps to advance between folds
                         (defaults to horizon → non-overlapping test windows)
    """
    if step is None:
        step = horizon

    splits = []
    train_end = initial_train_size
    while train_end + horizon <= n:
        train_idx = np.arange(0, train_end)
        test_idx  = np.arange(train_end, min(train_end + horizon, n))
        splits.append((train_idx, test_idx))
        train_end += step

    return splits


# ──────────────────────────────────────────────
# Pretty-print helpers
# ──────────────────────────────────────────────

def metrics_to_dataframe(model_metrics: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """
    Convert {model_name: metrics_dict} mapping to a display DataFrame.
    """
    rows = []
    for model, m in model_metrics.items():
        rows.append({
            "Model":     model,
            "MAE":       round(m.get("mae",  np.nan), 3),
            "RMSE":      round(m.get("rmse", np.nan), 3),
            "MAPE (%)":  round(m.get("mape", np.nan), 2),
            "SMAPE (%)": round(m.get("smape",np.nan), 2),
            "Coverage":  round(m.get("coverage", np.nan), 3),
            "Fit (s)":   round(m.get("fit_time_s", np.nan), 2),
        })
    return pd.DataFrame(rows).set_index("Model")


def pick_best_model(model_metrics: Dict[str, Dict[str, float]],
                    primary_metric: str = "smape") -> str:
    """
    Return the model name with the lowest value of primary_metric.
    Falls back to MAPE → MAE if primary_metric is missing.
    """
    def score(m: Dict) -> float:
        for key in [primary_metric, "smape", "mape", "mae"]:
            v = m.get(key, np.nan)
            if not np.isnan(v):
                return v
        return np.inf

    return min(model_metrics, key=lambda name: score(model_metrics[name]))


if __name__ == "__main__":
    # Quick smoke-test
    rng = np.random.default_rng(42)
    true  = rng.integers(5, 20, 30).astype(float)
    pred  = true + rng.normal(0, 2, 30)
    lower = pred - 3
    upper = pred + 3

    m = evaluate_forecast(true, pred, lower, upper, fit_time_s=1.23)
    print("Metric smoke-test:")
    for k, v in m.items():
        print(f"  {k:20s} = {v:.4f}")

    splits = walk_forward_splits(100, 60, 7, 7)
    print(f"\nWalk-forward splits: {len(splits)} folds")
    print(f"  First fold train: {splits[0][0][[0,-1]]}  test: {splits[0][1]}")
