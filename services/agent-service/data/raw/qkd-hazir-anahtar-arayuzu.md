---
id: qkd-hazir-anahtar-arayuzu
title: "QKD'ye hazır anahtar arayüzü: KeyMaterialProvider ve birleşik sağlayıcı"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.19; crypto-domain"
applies_to: {}
language: tr
status: draft
---

Quancrypt'in hedef kalıbında anahtar malzemesi bir `KeyMaterialProvider` arayüzünün arkasından gelir ve arayüzün üç uygulaması vardır:

- `PqcKemProvider`: ML-KEM ile anahtar kurar.
- `QkdEtsi014Provider`: QKD donanımından ETSI GS QKD 014 ile anahtar alır.
- `CombinedProvider`: iki sırrı HKDF ile birleştirir. Sırlardan biri kırılsa bile diğeri anahtarı korur.

`SimulatedKme`, önceki projenin Q# BB84 simülatörünü ETSI 014 REST arayüzüyle sarar. Yalnızca test profilinde açılır; üretim profilinde etkinleştirilirse uygulama başlamayı reddeder. ETSI 014 çağrıları HTTPS üzerinden yapılır ve bu kanalın kendisi de hibrit post-kuantum TLS kullanır.

BB84 için Shor–Preskill sınırına göre QBER yaklaşık %11'in altındaysa güvenli anahtar çıkarılabilir; tam intercept-resend saldırısı elenmiş anahtarda yaklaşık %25 QBER üretir.
