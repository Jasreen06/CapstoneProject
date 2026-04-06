# DockWise AI v2 — New Features Documentation

## 1. Interactive Leaflet Map (Replaced Canvas)

**Location:** `frontend/src/components/VesselMap.jsx`

The canvas-based map has been replaced with a fully interactive Leaflet map using OpenStreetMap tiles (CartoDB dark theme).

**Features:**
- Real geographic map with all US states, coastlines, and waterways visible
- Smooth zoom and pan interaction
- Animated fly-to when selecting vessels or navigating from other pages
- CartoDB dark tile layer matching the app's dark UI theme

---

## 2. Vessel Filtering by Navigation Status

**Location:** `frontend/src/components/VesselMap.jsx`, `frontend/src/utils/constants.js`

Users can now filter vessels by their navigation status in addition to vessel type.

**Filter Options:**
- All Statuses
- Under Way (nav_status=0)
- At Anchor (nav_status=1)
- Moored (nav_status=5)
- Fishing (nav_status=7)

**Visual Differentiation:**
| Status | Color | Description |
|--------|-------|-------------|
| Under Way | Vessel type color | Moving under engine power |
| At Anchor | Orange (#f97316) | Stationary, anchored in open water |
| Moored | Cyan (#06b6d4) | Tied to a dock or berth |
| Fishing | Green (#22c55e) | Actively fishing with gear deployed |

Each filter option includes a descriptive tooltip explaining what the status means.

---

## 3. Vessel Origin Detection

**Location:** `frontend/src/components/VesselDetail.jsx`

The vessel detail panel now shows the nearest known US port to the vessel's current position.

**Display:**
- "Current Location" section with green navigation icon
- Shows "Near {PortName}" with distance in nautical miles
- "View Port Intelligence" button for the origin port
- Uses haversine distance calculation against all PORT_COORDS entries

---

## 4. Distance and ETA Calculation

**Location:** `frontend/src/components/VesselDetail.jsx`, `frontend/src/utils/trajectory.js`

**Display:**
- Distance to destination in nautical miles
- Estimated time of arrival based on vessel speed
  - Uses 90% of Speed Over Ground (SOG) as average speed
  - Displayed as hours (<24h) or days (>24h) with hour equivalent
- Route summary bar showing Origin -> Destination

---

## 5. International Destination Detection

**Location:** `frontend/src/components/VesselDetail.jsx`

Vessels with destinations that don't match any tracked US port are identified as international/unresolved.

**Display:**
- Amber globe icon next to destination
- "International / Unresolved destination" label
- Informational notice: "This vessel's destination does not match a tracked US port. Rerouting analysis and congestion data are only available for US ports."
- Rerouting analysis button disabled with "Rerouting N/A (International)" text

---

## 6. Server-Side Rerouting Alerts

**Location:** `frontend/src/components/ReroutingTab.jsx`, `backend/api/routes_rerouting.py`

The rerouting advisor now uses a server-computed alerts endpoint for accurate data.

**Features:**
- Auto-loads on page visit, refreshes every 2 minutes
- Manual refresh button
- Shows total alert count and number of HIGH congestion ports
- Each alert card shows:
  - Vessel name, type, MMSI, speed
  - Raw AIS destination and resolved port name
  - Congestion badge with score
  - "Rerouting Recommended" label
  - "View on Map" button
  - Expandable details with full rerouting analysis

---

## 7. Isolated Map View (Focused Vessel)

**Location:** `frontend/src/components/VesselMap.jsx`

When navigating from the rerouting tab via "View on Map", only the selected vessel is shown.

**Features:**
- URL parameter `?focus=MMSI` triggers isolation mode
- Only the focused vessel is rendered (not all 4000+)
- Destination port highlighted with red dashed circle and permanent "DEST" label
- Alternative ports highlighted with green dashed circles and "ALT" labels
- Projected trajectory line (dashed blue)
- "Focused View" banner at top center
- "Show All" button to exit isolation and show all vessels
- "Reset" button to return to full US view

---

## 8. Cross-Page Navigation

**Flow diagram:**
```
Rerouting Tab
  |-- "View on Map" -> /vessels?focus=MMSI&dest=PORT&alts=ALT1,ALT2
  |-- "View PORT Intelligence" -> /ports?port=PORT

Vessel Detail Panel
  |-- "View Port Intelligence" -> /ports?port=PORT
  |-- Origin port "View Port Intelligence" -> /ports?port=ORIGIN

Port Intelligence
  |-- Port sidebar selection -> updates ?port= URL param
```

---

## 9. Port Intelligence Visualizations (3 New Charts)

### Traffic Volume Chart (`TrafficVolumeChart.jsx`)
- Bar chart showing daily port calls over the last 7 days
- Bars colored by congestion level (green=LOW, yellow=MEDIUM, red=HIGH)
- Custom tooltip with port calls count and congestion info

### Vessel Distribution Chart (`VesselDistributionChart.jsx`)
- Donut/pie chart showing the mix of inbound vessel types
- Filters all tracked vessels by destination matching the selected port
- Shows vessel count by type with color-coded legend
- Types: Cargo, Tanker, Passenger, Fishing, Tug, High Speed, Other

### Port Comparison Chart (`PortComparisonChart.jsx`)
- Horizontal bar chart comparing selected port vs its regional alternatives
- Fetches real-time congestion data for each alternative port
- Reference lines at score 33 (LOW threshold) and 66 (HIGH threshold)
- Selected port highlighted with white border
- Tooltip showing congestion level, score, and port calls

### Updated Dashboard Layout
```
Row 1: Congestion Hero (score ring + stats)
Row 2: 7-Day Trend (line) | Weather Conditions
Row 3: Daily Traffic (bar) | Vessel Types (donut)
Row 4: 7-Day Forecast (line, 3 models)
Row 5: Port Comparison (horizontal bar)
```

---

## 10. Enhanced CongestionHero

**Location:** `frontend/src/components/CongestionHero.jsx`

- Animated SVG score ring with smooth transitions
- Pulsating glow effect when congestion is HIGH
- Border color changes to red for HIGH congestion cards
- Shows: congestion score/100, port calls, vs 90-day average, trend direction

---

## 11. Polished Navigation Bar

**Location:** `frontend/src/components/Layout.jsx`

- Gradient background
- Animated ping dot on LIVE indicator
- Active tab styled with blue background and drop shadow
- Responsive: tab labels hidden on small screens (icons only)
- UTC clock in the corner
