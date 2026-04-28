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
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# MARITIME KNOWLEDGE BASE  (static context fed to every query)
# Sources: UNCTAD Review of Maritime Transport, IMF PortWatch,
# BTS Freight Indicators, MARAD Port Statistics, public domain
# ─────────────────────────────────────────────────────────────
MARITIME_KNOWLEDGE = """
=== DOCKWISE SYSTEM REFERENCE ===

--- CONGESTION SCORING (DockWise 0-100 scale) ---
0-33  LOW   : Traffic below 90-day Prophet+XGBoost baseline (port operating with capacity)
34-66 MEDIUM: Near-normal, monitor for trend changes
67-100 HIGH : Traffic significantly above baseline — expect delays, berth waits up to 3-5 days

--- CHOKEPOINT-TO-PORT LAG TABLE ---
Empirically derived from negative cross-correlation analysis on 7 years of IMF PortWatch data
(2019-2026). Only pairs showing a disruption signal (chokepoint transits drop -> port congestion
rises) are included. Coverage = ports showing the signal out of total ports on that coast.

Suez Canal        -> East Coast:  ~35 days  (15/25 ports show signal)
Bab el-Mandeb     -> East Coast:  ~28 days  (15/25 ports show signal)
  NOTE: NY-NJ, Baltimore, Savannah, Boston show NO disruption signal from Bab el-Mandeb
  — these large ports appear to absorb diversions without measurable congestion impact.
Malacca Strait    -> West Coast:  ~24 days  (6/12 ports show signal)
Taiwan Strait     -> West Coast:  ~28 days  (9/12 ports show signal)
Panama Canal      -> West Coast:  ~35 days  (9/12 ports show signal)
Panama Canal      -> East Coast:  ~42 days  (17/25 ports show signal)
Panama Canal      -> Gulf Coast:  ~28 days  (5/12 ports show signal)
Strait of Hormuz  -> Gulf Coast:  ~49 days  (5/12 ports show signal)
Panama Canal      -> Great Lakes: ~49 days  (9/10 ports show signal)

Not every port responds to every chokepoint. When a port shows no signal, it likely
routes cargo via alternate lanes or has enough capacity to absorb disruption-driven bunching.

--- WEATHER RISK (computed live by weather agent) ---
The weather agent already applies these thresholds to live OpenWeatherMap data and
reports a computed risk level (LOW/MEDIUM/HIGH) with specific reasons.
HIGH   = wind >= 20 m/s (crane ops suspended) OR visibility <= 500m OR severe weather
MEDIUM = wind >= 15 m/s (crane ops marginal) OR visibility <= 1000m OR heavy rain

=== END SYSTEM REFERENCE ===
"""

