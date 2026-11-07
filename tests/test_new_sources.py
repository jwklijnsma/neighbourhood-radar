import asyncio
import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.geo import bbox
from app.sources import air, ndw, transit_alerts, weather, webcams
from app.sources.datex import iter_records
from app.sources.remotezip import RangeNotSupported, read_member
from tests import builders

FX = Path(__file__).parent / "fixtures"
BOX = bbox(52.9594, 5.9189, 60)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def titles(feats):
    return sorted(f["properties"]["title"] for f in feats)


# --- DATEX helper ----------------------------------------------------------
def test_datex_flags_are_scoped_correctly():
    live, plan = builders.bridge_feeds(NOW)
    recs = {r.situation_id: r for r in iter_records(plan)}
    assert recs["BP3"].cancelled is True           # situation-level <cancel>
    assert recs["BP1"].cancelled is False          # ...doesn't leak to the next situation
    rw = {r.situation_id: r for r in iter_records(builders.roadworks_feed(NOW))}
    assert rw["W5"].ended is True and rw["W1"].ended is False  # record-level <end>


def test_traffic_layer_skips_bridges_and_roadworks():
    live, _ = builders.bridge_feeds(NOW)
    feats = ndw.parse(live, BOX)
    assert [f["properties"]["category"] for f in feats] == ["closure"]


# --- bridges ---------------------------------------------------------------
def test_bridges_open_and_planned():
    live, plan = builders.bridge_feeds(NOW)
    feats = ndw.parse_bridges([live, plan], BOX, now=NOW)
    by_cat = {}
    for f in feats:
        by_cat.setdefault(f["properties"]["category"], []).append(f)
    # BR1 open (its later announcement BP4 collapses into it); BP1 planned.
    # BR2 closed again, BR3 outside region, BP2 too far ahead, BP3 cancelled.
    assert len(by_cat["open"]) == 1 and len(by_cat["planned"]) == 1 and len(feats) == 2
    assert by_cat["open"][0]["properties"]["title"] == "Brug open"
    assert "verwacht dicht" in by_cat["open"][0]["properties"]["detail"]
    assert by_cat["planned"][0]["properties"]["title"].startswith("Brugopening om ")


# --- roadworks -------------------------------------------------------------
def test_roadworks_window():
    feats = ndw.parse_roadworks(builders.roadworks_feed(NOW), BOX, now=NOW)
    assert titles(feats) == ["Evenement", "Werkzaamheden A7"]
    cats = {f["properties"]["title"]: f["properties"]["category"] for f in feats}
    assert cats == {"Werkzaamheden A7": "now", "Evenement": "soon"}
    a7 = next(f for f in feats if f["properties"]["title"] == "Werkzaamheden A7")
    assert a7["properties"]["detail"].startswith("Asfaltering · nu tot ")


# --- transit alerts ----------------------------------------------------------
def test_stops_limited_to_region():
    stops = transit_alerts.parse_stops((FX / "stops.txt").read_bytes(), BOX)
    assert set(stops) == {"2340001", "2340002", "2340010"}


def test_alerts_one_marker_per_stop_name_and_expiry():
    now = time.time()
    stops = transit_alerts.parse_stops((FX / "stops.txt").read_bytes(), BOX)
    feats = transit_alerts.parse_alerts(builders.alerts_pb(now), stops, now)
    assert len(feats) == 1  # two platforms of the same stop -> one; expired alert dropped
    p = feats[0]["properties"]
    assert p["title"] == "Omleiding lijn 98"          # Dutch translation preferred
    assert p["detail"] == "Heerenveen, Station: Halte tijdelijk niet bediend"
    assert p["category"] == "omleiding"


def _zip_with_stops() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("agency.txt", "agency_id,agency_name\nARR,Arriva\n")
        zf.writestr("stop_times.txt", "x" * 2_000_000)  # big member we must NOT download
        zf.writestr("stops.txt", (FX / "stops.txt").read_text())
    return buf.getvalue()


