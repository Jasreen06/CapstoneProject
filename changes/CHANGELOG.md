# DockWise AI v2 — Comprehensive UI Overhaul Changelog

**Date:** April 6, 2026
**Branch:** v2-live-ais
**Author:** Pramod Krishnachari + Claude (AI pair programming)

---

## Overview

This update is a complete UI/UX overhaul of the DockWise AI v2 maritime port intelligence dashboard. It addresses data consistency issues, replaces the canvas-based map with a real interactive map, adds new visualizations, implements cross-page navigation, and improves the rerouting advisor to use server-side computed alerts.

---

## Summary of Changes

### Backend Changes (3 files modified, 1 new endpoint)
### Frontend Changes (12 files modified, 4 new files created)

---

## Detailed Changes

### 1. Backend: Port Name Resolution (`backend/config.py`)

**Problem:** AIS vessel destinations use raw, abbreviated, non-standard naming (e.g., "SOUTH PHILLY", "SAN DIEGO-US SAN", "NY/NJ", "JAX-FL"). These never matched the standardized PortWatch port names (e.g., "Philadelphia", "San Diego", "New York-New Jersey"), causing congestion lookups to fail silently and return default MEDIUM/50 scores.

**Solution:** Added `resolve_port_name()` function with ~55 keyword mappings that fuzzy-match raw AIS destination strings to known PortWatch port names.

**Changes:**
- Added `resolve_port_name(raw_destination: str) -> str | None` function
- Covers all major US ports including abbreviations, alternate names, and common AIS formats
- Updated `get_alternative_ports()` to call `resolve_port_name()` before matching

### 2. Backend: Rerouting Engine Fix (`backend/analytics/rerouting.py`)

**Problem:** `get_rerouting_for_vessel()` passed raw AIS destinations directly to `portwatch_store.get_port_overview()`, which failed for unresolved names. The fallback was `congestion_level: "MEDIUM"`, causing vessels heading to HIGH congestion ports to incorrectly show "Continue to Destination" with MEDIUM risk.

**Solution:** Now resolves port names before congestion lookup and uses "UNKNOWN" as fallback level.

**Changes:**
- Calls `resolve_port_name(raw_destination)` before looking up congestion
- Changed fallback congestion level from `"MEDIUM"` to `"UNKNOWN"` to avoid false reassurance
- Adds `resolved_port` and `raw_destination` fields to the response
- Updates `destination.port` to use the resolved name for display consistency

### 3. Backend: Rerouting Alerts Endpoint (`backend/api/routes_rerouting.py`)

**Problem:** The frontend was doing client-side matching of vessel destinations to congested ports using fragile string matching, leading to mismatches between what the rerouting tab showed and what Port Intelligence showed.

**Solution:** New server-side `GET /api/rerouting/alerts` endpoint that does the matching correctly using the backend's `resolve_port_name()` function.

**Changes:**
- Added `GET /api/rerouting/alerts` endpoint
- Server-side filtering: iterates all vessels, resolves destinations, checks if destination port has HIGH congestion
- Only returns vessels where `should_reroute=true`
- Returns `{alerts: [...], total: N, high_congestion_ports: N}`
- Capped at 50 results, sorted by congestion score descending

### 4. Frontend: Real Interactive Map (`frontend/src/components/VesselMap.jsx`)

**Problem:** The original map was a canvas-based rendering with a hand-drawn US coastline (~800 coordinate points). Users wanted "the actual live map, with all the states."

**Solution:** Complete rewrite using Leaflet + react-leaflet with OpenStreetMap tiles.

**Changes:**
- Replaced canvas-based map with `react-leaflet` MapContainer
- Uses CartoDB dark tiles (`dark_all`) matching the app's dark theme
- `FlyTo` component for animated map panning when selecting vessels
- `resolveDestPort()` client-side port name resolver for destination highlighting
- `findNearestPort()` for origin port calculation
- CircleMarker for vessels with color coding by type/status
- Polyline for projected trajectory (dead reckoning)
- Destination port highlighted with red dashed circle
- Alternative ports highlighted with green dashed circles
- Permanent tooltips on highlighted ports showing "DEST: portname" or "ALT: portname"
- Isolated mode (`isolateMode`): when navigating from rerouting, only the focused vessel is shown
- "Focused View" banner with "Show All" button to exit isolation
- Vessel type and nav status filter dropdowns with descriptions
- Legend showing vessel types and status shapes/colors
- Stats overlay (vessel count, underway/anchored/moored breakdown)
- Connection status indicator (Live/Reconnecting)

### 5. Frontend: Enhanced Vessel Detail (`frontend/src/components/VesselDetail.jsx`)

**Problem:** No origin port shown, no international destination detection, distance/ETA not displayed.

