# qbank-gateway

QBank gateway'i (referans sistem, bilerek RSA ile kurulmuştur): dış istemciye TLS sunar ve istekleri hesap ve ödeme servislerine mTLS ile iletir. **Yalnızca yapılandırma ve rota içerir; iş mantığı ve hexagonal katman yoktur** (D-06). Tek kod parçası log biçimlendiricisidir (`JsonLogFormatter`, D-110). Java 25, Spring Boot 4.0.8 ve Spring Cloud 2025.1.3 (gateway 5.0.3; D-39), Gradle Kotlin DSL; WebFlux (Reactor Netty) sürümü kullanılır, çünkü MVC sürümünde TLS ayarı yoktur ve WebFlux'ta HttpClient bir SSL bundle alabilir (D-109).

## Rotalar ve TLS

| Yol | Hedef |
|---|---|
| `/api/v1/auth/**`, `/api/v1/accounts/**`, `/.well-known/jwks.json` | `qbank-account-service` (`ACCOUNT_SERVICE_URL`) |
| `/api/v1/payments/**` | `qbank-payment-service` (`PAYMENT_SERVICE_URL`) |

Başka yol 404 döner. Gateway kimlik doğrulama yapmaz. Spring Cloud Gateway'in varsayılan davranışıyla `Forwarded`/`X-Forwarded-*` başlıkları ekleyebilir ve hop-by-hop başlıkları kaldırır (bu fazda ölçülmedi); gateway'in kendi ürettiği hata gövdeleri (404, 5xx) RFC 9457 `problem+json` olmayabilir, ve gateway'de yeniden deneme ya da devre kesici yoktur (yalnızca zaman aşımı). Uygulama başlıkları: `Authorization`, `Idempotency-Key` ve `X-Trace-Id` arka uca olduğu gibi gider, yanıttaki `X-Trace-Id` arka uçtan gelir (gateway kendisi iz kimliği üretmez; arka uçlar üretir).

- **Dış istemciye:** TLS (RSA-2048 `qbank-gateway` sertifikası, SAN `qbank-gateway` ve `localhost`), istemci sertifikası istenmez (`client-auth: none`). Port 9443; compose'ta `127.0.0.1:9443`.
- **Arka uçlara:** mTLS. HttpClient SSL ayarı global olduğundan iki arka uç için **tek istemci kimliği** vardır: `gateway-to-account` (D-109). Arka uç sertifikasının ana bilgisayar adı doğrulanır (`BackendHostnameVerificationTest`).

## Yapılandırma

Yalnızca ortam değişkenleriyle yapılandırılır; varsayılanlar yerel geliştirme içindir (imajda `Dockerfile` değerleri geçerlidir).

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `QBANK_CERTS_DIR` | `../certs/out` (imajda `/certs`) | PEM dizini |
| `SERVER_PORT` | `9443` | Dış TLS portu |
| `MANAGEMENT_SERVER_PORT` | `9543` | Sağlık portu (düz HTTP, loopback, yayımlanmaz) |
| `ACCOUNT_SERVICE_URL` | `https://localhost:9444` (imajda `https://qbank-account-service:9444`) | Hesap servisi |
| `PAYMENT_SERVICE_URL` | `https://localhost:9445` (imajda `https://qbank-payment-service:9445`) | Ödeme servisi |

Kullanılan dosyalar (`QBANK_CERTS_DIR` altında): `qbank-gateway.crt.pem` ve `.key.pem` (sunucu kimliği), `gateway-to-account.crt.pem` ve `.key.pem` (arka uç istemci kimliği), `ca.crt.pem` (güven kökü).

## Komutlar

```bash
make verify   # sertifikaları üretir (yoksa), sonra ./gradlew check
make run      # servisi yerelde çalıştırır (hesap ve ödeme servisi ayrıca çalışmalıdır)
make image    # Docker imajı: qbank-gateway:1.0.0
```

`make verify` Checkstyle, SpotBugs ve testleri çalıştırır: rotalar ve istemci kimliği (JDK `HttpsServer` test çiftleri, gerçek servis sertifikalarıyla), dış TLS, düz HTTP reddi, arka uç ana bilgisayar adı doğrulaması, yönetim portu ve log biçimi.

## Bilerek kalan zayıflıklar

Zayıflıklar listesi: [`../README.md`](../README.md). Bu serviste: RSA-2048 sertifikalı TLS ve mTLS, JDK/Netty varsayılanı klasik anahtar değişimi; gateway istek sınırı, hız sınırı veya kimlik doğrulama uygulamaz.

## Docker

`Dockerfile` çok aşamalıdır (`gradle:9.8.0-jdk25` ve `eclipse-temurin:25.0.4.1_1-jre`), `USER 10001` ile çalışır; sertifika ve anahtar imaja girmez, çalıştırırken yalnızca bu servisin dosyaları (yukarıdaki liste) salt okunur bağlanır. Sağlık kontrolü (`HEALTHCHECK`) `bash`'in `/dev/tcp`'si ile yönetim portundaki `GET /health/liveness`'ı çağırır (JRE imajında `curl` ve `wget` yoktur, D-120).
