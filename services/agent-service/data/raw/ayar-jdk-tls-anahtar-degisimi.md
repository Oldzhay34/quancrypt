---
id: ayar-jdk-tls-anahtar-degisimi
title: "Ayar kataloğu: JDK TLS anahtar değişim grupları (jdk.tls.namedGroups)"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.16; crypto-domain"
applies_to: {}
language: tr
status: draft
---

JDK'nın TLS anahtar değişim grupları `jdk.tls.namedGroups` sistem özelliğiyle ayarlanır. JDK 27'de X25519MLKEM768 hibrit grubu zaten listenin başındadır (JEP 527).

JDK 27 öncesinde TLS 1.3 varsayılan anahtar değişim grupları klasiktir: ECDHE ve FFDHE; hibrit grup yoktur. Kesin varsayılan sıra, kullanılan JDK sürümünün JSSE belgesinden doğrulanmalıdır.

Hibrit TLS anahtar değişimine geçiş yolları sürüm matrisi notundadır (JDK 27, JDK 25 güncellemesi, JDK 17 ve 21 için 2027, Bouncy Castle JSSE).
