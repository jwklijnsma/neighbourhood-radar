# Run it

```bash
cp .env.example .env          # optional: add NS / Windy / FR24 keys
docker compose up -d --build  # http://localhost:8080
```

Without Docker:

```bash
pip install -r requirements.txt
(cd frontend && npm ci && npm run build)   # builds into app/static
uvicorn app.main:app --port 8080
```

Frontend development with hot reload (proxies `/api` to the backend on :8080):

```bash
uvicorn app.main:app --port 8080 --reload &
cd frontend && npm run dev                 # http://localhost:5173/static/
```

## Kubernetes / OpenShift

From the published chart (OCI on GHCR, versions match the releases):

```bash
helm upgrade --install neighbourhood-radar \
  oci://ghcr.io/jwklijnsma/charts/neighbourhood-radar --version <x.y.z> \
  --set route.enabled=true \
  --set secrets.OL_NS_API_KEY=xxxxx
```

Or from a checkout: `helm upgrade --install neighbourhood-radar deploy/helm/neighbourhood-radar ...`
(that uses the chart's default image tag).

The image runs as an arbitrary UID with group 0 and a read-only root filesystem,
so it fits `restricted-v2` without an SCC exception. Use `secrets.existingSecret`
for Sealed Secrets / External Secrets in a GitOps setup. Keep `replicaCount: 1`:
the cache is in-memory, and each replica would spend its own API credits
(OpenSky, Flightradar24).
