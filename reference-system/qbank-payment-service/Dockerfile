# Build context: reference-system/ (the MQTT message schema is copied from contracts/).
#   docker build -f qbank-payment-service/Dockerfile -t qbank-payment-service:1.0.0 reference-system
# Build: Gradle with JDK 25; run: JRE 25 (tags from docs/VERSIONS.md).
FROM gradle:9.8.0-jdk25 AS build
USER root
WORKDIR /workspace
COPY contracts/terminal-transaction.schema.json contracts/terminal-transaction.schema.json
WORKDIR /workspace/qbank-payment-service
COPY qbank-payment-service/settings.gradle.kts qbank-payment-service/build.gradle.kts ./
COPY qbank-payment-service/config config
COPY qbank-payment-service/src src
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:25.0.4.1_1-jre
WORKDIR /app
COPY --from=build /workspace/qbank-payment-service/build/libs/qbank-payment-service.jar /app/app.jar

# Configuration comes from the environment only. Certificates, keys and secrets are never part of the image:
# mount only the files this service needs, read-only, under /certs when the container runs.
ENV QBANK_CERTS_DIR=/certs \
    SERVER_PORT=9445 \
    MANAGEMENT_SERVER_PORT=9545 \
    ACCOUNT_SERVICE_URL=https://qbank-account-service:9444 \
    MQTT_BROKER_URL=ssl://mosquitto:8883

USER 10001
EXPOSE 9445

# Health lives on the plain-HTTP management port, bound to loopback inside the container and never published.
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${MANAGEMENT_SERVER_PORT}/health/liveness" || exit 1

# Exec form: the JVM is PID 1 and receives SIGTERM, which triggers the graceful shutdown (30 s).
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
