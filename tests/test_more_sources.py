import gzip

import pytest

from app.geo import bbox
from app.sources import charging, drips, osm, water
from tests import builders_more as B

BOX = bbox(52.9594, 5.9189, 60)


def by_id(feats):
    return {f["properties"]["id"].split(":", 1)[1]: f["properties"] for f in feats}


# --- charging -----------------------------------------------------------------
def test_charging_summary_and_filters():
    feats = by_id(charging.parse(B.ocpi_locations(), BOX))
    assert set(feats) == {"NLLOC001", "NLLOC002", "NLLOC003", "NLLOC006"}
    a = feats["NLLOC001"]
    assert a["category"] == "available" and a["free"] == 1 and a["total"] == 2 and a["kw"] == 300
    assert a["title"] == "Snellader: Fastned Heerenveen" and "1 van 2 vrij" in a["detail"]
    assert feats["NLLOC002"]["category"] == "occupied"
    assert feats["NLLOC002"]["title"] == "Dracht 10"           # falls back to address
    assert feats["NLLOC003"]["category"] == "unknown" and "status onbekend" in feats["NLLOC003"]["detail"]
    assert feats["NLLOC006"]["category"] == "out-of-order"     # kept despite country_code US


def test_charging_streams_instead_of_loading():
    # ijson must be able to parse a stream: feed it a gzip of a large array
    many = b"[" + b",".join([b'{"id":"x","coordinates":{"latitude":"51","longitude":"4"},"evses":[]}'] * 20000) + b"]"
    assert charging.parse(gzip.compress(many), BOX) == []


# --- DRIPs ----------------------------------------------------------------------
def test_drips_with_separate_table():
    table = drips.read_locations(B.drip_table())
    feats = by_id(drips.parse(B.drip_status(), BOX, table))
    assert set(feats) == {"RWS01_DRIP_A7_1", "RWS01_DRIP_A32_2"}  # A2 outside region, blank skipped
    a7 = feats["RWS01_DRIP_A7_1"]
    assert a7["title"] == "FILE A7 / Joure - Drachten 12 min" and a7["category"] == "text"
    assert a7["detail"] == "A7 Re 85,3 Heerenveen"
    img = feats["RWS01_DRIP_A32_2"]
    assert img["category"] == "image" and img["image"].startswith("data:image/png;base64,iVBOR")


def test_drips_with_table_in_same_payload():
    feats = drips.parse(B.drip_combined(), BOX)
    assert len(feats) == 2


def test_drips_reject_non_png_images():
    table = drips.read_locations(B.drip_table())
    feats = by_id(drips.parse(B.drip_status(bad_png=True), BOX, table))
    assert "RWS01_DRIP_A32_2" not in feats  # nothing else to show on that panel


def test_drips_without_any_locations_say_so():
    with pytest.raises(drips.NoLocations, match="OL_NDW_DRIP_TABLE_URL"):
        drips.parse(B.drip_status(), BOX, {})


def test_drips_oversized_png_dropped():
    big = B.tiny_png() + b"\x00" * (drips.MAX_PNG_BYTES + 1)
    import base64
    assert drips._png_data_uri(base64.b64encode(big).decode()) is None


# --- water levels -----------------------------------------------------------------
def test_water_stations_from_catalogue():
    st = water.stations_from_catalogue(B.rws_catalogue(), BOX)
    assert set(st) == {"lemmer", "harlingen"}  # Hoek v Holland outside, Sneek has no WATHTE


def test_water_latest_skips_forecasts_and_missing_values():
    st = water.stations_from_catalogue(B.rws_catalogue(), BOX)
    feats = by_id(water.parse_latest(B.rws_latest(), st))
    assert feats["lemmer"]["level_cm"] == -21.0 and feats["lemmer"]["title"] == "Lemmer: -21 cm NAP"
    assert feats["harlingen"]["level_cm"] == 112.0 and feats["harlingen"]["category"] == "high"
    assert feats["harlingen"]["title"] == "Harlingen: +112 cm NAP"


# --- OSM safety points -------------------------------------------------------------
def test_overpass_query_covers_all_kinds():
    q = osm.build_query(BOX)
    for (k, v) in osm.KINDS:
        assert f'nwr["{k}"="{v}"]' in q
    assert q.startswith("[out:json]") and "out center tags;" in q


def test_overpass_parse():
    feats = by_id(osm.parse(B.overpass()))
    assert set(feats) == {"n1", "w2", "n3", "n4"}
    assert feats["n1"]["title"] == "AED" and "open 24/7" in feats["n1"]["detail"]
    assert feats["w2"]["title"] == "Ziekenhuis: Tjongerschans" and "spoedeisende hulp" in feats["w2"]["detail"]
    assert feats["n4"]["title"] == "Politiebureau"
    assert feats["w2"]["url"] == "https://www.openstreetmap.org/way/2"
