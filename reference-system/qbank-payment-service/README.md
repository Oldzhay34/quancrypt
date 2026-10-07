# qbank-payment-service

QBank ödeme servisi (referans sistem, bilerek RSA ile kurulmuştur): ödemeyi alır, kart numarasını RSA-OAEP ile token'lar, imzalı makbuz üretir ve saha terminalinden MQTT üzerinden TLS ile işlem alır. Java 25, Spring Boot, Gradle Kotlin DSL; hexagonal ve SOLID (D-05); veritabanı yok, bellek içi adaptörler (D-29). Paket kökü `com.quancrypt.qbank.payment`.

Kontrat: [`../contracts/qbank-payment.openapi.yaml`](../contracts/qbank-payment.openapi.yaml) (REST) ve [`../contracts/terminal-transaction.schema.json`](../contracts/terminal-transaction.schema.json) (MQTT mesajı). Kod kontrata uyar; sözleşme testi (`ApiContractTest`) bunu denetler.

## Uçlar ve erişim kuralları

Ana port (varsayılan 9445) **tüm uçlarda mTLS** ister (`server.ssl.client-auth: need`, D-100) ve ayrıca **Bearer JWT** ister: hesap servisinin RS256 imzalı token'ı, JWKS adresi hesap servisidir ve `mTLS` ile çekilir (`payment-to-account` istemci sertifikası). Token geçerli değilse 401.

| Uç | Davranış |
|---|---|
| `POST /api/v1/payments` | Hesabı **çağıranın JWT'sini hesap servisine ileterek** doğrular (hesap servisi hesabı yalnızca sahibine verir, D-101); kart numarasını token'lar, ödemeyi kaydeder. 201; 403 hesap sana ait değil, 404 hesap yok, 503 hesap servisi erişilemiyor, 409 `Idempotency-Key` başka bir istekle kullanıldı |
| `GET /api/v1/payments/{paymentId}` | Ödemeyi döner. UUID olmayan kimlik 404'tür. **Sahiplik denetimi yok** (D-102) |
| `POST /api/v1/payments/{paymentId}/receipt` | İmzalı makbuz döner. **Sahiplik denetimi yok** (D-102) |

Yanıtlar kart numarasını da token'ını da içermez. `POST` uçları `Idempotency-Key` kabul eder: aynı anahtar ve aynı istek ilk sonucu döner, anahtar token sahibine özgüdür, farklı istekle gelirse 409. İstek parmak izi SHA-256 olarak tutulur; kart numarası düz metin saklanmaz. Hatalar RFC 9457 `application/problem+json`; her yanıt `X-Trace-Id` taşır.

### Makbuz imzası (D-92, D-93)

`receipt` nesnesi şu **kompakt JSON** metnine çevrilir (alan sırası sabit, boşluk yok) ve bu metnin UTF-8 baytları `SHA1withRSA` ile `receipt-signing` anahtarıyla imzalanır; `signature` standart base64'tür:

```
{"paymentId":"...","accountId":"...","amount":"12.50","currency":"TRY","issuedAt":"2026-10-07T10:15:30Z"}
```

Doğrulamak için `receipt-signing.pub.pem` (RSA-1024) kullanılır: `openssl dgst -sha1 -verify receipt-signing.pub.pem -signature imza.bin metin.json`. `keyId`, bu genel anahtarın RFC 7638 thumbprint'idir. **Bilerek zayıf:** hem RSA-1024 hem SHA-1 (P0 bulgular, `../README.md` zayıflık listesi); bu sınıflar `reference-system/` dışına taşınamaz.

### Kart token'ı (D-71, D-97)

`Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")` ile `card-token.pub.pem` (RSA-2048) altında şifrelenir; çıktı 256 bayt, base64. "ECB" JCA'nın ad kalıbıdır, RSA'nın blok modu yoktur. Test (`CryptoRoundTripTest`) bu dönüşümün OAEP özetini SHA-256, MGF1 özetini **SHA-1** olarak gözlemler; başka araçla çözerken `OAEPParameterSpec` veya eşdeğer ayar gerekir. Servis özel anahtarı bilmez ve token'ı çözmez; özel anahtar (`card-token.key.pem`) servise bağlanmaz.

## MQTT aboneliği (D-98, D-103)

