---
id: jep-527-hibrit-tls
title: "JEP 527: TLS 1.3 için post-kuantum hibrit anahtar değişimi"
source_url: "https://openjdk.org/jeps/527"
source_type: JEP
version_tag: "JDK 27 (JEP 527, Closed/Delivered)"
applies_to: {}
language: tr
status: draft
---

JEP 527 ("Post-Quantum Hybrid Key Exchange for TLS 1.3") durumu Closed/Delivered'dır ve JDK 27'de yayımlandı.

JEP, JDK'nın TLS 1.3 gerçeklemesine üç hibrit anahtar değişim şeması ekler. Her biri ML-KEM'i bir ECDHE algoritmasıyla eşler. İstemcinin tercih listesinde varsayılan olarak X25519MLKEM768 en başa konur; `javax.net.ssl` kullanan uygulamalar, belirli grupları seçmedikçe, kod değişikliği olmadan bunu alır. SecP256r1MLKEM768 ve SecP384r1MLKEM1024 varsayılan olarak etkin değildir.

JEP'te yazılı varsayılan adlandırılmış grup sırası: X25519MLKEM768, x25519, secp256r1, secp384r1, secp521r1, x448, ffdhe2048, ffdhe3072 ve ffdhe4096.
