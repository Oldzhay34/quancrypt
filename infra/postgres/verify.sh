#!/usr/bin/env bash
# PostgreSQL rol izolasyonu ve pgvector doğrulaması (P0.3).
#
# Kullanım (repo kökünden veya herhangi bir dizinden):  infra/postgres/verify.sh
# Önkoşul: `make up` ile `postgres` servisi healthy olmalı; `.env` oluşturulmuş olmalı.
#
# Denetler:
#   1. Her rol yalnızca kendi veritabanına bağlanabilir; başka veritabanlarına bağlanma
#      ("permission denied") reddedilir. Hedefler: dört servis veritabanı, `postgres`, `template1`.
#   2. `_app` rolleri ve `warehouse_reader` tablo, şema ve geçici tablo yaratamaz (ek kontrol, D-60).
#   3. Yanlış parola reddedilir (parola doğrulaması gerçekten çalışıyor; ek kontrol).
#   4. `agent_db`'de `vector` uzantısı yüklü ve kullanılabilir.
#   5. Port yalnızca 127.0.0.1'e bağlı (ek kontrol; kabul ölçütü "portlar yalnızca 127.0.0.1").
#
# Parolalar `.env`'den satır satır okunur (dosya kabukta çalıştırılmaz) ve hiçbir yere yazılmaz.
# ENV_FILE ile başka bir env dosyası verilebilir (varsayılan: .env).
set -uo pipefail

cd "$(dirname "$0")/../.."
ENV_FILE="${ENV_FILE:-.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "HATA: $ENV_FILE bulunamadı. .env.example dosyasını .env olarak kopyalayıp doldurun." >&2
  exit 2
fi

envval() { grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r'; }
compose() { docker compose --env-file "$ENV_FILE" "$@"; }

# Ön kontrol: docker ve çalışan bir postgres olmadan onlarca ayrı hata basmak yerine tek mesajla çıkar.
if ! command -v docker >/dev/null 2>&1; then
  echo "HATA: 'docker' komutu bulunamadı. WSL'de Docker Desktop → Settings → Resources → WSL integration ayarını açın." >&2
  exit 2
fi
if ! compose exec -T postgres pg_isready -h 127.0.0.1 -U postgres -d postgres >/dev/null 2>&1; then
  echo "HATA: postgres servisi çalışmıyor veya hazır değil. Önce 'make up' çalıştırın ve 'healthy' olmasını bekleyin." >&2
  exit 2
fi

pass=0
fail=0
ok()   { echo "OK    $*"; pass=$((pass + 1)); }
bad()  { echo "HATA  $*"; fail=$((fail + 1)); }

# run_psql <rol> <parola> <veritabanı> <sql>  → çıktı ve çıkış kodu psql'inkidir
run_psql() {
  local role=$1 pw=$2 db=$3 sql=$4
  PGPASSWORD="$pw" compose exec -T -e PGPASSWORD postgres \
    psql -h postgres -v ON_ERROR_STOP=1 --no-psqlrc -tA -U "$role" -d "$db" -c "$sql" 2>&1
}

# rol → izinli veritabanları
declare -A ALLOWED=(
  [core_db_migrator]="core_db"
  [core_db_app]="core_db"
  [agent_db_migrator]="agent_db"
  [agent_db_app]="agent_db"
  [warehouse_db_migrator]="warehouse_db"
  [warehouse_db_app]="warehouse_db"
  [warehouse_reader]="warehouse_db"
  [mlflow_db_migrator]="mlflow_db"
  [mlflow_db_app]="mlflow_db"
)
TARGETS=(core_db agent_db warehouse_db mlflow_db postgres template1)

echo "== Rol izolasyonu"
for role in core_db_migrator core_db_app agent_db_migrator agent_db_app \
            warehouse_db_migrator warehouse_db_app warehouse_reader \
            mlflow_db_migrator mlflow_db_app; do
  key="$(printf '%s' "$role" | tr '[:lower:]' '[:upper:]')_PASSWORD"
  pw="$(envval "$key")"
  if [ -z "$pw" ]; then
    bad "$key $ENV_FILE içinde tanımlı değil"
    continue
  fi
  for db in "${TARGETS[@]}"; do
    out="$(run_psql "$role" "$pw" "$db" 'select 1')"
    rc=$?
    case " ${ALLOWED[$role]} " in
      *" $db "*)
        if [ $rc -eq 0 ]; then ok "$role -> $db bağlanabildi (beklenen)"; else bad "$role -> $db bağlanamadı (beklenmeyen): $(echo "$out" | head -n 1)"; fi ;;
      *)
        if [ $rc -ne 0 ] && echo "$out" | grep -q 'permission denied for database'; then
          ok "$role -> $db reddedildi (beklenen)"
        elif [ $rc -eq 0 ]; then
          bad "$role -> $db bağlandı (İZOLASYON İHLALİ)"
        else
          bad "$role -> $db reddedildi ama nedeni 'permission denied' değil: $(echo "$out" | head -n 1)"
        fi ;;
    esac
  done
