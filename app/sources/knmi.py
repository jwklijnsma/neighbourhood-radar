"""Recent earthquakes from the KNMI FDSN event service (keyless, CC BY 4.0)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.geo import valid_coord
from app.sources.base import Source, feature

URL = "https://rdsa.knmi.nl/fdsnws/event/1/query"


def parse(text: str) -> list[dict]:
    """FDSN text format:
    #EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|ContributorID|
     MagType|Magnitude|MagAuthor|EventLocationName|EventType
    """
    out = []
    header: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            header = [h.strip().lower() for h in line[1:].split("|")]
            continue
        cols = line.split("|")
        row = dict(zip(header, cols)) if header else {}
        lat, lon = row.get("latitude"), row.get("longitude")
        if not valid_coord(lat, lon):
            continue
        mag = row.get("magnitude", "").strip()
        place = row.get("eventlocationname", "").strip()
        depth = row.get("depth/km", "").strip()
        etype = row.get("eventtype", "").strip()
        induced = "induced" in etype.lower()
        try:
            magf = float(mag)
        except ValueError:
            magf = None
        out.append(
            feature(
                source="quakes",
                fid=row.get("eventid", "").strip(),
                lat=float(lat),
                lon=float(lon),
                title=f"M{mag} {place}".strip() if mag else (place or "Aardbeving"),
                category="induced" if induced else "natural",
                detail=" · ".join(p for p in [f"diepte {depth} km" if depth else "", etype] if p),
                time_iso=(row.get("time", "").strip() or None),
                magnitude=magf,
            )
        )
    return out


class KNMIQuakeSource(Source):
    name = "quakes"
    label = "Aardbevingen (KNMI)"
    ttl = 300
    refresh_hint = 300
    attribution = "Aardbevingen: KNMI (CC BY 4.0)"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        start = datetime.now(timezone.utc) - timedelta(days=self.settings.knmi_days)
        lamin, lomin, lamax, lomax = self.region_box
        r = await client.get(
            URL,
            params={
                "format": "text",
                "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
                "minlatitude": round(lamin, 4),
                "maxlatitude": round(lamax, 4),
                "minlongitude": round(lomin, 4),
                "maxlongitude": round(lomax, 4),
                "orderby": "time",
            },
        )
        if r.status_code == 204:  # FDSN: no events
            return []
        r.raise_for_status()
        return parse(r.text)
