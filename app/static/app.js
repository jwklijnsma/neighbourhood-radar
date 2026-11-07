"use strict";
// All feed text is untrusted: everything goes into the DOM via textContent, never innerHTML.

const COLORS = {
  p2000: "#e03131",
  traffic: "#f08c00",
  transit: "#1c7ed6",
  trains: "#7048e8",
  aircraft: "#0ca678",
  satellites: "#ae3ec9",
  quakes: "#795548",
};
const CATEGORY_LABEL = {
  fire: "Brandweer", ambulance: "Ambulance", police: "Politie", helicopter: "Traumaheli", boat: "KNRM",
};
const DEFAULT_ON = new Set(["p2000", "traffic", "trains", "aircraft", "quakes"]);
const STORE_KEY = "omgeving-live:v1";

const state = {
  lat: 0, lon: 0, radius: 5,
  layers: {},          // name -> {meta, group, timer, features, enabled}
  centerMarker: null, circle: null,
};

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch { return {}; }
}
function savePrefs() {
  const enabled = Object.fromEntries(Object.entries(state.layers).map(([k, l]) => [k, l.enabled]));
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ lat: state.lat, lon: state.lon, radius: state.radius, enabled }));
  } catch { /* storage unavailable; fine */ }
}

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) n.append(k);
  return n;
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins >= 0 && mins < 60) return mins <= 0 ? "zojuist" : `${mins} min geleden`;
  return d.toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function popupFor(p) {
  const meta = [CATEGORY_LABEL[p.category], fmtTime(p.time), p.distance_km != null ? `${p.distance_km} km` : null]
    .filter(Boolean).join(" · ");
  return el("div", {}, el("b", {}, p.title || ""), p.detail ? el("div", {}, p.detail) : null, el("div", { class: "muted" }, meta));
}

function markerFor(f, color) {
  const [lon, lat] = f.geometry.coordinates;
  const p = f.properties;
  if (p.source === "aircraft" && p.heading != null) {
    const icon = L.divIcon({
      className: "",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
      html: `<svg class="plane" width="22" height="22" viewBox="0 0 24 24" style="transform:rotate(${Number(p.heading) || 0}deg)">
        <path d="M12 2l2 7 7 4v2l-7-2-1 5 3 2v2l-4-1-4 1v-2l3-2-1-5-7 2v-2l7-4z" fill="${color}" stroke="#fff" stroke-width="1"/></svg>`,
    });
    return L.marker([lat, lon], { icon });
  }
  let radius = 7;
  if (p.source === "quakes" && p.magnitude != null) radius = 5 + Math.max(0, p.magnitude) * 4;
  if (p.source === "transit") radius = 5;
  return L.circleMarker([lat, lon], {
    radius, color: "#fff", weight: 1.5, fillColor: color, fillOpacity: p.source === "quakes" ? 0.55 : 0.9,
  });
}

