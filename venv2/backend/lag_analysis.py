"""
lag_analysis.py
===============
Empirically derives the lag (in days) between chokepoint disruptions
and US port congestion using cross-correlation on IMF PortWatch data.

Run:
    python lag_analysis.py

Output:
    - Console table: port cluster × chokepoint → peak lag + correlation
    - lag_analysis_results.csv: full results for every pair tested
"""

from __future__ import annotations
import warnings
warnings.filterwarnings("ignore")

import os
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ── Coast classification (mirrors api.py keywords) ────────────────────────────
WEST_PORTS = {
    "Los Angeles-Long Beach", "Oakland", "Seattle", "Tacoma", "San Diego",
    "San Francisco", "Port Hueneme", "Richmond, CA", "Portland, OR",
    "Anacortes", "Bellingham", "Aberdeen", "Cherry Point",
}
GULF_PORTS = {
    "Houston", "New Orleans", "South Louisiana", "Baton Rouge", "Beaumont",
    "Port Arthur", "Corpus Christi", "Freeport", "Galveston", "Texas City",
    "Lake Charles", "Gulfport", "Pascagoula", "Mobile", "Tampa",
    "Port Manatee", "Port Lavaca", "Port Aransas", "Brownsville", "Panama City",
}
LAKES_PORTS = {
    "Chicago", "Detroit", "Cleveland", "Toledo", "Gary", "Duluth",
    "Milwaukee", "Indiana Harbor", "Bay City", "Buffington", "Calumet Harbor",
    "Sandusky", "Presque Isle", "Manitowoc", "Menominee",
}
# Everything else → East Coast
EAST_PORTS = {
    "New York-New Jersey", "Philadelphia", "Baltimore", "Norfolk",
    "Newport News", "Savannah", "Charleston", "Jacksonville", "Miami",
    "Palm Beach", "Port Everglades", "Wilmington, NC", "Morehead City",
    "Boston", "Providence", "New Haven", "Bridgeport", "New Bedford",
    "Portland, ME", "Searsport", "Portmouth", "Brunswick",
}

def classify_port(name: str) -> str:
    if name in WEST_PORTS:  return "West Coast"
    if name in GULF_PORTS:  return "Gulf Coast"
    if name in LAKES_PORTS: return "Great Lakes"
    return "East Coast"


# ── Chokepoints relevant to each coast ───────────────────────────────────────
# Based on shipping lane geography. We test these pairs specifically.
COAST_CHOKEPOINTS = {
    "West Coast":  ["Malacca Strait", "Taiwan Strait", "Panama Canal", "Luzon Strait"],
    "East Coast":  ["Suez Canal", "Bab el-Mandeb Strait", "Panama Canal", "Gibraltar Strait"],
    "Gulf Coast":  ["Strait of Hormuz", "Panama Canal", "Yucatan Channel", "Bab el-Mandeb Strait"],
    "Great Lakes": ["Panama Canal", "Suez Canal"],
}

# All chokepoints — also run a full sweep so we don't miss surprises
ALL_CHOKEPOINTS = [
    "Suez Canal", "Panama Canal", "Bab el-Mandeb Strait", "Malacca Strait",
    "Strait of Hormuz", "Taiwan Strait", "Gibraltar Strait", "Dover Strait",
    "Luzon Strait", "Lombok Strait", "Yucatan Channel",
]

LAG_RANGE = range(7, 57, 7)   # test 1 to 8 weeks in weekly steps


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_port_data() -> pd.DataFrame:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        from db import get_engine
        engine = get_engine()
        df = pd.read_sql("SELECT portname, date, portcalls FROM port_data", engine)
        df["date"] = pd.to_datetime(df["date"])
        return df
    csv = os.path.join(os.path.dirname(__file__), "portwatch_us_data.csv")
    df = pd.read_csv(csv, low_memory=False, parse_dates=["date"])
    return df[["portname", "date", "portcalls"]]


def load_chokepoint_data() -> pd.DataFrame:
    csv = os.path.join(os.path.dirname(__file__), "chokepoint_data.csv")
    df = pd.read_csv(csv, low_memory=False, parse_dates=["date"])
    return df[["portname", "date", "n_total"]].rename(
        columns={"portname": "chokepoint", "n_total": "transits"}
    )


# ── Signal preparation ────────────────────────────────────────────────────────

