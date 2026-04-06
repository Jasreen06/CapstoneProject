import { useNavigate } from 'react-router-dom';
import { X, CheckCircle, AlertTriangle, Minus, Navigation, Clock, Ruler, Map, BarChart3 } from 'lucide-react';
import { CONGESTION_COLORS } from '../utils/constants.js';

const REC_STYLES = {
  STRONG: 'bg-green-900/40 text-green-400 border-green-500/50',
  MODERATE: 'bg-yellow-900/40 text-yellow-400 border-yellow-500/50',
  WEAK: 'bg-slate-700/40 text-slate-400 border-slate-600',
  NONE: 'bg-slate-700/20 text-slate-500 border-slate-700',
};

const REC_ICONS = {
  STRONG: CheckCircle,
  MODERATE: AlertTriangle,
  WEAK: Minus,
  NONE: Minus,
};

function AltRow({ alt, index, showMapLink, vesselMmsi, destPort }) {
  const navigate = useNavigate();
  const color = CONGESTION_COLORS[alt.congestion_level] || '#64748b';
  const recStyle = REC_STYLES[alt.recommendation] || REC_STYLES.NONE;
  const RecIcon = REC_ICONS[alt.recommendation] || Minus;

  return (
    <div className={`p-3 rounded-lg border transition-all ${
      alt.recommendation === 'STRONG' ? 'border-green-500/40 bg-green-900/10' : 'border-slate-700 bg-slate-700/20'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-slate-500 text-xs font-mono">#{index + 1}</span>
          <span className="text-white text-sm font-semibold">{alt.port}</span>
        </div>
        <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border ${recStyle}`}>
          <RecIcon size={10} />
          {alt.recommendation}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full" style={{ background: color }} />
          <span style={{ color }}>{alt.congestion_level}</span>
          <span className="text-slate-500">({alt.congestion_score})</span>
        </div>
        <div className="flex items-center gap-1 text-slate-400">
          <Ruler size={10} />
          <span>{alt.additional_distance_nm > 0 ? `+${alt.additional_distance_nm}nm` : `${alt.additional_distance_nm}nm`}</span>
        </div>
        <div className="flex items-center gap-1 text-slate-400">
          <Clock size={10} />
          <span>{alt.additional_time_hours > 0 ? `+${alt.additional_time_hours}h` : `${alt.additional_time_hours}h`}</span>
        </div>
      </div>
      {!alt.draught_compatible && (
        <p className="text-xs text-red-400 mt-1">Warning: draught may exceed port depth</p>
      )}
      {showMapLink && vesselMmsi && (
        <button
          onClick={() => navigate(`/vessels?focus=${vesselMmsi}&dest=${encodeURIComponent(destPort || '')}&alts=${encodeURIComponent(alt.port)}`)}
          className="mt-2 flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          <Map size={10} /> View route on map
        </button>
      )}
    </div>
  );
}

export default function ReroutingPanel({ reroutingData, onClose, showMapLink = false, vesselMmsi }) {
  const navigate = useNavigate();
  if (!reroutingData) return null;

  const { should_reroute, reason, destination, alternatives, vessel_name } = reroutingData;
  const destColor = CONGESTION_COLORS[destination?.congestion_level] || '#64748b';
  const allAlts = alternatives?.map(a => a.port).join(',') || '';

  return (
    <div className="space-y-3">
      {onClose && (
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Rerouting Analysis</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Recommendation banner */}
      <div className={`rounded-lg p-3 border ${
        should_reroute ? 'bg-red-900/30 border-red-500/40' : 'bg-green-900/20 border-green-500/30'
      }`}>
        <p className={`text-sm font-bold ${should_reroute ? 'text-red-400' : 'text-green-400'}`}>
          {should_reroute ? 'Rerouting Recommended' : 'Continue to Destination'}
        </p>
        <p className="text-xs text-slate-400 mt-1">{reason}</p>
      </div>

      {/* Destination */}
      {destination?.port && (
        <div className="bg-slate-700/50 rounded-lg p-2.5 text-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Navigation size={11} className="text-slate-400" />
              <span className="text-slate-300 font-medium">{destination.port}</span>
            </div>
            <span className="font-bold" style={{ color: destColor }}>
              {destination.congestion_level} ({destination.congestion_score})
            </span>
          </div>
          {destination.weather_risk && destination.weather_risk !== 'LOW' && (
            <p className="text-yellow-400 mt-1">Weather: {destination.weather_risk} risk</p>
          )}
        </div>
      )}

      {/* View on Map - full route */}
      {showMapLink && vesselMmsi && should_reroute && alternatives?.length > 0 && (
        <button
          onClick={() => navigate(`/vessels?focus=${vesselMmsi}&dest=${encodeURIComponent(destination?.port || '')}&alts=${encodeURIComponent(allAlts)}`)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600/80 hover:bg-blue-600 text-white text-xs rounded-lg font-medium transition-colors"
        >
          <Map size={12} /> View Vessel & Alternatives on Map
        </button>
      )}

      {/* Alternatives */}
      {alternatives && alternatives.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Alternative Ports</p>
          {alternatives.slice(0, 4).map((alt, i) => (
            <AltRow
              key={alt.port}
              alt={alt}
              index={i}
              showMapLink={showMapLink}
              vesselMmsi={vesselMmsi}
              destPort={destination?.port}
            />
          ))}
        </div>
      )}

      {alternatives?.length === 0 && (
        <p className="text-sm text-slate-500 text-center py-2">No alternative ports available</p>
      )}

      {/* Navigate to port intelligence */}
      {destination?.port && (
        <button
          onClick={() => navigate(`/ports?port=${encodeURIComponent(destination.port)}`)}
          className="w-full flex items-center justify-center gap-2 text-xs text-slate-400 hover:text-slate-300 py-1.5 transition-colors"
        >
          <BarChart3 size={10} /> View {destination.port} Intelligence
        </button>
      )}
    </div>
  );
}
