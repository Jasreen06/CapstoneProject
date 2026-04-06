import { useState, useEffect, useRef } from 'react';
import { createSSE, fetchJSON } from '../api/client.js';

/**
 * SSE hook for live vessel data.
 * Maintains a Map of vessels keyed by MMSI.
 */
export function useVessels({ vesselType, navStatus } = {}) {
  const [vessels, setVessels] = useState(new Map());
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const sseRef = useRef(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (vesselType) params.set('vessel_type', vesselType);
    if (navStatus !== undefined) params.set('nav_status', navStatus);

    const endpoint = `/api/vessels/stream${params.toString() ? `?${params}` : ''}`;
    const sse = createSSE(endpoint);
    sseRef.current = sse;

    sse.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    sse.addEventListener('vessels', (e) => {
      try {
        const data = JSON.parse(e.data);
        const newMap = new Map();
        for (const v of data.vessels || []) {
          if (v.mmsi) newMap.set(v.mmsi, v);
        }
        setVessels(newMap);
      } catch {
        // ignore parse errors
      }
    });

    sse.onerror = () => {
      setIsConnected(false);
      setError('Connection lost — reconnecting...');
    };

    return () => {
      sse.close();
      sseRef.current = null;
      setIsConnected(false);
    };
  }, [vesselType, navStatus]);

  const vesselList = Array.from(vessels.values());
  return { vessels, vesselList, isConnected, error };
}

/**
 * Hook to fetch a single vessel's full details.
 */
export function useVessel(mmsi) {
  const [vessel, setVessel] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!mmsi) {
      setVessel(null);
      return;
    }
    setLoading(true);
    fetchJSON(`/api/vessels/${mmsi}`)
      .then(setVessel)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [mmsi]);

  return { vessel, loading, error };
}
