import requests
import pandas as pd
import time
import os
import logging

logger = logging.getLogger(__name__)

# ── ArcGIS endpoints ──────────────────────────────────────────────────────────
PORTS_URL       = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query"
CHOKEPOINTS_URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
CHOKEPOINTS_START = "2017-01-01"


# ── Shared helpers ─────────────────────────────────────────────────────────────

def get_last_date(table_name: str) -> str | None:
    """Return the latest date stored in the given DB table, or None if empty."""
    try:
        from db import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text(f"SELECT MAX(date) FROM {table_name}"))
            val = result.scalar()
            return str(val) if val else None
    except Exception as e:
        logger.warning(f"Could not read last date from {table_name}: {e}")
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

        response = requests.get(base_url, params=params, timeout=30)
        data = response.json()

        if "error" in data:
            logger.error(f"API error ({label}): {data['error']}")
            break

        features = data.get("features", [])
        if not features:
            break

        logger.info(f"[{label}] fetched {len(features)} records (offset: {offset})")
        all_features.extend(features)

        if len(features) < batch_size:
            break

        offset += batch_size
        time.sleep(0.2)

    return all_features


def _save(features, table_name: str, convert_date_ms=False):
    """Save fetched records to the Supabase DB table, ignoring duplicates."""
    if not features:
        logger.info("No new records — already up to date.")
        return

    df = pd.json_normalize([f["attributes"] for f in features])

    if convert_date_ms and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms").dt.strftime("%Y-%m-%d")

    # Coerce date to proper type
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    try:
        from db import get_engine, upsert_ignore
        engine = get_engine()
        upsert_ignore(table_name, df, engine=engine)
        logger.info(f"Saved {len(df)} records → {table_name}")
    except Exception as e:
        logger.error(f"DB save failed for {table_name}: {e}")
        raise


# ── Port data (US, incremental) ───────────────────────────────────────────────

def run_ports():
    last_date = get_last_date("port_data")

    if last_date:
        where = f"country = 'UNITED STATES' AND date > '{last_date}'"
        logger.info(f"[Ports] Fetching records after {last_date}...")
    else:
        where = "country = 'UNITED STATES'"
        logger.info("[Ports] No existing data — fetching full history...")

    features = _paginated_fetch(PORTS_URL, where, label="ports")
    _save(features, "port_data")


# ── Chokepoint data (global, incremental from 2017) ───────────────────────────

def run_chokepoints():
    last_date = get_last_date("chokepoint_data")

    if last_date:
        where = f"date > '{last_date}'"
        logger.info(f"[Chokepoints] Fetching records after {last_date}...")
    else:
        where = f"date >= '{CHOKEPOINTS_START}'"
        logger.info(f"[Chokepoints] No existing data — fetching from {CHOKEPOINTS_START}...")

    features = _paginated_fetch(CHOKEPOINTS_URL, where, label="chokepoints")
    _save(features, "chokepoint_data", convert_date_ms=True)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db import init_tables
    init_tables()
    run_ports()
    run_chokepoints()
