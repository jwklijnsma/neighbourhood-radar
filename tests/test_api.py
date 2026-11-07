"""API tests with every upstream mocked via httpx.MockTransport."""
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

FX = Path(__file__).parent / "fixtures"
os.environ.setdefault("OL_NS_API_KEY", "test-key")

from app import main  # noqa: E402
from app import sources as registry  # noqa: E402
from app.config import Settings  # noqa: E402

CALLS: list[str] = []


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    CALLS.append(url)
    if "brandweer-berkel-enschot" in url:
        return httpx.Response(200, content=(FX / "p2000.xml").read_bytes())
    if "ndw.nu" in url:
        return httpx.Response(200, content=(FX / "ndw.xml.gz").read_bytes())
    if "ovapi" in url:
        return httpx.Response(200, content=(FX / "vehicles.pb").read_bytes())
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
def client():
    CALLS.clear()
    with TestClient(main.app) as c:
        main.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        main.app.state.sources = registry.build(Settings())
        yield c


def test_config_lists_layers(client):
    cfg = client.get("/api/config").json()
    names = [l["name"] for l in cfg["layers"]]
    assert names == ["p2000", "traffic", "transit", "trains", "aircraft", "satellites", "quakes"]
    assert all(l["configured"] for l in cfg["layers"])


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


def test_index_and_security_headers(client):
    r = client.get("/")
    assert r.status_code == 200 and "Omgeving Live" in r.text
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/vendor/leaflet/leaflet.js").status_code == 200
