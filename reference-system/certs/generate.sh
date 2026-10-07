#!/usr/bin/env bash
# QBank demo sertifika ve anahtar üreticisi (P1.1).
# Yalnızca PEM üretir; keystore (PKCS#12, JKS) üretmez (D-19).
# Çıktı yalnızca bu betiğin yanındaki out/ dizinine yazılır (D-78); dizin ortam değişkeniyle değiştirilemez.
#
# Kullanım:
#   bash generate.sh           Eksik dosyaları üretir; var olanları atlar (idempotent).
#   bash generate.sh --force   Betiğin bildiği tüm dosyaları silip yeniden üretir.
#
# QBank bilerek RSA ile kurulmuştur; receipt-signing anahtarı bilerek zayıftır (RSA-1024).
# Bu anahtarlar yalnızca demo içindir ve out/ içinde parolasız durur.

set -euo pipefail
umask 077

DAYS=825 # D-70: CA ve tüm sertifikalar
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OUT_DIR="$SCRIPT_DIR/out"

# Sunucu sertifikaları: SAN olarak servis adı ve localhost taşır.
SERVERS=(qbank-gateway qbank-account-service qbank-payment-service mosquitto)
# mTLS istemci ve cihaz sertifikaları: SAN yok (promptta istenmedi).
CLIENTS=(gateway-to-account payment-to-account payment-to-mosquitto terminal-001)
# Yalnızca anahtar çifti (sertifika yok, D-72): ad:bit
KEYPAIRS=(jwt-signing:2048 card-token:2048 receipt-signing:1024)

FORCE=0
if [ "$#" -gt 1 ]; then
  echo "HATA: en fazla bir argüman verilebilir. Kullanım: bash generate.sh [--force]" >&2
  exit 2
fi
case "${1:-}" in
  "") ;;
  --force) FORCE=1 ;;
  *)
    echo "HATA: bilinmeyen argüman '$1'. Kullanım: bash generate.sh [--force]" >&2
    exit 2
    ;;
esac

if ! command -v openssl >/dev/null 2>&1; then
  echo "HATA: openssl bulunamadı." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# `openssl req` için asgari bir istek yapılandırması kullanılır (ortamdaki varsayılan req ayarlarına bağlı kalmamak için).
REQ_CNF="$TMP_DIR/req.cnf"
printf '[req]\ndistinguished_name = dn\nprompt = no\n[dn]\nCN = placeholder\n' > "$REQ_CNF"

created=0
skipped=0

# Betiğin ürettiği dosyalar. --force yalnızca bunları siler.
known_files() {
  echo ca.crt.pem ca.key.pem
  local n
  for n in "${SERVERS[@]}" "${CLIENTS[@]}"; do
    echo "$n.crt.pem" "$n.key.pem"
  done
  local kp
  for kp in "${KEYPAIRS[@]}"; do
    echo "${kp%%:*}.key.pem" "${kp%%:*}.pub.pem"
  done
}

rand_serial() {
  # Rastgele 80 bit; başına sabit bir 1 hanesi eklenir, böylece seri numarası pozitif ve sıfırdan farklı olur.
  local s
  s="$(openssl rand -hex 10)"
  printf '0x1%s' "$s"
}

# openssl'in ilerleme noktalarını ve bilgi satırlarını gizler; hata olursa çıktısını gösterir.
run_quiet() {
  if ! "$@" > "$TMP_DIR/openssl.log" 2>&1; then
    cat "$TMP_DIR/openssl.log" >&2
    return 1
  fi
}

harden() {
  # drvfs (/mnt/c) üzerinde chmod etkisiz olabilir; bu yüzden en iyi çabadır.
  chmod 600 "$@" 2>/dev/null || true
}

have_all() {
  local f
  for f in "$@"; do
    [ -s "$OUT_DIR/$f" ] || return 1
  done
  return 0
}

note_created() { echo "ÜRETİLDİ  out/$1"; created=$((created + 1)); }
note_skipped() { echo "ATLANDI   out/$1"; skipped=$((skipped + 1)); }

