---
id: surum-matrisi
title: "Sürüm matrisi: JDK, Bouncy Castle ve OpenSSL'de post-kuantum desteği"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.18; crypto-domain"
applies_to: {}
language: tr
status: draft
---

| Bileşen | Bilgi |
|---|---|
| JDK 21 | `javax.crypto.KEM` API'si JDK 21'den beri vardır. |
| JDK 24 | ML-KEM (JEP 496) ve ML-DSA (JEP 497). |
| JDK 27 | 15 Eylül 2026'da çıktı; TLS 1.3'te hibrit `X25519MLKEM768` varsayılandır (JEP 527). |
| JDK 27 öncesi | TLS 1.3 varsayılan anahtar değişim grupları klasiktir (ECDHE ve FFDHE; hibrit yok). Kesin sıra, kullanılan JDK sürümünün JSSE belgesinden doğrulanır. |
| JDK 25, 21, 17 | Oracle'ın duyurusuna göre hibrit grup JDK 25'e Ekim 2026 CPU'su ile, JDK 21 ve 17'ye 2027'nin ilk yarısında gelir. Kullanılan OpenJDK dağıtımında ayrıca doğrulanmalıdır. |
| Bouncy Castle | Eski JDK'larda post-kuantum kriptografi ve hibrit TLS için BC ve BCJSSE yolu (proje dokümanında 1.86 sürüm notu). Post-kuantum (ML-DSA) sertifikalar için de Bouncy Castle desteği anılır. |
| OpenSSL | 3.5.0 (Nisan 2025): ML-KEM, ML-DSA, SLH-DSA; `X25519MLKEM768` varsayılan anahtar paylaşımındadır. |

Servisler arası TLS için hibrit anahtar değişimine geçiş yolu proje dokümanında şöyle özetlenir: JDK 27'de varsayılan; JDK 25 için Ekim 2026 güncellemesiyle; JDK 17 ve 21 için 2027'nin ilk yarısı ya da Bouncy Castle JSSE. Uygulama içi şifreleme ve imza için ML-KEM ve ML-DSA JDK 24 ve sonrasında yerleşiktir; eski JDK'larda Bouncy Castle kullanılır.
