import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { CONGESTION_COLORS } from '../utils/constants.js';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const color = CONGESTION_COLORS[d.congestion_level] || '#64748b';
  return (
    <div className="bg-slate-800 border border-slate-600 rounded p-2 text-xs shadow-lg">
      <p className="text-slate-400 mb-1">{label}</p>
      <p className="text-white">Port Calls: <span className="font-bold">{d.portcalls}</span></p>
      <p style={{ color }} className="font-medium">Congestion: {d.congestion_level} ({Math.round(d.congestion_score)})</p>
    </div>
  );
}

export default function TrafficVolumeChart({ data }) {
  if (!data || data.length === 0) return null;

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <h3 className="text-sm font-semibold text-white mb-3">Daily Port Traffic</h3>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fill: '#64748b', fontSize: 9 }}
            tickFormatter={d => d.slice(5)}
          />
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="portcalls" radius={[3, 3, 0, 0]}>
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={CONGESTION_COLORS[entry.congestion_level] || '#3b82f6'}
                fillOpacity={0.8}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