new_private_key() { # <bit> <dosya>
  run_quiet openssl genpkey -algorithm RSA -pkeyopt "rsa_keygen_bits:$1" -out "$OUT_DIR/$2"
  harden "$OUT_DIR/$2"
}

gen_ca() {
  new_private_key 2048 ca.key.pem
  run_quiet openssl req -x509 -new -config "$REQ_CNF" -key "$OUT_DIR/ca.key.pem" -sha256 -days "$DAYS" \
    -subj "/O=QBank Demo/CN=QBank Demo CA" -set_serial "$(rand_serial)" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" \
    -out "$OUT_DIR/ca.crt.pem"
  note_created ca.key.pem
  note_created ca.crt.pem
}

gen_leaf() { # <ad> <server|client>
  local name="$1" kind="$2" ext="$TMP_DIR/$1.ext"
  {
    echo "basicConstraints=critical,CA:FALSE"
    if [ "$kind" = server ]; then
      echo "keyUsage=critical,digitalSignature,keyEncipherment"
      echo "extendedKeyUsage=serverAuth"
      echo "subjectAltName=DNS:$name,DNS:localhost"
    else
      echo "keyUsage=critical,digitalSignature"
      echo "extendedKeyUsage=clientAuth"
    fi
    echo "subjectKeyIdentifier=hash"
    echo "authorityKeyIdentifier=keyid"
  } > "$ext"
  new_private_key 2048 "$name.key.pem"
  run_quiet openssl req -new -config "$REQ_CNF" -key "$OUT_DIR/$name.key.pem" \
    -subj "/O=QBank Demo/CN=$name" -out "$TMP_DIR/$name.csr"
  run_quiet openssl x509 -req -in "$TMP_DIR/$name.csr" -CA "$OUT_DIR/ca.crt.pem" -CAkey "$OUT_DIR/ca.key.pem" \
    -set_serial "$(rand_serial)" -days "$DAYS" -sha256 -extfile "$ext" -out "$OUT_DIR/$name.crt.pem"
  note_created "$name.key.pem"
  note_created "$name.crt.pem"
}

gen_keypair() { # <ad> <bit>
  new_private_key "$2" "$1.key.pem"
  run_quiet openssl pkey -in "$OUT_DIR/$1.key.pem" -pubout -out "$OUT_DIR/$1.pub.pem"
  note_created "$1.key.pem"
  note_created "$1.pub.pem"
}

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR" 2>/dev/null || true

if [ "$FORCE" -eq 1 ]; then
  for f in $(known_files); do
    rm -f "$OUT_DIR/$f"
  done
  echo "--force: bilinen dosyalar silindi, yeniden üretiliyor."
fi

# CA eksikse (veya yarımsa) CA ile imzalı tüm sertifikalar yeniden üretilir; zincir tutarsız kalmaz.
regen_signed=0
if have_all ca.crt.pem ca.key.pem; then
  note_skipped ca.key.pem
  note_skipped ca.crt.pem
else
  gen_ca
  regen_signed=1
fi

for n in "${SERVERS[@]}"; do
  if [ "$regen_signed" -eq 0 ] && have_all "$n.crt.pem" "$n.key.pem"; then
    note_skipped "$n.key.pem"
    note_skipped "$n.crt.pem"
  else
    gen_leaf "$n" server
  fi
done

for n in "${CLIENTS[@]}"; do
  if [ "$regen_signed" -eq 0 ] && have_all "$n.crt.pem" "$n.key.pem"; then
    note_skipped "$n.key.pem"
    note_skipped "$n.crt.pem"
  else
    gen_leaf "$n" client
  fi
done

for kp in "${KEYPAIRS[@]}"; do
  name="${kp%%:*}"
  bits="${kp##*:}"
  if have_all "$name.key.pem" "$name.pub.pem"; then
    note_skipped "$name.key.pem"
    note_skipped "$name.pub.pem"
  else
    gen_keypair "$name" "$bits"
  fi
done

echo
echo "Özet: $created dosya üretildi, $skipped dosya atlandı (çıktı dizini: reference-system/certs/out/)."
