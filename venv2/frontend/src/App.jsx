import React, { useState, useEffect, useRef } from "react";
import {
  Area, BarChart, Bar, ComposedChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { format, parseISO } from "date-fns";
import {
  Anchor, TrendingUp, TrendingDown, Minus,
  ChevronDown, AlertTriangle, CheckCircle, Clock, Ship,
  Calendar, Navigation, Zap, Info, MessageSquare, Send, RotateCcw,
  Sun, Moon,
} from "lucide-react";
import { usePortList, useOverview, useForecast, useTopPorts, useTopLoadedPorts, useModelComp, usePortChokepoints, useWeather, useRiskAssessment, postChat, postFollowups } from "./hooks/useApi";
import { useTheme } from "./hooks/useTheme";
import VesselMap from "./VesselMap";
import Briefing from "./components/advisor/Briefing";
import PortComparison from "./components/advisor/PortComparison";
import NearbyPortOutlook from "./components/advisor/NearbyPortOutlook";

/* ─────────────────────────────────────────────────────────
   DESIGN TOKENS
───────────────────────────────────────────────────────── */
const T = {
  navy:    "var(--bg-navy)",
  navy2:   "var(--bg-navy2)",
  navy3:   "var(--bg-navy3)",
  slate:   "var(--bg-slate)",
  slateL:  "var(--bg-slateL)",
  border:  "var(--border-color)",
  borderL: "var(--border-colorL)",
  borderSubtle: "var(--border-subtle)",
  borderMedium: "var(--border-medium)",
  teal:    "var(--accent-teal)",
  tealD:   "var(--accent-tealD)",
  tealBg:  "var(--teal-bg)",
  tealSubtle: "var(--teal-subtle)",
  tealFaint:  "var(--teal-faint)",
  tealBorder: "var(--teal-border)",
  amber:   "#F59E0B",
  amberBg: "var(--amber-bg)",
  red:     "#EF4444",
  redBg:   "var(--red-bg)",
  green:   "#10B981",
  greenBg: "var(--green-bg)",
  blue:    "#3B82F6",
  blueBg:  "var(--blue-bg)",
  ink:     "var(--text-ink)",
  inkMid:  "var(--text-inkMid)",
  inkDim:  "var(--text-inkDim)",
  navy2Overlay: "var(--navy2-overlay)",
  mono:    "'JetBrains Mono', monospace",
  sans:    "'Syne', sans-serif",
};

/* ─────────────────────────────────────────────────────────
   GLOBAL STYLES
───────────────────────────────────────────────────────── */
const GLOBAL_CSS = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; }
  body {
    background: ${T.navy};
    color: ${T.ink};
    font-family: ${T.sans};
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
  }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: ${T.borderL}; border-radius: 2px; }

  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes fade-up {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .fade-up { animation: fade-up 0.35s ease forwards; }
`;

/* ─────────────────────────────────────────────────────────
   UTILS
───────────────────────────────────────────────────────── */
const dayOf  = iso => { try { return format(parseISO(iso), "EEE"); } catch { return ""; } };
const dateOf = iso => { try { return format(parseISO(iso), "MMM d"); } catch { return iso || ""; } };

const RISK_CFG = {
  HIGH:   { color: T.red,   bg: T.redBg,   label: "High Congestion", icon: AlertTriangle },
  MEDIUM: { color: T.amber, bg: T.amberBg, label: "Moderate",        icon: Clock },
  LOW:    { color: T.green, bg: T.greenBg, label: "Normal Flow",     icon: CheckCircle },
};

const congestionColor = score =>
  score >= 67 ? T.red : score >= 33 ? T.amber : T.green;

/* ─────────────────────────────────────────────────────────
   SMALL COMPONENTS
───────────────────────────────────────────────────────── */
function Spinner() {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", padding:"3rem" }}>
      <div style={{
        width:28, height:28, borderRadius:"50%",
        border:`2px solid ${T.border}`, borderTopColor: T.teal,
        animation: "spin 0.7s linear infinite",
      }} />
    </div>
  );
}

function RiskPill({ level, unverified = false }) {
  const cfg = RISK_CFG[level] || RISK_CFG.LOW;
  const Icon = cfg.icon;
  // Phase 6A.2 — unverified variant: outlined-dashed, no fill, hue preserved.
  // Note: width-constrained header pill — caller suppresses the "· UNVERIFIED"
  // suffix. Wider callers (forecast cards) append the suffix themselves.
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"3px 10px", borderRadius:99,
      background: unverified ? "transparent" : cfg.bg,
      color: cfg.color,
      fontSize:11, fontWeight:700, letterSpacing:"0.04em",
      border: unverified
        ? `1px dashed ${cfg.color}88`
        : `1px solid ${cfg.color}33`,
      textTransform:"uppercase",
      opacity: unverified ? 0.85 : 1,
    }}>
      <Icon size={11} />
      {cfg.label}
    </span>
  );
}

function LiveDot() {
  return (
    <span style={{
      width:7, height:7, borderRadius:"50%",
      background: T.teal, display:"inline-block",
      animation: "pulse-dot 2s ease-in-out infinite",
    }} />
  );
}

function Card({ children, style = {} }) {
  return (
    <div style={{
      background: T.navy2,
      border: `1px solid ${T.border}`,
      borderRadius:12,
      ...style,
    }}>{children}</div>
  );
}

function Label({ children, style = {} }) {
  return (
    <div style={{
      fontSize:10, fontWeight:700, letterSpacing:"0.1em",
      color: T.inkDim, textTransform:"uppercase",
      ...style,
    }}>{children}</div>
  );
}

function ModelBadge({ model, recommended }) {
  const colors = { Prophet:"#3B82F6", ARIMA:"#F59E0B", XGBoost:"#10B981" };
  const c = colors[model] || T.teal;
  return (
    <span style={{
      fontSize:10, fontWeight:700, letterSpacing:"0.06em",
      padding:"2px 8px", borderRadius:5,
      background:`${c}18`, color:c, border:`1px solid ${c}33`,
      textTransform:"uppercase",
    }}>
      {model}{recommended === model ? " ★" : ""}
    </span>
  );
}

/* ─────────────────────────────────────────────────────────
   PORT SELECTOR DROPDOWN
───────────────────────────────────────────────────────── */
function PortSelector({ ports, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const filtered = ports.filter(p => p.toLowerCase().includes(q.toLowerCase()));

  return (
    <div style={{ position:"relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display:"flex", alignItems:"center", gap:8,
          background: T.slate, border:`1px solid ${T.borderL}`,
          borderRadius:8, padding:"0.45rem 0.9rem",
          color: T.ink, fontFamily: T.sans, fontWeight:600, fontSize:14,
          cursor:"pointer", whiteSpace:"nowrap",
        }}
      >
        <Ship size={14} color={T.teal} />
        {value || "Select port"}
        <ChevronDown size={13} color={T.inkMid} style={{ marginLeft:2 }} />
      </button>

      {open && (
        <div style={{
          position:"absolute", top:"calc(100% + 6px)", left:0, zIndex:100,
          background: T.slate, border:`1px solid ${T.borderL}`,
          borderRadius:10, width:240, overflow:"hidden",
          boxShadow:"0 8px 24px rgba(0,0,0,0.4)",
        }}>
          <div style={{ padding:"0.5rem" }}>
            <input
              autoFocus
              value={q} onChange={e => setQ(e.target.value)}
              placeholder="Search ports…"
              style={{
                width:"100%", padding:"0.4rem 0.6rem",
                background: T.navy3, border:`1px solid ${T.border}`,
                borderRadius:6, color: T.ink, fontFamily: T.sans, fontSize:13,
                outline:"none",
              }}
            />
          </div>
          <div style={{ maxHeight:220, overflowY:"auto" }}>
            {filtered.map(p => (
              <div
                key={p}
                onClick={() => { onChange(p); setOpen(false); setQ(""); }}
                style={{
                  padding:"0.5rem 0.85rem",
                  color: p === value ? T.teal : T.ink,
                  background: p === value ? T.tealBg : "transparent",
                  fontSize:13, cursor:"pointer", fontWeight: p === value ? 600 : 400,
                  transition:"background 0.1s",
                }}
                onMouseEnter={e => { if (p !== value) e.currentTarget.style.background = T.navy3; }}
                onMouseLeave={e => { if (p !== value) e.currentTarget.style.background = "transparent"; }}
              >
                {p}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   CONGESTION HERO  (gauge + current state)
───────────────────────────────────────────────────────── */
function CongestionHero({ kpi }) {
  const score = kpi?.congestion_score ?? 0;
  const level = kpi?.congestion_level || kpi?.traffic_level || "LOW";
  const cfg   = RISK_CFG[level] || RISK_CFG.LOW;
  const lag   = kpi?.data_lag_days ?? 0;

  // Phase 6A — staleness reconciliation
  const tierAdjusted    = kpi?.tier_adjusted === true;
  const portwatchTier   = kpi?.portwatch_tier;
  const adjustReason    = kpi?.tier_adjustment_reason;
  const liveUnavailable = kpi?.live_data_available === false;
  // Phase 6A.1 — spatial coverage classification
  const liveCoverage    = kpi?.live_coverage; // "covered" | "sparse" | "dark" | "unavailable" | null
  // Phase 6A.2 — visual unverified state when live coverage cannot validate
  // the displayed tier. We dash the gauge fill and ghost the score number.
  const isUnverified =
    liveCoverage === "dark" ||
    liveCoverage === "sparse" ||
    liveCoverage === "unavailable";

  // Semicircle gauge
  const R = 54, cx = 64, cy = 62;
  const pLen  = Math.PI * R;
  const fill  = (Math.min(100, Math.max(0, score)) / 100) * pLen;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:"0.5rem" }}>
      {tierAdjusted && (
        <div style={{
          display:"flex", alignItems:"flex-start", gap:"0.6rem",
          padding:"0.6rem 0.9rem",
          background: T.amberBg,
          border: `1px solid ${T.amber}55`,
          borderRadius: 8,
          fontSize: 12, color: T.ink, lineHeight: 1.4,
        }}>
          <AlertTriangle size={14} color={T.amber} style={{ flexShrink:0, marginTop:1 }} />
          <div>
            <div style={{ fontWeight:700, color: T.amber, marginBottom:2 }}>
              Tier adjusted using live AIS
            </div>
            <div style={{ color: T.inkMid }}>{adjustReason}</div>
            {portwatchTier && portwatchTier !== level && (
              <div style={{ fontSize:11, color: T.inkDim, marginTop:3 }}>
                PortWatch tier (historical): <strong style={{ color: T.inkMid }}>{portwatchTier}</strong>
              </div>
            )}
          </div>
        </div>
      )}
    <Card style={{ padding:"1.25rem 1.5rem", display:"flex", alignItems:"center", gap:"1.5rem" }}>
      {/* Gauge */}
      <div style={{ flexShrink:0, display:"flex", flexDirection:"column", alignItems:"center", gap:4 }}>
        <svg width={128} height={74} viewBox="0 0 128 74">
          {/* track segments: LOW zone */}
          <path d={`M ${cx-R},${cy} A ${R},${R} 0 0 1 ${cx+R},${cy}`}
            fill="none" stroke={T.border} strokeWidth={10} strokeLinecap="butt" />
          {/* colored fill — dashed + ghosted when live AIS can't verify the tier */}
          <path d={`M ${cx-R},${cy} A ${R},${R} 0 0 1 ${cx+R},${cy}`}
            fill="none" stroke={cfg.color} strokeWidth={10} strokeLinecap="butt"
            strokeDasharray={isUnverified ? "5 4" : `${fill} ${pLen}`}
            opacity={isUnverified ? 0.55 : 1}
            style={{ transition:"stroke-dasharray 0.7s ease, stroke 0.4s ease, opacity 0.3s ease" }} />
          <text x={cx} y={cy-4} textAnchor="middle" fontSize={22} fontWeight={800}
            fontFamily={T.sans} fill={isUnverified ? T.inkMid : T.ink}>{Math.round(score)}</text>
          <text x={cx} y={cy+12} textAnchor="middle" fontSize={9} fontWeight={600}
            fontFamily={T.sans} fill={T.inkMid} letterSpacing="0.1em">CONGESTION</text>
        </svg>
        <RiskPill level={level} unverified={isUnverified} />
      </div>

      {/* Info column */}
      <div style={{ flex:1 }}>
        <div style={{ fontSize:18, fontWeight:800, color: T.ink, marginBottom:4 }}>
          Port Status
        </div>
        <div style={{ fontSize:12, color: T.inkMid, marginBottom:12 }}>
          {kpi?.port || "—"} · latest data point: {kpi?.last_date || "—"}
          {lag > 0 && (
            <span style={{ color: lag > 3 ? T.amber : T.inkDim, marginLeft:6 }}>
              ({lag}-day lag)
            </span>
          )}
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0.6rem 1.2rem" }}>
          <div>
            <div style={{ fontSize:10, color: T.inkDim, marginBottom:2, letterSpacing:"0.06em", textTransform:"uppercase" }}>vs 90-day normal</div>
            <div style={{ fontSize:16, fontWeight:700, color: (kpi?.pct_vs_normal ?? 0) > 0 ? T.red : T.green }}>
              {kpi?.pct_vs_normal != null
                ? `${kpi.pct_vs_normal > 0 ? "+" : ""}${kpi.pct_vs_normal.toFixed(1)}%`
                : "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize:10, color: T.inkDim, marginBottom:2, letterSpacing:"0.06em", textTransform:"uppercase" }}>Trend (last 7d in data)</div>
            <div style={{ fontSize:13, fontWeight:700, color:
              kpi?.trend_direction === "rising"  ? T.red :
              kpi?.trend_direction === "falling" ? T.green : T.amber,
              display:"flex", alignItems:"center", gap:4,
            }}>
              {kpi?.trend_direction === "rising"  ? <TrendingUp  size={14} /> :
               kpi?.trend_direction === "falling" ? <TrendingDown size={14} /> : <Minus size={14} />}
              {kpi?.trend_direction || "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize:10, color: T.inkDim, marginBottom:2, letterSpacing:"0.06em", textTransform:"uppercase" }}>
              Ships on {kpi?.last_date || "—"}
            </div>
            <div style={{ fontSize:16, fontWeight:700, color: T.ink }}>
              {kpi?.last_portcalls != null ? Math.round(kpi.last_portcalls) : "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize:10, color: T.inkDim, marginBottom:2, letterSpacing:"0.06em", textTransform:"uppercase" }}>Data freshness</div>
            <div style={{ fontSize:13, fontWeight:600,
              color: lag === 0 ? T.green : lag > 7 ? T.red : lag > 3 ? T.amber : T.inkMid,
              display:"flex", alignItems:"center", gap:4 }}>
              <Clock size={12} />
              {lag === 0 ? "Up to date" : `${lag}d behind real-time`}
            </div>
            {liveUnavailable && lag > 7 && (
              <div style={{ fontSize:10, color: T.inkDim, marginTop:3, fontStyle:"italic" }}>
                Live AIS unavailable — tier reflects PortWatch only
              </div>
            )}
            {liveCoverage === "sparse" && (
              <div
                title="Live AIS shows few vessels near this port. The displayed tier is based on PortWatch arrivals data only."
                style={{ fontSize:10, color: T.inkMid, marginTop:3, padding:"2px 6px",
                  background: T.navy3, border: `1px solid ${T.border}`, borderRadius: 4,
                  display:"inline-block", cursor:"help" }}>
                Limited live coverage
              </div>
            )}
            {liveCoverage === "dark" && (
              <div
                title="No live AIS vessels detected near this port. Common for inland ports outside coastal AIS reception. Tier is based on PortWatch arrivals data only and has not been validated against live conditions."
                style={{ fontSize:10, color: T.inkMid, marginTop:3, padding:"2px 6px",
                  background: T.navy3, border: `1px solid ${T.border}`, borderRadius: 4,
                  display:"inline-block", cursor:"help" }}>
                Live coverage unavailable
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   7-DAY CONGESTION OUTLOOK CARDS  (weather-app style)
───────────────────────────────────────────────────────── */
function CongestionDayCard({ row, isHighest, isLowest, isFirst, isUnverified = false }) {
  const score  = row.congestion_score ?? 50;
  const level  = row.congestion_level || (score >= 67 ? "HIGH" : score >= 33 ? "MEDIUM" : "LOW");
  const clr    = congestionColor(score);
  const dateStr= row.ds || row.date || "";

  // Phase 6A.2 — when live AIS coverage can't validate the tier, render the
  // forecast card neutrally: no AVOID/BEST badge, dashed border + ring,
  // outlined level pill, and a "· UNVERIFIED" suffix on the level label
  // (this caller has horizontal room; the header pill does not).
  const cardBg     = isUnverified ? T.navy3 : (isHighest ? T.redBg : isLowest ? T.greenBg : T.navy3);
  const cardBorder = isUnverified
    ? `1px dashed ${T.borderL}`
    : `1px solid ${isHighest ? T.red+"44" : isLowest ? T.green+"44" : T.border}`;

  return (
    <div style={{
      flex:1, minWidth:0,
      background: cardBg,
      border: cardBorder,
      borderRadius:10, padding:"0.9rem 0.6rem",
      display:"flex", flexDirection:"column", alignItems:"center", gap:6,
      transition:"background 0.2s",
      position:"relative",
      opacity: isUnverified ? 0.85 : 1,
    }}>
      {isFirst && (
        <div style={{
          position:"absolute", top:-9, left:"50%", transform:"translateX(-50%)",
          background: T.blue, color:"#fff", fontSize:8, fontWeight:700,
          padding:"1px 6px", borderRadius:4, letterSpacing:"0.06em", textTransform:"uppercase",
          whiteSpace:"nowrap",
        }}>Forecast</div>
      )}

      <div style={{ fontSize:11, fontWeight:700, color: T.inkMid, letterSpacing:"0.06em", textTransform:"uppercase" }}>
        {dayOf(dateStr)}
      </div>
      <div style={{ fontSize:10, color: T.inkDim }}>
        {dateOf(dateStr)}
      </div>

      {/* Score ring */}
      <svg width={52} height={52} viewBox="0 0 52 52">
        <circle cx={26} cy={26} r={20} fill="none" stroke={T.border} strokeWidth={4} />
        <circle cx={26} cy={26} r={20} fill="none" stroke={clr} strokeWidth={4}
          strokeDasharray={isUnverified ? "4 3" : `${(score / 100) * 125.6} 125.6`}
          strokeDashoffset={31.4}
          strokeLinecap="round"
          opacity={isUnverified ? 0.55 : 1}
          style={{ transition:"stroke-dasharray 0.6s ease, opacity 0.3s ease" }} />
        <text x={26} y={31} textAnchor="middle" fontSize={13} fontWeight={800}
          fontFamily={T.sans} fill={isUnverified ? T.inkMid : T.ink}>{Math.round(score)}</text>
      </svg>

      <div style={{
        fontSize:9, fontWeight:700, letterSpacing:"0.06em",
        color: clr, textTransform:"uppercase",
        padding:"2px 6px", borderRadius:4,
        background: isUnverified ? "transparent" : `${clr}18`,
        border: isUnverified ? `1px dashed ${clr}88` : "none",
        whiteSpace:"nowrap",
      }}>
        {level}{isUnverified ? " · UNVERIFIED" : ""}
      </div>

      {!isUnverified && isHighest && <div style={{ fontSize:8, color: T.red, fontWeight:700, letterSpacing:"0.05em" }}>⚠ AVOID</div>}
      {!isUnverified && isLowest  && <div style={{ fontSize:8, color: T.green, fontWeight:700, letterSpacing:"0.05em" }}>✓ BEST</div>}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   CONGESTION TIMELINE CHART  (90d history + 7d forecast)
───────────────────────────────────────────────────────── */
function CongestionTimelineChart({ history, forecast }) {
  const histRows = (history || []).map(r => ({
    date: r.date?.slice(5),
    score: r.congestion_score ?? null,
    _type: "hist",
  }));

  const fcstRows = (forecast || []).map(r => ({
    date: r.ds?.slice(5),
    fcst: r.congestion_score ?? null,
    _type: "fcst",
  }));

  const combined = [...histRows, ...fcstRows];
  if (!combined.length) return null;

  const cutDate = histRows.length ? histRows[histRows.length - 1]?.date : null;

  return (
    <ResponsiveContainer width="100%" height={180}>
      <ComposedChart data={combined} margin={{ top:8, right:8, bottom:0, left:0 }}>
        <defs>
          <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor={T.teal} stopOpacity={0.3} />
            <stop offset="100%" stopColor={T.teal} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        <CartesianGrid strokeDasharray="2 4" stroke={T.border} vertical={false} />
        <XAxis dataKey="date" tick={{ fill:T.inkDim, fontSize:9 }} tickLine={false} axisLine={false}
          interval={Math.floor(combined.length / 7)} />
        <YAxis domain={[0,100]} tick={{ fill:T.inkDim, fontSize:9 }} tickLine={false} axisLine={false} width={24} />
        <Tooltip content={({ active, payload, label }) => {
          if (!active || !payload?.length) return null;
          return (
            <div style={{ background:T.slate, border:`1px solid ${T.borderL}`, borderRadius:8, padding:"0.5rem 0.75rem", fontSize:11 }}>
              <div style={{ color:T.inkMid, marginBottom:3 }}>{label}</div>
              {payload.map((p, i) => p.value != null && (
                <div key={i} style={{ color:p.color, fontWeight:600 }}>
                  {p.name}: {Math.round(p.value)}
                </div>
              ))}
            </div>
          );
        }} />

        {/* Threshold zones */}
        <ReferenceLine y={67} stroke={T.red}   strokeDasharray="3 3" strokeOpacity={0.5}
          label={{ value:"HIGH", fill:T.red,   fontSize:8, position:"insideTopRight" }} />
        <ReferenceLine y={33} stroke={T.amber} strokeDasharray="3 3" strokeOpacity={0.5}
          label={{ value:"MED",  fill:T.amber, fontSize:8, position:"insideTopRight" }} />

        {/* History area */}
        <Area type="monotone" dataKey="score" name="Historical"
          stroke={T.teal} strokeWidth={2} fill="url(#histGrad)" dot={false} connectNulls />

        {/* Forecast dashed line */}
        <Line type="monotone" dataKey="fcst" name="Forecast"
          stroke={T.blue} strokeWidth={2} strokeDasharray="5 3"
          dot={{ r:3, fill:T.blue, stroke:T.navy2, strokeWidth:2 }}
          activeDot={{ r:5 }} connectNulls />

        {cutDate && (
          <ReferenceLine x={cutDate}
            stroke={T.borderL} strokeDasharray="2 2"
            label={{ value:"Now", fill:T.inkDim, fontSize:9, position:"insideTopRight" }} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/* ─────────────────────────────────────────────────────────
   INSIGHTS PANEL
───────────────────────────────────────────────────────── */
function InsightsPanel({ kpi, forecast }) {
  if (!forecast?.length) return null;

  const scores = forecast.map(r => ({ date: r.ds, score: r.congestion_score ?? 50, level: r.congestion_level }));
  const minRow  = scores.reduce((a, b) => b.score < a.score ? b : a, scores[0]);
  const highDays= scores.filter(r => r.score >= 67);
  const avgFcst = scores.reduce((s, r) => s + r.score, 0) / scores.length;

  const trend = kpi?.trend_direction || "stable";
  const lag   = kpi?.data_lag_days ?? 0;

  const items = [
    {
      icon: CheckCircle,
      color: T.green,
      title: "Best day to arrive",
      body: `${dayOf(minRow.date)} ${dateOf(minRow.date)} — congestion score ${Math.round(minRow.score)} (${minRow.level})`,
    },
    {
      icon: AlertTriangle,
      color: T.red,
      title: highDays.length > 0 ? `Avoid (${highDays.length} HIGH day${highDays.length > 1 ? "s" : ""})` : "No high-risk days forecast",
      body: highDays.length > 0
        ? highDays.map(r => `${dayOf(r.date)} ${dateOf(r.date)}`).join(", ")
        : "All 7 forecast days within normal range",
    },
    {
      icon: TrendingUp,
      color: trend === "rising" ? T.red : trend === "falling" ? T.green : T.amber,
      title: "Current trend",
      body: trend === "rising"  ? "Traffic rising — expect higher congestion"
          : trend === "falling" ? "Traffic easing — conditions improving"
          : "Stable — no significant change expected",
    },
    {
      icon: Zap,
      color: T.blue,
      title: "7-day avg forecast",
      body: `Score ${avgFcst.toFixed(0)} / 100 — ${avgFcst >= 67 ? "HIGH congestion period" : avgFcst >= 33 ? "Moderate period" : "Low-congestion week"}`,
    },
  ];

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
      {items.map(({ icon: Icon, color, title, body }) => (
        <div key={title} style={{
          display:"flex", gap:10, padding:"0.65rem 0.8rem",
          background: T.navy3, borderRadius:8, border:`1px solid ${T.border}`,
        }}>
          <div style={{
            width:28, height:28, borderRadius:7, flexShrink:0,
            background:`${color}18`,
            display:"flex", alignItems:"center", justifyContent:"center",
          }}>
            <Icon size={13} color={color} />
          </div>
          <div>
            <div style={{ fontSize:11, fontWeight:700, color: T.ink, marginBottom:2 }}>{title}</div>
            <div style={{ fontSize:10, color: T.inkMid, lineHeight:1.5 }}>{body}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   ALTERNATIVE PORTS TABLE
───────────────────────────────────────────────────────── */
function AlternativePortsTable({ topPorts, selectedPort, onSelect }) {
  const ports = (topPorts || []).filter(p => p.portname !== selectedPort).slice(0, 8);
  if (!ports.length) return <div style={{ color: T.inkDim, fontSize:12 }}>No data</div>;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
      <div style={{ display:"grid", gridTemplateColumns:"1fr auto auto", gap:"0.5rem 1rem",
        padding:"0.3rem 0.5rem", marginBottom:2 }}>
        <Label>Port</Label>
        <Label>Score</Label>
        <Label>Status</Label>
      </div>
      {ports.map((p, i) => {
        const color = p.status === "HIGH" ? T.red : p.status === "MEDIUM" ? T.amber : T.green;
        return (
          <div
            key={p.portname}
            onClick={() => onSelect(p.portname)}
            style={{
              display:"grid", gridTemplateColumns:"1fr auto auto", gap:"0.5rem 1rem",
              padding:"0.55rem 0.7rem", borderRadius:7,
              background: T.navy3, border:`1px solid ${T.border}`,
              cursor:"pointer", transition:"border-color 0.15s",
              alignItems:"center",
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = T.borderL}
            onMouseLeave={e => e.currentTarget.style.borderColor = T.border}
          >
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <span style={{ fontSize:10, color: T.inkDim, fontFamily: T.mono, width:14, textAlign:"right" }}>
                {i + 1}
              </span>
              <span style={{ fontSize:12, fontWeight:600, color: T.ink,
                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                {p.portname}
              </span>
            </div>
            <div style={{
              fontFamily: T.mono, fontSize:12, fontWeight:700, color,
              minWidth:28, textAlign:"right",
            }}>
              {Math.round(p.current_score ?? 0)}
            </div>
            <span style={{
              fontSize:9, fontWeight:700, letterSpacing:"0.05em",
              padding:"2px 6px", borderRadius:4,
              background:`${color}18`, color,
              textTransform:"uppercase",
            }}>
              {p.status}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   VESSEL MIX MINI CHART
───────────────────────────────────────────────────────── */
const VESSEL_CFG = [
  { key:"portcalls_container",     label:"Container", color:"#3B82F6" },
  { key:"portcalls_tanker",        label:"Tanker",    color:"#F59E0B" },
  { key:"portcalls_dry_bulk",      label:"Dry Bulk",  color:"#10B981" },
  { key:"portcalls_general_cargo", label:"General",   color:"#8B5CF6" },
  { key:"portcalls_roro",          label:"RoRo",      color:"#EC4899" },
];

function VesselMixChart({ mix }) {
  if (!mix?.length) return null;
  const last6 = mix.slice(-6);
  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={last6} margin={{ top:4, right:4, bottom:0, left:0 }}>
        <CartesianGrid strokeDasharray="2 4" stroke={T.border} vertical={false} />
        <XAxis dataKey="month" tickFormatter={d => d?.slice(5,7)+"/"+d?.slice(2,4)}
          tick={{ fill:T.inkDim, fontSize:9 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill:T.inkDim, fontSize:9 }} tickLine={false} axisLine={false} width={24} />
        <Tooltip content={({ active, payload, label }) => {
          if (!active || !payload?.length) return null;
          return (
            <div style={{ background:T.slate, border:`1px solid ${T.borderL}`, borderRadius:8, padding:"0.5rem 0.75rem", fontSize:11 }}>
              <div style={{ color:T.inkMid, marginBottom:3 }}>{label}</div>
              {payload.map((p, i) => (
                <div key={i} style={{ color:p.color, fontWeight:600 }}>
                  {p.name}: {typeof p.value === "number" ? p.value.toFixed(1) : p.value}
                </div>
              ))}
            </div>
          );
        }} />
        {VESSEL_CFG.map(v => (
          <Bar key={v.key} dataKey={v.key} stackId="a" fill={v.color} name={v.label} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ─────────────────────────────────────────────────────────
   SIDEBAR PORTS LIST  (sorted by lowest congestion)
───────────────────────────────────────────────────────── */
function SidebarPortsList({ topPorts, selectedPort, onSelect }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:0, overflowY:"auto", flex:1 }}>
      {(topPorts || []).map((p, i) => {
        const isActive = p.portname === selectedPort;
        const color = p.status === "HIGH" ? T.red : p.status === "MEDIUM" ? T.amber : T.green;
        return (
          <div
            key={p.portname}
            onClick={() => onSelect(p.portname)}
            style={{
              display:"flex", alignItems:"center", gap:8,
              padding:"0.55rem 0.75rem",
              background: isActive ? T.tealBg : "transparent",
              borderLeft: `2px solid ${isActive ? T.teal : "transparent"}`,
              cursor:"pointer", transition:"all 0.15s",
            }}
            onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = T.navy3; }}
            onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
          >
            <span style={{ fontSize:9, fontFamily:T.mono, color:T.inkDim, width:14, textAlign:"right" }}>
              {i + 1}
            </span>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:11, fontWeight:600, color: isActive ? T.teal : T.ink,
                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                {p.portname}
              </div>
            </div>
            <div style={{ display:"flex", alignItems:"center", gap:4, flexShrink:0 }}>
              <span style={{ fontSize:10, fontFamily:T.mono, fontWeight:700, color }}>
                {Math.round(p.current_score ?? 0)}
              </span>
              <span style={{ width:5, height:5, borderRadius:"50%", background:color, flexShrink:0 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   SIDEBAR LOADED PORTS  (sorted by current portcalls desc)
───────────────────────────────────────────────────────── */
function SidebarLoadedPortsList({ loadedPorts, selectedPort, onSelect }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:0, overflowY:"auto", flex:1 }}>
      {(loadedPorts || []).map((p, i) => {
        const isActive = p.portname === selectedPort;
        const color = p.congestion_level === "HIGH" ? T.red : p.congestion_level === "MEDIUM" ? T.amber : T.green;
        return (
          <div
            key={p.portname}
            onClick={() => onSelect(p.portname)}
            style={{
              display:"flex", alignItems:"center", gap:8,
              padding:"0.55rem 0.75rem",
              background: isActive ? T.tealBg : "transparent",
              borderLeft: `2px solid ${isActive ? T.teal : "transparent"}`,
              cursor:"pointer", transition:"all 0.15s",
            }}
            onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = T.navy3; }}
            onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
          >
            <span style={{ fontSize:9, fontFamily:T.mono, color:T.inkDim, width:14, textAlign:"right" }}>
              {i + 1}
            </span>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:11, fontWeight:600, color: isActive ? T.teal : T.ink,
                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                {p.portname}
              </div>
            </div>
            <div style={{ display:"flex", alignItems:"center", gap:4, flexShrink:0 }}>
              <span style={{ fontSize:10, fontFamily:T.mono, fontWeight:700, color: T.ink }}>
                {Math.round(p.current_portcalls ?? 0)}
              </span>
              <span style={{ width:5, height:5, borderRadius:"50%", background:color, flexShrink:0 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   CHOKEPOINT COMPONENTS
───────────────────────────────────────────────────────── */
const DISRUPTION_CFG = {
  HIGH:   { color: T.red,   bg: T.redBg,   label: "Disrupted",    icon: AlertTriangle },
  MEDIUM: { color: T.amber, bg: T.amberBg, label: "Watch",        icon: Clock },
  LOW:    { color: T.green, bg: T.greenBg, label: "Normal Flow",  icon: CheckCircle },
};

/* ─────────────────────────────────────────────────────────
   WEATHER COMPONENTS
───────────────────────────────────────────────────────── */
const WEATHER_RISK_CFG = {
  HIGH:   { color: T.red,   bg: T.redBg,   label: "Ops Risk"   },
  MEDIUM: { color: T.amber, bg: T.amberBg, label: "Watch"      },
  LOW:    { color: T.green, bg: T.greenBg, label: "Clear"      },
};

const WIND_DIR = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
const degToDir = deg => WIND_DIR[Math.round(deg / 22.5) % 16] || "—";

function WeatherIcon({ icon, size = 28 }) {
  if (!icon) return null;
  return (
    <img
      src={`https://openweathermap.org/img/wn/${icon}@2x.png`}
      alt="weather"
      style={{ width: size, height: size, objectFit:"contain" }}
    />
  );
}