def test_remote_zip_reads_only_what_it_needs():
    blob = _zip_with_stops()
    served = []

    def handler(req: httpx.Request):
        if req.method == "HEAD":
            return httpx.Response(200, headers={"accept-ranges": "bytes", "content-length": str(len(blob))})
        start, end = req.headers["range"].removeprefix("bytes=").split("-")
        chunk = blob[int(start): int(end) + 1]
        served.append(len(chunk))
        return httpx.Response(206, content=chunk)

    data = read_member("https://x/gtfs-nl.zip", "stops.txt", transport=httpx.MockTransport(handler))
    assert b"Heerenveen, Station" in data
    # The 2 MB stop_times member compresses well, but we still shouldn't have pulled the whole zip
    # in more than a couple of reads.
    assert len(served) <= 4


def test_remote_zip_refuses_servers_without_range():
    def handler(req):
        if req.method == "HEAD":
            return httpx.Response(200, headers={"content-length": "100"})
        return httpx.Response(200, content=b"x" * 100)

    with pytest.raises(RangeNotSupported):
        read_member("https://x/a.zip", "stops.txt", transport=httpx.MockTransport(handler))


# --- webcams -------------------------------------------------------------------
def test_webcams_only_https_urls_reach_the_page():
    feats = webcams.parse(json.loads((FX / "windy.json").read_text()))
    assert len(feats) == 2
    good, bad = feats
    assert good["properties"]["image"].startswith("https://imgproxy.windy.com/")
    assert good["properties"]["url"] == "https://www.windy.com/webcams/1170000001"
    assert "image" not in bad["properties"] and "url" not in bad["properties"]


# --- weather -------------------------------------------------------------------
def test_weather_parse():
    feats = weather.parse(json.loads((FX / "buienradar.json").read_text()), BOX)
    assert len(feats) == 1  # Schiphol outside region, broken station skipped
    p = feats[0]["properties"]
    assert p["title"] == "Leeuwarden: 9.4 °C"
    assert "wind ZW 4 Bft" in p["detail"] and "0.2 mm regen" in p["detail"]
    assert p["time"] == "2026-11-07T12:30:00+01:00"


# --- air quality ---------------------------------------------------------------
@pytest.mark.parametrize("v,cat", [(1, "good"), (3, "good"), (4, "moderate"), (7, "poor"), (9, "bad"), (11, "very-bad")])
def test_lki_bands(v, cat):
    assert air.lki_band(v)[0] == cat


def test_air_quality_crawl_filters_region_and_respects_pacing(monkeypatch):
    monkeypatch.setattr(air, "MIN_INTERVAL", 0)
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.path + "?" + req.url.query.decode())
        p = req.url.path
        if p.endswith("/stations"):
            page = req.url.params.get("page")
            return httpx.Response(200, content=(FX / f"lmn_stations_p{page}.json").read_bytes())
        if "/stations/" in p:
            return httpx.Response(200, content=(FX / f"lmn_{p.rsplit('/', 1)[-1]}.json").read_bytes())
        if p.endswith("/lki"):
            return httpx.Response(200, content=(FX / "lmn_lki.json").read_bytes())
        return httpx.Response(404)

    from app.config import Settings

    src = air.AirQualitySource(Settings())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await src.fetch(client)

    feats = asyncio.run(run())
    # Heerenveen and Kollumerwaard are in the region, IJmuiden is not.
    assert sorted(f["properties"]["id"] for f in feats) == ["air:NL10107", "air:NL49704"]
    assert sum(c.endswith(("/lki?station_number=NL10938&order_by=timestamp_measured&order_direction=desc",)) for c in calls) == 0
    assert feats[0]["properties"]["title"] == "Luchtkwaliteit goed (LKI 3)"


def test_air_pacing_constant_is_within_rate_limit():
    # 100 requests per 5 minutes => at least 3 s between requests
    assert 300 / air.MIN_INTERVAL <= 100
