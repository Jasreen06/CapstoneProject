import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Navigation, Anchor, Ship, MapPin, Clock, RotateCcw, Compass, ArrowRight, BarChart3, Info, Globe, Navigation2 } from 'lucide-react';
import { fetchJSON } from '../api/client.js';
import { NAV_STATUS_LABELS, NAV_STATUS_DESCRIPTIONS, VESSEL_TYPE_DESCRIPTIONS, PORT_COORDS } from '../utils/constants.js';
import { haversineNm, estimateEta } from '../utils/trajectory.js';
import ReroutingPanel from './ReroutingPanel.jsx';

function InfoRow({ label, value, highlight }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex justify-between py-1.5 border-b border-slate-700/50">
      <span className="text-slate-400 text-sm">{label}</span>
      <span className={`text-sm font-medium ${highlight ? 'text-blue-400' : 'text-slate-100'}`}>{value}</span>
    </div>
  );
}

function resolveDestPort(destination) {
  if (!destination) return null;
  const destUpper = destination.toUpperCase();
  const keywords = {
    'LOS ANGELES': 'Los Angeles-Long Beach', 'LONG BEACH': 'Los Angeles-Long Beach',
    'LA/LB': 'Los Angeles-Long Beach', 'LALB': 'Los Angeles-Long Beach',
    'OAKLAND': 'Oakland', 'SEATTLE': 'Seattle', 'TACOMA': 'Tacoma',
    'SAN DIEGO': 'San Diego', 'SAN FRANC': 'San Francisco',
    'HOUSTON': 'Houston', 'NEW ORLEANS': 'New Orleans', 'NOLA': 'New Orleans',
    'CORPUS CHR': 'Corpus Christi',
    'NEW YORK': 'New York-New Jersey', 'NY/NJ': 'New York-New Jersey', 'NEWARK': 'New York-New Jersey',
    'SAVANNAH': 'Savannah', 'CHARLESTON': 'Charleston', 'BALTIMORE': 'Baltimore',
    'NORFOLK': 'Norfolk', 'PHILADELPHIA': 'Philadelphia', 'PHILLY': 'Philadelphia',
    'MIAMI': 'Miami', 'BOSTON': 'Boston',
    'JACKSONVILLE': 'Jacksonville', 'JAX': 'Jacksonville',
    'TAMPA': 'Tampa', 'MOBILE': 'Mobile', 'GALVESTON': 'Galveston',
    'PORTLAND OR': 'Portland, OR', 'PORTLAND,OR': 'Portland, OR',
    'FREEPORT': 'Freeport', 'CHICAGO': 'Chicago', 'DETROIT': 'Detroit',
    'CLEVELAND': 'Cleveland', 'DULUTH': 'Duluth', 'HONOLULU': 'Honolulu',
    'BATON ROUGE': 'Baton Rouge', 'PORT ARTHUR': 'Port Arthur',
    'BEAUMONT': 'Beaumont', 'LAKE CHARLES': 'Lake Charles',
    'PORT EVERGLADES': 'Port Everglades', 'FT LAUDERDALE': 'Port Everglades',
    'CANAVERAL': 'Canaveral Harbor', 'GULFPORT': 'Gulfport',
    'SOUTH LOUIS': 'South Louisiana', 'TEXAS CITY': 'Texas City',
    'ANCHORAGE': 'Anchorage (Alaska)', 'BRUNSWICK': 'Brunswick',
    'WILMINGTON NC': 'Wilmington, NC', 'WILMINGTON DE': 'Wilmington, DE',
    'PASCAGOULA': 'Pascagoula', 'PENSACOLA': 'Pensacola',
  };
  for (const [kw, portName] of Object.entries(keywords)) {
    if (destUpper.includes(kw)) {
      const coords = PORT_COORDS[portName];
      if (coords) return { name: portName, lat: coords[0], lon: coords[1] };
    }
  }
  return null;
}

function findNearestPort(lat, lon) {
  if (!lat || !lon) return null;
  let best = null;
  let bestDist = Infinity;
  for (const [name, coords] of Object.entries(PORT_COORDS)) {
    const dist = haversineNm(lat, lon, coords[0], coords[1]);
    if (dist < bestDist) {
      bestDist = dist;
      best = { name, distNm: dist };
    }
  }
  return best;
}

