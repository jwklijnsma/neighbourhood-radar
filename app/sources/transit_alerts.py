"""Bus, tram and metro service alerts (OVapi GTFS-realtime alerts.pb), pinned on
the stops they affect. Stop coordinates come from stops.txt in the national
GTFS archive, read with HTTP range requests and refreshed weekly."""
from __future__ import annotations

import asyncio
import csv
import io
import time
from datetime import datetime, timezone

import httpx
from google.transit import gtfs_realtime_pb2

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature
from app.sources.remotezip import read_member

EFFECTS = {
    1: "Geen dienst", 2: "Minder dienst", 3: "Vertraging", 4: "Omleiding",
    5: "Extra dienst", 6: "Aangepaste dienst", 7: "Overig", 9: "Halte verplaatst",
    10: "Geen effect", 11: "Toegankelijkheid",
}


def parse_stops(raw: bytes, box=None) -> dict[str, tuple[float, float, str]]:
    """stop_id -> (lat, lon, name), limited to the region box."""
    text = raw.decode("utf-8-sig", errors="replace")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        lat, lon = row.get("stop_lat"), row.get("stop_lon")
        if not valid_coord(lat, lon):
            continue
        lat, lon = float(lat), float(lon)
        if box and not in_bbox(lat, lon, box):
            continue
        out[row["stop_id"]] = (lat, lon, row.get("stop_name", ""))
    return out


def _text(ts, lang: str = "nl") -> str:
    """Pick the Dutch translation of a TranslatedString, else the first one."""
    if not ts.translation:
        return ""
    for t in ts.translation:
        if t.language.lower().startswith(lang):
            return t.text.strip()
    return ts.translation[0].text.strip()


def parse_alerts(raw: bytes, stops: dict, now: float | None = None) -> list[dict]:
    now = now or time.time()
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(raw)
    out = []
    for ent in msg.entity:
        if not ent.HasField("alert"):
            continue
        a = ent.alert
        if a.active_period and not any(
            (not p.start or p.start <= now) and (not p.end or p.end >= now) for p in a.active_period
        ):
            continue
        title = _text(a.header_text) or EFFECTS.get(a.effect, "Melding")
        detail = _text(a.description_text)
        start = None
        if a.active_period and a.active_period[0].start:
            start = datetime.fromtimestamp(a.active_period[0].start, tz=timezone.utc).isoformat()
        # One marker per affected stop *name*: platforms on both sides of the road
        # share a name and would otherwise stack two identical markers.
        seen_names = set()
        for ie in a.informed_entity:
            stop = stops.get(ie.stop_id) if ie.stop_id else None
            if not stop:
                continue
            lat, lon, name = stop
            if name in seen_names:
                continue
            seen_names.add(name)
            out.append(
                feature(
                    source="busalerts",
                    fid=f"{ent.id}:{ie.stop_id}",
                    lat=lat,
                    lon=lon,
                    title=title,
                    category=EFFECTS.get(a.effect, "Melding").lower().replace(" ", "-"),
                    detail=f"{name}: {detail}" if detail else name,
                    time_iso=start,
                    stop=name,
                )
            )
    return out


class TransitAlertSource(Source):
    name = "busalerts"
    label = "Bus/tram-meldingen"
    ttl = 60
    refresh_hint = 60
    attribution = "OV-meldingen: OVapi (CC0)"
    STOPS_TTL = 7 * 24 * 3600
    blocking_first_load = False  # the first stops.txt download can take a while

    def __init__(self, settings):
        super().__init__(settings)
        self._stops: dict = {}
        self._stops_at = 0.0

    async def _load_stops(self) -> None:
        url = self.settings.gtfs_stops_url
        if url.lower().endswith(".txt"):  # a plain stops.txt somewhere (override)
            def get():
                with httpx.Client(timeout=120, follow_redirects=True) as c:
                    r = c.get(url, headers={"User-Agent": self.settings.user_agent})
                    r.raise_for_status()
                    return r.content
            raw = await asyncio.to_thread(get)
        else:
            raw = await asyncio.to_thread(
                read_member, url, "stops.txt", headers={"User-Agent": self.settings.user_agent}, timeout=120
            )
        self._stops = parse_stops(raw, self.region_box)
        self._stops_at = time.monotonic()

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        if not self._stops or time.monotonic() - self._stops_at > self.STOPS_TTL:
            try:
                await self._load_stops()
            except Exception:
                if not self._stops:
                    raise  # nothing to place alerts on yet
        r = await client.get(self.settings.gtfs_alerts_url)
        r.raise_for_status()
        return parse_alerts(r.content, self._stops)