SYSTEM_PROMPT = (
    "You are DockWise AI, a maritime port intelligence advisor. "
    "You help logistics managers, port operators, and supply chain analysts understand "
    "port congestion, chokepoint disruptions, weather risks, and make practical recommendations.\n\n"
    "You will receive two inputs: DOCKWISE SYSTEM REFERENCE (scoring definitions and empirically "
    "derived chokepoint lag table) and LIVE DASHBOARD DATA (current port scores, forecasts, "
    "weather, vessel counts). Use both together with your own maritime domain knowledge to give "
    "accurate, specific, and actionable advice.\n\n"
    "Guidelines:\n"
    "- Be concise and direct. Lead with the most important insight.\n"
    "- Always ground your answer in the live data scores provided — cite specific numbers.\n"
    "- Use the lag table to reason about forward-looking chokepoint impacts.\n"
    "- For recommendations, apply your maritime expertise — do not wait to be told what to suggest.\n"
    "- Format lists with bullet points for readability.\n\n"
    "IMPORTANT: You MUST respond with valid JSON in this exact format:\n"
    '{"answer": "<your full answer text here>", "sources": ["<source1>", "<source2>"]}\n\n'
    "CRITICAL JSON RULES:\n"
    "- The answer field is a single JSON string. If your answer needs to include a quotation, "
    "use single quotes inside the answer string. Never nest double quotes inside the answer value.\n"
    "- Do NOT wrap the JSON in markdown code fences.\n"
    "- Do NOT include any text before or after the JSON object.\n"
    "- Ensure the JSON is valid: no trailing commas, no unescaped special characters.\n\n"
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
# PHASE 7A — CROSS-PORT QUERY SUPPORT
# Scope classifier + scope-specific live-data builders.
# Single-port path is preserved bytes-identical when extra_ctx == "".
# ─────────────────────────────────────────────────────────────

# TODO: extract to data_layer.py if more callers emerge.
# Lazy imports inside helpers below intentionally avoid circular import
# (api.py imports llm at module load; llm.py must not reciprocate at module load).

_GLOBAL_KEYWORDS = [
    "suez", "panama canal", "hormuz", "malacca", "bab el-mandeb", "bab-el-mandeb",
    "dover strait", "taiwan strait", "gibraltar", "luzon", "chokepoint", "chokepoints",
]

# Mirrors api._WEST/_GULF/_LAKES/_EAST classification but operates on user-question
# phrasing rather than canonical port names. Multi-word phrases ranked first so
# "great lakes" matches before "lakes".
_REGIONAL_SYNONYMS = {
    "east": [
        "east coast", "atlantic coast", "atlantic side", "atlantic ports",
        "eastern seaboard", "east-coast", "atlantic",
    ],
    "west": [
        "west coast", "pacific coast", "pacific side", "pacific ports",
        "west-coast", "pacific",
    ],
    "gulf": [
        "gulf coast", "gulf of mexico", "gulf ports", "gulf-coast", "gulf",
    ],
    "lakes": [
        "great lakes", "midwest ports", "midwest", "great-lakes", "seaway",
    ],
}

_NATIONAL_KEYWORDS = [
    "most congested", "worst congestion", "highest congestion",
    "least congested", "best ports", "top ports", "top us ports",
    "across the us", "across the country", "nationally", "nationwide",
    "which port", "what port", "which ports", "what ports",
    "us ports overall", "all us ports",
]

_COMPARISON_TOKENS = ["compare", " vs ", " vs.", "versus", "between"]

_KNOWN_PORTS_CACHE: list[tuple[str, str]] | None = None
_GENERIC_FRAGMENT_SKIP = {"united states", "usa"}


def _known_ports() -> list[tuple[str, str]]:
    """Cached list of (alias_lower, canonical_name).
    Canonical names are PortWatch port names. Aliases also include split fragments
    of compound names ('Los Angeles-Long Beach' → 'Long Beach' / 'Los Angeles')."""
    global _KNOWN_PORTS_CACHE
    if _KNOWN_PORTS_CACHE is not None:
        return _KNOWN_PORTS_CACHE
    try:
        import api as _api  # lazy
        df = _api.get_df()
        names = sorted({str(n) for n in df["portname"].dropna().unique() if len(str(n)) >= 4})
        aliases: list[tuple[str, str]] = []
        for n in names:
            aliases.append((n.lower(), n))
            for sep in (" - ", "-", "/"):
                if sep in n:
                    for frag in n.split(sep):
                        frag = frag.strip()
                        if len(frag) >= 4 and frag.lower() not in _GENERIC_FRAGMENT_SKIP:
                            aliases.append((frag.lower(), n))
        _KNOWN_PORTS_CACHE = aliases
    except Exception as e:
        logger.warning(f"_known_ports: failed to load port list: {e}")
        _KNOWN_PORTS_CACHE = []
    return _KNOWN_PORTS_CACHE


def _extract_named_ports(question: str) -> list[str]:
    """Word-boundary match aliases in question. Longest-first prevents
    'Long Beach' matching before 'Los Angeles-Long Beach'. Returns canonical names."""
    q = question.lower()
    found: list[str] = []
    consumed_spans: list[tuple[int, int]] = []
    for alias, canonical in sorted(_known_ports(), key=lambda x: len(x[0]), reverse=True):
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])"
        for m in re.finditer(pattern, q):
            span = m.span()
            if any(s <= span[0] < e or s < span[1] <= e for s, e in consumed_spans):
                continue
            consumed_spans.append(span)
            if canonical not in found:
                found.append(canonical)
    return found


def _detect_coast(question: str) -> str | None:
    """Return 'east' / 'west' / 'gulf' / 'lakes' or None. Longest phrase wins."""
    q = question.lower()
    candidates: list[tuple[int, str]] = []
    for region, synonyms in _REGIONAL_SYNONYMS.items():
        for phrase in synonyms:
            if phrase in q:
                candidates.append((len(phrase), region))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _coast_for_port(portname: str) -> str:
    """Classify a canonical port name to coast bucket. Mirrors api._get_port_chokepoints."""
    try:
        import api as _api  # lazy
        p = portname.lower()
        if any(k in p for k in _api._WEST_KEYWORDS):
            return "west"
        if any(k in p for k in _api._GULF_KEYWORDS):
            return "gulf"
        if any(k in p for k in _api._LAKES_KEYWORDS):
            return "lakes"
        return "east"
    except Exception:
        return "east"


