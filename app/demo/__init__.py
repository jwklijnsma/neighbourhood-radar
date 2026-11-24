"""Demo mode (OL_DEMO=1): every upstream request is answered from built-in sample
data instead of the internet. Used for screenshots, trying the app offline, and
showing it without exposing real P2000 messages.

The samples are synthetic: invented incidents, vehicles and charging points
around the configured centre, with timestamps relative to "now" so the map
always looks current.
"""
from __future__ import annotations

import dataclasses
import gzip
import json
import random
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
from google.transit import gtfs_realtime_pb2

from app.demo import builders, builders_more

DATA = Path(__file__).parent / "data"


def _rng(seed: int = 7) -> random.Random:
    return random.Random(seed)


def _around(rng, lat, lon, km):
    return lat + rng.uniform(-km, km) / 111.0, lon + rng.uniform(-km, km) / 67.0


# --- generated samples --------------------------------------------------------
def p2000_rss(lat: float, lon: float) -> bytes:
    now = datetime.now(timezone.utc)
    items = [
        ("A1 Heerenveen Rit 0471 (demo)", "Ambulancediensten", 4, (0.002, 0.003)),
        ("P 1 BRT-01 Brand woning Joure (demo)", "Brandweerdiensten", 18, (0.005, -0.12)),
        ("P 2 Assistentie ambulance Akkrum (demo)", "Brandweerdiensten", 35, (0.09, -0.08)),
        ("A2 Gorredijk Rit 0482 (demo)", "Ambulancediensten", 52, (0.0, 0.17)),
        ("P 1 Lifeliner 4 Wolvega (demo)", "Lifeliner", 70, (-0.11, -0.01)),
    ]
    out = ['<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>P2000 demo</title>']
    for msg, dienst, mins, (dlat, dlon) in items:
        when = format_datetime(now - timedelta(minutes=mins))
        out.append(
            f"<item><title>{msg}</title><message>{msg}</message><pubDate>{when}</pubDate>"
            f"<regcode>02</regcode><regname>Fryslan</regname><dienst>{dienst}</dienst><code>0200000</code>"
            f"<lat>{lat + dlat:.5f}</lat><lon>{lon + dlon:.5f}</lon></item>"
        )
    out.append("</channel></rss>")
    return "".join(out).encode()


def traffic(lat: float, lon: float) -> bytes:
    now = datetime.now(timezone.utc)
    S = builders.situation
    return builders.publication(
        S("D1", "D1_1", xsi="Accident", lat=lat + 0.02, lon=lon + 0.04, road="A7",
          start=now - timedelta(minutes=12), comment="Ongeval, rechterrijstrook dicht (demo)"),
        S("D2", "D2_1", xsi="AbnormalTraffic", lat=lat - 0.05, lon=lon - 0.02, road="A32",
          start=now - timedelta(minutes=25), comment="File 3 km (demo)"),
        S("D3", "D3_1", xsi="VehicleObstruction", lat=lat + 0.06, lon=lon - 0.1, road="N354",
          start=now - timedelta(minutes=5), comment="Gestrand voertuig op de vluchtstrook (demo)"),
    )


def vehicles(lat: float, lon: float) -> bytes:
    rng = _rng(3)
    m = gtfs_realtime_pb2.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    m.header.timestamp = int(time.time())
    for i in range(14):
        e = m.entity.add()
        e.id = f"demo:ARR:{1000 + i}:{4300 + i}"
        v = e.vehicle
        v.position.latitude, v.position.longitude = _around(rng, lat, lon, 12)
        v.position.bearing = rng.randrange(360)
        v.vehicle.label = str(4300 + i)
        v.trip.route_id = f"ARR:{rng.choice([7, 13, 98, 99, 315])}"
        v.timestamp = int(time.time()) - rng.randrange(60)
    return m.SerializeToString()


DEMO_AIRCRAFT = [
    # callsign, reg, type, desc, operator, alt_ft, gs_kt, km_from_centre, extra
    ("KLM1567", "PH-BXA", "B738", "BOEING 737-800", "KLM", 36000, 450, 9, {}),
    ("TRA6721", "PH-HSJ", "B738", "BOEING 737-800", "Transavia", 24000, 420, 6, {"baro_rate": -1600}),
    ("EZY78QK", "G-UZHA", "A20N", "AIRBUS A320neo", "easyJet", 38000, 460, 10, {}),
    ("RYR5HB", "EI-DCL", "B738", "BOEING 737-800", "Ryanair", 33000, 440, 8, {}),
    ("DLH9TA", "D-AINA", "A20N", "AIRBUS A320neo", "Lufthansa", 21000, 380, 5, {"baro_rate": 1800}),
    ("LIFE4", "PH-DMO", "EC35", "EUROCOPTER EC-135", "Traumaheli (demo)", 1200, 120, 3, {"category": "A7"}),
    ("PHHOW", "PH-HOW", "C172", "CESSNA 172", "", 1800, 95, 4, {}),
    ("DEMO77", "PH-XYZ", "PC12", "PILATUS PC-12", "", 9000, 240, 7, {"squawk": "7700", "emergency": "general"}),
]


