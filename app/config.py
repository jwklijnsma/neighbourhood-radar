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

    # NDW current traffic situations: accidents, queues, obstructions (DATEX II, no key).
    ndw_incidents_url: str = field(
        default_factory=lambda: _env("NDW_INCIDENTS_URL", "https://opendata.ndw.nu/actueel_beeld.xml.gz")
    )

    # OVapi GTFS-realtime vehicle positions (buses, trams, trains; no key).
    gtfs_vehicles_url: str = field(
        default_factory=lambda: _env("GTFS_VEHICLES_URL", "https://gtfs.ovapi.nl/nl/vehiclePositions.pb")
    )
    # OVapi GTFS-realtime service alerts, and the static GTFS archive for stop locations
    # (only stops.txt is read from it, via HTTP range requests). May also point at a stops.txt.
    gtfs_alerts_url: str = field(
        default_factory=lambda: _env("GTFS_ALERTS_URL", "https://gtfs.ovapi.nl/nl/alerts.pb")
    )
    gtfs_stops_url: str = field(
        default_factory=lambda: _env("GTFS_STOPS_URL", "https://gtfs.ovapi.nl/nl/gtfs-nl.zip")
    )

    # NDW dynamic route information panels. The table URL is only needed if NDW
    # publishes the panel locations in a separate file.
    ndw_drip_url: str = field(
        default_factory=lambda: _env("NDW_DRIP_URL", "https://opendata.ndw.nu/dynamische_route_informatie_paneel.xml.gz")
    )
    ndw_drip_table_url: str = field(default_factory=lambda: _env("NDW_DRIP_TABLE_URL"))

    # Windy webcams (free key at api.windy.com/keys).
    windy_api_key: str = field(default_factory=lambda: _env("WINDY_API_KEY"))

    # NS disruptions (needs a free key from apiportal.ns.nl, product "Ns-App").
    ns_api_key: str = field(default_factory=lambda: _env("NS_API_KEY"))

    # Aircraft. OL_AIRCRAFT_SOURCE picks the provider:
    #   auto (default)  fr24 if a token is set, else readsb if a URL is set, else adsblol
    #   adsblol         adsb.lol, open data (ODbL), no key
    #   airplaneslive   airplanes.live, no key, non-commercial use only
    #   opensky         OpenSky Network (optional OAuth2 client below)
    #   fr24            Flightradar24 official API (paid subscription, token below)
    #   readsb          your own receiver: readsb / dump1090-fa / tar1090 aircraft.json
    aircraft_source: str = field(default_factory=lambda: _env("AIRCRAFT_SOURCE", "auto").lower())
    fr24_api_token: str = field(default_factory=lambda: _env("FR24_API_TOKEN"))
    # "full" adds type, registration and route (costs more credits than "light").
    fr24_endpoint: str = field(default_factory=lambda: _env("FR24_ENDPOINT", "full").lower())
    readsb_url: str = field(default_factory=lambda: _env("READSB_URL"))
    # Seconds between aircraft refreshes; 0 = the provider's default.
    aircraft_ttl: float = field(default_factory=lambda: _float("AIRCRAFT_TTL", 0))
    # Minutes of track history drawn behind each aircraft (0 = no trails).
    aircraft_trail_minutes: float = field(default_factory=lambda: _float("AIRCRAFT_TRAIL_MINUTES", 10))

    # OpenSky Network. Anonymous works (400 credits/day); OAuth2 client raises that to 4000.
    opensky_client_id: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_ID"))
    opensky_client_secret: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_SECRET"))

    # CelesTrak groups to track (see celestrak.org/NORAD/elements).
    celestrak_groups: list[str] = field(default_factory=lambda: _list("CELESTRAK_GROUPS", "stations,visual"))
    sat_min_elevation_deg: float = field(default_factory=lambda: _float("SAT_MIN_ELEVATION_DEG", 10.0))

    # KNMI earthquakes.
    knmi_days: float = field(default_factory=lambda: _float("KNMI_DAYS", 30.0))

    # UFO sightings: CSV of geocoded reports (see app/sources/ufo.py for the layouts).
    # Empty = the NUFORC export mirrored on GitHub (historical, 1906-2014).
    # Turn the layer off with OL_DISABLED_SOURCES=ufo.
    ufo_url: str = field(default_factory=lambda: _env("UFO_URL") or (
        "https://raw.githubusercontent.com/planetsig/ufo-reports/master/csv-data/"
        "ufo-scrubbed-geocoded-time-standardized.csv"
    ))

    # Base map tiles (XYZ template). Default: PDOK BRT achtergrondkaart, the Dutch
    # government's free, keyless base map. Outside NL, point this at another provider
    # and add its host to the page's Content-Security-Policy via the same setting.
    tile_url: str = field(default_factory=lambda: _env(
        "TILE_URL", "https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/grijs/EPSG:3857/{z}/{x}/{y}.png"))
    tile_attribution: str = field(default_factory=lambda: _env(
        "TILE_ATTRIBUTION", "Kaart © Kadaster (PDOK, CC BY 4.0)"))

    # Demo mode: answer every upstream request from built-in sample data.
    demo: bool = field(default_factory=lambda: _env("DEMO", "").lower() in ("1", "true", "yes"))

    user_agent: str = field(default_factory=lambda: _env("USER_AGENT", "neighbourhood-radar/1.0"))

    def enabled(self, name: str) -> bool:
        return name not in self.disabled_sources


settings = Settings()
