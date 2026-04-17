"""
forecast_tracker.py
===================
Saves forecast predictions to Supabase and validates them against actual data.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# SAVE FORECAST
# ──────────────────────────────────────────────────────────────────────────────

def save_forecast(port: str, model: str, forecast_df: pd.DataFrame) -> None:
    try:
        from db import get_engine
        engine = get_engine()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        rows = []
        for _, row in forecast_df.iterrows():
            rows.append({
                "logged_at":        now,
                "port":             port,
                "model":            model,
                "target_date":      str(row.get("ds") or row.get("date"))[:10],
                "yhat":             round(float(row["yhat"]), 3),
                "yhat_lower":       round(float(row["yhat_lower"]), 3),
                "yhat_upper":       round(float(row["yhat_upper"]), 3),
                "actual":           None,
                "error":            None,
                "within_interval":  None,
                "validated_at":     None,
            })

        new_df = pd.DataFrame(rows)
        new_df.to_sql("forecast_log", engine, if_exists="append", index=False)
        logger.info(f"[ForecastTracker] Saved {len(rows)} predictions for {port}/{model}")

    except Exception as e:
        logger.error(f"[ForecastTracker] Failed to save forecast: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# VALIDATE FORECASTS
# ──────────────────────────────────────────────────────────────────────────────

def validate(data_file: str = None) -> dict:
    """
    Match saved forecasts against actual portcalls and fill in error metrics.
    `data_file` argument is ignored — kept for backward compatibility.
    """
    try:
        from db import get_engine
        from data_cleaning import load_and_clean
        engine = get_engine()

        # Load actual port data
        actuals_df = load_and_clean()
        actuals_df["date"] = pd.to_datetime(actuals_df["date"])

        # Load unvalidated forecasts
        log = pd.read_sql(
            "SELECT * FROM forecast_log WHERE validated_at IS NULL",
            engine
        )

        if log.empty:
            full_log = pd.read_sql("SELECT * FROM forecast_log", engine)
            return _build_summary(full_log)

        log["target_date"] = pd.to_datetime(log["target_date"])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        updated = 0

        with engine.connect() as conn:
            for _, row in log.iterrows():
                match = actuals_df[
                    (actuals_df["portname"] == row["port"]) &
                    (actuals_df["date"]     == row["target_date"])
                ]
                if match.empty:
                    continue

                actual = float(match["portcalls"].iloc[0])
                error  = round(float(row["yhat"]) - actual, 3)
                within = bool(row["yhat_lower"] <= actual <= row["yhat_upper"])

                conn.execute(text("""
                    UPDATE forecast_log
                    SET actual = :actual,
                        error  = :error,
                        within_interval = :within,
                        validated_at    = :now
                    WHERE id = :row_id
                """), {
                    "actual": actual,
                    "error":  error,
                    "within": within,
                    "now":    now,
                    "row_id": int(row["id"]),
                })
                updated += 1
            conn.commit()

        logger.info(f"[ForecastTracker] Validated {updated} predictions")
        full_log = pd.read_sql("SELECT * FROM forecast_log", engine)
        return _build_summary(full_log)

    except Exception as e:
        logger.error(f"[ForecastTracker] Validation error: {e}")
        return {"error": str(e)}


def _build_summary(log: pd.DataFrame) -> dict:
    validated = log[log["validated_at"].notna()].copy()

    if validated.empty:
        return {
            "message":       "No validated forecasts yet — actual data not available",
            "total_logged":  len(log),
            "pending_dates": int(log["validated_at"].isna().sum()),
        }

    validated["abs_error"] = validated["error"].abs()
    validated["pct_error"] = (
        validated["abs_error"] /
        validated["actual"].replace(0, np.nan) * 100
    )

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

    best = min(model_summary, key=lambda m: model_summary[m]["mae"]) if model_summary else None

    return {
        "total_validated": len(validated),
        "total_pending":   int(log["validated_at"].isna().sum()),
        "best_model":      best,
        "model_summary":   model_summary,
    }


# ──────────────────────────────────────────────────────────────────────────────
# READ LOG
# ──────────────────────────────────────────────────────────────────────────────

def get_log(port: str = None, model: str = None) -> dict:
    try:
        from db import get_engine
        engine = get_engine()

        query = "SELECT * FROM forecast_log WHERE 1=1"
        params = {}
        if port:
            query += " AND port = :port"
            params["port"] = port
        if model:
            query += " AND model = :model"
            params["model"] = model
        query += " ORDER BY target_date DESC"

        log = pd.read_sql(text(query), engine, params=params)
        records = log.where(pd.notna(log), None).to_dict("records")
        return {"records": records, "total": len(records)}

    except Exception as e:
        logger.error(f"[ForecastTracker] get_log error: {e}")
        return {"records": [], "total": 0}
