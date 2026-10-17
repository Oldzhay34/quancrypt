---
id: saha-cihazlari-boyutlar
title: "Saha cihazları ve boyut tablosu: ML-KEM, ML-DSA ve RSA'nın bayt boyutları"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.17, 20; crypto-domain"
applies_to: {}
language: tr
status: draft
---

Saha cihazı bağlantıları (MQTT üzerinden TLS) için geçiş stratejisi: cihazda hibrit anahtar değişimi; zayıf mikrodenetleyicilerde TLS'i gateway'de sonlandırma. OpenSSL 3.5 ve sonrası X25519MLKEM768'i varsayılan olarak sunar; cihazda grup ayarı `openssl.cnf` içindedir.

Proje dokümanındaki PYNQ-Z2 demosunda kart bir MQTT broker'ına TLS ile bağlanan saha terminali rolünü oynar. Geçişten önce RSA sertifikası ve klasik anahtar değişimi kullanır; geçişten sonra kartta derlenen OpenSSL 3.5 ile X25519MLKEM768 müzakere edilir.

Zayıf cihazlarda boyut önemlidir:

| Değer | Boyut |
|---|---|
| ML-KEM-768 açık anahtar | 1.184 bayt |
| ML-KEM-768 şifreli metin | 1.088 bayt |
| ML-DSA-65 açık anahtar | 1.952 bayt |
| ML-DSA-65 imza | 3.309 bayt |
| RSA-2048 imza | 256 bayt |

Netleştirme protokolündeki beşinci soru bu yüzden cihaz donanımını ve OpenSSL sürümünü sorar.