**Solution:** Added origin port detection, route visualization, distance/ETA calculations, and international destination handling.

**Changes:**
- Shows nearest port as "Current Location" with distance (e.g., "Near Philadelphia, 12 nm away")
- Route summary bar: Origin (green) -> Destination (blue)
- Resolves AIS destination to known port name (shows both raw and resolved)
- Distance in nautical miles and ETA (hours/days) computed via haversine formula
- International/unresolved destinations shown with amber globe icon and explanatory notice
- Rerouting button disabled for international destinations with "Rerouting N/A" text
- Nav status descriptions togglable via info button
- Vessel type descriptions togglable via info button
- Color-coded status badges (green=underway, orange=anchored, cyan=moored)
- "View Port Intelligence" button navigating to `/ports?port=...`

### 6. Frontend: Rerouting Tab Rewrite (`frontend/src/components/ReroutingTab.jsx`)

**Problem:** Client-side matching of vessels to congested ports produced different results than the backend, causing data mismatches (e.g., showing HIGH in the list but MEDIUM when expanded).

**Solution:** Complete rewrite to use the new server-side `/api/rerouting/alerts` endpoint.

**Changes:**
- Fetches from `GET /api/rerouting/alerts` instead of client-side filtering
- Auto-refreshes every 2 minutes
- Manual refresh button
- Each card shows: vessel name, type, MMSI, speed, raw AIS destination, resolved port, congestion badge, recommendation
- "View on Map" button navigates with URL params (focus=MMSI&dest=PORT&alts=ALT1,ALT2)
- Expandable details section shows full ReroutingPanel inline
- Shows alert count badge and HIGH congestion port count
- Manual MMSI lookup preserved as secondary section
- Proper loading and error states

### 7. Frontend: Rerouting Panel Updates (`frontend/src/components/ReroutingPanel.jsx`)

**Changes:**
- Added `showMapLink` prop for "View on Map" button
- "View Vessel & Alternatives on Map" button navigating with URL params
- Per-alternative "View route on map" links
- "View PORT Intelligence" link for destination port
- Color-coded recommendation badges (STRONG=green, MODERATE=yellow, WEAK/NONE=gray)

### 8. Frontend: Port Intelligence Dashboard (`frontend/src/components/PortDashboard.jsx`)

**Changes:**
- Reads `?port=` URL parameter for cross-page navigation
- 5-row layout:
  1. CongestionHero (full width)
  2. 7-Day Congestion Trend + Weather Conditions (side by side)
  3. Daily Port Traffic + Inbound Vessel Types (side by side)
  4. 7-Day Congestion Forecast with model selector (Prophet/XGBoost/ARIMA)
  5. Port Comparison vs Alternatives (horizontal bar chart)

### 9. Frontend: New Chart Components (3 new files)

#### `frontend/src/components/TrafficVolumeChart.jsx`
- Recharts BarChart showing daily port calls from `recent_7_days` data
- Bars colored by congestion level (green/yellow/red)
- Custom tooltip showing port calls and congestion info

#### `frontend/src/components/VesselDistributionChart.jsx`
- Recharts PieChart (donut) showing inbound vessel type distribution
- Filters vessel list by destination matching selected port
- Color-coded by vessel type with legend

#### `frontend/src/components/PortComparisonChart.jsx`
- Recharts horizontal BarChart comparing selected port vs alternatives' congestion scores
- Fetches alternative port congestion data on demand
- Reference lines at 33 (LOW threshold) and 66 (HIGH threshold)
- Selected port highlighted with white border

### 10. Frontend: Constants Expansion (`frontend/src/utils/constants.js`)

**Changes:**
- Added `CONGESTION_BG` for badge background styling
- Added `VESSEL_TYPE_COLORS` (Cargo=blue, Tanker=amber, Passenger=purple, Fishing=green)
- Added `NAV_STATUS_COLORS` (Anchored=orange, Moored=cyan, Fishing=green)
- Added `VESSEL_TYPE_FILTER_OPTIONS` and `NAV_STATUS_FILTER_OPTIONS` arrays
- Added `VESSEL_TYPE_DESCRIPTIONS` and `NAV_STATUS_DESCRIPTIONS` with explanations
- Added `PORT_ALTERNATIVES` mapping (mirrors backend ALTERNATIVES config)
- Added `MAP_LEGEND` with shape info (circle/diamond/square)
- Added more `PORT_COORDS` entries (Jacksonville, Tampa, Mobile, Portland OR)

### 11. Frontend: Trajectory Utilities (`frontend/src/utils/trajectory.js`)

**Changes:**
- Added `haversineNm(lat1, lon1, lat2, lon2)` — great circle distance in nautical miles
- Added `estimateEta(distNm, sogKnots)` — returns hours using 90% of SOG as average speed
- `projectTrajectory()` for dead reckoning vessel position projection

