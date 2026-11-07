"""NDW road incidents (DATEX II, gzip XML). Parsed namespace-agnostic and streaming,
so the code survives the v2.3/v3 differences and stays light on memory."""
from __future__ import annotations

import gzip
import io
import xml.etree.ElementTree as ET

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# DATEX record type -> category + Dutch label
RECORD_TYPES = {
    "Accident": ("accident", "Ongeval"),
    "VehicleObstruction": ("obstruction", "Gestrand voertuig"),
    "AnimalPresenceObstruction": ("obstruction", "Dieren op de weg"),
    "GeneralObstruction": ("obstruction", "Obstakel"),
    "EnvironmentalObstruction": ("obstruction", "Obstakel"),
    "AbnormalTraffic": ("congestion", "File"),
    "RoadOrCarriagewayOrLaneManagement": ("closure", "Afsluiting"),
    "MaintenanceWorks": ("roadworks", "Werkzaamheden"),
    "ConstructionWorks": ("roadworks", "Werkzaamheden"),
    "PoorEnvironmentConditions": ("weather", "Slecht zicht/weer"),
}


def _record_info(xsi: str) -> tuple[str, str]:
    t = xsi.split(":")[-1]
    return RECORD_TYPES.get(t, ("incident", t or "Incident"))


def parse(raw: bytes, box=None) -> list[dict]:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    out = []
    for _, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if _local(el.tag) != "situationRecord":
            continue
        rid = el.get("id", "")
        lat = lon = None
        comment = road = start = None
        for sub in el.iter():
            name = _local(sub.tag)
            if name == "latitude" and lat is None:
                lat = sub.text
            elif name == "longitude" and lon is None:
                lon = sub.text
            elif name == "overallStartTime" and start is None:
                start = sub.text
            elif name in ("roadNumber", "roadName") and road is None:
                road = (sub.text or "").strip() or None
            elif name == "generalPublicComment" and comment is None:
                vals = [v.text for v in sub.iter() if _local(v.tag) == "value" and v.text]
                comment = vals[0].strip() if vals else None
        if valid_coord(lat, lon):
            lat, lon = float(lat), float(lon)
            if not box or in_bbox(lat, lon, box):
                cat, label = _record_info(el.get(XSI_TYPE, ""))
                title = f"{label} {road}" if road else label
                out.append(
                    feature(
                        source="traffic",
                        fid=rid,
                        lat=lat,
                        lon=lon,
                        title=title,
                        category=cat,
                        detail=comment or "",
                        time_iso=start,
                        road=road,
                    )
                )
        el.clear()
    return out


class NDWIncidentSource(Source):
    name = "traffic"
    label = "Verkeer (NDW)"
    ttl = 60
    refresh_hint = 60
    attribution = "Incidenten: NDW open data"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(self.settings.ndw_incidents_url)
        r.raise_for_status()
        return parse(r.content, self.region_box)
