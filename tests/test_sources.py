import json
from datetime import datetime, timezone
from pathlib import Path

from app.geo import bbox, haversine_km
from app.sources import gtfs_vehicles, knmi, ndw, ns, opensky, p2000, satellites

FX = Path(__file__).parent.parent / "app" / "demo" / "data"
HEERENVEEN = (52.9594, 5.9189)
BOX = bbox(*HEERENVEEN, 60)


def coords(f):
    lon, lat = f["geometry"]["coordinates"]
    return lat, lon


def test_haversine_known_distance():
    # Heerenveen -> Leeuwarden is roughly 27 km as the crow flies
    assert 25 < haversine_km(52.9594, 5.9189, 53.2012, 5.7999) < 30


def test_p2000_filters_region_location_and_merges_capcodes():
    feats = p2000.parse((FX / "p2000.xml").read_bytes(), ["1", "2", "3"], BOX)
    assert len(feats) == 2  # Amsterdam (regio 13) and the item without lat/lon are dropped
    amb = next(f for f in feats if f["properties"]["category"] == "ambulance")
    assert sorted(amb["properties"]["capcodes"]) == ["0223001", "0223999"]
    assert amb["properties"]["time"].startswith("2026-11-07T10:40:12")
    fire = next(f for f in feats if f["properties"]["category"] == "fire")
    assert "Joure" in fire["properties"]["title"]


def test_p2000_no_regio_filter_keeps_everything_with_location():
    feats = p2000.parse((FX / "p2000.xml").read_bytes(), [], None)
    assert len(feats) == 3


def test_ndw_gzip_and_box():
    feats = ndw.parse((FX / "ndw.xml.gz").read_bytes(), BOX)
    assert len(feats) == 1  # the Rotterdam record falls outside the box
    p = feats[0]["properties"]
    assert p["category"] == "accident"
    assert p["title"] == "Ongeval A7"
    assert "rechterrijstrook" in p["detail"]
    assert coords(feats[0]) == (52.9701, 5.962)


def test_gtfs_vehicles():
    feats = gtfs_vehicles.parse((FX / "vehicles.pb").read_bytes(), BOX)
    assert len(feats) == 1
    p = feats[0]["properties"]
    assert p["operator"] == "ARR" and p["title"] == "ARR 4321" and p["bearing"] == 90


def test_ns_active_only_and_station_pins():
    feats = ns.parse(json.loads((FX / "ns.json").read_text()), BOX)
    names = sorted(f["properties"]["station"] for f in feats)
    assert names == ["Heerenveen", "Leeuwarden"]
    assert all("seinstoring" in f["properties"]["detail"] for f in feats)


def test_opensky_skips_missing_positions():
    feats = opensky.parse(json.loads((FX / "opensky.json").read_text()))
    assert [f["properties"]["title"] for f in feats] == ["KLM1234", "PH-ABC"]
    klm = feats[0]["properties"]
    assert klm["category"] == "airborne" and klm["heading"] == 45 and "36.089 ft" in klm["detail"]
    assert feats[1]["properties"]["category"] == "ground"


def test_knmi_text():
    feats = knmi.parse((FX / "knmi.txt").read_text())
    assert len(feats) == 2
    assert feats[0]["properties"]["title"] == "M1.4 Garrelsweer"
    assert feats[0]["properties"]["category"] == "induced"
    assert feats[1]["properties"]["magnitude"] == 0.9


def test_satellite_propagation_is_physical():
    sats = satellites.parse_tle((FX / "stations.tle").read_text())
    assert len(sats) == 1 and sats[0][0] == "ISS (ZARYA)"
    when = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    lat, lon, alt = satellites.position(sats[0][1], when)
    assert -51.7 <= lat <= 51.7          # ISS can't exceed its inclination
    assert 380 < alt < 450               # low earth orbit
    # Directly below the satellite the elevation must be ~90 degrees.
    assert satellites.elevation_deg(lat, lon, lat, lon, alt) > 89
    # On the far side of the earth it must be below the horizon.
    assert satellites.elevation_deg(-lat, lon + 180, lat, lon, alt) < 0


def test_satellite_visibility_filter():
    sats = satellites.parse_tle((FX / "stations.tle").read_text())
    when = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    lat, lon, _ = satellites.position(sats[0][1], when)
    assert len(satellites.visible(sats, lat, lon, 10, when)) == 1
    assert satellites.visible(sats, -lat, lon + 180, 10, when) == []
