import { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { fetchJSON } from '../api/client.js';
import { VESSEL_TYPE_COLORS } from '../utils/constants.js';

const TYPE_COLORS = {
  Cargo: '#3b82f6',
  Tanker: '#f59e0b',
  Passenger: '#8b5cf6',
  Fishing: '#22c55e',
  Tug: '#a855f7',
  'High Speed Craft': '#06b6d4',
  'Special Craft': '#ec4899',
  Other: '#94a3b8',
  Unknown: '#64748b',
};

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="bg-slate-800 border border-slate-600 rounded p-2 text-xs shadow-lg">
      <p className="text-white font-medium">{d.name}</p>
      <p className="text-slate-400">{d.value} vessels</p>
    </div>
  );
}

export default function VesselDistributionChart({ portName, vesselList }) {
  const [data, setData] = useState([]);

  useEffect(() => {
    if (!portName || !vesselList || vesselList.length === 0) {
      setData([]);
      return;
    }
    // Filter vessels heading to this port
    const portLower = portName.toLowerCase();
    const matching = vesselList.filter(v => {
      if (!v.destination) return false;
      const destLower = v.destination.toLowerCase();
      return destLower.includes(portLower.split('-')[0]) || portLower.includes(destLower.split(/[,\s-]/)[0]);
    });

    // Group by type
    const byType = {};
    for (const v of matching) {
      const type = (v.vessel_type_label || 'Unknown').replace(/ \(Haz.*\)/, '');
      byType[type] = (byType[type] || 0) + 1;
    }

    const chartData = Object.entries(byType)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);

    setData(chartData);
  }, [portName, vesselList]);

  if (data.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-3">Inbound Vessel Types</h3>
        <p className="text-slate-500 text-xs text-center py-6">No inbound vessels detected for this port</p>
      </div>
    );
  }

  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Inbound Vessel Types</h3>
        <span className="text-xs text-slate-400">{total} vessels</span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={35}
            outerRadius={60}
            dataKey="value"
            paddingAngle={2}
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={TYPE_COLORS[entry.name] || '#64748b'} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      {/* Legend below chart */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 justify-center">
        {data.map((d, i) => (
          <div key={i} className="flex items-center gap-1 text-xs">
            <div className="w-2 h-2 rounded-full" style={{ background: TYPE_COLORS[d.name] || '#64748b' }} />
            <span className="text-slate-400">{d.name} ({d.value})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
