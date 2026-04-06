import { NavLink, Outlet } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { Anchor, Map, BarChart3, Globe, Route, MessageSquare } from 'lucide-react';

const tabs = [
  { to: '/vessels', label: 'Live Vessels', icon: Map },
  { to: '/ports', label: 'Port Intelligence', icon: BarChart3 },
  { to: '/chokepoints', label: 'Chokepoints', icon: Globe },
  { to: '/rerouting', label: 'Rerouting', icon: Route },
  { to: '/advisor', label: 'AI Advisor', icon: MessageSquare },
];

function UtcClock() {
  const [time, setTime] = useState('');

  useEffect(() => {
    const update = () => {
      setTime(new Date().toUTCString().split(' ').slice(4, 5)[0] + ' UTC');
    };
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, []);

  return <span className="text-slate-400 text-sm font-mono tabular-nums">{time}</span>;
}

export default function Layout() {
  return (
    <div className="min-h-screen bg-slate-900 flex flex-col">
      {/* Navbar */}
      <nav className="bg-gradient-to-r from-slate-800 via-slate-800 to-slate-800/95 border-b border-slate-700/80 sticky top-0 z-50 backdrop-blur-sm">
        <div className="max-w-full px-4 h-14 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <Anchor className="text-blue-400" size={22} />
            <span className="text-white font-bold text-lg tracking-tight">DockWise AI</span>
            <span className="text-xs text-slate-500 font-medium">v2</span>
            <div className="flex items-center gap-1.5 ml-3">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-400" />
              </span>
              <span className="text-green-400 text-xs font-semibold tracking-wide">LIVE</span>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-1">
            {tabs.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                      : 'text-slate-400 hover:text-white hover:bg-slate-700/70'
                  }`
                }
              >
                <Icon size={15} />
                <span className="hidden md:block">{label}</span>
              </NavLink>
            ))}
          </div>

          <UtcClock />
        </div>
      </nav>

      {/* Page content */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