done

# Uygulama (ve salt okunur) roller DDL yapamaz ve geçici tablo açamaz (D-54, D-59).
# Denemeler BEGIN ... ROLLBACK içindedir: beklenmeyen şekilde başarılı olsalar bile hiçbir nesne kalmaz.
echo "== DDL ve TEMPORARY yetkisi (reddedilmeli)"
for role in core_db_app agent_db_app warehouse_db_app mlflow_db_app warehouse_reader; do
  key="$(printf '%s' "$role" | tr '[:lower:]' '[:upper:]')_PASSWORD"
  pw="$(envval "$key")"
  db="${ALLOWED[$role]}"
  [ -n "$pw" ] || continue
  for check in "CREATE TABLE public.verify_probe (x int)|tablo yaratma" \
               "CREATE SCHEMA verify_probe|şema yaratma" \
               "CREATE TEMP TABLE verify_probe_tmp (x int)|geçici tablo yaratma"; do
    sql="${check%%|*}"
    label="${check##*|}"
    out="$(run_psql "$role" "$pw" "$db" "BEGIN; $sql; ROLLBACK;")"
    rc=$?
    if [ $rc -ne 0 ] && echo "$out" | grep -q 'permission denied'; then
      ok "$role ($db): $label reddedildi (beklenen)"
    elif [ $rc -eq 0 ]; then
      bad "$role ($db): $label BAŞARILI OLDU (İZOLASYON/YETKİ İHLALİ; ROLLBACK ile geri alındı)"
    else
      bad "$role ($db): $label reddedildi ama nedeni 'permission denied' değil: $(echo "$out" | head -n 1)"
    fi
  done
done

echo "== Parola doğrulaması"
out="$(run_psql core_db_app "yanlis-parola-denemesi" core_db 'select 1')"
if [ $? -ne 0 ] && echo "$out" | grep -q 'password authentication failed'; then
  ok "yanlış parola reddedildi"
else
  bad "yanlış parola beklenen şekilde reddedilmedi: $(echo "$out" | head -n 1)"
fi

echo "== pgvector"
agent_pw="$(envval AGENT_DB_APP_PASSWORD)"
ver="$(run_psql agent_db_app "$agent_pw" agent_db "select extversion from pg_extension where extname = 'vector'")"
if [ $? -eq 0 ] && [ -n "$ver" ]; then ok "agent_db'de vector uzantısı yüklü (sürüm $ver)"; else bad "agent_db'de vector uzantısı yok: $ver"; fi
vec="$(run_psql agent_db_app "$agent_pw" agent_db "select '[1,2,3]'::vector(3)")"
if [ $? -eq 0 ] && [ "$vec" = "[1,2,3]" ]; then ok "vector tipi kullanılabilir"; else bad "vector tipi kullanılamadı: $vec"; fi

echo "== Port bağlaması"
bind="$(compose port postgres 5432 2>&1)"
case "$bind" in
  127.0.0.1:*) ok "postgres 5432 yalnızca 127.0.0.1'e bağlı ($bind)" ;;
  *) bad "postgres 5432 beklenmeyen adrese bağlı: $bind" ;;
esac

echo
echo "Özet: $pass başarılı, $fail başarısız"
[ "$fail" -eq 0 ]
