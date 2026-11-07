"""neighbourhood-radar: one map with live open data around a point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import sources as source_registry
from app.config import settings
from app.geo import haversine_km

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    active, transport = settings, None
    if settings.demo:
        from app import demo

        active, transport = demo.enable(settings)
        logging.getLogger(__name__).warning("DEMO MODE: serving built-in sample data, no live feeds")
    app.state.demo = settings.demo
    app.state.client = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
        transport=transport,
    )
    app.state.sources = source_registry.build(active)
    yield
    await app.state.client.aclose()


app = FastAPI(title="neighbourhood-radar", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://*.basemaps.cartocdn.com https://*.windy.com; "
        "connect-src 'self'; frame-ancestors 'none'",
    )
    return resp


def _check_point(lat: float, lon: float, radius_km: float) -> None:
    if radius_km > settings.max_query_radius_km:
        raise HTTPException(400, f"radius_km may be at most {settings.max_query_radius_km}")


def _filter(features: list[dict], lat: float, lon: float, radius_km: float) -> list[dict]:
    out = []
    for f in features:
        flon, flat = f["geometry"]["coordinates"]
        d = haversine_km(lat, lon, flat, flon)
        if d <= radius_km:
            g = dict(f)
            g["properties"] = {**f["properties"], "distance_km": round(d, 2)}
            out.append(g)
    out.sort(key=lambda f: f["properties"]["distance_km"])
    return out


def _source(name: str):
    src = app.state.sources.get(name)
    if not src:
        raise HTTPException(404, f"unknown or disabled layer '{name}'")
    return src


@app.get("/api/config")
async def config():
    return {
        "demo": getattr(app.state, "demo", False),
        "center": {"lat": settings.center_lat, "lon": settings.center_lon},
        "region_radius_km": settings.region_radius_km,
        "max_query_radius_km": settings.max_query_radius_km,
        "layers": [s.status() for s in app.state.sources.values()],
    }


@app.get("/api/layers/{name}")
async def layer(
    name: str,
    lat: float = Query(settings.center_lat, ge=-90, le=90),
    lon: float = Query(settings.center_lon, ge=-180, le=180),
    radius_km: float = Query(25.0, gt=0),
):
    _check_point(lat, lon, radius_km)
    src = _source(name)
    feats = await src.get(app.state.client)
    return JSONResponse(
        {"type": "FeatureCollection", "features": _filter(feats, lat, lon, radius_km), "status": src.status()},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/summary")
async def summary(
    lat: float = Query(settings.center_lat, ge=-90, le=90),
    lon: float = Query(settings.center_lon, ge=-180, le=180),
    radius_km: float = Query(1.5, gt=0),
):
    """Counts per layer within radius_km of a point, e.g. '3 alerts within 1.5 km'."""
    _check_point(lat, lon, radius_km)
    srcs = list(app.state.sources.values())
    results = await asyncio.gather(*(s.get(app.state.client) for s in srcs))
    out = []
    for s, feats in zip(srcs, results):
        near = _filter(feats, lat, lon, radius_km)
        out.append(
            {
                "layer": s.name,
                "label": s.label,
                "count": len(near),
                "nearest": near[0]["properties"] if near else None,
                "error": s.status()["last_error"],
            }
        )
    return {"lat": lat, "lon": lon, "radius_km": radius_km, "layers": out}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/readyz")
async def readyz():
    return {"ok": hasattr(app.state, "sources")}


@app.get("/")
async def index():
    page = STATIC / "index.html"
    if not page.exists():
        return PlainTextResponse(
            "Frontend not built. Run: cd frontend && npm ci && npm run build", status_code=503
        )
    # Hashed assets can be cached forever; the page itself must not be.
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


# The React build (frontend/ -> app/static). check_dir=False so the API still
# starts when only the backend is installed.
app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
