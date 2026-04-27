"""
data_cleaning.py
================
Load and clean PortWatch port data and chokepoint data from Supabase DB.
"""

from __future__ import annotations
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Column definitions
# ──────────────────────────────────────────────
ID_COLS = ["date", "year", "month", "day", "portid", "portname", "country", "ISO3", "ObjectId"]
CARGO_COLS = [
    "portcalls",
    "portcalls_container",
    "portcalls_dry_bulk",
    "portcalls_general_cargo",
    "portcalls_roro",
    "portcalls_tanker",
]
RENAME_MAP = {
    "import":        "import_total",
    "export":        "export_total",
    "import_cargo":  "import_cargo_total",
    "export_cargo":  "export_cargo_total",
}


def _has_database() -> bool:
    import os
    return bool(os.getenv("DATABASE_URL", ""))


def load_and_clean(filepath: str = None) -> pd.DataFrame:
    """
    Load port data from Supabase DB when DATABASE_URL is set,
    otherwise fall back to local CSV file.
    """
    if _has_database():
        logger.info("Loading port data from database")
        from db import get_engine
        engine = get_engine()
        df = pd.read_sql("SELECT * FROM port_data", engine)
    else:
        from pathlib import Path
        csv_path = filepath or str(Path(__file__).parent / "portwatch_us_data.csv")
        logger.info(f"Loading port data from CSV: {csv_path}")
        df = pd.read_csv(csv_path)

    # ── Rename columns ─────────────────────────────────────────────────────
    df = df.rename(columns=RENAME_MAP)

    # ── Parse dates ─────────────────────────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    # ── Strip strings ────────────────────────────────────────────────────────
    for col in ["portname", "country", "ISO3"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # ── Coerce numerics ──────────────────────────────────────────────────────
    numeric_cols = [c for c in df.columns if c not in ID_COLS]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    # ── Dedup ────────────────────────────────────────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["portname", "date"])
    if before != len(df):
        logger.info(f"Removed {before - len(df)} duplicate rows.")

    # ── Sort ─────────────────────────────────────────────────────────────────
    df = df.sort_values(["portname", "date"]).reset_index(drop=True)

    logger.info(
        f"Cleaned: {len(df):,} rows | "
        f"{df['portname'].nunique()} ports | "
        f"{df['date'].min().date()} → {df['date'].max().date()}"
    )
    return df


def get_port_daily_series(df: pd.DataFrame, port: str) -> pd.DataFrame:
    """
    Return a complete daily time series for a single port.
    Missing dates are filled with zeros.
    """
    p = df[df["portname"] == port].copy()
    p = p.set_index("date")

    keep_cols = [c for c in CARGO_COLS + ["import_total", "export_total"] if c in p.columns]
    daily = p[keep_cols].resample("D").sum()

    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0)
    daily.index.name = "date"
    return daily.reset_index()


# ──────────────────────────────────────────────
# Chokepoint column definitions
# ──────────────────────────────────────────────
CHOKEPOINT_ID_COLS = ["date", "year", "month", "day", "portid", "portname", "ObjectId"]
CHOKEPOINT_TRANSIT_COLS = [
    "n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker",
    "n_cargo", "n_total",
]
CHOKEPOINT_CAPACITY_COLS = [
    "capacity_container", "capacity_dry_bulk", "capacity_general_cargo",
    "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity",
]


def load_and_clean_chokepoints(filepath: str = None) -> pd.DataFrame:
    """
    Load chokepoint data from Supabase DB when DATABASE_URL is set,
    otherwise fall back to local CSV file.
    """
    if _has_database():
        logger.info("Loading chokepoint data from database")
        from db import get_engine
        engine = get_engine()
        df = pd.read_sql("SELECT * FROM chokepoint_data", engine)
    else:
        from pathlib import Path
        csv_path = filepath or str(Path(__file__).parent / "chokepoint_data.csv")
        logger.info(f"Loading chokepoint data from CSV: {csv_path}")
        df = pd.read_csv(csv_path, on_bad_lines="skip")

    # ── Parse dates ─────────────────────────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    # ── Strip strings ────────────────────────────────────────────────────────
    df["portname"] = df["portname"].astype(str).str.strip()

    # ── Coerce numerics ──────────────────────────────────────────────────────
    numeric_cols = [c for c in df.columns if c not in CHOKEPOINT_ID_COLS]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    # ── Dedup ────────────────────────────────────────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["portname", "date"])
    if before != len(df):
        logger.info(f"Removed {before - len(df)} duplicate rows.")

    # ── Sort ─────────────────────────────────────────────────────────────────
    df = df.sort_values(["portname", "date"]).reset_index(drop=True)

    # ── Disruption score (z-score of n_total vs 90-day rolling baseline) ────
    def _disruption_series(s: pd.Series) -> pd.Series:
        rolling_mean = s.rolling(90, min_periods=1).mean()
        rolling_std  = s.rolling(90, min_periods=1).std().replace(0, np.nan)
        z = ((s - rolling_mean) / rolling_std).fillna(0).clip(-3, 3)
        return ((z + 3) / 6 * 100).round(1)

    df["disruption_score"] = (
        df.groupby("portname")["n_total"].transform(_disruption_series)
    )
    df["disruption_level"] = df["disruption_score"].apply(
        lambda x: "HIGH" if x >= 67 else ("MEDIUM" if x >= 33 else "LOW")
    )

    logger.info(
        f"Cleaned chokepoints: {len(df):,} rows | "
        f"{df['portname'].nunique()} chokepoints | "
        f"{df['date'].min().date()} → {df['date'].max().date()}"
    )
    return df


def get_chokepoint_daily_series(df: pd.DataFrame, chokepoint: str) -> pd.DataFrame:
    """Return a complete daily time series for a single chokepoint."""
    p = df[df["portname"] == chokepoint].copy().set_index("date")
    keep = [c for c in CHOKEPOINT_TRANSIT_COLS + CHOKEPOINT_CAPACITY_COLS if c in p.columns]
    daily = p[keep].resample("D").sum()
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0)
    daily.index.name = "date"
    return daily.reset_index()
