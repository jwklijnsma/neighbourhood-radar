"""Small geodesy helpers (WGS84 sphere approximation is plenty for map filtering)."""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """(lamin, lomin, lamax, lomax) of a box enclosing the circle."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.01, math.cos(math.radians(lat))))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def in_bbox(lat: float, lon: float, box: tuple[float, float, float, float]) -> bool:
    lamin, lomin, lamax, lomax = box
    return lamin <= lat <= lamax and lomin <= lon <= lomax


def valid_coord(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)
