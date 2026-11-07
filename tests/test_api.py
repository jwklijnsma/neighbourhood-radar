"""API tests with every upstream mocked via httpx.MockTransport."""
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

FX = Path(__file__).parent / "fixtures"
os.environ.setdefault("OL_NS_API_KEY", "test-key")
os.environ.setdefault("OL_WINDY_API_KEY", "windy-test-key")

from app import main  # noqa: E402
from app import sources as registry  # noqa: E402
from app.config import Settings  # noqa: E402
from app.sources import air, transit_alerts  # noqa: E402
from tests import builders  # noqa: E402

CALLS: list[str] = []


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    CALLS.append(url)
    if "brandweer-berkel-enschot" in url:
        return httpx.Response(200, content=(FX / "p2000.xml").read_bytes())
    if "ndw.nu" in url:
        live, plan = builders.bridge_feeds()
        if "actueel_beeld" in url:
            return httpx.Response(200, content=(FX / "ndw.xml.gz").read_bytes())
        if "afsluitingen" in url:
            return httpx.Response(200, content=live)
        if "brugopeningen" in url:
            return httpx.Response(200, content=plan)
        if "wegwerkzaamheden" in url:
            return httpx.Response(200, content=builders.roadworks_feed())
    if "ovapi" in url and url.endswith("alerts.pb"):
        import time

        return httpx.Response(200, content=builders.alerts_pb(time.time()))
    if "ovapi" in url:
        return httpx.Response(200, content=(FX / "vehicles.pb").read_bytes())
    if "api.windy.com" in url:
        assert request.headers["X-WINDY-API-KEY"] == "windy-test-key"
        return httpx.Response(200, content=(FX / "windy.json").read_bytes())
    if "buienradar" in url:
        return httpx.Response(200, content=(FX / "buienradar.json").read_bytes())
    if "luchtmeetnet" in url:
        path = request.url.path
        if path.endswith("/stations"):
            page = request.url.params.get("page")
            return httpx.Response(200, content=(FX / f"lmn_stations_p{page}.json").read_bytes())
        if "/stations/" in path:
            return httpx.Response(200, content=(FX / f"lmn_{path.rsplit('/', 1)[-1]}.json").read_bytes())
        return httpx.Response(200, content=(FX / "lmn_lki.json").read_bytes())
    if "apiportal.ns.nl" in url:
        assert request.headers["Ocp-Apim-Subscription-Key"] == "test-key"
        return httpx.Response(200, content=(FX / "ns.json").read_bytes())
    if "opensky" in url:
        return httpx.Response(200, content=(FX / "opensky.json").read_bytes())
    if "celestrak" in url:
        return httpx.Response(200, text=(FX / "stations.tle").read_text())
    if "knmi" in url:
        return httpx.Response(500, text="upstream down")
    return httpx.Response(404)


@pytest.fixture
def client(monkeypatch):
    CALLS.clear()
    monkeypatch.setattr(air, "MIN_INTERVAL", 0)

    async def fake_stops(self):
        self._stops = transit_alerts.parse_stops((FX / "stops.txt").read_bytes(), self.region_box)
        self._stops_at = 1e12

    monkeypatch.setattr(transit_alerts.TransitAlertSource, "_load_stops", fake_stops)
    with TestClient(main.app) as c:
        main.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        main.app.state.sources = registry.build(Settings())
        yield c


def test_config_lists_layers(client):
    cfg = client.get("/api/config").json()
    names = [l["name"] for l in cfg["layers"]]
    assert names == [
        "p2000", "traffic", "bridges", "roadworks", "busalerts", "transit", "trains",
        "webcams", "weather", "air", "aircraft", "satellites", "quakes",
    ]
    assert all(l["configured"] for l in cfg["layers"])


def _eventually(client, layer, **params):
    """Non-blocking sources return [] on the first call and fill in the background."""
    import time

    for _ in range(50):
        body = client.get(f"/api/layers/{layer}", params={"radius_km": 60, **params}).json()
        if body["features"]:
            return body
        time.sleep(0.05)
    raise AssertionError(f"{layer} never produced data: {body['status']}")


def test_slow_sources_do_not_block_first_request(client):
    first = client.get("/api/layers/air", params={"radius_km": 60}).json()
    assert first["features"] == []          # returned straight away, crawl runs in background
    body = _eventually(client, "air")
    assert len(body["features"]) == 2


def test_new_layers_end_to_end(client):
    assert len(_eventually(client, "busalerts")["features"]) == 1
    assert {f["properties"]["category"] for f in _eventually(client, "bridges")["features"]} == {"open", "planned"}
    assert len(_eventually(client, "roadworks")["features"]) == 2
    assert len(_eventually(client, "webcams")["features"]) == 2
    assert _eventually(client, "weather")["features"][0]["properties"]["temperature"] == 9.4


def test_unconfigured_layer_is_reported_and_skipped(client, monkeypatch):
    monkeypatch.delenv("OL_WINDY_API_KEY")
    main.app.state.sources = registry.build(Settings())
    body = client.get("/api/layers/webcams").json()
    assert body["features"] == [] and body["status"]["configured"] is False
    assert not any("windy" in c for c in CALLS)


def test_layer_radius_filter_and_distance_sorting(client):
    r = client.get("/api/layers/p2000", params={"lat": 52.9594, "lon": 5.9189, "radius_km": 2})
    feats = r.json()["features"]
    assert len(feats) == 1 and feats[0]["properties"]["category"] == "ambulance"
    wide = client.get("/api/layers/p2000", params={"lat": 52.9594, "lon": 5.9189, "radius_km": 20}).json()
    d = [f["properties"]["distance_km"] for f in wide["features"]]
    assert d == sorted(d) and len(d) == 2


def test_cache_prevents_repeat_upstream_calls(client):
    for _ in range(3):
        client.get("/api/layers/aircraft")
    assert sum("opensky" in c for c in CALLS) == 1


def test_failed_source_reports_error_not_500(client):
    r = client.get("/api/layers/quakes")
    assert r.status_code == 200
    body = r.json()
    assert body["features"] == [] and "HTTPStatusError" in body["status"]["last_error"]


def test_summary_counts(client):
    s = client.get("/api/summary", params={"lat": 52.9614, "lon": 5.9150, "radius_km": 1.5}).json()
    counts = {l["layer"]: l["count"] for l in s["layers"]}
    assert counts["p2000"] == 1 and counts["trains"] == 1 and counts["transit"] == 1


def test_radius_cap_and_unknown_layer(client):
    assert client.get("/api/layers/p2000", params={"radius_km": 5000}).status_code == 400
    assert client.get("/api/layers/nope").status_code == 404


def test_security_headers(client):
    r = client.get("/api/config")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


BUILT = (Path(main.__file__).parent / "static" / "index.html").exists()


@pytest.mark.skipif(not BUILT, reason="frontend not built (cd frontend && npm run build)")
def test_index_serves_react_build_and_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and '<div id="root">' in r.text
    import re

    assets = re.findall(r'(?:src|href)="(/static/assets/[^"]+)"', r.text)
    assert assets, "built page should reference hashed assets"
    for a in assets:
        assert client.get(a).status_code == 200


def test_index_without_build_explains(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STATIC", tmp_path)
    r = client.get("/")
    assert r.status_code == 503 and "npm run build" in r.text
