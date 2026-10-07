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

Dizin yapısı:

- `certs/`: demo CA, sertifikalar ve anahtar çiftleri; ayrıntılar `certs/README.md`'de
- `contracts/`: `qbank-account.openapi.yaml`, `qbank-payment.openapi.yaml` (OpenAPI 3.1) ve `terminal-transaction.schema.json` (MQTT konusu `terminal/{terminalId}/transactions` için JSON Schema)
- `qbank-gateway/`, `qbank-account-service/`, `qbank-payment-service/`: Java servisleri (her birinin kendi `README.md`'si ve `make verify`'ı vardır)
- `mosquitto/`: broker yapılandırması (`mosquitto.conf`) ve konu yetkileri (`acl`)
- `field-device-sim/`: saha terminali simülatörü (Python)
- `expected/`: Quancrypt analizci testlerinin altın verisi (`crypto_inventory.yaml`, `topology.yaml`); kullanıcı onayı olmadan Faz 3 testlerinde kullanılmaz
- `demo-smoke.sh`: `make demo-smoke`'un betiği

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

Gereken araçlar: Docker (Compose v2) ve WSL2 Ubuntu'daki `bash`, `openssl`, `curl`, `python3`. Komutlar repo kökünden çalışır.

```bash
bash reference-system/certs/generate.sh   # demo CA, sertifikalar ve anahtarlar (varsa atlar)
cp .env.example .env                      # yalnızca ilk seferde; CHANGE_ME değerlerini doldurun (postgres her `make up`'ta kalkar, D-53)
make up PROFILES=demo                     # gateway, hesap, ödeme, mosquitto ve saha cihazı; hepsi healthy olunca döner
make demo-smoke                           # login, ödeme, makbuz imzası ve cihazdan gelen işlem
make down PROFILES=demo
```

`make demo-smoke` şunları doğrular: (1) gateway üzerinden `demo1` ile login ve RS256 JWT, (2) ödeme, (3) makbuz ve imzasının `receipt-signing.pub.pem` ile `openssl dgst -sha1 -verify` doğrulaması (değiştirilmiş makbuz reddedilir), (4) payment loglarında `field-device-sim`'den gelen bir işlemin kaydı. İlk `make up` imajları üretir ve `gradle`, `eclipse-temurin` ve `python` taban imajlarını çeker (internet gerekir; sonraki çalıştırmalarda önbellek kullanılır).

Dışarıdan tek giriş noktası gateway'dir: `https://localhost:9443` (yalnızca `127.0.0.1`'e yayımlanır). Sertifikasının SAN'ında IP yoktur (`qbank-gateway`, `localhost`), bu yüzden adres `localhost` olmalıdır:

```bash
curl --cacert reference-system/certs/out/ca.crt.pem --resolve localhost:9443:127.0.0.1 \
  -X POST https://localhost:9443/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"demo1","password":"demo1-demo-pass"}'
```

Demo kullanıcıları ve hesapları `qbank-account-service/README.md`'dedir. Diğer servisler (`qbank-account-service`, `qbank-payment-service`, `mosquitto`) ana makineye yayımlanmaz; `qbank-net` ve `qbank-device` ağları `internal` olduğundan demo servisleri dış ağa çıkamaz, yalnızca `qbank-gateway` ayrıca `quancrypt` ağına bağlıdır. Anahtar dosyaları `600` izinlidir ve konteynerler 10001 (Mosquitto kendi kullanıcısı) ile çalışır; demo repo `/mnt/c` (drvfs, izinler 777 görünür) altında çalıştığı için okunabilir, ext4'e taşınırsa anahtar dosyası izni/sahipliği çözülmelidir. Sertifika ve anahtarlar her konteynere yalnızca gereken dosyalar tek tek salt okunur bağlanır; `ca.key.pem` ve `card-token.key.pem` hiçbir konteynere girmez.

Servisleri tek tek doğrulamak için: `make verify` (her servis dizininde) veya `make verify-all` (kökte). Payment ve `field-device-sim` testleri Docker'ın açık olmasını ister (gerçek Mosquitto konteyneri başlatırlar).

### Erişim denetimi

- Her servis ana portunda mTLS ister; demo CA'nın imzaladığı ve `clientAuth` taşıyan her istemci sertifikası kabul edilir (CN izin listesi yoktur, D-91, D-108). Erişim kuralı ağ ayrımıyla sağlanır (D-122): `qbank-net` (internal) gateway, hesap, ödeme ve Mosquitto'yu taşır; `qbank-device` (internal) yalnızca Mosquitto ve `field-device-sim`'i taşır. Saha cihazı hesap ve ödeme servisine ağdan ulaşamaz, yalnızca broker'a ulaşır; dışarıdan yalnızca gateway'e `127.0.0.1:9443` ile girilir. Aynı `qbank-net` içindeki servisler birbirine mTLS ile ulaşabilir (örneğin Mosquitto hesap servisinin portuna ağdan erişebilir; sertifikası olmadığı için el sıkışma reddedilir).
- Mosquitto'da `require_certificate true` ve `use_identity_as_username true` vardır; konu yetkileri `mosquitto/acl`'dedir: her istemci yalnızca `terminal/<kendi CN'i>/transactions` konusuna yazabilir, yalnızca `payment-to-mosquitto` `terminal/+/transactions` konusunu okuyabilir (D-118). Mosquitto 2.0.22, MQTT 3.1.1 istemcisinin yetkisiz aboneliğine başarı yanıtı verir ama mesajı iletmez; testler iletimi denetler.
