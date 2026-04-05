"""
weather.py
==========
Fetch current weather and 7-day forecast from OpenWeatherMap for US ports.
Provides weather risk scoring relevant to port operations.
"""

from __future__ import annotations
import os
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

OWM_CURRENT_URL  = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast/daily"
OWM_FREE_URL     = "https://api.openweathermap.org/data/2.5/forecast"  # fallback 5-day/3h

def _api_key() -> str:
    return os.getenv("WEATHER_API_KEY", "")

# ── Port coordinates (lat, lon) ──────────────────────────────────────────────
PORT_COORDS: dict[str, tuple[float, float]] = {
    # West Coast
    "Los Angeles-Long Beach": (33.75,  -118.22),
    "Oakland":                (37.80,  -122.27),
    "Seattle":                (47.60,  -122.34),
    "Tacoma":                 (47.27,  -122.41),
    "San Diego":              (32.71,  -117.17),
    "San Francisco":          (37.79,  -122.39),
    "Port Hueneme":           (34.15,  -119.20),
    "EL Segundo":             (33.92,  -118.42),
    "Richmond, CA":           (37.92,  -122.38),
    "Benicia":                (38.05,  -122.16),
    "Stockton":               (37.96,  -121.29),
    "Portland, OR":           (45.52,  -122.68),
    "Longview":               (46.14,  -122.93),
    "Vancouver":              (45.62,  -122.67),
    "Kalama":                 (46.01,  -122.84),
    "Anacortes":              (48.51,  -122.61),
    "Everett":                (47.97,  -122.20),
    "Bellingham":             (48.74,  -122.49),
    "Aberdeen":               (46.97,  -123.82),
    "Cherry Point":           (48.86,  -122.75),
    # Alaska / Hawaii
    "Anchorage (Alaska)":     (61.22,  -149.90),
    "Dutch Harbor":           (53.89,  -166.54),
    "Kodiak":                 (57.80,  -152.41),
    "Nikiski":                (60.68,  -151.38),
    "Honolulu":               (21.31,  -157.87),
    "Hilo":                   (19.73,  -155.09),
    "Barbor's Point":         (21.32,  -158.12),
    # Gulf Coast
    "Houston":                (29.75,   -95.08),
    "South Louisiana":        (29.95,   -90.36),
    "New Orleans":            (29.95,   -90.06),
    "Baton Rouge":            (30.44,   -91.19),
    "Beaumont":               (30.08,   -94.10),
    "Port Arthur":            (29.88,   -93.93),
    "Corpus Christi":         (27.80,   -97.40),
    "Freeport":               (28.95,   -95.36),
    "Galveston":              (29.30,   -94.80),
    "Texas City":             (29.39,   -94.90),
    "Sabine Pass":            (29.73,   -93.87),
    "Lake Charles":           (30.22,   -93.21),
    "Gulfport":               (30.37,   -89.09),
    "Pascagoula":             (30.35,   -88.56),
    "Mobile":                 (30.69,   -88.04),
    "Panama City":            (30.16,   -85.66),
    "Pensacola":              (30.42,   -87.22),
    "Tampa":                  (27.94,   -82.45),
    "Port Manatee":           (27.64,   -82.56),
    "Fourchon":               (29.11,   -90.20),
    "Plaquemines":            (29.37,   -89.82),
    "Port Lavaca":            (28.62,   -96.63),
    "Port Aransas":           (27.83,   -97.05),
    "Brownsville":            (25.93,   -97.49),
    "Monroe":                 (29.95,   -90.06),
    # East Coast
    "New York-New Jersey":    (40.68,   -74.04),
    "Philadelphia":           (39.87,   -75.14),
    "Baltimore":              (39.27,   -76.58),
    "Norfolk":                (36.85,   -76.30),
    "Port of Virginia":       (36.93,   -76.33),
    "Newport News":           (37.00,   -76.43),
    "Savannah":               (32.08,   -81.09),
    "Charleston":             (32.78,   -79.94),
    "Jacksonville":           (30.33,   -81.66),
    "Miami":                  (25.77,   -80.19),
    "Palm Beach":             (26.72,   -80.05),
    "Port Everglades":        (26.09,   -80.12),
    "Canaveral Harbor":       (28.41,   -80.59),
    "Wilmington, NC":         (34.24,   -77.95),
    "Morehead City":          (34.72,   -76.73),
    "Fernandina":             (30.67,   -81.46),
    "Brunswick":              (31.15,   -81.49),
    "Key West":               (24.56,   -81.78),
    "Boston":                 (42.36,   -71.05),
    "Providence":             (41.82,   -71.40),
    "New Haven":              (41.31,   -72.92),
    "Bridgeport":             (41.18,   -73.19),
    "New Bedford":            (41.63,   -70.93),
    "Fall River":             (41.70,   -71.16),
    "Davisville Depot":       (41.60,   -71.40),
    "Albany":                 (42.65,   -73.75),
    "Portland, ME":           (43.66,   -70.25),
    "Searsport":              (44.47,   -68.92),
    "Salem":                  (42.52,   -70.90),
    "Portmouth":              (43.07,   -70.76),
    "Marcus Hook":            (39.82,   -75.41),
    "Chester":                (39.85,   -75.36),
    "Delaware":               (39.74,   -75.55),
    "Wilmington, DE":         (39.74,   -75.55),
    "Fairless Hills":         (40.18,   -74.86),
    "Sydney":                 (42.36,   -71.05),
    "Dominion Cove Point":    (38.39,   -76.38),
    # Great Lakes
    "Chicago":                (41.85,   -87.65),
    "Detroit":                (42.33,   -83.05),
    "Cleveland":              (41.51,   -81.69),
    "Toledo":                 (41.66,   -83.55),
    "Gary":                   (41.60,   -87.35),
    "Duluth":                 (46.78,   -92.10),
    "Milwaukee":              (43.04,   -87.91),
    "Indiana Harbor":         (41.66,   -87.44),
    "Ashtabula":              (41.90,   -80.79),
    "Burns Harbor":           (41.62,   -87.13),
    "Buffington":             (41.63,   -87.42),
    "Calumet Harbor":         (41.73,   -87.53),
    "Sandusky":               (41.45,   -82.72),
    "Presque Isle":           (42.13,   -80.08),
    "Erie":                   (42.13,   -80.08),
    "Muskegon":               (43.23,   -86.26),
    "Grand Haven":            (43.06,   -86.23),
    "Green Bay":              (44.52,   -88.02),
    "Manitowoc":              (44.09,   -87.66),
    "Menominee":              (45.11,   -87.62),
    "Two Harbors":            (47.02,   -91.67),
    "Conneaut":               (41.96,   -80.56),
    "Fairport":               (41.76,   -81.28),
    "Bay City":               (43.59,   -83.88),
    "Swanport":               (42.63,   -82.88),
    "Empire":                 (44.81,   -86.06),
    "Manchester":             (41.77,   -72.52),
    "Rodeo":                  (38.03,   -122.26),
    "United States - Offshore Oil Terminal 1": (28.95, -88.97),
}

