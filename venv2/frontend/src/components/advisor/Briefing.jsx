import React, { useState, useEffect } from "react";
import { TrendingUp, AlertTriangle, Zap } from "lucide-react";
import { postBriefing } from "../../hooks/useApi";

const CARD_ICONS = [
  { Icon: AlertTriangle, color: "#EF4444", bg: "rgba(239,68,68,0.12)" },
  { Icon: TrendingUp,    color: "#F59E0B", bg: "rgba(245,158,11,0.12)" },
  { Icon: Zap,           color: "#10B981", bg: "rgba(16,185,129,0.12)" },
];

export default function Briefing({ T, onAskMore }) {
  const [cards, setCards] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    postBriefing()
      .then(data => {
        if (!cancelled) setCards(data.cards || []);
      })
      .catch(e => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", gap: 10, width: "100%" }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            flex: 1, height: 100, borderRadius: 10,
            background: T.navy3, border: `1px solid ${T.border}`,
            animation: "pulse-dot 1.5s ease-in-out infinite",
            opacity: 0.4,
          }} />
        ))}
      </div>
    );
  }

  if (error || !cards || cards.length === 0) return null;

  return (
    <div style={{
      display: "flex", gap: 10, width: "100%",
      flexDirection: "row",
    }}>
      {cards.map((card, i) => {
        const { Icon, color, bg } = CARD_ICONS[i % CARD_ICONS.length];
        return (
          <div key={i} style={{
            flex: 1, padding: "12px 14px", borderRadius: 10,
            background: T.navy3, border: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6,
            minWidth: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{
                width: 24, height: 24, borderRadius: 6,
                background: bg, display: "flex",
                alignItems: "center", justifyContent: "center", flexShrink: 0,
              }}>
                <Icon size={13} color={color} />
              </div>
              <div style={{
                fontSize: 12, fontWeight: 700, color: T.ink,
                lineHeight: 1.3, overflow: "hidden",
                display: "-webkit-box", WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
              }}>
                {card.headline}
              </div>
            </div>
            <div style={{
              fontSize: 11, color: T.inkMid, lineHeight: 1.5,
              overflow: "hidden", display: "-webkit-box",
              WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
            }}>
              {card.body}
            </div>
            {card.seed_question && (
              <button
                onClick={() => onAskMore(card.seed_question)}
                style={{
                  marginTop: "auto", paddingTop: 4,
                  background: "none", border: "none",
                  color: T.teal, fontSize: 10, fontWeight: 600,
                  cursor: "pointer", textAlign: "left",
                  fontFamily: T.sans,
                }}
              >
                Ask more &rarr;
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
