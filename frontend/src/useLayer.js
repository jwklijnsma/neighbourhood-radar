import { useEffect, useState } from "react";

/**
 * Polls one layer from the backend while it's enabled.
 * Refetches immediately when the point or radius changes and drops responses
 * that arrive after the query changed (AbortController).
 */
export function useLayer(name, { enabled, lat, lon, radius, refreshSeconds }) {
  const [state, setState] = useState({ features: [], error: null, loading: false });

  useEffect(() => {
    if (!enabled) {
      setState({ features: [], error: null, loading: false });
      return undefined;
    }
    let controller;
    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      setState((s) => ({ ...s, loading: true }));
      const q = new URLSearchParams({ lat, lon, radius_km: radius });
      try {
        const r = await fetch(`/api/layers/${encodeURIComponent(name)}?${q}`, { signal: controller.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setState({ features: data.features, error: data.status?.last_error || null, loading: false });
      } catch (e) {
        if (e.name === "AbortError") return;
        setState((s) => ({ ...s, error: String(e), loading: false }));
      }
    };
    load();
    const timer = setInterval(load, Math.max(10, refreshSeconds) * 1000);
    return () => {
      clearInterval(timer);
      controller?.abort();
    };
  }, [name, enabled, lat, lon, radius, refreshSeconds]);

  return state;
}
