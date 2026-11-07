"""Weather station measurements from Buienradar's free JSON feed.

Buienradar asks for attribution and allows the free feed for non-commercial use.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

URL = "https://data.buienradar.nl/2.0/feed/json"
AMS = ZoneInfo("Europe/Amsterdam")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse(data: dict, box=None) -> list[dict]:
    out = []
    for s in ((data or {}).get("actual") or {}).get("stationmeasurements") or []:
        lat, lon = s.get("lat"), s.get("lon")
        if not valid_coord(lat, lon):
            continue
        lat, lon = float(lat), float(lon)
        if box and not in_bbox(lat, lon, box):
            continue
        temp = _num(s.get("temperature"))
        parts = []
        if s.get("weatherdescription"):
            parts.append(s["weatherdescription"])
        if s.get("windspeedBft") is not None and s.get("winddirection"):
            parts.append(f"wind {s['winddirection']} {s['windspeedBft']} Bft")
        if _num(s.get("rainFallLastHour")):
            parts.append(f"{s['rainFallLastHour']} mm regen afgelopen uur")
        if _num(s.get("humidity")) is not None:
            parts.append(f"{round(_num(s['humidity']))}% vocht")
        ts = s.get("timestamp")
        if ts:
            try:  # Buienradar timestamps are local time without offset
                ts = datetime.fromisoformat(ts).replace(tzinfo=AMS).isoformat()
            except ValueError:
                ts = None
        name = (s.get("stationname") or "").removeprefix("Meetstation ").strip()
        out.append(
            feature(
                source="weather",
                fid=str(s.get("stationid", name)),
                lat=lat,
                lon=lon,
                title=f"{name}: {temp:.1f} °C" if temp is not None else name,
                category="station",
                detail=" · ".join(parts),
                time_iso=ts,
                temperature=temp,
                wind_bft=s.get("windspeedBft"),
                wind_deg=s.get("winddirectiondegrees"),
            )
        )
    return out


class WeatherSource(Source):
    name = "weather"
    label = "Weer (Buienradar)"
    ttl = 600   # stations report every 10 minutes
    refresh_hint = 600
    attribution = "Weer: Buienradar.nl"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(URL)
        r.raise_for_status()
        return parse(r.json(), self.region_box)
