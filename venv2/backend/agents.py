"""
agents.py
=========
Risk Orchestrator + LangGraph pipeline for DockWise AI.

Imports the two specialized agents and wires them into a LangGraph pipeline:

    weather_agent → congestion_agent → risk_orchestrator → END

Each agent reads from and writes to the shared RiskState.

Usage:
    from agents import run_risk_assessment
    result = run_risk_assessment("Los Angeles-Long Beach")
"""

from __future__ import annotations
import os
import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ──────────────────────────────────────────────────────────────────────────────

class RiskState(TypedDict):
    port: str

    # ── Weather Disruption Agent outputs ──────────────────────────────────────
    weather_disruption_score: float   # 0.0 – 1.0
    weather_risk_level: str           # LOW / MEDIUM / HIGH
    active_warnings: list             # human-readable warning strings
    weather_summary: str              # one-line condition summary

    # ── Vessel Arrival Agent outputs (TODO) ──────────────────────────────────
    vessel_count: int                 # vessels arriving in next 72 hours
    vessel_delay_score: float         # historical on-time rate (0-1)
    mega_vessel_flag: bool            # True if any 10K+ TEU vessel in queue

    # ── Port Congestion Agent outputs ─────────────────────────────────────────
    congestion_score: float           # 0 – 100 (z-score vs Prophet baseline)
    congestion_ratio: float           # current portcalls / Prophet expected
    trend_direction: str              # rising / stable / falling
    seasonal_context: str             # peak / off-peak / CNY etc.
    prophet_expected: float | None    # what Prophet expected for today

    # ── Risk Orchestrator outputs ─────────────────────────────────────────────
    risk_score: float                 # 0.0 – 1.0  (final combined score)
    risk_tier: str                    # LOW / MEDIUM / HIGH
    explanation: str                  # LLM-generated risk narrative


# ──────────────────────────────────────────────────────────────────────────────
# RISK ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

# Contribution weights for the final risk score
_CONGESTION_WEIGHT = 0.65
_WEATHER_WEIGHT    = 0.35


def risk_orchestrator(state: RiskState) -> RiskState:
    """
    Combine agent signals into a final risk score and generate an explanation.

    Formula:
        risk_score = 0.65 × (congestion_score / 100) + 0.35 × weather_disruption_score

    Thresholds:
        >= 0.67  →  HIGH
        >= 0.33  →  MEDIUM
        <  0.33  →  LOW
    """
    congestion_norm = state["congestion_score"] / 100.0
    weather_score   = state["weather_disruption_score"]

    risk_score = round(
        _CONGESTION_WEIGHT * congestion_norm + _WEATHER_WEIGHT * weather_score,
        3,
    )

    if risk_score >= 0.67:
        risk_tier = "HIGH"
    elif risk_score >= 0.33:
        risk_tier = "MEDIUM"
    else:
        risk_tier = "LOW"

    logger.info(
        f"[RiskOrchestrator] port={state['port']}  "
        f"risk_score={risk_score}  tier={risk_tier}"
    )

    explanation = _generate_explanation(state, risk_score, risk_tier)

    return {
        **state,
        "risk_score":  risk_score,
        "risk_tier":   risk_tier,
        "explanation": explanation,
    }


