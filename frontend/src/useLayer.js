import { useEffect, useState } from "react";
import { STATIC_API, filterFeatures, layerUrl } from "./api.js";

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
      try {
        const r = await fetch(layerUrl(name, { lat, lon, radius }), { signal: controller.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const features = STATIC_API ? filterFeatures(data.features, { lat, lon, radius }) : data.features;
        setState({ features, error: data.status?.last_error || null, loading: false });
      } catch (e) {
        if (e.name === "AbortError") return;
        setState((s) => ({ ...s, error: String(e), loading: false }));
      }
    };
    load();
    const timer = setInterval(load, Math.max(STATIC_API ? 60 : 10, refreshSeconds) * 1000);
    return () => {
      clearInterval(timer);
      controller?.abort();
    };
  }, [name, enabled, lat, lon, radius, refreshSeconds]);

  return state;
}
