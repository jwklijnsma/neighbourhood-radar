# API

* `GET /api/config` – centre, limits, layer status
* `GET /api/layers/{name}?lat=&lon=&radius_km=` – GeoJSON FeatureCollection, sorted by distance
* `GET /api/summary?lat=&lon=&radius_km=1.5` – count + nearest item per layer (the "3 alerts within 1.5 km" view)
* `GET /healthz`, `/readyz`, `/api/docs`