function WeatherCard({ port }) {
  const { data, loading } = useWeather(port);
  if (loading) return null;
  if (!data?.current) return null;

  const c   = data.current;
  const cfg = WEATHER_RISK_CFG[c.risk?.level] || WEATHER_RISK_CFG.LOW;

  return (
    <Card style={{ padding:"1rem 1.1rem" }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
          <Zap size={13} color={T.blue} />
          <Label>Port Weather</Label>
          <span style={{ fontSize:9, color:T.inkDim }}>current conditions</span>
        </div>
        <span style={{
          fontSize:10, fontWeight:700, padding:"2px 8px", borderRadius:99,
          background: cfg.bg, color: cfg.color,
          border:`1px solid ${cfg.color}33`, textTransform:"uppercase",
        }}>
          {cfg.label}
        </span>
      </div>

      <div style={{ display:"flex", alignItems:"center", gap:"1rem" }}>
        {/* Icon + temp */}
        <div style={{ display:"flex", flexDirection:"column", alignItems:"center",
          background: T.navy3, borderRadius:10, padding:"0.6rem 0.8rem",
          border:`1px solid ${T.border}`, flexShrink:0 }}>
          <WeatherIcon icon={c.weather_icon} size={40} />
          <div style={{ fontSize:22, fontWeight:800, color:T.ink }}>{c.temp_c}°C</div>
          <div style={{ fontSize:9, color:T.inkMid, textAlign:"center", maxWidth:80 }}>
            {c.weather_description}
          </div>
        </div>

        {/* Stats grid */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:"0.5rem", flex:1 }}>
          {[
            { label:"Wind",       value:`${c.wind_speed_ms} m/s ${degToDir(c.wind_deg)}`, sub: c.wind_beaufort,
              color: c.wind_speed_ms >= 15 ? T.red : c.wind_speed_ms >= 10 ? T.amber : T.inkMid },
            { label:"Gust",       value:`${c.wind_gust_ms} m/s`, sub:"peak gust",
              color: c.wind_gust_ms >= 20 ? T.red : T.inkMid },
            { label:"Visibility", value: c.visibility_m >= 10000 ? ">10 km" : `${(c.visibility_m/1000).toFixed(1)} km`,
              sub: c.visibility_m <= 500 ? "Critical" : c.visibility_m <= 1000 ? "Fog advisory" : "Good",
              color: c.visibility_m <= 500 ? T.red : c.visibility_m <= 1000 ? T.amber : T.inkMid },
            { label:"Humidity",   value:`${c.humidity}%`,        sub:"relative", color: T.inkMid },
            { label:"Pressure",   value:`${c.pressure_hpa} hPa`, sub:"sea level", color: T.inkMid },
            { label:"Rain",       value: c.rain_1h > 0 ? `${c.rain_1h} mm/h` : "None",
              sub:"1h accum",
              color: c.rain_1h >= 10 ? T.red : c.rain_1h > 0 ? T.amber : T.inkMid },
          ].map(({ label, value, sub, color }) => (
            <div key={label} style={{ background:T.navy3, borderRadius:7,
              border:`1px solid ${T.border}`, padding:"0.45rem 0.6rem" }}>
              <div style={{ fontSize:9, color:T.inkDim, textTransform:"uppercase",
                letterSpacing:"0.06em", marginBottom:2 }}>{label}</div>
              <div style={{ fontSize:13, fontWeight:700, color }}>{value}</div>
              <div style={{ fontSize:9, color:T.inkDim }}>{sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Risk reason */}
      {c.risk?.level !== "LOW" && (
        <div style={{ marginTop:8, padding:"0.4rem 0.7rem", borderRadius:6,
          background: cfg.bg, border:`1px solid ${cfg.color}33`,
          fontSize:10, color: cfg.color }}>
          ⚠ {c.risk.reasons[0]}
        </div>
      )}

      {/* 5-day forecast strip */}
      {data.forecast?.length > 0 && (
        <div style={{ display:"flex", gap:4, marginTop:10 }}>
          {data.forecast.slice(0, 5).map((d, i) => {
            const rCfg = WEATHER_RISK_CFG[d.risk_level] || WEATHER_RISK_CFG.LOW;
            return (
              <div key={i} style={{ flex:1, background:T.navy3, borderRadius:7,
                border:`1px solid ${d.risk_level !== "LOW" ? rCfg.color+"44" : T.border}`,
                padding:"0.4rem 0.3rem", display:"flex", flexDirection:"column",
                alignItems:"center", gap:2 }}>
                <div style={{ fontSize:9, color:T.inkDim, fontWeight:600 }}>
                  {d.date?.slice(5)}
                </div>
                <WeatherIcon icon={d.weather_icon} size={22} />
                <div style={{ fontSize:10, fontWeight:700, color:T.ink }}>
                  {d.temp_max_c}°
                </div>
                <div style={{ fontSize:8, color:T.inkDim }}>{d.temp_min_c}°</div>
                <div style={{ fontSize:8, color: d.wind_speed_ms >= 15 ? T.red : T.inkDim }}>
                  {d.wind_speed_ms}m/s
                </div>
                {d.pop > 20 && (
                  <div style={{ fontSize:8, color:T.blue }}>{d.pop}%💧</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────
   SUPPLY CHAIN RISK CARD  (port-specific chokepoints)
───────────────────────────────────────────────────────── */
function SupplyChainRiskCard({ port }) {
  const { data, loading } = usePortChokepoints(port);
  const chokepoints = data?.chokepoints || [];

  if (loading) return (
    <Card style={{ padding:"1rem 1.1rem" }}>
      <Label style={{ marginBottom:8 }}>Supply Chain Risk</Label>
      <Spinner />
    </Card>
  );

  const worstLevel = chokepoints.some(c => c.disruption_level === "HIGH") ? "HIGH"
    : chokepoints.some(c => c.disruption_level === "MEDIUM") ? "MEDIUM" : "LOW";
  const overallCfg = DISRUPTION_CFG[worstLevel] || DISRUPTION_CFG.LOW;
  const OverallIcon = overallCfg.icon;

  return (
    <Card style={{ padding:"1rem 1.1rem" }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <Navigation size={13} color={T.amber} />
          <div>
            <Label>Supply Chain Risk</Label>
            <div style={{ fontSize:10, color:T.inkMid, marginTop:2 }}>
              Upstream chokepoints feeding {port}
            </div>
          </div>
        </div>
        <span style={{
          display:"flex", alignItems:"center", gap:5,
          fontSize:10, fontWeight:700, padding:"3px 10px", borderRadius:99,
          background: overallCfg.bg, color: overallCfg.color,
          border:`1px solid ${overallCfg.color}33`, textTransform:"uppercase",
        }}>
          <OverallIcon size={10} />
          {worstLevel === "HIGH" ? "Disruption Detected" : worstLevel === "MEDIUM" ? "Monitor Closely" : "Supply Chain Clear"}
        </span>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:`repeat(${Math.min(chokepoints.length, 4)}, 1fr)`, gap:"0.6rem" }}>
        {chokepoints.map(c => {
          const cfg = DISRUPTION_CFG[c.disruption_level] || DISRUPTION_CFG.LOW;
          const score = c.disruption_score ?? 0;
          return (
            <div key={c.portname} style={{
              background: T.navy3, borderRadius:8,
              border:`1px solid ${cfg.color}44`,
              padding:"0.65rem 0.7rem",
              display:"flex", flexDirection:"column", gap:5,
            }}>
              <div style={{ fontSize:10, fontWeight:700, color:T.ink,
                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                {c.portname}
              </div>

              {/* Score bar */}
              <div style={{ height:3, background:T.border, borderRadius:2, overflow:"hidden" }}>
                <div style={{ width:`${score}%`, height:"100%", background:cfg.color,
                  borderRadius:2, transition:"width 0.6s ease" }} />
              </div>

              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                <span style={{ fontSize:9, padding:"1px 5px", borderRadius:3,
                  background:`${cfg.color}18`, color:cfg.color,
                  fontWeight:700, textTransform:"uppercase", letterSpacing:"0.04em" }}>
                  {c.disruption_level}
                </span>
                <div style={{ display:"flex", alignItems:"center", gap:3, fontSize:9, color:
                  c.trend === "rising" ? T.red : c.trend === "falling" ? T.green : T.inkDim }}>
                  {c.trend === "rising"  ? <TrendingUp size={9}  /> :
                   c.trend === "falling" ? <TrendingDown size={9} /> : <Minus size={9} />}
                  {c.pct_vs_normal != null
                    ? `${c.pct_vs_normal > 0 ? "+" : ""}${c.pct_vs_normal.toFixed(0)}%`
                    : c.trend}
                </div>
              </div>

              <div style={{ fontSize:9, color:T.inkDim }}>
                {c.n_total ?? 0} ships · avg {c.avg_daily_transits?.toFixed(0) ?? "—"}/day
              </div>

              {/* Transit lag + impact note */}
              {c.lag_days && (
                <div style={{
                  fontSize:8,
                  color: c.disruption_level === "HIGH" ? cfg.color : T.inkDim,
                  fontWeight: c.disruption_level === "HIGH" ? 600 : 400,
                  borderTop:`1px solid ${T.border}`,
                  paddingTop:4, marginTop:1,
                }}>
                  {c.impact_note || `~${c.lag_days}d transit to port`}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────
   AI ADVISOR (chat panel)
───────────────────────────────────────────────────────── */
const QUESTION_CATEGORIES = {
  Diagnostic: [
    "Break down today's delay score for {port} — which factor is driving it most?",
    "Is {port}'s current congestion an anomaly or within normal variance?",
    "How does {port} today compare to the same week last year?",
    "Which vessel classes are contributing most to queue pressure at {port}?",
  ],
  Predictive: [
    "What's the 7-day congestion forecast confidence interval for {port}?",
    "When is the next predicted congestion spike at {port}?",
    "Forecast berth availability at {port} for vessels arriving in 72 hours",
    "If a chokepoint closes for 48h, what's the cascade effect on {port}?",
  ],
  Comparative: [
    "Compare {port} to Oakland and Seattle this week",
    "Which West Coast port has the lowest delay score right now?",
    "Rank ports by 7-day forecast improvement",
    "Is rerouting from {port} to Oakland worth the extra transit time?",
  ],
  Operational: [
    "Best arrival window at {port} to minimize wait time in the next 5 days",
    "Should I hold vessels at anchor or reroute from {port}?",
    "What's the expected dwell time at {port} for a vessel arriving Thursday?",
    "Recommend a contingency plan if {port} volatility exceeds threshold",
  ],
};

function AiAdvisor({ port, onSelectPort }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);
  const [activeCategory, setActiveCategory] = useState("Diagnostic");
  const bottomRef               = useRef(null);
  const { data: portListData }  = usePortList();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const portLabel = port || "Los Angeles-Long Beach";

  const send = async (question, reset = false) => {
    const q = question || input.trim();
    if (!q) return;
    setInput("");
    setError(null);
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setLoading(true);
    try {
      const res = await postChat(q, port, reset);
      const sources = res.sources || [];
      // Add AI message first
      setMessages(prev => [...prev, { role: "ai", text: res.answer, sources, followups: null }]);
      // Fetch follow-ups in background
      postFollowups(res.answer, port).then(followups => {
        if (followups && followups.length > 0) {
          setMessages(prev => {
            const updated = [...prev];
            // Find the last AI message and attach followups
            for (let i = updated.length - 1; i >= 0; i--) {
              if (updated[i].role === "ai" && updated[i].followups === null) {
                updated[i] = { ...updated[i], followups };
                break;
              }
            }
            return updated;
          });
        }
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setMessages([]);
    setError(null);
  };

  const isEmpty = messages.length === 0;
  const categories = Object.keys(QUESTION_CATEGORIES);

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" }}>

      {/* Header */}
      <div style={{
        padding:"0.85rem 1.25rem", borderBottom:`1px solid ${T.border}`,
        display:"flex", alignItems:"center", justifyContent:"space-between", flexShrink:0,
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <div style={{
            width:28, height:28, borderRadius:7,
            background:T.tealSubtle, border:`1px solid ${T.tealBorder}`,
            display:"flex", alignItems:"center", justifyContent:"center",
          }}>
            <MessageSquare size={13} color={T.teal} />
          </div>
          <div>
            <div style={{ fontWeight:700, fontSize:13 }}>DockWise AI Advisor</div>
            <div style={{ fontSize:9, color:T.inkDim, letterSpacing:"0.05em", textTransform:"uppercase" }}>
              Powered by Groq · llama-3.3-70b
            </div>
          </div>
        </div>
        {messages.length > 0 && (
          <button onClick={reset} style={{
            display:"flex", alignItems:"center", gap:4,
            padding:"0.25rem 0.6rem", borderRadius:6,
            background:"transparent", border:`1px solid ${T.border}`,
            color:T.inkMid, fontSize:10, cursor:"pointer", fontFamily:T.sans,
          }}>
            <RotateCcw size={10} /> New chat
          </button>
        )}
      </div>

      {/* Message area */}
      <div style={{ flex:1, overflowY:"auto", padding:"1rem 1.25rem", display:"flex", flexDirection:"column", gap:"0.75rem" }}>
        {isEmpty && (
          <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
            flex:1, gap:"1.5rem", paddingTop:"2rem" }}>
            <div style={{ textAlign:"center" }}>
              <div style={{ fontSize:28, marginBottom:8 }}>{"\u{1F6A2}"}</div>
              <div style={{ fontWeight:700, fontSize:15, color:T.ink, marginBottom:4 }}>
                Maritime Intelligence Advisor
              </div>
              <div style={{ fontSize:12, color:T.inkDim, maxWidth:340, lineHeight:1.5 }}>
                Ask about port congestion, chokepoint risks, weather impacts, and supply chain recommendations.
                {port && <span style={{ color:T.teal }}> Currently analysing <strong>{port}</strong>.</span>}
              </div>
            </div>

            {/* Today's Briefing (3A) */}
            <Briefing T={T} onAskMore={(q) => send(q)} />

            {/* Nearby Port Outlook (6B Part 3) */}
            {port && (
              <NearbyPortOutlook T={T} port={port} onSelectPort={onSelectPort} />
            )}

            {/* Category pills */}
            <div style={{ display:"flex", gap:6, flexWrap:"wrap", justifyContent:"center" }}>
              {categories.map(cat => (
                <button key={cat} onClick={() => setActiveCategory(cat)} style={{
                  padding:"0.3rem 0.75rem", borderRadius:20,
                  background: activeCategory === cat ? T.tealSubtle : "transparent",
                  border: `1px solid ${activeCategory === cat ? T.teal : T.border}`,
                  color: activeCategory === cat ? T.teal : T.inkMid,
                  fontSize:11, fontWeight: activeCategory === cat ? 700 : 500,
                  cursor:"pointer", fontFamily:T.sans,
                  transition:"all 0.15s",
                }}>
                  {cat}
                </button>
              ))}
            </div>

            {/* Suggested questions for active category */}
            <div style={{ display:"flex", flexDirection:"column", gap:6, width:"100%", maxWidth:520 }}>
              <div style={{ fontSize:10, color:T.inkDim, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:2 }}>
                {activeCategory} questions
              </div>
              {QUESTION_CATEGORIES[activeCategory].map((q, i) => {
                const resolved = q.replace(/\{port\}/g, portLabel);
                return (
                  <button key={i} onClick={() => send(resolved)} style={{
                    textAlign:"left", padding:"0.5rem 0.8rem", borderRadius:8,
                    background:T.navy3, border:`1px solid ${T.border}`,
                    color:T.inkMid, fontSize:12, cursor:"pointer", fontFamily:T.sans,
                    transition:"all 0.15s",
                  }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = T.teal; e.currentTarget.style.color = T.ink; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.inkMid; }}
                  >
                    {resolved}
                  </button>
                );
              })}
            </div>

            {/* Port Comparison (3C) */}
            {portListData && portListData.ports && (
              <PortComparison T={T} ports={portListData.ports} />
            )}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} style={{ display:"flex", flexDirection:"column",
            alignItems: m.role === "user" ? "flex-end" : "flex-start",
          }}>
            <div style={{
              maxWidth:"82%",
              padding:"0.65rem 0.9rem",
              borderRadius: m.role === "user" ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
              background: m.role === "user" ? T.tealBg : T.navy3,
              border: `1px solid ${m.role === "user" ? T.tealBorder : T.border}`,
              fontSize:13, lineHeight:1.6, color:T.ink,
              whiteSpace:"pre-wrap",
            }}>
              {m.role === "ai" && (
                <div style={{ display:"flex", alignItems:"center", gap:4, marginBottom:6 }}>
                  <MessageSquare size={10} color={T.teal} />
                  <span style={{ fontSize:9, color:T.teal, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.05em" }}>
                    DockWise AI
                  </span>
                </div>
              )}
              {m.text}
              {/* Sources footer */}
              {m.role === "ai" && m.sources && m.sources.length > 0 && (
                <div style={{
                  marginTop:8, paddingTop:6, borderTop:`1px solid ${T.border}`,
                  fontSize:10, color:T.inkDim, fontStyle:"italic",
                }}>
                  Sources: {m.sources.join(" · ")}
                </div>
              )}
            </div>
            {/* Follow-up chips */}
            {m.role === "ai" && m.followups && m.followups.length > 0 && (
              <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginTop:6, maxWidth:"82%" }}>
                {m.followups.map((fq, fi) => (
                  <button key={fi} onClick={() => send(fq)} disabled={loading} style={{
                    padding:"0.25rem 0.6rem", borderRadius:14,
                    background:"transparent", border:`1px solid ${T.border}`,
                    color:T.inkMid, fontSize:11, cursor: loading ? "not-allowed" : "pointer",
                    fontFamily:T.sans, transition:"all 0.15s",
                    opacity: loading ? 0.5 : 1,
                  }}
                    onMouseEnter={e => { if (!loading) { e.currentTarget.style.borderColor = T.teal; e.currentTarget.style.color = T.teal; } }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.inkMid; }}
                  >
                    {fq}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display:"flex", justifyContent:"flex-start" }}>
            <div style={{
              padding:"0.65rem 0.9rem", borderRadius:"12px 12px 12px 4px",
              background:T.navy3, border:`1px solid ${T.border}`,
              display:"flex", alignItems:"center", gap:6,
            }}>
              <div style={{ display:"flex", gap:3 }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width:6, height:6, borderRadius:"50%", background:T.teal,
                    animation:`pulse-dot 1.2s ${i * 0.2}s infinite ease-in-out`,
                  }} />
                ))}
              </div>
              <span style={{ fontSize:11, color:T.inkDim }}>Analysing…</span>
            </div>
          </div>
        )}

        {error && (
          <div style={{
            padding:"0.6rem 0.9rem", borderRadius:8,
            background:T.redBg, border:`1px solid ${T.red}44`,
            color:T.red, fontSize:12,
          }}>
            ⚠ {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{
        padding:"0.75rem 1.25rem", borderTop:`1px solid ${T.border}`, flexShrink:0,
        display:"flex", gap:8, alignItems:"flex-end",
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={port ? `Ask about ${port}…` : "Ask about port conditions, chokepoints, routing…"}
          rows={2}
          disabled={loading}
          style={{
            flex:1, resize:"none", padding:"0.55rem 0.75rem",
            background:T.navy3, border:`1px solid ${T.border}`,
            borderRadius:10, color:T.ink, fontFamily:T.sans, fontSize:13,
            outline:"none", lineHeight:1.5,
            transition:"border-color 0.15s",
          }}
          onFocus={e => { e.target.style.borderColor = T.teal; }}
          onBlur={e => { e.target.style.borderColor = T.border; }}
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          style={{
            width:38, height:38, borderRadius:10, border:"none",
            background: (loading || !input.trim()) ? T.navy3 : T.teal,
            color: (loading || !input.trim()) ? T.inkDim : T.navy,
            cursor: (loading || !input.trim()) ? "not-allowed" : "pointer",
            display:"flex", alignItems:"center", justifyContent:"center",
            transition:"all 0.15s", flexShrink:0,
          }}
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────
   RISK ASSESSMENT CARD  (multi-agent pipeline output)
───────────────────────────────────────────────────────── */
function RiskAssessmentCard({ port }) {
  const { data, loading, error, reload } = useRiskAssessment(port);

  const riskColor = tier =>
    tier === "HIGH" ? T.red : tier === "MEDIUM" ? T.amber : T.green;
  const riskBg = tier =>
    tier === "HIGH" ? T.redBg : tier === "MEDIUM" ? T.amberBg : T.greenBg;

  return (
    <Card style={{ padding:"1rem 1.1rem" }}>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:14 }}>
        <div style={{ display:"flex", alignItems:"center", gap:7 }}>
          <Zap size={13} color={T.teal} />
          <div>
            <Label>AI Risk Assessment</Label>
            <div style={{ fontSize:10, color:T.inkMid, marginTop:2 }}>
              Multi-agent pipeline · Weather + Congestion + Vessel signals
            </div>
          </div>
        </div>
        <button
          onClick={reload}
          title="Re-run assessment"
          style={{
            background:"transparent", border:`1px solid ${T.border}`,
            borderRadius:6, padding:"3px 8px", cursor:"pointer",
            color:T.inkMid, display:"flex", alignItems:"center", gap:4, fontSize:10,
          }}
        >
          <RotateCcw size={10} /> Refresh
        </button>
      </div>

      {loading && <Spinner />}
      {error   && <div style={{ fontSize:12, color:T.red, padding:"0.5rem 0" }}>Error: {error}</div>}

      {!loading && !error && data && (() => {
        const tier    = data.risk_tier;
        const score   = data.risk_score;
        const signals = data.signals || {};
        const weather = signals.weather    || {};
        const cong    = signals.congestion || {};
        const vessel  = signals.vessel     || {};
        const color   = riskColor(tier);
        const bg      = riskBg(tier);

        // Vessel delay severity → color (mirrors weather risk levels)
        const vesselScore = vessel.vessel_delay_score || 0;
        const vesselTier  =
          vesselScore >= 0.67 ? "HIGH" :
          vesselScore >= 0.33 ? "MEDIUM" : "LOW";
        const vesselColor = riskColor(vesselTier);

        return (
          <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

            {/* Risk score bar + tier */}
            <div style={{
              display:"flex", alignItems:"center", gap:14,
              padding:"0.75rem 1rem", borderRadius:10,
              background:bg, border:`1px solid ${color}33`,
            }}>
              {/* Circular score */}
              <div style={{ position:"relative", flexShrink:0 }}>
                <svg width={64} height={64} viewBox="0 0 64 64">
                  <circle cx={32} cy={32} r={26} fill="none"
                    stroke={`${color}22`} strokeWidth={6} />
                  <circle cx={32} cy={32} r={26} fill="none"
                    stroke={color} strokeWidth={6}
                    strokeDasharray={`${2 * Math.PI * 26}`}
                    strokeDashoffset={`${2 * Math.PI * 26 * (1 - score)}`}
                    strokeLinecap="round"
                    transform="rotate(-90 32 32)" />
                </svg>
                <div style={{
                  position:"absolute", inset:0,
                  display:"flex", alignItems:"center", justifyContent:"center",
                  flexDirection:"column",
                }}>
                  <div style={{ fontSize:14, fontWeight:800, color, fontFamily:T.mono }}>
                    {(score * 100).toFixed(0)}
                  </div>
                  <div style={{ fontSize:8, color, opacity:0.7 }}>/ 100</div>
                </div>
              </div>

              <div>
                <div style={{ fontSize:18, fontWeight:800, color, letterSpacing:"0.04em" }}>
                  {tier} RISK
                </div>
                <div style={{ fontSize:11, color:T.inkMid, marginTop:4, lineHeight:1.5 }}>
                  {data.explanation}
                </div>
              </div>
            </div>

            {/* Agent signal breakdown */}
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:10 }}>

              {/* Weather signals */}
              <div style={{
                padding:"0.75rem", borderRadius:8,
                background:T.navy3, border:`1px solid ${T.border}`,
              }}>
                <div style={{ display:"flex", alignItems:"center", gap:5, marginBottom:8 }}>
                  <div style={{
                    width:6, height:6, borderRadius:"50%",
                    background: riskColor(weather.risk_level || "LOW"),
                  }} />
                  <Label>Weather Agent</Label>
                </div>
                <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Disruption Score</span>
                    <span style={{ fontWeight:700, color:riskColor(weather.risk_level || "LOW"), fontFamily:T.mono }}>
                      {((weather.disruption_score || 0) * 100).toFixed(0)} / 100
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Risk Level</span>
                    <span style={{ fontWeight:700, color:riskColor(weather.risk_level || "LOW") }}>
                      {weather.risk_level || "LOW"}
                    </span>
                  </div>
                  <div style={{ fontSize:10, color:T.inkDim, marginTop:2, lineHeight:1.4 }}>
                    {weather.summary || "No weather data"}
                  </div>
                  {weather.active_warnings?.length > 0 && (
                    <div style={{ marginTop:4, display:"flex", flexDirection:"column", gap:3 }}>
                      {weather.active_warnings.map((w, i) => (
                        <div key={i} style={{
                          fontSize:10, color:T.amber,
                          display:"flex", alignItems:"flex-start", gap:4,
                        }}>
                          <AlertTriangle size={9} style={{ flexShrink:0, marginTop:1 }} />
                          {w}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Congestion signals */}
              <div style={{
                padding:"0.75rem", borderRadius:8,
                background:T.navy3, border:`1px solid ${T.border}`,
              }}>
                <div style={{ display:"flex", alignItems:"center", gap:5, marginBottom:8 }}>
                  <div style={{
                    width:6, height:6, borderRadius:"50%",
                    background: congestionColor(cong.score || 0),
                  }} />
                  <Label>Congestion Agent</Label>
                </div>
                <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Congestion Score</span>
                    <span style={{ fontWeight:700, color:congestionColor(cong.score || 0), fontFamily:T.mono }}>
                      {(cong.score || 0).toFixed(1)} / 100
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>vs Baseline</span>
                    <span style={{ fontWeight:700, color:T.ink, fontFamily:T.mono }}>
                      {cong.ratio != null ? `${cong.ratio.toFixed(2)}x` : "—"}
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Trend</span>
                    <span style={{ fontWeight:700, color:
                      cong.trend === "rising" ? T.red :
                      cong.trend === "falling" ? T.green : T.inkMid
                    }}>
                      {cong.trend === "rising" ? "↑ Rising" :
                       cong.trend === "falling" ? "↓ Falling" : "→ Stable"}
                    </span>
                  </div>
                  <div style={{ fontSize:10, color:T.inkDim, marginTop:2, lineHeight:1.4 }}>
                    {cong.seasonal_context || ""}
                  </div>
                </div>
              </div>

              {/* Vessel signals */}
              <div style={{
                padding:"0.75rem", borderRadius:8,
                background:T.navy3, border:`1px solid ${T.border}`,
              }}>
                <div style={{ display:"flex", alignItems:"center", gap:5, marginBottom:8 }}>
                  <div style={{
                    width:6, height:6, borderRadius:"50%",
                    background: vesselColor,
                  }} />
                  <Label>Vessel Agent</Label>
                  {vessel.mega_vessel_flag && (
                    <span style={{
                      marginLeft:"auto",
                      fontSize:9, fontWeight:700,
                      color:T.amber,
                      display:"flex", alignItems:"center", gap:3,
                    }}>
                      <Ship size={9} /> MEGA
                    </span>
                  )}
                </div>
                <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Delay Score</span>
                    <span style={{ fontWeight:700, color:vesselColor, fontFamily:T.mono }}>
                      {(vesselScore * 100).toFixed(0)} / 100
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Vessels (72h)</span>
                    <span style={{ fontWeight:700, color:T.ink, fontFamily:T.mono }}>
                      {vessel.vessel_count ?? 0}
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>At Anchor</span>
                    <span style={{ fontWeight:700, color:T.ink, fontFamily:T.mono }}>
                      {vessel.anchor_count ?? 0}
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Moored</span>
                    <span style={{ fontWeight:700, color:T.ink, fontFamily:T.mono }}>
                      {vessel.moored_count ?? 0}
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Incoming ≤72h</span>
                    <span style={{ fontWeight:700, color:T.ink, fontFamily:T.mono }}>
                      {vessel.incoming_72h ?? 0}
                    </span>
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", fontSize:11 }}>
                    <span style={{ color:T.inkMid }}>Queue Pressure</span>
                    <span style={{ fontWeight:700, color:T.ink, fontFamily:T.mono }}>
                      {(vessel.queue_pressure ?? 0).toFixed(2)}
                    </span>
                  </div>
                  {vessel.mega_vessel_count > 0 && (
                    <div style={{ fontSize:10, color:T.inkDim, marginTop:2, lineHeight:1.4 }}>
                      {vessel.mega_vessel_count} mega-vessel{vessel.mega_vessel_count > 1 ? "s" : ""} in window
                    </div>
                  )}
                </div>
              </div>
            </div>

          </div>
        );
      })()}
    </Card>
  );
}


/* ─────────────────────────────────────────────────────────
   ROOT APP
───────────────────────────────────────────────────────── */
export default function App() {
  const [port,  setPort]  = useState("");
  const [model, setModel] = useState("Prophet");
  const [tab,   setTab]   = useState("ports"); // "ports" | "vessels" | "advisor"
  const { isDark, toggle: toggleTheme } = useTheme();

  const { data: portData }                    = usePortList();
  const { data: overview, loading: ovLoad }   = useOverview(port);
  const { data: fcstData, loading: fcLoad }   = useForecast(port, model);
  const { data: topData }                     = useTopPorts(20);                // asc — feeds AlternativePortsTable
  const { data: loadedData }                   = useTopLoadedPorts(10);
  const { data: compData }                    = useModelComp();

  const ports       = portData?.ports || [];
  const recommended = compData?.best_model || "Prophet";
  const kpi         = overview?.kpi;
  const forecast    = fcstData?.forecast || [];

  // Find highest/lowest congestion days in forecast
  const scores   = forecast.map(r => r.congestion_score ?? 50);
  const maxScore = scores.length ? Math.max(...scores) : -1;
  const minScore = scores.length ? Math.min(...scores) : 999;

  useEffect(() => { if (recommended) setModel(recommended); }, [recommended]);

  useEffect(() => {
    if (ports.length && !port) {
      const la = ports.find(p => p.toLowerCase().includes("los angeles"));
      setPort(la || ports[0]);
    }
  }, [ports, port]);

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <div style={{ display:"flex", height:"100vh", overflow:"hidden" }}>

        {/* ── LEFT SIDEBAR (Port Intelligence only) ────── */}
        <aside style={{
          width: tab === "ports" ? 210 : 0, flexShrink:0,
          background: T.navy2,
          borderRight: tab === "ports" ? `1px solid ${T.border}` : "none",
          display:"flex", flexDirection:"column",
          overflow:"hidden",
          transition:"width 0.2s ease",
        }}>
          {/* Logo */}
          <div style={{ padding:"1rem 1rem 0.85rem", borderBottom:`1px solid ${T.border}`, flexShrink:0 }}>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <div style={{
                width:30, height:30, borderRadius:8,
                background:T.tealSubtle, border:`1px solid ${T.tealBorder}`,
                display:"flex", alignItems:"center", justifyContent:"center",
              }}>
                <Anchor size={15} color={T.teal} />
              </div>
              <div>
                <div style={{ fontWeight:800, fontSize:15, letterSpacing:"0.02em" }}>DockWise</div>
                <div style={{ fontSize:9, color: T.inkDim, letterSpacing:"0.08em", textTransform:"uppercase" }}>Port Intelligence</div>
              </div>
            </div>
          </div>

          {tab === "ports" && (
            <>
              {/* Model selector */}
              <div style={{ padding:"0.75rem 0.9rem", borderBottom:`1px solid ${T.border}`, flexShrink:0 }}>
                <Label style={{ marginBottom:7 }}>Forecast Model</Label>
                <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
                  {["Prophet", "ARIMA", "XGBoost"].map(m => (
                    <button key={m} onClick={() => setModel(m)} style={{
                      display:"flex", alignItems:"center", justifyContent:"space-between",
                      padding:"0.3rem 0.6rem", borderRadius:6, border:"none", cursor:"pointer",
                      background: model === m ? T.tealBg : "transparent",
                      color: model === m ? T.teal : T.inkMid,
                      fontFamily: T.sans, fontSize:12, fontWeight: model === m ? 700 : 400,
                      textAlign:"left", transition:"all 0.15s",
                    }}>
                      {m}
                      {recommended === m && <span style={{ fontSize:9, color: T.amber }}>★ best</span>}
                    </button>
                  ))}
                </div>
              </div>

              {/* Most loaded ports — absolute current portcalls */}
              <div style={{ padding:"0.75rem 0 0", borderBottom:`1px solid ${T.border}`,
                display:"flex", flexDirection:"column", flex:1, minHeight:0, overflow:"hidden" }}>
                <div style={{ padding:"0 0.9rem 0.5rem", flexShrink:0, display:"flex", alignItems:"center", justifyContent:"space-between", gap:6 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:5, minWidth:0 }}>
                    <Label>Most Loaded Ports</Label>
                    <span
                      title={loadedData?.description || "Ports ranked by absolute current vessel call volume. Highlights the busiest ports right now."}
                      style={{ display:"inline-flex", cursor:"help", color: T.inkDim }}
                    >
                      <Info size={10} />
                    </span>
                  </div>
                  <span style={{ fontSize:9, color: T.inkDim }}>portcalls</span>
                </div>
                <SidebarLoadedPortsList
                  loadedPorts={loadedData?.ports}
                  selectedPort={port}
                  onSelect={setPort}
                />
              </div>
            </>
          )}

          {/* Bottom status */}
          <div style={{ padding:"0.6rem 0.9rem", borderTop:`1px solid ${T.border}`, flexShrink:0 }}>
            <div style={{ display:"flex", alignItems:"center", gap:6 }}>
              <LiveDot />
              <span style={{ fontSize:10, color: T.inkDim }}>Live PortWatch data</span>
            </div>
          </div>
        </aside>

        {/* ── MAIN CONTENT ─────────────────────────────── */}
        <main style={{ flex:1, overflow:"auto", background: T.navy }}>

          {/* Top bar */}
          <div style={{
            display:"flex", alignItems:"center", justifyContent:"space-between",
            padding:"0.75rem 1.25rem",
            background: T.navy2, borderBottom:`1px solid ${T.border}`,
            position:"sticky", top:0, zIndex:10,
          }}>
            {/* Tab switcher */}
            <div style={{ display:"flex", alignItems:"center", gap:4,
              background:T.navy3, borderRadius:8, padding:3, border:`1px solid ${T.border}` }}>
              {[["ports","Port Intelligence"],["vessels","Live Vessels"],["advisor","AI Advisor"]].map(([key, label]) => (
                <button key={key} onClick={() => setTab(key)} style={{
                  padding:"0.3rem 0.85rem", borderRadius:6, border:"none", cursor:"pointer",
                  background: tab === key ? T.teal : "transparent",
                  color: tab === key ? T.navy : T.inkMid,
                  fontFamily:T.sans, fontSize:12, fontWeight:700,
                  transition:"all 0.15s",
                }}>{label}</button>
              ))}
            </div>

            {tab === "ports" && (
              <div style={{ display:"flex", alignItems:"center", gap:12 }}>
                <PortSelector ports={ports} value={port} onChange={setPort} />
                {kpi && <RiskPill
                  level={kpi.congestion_level || kpi.traffic_level}
                  unverified={kpi.live_coverage === "dark" || kpi.live_coverage === "sparse" || kpi.live_coverage === "unavailable"}
                />}
              </div>
            )}

            <div style={{ display:"flex", alignItems:"center", gap:10 }}>
              {tab === "ports" && (
                <>
                  <ModelBadge model={model} recommended={recommended} />
                  {kpi?.last_date && (
                    <div style={{ fontSize:10, color:T.inkDim, display:"flex", alignItems:"center", gap:4 }}>
                      <Calendar size={10} />
                      Last data: {kpi.last_date}
                    </div>
                  )}
                </>
              )}
              <button
                onClick={toggleTheme}
                title={isDark ? "Switch to light mode" : "Switch to dark mode"}
                style={{
                  background:"none", border:`1px solid ${T.border}`, borderRadius:6,
                  cursor:"pointer", padding:"5px 7px", display:"flex", alignItems:"center",
                  color:T.inkMid, transition:"all 0.15s",
                }}
              >
                {isDark ? <Sun size={14} /> : <Moon size={14} />}
              </button>
            </div>
          </div>

          {/* Content */}
          {tab === "vessels" ? (
            <div style={{ height:"calc(100vh - 49px)", overflow:"hidden" }}>
              <VesselMap />
            </div>
          ) : tab === "advisor" ? (
            <div style={{ height:"calc(100vh - 49px)", overflow:"hidden" }}>
              <AiAdvisor port={port} onSelectPort={setPort} />
            </div>
          ) : !port ? (
            <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
              height:"calc(100% - 48px)", flexDirection:"column", gap:12, color: T.inkDim }}>
              <Anchor size={40} color={T.border} />
              <div style={{ fontSize:14 }}>Select a port to view congestion intelligence</div>
            </div>
          ) : ovLoad ? <Spinner /> : (
            <div className="fade-up" style={{ padding:"1rem 1.25rem", display:"flex", flexDirection:"column", gap:"1rem" }}>

              {/* ROW 1: Congestion hero */}
              <CongestionHero kpi={kpi} />

              {/* ROW 2: 7-day congestion outlook */}
              {!fcLoad && forecast.length > 0 && (
                <Card style={{ padding:"1rem 1.1rem" }}>
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
                    <div>
                      <Label>7-Day Congestion Outlook</Label>
                      <div style={{ fontSize:10, color: T.inkMid, marginTop:3 }}>
                        Forecasted congestion score per day · {model} model
                      </div>
                    </div>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      {fcLoad && <span style={{ fontSize:10, color: T.inkDim }}>computing…</span>}
                      <ModelBadge model={model} recommended={recommended} />
                    </div>
                  </div>
                  <div style={{ display:"flex", gap:8 }}>
                    {forecast.map((row, i) => (
                      <CongestionDayCard
                        key={i}
                        row={row}
                        isHighest={(row.congestion_score ?? 50) === maxScore}
                        isLowest={(row.congestion_score ?? 50) === minScore}
                        isFirst={i === 0}
                        isUnverified={kpi?.live_coverage === "dark" || kpi?.live_coverage === "sparse" || kpi?.live_coverage === "unavailable"}
                      />
                    ))}
                  </div>
                </Card>
              )}
              {fcLoad && (
                <Card style={{ padding:"1rem 1.1rem" }}>
                  <Label style={{ marginBottom:8 }}>7-Day Congestion Outlook</Label>
                  <Spinner />
                </Card>
              )}

              {/* ROW 3: Timeline + Insights */}
              <div style={{ display:"grid", gridTemplateColumns:"1.6fr 1fr", gap:"1rem" }}>
                <Card style={{ padding:"1rem 1.1rem" }}>
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
                    <div>
                      <Label>Congestion Timeline</Label>
                      <div style={{ fontSize:10, color: T.inkMid, marginTop:2 }}>
                        90-day history + 7-day forecast
                      </div>
                    </div>
                    <div style={{ display:"flex", gap:12, alignItems:"center" }}>
                      <span style={{ display:"flex", alignItems:"center", gap:4, fontSize:9, color:T.teal }}>
                        <span style={{ width:16, height:2, background:T.teal, display:"inline-block" }} />
                        History
                      </span>
                      <span style={{ display:"flex", alignItems:"center", gap:4, fontSize:9, color:T.blue }}>
                        <span style={{ width:16, height:2, background:T.blue, display:"inline-block",
                          backgroundImage:`repeating-linear-gradient(90deg,${T.blue} 0,${T.blue} 5px,transparent 5px,transparent 8px)` }} />
                        Forecast
                      </span>
                    </div>
                  </div>
                  <CongestionTimelineChart history={fcstData?.history} forecast={forecast} />
                </Card>

                <Card style={{ padding:"1rem 1.1rem", overflow:"auto" }}>
                  <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:10 }}>
                    <Navigation size={12} color={T.teal} />
                    <Label>Operational Insights</Label>
                  </div>
                  <InsightsPanel kpi={kpi} forecast={forecast} />
                </Card>
              </div>

              {/* ROW 4: Weather + Vessel mix + Alternatives */}
              <WeatherCard port={port} />
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"1rem" }}>
                <Card style={{ padding:"1rem 1.1rem" }}>
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
                    <Label>Vessel Type Mix</Label>
                    <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                      {VESSEL_CFG.map(v => (
                        <span key={v.key} style={{ display:"flex", alignItems:"center", gap:3, fontSize:9, color:T.inkDim }}>
                          <span style={{ width:6, height:6, borderRadius:2, background:v.color, display:"inline-block" }} />
                          {v.label}
                        </span>
                      ))}
                    </div>
                  </div>
                  <VesselMixChart mix={overview?.vessel_mix} />
                  <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0.5rem", marginTop:10 }}>
                    <div style={{ padding:"0.5rem 0.75rem", background:T.navy3, borderRadius:7, border:`1px solid ${T.border}` }}>
                      <Label style={{ marginBottom:4 }}>Avg Daily Visits</Label>
                      <div style={{ fontSize:18, fontWeight:800, color:T.ink }}>
                        {kpi?.avg_daily_visits != null ? kpi.avg_daily_visits.toFixed(1) : "—"}
                      </div>
                    </div>
                    <div style={{ padding:"0.5rem 0.75rem", background:T.navy3, borderRadius:7, border:`1px solid ${T.border}` }}>
                      <Label style={{ marginBottom:4 }}>90d Import</Label>
                      <div style={{ fontSize:18, fontWeight:800, color:T.ink }}>
                        {kpi?.total_incoming != null
                          ? kpi.total_incoming >= 1e6
                            ? `${(kpi.total_incoming/1e6).toFixed(1)}M`
                            : kpi.total_incoming >= 1e3
                              ? `${(kpi.total_incoming/1e3).toFixed(0)}K`
                              : String(kpi.total_incoming)
                          : "—"}
                      </div>
                    </div>
                  </div>
                </Card>

                <Card style={{ padding:"1rem 1.1rem" }}>
                  <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:10 }}>
                    <Info size={11} color={T.blue} />
                    <Label>Alternative Ports</Label>
                    <span style={{ fontSize:9, color:T.inkDim, marginLeft:"auto" }}>sorted by availability</span>
                  </div>
                  <div style={{ fontSize:10, color:T.inkMid, marginBottom:8 }}>
                    Click any port to switch view
                  </div>
                  <AlternativePortsTable
                    topPorts={topData?.ports}
                    selectedPort={port}
                    onSelect={setPort}
                  />
                </Card>
              </div>

              {/* ROW 5: Supply Chain Risk */}
              <SupplyChainRiskCard port={port} />

              {/* ROW 6: AI Risk Assessment (multi-agent pipeline) */}
              <RiskAssessmentCard port={port} />

            </div>
          )}
        </main>
      </div>
    </>
  );
}
