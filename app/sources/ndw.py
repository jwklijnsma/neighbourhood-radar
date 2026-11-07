"""NDW open data (opendata.ndw.nu): road incidents, bridge openings, roadworks."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature
from app.sources.datex import Record, iter_records

BASE = "https://opendata.ndw.nu"

# DATEX record type -> (category, Dutch label)
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
    "RoadworksSituation": ("roadworks", "Werkzaamheden"),
    "PublicEvent": ("event", "Evenement"),
    "SpeedManagement": ("speed", "Snelheidsbeperking"),
    "PoorEnvironmentConditions": ("weather", "Slecht zicht/weer"),
}

BRIDGE = "bridgeSwingInOperation"


def _record_info(rtype: str) -> tuple[str, str]:
    return RECORD_TYPES.get(rtype, ("incident", rtype or "Incident"))


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _placed(rec: Record, box) -> tuple[float, float] | None:
    if not valid_coord(rec.lat, rec.lon):
        return None
    lat, lon = float(rec.lat), float(rec.lon)
    if box and not in_bbox(lat, lon, box):
        return None
    return lat, lon


# --- incidents ----------------------------------------------------------------
ROADWORK_TYPES = {"MaintenanceWorks", "ConstructionWorks", "RoadworksSituation"}


def parse(raw: bytes, box=None) -> list[dict]:
    """Current traffic situations (actueel_beeld.xml.gz, or the older incidents.xml.gz).
    Bridge openings and roadworks have their own layers and are left out here."""
    out = []
    for rec in iter_records(raw):
        if rec.cancelled or rec.ended:
            continue
        if rec.network_mgmt_type == BRIDGE or rec.type in ROADWORK_TYPES:
            continue
        pos = _placed(rec, box)
        if not pos:
            continue
        cat, label = _record_info(rec.type)
        out.append(
            feature(
                source="traffic",
                fid=rec.id,
                lat=pos[0],
                lon=pos[1],
                title=f"{label} {rec.road}" if rec.road else label,
                category=cat,
                detail=rec.comments[0] if rec.comments else "",
                time_iso=rec.start,
                road=rec.road,
            )
        )
    return out


class NDWIncidentSource(Source):
    name = "traffic"
    label = "Verkeer (NDW)"
    ttl = 60
    refresh_hint = 60
    attribution = "Verkeer: NDW open data"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(self.settings.ndw_incidents_url)
        r.raise_for_status()
        return parse(r.content, self.region_box)


# --- bridges ------------------------------------------------------------------
def bridge_state(rec: Record, now: datetime, horizon: timedelta) -> str | None:
    """'open' (closed to road traffic right now), 'planned', or None to skip."""
    if rec.cancelled or rec.ended or rec.operator_status == "beingTerminated":
        return None
    start, end = _dt(rec.start), _dt(rec.end)
    if end and end < now:
        return None
    if rec.operator_status in ("beingImplemented", "implemented"):
        return "open"
    if rec.operator_status == "approved" and start and now <= start <= now + horizon:
        return "planned"
    return None


def parse_bridges(raws: list[bytes], box=None, now: datetime | None = None,
                  horizon: timedelta = timedelta(hours=6)) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    best: dict[tuple, tuple] = {}  # location -> (rank, start, rec, state, pos)
    for raw in raws:
        for rec in iter_records(raw):
            if rec.network_mgmt_type != BRIDGE:
                continue
            state = bridge_state(rec, now, horizon)
            pos = _placed(rec, box) if state else None
            if not pos:
                continue
            key = (round(pos[0], 4), round(pos[1], 4))
            rank = 0 if state == "open" else 1
            start = _dt(rec.start) or now
            cur = best.get(key)
            if cur is None or (rank, start) < (cur[0], cur[1]):
                best[key] = (rank, start, rec, state, pos)
    out = []
    for rank, start, rec, state, pos in best.values():
        local = start.astimezone().strftime("%H:%M")
        title = "Brug open" if state == "open" else f"Brugopening om {local}"
        end = _dt(rec.end)
        detail = rec.comments[0] if rec.comments else ""
        if state == "open" and end:
            detail = (detail + " · " if detail else "") + f"verwacht dicht om {end.astimezone():%H:%M}"
        out.append(
            feature(
                source="bridges",
                fid=rec.situation_id or rec.id,
                lat=pos[0],
                lon=pos[1],
                title=title,
                category=state,
                detail=detail,
                time_iso=rec.start,
            )
        )
    return out


class NDWBridgeSource(Source):
    name = "bridges"
    label = "Bruggen open"
    ttl = 30
    refresh_hint = 30
    attribution = "Bruggen: NDW open data"

    URLS = (
        f"{BASE}/tijdelijke_verkeersmaatregelen_afsluitingen.xml.gz",  # live state
        f"{BASE}/planningsfeed_brugopeningen.xml.gz",                  # announcements
    )

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        rs = await asyncio.gather(*(client.get(u) for u in self.URLS))
        for r in rs:
            r.raise_for_status()
        return parse_bridges([r.content for r in rs], self.region_box)


# --- roadworks & events -------------------------------------------------------
def parse_roadworks(raw: bytes, box=None, now: datetime | None = None,
                    ahead: timedelta = timedelta(hours=24)) -> list[dict]:
    """Roadworks and events that are on now or start within `ahead`."""
    now = now or datetime.now(timezone.utc)
    out, seen = [], set()
    for rec in iter_records(raw):
        if rec.cancelled or rec.ended or rec.network_mgmt_type == BRIDGE:
            continue
        start, end = _dt(rec.start), _dt(rec.end)
        if (start and start > now + ahead) or (end and end < now):
            continue
        pos = _placed(rec, box)
        if not pos:
            continue
        key = (rec.situation_id, round(pos[0], 4), round(pos[1], 4))
        if key in seen:
            continue
        seen.add(key)
        cat, label = _record_info(rec.type)
        when = "nu" if not start or start <= now else f"vanaf {start.astimezone():%d-%m %H:%M}"
        until = f" tot {end.astimezone():%d-%m %H:%M}" if end else ""
        out.append(
            feature(
                source="roadworks",
                fid=rec.id,
                lat=pos[0],
                lon=pos[1],
                title=f"{label} {rec.road}" if rec.road else label,
                category="now" if when == "nu" else "soon",
                detail=" · ".join(p for p in [rec.comments[0] if rec.comments else "", when + until] if p),
                time_iso=rec.start,
                kind=cat,
            )
        )
    return out


class NDWRoadworksSource(Source):
    name = "roadworks"
    label = "Wegwerkzaamheden"
    ttl = 900          # the feed is ~15 MB; NDW refreshes it every few minutes at most
    refresh_hint = 300
    attribution = "Wegwerkzaamheden: NDW open data"

    URL = f"{BASE}/planningsfeed_wegwerkzaamheden_en_evenementen.xml.gz"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        r = await client.get(self.URL, timeout=120)
        r.raise_for_status()
        # Parsing a large file is CPU-bound; keep the event loop responsive.
        return await asyncio.to_thread(parse_roadworks, r.content, self.region_box)
