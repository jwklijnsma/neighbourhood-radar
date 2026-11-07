import { useState } from "react";
import { colorFor, fmtTime } from "../constants.js";

export default function Sidebar({
  point, radius, maxRadius, onRadius, onLocate,
  layers, enabled, data, onToggle, nearby, onSelect, attribution,
}) {
  return (
    <aside className="panel">
      <header>
        <h1><span className="dot" />Omgeving Live</h1>
        <p className="muted sub">Klik op de kaart om een punt te kiezen.</p>
      </header>

      <section className="where">
        <span className="coords">{point.lat.toFixed(4)}, {point.lon.toFixed(4)}</span>
        <LocateButton onLocate={onLocate} />
      </section>

      <section className="radius">
        <label htmlFor="radius">
          Straal <output>{radius} km</output>
        </label>
        <input
          id="radius"
          type="range"
          min="0.5"
          max={maxRadius}
          step="0.5"
          value={radius}
          onChange={(e) => onRadius(+e.target.value)}
        />
      </section>

      <section>
        <h2>Lagen</h2>
        <ul className="layers">
          {layers.map((m) => (
            <LayerRow
              key={m.name}
              meta={m}
              on={!!enabled[m.name]}
              state={data[m.name]}
              onToggle={onToggle}
            />
          ))}
        </ul>
      </section>

      <section className="nearby">
        <h2>Dichtbij {nearby.length > 0 && <span className="muted">({nearby.length})</span>}</h2>
        <ol>
          {nearby.length === 0 && <li className="empty muted">Niets binnen de straal.</li>}
          {nearby.slice(0, 40).map((f) => (
            <NearbyItem key={f.properties.id} f={f} onSelect={onSelect} />
          ))}
        </ol>
      </section>

      <footer className="muted">{attribution}</footer>
    </aside>
  );
}

function LocateButton({ onLocate }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!("geolocation" in navigator)) return null;
  const go = () => {
    setBusy(true);
    setFailed(false);
    navigator.geolocation.getCurrentPosition(
      (pos) => { setBusy(false); onLocate(pos.coords.latitude, pos.coords.longitude); },
      () => { setBusy(false); setFailed(true); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };
  return (
    <button type="button" onClick={go} disabled={busy} title={failed ? "Locatie niet beschikbaar" : undefined}>
      {busy ? "Zoeken…" : failed ? "Geen locatie" : "Mijn locatie"}
    </button>
  );
}

function LayerRow({ meta, on, state, onToggle }) {
  const count = on ? state?.features.length ?? 0 : null;
  let note = null;
  if (!meta.configured) note = <span className="note">Niet geconfigureerd</span>;
  else if (on && state?.error) note = <span className="note err">Bron niet bereikbaar</span>;
  return (
    <li>
      <label title={state?.error || meta.reason || undefined}>
        <input
          type="checkbox"
          checked={on}
          disabled={!meta.configured}
          onChange={(e) => onToggle(meta.name, e.target.checked)}
        />
        <span className="swatch" style={{ background: colorFor(meta.name) }} />
        <span>{meta.label}</span>
        <span className={"count" + (count ? " has" : "")}>
          {on && state?.loading && !state.features.length ? "…" : count ?? ""}
        </span>
        {note}
      </label>
    </li>
  );
}

function NearbyItem({ f, onSelect }) {
  const p = f.properties;
  return (
    <li style={{ "--c": colorFor(p.source) }}>
      <button type="button" onClick={() => onSelect(f)}>
        <span className="t">{p.title}</span>
        {p.detail && <span className="d">{p.detail}</span>}
        <span className="m">
          <span>{fmtTime(p.time)}</span>
          <span>{p.distance_km} km</span>
        </span>
      </button>
    </li>
  );
}
