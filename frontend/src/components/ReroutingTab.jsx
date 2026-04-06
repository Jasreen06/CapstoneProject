import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchJSON } from '../api/client.js';
import { CONGESTION_COLORS, CONGESTION_BG, PORT_ALTERNATIVES } from '../utils/constants.js';
import { Route, Search, Map, AlertTriangle, ChevronDown, ChevronUp, Ship, ArrowRight, Anchor, RefreshCw } from 'lucide-react';
import ReroutingPanel from './ReroutingPanel.jsx';

function VesselRerouteCard({ alert }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const { vessel, resolved_port, congestion_score, congestion_level, rerouting } = alert;

  const color = CONGESTION_COLORS[congestion_level] || '#64748b';
  const alts = rerouting?.alternatives?.map(a => a.port).join(',') || '';

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden animate-fadeInUp transition-all hover:border-slate-600">
      {/* Card header */}
      <div className="p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <Ship size={16} className="text-blue-400 shrink-0" />
            <div className="min-w-0">
              <p className="text-white font-semibold text-sm truncate">{vessel.name || `MMSI ${vessel.mmsi}`}</p>
              <p className="text-slate-400 text-xs">{vessel.vessel_type_label || 'Unknown'} · {vessel.mmsi}</p>
            </div>
          </div>
          <div className="text-right shrink-0 ml-3">
            <p className="text-slate-300 text-sm">{vessel.sog || 0} kn</p>
            <div className="flex items-center gap-1.5 justify-end">
              <ArrowRight size={10} className="text-slate-500" />
              <span className="text-xs font-medium" style={{ color }}>{resolved_port}</span>
            </div>
          </div>
        </div>

        {/* Raw AIS destination if different from resolved */}
        {vessel.destination && vessel.destination !== resolved_port && (
          <p className="text-slate-500 text-xs mt-1 ml-7">AIS: {vessel.destination}</p>
        )}

        {/* Congestion badge + actions */}
        <div className="flex items-center justify-between mt-2.5">
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border ${CONGESTION_BG[congestion_level] || CONGESTION_BG.UNKNOWN}`}>
              <AlertTriangle size={9} />
              {congestion_level} ({Math.round(congestion_score)})
            </span>
            {rerouting?.should_reroute && (
              <span className="text-red-400 text-xs font-medium">Rerouting Recommended</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate(`/vessels?focus=${vessel.mmsi}&dest=${encodeURIComponent(resolved_port)}&alts=${encodeURIComponent(alts)}`)}
              className="flex items-center gap-1 px-2 py-1 text-xs text-blue-400 hover:text-blue-300 bg-blue-900/20 hover:bg-blue-900/40 rounded transition-colors"
            >
              <Map size={10} /> View on Map
            </button>
            <button
              onClick={() => setExpanded(e => !e)}
              className="flex items-center gap-1 px-2 py-1 text-xs text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 rounded transition-colors"
            >
              {expanded ? <><ChevronUp size={10} /> Hide</> : <><ChevronDown size={10} /> Details</>}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded rerouting details */}
      {expanded && rerouting && (
        <div className="border-t border-slate-700 p-3 bg-slate-800/50">
          <ReroutingPanel
            reroutingData={rerouting}
            showMapLink={true}
            vesselMmsi={vessel.mmsi}
          />
        </div>
      )}
    </div>
  );
}

export default function ReroutingTab() {
  const navigate = useNavigate();

  // Server-side alerts (pre-computed, correct data)
  const [alerts, setAlerts] = useState([]);
  const [alertsMeta, setAlertsMeta] = useState({ total: 0, high_congestion_ports: 0 });
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState(null);

  // Manual MMSI search
  const [mmsiInput, setMmsiInput] = useState('');
  const [searchVessel, setSearchVessel] = useState(null);
  const [searchRerouting, setSearchRerouting] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);

  const fetchAlerts = () => {
    setAlertsLoading(true);
    setAlertsError(null);
    fetchJSON('/api/rerouting/alerts')
      .then(data => {
        setAlerts(data.alerts || []);
        setAlertsMeta({ total: data.total || 0, high_congestion_ports: data.high_congestion_ports || 0 });
      })
      .catch(e => setAlertsError(e.message))
      .finally(() => setAlertsLoading(false));
  };

  useEffect(() => {
    fetchAlerts();
    // Refresh every 2 minutes
    const timer = setInterval(fetchAlerts, 120000);
    return () => clearInterval(timer);
  }, []);

  const lookup = async () => {
    const mmsi = parseInt(mmsiInput.trim());
    if (!mmsi) return;
    setSearchLoading(true);
    setSearchError(null);
    setSearchRerouting(null);
    try {
      const [v, r] = await Promise.all([
        fetchJSON(`/api/vessels/${mmsi}`),
        fetchJSON(`/api/vessels/${mmsi}/rerouting`),
      ]);
      setSearchVessel(v);
      setSearchRerouting(r);
    } catch (e) {
      setSearchError(e.message);
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto" style={{ height: 'calc(100vh - 56px)' }}>
      <div className="max-w-4xl mx-auto p-4 space-y-6">

        {/* Header */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Route size={20} className="text-blue-400" />
            <h2 className="text-xl font-bold text-white">Rerouting Advisor</h2>
          </div>
          <p className="text-slate-400 text-sm">
            Vessels heading to congested US ports with rerouting recommendations to lower-congestion alternatives.
            Data is computed server-side using resolved port names and live congestion scores.
          </p>
        </div>

        {/* Auto-detected vessels at congested ports (from backend) */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-red-400" />
              <h3 className="text-sm font-semibold text-white">
                Vessels Heading to Congested Ports
              </h3>
              {!alertsLoading && (
                <span className="bg-red-900/40 text-red-400 border border-red-700/30 px-2 py-0.5 rounded-full text-xs font-bold">
                  {alertsMeta.total}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {alertsMeta.high_congestion_ports > 0 && (
                <p className="text-xs text-slate-500">
                  {alertsMeta.high_congestion_ports} HIGH congestion ports
                </p>
              )}
              <button
                onClick={fetchAlerts}
                disabled={alertsLoading}
                className="flex items-center gap-1 px-2 py-1 text-xs text-slate-400 hover:text-white bg-slate-700 hover:bg-slate-600 rounded transition-colors"
              >
                <RefreshCw size={10} className={alertsLoading ? 'animate-spin' : ''} /> Refresh
              </button>
            </div>
          </div>

          {alertsLoading && alerts.length === 0 && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center animate-pulse">
              <p className="text-slate-400 text-sm">Loading rerouting alerts from server...</p>
            </div>
          )}

          {alertsError && (
            <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm mb-3">
              Failed to load alerts: {alertsError}
            </div>
          )}

          {!alertsLoading && alerts.length === 0 && !alertsError && (
            <div className="bg-green-900/20 border border-green-700/30 rounded-lg p-4 text-center">
              <Anchor size={24} className="mx-auto text-green-400 mb-2 opacity-50" />
              <p className="text-green-400 text-sm font-medium">No vessels currently need rerouting</p>
              <p className="text-slate-500 text-xs mt-1">All tracked vessels have acceptable destination congestion levels</p>
            </div>
          )}

          <div className="space-y-2">
            {alerts.slice(0, 30).map((alert) => (
              <VesselRerouteCard key={alert.vessel.mmsi} alert={alert} />
            ))}
          </div>

          {alerts.length > 30 && (
            <p className="text-slate-500 text-xs text-center mt-2">
              Showing 30 of {alertsMeta.total} vessels
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-slate-700 pt-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Search size={14} className="text-slate-400" />
            Manual Vessel Lookup
          </h3>

          <div className="flex gap-2 mb-4">
            <input
              type="number"
              value={mmsiInput}
              onChange={e => setMmsiInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && lookup()}
              placeholder="Enter MMSI (e.g., 366999999)"
              className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
            <button
              onClick={lookup}
              disabled={!mmsiInput || searchLoading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg flex items-center gap-2 text-sm font-medium transition-colors"
            >
              <Search size={14} />
              {searchLoading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>

          {searchError && (
            <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm mb-4">
              {searchError}
            </div>
          )}

          {searchVessel && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 mb-4 text-sm animate-fadeInUp">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-semibold">{searchVessel.name || `MMSI ${searchVessel.mmsi}`}</p>
                  <p className="text-slate-400 text-xs">{searchVessel.vessel_type_label} · MMSI: {searchVessel.mmsi}</p>
                </div>
                <div className="text-right">
                  <p className="text-slate-300">{searchVessel.sog} kn</p>
                  <p className="text-slate-400 text-xs">{searchVessel.destination || 'No destination'}</p>
                </div>
              </div>
            </div>
          )}

          {searchRerouting && (
            <div className="animate-fadeInUp">
              <ReroutingPanel
                reroutingData={searchRerouting}
                showMapLink={true}
                vesselMmsi={searchVessel?.mmsi}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
