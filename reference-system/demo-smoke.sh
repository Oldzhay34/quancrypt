#!/usr/bin/env bash
# QBank demo uçtan uca kontrolü (P1.4). `make demo-smoke` çağırır; önce `make up PROFILES=demo` çalışmış olmalıdır.
#
#   1. Gateway üzerinden login yapılır ve RS256 JWT alınır.
#   2. Ödeme oluşturulur.
#   3. Makbuz alınır ve imzası receipt-signing açık anahtarıyla (SHA1withRSA, RSA-1024) doğrulanır.
#   4. Payment loglarında field-device-sim'den gelen bir işlemin kaydedildiği görülür.
#
# Gateway sertifikasının SAN'ında IP yoktur (qbank-gateway, localhost), bu yüzden adres `localhost`'tur ve
# 127.0.0.1'e sabitlenir. Token ve parola ekrana basılmaz.
set -euo pipefail

ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
CERTS="$ROOT/reference-system/certs/out"
BASE="https://localhost:9443"
# ENV_FILE (kök Makefile verir) varsa compose ona göre çalışır; yoksa compose kendi varsayılanını kullanır.
compose=(docker compose)
if [ -n "${ENV_FILE:-}" ]; then
  compose+=(--env-file "$ENV_FILE")
fi
compose+=(--profile demo)
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

step() { printf '\n[%s] %s\n' "$1" "$2"; }
fail() { printf 'BAŞARISIZ: %s\n' "$*" >&2; exit 1; }

# curl ile gateway'e istek atar; gövdeyi $WORK/body'ye yazar ve HTTP durum kodunu basar.
gateway() {
  curl --silent --show-error --max-time 20 \
    --cacert "$CERTS/ca.crt.pem" --resolve localhost:9443:127.0.0.1 \
    --output "$WORK/body" --write-out '%{http_code}' "$@"
}

json() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$WORK/body" "$1"; }

[ -f "$CERTS/ca.crt.pem" ] || fail "sertifikalar yok: bash reference-system/certs/generate.sh"

step 1 "login (demo1) ve JWT"
printf '%s' '{"username":"demo1","password":"demo1-demo-pass"}' > "$WORK/login.json"
status="$(gateway -X POST "$BASE/api/v1/auth/login" -H 'Content-Type: application/json' -d @"$WORK/login.json")"
[ "$status" = "200" ] || fail "login HTTP $status"
printf 'Authorization: Bearer %s' "$(json accessToken)" > "$WORK/auth"
alg="$(python3 - "$WORK/auth" <<'PY'
import base64, json, sys
header = open(sys.argv[1], encoding="utf-8").read().split(" ", 2)[2].split(".")[0]
print(json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))["alg"])
PY
)"
[ "$alg" = "RS256" ] || fail "JWT alg RS256 değil: $alg"
echo "  login 200, JWT alg=$alg"

step 2 "ödeme oluşturma"
key="smoke-$(date +%s)-$RANDOM"
printf '%s' '{"accountId":"acc-001","amount":"12.50","currency":"TRY","cardNumber":"4111111111111111"}' > "$WORK/payment.json"
status="$(gateway -X POST "$BASE/api/v1/payments" -H @"$WORK/auth" -H "Idempotency-Key: $key" \
  -H 'Content-Type: application/json' -d @"$WORK/payment.json")"
[ "$status" = "201" ] || fail "ödeme HTTP $status"
payment_id="$(json paymentId)"
echo "  ödeme 201, paymentId=$payment_id"

step 3 "makbuz ve imza doğrulaması"
status="$(gateway -X POST "$BASE/api/v1/payments/$payment_id/receipt" -H @"$WORK/auth")"
[ "$status" = "200" ] || fail "makbuz HTTP $status"
python3 - "$WORK/body" "$WORK" <<'PY'
import base64, json, sys
body = json.load(open(sys.argv[1]))
assert body["algorithm"] == "SHA1withRSA", body["algorithm"]
receipt = body["receipt"]
# D-93: kompakt JSON, sabit alan sırası, boşluk yok
order = ("paymentId", "accountId", "amount", "currency", "issuedAt")
signed = json.dumps({name: receipt[name] for name in order}, separators=(",", ":"))
tampered = json.dumps({name: ("13.50" if name == "amount" else receipt[name]) for name in order}, separators=(",", ":"))
open(sys.argv[2] + "/signed.json", "w", encoding="utf-8").write(signed)
open(sys.argv[2] + "/tampered.json", "w", encoding="utf-8").write(tampered)
open(sys.argv[2] + "/signature.bin", "wb").write(base64.b64decode(body["signature"]))
PY
verified="$(openssl dgst -sha1 -verify "$CERTS/receipt-signing.pub.pem" -signature "$WORK/signature.bin" "$WORK/signed.json" 2>&1)" \
  || fail "makbuz imzası doğrulanamadı: $verified"
[ "$verified" = "Verified OK" ] || fail "makbuz imzası: $verified"
if openssl dgst -sha1 -verify "$CERTS/receipt-signing.pub.pem" -signature "$WORK/signature.bin" "$WORK/tampered.json" \
  >/dev/null 2>&1; then
  fail "değiştirilmiş makbuz da doğrulandı"
fi
echo "  makbuz 200, SHA1withRSA imzası receipt-signing.pub.pem ile: $verified (değiştirilmiş makbuz reddedildi)"

step 4 "saha cihazından gelen işlem payment loglarında"
# Earlier runs leave their log lines in the container: the count must grow while this script waits.
payment_logs="$("${compose[@]}" logs --no-color qbank-payment-service)"
before="$(printf '%s\n' "$payment_logs" | grep -c 'terminal message recorded' || true)"
recorded="$before"
for _ in $(seq 1 15); do
  sleep 2
  payment_logs="$("${compose[@]}" logs --no-color qbank-payment-service)"
  recorded="$(printf '%s\n' "$payment_logs" | grep -c 'terminal message recorded' || true)"
  [ "$recorded" -gt "$before" ] && break
done
[ "$recorded" -gt "$before" ] || fail "bu çalıştırma sırasında payment loglarına yeni 'terminal message recorded' satırı düşmedi"
device_logs="$("${compose[@]}" logs --no-color field-device-sim)"
published="$(printf '%s\n' "$device_logs" | grep -c 'published transaction' || true)"
[ "$published" -ge 1 ] || fail "field-device-sim loglarında yayımlanan işlem yok"
echo "  payment bu çalıştırmada $((recorded - before)) yeni işlem kaydetti, field-device-sim toplam $published işlem yayımladı"

printf '\nTÜMÜ GEÇTİ\n'
