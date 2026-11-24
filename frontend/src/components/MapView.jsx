import { useEffect, useMemo, useRef } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import L from "leaflet";
import {
  Circle, CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, useMap, useMapEvents,
} from "react-leaflet";
import { ACCENT, CATEGORY_LABEL, featureColor, fmtTime, safeImage, safeUrl } from "../constants.js";


export default function MapView({ point, radius, fitRadius, layers, enabled, data, selected, onPick, tiles }) {
  return (
    <MapContainer className="map" center={[point.lat, point.lon]} zoom={11} preferCanvas>
      <TileLayer url={tiles.url} attribution={tiles.attribution} subdomains="abcd" maxZoom={19} />
      <ClickToPick onPick={onPick} />
      <FitToRadius point={point} radius={fitRadius} />
      <Circle
        center={[point.lat, point.lon]}
        radius={radius * 1000}
        pathOptions={{ color: ACCENT, weight: 1.5, fillOpacity: 0.04 }}
        interactive={false}
      />
      <CircleMarker
        center={[point.lat, point.lon]}
        radius={6}
        pathOptions={{ color: "#fff", weight: 2, fillColor: ACCENT, fillOpacity: 1 }}
        interactive={false}
      />
      {enabled.aircraft &&
        (data.aircraft?.features || [])
          .filter((f) => Array.isArray(f.properties.trail) && f.properties.trail.length > 1)
          .map((f) => <Trail key={`trail-${f.properties.id}`} f={f} />)}
      {layers
        .filter((m) => enabled[m.name])
        .flatMap((m) =>
          (data[m.name]?.features || []).map((f) => <FeatureMarker key={f.properties.id} f={f} />),
        )}
      <FlyToSelected selected={selected} />
    </MapContainer>
  );
}

/** Flown path of one aircraft, ending at its current position. */
function Trail({ f }) {
  const p = f.properties;
  const [lon, lat] = f.geometry.coordinates;
  const pts = p.trail
    .filter((pt) => Array.isArray(pt) && Number.isFinite(pt[0]) && Number.isFinite(pt[1]))
    .concat([[lat, lon]]);
  return (
    <Polyline
      positions={pts}
      interactive={false}
      pathOptions={{ color: featureColor(p), weight: 2, opacity: 0.55, dashArray: p.category === "ground" ? "2 4" : null }}
    />
  );
}

function ClickToPick({ onPick }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

/**
 * Radius changed (settled): zoom so the whole circle is visible.
 * Point changed: only pan, and only if it left the view (e.g. "Mijn locatie").
 */
function FitToRadius({ point, radius }) {
  const map = useMap();
  const pointRef = useRef(point);
  pointRef.current = point;
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const { lat, lon } = pointRef.current;
    map.fitBounds(L.latLng(lat, lon).toBounds(radius * 2000), { padding: [20, 20], maxZoom: 15 });
  }, [map, radius]);
  useEffect(() => {
    const ll = L.latLng(point.lat, point.lon);
    if (!map.getBounds().contains(ll)) map.setView(ll, Math.max(map.getZoom(), 12));
  }, [map, point]);
  return null;
}

function FlyToSelected({ selected }) {
  const map = useMap();
  useEffect(() => {
    if (!selected) return;
    const [lon, lat] = selected.geometry.coordinates;
    map.setView([lat, lon], Math.max(map.getZoom(), 13));
    // Same React component as marker popups, rendered into a detached node.
    const node = document.createElement("div");
    const root = createRoot(node);
    // Render before Leaflet measures the popup, or it sizes itself to an empty node.
    flushSync(() => root.render(<PopupBody p={selected.properties} />));
    const popup = L.popup({ maxWidth: 340, minWidth: 220 }).setLatLng([lat, lon]).setContent(node).openOn(map);
    popup.on("remove", () => setTimeout(() => root.unmount()));
  }, [map, selected]);
  return null;
}

const LINK_LABEL = {
  webcams: "Bekijk op Windy",
  safety: "Bekijk op OpenStreetMap",
  aircraft: "Volg deze vlucht",
};

const STATE_LABEL = {
  bridges: { open: "Brug open: weg dicht", planned: "Gepland" },
  roadworks: { now: "Nu bezig", soon: "Binnenkort" },
  aircraft: {
    emergency: "Noodsituatie", helicopter: "Helikopter", military: "Militair",
    ground: "Aan de grond", airborne: "In de lucht",
  },
};

