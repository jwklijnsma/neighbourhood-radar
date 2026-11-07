from app.config import Settings
from app.sources.base import Source
from app.sources.gtfs_vehicles import GTFSVehicleSource
from app.sources.knmi import KNMIQuakeSource
from app.sources.ndw import NDWIncidentSource
from app.sources.ns import NSDisruptionSource
from app.sources.opensky import OpenSkySource
from app.sources.p2000 import P2000Source
from app.sources.satellites import SatelliteSource

ALL = [
    P2000Source,
    NDWIncidentSource,
    GTFSVehicleSource,
    NSDisruptionSource,
    OpenSkySource,
    SatelliteSource,
    KNMIQuakeSource,
]


def build(settings: Settings) -> dict[str, Source]:
    out = {}
    for cls in ALL:
        if settings.enabled(cls.name):
            out[cls.name] = cls(settings)
    return out