def _latest_port_kpis() -> list[dict]:
    """Latest scored row per port — congestion score, level, last date, portcalls."""
    try:
        import api as _api  # lazy
        scored = _api.get_scored_df()
        latest = scored.sort_values("date").groupby("portname").tail(1)
        rows = []
        for _, r in latest.iterrows():
            rows.append({
                "portname": str(r["portname"]),
                "congestion_score": float(r.get("congestion_score", 0.0) or 0.0),
                "traffic_level": str(r.get("traffic_level", "LOW")),
                "portcalls": float(r.get("portcalls", 0.0) or 0.0),
                "date": str(r.get("date", "")),
            })
        return rows
    except Exception as e:
        logger.warning(f"_latest_port_kpis: failed: {e}")
        return []


def classify_query_scope(question: str) -> str:
    """Priority order: global > comparison > regional > national > single_port."""
    q = question.lower()
    if any(k in q for k in _GLOBAL_KEYWORDS):
        return "global"
    if any(tok in q for tok in _COMPARISON_TOKENS):
        return "comparison"
    if _detect_coast(q) is not None:
        return "regional"
    if any(k in q for k in _NATIONAL_KEYWORDS):
        return "national"
    return "single_port"


def build_regional_context(question: str) -> str:
    """Live data block for a coast-scoped question."""
    coast = _detect_coast(question)
    if coast is None:
        return ""
    rows = _latest_port_kpis()
    matched = [r for r in rows if _coast_for_port(r["portname"]) == coast]
    if not matched:
        return ""
    matched.sort(key=lambda r: r["congestion_score"], reverse=True)
    label = {"east": "East Coast", "west": "West Coast",
             "gulf": "Gulf Coast", "lakes": "Great Lakes"}[coast]
    lines = [f"\n=== REGIONAL LIVE DATA — {label} ({len(matched)} ports) ==="]
    for r in matched[:25]:
        lines.append(
            f"  {r['portname']}: score={r['congestion_score']:.1f}/100 "
            f"({r['traffic_level']}), portcalls={r['portcalls']:.1f}, as of {r['date']}"
        )
    lines.append("=== END REGIONAL DATA ===")
    return "\n".join(lines)


def build_national_context() -> str:
    """Live data block for nationwide ranking questions."""
    rows = _latest_port_kpis()
    if not rows:
        return ""
    rows.sort(key=lambda r: r["congestion_score"], reverse=True)
    high = [r for r in rows if r["traffic_level"] == "HIGH"]
    medium = [r for r in rows if r["traffic_level"] == "MEDIUM"]
    low = [r for r in rows if r["traffic_level"] == "LOW"]
    lines = [f"\n=== NATIONAL LIVE DATA — {len(rows)} US ports ==="]
    lines.append(f"Tier counts: HIGH={len(high)}, MEDIUM={len(medium)}, LOW={len(low)}")
    lines.append(f"\nTop 10 most congested:")
    for r in rows[:10]:
        lines.append(
            f"  {r['portname']}: {r['congestion_score']:.1f}/100 ({r['traffic_level']}), as of {r['date']}"
        )
    lines.append(f"\nLeast congested 5:")
    for r in rows[-5:]:
        lines.append(
            f"  {r['portname']}: {r['congestion_score']:.1f}/100 ({r['traffic_level']}), as of {r['date']}"
        )
    lines.append("=== END NATIONAL DATA ===")
    return "\n".join(lines)


def build_comparison_context(question: str) -> str:
    """Live data block for a port-vs-port comparison."""
    named = _extract_named_ports(question)
    if len(named) < 2:
        # Deterministic fallback hint — let the LLM ask for clarification rather than guess.
        return (
            "\n=== COMPARISON CONTEXT ===\n"
            "The user appears to be asking a comparison question, but two or more "
            "specific port names could not be confidently extracted. Ask the user to "
            "name the exact ports they want compared (e.g., 'Compare Houston vs Long Beach').\n"
            "=== END COMPARISON CONTEXT ==="
        )
    rows = _latest_port_kpis()
    by_name = {r["portname"]: r for r in rows}
    lines = [f"\n=== COMPARISON LIVE DATA — {len(named)} ports ==="]
    for n in named:
        r = by_name.get(n)
        if r is None:
            lines.append(f"  {n}: no live data available")
            continue
        lines.append(
            f"  {r['portname']}: score={r['congestion_score']:.1f}/100 "
            f"({r['traffic_level']}), portcalls={r['portcalls']:.1f}, "
            f"coast={_coast_for_port(r['portname'])}, as of {r['date']}"
        )
    lines.append("=== END COMPARISON DATA ===")
    return "\n".join(lines)


