"""Transit alerts: translation fallback, active periods, and the source's stops
loading/refresh (zip member vs plain stops.txt, keeping old stops on failure)."""
import asyncio
import dataclasses
import time
from pathlib import Path

import httpx
import pytest
from google.transit import gtfs_realtime_pb2

from app.config import Settings
from app.sources import transit_alerts as ta

FX = Path(__file__).parent.parent / "app" / "demo" / "data"
STOPS = (FX / "stops.txt").read_bytes()


def feed(*alerts):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    for i, spec in enumerate(alerts):
        ent = msg.entity.add()
        ent.id = f"a{i}"
        a = ent.alert
        for lang, text in spec.get("header", []):
            t = a.header_text.translation.add()
            t.text, t.language = text, lang
        for lang, text in spec.get("desc", []):
            t = a.description_text.translation.add()
            t.text, t.language = text, lang
        a.effect = spec.get("effect", 7)
        for start, end in spec.get("periods", []):
            p = a.active_period.add()
            if start:
                p.start = start
            if end:
                p.end = end
        for stop in spec.get("stops", []):
            a.informed_entity.add().stop_id = stop
    ent = msg.entity.add()
    ent.id = "not-an-alert"
    ent.vehicle.vehicle.id = "bus1"
    return msg.SerializeToString()


STOP_MAP = {"s1": (52.96, 5.92, "Centrum"), "s2": (52.97, 5.93, "Station")}


def test_text_prefers_dutch_then_first():
    msg = gtfs_realtime_pb2.TranslatedString()
    assert ta._text(msg) == ""
    t = msg.translation.add()
    t.text, t.language = " Diversion ", "en"
    assert ta._text(msg) == "Diversion"                     # no Dutch: first one
    t = msg.translation.add()
    t.text, t.language = " Omleiding ", "NL-nl"
    assert ta._text(msg) == "Omleiding"


def test_effect_name_is_the_title_when_there_is_no_header():
    now = 1_800_000_000
    feats = ta.parse_alerts(feed({"effect": 3, "stops": ["s1"]}), STOP_MAP, now)
    p = feats[0]["properties"]
    assert (p["title"], p["category"], p["detail"]) == ("Vertraging", "vertraging", "Centrum")
    feats = ta.parse_alerts(feed({"effect": 8, "stops": ["s1"]}), STOP_MAP, now)   # UNKNOWN_EFFECT
    assert feats[0]["properties"]["title"] == "Melding"


def test_active_periods(monkeypatch):
    now = 1_800_000_000
    alerts = feed(
        {"header": [("nl", "future")], "periods": [(now + 60, None)], "stops": ["s1"]},
        {"header": [("nl", "over")], "periods": [(None, now - 60)], "stops": ["s1"]},
        {"header": [("nl", "one of two")], "periods": [(now - 999, now - 500), (now - 10, now + 10)], "stops": ["s1"]},
        {"header": [("nl", "open ended")], "periods": [(now - 10, None)], "stops": ["s2", "unknown", ""]},
    )
    feats = ta.parse_alerts(alerts, STOP_MAP, now)
    assert sorted(f["properties"]["title"] for f in feats) == ["one of two", "open ended"]
    open_ended = next(f for f in feats if f["properties"]["title"] == "open ended")
    assert open_ended["properties"]["time"] == "2027-01-15T07:59:50+00:00"     # first period start (now - 10)


def test_parse_stops_skips_bad_coordinates():
    raw = b"\xef\xbb\xbfstop_id,stop_name,stop_lat,stop_lon\nok,A,52.96,5.92\nbad,B,,\nnan,C,abc,5\n"
    assert ta.parse_stops(raw) == {"ok": (52.96, 5.92, "A")}


class Resp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class Client:
    def __init__(self, content):
        self.content, self.urls = content, []

    async def get(self, url):
        self.urls.append(url)
        return Resp(self.content)


def source(**kw):
    return ta.TransitAlertSource(dataclasses.replace(Settings(), **kw))


def test_fetch_loads_stops_from_the_gtfs_zip_once(monkeypatch):
    calls = []
    monkeypatch.setattr(ta, "read_member", lambda url, member, **kw: calls.append((url, member)) or STOPS)
    src = source(gtfs_stops_url="https://gtfs.test/gtfs-nl.zip", gtfs_alerts_url="https://gtfs.test/alerts.pb")
    client = Client(feed({"header": [("nl", "x")], "stops": ["2340001"]}))
    feats = asyncio.run(src.fetch(client))
    assert calls == [("https://gtfs.test/gtfs-nl.zip", "stops.txt")] and client.urls == ["https://gtfs.test/alerts.pb"]
    assert len(feats) == 1
    asyncio.run(src.fetch(client))
    assert len(calls) == 1                                  # stops are cached for a week


def test_plain_stops_txt_override(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=STOPS)

    real = httpx.Client
    monkeypatch.setattr(ta.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    src = source(gtfs_stops_url="https://mirror.test/stops.TXT")
    asyncio.run(src._load_stops())
    assert seen == ["https://mirror.test/stops.TXT"] and "2340001" in src._stops


def test_stale_stops_are_kept_when_a_refresh_fails(monkeypatch):
    src = source()
    src._stops, src._stops_at = dict(STOP_MAP), time.monotonic() - src.STOPS_TTL - 1

    def down(*a, **k):
        raise OSError("gtfs down")

    monkeypatch.setattr(ta, "read_member", down)
    feats = asyncio.run(src.fetch(Client(feed({"stops": ["s1"]}))))
    assert len(feats) == 1                                   # old stops still used


def test_first_load_failure_is_raised(monkeypatch):
    def down(*a, **k):
        raise OSError("gtfs down")

    monkeypatch.setattr(ta, "read_member", down)
    with pytest.raises(OSError):
        asyncio.run(source().fetch(Client(b"")))
