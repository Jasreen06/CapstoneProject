import requests
import pandas as pd
import time
import os

# Resolve paths relative to this script's directory so data_pull.py
# works correctly regardless of which directory it is run from.
_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Ports (US) ────────────────────────────────────────────────────────────────
PORTS_URL      = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query"
PORTS_CSV      = os.path.join(_DIR, "portwatch_us_data.csv")

# ── Chokepoints (global) ──────────────────────────────────────────────────────
CHOKEPOINTS_URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
CHOKEPOINTS_CSV = os.path.join(_DIR, "chokepoint_data.csv")
CHOKEPOINTS_START = "2017-01-01"   # pre-COVID baseline


# ── Shared helpers ─────────────────────────────────────────────────────────────

def get_last_date(csv_path):
    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path, usecols=["date"])
        if not existing.empty:
            return existing["date"].max()
    return None


def _paginated_fetch(base_url, where_clause, label="records"):
    """Generic paginated ArcGIS fetch. Returns list of raw feature dicts."""
    all_features = []
    offset = 0
    batch_size = 2000

    while True:
        params = {
            "where": where_clause,
            "outFields": "*",
            "outSR": 4326,
            "f": "json",
            "resultRecordCount": batch_size,
            "resultOffset": offset,
            "returnGeometry": False,
            "orderByFields": "year ASC, month ASC, day ASC",
            "resultType": "standard",
            "returnExceededLimitFeatures": True,
        }

        response = requests.get(base_url, params=params)
        data = response.json()

        if "error" in data:
            print(f"  API Error ({label}):", data["error"])
            break

        features = data.get("features", [])
        if not features:
            break

        print(f"  [{label}] fetched {len(features)} records (offset: {offset})")
        all_features.extend(features)

        if len(features) < batch_size:
            break

        offset += batch_size
        time.sleep(0.2)

    return all_features


def _save(features, csv_path, convert_date_ms=False):
    if not features:
        print("  No new records — already up to date.")
        return
    df = pd.json_normalize([f["attributes"] for f in features])
    if convert_date_ms and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms").dt.strftime("%Y-%m-%d")
    file_exists = os.path.exists(csv_path)
    df.to_csv(csv_path, mode="a", header=not file_exists, index=False)
    print(f"  Saved {len(df)} records → {csv_path}")


# ── Port data (US, incremental) ───────────────────────────────────────────────

def run_ports():
    last_date = get_last_date(PORTS_CSV)

    if last_date:
        where = f"country = 'UNITED STATES' AND date > '{last_date}'"
        print(f"\n[Ports] Fetching records after {last_date}...")
    else:
        where = "country = 'UNITED STATES'"
        print("\n[Ports] No existing data — fetching full history...")

    features = _paginated_fetch(PORTS_URL, where, label="ports")
    _save(features, PORTS_CSV)


# ── Chokepoint data (global, incremental from 2017) ───────────────────────────

def run_chokepoints():
    last_date = get_last_date(CHOKEPOINTS_CSV)

    if last_date:
        where = f"date > '{last_date}'"
        print(f"\n[Chokepoints] Fetching records after {last_date}...")
    else:
        where = f"date >= '{CHOKEPOINTS_START}'"
        print(f"\n[Chokepoints] No existing data — fetching from {CHOKEPOINTS_START}...")

    features = _paginated_fetch(CHOKEPOINTS_URL, where, label="chokepoints")
    _save(features, CHOKEPOINTS_CSV, convert_date_ms=True)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_ports()
    run_chokepoints()
