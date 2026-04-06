"""
congestion.py
=============
Z-score based congestion scoring for DockWise AI v2.
Normalized to 0-100. Thresholds: LOW <34, MEDIUM 34-66, HIGH >66.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def get_congestion_level(score: float) -> str:
    if score >= 67:
        return "HIGH"
    elif score >= 34:
        return "MEDIUM"
    return "LOW"


def compute_congestion_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 90-day rolling z-score congestion scores.

    Input: DataFrame with columns [date, portcalls] (and optionally port/portname).
    Output: same DataFrame with added columns: congestion_score, congestion_level.
    """
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)
    df["portcalls"] = pd.to_numeric(df["portcalls"], errors="coerce").fillna(0).clip(lower=0)

    rolling_mean = df["portcalls"].rolling(90, min_periods=1).mean()
    rolling_std = df["portcalls"].rolling(90, min_periods=1).std().fillna(1).replace(0, 1)

    z = ((df["portcalls"] - rolling_mean) / rolling_std).clip(-3, 3)
    scores = (z + 3) / 6 * 100

    df["congestion_score"] = scores.round(1)
    df["congestion_level"] = df["congestion_score"].apply(get_congestion_level)

    return df
