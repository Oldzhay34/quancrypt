---
id: jep-497-ml-dsa
title: "JEP 497: Kuantuma dirençli modül-kafes tabanlı sayısal imza algoritması (ML-DSA)"
source_url: "https://openjdk.org/jeps/497"
source_type: JEP
version_tag: "JDK 24 (JEP 497, Closed/Delivered)"
applies_to:
  java: ">=24"
language: tr
status: draft
---

JEP 497 ("Quantum-Resistant Module-Lattice-Based Digital Signature Algorithm") durumu Closed/Delivered'dır ve JDK 24'te yayımlanmıştır.

JEP, NIST'in FIPS 204'te standartlaştırdığı ML-DSA'nın Java gerçeklemesini ekler. ML-DSA-44, ML-DSA-65 ve ML-DSA-87 parametre kümeleri için `KeyPairGenerator`, `Signature` ve `KeyFactory` desteği sağlanır; varsayılan parametre kümesi ML-DSA-65'tir.
