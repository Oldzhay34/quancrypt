---
id: qkd-sinirlari
title: "QKD'nin sınırları: yazılımla kurulamaz, özel donanım ve fiziksel kanal gerektirir"
source_url: "https://www.nsa.gov/Cybersecurity/Quantum-Key-Distribution-QKD-and-Quantum-Cryptography-QC/"
source_type: GOVERNMENT_GUIDANCE
version_tag: "NSA, QKD ve Quantum Cryptography sayfası"
applies_to: {}
language: tr
status: draft
---

NSA'ya göre kuantum anahtar dağıtımı (QKD) yazılımla kurulamaz; özel donanım ve fiziksel kanal gerektirir. Proje dokümanına göre QKD fiziksel kanal gerektirir; Quancrypt onu yalnızca donanımı olan kurumlar için arayüz düzeyinde destekler.

Quancrypt QKD'yi yalnızca ETSI GS QKD 014 arayüzü düzeyinde destekler: QKD donanımı olan kurumlar için ETSI standardında bir anahtar arayüzü sunulur. QKD donanımının kendisini yazılımla kurmaya çalışmaz. İki sırrı (ML-KEM ve QKD) HKDF ile birleştiren bir birleşik sağlayıcı da vardır (QKD'ye hazır anahtar arayüzü notuna bakın).
