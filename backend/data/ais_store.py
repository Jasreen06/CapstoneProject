"""
ais_store.py
============
Thread-safe in-memory store for latest vessel positions.
Keyed by MMSI. Merges position reports and static data.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any


class VesselStore:
    """Thread-safe in-memory store for latest vessel positions."""

    def __init__(self) -> None:
        self._vessels: dict[int, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def update_position(self, mmsi: int, data: dict[str, Any]) -> None:
        async with self._lock:
            existing = self._vessels.get(mmsi, {})
            existing.update(data)
            existing["mmsi"] = mmsi
            existing["last_update"] = datetime.now(timezone.utc).isoformat()
            self._vessels[mmsi] = existing

    async def update_static(self, mmsi: int, data: dict[str, Any]) -> None:
        async with self._lock:
            existing = self._vessels.get(mmsi, {})
            existing.update(data)
            existing["mmsi"] = mmsi
            self._vessels[mmsi] = existing

    async def get_all_vessels(self) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._vessels.values())

    async def get_vessel(self, mmsi: int) -> dict[str, Any] | None:
        async with self._lock:
            return self._vessels.get(mmsi)

    async def get_vessels_in_bbox(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                v for v in self._vessels.values()
                if (
                    "lat" in v and "lon" in v
                    and lat_min <= v["lat"] <= lat_max
                    and lon_min <= v["lon"] <= lon_max
                )
            ]

    async def get_vessels_by_destination(self, port_name: str) -> list[dict[str, Any]]:
        target = port_name.lower()
        async with self._lock:
            return [
                v for v in self._vessels.values()
                if target in (v.get("destination") or "").lower()
            ]

    async def get_vessel_count(self) -> int:
        async with self._lock:
            return len(self._vessels)

    async def cleanup_stale(self, max_age_minutes: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        removed = 0
        async with self._lock:
            stale_keys = []
            for mmsi, vessel in self._vessels.items():
                last_update = vessel.get("last_update")
                if last_update:
                    try:
                        dt = datetime.fromisoformat(last_update)
                        if dt < cutoff:
                            stale_keys.append(mmsi)
                    except (ValueError, TypeError):
                        pass
            for k in stale_keys:
                del self._vessels[k]
            removed = len(stale_keys)
        return removed

    def get_stats(self) -> dict[str, Any]:
        """Return synchronous stats (call from non-async context after lock is free)."""
        vessels = list(self._vessels.values())
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for v in vessels:
            t = v.get("vessel_type_label", "Unknown")
            by_type[t] = by_type.get(t, 0) + 1
            s = v.get("nav_status_label", "Unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": len(vessels),
            "by_type": by_type,
            "by_nav_status": by_status,
        }


# Module-level singleton
vessel_store = VesselStore()
