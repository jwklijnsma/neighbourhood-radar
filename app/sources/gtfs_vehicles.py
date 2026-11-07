"""Live public-transport vehicle positions from OVapi's GTFS-realtime feed."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from google.transit import gtfs_realtime_pb2

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature


def parse(raw: bytes, box=None) -> list[dict]:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(raw)
    out = []
    for ent in msg.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        if not v.HasField("position"):
            continue
        lat, lon = v.position.latitude, v.position.longitude
        if not valid_coord(lat, lon) or (box and not in_bbox(lat, lon, box)):
            continue
        # Entity ids look like "2026-11-07:ARR:...:1234"; the operator is the 2nd part.
        parts = ent.id.split(":")
        operator = parts[1] if len(parts) > 2 else ""
        label = v.vehicle.label or v.vehicle.id
        ts = datetime.fromtimestamp(v.timestamp, tz=timezone.utc).isoformat() if v.timestamp else None
        out.append(
            feature(
                source="transit",
                fid=ent.id,
                lat=lat,
                lon=lon,
                title=f"{operator} {label}".strip() or "Voertuig",
                category="vehicle",
                detail=f"route {v.trip.route_id}" if v.trip.route_id else "",
                time_iso=ts,
                operator=operator or None,
                bearing=round(v.position.bearing) if v.position.HasField("bearing") else None,
            )
        )
    return out


class GTFSVehicleSource(Source):
    name = "transit"
    label = "OV-voertuigen"
    ttl = 20
    refresh_hint = 20
    attribution = "OV: OVapi GTFS-realtime (CC0)"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(self.settings.gtfs_vehicles_url)
        r.raise_for_status()
        return parse(r.content, self.region_box)
