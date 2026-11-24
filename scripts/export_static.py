"""Export a static snapshot of the API for GitHub Pages.

GitHub Pages only serves files, so instead of the FastAPI backend this writes
what the backend would answer to plain JSON files:

    OUT/api/config.json          same as GET /api/config (+ "static" info)
    OUT/api/layers/<name>.json   every feature in the region for that layer

The frontend, built with VITE_STATIC_API=1, reads these and does the distance
filtering in the browser.

Usage:
    OL_DEMO=1 python scripts/export_static.py _site      # sample data
    python scripts/export_static.py _site                # live snapshot

OL_EXPORT_TIMEOUT (seconds, default 90) caps how long one source may take.
Slow sources (air quality's first crawl takes ~6 minutes) are skipped with
an error in their status when they don't finish in time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sources as source_registry  # noqa: E402
from app.config import settings  # noqa: E402

log = logging.getLogger("export_static")


async def _load(src, client: httpx.AsyncClient, timeout: float) -> None:
    if not src.configured()[0]:
        return
    try:
        await asyncio.wait_for(src._refresh(client), timeout)
    except asyncio.TimeoutError:
        src._last_error = f"Timeout: no data within {timeout:.0f} s while building the snapshot"
        log.warning("source %s timed out", src.name)


async def export(out: Path) -> int:
    active, transport = settings, None
    if settings.demo:
        from app import demo

        active, transport = demo.enable(settings)
    timeout = float(os.environ.get("OL_EXPORT_TIMEOUT", "90"))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
        transport=transport,
    ) as client:
        srcs = source_registry.build(active)
        await asyncio.gather(*(_load(s, client, timeout) for s in srcs.values()))

        layers_dir = out / "api" / "layers"
        layers_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for name, src in srcs.items():
            feats = src.postprocess(src._data) if src.configured()[0] else []
            total += len(feats)
            body = {"type": "FeatureCollection", "features": feats, "status": src.status()}
            (layers_dir / f"{name}.json").write_text(json.dumps(body, separators=(",", ":")))
            log.info("%-10s %5d features%s", name, len(feats),
                     f"  ({src._last_error})" if src._last_error else "")

        cfg = {
            "demo": settings.demo,
            "static": {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            "tiles": {"url": settings.tile_url, "attribution": settings.tile_attribution},
            "center": {"lat": settings.center_lat, "lon": settings.center_lon},
            "region_radius_km": settings.region_radius_km,
            "max_query_radius_km": min(settings.max_query_radius_km, settings.region_radius_km),
            "layers": [s.status() for s in srcs.values()],
        }
        (out / "api" / "config.json").write_text(json.dumps(cfg, separators=(",", ":")))
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    total = asyncio.run(export(out))
    log.info("wrote %d features to %s", total, out / "api")
    if total == 0:
        sys.exit("No features at all: every source failed, not publishing an empty map")


if __name__ == "__main__":
    main()
