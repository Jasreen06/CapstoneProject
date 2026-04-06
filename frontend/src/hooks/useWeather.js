import { useState, useEffect, useRef } from 'react';
import { fetchJSON } from '../api/client.js';

const POLL_INTERVAL = 15 * 60 * 1000; // 15 minutes

export function useWeather(portName) {
  const [weather, setWeather] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!portName) {
      setWeather(null);
      return;
    }

    const fetchWeather = () => {
      setLoading(true);
      fetchJSON(`/api/weather/${encodeURIComponent(portName)}`)
        .then((data) => {
          setWeather(data);
          setError(null);
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    };

    fetchWeather();
    timerRef.current = setInterval(fetchWeather, POLL_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [portName]);

  return { weather, loading, error };
}