def aircraft(lat: float, lon: float) -> dict:
    """readsb-format response (as from api.adsb.lol) that drifts with time, so
    trails build up while the demo runs."""
    import math

    rng = _rng(5)
    t = time.time()
    ac = []
    for i, (cs, reg, typ, desc, op, alt, gs, km, extra) in enumerate(DEMO_AIRCRAFT):
        bearing = rng.uniform(0, 360)
        track = (bearing + 90) % 360
        # each aircraft circles the centre slowly; position depends on the clock
        angle = math.radians(bearing + (t / 30) * (gs / 400) * 2)
        la = lat + (km / 111.0) * math.cos(angle)
        lo = lon + (km / 67.0) * math.sin(angle)
        ac.append({
            "hex": f"48{i:04x}", "flight": cs.ljust(8), "r": reg, "t": typ, "desc": desc, "ownOp": op,
            "lat": round(la, 5), "lon": round(lo, 5), "alt_baro": alt, "gs": gs,
            "track": round((math.degrees(angle) + 90) % 360, 1), "squawk": "1000", "category": "A3",
            "seen_pos": rng.uniform(0, 3), "dbFlags": 0, **extra,
        })
    return {"now": int(t * 1000), "ac": ac, "msg": "No error", "total": len(ac)}


def airports(lat: float, lon: float) -> bytes:
    rows = [
        ("EHLW", "medium_airport", "Leeuwarden Air Base", 53.2286, 5.7606, "Leeuwarden", "", ""),
        ("EHDR", "small_airport", "Drachten Airfield", 53.1192, 6.1297, "Drachten", "", ""),
        ("EHHV", "small_airport", "Heerenveen Airfield (demo)", lat - 0.03, lon + 0.05, "Heerenveen", "", ""),
        ("NL-0001", "heliport", "Ziekenhuis Heliport (demo)", lat - 0.006, lon + 0.016, "Heerenveen", "", ""),
        ("EHGG", "medium_airport", "Groningen Airport Eelde", 53.1197, 6.5794, "Groningen", "GRQ", "yes"),
        ("EHOLD", "closed", "Old strip", lat, lon, "", "", ""),
    ]
    head = "id,ident,type,name,latitude_deg,longitude_deg,municipality,iata_code,scheduled_service,gps_code\n"
    body = "".join(f'{i},{r[0]},{r[1]},"{r[2]}",{r[3]},{r[4]},{r[5]},{r[6]},{r[7]},{r[0]}\n'
                   for i, r in enumerate(rows))
    return (head + body).encode()


def charging(lat: float, lon: float) -> bytes:
    rng = _rng(11)
    ops = ["Vattenfall", "Shell Recharge", "Allego", "Fastned", "Equans", "Ecotap"]
    locs = []
    for i in range(35):
        la, lo = _around(rng, lat, lon, 10)
        fast = rng.random() < 0.12
        n = rng.choice([1, 2, 2, 2, 4]) if not fast else rng.choice([4, 6, 8])
        statuses = rng.choices(["AVAILABLE", "CHARGING", "OUTOFORDER", "UNKNOWN"], weights=[50, 35, 5, 10], k=n)
        locs.append({
            "id": f"DEMO{i:03d}", "name": f"Laadplein {i + 1} (demo)" if fast else "",
            "address": f"Demostraat {i + 1}", "city": "Heerenveen",
            "coordinates": {"latitude": f"{la:.5f}", "longitude": f"{lo:.5f}"},
            "operator": {"name": rng.choice(ops)},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "evses": [{"status": s, "connectors": [{"max_electric_power": 150000 if fast else 11000}]}
                      for s in statuses],
        })
    return gzip.compress(json.dumps(locs).encode())


