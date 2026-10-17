---
id: strateji-tablosu
title: "Kripto geçiş stratejileri ve öncelik tablosu (P0–P3)"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.18–19; crypto-domain"
applies_to: {}
language: tr
status: draft
---

Quancrypt bulguları dört öncelik düzeyinde sınıflandırır ve her düzey için bir geçiş stratejisi önerir.

| Öncelik | Bulgu türü | Strateji kodu | Strateji |
|---|---|---|---|
| P0 | Bugün kırılabilen zayıf klasik kripto: MD5 veya SHA-1 imza, DES/3DES, blok şifrelerde (AES, DES) ECB modu, 2048 bitten kısa RSA, PKCS#1 v1.5 şifreleme | FIX_WEAK_CLASSIC | Güncel standarda düzeltme (SHA-256 ve üstü, AES-GCM) veya doğrudan ML-KEM; mekanizma JCA |
| P1 | Servisler arası TLS ve mTLS anahtar değişimi | HYBRID_TLS_KEX | Hibrit X25519MLKEM768 |
| P1 | Uygulama içi RSA şifreleme ve anahtar sarma | KEM_DEM_ENCRYPTION | ML-KEM ile anahtar kapsülleme, HKDF ve AES-GCM (KEM-DEM) |
| P1 | Saha cihazı bağlantıları (MQTT üzerinden TLS) | DEVICE_HYBRID_TLS | Cihazda hibrit anahtar değişimi; zayıf mikrodenetleyicilerde TLS'i gateway'de sonlandırma |
| P2 | Uzun ömürlü imzalar: belgeler, denetim kayıtları, yazılım paketleri | PQ_SIGNATURE | ML-DSA veya hibrit (RSA ve ML-DSA) imza |
| P3 | Kısa ömürlü token'lar (JWT RS256) | KEEP_SHORT_LIVED_TOKEN | Kısa vadede korunur; JOSE kütüphane desteği olgunlaştıkça ML-DSA'ya geçilir |
| P3 | Sertifikalar ve mTLS kimlik doğrulaması | HYBRID_KEX_CLASSIC_CERT | Kısa vadede klasik sertifika ile hibrit anahtar değişimi; post-kuantum sertifikalar test ortamında |

Destekleyici plan maddesi JDK_UPGRADE'dir: hedef JDK sürümüne yükseltme önerisi.

RSA için JCA'nın "RSA/ECB/..." dönüşümlerindeki "ECB" bir blok şifre modu değildir ve P0 ECB kuralına girmez. Proje dokümanı saha cihazı bağlantıları için P1–P2 aralığı verir; Quancrypt prototipi bunları P1 olarak sınıflandırır.