# ── Weather risk thresholds (port operations) ────────────────────────────────
WIND_HIGH    = 15.0   # m/s ≈ 33 mph — crane operations marginal
WIND_EXTREME = 20.0   # m/s ≈ 45 mph — crane operations suspended
VIS_LOW      = 1000   # metres — fog advisory
VIS_CRITICAL = 500    # metres — vessel movement restricted
RAIN_HIGH    = 10.0   # mm/h — heavy rain affecting bulk cargo loading


def _get_coords(port: str) -> tuple[float, float] | None:
    return PORT_COORDS.get(port)


def _wind_beaufort(speed_ms: float) -> str:
    if speed_ms < 5.5:   return "Light"
    if speed_ms < 10.8:  return "Moderate"
    if speed_ms < 17.2:  return "Strong"
    if speed_ms < 24.5:  return "Gale"
    return "Storm"


def _weather_risk(current: dict) -> dict:
    """Score operational risk from current weather conditions."""
    reasons = []
    level   = "LOW"

    wind = current.get("wind_speed_ms", 0) or 0
    vis  = current.get("visibility_m", 10000) or 10000
    rain = current.get("rain_1h", 0) or 0
    cond = current.get("weather_main", "").lower()

    if wind >= WIND_EXTREME:
        level = "HIGH"; reasons.append(f"Extreme wind {wind:.1f} m/s — crane ops suspended")
    elif wind >= WIND_HIGH:
        level = "MEDIUM"; reasons.append(f"Strong wind {wind:.1f} m/s — crane ops marginal")

    if vis <= VIS_CRITICAL:
        level = "HIGH"; reasons.append(f"Critical visibility {vis}m — vessel movement restricted")
    elif vis <= VIS_LOW:
        if level == "LOW": level = "MEDIUM"
        reasons.append(f"Low visibility {vis}m — fog advisory")

    if rain >= RAIN_HIGH:
        if level == "LOW": level = "MEDIUM"
        reasons.append(f"Heavy rain {rain:.1f} mm/h — bulk cargo loading affected")

    if any(w in cond for w in ["thunderstorm", "tornado", "hurricane"]):
        level = "HIGH"; reasons.append(f"Severe weather: {current.get('weather_description', cond)}")

    if not reasons:
        reasons.append("Conditions normal for port operations")

    return {"level": level, "reasons": reasons}


