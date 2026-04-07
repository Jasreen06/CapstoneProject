import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Circle, Marker, Tooltip, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Ship, Wifi, WifiOff, RotateCcw, ChevronDown, Anchor, MapPin, Search } from "lucide-react";

/* ── Design tokens (match App.jsx) ────────────────────────── */
const T = {
  navy: "#0B1426", navy2: "#111D35", navy3: "#162140",
  border: "#2A3F62", borderL: "#354D75",
  teal: "#00C9A7", amber: "#F59E0B", red: "#EF4444",
  green: "#10B981", blue: "#3B82F6",
  ink: "#E8EFF8", inkMid: "#8FA3BF", inkDim: "#4A6080",
  sans: "'Syne', sans-serif", mono: "'JetBrains Mono', monospace",
};

const AIS_BASE = "http://localhost:8001";
const API_BASE = "http://localhost:8004";

/* ── US Port Coordinates ─────────────────────────────────── */
const PORT_COORDS = {
  "Los Angeles-Long Beach": [33.75, -118.22], "Oakland": [37.80, -122.27],
  "Seattle": [47.60, -122.34], "Tacoma": [47.27, -122.41],
  "San Diego": [32.71, -117.17], "San Francisco": [37.79, -122.39],
  "Port Hueneme": [34.15, -119.20], "Portland, OR": [45.52, -122.68],
  "Longview": [46.14, -122.93], "Everett": [47.97, -122.20],
  "Bellingham": [48.74, -122.49],
  "Anchorage (Alaska)": [61.22, -149.90], "Dutch Harbor": [53.89, -166.54],
  "Kodiak": [57.80, -152.41], "Honolulu": [21.31, -157.87], "Hilo": [19.73, -155.09],
  "Houston": [29.75, -95.08], "South Louisiana": [29.95, -90.36],
  "New Orleans": [29.95, -90.06], "Baton Rouge": [30.44, -91.19],
  "Beaumont": [30.08, -94.10], "Port Arthur": [29.88, -93.93],
  "Corpus Christi": [27.80, -97.40], "Freeport": [28.95, -95.36],
  "Galveston": [29.30, -94.80], "Texas City": [29.39, -94.90],
  "Lake Charles": [30.22, -93.21], "Mobile": [30.69, -88.04],
  "Tampa": [27.94, -82.45], "Port Lavaca": [28.62, -96.63],
  "Brownsville": [25.93, -97.49], "Gulfport": [30.37, -89.09],
  "Pascagoula": [30.35, -88.56], "Pensacola": [30.42, -87.22],
  "Panama City": [30.16, -85.66], "Fourchon": [29.11, -90.20],
  "New York-New Jersey": [40.68, -74.04], "Philadelphia": [39.87, -75.14],
  "Baltimore": [39.27, -76.58], "Norfolk": [36.85, -76.30],
  "Port of Virginia": [36.93, -76.33], "Newport News": [37.00, -76.43],
  "Savannah": [32.08, -81.09], "Charleston": [32.78, -79.94],
  "Jacksonville": [30.33, -81.66], "Miami": [25.77, -80.19],
  "Port Everglades": [26.09, -80.12], "Canaveral Harbor": [28.41, -80.59],
  "Wilmington, NC": [34.24, -77.95], "Brunswick": [31.15, -81.49],
  "Boston": [42.36, -71.05], "Providence": [41.82, -71.40],
  "Portland, ME": [43.66, -70.25], "Marcus Hook": [39.82, -75.41],
  "Wilmington, DE": [39.74, -75.55], "Dominion Cove Point": [38.39, -76.38],
  "Chicago": [41.85, -87.65], "Detroit": [42.33, -83.05],
  "Cleveland": [41.51, -81.69], "Toledo": [41.66, -83.55],
  "Duluth": [46.78, -92.10], "Milwaukee": [43.04, -87.91],
  "Gary": [41.60, -87.35], "Green Bay": [44.52, -88.02],
  "Erie": [42.13, -80.08], "Ashtabula": [41.90, -80.79],
};