def build_global_context(all_chokepoints: list[dict] | None) -> str:
    """Chokepoint-level live data already passed in by api.chat_endpoint."""
    if not all_chokepoints:
        return ""
    lines = ["\n=== GLOBAL CHOKEPOINT LIVE DATA ==="]
    for c in all_chokepoints:
        lines.append(
            f"  {c.get('portname')}: disruption={c.get('disruption_score')} "
            f"({c.get('disruption_level')}), trend={c.get('trend','stable')}, "
            f"transits={c.get('n_total')}/day"
        )
    lines.append("=== END GLOBAL CHOKEPOINT DATA ===")
    return "\n".join(lines)


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

    # Phase 7A — classify scope and append scope-specific live data.
    # Single-port path keeps extra_ctx == "" so full_input is bytes-identical to pre-7A.
    scope = classify_query_scope(question)
    logger.info(f"chat() classified question scope as '{scope}'")

    extra_ctx = ""
    if scope == "regional":
        extra_ctx = build_regional_context(question)
    elif scope == "national":
        extra_ctx = build_national_context()
    elif scope == "comparison":
        extra_ctx = build_comparison_context(question)
    elif scope == "global":
        extra_ctx = build_global_context(chokepoints)

    if extra_ctx:
        full_input = f"{MARITIME_KNOWLEDGE}\n\n{live_ctx}\n{extra_ctx}\n\nUser question: {question}"
    else:
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

        answer_text = None
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

        # Attempt 3 (Layer A): regex extraction of answer field from raw string
        if result is None:
            regex_match = re.search(
                r'"answer"\s*:\s*"(.+?)"\s*,\s*"sources"\s*:\s*\[(.*?)\]',
                raw,
                re.DOTALL,
            )
            if regex_match:
                extracted_answer = regex_match.group(1).replace('\\"', '"')
                raw_sources = regex_match.group(2).strip()
                parsed_sources = []
                if raw_sources:
                    parsed_sources = [
                        s.strip().strip('"').strip("'")
                        for s in raw_sources.split(",")
                        if s.strip().strip('"').strip("'")
                    ]
                result = (extracted_answer, parsed_sources)
                logger.info("Parsed response via Layer A regex extraction")

        if result is not None:
            answer_text, sources = result

        # Layer C: safe fallback — never return raw JSON to the UI
        if answer_text is None or (answer_text.strip().startswith("{") and answer_text.strip().endswith("}")):
            if answer_text is None:
                logger.warning(f"All parse attempts failed. Full raw response:\n{raw}")
            else:
                logger.warning(f"answer_text still looks like JSON after parsing. Full raw response:\n{raw}")
            # Try to salvage by stripping the JSON wrapper
            salvage = re.sub(r'^\s*\{\s*"answer"\s*:\s*"', '', raw)
            salvage = re.sub(r'"\s*,\s*"sources"\s*:\s*\[.*\]\s*\}\s*$', '', salvage)
            salvage = salvage.replace('\\"', '"').strip()
            if salvage and not (salvage.startswith("{") and salvage.endswith("}")):
                answer_text = salvage
                sources = []
                logger.info("Salvaged answer text from raw JSON wrapper")
            else:
                answer_text = "I had trouble formatting that response. Please try again."
                sources = []
                logger.warning("Could not salvage answer — returning apology string")

        # Update history with trimmed versions (omit bulky knowledge for memory efficiency)
        _history.append(HumanMessage(content=f"[Port: {port}] {question}"))
        _history.append(AIMessage(content=answer_text))
        # Keep only last N turns
        _history = _history[-(2 * _MAX_TURNS):]

        return {"answer": answer_text, "sources": sources}
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise


