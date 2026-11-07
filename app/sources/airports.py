"""Airports, airfields and heliports from OurAirports (public domain, daily CSV)."""
from __future__ import annotations

import asyncio
import csv
import io

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

TYPES = {
    "large_airport": "Luchthaven",
    "medium_airport": "Luchthaven",
    "small_airport": "Vliegveld",
    "heliport": "Helihaven",
    "seaplane_base": "Watervliegveld",
    "balloonport": "Ballonstartplaats",
}


def _https(url: str) -> str | None:
    url = (url or "").strip()
    return url if url.startswith("https://") else None


def parse(raw: bytes, box=None) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        kind = row.get("type", "")
        if kind not in TYPES:
            continue  # includes "closed"
        lat, lon = row.get("latitude_deg"), row.get("longitude_deg")
        if not valid_coord(lat, lon):
            continue
        lat, lon = float(lat), float(lon)
        if box and not in_bbox(lat, lon, box):
            continue
        codes = []
        icao = row.get("gps_code") or row.get("icao_code") or ""
        if icao:
            codes.append(f"ICAO {icao}")
        if row.get("iata_code"):
            codes.append(f"IATA {row['iata_code']}")
        bits = [TYPES[kind]] + codes
        if row.get("municipality"):
            bits.append(row["municipality"])
        if row.get("scheduled_service") == "yes":
            bits.append("lijnvluchten")
        ident = row.get("ident", "")
        link = (_https(row.get("home_link")) or _https(row.get("wikipedia_link"))
                or (f"https://ourairports.com/airports/{ident}/" if ident else None))
        out.append(
            feature(
                source="airports",
                fid=ident or row.get("id", ""),
                lat=lat,
                lon=lon,
                title=row.get("name") or ident,
                category=kind,
                detail=" · ".join(bits),
                url=link,
            )
        )
    return out


class AirportSource(Source):
    name = "airports"
    label = "Vliegvelden"
    ttl = 24 * 3600
    refresh_hint = 3600
    attribution = "Vliegvelden: OurAirports (publiek domein)"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(URL, timeout=120)
        r.raise_for_status()
        return await asyncio.to_thread(parse, r.content, self.region_box)
