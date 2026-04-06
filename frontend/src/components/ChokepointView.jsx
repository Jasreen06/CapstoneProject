import { useState, useEffect } from 'react';
import { fetchJSON } from '../api/client.js';
import { CONGESTION_COLORS } from '../utils/constants.js';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Globe, ChevronDown, ChevronUp } from 'lucide-react';

function ChokepointCard({ chokepoint, onSelect, isSelected }) {
  const color = CONGESTION_COLORS[chokepoint.disruption_level] || '#64748b';
  return (
    <button
      onClick={() => onSelect(isSelected ? null : chokepoint)}
      className={`w-full text-left bg-slate-800 border rounded-lg p-3 hover:bg-slate-700/50 transition-colors ${
        isSelected ? 'border-blue-500' : 'border-slate-700'
      }`}
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white leading-tight">{chokepoint.name}</h3>
          <p className="text-xs text-slate-400 mt-0.5">Transits: {chokepoint.transits_today} (avg: {chokepoint.avg_90day})</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span
            className="text-sm font-bold px-2 py-0.5 rounded"
            style={{ background: `${color}25`, color }}
          >
            {Math.round(chokepoint.disruption_score)}
          </span>
          <span className="text-xs font-medium" style={{ color }}>
            {chokepoint.disruption_level}
          </span>
        </div>
      </div>
      {isSelected && (
        <ChevronUp size={14} className="text-slate-400 mt-1" />
      )}
    </button>
  );
}

function ChokepointDetail({ name }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchJSON(`/api/chokepoints/${encodeURIComponent(name)}`)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [name]);

  if (loading) return <div className="p-4 text-slate-400 text-sm text-center">Loading history...</div>;
  if (!detail?.history_90d?.length) return null;

  return (
    <div className="mt-3 p-3 bg-slate-900 rounded border border-slate-700">
      <h4 className="text-xs font-semibold text-slate-400 mb-2">90-Day Transit History</h4>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={detail.history_90d} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
          <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} tickFormatter={d => d.slice(5)} interval={14} />
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }}
            labelStyle={{ color: '#94a3b8' }}
            itemStyle={{ color: '#3b82f6' }}
          />
          <Line type="monotone" dataKey="transits" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function ChokepointView() {
  const [chokepoints, setChokepoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetchJSON('/api/chokepoints/')
      .then(d => setChokepoints(d.chokepoints || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-4" style={{ height: 'calc(100vh - 56px)', overflowY: 'auto' }}>
      <div className="flex items-center gap-2 mb-4">
        <Globe size={18} className="text-blue-400" />
        <h2 className="text-lg font-bold text-white">Global Chokepoint Monitor</h2>
        <span className="text-xs text-slate-400 ml-2">{chokepoints.length} chokepoints tracked</span>
      </div>

      {loading ? (
        <div className="text-slate-400 text-sm text-center py-8">Loading chokepoint data...</div>
      ) : chokepoints.length === 0 ? (
        <div className="text-slate-400 text-sm text-center py-8">
          No chokepoint data available. Run the seed script or wait for PortWatch data to load.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {chokepoints.map(cp => (
            <div key={cp.name}>
              <ChokepointCard
                chokepoint={cp}
                onSelect={setSelected}
                isSelected={selected?.name === cp.name}
              />
              {selected?.name === cp.name && (
                <ChokepointDetail name={cp.name} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
