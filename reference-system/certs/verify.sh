#!/usr/bin/env bash
# QBank demo sertifika ve anahtarlarını doğrular (P1.1).
# Her dosyanın anahtar algoritmasını ve bit boyutunu beklenen tabloyla karşılaştırır ve tablo basar.
#   Sertifikalar : openssl x509 -noout -text
#   Anahtarlar   : openssl pkey -noout -text (boyut) ve openssl asn1parse (algoritma);
#                  anahtar çiftleri sertifika olmadığından x509 ile okunamaz.
# Yalnızca başlık satırları ayrıştırılır; anahtar içeriği değişkene alınmaz ve basılmaz.
# Çıkış kodu: tüm satırlar eşleşirse 0, aksi halde 1.
#
# Kullanım: bash verify.sh

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OUT_DIR="$SCRIPT_DIR/out"

if ! command -v openssl >/dev/null 2>&1; then
  echo "HATA: openssl bulunamadı." >&2
  exit 1
fi

# Beklenen tablo: dosya|tür|algoritma|bit
EXPECTED=(
  "ca.crt.pem|sertifika|rsaEncryption|2048"
  "ca.key.pem|ozel anahtar|rsaEncryption|2048"
  "qbank-gateway.crt.pem|sertifika|rsaEncryption|2048"
  "qbank-gateway.key.pem|ozel anahtar|rsaEncryption|2048"
  "qbank-account-service.crt.pem|sertifika|rsaEncryption|2048"
  "qbank-account-service.key.pem|ozel anahtar|rsaEncryption|2048"
  "qbank-payment-service.crt.pem|sertifika|rsaEncryption|2048"
  "qbank-payment-service.key.pem|ozel anahtar|rsaEncryption|2048"
  "gateway-to-account.crt.pem|sertifika|rsaEncryption|2048"
  "gateway-to-account.key.pem|ozel anahtar|rsaEncryption|2048"
  "gateway-to-payment.crt.pem|sertifika|rsaEncryption|2048"
  "gateway-to-payment.key.pem|ozel anahtar|rsaEncryption|2048"
  "payment-to-account.crt.pem|sertifika|rsaEncryption|2048"
  "payment-to-account.key.pem|ozel anahtar|rsaEncryption|2048"
  "payment-to-mosquitto.crt.pem|sertifika|rsaEncryption|2048"
  "payment-to-mosquitto.key.pem|ozel anahtar|rsaEncryption|2048"
  "mosquitto.crt.pem|sertifika|rsaEncryption|2048"
  "mosquitto.key.pem|ozel anahtar|rsaEncryption|2048"
  "terminal-001.crt.pem|sertifika|rsaEncryption|2048"
  "terminal-001.key.pem|ozel anahtar|rsaEncryption|2048"
  "jwt-signing.key.pem|ozel anahtar|rsaEncryption|2048"
  "jwt-signing.pub.pem|genel anahtar|rsaEncryption|2048"
  "card-token.key.pem|ozel anahtar|rsaEncryption|2048"
  "card-token.pub.pem|genel anahtar|rsaEncryption|2048"
  "receipt-signing.key.pem|ozel anahtar|rsaEncryption|1024"
  "receipt-signing.pub.pem|genel anahtar|rsaEncryption|1024"
)

short_alg() {
  case "$1" in
    rsaEncryption) echo RSA ;;
    "") echo "?" ;;
    *) echo "$1" ;;
  esac
}

# Bulunan algoritma ve bit boyutunu "algoritma bit" olarak yazar; okunamazsa boş döner.
inspect() { # <dosya> <tür>
  local f="$1" kind="$2" alg="" bits=""
  case "$kind" in
    sertifika)
      alg="$(openssl x509 -in "$f" -noout -text 2>/dev/null \
        | sed -nE 's/^[[:space:]]*Public Key Algorithm:[[:space:]]*(.*)$/\1/p' | head -1 || true)"
      bits="$(openssl x509 -in "$f" -noout -text 2>/dev/null \
        | sed -nE 's/^[[:space:]]*(RSA )?Public-Key:[[:space:]]*\(([0-9]+) bit.*/\2/p' | head -1 || true)"
      ;;
    "ozel anahtar")
      alg="$(openssl pkey -in "$f" -pubout 2>/dev/null | openssl asn1parse 2>/dev/null \
        | sed -nE 's/.*OBJECT[[:space:]]*:([A-Za-z0-9._-]+).*/\1/p' | head -1 || true)"
      bits="$(openssl pkey -in "$f" -noout -text 2>/dev/null \
        | sed -nE 's/^[[:space:]]*(RSA )?Private-Key:[[:space:]]*\(([0-9]+) bit.*/\2/p' | head -1 || true)"
      ;;
    "genel anahtar")
      alg="$(openssl asn1parse -in "$f" 2>/dev/null \
        | sed -nE 's/.*OBJECT[[:space:]]*:([A-Za-z0-9._-]+).*/\1/p' | head -1 || true)"
      bits="$(openssl pkey -pubin -in "$f" -noout -text 2>/dev/null \
        | sed -nE 's/^[[:space:]]*(RSA )?Public-Key:[[:space:]]*\(([0-9]+) bit.*/\2/p' | head -1 || true)"
      ;;
  esac
  if [ -n "$alg" ] && [ -n "$bits" ]; then
    echo "$alg $bits"
  fi
}

ROW_FMT='%-32s %-14s %-12s %-12s %s\n'
printf "$ROW_FMT" "Dosya" "Tur" "Beklenen" "Bulunan" "Sonuc"
printf "$ROW_FMT" "--------------------------------" "--------------" "------------" "------------" "-----"

failed=0
for row in "${EXPECTED[@]}"; do
  IFS='|' read -r name kind exp_alg exp_bits <<< "$row"
  expected="$(short_alg "$exp_alg")-$exp_bits"
  found="-"
  result="FAIL"
  if [ -s "$OUT_DIR/$name" ]; then
    got="$(inspect "$OUT_DIR/$name" "$kind")"
    if [ -n "$got" ]; then
      found="$(short_alg "${got% *}")-${got##* }"
      if [ "${got% *}" = "$exp_alg" ] && [ "${got##* }" = "$exp_bits" ]; then
        result="PASS"
      fi
    else
      found="okunamadi"
    fi
  else
    found="dosya yok"
  fi
  [ "$result" = "PASS" ] || failed=$((failed + 1))
  printf "$ROW_FMT" "$name" "$kind" "$expected" "$found" "$result"
done

total="${#EXPECTED[@]}"
echo
if [ "$failed" -eq 0 ]; then
  echo "Sonuc: $total/$total satir beklenen algoritma ve boyutta."
  exit 0
fi
echo "Sonuc: $failed/$total satir BASARISIZ."
exit 1
