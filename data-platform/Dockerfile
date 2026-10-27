# Build: dependencies with uv; run: slim Python image (tags from docs/VERSIONS.md). The build context is the repository root
# (the event schemas are copied from contracts/); Dockerfile.dockerignore lets in only what the image needs.
FROM python:3.12.15-slim AS build
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY data-platform/requirements.txt ./
RUN uv pip install --no-cache --target /opt/deps -r requirements.txt

FROM python:3.12.15-slim
WORKDIR /app
COPY --from=build /opt/deps /opt/deps
COPY data-platform/migrations /app/migrations
COPY data-platform/src /app/src
COPY contracts/schemas/events /app/contracts/schemas/events

# Configuration comes from the environment only. The image holds no secret, no .env and no test data. The migrations are in
# the image: the service applies them at startup (warehouse_db migrator role).
ENV PYTHONPATH=/app/src:/opt/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EVENT_SCHEMAS_DIR=/app/contracts/schemas/events \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8084

USER 10001

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request as r; o = r.build_opener(r.ProxyHandler({})); sys.exit(0 if o.open('http://127.0.0.1:%s/health/liveness' % os.environ['UVICORN_PORT'], timeout=3).status == 200 else 1)"]

# Exec form: Python is PID 1 and receives SIGTERM; uvicorn finishes running requests and stops within 30 seconds. At most 8 requests
# run at once (each 8 MiB body is about 260 MB once parsed; a ninth gets 503 and the sender retries); the compose memory limit backs it.
CMD ["python", "-m", "uvicorn", "quancrypt_data.api.ingest:app", "--no-access-log", "--timeout-graceful-shutdown", "30", "--limit-concurrency", "8"]
