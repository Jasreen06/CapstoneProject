"""
forecast_tracker.py
===================
Saves forecast predictions to a log file and validates them
against actual data when it becomes available.

Every time /api/forecast is called, the predictions are saved to
forecast_log.csv. When new PortWatch data arrives, run validate()
to see how accurate the models actually were.

Log columns:
    logged_at      — when the forecast was made
    port           — port name
    model          — ARIMA / Prophet / XGBoost
    target_date    — the date being predicted
    yhat           — predicted portcalls
    yhat_lower     — lower confidence bound
    yhat_upper     — upper confidence bound
    actual         — actual portcalls (filled in during validation)
    error          — yhat - actual (filled in during validation)
    validated_at   — when validation was run
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_DIR      = os.path.dirname(os.path.abspath(__file__))
LOG_FILE  = os.path.join(_DIR, "forecast_log.csv")

LOG_COLS = [
    "logged_at", "port", "model",
    "target_date", "yhat", "yhat_lower", "yhat_upper",
    "actual", "error", "within_interval", "validated_at",
]


# ──────────────────────────────────────────────────────────────────────────────
# SAVE FORECAST
# ──────────────────────────────────────────────────────────────────────────────

def save_forecast(port: str, model: str, forecast_df: pd.DataFrame) -> None:
    """
    Save a forecast to the log file.

    Parameters
    ----------
    port        : port name
    model       : model name (ARIMA / Prophet / XGBoost)
    forecast_df : DataFrame with columns ds, yhat, yhat_lower, yhat_upper
                  (standard output from forecasting.py)
    """
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        rows = []
        for _, row in forecast_df.iterrows():
            rows.append({
                "logged_at":       now,
                "port":            port,
                "model":           model,
                "target_date":     str(row.get("ds") or row.get("date"))[:10],
                "yhat":            round(float(row["yhat"]), 3),
                "yhat_lower":      round(float(row["yhat_lower"]), 3),
                "yhat_upper":      round(float(row["yhat_upper"]), 3),
                "actual":          None,
                "error":           None,
                "within_interval": None,
                "validated_at":    None,
            })

        new_df = pd.DataFrame(rows, columns=LOG_COLS)

        file_exists = Path(LOG_FILE).exists()
        new_df.to_csv(LOG_FILE, mode="a", header=not file_exists, index=False)

        logger.info(f"[ForecastTracker] Saved {len(rows)} predictions → {LOG_FILE}")

    except Exception as e:
        logger.error(f"[ForecastTracker] Failed to save forecast: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# VALIDATE FORECASTS
# ──────────────────────────────────────────────────────────────────────────────

def validate(data_file: str | None = None) -> dict:
    """
    Compare saved forecasts against actual portcalls data.

    For each logged prediction where:
        - actual data is now available (target_date <= last date in CSV)
        - not yet validated

    Fills in: actual, error, within_interval, validated_at.

    Returns a summary dict with accuracy metrics per model.
    """
    if not Path(LOG_FILE).exists():
        return {"error": "No forecast log found. Run /api/forecast first."}

    data_file = data_file or os.environ.get("DATA_FILE", "portwatch_us_data.csv")
    data_path = os.path.join(_DIR, data_file) if not os.path.isabs(data_file) else data_file

    if not Path(data_path).exists():
        return {"error": f"Data file not found: {data_path}"}

    try:
        from data_cleaning import load_and_clean

        # Load actual data
        actuals_df = load_and_clean(data_path)
        actuals_df["date"] = pd.to_datetime(actuals_df["date"])

        # Load forecast log
        log = pd.read_csv(LOG_FILE)
        log["target_date"] = pd.to_datetime(log["target_date"])

        # Only process unvalidated rows
        unvalidated = log[log["validated_at"].isna()].copy()
        if unvalidated.empty:
            return _build_summary(log)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        updated = 0

        for idx, row in unvalidated.iterrows():
            port        = row["port"]
            target_date = row["target_date"]

            # Look up actual value
            match = actuals_df[
                (actuals_df["portname"] == port) &
                (actuals_df["date"]     == target_date)
            ]

            if match.empty:
                continue  # actual data not available yet

            actual = float(match["portcalls"].iloc[0])
            error  = round(float(row["yhat"]) - actual, 3)
            within = bool(row["yhat_lower"] <= actual <= row["yhat_upper"])

            log.at[idx, "actual"]          = actual
            log.at[idx, "error"]           = error
            log.at[idx, "within_interval"] = within
            log.at[idx, "validated_at"]    = now
            updated += 1

        # Save updated log
        log.to_csv(LOG_FILE, index=False)
        logger.info(f"[ForecastTracker] Validated {updated} predictions")

        return _build_summary(log)

    except Exception as e:
        logger.error(f"[ForecastTracker] Validation error: {e}")
        return {"error": str(e)}


def _build_summary(log: pd.DataFrame) -> dict:
    """Build accuracy summary from validated log entries."""
    validated = log[log["validated_at"].notna()].copy()

    if validated.empty:
        total     = len(log)
        pending   = int(log["validated_at"].isna().sum())
        return {
            "message":           "No validated forecasts yet — actual data not available",
            "total_logged":      total,
            "pending_dates":     pending,
            "earliest_forecast": str(log["target_date"].min())[:10] if len(log) else None,
            "latest_forecast":   str(log["target_date"].max())[:10] if len(log) else None,
        }

    validated["abs_error"] = validated["error"].abs()
    validated["pct_error"] = (
        validated["abs_error"] /
        validated["actual"].replace(0, np.nan) * 100
    )

    # Per-model summary
    model_summary = {}
    for model, grp in validated.groupby("model"):
        model_summary[model] = {
            "predictions":      len(grp),
            "mae":              round(float(grp["abs_error"].mean()), 3),
            "rmse":             round(float(np.sqrt((grp["error"] ** 2).mean())), 3),
            "mape":             round(float(grp["pct_error"].mean(skipna=True)), 2),
            "coverage":         round(float(grp["within_interval"].mean()), 3),
            "avg_over_predict": round(float(grp["error"].mean()), 3),
        }

    # Best model by MAE
    best = min(model_summary, key=lambda m: model_summary[m]["mae"]) if model_summary else None

    return {
        "total_validated":   len(validated),
        "total_pending":     int(log["validated_at"].isna().sum()),
        "date_range":        {
            "from": str(validated["target_date"].min())[:10],
            "to":   str(validated["target_date"].max())[:10],
        },
        "best_model":        best,
        "model_summary":     model_summary,
    }


# ──────────────────────────────────────────────────────────────────────────────
# READ LOG
# ──────────────────────────────────────────────────────────────────────────────

def get_log(port: str | None = None, model: str | None = None) -> dict:
    """Return the forecast log as a dict, optionally filtered."""
    if not Path(LOG_FILE).exists():
        return {"records": [], "total": 0}

    log = pd.read_csv(LOG_FILE)

    if port:
        log = log[log["port"] == port]
    if model:
        log = log[log["model"] == model]

    log = log.sort_values("target_date", ascending=False)

    records = log.where(pd.notna(log), None).to_dict("records")
    return {"records": records, "total": len(records)}