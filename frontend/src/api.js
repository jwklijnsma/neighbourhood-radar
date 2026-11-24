/**
 * Talks to the FastAPI backend, or, in a static build (VITE_STATIC_API=1, used
 * for GitHub Pages), to the JSON snapshot written by scripts/export_static.py.
 * The static files hold the whole region, so distance filtering happens here.
 */
export const STATIC_API = import.meta.env.VITE_STATIC_API === "1";
const BASE = import.meta.env.BASE_URL; // "/static/" normally, "/<repo>/" on Pages

export function configUrl() {
  return STATIC_API ? `${BASE}api/config.json` : "/api/config";
}

export function layerUrl(name, { lat, lon, radius }) {
  if (STATIC_API) return `${BASE}api/layers/${encodeURIComponent(name)}.json`;
  const q = new URLSearchParams({ lat, lon, radius_km: radius });
  return `/api/layers/${encodeURIComponent(name)}?${q}`;
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
}

/** Same as the backend's _filter: keep features within radius, add distance_km, nearest first. */
export function filterFeatures(features, { lat, lon, radius }) {
  const out = [];
  for (const f of features) {
    const [flon, flat] = f.geometry.coordinates;
    const d = haversineKm(lat, lon, flat, flon);
    if (d <= radius) out.push({ ...f, properties: { ...f.properties, distance_km: Math.round(d * 100) / 100 } });
  }
  return out.sort((a, b) => a.properties.distance_km - b.properties.distance_km);
}