def weekly_zscore(series: pd.Series) -> pd.Series:
    """Resample to weekly sum, then z-score normalise."""
    weekly = series.resample("W").sum()
    mu, sd = weekly.mean(), weekly.std()
    if sd < 1e-6:
        return pd.Series(dtype=float)
    return (weekly - mu) / sd


def build_port_signals(port_df: pd.DataFrame) -> dict[str, pd.Series]:
    """Returns {portname: weekly_zscore_series}."""
    signals = {}
    for name, grp in port_df.groupby("portname"):
        s = grp.set_index("date")["portcalls"].sort_index()
        s = pd.to_numeric(s, errors="coerce").fillna(0)
        z = weekly_zscore(s)
        if len(z) >= 52:   # need at least 1 year of weekly data
            signals[name] = z
    return signals


def build_chokepoint_signals(chk_df: pd.DataFrame) -> dict[str, pd.Series]:
    """Returns {chokepoint_name: weekly_zscore_series}."""
    signals = {}
    for name, grp in chk_df.groupby("chokepoint"):
        if name not in ALL_CHOKEPOINTS:
            continue
        s = grp.set_index("date")["transits"].sort_index()
        s = pd.to_numeric(s, errors="coerce").fillna(0)
        z = weekly_zscore(s)
        if len(z) >= 52:
            signals[name] = z
    return signals


# ── Cross-correlation at each lag ─────────────────────────────────────────────

def cross_corr_at_lag(chk_signal: pd.Series, port_signal: pd.Series, lag_days: int) -> float:
    """
    Shift chokepoint signal forward by lag_days, align with port signal,
    return Pearson correlation. Returns NaN if insufficient overlap.
    """
    lag_weeks = lag_days // 7
    shifted = chk_signal.shift(lag_weeks)
    aligned = pd.concat([shifted, port_signal], axis=1, join="inner").dropna()
    if len(aligned) < 20:
        return float("nan")
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def analyse_pair(chk_name: str, chk_sig: pd.Series,
                 port_name: str, port_sig: pd.Series) -> dict:
    corrs = {lag: cross_corr_at_lag(chk_sig, port_sig, lag) for lag in LAG_RANGE}
    valid = {lag: c for lag, c in corrs.items() if not np.isnan(c)}
    if not valid:
        return None

    # Negative correlations are the causal signal:
    # chokepoint transits DOWN → port congestion UP after the lag.
    # Prefer the strongest negative lag; fall back to strongest absolute if none exist.
    neg_valid = {lag: c for lag, c in valid.items() if c < 0}
    if neg_valid:
        peak_lag  = min(neg_valid, key=lambda l: neg_valid[l])   # most negative
        signal    = "disruption"   # causal: blockage → congestion
    else:
        peak_lag  = max(valid, key=lambda l: abs(valid[l]))
        signal    = "seasonal"     # shared seasonal co-movement only

    peak_corr = valid[peak_lag]
    return {
        "port":          port_name,
        "coast":         classify_port(port_name),
        "chokepoint":    chk_name,
        "peak_lag_days": peak_lag,
        "peak_corr":     round(peak_corr, 4),
        "direction":     "negative" if peak_corr < 0 else "positive",
        "signal_type":   signal,   # disruption (meaningful) vs seasonal (noise)
        "all_corrs":     {lag: round(c, 4) for lag, c in valid.items()},
    }


# ── Cluster-level summary (average across ports in a coast) ──────────────────

def coast_summary(results: list[dict]) -> pd.DataFrame:
    rows = []
    for coast, chokepoints in COAST_CHOKEPOINTS.items():
        for chk in chokepoints:
            all_pairs = [r for r in results
                         if r["coast"] == coast and r["chokepoint"] == chk]
            # Only use disruption-signal pairs for lag estimation
            disrupt = [r for r in all_pairs if r["signal_type"] == "disruption"]
            if not all_pairs:
                continue
            lags  = [r["peak_lag_days"] for r in disrupt] if disrupt else []
            corrs = [abs(r["peak_corr"])  for r in disrupt] if disrupt else []
            rows.append({
                "coast":             coast,
                "chokepoint":        chk,
                "total_ports":       len(all_pairs),
                "disruption_ports":  len(disrupt),
                "median_lag_days":   int(np.median(lags))  if lags  else "n/a",
                "mean_abs_corr":     round(np.mean(corrs), 4) if corrs else "n/a",
                "hardcoded_lag":     _hardcoded_lag(coast, chk),
            })
    return pd.DataFrame(rows)


