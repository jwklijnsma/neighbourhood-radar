"""Public webcams from the Windy Webcams API v3 (free key: api.windy.com/keys).

Free-tier image URLs carry a token that expires after 10 minutes, so the cache
TTL stays well under that and images are always fetched fresh by the browser.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.geo import valid_coord
from app.sources.base import Source, feature

URL = "https://api.windy.com/webcams/api/v3/webcams"
PAGE = 50          # API maximum per request
MAX_PAGES = 4      # 200 webcams is plenty for one region


def _https(url) -> str | None:
    return url if isinstance(url, str) and url.startswith("https://") else None


def parse(data: dict) -> list[dict]:
    out = []
    for w in (data or {}).get("webcams") or []:
        loc = w.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if not valid_coord(lat, lon):
            continue
        cur = ((w.get("images") or {}).get("current")) or {}
        image = _https(cur.get("preview")) or _https(cur.get("thumbnail")) or _https(cur.get("icon"))
        urls = w.get("urls") or {}
        link = _https(urls.get("detail")) or _https((w.get("player") or {}).get("day"))
        updated = w.get("lastUpdatedOn")
        if isinstance(updated, (int, float)):
            updated = datetime.fromtimestamp(updated, tz=timezone.utc).isoformat()
        out.append(
            feature(
                source="webcams",
                fid=str(w.get("webcamId", "")),
                lat=float(lat),
                lon=float(lon),
                title=w.get("title") or "Webcam",
                category="webcam",
                detail=", ".join(p for p in [loc.get("city"), loc.get("region")] if p),
                time_iso=updated if isinstance(updated, str) else None,
                image=image,
                url=link,
            )
        )
    return out


class WebcamSource(Source):
    name = "webcams"
    label = "Webcams"
    ttl = 300
    refresh_hint = 300
    attribution = "Webcams: windy.com"

    def configured(self):
        if not self.settings.windy_api_key:
            return False, "OL_WINDY_API_KEY not set (free key at api.windy.com/keys)"
        return True, ""

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        radius = min(250, round(self.settings.region_radius_km))
        out = []
        for page in range(MAX_PAGES):
            r = await client.get(
                URL,
                params={
                    "nearby": f"{self.settings.center_lat},{self.settings.center_lon},{radius}",
                    "include": "images,location,urls,player",
                    "limit": PAGE,
                    "offset": page * PAGE,
                },
                headers={"X-WINDY-API-KEY": self.settings.windy_api_key},
            )
            r.raise_for_status()
            data = r.json()
            out.extend(parse(data))
            if len(data.get("webcams") or []) < PAGE:
                break
        return out
