import React, { useState } from "react";
import { AlertTriangle, Navigation, Shield } from "lucide-react";
import { postScenario } from "../../hooks/useApi";

const SCENARIOS = [
  { label: "Panama Canal closes for 72 hours",     icon: "canal" },
  { label: "Labor strike at LA-Long Beach (1 week)", icon: "strike" },
  { label: "Hurricane hits Gulf ports",              icon: "hurricane" },
  { label: "Suez Canal restrictions tighten",        icon: "suez" },
];

const CONFIDENCE_COLORS = {
  high:   { color: "#10B981", bg: "rgba(16,185,129,0.12)" },
  medium: { color: "#F59E0B", bg: "rgba(245,158,11,0.12)" },
  low:    { color: "#EF4444", bg: "rgba(239,68,68,0.12)" },
};

export default function ScenarioSimulator({ T, onFollowUp }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeScenario, setActiveScenario] = useState(null);

  const run = async (scenario) => {
    setActiveScenario(scenario);
    setResult(null);
    setError(null);
    setLoading(true);
    try {
      const data = await postScenario(scenario);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const conf = result ? (CONFIDENCE_COLORS[result.confidence] || CONFIDENCE_COLORS.medium) : null;

  return (
    <div style={{ width: "100%" }}>
      <div style={{
        fontSize: 10, color: T.inkDim, textTransform: "uppercase",
        letterSpacing: "0.06em", marginBottom: 8, fontWeight: 700,
      }}>
        Scenario Simulator
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: result || loading || error ? 10 : 0 }}>
        {SCENARIOS.map(s => (
          <button
            key={s.label}
            onClick={() => run(s.label)}
            disabled={loading}
            style={{
              padding: "6px 12px", borderRadius: 8,
              background: activeScenario === s.label ? T.tealSubtle : T.navy3,
              border: `1px solid ${activeScenario === s.label ? T.teal : T.border}`,
              color: activeScenario === s.label ? T.teal : T.inkMid,
              fontSize: 11, cursor: loading ? "not-allowed" : "pointer",
              fontFamily: T.sans, opacity: loading ? 0.6 : 1,
              transition: "all 0.15s",
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      {loading && (
        <div style={{
          padding: "16px", borderRadius: 10,
          background: T.navy3, border: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <div style={{
            width: 16, height: 16, borderRadius: "50%",
            border: `2px solid ${T.border}`, borderTopColor: T.teal,
            animation: "spin 0.7s linear infinite",
          }} />
          <span style={{ fontSize: 12, color: T.inkDim }}>Analysing scenario...</span>
        </div>
      )}

      {error && (
        <div style={{
          padding: "10px 14px", borderRadius: 8,
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
          color: T.red, fontSize: 12,
        }}>
          {error}
        </div>
      )}

      {result && !loading && (
        <div style={{
          borderRadius: 10, background: T.navy3,
          border: `1px solid ${T.border}`, overflow: "hidden",
        }}>
          {/* Impact summary */}
          <div style={{ padding: "14px 16px", borderBottom: `1px solid ${T.border}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <AlertTriangle size={13} color={T.amber} />
              <span style={{ fontSize: 11, fontWeight: 700, color: T.ink, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                Impact Analysis
              </span>
              {conf && (
                <span style={{
                  marginLeft: "auto", fontSize: 9, fontWeight: 700,
                  padding: "2px 8px", borderRadius: 10,
                  color: conf.color, background: conf.bg,
                  textTransform: "uppercase",
                }}>
                  {result.confidence} confidence
                </span>
              )}
            </div>
            <div style={{ fontSize: 12, color: T.ink, lineHeight: 1.6 }}>
              {result.impact_summary}
            </div>
          </div>

          {/* Affected ports */}
          {result.affected_ports && result.affected_ports.length > 0 && (
            <div style={{ padding: "10px 16px", borderBottom: `1px solid ${T.border}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 6 }}>
                <Navigation size={11} color={T.red} />
                <span style={{ fontSize: 10, fontWeight: 700, color: T.inkDim, textTransform: "uppercase" }}>
                  Affected Ports
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {result.affected_ports.map((p, i) => (
                  <span key={i} style={{
                    fontSize: 11, padding: "3px 10px", borderRadius: 6,
                    background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)",
                    color: T.ink,
                  }}>
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Recommended reroutes */}
          {result.recommended_reroutes && result.recommended_reroutes.length > 0 && (
            <div style={{ padding: "10px 16px", borderBottom: `1px solid ${T.border}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 6 }}>
                <Shield size={11} color={T.green} />
                <span style={{ fontSize: 10, fontWeight: 700, color: T.inkDim, textTransform: "uppercase" }}>
                  Recommended Actions
                </span>
              </div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {result.recommended_reroutes.map((r, i) => (
                  <li key={i} style={{ fontSize: 11, color: T.ink, lineHeight: 1.6, marginBottom: 2 }}>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Follow up in chat */}
          <div style={{ padding: "8px 16px" }}>
            <button
              onClick={() => onFollowUp(`Tell me more about the impact of: ${activeScenario}`)}
              style={{
                background: "none", border: "none",
                color: T.teal, fontSize: 10, fontWeight: 600,
                cursor: "pointer", fontFamily: T.sans,
              }}
            >
              Discuss in chat &rarr;
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
