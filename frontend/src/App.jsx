import { useCallback, useEffect, useMemo, useState } from "react";
import { DEFAULT_ON, NOT_IN_NEARBY, inNearby } from "./constants.js";
import { loadPrefs, savePrefs } from "./prefs.js";
import { useLayer } from "./useLayer.js";
import Sidebar from "./components/Sidebar.jsx";
import MapView from "./components/MapView.jsx";

export default function App() {
  const [cfg, setCfg] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setCfg)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="splash">Backend niet bereikbaar: {error}</div>;
  if (!cfg) return <div className="splash">Laden…</div>;
  return <Live cfg={cfg} />;
}

/** Calls useLayer for one layer and reports the result upward; renders nothing. */
function LayerFeed({ meta, enabled, lat, lon, radius, onData }) {
  const data = useLayer(meta.name, { enabled, lat, lon, radius, refreshSeconds: meta.refresh });
  useEffect(() => onData(meta.name, data), [meta.name, data, onData]);
  return null;
}

function Live({ cfg }) {
  const prefs = useMemo(loadPrefs, []);
  const maxRadius = Math.min(50, cfg.max_query_radius_km);

  const [point, setPoint] = useState({
    lat: prefs.lat ?? cfg.center.lat,
    lon: prefs.lon ?? cfg.center.lon,
  });
  // `radiusInput` follows the slider; `radius` is what we query with (debounced).
  const [radiusInput, setRadiusInput] = useState(Math.min(prefs.radius ?? 5, maxRadius));
  const [radius, setRadius] = useState(radiusInput);
  const [enabled, setEnabled] = useState(() =>
    Object.fromEntries(
      cfg.layers.map((m) => [
        m.name,
        m.configured && (prefs.enabled ? !!prefs.enabled[m.name] : DEFAULT_ON.has(m.name)),
      ]),
    ),
  );
  const [data, setData] = useState({});
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => setRadius(radiusInput), 350);
    return () => clearTimeout(t);
  }, [radiusInput]);

  useEffect(() => {
    savePrefs({ lat: point.lat, lon: point.lon, radius, enabled });
  }, [point, radius, enabled]);

  const onData = useCallback((name, d) => setData((prev) => ({ ...prev, [name]: d })), []);

  const choosePoint = useCallback((lat, lon) => {
    setPoint({ lat: +lat.toFixed(5), lon: +lon.toFixed(5) });
    setSelected(null);
  }, []);

  const toggle = useCallback((name, on) => setEnabled((e) => ({ ...e, [name]: on })), []);

  const nearby = useMemo(() => {
    const all = [];
    for (const m of cfg.layers) {
      if (!enabled[m.name] || NOT_IN_NEARBY.has(m.name)) continue;
      all.push(...(data[m.name]?.features || []).filter(inNearby));
    }
    return all.sort((a, b) => a.properties.distance_km - b.properties.distance_km);
  }, [cfg.layers, enabled, data]);

  const attribution = cfg.layers.map((m) => m.attribution).filter(Boolean).join(" · ");

  return (
    <div className="app">
      {cfg.layers.map((m) => (
        <LayerFeed
          key={m.name}
          meta={m}
          enabled={!!enabled[m.name]}
          lat={point.lat}
          lon={point.lon}
          radius={radius}
          onData={onData}
        />
      ))}
      <Sidebar
        point={point}
        radius={radiusInput}
        maxRadius={maxRadius}
        onRadius={setRadiusInput}
        onLocate={choosePoint}
        layers={cfg.layers}
        enabled={enabled}
        data={data}
        onToggle={toggle}
        nearby={nearby}
        onSelect={setSelected}
        attribution={attribution}
        demo={!!cfg.demo}
      />
      <MapView
        point={point}
        radius={radiusInput}
        fitRadius={radius}
        layers={cfg.layers}
        enabled={enabled}
        data={data}
        selected={selected}
        onPick={choosePoint}
        tiles={cfg.tiles}
      />
    </div>
  );
}
