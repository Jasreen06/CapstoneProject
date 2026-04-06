# DockWise AI v2 — Bug Fixes Documentation

## Critical Bug Fix: Port Name Resolution Mismatch

### Symptom
- Rerouting tab showed a vessel heading to San Diego as HIGH congestion in the list
- But expanding the card showed "Continue to Destination — MEDIUM (50)"
- Port Intelligence page showed San Diego as HIGH (73)
- Scores were inconsistent across pages for the same port

### Root Cause
AIS (Automatic Identification System) vessel destinations are free-text fields entered by ship crews. They use abbreviated, non-standard naming:

| AIS Destination | Expected Port | What Backend Matched |
|----------------|---------------|---------------------|
| `SOUTH PHILLY` | Philadelphia | (none) -> default MEDIUM |
| `SAN DIEGO-US SAN` | San Diego | (none) -> default MEDIUM |
| `NY/NJ` | New York-New Jersey | (none) -> default MEDIUM |
| `JAX-FL` | Jacksonville | (none) -> default MEDIUM |
| `NOLA` | New Orleans | (none) -> default MEDIUM |
| `LA/LB` | Los Angeles-Long Beach | (none) -> default MEDIUM |

The `portwatch_store.get_port_overview()` function does an exact case-insensitive match against its dataset. When the raw AIS string didn't match, the fallback was `{congestion_score: 50.0, congestion_level: "MEDIUM"}` — making every unresolved port appear as moderate risk regardless of actual congestion.

### Fix Applied

**1. `backend/config.py` — Added `resolve_port_name()`**
- Keyword-based fuzzy matching with ~55 patterns
- Handles abbreviations (JAX, NOLA, LA/LB, PHILLY)
- Handles compound names (SAN DIEGO-US SAN, PORT ARTHUR TX)
- Returns the canonical PortWatch port name or None

**2. `backend/analytics/rerouting.py` — Uses resolved names**
- Calls `resolve_port_name()` before any congestion lookup
- Changed fallback level from "MEDIUM" to "UNKNOWN" to avoid false reassurance
- Adds both `resolved_port` and `raw_destination` to response

**3. `backend/api/routes_rerouting.py` — Server-side alerts**
- New endpoint does resolution server-side, eliminating client/server mismatch
- Only returns vessels where rerouting is truly recommended

**4. `frontend/src/components/ReroutingTab.jsx` — Uses server endpoint**
- Replaced buggy client-side string matching with server `/api/rerouting/alerts`
- Data is now computed once, correctly, on the backend

### Verification
After the fix, the same vessel (GENESIS VALIANT → Philadelphia):
- Rerouting alert: HIGH (97) — Rerouting Recommended
- Rerouting detail: Philadelphia HIGH (96.8)
- Port Intelligence: Philadelphia HIGH (96.8)
- All scores now match.

---

## Bug Fix: Map Showing Rough Canvas Coastline

### Symptom
Instead of a real map with states and geography, users saw a rough hand-drawn outline of the US coastline rendered on an HTML canvas.

### Root Cause
The original VesselMap.jsx used a pure canvas-based renderer with a custom `coastline.js` file containing ~800 coordinate points that approximated the US coastline.

### Fix Applied
Complete rewrite of VesselMap.jsx using Leaflet + react-leaflet with CartoDB dark OpenStreetMap tiles. Provides a full interactive map with zoom, pan, and detailed geography.

---

## Bug Fix: "View on Map" Showing All Vessels

### Symptom
Clicking "View on Map" from the rerouting tab navigated to the map page but showed all 4000+ vessels, making it impossible to find the vessel of interest.

### Root Cause
No filtering mechanism existed — the map always rendered the full vessel list.

### Fix Applied
Added `isolateMode` to VesselMap.jsx. When URL contains `?focus=MMSI`, only that vessel is rendered. A "Focused View" banner appears with a "Show All" button to exit isolation mode.

---

## Bug Fix: Inconsistent Congestion Scores Between Pages

### Symptom
A port would show different congestion scores on the Rerouting page vs the Port Intelligence page.

### Root Cause
Same as the port name resolution bug — the rerouting engine was looking up an unresolved name and falling back to default scores, while Port Intelligence used the correct port name from its dropdown.

### Fix Applied
All congestion lookups now go through `resolve_port_name()` first, ensuring the same canonical port name is used everywhere.