function PopupBody({ p }) {
  const meta = [
    CATEGORY_LABEL[p.category] || STATE_LABEL[p.source]?.[p.category],
    fmtTime(p.time),
    p.distance_km != null ? `${p.distance_km} km` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const image = safeImage(p.image);
  const link = safeUrl(p.url);
  return (
    <div className="popup">
      {image && (
        <img
          className={p.source === "drips" ? "popup-img drip" : "popup-img"}
          src={image}
          alt={p.title}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
      )}
      <b>{p.title}</b>
      {p.detail && <div>{p.detail}</div>}
      <div className="muted">{meta}</div>
      {link && (
        <a href={link} target="_blank" rel="noopener noreferrer">
          {LINK_LABEL[p.source] || "Meer info"}
        </a>
      )}
    </div>
  );
}

// divIcon html is a string: only numbers and our own constants go into it.
function planeIcon(heading, color) {
  const deg = Number(heading) || 0;
  return L.divIcon({
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<svg width="22" height="22" viewBox="0 0 24 24" style="transform:rotate(${deg}deg)"><path d="M12 2l2 7 7 4v2l-7-2-1 5 3 2v2l-4-1-4 1v-2l3-2-1-5-7 2v-2l7-4z" fill="${color}" stroke="#fff" stroke-width="1"/></svg>`,
  });
}

// Top-down helicopter: rotor disc, body and tail boom.
function heliIcon(heading, color) {
  const deg = Number(heading) || 0;
  return L.divIcon({
    className: "",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    html: `<svg width="24" height="24" viewBox="0 0 24 24" style="transform:rotate(${deg}deg)"><circle cx="12" cy="10" r="8" fill="none" stroke="${color}" stroke-width="1.5" stroke-dasharray="3 2"/><path d="M12 5c2 0 3 2 3 5s-1 4-3 4-3-1-3-4 1-5 3-5zM11.3 14h1.4v7h-1.4zM9.5 20.5h5v1.2h-5z" fill="${color}" stroke="#fff" stroke-width=".8"/></svg>`,
  });
}

function tempIcon(t, color) {
  const n = Number(t);
  const label = Number.isFinite(n) ? `${Math.round(n)}°` : "?";
  return L.divIcon({
    className: "",
    iconSize: [38, 22],
    iconAnchor: [19, 11],
    html: `<div class="temp-badge" style="background:${color}">${label}</div>`,
  });
}

function camIcon(color) {
  return L.divIcon({
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<svg width="22" height="22" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="${color}" stroke="#fff" stroke-width="1.5"/><path d="M6 9h8v6H6zM14 11l4-2v6l-4-2z" fill="#fff"/></svg>`,
  });
}

// Flying saucer: dome, disc and three lights.
function ufoIcon(color) {
  return L.divIcon({
    className: "",
    iconSize: [26, 20],
    iconAnchor: [13, 10],
    html: `<svg width="26" height="20" viewBox="0 0 26 20"><path d="M8 9a5 5 0 0 1 10 0z" fill="#fff" stroke="${color}" stroke-width="1.5"/><ellipse cx="13" cy="11" rx="12" ry="4" fill="${color}" stroke="#fff" stroke-width="1.2"/><circle cx="7" cy="11.5" r="1" fill="#fff"/><circle cx="13" cy="12.5" r="1" fill="#fff"/><circle cx="19" cy="11.5" r="1" fill="#fff"/><path d="M10 15l-2 4M16 15l2 4" stroke="${color}" stroke-width="1" opacity=".6"/></svg>`,
  });
}

function badgeIcon(label, color, width = 38) {
  return L.divIcon({
    className: "",
    iconSize: [width, 22],
    iconAnchor: [width / 2, 11],
    html: `<div class="temp-badge" style="background:${color}">${label}</div>`,
  });
}

const AIRPORT_GLYPH = { heliport: "H", seaplane_base: "≈", balloonport: "○" };

// Fixed glyphs per OSM category; never feed text.
const SAFETY_GLYPH = { aed: "♥", hospital: "H", fire_station: "B", police: "P", ambulance_station: "A" };

function waterIcon(level, color) {
  const n = Number(level);
  const label = Number.isFinite(n) ? `${n > 0 ? "+" : ""}${Math.round(n)}` : "?";
  return badgeIcon(label, color, 44);
}

function iconFor(p, color) {
  if (p.source === "aircraft" && p.category === "helicopter") return heliIcon(p.heading, color);
  if (p.source === "aircraft") {
    const icon = planeIcon(p.heading, color);
    // Emergencies pulse so they stand out among dozens of aircraft.
    if (p.category === "emergency") icon.options.className = "pulse";
    return icon;
  }
  if (p.source === "airports") return badgeIcon(AIRPORT_GLYPH[p.category] || "✈", color, 22);
  if (p.source === "weather" && p.temperature != null) return tempIcon(p.temperature, color);
  if (p.source === "webcams") return camIcon(color);
  if (p.source === "water" && p.level_cm != null) return waterIcon(p.level_cm, color);
  if (p.source === "safety") return badgeIcon(SAFETY_GLYPH[p.category] || "+", color, 22);
  if (p.source === "drips") return badgeIcon("▤", color, 22);
  if (p.source === "ufo") return ufoIcon(color);
  return null;
}

// Planned/not-yet-active things are drawn hollow.
const HOLLOW = { bridges: "planned", roadworks: "soon" };

function FeatureMarker({ f }) {
  const p = f.properties;
  const [lon, lat] = f.geometry.coordinates;
  const color = featureColor(p);
  const icon = useMemo(() => iconFor(p, color), [p, color]);
  const popup = (
    <Popup maxWidth={340} minWidth={220}>
      <PopupBody p={p} />
    </Popup>
  );
  if (icon) {
    const front = p.category === "emergency" ? 1000 : 0;
    return <Marker position={[lat, lon]} icon={icon} zIndexOffset={front}>{popup}</Marker>;
  }
  let r = 7;
  if (p.source === "quakes" && p.magnitude != null) r = 5 + Math.max(0, p.magnitude) * 4;
  if (p.source === "transit") r = 5;
  if (p.source === "air") r = 9;
  if (p.source === "charging") r = p.fast ? 7 : 5;
  const hollow = HOLLOW[p.source] === p.category;
  return (
    <CircleMarker
      center={[lat, lon]}
      radius={r}
      bubblingMouseEvents={false}
      pathOptions={{
        color: hollow ? color : "#fff",
        weight: hollow ? 2.5 : 1.5,
        fillColor: color,
        fillOpacity: hollow ? 0.15 : p.source === "quakes" ? 0.55 : 0.9,
      }}
    >
      {popup}
    </CircleMarker>
  );
}
