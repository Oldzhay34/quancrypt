---
id: etsi-qkd-014-uclar
title: "ETSI GS QKD 014: REST tabanlı anahtar dağıtım API'sinin uçları ve veri biçimleri"
source_url: "https://www.etsi.org/deliver/etsi_gs/QKD/001_099/014/01.01.01_60/gs_qkd014v010101p.pdf"
source_type: SPECIFICATION
version_tag: "ETSI GS QKD 014 V1.1.1 (2019-02)"
applies_to: {}
language: tr
status: draft
---

ETSI GS QKD 014 V1.1.1 (Şubat 2019), "Quantum Key Distribution (QKD); Protocol and data format of REST-based key delivery API", bir QKD ağının bir uygulamaya anahtar sunması için HTTPS üzerinden REST protokolünü ve JSON veri biçimini tanımlar.

Ortak kurallar: HTTPS, TLS 1.2 veya üstü, UTF-8, içerik türü application/json. Bağlantı kurulurken SAE (uygulama) ile KME (anahtar yönetim varlığı) arasında karşılıklı kimlik doğrulama yapılır: SAE, KME'nin sertifikasını ve KME kimliğini doğrulamadan API'yi kullanmaz; KME de SAE'nin sertifikasını ve SAE kimliğini doğrulamadan bağlantıyı kabul etmez.

Üç yöntem vardır:

| Yöntem | URL | Erişim |
|---|---|---|
| Get status | `https://{KME_hostname}/api/v1/keys/{slave_SAE_ID}/status` | GET |
| Get key | `https://{KME_hostname}/api/v1/keys/{slave_SAE_ID}/enc_keys` | POST (veya basit isteklerde GET) |
| Get key with key IDs | `https://{KME_hostname}/api/v1/keys/{master_SAE_ID}/dec_keys` | POST (veya basit isteklerde GET) |

Get status yanıtı (Status) şu alanları taşır: source_KME_ID, target_KME_ID, master_SAE_ID, slave_SAE_ID, key_size, stored_key_count, max_key_count, max_key_per_request, max_key_size, min_key_size ve max_SAE_ID_count. Get key isteği (Key request) isteğe bağlı olarak number (varsayılan 1), size (bit; varsayılanı Status'taki key_size) ve additional_slave_SAE_IDs alanlarını alır. Üç yöntem de 400 (hatalı istek), 401 (yetkisiz) ve 503 (sunucu hatası) dönebilir. Get key ve Get key with key IDs sonrasında verilen anahtarlar KME'nin anahtar havuzundan çıkarılır.
