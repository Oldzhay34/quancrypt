# Build context: the repository root (the canonical dictionary and the redaction rules are copied from contracts/).
#   docker build -f services/analyzer-service/Dockerfile -t analyzer-service:1.0.0 .
# Build: Gradle with JDK 25; run: JRE 25 (tags from docs/VERSIONS.md).
FROM gradle:9.8.0-jdk25 AS build
USER root
WORKDIR /workspace
COPY contracts/redaction-rules.yaml contracts/redaction-rules.yaml
COPY contracts/canonical_dictionary.csv contracts/canonical_dictionary.csv
WORKDIR /workspace/services/analyzer-service
COPY services/analyzer-service/settings.gradle.kts services/analyzer-service/build.gradle.kts ./
COPY services/analyzer-service/config config
COPY services/analyzer-service/src src
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:25.0.4.1_1-jre
WORKDIR /app
COPY --from=build /workspace/services/analyzer-service/build/libs/analyzer-service.jar /app/app.jar

# Configuration comes from the environment only (compose passes it from .env). No secret, key or .env file is part of the
# image: INTERNAL_SERVICE_TOKEN has no default and the service refuses to start without it. The analyzed project is mounted
# read-only at /workspace (docker-compose.yml); the service never writes.
ENV SERVER_PORT=8082 \
    SERVER_ADDRESS=0.0.0.0 \
    ANALYZER_ALLOWED_ROOTS=/workspace,/corpus \
    ANALYSIS_TIME_BUDGET_SECONDS=300

USER 10001
EXPOSE 8082

# The JRE image has neither curl nor wget, so bash's /dev/tcp asks for /health/liveness (D-120).
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
    CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/${SERVER_PORT} && printf 'GET /health/liveness HTTP/1.0\\r\\n\\r\\n' >&3 && head -n1 <&3 | grep -q ' 200 '"]

# Exec form: the JVM is PID 1 and receives SIGTERM, which starts the graceful shutdown (30 s).
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]
