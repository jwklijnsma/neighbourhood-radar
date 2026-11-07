"""Aircraft from the OpenSky Network state-vector API.

Credit budget: a box under 25 square degrees costs 1 credit. Anonymous clients
get 400/day, so the default TTL (240 s) stays under that even if someone keeps
the page open all day. With OAuth2 client credentials (4000/day) the TTL drops to 30 s.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.geo import valid_coord
from app.sources.base import Source, feature

STATES_URL = "https://opensky-network.org/api/states/all"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"


def parse(data: dict) -> list[dict]:
    out = []
    for s in (data or {}).get("states") or []:
        # https://openskynetwork.github.io/opensky-api/rest.html#response
        icao, callsign, country = s[0], (s[1] or "").strip(), s[2]
        lon, lat = s[5], s[6]
        if not valid_coord(lat, lon):
            continue
        on_ground = bool(s[8])
        alt = s[13] if s[13] is not None else s[7]
        speed = s[9]
        ts = datetime.fromtimestamp(s[4], tz=timezone.utc).isoformat() if s[4] else None
        detail = []
        if alt is not None:
            detail.append(f"{round(alt * 3.28084):,} ft".replace(",", "."))
        if speed is not None:
            detail.append(f"{round(speed * 3.6)} km/u")
        detail.append(country)
        out.append(
            feature(
                source="aircraft",
                fid=icao,
                lat=lat,
                lon=lon,
                title=callsign or icao.upper(),
                category="ground" if on_ground else "airborne",
                detail=" · ".join(d for d in detail if d),
                time_iso=ts,
                heading=round(s[10]) if s[10] is not None else None,
                altitude_m=round(alt) if alt is not None else None,
            )
        )
    return out


class OpenSkySource(Source):
    name = "aircraft"
    label = "Vliegtuigen"
    attribution = "Vliegtuigen: The OpenSky Network"

    def __init__(self, settings):
        super().__init__(settings)
        self._authed = bool(settings.opensky_client_id and settings.opensky_client_secret)
        self.ttl = 30 if self._authed else 240
        self.refresh_hint = self.ttl
        self._token: str | None = None
        self._token_exp = 0.0

    async def _auth_header(self, client: httpx.AsyncClient) -> dict:
        if not self._authed:
            return {}
        if not self._token or time.monotonic() > self._token_exp:
            r = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.opensky_client_id,
                    "client_secret": self.settings.opensky_client_secret,
                },
            )
            r.raise_for_status()
            tok = r.json()
            self._token = tok["access_token"]
            self._token_exp = time.monotonic() + int(tok.get("expires_in", 1800)) - 60
        return {"Authorization": f"Bearer {self._token}"}

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        lamin, lomin, lamax, lomax = self.region_box
        r = await client.get(
            STATES_URL,
            params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax},
            headers=await self._auth_header(client),
        )
        r.raise_for_status()
        return parse(r.json())
