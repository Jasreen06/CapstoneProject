# Challenge: Zoom-Responsive Port Circles Cause Performance Issues

## Symptom
After adding zoom-responsive scaling to port congestion circles (so they appear larger when zoomed out and smaller when zoomed in), the map became laggy during zoom animations. Circles appeared to "catch up" after the zoom finished rather than scaling smoothly with the map.

## Root Cause
The implementation tracked zoom level in React state via `useMapEvents({ zoomend })` and used it to compute a scale factor for port `Circle` radii. This created a cascading performance problem:

### Attempt 1: Exponential scaling in VesselMap state
```javascript
const [zoomLevel, setZoomLevel] = useState(4);
// scaleFactor = Math.pow(2, (12 - zoomLevel)) * 0.15
// At zoom 4: 2^8 * 0.15 = 38.4x (unbounded growth)
```
**Problem:** The exponential formula produced extreme values (38x at zoom 4, 0.15x at zoom 12). Port circles became enormous when zoomed out. More critically, `zoomLevel` state lived in the main `VesselMap` component, so every zoom change re-rendered the entire component tree — including ~4,000 vessel markers.

### Attempt 2: Clamped linear scaling in PortLayer child
Moved zoom tracking into a `PortLayer` child component to isolate re-renders from vessel markers:
```javascript
function PortLayer({ portMarkers, showPorts }) {
  const [zoom, setZoom] = useState(4);
  useMapEvents({ zoomend: (e) => setZoom(e.target.getZoom()) });
  const scale = 0.5 + (11 - Math.min(Math.max(zoom, 3), 11)) * (7.5 / 8);
  // ...render 55 port Circles with radius * scale
}
```
**Problem:** While this prevented vessel marker re-renders, React still re-rendered all 55 port `Circle` elements with new radii after each zoom animation ended. The Leaflet `Circle` component (meter-based) needs to recalculate its SVG/Canvas path when the radius changes, causing a visible "jump" where circles resize in a single frame after the smooth zoom animation completes.

### Why Leaflet Circles Don't Need Zoom Scaling
Leaflet `Circle` uses a meter-based radius. As you zoom in, Leaflet's internal projection naturally converts meters to more pixels — the circle automatically grows on screen. As you zoom out, it shrinks. This is the correct physical behavior (a 5km zone looks bigger when you zoom into it).

The perceived problem — "circles are too small at US overview zoom" — was actually a radius calibration issue, not a zoom scaling issue. Major ports needed a larger base radius (8000m vs 3000m), and vessel count should influence the radius.

## Resolution
Removed all zoom-state tracking from `PortLayer`. Port circles use fixed `baseRadius` values that scale naturally via Leaflet's built-in meter-to-pixel projection:

```javascript
const baseRadius = isMajor
  ? Math.min(8000 + vesselCount * 500, 30000)   // major ports: 8-30km
  : Math.min(3000 + vesselCount * 400, 25000);  // other ports: 3-25km
```

**Result:**
- No React re-renders on zoom — `PortLayer` has no state at all
- Circles scale via Leaflet's native projection (hardware-accelerated canvas transform)
- Major ports with high vessel counts are visible even at US overview zoom
- Smooth, jank-free zoom animation

## Key Takeaway
When using Leaflet's Canvas renderer (`preferCanvas={true}`), zoom animations are handled by the browser/GPU as a single transform on the canvas layer. Injecting React state updates into the zoom cycle breaks this — React re-renders components between frames, causing visible stutter. The fix is to let Leaflet handle zoom natively and avoid React state that depends on zoom level.

## Files Changed
- `venv2/frontend/src/VesselMap.jsx` — removed ZoomTracker, removed zoom state from PortLayer