def _hardcoded_lag(coast: str, chk: str) -> str:
    table = {
        ("East Coast",  "Suez Canal"):           "~28 days",
        ("East Coast",  "Bab el-Mandeb Strait"):  "~28 days",
        ("East Coast",  "Panama Canal"):          "~7-14 days",
        ("West Coast",  "Malacca Strait"):        "~14-18 days",
        ("West Coast",  "Taiwan Strait"):         "~14-18 days",
        ("West Coast",  "Panama Canal"):          "~7 days",
        ("Gulf Coast",  "Strait of Hormuz"):      "unknown",
        ("Gulf Coast",  "Panama Canal"):          "~7-14 days",
        ("Great Lakes", "Panama Canal"):          "unknown",
    }
    return table.get((coast, chk), "unknown")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading port data...")
    port_df = load_port_data()
    print(f"  {len(port_df):,} rows, {port_df['portname'].nunique()} ports")

    print("Loading chokepoint data...")
    chk_df = load_chokepoint_data()
    print(f"  {len(chk_df):,} rows, {chk_df['chokepoint'].nunique()} chokepoints")

    print("Building weekly signals...")
    port_signals = build_port_signals(port_df)
    chk_signals  = build_chokepoint_signals(chk_df)
    print(f"  {len(port_signals)} port signals, {len(chk_signals)} chokepoint signals")

    print(f"\nRunning cross-correlation (lags: {list(LAG_RANGE)} days)...")
    results = []
    total = sum(
        len([p for p in port_signals if classify_port(p) == coast])
        for coast, chks in COAST_CHOKEPOINTS.items()
        for _ in chks
    )
    done = 0
    for coast, chokepoints in COAST_CHOKEPOINTS.items():
        coast_ports = [p for p in port_signals if classify_port(p) == coast]
        for chk in chokepoints:
            if chk not in chk_signals:
                continue
            chk_sig = chk_signals[chk]
            for port in coast_ports:
                r = analyse_pair(chk, chk_sig, port, port_signals[port])
                if r:
                    results.append(r)
                done += 1
                if done % 20 == 0:
                    print(f"  {done}/{total} pairs analysed...", end="\r")

    print(f"\nAnalysed {len(results)} port-chokepoint pairs.")

    # ── Per-pair CSV ──────────────────────────────────────────────────────────
    flat = [
        {k: v for k, v in r.items() if k != "all_corrs"}
        for r in results
    ]
    pair_df = pd.DataFrame(flat).sort_values(
        ["coast", "chokepoint", "signal_type", "peak_corr"]
    )
    pair_df.to_csv("lag_analysis_results.csv", index=False)
    print("\nSaved: lag_analysis_results.csv")

    # ── Coast-level summary ───────────────────────────────────────────────────
    summary = coast_summary(results)

    print("\n" + "=" * 80)
    print("COAST × CHOKEPOINT SUMMARY")
    print("median_peak_lag = empirically derived from your data")
    print("hardcoded_lag   = what llm.py currently tells the LLM")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print("DISRUPTION SIGNAL: strongest negative correlations")
    print("(chokepoint blockage -> port congestion rises after lag)")
    print("=" * 80)
    disruption = pair_df[pair_df["signal_type"] == "disruption"]
    top_neg = disruption.nsmallest(10, "peak_corr")
    print(top_neg[["port", "coast", "chokepoint", "peak_lag_days", "peak_corr"]].to_string(index=False))

    print("\n" + "=" * 80)
    print("SEASONAL ONLY: pairs with NO negative correlation found")
    print("(chokepoint has no detectable disruption effect on this port)")
    print("=" * 80)
    seasonal = pair_df[pair_df["signal_type"] == "seasonal"]
    print(seasonal[["port", "coast", "chokepoint", "peak_lag_days", "peak_corr"]].to_string(index=False))

    print("\n" + "=" * 80)
    print(f"SIGNAL TYPE SUMMARY: {len(disruption)} disruption pairs, {len(seasonal)} seasonal-only pairs")
    print("=" * 80)

    print("\nDone. Full results in lag_analysis_results.csv")


if __name__ == "__main__":
    main()
