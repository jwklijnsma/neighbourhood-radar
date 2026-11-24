"""UFO sightings, from a CSV of geocoded reports.

Default: the NUFORC "scrubbed" export (~80 000 reports, 1906-2014, ~14 MB) as
mirrored on GitHub by planetsig/ufo-reports. It's mostly US, but holds a few
dozen Dutch reports (Heerenveen, Drachten, Groningen, Emmen ...). It's
historical data, so it is fetched once a day.

Point OL_UFO_URL at your own CSV to use another set. Two layouts are accepted:
  * the headerless NUFORC layout: datetime, city, state, country, shape,
    duration (s), duration, comments, date posted, latitude, longitude
  * any CSV with a header row containing lat/latitude and lon/lng/longitude;
    optional columns: datetime/date/time, city/location/place, shape,
    comments/description/summary, duration, url/link, id
"""
from __future__ import annotations

import csv
import html
import io
from datetime import datetime

import httpx

from app.geo import valid_coord
from app.sources.base import Source, feature

# NUFORC writes dates as M/D/YYYY H:MM (US order).
DATE_FORMATS = ("%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
NUFORC_COLS = ["datetime", "city", "state", "country", "shape", "duration_s", "duration", "comments", "posted",
               "latitude", "longitude"]

ALIASES = {
    "lat": ("latitude", "lat"),
    "lon": ("longitude", "lon", "lng", "long"),
    "time": ("datetime", "date_time", "date", "time", "occurred"),
    "place": ("city", "location", "place"),
    "shape": ("shape",),
    "text": ("comments", "description", "summary", "text"),
    "duration": ("duration", "duration (hours/min)"),
    "url": ("url", "link"),
    "id": ("id",),
}

SHAPE_NL = {
    "light": "licht", "circle": "cirkel", "triangle": "driehoek", "fireball": "vuurbal", "disk": "schotel",
    "sphere": "bol", "oval": "ovaal", "formation": "formatie", "cigar": "sigaar", "cylinder": "cilinder",
    "chevron": "chevron", "diamond": "ruit", "rectangle": "rechthoek", "flash": "flits", "egg": "ei",
    "teardrop": "druppel", "cross": "kruis", "cone": "kegel", "changing": "veranderend", "other": "anders",
    "unknown": "onbekend",
}


def _clean(s) -> str:
    # NUFORC escapes commas as "&#44" (no semicolon); html.unescape handles that.
    return " ".join(html.unescape(s or "").split())


def _iso(raw: str) -> str | None:
    raw = (raw or "").strip()
    # NUFORC uses "24:00" for midnight.
    raw = raw.replace(" 24:00", " 00:00")
    for fmt in DATE_FORMATS:
        try:
            # Reports give the witness's local clock time, no zone: keep it naive
            # so the browser shows it as-is.
            return datetime.strptime(raw, fmt).isoformat()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def _rows(text: str):
    reader = csv.reader(io.StringIO(text))
    first = next(reader, None)
    if first is None:
        return
    lowered = [c.strip().lower() for c in first]
    if any(c in ("lat", "latitude") for c in lowered):
        cols = {}
        for key, names in ALIASES.items():
            for n in names:
                if n in lowered:
                    cols[key] = lowered.index(n)
                    break
        for row in reader:
            yield {k: row[i] if i < len(row) else "" for k, i in cols.items()}
        return
    for row in [first, *reader]:
        if len(row) < len(NUFORC_COLS):
            continue
        r = dict(zip(NUFORC_COLS, row))
        yield {
            "lat": r["latitude"], "lon": r["longitude"], "time": r["datetime"], "place": r["city"],
            "shape": r["shape"], "text": r["comments"], "duration": r["duration"],
            "_state": r["state"], "_country": r["country"],
        }


def _place(raw: str) -> str:
    # "heerenveen (netherlands)" -> "Heerenveen (netherlands)"
    raw = _clean(raw)
    return raw[:1].upper() + raw[1:] if raw else ""


def parse(text: str, box: tuple[float, float, float, float]) -> list[dict]:
    lamin, lomin, lamax, lomax = box
    out = []
    for n, r in enumerate(_rows(text)):
        lat, lon = r.get("lat"), r.get("lon")
        if not valid_coord(lat, lon):
            continue
        lat, lon = float(lat), float(lon)
        if not (lamin <= lat <= lamax and lomin <= lon <= lomax):
            continue
        # A few NUFORC rows carry a US/Canadian state but were geocoded to Europe.
        if r.get("_state", "").strip() and r.get("_country", "").strip() in ("", "us", "ca") and lon > -30:
            continue
        shape = _clean(r.get("shape")).lower()
        place = _place(r.get("place", ""))
        text_ = _clean(r.get("text"))
        duration = _clean(r.get("duration"))
        title = "UFO" + (f": {SHAPE_NL.get(shape, shape)}" if shape else "")
        url = r.get("url", "").strip()
        out.append(
            feature(
                source="ufo",
                fid=_clean(r.get("id")) or str(n),
                lat=lat,
                lon=lon,
                title=title,
                category=shape or "unknown",
                detail=" · ".join(p for p in [place, f"duur {duration}" if duration else "", text_] if p)[:400],
                time_iso=_iso(r.get("time", "")),
                url=url if url.startswith("https://") else None,
            )
        )
    out.sort(key=lambda f: f["properties"]["time"] or "", reverse=True)
    return out


class UFOSource(Source):
    name = "ufo"
    label = "UFO-waarnemingen"
    ttl = 24 * 3600
    refresh_hint = 3600
    attribution = "UFO: NUFORC"
    blocking_first_load = False  # ~14 MB download

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(self.settings.ufo_url, timeout=httpx.Timeout(120.0, connect=10.0))
        r.raise_for_status()
        return parse(r.content.decode("utf-8", errors="replace"), self.region_box)
