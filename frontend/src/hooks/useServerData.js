import { useState, useEffect, useCallback, useRef } from 'react';
import { REFRESH_INTERVAL_MS } from '../config';

export function useServerData(endpoint, startDate, endDate) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const debounceRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (startDate) params.set('start', startDate);
      if (endDate) params.set('end', endDate);
      const url = `/api/${endpoint}?${params}`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [endpoint, startDate, endDate]);

  // Track previous params to detect real changes vs polling
  const prevParamsRef = useRef({ endpoint, startDate, endDate });

  useEffect(() => {
    const prev = prevParamsRef.current;
    const paramsChanged = prev.endpoint !== endpoint || prev.startDate !== startDate || prev.endDate !== endDate;
    prevParamsRef.current = { endpoint, startDate, endDate };

    // Show loading immediately when dates change (before debounce)
    if (paramsChanged) {
      setLoading(true);
    }

    // Debounce fetches by 500ms so slider drags don't flood the server
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchData();
    }, paramsChanged ? 500 : 0);

    // Set up polling after initial debounced fetch
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => {
      clearTimeout(debounceRef.current);
      clearInterval(interval);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [fetchData]);

  return { data, loading, error };
}
