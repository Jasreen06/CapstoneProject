"""
knowledge.py
============
Maritime knowledge base and context builder for DockWise AI v2 advisor.
"""

from __future__ import annotations
from typing import Any

MARITIME_KNOWLEDGE = """
=== MARITIME KNOWLEDGE BASE ===

--- GLOBAL CHOKEPOINTS ---
Suez Canal (Egypt): Connects Red Sea to Mediterranean. ~12% of global trade and ~30% of container
  traffic transits daily. Blockages (e.g., Ever Given 2021) cause immediate ripple effects on
  Europe-Asia lanes. Average transit: 50-60 vessels/day. Controlled by Suez Canal Authority.
  Risk drivers: Houthi attacks (2024–present), piracy in Red Sea, vessel size constraints.

Panama Canal (Panama): Connects Pacific to Atlantic. ~5% of global seaborne trade, critical for
  US East Coast imports from Asia. Drought in 2023–24 forced transit reductions to 18–22 ships/day
  (vs normal 36–38). Locks limit vessel beam to ~49m (Neopanamax up to 51m). Risk: drought,
  mechanical failures, geopolitical tensions.

Strait of Hormuz (Iran/Oman): ~20% of global oil supply and ~25% of LNG transits daily.
  Controlled approaches by Iran. Any closure would cause immediate crude oil price spikes.
  Average: 20–21 tankers/day. Risk: Iran-US tensions, naval incidents, military exercises.

Malacca Strait (Malaysia/Singapore/Indonesia): World's busiest shipping lane. ~25% of global
  trade, ~15 million barrels of oil/day. 80% of China's oil imports pass through here. Narrow
  (2.5km at Phillips Channel). Risk: piracy, vessel groundings, congestion at Singapore.

Bab el-Mandeb Strait (Yemen/Djibouti): Links Red Sea to Gulf of Aden. ~9% of global trade.
  Houthi attacks since late 2023 diverted 90% of container traffic away from Suez → Cape of Good
  Hope route, adding 10–14 days and $1M+ in fuel per voyage.

Dover Strait (UK/France): Busiest shipping lane by vessel count. ~500 vessels/day. Critical for
  intra-European trade. Risk: poor weather, collisions, UK-EU regulatory changes.

Taiwan Strait: ~48% of global container fleet transits annually. Crucial for East Asia exports.
  Risk: China-Taiwan tensions, military exercises causing vessel diversions.

Gibraltar Strait: 100,000+ vessels/year. Gateway between Atlantic and Mediterranean.

--- US PORT CLUSTERS & CHARACTERISTICS ---
WEST COAST (LA/Long Beach, Seattle, Oakland, Tacoma):
  - Handle ~40% of US containerized imports from Asia
  - LA-Long Beach complex: largest US port complex, 9–10M TEUs/year
  - Vulnerable to: labor disputes (ILWU), Asia-origin chokepoint disruptions (Malacca, Taiwan Strait)
  - Typical lead time from Shanghai: 14–18 days via Transpacific

EAST COAST (New York/NJ, Savannah, Charleston, Baltimore, Norfolk):
  - Growing share after Panama Canal expansion (2016) enabled larger vessels
  - Savannah: fastest growing US port, ~6M TEUs/year; major hub for Southeast US
  - Baltimore: key auto and RoRo hub
  - Vulnerable to: Suez/Bab el-Mandeb disruptions affecting Europe-Asia-US routes

GULF COAST (Houston, New Orleans, Corpus Christi):
  - Houston: largest US port by total tonnage; critical for petrochemicals, LNG exports
  - New Orleans: major bulk commodity (grain, coal) export hub for Midwest farm belt
  - Vulnerable to: hurricane season (June–November), Hormuz disruptions for energy trade

GREAT LAKES (Chicago, Detroit, Cleveland, Duluth):
  - Limited to Seaway-size vessels (max ~225m LOA)
  - Seasonal: closed to most large vessel traffic Nov–March (ice)
  - Key commodities: steel, iron ore, limestone, grain

--- SUPPLY CHAIN RISK FACTORS ---
Congestion Score Interpretation (DockWise 0–100 scale):
  0–33  LOW   : Traffic below 90-day baseline (port operating with capacity)
  34–66 MEDIUM: Near-normal, monitor for trend changes
  67–100 HIGH : Traffic significantly above baseline — expect delays, anchorage queues,
                berth waits up to 3–5 days, elevated drayage costs

Leading Indicators for Port Congestion (14–28 day lag):
  - Chokepoint disruption score spikes typically arrive at US ports within 14–28 days
  - Suez/Bab el-Mandeb → East Coast ports (~28 days)
  - Malacca/Taiwan Strait → West Coast ports (~14–18 days)
  - Panama Canal restrictions → Both coasts (~7–14 days)

Weather Risk Thresholds (Port Operations):
  - Wind ≥ 15 m/s (33 knots): Container crane operations suspended at many terminals
  - Wind ≥ 20 m/s (39 knots, near gale): All outdoor cargo ops suspended
  - Visibility ≤ 1 km: Vessel approach/departure suspended (VTS restriction)
  - Heavy rain (>5 mm/h): Reduced productivity, documentation delays

Seasonal Patterns:
  - Peak season: Aug–Oct (pre-Christmas imports; US West Coast congestion peaks)
  - Chinese New Year (Jan/Feb): Factory shutdowns → vessel bunching 2–3 weeks later
  - Hurricane season (June–Nov): Gulf/East Coast risk elevated
  - Winter storms: Great Lakes closures; Northeast port weather risk

--- RECOMMENDATIONS FRAMEWORK ---
For HIGH congestion port:
  1. Consider alternative nearby ports (e.g., Oakland instead of LA-LB)
  2. Expedite customs pre-clearance to minimize dwell time
  3. Check upstream chokepoint disruption scores for 14–28 day forward outlook
  4. Add 3–5 buffer days to supply chain schedule

For chokepoint disruption:
  1. Suez HIGH: Expect Cape of Good Hope diversions; add 10–14 transit days
  2. Panama LOW capacity: Explore Suez alternative or All-Water East Coast service
  3. Hormuz HIGH: Energy price hedging; check alternative LNG/crude sources
  4. Malacca HIGH: Lombok Strait alternative (adds ~1 day but avoids congestion)

For weather risk:
  1. HIGH ops risk: Delay vessel arrivals by 12–24h; pre-notify terminal
  2. Storm surge risk (Gulf Coast): Move anchorage outside storm track
=== END KNOWLEDGE BASE ===
"""

