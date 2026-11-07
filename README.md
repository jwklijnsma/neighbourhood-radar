# omgeving-live

One map with live open data around a point you choose: 112/P2000 alerts, road
incidents, buses and trains on the move, NS disruptions, aircraft overhead,
satellites above your horizon and recent earthquakes. Click the map, set a
radius, and the side panel lists what's happening nearby, nearest first.

Inspired by the "KW Live" demo from Kitchener (CTV News, Oct 2026), rebuilt
from scratch for the Netherlands with Dutch open data. Defaults to Heerenveen /
the three northern provinces; everything is configurable.

## Layers

| Layer | Source | Key needed | Refresh |
|---|---|---|---|
| `p2000` – 112 alerts | P2000 RSS from p2000.brandweer-berkel-enschot.nl (same feed as the Home Assistant P2000 component) | no | 30 s |
| `traffic` – incidents | NDW open data `incidents.xml.gz` (DATEX II) | no | 60 s |
| `transit` – live vehicles | OVapi GTFS-realtime `vehiclePositions.pb` (CC0) | no | 20 s |
| `trains` – disruptions | NS API `disruptions/v3` | yes, free (apiportal.ns.nl, product *Ns-App*) | 2 min |
| `aircraft` | OpenSky Network `states/all`, bounding box | optional | 4 min anonymous / 30 s with OAuth client |
| `satellites` | CelesTrak TLEs, SGP4 propagated locally | no | positions every 15 s |
| `quakes` | KNMI FDSN event service (CC BY 4.0) | no | 5 min |

Layers without their key show up greyed out ("Niet geconfigureerd") rather than failing.

Traffic cameras from the original demo are not included: Rijkswaterstaat doesn't
publish an open camera feed.

## How it works

```
browser (Leaflet) ──/api/layers/{name}?lat&lon&radius_km──▶ FastAPI
                                                              │  per-source TTL cache
                                                              ▼  (one fetch serves all viewers)
                       P2000 · NDW · OVapi · NS · OpenSky · CelesTrak · KNMI
```

* Each source fetches **once for the whole configured region** (`OL_REGION_RADIUS_KM`
  around the centre) and caches it; requests only filter by distance. Ten people
  with the page open cost the upstreams the same as one.
* A failing upstream keeps serving the last good data and reports the error in
  `status.last_error`; the UI marks the layer "Bron niet bereikbaar".
* OpenSky's anonymous budget is 400 credits/day; one region box costs 1 credit,
  so the 240 s TTL stays under it even with the page open 24/7.
* All feed text is rendered with `textContent`; strict CSP, no third-party
  scripts (Leaflet is vendored in `app/static/vendor`). Map tiles come from CARTO.

## API

* `GET /api/config` – centre, limits, layer status
* `GET /api/layers/{name}?lat=&lon=&radius_km=` – GeoJSON FeatureCollection, sorted by distance
* `GET /api/summary?lat=&lon=&radius_km=1.5` – count + nearest item per layer (the "3 alerts within 1.5 km" view)
* `GET /healthz`, `/readyz`, `/api/docs`

## Run it

```bash
cp .env.example .env          # optional: add NS / OpenSky keys
docker compose up -d --build  # http://localhost:8080
```

Without Docker:

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8080
```

### Kubernetes / OpenShift

```bash
helm upgrade --install omgeving-live deploy/helm/omgeving-live \
  --set route.enabled=true \
  --set secrets.OL_NS_API_KEY=xxxxx
```

The image runs as an arbitrary UID with group 0 and a read-only root filesystem,
so it fits `restricted-v2` without an SCC exception. Use `secrets.existingSecret`
for Sealed Secrets / External Secrets in a GitOps setup. Keep `replicaCount: 1`:
the cache is in-memory, and each replica would spend its own OpenSky credits.

## Configuration

All settings are environment variables with prefix `OL_`; see `.env.example`.
To move the map elsewhere, change `OL_CENTER_LAT/LON` and `OL_P2000_REGIOS`
(1 Groningen, 2 Fryslân, 3 Drenthe, … 25 Flevoland).

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Every parser is tested against recorded-format fixtures and the API is tested
with all upstreams mocked, so tests run offline.

## Caveats

* The P2000 feed is a volunteer-run service, not an official API. If it goes
  away, point `OL_P2000_URL` at another RSS feed with the same item fields
  (`message`, `regcode`, `dienst`, `code`, `lat`, `lon`), or run your own
  RTL-SDR + multimon-ng receiver.
* OpenSky data is for non-commercial use under their terms.
* P2000 messages are public broadcasts, but they describe real emergencies at
  real addresses. Think before exposing this publicly.
