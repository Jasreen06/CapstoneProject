"""
weather.py
==========
Weather fetch + operational risk scoring for DockWise AI v2.
Uses OpenWeatherMap API with in-memory caching (15 min TTL).
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from config import WEATHER_API_KEY, PORT_COORDS

logger = logging.getLogger(__name__)

OWM_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast/daily"
OWM_FREE_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Risk thresholds
WIND_HIGH = 15.0       # m/s — crane ops marginal
WIND_EXTREME = 20.0    # m/s — crane ops suspended
VIS_LOW = 1000         # m — fog advisory
VIS_CRITICAL = 500     # m — vessel movement restricted
RAIN_HIGH = 10.0       # mm/h — bulk cargo affected

# Cache: port_name → {data, expires_at}
_cache: dict[str, dict[str, Any]] = {}
_CACHE_TTL_MINUTES = 15


def _weather_risk(current: dict) -> dict[str, Any]:
    reasons: list[str] = []
    level = "LOW"

    wind = current.get("wind_speed_ms", 0) or 0
    vis = current.get("visibility_m", 10000) or 10000
    rain = current.get("rain_1h", 0) or 0
    cond = current.get("weather_main", "").lower()

    if wind >= WIND_EXTREME:
        level = "HIGH"
        reasons.append(f"Extreme wind {wind:.1f} m/s — crane ops suspended")
    elif wind >= WIND_HIGH:
        level = "MEDIUM"
        reasons.append(f"Strong wind {wind:.1f} m/s — crane ops marginal")

    if vis <= VIS_CRITICAL:
        level = "HIGH"
        reasons.append(f"Critical visibility {vis}m — vessel movement restricted")
    elif vis <= VIS_LOW:
        if level == "LOW":
            level = "MEDIUM"
        reasons.append(f"Low visibility {vis}m — fog advisory")

    if rain >= RAIN_HIGH:
        if level == "LOW":
            level = "MEDIUM"
        reasons.append(f"Heavy rain {rain:.1f} mm/h — bulk cargo loading affected")

    if any(w in cond for w in ["thunderstorm", "tornado", "hurricane"]):
        level = "HIGH"
        reasons.append(f"Severe weather: {current.get('weather_description', cond)}")

    if not reasons:
        reasons.append("Conditions normal for port operations")

    return {"level": level, "reasons": reasons}


def _fetch_current(lat: float, lon: float) -> dict[str, Any] | None:
    if not WEATHER_API_KEY:
        return None
    try:
        r = requests.get(OWM_CURRENT_URL, params={
            "lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric",
        }, timeout=5)
        if r.status_code != 200:
            return None
        d = r.json()
        current: dict[str, Any] = {
            "temp_c": round(d["main"]["temp"], 1),
            "feels_like_c": round(d["main"]["feels_like"], 1),
            "humidity": d["main"]["humidity"],
            "pressure_hpa": d["main"]["pressure"],
            "wind_speed_ms": round(d["wind"]["speed"], 1),
            "wind_deg": d["wind"].get("deg", 0),
            "wind_gust_ms": round(d["wind"].get("gust", d["wind"]["speed"]), 1),
            "visibility_m": d.get("visibility", 10000),
            "weather_main": d["weather"][0]["main"],
            "weather_description": d["weather"][0]["description"].title(),
            "weather_icon": d["weather"][0]["icon"],
            "rain_1h": d.get("rain", {}).get("1h", 0),
            "clouds_pct": d["clouds"]["all"],
        }
        current["risk"] = _weather_risk(current)
        return current
    except Exception as e:
        logger.error(f"Weather current fetch error: {e}")
        return None


def _fetch_forecast(lat: float, lon: float, days: int = 5) -> list[dict[str, Any]]:
    if not WEATHER_API_KEY:
        return []
    try:
        r = requests.get(OWM_FORECAST_URL, params={
            "lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric", "cnt": days,
        }, timeout=5)
        if r.status_code == 200:
            return _parse_daily_forecast(r.json())
    except Exception:
        pass

    # Fallback to free 5-day/3h
    try:
        r = requests.get(OWM_FREE_URL, params={
            "lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric", "cnt": 40,
        }, timeout=5)
        if r.status_code == 200:
            return _parse_3h_to_daily(r.json(), days)
    except Exception as e:
        logger.error(f"Forecast fetch error: {e}")
    return []


def _parse_daily_forecast(data: dict) -> list[dict[str, Any]]:
    result = []
    for d in data.get("list", []):
        result.append({
            "date": datetime.fromtimestamp(d["dt"], tz=timezone.utc).strftime("%Y-%m-%d"),
            "temp_max_c": round(d["temp"]["max"], 1),
            "temp_min_c": round(d["temp"]["min"], 1),
            "wind_speed_ms": round(d.get("speed", 0), 1),
            "wind_gust_ms": round(d.get("gust", d.get("speed", 0)), 1),
            "rain_mm": round(d.get("rain", 0), 1),
            "pop": round(d.get("pop", 0) * 100),
            "weather_main": d["weather"][0]["main"],
            "weather_icon": d["weather"][0]["icon"],
            "weather_description": d["weather"][0]["description"].title(),
            "risk_level": _weather_risk({
                "wind_speed_ms": d.get("speed", 0),
                "visibility_m": 10000,
                "rain_1h": d.get("rain", 0) / 24,
                "weather_main": d["weather"][0]["main"],
                "weather_description": d["weather"][0]["description"],
            })["level"],
        })
    return result


def _parse_3h_to_daily(data: dict, days: int) -> list[dict[str, Any]]:
    from collections import defaultdict
    buckets: dict[str, list] = defaultdict(list)
    for item in data.get("list", []):
        day = datetime.fromtimestamp(item["dt"], tz=timezone.utc).strftime("%Y-%m-%d")
        buckets[day].append(item)

    result = []
    for day in sorted(buckets)[:days]:
        items = buckets[day]
        winds = [i["wind"]["speed"] for i in items]
        gusts = [i["wind"].get("gust", i["wind"]["speed"]) for i in items]
        temps = [i["main"]["temp"] for i in items]
        rains = [i.get("rain", {}).get("3h", 0) for i in items]
        pops = [i.get("pop", 0) for i in items]
        mid = items[len(items) // 2]
        max_wind = max(winds)
        result.append({
            "date": day,
            "temp_max_c": round(max(temps), 1),
            "temp_min_c": round(min(temps), 1),
            "wind_speed_ms": round(max_wind, 1),
            "wind_gust_ms": round(max(gusts), 1),
            "rain_mm": round(sum(rains), 1),
            "pop": round(max(pops) * 100),
            "weather_main": mid["weather"][0]["main"],
            "weather_icon": mid["weather"][0]["icon"],
            "weather_description": mid["weather"][0]["description"].title(),
            "risk_level": _weather_risk({
                "wind_speed_ms": max_wind,
                "visibility_m": 10000,
                "rain_1h": sum(rains) / 24,
                "weather_main": mid["weather"][0]["main"],
                "weather_description": mid["weather"][0]["description"],
            })["level"],
        })
    return result


async def fetch_weather_for_port(port_name: str) -> dict[str, Any]:
    """Fetch weather for a named port with 15-minute cache."""
    now = datetime.now(timezone.utc)

    # Check cache
    cached = _cache.get(port_name)
    if cached and cached.get("expires_at") and now < cached["expires_at"]:
        return cached["data"]

    coords = PORT_COORDS.get(port_name)
    if not coords:
        return {"error": f"Unknown port: {port_name}", "risk_level": "UNKNOWN"}

    lat, lon = coords

    loop = asyncio.get_event_loop()
    current = await loop.run_in_executor(None, _fetch_current, lat, lon)
    forecast = await loop.run_in_executor(None, _fetch_forecast, lat, lon, 5)

    result: dict[str, Any] = {
        "port": port_name,
        "current": current,
        "forecast": forecast,
        "risk_level": current["risk"]["level"] if current else "UNKNOWN",
        "risk_reasons": current["risk"]["reasons"] if current else [],
        "fetched_at": now.isoformat(),
    }

    _cache[port_name] = {
        "data": result,
        "expires_at": now + timedelta(minutes=_CACHE_TTL_MINUTES),
    }
    return result
