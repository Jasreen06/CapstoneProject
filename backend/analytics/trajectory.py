"""
trajectory.py
=============
Dead reckoning trajectory prediction for DockWise AI v2.
Uses great circle math (no external geo libraries).
"""

from __future__ import annotations
import math
from datetime import datetime, timezone, timedelta
from typing import Any

from config import PORT_COORDS

EARTH_RADIUS_NM = 3440.065  # nautical miles
SLOW_DOWN_NM = 20           # slow to approach speed within this distance
APPROACH_SPEED_KN = 6.0     # knots when within SLOW_DOWN_NM of destination


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in nautical miles between two lat/lon points."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def _initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing (degrees 0-360) from point 1 to point 2."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlon = rlon2 - rlon1
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _move_position(lat: float, lon: float, bearing_deg: float, distance_nm: float) -> tuple[float, float]:
    """Move from (lat, lon) by distance_nm nautical miles along bearing_deg."""
    d = distance_nm / EARTH_RADIUS_NM  # angular distance in radians
    b = math.radians(bearing_deg)
    rlat = math.radians(lat)
    rlon = math.radians(lon)

    new_lat = math.asin(
        math.sin(rlat) * math.cos(d) + math.cos(rlat) * math.sin(d) * math.cos(b)
    )
    new_lon = rlon + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(rlat),
        math.cos(d) - math.sin(rlat) * math.sin(new_lat),
    )
    return math.degrees(new_lat), math.degrees(new_lon)


def _heading_diff(cog: float, bearing: float) -> float:
    """Signed difference between COG and target bearing (-180 to 180)."""
    diff = (bearing - cog + 180) % 360 - 180
    return diff


def predict_trajectory(
    lat: float,
    lon: float,
    sog_knots: float,
    cog_degrees: float,
    rate_of_turn: float = 0,
    destination_port: str | None = None,
    hours: int = 72,
) -> list[dict[str, Any]]:
    """
    Predict vessel positions at 1-hour intervals for the next `hours` hours.

    Returns list of {lat, lon, timestamp, hours_from_now}.
    """
    if sog_knots <= 0:
        sog_knots = 0.1

    dest_coords = None
    if destination_port:
        dest_coords = PORT_COORDS.get(destination_port)

    now = datetime.now(timezone.utc)
    positions = []
    cur_lat, cur_lon = lat, lon
    cur_cog = cog_degrees

    for h in range(1, hours + 1):
        if dest_coords:
            dest_lat, dest_lon = dest_coords
            dist_to_dest = _haversine_nm(cur_lat, cur_lon, dest_lat, dest_lon)

            if dist_to_dest < 1.0:
                # Arrived at destination — stop here
                break

            bearing = _initial_bearing(cur_lat, cur_lon, dest_lat, dest_lon)
            # Gradually turn toward destination bearing
            diff = _heading_diff(cur_cog, bearing)
            turn_rate = min(abs(diff), 10)  # max 10 deg/hour turn
            cur_cog = (cur_cog + math.copysign(turn_rate, diff)) % 360

            # Slow down near port
            speed = APPROACH_SPEED_KN if dist_to_dest <= SLOW_DOWN_NM else sog_knots
        else:
            speed = sog_knots
            # Apply rate of turn (degrees per minute → degrees per hour)
            if rate_of_turn and abs(rate_of_turn) < 127:
                cur_cog = (cur_cog + rate_of_turn * 60) % 360

        distance_nm = speed * 1.0  # 1 hour
        cur_lat, cur_lon = _move_position(cur_lat, cur_lon, cur_cog, distance_nm)

        positions.append({
            "lat": round(cur_lat, 5),
            "lon": round(cur_lon, 5),
            "timestamp": (now + timedelta(hours=h)).isoformat(),
            "hours_from_now": h,
        })

    return positions


def estimate_eta(
    lat: float,
    lon: float,
    sog_knots: float,
    destination_port: str,
) -> float | None:
    """
    Estimate hours until vessel reaches destination port.
    Returns None if destination unknown or vessel stationary.
    """
    dest_coords = PORT_COORDS.get(destination_port)
    if not dest_coords or sog_knots <= 0:
        return None

    dest_lat, dest_lon = dest_coords
    distance_nm = _haversine_nm(lat, lon, dest_lat, dest_lon)

    # Assume average speed is slightly less than current due to slowdown near port
    avg_speed = sog_knots * 0.9
    if avg_speed <= 0:
        return None

    return round(distance_nm / avg_speed, 1)
