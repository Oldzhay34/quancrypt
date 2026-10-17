---
id: nist-ir-8547-gecis-takvimi
title: "NIST IR 8547 (ilk kamuya açık taslak): kuantuma açık algoritmaların geçiş takvimi"
source_url: "https://csrc.nist.gov/pubs/ir/8547/ipd"
source_type: STANDARD
version_tag: "NIST IR 8547 ipd (Kasım 2024, taslak)"
applies_to: {}
language: tr
status: draft
---

NIST IR 8547, "Transition to Post-Quantum Cryptography Standards", 12 Kasım 2024'te ilk kamuya açık taslak (initial public draft) olarak yayımlanmıştır. Rapor, NIST'in kuantuma açık algoritmalardan post-kuantum imza ve anahtar kurma şemalarına geçişe ilişkin beklenen yaklaşımını anlatır. Bu bir taslaktır; yorum süresi 10 Ocak 2025'te kapanmıştır.

Taslaktaki geçiş tablolarına göre:
- İmza: ECDSA ve RSA için 112 bit güvenlik gücü 2030'dan sonra kullanımdan kaldırılır (deprecated), 2035'ten sonra yasaklanır (disallowed); 128 bit ve üzeri güvenlik gücü 2035'ten sonra yasaklanır. EdDSA (128 bit ve üzeri) 2035'ten sonra yasaklanır.
- Anahtar kurma: sonlu cisim DH ve MQV, eliptik eğri DH ve MQV, ve RSA (SP 800-56B) için aynı takvim geçerlidir: 112 bit güvenlik gücü 2030'dan sonra kullanımdan kaldırılır ve 2035'ten sonra yasaklanır; 128 bit ve üzeri 2035'ten sonra yasaklanır.

Taslak ayrıca NSM-10'u anar: NSM-10, federal sistemlerde post-kuantum kriptografiye geçişi tamamlamak için birincil hedef yıl olarak 2035'i belirler.