def fetch_current_weather(port: str) -> dict | None:
    """Fetch current weather for a port. Returns None if unavailable."""
    coords = _get_coords(port)
    key = _api_key()
    if not coords or not key:
        return None
    lat, lon = coords
    try:
        r = requests.get(OWM_CURRENT_URL, params={
            "lat": lat, "lon": lon,
            "appid": key,
            "units": "metric",
        }, timeout=5)
        if r.status_code != 200:
            logger.warning(f"Weather API {r.status_code} for {port}")
            return None
        d = r.json()
        current = {
            "port":                port,
            "temp_c":              round(d["main"]["temp"], 1),
            "feels_like_c":        round(d["main"]["feels_like"], 1),
            "humidity":            d["main"]["humidity"],
            "pressure_hpa":        d["main"]["pressure"],
            "wind_speed_ms":       round(d["wind"]["speed"], 1),
            "wind_deg":            d["wind"].get("deg", 0),
            "wind_gust_ms":        round(d["wind"].get("gust", d["wind"]["speed"]), 1),
            "wind_beaufort":       _wind_beaufort(d["wind"]["speed"]),
            "visibility_m":        d.get("visibility", 10000),
            "weather_main":        d["weather"][0]["main"],
            "weather_description": d["weather"][0]["description"].title(),
            "weather_icon":        d["weather"][0]["icon"],
            "rain_1h":             d.get("rain", {}).get("1h", 0),
            "snow_1h":             d.get("snow", {}).get("1h", 0),
            "clouds_pct":          d["clouds"]["all"],
            "dt":                  d["dt"],
        }
        current["risk"] = _weather_risk(current)
        return current
    except Exception as e:
        logger.error(f"Weather fetch error for {port}: {e}")
        return None


