import { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, useMap, Tooltip as LTooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { useVessels } from '../hooks/useVessels.js';
import { projectTrajectory, haversineNm, estimateEta } from '../utils/trajectory.js';
import {
  PORT_COORDS, VESSEL_TYPE_COLORS, NAV_STATUS_COLORS, MAP_LEGEND,
  VESSEL_TYPE_FILTER_OPTIONS, NAV_STATUS_FILTER_OPTIONS,
  VESSEL_TYPE_DESCRIPTIONS, NAV_STATUS_DESCRIPTIONS, CONGESTION_COLORS,
} from '../utils/constants.js';
import VesselDetail from './VesselDetail.jsx';
import { Wifi, WifiOff, Filter, Info, Maximize2, Eye, EyeOff } from 'lucide-react';

function getVesselColor(vessel) {
  const status = vessel.nav_status;
  const statusColor = NAV_STATUS_COLORS[status];
  if (statusColor) return statusColor;
  const typeLabel = (vessel.vessel_type_label || '').replace(/ \(Haz.*\)/, '');
  return VESSEL_TYPE_COLORS[typeLabel] || VESSEL_TYPE_COLORS.Unknown;
}

function findNearestPort(lat, lon) {
  if (!lat || !lon) return null;
  let best = null;
  let bestDist = Infinity;
  for (const [name, [pLat, pLon]] of Object.entries(PORT_COORDS)) {
    const dist = haversineNm(lat, lon, pLat, pLon);
    if (dist < bestDist) {
      bestDist = dist;
      best = { name, lat: pLat, lon: pLon, distNm: dist };
    }
  }
  return best;
}

function resolveDestPort(destination) {
  if (!destination) return null;
  const destUpper = destination.toUpperCase();
  const keywords = {
    'LOS ANGELES': 'Los Angeles-Long Beach', 'LONG BEACH': 'Los Angeles-Long Beach',
    'LA/LB': 'Los Angeles-Long Beach', 'OAKLAND': 'Oakland',
    'SEATTLE': 'Seattle', 'TACOMA': 'Tacoma', 'SAN DIEGO': 'San Diego',
    'HOUSTON': 'Houston', 'NEW ORLEANS': 'New Orleans', 'CORPUS CHR': 'Corpus Christi',
    'NEW YORK': 'New York-New Jersey', 'NY/NJ': 'New York-New Jersey', 'NEWARK': 'New York-New Jersey',
    'SAVANNAH': 'Savannah', 'CHARLESTON': 'Charleston', 'BALTIMORE': 'Baltimore',
    'NORFOLK': 'Norfolk', 'PHILADELPHIA': 'Philadelphia', 'MIAMI': 'Miami',
    'BOSTON': 'Boston', 'JACKSONVILLE': 'Jacksonville', 'JAX': 'Jacksonville',
    'TAMPA': 'Tampa', 'MOBILE': 'Mobile', 'GALVESTON': 'Galveston',
    'PORTLAND OR': 'Portland, OR', 'PORTLAND,OR': 'Portland, OR',
    'FREEPORT': 'Freeport', 'CHICAGO': 'Chicago', 'DETROIT': 'Detroit',
    'CLEVELAND': 'Cleveland', 'DULUTH': 'Duluth', 'HONOLULU': 'Honolulu',
    'BATON ROUGE': 'Baton Rouge', 'PORT ARTHUR': 'Port Arthur',
    'BEAUMONT': 'Beaumont', 'LAKE CHARLES': 'Lake Charles',
    'PORT EVERGLADES': 'Port Everglades', 'FT LAUDERDALE': 'Port Everglades',
    'CANAVERAL': 'Canaveral Harbor', 'GULFPORT': 'Gulfport',
    'SOUTH LOUIS': 'South Louisiana', 'TEXAS CITY': 'Texas City',
  };
  for (const [kw, portName] of Object.entries(keywords)) {
    if (destUpper.includes(kw)) {
      const coords = PORT_COORDS[portName];
      if (coords) return { name: portName, lat: coords[0], lon: coords[1] };
    }
  }
  return null;
}

// Component to fly the map to a location
function FlyTo({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) map.flyTo(center, zoom || 8, { duration: 1.5 });
  }, [center, zoom, map]);
  return null;
}

