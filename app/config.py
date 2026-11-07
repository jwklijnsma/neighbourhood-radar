"""Runtime configuration, read from environment variables (prefix OL_)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(f"OL_{name}", default).strip()


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


def _list(name: str, default: str) -> list[str]:
    return [p.strip() for p in _env(name, default).split(",") if p.strip()]


@dataclass(frozen=True)
class Settings:
    # Map centre and the area the backend fetches data for.
    center_lat: float = field(default_factory=lambda: _float("CENTER_LAT", 52.9594))
    center_lon: float = field(default_factory=lambda: _float("CENTER_LON", 5.9189))
    region_radius_km: float = field(default_factory=lambda: _float("REGION_RADIUS_KM", 60.0))
    max_query_radius_km: float = field(default_factory=lambda: _float("MAX_QUERY_RADIUS_KM", 100.0))

    # Sources that should not run at all (comma separated names).
    disabled_sources: list[str] = field(default_factory=lambda: _list("DISABLED_SOURCES", ""))

    # P2000 (emergency services paging network). RSS with lat/lon per item.
    p2000_url: str = field(
        default_factory=lambda: _env("P2000_URL", "http://p2000.brandweer-berkel-enschot.nl/homeassistant/rss.asp")
    )
    # Veiligheidsregio codes: 1 Groningen, 2 Fryslân, 3 Drenthe ... empty = all.
    p2000_regios: list[str] = field(default_factory=lambda: _list("P2000_REGIOS", "1,2,3"))

    # NDW road incidents (DATEX II, open data, no key).
    ndw_incidents_url: str = field(
        default_factory=lambda: _env("NDW_INCIDENTS_URL", "https://opendata.ndw.nu/incidents.xml.gz")
    )

    # OVapi GTFS-realtime vehicle positions (buses, trams, trains; no key).
    gtfs_vehicles_url: str = field(
        default_factory=lambda: _env("GTFS_VEHICLES_URL", "https://gtfs.ovapi.nl/nl/vehiclePositions.pb")
    )

    # NS disruptions (needs a free key from apiportal.ns.nl, product "Ns-App").
    ns_api_key: str = field(default_factory=lambda: _env("NS_API_KEY"))

    # OpenSky Network. Anonymous works (400 credits/day); OAuth2 client raises that to 4000.
    opensky_client_id: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_ID"))
    opensky_client_secret: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_SECRET"))

    # CelesTrak groups to track (see celestrak.org/NORAD/elements).
    celestrak_groups: list[str] = field(default_factory=lambda: _list("CELESTRAK_GROUPS", "stations,visual"))
    sat_min_elevation_deg: float = field(default_factory=lambda: _float("SAT_MIN_ELEVATION_DEG", 10.0))

    # KNMI earthquakes.
    knmi_days: float = field(default_factory=lambda: _float("KNMI_DAYS", 30.0))

    user_agent: str = field(default_factory=lambda: _env("USER_AGENT", "omgeving-live/1.0"))

    def enabled(self, name: str) -> bool:
        return name not in self.disabled_sources


settings = Settings()
