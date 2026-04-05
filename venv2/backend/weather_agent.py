"""
weather_agent.py
================
Weather Disruption Agent for DockWise AI.

Fetches current weather for a port and produces a weather_disruption_score (0-1)
with active warning labels for the Risk Orchestrator.

Score mapping:
    HIGH   → 0.80  (crane ops suspended, severe weather, critical visibility)
    MEDIUM → 0.40  (marginal crane ops, fog advisory, heavy rain)
    LOW    → 0.10  (normal conditions)
    +0.05 per additional active warning, capped at 1.0
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents import RiskState

logger = logging.getLogger(__name__)


def run(state: "RiskState") -> "RiskState":
    """
    Fetch current weather for the port and score operational disruption risk.

    Reads:  state["port"]
    Writes: weather_disruption_score, weather_risk_level,
            active_warnings, weather_summary
    """
    from weather import fetch_current_weather

    port = state["port"]
    logger.info(f"[WeatherAgent] Assessing weather for '{port}'")

    current = fetch_current_weather(port)

    if current is None:
        logger.warning(f"[WeatherAgent] No weather data available for '{port}'")
        return {
            **state,
            "weather_disruption_score": 0.0,
            "weather_risk_level":       "LOW",
            "active_warnings":          ["Weather data unavailable for this port"],
            "weather_summary":          "No weather data available.",
        }

    risk    = current.get("risk", {})
    level   = risk.get("level", "LOW")
    reasons = risk.get("reasons", [])

    # Base score by risk level
    base_score    = {"HIGH": 0.80, "MEDIUM": 0.40, "LOW": 0.10}.get(level, 0.10)
    # Boost for multiple simultaneous warnings
    warning_boost = min(len(reasons) * 0.05, 0.15)
    disruption_score = round(min(base_score + warning_boost, 1.0), 3)

    summary = (
        f"{current.get('weather_description', 'N/A')}, "
        f"Temp: {current.get('temp_c')}°C, "
        f"Wind: {current.get('wind_speed_ms')} m/s, "
        f"Visibility: {current.get('visibility_m')} m"
    )

    logger.info(
        f"[WeatherAgent] level={level}  score={disruption_score}  "
        f"warnings={reasons}"
    )

    return {
        **state,
        "weather_disruption_score": disruption_score,
        "weather_risk_level":       level,
        "active_warnings":          reasons,
        "weather_summary":          summary,
    }