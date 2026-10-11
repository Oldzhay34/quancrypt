# Build context: the repository root (the redaction rules are copied from contracts/).
#   docker build -f services/core-service/Dockerfile -t core-service:1.0.0 .
# Build: Gradle with JDK 25; run: JRE 25 (tags from docs/VERSIONS.md).
FROM gradle:9.8.0-jdk25 AS build
USER root
WORKDIR /workspace
COPY contracts/redaction-rules.yaml contracts/redaction-rules.yaml
WORKDIR /workspace/services/core-service
COPY services/core-service/settings.gradle.kts services/core-service/build.gradle.kts ./
COPY services/core-service/config config
COPY services/core-service/src src
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:25.0.4.1_1-jre
WORKDIR /app
COPY --from=build /workspace/services/core-service/build/libs/core-service.jar /app/app.jar

# Configuration comes from the environment only (compose passes it from .env). No secret, key or .env file is part of the
# image: CORE_DB_*_PASSWORD, QUANCRYPT_ANON_SALT, QUANCRYPT_SESSION_TOKEN and INTERNAL_SERVICE_TOKEN have no default and the
# service refuses to start without them. The migrations run at start-up, as the schema owner.
ENV SERVER_PORT=8081 \
    CORE_DB_URL=jdbc:postgresql://postgres:5432/core_db \
    OUTBOX_RELAY_ENABLED=false

USER 10001
EXPOSE 8081

# The JRE image has neither curl nor wget, so bash's /dev/tcp asks for /health/liveness (D-120).
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
    CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/${SERVER_PORT} && printf 'GET /health/liveness HTTP/1.0\\r\\n\\r\\n' >&3 && head -n1 <&3 | grep -q ' 200 '"]

# Exec form: the JVM is PID 1 and receives SIGTERM, which starts the graceful shutdown (30 s).
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]
