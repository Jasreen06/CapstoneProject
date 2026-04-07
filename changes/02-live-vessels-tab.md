# Live Vessels Tab — Frontend

## Overview
Added a new "Live Vessels" tab to the DockWise AI dashboard with an interactive Leaflet map displaying real-time AIS vessel positions in US waters, port congestion visualization, and filtering controls.

## Files Created

### `venv2/frontend/src/VesselMap.jsx`
Complete Leaflet-based vessel map component (~700 lines). Main features:

#### Data Hooks
- **`useVesselStream()`** — SSE hook connecting to `http://localhost:8001/api/vessels/stream`, auto-reconnects on failure (3s delay), returns `{ vessels, connected }`
- **`usePortCongestion()`** — Fetches from `http://localhost:8000/api/top-ports?top_n=120` every 60 seconds for port congestion scores

#### US Vessel Filtering
- **`resolveUSPort(destination)`** — Fuzzy-matches AIS destination strings to 55 US port names using ~30 abbreviation overrides (e.g., "LA" → "Los Angeles-Long Beach", "NYNJ" → "New York-New Jersey")
- **Geographic bounding box filter** — includes vessels physically in US waters (CONUS, Hawaii, Alaska) even without a destination
- Vessels are included if they match either a US port destination OR fall within US bounding boxes

#### Port Coordinates
- **`PORT_COORDS`** — 55 US port lat/lon coordinates covering West Coast, Gulf Coast, East Coast, Great Lakes, Hawaii, and Alaska

#### 10 Distinct Vessel Colors
Maximally-distinct colors optimized for dark map background:
| Assignment | Color | Hex |
|---|---|---|
| Cargo | Electric Blue | `#00BFFF` |
| Tanker | Hot Pink | `#FF1493` |
| Passenger | Bright Cyan | `#00FFCC` |
| Fishing | Lime Green | `#7FFF00` |
| High Speed Craft | Gold | `#FFD700` |
| Special Craft | Electric Purple | `#BF40FF` |
| Other | Silver | `#C0C0C0` |
| At Anchor | Bright Orange | `#FF6B00` |
| Moored | Coral Red | `#FF4040` |
| Engaged in Fishing | Spring Green | `#00FF7F` |

#### Vessel Shape Definitions (Legend Only)
SVG shapes defined per vessel type for the legend display:
- Cargo = Diamond, Tanker = Triangle, Passenger = Square, Fishing = Circle, High Speed Craft = Star, Special Craft = Hexagon, Other = Small Circle
- **Note:** On the map, vessels render as `CircleMarker` (colored circles) for performance. Shape icons via `Marker` + `divIcon` caused zoom lag with ~4,000 vessels. Shapes remain in the legend for reference. A future optimization (e.g., WebGL/deck.gl) could enable on-map shapes at scale.

#### Map Features
- **CartoDB Dark** tile layer — `dark_all` basemap matching the dashboard theme
- **North America bounds lock** — `maxBounds` prevents panning outside NA, `minZoom: 3`, `maxZoom: 14`
- **Canvas rendering** — `preferCanvas={true}` for fast rendering of thousands of CircleMarkers
- **Port congestion circles** — `Circle` (meter-based) per port, colored red/amber/green by congestion score (HIGH ≥67, MEDIUM 33–66, LOW <33), with dashed borders for non-congested ports
- **Major port emphasis** — 15 major US ports get larger base radius (8000m vs 3000m) and bigger center dots
- **Sonar pulse animation** — Congested ports (score ≥67) display pulsating expanding red rings via CSS `@keyframes` on a `divIcon` Marker
- **Port vessel counts** — Circle radius scales with number of inbound vessels resolved to each port

#### UI Components
- **`PortDropdown`** — Searchable dropdown listing all 55 ports, major ports marked with ★, selects to zoom into port (zoom level 10)
- **`FlyToPort`** — Map child component that calls `map.flyTo()` with smooth animation (1.2s duration)
- **`FilterDropdown`** — Reusable dropdown for vessel type and nav status filtering
- **`VesselPanel`** — Side panel showing detailed info for a selected vessel (MMSI, type, status, speed, course, destination, resolved port, position)
- **`ResetView`** — Button to reset map to US overview (zoom 4, center [37.5, -96.0])
- **`PortLayer`** — Isolated component rendering port circles, center dots, and pulse markers. Uses fixed meter radii — no zoom-state tracking — so port circles scale naturally with Leaflet zoom without triggering React re-renders.
- **Stats overlay** — Live vessel count + connection status indicator
- **Legend** — Vessel types with shape icons, nav status colors, port congestion color scale

## Files Modified

### `venv2/frontend/src/App.jsx`
Minimal changes to add the Live Vessels tab:
- Added import: `import VesselMap from "./VesselMap"`
- Added `"vessels"` to the tab array: `[["ports","Port Intelligence"],["vessels","Live Vessels"],["chokepoints","Chokepoints"],["advisor","AI Advisor"]]`
- Added VesselMap render block: `{tab === "vessels" && <VesselMap />}`

### `venv2/frontend/package.json`
Added dependencies via `npm install`:
- `leaflet` (^1.9.4)
- `react-leaflet` (^4.2.1)
- `@react-leaflet/core` (^2.1.0)

## Performance Notes
- ~4,000+ live vessels rendered simultaneously
- `CircleMarker` renders on a single Canvas layer — Leaflet transforms it as one unit during zoom
- `PortLayer` uses no React state tied to zoom — port circles scale via Leaflet's native meter-to-pixel projection
- Pulse animation is CSS-only on ~5-10 divIcon Markers (negligible overhead)
- Icon cache (`_iconCache`) prevents re-creating Leaflet icon objects across renders
