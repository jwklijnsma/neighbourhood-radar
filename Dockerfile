# --- 1. build the React frontend ------------------------------------------
# Frontend output is platform independent: build it once on the native builder.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# vite.config.js writes to ../app/static
RUN npm run build

# --- 2. runtime: Python backend serving API + built frontend ----------------
# Runs as an arbitrary non-root UID with group 0, so it works on OpenShift's restricted SCC as-is.
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY --from=frontend /src/app/static ./app/static
RUN chgrp -R 0 /opt/app && chmod -R g=u /opt/app

USER 1001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--no-server-header"]
