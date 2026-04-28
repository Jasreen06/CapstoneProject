"""
db.py
=====
Supabase / PostgreSQL connection helper.

Set DATABASE_URL in your .env or Render environment variables:
  postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres
"""

from __future__ import annotations
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)


def get_engine():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable not set")
    # Render provides postgres:// but SQLAlchemy requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def init_tables(engine=None):
    """Create all tables if they don't exist. Safe to call on every startup."""
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS port_data (
                portname TEXT NOT NULL,
                date     DATE NOT NULL,
                portcalls               FLOAT DEFAULT 0,
                portcalls_container     FLOAT DEFAULT 0,
                portcalls_dry_bulk      FLOAT DEFAULT 0,
                portcalls_general_cargo FLOAT DEFAULT 0,
                portcalls_roro          FLOAT DEFAULT 0,
                portcalls_tanker        FLOAT DEFAULT 0,
                import                  FLOAT DEFAULT 0,
                export                  FLOAT DEFAULT 0,
                import_cargo            FLOAT DEFAULT 0,
                export_cargo            FLOAT DEFAULT 0,
                PRIMARY KEY (portname, date)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chokepoint_data (
                portname TEXT NOT NULL,
                date     DATE NOT NULL,
                n_total               FLOAT DEFAULT 0,
                n_container           FLOAT DEFAULT 0,
                n_dry_bulk            FLOAT DEFAULT 0,
                n_general_cargo       FLOAT DEFAULT 0,
                n_roro                FLOAT DEFAULT 0,
                n_tanker              FLOAT DEFAULT 0,
                n_cargo               FLOAT DEFAULT 0,
                capacity              FLOAT DEFAULT 0,
                capacity_container    FLOAT DEFAULT 0,
                capacity_dry_bulk     FLOAT DEFAULT 0,
                capacity_general_cargo FLOAT DEFAULT 0,
                capacity_roro         FLOAT DEFAULT 0,
                capacity_tanker       FLOAT DEFAULT 0,
                capacity_cargo        FLOAT DEFAULT 0,
                PRIMARY KEY (portname, date)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS forecast_log (
                id             SERIAL PRIMARY KEY,
                logged_at      TIMESTAMP,
                port           TEXT,
                model          TEXT,
                target_date    DATE,
                yhat           FLOAT,
                yhat_lower     FLOAT,
                yhat_upper     FLOAT,
                actual         FLOAT,
                error          FLOAT,
                within_interval BOOLEAN,
                validated_at   TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS model_comparison_results (
                id         SERIAL PRIMARY KEY,
                saved_at   TIMESTAMP DEFAULT now(),
                results    JSONB NOT NULL
            )
        """))
        conn.commit()
    logger.info("DB tables verified/created.")


def upsert_ignore(table_name: str, df, engine=None, conflict_cols=("portname", "date")):
    """Insert rows, silently ignoring conflicts on (portname, date)."""
    if engine is None:
        engine = get_engine()
    if df.empty:
        return
    from sqlalchemy import Table, MetaData
    meta = MetaData()
    meta.reflect(bind=engine, only=[table_name])
    tbl = meta.tables[table_name]
    # Only keep columns that exist in the table — ArcGIS may return extras
    valid_cols = {c.name for c in tbl.columns}
    df = df[[c for c in df.columns if c in valid_cols]]
    dialect = engine.dialect.name
    # SQLite can't bind pandas Timestamps — convert date to string
    if dialect == "sqlite" and "date" in df.columns:
        df = df.copy()
        df["date"] = df["date"].astype(str)
    records = df.to_dict("records")
    with engine.connect() as conn:
        if dialect == "sqlite":
            from sqlalchemy import text
            cols = [c for c in df.columns]
            placeholders = ", ".join([f":{c}" for c in cols])
            col_names = ", ".join(cols)
            sql = f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})"
            conn.execute(text(sql), records)
        else:
            stmt = pg_insert(tbl).values(records).on_conflict_do_nothing(
                index_elements=list(conflict_cols)
            )
            conn.execute(stmt)
        conn.commit()
