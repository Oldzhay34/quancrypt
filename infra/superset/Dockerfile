# Apache Superset for the warehouse dashboards (P7.5, D-24, D-40, D-49, D-344i). The official image has no PostgreSQL
# driver, so this adds psycopg2-binary 2.9.9 (the pin of Superset 6.1.0's own `postgres` extra) to the image's venv.
# The server, its UI and its migrations are the image's own. The metadata database is the image's default SQLite file in
# SUPERSET_HOME, which compose mounts as the `superset-home` volume.
FROM apache/superset:6.1.0

USER root
RUN uv pip install --no-cache --python /app/.venv/bin/python psycopg2-binary==2.9.9 \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin quancrypt

# Local-only configuration (read by the image's config.py from PYTHONPATH=/app/pythonpath) and the one-off init step.
COPY superset_config.py /app/pythonpath/superset_config.py
COPY quancrypt_init.py quancrypt_import.py /app/pythonpath/
RUN chmod 0444 /app/pythonpath/superset_config.py /app/pythonpath/quancrypt_init.py /app/pythonpath/quancrypt_import.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    DO_NOT_TRACK=1

USER 10001
EXPOSE 8088
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=40s \
    CMD ["python", "-c", "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8088/health', timeout=4)"]
