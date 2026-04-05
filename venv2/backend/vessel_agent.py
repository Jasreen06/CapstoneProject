"""
vessel_agent.py
===============
Vessel Arrival Agent for DockWise AI.

TODO: Implement vessel arrival risk signals using AIS data.

Planned outputs:
    vessel_count       — number of vessels arriving in next 72 hours
    vessel_delay_score — historical on-time rate of arriving vessels (0-1)
    mega_vessel_flag   — True if any 10K+ TEU vessels in the queue

Data sources needed:
    - AIS vessel position data (Marine Cadastre or similar)
    - Port vessel call schedules
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents import RiskState

logger = logging.getLogger(__name__)


def run(state: "RiskState") -> "RiskState":
    """
    Vessel Arrival Agent — not yet implemented.
    Returns neutral/default values until AIS data is integrated.
    """
    logger.info(f"[VesselAgent] Not yet implemented — returning defaults for '{state['port']}'")

    return {
        **state,
        "vessel_count":       0,
        "vessel_delay_score": 0.0,
        "mega_vessel_flag":   False,
    }