"""
backfill_missing_ports.py
=========================
Upload historical data for ports missing from Supabase DB.
Reads from the local CSV and inserts only the ports not already in the DB.

Usage:
    DATABASE_URL=... python3 backfill_missing_ports.py
"""
from __future__ import annotations
import os
import logging
import warnings
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CSV_FILE = "portwatch_us_data.csv"
BATCH_SIZE = 5000


def main():
    from db import get_engine
    engine = get_engine()

    # Get ports already in DB
    with engine.connect() as conn:
        db_ports = set(
            r[0] for r in conn.execute(text("SELECT DISTINCT portname FROM port_data")).fetchall()
        )
    logger.info(f"Ports already in DB: {len(db_ports)}")

    # Load CSV
    logger.info(f"Loading CSV: {CSV_FILE}")
    df = pd.read_csv(CSV_FILE, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    csv_ports = set(df["portname"].dropna().str.strip().unique())
    missing = sorted(csv_ports - db_ports)
    logger.info(f"Ports in CSV but missing from DB ({len(missing)}): {missing}")

    if not missing:
        logger.info("Nothing to backfill — DB already has all ports.")
        return

    # Filter to missing ports only
    to_insert = df[df["portname"].isin(missing)].copy()
    logger.info(f"Rows to insert: {len(to_insert):,}")

    # Map CSV columns to DB columns (CSV uses import/export not renamed)
    col_map = {
        "import":        "import",
        "export":        "export",
        "import_cargo":  "import_cargo",
        "export_cargo":  "export_cargo",
    }

    # Keep only columns that exist in both CSV and DB
    db_cols = [
        "portname","date","portcalls","portcalls_container","portcalls_dry_bulk",
        "portcalls_general_cargo","portcalls_roro","portcalls_tanker",
        "import","export","import_cargo","export_cargo",
        "portid","country","ISO3","year","month","day",
        "portcalls_cargo","import_container","import_dry_bulk",
        "import_general_cargo","import_roro","import_tanker",
        "export_container","export_dry_bulk","export_general_cargo",
        "export_roro","export_tanker","ObjectId",
    ]
    available_cols = [c for c in db_cols if c in to_insert.columns]
    to_insert = to_insert[available_cols].copy()

    # Convert date to string for insertion
    to_insert["date"] = to_insert["date"].dt.strftime("%Y-%m-%d")

    # Insert in batches
    total = len(to_insert)
    inserted = 0
    with engine.begin() as conn:
        for i in range(0, total, BATCH_SIZE):
            batch = to_insert.iloc[i:i+BATCH_SIZE]
            records = batch.where(pd.notnull(batch), None).to_dict("records")
            if not records:
                continue
            cols = list(records[0].keys())
            placeholders = ", ".join([f":{c}" for c in cols])
            col_names = ", ".join([f'"{c}"' for c in cols])
            sql = text(
                f"INSERT INTO port_data ({col_names}) VALUES ({placeholders}) "
                f"ON CONFLICT DO NOTHING"
            )
            conn.execute(sql, records)
            inserted += len(batch)
            logger.info(f"  Inserted {inserted:,}/{total:,} rows...")

    logger.info(f"Backfill complete — {inserted:,} rows inserted for {len(missing)} ports.")

    # Verify
    with engine.connect() as conn:
        new_count = conn.execute(text("SELECT COUNT(DISTINCT portname) FROM port_data")).scalar()
        logger.info(f"DB now has {new_count} distinct ports.")


if __name__ == "__main__":
    main()