SYSTEM_PROMPT = (
    "You are DockWise AI, a maritime port intelligence advisor for DockWise AI v2. "
    "You help logistics managers, port operators, vessel operators, and supply chain analysts "
    "understand port congestion, chokepoint disruptions, weather risks, and vessel rerouting. "
    "You have access to live AIS vessel tracking data, real-time port congestion scores, "
    "weather risk assessments, and chokepoint disruption metrics.\n\n"
    "Use the MARITIME KNOWLEDGE BASE and LIVE DATA in the user's message "
    "to give accurate, specific, and actionable advice.\n\n"
    "Guidelines:\n"
    "- Be concise and direct. Lead with the most important insight.\n"
    "- When congestion is HIGH, always suggest concrete mitigation actions.\n"
    "- Reference specific scores, port names, and vessel data from the live data.\n"
    "- For rerouting questions, consider congestion, weather, draught, and transit time.\n"
    "- Format lists with bullet points for readability.\n"
    "- If asked about something not in the data, use your maritime knowledge base."
)


def build_context(
    port_name: str | None = None,
    vessel_mmsi: int | None = None,
    ports_data: dict | None = None,
    vessels_data: list | None = None,
    weather_data: dict | None = None,
    chokepoints_data: list | None = None,
    vessel_rerouting: dict | None = None,
) -> str:
    """Build a rich context string from live data for the AI advisor."""
    lines: list[str] = ["=== LIVE DASHBOARD DATA ==="]

    if port_name and ports_data:
        lines.append(f"\nSelected Port: {port_name}")
        lines.append(f"  Congestion Score: {ports_data.get('congestion_score', '?')} / 100  ({ports_data.get('congestion_level', '?')})")
        lines.append(f"  Port Calls (latest): {ports_data.get('portcalls', '?')} vessels")
        lines.append(f"  Trend (7-day): {ports_data.get('trend', 'stable')}")
        lines.append(f"  vs 90-Day Normal: {ports_data.get('pct_vs_normal', '?')}%")
        lines.append(f"  Data as of: {ports_data.get('last_date', '?')}")

    if weather_data and weather_data.get("current"):
        c = weather_data["current"]
        risk = c.get("risk", {})
        lines.append(f"\nPort Weather:")
        lines.append(f"  Conditions: {c.get('weather_description', '')}, Temp: {c.get('temp_c', '?')}°C")
        lines.append(f"  Wind: {c.get('wind_speed_ms', '?')} m/s")
        lines.append(f"  Visibility: {c.get('visibility_m', '?')} m")
        lines.append(f"  Ops Risk: {risk.get('level', 'LOW')} — {', '.join(risk.get('reasons', []))}")

    if vessel_mmsi and vessels_data:
        vessel = next((v for v in vessels_data if v.get("mmsi") == vessel_mmsi), None)
        if vessel:
            lines.append(f"\nSelected Vessel: {vessel.get('name', '?')} (MMSI: {vessel_mmsi})")
            lines.append(f"  Type: {vessel.get('vessel_type_label', '?')}")
            lines.append(f"  Position: {vessel.get('lat', '?')}, {vessel.get('lon', '?')}")
            lines.append(f"  Speed: {vessel.get('sog', '?')} knots, COG: {vessel.get('cog', '?')}°")
            lines.append(f"  Destination: {vessel.get('destination', 'unknown')}")
            lines.append(f"  Nav Status: {vessel.get('nav_status_label', '?')}")

    if vessel_rerouting:
        lines.append(f"\nRerouting Analysis:")
        lines.append(f"  Should Reroute: {vessel_rerouting.get('should_reroute', False)}")
        lines.append(f"  Reason: {vessel_rerouting.get('reason', '')}")
        alts = vessel_rerouting.get("alternatives", [])
        if alts:
            lines.append(f"  Top Alternative: {alts[0].get('port', '?')} "
                        f"(congestion: {alts[0].get('congestion_level', '?')}, "
                        f"recommendation: {alts[0].get('recommendation', '?')})")

    if chokepoints_data:
        high = [c["name"] for c in chokepoints_data if c.get("disruption_level") == "HIGH"]
        medium = [c["name"] for c in chokepoints_data if c.get("disruption_level") == "MEDIUM"]
        if high:
            lines.append(f"\nGlobal Chokepoints — HIGH disruption: {', '.join(high)}")
        if medium:
            lines.append(f"Global Chokepoints — MEDIUM (watch): {', '.join(medium)}")

    if vessels_data is not None:
        lines.append(f"\nLive Vessels Tracked: {len(vessels_data)}")

    lines.append("\n=== END LIVE DATA ===")
    return "\n".join(lines)
