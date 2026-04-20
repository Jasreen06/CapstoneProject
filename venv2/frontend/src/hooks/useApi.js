import { useState, useEffect, useCallback } from "react";

const BASE = process.env.REACT_APP_API_URL || "http://localhost:8004";

export function useFetch(path) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}${path}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}

export const usePortList        = ()              => useFetch("/api/ports");
export const useOverview        = (port)          => useFetch(port ? `/api/overview?port=${encodeURIComponent(port)}` : null);
export const useForecast        = (port, model)   => useFetch(port ? `/api/forecast?port=${encodeURIComponent(port)}&model=${model}&horizon=7` : null);
export const useTopPorts        = (n = 50)        => useFetch(`/api/top-ports?top_n=${n}`);
export const useModelComp       = ()              => useFetch("/api/model-comparison");
export const useChokepoints      = ()             => useFetch("/api/chokepoints");
export const useChokepointDetail = (name)         => useFetch(name ? `/api/chokepoints/overview?name=${encodeURIComponent(name)}` : null);
export const usePortChokepoints  = (port)         => useFetch(port ? `/api/port-chokepoints?port=${encodeURIComponent(port)}` : null);
export const useWeather          = (port)         => useFetch(port ? `/api/weather?port=${encodeURIComponent(port)}` : null);
export const useRiskAssessment   = (port)         => useFetch(port ? `/api/risk-assessment?port=${encodeURIComponent(port)}` : null);

export async function postChat(question, port, resetMemory = false) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, port: port || null, reset_memory: resetMemory }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function postFollowups(answer, port) {
  try {
    const res = await fetch(`${BASE}/api/chat/followups`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, port: port || null }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.followups || [];
  } catch {
    return [];
  }
}
