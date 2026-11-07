"""Air quality (LKI, the Dutch 1-11 air quality index) from Luchtmeetnet.

The API has no bulk "stations with coordinates" call and allows 100 requests per
5 minutes, so station locations are crawled slowly (one request every ~3.2 s)
and cached for a week. After that only the stations inside the region are
polled, once an hour, which is how often the data changes.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

API = "https://api.luchtmeetnet.nl/open_api"
MIN_INTERVAL = 3.2       # seconds between requests: < 100 per 5 minutes
STATIONS_TTL = 7 * 24 * 3600

# LKI 1-11 -> (category, Dutch label)
def lki_band(v: float) -> tuple[str, str]:
    if v <= 3:
        return "good", "goed"
    if v <= 6:
        return "moderate", "matig"
    if v <= 8:
        return "poor", "onvoldoende"
    if v <= 10:
        return "bad", "slecht"
    return "very-bad", "zeer slecht"


def parse_station(number: str, data: dict) -> dict | None:
    d = (data or {}).get("data") or {}
    coords = ((d.get("geometry") or {}).get("coordinates")) or []
    if len(coords) < 2 or not valid_coord(coords[1], coords[0]):
        return None
    return {
        "number": number,
        "lat": float(coords[1]),
        "lon": float(coords[0]),
        "name": d.get("location") or number,
        "municipality": d.get("municipality") or "",
    }


def latest_lki(data: dict) -> tuple[float, str] | None:
    rows = (data or {}).get("data") or []
    if not rows:
        return None
    row = rows[0]
    try:
        return float(row["value"]), row.get("timestamp_measured")
    except (KeyError, TypeError, ValueError):
        return None


def to_feature(st: dict, lki: float, ts: str | None) -> dict:
    cat, label = lki_band(lki)
    return feature(
        source="air",
        fid=st["number"],
        lat=st["lat"],
        lon=st["lon"],
        title=f"Luchtkwaliteit {label} (LKI {lki:g})",
        category=cat,
        detail=", ".join(p for p in [st["name"], st["municipality"]] if p),
        time_iso=ts,
        lki=lki,
    )


class AirQualitySource(Source):
    name = "air"
    label = "Luchtkwaliteit"
    ttl = 3600
    refresh_hint = 900
    attribution = "Luchtkwaliteit: Luchtmeetnet (RIVM e.a.)"
    blocking_first_load = False  # the first station crawl takes ~6 minutes

    def __init__(self, settings):
        super().__init__(settings)
        self._stations: list[dict] = []
        self._stations_at = 0.0
        self._last_call = 0.0

    async def _get(self, client: httpx.AsyncClient, path: str, **params) -> dict:
        wait = self._last_call + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()
        r = await client.get(f"{API}{path}", params=params or None)
        r.raise_for_status()
        return r.json()

    async def _crawl_stations(self, client: httpx.AsyncClient) -> None:
        numbers, page, last = [], 1, 1
        while page <= last:
            data = await self._get(client, "/stations", page=page, order_by="number")
            numbers += [s["number"] for s in data.get("data") or [] if s.get("number")]
            last = int((data.get("pagination") or {}).get("last_page") or 1)
            page += 1
        stations = []
        for n in numbers:
            try:
                st = parse_station(n, await self._get(client, f"/stations/{n}"))
            except httpx.HTTPError:
                continue
            if st and in_bbox(st["lat"], st["lon"], self.region_box):
                stations.append(st)
        self._stations = stations
        self._stations_at = time.monotonic()

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        if not self._stations_at or time.monotonic() - self._stations_at > STATIONS_TTL:
            await self._crawl_stations(client)
        out = []
        for st in self._stations:
            try:
                got = latest_lki(
                    await self._get(
                        client, "/lki", station_number=st["number"],
                        order_by="timestamp_measured", order_direction="desc",
                    )
                )
            except httpx.HTTPError:
                continue
            if got:
                out.append(to_feature(st, *got))
        return out
