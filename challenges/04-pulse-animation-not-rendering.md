# Challenge: Pulse Animation Not Rendering on Congested Ports

## Symptom
Highly congested ports (score >= 67) were supposed to show a pulsating red "sonar ring" animation. The initial implementation used CSS classes on Leaflet `Circle` SVG paths, but the animation either did not appear or was barely visible.

## Root Cause
The first approach applied a `className="pulse-ring"` to a react-leaflet `<Circle>` component and used CSS `@keyframes` to animate `stroke-width` and `stroke-opacity` on the resulting SVG `<path>` element.

Two problems:
1. **react-leaflet's `Circle` doesn't reliably pass `className` to the underlying SVG path.** The Leaflet Circle creates an SVG `<path>` element, but react-leaflet's prop-to-DOM mapping doesn't always apply custom class names to the rendered SVG element.
2. **Stroke-width animation doesn't create a visually expanding ring.** Animating `stroke-width` on an SVG path makes the border thicker, but the circle doesn't visually grow outward, it just gets a fatter border in place.

## Resolution
Replaced the CSS-on-SVG approach with a `Marker` + `L.divIcon` that contains HTML `<div>` elements animated with CSS `transform: scale()` and `opacity`:

```javascript
const _pulseIcon = L.divIcon({
  className: "",
  html: `<div style="...">
    <div class="sonar-ring ring-1"></div>
    <div class="sonar-ring ring-2"></div>
  </div>`,
  iconSize: [60, 60],
  iconAnchor: [30, 30],
});
```

```css
@keyframes sonar-expand {
  0%   { transform: scale(0.5); opacity: 0.8; }
  100% { transform: scale(2.5); opacity: 0; }
}
.sonar-ring {
  position: absolute;
  width: 100%; height: 100%;
  border: 2px solid #EF4444;
  border-radius: 50%;
  animation: sonar-expand 2s ease-out infinite;
}
.ring-2 { animation-delay: 1s; }
```

### Why This Works
- `transform: scale()` on a `<div>` genuinely scales the element outward: creating a visible expanding ring effect
- Only ~5-10 congested ports get pulse markers at any time (negligible DOM overhead vs 4,000 vessel markers)
- The `Marker` + `divIcon` performance concern that affects vessels doesn't apply here because there are so few pulse markers

## Files Changed
- `venv2/frontend/src/VesselMap.jsx`: pulse icon definition and PortLayer rendering logic
