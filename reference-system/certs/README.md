# QBank sertifikaları ve anahtarları

`generate.sh` demo CA'yı, sertifikaları ve anahtar çiftlerini OpenSSL ile üretir; `verify.sh` her dosyanın algoritmasını ve boyutunu doğrular. Yalnızca PEM üretilir; keystore (PKCS#12, JKS) üretilmez (D-19). Çıktı yalnızca `out/` dizinine yazılır ve git'e girmez.

```bash
bash reference-system/certs/generate.sh           # eksik dosyaları üretir; var olanları atlar
bash reference-system/certs/generate.sh --force   # bilinen tüm dosyaları silip yeniden üretir
bash reference-system/certs/verify.sh             # beklenen tabloyla karşılaştırır, tablo basar
```

Tüm sertifikalar ve CA 825 gün geçerlidir (D-70), SHA-256 ile imzalanır ve RSA-2048'dir. Özel anahtarlar PKCS#8 PEM biçimindedir ve parolasızdır; bunlar yalnızca demo anahtarlarıdır. `generate.sh` `chmod 600` dener, ancak repo Windows diski üzerinde (`/mnt/c`) durduğunda dosya izinleri uygulanmayabilir; anahtarların korunması `out/` dizininin git dışı olmasına dayanır.

Yaprak sertifikalar CA ile aynı anda ya da biraz (tek çalıştırmada yaklaşık bir saniye, sonradan tek başına üretilirse daha fazla) geç sona erer. `generate.sh` CA yoksa tüm imzalı sertifikaları birlikte yeniden üretir.

## Dosyalar ve kullanıldıkları yer

Aşağıdaki kullanım, QBank'in tasarımına göre amaçlanan kullanımdır; servis kodu P1.2–P1.4'te yazılır ve orada doğrulanır. Portlar `docs/ports.md`'dedir.

| Dosya (`out/` altında) | Tür | Kullanan | Amaç |
|---|---|---|---|
| `ca.crt.pem` | Demo CA sertifikası (RSA-2048) | tüm servisler, `mosquitto`, `field-device-sim` | Güven kökü: karşı tarafın sertifikasını doğrular |
| `ca.key.pem` | Demo CA özel anahtarı | yalnızca `generate.sh` | Sertifika imzalar; hiçbir servise bağlanmaz |
| `qbank-gateway.crt.pem`, `qbank-gateway.key.pem` | Sunucu sertifikası (SAN: `qbank-gateway`, `localhost`) | `qbank-gateway` | Gateway'in TLS sunucu kimliği |
| `qbank-account-service.crt.pem`, `.key.pem` | Sunucu sertifikası (SAN: `qbank-account-service`, `localhost`) | `qbank-account-service` | Hesap servisinin TLS sunucu kimliği |
| `qbank-payment-service.crt.pem`, `.key.pem` | Sunucu sertifikası (SAN: `qbank-payment-service`, `localhost`) | `qbank-payment-service` | Ödeme servisinin TLS sunucu kimliği |
| `mosquitto.crt.pem`, `mosquitto.key.pem` | Sunucu sertifikası (SAN: `mosquitto`, `localhost`) | `mosquitto` | MQTT broker'ının TLS sunucu kimliği |
| `gateway-to-account.crt.pem`, `.key.pem` | mTLS istemci sertifikası | `qbank-gateway` | Gateway → hesap servisi bağlantısında istemci kimliği |
| `gateway-to-payment.crt.pem`, `.key.pem` | mTLS istemci sertifikası | `qbank-gateway` | Gateway → ödeme servisi bağlantısında istemci kimliği |
| `payment-to-account.crt.pem`, `.key.pem` | mTLS istemci sertifikası | `qbank-payment-service` | Ödeme → hesap servisi bağlantısında istemci kimliği |
| `terminal-001.crt.pem`, `terminal-001.key.pem` | Cihaz istemci sertifikası | `field-device-sim` | Saha terminalinin MQTT bağlantısında istemci kimliği |
| `jwt-signing.key.pem` | JWT imzalama özel anahtarı (RSA-2048) | `qbank-account-service` | RS256 JWT imzalar |
| `jwt-signing.pub.pem` | JWT doğrulama genel anahtarı | `qbank-account-service` | `/.well-known/jwks.json` içinde yayımlanır; diğer servisler JWT'yi bununla doğrular |
| `card-token.pub.pem`, `card-token.key.pem` | Kart token'ı anahtar çifti (RSA-2048) | `qbank-payment-service` | Kart numarası RSA-OAEP ile şifrelenir ve saklanır (D-71) |
| `receipt-signing.key.pem` | Makbuz imzalama özel anahtarı (**RSA-1024, bilerek zayıf**) | `qbank-payment-service` | Makbuzu imzalar |
| `receipt-signing.pub.pem` | Makbuz doğrulama genel anahtarı (**RSA-1024**) | `qbank-payment-service` | Makbuz imzasını doğrular |

İstemci sertifikalarında SAN yoktur; kimlik `CN` alanındadır (`CN` dosya adıyla aynıdır). JWT, kart ve makbuz için yalnızca anahtar çifti üretilir, sertifika üretilmez (D-72).

Özel anahtarlar `*.key.pem` adlıdır; kök `.gitignore` `*.key.pem` ve `*-key.pem` desenlerini yok sayar (D-78).
