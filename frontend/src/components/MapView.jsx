import { useEffect, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import L from "leaflet";
import {
  Circle, CircleMarker, MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents,
} from "react-leaflet";
import { ACCENT, CATEGORY_LABEL, featureColor, fmtTime, safeImage, safeUrl } from "../constants.js";

const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
const TILE_URL = `https://{s}.basemaps.cartocdn.com/${dark ? "dark_all" : "light_all"}/{z}/{x}/{y}{r}.png`;
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

export default function MapView({ point, radius, fitRadius, layers, enabled, data, selected, onPick }) {
  return (
    <MapContainer className="map" center={[point.lat, point.lon]} zoom={11} preferCanvas>
      <TileLayer url={TILE_URL} attribution={TILE_ATTR} subdomains="abcd" maxZoom={19} />
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
      {layers
        .filter((m) => enabled[m.name])
        .flatMap((m) =>
          (data[m.name]?.features || []).map((f) => <FeatureMarker key={f.properties.id} f={f} />),
        )}
      <FlyToSelected selected={selected} />
    </MapContainer>
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
    root.render(<PopupBody p={selected.properties} />);
    const popup = L.popup({ maxWidth: 340 }).setLatLng([lat, lon]).setContent(node).openOn(map);
    popup.on("remove", () => setTimeout(() => root.unmount()));
  }, [map, selected]);
  return null;
}

const STATE_LABEL = {
  bridges: { open: "Brug open: weg dicht", planned: "Gepland" },
  roadworks: { now: "Nu bezig", soon: "Binnenkort" },
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
          {p.source === "webcams" ? "Bekijk op Windy" : p.source === "safety" ? "Bekijk op OpenStreetMap" : "Meer info"}
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

function badgeIcon(label, color, width = 38) {
  return L.divIcon({
    className: "",
    iconSize: [width, 22],
    iconAnchor: [width / 2, 11],
    html: `<div class="temp-badge" style="background:${color}">${label}</div>`,
  });
}

// Fixed glyphs per OSM category; never feed text.
const SAFETY_GLYPH = { aed: "♥", hospital: "H", fire_station: "B", police: "P", ambulance_station: "A" };

function waterIcon(level, color) {
  const n = Number(level);
  const label = Number.isFinite(n) ? `${n > 0 ? "+" : ""}${Math.round(n)}` : "?";
  return badgeIcon(label, color, 44);
}

function iconFor(p, color) {
  if (p.source === "aircraft" && p.heading != null) return planeIcon(p.heading, color);
  if (p.source === "weather" && p.temperature != null) return tempIcon(p.temperature, color);
  if (p.source === "webcams") return camIcon(color);
  if (p.source === "water" && p.level_cm != null) return waterIcon(p.level_cm, color);
  if (p.source === "safety") return badgeIcon(SAFETY_GLYPH[p.category] || "+", color, 22);
  if (p.source === "drips") return badgeIcon("▤", color, 22);
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
    <Popup maxWidth={340}>
      <PopupBody p={p} />
    </Popup>
  );
  if (icon) {
    return <Marker position={[lat, lon]} icon={icon}>{popup}</Marker>;
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
