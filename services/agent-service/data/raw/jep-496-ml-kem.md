---
id: jep-496-ml-kem
title: "JEP 496: Kuantuma dirençli modül-kafes tabanlı anahtar kapsülleme mekanizması (ML-KEM)"
source_url: "https://openjdk.org/jeps/496"
source_type: JEP
version_tag: "JDK 24 (JEP 496, Closed/Delivered)"
applies_to:
  java: ">=24"
language: tr
status: draft
---

JEP 496 ("Quantum-Resistant Module-Lattice-Based Key Encapsulation Mechanism") durumu Closed/Delivered'dır ve JDK 24'te yayımlanmıştır.

JEP, NIST'in FIPS 203'te standartlaştırdığı ML-KEM'in Java gerçeklemesini ekler; uygulamalar simetrik anahtarlarını gelecekteki kuantum saldırılarına karşı koruyabilir. ML-KEM-512, ML-KEM-768 ve ML-KEM-1024 parametre kümeleri `KeyPairGenerator`, `KEM` ve `KeyFactory` API'leriyle desteklenir. JEP, Kyber'in kendisini gerçeklemez ve ML-KEM'i TLS'e eklemez.
