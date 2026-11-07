"""Public EV charging locations from NDW's national OCPI export, with live EVSE status.

The file is ~18 MB gzipped and far larger unpacked (one JSON array of OCPI
Locations), so it is streamed with ijson instead of loaded whole.
"""
from __future__ import annotations

import asyncio
import gzip
import io
from collections import Counter

import httpx
import ijson

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

URL = "https://opendata.ndw.nu/charging_point_locations_ocpi.json.gz"

FREE = {"AVAILABLE"}
BUSY = {"CHARGING", "BLOCKED", "RESERVED"}
DOWN = {"OUTOFORDER", "INOPERATIVE"}
GONE = {"REMOVED", "PLANNED"}


def _stream(raw: bytes):
    return gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b"\x1f\x8b" else io.BytesIO(raw)


def summarize(loc: dict) -> dict | None:
    """Reduce one OCPI Location to what the map needs, or None if unusable."""
    if loc.get("publish") is False:
        return None
    coords = loc.get("coordinates") or {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    if not valid_coord(lat, lon):
        return None
    status = Counter()
    max_w = 0.0
    for evse in loc.get("evses") or []:
        st = (evse.get("status") or "UNKNOWN").upper()
        if st in GONE:
            continue
        status[st] += 1
        for c in evse.get("connectors") or []:
            p = c.get("max_electric_power")
            if isinstance(p, (int, float)) and p > max_w:
                max_w = float(p)
    total = sum(status.values())
    if not total:
        return None
    free = sum(status[s] for s in FREE)
    busy = sum(status[s] for s in BUSY)
    down = sum(status[s] for s in DOWN)
    known = free + busy + down
    if not known:
        category = "unknown"
    elif free:
        category = "available"
    elif busy:
        category = "occupied"
    else:
        category = "out-of-order"
    return {
        "id": str(loc.get("id", "")),
        "lat": float(lat),
        "lon": float(lon),
        "name": (loc.get("name") or loc.get("address") or "").strip(),
        "address": ", ".join(p for p in [loc.get("address"), loc.get("city")] if p),
        "operator": ((loc.get("operator") or {}).get("name") or "").strip(),
        "kw": round(max_w / 1000) if max_w else None,
        "total": total,
        "free": free if known else None,
        "category": category,
        "updated": loc.get("last_updated"),
    }


def parse(raw: bytes, box=None) -> list[dict]:
    out = []
    # use_float: Decimal is slow and we only need floats
    for loc in ijson.items(_stream(raw), "item", use_float=True):
        coords = loc.get("coordinates") or {}
        # Cheap box check before summarising: most of the country is outside the region.
        if box and valid_coord(coords.get("latitude"), coords.get("longitude")):
            if not in_bbox(float(coords["latitude"]), float(coords["longitude"]), box):
                continue
        s = summarize(loc)
        if not s:
            continue
        power = f"tot {s['kw']} kW" if s["kw"] else ""
        if s["free"] is None:
            avail = f"{s['total']} laadpunt{'en' if s['total'] != 1 else ''}, status onbekend"
        else:
            avail = f"{s['free']} van {s['total']} vrij"
        fast = s["kw"] is not None and s["kw"] >= 50
        out.append(
            feature(
                source="charging",
                fid=s["id"],
                lat=s["lat"],
                lon=s["lon"],
                title=(("Snellader: " if fast else "") + (s["name"] or s["operator"] or "Laadpunt")),
                category=s["category"],
                detail=" · ".join(p for p in [avail, power, s["operator"], s["address"]] if p),
                time_iso=s["updated"],
                free=s["free"],
                total=s["total"],
                kw=s["kw"],
                fast=fast,
            )
        )
    return out


class ChargingSource(Source):
    name = "charging"
    label = "Laadpalen"
    ttl = 900          # an 18 MB download: every 15 minutes is plenty for availability
    refresh_hint = 300
    attribution = "Laadpalen: NDW open data (OCPI)"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(URL, timeout=120)
        r.raise_for_status()
        return await asyncio.to_thread(parse, r.content, self.region_box)