Servis açılırken `MQTT_BROKER_URL` adresindeki broker'a `payment-to-mosquitto` istemci sertifikasıyla TLS üzerinden bağlanır ve `terminal/+/transactions` konusuna QoS 1 ile abone olur (Paho mqttv3 1.2.5, D-94). Broker erişilemezse servis yine açılır, readiness etkilenmez ve bağlantı 10 saniyede bir yeniden denenir; bağlantı koparsa Paho otomatik yeniden bağlanır ve yeniden abone olunur.

Mesaj `terminal-transaction.schema.json`'a göre doğrulanır; konudaki `{terminalId}` ile mesajdaki `terminalId` aynı olmalıdır. Şemaya uymayan, konusu uyuşmayan veya 4 KB'tan büyük mesaj atılır ve yalnızca neden loglanır (içerik değil). Aynı `transactionId` ikinci kez gelirse yok sayılır (ilk kayıt kalır). Hesap servisinde hesap varlığı kontrol edilmez.

## Yapılandırma

Yalnızca ortam değişkenleriyle yapılandırılır; varsayılanlar yerel geliştirme içindir (imajda `Dockerfile` değerleri geçerlidir).

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `QBANK_CERTS_DIR` | `../certs/out` (imajda `/certs`) | `reference-system/certs/generate.sh`'ın ürettiği PEM dizini |
| `SERVER_PORT` | `9445` | mTLS ana portu |
| `MANAGEMENT_SERVER_PORT` | `9545` | Sağlık portu (düz HTTP, loopback) |
| `ACCOUNT_SERVICE_URL` | `https://localhost:9444` (imajda `https://qbank-account-service:9444`) | Hesap servisi |
| `MQTT_BROKER_URL` | `ssl://localhost:8883` (imajda `ssl://mosquitto:8883`) | MQTT broker'ı |

