# How it works

```
browser (React) ────/api/layers/{name}?lat&lon&radius_km──▶ FastAPI
                                                              │  per-source TTL cache
                                                              ▼  (one fetch serves all viewers)
                       P2000 · NDW · OVapi · NS · adsb.lol/FR24 · CelesTrak · KNMI · …
```

* Each source fetches **once for the whole configured region** (`OL_REGION_RADIUS_KM`
  around the centre) and caches it; requests only filter by distance. Ten people
  with the page open cost the upstreams the same as one.
* A failing upstream keeps serving the last good data and reports the error in
  `status.last_error`; the UI marks the layer "Bron niet bereikbaar".
* Rate-limited providers get conservative refresh intervals: OpenSky's anonymous
  budget is 400 credits/day (one region box costs 1), so it refreshes every 240 s;
  Flightradar24 every 60 s.
* The UI is React + react-leaflet (Vite), in `frontend/`. It builds into
  `app/static`, which FastAPI serves, so production is still one container.
* Feed text is only rendered as React text (escaped); strict CSP, no
  third-party scripts. The base map is PDOK's BRT achtergrondkaart (Kadaster),
  free and keyless; set `OL_TILE_URL` and `OL_TILE_ATTRIBUTION` for another provider.
