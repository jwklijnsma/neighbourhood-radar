"""Live water levels from Rijkswaterstaat (DDAPI 2.0 waterwebservices, no key).

Once a day the catalogue tells us which measuring locations in the region report
water height (WATHTE, cm relative to NAP); then the latest measurement for all of
them is fetched in one request every 10 minutes.
"""
from __future__ import annotations

import time

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

BASE = "https://ddapi20-waterwebservices.rijkswaterstaat.nl"
CATALOGUE = f"{BASE}/METADATASERVICES/OphalenCatalogus"
LATEST = f"{BASE}/ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen"
CATALOGUE_TTL = 24 * 3600

WATER_HEIGHT = {
    "Compartiment": {"Code": "OW"},
    "Grootheid": {"Code": "WATHTE"},
    "Eenheid": {"Code": "cm"},
    "Hoedanigheid": {"Code": "NAP"},
}


def _code(meta: dict, key: str) -> str:
    v = meta.get(key)
    if isinstance(v, dict):
        return (v.get("Code") or "").upper()
    return (v or "").upper() if isinstance(v, str) else ""


def stations_from_catalogue(cat: dict, box=None) -> dict[str, dict]:
    """Locations that report water height relative to NAP, keyed by location code."""
    metas = {
        m.get("AquoMetadata_MessageID"): m
        for m in cat.get("AquoMetadataLijst") or []
        if _code(m, "Grootheid") == "WATHTE" and _code(m, "Hoedanigheid") == "NAP"
        and _code(m, "Compartiment") == "OW"
    }
    wanted = {
        link.get("Locatie_MessageID")
        for link in cat.get("AquoMetadataLocatieLijst") or []
        if link.get("AquoMetaData_MessageID") in metas
    }
    out = {}
    for loc in cat.get("LocatieLijst") or []:
        if loc.get("Locatie_MessageID") not in wanted:
            continue
        lat, lon = loc.get("Lat"), loc.get("Lon")
        if not valid_coord(lat, lon):
            continue
        lat, lon = float(lat), float(lon)
        if box and not in_bbox(lat, lon, box):
            continue
        out[loc["Code"]] = {"code": loc["Code"], "name": loc.get("Naam") or loc["Code"], "lat": lat, "lon": lon}
    return out


def parse_latest(data: dict, stations: dict) -> list[dict]:
    best: dict[str, tuple] = {}
    for w in (data or {}).get("WaarnemingenLijst") or []:
        meta = w.get("AquoMetadata") or {}
        proc = (meta.get("ProcesType") or "").lower() if isinstance(meta.get("ProcesType"), str) else ""
        if proc and proc != "meting":
            continue  # skip forecasts / astronomical tide
        loc = w.get("Locatie") or {}
        st = stations.get(loc.get("Code")) or (
            {"code": loc.get("Code"), "name": loc.get("Naam"), "lat": float(loc["Lat"]), "lon": float(loc["Lon"])}
            if valid_coord(loc.get("Lat"), loc.get("Lon")) else None
        )
        if not st:
            continue
        for m in w.get("MetingenLijst") or []:
            if ((m.get("WaarnemingMetadata") or {}).get("Kwaliteitswaardecode") or "") == "99":
                continue  # RWS marks missing values with quality code 99
            v = (m.get("Meetwaarde") or {}).get("Waarde_Numeriek")
            if not isinstance(v, (int, float)) or abs(v) > 5000:  # 999999999 = missing
                continue
            t = m.get("Tijdstip")
            if st["code"] not in best or (t or "") > (best[st["code"]][1] or ""):
                best[st["code"]] = (v, t, st)
    out = []
    for v, t, st in best.values():
        sign = "+" if v > 0 else ""
        out.append(
            feature(
                source="water",
                fid=st["code"],
                lat=st["lat"],
                lon=st["lon"],
                title=f"{st['name']}: {sign}{v:.0f} cm NAP",
                category="high" if v >= 100 else "low" if v <= -100 else "normal",
                detail="Waterstand t.o.v. NAP",
                time_iso=t,
                level_cm=v,
            )
        )
    return out


class WaterLevelSource(Source):
    name = "water"
    label = "Waterstanden (RWS)"
    ttl = 600
    refresh_hint = 600
    attribution = "Waterstanden: Rijkswaterstaat"

    def __init__(self, settings):
        super().__init__(settings)
        self._stations: dict = {}
        self._stations_at = 0.0

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        if not self._stations or time.monotonic() - self._stations_at > CATALOGUE_TTL:
            r = await client.post(
                CATALOGUE,
                json={"CatalogusFilter": {"Grootheden": True, "Eenheden": True, "Compartimenten": True,
                                          "Hoedanigheden": True}},
                timeout=120,
            )
            r.raise_for_status()
            self._stations = stations_from_catalogue(r.json(), self.region_box)
            self._stations_at = time.monotonic()
        if not self._stations:
            return []
        r = await client.post(
            LATEST,
            json={
                "AquoPlusWaarnemingMetadataLijst": [{"AquoMetadata": WATER_HEIGHT}],
                "LocatieLijst": [{"Code": c} for c in self._stations],
            },
            timeout=60,
        )
        if r.status_code == 204:
            return []
        r.raise_for_status()
        return parse_latest(r.json(), self._stations)
