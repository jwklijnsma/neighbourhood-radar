"""Aircraft from one of several providers, normalised to the same map features.

Providers (OL_AIRCRAFT_SOURCE):
  adsblol        https://api.adsb.lol    open data (ODbL), no key            [default]
  airplaneslive  https://api.airplanes.live  no key, non-commercial only
  readsb         your own receiver's aircraft.json (readsb, dump1090-fa, tar1090)
  opensky        OpenSky Network state vectors
  fr24           Flightradar24 official API, paid subscription (Bearer token)

adsb.lol, airplanes.live and a local readsb all speak the readsb JSON format,
so they share one parser. Positions from successive fetches are kept for a few
minutes and sent along as a trail, like on Flightradar24.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

KM_PER_NM = 1.852

# readsb "emergency" values and squawk codes -> Dutch label
EMERGENCY_LABEL = {
    "general": "Noodgeval",
    "lifeguard": "Medische vlucht met voorrang",
    "minfuel": "Brandstoftekort",
    "nordo": "Geen radiocontact",
    "unlawful": "Kaping",
    "downed": "Neergestort",
}
SQUAWK_EMERGENCY = {"7500": "Kaping (squawk 7500)", "7600": "Radiostoring (squawk 7600)",
                    "7700": "Noodgeval (squawk 7700)"}

# ICAO type designators of common helicopters (ADS-B emitter category A7 also counts).
HELI_TYPES = {
    "EC20", "EC30", "EC35", "EC45", "EC55", "EC75", "H160", "H175", "AS32", "AS50", "AS55",
    "AS65", "A109", "A119", "A139", "A169", "A189", "AW09", "B06", "B407", "B429", "B412",
    "S76", "S92", "R22", "R44", "R66", "NH90", "H60", "CH47", "EH10", "MD52", "MD60", "B505",
}


@dataclass
class Plane:
    hex: str
    lat: float
    lon: float
    callsign: str = ""
    reg: str = ""
    type: str = ""
    desc: str = ""
    operator: str = ""
    alt_ft: int | None = None
    on_ground: bool = False
    gs_kt: float | None = None
    track: float | None = None
    vrate_fpm: int | None = None
    squawk: str = ""
    emergency: str = ""        # readsb emergency value, "" when none
    emitter: str = ""          # ADS-B emitter category, e.g. "A3", "A7"
    military: bool = False
    origin: str = ""
    destination: str = ""
    ts: str | None = None
    link: str | None = None


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- parsers ------------------------------------------------------------------------
def parse_readsb(data: dict, now: float | None = None, link_base: str | None = None,
                 max_age_s: float = 60) -> list[Plane]:
    """readsb JSON: api.adsb.lol / api.airplanes.live ("ac") or a local aircraft.json ("aircraft")."""
    now = now or time.time()
    base_ts = _float((data or {}).get("now"))
    if base_ts and base_ts > 1e12:  # the APIs give milliseconds, aircraft.json seconds
        base_ts /= 1000
    base_ts = base_ts or now
    out = []
    for a in (data or {}).get("ac") or (data or {}).get("aircraft") or []:
        lat, lon = a.get("lat"), a.get("lon")
        if not valid_coord(lat, lon):
            lp = a.get("lastPosition") or {}
            lat, lon = lp.get("lat"), lp.get("lon")
            if not valid_coord(lat, lon):
                continue
        seen_pos = _float(a.get("seen_pos")) or 0.0
        if seen_pos > max_age_s:
            continue  # stale position
        alt = a.get("alt_baro")
        on_ground = alt == "ground"
        hexid = (a.get("hex") or "").lower().lstrip("~")
        emergency = (a.get("emergency") or "").lower()
        out.append(
            Plane(
                hex=hexid,
                lat=float(lat),
                lon=float(lon),
                callsign=(a.get("flight") or "").strip(),
                reg=(a.get("r") or "").strip(),
                type=(a.get("t") or "").strip().upper(),
                desc=(a.get("desc") or "").strip(),
                operator=(a.get("ownOp") or "").strip(),
                alt_ft=None if on_ground else _int(alt if alt is not None else a.get("alt_geom")),
                on_ground=on_ground,
                gs_kt=_float(a.get("gs")),
                track=_float(a.get("track") if a.get("track") is not None else a.get("true_heading")),
                vrate_fpm=_int(a.get("baro_rate") if a.get("baro_rate") is not None else a.get("geom_rate")),
                squawk=str(a.get("squawk") or ""),
                emergency="" if emergency in ("", "none") else emergency,
                emitter=(a.get("category") or "").upper(),
                military=bool((_int(a.get("dbFlags")) or 0) & 1),
                ts=datetime.fromtimestamp(base_ts - seen_pos, tz=timezone.utc).isoformat(),
                link=f"{link_base}{hexid}" if link_base and hexid else None,
            )
        )
    return out


def parse_opensky(data: dict) -> list[Plane]:
    out = []
    for s in (data or {}).get("states") or []:
        # https://openskynetwork.github.io/opensky-api/rest.html#response
        lon, lat = s[5], s[6]
        if not valid_coord(lat, lon):
            continue
        alt_m = s[13] if s[13] is not None else s[7]
        category = s[17] if len(s) > 17 else None
        out.append(
            Plane(
                hex=(s[0] or "").lower(),
                lat=float(lat),
                lon=float(lon),
                callsign=(s[1] or "").strip(),
                operator=s[2] or "",           # origin country; OpenSky has no operator
                alt_ft=None if s[8] or alt_m is None else round(alt_m * 3.28084),
                on_ground=bool(s[8]),
                gs_kt=s[9] / 0.514444 if s[9] is not None else None,
                track=s[10],
                vrate_fpm=round(s[11] * 196.85) if s[11] is not None else None,
                squawk=s[14] or "",
                emitter="A7" if category == 8 else "",
                ts=datetime.fromtimestamp(s[4], tz=timezone.utc).isoformat() if s[4] else None,
            )
        )
    return out


def parse_fr24(data: dict) -> list[Plane]:
    out = []
    for f in (data or {}).get("data") or []:
        lat, lon = f.get("lat"), f.get("lon")
        if not valid_coord(lat, lon):
            continue
        alt = _int(f.get("alt"))
        gs = _float(f.get("gspeed"))
        callsign = (f.get("callsign") or "").strip()
        fid = f.get("fr24_id") or ""
        link = None
        if fid and callsign:
            link = f"https://www.flightradar24.com/{callsign}/{fid}"
        elif f.get("reg"):
            link = f"https://www.flightradar24.com/data/aircraft/{f['reg'].lower()}"
        out.append(
            Plane(
                hex=(f.get("hex") or fid).lower(),
                lat=float(lat),
                lon=float(lon),
                callsign=callsign or (f.get("flight") or ""),
                reg=f.get("reg") or "",
                type=(f.get("type") or "").upper(),
                operator=f.get("operating_as") or f.get("painted_as") or "",
                alt_ft=alt,
                on_ground=(alt is not None and alt <= 0 and (gs or 0) < 50),
                gs_kt=gs,
                track=_float(f.get("track")),
                vrate_fpm=_int(f.get("vspeed")),
                squawk=str(f.get("squawk") or ""),
                origin=f.get("orig_iata") or f.get("orig_icao") or "",
                destination=f.get("dest_iata") or f.get("dest_icao") or "",
                ts=f.get("timestamp"),
                link=link,
            )
        )
    return out


# --- feature -------------------------------------------------------------------------
def emergency_text(p: Plane) -> str:
    if p.emergency:
        return EMERGENCY_LABEL.get(p.emergency, f"Noodsituatie ({p.emergency})")
    return SQUAWK_EMERGENCY.get(p.squawk, "")


def is_helicopter(p: Plane) -> bool:
    return p.emitter == "A7" or p.type in HELI_TYPES


def category(p: Plane) -> str:
    if emergency_text(p):
        return "emergency"
    if is_helicopter(p):
        return "helicopter"
    if p.on_ground:
        return "ground"
    if p.military:
        return "military"
    return "airborne"


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def to_feature(p: Plane, trail: list | None = None) -> dict:
    who = " · ".join(x for x in [p.type, p.reg, p.operator] if x)
    route = f"{p.origin} → {p.destination}" if p.origin and p.destination else ""
    motion = []
    if p.on_ground:
        motion.append("aan de grond")
    elif p.alt_ft is not None:
        motion.append(f"{_thousands(p.alt_ft)} ft ({_thousands(round(p.alt_ft * 0.3048))} m)")
    if p.gs_kt is not None and not (p.on_ground and p.gs_kt < 1):
        motion.append(f"{round(p.gs_kt * KM_PER_NM)} km/u")
    if p.vrate_fpm is not None and not p.on_ground and abs(p.vrate_fpm) >= 300:
        motion.append("klimt" if p.vrate_fpm > 0 else "daalt")
    emergency = emergency_text(p)
    lines = [emergency, route, who, " · ".join(motion)]
    title = p.callsign or p.reg or p.hex.upper()
    return feature(
        source="aircraft",
        fid=p.hex or f"{p.lat:.4f},{p.lon:.4f}",
        lat=p.lat,
        lon=p.lon,
        title=f"{title} ({p.desc})" if p.desc and len(p.desc) < 30 else title,
        category=category(p),
        detail=" · ".join(x for x in lines if x),
        time_iso=p.ts,
        heading=round(p.track) if p.track is not None else None,
        altitude_m=round(p.alt_ft * 0.3048) if p.alt_ft is not None else None,
        squawk=p.squawk or None,
        url=p.link,
        trail=trail if trail and len(trail) > 1 else None,
    )


# --- source ------------------------------------------------------------------------------
PROVIDERS = {
    # name: (default ttl seconds, attribution)
    "adsblol": (15, "Vliegtuigen: adsb.lol (ODbL)"),
    "airplaneslive": (15, "Vliegtuigen: airplanes.live"),
    "readsb": (5, "Vliegtuigen: eigen ADS-B-ontvanger"),
    "opensky": (240, "Vliegtuigen: The OpenSky Network"),
    "fr24": (60, "Vliegtuigen: Flightradar24"),
}

OPENSKY_STATES = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
FR24_BASE = "https://fr24api.flightradar24.com/api/live/flight-positions"


def resolve_provider(settings) -> str:
    choice = settings.aircraft_source or "auto"
    if choice != "auto":
        return choice
    if settings.fr24_api_token:
        return "fr24"
    if settings.readsb_url:
        return "readsb"
    return "adsblol"


class AircraftSource(Source):
    name = "aircraft"
    label = "Vliegtuigen"

    def __init__(self, settings):
        super().__init__(settings)
        self.provider = resolve_provider(settings)
        default_ttl, self.attribution = PROVIDERS.get(self.provider, (30, "Vliegtuigen"))
        if self.provider == "opensky" and settings.opensky_client_id and settings.opensky_client_secret:
            default_ttl = 30  # 4000 credits/day with an OAuth client
        self.ttl = settings.aircraft_ttl or default_ttl
        self.refresh_hint = max(10, self.ttl)
        self._trails: dict[str, deque] = {}
        self._token: str | None = None
        self._token_exp = 0.0

    def configured(self):
        if self.provider not in PROVIDERS:
            return False, f"unknown OL_AIRCRAFT_SOURCE '{self.provider}'"
        if self.provider == "fr24" and not self.settings.fr24_api_token:
            return False, "OL_FR24_API_TOKEN not set (Flightradar24 API subscription)"
        if self.provider == "readsb" and not self.settings.readsb_url:
            return False, "OL_READSB_URL not set (e.g. http://receiver/tar1090/data/aircraft.json)"
        return True, ""

    # -- provider calls --------------------------------------------------------------
    def _radius_nm(self) -> int:
        return max(1, min(250, round(self.settings.region_radius_km / KM_PER_NM)))

    async def _fetch_planes(self, client: httpx.AsyncClient) -> list[Plane]:
        s, lat, lon = self.settings, self.settings.center_lat, self.settings.center_lon
        if self.provider in ("adsblol", "airplaneslive"):
            host, link = {
                "adsblol": ("https://api.adsb.lol", "https://adsb.lol/?icao="),
                "airplaneslive": ("https://api.airplanes.live", "https://globe.airplanes.live/?icao="),
            }[self.provider]
            r = await client.get(f"{host}/v2/point/{lat:.4f}/{lon:.4f}/{self._radius_nm()}")
            r.raise_for_status()
            return parse_readsb(r.json(), link_base=link)
        if self.provider == "readsb":
            r = await client.get(s.readsb_url)
            r.raise_for_status()
            return parse_readsb(r.json())
        if self.provider == "fr24":
            north, south = self.region_box[2], self.region_box[0]
            west, east = self.region_box[1], self.region_box[3]
            endpoint = "light" if s.fr24_endpoint == "light" else "full"
            r = await client.get(
                f"{FR24_BASE}/{endpoint}",
                params={"bounds": f"{north:.3f},{south:.3f},{west:.3f},{east:.3f}"},
                headers={"Accept": "application/json", "Accept-Version": "v1",
                         "Authorization": f"Bearer {s.fr24_api_token}"},
            )
            r.raise_for_status()
            return parse_fr24(r.json())
        if self.provider == "opensky":
            lamin, lomin, lamax, lomax = self.region_box
            r = await client.get(
                OPENSKY_STATES,
                params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax, "extended": 1},
                headers=await self._opensky_auth(client),
            )
            r.raise_for_status()
            return parse_opensky(r.json())
        raise ValueError(f"unknown aircraft provider {self.provider!r}")

    async def _opensky_auth(self, client: httpx.AsyncClient) -> dict:
        s = self.settings
        if not (s.opensky_client_id and s.opensky_client_secret):
            return {}
        if not self._token or time.monotonic() > self._token_exp:
            r = await client.post(OPENSKY_TOKEN, data={
                "grant_type": "client_credentials",
                "client_id": s.opensky_client_id,
                "client_secret": s.opensky_client_secret,
            })
            r.raise_for_status()
            tok = r.json()
            self._token = tok["access_token"]
            self._token_exp = time.monotonic() + int(tok.get("expires_in", 1800)) - 60
        return {"Authorization": f"Bearer {self._token}"}

    # -- trails -----------------------------------------------------------------------
    def _update_trails(self, planes: list[Plane], now: float) -> None:
        keep = self.settings.aircraft_trail_minutes * 60
        for p in planes:
            if not p.hex:
                continue
            t = self._trails.setdefault(p.hex, deque(maxlen=120))
            point = (now, round(p.lat, 4), round(p.lon, 4))
            if not t or t[-1][1:] != point[1:]:
                t.append(point)
        for hexid in list(self._trails):
            t = self._trails[hexid]
            while t and now - t[0][0] > keep:
                t.popleft()
            if not t:
                del self._trails[hexid]

    def trail(self, hexid: str) -> list | None:
        if not self.settings.aircraft_trail_minutes:
            return None
        t = self._trails.get(hexid)
        return [[lat, lon] for _, lat, lon in t] if t else None

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        planes = [p for p in await self._fetch_planes(client) if in_bbox(p.lat, p.lon, self.region_box)]
        self._update_trails(planes, time.monotonic())
        return [to_feature(p, self.trail(p.hex)) for p in planes]
