"""
seed_portwatch.py
=================
One-time full PortWatch data pull for DockWise AI v2.
Fetches last 365 days of US port data and chokepoint data.

Usage:
    cd CapstoneProject
    python scripts/seed_portwatch.py
"""

import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
except ImportError:
    pass

import requests
import pandas as pd

PORTS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Ports_Data/FeatureServer/0/query"
)
CHOKEPOINTS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Chokepoints_Data/FeatureServer/0/query"
)

_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "data")
PORTS_CSV = os.path.join(_DIR, "portwatch_us_data.csv")
CHOKEPOINTS_CSV = os.path.join(_DIR, "chokepoint_data.csv")


def paginated_fetch(base_url: str, where: str, label: str) -> list[dict]:
    all_features = []
    offset = 0
    batch = 2000

    while True:
        params = {
            "where": where,
            "outFields": "*",
            "outSR": 4326,
            "f": "json",
            "resultRecordCount": batch,
            "resultOffset": offset,
            "returnGeometry": False,
            "orderByFields": "year ASC, month ASC, day ASC",
            "resultType": "standard",
            "returnExceededLimitFeatures": True,
        }
        r = requests.get(base_url, params=params, timeout=30)
        data = r.json()
        if "error" in data:
            print(f"  API Error: {data['error']}")
            break
        features = data.get("features", [])
        if not features:
            break
        print(f"  [{label}] batch {offset//batch + 1}: {len(features)} records")
        all_features.extend(features)
        if len(features) < batch:
            break
        offset += batch
        time.sleep(0.3)

    return all_features


def save(features: list[dict], csv_path: str, convert_date_ms: bool = False) -> None:
    if not features:
        print("  No records to save.")
        return
    df = pd.json_normalize([f["attributes"] for f in features])
    if convert_date_ms and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms").dt.strftime("%Y-%m-%d")
    df.to_csv(csv_path, index=False)
    print(f"  Saved {len(df)} records → {csv_path}")


def seed_ports() -> None:
    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    where = f"country = 'UNITED STATES' AND date >= '{cutoff}'"
    print(f"\n[Ports] Fetching US port data from {cutoff}...")
    features = paginated_fetch(PORTS_URL, where, "ports")
    save(features, PORTS_CSV)


def seed_chokepoints() -> None:
    where = "date >= '2020-01-01'"
    print(f"\n[Chokepoints] Fetching global chokepoint data from 2020-01-01...")
    features = paginated_fetch(CHOKEPOINTS_URL, where, "chokepoints")
    save(features, CHOKEPOINTS_CSV, convert_date_ms=True)


if __name__ == "__main__":
    print("DockWise AI v2 — PortWatch Data Seed")
    print("=" * 40)
    seed_ports()
    seed_chokepoints()
    print("\nDone! Data saved to backend/data/")
