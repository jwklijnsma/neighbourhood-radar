import asyncio
import dataclasses
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.demo import airports as demo_airports
from app.sources import aircraft, airports
from app.geo import bbox

FX = Path(__file__).parent.parent / "app" / "demo" / "data"
BOX = bbox(52.9594, 5.9189, 60)


def props(planes):
    return {p.hex: aircraft.to_feature(p)["properties"] for p in planes}


# --- parsing ---------------------------------------------------------------------
def test_readsb_parse_adsblol():
    planes = aircraft.parse_readsb(json.loads((FX / "adsblol.json").read_text()),
                                   link_base="https://adsb.lol/?icao=")
    p = props(planes)
    assert set(p) == {"4840d6", "480c1d", "4b1234"}  # no position and stale position dropped
    klm = p["4840d6"]
    assert klm["title"] == "KLM1234 (BOEING 737-800)"
    assert klm["detail"] == "B738 · PH-BXA · KLM · 36.000 ft (10.973 m) · 834 km/u"
    assert klm["url"] == "https://adsb.lol/?icao=4840d6" and klm["heading"] == 45
    assert p["480c1d"]["category"] == "helicopter"
    mil = p["4b1234"]
    assert mil["category"] == "emergency"           # emergency beats military/ground
    assert mil["detail"].startswith("Noodgeval (squawk 7700)") and "aan de grond" in mil["detail"]


def test_readsb_local_aircraft_json_format():
    # A receiver's aircraft.json uses "aircraft" and "now" in seconds
    data = {"now": 1793000000.5, "aircraft": [{"hex": "abcdef", "lat": 52.9, "lon": 5.9, "alt_baro": 2000,
                                                "seen_pos": 1.5}]}
    (p,) = aircraft.parse_readsb(data)
    assert p.ts.startswith("2026-10-26T") and p.alt_ft == 2000 and p.link is None


def test_fr24_full():
    p = props(aircraft.parse_fr24(json.loads((FX / "fr24.json").read_text())))
    klm = p["4840d6"]
    assert klm["detail"].startswith("AMS → OSL · B738 · PH-BXA · KLM")
    assert klm["url"] == "https://www.flightradar24.com/KLM1234/3b4c5d6e"
    ground = p["3b4c5d6f"]
    assert ground["category"] == "ground" and ground["title"] == "PH-ABC"
    assert ground["url"] == "https://www.flightradar24.com/data/aircraft/ph-abc"


@pytest.mark.parametrize("squawk,label", [("7500", "Kaping"), ("7600", "Radiostoring"), ("7700", "Noodgeval")])
def test_emergency_squawks(squawk, label):
    p = aircraft.Plane(hex="a", lat=52.9, lon=5.9, squawk=squawk)
    assert aircraft.category(p) == "emergency" and aircraft.emergency_text(p).startswith(label)


def test_helicopter_by_type_without_emitter_category():
    assert aircraft.is_helicopter(aircraft.Plane(hex="a", lat=0, lon=0, type="A139"))
    assert not aircraft.is_helicopter(aircraft.Plane(hex="a", lat=0, lon=0, type="B738"))


# --- provider selection ------------------------------------------------------------
def settings(**kw):
    return dataclasses.replace(Settings(), **kw)


@pytest.mark.parametrize("kw,expected", [
    ({}, "adsblol"),
    ({"readsb_url": "http://pi/data/aircraft.json"}, "readsb"),
    ({"fr24_api_token": "x", "readsb_url": "http://pi"}, "fr24"),
    ({"aircraft_source": "opensky", "fr24_api_token": "x"}, "opensky"),
])
def test_resolve_provider(kw, expected):
    assert aircraft.resolve_provider(settings(aircraft_source=kw.pop("aircraft_source", "auto"), **kw)) == expected


def test_fr24_without_token_is_not_configured():
    src = aircraft.AircraftSource(settings(aircraft_source="fr24"))
    ok, reason = src.configured()
    assert not ok and "OL_FR24_API_TOKEN" in reason


def run(src, handler):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await src.fetch(c)
    return asyncio.run(go())


def test_fr24_request_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["headers"] = req.headers
        return httpx.Response(200, content=(FX / "fr24.json").read_bytes())

    src = aircraft.AircraftSource(settings(fr24_api_token="tok123"))
    feats = run(src, handler)
    assert seen["url"].startswith("https://fr24api.flightradar24.com/api/live/flight-positions/full?bounds=")
    north, south, west, east = map(float, httpx.URL(seen["url"]).params["bounds"].split(","))
    assert north > south and east > west          # FR24 order: north,south,west,east
    assert seen["headers"]["authorization"] == "Bearer tok123"
    assert seen["headers"]["accept-version"] == "v1"
    assert len(feats) == 2


def test_adsblol_request_uses_nautical_miles():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, content=(FX / "adsblol.json").read_bytes())

    run(aircraft.AircraftSource(settings(region_radius_km=60)), handler)
    assert seen["url"] == "https://api.adsb.lol/v2/point/52.9594/5.9189/32"


def test_trails_accumulate_and_expire():
    src = aircraft.AircraftSource(settings(aircraft_trail_minutes=10))
    p = aircraft.Plane(hex="abc", lat=52.90, lon=5.90)
    src._update_trails([p], now=0)
    src._update_trails([dataclasses.replace(p, lat=52.91)], now=30)
    src._update_trails([dataclasses.replace(p, lat=52.91)], now=60)  # didn't move: no new point
    assert src.trail("abc") == [[52.9, 5.9], [52.91, 5.9]]
    src._update_trails([], now=30 + 601)
    assert src.trail("abc") is None


def test_trails_off():
    src = aircraft.AircraftSource(settings(aircraft_trail_minutes=0))
    src._update_trails([aircraft.Plane(hex="a", lat=1, lon=1)], now=0)
    assert src.trail("a") is None


# --- airfields ----------------------------------------------------------------------
def test_airports_parse():
    feats = airports.parse(demo_airports(52.9594, 5.9189), BOX)
    by = {f["properties"]["id"]: f["properties"] for f in feats}
    assert "airports:EHOLD" not in by                       # closed
    eelde = by["airports:EHGG"]
    assert eelde["detail"] == "Luchthaven · ICAO EHGG · IATA GRQ · Groningen · lijnvluchten"
    assert eelde["url"] == "https://ourairports.com/airports/EHGG/"
    assert by["airports:NL-0001"]["category"] == "heliport"
