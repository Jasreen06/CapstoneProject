"""
portwatch.py
============
PortWatch data module for DockWise AI v2.
Pulls from IMF PortWatch ArcGIS FeatureServer.
Maintains in-memory DataFrames for US ports and global chokepoints.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
PORTS_CSV = os.path.join(_DIR, "portwatch_us_data.csv")
CHOKEPOINTS_CSV = os.path.join(_DIR, "chokepoint_data.csv")

PORTS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Ports_Data/FeatureServer/0/query"
)
CHOKEPOINTS_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Chokepoints_Data/FeatureServer/0/query"
)
CHOKEPOINTS_START = "2020-01-01"
PORTS_LOOKBACK_DAYS = 180


def _get_last_date(csv_path: str) -> str | None:
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, usecols=["date"])
            if not df.empty:
                return str(df["date"].max())
        except Exception:
            pass
    return None


def _paginated_fetch(base_url: str, where_clause: str, label: str = "records") -> list[dict]:
    all_features: list[dict] = []
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
        try:
            response = requests.get(base_url, params=params, timeout=30)
            data = response.json()
        except Exception as e:
            logger.error(f"PortWatch fetch error ({label}): {e}")
            break

        if "error" in data:
            logger.error(f"PortWatch API error ({label}): {data['error']}")
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


def _features_to_df(features: list[dict], convert_date_ms: bool = False) -> pd.DataFrame:
    if not features:
        return pd.DataFrame()
    df = pd.json_normalize([f["attributes"] for f in features])
    if convert_date_ms and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms").dt.strftime("%Y-%m-%d")
    return df


def _save_to_csv(df: pd.DataFrame, csv_path: str) -> None:
    if df.empty:
        return
    file_exists = os.path.exists(csv_path)
    df.to_csv(csv_path, mode="a", header=not file_exists, index=False)
    logger.info(f"Saved {len(df)} records → {csv_path}")


class PortWatchStore:
    """In-memory store for PortWatch port and chokepoint data."""

    def __init__(self) -> None:
        self.ports_df: pd.DataFrame | None = None
        self.chokepoints_df: pd.DataFrame | None = None
        self.last_updated: datetime | None = None
        self._lock = asyncio.Lock()

    async def load_data(self) -> None:
        """Load all port and chokepoint data. Fetches from API or falls back to CSV cache."""
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._sync_load)

    def _sync_load(self) -> None:
        self._load_ports()
        self._load_chokepoints()
        self.last_updated = datetime.now(timezone.utc)
        logger.info(
            f"PortWatch loaded: {len(self.ports_df) if self.ports_df is not None else 0} port rows, "
            f"{len(self.chokepoints_df) if self.chokepoints_df is not None else 0} chokepoint rows"
        )

    def _load_ports(self) -> None:
        last_date = _get_last_date(PORTS_CSV)
        if last_date:
            cutoff = (datetime.now() - timedelta(days=PORTS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            where = f"country = 'UNITED STATES' AND date > '{last_date}'"
        else:
            cutoff = (datetime.now() - timedelta(days=PORTS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            where = f"country = 'UNITED STATES' AND date >= '{cutoff}'"

        features = _paginated_fetch(PORTS_URL, where, label="ports")
        if features:
            df = _features_to_df(features)
            _save_to_csv(df, PORTS_CSV)

        # Load full CSV into memory
        if os.path.exists(PORTS_CSV):
            try:
                self.ports_df = pd.read_csv(PORTS_CSV)
                self.ports_df["date"] = pd.to_datetime(self.ports_df["date"])
                # Keep only last 180 days in memory
                cutoff_dt = datetime.now() - timedelta(days=180)
                self.ports_df = self.ports_df[self.ports_df["date"] >= cutoff_dt]
            except Exception as e:
                logger.error(f"Failed to load ports CSV: {e}")

    def _load_chokepoints(self) -> None:
        last_date = _get_last_date(CHOKEPOINTS_CSV)
        if last_date:
            where = f"date > '{last_date}'"
        else:
            where = f"date >= '{CHOKEPOINTS_START}'"

        features = _paginated_fetch(CHOKEPOINTS_URL, where, label="chokepoints")
        if features:
            df = _features_to_df(features, convert_date_ms=True)
            _save_to_csv(df, CHOKEPOINTS_CSV)

        if os.path.exists(CHOKEPOINTS_CSV):
            try:
                self.chokepoints_df = pd.read_csv(CHOKEPOINTS_CSV)
                self.chokepoints_df["date"] = pd.to_datetime(self.chokepoints_df["date"])
            except Exception as e:
                logger.error(f"Failed to load chokepoints CSV: {e}")

    async def refresh(self) -> None:
        """Incremental refresh — only fetches data since last loaded date."""
        await self.load_data()

    def get_port_names(self) -> list[str]:
        if self.ports_df is None or self.ports_df.empty:
            return []
        col = "portname" if "portname" in self.ports_df.columns else "port"
        return sorted(self.ports_df[col].dropna().unique().tolist())

    def _get_port_df(self, port_name: str) -> pd.DataFrame:
        if self.ports_df is None or self.ports_df.empty:
            return pd.DataFrame()
        col = "portname" if "portname" in self.ports_df.columns else "port"
        mask = self.ports_df[col].str.lower() == port_name.lower()
        return self.ports_df[mask].copy()

    def get_port_overview(self, port_name: str) -> dict[str, Any]:
        df = self._get_port_df(port_name)
        if df.empty:
            return {"error": f"Port '{port_name}' not found"}

        df = df.sort_values("date")
        portcalls_col = "portcalls" if "portcalls" in df.columns else "n_portcalls"
        if portcalls_col not in df.columns:
            portcalls_col = df.columns[df.columns.str.contains("portcall", case=False)][0] if any(df.columns.str.contains("portcall", case=False)) else None

        if not portcalls_col:
            return {"error": "No portcalls column found"}

        # Compute congestion score
        from analytics.congestion import compute_congestion_scores, get_congestion_level
        df_scored = compute_congestion_scores(df.rename(columns={portcalls_col: "portcalls"}))

        latest = df_scored.iloc[-1]
        recent_7 = df_scored.tail(7)

        trend = "stable"
        if len(df_scored) >= 14:
            prev_7_avg = df_scored.iloc[-14:-7]["portcalls"].mean()
            cur_7_avg = recent_7["portcalls"].mean()
            if cur_7_avg > prev_7_avg * 1.05:
                trend = "increasing"
            elif cur_7_avg < prev_7_avg * 0.95:
                trend = "decreasing"

        rolling_mean = df_scored["portcalls"].rolling(90, min_periods=1).mean().iloc[-1]
        pct_vs_normal = round(
            ((latest.get("portcalls", 0) - rolling_mean) / rolling_mean * 100) if rolling_mean else 0, 1
        )

        return {
            "port": port_name,
            "congestion_score": round(float(latest.get("congestion_score", 50)), 1),
            "congestion_level": latest.get("congestion_level", "MEDIUM"),
            "portcalls": int(latest.get("portcalls", 0)),
            "last_date": str(latest["date"])[:10] if "date" in latest else "",
            "trend": trend,
            "pct_vs_normal": pct_vs_normal,
            "recent_7_days": [
                {
                    "date": str(row["date"])[:10],
                    "portcalls": int(row.get("portcalls", 0)),
                    "congestion_score": round(float(row.get("congestion_score", 50)), 1),
                    "congestion_level": row.get("congestion_level", "MEDIUM"),
                }
                for _, row in recent_7.iterrows()
            ],
        }

    def get_top_ports(self, n: int = 20) -> list[dict[str, Any]]:
        if self.ports_df is None or self.ports_df.empty:
            return []

        from analytics.congestion import compute_congestion_scores
        port_col = "portname" if "portname" in self.ports_df.columns else "port"
        portcalls_col = "portcalls" if "portcalls" in self.ports_df.columns else "n_portcalls"

        if portcalls_col not in self.ports_df.columns:
            return []

        results = []
        for port_name in self.ports_df[port_col].dropna().unique():
            df = self.ports_df[self.ports_df[port_col] == port_name].copy()
            df = df.sort_values("date")
            if len(df) < 7:
                continue
            try:
                df_scored = compute_congestion_scores(df.rename(columns={portcalls_col: "portcalls"}))
                latest = df_scored.iloc[-1]
                results.append({
                    "port": port_name,
                    "congestion_score": round(float(latest.get("congestion_score", 50)), 1),
                    "congestion_level": latest.get("congestion_level", "MEDIUM"),
                    "portcalls": int(latest.get("portcalls", 0)),
                    "last_date": str(latest["date"])[:10] if "date" in latest else "",
                })
            except Exception:
                pass

        results.sort(key=lambda x: x["congestion_score"], reverse=True)
        return results[:n]

    def get_port_time_series(self, port_name: str) -> pd.DataFrame:
        """Return date/portcalls DataFrame for a port (for forecasting)."""
        df = self._get_port_df(port_name)
        if df.empty:
            return pd.DataFrame()
        portcalls_col = "portcalls" if "portcalls" in df.columns else "n_portcalls"
        if portcalls_col not in df.columns:
            return pd.DataFrame()
        df = df[["date", portcalls_col]].rename(columns={portcalls_col: "portcalls"})
        return df.sort_values("date").reset_index(drop=True)

    def get_chokepoints(self) -> list[dict[str, Any]]:
        if self.chokepoints_df is None or self.chokepoints_df.empty:
            return []

        from analytics.congestion import compute_congestion_scores

        results = []
        name_col = "portname" if "portname" in self.chokepoints_df.columns else "chokepoint"
        transit_col = next(
            (c for c in ["n_total", "portcalls", "n_portcalls"] if c in self.chokepoints_df.columns),
            None
        )
        if not transit_col:
            return []

        for name in self.chokepoints_df[name_col].dropna().unique():
            df = self.chokepoints_df[self.chokepoints_df[name_col] == name].copy()
            df = df.sort_values("date")
            if len(df) < 30:
                continue
            try:
                df_scored = compute_congestion_scores(df.rename(columns={transit_col: "portcalls"}))
                latest = df_scored.iloc[-1]
                avg_90 = df_scored.tail(90)["portcalls"].mean()
                results.append({
                    "name": name,
                    "disruption_score": round(float(latest.get("congestion_score", 50)), 1),
                    "disruption_level": latest.get("congestion_level", "MEDIUM"),
                    "transits_today": int(latest.get("portcalls", 0)),
                    "avg_90day": round(float(avg_90), 1),
                    "last_date": str(latest["date"])[:10] if "date" in latest else "",
                })
            except Exception:
                pass

        results.sort(key=lambda x: x["disruption_score"], reverse=True)
        return results

    def get_chokepoint(self, name: str) -> dict[str, Any]:
        if self.chokepoints_df is None or self.chokepoints_df.empty:
            return {"error": f"Chokepoint '{name}' not found"}

        name_col = "portname" if "portname" in self.chokepoints_df.columns else "chokepoint"
        transit_col = next(
            (c for c in ["n_total", "portcalls", "n_portcalls"] if c in self.chokepoints_df.columns),
            None
        )
        if not transit_col:
            return {"error": "No transit column found"}

        mask = self.chokepoints_df[name_col].str.lower() == name.lower()
        df = self.chokepoints_df[mask].copy().sort_values("date")

        if df.empty:
            return {"error": f"Chokepoint '{name}' not found"}

        from analytics.congestion import compute_congestion_scores
        try:
            df_scored = compute_congestion_scores(df.rename(columns={transit_col: "portcalls"}))
        except Exception:
            df_scored = df

        history = [
            {
                "date": str(row["date"])[:10],
                "transits": int(row.get(transit_col, 0)),
                "congestion_score": round(float(row.get("congestion_score", 50)), 1),
            }
            for _, row in df_scored.tail(90).iterrows()
        ]

        latest = df_scored.iloc[-1]
        return {
            "name": name,
            "disruption_score": round(float(latest.get("congestion_score", 50)), 1),
            "disruption_level": latest.get("congestion_level", "MEDIUM"),
            "transits_today": int(latest.get("portcalls", 0)),
            "history_90d": history,
        }


# Module-level singleton
portwatch_store = PortWatchStore()
