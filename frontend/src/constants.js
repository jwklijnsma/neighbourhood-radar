export const COLORS = {
  p2000: "#e03131",
  traffic: "#f08c00",
  bridges: "#c2255c",
  roadworks: "#e67700",
  busalerts: "#1971c2",
  transit: "#4dabf7",
  trains: "#7048e8",
  webcams: "#495057",
  weather: "#0c8599",
  air: "#2f9e44",
  aircraft: "#0ca678",
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

export const CATEGORY_LABEL = {
  fire: "Brandweer",
  ambulance: "Ambulance",
  police: "Politie",
  helicopter: "Traumaheli",
  boat: "KNRM",
};

export const DEFAULT_ON = new Set(["p2000", "traffic", "bridges", "busalerts", "trains", "aircraft", "quakes"]);

// Layers left out of the "Dichtbij" list: they're conditions or fixed things,
// not events, and would push the actual news off the list.
export const NOT_IN_NEARBY = new Set(["transit", "webcams", "weather", "air"]);

export const ACCENT = "#e8590c";

export function colorFor(name) {
  return COLORS[name] || "#888";
}

/** Colour for one feature: some layers colour by state instead of by layer. */
export function featureColor(p) {
  if (p.source === "air") return AIR_COLORS[p.category] || COLORS.air;
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

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins >= 0 && mins < 60) return mins <= 0 ? "zojuist" : `${mins} min geleden`;
  if (mins < 0 && mins > -60) return `over ${-mins} min`;
  return d.toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
