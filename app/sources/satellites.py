"""Satellites currently above the horizon, propagated with SGP4 from CelesTrak TLEs.

TLEs are fetched rarely (every 6 h); positions are recomputed on every request,
so the markers move even though the upstream data is cached.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import httpx
from sgp4.api import Satrec, jday

from app.sources.base import Source, feature

GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
WGS84_A = 6378.137
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def parse_tle(text: str) -> list[tuple[str, Satrec]]:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    sats = []
    i = 0
    while i + 2 < len(lines):
        name, l1, l2 = lines[i].strip(), lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            sats.append((name, Satrec.twoline2rv(l1, l2)))
            i += 3
        else:
            i += 1
    return sats


def _gmst(jd_ut1: float) -> float:
    """Greenwich mean sidereal time in radians (IAU 1982)."""
    t = (jd_ut1 - 2451545.0) / 36525.0
    g = 67310.54841 + (876600 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t**3
    return math.radians((g % 86400) / 240.0)


def _ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - WGS84_E2))
    for _ in range(5):
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + h)))
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def _geodetic_to_ecef(lat: float, lon: float, h: float = 0.0) -> tuple[float, float, float]:
    la, lo = math.radians(lat), math.radians(lon)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(la) ** 2)
    return (
        (n + h) * math.cos(la) * math.cos(lo),
        (n + h) * math.cos(la) * math.sin(lo),
        (n * (1 - WGS84_E2) + h) * math.sin(la),
    )


def position(sat: Satrec, when: datetime) -> tuple[float, float, float] | None:
    """Sub-satellite point (lat, lon, altitude km) or None if propagation fails."""
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute, when.second + when.microsecond / 1e6)
    err, r, _ = sat.sgp4(jd, fr)
    if err != 0:
        return None
    th = _gmst(jd + fr)
    c, s = math.cos(th), math.sin(th)
    x, y = c * r[0] + s * r[1], -s * r[0] + c * r[1]  # TEME -> ECEF (polar motion ignored)
    return _ecef_to_geodetic(x, y, r[2])


def elevation_deg(obs_lat: float, obs_lon: float, sat_lat: float, sat_lon: float, sat_alt: float) -> float:
    ox, oy, oz = _geodetic_to_ecef(obs_lat, obs_lon)
    sx, sy, sz = _geodetic_to_ecef(sat_lat, sat_lon, sat_alt)
    dx, dy, dz = sx - ox, sy - oy, sz - oz
    la, lo = math.radians(obs_lat), math.radians(obs_lon)
    up = math.cos(la) * math.cos(lo) * dx + math.cos(la) * math.sin(lo) * dy + math.sin(la) * dz
    return math.degrees(math.asin(up / math.sqrt(dx * dx + dy * dy + dz * dz)))


def visible(sats, obs_lat: float, obs_lon: float, min_elev: float, when: datetime | None = None) -> list[dict]:
    when = when or datetime.now(timezone.utc)
    out = []
    for name, sat in sats:
        p = position(sat, when)
        if not p:
            continue
        lat, lon, alt = p
        el = elevation_deg(obs_lat, obs_lon, lat, lon, alt)
        if el < min_elev:
            continue
        out.append(
            feature(
                source="satellites",
                fid=str(sat.satnum),
                lat=lat,
                lon=lon,
                title=name,
                category="iss" if sat.satnum == 25544 else "satellite",
                detail=f"{round(alt)} km hoog · {round(el)}° boven de horizon",
                time_iso=when.isoformat(),
                elevation_deg=round(el, 1),
                altitude_km=round(alt),
                norad=sat.satnum,
            )
        )
    return out


class SatelliteSource(Source):
    name = "satellites"
    label = "Satellieten"
    ttl = 6 * 3600
    refresh_hint = 15
    attribution = "Satellieten: CelesTrak"

    def __init__(self, settings):
        super().__init__(settings)
        self._sats: list[tuple[str, Satrec]] = []

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        sats: dict[int, tuple[str, Satrec]] = {}
        for group in self.settings.celestrak_groups:
            r = await client.get(GP_URL, params={"GROUP": group, "FORMAT": "tle"})
            r.raise_for_status()
            for name, s in parse_tle(r.text):
                sats[s.satnum] = (name, s)
        self._sats = list(sats.values())
        return [{"name": n} for n, _ in self._sats]  # cache marker; positions come later

    def postprocess(self, _features):
        return visible(
            self._sats,
            self.settings.center_lat,
            self.settings.center_lon,
            self.settings.sat_min_elevation_deg,
        )
