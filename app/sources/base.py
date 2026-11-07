"""Common plumbing for data sources: GeoJSON features, a TTL cache and status."""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import Settings
from app.geo import bbox

log = logging.getLogger(__name__)


def feature(
    *,
    source: str,
    fid: str,
    lat: float,
    lon: float,
    title: str,
    category: str = "",
    detail: str = "",
    time_iso: str | None = None,
    **extra: Any,
) -> dict:
    props = {
        "source": source,
        "id": f"{source}:{fid}",
        "title": title,
        "category": category,
        "detail": detail,
        "time": time_iso,
    }
    props.update({k: v for k, v in extra.items() if v is not None})
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(float(lon), 6), round(float(lat), 6)]},
        "properties": props,
    }


class Source(ABC):
    """One layer on the map. Subclasses implement `fetch`; caching is handled here."""

    name: str = ""
    label: str = ""
    ttl: float = 60.0          # seconds the fetched data stays fresh
    refresh_hint: float = 60.0  # how often the browser should poll this layer
    attribution: str = ""
    # False for sources whose first load takes minutes (e.g. a throttled crawl):
    # the first request then returns empty with status "loading" instead of hanging.
    blocking_first_load: bool = True

    def __init__(self, settings: Settings):
        self.settings = settings
        self.region_box = bbox(settings.center_lat, settings.center_lon, settings.region_radius_km)
        self._data: list[dict] = []
        self._fetched_at: float = 0.0
        self._last_error: str | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    # -- to implement -----------------------------------------------------
    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        """Return features for the configured region."""

    def configured(self) -> tuple[bool, str]:
        """(ok, reason). Override when a source needs a key."""
        return True, ""

    # -- shared -------------------------------------------------------------
    def postprocess(self, features: list[dict]) -> list[dict]:
        """Hook for sources that compute positions per request (satellites)."""
        return features

    def _fresh(self) -> bool:
        return bool(self._fetched_at) and time.monotonic() - self._fetched_at < self.ttl

    async def _refresh(self, client: httpx.AsyncClient) -> None:
        async with self._lock:
            if self._fresh():  # another caller refreshed while we waited
                return
            try:
                self._data = await self.fetch(client)
                self._last_error = None
            except Exception as exc:  # keep serving stale data on failure
                self._last_error = f"{type(exc).__name__}: {exc}"[:300]
                log.warning("source %s failed: %s", self.name, self._last_error)
            # Back off on errors too, so a dead upstream isn't hammered.
            self._fetched_at = time.monotonic()

    async def get(self, client: httpx.AsyncClient) -> list[dict]:
        """Stale-while-revalidate: only the very first load of a source waits for
        upstream (and not even that for slow sources); after that requests get the
        cached data immediately while a refresh runs in the background."""
        if not self.configured()[0]:
            return []
        if not self._fresh():
            first = not self._fetched_at
            if first and self.blocking_first_load:
                await self._refresh(client)
            elif self._task is None or self._task.done():
                self._task = asyncio.create_task(self._refresh(client))
        return self.postprocess(self._data)

    def status(self) -> dict:
        ok, reason = self.configured()
        age = None if not self._fetched_at else round(time.monotonic() - self._fetched_at, 1)
        return {
            "name": self.name,
            "label": self.label,
            "configured": ok,
            "reason": reason or None,
            "ttl": self.ttl,
            "refresh": self.refresh_hint,
            "cached_items": len(self._data),
            "loading": self._lock.locked(),
            "age_seconds": age,
            "last_error": self._last_error,
            "attribution": self.attribution,
        }
