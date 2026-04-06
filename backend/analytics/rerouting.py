"""
rerouting.py
============
Congestion-aware vessel rerouting engine for DockWise AI v2.
Evaluates whether a vessel should reroute to an alternative port.
"""

from __future__ import annotations
import math
from typing import Any

from config import PORT_COORDS, PORT_DEPTHS_METERS, get_alternative_ports, resolve_port_name
from analytics.trajectory import _haversine_nm


def _draught_compatible(vessel_draught: float, port: str) -> bool:
    min_depth = PORT_DEPTHS_METERS.get(port, 12.0)
    return vessel_draught <= min_depth


def _vessel_type_compatible(vessel_type: int, port: str) -> bool:
    """
    Simple type compatibility check.
    All major ports support cargo and container vessels.
    Tankers need specific terminals — for simplicity, allow all major ports.
    """
    return True


def _get_recommendation(
    dest_level: str,
    alt_level: str,
    alt_dist_additional: float,
) -> str:
    if dest_level == "HIGH" and alt_level == "LOW":
        return "STRONG"
    elif dest_level == "HIGH" and alt_level == "MEDIUM":
        return "MODERATE"
    elif dest_level == "MEDIUM" and alt_level == "LOW" and alt_dist_additional < 500:
        return "WEAK"
    return "NONE"


