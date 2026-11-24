from app.config import Settings
from app.sources.air import AirQualitySource
from app.sources.aircraft import AircraftSource
from app.sources.airports import AirportSource
from app.sources.base import Source
from app.sources.charging import ChargingSource
from app.sources.drips import DripSource
from app.sources.gtfs_vehicles import GTFSVehicleSource
from app.sources.knmi import KNMIQuakeSource
from app.sources.ndw import NDWBridgeSource, NDWIncidentSource, NDWRoadworksSource
from app.sources.ns import NSDisruptionSource
from app.sources.osm import SafetyPointsSource
from app.sources.p2000 import P2000Source
from app.sources.satellites import SatelliteSource
from app.sources.transit_alerts import TransitAlertSource
from app.sources.ufo import UFOSource
from app.sources.water import WaterLevelSource
from app.sources.weather import WeatherSource
from app.sources.webcams import WebcamSource

# Order is the order of the layer list in the UI.
ALL = [
    P2000Source,
    NDWIncidentSource,
    NDWBridgeSource,
    NDWRoadworksSource,
    DripSource,
    TransitAlertSource,
    GTFSVehicleSource,
    NSDisruptionSource,
    WebcamSource,
    ChargingSource,
    SafetyPointsSource,
    WeatherSource,
    WaterLevelSource,
    AirQualitySource,
    AircraftSource,
    AirportSource,
    SatelliteSource,
    KNMIQuakeSource,
    UFOSource,
]


def build(settings: Settings) -> dict[str, Source]:
    out = {}
    for cls in ALL:
        if settings.enabled(cls.name):
            out[cls.name] = cls(settings)
    return out
