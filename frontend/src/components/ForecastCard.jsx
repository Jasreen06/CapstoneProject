import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { fetchJSON } from '../api/client.js';
import { CONGESTION_COLORS } from '../utils/constants.js';

const MODELS = ['Prophet', 'XGBoost', 'ARIMA'];

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const color = CONGESTION_COLORS[d.congestion_level] || '#64748b';
  return (
    <div className="bg-slate-800 border border-slate-600 rounded p-2 text-xs shadow">
      <p className="text-slate-400 mb-1">{label}</p>
      <p className="text-white">Score: <span style={{ color }}>{d.congestion_score}</span></p>
      <p style={{ color }} className="font-medium">{d.congestion_level}</p>
      <p className="text-slate-400">Calls: {Math.round(d.predicted_portcalls)}</p>
    </div>
  );
}

export default function ForecastCard({ portName }) {
  const [model, setModel] = useState('Prophet');
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(null);

  const load = (m) => {
    if (loaded === `${portName}:${m}`) return;
    setLoading(true);
    setError(null);
    fetchJSON(`/api/ports/${encodeURIComponent(portName)}/forecast?model=${m}&horizon=7`)
      .then(d => { setForecast(d.forecast || []); setLoaded(`${portName}:${m}`); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  const handleModelChange = (m) => {
    setModel(m);
    load(m);
  };

  if (!portName) return null;
  if (!loaded && !loading) load(model);

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">7-Day Congestion Forecast</h3>
        <div className="flex gap-1">
          {MODELS.map(m => (
            <button
              key={m}
              onClick={() => handleModelChange(m)}
              className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${
                model === m ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="h-32 flex items-center justify-center text-slate-400 text-sm">Loading forecast...</div>}
      {error && <div className="h-32 flex items-center justify-center text-red-400 text-sm">{error}</div>}
      {forecast && !loading && (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={forecast} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={d => d.slice(5)} />
            <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={33} stroke="#22c55e" strokeDasharray="3 3" strokeOpacity={0.5} />
            <ReferenceLine y={66} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.5} />
            <Line
              type="monotone"
              dataKey="congestion_score"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: '#3b82f6', r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