/* ── Destination → US port fuzzy matching ────────────────── */
const _PORT_KEYWORDS = {};
for (const name of Object.keys(PORT_COORDS)) {
  _PORT_KEYWORDS[name.toLowerCase()] = name;
  for (const part of name.split(/[-,]/)) {
    const trimmed = part.trim().toLowerCase();
    if (trimmed.length > 3) _PORT_KEYWORDS[trimmed] = name;
  }
}
Object.assign(_PORT_KEYWORDS, {
  "la": "Los Angeles-Long Beach", "long beach": "Los Angeles-Long Beach",
  "lb": "Los Angeles-Long Beach", "la/lb": "Los Angeles-Long Beach",
  "nyc": "New York-New Jersey", "new york": "New York-New Jersey",
  "nynj": "New York-New Jersey", "ny/nj": "New York-New Jersey",
  "nola": "New Orleans", "south philly": "Philadelphia",
  "philly": "Philadelphia", "san fran": "San Francisco",
  "sf": "San Francisco", "jax": "Jacksonville",
  "bal": "Baltimore", "balt": "Baltimore",
  "sav": "Savannah", "chs": "Charleston",
  "mia": "Miami", "tpa": "Tampa", "hou": "Houston",
  "corpus": "Corpus Christi", "pt arthur": "Port Arthur",
  "lake chas": "Lake Charles", "norf": "Norfolk",
});

function resolveUSPort(destination) {
  if (!destination) return null;
  const dest = destination.toUpperCase().trim();
  const isLikelyUS = /\bUS\b|USA|UNITED STATES/.test(dest);
  const destLower = destination.toLowerCase().trim();
  if (_PORT_KEYWORDS[destLower]) return _PORT_KEYWORDS[destLower];
  for (const [keyword, portName] of Object.entries(_PORT_KEYWORDS)) {
    if (destLower.includes(keyword)) return portName;
  }
  if (isLikelyUS) return "__US_UNKNOWN__";
  return null;
}

/* ── 10 maximally-distinct colors for dark map background ── */
const TYPE_COLORS = {
  "Cargo": "#00BFFF",           // electric blue
  "Tanker": "#FF1493",          // hot pink
  "Passenger": "#00FFCC",       // bright cyan
  "Fishing": "#7FFF00",         // lime green
  "High Speed Craft": "#FFD700", // gold
  "Special Craft": "#BF40FF",   // electric purple
  "Other": "#C0C0C0",           // silver
  "Unknown": "#4A6080",         // dim
};

const STATUS_COLORS = {
  "At Anchor": "#FF6B00",       // bright orange
  "Moored": "#FF4040",          // coral red
  "Engaged in Fishing": "#00FF7F", // spring green
};

function getVesselColor(v) {
  return STATUS_COLORS[v.nav_status_label] || TYPE_COLORS[v.vessel_type_label] || TYPE_COLORS["Unknown"];
}

/* ── Vessel SVG shapes per type ────────────────────────────── */
const VESSEL_SHAPES = {
  "Cargo":            (c) => `<polygon points="6,0 12,6 6,12 0,6" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
  "Tanker":           (c) => `<polygon points="6,0 12,11 0,11" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
  "Passenger":        (c) => `<rect x="1" y="1" width="10" height="10" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
  "Fishing":          (c) => `<circle cx="6" cy="6" r="5" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
  "High Speed Craft": (c) => `<polygon points="6,0 7.8,4.2 12,4.6 8.8,7.4 9.7,12 6,9.6 2.3,12 3.2,7.4 0,4.6 4.2,4.2" fill="${c}" stroke="${c}" stroke-width="0.3"/>`,
  "Special Craft":    (c) => `<polygon points="6,0 10.5,3 10.5,9 6,12 1.5,9 1.5,3" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
  "Other":            (c) => `<circle cx="6" cy="6" r="3.5" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
  "Unknown":          (c) => `<circle cx="6" cy="6" r="3" fill="${c}" stroke="${c}" stroke-width="0.5"/>`,
};