def evaluate_rerouting(
    vessel: dict[str, Any],
    trajectory: list[dict[str, Any]],
    destination_congestion: dict[str, Any],
    destination_weather: dict[str, Any],
    alternative_ports: list[str],
    alternatives_congestion: dict[str, dict[str, Any]] | None = None,
    alternatives_weather: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Evaluate whether a vessel should reroute to an alternative port.

    Returns a structured rerouting recommendation dict.
    """
    if alternatives_congestion is None:
        alternatives_congestion = {}
    if alternatives_weather is None:
        alternatives_weather = {}

    vessel_lat = vessel.get("lat", 0.0)
    vessel_lon = vessel.get("lon", 0.0)
    vessel_sog = vessel.get("sog", 12.0) or 12.0
    vessel_draught = vessel.get("draught", 0.0) or 0.0
    vessel_type = vessel.get("vessel_type", 70) or 70
    destination = vessel.get("destination", "")

    dest_congestion_score = destination_congestion.get("congestion_score", 50.0)
    dest_congestion_level = destination_congestion.get("congestion_level", "MEDIUM")
    dest_weather_risk = destination_weather.get("risk_level", "LOW") if destination_weather else "LOW"

    # Determine if rerouting should be considered
    should_reroute = (
        dest_congestion_level == "HIGH"
        or dest_weather_risk == "HIGH"
        or (dest_congestion_level == "MEDIUM" and dest_weather_risk == "MEDIUM")
    )

    # Build reason
    reasons = []
    if dest_congestion_level == "HIGH":
        reasons.append(f"Destination congestion is HIGH (score: {dest_congestion_score:.0f}/100)")
    if dest_weather_risk == "HIGH":
        reasons.append(f"Destination weather risk is HIGH")
    if not reasons and dest_congestion_level == "MEDIUM":
        reasons.append(f"Destination congestion is MEDIUM — monitoring advisable")

    # Get destination coords for distance calculations
    dest_coords = PORT_COORDS.get(destination)

    # Evaluate each alternative
    evaluated_alternatives = []
    for alt_port in alternative_ports:
        alt_coords = PORT_COORDS.get(alt_port)
        if not alt_coords:
            continue

        # Distance from vessel to alternative
        dist_to_alt = _haversine_nm(vessel_lat, vessel_lon, alt_coords[0], alt_coords[1])

        # Distance from vessel to original destination
        dist_to_dest = 0.0
        if dest_coords:
            dist_to_dest = _haversine_nm(vessel_lat, vessel_lon, dest_coords[0], dest_coords[1])

        additional_distance = round(dist_to_alt - dist_to_dest, 0)
        additional_time = round(additional_distance / vessel_sog, 1) if vessel_sog > 0 else 0

        alt_congestion = alternatives_congestion.get(alt_port, {})
        alt_congestion_score = alt_congestion.get("congestion_score", 50.0)
        alt_congestion_level = alt_congestion.get("congestion_level", "MEDIUM")

        alt_weather = alternatives_weather.get(alt_port, {})
        alt_weather_risk = alt_weather.get("risk_level", "LOW") if alt_weather else "LOW"

        draught_ok = _draught_compatible(vessel_draught, alt_port)
        type_ok = _vessel_type_compatible(vessel_type, alt_port)

        recommendation = _get_recommendation(
            dest_congestion_level,
            alt_congestion_level,
            abs(additional_distance),
        )

        evaluated_alternatives.append({
            "port": alt_port,
            "congestion_score": round(alt_congestion_score, 1),
            "congestion_level": alt_congestion_level,
            "additional_distance_nm": additional_distance,
            "additional_time_hours": additional_time,
            "draught_compatible": draught_ok,
            "vessel_type_compatible": type_ok,
            "weather_risk": alt_weather_risk,
            "recommendation": recommendation,
        })

    # Sort: STRONG first, then by congestion score ascending
    _rec_order = {"STRONG": 0, "MODERATE": 1, "WEAK": 2, "NONE": 3}
    evaluated_alternatives.sort(
        key=lambda x: (_rec_order.get(x["recommendation"], 3), x["congestion_score"])
    )

    return {
        "should_reroute": should_reroute,
        "reason": "; ".join(reasons) if reasons else "Destination conditions acceptable",
        "destination": {
            "port": destination,
            "congestion_score": round(dest_congestion_score, 1),
            "congestion_level": dest_congestion_level,
            "weather_risk": dest_weather_risk,
        },
        "alternatives": evaluated_alternatives,
        "vessel_mmsi": vessel.get("mmsi"),
        "vessel_name": vessel.get("name", ""),
    }


def get_rerouting_for_vessel(
    vessel: dict[str, Any],
    portwatch_store: Any,
    weather_cache: dict | None = None,
) -> dict[str, Any]:
    """
    Convenience function: builds all needed data and calls evaluate_rerouting.
    """
    from analytics.trajectory import predict_trajectory, estimate_eta

    raw_destination = vessel.get("destination", "")
    if not raw_destination:
        return {
            "should_reroute": False,
            "reason": "No destination set for this vessel",
            "destination": {},
            "alternatives": [],
            "vessel_mmsi": vessel.get("mmsi"),
            "vessel_name": vessel.get("name", ""),
        }

    # Resolve the raw AIS destination to a known port name
    resolved_port = resolve_port_name(raw_destination)
    lookup_name = resolved_port or raw_destination

    # Get trajectory
    trajectory = predict_trajectory(
        lat=vessel.get("lat", 0),
        lon=vessel.get("lon", 0),
        sog_knots=vessel.get("sog", 10),
        cog_degrees=vessel.get("cog", 0),
        rate_of_turn=vessel.get("rate_of_turn", 0),
        destination_port=raw_destination,
        hours=72,
    )

    # Get destination congestion using resolved name
    dest_congestion = portwatch_store.get_port_overview(lookup_name) if portwatch_store else {}
    if "error" in dest_congestion:
        dest_congestion = {"congestion_score": 50.0, "congestion_level": "UNKNOWN"}

    # Get alternative ports using resolved name
    alt_ports = get_alternative_ports(lookup_name)

    # Get alternatives' congestion
    alts_congestion = {}
    for alt in alt_ports:
        data = portwatch_store.get_port_overview(alt) if portwatch_store else {}
        if "error" not in data:
            alts_congestion[alt] = data

    # Build the result — use the resolved port name for display
    result = evaluate_rerouting(
        vessel=vessel,
        trajectory=trajectory,
        destination_congestion=dest_congestion,
        destination_weather={},
        alternative_ports=alt_ports,
        alternatives_congestion=alts_congestion,
    )

    # Add resolved port info to the result
    result["resolved_port"] = resolved_port
    result["raw_destination"] = raw_destination
    if resolved_port and result.get("destination"):
        result["destination"]["port"] = resolved_port

    return result
