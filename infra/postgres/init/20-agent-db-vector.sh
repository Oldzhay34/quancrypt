#!/usr/bin/env bash
# agent_db: bilgi tabanı vektörleri pgvector ile tutulur (D-13).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname agent_db <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
SQL
