import React from "react";
import { TrendingUp, TrendingDown, Minus, MapPin, CheckCircle, AlertTriangle, Eye } from "lucide-react";
import { useNearbyPorts } from "../../hooks/useApi";

const TIER_COLORS = {
  HIGH:   { color: "#EF4444", bg: "rgba(239,68,68,0.12)",   label: "HIGH" },
  MEDIUM: { color: "#F59E0B", bg: "rgba(245,158,11,0.12)",  label: "MEDIUM" },
  LOW:    { color: "#10B981", bg: "rgba(16,185,129,0.12)",  label: "LOW" },
};

const REC_CFG = {
  good_alternative: { color: "#10B981", bg: "rgba(16,185,129,0.12)", label: "Good alternative", Icon: CheckCircle },
  watch:            { color: "#F59E0B", bg: "rgba(245,158,11,0.12)", label: "Watch",            Icon: Eye },
  avoid:            { color: "#EF4444", bg: "rgba(239,68,68,0.12)",  label: "Avoid",            Icon: AlertTriangle },
};

const TREND_ICON = { rising: TrendingUp, falling: TrendingDown, stable: Minus };
const TREND_COLOR = { rising: "#EF4444", falling: "#10B981", stable: "#94A3B8" };

export default function NearbyPortOutlook({ T, port, onSelectPort }) {
  const { data, loading, error } = useNearbyPorts(port, 300, 6);

  if (!port) return null;

  if (loading) {
    return (
      <div style={{ width: "100%" }}>
        <div style={{
          fontSize: 10, color: T.inkDim, textTransform: "uppercase",
          letterSpacing: "0.06em", marginBottom: 8, fontWeight: 700,
        }}>
          Nearby Port Outlook
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{
              flex: "1 1 200px", height: 86, borderRadius: 10,
              background: T.navy3, border: `1px solid ${T.border}`,
              animation: "pulse-dot 1.5s ease-in-out infinite",
              opacity: 0.4,
            }} />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data || !data.ports || data.ports.length === 0) return null;

  return (
    <div style={{ width: "100%" }}>
      <div style={{
        display: "flex", alignItems: "baseline", justifyContent: "space-between",
        marginBottom: 8, gap: 12,
      }}>
        <div style={{
          fontSize: 10, color: T.inkDim, textTransform: "uppercase",
          letterSpacing: "0.06em", fontWeight: 700,
        }}>
          Nearby Port Outlook
        </div>
        <div style={{ fontSize: 10, color: T.inkDim, fontStyle: "italic" }}>
          Ports within {Math.round(data.radius_nm)} nm of {port}, ranked by alternative-route suitability.
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {data.ports.map(p => {
          const tier = TIER_COLORS[p.congestion_level] || TIER_COLORS.MEDIUM;
          const rec = REC_CFG[p.recommendation] || REC_CFG.watch;
          const TrendIcon = TREND_ICON[p.trend] || Minus;
          const trendColor = TREND_COLOR[p.trend] || T.inkDim;
          const RecIcon = rec.Icon;

          return (
            <button
              key={p.portname}
              onClick={() => onSelectPort && onSelectPort(p.portname)}
              style={{
                flex: "1 1 220px", minWidth: 0,
                padding: "10px 12px", borderRadius: 10,
                background: T.navy3, border: `1px solid ${T.border}`,
                display: "flex", flexDirection: "column", gap: 6,
                cursor: "pointer", textAlign: "left",
                fontFamily: T.sans, transition: "all 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = T.teal; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                <MapPin size={12} color={T.teal} style={{ flexShrink: 0 }} />
                <div style={{
                  fontSize: 12, fontWeight: 700, color: T.ink,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
                }}>
                  {p.portname}
                </div>
                <div style={{
                  fontSize: 10, fontFamily: T.mono, color: T.inkDim, flexShrink: 0,
                }}>
                  {Math.round(p.distance_nm)} nm
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 3,
                  padding: "2px 7px", borderRadius: 10,
                  background: tier.bg, color: tier.color,
                  fontSize: 9, fontWeight: 700, letterSpacing: "0.04em",
                }}>
                  {tier.label}
                </span>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 2,
                  fontSize: 10, color: trendColor, fontFamily: T.mono,
                }}>
                  <TrendIcon size={10} />
                  {p.trend}
                </span>
                <span style={{
                  marginLeft: "auto",
                  display: "inline-flex", alignItems: "center", gap: 3,
                  padding: "2px 7px", borderRadius: 10,
                  background: rec.bg, color: rec.color,
                  fontSize: 9, fontWeight: 700,
                }}>
                  <RecIcon size={9} />
                  {rec.label}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
