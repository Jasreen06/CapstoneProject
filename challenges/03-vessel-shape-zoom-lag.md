# Challenge: Vessel Shape Icons Cause Zoom Lag

## Symptom
After replacing vessel dots with distinct SVG shape icons (diamond for cargo, triangle for tanker, etc.), zooming in and out became visibly laggy. The map animation stuttered and felt like "layers catching up one after another" instead of smooth panning/zooming.

## Root Cause
The shape icons used Leaflet `Marker` with `L.divIcon`, this creates a real DOM `<div>` element per vessel. With ~4,000 live vessels on screen, that meant ~4,000 individual DOM nodes that the browser had to reposition during every zoom frame.

### CircleMarker vs Marker Performance

| Approach | Rendering | Zoom Behaviour | ~4,000 Vessels |
|----------|-----------|----------------|----------------|
| `CircleMarker` + `preferCanvas` | Single `<canvas>` element | Browser transforms one canvas layer as a unit | Smooth |
| `Marker` + `L.divIcon` | One `<div>` per marker | Browser repositions 4,000 individual DOM elements per frame | Laggy |

The `preferCanvas={true}` prop on `MapContainer` only affects `CircleMarker` and `Circle`, it has no effect on `Marker`, which always renders as DOM elements.

### Why Shapes Were Attempted
Different vessel types (Cargo, Tanker, Passenger, Fishing, etc.) are hard to distinguish when they're all identical colored dots. Shape icons provide instant visual differentiation. The shapes work correctly, the only problem is performance at scale.

## Resolution
Reverted vessels back to `CircleMarker` (colored circles) for on-map rendering. Shape definitions (`VESSEL_SHAPES`, `LEGEND_SHAPES`) remain in the code and are used in the legend panel for reference.

**Current state:**
- Map: `CircleMarker` with `preferCanvas={true}`: fast, smooth zooming
- Legend: Shape SVGs per vessel type: visual reference for what each color means

### Future Fix
To get shapes on the map at this scale, the rendering layer would need to change from Leaflet SVG/Canvas to a GPU-accelerated approach:
- **deck.gl** (WebGL scatterplot layer with custom icons)
- **Leaflet.glify** (WebGL plugin for Leaflet)
- **Mapbox GL JS** (native WebGL map with symbol layers)

These can render 10,000+ custom icons at 60fps because the GPU handles the transforms instead of the browser's DOM layout engine.

## Files Changed
- `venv2/frontend/src/VesselMap.jsx`: reverted to CircleMarker, kept shape code for legend
