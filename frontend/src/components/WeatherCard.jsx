import { useWeather } from '../hooks/useWeather.js';
import { Wind, Eye, Thermometer, CloudRain, AlertTriangle, CheckCircle } from 'lucide-react';

const RISK_STYLES = {
  HIGH: { bg: 'bg-red-900/30 border-red-500/50', text: 'text-red-400', icon: AlertTriangle },
  MEDIUM: { bg: 'bg-yellow-900/30 border-yellow-500/50', text: 'text-yellow-400', icon: AlertTriangle },
  LOW: { bg: 'bg-green-900/30 border-green-500/50', text: 'text-green-400', icon: CheckCircle },
};

export default function WeatherCard({ portName }) {
  const { weather, loading, error } = useWeather(portName);

  if (!portName) return null;

  if (loading && !weather) {
    return (
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 animate-pulse h-36" />
    );
  }

  if (error || !weather?.current) {
    return (
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <p className="text-slate-400 text-sm">Weather data unavailable</p>
        {error && <p className="text-red-400 text-xs mt-1">{error}</p>}
      </div>
    );
  }

  const { current, risk_level, risk_reasons } = weather;
  const styles = RISK_STYLES[risk_level] || RISK_STYLES.LOW;
  const RiskIcon = styles.icon;

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Weather Conditions</h3>
        <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${styles.bg} ${styles.text}`}>
          <RiskIcon size={11} />
          {risk_level} RISK
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="flex items-center gap-2 text-slate-300">
          <Thermometer size={14} className="text-orange-400 shrink-0" />
          <span>{current.temp_c}°C</span>
        </div>
        <div className="flex items-center gap-2 text-slate-300">
          <Wind size={14} className="text-blue-400 shrink-0" />
          <span>{current.wind_speed_ms} m/s</span>
        </div>
        <div className="flex items-center gap-2 text-slate-300">
          <Eye size={14} className="text-slate-400 shrink-0" />
          <span>{(current.visibility_m / 1000).toFixed(1)} km</span>
        </div>
        <div className="flex items-center gap-2 text-slate-300">
          <CloudRain size={14} className="text-sky-400 shrink-0" />
          <span>{current.weather_description}</span>
        </div>
      </div>

      {risk_reasons && risk_reasons.length > 0 && (
        <div className={`rounded p-2 text-xs border ${styles.bg} ${styles.text} space-y-1`}>
          {risk_reasons.map((r, i) => (
            <p key={i}>{r}</p>
          ))}
        </div>
      )}

      {/* 5-day forecast strip */}
      {weather.forecast && weather.forecast.length > 0 && (
        <div className="flex gap-2 pt-1 border-t border-slate-700">
          {weather.forecast.slice(0, 5).map((day, i) => {
            const riskStyles = RISK_STYLES[day.risk_level] || RISK_STYLES.LOW;
            return (
              <div key={i} className="flex-1 text-center">
                <p className="text-xs text-slate-500">{day.date.slice(5)}</p>
                <p className={`text-xs font-medium ${riskStyles.text}`}>{day.risk_level}</p>
                <p className="text-xs text-slate-400">{day.wind_speed_ms}m/s</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
