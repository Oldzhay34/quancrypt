---
id: spring-boot-ssl-paketleri
title: "Spring Boot SSL paketleri: spring.ssl.bundle ve server.ssl.bundle ayarları"
source_url: "https://docs.spring.io/spring-boot/reference/features/ssl.html"
source_type: VENDOR_DOC
version_tag: "Spring Boot referans belgesi, SSL sayfası"
applies_to: {}
language: tr
status: draft
---

Spring Boot, TLS malzemesini adlandırılmış SSL paketleriyle (SSL bundles) tanımlar. Her paketin kullanıcı verdiği bir adı vardır ve paket ada göre başvurulur.

Java KeyStore dosyaları (JKS veya PKCS12) için ayarlar:
- `spring.ssl.bundle.jks.<paket-adı>.key.alias`
- `spring.ssl.bundle.jks.<paket-adı>.keystore.location`, `.keystore.password`, `.keystore.type`
- `spring.ssl.bundle.jks.<paket-adı>.truststore.location`, `.truststore.password`

PEM kodlu sertifikalar için ayarlar:
- `spring.ssl.bundle.pem.<paket-adı>.keystore.certificate` ve `.keystore.private-key`
- `spring.ssl.bundle.pem.<paket-adı>.truststore.certificate`
- `spring.ssl.bundle.pem.<paket-adı>.reload-on-update`

Bir paketi gömülü web sunucusuna bağlamak için `server.ssl.bundle` kullanılır. Değer biçimleri: bir konum (`classpath:` veya `file:`), `base64:` önekli Base64 içerik ya da BEGIN/END işaretleri taşıyan satır içi PEM. Ortam değişkenlerinde paket adları küçük harfe çevrilir.

Otomatik yapılandırılan `SslBundles` bean'i ile kodda `getBundle("paketadı")` çağrılabilir. `SslBundle` üzerinden `getStores()`, `getManagers()` ve `createSslContext()` kullanılabilir. Paketi dosya değişince yeniden yüklemek için `reload-on-update` ile açıkça seçim yapılır; belgede uyumlu olarak yalnızca Tomcat ve Netty web sunucuları sayılır.
