export const COLORS = {
  p2000: "#e03131",
  traffic: "#f08c00",
  transit: "#1c7ed6",
  trains: "#7048e8",
  aircraft: "#0ca678",
  satellites: "#ae3ec9",
  quakes: "#795548",
};

export const CATEGORY_LABEL = {
  fire: "Brandweer",
  ambulance: "Ambulance",
  police: "Politie",
  helicopter: "Traumaheli",
  boat: "KNRM",
};

export const DEFAULT_ON = new Set(["p2000", "traffic", "trains", "aircraft", "quakes"]);

// Layers left out of the "Dichtbij" list because they would flood it.
export const NOT_IN_NEARBY = new Set(["transit"]);

export const ACCENT = "#e8590c";

export function colorFor(name) {
  return COLORS[name] || "#888";
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins >= 0 && mins < 60) return mins <= 0 ? "zojuist" : `${mins} min geleden`;
  return d.toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
