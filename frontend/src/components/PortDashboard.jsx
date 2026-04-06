import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import PortSelector from './PortSelector.jsx';
import CongestionHero from './CongestionHero.jsx';
import ForecastCard from './ForecastCard.jsx';
import WeatherCard from './WeatherCard.jsx';
import TrafficVolumeChart from './TrafficVolumeChart.jsx';
import VesselDistributionChart from './VesselDistributionChart.jsx';
import PortComparisonChart from './PortComparisonChart.jsx';
import { usePortData } from '../hooks/usePortData.js';
import { useVessels } from '../hooks/useVessels.js';
import { BarChart3 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

function PortTrend({ data }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <h3 className="text-sm font-semibold text-white mb-3">7-Day Congestion Trend</h3>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} tickFormatter={d => d.slice(5)} />
          <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 9 }} />
          <Tooltip
            formatter={(v) => [`${v.toFixed(0)}`, 'Score']}
            labelFormatter={l => l}
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }}
            labelStyle={{ color: '#94a3b8' }}
            itemStyle={{ color: '#3b82f6' }}
          />
          <Line type="monotone" dataKey="congestion_score" stroke="#3b82f6" strokeWidth={2} dot={{ fill: '#3b82f6', r: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function PortDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const portFromUrl = searchParams.get('port');
  const [selectedPort, setSelectedPort] = useState(portFromUrl || 'Los Angeles-Long Beach');

  // Update selected port when URL changes
  useEffect(() => {
    if (portFromUrl && portFromUrl !== selectedPort) {
      setSelectedPort(portFromUrl);
    }
  }, [portFromUrl]);

  const { overview, forecast, loading, error } = usePortData(selectedPort);
  const { vesselList } = useVessels();

  const handleSelectPort = (port) => {
    setSelectedPort(port);
    // Update URL param
    const newParams = new URLSearchParams(searchParams);
    newParams.set('port', port);
    setSearchParams(newParams, { replace: true });
  };

  return (
    <div className="flex h-full" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Sidebar */}
      <div className="w-64 bg-slate-800 border-r border-slate-700 flex flex-col shrink-0">
        <div className="p-3 border-b border-slate-700 flex items-center gap-2">
          <BarChart3 size={15} className="text-blue-400" />
          <span className="text-sm font-semibold text-white">Ports</span>
        </div>
        <div className="flex-1 overflow-hidden">
          <PortSelector selectedPort={selectedPort} onSelectPort={handleSelectPort} />
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Port name */}
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">{selectedPort}</h2>
          {loading && <span className="text-xs text-slate-400 animate-pulse">Refreshing...</span>}
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Row 1: Congestion Hero */}
        <CongestionHero overview={overview} />

        {/* Row 2: Trend + Weather */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PortTrend data={overview?.recent_7_days} />
          <WeatherCard portName={selectedPort} />
        </div>

        {/* Row 3: Traffic Volume + Vessel Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrafficVolumeChart data={overview?.recent_7_days} />
          <VesselDistributionChart portName={selectedPort} vesselList={vesselList} />
        </div>

        {/* Row 4: Forecast */}
        <ForecastCard portName={selectedPort} />

        {/* Row 5: Port Comparison */}
        <PortComparisonChart portName={selectedPort} overview={overview} />
      </div>
    </div>
  );
}