def fetch_weather_forecast(port: str, days: int = 7) -> list[dict]:
    """Fetch daily weather forecast for a port (up to 7 days)."""
    coords = _get_coords(port)
    key = _api_key()
    if not coords or not key:
        return []
    lat, lon = coords

    # Try 16-day daily forecast first (paid), fall back to 5-day/3h (free)
    try:
        r = requests.get(OWM_FORECAST_URL, params={
            "lat": lat, "lon": lon,
            "appid": key,
            "units": "metric",
            "cnt": days,
        }, timeout=5)
        if r.status_code == 200:
            return _parse_daily_forecast(r.json())
    except Exception:
        pass

    # Fallback: 5-day/3h forecast, aggregate to daily
    try:
        r = requests.get(OWM_FREE_URL, params={
            "lat": lat, "lon": lon,
            "appid": key,
            "units": "metric",
            "cnt": 40,
        }, timeout=5)
        if r.status_code == 200:
            return _parse_3h_to_daily(r.json(), days)
    except Exception as e:
        logger.error(f"Forecast fetch error for {port}: {e}")

    return []


def _parse_daily_forecast(data: dict) -> list[dict]:
    result = []
    for d in data.get("list", []):
        result.append({
            "date":         datetime.fromtimestamp(d["dt"], tz=timezone.utc).strftime("%Y-%m-%d"),
            "temp_max_c":   round(d["temp"]["max"], 1),
            "temp_min_c":   round(d["temp"]["min"], 1),
            "wind_speed_ms":round(d.get("speed", 0), 1),
            "wind_gust_ms": round(d.get("gust", d.get("speed", 0)), 1),
            "rain_mm":      round(d.get("rain", 0), 1),
            "snow_mm":      round(d.get("snow", 0), 1),
            "pop":          round(d.get("pop", 0) * 100),
            "clouds_pct":   d.get("clouds", 0),
            "humidity":     d.get("humidity", 0),
            "weather_main": d["weather"][0]["main"],
            "weather_icon": d["weather"][0]["icon"],
            "weather_description": d["weather"][0]["description"].title(),
            "wind_beaufort": _wind_beaufort(d.get("speed", 0)),
            "risk_level":   _weather_risk({
                "wind_speed_ms": d.get("speed", 0),
                "visibility_m":  10000,
                "rain_1h":       d.get("rain", 0) / 24,
                "weather_main":  d["weather"][0]["main"],
                "weather_description": d["weather"][0]["description"],
            })["level"],
        })
    return result


def _parse_3h_to_daily(data: dict, days: int) -> list[dict]:
    """Aggregate 3-hour intervals into daily summaries."""
    from collections import defaultdict
    buckets: dict[str, list] = defaultdict(list)
    for item in data.get("list", []):
        day = datetime.fromtimestamp(item["dt"], tz=timezone.utc).strftime("%Y-%m-%d")
        buckets[day].append(item)

    result = []
    for day in sorted(buckets)[:days]:
        items = buckets[day]
        winds  = [i["wind"]["speed"] for i in items]
        gusts  = [i["wind"].get("gust", i["wind"]["speed"]) for i in items]
        temps  = [i["main"]["temp"] for i in items]
        rains  = [i.get("rain", {}).get("3h", 0) for i in items]
        pops   = [i.get("pop", 0) for i in items]
        mid    = items[len(items) // 2]
        max_wind = max(winds)
        result.append({
            "date":          day,
            "temp_max_c":    round(max(temps), 1),
            "temp_min_c":    round(min(temps), 1),
            "wind_speed_ms": round(max_wind, 1),
            "wind_gust_ms":  round(max(gusts), 1),
            "rain_mm":       round(sum(rains), 1),
            "snow_mm":       0.0,
            "pop":           round(max(pops) * 100),
            "clouds_pct":    mid["clouds"]["all"],
            "humidity":      mid["main"]["humidity"],
            "weather_main":  mid["weather"][0]["main"],
            "weather_icon":  mid["weather"][0]["icon"],
            "weather_description": mid["weather"][0]["description"].title(),
            "wind_beaufort": _wind_beaufort(max_wind),
            "risk_level":    _weather_risk({
                "wind_speed_ms": max_wind,
                "visibility_m":  10000,
                "rain_1h":       sum(rains) / 24,
                "weather_main":  mid["weather"][0]["main"],
                "weather_description": mid["weather"][0]["description"],
            })["level"],
        })
    return result
