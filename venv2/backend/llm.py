"""
llm.py
======
LangChain + Groq LLM workflow for DockWise AI recommendations.

Uses modern LCEL (LangChain Expression Language) with explicit message history.

Provides:
  - MARITIME_KNOWLEDGE  – static facts about chokepoints, ports, trade
  - build_context()     – assembles live dashboard data into a context string
  - chat()              – main function called by /api/chat endpoint
"""

from __future__ import annotations
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# MARITIME KNOWLEDGE BASE  (static context fed to every query)
# Sources: UNCTAD Review of Maritime Transport, IMF PortWatch,
# BTS Freight Indicators, MARAD Port Statistics, public domain
# ─────────────────────────────────────────────────────────────
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

Luzon Strait (Philippines): Alternative Pacific route if South China Sea is disrupted.

--- US PORT CLUSTERS & CHARACTERISTICS ---
WEST COAST (LA/Long Beach, Seattle, Oakland, Tacoma):
  - Handle ~40% of US containerized imports from Asia
  - LA-Long Beach complex: largest US port complex, 9–10M TEUs/year
  - Vulnerable to: labor disputes (ILWU), Asia-origin chokepoint disruptions (Malacca, Taiwan Strait)
  - Typical lead time from Shanghai: 14–18 days via Transpacific

EAST COAST (New York/NJ, Savannah, Charleston, Baltimore, Norfolk):
  - Growing share after Panama Canal expansion (2016) enabled larger vessels
  - Savannah: fastest growing US port, ~6M TEUs/year; major hub for Southeast US
  - Baltimore: key auto and RoRo hub (Francis Scott Key Bridge collapse 2024 = major disruption)
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

Freight Rate Context:
  - Freightos Baltic Index (FBX): Global container spot rates; >$5,000/FEU = tight market
  - Baltic Dry Index (BDI): Dry bulk demand indicator; >2,000 = elevated bulk demand
  - Diversion via Cape of Good Hope adds ~$600–800 in daily bunker fuel costs per vessel

--- RECOMMENDATIONS FRAMEWORK ---
For HIGH congestion port:
  1. Consider alternative nearby ports (e.g., Oakland instead of LA-LB)
  2. Expedite customs pre-clearance to minimize dwell time
  3. Check upstream chokepoint disruption scores for 14–28 day forward outlook
  4. Consider rail-air transshipment for time-sensitive cargo
  5. Add 3–5 buffer days to supply chain schedule

For chokepoint disruption:
  1. Suez HIGH: Expect Cape of Good Hope diversions; add 10–14 transit days
  2. Panama LOW capacity: Explore Suez alternative or All-Water East Coast service
  3. Hormuz HIGH: Energy price hedging; check alternative LNG/crude sources
  4. Malacca HIGH: Lombok Strait alternative (adds ~1 day but avoids congestion)

For weather risk:
  1. HIGH ops risk: Delay vessel arrivals by 12–24h; pre-notify terminal
  2. Storm surge risk (Gulf Coast): Move anchorage outside storm track
  3. Cold weather: Pre-heat systems; check ice classification requirements (Great Lakes)
