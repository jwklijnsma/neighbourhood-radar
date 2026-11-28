# Tests

```bash
pip install -r requirements-dev.txt
(cd frontend && npm ci && npm run build)   # optional; the UI test is skipped without it
pytest -q
```

Every parser is tested against recorded-format fixtures and the API is tested
with all upstreams mocked, so tests run offline.
