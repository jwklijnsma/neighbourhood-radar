"""What the dynamic route information panels (DRIPs) above Dutch roads show right now.

NDW DATEX II v3 VMS profile:
- configuration/location: vmsController (with vmsLocation coordinates), in a
  VmsTablePublication — either in the same payload or a separate file
- live state: vmsControllerStatus -> vmsStatus -> vmsMessage, holding text lines
  (textLine) and/or a PNG image (image/imageData, base64)

Many DRIPs show only an image (travel times, route advice), so the PNG is passed
through to the popup as a data: URI after checking it really is a small PNG.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import gzip
import io
import xml.etree.ElementTree as ET

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature
from app.sources.datex import local

URL = "https://opendata.ndw.nu/dynamische_route_informatie_paneel.xml.gz"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 150_000


class NoLocations(RuntimeError):
    pass


def _stream(raw: bytes):
    return gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b"\x1f\x8b" else io.BytesIO(raw)


def _png_data_uri(b64: str) -> str | None:
    try:
        data = base64.b64decode(b64.strip(), validate=False)
    except (binascii.Error, ValueError):
        return None
    if not data.startswith(PNG_MAGIC) or len(data) > MAX_PNG_BYTES:
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _first_coords(el) -> tuple[str | None, str | None]:
    lat = lon = None
    for sub in el.iter():
        n = local(sub.tag)
        if n == "latitude" and lat is None:
            lat = (sub.text or "").strip()
        elif n == "longitude" and lon is None:
            lon = (sub.text or "").strip()
        if lat and lon:
            break
    return lat, lon


def read_locations(raw: bytes) -> dict[str, tuple[float, float, str]]:
    """controller id -> (lat, lon, description) from any vmsController elements."""
    out = {}
    for _, el in ET.iterparse(_stream(raw), events=("end",)):
        if local(el.tag).lower() != "vmscontroller":
            continue
        lat, lon = _first_coords(el)
        if valid_coord(lat, lon):
            desc = ""
            for sub in el.iter():
                if local(sub.tag) == "description":
                    vals = [v.text.strip() for v in sub.iter() if local(v.tag) == "value" and v.text]
                    desc = vals[0] if vals else (sub.text or "").strip()
                    if desc:
                        break
            out[el.get("id", "")] = (float(lat), float(lon), desc)
        el.clear()
    return out


def parse(raw: bytes, box=None, table: dict | None = None) -> list[dict]:
    """Features for DRIPs that currently show something. `table` adds locations from
    a separate table publication; locations inside `raw` are used as well."""
    locations = dict(table or {})
    locations.update(read_locations(raw))

    out, unplaced = [], 0
    for _, el in ET.iterparse(_stream(raw), events=("end",)):
        if local(el.tag).lower() != "vmscontrollerstatus":
            continue
        ref = next((s for s in el.iter() if local(s.tag) == "vmsControllerReference"), None)
        cid = ref.get("id", "") if ref is not None else ""
        lat, lon = _first_coords(el)  # some publishers put the location in the status too
        if valid_coord(lat, lon):
            pos = (float(lat), float(lon), "")
        else:
            pos = locations.get(cid)
        lines, image, set_at, working = [], None, None, None
        for sub in el.iter():
            n = local(sub.tag)
            if n == "textLine":
                txt = " ".join(t.strip() for t in sub.itertext() if t.strip())
                if txt and txt not in lines:
                    lines.append(txt)
            elif n == "imageData" and image is None and sub.text:
                image = _png_data_uri(sub.text)
            elif n == "timeLastSet" and set_at is None:
                set_at = (sub.text or "").strip() or None
            elif n == "workingStatus" and working is None:
                working = (sub.text or "").strip()
        el.clear()
        if not lines and not image:
            continue  # blank panel
        if not pos:
            unplaced += 1
            continue
        if box and not in_bbox(pos[0], pos[1], box):
            continue
        title = " / ".join(lines[:3]) if lines else "Route-informatiepaneel"
        out.append(
            feature(
                source="drips",
                fid=cid or f"{pos[0]:.5f},{pos[1]:.5f}",
                lat=pos[0],
                lon=pos[1],
                title=title[:140],
                category="text" if lines else "image",
                detail=pos[2] or ("buiten werking" if working and working != "working" else ""),
                time_iso=set_at,
                image=image,
                lines=lines or None,
            )
        )
    if unplaced and not out and not locations:
        raise NoLocations(
            f"{unplaced} active DRIPs but no locations in the feed; "
            "set OL_NDW_DRIP_TABLE_URL to NDW's DRIP location table"
        )
    return out


class DripSource(Source):
    name = "drips"
    label = "Matrixborden (DRIP)"
    ttl = 60      # NDW publishes the state every 60 s
    refresh_hint = 60
    attribution = "DRIP's: NDW open data"
    TABLE_TTL = 24 * 3600

    def __init__(self, settings):
        super().__init__(settings)
        self._table: dict = {}
        self._table_at = 0.0

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        import time

        table_url = self.settings.ndw_drip_table_url
        if table_url and (not self._table or time.monotonic() - self._table_at > self.TABLE_TTL):
            t = await client.get(table_url, timeout=120)
            t.raise_for_status()
            self._table = await asyncio.to_thread(read_locations, t.content)
            self._table_at = time.monotonic()
        r = await client.get(self.settings.ndw_drip_url, timeout=60)
        r.raise_for_status()
        return await asyncio.to_thread(parse, r.content, self.region_box, self._table)
