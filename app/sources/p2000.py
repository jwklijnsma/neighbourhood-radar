"""P2000 emergency-service alerts from an RSS feed that carries lat/lon per item."""
from __future__ import annotations

import calendar
import hashlib
from datetime import datetime, timezone

import feedparser
import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

# Map the feed's "dienst" field onto a short category used for icons/colours.
DISCIPLINES = {
    "brandweer": "fire",
    "ambulance": "ambulance",
    "politie": "police",
    "knrm": "boat",
    "lifeliner": "helicopter",
}


def _category(dienst: str) -> str:
    d = (dienst or "").lower()
    for key, cat in DISCIPLINES.items():
        if key in d:
            return cat
    return "other"


def parse(raw: bytes, regios: list[str], box=None) -> list[dict]:
    feed = feedparser.parse(raw)
    wanted = {r.lstrip("0") for r in regios}
    out: dict[str, dict] = {}
    for e in feed.entries:
        regio = str(e.get("regcode", "")).lstrip("0")
        if wanted and regio and regio not in wanted:
            continue
        lat, lon = e.get("lat"), e.get("lon")
        if not valid_coord(lat, lon):
            continue  # an alert we can't place on the map
        lat, lon = float(lat), float(lon)
        if box and not in_bbox(lat, lon, box):
            continue
        msg = (e.get("message") or e.get("title") or "").strip()
        ts = None
        if e.get("published_parsed"):
            ts = datetime.fromtimestamp(calendar.timegm(e.published_parsed), tz=timezone.utc).isoformat()
        # One incident is paged to several capcodes; merge on message+time.
        key = hashlib.sha1(f"{msg}|{ts}".encode()).hexdigest()[:16]
        if key in out:
            caps = out[key]["properties"].setdefault("capcodes", [])
            if e.get("code") and e.get("code") not in caps:
                caps.append(e.get("code"))
            continue
        out[key] = feature(
            source="p2000",
            fid=key,
            lat=lat,
            lon=lon,
            title=msg or "P2000 melding",
            category=_category(e.get("dienst", "")),
            detail=e.get("regname", ""),
            time_iso=ts,
            discipline=e.get("dienst"),
            capcodes=[e.get("code")] if e.get("code") else [],
        )
    return list(out.values())


class P2000Source(Source):
    name = "p2000"
    label = "112 / P2000"
    ttl = 30
    refresh_hint = 30
    attribution = "P2000 via p2000.brandweer-berkel-enschot.nl"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(self.settings.p2000_url)
        r.raise_for_status()
        return parse(r.content, self.settings.p2000_regios, self.region_box)
