"""
feature_engineering.py
=======================
Step 2: Build rich feature sets from the cleaned daily time series.

Usage:
    from data_cleaning import load_and_clean, get_port_daily_series
    from feature_engineering import build_features

    df_clean = load_and_clean("portwatch_us_data.csv")
    daily    = get_port_daily_series(df_clean, "Los Angeles")
    features = build_features(daily)
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def build_features(daily: pd.DataFrame) -> pd.DataFrame:
    """
    Build all features from a port's daily time-series DataFrame.

    Input columns expected:
        date, portcalls, import_total, export_total,
        portcalls_container, portcalls_dry_bulk,
        portcalls_general_cargo, portcalls_roro, portcalls_tanker

    Returns the original DataFrame plus engineered feature columns.
    """
    df = daily.copy()
    df = df.sort_values("date").reset_index(drop=True)

    df = _calendar_features(df)
    df = _rolling_features(df)
    df = _lag_features(df)
    df = _flow_features(df)
    df = _vessel_mix_features(df)
    df = _congestion_score(df)

    logger.info(f"Feature engineering: {len(df)} rows, {len(df.columns)} columns")
    return df


def get_model_feature_cols() -> list[str]:
    """Return the feature column names used by ML models."""
    return [
        # Calendar
        "day_of_week", "month", "week_of_year", "is_weekend", "quarter",
        # Lags
        "portcalls_lag1", "portcalls_lag7", "portcalls_lag14", "portcalls_lag28",
        # Rolling
        "portcalls_roll7", "portcalls_roll14", "portcalls_roll30",
        "portcalls_roll7_std", "portcalls_roll14_std", "portcalls_roll30_std",
        # Trend
        "portcalls_roll7_slope", "portcalls_roll30_slope",
        # Flow
        "net_flow", "import_export_ratio",
        "import_roll7", "export_roll7",
        # Vessel mix ratios
        "container_share", "tanker_share", "dry_bulk_share",
        # Congestion
        "congestion_score", "congestion_z",
    ]


# ──────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────

def _calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Day-of-week, month, week, weekend flag, quarter, year."""
    df["day_of_week"]  = df["date"].dt.dayofweek          # 0=Mon
    df["month"]        = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["quarter"]      = df["date"].dt.quarter
    df["year"]         = df["date"].dt.year
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)
    return df


def _rolling_features(df: pd.DataFrame, col: str = "portcalls") -> pd.DataFrame:
    """Rolling mean, std and slope at 7/14/30-day windows."""
    for w in [7, 14, 30]:
        roll = df[col].rolling(w, min_periods=1)
        df[f"{col}_roll{w}"]     = roll.mean()
        df[f"{col}_roll{w}_std"] = roll.std().fillna(0)

    # Slope = (last value - first value) / window  for 7 and 30-day windows
    def slope(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window, min_periods=2).apply(
            lambda x: (x[-1] - x[0]) / len(x), raw=True
        ).fillna(0)

    df[f"{col}_roll7_slope"]  = slope(df[col], 7)
    df[f"{col}_roll30_slope"] = slope(df[col], 30)
    return df


def _lag_features(df: pd.DataFrame, col: str = "portcalls") -> pd.DataFrame:
    """Lag features: 1, 7, 14, 28 days."""
    for lag in [1, 7, 14, 28]:
        df[f"{col}_lag{lag}"] = df[col].shift(lag).fillna(0)
    return df


def _flow_features(df: pd.DataFrame) -> pd.DataFrame:
    """Net cargo flow, import/export ratio, rolling flows."""
    imp = df.get("import_total", pd.Series(0, index=df.index))
    exp = df.get("export_total", pd.Series(0, index=df.index))

    df["net_flow"]           = imp - exp
    df["import_export_ratio"] = (imp / exp.replace(0, np.nan)).fillna(0)
    df["import_roll7"]        = imp.rolling(7, min_periods=1).mean()
    df["export_roll7"]        = exp.rolling(7, min_periods=1).mean()
    return df


def _vessel_mix_features(df: pd.DataFrame) -> pd.DataFrame:
    """Vessel type share as fraction of total portcalls."""
    total = df["portcalls"].replace(0, np.nan)
    for vtype in ["container", "tanker", "dry_bulk", "general_cargo", "roro"]:
        col = f"portcalls_{vtype}"
        if col in df.columns:
            df[f"{vtype}_share"] = (df[col] / total).fillna(0).clip(0, 1)
        else:
            df[f"{vtype}_share"] = 0.0
    return df


def _congestion_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Congestion score (0–100) based on z-score of portcalls relative to
    a 90-day rolling baseline. Congestion z-score also retained for
    downstream ML use.
    """
    roll_mean = df["portcalls"].rolling(90, min_periods=1).mean()
    roll_std  = df["portcalls"].rolling(90, min_periods=1).std().replace(0, np.nan)

    z = ((df["portcalls"] - roll_mean) / roll_std).fillna(0).clip(-3, 3)
    df["congestion_z"]     = z
    df["congestion_score"] = ((z + 3) / 6 * 100).round(2)
    df["traffic_level"]    = df["congestion_score"].apply(
        lambda x: "HIGH" if x >= 67 else ("MEDIUM" if x >= 33 else "LOW")
    )
    return df


if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from data_cleaning import load_and_clean, get_port_daily_series

    path = sys.argv[1] if len(sys.argv) > 1 else "portwatch_us_data.csv"
    df_clean = load_and_clean(path)

    port = "Los Angeles"
    daily = get_port_daily_series(df_clean, port)
    features = build_features(daily)

    print(f"\nFeature columns ({len(features.columns)}):")
    print(features[get_model_feature_cols()].tail(5).to_string())