export default function VesselDetail({ vessel, onClose, onNavigateToPort }) {
  const [rerouting, setRerouting] = useState(null);
  const [loadingReroute, setLoadingReroute] = useState(false);
  const [rerouteError, setRerouteError] = useState(null);
  const [showTypeInfo, setShowTypeInfo] = useState(false);
  const [showStatusInfo, setShowStatusInfo] = useState(false);
  const navigate = useNavigate();

  const fetchRerouting = () => {
    setLoadingReroute(true);
    setRerouteError(null);
    fetchJSON(`/api/vessels/${vessel.mmsi}/rerouting`)
      .then(setRerouting)
      .catch(e => setRerouteError(e.message))
      .finally(() => setLoadingReroute(false));
  };

  const navStatus = NAV_STATUS_LABELS[vessel.nav_status] || vessel.nav_status_label || 'Unknown';
  const navStatusDesc = NAV_STATUS_DESCRIPTIONS[vessel.nav_status];
  const typeDesc = VESSEL_TYPE_DESCRIPTIONS[(vessel.vessel_type_label || '').replace(/ \(Haz.*\)/, '')];

  // Resolve destination to a known US port
  const destInfo = useMemo(() => {
    const port = resolveDestPort(vessel.destination);
    if (!port || !vessel.lat || !vessel.lon) return null;
    const distNm = haversineNm(vessel.lat, vessel.lon, port.lat, port.lon);
    const etaHours = estimateEta(distNm, vessel.sog);
    return { portName: port.name, distNm, etaHours, isUS: true };
  }, [vessel.destination, vessel.lat, vessel.lon, vessel.sog]);

  // Detect international destination (has destination text but no US port match)
  const isInternational = vessel.destination && !destInfo;

  // Find nearest port as origin reference
  const nearestPort = useMemo(() => {
    return findNearestPort(vessel.lat, vessel.lon);
  }, [vessel.lat, vessel.lon]);

  const statusIcon = vessel.nav_status === 5 ? Anchor : vessel.nav_status === 0 ? Navigation : Anchor;
  const StatusIcon = statusIcon;

  return (
    <div className="bg-slate-800 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <Ship size={18} className="text-blue-400" />
          <div>
            <h2 className="text-white font-semibold text-sm leading-tight">
              {vessel.name || `Vessel ${vessel.mmsi}`}
            </h2>
            <p className="text-slate-400 text-xs">MMSI: {vessel.mmsi}</p>
          </div>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-700 transition-colors">
          <X size={16} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Status badge */}
        <div>
          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${
            vessel.nav_status === 0 ? 'bg-green-900/40 text-green-400 border border-green-700/30' :
            vessel.nav_status === 1 ? 'bg-orange-900/40 text-orange-400 border border-orange-700/30' :
            vessel.nav_status === 5 ? 'bg-cyan-900/40 text-cyan-400 border border-cyan-700/30' :
            'bg-slate-700/40 text-slate-400 border border-slate-600/30'
          }`}>
            <StatusIcon size={10} />
            {navStatus}
            <button onClick={() => setShowStatusInfo(s => !s)} className="ml-1 opacity-60 hover:opacity-100">
              <Info size={9} />
            </button>
          </div>
          {showStatusInfo && navStatusDesc && (
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed bg-slate-700/30 rounded p-2">
              {navStatusDesc}
            </p>
          )}
        </div>

        {/* Origin (nearest port) */}
        {nearestPort && (
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Current Location</h3>
            <div className="flex items-center gap-2 bg-slate-700/40 rounded-lg p-2.5">
              <Navigation2 size={14} className="text-green-400 shrink-0" />
              <div className="flex-1">
                <span className="text-white text-sm font-medium">Near {nearestPort.name}</span>
                <span className="text-slate-500 text-xs ml-2">({Math.round(nearestPort.distNm)} nm away)</span>
              </div>
              <button
                onClick={() => onNavigateToPort?.(nearestPort.name)}
                className="text-green-400 hover:text-green-300 transition-colors"
                title="View Port Intelligence"
              >
                <BarChart3 size={14} />
              </button>
            </div>
          </div>
        )}

        {/* Position & Movement */}
        <div className="space-y-0.5">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Position</h3>
          <InfoRow label="Latitude" value={vessel.lat?.toFixed(5)} />
          <InfoRow label="Longitude" value={vessel.lon?.toFixed(5)} />
          <InfoRow label="Speed (SOG)" value={vessel.sog != null ? `${vessel.sog} kn` : null} />
          <InfoRow label="Course (COG)" value={vessel.cog != null ? `${vessel.cog}\u00B0` : null} />
          <InfoRow label="Heading" value={vessel.heading != null && vessel.heading !== 511 ? `${vessel.heading}\u00B0` : null} />
          <InfoRow label="Rate of Turn" value={vessel.rate_of_turn} />
        </div>

        {/* Vessel Info */}
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Vessel</h3>
            {typeDesc && (
              <button onClick={() => setShowTypeInfo(s => !s)} className="text-slate-500 hover:text-slate-400">
                <Info size={10} />
              </button>
            )}
          </div>
          {showTypeInfo && typeDesc && (
            <p className="text-xs text-slate-500 mb-2 leading-relaxed bg-slate-700/30 rounded p-2">
              {typeDesc}
            </p>
          )}
          <InfoRow label="Type" value={vessel.vessel_type_label} />
          <InfoRow label="Draught" value={vessel.draught ? `${vessel.draught}m` : null} />
          <InfoRow label="Call Sign" value={vessel.call_sign} />
          <InfoRow label="IMO" value={vessel.imo} />
        </div>

        {/* Destination + Distance/ETA */}
        {vessel.destination && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Destination</h3>

            {/* Raw AIS destination */}
            <div className="flex items-center gap-2 bg-slate-700/50 rounded-lg p-2.5">
              <MapPin size={14} className={isInternational ? 'text-amber-400 shrink-0' : 'text-blue-400 shrink-0'} />
              <div className="flex-1 min-w-0">
                <span className="text-white text-sm font-medium block">{vessel.destination}</span>
                {destInfo && destInfo.portName !== vessel.destination && (
                  <span className="text-slate-400 text-xs">Resolved: {destInfo.portName}</span>
                )}
                {isInternational && (
                  <span className="text-amber-400 text-xs flex items-center gap-1 mt-0.5">
                    <Globe size={10} /> International / Unresolved destination
                  </span>
                )}
              </div>
              {destInfo && (
                <button
                  onClick={() => onNavigateToPort?.(destInfo.portName)}
                  className="text-blue-400 hover:text-blue-300 transition-colors"
                  title="View Port Intelligence"
                >
                  <BarChart3 size={14} />
                </button>
              )}
            </div>

            {/* Route summary: Origin → Destination */}
            {nearestPort && destInfo && (
              <div className="bg-slate-700/30 rounded-lg p-2.5 flex items-center gap-2 text-xs">
                <span className="text-green-400 font-medium truncate">{nearestPort.name}</span>
                <ArrowRight size={12} className="text-slate-500 shrink-0" />
                <span className="text-blue-400 font-medium truncate">{destInfo.portName}</span>
              </div>
            )}

            {/* Distance and ETA */}
            {destInfo && (
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-700/30 rounded-lg p-2.5 text-center">
                  <Compass size={14} className="mx-auto text-blue-400 mb-1" />
                  <p className="text-white font-semibold text-sm">{Math.round(destInfo.distNm)} nm</p>
                  <p className="text-slate-500 text-xs">Distance</p>
                </div>
                <div className="bg-slate-700/30 rounded-lg p-2.5 text-center">
                  <Clock size={14} className="mx-auto text-amber-400 mb-1" />
                  <p className="text-white font-semibold text-sm">
                    {destInfo.etaHours != null
                      ? destInfo.etaHours < 24
                        ? `~${Math.round(destInfo.etaHours)}h`
                        : `~${(destInfo.etaHours / 24).toFixed(1)}d`
                      : '\u2014'}
                  </p>
                  <p className="text-slate-500 text-xs">
                    {destInfo.etaHours != null && destInfo.etaHours >= 24
                      ? `(${Math.round(destInfo.etaHours)}h)`
                      : 'Est. Arrival'}
                  </p>
                </div>
              </div>
            )}

            {/* International destination notice */}
            {isInternational && (
              <div className="bg-amber-900/20 border border-amber-700/30 rounded-lg p-2.5 text-xs text-amber-300">
                <Globe size={11} className="inline mr-1" />
                This vessel's destination does not match a tracked US port. Rerouting analysis and congestion data are only available for US ports.
              </div>
            )}

            {vessel.eta_crew && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Clock size={12} />
                <span>Crew ETA: {vessel.eta_crew}</span>
              </div>
            )}
          </div>
        )}

        {/* Last update */}
        {vessel.last_update && (
          <p className="text-xs text-slate-500">
            Last seen: {new Date(vessel.last_update).toLocaleTimeString()}
          </p>
        )}

        {/* Actions */}
        <div className="space-y-2 pt-2 border-t border-slate-700">
          {!rerouting && (
            <button
              onClick={fetchRerouting}
              disabled={loadingReroute || !vessel.destination || isInternational}
              className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded-lg font-medium transition-colors"
            >
              <RotateCcw size={14} />
              {loadingReroute ? 'Analyzing...' : isInternational ? 'Rerouting N/A (International)' : 'Get Rerouting Analysis'}
            </button>
          )}

          {destInfo && (
            <button
              onClick={() => onNavigateToPort?.(destInfo.portName)}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white text-sm rounded-lg font-medium transition-colors"
            >
              <BarChart3 size={14} />
              View {destInfo.portName} Intelligence
              <ArrowRight size={12} />
            </button>
          )}
        </div>

        {rerouteError && (
          <p className="text-red-400 text-xs">{rerouteError}</p>
        )}

        {rerouting && (
          <div className="animate-fadeInUp">
            <ReroutingPanel
              reroutingData={rerouting}
              onClose={() => setRerouting(null)}
              showMapLink={false}
              vesselMmsi={vessel.mmsi}
            />
          </div>
        )}
      </div>
    </div>
  );
}