export default function VesselMap() {
  const [selectedVessel, setSelectedVessel] = useState(null);
  const [vesselTypeFilter, setVesselTypeFilter] = useState('');
  const [navStatusFilter, setNavStatusFilter] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [flyTarget, setFlyTarget] = useState(null);
  const [flyZoom, setFlyZoom] = useState(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const focusMmsi = searchParams.get('focus');
  const focusDest = searchParams.get('dest');
  const focusAlts = searchParams.get('alts')?.split(',').filter(Boolean) || [];
  const isolateMode = searchParams.has('focus'); // When navigating from rerouting, isolate
  const focusedRef = useRef(false);

  const { vesselList, isConnected } = useVessels({
    vesselType: vesselTypeFilter || undefined,
    navStatus: navStatusFilter || undefined,
  });

  // Handle focus from URL params
  useEffect(() => {
    if (!focusMmsi || focusedRef.current || vesselList.length === 0) return;
    const mmsi = parseInt(focusMmsi);
    const vessel = vesselList.find(v => v.mmsi === mmsi);
    if (vessel) {
      setSelectedVessel(vessel);
      const destPort = resolveDestPort(vessel.destination);
      if (destPort) {
        const cLat = (vessel.lat + destPort.lat) / 2;
        const cLon = (vessel.lon + destPort.lon) / 2;
        setFlyTarget([cLat, cLon]);
        const span = Math.max(Math.abs(vessel.lat - destPort.lat), Math.abs(vessel.lon - destPort.lon));
        setFlyZoom(span > 15 ? 4 : span > 8 ? 5 : span > 3 ? 7 : 9);
      } else {
        setFlyTarget([vessel.lat, vessel.lon]);
        setFlyZoom(8);
      }
      focusedRef.current = true;
    }
  }, [focusMmsi, vesselList]);

  const handleVesselClick = useCallback((vessel) => {
    setSelectedVessel(vessel);
    const destPort = resolveDestPort(vessel.destination);
    if (destPort) {
      const cLat = (vessel.lat + destPort.lat) / 2;
      const cLon = (vessel.lon + destPort.lon) / 2;
      setFlyTarget([cLat, cLon]);
      const span = Math.max(Math.abs(vessel.lat - destPort.lat), Math.abs(vessel.lon - destPort.lon));
      setFlyZoom(span > 15 ? 4 : span > 8 ? 5 : span > 3 ? 7 : 9);
    } else {
      setFlyTarget([vessel.lat, vessel.lon]);
      setFlyZoom(10);
    }
  }, []);

  // In isolated mode, only show the focused vessel
  const displayVessels = useMemo(() => {
    if (isolateMode && focusMmsi) {
      const mmsi = parseInt(focusMmsi);
      return vesselList.filter(v => v.mmsi === mmsi);
    }
    return vesselList;
  }, [vesselList, isolateMode, focusMmsi]);

  // Trajectory for selected vessel
  const trajectory = useMemo(() => {
    if (!selectedVessel?.lat || !selectedVessel?.lon || !selectedVessel?.sog) return [];
    return projectTrajectory(selectedVessel.lat, selectedVessel.lon, selectedVessel.sog, selectedVessel.cog, 24)
      .map(p => [p.lat, p.lon]);
  }, [selectedVessel]);

  // Destination port info for selected vessel
  const destPort = useMemo(() => resolveDestPort(selectedVessel?.destination), [selectedVessel?.destination]);

  const resetView = () => {
    setFlyTarget([37.5, -96.0]);
    setFlyZoom(4);
    // Clear isolation mode
    if (isolateMode) {
      setSearchParams({}, { replace: true });
      focusedRef.current = false;
    }
  };

  const exitIsolation = () => {
    setSearchParams({}, { replace: true });
    focusedRef.current = false;
    setSelectedVessel(null);
  };

  const stats = useMemo(() => ({
    total: displayVessels.length,
    underway: displayVessels.filter(v => v.nav_status === 0).length,
    anchored: displayVessels.filter(v => v.nav_status === 1).length,
    moored: displayVessels.filter(v => v.nav_status === 5).length,
  }), [displayVessels]);

  return (
    <div className="flex h-full" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Map area */}
      <div className="flex-1 relative">
        {/* Stats overlay */}
        <div className="absolute top-3 left-3 z-[1000] bg-slate-800/90 border border-slate-700 rounded-lg px-3 py-2 backdrop-blur-sm">
          <p className="text-white font-bold text-xs">Vessels tracked: {stats.total}</p>
          <p className="text-slate-400 text-xs">
            Underway: {stats.underway}  Anchored: {stats.anchored}  Moored: {stats.moored}
          </p>
        </div>

        {/* Isolation mode banner */}
        {isolateMode && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] bg-blue-900/90 border border-blue-600/50 rounded-lg px-4 py-2 backdrop-blur-sm flex items-center gap-3">
            <Eye size={14} className="text-blue-400" />
            <span className="text-blue-200 text-xs font-medium">Focused View — Showing selected vessel only</span>
            <button onClick={exitIsolation} className="flex items-center gap-1 px-2 py-0.5 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded transition-colors">
              <EyeOff size={10} /> Show All
            </button>
          </div>
        )}

        {/* Right controls */}
        <div className="absolute top-3 right-3 z-[1000] flex flex-col gap-2" style={{ maxHeight: 'calc(100vh - 80px)', overflowY: 'auto' }}>
          <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium backdrop-blur-sm ${
            isConnected ? 'bg-green-900/60 text-green-400 border border-green-700/50' : 'bg-red-900/60 text-red-400 border border-red-700/50'
          }`}>
            {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
            {isConnected ? 'Live' : 'Reconnecting...'}
          </div>

          <button onClick={resetView}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs bg-slate-800/90 text-slate-300 border border-slate-700 hover:bg-slate-700 backdrop-blur-sm transition-colors"
            title="Reset view"
          >
            <Maximize2 size={12} /> Reset
          </button>

          <button
            onClick={() => setShowFilters(f => !f)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium backdrop-blur-sm transition-colors ${
              showFilters ? 'bg-blue-600/80 text-white border border-blue-500/50' : 'bg-slate-800/90 text-slate-300 border border-slate-700 hover:bg-slate-700'
            }`}
          >
            <Filter size={12} /> Filter
          </button>

          {showFilters && (
            <div className="bg-slate-800/95 border border-slate-700 rounded-lg p-3 text-xs space-y-3 backdrop-blur-sm w-56 animate-fadeInUp">
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Vessel Type</label>
                <select value={vesselTypeFilter} onChange={e => setVesselTypeFilter(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-md px-2 py-1.5 text-slate-200 focus:border-blue-500 focus:outline-none">
                  {VESSEL_TYPE_FILTER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                {vesselTypeFilter && VESSEL_TYPE_DESCRIPTIONS[vesselTypeFilter] && (
                  <p className="text-slate-500 mt-1 leading-snug"><Info size={9} className="inline mr-1" />{VESSEL_TYPE_DESCRIPTIONS[vesselTypeFilter]}</p>
                )}
              </div>
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Navigation Status</label>
                <select value={navStatusFilter} onChange={e => setNavStatusFilter(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-md px-2 py-1.5 text-slate-200 focus:border-blue-500 focus:outline-none">
                  {NAV_STATUS_FILTER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                {navStatusFilter && NAV_STATUS_DESCRIPTIONS[parseInt(navStatusFilter)] && (
                  <p className="text-slate-500 mt-1 leading-snug"><Info size={9} className="inline mr-1" />{NAV_STATUS_DESCRIPTIONS[parseInt(navStatusFilter)]}</p>
                )}
              </div>
              {(vesselTypeFilter || navStatusFilter) && (
                <button onClick={() => { setVesselTypeFilter(''); setNavStatusFilter(''); }}
                  className="w-full text-center text-blue-400 hover:text-blue-300 text-xs py-1">Clear all filters</button>
              )}
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="absolute bottom-3 left-3 z-[1000] bg-slate-800/90 border border-slate-700 rounded-lg p-2.5 text-xs flex flex-wrap gap-x-3 gap-y-1.5 backdrop-blur-sm">
          {MAP_LEGEND.map(({ label, color, shape }) => (
            <div key={label} className="flex items-center gap-1.5">
              {shape === 'diamond' ? (
                <svg width="10" height="10" viewBox="0 0 10 10"><polygon points="5,0 10,5 5,10 0,5" fill={color} /></svg>
              ) : shape === 'square' ? (
                <span className="w-2.5 h-2.5" style={{ background: color }} />
              ) : (
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
              )}
              <span className="text-slate-400">{label}</span>
            </div>
          ))}
        </div>

        {/* Leaflet Map */}
        <MapContainer
          center={[37.5, -96.0]}
          zoom={4}
          style={{ width: '100%', height: '100%' }}
          zoomControl={false}
          attributionControl={false}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; OpenStreetMap'
          />

          {flyTarget && <FlyTo center={flyTarget} zoom={flyZoom} />}

          {/* Port markers for highlighted destinations/alternatives */}
          {focusDest && Object.entries(PORT_COORDS).map(([name, [lat, lon]]) => {
            const isDest = name.toLowerCase().includes(focusDest.toLowerCase());
            const isAlt = focusAlts.some(a => name.toLowerCase().includes(a.toLowerCase()));
            if (!isDest && !isAlt) return null;
            return (
              <CircleMarker
                key={`port-${name}`}
                center={[lat, lon]}
                radius={isDest ? 10 : 8}
                pathOptions={{
                  color: isDest ? '#ef4444' : '#22c55e',
                  fillColor: isDest ? '#ef4444' : '#22c55e',
                  fillOpacity: 0.3,
                  weight: 2,
                  dashArray: isDest ? '5 3' : '4 3',
                }}
              >
                <LTooltip permanent direction="top" className="custom-tooltip">
                  <span style={{ color: isDest ? '#ef4444' : '#22c55e', fontWeight: 'bold', fontSize: '11px' }}>
                    {isDest ? `DEST: ${name}` : `ALT: ${name}`}
                  </span>
                </LTooltip>
              </CircleMarker>
            );
          })}

          {/* Destination port highlight for selected vessel */}
          {destPort && selectedVessel && (
            <CircleMarker
              center={[destPort.lat, destPort.lon]}
              radius={10}
              pathOptions={{ color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.2, weight: 2, dashArray: '5 3' }}
            >
              <LTooltip permanent direction="top" className="custom-tooltip">
                <span style={{ color: '#ef4444', fontWeight: 'bold', fontSize: '11px' }}>
                  DEST: {destPort.name}
                </span>
              </LTooltip>
            </CircleMarker>
          )}

          {/* Trajectory line */}
          {trajectory.length > 0 && selectedVessel && (
            <Polyline
              positions={[[selectedVessel.lat, selectedVessel.lon], ...trajectory]}
              pathOptions={{ color: '#3b82f6', weight: 2, dashArray: '8 6', opacity: 0.7 }}
            />
          )}

          {/* Vessel markers */}
          {displayVessels.map(vessel => {
            if (!vessel.lat || !vessel.lon) return null;
            const color = getVesselColor(vessel);
            const isSelected = selectedVessel?.mmsi === vessel.mmsi;
            return (
              <CircleMarker
                key={vessel.mmsi}
                center={[vessel.lat, vessel.lon]}
                radius={isSelected ? 8 : 4}
                pathOptions={{
                  color: isSelected ? '#ffffff' : color,
                  fillColor: color,
                  fillOpacity: isSelected ? 1 : 0.8,
                  weight: isSelected ? 2 : 1,
                }}
                eventHandlers={{ click: () => handleVesselClick(vessel) }}
              >
                <LTooltip direction="top" className="custom-tooltip">
                  <div style={{ fontSize: '11px' }}>
                    <strong>{vessel.name || `MMSI ${vessel.mmsi}`}</strong><br/>
                    {vessel.vessel_type_label} · {vessel.sog} kn
                    {vessel.destination && <><br/>→ {vessel.destination}</>}
                  </div>
                </LTooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      {/* Side panel */}
      {selectedVessel && (
        <div className="w-96 border-l border-slate-700 overflow-y-auto animate-fadeInUp shrink-0">
          <VesselDetail
            vessel={selectedVessel}
            onClose={() => { setSelectedVessel(null); if (isolateMode) exitIsolation(); }}
            onNavigateToPort={(portName) => navigate(`/ports?port=${encodeURIComponent(portName)}`)}
          />
        </div>
      )}
    </div>
  );
}
