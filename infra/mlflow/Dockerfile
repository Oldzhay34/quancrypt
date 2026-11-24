# MLflow tracking server (P7.1, D-322e). The official image has no PostgreSQL driver, so this adds psycopg2-binary on top of it
# (the same way as the Superset image, D-40). Nothing else changes: the server, its UI and its migrations are the image's own.
FROM ghcr.io/mlflow/mlflow:v3.16.1

RUN pip install --no-cache-dir psycopg2-binary==2.9.9 \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mlflow \
    && mkdir -p /mlartifacts \
    && chown 10001:10001 /mlartifacts

# Telemetry off (read from mlflow/telemetry/utils.py of this image: MLFLOW_DISABLE_TELEMETRY or DO_NOT_TRACK).
ENV MLFLOW_DISABLE_TELEMETRY=true \
    DO_NOT_TRACK=true \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 5000