// Legend-sized SVG shapes (inline, 10×10)
const LEGEND_SHAPES = {
  "Cargo":            (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><polygon points="6,0 12,6 6,12 0,6" fill="${c}"/></svg>`,
  "Tanker":           (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><polygon points="6,0 12,11 0,11" fill="${c}"/></svg>`,
  "Passenger":        (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><rect x="1" y="1" width="10" height="10" fill="${c}"/></svg>`,
  "Fishing":          (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="${c}"/></svg>`,
  "High Speed Craft": (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><polygon points="6,0 7.8,4.2 12,4.6 8.8,7.4 9.7,12 6,9.6 2.3,12 3.2,7.4 0,4.6 4.2,4.2" fill="${c}"/></svg>`,
  "Special Craft":    (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><polygon points="6,0 10.5,3 10.5,9 6,12 1.5,9 1.5,3" fill="${c}"/></svg>`,
  "Other":            (c) => `<svg width="10" height="10" viewBox="0 0 12 12"><circle cx="6" cy="6" r="3.5" fill="${c}"/></svg>`,
};

// Icon cache to avoid re-creating divIcons on every render
const _iconCache = {};
function getVesselIcon(type, color, isSelected) {
  const size = isSelected ? 16 : 12;
  const key = `${type}|${color}|${isSelected ? 1 : 0}`;
  if (_iconCache[key]) return _iconCache[key];
  const shapeFn = VESSEL_SHAPES[type] || VESSEL_SHAPES["Unknown"];
  const svg = `<svg width="${size}" height="${size}" viewBox="0 0 12 12" xmlns="http://www.w3.org/2000/svg">${shapeFn(color)}</svg>`;
  const icon = L.divIcon({
    html: svg,
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
  _iconCache[key] = icon;
  return icon;
}

// Cached divIcon for congested-port sonar pulse (pixel-based, zoom-independent)
const _pulseIcon = L.divIcon({
  html: '<div class="port-sonar"><div class="port-sonar-ring"></div><div class="port-sonar-ring"></div></div>',
  className: "",
  iconSize: [60, 60],
  iconAnchor: [30, 30],
});

/* ── SSE hook for live vessels ───────────────────────────── */
function useVesselStream() {
  const [vessels, setVessels] = useState([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef(null);

  useEffect(() => {
    let es;
    function connect() {
      es = new EventSource(`${AIS_BASE}/api/vessels/stream`);
      esRef.current = es;
      es.addEventListener("vessels", (e) => {
        try {
          const data = JSON.parse(e.data);
          setVessels(data.vessels || []);
          setConnected(true);
        } catch {}
      });
      es.onerror = () => {
        setConnected(false);
        es.close();
        setTimeout(connect, 3000);
      };
    }
    connect();
    return () => { if (esRef.current) esRef.current.close(); };
  }, []);

  return { vessels, connected };
}

/* ── Port congestion data hook ───────────────────────────── */
function usePortCongestion() {
  const [ports, setPorts] = useState([]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/top-ports?top_n=120`);
        const data = await res.json();
        if (mounted) setPorts(data.ports || []);
      } catch {}
    }
    load();
    const interval = setInterval(load, 60000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return ports;
}

/* ── Reset view control ──────────────────────────────────── */
function ResetView({ center, zoom }) {
  const map = useMap();
  const handleReset = useCallback(() => {
    map.setView(center, zoom);
  }, [map, center, zoom]);
  return (
    <button onClick={handleReset} title="Reset view" style={{
      position: "absolute", top: 12, right: 12, zIndex: 1000,
      background: T.navy2, border: `1px solid ${T.border}`, borderRadius: 6,
      color: T.inkMid, cursor: "pointer", padding: "6px 8px", display: "flex",
      alignItems: "center", gap: 4, fontSize: 11, fontFamily: T.sans,
    }}>
      <RotateCcw size={12} /> Reset
    </button>
  );
}

/* ── Selected vessel side panel ──────────────────────────── */
function VesselPanel({ vessel, onClose }) {
  if (!vessel) return null;
  const resolvedPort = resolveUSPort(vessel.destination);
  const fields = [
    ["MMSI", vessel.mmsi],
    ["Type", vessel.vessel_type_label || "Unknown"],
    ["Status", vessel.nav_status_label || "Unknown"],
    ["Speed", vessel.sog != null ? `${vessel.sog} kn` : "—"],
    ["Course", vessel.cog != null ? `${vessel.cog}°` : "—"],
    ["Destination", vessel.destination || "—"],
    ...(resolvedPort && resolvedPort !== "__US_UNKNOWN__"
      ? [["Resolved Port", resolvedPort]]
      : []),
    ["Position", `${vessel.lat?.toFixed(4)}, ${vessel.lon?.toFixed(4)}`],
  ];
  return (
    <div style={{
      position: "absolute", top: 0, right: 0, bottom: 0, width: 280, zIndex: 1000,
      background: T.navy2, borderLeft: `1px solid ${T.border}`,
      display: "flex", flexDirection: "column", overflow: "auto",
    }}>
      <div style={{
        padding: "12px 14px", borderBottom: `1px solid ${T.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: T.ink }}>
          {vessel.name || "Unknown Vessel"}
        </div>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: T.inkMid, cursor: "pointer", fontSize: 18,
        }}>&times;</button>
      </div>
      <div style={{ padding: "10px 14px" }}>
        {fields.map(([label, value]) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between",
            padding: "6px 0", borderBottom: `1px solid ${T.border}22`,
          }}>
            <span style={{ fontSize: 11, color: T.inkDim }}>{label}</span>
            <span style={{ fontSize: 11, color: T.ink, fontFamily: T.mono }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Filter dropdown ─────────────────────────────────────── */
function FilterDropdown({ label, value, options, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)} style={{
        background: T.navy2, border: `1px solid ${T.border}`, borderRadius: 6,
        color: value ? T.teal : T.inkMid, cursor: "pointer", padding: "5px 10px",
        fontSize: 11, fontFamily: T.sans, display: "flex", alignItems: "center", gap: 4,
      }}>
        {value || label} <ChevronDown size={10} />
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 2000,
          background: T.navy2, border: `1px solid ${T.border}`, borderRadius: 6,
          minWidth: 140, maxHeight: 200, overflow: "auto",
        }}>
          <div onClick={() => { onChange(null); setOpen(false); }} style={{
            padding: "6px 10px", cursor: "pointer", fontSize: 11, color: T.inkMid,
            borderBottom: `1px solid ${T.border}22`,
          }}>All</div>
          {options.map(opt => (
            <div key={opt} onClick={() => { onChange(opt); setOpen(false); }} style={{
              padding: "6px 10px", cursor: "pointer", fontSize: 11,
              color: value === opt ? T.teal : T.ink,
              background: value === opt ? `${T.teal}11` : "transparent",
            }}>{opt}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Congestion color helper ─────────────────────────────── */
function congestionColor(score) {
  if (score >= 67) return T.red;
  if (score >= 33) return T.amber;
  return T.green;
}

function congestionFill(score) {
  if (score >= 67) return "rgba(239,68,68,0.18)";
  if (score >= 33) return "rgba(245,158,11,0.14)";
  return "rgba(16,185,129,0.12)";
}

/* ── Port dropdown with search ─────────────────────────── */
const SORTED_PORTS = Object.keys(PORT_COORDS).sort();

function PortDropdown({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const filtered = search
    ? SORTED_PORTS.filter(p => p.toLowerCase().includes(search.toLowerCase()))
    : SORTED_PORTS;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)} style={{
        background: value ? `${T.teal}22` : T.navy2,
        border: `1px solid ${value ? T.teal : T.border}`,
        borderRadius: 6, color: value ? T.teal : T.inkMid,
        cursor: "pointer", padding: "5px 10px", fontSize: 11, fontFamily: T.sans,
        display: "flex", alignItems: "center", gap: 4, maxWidth: 180,
      }}>
        <MapPin size={10} />
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {value || "Zoom to Port"}
        </span>
        <ChevronDown size={10} />
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 2000,
          background: T.navy2, border: `1px solid ${T.border}`, borderRadius: 6,
          width: 220, maxHeight: 280, display: "flex", flexDirection: "column",
        }}>
          <div style={{ padding: "6px 8px", borderBottom: `1px solid ${T.border}22`, display: "flex", alignItems: "center", gap: 4 }}>
            <Search size={10} color={T.inkDim} />
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search ports..."
              style={{
                background: "transparent", border: "none", outline: "none",
                color: T.ink, fontSize: 11, fontFamily: T.sans, width: "100%",
              }}
            />
          </div>
          <div style={{ overflow: "auto", flex: 1 }}>
            <div onClick={() => { onChange(null); setOpen(false); setSearch(""); }} style={{
              padding: "6px 10px", cursor: "pointer", fontSize: 11, color: T.inkMid,
              borderBottom: `1px solid ${T.border}22`,
            }}>All (Reset View)</div>
            {filtered.map(port => (
              <div key={port} onClick={() => { onChange(port); setOpen(false); setSearch(""); }} style={{
                padding: "6px 10px", cursor: "pointer", fontSize: 11,
                color: value === port ? T.teal : T.ink,
                background: value === port ? `${T.teal}11` : "transparent",
              }}>
                {MAJOR_PORTS.has(port) ? "★ " : ""}{port}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── FlyToPort — responds to selectedPort state ──────────── */
function FlyToPort({ port }) {
  const map = useMap();
  useEffect(() => {
    if (port && PORT_COORDS[port]) {
      map.flyTo(PORT_COORDS[port], 10, { duration: 1.2 });
    } else if (!port) {
      map.flyTo(US_CENTER, US_ZOOM, { duration: 1.2 });
    }
  }, [port, map]);
  return null;
}

/* ── Major ports (larger circles at US zoom level) ─────── */
const MAJOR_PORTS = new Set([
  "Los Angeles-Long Beach", "New York-New Jersey", "Houston", "Savannah",
  "Charleston", "Norfolk", "Seattle", "Tacoma", "Oakland", "New Orleans",
  "Miami", "Jacksonville", "Baltimore", "Tampa", "Philadelphia",
]);

/* ── North America bounds ─────────────────────────────────── */
const NA_BOUNDS = [[12, -180], [72, -50]];

/* ── Constants ────────────────────────────────────────────── */
const US_CENTER = [37.5, -96.0];
const US_ZOOM = 4;

/* ── Port layer (static radii — no zoom state, no rerender on zoom) ── */
function PortLayer({ portMarkers, showPorts }) {
  if (!showPorts) return null;
  return (
    <>
      {/* Sonar pulse markers for HIGH congestion ports */}
      {portMarkers.filter(p => p.score >= 67).map(p => (
        <Marker key={`pulse-${p.name}`} position={p.coords} icon={_pulseIcon}
          zIndexOffset={-1000} interactive={false} />
      ))}

      {/* Port congestion circles — fixed meter radius, Leaflet handles zoom natively */}
      {portMarkers.map(p => (
        <Circle key={`port-${p.name}`} center={p.coords}
          radius={p.baseRadius}
          pathOptions={{
            color: congestionColor(p.score), fillColor: congestionFill(p.score),
            fillOpacity: 0.5, weight: 1.5,
            dashArray: p.score >= 67 ? "" : "4 3",
          }}
        >
          <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
            <div style={{ fontFamily: T.sans, fontSize: 11, lineHeight: 1.5 }}>
              <strong>{p.name}</strong><br />
              Congestion: <span style={{ color: congestionColor(p.score), fontWeight: 700 }}>{p.status}</span> ({p.score.toFixed(0)})<br />
              Inbound vessels: <strong>{p.vesselCount}</strong>
            </div>
          </Tooltip>
        </Circle>
      ))}

      {/* Port center dots (pixel-based — zoom-independent) */}
      {portMarkers.map(p => (
        <CircleMarker key={`port-dot-${p.name}`} center={p.coords}
          radius={p.isMajor ? 6 : 4}
          pathOptions={{
            color: congestionColor(p.score), fillColor: congestionColor(p.score),
            fillOpacity: 0.9, weight: p.isMajor ? 2 : 1,
          }}
        />
      ))}
    </>
  );
}

/* ── Main VesselMap component ────────────────────────────── */

const VESSEL_TYPES = ["Cargo", "Tanker", "Passenger", "Fishing", "High Speed Craft", "Special Craft", "Other"];
const NAV_STATUSES = ["Under Way Using Engine", "At Anchor", "Moored", "Engaged in Fishing", "Under Way Sailing"];

export default function VesselMap() {
  const { vessels, connected } = useVesselStream();
  const congestionPorts = usePortCongestion();
  const [selected, setSelected] = useState(null);
  const [typeFilter, setTypeFilter] = useState(null);
  const [statusFilter, setStatusFilter] = useState(null);
  const [showPorts, setShowPorts] = useState(true);
  const [selectedPort, setSelectedPort] = useState(null);

  // Inject pulse animation CSS
  useEffect(() => {
    const id = "vessel-map-pulse-css";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      .port-sonar { position: relative; width: 60px; height: 60px; pointer-events: none; }
      .port-sonar-ring {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        border-radius: 50%; border: 2px solid #EF4444;
        opacity: 0; animation: sonar-expand 2s ease-out infinite;
      }
      .port-sonar-ring:nth-child(2) { animation-delay: 1s; }
      @keyframes sonar-expand {
        0%   { transform: scale(0.3); opacity: 0.7; }
        50%  { opacity: 0.3; }
        100% { transform: scale(2.5); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
    return () => { const el = document.getElementById(id); if (el) el.remove(); };
  }, []);

  // Filter to US-bound vessels only + apply type/status filters
  const { usVessels, portVesselCounts } = useMemo(() => {
    const counts = {};
    const usOnly = [];

    for (const v of vessels) {
      const resolvedPort = resolveUSPort(v.destination);
      const inUSWaters = (
        (v.lat >= 24.5 && v.lat <= 49.0 && v.lon >= -125.0 && v.lon <= -66.0) ||
        (v.lat >= 18.0 && v.lat <= 23.0 && v.lon >= -161.0 && v.lon <= -154.0) ||
        (v.lat >= 55.0 && v.lat <= 65.0 && v.lon >= -170.0 && v.lon <= -140.0)
      );

      if (resolvedPort || inUSWaters) {
        usOnly.push(v);
        if (resolvedPort && resolvedPort !== "__US_UNKNOWN__") {
          counts[resolvedPort] = (counts[resolvedPort] || 0) + 1;
        }
      }
    }

    return { usVessels: usOnly, portVesselCounts: counts };
  }, [vessels]);

  const filtered = usVessels.filter(v => {
    if (typeFilter && v.vessel_type_label !== typeFilter) return false;
    if (statusFilter && v.nav_status_label !== statusFilter) return false;
    return true;
  });

  const selectedVessel = selected ? usVessels.find(v => v.mmsi === selected) : null;

  // Build port marker data: merge congestion scores with vessel counts
  const portMarkers = useMemo(() => {
    const congestionMap = {};
    for (const p of congestionPorts) {
      congestionMap[p.portname] = p;
    }
    const markers = [];
    for (const [name, coords] of Object.entries(PORT_COORDS)) {
      const cong = congestionMap[name];
      const vesselCount = portVesselCounts[name] || 0;
      const score = cong?.current_score ?? 50;
      const status = cong?.status || "MEDIUM";
      const isMajor = MAJOR_PORTS.has(name);
      const baseRadius = isMajor
        ? Math.min(8000 + vesselCount * 500, 30000)
        : Math.min(3000 + vesselCount * 400, 25000);
      markers.push({ name, coords, vesselCount, score, status, baseRadius, isMajor });
    }
    return markers;
  }, [congestionPorts, portVesselCounts]);

  return (
    <div style={{ height: "100%", position: "relative", background: T.navy }}>
      {/* Stats overlay */}
      <div style={{
        position: "absolute", top: 12, left: 12, zIndex: 1000,
        background: `${T.navy2}ee`, border: `1px solid ${T.border}`,
        borderRadius: 8, padding: "8px 12px", display: "flex", gap: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Ship size={14} color={T.teal} />
          <span style={{ fontSize: 13, fontWeight: 700, color: T.ink, fontFamily: T.mono }}>{filtered.length}</span>
          <span style={{ fontSize: 10, color: T.inkDim }}>US vessels</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {connected ? <Wifi size={11} color={T.green} /> : <WifiOff size={11} color={T.red} />}
          <span style={{ fontSize: 10, color: connected ? T.green : T.red }}>
            {connected ? "Live" : "Reconnecting..."}
          </span>
        </div>
      </div>

      {/* Filter controls */}
      <div style={{
        position: "absolute", top: 12, left: 230, zIndex: 1000,
        display: "flex", gap: 6,
      }}>
        <PortDropdown value={selectedPort} onChange={setSelectedPort} />
        <FilterDropdown label="Vessel Type" value={typeFilter} options={VESSEL_TYPES} onChange={setTypeFilter} />
        <FilterDropdown label="Nav Status" value={statusFilter} options={NAV_STATUSES} onChange={setStatusFilter} />
        <button onClick={() => setShowPorts(p => !p)} style={{
          background: showPorts ? `${T.teal}22` : T.navy2,
          border: `1px solid ${showPorts ? T.teal : T.border}`,
          borderRadius: 6, color: showPorts ? T.teal : T.inkMid,
          cursor: "pointer", padding: "5px 10px", fontSize: 11, fontFamily: T.sans,
          display: "flex", alignItems: "center", gap: 4,
        }}>
          <Anchor size={10} /> Ports
        </button>
      </div>

      {/* Legend */}
      <div style={{
        position: "absolute", bottom: 12, left: 12, zIndex: 1000,
        background: `${T.navy2}ee`, border: `1px solid ${T.border}`,
        borderRadius: 8, padding: "8px 12px", maxWidth: 560,
      }}>
        <div style={{ fontSize: 10, color: T.inkDim, marginBottom: 6, fontWeight: 700 }}>Vessel Types</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
          {Object.entries(TYPE_COLORS).filter(([k]) => k !== "Unknown").map(([type, color]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span dangerouslySetInnerHTML={{ __html: LEGEND_SHAPES[type]?.(color) || `<svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="${color}"/></svg>` }} />
              <span style={{ fontSize: 9, color: T.inkMid }}>{type}</span>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10, color: T.inkDim, marginTop: 6, marginBottom: 4, fontWeight: 700 }}>Nav Status</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
          {Object.entries(STATUS_COLORS).map(([status, color]) => (
            <div key={status} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />
              <span style={{ fontSize: 9, color: T.inkMid }}>{status}</span>
            </div>
          ))}
        </div>
        {showPorts && (
          <>
            <div style={{ fontSize: 10, color: T.inkDim, marginTop: 6, marginBottom: 4, fontWeight: 700 }}>Port Congestion</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
              {[["High (≥67)", T.red], ["Moderate (33–66)", T.amber], ["Low (<33)", T.green]].map(([label, color]) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: color, opacity: 0.5, border: `1.5px solid ${color}` }} />
                  <span style={{ fontSize: 9, color: T.inkMid }}>{label}</span>
                </div>
              ))}
              <span style={{ fontSize: 9, color: T.inkDim, fontStyle: "italic" }}>size = inbound vessels</span>
            </div>
          </>
        )}
      </div>

      {/* Map */}
      <MapContainer
        center={US_CENTER}
        zoom={US_ZOOM}
        style={{ height: "100%", width: "100%", background: T.navy }}
        zoomControl={false}
        preferCanvas={true}
        maxBounds={NA_BOUNDS}
        maxBoundsViscosity={1.0}
        minZoom={3}
        maxZoom={14}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        />
        <ResetView center={US_CENTER} zoom={US_ZOOM} />
        <FlyToPort port={selectedPort} />

        {/* Port layer (owns zoom state — zoom changes only rerender ports, not vessels) */}
        <PortLayer portMarkers={portMarkers} showPorts={showPorts} />

        {/* Vessel markers (CircleMarker — single canvas layer, smooth zoom) */}
        {filtered.map(v => (
          <CircleMarker
            key={v.mmsi}
            center={[v.lat, v.lon]}
            radius={selected === v.mmsi ? 7 : 3}
            pathOptions={{
              color: getVesselColor(v),
              fillColor: getVesselColor(v),
              fillOpacity: selected === v.mmsi ? 1 : 0.7,
              weight: selected === v.mmsi ? 2 : 1,
            }}
            eventHandlers={{
              click: () => setSelected(v.mmsi === selected ? null : v.mmsi),
            }}
          >
            <Tooltip direction="top" offset={[0, -6]} opacity={0.95}>
              <div style={{ fontFamily: T.sans, fontSize: 11, lineHeight: 1.4 }}>
                <strong>{v.name || "Unknown"}</strong><br />
                {v.vessel_type_label || "Unknown"} · {v.sog ?? 0} kn<br />
                {v.destination ? `→ ${v.destination}` : "No destination"}
              </div>
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>

      {/* Selected vessel panel */}
      <VesselPanel vessel={selectedVessel} onClose={() => setSelected(null)} />
    </div>
  );
}
