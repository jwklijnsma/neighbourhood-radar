// Per-browser conveniences only (last point, radius, which layers are on).
const KEY = "neighbourhood-radar:v1";

export function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

export function savePrefs(prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable: fine */
  }
}
