#!/usr/bin/env bash
# Veritabanları ve roller (D-09, D-54). Postgres imajı bu betiği yalnızca BOŞ veri dizininde,
# ilk açılışta çalıştırır. Betik yine de idempotenttir: tekrar çalıştırılırsa hata vermez.
# Parolalar komut satırına girmez: psql `\getenv` ile ortamdan okur. Parola SQL metnine gömüldüğü
# için hata durumunda loga düşmesin diye oturumda ifade loglaması kapatılır.
set -euo pipefail

# Fail-closed (D-57): boş veya `.env.example`'daki yer tutucu (CHANGE_ME) parolayla açılmaz.
# Not: Bu denetim initdb'den sonra çalışır; reddedilirse veri dizini yarım kalır ve imaj sonraki
# açılışta init betiklerini yeniden çalıştırmaz. Düzeltme: .env'i doldurup `make db-reset`.
for name in POSTGRES_PASSWORD \
            CORE_DB_MIGRATOR_PASSWORD CORE_DB_APP_PASSWORD \
            AGENT_DB_MIGRATOR_PASSWORD AGENT_DB_APP_PASSWORD \
            WAREHOUSE_DB_MIGRATOR_PASSWORD WAREHOUSE_DB_APP_PASSWORD WAREHOUSE_READER_PASSWORD \
            MLFLOW_DB_MIGRATOR_PASSWORD MLFLOW_DB_APP_PASSWORD; do
  value="${!name:-}"
  if [ -z "$value" ] || [ "$value" = "CHANGE_ME" ]; then
    # Yarım kalacak kümede süper kullanıcı parolası yer tutucu olarak kalmasın: parola geçersiz kılınır
    # (TCP ile parolayla giriş imkansız olur; unix soketi yalnızca konteyner içinden erişilebilir).
    psql --no-psqlrc --username "$POSTGRES_USER" --dbname postgres \
      -c 'ALTER ROLE CURRENT_USER PASSWORD NULL' >/dev/null 2>&1 || true
    echo "HATA: $name boş veya CHANGE_ME. .env değerlerini doldurup 'make db-reset' ile volume'ü sıfırlayın." >&2
    exit 1
  fi
done

psql_admin() {
  psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname postgres "$@"
}

# `postgres` ve `template1` veritabanlarında PUBLIC'in CONNECT yetkisi varsayılan olarak vardır;
# uygulama rollerinin başka hiçbir veritabanına bağlanamaması için kaldırılır.
psql_admin <<'SQL'
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;
SQL

for db in core_db agent_db warehouse_db mlflow_db; do
  prefix="$(printf '%s' "$db" | tr '[:lower:]' '[:upper:]')"
  migrator_env="${prefix}_MIGRATOR_PASSWORD"
  app_env="${prefix}_APP_PASSWORD"
  : "${!migrator_env:?${migrator_env} tanımlı olmalı}"
  : "${!app_env:?${app_env} tanımlı olmalı}"

  psql_admin -v db="$db" -v migrator_env="$migrator_env" -v app_env="$app_env" <<'SQL'
-- Parola SQL metnine gömüldüğü için, bir ifade hata verirse sunucu ve psql ifadeyi (parolayla)
-- loga yazmasın.
\set VERBOSITY terse
SET log_min_error_statement = panic;
SET log_statement = 'none';
\getenv migrator_pw :migrator_env
\getenv app_pw :app_env

-- Roller: giriş yapabilir, başka hiçbir ayrıcalığı yoktur.
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
              :'db' || '_migrator', :'migrator_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db' || '_migrator') \gexec
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
              :'db' || '_app', :'app_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db' || '_app') \gexec

-- Veritabanının sahibi migrator'dır: DDL yetkisi buradan gelir.
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'db' || '_migrator')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec

-- Yalnızca kendi rolleri bağlanabilir. PUBLIC'in varsayılan TEMPORARY yetkisi de kaldırılır (D-59);
-- veritabanının sahibi migrator'ın yetkisi etkilenmez.
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I, %I', :'db', :'db' || '_migrator', :'db' || '_app') \gexec
SQL

  # `public` şemasında migrator'ın yaratacağı tablo ve sequence'ler için app rolüne DML (D-54).
  # Başka şemalar için aynı yetkiyi ilgili fazın migration'ı yazar.
  psql_admin -v db="$db" <<'SQL'
\connect :db
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
              :'db' || '_migrator', :'db' || '_app') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
              :'db' || '_migrator', :'db' || '_app') \gexec
SQL
done
