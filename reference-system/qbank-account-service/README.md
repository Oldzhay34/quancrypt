# qbank-account-service

QBank hesap servisi (referans sistem, bilerek RSA ile kurulmuştur): kullanıcıya RS256 imzalı JWT verir, JWT'yi doğrulayan açık anahtarı JWKS olarak yayımlar ve hesap bilgisini sunar. Java 25, Spring Boot, Gradle Kotlin DSL; hexagonal ve SOLID (D-05); veritabanı yok, bellek içi adaptör (D-29). Paket kökü `com.quancrypt.qbank.account`.

Kontrat: [`../contracts/qbank-account.openapi.yaml`](../contracts/qbank-account.openapi.yaml). Kod kontrata uyar; sözleşme testi (`ApiContractTest`) bunu denetler.

## Uçlar ve erişim kuralları

Ana port (varsayılan 9444) **tüm uçlarda mTLS** ister (`server.ssl.client-auth: need`, D-80): geçerli bir demo CA istemci sertifikası olmadan TLS el sıkışması reddedilir.

| Uç | Ek kural |
|---|---|
| `POST /api/v1/auth/login` | Kullanıcı adı ve parola; yanıt `accessToken` (RS256 JWT), `tokenType`, `expiresIn` (900 sn) |
| `GET /.well-known/jwks.json` | JWT'yi doğrulayan RSA açık anahtarı (RFC 7517), `kid` JWT başlığındakiyle aynıdır |
| `GET /api/v1/accounts/{accountId}` | Bearer JWT gerekir; yalnızca token sahibinin hesabı okunabilir (başkasının hesabı 403, olmayan hesap 404, `[A-Za-z0-9._-]` dışı karakter veya 64'ten uzun kimlik 400, D-105) |

Token'da yalnızca `sub` (kullanıcı adı), `iat` ve `exp` vardır; başlıkta `alg=RS256` ve `kid` (RFC 7638 JWK thumbprint) bulunur (D-86). Hatalar RFC 9457 `application/problem+json` biçimindedir; her yanıt `X-Trace-Id` taşır.

Sağlık uçları (`/health/liveness`, `/health/readiness`) ayrı bir yönetim portundadır (varsayılan 9544): düz HTTP, yalnızca konteyner içinde `127.0.0.1`'e bağlı, yayımlanmaz (D-88).

## Demo kimlik bilgileri (D-87)

Bunlar yalnızca demo kullanıcılarıdır. Kaynakta yalnızca BCrypt hash'leri bulunur (`src/main/resources/demo-data.yaml`).

| Kullanıcı | Parola | Hesap | Sahip | Bakiye |
|---|---|---|---|---|
| `demo1` | `demo1-demo-pass` | `acc-001` | Demo User 1 | 1000.00 TRY |
| `demo2` | `demo2-demo-pass` | `acc-002` | Demo User 2 | 2500.50 TRY |
| `demo3` | `demo3-demo-pass` | `acc-003` | Demo User 3 | 10000.00 TRY |

## Yapılandırma

Yalnızca ortam değişkenleriyle yapılandırılır; varsayılanlar yerel geliştirme içindir.

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `QBANK_CERTS_DIR` | `../certs/out` (imajda `/certs`) | `reference-system/certs/generate.sh`'ın ürettiği PEM dizini |
| `SERVER_PORT` | `9444` | mTLS ana portu |
| `MANAGEMENT_SERVER_PORT` | `9544` | Sağlık portu (düz HTTP, loopback) |
| `QBANK_JWT_TTL_SECONDS` | `900` | JWT geçerlilik süresi (D-81) |

Kullanılan dosyalar (`QBANK_CERTS_DIR` altında): `qbank-account-service.crt.pem` ve `.key.pem` (sunucu kimliği), `ca.crt.pem` (istemci sertifikalarını doğrulayan güven kökü), `jwt-signing.key.pem` ve `jwt-signing.pub.pem` (JWT imzası ve JWKS). Özel anahtar dosyaları yalnızca bu servisin ihtiyaç duyduğu dosyalardır; `ca.key.pem` hiçbir servise bağlanmamalıdır.

## Komutlar

```bash
make verify   # sertifikaları üretir (yoksa), sonra ./gradlew check
make run      # servisi yerelde çalıştırır
make image    # Docker imajı: qbank-account-service:1.0.0
```

`make verify` şunları çalıştırır: Checkstyle, SpotBugs, ArchUnit (mimari), birim, port sözleşmesi (LSP), API sözleşmesi, mTLS entegrasyonu ve JaCoCo (domain ve usecase için en az %75 satır kapsamı). Testler gerçek demo sertifikalarını kullanır; sertifikalar yoksa `make certs` gerekir.

## Katmanlar

```
api            controller, DTO, hata işleyici (problem+json), TraceIdFilter
facade         kaba taneli giriş noktaları ve facade DTO/hataları
port.inbound   use case arayüzleri, komut/sorgu/sonuç kayıtları, use case hataları
port.outbound  AccountRepository, CredentialRepository, PasswordVerifier, TokenIssuer, VerificationKeySource, Clock
usecase        AuthenticateUserService, GetAccountService, GetJwksService
domain         Account, AccountId, UserCredential, PasswordHash, VerificationKey (yalnızca java.*)
infrastructure bellek içi depolar, BCrypt, Nimbus JWT, PEM yükleme, AccessTokenFilter, JSON log, config (composition root)
```

Use case hataları (`InvalidCredentialsException`, `AccountNotFoundException`, `AccountAccessDeniedException`, `InvalidRequestException`) `port.inbound` içindedir: `api` yalnızca `facade`'i, `facade` yalnızca `port.inbound`'u görebildiği için hata türleri use case sözleşmesinin parçasıdır ve facade bunları HTTP'den bağımsız facade hatalarına çevirir.

## Bilerek kalan zayıflıklar

QBank'ı güvenli hale getirmek bu fazın kapsamı dışındadır (zayıflıklar listesi: [`../README.md`](../README.md)). Bu serviste: RS256 JWT, RSA-2048 sertifikalı mTLS ve klasik (JDK varsayılanı) TLS anahtar değişimi. Ek olarak şunları bilin: tüm demo parolaları bu README'de açıktır; bilinmeyen kullanıcı için parola doğrulaması çalıştırılmadığından yanıt süresi kullanıcı varlığını sezdirebilir.

## Docker

`Dockerfile` çok aşamalıdır (`gradle:9.8.0-jdk25` ile build, `eclipse-temurin:25.0.4.1_1-jre` ile çalıştırma), `USER 10001` ile çalışır; sertifika, anahtar ve `.env` imaja girmez. Çalıştırırken yalnızca bu servisin ihtiyaç duyduğu beş dosya salt okunur bağlanır; `certs/out` dizininin tamamı (CA özel anahtarı ve diğer servislerin anahtarları dahil) bağlanmaz:

```bash
C="$PWD/../certs/out"
docker run --rm -p 127.0.0.1:9444:9444 \
  -v "$C/qbank-account-service.crt.pem:/certs/qbank-account-service.crt.pem:ro" \
  -v "$C/qbank-account-service.key.pem:/certs/qbank-account-service.key.pem:ro" \
  -v "$C/ca.crt.pem:/certs/ca.crt.pem:ro" \
  -v "$C/jwt-signing.key.pem:/certs/jwt-signing.key.pem:ro" \
  -v "$C/jwt-signing.pub.pem:/certs/jwt-signing.pub.pem:ro" \
  qbank-account-service:1.0.0
```

**Doğrulanmadı:** Docker imajı bu fazda çekilmediği için `docker build`, `HEALTHCHECK` (`curl`'ün çalışma imajında bulunduğu varsayımı) ve yukarıdaki çalıştırma komutu denenmemiştir. Compose girişi P1.4'tedir.
