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
SAVE_BATCH_SIZE = 5000


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


def _get_oid_range(base_url, where_clause, label="records"):
    """Get min/max ObjectId for the query — used to drive cursor pagination."""
    import json as _json
    params = {
        "where": where_clause,
        "outStatistics": _json.dumps([
            {"statisticType": "min", "onStatisticField": "ObjectId", "outStatisticFieldName": "min_oid"},
            {"statisticType": "max", "onStatisticField": "ObjectId", "outStatisticFieldName": "max_oid"},
        ]),
        "f": "json",
    }
    r = requests.get(base_url, params=params, timeout=60)
    data = r.json()
    attrs = data.get("features", [{}])[0].get("attributes", {})
    min_oid = attrs.get("min_oid")
    max_oid = attrs.get("max_oid")
    if min_oid is None or max_oid is None:
        logger.warning(f"[{label}] Could not get OID range — falling back to offset pagination")
        return None, None
    logger.info(f"[{label}] OID range: {min_oid} → {max_oid} ({max_oid - min_oid + 1} rows)")
    return int(min_oid), int(max_oid)


def _fetch_with_retry(base_url, params, label, context=""):
    """Fetch one page with retry on empty/timeout."""
    for attempt in range(4):
        try:
            response = requests.get(base_url, params=params, timeout=90)
            if response.text.strip():
                return response.json()
            wait = 10 * (attempt + 1)
            logger.warning(f"[{label}] Empty response {context}attempt {attempt + 1}/4, retrying in {wait}s...")
            time.sleep(wait)
        except requests.exceptions.Timeout:
            wait = 5 * (attempt + 1)
            logger.warning(f"[{label}] Timeout {context}attempt {attempt + 1}/4, retrying in {wait}s...")
            if attempt == 3:
                raise
            time.sleep(wait)
    return None


def _paginated_fetch(base_url, where_clause, label="records"):
    """Paginate via ObjectId ranges to avoid ArcGIS offset limits (~150k rows)."""
    batch_size = 2000
    all_features = []

    min_oid, max_oid = _get_oid_range(base_url, where_clause, label)

    if min_oid is None:
        # Fallback: offset pagination (works for small datasets)
        offset = 0
        while True:
            params = {
                "where": where_clause,
                "outFields": "*",
                "f": "json",
                "resultRecordCount": batch_size,
                "resultOffset": offset,
                "returnGeometry": False,
            }
            data = _fetch_with_retry(base_url, params, label, f"offset={offset} ")
            if not data:
                break
            features = data.get("features", [])
            if not features:
                break
            all_features.extend(features)
            logger.info(f"[{label}] fetched {len(all_features)} records (offset={offset})")
            if len(features) < batch_size:
                break
            offset += batch_size
            time.sleep(0.3)
        return all_features

    # ObjectId cursor pagination — no offset limit
    current = min_oid
    while current <= max_oid:
        end = current + batch_size - 1
        oid_filter = f"ObjectId >= {current} AND ObjectId <= {end}"
        combined = f"({where_clause}) AND {oid_filter}" if where_clause.strip().lower() != "1=1" else oid_filter

        params = {
            "where": combined,
            "outFields": "*",
            "f": "json",
            "returnGeometry": False,
        }
        data = _fetch_with_retry(base_url, params, label, f"OID {current}-{end} ")
        if data and "features" in data:
            features = data["features"]
            all_features.extend(features)
            if features:
                logger.info(f"[{label}] fetched {len(all_features)} total (OID {current}–{end})")

        current += batch_size
        time.sleep(0.2)

    return all_features


def _save_batch(features, table_name: str, convert_date_ms=False):
    """Save a batch of records to Supabase, ignoring duplicates."""
    if not features:
        return 0

    df = pd.json_normalize([f["attributes"] for f in features])

    if convert_date_ms and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms").dt.strftime("%Y-%m-%d")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    from db import get_engine, upsert_ignore
    engine = get_engine()
    upsert_ignore(table_name, df, engine=engine)
    return len(df)


def _save(features, table_name: str, convert_date_ms=False):
    """Save records to Supabase in batches to avoid timeouts."""
    if not features:
        logger.info("No new records — already up to date.")
        return

    total = 0
    for i in range(0, len(features), SAVE_BATCH_SIZE):
        batch = features[i:i + SAVE_BATCH_SIZE]
        try:
            saved = _save_batch(batch, table_name, convert_date_ms)
            total += saved
            logger.info(f"Saved {total}/{len(features)} records → {table_name}")
        except Exception as e:
            logger.error(f"DB save failed at offset {i} for {table_name}: {e}")
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
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    from dotenv import load_dotenv
    load_dotenv()
    from db import init_tables
    init_tables()
    run_ports()
    run_chokepoints()
