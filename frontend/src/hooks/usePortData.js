import { useState, useEffect, useRef } from 'react';
import { fetchJSON } from '../api/client.js';

const POLL_INTERVAL = 5 * 60 * 1000; // 5 minutes

export function usePortList() {
  const [ports, setPorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON('/api/ports/')
      .then((data) => setPorts(data.ports || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { ports, loading, error };
}

export function useTopPorts(n = 20) {
  const [ports, setPorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetch = () => {
      fetchJSON(`/api/ports/top?n=${n}`)
        .then((data) => setPorts(data.ports || []))
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    };
    fetch();
    const timer = setInterval(fetch, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [n]);

  return { ports, loading, error };
}

export function usePortData(portName) {
  const [overview, setOverview] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!portName) {
      setOverview(null);
      setForecast(null);
      return;
    }

    const fetchData = () => {
      setLoading(true);
      const encodedPort = encodeURIComponent(portName);

      Promise.all([
        fetchJSON(`/api/ports/${encodedPort}/overview`),
        fetchJSON(`/api/ports/${encodedPort}/forecast?model=Prophet&horizon=7`),
      ])
        .then(([ov, fc]) => {
          setOverview(ov);
          setForecast(fc.forecast || []);
          setError(null);
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    };

    fetchData();
    timerRef.current = setInterval(fetchData, POLL_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [portName]);

  return { overview, forecast, loading, error };
}
