"""NS train disruptions and engineering works, pinned on the affected stations."""
from __future__ import annotations

import httpx

from app.geo import in_bbox, valid_coord
from app.sources.base import Source, feature

URL = "https://gateway.apiportal.ns.nl/disruptions/v3"


def parse(items: list[dict], box=None) -> list[dict]:
    out = []
    for d in items or []:
        if d.get("isActive") is False:
            continue
        did = str(d.get("id", ""))
        dtype = (d.get("type") or "").upper()
        category = {"CALAMITY": "calamity", "DISRUPTION": "disruption", "MAINTENANCE": "maintenance"}.get(
            dtype, "disruption"
        )
        title = d.get("title") or "Treinstoring"
        detail = ""
        tc = d.get("timespans") or []
        if tc and isinstance(tc[0], dict):
            detail = (tc[0].get("situation") or {}).get("label", "") or ""
        if not detail:
            detail = (d.get("situation") or {}).get("label", "") if isinstance(d.get("situation"), dict) else ""
        seen = set()
        for pub in d.get("publicationSections") or []:
            stations = ((pub.get("section") or {}).get("stations")) or []
            for st in stations:
                coord = st.get("coordinate") or {}
                lat, lon = coord.get("lat"), coord.get("lng")
                code = st.get("stationCode") or st.get("uicCode") or st.get("name")
                if code in seen or not valid_coord(lat, lon):
                    continue
                seen.add(code)
                if box and not in_bbox(float(lat), float(lon), box):
                    continue
                out.append(
                    feature(
                        source="trains",
                        fid=f"{did}:{code}",
                        lat=float(lat),
                        lon=float(lon),
                        title=title,
                        category=category,
                        detail=f"{st.get('name', code)}: {detail}".strip(": "),
                        time_iso=d.get("start"),
                        station=st.get("name"),
                    )
                )
    return out


class NSDisruptionSource(Source):
    name = "trains"
    label = "Treinstoringen (NS)"
    ttl = 120
    refresh_hint = 120
    attribution = "Treinen: NS API"

    def configured(self):
        if not self.settings.ns_api_key:
            return False, "OL_NS_API_KEY not set (free key at apiportal.ns.nl, product Ns-App)"
        return True, ""

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        if not self.settings.ns_api_key:
            return []
        r = await client.get(
            URL,
            params={"isActive": "true"},
            headers={"Ocp-Apim-Subscription-Key": self.settings.ns_api_key},
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):  # some versions wrap the list
            data = data.get("payload") or data.get("disruptions") or []
        return parse(data, self.region_box)
