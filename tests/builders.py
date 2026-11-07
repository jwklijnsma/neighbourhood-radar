"""Build time-relative test feeds (DATEX II bridges/roadworks, GTFS-RT alerts)."""
from __future__ import annotations

import gzip
from datetime import datetime, timedelta, timezone

from google.transit import gtfs_realtime_pb2

NS = (
    'xmlns="http://datex2.eu/schema/3/situation" '
    'xmlns:com="http://datex2.eu/schema/3/common" '
    'xmlns:loc="http://datex2.eu/schema/3/locationReferencing" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def situation(sid, rid, *, xsi="GeneralNetworkManagement", lat, lon, start, end=None,
              gnm=None, status=None, cancel=False, comment=None, road=None, rec_end=False):
    parts = [f'<situation id="{sid}" version="1">']
    parts.append(f'<situationRecord id="{rid}" version="1" xsi:type="{xsi}">')
    parts.append("<probabilityOfOccurrence>certain</probabilityOfOccurrence>")
    parts.append("<validity><com:validityTimeSpecification>")
    parts.append(f"<com:overallStartTime>{iso(start)}</com:overallStartTime>")
    if end:
        parts.append(f"<com:overallEndTime>{iso(end)}</com:overallEndTime>")
    parts.append("</com:validityTimeSpecification></validity>")
    if comment:
        parts.append(f"<generalPublicComment><comment><com:values><com:value lang=\"nl\">{comment}</com:value></com:values></comment></generalPublicComment>")
    if rec_end:
        parts.append("<end>true</end>")
    parts.append('<locationReference xsi:type="loc:PointLocation">')
    if road:
        parts.append(f"<loc:roadInformation><loc:roadNumber>{road}</loc:roadNumber></loc:roadInformation>")
    parts.append(f"<loc:coordinatesForDisplay><loc:latitude>{lat}</loc:latitude><loc:longitude>{lon}</loc:longitude></loc:coordinatesForDisplay></locationReference>")
    if status:
        parts.append(f"<operatorActionStatus>{status}</operatorActionStatus>")
    if gnm:
        parts.append(f"<generalNetworkManagementType>{gnm}</generalNetworkManagementType>")
    parts.append("</situationRecord>")
    if cancel:
        parts.append("<cancel>true</cancel>")
    parts.append("</situation>")
    return "".join(parts)


def publication(*situations: str, gz: bool = True) -> bytes:
    xml = f'<?xml version="1.0"?><payload {NS}><publicationTime>{iso(datetime.now(timezone.utc))}</publicationTime>{"".join(situations)}</payload>'
    data = xml.encode()
    return gzip.compress(data) if gz else data


def bridge_feeds(now: datetime | None = None) -> tuple[bytes, bytes]:
    now = now or datetime.now(timezone.utc)
    B = "bridgeSwingInOperation"
    live = publication(
        # open now, Akkrum (in region)
        situation("BR1", "BR1_1", lat=53.0490, lon=5.8390, start=now - timedelta(minutes=2),
                  end=now + timedelta(minutes=5), gnm=B, status="beingImplemented"),
        # already closed again
        situation("BR2", "BR2_1", lat=52.9700, lon=5.9200, start=now - timedelta(minutes=20),
                  end=now - timedelta(minutes=10), gnm=B, status="implemented"),
        # open, but in Gouda (outside region)
        situation("BR3", "BR3_1", lat=52.0244, lon=4.6677, start=now, gnm=B, status="beingImplemented"),
        # not a bridge
        situation("RD1", "RD1_1", lat=52.95, lon=5.90, start=now, xsi="RoadOrCarriagewayOrLaneManagement"),
    )
    plan = publication(
        # planned in 45 min, Sneek
        situation("BP1", "BP1_1", lat=53.0330, lon=5.6600, start=now + timedelta(minutes=45),
                  end=now + timedelta(minutes=55), gnm=B, status="approved"),
        # planned for tomorrow: beyond horizon
        situation("BP2", "BP2_1", lat=53.0100, lon=5.7000, start=now + timedelta(days=1), gnm=B, status="approved"),
        # cancelled announcement
        situation("BP3", "BP3_1", lat=53.0200, lon=5.7100, start=now + timedelta(minutes=30), gnm=B,
                  status="approved", cancel=True),
        # same bridge as BR1, also announced: must collapse into the 'open' marker
        situation("BP4", "BP4_1", lat=53.0490, lon=5.8390, start=now + timedelta(minutes=60), gnm=B, status="approved"),
    )
    return live, plan


def roadworks_feed(now: datetime | None = None) -> bytes:
    now = now or datetime.now(timezone.utc)
    return publication(
        situation("W1", "W1_1", xsi="MaintenanceWorks", lat=52.9800, lon=5.9500, road="A7",
                  start=now - timedelta(days=2), end=now + timedelta(days=3), comment="Asfaltering"),
        situation("W2", "W2_1", xsi="PublicEvent", lat=52.9500, lon=5.9300,
                  start=now + timedelta(hours=5), end=now + timedelta(hours=9), comment="Wielerronde"),
        situation("W3", "W3_1", xsi="MaintenanceWorks", lat=52.9600, lon=5.9100,
                  start=now + timedelta(days=10)),                                   # too far ahead
        situation("W4", "W4_1", xsi="MaintenanceWorks", lat=52.9600, lon=5.9100,
                  start=now - timedelta(days=5), end=now - timedelta(days=1)),       # finished
        situation("W5", "W5_1", xsi="MaintenanceWorks", lat=52.9600, lon=5.9100,
                  start=now - timedelta(days=1), rec_end=True),                      # ended flag
    )


def alerts_pb(now: float) -> bytes:
    m = gtfs_realtime_pb2.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    m.header.timestamp = int(now)

    e = m.entity.add()
    e.id = "KV15:ARR:1"
    a = e.alert
    p = a.active_period.add()
    p.start, p.end = int(now - 600), int(now + 3600)
    a.effect = 4  # DETOUR
    a.header_text.translation.add(text="Detour", language="en")
    a.header_text.translation.add(text="Omleiding lijn 98", language="nl")
    a.description_text.translation.add(text="Halte tijdelijk niet bediend", language="nl")
    for sid in ("2340001", "2340002", "9990001", "unknown"):  # two platforms, one far away, one unknown
        a.informed_entity.add(stop_id=sid)

    e = m.entity.add()
    e.id = "KV15:ARR:old"
    a = e.alert
    p = a.active_period.add()
    p.start, p.end = int(now - 7200), int(now - 3600)  # expired
    a.informed_entity.add(stop_id="2340010")
    return m.SerializeToString()
