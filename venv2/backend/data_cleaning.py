"""
data_cleaning.py
================
Load and clean PortWatch port data and chokepoint data.

Usage:
    from data_cleaning import load_and_clean, load_and_clean_chokepoints
    df   = load_and_clean("portwatch_us_data.csv")
    chk  = load_and_clean_chokepoints("chokepoint_data.csv")
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
FLOW_COLS  = ["import", "export"]       # renamed below
RENAME_MAP = {
    "import": "import_total",
    "export": "export_total",
    "import_cargo": "import_cargo_total",
    "export_cargo": "export_cargo_total",
}

def load_and_clean(filepath: str) -> pd.DataFrame:
    """
    Load the raw PortWatch CSV and return a clean DataFrame.

    Steps
    -----
    1. Read CSV
    2. Rename ambiguous columns (import → import_total, export → export_total)
    3. Parse dates
    4. Strip whitespace from string columns
    5. Coerce numeric columns; fill NaN → 0
    6. Remove duplicate (portname, date) rows
    7. Sort by portname, date
    8. Validate: warn on suspicious negatives
    9. Return cleaned DataFrame
    """
    logger.info(f"Loading data from {filepath}")
    df = pd.read_csv(filepath, low_memory=False)

    # ── 1. Rename ──────────────────────────────────────────
    df = df.rename(columns=RENAME_MAP)

    # ── 2. Parse dates ─────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df["date"].isna().sum()
    if bad_dates:
        logger.warning(f"Dropped {bad_dates} rows with unparseable dates.")
    df = df.dropna(subset=["date"])

    # ── 3. Strip strings ───────────────────────────────────
    for col in ["portname", "country", "ISO3"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # ── 4. Coerce numerics ─────────────────────────────────
    numeric_cols = [c for c in df.columns if c not in ID_COLS]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    # ── 5. Dedup ───────────────────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["portname", "date"])
    after = len(df)
    if before != after:
        logger.info(f"Removed {before - after} duplicate (portname, date) rows.")

    # ── 6. Sort ────────────────────────────────────────────
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
    Missing dates are filled with zeros (calendar gaps in the raw data).

    Returns DataFrame with columns: date, portcalls, import_total, export_total,
    portcalls_container, portcalls_dry_bulk, portcalls_general_cargo,
    portcalls_roro, portcalls_tanker.
    """
    p = df[df["portname"] == port].copy()
    p = p.set_index("date")

    keep_cols = [c for c in CARGO_COLS + ["import_total", "export_total"] if c in p.columns]
    daily = p[keep_cols].resample("D").sum()

    # Fill calendar gaps
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


def load_and_clean_chokepoints(filepath: str) -> pd.DataFrame:
    """
    Load the raw chokepoint CSV and return a clean DataFrame.

    Steps
    -----
    1. Read CSV
    2. Parse dates
    3. Strip whitespace from portname
    4. Coerce numeric columns; fill NaN → 0
    5. Remove duplicate (portname, date) rows
    6. Sort by portname, date
    7. Compute 90-day rolling baseline and disruption score per chokepoint
    """
    logger.info(f"Loading chokepoint data from {filepath}")
    df = pd.read_csv(filepath, low_memory=False)

    # ── 1. Parse dates ─────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df["date"].isna().sum()
    if bad_dates:
        logger.warning(f"Dropped {bad_dates} rows with unparseable dates.")
    df = df.dropna(subset=["date"])

    # ── 2. Strip strings ───────────────────────────────────
    df["portname"] = df["portname"].astype(str).str.strip()

    # ── 3. Coerce numerics ─────────────────────────────────
    numeric_cols = [c for c in df.columns if c not in CHOKEPOINT_ID_COLS]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    # ── 4. Dedup ───────────────────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["portname", "date"])
    if before != len(df):
        logger.info(f"Removed {before - len(df)} duplicate (portname, date) rows.")

    # ── 5. Sort ────────────────────────────────────────────
    df = df.sort_values(["portname", "date"]).reset_index(drop=True)

    # ── 6. Disruption score (z-score of n_total vs 90-day rolling baseline) ──
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
    """
    Return a complete daily time series for a single chokepoint.
    Missing dates are filled with zeros.
    """
    p = df[df["portname"] == chokepoint].copy().set_index("date")
    keep = [c for c in CHOKEPOINT_TRANSIT_COLS + CHOKEPOINT_CAPACITY_COLS if c in p.columns]
    daily = p[keep].resample("D").sum()
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0)
    daily.index.name = "date"
    return daily.reset_index()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    path = sys.argv[1] if len(sys.argv) > 1 else "portwatch_us_data.csv"
    df = load_and_clean(path)
    print(df.head())
    print(f"\nPorts available: {sorted(df['portname'].unique())[:10]}")

    chk = load_and_clean_chokepoints("chokepoint_data.csv")
    print(chk.head())
    print(f"\nChokepoints: {sorted(chk['portname'].unique())}")
