# Build: dependencies with uv; run: slim Python image (tags from docs/VERSIONS.md).
FROM python:3.12.15-slim AS build
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY requirements.txt ./
RUN uv pip install --no-cache --target /opt/deps -r requirements.txt

FROM python:3.12.15-slim
WORKDIR /app
COPY --from=build /opt/deps /opt/deps
COPY src /app/src

# Configuration comes from the environment only. Certificates, keys and secrets are never part of the image:
# mount only the files this service needs (ca.crt.pem and the terminal's .crt.pem and .key.pem), read-only, under /certs.
ENV PYTHONPATH=/app/src:/opt/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QBANK_CERTS_DIR=/certs \
    MQTT_BROKER_URL=ssl://mosquitto:8883 \
    FIELD_DEVICE_SIM_STATUS_FILE=/tmp/field-device-sim.status

USER 10001

# The simulator has no port; it is healthy while it keeps publishing (the status file is written after every
# acknowledged publication).
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-m", "field_device_sim", "healthcheck", "--max-age", "30"]

# Exec form: Python is PID 1 and receives SIGTERM, which ends the loop and closes the connection.
ENTRYPOINT ["python", "-m", "field_device_sim"]
CMD ["run", "--terminal-id", "terminal-001", "--interval", "5"]