def _generate_explanation(state: RiskState, risk_score: float, risk_tier: str) -> str:
    """Call Groq LLM to generate a structured risk narrative."""
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage, SystemMessage

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return _fallback_explanation(state, risk_score, risk_tier)

        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=api_key,
            temperature=0.2,
            max_tokens=400,
        )

        prompt = f"""Port: {state['port']}
Overall Risk: {risk_tier}  (score {risk_score:.2f} / 1.0)

Agent Signals:
  Congestion Score : {state['congestion_score']} / 100
  Congestion Ratio : {state['congestion_ratio']}x vs 90-day baseline
  Trend            : {state['trend_direction']}
  Seasonal Context : {state['seasonal_context']}
  Weather Risk     : {state['weather_risk_level']}
  Conditions       : {state['weather_summary']}
  Active Warnings  : {', '.join(state['active_warnings']) if state['active_warnings'] else 'None'}

Write a 3-4 sentence risk assessment:
1. Lead with the overall risk tier and score.
2. Identify the primary driver (congestion or weather).
3. Note the trend and seasonal context.
4. End with 1-2 specific actionable recommendations."""

        response = llm.invoke([
            SystemMessage(content="You are DockWise AI, a maritime port risk advisor. Be concise, specific, and actionable."),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()

    except Exception as e:
        logger.error(f"[RiskOrchestrator] LLM explanation error: {e}")
        return _fallback_explanation(state, risk_score, risk_tier)


def _fallback_explanation(state: RiskState, risk_score: float, risk_tier: str) -> str:
    """Rule-based explanation used when LLM is unavailable."""
    parts = [f"{risk_tier} risk at {state['port']} (score: {risk_score:.2f}/1.0)."]

    if state["congestion_score"] >= 67:
        parts.append(
            f"Congestion is HIGH at {state['congestion_score']}/100 "
            f"({state['congestion_ratio']}x baseline), trending {state['trend_direction']}."
        )
    elif state["congestion_score"] >= 33:
        parts.append(
            f"Congestion is MEDIUM at {state['congestion_score']}/100, "
            f"trending {state['trend_direction']}."
        )
    else:
        parts.append(f"Congestion is LOW at {state['congestion_score']}/100.")

    if state["weather_risk_level"] != "LOW":
        parts.append(
            f"Weather risk is {state['weather_risk_level']}: "
            f"{', '.join(state['active_warnings'])}."
        )

    parts.append(state["seasonal_context"] + ".")
    return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# LANGGRAPH PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def build_risk_graph():
    """
    Build and compile the LangGraph risk assessment pipeline.

    Flow:
        weather_agent → congestion_agent → risk_orchestrator → END
    """
    from langgraph.graph import StateGraph, END
    import weather_agent
    import congestion_agent
    import vessel_agent

    graph = StateGraph(RiskState)

    graph.add_node("weather_agent",     weather_agent.run)
    graph.add_node("congestion_agent",  congestion_agent.run)
    graph.add_node("vessel_agent",      vessel_agent.run)      # TODO: implement
    graph.add_node("risk_orchestrator", risk_orchestrator)

    graph.set_entry_point("weather_agent")
    graph.add_edge("weather_agent",     "congestion_agent")
    graph.add_edge("congestion_agent",  "vessel_agent")
    graph.add_edge("vessel_agent",      "risk_orchestrator")
    graph.add_edge("risk_orchestrator", END)

    return graph.compile()


# ── Module-level compiled graph (built once, reused across requests) ──────────
_graph = None


def run_risk_assessment(port: str) -> dict:
    """
    Run the full agent pipeline for a port and return the complete RiskState.

    Parameters
    ----------
    port : str
        Port name exactly as it appears in portwatch_us_data.csv
        e.g. "Los Angeles-Long Beach", "Houston", "New York-New Jersey"

    Returns
    -------
    dict with all RiskState fields populated.
    """
    global _graph
    if _graph is None:
        _graph = build_risk_graph()

    initial_state: RiskState = {
        "port":                     port,
        # Weather agent defaults
        "weather_disruption_score": 0.0,
        "weather_risk_level":       "LOW",
        "active_warnings":          [],
        "weather_summary":          "",
        # Vessel agent defaults (TODO)
        "vessel_count":             0,
        "vessel_delay_score":       0.0,
        "mega_vessel_flag":         False,
        # Congestion agent defaults
        "congestion_score":         50.0,
        "congestion_ratio":         1.0,
        "trend_direction":          "stable",
        "seasonal_context":         "",
        "prophet_expected":         None,
        # Orchestrator defaults
        "risk_score":               0.0,
        "risk_tier":                "LOW",
        "explanation":              "",
    }

    return _graph.invoke(initial_state)