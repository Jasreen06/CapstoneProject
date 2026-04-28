import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Circle, Marker, Tooltip, useMap, useMapEvents } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import { Ship, Wifi, WifiOff, RotateCcw, ChevronDown, Anchor, MapPin, Search, Navigation } from "lucide-react";
import { haversineNM } from "./utils/geo";
import { useTheme } from "./hooks/useTheme";

/* ── Design tokens (match App.jsx — CSS custom properties) ── */
const T = {
  navy: "var(--bg-navy)", navy2: "var(--bg-navy2)", navy3: "var(--bg-navy3)",
  border: "var(--border-color)", borderL: "var(--border-colorL)",
  borderSubtle: "var(--border-subtle)", borderMedium: "var(--border-medium)",
  teal: "var(--accent-teal)",
  tealSubtle: "var(--teal-subtle)", tealFaint: "var(--teal-faint)", tealBorder: "var(--teal-border)",
  amber: "#F59E0B", red: "#EF4444", green: "#10B981", blue: "#3B82F6",
  ink: "var(--text-ink)", inkMid: "var(--text-inkMid)", inkDim: "var(--text-inkDim)",
  navy2Overlay: "var(--navy2-overlay)",
  sans: "'Syne', sans-serif", mono: "'JetBrains Mono', monospace",
};

const AIS_BASE = process.env.REACT_APP_AIS_URL || "http://localhost:8001";
const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8004";

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
  // Common abbreviations
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
  // UN/LOCODE 5-letter codes (US + 3-letter port code)
  "uslax": "Los Angeles-Long Beach", "uslgb": "Los Angeles-Long Beach",
  "usoak": "Oakland", "ussfo": "San Francisco",
  "ussea": "Seattle", "ustac": "Tacoma",
  "ussan": "San Diego", "ushue": "Port Hueneme",
  "uspdx": "Portland, OR", "uslvw": "Longview",
  "useve": "Everett", "usbli": "Bellingham",
  "usanc": "Anchorage (Alaska)", "usdut": "Dutch Harbor",
  "ushnl": "Honolulu", "usito": "Hilo",
  "ushou": "Houston", "usnol": "New Orleans",
  "usbtr": "Baton Rouge", "usbmt": "Beaumont",
  "uspat": "Port Arthur", "uscrp": "Corpus Christi",
  "usfpt": "Freeport", "usgls": "Galveston",
  "ustxc": "Texas City", "uslch": "Lake Charles",
  "usmob": "Mobile", "ustpa": "Tampa",
  "usplv": "Port Lavaca", "usbro": "Brownsville",
  "usgpt": "Gulfport", "uspgl": "Pascagoula",
  "uspns": "Pensacola", "uspfn": "Panama City",
  "usnyc": "New York-New Jersey", "usewr": "New York-New Jersey",
  "usphl": "Philadelphia", "usbal": "Baltimore",
  "usnor": "Norfolk", "usnnw": "Newport News",
  "ussav": "Savannah", "uschs": "Charleston",
  "usjax": "Jacksonville", "usmia": "Miami",
  "uspef": "Port Everglades", "usccv": "Canaveral Harbor",
  "usilm": "Wilmington, NC", "usbqk": "Brunswick",
  "usbos": "Boston", "uspvd": "Providence",
  "uspwm": "Portland, ME", "usmrh": "Marcus Hook",
  "uschi": "Chicago", "usdet": "Detroit",
  "uscle": "Cleveland", "ustol": "Toledo",
  "usdlh": "Duluth", "usmke": "Milwaukee",
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

// Cached divIcons for sonar pulse per congestion tier
const _pulseIconCache = {};
function getPulseIcon(score) {
  const tier = score >= 67 ? "high" : score >= 33 ? "med" : "low";
  if (_pulseIconCache[tier]) return _pulseIconCache[tier];
  _pulseIconCache[tier] = L.divIcon({
    html: `<div class="port-sonar port-sonar-${tier}"><div class="port-sonar-ring"></div></div>`,
    className: "",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });
  return _pulseIconCache[tier];
}

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
        console.log("[usePortCongestion] fetched", data.ports?.length, "ports, sample:", data.ports?.[0]);
        if (mounted) setPorts(data.ports || []);
      } catch (e) { console.error("[usePortCongestion] fetch failed:", e); }
    }
    load();
    const interval = setInterval(load, 60000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return ports;
}

