import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { fetchJSON } from '../api/client.js';
import { CONGESTION_COLORS, PORT_ALTERNATIVES } from '../utils/constants.js';

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const color = CONGESTION_COLORS[d.level] || '#64748b';
  return (
    <div className="bg-slate-800 border border-slate-600 rounded p-2 text-xs shadow-lg">
      <p className="text-white font-medium">{d.name}</p>
      <p style={{ color }}>Congestion: {d.level} ({d.score})</p>
      <p className="text-slate-400">Port Calls: {d.portcalls ?? '—'}</p>
      {d.isCurrent && <p className="text-blue-400 font-medium mt-1">Selected Port</p>}
    </div>
  );
}

export default function PortComparisonChart({ portName, overview }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!portName || !overview) return;
    const alts = PORT_ALTERNATIVES[portName] || [];
    if (alts.length === 0) {
      setData([{
        name: portName.split('-')[0],
        score: overview.congestion_score || 0,
        level: overview.congestion_level || 'UNKNOWN',
        portcalls: overview.portcalls,
        isCurrent: true,
      }]);
      return;
    }

    setLoading(true);
    const current = {
      name: portName.split('-')[0],
      score: overview.congestion_score || 0,
      level: overview.congestion_level || 'UNKNOWN',
      portcalls: overview.portcalls,
      isCurrent: true,
    };

    Promise.all(
      alts.slice(0, 4).map(alt =>
        fetchJSON(`/api/ports/${encodeURIComponent(alt)}/overview`)
          .then(d => ({
            name: alt.split('-')[0],
            score: d.congestion_score || 0,
            level: d.congestion_level || 'UNKNOWN',
            portcalls: d.portcalls,
            isCurrent: false,
          }))
          .catch(() => null)
      )
    ).then(results => {
      const valid = results.filter(Boolean);
      setData([current, ...valid].sort((a, b) => b.score - a.score));
      setLoading(false);
    });
  }, [portName, overview]);

  if (data.length <= 1 && !loading) return null;

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Port Comparison — vs Alternatives</h3>
        {loading && <span className="text-xs text-slate-500">Loading...</span>}
      </div>
      {data.length > 0 && (
        <ResponsiveContainer width="100%" height={Math.max(120, data.length * 36)}>
          <BarChart data={data} layout="vertical" margin={{ top: 5, right: 30, left: 5, bottom: 5 }}>
            <XAxis type="number" domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              width={90}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine x={33} stroke="#22c55e" strokeDasharray="3 3" strokeOpacity={0.4} />
            <ReferenceLine x={66} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.4} />
            <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={20}>
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.isCurrent
                    ? (CONGESTION_COLORS[entry.level] || '#3b82f6')
                    : (CONGESTION_COLORS[entry.level] || '#64748b')}
                  fillOpacity={entry.isCurrent ? 1 : 0.7}
                  stroke={entry.isCurrent ? '#ffffff' : 'none'}
                  strokeWidth={entry.isCurrent ? 1 : 0}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500 justify-center">
        <div className="flex items-center gap-1">
          <div className="w-6 h-0.5 bg-green-500" style={{ borderTop: '1px dashed #22c55e' }} />
          LOW (&lt;33)
        </div>
        <div className="flex items-center gap-1">
          <div className="w-6 h-0.5 bg-red-500" style={{ borderTop: '1px dashed #ef4444' }} />
          HIGH (&gt;66)
        </div>
      </div>
    </div>
  );
}