### 12. Frontend: CSS Animations & Styling (`frontend/src/index.css`)

**Changes:**
- Added Leaflet CSS import
- Added custom animations: `fadeInUp`, `pulseRing`, `glowPulse`
- Added corresponding utility classes: `.animate-fadeInUp`, `.animate-pulse-ring`, `.animate-glow-pulse`
- Custom dark scrollbar styling
- Custom Leaflet tooltip styling (dark theme: `#1e293b` background, `#334155` border)
- Hidden default Leaflet attribution

### 13. Frontend: CongestionHero Polish (`frontend/src/components/CongestionHero.jsx`)

**Changes:**
- Pulsating glow animation on HIGH congestion score ring
- Larger score display with animated SVG ring
- Border color changes to red for HIGH congestion

### 14. Frontend: Layout Polish (`frontend/src/components/Layout.jsx`)

**Changes:**
- Gradient navbar background
- Animated ping dot on LIVE indicator
- Active tab styled with blue background and shadow
- Responsive tab labels (hidden on small screens)

### 15. Frontend: Dependencies Added (`frontend/package.json`)

**New dependencies:**
- `leaflet: ^1.9.4` — Map rendering library
- `react-leaflet: ^5.0.0` — React bindings for Leaflet

---

## Data Flow (Before vs After)

### Before (Broken):
```
AIS destination "SOUTH PHILLY"
  -> portwatch_store.get_port_overview("SOUTH PHILLY")
  -> No match -> fallback {score: 50, level: "MEDIUM"}
  -> Rerouting says "Continue to Destination"
  -> But Port Intelligence shows Philadelphia as HIGH (97)
  -> DATA MISMATCH
```

### After (Fixed):
```
AIS destination "SOUTH PHILLY"
  -> resolve_port_name("SOUTH PHILLY") -> "Philadelphia"
  -> portwatch_store.get_port_overview("Philadelphia")
  -> {score: 96.8, level: "HIGH"}
  -> Rerouting says "Rerouting Recommended"
  -> Port Intelligence also shows HIGH (97)
  -> CONSISTENT DATA
```

---

## Cross-Page Navigation Flow

```
Rerouting Tab
  -> "View on Map" button
  -> /vessels?focus=MMSI&dest=Philadelphia&alts=Baltimore,Norfolk
  -> VesselMap: isolated mode, only focused vessel shown
  -> Destination port (red), alternatives (green) highlighted
  -> Trajectory line projected from vessel

Vessel Detail Panel
  -> "View Port Intelligence" button
  -> /ports?port=Philadelphia
  -> PortDashboard: auto-selects Philadelphia
  -> Shows all 5 visualization cards

Port Intelligence
  -> Port Comparison chart
  -> Click alternative port (via sidebar)
  -> View and compare congestion data
```

---

## Files Changed Summary

| File | Type | Action |
|------|------|--------|
| `backend/config.py` | Backend | Modified — added `resolve_port_name()` |
| `backend/analytics/rerouting.py` | Backend | Modified — uses resolved names, UNKNOWN fallback |
| `backend/api/routes_rerouting.py` | Backend | Modified — added `GET /api/rerouting/alerts` |
| `frontend/src/components/VesselMap.jsx` | Frontend | Rewritten — Leaflet map, isolation mode |
| `frontend/src/components/VesselDetail.jsx` | Frontend | Modified — origin, distance, ETA, international |
| `frontend/src/components/ReroutingTab.jsx` | Frontend | Rewritten — uses server alerts endpoint |
| `frontend/src/components/ReroutingPanel.jsx` | Frontend | Modified — map links, port intelligence links |
| `frontend/src/components/PortDashboard.jsx` | Frontend | Modified — URL params, 5-row layout |
| `frontend/src/components/Layout.jsx` | Frontend | Modified — gradient, animation, polish |
| `frontend/src/components/CongestionHero.jsx` | Frontend | Modified — glow animation |
| `frontend/src/components/TrafficVolumeChart.jsx` | Frontend | **New** — daily port traffic bar chart |
| `frontend/src/components/VesselDistributionChart.jsx` | Frontend | **New** — vessel type donut chart |
| `frontend/src/components/PortComparisonChart.jsx` | Frontend | **New** — port vs alternatives bar chart |
| `frontend/src/utils/constants.js` | Frontend | Modified — colors, filters, descriptions, mappings |
| `frontend/src/utils/trajectory.js` | Frontend | Modified — haversine, ETA functions |
| `frontend/src/index.css` | Frontend | Modified — Leaflet CSS, animations, tooltips |
| `frontend/package.json` | Frontend | Modified — leaflet, react-leaflet deps |