/* ── Phase 6A.2 — live AIS coverage snapshot hook ─────────
   Returns a {portname → "covered"|"sparse"|"dark"|"unavailable"} map.
   Fails open: on error or empty response, returns {} so callers default
   every port to "covered" (i.e. no dashed treatment). */
function useCoverageSnapshot() {
  const [coverage, setCoverage] = useState({});

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/coverage-snapshot`);
        const data = await res.json();
        if (mounted) setCoverage(data.coverage || {});
      } catch (e) {
        if (mounted) setCoverage({});
      }
    }
    load();
    const interval = setInterval(load, 60000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return coverage;
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

/* ── Rerouting analysis helper ──────────────────────────── */
function getReroutingAnalysis(vessel, portMarkers) {
  const resolvedPort = resolveUSPort(vessel.destination);
  if (!resolvedPort || resolvedPort === "__US_UNKNOWN__") {
    return { status: "no_destination", resolvedPort: null, tier: null, alternatives: [] };
  }

  const destMarker = portMarkers.find(p => p.name === resolvedPort);
  if (!destMarker) {
    return { status: "no_data", resolvedPort, tier: null, alternatives: [] };
  }

  const tier = destMarker.status; // "HIGH", "MEDIUM", "LOW"
  if (tier !== "HIGH") {
    return { status: "ok", resolvedPort, tier, score: destMarker.score, alternatives: [] };
  }

  // HIGH congestion — find 3 nearest LOW/MEDIUM ports within 500nm
  const MAX_REROUTE_NM = 500;
  const candidates = portMarkers
    .filter(p => p.name !== resolvedPort && (p.status === "LOW" || p.status === "MEDIUM"))
    .map(p => ({
      name: p.name,
      tier: p.status,
      score: p.score,
      vesselCount: p.vesselCount,
      distNM: Math.round(haversineNM(vessel.lat, vessel.lon, p.coords[0], p.coords[1])),
      coords: p.coords,
    }))
    .filter(p => p.distNM <= MAX_REROUTE_NM)
    .sort((a, b) => a.distNM - b.distNM)
    .slice(0, 3);

  return { status: "congested", resolvedPort, tier, score: destMarker.score, alternatives: candidates };
}

/* ── Congestion tier badge ──────────────────────────────── */
function TierBadge({ tier, score }) {
  const color = tier === "HIGH" ? T.red : tier === "MEDIUM" ? T.amber : T.green;
  const label = tier === "HIGH" ? "Destination congested"
    : tier === "MEDIUM" ? "Moderate congestion expected"
    : "Destination clear — no rerouting needed";
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6, padding: "6px 8px",
      borderRadius: 6, background: `${color}18`, border: `1px solid ${color}44`,
    }}>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ fontSize: 11, color, fontWeight: 600 }}>{label}</span>
      {score != null && (
        <span style={{ fontSize: 10, color: T.inkDim, marginLeft: "auto" }}>{score.toFixed(0)}</span>
      )}
    </div>
  );
}

/* ── Selected vessel side panel ──────────────────────────── */
function VesselPanel({ vessel, onClose, portMarkers, onFlyTo }) {
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

  const rerouting = getReroutingAnalysis(vessel, portMarkers);

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
            padding: "6px 0", borderBottom: `1px solid ${T.borderSubtle}`,
          }}>
            <span style={{ fontSize: 11, color: T.inkDim }}>{label}</span>
            <span style={{ fontSize: 11, color: T.ink, fontFamily: T.mono }}>{value}</span>
          </div>
        ))}
      </div>

      {/* ── Rerouting Analysis Section ── */}
      <div style={{
        padding: "10px 14px", borderTop: `1px solid ${T.border}`,
      }}>
        <div style={{
          fontSize: 11, fontWeight: 700, color: T.inkMid, textTransform: "uppercase",
          letterSpacing: "0.05em", marginBottom: 8,
          display: "flex", alignItems: "center", gap: 5,
        }}>
          <Navigation size={11} /> Rerouting Analysis
        </div>

        {rerouting.status === "no_destination" && (
          <div style={{ fontSize: 11, color: T.inkDim, fontStyle: "italic" }}>
            No destination set — rerouting analysis unavailable.
          </div>
        )}
        {rerouting.status === "no_data" && (
          <div style={{ fontSize: 11, color: T.inkDim, fontStyle: "italic" }}>
            Destination "{rerouting.resolvedPort}" — congestion data unavailable.
          </div>
        )}
        {(rerouting.status === "ok" || rerouting.status === "congested") && (
          <TierBadge tier={rerouting.tier} score={rerouting.score} />
        )}

        {rerouting.status === "congested" && rerouting.alternatives.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, color: T.inkDim, marginBottom: 6, fontWeight: 600 }}>
              Suggested alternatives
            </div>
            {rerouting.alternatives.map(alt => (
              <div
                key={alt.name}
                onClick={() => onFlyTo(alt.coords, alt.name)}
                style={{
                  display: "grid", gridTemplateColumns: "1fr auto auto auto",
                  gap: 6, alignItems: "center",
                  padding: "6px 8px", marginBottom: 3, borderRadius: 5,
                  background: `${T.navy3}`, border: `1px solid ${T.borderMedium}`,
                  cursor: "pointer", transition: "border-color 0.15s",
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = T.teal}
                onMouseLeave={e => e.currentTarget.style.borderColor = T.borderMedium}
              >
                <span style={{ fontSize: 11, color: T.ink, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {alt.name}
                </span>
                <span style={{ fontSize: 10, color: T.inkDim, fontFamily: T.mono }}>
                  {alt.distNM} nm
                </span>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
                  color: alt.tier === "LOW" ? T.green : T.amber,
                  background: alt.tier === "LOW" ? `${T.green}18` : `${T.amber}18`,
                }}>
                  {alt.tier}
                </span>
                <span style={{ fontSize: 10, color: T.inkDim }}>
                  {alt.vesselCount} in
                </span>
              </div>
            ))}
          </div>
        )}
        {rerouting.status === "congested" && rerouting.alternatives.length === 0 && (
          <div style={{ fontSize: 11, color: T.inkDim, fontStyle: "italic", marginTop: 6 }}>
            No viable alternatives nearby (&lt;500 nm).
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Port info side panel (2B) ──────────────────────────── */
function deriveCoast(coords) {
  const [lat, lon] = coords;
  if (lon < -100) return "West Coast";
  if (lat < 32 && lon >= -100 && lon <= -80) return "Gulf Coast";
  return "East Coast";
}

function PortPanel({ portInfo, onClose }) {
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const profileCache = useRef({});

  const name = portInfo?.name;

  useEffect(() => {
    if (!name) { setProfile(null); return; }
    if (profileCache.current[name]) {
      setProfile(profileCache.current[name]);
      return;
    }
    setProfileLoading(true);
    setProfile(null);
    fetch(`${API_BASE}/api/port-profile/${encodeURIComponent(name)}`)
      .then(res => {
        if (!res.ok) throw new Error("not found");
        return res.json();
      })
      .then(data => {
        profileCache.current[name] = data;
        setProfile(data);
      })
      .catch(() => setProfile(null))
      .finally(() => setProfileLoading(false));
  }, [name]);

  if (!portInfo) return null;
  const { coords, score, status, vesselCount } = portInfo;
  const coast = deriveCoast(coords);
  const tierColor = score >= 67 ? T.red : score >= 33 ? T.amber : T.green;
  const trend = portInfo.trend;

  return (
    <div style={{
      position: "absolute", top: 0, right: 0, bottom: 0, width: 280, zIndex: 1000,
      background: T.navy2, borderLeft: `1px solid ${T.border}`,
      display: "flex", flexDirection: "column", overflow: "auto",
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 14px", borderBottom: `1px solid ${T.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: T.ink }}>{name}</div>
          <div style={{ fontSize: 10, color: T.inkDim, marginTop: 2 }}>{coast}</div>
        </div>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: T.inkMid, cursor: "pointer", fontSize: 18,
        }}>&times;</button>
      </div>

      {/* Congestion stats */}
      <div style={{ padding: "10px 14px" }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 6, padding: "8px 10px",
          borderRadius: 6, background: `${tierColor}18`, border: `1px solid ${tierColor}44`,
          marginBottom: 10,
        }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: tierColor }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: tierColor }}>{status}</span>
          <span style={{ fontSize: 11, color: T.ink, marginLeft: "auto", fontFamily: T.mono }}>
            {score.toFixed(0)}/100
          </span>
        </div>

        {[
          ["Congestion Score", `${score.toFixed(1)}`],
          ["Congestion Tier", status],
          ["Inbound Vessels", `${vesselCount}`],
          ...(trend ? [["7-Day Trend", trend]] : []),
        ].map(([label, value]) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between",
            padding: "6px 0", borderBottom: `1px solid ${T.borderSubtle}`,
          }}>
            <span style={{ fontSize: 11, color: T.inkDim }}>{label}</span>
            <span style={{
              fontSize: 11, fontFamily: T.mono,
              color: label === "7-Day Trend"
                ? (value === "rising" ? T.red : value === "falling" ? T.green : T.inkMid)
                : T.ink,
            }}>
              {label === "7-Day Trend" ? (value === "rising" ? "Rising" : value === "falling" ? "Falling" : "Stable") : value}
            </span>
          </div>
        ))}
      </div>

      {/* Port Profile */}
      <div style={{
        padding: "10px 14px", borderTop: `1px solid ${T.border}`,
      }}>
        <div style={{
          fontSize: 11, fontWeight: 700, color: T.inkMid, textTransform: "uppercase",
          letterSpacing: "0.05em", marginBottom: 8,
          display: "flex", alignItems: "center", gap: 5,
        }}>
          <Anchor size={11} /> Port Profile
        </div>

        {profileLoading && (
          <div style={{ fontSize: 11, color: T.inkDim, fontStyle: "italic" }}>Loading...</div>
        )}
        {!profileLoading && !profile && (
          <div style={{ fontSize: 11, color: T.inkDim, fontStyle: "italic" }}>
            Profile not available for this port.
          </div>
        )}
        {!profileLoading && profile && (
          <>
            <p style={{ fontSize: 11, color: T.ink, lineHeight: 1.6, margin: "0 0 8px 0" }}>
              {profile.profile}
            </p>
            {profile.notable && profile.notable.length > 0 && (
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {profile.notable.map((fact, i) => (
                  <li key={i} style={{ fontSize: 10, color: T.inkMid, lineHeight: 1.6 }}>{fact}</li>
                ))}
              </ul>
            )}
          </>
        )}
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
            borderBottom: `1px solid ${T.borderSubtle}`,
          }}>All</div>
          {options.map(opt => (
            <div key={opt} onClick={() => { onChange(opt); setOpen(false); }} style={{
              padding: "6px 10px", cursor: "pointer", fontSize: 11,
              color: value === opt ? T.teal : T.ink,
              background: value === opt ? T.tealFaint : "transparent",
            }}>{opt}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Multi-select filter dropdown ────────────────────────── */
function MultiSelectDropdown({ label, selected, options, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const allSelected = selected.size === options.length;

  const toggle = (opt) => {
    const next = new Set(selected);
    if (next.has(opt)) next.delete(opt); else next.add(opt);
    onChange(next);
  };

  const toggleAll = () => {
    onChange(allSelected ? new Set() : new Set(options));
  };

  const summary = allSelected
    ? "All types"
    : selected.size === 0
      ? label
      : [...selected].slice(0, 2).join(" + ") + (selected.size > 2 ? ` (${selected.size})` : selected.size === 2 ? ` (${selected.size})` : "");

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)} style={{
        background: !allSelected && selected.size > 0 ? T.tealSubtle : T.navy2,
        border: `1px solid ${!allSelected && selected.size > 0 ? T.teal : T.border}`,
        borderRadius: 6, color: !allSelected && selected.size > 0 ? T.teal : T.inkMid,
        cursor: "pointer", padding: "5px 10px",
        fontSize: 11, fontFamily: T.sans, display: "flex", alignItems: "center", gap: 4,
      }}>
        {summary} <ChevronDown size={10} />
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 2000,
          background: T.navy2, border: `1px solid ${T.border}`, borderRadius: 6,
          minWidth: 170, maxHeight: 240, overflow: "auto",
        }}>
          <div onClick={toggleAll} style={{
            padding: "6px 10px", cursor: "pointer", fontSize: 11, color: T.inkMid,
            borderBottom: `1px solid ${T.borderSubtle}`, display: "flex", alignItems: "center", gap: 6,
          }}>
            <div style={{
              width: 12, height: 12, borderRadius: 2, border: `1.5px solid ${allSelected ? T.teal : T.border}`,
              background: allSelected ? T.teal : "transparent", display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              {allSelected && <span style={{ color: T.navy, fontSize: 9, fontWeight: 700 }}>✓</span>}
            </div>
            All types
          </div>
          {options.map(opt => {
            const checked = selected.has(opt);
            return (
              <div key={opt} onClick={() => toggle(opt)} style={{
                padding: "6px 10px", cursor: "pointer", fontSize: 11,
                color: checked ? T.ink : T.inkMid,
                background: checked ? T.tealFaint : "transparent",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <div style={{
                  width: 12, height: 12, borderRadius: 2, border: `1.5px solid ${checked ? T.teal : T.border}`,
                  background: checked ? T.teal : "transparent", display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {checked && <span style={{ color: T.navy, fontSize: 9, fontWeight: 700 }}>✓</span>}
                </div>
                {opt}
              </div>
            );
          })}
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
  if (score >= 67) return "rgba(239,68,68,0.25)";
  if (score >= 33) return "rgba(245,158,11,0.22)";
  return "rgba(16,185,129,0.20)";
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
        background: value ? T.tealSubtle : T.navy2,
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
          <div style={{ padding: "6px 8px", borderBottom: `1px solid ${T.borderSubtle}`, display: "flex", alignItems: "center", gap: 4 }}>
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
              borderBottom: `1px solid ${T.borderSubtle}`,
            }}>All (Reset View)</div>
            {filtered.map(port => (
              <div key={port} onClick={() => { onChange(port); setOpen(false); setSearch(""); }} style={{
                padding: "6px 10px", cursor: "pointer", fontSize: 11,
                color: value === port ? T.teal : T.ink,
                background: value === port ? T.tealFaint : "transparent",
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

/* ── MapRefSetter — captures map instance into a ref ────── */
function MapRefSetter({ mapRef }) {
  const map = useMap();
  useEffect(() => { mapRef.current = map; }, [map, mapRef]);
  return null;
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
function PortLayer({ portMarkers, showPorts, onPortClick }) {
  if (!showPorts) return null;
  return (
    <>
      {/* Sonar pulse markers for HIGH congestion ports — suppressed on unverified */}
      {portMarkers.filter(p => p.score >= 67 && !p.isUnverified).map(p => (
        <Marker key={`pulse-${p.name}`} position={p.coords} icon={getPulseIcon(p.score)}
          zIndexOffset={-1000} interactive={false} />
      ))}

      {/* Port congestion circles — fixed meter radius, Leaflet handles zoom natively.
          Phase 6A.2: ports with unverified coverage render dashed + ghosted. */}
      {portMarkers.map(p => (
        <Circle key={`port-${p.name}`} center={p.coords}
          radius={p.baseRadius}
          pathOptions={{
            color: congestionColor(p.score), fillColor: congestionFill(p.score),
            fillOpacity: p.isUnverified ? 0.15 : 0.5,
            weight: p.isUnverified ? 1 : 1.5,
            dashArray: p.isUnverified ? "8 6" : (p.score >= 67 ? "" : "4 3"),
            opacity: p.isUnverified ? 0.7 : 1,
          }}
          eventHandlers={{
            click: () => onPortClick && onPortClick(p),
          }}
        >
          <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
            <div style={{ fontFamily: T.sans, fontSize: 11, lineHeight: 1.5 }}>
              <strong>{p.name}</strong><br />
              Congestion: <span style={{ color: congestionColor(p.score), fontWeight: 700 }}>{p.status}</span> ({p.score.toFixed(0)})<br />
              At port (anchored/moored): <strong>{p.atPort || 0}</strong>
              <br />En route: <strong>{p.enRoute || 0}</strong>
              {p.isUnverified && (
                <><br /><span style={{ color: T.inkDim, fontStyle: "italic" }}>
                  Live AIS coverage: {p.coverage}
                </span></>
              )}
            </div>
          </Tooltip>
        </Circle>
      ))}

      {/* Port center dots (pixel-based — zoom-independent) */}
      {portMarkers.map(p => (
        <Marker key={`port-dot-${p.name}`}
          position={p.coords}
          icon={getPortAnchorIcon(p.score)}
          zIndexOffset={500}
          eventHandlers={{
            click: () => onPortClick && onPortClick(p),
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
  const coverageMap     = useCoverageSnapshot();
  const { isDark } = useTheme();
  const [selected, setSelected] = useState(null);
  const [typeFilters, setTypeFilters] = useState(() => new Set(VESSEL_TYPES));
  const [statusFilter, setStatusFilter] = useState(null);
  const [congestionFilter, setCongestionFilter] = useState(null);
  const [showPorts, setShowPorts] = useState(true);
  const [selectedPort, setSelectedPort] = useState(null);
  const [selectedPortInfo, setSelectedPortInfo] = useState(null); // for port sidebar (2B)
  const mapRef = useRef(null);

  // Inject pulse animation CSS
  useEffect(() => {
    const id = "vessel-map-pulse-css";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      .port-sonar { position: relative; width: 36px; height: 36px; pointer-events: none; }
      .port-sonar-ring {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        border-radius: 50%;
        opacity: 0;
      }
      .port-sonar-high .port-sonar-ring {
        border: 2px solid #DC2626;
        animation: sonar-fast 1.8s ease-out infinite;
      }
      .port-sonar-med .port-sonar-ring {
        border: 1.5px solid #D97706;
        animation: sonar-med 2.5s ease-out infinite;
      }
      .port-sonar-low .port-sonar-ring {
        border: 1px solid #059669;
        animation: sonar-slow 3.5s ease-out infinite;
      }
      .port-circle-clickable { cursor: pointer; }
      @keyframes sonar-fast {
        0%   { transform: scale(0.5); opacity: 0.6; }
        100% { transform: scale(2.0); opacity: 0; }
      }
      @keyframes sonar-med {
        0%   { transform: scale(0.5); opacity: 0.4; }
        100% { transform: scale(1.8); opacity: 0; }
      }
      @keyframes sonar-slow {
        0%   { transform: scale(0.5); opacity: 0.25; }
        100% { transform: scale(1.5); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
    return () => { const el = document.getElementById(id); if (el) el.remove(); };
  }, []);

  // Filter to US-bound vessels only + split counts: at port vs en route
  const { usVessels, portVesselCounts, portAtPort, portEnRoute } = useMemo(() => {
    const counts = {};
    const atPort = {};
    const enRoute = {};
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
          const isAtPort = v.nav_status_label === "At Anchor" || v.nav_status_label === "Moored";
          if (isAtPort) {
            atPort[resolvedPort] = (atPort[resolvedPort] || 0) + 1;
          } else {
            enRoute[resolvedPort] = (enRoute[resolvedPort] || 0) + 1;
          }
        }
      }
    }

    return { usVessels: usOnly, portVesselCounts: counts, portAtPort: atPort, portEnRoute: enRoute };
  }, [vessels]);

  // STRESS_TEST: uncomment to simulate 10K vessels
  // const stressVessels = useMemo(() => {
  //   const result = [...usVessels];
  //   const target = 10000;
  //   let idx = 0;
  //   while (result.length < target && usVessels.length > 0) {
  //     const src = usVessels[idx % usVessels.length];
  //     result.push({
  //       ...src,
  //       mmsi: src.mmsi + 100000 + result.length,
  //       lat: src.lat + (Math.random() - 0.5) * 2,
  //       lon: src.lon + (Math.random() - 0.5) * 2,
  //     });
  //     idx++;
  //   }
  //   return result;
  // }, [usVessels]);
  // To enable: replace `usVessels` with `stressVessels` in the filtered line below

  const filtered = useMemo(() => usVessels.filter(v => {
    if (typeFilters.size < VESSEL_TYPES.length && !typeFilters.has(v.vessel_type_label)) return false;
    if (statusFilter && v.nav_status_label !== statusFilter) return false;
    // Hide vessels with no useful info (unknown type + no destination)
    const hasType = v.vessel_type_label && v.vessel_type_label !== "Unknown";
    const hasDest = v.destination && v.destination.trim() !== "";
    if (!hasType && !hasDest) return false;
    return true;
  }), [usVessels, typeFilters, statusFilter]);

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
      const atPort = portAtPort[name] || 0;
      const enRoute = portEnRoute[name] || 0;
      const portcalls = cong?.last_portcalls ?? 0;
      const score = cong?.current_score ?? 50;
      const status = cong?.status || "MEDIUM";
      const isMajor = MAJOR_PORTS.has(name);
      const baseRadius = isMajor
        ? Math.min(8000 + vesselCount * 500, 30000)
        : Math.min(3000 + vesselCount * 400, 25000);
      // Phase 6A.2 — coverage classification (default "covered" if snapshot
      // missing or empty: fail-open so a backend hiccup doesn't ghost the map).
      const coverage = coverageMap[name] || "covered";
      const isUnverified = coverage === "dark" || coverage === "sparse" || coverage === "unavailable";
      markers.push({ name, coords, vesselCount, atPort, enRoute, portcalls, score, status, baseRadius, isMajor, coverage, isUnverified });
    }
    return markers;
  }, [congestionPorts, portVesselCounts, portAtPort, portEnRoute, coverageMap]);

  // Fly-to handler for rerouting alternatives and port clicks
  const handleFlyTo = useCallback((coords, portName) => {
    if (mapRef.current) {
      mapRef.current.flyTo(coords, 10, { duration: 1.2 });
    }
  }, []);

  // Stable cluster icon factory — avoids MarkerClusterGroup re-init on every render
  const clusterIconCreate = useCallback((cluster) => {
    const count = cluster.getChildCount();
    const size = count < 50 ? 30 : count < 200 ? 38 : 46;
    return L.divIcon({
      html: `<div style="
        width:${size}px;height:${size}px;
        background:var(--teal-subtle);
        border:2px solid var(--accent-teal);
        border-radius:50%;
        display:flex;align-items:center;justify-content:center;
        font-family:${T.mono};font-size:${size < 38 ? 10 : 12}px;
        font-weight:700;color:${T.teal};
      ">${count}</div>`,
      className: "",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }, []);

  // Stable port-click handler — avoids PortLayer re-render from new function ref
  const handlePortClick = useCallback((p) => {
    setSelectedPortInfo(p);
    setSelected(null);
  }, []);

  return (
    <div style={{ height: "100%", position: "relative", background: T.navy }}>
      {/* Stats overlay */}
      <div style={{
        position: "absolute", top: 12, left: 12, zIndex: 1000,
        background: T.navy2Overlay, border: `1px solid ${T.border}`,
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
        <MultiSelectDropdown label="Vessel Type" selected={typeFilters} options={VESSEL_TYPES} onChange={setTypeFilters} />
        <FilterDropdown label="Nav Status" value={statusFilter} options={NAV_STATUSES} onChange={setStatusFilter} />
        <FilterDropdown label="Congestion" value={congestionFilter} options={["HIGH", "MEDIUM", "LOW"]} onChange={setCongestionFilter} />
        <button onClick={() => setShowPorts(p => !p)} style={{
          background: showPorts ? T.tealSubtle : T.navy2,
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
        background: T.navy2Overlay, border: `1px solid ${T.border}`,
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
          key={isDark ? "dark-tiles" : "light-tiles"}
          url={isDark
            ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"}
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        />
        <MapRefSetter mapRef={mapRef} />
        <ResetView center={US_CENTER} zoom={US_ZOOM} />
        <FlyToPort port={selectedPort} />

        {/* Port layer (owns zoom state — zoom changes only rerender ports, not vessels) */}
        <PortLayer portMarkers={congestionFilter
          ? portMarkers.filter(p => p.status === congestionFilter)
          : portMarkers} showPorts={showPorts} onPortClick={handlePortClick} />

        {/* Vessel markers — clustered at low zoom, individual at zoom ≥ 10 */}
        <MarkerClusterGroup
          disableClusteringAtZoom={10}
          maxClusterRadius={60}
          spiderfyOnMaxZoom={false}
          showCoverageOnHover={false}
          iconCreateFunction={clusterIconCreate}
        >
          {filtered.map(v => (
            <Marker
              key={v.mmsi}
              position={[v.lat, v.lon]}
              icon={getVesselIcon(v.vessel_type_label || "Unknown", getVesselColor(v), selected === v.mmsi)}
              eventHandlers={{
                click: () => {
                  setSelected(v.mmsi === selected ? null : v.mmsi);
                  setSelectedPortInfo(null); // close port panel
                },
              }}
            >
              <Tooltip direction="top" offset={[0, -6]} opacity={0.95}>
                <div style={{ fontFamily: T.sans, fontSize: 11, lineHeight: 1.4 }}>
                  <strong>{v.name || "Unknown"}</strong><br />
                  {v.vessel_type_label || "Unknown"} · {v.sog ?? 0} kn<br />
                  {v.destination ? `→ ${v.destination}` : "No destination"}
                </div>
              </Tooltip>
            </Marker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      {/* Selected vessel panel */}
      <VesselPanel vessel={selectedVessel} onClose={() => setSelected(null)} portMarkers={portMarkers} onFlyTo={handleFlyTo} />

      {/* Selected port panel */}
      <PortPanel portInfo={selectedPortInfo} onClose={() => setSelectedPortInfo(null)} />
    </div>
  );
}
