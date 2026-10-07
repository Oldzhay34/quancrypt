# Build: Gradle with JDK 25; run: JRE 25 (tags from docs/VERSIONS.md).
FROM gradle:9.8.0-jdk25 AS build
USER root
WORKDIR /workspace
COPY settings.gradle.kts build.gradle.kts ./
COPY config config
COPY src src
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:25.0.4.1_1-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/qbank-gateway.jar /app/app.jar

# Configuration comes from the environment only. Certificates, keys and secrets are never part of the image:
# mount only the files this service needs, read-only, under /certs when the container runs.
ENV QBANK_CERTS_DIR=/certs \
    SERVER_PORT=9443 \
    MANAGEMENT_SERVER_PORT=9543 \
    ACCOUNT_SERVICE_URL=https://qbank-account-service:9444 \
    PAYMENT_SERVICE_URL=https://qbank-payment-service:9445

USER 10001
EXPOSE 9443

# Health lives on the plain-HTTP management port, bound to loopback inside the container and never published.
# The JRE image has neither curl nor wget, so bash's /dev/tcp asks for /health/liveness (D-120).
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/${MANAGEMENT_SERVER_PORT} && printf 'GET /health/liveness HTTP/1.0\\r\\n\\r\\n' >&3 && head -n1 <&3 | grep -q ' 200 '"]

# Exec form: the JVM is PID 1 and receives SIGTERM, which triggers the graceful shutdown (30 s).
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
