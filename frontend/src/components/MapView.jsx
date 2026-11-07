import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import {
  Circle, CircleMarker, MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents,
} from "react-leaflet";
import { ACCENT, CATEGORY_LABEL, colorFor, fmtTime } from "../constants.js";

const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
const TILE_URL = `https://{s}.basemaps.cartocdn.com/${dark ? "dark_all" : "light_all"}/{z}/{x}/{y}{r}.png`;
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

export default function MapView({ point, radius, fitRadius, layers, enabled, data, selected, onPick }) {
  return (
    <MapContainer className="map" center={[point.lat, point.lon]} zoom={11}>
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
    L.popup().setLatLng([lat, lon]).setContent(popupNode(selected.properties)).openOn(map);
  }, [map, selected]);
  return null;
}

function PopupBody({ p }) {
  const meta = [CATEGORY_LABEL[p.category], fmtTime(p.time), p.distance_km != null ? `${p.distance_km} km` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="popup">
      <b>{p.title}</b>
      {p.detail && <div>{p.detail}</div>}
      <div className="muted">{meta}</div>
    </div>
  );
}

// For the imperative popup opened from the list: built with DOM APIs so feed
// text is set via textContent, never parsed as HTML.
function popupNode(p) {
  const root = document.createElement("div");
  root.className = "popup";
  const add = (tag, text, cls) => {
    if (!text) return;
    const n = document.createElement(tag);
    n.textContent = text;
    if (cls) n.className = cls;
    root.append(n);
  };
  add("b", p.title);
  add("div", p.detail);
  add("div", [CATEGORY_LABEL[p.category], fmtTime(p.time), p.distance_km != null ? `${p.distance_km} km` : null]
    .filter(Boolean).join(" · "), "muted");
  return root;
}

function planeIcon(heading, color) {
  const deg = Number(heading) || 0; // numeric only: this string becomes HTML
  return L.divIcon({
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<svg width="22" height="22" viewBox="0 0 24 24" style="transform:rotate(${deg}deg)"><path d="M12 2l2 7 7 4v2l-7-2-1 5 3 2v2l-4-1-4 1v-2l3-2-1-5-7 2v-2l7-4z" fill="${color}" stroke="#fff" stroke-width="1"/></svg>`,
  });
}

function FeatureMarker({ f }) {
  const p = f.properties;
  const [lon, lat] = f.geometry.coordinates;
  const color = colorFor(p.source);
  const icon = useMemo(
    () => (p.source === "aircraft" && p.heading != null ? planeIcon(p.heading, color) : null),
    [p.source, p.heading, color],
  );
  const popup = (
    <Popup>
      <PopupBody p={p} />
    </Popup>
  );
  if (icon) {
    return <Marker position={[lat, lon]} icon={icon}>{popup}</Marker>;
  }
  let r = 7;
  if (p.source === "quakes" && p.magnitude != null) r = 5 + Math.max(0, p.magnitude) * 4;
  if (p.source === "transit") r = 5;
  return (
    <CircleMarker
      center={[lat, lon]}
      radius={r}
      bubblingMouseEvents={false}
      pathOptions={{
        color: "#fff",
        weight: 1.5,
        fillColor: color,
        fillOpacity: p.source === "quakes" ? 0.55 : 0.9,
      }}
    >
      {popup}
    </CircleMarker>
  );
}