Kullanılan dosyalar (`QBANK_CERTS_DIR` altında): `qbank-payment-service.crt.pem` ve `.key.pem` (sunucu kimliği), `ca.crt.pem` (güven kökü), `payment-to-account.crt.pem` ve `.key.pem` (hesap servisine ve JWKS'e mTLS), `payment-to-mosquitto.crt.pem` ve `.key.pem` (MQTT), `card-token.pub.pem` (yalnızca genel anahtar), `receipt-signing.key.pem` ve `receipt-signing.pub.pem`. `ca.key.pem` ve `card-token.key.pem` hiçbir zaman bağlanmaz.

Hesap servisi çağrısında bağlanma 2 sn, okuma 3 sn zaman aşımı vardır; teknik hatada en fazla bir yeniden deneme ve devre kesici (10 çağrılık pencere, %50 hata eşiği, 10 sn açık kalma) devrededir. 403, 404 ve 401 yanıtları iş sonucudur: yeniden denenmez ve devre kesiciyi etkilemez. Hesap servisinin başka bir 4xx yanıtı (ör. 400) teknik hata sayılmaz: yeniden denenmez, devre kesiciye hata yazılmaz ve istemciye 503 döner (D-106). `accountId` yalnızca `[A-Za-z0-9._-]` karakterlerinden oluşan 1-64 karakterdir (D-105). Makbuz ucunda boş veya 128 karakterden uzun `Idempotency-Key` 400 döner. `ACCOUNT_SERVICE_URL` `https://`, `MQTT_BROKER_URL` `ssl://` ile başlamıyorsa servis açılmaz.

Sağlık uçları (`/health/liveness`, `/health/readiness`) ayrı yönetim portundadır: düz HTTP, konteyner içinde `127.0.0.1`'e bağlı, yayımlanmaz (D-88, D-100).

## Komutlar

```bash
make verify   # sertifikaları üretir (yoksa), sonra ./gradlew check; Docker Desktop açık olmalı
make run      # servisi yerelde çalıştırır (hesap servisi ve Mosquitto ayrıca çalışmalıdır)
make image    # Docker imajı: qbank-payment-service:1.0.0 (build bağlamı reference-system/)
```

`make verify` şunları çalıştırır: Checkstyle, SpotBugs, ArchUnit (mimari ve "kripto yalnızca `infrastructure`'da"), birim, port sözleşmeleri (LSP), kripto gidiş-dönüş testleri, API sözleşmesi, mTLS/JWT entegrasyonu, MQTT entegrasyonu ve JaCoCo (domain ve usecase için en az %75 satır kapsamı). **MQTT entegrasyon testi Testcontainers ile `eclipse-mosquitto:2.0.22` konteyneri başlatır: Docker Desktop açık ve WSL entegrasyonu etkin olmalıdır; Docker yoksa test atlanmaz, başarısız olur.** Testler gerçek demo sertifikalarını kullanır; sertifikalar yoksa `make certs` gerekir. Hesap servisinin yerine testlerde, gerçek hesap servisi sertifikasıyla ve `payment-to-account` istemci sertifikasını zorunlu kılan bir JDK `HttpsServer` test çifti kullanılır.

## Katmanlar

```
api            REST controller, DTO, hata işleyici (problem+json), TraceIdFilter; api/mqtt: MQTT dinleyicisi (gelen adaptör)
facade         kaba taneli giriş noktaları ve facade DTO/hataları
port.inbound   use case arayüzleri, komut/sorgu/sonuç kayıtları, use case hataları
port.outbound  PaymentRepository, TerminalTransactionRepository, AccountDirectory, CardTokenizer, ReceiptSigner, Clock, IdGenerator, IdempotencyStore
usecase        CreatePaymentService, GetPaymentService, IssueReceiptService, RecordTerminalTransactionService
domain         Payment, CardToken, Receipt, ReceiptSignature, IssuedReceipt, TerminalTransaction, AccountId, AccountSummary, Caller (yalnızca java.*)
infrastructure persistence (bellek içi), crypto (RSA-OAEP, SHA1withRSA, PEM, thumbprint, parmak izi), client (RestClient + Resilience4j), security (Spring Security), observability (JSON log), time, config (composition root, Paho bağlantısı)
```

Kripto çağrıları (`javax.crypto`, `java.security`) yalnızca `infrastructure` içindedir; ArchUnit bunu denetler. Use case hataları `port.inbound` içindedir (`api` yalnızca `facade`'i, `facade` yalnızca `port.inbound`'u görebilir) ve facade bunları HTTP'den bağımsız facade hatalarına çevirir.

## Bilerek kalan zayıflıklar

QBank'ı güvenli hale getirmek bu fazın kapsamı dışındadır (zayıflıklar listesi: [`../README.md`](../README.md)). Bu serviste: RSA-1024 anahtarı ve SHA-1 imza (makbuz), RSA-OAEP kart token'ı, RS256 JWT doğrulaması, RSA-2048 sertifikalı mTLS ve klasik (JDK varsayılanı) TLS anahtar değişimi. Ek olarak şunları bilin:

- `GET /payments/{id}` ve makbuz ucunda sahiplik denetimi yoktur: geçerli JWT'si olan herkes her ödemeyi ve makbuzu okuyabilir (BOLA, D-102).
- Token'da `iss` ve `aud` yoktur; hesap servisinin token'ı bu serviste de geçerlidir.
- Mosquitto'da ACL yoktur (D-108): CA imzalı her istemci sertifikası başka bir terminal adına yayın yapabilir; konudaki `terminalId` ile mesajdakinin eşitliği gönderen kimliğini kanıtlamaz. MQTT oturumu kalıcıdır (`cleanSession=false`, D-107).
- `Idempotency-Key` yarışı serileştirilmez: aynı anahtarla eşzamanlı ilk istekler ikisi de çalışabilir (bellek içi demo).
- Hesap servisinden JWKS alınamazsa (ilk istekte) token doğrulaması 401 döner, 503 değil.
- JWT saat kayması Spring varsayılanıdır (60 sn); hesap servisinde 0 sn'dir.

## Docker

`Dockerfile` çok aşamalıdır (`gradle:9.8.0-jdk25` ile build, `eclipse-temurin:25.0.4.1_1-jre` ile çalıştırma), `USER 10001` ile çalışır. Build bağlamı `reference-system/` dizinidir (MQTT mesaj şeması `contracts/`'tan kopyalanır); `Dockerfile.dockerignore` `certs/` dizinini (özel anahtarlar) bağlamdan çıkarır. `<Dockerfile>.dockerignore` yalnızca BuildKit'te geçerlidir (Docker 23 ve sonrasında varsayılan); `DOCKER_BUILDKIT=0` ile eski builder kullanılırsa `certs/out/*.key.pem` build bağlamı olarak daemon'a gönderilir (imaja girmez, `COPY` seçicidir). Sertifika, anahtar ve `.env` imaja girmez; çalıştırırken yalnızca bu servisin dosyaları (yukarıdaki liste) salt okunur bağlanır.

**Doğrulanmadı:** `gradle` ve `temurin` imajları bu fazda çekilmediği için `docker build`, `HEALTHCHECK` (`curl`'ün çalışma imajında bulunduğu varsayımı) ve `USER 10001` ile sertifika okuma denenmemiştir. Compose girişi P1.4'tedir.
