# Layers

| Layer | Source | Key needed | Refresh |
|---|---|---|---|
| `p2000` – 112 alerts | P2000 RSS from p2000.brandweer-berkel-enschot.nl (same feed as the Home Assistant P2000 component) | no | 30 s |
| `traffic` – accidents, queues, obstructions | NDW open data `actueel_beeld.xml.gz` (DATEX II) | no | 60 s |
| `bridges` – bridges open right now, and openings in the next 6 h | NDW `tijdelijke_verkeersmaatregelen_afsluitingen` (live) + `planningsfeed_brugopeningen` | no | 30 s |
| `roadworks` – roadworks and events, now or in the next 24 h | NDW `planningsfeed_wegwerkzaamheden_en_evenementen` | no | 15 min |
| `drips` – what the dynamic route signs above the road show now (text, or the sign image) | NDW `dynamische_route_informatie_paneel` (DATEX II VMS) | no | 60 s |
| `busalerts` – bus/tram/metro service alerts, on the affected stops | OVapi GTFS-realtime `alerts.pb` + `stops.txt` from `gtfs-nl.zip` (CC0) | no | 60 s |
| `transit` – live vehicles | OVapi GTFS-realtime `vehiclePositions.pb` (CC0) | no | 20 s |
| `trains` – disruptions | NS API `disruptions/v3` | yes, free (apiportal.ns.nl, product *Ns-App*) | 2 min |
| `webcams` – live webcam images | Windy Webcams API v3 | yes, free (api.windy.com/keys) | 5 min |
| `charging` – public EV charging points, coloured by live availability | NDW national OCPI export (streamed, ~18 MB) | no | 15 min |
| `safety` – AEDs, hospitals, fire, police and ambulance stations | OpenStreetMap via Overpass API (ODbL) | no | daily |
| `weather` – station measurements | Buienradar JSON feed | no | 10 min |
| `water` – water levels in cm relative to NAP | Rijkswaterstaat waterwebservices (DDAPI 2.0) | no | 10 min |
| `air` – air quality index (LKI 1–11) | Luchtmeetnet open API | no | hourly |
| `aircraft` – aircraft with type, registration, altitude, speed and a trail of where they flew; emergencies (squawk 7500/7600/7700) pulse red, helicopters get their own icon | **adsb.lol** (open data, ODbL) by default; or Flightradar24, OpenSky, airplanes.live, or your own ADS-B receiver (see below) | no (FR24: paid token) | 15 s |
| `airports` – airports, airfields and heliports | OurAirports (public domain) | no | daily |
| `satellites` | CelesTrak TLEs, SGP4 propagated locally | no | positions every 15 s |
| `quakes` | KNMI FDSN event service (CC BY 4.0) | no | 5 min |
| `ufo` – reported UFO sightings (historical, 1906–2014; shape, duration and the witness's own words) | NUFORC reports, geocoded CSV mirrored at [planetsig/ufo-reports](https://github.com/planetsig/ufo-reports); `OL_UFO_URL` takes your own CSV (headerless NUFORC layout, or any CSV with `latitude`/`longitude` columns) | no | daily |

## Aircraft providers

Set `OL_AIRCRAFT_SOURCE` (default `auto`):

| Value | Source | Notes |
|---|---|---|
| `adsblol` | [adsb.lol](https://adsb.lol) | Open data (ODbL), no key. Default. |
| `fr24` | [Flightradar24 API](https://fr24api.flightradar24.com) | Paid subscription. Set `OL_FR24_API_TOKEN`. Adds routes (AMS → OSL). `OL_FR24_ENDPOINT=light` uses fewer credits but drops type, registration and route. Polls every 60 s; check your credit usage in the FR24 portal and raise `OL_AIRCRAFT_TTL` if needed. |
| `readsb` | Your own receiver | Set `OL_READSB_URL` to its `aircraft.json` (readsb, dump1090-fa, tar1090, e.g. `http://pi/tar1090/data/aircraft.json`). Polls every 5 s. |
| `opensky` | OpenSky Network | Optional OAuth client for more requests. |
| `airplaneslive` | airplanes.live | No key, non-commercial use only. |

`auto` picks `fr24` if a token is set, else `readsb` if a URL is set, else `adsblol`.
Trails show the last 10 minutes (`OL_AIRCRAFT_TRAIL_MINUTES`, 0 turns them off).
Airliners at cruising height don't fill the "Dichtbij" list: only emergencies,
helicopters and aircraft below 1000 m do.

Flightradar24's website data isn't open and scraping it is against their terms,
so this only uses their official API.

Layers without their key show up greyed out ("Niet geconfigureerd") rather than failing.

Some layers need a slow first load and fill in a little after startup instead of
holding up the page:

* **busalerts** reads only `stops.txt` out of OVapi's national GTFS archive,
  using HTTP range requests (a few MB instead of the whole archive), refreshed weekly.
  If OVapi ever stops serving ranges, point `OL_GTFS_STOPS_URL` at a plain `stops.txt`.
* **air** has to look up every station's location once; Luchtmeetnet allows
  100 requests per 5 minutes, so that crawl takes about 6 minutes and is cached for a week.

Traffic cameras as in the original demo aren't available: Rijkswaterstaat doesn't
publish an open camera feed, so the `webcams` layer uses public webcams from Windy.

If the DRIP layer reports that signs have no locations, NDW is publishing the
sign locations in a separate table file: set `OL_NDW_DRIP_TABLE_URL` to it.

AED locations come from OpenStreetMap volunteers and are not the official
HartslagNu register. Don't rely on the map in an emergency: call 112.

Licences and terms: Buienradar's free feed requires attribution and is for
non-commercial use; OpenSky data is for non-commercial use; KNMI data is CC BY 4.0;
OVapi is CC0; OpenStreetMap data is ODbL. Attribution for every layer is shown at the bottom of the side panel.
