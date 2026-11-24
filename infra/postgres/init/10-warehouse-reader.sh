#!/usr/bin/env bash
# `warehouse_reader`: marts şemasını okuyan salt okunur rol (Superset ve ML için, D-24).
# `marts` şeması bu betik çalıştığında yoktur (dbt yaratır): rol burada yalnızca warehouse_db'ye CONNECT alır. `marts`'ta
# USAGE ve tablo başına SELECT yetkisini dbt build verir (dbt_project.yml `grants` ve grant_schema_usage makrosu, P6.6, D-319e);
# core, snapshots, staging, prep ve raw'da hiçbir yetkisi yoktur. TODO(P0.3-1) böylece kapandı.
set -euo pipefail

: "${WAREHOUSE_READER_PASSWORD:?WAREHOUSE_READER_PASSWORD tanımlı olmalı}"

psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname postgres <<'SQL'
-- Hata durumunda ifade (parolayla) loga yazılmasın.
\set VERBOSITY terse
SET log_min_error_statement = panic;
SET log_statement = 'none';
\getenv reader_pw WAREHOUSE_READER_PASSWORD

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
              'warehouse_reader', :'reader_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'warehouse_reader') \gexec

GRANT CONNECT ON DATABASE warehouse_db TO warehouse_reader;
SQL
