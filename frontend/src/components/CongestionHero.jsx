import { TrendingUp, TrendingDown, Minus, Ship, Calendar } from 'lucide-react';
import { CONGESTION_COLORS } from '../utils/constants.js';

function ScoreRing({ score, level }) {
  const color = CONGESTION_COLORS[level] || '#64748b';
  const pct = Math.round(score || 0);
  const isHigh = level === 'HIGH';

  return (
    <div className="relative flex items-center justify-center" style={{ width: 110, height: 110 }}>
      <svg width={110} height={110} viewBox="0 0 110 110" className={isHigh ? 'animate-glow-pulse' : ''} style={isHigh ? { color } : {}}>
        {/* Background ring */}
        <circle cx="55" cy="55" r="46" fill="none" stroke="#1e293b" strokeWidth="8" />
        {/* Score ring */}
        <circle
          cx="55" cy="55" r="46"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={`${(pct / 100) * 289} 289`}
          strokeLinecap="round"
          transform="rotate(-90 55 55)"
          style={{ transition: 'stroke-dasharray 0.8s ease-out' }}
        />
        {/* Glow effect for HIGH */}
        {isHigh && (
          <circle
            cx="55" cy="55" r="46"
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeDasharray={`${(pct / 100) * 289} 289`}
            strokeLinecap="round"
            transform="rotate(-90 55 55)"
            opacity="0.3"
            filter="blur(4px)"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-white">{pct}</span>
        <span className="text-xs text-slate-400">/100</span>
      </div>
    </div>
  );
}

export default function CongestionHero({ overview }) {
  if (!overview) {
    return (
      <div className="bg-slate-800 rounded-lg p-5 border border-slate-700 animate-pulse h-36" />
    );
  }

  const { congestion_score, congestion_level, portcalls, trend, pct_vs_normal, last_date } = overview;
  const color = CONGESTION_COLORS[congestion_level] || '#64748b';

  const TrendIcon = trend === 'increasing' ? TrendingUp : trend === 'decreasing' ? TrendingDown : Minus;
  const trendColor = trend === 'increasing' ? 'text-red-400' : trend === 'decreasing' ? 'text-green-400' : 'text-slate-400';

  return (
    <div className={`bg-slate-800 rounded-lg p-5 border transition-colors ${
      congestion_level === 'HIGH' ? 'border-red-500/30' : 'border-slate-700'
    }`}>
      <div className="flex items-center gap-6">
        <ScoreRing score={congestion_score} level={congestion_level} />
        <div className="flex-1 space-y-3">
          <div>
            <span
              className="inline-block px-2.5 py-1 rounded-md text-xs font-bold tracking-wide"
              style={{ backgroundColor: `${color}20`, color, border: `1px solid ${color}40` }}
            >
              {congestion_level} CONGESTION
            </span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-slate-400 text-xs mb-0.5 flex items-center gap-1">
                <Ship size={10} /> Port Calls
              </p>
              <p className="text-white font-semibold text-lg">{portcalls ?? '—'}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-0.5">vs 90-Day Avg</p>
              <p className={`font-semibold text-lg ${(pct_vs_normal || 0) > 0 ? 'text-red-400' : 'text-green-400'}`}>
                {pct_vs_normal > 0 ? '+' : ''}{pct_vs_normal ?? 0}%
              </p>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-0.5">Trend</p>
              <div className={`flex items-center gap-1 font-semibold text-lg ${trendColor}`}>
                <TrendIcon size={16} />
                <span className="capitalize">{trend || 'stable'}</span>
              </div>
            </div>
          </div>
          <p className="text-xs text-slate-500 flex items-center gap-1">
            <Calendar size={10} /> Data as of {last_date}
          </p>
        </div>
      </div>
    </div>
  );
}
