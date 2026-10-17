---
id: oncelik-mantigi
title: "Öncelik mantığı: neden önce anahtar kurulumu ve şifreleme, en son token ve sertifika"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.18; crypto-domain"
applies_to: {}
language: tr
status: draft
---

Öncelik "şimdi topla, sonra çöz" tehdidine göre belirlenir. Sıra şöyledir:

1. Bugün kırılabilen zayıf klasik kripto her zaman ilk sıradadır (P0).
2. Sonra anahtar kurulumu ve şifreleme gelir (P1): servisler arası TLS ve mTLS anahtar değişimi, uygulama içi RSA şifreleme ve anahtar sarma, saha cihazı bağlantıları.
3. Sonra uzun ömürlü imzalar gelir (P2): belgeler, denetim kayıtları, yazılım paketleri.
4. En son kısa ömürlü token'lar ve sertifikalar gelir (P3).

İmzalar bu tehditten etkilenmez, çünkü sahte bir imza ancak kuantum bilgisayarı gerçekten varken atılabilir.