=== END KNOWLEDGE BASE ===
"""

SYSTEM_PROMPT = (
    "You are DockWise AI, a maritime port intelligence advisor. "
    "You help logistics managers, port operators, and supply chain analysts understand "
    "port congestion, chokepoint disruptions, weather risks, and make practical recommendations.\n\n"
    "Use the MARITIME KNOWLEDGE BASE and LIVE DASHBOARD DATA in the user's message "
    "to give accurate, specific, and actionable advice.\n\n"
    "Guidelines:\n"
    "- Be concise and direct. Lead with the most important insight.\n"
    "- When congestion is HIGH, always suggest concrete mitigation actions.\n"
    "- Reference specific scores, dates, and chokepoint names from the live data.\n"
    "- If asked about something not in the data, use your maritime knowledge base.\n"
    "- Format lists with bullet points for readability.\n"
    "- Do not speculate about political events beyond what the knowledge base describes.\n\n"
    "IMPORTANT: You MUST respond with valid JSON in this exact format:\n"
    '{"answer": "<your full answer text here>", "sources": ["<source1>", "<source2>"]}\n\n'
    "For sources, list only the data sources you actually used from this set:\n"
    "AIS records, ARIMA forecast, Prophet forecast, XGBoost forecast, NOAA weather, "
    "OpenWeatherMap, IMF PortWatch, congestion z-score, vessel delay score, "
    "chokepoint transit data, maritime knowledge base.\n"
    "Include 1-4 sources that are most relevant. Do NOT include sources you did not use.\n"
    "The answer field should contain your full response as plain text (use bullet points with - not *)."
)


# ─────────────────────────────────────────────────────────────
# CONTEXT BUILDER
# ─────────────────────────────────────────────────────────────

def build_context(
    port: str | None = None,
    overview: dict | None = None,
    forecast: list[dict] | None = None,
    chokepoints: list[dict] | None = None,
    port_chokepoints: list[dict] | None = None,
    weather: dict | None = None,
) -> str:
    """Build a live-data context block from dashboard data."""
    lines: list[str] = ["=== LIVE DASHBOARD DATA ==="]

    if overview and overview.get("kpi"):
        k = overview["kpi"]
        lines.append(f"\nSelected Port: {k.get('port', port)}")
        lines.append(f"  Congestion Score: {k.get('congestion_score')} / 100  ({k.get('congestion_level')})")
        lines.append(f"  Last Port Calls: {k.get('last_portcalls')} vessels/day")
        lines.append(f"  7-Day Trend: {k.get('trend_direction')}")
        lines.append(f"  vs 90-Day Normal: {k.get('pct_vs_normal')}%")
        lines.append(f"  Data as of: {k.get('last_date')}")

    if forecast:
        lines.append("\n7-Day Congestion Forecast:")
        for row in forecast[:7]:
            lines.append(f"  {row.get('date','')}: score={row.get('congestion_score')}, level={row.get('congestion_level')}")

    if weather and weather.get("current"):
        c = weather["current"]
        risk = c.get("risk", {})
        lines.append(f"\nPort Weather (current):")
        lines.append(f"  Conditions: {c.get('description','')}, Temp: {c.get('temp_c')}°C")
        lines.append(f"  Wind: {c.get('wind_speed_ms')} m/s, Gusts: {c.get('wind_gust_ms')} m/s")
        lines.append(f"  Visibility: {c.get('visibility_m')} m")
        lines.append(f"  Ops Risk: {risk.get('level','LOW')} — {', '.join(risk.get('reasons', ['none']))}")
        if weather.get("forecast"):
            lines.append("  5-Day Forecast:")
            for d in weather["forecast"][:5]:
                lines.append(f"    {d.get('date','')}: {d.get('description','')}, wind={d.get('wind_max_ms')} m/s")

    if port_chokepoints:
        lines.append(f"\nUpstream Chokepoints for {port}:")
        for c in port_chokepoints:
            lines.append(
                f"  {c['portname']}: disruption={c['disruption_score']} ({c['disruption_level']}), "
                f"trend={c.get('trend','stable')}, transits={c.get('n_total')} ships/day"
            )

    if chokepoints:
        high   = [c["portname"] for c in chokepoints if c.get("disruption_level") == "HIGH"]
        medium = [c["portname"] for c in chokepoints if c.get("disruption_level") == "MEDIUM"]
        if high:
            lines.append(f"\nGlobal Chokepoints — HIGH disruption: {', '.join(high)}")
        if medium:
            lines.append(f"Global Chokepoints — MEDIUM (watch): {', '.join(medium)}")

    lines.append("\n=== END LIVE DATA ===")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# CONVERSATION HISTORY (module-level, shared across requests)
# In production you'd key this per session/user
# ─────────────────────────────────────────────────────────────
_history: list = []   # list of (HumanMessage | AIMessage)
_MAX_TURNS = 8        # keep last 8 exchanges (16 messages)


def _get_llm():
    """Create the ChatGroq instance (lazily initialised)."""
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        raise RuntimeError("langchain-groq not installed. Run: pip install langchain-groq")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in .env file.")

    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=api_key,
        temperature=0.3,
        max_tokens=1024,
    )


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def chat(
    question: str,
    port: str | None = None,
    overview: dict | None = None,
    forecast: list | None = None,
    chokepoints: list | None = None,
    port_chokepoints: list | None = None,
    weather: dict | None = None,
    reset_memory: bool = False,
) -> str:
    """
    Send a question to the LLM with full maritime context.
    Maintains a sliding window of conversation history.
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    global _history

    if reset_memory:
        _history = []

    llm = _get_llm()

    live_ctx = build_context(
        port=port,
        overview=overview,
        forecast=forecast,
        chokepoints=chokepoints,
        port_chokepoints=port_chokepoints,
        weather=weather,
    )

    full_input = f"{MARITIME_KNOWLEDGE}\n\n{live_ctx}\n\nUser question: {question}"

    # Build message list: system + history + current human message
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    # Trim history to last N turns
    recent = _history[-(2 * _MAX_TURNS):]
    messages.extend(recent)
    messages.append(HumanMessage(content=full_input))

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()

        import json
        import re

        logger.info(f"Raw LLM response: {raw[:500]}")

        answer_text = raw
        sources = []

        def _try_parse(text):
            """Try to parse JSON and extract answer+sources. Returns (answer, sources) or None."""
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "answer" in parsed:
                    return (parsed["answer"], parsed.get("sources", []))
            except (json.JSONDecodeError, TypeError):
                pass
            return None

        # Attempt 1: direct JSON parse
        result = _try_parse(raw)

        # Attempt 2: JSON wrapped in markdown code fences
        if result is None:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
            if json_match:
                result = _try_parse(json_match.group(1))

        if result is not None:
            answer_text, sources = result

        # Final safety: if answer_text still looks like raw JSON, treat as plain text
        stripped = answer_text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            logger.warning("answer_text still looks like JSON — falling back to plain text")
            answer_text = raw
            sources = []

        # Update history with trimmed versions (omit bulky knowledge for memory efficiency)
        _history.append(HumanMessage(content=f"[Port: {port}] {question}"))
        _history.append(AIMessage(content=answer_text))
        # Keep only last N turns
        _history = _history[-(2 * _MAX_TURNS):]

        return {"answer": answer_text, "sources": sources}
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise


def generate_followups(answer: str, port: str | None = None) -> list[str]:
    """
    Generate 3 short follow-up questions based on an AI answer.
    Returns a list of 3 strings.
    """
    import json
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()
    port_label = port or "this port"
    prompt = (
        f"Given this answer about {port_label}: {answer}\n\n"
        "Generate exactly 3 short follow-up questions (under 10 words each) "
        "a supply chain manager would naturally ask next. "
        "Return as a JSON array of strings, nothing else."
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You generate concise follow-up questions. Return only a JSON array of 3 strings."),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        followups = json.loads(raw)
        if isinstance(followups, list) and len(followups) >= 3:
            return [str(q) for q in followups[:3]]
    except Exception as e:
        logger.error(f"Follow-up generation error: {e}")

    return []
