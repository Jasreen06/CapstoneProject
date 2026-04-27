import React, { useState, useEffect, useRef } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Legend,
} from "recharts";
import { ChevronDown, BarChart2 } from "lucide-react";
import { postComparison } from "../../hooks/useApi";

const AXIS_LABELS = {
  congestion_score: "Congestion",
  volatility: "Volatility",
  trend: "Trend",
  weather_risk: "Weather",
  chokepoint_risk: "Chokepoint",
  inbound_vessels: "Inbound",
};

const PORT_COLORS = ["#00C9A7", "#3B82F6", "#F59E0B"];

function PortMultiSelect({ label, selected, options, onChange, max, T }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggle = (port) => {
    if (selected.includes(port)) {
      onChange(selected.filter(p => p !== port));
    } else if (selected.length < max) {
      onChange([...selected, port]);
    }
  };

  const summary = selected.length === 0
    ? label
    : selected.join(", ");

  return (
    <div ref={ref} style={{ position: "relative", flex: 1 }}>
      <button onClick={() => setOpen(!open)} style={{
        width: "100%", textAlign: "left",
        background: selected.length > 0 ? T.tealSubtle : T.navy3,
        border: `1px solid ${selected.length > 0 ? T.teal : T.border}`,
        borderRadius: 6, color: selected.length > 0 ? T.teal : T.inkMid,
        cursor: "pointer", padding: "6px 10px",
        fontSize: 11, fontFamily: T.sans,
        display: "flex", alignItems: "center", gap: 4,
        overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis",
      }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>
          {summary}
        </span>
        <ChevronDown size={10} style={{ flexShrink: 0 }} />
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 2000,
          background: T.navy2, border: `1px solid ${T.border}`, borderRadius: 6,
          width: "100%", maxHeight: 200, overflow: "auto",
        }}>
          {options.map(port => {
            const checked = selected.includes(port);
            const disabled = !checked && selected.length >= max;
            return (
              <div key={port} onClick={() => !disabled && toggle(port)} style={{
                padding: "5px 10px", cursor: disabled ? "default" : "pointer",
                fontSize: 11, color: disabled ? T.inkDim : checked ? T.teal : T.ink,
                background: checked ? T.tealFaint : "transparent",
                opacity: disabled ? 0.4 : 1,
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <div style={{
                  width: 10, height: 10, borderRadius: 2,
                  border: `1.5px solid ${checked ? T.teal : T.border}`,
                  background: checked ? T.teal : "transparent",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  {checked && <span style={{ color: T.navy, fontSize: 8, fontWeight: 700 }}>&#10003;</span>}
                </div>
                {port}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function PortComparison({ T, ports: portList }) {
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const compare = async () => {
    if (selected.length < 2) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await postComparison(selected);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Drop weather axis if all ports report 0
  const visibleAxes = result
    ? Object.keys(AXIS_LABELS).filter(key =>
        key !== "weather_risk" || result.ports.some(p => (p[key] ?? 0) !== 0)
      )
    : Object.keys(AXIS_LABELS);

  // Transform for radar chart: one entry per visible axis
  const radarData = result ? visibleAxes.map(key => {
    const entry = { axis: AXIS_LABELS[key] };
    result.ports.forEach(p => {
      entry[p.portname] = p[key] ?? 0;
    });
    return entry;
  }) : [];

  return (
    <div style={{ width: "100%" }}>
      <div style={{
        fontSize: 10, color: T.inkDim, textTransform: "uppercase",
        letterSpacing: "0.06em", marginBottom: 8, fontWeight: 700,
        display: "flex", alignItems: "center", gap: 5,
      }}>
        <BarChart2 size={11} /> Compare Ports
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 10, alignItems: "center" }}>
        <PortMultiSelect
          label="Select 2-3 ports"
          selected={selected}
          options={portList}
          onChange={setSelected}
          max={3}
          T={T}
        />
        <button
          onClick={compare}
          disabled={selected.length < 2 || loading}
          style={{
            padding: "6px 14px", borderRadius: 6,
            background: selected.length >= 2 && !loading ? T.teal : T.navy3,
            border: `1px solid ${selected.length >= 2 && !loading ? T.teal : T.border}`,
            color: selected.length >= 2 && !loading ? T.navy : T.inkDim,
            fontSize: 11, fontWeight: 700, cursor: selected.length < 2 || loading ? "not-allowed" : "pointer",
            fontFamily: T.sans, flexShrink: 0,
          }}
        >
          {loading ? "..." : "Compare"}
        </button>
      </div>

      {error && (
        <div style={{
          padding: "10px 14px", borderRadius: 8,
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
          color: "#EF4444", fontSize: 12,
        }}>
          {error}
        </div>
      )}

      {result && !loading && (
        <div style={{
          borderRadius: 10, background: T.navy3,
          border: `1px solid ${T.border}`, padding: "14px",
        }}>
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
              <PolarGrid stroke={T.border} />
              <PolarAngleAxis
                dataKey="axis"
                tick={{ fill: T.inkMid, fontSize: 10, fontFamily: "'Syne', sans-serif" }}
              />
              <PolarRadiusAxis
                angle={90}
                domain={[0, 100]}
                tick={{ fill: T.inkDim, fontSize: 9 }}
                axisLine={false}
              />
              {result.ports.map((p, i) => (
                <Radar
                  key={p.portname}
                  name={p.portname}
                  dataKey={p.portname}
                  stroke={PORT_COLORS[i]}
                  fill={PORT_COLORS[i]}
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              ))}
              <Legend
                wrapperStyle={{ fontSize: 11, fontFamily: "'Syne', sans-serif" }}
              />
            </RadarChart>
          </ResponsiveContainer>

          {result.commentary && (
            <div style={{
              marginTop: 10, padding: "10px 12px",
              borderRadius: 8, background: T.tealBg,
              border: `1px solid ${T.tealSubtle}`,
              fontSize: 12, color: T.ink, lineHeight: 1.6,
            }}>
              {result.commentary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
