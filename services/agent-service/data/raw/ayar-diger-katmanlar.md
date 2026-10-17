---
id: ayar-diger-katmanlar
title: "Ayar kataloğu: Spring sunucu ve istemcileri, kripto sağlayıcısı, keystore, JWT, altyapı ve saha cihazı"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.16–17"
applies_to: {}
language: tr
status: draft
---

Proje dokümanındaki ayar kataloğu, bir geliştiricinin hibrit veya post-kuantum geçişte dokunacağı katmanları şöyle sıralar:

| Katman | Ayar | Örnek |
|---|---|---|
| JDK TLS | Anahtar değişim grupları | `jdk.tls.namedGroups` sistem özelliği; JDK 27'de X25519MLKEM768 zaten listenin başında |
| Spring Boot sunucusu | TLS sürümü ve SSL paketi | `server.ssl.enabled-protocols=TLSv1.3`, `server.ssl.bundle` ve `spring.ssl.bundle.*` |
| Spring istemcileri | RestClient, WebClient ve Feign'in TLS ayarı | Aynı SSL paketinin istemcilere bağlanması |
| Kripto sağlayıcısı | Bouncy Castle kaydı ve sırası (JDK 24 öncesi) | `java.security` dosyası veya `Security.insertProviderAt` |
| Keystore | Anahtar ve sertifika biçimi | PKCS#12; test ortamında ML-DSA sertifikaları |
| Spring Security | JWT imza algoritmaları | `spring.security.oauth2.resourceserver.jwt.jws-algorithms` |
| Uygulama politikası | Algoritma seçimi | `CryptoPolicy` yapılandırması |
| Altyapı | Ingress, ters proxy, servis mesh | nginx veya Envoy'un OpenSSL 3.5 ile hibrit grubu sunması |
| Saha cihazı | OpenSSL grup listesi | `openssl.cnf` içindeki grup ayarı |

TLS çoğu zaman uygulamada değil, ingress'te veya servis mesh'te sonlanır. Bu yüzden yalnızca Java ayarlarına bakmak yetmez; altyapı katmanı da sorgulanmalıdır.
