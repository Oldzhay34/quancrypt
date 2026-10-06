#!/usr/bin/env bash
# `warehouse_reader`: marts şemasını okuyan salt okunur rol (Superset ve ML için, D-24).
# TODO(P0.3-1): `marts` şeması henüz yok; SELECT yetkisi şema yaratıldığında (P6.5/P6.6) eklenecek.
# Şimdilik rol yalnızca warehouse_db'ye CONNECT yetkisine sahiptir.
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