def buienradar(lat: float, lon: float) -> dict:
    stations = [("Leeuwarden", 0.26, -0.12, 9.4), ("Heerenveen (demo)", 0.0, 0.0, 9.9),
                ("Stavoren", 0.0, -0.53, 10.6), ("Lauwersoog", 0.45, 0.33, 8.7),
                ("Hoogeveen", -0.21, 0.55, 8.2)]
    now = datetime.now().replace(second=0, microsecond=0).isoformat()
    return {"actual": {"stationmeasurements": [
        {"stationid": 9000 + i, "stationname": f"Meetstation {name}", "lat": lat + dla, "lon": lon + dlo,
         "timestamp": now, "weatherdescription": "Half bewolkt", "winddirection": "ZW", "temperature": t,
         "windspeedBft": 4, "winddirectiondegrees": 225, "humidity": 84, "rainFallLastHour": 0.0}
        for i, (name, dla, dlo, t) in enumerate(stations)
    ]}}


def overpass(lat: float, lon: float) -> dict:
    rng = _rng(13)
    els = builders_more.overpass()["elements"]
    for i in range(10):
        la, lo = _around(rng, lat, lon, 8)
        els.append({"type": "node", "id": 100 + i, "lat": la, "lon": lo,
                    "tags": {"emergency": "defibrillator", "opening_hours": "24/7"}})
    return {"elements": els}


# --- request router -------------------------------------------------------------
def make_handler(lat: float, lon: float):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if "brandweer-berkel-enschot" in url:
            return httpx.Response(200, content=p2000_rss(lat, lon))
        if "ndw.nu" in url:
            live, plan = builders.bridge_feeds()
            if "actueel_beeld" in url or "incidents" in url:
                return httpx.Response(200, content=traffic(lat, lon))
            if "afsluitingen" in url:
                return httpx.Response(200, content=live)
            if "brugopeningen" in url:
                return httpx.Response(200, content=plan)
            if "wegwerkzaamheden" in url:
                return httpx.Response(200, content=builders.roadworks_feed())
            if "charging_point_locations_ocpi" in url:
                return httpx.Response(200, content=charging(lat, lon))
            if "dynamische_route_informatie_paneel" in url:
                return httpx.Response(200, content=builders_more.drip_combined())
        if "ovapi" in url and path.endswith("alerts.pb"):
            return httpx.Response(200, content=builders.alerts_pb(time.time()))
        if "ovapi" in url:
            return httpx.Response(200, content=vehicles(lat, lon))
        if "apiportal.ns.nl" in url:
            return httpx.Response(200, content=(DATA / "ns.json").read_bytes())
        if "adsb.lol" in url or "airplanes.live" in url:
            return httpx.Response(200, json=aircraft(lat, lon))
        if "ourairports" in url:
            return httpx.Response(200, content=airports(lat, lon))
        if "celestrak" in url:
            return httpx.Response(200, text=(DATA / "stations.tle").read_text())
        if "knmi" in url:
            return httpx.Response(200, text=(DATA / "knmi.txt").read_text())
        if "ufo-reports" in url:
            return httpx.Response(200, text=(DATA / "ufo.csv").read_text())
        if "api.windy.com" in url:
            return httpx.Response(200, content=(DATA / "windy.json").read_bytes())
        if "buienradar" in url:
            return httpx.Response(200, json=buienradar(lat, lon))
        if "rijkswaterstaat" in url:
            if "OphalenCatalogus" in url:
                return httpx.Response(200, json=builders_more.rws_catalogue())
            return httpx.Response(200, json=builders_more.rws_latest())
        if "overpass" in url:
            return httpx.Response(200, json=overpass(lat, lon))
        if "luchtmeetnet" in url:
            if path.endswith("/stations"):
                page = request.url.params.get("page")
                return httpx.Response(200, content=(DATA / f"lmn_stations_p{page}.json").read_bytes())
            if "/stations/" in path:
                return httpx.Response(200, content=(DATA / f"lmn_{path.rsplit('/', 1)[-1]}.json").read_bytes())
            return httpx.Response(200, content=(DATA / "lmn_lki.json").read_bytes())
        return httpx.Response(404, text="not in demo data")

    return handler


def enable(settings):
    """Return (settings, transport) for demo mode and stub out the two code paths
    that open their own connections or deliberately wait (stops.txt, Luchtmeetnet pacing)."""
    from app.sources import air, transit_alerts

    air.MIN_INTERVAL = 0

    async def demo_stops(self):
        self._stops = transit_alerts.parse_stops((DATA / "stops.txt").read_bytes(), self.region_box)
        self._stops_at = time.monotonic()

    transit_alerts.TransitAlertSource._load_stops = demo_stops
    demo_settings = dataclasses.replace(
        settings,
        aircraft_source="adsblol",  # the demo answers in readsb format
        ns_api_key=settings.ns_api_key or "demo",
        windy_api_key=settings.windy_api_key or "demo",
    )
    return demo_settings, httpx.MockTransport(make_handler(settings.center_lat, settings.center_lon))
