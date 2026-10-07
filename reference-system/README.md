# QBank referans sistemi

QBank, Quancrypt'in demo hedefi olan küçük bir bankacılık sistemidir ve **bilerek RSA ile kurulmuştur**. Quancrypt'in analizcisi bu sistemi tarar; RSA kullanımını, servisler ve saha terminali arasındaki bağlantıları ve her bağlantının kriptosunu bulur, ardından ML-KEM/ML-DSA hibrit geçişi için riske göre sıralı bir plan üretir. QBank gerçek bir bankacılık ürünü değildir; yalnızca demo amaçlıdır, veritabanı kullanmaz (bellek içi adaptörler) ve gerçek kart verisi içermez (yalnızca test kart numaraları).

## Bileşenler

| Bileşen | Rol |
|---|---|
| `qbank-gateway` | Spring Cloud Gateway; yalnızca rota ve TLS yapılandırması, iş mantığı yok |
| `qbank-account-service` | Kimlik doğrulama (RS256 JWT yayımlar, JWKS sunar) ve hesap bilgisi |
| `qbank-payment-service` | Ödeme alır, kart numarasını RSA-OAEP ile token'lar ve saklar, imzalı makbuz üretir |
| `mosquitto` | Saha terminalinin bağlandığı MQTT broker'ı (TLS) |
| `field-device-sim` | Saha terminali simülatörü (`terminal-001`); aynı kod PYNQ-Z2'de çalışır |

Servis kodu P1.2–P1.4'te yazılır. Bu dizinde şu an yalnızca sertifika üretimi ve kontratlar vardır:

- `certs/`: demo CA, sertifikalar ve anahtar çiftleri; ayrıntılar `certs/README.md`'de
- `contracts/`: `qbank-account.openapi.yaml`, `qbank-payment.openapi.yaml` (OpenAPI 3.1) ve `terminal-transaction.schema.json` (MQTT konusu `terminal/{terminalId}/transactions` için JSON Schema)

## Bilerek konan zayıflıklar

Aşağıdaki zayıflıklar Quancrypt'in bulması için bilerek QBank'e konmuştur. Öncelik sütunu `crypto-domain` skill'indeki öncelik tablosundan ve dokümandaki demo senaryosundan gelir ("P0 zayıf anahtar, P1 servisler arası TLS ve RSA-OAEP, P3 JWT").

| # | Zayıflık | Yeri | Beklenen öncelik |
|---|---|---|---|
| 1 | Bilerek zayıf RSA-1024 anahtarı | Makbuz imzası (`receipt-signing`) | P0 |
| 2 | SHA-1 ile imza (`SHA1withRSA`) | Makbuz imzası (`receipt-signing`) | P0 |
| 3 | Servisler arası TLS ve mTLS'te RSA sertifikalı, JDK 27 öncesi varsayılanıyla klasik anahtar değişimi (`crypto-domain`: JDK 27 öncesinde hibrit grup yok) | gateway → account, gateway → payment, payment → account | P1 |
| 4 | Kart numarasının RSA-OAEP ile şifrelenmesi (uygulama içi RSA şifreleme) | Ödeme servisi (`card-token`) | P1 |
| 5 | Saha terminalinin MQTT üzerinden RSA sertifikalı TLS bağlantısı | `terminal-001` → `mosquitto` | P1 |
| 6 | RS256 imzalı JWT | Hesap servisi (`jwt-signing`) | P3 |
| 7 | RSA-2048 sertifikalar ve mTLS kimlik doğrulaması | Tüm sunucu ve istemci sertifikaları | P3 |

### Yasak kalıplar ile ilişki

`crypto-domain` skill'indeki yasak kalıplar (her sertifikaya güvenen `TrustManager`, TLS 1.0/1.1, ECB modu, kaynağa gömülü anahtar vb.) Quancrypt'in kendi kodunda, önerilerinde ve dönüşümlerinde kullanılamaz. Bu kuralın tek istisnası `reference-system/` dizinidir ve yalnızca yukarıdaki listedeki bilerek konmuş zayıflıkları kapsar. Listede olmayan hiçbir yasak kalıp QBank'e konmaz.

## Çalıştırma

`TODO(P1.1-1)`: Tam çalıştırma talimatı P1.4'te (gateway, Mosquitto, saha cihazı ve demo profili) yazılır.

Şimdilik yalnızca sertifikalar üretilebilir ve doğrulanabilir (WSL içinden):

```bash
bash reference-system/certs/generate.sh
bash reference-system/certs/verify.sh
```
