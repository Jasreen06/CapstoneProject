"""
port_anchor_thresholds.py
=========================
Per-port anchor-count thresholds used by the staleness reconciliation logic
in api.py:port_overview (Phase 6A).

When PortWatch data is >7 days stale, /api/overview asks the AIS service for
the live anchor count near the port. If that count meets-or-exceeds the
threshold below, the displayed congestion tier is bumped one level upward.

Source of values
----------------
v1 heuristic. Numbers are tuned-by-eye to roughly approximate p75 of typical
anchor concentrations at each port based on public anchorage capacity and
historical reporting. They are NOT empirically derived from logged AIS data
and should be replaced once Phase 7 (AIS history persistence) lands.

Default for unlisted ports is 5, which is also the floor enforced by
`max(get_anchor_threshold(port), 5)` in api.py.
"""

from __future__ import annotations

DEFAULT_THRESHOLD = 5

_ANCHOR_P75: dict[str, int] = {
    "Los Angeles-Long Beach":  25,
    "New York-New Jersey":     20,
    "Houston":                 20,
    "South Louisiana":         18,
    "Savannah":                15,
    "Seattle":                 12,
    "Tacoma":                  12,
    "Oakland":                 12,
    "Charleston":              12,
    "Norfolk":                 12,
    "New Orleans":             10,
    "Baltimore":                8,
    "Jacksonville":             8,
    "Miami":                    8,
    "Mobile":                   8,
    "Tampa":                    6,
    "Corpus Christi":          10,
    "Beaumont":                 8,
    "Port Arthur":              6,
    "Lake Charles":             6,
    "Galveston":                6,
    "Philadelphia":             6,
    "Boston":                   6,
    "Portland":                 6,
    "San Diego":                6,
}


def get_anchor_threshold(port: str) -> int:
    """Return the p75-anchor-count threshold for a port, or DEFAULT_THRESHOLD."""
    return _ANCHOR_P75.get(port, DEFAULT_THRESHOLD)