async function fetchLayer(name) {
  const layer = state.layers[name];
  if (!layer || !layer.enabled) return;
  const q = new URLSearchParams({ lat: state.lat, lon: state.lon, radius_km: state.radius });
  try {
    const r = await fetch(`/api/layers/${encodeURIComponent(name)}?${q}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    layer.features = data.features;
    layer.error = data.status.last_error;
    layer.group.clearLayers();
    for (const f of data.features) {
      markerFor(f, COLORS[name] || "#888").bindPopup(() => popupFor(f.properties)).addTo(layer.group);
    }
  } catch (e) {
    layer.error = String(e);
  }
  renderLayers();
  renderNearby();
}

function schedule(name) {
  const layer = state.layers[name];
  clearInterval(layer.timer);
  if (!layer.enabled) return;
  fetchLayer(name);
  layer.timer = setInterval(() => fetchLayer(name), Math.max(10, layer.meta.refresh) * 1000);
}

function renderLayers() {
  const ul = document.getElementById("layers");
  ul.replaceChildren();
  for (const [name, l] of Object.entries(state.layers)) {
    const cb = el("input", { type: "checkbox" });
    cb.checked = l.enabled;
    cb.disabled = !l.meta.configured;
    cb.addEventListener("change", () => toggleLayer(name, cb.checked));
    const n = l.enabled ? l.features.length : "";
    const count = el("span", { class: "count" + (n ? " has" : "") }, String(n));
    const label = el("label", {}, cb,
      el("span", { class: "swatch", style: `background:${COLORS[name] || "#888"}` }),
      el("span", {}, l.meta.label), count);
    if (!l.meta.configured) label.append(el("span", { class: "note" }, "Niet geconfigureerd"));
    else if (l.enabled && l.error) label.append(el("span", { class: "note err" }, "Bron niet bereikbaar"));
    if (!l.meta.configured && l.meta.reason) label.title = l.meta.reason;
    if (l.error) label.title = l.error;
    ul.append(el("li", {}, label));
  }
}

function renderNearby() {
  const all = [];
  for (const [name, l] of Object.entries(state.layers)) {
    if (!l.enabled || name === "transit") continue; // buses would flood the list
    for (const f of l.features) all.push(f);
  }
  all.sort((a, b) => a.properties.distance_km - b.properties.distance_km);
  const list = document.getElementById("nearby");
  list.replaceChildren();
  document.getElementById("nearCount").textContent = all.length ? `(${all.length})` : "";
  for (const f of all.slice(0, 40)) {
    const p = f.properties;
    const li = el("li", { style: `--c:${COLORS[p.source] || "#888"}` },
      el("div", { class: "t" }, p.title || ""),
      p.detail ? el("div", {}, p.detail) : null,
      el("div", { class: "m" }, el("span", {}, fmtTime(p.time)), el("span", {}, `${p.distance_km} km`)));
    li.addEventListener("click", () => {
      const [lon, lat] = f.geometry.coordinates;
      map.setView([lat, lon], Math.max(map.getZoom(), 13));
      L.popup().setLatLng([lat, lon]).setContent(popupFor(p)).openOn(map);
    });
    list.append(li);
  }
  if (!all.length) list.append(el("li", { class: "muted", style: "cursor:default" }, "Niets binnen de straal."));
}

function toggleLayer(name, on) {
  const l = state.layers[name];
  l.enabled = on;
  if (on) l.group.addTo(map); else { l.group.remove(); l.features = []; }
  schedule(name);
  renderLayers(); renderNearby(); savePrefs();
}

function setPoint(lat, lon, refetch = true) {
  state.lat = +lat.toFixed(5); state.lon = +lon.toFixed(5);
  document.getElementById("coords").textContent = `${state.lat.toFixed(4)}, ${state.lon.toFixed(4)}`;
  state.centerMarker.setLatLng([lat, lon]);
  state.circle.setLatLng([lat, lon]).setRadius(state.radius * 1000);
  savePrefs();
  if (refetch) Object.keys(state.layers).forEach(schedule);
}

let map;
let debounce;

async function init() {
  const cfg = await (await fetch("/api/config")).json();
  const prefs = loadPrefs();
  state.lat = prefs.lat ?? cfg.center.lat;
  state.lon = prefs.lon ?? cfg.center.lon;
  state.radius = Math.min(prefs.radius ?? 5, cfg.max_query_radius_km);

  const radius = document.getElementById("radius");
  radius.max = Math.min(50, cfg.max_query_radius_km);
  radius.value = state.radius;
  document.getElementById("radiusOut").textContent = `${state.radius} km`;

  map = L.map("map", { zoomControl: true }).setView([state.lat, state.lon], 11);
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  L.tileLayer(`https://{s}.basemaps.cartocdn.com/${dark ? "dark_all" : "light_all"}/{z}/{x}/{y}{r}.png`, {
    maxZoom: 19, subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
  }).addTo(map);

  state.circle = L.circle([state.lat, state.lon], {
    radius: state.radius * 1000, color: "#e8590c", weight: 1.5, fillOpacity: 0.04, interactive: false,
  }).addTo(map);
  state.centerMarker = L.circleMarker([state.lat, state.lon], {
    radius: 6, color: "#fff", weight: 2, fillColor: "#e8590c", fillOpacity: 1,
  }).addTo(map);

  const attributions = [];
  for (const meta of cfg.layers) {
    const enabled = meta.configured && (prefs.enabled ? !!prefs.enabled[meta.name] : DEFAULT_ON.has(meta.name));
    state.layers[meta.name] = { meta, enabled, features: [], group: L.layerGroup(), timer: null, error: null };
    if (enabled) state.layers[meta.name].group.addTo(map);
    if (meta.attribution) attributions.push(meta.attribution);
  }
  document.getElementById("attrib").textContent = attributions.join(" · ");

  map.on("click", (e) => setPoint(e.latlng.lat, e.latlng.lng));
  radius.addEventListener("input", () => {
    state.radius = +radius.value;
    document.getElementById("radiusOut").textContent = `${state.radius} km`;
    state.circle.setRadius(state.radius * 1000);
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      map.fitBounds(state.circle.getBounds(), { padding: [20, 20] });
      setPoint(state.lat, state.lon);
    }, 350);
  });
  document.getElementById("locate").addEventListener("click", () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => { setPoint(pos.coords.latitude, pos.coords.longitude); map.setView([state.lat, state.lon], 13); },
      () => alert("Locatie niet beschikbaar."),
      { enableHighAccuracy: true, timeout: 10000 });
  });

  renderLayers();
  setPoint(state.lat, state.lon);
}

init().catch((e) => {
  document.getElementById("coords").textContent = "Backend niet bereikbaar: " + e;
});
