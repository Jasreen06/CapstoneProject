import { useState } from 'react';
import { useTopPorts } from '../hooks/usePortData.js';
import { CONGESTION_COLORS } from '../utils/constants.js';
import { Search } from 'lucide-react';

export default function PortSelector({ selectedPort, onSelectPort }) {
  const { ports, loading } = useTopPorts(50);
  const [search, setSearch] = useState('');

  const filtered = ports.filter(p =>
    p.port.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-slate-700">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search ports..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded pl-8 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Port list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-slate-400 text-sm text-center">Loading ports...</div>
        ) : (
          filtered.map((p) => {
            const color = CONGESTION_COLORS[p.congestion_level] || '#64748b';
            const isSelected = selectedPort === p.port;
            return (
              <button
                key={p.port}
                onClick={() => onSelectPort(p.port)}
                className={`w-full flex items-center justify-between px-3 py-2.5 text-left border-b border-slate-700/50 hover:bg-slate-700/50 transition-colors ${
                  isSelected ? 'bg-slate-700 border-l-2 border-l-blue-500' : ''
                }`}
              >
                <div className="min-w-0">
                  <p className="text-sm text-slate-200 truncate">{p.port}</p>
                  <p className="text-xs text-slate-500">{p.portcalls} calls</p>
                </div>
                <div className="flex flex-col items-end ml-2 shrink-0">
                  <span
                    className="text-xs font-bold px-1.5 py-0.5 rounded"
                    style={{ background: `${color}25`, color }}
                  >
                    {Math.round(p.congestion_score)}
                  </span>
                  <span className="text-xs mt-0.5" style={{ color }}>
                    {p.congestion_level}
                  </span>
                </div>
              </button>
            );
          })
        )}
        {!loading && filtered.length === 0 && (
          <div className="p-4 text-slate-500 text-sm text-center">No ports found</div>
        )}
      </div>
    </div>
  );
}