def generate_briefing(port_summaries: list[dict]) -> list[dict]:
    """
    Generate 3 insight cards from current port data.
    Each card: {headline, body, seed_question}.
    port_summaries: list of {portname, score, status, last_portcalls, trend_direction, pct_vs_normal}
    """
    import json
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()

    # Build a compact data block
    data_lines = []
    for p in port_summaries[:20]:  # top 20 to keep prompt compact
        data_lines.append(
            f"  {p['portname']}: score={p.get('score')}, status={p.get('status')}, "
            f"trend={p.get('trend_direction','stable')}, vs_normal={p.get('pct_vs_normal',0)}%"
        )
    data_block = "\n".join(data_lines)

    prompt = (
        f"Here is today's port congestion data:\n{data_block}\n\n"
        "Identify the top 3 most noteworthy signals for a logistics manager. "
        "For each, provide:\n"
        "- headline: one punchy line (under 10 words)\n"
        "- body: 2 sentences explaining why it matters\n"
        "- seed_question: a follow-up question the user can ask the AI advisor\n\n"
        "Return ONLY a JSON array of 3 objects with keys: headline, body, seed_question. "
        "No markdown fences, no surrounding text."
    )

    try:
        response = llm.invoke([
            SystemMessage(content=(
                "You are DockWise AI, a maritime intelligence briefing generator. "
                "Be concise and data-driven. Reference specific ports and scores."
            )),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        # Try to parse, handling potential markdown fences
        import re
        clean = raw
        fence_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw, re.DOTALL)
        if fence_match:
            clean = fence_match.group(1)
        cards = json.loads(clean)
        if isinstance(cards, list) and len(cards) >= 3:
            return [
                {
                    "headline": str(c.get("headline", "")),
                    "body": str(c.get("body", "")),
                    "seed_question": str(c.get("seed_question", "")),
                }
                for c in cards[:3]
            ]
    except Exception as e:
        logger.error(f"Briefing generation error: {e}")

    return []


def generate_scenario(scenario: str, port_summaries: list[dict], chokepoints: list[dict] | None = None) -> dict:
    """
    Run a what-if scenario analysis.
    Returns {impact_summary, affected_ports[], recommended_reroutes[], confidence}.
    """
    import json
    import re
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()

    data_lines = []
    for p in port_summaries[:15]:
        data_lines.append(f"  {p['portname']}: score={p.get('score')}, status={p.get('status')}")
    data_block = "\n".join(data_lines)

    chk_block = ""
    if chokepoints:
        chk_lines = [f"  {c['portname']}: disruption={c.get('disruption_score')}, level={c.get('disruption_level')}"
                     for c in chokepoints[:10]]
        chk_block = "\nChokepoint status:\n" + "\n".join(chk_lines)

    prompt = (
        f"SCENARIO: {scenario}\n\n"
        f"Current port congestion data:\n{data_block}\n{chk_block}\n\n"
        f"{MARITIME_KNOWLEDGE}\n\n"
        "Analyse this scenario's impact on US ports and supply chains. Return ONLY valid JSON "
        "with these keys:\n"
        "- impact_summary: 3-4 sentence analysis of the scenario's effects\n"
        "- affected_ports: array of strings (port names most impacted)\n"
        "- recommended_reroutes: array of strings (specific rerouting suggestions)\n"
        "- confidence: 'high', 'medium', or 'low' based on data availability\n\n"
        "No markdown fences, no surrounding text. Just the JSON object."
    )

    try:
        response = llm.invoke([
            SystemMessage(content=(
                "You are DockWise AI, a maritime scenario analyst. "
                "Use the maritime knowledge base and current data to provide realistic, "
                "specific impact assessments. Be practical and actionable."
            )),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        clean = raw
        fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if fence_match:
            clean = fence_match.group(1)
        result = json.loads(clean)
        return {
            "impact_summary": str(result.get("impact_summary", "")),
            "affected_ports": [str(p) for p in result.get("affected_ports", [])],
            "recommended_reroutes": [str(r) for r in result.get("recommended_reroutes", [])],
            "confidence": str(result.get("confidence", "medium")),
        }
    except Exception as e:
        logger.error(f"Scenario generation error: {e}")
        return {
            "impact_summary": "Unable to generate scenario analysis. Please try again.",
            "affected_ports": [],
            "recommended_reroutes": [],
            "confidence": "low",
        }


def generate_comparison(ports_data: list[dict]) -> str:
    """
    Generate 2-3 sentence LLM commentary comparing ports.
    ports_data: list of {portname, congestion_score, volatility, trend, weather_risk,
                         chokepoint_risk, inbound_vessels} (already normalized 0-100).
    """
    import json
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()

    data_lines = []
    for p in ports_data:
        data_lines.append(
            f"  {p['portname']}: congestion={p.get('congestion_score',50)}, "
            f"volatility={p.get('volatility',50)}, trend={p.get('trend',50)}, "
            f"weather_risk={p.get('weather_risk',0)}, chokepoint_risk={p.get('chokepoint_risk',50)}, "
            f"inbound_vessels={p.get('inbound_vessels',0)}"
        )
    data_block = "\n".join(data_lines)

    prompt = (
        f"Compare these ports (all values on 0-100 scale):\n{data_block}\n\n"
        "Write 2-3 concise sentences comparing them for a logistics manager. "
        "Highlight the key trade-off. Plain text only, no JSON."
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are DockWise AI. Give concise, data-driven port comparisons."),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()
    except Exception as e:
        logger.error(f"Comparison commentary error: {e}")
        return "Unable to generate comparison commentary."


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
