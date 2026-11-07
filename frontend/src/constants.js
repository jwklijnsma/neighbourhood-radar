export const COLORS = {
  p2000: "#e03131",
  traffic: "#f08c00",
  bridges: "#c2255c",
  roadworks: "#e67700",
  drips: "#f59f00",
  busalerts: "#1971c2",
  transit: "#4dabf7",
  trains: "#7048e8",
  webcams: "#495057",
  charging: "#37b24d",
  safety: "#d6336c",
  weather: "#0c8599",
  water: "#1864ab",
  air: "#2f9e44",
  aircraft: "#0ca678",
  airports: "#5f3dc4",
  satellites: "#ae3ec9",
  quakes: "#795548",
};

// LKI bands (Luchtmeetnet): green → purple, same steps as the official legend.
export const AIR_COLORS = {
  good: "#2f9e44",
  moderate: "#fab005",
  poor: "#f76707",
  bad: "#e03131",
  "very-bad": "#862e9c",
};

export const CHARGING_COLORS = {
  available: "#37b24d",
  occupied: "#f08c00",
  "out-of-order": "#868e96",
  unknown: "#74c0fc",
};

export const AIRCRAFT_COLORS = {
  emergency: "#e03131",
  helicopter: "#e8590c",
  military: "#5c940d",
  ground: "#868e96",
  airborne: "#0ca678",
};

export const CATEGORY_LABEL = {
  fire: "Brandweer",
  ambulance: "Ambulance",
  police: "Politie",
  helicopter: "Traumaheli",
  boat: "KNRM",
  available: "Vrij",
  occupied: "Bezet",
  "out-of-order": "Buiten werking",
};

export const DEFAULT_ON = new Set(["p2000", "traffic", "bridges", "busalerts", "trains", "aircraft", "quakes"]);

// Layers left out of the "Dichtbij" list: they're conditions or fixed things,
// not events, and would push the actual news off the list.
export const NOT_IN_NEARBY = new Set([
  "transit", "webcams", "weather", "air", "charging", "safety", "water", "airports",
]);

/** Aircraft only make the "nearby" list when they matter locally: emergencies,
 *  helicopters, or anything low enough to be landing, taking off or circling. */
export function inNearby(f) {
  const p = f.properties;
  if (NOT_IN_NEARBY.has(p.source)) return false;
  if (p.source !== "aircraft") return true;
  if (p.category === "emergency" || p.category === "helicopter") return true;
  return p.altitude_m != null && p.altitude_m < 1000;
}

export const ACCENT = "#e8590c";

export function colorFor(name) {
  return COLORS[name] || "#888";
}

/** Colour for one feature: some layers colour by state instead of by layer. */
export function featureColor(p) {
  if (p.source === "air") return AIR_COLORS[p.category] || COLORS.air;
  if (p.source === "charging") return CHARGING_COLORS[p.category] || COLORS.charging;
  if (p.source === "aircraft") return AIRCRAFT_COLORS[p.category] || COLORS.aircraft;
  return colorFor(p.source);
}

/** Feed values are untrusted: only plain https URLs are ever put in src/href. */
export function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

/** Images may also be inline PNGs (road sign pictures from NDW); nothing else. */
export function safeImage(url) {
  if (typeof url === "string" && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(url)) return url;
  return safeUrl(url);
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins >= 0 && mins < 60) return mins <= 0 ? "zojuist" : `${mins} min geleden`;
  if (mins < 0 && mins > -60) return `over ${-mins} min`;
  return d.toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
