"""Safety points from OpenStreetMap via the Overpass API: AEDs, hospitals,
fire stations, police stations and ambulance posts. These hardly change, so
the region is queried once a day (Overpass is a shared, free service)."""
from __future__ import annotations

import httpx

from app.geo import valid_coord
from app.sources.base import Source, feature

ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# OSM tag -> (category, Dutch label)
KINDS = {
    ("emergency", "defibrillator"): ("aed", "AED"),
    ("amenity", "hospital"): ("hospital", "Ziekenhuis"),
    ("amenity", "fire_station"): ("fire_station", "Brandweerkazerne"),
    ("amenity", "police"): ("police", "Politiebureau"),
    ("emergency", "ambulance_station"): ("ambulance_station", "Ambulancepost"),
}


def build_query(box) -> str:
    s, w, n, e = box
    bb = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    parts = []
    for (k, v), _ in KINDS.items():
        parts.append(f'nwr["{k}"="{v}"]{bb};')
    return f"[out:json][timeout:90];({''.join(parts)});out center tags;"


def _kind(tags: dict):
    for (k, v), info in KINDS.items():
        if tags.get(k) == v:
            return info
    return None


def parse(data: dict) -> list[dict]:
    out = []
    for el in (data or {}).get("elements") or []:
        tags = el.get("tags") or {}
        kind = _kind(tags)
        if not kind:
            continue
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None and el.get("center"):
            lat, lon = el["center"].get("lat"), el["center"].get("lon")
        if not valid_coord(lat, lon):
            continue
        cat, label = kind
        name = tags.get("name") or ""
        bits = []
        if cat == "aed":
            if tags.get("defibrillator:location"):
                bits.append(tags["defibrillator:location"])
            if tags.get("opening_hours"):
                bits.append("open " + ("24/7" if tags["opening_hours"] == "24/7" else tags["opening_hours"]))
            if tags.get("access") in ("private", "no", "customers"):
                bits.append("beperkt toegankelijk")
        if cat == "hospital" and tags.get("emergency") == "yes":
            bits.append("met spoedeisende hulp")
        street = " ".join(p for p in [tags.get("addr:street"), tags.get("addr:housenumber")] if p)
        place = ", ".join(p for p in [street, tags.get("addr:city")] if p)
        if place:
            bits.append(place)
        out.append(
            feature(
                source="safety",
                fid=f"{el.get('type', 'n')[0]}{el.get('id')}",
                lat=float(lat),
                lon=float(lon),
                title=f"{label}: {name}" if name else label,
                category=cat,
                detail=" · ".join(bits),
                url=f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
            )
        )
    return out


class SafetyPointsSource(Source):
    name = "safety"
    label = "AED's & hulpdiensten"
    ttl = 24 * 3600
    refresh_hint = 3600
    attribution = "AED's & hulpposten: © OpenStreetMap-bijdragers (ODbL)"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        query = build_query(self.region_box)
        last = None
        for url in ENDPOINTS:  # fall back to a mirror if the main instance is busy
            try:
                r = await client.post(url, data={"data": query}, timeout=120)
                r.raise_for_status()
                return parse(r.json())
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
        raise last
