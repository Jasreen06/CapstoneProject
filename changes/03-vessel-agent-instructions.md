# Vessel Agent Implementation Instructions

## Overview
Created a detailed instruction file for an AI agent (Antigravity/Cursor) to implement the `vessel_agent.py` risk assessment agent. This file was generated in a prior session and the agent has already executed it — the vessel agent is now implemented and committed.

## File Created

### `venv2/backend/VESSEL_AGENT_INSTRUCTIONS.md`
~470-line instruction document containing:
- **Scope guardrails** — ONLY modify `vessel_agent.py`, DO NOT touch any other file
- **Contract** — `run(state: RiskState) -> RiskState` function signature, reads `state["port"]`, writes `vessel_count`, `vessel_delay_score`, `mega_vessel_flag`
- **Data source** — PortWatch historical data via `data_cleaning.load_and_clean()` and `get_port_daily_series()`
- **Implementation strategy**:
  - `vessel_count`: 7-day rolling average portcalls × 3 (72-hour projection)
  - `vessel_delay_score`: recent-vs-baseline ratio with variance bonus, clamped 0–1
  - `mega_vessel_flag`: container call threshold (≥5/day) OR hardcoded major port list
- **Complete replacement code** for `vessel_agent.py`
- **Testing instructions** with expected outputs for Houston

## Status
The vessel agent has been implemented and is live in the risk assessment pipeline. The instructions file remains as documentation of the implementation approach.
