# CI and releases

* **`ci.yaml`** runs on pull requests and non-main branches: frontend build,
  pytest, `helm lint`, and a Docker build with a smoke test (nothing is pushed).
* **`release.yaml`** runs on every push to `main` (docs-only pushes excepted):
  it runs CI, picks the next version, builds a `linux/amd64` + `linux/arm64`
  image with SBOM and provenance, pushes the Helm chart to
  `oci://ghcr.io/jwklijnsma/charts`, and creates the tag and GitHub Release with
  generated notes and the chart `.tgz` attached.

Image tags: `x.y.z`, `x.y`, `latest`, `sha-<commit>`.

The version comes from commit messages since the last `v*` tag
([Conventional Commits](https://www.conventionalcommits.org/)):

| Commit message | Bump |
|---|---|
| `feat: ...` or `feat(scope): ...` | minor |
| `type!: ...` or `BREAKING CHANGE` in the body | major |
| anything else | patch |

To force a bump, run the release workflow by hand (Actions → release → Run
workflow) and pick patch, minor or major.

New GHCR packages start private. Make `neighbourhood-radar` and
`charts/neighbourhood-radar` public in the package settings, or give the
cluster a pull secret.

## GitHub Pages

**`pages.yaml`** publishes the map to https://jwklijnsma.github.io/neighbourhood-radar/.
Pages only serves static files, so there is no backend there: the workflow runs
every source once with `scripts/export_static.py`, writes the answers to
`api/config.json` and `api/layers/<name>.json`, and builds the frontend with
`VITE_STATIC_API=1` so it reads those files and filters by distance in the
browser. The sidebar shows when the snapshot was taken.

One-time setup: **Settings → Pages → Source: GitHub Actions**.

The repository variable `PAGES_MODE` picks what the site shows:

| `PAGES_MODE` | Site shows | Updates |
|---|---|---|
| `demo` (default) | built-in sample data, no real 112 messages | on every push to `main` |
| `live` | a snapshot of the real feeds | on every push, and every 15 minutes (GitHub's schedule can lag) |

In `live` mode the secrets `OL_NS_API_KEY` and `OL_WINDY_API_KEY` turn on the
trains and webcams layers; without them those layers show "Niet geconfigureerd".
The air-quality layer's first crawl takes about 6 minutes, longer than the
snapshot waits (`OL_EXPORT_TIMEOUT`, 90 s), so it stays empty on Pages in live mode.
Run the workflow by hand (Actions → pages → Run workflow) to rebuild now or to
try the other mode once.
