# Build: dependencies with uv; run: slim Python image (tags from docs/VERSIONS.md).
FROM python:3.12.15-slim AS build
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY requirements.txt ./
RUN uv pip install --no-cache --target /opt/deps -r requirements.txt

FROM python:3.12.15-slim
WORKDIR /app
COPY --from=build /opt/deps /opt/deps
COPY config /app/config
COPY src /app/src

# Configuration comes from the environment only (see config/*.yaml for the ${NAME} placeholders). The image holds no secret,
# no .env and no test data.
ENV PYTHONPATH=/app:/opt/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QUANCRYPT_CONFIG_DIR=/app/config \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8083

USER 10001

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request as r; o = r.build_opener(r.ProxyHandler({})); sys.exit(0 if o.open('http://127.0.0.1:%s/health/liveness' % os.environ['UVICORN_PORT'], timeout=3).status == 200 else 1)"]

# Exec form: Python is PID 1 and receives SIGTERM; uvicorn finishes running requests and stops within 30 seconds.
CMD ["python", "-m", "uvicorn", "src.app.main:app", "--no-access-log", "--timeout-graceful-shutdown", "30"]
