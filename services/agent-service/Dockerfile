# Build: dependencies with uv; run: slim Python image (tags from docs/VERSIONS.md). The build context is the repository root
# (the contracts are copied from contracts/); Dockerfile.dockerignore lets in only what the image needs.
FROM python:3.12.15-slim AS build
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY services/agent-service/requirements.txt ./
RUN uv pip install --no-cache --target /opt/deps -r requirements.txt

FROM python:3.12.15-slim
WORKDIR /app
COPY --from=build /opt/deps /opt/deps
COPY services/agent-service/config /app/config
COPY services/agent-service/migrations /app/migrations
COPY services/agent-service/src /app/src
# The tool contracts (JSON Schema and the OpenAPI documents they point into) and the shared redaction rules (P4.3).
COPY contracts/openapi /app/contracts/openapi
COPY contracts/schemas /app/contracts/schemas
COPY contracts/redaction-rules.yaml /app/contracts/redaction-rules.yaml

# Configuration comes from the environment only (see config/*.yaml for the ${NAME} placeholders). The image holds no secret,
# no .env and no test data. The migrations are in the image: the service applies them at startup (agent_db migrator role).
ENV PYTHONPATH=/app:/opt/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QUANCRYPT_CONFIG_DIR=/app/config \
    QUANCRYPT_CONTRACTS_DIR=/app/contracts \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8083

USER 10001

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request as r; o = r.build_opener(r.ProxyHandler({})); sys.exit(0 if o.open('http://127.0.0.1:%s/health/liveness' % os.environ['UVICORN_PORT'], timeout=3).status == 200 else 1)"]

# Exec form: Python is PID 1 and receives SIGTERM; uvicorn finishes running requests and stops within 30 seconds.
CMD ["python", "-m", "uvicorn", "src.app.main:app", "--no-access-log", "--timeout-graceful-shutdown", "30"]
